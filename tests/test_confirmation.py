import pytest

from backend import create_app
from backend.db import get_db


def details(client, saved):
    return client.get(f'/api/requests/{saved["id"]}').json


def test_confirmation_uses_verified_capture_and_persists(app, client, saved, named, paypal, approved):
    path, order_id = approved
    assert client.get(path + "?success=true&capture_id=FAKE").json["request"]["confirmation"] is None
    result = client.post(path + "/capture", json={"order_id": order_id})
    assert result.status_code == 200
    confirmation = client.get(path).json["request"]["confirmation"]
    assert confirmation == details(client, saved)["confirmation"]
    assert confirmation == {
        "amount_cents": 5010, "currency": "USD", "sandbox": True,
        "service_description": saved["service_description"], "freelancer_display_name": named,
        "capture_reference": result.json["capture_id"], "confirmed_at": details(client, saved)["request"]["paid_at"],
    }
    reopened = create_app(dict(app.config)).test_client()
    assert reopened.get(path).json["request"]["confirmation"] == confirmation


@pytest.mark.parametrize("inconsistency", ["no_capture", "wrong_capture", "not_completed", "no_timestamp"])
def test_inconsistent_paid_data_does_not_produce_confirmation(app, client, saved, paypal, approved, inconsistency):
    path, order_id = approved
    client.post(path + "/capture", json={"order_id": order_id})
    with app.app_context():
        get_db().execute({
            "no_capture": "UPDATE payment_requests SET capture_id=NULL",
            "wrong_capture": "UPDATE payment_requests SET capture_id='UNVERIFIED'",
            "not_completed": "UPDATE payment_attempts SET state='uncertain'",
            "no_timestamp": "UPDATE payment_requests SET paid_at=NULL",
        }[inconsistency])
    assert client.get(path).json["request"]["confirmation"] is None
    assert details(client, saved)["confirmation"] is None


def test_public_confirmation_minimal_and_token_scoped(client, saved, named, paypal, approved):
    path, order_id = approved
    client.post(path + "/capture", json={"order_id": order_id})
    response = client.get(path, environ_overrides={"REMOTE_ADDR": "192.0.2.1"})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    for forbidden in ("client_name", "public_token", "payment_url", "activity", "diagnostic", "create_key", "access_token", "test-secret"):
        assert forbidden not in response.text
    assert saved["payment_url"].rsplit("/", 1)[1] not in response.text
    assert client.get("/api/public/requests/not-a-valid-token").status_code == 404
    assert client.get("/api/public/requests/").status_code == 404
    assert client.get("/api/public/requests/not-a-valid-token?success=true").status_code == 404
    assert client.get(f'/api/requests/{saved["id"]}', environ_overrides={"REMOTE_ADDR": "192.0.2.1"}).status_code == 403
    assert client.get(f'/api/public/requests/{saved["id"]}').status_code == 404


def test_confirmation_allows_unconfigured_freelancer(client, saved, paypal, approved):
    path, order_id = approved
    client.post(path + "/capture", json={"order_id": order_id})
    assert client.get(path).json["request"]["confirmation"]["freelancer_display_name"] is None


def test_pending_or_unapproved_capture_never_confirms(client, saved, paypal, approved):
    path, order_id = approved
    paypal.capture_status = "PENDING"
    assert client.post(path + "/capture", json={"order_id": order_id}).status_code == 409
    assert client.get(path).json["request"]["confirmation"] is None
    assert details(client, saved)["confirmation"] is None


def test_production_app_does_not_register_browser_fixture_controls(app, client):
    assert not any(rule.rule.startswith("/__test__/") for rule in app.url_map.iter_rules())
    assert client.post("/__test__/services", json={"enabled": True}).status_code == 405
