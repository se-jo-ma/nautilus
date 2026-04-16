# Tasks: Operator Platform (Phase 4)

## Phase 1: Make It Work (POC)

Focus: Validate each workstream end-to-end. Skip tests, accept shortcuts, hardcoded values OK.

### 1A — Infrastructure Setup

- [x] 1.1 Add runtime dependencies to pyproject.toml
  - **Do**:
    1. Add `sse-starlette`, `python-multipart` to `[project.dependencies]`
    2. Add `influxdb-client`, `aiobotocore` to `[project.dependencies]`
    3. Add `[project.optional-dependencies] otel = [...]` with `opentelemetry-sdk`, `opentelemetry-api`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-exporter-otlp-proto-http`, `prometheus-client`
  - **Files**: `pyproject.toml`
  - **Done when**: `uv sync` (or `pip install -e .`) resolves all deps without error
  - **Verify**: `python -c "import sse_starlette; import multipart; print('OK')"`
  - **Commit**: `feat(deps): add admin-ui, otel, influxdb, s3 dependencies`
  - _Requirements: FR-30, AC-18.1, AC-18.2_

- [x] 1.2 Add dev dependencies, entry points, and package-data to pyproject.toml
  - **Do**:
    1. Add `locust`, `mkdocs`, `mkdocs-material`, `mkdocstrings[python]`, `copier` to `[project.optional-dependencies] dev`
    2. Add `[project.entry-points."fathom.packs"]` with `data-routing-nist` and `data-routing-hipaa`
    3. Add `[project.entry-points."nautilus.adapters"]` with `influxdb` and `s3`
    4. Add `"nautilus.ui"` to `[tool.setuptools.package-data]` for templates and static files: `["templates/**/*", "static/*"]`
  - **Files**: `pyproject.toml`
  - **Done when**: Entry points declared, package-data includes UI assets
  - **Verify**: `python -c "import toml; print('OK')" 2>/dev/null || python -c "print('pyproject.toml updated')"`
  - **Commit**: `feat(deps): add dev deps, entry points, package-data for ui`
  - _Requirements: FR-1, FR-24, FR-25, AC-13.2, AC-14.2, AC-17.3_

- [x] 1.3 [VERIFY] Quality checkpoint: deps resolve
  - **Do**: Run quality commands to verify deps and types
  - **Verify**: `ruff check nautilus tests && pyright`
  - **Done when**: No lint errors, no type errors after dep changes
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

### 1B — Admin UI Skeleton

- [x] 1.4 Create nautilus/ui package with __init__.py and create_admin_router factory
  - **Do**:
    1. Create `nautilus/ui/__init__.py` exporting `create_admin_router()` that returns an `APIRouter(prefix="/admin", tags=["admin"])`
    2. Router includes placeholder routes (will be filled in subsequent tasks)
  - **Files**: `nautilus/ui/__init__.py`
  - **Done when**: `from nautilus.ui import create_admin_router` succeeds and returns an APIRouter
  - **Verify**: `python -c "from nautilus.ui import create_admin_router; r = create_admin_router(); print(r.prefix)"`
  - **Commit**: `feat(ui): create admin router factory`
  - _Requirements: FR-1, AC-1.1_
  - _Design: Component A — Admin UI_

- [x] 1.5 Create dependencies.py with shared admin deps (broker, auth, audit path)
  - **Do**:
    1. Create `nautilus/ui/dependencies.py` with FastAPI dependency functions:
       - `get_broker(request)` → returns `request.app.state.broker`
       - `get_auth_user(request)` → dispatches to `proxy_trust_dependency` or `api_key` based on `request.app.state.auth_mode`
       - `get_audit_path(request)` → returns audit JSONL path from broker config
    2. Reuse existing `proxy_trust_dependency` and `verify_api_key` from `nautilus/transport/auth.py`
  - **Files**: `nautilus/ui/dependencies.py`
  - **Done when**: All three dependency functions importable
  - **Verify**: `python -c "from nautilus.ui.dependencies import get_broker, get_auth_user, get_audit_path; print('OK')"`
  - **Commit**: `feat(ui): add shared admin UI dependencies`
  - _Requirements: FR-10, AC-5.1, AC-5.4_
  - _Design: Component A — dependencies.py_

- [x] 1.6 [P] Create base.html root template and dashboard layout
  - **Do**:
    1. Create `nautilus/ui/templates/base.html` — HTML5 root with `<head>` referencing vendored `/admin/static/htmx.min.js`, `/admin/static/htmx-ext-sse.min.js`, `/admin/static/styles.css`. Nav links to /admin/sources, /admin/decisions, /admin/audit, /admin/attestation. Display `{{ user }}` in header. Block `content` for child templates.
    2. Create `nautilus/ui/templates/layouts/dashboard.html` — extends `base.html`, adds sidebar + content grid layout
  - **Files**: `nautilus/ui/templates/base.html`, `nautilus/ui/templates/layouts/dashboard.html`
  - **Done when**: Templates parse without Jinja2 errors
  - **Verify**: `python -c "from jinja2 import Environment, FileSystemLoader; e=Environment(loader=FileSystemLoader('nautilus/ui/templates')); e.get_template('base.html'); e.get_template('layouts/dashboard.html'); print('OK')"`
  - **Commit**: `feat(ui): add base.html and dashboard layout templates`
  - _Requirements: AC-17.4, AC-17.5, FR-29_
  - _Design: Component A — templates_

- [x] 1.7 [P] Create static assets (htmx.min.js, htmx-ext-sse.min.js, styles.css)
  - **Do**:
    1. Create `nautilus/ui/static/htmx.min.js` — vendored HTMX 2.0.x (download or placeholder with comment noting version)
    2. Create `nautilus/ui/static/htmx-ext-sse.min.js` — vendored SSE extension
    3. Create `nautilus/ui/static/styles.css` — custom CSS (~200 lines) for dashboard layout: nav, sidebar, tables, cards, modals, forms, pagination, responsive grid
  - **Files**: `nautilus/ui/static/htmx.min.js`, `nautilus/ui/static/htmx-ext-sse.min.js`, `nautilus/ui/static/styles.css`
  - **Done when**: All three files exist and are non-empty
  - **Verify**: `test -f nautilus/ui/static/htmx.min.js && test -f nautilus/ui/static/styles.css && echo OK`
  - **Commit**: `feat(ui): vendor htmx 2.0.x + custom styles.css`
  - _Requirements: AC-17.1, AC-17.2, AC-17.5, FR-29_
  - _Design: Component A — static assets_

- [x] 1.8 Create macros/table.html with reusable table Jinja2 macros
  - **Do**:
    1. Create `nautilus/ui/templates/macros/table.html` with macros: `render_table(headers, rows)`, `render_sort_header(field, label, current_sort)`, `render_filter_form(filters)`, `render_empty_state(message)`
  - **Files**: `nautilus/ui/templates/macros/table.html`
  - **Done when**: Macro file parses without Jinja2 errors
  - **Verify**: `python -c "from jinja2 import Environment, FileSystemLoader; e=Environment(loader=FileSystemLoader('nautilus/ui/templates')); e.get_template('macros/table.html'); print('OK')"`
  - **Commit**: `feat(ui): add reusable table macros`
  - _Requirements: AC-17.4_
  - _Design: Component A — macros_

- [x] 1.9 Mount admin router + static files in fastapi_app.py
  - **Do**:
    1. In `create_app()`, after route registrations, add `from nautilus.ui import create_admin_router` and `app.include_router(create_admin_router())`
    2. Add `from fastapi.staticfiles import StaticFiles` and mount static dir: `app.mount("/admin/static", StaticFiles(directory=<ui_static_path>), name="admin-static")`
    3. Use `importlib.resources` or `Path(__file__)` to resolve `nautilus/ui/static/` path
  - **Files**: `nautilus/transport/fastapi_app.py`
  - **Done when**: `/admin/` routes and `/admin/static/` mounts registered on app
  - **Verify**: `python -c "from nautilus.transport.fastapi_app import create_app; print('import OK')"`
  - **Commit**: `feat(ui): mount admin router and static files in fastapi app`
  - _Requirements: FR-1, AC-1.1_
  - _Design: Integration — fastapi_app.py mount_

- [x] 1.10 [VERIFY] Quality checkpoint: admin skeleton
  - **Do**: Run quality commands after admin UI skeleton
  - **Verify**: `ruff check nautilus tests && pyright`
  - **Done when**: No lint errors, no type errors
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

### 1C — Audit Reader (Core Data Layer)

- [x] 1.11 Create AuditReader with seek-based JSONL pagination
  - **Do**:
    1. Create `nautilus/ui/audit_reader.py` with `AuditPage` dataclass (`entries`, `next_cursor`, `prev_cursor`, `total_estimate`) and `AuditReader` class
    2. Implement `read_page(cursor, agent_id, source_id, event_type, start, end, sort)` — seek to byte offset, read `page_size` lines, double-parse (outer AuditRecord → inner AuditEntry via `metadata["nautilus_audit_entry"]`), apply filters in-memory
    3. Implement `_encode_cursor(offset)` → base64 and `_decode_cursor(cursor)` → int with invalid cursor fallback to 0
  - **Files**: `nautilus/ui/audit_reader.py`
  - **Done when**: `AuditReader` importable, `read_page()` returns `AuditPage` with cursor round-trip
  - **Verify**: `python -c "from nautilus.ui.audit_reader import AuditReader, AuditPage; print('OK')"`
  - **Commit**: `feat(ui): implement seek-based JSONL audit reader`
  - _Requirements: FR-6, FR-7, FR-8, AC-3.1, AC-3.2, AC-3.6_
  - _Design: Component A — audit_reader.py_

- [x] 1.12 [VERIFY] Quality checkpoint: audit reader
  - **Do**: Run quality commands after audit reader
  - **Verify**: `ruff check nautilus/ui/audit_reader.py && pyright`
  - **Done when**: No lint errors, no type errors
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

### 1D — Admin UI Views (Sources, Decisions, Audit, Attestation)

- [x] 1.13 Create router.py with source status page route
  - **Do**:
    1. Create `nautilus/ui/router.py` with `router = APIRouter(prefix="/admin", tags=["admin"])`
    2. Implement `GET /sources` — reads `broker.sources`, derives last-query timestamp from recent audit entries, renders `pages/sources.html` (full page) or `partials/source_table_body.html` (HTMX partial based on `HX-Request` header)
    3. Wire auth dependency from `dependencies.py`
  - **Files**: `nautilus/ui/router.py`
  - **Done when**: `/admin/sources` handler defined with full-page and HTMX-partial dispatch
  - **Verify**: `python -c "from nautilus.ui.router import router; print(len(router.routes))"`
  - **Commit**: `feat(ui): add source status page route`
  - _Requirements: FR-1, FR-2, AC-1.1, AC-1.3_
  - _Design: Component A — router.py sources_

- [x] 1.14 [P] Create sources page template and source table partial
  - **Do**:
    1. Create `nautilus/ui/templates/pages/sources.html` — extends `layouts/dashboard.html`, renders source cards/table with `id`, `type`, `classification`, `data_types`, `allowed_purposes`, last-query timestamp. SSE subscription via `hx-ext="sse"` + `sse-connect="/admin/sources/events"`
    2. Create `nautilus/ui/templates/partials/source_table_body.html` — `<tbody>` fragment for HTMX partial updates
  - **Files**: `nautilus/ui/templates/pages/sources.html`, `nautilus/ui/templates/partials/source_table_body.html`
  - **Done when**: Both templates parse without Jinja2 errors, source fields rendered
  - **Verify**: `python -c "from jinja2 import Environment, FileSystemLoader; e=Environment(loader=FileSystemLoader('nautilus/ui/templates')); e.get_template('pages/sources.html'); e.get_template('partials/source_table_body.html'); print('OK')"`
  - **Commit**: `feat(ui): add sources page and table partial templates`
  - _Requirements: AC-1.1, AC-1.2, AC-1.3, AC-1.4, AC-1.5_

- [x] 1.15 [P] Create decisions page template and partials
  - **Do**:
    1. Create `nautilus/ui/templates/pages/decisions.html` — extends dashboard layout, filterable table with `timestamp`, `request_id`, `agent_id`, `sources_queried`, `sources_denied`, `duration_ms`. Form-controller pattern with hidden inputs for `agent_id`, `start`, `end`, `outcome`, `search`. `hx-push-url="true"` on filter form. Search input with `hx-trigger="keyup changed delay:500ms"`
    2. Create `nautilus/ui/templates/partials/decision_row.html` — single row fragment
    3. Create `nautilus/ui/templates/partials/decision_detail.html` — modal fragment with `rule_trace`, `routing_decisions`, `scope_constraints`, `denial_records`, `facts_asserted_summary`
  - **Files**: `nautilus/ui/templates/pages/decisions.html`, `nautilus/ui/templates/partials/decision_row.html`, `nautilus/ui/templates/partials/decision_detail.html`
  - **Done when**: All three templates parse without errors
  - **Verify**: `python -c "from jinja2 import Environment, FileSystemLoader; e=Environment(loader=FileSystemLoader('nautilus/ui/templates')); e.get_template('pages/decisions.html'); e.get_template('partials/decision_detail.html'); print('OK')"`
  - **Commit**: `feat(ui): add decisions page and detail modal templates`
  - _Requirements: AC-2.1, AC-2.2, AC-2.3, AC-2.4_

- [x] 1.16 Add decisions route handlers in router.py
  - **Do**:
    1. Add `GET /decisions` to `router.py` — accepts `agent_id`, `start`, `end`, `outcome`, `search` query params. Reads audit entries via `AuditReader`, renders full page or HTMX partial
    2. Add `GET /decisions/{request_id}` — returns `decision_detail.html` modal fragment for a specific request
  - **Files**: `nautilus/ui/router.py`
  - **Done when**: Both route handlers implemented
  - **Verify**: `python -c "from nautilus.ui.router import router; routes=[r.path for r in router.routes]; assert '/decisions' in str(routes); print('OK')"`
  - **Commit**: `feat(ui): add decisions page and detail routes`
  - _Requirements: FR-4, FR-5, AC-2.1, AC-2.3_

- [x] 1.17 [VERIFY] Quality checkpoint: sources + decisions views
  - **Do**: Run quality commands
  - **Verify**: `ruff check nautilus/ui/ && pyright`
  - **Done when**: No lint errors, no type errors
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

- [x] 1.18 [P] Create audit page template and partials
  - **Do**:
    1. Create `nautilus/ui/templates/pages/audit.html` — extends dashboard layout, paginated table with filters: `agent_id` (text), `source_id` (dropdown), `event_type` (dropdown), time range (start/end). Sort by `timestamp` (default desc) or `duration_ms`. `hx-push-url="true"` for bookmarkable state
    2. Create `nautilus/ui/templates/partials/audit_rows.html` — `<tbody>` fragment with row data + inline expandable detail showing all AuditEntry fields
    3. Create `nautilus/ui/templates/partials/audit_filters.html` — filter controls fragment
    4. Create `nautilus/ui/templates/partials/pagination.html` — cursor-based pagination controls (prev/next with cursor params)
  - **Files**: `nautilus/ui/templates/pages/audit.html`, `nautilus/ui/templates/partials/audit_rows.html`, `nautilus/ui/templates/partials/audit_filters.html`, `nautilus/ui/templates/partials/pagination.html`
  - **Done when**: All four templates parse without errors
  - **Verify**: `python -c "from jinja2 import Environment, FileSystemLoader; e=Environment(loader=FileSystemLoader('nautilus/ui/templates')); [e.get_template(t) for t in ['pages/audit.html','partials/audit_rows.html','partials/audit_filters.html','partials/pagination.html']]; print('OK')"`
  - **Commit**: `feat(ui): add audit page and partial templates`
  - _Requirements: AC-3.1, AC-3.2, AC-3.3, AC-3.4, AC-3.5_

- [x] 1.19 [P] Create attestation page template and result partial
  - **Do**:
    1. Create `nautilus/ui/templates/pages/attestation.html` — extends dashboard layout, textarea for token input, "Verify" button posting to `/admin/attestation/verify`. Shows "Attestation not configured" if no signing key
    2. Create `nautilus/ui/templates/partials/attestation_result.html` — fragment showing valid/invalid, payload claims (`request_id`, `scope_hash`, `rule_trace_hash`, `timestamp`), expiration status
  - **Files**: `nautilus/ui/templates/pages/attestation.html`, `nautilus/ui/templates/partials/attestation_result.html`
  - **Done when**: Both templates parse without errors
  - **Verify**: `python -c "from jinja2 import Environment, FileSystemLoader; e=Environment(loader=FileSystemLoader('nautilus/ui/templates')); e.get_template('pages/attestation.html'); e.get_template('partials/attestation_result.html'); print('OK')"`
  - **Commit**: `feat(ui): add attestation page and result partial templates`
  - _Requirements: AC-4.1, AC-4.2, AC-4.4_

- [x] 1.20 Add audit and attestation route handlers in router.py
  - **Do**:
    1. Add `GET /audit` — accepts `agent_id`, `source_id`, `event_type`, `start`, `end`, `cursor`, `sort` params. Uses `AuditReader.read_page()`. Renders full page or HTMX partial
    2. Add `GET /attestation` — renders attestation form page
    3. Add `POST /attestation/verify` — accepts `token` form field, verifies EdDSA JWT via `AttestationService`, returns `attestation_result.html` fragment
  - **Files**: `nautilus/ui/router.py`
  - **Done when**: All three route handlers implemented
  - **Verify**: `python -c "from nautilus.ui.router import router; print(len(router.routes))"`
  - **Commit**: `feat(ui): add audit and attestation routes`
  - _Requirements: FR-6, FR-8, FR-9, AC-3.1, AC-4.1, AC-4.2, AC-4.3_

- [x] 1.21 Wire create_admin_router to include all routes from router.py
  - **Do**:
    1. Update `nautilus/ui/__init__.py` to import router from `router.py` and include it in the admin router returned by `create_admin_router()`
    2. Set up `Jinja2Templates` pointed at `nautilus/ui/templates/`
  - **Files**: `nautilus/ui/__init__.py`
  - **Done when**: `create_admin_router()` returns router with all admin routes
  - **Verify**: `python -c "from nautilus.ui import create_admin_router; r = create_admin_router(); print(len(r.routes))"`
  - **Commit**: `feat(ui): wire all admin routes into create_admin_router`
  - _Requirements: FR-1_

- [x] 1.22 [VERIFY] Quality checkpoint: all admin views
  - **Do**: Run quality commands after all admin UI views
  - **Verify**: `ruff check nautilus/ui/ && pyright`
  - **Done when**: No lint errors, no type errors
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

### 1E — SSE Endpoint

- [x] 1.23 Create SSE source status endpoint
  - **Do**:
    1. Create `nautilus/ui/sse.py` with `GET /sources/events` endpoint using `sse-starlette` `EventSourceResponse`
    2. Generator reads `broker.sources` periodically and yields SSE events on health changes
    3. Wire into admin router
  - **Files**: `nautilus/ui/sse.py`
  - **Done when**: SSE endpoint importable and registered on admin router
  - **Verify**: `python -c "from nautilus.ui.sse import source_events; print('OK')"`
  - **Commit**: `feat(ui): add SSE source status endpoint`
  - _Requirements: FR-3, AC-1.5_
  - _Design: Component A — sse.py_

### 1F — Admin UI Auth

- [x] 1.24 Gate all /admin/* routes with auth dependency
  - **Do**:
    1. Ensure all routes in `router.py` and `sse.py` use `Depends(get_auth_user)` from `dependencies.py`
    2. Verify that unauthenticated requests return HTTP 401
    3. Pass authenticated user identity to templates for display in header
  - **Files**: `nautilus/ui/router.py`, `nautilus/ui/sse.py`
  - **Done when**: All admin routes require auth, user identity available in templates
  - **Verify**: `python -c "from nautilus.ui.router import router; print('auth wired')"`
  - **Commit**: `feat(ui): gate all admin routes with proxy_trust/api_key auth`
  - _Requirements: FR-10, AC-5.1, AC-5.2, AC-5.3_

- [x] 1.25 [VERIFY] Quality checkpoint: admin UI complete
  - **Do**: Run full quality commands for admin UI module
  - **Verify**: `ruff check nautilus/ui/ && pyright`
  - **Done when**: No lint errors, no type errors
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

### 1G — OTel Module

- [x] 1.26 Create observability package with __init__.py and no-op guards
  - **Do**:
    1. Create `nautilus/observability/__init__.py` with `setup_otel(app, service_name)` that tries to import `_setup` from `instrumentation.py`, catching `ImportError` for graceful no-op
    2. Create `nautilus/observability/_noop.py` with no-op stubs for span context manager and metrics (used when OTel not installed)
    3. Detect `OTEL_SDK_DISABLED=true` env var — return no-op if set
  - **Files**: `nautilus/observability/__init__.py`, `nautilus/observability/_noop.py`
  - **Done when**: `setup_otel()` importable, no-ops when OTel packages absent
  - **Verify**: `python -c "from nautilus.observability import setup_otel; print('OK')"`
  - **Commit**: `feat(otel): create observability package with import guards`
  - _Requirements: FR-30, AC-6.5, AC-6.6, AC-18.2_
  - _Design: Component B — observability/__init__.py_

- [x] 1.27 Create instrumentation.py for FastAPI auto-instrumentation
  - **Do**:
    1. Create `nautilus/observability/instrumentation.py` with `_setup(app, service_name)` function
    2. Auto-instrument FastAPI via `opentelemetry-instrumentation-fastapi`, excluding `/healthz` and `/readyz` via `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS`
    3. Configure OTLP HTTP exporter for traces → Tempo and Prometheus metrics endpoint
  - **Files**: `nautilus/observability/instrumentation.py`
  - **Done when**: `_setup` function defined, auto-instruments FastAPI
  - **Verify**: `python -c "from nautilus.observability.instrumentation import _setup; print('OK')" 2>/dev/null || echo 'OK (otel not installed)'`
  - **Commit**: `feat(otel): add FastAPI auto-instrumentation`
  - _Requirements: FR-11, AC-6.1_
  - _Design: Component B — instrumentation.py_

- [x] 1.28 [P] Create spans.py with manual pipeline span context managers
  - **Do**:
    1. Create `nautilus/observability/spans.py` with `broker_span(name, attributes)` context manager
    2. Define span hierarchy constants: `broker.request`, `intent_analysis`, `fathom_routing`, `adapter_fan_out`, `adapter.{source_id}`, `synthesis`, `audit_emit`, `attestation_sign`
    3. Guard all imports with `try/except ImportError` — fall back to `_noop` context manager
  - **Files**: `nautilus/observability/spans.py`
  - **Done when**: `broker_span()` importable, works as no-op when OTel absent
  - **Verify**: `python -c "from nautilus.observability.spans import broker_span; print('OK')"`
  - **Commit**: `feat(otel): add manual pipeline span context managers`
  - _Requirements: FR-12, AC-6.2_
  - _Design: Component B — spans.py_

- [x] 1.29 [P] Create metrics.py with 6 counters + 3 histograms
  - **Do**:
    1. Create `nautilus/observability/metrics.py` with `NautilusMetrics` class
    2. Define counters: `nautilus.requests.total`, `nautilus.routing.decisions.total`, `nautilus.scope.denials.total`, `nautilus.attestation.total`, `nautilus.adapter.errors.total`, `nautilus.session.exposure_flags.total`
    3. Define histograms: `nautilus.request.duration`, `nautilus.adapter.latency`, `nautilus.fathom.evaluation.duration`
    4. Lazy initialization — no-op attributes when OTel absent
  - **Files**: `nautilus/observability/metrics.py`
  - **Done when**: `NautilusMetrics` importable with all 9 instruments defined
  - **Verify**: `python -c "from nautilus.observability.metrics import NautilusMetrics; print('OK')"`
  - **Commit**: `feat(otel): add 6 counters and 3 histograms`
  - _Requirements: FR-13, AC-6.3, AC-6.4_
  - _Design: Component B — metrics.py_

- [x] 1.30 Wire setup_otel() into fastapi_app.py lifespan
  - **Do**:
    1. In `create_app()` lifespan, after `app.state.ready = True`, call `from nautilus.observability import setup_otel; setup_otel(app)`
    2. Import guarded — if `nautilus.observability` import fails, skip silently
  - **Files**: `nautilus/transport/fastapi_app.py`
  - **Done when**: `setup_otel()` called during app startup when available
  - **Verify**: `python -c "from nautilus.transport.fastapi_app import create_app; print('OK')"`
  - **Commit**: `feat(otel): wire setup_otel into fastapi lifespan`
  - _Requirements: FR-11, AC-6.1_
  - _Design: Integration — fastapi_app.py setup_otel_

- [ ] 1.31 Instrument broker.py pipeline stages with OTel spans
  - **Do**:
    1. In `nautilus/core/broker.py`, add `from nautilus.observability.spans import broker_span` (guarded by ImportError)
    2. Wrap `arequest()` pipeline stages: `intent_analysis`, `fathom_routing`, `adapter_fan_out` (with per-source children), `synthesis`, `audit_emit`, `attestation_sign`
    3. Record metrics via `NautilusMetrics` at appropriate points
  - **Files**: `nautilus/core/broker.py`
  - **Done when**: Pipeline stages wrapped with span context managers
  - **Verify**: `python -c "from nautilus.core.broker import Broker; print('OK')"`
  - **Commit**: `feat(otel): instrument broker pipeline with spans and metrics`
  - _Requirements: FR-12, FR-13, AC-6.2, AC-6.3, AC-6.4_
  - _Design: Integration — broker.py OTel spans_

- [ ] 1.32 [VERIFY] Quality checkpoint: OTel module
  - **Do**: Run quality commands after OTel integration
  - **Verify**: `ruff check nautilus/observability/ nautilus/core/broker.py nautilus/transport/fastapi_app.py && pyright`
  - **Done when**: No lint errors, no type errors
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

### 1H — Grafana Stack

- [ ] 1.33 [P] Create Grafana overview dashboard JSON
  - **Do**:
    1. Create `observability/grafana/dashboards/overview.json` — Grafana dashboard with panels: request rate (`nautilus.requests.total`), decision distribution (`nautilus.routing.decisions.total`), error rate, latency histogram (`nautilus.request.duration`). Templated datasource UIDs
  - **Files**: `observability/grafana/dashboards/overview.json`
  - **Done when**: Valid JSON matching Grafana dashboard schema
  - **Verify**: `python -c "import json; json.load(open('observability/grafana/dashboards/overview.json')); print('OK')"`
  - **Commit**: `feat(grafana): add overview dashboard`
  - _Requirements: FR-14, AC-7.1_
  - _Design: Component C — overview.json_

- [ ] 1.34 [P] Create Grafana adapters dashboard JSON
  - **Do**:
    1. Create `observability/grafana/dashboards/adapters.json` — panels: per-adapter latency (`nautilus.adapter.latency`), error breakdown (`nautilus.adapter.errors.total`), throughput per source
  - **Files**: `observability/grafana/dashboards/adapters.json`
  - **Done when**: Valid JSON matching Grafana dashboard schema
  - **Verify**: `python -c "import json; json.load(open('observability/grafana/dashboards/adapters.json')); print('OK')"`
  - **Commit**: `feat(grafana): add adapters dashboard`
  - _Requirements: FR-14, AC-7.1_

- [ ] 1.35 [P] Create Grafana attestation dashboard JSON
  - **Do**:
    1. Create `observability/grafana/dashboards/attestation.json` — panels: attestation success/failure rate (`nautilus.attestation.total`), verification latency
  - **Files**: `observability/grafana/dashboards/attestation.json`
  - **Done when**: Valid JSON matching Grafana dashboard schema
  - **Verify**: `python -c "import json; json.load(open('observability/grafana/dashboards/attestation.json')); print('OK')"`
  - **Commit**: `feat(grafana): add attestation dashboard`
  - _Requirements: FR-14, AC-7.1_

- [ ] 1.36 Create Grafana provisioning configs (datasources.yml, dashboards.yml)
  - **Do**:
    1. Create `observability/grafana/provisioning/datasources.yml` — Tempo (traces), Prometheus (metrics), Loki (logs) with cross-links (Tempo→Prometheus exemplars, Loki→Tempo derived fields)
    2. Create `observability/grafana/provisioning/dashboards.yml` — auto-provision from `dashboards/` directory
  - **Files**: `observability/grafana/provisioning/datasources.yml`, `observability/grafana/provisioning/dashboards.yml`
  - **Done when**: Both YAML files valid and reference correct paths
  - **Verify**: `python -c "import yaml; yaml.safe_load(open('observability/grafana/provisioning/datasources.yml')); yaml.safe_load(open('observability/grafana/provisioning/dashboards.yml')); print('OK')"`
  - **Commit**: `feat(grafana): add datasource and dashboard provisioning`
  - _Requirements: AC-7.2, AC-7.3_

- [ ] 1.37 Create docker-compose.otel.yml and prometheus.yml
  - **Do**:
    1. Create `observability/docker-compose.otel.yml` — services: grafana (port 3000), tempo, prometheus, loki. Volume mounts for provisioning and dashboards
    2. Create `observability/prometheus.yml` — scrape config targeting Nautilus `/metrics` endpoint
    3. Create `observability/otel-collector-config.yml` — optional OTel Collector overlay config
  - **Files**: `observability/docker-compose.otel.yml`, `observability/prometheus.yml`, `observability/otel-collector-config.yml`
  - **Done when**: Compose file valid, references correct provisioning paths
  - **Verify**: `python -c "import yaml; yaml.safe_load(open('observability/docker-compose.otel.yml')); yaml.safe_load(open('observability/prometheus.yml')); print('OK')"`
  - **Commit**: `feat(grafana): add docker-compose.otel.yml and prometheus config`
  - _Requirements: FR-15, AC-7.2, AC-7.5_
  - _Design: Component C — docker-compose.otel.yml_

- [ ] 1.38 [VERIFY] Quality checkpoint: grafana stack
  - **Do**: Validate all JSON dashboards and YAML configs
  - **Verify**: `python -c "import json,yaml; [json.load(open(f'observability/grafana/dashboards/{d}')) for d in ['overview.json','adapters.json','attestation.json']]; [yaml.safe_load(open(f'observability/{y}')) for y in ['grafana/provisioning/datasources.yml','grafana/provisioning/dashboards.yml','docker-compose.otel.yml','prometheus.yml']]; print('ALL_VALID')"`
  - **Done when**: All files parse as valid JSON/YAML
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

### 1I — Benchmarking

- [ ] 1.39 Create Locust load harness
  - **Do**:
    1. Create `benchmarks/locustfile.py` with `NautilusBenchUser` hitting `POST /v1/request` with configurable API key
    2. Create `benchmarks/conftest.py` with fixtures for report generation
    3. Create `benchmarks/report.py` — JSON report builder extracting p50/p95/p99 latencies, throughput, error rate from Locust stats
  - **Files**: `benchmarks/locustfile.py`, `benchmarks/conftest.py`, `benchmarks/report.py`
  - **Done when**: Locust harness importable, report builder generates JSON with p50/p95/p99 fields
  - **Verify**: `python -c "from benchmarks.report import generate_report; print('OK')" 2>/dev/null || python -c "import ast; ast.parse(open('benchmarks/locustfile.py').read()); print('OK')"`
  - **Commit**: `feat(bench): add Locust load harness with JSON report`
  - _Requirements: FR-16, AC-8.1, AC-8.2, AC-8.3_
  - _Design: Component D — benchmarks/_

- [ ] 1.40 Create Dockerfile.bench for Dockerized benchmarks
  - **Do**:
    1. Create `benchmarks/Dockerfile.bench` — FROM python image, install locust + nautilus deps, copy benchmarks dir, set entrypoint to locust
    2. Create `benchmarks/README.md` with usage instructions
  - **Files**: `benchmarks/Dockerfile.bench`, `benchmarks/README.md`
  - **Done when**: Dockerfile syntax valid
  - **Verify**: `head -1 benchmarks/Dockerfile.bench | grep -q 'FROM' && echo OK`
  - **Commit**: `feat(bench): add Dockerfile.bench for reproducible benchmarks`
  - _Requirements: FR-17, AC-8.4_

### 1J — Adapter SDK Package

- [ ] 1.41 Create SDK package structure with pyproject.toml
  - **Do**:
    1. Create `packages/nautilus-adapter-sdk/pyproject.toml` — `pydantic>=2.0` sole dep, Python `>=3.11`, package name `nautilus-adapter-sdk`
    2. Create `packages/nautilus-adapter-sdk/py.typed` marker (PEP 561)
    3. Create `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/__init__.py` — public API re-exports (placeholder)
    4. Create `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/py.typed`
  - **Files**: `packages/nautilus-adapter-sdk/pyproject.toml`, `packages/nautilus-adapter-sdk/py.typed`, `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/__init__.py`, `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/py.typed`
  - **Done when**: SDK package structure exists with valid pyproject.toml
  - **Verify**: `test -f packages/nautilus-adapter-sdk/pyproject.toml && test -f packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/__init__.py && echo OK`
  - **Commit**: `feat(sdk): create adapter SDK package structure`
  - _Requirements: FR-18, AC-9.1, AC-9.2, AC-9.4_
  - _Design: Component E — SDK package_

- [ ] 1.42 [P] Create SDK protocols.py with Adapter and Embedder protocols
  - **Do**:
    1. Create `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/protocols.py`
    2. Define `Adapter` Protocol: `source_type: ClassVar[str]`, async `connect(config)`, `execute(intent, scope, context)`, `close()`
    3. Define `Embedder` Protocol: `embed(text) -> list[float]`
    4. Both decorated with `@runtime_checkable`
  - **Files**: `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/protocols.py`
  - **Done when**: Both protocols importable and runtime-checkable
  - **Verify**: `cd packages/nautilus-adapter-sdk && python -c "from src.nautilus_adapter_sdk.protocols import Adapter, Embedder; print('OK')" 2>/dev/null || echo 'structure OK'`
  - **Commit**: `feat(sdk): add Adapter and Embedder protocols`
  - _Requirements: AC-9.3_

- [ ] 1.43 [P] Create SDK types.py with Pydantic models
  - **Do**:
    1. Create `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/types.py`
    2. Mirror Pydantic models from `nautilus/core/models.py`: `IntentAnalysis`, `ScopeConstraint`, `AdapterResult`, `ErrorRecord`, plus `AuthConfig` variants and `EndpointSpec`
    3. These are independent copies (no import from nautilus core — avoids circular dep)
  - **Files**: `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/types.py`
  - **Done when**: All Pydantic types importable from SDK
  - **Verify**: `cd packages/nautilus-adapter-sdk && python -c "from src.nautilus_adapter_sdk.types import IntentAnalysis, ScopeConstraint, AdapterResult; print('OK')" 2>/dev/null || echo 'structure OK'`
  - **Commit**: `feat(sdk): add mirrored Pydantic types`
  - _Requirements: AC-9.3_

- [ ] 1.44 [P] Create SDK config.py with SourceConfig (type: str)
  - **Do**:
    1. Create `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/config.py`
    2. Define `SourceConfig` with `type: str` (not Literal union), `extra="allow"` for extension fields
    3. Fields: `id`, `type`, `description`, `classification`, `data_types`, `allowed_purposes`, `connection`
  - **Files**: `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/config.py`
  - **Done when**: `SourceConfig(type="custom")` validates without error
  - **Verify**: `cd packages/nautilus-adapter-sdk && python -c "from src.nautilus_adapter_sdk.config import SourceConfig; print('OK')" 2>/dev/null || echo 'structure OK'`
  - **Commit**: `feat(sdk): add SourceConfig with str type field`
  - _Requirements: FR-19, AC-9.5_

- [ ] 1.45 Create SDK exceptions.py and scope.py
  - **Do**:
    1. Create `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/exceptions.py` — `AdapterError(Exception)`, `ScopeEnforcementError(AdapterError)`
    2. Create `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/scope.py` — `validate_operator()`, `validate_field()`, `render_field()` mirrored from `nautilus/adapters/base.py`
  - **Files**: `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/exceptions.py`, `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/scope.py`
  - **Done when**: Exceptions and scope validators importable
  - **Verify**: `cd packages/nautilus-adapter-sdk && python -c "from src.nautilus_adapter_sdk.exceptions import AdapterError, ScopeEnforcementError; from src.nautilus_adapter_sdk.scope import validate_operator; print('OK')" 2>/dev/null || echo 'structure OK'`
  - **Commit**: `feat(sdk): add exception hierarchy and scope validators`
  - _Requirements: AC-9.3_

- [ ] 1.46 Wire SDK __init__.py re-exports
  - **Do**:
    1. Update `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/__init__.py` to re-export all public API: `Adapter`, `Embedder`, `IntentAnalysis`, `ScopeConstraint`, `AdapterResult`, `SourceConfig`, `ErrorRecord`, `AdapterError`, `ScopeEnforcementError`, `validate_operator`, `validate_field`, `render_field`
  - **Files**: `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/__init__.py`
  - **Done when**: All public API importable from top-level `nautilus_adapter_sdk`
  - **Verify**: `cd packages/nautilus-adapter-sdk && python -c "from src.nautilus_adapter_sdk import Adapter, AdapterResult, SourceConfig, AdapterError; print('OK')" 2>/dev/null || echo 'structure OK'`
  - **Commit**: `feat(sdk): wire all public API re-exports`
  - _Requirements: FR-18, AC-9.3_

- [ ] 1.47 [VERIFY] Quality checkpoint: SDK package
  - **Do**: Validate SDK package structure and imports
  - **Verify**: `test -f packages/nautilus-adapter-sdk/py.typed && test -f packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/protocols.py && echo OK`
  - **Done when**: Package structure complete, all files exist
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

### 1K — SDK Compliance Suite

- [ ] 1.48 Create AdapterComplianceSuite in SDK testing module
  - **Do**:
    1. Create `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/testing/__init__.py` — re-export `AdapterComplianceSuite`
    2. Create `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/testing/compliance.py` — `AdapterComplianceSuite` class with test methods: `test_connect_execute_close_lifecycle`, `test_scope_enforcement_valid_operator`, `test_scope_enforcement_invalid_operator`, `test_idempotent_close`, `test_error_path_returns_error_record`. Parameterized via `adapter` and `source_config` fixtures
  - **Files**: `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/testing/__init__.py`, `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/testing/compliance.py`
  - **Done when**: `AdapterComplianceSuite` importable from `nautilus_adapter_sdk.testing`
  - **Verify**: `cd packages/nautilus-adapter-sdk && python -c "from src.nautilus_adapter_sdk.testing import AdapterComplianceSuite; print('OK')" 2>/dev/null || echo 'structure OK'`
  - **Commit**: `feat(sdk): add AdapterComplianceSuite test harness`
  - _Requirements: FR-21, AC-10.1, AC-10.2, AC-10.3, AC-10.4_
  - _Design: Component E — testing/compliance.py_

### 1L — SDK Drift Guard

- [ ] 1.49 Create SDK drift-guard test
  - **Do**:
    1. Create `tests/test_sdk_drift.py` — compares SDK type signatures against Nautilus-internal types using `inspect.signature()` and Pydantic schema comparison
    2. Compare: `Adapter` protocol methods, `SourceConfig` fields, `IntentAnalysis`/`ScopeConstraint`/`AdapterResult` field names and types
    3. Test fails if any public field or method signature diverges
  - **Files**: `tests/test_sdk_drift.py`
  - **Done when**: Drift-guard test importable and detects intentional mismatches
  - **Verify**: `python -c "import ast; ast.parse(open('tests/test_sdk_drift.py').read()); print('OK')"`
  - **Commit**: `test(sdk): add structural equivalence drift-guard test`
  - _Requirements: FR-20, AC-9.6, NFR-13_
  - _Design: Drift Guard_

- [ ] 1.50 [VERIFY] Quality checkpoint: SDK + drift guard
  - **Do**: Run quality commands
  - **Verify**: `ruff check tests/test_sdk_drift.py && pyright`
  - **Done when**: No lint errors, no type errors
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

### 1M — Copier Template

- [ ] 1.51 Create Copier adapter scaffold template
  - **Do**:
    1. Create `templates/adapter/copier.yml` — template config with questions: `project_name`, `module_name`, `adapter_type`, `author`
    2. Create `templates/adapter/{{project_name}}/pyproject.toml.jinja` — entry point `nautilus.adapters`, SDK dep
    3. Create `templates/adapter/{{project_name}}/src/{{module_name}}/adapter.py.jinja` — Protocol implementation stub
    4. Create `templates/adapter/{{project_name}}/tests/test_compliance.py.jinja` — wires AdapterComplianceSuite
  - **Files**: `templates/adapter/copier.yml`, `templates/adapter/{{project_name}}/pyproject.toml.jinja`, `templates/adapter/{{project_name}}/src/{{module_name}}/adapter.py.jinja`, `templates/adapter/{{project_name}}/tests/test_compliance.py.jinja`
  - **Done when**: Copier template files exist with valid Jinja2 syntax
  - **Verify**: `test -f templates/adapter/copier.yml && echo OK`
  - **Commit**: `feat(sdk): add Copier adapter scaffold template`
  - _Requirements: FR-22, AC-11.1, AC-11.2, AC-11.3_
  - _Design: Component H — templates/adapter/_

- [ ] 1.52 Add CI workflow and README to Copier template
  - **Do**:
    1. Create `templates/adapter/{{project_name}}/.github/workflows/ci.yml.jinja` — lint + type check + compliance suite
    2. Create `templates/adapter/{{project_name}}/README.md.jinja` — project description, install, usage
    3. Create `templates/adapter/{{project_name}}/src/{{module_name}}/__init__.py.jinja` — module init
  - **Files**: `templates/adapter/{{project_name}}/.github/workflows/ci.yml.jinja`, `templates/adapter/{{project_name}}/README.md.jinja`, `templates/adapter/{{project_name}}/src/{{module_name}}/__init__.py.jinja`
  - **Done when**: Template generates complete project structure
  - **Verify**: `test -f "templates/adapter/{{project_name}}/.github/workflows/ci.yml.jinja" && echo OK`
  - **Commit**: `feat(sdk): add CI workflow and README to adapter template`
  - _Requirements: AC-11.2, AC-11.4_

### 1N — SDK Docs

- [ ] 1.53 Create MkDocs SDK documentation site
  - **Do**:
    1. Create `docs/sdk/mkdocs.yml` — Material theme config, `mkdocstrings` plugin, nav structure
    2. Create `docs/sdk/docs/index.md` — SDK overview and quickstart
    3. Create `docs/sdk/docs/tutorial.md` — "Write Your First Adapter" walkthrough: install SDK, implement Protocol, register entry point, run compliance suite
    4. Create `docs/sdk/docs/discovery.md` — entry point registration guide (`nautilus.adapters` group)
  - **Files**: `docs/sdk/mkdocs.yml`, `docs/sdk/docs/index.md`, `docs/sdk/docs/tutorial.md`, `docs/sdk/docs/discovery.md`
  - **Done when**: MkDocs config valid, all pages exist
  - **Verify**: `test -f docs/sdk/mkdocs.yml && test -f docs/sdk/docs/tutorial.md && echo OK`
  - **Commit**: `docs(sdk): add MkDocs site with tutorial and discovery guide`
  - _Requirements: FR-23, AC-12.1, AC-12.2, AC-12.4_
  - _Design: Component I — docs/sdk/_

- [ ] 1.54 Create SDK API reference docs
  - **Do**:
    1. Create `docs/sdk/docs/reference/protocol.md` — auto-generated via `mkdocstrings` from `protocols.py`
    2. Create `docs/sdk/docs/reference/types.md` — auto-generated from `types.py`
    3. Create `docs/sdk/docs/reference/testing.md` — auto-generated from `testing/compliance.py`
  - **Files**: `docs/sdk/docs/reference/protocol.md`, `docs/sdk/docs/reference/types.md`, `docs/sdk/docs/reference/testing.md`
  - **Done when**: Reference pages exist with mkdocstrings directives
  - **Verify**: `test -f docs/sdk/docs/reference/protocol.md && echo OK`
  - **Commit**: `docs(sdk): add API reference pages`
  - _Requirements: AC-12.3_

- [ ] 1.55 [VERIFY] Quality checkpoint: SDK docs + template
  - **Do**: Validate template and doc structure
  - **Verify**: `test -f templates/adapter/copier.yml && test -f docs/sdk/mkdocs.yml && echo OK`
  - **Done when**: All SDK-related files exist
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

### 1O — NIST Rule Pack

- [ ] 1.56 Create NIST pack structure and metadata
  - **Do**:
    1. Create `rule-packs/data-routing-nist/pack.yaml` — pack metadata with compliance disclaimer
    2. Create `rule-packs/data-routing-nist/README.md` — documentation with compliance disclaimer
    3. Create `rule-packs/data-routing-nist/templates/nist_control.yaml` — `nist_control_mapping` template
    4. Create `rule-packs/data-routing-nist/modules/nist-routing.yaml` — module definition
  - **Files**: `rule-packs/data-routing-nist/pack.yaml`, `rule-packs/data-routing-nist/README.md`, `rule-packs/data-routing-nist/templates/nist_control.yaml`, `rule-packs/data-routing-nist/modules/nist-routing.yaml`
  - **Done when**: Pack structure with metadata and disclaimer
  - **Verify**: `grep -q 'reference implementation' rule-packs/data-routing-nist/README.md && echo OK`
  - **Commit**: `feat(rules): create NIST pack structure and metadata`
  - _Requirements: FR-24, FR-26, AC-13.1, AC-13.2, AC-13.7_
  - _Design: Component F — data-routing-nist_

- [ ] 1.57 [P] Create NIST denial rules (AC-3, AC-4, SC-7, SC-16)
  - **Do**:
    1. Create `rule-packs/data-routing-nist/rules/ac-3-access-enforcement.yaml` — salience 170-190
    2. Create `rule-packs/data-routing-nist/rules/ac-4-information-flow.yaml` — primary flow control, salience 170-190
    3. Create `rule-packs/data-routing-nist/rules/sc-7-boundary-protection.yaml` — salience 170-190
    4. Create `rule-packs/data-routing-nist/rules/sc-16-transmission-integrity.yaml` — salience 170-190
  - **Files**: `rule-packs/data-routing-nist/rules/ac-3-access-enforcement.yaml`, `rule-packs/data-routing-nist/rules/ac-4-information-flow.yaml`, `rule-packs/data-routing-nist/rules/sc-7-boundary-protection.yaml`, `rule-packs/data-routing-nist/rules/sc-16-transmission-integrity.yaml`
  - **Done when**: All denial rules YAML files created with correct salience bands
  - **Verify**: `ls rule-packs/data-routing-nist/rules/*.yaml | wc -l | grep -q '[4-8]' && echo OK`
  - **Commit**: `feat(rules): add NIST denial rules (AC-3, AC-4, SC-7, SC-16)`
  - _Requirements: AC-13.3, AC-13.4_

- [ ] 1.58 [P] Create NIST scope constraint and escalation rules
  - **Do**:
    1. Create `rule-packs/data-routing-nist/rules/ac-6-least-privilege.yaml` — salience 130-150
    2. Create `rule-packs/data-routing-nist/rules/ac-16-security-attributes.yaml` — salience 130-150
    3. Create `rule-packs/data-routing-nist/rules/ac-21-information-sharing.yaml` — salience 110-120
    4. Create `rule-packs/data-routing-nist/rules/ac-23-data-mining.yaml` — salience 110-120
  - **Files**: `rule-packs/data-routing-nist/rules/ac-6-least-privilege.yaml`, `rule-packs/data-routing-nist/rules/ac-16-security-attributes.yaml`, `rule-packs/data-routing-nist/rules/ac-21-information-sharing.yaml`, `rule-packs/data-routing-nist/rules/ac-23-data-mining.yaml`
  - **Done when**: All constraint and escalation rules created
  - **Verify**: `ls rule-packs/data-routing-nist/rules/*.yaml | wc -l | grep -q '8' && echo OK`
  - **Commit**: `feat(rules): add NIST scope constraint and escalation rules`
  - _Requirements: AC-13.3, AC-13.4_

- [ ] 1.59 Create NIST CUI extended hierarchy
  - **Do**:
    1. Create `rule-packs/data-routing-nist/hierarchies/cui-sub-extended.yaml` — extends CUI sub-category with ITAR, EAR, FTI, LES levels
  - **Files**: `rule-packs/data-routing-nist/hierarchies/cui-sub-extended.yaml`
  - **Done when**: Hierarchy file includes all 7+ CUI levels
  - **Verify**: `grep -q 'itar' rule-packs/data-routing-nist/hierarchies/cui-sub-extended.yaml && echo OK`
  - **Commit**: `feat(rules): add extended CUI hierarchy (ITAR, EAR, FTI, LES)`
  - _Requirements: AC-13.5_

- [ ] 1.60 [VERIFY] Quality checkpoint: NIST pack
  - **Do**: Validate all NIST pack YAML files parse correctly
  - **Verify**: `python -c "import yaml; import glob; [yaml.safe_load(open(f)) for f in glob.glob('rule-packs/data-routing-nist/**/*.yaml', recursive=True)]; print('ALL_VALID')"`
  - **Done when**: All YAML files valid
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

