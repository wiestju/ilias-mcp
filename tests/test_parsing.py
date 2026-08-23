import pytest

from ilias_mcp.exceptions import ParseError
from ilias_mcp.ilias.parsing import (
    parse_exercise_overview,
    parse_forum_posts,
    parse_forum_threads,
    parse_info_properties,
    parse_repository_items,
)


def test_parse_repository_items_finds_known_selector():
    html = """
    <div class="il-item-title"><a href="ilias.php?ref_id=123&cmdClass=x">Kurs A</a></div>
    <div class="il-item-title"><a href="ilias.php?ref_id=456&cmdClass=x">Kurs B</a></div>
    """

    nodes = parse_repository_items(html, "https://ilias.example.edu")

    assert {n.ref_id for n in nodes} == {"123", "456"}
    assert {n.ref_id: n.title for n in nodes}["123"] == "Kurs A"


def test_parse_repository_items_handles_goto_permalinks_and_description():
    # Structure confirmed against a real, authenticated KIT dashboard page
    # (ilMembershipOverviewGUI) on 2026-08-14 — course cards link via a
    # goto.php permalink rather than a ref_id query param, and carry a
    # sibling .il-item-description block.
    html = """
    <div class="il-item il-std-item">
      <div class="media-body">
        <h4 class="il-item-title"><a href="https://ilias.example.edu/goto.php/crs/2879639">2400095 – Human-Computer-Interaction</a></h4>
        <div class="il-item-description">Einf&uuml;hrung in die Mensch-Maschine Interaktion.</div>
      </div>
    </div>
    """

    nodes = parse_repository_items(html, "https://ilias.example.edu")

    assert len(nodes) == 1
    node = nodes[0]
    assert node.ref_id == "2879639"
    assert node.obj_type == "crs"
    assert node.title == "2400095 – Human-Computer-Interaction"
    assert node.description == "Einführung in die Mensch-Maschine Interaktion."


def test_parse_repository_items_raises_on_unknown_markup():
    with pytest.raises(ParseError):
        parse_repository_items("<html><body>nothing here</body></html>", "https://ilias.example.edu")


def test_parse_repository_items_infers_type_from_classic_list_icon():
    # Classic repository-list markup (contents of a course/folder), confirmed
    # against a real KIT course page on 2026-08-14 — links via a plain
    # ref_id query param (no goto.php type segment), so the type has to come
    # from the icon filename instead.
    html = """
    <li class="ilCLI ilObjListRow">
      <div class="ilContainerListItemOuter">
        <div class="ilContainerListItemIcon">
          <img alt="Ordner" title="Ordner" src="./images/standard/icon_fold.svg" class="ilListItemIcon" />
        </div>
        <div class="ilContainerListItemContent">
          <h3 class="il_ContainerItemTitle">
            <a href="ilias.php?baseClass=ilrepositorygui&ref_id=2916774" class="il_ContainerItemTitle">Folien</a>
          </h3>
        </div>
      </div>
    </li>
    """

    nodes = parse_repository_items(html, "https://ilias.example.edu")

    assert len(nodes) == 1
    assert nodes[0].ref_id == "2916774"
    assert nodes[0].obj_type == "fold"


def test_parse_repository_items_infers_type_from_custom_icon_alt_text():
    # Custom per-object icons (icon_custom.svg) don't carry the type in the
    # filename, so this falls back to the (German, KIT UI) alt text.
    html = """
    <div class="il-item il-std-item">
      <div class="media-left">
        <img class="icon custom medium" src="./data/produktiv/container_data/obj_1/icon_custom.svg" alt="Kurs" />
      </div>
      <div class="media-body">
        <h4 class="il-item-title"><a href="ilias.php?ref_id=42">Custom-Icon Course</a></h4>
      </div>
    </div>
    """

    nodes = parse_repository_items(html, "https://ilias.example.edu")

    assert len(nodes) == 1
    assert nodes[0].obj_type == "crs"


def test_parse_forum_threads_empty_state_confirmed_live():
    # Exact tbody markup dumped from a real, authenticated KIT forum page
    # (ref_id 2905709, "Organisatorisch") on 2026-08-23 — this specific
    # empty-state row is live-confirmed, unlike the populated-row case below.
    html = """
    <table id="recf_2905709">
      <tbody>
        <tr class="tblrow1">
          <td class="ilCenter" colspan="4">Keine Einträge</td>
        </tr>
      </tbody>
    </table>
    """

    assert parse_forum_threads(html, "https://ilias.example.edu") == []


def test_parse_forum_threads_raises_when_table_missing():
    with pytest.raises(ParseError):
        parse_forum_threads("<html><body>not a forum page</body></html>", "https://ilias.example.edu")


