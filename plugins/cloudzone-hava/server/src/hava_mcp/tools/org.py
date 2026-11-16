"""Account administration: teams, projects, members and API tokens.

Every route here is ``/accounts/{account_id}/...`` and Hava has no endpoint that
reports which account a token belongs to. The token is a JWT whose ``sub`` claim
is the account ID (confirmed against the live API), so ``account_id`` defaults
to that and callers rarely need to supply it.

``hava_create_api_token`` returns the new token's secret once, so it appears in
the conversation transcript. Treat the transcript as sensitive.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from ..app import (
    as_results,
    client,
    hava_tool,
    page_meta,
    page_params,
    require_confirm,
    resolve_account_id,
)
from ..errors import HavaError
from ..formatting import (
    ResponseFormat,
    as_output,
    render_projects,
    render_simple,
    render_teams,
    render_tokens,
    summarize_project,
    summarize_team,
    summarize_token,
)

AccountId = Annotated[
    str | None,
    Field(default=None, description="Hava account UUID. Defaults to the account the API token belongs to."),
]


# --------------------------------------------------------------------------- #
# Teams
# --------------------------------------------------------------------------- #

@hava_tool("hava_list_teams", title="List Hava teams")
async def hava_list_teams(
    account_id: AccountId = None,
    page: Annotated[int | None, Field(default=None, description="1-based page number.", ge=1)] = None,
    page_size: Annotated[int, Field(default=25, description="Teams per page.", ge=1, le=100)] = 25,
    page_token: Annotated[str | None, Field(default=None, description="next_page_token from a previous call.")] = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """List the teams in a Hava account, with their roles and members.

    This is also the way to get the `user_id` values that
    `hava_add_project_member`, `hava_remove_team_member` and note tagging need.

    Args:
        account_id: Account UUID; defaults to the token's own account.
        page: 1-based page number.
        page_size: Teams per page, 1-100.
        page_token: Opaque token from a previous response.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: Markdown with each team's roles and members, or JSON
        {"total","count","teams":[{"team_id","name","roles","members":[...]}]}.
    """
    account = resolve_account_id(account_id)
    payload = await client().get_json(
        f"/accounts/{account}/teams",
        params=page_params(page, page_size, None, None, page_token),
    )
    teams = [summarize_team(t) for t in as_results(payload)]
    meta = page_meta(payload)
    data = {"account_id": account, "total": meta["total"], "count": len(teams), "teams": teams}
    return as_output(data, render_teams(teams, meta), response_format)


@hava_tool("hava_get_team", title="Get a Hava team")
async def hava_get_team(
    team_id: Annotated[str, Field(description="The team's UUID.", min_length=1)],
    account_id: AccountId = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Get one team with its roles and full member list.

    Args:
        team_id: The team UUID.
        account_id: Account UUID; defaults to the token's own account.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: The team, its roles, and its members with their user IDs.
    """
    account = resolve_account_id(account_id)
    payload = await client().get_json(f"/accounts/{account}/teams/{team_id}")
    team = summarize_team(payload or {})
    return as_output({"team": team}, render_teams([team], {}), response_format)


