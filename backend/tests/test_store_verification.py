"""Purchase evidence, not client flags or old receipts, determines access."""
from __future__ import annotations

import copy
import logging
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from app.services import store_billing_service as ledger
from app.services import store_verification as verification

OWNER = uuid.uuid4()


def google_evidence(offer="monthly", state="ACTIVE"):
    now = datetime.now(UTC)
    item = {"productId": verification.PRODUCTS["google"][offer],
            "expiryTime": (now + timedelta(days=7)).isoformat(),
            "offerDetails": {"basePlanId": verification.BASE_PLANS[offer]}}
    item["prepaidPlan" if offer == "weekly" else "autoRenewingPlan"] = {} if offer == "weekly" else {"autoRenewEnabled": True}
    return {"subscriptionState": "SUBSCRIPTION_STATE_" + state,
            "startTime": (now - timedelta(hours=1)).isoformat(),
            "externalAccountIdentifiers": {"obfuscatedExternalAccountId": str(OWNER)},
            "lineItems": [item], "acknowledgementState": "ACKNOWLEDGEMENT_STATE_PENDING"}


@pytest.mark.parametrize("offer", ["monthly", "weekly"])
def test_google_verified_duration_and_account_binding(offer):
    evidence = google_evidence(offer)
    result = verification.google_purchase(evidence, "private-receipt-token")
    assert result.owner_id == OWNER
    assert result.offer == offer and result.status == "active"
    assert result.environment == "production"
    assert result.auto_renew is (offer == "monthly")
    assert "private-receipt-token" not in result.purchase_key
    assert result.expires_at == datetime.fromisoformat(evidence["lineItems"][0]["expiryTime"])


@pytest.mark.parametrize("state,expected", [("CANCELED", "active"), ("IN_GRACE_PERIOD", "active"),
    ("ON_HOLD", "suspended"), ("PAUSED", "suspended"), ("EXPIRED", "expired"),
    ("PENDING", "pending"), ("PENDING_PURCHASE_CANCELED", "expired")])
def test_google_payment_and_renewal_states(state, expected):
    assert verification.google_purchase(google_evidence(state=state), "token").status == expected


