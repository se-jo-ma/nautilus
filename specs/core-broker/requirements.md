---
spec: core-broker
phase: requirements
created: 2026-04-14
---

# Requirements: Nautilus Core Broker (Phase 1)

## Overview

Nautilus Core Broker is the Phase 1 deliverable of the Nautilus project: an intelligent data broker that sits between AI agents and data sources. Instead of giving agents direct database access, agents submit natural-language or structured intents to a `Broker`; the broker uses the Fathom rules engine to reason about which sources are relevant, whether the agent is authorized to see them, and what scope constraints apply. The broker then executes scoped queries against those sources in parallel, merges the results, writes an audit record, and returns a structured response with an attestation token.

Phase 1 ships a greenfield Python package (`nautilus`) with: a YAML source registry, a pattern-matching intent analyzer, Fathom integration that uses custom templates (`routing_decision`, `scope_constraint`, `denial_record`) as the source of truth, async PostgreSQL and pgvector adapters with safe scope enforcement, a basic synthesizer that structurally merges multi-source results, an append-only audit log built on Fathom's `AuditSink` protocol, a sync Python SDK with async adapter internals, and a test suite combining unit tests with `testcontainers`-backed integration tests against real PostgreSQL + pgvector. The end-to-end MVP success criterion is: an agent submits an intent, Fathom routes it to both a PostgreSQL and a pgvector source, scoped queries execute, a synthesized response is returned, and a complete audit entry is persisted.

---

## User Stories

### US-1: Configure a Source Registry
**As an** operator deploying Nautilus
**I want to** declare available data sources in a YAML file
**So that** the broker knows what sources exist, their classification, data types, allowed purposes, and connection details without hardcoding them.

**Acceptance Criteria (Given / When / Then):**
- **AC-1.1** — Given a `nautilus.yaml` with a `sources:` list containing `id`, `type`, `description`, `classification`, `data_types`, optional `allowed_purposes`, and `connection` fields, when `Broker.from_config("nautilus.yaml")` is called, then a `Broker` instance is returned with every source loaded and validated against a `SourceConfig` Pydantic model.
- **AC-1.2** — Given a `connection` value containing `${ENV_VAR}` placeholders, when the config is loaded, then environment-variable interpolation is performed and a missing required variable raises a clear `ConfigError` naming the variable and the source `id`.
- **AC-1.3** — Given a source with a duplicate `id` or an unknown `type`, when the config loads, then loading fails with a descriptive `ConfigError` before any network/DB connection is attempted.
- **AC-1.4** — Given a valid config, when `broker.sources` is inspected, then it exposes all registered sources with fields matching the YAML (verified via snapshot test).
- **AC-1.5** — Restarting the process re-reads `nautilus.yaml`; no in-process reload API is exposed in Phase 1 (verified by absence of a public reload method on `Broker`).

---

### US-2: Analyze Intent with Pattern Matching (Air-Gapped)
**As an** agent operating in an air-gapped environment
**I want to** submit a natural-language intent and have it deterministically parsed without calling any LLM
**So that** routing decisions remain reproducible, auditable, and do not require external network access.

**Acceptance Criteria:**
- **AC-2.1** — Given an intent string and a YAML-configured keyword→data-type mapping, when the pattern-matching analyzer runs, then it returns an `IntentAnalysis` Pydantic model with `raw_intent`, `data_types_needed: list[str]`, `entities: list[str]`, `temporal_scope: str | None`, and `estimated_sensitivity: str | None`.
- **AC-2.2** — Given an intent `"Find all known vulnerabilities, patches, and affected systems for CVE-2026-1234"`, when analyzed, then `data_types_needed` contains at least `["vulnerability", "patch", "asset"]` and `entities` contains `"CVE-2026-1234"` (extracted via regex for common identifier formats such as CVE IDs).
- **AC-2.3** — Given no keyword match, when analyzed, then `data_types_needed` is an empty list and routing proceeds with zero matched sources (not an error).
- **AC-2.4** — The analyzer conforms to an `IntentAnalyzer` Protocol (`analyze(intent: str, context: dict) -> IntentAnalysis`) so that Phase 3 can plug in an LLM-backed implementation without changing the broker.
- **AC-2.5** — Analysis is fully deterministic: the same input always produces the same `IntentAnalysis` (verified by property-style unit test).

