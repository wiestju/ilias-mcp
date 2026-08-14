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


def test_parse_repository_items_raises_on_unknown_markup():
    with pytest.raises(ParseError):
        parse_repository_items("<html><body>nothing here</body></html>", "https://ilias.example.edu")
