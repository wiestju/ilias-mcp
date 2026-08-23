import shutil
import types
from pathlib import Path

import pymupdf
import pytest

from ilias_mcp import mcp_server


def _make_test_pdf(path: Path, pages: list[str]) -> None:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


class _FakeClient:
    """Stands in for ILIASClient: 'downloading' just copies a fixture file
    into the requested destination directory, like the real client would."""

    def __init__(self, source_path: Path) -> None:
        self.source_path = source_path

    def download_file(self, ref_id: str, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / self.source_path.name
        shutil.copy(self.source_path, dest)
        return dest


@pytest.fixture
def fake_pdf(tmp_path) -> Path:
    path = tmp_path / "lecture.pdf"
    _make_test_pdf(path, ["Hello Vigenere page one", "Second page content"])
    return path


def test_read_file_extracts_text_per_page(monkeypatch, fake_pdf):
    monkeypatch.setattr(mcp_server, "_get_client", lambda: _FakeClient(fake_pdf))

    text = mcp_server.read_file("123")

    assert "Vigenere" in text
    assert "page 1/2" in text
    assert "page 2/2" in text
    assert "Second page content" in text


def test_read_file_rejects_non_pdf(monkeypatch, tmp_path):
    txt_path = tmp_path / "notes.txt"
    txt_path.write_text("plain text")
    monkeypatch.setattr(mcp_server, "_get_client", lambda: _FakeClient(txt_path))

    with pytest.raises(ValueError, match="only supports PDF"):
        mcp_server.read_file("123")


def test_read_file_images_defaults_to_all_pages(monkeypatch, fake_pdf):
    monkeypatch.setattr(mcp_server, "_get_client", lambda: _FakeClient(fake_pdf))

    images = mcp_server.read_file_images("123")

    assert len(images) == 2
    assert images[0].to_image_content().mime_type == "image/png"


def test_read_file_images_renders_only_requested_pages(monkeypatch, fake_pdf):
    monkeypatch.setattr(mcp_server, "_get_client", lambda: _FakeClient(fake_pdf))

    images = mcp_server.read_file_images("123", pages="2")

    assert len(images) == 1


def test_read_file_images_out_of_range_page_raises(monkeypatch, fake_pdf):
    monkeypatch.setattr(mcp_server, "_get_client", lambda: _FakeClient(fake_pdf))

    with pytest.raises(ValueError, match="out of range"):
        mcp_server.read_file_images("123", pages="99")


def test_read_file_images_rejects_non_pdf(monkeypatch, tmp_path):
    txt_path = tmp_path / "notes.txt"
    txt_path.write_text("plain text")
    monkeypatch.setattr(mcp_server, "_get_client", lambda: _FakeClient(txt_path))

    with pytest.raises(ValueError, match="only supports PDF"):
        mcp_server.read_file_images("123")


def test_download_file_tool_returns_local_path(monkeypatch, fake_pdf, tmp_path):
    monkeypatch.setattr(mcp_server, "_get_client", lambda: _FakeClient(fake_pdf))
    monkeypatch.setattr(
        mcp_server, "Settings", lambda: types.SimpleNamespace(download_dir=tmp_path / "downloads")
    )

    result = mcp_server.download_file("123")

    assert result == str(tmp_path / "downloads" / "lecture.pdf")
    assert Path(result).exists()


@pytest.mark.parametrize(
    ("spec", "page_count", "expected"),
    [
        ("3", 10, [2]),
        ("3-5", 10, [2, 3, 4]),
        ("3,7,10-12", 12, [2, 6, 9, 10, 11]),
    ],
)
def test_parse_page_spec(spec, page_count, expected):
    assert mcp_server._parse_page_spec(spec, page_count) == expected


def test_parse_page_spec_out_of_range_raises():
    with pytest.raises(ValueError, match="out of range"):
        mcp_server._parse_page_spec("99", 5)


class _FakeListingClient:
    """Stands in for ILIASClient for the thin list_*/forum tool wrappers —
    these just need to exercise the wiring, not real ILIAS parsing."""

    def __init__(self, **results):
        self._results = results

    def list_my_courses(self, favorites_only=False):
        return self._results["list_my_courses"]

    def list_container(self, ref_id):
        return self._results["list_container"]

    def list_forum_threads(self, ref_id):
        return self._results["list_forum_threads"]

    def read_forum_thread(self, thread_url):
        return self._results["read_forum_thread"]

    def list_exercise_assignments(self, ref_id):
        return self._results["list_exercise_assignments"]


def test_list_courses_tool_serializes_nodes(monkeypatch):
    from ilias_mcp.ilias.models import Node

    node = Node(ref_id="1", title="Kurs A", url="https://x/1", obj_type="crs")
    monkeypatch.setattr(
        mcp_server, "_get_client", lambda: _FakeListingClient(list_my_courses=[node])
    )

    result = mcp_server.list_courses()

    assert result == [
        {"ref_id": "1", "title": "Kurs A", "url": "https://x/1", "obj_type": "crs", "description": None}
    ]


def test_list_container_tool_serializes_nodes(monkeypatch):
    from ilias_mcp.ilias.models import Node

    node = Node(ref_id="2", title="Folien", url="https://x/2", obj_type="fold")
    monkeypatch.setattr(mcp_server, "_get_client", lambda: _FakeListingClient(list_container=[node]))

    result = mcp_server.list_container("2")

    assert result[0]["ref_id"] == "2"
    assert result[0]["obj_type"] == "fold"


def test_list_forum_threads_tool_passes_through(monkeypatch):
    threads = [{"thread_id": "9", "title": "Klausurtermin", "url": "https://x", "last_update": "23.08.2026"}]
    monkeypatch.setattr(
        mcp_server, "_get_client", lambda: _FakeListingClient(list_forum_threads=threads)
    )

    assert mcp_server.list_forum_threads("2905709") == threads


def test_read_forum_thread_tool_passes_through(monkeypatch):
    posts = [{"author": "Prof.", "content": "..."}]
    monkeypatch.setattr(
        mcp_server, "_get_client", lambda: _FakeListingClient(read_forum_thread=posts)
    )

    assert mcp_server.read_forum_thread("https://x/thread") == posts


def test_list_exercise_assignments_tool_passes_through(monkeypatch):
    monkeypatch.setattr(
        mcp_server, "_get_client", lambda: _FakeListingClient(list_exercise_assignments=[])
    )

    assert mcp_server.list_exercise_assignments("2911807") == []
