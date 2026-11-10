from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3
from unittest.mock import MagicMock

import pytest
import requests

from backend.db import get_db
from backend.errors import AppError
from backend.paypal import PayPalService
from conftest import public_path


def unpaid(client, saved):
    assert client.get(f'/api/requests/{saved["id"]}').json["request"]["status"] != "paid"


def test_create_and_capture_and_duplicates(client, saved, paypal, approved):
    path, order_id = approved
    # An approved order must be reconciled, not sent through buyer approval again.
    assert client.post(path + "/orders").json["error"]["code"] == "payment_pending"
    assert len(paypal.create_calls) == 1
    for _ in range(2):
        response = client.post(path + "/capture", json={"order_id": order_id})
        assert response.status_code == 200
        assert response.json["status"] == "paid"
    assert len(paypal.capture_calls) == 1
    assert client.get("/api/dashboard").json["paid_cents"] == 5010
    assert client.post(path + "/orders").status_code == 409


def test_cancellation_is_retryable(client, saved, paypal):
    path = public_path(saved)
    order_id = client.post(path + "/orders").json["order_id"]
    assert client.post(path + "/cancel", json={"order_id": order_id}).status_code == 200
    unpaid(client, saved)
    assert client.post(path + "/orders").json["order_id"] == order_id
    assert len(paypal.capture_calls) == 0


def test_unapproved_order_never_captured(client, saved, paypal):
    path = public_path(saved)
    order_id = client.post(path + "/orders").json["order_id"]
    assert client.post(path + "/capture", json={"order_id": order_id}).json["error"]["code"] == "order_not_approved"
    assert len(paypal.capture_calls) == 0
    assert client.post(path + "/orders").status_code == 201
    unpaid(client, saved)


@pytest.mark.parametrize("field,value", [("value", "50.11"), ("currency_code", "EUR")])
def test_amount_currency_mismatch(client, saved, paypal, approved, field, value):
    path, order_id = approved
    paypal.orders[order_id]["purchase_units"][0]["amount"][field] = value
    response = client.post(path + "/capture", json={"order_id": order_id})
    assert response.json["error"]["code"] == "payment_mismatch"
    assert len(paypal.capture_calls) == 0
    unpaid(client, saved)


@pytest.mark.parametrize("field,value", [("custom_id", "unrelated"), ("reference_id", "999"), ("payee", {"merchant_id": "OTHERSELLER"})])
def test_binding_and_merchant_verification(client, saved, paypal, approved, field, value):
    path, order_id = approved
    paypal.orders[order_id]["purchase_units"][0][field] = value
    assert client.post(path + "/capture", json={"order_id": order_id}).json["error"]["code"] == "payment_mismatch"
    unpaid(client, saved)


def test_unrelated_order(client, saved, paypal, approved):
    path, order_id = approved
    other = client.post("/api/requests", json={"client_name": "Other", "service_description": "Other", "amount": "50.10", "due_date": "2026-11-10"}).json["request"]
    response = client.post(public_path(other) + "/capture", json={"order_id": order_id})
    assert response.json["error"]["code"] == "order_not_bound"
    assert len(paypal.capture_calls) == 0
    unpaid(client, saved)


@pytest.mark.parametrize("capture_status,code", [("PENDING", "payment_pending"), ("DECLINED", "payment_declined"), ("FAILED", "payment_declined")])
def test_pending_and_failure_not_paid(client, saved, paypal, approved, capture_status, code):
    path, order_id = approved
    paypal.capture_status = capture_status
    response = client.post(path + "/capture", json={"order_id": order_id})
    assert response.json["error"]["code"] == code
    unpaid(client, saved)
    if capture_status == "PENDING":
        assert client.post(path + "/orders").status_code == 409
        client.post(path + "/capture", json={"order_id": order_id})
        assert len(paypal.capture_calls) == 1
    else:
        retry = client.post(path + "/orders")
        assert retry.status_code == 201
        assert retry.json["order_id"] != order_id


def test_uncertain_capture_recovers_without_second_capture(client, saved, paypal, approved):
    path, order_id = approved
    paypal.uncertain_capture = True
    assert client.post(path + "/capture", json={"order_id": order_id}).status_code == 502
    unpaid(client, saved)
    assert client.get(path).json["request"]["active_order_id"] == order_id
    assert client.post(path + "/orders").status_code == 409
    assert client.post(path + "/capture", json={"order_id": order_id}).json["status"] == "paid"
    assert len(paypal.capture_calls) == 1
    assert len(paypal.get_calls) == 2