---

### US-3: Route Requests via Fathom (Custom Templates)
**As a** security engineer
**I want** the broker to use Fathom rules to decide which sources are relevant and which are denied
**So that** routing and scoping decisions are deterministic, auditable, and driven by declarative policy.

**Acceptance Criteria:**
- **AC-3.1** — Given the broker is initialized, when it constructs its Fathom `Engine`, then it loads Nautilus-specific templates `routing_decision` (slots: `source_id`, `reason`), `scope_constraint` (slots: `source_id`, `field`, `operator`, `value`), and `denial_record` (slots: `source_id`, `reason`, `rule_name`).
- **AC-3.2** — Given an incoming request, when `broker.request(...)` executes, then the broker asserts facts for: `agent` (id, clearance, purpose), `intent` (data_types_needed, entities), each `source` from the registry, and any `session` state, then calls `engine.evaluate()`.
- **AC-3.3** — Given rules fire that select multiple sources, when the broker queries the `routing_decision` template after evaluation, then it retrieves every selected `source_id` (not just the last-write-wins `decision` field).
- **AC-3.4** — Given rules assert into `scope_constraint` or `denial_record`, when the broker queries those templates, then it retrieves the full scope list and denial list for the request.
- **AC-3.5** — Given any evaluation, the full `rule_trace` returned by Fathom is captured verbatim in the audit record for that request.
- **AC-3.6** — Built-in default rules ship under `nautilus/rules/` (subdirectories `templates/`, `modules/`, `rules/` following the Fathom convention) and are loaded automatically; user rules declared via `nautilus.yaml` layer on top without replacing built-ins.
- **AC-3.7** — Default rules include at minimum: (a) match-sources-by-data-type (intent.data_types overlaps source.data_types ⇒ assert `routing_decision`), (b) deny-purpose-mismatch (agent.purpose not in source.allowed_purposes ⇒ assert `denial_record`).

---

### US-4: Query PostgreSQL with Scope Enforcement
**As a** security engineer
**I want to** scope constraints produced by Fathom to be enforced on PostgreSQL queries via parameterized WHERE clauses
**So that** agents can never receive data outside their authorized scope, and the adapter is structurally immune to SQL injection.

**Acceptance Criteria:**
- **AC-4.1** — Given a `postgres` source, when the adapter executes a query, then it uses `asyncpg` with server-side parameterized queries only (`$1`, `$2`, …); no string interpolation of user-controlled values into SQL is permitted (verified by static grep + unit tests).
- **AC-4.2** — Given Fathom produced one or more `scope_constraint` facts for a source, when the adapter builds its query, then each constraint is appended as a parameterized `WHERE` clause with the declared `operator` (`=`, `IN`, `<`, `>`, `<=`, `>=`, `LIKE`).
- **AC-4.3** — Given an unknown or unsupported operator in a `scope_constraint`, when the adapter runs, then it raises `ScopeEnforcementError` and the source is reported under `sources_denied` rather than executed.
- **AC-4.4** — Given a connection failure or query error, when the adapter runs, then the error is captured, the source is reported under `sources_denied` (or `sources_errored`, implementation choice documented), and the overall request does not crash.
- **AC-4.5** — Connections are managed via an `asyncpg` connection pool owned by the adapter; `broker.close()` cleanly releases all pools.
- **AC-4.6** — Integration test: given a `testcontainers`-booted PostgreSQL with a seeded table, when a scoped query runs, then only rows matching the scope appear in the result (verified against both matching and non-matching rows).

---

### US-5: Query pgvector with Metadata Filtering
**As a** security engineer
**I want to** similarity search on a pgvector source to honor the same scope constraints as PostgreSQL
**So that** vector search results cannot leak data above an agent's clearance or outside its purpose.

