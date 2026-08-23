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

Login, course listing, folder navigation, and file download are implemented
and verified end-to-end against a real KIT account (2026-08-14): the
Shibboleth login flow, `ilias_mcp/ilias/parsing.py`'s repository-item
parsing, and the `goto.php/file/<ref_id>/download` direct-download permalink
all work against live ILIAS pages, not just fixtures.

Roadmap, in priority order (see `.env.example` to get logged in):

1. ~~Course/folder tree listing~~ — done, live-verified.
2. ~~File download~~ — done, live-verified.
3. ~~Announcements/news per course~~ — done as generic forum reading
   (`list_forum_threads`/`read_forum_thread`); there's no separate
   "announcements" object type in ILIAS, a course's announcements are just
   a forum. Empty-forum state confirmed live (2026-08-23); the populated
   thread-row/post markup is still best-effort/unverified — none of the
   forums available to test against had any threads yet.
4. ~~Exercises/assignments~~ — done, read-only by design (no submit/upload
   tool exists or is planned). `list_exercise_assignments` returns each
   assignment's title, state, deadline, last submission date, submission
   type, and grading status (English dict keys; values pass through
   ILIAS's own UI-language text, German for a standard KIT account); uses
   `mode=all` rather than the page's own
   default (ongoing-only), which would hide a past semester's finished
   assignments entirely. Both the empty and populated states are
   live-verified (2026-08-23, ref_id 2911807, "Numerische Mathematik").

Known gaps:

- No MFA/passkey support yet — KIT's IdP form includes WebAuthn/SPNEGO
  options in the markup, but the login flow only drives the plain
  username/password path. Will need real-world testing against an
  MFA-enabled account to implement.
- ILIAS object types beyond files/folders/forums/exercises aren't readable
  yet: Learning Modules (`lm`) and Content Pages (`copa`) hold real text
  content directly in ILIAS (not a downloadable file) but only their title
  is currently surfaced via `list_container`; Opencast recordings (`xoct`)
  aren't accessible at all (deliberately not planned — see discussion,
  low value without a transcription pipeline).
- A generic "read any object's Info screen" tool (deadlines, file size,
  etc. — `ilInfoScreenGUI`) was attempted and reverted: ILIAS validates the
  `cmdNode` routing parameter server-side, and it can't be constructed
  from a bare ref_id without having actually navigated there first, so a
  direct URL 500s. `ilias_mcp/ilias/parsing.py`'s `parse_info_properties`
  is implemented and tested against real markup, just not wired to a
  reachable client method yet.

`list_my_courses()` (CLI: `courses`, MCP tool: `list_courses`) returns the
full membership overview (`ilMembershipOverviewGUI`) by default — every
course/group the user belongs to. Pass `favorites_only=True`
(`--favorites` on the CLI) for just the personal dashboard's "Meine Kurse"
widget instead, which is a strict subset of manually/automatically pinned
items — confirmed live to omit courses/groups the user is a member of but
never pinned to the dashboard.

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
`list_courses`, `list_container(ref_id)`, `download_file(ref_id)`,
`read_file(ref_id)` (PDF text, page by page), `read_file_images(ref_id,
pages=None)` (PDF pages as images, for diagrams/layout — call `read_file`
first and only reach for this on the specific pages that need it; capped
at 20 pages per call, since Claude Desktop/claude.ai reject a turn with
more images than that),
`list_forum_threads(ref_id)` and `read_forum_thread(url)` (a course's
announcements are just a forum — find it via `list_container`, there's no
separate announcements type), `list_exercise_assignments(ref_id)`
(deadlines, submission status, grading status per assignment — read-only,
no submit/upload tool). Login happens lazily on first tool call, and transparently
re-authenticates if the ILIAS session times out mid-chat.

**Credentials:** run `ilias-mcp init` once to store your login in the OS
keyring (macOS Keychain / Windows Credential Manager / Linux Secret
Service) instead of a plaintext file — recommended for a real university
password, which (unlike a scoped API key) can't be revoked or rate-limited
if it leaks. `.env` still works as a fallback (see Quickstart above).

**Registering the server itself**, per client — each command edits that
client's own config file in place (backing up the previous version first,
and doing nothing if already configured), no manual JSON/TOML editing:

```bash
ilias-mcp setup claude-desktop   # ~/Library/Application Support/Claude/claude_desktop_config.json
ilias-mcp setup codex            # ~/.codex/config.toml (Codex, inside the ChatGPT desktop app)
ilias-mcp setup cursor           # ~/.cursor/mcp.json
ilias-mcp setup windsurf         # ~/.codeium/windsurf/mcp_config.json
```

Restart the app afterwards. Any other MCP-compatible client can be wired
up the same way manually: point it at the `ilias-mcp-server` executable
inside this project's `.venv/bin/`, stdio transport.

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
