---
spec: operator-platform
phase: requirements
created: 2026-04-16
depends-on: [core-broker, reasoning-engine]
---

# Requirements: Operator Platform (Phase 4)

## Goal

Ship operator-facing surfaces that make Nautilus operable at scale: a read-only Admin UI for inspecting routing decisions and audit history, OpenTelemetry instrumentation with Grafana dashboards, a standalone adapter SDK for third-party plugin authors, compliance rule packs (NIST SP 800-53 and HIPAA), and two new ecosystem adapters (InfluxDB, S3). All workstreams are additive — zero Broker-side changes required.

---

## User Stories

### Workstream A — Admin UI

#### US-1: View Source Status Dashboard

**As an** operator
**I want to** see the health and policy summary of every registered data source
**So that** I can spot misconfigured or unreachable sources without inspecting config files.

**Acceptance Criteria:**
- [ ] AC-1.1: `GET /admin/sources` returns a full HTML page listing every source from `Broker.sources` with `id`, `type`, `classification`, `data_types`, and `allowed_purposes`.
- [ ] AC-1.2: Each source card shows last-successful-query timestamp derived from the most recent `AuditEntry` where `sources_queried` includes that `source_id`.
- [ ] AC-1.3: HTMX partial request (`HX-Request: true`) to `/admin/sources` returns only the `<tbody>` fragment for table updates.
- [ ] AC-1.4: Page functions with JavaScript disabled (full-page reload fallback via standard form submit).
- [ ] AC-1.5: SSE endpoint `/admin/sources/events` pushes source health changes; the page subscribes via `hx-ext="sse"`.

---

#### US-2: View Routing Decisions per Request

**As an** operator
**I want to** inspect the full routing trace for any broker request — facts asserted, rules fired, sources selected/denied/skipped, and scope constraints applied
**So that** I can debug unexpected routing behavior without reading raw JSONL.

**Acceptance Criteria:**
- [ ] AC-2.1: `GET /admin/decisions` renders a filterable table of recent requests with columns: `timestamp`, `request_id`, `agent_id`, `sources_queried`, `sources_denied`, `duration_ms`.
- [ ] AC-2.2: Filters for `agent_id`, time range, and decision outcome (success/denied/error) implemented as form-controller hidden inputs with `hx-push-url="true"`.
- [ ] AC-2.3: Clicking a row opens a detail modal (via `hx-get="/admin/decisions/{request_id}"`) showing `rule_trace`, `routing_decisions`, `scope_constraints`, `denial_records`, and `facts_asserted_summary`.
- [ ] AC-2.4: Search input debounces at 500ms (`hx-trigger="keyup changed delay:500ms"`).

---

#### US-3: Browse and Search the Audit Log

**As an** operator
**I want to** browse the full audit history with filtering by agent, source, decision outcome, and time range
**So that** I can investigate incidents and verify compliance posture.

**Acceptance Criteria:**
- [ ] AC-3.1: `GET /admin/audit` renders a paginated table of `AuditEntry` records parsed from `audit.jsonl` via `decode_nautilus_entry()`.
- [ ] AC-3.2: Pagination uses seek-based cursors (file byte offset), not line counting, to handle GB-sized JSONL files. Page size default: 50 rows.
- [ ] AC-3.3: Filters: `agent_id` (text), `source_id` (dropdown), `event_type` (dropdown), time range (start/end datetime inputs). All filters compose as AND.
- [ ] AC-3.4: Sort by `timestamp` descending (default) or `duration_ms`. Sort state preserved in URL via `hx-push-url`.
- [ ] AC-3.5: Clicking a row expands inline detail showing all `AuditEntry` fields including `rule_trace` and `attestation_token`.
- [ ] AC-3.6: Double-parse handled transparently: outer `AuditRecord` envelope unwrapped, inner `AuditEntry` extracted from `metadata["nautilus_audit_entry"]`.

---

#### US-4: Verify Attestation Tokens

**As an** operator
**I want to** paste or select an attestation token and verify its signature against the broker's Ed25519 public key
**So that** I can confirm a response was policy-checked without external tools.

**Acceptance Criteria:**
- [ ] AC-4.1: `GET /admin/attestation` renders a form with a textarea for token input and a "Verify" button.
- [ ] AC-4.2: `POST /admin/attestation/verify` accepts the token, verifies the EdDSA JWT signature, and returns an HTML fragment showing: valid/invalid, payload claims (`request_id`, `scope_hash`, `rule_trace_hash`, `timestamp`), and expiration status.
- [ ] AC-4.3: Verification is client-side-free — all crypto runs server-side via the existing `AttestationService`.
- [ ] AC-4.4: If no signing key is configured (air-gap mode without attestation), the page shows a clear "Attestation not configured" message.

