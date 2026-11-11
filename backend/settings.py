import unicodedata

from .db import get_db, now, transaction
from .errors import AppError


def validate_display_name(value):
    if (not isinstance(value, str) or len(value.strip()) > 120
            or any(unicodedata.category(char).startswith("C")
                   or unicodedata.category(char) in ("Zl", "Zp") for char in value)):
        raise AppError("validation_error", "Display name must be a single line of at most 120 characters, without control characters.")
    return value.strip()


def get_settings():
    row = get_db().execute("SELECT freelancer_display_name FROM workspace_settings WHERE id=1").fetchone()
    return {"freelancer_display_name": row["freelancer_display_name"] if row else ""}


def save_settings(data):
    name = validate_display_name(data.get("freelancer_display_name"))
    timestamp = now()
    with transaction() as db:
        db.execute(
            """INSERT INTO workspace_settings (id, freelancer_display_name, created_at, updated_at)
            VALUES (1, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET
            freelancer_display_name=excluded.freelancer_display_name, updated_at=excluded.updated_at""",
            (name, timestamp, timestamp),
        )
    return get_settings()


def require_display_name(value):
    name = validate_display_name(value)
    if not name:
        raise AppError("display_name_required", "Add your freelancer display name in the AI panel before generating a signed message.", 409)
    return name
