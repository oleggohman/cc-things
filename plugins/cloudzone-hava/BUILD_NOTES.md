# cloudzone-hava build notes

## 0.4.1 - a Codex package

Adds a third artifact, `cloudzone-hava-mcp-codex-v<version>.zip`, built by
`scripts/build.sh codex` from `packaging/codex/`. It is the portable
[Agent Plugins](https://agent-plugins.org) format Codex reads - root
`plugin.json` + `mcp.json` + `skills/` - carrying the same server and the same
`hava-diagrams` skill as the Claude plugin, plus a Codex-specific
`hava-setup` onboarding skill and an `install.sh`.

Three things could not be carried over from the Claude packaging, and each one
is a deliberate difference rather than an omission:

- **No Node.** Claude Desktop ships Node and no Python, which is why
  `launch.mjs` exists; Codex ships neither. The Codex package uses
  `server/launch.sh` instead - same prepared-virtualenv design (stamped on the
  source + lockfile, built under a `mkdir` lock, detached so a build survives
  the client giving up), minus the Electron stdio bridging, which a Codex stdio
  server does not need because its fd 0/1 really are the MCP stream. `uv`
  remains the only prerequisite. `launch.sh --prepare` builds in the
  foreground and exits; `install.sh` and the build's smoke test both use it.
- **No install-time prompt, and no env to inherit.** Codex has no
  `user_config` equivalent, and - confirmed in the Codex source, not just the
  docs - it hands a stdio server only its own env allowlist, the literal `env`
  from the server config, and the names a `config.toml` server lists in
  `env_vars`. A plugin's bundled server can declare none of those, so an
  exported `HAVA_API_TOKEN` normally never arrives. The launcher therefore
  resolves configuration itself, from `~/.hava-mcp/{api_token,endpoint,read_only}`
  (`HAVA_MCP_CONFIG_HOME` relocates them), with the environment still winning
  where it does arrive. This re-introduces a credential file, which 0.3.0
  removed for the Claude artifacts - those still have exactly one setting, and
  nothing about them changed.
- **Advice a Codex user can follow.** `auth.require()` printed Claude's
  `/plugin configure` instructions to everyone. `auth.setup_instructions()`
  now picks by `HAVA_MCP_HOST`, which the Codex launcher sets to `codex`;
  every other host keeps the old text verbatim.

One bug shipped in the first build of this package and is worth recording,
because nothing about the package looked wrong: `install.sh` wrote
`"authentication": "ON_FIRST_USE"` into the marketplace entry (a value the
MCPB-builder skill's own packer offers). codex-cli deserializes that field as
an enum accepting only `ON_INSTALL` or `ON_USE`, and an unknown variant makes
it reject **the whole marketplace file** - every plugin in it, not just ours.
`codex plugin marketplace list` says so exactly; ChatGPT says only "Could not
add plugin. Please try again." It is now `ON_USE` (this server authenticates
when a tool runs, not at install), and the build installs the packed zip into
a throwaway `HOME` and has the real `codex` CLI confirm it:
`verify_codex_install` asserts the marketplace loads, `codex plugin add`
installs and enables the plugin, and `codex mcp list` shows the server
pointing at the cached `server/launch.sh`. Verified against codex-cli 0.162.1 and 0.169.0,
which also confirms `${PLUGIN_ROOT}` expansion in `args` and that Codex
injects `PLUGIN_ROOT`/`PLUGIN_DATA` into the server's environment.

`scripts/check_codex_package.py` validates the assembled package against the
1.0.0 Agent Plugins schemas' rules (exact `$schema`, kebab `name`, no
root property the schema forbids, `./`-prefixed `extensions."com.openai"`
paths that exist, a transport `type` per server, no `${user_config.*}`
leftovers, skill frontmatter `name` == folder, version higher than the newest
zip already in the output directory). The schemas are not fetched: a build
must not need the network.

The build then smoke-tests the **packed** zip the way Codex starts it -
`sh <root>/server/launch.sh` - and asserts its `tools/list` is identical to
the one probed from source.

Verified here: install into a throwaway `HOME` (plugin copied to
`~/.codex/plugins/cloudzone-hava`, personal marketplace upserted without
disturbing an unrelated entry, re-install idempotent), token resolution in all
four states (env, file, env over file, unexpanded `${...}` placeholder
dropped), `read_only` reducing 47 tools to 19 through the launcher, and
`hava_auth_status` returning the Codex setup text, and - through
`verify_codex_install` above - the `codex` CLI loading the marketplace,
installing and enabling the plugin and registering its server. Not tested: an
interactive Codex session starting the server and calling its tools, and the
ChatGPT desktop app.