---

#### US-5: Admin UI Auth via Reverse Proxy

**As an** operator
**I want to** the Admin UI to be protected by the same `proxy_trust` auth as the broker API
**So that** only authenticated operators (identified by `X-Forwarded-User`) can access admin views.

**Acceptance Criteria:**
- [ ] AC-5.1: All `/admin/*` routes are gated by the existing `proxy_trust_dependency` (or `api_key` depending on config mode).
- [ ] AC-5.2: Unauthenticated requests to `/admin/*` return HTTP 401 (not a redirect to a login page).
- [ ] AC-5.3: The authenticated user identity is displayed in the dashboard header.
- [ ] AC-5.4: No new auth mechanism is introduced; zero additional auth code beyond reusing the existing dependency.

---

### Workstream B — Observability

#### US-6: Instrument Broker Pipeline with OpenTelemetry

**As an** operator
**I want to** the broker to emit OpenTelemetry traces and metrics for every request
**So that** I can monitor performance, debug latency, and track routing patterns in Grafana.

**Acceptance Criteria:**
- [ ] AC-6.1: Auto-instrument FastAPI HTTP layer via `opentelemetry-instrumentation-fastapi`. Exclude `/healthz` and `/readyz` via `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS`.
- [ ] AC-6.2: Manual spans created for broker pipeline stages: `broker.request` (root), `intent_analysis`, `fathom_routing`, `adapter_fan_out` (with per-source child spans), `synthesis`, `audit_emit`, `attestation_sign`.
- [ ] AC-6.3: Six counters emitted: `nautilus.requests.total`, `nautilus.routing.decisions.total`, `nautilus.scope.denials.total`, `nautilus.attestation.total`, `nautilus.adapter.errors.total`, `nautilus.session.exposure_flags.total`.
- [ ] AC-6.4: Three histograms emitted: `nautilus.request.duration`, `nautilus.adapter.latency`, `nautilus.fathom.evaluation.duration`.
- [ ] AC-6.5: All OTel code guarded by `try/except ImportError`; missing `nautilus[otel]` extras produce no errors.
- [ ] AC-6.6: `OTEL_SDK_DISABLED=true` makes the SDK entirely no-op for air-gap deployments.

---

#### US-7: Ship Grafana Dashboard Provisioning

**As an** operator
**I want to** pre-built Grafana dashboards that visualize Nautilus metrics and traces
**So that** I can deploy observability without hand-building dashboards.

**Acceptance Criteria:**
- [ ] AC-7.1: Three raw JSON dashboard files shipped: `overview.json` (request rate, decision distribution, error rate), `adapters.json` (per-adapter latency, error breakdown), `attestation.json` (attestation success/failure rate, verification latency).
- [ ] AC-7.2: `docker-compose.otel.yml` boots Grafana + Tempo (traces) + Prometheus (metrics) + Loki (logs) with provisioned datasources.
- [ ] AC-7.3: Datasource provisioning supports Tempo-to-Prometheus exemplar links and Loki-to-Tempo derived field drill-down.
- [ ] AC-7.4: Dashboards render correctly against a `docker compose up` stack with a running Nautilus broker emitting OTel data.
- [ ] AC-7.5: All dashboard JSON files and compose config ship inside the package (air-gap compatible).

---

#### US-8: Benchmark Broker Performance

**As an** operator
**I want to** run a reproducible load test that produces a latency/throughput report across all adapters
**So that** I can validate performance characteristics before production deployment.

**Acceptance Criteria:**
- [ ] AC-8.1: Locust-based load harness under `benchmarks/` with configurable user count, spawn rate, and test duration.
- [ ] AC-8.2: `--otel` flag enables OTel span emission from Locust workers for correlated load test traces.
- [ ] AC-8.3: JSON report output with p50/p95/p99 latencies, throughput (req/s), and error rate per endpoint.
- [ ] AC-8.4: `Dockerfile.bench` for reproducible Dockerized benchmark runs.
- [ ] AC-8.5: Existing in-process harness (`test_fastapi_latency_harness.py`) preserved; Locust harness is additive.

---

### Workstream C — Adapter SDK

#### US-9: Publish Standalone Adapter SDK Package

**As a** third-party adapter author
**I want to** install `nautilus-adapter-sdk` with only `pydantic>=2.0` as a dependency
**So that** I can build adapters without pulling in the full Nautilus broker.

