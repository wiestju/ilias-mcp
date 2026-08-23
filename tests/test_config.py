import pytest

import ilias_mcp.config as config_module
from ilias_mcp.config import load_credentials, require_provider_name
from ilias_mcp.exceptions import MissingCredentialsError, ProviderNotFoundError
from ilias_mcp.providers.kit import KITProvider


@pytest.fixture(autouse=True)
def no_real_keyring(monkeypatch):
    """Isolate tests from whatever the developer's real OS keyring happens
    to hold (e.g. actual KIT credentials stored via `ilias-mcp init`) —
    otherwise these tests' pass/fail depends on the machine they run on."""
    monkeypatch.setattr(config_module.keyring, "get_password", lambda service, name: None)


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


def test_require_provider_name_raises_when_unset():
    with pytest.raises(ProviderNotFoundError):
        require_provider_name(None)


def test_require_provider_name_passes_through_value():
    assert require_provider_name("kit") == "kit"
