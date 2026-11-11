import re
import time
from http.cookies import SimpleCookie
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


def test_native_login_policy_preserves_origin_without_exposing_payment_referrers(auth_app):
    client = auth_app.test_client()
    assert get(client, "/login").headers["Referrer-Policy"] == "same-origin"
    failure = client.post("/login", base_url=ORIGIN, data={})
    assert failure.status_code == 403
    assert failure.headers["Referrer-Policy"] == "same-origin"
    assert get(client, "/pay/fictional-token").headers["Referrer-Policy"] == "no-referrer"
    assert get(client, "/api/public/config").headers["Referrer-Policy"] == "no-referrer"
    assert get(client, "/api/auth/session").headers["Referrer-Policy"] == "no-referrer"


@pytest.mark.parametrize("path", ["/", "/login", "/pay/fictional-token", "/api/public/config", "/api/settings", "/healthz"])
def test_microphone_allowed_only_for_self_with_other_security_headers_preserved(auth_app, path):
    auth_app.config["HOSTED"] = True
    response = get(auth_app.test_client(), path)
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(self), geolocation=()"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == ("same-origin" if path == "/login" else "no-referrer")
    if path == "/login":
        assert response.headers["Content-Security-Policy"] == "default-src 'none'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    if path == "/api/settings":
        assert response.status_code == 401


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


RENDER_HOST = "freelance-flow-mapt.onrender.com"
RENDER_ORIGIN = f"https://{RENDER_HOST}"


@pytest.fixture
def render_proxy_app(auth_app):
    # Initialize only the isolated SQLite fixture, then exercise hosted request
    # boundaries. Production's actual PostgreSQL startup requirement is unchanged.
    auth_app.config.update(HOSTED=True, PUBLIC_BASE_URL=RENDER_ORIGIN, TRUSTED_HOSTS=[RENDER_HOST])
    return auth_app


def proxy_login_form(app):
    client = app.test_client(use_cookies=False)
    # Render terminates browser HTTPS; Gunicorn deliberately sees plain HTTP.
    response = client.get("/login", base_url=f"http://{RENDER_HOST}")
    token = re.search(r'name="csrf_token" value="([^"]+)"', response.text).group(1)
    cookie = SimpleCookie(response.headers["Set-Cookie"])["__Host-ff_session"].value
    return client, token, f"__Host-ff_session={cookie}"


def test_https_origin_login_accepted_over_http_proxy_without_trusting_headers(render_proxy_app):
    client, token, cookie = proxy_login_form(render_proxy_app)
    # No X-Forwarded-Proto is required for the configured HTTPS origin to match.
    response = client.post("/login", base_url=f"http://{RENDER_HOST}", headers={
        "Origin": RENDER_ORIGIN, "Cookie": cookie,
    }, data={"username": "demo-admin", "password": PASSWORD, "csrf_token": token, "next": "/requests"})
    assert response.status_code == 303 and response.headers["Location"] == "/requests"
    assert all(flag in response.headers["Set-Cookie"] for flag in ("Secure", "HttpOnly", "SameSite=Lax"))
    authenticated_cookie = SimpleCookie(response.headers["Set-Cookie"])["__Host-ff_session"].value
    protected = client.get("/api/settings", base_url=f"http://{RENDER_HOST}", headers={"Cookie": f"__Host-ff_session={authenticated_cookie}"})
    assert protected.status_code == 200


@pytest.mark.parametrize("origin", ["https://foreign.example", "null", f"http://{RENDER_HOST}"])
def test_foreign_origin_login_stays_blocked_despite_spoofed_proxy_headers(render_proxy_app, monkeypatch, origin):
    client, token, cookie = proxy_login_form(render_proxy_app)
    check = MagicMock(side_effect=AssertionError("Password checking must not be reached"))
    monkeypatch.setattr("backend.auth.check_password_hash", check)
    response = client.post("/login", base_url=f"http://{RENDER_HOST}", headers={
        "Origin": origin, "Cookie": cookie, "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": RENDER_HOST, "Forwarded": f"proto=https;host={RENDER_HOST}",
    }, data={"username": "demo-admin", "password": PASSWORD, "csrf_token": token})
    assert response.status_code == 403 and response.mimetype == "text/html"
    assert 'role="alert"' in response.text and "configured public origin" in response.text
    assert PASSWORD not in response.text and "demo-admin" not in response.text
    assert client.get("/api/settings", base_url=f"http://{RENDER_HOST}", headers={"Cookie": cookie}).status_code == 401
    check.assert_not_called()


