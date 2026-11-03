"""Fulfill a verified one-time payment once and enforce its seven-day expiry."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.pro_pass import ProPass
from app.models.subscription import Subscription
from app.models.user import User


def has_current_pro_pass(user: User, now: datetime | None = None) -> bool:
    expiry = getattr(user, "pro_pass_expires_at", None)
    mode = getattr(user, "billing_livemode", settings.stripe_live_mode)
    return mode is settings.stripe_live_mode and expiry is not None and expiry > (now or datetime.now(UTC))


def billing_mode_matches(record: Subscription) -> bool:
    return getattr(record, "stripe_livemode", False) is settings.stripe_live_mode


def monthly_pro_is_active(record: Subscription | None) -> bool:
    return bool(record and billing_mode_matches(record) and record.plan == "starter" and record.status in {"active", "trialing"})


async def refresh_expired_pro_pass(db: AsyncSession, user: User) -> None:
    mode = getattr(user, "billing_livemode", None)
    if mode is True and not settings.stripe_live_mode:
        # Never overwrite live entitlements while using a sandbox key.
        raise HTTPException(503, "This account requires the live billing service")
    expiry = getattr(user, "pro_pass_expires_at", None)
    if not (mode is False and settings.stripe_live_mode) and (expiry is None or has_current_pro_pass(user)):
        return
    # A newly purchased pass may have committed since authentication loaded
    # this row. Lock and reload before clearing the old deadline or sandbox mode.
    await db.refresh(user, with_for_update=True)
    mode = getattr(user, "billing_livemode", None)
    if mode is True and not settings.stripe_live_mode:
        raise HTTPException(503, "This account requires the live billing service")
    if mode is False and settings.stripe_live_mode:
        if user.plan == "starter":
            user.plan = "free"
        user.pro_pass_expires_at = None
        user.billing_livemode = None
        await db.flush()
        return
    expiry = getattr(user, "pro_pass_expires_at", None)
    if expiry is None or has_current_pro_pass(user):
        return
    # Enforce the deadline on every authenticated request, including quota checks.
    # A scheduler or a visit to the payment return page is not required.
    result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    record = result.scalar_one_or_none()
    user.pro_pass_expires_at = None
    if user.plan in {"free", "starter"}:
        user.plan = "starter" if monthly_pro_is_active(record) else "free"
        user.billing_livemode = settings.stripe_live_mode if user.plan == "starter" else None
    await db.flush()


async def fulfill_weekly_pass(db: AsyncSession, session_id: str) -> None:
    from app.services.billing_service import stripe_request

    if not settings.stripe_weekly_price_id or not session_id.startswith("cs_"):
        return
    session = await stripe_request(
        "GET", f"/checkout/sessions/{quote(session_id, safe='')}"
        "?expand[]=line_items&expand[]=payment_intent.latest_charge",
    )
    metadata = session.get("metadata") or {}
    if session.get("livemode", settings.stripe_live_mode) is not settings.stripe_live_mode:
        return
    if session.get("mode") != "payment" or metadata.get("vesquiri_offer") != "weekly":
        return
    if session.get("status") != "complete" or session.get("payment_status") != "paid":
        return
    items = (session.get("line_items") or {}).get("data") or []
    if (
        len(items) != 1
        or (session.get("line_items") or {}).get("has_more")
        or (items[0].get("price") or {}).get("id") != settings.stripe_weekly_price_id
        or items[0].get("quantity") != 1
        or session.get("currency") != "gbp"
        or session.get("amount_total") != 599
        or session.get("amount_subtotal") != 599
    ):
        return
    try:
        owner_id = uuid.UUID(metadata.get("zephyr_user_id"))
    except (ValueError, TypeError, AttributeError):
        return
    if session.get("client_reference_id") != str(owner_id):
        return

    intent = session.get("payment_intent")
    charge = intent.get("latest_charge") if isinstance(intent, dict) else None
    if not isinstance(charge, dict):
        raise HTTPException(503, "Payment confirmation is temporarily unavailable")
    if (
        intent.get("status") != "succeeded"
        or intent.get("amount_received") != 599
        or intent.get("currency") != "gbp"
        or intent.get("customer") != session.get("customer")
        or not charge.get("paid")
        or not charge.get("captured")
        or charge.get("amount_captured") != 599
        or charge.get("payment_intent") != intent.get("id")
        or not isinstance(charge.get("created"), int)
        or charge["created"] <= 0
    ):
        return

    # Serialize all fulfillments for this account, including duplicate deliveries.
    result = await db.execute(select(User).where(User.id == owner_id).with_for_update())
    user = result.scalar_one_or_none()
    if user is None:
        return
    result = await db.execute(select(Subscription).where(Subscription.user_id == owner_id))
    billing = result.scalar_one_or_none()
    if billing is None or not billing_mode_matches(billing) or billing.stripe_customer_id != session.get("customer"):
        return
    result = await db.execute(
        select(ProPass).where(ProPass.stripe_checkout_session_id == session_id)
    )
    paid_pass = result.scalar_one_or_none()
    if paid_pass is not None and (
        paid_pass.user_id != owner_id or paid_pass.stripe_payment_intent_id != intent.get("id")
    ):
        return
    now = datetime.now(UTC)
    if paid_pass is None:
        paid_at = datetime.fromtimestamp(charge["created"], UTC)
        paid_pass = ProPass(
            user_id=owner_id,
            stripe_checkout_session_id=session_id,
            stripe_payment_intent_id=intent["id"],
            starts_at=paid_at,
            expires_at=paid_at + timedelta(days=7),
        )
        db.add(paid_pass)
    # Refetching current payment state prevents a delayed success event from
    # restoring a fully refunded or disputed pass. Revocation is never undone
    # by a duplicate delivery; replays also never move the original deadline.
    if charge.get("refunded") or charge.get("disputed"):
        paid_pass.revoked_at = paid_pass.revoked_at or now
    await db.flush()
    result = await db.execute(
        select(ProPass).where(
            ProPass.user_id == owner_id,
            ProPass.revoked_at.is_(None),
            ProPass.starts_at <= now,
            ProPass.expires_at > now,
        ).order_by(ProPass.expires_at.desc()).limit(1)
    )
    active_pass = result.scalar_one_or_none()
    user.pro_pass_expires_at = active_pass.expires_at if active_pass else None
    if user.plan in {"free", "starter"}:
        user.plan = "starter" if active_pass or monthly_pro_is_active(billing) else "free"
        user.billing_livemode = settings.stripe_live_mode if user.plan == "starter" else None
    if billing.pending_checkout_session_id == session_id:
        billing.pending_checkout_session_id = None
        billing.pending_checkout_offer = None
        billing.checkout_expires_at = None
    await db.flush()


async def reconcile_pass_payment_event(db: AsyncSession, obj: dict, *, dispute: bool) -> None:
    from app.services.billing_service import stripe_request

    intent_id = obj.get("payment_intent")
    if dispute and not isinstance(intent_id, str):
        charge_id = obj.get("charge")
        if not isinstance(charge_id, str):
            return
        charge = await stripe_request("GET", f"/charges/{quote(charge_id, safe='')}")
        intent_id = charge.get("payment_intent")
    if not isinstance(intent_id, str) or not intent_id.startswith("pi_"):
        return
    # Lookup in Stripe also handles a refund/dispute arriving before the first
    # successful Checkout event. No local payment history is assumed to exist.
    sessions = await stripe_request(
        "GET", f"/checkout/sessions?payment_intent={quote(intent_id, safe='')}&limit=100"
    )
    if sessions.get("has_more"):
        raise HTTPException(503, "Payment confirmation is temporarily unavailable")
    for session in sessions.get("data", []):
        if (session.get("metadata") or {}).get("vesquiri_offer") == "weekly":
            await fulfill_weekly_pass(db, session["id"])
