import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspace_settings (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    freelancer_display_name TEXT NOT NULL CHECK(length(freelancer_display_name) <= 120),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payment_requests (
    id INTEGER PRIMARY KEY,
    public_token TEXT NOT NULL UNIQUE,
    client_name TEXT NOT NULL,
    service_description TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    currency TEXT NOT NULL DEFAULT 'USD' CHECK(currency = 'USD'),
    due_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unpaid' CHECK(status IN ('unpaid','paid')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    paid_at TEXT,
    capture_id TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS payment_attempts (
    id TEXT PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES payment_requests(id),
    order_id TEXT UNIQUE,
    capture_id TEXT UNIQUE,
    create_key TEXT NOT NULL UNIQUE,
    capture_key TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL,
    diagnostic TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    capture_started_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_attempt
ON payment_attempts(request_id) WHERE state NOT IN ('failed', 'completed');
CREATE TABLE IF NOT EXISTS payment_events (
    id INTEGER PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES payment_requests(id),
    attempt_id TEXT REFERENCES payment_attempts(id),
    kind TEXT NOT NULL CHECK(kind IN ('request_created','order_created','payment_confirmed','attempt_cancelled','attempt_failed','order_unavailable')),
    occurred_at TEXT NOT NULL,
    event_key TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS payment_events_request ON payment_events(request_id, occurred_at, id);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=35, isolation_level=None)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA busy_timeout = 35000")
    return g.db


@contextmanager
def transaction():
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise


def init_db():
    Path(current_app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    get_db().execute("PRAGMA journal_mode = WAL")
    get_db().executescript(SCHEMA)


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()
