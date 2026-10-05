import pytest

from ilias_mcp.exceptions import ParseError
from ilias_mcp.ilias.parsing import (
    parse_container_page_text,
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


def test_parse_repository_items_ignores_side_column_blocks():
    # Structure confirmed against a real KIT course page on 2026-10-05: a
    # consultation-hours block in the right column uses the same card
    # markup as the dashboard, and used to shadow the course's real
    # contents in the center column.
    html = """
    <div id="il_center_col">
      <div class="ilContainerListItemOuter">
        <img class="ilListItemIcon" src="/templates/default/images/standard/icon_fold.svg" alt="Ordner">
        <h3 class="il_ContainerItemTitle"><a class="il_ContainerItemTitle" href="https://ilias.example.edu/goto.php/fold/111">Vorlesungen</a></h3>
      </div>
    </div>
    <aside id="il_right_col">
      <div class="il-item il-std-item">
        <h4 class="il-item-title"><a href="ilias.php?cmdClass=ilcalendarpresentationgui&ref_id=999&ch_user_id=1">Prof. Dr. Example</a></h4>
      </div>
    </aside>
    """

    nodes = parse_repository_items(html, "https://ilias.example.edu")

    assert [(n.ref_id, n.title, n.obj_type) for n in nodes] == [("111", "Vorlesungen", "fold")]


def test_parse_repository_items_reads_classic_list_description():
    # Classic repository-list markup, confirmed against a real KIT course
    # page on 2026-10-05: every item carries an .il_Description section,
    # empty for items without a description.
    html = """
    <div class="ilContainerListItemOuter">
      <h3 class="il_ContainerItemTitle"><a class="il_ContainerItemTitle" href="https://ilias.example.edu/goto.php/webr/1">Chat</a></h3>
      <div class="ilListItemSection il_Description">Anonymer Chat zur Vorlesung.</div>
    </div>
    <div class="ilContainerListItemOuter">
      <h3 class="il_ContainerItemTitle"><a class="il_ContainerItemTitle" href="https://ilias.example.edu/goto.php/fold/2">Vorlesungen</a></h3>
      <div class="ilListItemSection il_Description"></div>
    </div>
    """

    nodes = parse_repository_items(html, "https://ilias.example.edu")

    assert {n.ref_id: n.description for n in nodes} == {
        "1": "Anonymer Chat zur Vorlesung.",
        "2": None,
    }


_CONTAINER_PAGE_HTML = """
<div id="il_center_col">
  <!--COPage-PageTop-->
  <a id="ilPageShowAdvContent"><span>Vertiefungswissen anzeigen</span></a>
  <div class="ilc_section_Separator ilCOPageSection">
    <p class="ilc_Paragraph"><strong>Herzlich Willkommen</strong> zur <em>Vorlesung</em>.</p><!--Break-->
    <p class="ilc_Paragraph">Mittwochs 08:00<br>im Audimax.</p>
  </div>
  <div class="ilc_va_cntr_AccordCntr">
    <div class="ilc_va_ihead_AccordIHead"><div class="ilc_va_ihcap_AccordIHeadCap">Klausur</div></div>
    <div class="il_VAccordionContentDef ilAccHideContent">
      <p class="ilc_Paragraph">Anmeldung im <a href="https://portal.example.edu/x">Portal</a>, siehe <a href="goto.php/crs/42">Kurs</a>.</p>
      <div class="ilc_Paragraph"><ul><li>Teil A (60%)</li><li>Teil B (40%)</li></ul></div>
    </div>
  </div>
  <div class="ilContainerBlock"><h3 class="il_ContainerItemTitle"><a href="goto.php/fold/7">Vorlesungen</a></h3></div>
  <div class="il-copg-mob-fullscreen-modal"><dialog>Vollbild Abbrechen</dialog></div>
</div>
<aside id="il_right_col">Sprechstunde</aside>
"""


def test_parse_container_page_text_renders_page_editor_content():
    # Structure confirmed against a real KIT course page on 2026-10-05.
    text = parse_container_page_text(_CONTAINER_PAGE_HTML, "https://ilias.example.edu")

    assert text.splitlines() == [
        "Herzlich Willkommen zur Vorlesung.",
        "Mittwochs 08:00",
        "im Audimax.",
        "## Klausur",
        (
            "Anmeldung im Portal (https://portal.example.edu/x), siehe Kurs "
            "(https://ilias.example.edu/goto.php/crs/42)."
        ),
        "- Teil A (60%)",
        "- Teil B (40%)",
    ]


def test_parse_container_page_text_is_empty_without_page_content():
    html = """
    <div id="il_center_col">
      <div class="ilContainerBlock"><a class="il_ContainerItemTitle" href="goto.php/fold/7">Vorlesungen</a></div>
    </div>
    """

    assert parse_container_page_text(html, "https://ilias.example.edu") == ""


def test_parse_container_page_text_raises_when_content_column_missing():
    with pytest.raises(ParseError):
        parse_container_page_text("<html><body>Login</body></html>", "https://ilias.example.edu")


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


def test_parse_exercise_overview_empty_state_is_language_independent():
    # Same structural markup, English UI text instead of German — the ILIAS
    # UI language is a per-account setting; detection must not depend on
    # matching the German wording.
    html = """
    <div class="panel-body">
      <div class="alert alert-info" role="status">No exercise units available.</div>
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
            "state": "Beendet",
            "deadline": "8. Mai 2026, 09:45",
            "requirement": "Verpflichtend",
            "last_submission_date": "Bisher keine Abgabe",
            "submission_type": "Datei",
            "grading_status": "Nicht bewertet",
        }
    ]


def test_parse_exercise_overview_keeps_unrecognized_property_labels_as_is():
    # An unknown property label (not in _PROPERTY_NAME_TRANSLATIONS) should
    # fall through with its original key rather than being dropped.
    html = """
    <div class="il-item il-std-item">
      <div class="row">
        <div class="col-sm-3">Läuft</div>
        <div class="col-sm-9">
          <h4 class="il-item-title"><a href="ilias.php?ass_id=1">2. Blatt</a></h4>
          <div class="row">
            <div class="col-md-6"><span class="il-item-property-name">Irgendein neues Feld</span><span class="il-item-property-value">Wert</span></div>
          </div>
        </div>
      </div>
    </div>
    """

    assignments = parse_exercise_overview(html)

    assert assignments[0]["Irgendein neues Feld"] == "Wert"
