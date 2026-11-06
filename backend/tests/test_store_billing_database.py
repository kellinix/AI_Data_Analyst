"""Real transaction/locking tests against an explicitly selected disposable DB."""
from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import store_billing as endpoints
from app.models.store_purchase import StorePurchase
from app.models.subscription import Subscription
from app.models.user import User
from app.services import store_billing_service as service
from app.services.store_verification import PRODUCTS, VerifiedStorePurchase

pytestmark = pytest.mark.skipif(not os.getenv("BILLING_TEST_DATABASE_URL"), reason="Needs disposable PostgreSQL")


@pytest.fixture
async def account(monkeypatch):
    engine = create_async_engine(os.environ["BILLING_TEST_DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    owner = uuid.uuid4()
    monkeypatch.setattr(service.settings, "app_store_billing_enabled", True)
    monkeypatch.setattr(service.settings, "store_token_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(service.settings, "store_sandbox_user_ids", [])
    monkeypatch.setattr(service.settings, "stripe_live_mode", False)
    async with sessions() as db:
        db.add(User(id=owner, supabase_id=str(owner), email=f"store-{owner}@example.test",
                    analyses_this_month=5, ai_queries_this_month=9))
        await db.commit()
    now = datetime.now(UTC)
    evidence = VerifiedStorePurchase("apple", "production", uuid.uuid4().hex, owner,
        PRODUCTS["apple"]["weekly"], "weekly", "active", now, now+timedelta(days=7))
    try:
        yield sessions, owner, evidence
    finally:
        async with sessions() as db:
            await db.execute(delete(User).where(User.id == owner))
            await db.execute(delete(StorePurchase).where(StorePurchase.owner_hash == service.owner_hash(owner)))
            await db.commit()
        await engine.dispose()


async def deliver(sessions, evidence):
    async with sessions() as db:
        await service.save_verified_purchase(db, evidence)
        await db.commit()


async def test_concurrent_duplicate_receipts_do_not_extend_access_or_reset_usage(account):
    sessions, owner, evidence = account
    await asyncio.gather(deliver(sessions, evidence), deliver(sessions, evidence))
    async with sessions() as db:
        rows = (await db.execute(select(StorePurchase).where(StorePurchase.user_id == owner))).scalars().all()
        assert len(rows) == 1 and rows[0].expires_at == evidence.expires_at
        user = await db.get(User, owner)
        assert user.plan == "starter" and user.store_access_expires_at == evidence.expires_at
        assert (user.analyses_this_month, user.ai_queries_this_month) == (5, 9)


async def test_confirmation_contract_grants_once_and_restore_is_idempotent(account, monkeypatch):
    sessions, owner, evidence = account
    monkeypatch.setattr(service, "store_available", lambda _: True)
    monkeypatch.setattr(service, "verify_apple", AsyncMock(return_value=evidence))
    for already in (False, True):
        async with sessions() as db:
            user = await db.get(User, owner)
            result = await service.confirm_purchase(db, user, "apple", evidence.product_id, "signed-JWS")
            assert result == {"status": "entitled", "alreadyGranted": already}
            await db.commit()


async def test_pending_payment_is_saved_without_ack_or_access_then_settles(account, monkeypatch):
    sessions, owner, evidence = account
    pending = replace(evidence, store="google", product_id=PRODUCTS["google"]["weekly"],
                      status="pending", starts_at=None, expires_at=None, token="private-token")
    verify = AsyncMock(return_value=pending)
    ack = AsyncMock()
    monkeypatch.setattr(service, "store_available", lambda _: True)
    monkeypatch.setattr(service, "verify_google", verify)
    monkeypatch.setattr(service, "acknowledge_google", ack)
    async with sessions() as db:
        user = await db.get(User, owner)
        assert await service.confirm_purchase(db, user, "google", pending.product_id, pending.token) == {"status": "store_pending"}
        assert user.plan == "free" and await service.pending_store_purchase(db, user)
        ack.assert_not_awaited()
        await db.commit()
    verify.return_value = replace(pending, status="active", starts_at=evidence.starts_at, expires_at=evidence.expires_at,
                                  verified_at=datetime.now(UTC))
    async with sessions() as db:
        user = await db.get(User, owner)
        assert await service.confirm_purchase(db, user, "google", pending.product_id, pending.token) == {"status": "entitled", "alreadyGranted": False}
        assert user.plan == "starter" and not await service.pending_store_purchase(db, user)
        ack.assert_awaited_once()
        await db.commit()


async def test_refund_and_expiry_revoke_access(account):
    sessions, owner, evidence = account
    await deliver(sessions, evidence)
    await deliver(sessions, replace(evidence, status="revoked"))
    async with sessions() as db:
        user = await db.get(User, owner)
        assert user.plan == "free" and user.store_access_expires_at is None
    await deliver(sessions, replace(evidence, expires_at=datetime.now(UTC)-timedelta(seconds=1)))
    async with sessions() as db:
        user = await db.get(User, owner)
        assert user.plan == "free" and user.store_access_expires_at is None


@pytest.mark.parametrize("other_source", ["stripe", "pass", "another_store"])
async def test_revoking_one_source_preserves_other_paid_access(account, other_source):
    sessions, owner, evidence = account
    await deliver(sessions, evidence)
    async with sessions() as db:
        user = await db.get(User, owner)
        if other_source == "stripe":
            db.add(Subscription(user_id=owner, stripe_subscription_id="sub_fake", plan="starter", status="active",
                                current_period_end=(datetime.now(UTC)+timedelta(days=30)).isoformat()))
        elif other_source == "pass":
            user.pro_pass_expires_at = datetime.now(UTC)+timedelta(days=1)
            user.billing_livemode = False
        else:
            await service.save_verified_purchase(db, replace(evidence, purchase_key=uuid.uuid4().hex))
        await db.commit()
    await deliver(sessions, replace(evidence, status="revoked"))
    async with sessions() as db:
        assert (await db.get(User, owner)).plan == "starter"


async def test_deleted_account_keeps_ownership_tombstone_and_cannot_be_recreated(account):
    sessions, owner, evidence = account
    await deliver(sessions, evidence)
    async with sessions() as db:
        await db.execute(delete(User).where(User.id == owner))
        await db.commit()
    await deliver(sessions, replace(evidence, status="revoked"))
    async with sessions() as db:
        assert await db.get(User, owner) is None
        row = await db.scalar(select(StorePurchase).where(StorePurchase.purchase_key == evidence.purchase_key))
        assert row.user_id is None and row.owner_hash == service.owner_hash(owner) and row.status == "revoked"


async def test_purchase_cannot_be_transferred_to_another_account(account):
    sessions, owner, evidence = account
    await deliver(sessions, evidence)
    with pytest.raises(HTTPException) as exc:
        await deliver(sessions, replace(evidence, owner_id=uuid.uuid4()))
    assert exc.value.status_code == 409


async def test_slow_older_confirmation_cannot_undo_newer_refund(account):
    sessions, owner, evidence = account
    await deliver(sessions, evidence)
    await deliver(sessions, replace(evidence, status="revoked", verified_at=evidence.verified_at+timedelta(seconds=1)))
    await deliver(sessions, evidence)
    async with sessions() as db:
        assert (await db.get(User, owner)).plan == "free"
        row = await db.scalar(select(StorePurchase).where(StorePurchase.purchase_key == evidence.purchase_key))
        assert row.status == "revoked"


async def test_google_tokens_are_encrypted_and_replacement_ends_previous_entitlement(account):
    sessions, owner, evidence = account
    first = replace(evidence, store="google", product_id=PRODUCTS["google"]["monthly"], offer="monthly", token="private-token")
    await deliver(sessions, first)
    second = replace(first, purchase_key=uuid.uuid4().hex, linked_key=first.purchase_key, token="replacement-token")
    await deliver(sessions, second)
    async with sessions() as db:
        rows = (await db.execute(select(StorePurchase).where(StorePurchase.user_id == owner))).scalars().all()
        assert len(rows) == 2
        old = next(row for row in rows if row.purchase_key == first.purchase_key)
        assert old.status == "replaced" and old.encrypted_token != "private-token"
        assert service.token_cipher().decrypt(old.encrypted_token.encode()) == b"private-token"


async def test_prepare_serializes_purchases_and_stale_cancel_cannot_clear_new_intent(account, monkeypatch):
    sessions, owner, _ = account
    monkeypatch.setattr(endpoints, "store_available", lambda _: True)
    async def prepare():
        async with sessions() as db:
            user = await db.get(User, owner)
            result = await endpoints.prepare_purchase(endpoints.PrepareRequest(store="apple", offer="weekly"), user, db)
            await db.commit()
            return result
    results = await asyncio.gather(prepare(), prepare(), return_exceptions=True)
    success = [r for r in results if isinstance(r, dict)]
    failures = [r for r in results if isinstance(r, HTTPException)]
    assert len(success) == len(failures) == 1 and failures[0].status_code == 409
    assert success[0]["accountToken"] == str(owner)
    async with sessions() as db:
        user = await db.get(User, owner)
        await endpoints.cancel_purchase_intent(endpoints.CancelRequest(intent=uuid.uuid4()), user, db)
        assert user.store_purchase_intent == success[0]["intent"]
        await endpoints.cancel_purchase_intent(endpoints.CancelRequest(intent=success[0]["intent"]), user, db)
        assert user.store_purchase_intent is None


async def test_native_prepare_blocks_existing_stripe_checkout(account, monkeypatch):
    sessions, owner, _ = account
    monkeypatch.setattr(endpoints, "store_available", lambda _: True)
    async with sessions() as db:
        db.add(Subscription(user_id=owner, plan="free", status="canceled", pending_checkout_session_id="cs_fake",
                            checkout_expires_at=datetime.now(UTC)+timedelta(minutes=15)))
        await db.commit()
        user = await db.get(User, owner)
        with pytest.raises(HTTPException) as exc:
            await endpoints.prepare_purchase(endpoints.PrepareRequest(store="google", offer="monthly"), user, db)
        assert exc.value.status_code == 409


async def test_billing_retry_blocks_another_purchase_until_original_subscription_is_managed(account, monkeypatch):
    sessions, owner, evidence = account
    monkeypatch.setattr(endpoints, "store_available", lambda _: True)
    await deliver(sessions, replace(evidence, product_id=PRODUCTS["apple"]["monthly"], offer="monthly",
                                   status="suspended", auto_renew=True))
    async with sessions() as db:
        user = await db.get(User, owner)
        assert user.plan == "free"
        with pytest.raises(HTTPException) as exc:
            await endpoints.prepare_purchase(endpoints.PrepareRequest(store="google", offer="weekly"), user, db)
        assert exc.value.status_code == 409


async def test_test_receipts_cannot_grant_public_pro_even_if_delivered_by_notification(account):
    sessions, owner, evidence = account
    with pytest.raises(HTTPException) as exc:
        await deliver(sessions, replace(evidence, environment="sandbox"))
    assert exc.value.status_code == 403
    async with sessions() as db:
        assert (await db.get(User, owner)).plan == "free"
