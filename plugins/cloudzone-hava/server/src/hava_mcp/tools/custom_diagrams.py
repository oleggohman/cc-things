"""Creating, updating and deleting custom (search-built) Hava diagrams.

Imported diagrams mirror a cloud account and cannot be edited through the API.
A *custom* diagram is defined by a Hava search query, so these tools only make
sense for `diagram_type: "search"` environments.
"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Literal

from pydantic import Field

from ..app import client, hava_tool, poll_job, require_confirm
from ..errors import HavaError
from ..formatting import ResponseFormat, as_output, render_diagram, summarize_environment

_QUERY_HELP = (
    "Fields verified against the live API: `source:<source_id>`, "
    "`region:<region>`, `vpc:<vpc-id>`, `cluster:\"<arn>\"`, and tag filters "
    "such as `CostCenter:DEV`, combined with AND/OR and parentheses. "
    "`type:` does not work despite appearing in Hava's docs."
)


@hava_tool(
    "hava_create_diagram",
    title="Create a custom Hava diagram",
    read_only=False,
    destructive=False,
    idempotent=False,
)
async def hava_create_diagram(
    query: Annotated[
        str,
        Field(description=f"Hava search query defining what the diagram contains. {_QUERY_HELP}", min_length=1),
    ],
    name: Annotated[str | None, Field(default=None, description="Name for the new diagram.")] = None,
    wait_seconds: Annotated[
        int,
        Field(default=60, description="Seconds to wait for the initial build before returning.", ge=0, le=600),
    ] = 60,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Create a new custom diagram from a Hava search query.

    The diagram is built asynchronously; it reports `state: "pending"` and has
    no usable views until the build finishes. This tool waits briefly and then
    re-reads it, so the returned views are usually ready to export.

    Args:
        query: The Hava search query that selects the resources to draw.
        name: Optional display name.
        wait_seconds: How long to wait for the build, 0-600.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: The created diagram, including its `diagram_id` and view IDs once
        the build completes.

    Examples:
        - Use when: "make a diagram of just vpc-123 and vpc-456" ->
          query="vpc:vpc-123 OR vpc:vpc-456"
        - Don't use when: the user wants a diagram of a whole cloud account -
          Hava already imports those; use hava_find_diagrams.
    """
    current = client()
    body = {"query": query}
    if name:
        body["name"] = name
    payload = await current.request("POST", "/environments", json=body)
    created = payload.json() if payload.content else {}
    diagram_id = (created or {}).get("id")
    if not diagram_id:
        raise HavaError("Hava accepted the diagram but returned no diagram ID.")

    diagram = summarize_environment(created)
    # The live API reports 'importing' as well as the documented 'pending',
    # and views only appear once the state reaches 'active'. Anything else
    # means the build is still in flight.
    if diagram.get("state") != "active" and wait_seconds:
        waited = 0.0
        while waited < wait_seconds:
            await asyncio.sleep(min(3.0, wait_seconds - waited))
            waited += 3.0
            refreshed = await current.get_json(f"/environments/{diagram_id}")
            if isinstance(refreshed, dict):
                diagram = summarize_environment(refreshed)
                if refreshed.get("state") == "active":
                    break

    note = ""
    if diagram.get("state") != "active":
        note = (
            f"\n\n_Still building (state: {diagram.get('state')}) after "
            f"{wait_seconds}s, so it has no views yet and cannot be exported or "
            f"annotated. Re-read it with "
            f"hava_get_diagram(diagram_id=\"{diagram_id}\")._"
        )
    return as_output({"diagram": diagram}, render_diagram(diagram, None) + note, response_format)


@hava_tool(
    "hava_update_diagram",
    title="Update a custom Hava diagram",
    read_only=False,
    destructive=False,
    idempotent=False,
)
async def hava_update_diagram(
    diagram_id: Annotated[str, Field(description="The custom diagram's UUID.", min_length=1)],
    query: Annotated[
        str,
        Field(description=f"The new search query. Required by Hava even when only renaming. {_QUERY_HELP}", min_length=1),
    ],
    name: Annotated[str | None, Field(default=None, description="New name for the diagram.")] = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Change the query or name of a custom diagram, triggering a rebuild.

    Only works on diagrams with `diagram_type: "search"`. Imported diagrams
    mirror a cloud account and Hava rejects edits to them.

    Hava requires `query` on every update, so pass the existing query unchanged
    if you only meant to change something else - read it first with
    hava_get_diagram.

    **Renaming does not work.** Hava accepts `name` and returns 200, but the
    name is never applied (verified against the live API). This tool sends it
    anyway in case your Hava version behaves differently, then re-reads the
    diagram and tells you plainly if the rename was ignored. Rename in the Hava
    UI instead.

    Args:
        diagram_id: The custom diagram's UUID.
        query: The new (or unchanged) search query.
        name: Optional new name. Hava is known to ignore this.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: The updated diagram, plus a warning if a requested rename did not
        take effect. The rebuild is asynchronous, so views may be absent for a
        moment afterwards.
    """
    current = client()
    body: dict[str, object] = {"query": query}
    if name:
        body["name"] = name
    response = await current.request("PUT", f"/environments/{diagram_id}", json=body)
    updated = response.json() if response.content else {}

    # The PUT response echoes pre-update state, so re-read for the truth.
    if name:
        try:
            updated = await current.get_json(f"/environments/{diagram_id}") or updated
        except HavaError:
            pass

    diagram = summarize_environment(updated or {})
    note = ""
    if name and diagram.get("name") != name:
        note = (
            f"\n\n_Hava ignored the rename: the diagram is still "
            f"{diagram.get('name')!r}, not {name!r}. Its `PUT /environments` "
            f"endpoint accepts `name` but does not apply it - rename it in the "
            f"Hava UI. The query change above did take effect._"
        )
    return as_output(
        {"diagram": diagram, "rename_applied": (diagram.get("name") == name) if name else None},
        render_diagram(diagram, None) + note,
        response_format,
    )


@hava_tool(
    "hava_delete_diagram",
    title="Delete a custom Hava diagram",
    read_only=False,
    destructive=True,
    idempotent=True,
)
async def hava_delete_diagram(
    diagram_id: Annotated[str, Field(description="The custom diagram's UUID.", min_length=1)],
    confirm: Annotated[
        bool,
        Field(default=False, description="Must be true. Deletion is permanent and takes the version history with it."),
    ] = False,
) -> str:
    """Permanently delete a custom diagram and its entire version history.

    This cannot be undone. Only custom (search-built) diagrams can be deleted;
    imported ones belong to a cloud source. Always confirm with the user before
    calling this, and name the diagram you are about to remove.

    Args:
        diagram_id: The custom diagram's UUID.
        confirm: Must be true, as an explicit guard against accidental deletion.

    Returns:
        str: Confirmation that the diagram was deleted.
    """
    require_confirm(confirm, f"delete diagram {diagram_id}")
    current = client()
    # Name it in the confirmation so the user can see what actually went.
    name = None
    try:
        existing = await current.get_json(f"/environments/{diagram_id}")
        name = (existing or {}).get("name")
    except HavaError:
        pass
    await current.request("DELETE", f"/environments/{diagram_id}")
    label = f"{name!r} (`{diagram_id}`)" if name else f"`{diagram_id}`"
    return f"Deleted diagram {label} and its version history. This cannot be undone."
