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
