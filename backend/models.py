import re
import secrets
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from flask import current_app

from .activity import record_event
from .confirmation import payment_confirmation
from .db import get_db, now, transaction
from .errors import AppError


def today():
    return datetime.now(ZoneInfo("Africa/Nairobi")).date()


def find_request(request_id=None, token=None):
    column, value = ("public_token", token) if token is not None else ("id", request_id)
    row = get_db().execute(f"SELECT * FROM payment_requests WHERE {column} = ?", (value,)).fetchone()
    if row is None:
        raise AppError("not_found", "Payment request not found.", 404)
    return row


def status(row):
    if row["status"] == "paid":
        return "paid"
    return "overdue" if date.fromisoformat(row["due_date"]) < today() else "pending"


def require_public_available(row):
    if row["archived_at"] and row["status"] != "paid":
        raise AppError("request_unavailable", "This payment request is no longer available.", 404)


def serialize(row, public=False):
    result = {key: row[key] for key in (
        "service_description", "amount_cents", "currency", "due_date", "paid_at"
    )}
    result["status"] = status(row)
    if not public:
        result.update({key: row[key] for key in ("id", "client_name", "created_at", "updated_at")})
        result["payment_url"] = f'{current_app.config["PUBLIC_BASE_URL"]}/pay/{row["public_token"]}'
        result.update(archived=bool(row["archived_at"]), archived_at=row["archived_at"])
    else:
        # No client name, internal IDs, prompts, or attempt diagnostics on public pages.
        attempt = get_db().execute(
            "SELECT order_id FROM payment_attempts WHERE request_id=? AND state NOT IN ('failed','completed')",
            (row["id"],),
        ).fetchone()
        result["active_order_id"] = attempt["order_id"] if attempt else None
        result["confirmation"] = payment_confirmation(row)
    return result


def create_request(data):
    if not isinstance(data, dict):
        raise AppError("validation_error", "Provide a JSON object.")
    fields = {}
    for key, maximum, label in [
        ("client_name", 120, "Client name"),
        ("service_description", 1000, "Service description"),
    ]:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
            raise AppError("validation_error", f"{label} is required (maximum {maximum} characters).")
        fields[key] = value.strip()
    amount = data.get("amount")
    # Decimal strings only: no JSON floats, exponents, NaN, or rounding away fractions of cents.
    if not isinstance(amount, str) or not re.fullmatch(r"\d{1,7}(?:\.\d{1,2})?", amount):
        raise AppError("validation_error", "Amount must be a USD decimal string with at most two decimal places.")
    cents = int(Decimal(amount) * 100)
    if not 1 <= cents <= 99_999_999:
        raise AppError("validation_error", "Amount must be between $0.01 and $999,999.99 USD.")
    due = data.get("due_date")
    try:
        if not isinstance(due, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
            raise ValueError()
        date.fromisoformat(due)
    except ValueError:
        raise AppError("validation_error", "Due date must be a valid YYYY-MM-DD date.") from None
    if data.get("currency", "USD") != "USD":
        raise AppError("validation_error", "Only USD is supported.")
    timestamp = now()
    with transaction() as db:
        cursor = db.execute(
            """INSERT INTO payment_requests
            (public_token, client_name, service_description, amount_cents, due_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (secrets.token_urlsafe(32), fields["client_name"], fields["service_description"], cents, due, timestamp, timestamp),
        )
        request_id = cursor.fetchone()["id"]
        record_event(db, request_id, "request_created", occurred_at=timestamp)
    return find_request(request_id)
