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

# Item-title selector: the newer "card" style used on the dashboard /
# membership overview, and the classic repository-list style used inside
# courses/folders — both confirmed against real, authenticated KIT pages.
_ITEM_TITLE_SELECTORS = (
    ".il-item-title a",
    "a.il_ContainerItemTitle",
    ".il-std-item-title a",
    ".ilContainerItemTitle a",
)

# Standard-icon filenames embed ILIAS's own type code directly
# (icon_fold.svg, icon_frm.svg, ...) — confirmed live and preferred when
# present since it's unambiguous and independent of UI language. Custom
# per-object icons (icon_custom.svg) don't carry the type, so the alt-text
# map below is the fallback, also confirmed live (German KIT UI).
_ICON_SRC_TYPE_RE = re.compile(r"icon_([a-z]+)\.svg")
_ICON_ALT_TYPE_MAP = {
    "Kurs": "crs",
    "Gruppe": "grp",
    "Ordner": "fold",
    "Verzeichnis": "fold",
    "Forum": "frm",
    "Test": "tst",
    "Übung": "exc",
    "Lernmodul ILIAS": "lm",
    "Opencast": "xoct",
    "Weblink": "webr",
    "Wiki": "wiki",
    "Datei": "file",
    "Inline Datei": "file",
}


def _extract_ref_id_and_type(url: str) -> tuple[str | None, str | None]:
    goto_match = _GOTO_RE.search(url)
    if goto_match:
        obj_type, ref_id = goto_match.groups()
        return ref_id, obj_type
    query_match = _REF_ID_QUERY_RE.search(url)
    if query_match:
        return query_match.group(1), None
    return None, None


def _find_item_container(anchor: Tag) -> Tag | None:
    # Newer "card" style (dashboard/membership overview) vs. classic
    # repository-list style (contents of a course/folder) — both real,
    # confirmed KIT markup.
    return anchor.find_parent(class_="il-item") or anchor.find_parent(
        class_="ilContainerListItemOuter"
    )


def _find_icon(container: Tag | None) -> Tag | None:
    if container is None:
        return None
    return container.select_one("img.icon") or container.select_one("img.ilListItemIcon")


def _icon_obj_type(icon: Tag | None) -> str | None:
    if icon is None:
        return None
    src_match = _ICON_SRC_TYPE_RE.search(icon.get("src", ""))
    # "custom" isn't a real ILIAS type code — it just means the course/group
    # replaced the standard icon with its own image, confirmed live on
    # several of the user's own courses. Fall back to the alt-text map then.
    if src_match and src_match.group(1) != "custom":
        return src_match.group(1)
    return _ICON_ALT_TYPE_MAP.get(icon.get("alt"))


def _find_description(container: Tag | None) -> str | None:
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
        ref_id, url_obj_type = _extract_ref_id_and_type(full_url)
        if ref_id is None:
            continue
        title = a.get_text(strip=True)
        if not title:
            continue
        container = _find_item_container(a)
        obj_type = url_obj_type or _icon_obj_type(_find_icon(container))
        nodes[ref_id] = Node(
            ref_id=ref_id,
            title=title,
            url=full_url,
            obj_type=obj_type,
            description=_find_description(container),
        )

    return list(nodes.values())
