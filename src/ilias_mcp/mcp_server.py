from __future__ import annotations

import functools
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any, TypeVar

import pymupdf
import requests
from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .bootstrap import build_client
from .config import Settings
from .exceptions import IliasMcpError, ParseError
from .ilias.client import ILIASClient

_F = TypeVar("_F", bound=Callable[..., Any])


def _anticipated_errors(fn: _F) -> _F:
    """Turn the failures we expect into ToolError so the model sees the message.

    The MCP SDK treats every exception other than ToolError as a crash and
    hands the client only "Error executing tool <name>", which hid useful
    messages like "only supports PDF" or "session expired" from the model.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except ToolError:
            raise
        except (IliasMcpError, ValueError, zipfile.BadZipFile) as exc:
            raise ToolError(str(exc)) from exc
        except requests.HTTPError as exc:
            raise ToolError(f"ILIAS returned an HTTP error: {exc}") from exc

    return wrapper  # type: ignore[return-value]


mcp = MCPServer(
    "ilias-mcp",
    instructions=(
        "Tools for browsing and downloading course materials from ILIAS — a "
        "learning-management/e-learning platform used by many German and other "
        "European universities for lecture slides, exercises, course "
        "structure, and forum-based announcements. Relevant whenever the "
        "user asks about their university courses or coursework (lecture "
        'materials, exam prep, assignments, "what did the professor '
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
@_anticipated_errors
def list_courses(favorites_only: bool = False) -> list[dict]:
    """List the current user's ILIAS course/group memberships. By default
    returns every course/group the user belongs to; set favorites_only=True
    for just the personal dashboard's "Meine Kurse" widget (pinned items
    only, a strict subset)."""
    return [asdict(node) for node in _get_client().list_my_courses(favorites_only=favorites_only)]


@mcp.tool()
@_anticipated_errors
def list_container(ref_id: str) -> list[dict]:
    """List the direct children (folders, files, exercises, ...) of an ILIAS
    repository container, identified by its ref_id (as returned by
    list_courses/list_container itself). Only the items are returned — the
    text a course shows above them (welcome text, schedule, exam dates) is
    available via read_container_page."""
    try:
        nodes = _get_client().list_container(ref_id)
    except ParseError as exc:
        raise ToolError(
            f"Could not list ref_id {ref_id} as a container ({exc}). If this ref_id is a "
            "file (obj_type 'file' in the parent listing), use read_file or download_file instead."
        ) from exc
    return [asdict(node) for node in nodes]


@mcp.tool()
@_anticipated_errors
def read_container_page(ref_id: str) -> str:
    """Read the text an ILIAS course or folder shows on its own page above
    the item list — typically a welcome text, lecture times and rooms, exam
    dates and registration periods, tutorial info — given the container's
    ref_id (as for list_container). Collapsed accordion sections are
    included, their captions marked with "## "; link targets follow the
    link text in parentheses. Returns an empty string if the page has no
    such text. Embedded images are not captured."""
    return _get_client().read_container_page(ref_id)


@mcp.tool()
@_anticipated_errors
def list_forum_threads(ref_id: str) -> list[dict]:
    """List the threads in an ILIAS forum, identified by its ref_id (an item
    with obj_type "frm" from list_container). There's no separate
    "announcements" tool — a course's announcements are just a forum, often
    literally titled "Announcements" or "Organisatorisch" — find it via
    list_container first. Each thread includes a `url`; pass that to
    read_forum_thread to read its posts."""
    return _get_client().list_forum_threads(ref_id)


@mcp.tool()
@_anticipated_errors
def read_forum_thread(thread_url: str) -> list[dict]:
    """Read the posts in a forum thread, given the `url` field from one of
    list_forum_threads' results (not a ref_id). Note posts may name their
    author and can be written by other students, not just staff — be
    mindful before quoting or forwarding a post's content elsewhere."""
    return _get_client().read_forum_thread(thread_url)


@mcp.tool()
@_anticipated_errors
def list_exercise_assignments(ref_id: str) -> list[dict]:
    """List the assignment units of an ILIAS exercise (an item with
    obj_type "exc" from list_container), read-only — no submission/upload
    support by design, this can only look, never turn anything in on the
    user's behalf. Includes past/finished assignments, not just current
    ones. Each entry has assignment_id, title, state (ILIAS's own text,
    e.g. "Beendet"/"Läuft" — which of the Laufende/Kommende/Vergangene
    tabs it's in), and whatever properties ILIAS shows for it — commonly
    deadline, last_submission_date, submission_type, and grading_status.
    Dict keys are English; values are passed through as ILIAS's UI
    language returns them (German for a standard KIT account)."""
    return _get_client().list_exercise_assignments(ref_id)


@mcp.tool()
@_anticipated_errors
def download_file(ref_id: str) -> str:
    """Download an ILIAS file object by ref_id into the configured download
    directory and return the local file path."""
    path = _get_client().download_file(ref_id, Settings().download_dir)
    return str(path)


