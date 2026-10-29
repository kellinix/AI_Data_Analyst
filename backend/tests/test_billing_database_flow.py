"""Optional local PostgreSQL test of the full persisted billing lifecycle.

Set BILLING_TEST_DATABASE_URL only for a disposable database migrated to head.
No Stripe network calls or charges are made.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_db
from app.api.v1.endpoints import billing
from app.models.subscription import Subscription
from app.models.user import User
from app.services import billing_service


@pytest.mark.skipif(
    not os.getenv("BILLING_TEST_DATABASE_URL"), reason="Needs disposable PostgreSQL"
)
async def test_checkout_webhook_and_cancellation_persist(monkeypatch):
    engine = create_async_engine(os.environ["BILLING_TEST_DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    owner = User(supabase_id=str(uuid.uuid4()), email=f"billing-{uuid.uuid4()}@example.test")
    monkeypatch.setattr(billing.settings, "stripe_billing_enabled", True)
    monkeypatch.setattr(billing.settings, "stripe_secret_key", "sk_test_only")
    monkeypatch.setattr(billing.settings, "stripe_webhook_secret", "whsec_test_only")
    monkeypatch.setattr(billing.settings, "stripe_pro_price_id", "price_pro_19")
    monkeypatch.setattr(billing.settings, "frontend_url", "https://zephyr.example")
    remote_status = {"value": "active"}

    async def stripe(method, path, **kwargs):
        if path == "/prices/price_pro_19":
            return {
                "active": True,
                "currency": "gbp",
                "unit_amount": 1900,
                "recurring": {"interval": "month", "interval_count": 1},
            }
        if path == "/customers":
            return {"id": "cus_local_test"}
        if path.startswith("/subscriptions?"):
            return {"data": []}
        if path == "/checkout/sessions":
            return {
                "id": "cs_local_test",
                "expires_at": int(time.time()) + 3600,
                "url": "https://checkout.stripe.com/c/pay/localtest",
            }
        if path == "/subscriptions/sub_local_test":
            return {
                "id": "sub_local_test",
                "customer": "cus_local_test",
                "status": remote_status["value"],
                "metadata": {"zephyr_user_id": str(owner.id)},
                "items": {
                    "data": [
                        {
                            "price": {"id": "price_pro_19"},
                            "current_period_start": 1700000000,
                            "current_period_end": 1702592000,
                        }
                    ]
                },
                "cancel_at_period_end": False,
            }
        raise AssertionError(f"Unexpected mock Stripe request: {path}")

    monkeypatch.setattr(billing, "stripe_request", stripe)
    monkeypatch.setattr(billing_service, "stripe_request", stripe)
    try:
        async with sessions() as db:
            db.add(owner)
            await db.commit()
            await db.refresh(owner)
            result = await billing.checkout(owner, db)
            assert result["url"].startswith("https://checkout.stripe.com/")
            await db.commit()

        async with sessions() as db:
            before = (await db.execute(select(User).where(User.id == owner.id))).scalar_one()
            record = (
                await db.execute(select(Subscription).where(Subscription.user_id == owner.id))
            ).scalar_one()
            assert before.plan == "free"
            assert record.pending_checkout_session_id == "cs_local_test"

        app = FastAPI()
        app.include_router(billing.router, prefix="/billing")

        async def local_db():
            async with sessions() as db:
                yield db
                await db.commit()

        app.dependency_overrides[get_db] = local_db

        async def deliver(kind):
            payload = json.dumps(
                {
                    "type": kind,
                    "data": {"object": {"id": "sub_local_test"}},
                }
            ).encode()
            timestamp = int(time.time())
            signature = hmac.new(
                b"whsec_test_only", f"{timestamp}.".encode() + payload, hashlib.sha256
            ).hexdigest()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    "/billing/webhook",
                    content=payload,
                    headers={"stripe-signature": f"t={timestamp},v1={signature}"},
                )

        assert (await deliver("customer.subscription.created")).status_code == 200
        assert (await deliver("customer.subscription.created")).status_code == 200
        async with sessions() as db:
            paid = (await db.execute(select(User).where(User.id == owner.id))).scalar_one()
            record = (
                await db.execute(select(Subscription).where(Subscription.user_id == owner.id))
            ).scalar_one()
            assert paid.plan == "starter"
            assert record.pending_checkout_session_id is None
            assert record.stripe_subscription_id == "sub_local_test"

        remote_status["value"] = "past_due"
        assert (await deliver("customer.subscription.updated")).status_code == 200
        async with sessions() as db:
            unpaid = (await db.execute(select(User).where(User.id == owner.id))).scalar_one()
            assert unpaid.plan == "free"

        remote_status["value"] = "canceled"
        assert (await deliver("customer.subscription.deleted")).status_code == 200
        async with sessions() as db:
            record = (
                await db.execute(select(Subscription).where(Subscription.user_id == owner.id))
            ).scalar_one()
            assert record.status == "canceled"
    finally:
        await engine.dispose()
