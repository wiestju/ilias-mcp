from __future__ import annotations

from .config import Settings, load_credentials, require_provider_name
from .ilias.client import ILIASClient
from .providers.registry import get_provider_class


def build_client() -> ILIASClient:
    """Read Settings/.env, instantiate the configured provider, log in, and
    return a ready-to-use ILIASClient. Shared by the CLI and the MCP server
    so both bootstrap identically.
    """
    settings = Settings()
    provider_cls = get_provider_class(require_provider_name(settings.ilias_provider))
    provider = provider_cls(base_url=settings.ilias_base_url)
    client = ILIASClient(provider)
    credentials = load_credentials(provider)
    client.login(credentials)
    return client