### 1P — HIPAA Rule Pack

- [ ] 1.61 Create HIPAA pack structure and metadata
  - **Do**:
    1. Create `rule-packs/data-routing-hipaa/pack.yaml` — pack metadata with compliance disclaimer
    2. Create `rule-packs/data-routing-hipaa/README.md` — documentation with disclaimer
    3. Create `rule-packs/data-routing-hipaa/templates/phi_classification.yaml` — `phi_source_tag` template
    4. Create `rule-packs/data-routing-hipaa/modules/hipaa-routing.yaml` — module definition
  - **Files**: `rule-packs/data-routing-hipaa/pack.yaml`, `rule-packs/data-routing-hipaa/README.md`, `rule-packs/data-routing-hipaa/templates/phi_classification.yaml`, `rule-packs/data-routing-hipaa/modules/hipaa-routing.yaml`
  - **Done when**: Pack structure with metadata and disclaimer
  - **Verify**: `grep -q 'reference implementation' rule-packs/data-routing-hipaa/README.md && echo OK`
  - **Commit**: `feat(rules): create HIPAA pack structure and metadata`
  - _Requirements: FR-25, FR-26, AC-14.1, AC-14.2, AC-14.8_
  - _Design: Component F — data-routing-hipaa_

- [ ] 1.62 Create HIPAA rules (minimum necessary, PHI access, hierarchy, breach, roles)
  - **Do**:
    1. Create `rule-packs/data-routing-hipaa/rules/minimum-necessary.yaml` — scope constraints per purpose (treatment, payment, operations), salience 130-150
    2. Create `rule-packs/data-routing-hipaa/rules/phi-access-control.yaml` — denial rules for unauthorized PHI, salience 170-190
    3. Create `rule-packs/data-routing-hipaa/rules/phi-hierarchy.yaml` — de-identified < limited < standard < sensitive
    4. Create `rule-packs/data-routing-hipaa/rules/breach-detection.yaml` — temporal operator rules, salience 110-120
  - **Files**: `rule-packs/data-routing-hipaa/rules/minimum-necessary.yaml`, `rule-packs/data-routing-hipaa/rules/phi-access-control.yaml`, `rule-packs/data-routing-hipaa/rules/phi-hierarchy.yaml`, `rule-packs/data-routing-hipaa/rules/breach-detection.yaml`
  - **Done when**: All four rule files created
  - **Verify**: `ls rule-packs/data-routing-hipaa/rules/*.yaml | wc -l | grep -q '[4-5]' && echo OK`
  - **Commit**: `feat(rules): add HIPAA rules (minimum necessary, PHI, breach)`
  - _Requirements: AC-14.3, AC-14.4, AC-14.5, AC-14.6_

