"""Real Gunicorn + built React smoke. Default tests use disposable SQLite only.

run_smoke(neon_url=...) is explicitly invoked separately for genuine Neon checks;
it reads the existing labelled fictional request, never creates/imports app data.
"""

from http.cookies import SimpleCookie
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time

import pytest
import requests
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parent.parent
ORIGIN = "https://render-smoke.example"


def run_smoke(neon_url="", existing_id=None):
    with tempfile.TemporaryDirectory(prefix="ff-gunicorn-", dir="/tmp/opencode") as directory:
        directory = Path(directory)
        selected_env = directory / ".env.smoke"
        selected_env.write_text("")
        selected_env.chmod(0o600)
        password = secrets.token_urlsafe(32)
        env = os.environ.copy()
        env.update(
            APP_ENV="production" if neon_url else "local", RENDER="false",
            FF_ENV_FILE=str(selected_env), FLASK_SKIP_DOTENV="1",
            DATABASE_URL=neon_url, DATABASE_PATH=str(directory / "isolated.sqlite3"),
            PUBLIC_BASE_URL=ORIGIN, APP_HOSTS="render-smoke.example",
            SECRET_KEY=secrets.token_urlsafe(48), ADMIN_USERNAME="fictional-smoke-admin",
            ADMIN_PASSWORD_HASH=generate_password_hash(password),
            GOOGLE_API_KEY="", GEMINI_API_KEY="", PAYPAL_CLIENT_ID="", PAYPAL_CLIENT_SECRET="", PAYPAL_MERCHANT_ID="",
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env["PORT"] = str(port)
        base = f"http://127.0.0.1:{port}"
        process = None
        cookie = ""

        def call(path, method="GET", *, data=None, payload=None, headers=None, anonymous=False):
            # Render terminates HTTPS; test the HTTP upstream with the public Host.
            # Secure cookies are transported explicitly only over our loopback test.
            combined = {"Host": "render-smoke.example", **(headers or {})}
            if cookie and not anonymous:
                combined["Cookie"] = cookie
            return requests.request(method, base + path, data=data, json=payload,
                                    headers=combined, allow_redirects=False, timeout=30)

        def start():
            child = subprocess.Popen(
                [sys.executable, "-m", "gunicorn", "--config", "gunicorn.conf.py", "wsgi:app"],
                cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
            )
            try:
                for _ in range(180):
                    assert child.poll() is None, "Gunicorn worker exited; output suppressed"
                    try:
                        if call("/healthz", anonymous=True).status_code == 200:
                            return child
                    except requests.RequestException:
                        pass
                    time.sleep(0.2)
                raise AssertionError("Gunicorn did not become ready")
            except BaseException:
                child.terminate()
                child.wait(timeout=30)
                raise

        def stop():
            nonlocal process
            if process:
                process.terminate()
                try:
                    process.wait(timeout=100)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)  # Only this test's process group.
                    process.wait(timeout=10)
                    raise
                process = None

        try:
            process = start()
            for path in ("/", "/requests/new", "/requests/1", "/index.html"):
                response = call(path, anonymous=True)
                assert response.status_code == 302 and response.headers["Location"].startswith("/login?")
            assert call("/api/requests", anonymous=True).status_code == 401
            assert call("/api/health", anonymous=True).status_code == 401
            for method in ("GET", "POST"):
                for path in ("/api", "/api/missing", "/api/public/missing"):
                    response = call(path, method, anonymous=True)
                    assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"
            assert call("/api/public/config", anonymous=True).json()["sandbox"] is True
            missing_csrf = call("/login", "POST", data={"username": "fictional-smoke-admin", "password": password})
            assert missing_csrf.status_code == 403
            assert missing_csrf.headers["Content-Type"].startswith("text/html")
            assert 'role="alert"' in missing_csrf.text and password not in missing_csrf.text
            page = call("/login")
            csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
            login_cookie = SimpleCookie(page.headers["Set-Cookie"])["__Host-ff_session"]
            cookie = "__Host-ff_session=" + login_cookie.value
            foreign = call("/login", "POST", data={"username": "fictional-smoke-admin", "password": password, "csrf_token": csrf}, headers={"Origin": "https://foreign.example"})
            assert foreign.status_code == 403 and "configured public origin" in foreign.text
            assert 'role="alert"' in foreign.text and password not in foreign.text
            response = call("/login", "POST", data={"username": "fictional-smoke-admin", "password": password, "csrf_token": csrf}, headers={"Origin": ORIGIN})
            assert response.status_code == 303
            assert all(flag in response.headers["Set-Cookie"] for flag in ("Secure", "HttpOnly", "SameSite=Lax"))
            authenticated_cookie = SimpleCookie(response.headers["Set-Cookie"])["__Host-ff_session"]
            cookie = "__Host-ff_session=" + authenticated_cookie.value
            info = call("/api/auth/session").json()
            assert info["auth_enabled"] is True and info["csrf_token"] != csrf
            csrf = info["csrf_token"]
            headers = {"X-CSRF-Token": csrf, "Origin": ORIGIN}
            assert call("/api/settings", "PUT", payload={}).status_code == 403
            assert call("/api/settings", "PUT", payload={}, headers={**headers, "Origin": "https://evil.example"}).status_code == 403

            if existing_id is None:
                response = call("/api/requests", "POST", headers=headers, payload={
                    "client_name": "FICTIONAL GUNICORN CHECK", "service_description": "TEST ONLY - not a real invoice",
                    "amount": "50.10", "due_date": "2099-12-31",
                })
                assert response.status_code == 201
                row = response.json()["request"]
                existing_id = row["id"]
            detail_path = f"/api/requests/{existing_id}"
            details = call(detail_path).json()
            row = details["request"]
            assert row["client_name"].startswith("FICTIONAL ") and row["amount_cents"] == 5010
            assert row["payment_url"].startswith(ORIGIN + "/pay/")
            token = row["payment_url"].rsplit("/", 1)[1]
            for path in ("/", "/requests/new", f"/requests/{existing_id}", "/index.html"):
                response = call(path)
                assert response.status_code == 200 and '<div id="root">' in response.text
            landing = call("/pay/" + token, anonymous=True)
            assert landing.status_code == 200 and '<div id="root">' in landing.text
            public = call("/api/public/requests/" + token, anonymous=True)
            assert public.status_code == (404 if row["archived"] else 200)
            if public.status_code == 200:
                assert "client_name" not in public.json()["request"]
            asset = re.search(r'src="(/assets/[^\"]+\.js)"', landing.text).group(1)
            assert call(asset, anonymous=True).status_code == 200
            assert call("/assets/not-a-file.js", anonymous=True).status_code == 404
            settings = call("/api/settings").json()
            old_pid = process.pid
            stop()
            process = start()
            assert process.pid != old_pid
            assert call("/api/auth/session").json()["csrf_token"] == csrf
            assert call(detail_path).json() == details
            assert call("/api/settings").json() == settings
            assert call("/api/auth/logout", "POST", payload={}, headers=headers).json()["logged_out"]
            # Replay the pre-logout cookie: server-side revocation must reject it.
            assert call("/api/requests").status_code == 401
            return {"server": "Gunicorn", "storage": "Neon" if neon_url else "disposable SQLite",
                    "direct_routes": "PASS", "authentication_csrf_logout": "PASS",
                    "public_token_pages": "PASS", "api_json_errors": "PASS",
                    "restart_request_settings_timeline_session_persistence": "PASS"}
        finally:
            stop()


@pytest.mark.skipif(not (ROOT / "dist/index.html").exists(), reason="Run npm run build before production-server smoke")
def test_real_gunicorn_production_build():
    assert run_smoke()["storage"] == "disposable SQLite"