**Acceptance Criteria:**
- **AC-5.1** — Given a `pgvector` source, when the adapter executes, then it performs a similarity query of the form `SELECT ... FROM <table> WHERE <scope filters> ORDER BY embedding <=> $N LIMIT $M` (or `<->` / `<#>` distance operator, configurable per source).
- **AC-5.2** — Given scope constraints apply to metadata columns (typically a JSONB `metadata` column), when the query runs, then metadata filters are applied via parameterized WHERE clauses **before** the similarity ordering.
- **AC-5.3** — Given an intent contains an embeddable query (or pre-computed embedding supplied in context), when the adapter runs, then it constructs the embedding input per the source config (Phase 1 may accept a pre-computed embedding; pluggable embedder is out of scope).
- **AC-5.4** — Top-K limit is configurable per-source in `nautilus.yaml` with a sane default (e.g., `top_k: 10`).
- **AC-5.5** — Integration test: given a `testcontainers`-booted PostgreSQL with the `pgvector` extension and seeded embeddings with metadata, when a scoped similarity query runs, then returned rows (a) match the metadata filter and (b) are ordered by similarity.

---

### US-6: Synthesize Multi-Source Results
**As an** agent
**I want** the broker to return a single merged response covering every successfully queried source
**So that** I don't need to know how many sources were involved or how to stitch their results together.

**Acceptance Criteria:**
- **AC-6.1** — Given results from N adapters, when the basic synthesizer runs, then it returns a structured dict mapping `{source_id: [rows...]}` preserving the per-source shape.
- **AC-6.2** — Given one or more adapters failed or were denied, when synthesis runs, then the response `data` still contains the successful sources and the failed/denied sources appear in `sources_denied` / `sources_skipped` / `sources_errored` — synthesis never raises on partial failure.
- **AC-6.3** — The synthesizer conforms to a `Synthesizer` Protocol so that Phase 2+ implementations (e.g., LLM summarization) can be swapped in.
- **AC-6.4** — Ordering: sources appear in the response in the order they completed (async) but the response also includes a stable `sources_queried: list[str]` list derived from `routing_decision` order.

---

### US-7: Persist a Complete Audit Record
**As a** compliance officer
**I want** every broker request to produce a structured, append-only audit record
**So that** I can reconstruct exactly which agent asked for what, what was decided, what was queried, and what was returned.

**Acceptance Criteria:**
- **AC-7.1** — Audit records are written via the Fathom `AuditSink` protocol; Nautilus ships a default `FileSink`-backed JSON-Lines implementation and accepts any compatible sink injected at construction.
- **AC-7.2** — Each `AuditEntry` (Pydantic model) contains at minimum: `timestamp` (UTC ISO8601), `request_id` (UUIDv4), `agent_id`, `session_id`, `raw_intent`, `intent_analysis`, `facts_asserted_summary`, `routing_decisions`, `scope_constraints`, `denial_records`, `rule_trace`, `sources_queried`, `sources_denied`, `sources_skipped`, `attestation_token` (nullable in Phase 1), `duration_ms`.
- **AC-7.3** — Writes are append-only; Nautilus never updates or deletes existing entries (verified by test that reads entries before and after a second request).
- **AC-7.4** — An audit record is written even when routing denies all sources, when an adapter fails, or when intent analysis yields zero data types.
- **AC-7.5** — Audit records are valid JSON per line and round-trip through `AuditEntry.model_validate_json()`.

---

### US-8: Submit Requests via the Python SDK
**As an** agent developer
**I want** a simple synchronous Python API that hides adapter concurrency
**So that** I can integrate Nautilus in any Python program without managing event loops.

**Acceptance Criteria:**
- **AC-8.1** — `Broker.from_config(path: str | Path) -> Broker` constructs a broker from a YAML file.
- **AC-8.2** — `broker.request(agent_id: str, intent: str, context: dict) -> BrokerResponse` is a synchronous call; it drives async adapters internally via `asyncio.run()` (or a managed event loop) and fans out via `asyncio.gather()` so multi-source queries execute concurrently.
- **AC-8.3** — `BrokerResponse` (Pydantic model) exposes: `data`, `sources_queried: list[str]`, `sources_denied: list[str]`, `sources_skipped: list[str]`, `scope_restrictions: dict[str, list[ScopeConstraint]]` (where `ScopeConstraint` is a Pydantic model of `{field, operator, value}`), `attestation_token: str | None`, `duration_ms: int`, `request_id: str`.
- **AC-8.4** — Session state (for Phase-2 cumulative exposure rules) is tracked in an in-memory `dict` scoped to the `Broker` instance, keyed by `context["session_id"]`; access is guarded by a `SessionStore` Protocol so Phase 2 can swap Redis/Postgres without API changes.
- **AC-8.5** — Calling `broker.request()` when already inside a running event loop raises a clear error pointing at a (documented) `broker.arequest()` async variant — OR the sync method safely runs via a helper such as `asyncio.run_coroutine_threadsafe` (implementation choice documented). Either way, nested event-loop misuse never silently deadlocks.
- **AC-8.6** — `broker.close()` is idempotent and cleanly releases all adapter resources.
- **AC-8.7** — Phase 1 exposes only `broker.request(agent_id, intent, context)`; the structured `broker.query(data_types, filters, context)` variant from design.md is deferred to Phase 2.

