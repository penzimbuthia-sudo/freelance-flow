from backend.config import configuration


def test_api_key_precedence(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    assert configuration()["GOOGLE_API_KEY"] == "google-key"
    monkeypatch.setenv("GOOGLE_API_KEY", " ")
    assert configuration()["GOOGLE_API_KEY"] == "gemini-key"


def test_model_configurable_without_replacement(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "explicit-test-model")
    assert configuration()["GEMINI_MODEL"] == "explicit-test-model"


def test_blank_model_keeps_existing_default(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", " ")
    assert configuration()["GEMINI_MODEL"] == "gemini-3.5-flash-lite"
