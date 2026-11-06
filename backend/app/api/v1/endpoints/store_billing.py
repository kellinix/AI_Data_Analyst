"""Native billing endpoints; the authenticated account owns each purchase."""
from __future__ import annotations

import asyncio
import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.core.config import settings
from app.models.store_purchase import StorePurchase
from app.models.subscription import Subscription
from app.services.store_billing_service import (
    confirm_purchase,
    pending_store_purchase,
    sandbox_allowed,
    save_verified_purchase,
)
from app.services.store_verification import (
    BASE_PLANS,
    PRODUCTS,
    _decode_apple,
    acknowledge_google,
    store_available,
    verify_apple,
    verify_google,
)

router = APIRouter()


class PurchaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    store: Literal["apple", "google"]
    product_id: str = Field(alias="productId", min_length=1, max_length=128)
    purchase_token: str = Field(alias="purchaseToken", min_length=1, max_length=32000)


class PrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    store: Literal["apple", "google"]
    offer: Literal["monthly", "weekly"]


class CancelRequest(BaseModel):
    intent: uuid.UUID


@router.get("/status")
async def store_status(current_user: CurrentUser, db: DB):
    rows = (await db.execute(select(StorePurchase).where(StorePurchase.user_id == current_user.id))).scalars().all()
    now = datetime.now(UTC)
    return {"available": {store: store_available(store) for store in PRODUCTS}, "products": PRODUCTS,
        "basePlans": BASE_PLANS, "pending": await pending_store_purchase(db, current_user),
        "purchases": [{"store": r.store, "offer": r.offer, "status": r.status,
                       "expiresAt": r.expires_at, "autoRenew": r.auto_renew,
                       "active": bool(r.status == "active" and r.expires_at and r.expires_at > now
                                      and (r.environment == "production" or sandbox_allowed(current_user.id)))} for r in rows]}


@router.post("/prepare")
async def prepare_purchase(body: PrepareRequest, current_user: CurrentUser, db: DB):
    if not store_available(body.store):
        raise HTTPException(503, "Purchases are not available yet")
    await db.refresh(current_user, with_for_update=True)
    if current_user.plan != "free":
        raise HTTPException(409, "Your account already has paid access")
    if await pending_store_purchase(db, current_user):
        raise HTTPException(409, "Another purchase is awaiting confirmation. Restore purchases before trying again.")
    billing = (await db.execute(select(Subscription).where(Subscription.user_id == current_user.id))).scalar_one_or_none()
    now = datetime.now(UTC)
    if billing and billing.pending_checkout_session_id and (not billing.checkout_expires_at or billing.checkout_expires_at > now):
        raise HTTPException(409, "Another purchase is awaiting confirmation. Please finish or cancel it first.")
    intent = str(uuid.uuid4())
    current_user.store_purchase_intent = intent
    current_user.store_purchase_pending_until = now + timedelta(minutes=15)
    await db.flush()
    return {"intent": intent, "accountToken": str(current_user.id), "productId": PRODUCTS[body.store][body.offer],
            "basePlanId": BASE_PLANS[body.offer]}


@router.post("/cancel-intent")
async def cancel_purchase_intent(body: CancelRequest, current_user: CurrentUser, db: DB):
    await db.refresh(current_user, with_for_update=True)
    if current_user.store_purchase_intent == str(body.intent):
        current_user.store_purchase_intent = None
        current_user.store_purchase_pending_until = None
        await db.flush()
    return {"ok": True}


@router.post("/confirm")
async def confirm_native_purchase(body: PurchaseRequest, current_user: CurrentUser, db: DB):
    return await confirm_purchase(db, current_user, body.store, body.product_id, body.purchase_token)


@router.post("/apple/notifications")
async def apple_notifications(request: Request, db: DB):
    if not store_available("apple"):
        raise HTTPException(503, "Apple billing is not configured")
    raw = await request.body()
    if len(raw) > 128000:
        raise HTTPException(413, "Notification is too large")
    try:
        signed = json.loads(raw)["signedPayload"]
        if not isinstance(signed, str) or len(signed) > 100000:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise HTTPException(400, "Invalid Apple notification") from None
    try:
        notification, _, _ = await asyncio.to_thread(_decode_apple, signed, True)
        if notification.notificationType == "TEST":
            return {"ok": True}
        transaction = notification.data.signedTransactionInfo if notification.data else None
        if not transaction:
            return {"ok": True}
        purchase = await verify_apple(transaction)
        await save_verified_purchase(db, purchase)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Apple notification verification is temporarily unavailable") from None


def _verify_google_notification(bearer: str):
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2.id_token import verify_oauth2_token

    claims = verify_oauth2_token(bearer, GoogleRequest(), audience=settings.google_play_notification_audience)
    if claims.get("email") != settings.google_play_notification_email or claims.get("email_verified") is not True:
        raise ValueError("Unexpected Pub/Sub identity")


@router.post("/google/notifications")
async def google_notifications(request: Request, db: DB):
    if not (store_available("google") and settings.google_play_notification_audience and settings.google_play_notification_email):
        raise HTTPException(503, "Google Play notifications are not configured")
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Signed notification authorization is required")
    try:
        await asyncio.to_thread(_verify_google_notification, authorization[7:])
    except Exception:
        raise HTTPException(401, "Notification identity could not be verified") from None
    raw = await request.body()
    if len(raw) > 128000:
        raise HTTPException(413, "Notification is too large")
    try:
        envelope = json.loads(raw)
        data = json.loads(base64.b64decode(envelope["message"]["data"], validate=True))
        if data.get("packageName") != settings.store_bundle_id:
            raise ValueError
        if "testNotification" in data:
            return {"ok": True}
        update = data.get("subscriptionNotification") or data.get("voidedPurchaseNotification") or {}
        token = update["purchaseToken"]
        if not isinstance(token, str) or not 1 <= len(token) <= 16000:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise HTTPException(400, "Invalid Google Play notification") from None
    purchase = await verify_google(token)
    if purchase.status == "active" and (purchase.environment == "production" or sandbox_allowed(purchase.owner_id)):
        await acknowledge_google(purchase)
    await save_verified_purchase(db, purchase)
    return {"ok": True}
