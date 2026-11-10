import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from backend import create_app
from backend.db import SCHEMA, get_db
from backend.errors import AppError
from conftest import public_path


def path(saved):
    return f'/api/requests/{saved["id"]}'


def details(client, saved):
    return client.get(path(saved)).json


def payment_rows(app):
    with app.app_context():
        return {
            table: [tuple(row) for row in get_db().execute(f"SELECT * FROM {table} ORDER BY rowid")]
            for table in ("payment_attempts", "payment_events")
        }


def test_archive_restore_persist_without_changing_status_or_history(app, client, saved):
    before = details(client, saved)
    records = payment_rows(app)
    archived = client.post(path(saved) + "/archive")
    assert archived.status_code == 200
    item = archived.json["request"]
    assert item["archived"] is True and item["archived_at"]
    assert {key: value for key, value in item.items() if key not in ("archived", "archived_at")} == {
        key: value for key, value in saved.items() if key not in ("archived", "archived_at")
    }
    assert client.post(path(saved) + "/archive").json == archived.json
    reopened = create_app(dict(app.config)).test_client()
    assert reopened.get(path(saved)).json["request"] == item
    assert client.get("/api/requests").json["requests"] == []
    assert client.get("/api/requests?archived=1").json["requests"] == [item]
    assert details(client, saved)["activity"] == before["activity"]
    assert payment_rows(app) == records
    for _ in range(2):
        assert client.post(path(saved) + "/restore").json["request"] == saved
    assert details(client, saved) == before
    assert client.get("/api/requests?archived=1").json["requests"] == []


def test_dashboard_totals_and_recent_requests_exclude_archived(client, saved, paypal, approved):
    public, order_id = approved
    assert client.post(public + "/capture", json={"order_id": order_id}).status_code == 200
    other = client.post("/api/requests", json={"client_name": "Overdue archive fixture", "service_description": "Fictional", "amount": "10.00", "due_date": "2000-01-01"}).json["request"]
    assert client.get("/api/dashboard").json["paid_cents"] == 5010
    assert client.post(path(saved) + "/archive").status_code == 200
    totals = client.get("/api/dashboard").json
    assert (totals["paid_cents"], totals["outstanding_cents"], totals["overdue_cents"], totals["request_count"]) == (0, 1000, 1000, 1)
    assert totals["archived_excluded"] is True
    assert [item["id"] for item in totals["recent_requests"]] == [other["id"]]
    assert client.post(path(other) + "/archive").status_code == 200
    totals = client.get("/api/dashboard").json
    assert (totals["paid_cents"], totals["outstanding_cents"], totals["overdue_cents"], totals["request_count"]) == (0, 0, 0, 0)
    assert totals["recent_requests"] == []
    assert client.post(path(saved) + "/restore").status_code == 200
    assert client.get("/api/dashboard").json["paid_cents"] == 5010
    assert len(client.get("/api/requests?archived=1").json["requests"]) == 1
    assert client.get("/api/requests?archived=invalid").status_code == 400


def test_old_unpaid_link_cannot_create_capture_or_cancel_even_if_order_later_approved(app, client, saved, paypal):
    public = public_path(saved)
    order_id = client.post(public + "/orders").json["order_id"]
    records = payment_rows(app)
    assert client.post(path(saved) + "/archive").status_code == 200
    paypal.orders[order_id]["status"] = "APPROVED"  # An already-open buyer popup may approve later.
    counts = (len(paypal.create_calls), len(paypal.capture_calls), len(paypal.get_calls))
    responses = [client.get(public)] + [client.post(public + action, json={"order_id": order_id}) for action in ("/orders", "/capture", "/cancel")]
    for response in responses:
        assert response.status_code == 404
        assert response.json == {"error": {"code": "request_unavailable", "message": "This payment request is no longer available."}}
    assert (len(paypal.create_calls), len(paypal.capture_calls), len(paypal.get_calls)) == counts
    assert payment_rows(app) == records
    assert client.post(path(saved) + "/restore").status_code == 200
    assert client.get(public).status_code == 200
    assert details(client, saved)["request"]["status"] != "paid"
    assert client.post(public + "/capture", json={"order_id": order_id}).json["status"] == "paid"
    assert len(paypal.capture_calls) == 1


def test_archived_paid_confirmation_and_duplicate_capture_remain_valid(app, client, saved, paypal, approved):
    public, order_id = approved
    captured = client.post(public + "/capture", json={"order_id": order_id}).json
    before = client.get(public).json
    records = payment_rows(app)
    assert client.post(path(saved) + "/archive").status_code == 200
    response = client.get(public, environ_overrides={"REMOTE_ADDR": "192.0.2.1"})
    assert response.json == before
    assert "archived" not in response.text
    assert response.json["request"]["confirmation"]["capture_reference"] == captured["capture_id"]
    paypal.ready = False
    assert client.get(public).json == before  # Confirmation reads stored evidence, not credentials.
    paypal.ready = True
    assert client.post(public + "/capture", json={"order_id": order_id}).json == captured
    assert len(paypal.capture_calls) == 1
    assert client.post(public + "/orders").status_code == 409
    assert client.post(path(saved) + "/restore").status_code == 200
    assert payment_rows(app) == records
    assert client.get(public).json == before