A bundled stdio server keeps this package out of the public plugin directory;
workspace publishing (ChatGPT -> Plugins -> Personal -> Publish) is unaffected.

## 0.4.0 - secret-handling tools

Adds `hava_create_source` (AWS cross-account role only),
`hava_update_source_credentials` and `hava_create_api_token`: 47 tools in total.
The last two pass credentials through the conversation. Skill is now version 3.

## 0.3.9 - Claude Desktop protocol compatibility

Claude Desktop 2.31226.1 can time out its modern discovery probe, then send a
legacy `initialize` on the same connection. MCP SDK 2.3.0 commits that
connection to the protocol selected by the first request, so this produces
error -32022 even though a fresh connection works with either protocol.

This release pins MCP SDK 1.29.0 and restores its FastMCP and camelCase model
APIs. The server stays on the legacy handshake protocol; a modern discovery
probe is rejected without preventing a subsequent `initialize`. Hava's
version is explicitly set on FastMCP's underlying server (the 1.x constructor
does not accept a version argument).

Packages now include `uv.lock` and install with `uv sync --locked --no-dev
--no-editable` into the prepared external environment. The lockfile is included
in the environment fingerprint. Builds record failure and the launcher reports
it; there is no unlocked fallback. These details supersede the older build
descriptions below.

Regression tests cover fresh initialize, discovery followed by initialize,
and both requests queued during a startup delay exceeding Claude's 2s probe.
The build probes each unpacked artifact through a module-imported Node launcher,
including a real offline tools/call. No Hava credentials are needed for testing.

| | |
|---|---|
| Deliverables | `cloudzone-hava.zip` (org upload) and `hava-mcp.mcpb` (direct Claude Desktop install) |
| Server version | 0.1.0 (CloudZone-authored, not an upstream package) |
| Mode | **launcher** — Node launcher + bundled Python source, run through `uv` |
| Platforms | **macOS only** (`darwin`); the Windows discovery branch was removed as untested |
| Entry point | `server/launch.mjs` (`type: node`, `command: node`) |
| Hava API | REST v1.1.6, spec vendored in the source project at `reference/` |
| License | MIT (shipped at `server/LICENSE`) |

## Why a Node launcher for a Python server

This is a Python MCP server, and the obvious manifest (`"command": "uvx"`)
fails on a real Claude Desktop install. Three findings from this machine:

1. **Claude Desktop ships Node but no Python and no uv.** Only
   `app.asar.unpacked/node_modules` exists under `Claude.app`.
2. **The system `python3` is 3.9.6**, below this server's 3.10 floor — its
   `str | None` annotations are evaluated by Pydantic at import time.
3. **GUI apps on macOS do not inherit a shell PATH.** `uv` lives at
   `/opt/homebrew/bin/uv`, which is invisible to an app launched from Finder,
   so a bare `uvx` would die with `ENOENT`.

So `server/launch.mjs` runs on the Node that Claude Desktop guarantees, finds
`uv` itself, and runs `uv tool run --python '>=3.10' --from <bundle>/server
hava-mcp`, bridging the MCP stream to it explicitly (see 0.3.6 below).
uv supplies Python 3.10+ and the dependencies, building into its own cache so
nothing is written inside the (possibly read-only) extension directory.

**Prerequisite:** `uv` on the user's machine. If absent, the launcher writes
install instructions to stderr and exits 1, which surfaces in the extension
log. `HAVA_MCP_UV` overrides the discovered path.

## Token resolution (highest priority first)

1. `HAVA_API_TOKEN` / `HAVA_TOKEN` / `HAVA_API_KEY` from the environment —
   this is what the install-time `user_config.api_token` field becomes.
2. `$HAVA_API_TOKEN_FILE`, `~/.hava-mcp/api_token`, or `~/.hava/api_token`,
   because desktop apps do not inherit shell exports.
3. Nothing — the server then falls back to the OS keychain, which is populated
   by running `hava-mcp login` once.

Blank values and unexpanded `${user_config.*}` placeholders are dropped rather
than passed through as a literal token.

## Patches applied

None. The server is first-party code with no main-module guard: `cli.py`
exposes `main()` as a console script and `server.py` guards only its
`__main__` block, which the launcher never relies on.

## Verification

