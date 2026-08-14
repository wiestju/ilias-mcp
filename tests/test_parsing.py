import pytest

from ilias_mcp.exceptions import ParseError
from ilias_mcp.ilias.parsing import parse_repository_items


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
