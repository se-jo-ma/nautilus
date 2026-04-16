---
spec: reasoning-engine
phase: requirements
created: 2026-04-15
---

# Requirements: Nautilus Reasoning Engine (Phase 2 + Phase 3 minus Admin UI)

## Overview

Nautilus Reasoning Engine completes the broker's reasoning surface and ships mainstream transport + adapter coverage on top of the Phase 1 `core-broker` foundation. It introduces classification hierarchy with rank-based dominance, cumulative exposure tracking backed by a Postgres-capable session store, classification escalation rules, cooperative cross-agent handoff detection with a forensic correlation fallback, purpose-bound temporal scoping, and a pluggable LLM-based intent analyzer with deterministic pattern fallback. Four new adapters (Elasticsearch, REST, Neo4j, ServiceNow) extend data-source coverage; a FastAPI REST endpoint and an MCP tool server expose the broker over network and tool-invocation surfaces; a new `nautilus` CLI + distroless Docker image make it deployable. Attestation gains a store-and-forward `AttestationSink` subsystem and a versioned `scope_hash_v2` payload format that preserves Phase 1 attestation-token verification unchanged.

All Phase 1 quality gates (≥80% branch coverage, pyright strict, operator-allowlist drift tests, air-gap posture) carry forward. Nothing in the request path requires external network when `--air-gapped` is set.

---

## In Scope

**Policy & Reasoning**
- Classification hierarchy (YAML-driven, rank-based) with sub-category hierarchies composed via two `fathom-dominates` calls.
- Cumulative exposure tracking — session-scoped working memory with a richer `session` template and a derived `session_exposure` fact template.
- Classification escalation rules — new `escalation_rule` template + `contains-all` CLIPS external.
- Cross-agent information flow — declarative `Broker.declare_handoff(...)` API plus a forensic audit-log correlation worker shipping with a Fathom rule pack.
- Purpose-bound temporal scoping — `expires_at` / `valid_from` slots on `scope_constraint`; broker-side filter with denial-record emission for dropped constraints.
- Agent registry (`agents:` top-level in `nautilus.yaml`).

**Intent Analysis**
- `LLMIntentProvider` Protocol + three providers (Anthropic, OpenAI, LocalInference OpenAI-compatible).
- `FallbackIntentAnalyzer` wrapper (LLM-primary, pattern-fallback).
- Pattern analyzer remains Phase 1 default and is forced under `--air-gapped`.

**Adapters**
- Elasticsearch adapter (`AsyncElasticsearch` + bundled DSL).
- REST API adapter (`httpx.AsyncClient` + per-source `EndpointSpec` allowlist).
- Neo4j adapter (official `neo4j>=5` async driver, `execute_query`).
- ServiceNow adapter (`httpx.AsyncClient` against Table API; encoded-query composition with `^`/OR sanitizer).

**Transport**
- FastAPI REST endpoint (`POST /v1/request`, `POST /v1/query` alias, `GET /v1/sources`, `GET /healthz`, `GET /readyz`).
- MCP tool server (stdio + streamable-http; `nautilus.request` tool; optional `nautilus.declare_handoff`).
- API-key auth (`X-API-Key`) by default; `proxy_trust` escape hatch.

**Attestation**
- `AttestationSink` Protocol + `NullAttestationSink` / `FileAttestationSink` / `HttpAttestationSink`.
- `scope_hash_v2` alongside v1; `AuditEntry.scope_hash_version` discriminator.
- Dispatch integrated into broker post-sign, audit-first ordering preserved.

**CLI & Packaging**
- `nautilus/cli.py` (stdlib `argparse`) with `serve`, `health`, `version` subcommands.
- Multi-stage distroless Docker image (`uv` builder → `gcr.io/distroless/cc-debian13` runtime).

---

## Out of Scope

- **Admin UI** (source status dashboard, routing decision viewer, audit viewer) — deferred to spec `operator-platform`.
- **Rule packs** (`data-routing-nist`, `data-routing-hipaa`) — deferred to `operator-platform`; this spec ships built-in rules only.
- **InfluxDB / S3 / document-store adapters** — deferred to `operator-platform`; Phase 2 adapter coverage limited to the four enumerated.
- **Custom adapter SDK + publication docs** — deferred to `operator-platform`; Phase 2 uses the internal `Adapter` Protocol only.
- **Grafana dashboard templates / benchmarking suite** — deferred to `operator-platform`; observability is per-audit-record only.
- **OAuth2 / OIDC for REST endpoint** — deferred to `operator-platform` (requires IdP incompatible with strict air-gap); Phase 2 ships API-key + `proxy_trust`.
- **Per-level compartments upstream in Fathom's `HierarchyDefinition`** — research open question 1 resolved: use two-hierarchy workaround; no upstream Fathom change in this spec.
- **Agent registry management UI** — `agents:` top-level lives in YAML; no CRUD UI in this spec (operator-platform concern).
- **Structured `broker.query(data_types, filters, context)` variant** — `/v1/query` ships as an alias of `/v1/request`; true query-style semantics deferred to a later phase.
- **Hot-reload of `nautilus.yaml`** — remains an operator restart concern (consistent with Phase 1).
- **Persistent LLM response caching** — out of scope; `FallbackIntentAnalyzer` is stateless between calls.

---

## User Stories

### US-1: Model Classification Hierarchy with Sub-Categories
**As a** security engineer
**I want to** declare a classification ladder plus optional sub-category ladders in YAML
**So that** rules can deny access using rank-based dominance covering both the top-level classification and a sub-category axis (e.g., `cui-sp-cti`).

**Acceptance Criteria:**
- **AC-1.1** — Given a `classification.yaml` under `nautilus/rules/hierarchies/` with `name: classification` and `levels: [unclassified, cui, confidential, secret, top-secret]`, when the broker starts, then the hierarchy is registered in Fathom's `_hierarchy_registry` and reachable from rules via `(fathom-dominates ?clearance ?subj_cmp ?src_cls ?src_cmp "classification")`.
- **AC-1.2** — Given a sibling `cui-sub.yaml` hierarchy file, when a source has `classification: cui` and `sub_category: cui-sp-cti`, then a default rule performs a second `fathom-dominates` call against the `cui-sub` ladder and denies when the agent's `sub_category` does not dominate the source's.
- **AC-1.3** — Given an agent whose `clearance` does not dominate the source's classification, when routed, then a `denial_record` with `rule_name = "default-classification-deny"` (salience 150) is produced and the source appears under `sources_denied`.
- **AC-1.4** — Given `source` and `agent` templates, when the broker boots, then both carry `compartments` (space-separated string) and `sub_category` (string, default "") slots fed from `SourceConfig` / `context["compartments"]`.
- **AC-1.5** — Given a custom hierarchy YAML dropped into an operator's `user_rules_dirs`, when the broker boots, then it is registered without code changes and a unit test demonstrates it firing from a user-authored rule.

