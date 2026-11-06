"""Store-authoritative verification. Client claims never grant paid access."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from app.core.config import settings


def _hide_play_purchase_request(record: logging.LogRecord) -> bool:
    # HTTPX normally logs full request URLs at INFO, and Google's purchase
    # verification URL contains the receipt token. Do not emit those records.
    return "androidpublisher.googleapis.com" not in record.getMessage()


logging.getLogger("httpx").addFilter(_hide_play_purchase_request)

PRODUCTS = {
    "apple": {"monthly": "com.zephyr.analytics.pro.monthly", "weekly": "com.zephyr.analytics.pro.seven_day"},
    "google": {"monthly": "vesquiri_pro_monthly", "weekly": "vesquiri_pro_seven_day"},
}
BASE_PLANS = {"monthly": "monthly", "weekly": "seven-days"}


@dataclass(frozen=True)
class VerifiedStorePurchase:
    store: str
    environment: str
    purchase_key: str
    owner_id: uuid.UUID
    product_id: str
    offer: str
    status: str
    starts_at: datetime | None
    expires_at: datetime | None
    auto_renew: bool = False
    token: str | None = field(default=None, repr=False)
    linked_key: str | None = None
    verified_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def store_available(store: str) -> bool:
    if store == "apple":
        return bool(settings.app_store_billing_enabled and settings.app_store_private_key
                    and settings.app_store_key_id and settings.app_store_issuer_id)
    return bool(store == "google" and settings.play_store_billing_enabled
                and settings.google_play_service_account_json and settings.store_token_encryption_key)


def offer_for(store: str, product: str) -> str:
    offer = next((offer for offer, sku in PRODUCTS.get(store, {}).items() if sku == product), None)
    if offer is None:
        raise HTTPException(400, "This product is not a Vesquiri purchase option")
    return offer


def _owner(value: Any) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(409, "This purchase is not linked to a Vesquiri account") from None


def _milliseconds(value: Any) -> datetime:
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise HTTPException(503, "Store confirmation is incomplete; please try restoring purchases later")
    return datetime.fromtimestamp(value / 1000, UTC)


def _iso(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(UTC)
    except (TypeError, ValueError):
        raise HTTPException(503, "Store confirmation is incomplete; please try restoring purchases later") from None


def _apple_verifier(environment):
    from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier

    roots = [p.read_bytes() for p in (Path(__file__).parents[1] / "certificates/apple").glob("*.cer")]
    if not roots:
        raise HTTPException(503, "Apple verification is not configured")
    return SignedDataVerifier(roots, True, environment, settings.store_bundle_id, settings.app_store_app_id)


def _decode_apple(signed: str, notification: bool = False):
    from appstoreserverlibrary.models.Environment import Environment
    from appstoreserverlibrary.signed_data_verifier import VerificationException, VerificationStatus

    for environment in (Environment.PRODUCTION, Environment.SANDBOX):
        verifier = _apple_verifier(environment)
        try:
            decoded = (verifier.verify_and_decode_notification(signed) if notification
                       else verifier.verify_and_decode_signed_transaction(signed))
            return decoded, environment, verifier
        except VerificationException as exc:
            if exc.status == VerificationStatus.RETRYABLE_VERIFICATION_FAILURE:
                raise HTTPException(503, "Apple verification is temporarily unavailable; restore purchases later") from None
            continue
    raise HTTPException(400, "Apple purchase signature could not be verified")


def _apple_purchase_sync(signed: str) -> VerifiedStorePurchase:
    from appstoreserverlibrary.api_client import AppStoreServerAPIClient
    from appstoreserverlibrary.models.Environment import Environment

    receipt, environment, verifier = _decode_apple(signed)
    # First verify the supplied JWS, then ask Apple for current transaction and
    # subscription state. Replaying an older valid JWS cannot undo a refund.
    client = AppStoreServerAPIClient(settings.app_store_private_key.encode(), settings.app_store_key_id,
                                    settings.app_store_issuer_id, settings.store_bundle_id, environment)
    current = client.get_transaction_info(str(receipt.transactionId))
    transaction = verifier.verify_and_decode_signed_transaction(current.signedTransactionInfo)
    offer = offer_for("apple", transaction.productId)
    if transaction.transactionId != receipt.transactionId or transaction.appAccountToken != receipt.appAccountToken:
        raise HTTPException(400, "Apple transaction does not match the purchase")
    owner = _owner(transaction.appAccountToken)
    original = str(transaction.originalTransactionId or transaction.transactionId)
    status, auto_renew, grace_expiry = "active", False, None
    if offer == "monthly":
        response = client.get_all_subscription_statuses(original)
        if response.bundleId != settings.store_bundle_id or response.environment != environment:
            raise HTTPException(400, "Apple subscription belongs to a different application")
        entries = [entry for group in response.data or [] for entry in group.lastTransactions or []
                   if str(entry.originalTransactionId) == original]
        if len(entries) != 1:
            raise HTTPException(503, "Apple subscription status is not yet available")
        entry = entries[0]
        transaction = verifier.verify_and_decode_signed_transaction(entry.signedTransactionInfo)
        renewal = verifier.verify_and_decode_renewal_info(entry.signedRenewalInfo)
        if (_owner(transaction.appAccountToken) != owner or str(transaction.originalTransactionId) != original
                or offer_for("apple", transaction.productId) != "monthly"
                or str(renewal.originalTransactionId) != original or renewal.productId != transaction.productId):
            raise HTTPException(400, "Apple subscription ownership does not match")
        state = int(entry.status)
        status = "active" if state in {1, 4} else "revoked" if state == 5 else "suspended" if state == 3 else "expired"
        auto_renew = int(renewal.autoRenewStatus or 0) == 1
        if state == 4 and renewal.gracePeriodExpiresDate:
            grace_expiry = _milliseconds(renewal.gracePeriodExpiresDate)
    expected_type = "Auto-Renewable Subscription" if offer == "monthly" else "Non-Renewing Subscription"
    if transaction.type != expected_type or transaction.quantity != 1 or transaction.inAppOwnershipType != "PURCHASED":
        raise HTTPException(400, "Apple purchase type or ownership is not supported")
    starts = _milliseconds(transaction.purchaseDate)
    expiry = (grace_expiry or _milliseconds(transaction.expiresDate)) if offer == "monthly" else starts + timedelta(days=7)
    now = datetime.now(UTC)
    if starts > now + timedelta(minutes=5):
        raise HTTPException(400, "Apple purchase time is invalid")
    if transaction.revocationDate is not None:
        status = "revoked"
    elif expiry <= now and status == "active":
        status = "expired"
    return VerifiedStorePurchase("apple", "sandbox" if environment == Environment.SANDBOX else "production",
        original if offer == "monthly" else str(transaction.transactionId), owner,
        transaction.productId, offer, status, starts, expiry, auto_renew)


async def verify_apple(signed: str) -> VerifiedStorePurchase:
    started = datetime.now(UTC)
    try:
        return replace(await asyncio.to_thread(_apple_purchase_sync, signed), verified_at=started)
    except HTTPException:
        raise
    except Exception:
        # Exception messages and request URLs can contain purchase evidence.
        raise HTTPException(503, "Apple verification is temporarily unavailable; restore purchases later") from None


def _google_access_token() -> str:
    from google.auth.transport.requests import Request
    from google.oauth2.service_account import Credentials

    credentials = Credentials.from_service_account_info(json.loads(settings.google_play_service_account_json),
        scopes=["https://www.googleapis.com/auth/androidpublisher"])
    credentials.refresh(Request())
    return credentials.token


async def google_request(method: str, route: str) -> dict:
    try:
        token = await asyncio.to_thread(_google_access_token)
        url = f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{quote(settings.store_bundle_id, safe='')}/{route}"
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.request(method, url, headers={"Authorization": f"Bearer {token}"},
                                            json={} if method == "POST" else None)
        if response.status_code == 404:
            raise HTTPException(400, "Google Play could not verify this purchase")
        if response.status_code >= 400:
            raise HTTPException(503, "Google Play verification is temporarily unavailable")
        return response.json() if response.content else {}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Google Play verification is temporarily unavailable; restore purchases later") from None


def google_purchase(data: dict, token: str) -> VerifiedStorePurchase:
    items = data.get("lineItems") or []
    if len(items) != 1:
        raise HTTPException(400, "This Google Play purchase is not supported")
    item = items[0]
    offer = offer_for("google", item.get("productId"))
    if (item.get("offerDetails") or {}).get("basePlanId") != BASE_PLANS[offer]:
        raise HTTPException(400, "The Google Play billing plan does not match")
    owner = _owner((data.get("externalAccountIdentifiers") or {}).get("obfuscatedExternalAccountId"))
    raw_state = data.get("subscriptionState")
    states = {"SUBSCRIPTION_STATE_ACTIVE": "active", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD": "active",
              "SUBSCRIPTION_STATE_CANCELED": "active", "SUBSCRIPTION_STATE_PENDING": "pending",
              "SUBSCRIPTION_STATE_PENDING_PURCHASE_CANCELED": "expired", "SUBSCRIPTION_STATE_EXPIRED": "expired",
              "SUBSCRIPTION_STATE_ON_HOLD": "suspended", "SUBSCRIPTION_STATE_PAUSED": "suspended"}
    if raw_state not in states:
        raise HTTPException(503, "Google Play is still confirming this purchase")
    status = states[raw_state]
    starts = _iso(data["startTime"]) if data.get("startTime") else None
    expiry = _iso(item["expiryTime"]) if item.get("expiryTime") else None
    if status == "active" and (starts is None or expiry is None):
        raise HTTPException(503, "Google Play is still confirming the purchase period")
    if starts and starts > datetime.now(UTC) + timedelta(minutes=5):
        raise HTTPException(400, "Google Play purchase time is invalid")
    if offer == "weekly" and "prepaidPlan" not in item or offer == "monthly" and "autoRenewingPlan" not in item:
        raise HTTPException(400, "The Google Play purchase duration does not match")
    if expiry and expiry <= datetime.now(UTC) and status == "active":
        status = "expired"
    linked = data.get("linkedPurchaseToken")
    return VerifiedStorePurchase("google", "sandbox" if data.get("testPurchase") is not None else "production",
        hashlib.sha256(token.encode()).hexdigest(), owner, item["productId"], offer, status, starts, expiry,
        bool((item.get("autoRenewingPlan") or {}).get("autoRenewEnabled")), token,
        hashlib.sha256(linked.encode()).hexdigest() if linked else None)


async def verify_google(token: str) -> VerifiedStorePurchase:
    started = datetime.now(UTC)
    data = await google_request("GET", f"purchases/subscriptionsv2/tokens/{quote(token, safe='')}")
    return replace(google_purchase(data, token), verified_at=started)


async def acknowledge_google(purchase: VerifiedStorePurchase) -> None:
    # Repeated acknowledgements are safe; check the current state first.
    route = f"purchases/subscriptionsv2/tokens/{quote(purchase.token or '', safe='')}"
    current = await google_request("GET", route)
    refreshed = google_purchase(current, purchase.token or "")
    if (refreshed.owner_id != purchase.owner_id or refreshed.product_id != purchase.product_id
            or refreshed.environment != purchase.environment or refreshed.status != "active"
            or refreshed.expires_at != purchase.expires_at):
        raise HTTPException(503, "Google Play purchase changed during confirmation; restore purchases later")
    if current.get("acknowledgementState") == "ACKNOWLEDGEMENT_STATE_PENDING":
        await google_request("POST", f"purchases/subscriptions/{quote(purchase.product_id, safe='')}/tokens/{quote(purchase.token or '', safe='')}:acknowledge")
