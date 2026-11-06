"""Store entitlement ledger, ownership binding and cross-provider access."""
from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.store_purchase import StorePurchase
from app.models.subscription import Subscription
from app.models.user import User
from app.services.pro_pass_service import has_current_pro_pass, monthly_pro_is_active
from app.services.store_verification import (
    VerifiedStorePurchase,
    acknowledge_google,
    offer_for,
    store_available,
    verify_apple,
    verify_google,
)


def owner_hash(owner_id: uuid.UUID) -> str:
    return hashlib.sha256(str(owner_id).encode()).hexdigest()


def sandbox_allowed(owner_id: uuid.UUID) -> bool:
    return str(owner_id) in settings.store_sandbox_user_ids


def token_cipher() -> Fernet:
    try:
        return Fernet(settings.store_token_encryption_key.encode())
    except (ValueError, TypeError):
        raise HTTPException(503, "Store verification is not configured") from None


async def refresh_store_access(db: AsyncSession, user: User) -> None:
    if not (settings.app_store_billing_enabled or settings.play_store_billing_enabled
            or getattr(user, "store_access_expires_at", None)):
        return
    now = datetime.now(UTC)
    environments = ["production", "sandbox"] if sandbox_allowed(user.id) else ["production"]
    statement = select(StorePurchase).where(
        StorePurchase.user_id == user.id, StorePurchase.environment.in_(environments),
        StorePurchase.status == "active", StorePurchase.expires_at > now).execution_options(populate_existing=True)
    result = await db.execute(statement)
    purchases = list(result.scalars().all())
    previous = getattr(user, "store_access_expires_at", None)
    if not purchases and previous is None:
        return
    # Reload under the same account lock used by Stripe and purchase delivery.
    await db.refresh(user, with_for_update=True)
    # A delivery may have changed or revoked the receipt while this request
    # waited for the account lock. Re-read before changing its plan.
    purchases = (await db.execute(statement)).scalars().all()
    expiry = max((p.expires_at for p in purchases), default=None)
    user.store_access_expires_at = expiry
    if user.plan in {"free", "starter"}:
        record = (await db.execute(select(Subscription).where(Subscription.user_id == user.id))).scalar_one_or_none()
        user.plan = "starter" if expiry or has_current_pro_pass(user) or monthly_pro_is_active(record) else "free"
    await db.flush()


async def pending_store_purchase(db: AsyncSession, user: User) -> bool:
    now = datetime.now(UTC)
    if getattr(user, "store_purchase_pending_until", None) and user.store_purchase_pending_until > now:
        return True
    environments = ["production", "sandbox"] if sandbox_allowed(user.id) else ["production"]
    return (await db.execute(select(StorePurchase.id).where(
        StorePurchase.user_id == user.id, StorePurchase.environment.in_(environments),
        or_(StorePurchase.status == "pending", and_(StorePurchase.offer == "monthly",
            StorePurchase.auto_renew.is_(True), StorePurchase.status.in_(["active", "suspended"]))))
        .limit(1))).first() is not None


