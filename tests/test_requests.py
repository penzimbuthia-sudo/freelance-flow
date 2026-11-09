from datetime import date

import pytest

from backend import create_app, models
from backend.db import get_db, now


def test_create_and_persist(app, client, saved):
    assert saved["amount_cents"] == 5010
    assert saved["client_name"] == "Alex Demo"
    assert len(saved["payment_url"].rsplit("/", 1)[1]) >= 40
    second_app = create_app({**app.config})
    assert second_app.test_client().get(f'/api/requests/{saved["id"]}').json["request"] == saved
    assert len(client.get("/api/requests").json["requests"]) == 1


@pytest.mark.parametrize("field,value", [
    ("client_name", " "), ("client_name", "x" * 121), ("service_description", ""),
    ("service_description", "x" * 1001), ("amount", "0"), ("amount", "-1"),
    ("amount", "0.001"), ("amount", 0.1), ("amount", "NaN"), ("amount", "1e2"),
    ("amount", "1000000.00"), ("due_date", "2026-02-30"), ("due_date", "20261110"),
    ("due_date", None), ("currency", "EUR"),
])
def test_validation(client, field, value):
    data = {"client_name": "Demo", "service_description": "Demo", "amount": "0.10", "due_date": "2026-11-10"}
    data[field] = value
    response = client.post("/api/requests", json=data)
    assert response.status_code == 400
    assert response.json["error"]["code"] == "validation_error"
    assert client.get("/api/requests").json["requests"] == []


def test_precision_totals_and_overdue(app, client, monkeypatch):
    monkeypatch.setattr(models, "today", lambda: date(2026, 11, 10))
    for amount, due in [("0.10", "2026-11-09"), ("0.20", "2026-11-10"), ("0.30", "2026-11-01")]:
        client.post("/api/requests", json={"client_name": "Demo", "service_description": "Demo", "amount": amount, "due_date": due})
    with app.app_context():
        get_db().execute("UPDATE payment_requests SET status='paid', paid_at=? WHERE id=3", (now(),))
    totals = client.get("/api/dashboard").json
    assert (totals["paid_cents"], totals["outstanding_cents"], totals["overdue_cents"]) == (30, 30, 10)
    assert [r["status"] for r in totals["recent_requests"]] == ["paid", "pending", "overdue"]


def test_json_errors_and_security(client):
    assert client.post("/api/requests", data="invalid", content_type="application/json").json["error"]
    assert client.post("/api/requests", json=[]).status_code == 400
    assert client.get("/api/requests/999").status_code == 404
    assert client.get("/api/missing").status_code == 404
    assert client.get("/api/requests", environ_overrides={"REMOTE_ADDR": "192.0.2.1"}).status_code == 403
    assert client.post("/api/requests", json={}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/requests", headers={"X-Forwarded-For": "192.0.2.1"}).status_code == 403


def test_public_domain_does_not_expose_management(app):
    app.config["TRUSTED_HOSTS"] = ["demo.example"]
    browser = app.test_client()
    assert browser.get("/api/requests", headers={"Host": "demo.example"}).status_code == 403
    assert browser.get("/requests", headers={"Host": "demo.example"}).status_code == 403
    assert browser.get("/api/public/config", headers={"Host": "demo.example"}).status_code == 200


def test_readiness_and_public_minimization(client, saved):
    health = client.get("/api/health").json
    assert health["status"] == "ok"
    assert health["gemini_model"] == "gemini-3.5-flash-lite"
    assert "test-secret" not in str(health)
    token = saved["payment_url"].rsplit("/", 1)[1]
    public = client.get(f"/api/public/requests/{token}", environ_overrides={"REMOTE_ADDR": "192.0.2.1"})
    assert public.status_code == 200
    assert "client_name" not in public.json["request"]
    assert "payment_url" not in public.json["request"]
    assert "id" not in public.json["request"]
    assert public.headers["Cache-Control"] == "no-store"