- `mcpb validate manifest.json` — schema passes, icon passes (512×512).
- `probe_server.py --non-main -- node server/launch.mjs` with **all** Hava env
  vars unset: MCP handshake succeeds, 10 tools listed, stdout clean (uv writes
  progress to stderr only).
- Token chain exercised in all three modes (env / key file / keychain
  fallback), including an unexpanded placeholder and a whitespace-only
  endpoint.
- Re-probed after unzipping the packed `.mcpb`, not just the build directory.
- `__pycache__`/`*.pyc` excluded via `.mcpbignore` — a first pack shipped 16
  stale `.pyc` files for Python 3.12 and 3.14.

## Not tested

Installation in Claude Desktop itself, and Windows/Linux `uv` discovery paths
(the fallback lists are written but only the macOS Homebrew path was exercised).

## Org-upload packaging (added after the first MCPB build)

The target changed to "installed from the Claude organization, macOS only", so
the primary artifact is now `cloudzone-hava.zip`:

- `.claude-plugin/plugin.json` sits at the zip root; name is prefixed
  `cloudzone-` with a `displayName`, so it cannot collide with a future
  official Hava plugin.
- Org plugins have **no install-time `user_config`**, so the token can no
  longer be typed at install. `.mcp.json` uses `${HAVA_API_TOKEN:-}` (empty
  rather than failing when unset) and the launcher's key-file and Keychain
  fallbacks become the primary setup path, documented in the README and skill.
- `skills/hava-diagrams/` ships alongside the server, which an `.mcpb` cannot
  carry. `references/tools.md` is generated from a live `tools/list`, and every
  tool and parameter the skill cites was checked against it.
- `compatibility.platforms` is `["darwin"]` and the launcher's uv search is
  macOS-only.

**Limitation to flag to users:** a local `command` MCP server is ignored by
claude.ai chat; it runs in Cowork and Claude Code only. Hava offers no hosted
MCP connector, so there is no HTTP-connector alternative to pair with it.

## Versioned artifacts and a reproducible build (0.3.0)

Both artifacts are now produced by `scripts/build.sh` from `packaging/`, and
their filenames carry the version from `pyproject.toml`:

```
cloudzone-hava-<version>.zip
hava-mcp-<version>.mcpb
```

Earlier builds wrote unversioned `cloudzone-hava.zip` / `hava-mcp.mcpb`, which
overwrote the previous release and made it impossible to tell two uploads
apart. Those names are retired; any left in the output folder are superseded.

The script regenerates `skills/hava-diagrams/references/tools.md`, probes the
server for its live tool list and writes it into the `.mcpb` manifest (so the
manifest can never drift from the code), stamps the version into both
manifests, runs `mcpb validate` and `claude plugin validate --strict`, and
packs. `packaging/plugin/mcp.json` is stored dot-less because the build sandbox
refuses to write paths named `.mcp.json`; the build copies it into place.

## Authentication, as of 0.3.0

One setting, no fallbacks. Both artifacts declare install-time configuration -
`userConfig` for the plugin (prompted when enabled; sensitive values go to OS
secure storage) and `user_config` for the `.mcpb` - and deliver it as
`HAVA_API_TOKEN`. The `hava_login`/`hava_logout` tools, the `login`/`logout`
CLI commands, the keychain write, the credential file, the key-file fallbacks
and the `HAVA_TOKEN`/`HAVA_API_KEY` aliases were all removed, along with the
`keyring` dependency. The launcher drops blank and unexpanded `${...}` values
so a failed substitution reports "not configured" instead of authenticating
with a literal placeholder.

## 0.3.6 - the Desktop install actually works

