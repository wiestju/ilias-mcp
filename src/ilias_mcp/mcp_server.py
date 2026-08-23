from __future__ import annotations

import tempfile
from dataclasses import asdict
from pathlib import Path

import pymupdf
from mcp.server.mcpserver import Image, MCPServer

from .bootstrap import build_client
from .config import Settings
from .ilias.client import ILIASClient

mcp = MCPServer(
    "ilias-mcp",
    instructions=(
        "Tools for browsing and downloading course materials from ILIAS — a "
        "learning-management/e-learning platform used by many German and other "
        "European universities for lecture slides, exercises, course "
        "structure, and forum-based announcements. Relevant whenever the "
        "user asks about their university courses or coursework (lecture "
        "materials, exam prep, assignments, \"what did the professor "
        "announce/say about X\"), even if they don't say 'ILIAS' explicitly "
        "— not a general web browser or search tool. "
        "Scoped to a single, pre-configured ILIAS instance (one university, "
        "set via ILIAS_PROVIDER — see 'ilias-mcp providers' for what's "
        "registered). Login happens lazily on first tool call, using "
        "credentials from the OS keyring ('ilias-mcp init'), the environment, "
        "or .env."
    ),
)

_client: ILIASClient | None = None


def _get_client() -> ILIASClient:
    global _client
    if _client is None:
        _client = build_client()
    return _client


@mcp.tool()
def list_courses(favorites_only: bool = False) -> list[dict]:
    """List the current user's ILIAS course/group memberships. By default
    returns every course/group the user belongs to; set favorites_only=True
    for just the personal dashboard's "Meine Kurse" widget (pinned items
    only, a strict subset)."""
    return [asdict(node) for node in _get_client().list_my_courses(favorites_only=favorites_only)]


@mcp.tool()
def list_container(ref_id: str) -> list[dict]:
    """List the direct children (folders, files, exercises, ...) of an ILIAS
    repository container, identified by its ref_id (as returned by
    list_courses/list_container itself)."""
    return [asdict(node) for node in _get_client().list_container(ref_id)]


@mcp.tool()
def list_forum_threads(ref_id: str) -> list[dict]:
    """List the threads in an ILIAS forum, identified by its ref_id (an item
    with obj_type "frm" from list_container). There's no separate
    "announcements" tool — a course's announcements are just a forum, often
    literally titled "Announcements" or "Organisatorisch" — find it via
    list_container first. Each thread includes a `url`; pass that to
    read_forum_thread to read its posts."""
    return _get_client().list_forum_threads(ref_id)


@mcp.tool()
def read_forum_thread(thread_url: str) -> list[dict]:
    """Read the posts in a forum thread, given the `url` field from one of
    list_forum_threads' results (not a ref_id)."""
    return _get_client().read_forum_thread(thread_url)


@mcp.tool()
def download_file(ref_id: str) -> str:
    """Download an ILIAS file object by ref_id into the configured download
    directory and return the local file path."""
    path = _get_client().download_file(ref_id, Settings().download_dir)
    return str(path)


def _require_pdf(path: Path, tool_name: str) -> None:
    if path.suffix.lower() != ".pdf":
        raise ValueError(
            f"{tool_name} only supports PDF files right now (got '{path.name}'). "
            "Use download_file for this file instead."
        )


def _parse_page_spec(spec: str, page_count: int) -> list[int]:
    """Parse a 1-based page spec like "3,7,10-12" into 0-based page indices."""
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            pages.extend(range(int(start) - 1, int(end)))
        else:
            pages.append(int(part) - 1)
    for page in pages:
        if not 0 <= page < page_count:
            raise ValueError(f"Page {page + 1} out of range (document has {page_count} pages).")
    return pages


@mcp.tool()
def read_file(ref_id: str) -> str:
    """Download an ILIAS file object by ref_id and return its text content,
    page by page. Only PDF files are supported; use download_file for other
    formats. This extracts the embedded text layer only — diagrams,
    images, handwriting, and scanned (non-text) pages are not captured, so
    fall back to read_file_images for those. Prefer this tool first: it is
    far cheaper than read_file_images and usually sufficient for
    text-heavy material like lecture slides. The file is downloaded to a
    temporary location and deleted again immediately after its content is
    read, leaving nothing on disk."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = _get_client().download_file(ref_id, Path(tmp_dir))
        _require_pdf(path, "read_file")
        with pymupdf.open(str(path)) as doc:
            return "\n\n".join(
                f"--- page {i + 1}/{doc.page_count} ---\n{page.get_text()}"
                for i, page in enumerate(doc)
            )


@mcp.tool(structured_output=False)
def read_file_images(ref_id: str, pages: str | None = None) -> list[Image]:
    """Download an ILIAS PDF by ref_id and return specific pages as images,
    the same way a PDF looks when attached to the chat manually — diagrams,
    layout, and handwriting included, not just the text layer. Only PDF
    files are supported; use download_file for other formats. Rendered
    pages are far more expensive (payload size and vision tokens) than
    read_file's text output, so call read_file first and only reach for
    this tool for the specific pages where the text wasn't enough (e.g. a
    diagram, table, or scanned page) — pass those via `pages`, e.g. "10",
    "10-13", or "3,7,10-12" (1-based, comma-separated, ranges with a
    dash). Omit `pages` only if you deliberately need the whole document.
    The file is downloaded to a temporary location and deleted again
    immediately after rendering, leaving nothing on disk."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = _get_client().download_file(ref_id, Path(tmp_dir))
        _require_pdf(path, "read_file_images")
        with pymupdf.open(str(path)) as doc:
            page_indices = _parse_page_spec(pages, doc.page_count) if pages else range(doc.page_count)
            return [
                Image(data=doc[i].get_pixmap(dpi=150).tobytes("png"), format="png")
                for i in page_indices
            ]


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