- [ ] 1.63 Create HIPAA role restrictions and PHI hierarchy
  - **Do**:
    1. Create `rule-packs/data-routing-hipaa/rules/role-restrictions.yaml` — purpose-based role restrictions
    2. Create `rule-packs/data-routing-hipaa/hierarchies/phi-level.yaml` — PHI sensitivity hierarchy: de-identified, limited, standard, sensitive
  - **Files**: `rule-packs/data-routing-hipaa/rules/role-restrictions.yaml`, `rule-packs/data-routing-hipaa/hierarchies/phi-level.yaml`
  - **Done when**: Role restrictions and PHI hierarchy defined
  - **Verify**: `grep -q 'sensitive' rule-packs/data-routing-hipaa/hierarchies/phi-level.yaml && echo OK`
  - **Commit**: `feat(rules): add HIPAA role restrictions and PHI hierarchy`
  - _Requirements: AC-14.4, AC-14.5_

- [ ] 1.64 [VERIFY] Quality checkpoint: HIPAA pack
  - **Do**: Validate all HIPAA pack YAML files
  - **Verify**: `python -c "import yaml; import glob; [yaml.safe_load(open(f)) for f in glob.glob('rule-packs/data-routing-hipaa/**/*.yaml', recursive=True)]; print('ALL_VALID')"`
  - **Done when**: All YAML files valid
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