---

### US-9: Validate the Broker with a Test Suite
**As a** maintainer
**I want** a comprehensive pytest suite (unit + integration) shipped from day one
**So that** regressions are caught before release and contributors can verify changes quickly.

**Acceptance Criteria:**
- **AC-9.1** — Testing uses `pytest` + `pytest-asyncio`. Unit tests run without Docker and complete in under 30 seconds total on a developer laptop.
- **AC-9.2** — Integration tests use `testcontainers` to boot a real PostgreSQL image with the `pgvector` extension; the suite is marked (e.g., `@pytest.mark.integration`) and can be selected or skipped independently.
- **AC-9.3** — A single end-to-end MVP test exists that: (a) loads a fixture `nautilus.yaml` with exactly one `postgres` source and one `pgvector` source, (b) seeds both via testcontainers, (c) calls `broker.request()` with a realistic intent, (d) asserts `sources_queried == ["<pg>", "<pgv>"]`, (e) asserts `data` contains rows from both, (f) asserts an audit entry was written, (g) asserts `rule_trace` is non-empty.
- **AC-9.4** — Branch-coverage floor of 80% on the `nautilus/` package (measured by `pytest-cov`), with coverage reporting wired into the dev workflow.
- **AC-9.5** — Each component (source registry loader, intent analyzer, Fathom wiring, postgres adapter, pgvector adapter, synthesizer, audit log, broker) has at least one dedicated unit-test module under `tests/unit/`.

---

## Functional Requirements

| ID | Requirement | User Story | Priority | How to Verify |
|----|-------------|------------|----------|---------------|
| FR-1 | Load `nautilus.yaml` and validate every source against a `SourceConfig` Pydantic model. | US-1 | High | Unit test with valid + invalid YAML fixtures. |
| FR-2 | Interpolate `${ENV_VAR}` in `connection` strings; fail with descriptive error on missing vars. | US-1 | High | Unit test with env set / unset. |
| FR-3 | Provide `PatternMatchingIntentAnalyzer` implementing the `IntentAnalyzer` Protocol, with regex-based entity extraction (CVE IDs at minimum). | US-2 | High | Unit test against sample intents. |
| FR-4 | Register Nautilus-specific templates (`routing_decision`, `scope_constraint`, `denial_record`) on the Fathom `Engine` at broker construction. | US-3 | High | Inspect `engine.query(...)` after evaluate. |
| FR-5 | Ship built-in default rules under `nautilus/rules/` auto-loaded at startup; user rules layer on top via `nautilus.yaml`. | US-3 | High | Integration test with built-ins only, then with user-added rule. |
| FR-6 | After `engine.evaluate()`, query `routing_decision` / `scope_constraint` / `denial_record` templates to assemble the full routing table (do not rely on `EvaluationResult.decision`). | US-3 | High | Unit test with ≥3 matching sources. |
| FR-7 | Capture `rule_trace` from Fathom verbatim into the audit entry for every request. | US-3, US-7 | High | Unit test asserts trace list is persisted. |
| FR-8 | `PostgresAdapter` uses `asyncpg` with a connection pool and parameterized queries only; build WHERE clauses from `scope_constraint` facts. | US-4 | High | Static grep test + integration test against testcontainers PG. |
| FR-9 | `PgVectorAdapter` performs similarity search with metadata WHERE filters applied before `ORDER BY embedding <=>`. | US-5 | High | Integration test against testcontainers PG+pgvector. |
| FR-10 | `BasicSynthesizer` returns `{source_id: rows}` structurally; never raises on per-adapter failure. | US-6 | High | Unit test with one adapter raising. |
| FR-11 | Audit log writes append-only JSON Lines via a Fathom `AuditSink`; default implementation is a `FileSink`. | US-7 | High | Integration test reads the jsonl file after N requests. |
| FR-12 | `Broker.from_config()` and `broker.request()` constitute the sync public SDK; adapter fan-out uses `asyncio.gather()`. | US-8 | High | Unit test + e2e test. |
| FR-13 | `BrokerResponse` is a Pydantic model exposing `data`, `sources_queried`, `sources_denied`, `sources_skipped`, `scope_restrictions: dict[str, list[ScopeConstraint]]` (where `ScopeConstraint` is a Pydantic model of `{field, operator, value}`), `attestation_token`, `duration_ms`, `request_id`. | US-8 | High | Model snapshot test. |
| FR-14 | Session state is an in-memory dict keyed by `session_id`, accessed through a `SessionStore` Protocol. | US-8 | Medium | Unit test injects a mock store. |
| FR-15 | Dedicated pytest markers separate `unit` and `integration` tests; integration uses `testcontainers`. | US-9 | High | `pytest -m unit` and `pytest -m integration` both run. |
| FR-16 | End-to-end MVP test covers PG + pgvector success path with audit assertion. | US-9 | High | The e2e test exists and passes. |
| FR-17 | `broker.close()` releases all adapter resources idempotently. | US-4, US-5, US-8 | Medium | Unit test calls `close()` twice. |
| FR-18 | Adapter errors degrade gracefully: failing source reported in response; other sources proceed. | US-4, US-5, US-6 | High | Unit test with one adapter raising. |

