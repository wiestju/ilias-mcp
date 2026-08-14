from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from ..exceptions import ParseError
from .models import Node

_REF_ID_RE = re.compile(r"ref_id=(\d+)")

# ILIAS repository markup has changed across major versions (5.4 vs 7 vs 8)
# and can carry theme-specific customizations, so we try a few known
# item-title selector patterns in order rather than betting on exactly one.
# NOT yet verified against a real authenticated KIT page — refine this list
# once a real dashboard/course HTML dump is available (ILIAS_MCP_DEBUG_DUMP=1).
_ITEM_TITLE_SELECTORS = (
    "a.il_ContainerItemTitle",
    ".il-item-title a",
    ".il-std-item-title a",
    ".ilContainerItemTitle a",
)


def _extract_ref_id(href: str) -> str | None:
    match = _REF_ID_RE.search(href)
    return match.group(1) if match else None


def parse_repository_items(html: str, base_url: str) -> list[Node]:
    """Parse the item list out of an ILIAS repository/course/dashboard page.

    Raises ParseError if none of the known selector patterns match anything,
    so callers get a clear signal to inspect the page (rather than silently
    returning an empty list) — see the module docstring note above.
    """
    soup = BeautifulSoup(html, "lxml")

    anchors = []
    for selector in _ITEM_TITLE_SELECTORS:
        anchors = soup.select(selector)
        if anchors:
            break

    if not anchors:
        raise ParseError(
            "Could not find any repository item titles in this page using the "
            "known selectors. ILIAS markup varies by version/theme — rerun with "
            "ILIAS_MCP_DEBUG_DUMP=1 and update _ITEM_TITLE_SELECTORS in "
            "ilias_mcp/ilias/parsing.py to match the real markup."
        )

    nodes: dict[str, Node] = {}
    for a in anchors:
        href = a.get("href")
        if not href:
            continue
        full_url = urljoin(base_url + "/", href)
        ref_id = _extract_ref_id(full_url)
        if ref_id is None:
            continue
        title = a.get_text(strip=True)
        if not title:
            continue
        nodes[ref_id] = Node(ref_id=ref_id, title=title, url=full_url)

    return list(nodes.values())


def extract_file_download_href(html: str) -> str | None:
    """Best-effort: find the download link on an ILIAS file-object page.

    Provisional, same caveat as parse_repository_items — ILIAS file object
    pages typically expose a "cmd=sendfile" or "cmd=download" link.
    """
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        query = parse_qs(urlparse(href).query)
        cmd = query.get("cmd", [""])[0].lower()
        if cmd in ("sendfile", "download"):
            return href
    return None
