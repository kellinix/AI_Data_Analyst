"""Seven-day payments must not renew, extend on replay, or outlive access checks."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api import deps
from app.api.v1.endpoints import billing
from app.services import billing_service, pro_pass_service


@pytest.fixture
def configured(monkeypatch):
    for key, value in {
        "stripe_billing_enabled": True,
        "stripe_live_mode": False,
        "stripe_secret_key": "sk_test_only",
        "stripe_webhook_secret": "whsec_test_only",
        "stripe_pro_price_id": "price_monthly",
        "stripe_weekly_price_id": "price_weekly",
        "stripe_payment_method_configuration_id": "",
        "frontend_url": "https://vesquiri.example",
        "app_name": "Vesquiri",
    }.items():
        monkeypatch.setattr(billing.settings, key, value)


@pytest.fixture
def owner():
    return SimpleNamespace(
        id=uuid.uuid4(), email="weekly@example.test", plan="free", is_active=True,
        pro_pass_expires_at=None, analyses_this_month=5, ai_queries_this_month=1,
    )


def checkout_db(record=None):
    db = AsyncMock()
    db.add = Mock()
    db.execute.side_effect = [Mock(), Mock(scalar_one_or_none=Mock(return_value=record))]
    return db


def pending_record(offer="weekly"):
    return SimpleNamespace(
        stripe_subscription_id=None, stripe_customer_id="cus_weekly", status="incomplete",
        pending_checkout_session_id="cs_open", pending_checkout_offer=offer,
        checkout_expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )


def weekly_price():
    return {"active": True, "currency": "gbp", "unit_amount": 599, "type": "one_time"}


async def test_weekly_checkout_is_one_payment_without_granting_access(configured, owner, monkeypatch):
    calls = []

    async def stripe(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path.startswith("/prices/"):
            return weekly_price()
        if path == "/customers":
            return {"id": "cus_weekly"}
        if path.startswith("/subscriptions?"):
            return {"data": []}
        return {"id": "cs_weekly", "url": "https://checkout.stripe.com/c/pay/weekly",
                "expires_at": int(time.time()) + 3600}

    monkeypatch.setattr(billing, "stripe_request", stripe)
    db = checkout_db()
    await billing.checkout(owner, db, billing.CheckoutRequest(offer="weekly"))
    data = calls[-1][2]["data"]
    assert data["mode"] == "payment"
    assert data["line_items[0][price]"] == "price_weekly"
    assert data["metadata[vesquiri_offer]"] == "weekly"
    assert data["metadata[zephyr_user_id]"] == str(owner.id)
    assert data["invoice_creation[enabled]"] == "true"
    assert data["payment_method_types[0]"] == "card"
    assert "payment_method_configuration" not in data
    assert not any(key.startswith("subscription_data") for key in data)
    assert "Does not renew" in data["custom_text[submit][message]"]
    assert owner.plan == "free"
    assert owner.pro_pass_expires_at is None
    assert owner.analyses_this_month == 5
    assert db.add.call_args.args[0].pending_checkout_offer == "weekly"


@pytest.mark.parametrize("offer", ["weekly", "monthly"])
async def test_app_specific_methods_are_selected_without_forcing_card(configured, owner, monkeypatch, offer):
    monkeypatch.setattr(billing.settings, "stripe_payment_method_configuration_id", "pmc_vesquiri")
    record = pending_record(offer)
    record.pending_checkout_session_id = None
    price = weekly_price() if offer == "weekly" else {
        "active": True, "currency": "gbp", "unit_amount": 1900,
        "type": "recurring", "recurring": {"interval": "month", "interval_count": 1},
    }
    remote = AsyncMock(side_effect=[price, {"data": []}, {
        "id": "cs_methods", "url": "https://checkout.stripe.com/c/pay/methods",
        "expires_at": int(time.time()) + 3600,
    }])
    monkeypatch.setattr(billing, "stripe_request", remote)
    await billing.checkout(owner, checkout_db(record), billing.CheckoutRequest(offer=offer))
    data = remote.await_args_list[-1].kwargs["data"]
    assert data["payment_method_configuration"] == "pmc_vesquiri"
    assert not any(key.startswith("payment_method_types") for key in data)
    assert data["mode"] == ("payment" if offer == "weekly" else "subscription")
    assert owner.plan == "free"


async def test_enabling_methods_replaces_an_old_card_only_checkout(configured, owner, monkeypatch):
    monkeypatch.setattr(billing.settings, "stripe_payment_method_configuration_id", "pmc_vesquiri")
    record = pending_record()
    remote = AsyncMock(side_effect=[
        {"status": "open", "metadata": {"vesquiri_offer": "weekly"}, "payment_method_types": ["card"]},
        {"status": "expired"}, weekly_price(), {"data": []},
        {"id": "cs_methods", "url": "https://checkout.stripe.com/c/pay/methods",
         "expires_at": int(time.time()) + 3600},
    ])
    monkeypatch.setattr(billing, "stripe_request", remote)
    await billing.checkout(owner, checkout_db(record), billing.CheckoutRequest(offer="weekly"))
    assert remote.await_args_list[1].args == ("POST", "/checkout/sessions/cs_open/expire")
    assert record.pending_checkout_session_id == "cs_methods"


async def test_same_offer_and_method_configuration_reuses_the_open_checkout(configured, owner, monkeypatch):
    monkeypatch.setattr(billing.settings, "stripe_payment_method_configuration_id", "pmc_vesquiri")
    remote = AsyncMock(return_value={
        "status": "open", "metadata": {"vesquiri_offer": "weekly"},
        "payment_method_configuration_details": {"id": "pmc_vesquiri"},
        "url": "https://checkout.stripe.com/c/pay/reused-methods",
    })
    monkeypatch.setattr(billing, "stripe_request", remote)
    result = await billing.checkout(owner, checkout_db(pending_record()), billing.CheckoutRequest(offer="weekly"))
    assert result["url"].endswith("/reused-methods")
    assert remote.await_count == 1


@pytest.mark.parametrize("status", ["requires_payment_method", "canceled"])
async def test_failed_bank_payment_allows_a_fresh_checkout(configured, owner, monkeypatch, status):
    record = pending_record()
    remote = AsyncMock(side_effect=[
        {"status": "complete", "payment_status": "unpaid", "payment_intent": "pi_failed"},
        {"status": status}, weekly_price(), {"data": []},
        {"id": "cs_retry", "url": "https://checkout.stripe.com/c/pay/retry",
         "expires_at": int(time.time()) + 3600},
    ])
    monkeypatch.setattr(billing, "stripe_request", remote)
    await billing.checkout(owner, checkout_db(record), billing.CheckoutRequest(offer="weekly"))
    assert record.pending_checkout_session_id == "cs_retry"
    assert owner.plan == "free"
    assert not any(call.args[1].endswith("/expire") for call in remote.await_args_list)


@pytest.mark.parametrize("status", ["processing", "requires_action", "succeeded"])
async def test_bank_payment_awaiting_confirmation_blocks_another_purchase(configured, owner, monkeypatch, status):
    remote = AsyncMock(side_effect=[
        {"status": "complete", "payment_status": "unpaid", "payment_intent": "pi_pending"},
        {"status": status},
    ])
    monkeypatch.setattr(billing, "stripe_request", remote)
    with pytest.raises(HTTPException) as error:
        await billing.checkout(owner, checkout_db(pending_record()), billing.CheckoutRequest(offer="weekly"))
    assert error.value.status_code == 409
    assert remote.await_count == 2
    assert owner.plan == "free"


@pytest.mark.parametrize("change", [
    {"unit_amount": 5990}, {"currency": "usd"}, {"active": False},
    {"type": "recurring", "recurring": {"interval": "week"}},
])
async def test_weekly_rejects_wrong_or_recurring_price(configured, owner, monkeypatch, change):
    remote = AsyncMock(return_value=weekly_price() | change)
    monkeypatch.setattr(billing, "stripe_request", remote)
    with pytest.raises(HTTPException) as error:
        await billing.checkout(owner, checkout_db(), billing.CheckoutRequest(offer="weekly"))
    assert error.value.status_code == 503
    assert remote.await_count == 1


@pytest.mark.parametrize("offer", ["weekly", "monthly"])
async def test_active_pass_prevents_overlapping_purchases(configured, owner, monkeypatch, offer):
    owner.pro_pass_expires_at = datetime.now(UTC) + timedelta(days=2)
    owner.plan = "starter"
    remote = AsyncMock()
    monkeypatch.setattr(billing, "stripe_request", remote)
    with pytest.raises(HTTPException) as error:
        await billing.checkout(owner, checkout_db(), billing.CheckoutRequest(offer=offer))
    assert error.value.status_code == 409
    remote.assert_not_awaited()


async def test_weekly_reuses_only_weekly_session(configured, owner, monkeypatch):
    remote = AsyncMock(return_value={
        "status": "open", "metadata": {"vesquiri_offer": "weekly"},
        "url": "https://checkout.stripe.com/c/pay/reused-weekly",
    })
    monkeypatch.setattr(billing, "stripe_request", remote)
    result = await billing.checkout(owner, checkout_db(pending_record()), billing.CheckoutRequest(offer="weekly"))
    assert result["url"].endswith("reused-weekly")
    remote.assert_awaited_once_with("GET", "/checkout/sessions/cs_open")


async def test_switching_offer_expires_the_old_payable_session(configured, owner, monkeypatch):
    record = pending_record("monthly")
    remote = AsyncMock(side_effect=[
        {"status": "open", "metadata": {"vesquiri_offer": "monthly"}},
        {"status": "expired"}, weekly_price(), {"data": []},
        {"id": "cs_new_weekly", "url": "https://checkout.stripe.com/c/pay/weekly",
         "expires_at": int(time.time()) + 3600},
    ])
    monkeypatch.setattr(billing, "stripe_request", remote)
    await billing.checkout(owner, checkout_db(record), billing.CheckoutRequest(offer="weekly"))
    assert remote.await_args_list[1].args == ("POST", "/checkout/sessions/cs_open/expire")
    assert record.pending_checkout_offer == "weekly"
    assert record.pending_checkout_session_id == "cs_new_weekly"


async def test_completed_payment_pending_webhook_blocks_a_second_charge(configured, owner, monkeypatch):
    record = pending_record()
    record.checkout_expires_at = datetime.now(UTC) - timedelta(days=1)
    remote = AsyncMock(return_value={"status": "complete"})
    monkeypatch.setattr(billing, "stripe_request", remote)
    with pytest.raises(HTTPException) as error:
        await billing.checkout(owner, checkout_db(record), billing.CheckoutRequest(offer="weekly"))
    assert error.value.status_code == 409
    assert remote.await_count == 1


async def test_expiry_is_enforced_by_auth_before_quota_checks(owner, monkeypatch):
    owner.plan = "starter"
    owner.pro_pass_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db = AsyncMock()
    db.execute.side_effect = [
        Mock(scalar_one_or_none=Mock(return_value=owner)),
        Mock(scalar_one_or_none=Mock(return_value=None)),
    ]
    monkeypatch.setattr(deps, "verify_supabase_token", AsyncMock(return_value={"sub": "owner"}))
    user = await deps.get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials="test"), db)
    assert user.plan == "free"
    assert user.pro_pass_expires_at is None
    with pytest.raises(HTTPException) as error:
        deps.ensure_analysis_quota(user)
    assert error.value.status_code == 402


async def test_expired_pass_does_not_cancel_an_active_monthly_entitlement(owner):
    owner.plan = "starter"
    owner.pro_pass_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db = AsyncMock()
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=SimpleNamespace(plan="starter", status="active")))
    await pro_pass_service.refresh_expired_pro_pass(db, owner)
    assert owner.plan == "starter"
    assert owner.pro_pass_expires_at is None


async def test_monthly_cancellation_cannot_erase_a_weekly_pass(configured, owner):
    expiry = datetime.now(UTC) + timedelta(days=3)
    owner.pro_pass_expires_at = expiry
    record = SimpleNamespace(
        user_id=owner.id, stripe_customer_id="cus_weekly", stripe_subscription_id="sub_old",
        status="active", plan="starter", pending_checkout_offer="weekly",
        pending_checkout_session_id="cs_weekly",
    )
    db = AsyncMock()
    db.execute.side_effect = [Mock(scalar_one_or_none=Mock(return_value=record)),
                             Mock(scalar_one_or_none=Mock(return_value=owner))]
    await billing_service.reconcile_subscription(db, {
        "id": "sub_old", "customer": "cus_weekly", "status": "canceled",
        "metadata": {"zephyr_user_id": str(owner.id)},
        "items": {"data": [{"price": {"id": "price_monthly"}}]},
    })
    assert record.plan == "free"
    assert owner.plan == "starter"
    assert owner.pro_pass_expires_at == expiry
    assert record.pending_checkout_session_id == "cs_weekly"


async def test_live_mode_rejects_a_test_secret(configured):
    billing.settings.stripe_live_mode = True
    assert not billing_service.billing_available("weekly")


async def test_sandbox_access_does_not_become_live_pro(configured, owner, monkeypatch):
    monkeypatch.setattr(billing.settings, "stripe_live_mode", True)
    owner.plan = "starter"
    owner.billing_livemode = False
    owner.pro_pass_expires_at = datetime.now(UTC) + timedelta(days=3)
    db = AsyncMock()
    await pro_pass_service.refresh_expired_pro_pass(db, owner)
    assert owner.plan == "free"
    assert owner.pro_pass_expires_at is None
    assert owner.billing_livemode is None
    db.refresh.assert_awaited_once_with(owner, with_for_update=True)


async def test_sandbox_cannot_overwrite_live_entitlements(configured, owner):
    owner.plan = "starter"
    owner.billing_livemode = True
    with pytest.raises(HTTPException) as error:
        await pro_pass_service.refresh_expired_pro_pass(AsyncMock(), owner)
    assert error.value.status_code == 503
    assert owner.plan == "starter"


async def test_expiry_reload_does_not_erase_a_new_purchase(configured, owner):
    owner.plan = "starter"
    owner.pro_pass_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db = AsyncMock()
    new_deadline = datetime.now(UTC) + timedelta(days=7)

    async def reload(*args, **kwargs):
        owner.pro_pass_expires_at = new_deadline
        owner.billing_livemode = False

    db.refresh.side_effect = reload
    await pro_pass_service.refresh_expired_pro_pass(db, owner)
    assert owner.pro_pass_expires_at == new_deadline
    assert owner.plan == "starter"
    db.execute.assert_not_awaited()


async def test_live_checkout_replaces_only_sandbox_customer_ids(configured, owner, monkeypatch):
    monkeypatch.setattr(billing.settings, "stripe_live_mode", True)
    monkeypatch.setattr(billing.settings, "stripe_secret_key", "sk_live_only")
    record = pending_record()
    record.stripe_livemode = False
    record.stripe_subscription_id = "sub_sandbox"
    record.status = "active"
    remote = AsyncMock(side_effect=[
        weekly_price(), {"id": "cus_live_new"}, {"data": []},
        {"id": "cs_live_new", "url": "https://checkout.stripe.com/c/pay/live",
         "expires_at": int(time.time()) + 3600},
    ])
    monkeypatch.setattr(billing, "stripe_request", remote)
    await billing.checkout(owner, checkout_db(record), billing.CheckoutRequest(offer="weekly"))
    assert record.stripe_livemode is True
    assert record.stripe_customer_id == "cus_live_new"
    assert record.stripe_subscription_id is None
    assert not any("cus_weekly" in str(call) or "cs_open" in str(call) for call in remote.await_args_list)


async def test_live_records_are_never_replaced_by_sandbox_checkout(configured, owner, monkeypatch):
    record = pending_record()
    record.stripe_livemode = True
    remote = AsyncMock()
    monkeypatch.setattr(billing, "stripe_request", remote)
    with pytest.raises(HTTPException) as error:
        await billing.checkout(owner, checkout_db(record), billing.CheckoutRequest(offer="weekly"))
    assert error.value.status_code == 409
    assert record.stripe_customer_id == "cus_weekly"
    remote.assert_not_awaited()


async def test_cross_mode_webhook_cannot_change_access(configured, owner, monkeypatch):
    monkeypatch.setattr(billing.settings, "stripe_live_mode", True)
    remote = AsyncMock()
    monkeypatch.setattr(billing_service, "stripe_request", remote)
    db = AsyncMock()
    await billing_service.process_billing_event(db, {
        "type": "customer.subscription.created", "livemode": False,
        "data": {"object": {"id": "sub_test"}},
    })
    remote.assert_not_awaited()
    db.execute.assert_not_awaited()
