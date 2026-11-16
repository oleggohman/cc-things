"""Managing connected cloud sources.

``hava_create_source`` only creates AWS cross-account-role sources, which carry
no secret. ``hava_update_source_credentials`` can still take long-lived cloud
secrets (AWS keys, Azure client secrets, GCP service-account JSON) as tool
arguments, so those pass through the conversation. Secrets are never echoed
back in a tool result.
"""

from __future__ import annotations

import base64
import json
from typing import Annotated, Any, Literal

from pydantic import Field

from ..app import (
    client,
    hava_tool,
    job_from_response,
    poll_job,
    require_confirm,
)
from ..errors import HavaError
from ..formatting import (
    ResponseFormat,
    as_output,
    render_simple,
    render_source_detail,
    summarize_source_detail,
)


SourceType = Literal[
    "AWS::Keys", "AWS::CrossAccountRole", "Azure::Credentials", "GCP::ServiceAccountCredentials"
]

# Credential fields each source type needs, in the order they are reported.
_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "AWS::Keys": ("access_key", "secret_key"),
    "AWS::CrossAccountRole": ("role_arn", "external_id"),
    "Azure::Credentials": ("subscription_id", "tenant_id", "client_id", "secret_key"),
    "GCP::ServiceAccountCredentials": ("service_account_json",),
}


def _credential_body(source_type: str, fields: dict[str, Any], *, require_all: bool) -> dict[str, Any]:
    """Build the credential part of a source request, validating by type."""
    required = _REQUIRED_FIELDS[source_type]
    missing = [f for f in required if not fields.get(f)]
    if require_all and missing:
        raise HavaError(f"{source_type} sources need: {', '.join(required)}. Missing: {', '.join(missing)}.")
    body: dict[str, Any] = {}
    for key in required:
        value = fields.get(key)
        if not value:
            continue
        if key == "service_account_json":
            raw = value.strip()
            try:
                json.loads(raw)
            except ValueError as exc:
                raise HavaError("service_account_json must be the service-account key file's JSON text.") from exc
            body["encoded_file"] = base64.b64encode(raw.encode()).decode()
        else:
            body[key] = value
    return body


