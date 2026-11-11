from urllib.parse import urlsplit

import hashlib
import hmac
import secrets
import time

from flask import current_app, g, request, session

from .db import get_db, transaction
from .errors import AppError


def require_local_management():
    # Check the host as well as peer address: a loopback reverse proxy must not
    # accidentally turn a publicly hosted domain into an admin interface.
    if (request.remote_addr not in ("127.0.0.1", "::1")
            or urlsplit(request.host_url).hostname not in ("localhost", "127.0.0.1", "::1")
            or request.headers.get("X-Forwarded-For") or request.headers.get("Forwarded")):
        raise AppError("local_only", "Workspace management is available only on the local machine.", 403)


def credential_version():
    config = current_app.config
    return hashlib.sha256((config["ADMIN_USERNAME"] + "\0" + config["ADMIN_PASSWORD_HASH"]).encode()).hexdigest()


def session_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def authenticated():
    if "management_authenticated" not in g:
        token = session.get("auth_token")
        row = None
        if isinstance(token, str) and len(token) <= 128:
            row = get_db().execute("SELECT credential_version, expires_at FROM management_sessions WHERE token_hash=?", (session_digest(token),)).fetchone()
        g.management_authenticated = bool(row and row["expires_at"] > int(time.time())
                                          and hmac.compare_digest(row["credential_version"], credential_version()))
        if not g.management_authenticated and token:
            session.clear()
    return g.management_authenticated


def require_management():
    if current_app.config["AUTH_REQUIRED"]:
        if not authenticated():
            raise AppError("authentication_required", "Sign in to manage this workspace.", 401)
    else:
        require_local_management()


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def require_csrf(value=None):
    supplied = value if value is not None else request.headers.get("X-CSRF-Token", "")
    expected = session.get("csrf_token", "")
    if (not isinstance(supplied, str) or not expected or len(supplied) > 128
            or not hmac.compare_digest(supplied.encode(), expected.encode())):
        raise AppError("csrf_failed", "Your session changed. Refresh the page and try again.", 403)


def require_allowed_origin():
    origin = request.headers.get("Origin")
    # Browser-visible origin, not request.scheme: Render forwards HTTPS over HTTP.
    # Never extend hosted trust using Host, X-Forwarded-* or Forwarded headers.
    allowed = {current_app.config["PUBLIC_BASE_URL"]}
    if not current_app.config["HOSTED"]:
        # Preserve approved localhost/SSH management of public token links.
        if not request.path.startswith("/api/public/"):
            allowed.add(request.host_url.rstrip("/"))
    if origin and origin not in allowed:
        raise AppError("origin_forbidden", "This request origin is not allowed.", 403)


def rate_limit(bucket, maximum, window):
    """Fixed global buckets: durable across restarts, no spoofable proxy IP keys.

    Single-workspace quotas intentionally favor bounded cost over availability.
    Rejections commit the counter before raising; expired windows are reused.
    """
    timestamp = int(time.time())
    blocked = False
    with transaction() as db:
        row = db.execute("SELECT starts_at, attempts FROM request_limits WHERE bucket=?", (bucket,)).fetchone()
        if not row or timestamp - row["starts_at"] >= window:
            db.execute("INSERT INTO request_limits (bucket, starts_at, attempts) VALUES (?, ?, 1) ON CONFLICT(bucket) DO UPDATE SET starts_at=excluded.starts_at, attempts=1", (bucket, timestamp))
        elif row["attempts"] >= maximum:
            blocked = True
        else:
            db.execute("UPDATE request_limits SET attempts=attempts+1 WHERE bucket=?", (bucket,))
    if blocked:
        raise AppError("request_rate_limited", "Too many requests. Please wait and try again.", 429, {"retry_after": window})
