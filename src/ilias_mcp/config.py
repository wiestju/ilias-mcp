from __future__ import annotations

import os
from pathlib import Path

import keyring
from dotenv import dotenv_values
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .exceptions import MissingCredentialsError, ProviderNotFoundError
from .providers.base import AuthProvider

# Resolved relative to this file rather than left as a bare ".env": MCP
# clients (Claude Desktop, etc.) spawn this process with an arbitrary
# working directory, so a cwd-relative lookup silently finds nothing and
# every tool call fails with a misleading "missing credentials" error.
_DEFAULT_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"

# Service name under which `ilias-mcp init` stores credentials in the OS
# keyring (macOS Keychain / Windows Credential Manager / Linux Secret
# Service via `keyring`) — a real secret store instead of a plaintext file,
# which matters more for a university login than for a scoped, revocable
# API key.
KEYRING_SERVICE = "ilias-mcp"


class Settings(BaseSettings):
    """Non-credential configuration, loaded from the environment / .env.

    Field names map to env vars case-insensitively by their SCREAMING_SNAKE
    form (e.g. ``ilias_provider`` <-> ``ILIAS_PROVIDER``), except
    ``download_dir`` which needs an explicit alias since its env var carries
    the project prefix to avoid colliding with unrelated tools.
    """

    model_config = SettingsConfigDict(
        env_file=_DEFAULT_ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    # No default on purpose: this is a generic ILIAS MCP server, and silently
    # defaulting to "kit" would let a non-KIT user run it against the wrong
    # institution without noticing. Forcing an explicit choice makes clear,
    # at setup time, that it only works against whichever ILIAS instance
    # you've told it about.
    ilias_provider: str | None = None
    ilias_base_url: str | None = None
    download_dir: Path = Field(
        default=Path("~/ILIAS").expanduser(), validation_alias="ILIAS_MCP_DOWNLOAD_DIR"
    )

    @field_validator("download_dir", mode="before")
    @classmethod
    def _expand_user(cls, v: str | Path) -> Path:
        return Path(v).expanduser()


def require_provider_name(value: str | None) -> str:
    """Validate a resolved provider name (from ``--provider`` or
    ``ILIAS_PROVIDER``), raising a clear error if none was configured
    anywhere rather than silently falling back to a specific institution."""
    if not value:
        raise ProviderNotFoundError(
            "No ILIAS provider configured. This is a generic ILIAS MCP server — "
            "it needs to be told which university's ILIAS instance to use. Set "
            "ILIAS_PROVIDER=<name> (env var or .env) or pass --provider <name> "
            "to 'ilias-mcp init'. Run 'ilias-mcp providers' to see what's "
            "registered."
        )
    return value


def load_credentials(
    provider: AuthProvider, env_file: str | Path = _DEFAULT_ENV_FILE
) -> dict[str, str]:
    """Look up ``{PROVIDER_NAME}_{FIELD}`` (e.g. ``KIT_USERNAME`` /
    ``KIT_PASSWORD``) for each of the provider's declared
    ``credential_fields``, checked in this order: a real environment
    variable (explicit override, e.g. for CI), then the OS keyring (what
    ``ilias-mcp init`` writes to — the recommended way to store a real
    university password), then the ``.env`` file (legacy/manual fallback).
    """
    file_values = dotenv_values(env_file)
    prefix = provider.name.upper()
    creds: dict[str, str] = {}
    missing: list[str] = []
    for field in provider.credential_fields:
        env_name = f"{prefix}_{field.upper()}"
        value = (
            os.environ.get(env_name)
            or keyring.get_password(KEYRING_SERVICE, env_name)
            or file_values.get(env_name)
        )
        if not value:
            missing.append(env_name)
        else:
            creds[field] = value
    if missing:
        raise MissingCredentialsError(
            f"Missing credentials for provider '{provider.name}': set "
            f"{', '.join(missing)} via 'ilias-mcp init', or in your environment "
            "or .env file (see .env.example)."
        )
    return creds