def _require_pdf(path: Path, tool_name: str) -> None:
    if path.suffix.lower() != ".pdf":
        raise ValueError(
            f"{tool_name} cannot read '{path.name}': supported are PDF"
            + (", plain-text and ZIP files" if tool_name == "read_file" else " files")
            + ". Use download_file for this file instead."
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


_TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".tex",
    ".py",
    ".java",
    ".c",
    ".h",
    ".xml",
    ".yaml",
    ".yml",
}
# Members of a ZIP are read into memory (never extracted to disk, so no
# path-traversal risk); skip anything unreasonably large.
_MAX_ZIP_MEMBER_BYTES = 50 * 1024 * 1024


def _pdf_text(doc: pymupdf.Document) -> str:
    return "\n\n".join(
        f"--- page {i + 1}/{doc.page_count} ---\n{page.get_text()}" for i, page in enumerate(doc)
    )


def _zip_text(path: Path) -> str:
    parts: list[str] = []
    with zipfile.ZipFile(path) as zf:
        members = [
            m for m in zf.infolist() if not m.is_dir() and not m.filename.startswith("__MACOSX/")
        ]
        parts.append(
            f"ZIP archive '{path.name}' with {len(members)} files: "
            + ", ".join(m.filename for m in members)
        )
        for member in members:
            suffix = Path(member.filename).suffix.lower()
            header = f"===== {member.filename}"
            if member.file_size > _MAX_ZIP_MEMBER_BYTES:
                parts.append(f"{header} (skipped: {member.file_size} bytes)")
            elif suffix == ".pdf":
                with pymupdf.open(stream=zf.read(member), filetype="pdf") as doc:
                    parts.append(f"{header} ({doc.page_count} pages)\n{_pdf_text(doc)}")
            elif suffix in _TEXT_SUFFIXES:
                parts.append(f"{header}\n{zf.read(member).decode('utf-8', errors='replace')}")
            else:
                parts.append(
                    f"{header} (not read: '{suffix or 'no extension'}' is not a text or PDF format; use download_file)"
                )
    return "\n\n".join(parts)


@mcp.tool()
@_anticipated_errors
def read_file(ref_id: str) -> str:
    """Download an ILIAS file object by ref_id and return its text content.
    PDFs come back page by page; plain-text files (.txt, .md, .csv, code, ...)
    as-is; ZIP archives as a member list followed by the text of every PDF
    and text file inside. Other formats (e.g. .docx, .xlsx, images) are not
    read; use download_file for those. Only the embedded PDF text layer is
    extracted: diagrams, images, handwriting, and scanned pages are not
    captured, so fall back to read_file_images for those. Prefer this tool
    first: it is far cheaper than read_file_images and usually sufficient for
    text-heavy material like lecture slides. The file is downloaded to a
    temporary location and deleted again immediately after its content is
    read, leaving nothing on disk."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = _get_client().download_file(ref_id, Path(tmp_dir))
        suffix = path.suffix.lower()
        if suffix == ".zip" or (
            suffix != ".pdf"
            and zipfile.is_zipfile(path)
            and suffix not in {".docx", ".xlsx", ".pptx"}
        ):
            return _zip_text(path)
        if suffix in _TEXT_SUFFIXES:
            return path.read_text(encoding="utf-8", errors="replace")
        _require_pdf(path, "read_file")
        with pymupdf.open(str(path)) as doc:
            return _pdf_text(doc)


# Claude Desktop/claude.ai reject a turn with more than 20 image blocks
# outright; the API allows more, but this server has no way to know which
# client is asking. Cap here with a clear error rather than letting a wide
# `pages` spec (or an omitted one, on a long document) fail opaquely on
# the client side.
_MAX_IMAGE_PAGES = 20


@mcp.tool(structured_output=False)
@_anticipated_errors
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
    dash). Capped at 20 pages per call (Claude Desktop/claude.ai reject
    more images than that in one turn); call this multiple times with
    different `pages` for a longer document rather than omitting `pages`
    on one you haven't checked the length of. The file is downloaded to a
    temporary location and deleted again immediately after rendering,
    leaving nothing on disk."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = _get_client().download_file(ref_id, Path(tmp_dir))
        _require_pdf(path, "read_file_images")
        with pymupdf.open(str(path)) as doc:
            page_indices = (
                _parse_page_spec(pages, doc.page_count) if pages else range(doc.page_count)
            )
            if len(page_indices) > _MAX_IMAGE_PAGES:
                raise ValueError(
                    f"{len(page_indices)} pages requested, but read_file_images is capped at "
                    f"{_MAX_IMAGE_PAGES} per call (Claude Desktop/claude.ai reject more images "
                    "than that in one turn). Narrow `pages` and call again for the rest."
                )
            return [
                Image(data=doc[i].get_pixmap(dpi=150).tobytes("png"), format="png")
                for i in page_indices
            ]


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
