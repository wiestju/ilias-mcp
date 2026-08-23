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


_ASS_ID_RE = re.compile(r"ass_id=(\d+)")


def parse_exercise_overview(html: str) -> list[dict[str, str | None]]:
    """Parse the assignment list off an ILIAS exercise overview page
    (``ilExerciseHandlerGUI``/``ilObjExerciseGUI&cmd=showOverview``,
    ``mode=all`` — the default ``mode=ongoing`` hides everything outside
    the current date range, e.g. a past semester's finished assignments)
    — read-only: this is the student-facing overview, not a submission
    endpoint.

    Both states confirmed live against a real KIT exercise (ref_id
    2911807, "Übungsblätter", 2026-08-23) and structurally different, not
    just "empty vs non-empty" of the same layout:

    - Populated: each assignment is a ``.il-item.il-std-item`` card (the
      ``.il-std-item`` qualifier matters — bare ``.il-item`` also matches
      unrelated page chrome like the notification-bell widget) with a
      ``.il-item-title a`` (title + ``ass_id=<id>`` in its href) and
      ``.il-item-property-name``/``.il-item-property-value`` span pairs
      (deadline, last submission date, type, grading status, ...).
    - Empty: a ``.panel-body`` containing an ``.alert-info`` box with
      "Keine Übungseinheiten vorhanden." — this wrapper is only present
      in the empty state, not around populated results.
    """
    soup = BeautifulSoup(html, "lxml")

    assignments: list[dict[str, str | None]] = []
    for item in soup.select(".il-item.il-std-item"):
        title_link = item.select_one(".il-item-title a")
        if title_link is None:
            continue
        ass_id_match = _ASS_ID_RE.search(title_link.get("href", ""))
        status_col = item.select_one(".col-sm-3")
        assignment: dict[str, str | None] = {
            "assignment_id": ass_id_match.group(1) if ass_id_match else None,
            "title": title_link.get_text(strip=True),
            "status": status_col.get_text(strip=True) if status_col else None,
        }
        names = item.select(".il-item-property-name")
        values = item.select(".il-item-property-value")
        for name_el, value_el in zip(names, values, strict=False):
            key = name_el.get_text(strip=True)
            if key:
                assignment[key] = value_el.get_text(strip=True)
        assignments.append(assignment)

    if assignments:
        return assignments

    empty_state = soup.select_one(".panel-body .alert-info")
    if empty_state and "keine" in empty_state.get_text(strip=True).lower():
        return []

    raise ParseError(
        "Could not find either assignment cards or the known empty-state "
        "message on this exercise overview page. Rerun with "
        "ILIAS_MCP_DEBUG_DUMP=1 and check parse_exercise_overview in "
        "ilias_mcp/ilias/parsing.py."
    )


def parse_info_properties(html: str) -> dict[str, str]:
    """Parse the label/value property pairs off an ILIAS object's Info
    screen (``ilInfoScreenGUI&cmd=showSummary``).

    This page exists for every ILIAS object type (file, exercise, test,
    course, ...) and is purely informational — a safe, read-only way to see
    e.g. an exercise's deadline without going anywhere near submission/edit
    endpoints. Markup confirmed live against a real file object's info
    screen on 2026-08-14:
        <div class="form-group row">
          <div class="il_InfoScreenProperty ...">Label</div>
          <div class="il_InfoScreenPropertyValue ...">Value</div>
        </div>
    """
    soup = BeautifulSoup(html, "lxml")
    properties: dict[str, str] = {}
    for label in soup.select(".il_InfoScreenProperty"):
        value = label.find_next_sibling(class_="il_InfoScreenPropertyValue")
        key = label.get_text(strip=True)
        if not key or value is None:
            continue
        properties[key] = value.get_text(" ", strip=True)
    return properties


_THR_PK_RE = re.compile(r"thr_pk=(\d+)")


def parse_forum_threads(html: str, base_url: str) -> list[dict[str, str | None]]:
    """Parse the thread list off an ILIAS forum page (``ilObjForumGUI&cmd=view``).

    The empty-state table (a single "Keine Einträge" row) is confirmed live
    against a real KIT forum (2026-08-23). The actual thread-row markup below
    is still a best-effort guess at ILIAS's standard table-row conventions,
    not independently verified — none of the forums available to verify
    against had any threads. If this returns nothing for a forum you know
    has threads, rerun with ILIAS_MCP_DEBUG_DUMP=1 and fix the row-parsing
    below.
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table[id^='recf_']")
    if table is None:
        raise ParseError(
            "Could not find the forum thread table on this page. Rerun with "
            "ILIAS_MCP_DEBUG_DUMP=1 and check parse_forum_threads in "
            "ilias_mcp/ilias/parsing.py."
        )

    threads: list[dict[str, str | None]] = []
    for row in table.select("tbody tr"):
        cells = row.find_all("td")
        if len(cells) <= 1:
            continue  # "Keine Einträge" placeholder row
        link = row.find("a", href=True)
        if link is None:
            continue
        full_url = urljoin(base_url + "/", link["href"])
        thr_match = _THR_PK_RE.search(full_url)
        threads.append(
            {
                "thread_id": thr_match.group(1) if thr_match else None,
                "title": link.get_text(strip=True),
                "url": full_url,
                "last_update": cells[-1].get_text(strip=True),
            }
        )
    return threads


_POST_SELECTORS = (".ilFrmPostRow", ".forumPostRow", ".il-forum-post")


def parse_forum_posts(html: str) -> list[dict[str, str | None]]:
    """Parse individual posts out of an ILIAS forum thread page (``cmd=viewThread``).

    UNVERIFIED against real data — no populated thread was available in the
    account this was built against (see parse_forum_threads). Rerun with
    ILIAS_MCP_DEBUG_DUMP=1 against a real thread and fix the selectors here
    if this raises ParseError or returns nonsense on your ILIAS instance.
    """
    soup = BeautifulSoup(html, "lxml")

    rows = []
    for selector in _POST_SELECTORS:
        rows = soup.select(selector)
        if rows:
            break

    if not rows:
        raise ParseError(
            "Could not find any forum posts on this page using the known "
            "(unverified) selectors. Rerun with ILIAS_MCP_DEBUG_DUMP=1 and "
            "update parse_forum_posts in ilias_mcp/ilias/parsing.py to match "
            "the real markup."
        )

    posts: list[dict[str, str | None]] = []
    for row in rows:
        author = row.select_one(".ilFrmPostTitle, .il-post-author, .ilForumPostTitle")
        content = row.select_one(".ilFrmPostContent, .il-post-content, .ilForumPostContent")
        posts.append(
            {
                "author": author.get_text(strip=True) if author else None,
                "content": content.get_text("\n", strip=True)
                if content
                else row.get_text("\n", strip=True),
            }
        )
    return posts
