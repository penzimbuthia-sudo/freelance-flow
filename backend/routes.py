from decimal import Decimal

from flask import Blueprint, current_app, jsonify, request

from . import ai, payments
from .activity import activity_for, record_event
from .archiving import archive_request, restore_request
from .confirmation import payment_confirmation
from .db import get_db, now, transaction
from .errors import AppError
from .guidance import explain_payment
from .models import create_request, find_request, require_public_available, serialize, status, today
from .security import rate_limit, require_allowed_origin, require_csrf, require_management
from .settings import get_settings, require_display_name, save_settings

api = Blueprint("api", __name__, url_prefix="/api")


@api.before_request
def boundaries():
    # Token APIs stay public. Management requires local boundaries or hosted login.
    if not request.path.startswith("/api/public/"):
        require_management()
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        require_allowed_origin()
        if current_app.config["AUTH_REQUIRED"] and not request.path.startswith("/api/public/"):
            require_csrf()


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
                    "today": today().isoformat(), "management": "authenticated single workspace" if current_app.config["AUTH_REQUIRED"] else "local-only, single workspace"})


@api.get("/requests")
def list_requests():
    archived = request.args.get("archived", "0")
    if archived not in ("0", "1"):
        raise AppError("validation_error", "archived must be 0 or 1.")
    condition = "IS NOT NULL" if archived == "1" else "IS NULL"
    rows = get_db().execute(f"SELECT * FROM payment_requests WHERE archived_at {condition} ORDER BY created_at DESC, id DESC").fetchall()
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
    row = find_request(request_id)
    return jsonify({"request": serialize(row), "guidance": explain_payment(row),
                    "activity": activity_for(row), "confirmation": payment_confirmation(row)})


@api.post("/requests/<int:request_id>/archive")
def archive(request_id):
    return jsonify({"request": serialize(archive_request(request_id))})


@api.post("/requests/<int:request_id>/restore")
def restore(request_id):
    return jsonify({"request": serialize(restore_request(request_id))})


@api.get("/dashboard")
def dashboard():
    rows = get_db().execute("SELECT * FROM payment_requests WHERE archived_at IS NULL ORDER BY created_at DESC, id DESC").fetchall()
    return jsonify({
        "paid_cents": sum(row["amount_cents"] for row in rows if row["status"] == "paid"),
        "outstanding_cents": sum(row["amount_cents"] for row in rows if row["status"] != "paid"),
        "overdue_cents": sum(row["amount_cents"] for row in rows if status(row) == "overdue"),
        "request_count": len(rows), "recent_requests": [serialize(row) for row in rows[:5]],
        "archived_excluded": True,
    })


@api.post("/requests/<int:request_id>/message")
def message(request_id):
    if current_app.config["AUTH_REQUIRED"]:
        rate_limit("ai", 6, 60)
    row = find_request(request_id)
    if row["archived_at"] and row["status"] != "paid":
        raise AppError("request_archived", "Restore this request before generating a payment message.", 409)
    options = body() if request.is_json else {}
    if options.get("context_aware") is True:
        facts = explain_payment(row)
        text = ai.generate_guidance_message(
            facts, row["client_name"], get_settings()["freelancer_display_name"],
            current_app.config["GOOGLE_API_KEY"], current_app.config["GEMINI_MODEL"],
        )
        fresh = find_request(request_id)
        if (fresh["archived_at"] and fresh["status"] != "paid") or explain_payment(fresh) != facts:
            raise AppError("guidance_changed", "Payment facts changed while generating. Refresh the request and try again.", 409)
        return jsonify({"message": text, "source": "gemini", "model": current_app.config["GEMINI_MODEL"], "wording": "constrained"})
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
    require_public_available(find_request(request_id))
    return jsonify({"message": text, "source": "gemini", "model": current_app.config["GEMINI_MODEL"]})


@api.get("/public/config")
def public_config():
    return jsonify({"sandbox": True, "paypal_client_id": current_app.config["PAYPAL_CLIENT_ID"] if payments.service().ready else None,
                    "paypal_configured": payments.service().ready})


@api.get("/public/requests/<token>")
def public_details(token):
    row = find_request(token=token)
    require_public_available(row)
    return jsonify({"request": serialize(row, public=True)})


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
    order_id = body().get("order_id")
    if not isinstance(order_id, str) or not 1 <= len(order_id) <= 64 or not order_id.isalnum():
        raise AppError("validation_error", "An order_id is required.")
    # A browser cancellation is advisory, not proof an order cannot still capture.
    with transaction() as db:
        row = find_request(token=token)
        require_public_available(row)
        attempt = db.execute("SELECT * FROM payment_attempts WHERE request_id=? AND order_id=?", (row["id"], order_id)).fetchone()
        if not attempt:
            raise AppError("order_not_bound", "This order does not belong to this payment request.", 409)
        if row["status"] == "paid" or attempt["state"] == "completed":
            return jsonify({"status": "paid", "message": "Payment already confirmed; cancellation did not change it."})
        if attempt["state"] != "failed":
            if not attempt["capture_started_at"]:
                db.execute("UPDATE payment_attempts SET diagnostic='buyer_cancelled', updated_at=? WHERE id=?", (now(), attempt["id"]))
            record_event(db, row["id"], "attempt_cancelled", attempt["id"])
    return jsonify({"status": "cancelled", "message": "Checkout cancelled. No paid state was recorded."})