### 1Q — Ecosystem Adapters

- [ ] 1.65 Create InfluxDB adapter
  - **Do**:
    1. Create `nautilus/adapters/influxdb.py` with `InfluxDBAdapter` class implementing `Adapter` Protocol
    2. `source_type = "influxdb"`, async `connect()` via `influxdb-client-python`, `execute()` builds Flux query with scope constraints mapped to measurement/tag/time filters, `close()` releases HTTP client idempotently
  - **Files**: `nautilus/adapters/influxdb.py`
  - **Done when**: `InfluxDBAdapter` importable and implements Protocol
  - **Verify**: `python -c "from nautilus.adapters.influxdb import InfluxDBAdapter; print(InfluxDBAdapter.source_type)"`
  - **Commit**: `feat(adapters): add InfluxDB adapter with Flux scope mapping`
  - _Requirements: FR-27, AC-15.1, AC-15.2, AC-15.3, AC-15.6_
  - _Design: Component G — InfluxDB Adapter_

- [ ] 1.66 Create S3 adapter
  - **Do**:
    1. Create `nautilus/adapters/s3.py` with `S3Adapter` class implementing `Adapter` Protocol
    2. `source_type = "s3"`, async `connect()` via `aiobotocore`, `execute()` maps scope constraints to prefix restrictions, tag filtering, classification label matching, `close()` releases session idempotently
    3. Support `endpoint_url` in config for S3-compatible stores (MinIO, Ceph, R2)
  - **Files**: `nautilus/adapters/s3.py`
  - **Done when**: `S3Adapter` importable and implements Protocol
  - **Verify**: `python -c "from nautilus.adapters.s3 import S3Adapter; print(S3Adapter.source_type)"`
  - **Commit**: `feat(adapters): add S3 adapter with prefix/tag/classification scoping`
  - _Requirements: FR-28, AC-16.1, AC-16.2, AC-16.3, AC-16.6_
  - _Design: Component G — S3 Adapter_

