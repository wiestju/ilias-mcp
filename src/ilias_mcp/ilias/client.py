from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

import requests

from ..exceptions import NotLoggedInError, ParseError
from ..providers.base import AuthProvider
from .models import Node
from .parsing import parse_forum_posts, parse_forum_threads, parse_repository_items

_CONTENT_DISPOSITION_FILENAME_RE = re.compile(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?')


def _filename_from_response(resp: requests.Response) -> str | None:
    content_disposition = resp.headers.get("Content-Disposition")
    if not content_disposition:
        return None
    match = _CONTENT_DISPOSITION_FILENAME_RE.search(content_disposition)
    return match.group(1) if match else None


class ILIASClient:
    """Thin session-based client for an ILIAS instance, authenticated via a
    pluggable :class:`~ilias_mcp.providers.base.AuthProvider`.
    """

    def __init__(self, provider: AuthProvider, user_agent: str = "ilias-mcp/0.1") -> None:
        self.provider = provider
        self.base_url = provider.base_url
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self._logged_in = False
        self._credentials: Mapping[str, str] | None = None

    def login(self, credentials: Mapping[str, str]) -> None:
        self.provider.login(self.session, credentials)
        self._logged_in = True
        # Kept so a long-lived client (the MCP server process stays up for an
        # entire chat session) can transparently re-authenticate if the ILIAS
        # session times out mid-conversation, instead of every subsequent
        # call failing with a confusing "couldn't parse the page" error.
        self._credentials = credentials

    def _require_login(self) -> None:
        if not self._logged_in:
            raise NotLoggedInError("Call login() before using the ILIAS client.")

    def _reauth_if_expired(self) -> bool:
        """Re-login with the original credentials if the ILIAS session has
        silently expired. Returns True if a fresh login was performed."""
        if self._credentials is None or self.provider.is_logged_in(self.session):
            return False
        self.provider.login(self.session, self._credentials)
        return True

    def list_my_courses(self, favorites_only: bool = False) -> list[Node]:
        """List the user's ILIAS course/group memberships.

        By default this is the full membership overview — every course/group
        the user belongs to. Pass ``favorites_only=True`` for just the
        personal dashboard's "Meine Kurse" widget instead: a strict subset of
        manually/automatically pinned items, confirmed live to omit courses
        the user is a member of but never pinned (and, conversely, to
        include non-membership items like forums that the full overview
        doesn't list).
        """
        self._require_login()
        if favorites_only:
            params = {"baseClass": "ilDashboardGUI", "cmd": "show"}
        else:
            params = {"baseClass": "ilMembershipOverviewGUI"}

        def _fetch() -> list[Node]:
            resp = self.session.get(f"{self.base_url}/ilias.php", params=params)
            resp.raise_for_status()
            return parse_repository_items(resp.text, self.base_url)

        try:
            return _fetch()
        except ParseError:
            # A page we can't parse is most often a stale session landing on
            # ILIAS's login page instead of the expected listing — re-login
            # and retry once before treating it as a real markup change.
            if self._reauth_if_expired():
                return _fetch()
            raise

    def list_container(self, ref_id: str) -> list[Node]:
        """List the direct children of a repository container (course, folder, ...)."""
        self._require_login()

        def _fetch() -> list[Node]:
            resp = self.session.get(
                f"{self.base_url}/ilias.php",
                params={"baseClass": "ilRepositoryGUI", "ref_id": ref_id, "cmd": "view"},
            )
            resp.raise_for_status()
            return parse_repository_items(resp.text, self.base_url)

        try:
            return _fetch()
        except ParseError:
            if self._reauth_if_expired():
                return _fetch()
            raise

    def download_file(self, ref_id: str, dest_dir: Path) -> Path:
        """Download a file object by ref_id into dest_dir, returning the local path.

        Uses ILIAS's ``goto.php`` direct-download permalink
        (``/goto.php/file/<ref_id>/download``), confirmed live against a real
        KIT file object — no page-scraping needed for this step.
        """
        self._require_login()
        # No parse step here to react to on failure (a stale session would
        # silently save the login page's HTML as if it were the file), so
        # check proactively instead.
        self._reauth_if_expired()
        dest_dir.mkdir(parents=True, exist_ok=True)

        with self.session.get(f"{self.base_url}/goto.php/file/{ref_id}/download", stream=True) as resp:
            resp.raise_for_status()
            filename = _filename_from_response(resp) or f"ilias_file_{ref_id}"
            dest_path = dest_dir / filename
            with open(dest_path, "wb") as fh:
                fh.writelines(resp.iter_content(chunk_size=64 * 1024))
        return dest_path

    def list_forum_threads(self, ref_id: str) -> list[dict[str, str | None]]:
        """List the threads in an ILIAS forum, identified by its ref_id.

        There's no separate "announcements" object type — a course's
        announcements are just a forum (often literally titled
        "Announcements" or "Organisatorisch"), discoverable via
        list_container like any other item.
        """
        self._require_login()

        def _fetch() -> list[dict[str, str | None]]:
            resp = self.session.get(
                f"{self.base_url}/ilias.php",
                params={"baseClass": "ilRepositoryGUI", "ref_id": ref_id, "cmd": "view"},
            )
            resp.raise_for_status()
            return parse_forum_threads(resp.text, self.base_url)

        try:
            return _fetch()
        except ParseError:
            if self._reauth_if_expired():
                return _fetch()
            raise

    def read_forum_thread(self, thread_url: str) -> list[dict[str, str | None]]:
        """Read the posts in a forum thread, given the absolute thread URL
        returned by list_forum_threads (its ``url`` field)."""
        self._require_login()

        def _fetch() -> list[dict[str, str | None]]:
            resp = self.session.get(thread_url)
            resp.raise_for_status()
            return parse_forum_posts(resp.text)

        try:
            return _fetch()
        except ParseError:
            if self._reauth_if_expired():
                return _fetch()
            raise
