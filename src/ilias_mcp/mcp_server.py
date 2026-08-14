from __future__ import annotations

from dataclasses import asdict

from mcp.server.mcpserver import MCPServer

from .bootstrap import build_client
from .config import Settings
from .ilias.client import ILIASClient

mcp = MCPServer(
    "ilias-mcp",
    instructions=(
        "Tools for browsing and downloading a student's ILIAS courses and course "
        "materials. Login happens lazily on first tool call, using the provider "
        "configured via ILIAS_PROVIDER and credentials from the environment/.env."
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
def download_file(ref_id: str) -> str:
    """Download an ILIAS file object by ref_id into the configured download
    directory and return the local file path."""
    path = _get_client().download_file(ref_id, Settings().download_dir)
    return str(path)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
