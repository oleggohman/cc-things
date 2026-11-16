# Hava MCP tools reference

Generated from the bundled server (hava-mcp 0.4.1, 47 tools). Descriptions are the server's own; parameters are top-level inputs (`*` = required). `[W]` changes something in Hava, `[!]` is destructive and needs `confirm=true`.

## Contents

- **Find diagrams**: `hava_list_diagrams`, `hava_find_diagrams`
- **Inspect a diagram**: `hava_get_diagram`, `hava_list_diagram_versions`
- **Cloud resources**: `hava_list_resources`, `hava_export_resources` `[W]`
- **Export**: `hava_export_diagram` `[W]`, `hava_get_job`
- **Custom diagrams**: `hava_create_diagram` `[W]`, `hava_update_diagram` `[W]`, `hava_delete_diagram` `[!]`
- **Notes**: `hava_list_diagram_notes`, `hava_create_diagram_note` `[W]`, `hava_delete_diagram_note` `[!]`
- **Shares (public links)**: `hava_list_diagram_shares`, `hava_get_diagram_share`, `hava_create_diagram_share` `[W]`, `hava_update_diagram_share` `[W]`
- **Reports**: `hava_list_reports`, `hava_get_report`, `hava_export_report` `[W]`
- **Cloud sources**: `hava_list_sources`, `hava_get_source`, `hava_sync_source` `[W]`, `hava_create_source` `[W]`, `hava_update_source_credentials` `[W]`, `hava_rename_source` `[W]`, `hava_delete_source` `[!]`
- **Teams and members**: `hava_list_teams`, `hava_get_team`, `hava_create_team` `[W]`, `hava_update_team` `[W]`, `hava_delete_team` `[!]`, `hava_add_team_member` `[W]`, `hava_invite_team_member` `[W]`, `hava_remove_team_member` `[!]`
- **Projects and members**: `hava_list_projects`, `hava_get_project`, `hava_create_project` `[W]`, `hava_update_project` `[W]`, `hava_delete_project` `[!]`, `hava_add_project_member` `[W]`, `hava_remove_project_member` `[!]`
- **API tokens**: `hava_list_api_tokens`, `hava_create_api_token` `[W]`, `hava_delete_api_token` `[!]`
- **Authentication**: `hava_auth_status`

## Find diagrams

### `hava_list_diagrams`

List all Hava diagrams (environments) in the account, one page at a time.

Parameters:

- `page` (integer|null): 1-based page number.
- `page_size` (integer): Diagrams per page. Hava enforces a floor of 10.
- `sort` (null|string): Field to sort by, e.g. 'name'.
- `sort_dir` (string) — one of: asc, desc: Sort direction.
- `page_token` (null|string): next_page_token from a previous call; overrides the other paging args.
- `response_format` (any): 'markdown' or 'json'.

### `hava_find_diagrams`

Find diagrams by name, or by the cloud resources they contain.

Parameters:

- `name_contains` (null|string): Case-insensitive substring of the diagram name, e.g. 'prod'.
- `resource_query` (null|string): Hava search syntax to match resources; returns the diagrams containing them. Examples: 'vpc:vpc-1234', 'type:ec2_instance AND region:us-east-1', '(vpc:vpc-1 OR vpc:vpc-2) AND CostCenter:DEV'.
- `limit` (integer): Maximum diagrams to return.
- `max_pages` (integer): Safety cap on pages scanned when filtering by name.
- `response_format` (any): 'markdown' or 'json'.

## Inspect a diagram

### `hava_get_diagram`

Get one diagram with its views, sources, and optionally its resources.

Parameters:

- `diagram_id`* (string): The diagram (environment) UUID.
- `revision_id` (null|string): A past version to inspect; see hava_list_diagram_versions.
- `include_resources` (boolean): Include the diagram's cloud resources (can be large).
- `resource_limit` (integer): Maximum resources to include.
- `response_format` (any): 'markdown' or 'json'.

### `hava_list_diagram_versions`

List the version history of a diagram, newest first by default.

Parameters:

- `diagram_id`* (string): The diagram (environment) UUID.
- `page` (integer|null): 1-based page number.
- `page_size` (integer): Versions per page.
- `sort_dir` (null|string): Sort direction.
- `page_token` (null|string): next_page_token from a previous call.
- `response_format` (any): 'markdown' or 'json'.