---

### US-2: Persist Cumulative Exposure Across Requests in a Session Store
**As a** compliance officer
**I want** a session to accumulate what data types, sources, and PII categories an agent has touched
**So that** escalation rules can reason about aggregate exposure even after broker restart.

**Acceptance Criteria:**
- **AC-2.1** — Given `session_store.backend: memory`, when two requests share a `session_id`, then the second request's Fathom evaluation sees `session` facts populated from the first request's outcome (via a multislot containing `pii_sources_accessed`, `data_types_seen`, `sources_visited`).
- **AC-2.2** — Given `session_store.backend: postgres` and `session_store.dsn: ${NAUTILUS_SESSION_DSN}`, when the broker bootstraps, then it runs `CREATE TABLE IF NOT EXISTS nautilus_session_state (session_id TEXT PRIMARY KEY, state JSONB NOT NULL, updated_at TIMESTAMPTZ)` via `Broker.setup()` and subsequent requests upsert state per `session_id`.
- **AC-2.3** — Given `FathomRouter.route()` executes, when the session fact is asserted, then each multiset element also produces one `session_exposure` fact per entry so rules can pattern-match individual values.
- **AC-2.4** — Given a broker restart with Postgres backend, when a prior session_id's request arrives, then accumulated state is restored from Postgres and available to rules before `evaluate()` fires.
- **AC-2.5** — Given `session_store.backend: postgres` and the Postgres DSN is unreachable, when the operator sets `session_store.on_failure: fail_closed`, then `Broker.arequest` raises `SessionStoreUnavailableError` and the request is denied with an audit record; when set to `fallback_memory`, the broker degrades to `InMemorySessionStore` for the duration of the outage and emits a structured warning.

---

### US-3: Escalate Classification on Combinations of Unclassified Data
**As a** security engineer
**I want** rules that detect when an agent has accumulated a combination of data types that together reach a higher classification
**So that** PII-aggregation attacks are caught even when each individual value is unclassified.

**Acceptance Criteria:**
- **AC-3.1** — Given an `escalation_rule` template asserted with `trigger_combination: "email phone dob ssn"` and `resulting_level: confidential`, when the session's accumulated `data_types_seen` multislot contains all four tokens, then a `contains-all` external match fires and either a `denial_record` (action `deny`) or an escalated `scope_constraint` (action `escalate`) is produced.
- **AC-3.2** — Given a `config.rules.escalation_rules_dir` pointing at a directory with multiple YAML files, when the broker boots, then each file is parsed into `escalation_rule` facts asserted on every request.
- **AC-3.3** — Given a default escalation pack at `nautilus/rules/escalation/default.yaml` with the canonical PII-aggregation combination, when the broker boots, then it is loaded automatically and its rule fires end-to-end in the integration test.
- **AC-3.4** — Given `contains-all` is called with two multislots, when all elements of the first appear in the second (order-independent), then it returns `TRUE`; otherwise `FALSE`. Unit test covers both cases plus empty-set edge.
- **AC-3.5** — Given an `escalation_rule` with `action: notify`, when the rule fires, then a `denial_record`-shaped notify record is written to the audit entry but the source is NOT denied.

---

### US-4: Declare Cross-Agent Data Handoffs Cooperatively
**As an** orchestration developer
**I want** a public `Broker.declare_handoff(source_agent, receiving_agent, session_id, data_summary)` API
**So that** I can notify Nautilus when data passes between agents and get a policy decision without firing an adapter query.

**Acceptance Criteria:**
- **AC-4.1** — Given `Broker.declare_handoff(source_agent_id="a1", receiving_agent_id="a2", session_id="s1", data_classifications=["secret"], rule_trace_refs=[...])`, when called, then the broker asserts a `data_handoff` fact and runs a reasoning-only evaluation (zero adapter calls) returning a `HandoffDecision` with `action: allow | deny | escalate` and `denial_records`.
- **AC-4.2** — Given an `agents:` top-level block in `nautilus.yaml` mapping `id → {clearance, compartments, default_purpose}`, when `declare_handoff` runs, then the receiving agent's clearance is looked up from the registry (callers do not pass it explicitly).
- **AC-4.3** — Given a `data_handoff` fact where `from_agent_clearance` dominates `data_classification` but `to_agent_clearance` does not, when the `information-flow-violation` rule fires, then `HandoffDecision.action == "deny"` and a `denial_record` with `rule_name = "information-flow-violation"` is produced.
- **AC-4.4** — Every `declare_handoff` call produces exactly one audit entry with `event_type: "handoff_declared"` carrying the resulting `HandoffDecision`.
- **AC-4.5** — Given concurrent `declare_handoff` calls sharing `session_id`, when both complete, then both audit entries are written and each carries a stable `handoff_id` (UUIDv4) distinguishable in the audit log.

---

### US-5: Detect Undeclared Handoffs via Forensic Correlation
**As a** compliance officer
**I want** Nautilus to infer likely handoffs from the audit log even when no orchestrator called `declare_handoff`
**So that** undeclared information flow doesn't go undetected.

**Acceptance Criteria:**
- **AC-5.1** — Given a forensic correlation worker process (module `nautilus.forensics.handoff_worker`), when run against an audit log, then it emits `InferredHandoff` records (`session_id`, `source_agent`, `receiving_agent`, `confidence`, `signals`) to a configured sink.
- **AC-5.2** — Given a Fathom rule pack at `nautilus/rules/forensics/handoff.yaml` containing inference heuristics (shared session_id across different agent_ids within a window, overlapping `sources_queried`, classification delta), when the worker runs, then those rules produce `InferredHandoff` records.
- **AC-5.3** — Given a `declare_handoff` audit record exists for the same `(session_id, source_agent, receiving_agent)` tuple within the correlation window, when the worker runs, then the declared record takes precedence and no duplicate `InferredHandoff` is emitted.
- **AC-5.4** — Given the worker re-runs over an audit segment already processed, when it finishes, then no duplicate `InferredHandoff` records are produced for the same underlying audit-line hash (idempotency via processed-offsets file).
- **AC-5.5** — The worker runs entirely offline (reads audit files, writes forensic output) and requires no network, satisfying air-gap deployments.

---

