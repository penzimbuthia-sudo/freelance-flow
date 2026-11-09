from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend import ai
from backend.db import get_db


def mock_genai(monkeypatch, text="Hello Alex, please review your USD 50.10 request.", error=None):
    client = MagicMock()
    client.__enter__.return_value = client
    client.models.generate_content.return_value = SimpleNamespace(text=text)
    if error:
        client.models.generate_content.side_effect = error
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(ai.genai, "Client", factory)
    return factory, client


def test_ai_missing_configuration(client, saved):
    response = client.post(f'/api/requests/{saved["id"]}/message')
    assert response.status_code == 503
    assert response.json["error"]["code"] == "ai_not_configured"


def test_ai_success_saved_facts_and_model(app, client, saved, monkeypatch):
    app.config["GOOGLE_API_KEY"] = "secret-for-test"
    app.config["GEMINI_MODEL"] = "configured-model"
    factory, upstream = mock_genai(monkeypatch)
    response = client.post(f'/api/requests/{saved["id"]}/message', json={"amount": "999"})
    assert response.status_code == 200
    assert response.json["source"] == "gemini"
    call = upstream.models.generate_content.call_args.kwargs
    assert call["model"] == "configured-model"
    assert '"amount": "50.10"' in call["contents"]
    assert '999' not in call["contents"]
    assert factory.call_args.kwargs["http_options"].timeout == 12000


@pytest.mark.parametrize("text", [None, "", "  "])
def test_ai_empty(app, client, saved, monkeypatch, text):
    app.config["GOOGLE_API_KEY"] = "test"
    mock_genai(monkeypatch, text=text)
    response = client.post(f'/api/requests/{saved["id"]}/message')
    assert response.status_code == 502
    assert response.json["error"]["code"] == "ai_empty_response"


@pytest.mark.parametrize("code,expected,status", [(429, "ai_rate_limited", 429), (404, "ai_model_unavailable", 502), (500, "ai_upstream_error", 502), (None, "ai_upstream_error", 502)])
def test_ai_failure(app, client, saved, monkeypatch, code, expected, status):
    app.config["GOOGLE_API_KEY"] = "test"
    error = RuntimeError("sensitive upstream prompt content")
    error.code = code
    mock_genai(monkeypatch, error=error)
    response = client.post(f'/api/requests/{saved["id"]}/message')
    assert response.status_code == status
    assert response.json["error"]["code"] == expected
    assert "sensitive" not in response.text


def test_paid_request_does_not_call_ai(app, client, saved, monkeypatch):
    factory, _ = mock_genai(monkeypatch)
    with app.app_context():
        get_db().execute("UPDATE payment_requests SET status='paid' WHERE id=?", (saved["id"],))
    assert client.post(f'/api/requests/{saved["id"]}/message').status_code == 409
    factory.assert_not_called()