def test_uncertain_create_reuses_key(client, saved, paypal):
    path = public_path(saved)
    paypal.uncertain_create = True
    assert client.post(path + "/orders").status_code == 502
    assert client.post(path + "/orders").status_code == 201
    assert len(paypal.create_calls) == 2
    assert paypal.create_calls[0] == paypal.create_calls[1]
    unpaid(client, saved)


def test_capture_retry_after_reconcile_reuses_key(client, saved, paypal, approved, monkeypatch):
    path, order_id = approved
    original = paypal.capture
    keys = []

    def timeout_before_capture(order, key):
        keys.append(key)
        raise AppError("paypal_uncertain", "Timeout before reaching PayPal", 502)

    monkeypatch.setattr(paypal, "capture", timeout_before_capture)
    assert client.post(path + "/capture", json={"order_id": order_id}).status_code == 502
    monkeypatch.setattr(paypal, "capture", original)
    assert client.post(path + "/capture", json={"order_id": order_id}).status_code == 200
    assert keys == paypal.capture_calls
    assert len(paypal.get_calls) == 2


def test_retry_window_blocks_ambiguous_replay(app, client, saved, paypal, approved):
    path, order_id = approved
    old = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
    with app.app_context():
        get_db().execute("UPDATE payment_attempts SET capture_started_at=?", (old,))
    assert client.post(path + "/capture", json={"order_id": order_id}).json["error"]["code"] == "reconciliation_required"
    assert len(paypal.capture_calls) == 0
    unpaid(client, saved)


def test_capture_amount_mismatch_not_paid(client, saved, paypal, approved, monkeypatch):
    path, order_id = approved
    original = paypal.capture

    def wrong_capture(order, key):
        result = original(order, key)
        result["purchase_units"][0]["payments"]["captures"][0]["amount"]["value"] = "1.00"
        return result

    monkeypatch.setattr(paypal, "capture", wrong_capture)
    assert client.post(path + "/capture", json={"order_id": order_id}).json["error"]["code"] == "payment_mismatch"
    unpaid(client, saved)


def test_concurrent_callbacks_capture_once(app, saved, paypal, approved):
    path, order_id = approved

    def call(_):
        with app.test_client() as browser:
            return browser.post(path + "/capture", json={"order_id": order_id}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(call, range(2))) == [200, 200]
    assert len(paypal.capture_calls) == 1


def test_transport_sandbox_oauth_keys_and_no_secret_to_browser(app, client):
    service = PayPalService(app.config)
    auth = MagicMock()
    auth.json.return_value = {"access_token": "test-token", "expires_in": 3600}
    service.session.post = MagicMock(return_value=auth)
    response = MagicMock(ok=True)
    response.json.return_value = {"id": "ORDER1"}
    service.session.request = MagicMock(return_value=response)
    for _ in range(2):
        service.capture("ORDER1", "persistent-key")
    service.session.post.assert_called_once()
    call = service.session.request.call_args
    assert call.args == ("POST", "https://api-m.sandbox.paypal.com/v2/checkout/orders/ORDER1/capture")
    assert call.kwargs["headers"]["PayPal-Request-Id"] == "persistent-key"
    assert "test-secret" not in client.get("/api/public/config").text


def test_transport_timeout_is_uncertain(app):
    service = PayPalService(app.config)
    service.access_token = lambda: "test-token"
    service.session.request = MagicMock(side_effect=requests.Timeout("sensitive response"))
    with pytest.raises(AppError) as error:
        service.capture("ORDER1", "key")
    assert error.value.code == "paypal_uncertain"
    assert "sensitive" not in str(error.value)
    assert service.session.request.call_count == 1


def test_expired_order_can_restart(client, saved, paypal, approved):
    path, order_id = approved
    paypal.orders[order_id]["status"] = "VOIDED"
    assert client.post(path + "/capture", json={"order_id": order_id}).json["error"]["code"] == "order_voided"
    assert client.post(path + "/orders").json["order_id"] != order_id
    unpaid(client, saved)


