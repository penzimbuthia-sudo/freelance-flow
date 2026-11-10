"""Minimal token-scoped confirmation from server-verified persisted capture data."""

from .payment_records import has_verified_capture
from .settings import get_settings


def payment_confirmation(row):
    if not has_verified_capture(row):
        return None
    return {
        "sandbox": True, "service_description": row["service_description"],
        "amount_cents": row["amount_cents"], "currency": row["currency"],
        "freelancer_display_name": get_settings()["freelancer_display_name"] or None,
        "confirmed_at": row["paid_at"], "capture_reference": row["capture_id"],
    }
