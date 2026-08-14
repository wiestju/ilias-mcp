from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .exceptions import MissingCredentialsError
from .providers.base import AuthProvider


class Settings(BaseSettings):
    """Non-credential configuration, loaded from the environment / .env.

    Field names map to env vars case-insensitively by their SCREAMING_SNAKE
    form (e.g. ``ilias_provider`` <-> ``ILIAS_PROVIDER``), except
    ``download_dir`` which needs an explicit alias since its env var carries
    the project prefix to avoid colliding with unrelated tools.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ilias_provider: str = "kit"
    ilias_base_url: str | None = None
    download_dir: Path = Field(
        default=Path("~/ILIAS").expanduser(), validation_alias="ILIAS_MCP_DOWNLOAD_DIR"
    )

    @field_validator("download_dir", mode="before")
    @classmethod
    def _expand_user(cls, v: str | Path) -> Path:
        return Path(v).expanduser()


def load_credentials(provider: AuthProvider, env_file: str | Path = ".env") -> dict[str, str]:
    """Look up ``{PROVIDER_NAME}_{FIELD}`` (e.g. ``KIT_USERNAME`` /
    ``KIT_PASSWORD``) for each of the provider's declared
    ``credential_fields``. Real environment variables take precedence over
    the ``.env`` file, matching normal dotenv semantics.
    """
    file_values = dotenv_values(env_file)
    prefix = provider.name.upper()
    creds: dict[str, str] = {}
    missing: list[str] = []
    for field in provider.credential_fields:
        env_name = f"{prefix}_{field.upper()}"
        value = os.environ.get(env_name) or file_values.get(env_name)
        if not value:
            missing.append(env_name)
        else:
            creds[field] = value
    if missing:
        raise MissingCredentialsError(
            f"Missing credentials for provider '{provider.name}': set "
            f"{', '.join(missing)} in your environment or .env file (see .env.example)."
        )
    return creds
