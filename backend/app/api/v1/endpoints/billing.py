"""Authenticated billing actions and Stripe's signed webhook."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.core.config import settings
from app.models.subscription import Subscription
from app.models.user import User
from app.services.billing_service import (
    billing_available,
    process_billing_event,
    require_stripe_url,
    stripe_request,
    verify_webhook,
)

router = APIRouter()


@router.get("/availability")
async def availability() -> dict[str, bool]:
    return {"enabled": billing_available()}


@router.post("/checkout")
async def checkout(current_user: CurrentUser, db: DB) -> dict[str, str]:
    if not billing_available():
        raise HTTPException(503, "Pro subscriptions are not open yet.")

    # Lock the account while deciding whether a new Checkout Session is allowed.
    await db.execute(select(User).where(User.id == current_user.id).with_for_update())
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == current_user.id).with_for_update()
    )
    record = result.scalar_one_or_none()
    if record and record.stripe_subscription_id and record.status not in ("canceled", "cancelled"):
        raise HTTPException(409, "You already have a subscription. Open billing to manage it.")

    if record and record.pending_checkout_session_id and record.checkout_expires_at:
        if record.checkout_expires_at > datetime.now(UTC):
            pending = await stripe_request(
                "GET", f"/checkout/sessions/{record.pending_checkout_session_id}"
            )
            if pending.get("status") == "open":
                return {"url": require_stripe_url(pending.get("url"), "checkout.stripe.com")}
        record.pending_checkout_session_id = None
        record.checkout_expires_at = None

    price = await stripe_request("GET", f"/prices/{settings.stripe_pro_price_id}")
    recurring = price.get("recurring") or {}
    if (
        not price.get("active")
        or price.get("currency") != "gbp"
        or price.get("unit_amount") != 1900
        or recurring.get("interval") != "month"
        or recurring.get("interval_count", 1) != 1
    ):
        raise HTTPException(503, "The Pro price is not configured as £19 per month.")

    customer_id = record.stripe_customer_id if record else None
    if not customer_id:
        customer = await stripe_request(
            "POST",
            "/customers",
            data={
                "email": current_user.email,
                "metadata[zephyr_user_id]": str(current_user.id),
            },
            idempotency_key=f"zephyr-customer-{current_user.id}",
        )
        customer_id = customer.get("id")
        if not isinstance(customer_id, str) or not customer_id.startswith("cus_"):
            raise HTTPException(503, "Billing could not create a customer. Please try again.")
        if record is None:
            record = Subscription(user_id=current_user.id, plan="free", status="incomplete")
            db.add(record)
        record.stripe_customer_id = customer_id
        await db.flush()

    existing = await stripe_request(
        "GET", f"/subscriptions?customer={customer_id}&status=all&limit=100"
    )
    if existing.get("has_more"):
        raise HTTPException(409, "Please contact support to review your billing account.")
    if any(
        item.get("status") in {"active", "trialing", "past_due", "unpaid", "paused", "incomplete"}
        for item in existing.get("data", [])
    ):
        raise HTTPException(409, "You already have a subscription. Open billing to manage it.")

    session = await stripe_request(
        "POST",
        "/checkout/sessions",
        data={
            "mode": "subscription",
            "customer": customer_id,
            "client_reference_id": str(current_user.id),
            "line_items[0][price]": settings.stripe_pro_price_id,
            "line_items[0][quantity]": "1",
            "payment_method_types[0]": "card",
            "subscription_data[metadata][zephyr_user_id]": str(current_user.id),
            "success_url": f"{settings.frontend_url.rstrip('/')}/settings?billing=returned",
            "cancel_url": f"{settings.frontend_url.rstrip('/')}/pricing?billing=cancelled",
        },
        idempotency_key=f"zephyr-checkout-{current_user.id}-{uuid.uuid4()}",
    )
    url = require_stripe_url(session.get("url"), "checkout.stripe.com")
    session_id = session.get("id")
    expires_at = session.get("expires_at")
    if not isinstance(session_id, str) or not isinstance(expires_at, int):
        raise HTTPException(503, "Billing did not return a valid payment session.")
    record.pending_checkout_session_id = session_id
    record.checkout_expires_at = datetime.fromtimestamp(expires_at, UTC)
    await db.flush()
    return {"url": url}


@router.post("/portal")
async def portal(current_user: CurrentUser, db: DB) -> dict[str, str]:
    if not settings.stripe_secret_key:
        raise HTTPException(503, "Billing is temporarily unavailable.")
    result = await db.execute(select(Subscription).where(Subscription.user_id == current_user.id))
    record = result.scalar_one_or_none()
    if not record or not record.stripe_customer_id:
        raise HTTPException(404, "You do not have a billing account yet.")
    session = await stripe_request(
        "POST",
        "/billing_portal/sessions",
        data={
            "customer": record.stripe_customer_id,
            "return_url": f"{settings.frontend_url.rstrip('/')}/settings",
        },
    )
    return {"url": require_stripe_url(session.get("url"), "billing.stripe.com")}


@router.post("/webhook")
async def webhook(request: Request, db: DB) -> dict[str, bool]:
    event = verify_webhook(await request.body(), request.headers.get("stripe-signature", ""))
    await process_billing_event(db, event)
    return {"received": True}
