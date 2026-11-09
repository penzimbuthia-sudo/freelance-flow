import pytest

from backend import create_app
from backend.db import get_db
from conftest import public_path


def test_default_display_name_is_unset(client):
    assert client.get("/api/settings").json == {"settings": {"freelancer_display_name": ""}}


def test_name_save_update_and_reopen(app, client):
    for name in ["  Taylor Demo  ", "Amélie O’Demo"]:
        response = client.put("/api/settings", json={"freelancer_display_name": name})
        assert response.status_code == 200
        assert response.json["settings"]["freelancer_display_name"] == name.strip()
        assert client.get("/api/settings").json == response.json
        reopened = create_app(dict(app.config)).test_client()
        assert reopened.get("/api/settings").json == response.json
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM workspace_settings").fetchone()[0] == 1
        assert get_db().execute("SELECT created_at, updated_at FROM workspace_settings").fetchone()["updated_at"]


@pytest.mark.parametrize("value", [None, 123, True, [], {}, "x" * 121, "Name\nOther", "Name\r", "Name\tOther", "Name\x00", "Name\u2028Other", "Name\u200bOther"])
def test_display_name_validation_preserves_saved_name(client, named, value):
    response = client.put("/api/settings", json={"freelancer_display_name": value})
    assert response.status_code == 400
    assert response.json["error"]["code"] == "validation_error"
    assert client.get("/api/settings").json["settings"]["freelancer_display_name"] == named


def test_clear_name_and_missing_payload(client, named):
    assert client.put("/api/settings", json={}).status_code == 400
    assert client.put("/api/settings", json=[]).status_code == 400
    assert client.put("/api/settings", json={"freelancer_display_name": "  "}).json["settings"]["freelancer_display_name"] == ""


def test_settings_are_local_only_and_not_public(client, saved, named):
    assert client.get("/api/settings", environ_overrides={"REMOTE_ADDR": "192.0.2.1"}).status_code == 403
    assert client.put("/api/settings", json={"freelancer_display_name": "Changed"}, environ_overrides={"REMOTE_ADDR": "192.0.2.1"}).status_code == 403
    assert client.put("/api/settings", json={"freelancer_display_name": "Changed"}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/public/settings").status_code == 404
    assert named not in client.get(public_path(saved)).text
    assert named not in client.get("/api/public/config").text


def test_additive_initialization_preserves_existing_requests_and_attempts(app, client, saved, approved):
    _, order_id = approved
    with app.app_context():
        # Simulate a pre-setting database using only this isolated test database.
        get_db().execute("DROP TABLE workspace_settings")
    upgraded = create_app(dict(app.config))
    browser = upgraded.test_client()
    assert browser.get("/api/settings").json["settings"]["freelancer_display_name"] == ""
    assert browser.get(f'/api/requests/{saved["id"]}').json["request"] == saved
    with upgraded.app_context():
        assert get_db().execute("SELECT order_id FROM payment_attempts").fetchone()["order_id"] == order_id
