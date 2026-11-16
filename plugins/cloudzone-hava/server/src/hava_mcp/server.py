#!/usr/bin/env python3
"""MCP server for Hava (hava.io) cloud architecture diagrams.

Vocabulary note: what Hava's UI calls a *diagram* is an **environment** in the
API, and each environment holds several **views** (infrastructure, extended,
security, container, list). Exports act on a view, not on the environment, so
most workflows are: list/find a diagram -> pick a view -> export it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from . import auth
from .app import (
    as_results,
    client as get_client,
    fetch_environment as _fetch_environment,
    hava_tool,
    job_from_response,
    mcp,
    page_meta as _page_meta,
    page_params as _page_params,
    poll_job as _poll_job,
    resolve_save_path as _resolve_save_path,
    source_count as _source_count,
)
from .client import HavaClient
from .errors import HavaError
from .formatting import (
    ResponseFormat,
    as_output,
    render_diagram,
    render_diagram_list,
    render_export,
    render_job,
    render_revisions,
    render_search_results,
    render_sources,
    summarize_environment,
    summarize_resource,
    summarize_revision,
    summarize_source,
)
from .views import VIEW_CHOICES, pick_view, short_name

#: File extension per export format (Hava returns the artifact, not a filename).
_EXTENSIONS = {"pdf": ".pdf", "png": ".png", "vsdx": ".vsdx", "csv": ".csv", "json": ".json"}

#: Which views each export format accepts, verified against the live API.
#: Hava answers 422 for the rest, so checking up front gives a better message.
_FORMAT_VIEWS: dict[str, tuple[str, ...]] = {
    "png": ("infrastructure", "extended", "security", "container"),
    "pdf": ("infrastructure", "extended", "security", "container"),
    "vsdx": ("infrastructure",),
    "csv": VIEW_CHOICES,
    "json": VIEW_CHOICES,
}

ViewName = Literal["infrastructure", "extended", "security", "container", "list"]
ExportFormat = Literal["pdf", "png", "vsdx", "csv", "json"]


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #

@hava_tool(
    "hava_auth_status",
    title="Check Hava authentication",
    read_only=True,
    destructive=False,
    idempotent=True,
    open_world=True,
)
async def hava_auth_status(
    verify: Annotated[
        bool,
        Field(default=True, description="Call the Hava API to confirm the token still works."),
    ] = True,
) -> str:
    """Report which Hava API token is in use, where it came from, and whether it works.

    The token is configuration, not something this server stores: it comes from
    the plugin/extension's "Hava API token" field (delivered as
    HAVA_API_TOKEN), or from a key file for development checkouts.

    Args:
        verify: When true, performs a cheap authenticated call (GET /sources).

    Returns:
        str: The API endpoint, the credential origin (the environment variable
        name or key-file path), a masked token, and the live check result.
    """
    current = get_client()
    credential = current.credential()
    lines = [f"Hava API endpoint: {current.base_url}"]
    if credential is None:
        lines.append("Status: **no API token configured**")
        lines.append("")
        lines.append(auth.setup_instructions())
        return "\n".join(lines)

    lines.append(f"Credential origin: {credential.origin}")
    lines.append(f"Token: {auth.mask(credential.token)}")
    account = auth.account_id_from_token(credential.token)
    if account:
        lines.append(f"Account ID (from token): {account}")
    if verify:
        try:
            count = await _source_count(current)
        except HavaError as exc:
            lines.append(f"Live check: FAILED - {exc}")
        else:
            lines.append(f"Live check: OK ({count} cloud source(s) visible)")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Diagram discovery
# --------------------------------------------------------------------------- #

@hava_tool(
    "hava_list_diagrams",
    title="List Hava diagrams",
    read_only=True,
    destructive=False,
    idempotent=True,
    open_world=True,
)
async def hava_list_diagrams(
    page: Annotated[int | None, Field(default=None, description="1-based page number.", ge=1)] = None,
    page_size: Annotated[
        int,
        Field(default=25, description="Diagrams per page. Hava enforces a floor of 10.", ge=1, le=500),
    ] = 25,
    sort: Annotated[str | None, Field(default="name", description="Field to sort by, e.g. 'name'.")] = "name",
    sort_dir: Annotated[Literal["asc", "desc"], Field(default="asc", description="Sort direction.")] = "asc",
    page_token: Annotated[
        str | None,
        Field(default=None, description="next_page_token from a previous call; overrides the other paging args."),
    ] = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """List all Hava diagrams (environments) in the account, one page at a time.

    Each entry carries the `diagram_id` plus every view with its `view_id`, which
    is what `hava_export_diagram` needs. Diagrams in state `pending` are still
    building and have no usable views yet.

    Args:
        page: 1-based page number (ignored when page_token is given).
        page_size: Results per page, up to 500. Hava floors this at 10.
        sort: Field to sort by; defaults to 'name' for a stable, resumable order.
        sort_dir: 'asc' or 'desc'.
        page_token: Opaque token from a previous response's next_page_token.
        response_format: 'markdown' (default) or 'json' for the full records.

    Returns:
        str: Markdown listing, or JSON of the shape
        {"total": int, "count": int, "next_page_token": str|None,
         "diagrams": [{"diagram_id","name","state","diagram_type","query",
                       "sources":[...], "views":[{"view","view_id",...}]}]}

    Examples:
        - Use when: "what diagrams do we have in Hava?"
        - Don't use when: you are hunting for a specific resource - use
          hava_find_diagrams with a resource_query instead.
    """
    client = get_client()
    payload = await client.get_json(
        "/environments", params=_page_params(page, page_size, sort, sort_dir, page_token)
    )
    results = (payload or {}).get("results") or []
    diagrams = [summarize_environment(env) for env in results]
    meta = _page_meta(payload or {})
    data = {
        "total": meta["total"],
        "count": len(diagrams),
        "next_page_token": meta["next_page_token"],
        "diagrams": diagrams,
    }
    return as_output(data, render_diagram_list(diagrams, meta), response_format)


@hava_tool(
    "hava_find_diagrams",
    title="Find Hava diagrams",
    read_only=True,
    destructive=False,
    idempotent=True,
    open_world=True,
)
async def hava_find_diagrams(
    name_contains: Annotated[
        str | None,
        Field(default=None, description="Case-insensitive substring of the diagram name, e.g. 'prod'."),
    ] = None,
    resource_query: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Hava search syntax to match resources; returns the diagrams containing "
                "them. Examples: 'vpc:vpc-1234', 'type:ec2_instance AND region:us-east-1', "
                "'(vpc:vpc-1 OR vpc:vpc-2) AND CostCenter:DEV'."
            ),
        ),
    ] = None,
    limit: Annotated[int, Field(default=25, description="Maximum diagrams to return.", ge=1, le=200)] = 25,
    max_pages: Annotated[
        int,
        Field(default=20, description="Safety cap on pages scanned when filtering by name.", ge=1, le=100),
    ] = 20,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Find diagrams by name, or by the cloud resources they contain.

    Two independent modes, which can be combined:

    * `resource_query` uses Hava's server-side search (GET /search/environments)
      and returns each matching diagram with a deep link that highlights the
      matched resources.
    * `name_contains` pages through the account's diagrams and filters names
      locally, because the Hava API has no name filter.

    Args:
        name_contains: Substring to match against diagram names, case-insensitive.
        resource_query: Hava search syntax
            (https://docs.hava.io/discover/searching/search-syntax).
        limit: Maximum diagrams to return, 1-200.
        max_pages: Cap on pages fetched in name mode (100 diagrams per page).
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: Markdown listing, or JSON
        {"mode": "resource_query"|"name"|"both", "count": int,
         "truncated": bool, "diagrams": [...]}. Resource-query hits include a
        `url` deep link; name hits include the full view list with view IDs.

    Examples:
        - Use when: "which diagram shows vpc-0ab12?" -> resource_query="vpc:vpc-0ab12"
        - Use when: "find our production diagrams" -> name_contains="production"
        - Don't use when: you already have the diagram_id - use hava_get_diagram.
    """
    if not name_contains and not resource_query:
        raise HavaError(
            "Provide name_contains, resource_query, or both. To browse everything "
            "without a filter, use hava_list_diagrams."
        )

    client = get_client()
    needle = (name_contains or "").strip().lower()
    truncated = False
    meta: dict[str, Any] = {}

    if resource_query:
        try:
            payload = await client.get_json(
                "/search/environments", params={"q": resource_query}
            )
        except HavaError as exc:
            raise HavaError(
                f"{exc}\n\nHava's resource search needs field:value syntax such as "
                f"'vpc:vpc-1234' or 'type:ec2_instance' - bare words are rejected with "
                f"422, and some queries make the endpoint return 500. If it keeps "
                f"failing, filter by diagram name with name_contains instead."
            ) from exc
        results = (payload or {}).get("results") or []
        diagrams = [
            {
                "diagram_id": item.get("id"),
                "name": item.get("name"),
                "url": item.get("url"),
                "thumbnail_url": item.get("image"),
            }
            for item in results
        ]
        if needle:
            diagrams = [d for d in diagrams if needle in (d.get("name") or "").lower()]
        meta = _page_meta(payload or {})
        mode = "both" if needle else "resource_query"
    else:
        # The Hava API has no name filter, so page through and match locally.
        # Pagination is token-based and carries the sort order, so a stable sort
        # on the first request keeps the walk consistent.
        diagrams = []
        token: str | None = None
        scanned = 0
        for _ in range(max_pages):
            params: dict[str, Any] = (
                {"token": token}
                if token
                else {"sort": "name", "sort_dir": "asc", "page_size": 100}
            )
            payload = await client.get_json("/environments", params=params)
            results = as_results(payload)
            scanned += len(results)
            for env in results:
                if needle in (env.get("name") or "").lower():
                    diagrams.append(summarize_environment(env))
            token = (payload or {}).get("next_page_token")
            if not token or len(diagrams) >= limit:
                break
        meta = {
            "scanned": scanned,
            "more_pages": bool(token),
            "stopped_at_limit": len(diagrams) >= limit,
        }
        mode = "name"

    if len(diagrams) > limit:
        diagrams = diagrams[:limit]
        truncated = True

    data = {
        "mode": mode,
        "count": len(diagrams),
        "truncated": truncated,
        "diagrams": diagrams,
    }
    meta = {**meta, "truncated": truncated}
    markdown = (
        render_search_results(diagrams, meta)
        if resource_query
        else render_diagram_list(diagrams, meta)
    )
    return as_output(data, markdown, response_format)


