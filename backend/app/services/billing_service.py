"""Small Stripe REST client and verified subscription reconciliation.

Only Stripe webhooks change a user's paid access. Checkout redirects are never
treated as proof of payment.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.subscription import Subscription
from app.models.user import User
from app.services.pro_pass_service import (
    billing_mode_matches,
    fulfill_weekly_pass,
    has_current_pro_pass,
    reconcile_pass_payment_event,
)

logger = get_logger(__name__)
STRIPE_API = "https://api.stripe.com/v1"
PAID_STATUSES = {"active", "trialing"}


def billing_available(offer: str = "monthly") -> bool:
    return bool(
        settings.stripe_billing_enabled
        and stripe_key_matches_mode()
        and settings.stripe_webhook_secret
        and (settings.stripe_weekly_price_id if offer == "weekly" else settings.stripe_pro_price_id)
    )


def stripe_key_matches_mode() -> bool:
    prefixes = ("sk_live_", "rk_live_") if settings.stripe_live_mode else ("sk_test_", "rk_test_")
    return settings.stripe_secret_key.startswith(prefixes)


async def stripe_request(
    method: str,
    path: str,
    *,
    data: dict[str, str] | None = None,
    idempotency_key: str | None = None,
) -> dict:
    headers = {"Authorization": f"Bearer {settings.stripe_secret_key}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.request(
                method, f"{STRIPE_API}{path}", data=data, headers=headers
            )
    except httpx.RequestError as exc:
        logger.warning("Stripe request unavailable", error_type=type(exc).__name__)
        raise HTTPException(503, "Billing is temporarily unavailable. Please try again.") from None
    if response.status_code >= 400:
        logger.warning("Stripe request failed", status=response.status_code, path=path)
        raise HTTPException(503, "Billing is temporarily unavailable. Please try again.")
    try:
        result = response.json()
    except ValueError:
        raise HTTPException(503, "Billing is temporarily unavailable. Please try again.") from None
    if not isinstance(result, dict):
        raise HTTPException(503, "Billing is temporarily unavailable. Please try again.")
    return result


def require_stripe_url(url: object, host: str) -> str:
    if not isinstance(url, str):
        raise HTTPException(503, "Billing did not return a payment link. Please try again.")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != host:
        raise HTTPException(503, "Billing did not return a valid payment link.")
    return url


def verify_webhook(payload: bytes, signature: str) -> dict:
    """Validate Stripe's signed raw body and five-minute replay window."""
    if len(payload) > 1024 * 1024:
        raise HTTPException(413, "Billing event is too large")
    if not settings.stripe_webhook_secret:
        raise HTTPException(503, "Billing webhooks are not configured")
    parts: dict[str, list[str]] = {}
    for field in signature.split(","):
        key, _, value = field.strip().partition("=")
        parts.setdefault(key, []).append(value)
    try:
        timestamp = int(parts["t"][0])
        candidates = parts["v1"]
    except (KeyError, ValueError, IndexError):
        raise HTTPException(400, "Invalid billing signature") from None
    if abs(time.time() - timestamp) > 300:
        raise HTTPException(400, "Expired billing signature")
    signed = str(timestamp).encode() + b"." + payload
    expected = hmac.new(settings.stripe_webhook_secret.encode(), signed, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in candidates):
        raise HTTPException(400, "Invalid billing signature")
    try:
        event = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(400, "Invalid billing event") from None
    if not isinstance(event, dict) or not isinstance(event.get("type"), str):
        raise HTTPException(400, "Invalid billing event")
    return event


def _period(value: object) -> str | None:
    if isinstance(value, int) and value > 0:
        return datetime.fromtimestamp(value, UTC).isoformat()
    return None


