"""Admin UI route handlers for the Nautilus operator dashboard.

Implements the source-status page (FR-1, FR-2, AC-1.1, AC-1.3) and the
decisions / audit-log viewer (FR-4, FR-5, AC-2.1, AC-2.3).
Each endpoint serves a full page for normal requests or an HTMX partial
when the ``HX-Request`` header is present.
"""

from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from nautilus.core.broker import Broker
from nautilus.ui.audit_reader import AuditReader
from nautilus.ui.dependencies import get_audit_path, get_auth_user, get_broker

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))


@router.get("/sources")
async def source_status(
    request: Request,
    broker: Annotated[Broker, Depends(get_broker)],
    user: Annotated[str, Depends(get_auth_user)],
) -> HTMLResponse:
    """Source status page — lists configured sources with metadata.

    SECURITY: ``SourceConfig.connection`` is never passed to the template
    (it contains credentials / DSNs).  Only ``id``, ``type``,
    ``classification``, ``description``, and ``data_types`` are exposed.

    When the ``HX-Request`` header is present, returns only the table-body
    partial (``partials/source_table_body.html``) for HTMX swap; otherwise
    returns the full page (``pages/sources.html``).
    """
    sources = broker.sources
    source_rows = [
        {
            "id": s.id,
            "type": s.type,
            "classification": s.classification,
            "description": s.description,
            "data_types": s.data_types,
        }
        for s in sources
    ]

    context = {
        "request": request,
        "user": user,
        "sources": source_rows,
        "source_count": len(source_rows),
    }

    is_htmx = request.headers.get("HX-Request") == "true"
    template_name = (
        "partials/source_table_body.html" if is_htmx else "pages/sources.html"
    )
    return templates.TemplateResponse(request, template_name, context)


@router.get("/decisions")
async def decisions(
    request: Request,
    audit_path: Annotated[str, Depends(get_audit_path)],
    user: Annotated[str, Depends(get_auth_user)],
    agent_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    outcome: str | None = None,
    search: str | None = None,
) -> HTMLResponse:
    """Decisions page — lists audit entries with filters.

    Query params ``agent_id``, ``start``, ``end``, ``outcome``, and
    ``search`` narrow results.  ``outcome`` maps to whether the entry has
    denial records (``"denied"``) or not (``"allowed"``).

    When the ``HX-Request`` header is present, returns only the table-body
    partial (``partials/decision_row.html`` rows) for HTMX swap; otherwise
    returns the full page (``pages/decisions.html``).
    """
    reader = AuditReader(audit_path)
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    page = reader.read_page(agent_id=agent_id, start=start_dt, end=end_dt)

    entries = page.entries

    # Filter by outcome (allowed / denied)
    if outcome == "denied":
        entries = [e for e in entries if e.denial_records]
    elif outcome == "allowed":
        entries = [e for e in entries if not e.denial_records]

    # Free-text search across request_id, agent_id, raw_intent
    if search:
        term = search.lower()
        entries = [
            e
            for e in entries
            if term in e.request_id.lower()
            or term in e.agent_id.lower()
            or term in e.raw_intent.lower()
        ]

    decisions_list = [
        {
            "timestamp": e.timestamp,
            "request_id": e.request_id,
            "agent_id": e.agent_id,
            "sources_queried": ", ".join(e.sources_queried) if e.sources_queried else "—",
            "sources_denied": ", ".join(e.sources_denied) if e.sources_denied else "—",
            "duration_ms": e.duration_ms,
        }
        for e in entries
    ]

    filters = {
        "agent_id": agent_id or "",
        "start": start or "",
        "end": end or "",
        "outcome": outcome or "",
        "search": search or "",
    }

    context = {
        "request": request,
        "user": user,
        "decisions": decisions_list,
        "filters": filters,
    }

    is_htmx = request.headers.get("HX-Request") == "true"
    if is_htmx:
        # Return just the table rows for HTMX swap
        rows = "".join(
            templates.get_template("partials/decision_row.html").render(
                decision=d
            )
            for d in decisions_list
        )
        if not decisions_list:
            rows = (
                '<tr><td colspan="6"><div class="empty-state">'
                "<p>No decisions found</p></div></td></tr>"
            )
        return HTMLResponse(content=rows)
    return templates.TemplateResponse(request, "pages/decisions.html", context)


@router.get("/decisions/{request_id}")
async def decision_detail(
    request: Request,
    request_id: str,
    audit_path: Annotated[str, Depends(get_audit_path)],
    user: Annotated[str, Depends(get_auth_user)],
) -> HTMLResponse:
    """Decision detail modal — returns the full trace for a specific request.

    Returns a ``decision_detail.html`` modal fragment containing rule trace,
    routing decisions, scope constraints, denial records, and facts summary
    for the given ``request_id``.
    """
    reader = AuditReader(audit_path)
    page = reader.read_page()

    entry = None
    for e in page.entries:
        if e.request_id == request_id:
            entry = e
            break

    if entry is None:
        return HTMLResponse(
            content='<div class="empty-state"><p>Decision not found</p></div>'
        )

    decision = {
        "request_id": entry.request_id,
        "timestamp": str(entry.timestamp),
        "agent_id": entry.agent_id,
        "rule_trace": entry.rule_trace,
        "routing_decisions": [
            rd.model_dump(mode="json") for rd in entry.routing_decisions
        ],
        "scope_constraints": [
            sc.model_dump(mode="json") for sc in entry.scope_constraints
        ],
        "denial_records": [
            dr.model_dump(mode="json") for dr in entry.denial_records
        ],
        "facts_asserted_summary": entry.facts_asserted_summary,
        "sources_queried": entry.sources_queried,
        "sources_denied": entry.sources_denied,
        "duration_ms": entry.duration_ms,
    }

    context = {"request": request, "decision": decision}
    return templates.TemplateResponse(request, "partials/decision_detail.html", context)


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO datetime string, returning *None* on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


__all__ = ["router"]