def _source_result(response: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if response.content:
        try:
            payload = response.json() or {}
        except ValueError:
            payload = {}
    return summarize_source_detail(payload or fallback)


@hava_tool("hava_get_source", title="Get a cloud source")
async def hava_get_source(
    source_id: Annotated[str, Field(description="The source's UUID, from hava_list_sources.", min_length=1)],
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Get one cloud source, including when it last synced.

    Use this to check whether a source's data is current before trusting its
    diagrams, and to see the role or credential identifier Hava connects with.

    Args:
        source_id: The source UUID.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: The source's type, cloud account, state, and last/queued sync times.
    """
    current = client()
    payload = await current.get_json(f"/sources/{source_id}")
    source = summarize_source_detail(payload or {})
    return as_output({"source": source}, render_source_detail(source), response_format)


@hava_tool(
    "hava_sync_source",
    title="Sync a cloud source",
    read_only=False,
    idempotent=False,
)
async def hava_sync_source(
    source_id: Annotated[str, Field(description="The source's UUID.", min_length=1)],
    metadata: Annotated[
        dict | None,
        Field(default=None, description="Optional metadata attached to the job and to the resources/diagrams it creates, e.g. {\"build_no\": 10}."),
    ] = None,
    wait_seconds: Annotated[
        int,
        Field(default=0, description="Seconds to wait for the import. 0 returns the job ID immediately, which is usually right - a full import can take many minutes.", ge=0, le=900),
    ] = 0,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Re-import a cloud account so its diagrams reflect current infrastructure.

    This calls out to the cloud provider and rebuilds every diagram for the
    source, which can take many minutes on a large account and creates a new
    version in each diagram's history. It does not change any cloud resources.

    Defaults to returning the job ID rather than waiting, because imports
    usually outlast any sensible tool timeout. Poll with `hava_get_job`, or
    check `last_sync` with `hava_get_source`.

    Args:
        source_id: The source UUID.
        metadata: Arbitrary metadata to attach - handy from CI to record a build
            number against the diagrams it produced.
        wait_seconds: Polling budget; 0 (default) returns immediately.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: The job ID and state.

    Examples:
        - Use when: "refresh the diagrams, we just deployed"
        - Don't use when: the diagram is merely slow to read - syncing is
          expensive and adds version history.
    """
    current = client()
    response = await current.request(
        "POST", f"/sources/{source_id}/sync", json=metadata or None
    )
    job_id = job_from_response(response)
    state = "queued"
    if job_id and wait_seconds:
        state, _ = await poll_job(current, job_id, wait_seconds)

    result = {"source_id": source_id, "job_id": job_id, "state": state}
    note = (
        f"Import queued. Check progress with hava_get_job(job_id=\"{job_id}\") "
        f"or hava_get_source(source_id=\"{source_id}\")."
        if job_id else
        "Hava accepted the sync but returned no job reference; check "
        "hava_get_source for the sync timestamps."
    )
    return as_output(result, render_simple(f"Source sync {state}", {
        "source_id": f"`{source_id}`",
        "job_id": f"`{job_id}`" if job_id else None,
        "metadata": metadata or None,
    }, note=note), response_format)


@hava_tool(
    "hava_rename_source",
    title="Rename a cloud source",
    read_only=False,
    idempotent=True,
)
async def hava_rename_source(
    source_id: Annotated[str, Field(description="The source's UUID.", min_length=1)],
    name: Annotated[str, Field(description="The new display name for the source.", min_length=1)],
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Rename a connected cloud source.

    Sends only the name, never credentials. To rotate credentials use
    `hava_update_source_credentials`.

    Args:
        source_id: The source UUID.
        name: The new display name.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: The updated source.
    """
    current = client()
    response = await current.request("PUT", f"/sources/{source_id}", json={"name": name})
    updated = {}
    if response.content:
        try:
            updated = response.json() or {}
        except ValueError:
            updated = {}
    source = summarize_source_detail(updated or {"id": source_id, "display_name": name})
    return as_output({"source": source}, render_source_detail(source), response_format)


@hava_tool(
    "hava_create_source",
    title="Connect an AWS account via cross-account role",
    read_only=False,
    idempotent=False,
)
async def hava_create_source(
    name: Annotated[str, Field(description="Display name for the source.", min_length=1)],
    role_arn: Annotated[str, Field(description="ARN of the IAM role Hava assumes, e.g. arn:aws:iam::123456789012:role/Hava.", min_length=1)],
    external_id: Annotated[str, Field(description="External ID for the role trust policy (MD5 of your Hava account ID, shown in Hava's 'Add Environment' prompt).", min_length=1)],
    project_id: Annotated[str | None, Field(default=None, description="Project UUID to add the source to. Defaults to the Default project.")] = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Connect an AWS account to Hava using a cross-account IAM role.

    Only `AWS::CrossAccountRole` sources can be created here. The role and
    external ID are identifiers, not secrets, so no access keys or secret keys
    ever pass through the conversation. Azure, GCP and AWS access-key sources
    must be connected in the Hava UI.

    Creating a source starts an import; follow it with `hava_get_source`.

    Args:
        name: Display name.
        role_arn: ARN of the role Hava assumes.
        external_id: External ID configured in the role's trust policy.
        project_id: Optional project UUID.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: The new source.
    """
    body: dict[str, Any] = {
        "name": name, "type": "AWS::CrossAccountRole",
        "role_arn": role_arn, "external_id": external_id,
    }
    if project_id:
        body["project_id"] = project_id
    response = await client().request("POST", "/sources", json=body)
    source = _source_result(response, {"display_name": name, "type": "AWS::CrossAccountRole"})
    return as_output({"source": source}, render_source_detail(source), response_format)


@hava_tool(
    "hava_update_source_credentials",
    title="Rotate a cloud source's credentials",
    read_only=False,
    idempotent=True,
)
async def hava_update_source_credentials(
    source_id: Annotated[str, Field(description="The source's UUID.", min_length=1)],
    type: Annotated[SourceType, Field(description="The source's type (see hava_get_source). Decides which credential fields apply.")],
    name: Annotated[str | None, Field(default=None, description="Optional new display name.")] = None,
    role_arn: Annotated[str | None, Field(default=None, description="AWS::CrossAccountRole: new role ARN.")] = None,
    external_id: Annotated[str | None, Field(default=None, description="AWS::CrossAccountRole: new external ID.")] = None,
    access_key: Annotated[str | None, Field(default=None, description="AWS::Keys: new access key ID.")] = None,
    secret_key: Annotated[str | None, Field(default=None, description="AWS::Keys / Azure::Credentials: new secret. A SECRET.")] = None,
    subscription_id: Annotated[str | None, Field(default=None, description="Azure::Credentials: subscription ID.")] = None,
    tenant_id: Annotated[str | None, Field(default=None, description="Azure::Credentials: tenant ID.")] = None,
    client_id: Annotated[str | None, Field(default=None, description="Azure::Credentials: client ID.")] = None,
    service_account_json: Annotated[str | None, Field(default=None, description="GCP::ServiceAccountCredentials: new key file JSON text. A SECRET.")] = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Replace a source's cloud credentials (and optionally its name).

    Only the fields you pass are changed. The same SECURITY caveat as
    `hava_create_source` applies: secrets passed here enter the conversation
    transcript. For a rename only, use `hava_rename_source`.

    Args:
        source_id: The source UUID.
        type: The source's type, so the right fields are accepted.
        name: Optional new display name.
        role_arn, external_id, access_key, secret_key, subscription_id,
            tenant_id, client_id, service_account_json: New credential values.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: The updated source (never including credentials).
    """
    fields = {
        "role_arn": role_arn, "external_id": external_id, "access_key": access_key,
        "secret_key": secret_key, "subscription_id": subscription_id, "tenant_id": tenant_id,
        "client_id": client_id, "service_account_json": service_account_json,
    }
    body = _credential_body(type, fields, require_all=False)
    if name:
        body["name"] = name
    if not body:
        raise HavaError("Nothing to update: pass a name or at least one credential field.")
    response = await client().request("PUT", f"/sources/{source_id}", json=body)
    source = _source_result(response, {"id": source_id, "display_name": name, "type": type})
    return as_output({"source": source}, render_source_detail(source), response_format)


@hava_tool(
    "hava_delete_source",
    title="Delete a cloud source",
    read_only=False,
    destructive=True,
    idempotent=True,
)
async def hava_delete_source(
    source_id: Annotated[str, Field(description="The source's UUID.", min_length=1)],
    confirm: Annotated[
        bool,
        Field(default=False, description="Must be true. This also deletes every resource and diagram from this source."),
    ] = False,
) -> str:
    """Disconnect a cloud source, deleting all its resources and diagrams.

    This is the most destructive call in the server: it removes the source and
    **every diagram and version history derived from it**. It does not touch
    anything in the cloud account itself, but the Hava-side history is gone for
    good. Name the source and its diagram count to the user and get explicit
    agreement before calling.

    Args:
        source_id: The source UUID.
        confirm: Must be true.

    Returns:
        str: Confirmation naming what was removed.
    """
    require_confirm(confirm, f"delete source {source_id} and all of its diagrams")
    current = client()
    name = None
    try:
        existing = await current.get_json(f"/sources/{source_id}")
        name = (existing or {}).get("display_name") or (existing or {}).get("name")
    except HavaError:
        pass
    await current.request("DELETE", f"/sources/{source_id}")
    label = f"{name!r} (`{source_id}`)" if name else f"`{source_id}`"
    return (
        f"Deleted source {label}, along with its resources and diagrams. "
        f"The cloud account itself was not touched. This cannot be undone."
    )
