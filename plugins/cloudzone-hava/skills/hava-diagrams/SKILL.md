---
name: hava-diagrams
version: 3
description: Find, inspect, export and manage Hava.io cloud architecture diagrams for AWS, Azure, GCP and Kubernetes accounts. Use whenever someone asks for a cloud architecture diagram, a network/VPC topology picture, a security-group view, an inventory of cloud resources, an "architecture doc" or a Visio/PNG/PDF export of infrastructure — and also when they ask what changed in an environment over time, want to share or embed a diagram, want to refresh diagrams after a deploy, or need to manage Hava teams, projects, members or API tokens. Do NOT use for drawing diagrams by hand (use a diagramming tool) or for live cloud API queries (use the cloud provider's own CLI).
---

# Hava cloud diagrams

Hava continuously imports connected cloud accounts and generates architecture
diagrams from the real configuration. Nothing here changes cloud
infrastructure, but several tools do change things inside Hava.

Full parameter lists for all 47 tools: `references/tools.md`.

## The one thing to understand first

Hava's UI says *diagram*; the API says **environment**, and each environment
holds several **views**:

| view | what it shows | availability |
|---|---|---|
| `infrastructure` | the clean topology diagram | always |
| `extended` | topology plus extra detail | always |
| `security` | security groups and open ports | AWS and Azure only |
| `container` | containerised workloads | only where containers were found |
| `list` | every resource, visualised or not | always |

**Exports act on a view, not on a diagram.** The normal flow is: find the
diagram → pick a view → export. Every listing already returns each view's
`view_id`, so you rarely need an extra lookup.

## Choosing a tool

| the ask | tool |
|---|---|
| "what diagrams do we have?" | `hava_list_diagrams` |
| "find the prod diagram" | `hava_find_diagrams` with `name_contains` |
| "which diagram has vpc-123?" | `hava_find_diagrams` with `resource_query` (see caveats) |
| "what's in this diagram?" | `hava_get_diagram`, `include_resources` if needed |
| "what's running in eu-west-1?" | `hava_list_resources` |
| "dump our whole inventory" | `hava_export_resources` with `save_to` |
| "what changed last week?" | `hava_list_diagram_versions`, then pass `revision_id` |
| "export it as PNG/PDF/Visio" | `hava_export_diagram` |
| "give me a shareable link" | `hava_create_diagram_share` — **publishes publicly** |
| "refresh after our deploy" | `hava_sync_source` |
| "which cloud accounts are connected?" | `hava_list_sources`, `hava_get_source` |
| "make a diagram of just these VPCs" | `hava_create_diagram` with a query |
| "who has access?" | `hava_list_teams`, `hava_list_projects` |
| "audit our API tokens" | `hava_list_api_tokens` |
| "connect our AWS account" | `hava_create_source` (cross-account role only) |
| "rotate a source's credentials" | `hava_update_source_credentials` |
| "create an API token" | `hava_create_api_token` |
| auth trouble | `hava_auth_status` |

Every tool takes `response_format`: `markdown` (default, compact) or `json`
when you need to pick fields out programmatically.

## Export format and view compatibility

Validated before calling Hava, so a bad pair fails instantly with a message
naming what *would* work:

| format | views it accepts |
|---|---|
| `png`, `pdf` | infrastructure, extended, security, container — **not** list |
| `vsdx` (editable Visio) | infrastructure **only** |
| `csv`, `json` | every view |

Use `vsdx` when someone wants to edit the diagram, `pdf` for a document, `png`
to paste into a page, and `csv`/`json` when they want resource data rather than
a picture.

## Exports are asynchronous — budget for it

`hava_export_diagram` queues a job and polls it. `wait_seconds` defaults to
100, deliberately under the 120s tool timeout most clients enforce. Large
diagrams genuinely exceed that: a 461-resource VPC took over two minutes as
`vsdx`. When the budget runs out you get a `job_id` back — **that is not a
failure**. Call `hava_get_job` with it, optionally with its own `save_to` and a
larger `wait_seconds`.

Download URLs are short-lived signed CDN links. If the user wants to keep the
file, pass `save_to` rather than handing them a URL that will expire.

## Search query syntax (tested, not as documented)

Fields that **work** on `hava_list_resources` and `hava_find_diagrams`:
`source:<source_id>`, `region:<region>`, `vpc:<vpc-id>`, `cluster:"<arn>"`, and
tag filters such as `CostCenter:DEV`, combined with `AND`/`OR` and parentheses.

- **`type:` does not work**, despite appearing in Hava's docs — it returns zero
  results. Filter by type with `hava_list_resources`'s `type_contains`
  parameter instead.
- **`name:` does not work** either.
- Bare words (no `field:`) are rejected with a 422.

## Context discipline

- A broad resource query matches enormous sets — `region:eu-west-1` returned
  **13,979** resources on a real account. `hava_list_resources` leads with a
  per-type breakdown and caps the listing at `limit`; keep it small and read
  the breakdown rather than paging through everything.
- `hava_get_diagram` omits resources by default. Only pass `include_resources`
  when the resources are the point, and keep `resource_limit` modest.
- `hava_export_resources` is a bulk dump for a **file**. Always pass `save_to`.
- Prefer `hava_find_diagrams` over listing every page when the user named
  something.

## Confirm before these

Tools that change Hava require an explicit `confirm=true` and should never be
called speculatively. Say what will be affected, in the user's own terms, and
wait for a clear yes:

- `hava_delete_source` — **the most destructive call here.** Removes the cloud
  source *and every diagram and version history derived from it*. The cloud
  account itself is untouched.
- `hava_delete_diagram` — permanent, takes the version history with it.
- `hava_delete_team` — per Hava's docs this also removes the team's members
  **from the account**, so it can revoke people's access entirely.
- `hava_delete_api_token` — instant and irreversible; may be the token this
  server itself is using, which would break every later call.
- `hava_delete_project`, `hava_remove_team_member`,
  `hava_remove_project_member`, `hava_delete_diagram_note`.

Also treat these as side effects worth flagging first, even though they are not
destructive:

- `hava_create_diagram_share` **publishes the diagram publicly.** Anyone with
  the URL can view the architecture without signing in — for production that
  means exposing network layout, security groups and resource names.
- `hava_invite_team_member` **emails a real person** and grants them access to
  your architecture documentation.
- `hava_sync_source` calls out to the cloud provider, can take many minutes,
  and adds a new version to every diagram in that source.
- `hava_create_team` / `hava_update_team` with `roles` grants account-wide
  permissions; `roles` **replaces** the list rather than adding to it.
- Writing files: only pass `save_to` when a file was asked for, and say where
  it landed.

## Tools that handle secrets

`hava_create_source` connects AWS accounts by cross-account role only (no
secret); Azure, GCP and AWS-key sources must be added in the Hava UI.
`hava_update_source_credentials` and `hava_create_api_token` put cloud
credentials or a new API token into the conversation transcript. Warn the user
first and never repeat a secret back.

API access needs a Hava Teams/Business plan or a self-hosted install.
Read-only mode is an option in the same configuration flow and hides every
mutating tool.

`hava_delete_api_token` revokes a Hava credential; it does not configure
the token used by this plugin.
