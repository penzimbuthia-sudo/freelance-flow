"""Reversible management-only visibility state, independent of payment status."""

from flask import current_app

from .db import get_db, now, transaction
from .errors import AppError
from .models import find_request
from .payment_records import has_verified_capture
from .paypal import verify_order


def blocked(diagnostics=None):
    return AppError("archive_payment_unresolved", "Finish or reconcile the payment attempt before archiving this request.", 409, diagnostics)


def local_attempts(row):
    attempts = get_db().execute("SELECT * FROM payment_attempts WHERE request_id=?", (row["id"],)).fetchall()
    if row["status"] == "paid" and not has_verified_capture(row):
        raise blocked()
    for attempt in attempts:
        if attempt["state"] == "completed":
            if row["status"] != "paid" or attempt["capture_id"] != row["capture_id"]:
                raise blocked()
        elif attempt["state"] == "failed":
            if attempt["capture_id"]:
                raise blocked()
        elif (attempt["state"] != "created" or attempt["capture_started_at"]
              or attempt["capture_id"] or not attempt["order_id"]):
            raise blocked()
    return attempts


def archive_request(request_id):
    row = find_request(request_id)
    if row["archived_at"]:
        return row
    # WAL reads can see the persisted creating/capturing marker while another
    # process holds the payment write lock during a network call. Reject promptly.
    local_attempts(row)
    with transaction() as db:
        row = find_request(request_id)
        if row["archived_at"]:
            return row
        attempts = local_attempts(row)  # Recheck under the same lock used by payments.
        service = current_app.extensions["paypal"]
        for attempt in attempts:
            if attempt["state"] != "created":
                continue
            if not service.ready:
                raise blocked()
            try:
                order = service.get_order(attempt["order_id"])
            except AppError as error:
                # No capture ever started locally; an authoritative missing order
                # is unavailable, not an ambiguous POST. Never rotate or delete it.
                if error.code == "paypal_order_not_found":
                    continue
                raise blocked(error.diagnostics) from None
            try:
                capture_id = verify_order(order, row, attempt, service.merchant_id)
            except AppError as error:
                raise blocked(error.diagnostics) from None
            if capture_id or order.get("status") not in ("CREATED", "VOIDED"):
                raise blocked()
        db.execute("UPDATE payment_requests SET archived_at=? WHERE id=?", (now(), request_id))
        return find_request(request_id)


def restore_request(request_id):
    with transaction() as db:
        find_request(request_id)
        db.execute("UPDATE payment_requests SET archived_at=NULL WHERE id=?", (request_id,))
        return find_request(request_id)