def test_mismatched_public_base_url_not_overridden_by_host_or_forwarded_proto(render_proxy_app, monkeypatch):
    client, token, cookie = proxy_login_form(render_proxy_app)
    render_proxy_app.config["PUBLIC_BASE_URL"] = "https://other-workspace.example"
    check = MagicMock(side_effect=AssertionError("Password checking must not be reached"))
    monkeypatch.setattr("backend.auth.check_password_hash", check)
    response = client.post("/login", base_url=f"http://{RENDER_HOST}", headers={
        "Cookie": cookie, "Origin": RENDER_ORIGIN, "X-Forwarded-Proto": "https",
    }, data={"username": "demo-admin", "password": PASSWORD, "csrf_token": token})
    assert response.status_code == 403 and "PUBLIC_BASE_URL" in response.text
    check.assert_not_called()


@pytest.mark.parametrize("supplied", [None, "wrong-token"])
def test_same_origin_proxy_login_still_requires_csrf_with_readable_errors(render_proxy_app, monkeypatch, supplied):
    client, token, cookie = proxy_login_form(render_proxy_app)
    check = MagicMock(side_effect=AssertionError("Password checking must not be reached"))
    monkeypatch.setattr("backend.auth.check_password_hash", check)
    form = {"username": "demo-admin", "password": PASSWORD, "next": "/requests/new"}
    if supplied is not None:
        form["csrf_token"] = supplied
    response = client.post("/login", base_url=f"http://{RENDER_HOST}", headers={"Origin": RENDER_ORIGIN, "Cookie": cookie}, data=form)
    assert response.status_code == 403 and response.mimetype == "text/html"
    assert "secure cookies" in response.text and 'name="csrf_token"' in response.text
    assert 'name="next" value="/requests/new"' in response.text
    assert PASSWORD not in response.text and "demo-admin" not in response.text
    check.assert_not_called()


def test_login_api_errors_remain_json_and_rate_limits_remain_effective(render_proxy_app):
    client, token, cookie = proxy_login_form(render_proxy_app)
    response = client.post("/login", base_url=f"http://{RENDER_HOST}", headers={"Origin": "https://foreign.example", "Cookie": cookie}, json={})
    assert response.status_code == 403 and response.json["error"]["code"] == "origin_forbidden"
    with render_proxy_app.app_context():
        get_db().execute("INSERT INTO request_limits (bucket, starts_at, attempts) VALUES ('login', ?, 10)", (int(time.time()),))
    blocked = client.post("/login", base_url=f"http://{RENDER_HOST}", headers={"Origin": RENDER_ORIGIN, "Cookie": cookie}, data={
        "username": "demo-admin", "password": PASSWORD, "csrf_token": token,
    })
    assert blocked.status_code == 429 and blocked.headers["Retry-After"] == "900"
    assert blocked.mimetype == "text/html" and "Wait 15 minutes" in blocked.text
    assert PASSWORD not in blocked.text


def test_same_origin_proxy_login_still_checks_password(render_proxy_app):
    client, token, cookie = proxy_login_form(render_proxy_app)
    response = client.post("/login", base_url=f"http://{RENDER_HOST}", headers={"Origin": RENDER_ORIGIN, "Cookie": cookie}, data={
        "username": "demo-admin", "password": "incorrect-fictional-password", "csrf_token": token,
    })
    assert response.status_code == 401 and response.mimetype == "text/html"
    assert 'role="alert"' in response.text and "Sign-in details are incorrect." in response.text
    assert "incorrect-fictional-password" not in response.text
    assert client.get("/api/settings", base_url=f"http://{RENDER_HOST}", headers={"Cookie": cookie}).status_code == 401
    with render_proxy_app.app_context():
        assert get_db().execute("SELECT COUNT(*) AS count FROM management_sessions").fetchone()["count"] == 0