**Acceptance Criteria:**
- [ ] AC-9.1: `nautilus-adapter-sdk` is a separate PyPI package with `pydantic>=2.0` as sole runtime dependency.
- [ ] AC-9.2: Package targets Python `>=3.11` (broader than Nautilus's `>=3.14`).
- [ ] AC-9.3: Exports: `Adapter` Protocol, `Embedder` Protocol, Pydantic types (`IntentAnalysis`, `ScopeConstraint`, `AdapterResult`, `SourceConfig`, `ErrorRecord`, `AuthConfig` variants, `EndpointSpec`), exception hierarchy (`AdapterError`, `ScopeEnforcementError`), scope validators (`validate_operator`, `validate_field`, `render_field`).
- [ ] AC-9.4: Ships `py.typed` marker for PEP 561 type distribution.
- [ ] AC-9.5: `SourceConfig.type` is `str` (not a Literal union) so third-party adapters can declare arbitrary type names.
- [ ] AC-9.6: CI drift-guard test asserts structural equivalence between SDK types and Nautilus-internal types (no circular dependency).

---

#### US-10: Adapter Compliance Test Suite

**As a** third-party adapter author
**I want to** run a pre-built compliance suite against my adapter
**So that** I can verify it satisfies the Adapter Protocol contract before publishing.

**Acceptance Criteria:**
- [ ] AC-10.1: `AdapterComplianceSuite` importable from `nautilus_adapter_sdk.testing`.
- [ ] AC-10.2: Suite covers: connect/execute/close lifecycle, scope enforcement (valid + invalid operators), idempotent close, error path handling.
- [ ] AC-10.3: Suite is parameterized: adapter authors provide a fixture returning their adapter instance + a test `SourceConfig`.
- [ ] AC-10.4: Suite runs via standard `pytest` — no custom runner required.

---

#### US-11: Adapter Scaffold Template

**As a** third-party adapter author
**I want to** scaffold a new adapter project from a Copier template
**So that** I get correct project structure, CI config, and compliance suite wiring out of the box.

**Acceptance Criteria:**
- [ ] AC-11.1: Copier template under `templates/adapter/` in the Nautilus repo.
- [ ] AC-11.2: Template generates: adapter module, `pyproject.toml` with `nautilus.adapters` entry point, compliance suite test file, README, and CI workflow.
- [ ] AC-11.3: `copier update` works for template evolution sync.
- [ ] AC-11.4: Generated project passes `ruff check`, `pyright`, and compliance suite on first run (no manual fixes needed).

---

#### US-12: Adapter SDK Documentation

**As a** third-party adapter author
**I want to** a "Write Your First Adapter" tutorial and API reference
**So that** I can build an adapter without reading Nautilus internals.

**Acceptance Criteria:**
- [ ] AC-12.1: MkDocs + Material site under `docs/sdk/`.
- [ ] AC-12.2: "Write Your First Adapter" tutorial walks through: install SDK, implement Protocol, register entry point, run compliance suite.
- [ ] AC-12.3: API reference auto-generated via `mkdocstrings` from SDK docstrings.
- [ ] AC-12.4: Plugin discovery documented: entry point group `nautilus.adapters`, how the broker discovers and loads third-party adapters at startup.

---

### Workstream D — Compliance Rule Packs

#### US-13: NIST SP 800-53 Data Routing Rule Pack

**As an** operator in a federal/CUI environment
**I want to** install a `data-routing-nist` rule pack that enforces NIST SP 800-53 access and information flow controls
**So that** my Nautilus routing decisions align with federal compliance requirements.

**Acceptance Criteria:**
- [ ] AC-13.1: Pack ships as YAML under `rule-packs/data-routing-nist/` with `templates/`, `modules/`, `rules/` subdirectories.
- [ ] AC-13.2: Registered via `fathom.packs` entry point in `pyproject.toml`.
- [ ] AC-13.3: Rules map these NIST controls to Nautilus routing: AC-3 (access enforcement), AC-4 (information flow), AC-6 (least privilege), AC-16 (security attributes), AC-21 (information sharing), AC-23 (data mining protection), SC-7 (boundary protection), SC-16 (transmission integrity).
- [ ] AC-13.4: Salience bands: 170-190 for denials, 130-150 for scope constraints, 110-120 for escalations.
- [ ] AC-13.5: Extends CUI sub-category hierarchy with ITAR, EAR, FTI, LES categories.
- [ ] AC-13.6: Pack passes Fathom's pack validation (`Engine.load_pack()` succeeds without error).
- [ ] AC-13.7: Compliance disclaimer included in pack metadata and documentation: "Reference implementation only — not certified for production compliance."

---

#### US-14: HIPAA Data Routing Rule Pack

**As an** operator in a healthcare environment
**I want to** install a `data-routing-hipaa` rule pack that enforces HIPAA minimum necessary and PHI classification
**So that** my Nautilus routing decisions restrict PHI access to the minimum required for each purpose.

**Acceptance Criteria:**
- [ ] AC-14.1: Pack ships as YAML under `rule-packs/data-routing-hipaa/` with `templates/`, `modules/`, `rules/` subdirectories.
- [ ] AC-14.2: Registered via `fathom.packs` entry point in `pyproject.toml`.
- [ ] AC-14.3: PHI classification via 18 HIPAA identifiers as `data_types` tags on sources. Rules match on these tags to restrict access.
- [ ] AC-14.4: Minimum necessary standard mapped to `scope_constraint` template — emit field-level restrict constraints per purpose (treatment, payment, operations).
- [ ] AC-14.5: PHI hierarchy defined: de-identified < limited < standard < sensitive (mental health, substance abuse, HIV).
- [ ] AC-14.6: Salience bands consistent with NIST pack: 170-190 denials, 130-150 scope constraints, 110-120 escalations.
- [ ] AC-14.7: Pack passes Fathom's pack validation.
- [ ] AC-14.8: Compliance disclaimer included.

---

### Workstream E — Ecosystem Adapters

#### US-15: InfluxDB Adapter

**As an** operator with time-series data in InfluxDB
**I want to** register an InfluxDB source and have Nautilus scope queries by measurement, tags, and time range
**So that** agents can query time-series data with the same scope enforcement as other sources.

**Acceptance Criteria:**
- [ ] AC-15.1: `InfluxDBAdapter` implements the `Adapter` Protocol with `source_type = "influxdb"`.
- [ ] AC-15.2: Scope constraints map to: measurement filtering, tag key/value restrictions, and time range enforcement (`>=`/`<=` on `_time`).
- [ ] AC-15.3: Connection via `influxdb-client-python` async API to InfluxDB v2+ (Flux query language).
- [ ] AC-15.4: Adapter registered in `ADAPTER_REGISTRY` and discoverable via `nautilus.adapters` entry point.
- [ ] AC-15.5: Integration test with `testcontainers`-booted InfluxDB verifies scoped query returns only matching measurements/tags within the time window.
- [ ] AC-15.6: `close()` releases HTTP client resources idempotently.

---

#### US-16: S3 Document Store Adapter

**As an** operator with documents in S3
**I want to** register an S3 source and have Nautilus scope access by prefix, tags, and classification labels
**So that** agents can access documents with the same policy enforcement as structured data.

**Acceptance Criteria:**
- [ ] AC-16.1: `S3Adapter` implements the `Adapter` Protocol with `source_type = "s3"`.
- [ ] AC-16.2: Scope constraints map to: S3 prefix restrictions, object tag filtering, and classification label matching (via object metadata).
- [ ] AC-16.3: Connection via `aiobotocore` async S3 client.
- [ ] AC-16.4: Adapter registered in `ADAPTER_REGISTRY` and discoverable via `nautilus.adapters` entry point.
- [ ] AC-16.5: Integration test with `testcontainers`-booted MinIO (S3-compatible) verifies scoped listing returns only objects matching prefix/tag/classification constraints.
- [ ] AC-16.6: `close()` releases session resources idempotently.

---

### Workstream F — Infrastructure

#### US-17: Admin UI Static Asset Packaging

**As an** operator deploying in air-gapped environments
**I want to** all Admin UI assets (HTMX, CSS, templates) shipped inside the Python package
**So that** no CDN or external network access is required at runtime.

**Acceptance Criteria:**
- [ ] AC-17.1: `htmx.min.js` (2.0.x, ~14KB gzip) and `htmx-ext-sse.min.js` (~3KB) vendored under `nautilus/ui/static/`.
- [ ] AC-17.2: Custom `styles.css` ships under `nautilus/ui/static/`.
- [ ] AC-17.3: All static files declared in `pyproject.toml` `[tool.setuptools.package-data]` (or equivalent) for inclusion in sdist/wheel.
- [ ] AC-17.4: Jinja2 templates under `nautilus/ui/templates/` following the hierarchy: `base.html` > `layouts/dashboard.html` > `pages/*.html` with `partials/*.html` for HTMX fragments.
- [ ] AC-17.5: Zero external resource references (`<script src>`, `<link href>`, `<img src>`) pointing outside the package.

---

#### US-18: OTel Optional Dependency Group

**As an** operator
**I want to** OTel instrumentation available via `pip install nautilus[otel]` without bloating the base install
**So that** air-gap deployments stay lean and OTel-equipped deployments get everything they need.

**Acceptance Criteria:**
- [ ] AC-18.1: `pyproject.toml` declares `[project.optional-dependencies] otel = [...]` with `opentelemetry-sdk`, `opentelemetry-api`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-exporter-otlp-proto-http`, `prometheus-client`.
- [ ] AC-18.2: All OTel imports in Nautilus source guarded by `try/except ImportError` with graceful no-op fallback.
- [ ] AC-18.3: `pip install nautilus` (no extras) works without any OTel packages installed.

---

## Functional Requirements

| ID | Requirement | User Story | Priority | How to Verify |
|----|-------------|------------|----------|---------------|
| FR-1 | Mount Admin UI as a FastAPI `APIRouter` under `/admin/` on the existing app. Share broker lifespan and auth. | US-1, US-5 | High | Integration test: `GET /admin/sources` returns 200 with HTML content-type. |
| FR-2 | Source status page lists all sources from `Broker.sources` with health metadata derived from recent `AuditEntry` records. | US-1 | High | Unit test: mock broker with 3 sources, assert all rendered. |
| FR-3 | SSE endpoint `/admin/sources/events` pushes source health updates using `sse-starlette`. | US-1 | Medium | Integration test: SSE client receives event after a broker request completes. |
| FR-4 | Routing decisions table with `agent_id`, time range, and outcome filters. Form-controller pattern with `hx-push-url`. | US-2 | High | Unit test: filter params produce correct AuditEntry query. |
| FR-5 | Decision detail modal served via `hx-get="/admin/decisions/{request_id}"` returning an HTML fragment with `rule_trace`, `routing_decisions`, `scope_constraints`, `denial_records`. | US-2 | High | Unit test: given an AuditEntry, modal fragment contains all expected fields. |
| FR-6 | Audit log viewer with seek-based JSONL pagination (byte offset cursors, not line counting). Default page size 50. | US-3 | High | Unit test: 200-line JSONL file paginated in 4 pages; cursor round-trips correctly. |
| FR-7 | Audit viewer double-parse: unwrap outer `AuditRecord` envelope, extract `AuditEntry` from `metadata["nautilus_audit_entry"]`. | US-3 | High | Unit test: raw JSONL line → `AuditEntry` model validates. |
| FR-8 | Audit filters compose as AND: `agent_id` (text), `source_id` (dropdown), `event_type` (dropdown), time range (start/end). | US-3 | High | Unit test: combined filters produce correct subset. |
| FR-9 | Attestation verification page: textarea input, server-side EdDSA JWT verification via `AttestationService`, result fragment. | US-4 | High | Unit test: valid token → "valid" result; tampered token → "invalid". |
| FR-10 | All `/admin/*` routes gated by existing auth dependency (`proxy_trust_dependency` or `require_api_key` per config). | US-5 | High | Integration test: request without auth header returns 401. |
| FR-11 | Auto-instrument FastAPI with `opentelemetry-instrumentation-fastapi`. Exclude health probes. | US-6 | High | Integration test: OTel collector receives HTTP spans for `/v1/request` but not `/healthz`. |
| FR-12 | Manual OTel spans for broker pipeline: `broker.request`, `intent_analysis`, `fathom_routing`, `adapter_fan_out` (per-source children), `synthesis`, `audit_emit`, `attestation_sign`. | US-6 | High | Unit test: mock tracer captures expected span hierarchy. |
| FR-13 | Emit 6 OTel counters and 3 histograms aligned with `design-v2.md` metric names. | US-6 | High | Unit test: after one broker request, all 9 metrics have non-zero values. |
| FR-14 | Three raw JSON Grafana dashboard files: `overview.json`, `adapters.json`, `attestation.json`. | US-7 | High | Validate: each file is valid JSON matching Grafana dashboard schema. |
| FR-15 | `docker-compose.otel.yml` boots Grafana + Tempo + Prometheus + Loki with provisioned datasources and dashboards. | US-7 | High | `docker compose -f docker-compose.otel.yml up` succeeds; Grafana reachable at `:3000`. |
| FR-16 | Locust-based load harness under `benchmarks/` with `--otel` flag and JSON report output. | US-8 | Medium | Run harness for 10s; JSON report contains p50/p95/p99 fields. |
| FR-17 | `Dockerfile.bench` for reproducible Dockerized benchmark runs. | US-8 | Medium | `docker build -f Dockerfile.bench .` succeeds. |
| FR-18 | `nautilus-adapter-sdk` package exports Protocol, types, exceptions, and scope validators with `pydantic>=2.0` sole dep. | US-9 | High | `pip install nautilus-adapter-sdk` in clean venv; `from nautilus_adapter_sdk import Adapter` succeeds. |
| FR-19 | SDK `SourceConfig.type` field is `str` (not Literal union). | US-9 | High | Type check: third-party adapter with `source_type = "custom"` passes pyright. |
| FR-20 | CI drift-guard test: structural equivalence between SDK types and Nautilus-internal types. | US-9 | High | CI job fails if SDK type signature diverges from Nautilus internal type. |
| FR-21 | `AdapterComplianceSuite` in `nautilus_adapter_sdk.testing`: lifecycle, scope, idempotent close, error paths. | US-10 | High | Run suite against one built-in adapter (e.g., PostgresAdapter); all pass. |
| FR-22 | Copier template under `templates/adapter/` generates adapter project with entry point, compliance test, CI. | US-11 | Medium | `copier copy templates/adapter/ /tmp/test-adapter`; generated project passes lint + compliance suite. |
| FR-23 | MkDocs + Material docs under `docs/sdk/` with tutorial and API reference via `mkdocstrings`. | US-12 | Medium | `mkdocs build` succeeds; "Write Your First Adapter" page exists. |
| FR-24 | `data-routing-nist` rule pack: YAML under `rule-packs/data-routing-nist/`, 8 NIST controls mapped, `fathom.packs` entry point. | US-13 | High | `Engine.load_pack("data-routing-nist")` succeeds; evaluation with CUI source produces expected denials. |
| FR-25 | `data-routing-hipaa` rule pack: YAML under `rule-packs/data-routing-hipaa/`, PHI classification via 18 identifiers, minimum necessary scope constraints. | US-14 | High | `Engine.load_pack("data-routing-hipaa")` succeeds; evaluation with PHI source restricts fields per purpose. |
| FR-26 | Both packs carry compliance disclaimer in metadata and README. | US-13, US-14 | High | Grep pack YAML and README for "reference implementation" disclaimer text. |
| FR-27 | `InfluxDBAdapter` with `source_type = "influxdb"`. Scope: measurement, tag, time range. Async via `influxdb-client-python`. | US-15 | High | Integration test with testcontainers InfluxDB: scoped query returns correct measurements. |
| FR-28 | `S3Adapter` with `source_type = "s3"`. Scope: prefix, tag, classification label. Async via `aiobotocore`. | US-16 | High | Integration test with testcontainers MinIO: scoped listing returns correct objects. |
| FR-29 | Vendor `htmx.min.js` 2.0.x + `htmx-ext-sse.min.js` under `nautilus/ui/static/`. Zero CDN references. | US-17 | High | Grep all templates for external URLs; expect zero matches. |
| FR-30 | `nautilus[otel]` optional dependency group in `pyproject.toml`. All OTel imports guarded by ImportError. | US-18 | High | `pip install nautilus` without extras; import nautilus succeeds with no OTel warning. |

---

## Non-Functional Requirements

| ID | Category | Metric | Target | Notes |
|----|----------|--------|--------|-------|
| NFR-1 | Air-gap — UI | External network references in templates | Zero | Grep static/ and templates/ for `http://` or `https://`. |
| NFR-2 | Air-gap — OTel | Base install without OTel extras | Functional | `pip install nautilus` works; OTel no-op fallback active. |
| NFR-3 | Air-gap — OTel disable | `OTEL_SDK_DISABLED=true` behavior | All spans/metrics silently discarded | Integration test with env var set. |
| NFR-4 | Performance — audit pagination | Seek-based cursor for 1GB JSONL file | Page load < 200ms | Benchmark test with synthetic 1M-line JSONL. |
| NFR-5 | Performance — OTel overhead | p95 latency increase from OTel instrumentation | < 3% of baseline `broker.request()` | Benchmark before/after with OTel enabled. |
| NFR-6 | Performance — UI render | `/admin/sources` full page render | < 100ms server-side | Unit test measures template render time. |
| NFR-7 | Security — read-only | Admin UI write endpoints | Zero POST/PUT/DELETE that mutate broker state | Static audit: only reads from `Broker.sources` and `audit.jsonl`. Exception: attestation verify POST is read-only (verifies, doesn't write). |
| NFR-8 | Security — auth | Unauthenticated admin access | HTTP 401 on every `/admin/*` route | Integration test. |
| NFR-9 | Security — no secrets in UI | Credentials in source status view | Zero | `SourceConfig.connection` never rendered; only `id`, `type`, `classification` shown. |
| NFR-10 | Compatibility — SDK Python | SDK target Python version | `>=3.11` | CI matrix: 3.11, 3.12, 3.13, 3.14. |
| NFR-11 | Compatibility — SDK Pydantic | SDK Pydantic dependency | `>=2.0` only | `pip install nautilus-adapter-sdk` in clean venv; no other runtime deps installed. |
| NFR-12 | Compatibility — Nautilus Python | Nautilus target Python version | `>=3.14` | Existing CI gate. |
| NFR-13 | Testing — SDK drift | SDK ↔ Nautilus type equivalence | CI gate passes | Drift-guard test in CI; fails if signatures diverge. |
| NFR-14 | Testing — compliance suite | AdapterComplianceSuite coverage | All built-in adapters pass | Run suite against postgres, pgvector, influxdb, s3 adapters. |
| NFR-15 | Testing — rule packs | Pack validation | Both packs pass `Engine.load_pack()` | CI test loads each pack and runs evaluation against fixture facts. |
| NFR-16 | Packaging — static assets | HTMX + CSS in wheel | Present in installed package | `pip install nautilus`; `importlib.resources` resolves `nautilus/ui/static/htmx.min.js`. |
| NFR-17 | Packaging — distroless | Static files in Docker image | Present without shell access | Dockerfile COPY from build stage; verify via `docker run --entrypoint=...`. |
| NFR-18 | License | All new dependencies MIT-compatible | No GPL/AGPL deps | License check in CI. |

---

## Unresolved Questions

- **UQ-1: Audit file rotation** — GB-sized `audit.jsonl` files are handled via seek-based pagination, but should Nautilus support log rotation (daily rollover, max file size)? If so, the audit viewer must discover and span multiple files. Recommend deferring rotation to Phase 5; seek-pagination handles the immediate scale concern.
- **UQ-2: Admin UI base path** — Fixed at `/admin/` or configurable via `nautilus.yaml`? Research assumes fixed. Configurable adds complexity for bookmark/URL stability. Recommend fixed.
- **UQ-3: SDK repository layout** — Monorepo workspace member (under `packages/nautilus-adapter-sdk/`) or separate repository? Monorepo simplifies drift-guard CI. Separate repo better models the third-party experience. Decide during design.
- **UQ-4: OTel trace_id in audit.jsonl** — Injecting `trace_id` into audit entries enables Loki-to-Tempo drill-down from audit log. Requires adding a field to `AuditEntry` (broker-side change). Recommend adding as optional field if backward-compatible.
- **UQ-5: CSS approach** — Custom `styles.css` (~200 lines) or vendored classless framework (e.g., Pico CSS)? Custom is smaller; Pico provides more polish with minimal effort. Decide during design.
- **UQ-6: InfluxDB version** — Target InfluxDB v2+ (Flux) only, or also support v1 (InfluxQL)? Research assumes v2+ only. Confirm.
- **UQ-7: S3-compatible stores** — Should `S3Adapter` explicitly support MinIO and other S3-compatible stores, or only AWS S3? `aiobotocore` works with any S3-compatible endpoint via `endpoint_url` config. Recommend documenting S3-compatible support.
- **UQ-8: Embedder Protocol in SDK** — SDK exports `Embedder` Protocol per AC-9.3. Confirm this is stable enough to publish (no embedder implementations exist in core-broker Phase 1; reasoning-engine may introduce one).

---

## Out of Scope

- Write endpoints in Admin UI (no config editing, rule editing, or source management through the UI)
- Real-time streaming audit viewer (operators search/filter, not watch live; SSE only for source status)
- Multi-tenant admin (single operator role, no RBAC)
- Custom CSS framework or JS build pipeline
- LLM-based features in Admin UI (no AI-assisted search or natural language filtering)
- Rule pack certification or compliance attestation (reference implementations only)
- Additional adapters beyond InfluxDB and S3 (e.g., Snowflake, BigQuery)
- SDK hosting infrastructure (PyPI publishing workflow is documented but not automated in this spec)
- Grafana alerting rules (dashboards only; operators configure alerts per their environment)
- Hot-reload of admin UI templates without restart
- Persistent audit index (seek-based pagination avoids needing a database index over JSONL)
- Admin UI i18n / l10n

---

## Dependencies

**On `core-broker`:**
- `Broker.sources` — source registry for status view
- `AuditEntry` model + `decode_nautilus_entry()` — audit viewer data source
- `Adapter` Protocol + Pydantic types — SDK extraction source
- `AttestationService` — attestation verification
- `proxy_trust_dependency` — admin auth
- `fastapi_app.py` app factory — admin router mount point

**On `reasoning-engine`:**
- Classification hierarchy — NIST/HIPAA packs depend on CUI/PHI hierarchies
- Cumulative exposure primitives — rule packs reference session exposure state
- Phase 2/3 `AuditEntry` fields (`event_type`, LLM metadata, handoff events) — admin UI must display these
- All 6+ adapter implementations — SDK extracts the stable Protocol surface after these exist

**Runtime dependencies (new in this phase):**
- `sse-starlette` — SSE for live source status
- `python-multipart` — form data parsing (FastAPI optional dep)
- `influxdb-client` — InfluxDB v2+ async client (for InfluxDB adapter)
- `aiobotocore` — async S3 client (for S3 adapter)

**Optional dependencies (new in this phase):**
- `opentelemetry-sdk`, `opentelemetry-api` — OTel core
- `opentelemetry-instrumentation-fastapi` — FastAPI auto-instrumentation
- `opentelemetry-exporter-otlp-proto-http` — OTLP exporter
- `prometheus-client` — `/metrics` endpoint

**Dev dependencies (new in this phase):**
- `locust` — load testing harness
- `mkdocs`, `mkdocs-material`, `mkdocstrings[python]` — SDK documentation
- `copier` — adapter scaffold template

---

## Success Criteria

- All 4 Admin UI views render against audit data generated by the existing broker pipeline with zero broker-side changes
- `docker-compose.otel.yml` stack shows populated Grafana dashboards after a benchmark run
- `nautilus-adapter-sdk` installable in a clean Python 3.11+ venv; compliance suite passes against all built-in adapters
- Both rule packs load via `Engine.load_pack()` and produce expected routing decisions against fixture facts
- InfluxDB and S3 adapters pass integration tests with testcontainers
- Benchmark harness produces a reproducible JSON report

---

## Glossary

- **Admin UI** — Read-only HTMX + Jinja2 web interface mounted at `/admin/` for operators to inspect source status, routing decisions, audit logs, and attestation tokens.
- **Seek-based pagination** — Pagination using file byte offsets as cursors instead of line numbers. Enables O(1) page access on large JSONL files.
- **Form-controller pattern** — HTMX pattern where a single `<form>` manages filter/sort/pagination state via hidden inputs. Server returns table body fragments.
- **HTMX fragment** — Partial HTML returned for `HX-Request: true` requests; swapped into the page without full reload.
- **SSE** — Server-Sent Events. Used for pushing source status updates to the Admin UI via `sse-starlette`.
- **OTel** — OpenTelemetry. Vendor-neutral observability framework for traces, metrics, and logs.
- **Span** — An OTel trace unit representing a single operation (e.g., `fathom_routing`, `adapter_fan_out`).
- **Adapter SDK** — `nautilus-adapter-sdk` PyPI package containing the Adapter Protocol, Pydantic types, and compliance test suite for third-party adapter authors.
- **Adapter Compliance Suite** — Pre-built pytest harness (`AdapterComplianceSuite`) that verifies an adapter satisfies the Protocol contract.
- **Drift-guard test** — CI test asserting structural equivalence between SDK-exported types and Nautilus-internal types. Prevents silent divergence without introducing a circular dependency.
- **Copier** — Python project scaffolding tool (preferred over Cookiecutter for `copier update` template sync).
- **Rule pack** — A set of YAML-defined Fathom rules in `templates/`, `modules/`, `rules/` subdirectories, distributed via `fathom.packs` entry point.
- **Salience band** — Numeric priority range controlling rule firing order in Fathom. Higher = fires first. Compliance denials: 170-190; scope constraints: 130-150; escalations: 110-120.
- **PHI** — Protected Health Information. The 18 HIPAA identifiers (name, SSN, DOB, etc.) that classify data as PHI.
- **CUI** — Controlled Unclassified Information. Federal designation with sub-categories (ITAR, EAR, FTI, LES).
- **Minimum necessary** — HIPAA standard requiring that PHI access be limited to the minimum needed for the stated purpose.
- **Proxy trust** — Auth mode where Nautilus trusts `X-Forwarded-User` header set by an upstream reverse proxy/SSO.
- **Distroless** — Docker image with no shell or package manager. Static files must be embedded in `package_data`.

---

## Next Steps

1. Resolve UQ-1 through UQ-8 during design review.
2. Produce `design.md` with module layout, template hierarchy, API route signatures, OTel instrumentation plan, SDK package structure, and rule pack YAML schemas.
3. Scaffold `nautilus/ui/` package with `templates/`, `static/`, and route modules.
4. Add runtime and optional dependencies via `uv`.
5. Implement in priority order: Admin UI views → OTel instrumentation → Grafana dashboards → SDK package → rule packs → ecosystem adapters → benchmarking.
