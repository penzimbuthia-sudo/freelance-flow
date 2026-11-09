from copy import deepcopy

import pytest

from backend import create_app
from backend.errors import AppError


@pytest.fixture
def app(tmp_path):
    return create_app({
        "TESTING": True, "DATABASE": str(tmp_path / "test.sqlite3"),
        "GOOGLE_API_KEY": "", "GEMINI_MODEL": "gemini-3.5-flash-lite",
        "PAYPAL_CLIENT_ID": "test-client", "PAYPAL_CLIENT_SECRET": "test-secret",
        "PAYPAL_MERCHANT_ID": "TESTSELLER", "PUBLIC_BASE_URL": "http://localhost:5173",
    })


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def saved(client):
    return client.post("/api/requests", json={
        "client_name": "Alex Demo", "service_description": "Fictional website design",
        "amount": "50.10", "due_date": "2026-11-10",
    }).json["request"]


@pytest.fixture
def named(client):
    name = "Taylor Demo"
    assert client.put("/api/settings", json={"freelancer_display_name": name}).status_code == 200
    return name


def public_path(saved):
    return "/api/public/requests/" + saved["payment_url"].rsplit("/", 1)[1]


class FakePayPal:
    ready = True
    merchant_id = "TESTSELLER"

    def __init__(self):
        self.orders = {}
        self.order_keys = {}
        self.create_calls = []
        self.capture_calls = []
        self.get_calls = []
        self.uncertain_create = False
        self.uncertain_capture = False
        self.capture_status = "COMPLETED"

    def create(self, row, attempt):
        self.create_calls.append(attempt["create_key"])
        order_id = self.order_keys.setdefault(attempt["create_key"], f"ORDER{row['id']}N{len(self.orders) + 1}")
        self.orders.setdefault(order_id, {
            "id": order_id, "status": "CREATED", "purchase_units": [{
                "reference_id": str(row["id"]), "custom_id": attempt["id"],
                "payee": {"merchant_id": self.merchant_id},
                "amount": {"currency_code": "USD", "value": f"{row['amount_cents'] // 100}.{row['amount_cents'] % 100:02}"},
            }],
        })
        if self.uncertain_create:
            self.uncertain_create = False
            raise AppError("paypal_uncertain", "Simulated create timeout", 502)
        return deepcopy(self.orders[order_id])

    def get_order(self, order_id):
        self.get_calls.append(order_id)
        return deepcopy(self.orders[order_id])

    def capture(self, order_id, key):
        self.capture_calls.append(key)
        order = self.orders[order_id]
        order["status"] = "COMPLETED" if self.capture_status == "COMPLETED" else "APPROVED"
        unit = order["purchase_units"][0]
        unit["payments"] = {"captures": [{
            "id": f"CAPTURE{order_id}", "status": self.capture_status, "amount": deepcopy(unit["amount"]),
        }]}
        if self.uncertain_capture:
            self.uncertain_capture = False
            raise AppError("paypal_uncertain", "Simulated capture timeout", 502)
        return deepcopy(order)


@pytest.fixture
def paypal(app):
    fake = FakePayPal()
    app.extensions["paypal"] = fake
    return fake


@pytest.fixture
def approved(client, saved, paypal):
    path = public_path(saved)
    response = client.post(path + "/orders")
    assert response.status_code == 201
    order_id = response.json["order_id"]
    paypal.orders[order_id]["status"] = "APPROVED"
    return path, order_id