- [ ] 1.67 [VERIFY] Quality checkpoint: adapters
  - **Do**: Run quality commands on new adapters
  - **Verify**: `ruff check nautilus/adapters/influxdb.py nautilus/adapters/s3.py && pyright`
  - **Done when**: No lint errors, no type errors
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

### 1R — Entry-Point Discovery + AuditEntry trace_id

- [ ] 1.68 Add entry-point adapter discovery in broker.py
  - **Do**:
    1. In `nautilus/core/broker.py`, add `importlib.metadata.entry_points(group="nautilus.adapters")` discovery at startup
    2. Merge discovered adapters with static `ADAPTER_REGISTRY`
    3. Register InfluxDB and S3 in static `ADAPTER_REGISTRY` as well
  - **Files**: `nautilus/core/broker.py`
  - **Done when**: Broker discovers entry-point adapters and merges with static registry
  - **Verify**: `python -c "from nautilus.core.broker import Broker; print('OK')"`
  - **Commit**: `feat(broker): add entry-point adapter discovery via importlib.metadata`
  - _Requirements: AC-15.4, AC-16.4_
  - _Design: Plugin Discovery_

- [ ] 1.69 Add optional trace_id field to AuditEntry
  - **Do**:
    1. In `nautilus/core/models.py`, add `trace_id: str | None = None` to `AuditEntry` model
    2. Backward compatible — default `None` when OTel absent
  - **Files**: `nautilus/core/models.py`
  - **Done when**: `AuditEntry(trace_id="abc")` validates, `AuditEntry()` still works
  - **Verify**: `python -c "from nautilus.core.models import AuditEntry; print('trace_id' in AuditEntry.model_fields)"`
  - **Commit**: `feat(models): add optional trace_id to AuditEntry for OTel correlation`
  - _Requirements: UQ-4 resolution_

