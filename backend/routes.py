from decimal import Decimal
from urllib.parse import urlsplit

from flask import Blueprint, current_app, jsonify, request

from . import ai, payments
from .db import get_db, now
from .errors import AppError
from .models import create_request, find_request, serialize, status, today
from .security import require_local_management
from .settings import get_settings, require_display_name, save_settings

api = Blueprint("api", __name__, url_prefix="/api")


@api.before_request
def boundaries():
    # Local-only management. Do NOT trust X-Forwarded-For from arbitrary callers.
    if not request.path.startswith("/api/public/"):
        require_local_management()
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("Origin")
        base = urlsplit(current_app.config["PUBLIC_BASE_URL"])
        allowed_origin = f"{base.scheme}://{base.netloc}"
        allowed_origins = {allowed_origin}
        if not request.path.startswith("/api/public/"):
            # Local management remains usable through an SSH localhost tunnel
            # even when shared payment links use an approved public origin.
            allowed_origins.add(request.host_url.rstrip("/"))
        if origin and origin not in allowed_origins:
            raise AppError("origin_forbidden", "This request origin is not allowed.", 403)


def body():
    data = request.get_json()
    if not isinstance(data, dict):
        raise AppError("validation_error", "Provide a JSON object.")
    return data


@api.get("/health")
def health():
    get_db().execute("SELECT 1")
    return jsonify({"status": "ok", "database": "ready", "sandbox": True,
                    "ai_configured": bool(current_app.config["GOOGLE_API_KEY"]),
                    "gemini_model": current_app.config["GEMINI_MODEL"],
                    "paypal_configured": payments.service().ready, "timezone": "Africa/Nairobi",
                    "today": today().isoformat(), "management": "local-only, single workspace"})


@api.get("/requests")
def list_requests():
    rows = get_db().execute("SELECT * FROM payment_requests ORDER BY created_at DESC, id DESC").fetchall()
    return jsonify({"requests": [serialize(row) for row in rows]})


@api.get("/settings")
def workspace_settings():
    return jsonify({"settings": get_settings()})


@api.put("/settings")
def update_workspace_settings():
    return jsonify({"settings": save_settings(body())})


@api.post("/requests")
def new_request():
    return jsonify({"request": serialize(create_request(body()))}), 201


@api.get("/requests/<int:request_id>")
def request_details(request_id):
    return jsonify({"request": serialize(find_request(request_id))})


@api.get("/dashboard")
def dashboard():
    rows = get_db().execute("SELECT * FROM payment_requests ORDER BY created_at DESC, id DESC").fetchall()
    return jsonify({
        "paid_cents": sum(row["amount_cents"] for row in rows if row["status"] == "paid"),
        "outstanding_cents": sum(row["amount_cents"] for row in rows if row["status"] != "paid"),
        "overdue_cents": sum(row["amount_cents"] for row in rows if status(row) == "overdue"),
        "request_count": len(rows), "recent_requests": [serialize(row) for row in rows[:5]],
    })


@api.post("/requests/<int:request_id>/message")
def message(request_id):
    row = find_request(request_id)
    if row["status"] == "paid":
        raise AppError("already_paid", "This request is paid; no payment reminder is needed.", 409)
    freelancer_display_name = require_display_name(get_settings()["freelancer_display_name"])
    text = ai.generate_message({
        "freelancer_display_name": freelancer_display_name,
        "client_name": row["client_name"], "service_description": row["service_description"],
        "amount": f'{Decimal(row["amount_cents"]) / 100:.2f}', "currency": "USD",
        "due_date": row["due_date"], "today": today().isoformat(),
        "overdue": status(row) == "overdue", "payment_status": "unpaid",
    }, current_app.config["GOOGLE_API_KEY"], current_app.config["GEMINI_MODEL"])
    return jsonify({"message": text, "source": "gemini", "model": current_app.config["GEMINI_MODEL"]})


@api.get("/public/config")
def public_config():
    return jsonify({"sandbox": True, "paypal_client_id": current_app.config["PAYPAL_CLIENT_ID"] if payments.service().ready else None,
                    "paypal_configured": payments.service().ready})


@api.get("/public/requests/<token>")
def public_details(token):
    return jsonify({"request": serialize(find_request(token=token), public=True)})


@api.post("/public/requests/<token>/orders")
def order_create(token):
    return jsonify(payments.create_order(token)), 201


@api.post("/public/requests/<token>/capture")
def order_capture(token):
    order_id = body().get("order_id")
    if not isinstance(order_id, str) or not 1 <= len(order_id) <= 64 or not order_id.isalnum():
        raise AppError("validation_error", "A valid PayPal order_id is required.")
    return jsonify(payments.capture_order(token, order_id))


@api.post("/public/requests/<token>/cancel")
def order_cancel(token):
    row = find_request(token=token)
    order_id = body().get("order_id")
    if not isinstance(order_id, str):
        raise AppError("validation_error", "An order_id is required.")
    # A browser cancellation is advisory, not proof an order cannot still capture.
    get_db().execute("UPDATE payment_attempts SET diagnostic='buyer_cancelled', updated_at=? WHERE request_id=? AND order_id=? AND state!='completed'", (now(), row["id"], order_id))
    return jsonify({"status": "cancelled", "message": "Checkout cancelled. No paid state was recorded."})
