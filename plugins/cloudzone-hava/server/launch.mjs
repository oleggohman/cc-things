#!/usr/bin/env node
/**
 * Launcher for the Hava MCP server.
 *
 * Why this exists instead of `"command": "uvx"`:
 *   - Claude ships Node but no Python and no uv.
 *   - The system python3 on macOS is 3.9, below this server's 3.10 floor.
 *   - GUI apps on macOS do not inherit a shell PATH, so Homebrew's uv is
 *     invisible to them and a bare `uvx` fails with ENOENT.
 *
 * So: Node (always present) locates uv, passes the configured settings
 * through, and hands its own stdio to the Python server so the MCP stream
 * flows straight through.
 *
 * Why there is a prepared virtualenv instead of a plain `uv tool run`:
 *   The client gives a newly spawned server roughly two seconds to answer its
 *   capability probe. `uv tool run --from <dir>` has to resolve requirements,
 *   build the local package and materialise an environment before Python even
 *   starts; warm that is ~0.2s, but cold - or with any disk/network jitter -
 *   it is 2-4s. Add ~0.45s for importing the MCP SDK and the launch lands on
 *   either side of the deadline at random, which is why the server appeared to
 *   start "sometimes". So the environment is built once into a stable
 *   location, and every later launch skips uv entirely and execs that
 *   interpreter directly: a fixed ~0.5s with no resolver and no network.
 *
 * Configuration comes from the host (the plugin's userConfig or the .mcpb
 * extension's user_config) as environment variables. This script only cleans
 * them up; it never reads or writes credentials anywhere.
 */

import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
} from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const log = (msg) => process.stderr.write(`[hava-mcp] ${msg}\n`);

log(
  `node ${process.version} ${process.platform}/${process.arch}` +
    (process.versions.electron ? ` electron ${process.versions.electron}` : "") +
    ` execPath=${process.execPath}`
);

/** Strip blanks and placeholders the host left unexpanded. */
function clean(value) {
  if (value === undefined || value === null) return undefined;
  const text = String(value).trim();
  if (!text) return undefined;
  if (/^\$\{.*\}$/.test(text)) return undefined;
  return text;
}