@hava_tool("hava_create_team", title="Create a Hava team", read_only=False, idempotent=False)
async def hava_create_team(
    name: Annotated[str, Field(description="Name for the new team.", min_length=1)],
    roles: Annotated[
        list[str] | None,
        Field(default=None, description="Roles granted to the team, e.g. ['Admin']. Omit for a team with no elevated roles."),
    ] = None,
    account_id: AccountId = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Create a team in the Hava account.

    Roles grant account-wide permissions, so passing `['Admin']` makes every
    member an account admin. Only set roles the user explicitly asked for.

    Args:
        name: The team name.
        roles: Roles to grant the team.
        account_id: Account UUID; defaults to the token's own account.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: The created team, including its `team_id`.
    """
    account = resolve_account_id(account_id)
    body: dict[str, object] = {"name": name}
    if roles:
        body["roles"] = roles
    response = await client().request("POST", f"/accounts/{account}/teams", json=body)
    created = response.json() if response.content else {}
    team = summarize_team(created or {})
    return as_output({"team": team}, render_teams([team], {}), response_format)


@hava_tool("hava_update_team", title="Update a Hava team", read_only=False)
async def hava_update_team(
    team_id: Annotated[str, Field(description="The team's UUID.", min_length=1)],
    name: Annotated[str, Field(description="The team name. Hava requires it on every update, so pass the current name when only changing roles.", min_length=1)],
    roles: Annotated[list[str] | None, Field(default=None, description="Replacement roles list, e.g. ['Admin'].")] = None,
    account_id: AccountId = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Rename a team or change the roles it grants.

    `roles` replaces the existing list rather than adding to it, and roles are
    account-wide permissions - read the team first with `hava_get_team` so you
    do not silently drop or grant access.

    Args:
        team_id: The team UUID.
        name: The team name (required by Hava even when unchanged).
        roles: Replacement roles list.
        account_id: Account UUID; defaults to the token's own account.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: The updated team.
    """
    account = resolve_account_id(account_id)
    body: dict[str, object] = {"name": name}
    if roles is not None:
        body["roles"] = roles
    response = await client().request("PUT", f"/accounts/{account}/teams/{team_id}", json=body)
    updated = response.json() if response.content else {}
    team = summarize_team(updated or {})
    return as_output({"team": team}, render_teams([team], {}), response_format)


@hava_tool("hava_delete_team", title="Delete a Hava team", read_only=False, destructive=True)
async def hava_delete_team(
    team_id: Annotated[str, Field(description="The team's UUID.", min_length=1)],
    confirm: Annotated[
        bool,
        Field(default=False, description="Must be true. Per Hava's docs this also removes the team's members from the account."),
    ] = False,
    account_id: AccountId = None,
) -> str:
    """Delete a team, which also removes its members from the Hava account.

    Hava documents this as removing all members from your account, so it can
    revoke people's access entirely - not just their team membership. List the
    team first and tell the user who will be affected.

    Args:
        team_id: The team UUID.
        confirm: Must be true.
        account_id: Account UUID; defaults to the token's own account.

    Returns:
        str: Confirmation naming the team and the members affected.
    """
    require_confirm(confirm, f"delete team {team_id} and remove its members from the account")
    account = resolve_account_id(account_id)
    current = client()
    name, members = None, []
    try:
        existing = await current.get_json(f"/accounts/{account}/teams/{team_id}")
        name = (existing or {}).get("name")
        members = [m.get("email") or m.get("username") for m in (existing or {}).get("members") or []]
    except HavaError:
        pass
    await current.request("DELETE", f"/accounts/{account}/teams/{team_id}")
    label = f"{name!r} (`{team_id}`)" if name else f"`{team_id}`"
    who = f" Members removed from the account: {', '.join(filter(None, members))}." if members else ""
    return f"Deleted team {label}.{who}"


@hava_tool("hava_add_team_member", title="Add a member to a team", read_only=False)
async def hava_add_team_member(
    team_id: Annotated[str, Field(description="The team's UUID.", min_length=1)],
    email: Annotated[str, Field(description="Email address of an existing Hava user.", min_length=3)],
    account_id: AccountId = None,
) -> str:
    """Add an existing Hava user to a team by email.

    The person must already have a Hava account. To bring in someone new, use
    `hava_invite_team_member`, which sends an invitation.

    Args:
        team_id: The team UUID.
        email: The user's email address.
        account_id: Account UUID; defaults to the token's own account.

    Returns:
        str: Confirmation, or an error if no such user exists.
    """
    account = resolve_account_id(account_id)
    await client().request(
        "POST", f"/accounts/{account}/teams/{team_id}/members", params={"email": email}
    )
    return (
        f"Added {email} to team `{team_id}`. They inherit the team's roles, so "
        f"check them with hava_get_team if that matters."
    )


@hava_tool("hava_invite_team_member", title="Invite a user to a team", read_only=False, idempotent=False)
async def hava_invite_team_member(
    team_id: Annotated[str, Field(description="The team's UUID.", min_length=1)],
    email: Annotated[str, Field(description="Email address to invite.", min_length=3)],
    account_id: AccountId = None,
) -> str:
    """Invite someone to Hava by email and add them to a team.

    **This sends an email to a real person** and grants them access to your
    cloud architecture documentation once they accept. Only call it when the
    user has named the person to invite.

    Args:
        team_id: The team UUID.
        email: The email address to invite.
        account_id: Account UUID; defaults to the token's own account.

    Returns:
        str: Confirmation that the invitation was sent.
    """
    account = resolve_account_id(account_id)
    await client().request(
        "POST", f"/accounts/{account}/teams/{team_id}/members/invite", params={"email": email}
    )
    return (
        f"Invited {email} to Hava and to team `{team_id}`. They will receive an "
        f"email and gain access to this account's diagrams once they accept."
    )


@hava_tool("hava_remove_team_member", title="Remove a member from a team", read_only=False, destructive=True)
async def hava_remove_team_member(
    team_id: Annotated[str, Field(description="The team's UUID.", min_length=1)],
    user_id: Annotated[str, Field(description="The user's UUID, from hava_get_team.", min_length=1)],
    confirm: Annotated[
        bool,
        Field(default=False, description="Must be true. This revokes a person's access."),
    ] = False,
    account_id: AccountId = None,
) -> str:
    """Remove a user from a team, revoking the access that team grants.

    Identified by `user_id`, not email - get it from `hava_get_team`. This takes
    away a real person's access, so confirm who is being removed first.

    Args:
        team_id: The team UUID.
        user_id: The user UUID to remove.
        confirm: Must be true.
        account_id: Account UUID; defaults to the token's own account.

    Returns:
        str: Confirmation that the member was removed.
    """
    require_confirm(confirm, f"remove user {user_id} from team {team_id}")
    account = resolve_account_id(account_id)
    await client().request(
        "DELETE", f"/accounts/{account}/teams/{team_id}/members/{user_id}"
    )
    return f"Removed user `{user_id}` from team `{team_id}`."


# --------------------------------------------------------------------------- #
# Projects
# --------------------------------------------------------------------------- #

@hava_tool("hava_list_projects", title="List Hava projects")
async def hava_list_projects(
    account_id: AccountId = None,
    page: Annotated[int | None, Field(default=None, description="1-based page number.", ge=1)] = None,
    page_size: Annotated[int, Field(default=25, description="Projects per page.", ge=1, le=100)] = 25,
    page_token: Annotated[str | None, Field(default=None, description="next_page_token from a previous call.")] = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """List the projects in a Hava account.

    Projects group environments so access can be granted per project rather
    than account-wide.

    Args:
        account_id: Account UUID; defaults to the token's own account.
        page: 1-based page number.
        page_size: Projects per page, 1-100.
        page_token: Opaque token from a previous response.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: Markdown list, or JSON {"total","count","projects"}.
    """
    account = resolve_account_id(account_id)
    payload = await client().get_json(
        f"/accounts/{account}/projects",
        params=page_params(page, page_size, None, None, page_token),
    )
    projects = [summarize_project(p) for p in as_results(payload)]
    meta = page_meta(payload)
    data = {"account_id": account, "total": meta["total"], "count": len(projects), "projects": projects}
    return as_output(data, render_projects(projects, meta), response_format)


@hava_tool("hava_get_project", title="Get a Hava project")
async def hava_get_project(
    project_id: Annotated[str, Field(description="The project's UUID.", min_length=1)],
    account_id: AccountId = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Get one project with its description and members.

    Args:
        project_id: The project UUID.
        account_id: Account UUID; defaults to the token's own account.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: The project and its members.
    """
    account = resolve_account_id(account_id)
    payload = await client().get_json(f"/accounts/{account}/projects/{project_id}")
    project = summarize_project(payload or {})
    return as_output({"project": project}, render_projects([project], {}), response_format)


@hava_tool("hava_create_project", title="Create a Hava project", read_only=False, idempotent=False)
async def hava_create_project(
    name: Annotated[str, Field(description="Name for the new project.", min_length=1)],
    description: Annotated[str | None, Field(default=None, description="What the project is for.")] = None,
    account_id: AccountId = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Create a project for grouping environments and scoping access.

    Args:
        name: The project name.
        description: Optional description.
        account_id: Account UUID; defaults to the token's own account.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: The created project, including its `project_id`.
    """
    account = resolve_account_id(account_id)
    body: dict[str, object] = {"name": name}
    if description:
        body["description"] = description
    response = await client().request("POST", f"/accounts/{account}/projects", json=body)
    created = response.json() if response.content else {}
    project = summarize_project(created or {})
    return as_output({"project": project}, render_projects([project], {}), response_format)


@hava_tool("hava_update_project", title="Update a Hava project", read_only=False)
async def hava_update_project(
    project_id: Annotated[str, Field(description="The project's UUID.", min_length=1)],
    name: Annotated[str | None, Field(default=None, description="New name.")] = None,
    description: Annotated[str | None, Field(default=None, description="New description.")] = None,
    account_id: AccountId = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Rename a project or change its description.

    Args:
        project_id: The project UUID.
        name: New name, if changing.
        description: New description, if changing.
        account_id: Account UUID; defaults to the token's own account.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: The updated project.
    """
    if name is None and description is None:
        raise HavaError("Pass name, description, or both - there is nothing to update.")
    account = resolve_account_id(account_id)
    body = {k: v for k, v in (("name", name), ("description", description)) if v is not None}
    response = await client().request(
        "PUT", f"/accounts/{account}/projects/{project_id}", json=body
    )
    updated = response.json() if response.content else {}
    project = summarize_project(updated or {})
    return as_output({"project": project}, render_projects([project], {}), response_format)


@hava_tool("hava_delete_project", title="Delete a Hava project", read_only=False, destructive=True)
async def hava_delete_project(
    project_id: Annotated[str, Field(description="The project's UUID.", min_length=1)],
    confirm: Annotated[bool, Field(default=False, description="Must be true.")] = False,
    account_id: AccountId = None,
) -> str:
    """Delete a project, removing its grouping and per-project access.

    Args:
        project_id: The project UUID.
        confirm: Must be true.
        account_id: Account UUID; defaults to the token's own account.

    Returns:
        str: Confirmation that the project was deleted.
    """
    require_confirm(confirm, f"delete project {project_id}")
    account = resolve_account_id(account_id)
    await client().request("DELETE", f"/accounts/{account}/projects/{project_id}")
    return f"Deleted project `{project_id}`."


@hava_tool("hava_add_project_member", title="Add a member to a project", read_only=False)
async def hava_add_project_member(
    project_id: Annotated[str, Field(description="The project's UUID.", min_length=1)],
    user_id: Annotated[str, Field(description="The user's UUID, from hava_list_teams.", min_length=1)],
    account_id: AccountId = None,
) -> str:
    """Give a user access to a project.

    Takes `user_id`, not email - unlike the team equivalent. Get IDs from
    `hava_list_teams` or `hava_get_team`.

    Args:
        project_id: The project UUID.
        user_id: The user UUID to add.
        account_id: Account UUID; defaults to the token's own account.

    Returns:
        str: Confirmation that the member was added.
    """
    account = resolve_account_id(account_id)
    await client().request(
        "POST", f"/accounts/{account}/projects/{project_id}/members",
        params={"user_id": user_id},
    )
    return f"Added user `{user_id}` to project `{project_id}`."


@hava_tool("hava_remove_project_member", title="Remove a member from a project", read_only=False, destructive=True)
async def hava_remove_project_member(
    project_id: Annotated[str, Field(description="The project's UUID.", min_length=1)],
    user_id: Annotated[str, Field(description="The user's UUID.", min_length=1)],
    confirm: Annotated[
        bool,
        Field(default=False, description="Must be true. This revokes a person's access."),
    ] = False,
    account_id: AccountId = None,
) -> str:
    """Revoke a user's access to a project.

    This takes away a real person's access, so confirm who is being removed
    first.

    Args:
        project_id: The project UUID.
        user_id: The user UUID to remove.
        confirm: Must be true.
        account_id: Account UUID; defaults to the token's own account.

    Returns:
        str: Confirmation that the member was removed.
    """
    require_confirm(confirm, f"remove user {user_id} from project {project_id}")
    account = resolve_account_id(account_id)
    await client().request(
        "DELETE", f"/accounts/{account}/projects/{project_id}/members/{user_id}"
    )
    return f"Removed user `{user_id}` from project `{project_id}`."


# --------------------------------------------------------------------------- #
# API tokens
# --------------------------------------------------------------------------- #

@hava_tool("hava_list_api_tokens", title="List Hava API tokens")
async def hava_list_api_tokens(
    account_id: AccountId = None,
    page: Annotated[int | None, Field(default=None, description="1-based page number.", ge=1)] = None,
    page_size: Annotated[int, Field(default=25, description="Tokens per page.", ge=1, le=100)] = 25,
    page_token: Annotated[str | None, Field(default=None, description="next_page_token from a previous call.")] = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """List the account's API tokens with their names and last-used times.

    Useful for credential hygiene: finding tokens that have never been used or
    have gone stale. The API never returns token values, only this metadata.

    Args:
        account_id: Account UUID; defaults to the token's own account.
        page: 1-based page number.
        page_size: Tokens per page, 1-100.
        page_token: Opaque token from a previous response.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: Markdown table, or JSON {"total","count","tokens"}.
    """
    account = resolve_account_id(account_id)
    payload = await client().get_json(
        f"/accounts/{account}/tokens",
        params=page_params(page, page_size, None, None, page_token),
    )
    tokens = [summarize_token(t) for t in as_results(payload)]
    meta = page_meta(payload)
    data = {"account_id": account, "total": meta["total"], "count": len(tokens), "tokens": tokens}
    return as_output(data, render_tokens(tokens, meta), response_format)


@hava_tool("hava_create_api_token", title="Create a Hava API token", read_only=False, idempotent=False)
async def hava_create_api_token(
    name: Annotated[str, Field(description="A name describing what the token is for, e.g. 'CI pipeline'.", min_length=1)],
    account_id: AccountId = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Generate a new API token. The secret is shown once and cannot be retrieved later.

    SECURITY: the token grants access to the account's whole cloud inventory and
    will appear in this conversation's transcript. Tell the user that, tell them
    to store it immediately, and do not repeat it elsewhere or write it to files
    unless asked. Use `hava_delete_api_token` to revoke it if it leaks.

    Args:
        name: Token name.
        account_id: Account UUID; defaults to the token's own account.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: The token ID, name and secret value.
    """
    account = resolve_account_id(account_id)
    response = await client().request("POST", f"/accounts/{account}/tokens", json={"name": name})
    payload = response.json() if response.content else {}
    data = {"token_id": payload.get("id"), "name": payload.get("name") or name, "token": payload.get("token")}
    return as_output(data, render_simple("API token created", {
        "token_id": f"`{data['token_id']}`",
        "name": data["name"],
        "token": f"`{data['token']}`",
    }, note="This is the only time the token is shown. Store it now; it cannot be retrieved again."), response_format)


@hava_tool("hava_delete_api_token", title="Revoke a Hava API token", read_only=False, destructive=True)
async def hava_delete_api_token(
    token_id: Annotated[str, Field(description="The token's UUID, from hava_list_api_tokens.", min_length=1)],
    confirm: Annotated[
        bool,
        Field(default=False, description="Must be true. Anything using this token stops working immediately."),
    ] = False,
    account_id: AccountId = None,
) -> str:
    """Revoke an API token. Anything using it breaks immediately.

    Revoking is instant and irreversible, and may be the token this very server
    is authenticated with - in which case every later call fails. Check
    `hava_auth_status` and `hava_list_api_tokens` first, and confirm with the
    user which token is going.

    Args:
        token_id: The token UUID to revoke.
        confirm: Must be true.
        account_id: Account UUID; defaults to the token's own account.

    Returns:
        str: Confirmation that the token was revoked.
    """
    require_confirm(confirm, f"revoke API token {token_id}")
    account = resolve_account_id(account_id)
    await client().request("DELETE", f"/accounts/{account}/tokens/{token_id}")
    return (
        f"Revoked API token `{token_id}`. Any integration using it now fails "
        f"authentication. This cannot be undone."
    )
