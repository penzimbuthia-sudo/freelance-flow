import re
import threading
import time
from decimal import Decimal, InvalidOperation

import requests

from .errors import AppError

BASE_URL = "https://api-m.sandbox.paypal.com"


class PayPalService:
    """Sandbox REST only. POSTs are never automatically retried by the HTTP client."""

    def __init__(self, config):
        self.client_id = config["PAYPAL_CLIENT_ID"]
        self.secret = config["PAYPAL_CLIENT_SECRET"]
        self.merchant_id = config["PAYPAL_MERCHANT_ID"]
        self.session = requests.Session()
        self._token = None
        self._expires = 0
        self._lock = threading.Lock()

    @property
    def ready(self):
        return bool(self.client_id and self.secret and self.merchant_id)

    def access_token(self):
        if not self.ready:
            raise AppError("paypal_not_configured", "Sandbox checkout needs PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, and PAYPAL_MERCHANT_ID on the server.", 503)
        with self._lock:
            if self._token and time.monotonic() < self._expires:
                return self._token
            try:
                response = self.session.post(
                    f"{BASE_URL}/v1/oauth2/token", auth=(self.client_id, self.secret),
                    data={"grant_type": "client_credentials"}, timeout=(5, 15),
                )
                response.raise_for_status()
                data = response.json()
                self._token = data["access_token"]
                self._expires = time.monotonic() + max(0, int(data["expires_in"]) - 60)
            except (requests.RequestException, ValueError, KeyError, TypeError):
                raise AppError("paypal_auth_error", "PayPal sandbox authentication failed. Check the seller app credentials.", 502) from None
            return self._token

    def call(self, method, path, key=None, payload=None):
        headers = {"Authorization": f"Bearer {self.access_token()}", "Content-Type": "application/json", "Prefer": "return=representation"}
        if key:
            headers["PayPal-Request-Id"] = key
        try:
            response = self.session.request(method, BASE_URL + path, headers=headers, json=payload, timeout=(5, 15))
            if response.status_code == 401:
                self._expires = 0  # Refresh on the next user-initiated attempt, not by replaying a POST.
            if not response.ok:
                raise AppError("paypal_upstream_error", "PayPal could not confirm the operation. Check payment status before retrying.", 502)
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except (requests.RequestException, ValueError):
            raise AppError("paypal_uncertain", "PayPal did not return a confirmed result. Use Check payment status before trying again.", 502) from None

    def create(self, row, attempt):
        return self.call("POST", "/v2/checkout/orders", key=attempt["create_key"], payload={
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": str(row["id"]), "custom_id": attempt["id"],
                "payee": {"merchant_id": self.merchant_id},
                "amount": {"currency_code": "USD", "value": f'{Decimal(row["amount_cents"]) / 100:.2f}'},
            }],
        })

    def get_order(self, order_id):
        if not isinstance(order_id, str) or not re.fullmatch(r"[A-Za-z0-9]{1,64}", order_id):
            raise AppError("invalid_order", "Invalid PayPal order identifier.")
        return self.call("GET", f"/v2/checkout/orders/{order_id}")

    def capture(self, order_id, key):
        return self.call("POST", f"/v2/checkout/orders/{order_id}/capture", key=key, payload={})


def verify_order(order, row, attempt, merchant_id):
    """Validate order binding, gross amount, currency, seller, and capture facts."""
    try:
        units = order["purchase_units"]
        if len(units) != 1:
            raise ValueError()
        unit = units[0]
        amount = unit["amount"]
        expected = Decimal(row["amount_cents"]) / 100
        if (order["id"] != attempt["order_id"] or unit["reference_id"] != str(row["id"])
                or unit["custom_id"] != attempt["id"] or unit["payee"]["merchant_id"] != merchant_id
                or amount["currency_code"] != "USD" or Decimal(amount["value"]) != expected):
            raise ValueError()
        captures = unit.get("payments", {}).get("captures", [])
        if not captures:
            if order["status"] == "COMPLETED":
                raise ValueError()
            return None
        if len(captures) != 1:
            raise ValueError()
        capture = captures[0]
        if capture["amount"]["currency_code"] != "USD" or Decimal(capture["amount"]["value"]) != expected:
            raise ValueError()
        if capture["status"] == "COMPLETED" and order["status"] == "COMPLETED" and capture.get("id"):
            return capture["id"]
        if capture["status"] in ("DECLINED", "FAILED", "DENIED"):
            raise AppError("payment_declined", "The payment was declined. Your request is still unpaid and can be retried.", 409)
        raise AppError("payment_pending", "PayPal has not completed this payment. Check its status again shortly; do not pay again.", 409)
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise AppError("payment_mismatch", "PayPal payment details did not match this request. The request has not been marked paid.", 409) from None