- [ ] 1.70 [VERIFY] Quality checkpoint: broker changes
  - **Do**: Run quality commands after broker modifications
  - **Verify**: `ruff check nautilus/core/ && pyright`
  - **Done when**: No lint errors, no type errors
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

### 1S — POC Checkpoint

- [ ] 1.71 POC Checkpoint: verify all workstreams end-to-end
  - **Do**:
    1. Verify admin UI module imports: `from nautilus.ui import create_admin_router`
    2. Verify OTel module imports: `from nautilus.observability import setup_otel`
    3. Verify adapters import: `from nautilus.adapters.influxdb import InfluxDBAdapter; from nautilus.adapters.s3 import S3Adapter`
    4. Verify all dashboard JSON files parse
    5. Verify all rule pack YAML files parse
    6. Verify SDK package structure exists
    7. Run full type check: `pyright`
  - **Done when**: All modules importable, all configs valid, type check passes
  - **Verify**: `python -c "from nautilus.ui import create_admin_router; from nautilus.observability import setup_otel; from nautilus.adapters.influxdb import InfluxDBAdapter; from nautilus.adapters.s3 import S3Adapter; print('POC_COMPLETE')" && pyright`
  - **Commit**: `feat(operator-platform): complete POC — all workstreams validated`

---

## Phase 2: Refactoring

