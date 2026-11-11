"""Canonical payment facts and deterministic message claims; no model arithmetic."""

from datetime import date
from decimal import Decimal

from . import models
from .db import attempt_order_column, get_db


def explain_payment(row):
    current_date = models.today()  # Africa/Nairobi, including calendar-day boundaries.
    due = date.fromisoformat(row["due_date"])
    paid = row["status"] == "paid"
    days = max(0, (current_date - due).days) if not paid else 0
    timing = "paid" if paid else "overdue" if days else "today" if due == current_date else "future"
    amount = f'{row["currency"]} {Decimal(row["amount_cents"]) / 100:.2f}'
    attempt = get_db().execute(
        f"SELECT state, diagnostic, capture_started_at FROM payment_attempts WHERE request_id=? ORDER BY {attempt_order_column()} DESC LIMIT 1",
        (row["id"],),
    ).fetchone()
    outcome = None
    if not paid and attempt:
        if attempt["state"] in ("uncertain", "capturing") or (attempt["capture_started_at"] and attempt["state"] not in ("failed", "completed")):
            outcome = "unconfirmed"
        elif attempt["state"] == "failed":
            outcome = "unavailable" if attempt["diagnostic"] == "order_unavailable" else "failed"
        elif attempt["diagnostic"] == "buyer_cancelled":
            outcome = "cancelled"
    if paid:
        explanation = f"This {amount} request for {row['client_name']} is recorded as paid. No further payment is requested."
        action = "Review and share a thank-you message, not another payment reminder."
    elif timing == "overdue":
        explanation = f"{amount} requested from {row['client_name']} remains unpaid and is {days} calendar {'day' if days == 1 else 'days'} overdue (due {due.isoformat()})."
        action = "Review a friendly follow-up and share the saved payment link."
    elif timing == "today":
        explanation = f"{amount} requested from {row['client_name']} remains unpaid and is due today, {due.isoformat()}."
        action = "Offer a polite due-today message with the saved payment link."
    else:
        explanation = f"{amount} requested from {row['client_name']} is unpaid and due on {due.isoformat()}. It is not overdue."
        action = "Share the saved payment request when you are ready."
    if outcome == "unconfirmed":
        explanation += " A payment attempt needs verification; no completed payment has been confirmed locally."
        action = "Open the client page and check payment status before attempting another payment."
    elif outcome == "cancelled":
        explanation += " A browser-reported checkout cancellation was recorded; the request remains unpaid."
        action = "Retry sandbox checkout using the saved link if the buyer still wishes to pay."
    elif outcome in ("failed", "unavailable"):
        explanation += " The previous sandbox order was recorded as unavailable." if outcome == "unavailable" else " The last payment attempt was recorded as failed."
        action = "Retry sandbox checkout using the saved link."
    return {
        "timing": timing, "payment_status": row["status"], "overdue_days": days,
        "amount_cents": row["amount_cents"], "currency": row["currency"],
        "due_date": row["due_date"], "today": current_date.isoformat(),
        "attempt_outcome": outcome, "explanation": explanation, "next_action": action,
        "message_purpose": "thank_you" if paid else "status_check" if outcome == "unconfirmed" else "payment_request",
    }


def message_body(facts, variant):
    """Only validated wording choices can influence text; all claims are app-owned."""
    amount = f'{facts["currency"]} {Decimal(facts["amount_cents"]) / 100:.2f}'
    if facts["message_purpose"] == "thank_you":
        return {
            "warm": f"Thank you for your {amount} payment. It is recorded as paid, and no further payment is needed.",
            "concise": f"Your {amount} payment is recorded as paid. Thank you!",
            "gentle": f"Thank you for taking care of the {amount} payment. No further payment is requested.",
        }[variant]
    if facts["message_purpose"] == "status_check":
        return f"The {amount} request remains unpaid in our records. A payment attempt needs verification. Please use Check payment status on the payment page before trying another payment."
    timing = facts["timing"]
    if timing == "overdue":
        days = facts["overdue_days"]
        detail = f"remains unpaid and is {days} calendar {'day' if days == 1 else 'days'} overdue (due {facts['due_date']})"
    elif timing == "today":
        detail = f"remains unpaid and is due today ({facts['due_date']})"
    else:
        detail = f"is unpaid and due on {facts['due_date']}"
    opening = {"warm": "A friendly note:", "concise": "For your reference:", "gentle": "A gentle follow-up:" if timing == "overdue" else "A quick note:"}[variant]
    return f"{opening} the {amount} payment request {detail}. Please use the payment link shared separately when you are ready."
