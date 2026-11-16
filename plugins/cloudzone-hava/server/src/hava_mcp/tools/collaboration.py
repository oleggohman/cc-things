"""Notes and shares attached to a Hava diagram."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from ..app import (
    as_results,
    client,
    hava_tool,
    job_from_response,
    page_meta,
    page_params,
    poll_job,
    require_confirm,
)
from ..errors import HavaError
from ..formatting import (
    ResponseFormat,
    as_output,
    render_notes,
    render_shares,
    render_simple,
    summarize_note,
    summarize_share,
)

ShareType = Literal["full", "light", "png"]

_SHARE_TYPES = {
    "full": "Share::Full",
    "light": "Share::Light",
    "png": "Share::PNG",
}


# --------------------------------------------------------------------------- #
# Notes
# --------------------------------------------------------------------------- #

@hava_tool("hava_list_diagram_notes", title="List diagram notes")
async def hava_list_diagram_notes(
    diagram_id: Annotated[str, Field(description="The diagram (environment) UUID.", min_length=1)],
    page: Annotated[int | None, Field(default=None, description="1-based page number.", ge=1)] = None,
    page_size: Annotated[int, Field(default=25, description="Notes per page.", ge=1, le=100)] = 25,
    page_token: Annotated[str | None, Field(default=None, description="next_page_token from a previous call.")] = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """List the notes people have left on a diagram.

    Notes are Hava's in-diagram commentary - useful context about why an
    environment looks the way it does, and often where architectural decisions
    are recorded.

    Args:
        diagram_id: The environment UUID.
        page: 1-based page number.
        page_size: Notes per page, 1-100.
        page_token: Opaque token from a previous response.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: Markdown list, or JSON {"total","count","next_page_token","notes"}.
    """
    current = client()
    payload = await current.get_json(
        f"/environments/{diagram_id}/notes",
        params=page_params(page, page_size, None, None, page_token),
    )
    notes = [summarize_note(n) for n in as_results(payload)]
    meta = page_meta(payload)
    data = {"total": meta["total"], "count": len(notes),
            "next_page_token": meta["next_page_token"], "notes": notes}
    return as_output(data, render_notes(notes, meta), response_format)


@hava_tool(
    "hava_create_diagram_note",
    title="Add a note to a diagram",
    read_only=False,
    idempotent=False,
)
async def hava_create_diagram_note(
    diagram_id: Annotated[str, Field(description="The diagram (environment) UUID.", min_length=1)],
    note: Annotated[str, Field(description="The note text.", min_length=1)],
    tagged_user_ids: Annotated[
        list[str] | None,
        Field(default=None, description="User IDs to tag, which notifies them in Hava. Get IDs from hava_list_teams."),
    ] = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Add a note to a diagram, optionally tagging teammates.

    Tagging notifies those users in Hava, so only tag people the user actually
    named.

    Args:
        diagram_id: The environment UUID.
        note: The note text.
        tagged_user_ids: User IDs to notify.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: The created note with its `note_id`.
    """
    current = client()
    body: dict[str, object] = {"note": note}
    if tagged_user_ids:
        body["tagged_users"] = tagged_user_ids
    response = await current.request("POST", f"/environments/{diagram_id}/notes", json=body)
    created = response.json() if response.content else {}
    summary = summarize_note(created or {})
    return as_output(
        {"note": summary},
        render_simple("Note added", {
            "note_id": f"`{summary.get('note_id')}`",
            "diagram_id": f"`{diagram_id}`",
            "text": summary.get("note") or note,
            "tagged": ", ".join(tagged_user_ids) if tagged_user_ids else None,
        }),
        response_format,
    )


@hava_tool(
    "hava_delete_diagram_note",
    title="Delete a diagram note",
    read_only=False,
    destructive=True,
)
async def hava_delete_diagram_note(
    diagram_id: Annotated[str, Field(description="The diagram (environment) UUID.", min_length=1)],
    note_id: Annotated[str, Field(description="The note's UUID, from hava_list_diagram_notes.", min_length=1)],
    confirm: Annotated[bool, Field(default=False, description="Must be true. Deleting a note is permanent.")] = False,
) -> str:
    """Delete a note from a diagram. Permanent.

    The note may be someone else's commentary, so confirm with the user first.

    Args:
        diagram_id: The environment UUID.
        note_id: The note to delete.
        confirm: Must be true.

    Returns:
        str: Confirmation that the note was deleted.
    """
    require_confirm(confirm, f"delete note {note_id}")
    current = client()
    await current.request("DELETE", f"/environments/{diagram_id}/notes/{note_id}")
    return f"Deleted note `{note_id}` from diagram `{diagram_id}`."


# --------------------------------------------------------------------------- #
# Shares
# --------------------------------------------------------------------------- #

