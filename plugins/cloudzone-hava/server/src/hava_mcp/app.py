"""The MCP server instance and the scaffolding every tool shares.

Tool definitions live in :mod:`hava_mcp.tools`; they import ``mcp`` and the
helpers here. Keeping the server object in its own module lets the tool
modules import it without a cycle back through :mod:`hava_mcp.server`.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import os
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import __version__, auth
from .client import HavaClient, get_client
from .errors import HavaError

# httpx logs every request at INFO level; keep the stdio transport readable.
logging.getLogger("httpx").setLevel(logging.WARNING)

mcp = FastMCP("hava_mcp")
# FastMCP 1.x does not expose version in its constructor. Keep initialize's
# serverInfo.version tied to Hava, rather than the SDK's package version.
mcp._mcp_server.version = __version__

#: When set, tools that change anything in Hava are not registered at all.
#: Safer than refusing at call time: the model never sees a tool it must not use.
READ_ONLY = (os.environ.get("HAVA_MCP_READ_ONLY") or "").strip().lower() in (
    "1", "true", "yes", "on",
)


def handle_errors(fn: Callable[..., Awaitable[str]]) -> Callable[..., Awaitable[str]]:
    """Turn exceptions into actionable text instead of protocol-level failures."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return await fn(*args, **kwargs)
        except HavaError as exc:
            return f"Error: {exc}"
        except Exception as exc:  # noqa: BLE001 - surface anything as readable text
            return f"Error: unexpected {type(exc).__name__}: {exc}"

    return wrapper


def hava_tool(
    name: str,
    *,
    title: str,
    read_only: bool = True,
    destructive: bool = False,
    idempotent: bool = True,
    open_world: bool = True,
) -> Callable[[Callable[..., Awaitable[str]]], Callable[..., Awaitable[str]]]:
    """Register a Hava tool with consistent error handling and annotations.

    A tool with ``read_only=False`` is skipped entirely when the server runs in
    read-only mode; the undecorated function is still returned so tests and
    other modules can import it.
    """

    def decorator(fn: Callable[..., Awaitable[str]]) -> Callable[..., Awaitable[str]]:
        wrapped = handle_errors(fn)
        if not read_only and READ_ONLY:
            return wrapped
        return mcp.tool(
            name=name,
            annotations=ToolAnnotations(
                title=title,
                readOnlyHint=read_only,
                destructiveHint=destructive,
                idempotentHint=idempotent,
                openWorldHint=open_world,
            ),
        )(wrapped)

    return decorator


# --------------------------------------------------------------------------- #
# Shared request helpers
# --------------------------------------------------------------------------- #

def client() -> HavaClient:
    return get_client()


def as_results(payload: Any) -> list[Any]:
    """Hava list endpoints answer either a bare array or {total_size, results}."""
    if isinstance(payload, dict):
        return list(payload.get("results") or [])
    return list(payload or [])


def page_params(
    page: int | None = None,
    page_size: int | None = None,
    sort: str | None = None,
    sort_dir: str | None = None,
    page_token: str | None = None,
) -> dict[str, Any]:
    """Hava paginates with page/page_size/sort, or with an opaque token alone."""
    if page_token:
        return {"token": page_token}
    return {"page": page, "page_size": page_size, "sort": sort, "sort_dir": sort_dir}


def page_meta(payload: Mapping[str, Any] | Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {"total": None, "next_page_token": None}
    return {
        "total": payload.get("total_size"),
        "next_page_token": payload.get("next_page_token"),
    }


def require_confirm(confirm: bool, what: str) -> None:
    """Gate an irreversible call behind an explicit confirm flag."""
    if not confirm:
        raise HavaError(
            f"Refusing to {what} without confirmation. This cannot be undone. "
            f"Re-run with confirm=true once the user has explicitly agreed."
        )


def resolve_account_id(account_id: str | None) -> str:
    """Use the caller's account_id, else derive it from the API token."""
    explicit = (account_id or "").strip()
    if explicit:
        return explicit
    credential = client().credential()
    derived = auth.account_id_from_token(credential.token) if credential else None
    if not derived:
        raise HavaError(
            "No account_id given and it could not be read from the API token. "
            "Pass account_id explicitly - it is the UUID in your Hava account URL."
        )
    return derived


# --------------------------------------------------------------------------- #
# Shared Hava operations used by more than one tool module
# --------------------------------------------------------------------------- #

async def source_count(current: HavaClient) -> int:
    """Cheap authenticated call, used to verify that a token works."""
    return len(as_results(await current.get_json("/sources")))


async def fetch_environment(
    current: HavaClient, diagram_id: str, revision_id: str | None = None
) -> dict[str, Any]:
    payload = await current.get_json(
        f"/environments/{diagram_id}", params={"revision_id": revision_id}
    )
    if not isinstance(payload, dict):
        raise HavaError(f"Unexpected response shape for diagram {diagram_id}.")
    return payload


async def poll_job(
    current: HavaClient, job_id: str, wait_seconds: float
) -> tuple[str, str | None]:
    """Poll ``GET /jobs/{id}`` until it redirects (done), fails, or times out.

    Returns ``(state, result_url)``. A finished job answers ``303 See Other``
    with the artifact URL in the ``location`` header.
    """
    deadline = time.monotonic() + max(wait_seconds, 0)
    delay = 1.5
    state = "queued"
    while True:
        response = await current.request("GET", f"/jobs/{job_id}")
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("location") or ""
            if not location:
                raise HavaError(
                    f"Job {job_id} reported completion but returned no location header."
                )
            return "complete", current.absolute_url(location)

        payload: Any = {}
        if response.content:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
        state = (payload or {}).get("state") or "unknown"
        if state in ("failed", "cancelled"):
            raise HavaError(
                f"Hava job {job_id} {state}. Re-run the request; if it keeps failing the "
                f"view may be too large for that format, or still building."
            )
        if state == "complete":
            return "complete", None
        if time.monotonic() >= deadline:
            return state, None
        await asyncio.sleep(delay)
        delay = min(delay * 1.4, 5.0)


def job_from_response(response: Any) -> str | None:
    """Pull a job id out of a 202 response's location header or body."""
    from .client import job_id_from_location

    location = response.headers.get("location") or ""
    job_id = job_id_from_location(location)
    if not job_id and response.content:
        try:
            payload = response.json() or {}
        except ValueError:
            payload = {}
        job_id = payload.get("id") or payload.get("job_id")
    return job_id


def resolve_save_path(save_to: str, suggested_name: str) -> Path:
    path = Path(save_to).expanduser()
    if path.is_dir() or save_to.endswith(("/", "\\")):
        path = path / suggested_name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