## Cloud resources

### `hava_list_resources`

Find cloud resources across all connected accounts using a Hava query.

Parameters:

- `query`* (string): Hava search query selecting resources. Fields verified against the live API: `source:<source_id>`, `region:<region>`, `vpc:<vpc-id>`, `cluster:"<arn>"`, and tag filters such as `CostCenter:DEV`, comb…
- `type_contains` (null|string): Client-side filter on resource type, e.g. 'EC2::Instance' or 'RDS'.
- `limit` (integer): Maximum resources to list.
- `response_format` (any): 'markdown' or 'json'.

### `hava_export_resources` `[W]`

Export the full resource inventory for one or more cloud sources as JSON.

Parameters:

- `source_ids` (null|string): Comma-separated source IDs to export. Omit for every connected source.
- `save_to` (null|string): Local file or directory to write the JSON to. Strongly recommended - the payload is large.
- `wait_seconds` (integer): Seconds to wait if Hava queues this as a job.
- `response_format` (any): 'markdown' or 'json'.

## Export

### `hava_export_diagram` `[W]`

Export one view of a Hava diagram to PNG, PDF, VSDX, CSV, or JSON.

Parameters:

- `export_format`* (string) — one of: pdf, png, vsdx, csv, json: Export format: 'png' or 'pdf' (images), 'vsdx' (editable Visio), 'csv' or 'json' (data).
- `diagram_id` (null|string): The diagram (environment) UUID. Required unless view_id is given.
- `view` (string) — one of: infrastructure, extended, security, container, list: Which view to export: infrastructure, extended, security, container, list.
- `view_id` (null|string): Export this view UUID directly, skipping lookup by diagram_id + view.
- `revision_id` (null|string): Export a past version; see hava_list_diagram_versions.
- `save_to` (null|string): Local file or directory to save the export to. Omit to just return the download URL.
- `connections` (boolean|null): Draw connections between resources.
- `labels` (boolean|null): Draw resource name labels.
- `isometric` (boolean|null): Render the 3D isometric layout instead of flat topology.
- `timestamp` (boolean|null): Stamp the generation time on the diagram (PNG/PDF only).
- `hide_resource_groups` (boolean|null): Azure only: group by Virtual Network instead of Resource Group.
- `hide_empty_networks` (boolean|null): Hide VPCs/VNets that contain no visible resources.
- `wait_seconds` (integer): How long to poll the export job before returning its job ID. The default stays under the 120s tool timeout most MCP clients use, so a slow export hands back a job ID instead of timing out.
- `response_format` (any): 'markdown' or 'json'.

### `hava_get_job`

Check an asynchronous Hava job and collect its result.

Parameters:

- `job_id`* (string): The job UUID returned by an export or sync.
- `wait_seconds` (integer): Seconds to keep polling before answering. 0 = check once.
- `save_to` (null|string): If the job is finished, save its artifact to this local file or directory.
- `response_format` (any): 'markdown' or 'json'.

## Custom diagrams

### `hava_create_diagram` `[W]`

Create a new custom diagram from a Hava search query.

Parameters:

