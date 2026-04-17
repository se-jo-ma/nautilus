# Research: operator-platform

## Executive Summary

Operator-platform is a read-only layer atop Nautilus's existing broker pipeline. All four workstreams — Admin UI, observability, adapter SDK, and compliance rule packs — are additive with zero broker-side changes. The Admin UI (HTMX + Jinja2 on FastAPI) mounts as an APIRouter under `/admin/`, reusing existing `proxy_trust` auth and `AuditEntry` models. OpenTelemetry instrumentation is hybrid: auto-instrument FastAPI HTTP, manually span broker pipeline stages, export to Grafana via Tempo/Prometheus/Loki. The adapter SDK extracts the stable Adapter Protocol + Pydantic types into a separate `nautilus-adapter-sdk` PyPI package with `pydantic>=2.0` as sole dependency. Compliance rule packs must define fresh rules against Nautilus templates (Fathom's built-in packs use incompatible template schemas).

## External Research

### Admin UI: HTMX + Jinja2 + FastAPI

**Architecture**: Full-page routes return documents extending `base.html`; HTMX-triggered routes return HTML fragments only, detected via `HX-Request` header. Same endpoint serves both.

**Data tables**: Form-controller pattern — a single `<form>` manages filter/sort/pagination state via hidden inputs. `hx-push-url="true"` enables bookmarkable URLs. `delay:500ms` debounces search. Server returns `<tbody>` fragments.

**Real-time**: SSE via `sse-starlette` + HTMX SSE extension for source status (push). Polling/manual refresh for audit log (operators search, not watch).

**Modals**: `hx-get` targeting a modal container div. Server returns complete modal HTML fragment. Vanilla JS `onclick` for close — no Hyperscript.

**Air-gap**: Vendor `htmx.min.js` (~14KB gzip) + `htmx-ext-sse.min.js` (~3KB) as static files. No CDN references. Custom `styles.css` (~200 lines).

**Template organization**:
```
nautilus/ui/templates/
├── base.html
├── layouts/dashboard.html
├── pages/{sources,decisions,audit,attestation}.html
├── partials/{source_card,decision_detail,audit_rows,audit_filters,attestation_result,pagination}.html
└── macros/table.html
```

**Dependencies**: `jinja2` (already transitive from FastAPI), `sse-starlette`, `python-multipart`. All pure Python, air-gap safe.

**Key risk**: Audit JSONL file size at scale. Need seek-based pagination or line-index caching for GB-sized files.

### Observability: OpenTelemetry + Grafana

**Hybrid instrumentation**: Auto-instrument FastAPI HTTP layer via `opentelemetry-instrumentation-fastapi` (v0.62b0, supports Python 3.14). Manually instrument broker pipeline stages:
1. `broker.request` — root business span
2. `intent_analysis` — child span
3. `fathom_routing` — child span (CLIPS evaluation)
4. `adapter_fan_out` — child span with per-source children
5. `synthesis`, `audit_emit`, `attestation_sign` — child spans

**Custom metrics** (6 counters + 3 histograms):
- `nautilus.requests.total` — total broker requests
- `nautilus.routing.decisions.total` — by source/action
- `nautilus.scope.denials.total` — by source/reason
- `nautilus.attestation.total` — by success/failure
- `nautilus.adapter.errors.total` — by type/source
- `nautilus.adapter.latency` — histogram, per-source
- `nautilus.request.duration` — histogram, end-to-end
- `nautilus.fathom.evaluation.duration` — histogram, CLIPS engine
- `nautilus.session.exposure_flags.total` — counter

**Exporters**: OTLP HTTP → Tempo (traces), Prometheus scrape `/metrics` (metrics), structured JSON logs with trace_id → Loki. Optional OTel Collector overlay for production.

**Dashboard provisioning**: Raw JSON models (3 dashboards: overview, adapters, attestation). Ship `docker-compose.otel.yml` with Grafana + Tempo + Prometheus + Loki.

**Benchmarking**: Keep existing in-process harness (`test_fastapi_latency_harness.py`). Add Locust-based load harness with `--otel` flag. JSON report output. Dockerized for reproducibility.

**Optional dependency**: `nautilus[otel]` keeps base install lean. `OTEL_SDK_DISABLED=true` makes SDK no-op for air-gap.

