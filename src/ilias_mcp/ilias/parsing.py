from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from ..exceptions import ParseError
from .models import Node

# Two ways ILIAS links to a repository object, both observed on a real,
# authenticated KIT dashboard (ilMembershipOverviewGUI) on 2026-08-14:
#   - a "goto" permalink:      https://<host>/goto.php/crs/2879639
#   - a classic query param:   ilias.php?...&ref_id=2879639&...
_GOTO_RE = re.compile(r"/goto\.php/([a-zA-Z]+)/(\d+)")
_REF_ID_QUERY_RE = re.compile(r"[?&]ref_id=(\d+)")

# Item-title selector, confirmed against the real KIT dashboard markup:
#   <h4 class="il-item-title"><a href="...">Course Name</a></h4>
# Kept as a tried-in-order list (rather than betting on exactly one) since
# ILIAS markup does vary across versions/themes and other providers' ILIAS
# installations may differ from KIT's.
_ITEM_TITLE_SELECTORS = (
    ".il-item-title a",
    "a.il_ContainerItemTitle",
    ".il-std-item-title a",
    ".ilContainerItemTitle a",
)


def _extract_ref_id_and_type(url: str) -> tuple[str | None, str | None]:
    goto_match = _GOTO_RE.search(url)
    if goto_match:
        obj_type, ref_id = goto_match.groups()
        return ref_id, obj_type
    query_match = _REF_ID_QUERY_RE.search(url)
    if query_match:
        return query_match.group(1), None
    return None, None


def _find_description(anchor: Tag) -> str | None:
    # Sibling of the title's containing block within the same item card:
    #   <div class="il-item ..."><h4 class="il-item-title">...</h4>
    #     <div class="il-item-description">...</div></div>
    container = anchor.find_parent(class_="il-item")
    if container is None:
        return None
    description = container.select_one(".il-item-description")
    return description.get_text(strip=True) if description else None


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
        ref_id, obj_type = _extract_ref_id_and_type(full_url)
        if ref_id is None:
            continue
        title = a.get_text(strip=True)
        if not title:
            continue
        nodes[ref_id] = Node(
            ref_id=ref_id,
            title=title,
            url=full_url,
            obj_type=obj_type,
            description=_find_description(a),
        )

    return list(nodes.values())