- `query`* (string): Hava search query defining what the diagram contains. Fields verified against the live API: `source:<source_id>`, `region:<region>`, `vpc:<vpc-id>`, `cluster:"<arn>"`, and tag filters such as `CostCe…
- `name` (null|string): Name for the new diagram.
- `wait_seconds` (integer): Seconds to wait for the initial build before returning.
- `response_format` (any): 'markdown' or 'json'.

### `hava_update_diagram` `[W]`

Change the query or name of a custom diagram, triggering a rebuild.

Parameters:

- `diagram_id`* (string): The custom diagram's UUID.
- `query`* (string): The new search query. Required by Hava even when only renaming. Fields verified against the live API: `source:<source_id>`, `region:<region>`, `vpc:<vpc-id>`, `cluster:"<arn>"`, and tag filters such…
- `name` (null|string): New name for the diagram.
- `response_format` (any): 'markdown' or 'json'.

### `hava_delete_diagram` `[!]`

Permanently delete a custom diagram and its entire version history.

Parameters:

- `diagram_id`* (string): The custom diagram's UUID.
- `confirm` (boolean): Must be true. Deletion is permanent and takes the version history with it.

## Notes

### `hava_list_diagram_notes`

List the notes people have left on a diagram.

Parameters:

- `diagram_id`* (string): The diagram (environment) UUID.
- `page` (integer|null): 1-based page number.
- `page_size` (integer): Notes per page.
- `page_token` (null|string): next_page_token from a previous call.
- `response_format` (any): 'markdown' or 'json'.

### `hava_create_diagram_note` `[W]`

Add a note to a diagram, optionally tagging teammates.

Parameters:

- `diagram_id`* (string): The diagram (environment) UUID.
- `note`* (string): The note text.
- `tagged_user_ids` (array<string>|null): User IDs to tag, which notifies them in Hava. Get IDs from hava_list_teams.
- `response_format` (any): 'markdown' or 'json'.

### `hava_delete_diagram_note` `[!]`

Delete a note from a diagram. Permanent.

Parameters:

- `diagram_id`* (string): The diagram (environment) UUID.
- `note_id`* (string): The note's UUID, from hava_list_diagram_notes.
- `confirm` (boolean): Must be true. Deleting a note is permanent.

## Shares (public links)

### `hava_list_diagram_shares`

List the embeddable shares that exist for a diagram.

Parameters:

- `diagram_id`* (string): The diagram (environment) UUID.
- `page` (integer|null): 1-based page number.
- `page_size` (integer): Shares per page.
- `page_token` (null|string): next_page_token from a previous call.
- `response_format` (any): 'markdown' or 'json'.

### `hava_get_diagram_share`

Get the details and configuration of one diagram share.

Parameters:

- `diagram_id`* (string): The diagram (environment) UUID.
- `share_id`* (string): The share's UUID.
- `response_format` (any): 'markdown' or 'json'.

### `hava_create_diagram_share` `[W]`

Create a publicly accessible, embeddable link to a diagram.

Parameters:

- `diagram_id`* (string): The diagram (environment) UUID.
- `share_type` (string) — one of: full, light, png: 'full' (interactive), 'light' (read-only interactive) or 'png' (static image).
- `config` (null|object): Share options, mainly for PNG shares (e.g. which view and render flags).
- `wait_seconds` (integer): Seconds to wait when Hava queues share generation as a job.
- `response_format` (any): 'markdown' or 'json'.

### `hava_update_diagram_share` `[W]`

Change the configuration of an existing share (PNG render options).

Parameters:

- `diagram_id`* (string): The diagram (environment) UUID.
- `share_id`* (string): The share's UUID.
- `config`* (object): The replacement share configuration. Used to change PNG share render options.
- `response_format` (any): 'markdown' or 'json'.

## Reports

### `hava_list_reports`

List the reports available in the Hava account.

Parameters:

- `page` (integer|null): 1-based page number.
- `page_size` (integer): Reports per page.
- `sort` (null|string): Field to sort by.
- `sort_dir` (null|string): Sort direction.
- `page_token` (null|string): next_page_token from a previous call.
- `response_format` (any): 'markdown' or 'json'.

### `hava_get_report`

Get one report's details and contents.

Parameters:

- `report_id`* (string): The report's UUID, from hava_list_reports.
- `response_format` (any): 'markdown' or 'json'.

### `hava_export_report` `[W]`

Export a report to PDF, waiting for the job and returning a download link.

Parameters:

- `report_id`* (string): The report's UUID.
- `export_option` (null|string): Hava's report render option: 'show' or 'hide' detail.
- `save_to` (null|string): Local file or directory to save the PDF to.
- `wait_seconds` (integer): Polling budget for the export job.
- `response_format` (any): 'markdown' or 'json'.

## Cloud sources

### `hava_list_sources`

List the cloud accounts (AWS/Azure/GCP/Kubernetes sources) connected to Hava.

Parameters:

- `response_format` (any): 'markdown' or 'json'.

### `hava_get_source`

Get one cloud source, including when it last synced.

Parameters:

- `source_id`* (string): The source's UUID, from hava_list_sources.
- `response_format` (any): 'markdown' or 'json'.

### `hava_sync_source` `[W]`

Re-import a cloud account so its diagrams reflect current infrastructure.

Parameters:

- `source_id`* (string): The source's UUID.
- `metadata` (null|object): Optional metadata attached to the job and to the resources/diagrams it creates, e.g. {"build_no": 10}.
- `wait_seconds` (integer): Seconds to wait for the import. 0 returns the job ID immediately, which is usually right - a full import can take many minutes.
- `response_format` (any): 'markdown' or 'json'.

### `hava_create_source` `[W]`

Connect an AWS account to Hava using a cross-account IAM role.

Parameters:

- `name`* (string): Display name for the source.
- `role_arn`* (string): ARN of the IAM role Hava assumes, e.g. arn:aws:iam::123456789012:role/Hava.
- `external_id`* (string): External ID for the role trust policy (MD5 of your Hava account ID, shown in Hava's 'Add Environment' prompt).
- `project_id` (null|string): Project UUID to add the source to. Defaults to the Default project.
- `response_format` (any): 'markdown' or 'json'.

### `hava_update_source_credentials` `[W]`

Replace a source's cloud credentials (and optionally its name).

Parameters:

- `source_id`* (string): The source's UUID.
- `type`* (string) — one of: AWS::Keys, AWS::CrossAccountRole, Azure::Credentials, GCP::ServiceAccountCredentials: The source's type (see hava_get_source). Decides which credential fields apply.
- `name` (null|string): Optional new display name.
- `role_arn` (null|string): AWS::CrossAccountRole: new role ARN.
- `external_id` (null|string): AWS::CrossAccountRole: new external ID.
- `access_key` (null|string): AWS::Keys: new access key ID.
- `secret_key` (null|string): AWS::Keys / Azure::Credentials: new secret. A SECRET.
- `subscription_id` (null|string): Azure::Credentials: subscription ID.
- `tenant_id` (null|string): Azure::Credentials: tenant ID.
- `client_id` (null|string): Azure::Credentials: client ID.
- `service_account_json` (null|string): GCP::ServiceAccountCredentials: new key file JSON text. A SECRET.
- `response_format` (any): 'markdown' or 'json'.

### `hava_rename_source` `[W]`

Rename a connected cloud source.

Parameters:

- `source_id`* (string): The source's UUID.
- `name`* (string): The new display name for the source.
- `response_format` (any): 'markdown' or 'json'.

### `hava_delete_source` `[!]`

Disconnect a cloud source, deleting all its resources and diagrams.

Parameters:

- `source_id`* (string): The source's UUID.
- `confirm` (boolean): Must be true. This also deletes every resource and diagram from this source.

## Teams and members

### `hava_list_teams`

List the teams in a Hava account, with their roles and members.

Parameters:

- `account_id` (null|string): Hava account UUID. Defaults to the account the API token belongs to.
- `page` (integer|null): 1-based page number.
- `page_size` (integer): Teams per page.
- `page_token` (null|string): next_page_token from a previous call.
- `response_format` (any): 'markdown' or 'json'.

### `hava_get_team`

Get one team with its roles and full member list.

Parameters:

- `team_id`* (string): The team's UUID.
- `account_id` (null|string): Hava account UUID. Defaults to the account the API token belongs to.
- `response_format` (any): 'markdown' or 'json'.

### `hava_create_team` `[W]`

Create a team in the Hava account.

Parameters:

- `name`* (string): Name for the new team.
- `roles` (array<string>|null): Roles granted to the team, e.g. ['Admin']. Omit for a team with no elevated roles.
- `account_id` (null|string): Hava account UUID. Defaults to the account the API token belongs to.
- `response_format` (any): 'markdown' or 'json'.

### `hava_update_team` `[W]`

Rename a team or change the roles it grants.

Parameters:

- `team_id`* (string): The team's UUID.
- `name`* (string): The team name. Hava requires it on every update, so pass the current name when only changing roles.
- `roles` (array<string>|null): Replacement roles list, e.g. ['Admin'].
- `account_id` (null|string): Hava account UUID. Defaults to the account the API token belongs to.
- `response_format` (any): 'markdown' or 'json'.

### `hava_delete_team` `[!]`

Delete a team, which also removes its members from the Hava account.

Parameters:

- `team_id`* (string): The team's UUID.
- `confirm` (boolean): Must be true. Per Hava's docs this also removes the team's members from the account.
- `account_id` (null|string): Hava account UUID. Defaults to the account the API token belongs to.

### `hava_add_team_member` `[W]`

Add an existing Hava user to a team by email.

Parameters:

- `team_id`* (string): The team's UUID.
- `email`* (string): Email address of an existing Hava user.
- `account_id` (null|string): Hava account UUID. Defaults to the account the API token belongs to.

### `hava_invite_team_member` `[W]`

Invite someone to Hava by email and add them to a team.

Parameters:

- `team_id`* (string): The team's UUID.
- `email`* (string): Email address to invite.
- `account_id` (null|string): Hava account UUID. Defaults to the account the API token belongs to.

### `hava_remove_team_member` `[!]`

Remove a user from a team, revoking the access that team grants.

Parameters:

- `team_id`* (string): The team's UUID.
- `user_id`* (string): The user's UUID, from hava_get_team.
- `confirm` (boolean): Must be true. This revokes a person's access.
- `account_id` (null|string): Hava account UUID. Defaults to the account the API token belongs to.

## Projects and members

### `hava_list_projects`

List the projects in a Hava account.

Parameters:

- `account_id` (null|string): Hava account UUID. Defaults to the account the API token belongs to.
- `page` (integer|null): 1-based page number.
- `page_size` (integer): Projects per page.
- `page_token` (null|string): next_page_token from a previous call.
- `response_format` (any): 'markdown' or 'json'.

### `hava_get_project`

Get one project with its description and members.

Parameters:

- `project_id`* (string): The project's UUID.
- `account_id` (null|string): Hava account UUID. Defaults to the account the API token belongs to.
- `response_format` (any): 'markdown' or 'json'.

### `hava_create_project` `[W]`

Create a project for grouping environments and scoping access.

Parameters:

- `name`* (string): Name for the new project.
- `description` (null|string): What the project is for.
- `account_id` (null|string): Hava account UUID. Defaults to the account the API token belongs to.
- `response_format` (any): 'markdown' or 'json'.

### `hava_update_project` `[W]`

Rename a project or change its description.

Parameters:

- `project_id`* (string): The project's UUID.
- `name` (null|string): New name.
- `description` (null|string): New description.
- `account_id` (null|string): Hava account UUID. Defaults to the account the API token belongs to.
- `response_format` (any): 'markdown' or 'json'.

### `hava_delete_project` `[!]`

Delete a project, removing its grouping and per-project access.

Parameters:

- `project_id`* (string): The project's UUID.
- `confirm` (boolean): Must be true.
- `account_id` (null|string): Hava account UUID. Defaults to the account the API token belongs to.

### `hava_add_project_member` `[W]`

Give a user access to a project.

Parameters:

- `project_id`* (string): The project's UUID.
- `user_id`* (string): The user's UUID, from hava_list_teams.
- `account_id` (null|string): Hava account UUID. Defaults to the account the API token belongs to.

### `hava_remove_project_member` `[!]`

Revoke a user's access to a project.

Parameters:

- `project_id`* (string): The project's UUID.
- `user_id`* (string): The user's UUID.
- `confirm` (boolean): Must be true. This revokes a person's access.
- `account_id` (null|string): Hava account UUID. Defaults to the account the API token belongs to.

## API tokens

### `hava_list_api_tokens`

List the account's API tokens with their names and last-used times.

Parameters:

- `account_id` (null|string): Hava account UUID. Defaults to the account the API token belongs to.
- `page` (integer|null): 1-based page number.
- `page_size` (integer): Tokens per page.
- `page_token` (null|string): next_page_token from a previous call.
- `response_format` (any): 'markdown' or 'json'.

### `hava_create_api_token` `[W]`

Generate a new API token. The secret is shown once and cannot be retrieved later.

Parameters:

- `name`* (string): A name describing what the token is for, e.g. 'CI pipeline'.
- `account_id` (null|string): Hava account UUID. Defaults to the account the API token belongs to.
- `response_format` (any): 'markdown' or 'json'.

### `hava_delete_api_token` `[!]`

Revoke an API token. Anything using it breaks immediately.

Parameters:

- `token_id`* (string): The token's UUID, from hava_list_api_tokens.
- `confirm` (boolean): Must be true. Anything using this token stops working immediately.
- `account_id` (null|string): Hava account UUID. Defaults to the account the API token belongs to.

## Authentication

### `hava_auth_status`

Report which Hava API token is in use, where it came from, and whether it works.

Parameters:

- `verify` (boolean): Call the Hava API to confirm the token still works.

