"""Authenticated billing actions and Stripe's signed webhook."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.core.config import settings
from app.models.subscription import Subscription
from app.models.user import User
from app.services.billing_service import (
    billing_available,
    process_billing_event,
    require_stripe_url,
    stripe_key_matches_mode,
    stripe_request,
    verify_webhook,
)
from app.services.pro_pass_service import billing_mode_matches, has_current_pro_pass

router = APIRouter()


class CheckoutRequest(BaseModel):
    offer: Literal["monthly", "weekly"] = "monthly"


@router.get("/availability")
async def availability() -> dict[str, bool]:
    return {"enabled": billing_available(), "weekly_enabled": billing_available("weekly")}


@router.post("/checkout")
async def checkout(
    current_user: CurrentUser, db: DB, body: CheckoutRequest | None = None
) -> dict[str, str]:
    offer = body.offer if body else "monthly"
    if not billing_available(offer):
        raise HTTPException(503, "This Pro option is not available yet.")

    # Lock the account while deciding whether a new Checkout Session is allowed.
    locked = await db.execute(
        select(User).where(User.id == current_user.id).with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked.scalar_one_or_none() is None:
        raise HTTPException(401, "Account is no longer available")
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == current_user.id).with_for_update()
    )
    record = result.scalar_one_or_none()
    if record and not billing_mode_matches(record):
        if record.stripe_livemode:
            raise HTTPException(409, "Use live billing to manage this account.")
        # This site previously ran in sandbox. Test customer IDs cannot be
        # used with a live key; live records are never discarded for testing.
        record.stripe_customer_id = None
        record.stripe_subscription_id = None
        record.pending_checkout_session_id = None
        record.pending_checkout_offer = None
        record.checkout_expires_at = None
        record.stripe_livemode = settings.stripe_live_mode
        record.status = "incomplete"
        record.plan = "free"
    if current_user.plan in {"professional", "enterprise"}:
        raise HTTPException(409, "Your current plan already includes Pro access.")
    if has_current_pro_pass(current_user):
        raise HTTPException(409, "Your seven-day Pro pass is still active. Buy again after it expires.")
    if record and record.stripe_subscription_id and record.status not in ("canceled", "cancelled"):
        raise HTTPException(409, "You already have a subscription. Open billing to manage it.")

    if record and record.pending_checkout_session_id:
        pending = await stripe_request(
            "GET", f"/checkout/sessions/{record.pending_checkout_session_id}"
        )
        if pending.get("status") == "complete":
            raise HTTPException(409, "Your payment is being confirmed. Refresh Settings shortly.")
        if pending.get("status") == "open":
            pending_offer = (pending.get("metadata") or {}).get("vesquiri_offer") or getattr(
                record, "pending_checkout_offer", None
            ) or "monthly"
            if pending_offer == offer:
                return {"url": require_stripe_url(pending.get("url"), "checkout.stripe.com")}
            # Switching offers must not reuse a link with the wrong amount or
            # leave a second payable session open for the same account.
            await stripe_request("POST", f"/checkout/sessions/{record.pending_checkout_session_id}/expire")
        record.pending_checkout_session_id = None
        record.pending_checkout_offer = None
        record.checkout_expires_at = None

    price_id = settings.stripe_weekly_price_id if offer == "weekly" else settings.stripe_pro_price_id
    amount = 599 if offer == "weekly" else 1900
    price = await stripe_request("GET", f"/prices/{price_id}")
    recurring = price.get("recurring") or {}
    if (
        not price.get("active")
        or price.get("currency") != "gbp"
        or price.get("unit_amount") != amount
        or (offer == "weekly" and (price.get("type") != "one_time" or recurring))
        or (offer == "monthly" and (
            recurring.get("interval") != "month" or recurring.get("interval_count", 1) != 1
        ))
    ):
        expected = "£5.99 one time" if offer == "weekly" else "£19 per month"
        raise HTTPException(503, f"The Pro price is not configured as {expected}.")

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
            record = Subscription(user_id=current_user.id, plan="free", status="incomplete", stripe_livemode=settings.stripe_live_mode)
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

    session_data = {
            "mode": "payment" if offer == "weekly" else "subscription",
            "customer": customer_id,
            "client_reference_id": str(current_user.id),
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": "1",
            "payment_method_types[0]": "card",
            "branding_settings[display_name]": settings.app_name,
            "consent_collection[terms_of_service]": "required",
            "custom_text[terms_of_service_acceptance][message]": (
                f"I agree to the [{settings.app_name} Terms of Use]"
                f"({settings.frontend_url.rstrip('/')}/terms) and have read the "
                f"[Privacy Policy]({settings.frontend_url.rstrip('/')}/privacy)."
            ),
            "metadata[zephyr_user_id]": str(current_user.id),
            "metadata[vesquiri_offer]": offer,
            "success_url": f"{settings.frontend_url.rstrip('/')}/settings?billing=returned",
            "cancel_url": f"{settings.frontend_url.rstrip('/')}/pricing?billing=cancelled",
    }
    if offer == "weekly":
        session_data.update({
            "invoice_creation[enabled]": "true",
            "payment_intent_data[metadata][zephyr_user_id]": str(current_user.id),
            "custom_text[submit][message]": (
                "One payment of £5.99 for seven days of Pro access. Does not renew. "
                "Existing monthly usage counts are not reset."
            ),
        })
    else:
        session_data["subscription_data[metadata][zephyr_user_id]"] = str(current_user.id)
    session = await stripe_request(
        "POST",
        "/checkout/sessions",
        data=session_data,
        idempotency_key=f"zephyr-checkout-{current_user.id}-{uuid.uuid4()}",
    )
    url = require_stripe_url(session.get("url"), "checkout.stripe.com")
    session_id = session.get("id")
    expires_at = session.get("expires_at")
    if not isinstance(session_id, str) or not isinstance(expires_at, int):
        raise HTTPException(503, "Billing did not return a valid payment session.")
    record.pending_checkout_session_id = session_id
    record.pending_checkout_offer = offer
    record.checkout_expires_at = datetime.fromtimestamp(expires_at, UTC)
    await db.flush()
    return {"url": url}


@router.post("/portal")
async def portal(current_user: CurrentUser, db: DB) -> dict[str, str]:
    if not stripe_key_matches_mode():
        raise HTTPException(503, "Billing is temporarily unavailable.")
    result = await db.execute(select(Subscription).where(Subscription.user_id == current_user.id))
    record = result.scalar_one_or_none()
    if not record or not billing_mode_matches(record) or not record.stripe_customer_id:
        raise HTTPException(404, "You do not have a billing account yet.")
    portal_data = {
        "customer": record.stripe_customer_id,
        "return_url": f"{settings.frontend_url.rstrip('/')}/settings",
    }
    if settings.stripe_portal_configuration_id:
        portal_data["configuration"] = settings.stripe_portal_configuration_id
    session = await stripe_request(
        "POST",
        "/billing_portal/sessions",
        data=portal_data,
    )
    return {"url": require_stripe_url(session.get("url"), "billing.stripe.com")}


@router.post("/webhook")
async def webhook(request: Request, db: DB) -> dict[str, bool]:
    event = verify_webhook(await request.body(), request.headers.get("stripe-signature", ""))
    await process_billing_event(db, event)
    return {"received": True}
