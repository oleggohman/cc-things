# hava-mcp

An MCP server for [Hava](https://hava.io) — automated AWS / Azure / GCP /
Kubernetes architecture diagrams. It lets an MCP client list and search your
Hava diagrams and export any view to PNG, PDF, Visio (VSDX), CSV, or JSON.

Built against the Hava REST API v1.1.6
([SwaggerHub](https://app.swaggerhub.com/apis-docs/H252/hava); the spec is
vendored at `reference/hava-openapi-1.1.6.json`).

## Vocabulary

Hava's UI says *diagram*; the API says **environment**. Each environment holds
several **views**:

| short name       | Hava view type                   | notes                                   |
| ---------------- | -------------------------------- | --------------------------------------- |
| `infrastructure` | `Views::Infrastructure`          | the clean topology diagram              |
| `extended`       | `Views::Infrastructure::Extended`| topology plus extra detail              |
| `security`       | `Views::Security`                | security groups and open ports (AWS/Azure) |
| `container`      | `Views::Container`               | containerised workloads                 |
| `list`           | `Views::List`                    | every resource, visualised or not       |

Exports act on a **view**, not an environment — so the usual flow is
list/find a diagram → pick a view → export it.

## Install

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
```

## Authentication

**The only supported way to configure the plugin's Hava API token is from
Claude Code running in a terminal, using
`/plugin configure cloudzone-hava@synced`.** Use this same command to replace
or update the token.

Get your token from <https://app.hava.io/settings/profile>:
avatar → **Personal Settings** → **API Tokens** → **Display Token**.

1. Open **Terminal** (or iTerm) on your Mac.
2. Run `claude` to start Claude Code.
3. Inside that Claude Code session, enter:

   ```text
   /plugin configure cloudzone-hava@synced
   ```

4. Paste your token into the **Hava API token** field and save.
5. Restart Claude or open a new session, then check authentication with
   `hava_auth_status`.

The slash command is entered **inside Claude Code**, after starting
`claude`; it is not a shell command.

Installing the plugin does not configure the token. Until setup is complete,
the skill may be available while the `hava_*` tools are missing. Token setup
must use the terminal flow above; chat messages, plugin menus, environment
variables, config files, and server tools are not supported setup methods.

If tools are still missing, run `claude plugin list` in the terminal and
check that `cloudzone-hava@synced` is loaded. Resolve any duplicate Hava
installation that shadows the synced plugin, then repeat the same slash
command inside Claude Code.

**Read-only mode** is an optional setting in the same configuration flow; it
hides every mutating tool. The API endpoint defaults to `https://api.hava.io`.
For a self-hosted Hava deployment, `HAVA_ENDPOINT` changes the endpoint only;
it is not an API-token configuration method.

API access requires a Hava Teams/Business plan or a self-hosted install.

## Register with this project

A `.mcp.json` is already checked in, pointing at `.venv/bin/hava-mcp`, so any
MCP client opened in this directory can discover the local server. This file
does not configure an API token. Configure the synced plugin through the
terminal flow in **Authentication** above.

For Codex, the equivalent is a `.codex/config.toml` in this checkout —
gitignored, so write your own. Codex hands a local server only its own
environment allowlist, a server's literal `env` and the names listed in
`env_vars`, so the token has to be named there while its value stays in the
shell that starts `codex`:

```toml
[mcp_servers.hava]
command = "/absolute/path/to/hava_mcp/.venv/bin/hava-mcp"
env_vars = ["HAVA_API_TOKEN", "HAVA_ENDPOINT", "HAVA_MCP_READ_ONLY"]
startup_timeout_sec = 30
tool_timeout_sec = 120
```

Do not set `HAVA_MCP_HOST = "codex"` here: it switches the missing-token advice
to the packaged plugin's `~/.hava-mcp/api_token` file, which only the plugin's
`launch.sh` reads. A server started directly like this takes the token from
`HAVA_API_TOKEN` alone.

## Codex

`./scripts/build.sh codex` produces `cloudzone-hava-mcp-codex-v<version>.zip`,
a portable [Agent Plugins](https://agent-plugins.org) package for Codex CLI,
the Codex IDE extension and Codex in the ChatGPT desktop app. Unzip it and run
`./install.sh`: it copies the plugin to `~/.codex/plugins/cloudzone-hava`,
registers it in the personal marketplace `~/.agents/plugins/marketplace.json`
and test-builds the Python environment, which also fills uv's download cache.
Then restart Codex, run `/plugins`, pick **Personal plugins** and install
`cloudzone-hava`. The first Codex start is still slower than later ones: Codex
gives the plugin its own data directory, so the server builds its environment
once more there, from the cache.

Codex has no install-time prompt and does not forward your shell environment to
a plugin's bundled server, so its launcher reads the token from
`~/.hava-mcp/api_token` (chmod 600), with `~/.hava-mcp/endpoint` and
`~/.hava-mcp/read_only` as the other two switches. The bundled `hava-setup`
skill walks through all of it. `packaging/codex/README.md` is the package's own
documentation.

Because the server is local (stdio), the package is not eligible for the public
plugin directory; a ChatGPT workspace admin can still publish it to the
workspace from **Plugins → Personal → Publish**.

## Tools

47 tools covering every endpoint in the Hava API worth exposing. `[W]` changes
something in Hava; `[!]` is destructive and requires `confirm=true`.

| area | tools |
| --- | --- |
| Find diagrams | `hava_list_diagrams`, `hava_find_diagrams` |
| Inspect | `hava_get_diagram`, `hava_list_diagram_versions` |
| Resources | `hava_list_resources`, `hava_export_resources` `[W]` |
| Export | `hava_export_diagram` `[W]`, `hava_get_job` |
| Custom diagrams | `hava_create_diagram` `[W]`, `hava_update_diagram` `[W]`, `hava_delete_diagram` `[!]` |
| Notes | `hava_list_diagram_notes`, `hava_create_diagram_note` `[W]`, `hava_delete_diagram_note` `[!]` |
| Shares | `hava_list_diagram_shares`, `hava_get_diagram_share`, `hava_create_diagram_share` `[W]`, `hava_update_diagram_share` `[W]` |
| Reports | `hava_list_reports`, `hava_get_report`, `hava_export_report` `[W]` |
| Sources | `hava_list_sources`, `hava_get_source`, `hava_sync_source` `[W]`, `hava_create_source` `[W]`, `hava_update_source_credentials` `[W]`, `hava_rename_source` `[W]`, `hava_delete_source` `[!]` |
| Teams | `hava_list_teams`, `hava_get_team`, `hava_create_team` `[W]`, `hava_update_team` `[W]`, `hava_delete_team` `[!]`, `hava_add_team_member` `[W]`, `hava_invite_team_member` `[W]`, `hava_remove_team_member` `[!]` |
| Projects | `hava_list_projects`, `hava_get_project`, `hava_create_project` `[W]`, `hava_update_project` `[W]`, `hava_delete_project` `[!]`, `hava_add_project_member` `[W]`, `hava_remove_project_member` `[!]` |
| API tokens | `hava_list_api_tokens`, `hava_create_api_token` `[W]`, `hava_delete_api_token` `[!]` |
| Auth | `hava_auth_status` |

Every tool takes `response_format`: `markdown` (default, compact and readable)
or `json` (full structured records). Full parameter reference:
`skills/hava-diagrams/references/tools.md`.

### Read-only mode

Tick **Read-only mode** when enabling the plugin, or set `HAVA_MCP_READ_ONLY=1`.
Mutating tools are then **not registered at all** — the model never sees a tool
it must not call. That leaves the 19 reading tools. Recommended wherever the
server is exposed to something you do not fully control.

### Account ID

Every `/accounts/{account_id}/...` route needs an account ID, and Hava has no
endpoint that reports one. The API token is a JWT whose `sub` claim is the
account ID (verified against the live API), so the org tools derive it
automatically; pass `account_id` only to target a different account.

### Tools that handle secrets

`hava_create_source` only connects AWS accounts through a cross-account role,
which carries no secret. `hava_update_source_credentials` and
`hava_create_api_token` pass long-lived credentials (AWS keys, Azure client
secrets, GCP service-account JSON, a new API token) through the conversation,
so they land in the transcript. Secrets are never echoed back by the source
tools; a new API token is shown once in the result. Use read-only mode to hide all of them.

### Export format / view compatibility

Verified against the live API — `hava_export_diagram` checks this before
calling Hava, so you get a useful message instead of a 422:

| format | views it accepts |
| --- | --- |
| `png`, `pdf` | infrastructure, extended, security, container (**not** list) |
| `vsdx` | infrastructure **only** |
| `csv`, `json` | every view |

### Export notes

Exporting is asynchronous. `hava_export_diagram` queues the job, polls it for
up to `wait_seconds` (default **100**), and returns a **time-limited** download
URL. Pass `save_to` to write the file locally as well:

```
hava_export_diagram(
    diagram_id="…", view="security", export_format="vsdx",
    save_to="./exports/", labels=true, connections=true,
)
```

If the job is still running when the budget runs out, the job ID comes back —
hand it to `hava_get_job`.

The 100s default is deliberate: most MCP clients (Claude Code included) abort a
tool call at 120s, so a longer budget would get the whole call killed instead of
returning a usable job ID. Large diagrams really do exceed this — a 461-resource
VPC took over two minutes to render as VSDX. Either leave the default and poll
with `hava_get_job`, or raise the client's limit (`MCP_TOOL_TIMEOUT` in Claude
Code) alongside `wait_seconds`.

Not every diagram has every view: security views exist for AWS and Azure only,
and container views only where containerised resources were discovered. Asking
for a missing view returns an error naming the views that do exist.

## Hava API quirks worth knowing

Behaviours confirmed against the live API that the OpenAPI spec does not state:

- **`GET /sources` returns `{total_size, results}`**, not the bare array the
  spec shows.
- **`page_size` has a server-side floor of 10** on `/environments` — asking for
  3 still returns 10.
- **Pagination is cursor-based.** `next_page_token` carries the sort order, so
  `hava_list_diagrams` sends `sort=name&sort_dir=asc` by default to keep a
  resumable walk stable. Passing `page_token` supersedes the other paging args.
- **`GET /search/environments` is fragile.** It needs `field:value` syntax
  (`vpc:vpc-1234`); bare words return 422, and some well-formed queries return
  500. `hava_find_diagrams` says so and points you at `name_contains`.
- **Export artifacts are served from CloudFront** with a short-lived signed
  URL, not from `api.hava.io`. The client deliberately omits the Hava token on
  those requests so it is never sent to the CDN.
- **`GET /jobs/{id}` answers `303`** with the artifact in the `location` header,
  so the HTTP client does not follow redirects.
- **`GET /resources` returns a bare JSON array**, not a paginated object, and
  it is unbounded: `region:eu-west-1` matched **13,979** resources on a real
  account. `hava_list_resources` leads with a per-type breakdown and caps the
  listing.
- **Search `type:` and `name:` do not work** despite appearing in Hava's docs —
  they match nothing. Fields verified to work: `source:`, `region:`, `vpc:`,
  `cluster:`, and tag filters such as `CostCenter:DEV`. Bare words give a 422.
  `hava_list_resources` offers `type_contains` to filter client-side.
- **`PUT /environments/{id}` silently ignores `name`.** It returns 200 and the
  old name, and the rename never applies. `hava_update_diagram` re-reads the
  diagram and says so rather than implying success.
- **Environments report an undocumented `importing` state** alongside the
  documented `active`/`pending`, and views only exist once the state is
  `active`.
- **Reports need a higher plan**: `GET /reports` returned 403 on the account
  this was built against. The report tools surface that explicitly.

## Building the distributables

```bash
./scripts/build.sh            # all three artifacts
./scripts/build.sh plugin     # just the Claude org plugin zip
./scripts/build.sh mcpb       # just the Claude Desktop extension
./scripts/build.sh codex      # just the Codex plugin zip
OUT_DIR=/tmp ./scripts/build.sh
```

Filenames carry the version from `pyproject.toml`, so releases do not overwrite
each other:

```
cloudzone-hava-0.4.1.zip               # Claude organization -> Plugins & skills
hava-mcp-0.4.1.mcpb                    # Claude Desktop, double-click to install
cloudzone-hava-mcp-codex-v0.4.1.zip    # Codex: unzip, then ./install.sh
```

To cut a new version, bump `version` in `pyproject.toml` *and* `__version__` in
`src/hava_mcp/__init__.py`, then re-run the script. It regenerates the tools
reference, probes the server for its live tool list, writes that into the
`.mcpb` manifest, stamps the version into both manifests, validates both, and
packs them.

Version 0.4.1 pins MCP SDK 1.30.0 (1.x line; 0.3.9 introduced the 1.x pin) for
Claude Desktop compatibility. Its legacy
handshake remains valid even when Claude sends `server/discover` first and
falls back to `initialize` after a startup timeout. This avoids the
"connection is serving the 2026-07-28 protocol" error in Cowork/Code sessions.
Do not upgrade to SDK 2.x until Claude's fallback has been verified to open a
fresh transport after an inconclusive modern probe.

Both packages include `uv.lock`. The launcher installs with `uv sync --locked`
into an external per-user environment, and the environment fingerprint includes
the lockfile. It reports a build error rather than falling back to an unlocked
installation. After changing dependencies or the project version, run `uv lock`
before building. Every build checks the packed launcher by importing it as a
module, negotiating stdio, listing tools, and calling the offline auth diagnostic.

Packaging inputs live in `packaging/` (icon, the manifests, the launchers, and
`plugin/mcp.json`, which is written to the Claude bundle as `.mcp.json`).
`packaging/codex/` holds the Codex package: a portable `plugin.json` and
`mcp.json`, the `hava-setup` onboarding skill, `install.sh`, and `launch.sh` —
a shell launcher, because Codex ships neither Node nor Python. The Codex build
validates the assembled package with `scripts/check_codex_package.py` and
smoke-tests the packed zip the way Codex starts it, `sh <root>/server/launch.sh`.

## Development

```bash
.venv/bin/python -m pytest    # 133 offline tests against a mocked Hava API
```

The test suite never touches the network: `respx` mocks the API, and
`tests/conftest.py` clears any ambient Hava configuration.

Layout:

```
packaging/       inputs for scripts/build.sh (manifests, icon, launcher)
scripts/
  build.sh       builds both versioned artifacts
  gen_tools_reference.py  regenerates the skill's tools.md
  probe_tools.py          live tool list for the .mcpb manifest
src/hava_mcp/
  app.py         the MCP server instance + shared tool scaffolding
  auth.py        reads HAVA_API_TOKEN; that is the whole auth model
  cli.py         hava-mcp status / serve
  client.py      async Hava REST client, error translation, job redirects
  errors.py      HavaError, HavaConfigError
  formatting.py  payload shaping + Markdown rendering
  server.py      core diagram/export tools, wires in the tools package
  views.py       friendly view names <-> Hava view types
  tools/         the rest of the API surface, one module per area
skills/hava-diagrams/
  SKILL.md       how an agent should use these tools
  references/tools.md   generated from a live tools/list
```