---

## Non-Functional Requirements

| ID | Category | Metric | Target | Notes |
|----|----------|--------|--------|-------|
| NFR-1 | Performance — Fathom routing | p95 latency of `engine.evaluate()` per request in isolation | < 5 ms for ≤ 20 sources / ≤ 10 default rules | Fathom measured ~15 µs per evaluation; 5 ms gives ample headroom. |
| NFR-2 | Performance — end-to-end | p95 latency of `broker.request()` against 2 local testcontainer sources | < 250 ms | Measured in the e2e test on dev hardware; informational, not a gate. |
| NFR-3 | Concurrency | Multi-source queries execute concurrently, not serially | 2 sources must overlap by ≥ 50% of their duration (verified via sleep-instrumented test adapter) | Enforces `asyncio.gather()` fan-out. |
| NFR-4 | Security — SQL | Zero string interpolation of user-controlled values into SQL | 100% of DB calls use parameterized queries | Static grep test forbids `f"..."` + `execute(`; code review. |
| NFR-5 | Security — config | Missing required env vars fail fast at config load | No `None`/empty connection strings reach adapters | Unit test. |
| NFR-6 | Testability | Branch coverage on `nautilus/` package | ≥ 80% | `pytest-cov` in CI. |
| NFR-7 | Testability | Unit-only test suite completes without Docker | `pytest -m unit` passes with no network access | CI job runs offline unit tier. |
| NFR-8 | Observability — audit | Every request, successful or not, produces exactly one audit record | 1:1 request→entry ratio | Integration test counts entries. |
| NFR-9 | Observability — tracing | `rule_trace` preserved on every audit record | 100% of audit entries include non-null `rule_trace` list | Integration test. |
| NFR-10 | Packaging | Single-command install via `uv add nautilus-broker` (or `uv sync` for source) | Works on Python 3.14+ on Linux and Windows | CI matrix. |
| NFR-11 | Dependencies | New runtime deps limited to `asyncpg`, `pgvector`; new dev deps `pytest`, `pytest-asyncio`, `pytest-cov`, `testcontainers` | No unapproved transitive surprises | `uv.lock` reviewed. |
| NFR-12 | License | All Nautilus source files compatible with MIT | No GPL/AGPL deps introduced | License check script. |
| NFR-13 | Determinism — intent analysis | Same input always yields the same `IntentAnalysis` | Property test: 100 random inputs × 5 repeats | Unit test. |
| NFR-14 | Determinism — routing | Given identical facts + rules, Fathom returns identical `rule_trace` | Property test | Unit test. |
| NFR-15 | Air-gap compatibility | Phase 1 runs with no outbound network calls apart from configured data sources | Egress test blocks all other traffic | Manual verification during e2e test. |