### US-6: Analyze Intent with an LLM (Optional, Pluggable, Fallback-Protected)
**As an** operator running in a connected environment
**I want to** plug in an LLM-backed intent analyzer
**So that** I get richer entity extraction than regex while retaining deterministic pattern fallback on any LLM failure.

**Acceptance Criteria:**
- **AC-6.1** — Given `analysis.mode: llm-first` and `analysis.provider: anthropic` with `ANTHROPIC_API_KEY` set, when `broker.arequest(...)` runs, then `AnthropicProvider.analyze(...)` is invoked with tool-use binding to `IntentAnalysis.model_json_schema()` at `temperature: 0` and the parsed model is returned.
- **AC-6.2** — Given the LLM provider raises any of `TimeoutError`, `LLMProviderError`, `pydantic.ValidationError` within `analysis.timeout_s`, when analysis runs, then `FallbackIntentAnalyzer` silently delegates to `PatternMatchingIntentAnalyzer` and the request proceeds without failure.
- **AC-6.3** — Given `analysis.mode: llm-only` and provider unreachable, when analysis runs, then the request fails closed with a structured error and an audit record capturing the provider failure.
- **AC-6.4** — Given `nautilus serve --air-gapped`, when the CLI processes its config, then `analysis.mode` is forced to `pattern` regardless of YAML value and a WARN log names the overridden field.
- **AC-6.5** — Given any LLM analysis outcome (success or fallback), when the audit entry is written, then it includes `llm_provider`, `llm_model`, `llm_version`, `raw_response_hash`, `prompt_version`, `fallback_used: bool` fields; Phase 1 audit entries without these fields must continue to parse successfully.
- **AC-6.6** — Given the three providers (`AnthropicProvider`, `OpenAIProvider`, `LocalInferenceProvider`), when unit-tested with recorded fixtures, then each produces a valid `IntentAnalysis` against the locked `nautilus/analysis/llm/prompts/intent_v1.txt` prompt template.

---

### US-7: Enforce Purpose-Bound Temporal Scoping
**As a** security engineer
**I want** scope constraints to declare `expires_at` / `valid_from` time windows
**So that** a scope only applies within its declared purpose window and expired constraints are visibly dropped from the audit trail.

**Acceptance Criteria:**
- **AC-7.1** — Given `scope_constraint` template has optional `expires_at: string` and `valid_from: string` slots (ISO-8601; empty = no bound), when rules assert such a constraint, then the broker records both slots on the Pydantic `ScopeConstraint` model returned in `BrokerResponse`.
- **AC-7.2** — Given an `expires_at` in the past or a `valid_from` in the future relative to the request timestamp, when the broker processes scope constraints, then the constraint is dropped from adapter execution AND a `denial_record` with `rule_name = "scope-expired"` is emitted naming the dropped `(source_id, field, operator, value)`.
- **AC-7.3** — Given a session's `purpose_start_ts` plus `purpose_ttl_seconds` in the session fact, when `fathom-changed-within` detects the purpose is stale, then a `purpose-expired-deny` rule denies the request.
- **AC-7.4** — Given a `scope_constraint` with temporal slots, when the attestation `scope_hash` is computed, then version `v2` is used and `AuditEntry.scope_hash_version == "v2"`; given temporal slots are both empty, `scope_hash_v1` is used and `scope_hash_version == "v1"`.
- **AC-7.5** — Phase 1 attestation tokens (no temporal slots on any constraint) must verify unchanged under the Phase 2 broker — a recorded Phase-1 token fixture round-trips through the verifier in a unit test.

---

### US-8: Query Elasticsearch with Scope Enforcement
**As a** security engineer
**I want** Nautilus to scope Elasticsearch queries via parameterized DSL filters
**So that** agents cannot widen a search past their allowed index + field scope.

**Acceptance Criteria:**
- **AC-8.1** — Given a source with `type: elasticsearch` and `index: <name>`, when `connect()` runs, then `AsyncElasticsearch` is built with `basic_auth` / `api_key` / `ca_certs` from `SourceConfig.auth`; adapter refuses to connect if `index` is unset or fails regex `^[a-z0-9][a-z0-9._-]*$`.
- **AC-8.2** — Given scope constraints, when the adapter executes, then each operator in `_OPERATOR_ALLOWLIST` maps to the documented DSL object (`=`→`Term`, `!=`→`Bool(must_not=[Term])`, `IN`→`Terms`, `NOT IN`→`Bool(must_not=[Terms])`, `< > <= >=`→`Range`, `BETWEEN`→`Range(gte,lte)`, `LIKE`→`Wildcard` with `%→*` / `_→?`, `IS NULL`→`Bool(must_not=[Exists])`); unknown operator raises `ScopeEnforcementError` and the source lands in `sources_denied`.
- **AC-8.3** — Given a `LIKE` pattern with a leading wildcard, when the adapter runs, then it logs a structured WARN but proceeds (performance, not policy).
- **AC-8.4** — Given scope values, when the request is built, then they pass through DSL objects as Python values — never string-concatenated into query JSON. Static grep test forbids `f"..."` + `Search.query(` pairs inside the adapter module.
- **AC-8.5** — Integration test: given a `testcontainers`-booted Elasticsearch index with mixed documents, when a scoped query runs, then only documents matching the DSL filter appear; a drift-guard test asserts every operator in the allowlist round-trips.

---

### US-9: Query a REST API Through an Endpoint Allowlist
**As an** operator fronting an internal HTTP API
**I want** Nautilus to call only declared endpoints with declared parameter shapes
**So that** arbitrary URL construction and SSRF are impossible.

**Acceptance Criteria:**
- **AC-9.1** — Given `SourceConfig.endpoints: list[EndpointSpec]` (each with `path`, `method`, `path_params`, `query_params`, `operator_templates`), when `connect()` runs, then any scope constraint referring to an undeclared endpoint path raises `ScopeEnforcementError` at adapter load time.
- **AC-9.2** — Given `httpx.AsyncClient(base_url=source.connection, follow_redirects=False)`, when a query runs, then the adapter refuses any response redirecting to a different host and fails closed with `SSRFBlockedError`.
- **AC-9.3** — Given scope operators, when requests are built, then each operator serializes per the endpoint's `operator_templates` block (defaults: `=`→`?f=v`, `!=`→`?f__ne=v`, `IN`→repeated `?f=v1&f=v2`, `< > <= >=`→`?f__lt=v` etc., `BETWEEN`→paired `__gte/__lte`, `LIKE`→`?f__contains=v`, `IS NULL`→`?f__isnull=true`). `NOT IN` is rejected unless explicitly declared.
- **AC-9.4** — Given `auth: {type: bearer, token_env: X}`, when `connect()` runs, then the token is read once and set as the default `Authorization` header; `type: basic` / `mtls` / `none` are also supported.
- **AC-9.5** — Drift-guard test asserts every operator listed in `_OPERATOR_ALLOWLIST` either has a default template or is explicitly marked rejected; test fails loud on new operator addition to the allowlist.

