import pytest

from ilias_mcp.config import load_credentials
from ilias_mcp.exceptions import MissingCredentialsError
from ilias_mcp.providers.kit import KITProvider


def test_load_credentials_from_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("KIT_USERNAME", raising=False)
    monkeypatch.delenv("KIT_PASSWORD", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("KIT_USERNAME=xy1234\nKIT_PASSWORD=secret\n")

    creds = load_credentials(KITProvider(), env_file=env_file)

    assert creds == {"username": "xy1234", "password": "secret"}


def test_load_credentials_prefers_real_env_var_over_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("KIT_USERNAME=from-file\nKIT_PASSWORD=from-file\n")
    monkeypatch.setenv("KIT_USERNAME", "from-env")
    monkeypatch.setenv("KIT_PASSWORD", "from-env")

    creds = load_credentials(KITProvider(), env_file=env_file)

    assert creds == {"username": "from-env", "password": "from-env"}


def test_load_credentials_missing_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("KIT_USERNAME", raising=False)
    monkeypatch.delenv("KIT_PASSWORD", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("")

    with pytest.raises(MissingCredentialsError):
        load_credentials(KITProvider(), env_file=env_file)