@hava_tool(
    "hava_get_diagram",
    title="Get a Hava diagram",
    read_only=True,
    destructive=False,
    idempotent=True,
    open_world=True,
)
async def hava_get_diagram(
    diagram_id: Annotated[str, Field(description="The diagram (environment) UUID.", min_length=1)],
    revision_id: Annotated[
        str | None,
        Field(default=None, description="A past version to inspect; see hava_list_diagram_versions."),
    ] = None,
    include_resources: Annotated[
        bool,
        Field(default=False, description="Include the diagram's cloud resources (can be large)."),
    ] = False,
    resource_limit: Annotated[
        int, Field(default=50, description="Maximum resources to include.", ge=1, le=1000)
    ] = 50,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Get one diagram with its views, sources, and optionally its resources.

    This is how you obtain the `view_id` values needed for an export, and the
    `current_revision_id` for exporting a specific point in time.

    Args:
        diagram_id: The environment UUID.
        revision_id: Optional past version to inspect instead of the current one.
        include_resources: Include the resource list (omitted by default because
            large environments hold thousands of resources).
        resource_limit: Cap on resources returned when include_resources is true.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: Markdown detail, or JSON {"diagram": {...}, "resources": [...] |
        null, "resources_truncated": bool}.

    Examples:
        - Use when: you need a view_id before calling hava_export_diagram.
        - Use when: "what's in the prod diagram?" -> include_resources=true
        - Don't use when: you only need the name/ID list - hava_list_diagrams is cheaper.
    """
    client = get_client()
    env = await _fetch_environment(client, diagram_id, revision_id)
    diagram = summarize_environment(env)

    resources: list[dict[str, Any]] | None = None
    resources_truncated = False
    if include_resources:
        raw = ((env.get("facet") or {}).get("resources")) or []
        resources_truncated = len(raw) > resource_limit
        resources = [summarize_resource(r) for r in raw[:resource_limit]]

    data = {
        "diagram": diagram,
        "resources": resources,
        "resources_truncated": resources_truncated,
    }
    markdown = render_diagram(diagram, resources)
    if resources_truncated:
        markdown += (
            f"\n\n_Showing {resource_limit} of {diagram.get('resource_count')} resources; "
            f"raise resource_limit for more._"
        )
    return as_output(data, markdown, response_format)


@hava_tool(
    "hava_list_diagram_versions",
    title="List diagram versions",
    read_only=True,
    destructive=False,
    idempotent=True,
    open_world=True,
)
async def hava_list_diagram_versions(
    diagram_id: Annotated[str, Field(description="The diagram (environment) UUID.", min_length=1)],
    page: Annotated[int | None, Field(default=None, description="1-based page number.", ge=1)] = None,
    page_size: Annotated[int, Field(default=25, description="Versions per page.", ge=1, le=100)] = 25,
    sort_dir: Annotated[Literal["asc", "desc"] | None, Field(default=None, description="Sort direction.")] = None,
    page_token: Annotated[str | None, Field(default=None, description="next_page_token from a previous call.")] = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """List the version history of a diagram, newest first by default.

    Hava snapshots an environment whenever the underlying cloud config changes.
    Pass a `revision_id` from here to `hava_export_diagram` or `hava_get_diagram`
    to work with a past state rather than the current one.

    Args:
        diagram_id: The environment UUID.
        page: 1-based page number.
        page_size: Versions per page, 1-100.
        sort_dir: 'asc' or 'desc'.
        page_token: Opaque token from a previous response.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: Markdown table, or JSON {"total": int, "count": int,
        "next_page_token": str|None, "versions": [{"revision_id","from","to"}]}.
        The newest version reports `to` as "current".
    """
    client = get_client()
    payload = await client.get_json(
        f"/environments/{diagram_id}/revisions",
        params=_page_params(page, page_size, None, sort_dir, page_token),
    )
    results = (payload or {}).get("results") or []
    versions = [summarize_revision(r) for r in results]
    meta = _page_meta(payload or {})
    data = {
        "total": meta["total"],
        "count": len(versions),
        "next_page_token": meta["next_page_token"],
        "versions": versions,
    }
    return as_output(data, render_revisions(versions, meta), response_format)


@hava_tool(
    "hava_list_sources",
    title="List connected cloud sources",
    read_only=True,
    destructive=False,
    idempotent=True,
    open_world=True,
)
async def hava_list_sources(
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """List the cloud accounts (AWS/Azure/GCP/Kubernetes sources) connected to Hava.

    Useful for mapping a diagram's `sources` back to a real cloud account, and
    for confirming a source finished importing (`state: active`) before
    expecting its diagrams to exist.

    Args:
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: Markdown table, or JSON {"count": int, "sources":
        [{"source_id","name","type","provider_account_id","state","info"}]}.
    """
    client = get_client()
    payload = await client.get_json("/sources")
    sources = [summarize_source(s) for s in as_results(payload)]
    return as_output(
        {"count": len(sources), "sources": sources}, render_sources(sources), response_format
    )


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #

@hava_tool(
    "hava_export_diagram",
    title="Export a Hava diagram view",
    read_only=False,
    destructive=False,
    idempotent=False,
    open_world=True,
)
async def hava_export_diagram(
    export_format: Annotated[
        ExportFormat,
        Field(description="Export format: 'png' or 'pdf' (images), 'vsdx' (editable Visio), 'csv' or 'json' (data)."),
    ],
    diagram_id: Annotated[
        str | None,
        Field(default=None, description="The diagram (environment) UUID. Required unless view_id is given."),
    ] = None,
    view: Annotated[
        ViewName,
        Field(default="infrastructure", description=f"Which view to export: {', '.join(VIEW_CHOICES)}."),
    ] = "infrastructure",
    view_id: Annotated[
        str | None,
        Field(default=None, description="Export this view UUID directly, skipping lookup by diagram_id + view."),
    ] = None,
    revision_id: Annotated[
        str | None,
        Field(default=None, description="Export a past version; see hava_list_diagram_versions."),
    ] = None,
    save_to: Annotated[
        str | None,
        Field(default=None, description="Local file or directory to save the export to. Omit to just return the download URL."),
    ] = None,
    connections: Annotated[bool | None, Field(default=None, description="Draw connections between resources.")] = None,
    labels: Annotated[bool | None, Field(default=None, description="Draw resource name labels.")] = None,
    isometric: Annotated[bool | None, Field(default=None, description="Render the 3D isometric layout instead of flat topology.")] = None,
    timestamp: Annotated[bool | None, Field(default=None, description="Stamp the generation time on the diagram (PNG/PDF only).")] = None,
    hide_resource_groups: Annotated[bool | None, Field(default=None, description="Azure only: group by Virtual Network instead of Resource Group.")] = None,
    hide_empty_networks: Annotated[bool | None, Field(default=None, description="Hide VPCs/VNets that contain no visible resources.")] = None,
    wait_seconds: Annotated[
        int,
        Field(
            default=100,
            description=(
                "How long to poll the export job before returning its job ID. The "
                "default stays under the 120s tool timeout most MCP clients use, so "
                "a slow export hands back a job ID instead of timing out."
            ),
            ge=0,
            le=900,
        ),
    ] = 100,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Export one view of a Hava diagram to PNG, PDF, VSDX, CSV, or JSON.

    Exporting is asynchronous: Hava queues a job and this tool polls it until the
    artifact is ready, then returns a time-limited download URL. Pass `save_to`
    to also write the file locally. If the job outlives `wait_seconds` the job ID
    is returned so `hava_get_job` can pick it up later.

    Identify the view either by `diagram_id` + `view` (the view is looked up for
    you) or by `view_id` directly. Not every diagram has every view: security
    views exist for AWS and Azure, container views only where containerised
    resources were found.

    Args:
        export_format: 'pdf', 'png', 'vsdx', 'csv', or 'json'.
        diagram_id: Environment UUID; required unless view_id is supplied.
        view: Which view to export - infrastructure, extended, security,
            container, or list. Ignored when view_id is supplied.
        view_id: Export this view UUID directly.
        revision_id: Export a past version of the view.
        save_to: Local path (file or directory) to write the artifact to.
        connections, labels, isometric, timestamp, hide_resource_groups,
            hide_empty_networks: Hava rendering options; left unset, Hava's
            defaults apply.
        wait_seconds: Polling budget, 0-900 (default 100, chosen to stay inside
            the 120s tool timeout most MCP clients apply). 0 returns the job ID
            immediately. Big diagrams in vsdx/pdf can take several minutes:
            leave the default and collect the result with hava_get_job.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: Markdown summary, or JSON {"state": "complete"|"queued"|"active",
        "job_id": str, "view_id": str, "view": str, "export_format": str,
        "download_url": str|None, "saved_to": str|None, "bytes": int|None}.

    Examples:
        - Use when: "export the prod infrastructure diagram as PNG" ->
          diagram_id=..., view="infrastructure", export_format="png"
        - Use when: "give me the security diagram as a Visio file I can edit" ->
          view="security", export_format="vsdx"
        - Don't use when: you want the raw resource data in context - use
          hava_get_diagram with include_resources=true.

    Error Handling:
        Returns a message listing the diagram's available views if the requested
        view does not exist, and the job ID if the export is still running when
        wait_seconds elapses.
    """
    client = get_client()

    diagram_name: str | None = None
    view_label = view
    if view_id is None:
        if not diagram_id:
            raise HavaError("Provide diagram_id (with an optional view) or view_id.")
        env = await _fetch_environment(client, diagram_id, revision_id)
        diagram_name = env.get("name")
        chosen = pick_view(env.get("views") or [], view)
        view_id = chosen.get("id")
        view_label = short_name(chosen.get("type"))
        if not view_id:
            raise HavaError(f"The {view!r} view of this diagram has no ID to export.")
    else:
        view_label = view  # caller-supplied ID; trust their label

    allowed = _FORMAT_VIEWS[export_format]
    if view_label in VIEW_CHOICES and view_label not in allowed:
        usable = [f for f, views in _FORMAT_VIEWS.items() if view_label in views]
        raise HavaError(
            f"Hava cannot export the {view_label!r} view as {export_format}. "
            f"{export_format} supports these views: {', '.join(allowed)}. "
            f"The {view_label!r} view can be exported as: {', '.join(usable)}."
        )

    body = {
        "export_format": export_format,
        "connections": connections,
        "labels": labels,
        "isometric": isometric,
        "timestamp": timestamp,
        "hide_resource_groups": hide_resource_groups,
        "hide_empty_networks": hide_empty_networks,
        "revision_id": revision_id,
    }
    body = {k: v for k, v in body.items() if v is not None}

    response = await client.request("POST", f"/views/{view_id}/export", json=body)
    job_id = job_from_response(response)
    if not job_id:
        raise HavaError(
            "Hava accepted the export but returned no job reference "
            f"(HTTP {response.status_code}, "
            f"location={response.headers.get('location')!r})."
        )

    state, download_url = await _poll_job(client, job_id, wait_seconds)

    result: dict[str, Any] = {
        "state": state,
        "job_id": job_id,
        "diagram_id": diagram_id,
        "diagram_name": diagram_name,
        "view": view_label,
        "view_id": view_id,
        "export_format": export_format,
        "revision_id": revision_id,
        "download_url": download_url,
        "saved_to": None,
        "bytes": None,
    }

    if state != "complete":
        result["note"] = (
            f"Still {state} after {wait_seconds}s. Call "
            f"hava_get_job(job_id=\"{job_id}\") to collect the download link."
        )
    elif download_url is None:
        result["note"] = (
            f"The job reports complete but returned no artifact link. Call "
            f"hava_get_job(job_id=\"{job_id}\") to retrieve it."
        )
    elif save_to:
        content, _ = await client.download(download_url)
        suggested = f"{(diagram_name or 'hava')}-{view_label}{_EXTENSIONS[export_format]}"
        suggested = suggested.replace("/", "-").replace(" ", "_")
        path = _resolve_save_path(save_to, suggested)
        path.write_bytes(content)
        result["saved_to"] = str(path)
        result["bytes"] = len(content)

    return as_output(result, render_export(result), response_format)


@hava_tool(
    "hava_get_job",
    title="Check a Hava job",
    read_only=True,
    destructive=False,
    idempotent=True,
    open_world=True,
)
async def hava_get_job(
    job_id: Annotated[str, Field(description="The job UUID returned by an export or sync.", min_length=1)],
    wait_seconds: Annotated[
        int, Field(default=0, description="Seconds to keep polling before answering. 0 = check once.", ge=0, le=900)
    ] = 0,
    save_to: Annotated[
        str | None,
        Field(default=None, description="If the job is finished, save its artifact to this local file or directory."),
    ] = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Check an asynchronous Hava job and collect its result.

    Hava queues exports, environment builds, and source syncs as jobs. A finished
    job redirects to the artifact it produced; this tool follows that and reports
    the resulting URL.

    Args:
        job_id: The job UUID (returned by hava_export_diagram).
        wait_seconds: Keep polling for up to this long, 0-900. 0 checks once.
        save_to: Local file or directory to write the artifact to when finished.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: Markdown summary, or JSON {"job_id": str, "state": str,
        "result_url": str|None, "saved_to": str|None, "bytes": int|None}.

    Examples:
        - Use when: an export returned "still active" with a job ID.
        - Don't use when: you have not started a job - there is nothing to poll.
    """
    client = get_client()
    state, result_url = await _poll_job(client, job_id, wait_seconds)
    job: dict[str, Any] = {
        "job_id": job_id,
        "state": state,
        "result_url": result_url,
        "saved_to": None,
        "bytes": None,
    }
    if state == "complete" and result_url and save_to:
        content, _ = await client.download(result_url)
        suffix = Path(result_url.split("?", 1)[0]).suffix or ".bin"
        path = _resolve_save_path(save_to, f"hava-job-{job_id}{suffix}")
        path.write_bytes(content)
        job["saved_to"] = str(path)
        job["bytes"] = len(content)
    elif state != "complete":
        job["note"] = f"Job is {state}; poll again or raise wait_seconds."
    return as_output(job, render_job(job), response_format)


def main() -> None:
    """Entry point for the ``hava-mcp`` console script (stdio transport)."""
    mcp.run()


# Importing the tool packages registers the rest of the API surface against the
# shared ``mcp`` instance. Kept at the bottom so the modules can import the
# helpers defined above without a cycle.
from . import tools as _tools  # noqa: E402,F401


if __name__ == "__main__":
    main()
