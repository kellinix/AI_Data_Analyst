"""Run only against an explicitly selected, migrated disposable PostgreSQL DB."""

from __future__ import annotations

import asyncio
import copy
import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import deps
from app.models.pro_pass import ProPass
from app.models.subscription import Subscription
from app.models.user import User
from app.services import billing_service, pro_pass_service

pytestmark = pytest.mark.skipif(
    not os.getenv("BILLING_TEST_DATABASE_URL"), reason="Needs disposable PostgreSQL"
)


@pytest.fixture
async def payment(monkeypatch):
    engine = create_async_engine(os.environ["BILLING_TEST_DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    token = uuid.uuid4()
    customer = f"cus_{token.hex}"
    intent = f"pi_{token.hex}"
    checkout = f"cs_{token.hex}"
    paid_at = int(time.time()) - 2
    remote = {
        "id": checkout, "mode": "payment", "status": "complete", "payment_status": "paid",
        "customer": customer, "client_reference_id": str(token),
        "currency": "gbp", "amount_total": 599, "amount_subtotal": 599,
        "metadata": {"zephyr_user_id": str(token), "vesquiri_offer": "weekly"},
        "line_items": {"data": [{"price": {"id": "price_weekly"}, "quantity": 1}]},
        "payment_intent": {
            "id": intent, "status": "succeeded", "amount_received": 599,
            "currency": "gbp", "customer": customer,
            "latest_charge": {
                "id": f"ch_{token.hex}", "created": paid_at, "paid": True,
                "captured": True, "amount_captured": 599, "payment_intent": intent,
                "refunded": False, "disputed": False,
            },
        },
    }
    monkeypatch.setattr(billing_service.settings, "stripe_weekly_price_id", "price_weekly")
    monkeypatch.setattr(billing_service.settings, "stripe_live_mode", False)

    async def stripe(method, path, **kwargs):
        assert method == "GET"
        if path.startswith(f"/checkout/sessions/{checkout}?"):
            return copy.deepcopy(remote)
        if path.startswith(f"/checkout/sessions?payment_intent={intent}"):
            return {"data": [copy.deepcopy(remote)]}
        raise AssertionError(f"Unexpected Stripe call: {path}")

    monkeypatch.setattr(billing_service, "stripe_request", stripe)
    async with sessions() as db:
        db.add(User(id=token, supabase_id=str(token), email=f"weekly-{token}@example.test",
                    analyses_this_month=5, ai_queries_this_month=1))
        db.add(Subscription(user_id=token, plan="free", status="canceled",
                            stripe_customer_id=customer, pending_checkout_session_id=checkout,
                            pending_checkout_offer="weekly"))
        await db.commit()

    async def deliver(kind="checkout.session.completed"):
        obj = {"id": checkout, "mode": "payment", "metadata": {"vesquiri_offer": "weekly"}}
        if kind == "charge.refunded":
            obj = {"payment_intent": intent}
        if kind == "charge.dispute.created":
            obj = {"payment_intent": intent}
        async with sessions() as db:
            await billing_service.process_billing_event(db, {"type": kind, "data": {"object": obj}})
            await db.commit()

    try:
        yield SimpleNamespace(
            sessions=sessions, token=token, remote=remote, deliver=deliver,
            checkout=checkout, paid_at=paid_at,
        )
    finally:
        async with sessions() as db:
            await db.execute(delete(User).where(User.id == token))
            await db.commit()
            assert await db.scalar(select(func.count()).select_from(ProPass).where(ProPass.user_id == token)) == 0
        await engine.dispose()


async def test_concurrent_duplicate_events_grant_exactly_seven_days_once(payment):
    await asyncio.gather(payment.deliver(), payment.deliver())
    async with payment.sessions() as db:
        rows = (await db.execute(select(ProPass).where(ProPass.user_id == payment.token))).scalars().all()
        assert len(rows) == 1
        expected_end = datetime.fromtimestamp(payment.paid_at, UTC) + timedelta(days=7)
        assert rows[0].expires_at == expected_end
        user = await db.get(User, payment.token)
        assert user.plan == "starter"
        assert user.pro_pass_expires_at == expected_end
        assert (user.analyses_this_month, user.ai_queries_this_month) == (5, 1)
        record = await db.scalar(select(Subscription).where(Subscription.user_id == payment.token))
        assert record.stripe_subscription_id is None
        assert record.pending_checkout_session_id is None
    await payment.deliver()
    async with payment.sessions() as db:
        assert (await db.get(User, payment.token)).pro_pass_expires_at == expected_end


@pytest.mark.parametrize("refunded_before_success", [False, True])
async def test_full_refund_and_late_success_cannot_restore_access(payment, refunded_before_success):
    if not refunded_before_success:
        await payment.deliver()
    payment.remote["payment_intent"]["latest_charge"]["refunded"] = True
    await payment.deliver("charge.refunded")
    await payment.deliver()
    async with payment.sessions() as db:
        user = await db.get(User, payment.token)
        record = await db.scalar(select(ProPass).where(ProPass.user_id == payment.token))
        assert record.revoked_at is not None
        assert user.plan == "free"
        assert user.pro_pass_expires_at is None


async def test_dispute_revokes_the_pass(payment):
    await payment.deliver()
    payment.remote["payment_intent"]["latest_charge"]["disputed"] = True
    await payment.deliver("charge.dispute.created")
    async with payment.sessions() as db:
        assert (await db.get(User, payment.token)).plan == "free"


async def test_expired_delayed_payment_does_not_start_a_new_week(payment):
    payment.remote["payment_intent"]["latest_charge"]["created"] = int(time.time()) - 8 * 86400
    await payment.deliver()
    async with payment.sessions() as db:
        assert (await db.get(User, payment.token)).plan == "free"


@pytest.mark.parametrize("invalid", ["unpaid", "amount", "price", "owner", "customer", "quantity"])
async def test_unverified_or_mismatched_payment_does_not_grant_access(payment, invalid):
    if invalid == "unpaid":
        payment.remote["payment_status"] = "unpaid"
    elif invalid == "amount":
        payment.remote["amount_total"] = 598
    elif invalid == "price":
        payment.remote["line_items"]["data"][0]["price"]["id"] = "price_other"
    elif invalid == "owner":
        payment.remote["client_reference_id"] = str(uuid.uuid4())
    elif invalid == "customer":
        payment.remote["customer"] = "cus_someone_else"
        payment.remote["payment_intent"]["customer"] = "cus_someone_else"
    elif invalid == "quantity":
        payment.remote["line_items"]["data"][0]["quantity"] = 2
    await payment.deliver()
    async with payment.sessions() as db:
        assert (await db.get(User, payment.token)).plan == "free"
        assert await db.scalar(select(func.count()).select_from(ProPass).where(ProPass.user_id == payment.token)) == 0


async def test_protected_request_expires_the_pass_without_scheduler_or_profile_visit(payment, monkeypatch):
    await payment.deliver()
    async with payment.sessions() as db:
        user = await db.get(User, payment.token)
        user.pro_pass_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    monkeypatch.setattr(deps, "verify_supabase_token", AsyncMock(return_value={"sub": str(payment.token)}))
    async with payment.sessions() as db:
        user = await deps.get_current_user(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="test"), db,
        )
        assert user.plan == "free"
        assert user.pro_pass_expires_at is None
        with pytest.raises(HTTPException) as error:
            deps.ensure_analysis_quota(user)
        assert error.value.status_code == 402
        await db.commit()


def test_deadline_is_exclusive():
    deadline = datetime.now(UTC)
    user = SimpleNamespace(pro_pass_expires_at=deadline)
    assert pro_pass_service.has_current_pro_pass(user, deadline - timedelta(microseconds=1))
    assert not pro_pass_service.has_current_pro_pass(user, deadline)


async def test_refunded_pass_does_not_remove_monthly_access(payment):
    await payment.deliver()
    async with payment.sessions() as db:
        subscription = await db.scalar(select(Subscription).where(Subscription.user_id == payment.token))
        subscription.plan = "starter"
        subscription.status = "active"
        subscription.stripe_subscription_id = "sub_monthly"
        await db.commit()
    payment.remote["payment_intent"]["latest_charge"]["refunded"] = True
    await payment.deliver("charge.refunded")
    async with payment.sessions() as db:
        user = await db.get(User, payment.token)
        assert user.plan == "starter"
        assert user.pro_pass_expires_at is None


async def test_promoting_site_does_not_turn_a_test_pass_into_live_access(payment, monkeypatch):
    await payment.deliver()
    monkeypatch.setattr(billing_service.settings, "stripe_live_mode", True)
    monkeypatch.setattr(deps, "verify_supabase_token", AsyncMock(return_value={"sub": str(payment.token)}))
    async with payment.sessions() as db:
        user = await deps.get_current_user(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="test"), db,
        )
        assert user.plan == "free"
        assert user.pro_pass_expires_at is None
        await db.commit()