---

### US-10: Query Neo4j with Scope-Enforced Cypher
**As a** security engineer
**I want** Cypher queries built from parameterized templates with a single allowlisted label per source
**So that** agents cannot pivot through the graph beyond their allowed neighborhood.

**Acceptance Criteria:**
- **AC-10.1** — Given a source with `type: neo4j` and `label: Person`, when `connect()` runs, then `label` is validated against `^[A-Z][A-Za-z0-9_]*$` and rendered backticked in all `MATCH` clauses; multi-label matching (`n:A:B`) is unreachable.
- **AC-10.2** — Given scope operators, when Cypher is built, then each operator maps to its documented form (`=`/`!=`/`IN`/`NOT IN`/`< > <= >=`/`BETWEEN`/`LIKE`/`IS NULL`) with property-name identifier-validated and backticked, values passed as `$p0..$pN` via `driver.execute_query(..., parameters_=dict)`.
- **AC-10.3** — Given `SourceConfig.like_style: "starts_with"` (default), when `LIKE` is used, then Cypher `STARTS WITH $p0` is emitted; given `like_style: "regex"`, `=~ $p0` is emitted (opt-in with a CONFIG WARN log).
- **AC-10.4** — Given `auth: (user, pw)` from env and URI `neo4j+s://...`, when `connect()` runs, then TLS is negotiated and a failed handshake lands the source in `sources_denied` without crashing the broker.
- **AC-10.5** — Integration test: given a `testcontainers`-booted Neo4j container with seeded `(:Person)` nodes, when a scoped query runs, then only nodes matching the WHERE filter are returned and `close()` is idempotent across repeated calls.

---

### US-11: Query ServiceNow via the Table API with Encoded-Query Sanitization
**As an** operator with a ServiceNow instance
**I want** Nautilus to compose `sysparm_query` encoded queries from scope constraints without exposing `^OR` injection
**So that** agent-visible ServiceNow records are narrowed, never widened.

**Acceptance Criteria:**
- **AC-11.1** — Given a source with `type: servicenow` and `table: incident`, when `connect()` runs, then `table` is validated against `^[a-z][a-z0-9_]*$`; `httpx.AsyncClient(base_url=source.connection)` is constructed with `auth` from `SourceConfig.auth`.
- **AC-11.2** — Given scope constraints, when the encoded query is built, then each operator maps to its GlideRecord form (`=`/`!=`/`IN`/`NOT IN`/`<`/`>`/`<=`/`>=`/`BETWEEN`/`LIKE`/`IS NULL`→`ISEMPTY`); composition uses `^` between clauses.
- **AC-11.3** — Given any scope value containing `^`, `\n`, or `\r`, when `_sanitize_sn_value` runs, then it raises `ScopeEnforcementError` and the source lands in `sources_denied`.
- **AC-11.4** — Given an `auth: {type: basic, ...}` or `{type: bearer, ...}`, when requests fire, then credentials are sent via the HTTP client's built-in mechanisms (no custom header concatenation); OAuth refresh flow is explicitly not supported.
- **AC-11.5** — Integration test (mocked via `respx` or `httpx.MockTransport` — ServiceNow has no testcontainer): full operator set round-trips through `sysparm_query` assembly and the sanitizer rejects malicious values in a dedicated injection test.

---

### US-12: Serve Broker Requests Over a FastAPI REST Endpoint
**As an** agent developer
**I want to** POST intents to Nautilus over HTTP
**So that** non-Python agents can consume the broker.

**Acceptance Criteria:**
- **AC-12.1** — Given `nautilus serve --transport rest --config ...`, when the process starts, then a FastAPI app exposes `POST /v1/request` (body `BrokerRequest{agent_id, intent, context}`), `POST /v1/query` (alias of `/v1/request`), `GET /v1/sources` (metadata, no secrets), `GET /healthz`, `GET /readyz`.
- **AC-12.2** — Given `config.api.keys: [${KEY1}, ${KEY2}]`, when a request arrives, then `APIKeyHeader(name="X-API-Key")` + `secrets.compare_digest` enforces one of the declared keys; missing/invalid key returns HTTP 401.
- **AC-12.3** — Given `config.api.auth.mode: proxy_trust`, when a request arrives with header `X-Forwarded-User`, then that header value is used as the authenticated identity (default mode is `api_key`; `proxy_trust` is opt-in).
- **AC-12.4** — Given FastAPI lifespan, when startup runs, then `broker = Broker.from_config(path)` is constructed once; `/readyz` returns 503 until startup completes and 200 afterwards; shutdown awaits `broker.aclose()`.
- **AC-12.5** — Given `POST /v1/request`, when the handler runs, then it calls `await app.state.broker.arequest(...)` directly — no `run_in_executor` and no bypass of the audit pipeline (verified by integration test asserting an audit line per HTTP request).
- **AC-12.6** — Given a p95 latency harness running 1 000 sequential `POST /v1/request` calls from a co-located loopback client against two testcontainer sources (pgvector + Postgres), when measured end-to-end over HTTP with the first 100 samples discarded as warm-up, then p95 computed over the remaining 900 samples is under 200 ms excluding adapter backend time.

---

### US-13: Serve Broker Requests Over MCP (stdio + HTTP)
**As an** MCP client
**I want** Nautilus to expose a tool that wraps `broker.arequest`
**So that** Claude Desktop, Cursor, and custom MCP clients can route intents through Nautilus policy.

**Acceptance Criteria:**
- **AC-13.1** — Given `nautilus serve --transport mcp --mcp-mode stdio`, when the process starts, then a `FastMCP` server exposes one tool `nautilus.request(agent_id: str, intent: str, context: dict[str, Any] = {}) -> BrokerResponse` with auto-generated JSON schema from Python type hints.
- **AC-13.2** — Given `--mcp-mode http --bind 0.0.0.0:8766`, when the server starts, then streamable-http transport runs with `stateless_http=True, json_response=True` and the same `APIKeyHeader` middleware as the REST surface.
- **AC-13.3** — Given a tool call, when `agent_id` is present in the arg, then it is used verbatim as the broker identity (never derived from MCP `client_id`); when `context["session_id"]` is unset, a session id derived from the MCP transport session (http) or request id (stdio) is used and the resolution is recorded in the audit entry.
- **AC-13.4** — Given the tool's return type is `BrokerResponse`, when invoked, then FastMCP auto-generates a structured-output schema from the Pydantic model; no custom schema is hand-written.
- **AC-13.5** — `nautilus serve --transport both` boots REST and MCP concurrently sharing one `Broker` singleton; both transports produce audit entries on the same sink.

