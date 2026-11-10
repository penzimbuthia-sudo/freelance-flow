"""Read persisted capture evidence; this never substitutes browser approval for payment."""

from .db import get_db


def has_verified_capture(row):
    if row["status"] != "paid" or not row["capture_id"] or not row["paid_at"]:
        return False
    # Payment capture persists this completed attempt and the request's paid facts
    # atomically, only after verifying amount, currency, seller and capture status.
    return get_db().execute(
        """SELECT 1 FROM payment_attempts WHERE request_id=? AND state='completed'
        AND capture_id=? AND order_id IS NOT NULL""", (row["id"], row["capture_id"]),
    ).fetchone() is not None
