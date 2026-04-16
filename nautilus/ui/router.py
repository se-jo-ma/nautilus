"""Admin UI route handlers for the Nautilus operator dashboard.

Implements the source-status page (FR-1, FR-2, AC-1.1, AC-1.3).
Each endpoint serves a full page for normal requests or an HTMX partial
when the ``HX-Request`` header is present.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from nautilus.core.broker import Broker
from nautilus.ui.dependencies import get_auth_user, get_broker

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
    return templates.TemplateResponse(template_name, context)


__all__ = ["router"]