async def reconcile_subscription(
    db: AsyncSession, stripe_subscription: dict, *, checkout_user_id: str | None = None
) -> None:
    """Idempotently mirror Stripe's current state; ignore unrelated subscriptions."""
    if stripe_subscription.get("livemode", settings.stripe_live_mode) is not settings.stripe_live_mode:
        return
    sub_id = stripe_subscription.get("id")
    customer_id = stripe_subscription.get("customer")
    if not isinstance(sub_id, str) or not isinstance(customer_id, str):
        return

    existing_result = await db.execute(
        select(Subscription).where(Subscription.stripe_customer_id == customer_id)
    )
    record = existing_result.scalar_one_or_none()
    metadata = stripe_subscription.get("metadata") or {}
    claimed_user_id = metadata.get("zephyr_user_id") or checkout_user_id
    if record:
        if not billing_mode_matches(record):
            return
        if claimed_user_id and claimed_user_id != str(record.user_id):
            logger.warning("Stripe subscription owner mismatch", subscription_id=sub_id)
            return
        if record.stripe_subscription_id not in (None, sub_id) and record.status not in (
            "canceled",
            "cancelled",
        ):
            logger.warning("Different Stripe subscription already linked", customer_id=customer_id)
            return
        user_result = await db.execute(select(User).where(User.id == record.user_id).with_for_update())
        user = user_result.scalar_one_or_none()
    else:
        try:
            owner_id = uuid.UUID(claimed_user_id)
        except (TypeError, ValueError):
            return
        user_result = await db.execute(select(User).where(User.id == owner_id).with_for_update())
        user = user_result.scalar_one_or_none()
        if user is None:
            return
        existing_result = await db.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        )
        record = existing_result.scalar_one_or_none()
        if record and record.stripe_customer_id not in (None, customer_id):
            logger.warning("Stripe customer does not match account", subscription_id=sub_id)
            return
        if record and not billing_mode_matches(record):
            return
        if record is None:
            record = Subscription(user_id=user.id, plan="free", status="incomplete", stripe_livemode=settings.stripe_live_mode)
            db.add(record)
    if user is None:
        return

    items = (stripe_subscription.get("items") or {}).get("data") or []
    first_item = items[0] if items else {}
    price = first_item.get("price") or {}
    price_id = price.get("id") if isinstance(price, dict) else price
    status = stripe_subscription.get("status") or "incomplete"
    entitled = status in PAID_STATUSES and price_id == settings.stripe_pro_price_id

    record.stripe_customer_id = customer_id
    record.stripe_subscription_id = sub_id
    if getattr(record, "pending_checkout_offer", None) != "weekly":
        record.pending_checkout_session_id = None
        record.pending_checkout_offer = None
        record.checkout_expires_at = None
    record.plan = "starter" if entitled else "free"
    record.status = str(status)
    record.current_period_start = _period(
        stripe_subscription.get("current_period_start") or first_item.get("current_period_start")
    )
    record.current_period_end = _period(
        stripe_subscription.get("current_period_end") or first_item.get("current_period_end")
    )
    record.cancel_at_period_end = bool(stripe_subscription.get("cancel_at_period_end"))
    user.plan = "starter" if entitled or has_current_pro_pass(user) else "free"
    user.billing_livemode = settings.stripe_live_mode if user.plan == "starter" else None
    await db.flush()


async def process_billing_event(db: AsyncSession, event: dict) -> None:
    if event.get("livemode", settings.stripe_live_mode) is not settings.stripe_live_mode:
        return
    kind = event["type"]
    obj = (event.get("data") or {}).get("object") or {}
    if not isinstance(obj, dict):
        return
    if kind in {"checkout.session.completed", "checkout.session.async_payment_succeeded"} and obj.get("mode") == "payment":
        session_id = obj.get("id")
        if isinstance(session_id, str) and (obj.get("metadata") or {}).get("vesquiri_offer") == "weekly":
            await fulfill_weekly_pass(db, session_id)
        return
    if kind in {"charge.refunded", "charge.dispute.created"}:
        await reconcile_pass_payment_event(db, obj, dispute=kind == "charge.dispute.created")
        return
    sub_id: str | None = None
    checkout_user_id = None
    if kind.startswith("customer.subscription."):
        sub_id = obj.get("id")
    elif kind == "checkout.session.completed" and obj.get("mode") == "subscription":
        sub_id = obj.get("subscription")
        checkout_user_id = obj.get("client_reference_id")
    elif kind in {"invoice.paid", "invoice.payment_failed"}:
        parent = obj.get("parent") or {}
        details = parent.get("subscription_details") or {}
        sub_id = details.get("subscription") or obj.get("subscription")
    if not isinstance(sub_id, str):
        return
    # Stripe may deliver events out of order. The latest remote state wins.
    try:
        current = await stripe_request("GET", f"/subscriptions/{sub_id}")
    except HTTPException:
        if kind != "customer.subscription.deleted":
            raise
        current = obj
    await reconcile_subscription(db, current, checkout_user_id=checkout_user_id)