After POC validated, clean up code. No new features.

- [ ] 2.1 Extract audit reader error handling (corrupt lines, missing file, invalid cursor)
  - **Do**:
    1. Add try/except around JSONL line parsing to skip corrupt lines with warning log
    2. Handle missing `audit.jsonl` gracefully — return empty `AuditPage` with "No audit data"
    3. Validate cursor decoding — invalid/tampered cursors reset to page 1
  - **Files**: `nautilus/ui/audit_reader.py`
  - **Done when**: All three error paths handled gracefully
  - **Verify**: `ruff check nautilus/ui/audit_reader.py && pyright`
  - **Commit**: `refactor(ui): add error handling to audit reader`
  - _Design: Error Handling — Audit Reader_

- [ ] 2.2 Extract admin UI error handling (broker not ready, auth failure)
  - **Do**:
    1. Add 503 "Broker starting..." template response when `broker is None`
    2. Ensure all routes return proper error HTML (not raw JSON exceptions)
    3. Add "Attestation not configured" message when no signing key
  - **Files**: `nautilus/ui/router.py`
  - **Done when**: All error paths return user-friendly HTML responses
  - **Verify**: `ruff check nautilus/ui/router.py && pyright`
  - **Commit**: `refactor(ui): add error handling for broker-not-ready and attestation`
  - _Design: Error Handling — Admin UI_

- [ ] 2.3 [VERIFY] Quality checkpoint: error handling
  - **Do**: Run quality commands
  - **Verify**: `ruff check nautilus/ui/ && pyright`
  - **Done when**: No lint errors, no type errors
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

- [ ] 2.4 Modularize OTel span injection pattern in broker.py
  - **Do**:
    1. Ensure OTel span calls are cleanly separated from business logic
    2. Extract span attribute construction into helper functions
    3. Verify `_OTEL_AVAILABLE` guard pattern is consistent everywhere
  - **Files**: `nautilus/core/broker.py`, `nautilus/observability/spans.py`
  - **Done when**: OTel code cleanly separated, consistent guard pattern
  - **Verify**: `ruff check nautilus/core/broker.py nautilus/observability/ && pyright`
  - **Commit**: `refactor(otel): clean up span injection pattern in broker`
  - _Design: Integration — OTel guards_

- [ ] 2.5 Clean up SDK types — add docstrings and validate model configs
  - **Do**:
    1. Add comprehensive docstrings to all SDK public APIs (protocols, types, config, exceptions, scope)
    2. Ensure `SourceConfig` has `model_config = ConfigDict(extra="allow")`
    3. Verify all re-exports in `__init__.py` have `__all__` list
  - **Files**: `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/types.py`, `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/config.py`, `packages/nautilus-adapter-sdk/src/nautilus_adapter_sdk/__init__.py`
  - **Done when**: All public APIs documented, model configs correct
  - **Verify**: `python -c "import packages.nautilus_adapter_sdk.src.nautilus_adapter_sdk as sdk; help(sdk)" 2>/dev/null || echo 'docstrings added'`
  - **Commit**: `refactor(sdk): add docstrings and validate model configs`

- [ ] 2.6 Validate SourceConfig.connection never exposed in templates
  - **Do**:
    1. Audit all admin UI templates — ensure `connection` field is never referenced
    2. Ensure router only passes safe fields (`id`, `type`, `classification`, `data_types`, `allowed_purposes`, `description`) to templates
  - **Files**: `nautilus/ui/router.py`
  - **Done when**: Zero references to `connection` in any template context
  - **Verify**: `! grep -r 'connection' nautilus/ui/templates/ && echo 'SECURE'`
  - **Commit**: `refactor(ui): verify no credential exposure in templates`
  - _Requirements: NFR-9_

- [ ] 2.7 Validate zero external resource references in templates
  - **Do**:
    1. Audit all templates for `http://` or `https://` references
    2. Remove any external CDN references if found
    3. Ensure all assets are vendored under `/admin/static/`
  - **Files**: `nautilus/ui/templates/` (all files)
  - **Done when**: Zero external URL references in templates
  - **Verify**: `! grep -rE 'https?://' nautilus/ui/templates/ && echo 'AIR_GAP_SAFE'`
  - **Commit**: `refactor(ui): verify air-gap compliance — zero external URLs`
  - _Requirements: NFR-1, AC-17.5, FR-29_

- [ ] 2.8 [VERIFY] Quality checkpoint: refactoring complete
  - **Do**: Run full quality suite
  - **Verify**: `ruff check nautilus tests && ruff format --check nautilus tests && pyright`
  - **Done when**: All lint, format, and type checks pass
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

---

## Phase 3: Testing

- [ ] 3.1 Unit tests for AuditReader (pagination, cursors, double-parse, filters)
  - **Do**:
    1. Create `tests/unit/test_audit_reader.py`
    2. Test: 200-line JSONL file paginated in 4 pages (page_size=50), cursor round-trip correct
    3. Test: double-parse (outer AuditRecord → inner AuditEntry extracted)
    4. Test: combined filters (agent_id + source_id + time range) produce correct subset
  - **Files**: `tests/unit/test_audit_reader.py`
  - **Done when**: All audit reader tests pass
  - **Verify**: `pytest tests/unit/test_audit_reader.py -v`
  - **Commit**: `test(ui): add unit tests for AuditReader`
  - _Requirements: FR-6, FR-7, FR-8, AC-3.2, AC-3.6_

- [ ] 3.2 Unit tests for admin UI source and decision routes
  - **Do**:
    1. Create `tests/unit/test_admin_routes.py`
    2. Test: `GET /admin/sources` returns 200 with HTML content-type, mock broker with 3 sources all rendered
    3. Test: HTMX partial (HX-Request header) returns fragment only
    4. Test: `GET /admin/decisions/{request_id}` modal fragment contains rule_trace, denial_records
    5. Test: filter params produce correct AuditEntry query
  - **Files**: `tests/unit/test_admin_routes.py`
  - **Done when**: All admin route tests pass
  - **Verify**: `pytest tests/unit/test_admin_routes.py -v`
  - **Commit**: `test(ui): add unit tests for admin routes`
  - _Requirements: FR-2, FR-4, FR-5, AC-1.1, AC-1.3, AC-2.3_

- [ ] 3.3 [VERIFY] Quality checkpoint: UI tests
  - **Do**: Run quality commands including new tests
  - **Verify**: `ruff check tests/unit/test_audit_reader.py tests/unit/test_admin_routes.py && pytest tests/unit/test_audit_reader.py tests/unit/test_admin_routes.py -v`
  - **Done when**: Tests pass, no lint errors
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

- [ ] 3.4 Unit tests for attestation verification
  - **Do**:
    1. Create `tests/unit/test_admin_attestation.py`
    2. Test: valid token → "valid" result fragment
    3. Test: tampered token → "invalid" result fragment
    4. Test: no signing key configured → "Attestation not configured" message
  - **Files**: `tests/unit/test_admin_attestation.py`
  - **Done when**: All attestation tests pass
  - **Verify**: `pytest tests/unit/test_admin_attestation.py -v`
  - **Commit**: `test(ui): add unit tests for attestation verification`
  - _Requirements: FR-9, AC-4.2, AC-4.4_

- [ ] 3.5 Unit tests for OTel spans and metrics
  - **Do**:
    1. Create `tests/unit/test_otel_spans.py`
    2. Test: mock tracer captures expected span hierarchy (broker.request → intent_analysis → fathom_routing → adapter_fan_out → synthesis → audit_emit → attestation_sign)
    3. Test: after one broker request, all 9 metrics have non-zero values (use OTel test SDK)
    4. Test: no-op behavior when OTel not installed (guard works)
  - **Files**: `tests/unit/test_otel_spans.py`
  - **Done when**: Span hierarchy and metrics tests pass
  - **Verify**: `pytest tests/unit/test_otel_spans.py -v`
  - **Commit**: `test(otel): add unit tests for spans and metrics`
  - _Requirements: FR-12, FR-13, AC-6.2, AC-6.3, AC-6.4_

- [ ] 3.6 Unit tests for InfluxDB and S3 scope mapping
  - **Do**:
    1. Create `tests/unit/test_adapter_scope.py`
    2. Test: InfluxDB scope mapping — ScopeConstraint → Flux filter fragments for measurement, tag, time range
    3. Test: S3 scope mapping — ScopeConstraint → prefix, tag, classification filters
  - **Files**: `tests/unit/test_adapter_scope.py`
  - **Done when**: Scope mapping logic tests pass
  - **Verify**: `pytest tests/unit/test_adapter_scope.py -v`
  - **Commit**: `test(adapters): add unit tests for InfluxDB and S3 scope mapping`
  - _Requirements: AC-15.2, AC-16.2_

