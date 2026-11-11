"""One workspace administrator, revocable server-side sessions; no sign-up."""

from datetime import timedelta
import hmac
import secrets
import time
from urllib.parse import urlsplit

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, send_from_directory
from werkzeug.security import check_password_hash

from .db import now, transaction
from .errors import AppError
from .security import credential_version, csrf_token, rate_limit, require_allowed_origin, require_csrf, require_management, session_digest

auth = Blueprint("auth", __name__)
SESSION_SECONDS = 8 * 3600


def configure_sessions(app):
    app.config.update(
        SESSION_COOKIE_NAME="__Host-ff_session", SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_PATH="/",
        SESSION_COOKIE_DOMAIN=None, SESSION_REFRESH_EACH_REQUEST=False,
        PERMANENT_SESSION_LIFETIME=timedelta(seconds=SESSION_SECONDS),
    )


def safe_next(value):
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value or any(ord(char) < 32 for char in value):
        return "/"
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.path.startswith(("/login", "/api")):
        return "/"
    return value


def render_login_error(error):
    # A normal HTML form must not strand the user on an API-style JSON error.
    # Keep the original HTTP status and all checks; never echo submitted credentials.
    messages = {
        "origin_forbidden": "Sign-in was blocked because this page's address does not match the configured public origin. Ask the workspace owner to check PUBLIC_BASE_URL, then reload this page.",
        "csrf_failed": "Your sign-in page expired or secure cookies are unavailable. Reload the sign-in page and try again.",
        "request_rate_limited": "Too many sign-in attempts. Wait 15 minutes before trying again.",
    }
    return render_template(
        "login.html", csrf=csrf_token(), destination=safe_next(request.values.get("next")),
        error=messages.get(error.code, error.message),
    )


@auth.route("/login", methods=["GET", "POST"])
def login():
    if not current_app.config["AUTH_REQUIRED"]:
        require_management()
        return redirect("/")
    destination = safe_next(request.values.get("next"))
    error, status = None, 200
    if request.method == "POST":
        require_allowed_origin()
        require_csrf(request.form.get("csrf_token", ""))
        rate_limit("login", 10, 900)
        username, password = request.form.get("username", ""), request.form.get("password", "")
        if len(username) > 120 or len(password) > 1024:
            raise AppError("invalid_credentials", "Sign-in details are incorrect.", 401)
        valid_password = check_password_hash(current_app.config["ADMIN_PASSWORD_HASH"], password)
        if hmac.compare_digest(username.encode(), current_app.config["ADMIN_USERNAME"].encode()) and valid_password:
            old_token = session.get("auth_token")
            token = secrets.token_urlsafe(32)
            timestamp = int(time.time())
            with transaction() as db:
                # Only expired authentication metadata is cleaned up, never app data.
                db.execute("DELETE FROM management_sessions WHERE expires_at<=?", (timestamp,))
                if isinstance(old_token, str):
                    db.execute("DELETE FROM management_sessions WHERE token_hash=?", (session_digest(old_token),))
                db.execute("INSERT INTO management_sessions (token_hash, credential_version, expires_at, created_at) VALUES (?, ?, ?, ?)", (session_digest(token), credential_version(), timestamp + SESSION_SECONDS, now()))
            session.clear()
            session.permanent = True
            session["auth_token"] = token
            csrf_token()  # Rotate both authentication and CSRF state on login.
            return redirect(destination, code=303)
        error, status = "Sign-in details are incorrect.", 401
    return render_template("login.html", csrf=csrf_token(), destination=destination, error=error), status


@auth.get("/auth-assets/login.css")
def login_css():
    return send_from_directory(current_app.root_path + "/static", "login.css")


@auth.get("/api/auth/session")
def session_info():
    require_management()
    enabled = current_app.config["AUTH_REQUIRED"]
    return jsonify(authenticated=True, auth_enabled=enabled, csrf_token=csrf_token() if enabled else None)


@auth.post("/api/auth/logout")
def logout():
    require_management()
    require_allowed_origin()
    if current_app.config["AUTH_REQUIRED"]:
        require_csrf()
        with transaction() as db:
            db.execute("DELETE FROM management_sessions WHERE token_hash=?", (session_digest(session["auth_token"]),))
        session.clear()
    return jsonify(logged_out=True)