/** uv on PATH first, then the usual macOS install locations. */
function findUv() {
  const override = clean(process.env.HAVA_MCP_UV);
  if (override && existsSync(override)) return override;

  for (const dir of (process.env.PATH || "").split(path.delimiter)) {
    if (!dir) continue;
    const candidate = path.join(dir, "uv");
    try {
      if (statSync(candidate).isFile()) return candidate;
    } catch {}
  }
  for (const candidate of [
    "/opt/homebrew/bin/uv",
    "/usr/local/bin/uv",
    path.join(homedir(), ".local/bin/uv"),
    path.join(homedir(), ".cargo/bin/uv"),
    "/opt/local/bin/uv",
  ]) {
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

const uv = findUv();
if (!uv) {
  log("FATAL: could not find `uv`, which is required to run this Python server.");
  log("Install it, then restart Claude:");
  log("  brew install uv");
  log("  (or) curl -LsSf https://astral.sh/uv/install.sh | sh");
  log("Already installed somewhere unusual? Set HAVA_MCP_UV to its full path.");
  process.exit(1);
}

// The token is configuration. Pass it through if present, otherwise remove the
// variable entirely so the server reports "not configured" rather than
// authenticating with an empty or literal "${user_config.api_token}" string.
const env = { ...process.env };

const token = clean(process.env.HAVA_API_TOKEN);
if (token) env.HAVA_API_TOKEN = token;
else delete env.HAVA_API_TOKEN;

const endpoint = clean(process.env.HAVA_ENDPOINT);
if (endpoint) env.HAVA_ENDPOINT = endpoint;
else delete env.HAVA_ENDPOINT;

// A boolean userConfig arrives as the string "true" or "false".
const readOnly = (clean(process.env.HAVA_MCP_READ_ONLY) || "").toLowerCase();
if (["1", "true", "yes", "on"].includes(readOnly)) env.HAVA_MCP_READ_ONLY = "1";
else delete env.HAVA_MCP_READ_ONLY;

log(`uv: ${uv}`);
log(`token: ${token ? "configured" : "NOT CONFIGURED - set the Hava API token"}`);
log(`endpoint: ${endpoint || "https://api.hava.io (default)"}`);
log(`read-only: ${env.HAVA_MCP_READ_ONLY ? "yes" : "no"}`);

// --------------------------------------------------------------------------
// The prepared environment
// --------------------------------------------------------------------------

/** Per-user state, outside the extension directory, which may be read-only. */
function stateDir() {
  const override = clean(process.env.HAVA_MCP_HOME);
  if (override) return override;
  if (process.platform === "darwin") {
    return path.join(homedir(), "Library", "Application Support", "hava-mcp");
  }
  const base = clean(process.env.XDG_CACHE_HOME) || path.join(homedir(), ".cache");
  return path.join(base, "hava-mcp");
}

/**
 * Identity of the code we are about to run: the locked dependencies plus
 * every source file. A new extension version - or an edited working copy
 * during development - produces a different stamp and so a rebuilt
 * environment, without depending on anyone remembering to bump a version
 * string. Twenty-odd small files, so a couple of milliseconds.
 */
function sourceStamp(root) {
  const hash = createHash("sha256").update("hava-mcp-env-v2\n");
  const walk = (dir) => {
    const entries = readdirSync(dir, { withFileTypes: true });
    entries.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    for (const entry of entries) {
      if (entry.name.startsWith(".") || entry.name === "__pycache__") continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.isFile()) {
        hash.update(full.slice(root.length));
        hash.update("\0");
        hash.update(readFileSync(full));
      }
    }
  };
  hash.update(readFileSync(path.join(root, "pyproject.toml")));
  hash.update(readFileSync(path.join(root, "uv.lock")));
  walk(path.join(root, "src"));
  return hash.digest("hex").slice(0, 16);
}

let stamp = null;
try {
  stamp = sourceStamp(HERE);
} catch (err) {
  log(`FATAL: cannot fingerprint the bundled source and lockfile: ${err?.message ?? err}`);
  process.exit(1);
}

const ENV_DIR = path.join(stateDir(), `venv-${stamp}`);
const ENV_PYTHON = path.join(ENV_DIR, "bin", "python");
const ENV_READY = path.join(ENV_DIR, ".ready");
const ENV_FAILED = `${ENV_DIR}.failed`;
const LOCK_DIR = path.join(stateDir(), `.building-${stamp}`);
// A build that is SIGKILLed skips its cleanup trap and leaves the lock behind.
// Two minutes is longer than any real build and short enough that the next
// launch clears it rather than queueing behind a directory nobody owns.
const LOCK_STALE_MS = 2 * 60 * 1000;

const envReady = () => existsSync(ENV_READY) && existsSync(ENV_PYTHON);

/**
 * Build the environment in a detached shell.
 *
 * Detached on purpose: when the client's probe deadline passes it kills this
 * launcher, and a build that died with it would restart from nothing on the
 * next launch and never finish. The shell outlives us, so the build completes
 * and the relaunch a second later is already on the fast path.
 *
 * The `.ready` marker is written last, so an interrupted build simply leaves a
 * directory that does not count as ready and gets replaced next time.
 */
function startBuild() {
  try {
    mkdirSync(stateDir(), { recursive: true });
  } catch (err) {
    log(`cannot create ${stateDir()}: ${err?.message ?? err}`);
    return false;
  }

  // mkdir is atomic, so it doubles as the lock against a second launcher
  // building the same directory underneath this one.
  try {
    const age = Date.now() - statSync(LOCK_DIR).mtimeMs;
    if (age > LOCK_STALE_MS) {
      log(`clearing a stale build lock (${Math.round(age / 1000)}s old)`);
      rmSync(LOCK_DIR, { recursive: true, force: true });
    }
  } catch {}
  try {
    mkdirSync(LOCK_DIR);
    rmSync(ENV_FAILED, { force: true });
  } catch {
    log("another launcher is already building the environment; waiting for it");
    return true;
  }

  const sh = [
    "set -e",
    'trap \'rc=$?; if [ "$rc" -ne 0 ]; then : > "$FAILED"; fi; rmdir "$LOCK" 2>/dev/null || true\' EXIT',
    'rm -rf "$ENVDIR"',
    '"$UV" sync --project "$SRC" --locked --no-dev --no-editable --python ">=3.10"',
    '"$ENVDIR/bin/python" -I -c "import hava_mcp.server"',
    ': > "$ENVDIR/.ready"',
  ].join("\n");

  // The build installs packages; it has no business holding the API token.
  const buildEnv = {
    ...env, UV: uv, ENVDIR: ENV_DIR, SRC: HERE, LOCK: LOCK_DIR,
    FAILED: ENV_FAILED, UV_PROJECT_ENVIRONMENT: ENV_DIR,
  };
  delete buildEnv.HAVA_API_TOKEN;

  const builder = spawn("/bin/sh", ["-c", sh], {
    detached: true,
    stdio: ["ignore", "ignore", "inherit"],
    env: buildEnv,
  });
  builder.on("error", (err) => log(`build failed to start: ${err?.message ?? err}`));
  builder.unref();
  log(`preparing the Python environment in ${ENV_DIR} (first launch only)`);
  return true;
}

/** Give a build in progress a chance to finish, stopping on build failure. */
function waitForEnv(deadlineMs) {
  const until = Date.now() + deadlineMs;
  const sleep = new Int32Array(new SharedArrayBuffer(4));
  while (Date.now() < until) {
    if (envReady()) return true;
    if (existsSync(ENV_FAILED)) return false;
    Atomics.wait(sleep, 0, 0, 200);
  }
  return envReady();
}

/**
 * Pick how to start Python.
 *
 * Always use the locked environment. An unlocked fallback could silently
 * reinstall a different SDK and reintroduce a protocol compatibility bug.
 */
function resolveCommand() {
  if (envReady()) return { cmd: ENV_PYTHON, args: ["-I", "-m", "hava_mcp"] };

  if (startBuild() && waitForEnv(120_000) && envReady()) {
    return { cmd: ENV_PYTHON, args: ["-I", "-m", "hava_mcp"] };
  }

  log("FATAL: locked environment is not ready; check the build error above and restart Claude to retry.");
  process.exit(1);
}

const { cmd, args } = resolveCommand();
log(`exec: ${cmd} ${args.join(" ")}`);

// stdio is piped, not inherited. Claude Desktop runs .mcpb extensions inside
// an Electron UtilityProcess, where this script's fd 0/1 are NOT the MCP
// stream - the stream is a pipe exposed only as process.stdin/process.stdout.
// With `stdio: "inherit"` the Python server therefore inherits an unrelated,
// already-closed fd 0, reads EOF immediately and exits ~1s after start, with
// no error of its own. Bridging the streams explicitly works both there and
// under a plain Node process (Claude Code, the CLI).
const child = spawn(cmd, args, { stdio: ["pipe", "pipe", "pipe"], env });

const ignoreClosed = (stream) => {
  stream.on("error", (err) => {
    if (err && (err.code === "EPIPE" || err.code === "ERR_STREAM_DESTROYED")) return;
    log(`stream error: ${err?.message ?? err}`);
  });
};
for (const s of [process.stdin, process.stdout, process.stderr, child.stdin, child.stdout, child.stderr]) {
  if (s) ignoreClosed(s);
}

process.stdin.pipe(child.stdin);
child.stdout.pipe(process.stdout);
child.stderr.pipe(process.stderr);
process.stdin.on("end", () => { try { child.stdin.end(); } catch {} });

child.on("error", (err) => {
  log(`FATAL: failed to start the server: ${err.message}${err.code ? ` (${err.code})` : ""}`);
  process.exit(1);
});
child.on("exit", (code, signal) => {
  if (signal) log(`server terminated by signal ${signal}`);
  else if (code) log(`server exited with code ${code}`);
  // Stop holding the event loop open, but do not process.exit(): that would
  // discard anything the server already wrote and we have not flushed yet.
  process.exitCode = code ?? 0;
  try { process.stdin.unpipe(child.stdin); } catch {}
  try { process.stdin.pause(); } catch {}
});
for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => {
    try { child.kill(sig); } catch {}
  });
}
