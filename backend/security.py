from urllib.parse import urlsplit

from flask import request

from .errors import AppError


def require_local_management():
    # Check the host as well as peer address: a loopback reverse proxy must not
    # accidentally turn a publicly hosted domain into an admin interface.
    if (request.remote_addr not in ("127.0.0.1", "::1")
            or urlsplit(request.host_url).hostname not in ("localhost", "127.0.0.1", "::1")
            or request.headers.get("X-Forwarded-For") or request.headers.get("Forwarded")):
        raise AppError("local_only", "Workspace management is available only on the local machine.", 403)
