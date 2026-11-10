"""Append-only factual activity, excluding tokens, buyer details and provider bodies."""

from .db import get_db, now
from .payment_records import has_verified_capture

LABELS = {
    "request_created": "Request created",
    "order_created": "PayPal sandbox order created",
    "payment_confirmed": "Payment confirmed",
    "attempt_cancelled": "Checkout cancellation reported by browser",
    "attempt_failed": "Payment attempt failed",
    "order_unavailable": "Sandbox order unavailable",
}


def record_event(db, request_id, kind, attempt_id=None, occurred_at=None):
    identity = request_id if kind in ("request_created", "payment_confirmed") else attempt_id
    db.execute(
        """INSERT INTO payment_events (request_id, attempt_id, kind, occurred_at, event_key)
        VALUES (?, ?, ?, ?, ?) ON CONFLICT(event_key) DO NOTHING""",
        (request_id, attempt_id, kind, occurred_at or now(), f"{kind}:{identity}"),
    )


def activity_for(row):
    events = [dict(event) for event in get_db().execute(
        "SELECT kind, occurred_at FROM payment_events WHERE request_id=? ORDER BY occurred_at, id", (row["id"],)
    )]
    # Only authoritative legacy timestamps can support historical entries.
    # Attempt.created_at precedes the provider POST; updated_at is mutable.
    # Neither proves when an old order was created, cancelled or failed.
    if row["created_at"] and not any(event["kind"] == "request_created" for event in events):
        events.insert(0, {"kind": "request_created", "occurred_at": row["created_at"]})
    if has_verified_capture(row) and not any(event["kind"] == "payment_confirmed" for event in events):
        events.append({"kind": "payment_confirmed", "occurred_at": row["paid_at"]})
    events.sort(key=lambda event: event["occurred_at"])
    return [{**event, "label": LABELS[event["kind"]]} for event in events]
