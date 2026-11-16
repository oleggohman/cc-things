"""Hava reports (cost and inventory reporting).

Note: ``GET /reports`` returned **403 Forbidden** on the account used to build
this server, so reports appear to need a higher Hava plan. The tools are here
and correct, and surface that 403 with an explanation rather than looking broken.
"""

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
    resolve_save_path,
)
from ..errors import HavaError
from ..formatting import (
    ResponseFormat,
    as_output,
    render_reports,
    render_simple,
    summarize_report,
)

_PLAN_HINT = (
    "Hava returned 403 for reports. Reporting is a plan feature - confirm your "
    "Hava plan includes it, and that this API token's account has access."
)


@hava_tool("hava_list_reports", title="List Hava reports")
async def hava_list_reports(
    page: Annotated[int | None, Field(default=None, description="1-based page number.", ge=1)] = None,
    page_size: Annotated[int, Field(default=25, description="Reports per page.", ge=1, le=100)] = 25,
    sort: Annotated[str | None, Field(default=None, description="Field to sort by.")] = None,
    sort_dir: Annotated[Literal["asc", "desc"] | None, Field(default=None, description="Sort direction.")] = None,
    page_token: Annotated[str | None, Field(default=None, description="next_page_token from a previous call.")] = None,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """List the reports available in the Hava account.

    Args:
        page: 1-based page number.
        page_size: Reports per page, 1-100.
        sort: Field to sort by.
        sort_dir: 'asc' or 'desc'.
        page_token: Opaque token from a previous response.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: Markdown table, or JSON {"total","count","reports"}.

    Error Handling:
        A 403 means the Hava plan does not include reporting; the message says so.
    """
    current = client()
    try:
        payload = await current.get_json(
            "/reports", params=page_params(page, page_size, sort, sort_dir, page_token)
        )
    except HavaError as exc:
        if "403" in str(exc):
            raise HavaError(f"{exc}\n\n{_PLAN_HINT}") from exc
        raise
    reports = [summarize_report(r) for r in as_results(payload)]
    meta = page_meta(payload)
    data = {"total": meta["total"], "count": len(reports),
            "next_page_token": meta["next_page_token"], "reports": reports}
    return as_output(data, render_reports(reports, meta), response_format)


@hava_tool("hava_get_report", title="Get a Hava report")
async def hava_get_report(
    report_id: Annotated[str, Field(description="The report's UUID, from hava_list_reports.", min_length=1)],
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Get one report's details and contents.

    Args:
        report_id: The report UUID.
        response_format: 'markdown' (default) or 'json'. Use 'json' when you
            need the report's figures rather than its summary.

    Returns:
        str: The report. Markdown shows the headline fields; JSON returns the
        full payload Hava sent, which for cost reports holds the figures.
    """
    current = client()
    try:
        payload = await current.get_json(f"/reports/{report_id}")
    except HavaError as exc:
        if "403" in str(exc):
            raise HavaError(f"{exc}\n\n{_PLAN_HINT}") from exc
        raise
    report = summarize_report(payload or {})
    return as_output(
        {"report": payload},
        render_simple(str(report.get("name") or "Report"), {
            "report_id": f"`{report.get('report_id')}`",
            "type": report.get("type"),
            "state": report.get("state"),
            "created": report.get("created"),
        }, note="_Call again with response_format='json' for the full report data._"),
        response_format,
    )


@hava_tool(
    "hava_export_report",
    title="Export a Hava report",
    read_only=False,
    idempotent=False,
)
async def hava_export_report(
    report_id: Annotated[str, Field(description="The report's UUID.", min_length=1)],
    export_option: Annotated[
        Literal["show", "hide"] | None,
        Field(default=None, description="Hava's report render option: 'show' or 'hide' detail."),
    ] = None,
    save_to: Annotated[str | None, Field(default=None, description="Local file or directory to save the PDF to.")] = None,
    wait_seconds: Annotated[
        int, Field(default=100, description="Polling budget for the export job.", ge=0, le=900)
    ] = 100,
    response_format: Annotated[ResponseFormat, Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")] = ResponseFormat.MARKDOWN,
) -> str:
    """Export a report to PDF, waiting for the job and returning a download link.

    PDF is the only format Hava offers for reports. As with diagram exports the
    link is time-limited, so pass `save_to` if the user wants to keep the file.

    Args:
        report_id: The report UUID.
        export_option: 'show' or 'hide' detail, per Hava's report options.
        save_to: Local path to write the PDF to.
        wait_seconds: Polling budget, 0-900.
        response_format: 'markdown' (default) or 'json'.

    Returns:
        str: The export state, job ID, download URL and saved path.
    """
    current = client()
    body: dict[str, object] = {"export_format": "pdf"}
    if export_option:
        body["export_option"] = export_option
    # The spec declares export_format as both a query parameter and a body
    # field, so send it in both places.
    try:
        response = await current.request(
            "POST", f"/reports/{report_id}/export",
            params={"export_format": "pdf"}, json=body,
        )
    except HavaError as exc:
        if "403" in str(exc):
            raise HavaError(f"{exc}\n\n{_PLAN_HINT}") from exc
        raise

    job_id = job_from_response(response)
    if not job_id:
        raise HavaError(
            "Hava accepted the report export but returned no job reference "
            f"(HTTP {response.status_code})."
        )
    state, download_url = await poll_job(current, job_id, wait_seconds)

    result: dict[str, object] = {
        "state": state, "job_id": job_id, "report_id": report_id,
        "export_format": "pdf", "download_url": download_url,
        "saved_to": None, "bytes": None,
    }
    if state == "complete" and download_url and save_to:
        content, _ = await current.download(download_url)
        path = resolve_save_path(save_to, f"hava-report-{report_id}.pdf")
        path.write_bytes(content)
        result["saved_to"] = str(path)
        result["bytes"] = len(content)
    elif state != "complete":
        result["note"] = (
            f"Still {state} after {wait_seconds}s. Collect it with "
            f"hava_get_job(job_id=\"{job_id}\", save_to=...)."
        )

    return as_output(result, render_simple(f"Report export {state}", {
        "report_id": f"`{report_id}`",
        "job_id": f"`{job_id}`",
        "download_url": result.get("download_url"),
        "saved to": result.get("saved_to"),
        "bytes": result.get("bytes"),
    }, note=str(result.get("note") or "")), response_format)
