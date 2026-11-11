import importlib.util
from pathlib import Path

import pytest
from dotenv import dotenv_values
from werkzeug.security import check_password_hash


@pytest.fixture
def generator(monkeypatch, tmp_path):
    source = Path(__file__).resolve().parent.parent / "scripts/create_hosted_secrets.py"
    spec = importlib.util.spec_from_file_location("hosted_secret_generator", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "__file__", str(tmp_path / "scripts/create_hosted_secrets.py"))
    monkeypatch.setattr("builtins.input", lambda _prompt: "fictional-admin")
    return module


def test_private_generation_never_prints_or_saves_password(generator, monkeypatch, tmp_path, capsys):
    password = "fictional-setup-password-only"
    monkeypatch.setattr(generator, "getpass", lambda _prompt: password)
    generator.main()
    target = tmp_path / ".env.render.local"
    assert target.stat().st_mode & 0o777 == 0o600
    values = dotenv_values(target)
    assert check_password_hash(values["ADMIN_PASSWORD_HASH"], password)
    assert len(values["SECRET_KEY"]) >= 32
    assert password not in target.read_text()
    output = capsys.readouterr().out
    assert all(value not in output for value in (password, values["SECRET_KEY"], values["ADMIN_PASSWORD_HASH"]))
    before = target.read_bytes()
    with pytest.raises(SystemExit, match="nothing was overwritten"):
        generator.main()
    assert target.read_bytes() == before


def test_weak_password_writes_nothing(generator, monkeypatch, tmp_path):
    monkeypatch.setattr(generator, "getpass", lambda _prompt: "short")
    with pytest.raises(SystemExit, match="no file written"):
        generator.main()
    assert not (tmp_path / ".env.render.local").exists()
