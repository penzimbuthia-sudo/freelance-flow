import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend import ai
from backend.db import get_db
from backend.errors import AppError


def mock_genai(monkeypatch, text="Please review your USD 50.10 request.", error=None):
    client = MagicMock()
    client.__enter__.return_value = client
    client.models.generate_content.return_value = SimpleNamespace(text=text)
    if error:
        client.models.generate_content.side_effect = error
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(ai.genai, "Client", factory)
    return factory, client


def test_ai_missing_configuration(client, saved, named):
    response = client.post(f'/api/requests/{saved["id"]}/message')
    assert response.status_code == 503
    assert response.json["error"]["code"] == "ai_not_configured"


def test_ai_success_saved_facts_and_model(app, client, saved, named, monkeypatch):
    app.config["GOOGLE_API_KEY"] = "secret-for-test"
    app.config["GEMINI_MODEL"] = "configured-model"
    factory, upstream = mock_genai(monkeypatch)
    response = client.post(f'/api/requests/{saved["id"]}/message', json={"amount": "999", "freelancer_display_name": "Spoofed Name"})
    assert response.status_code == 200
    assert response.json["source"] == "gemini"
    call = upstream.models.generate_content.call_args.kwargs
    assert call["model"] == "configured-model"
    assert '"amount": "50.10"' in call["contents"]
    assert '999' not in call["contents"]
    assert f'"freelancer_display_name": "{named}"' in call["contents"]
    assert 'Spoofed Name' not in call["contents"]
    assert response.json["message"].endswith(f"\n\nKind regards,\n{named}")
    assert "without a greeting, closing" in call["config"].system_instruction
    assert factory.call_args.kwargs["http_options"].timeout == 12000


@pytest.mark.parametrize("text", [None, "", "  "])
def test_ai_empty(app, client, saved, named, monkeypatch, text):
    app.config["GOOGLE_API_KEY"] = "test"
    mock_genai(monkeypatch, text=text)
    response = client.post(f'/api/requests/{saved["id"]}/message')
    assert response.status_code == 502
    assert response.json["error"]["code"] == "ai_empty_response"


@pytest.mark.parametrize("code,expected,status", [(429, "ai_rate_limited", 429), (404, "ai_model_unavailable", 502), (500, "ai_upstream_error", 502), (None, "ai_upstream_error", 502)])
def test_ai_failure(app, client, saved, named, monkeypatch, code, expected, status):
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


def test_missing_name_blocks_ai_before_upstream(app, client, saved, monkeypatch):
    app.config["GOOGLE_API_KEY"] = "test"
    factory, _ = mock_genai(monkeypatch)
    response = client.post(f'/api/requests/{saved["id"]}/message', json={"freelancer_display_name": "Unsaved Name"})
    assert response.status_code == 409
    assert response.json["error"]["code"] == "display_name_required"
    assert "display name" in response.json["error"]["message"]
    factory.assert_not_called()


def test_updated_name_used_for_next_message(app, client, saved, named, monkeypatch):
    app.config["GOOGLE_API_KEY"] = "test"
    _, upstream = mock_genai(monkeypatch)
    client.put("/api/settings", json={"freelancer_display_name": "New Demo Name"})
    response = client.post(f'/api/requests/{saved["id"]}/message')
    assert response.json["message"].endswith("\nKind regards,\nNew Demo Name")
    assert '"freelancer_display_name": "New Demo Name"' in upstream.models.generate_content.call_args.kwargs["contents"]


@pytest.mark.parametrize("closing", ["Kind regards,", "Best regards,", "Sincerely,", "Thanks!", "Best,", "Best regards, Invented Sender", "**Kind regards,**"])
def test_model_cannot_choose_the_closing_name(app, client, saved, named, monkeypatch, closing):
    app.config["GOOGLE_API_KEY"] = "test"
    mock_genai(monkeypatch, text=f"Please review USD 50.10.\n\n{closing}\nInvented Sender")
    response = client.post(f'/api/requests/{saved["id"]}/message')
    assert response.status_code == 200
    assert response.json["message"] == f'Hello {saved["client_name"]},\n\nPlease review USD 50.10.\n\nKind regards,\n{named}'
    assert "Invented Sender" not in response.json["message"]


def test_signature_only_response_is_not_a_success(app, client, saved, named, monkeypatch):
    app.config["GOOGLE_API_KEY"] = "test"
    mock_genai(monkeypatch, text="Kind regards,\nInvented Sender")
    response = client.post(f'/api/requests/{saved["id"]}/message')
    assert response.status_code == 502
    assert response.json["error"]["code"] == "ai_empty_response"


def test_service_requires_a_name_even_outside_request_handling(monkeypatch):
    factory, _ = mock_genai(monkeypatch)
    with pytest.raises(AppError) as error:
        ai.generate_message({}, "test")
    assert error.value.code == "display_name_required"
    factory.assert_not_called()


@pytest.mark.parametrize("model_greeting", ["", "Hello Taylor Demo,\n\n", "Dear Taylor Demo:\n", "Hello Invented Recipient, "])
def test_greeting_uses_saved_client_and_closing_uses_distinct_saved_freelancer(app, client, saved, named, monkeypatch, model_greeting):
    assert saved["client_name"] != named
    app.config["GOOGLE_API_KEY"] = "test"
    _, upstream = mock_genai(monkeypatch, text=f"{model_greeting}Please review USD 50.10.")
    # Browser-supplied names must not replace either independently saved identity.
    response = client.post(f'/api/requests/{saved["id"]}/message', json={
        "client_name": named, "freelancer_display_name": saved["client_name"],
    })
    assert response.status_code == 200
    assert response.json["message"] == f'Hello {saved["client_name"]},\n\nPlease review USD 50.10.\n\nKind regards,\n{named}'
    call = upstream.models.generate_content.call_args.kwargs
    facts = json.loads(call["contents"])
    assert facts["client_name"] == saved["client_name"]
    assert facts["freelancer_display_name"] == named
    assert "client_name is the recipient" in call["config"].system_instruction
    assert "freelancer_display_name is the sender" in call["config"].system_instruction


@pytest.mark.parametrize("client_facts", [{}, {"client_name": None}, {"client_name": ""}, {"client_name": "   "}])
def test_missing_client_uses_hello_not_freelancer_name(monkeypatch, client_facts):
    mock_genai(monkeypatch, text="Hello Taylor Demo,\n\nPlease review USD 50.10.")
    message = ai.generate_message({**client_facts, "freelancer_display_name": "Taylor Demo"}, "test")
    assert message == "Hello,\n\nPlease review USD 50.10.\n\nKind regards,\nTaylor Demo"


def test_greeting_only_response_is_not_a_success(app, client, saved, named, monkeypatch):
    app.config["GOOGLE_API_KEY"] = "test"
    mock_genai(monkeypatch, text="Hello Taylor Demo,")
    response = client.post(f'/api/requests/{saved["id"]}/message')
    assert response.status_code == 502
    assert response.json["error"]["code"] == "ai_empty_response"