def test_google_cancelled_subscription_does_not_extend_original_expiry():
    data = google_evidence(state="CANCELED")
    data["lineItems"][0]["expiryTime"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    assert verification.google_purchase(data, "token").status == "expired"


async def test_http_client_logs_and_purchase_repr_never_expose_google_receipt(monkeypatch, caplog):
    async def respond(request):
        return httpx.Response(200, json=google_evidence())
    original = httpx.AsyncClient
    monkeypatch.setattr(verification.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    monkeypatch.setattr(verification, "_google_access_token", lambda: "fake-access-token")
    with caplog.at_level(logging.INFO, logger="httpx"):
        purchase = await verification.verify_google("private-receipt-token")
    assert "private-receipt-token" not in caplog.text
    assert "private-receipt-token" not in repr(purchase)


def test_empty_test_purchase_object_is_sandbox():
    data = google_evidence()
    data["testPurchase"] = {}
    assert verification.google_purchase(data, "token").environment == "sandbox"


@pytest.mark.parametrize("mutation,code", [
    (lambda d: d.update(lineItems=[]), 400),
    (lambda d: d["lineItems"].append(copy.deepcopy(d["lineItems"][0])), 400),
    (lambda d: d["lineItems"][0].update(productId="another_apps_product"), 400),
    (lambda d: d["lineItems"][0]["offerDetails"].update(basePlanId="yearly"), 400),
    (lambda d: d.update(externalAccountIdentifiers={}), 409),
    (lambda d: d.update(startTime="2026-01-01T00:00:00"), 503),
    (lambda d: d["lineItems"][0].pop("expiryTime"), 503),
    (lambda d: d["lineItems"][0].pop("autoRenewingPlan"), 400),
    (lambda d: d.update(subscriptionState="NEW_UNKNOWN_STATE"), 503),
    (lambda d: d.update(startTime=(datetime.now(UTC) + timedelta(days=1)).isoformat()), 400),
])
def test_google_incomplete_or_wrong_evidence_cannot_grant_access(mutation, code):
    data = google_evidence()
    mutation(data)
    with pytest.raises(HTTPException) as exc:
        verification.google_purchase(data, "token")
    assert exc.value.status_code == code


async def test_google_only_acknowledges_matching_active_purchase(monkeypatch):
    data = google_evidence()
    purchase = verification.google_purchase(data, "sensitive/token")
    request = AsyncMock(side_effect=[copy.deepcopy(data), {}])
    monkeypatch.setattr(verification, "google_request", request)
    await verification.acknowledge_google(purchase)
    assert request.await_args_list[1].args == ("POST", "purchases/subscriptions/vesquiri_pro_monthly/tokens/sensitive%2Ftoken:acknowledge")
    data["subscriptionState"] = "SUBSCRIPTION_STATE_EXPIRED"
    request.reset_mock(side_effect=True)
    request.side_effect = [data]
    with pytest.raises(HTTPException):
        await verification.acknowledge_google(purchase)
    assert request.await_count == 1


@pytest.fixture
def apple(monkeypatch):
    import appstoreserverlibrary.api_client as client_module
    from appstoreserverlibrary.models.Environment import Environment

    now = datetime.now(UTC)
    transaction = NS(transactionId="2000001", originalTransactionId="2000000", appAccountToken=str(OWNER),
        productId=verification.PRODUCTS["apple"]["weekly"], type="Non-Renewing Subscription", quantity=1,
        inAppOwnershipType="PURCHASED", purchaseDate=int((now-timedelta(hours=1)).timestamp()*1000),
        expiresDate=int((now+timedelta(days=30)).timestamp()*1000), revocationDate=None)
    receipt = copy.deepcopy(transaction)
    renewal = NS(originalTransactionId="2000000", productId=verification.PRODUCTS["apple"]["monthly"],
        autoRenewStatus=1, gracePeriodExpiresDate=None)
    entry = NS(originalTransactionId="2000000", signedTransactionInfo="latest", signedRenewalInfo="renewal", status=1)
    response = NS(bundleId=verification.settings.store_bundle_id, environment=Environment.PRODUCTION,
        data=[NS(lastTransactions=[entry])])
    verifier = NS(verify_and_decode_signed_transaction=lambda _: transaction,
                  verify_and_decode_renewal_info=lambda _: renewal)
    calls = []
    def client(*args):
        calls.append(args)
        return NS(get_transaction_info=lambda _: NS(signedTransactionInfo="current"),
                  get_all_subscription_statuses=lambda _: response)
    monkeypatch.setattr(verification, "_decode_apple", lambda _: (receipt, Environment.PRODUCTION, verifier))
    monkeypatch.setattr(client_module, "AppStoreServerAPIClient", client)
    return NS(receipt=receipt, transaction=transaction, renewal=renewal, entry=entry, response=response, calls=calls)


def monthly(apple):
    apple.transaction.productId = verification.PRODUCTS["apple"]["monthly"]
    apple.transaction.type = "Auto-Renewable Subscription"


def test_apple_nonrenewing_pass_is_exactly_seven_days(apple):
    result = verification._apple_purchase_sync("signed")
    assert result.expires_at - result.starts_at == timedelta(days=7)
    assert result.purchase_key == "2000001" and not result.auto_renew
    assert len(apple.calls) == 1  # A current server lookup is required even for a valid old JWS.


def test_replaying_valid_apple_receipt_after_refund_cannot_restore_access(apple):
    apple.transaction.revocationDate = int(datetime.now(UTC).timestamp()*1000)
    assert apple.receipt.revocationDate is None
    assert verification._apple_purchase_sync("previously-valid-JWS").status == "revoked"


@pytest.mark.parametrize("status,expected", [(1, "active"), (2, "expired"), (3, "suspended"), (4, "active"), (5, "revoked")])
def test_apple_monthly_server_state_and_grace(apple, status, expected):
    monthly(apple)
    apple.entry.status = status
    grace = int((datetime.now(UTC)+timedelta(days=2)).timestamp()*1000)
    if status == 4:
        apple.transaction.expiresDate = int((datetime.now(UTC)-timedelta(days=1)).timestamp()*1000)
        apple.renewal.gracePeriodExpiresDate = grace
    result = verification._apple_purchase_sync("signed")
    assert result.status == expected and result.purchase_key == "2000000"
    if status == 4:
        assert result.expires_at == datetime.fromtimestamp(grace/1000, UTC)


@pytest.mark.parametrize("field,value", [("appAccountToken", str(uuid.uuid4())), ("transactionId", "different"),
    ("inAppOwnershipType", "FAMILY_SHARED"), ("quantity", 2), ("type", "Consumable")])
def test_apple_wrong_account_transaction_or_type_is_rejected(apple, field, value):
    setattr(apple.transaction, field, value)
    with pytest.raises(HTTPException):
        verification._apple_purchase_sync("signed")


def test_apple_wrong_app_subscription_is_rejected(apple):
    monthly(apple)
    apple.response.bundleId = "another.app"
    with pytest.raises(HTTPException):
        verification._apple_purchase_sync("signed")


def test_apple_billing_retry_remains_suspended_after_access_expiry(apple):
    monthly(apple)
    apple.entry.status = 3
    apple.transaction.expiresDate = int((datetime.now(UTC)-timedelta(days=1)).timestamp()*1000)
    result = verification._apple_purchase_sync("signed")
    assert result.status == "suspended" and result.auto_renew


def test_real_apple_signature_verifier_rejects_unsigned_token():
    with pytest.raises(HTTPException) as exc:
        verification._decode_apple("eyJhbGciOiJub25lIn0.eyJwcm9kdWN0SWQiOiJwcm8ifQ.")
    assert exc.value.status_code == 400


async def test_wrong_account_receipt_never_reaches_ledger_or_ack(monkeypatch):
    purchase = verification.google_purchase(google_evidence(), "token")
    monkeypatch.setattr(ledger, "store_available", lambda _: True)
    monkeypatch.setattr(ledger, "verify_google", AsyncMock(return_value=purchase))
    save = AsyncMock()
    ack = AsyncMock()
    monkeypatch.setattr(ledger, "save_verified_purchase", save)
    monkeypatch.setattr(ledger, "acknowledge_google", ack)
    with pytest.raises(HTTPException) as exc:
        await ledger.confirm_purchase(None, NS(id=uuid.uuid4()), "google", purchase.product_id, "token")
    assert exc.value.status_code == 409
    save.assert_not_awaited()
    ack.assert_not_awaited()


async def test_sandbox_purchase_cannot_activate_public_account(monkeypatch):
    data = google_evidence()
    data["testPurchase"] = {}
    purchase = verification.google_purchase(data, "token")
    monkeypatch.setattr(ledger, "store_available", lambda _: True)
    monkeypatch.setattr(ledger.settings, "store_sandbox_user_ids", [])
    monkeypatch.setattr(ledger, "verify_google", AsyncMock(return_value=purchase))
    save = AsyncMock()
    ack = AsyncMock()
    monkeypatch.setattr(ledger, "save_verified_purchase", save)
    monkeypatch.setattr(ledger, "acknowledge_google", ack)
    assert await ledger.confirm_purchase(None, NS(id=OWNER), "google", purchase.product_id, "token") == {"status": "test_account_restricted"}
    save.assert_not_awaited()
    ack.assert_not_awaited()
