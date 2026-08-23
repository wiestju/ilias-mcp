from __future__ import annotations

import getpass
from pathlib import Path

import keyring
import typer
from rich.console import Console
from rich.table import Table

from .bootstrap import build_client
from .config import KEYRING_SERVICE, Settings, require_provider_name
from .exceptions import IliasMcpError
from .providers.registry import discover_providers, get_provider_class

app = typer.Typer(
    help="CLI for ILIAS with pluggable login providers (KIT via Shibboleth built in)."
)
console = Console()


@app.command()
def providers() -> None:
    """List registered login providers."""
    table = Table("name", "display name", "default base URL")
    for name, cls in sorted(discover_providers().items()):
        table.add_row(name, cls.display_name, cls.default_base_url)
    console.print(table)


@app.command()
def init(
    provider_name: str = typer.Option(
        None, "--provider", help="Provider to configure (default: ILIAS_PROVIDER / 'kit')"
    ),
) -> None:
    """Interactively store your ILIAS login in the OS keyring (macOS
    Keychain / Windows Credential Manager / Linux Secret Service) instead
    of a plaintext .env file — recommended for a real university password,
    which (unlike a scoped API key) can't be revoked or rate-limited if it
    leaks."""
    try:
        provider_cls = get_provider_class(
            require_provider_name(provider_name or Settings().ilias_provider)
        )
    except IliasMcpError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    prefix = provider_cls.name.upper()
    console.print(
        f"Storing credentials for [bold]{provider_cls.display_name}[/bold] "
        f"(provider: {provider_cls.name}) in the OS keyring."
    )
    for field in provider_cls.credential_fields:
        env_name = f"{prefix}_{field.upper()}"
        value = (
            getpass.getpass(f"{field}: ")
            if "password" in field.lower()
            else typer.prompt(field)
        )
        keyring.set_password(KEYRING_SERVICE, env_name, value)
    console.print("[green]Done.[/green] Run 'ilias-mcp login' to verify.")


@app.command()
def login() -> None:
    """Authenticate against ILIAS using the configured provider and report success."""
    try:
        build_client()
    except IliasMcpError as exc:
        console.print(f"[red]Login failed:[/red] {exc}")
        raise typer.Exit(1)
    console.print("[green]Login successful.[/green]")


@app.command()
def courses(
    favorites: bool = typer.Option(
        False,
        "--favorites",
        help="Only the Dashboard 'Meine Kurse' widget (pinned items) instead of all memberships",
    ),
) -> None:
    """List your course/group memberships (all of them by default)."""
    try:
        client = build_client()
        nodes = client.list_my_courses(favorites_only=favorites)
    except IliasMcpError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    table = Table("ref_id", "type", "title", "url")
    for node in nodes:
        table.add_row(node.ref_id, node.obj_type or "", node.title, node.url)
    console.print(table)


@app.command()
def tree(ref_id: str) -> None:
    """List the direct children of a repository container (course/folder)."""
    try:
        client = build_client()
        nodes = client.list_container(ref_id)
    except IliasMcpError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    table = Table("ref_id", "type", "title", "url")
    for node in nodes:
        table.add_row(node.ref_id, node.obj_type or "", node.title, node.url)
    console.print(table)


@app.command()
def download(
    ref_id: str,
    out: Path = typer.Option(None, "--out", help="Destination directory (default: configured download_dir)"),
) -> None:
    """Download a file object by its ref_id."""
    try:
        client = build_client()
        dest_dir = out or Settings().download_dir
        path = client.download_file(ref_id, dest_dir)
    except IliasMcpError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    console.print(f"[green]Saved to[/green] {path}")


@app.command("serve-mcp")
def serve_mcp() -> None:
    """Run the MCP server (stdio transport) for use with Claude Code / Claude Desktop."""
    from .mcp_server import main as mcp_main

    mcp_main()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