@pytest.mark.parametrize("state,started", [("creating", False), ("capturing", True), ("uncertain", False), ("uncertain", True), ("created", True), ("unknown", False)])
def test_unresolved_local_states_block_archive_without_network_or_state_changes(app, client, saved, paypal, state, started):
    client.post(public_path(saved) + "/orders")
    with app.app_context():
        get_db().execute("UPDATE payment_attempts SET state=?,capture_started_at=?", (state, "2026-11-10T00:00:00+00:00" if started else None))
    before = payment_rows(app)
    result = client.post(path(saved) + "/archive")
    assert result.status_code == 409 and result.json["error"]["code"] == "archive_payment_unresolved"
    assert not details(client, saved)["request"]["archived"]
    assert payment_rows(app) == before
    assert not paypal.get_calls and not paypal.capture_calls


@pytest.mark.parametrize("status", ["APPROVED", "PAYER_ACTION_REQUIRED", "SAVED", "UNKNOWN"])
def test_unresolved_provider_order_blocks_archive(client, saved, paypal, status):
    order_id = client.post(public_path(saved) + "/orders").json["order_id"]
    paypal.orders[order_id]["status"] = status
    assert client.post(path(saved) + "/archive").status_code == 409
    assert not details(client, saved)["request"]["archived"]
    assert not paypal.capture_calls


@pytest.mark.parametrize("error_code,allowed", [("paypal_order_not_found", True), ("paypal_uncertain", False), ("paypal_auth_error", False), ("paypal_upstream_error", False), ("payment_mismatch", False)])
def test_only_authoritative_missing_uncaptured_order_is_safe(app, client, saved, paypal, monkeypatch, error_code, allowed):
    client.post(public_path(saved) + "/orders")
    before = payment_rows(app)

    def lookup(_):
        raise AppError(error_code, "Safe lookup failure", 502)

    monkeypatch.setattr(paypal, "get_order", lookup)
    assert client.post(path(saved) + "/archive").status_code == (200 if allowed else 409)
    assert details(client, saved)["request"]["archived"] is allowed
    assert payment_rows(app) == before


def test_remote_capture_must_be_reconciled_before_archive(client, saved, paypal, approved):
    public, order_id = approved
    paypal.capture(order_id, "external-fixture-capture")
    assert client.post(path(saved) + "/archive").status_code == 409
    assert details(client, saved)["request"]["status"] != "paid"
    assert client.post(public + "/capture", json={"order_id": order_id}).json["status"] == "paid"
    assert client.post(path(saved) + "/archive").status_code == 200
    assert len(paypal.capture_calls) == 1


def test_order_binding_mismatch_blocks_archive(client, saved, paypal):
    order_id = client.post(public_path(saved) + "/orders").json["order_id"]
    paypal.orders[order_id]["purchase_units"][0]["payee"]["merchant_id"] = "OTHERSELLER"
    assert client.post(path(saved) + "/archive").status_code == 409


def test_known_failed_and_voided_attempts_can_archive(app, client, saved, paypal, approved):
    public, order_id = approved
    paypal.capture_status = "DECLINED"
    assert client.post(public + "/capture", json={"order_id": order_id}).status_code == 409
    before = payment_rows(app)
    assert client.post(path(saved) + "/archive").status_code == 200
    assert payment_rows(app) == before
    assert client.post(path(saved) + "/restore").status_code == 200
    # A normal retry creates a second attempt; archive preserves its voided order too.
    next_id = client.post(public + "/orders").json["order_id"]
    paypal.orders[next_id]["status"] = "VOIDED"
    before = payment_rows(app)
    assert client.post(path(saved) + "/archive").status_code == 200
    assert payment_rows(app) == before


def test_archive_without_attempt_needs_no_paypal_credentials(client, saved, paypal):
    paypal.ready = False
    assert client.post(path(saved) + "/archive").status_code == 200
    assert client.post(public_path(saved) + "/orders").json["error"]["code"] == "request_unavailable"
    assert not paypal.create_calls and not paypal.get_calls


def test_archive_requires_management_access_and_has_no_public_mutations(app, client, saved):
    for action in ("archive", "restore"):
        endpoint = path(saved) + "/" + action
        assert client.post(endpoint, environ_overrides={"REMOTE_ADDR": "192.0.2.1"}).status_code == 403
        assert client.post(endpoint, headers={"Origin": "https://evil.example"}).status_code == 403
        assert client.post(endpoint, headers={"X-Forwarded-For": "192.0.2.1"}).status_code == 403
        assert client.post(public_path(saved) + "/" + action).status_code in (404, 405)
        assert not any(rule.rule.startswith('/api/public/') and rule.rule.endswith('/' + action) for rule in app.url_map.iter_rules())
    original_hosts = app.config["TRUSTED_HOSTS"]
    app.config["TRUSTED_HOSTS"] = ["demo.example"]
    assert client.post(path(saved) + "/archive", headers={"Host": "demo.example"}).status_code == 403
    app.config["TRUSTED_HOSTS"] = original_hosts
    assert not details(client, saved)["request"]["archived"]