---

### US-14: Dispatch Signed Attestation Payloads via a Pluggable Sink
**As a** compliance officer
**I want** signed attestation payloads to be emitted to a durable sink rather than just returned in the response
**So that** an external verifier can validate them asynchronously without blocking the broker.

**Acceptance Criteria:**
- **AC-14.1** — Given an `AttestationSink` Protocol (`async emit(payload)` / `async close()`), when the broker signs a response, then it calls `await sink.emit(AttestationPayload(token, nautilus_payload, emitted_at))` after `_sign` returns.
- **AC-14.2** — Given `config.attestation.sink.type: file` and `path: /audit/attestation.jsonl`, when a request completes, then the JSONL file gains one append-only line containing the signed token + deterministic payload; writes survive process crash (flush + fsync per entry).
- **AC-14.3** — Given `config.attestation.sink.type: http` and `url: https://verifier/...`, when a request completes, then `HttpAttestationSink` POSTs with configurable retry policy; on persistent failure the payload spills to a wrapped `FileAttestationSink` dead-letter path.
- **AC-14.4** — Given `NullAttestationSink` (default when no verifier configured), when a request completes, then the token is still signed and returned on `BrokerResponse.attestation_token` (Phase-1 behavior preserved).
- **AC-14.5** — Given sink `emit()` raises an exception, when the broker's hot path runs, then the exception is swallowed + logged WARN; the request response is unaffected and the audit record is still written (audit-first ordering preserved).
- **AC-14.6** — `Broker.aclose()` awaits `sink.close()` after the session store is flushed but before adapter pools are released.

---

### US-15: Boot Nautilus via a Command-Line Interface
**As an** operator
**I want** a `nautilus` CLI that launches the broker from a config file
**So that** Docker entrypoints, systemd units, and local dev share one invocation shape.

**Acceptance Criteria:**
- **AC-15.1** — Given `nautilus --help`, when invoked, then subcommands `serve`, `health`, `version` are listed and each subcommand has its own `--help`. Implementation uses stdlib `argparse`; no `click` / `typer` dependency.
- **AC-15.2** — Given `nautilus serve --config /config/nautilus.yaml --transport rest|mcp|both [--mcp-mode stdio|http] [--bind HOST:PORT] [--air-gapped]`, when run, then the specified transport(s) boot; `--air-gapped` forces `analysis.mode = pattern` and refuses any LLM provider config.
- **AC-15.3** — Given `nautilus health`, when run against a local `/readyz` endpoint, then it returns exit code 0 on 200 and non-zero otherwise, using only stdlib (`urllib.request`) so it runs under distroless without a shell.
- **AC-15.4** — Given `nautilus version`, when run, then it prints the package version from `importlib.metadata` and exits 0.
- **AC-15.5** — Given a missing or invalid config path, when `serve` runs, then a clear error with the path is printed and the process exits non-zero before any network bind.

---

### US-16: Ship a Distroless Docker Image
**As an** operator
**I want** an air-gap-friendly distroless image that runs `nautilus serve`
**So that** I can deploy without a shell, package manager, or outbound network at runtime.

**Acceptance Criteria:**
- **AC-16.1** — Given `docker build -t nautilus:x.y.z .`, when built, then a multi-stage Dockerfile produces a `gcr.io/distroless/cc-debian13`-based runtime image with the venv copied from a `ghcr.io/astral-sh/uv:python3.14-bookworm-slim` builder stage.
- **AC-16.2** — Given the built image, when `docker image inspect` reports its size, then uncompressed size is ≤200 MB.
- **AC-16.3** — Given `docker run -v ./nautilus.yaml:/config/nautilus.yaml:ro nautilus:x.y.z`, when executed, then `nautilus serve --config /config/nautilus.yaml` runs as the `ENTRYPOINT` and `POST /v1/request` end-to-end works against a backing Postgres.
- **AC-16.4** — Given the `HEALTHCHECK` directive, when Docker probes the container, then it invokes `["/app/.venv/bin/python", "-m", "nautilus", "health"]` (no curl, no shell).
- **AC-16.5** — Given the runtime image, when the container is inspected, then it contains no `apt`, `bash`, `sh`, or package manager; standard mount points `/config` (ro), `/rules` (ro), `/audit` (rw), `/keys` (ro) are documented in the image README.
- **AC-16.6** — An optional `-debug` image tag variant based on `python:3.14-slim + bash` is buildable from the same Dockerfile using `--target debug`; publication of the debug tag is explicitly deferred (see Open Questions).

---

## Functional Requirements