### Adapter SDK: Separate Package

**Package**: `nautilus-adapter-sdk` on PyPI. Sole runtime dep: `pydantic>=2.0`. Targets Python `>=3.11` (broader than Nautilus's `>=3.14`).

**Contents**: Adapter Protocol, Embedder Protocol, Pydantic types (IntentAnalysis, ScopeConstraint, AdapterResult, SourceConfig, ErrorRecord, AuthConfig variants, EndpointSpec), exception hierarchy, scope validators, `py.typed` marker.

**Plugin discovery**: `importlib.metadata` entry points under `nautilus.adapters` group, mirroring `fathom.packs` pattern. Broker merges static `ADAPTER_REGISTRY` with discovered entry points at startup.

**Testing**: `AdapterComplianceSuite` importable test harness (modeled on SQLAlchemy dialect compliance suite). Covers: connect/execute/close lifecycle, scope enforcement, idempotent close, error paths.

**Scaffold**: Copier template (not Cookiecutter) for new adapter projects. Supports `copier update` for template evolution.

**Documentation**: MkDocs + Material. "Write Your First Adapter" tutorial + API reference via `mkdocstrings`.

**No circular dep**: Nautilus keeps its own copy of types. CI drift-guard test asserts structural equivalence.

### Compliance Rule Packs

**Critical finding**: Fathom's built-in packs (nist-800-53, hipaa) use their own templates (`access_request`, `phi_policy`). Nautilus routing uses different templates (`agent`, `source`, `session`, `routing_decision`). These are **incompatible**. Nautilus packs must define fresh rules.

**data-routing-nist**: Maps NIST SP 800-53 controls to Nautilus routing. Key controls: AC-3 (access enforcement), AC-4 (information flow — primary), AC-6 (least privilege), AC-16 (security attributes), AC-21 (information sharing), AC-23 (data mining protection), SC-7 (boundary protection).

**data-routing-hipaa**: Maps HIPAA minimum necessary standard to scope constraints. PHI classification via 18 HIPAA identifiers as `data_types` tags. Role-based access restrictions per purpose (treatment, payment, operations). Breach detection via temporal operators.

**Salience bands**: Compliance denials 170-190, scope constraints 130-150, escalations 110-120 (fits between existing Nautilus bands).

**Distribution**: YAML files in `rule-packs/` directory. Registered via `fathom.packs` entry points in `pyproject.toml`. Each pack has `templates/`, `modules/`, `rules/`, optional `functions/` subdirectories.

**CUI gap**: Existing `cui-sub.yaml` covers 3 categories. NIST pack extends with ITAR, EAR, FTI, LES.

**PHI hierarchy**: de-identified → limited → standard → sensitive (mental health, substance abuse, HIV).

## Codebase Analysis

### Existing Patterns

| Pattern | Location | Relevance |
|---------|----------|-----------|
| FastAPI app factory | `nautilus/transport/fastapi_app.py` | Mount admin UI as additional router |
| Proxy trust auth | `nautilus/transport/auth.py` | `proxy_trust_dependency` reads X-Forwarded-User |
| Audit entry model | `nautilus/core/models.py::AuditEntry` | Pydantic model with all UI fields |
| JSONL round-trip | `nautilus/audit/logger.py::decode_nautilus_entry()` | Parses JSONL → AuditEntry |
| Source registry | `Broker.sources` / `GET /v1/sources` | Reuse for source status view |
| Attestation tokens | `AuditEntry.attestation_token` | EdDSA JWT for verification UI |
| Adapter Protocol | `nautilus/adapters/base.py` | 6 implementations, stable surface |
| Entry-point discovery | Fathom `fathom.packs` group | Pattern for adapter + rule pack discovery |
| Scope validators | `nautilus/adapters/base.py` | `validate_operator()`, `validate_field()`, `render_field()` |

### Audit Format (Critical for Admin UI)

Each JSONL line is a Fathom `AuditRecord` with `metadata["nautilus_audit_entry"]` containing the full `AuditEntry` JSON. Key fields:

| Field | Type | UI Use |
|-------|------|--------|
| `timestamp` | datetime (Z-suffix) | Sort/filter by time |
| `request_id` | UUID4 | Row ID, detail link |
| `agent_id` | str | Filter by agent |
| `routing_decisions` | list[RoutingDecision] | Sources selected/why |
| `scope_constraints` | list[ScopeConstraint] | Applied constraints |
| `denial_records` | list[DenialRecord] | Denied sources/reasons |
| `rule_trace` | list[str] | Fired rules |
| `attestation_token` | str\|None | JWT verification |
| `duration_ms` | int | Performance |
| `event_type` | str | Phase 2: handoff_declared |

Serialization uses `model_dump_json(by_alias=False)` with Z-suffix timestamp rewrite (AC-7.5).

### Dependencies

| Package | Purpose | Air-Gap |
|---------|---------|---------|
| `jinja2` | Templates (FastAPI transitive) | Yes |
| `sse-starlette` | SSE for live updates | Yes |
| `python-multipart` | Form data parsing | Yes |
| `opentelemetry-*` | OTel instrumentation (optional) | Yes |
| `prometheus-client` | Metrics export (optional) | Yes |
| `locust` | Benchmarking (dev only) | Yes |

### Constraints

1. Read-only: no write endpoints, no state mutation
2. Air-gap mandatory: every asset ships with package
3. Distroless Docker: static files in `package_data`
4. Audit JSONL double-parse: outer AuditRecord → inner AuditEntry
5. Python 3.14 for Nautilus, 3.11+ for SDK

## Related Specs

| Spec | Relevance | Relationship | May Need Update |
|------|-----------|--------------|-----------------|
| core-broker | High | Admin UI reads audit.jsonl + Broker.sources. SDK extracts types from core-broker. Rule packs consume core-broker templates. | false (read-only consumer) |
| reasoning-engine | High | Admin UI displays Phase 2/3 fields (LLM metadata, handoff events, classification escalation). Rule packs depend on classification hierarchy + cumulative exposure. | false (read-only consumer) |

## Quality Commands

| Type | Command | Source |
|------|---------|--------|
| Lint | `ruff check nautilus tests` | pyproject.toml [tool.ruff] |
| Format | `ruff format nautilus tests` | pyproject.toml [tool.ruff] |
| TypeCheck | `pyright` | pyproject.toml [tool.pyright] strict |
| Unit Test | `pytest -m unit` | pyproject.toml markers |
| Integration Test | `pytest -m integration` | pyproject.toml markers |
| All Tests | `pytest` | pyproject.toml [tool.pytest] |
| Build | `python -m build` or `uv build` | pyproject.toml [build-system] |
| Dev Server | `python -m nautilus serve --config nautilus.yaml --transport rest` | nautilus/cli.py |
| Health Check | `curl http://localhost:8000/healthz` | fastapi_app.py |
| Docker | `docker build -t nautilus:latest .` | Dockerfile |
| Local CI | `ruff check nautilus tests && pyright && pytest -m unit` | — |

## Feasibility Assessment

| Aspect | Assessment | Notes |
|--------|------------|-------|
| Admin UI | **High** / M effort / Low risk | All HTMX patterns well-documented. Read-only over existing data. Risk: JSONL file size. |
| OTel + Grafana | **High** / M effort / Low risk | Mature OTel Python SDK. Optional dependency. Risk: grafanalib incompatible (JSON only). |
| Adapter SDK | **High** / S effort / Low risk | Protocol stable (6 impls). Pydantic-only dep. Additive extraction. |
| Rule Packs (NIST) | **High** / M effort / Medium risk | Template incompatibility is solved. Risk: CUI hierarchy completeness, compliance accuracy. |
| Rule Packs (HIPAA) | **High** / M effort / Medium risk | Minimum necessary maps to scope_constraint. Risk: PHI field coverage per organization. |
| Benchmarking | **High** / S effort / Low risk | Existing harness extends naturally. Locust is standard. |
| New Adapters (InfluxDB, S3) | **High** / M effort / Low risk | Protocol well-defined. 6 reference implementations. |

**Overall**: High feasibility. ~30-35 tasks. No new architectural surfaces. Primary risks are JSONL scale and compliance rule accuracy.

## Recommendations for Requirements

1. **Admin UI**: Mount as FastAPI APIRouter under `/admin/`. Reuse `proxy_trust_dependency`. Form-controller pattern for all tables. Seek-based JSONL pagination. Vendor HTMX 2.0.x.
2. **OTel**: Hybrid instrumentation (auto HTTP + manual pipeline). Optional `nautilus[otel]` dep. `OTEL_SDK_DISABLED=true` for air-gap. Ship docker-compose.otel.yml.
3. **SDK**: Separate `nautilus-adapter-sdk` package. Python >=3.11. Copier template. AdapterComplianceSuite. MkDocs docs. CI drift-guard (no circular dep).
4. **Rule packs**: Fresh rules against Nautilus templates. Salience 110-190. YAML in rule-packs/. Entry-point registration. Compliance disclaimer. Extend CUI sub-hierarchy.
5. **Benchmarking**: Keep existing harness + add Locust load harness with OTel integration. JSON report. Dockerized.
6. **Adapters**: InfluxDB (measurement/tag scoping + time range enforcement). S3 (prefix/tag access + classification label filtering). Follow existing Protocol pattern.
7. **Grafana**: 3 raw JSON dashboards. Provisioning YAML for datasources. docker-compose overlay.

## Open Questions

1. **Audit file size**: Expected steady-state size? Log rotation support needed?
2. **Admin UI path**: Fixed `/admin/` or configurable via nautilus.yaml?
3. **SDK repo**: Monorepo workspace member or separate repository?
4. **SDK scope**: Include Embedder Protocol? Support sync adapters?
5. **SourceConfig.type**: Relax from Literal union to `str` in SDK for third-party adapters?
6. **OTel /metrics auth**: Require auth or rely on network isolation?
7. **Audit trace_id**: Inject OTel trace_id into audit.jsonl for Loki→Tempo drill-down?
8. **CSS framework**: Pure custom CSS or vendored classless CSS (e.g., Pico)?

## Sources

### Admin UI
- [TestDriven.io: HTMX + FastAPI](https://testdriven.io/blog/fastapi-htmx/)
- [HTMX SSE Extension](https://htmx.org/extensions/sse/)
- [HTMX Active Search](https://htmx.org/examples/active-search/)
- [HTMX Modal Dialogs](https://htmx.org/examples/modal-custom/)
- [sse-starlette](https://github.com/sysid/sse-starlette)
- [fastapi-htmx extension](https://github.com/maces/fastapi-htmx)

### OpenTelemetry
- [opentelemetry-instrumentation-fastapi](https://pypi.org/project/opentelemetry-instrumentation-fastapi/)
- [OTel Python SDK docs](https://opentelemetry-python.readthedocs.io/en/stable/)
- [OTel Python Exporters](https://opentelemetry.io/docs/languages/python/exporters/)
- [Full Stack Observability with Grafana](https://medium.com/@venkat65534/full-stack-observability-with-grafana-prometheus-loki-tempo-and-opentelemetry-90839113d17d)
- [Locust + OTel](https://www.locust.cloud/blog/observable-load-testing/)

### Adapter SDK
- [PEP 544 - Protocols](https://peps.python.org/pep-0544/)
- [PEP 561 - Type Distribution](https://peps.python.org/pep-0561/)
- [Python Packaging Guide - Plugins](https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/)
- [Airflow Custom Providers](https://airflow.apache.org/docs/apache-airflow-providers/howto/create-custom-providers.html)
- [Copier docs](https://copier.readthedocs.io/en/stable/)

### Compliance
- [NIST SP 800-53 Rev 5](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final)
- [HHS Minimum Necessary Guidance](https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/minimum-necessary-requirement/index.html)
- [18 HIPAA Identifiers](https://cphs.berkeley.edu/hipaa/hipaa18.html)
- [CUI Registry (NARA)](https://www.archives.gov/cui)
- [Kyverno Policy Library](https://kyverno.io/policies/)

### Codebase
- `nautilus/adapters/base.py` — Adapter Protocol
- `nautilus/core/models.py` — AuditEntry, IntentAnalysis, ScopeConstraint, AdapterResult
- `nautilus/audit/logger.py` — AuditLogger, JSONL serialization
- `nautilus/transport/fastapi_app.py` — FastAPI app factory, routes
- `nautilus/transport/auth.py` — API key + proxy trust auth
- `nautilus/config/models.py` — NautilusConfig, SourceConfig
- `nautilus/core/fathom_router.py` — Fathom integration, rule loading
- `nautilus/core/attestation_payload.py` — Ed25519 signing
