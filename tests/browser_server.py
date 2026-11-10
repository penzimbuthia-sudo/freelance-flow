"""Isolated Playwright server; never use this entry point for the real workspace.

Fixture controls are registered only here, not in production create_app. Real
credentials are blank, external services are mocked, and drafts are labelled as
test fixtures. All test records live in the ignored browser database.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flask import jsonify, request

from backend import ai, create_app
from backend.paypal import PayPalService
from conftest import FakePayPal


app = create_app({
    "DATABASE": str(ROOT / "test-results/browser.sqlite3"),
    "GOOGLE_API_KEY": "", "PAYPAL_CLIENT_ID": "", "PAYPAL_CLIENT_SECRET": "", "PAYPAL_MERCHANT_ID": "",
    "PUBLIC_BASE_URL": "http://localhost:5001", "TRUSTED_HOSTS": ["localhost", "127.0.0.1"],
})
app.config["FIXTURE_ENABLED"] = False
app.config["FIXTURE_AI_MODE"] = "success"
original_model = app.config["GEMINI_MODEL"]


def mock_response(**_kwargs):
    mode = app.config["FIXTURE_AI_MODE"]
    if mode == "error":
        raise RuntimeError("Explicit browser-test Gemini failure")
    return SimpleNamespace(text={"success": '{"variant":"warm"}', "malformed": '{"message":"not a valid choice"}', "empty": ""}[mode])


upstream = MagicMock()
upstream.__enter__.return_value = upstream
upstream.models.generate_content.side_effect = mock_response
ai.genai.Client = MagicMock(return_value=upstream)


@app.post("/__test__/services")
def fixture_services():
    enabled = request.get_json()["enabled"]
    app.config.update(
        FIXTURE_ENABLED=enabled, FIXTURE_AI_MODE="success",
        GOOGLE_API_KEY="explicit-browser-fixture" if enabled else "",
        GEMINI_MODEL="browser-test-fixture" if enabled else original_model,
        PAYPAL_CLIENT_ID="explicit-browser-fixture" if enabled else "",
    )
    app.extensions["paypal"] = FakePayPal() if enabled else PayPalService(app.config)
    return jsonify({"external_services": "mocked" if enabled else "disabled"})


@app.post("/__test__/ai")
def fixture_ai():
    mode = request.get_json()["mode"]
    if mode not in ("success", "error", "malformed", "empty"):
        return jsonify({"error": "Invalid fixture mode"}), 400
    app.config["FIXTURE_AI_MODE"] = mode
    return jsonify({"mode": mode})


@app.post("/__test__/approve")
def fixture_approval():
    service = app.extensions["paypal"]
    order_id = request.get_json()["order_id"]
    if not isinstance(service, FakePayPal) or order_id not in service.orders:
        return jsonify({"error": "Fixture order not found"}), 404
    service.orders[order_id]["status"] = "APPROVED"
    return jsonify({"approved": True, "external_services": "mocked"})


@app.after_request
def label_fixture(response):
    if app.config["FIXTURE_ENABLED"] and request.path.endswith("/message") and response.is_json and response.status_code == 200:
        data = response.get_json()
        data["source"] = "test-fixture"
        response.set_data(app.json.dumps(data))
    return response


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False, use_reloader=False)
