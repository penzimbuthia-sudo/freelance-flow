import re
import time
from unittest.mock import MagicMock

import pytest
from werkzeug.security import generate_password_hash

from backend import create_app
from backend.db import get_db

ORIGIN = "https://workspace.example"
PASSWORD = "fictional-test-password-not-a-real-secret"


@pytest.fixture(scope="module")
def password_hash():
    return generate_password_hash(PASSWORD)


@pytest.fixture
def auth_config(tmp_path, password_hash):
    return {
        "TESTING": True, "HOSTED": False, "AUTH_REQUIRED": True,
        "DATABASE": str(tmp_path / "auth.sqlite3"), "DATABASE_URL": "",
        "SECRET_KEY": "fictional-session-key-for-isolated-tests-only",
        "ADMIN_USERNAME": "demo-admin", "ADMIN_PASSWORD_HASH": password_hash,
        "PUBLIC_BASE_URL": ORIGIN, "TRUSTED_HOSTS": ["workspace.example"],
        "GOOGLE_API_KEY": "", "PAYPAL_CLIENT_ID": "", "PAYPAL_CLIENT_SECRET": "", "PAYPAL_MERCHANT_ID": "",
    }


@pytest.fixture
def auth_app(auth_config, tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>Fictional production build</title>")
    (dist / "assets").mkdir()
    (dist / "assets" / "app.js").write_text("// public bundle")
    monkeypatch.setattr("backend.ROOT", tmp_path)
    return create_app(auth_config)


def get(client, path):
    return client.get(path, base_url=ORIGIN)


def login(client, password=PASSWORD, destination="/"):
    page = get(client, "/login?next=" + destination)
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    return client.post("/login", base_url=ORIGIN, data={
        "username": "demo-admin", "password": password, "csrf_token": token, "next": destination,
    }, headers={"Origin": ORIGIN})


def mutate(client, path, method="POST", data=None, **kwargs):
    token = get(client, "/api/auth/session").json["csrf_token"]
    return client.open(path, method=method, base_url=ORIGIN, json=data or {},
                       headers={"X-CSRF-Token": token, "Origin": ORIGIN}, **kwargs)


@pytest.mark.parametrize("path", ["/", "/requests", "/requests/new", "/requests/1", "/index.html"])
def test_management_pages_require_server_login(auth_app, path):
    response = get(auth_app.test_client(), path)
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login?")
    assert "Fictional production build" not in response.text


@pytest.mark.parametrize("path", ["/api/requests", "/api/dashboard", "/api/settings", "/api/health", "/api/auth/session"])
def test_management_api_is_protected_even_from_loopback(auth_app, path):
    response = get(auth_app.test_client(), path)
    assert response.status_code == 401
    assert response.json["error"]["code"] == "authentication_required"
    assert response.headers["Cache-Control"] == "no-store"


def test_login_cookie_routes_public_pages_and_csrf(auth_app):
    client = auth_app.test_client()
    assert get(client, "/pay/fictional-token").status_code == 200
    assert get(client, "/api/public/config").json["sandbox"] is True
    assert get(client, "/assets/app.js").status_code == 200
    assert get(client, "/auth-assets/login.css").status_code == 200
    response = login(client, destination="/requests/new")
    assert response.status_code == 303 and response.headers["Location"] == "/requests/new"
    cookie = response.headers["Set-Cookie"]
    assert cookie.startswith("__Host-ff_session=")
    assert all(flag in cookie for flag in ("Secure", "HttpOnly", "SameSite=Lax", "Path=/"))
    assert "Domain=" not in cookie and PASSWORD not in cookie
    assert get(client, "/requests/1").status_code == 200
    assert get(client, "/index.html").status_code == 200
    assert get(client, "/api/dashboard").status_code == 200
    assert client.post("/api/requests", base_url=ORIGIN, json={}).status_code == 403
    assert client.put("/api/settings", base_url=ORIGIN, json={}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.put("/api/settings", base_url=ORIGIN, json={}, headers={"X-CSRF-Token": "é"}).status_code == 403
    created = mutate(client, "/api/requests", data={
        "client_name": "Fictional hosted check", "service_description": "Not a real invoice",
        "amount": "50.10", "due_date": "2099-12-31",
    })
    assert created.status_code == 201
    row = created.json["request"]
    assert row["payment_url"].startswith(ORIGIN + "/pay/")
    anonymous = auth_app.test_client()
    public = get(anonymous, "/api/public/requests/" + row["payment_url"].rsplit("/", 1)[1])
    assert public.status_code == 200 and "client_name" not in public.json["request"]


def test_login_csrf_origin_and_open_redirect_rejection(auth_app):
    client = auth_app.test_client()
    assert client.post("/login", base_url=ORIGIN, data={"username": "demo-admin", "password": PASSWORD}).status_code == 403
    page = get(client, "/login")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    assert client.post("/login", base_url=ORIGIN, data={"csrf_token": token}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert login(client, password="incorrect").status_code == 401
    for destination in ("//evil.example", "https://evil.example", "/\\evil.example", "/login", "/api/settings"):
        response = login(client, destination=destination)
        assert response.headers["Location"] == "/"
    info = get(client, "/api/auth/session").json
    assert client.put("/api/settings", base_url=ORIGIN, json={}, headers={"Origin": "https://evil.example", "X-CSRF-Token": info["csrf_token"]}).status_code == 403


def test_logout_revokes_copied_cookie_and_expiry(auth_app):
    client = auth_app.test_client()
    login(client)
    copied = client.get_cookie("__Host-ff_session", domain="workspace.example").value
    token = get(client, "/api/auth/session").json["csrf_token"]
    assert client.post("/api/auth/logout", base_url=ORIGIN, json={}).status_code == 403
    assert mutate(client, "/api/auth/logout").status_code == 200
    assert get(client, "/api/settings").status_code == 401
    replay = auth_app.test_client()
    replay.set_cookie("__Host-ff_session", copied, domain="workspace.example")
    assert get(replay, "/api/settings").status_code == 401
    login(client)
    with auth_app.app_context():
        get_db().execute("UPDATE management_sessions SET expires_at=?", (int(time.time()) - 1,))
    assert get(client, "/api/requests").status_code == 401
    assert token  # CSRF was issued only to an authenticated session.


def test_session_survives_app_restart_but_password_change_revokes(auth_app, auth_config):
    client = auth_app.test_client()
    login(client)
    cookie = client.get_cookie("__Host-ff_session", domain="workspace.example").value
    restarted = create_app(dict(auth_config)).test_client()
    restarted.set_cookie("__Host-ff_session", cookie, domain="workspace.example")
    assert get(restarted, "/api/settings").status_code == 200
    changed = create_app({**auth_config, "ADMIN_PASSWORD_HASH": generate_password_hash("different fictional password")}).test_client()
    changed.set_cookie("__Host-ff_session", cookie, domain="workspace.example")
    assert get(changed, "/api/settings").status_code == 401


def test_durable_global_login_and_ai_bounds(auth_app, auth_config, monkeypatch):
    client = auth_app.test_client()
    assert login(client).status_code == 303
    for _ in range(6):
        # No Gemini call: quota also bounds errors and nonexistent requests.
        assert mutate(client, "/api/requests/999/message").status_code == 404
    limited = mutate(client, "/api/requests/999/message")
    assert limited.status_code == 429 and limited.headers["Retry-After"] == "60"
    for _ in range(9):
        assert login(auth_app.test_client(), password="incorrect").status_code == 401
    monkeypatch.setattr("backend.auth.check_password_hash", MagicMock(side_effect=AssertionError("hash must not run beyond limit")))
    blocked = login(create_app(dict(auth_config)).test_client(), password="incorrect")
    assert blocked.status_code == 429 and blocked.headers["Retry-After"] == "900"


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@pytest.mark.parametrize("path", ["/api", "/api/missing", "/api/public/missing"])
def test_unknown_api_never_falls_through_to_spa(auth_app, method, path):
    response = auth_app.test_client().open(path, method=method, base_url=ORIGIN)
    assert response.status_code == 404 and response.is_json


def test_missing_assets_and_liveness(auth_app):
    client = auth_app.test_client()
    assert get(client, "/assets/missing.js").status_code == 404
    assert get(client, "/healthz").json == {"status": "ok"}
    assert get(client, "/login").headers["Content-Security-Policy"].startswith("default-src 'none'")


@pytest.mark.parametrize("changes", [
    {"DATABASE_URL": ""}, {"DATABASE_URL": "sqlite:///ephemeral.db"},
    {"PUBLIC_BASE_URL": "http://workspace.example"}, {"PUBLIC_BASE_URL": "https://localhost"},
    {"PUBLIC_BASE_URL": "https://workspace.example/path"},
    {"SECRET_KEY": "short"}, {"ADMIN_USERNAME": ""}, {"ADMIN_PASSWORD_HASH": "plaintext"},
    {"TRUSTED_HOSTS": ["*"]}, {"TRUSTED_HOSTS": ["other.example"]},
])
def test_hosted_config_fails_before_opening_database(auth_config, monkeypatch, changes):
    init = MagicMock()
    monkeypatch.setattr("backend.init_db", init)
    config = {**auth_config, "HOSTED": True, "DATABASE_URL": "postgresql://fictional.invalid/demo?sslmode=require", **changes}
    with pytest.raises(ValueError):
        create_app(config)
    init.assert_not_called()