| ID | Requirement | User Story | Priority | How to Verify |
|----|-------------|------------|----------|---------------|
| FR-1 | Register `classification` and optional sub-category hierarchies from `nautilus/rules/hierarchies/*.yaml`; add `compartments` + `sub_category` slots to `source` and `agent` templates. | US-1 | High | Integration test: classified source denied for lower-clearance agent. |
| FR-2 | Ship default `default-classification-deny` rule (salience 150) invoking `fathom-dominates`. | US-1 | High | Rule-fire unit test. |
| FR-3 | Provide `SessionStore` Protocol (async) with `InMemorySessionStore` (default) and `PostgresSessionStore` implementations; the latter mirrors Phase 1 `PostgresAdapter` pool conventions. | US-2 | High | Unit test with mock store + integration test with testcontainers Postgres. |
| FR-4 | Implement `Broker.setup()` running `CREATE TABLE IF NOT EXISTS nautilus_session_state(...)` idempotently on first Postgres use. | US-2 | High | Integration test: run `setup()` twice, table exists, no error. |
| FR-5 | Session fact template extended with multislots `data_types_seen`, `sources_visited`, `pii_sources_accessed_list`; derive `session_exposure` facts per multiset element during `FathomRouter.route()`. | US-2, US-3 | High | Snapshot test of asserted facts. |
| FR-6 | Add `escalation_rule` template + `contains-all` CLIPS external (mirrors `overlaps` / `not-in-list` registration). Load escalation YAML files from `nautilus/rules/escalation/` + operator-specified dir. | US-3 | High | Unit + integration tests. |
| FR-7 | Ship a default escalation pack covering the PII-aggregation combination from design.md §Cumulative Exposure Tracking. | US-3 | Medium | Integration test fires the default rule. |
| FR-8 | Add `data_handoff` fact template and `Broker.declare_handoff(...)` public API returning `HandoffDecision`. | US-4 | High | Unit test for each of allow/deny/escalate paths. |
| FR-9 | Add `agents:` top-level in `NautilusConfig`; provide `AgentRegistry` with `get_agent(id) -> AgentRecord`. `declare_handoff` looks up `receiving_agent` clearance here. | US-4 | High | Unit test missing-agent path raises. |
| FR-10 | Ship `information-flow-violation` default rule comparing source vs. receiver clearance via `fathom-dominates`. | US-4 | High | Rule-fire test. |
| FR-11 | Implement `nautilus.forensics.handoff_worker` reading audit files, asserting into a Fathom engine loaded with `nautilus/rules/forensics/handoff.yaml`, emitting deduplicated `InferredHandoff` records. | US-5 | High | End-to-end test with synthetic audit log. |
| FR-12 | Ship forensic rule pack with session-overlap, source-overlap, and classification-delta heuristics producing confidence-scored handoffs. | US-5 | Medium | Rule-fire test per heuristic. |
| FR-13 | Define `LLMIntentProvider` Protocol + `AnthropicProvider`, `OpenAIProvider`, `LocalInferenceProvider` concrete implementations; each supports `health_check()`. | US-6 | High | Unit test with recorded fixtures per provider. |
| FR-14 | Implement `FallbackIntentAnalyzer(primary, fallback, timeout_s)` that catches `TimeoutError | LLMProviderError | pydantic.ValidationError` and delegates to pattern analyzer. | US-6 | High | Unit test simulates each failure mode. |
| FR-15 | Lock the prompt template at `nautilus/analysis/llm/prompts/intent_v1.txt`; `analysis.prompt_version` selects version. | US-6 | Medium | Prompt-content snapshot test. |
| FR-16 | Extend `AuditEntry` with `llm_provider`, `llm_model`, `llm_version`, `raw_response_hash`, `prompt_version`, `fallback_used`, `scope_hash_version` fields (all additive, non-breaking). | US-6, US-7 | High | Backwards-compat test: Phase 1 audit lines parse unchanged. |
| FR-17 | Add optional `expires_at` / `valid_from` slots to `scope_constraint` template and mirror on the Pydantic model; broker-side filter drops expired/not-yet-valid constraints and emits `scope-expired` denial records. | US-7 | High | Unit test each temporal branch. |
| FR-18 | Add `purpose_start_ts: float`, `purpose_ttl_seconds: int` slots to `session` template; ship `purpose-expired-deny` rule via `fathom-changed-within`. | US-7 | Medium | Integration test for TTL expiry. |
| FR-19 | Implement `scope_hash_v2` in `nautilus/core/attestation_payload.py` emitted when any constraint on the request has `expires_at` or `valid_from` set; v1 otherwise. `AuditEntry.scope_hash_version` records the choice. | US-7, US-14 | High | Backwards-compat test: Phase 1 token verifies unchanged. |
| FR-20 | `ElasticsearchAdapter` implementing Phase 1 `Adapter` Protocol, using `AsyncElasticsearch` + `elasticsearch.dsl.AsyncSearch.filter(...)`; operator-allowlist drift test. | US-8 | High | Integration test with testcontainers ES + drift test. |
| FR-21 | `RestAdapter` using `httpx.AsyncClient(follow_redirects=False)`; `SourceConfig.endpoints: list[EndpointSpec]` + `SourceConfig.auth: AuthConfig` discriminated union; operator-template drift test. | US-9 | High | Unit test with respx mock + drift test. |
| FR-22 | `Neo4jAdapter` using `AsyncGraphDatabase.driver` + `driver.execute_query(..., routing_=READ)`; label validated + backticked; drift test. | US-10 | High | Integration test with testcontainers Neo4j + drift test. |
| FR-23 | `ServiceNowAdapter` using `httpx.AsyncClient` against Table API + `_sanitize_sn_value` rejecting `^`, `\n`, `\r`; drift test. | US-11 | High | Unit test with respx mock + injection test. |
| FR-24 | Extend `SourceConfig` with additive `index`, `label`, `endpoints`, `auth` fields (non-breaking for Phase 1 YAML). | US-8, US-9, US-10, US-11 | High | Phase 1 YAML fixture still loads. |
| FR-25 | `nautilus.transport.rest.create_app(config_path)` returns a FastAPI app with lifespan-managed broker singleton, `POST /v1/request`, `POST /v1/query` (alias), `GET /v1/sources`, `GET /healthz`, `GET /readyz`. | US-12 | High | HTTP integration test via `httpx.AsyncClient` + TestClient. |
| FR-26 | `APIKeyHeader(name="X-API-Key")` + `secrets.compare_digest` auth (default); `proxy_trust` mode reads `X-Forwarded-User`. | US-12 | High | Auth unit tests covering both modes. |
| FR-27 | `nautilus.transport.mcp.create_server(config_path)` using FastMCP with `nautilus.request` tool; stdio + streamable-http transports; HTTP transport wrapped with API-key middleware. | US-13 | High | MCP integration test calling the tool. |
| FR-28 | `AttestationSink` Protocol + `NullAttestationSink`, `FileAttestationSink(path)`, `HttpAttestationSink(url, retry_policy)` implementations. | US-14 | High | Unit test each sink; integration test file + http paths. |
| FR-29 | Broker calls `await sink.emit(...)` post-`_sign`, swallowing exceptions with WARN log; `aclose()` awaits `sink.close()`. | US-14 | High | Unit test simulating sink failure. |
| FR-30 | `nautilus/cli.py` using stdlib `argparse` with subcommands `serve`, `health`, `version`; `serve` supports `--transport`, `--mcp-mode`, `--bind`, `--air-gapped`, `--config`. | US-15 | High | CLI unit tests + e2e smoke test. |
| FR-31 | Multi-stage Dockerfile (uv builder → distroless runtime); `HEALTHCHECK` invokes `nautilus health`; image ≤200 MB uncompressed. | US-16 | High | CI build + `docker image inspect` size check. |
| FR-32 | Optional `-debug` build target publishes on-demand (not default CI). | US-16 | Low | Build-test only. |
| FR-33 | Declared `data_handoff` within the correlation window takes precedence over forensic `InferredHandoff` records for the same tuple; processed-offsets file ensures idempotent re-runs. | US-4, US-5 | High | Integration test feeding declared + undeclared flows. |

---