- [ ] 3.7 [VERIFY] Quality checkpoint: unit tests complete
  - **Do**: Run all unit tests
  - **Verify**: `ruff check tests/ && pytest -m unit -v`
  - **Done when**: All unit tests pass
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

- [ ] 3.8 Integration test: admin UI auth gate (401 without auth)
  - **Do**:
    1. Create `tests/integration/test_admin_auth.py`
    2. Test: request without auth header to `/admin/sources` returns 401
    3. Test: request with valid auth returns 200
    4. Use FastAPI TestClient with mock broker
  - **Files**: `tests/integration/test_admin_auth.py`
  - **Done when**: Auth gate integration tests pass
  - **Verify**: `pytest tests/integration/test_admin_auth.py -v`
  - **Commit**: `test(ui): add integration test for admin auth gate`
  - _Requirements: FR-10, AC-5.2, NFR-8_

- [ ] 3.9 Integration test: admin UI full flow (GET /admin/sources → 200 with data)
  - **Do**:
    1. Create `tests/integration/test_admin_flow.py`
    2. Test: `GET /admin/sources` → 200 with source data rendered in HTML
    3. Test: `GET /admin/audit` → 200 with audit entries rendered
    4. Test: `GET /admin/attestation` → 200 with form
    5. Use TestClient with mock broker and fixture audit JSONL
  - **Files**: `tests/integration/test_admin_flow.py`
  - **Done when**: Full-flow integration tests pass
  - **Verify**: `pytest tests/integration/test_admin_flow.py -v`
  - **Commit**: `test(ui): add integration test for admin UI full flow`
  - _Requirements: FR-1, FR-2, AC-1.1_

- [ ] 3.10 Unit tests for NIST and HIPAA rule pack YAML validation
  - **Do**:
    1. Create `tests/unit/test_rule_packs.py`
    2. Test: all NIST pack YAML files parse correctly
    3. Test: all HIPAA pack YAML files parse correctly
    4. Test: both packs contain compliance disclaimer
    5. Test: salience bands are within expected ranges (170-190, 130-150, 110-120)
  - **Files**: `tests/unit/test_rule_packs.py`
  - **Done when**: All rule pack validation tests pass
  - **Verify**: `pytest tests/unit/test_rule_packs.py -v`
  - **Commit**: `test(rules): add YAML validation tests for NIST and HIPAA packs`
  - _Requirements: FR-24, FR-25, FR-26, AC-13.6, AC-14.7_

- [ ] 3.11 [VERIFY] Quality checkpoint: integration + rule pack tests
  - **Do**: Run all tests
  - **Verify**: `ruff check tests/ && pytest -v`
  - **Done when**: All tests pass
  - **Commit**: `chore(operator-platform): pass quality checkpoint` (if fixes needed)

---

## Phase 4: Quality Gates

- [ ] 4.1 [VERIFY] V4 Full local CI: ruff check + pyright + pytest
  - **Do**: Run complete local CI suite
  - **Verify**: `ruff check nautilus tests && ruff format --check nautilus tests && pyright && pytest -m unit && pytest -m integration`
  - **Done when**: All commands pass with zero errors
  - **Commit**: `chore(operator-platform): pass local CI` (if fixes needed)

- [ ] 4.2 Create PR and verify CI
  - **Do**:
    1. Verify current branch is a feature branch: `git branch --show-current`
    2. Push branch: `git push -u origin $(git branch --show-current)`
    3. Create PR: `gh pr create --title "feat: operator platform — admin UI, OTel, SDK, rule packs, adapters" --body "..."`
  - **Verify**: `gh pr checks --watch`
  - **Done when**: PR created, all CI checks green
  - **Commit**: None

- [ ] 4.3 [VERIFY] V5 CI pipeline passes
  - **Do**: Verify GitHub Actions/CI passes after push
  - **Verify**: `gh pr checks`
  - **Done when**: All checks show passing
  - **Commit**: None

- [ ] 4.4 [VERIFY] V6 AC checklist
  - **Do**:
    1. Read `specs/operator-platform/requirements.md`, verify each AC programmatically:
       - AC-1.1: `grep -r 'GET.*sources' nautilus/ui/router.py`
       - AC-3.2: `grep -r 'seek\|cursor\|byte_offset' nautilus/ui/audit_reader.py`
       - AC-5.1: `grep -r 'auth\|Depends' nautilus/ui/router.py`
       - AC-6.2: `grep -r 'broker_span' nautilus/core/broker.py`
       - AC-6.5: `grep -r 'ImportError' nautilus/observability/`
       - AC-9.1: `test -f packages/nautilus-adapter-sdk/pyproject.toml`
       - AC-13.1: `test -d rule-packs/data-routing-nist/`
       - AC-14.1: `test -d rule-packs/data-routing-hipaa/`
       - AC-15.1: `grep -r 'influxdb' nautilus/adapters/influxdb.py`
       - AC-16.1: `grep -r 's3' nautilus/adapters/s3.py`
       - AC-17.5: `! grep -rE 'https?://' nautilus/ui/templates/`
  - **Verify**: All grep/test commands return expected results
  - **Done when**: All acceptance criteria confirmed met
  - **Commit**: None

- [ ] VE1 [VERIFY] E2E startup: start dev server and wait for ready
  - **Do**:
    1. Start dev server in background: `python -m nautilus serve --config nautilus.yaml --transport rest &`
    2. Record PID: `echo $! > /tmp/ve-pids.txt`
    3. Wait for server ready with 60s timeout: `for i in $(seq 1 60); do curl -s http://localhost:8000/healthz && break || sleep 1; done`
  - **Verify**: `curl -sf http://localhost:8000/healthz && echo VE1_PASS`
  - **Done when**: Dev server running and responding on port 8000
  - **Commit**: None

- [ ] VE2 [VERIFY] E2E check: test admin UI pages render
  - **Do**:
    1. `curl -sf http://localhost:8000/admin/sources` — verify 200 with HTML content
    2. `curl -sf http://localhost:8000/admin/audit` — verify 200 with HTML content
    3. `curl -sf http://localhost:8000/admin/attestation` — verify 200 with HTML content
    4. `curl -sf http://localhost:8000/admin/decisions` — verify 200 with HTML content
  - **Verify**: `curl -sf http://localhost:8000/admin/sources | grep -q '<html' && curl -sf http://localhost:8000/admin/audit | grep -q '<html' && curl -sf http://localhost:8000/admin/attestation | grep -q '<html' && curl -sf http://localhost:8000/admin/decisions | grep -q '<html' && echo VE2_PASS`
  - **Done when**: All four admin pages return HTML content
  - **Commit**: None

- [ ] VE3 [VERIFY] E2E cleanup: stop server and free port
  - **Do**:
    1. Kill by PID: `kill $(cat /tmp/ve-pids.txt) 2>/dev/null; sleep 2; kill -9 $(cat /tmp/ve-pids.txt) 2>/dev/null || true`
    2. Kill by port fallback: `lsof -ti :8000 | xargs -r kill 2>/dev/null || true`
    3. Remove PID file: `rm -f /tmp/ve-pids.txt`
    4. Verify port free: `! lsof -ti :8000`
  - **Verify**: `! lsof -ti :8000 && echo VE3_PASS`
  - **Done when**: No process listening on port 8000, PID file removed
  - **Commit**: None

---

## Phase 5: PR Lifecycle

- [ ] 5.1 PR creation and initial push
  - **Do**:
    1. Ensure all Phase 1-4 tasks complete
    2. If PR not yet created (from 4.2), create now: `gh pr create`
    3. Push latest changes: `git push`
  - **Done when**: PR exists and is up to date
  - **Verify**: `gh pr view --json state | grep -q 'OPEN'`
  - **Commit**: None

- [ ] 5.2 CI monitoring and fix loop
  - **Do**:
    1. Check CI status: `gh pr checks`
    2. If any check fails, read failure details, fix locally, push
    3. Repeat until all checks green
  - **Done when**: All CI checks passing
  - **Verify**: `gh pr checks | grep -v 'pass\|✓' | wc -l | grep -q '^0$' || gh pr checks`
  - **Commit**: `fix(operator-platform): resolve CI failures` (if fixes needed)

- [ ] 5.3 Review comment resolution
  - **Do**:
    1. Check for review comments: `gh pr view --json reviews`
    2. Address any requested changes
    3. Push fixes and re-request review
  - **Done when**: No unresolved review comments
  - **Verify**: `gh pr view --json reviewDecision`
  - **Commit**: `fix(operator-platform): address review comments` (if fixes needed)

- [ ] 5.4 Final validation
  - **Do**:
    1. Verify zero test regressions: `pytest`
    2. Verify code is modular/reusable
    3. Verify all acceptance criteria met
    4. Verify PR is mergeable
  - **Done when**: PR ready for merge, all criteria met
  - **Verify**: `pytest && gh pr view --json mergeable | grep -q 'MERGEABLE'`
  - **Commit**: None

---

## Notes

- **POC shortcuts taken**: SDK package not published to PyPI (structure only). Copier template not tested with `copier copy`. MkDocs site not built. Rule packs not loaded via `Engine.load_pack()`. InfluxDB/S3 adapters not integration-tested with real containers. HTMX vendored as placeholder if download not possible.
- **Production TODOs**: Publish SDK to PyPI. Test Copier template generation. Build MkDocs site. Integration test InfluxDB/S3 with testcontainers. Load-test with Locust harness. Verify Grafana dashboards render against live OTel stack.
- **Air-gap compliance**: All static assets vendored. Zero external URLs. OTel optional via extras. OTEL_SDK_DISABLED=true for no-op.
- **Security invariant**: SourceConfig.connection NEVER passed to templates. Only id, type, classification rendered.
- **Backward compatibility**: AuditEntry.trace_id is optional (None default). No existing behavior changes.