async def save_verified_purchase(db: AsyncSession, purchase: VerifiedStorePurchase) -> bool:
    """Serialize on the account; a purchase is permanently bound to one owner."""
    result = await db.execute(select(User).where(User.id == purchase.owner_id).with_for_update()
                              .execution_options(populate_existing=True))
    user = result.scalar_one_or_none()
    result = await db.execute(select(StorePurchase).where(
        StorePurchase.store == purchase.store, StorePurchase.environment == purchase.environment,
        StorePurchase.purchase_key == purchase.purchase_key).with_for_update().execution_options(populate_existing=True))
    record = result.scalar_one_or_none()
    if record and record.owner_hash != owner_hash(purchase.owner_id):
        raise HTTPException(409, "This purchase belongs to another Vesquiri account")
    if record and record.checked_at > purchase.verified_at:
        # A slow callback started verification before a later refund/renewal
        # check. It must not overwrite that more recently verified state.
        return record.status == "active"
    if user is None:
        # Deleting an account leaves a minimal ownership tombstone; later
        # renewals must never recreate the account or transfer the purchase.
        if record:
            record.status = purchase.status
            record.expires_at = purchase.expires_at
            record.checked_at = purchase.verified_at
            await db.flush()
        return False
    if purchase.environment == "sandbox" and not sandbox_allowed(user.id):
        raise HTTPException(403, "Test purchases are restricted to configured testing accounts")
    already_granted = bool(record and record.status == "active")
    if record is None:
        record = StorePurchase(user_id=user.id, owner_hash=owner_hash(user.id), store=purchase.store,
            environment=purchase.environment, purchase_key=purchase.purchase_key)
        db.add(record)
    record.product_id, record.offer, record.status = purchase.product_id, purchase.offer, purchase.status
    record.starts_at, record.expires_at = purchase.starts_at, purchase.expires_at
    record.auto_renew, record.checked_at = purchase.auto_renew, purchase.verified_at
    if purchase.token:
        record.encrypted_token = token_cipher().encrypt(purchase.token.encode()).decode()
    if purchase.linked_key:
        linked = (await db.execute(select(StorePurchase).where(
            StorePurchase.store == purchase.store, StorePurchase.environment == purchase.environment,
            StorePurchase.purchase_key == purchase.linked_key).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if linked:
            if linked.owner_hash != owner_hash(user.id):
                raise HTTPException(409, "The previous purchase belongs to another Vesquiri account")
            linked.status = "replaced"
    user.store_purchase_pending_until = None
    user.store_purchase_intent = None
    await db.flush()
    await refresh_store_access(db, user)
    return already_granted


async def confirm_purchase(db: AsyncSession, user: User, store: str, product: str, token: str) -> dict:
    if not store_available(store):
        raise HTTPException(503, "Purchases are not available yet")
    offer_for(store, product)
    purchase = await (verify_apple(token) if store == "apple" else verify_google(token))
    if purchase.owner_id != user.id:
        raise HTTPException(409, "This purchase belongs to another Vesquiri account")
    if purchase.product_id != product:
        raise HTTPException(400, "Store product does not match the requested purchase")
    if purchase.environment == "sandbox" and not sandbox_allowed(user.id):
        return {"status": "test_account_restricted"}
    if store == "google" and purchase.status == "active":
        await acknowledge_google(purchase)
    already = await save_verified_purchase(db, purchase)
    recorded = (await db.execute(select(StorePurchase).where(
        StorePurchase.store == store, StorePurchase.environment == purchase.environment,
        StorePurchase.purchase_key == purchase.purchase_key))).scalar_one_or_none()
    status = recorded.status if recorded else "invalid"
    if status == "pending":
        return {"status": "store_pending"}
    if status != "active" or not recorded or not recorded.expires_at or recorded.expires_at <= datetime.now(UTC):
        return {"status": "invalid", "reason": "The store reports that this purchase no longer grants access"}
    return {"status": "entitled", "alreadyGranted": already}


async def reconcile_saved_purchase(db: AsyncSession, record: StorePurchase) -> None:
    if record.store == "google":
        try:
            token = token_cipher().decrypt((record.encrypted_token or "").encode()).decode()
        except (InvalidToken, ValueError):
            raise HTTPException(503, "Stored purchase verification is temporarily unavailable") from None
        purchase = await verify_google(token)
    else:
        import asyncio

        from appstoreserverlibrary.api_client import AppStoreServerAPIClient
        from appstoreserverlibrary.models.Environment import Environment

        environment = Environment.SANDBOX if record.environment == "sandbox" else Environment.PRODUCTION
        client = AppStoreServerAPIClient(settings.app_store_private_key.encode(), settings.app_store_key_id,
            settings.app_store_issuer_id, settings.store_bundle_id, environment)
        info = await asyncio.to_thread(client.get_transaction_info, record.purchase_key)
        purchase = await verify_apple(info.signedTransactionInfo)
    if purchase.environment != record.environment or owner_hash(purchase.owner_id) != record.owner_hash:
        raise HTTPException(409, "Store purchase ownership changed unexpectedly")
    if record.store == "google" and purchase.status == "active":
        await acknowledge_google(purchase)
    await save_verified_purchase(db, purchase)


async def reconcile_due_purchases(db: AsyncSession, *, limit: int = 100) -> int:
    from datetime import timedelta

    now = datetime.now(UTC)
    records = (await db.execute(select(StorePurchase).where(
        StorePurchase.user_id.is_not(None), StorePurchase.checked_at < now - timedelta(minutes=10),
        or_(StorePurchase.status.in_(["active", "pending", "suspended"]),
            and_(StorePurchase.offer == "monthly", StorePurchase.expires_at > now - timedelta(days=30))))
        .order_by(StorePurchase.checked_at).limit(limit))).scalars().all()
    count = 0
    for record in records:
        if not store_available(record.store):
            continue
        try:
            async with db.begin_nested():
                await reconcile_saved_purchase(db, record)
            count += 1
        except Exception:
            # Keep last verified state until its original deadline. A provider
            # outage never extends access or logs a purchase token.
            continue
    return count
