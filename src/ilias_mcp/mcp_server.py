from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from .bootstrap import build_client
from .config import Settings
from .ilias.client import ILIASClient
from .ilias.models import Node

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
def list_courses() -> list[dict]:
    """List the current user's ILIAS courses ("Meine Kurse" on the dashboard)."""
    return [node.__dict__ for node in _get_client().list_my_courses()]


@mcp.tool()
def list_container(ref_id: str) -> list[dict]:
    """List the direct children (folders, files, exercises, ...) of an ILIAS
    repository container, identified by its ref_id (as returned by
    list_courses/list_container itself)."""
    return [node.__dict__ for node in _get_client().list_container(ref_id)]


@mcp.tool()
def download_file(ref_id: str) -> str:
    """Download an ILIAS file object by ref_id into the configured download
    directory and return the local file path."""
    client = _get_client()
    node = Node(
        ref_id=ref_id,
        title=f"ilias_file_{ref_id}",
        url=f"{client.base_url}/ilias.php?ref_id={ref_id}&baseClass=ilrepositorygui",
    )
    path = client.download_file(node, Settings().download_dir)
    return str(path)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
