# ilias-mcp

A CLI and [MCP](https://modelcontextprotocol.io) server for [ILIAS](https://www.ilias.de/),
with a pluggable login-provider architecture. Ships with a built-in provider
for **KIT** (Karlsruhe Institute of Technology), which logs in via KIT's
Shibboleth Identity Provider — the same "KIT-Konto" button you'd click in a
browser.

Goals:

- Make navigating ILIAS from the terminal painless.
- Let tools like Claude Code pull course materials, structure, and
  announcements directly out of ILIAS as MCP tools.
- Support other universities' ILIAS instances as a plugin, without touching
  this codebase — see [Adding a provider](#adding-a-provider).

## Status

Early, pre-first-login state. The login flow (`shib_login.php` → Shibboleth
IdP → SAML response relay back into ILIAS) was implemented and unit-tested
against a real, unauthenticated fetch of KIT's login pages (see
`tests/fixtures/`), but has not yet been exercised against a real account.
The repository-listing HTML parsing (`ilias_mcp/ilias/parsing.py`) is
similarly provisional — ILIAS markup differs across versions/themes, and it
needs a real authenticated page to be dialed in.

Roadmap, in priority order (see `.env.example` to unblock the next step):

1. ~~Course/folder tree listing~~ — implemented, needs live-HTML verification.
2. ~~File download~~ — implemented, needs live-HTML verification.
3. Announcements/news per course — not started.
4. Exercises/assignments (deadlines, submission status) — not started.

## Quickstart

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# edit .env: ILIAS_PROVIDER=kit, KIT_USERNAME=..., KIT_PASSWORD=...

ilias-mcp providers          # list registered login providers
ilias-mcp login               # authenticate and report success/failure
ilias-mcp courses             # list "Meine Kurse"
ilias-mcp tree <ref_id>       # list a course/folder's direct children
ilias-mcp download <ref_id>   # download a file object by ref_id
ilias-mcp serve-mcp           # run the MCP server (stdio transport)
```

Run the test suite with `pytest`.

### Using it as an MCP server

Point your MCP client at `ilias-mcp-server` (installed console script) or
`python -m ilias_mcp.mcp_server`, stdio transport. Exposed tools:
`list_courses`, `list_container(ref_id)`, `download_file(ref_id)`. Login
happens lazily on first tool call.

For Claude Code, add it as an MCP server pointing at the
`ilias-mcp-server` executable inside `.venv/bin/`.

## Architecture

```
src/ilias_mcp/
  providers/
    base.py        AuthProvider ABC — the extension point
    registry.py     built-ins + entry_points-based plugin discovery
    shibboleth.py   generic Shibboleth/SAML2 browser-login flow
    kit.py          KIT concrete provider (just config, reuses Shibboleth flow)
  ilias/
    client.py       session-based ILIAS client (courses, tree, download)
    parsing.py       HTML parsing of ILIAS repository pages
    models.py         Node dataclass
  config.py          .env / environment settings + credential lookup
  bootstrap.py        wires provider + client + credentials together
  cli.py               Typer CLI
  mcp_server.py         MCP server (FastMCP), same operations as tools
```

Login and ILIAS access are deliberately separate concerns: `AuthProvider`
only knows how to turn credentials into an authenticated `requests.Session`;
`ILIASClient` only knows how to talk to ILIAS once it has one. Both are
constructed once, in `bootstrap.build_client()`, shared by the CLI and the
MCP server.

### Why session-based scraping instead of the ILIAS REST API?

The official ILIAS REST API plugin has to be enabled per-installation by an
administrator and isn't reliably available to regular student accounts.
Driving the same login flow and HTML pages a browser would is more work
up front but works everywhere ILIAS + Shibboleth is used, with no server-side
opt-in required. If your ILIAS instance *does* expose the REST plugin, adding
a REST-based `ILIASClient` alternative alongside this one is a reasonable
future extension — the `AuthProvider`/`ILIASClient` split already leaves room
for it.

## Adding a provider

Two ways, depending on whether it belongs in this repo:

**In-tree** (e.g. contributing another Shibboleth-based university):

1. Add `src/ilias_mcp/providers/your_uni.py` subclassing
   `ShibbolethAuthProvider` (or `AuthProvider` directly, if your institution
   doesn't use Shibboleth) and set `name`, `display_name`, `default_base_url`.
2. Register it in `providers/registry.py::_builtin_providers()`.

**Out-of-tree** (your own package, no changes to this repo):

```toml
# your_package/pyproject.toml
[project.entry-points."ilias_mcp.providers"]
your-uni = "your_package:YourUniProvider"
```

Once installed alongside `ilias-mcp`, `ilias-mcp providers` picks it up
automatically — set `ILIAS_PROVIDER=your-uni` and add
`YOUR-UNI_USERNAME`/`YOUR-UNI_PASSWORD` to `.env`.

## Debugging the login/parsing flow

ILIAS and IdP markup can and will drift. Set `ILIAS_MCP_DEBUG_DUMP=1` to
write every hop of the login flow to `./debug_dumps/*.html` (gitignored) for
inspection when something breaks.

## License

MIT — see `LICENSE`.
