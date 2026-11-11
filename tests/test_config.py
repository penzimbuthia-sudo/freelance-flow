import pytest

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


def test_explicit_environment_file_and_process_precedence(monkeypatch, tmp_path):
    selected = tmp_path / ".env.local"
    selected.write_text("DATABASE_URL=postgresql://fictional.invalid/demo\nGEMINI_MODEL=file-model\n")
    monkeypatch.setenv("FF_ENV_FILE", str(selected))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("GEMINI_MODEL", "process-model")
    assert configuration()["DATABASE_URL"] == "postgresql://fictional.invalid/demo"
    assert configuration()["GEMINI_MODEL"] == "process-model"
    # dotenv mutates os.environ; ensure this fictional URL cannot leak to tests.
    monkeypatch.delenv("DATABASE_URL")


def test_missing_selected_environment_file_fails_before_database_initialization(monkeypatch, tmp_path):
    monkeypatch.setenv("FF_ENV_FILE", str(tmp_path / "missing.env.local"))
    with pytest.raises(ValueError, match="No database was initialized"):
        configuration()
