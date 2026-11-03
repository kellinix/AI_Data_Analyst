"""Billing contract: no paid access until a signed, matching Stripe state arrives."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from app.api.deps import get_db
from app.api.v1.endpoints import billing
from app.services import billing_service


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(billing.settings, "app_name", "Vesquiri")
    monkeypatch.setattr(billing.settings, "stripe_billing_enabled", True)
    monkeypatch.setattr(billing.settings, "stripe_secret_key", "sk_test_only")
    monkeypatch.setattr(billing.settings, "stripe_webhook_secret", "whsec_test_only")
    monkeypatch.setattr(billing.settings, "stripe_pro_price_id", "price_pro_19")
    monkeypatch.setattr(billing.settings, "stripe_portal_configuration_id", "")
    monkeypatch.setattr(billing.settings, "frontend_url", "https://zephyr.example")


@pytest.fixture
def owner():
    return SimpleNamespace(id=uuid.uuid4(), email="test@example.com", plan="free")


def _price(amount=1900):
    return {
        "active": True,
        "currency": "gbp",
        "unit_amount": amount,
        "recurring": {"interval": "month", "interval_count": 1},
    }


def _stripe_subscription(owner, *, status="active", price="price_pro_19", customer="cus_test"):
    return {
        "id": "sub_test",
        "customer": customer,
        "status": status,
        "metadata": {"zephyr_user_id": str(owner.id)},
        "items": {
            "data": [
                {
                    "price": {"id": price},
                    "current_period_start": 1700000000,
                    "current_period_end": 1702592000,
                }
            ]
        },
        "cancel_at_period_end": False,
    }


def _db_for(record, owner):
    db = AsyncMock()
    db.add = Mock()
    db.execute.side_effect = [
        Mock(scalar_one_or_none=Mock(return_value=record)),
        Mock(scalar_one_or_none=Mock(return_value=owner)),
    ]
    return db


def _signed(payload: bytes, secret="whsec_test_only", timestamp=None):
    timestamp = timestamp or int(time.time())
    digest = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def test_signed_webhook_rejects_forgery_and_replay(configured):
    payload = json.dumps({"type": "customer.subscription.updated", "data": {"object": {}}}).encode()
    assert (
        billing_service.verify_webhook(payload, _signed(payload))["type"]
        == "customer.subscription.updated"
    )
    with pytest.raises(HTTPException) as forged:
        billing_service.verify_webhook(payload + b" ", _signed(payload))
    assert forged.value.status_code == 400
    with pytest.raises(HTTPException) as replay:
        billing_service.verify_webhook(payload, _signed(payload, timestamp=int(time.time()) - 600))
    assert replay.value.status_code == 400


async def test_billing_flag_blocks_checkout(configured, owner, monkeypatch):
    monkeypatch.setattr(billing.settings, "stripe_billing_enabled", False)
    request = AsyncMock()
    monkeypatch.setattr(billing, "stripe_request", request)
    with pytest.raises(HTTPException) as error:
        await billing.checkout(owner, AsyncMock())
    assert error.value.status_code == 503
    request.assert_not_awaited()


@pytest.mark.parametrize("amount", [1800, 2900])
async def test_checkout_rejects_wrong_configured_price(configured, owner, monkeypatch, amount):
    db = AsyncMock()
    db.execute.side_effect = [Mock(), Mock(scalar_one_or_none=Mock(return_value=None))]
    request = AsyncMock(return_value=_price(amount))
    monkeypatch.setattr(billing, "stripe_request", request)
    with pytest.raises(HTTPException) as error:
        await billing.checkout(owner, db)
    assert error.value.status_code == 503
    assert "£19" in error.value.detail
    assert request.await_count == 1
    assert owner.plan == "free"


async def test_checkout_creates_customer_and_session_without_upgrading(
    configured, owner, monkeypatch
):
    db = AsyncMock()
    db.add = Mock()
    db.execute.side_effect = [Mock(), Mock(scalar_one_or_none=Mock(return_value=None))]
    calls = []

    async def stripe(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path.startswith("/prices/"):
            return _price()
        if path == "/customers":
            return {"id": "cus_test"}
        if path.startswith("/subscriptions?"):
            return {"data": []}
        return {
            "id": "cs_test",
            "expires_at": int(time.time()) + 3600,
            "url": "https://checkout.stripe.com/c/pay/test",
        }

    monkeypatch.setattr(billing, "stripe_request", stripe)
    result = await billing.checkout(owner, db)
    assert result["url"].startswith("https://checkout.stripe.com/")
    assert calls[1][2]["data"]["metadata[zephyr_user_id]"] == str(owner.id)
    assert calls[3][2]["data"]["line_items[0][price]"] == "price_pro_19"
    assert calls[3][2]["data"]["subscription_data[metadata][zephyr_user_id]"] == str(owner.id)
    assert calls[3][2]["data"]["success_url"] == "https://zephyr.example/settings?billing=returned"
    assert calls[3][2]["data"]["branding_settings[display_name]"] == "Vesquiri"
    assert calls[3][2]["data"]["consent_collection[terms_of_service]"] == "required"
    policy_text = calls[3][2]["data"]["custom_text[terms_of_service_acceptance][message]"]
    assert "https://zephyr.example/terms" in policy_text
    assert "https://zephyr.example/privacy" in policy_text
    assert owner.plan == "free"
    assert db.flush.await_count == 2


async def test_checkout_blocks_existing_subscription(configured, owner, monkeypatch):
    db = AsyncMock()
    db.execute.side_effect = [
        Mock(),
        Mock(
            scalar_one_or_none=Mock(
                return_value=SimpleNamespace(
                    stripe_subscription_id="sub_existing",
                    status="past_due",
                    pending_checkout_session_id=None,
                    checkout_expires_at=None,
                )
            )
        ),
    ]
    request = AsyncMock()
    monkeypatch.setattr(billing, "stripe_request", request)
    with pytest.raises(HTTPException) as error:
        await billing.checkout(owner, db)
    assert error.value.status_code == 409
    request.assert_not_awaited()


async def test_checkout_reuses_open_session(configured, owner, monkeypatch):
    record = SimpleNamespace(
        stripe_subscription_id=None,
        stripe_customer_id="cus_test",
        status="incomplete",
        pending_checkout_session_id="cs_open",
        checkout_expires_at=billing.datetime.now(UTC) + timedelta(minutes=30),
    )
    db = AsyncMock()
    db.execute.side_effect = [Mock(), Mock(scalar_one_or_none=Mock(return_value=record))]
    request = AsyncMock(
        return_value={
            "status": "open",
            "url": "https://checkout.stripe.com/c/pay/reused",
        }
    )
    monkeypatch.setattr(billing, "stripe_request", request)
    result = await billing.checkout(owner, db)
    assert result["url"].endswith("/reused")
    request.assert_awaited_once_with("GET", "/checkout/sessions/cs_open")


async def test_checkout_blocks_remote_active_subscription(configured, owner, monkeypatch):
    record = SimpleNamespace(
        stripe_subscription_id=None,
        stripe_customer_id="cus_test",
        status="incomplete",
        pending_checkout_session_id=None,
        checkout_expires_at=None,
    )
    db = AsyncMock()
    db.execute.side_effect = [Mock(), Mock(scalar_one_or_none=Mock(return_value=record))]
    calls = []

    async def stripe(method, path, **kwargs):
        calls.append(path)
        if path.startswith("/prices/"):
            return _price()
        return {"data": [{"id": "sub_remote", "status": "active"}]}

    monkeypatch.setattr(billing, "stripe_request", stripe)
    with pytest.raises(HTTPException) as error:
        await billing.checkout(owner, db)
    assert error.value.status_code == 409
    assert "/checkout/sessions" not in calls


async def test_portal_uses_only_owned_customer(configured, owner, monkeypatch):
    db = AsyncMock()
    db.execute.return_value = Mock(
        scalar_one_or_none=Mock(
            return_value=SimpleNamespace(
                stripe_customer_id="cus_owned",
            )
        )
    )
    request = AsyncMock(return_value={"url": "https://billing.stripe.com/p/session"})
    monkeypatch.setattr(billing, "stripe_request", request)
    assert (await billing.portal(owner, db))["url"].startswith("https://billing.stripe.com/")
    assert request.await_args.kwargs["data"]["customer"] == "cus_owned"
    assert request.await_args.kwargs["data"]["return_url"] == "https://zephyr.example/settings"


async def test_portal_uses_app_specific_configuration(configured, owner, monkeypatch):
    monkeypatch.setattr(billing.settings, "stripe_portal_configuration_id", "bpc_vesquiri")
    db = AsyncMock()
    db.execute.return_value = Mock(
        scalar_one_or_none=Mock(return_value=SimpleNamespace(stripe_customer_id="cus_owned"))
    )
    request = AsyncMock(return_value={"url": "https://billing.stripe.com/p/session"})
    monkeypatch.setattr(billing, "stripe_request", request)

    await billing.portal(owner, db)

    assert request.await_args.kwargs["data"] == {
        "customer": "cus_owned",
        "return_url": "https://zephyr.example/settings",
        "configuration": "bpc_vesquiri",
    }


@pytest.mark.parametrize(
    "status,price,expected",
    [
        ("active", "price_pro_19", "starter"),
        ("trialing", "price_pro_19", "starter"),
        ("past_due", "price_pro_19", "free"),
        ("unpaid", "price_pro_19", "free"),
        ("canceled", "price_pro_19", "free"),
        ("active", "price_other", "free"),
    ],
)
async def test_verified_subscription_controls_access(configured, owner, status, price, expected):
    record = SimpleNamespace(
        user_id=owner.id,
        stripe_customer_id="cus_test",
        stripe_subscription_id="sub_test",
        status="active",
        plan="starter",
    )
    db = _db_for(record, owner)
    await billing_service.reconcile_subscription(
        db, _stripe_subscription(owner, status=status, price=price)
    )
    assert owner.plan == expected
    assert record.plan == expected
    assert record.status == status
    assert record.current_period_end is not None
    db.flush.assert_awaited_once()


async def test_cancellation_at_period_end_keeps_pro_until_stripe_ends_it(configured, owner):
    record = SimpleNamespace(
        user_id=owner.id,
        stripe_customer_id="cus_test",
        stripe_subscription_id="sub_test",
        status="active",
        plan="starter",
    )
    db = _db_for(record, owner)
    stripe_sub = _stripe_subscription(owner)
    stripe_sub["cancel_at_period_end"] = True
    await billing_service.reconcile_subscription(db, stripe_sub)
    assert owner.plan == "starter"
    assert record.cancel_at_period_end is True


async def test_subscription_cannot_claim_another_users_customer(configured, owner):
    record = SimpleNamespace(
        user_id=uuid.uuid4(),
        stripe_customer_id="cus_test",
        stripe_subscription_id="sub_test",
        status="active",
        plan="free",
    )
    db = AsyncMock()
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=record))
    await billing_service.reconcile_subscription(db, _stripe_subscription(owner))
    db.flush.assert_not_awaited()
    assert record.plan == "free"


async def test_late_cancellation_event_uses_current_stripe_state(configured, owner, monkeypatch):
    record = SimpleNamespace(
        user_id=owner.id,
        stripe_customer_id="cus_test",
        stripe_subscription_id="sub_test",
        status="active",
        plan="starter",
    )
    db = _db_for(record, owner)
    remote = AsyncMock(return_value=_stripe_subscription(owner, status="active"))
    monkeypatch.setattr(billing_service, "stripe_request", remote)
    await billing_service.process_billing_event(
        db,
        {
            "type": "customer.subscription.deleted",
            "data": {"object": _stripe_subscription(owner, status="canceled")},
        },
    )
    assert owner.plan == "starter"
    remote.assert_awaited_once_with("GET", "/subscriptions/sub_test")


async def test_failed_invoice_rechecks_current_subscription(configured, owner, monkeypatch):
    record = SimpleNamespace(
        user_id=owner.id,
        stripe_customer_id="cus_test",
        stripe_subscription_id="sub_test",
        status="active",
        plan="starter",
    )
    db = _db_for(record, owner)
    monkeypatch.setattr(
        billing_service,
        "stripe_request",
        AsyncMock(return_value=_stripe_subscription(owner, status="past_due")),
    )
    await billing_service.process_billing_event(
        db,
        {
            "type": "invoice.payment_failed",
            "data": {"object": {"parent": {"subscription_details": {"subscription": "sub_test"}}}},
        },
    )
    assert owner.plan == "free"


async def test_checkout_return_does_not_grant_access(configured, owner):
    # Browser redirects never call the reconciliation function.
    assert owner.plan == "free"
    assert billing_service.require_stripe_url(
        "https://checkout.stripe.com/c/pay/test", "checkout.stripe.com"
    )
    with pytest.raises(HTTPException):
        billing_service.require_stripe_url(
            "https://attacker.example/checkout", "checkout.stripe.com"
        )


async def test_webhook_http_route_requires_signature_and_updates_plan(
    configured, owner, monkeypatch
):
    record = SimpleNamespace(
        user_id=owner.id,
        stripe_customer_id="cus_test",
        stripe_subscription_id="sub_test",
        status="incomplete",
        plan="free",
    )
    db = _db_for(record, owner)
    app = FastAPI()
    app.include_router(billing.router, prefix="/billing")

    async def fake_db():
        yield db

    app.dependency_overrides[get_db] = fake_db
    monkeypatch.setattr(
        billing_service, "stripe_request", AsyncMock(return_value=_stripe_subscription(owner))
    )
    payload = json.dumps(
        {
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_test"}},
        }
    ).encode()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        rejected = await client.post(
            "/billing/webhook", content=payload, headers={"stripe-signature": "invalid"}
        )
        assert rejected.status_code == 400
        accepted = await client.post(
            "/billing/webhook", content=payload, headers={"stripe-signature": _signed(payload)}
        )
    assert accepted.status_code == 200
    assert owner.plan == "starter"


async def test_billing_http_routes_require_login_for_checkout(configured):
    app = FastAPI()
    app.include_router(billing.router, prefix="/billing")

    async def fake_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = fake_db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        availability = await client.get("/billing/availability")
        checkout = await client.post("/billing/checkout")
        portal = await client.post("/billing/portal")
    assert availability.json() == {"enabled": True}
    assert checkout.status_code == 401
    assert portal.status_code == 401


async def test_stripe_http_client_uses_secret_and_hides_provider_error(configured, monkeypatch):
    captured = []
    status = {"code": 200}

    def respond(request):
        captured.append(request)
        if status["code"] == 200:
            return httpx.Response(200, json={"id": "cus_test"})
        return httpx.Response(400, json={"error": {"message": "private provider detail"}})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        billing_service.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs),
    )
    result = await billing_service.stripe_request(
        "POST",
        "/customers",
        data={"email": "test@example.com"},
        idempotency_key="zephyr-test",
    )
    assert result["id"] == "cus_test"
    assert captured[0].headers["authorization"] == "Bearer sk_test_only"
    assert captured[0].headers["idempotency-key"] == "zephyr-test"
    status["code"] = 400
    with pytest.raises(HTTPException) as error:
        await billing_service.stripe_request("GET", "/prices/bad")
    assert error.value.status_code == 503
    assert "private provider detail" not in error.value.detail
