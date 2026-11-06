"""Public notification endpoints require provider authentication before lookup."""
import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from app.api.v1.endpoints import store_billing as endpoints
from app.db.session import get_db
from app.services.store_verification import PRODUCTS, VerifiedStorePurchase


@pytest.fixture
async def notifications(monkeypatch):
    app = FastAPI()
    app.include_router(endpoints.router, prefix="/store-billing")
    async def db():
        yield None
    app.dependency_overrides[get_db] = db
    monkeypatch.setattr(endpoints, "store_available", lambda _: True)
    monkeypatch.setattr(endpoints.settings, "google_play_notification_audience", "https://test.invalid/notify")
    monkeypatch.setattr(endpoints.settings, "google_play_notification_email", "push@test.invalid")
    monkeypatch.setattr(endpoints, "_verify_google_notification", lambda _: None)
    now = datetime.now(UTC)
    purchase = VerifiedStorePurchase("google", "production", "token-hash", uuid.uuid4(), PRODUCTS["google"]["monthly"],
                                     "monthly", "active", now, now+timedelta(days=30))
    verify = AsyncMock(return_value=purchase)
    save = AsyncMock()
    ack = AsyncMock()
    monkeypatch.setattr(endpoints, "verify_google", verify)
    monkeypatch.setattr(endpoints, "save_verified_purchase", save)
    monkeypatch.setattr(endpoints, "acknowledge_google", ack)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield SimpleNamespace(client=client, verify=verify, save=save, ack=ack, purchase=purchase)


def envelope(**overrides):
    data = {"packageName": "com.zephyr.analytics", "subscriptionNotification": {"purchaseToken": "private-evidence"}}
    data.update(overrides)
    return {"message": {"data": base64.b64encode(json.dumps(data).encode()).decode()}}


async def test_google_unsigned_notification_is_rejected_before_provider_or_database(notifications):
    response = await notifications.client.post("/store-billing/google/notifications", json=envelope())
    assert response.status_code == 401
    notifications.verify.assert_not_awaited()
    notifications.save.assert_not_awaited()


async def test_google_wrong_notification_identity_is_rejected(notifications, monkeypatch):
    def reject(_):
        raise ValueError("wrong identity")
    monkeypatch.setattr(endpoints, "_verify_google_notification", reject)
    response = await notifications.client.post("/store-billing/google/notifications", json=envelope(), headers={"Authorization": "Bearer forged"})
    assert response.status_code == 401
    notifications.verify.assert_not_awaited()


async def test_google_wrong_application_notification_is_rejected(notifications):
    response = await notifications.client.post("/store-billing/google/notifications", json=envelope(packageName="other.app"), headers={"Authorization": "Bearer oidc"})
    assert response.status_code == 400
    notifications.verify.assert_not_awaited()


async def test_google_valid_notification_refetches_authoritative_state_and_acknowledges(notifications):
    response = await notifications.client.post("/store-billing/google/notifications", json=envelope(), headers={"Authorization": "Bearer oidc"})
    assert response.status_code == 200
    notifications.verify.assert_awaited_once_with("private-evidence")
    notifications.ack.assert_awaited_once_with(notifications.purchase)
    notifications.save.assert_awaited_once_with(None, notifications.purchase)
    assert "private-evidence" not in response.text


async def test_google_test_notification_has_no_entitlement_side_effect(notifications):
    response = await notifications.client.post("/store-billing/google/notifications", json=envelope(testNotification={}), headers={"Authorization": "Bearer oidc"})
    assert response.status_code == 200
    notifications.verify.assert_not_awaited()
    notifications.save.assert_not_awaited()


@pytest.mark.parametrize("payload", [{}, {"signedPayload": 42}, {"signedPayload": "x"*100001}])
async def test_apple_malformed_notification_is_rejected(notifications, payload):
    response = await notifications.client.post("/store-billing/apple/notifications", json=payload)
    assert response.status_code == 400
    notifications.save.assert_not_awaited()


async def test_apple_forged_signature_is_rejected(notifications, monkeypatch):
    def reject(*_):
        raise HTTPException(400, "Invalid signature")
    monkeypatch.setattr(endpoints, "_decode_apple", reject)
    response = await notifications.client.post("/store-billing/apple/notifications", json={"signedPayload": "forged"})
    assert response.status_code == 400
    notifications.save.assert_not_awaited()


async def test_apple_test_notification_does_not_grant_access(notifications, monkeypatch):
    monkeypatch.setattr(endpoints, "_decode_apple", lambda *_: (SimpleNamespace(notificationType="TEST"), None, None))
    response = await notifications.client.post("/store-billing/apple/notifications", json={"signedPayload": "verified"})
    assert response.status_code == 200
    notifications.save.assert_not_awaited()


async def test_apple_notification_uses_current_transaction_state(notifications, monkeypatch):
    monkeypatch.setattr(endpoints, "_decode_apple", lambda *_: (SimpleNamespace(notificationType="REFUND", data=SimpleNamespace(signedTransactionInfo="verified-inner")), None, None))
    verify = AsyncMock(return_value=notifications.purchase)
    monkeypatch.setattr(endpoints, "verify_apple", verify)
    response = await notifications.client.post("/store-billing/apple/notifications", json={"signedPayload": "verified-outer"})
    assert response.status_code == 200
    verify.assert_awaited_once_with("verified-inner")
    notifications.save.assert_awaited_once_with(None, notifications.purchase)
