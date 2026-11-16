"""Querying and exporting raw cloud resources.

``GET /resources`` answers with a bare JSON array of *every* match - one live
query for a whole region returned 13,979 resources - so these tools always
summarise and cap what reaches the conversation.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Annotated

from pydantic import Field

from ..app import client, hava_tool, poll_job, resolve_save_path
from ..errors import HavaError
from ..formatting import ResponseFormat, as_output, render_resources, summarize_resource

_QUERY_HELP = (
    "Fields verified against the live API: `source:<source_id>`, "
    "`region:<region>`, `vpc:<vpc-id>`, `cluster:\"<arn>\"`, and tag filters "
    "such as `CostCenter:DEV`, combined with AND/OR. `type:` does NOT work "
    "despite appearing in Hava's docs - filter by type with `type_contains`."
)


@hava_tool("hava_list_resources", title="Query cloud resources")
async def hava_list_resources(
    query: Annotated[
        str,
        Field(description=f"Hava search query selecting resources. {_QUERY_HELP}", min_length=1),
    ],
    type_contains: Annotated[
        str | None,
        Field(default=None, description="Client-side filter on resource type, e.g. 'EC2::Instance' or 'RDS'."),
    ] = None,
    limit: Annotated[int, Field(default=25, description="Maximum resources to list.", ge=1, le=500)] = 25,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Find cloud resources across all connected accounts using a Hava query.

    Returns the total match count and a breakdown by resource type first, then
    the first `limit` resources. The breakdown is usually the useful part: a
    broad query can match many thousands of resources, and this covers both
    resources drawn on diagrams and the non-visualised ones Hava keeps off them.

    Args:
        query: The Hava search query.
        type_contains: Narrow results to types containing this text,
            case-insensitive (the API's own `type:` filter does not work).
        limit: Maximum resources to include, 1-500.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: Markdown with a per-type breakdown and a resource sample, or JSON
        {"query","total","returned","by_type":{...},"resources":[...]}.

    Examples:
        - Use when: "what's running in eu-west-1?" -> query="region:eu-west-1"
        - Use when: "list the RDS instances in this account" ->
          query="source:<id>", type_contains="RDS"
        - Don't use when: you want a picture - use hava_export_diagram.
    """
    current = client()
    payload = await current.get_json("/resources", params={"q": query})
    raw = payload if isinstance(payload, list) else (payload or {}).get("results") or []

    if type_contains:
        needle = type_contains.lower()
        raw = [r for r in raw if needle in (r.get("type") or "").lower()]

    counts = Counter((r.get("type") or "unknown").split("::")[-1] for r in raw)
    by_type = counts.most_common(15)
    resources = [summarize_resource(r) for r in raw[:limit]]

    data = {
        "query": query,
        "type_contains": type_contains,
        "total": len(raw),
        "returned": len(resources),
        "by_type": dict(counts),
        "resources": resources,
    }
    return as_output(data, render_resources(resources, len(raw), by_type, query), response_format)


@hava_tool(
    "hava_export_resources",
    title="Export all resources to JSON",
    read_only=False,
    idempotent=False,
)
async def hava_export_resources(
    source_ids: Annotated[
        str | None,
        Field(default=None, description="Comma-separated source IDs to export. Omit for every connected source."),
    ] = None,
    save_to: Annotated[
        str | None,
        Field(default=None, description="Local file or directory to write the JSON to. Strongly recommended - the payload is large."),
    ] = None,
    wait_seconds: Annotated[
        int, Field(default=100, description="Seconds to wait if Hava queues this as a job.", ge=0, le=900)
    ] = 100,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Export the full resource inventory for one or more cloud sources as JSON.

    This is a bulk dump intended for a file, not for reading in conversation -
    a single account can hold tens of thousands of resources. Pass `save_to`;
    without it this tool reports the size and the download link rather than
    inlining the payload.

    Args:
        source_ids: Comma-separated source IDs, or omit for all sources.
        save_to: Local path to write the JSON to.
        wait_seconds: Polling budget if Hava returns a job instead of the data.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: Where the file was saved and how big it was, or a download URL.

    Examples:
        - Use when: "dump our whole AWS inventory to a file for diffing"
        - Don't use when: you want to look at a handful of resources - use
          hava_list_resources.
    """
    current = client()
    response = await current.request(
        "GET", "/resources/export", params={"source_ids": source_ids}
    )

    # Hava may answer with the data directly, or queue a job and redirect.
    download_url: str | None = None
    content: bytes | None = None
    if response.status_code in (301, 302, 303, 307, 308):
        from ..app import job_from_response

        job_id = job_from_response(response)
        if not job_id:
            download_url = current.absolute_url(response.headers.get("location") or "")
        else:
            state, download_url = await poll_job(current, job_id, wait_seconds)
            if state != "complete":
                return as_output(
                    {"state": state, "job_id": job_id},
                    f"Resource export still {state}. Collect it with "
                    f"hava_get_job(job_id=\"{job_id}\", save_to=...).",
                    response_format,
                )
    else:
        content = response.content

    if download_url and content is None:
        content, _ = await current.download(download_url)

    if content is None:
        raise HavaError("Hava returned no resource export payload.")

    result: dict[str, object] = {
        "bytes": len(content),
        "download_url": download_url,
        "saved_to": None,
        "source_ids": source_ids,
    }
    if save_to:
        path = resolve_save_path(save_to, "hava-resources.json")
        path.write_bytes(content)
        result["saved_to"] = str(path)

    try:
        parsed = json.loads(content)
        result["resource_count"] = len(parsed) if isinstance(parsed, list) else None
    except ValueError:
        result["resource_count"] = None

    lines = [
        "# Resource export complete",
        f"- sources: {source_ids or 'all connected sources'}",
        f"- size: {len(content):,} bytes",
    ]
    if result.get("resource_count") is not None:
        lines.append(f"- resources: {result['resource_count']:,}")
    if result["saved_to"]:
        lines.append(f"- saved to: `{result['saved_to']}`")
    else:
        lines.append(
            "- not saved. Pass `save_to` to write it to a file; it is too large to "
            "read inline."
        )
    return as_output(result, "\n".join(lines), response_format)
