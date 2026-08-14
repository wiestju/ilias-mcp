from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import ClassVar

import requests


class AuthProvider(ABC):
    """Base class for a login provider that can authenticate an ILIAS session.

    Subclass this to add support for another institution's ILIAS instance.
    Providers shipped in this package are wired up directly in
    :mod:`ilias_mcp.providers.registry`; third-party packages register their
    own by exposing a class under the ``ilias_mcp.providers`` entry-point
    group in their own ``pyproject.toml``::

        [project.entry-points."ilias_mcp.providers"]
        my-uni = "my_package.providers:MyUniProvider"

    That's the whole extension mechanism: implement ``login()`` (and
    optionally ``is_logged_in()``), set the four class attributes below, and
    the CLI/MCP server picks it up via ``ILIAS_PROVIDER=my-uni``.
    """

    #: Unique, stable identifier used in ILIAS_PROVIDER and entry points.
    name: ClassVar[str]
    #: Human-readable name shown in CLI output.
    display_name: ClassVar[str]
    #: Default ILIAS base URL for this provider, e.g. "https://ilias.example.edu".
    default_base_url: ClassVar[str]
    #: Names of the credential fields this provider needs, e.g. ("username", "password").
    credential_fields: ClassVar[tuple[str, ...]] = ("username", "password")

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or self.default_base_url).rstrip("/")

    @abstractmethod
    def login(self, session: requests.Session, credentials: Mapping[str, str]) -> None:
        """Authenticate ``session`` in place (cookies end up on the session).

        Must raise :class:`ilias_mcp.exceptions.LoginError` on failure rather
        than returning a falsy value, so callers don't need to guess what a
        given return type means.
        """

    def is_logged_in(self, session: requests.Session) -> bool:
        """Best-effort check whether ``session`` holds an authenticated ILIAS
        session. The default heuristic looks for the standard ILIAS login
        form on the personal desktop; override if a provider's ILIAS
        installation differs.
        """
        resp = session.get(
            f"{self.base_url}/ilias.php",
            params={"baseClass": "ilPersonalDesktopGUI"},
            allow_redirects=True,
        )
        return 'name="j_username"' not in resp.text and "cmd=force_login" not in resp.url
