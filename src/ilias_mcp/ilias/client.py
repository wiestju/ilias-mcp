from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urljoin

import requests

from ..exceptions import NotLoggedInError, ParseError
from ..providers.base import AuthProvider
from .models import Node
from .parsing import extract_file_download_href, parse_repository_items

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

    def login(self, credentials: Mapping[str, str]) -> None:
        self.provider.login(self.session, credentials)
        self._logged_in = True

    def _require_login(self) -> None:
        if not self._logged_in:
            raise NotLoggedInError("Call login() before using the ILIAS client.")

    def list_my_courses(self) -> list[Node]:
        """List the courses on the personal dashboard ("Meine Kurse")."""
        self._require_login()
        resp = self.session.get(
            f"{self.base_url}/ilias.php",
            params={"baseClass": "ilDashboardGUI", "cmd": "show"},
        )
        resp.raise_for_status()
        return parse_repository_items(resp.text, self.base_url)

    def list_container(self, ref_id: str) -> list[Node]:
        """List the direct children of a repository container (course, folder, ...)."""
        self._require_login()
        resp = self.session.get(
            f"{self.base_url}/ilias.php",
            params={"baseClass": "ilRepositoryGUI", "ref_id": ref_id, "cmd": "view"},
        )
        resp.raise_for_status()
        return parse_repository_items(resp.text, self.base_url)

    def download_file(self, node: Node, dest_dir: Path) -> Path:
        """Download a file-object node into dest_dir, returning the local path."""
        self._require_login()
        dest_dir.mkdir(parents=True, exist_ok=True)

        download_url = node.download_url
        if download_url is None:
            page = self.session.get(node.url)
            page.raise_for_status()
            href = extract_file_download_href(page.text)
            if href is None:
                raise ParseError(f"No download link found on file page: {node.url}")
            download_url = urljoin(node.url, href)

        with self.session.get(download_url, stream=True) as resp:
            resp.raise_for_status()
            filename = _filename_from_response(resp) or node.title
            dest_path = dest_dir / filename
            with open(dest_path, "wb") as fh:
                fh.writelines(resp.iter_content(chunk_size=64 * 1024))
        return dest_path

    def list_announcements(self, ref_id: str) -> list[Node]:
        raise NotImplementedError(
            "Announcements parsing needs a real authenticated ILIAS page to verify "
            "markup against; planned for right after live login testing (see README roadmap)."
        )

    def list_assignments(self, ref_id: str) -> list[Node]:
        raise NotImplementedError(
            "Assignments/exercises parsing needs a real authenticated ILIAS page to verify "
            "markup against; planned for right after live login testing (see README roadmap)."
        )
