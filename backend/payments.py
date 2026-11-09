from datetime import datetime, timezone
from uuid import uuid4

from flask import current_app

from .db import get_db, now, transaction
from .errors import AppError
from .models import find_request
from .paypal import verify_order


def service():
    return current_app.extensions["paypal"]


def require_ready():
    if not service().ready:
        raise AppError("paypal_not_configured", "Sandbox checkout needs the seller's PayPal client ID, secret, and merchant ID on the server.", 503)


def within_retry_window(timestamp):
    # Orders v2 defaults to six hours of idempotency retention. Stop short of that boundary.
    return (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp)).total_seconds() < 5 * 3600


def record_error(attempt_id, error):
    state = {"payment_declined": "failed", "order_voided": "failed", "order_not_approved": "created"}.get(error.code, "uncertain")
    with transaction() as db:
        db.execute(
            "UPDATE payment_attempts SET state=?, diagnostic=?, updated_at=? WHERE id=? AND state!='completed'",
            (state, error.code, now(), attempt_id),
        )
        if error.code == "order_not_approved":
            db.execute("UPDATE payment_attempts SET capture_started_at=NULL WHERE id=?", (attempt_id,))
    # Only fixed application codes: never raw upstream bodies, keys, or buyer details.
    current_app.logger.warning("Sandbox payment attempt %s: %s", attempt_id, error.code)


def create_order(token):
    require_ready()
    with transaction() as db:
        row = find_request(token=token)
        if row["status"] == "paid":
            raise AppError("already_paid", "This request is already paid.", 409)
        attempt = db.execute(
            "SELECT * FROM payment_attempts WHERE request_id=? AND state NOT IN ('failed','completed')", (row["id"],)
        ).fetchone()
        if not attempt:
            attempt_id, timestamp = str(uuid4()), now()
            db.execute(
                """INSERT INTO payment_attempts
                (id, request_id, create_key, capture_key, state, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'creating', ?, ?)""",
                (attempt_id, row["id"], str(uuid4()), str(uuid4()), timestamp, timestamp),
            )
            attempt = db.execute("SELECT * FROM payment_attempts WHERE id=?", (attempt_id,)).fetchone()
        attempt_id = attempt["id"]
    try:
        # Serialize this tiny workspace's payment operations, including across processes.
        # The persisted attempt above survives a process exit during an upstream call.
        with transaction() as db:
            row = find_request(token=token)
            if row["status"] == "paid":
                raise AppError("already_paid", "This request is already paid.", 409)
            attempt = db.execute("SELECT * FROM payment_attempts WHERE id=?", (attempt_id,)).fetchone()
            if attempt["order_id"]:
                if attempt["capture_started_at"]:
                    raise AppError("payment_pending", "An earlier payment needs verification. Use Check payment status before paying again.", 409)
                return {"order_id": attempt["order_id"]}
            if not within_retry_window(attempt["created_at"]):
                raise AppError("reconciliation_required", "This uncertain order is outside the safe retry window. The seller must reconcile it in PayPal sandbox before another attempt.", 409)
            order = service().create(row, attempt)
            order_id = order.get("id")
            if not isinstance(order_id, str) or not order_id.isalnum() or len(order_id) > 64:
                raise AppError("paypal_uncertain", "PayPal did not return a usable order identifier. Try checking again.", 502)
            bound_attempt = dict(attempt) | {"order_id": order_id}
            verify_order(order, row, bound_attempt, service().merchant_id)
            db.execute("UPDATE payment_attempts SET order_id=?, state='created', updated_at=?, diagnostic=NULL WHERE id=?", (order_id, now(), attempt_id))
            return {"order_id": order_id}
    except AppError as error:
        record_error(attempt_id, error)
        raise


def capture_order(token, order_id):
    require_ready()
    with transaction() as db:
        row = find_request(token=token)
        attempt = db.execute("SELECT * FROM payment_attempts WHERE order_id=? AND request_id=?", (order_id, row["id"])).fetchone()
        if not attempt:
            raise AppError("order_not_bound", "This order does not belong to this payment request.", 409)
        if row["status"] == "paid":
            if attempt["state"] != "completed" or row["capture_id"] != attempt["capture_id"]:
                raise AppError("already_paid", "This request was already paid by another attempt.", 409)
            return {"status": "paid", "capture_id": row["capture_id"]}
        if attempt["state"] == "failed":
            raise AppError("attempt_failed", "This attempt failed. Start a new sandbox checkout.", 409)
        db.execute("UPDATE payment_attempts SET capture_started_at=COALESCE(capture_started_at, ?), state='capturing', updated_at=? WHERE id=?", (now(), now(), attempt["id"]))
        attempt_id = attempt["id"]
    try:
        with transaction() as db:
            row = find_request(token=token)
            attempt = db.execute("SELECT * FROM payment_attempts WHERE id=?", (attempt_id,)).fetchone()
            if row["status"] == "paid":
                return {"status": "paid", "capture_id": row["capture_id"]}
            # ALWAYS reconcile first, including after timeouts, crashes, or duplicate callbacks.
            order = service().get_order(order_id)
            capture_id = verify_order(order, row, attempt, service().merchant_id)
            if not capture_id:
                if order.get("status") == "VOIDED":
                    raise AppError("order_voided", "This PayPal order expired or was voided. Start a new checkout.", 409)
                if order.get("status") != "APPROVED":
                    raise AppError("order_not_approved", "This order has not been approved. Return to sandbox checkout to approve it.", 409)
                if not within_retry_window(attempt["capture_started_at"]):
                    raise AppError("reconciliation_required", "No completed capture was found and the safe retry window has elapsed. The seller must reconcile this order in PayPal sandbox.", 409)
                # A retry follows a successful GET reconciliation and uses the SAME persisted key.
                order = service().capture(order_id, attempt["capture_key"])
                capture_id = verify_order(order, row, attempt, service().merchant_id)
                if not capture_id:
                    raise AppError("payment_pending", "PayPal has not completed this payment. Check its status again shortly.", 409)
            timestamp = now()
            db.execute("UPDATE payment_attempts SET state='completed', capture_id=?, diagnostic=NULL, updated_at=? WHERE id=?", (capture_id, timestamp, attempt_id))
            db.execute("UPDATE payment_requests SET status='paid', capture_id=?, paid_at=?, updated_at=? WHERE id=? AND status='unpaid'", (capture_id, timestamp, timestamp, row["id"]))
            return {"status": "paid", "capture_id": capture_id}
    except AppError as error:
        record_error(attempt_id, error)
        raise