def test_archived_unpaid_does_not_generate_ai_but_paid_can_still_thank(client, saved, named, paypal, approved, monkeypatch):
    from backend import ai

    calls = []
    monkeypatch.setattr(ai, "generate_guidance_message", lambda *args: calls.append(args) or "Thank-you fixture")
    public, order_id = approved
    paypal.orders[order_id]["status"] = "CREATED"
    assert client.post(path(saved) + "/archive").status_code == 200
    assert client.post(path(saved) + "/message", json={"context_aware": True}).status_code == 409
    assert not calls
    client.post(path(saved) + "/restore")
    paypal.orders[order_id]["status"] = "APPROVED"
    client.post(public + "/capture", json={"order_id": order_id})
    client.post(path(saved) + "/archive")
    assert client.post(path(saved) + "/message", json={"context_aware": True}).status_code == 200
    assert calls[0][0]["message_purpose"] == "thank_you"


def test_mid_generation_archive_rejects_stale_message(client, saved, named, monkeypatch):
    from backend import ai

    def generate(*_args):
        from backend.archiving import archive_request
        archive_request(saved["id"])
        return "Outdated payment request"

    monkeypatch.setattr(ai, "generate_guidance_message", generate)
    response = client.post(path(saved) + "/message", json={"context_aware": True})
    assert response.status_code == 409 and response.json["error"]["code"] == "guidance_changed"
    assert "Outdated" not in response.text


@pytest.mark.parametrize("operation", ["create", "capture"])
def test_inflight_network_operation_is_promptly_blocked_from_archiving(app, client, saved, paypal, monkeypatch, operation):
    public = public_path(saved)
    order_id = None
    if operation == "capture":
        order_id = client.post(public + "/orders").json["order_id"]
        paypal.orders[order_id]["status"] = "APPROVED"
    entered, release = Event(), Event()
    original = getattr(paypal, operation)

    def delayed(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(paypal, operation, delayed)

    def pay():
        with app.test_client() as browser:
            return browser.post(public + ("/orders" if operation == "create" else "/capture"), json={"order_id": order_id}).status_code

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(pay)
        assert entered.wait(5)
        try:
            assert client.post(path(saved) + "/archive").status_code == 409
        finally:
            release.set()
        assert future.result() == (201 if operation == "create" else 200)
    assert not details(client, saved)["request"]["archived"]


def test_archive_wins_race_and_capture_never_reaches_provider(app, client, saved, paypal, monkeypatch):
    public = public_path(saved)
    order_id = client.post(public + "/orders").json["order_id"]
    entered, release = Event(), Event()
    original = paypal.get_order

    def delayed(identifier):
        result = original(identifier)
        entered.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(paypal, "get_order", delayed)

    def archive():
        with app.test_client() as browser:
            return browser.post(path(saved) + "/archive").status_code

    def capture():
        with app.test_client() as browser:
            return browser.post(public + "/capture", json={"order_id": order_id}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(archive)
        assert entered.wait(5)
        paypal.orders[order_id]["status"] = "APPROVED"
        second = pool.submit(capture)
        release.set()
        assert first.result() == 200
        assert second.result() == 404
    assert not paypal.capture_calls


def test_additive_migration_preserves_legacy_requests_references_and_settings(app, tmp_path):
    legacy = tmp_path / "legacy.sqlite3"
    db = sqlite3.connect(legacy)
    db.executescript(SCHEMA.replace("    archived_at TEXT,\n", ""))
    timestamp = "2026-11-09T12:00:00+00:00"
    db.execute("INSERT INTO payment_requests(id,public_token,client_name,service_description,amount_cents,due_date,created_at,updated_at) VALUES(1,'legacy-token','Legacy client','Fictional service',100,'2026-11-12',?,?)", (timestamp, timestamp))
    db.execute("INSERT INTO payment_attempts(id,request_id,order_id,create_key,capture_key,state,created_at,updated_at) VALUES('legacy-attempt',1,'LEGACYORDER','create-key','capture-key','created',?,?)", (timestamp, timestamp))
    db.execute("INSERT INTO workspace_settings VALUES(1,'Legacy freelancer',?,?)", (timestamp, timestamp))
    db.commit()
    before = db.execute("SELECT * FROM payment_attempts").fetchall()
    db.close()
    for _ in range(2):
        upgraded = create_app({**app.config, "DATABASE": str(legacy)})
        with upgraded.app_context():
            assert [tuple(row) for row in get_db().execute("SELECT * FROM payment_attempts")] == before
            row = get_db().execute("SELECT * FROM payment_requests").fetchone()
            assert row["archived_at"] is None and row["created_at"] == timestamp
            assert row["public_token"] == "legacy-token" and row["status"] == "unpaid"
        assert upgraded.test_client().get("/api/settings").json["settings"]["freelancer_display_name"] == "Legacy freelancer"