def test_missing_paypal_configuration(app, client, saved):
    app.extensions["paypal"] = PayPalService({**app.config, "PAYPAL_CLIENT_SECRET": ""})
    assert client.post(public_path(saved) + "/orders").status_code == 503
    assert client.get("/api/public/config").json["paypal_client_id"] is None


def test_lookup_failure_does_not_replay_capture(client, saved, paypal, approved, monkeypatch):
    path, order_id = approved

    def failed_lookup(_):
        raise AppError("paypal_uncertain", "Simulated GET timeout", 502)

    monkeypatch.setattr(paypal, "get_order", failed_lookup)
    assert client.post(path + "/capture", json={"order_id": order_id}).status_code == 502
    assert len(paypal.capture_calls) == 0
    unpaid(client, saved)


@pytest.mark.parametrize("unavailable", ["missing", "VOIDED"])
def test_unavailable_uncaptured_order_is_replaced(app, client, saved, paypal, monkeypatch, unavailable):
    path = public_path(saved)
    old_id = client.post(path + "/orders").json["order_id"]
    original = paypal.get_order

    def lookup(order_id):
        if order_id == old_id and unavailable == "missing":
            raise AppError("paypal_order_not_found", "Unavailable", 502)
        return original(order_id)

    monkeypatch.setattr(paypal, "get_order", lookup)
    if unavailable == "VOIDED":
        paypal.orders[old_id]["status"] = "VOIDED"
    response = client.post(path + "/orders")
    assert response.status_code == 201
    new_id = response.json["order_id"]
    assert new_id != old_id
    assert client.post(path + "/orders").json["order_id"] == new_id
    assert len(set(paypal.create_calls)) == 2
    assert not paypal.capture_calls
    with app.app_context():
        old = get_db().execute("SELECT * FROM payment_attempts WHERE order_id=?", (old_id,)).fetchone()
        assert old["state"] == "failed"
        assert old["diagnostic"] == "order_unavailable"
        assert get_db().execute("SELECT COUNT(*) FROM payment_attempts").fetchone()[0] == 2
    unpaid(client, saved)


@pytest.mark.parametrize("code", ["paypal_uncertain", "paypal_auth_error", "paypal_upstream_error", "payment_mismatch"])
def test_cached_order_lookup_error_never_creates_replacement(client, saved, paypal, monkeypatch, code):
    path = public_path(saved)
    client.post(path + "/orders")

    def failed_lookup(_):
        raise AppError(code, "Lookup failed", 502)

    monkeypatch.setattr(paypal, "get_order", failed_lookup)
    assert client.post(path + "/orders").json["error"]["code"] == code
    assert len(paypal.create_calls) == 1
    assert not paypal.capture_calls


def test_cached_order_is_verified_before_reuse(client, saved, paypal):
    path = public_path(saved)
    order_id = client.post(path + "/orders").json["order_id"]
    paypal.orders[order_id]["purchase_units"][0]["payee"]["merchant_id"] = "OTHERSELLER"
    assert client.post(path + "/orders").json["error"]["code"] == "payment_mismatch"
    assert len(paypal.create_calls) == 1


def test_missing_order_after_capture_started_never_replaced(app, client, saved, paypal, approved, monkeypatch):
    path, order_id = approved

    def missing(_):
        raise AppError("paypal_order_not_found", "Unavailable", 502)

    monkeypatch.setattr(paypal, "get_order", missing)
    assert client.post(path + "/capture", json={"order_id": order_id}).status_code == 502
    assert client.post(path + "/orders").json["error"]["code"] == "payment_pending"
    assert len(paypal.create_calls) == 1
    assert not paypal.capture_calls
    unpaid(client, saved)