---

## Unresolved Questions

- **UQ-1: Top-level project structure** — `nautilus/core/`, `nautilus/adapters/`, `nautilus/analysis/`, `nautilus/config/` are research recommendations; confirm final layout in design phase.
- **UQ-2: Attestation in Phase 1** — design.md lists attestation under Phase 2, but Fathom's `AttestationService` is freely available. Decision: Phase 1 captures `attestation_token` as optional (may be `None`); full integration lands in Phase 2. Confirm during design.
- **UQ-3: pgvector embedding source** — Phase 1 accepts pre-computed embeddings supplied in `context` or a per-source static query vector; a pluggable embedder is Phase 3. Confirm no embedding model ships in Phase 1.
- **UQ-4: Nested event-loop handling** — `broker.request()` is sync but consumers may already be inside an event loop (e.g., FastAPI handlers). Choose between (a) raising with a pointer to a sibling `arequest()` coroutine or (b) using `asyncio.run_coroutine_threadsafe`. Decide in design.
- **UQ-5: "sources_errored" vs "sources_denied"** — when an adapter raises at runtime (not a policy denial), should the source land in `sources_denied` or a new `sources_errored` field? Recommend a distinct field for clarity; confirm in design.
- **UQ-6: Scope-constraint operator allowlist** — FR-8 lists `=`, `IN`, `<`, `>`, `<=`, `>=`, `LIKE`. Confirm set (and whether `BETWEEN`, `IS NULL`, `NOT IN` are included in Phase 1).
- **UQ-7: Default rule content** — design.md shows example rules using pseudo-DSL (`below(...)`, `overlaps(...)`). Phase 1 default rules must use actual Fathom YAML syntax with built-ins such as `fathom-dominates`. Map pseudo-DSL → real Fathom expressions during design.

---

## Out of Scope (Phase 2+)

- LLM-based intent analyzer (Phase 3)
- REST API / FastAPI server (Phase 2)
- MCP tool server integration (Phase 2)
- Docker container image & `nautilus serve` CLI (Phase 2)
- Full classification hierarchy support + `classification.yaml` (Phase 2)
- Cumulative exposure escalation rules and cross-session state (Phase 2)
- Classification-escalation rules / information-flow-violation rules (Phase 3)
- Cross-agent information-flow tracking (Phase 3)
- Admin UI (source status, routing decisions, audit viewer) (Phase 3)
- Additional adapters: Elasticsearch, REST API, Neo4j, ServiceNow, InfluxDB, S3/documents (Phase 2–4)
- Custom adapter SDK + documentation (Phase 4)
- Rule packs: `data-routing-nist`, `data-routing-hipaa` (Phase 4); Phase 1 ships built-in rules inline, NOT as a separate Fathom rule pack.
- Grafana dashboards / benchmarking suite (Phase 4)
- Hot-reload of `nautilus.yaml` without restart (explicitly deferred)
- Persistent / distributed `SessionStore` backends (Redis, Postgres) — Phase 1 defines the Protocol but only ships the in-memory implementation.
- Structured `broker.query()` variant (skip intent analysis) — Phase 2

---

## Dependencies & Assumptions

**Runtime dependencies (added in Phase 1):**
- `fathom-rules >= 0.1.0` — already present; provides `Engine`, templates, `AuditSink`, `AttestationService`, and transitive `pydantic`, `PyYAML`, `clipspy`, `PyJWT`, `cryptography`.
- `asyncpg` — async PostgreSQL driver with server-side parameterized queries.
- `pgvector` (Python client) — pgvector type adapters for asyncpg.

**Dev dependencies:**
- `pytest`, `pytest-asyncio`, `pytest-cov`, `testcontainers`, and a linter (recommended: `ruff`).

