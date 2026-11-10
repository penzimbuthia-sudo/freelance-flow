from concurrent.futures import ThreadPoolExecutor

import pytest

from backend import create_app
from backend.db import get_db
from conftest import public_path


def details(client, saved):
    return client.get(f'/api/requests/{saved["id"]}').json


def kinds(client, saved):
    return [event["kind"] for event in details(client, saved)["activity"]]


def test_events_persist_and_callbacks_are_deduplicated(app, client, saved, paypal, approved):
    path, order_id = approved
    for _ in range(2):
        assert client.post(path + "/cancel", json={"order_id": order_id}).status_code == 200
    assert details(client, saved)["request"]["status"] != "paid"
    for _ in range(3):
        assert client.post(path + "/capture", json={"order_id": order_id}).json["status"] == "paid"
    expected = ["request_created", "order_created", "attempt_cancelled", "payment_confirmed"]
    assert kinds(client, saved) == expected
    assert client.post(path + "/cancel", json={"order_id": order_id}).json["status"] == "paid"
    assert kinds(client, saved) == expected
    reopened = create_app(dict(app.config)).test_client()
    assert details(reopened, saved) == details(client, saved)
    assert len(paypal.capture_calls) == 1


def test_order_reuse_does_not_add_creation_events(client, saved, paypal):
    path = public_path(saved)
    first = client.post(path + "/orders").json["order_id"]
    for _ in range(3):
        assert client.post(path + "/orders").json["order_id"] == first
    assert kinds(client, saved) == ["request_created", "order_created"]


def test_concurrent_capture_has_one_confirmation_event(app, client, saved, paypal, approved):
    path, order_id = approved

    def capture(_):
        with app.test_client() as browser:
            return browser.post(path + "/capture", json={"order_id": order_id}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(capture, range(2))) == [200, 200]
    assert kinds(client, saved).count("payment_confirmed") == 1


def test_uncertain_capture_recovery_adds_confirmation_only_after_verification(client, saved, paypal, approved):
    path, order_id = approved
    paypal.uncertain_capture = True
    assert client.post(path + "/capture", json={"order_id": order_id}).status_code == 502
    assert "payment_confirmed" not in kinds(client, saved)
    assert details(client, saved)["guidance"]["attempt_outcome"] == "unconfirmed"
    assert client.post(path + "/capture", json={"order_id": order_id}).status_code == 200
    assert kinds(client, saved).count("payment_confirmed") == 1


@pytest.mark.parametrize("capture_status,failed", [("DECLINED", True), ("PENDING", False)])
def test_attempt_status_remains_separate(client, saved, paypal, approved, capture_status, failed):
    path, order_id = approved
    paypal.capture_status = capture_status
    assert client.post(path + "/capture", json={"order_id": order_id}).status_code == 409
    data = details(client, saved)
    assert data["request"]["status"] != "paid"
    assert ("attempt_failed" in kinds(client, saved)) == failed
    assert "payment_confirmed" not in kinds(client, saved)
    assert data["guidance"]["attempt_outcome"] == ("failed" if failed else "unconfirmed")
    if not failed:
        assert "check payment status" in data["guidance"]["next_action"]


def test_cancelled_guidance_and_unbound_cancellation(client, saved, paypal):
    path = public_path(saved)
    assert client.post(path + "/cancel", json={"order_id": "UNRELATED"}).status_code == 409
    assert kinds(client, saved) == ["request_created"]
    order_id = client.post(path + "/orders").json["order_id"]
    assert client.post(path + "/cancel", json={"order_id": order_id}).status_code == 200
    facts = details(client, saved)["guidance"]
    assert facts["attempt_outcome"] == "cancelled"
    assert "browser-reported" in facts["explanation"]
    assert facts["payment_status"] == "unpaid"
    assert "Retry sandbox checkout" in facts["next_action"]


def test_unavailable_attempt_has_current_event(client, saved, paypal):
    path = public_path(saved)
    order_id = client.post(path + "/orders").json["order_id"]
    paypal.orders[order_id]["status"] = "VOIDED"
    assert client.post(path + "/orders").status_code == 201
    assert kinds(client, saved) == ["request_created", "order_created", "order_unavailable", "order_created"]


def test_additive_migration_does_not_invent_attempt_history(app, client, saved, paypal, approved):
    path, order_id = approved
    client.post(path + "/cancel", json={"order_id": order_id})
    with app.app_context():
        get_db().execute("DROP TABLE payment_events")
    upgraded = create_app(dict(app.config))
    data = details(upgraded.test_client(), saved)
    assert [event["kind"] for event in data["activity"]] == ["request_created"]
    assert data["activity"][0]["occurred_at"] == saved["created_at"]
    assert data["guidance"]["attempt_outcome"] == "cancelled"
    with upgraded.app_context():
        assert get_db().execute("SELECT order_id FROM payment_attempts").fetchone()["order_id"] == order_id
        assert get_db().execute("SELECT COUNT(*) FROM payment_events").fetchone()[0] == 0


def test_legacy_paid_event_uses_only_verified_paid_timestamp(app, client, saved, paypal, approved):
    path, order_id = approved
    assert client.post(path + "/capture", json={"order_id": order_id}).status_code == 200
    with app.app_context():
        get_db().execute("DROP TABLE payment_events")
    upgraded = create_app(dict(app.config))
    data = details(upgraded.test_client(), saved)
    assert [event["kind"] for event in data["activity"]] == ["request_created", "payment_confirmed"]
    assert data["activity"][-1]["occurred_at"] == data["request"]["paid_at"]


def test_activity_minimal_and_management_only(client, saved, paypal, approved):
    data = details(client, saved)
    for event in data["activity"]:
        assert set(event) == {"kind", "label", "occurred_at"}
    assert "activity" not in client.get(public_path(saved)).json["request"]
    assert client.get(f'/api/requests/{saved["id"]}', environ_overrides={"REMOTE_ADDR": "192.0.2.1"}).status_code == 403