def test_parse_forum_threads_parses_populated_row():
    # UNVERIFIED against real data (see parse_forum_threads' docstring): no
    # forum available to build/test against had any threads. Best-effort
    # guess at ILIAS's standard table-row conventions — if this diverges
    # from a real populated forum, fix the row-parsing in parsing.py and
    # update this fixture to match.
    html = """
    <table id="recf_123">
      <tbody>
        <tr>
          <td><input type="checkbox" /></td>
          <td><img alt="Thread" /></td>
          <td><a href="ilias.php?thr_pk=456&cmd=viewThread">Klausurtermin verschoben</a></td>
          <td>23.08.2026</td>
        </tr>
      </tbody>
    </table>
    """

    threads = parse_forum_threads(html, "https://ilias.example.edu")

    assert threads == [
        {
            "thread_id": "456",
            "title": "Klausurtermin verschoben",
            "url": "https://ilias.example.edu/ilias.php?thr_pk=456&cmd=viewThread",
            "last_update": "23.08.2026",
        }
    ]


def test_parse_forum_posts_parses_known_selector():
    # UNVERIFIED against real data, same caveat as test_parse_forum_threads_parses_populated_row.
    html = """
    <div class="ilFrmPostRow">
      <div class="ilFrmPostTitle">Prof. Dr. Test</div>
      <div class="ilFrmPostContent">Die Klausur findet nun am 15.02. statt.</div>
    </div>
    """

    posts = parse_forum_posts(html)

    assert posts == [
        {"author": "Prof. Dr. Test", "content": "Die Klausur findet nun am 15.02. statt."}
    ]


def test_parse_forum_posts_raises_when_no_known_selector_matches():
    with pytest.raises(ParseError):
        parse_forum_posts("<html><body>not a thread page</body></html>")


def test_parse_info_properties_parses_label_value_pairs():
    # Markup shape confirmed live against a real file object's info screen
    # on 2026-08-14 (see the function's own docstring).
    html = """
    <div class="form-group row">
      <div class="il_InfoScreenProperty">Größe</div>
      <div class="il_InfoScreenPropertyValue">1.2 MB</div>
    </div>
    <div class="form-group row">
      <div class="il_InfoScreenProperty">Erstellt am</div>
      <div class="il_InfoScreenPropertyValue">14.08.2026, 12:00</div>
    </div>
    """

    assert parse_info_properties(html) == {
        "Größe": "1.2 MB",
        "Erstellt am": "14.08.2026, 12:00",
    }


def test_parse_exercise_overview_empty_state_confirmed_live():
    # Exact panel-body markup dumped from a real, authenticated KIT exercise
    # overview page (ref_id 2911807, "Übungsblätter") on 2026-08-23.
    html = """
    <div class="panel-body">
      <div class="alert alert-info" role="status">
        <div class="ilAccHeadingHidden">Informationsmeldung</div>Keine Übungseinheiten vorhanden.
      </div>
    </div>
    """

    assert parse_exercise_overview(html) == []


def test_parse_exercise_overview_raises_when_panel_missing():
    with pytest.raises(ParseError):
        parse_exercise_overview("<html><body>not an exercise page</body></html>")


def test_parse_exercise_overview_raises_on_unrecognized_markup():
    html = """
    <div class="panel-body">
      <div class="some-assignment-row">Blatt 1 — Frist: 01.09.2026</div>
    </div>
    """

    with pytest.raises(ParseError):
        parse_exercise_overview(html)


def test_parse_exercise_overview_parses_populated_assignments():
    # Trimmed but structurally exact markup from a real, authenticated KIT
    # exercise overview page (ref_id 2911807, "Übungsblätter", mode=all)
    # on 2026-08-23 — a past semester's finished assignments, confirming
    # this needs mode=all rather than the page's own default (ongoing-only,
    # which hides everything outside the current date range).
    html = """
    <div class="il-item il-notification-item">not a real assignment</div>
    <div class="il-item il-std-item">
      <div class="row">
        <div class="col-sm-3">Beendet </div>
        <div class="col-sm-9">
          <h4 class="il-item-title">
            <a href="ilias.php?cmdClass=ilAssignmentPresentationGUI&amp;ref_id=2911807&amp;ass_id=105632">1. Übungsblatt</a>
          </h4>
          <div class="row">
            <div class="col-md-6"><span class="il-item-property-name">Beendet am</span><span class="il-item-property-value">8. Mai 2026, 09:45</span></div>
            <div class="col-md-6"><span class="il-item-property-name">Anforderung</span><span class="il-item-property-value">Verpflichtend</span></div>
          </div>
          <div class="row">
            <div class="col-md-6"><span class="il-item-property-name">Datum der letzten Abgabe</span><span class="il-item-property-value">Bisher keine Abgabe</span></div>
            <div class="col-md-6"><span class="il-item-property-name">Type</span><span class="il-item-property-value">Datei</span></div>
          </div>
          <div class="row">
            <div class="col-md-6"><span class="il-item-property-name">Status</span><span class="il-item-property-value">Nicht bewertet</span></div>
          </div>
        </div>
      </div>
    </div>
    """

    assignments = parse_exercise_overview(html)

    assert assignments == [
        {
            "assignment_id": "105632",
            "title": "1. Übungsblatt",
            "status": "Beendet",
            "Beendet am": "8. Mai 2026, 09:45",
            "Anforderung": "Verpflichtend",
            "Datum der letzten Abgabe": "Bisher keine Abgabe",
            "Type": "Datei",
            "Status": "Nicht bewertet",
        }
    ]