@hava_tool("hava_list_diagram_shares", title="List diagram shares")
async def hava_list_diagram_shares(
    diagram_id: Annotated[str, Field(description="The diagram (environment) UUID.", min_length=1)],
    page: Annotated[int | None, Field(default=None, description="1-based page number.", ge=1)] = None,
    page_size: Annotated[int, Field(default=25, description="Shares per page.", ge=1, le=100)] = 25,
    page_token: Annotated[str | None, Field(default=None, description="next_page_token from a previous call.")] = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """List the embeddable shares that exist for a diagram.

    A share is a public, sign-in-free link to the diagram, so this doubles as an
    exposure audit: anyone holding a share URL can see the architecture.

    Args:
        diagram_id: The environment UUID.
        page: 1-based page number.
        page_size: Shares per page, 1-100.
        page_token: Opaque token from a previous response.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: Markdown list, or JSON {"total","count","shares"}. Share tokens are
        reported as present/absent rather than echoed.
    """
    current = client()
    payload = await current.get_json(
        f"/environments/{diagram_id}/shares",
        params=page_params(page, page_size, None, None, page_token),
    )
    shares = [summarize_share(s) for s in as_results(payload)]
    meta = page_meta(payload)
    data = {"total": meta["total"], "count": len(shares), "shares": shares}
    return as_output(data, render_shares(shares, meta), response_format)


@hava_tool("hava_get_diagram_share", title="Get a diagram share")
async def hava_get_diagram_share(
    diagram_id: Annotated[str, Field(description="The diagram (environment) UUID.", min_length=1)],
    share_id: Annotated[str, Field(description="The share's UUID.", min_length=1)],
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Get the details and configuration of one diagram share.

    Args:
        diagram_id: The environment UUID.
        share_id: The share UUID from hava_list_diagram_shares.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: The share's type, URL and config.
    """
    current = client()
    payload = await current.get_json(f"/environments/{diagram_id}/shares/{share_id}")
    share = summarize_share(payload or {})
    return as_output({"share": share}, render_shares([share], {}), response_format)


@hava_tool(
    "hava_create_diagram_share",
    title="Create a diagram share",
    read_only=False,
    idempotent=False,
)
async def hava_create_diagram_share(
    diagram_id: Annotated[str, Field(description="The diagram (environment) UUID.", min_length=1)],
    share_type: Annotated[
        ShareType,
        Field(default="full", description="'full' (interactive), 'light' (read-only interactive) or 'png' (static image)."),
    ] = "full",
    config: Annotated[
        dict | None,
        Field(default=None, description="Share options, mainly for PNG shares (e.g. which view and render flags)."),
    ] = None,
    wait_seconds: Annotated[
        int, Field(default=100, description="Seconds to wait when Hava queues share generation as a job.", ge=0, le=900)
    ] = 100,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Create a publicly accessible, embeddable link to a diagram.

    **This publishes the diagram.** Anyone with the resulting URL can view your
    architecture without signing in to Hava, which for a production environment
    means exposing network layout, security groups and resource names. Only
    create a share when the user has clearly asked to share or embed a diagram,
    and tell them the link is public.

    If the requested share type does not exist yet Hava queues a job to build
    it; this tool waits and then returns the finished share.

    Args:
        diagram_id: The environment UUID.
        share_type: 'full', 'light' or 'png'.
        config: Optional share configuration (PNG shares use it for view and
            render options).
        wait_seconds: Polling budget when a job is returned.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: The share, including its public URL.

    Examples:
        - Use when: "give me an embeddable link to the prod diagram"
        - Don't use when: the user wants a file - use hava_export_diagram, which
          publishes nothing.
    """
    current = client()
    body: dict[str, object] = {"type": _SHARE_TYPES[share_type]}
    if config:
        body["config"] = config
    response = await current.request("POST", f"/environments/{diagram_id}/shares", json=body)

    payload = {}
    if response.content:
        try:
            payload = response.json() or {}
        except ValueError:
            payload = {}

    # A share that must be generated comes back as a job instead.
    if response.status_code == 202 or (not payload.get("id") and not payload.get("url")):
        job_id = job_from_response(response)
        if job_id:
            state, result_url = await poll_job(current, job_id, wait_seconds)
            if state != "complete":
                return as_output(
                    {"state": state, "job_id": job_id},
                    f"Share generation still {state}. Check with "
                    f"hava_get_job(job_id=\"{job_id}\"), then list shares again.",
                    response_format,
                )
            if result_url and current.is_api_host(result_url):
                payload = await current.get_json(result_url.replace(current.base_url, "")) or {}

    share = summarize_share(payload)
    note = "**This link is public** - anyone with it can view the diagram without signing in."
    return as_output({"share": share}, render_shares([share], {}) + "\n\n" + note, response_format)


@hava_tool(
    "hava_update_diagram_share",
    title="Update a diagram share",
    read_only=False,
    idempotent=False,
)
async def hava_update_diagram_share(
    diagram_id: Annotated[str, Field(description="The diagram (environment) UUID.", min_length=1)],
    share_id: Annotated[str, Field(description="The share's UUID.", min_length=1)],
    config: Annotated[dict, Field(description="The replacement share configuration. Used to change PNG share render options.")],
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Change the configuration of an existing share (PNG render options).

    Args:
        diagram_id: The environment UUID.
        share_id: The share to update.
        config: The replacement configuration object.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: The updated share.
    """
    current = client()
    response = await current.request(
        "PUT", f"/environments/{diagram_id}/shares/{share_id}", json={"config": config}
    )
    updated = {}
    if response.content:
        try:
            updated = response.json() or {}
        except ValueError:
            updated = {}
    share = summarize_share(updated)
    return as_output({"share": share}, render_shares([share], {}), response_format)