def test_concurrent_stale_order_retries_create_one_replacement(app, client, saved, paypal, monkeypatch):
    path = public_path(saved)
    old_id = client.post(path + "/orders").json["order_id"]
    original = paypal.get_order

    def lookup(order_id):
        if order_id == old_id:
            raise AppError("paypal_order_not_found", "Unavailable", 502)
        return original(order_id)

    monkeypatch.setattr(paypal, "get_order", lookup)

    def create(_):
        with app.test_client() as browser:
            response = browser.post(path + "/orders")
            assert response.status_code == 201
            return response.json["order_id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(create, range(2)))
    assert ids[0] == ids[1] != old_id
    assert len(paypal.create_calls) == 2


def test_replacement_timeout_reuses_committed_key(app, client, saved, paypal, monkeypatch):
    path = public_path(saved)
    old_id = client.post(path + "/orders").json["order_id"]
    paypal.orders[old_id]["status"] = "VOIDED"
    paypal.uncertain_create = True
    original = paypal.create

    def create_with_committed_key(row, attempt):
        # A separate connection must see the replacement before the upstream POST.
        with sqlite3.connect(app.config["DATABASE"]) as connection:
            assert connection.execute("SELECT create_key FROM payment_attempts WHERE id=?", (attempt["id"],)).fetchone()[0] == attempt["create_key"]
        return original(row, attempt)

    monkeypatch.setattr(paypal, "create", create_with_committed_key)
    assert client.post(path + "/orders").status_code == 502
    with app.app_context():
        attempts = get_db().execute("SELECT * FROM payment_attempts ORDER BY rowid").fetchall()
        assert len(attempts) == 2
        assert attempts[0]["state"] == "failed"
        assert attempts[1]["state"] == "uncertain"
        key = attempts[1]["create_key"]
    assert client.post(path + "/orders").status_code == 201
    assert paypal.create_calls[-2:] == [key, key]


def test_late_error_cannot_resurrect_retired_attempt(app, client, saved, paypal):
    from backend.payments import record_error

    path = public_path(saved)
    old_id = client.post(path + "/orders").json["order_id"]
    paypal.orders[old_id]["status"] = "VOIDED"
    assert client.post(path + "/orders").status_code == 201
    with app.app_context():
        attempt = get_db().execute("SELECT id FROM payment_attempts WHERE order_id=?", (old_id,)).fetchone()
        record_error(attempt["id"], AppError("paypal_uncertain", "Late response", 502))
        assert get_db().execute("SELECT state FROM payment_attempts WHERE id=?", (attempt["id"],)).fetchone()[0] == "failed"


@pytest.mark.parametrize("method,path,status,name,issues,expected", [
    ("GET", "/v2/checkout/orders/ORDER1", 404, "RESOURCE_NOT_FOUND", ["INVALID_RESOURCE_ID"], "paypal_order_not_found"),
    ("GET", "/v2/checkout/orders/ORDER1", 404, "OTHER_ERROR", [], "paypal_upstream_error"),
    ("GET", "/v2/checkout/orders/ORDER1", 401, "RESOURCE_NOT_FOUND", ["INVALID_RESOURCE_ID"], "paypal_upstream_error"),
    ("POST", "/v2/checkout/orders/ORDER1/capture", 404, "RESOURCE_NOT_FOUND", ["INVALID_RESOURCE_ID"], "paypal_upstream_error"),
])
def test_transport_safe_diagnostics_and_missing_classification(app, caplog, method, path, status, name, issues, expected):
    service = PayPalService(app.config)
    service.access_token = lambda: "never-log-token"
    response = MagicMock(ok=False, status_code=status, headers={})
    response.json.return_value = {
        "name": name, "debug_id": "f4398162bb931", "message": "private-buyer-information",
        "details": [{"issue": issue, "value": "private-buyer-information"} for issue in issues],
        "access_token": "never-log-token",
    }
    service.session.request = MagicMock(return_value=response)
    with pytest.raises(AppError) as error:
        service.call(method, path)
    assert error.value.code == expected
    assert error.value.diagnostics["debug_id"] == "f4398162bb931"
    assert "f4398162bb931" in caplog.text
    assert "never-log-token" not in caplog.text
    assert "private-buyer-information" not in caplog.text
    assert service.session.request.call_count == 1


def test_safe_debug_id_in_api_error(app, client, saved, monkeypatch):
    def fail(_token):
        raise AppError("paypal_upstream_error", "PayPal unavailable", 502, {"debug_id": "f4398162bb931", "name": "PRIVATE"})

    monkeypatch.setattr("backend.payments.create_order", fail)
    response = client.post(public_path(saved) + "/orders")
    assert response.status_code == 502
    assert response.json["error"] == {"code": "paypal_upstream_error", "message": "PayPal unavailable", "debug_id": "f4398162bb931"}