## Non-Functional Requirements

| ID | Category | Metric | Target | Notes |
|----|----------|--------|--------|-------|
| NFR-1 | Air-gap compatibility | No outbound network in the request path when `--air-gapped` is set | 100% — verified by egress-block test on `nautilus serve --air-gapped` with LLM config present | CLI forces `analysis.mode = pattern`. |
| NFR-2 | Testability | Branch coverage on `nautilus/` package | ≥80% | Inherits Phase 1 gate; pytest-cov in CI. |
| NFR-3 | Type safety | Pyright strict clean on `nautilus/` + `tests/` | 0 errors, 0 warnings | Inherits Phase 1 gate. |
| NFR-4 | Security — operator allowlist | Drift test covering every operator for ES, REST, Neo4j, ServiceNow adapters | 100% of allowlist operators round-trip (or are explicitly marked rejected per-source for REST) | New drift tests extend Phase 1 pattern. |
| NFR-5 | Backwards compatibility — audit | Phase 1 `audit.jsonl` files parse under the Phase 2 `AuditEntry` schema | 100% — recorded Phase-1 fixture round-trips via `AuditEntry.model_validate_json()` | New fields all optional. |
| NFR-6 | Backwards compatibility — attestation | Phase 1 attestation tokens verify unchanged under Phase 2 verifier | 100% — recorded token fixture verifies | `scope_hash_v1` frozen. |
| NFR-7 | Session store degradation | If Postgres session store is unreachable, broker behavior is operator-chosen | `on_failure: fail_closed` denies with audit record; `on_failure: fallback_memory` degrades to in-memory with structured WARN | Unit test each policy. |
| NFR-8 | Performance — single-source latency | p95 end-to-end for a single-source request excluding adapter backend time | <200 ms | Measured via testcontainer harness. |
| NFR-9 | Performance — Fathom routing | p95 of `engine.evaluate()` in isolation | <5 ms for ≤20 sources / ≤30 rules (Phase 1 gate carried forward, rule count raised) | Bench test. |
| NFR-10 | Packaging | Docker image size (uncompressed, runtime stage) | ≤200 MB | `docker image inspect` in CI. |
| NFR-11 | Dependencies | New runtime deps: `fastapi>=0.115`, `uvicorn[standard]>=0.30`, `httpx>=0.27`, `elasticsearch>=8`, `neo4j>=5`, `mcp>=1.12`; optional `anthropic>=0.40`, `openai`. | Exact pins in `uv.lock`; no GPL/AGPL introduced | License check script. |
| NFR-12 | Determinism — LLM analysis | Given identical prompt + model snapshot, repeat analysis yields identical classification verdict and sensitivity level for ≥95 of 100 fixture prompts; the remaining ≤5 may differ only in optional explanatory / free-text fields, never in routing-relevant verdicts | Temperature 0; providers pinned by SDK version + model name | Property-style test with recorded fixtures. |
| NFR-13 | Determinism — forensic worker | Re-running the worker over the same audit segment yields zero duplicate `InferredHandoff` records | Processed-offsets file idempotency | Integration test. |
| NFR-14 | Concurrency — transports | REST and MCP `--transport both` share one `Broker` singleton; no duplicate `from_config` | 1 broker, ≥2 transport listeners | Process-inspection test. |
| NFR-15 | Observability — audit fidelity | Every HTTP and MCP request produces exactly one audit record | 1:1 ratio | Integration test counts entries. |
| NFR-16 | Attestation availability | `AttestationSink.emit` failure never fails a broker request | 0 requests aborted over a 1 000-request fault-injection run where the sink is forced to raise on 50% of emits (alternating success/failure) | Integration test. |
| NFR-17 | SSRF defense (REST) | Redirects to different hosts are refused | `follow_redirects=False` + explicit host check | Unit test. |
| NFR-18 | Encoded-query safety (ServiceNow) | `^`, `\n`, `\r` in scope values are rejected | 100% — injection test with adversarial values | Unit test. |

---

## Glossary

- **Classification rank** — Integer position of a level in `HierarchyDefinition.levels`; `fathom-dominates` uses `levels.index(...)` comparison.
- **Sub-category hierarchy** — Sibling hierarchy YAML (e.g., `cui-sub.yaml`) representing a second axis of classification under a top-level classification; queried by a second `fathom-dominates` call in the rule when needed.
- **Cumulative exposure** — Accumulated `(data_types_seen, sources_visited, pii_sources_accessed_list)` multislot state on a session fact, persisted between requests by `SessionStore` and re-asserted on each `route()`.
- **Session store** — Protocol abstraction over session-state persistence; Phase 2 ships `InMemorySessionStore` (default) and `PostgresSessionStore` (opt-in).
- **Handoff (declared)** — A policy decision requested explicitly via `Broker.declare_handoff(...)`; produces a `data_handoff` fact and `HandoffDecision`. Cooperative model.
- **Handoff (forensic)** — An `InferredHandoff` record emitted by the offline correlation worker when audit-log signals suggest a handoff occurred without a declaration. Never blocks a live request.
- **`scope_hash_v1`** — Phase 1 attestation hash over `(source_id, field, operator, value)` tuples. Frozen; all Phase 1 tokens verify under this version unchanged.
- **`scope_hash_v2`** — Phase 2 attestation hash including `expires_at` / `valid_from`. Emitted when any constraint on the request has temporal slots set; indicated by `AuditEntry.scope_hash_version`.
- **`AttestationSink`** — Protocol for durable, store-and-forward delivery of signed attestation payloads. Parallels `AuditSink`.
- **`LLMIntentProvider`** — Protocol returning `IntentAnalysis` from an intent string via an LLM; three concrete implementations ship.
- **`FallbackIntentAnalyzer`** — Composition wrapper that runs an `LLMIntentProvider` with a timeout + error safety net and delegates to `PatternMatchingIntentAnalyzer` on failure.
- **Forensic correlation worker** — Offline process that reads audit logs, asserts into a Fathom engine loaded with inference heuristics, and emits deduplicated `InferredHandoff` records.
- **Agent registry** — `agents:` top-level in `nautilus.yaml` mapping `agent_id` to clearance, compartments, and default purpose; used by `declare_handoff`.
- **`EndpointSpec`** — Per-source REST endpoint declaration: path template, method, `path_params` binding, `query_params` binding, `operator_templates`. Allowlisted; anything not declared is rejected.
- **`EncodedQuery`** — ServiceNow's `sysparm_query` clause-separated-by-`^` DSL. Nautilus composes it from scope constraints with a strict sanitizer.
- **Purpose-bound temporal scope** — Scope constraint with `expires_at` / `valid_from` slots; broker-side filter drops expired/not-yet-valid constraints with a `scope-expired` denial record.
- **Distroless image** — Google's minimal container image family with no shell/package-manager; Nautilus uses `gcr.io/distroless/cc-debian13` for its runtime stage.