"Not tested: installation in Claude Desktop itself" (above) was hiding a real
bug. Symptom: the extension starts, Desktop logs `Server started and connected
successfully`, the client's `initialize` goes out, and ~900ms later `Server
transport closed unexpectedly`, on a loop. No Python traceback, no uv error -
`uv` reported `Built hava-mcp` / `Installed 32 packages` and nothing else.

Cause: Claude Desktop does not run an `.mcpb` as a plain Node process. The log
says so - `Using UtilityProcess for extension ...: appConfig
.isUsingBuiltInNodeForMcp is true` - and an Electron **UtilityProcess** has no
real fd 0/1 carrying the MCP stream; the stream reaches the script only as
`process.stdin` / `process.stdout`, over an Electron pipe. The launcher spawned
`uv` with `stdio: "inherit"`, so the Python server inherited an unrelated,
already-closed fd 0, read EOF at once and exited cleanly. Every symptom follows
from that, including the silence.

This never showed up anywhere else: Claude Code and the CLI spawn the launcher
as an ordinary process where fd 0/1 *are* the stream, so `inherit` is correct
there and the plugin build worked throughout.

Fix: `stdio: ["pipe","pipe","pipe"]`, with `process.stdin -> child.stdin`,
`child.stdout -> process.stdout` and `child.stderr -> process.stderr` wired up
by hand. Correct under both runtimes. The exit handler now sets
`process.exitCode` instead of calling `process.exit()`, which would drop
whatever the server had written but not yet flushed, and EPIPE on a
torn-down pipe is swallowed rather than logged as an error.

Note for debugging: the launcher's own stderr does **not** appear in
`~/Library/Logs/Claude/mcp-server-<name>.log` for a UtilityProcess extension.
It goes to `~/Library/Logs/Claude/main.log`, prefixed `[UtilityProcess
stderr]`. The per-server log looked empty and implied the launcher had never
run; it had.

## 0.3.7 - the server starts every time, not most times

Symptom: on a cold start the extension either came up normally or failed, with
no pattern. The log alternated between `Era probe verdict: modern (sibling
answered server/discover)` and `legacy (sibling did not complete the
exchange)`, the latter followed by `Version negotiation failed: the connection
closed during the server/discover probe`. Same machine, same build, same
minute.

Cause: a race, not a bug in the server. Timing the log entries from
`Initializing server...` to the probe verdict separates cleanly - 0.60, 0.72,
0.78, 0.79, 0.83, 0.98, 1.03, 1.50, 1.78s all came back `modern`; 2.13, 2.37,
3.02, 3.03, 3.32, 4.00s all came back `legacy`. The client gives a freshly
spawned server about two seconds to answer its capability probe, and our
startup sat right on that line:

    uv tool run --from <dir>   0.2s warm, 3.5s cold   <- resolve, build, install
    python -c "import hava_mcp.server"   0.44s warm, 1.5s cold
    node boot                  ~0.08s

Warm and quiet that is ~0.7s and the probe succeeds. Cold, or with any disk or
network jitter, `uv tool run` has to re-resolve requirements and rebuild the
local package before Python starts, and the launch lands past the deadline.
Nothing crashes - the client simply gives up first and reports a protocol
failure, which sent the investigation at the handshake instead of at the
clock. (`mcp` accounts for 0.38s of the 0.44s import; that part is a floor.)

Fix: take uv off the hot path. The launcher now builds a virtualenv once into
`~/Library/Application Support/hava-mcp/venv-<hash>` and, on every later
launch, execs that interpreter directly - no resolver, no network, no build.
Measured time-to-`initialize`-response: 617, 626, 660, 680ms across runs,
against 0.6-4.0s before.

The hash covers `pyproject.toml` and every source file, so a new version - or
an edited working copy - rebuilds instead of silently running stale code.
`HAVA_MCP_HOME` overrides the location.

Two details that matter more than they look:

- The build is **detached**. The client kills a server that misses the probe
  deadline, so a build that died with the launcher would restart from nothing
  on the next launch and never finish. Killing the launcher at 2s, the build
  still completed at 4s and the next launch was on the fast path.
- The build is **locked** (`mkdir` on `.building`, cleared by an EXIT trap,
  and treated as stale after two minutes in case of SIGKILL). The client
  spawns two processes at once for the probe; without the lock both would
  build into the same directory. With it, one builds, the other waits, and
  exactly one venv appears.

If the environment cannot be built at all - unwritable home, no network on
first run - the launcher logs why and falls back to the old `uv tool run`
path, so the worst case is the previous behaviour rather than a dead server.

## 0.3.8 - directory metadata

`privacy_policies: ["https://www.hava.io/privacy"]` added to the `.mcpb`
manifest. The extension talks to `api.hava.io`, and the directory policy
expects a server that calls an external service to name the policy that covers
it; packaging flagged its absence.

No behaviour change, but the version bump edits `src/hava_mcp/__init__.py`,
which the launcher's environment stamp covers - so the first launch after
upgrading rebuilds the virtualenv once (~3s) before returning to ~0.5s. That
is the stamp working as intended: it tracks source, not a version string, so
it can never run stale code.

Both artifacts now also carry stable filenames (`hava-mcp.mcpb`,
`cloudzone-hava.zip`) beside the versioned ones. The org's "Upload new
version" matches on name, so a stable name is what an in-place upgrade needs;
the version inside the manifest is what has to increase.
