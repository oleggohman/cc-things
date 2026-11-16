"""Shaping and rendering of Hava API payloads.

Hava's responses carry a lot of detail that an agent rarely needs (every
thumbnail URL, every nested resource attribute). Each ``summarize_*`` helper
reduces a payload to the fields that matter, and each ``render_*`` helper turns
a summary into compact Markdown. Tools return Markdown by default and the full
summary as JSON on request.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence

from .views import short_name


class ResponseFormat(str, Enum):
    """Output format for tool responses."""

    MARKDOWN = "markdown"
    JSON = "json"


def as_output(data: Any, markdown: str, response_format: ResponseFormat | str) -> str:
    """Return either the Markdown rendering or the JSON payload."""
    fmt = ResponseFormat(response_format)
    if fmt is ResponseFormat.JSON:
        return json.dumps(data, indent=2, default=str)
    return markdown


def iso(value: Any) -> str:
    """Render a Hava timestamp (ISO string or epoch seconds) readably."""
    if value in (None, ""):
        return "-"
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# --------------------------------------------------------------------------- #
# Summarizers
# --------------------------------------------------------------------------- #

def summarize_view(view: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "view": short_name(view.get("type")),
        "view_id": view.get("id"),
        "view_type": view.get("type"),
        "revision_id": view.get("revision_id"),
        "regions": view.get("regions") or [],
        "empty": view.get("empty"),
        "thumbnail_url": view.get("image_url"),
        "thumbnail_generated": iso(view.get("export_timestamp")),
    }


def summarize_source(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_id": source.get("id"),
        "name": source.get("display_name") or source.get("name"),
        "type": source.get("type"),
        "provider_account_id": source.get("provider_account_id"),
        "state": source.get("state"),
        "info": source.get("info"),
    }


def summarize_resource(resource: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "resource_id": resource.get("id"),
        "name": resource.get("name"),
        "type": resource.get("type"),
        "region": resource.get("region"),
        "provider_id": resource.get("provider_id"),
        "provider_account_id": resource.get("provider_account_id"),
        "monthly_price": resource.get("price"),
    }


def summarize_environment(env: Mapping[str, Any]) -> dict[str, Any]:
    """Shape an EnvironmentSummary or Environment payload into a diagram record."""
    views = [summarize_view(v) for v in env.get("views") or ()]
    summary: dict[str, Any] = {
        "diagram_id": env.get("id"),
        "name": env.get("name"),
        "state": env.get("state"),
        "diagram_type": env.get("environment_type"),
        "query": env.get("query"),
        "sources": [summarize_source(s) for s in env.get("sources") or ()],
        "views": views,
    }
    current = env.get("current_revision") or {}
    if current.get("id"):
        summary["current_revision_id"] = current["id"]
    facet = env.get("facet") or {}
    if isinstance(facet.get("resources"), list):
        summary["resource_count"] = len(facet["resources"])
    return summary


def summarize_revision(revision: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "revision_id": revision.get("id"),
        "from": iso(revision.get("from")),
        "to": iso(revision.get("to")) if revision.get("to") else "current",
    }


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #

def _views_cell(views: Sequence[Mapping[str, Any]]) -> str:
    if not views:
        return "-"
    return ", ".join(f"{v['view']} ({v['view_id']})" for v in views)


def _sources_cell(sources: Sequence[Mapping[str, Any]]) -> str:
    if not sources:
        return "-"
    return ", ".join(str(s.get("name") or s.get("source_id")) for s in sources)


def render_diagram_list(diagrams: Sequence[Mapping[str, Any]], meta: Mapping[str, Any]) -> str:
    if not diagrams:
        return "No diagrams (Hava environments) found."
    lines = [f"**{len(diagrams)} diagram(s)**"]
    total = meta.get("total")
    if total is not None:
        lines[0] += f" of {total} total"
    lines.append("")
    for d in diagrams:
        lines.append(f"### {d.get('name') or '(unnamed)'}")
        lines.append(f"- diagram_id: `{d.get('diagram_id')}`")
        lines.append(
            f"- state: {d.get('state')} | type: {d.get('diagram_type')}"
            + (f" | query: `{d['query']}`" if d.get("query") else "")
        )
        lines.append(f"- sources: {_sources_cell(d.get('sources') or [])}")
        lines.append(f"- views: {_views_cell(d.get('views') or [])}")
        lines.append("")
    if meta.get("next_page_token"):
        lines.append(
            f"More results available - call again with "
            f"page_token=\"{meta['next_page_token']}\"."
        )
    if meta.get("truncated"):
        lines.append(
            "Result set was truncated by `limit`; raise `limit` or narrow the filter."
        )
    if meta.get("scanned") is not None:
        lines.append(f"_Scanned {meta['scanned']} diagram(s) while filtering by name._")
    if meta.get("more_pages"):
        lines.append(
            "Stopped after reaching `limit` - raise `limit` for more matches."
            if meta.get("stopped_at_limit")
            else "Not every diagram was scanned (`max_pages` reached) - raise "
            "`max_pages` to search further."
        )
    return "\n".join(lines).rstrip()


def render_diagram(diagram: Mapping[str, Any], resources: Sequence[Mapping[str, Any]] | None) -> str:
    lines = [
        f"# {diagram.get('name') or '(unnamed)'}",
        f"- diagram_id: `{diagram.get('diagram_id')}`",
        f"- state: {diagram.get('state')} | type: {diagram.get('diagram_type')}",
    ]
    if diagram.get("query"):
        lines.append(f"- query: `{diagram['query']}`")
    if diagram.get("current_revision_id"):
        lines.append(f"- current_revision_id: `{diagram['current_revision_id']}`")
    if diagram.get("resource_count") is not None:
        lines.append(f"- resources in diagram: {diagram['resource_count']}")

    lines.append("\n## Sources")
    sources = diagram.get("sources") or []
    if not sources:
        lines.append("_none_")
    for s in sources:
        lines.append(
            f"- {s.get('name')} (`{s.get('source_id')}`)"
            + (f" - {s.get('type')}" if s.get("type") else "")
            + (f", account {s.get('provider_account_id')}" if s.get("provider_account_id") else "")
        )

    lines.append("\n## Views (use view_id with hava_export_diagram)")
    views = diagram.get("views") or []
    if not views:
        lines.append("_none yet - the environment may still be building_")
    for v in views:
        bits = [f"- **{v['view']}** - view_id `{v['view_id']}`"]
        if v.get("regions"):
            bits.append(f"regions: {', '.join(v['regions'])}")
        if v.get("empty"):
            bits.append("empty: true")
        lines.append(" | ".join(bits))

    if resources is not None:
        lines.append(f"\n## Resources ({len(resources)} shown)")
        if not resources:
            lines.append("_none_")
        for r in resources:
            lines.append(
                f"- {r.get('name') or '(unnamed)'} - {r.get('type')}"
                + (f" | {r.get('region')}" if r.get("region") else "")
                + (f" | {r.get('provider_id')}" if r.get("provider_id") else "")
            )
    return "\n".join(lines)


def render_search_results(results: Sequence[Mapping[str, Any]], meta: Mapping[str, Any]) -> str:
    if not results:
        return (
            "No diagrams matched. Hava search syntax examples: `vpc:vpc-1234`, "
            "`type:ec2_instance AND region:us-east-1`, `CostCenter:DEV`. "
            "See https://docs.hava.io/discover/searching/search-syntax"
        )
    lines = [f"**{len(results)} matching diagram(s)**", ""]
    for r in results:
        lines.append(f"### {r.get('name') or '(unnamed)'}")
        lines.append(f"- diagram_id: `{r.get('diagram_id') or r.get('id')}`")
        if r.get("url"):
            lines.append(f"- open in Hava (matches highlighted): {r['url']}")
        if r.get("views"):
            lines.append(f"- views: {_views_cell(r['views'])}")
        lines.append("")
    if meta.get("next_page_token"):
        lines.append(f"More results available - next_page_token: `{meta['next_page_token']}`")
    return "\n".join(lines).rstrip()


def render_revisions(revisions: Sequence[Mapping[str, Any]], meta: Mapping[str, Any]) -> str:
    if not revisions:
        return "No versions found for this diagram."
    lines = [
        f"**{len(revisions)} version(s)**"
        + (f" of {meta['total']} total" if meta.get("total") is not None else ""),
        "",
        "| revision_id | covers from | covers to |",
        "| --- | --- | --- |",
    ]
    for r in revisions:
        lines.append(f"| `{r['revision_id']}` | {r['from']} | {r['to']} |")
    if meta.get("next_page_token"):
        lines.append(f"\nNext page token: `{meta['next_page_token']}`")
    return "\n".join(lines)


def render_sources(sources: Sequence[Mapping[str, Any]]) -> str:
    if not sources:
        return "No cloud sources are connected to this Hava account."
    lines = [f"**{len(sources)} source(s)**", "", "| name | source_id | type | account | state |", "| --- | --- | --- | --- | --- |"]
    for s in sources:
        lines.append(
            f"| {s.get('name') or '-'} | `{s.get('source_id')}` | {s.get('type') or '-'} "
            f"| {s.get('provider_account_id') or '-'} | {s.get('state') or '-'} |"
        )
    return "\n".join(lines)


def render_export(result: Mapping[str, Any]) -> str:
    lines = [
        f"# Export {result.get('state')}",
        f"- diagram: {result.get('diagram_name') or result.get('diagram_id') or '-'}",
        f"- view: {result.get('view')} (`{result.get('view_id')}`)",
        f"- format: {result.get('export_format')}",
        f"- job_id: `{result.get('job_id')}`",
    ]
    if result.get("revision_id"):
        lines.append(f"- revision_id: `{result['revision_id']}`")
    if result.get("download_url"):
        lines.append(f"- download_url: {result['download_url']}")
        lines.append("  (Hava export links are time-limited - download promptly.)")
    if result.get("saved_to"):
        lines.append(f"- saved to: `{result['saved_to']}` ({result.get('bytes')} bytes)")
    if result.get("note"):
        lines.append(f"\n{result['note']}")
    return "\n".join(lines)


def render_job(job: Mapping[str, Any]) -> str:
    lines = [f"Job `{job.get('job_id')}` state: **{job.get('state')}**"]
    if job.get("result_url"):
        lines.append(f"Result: {job['result_url']}")
    if job.get("note"):
        lines.append(job["note"])
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Summarizers and renderers for the wider API surface
# --------------------------------------------------------------------------- #

def summarize_member(member: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "user_id": member.get("id"),
        "username": member.get("username"),
        "email": member.get("email"),
        "name": " ".join(
            p for p in (member.get("first_name"), member.get("last_name")) if p
        ) or None,
    }


def summarize_team(team: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "team_id": team.get("id"),
        "name": team.get("name"),
        "account_id": team.get("account_id"),
        "roles": team.get("roles") or [],
        "members": [summarize_member(m) for m in team.get("members") or ()],
    }


def summarize_project(project: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "project_id": project.get("id"),
        "name": project.get("name"),
        "description": project.get("description"),
        "account_id": project.get("account_id"),
        "members": [summarize_member(m) for m in project.get("members") or ()],
    }


def summarize_token(token: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "token_id": token.get("id"),
        "name": token.get("name"),
        "account_id": token.get("account_id"),
        "last_used": iso(token.get("last_used_at")) if token.get("last_used_at") else "never",
    }


def summarize_note(note: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "note_id": note.get("id"),
        "note": note.get("note"),
        "created": iso(note.get("created_at")) if note.get("created_at") else None,
        "author": (note.get("user") or {}).get("username") or note.get("username"),
        "tagged_users": note.get("tagged_users") or [],
    }


def summarize_share(share: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "share_id": share.get("id"),
        "type": (share.get("type") or "").replace("Share::", "") or None,
        "url": share.get("url") or share.get("share_url"),
        "token": "present" if share.get("token") else None,
        "config": share.get("config") or {},
    }


def summarize_report(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "report_id": report.get("id"),
        "name": report.get("name"),
        "type": report.get("type"),
        "state": report.get("state"),
        "created": iso(report.get("created_at")) if report.get("created_at") else None,
    }


def summarize_source_detail(source: Mapping[str, Any]) -> dict[str, Any]:
    """Like summarize_source but with the sync timings GET /sources/{id} adds."""
    summary = summarize_source(source)
    summary.update(
        {
            "last_sync": iso(source.get("last_sync")) if source.get("last_sync") else "never",
            "sync_queued": iso(source.get("sync_queued")) if source.get("sync_queued") else None,
        }
    )
    return summary


def _rows(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join("-" if c in (None, "") else str(c) for c in row) + " |")
    return out


def _pagination_note(meta: Mapping[str, Any]) -> list[str]:
    if meta.get("next_page_token"):
        return ["", f"More available - call again with page_token=\"{meta['next_page_token']}\"."]
    return []


def render_teams(teams: Sequence[Mapping[str, Any]], meta: Mapping[str, Any]) -> str:
    if not teams:
        return "No teams found in this Hava account."
    lines = [f"**{len(teams)} team(s)**" + (f" of {meta['total']} total" if meta.get("total") is not None else ""), ""]
    for team in teams:
        lines.append(f"### {team.get('name') or '(unnamed)'}")
        lines.append(f"- team_id: `{team.get('team_id')}`")
        if team.get("roles"):
            lines.append(f"- roles: {', '.join(map(str, team['roles']))}")
        members = team.get("members") or []
        lines.append(f"- members ({len(members)}):")
        for m in members:
            lines.append(f"  - {m.get('name') or m.get('username') or '?'} <{m.get('email') or '?'}> `{m.get('user_id')}`")
        lines.append("")
    return "\n".join(lines + _pagination_note(meta)).rstrip()


def render_projects(projects: Sequence[Mapping[str, Any]], meta: Mapping[str, Any]) -> str:
    if not projects:
        return (
            "No projects found in this Hava account. Projects group environments for "
            "access control; create one with hava_create_project."
        )
    lines = [f"**{len(projects)} project(s)**" + (f" of {meta['total']} total" if meta.get("total") is not None else ""), ""]
    for p in projects:
        lines.append(f"### {p.get('name') or '(unnamed)'}")
        lines.append(f"- project_id: `{p.get('project_id')}`")
        if p.get("description"):
            lines.append(f"- {p['description']}")
        members = p.get("members") or []
        if members:
            lines.append(f"- members ({len(members)}): " + ", ".join(
                f"{m.get('username') or m.get('email')} (`{m.get('user_id')}`)" for m in members))
        lines.append("")
    return "\n".join(lines + _pagination_note(meta)).rstrip()


def render_tokens(tokens: Sequence[Mapping[str, Any]], meta: Mapping[str, Any]) -> str:
    if not tokens:
        return "No API tokens found in this Hava account."
    lines = [f"**{len(tokens)} API token(s)**", ""]
    lines += _rows(["name", "token_id", "last used"],
                   [[t.get("name"), f"`{t.get('token_id')}`", t.get("last_used")] for t in tokens])
    lines.append("")
    lines.append("_Token values are never returned by the API - only this metadata._")
    return "\n".join(lines + _pagination_note(meta)).rstrip()


def render_notes(notes: Sequence[Mapping[str, Any]], meta: Mapping[str, Any]) -> str:
    if not notes:
        return "This diagram has no notes."
    lines = [f"**{len(notes)} note(s)**" + (f" of {meta['total']} total" if meta.get("total") is not None else ""), ""]
    for n in notes:
        head = f"- `{n.get('note_id')}`"
        if n.get("author"):
            head += f" by {n['author']}"
        if n.get("created"):
            head += f" on {n['created']}"
        lines.append(head)
        lines.append(f"  {n.get('note')}")
    return "\n".join(lines + _pagination_note(meta)).rstrip()


def render_shares(shares: Sequence[Mapping[str, Any]], meta: Mapping[str, Any]) -> str:
    if not shares:
        return (
            "This diagram has no shares. Create an embeddable share with "
            "hava_create_diagram_share."
        )
    lines = [f"**{len(shares)} share(s)**", ""]
    for s in shares:
        lines.append(f"- **{s.get('type') or '?'}** - share_id `{s.get('share_id')}`")
        if s.get("url"):
            lines.append(f"  url: {s['url']}")
        if s.get("config"):
            lines.append(f"  config: {s['config']}")
    lines.append("")
    lines.append("_Anyone with a share URL can view the diagram without signing in._")
    return "\n".join(lines + _pagination_note(meta)).rstrip()


def render_reports(reports: Sequence[Mapping[str, Any]], meta: Mapping[str, Any]) -> str:
    if not reports:
        return "No reports found in this Hava account."
    lines = [f"**{len(reports)} report(s)**" + (f" of {meta['total']} total" if meta.get("total") is not None else ""), ""]
    lines += _rows(["name", "report_id", "type", "state", "created"],
                   [[r.get("name"), f"`{r.get('report_id')}`", r.get("type"), r.get("state"), r.get("created")]
                    for r in reports])
    return "\n".join(lines + _pagination_note(meta)).rstrip()


def render_resources(
    resources: Sequence[Mapping[str, Any]],
    total: int,
    by_type: Sequence[tuple[str, int]],
    query: str,
) -> str:
    if not total:
        return (
            f"No resources matched `{query}`.\n\n"
            "Fields verified to work against the live API: `source:<source_id>`, "
            "`region:<region>`, `vpc:<vpc-id>`, `cluster:\"<arn>\"`, and tag "
            "filters such as `CostCenter:DEV`. Note `type:` does **not** work "
            "despite appearing in Hava's docs."
        )
    lines = [f"**{total} resource(s)** matched `{query}`", ""]
    if by_type:
        lines.append("Breakdown by type:")
        lines += _rows(["type", "count"], [[t, c] for t, c in by_type])
        lines.append("")
    if len(resources) < total:
        lines.append(f"Showing the first {len(resources)}; raise `limit` for more.")
        lines.append("")
    for r in resources:
        bits = [f"- {r.get('name') or '(unnamed)'}", f"{(r.get('type') or '').split('::')[-1]}"]
        if r.get("region"):
            bits.append(r["region"])
        if r.get("provider_id"):
            bits.append(str(r["provider_id"]))
        if r.get("monthly_price"):
            bits.append(f"${r['monthly_price']}/mo")
        lines.append(" | ".join(bits))
    return "\n".join(lines)


def render_source_detail(source: Mapping[str, Any]) -> str:
    lines = [
        f"# {source.get('name') or '(unnamed)'}",
        f"- source_id: `{source.get('source_id')}`",
        f"- type: {source.get('type')}",
        f"- cloud account: {source.get('provider_account_id')}",
        f"- state: {source.get('state')}",
        f"- last sync: {source.get('last_sync')}",
    ]
    if source.get("sync_queued"):
        lines.append(f"- sync queued: {source['sync_queued']}")
    if source.get("info"):
        lines.append(f"- credential/role: {source['info']}")
    return "\n".join(lines)


def render_simple(title: str, fields: Mapping[str, Any], note: str | None = None) -> str:
    lines = [f"# {title}"]
    for key, value in fields.items():
        if value in (None, "", []):
            continue
        lines.append(f"- {key}: {value}")
    if note:
        lines += ["", note]
    return "\n".join(lines)
