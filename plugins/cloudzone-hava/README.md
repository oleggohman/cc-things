# Hava Cloud Diagrams (cloudzone-hava)

A Claude plugin that connects to [Hava.io](https://www.hava.io) and gives Claude
your automatically generated cloud architecture diagrams. Hava continuously
imports your connected AWS, Azure, GCP and Kubernetes accounts and draws
topology, security and container views from the real configuration.

With this plugin Claude can list and search your diagrams, inspect the
resources and dated version history of any of them, and export any view to
PNG, PDF, editable Visio (VSDX), CSV or JSON — saving the file locally when you
ask for one. It exposes 47 tools covering the whole useful Hava API — diagrams, resources,
version history, exports, notes, embeddable shares, source re-imports, and
administration of teams, projects and API tokens. It bundles a `hava-diagrams`
skill that teaches Claude which tool to reach for, which export formats work
with which views, how to handle Hava's asynchronous export jobs, and which
operations need confirmation first.

Destructive tools require an explicit `confirm=true`. Setting
`HAVA_MCP_READ_ONLY=1` removes every mutating tool from the list entirely,
leaving 19 read-only tools. Connecting cloud credentials and minting API
tokens are deliberately not exposed, because both would route secrets through
a conversation.

## Where it runs

**macOS only**, and in **Cowork or Claude Code** — not in claude.ai chat.
This plugin ships a local (`command`) MCP server, and chat only talks to hosted
HTTP connectors. Hava publishes no hosted MCP connector today, so chat support
is not available for it.

## Requirements

- macOS
- [`uv`](https://docs.astral.sh/uv) — `brew install uv`. This is a Python
  server and Claude ships no Python runtime; uv supplies Python 3.10+ and the
  dependencies on first launch. Node comes from Claude itself.
- A Hava API token, and a Hava Teams/Business plan or self-hosted install.

## Setup

**The only supported way to configure or update this plugin's Hava API token
is from Claude Code running in a terminal, using
`/plugin configure cloudzone-hava@synced`.**

Get your token from app.hava.io → avatar → **Personal Settings** → **API
Tokens** → **Display Token**.

1. Open **Terminal** (or iTerm) on your Mac.
2. Run `claude` to start Claude Code.
3. Inside that Claude Code session, enter:

   ```text
   /plugin configure cloudzone-hava@synced
   ```

4. Paste your token into the **Hava API token** field and save.
5. Restart Claude or open a new session, then check with `hava_auth_status`.

Enter the slash command **inside Claude Code**, after starting `claude`;
it is not a shell command. Use this same flow whenever the token needs to be
changed.

Installing the plugin does not configure the token. Its skill may load while
the `hava_*` tools are missing until setup is complete. Chat messages,
plugin menus, environment variables, config files, and server tools are not
supported ways to configure the token.

If tools remain missing, run `claude plugin list` in the terminal and check
that `cloudzone-hava@synced` is loaded. Resolve any duplicate Hava
installation that shadows it, then repeat the same slash command inside
Claude Code.

Read-only mode is an optional setting in the same configuration flow. The
endpoint defaults to `https://api.hava.io`.

## Data

What this plugin sends, and where:

- **To Hava's API** (`https://api.hava.io`, or your own host if `HAVA_ENDPOINT`
  is set): your API token on every request, plus the diagram, view, revision
  and job IDs and any search query you ask about. No other data leaves your
  machine, and nothing is sent to CloudZone.
- **From Hava to you**: diagram metadata, cloud resource details (names, types,
  regions, provider IDs, estimated monthly prices, tags) and export artifacts.
  Exports are served from Hava's CDN over short-lived signed URLs; the server
  deliberately omits your token on those requests so it is never sent to the
  CDN.
- **Stored locally**: Claude manages the token configured through the terminal
  flow above. The server does not store credentials or cache diagram contents.
  Export files are written locally when you pass `save_to`.

Resource names and cloud account IDs are part of the tool output and so enter
the conversation. Treat a Hava API token as a credential for your cloud
inventory metadata.

## License

MIT — see `LICENSE`. Built by CloudZone against the Hava REST API v1.1.6.
Hava is a trademark of its owner; this plugin is not affiliated with Hava.io.