**Environment assumptions:**
- Python 3.14 or newer.
- `uv` as package manager.
- Docker available on developer machines and CI for integration tests (unit-only tier runs without Docker).
- PostgreSQL with the `pgvector` extension available in integration environments (supplied via testcontainers).

**API-stability assumptions:**
- The Fathom 0.1.0 public API (`Engine`, templates, `assert_fact(s)`, `evaluate`, `query`, `rule_trace`, `AuditSink`) is stable for the Phase 1 timeline.
- CLIPS metadata slot string handling is lossy for embedded JSON → Nautilus uses separate fact slots for structured data, never JSON-in-metadata.

**Operational assumptions:**
- Rules authored by users are trusted input (authored by operators, not agents).
- Source connection credentials arrive via environment variables, not checked-in config.

---

## Glossary

- **Agent** — The AI system submitting requests; identified by `agent_id` and carries `clearance` and `purpose` in `context`.
- **Intent** — A natural-language or structured statement of what data an agent needs, submitted via `broker.request()` or `broker.query()`.
- **Intent Analysis** — Structured metadata (`data_types_needed`, `entities`, `temporal_scope`, `estimated_sensitivity`) extracted from an intent; in Phase 1 via pattern matching.
- **Source** — A data system (PostgreSQL table, pgvector collection, etc.) registered in `nautilus.yaml` with `id`, `type`, `classification`, `data_types`, and `allowed_purposes`.
- **Source Registry** — The in-memory catalog of configured sources loaded from `nautilus.yaml`.
- **Routing Decision** — A fact asserted into the `routing_decision` template by a Fathom rule, selecting a source for the request.
- **Scope Constraint** — A fact asserted into the `scope_constraint` template that narrows what can be returned from a given source (e.g., `classification = 'cui'`). Also represented in the SDK as a **Scope Constraint (model)** — a Pydantic model `{field: str, operator: str, value: Any}` representing one narrowing predicate applied to a source's query.
- **Denial Record** — A fact asserted into the `denial_record` template that explicitly excludes a source with a reason.
- **Adapter** — A per-source-type plugin (`PostgresAdapter`, `PgVectorAdapter`) that connects to a source and executes scoped queries.
- **Scope Enforcement** — The act of translating `scope_constraint` facts into parameterized query modifications (WHERE clauses, metadata filters).
- **Synthesizer** — The component that merges per-adapter results into a single `BrokerResponse.data` structure.
- **Audit Sink** — Fathom's protocol for structured audit output; Nautilus uses the same protocol and ships a JSON-Lines `FileSink` default.
- **Audit Entry** — A single append-only JSON record describing one broker request.
- **Attestation Token** — An Ed25519-signed JWT produced by Fathom's `AttestationService` proving the response was policy-checked (optional / nullable in Phase 1).
- **Session** — A logical grouping of requests by `session_id` used for cumulative-exposure reasoning; Phase 1 stores session state in an in-memory dict per `Broker` instance.
- **Session Store** — Protocol over session state; Phase 1 ships the in-memory backend; Phase 2 can add Redis/Postgres.
- **Cumulative Exposure** — The tracked history of what data classes/sources an agent has accessed across a session; underpinning capability for Phase 2 escalation rules.
- **Rule Trace** — The ordered list of Fathom rule names that fired during an evaluation; captured verbatim in every audit entry.

---

## Next Steps

1. Produce `design.md` in the `core-broker` spec (module layout, public types, Fathom YAML for `routing_decision` / `scope_constraint` / `denial_record`, default-rule authoring, adapter base class).
2. Resolve Unresolved Questions UQ-1 through UQ-7 during design review.
3. Scaffold the `nautilus/` package with `core/`, `adapters/`, `analysis/`, `config/`, `rules/` subpackages plus `tests/unit/` and `tests/integration/`.
4. Add runtime (`asyncpg`, `pgvector`) and dev (`pytest`, `pytest-asyncio`, `pytest-cov`, `testcontainers`) dependencies via `uv`.
5. Implement in dependency order: config & registry → intent analyzer → Fathom wiring → adapters → synthesizer → audit → broker facade → e2e MVP test.
6. Ship the MVP e2e test (US-9 / AC-9.3) as the first integration test and use it as the gate for "Phase 1 done".