---

## Dependencies & Assumptions

**Runtime dependencies (added in Phase 2):**
- `fastapi >= 0.115` — REST transport.
- `uvicorn[standard] >= 0.30` — ASGI server.
- `httpx >= 0.27` — REST + ServiceNow adapters, plus REST transport test client.
- `elasticsearch >= 8` — Elasticsearch adapter (async client + bundled DSL).
- `neo4j >= 5` — Neo4j adapter (async driver).
- `mcp >= 1.12` — MCP Python SDK (FastMCP, streamable-http transport).
- `anthropic >= 0.40` *(optional, extra `llm-anthropic`)* — Anthropic provider.
- `openai` *(optional, extra `llm-openai`)* — OpenAI + local-inference providers.
- `fathom-rules >= 0.3.0` — pinned; hierarchy registry, FactManager TTL, FactStore reference schema.

**Carried forward from Phase 1:**
- `asyncpg >= 0.30.0` (re-used by `PostgresSessionStore`).
- `pgvector`, `pyjwt`, `cryptography`, `pyyaml`, `pydantic` (all unchanged).

**Environment assumptions:**
- Python 3.14+.
- `uv` for dependency management.
- Docker available in CI for distroless image build + testcontainers-backed Elasticsearch / Neo4j / Postgres.
- Air-gapped deployments supply their own local OpenAI-compatible inference endpoint (vLLM, llama.cpp) if they want LLM analysis.

**Operational assumptions:**
- The agent registry (`agents:` in YAML) is authored by operators, not agents; it is trusted input.
- External verifiers for `HttpAttestationSink` are operator-owned; their failure modes are not modeled in the broker.
- Audit log retention / rotation for `FileAttestationSink` is an operator concern (same posture as Phase 1 `audit.jsonl`).

---

## Open Questions (flagged for design phase)

These are the five research open questions NOT resolved by the user interview; each carries a tentative answer to steer the design phase.

- **UQ-1: `PostgresSessionStore` schema migration ownership** *(research open Q#2)* — Tentative: add a `Broker.setup()` method that runs `CREATE TABLE IF NOT EXISTS` idempotently on first Postgres use (mirroring `PostgresFactStore._ensure_schema()`). Document the SQL so operators can pre-provision under strict RBAC instead. *(design to resolve)*
- **UQ-2: LLM determinism audit fields placement** *(research open Q#4)* — Tentative: audit fields land directly on `AuditEntry` as optional (`llm_provider`, `llm_model`, `llm_version`, `raw_response_hash`, `prompt_version`, `fallback_used`) — this is the approach taken in FR-16 to preserve Phase-1 line parseability. Alternative (sidecar `intent_analysis_trace` file) rejected pending design review of audit-canonicalization impact. *(design to resolve)*
- **UQ-3: `/v1/query` endpoint semantics** *(research open Q#6)* — Tentative: ship `/v1/query` as a literal alias of `/v1/request` in Phase 2 to reserve the URL; true query-style semantics (bypass intent analysis, accept structured `{data_types, filters}` input) defer to a later phase. Alternative: omit the endpoint until the split is real. *(design to resolve)*
- **UQ-4: MCP session identity binding** *(research open Q#7)* — Tentative: if `context["session_id"]` is absent, fall back to the MCP transport session id (streamable-http) or request id (stdio) and record the resolution in the audit entry. Alternative: require the caller to always supply `session_id` explicitly and 4xx on absence. *(design to resolve)*
- **UQ-5: Docker `-debug` image publication** *(research open Q#8)* — Tentative: the debug target builds from the same Dockerfile but is NOT published to the registry by default CI; operators can build locally. Alternative: publish `:x.y.z-debug` alongside `:x.y.z`. *(design to resolve)*

Research open Q#1 (per-level compartments) and Q#3 (cooperative vs forensic handoff) and Q#5 (scope-hash versioning) are resolved by the user interview and promoted to first-class requirements (US-1 / US-4+US-5 / US-7+US-14 respectively).

---

## References

- `./brief.md` — Charter, in/out scope, dependency-chain rationale, four research questions (all resolved).
- `./research.md` — Two-stream research covering all capabilities; 711 lines; settled decisions on session store, LLM provider abstraction, adapter library choices, transport shapes, image base.
- `../core-broker/design.md` — Phase 1 data model (`BrokerResponse`, `RoutingDecision`, `ScopeConstraint`, `ErrorRecord`, `IntentAnalysis`, `AuditEntry`); `Adapter` Protocol; `AuditSink` Protocol; attestation payload canonicalization.
- `../core-broker/requirements.md` — Reference format and structure; this document extends its audit, adapter, and session-store surfaces additively.
- `../../design.md` — Root product design (Classification Hierarchy, Cumulative Exposure Tracking, Deployment Models, Agent Interface).

---

## Next Steps

1. Produce `design.md` for `reasoning-engine` covering: hierarchy YAML + template extensions, `SessionStore` async Protocol + Postgres DDL, `data_handoff` template + registry + declare_handoff flow, forensic worker architecture, `LLMIntentProvider` Protocol + prompt template format, `scope_constraint` temporal slots + `scope_hash_v2` algorithm, `AttestationSink` Protocol + three sinks, four new adapters' module layouts, FastAPI app factory + lifespan, MCP server factory, CLI argparse schema, multi-stage Dockerfile.
2. Resolve UQ-1 through UQ-5 in design review.
3. Scaffold new subpackages: `nautilus/analysis/llm/`, `nautilus/forensics/`, `nautilus/transport/`, `nautilus/core/session_pg.py`, `nautilus/core/attestation_sink.py`, `nautilus/adapters/{elasticsearch,rest,neo4j,servicenow}.py`, `nautilus/cli.py`.
4. Add dependencies via `uv` with the `llm-anthropic`, `llm-openai` extras.
5. Implement in dependency order: template extensions → session store + agent registry → classification rules → escalation + handoff rules → LLM analyzer + fallback → temporal scoping + scope_hash_v2 → four adapters (drift-guard first) → attestation sink → REST transport → MCP transport → CLI → Dockerfile → forensic worker.
6. Gate: full Phase-1 test suite still green, plus new integration tests per adapter + transport. Phase-1 audit/attestation backwards-compat tests must pass before merge.
