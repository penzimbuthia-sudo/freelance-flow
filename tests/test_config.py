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


def test_render_enforces_hosted_mode_even_when_app_env_is_local(monkeypatch, tmp_path):
    selected = tmp_path / ".env.empty"
    selected.write_text("")
    monkeypatch.setenv("FF_ENV_FILE", str(selected))
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://workspace.example")
    monkeypatch.delenv("APP_HOSTS", raising=False)
    config = configuration()
    assert config["HOSTED"] is True and config["AUTH_REQUIRED"] is True
    assert config["TRUSTED_HOSTS"] == ["workspace.example"]


def test_hosted_mode_does_not_implicitly_load_dotenv(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("DATABASE_URL=postgresql://fictional.invalid/do-not-load\n")
    monkeypatch.setattr("backend.config.ROOT", tmp_path)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("FF_ENV_FILE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert configuration()["DATABASE_URL"] == ""
