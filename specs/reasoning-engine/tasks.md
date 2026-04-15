---
spec: reasoning-engine
phase: tasks
created: 2026-04-15
upstream: design.md
depends-on: core-broker
granularity: fine
total_tasks: 79
---

# Tasks: reasoning-engine

## Overview

This breakdown translates the 14-step build order in design §9 into 76 atomic tasks across five POC-first phases. Phase 1 (15 tasks) drives the POC milestone: a single `POST /v1/request` that runs classification rules → escalation rule → pattern-matcher (LLM-absent) intent analysis → temporal scope → pgvector adapter → `scope_hash_v2` emission → Ed25519 attestation token, against Postgres + pgvector testcontainers. Phase 2 (28 tasks) adds the remaining components in design-§9 order: LLM provider matrix, three remaining adapters, MCP transport, CLI, Dockerfile, forensic worker. Phase 3 (17 tasks) adds the §7 integration harnesses (drift-guard, determinism, latency, fault-injection, forensic idempotency, Phase-1 backwards-compat). Phase 4 (11 tasks) runs the full quality gate: pyright-strict, coverage ≥80%, license check, docs, PR lifecycle. Phase 5 (5 tasks) exercises the full pipeline end-to-end including forensic worker via VE1/VE2a/VE2b/VE2c/VE3. Quality `[VERIFY]` checkpoints run every 2–3 tasks throughout; each runs `uv run ruff check && uv run ruff format --check && uv run pyright src/ tests/ && uv run pytest -m unit`.

Every implementation task cites the `FR-N` / `US-N` / `NFR-N` / `AC-N.M` / `D-N` that it traces to. Phase-1-POC closes at Task 1.15 with the milestone integration test. All Phase 1 surfaces (`core-broker` spec, 59 tasks, already merged) remain green throughout — no refactor of that surface is permitted.

---

## Phase 1: POC — reasoning-engine end-to-end through one adapter and pattern fallback

Focus: Prove the new pipeline wires up. Ships classification + escalation + temporal + attestation dispatch + `scope_hash_v2` against pgvector. LLM providers and 3 remaining adapters deferred to Phase 2.

### Task 1.1 [x] — Scaffold new reasoning-engine subpackages
- **Do**:
  - Create empty `__init__.py` in each of: `nautilus/analysis/llm/`, `nautilus/analysis/llm/prompts/`, `nautilus/forensics/`, `nautilus/transport/`, `nautilus/rules/hierarchies/`, `nautilus/rules/escalation/`, `nautilus/rules/forensics/`.
  - Create empty test dirs: `tests/unit/analysis/llm/`, `tests/unit/adapters/`, `tests/unit/config/`, `tests/unit/core/`, `tests/unit/forensics/`, `tests/unit/rules/`, `tests/unit/transport/`, `tests/fixtures/llm/`, `tests/fixtures/llm_determinism/`, `tests/fixtures/audit/` (each with `__init__.py` where applicable).
- **Files**: 7 new package `__init__.py` + 8 new test-dir `__init__.py` per design §5.
- **Done when**: `python -c "import nautilus.analysis.llm, nautilus.forensics, nautilus.transport"` succeeds.
- **Verify**: `uv run python -c "import nautilus.analysis.llm, nautilus.forensics, nautilus.transport; print('OK')"`
- **Commit**: `chore(scaffold): create reasoning-engine subpackage skeleton`
- **References**: design §5 file tree.

### Task 1.2 [x] — Extend `pyproject.toml` with Phase 2 deps + extras
- **Do**:
  - Add runtime deps to `[project].dependencies`: `fastapi>=0.115`, `uvicorn[standard]>=0.30`, `httpx>=0.27`, `elasticsearch>=8`, `neo4j>=5`, `mcp>=1.12`.
  - Add optional extras to `[project.optional-dependencies]`: `llm-anthropic = ["anthropic>=0.40"]`, `llm-openai = ["openai"]`.
  - Extend `dev` extra with `respx>=0.21`, `pytest-recording>=0.13`, `testcontainers[elasticsearch,neo4j]>=4.0`.
  - Run `uv sync --extra dev --extra llm-anthropic --extra llm-openai`.
- **Files**: `pyproject.toml`, `uv.lock`.
- **Done when**: `uv sync --extra dev --extra llm-anthropic --extra llm-openai` resolves; `uv run python -c "import fastapi, httpx, elasticsearch, neo4j, mcp, respx"` succeeds.
- **Verify**: `uv sync --extra dev --extra llm-anthropic --extra llm-openai && uv run python -c "import fastapi, httpx, elasticsearch, neo4j, mcp, respx; print('deps ok')"`
- **Commit**: `chore(tooling): add reasoning-engine runtime + dev deps, LLM extras`
- **References**: NFR-11, design §5 pyproject edits.

### Task 1.3 [x] — Extend `SourceConfig`, `NautilusConfig` with additive Phase 2 fields
- **Do**:
  - Edit `nautilus/config/models.py`:
    - Add to `SourceConfig`: `index: str | None = None`, `label: str | None = None`, `endpoints: list[EndpointSpec] | None = None`, `auth: AuthConfig | None = None`, `compartments: str = ""`, `sub_category: str = ""`, `like_style: Literal["starts_with","regex"] = "starts_with"`.
    - Add new models `EndpointSpec(path, method, path_params, query_params, operator_templates)` and `AuthConfig` (discriminated union: `BearerAuth | BasicAuth | MtlsAuth | NoneAuth` on `type: Literal["bearer","basic","mtls","none"]`).
    - Add new model `AgentRecord(id, clearance, compartments: list[str] = [], default_purpose: str | None = None)`.
    - Add to `NautilusConfig`: `agents: dict[str, AgentRecord] = {}`, `api: ApiConfig = ApiConfig()`, `analysis: AnalysisConfig = AnalysisConfig()`, `attestation: AttestationConfig = AttestationConfig()` (extend existing), `session_store: SessionStoreConfig = SessionStoreConfig()`.
    - Define `ApiConfig`, `AnalysisConfig`, `SessionStoreConfig` with Phase-1-parseable defaults so existing YAML fixtures still load (NFR-5).
  - Extend `SourceConfig.type` Literal to include `"elasticsearch"|"rest"|"neo4j"|"servicenow"`.
- **Files**: `nautilus/config/models.py`, `nautilus/config/__init__.py`.
- **Done when**: `tests/fixtures/nautilus.yaml` (Phase 1 fixture) still loads via `load_config`; a new SourceConfig with `type="elasticsearch", index="foo"` constructs; invalid `auth.type="oauth"` raises `pydantic.ValidationError`.
- **Verify**: `uv run python -c "import os; os.environ['TEST_PG_DSN']='postgres://x'; os.environ['TEST_PGV_DSN']='postgres://y'; from nautilus.config.loader import load_config; c=load_config('tests/fixtures/nautilus.yaml'); assert c.agents == {} and c.sources; from nautilus.config.models import SourceConfig; SourceConfig(id='es', type='elasticsearch', description='', classification='u', data_types=['x'], connection='http://es:9200', index='logs')"`
- **Commit**: `feat(config): add Phase 2 additive fields (agents, api, endpoints, auth, index, label)`
- **References**: FR-9, FR-24, FR-26, NFR-5, AC-1.4, AC-2.5, AC-9.1, design §3.5, §3.11.

### Task 1.4 [x] — Implement `AgentRegistry` + `UnknownAgentError`
- **Do**:
  - Create `nautilus/config/agent_registry.py` with `class UnknownAgentError(Exception)` and `class AgentRegistry` wrapping `dict[str, AgentRecord]`; methods `get(agent_id) -> AgentRecord` (raises `UnknownAgentError`), `__iter__()`, `__len__()`.
  - Re-export `AgentRegistry`, `UnknownAgentError` from `nautilus/config/__init__.py`.
  - Ensure `Broker.from_config` constructs registry from `config.agents`; Phase 1 YAML without `agents:` produces an empty registry (AC-5.3 precedent — backwards compatible).
- **Files**: `nautilus/config/agent_registry.py`, `nautilus/config/__init__.py`, `nautilus/core/broker.py` (inject registry).
- **Done when**: `AgentRegistry({"a1": AgentRecord(id="a1", clearance="cui")}).get("a1").clearance == "cui"`; `.get("missing")` raises `UnknownAgentError`.
- **Verify**: `uv run python -c "from nautilus.config.models import AgentRecord; from nautilus.config.agent_registry import AgentRegistry, UnknownAgentError; r = AgentRegistry({'a1': AgentRecord(id='a1', clearance='cui')}); assert r.get('a1').clearance == 'cui'; import pytest; \ntry: r.get('x')\nexcept UnknownAgentError: pass\nelse: raise SystemExit('should have raised')"`
- **Commit**: `feat(config): add AgentRegistry with UnknownAgentError`
- **References**: FR-9, AC-4.2, design §3.5.

### Task 1.5 [x] — Extend Fathom templates (compartments, sub_category, temporal, session multislots, new templates)
- **Do**:
  - Edit `nautilus/rules/templates/nautilus.yaml`:
    - Extend `source` template: add slots `compartments: string default ""`, `sub_category: string default ""`.
    - Extend `agent` template: add slots `compartments: string default ""`, `sub_category: string default ""`.
    - Extend `scope_constraint` template: add `expires_at: string default ""`, `valid_from: string default ""`.
    - Extend `session` template: add multislots `data_types_seen`, `sources_visited`, `pii_sources_accessed_list`; scalar slots `purpose_start_ts: number default 0`, `purpose_ttl_seconds: number default 0`.
    - Add new templates: `data_handoff` (slots `from_agent`, `to_agent`, `session_id`, `classification`, `from_clearance`, `to_clearance`), `escalation_rule` (`id`, `trigger_combination`, `resulting_level`, `action`), `session_exposure` (`session_id`, `value`, `category`), `audit_event` (`session_id`, `agent_id`, `event_type`, `sources_queried`, `classification`, `timestamp`).
- **Files**: `nautilus/rules/templates/nautilus.yaml`.
- **Done when**: `Engine.from_rules(BUILT_IN_RULES_DIR)` succeeds (templates parse); Phase 1 fixture session facts with only `id` + `pii_sources_accessed` still parse (new multislots default to empty).
- **Verify**: `uv run pytest tests/integration/test_fathom_smoke.py -m integration -q`
- **Commit**: `feat(rules): extend templates with compartments, temporal, session multislots, new templates`
- **References**: FR-1, FR-5, FR-6, FR-8, FR-17, FR-18, AC-1.4, AC-2.3, AC-3.1, AC-4.1, AC-7.1, design §3.1, §3.3, §3.4, §3.6, §3.9.

### [VERIFY] Task 1.6 [x] — Quality checkpoint (config + template extensions)
- **Do**: Run toolchain + Phase-1 regression.
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit && uv run pytest tests/integration/test_fathom_smoke.py -m integration -q`
- **Done when**: All exit 0 — Phase 1 surface still green.
- **Commit**: `chore(reasoning): pass checkpoint after config + template extensions` (if fixes needed)

### Task 1.7 [x] — Extend `AuditEntry` + `ScopeConstraint` with Phase 2 optional fields
- **Do**:
  - Edit `nautilus/core/models.py`:
    - Add to `ScopeConstraint`: `expires_at: str | None = None`, `valid_from: str | None = None`.
    - Add to `AuditEntry` (ALL optional, all `= None` default — NFR-5): `llm_provider: str | None`, `llm_model: str | None`, `llm_version: str | None`, `raw_response_hash: str | None`, `prompt_version: str | None`, `fallback_used: bool | None`, `scope_hash_version: Literal["v1","v2"] | None`, `session_id_source: Literal["context","transport","stdio_request_id"] | None`, `session_store_mode: Literal["primary","degraded_memory"] | None`, `event_type: Literal["request","handoff_declared"] | None`, `handoff_id: str | None`, `handoff_decision: HandoffDecision | None`.
    - Add `BrokerRequest(BaseModel)` with fields `agent_id: str`, `intent: str`, `context: dict[str, Any] = {}` (research §5).
    - Add `HandoffDecision(BaseModel)` with `handoff_id: str`, `action: Literal["allow","deny","escalate"]`, `denial_records: list[DenialRecord] = []`, `rule_trace: list[str] = []`.
- **Files**: `nautilus/core/models.py`.
- **Done when**: Importing all models succeeds; a minimal Phase-1-shaped `AuditEntry` JSON line still parses via `AuditEntry.model_validate_json` (NFR-5).
- **Verify**: `uv run python -c "from nautilus.core.models import AuditEntry, ScopeConstraint, BrokerRequest, HandoffDecision; import json; j = json.dumps({'request_id':'r','timestamp':'2026-04-15T00:00:00Z','agent_id':'a','intent':'i','facts_asserted_summary':{},'rule_trace':[],'sources_queried':[],'sources_denied':[],'sources_errored':[],'denial_records':[],'error_records':[],'duration_ms':1}); AuditEntry.model_validate_json(j); BrokerRequest(agent_id='a', intent='i'); HandoffDecision(handoff_id='h', action='allow')"`
- **Commit**: `feat(core): extend AuditEntry + ScopeConstraint with Phase 2 optional fields; add BrokerRequest, HandoffDecision`
- **References**: FR-16, FR-17, FR-19, NFR-5, AC-6.5, AC-7.1, AC-7.4, D-7, D-8, design §3.10.

### Task 1.8 [x] — Implement `PostgresSessionStore` + async `SessionStore` Protocol extension + `Broker.setup()`
- **Do**:
  - Edit `nautilus/core/session.py`: extend `SessionStore` Protocol with async methods `aget(session_id) -> dict`, `aupdate(session_id, entry) -> None`, `aclose() -> None` **alongside** existing sync `get` / `update` (preserve for backwards compat).
  - Create `nautilus/core/session_pg.py`: `class SessionStoreUnavailableError(Exception)`; `class PostgresSessionStore` with `__init__(dsn: str, *, on_failure: Literal["fail_closed","fallback_memory"] = "fail_closed")`; methods `async setup()` (runs `CREATE TABLE IF NOT EXISTS nautilus_session_state (session_id TEXT PRIMARY KEY, state JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now())`), `async aget`, `async aupdate` (both using `asyncpg.Pool` with `ON CONFLICT (session_id) DO UPDATE SET state=EXCLUDED.state, updated_at=now()`), `async aclose`.
  - On `asyncpg.exceptions.CannotConnectNow`/`ConnectionDoesNotExistError`/`UndefinedTableError`: honor `on_failure` — raise `SessionStoreUnavailableError` or degrade to `InMemorySessionStore` instance bound by `degraded_since`.
  - Add `async Broker.setup()` in `nautilus/core/broker.py` that calls `session_store.setup()` if it is a `PostgresSessionStore`.
  - Broker prefers async methods when implementer provides them (`hasattr(store, 'aget')`).
- **Files**: `nautilus/core/session.py`, `nautilus/core/session_pg.py`, `nautilus/core/broker.py`, `nautilus/core/__init__.py`.
- **Done when**: `PostgresSessionStore("postgres://bad:5432/x", on_failure="fail_closed").setup()` raises `SessionStoreUnavailableError`; same with `fallback_memory` degrades without raising. `isinstance(InMemorySessionStore(), SessionStore)` still True (Phase-1 compat).
- **Verify**: `uv run pytest tests/unit/core/test_session_pg_unit.py -q` (test file lands in Task 3.3; this verify is a smoke that the module imports and the Protocol still admits InMemorySessionStore): `uv run python -c "from nautilus.core.session import SessionStore, InMemorySessionStore; assert isinstance(InMemorySessionStore(), SessionStore); from nautilus.core.session_pg import PostgresSessionStore, SessionStoreUnavailableError; print('OK')"`
- **Commit**: `feat(core): add PostgresSessionStore + async SessionStore Protocol + Broker.setup()`
- **References**: FR-3, FR-4, NFR-7, AC-2.2, AC-2.4, AC-2.5, D-1, D-2, D-3, design §3.2.

### Task 1.9 [x] — Implement `contains-all` external + escalation YAML loader
- **Do**:
  - Create `nautilus/rules/functions/contains_all.py` with `def register_contains_all(engine)` registering a CLIPS external that takes two multislots and returns `TRUE` iff every element of the first appears in the second (order-independent).
  - Create `nautilus/config/escalation.py` with `class EscalationRule(BaseModel)` (`id`, `trigger_combination: str`, `resulting_level: str`, `action: Literal["deny","escalate","notify"]`) and `def load_escalation_packs(dirs: list[Path]) -> list[EscalationRule]` that reads every `*.yaml` file and parses list-of-mappings into `EscalationRule` instances.
  - Create `nautilus/rules/escalation/default.yaml` with the PII-aggregation pack (`id: pii-aggregation-confidential`, `trigger_combination: "email phone dob ssn"`, `resulting_level: confidential`, `action: escalate`) per design §3.4.
  - Register `contains-all` in `FathomRouter.__init__` alongside `overlaps` and `not-in-list`; assert each loaded `EscalationRule` as one `escalation_rule` fact per request in `_assert_escalation_rules`.
- **Files**: `nautilus/rules/functions/contains_all.py`, `nautilus/config/escalation.py`, `nautilus/rules/escalation/default.yaml`, `nautilus/core/fathom_router.py`.
- **Done when**: `contains-all(["a","b"], ["b","a","c"]) == True`; `contains-all([], ["x"]) == True`; `contains-all(["a"], []) == False`; default pack loads into 1 `EscalationRule` instance.
- **Verify**: `uv run pytest tests/unit/rules/test_contains_all_external.py -q || echo "test lands in Task 3.2; smoke:"` then `uv run python -c "from nautilus.config.escalation import load_escalation_packs; from pathlib import Path; rules = load_escalation_packs([Path('nautilus/rules/escalation')]); assert len(rules)==1 and rules[0].action=='escalate', rules"`
- **Commit**: `feat(rules): add contains-all external + escalation_rule template loader + default pack`
- **References**: FR-6, FR-7, AC-3.1, AC-3.2, AC-3.3, AC-3.4, design §3.4.

### Task 1.10 [x] — Ship classification hierarchies + `default-classification-deny` rule
- **Do**:
  - Create `nautilus/rules/hierarchies/classification.yaml` with `name: classification`, `levels: [unclassified, cui, confidential, secret, top-secret]`.
  - Create `nautilus/rules/hierarchies/cui-sub.yaml` with `name: cui-sub`, `levels: [cui, cui-sp-cti, cui-sp-iih, cui-sp-pciip]`.
  - Create `nautilus/rules/rules/classification.yaml` containing rule `default-classification-deny` (salience 150) using `(fathom-dominates ?clearance ?subj_cmp ?src_cls ?src_cmp "classification")` to produce a `denial_record` with `rule_name="default-classification-deny"` when the agent's clearance does NOT dominate the source's classification.
  - Register hierarchies in `nautilus/rules/modules/nautilus-routing.yaml`.
- **Files**: `nautilus/rules/hierarchies/classification.yaml`, `nautilus/rules/hierarchies/cui-sub.yaml`, `nautilus/rules/rules/classification.yaml`, `nautilus/rules/modules/nautilus-routing.yaml`.
- **Done when**: `Engine.from_rules(BUILT_IN_RULES_DIR)` succeeds; smoke test asserts `_hierarchy_registry` contains `classification` and `cui-sub`.
- **Verify**: `uv run pytest tests/integration/test_fathom_smoke.py -m integration -q`
- **Commit**: `feat(rules): add classification + cui-sub hierarchies with default-deny rule`
- **References**: FR-1, FR-2, AC-1.1, AC-1.2, AC-1.3, AC-1.5, design §3.1.

### [VERIFY] Task 1.11 [x] — Quality checkpoint (rules + session)
- **Do**: Run toolchain.
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit && uv run pytest tests/integration/test_fathom_smoke.py -m integration -q`
- **Done when**: All exit 0.
- **Commit**: `chore(rules): pass checkpoint` (if fixes needed)

### Task 1.12 [x] — Implement `TemporalFilter` + `purpose-expired-deny` rule + `scope_hash_v2` canonicalization
- **Do**:
  - Create `nautilus/core/temporal.py` with `class TemporalFilter`: `@staticmethod def apply(constraints: dict[str, list[ScopeConstraint]], now: datetime) -> tuple[dict, list[DenialRecord]]` that drops constraints whose `expires_at` is in the past or `valid_from` in the future; malformed ISO-8601 → drop + denial. Each drop produces `DenialRecord(rule_name="scope-expired", source_id=..., ...)`.
  - Create `nautilus/rules/rules/temporal.yaml` with `purpose-expired-deny` rule using `fathom-changed-within` against `session.purpose_start_ts` + `session.purpose_ttl_seconds` — fires a global denial if the purpose TTL has elapsed.
  - Edit `nautilus/core/attestation_payload.py`: change `build_payload(...)` to return `tuple[dict, Literal["v1","v2"]]`. Rule: `version = "v2" if any(c.expires_at or c.valid_from for c in all_constraints) else "v1"`. v1 canonicalization FROZEN (4-tuple sort by `(source_id, field, operator)`); v2 adds `expires_at`/`valid_from` (empty string when unset) to the hashed tuple.
  - Wire `TemporalFilter.apply(now=datetime.utcnow())` into `Broker.arequest` BEFORE adapter fan-out; emitted denial records are added to the response's `denial_records` list.
  - Update call sites: `Broker` stores returned version into `AuditEntry.scope_hash_version`.
- **Files**: `nautilus/core/temporal.py`, `nautilus/rules/rules/temporal.yaml`, `nautilus/core/attestation_payload.py`, `nautilus/core/broker.py`, `nautilus/rules/modules/nautilus-routing.yaml` (register `temporal.yaml`).
- **Done when**: Two Phase-1-shape requests (no temporal slots) produce byte-identical `scope_hash` under v1 (NFR-6); a request with `expires_at` set uses v2 and the audit entry carries `scope_hash_version="v2"`.
- **Verify**: `uv run python -c "from nautilus.core.attestation_payload import build_payload; from nautilus.core.models import ScopeConstraint; p1, v1 = build_payload('r','a',['s'],[ScopeConstraint(source_id='s', field='f', operator='=', value=1)], {}); assert v1=='v1', v1; p2, v2 = build_payload('r','a',['s'],[ScopeConstraint(source_id='s', field='f', operator='=', value=1, expires_at='2030-01-01T00:00:00Z')], {}); assert v2=='v2', v2"`
- **Commit**: `feat(core): add TemporalFilter, purpose-expired-deny rule, scope_hash_v2 canonicalization`
- **References**: FR-17, FR-18, FR-19, AC-7.1, AC-7.2, AC-7.3, AC-7.4, NFR-6, D-7, design §3.9, §3.10.

### Task 1.13 [x] — Implement `AttestationSink` Protocol + `NullAttestationSink` + `FileAttestationSink` + broker wiring
- **Do**:
  - Create `nautilus/core/attestation_sink.py` with:
    - `class AttestationPayload(BaseModel)` (`token: str`, `nautilus_payload: dict[str, Any]`, `emitted_at: datetime`).
    - `class AttestationSink(Protocol)` with `async emit(payload) -> None`, `async close() -> None`. Mark `@runtime_checkable`.
    - `class NullAttestationSink` — no-op `emit`; no-op `close`. Default.
    - `class FileAttestationSink(path: Path)` — opens file in append mode; `emit` writes `payload.model_dump_json() + "\n"` then `flush()` + `os.fsync(fd)`; `close` closes the handle (idempotent).
  - Extend `nautilus/core/broker.py`: accept `attestation_sink: AttestationSink = NullAttestationSink()` in `__init__`; after `_sign(payload)` returns, call `await self._emit_attestation(sink, payload)` which `try/except Exception as exc: log.warning(...)` — never fails the hot path (AC-14.5).
  - `Broker.aclose()` order: `session_store.aclose()` → `attestation_sink.close()` → adapter pool close (D-8 contract).
  - Wire `AttestationSink` selection from `config.attestation.sink` in `Broker.from_config` (`type: "null"|"file"` — HTTP sink lands in Phase 2).
- **Files**: `nautilus/core/attestation_sink.py`, `nautilus/core/broker.py`, `nautilus/core/__init__.py`.
- **Done when**: `FileAttestationSink("/tmp/a.jsonl").emit(payload)` writes one JSONL line + flush+fsync; sink raising does NOT fail `broker.arequest`; order contract enforced.
- **Verify**: `uv run python -c "import asyncio, tempfile, os; from nautilus.core.attestation_sink import FileAttestationSink, AttestationPayload, NullAttestationSink; from datetime import datetime; p = AttestationPayload(token='t', nautilus_payload={'x':1}, emitted_at=datetime.utcnow()); async def run(): s = FileAttestationSink(tempfile.mkstemp(suffix='.jsonl')[1]); await s.emit(p); await s.close(); n = NullAttestationSink(); await n.emit(p); await n.close(); asyncio.run(run()); print('OK')"`
- **Commit**: `feat(core): add AttestationSink Protocol + Null/File impls + broker wiring (audit-first preserved)`
- **References**: FR-28, FR-29, AC-14.1, AC-14.2, AC-14.4, AC-14.5, AC-14.6, NFR-16, D-18, design §3.14.

### Task 1.14 [x] — Integrate extensions into `Broker.arequest` pipeline
- **Do**:
  - Edit `nautilus/core/broker.py::arequest`: wire the new pipeline per design §2.2 sequence diagram:
    1. `SessionStore.aget(session_id)` (prefer async; fallback to sync).
    2. `IntentAnalyzer.analyze(...)` (pattern-matcher stays default; `FallbackIntentAnalyzer` wiring lands in Phase 2).
    3. `FathomRouter.route(...)` — now receives `escalation_rules` + `agent_registry` + `session_exposure` derivation (new `_assert_session` expansion of multislots).
    4. `TemporalFilter.apply(scope_constraints, now)` — drop expired; append denial records.
    5. Adapter fan-out (unchanged Phase 1 path).
    6. `build_payload(...) -> (payload, version)`; stash `version` into `AuditEntry.scope_hash_version`.
    7. `_sign(payload)` → token.
    8. `await self._emit_attestation(sink, AttestationPayload(token, payload, now))` (exception-swallowed).
    9. `SessionStore.aupdate(session_id, new_state)`.
    10. `AuditLogger.emit(AuditEntry)` — ONCE per request (NFR-15).
  - `_assert_session` in `FathomRouter` now iterates the 3 multislots and asserts one `session_exposure` fact per element (AC-2.3, FR-5).
  - Backwards-compat: Phase-1 call sites without session multislots still work (defaults are empty); Phase-1 tests must stay green.
- **Files**: `nautilus/core/broker.py`, `nautilus/core/fathom_router.py`.
- **Done when**: Phase 1 integration test `tests/integration/test_mvp_e2e.py` still passes unchanged (backwards compat); new internal helpers exist.
- **Verify**: `uv run pytest tests/integration/test_mvp_e2e.py -m integration -q`
- **Commit**: `feat(core): wire session_pg, temporal, escalation, attestation sink into Broker.arequest`
- **References**: FR-5, FR-17, FR-19, FR-28, FR-29, NFR-15, AC-2.3, AC-7.4, AC-14.1, AC-14.5, design §2.2, §3.14.

### Task 1.15 [x] — **POC MILESTONE**: `classification_e2e` integration test
- **Do**:
  - Create `tests/integration/test_classification_e2e.py` marked `@pytest.mark.integration`.
  - Reuse `pg_container` fixture from Phase 1 `tests/conftest.py` (Postgres + pgvector).
  - Ship `tests/fixtures/reasoning/poc.yaml` — agents registry (`a1: clearance=cui`), one `pgvector` source with `classification: cui`, `data_types=[pii]`, no temporal slots; default escalation pack dropped in; `attestation.sink.type: file`, `path: /tmp/poc-attestation.jsonl`; `session_store.backend: postgres` with `on_failure: fail_closed`.
  - Test body:
    1. Export DSN env vars from pg_container; `broker = Broker.from_config("tests/fixtures/reasoning/poc.yaml")`; `await broker.setup()`.
    2. Issue first request: `await broker.arequest("a1", "find PII for threat hunting", {"clearance":"cui","purpose":"threat-hunt","session_id":"s1","compartments":"cti","embedding":[0.1,0.2,0.3]})`.
    3. Assert: `resp.attestation_token is not None`; reading `./audit.jsonl` last line, `entry.scope_hash_version == "v1"` (no temporal slots); `entry.session_store_mode == "primary"`; `entry.event_type == "request"`.
    4. Issue a second request with the same `session_id` and a scope constraint carrying `expires_at` 1 hour in the future — assert resp audit has `scope_hash_version == "v2"`.
    5. Issue a third request where the agent's clearance dominates the source — assert at least one `routing_decision` entry.
    6. Issue a fourth request where the agent's clearance is `unclassified` but source is `cui` — assert `denial_records` contains an entry with `rule_name == "default-classification-deny"`.
    7. Assert `/tmp/poc-attestation.jsonl` exists and has ≥4 JSONL lines (one per request), each parseable as `AttestationPayload`.
- **Files**: `tests/integration/test_classification_e2e.py`, `tests/fixtures/reasoning/poc.yaml`, `tests/conftest.py` (extend to create /tmp cleanup).
- **Done when**: `uv run pytest tests/integration/test_classification_e2e.py -m integration -q` exits 0.
- **Verify**: `uv run pytest tests/integration/test_classification_e2e.py -m integration -q`
- **Commit**: `test(integration): POC milestone — classification + scope_hash_v2 + attestation sink e2e`
- **References**: FR-1, FR-2, FR-5, FR-16, FR-17, FR-19, FR-28, AC-1.3, AC-2.1, AC-2.2, AC-7.4, AC-14.1, AC-14.2, NFR-5, design §2.2, §9 step 7.

> **POC MILESTONE ACHIEVED** — reasoning-engine pipeline proven end-to-end: classification rule fires, pattern-matcher analyzes intent, temporal filter selects v1 vs v2 hash, pgvector adapter returns rows, attestation token is signed and dispatched to a file sink. All Phase 1 surfaces remain green.

---

## Phase 2: Refactor / Completeness — add remaining components in design §9 order

Focus: Fill in all components NOT in the POC slice. Four adapters (ES → Neo4j → REST → ServiceNow per §9 step 8), LLM analyzer matrix, REST transport, MCP transport, CLI, Dockerfile, forensic worker. Each landing is a separate task with its own integration smoke.

### Task 2.1 [x] — Implement `Broker.declare_handoff` + `data_handoff` template + `information-flow-violation` rule
- **Do**:
  - Create `nautilus/rules/rules/handoff.yaml` with `information-flow-violation` rule: fires when `from_agent_clearance` dominates `data_handoff.classification` but `to_agent_clearance` does not → produces `denial_record(rule_name="information-flow-violation")`.
  - Add `async Broker.declare_handoff(*, source_agent_id, receiving_agent_id, session_id, data_classifications: list[str], rule_trace_refs: list[str] = [], data_compartments: list[str] = []) -> HandoffDecision` to `nautilus/core/broker.py`. Flow: resolve agents via `AgentRegistry` (propagates `UnknownAgentError` as `HandoffDecision(action="deny", denial_records=[DenialRecord(rule_name="unknown-agent", ...)])`); assert one `data_handoff` fact per classification; `await engine.evaluate()`; collect `denial_record` facts; write exactly one audit entry with `event_type="handoff_declared"`, `handoff_id=uuid4()`, `handoff_decision` populated. Zero adapter calls.
- **Files**: `nautilus/core/broker.py`, `nautilus/rules/rules/handoff.yaml`, `nautilus/rules/modules/nautilus-routing.yaml`.
- **Done when**: `await broker.declare_handoff(source_agent_id="a1", receiving_agent_id="a2", session_id="s1", data_classifications=["secret"])` returns a `HandoffDecision`; one audit entry with `event_type="handoff_declared"` per call.
- **Verify**: `uv run pytest tests/unit/core/test_declare_handoff.py -q || echo "unit test lands in Task 3.4"` then `uv run python -c "print('smoke: declare_handoff importable'); from nautilus.core.broker import Broker; assert hasattr(Broker, 'declare_handoff')"`
- **Commit**: `feat(core): add Broker.declare_handoff + information-flow-violation rule`
- **References**: FR-8, FR-10, AC-4.1, AC-4.2, AC-4.3, AC-4.4, AC-4.5, D-4, design §3.6.

### Task 2.2 [x] — Ship `LLMIntentProvider` Protocol + `LLMProvenance` + `LLMProviderError`
- **Do**:
  - Create `nautilus/analysis/llm/base.py` with:
    - `class LLMProviderError(Exception)`.
    - `@runtime_checkable class LLMIntentProvider(Protocol)` with attrs `model: str`, `provider_name: str`, `prompt_version: str`; methods `async analyze(intent, context) -> IntentAnalysis`, `health_check() -> None`.
    - `@dataclass class LLMProvenance(provider: str, model: str, version: str, prompt_version: str, raw_response_hash: str, fallback_used: bool)`.
  - Re-export from `nautilus/analysis/llm/__init__.py`.
- **Files**: `nautilus/analysis/llm/base.py`, `nautilus/analysis/llm/__init__.py`.
- **Done when**: Protocol and types import; `isinstance` check compiles under pyright-strict.
- **Verify**: `uv run python -c "from nautilus.analysis.llm.base import LLMIntentProvider, LLMProviderError, LLMProvenance; print('OK')"`
- **Commit**: `feat(analysis): add LLMIntentProvider Protocol + LLMProvenance + LLMProviderError`
- **References**: FR-13, D-5, design §3.8.

### Task 2.3 [x] — Ship locked `intent_v1.txt` prompt template + snapshot-test fixture
- **Do**:
  - Create `nautilus/analysis/llm/prompts/intent_v1.txt` — single prompt using stdlib `string.Template` `$var` substitution (no Jinja). Variables: `$intent`, `$context_json`. Template asks the LLM to produce JSON matching `IntentAnalysis.model_json_schema()` with `data_types_needed`, `entities`, `estimated_sensitivity`, `purpose_inferred`.
  - Lock the file content; `prompt_version` is derived from filename suffix (`v1` here).
- **Files**: `nautilus/analysis/llm/prompts/intent_v1.txt`.
- **Done when**: File exists, is non-empty, contains `$intent` and `$context_json` placeholders; `string.Template(open(...).read()).safe_substitute(intent="x", context_json="{}")` returns a non-empty string.
- **Verify**: `uv run python -c "import string, pathlib; t = string.Template(pathlib.Path('nautilus/analysis/llm/prompts/intent_v1.txt').read_text(encoding='utf-8')); out = t.safe_substitute(intent='x', context_json='{}'); assert len(out) > 100 and '$' not in out, out[:200]"`
- **Commit**: `feat(analysis): lock intent_v1.txt prompt template`
- **References**: FR-15, AC-6.6, design §3.8.

### Task 2.4 [x] — Implement `AnthropicProvider`
- **Do**:
  - Create `nautilus/analysis/llm/anthropic_provider.py` with `class AnthropicProvider` implementing `LLMIntentProvider`. Constructor takes `api_key_env: str`, `model: str` (default `claude-sonnet-4-5`), `timeout_s: float`. Uses `anthropic.AsyncAnthropic` SDK with tool-use binding to `IntentAnalysis.model_json_schema()`; `temperature=0`, `max_tokens=512`. On any SDK exception → raise `LLMProviderError`; on non-JSON response → `pydantic.ValidationError`.
  - Populate `LLMProvenance.raw_response_hash` from `sha256(response.id + response.content[0].input)` or equivalent deterministic hash.
- **Files**: `nautilus/analysis/llm/anthropic_provider.py`.
- **Done when**: Provider imports when `anthropic` extra installed; `health_check()` raises `LLMProviderError` when API key env var missing.
- **Verify**: `uv run python -c "import os; os.environ.pop('ANTHROPIC_API_KEY', None); from nautilus.analysis.llm.anthropic_provider import AnthropicProvider; p = AnthropicProvider(api_key_env='ANTHROPIC_API_KEY', model='claude-sonnet-4-5', timeout_s=2.0); from nautilus.analysis.llm.base import LLMProviderError; import pytest; \ntry: p.health_check()\nexcept LLMProviderError: pass\nelse: raise SystemExit('missing key not detected')"`
- **Commit**: `feat(analysis): add AnthropicProvider`
- **References**: FR-13, AC-6.1, AC-6.6, design §3.8.

### [VERIFY] Task 2.5 [x] — Quality checkpoint (declare_handoff + LLM Protocol)
- **Do**: Run toolchain + Phase-1 regression probe (matches Phase-1 [VERIFY] cadence 1.6 / 1.11).
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit && uv run pytest tests/integration/test_mvp_e2e.py -m integration -q`
- **Done when**: All exit 0; Phase-1 MVP E2E still passes.
- **Commit**: `chore(phase2): pass checkpoint after handoff + LLM Protocol` (if fixes needed)

### Task 2.6 [x] — Implement `OpenAIProvider` + `LocalInferenceProvider`
- **Do**:
  - Create `nautilus/analysis/llm/openai_provider.py` with `class OpenAIProvider` using `openai.AsyncOpenAI` and `responses.parse` bound to `IntentAnalysis` Pydantic schema; `temperature=0`.
  - Create `nautilus/analysis/llm/local_provider.py` with `class LocalInferenceProvider` — same SDK as OpenAI but configurable `base_url` (vLLM / llama.cpp OpenAI-compatible). Accepts `model` name verbatim. Air-gap-compatible.
- **Files**: `nautilus/analysis/llm/openai_provider.py`, `nautilus/analysis/llm/local_provider.py`.
- **Done when**: Both import; `LocalInferenceProvider(base_url="http://localhost:8000/v1", model="local")` constructs without network.
- **Verify**: `uv run python -c "from nautilus.analysis.llm.openai_provider import OpenAIProvider; from nautilus.analysis.llm.local_provider import LocalInferenceProvider; LocalInferenceProvider(base_url='http://localhost:8000/v1', model='local', timeout_s=2.0); print('OK')"`
- **Commit**: `feat(analysis): add OpenAIProvider + LocalInferenceProvider`
- **References**: FR-13, AC-6.1, AC-6.6, design §3.8.

### Task 2.7 [x] — Implement `FallbackIntentAnalyzer` + broker wiring
- **Do**:
  - Create `nautilus/analysis/fallback.py` with `class FallbackIntentAnalyzer(primary: LLMIntentProvider, fallback: IntentAnalyzer, *, timeout_s: float = 2.0, mode: Literal["llm-first","llm-only"] = "llm-first")`. `async analyze(intent, context) -> tuple[IntentAnalysis, LLMProvenance]`: wrap primary call in `asyncio.timeout(timeout_s)`; catch `TimeoutError | LLMProviderError | pydantic.ValidationError` → if `mode == "llm-first"` delegate to `fallback` and return with `fallback_used=True`; if `mode == "llm-only"` re-raise.
  - Update `Broker.from_config` to construct `FallbackIntentAnalyzer` when `config.analysis.mode in {"llm-first","llm-only"}` using `config.analysis.provider` + `pattern_analyzer` as fallback.
  - Broker copies `LLMProvenance` fields into `AuditEntry` (`llm_provider`, `llm_model`, etc.) per AC-6.5.
- **Files**: `nautilus/analysis/fallback.py`, `nautilus/analysis/__init__.py`, `nautilus/core/broker.py`.
- **Done when**: `FallbackIntentAnalyzer` constructs; each failure path (timeout / LLMProviderError / ValidationError) delegates to fallback and returns `fallback_used=True`; `mode="llm-only"` re-raises.
- **Verify**: `uv run pytest tests/unit/analysis/test_fallback.py -q || echo "test lands in Task 3.7; smoke:"` then `uv run python -c "from nautilus.analysis.fallback import FallbackIntentAnalyzer; print('OK')"`
- **Commit**: `feat(analysis): add FallbackIntentAnalyzer + broker wiring`
- **References**: FR-14, AC-6.2, AC-6.3, AC-6.5, D-6, design §3.8.

### Task 2.8 [x] — Implement `ElasticsearchAdapter` (§9 step 8a)
- **Do**:
  - Create `nautilus/adapters/elasticsearch.py` with `class ElasticsearchAdapter` implementing the Phase 1 `Adapter` Protocol.
  - `connect()`: `AsyncElasticsearch(source.connection, basic_auth=...|api_key=...|ca_certs=...)`. Refuse connect if `index` unset or fails regex `^[a-z0-9][a-z0-9._-]*$` (`ScopeEnforcementError`).
  - `execute(intent, scope, context)`: build `elasticsearch.dsl.AsyncSearch(using=client, index=index)`. For each operator in `_OPERATOR_ALLOWLIST`, apply the DSL mapping per AC-8.2 (`=`→`Term`, `!=`→`Bool(must_not=[Term])`, `IN`→`Terms`, `NOT IN`→`Bool(must_not=[Terms])`, `< > <= >=`→`Range`, `BETWEEN`→`Range(gte,lte)`, `LIKE`→`Wildcard` with `%→*` / `_→?`, `IS NULL`→`Bool(must_not=[Exists])`). Unknown operator → `ScopeEnforcementError`.
  - `close()`: idempotent `_closed` pattern from Phase 1.
  - Register in `nautilus/adapters/__init__.py` `ADAPTER_REGISTRY`.
  - Static grep check in adapter: forbid `f"..."` + `Search.query(` within 5 lines (inherits Phase 1 `test_sql_injection_static` pattern).
- **Files**: `nautilus/adapters/elasticsearch.py`, `nautilus/adapters/__init__.py`.
- **Done when**: Adapter imports; constructing with `SourceConfig(type='elasticsearch', index='bad index!')` raises at connect-time.
- **Verify**: `uv run python -c "from nautilus.adapters.elasticsearch import ElasticsearchAdapter; from nautilus.config.models import SourceConfig; from nautilus.adapters.base import ScopeEnforcementError; import asyncio; a = ElasticsearchAdapter(SourceConfig(id='es', type='elasticsearch', description='', classification='u', data_types=['x'], connection='http://es:9200', index='bad index!')); \nasync def run(): \n    try: await a.connect()\n    except ScopeEnforcementError: pass\n    else: raise SystemExit('bad index not rejected')\nasyncio.run(run())"`
- **Commit**: `feat(adapters): add ElasticsearchAdapter with operator allowlist + index validation`
- **References**: FR-20, AC-8.1, AC-8.2, AC-8.3, AC-8.4, NFR-4, design §3.11.

### Task 2.9 — Implement `Neo4jAdapter` (§9 step 8b)
- **Do**:
  - Create `nautilus/adapters/neo4j.py` with `class Neo4jAdapter`. `connect()`: `AsyncGraphDatabase.driver(source.connection, auth=(user, pw))`; validate `label` regex `^[A-Z][A-Za-z0-9_]*$`, backtick in Cypher.
  - `execute`: build parameterized Cypher `MATCH (n:\`<Label>\`) WHERE <predicates> RETURN n LIMIT $L` with `driver.execute_query(..., routing_=READ, parameters_=dict)`. Property identifiers regex-validated + backticked. Operator map per AC-10.2. `LIKE` honors `source.like_style` (default `starts_with` → `STARTS WITH $pN`; `regex` → `=~ $pN` with CONFIG WARN).
  - `close()`: idempotent.
- **Files**: `nautilus/adapters/neo4j.py`, `nautilus/adapters/__init__.py`.
- **Done when**: Adapter imports; constructor accepts `SourceConfig(label='Person')`; bad label raises `ScopeEnforcementError` at connect.
- **Verify**: `uv run python -c "from nautilus.adapters.neo4j import Neo4jAdapter; from nautilus.config.models import SourceConfig; from nautilus.adapters.base import ScopeEnforcementError; import asyncio; a = Neo4jAdapter(SourceConfig(id='n', type='neo4j', description='', classification='u', data_types=['x'], connection='bolt://n:7687', label='1bad')); \nasync def run():\n    try: await a.connect()\n    except ScopeEnforcementError: pass\n    else: raise SystemExit('bad label not rejected')\nasyncio.run(run())"`
- **Commit**: `feat(adapters): add Neo4jAdapter with label backticking + LIKE style switch`
- **References**: FR-22, AC-10.1, AC-10.2, AC-10.3, AC-10.4, NFR-4, design §3.11.

### [VERIFY] Task 2.10 — Quality checkpoint (LLM providers + 2 adapters)
- **Do**: Run toolchain.
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit`
- **Done when**: All exit 0.
- **Commit**: `chore(phase2): pass checkpoint after ES + Neo4j adapters` (if fixes needed)

### Task 2.11 — Implement `RestAdapter` with SSRF defense (§9 step 8c)
- **Do**:
  - Create `nautilus/adapters/rest.py` with `class RestAdapter` + `class SSRFBlockedError(AdapterError)`.
  - `connect()`: `httpx.AsyncClient(base_url=source.connection, follow_redirects=False, auth=<from AuthConfig>)`. If `SourceConfig.endpoints` references an undeclared path referenced by a scope constraint → `ScopeEnforcementError` at load.
  - `execute`: for each scope constraint, look up `EndpointSpec.operator_templates` (defaults: `=`→`?f=v`, `!=`→`?f__ne=v`, `IN`→repeated `?f=v1&f=v2`, `< > <= >=`→`?f__lt=v` etc., `BETWEEN`→paired `__gte/__lte`, `LIKE`→`?f__contains=v`, `IS NULL`→`?f__isnull=true`, `NOT IN` rejected unless explicitly declared). Build request via `httpx`; on response, assert `response.next_request` host matches `base_url` host — else `SSRFBlockedError`.
  - `close()`: idempotent.
- **Files**: `nautilus/adapters/rest.py`, `nautilus/adapters/__init__.py`.
- **Done when**: Adapter imports; `RestAdapter` refuses a redirect-to-different-host in unit test.
- **Verify**: `uv run pytest tests/unit/adapters/test_rest.py -q || echo "unit test lands in Task 3.9; smoke:"` then `uv run python -c "from nautilus.adapters.rest import RestAdapter, SSRFBlockedError; print('OK')"`
- **Commit**: `feat(adapters): add RestAdapter with SSRF defense + endpoint allowlist`
- **References**: FR-21, AC-9.1, AC-9.2, AC-9.3, AC-9.4, NFR-4, NFR-17, design §3.11.

### Task 2.12 — Implement `ServiceNowAdapter` with `_sanitize_sn_value` (§9 step 8d)
- **Do**:
  - Create `nautilus/adapters/servicenow.py` with `class ServiceNowAdapter`. `connect()`: validate `table` regex `^[a-z][a-z0-9_]*$`; `httpx.AsyncClient(base_url=source.connection, auth=...)`.
  - Implement `_sanitize_sn_value(v: str) -> str`: if `v` contains `^`, `\n`, or `\r` → raise `ScopeEnforcementError("sn-injection-rejected")`.
  - `execute`: compose `sysparm_query` from scope constraints using `^` separator; each operator maps to GlideRecord form per AC-11.2 (`=`/`!=`/`IN`/`NOT IN`/`<`/`>`/`<=`/`>=`/`BETWEEN`/`LIKE`/`IS NULL`→`ISEMPTY`). Every value passes through `_sanitize_sn_value` first.
  - `close()`: idempotent.
- **Files**: `nautilus/adapters/servicenow.py`, `nautilus/adapters/__init__.py`.
- **Done when**: Adapter imports; `_sanitize_sn_value("bad^value")` raises `ScopeEnforcementError`.
- **Verify**: `uv run python -c "from nautilus.adapters.servicenow import ServiceNowAdapter; from nautilus.adapters.base import ScopeEnforcementError; f = ServiceNowAdapter._sanitize_sn_value; \ntry: f('bad^value')\nexcept ScopeEnforcementError: pass\nelse: raise SystemExit('sanitizer did not reject ^')"`
- **Commit**: `feat(adapters): add ServiceNowAdapter with encoded-query sanitizer`
- **References**: FR-23, AC-11.1, AC-11.2, AC-11.3, AC-11.4, NFR-4, NFR-18, design §3.11, D-19.

### Task 2.13 — Implement `HttpAttestationSink` with retry + dead-letter
- **Do**:
  - Extend `nautilus/core/attestation_sink.py` with `class HttpAttestationSink(url: str, *, retry_policy: RetryPolicy = RetryPolicy(), dead_letter_path: Path | None = None)`. Uses `httpx.AsyncClient`. `emit` POSTs the payload; on exhausting retries, writes to a wrapped `FileAttestationSink(dead_letter_path)`.
  - Define `class RetryPolicy(BaseModel)` with `max_retries: int = 3`, `initial_backoff_s: float = 0.1`, `max_backoff_s: float = 5.0`.
  - `close()` awaits `AsyncClient.aclose()` + dead-letter sink close; idempotent.
  - Wire selection from `config.attestation.sink.type == "http"` into `Broker.from_config`.
- **Files**: `nautilus/core/attestation_sink.py`, `nautilus/core/broker.py`.
- **Done when**: HttpAttestationSink constructs with all defaults; unreachable URL + zero retries → one WARN log + dead-letter line written.
- **Verify**: `uv run python -c "from nautilus.core.attestation_sink import HttpAttestationSink, RetryPolicy; HttpAttestationSink(url='http://verifier/emit', retry_policy=RetryPolicy(max_retries=0)); print('OK')"`
- **Commit**: `feat(core): add HttpAttestationSink with retry + dead-letter spill`
- **References**: FR-28, AC-14.3, design §3.14.

### [VERIFY] Task 2.14 — Quality checkpoint (all 4 adapters + HTTP sink)
- **Do**: Run toolchain.
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit`
- **Done when**: All exit 0.
- **Commit**: `chore(phase2): pass checkpoint after adapters + http sink` (if fixes needed)

### Task 2.15 — Implement FastAPI REST transport: `create_app` + lifespan + endpoints
- **Do**:
  - Create `nautilus/transport/auth.py` with: `APIKeyHeader(name="X-API-Key", auto_error=True)` dependency; `verify_api_key(header_value, keys: list[str]) -> None` using `secrets.compare_digest`; optional `proxy_trust_dependency()` reading `X-Forwarded-User`.
  - Create `nautilus/transport/fastapi_app.py` with `def create_app(config_path: str | Path, *, existing_broker: Broker | None = None) -> FastAPI`. Uses `@asynccontextmanager` lifespan that constructs `broker = Broker.from_config(path)` (or accepts `existing_broker`) and `await broker.setup()`; sets `app.state.broker`; on shutdown `await broker.aclose()`.
  - Endpoints: `POST /v1/request` (body `BrokerRequest`, response `BrokerResponse`, direct `await app.state.broker.arequest(...)` — no executor), `POST /v1/query` (literal alias of `/v1/request` — D-9 / UQ-3), `GET /v1/sources` (metadata only), `GET /healthz` (static 200), `GET /readyz` (200 iff startup complete AND `await broker.session_store.aget('_ready_probe_')` succeeds; else 503).
  - All write endpoints gated by `Depends(verify_api_key)` unless `auth.mode == "proxy_trust"`.
- **Files**: `nautilus/transport/auth.py`, `nautilus/transport/fastapi_app.py`, `nautilus/transport/__init__.py`.
- **Done when**: `create_app(...)` returns a `FastAPI` instance; `httpx.AsyncClient(transport=ASGITransport(app))` can hit `GET /healthz` and receive 200.
- **Verify**: `uv run pytest tests/unit/transport/test_fastapi_unit.py -q || echo "unit test lands in Task 3.12; smoke:"` then `uv run python -c "from nautilus.transport.fastapi_app import create_app; print('create_app importable')"`
- **Commit**: `feat(transport): add FastAPI app factory + APIKeyHeader + lifespan broker singleton`
- **References**: FR-25, FR-26, AC-12.1, AC-12.2, AC-12.3, AC-12.4, AC-12.5, D-11, D-13, D-14, design §3.12.

### Task 2.16 — Implement MCP transport: `create_server` + session-id resolution + tool
- **Do**:
  - Create `nautilus/transport/mcp_server.py` with `def create_server(config_path: str | Path, *, existing_broker: Broker | None = None) -> FastMCP`.
  - Construct `FastMCP(name="nautilus", stateless_http=True, json_response=True)`.
  - Register tool `@mcp.tool() async def nautilus_request(agent_id: str, intent: str, context: dict[str, Any] = {}, ctx: Context | None = None) -> BrokerResponse`.
  - Session-id resolution (D-10 / UQ-4) — before calling `broker.arequest`:
    1. If `context.get("session_id")` → use; `audit.session_id_source="context"`.
    2. Else if `ctx` has `session_id` (http mode) → use `ctx.session_id`; `audit.session_id_source="transport"`.
    3. Else (stdio) → `ctx.request_id`; `audit.session_id_source="stdio_request_id"`.
  - `agent_id` is taken VERBATIM from the tool argument — never derived from MCP `client_id` (AC-13.3).
  - Optional tool gated on `config.mcp.expose_declare_handoff: true`: `nautilus_declare_handoff(...)` returning `HandoffDecision`.
  - HTTP transport's Starlette sub-app wrapped with the shared `APIKeyHeader` middleware from `transport/auth.py`.
- **Files**: `nautilus/transport/mcp_server.py`.
- **Done when**: `create_server(...)` returns a `FastMCP` instance; stdio invocation round-trips a `nautilus_request` tool call against a seeded broker.
- **Verify**: `uv run pytest tests/unit/transport/test_mcp_unit.py -q || echo "unit test lands in Task 3.13; smoke:"` then `uv run python -c "from nautilus.transport.mcp_server import create_server; print('create_server importable')"`
- **Commit**: `feat(transport): add FastMCP server + session-id fallback + shared API-key middleware`
- **References**: FR-27, AC-13.1, AC-13.2, AC-13.3, AC-13.4, AC-13.5, D-10, D-12, design §3.13.

### Task 2.17 — Implement `nautilus/cli.py` with `serve|health|version`
- **Do**:
  - Create `nautilus/cli.py` with stdlib `argparse` (no click/typer — FR-30 / D-15):
    - `nautilus version` → prints `importlib.metadata.version("nautilus")`, exits 0.
    - `nautilus health [--url http://localhost:8000/readyz]` → `urllib.request.urlopen(url, timeout=5)`, returns exit 0 if 200, non-zero otherwise. No `requests` import.
    - `nautilus serve --config PATH [--transport rest|mcp|both] [--mcp-mode stdio|http] [--bind HOST:PORT] [--air-gapped]` — loads config; enforces `--air-gapped` by overriding `config.analysis.mode = "pattern"` and refusing any LLM provider config (WARN naming the overridden field). Constructs `broker = Broker.from_config(config)` ONCE, then:
      - `--transport rest`: uvicorn.run(create_app(existing_broker=broker), host, port)
      - `--transport mcp`: `await create_server(existing_broker=broker).run_async(mode)`
      - `--transport both`: run both concurrently on one asyncio loop (sharing the broker singleton — NFR-14).
  - Create `nautilus/__main__.py`: one-liner `from nautilus.cli import main; main()`.
  - Missing/invalid config path → print error and exit non-zero BEFORE any network bind.
- **Files**: `nautilus/cli.py`, `nautilus/__main__.py`.
- **Done when**: `python -m nautilus --help` shows all three subcommands; `python -m nautilus version` prints the package version; `python -m nautilus serve --config /bogus/path.yaml` exits non-zero with a clear error.
- **Verify**: `uv run python -m nautilus --help 2>&1 | grep -q "serve" && uv run python -m nautilus version && (uv run python -m nautilus serve --config /bogus/path.yaml; test $? -ne 0) && echo CLI_OK`
- **Commit**: `feat(cli): add nautilus CLI with serve/health/version + --air-gapped enforcement`
- **References**: FR-30, AC-15.1, AC-15.2, AC-15.3, AC-15.4, AC-15.5, D-15, NFR-1, NFR-14, design §3.15.

### Task 2.18 — Implement multi-stage Dockerfile (builder + distroless + debug target)
- **Do**:
  - Create `/Dockerfile` at repo root (project root is `C:/Projects/project-fathom/nautilus`):
    - Stage `builder` (`FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim`): `uv sync --frozen --no-dev` into `/app/.venv`; `COPY nautilus /app/nautilus`; `COPY pyproject.toml uv.lock /app/`.
    - Stage `runtime` (`FROM gcr.io/distroless/cc-debian13 AS runtime`): `COPY --from=builder /app /app`; `ENV PYTHONPATH=/app PATH=/app/.venv/bin:$PATH`; `ENTRYPOINT ["/app/.venv/bin/python","-m","nautilus"]`; `CMD ["serve","--config","/config/nautilus.yaml"]`; `HEALTHCHECK CMD ["/app/.venv/bin/python","-m","nautilus","health"]`.
    - Stage `debug` (`FROM python:3.14-slim AS debug`): same COPY from builder; `RUN apt-get update && apt-get install -y bash`; NOT built by CI (operator-local only, D-17 / UQ-5).
  - Create `/.dockerignore` excluding `tests/`, `specs/`, `.git/`, `__pycache__/`, `*.pyc`, `audit.jsonl`, `.ve-*`.
- **Files**: `/Dockerfile`, `/.dockerignore`.
- **Done when**: `docker build -t nautilus:test .` succeeds; `docker image inspect nautilus:test | jq '.[0].Size'` returns a number ≤ 200*1024*1024 (200 MB); `docker build --target debug -t nautilus:test-debug .` also succeeds.
- **Verify**: `docker build -t nautilus:test . && SIZE=$(docker image inspect nautilus:test --format '{{.Size}}') && [ "$SIZE" -le 209715200 ] && docker build --target debug -t nautilus:test-debug . && echo IMAGE_OK`
- **Commit**: `feat(docker): add multi-stage distroless Dockerfile with optional debug target`
- **References**: FR-31, FR-32, AC-16.1, AC-16.2, AC-16.3, AC-16.4, AC-16.5, AC-16.6, D-16, D-17, NFR-10, design §3.16.

### [VERIFY] Task 2.19 — Quality checkpoint (transports + CLI + Docker)
- **Do**: Run toolchain.
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit`
- **Done when**: All exit 0.
- **Commit**: `chore(phase2): pass checkpoint after transports + CLI + Docker` (if fixes needed)

### Task 2.20 — Implement `ProcessedOffsets` (atomic write, bounded seen-hash set)
- **Do**:
  - Create `nautilus/forensics/offsets.py` with `class OffsetsCorruptError(Exception)` and `class ProcessedOffsets(BaseModel)` (`last_byte_offset: int`, `seen_line_sha256: set[str]`).
  - `load(path: Path) -> ProcessedOffsets`: returns fresh empty instance if file missing; else parse JSON; on parse error or non-monotonic `last_byte_offset` vs existing state → raise `OffsetsCorruptError`.
  - `save(self, path: Path) -> None`: write to `<path>.tmp` then `os.replace(tmp, path)` (atomic).
  - Bound `seen_line_sha256` to last 10**6 entries (LRU via `collections.deque` mirror).
- **Files**: `nautilus/forensics/offsets.py`, `nautilus/forensics/__init__.py`.
- **Done when**: Round-trip `ProcessedOffsets(last_byte_offset=100, seen_line_sha256={"abc"}).save(p); loaded = load(p); loaded.seen_line_sha256 == {"abc"}`; truncated JSON raises `OffsetsCorruptError`.
- **Verify**: `uv run python -c "import tempfile, pathlib; from nautilus.forensics.offsets import ProcessedOffsets, OffsetsCorruptError; p = pathlib.Path(tempfile.mkstemp(suffix='.json')[1]); o = ProcessedOffsets(last_byte_offset=100, seen_line_sha256={'abc'}); o.save(p); o2 = ProcessedOffsets.load(p); assert o2.last_byte_offset == 100; p.write_text('not json', encoding='utf-8'); \ntry: ProcessedOffsets.load(p)\nexcept OffsetsCorruptError: pass\nelse: raise SystemExit('corruption not raised')"`
- **Commit**: `feat(forensics): add ProcessedOffsets with atomic write + corruption detection`
- **References**: FR-33, NFR-13, AC-5.4, design §3.7.

### Task 2.21 — Implement forensic sinks (`JSONLForensicSink` + `HttpForensicSink`) + `InferredHandoff` model
- **Do**:
  - Add to `nautilus/core/models.py`: `class InferredHandoff(BaseModel)` with `session_id`, `source_agent`, `receiving_agent`, `confidence: float`, `signals: list[str]`, `inferred_at: datetime`.
  - Create `nautilus/forensics/sinks.py` with `@runtime_checkable class ForensicSink(Protocol)` (`async emit(record) / async close()`); `class JSONLForensicSink(path)` (append-only, flush+fsync); `class HttpForensicSink(url)` (httpx POST, no air-gap requirement since this is offline).
- **Files**: `nautilus/forensics/sinks.py`, `nautilus/core/models.py`.
- **Done when**: Both sinks import; `JSONLForensicSink.emit(InferredHandoff(...))` writes one line; Protocol admits both concrete sinks.
- **Verify**: `uv run python -c "import asyncio, tempfile, pathlib; from nautilus.forensics.sinks import JSONLForensicSink, ForensicSink; from nautilus.core.models import InferredHandoff; from datetime import datetime; p = pathlib.Path(tempfile.mkstemp(suffix='.jsonl')[1]); s = JSONLForensicSink(p); assert isinstance(s, ForensicSink); async def run(): await s.emit(InferredHandoff(session_id='s', source_agent='a', receiving_agent='b', confidence=0.7, signals=['shared-session'], inferred_at=datetime.utcnow())); await s.close()\nasyncio.run(run()); print('OK')"`
- **Commit**: `feat(forensics): add ForensicSink Protocol + JSONL/Http impls + InferredHandoff model`
- **References**: FR-11, AC-5.1, design §3.7.

### Task 2.22 — Ship forensic rule pack (`handoff.yaml`: h-shared-session, h-source-overlap, h-classification-delta)
- **Do**:
  - Create `nautilus/rules/forensics/handoff.yaml` with three rules per design §3.7:
    - `h-shared-session` (salience 100): matches two distinct `agent_id`s on same `session_id` within window.
    - `h-source-overlap` (salience 80): matches two agents sharing ≥1 `sources_queried` entry within window.
    - `h-classification-delta` (salience 60): matches later agent with lower max classification than earlier one.
  - Each rule produces an `InferredHandoff`-shaped fact with `confidence` slot derived from salience sum.
- **Files**: `nautilus/rules/forensics/handoff.yaml`.
- **Done when**: `fathom.Engine.from_rules(Path("nautilus/rules/forensics"))` constructs without error with the `audit_event` template loaded.
- **Verify**: `uv run python -c "from pathlib import Path; import fathom; e = fathom.Engine(); e.load_templates(Path('nautilus/rules/templates/nautilus.yaml')); e.load_rules(Path('nautilus/rules/forensics/handoff.yaml')); print('OK')"`
- **Commit**: `feat(rules): add forensic handoff rule pack with 3 heuristics`
- **References**: FR-12, AC-5.2, design §3.7.

### Task 2.23 — Implement forensic `handoff_worker.run_worker` + `__main__`
- **Do**:
  - Create `nautilus/forensics/handoff_worker.py` with:
    - `class WorkerReport(BaseModel)` (`lines_processed: int`, `records_emitted: int`, `new_offset: int`).
    - `def run_worker(audit_path: Path, offsets_path: Path, out_sink: ForensicSink, *, window_s: int = 3600) -> WorkerReport`.
      - Load `offsets = ProcessedOffsets.load(offsets_path)`.
      - Seek `audit_path` to `offsets.last_byte_offset`; stream lines; for each line, compute `sha256`; skip if already in `offsets.seen_line_sha256`.
      - Parse each line as `AuditEntry`; assert `audit_event` fact into Fathom engine loaded with `nautilus/rules/forensics/handoff.yaml`.
      - After stream end, `engine.evaluate()`; collect `InferredHandoff` facts.
      - DECLARED-PRECEDENCE DEDUP: before emitting, scan the same audit segment for `event_type="handoff_declared"` records matching `(session_id, source_agent, receiving_agent)` within window → drop matching inferred.
      - Emit remaining via `await out_sink.emit(...)`.
      - Atomic `offsets.save(offsets_path)` with updated `last_byte_offset` + `seen_line_sha256`.
  - Add `if __name__ == "__main__":` CLI block using stdlib `argparse`: `--audit`, `--offsets`, `--out` (file path → wraps `JSONLForensicSink`, or URL → `HttpForensicSink`), `--window-s`.
  - Handle audit-file rotation: if `last_byte_offset > size(audit_path)` → reset to 0 + WARN.
- **Files**: `nautilus/forensics/handoff_worker.py`.
- **Done when**: `python -m nautilus.forensics.handoff_worker --audit tests/fixtures/audit/sample.jsonl --offsets /tmp/off.json --out /tmp/inf.jsonl` exits 0 on a small fixture.
- **Verify**: `uv run pytest tests/unit/forensics/test_handoff_worker.py -q || echo "unit test lands in Task 3.6; smoke:"` then `uv run python -c "from nautilus.forensics.handoff_worker import run_worker, WorkerReport; print('OK')"`
- **Commit**: `feat(forensics): add handoff_worker with declared-precedence dedup + offsets idempotency`
- **References**: FR-11, FR-33, NFR-13, AC-5.1, AC-5.3, AC-5.4, AC-5.5, D-20, design §3.7.

### [VERIFY] Task 2.24 — Quality checkpoint (forensic worker + rule pack)
- **Do**: Run toolchain + Phase 1 regression.
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit && uv run pytest tests/integration/test_mvp_e2e.py tests/integration/test_classification_e2e.py -m integration -q`
- **Done when**: All exit 0 — Phase 1 surface + POC milestone still green.
- **Commit**: `chore(phase2): pass checkpoint after forensic worker` (if fixes needed)

### Task 2.25 — Record Phase 1 backwards-compat fixtures (audit line + attestation token)
- **Do**:
  - Run Phase 1 `test_mvp_e2e.py` against `tests/fixtures/nautilus.yaml` (Phase 1 config — no temporal slots, no agents block, no LLM, no API auth). Capture:
    - One `AuditEntry` JSONL line → save to `tests/fixtures/audit/phase1_audit_line.jsonl`.
    - One signed attestation token (`resp.attestation_token`) → save bytes to `tests/fixtures/audit/phase1_attestation_token.jwt`.
  - Commit both fixtures as binary-stable locked content.
- **Files**: `tests/fixtures/audit/phase1_audit_line.jsonl`, `tests/fixtures/audit/phase1_attestation_token.jwt`.
- **Done when**: Both files exist; each is ≥ 1 byte; `AuditEntry.model_validate_json(open(...).read())` succeeds on the audit line.
- **Verify**: `test -s tests/fixtures/audit/phase1_audit_line.jsonl && test -s tests/fixtures/audit/phase1_attestation_token.jwt && uv run python -c "from nautilus.core.models import AuditEntry; AuditEntry.model_validate_json(open('tests/fixtures/audit/phase1_audit_line.jsonl', encoding='utf-8').read().splitlines()[0])"`
- **Commit**: `test(fixtures): record Phase 1 audit line + attestation token for backwards-compat`
- **References**: NFR-5, NFR-6, AC-7.5, design §7.3.

### Task 2.26 — Record LLM cassettes (Anthropic, OpenAI, Local) + 100-prompt determinism fixture
- **Do**:
  - Create `tests/fixtures/llm/anthropic_cassette.yaml`, `openai_cassette.yaml`, `local_cassette.yaml` via `pytest-recording` — each capturing the 3 canonical fixture prompts under `temperature=0`.
  - Create `tests/fixtures/llm_determinism/intent_prompts_100.jsonl` — 100 lines, each `{"intent": "...", "context": {...}, "expected_sensitivity": "...", "expected_data_types": [...]}` covering a routing-representative distribution.
  - Cassettes may be synthesized (mock responses), but must be deterministic and follow the SDK's response schema.
- **Files**: `tests/fixtures/llm/*.yaml`, `tests/fixtures/llm_determinism/intent_prompts_100.jsonl`.
- **Done when**: All files exist; the 100-prompt file has exactly 100 lines; each cassette parses as YAML.
- **Verify**: `test $(wc -l < tests/fixtures/llm_determinism/intent_prompts_100.jsonl) -eq 100 && uv run python -c "import yaml; [yaml.safe_load(open(f, encoding='utf-8')) for f in ['tests/fixtures/llm/anthropic_cassette.yaml','tests/fixtures/llm/openai_cassette.yaml','tests/fixtures/llm/local_cassette.yaml']]; print('OK')"`
- **Commit**: `test(fixtures): record LLM cassettes + 100-prompt determinism fixture`
- **References**: FR-13, FR-15, NFR-12, AC-6.6, design §7.4.

### Task 2.27 — Extend `config loader` with new env-interpolated fields + registry for 4 new adapter types
- **Do**:
  - Edit `nautilus/config/loader.py` to env-interpolate new `${...}` references in `agents.*`, `api.keys`, `attestation.sink.*`, `session_store.dsn`, `analysis.*` (LLM API key envs).
  - Edit `nautilus/config/registry.py` / `Broker.from_config` adapter construction to dispatch on `source.type` for the 4 new types → ES / REST / Neo4j / ServiceNow adapters. Unknown type still raises `ConfigError`.
- **Files**: `nautilus/config/loader.py`, `nautilus/core/broker.py`.
- **Done when**: A YAML with `sources: [{type: elasticsearch, ...}]` constructs an `ElasticsearchAdapter` via `Broker.from_config`; missing env var in `api.keys` raises `ConfigError`.
- **Verify**: `uv run pytest tests/unit/config/test_config_loader.py -k "env_interp or adapter_dispatch" -q || echo "test lands in Task 3.1; smoke:"` then `uv run python -c "from nautilus.config.loader import load_config; print('loader importable')"`
- **Commit**: `feat(config): env-interpolate new fields + dispatch 4 new adapter types`
- **References**: FR-24, AC-1.4, design §5.

### [VERIFY] Task 2.28 — Quality checkpoint (Phase 2 completeness)
- **Do**: Run full toolchain + Phase 1 & POC regression.
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit && uv run pytest tests/integration/test_mvp_e2e.py tests/integration/test_classification_e2e.py -m integration -q`
- **Done when**: All exit 0.
- **Commit**: `chore(phase2): pass Phase 2 completeness checkpoint` (if fixes needed)

---

## Phase 3: Testing — integration harnesses + per-component units + drift-guards

Focus: Cover every component with dedicated unit module; land the 6 integration harnesses from design §7; ≥80% branch coverage (NFR-2).

### Task 3.1 — Unit: `tests/unit/config/test_agent_registry.py` + `test_escalation_loader.py` + `test_config_loader_phase2.py`
- **Do**:
  - `test_agent_registry.py`: (a) get returns record, (b) unknown id raises `UnknownAgentError`, (c) iteration preserves YAML order, (d) Phase 1 YAML without `agents:` loads with empty registry.
  - `test_escalation_loader.py`: (a) default pack produces 1 `EscalationRule`, (b) multiple YAML files load and merge, (c) invalid `action` raises `pydantic.ValidationError`.
  - `test_config_loader_phase2.py`: (a) env interpolation in `api.keys`, (b) missing env in `attestation.sink.url` raises `ConfigError`, (c) 4 new adapter types accepted, (d) Phase 1 fixture still loads.
- **Files**: `tests/unit/config/test_agent_registry.py`, `tests/unit/config/test_escalation_loader.py`, `tests/unit/config/test_config_loader_phase2.py`.
- **Done when**: 11 cases pass total.
- **Verify**: `uv run pytest tests/unit/config/ -q`
- **Commit**: `test(config): add agent registry + escalation loader + Phase 2 loader tests`
- **References**: FR-7, FR-9, FR-24, AC-1.4, AC-3.2, AC-4.2, NFR-5.

### Task 3.2 — Unit: `tests/unit/rules/test_contains_all_external.py` + `test_classification_rule.py` + `test_information_flow_rule.py`
- **Do**:
  - `test_contains_all_external.py`: (a) empty subset ⊆ any superset → TRUE, (b) full overlap → TRUE, (c) partial overlap → FALSE, (d) disjoint → FALSE (AC-3.4).
  - `test_classification_rule.py`: agent `clearance=cui`, source `classification=secret` → `default-classification-deny` fires with salience 150 (AC-1.1, AC-1.3).
  - `test_information_flow_rule.py`: from_agent_clearance dominates classification but to_agent_clearance does not → `information-flow-violation` fires (AC-4.3).
- **Files**: `tests/unit/rules/test_contains_all_external.py`, `tests/unit/rules/test_classification_rule.py`, `tests/unit/rules/test_information_flow_rule.py`.
- **Done when**: 9 cases pass total.
- **Verify**: `uv run pytest tests/unit/rules/ -q`
- **Commit**: `test(rules): add contains-all + classification + information-flow rule tests`
- **References**: FR-2, FR-6, FR-10, AC-1.1, AC-1.3, AC-3.4, AC-4.3.

### Task 3.3 — Unit: `tests/unit/core/test_session_pg_unit.py` + `test_temporal.py` + `test_scope_hash_v2.py`
- **Do**:
  - `test_session_pg_unit.py`: mocked `asyncpg.Pool`. Cases: (a) `setup()` issues idempotent DDL twice without error, (b) `aget`/`aupdate` happy path, (c) `CannotConnectNow` + `on_failure=fail_closed` → `SessionStoreUnavailableError`, (d) same + `fallback_memory` → degrades, (e) degraded-mode requests carry `session_store_mode="degraded_memory"` via broker audit field.
  - `test_temporal.py`: (a) `expires_at` in past → dropped with `scope-expired` denial, (b) `valid_from` in future → dropped, (c) both empty → kept, (d) malformed ISO-8601 → dropped with WARN.
  - `test_scope_hash_v2.py`: (a) no temporal slots → `v1` emitted AND hash byte-identical to Phase 1 fixture (NFR-6), (b) any temporal slot → `v2` emitted, (c) determinism: same inputs → same hash.
- **Files**: `tests/unit/core/test_session_pg_unit.py`, `tests/unit/core/test_temporal.py`, `tests/unit/core/test_scope_hash_v2.py`.
- **Done when**: 12 cases pass total.
- **Verify**: `uv run pytest tests/unit/core/test_session_pg_unit.py tests/unit/core/test_temporal.py tests/unit/core/test_scope_hash_v2.py -q`
- **Commit**: `test(core): add session_pg + temporal + scope_hash_v2 unit tests`
- **References**: FR-3, FR-4, FR-17, FR-19, NFR-6, NFR-7, AC-2.5, AC-7.1, AC-7.2, AC-7.4.

### [VERIFY] Task 3.4 — Quality checkpoint (test batch 1)
- **Do**: Run toolchain.
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit`
- **Done when**: All exit 0.
- **Commit**: `chore(tests): pass batch 1 checkpoint` (if fixes needed)

### Task 3.5 — Unit: `tests/unit/core/test_attestation_sink.py` + `test_declare_handoff.py`
- **Do**:
  - `test_attestation_sink.py`: (a) `NullAttestationSink.emit` is no-op, (b) `FileAttestationSink` writes one line per emit + flush+fsync, (c) `HttpAttestationSink` retries then spills to dead-letter, (d) sink raising does NOT fail `broker.arequest` (AC-14.5), (e) `Broker.aclose()` order: session_store → sink → adapter pool.
  - `test_declare_handoff.py`: (a) allow branch (clearance dominates both ways), (b) deny branch (AC-4.3), (c) escalate branch, (d) unknown receiving agent → `HandoffDecision(action="deny", rule_name="unknown-agent")` (AC-4.2), (e) exactly one audit entry per call (AC-4.4), (f) 50 concurrent calls via `asyncio.gather` produce 50 distinct `handoff_id`s (AC-4.5), (g) zero adapter calls (mock adapters — none invoked).
- **Files**: `tests/unit/core/test_attestation_sink.py`, `tests/unit/core/test_declare_handoff.py`.
- **Done when**: 12 cases pass.
- **Verify**: `uv run pytest tests/unit/core/test_attestation_sink.py tests/unit/core/test_declare_handoff.py -q`
- **Commit**: `test(core): add attestation_sink + declare_handoff unit tests`
- **References**: FR-8, FR-10, FR-28, FR-29, AC-4.1, AC-4.2, AC-4.3, AC-4.4, AC-4.5, AC-14.5, AC-14.6.

### Task 3.6 — Unit: `tests/unit/forensics/test_handoff_worker.py` + `test_offsets.py` + `test_sinks.py`
- **Do**:
  - `test_offsets.py`: (a) round-trip save/load, (b) atomic rename via `os.replace`, (c) corruption detection (truncated JSON, non-monotonic offset) raises `OffsetsCorruptError`, (d) bounded set behavior (10**6 cap).
  - `test_sinks.py`: (a) JSONL sink writes + flushes, (b) HTTP sink POSTs with retry (mocked via `respx`).
  - `test_handoff_worker.py`: (a) empty audit → 0 records; (b) 100-line synthetic audit with 2 shared-session events → 1 `InferredHandoff`; (c) re-run same audit+offsets → 0 new records (NFR-13); (d) declared handoff within window in same audit → inferred dropped (AC-5.3); (e) audit rotation (offset > file size) → reset to 0 + WARN.
- **Files**: `tests/unit/forensics/test_handoff_worker.py`, `tests/unit/forensics/test_offsets.py`, `tests/unit/forensics/test_sinks.py`.
- **Done when**: 11 cases pass.
- **Verify**: `uv run pytest tests/unit/forensics/ -q`
- **Commit**: `test(forensics): add worker + offsets + sinks unit tests`
- **References**: FR-11, FR-12, FR-33, NFR-13, AC-5.1, AC-5.3, AC-5.4.

### Task 3.7 — Unit: `tests/unit/analysis/test_fallback.py` + `test_anthropic.py` + `test_openai.py` + `test_local.py` + `test_prompt_snapshot.py`
- **Do**:
  - `test_fallback.py`: (a) success path returns `(IntentAnalysis, LLMProvenance(fallback_used=False))`, (b) `TimeoutError` → fallback with `fallback_used=True`, (c) `LLMProviderError` → fallback, (d) `pydantic.ValidationError` (non-conforming JSON) → fallback, (e) `mode="llm-only"` + error → raises (AC-6.3).
  - `test_anthropic.py`, `test_openai.py`, `test_local.py`: each uses its recorded cassette; asserts returned `IntentAnalysis` fields match expected (AC-6.6).
  - `test_prompt_snapshot.py`: reads `intent_v1.txt`, asserts `sha256(content)` matches a locked expected hash (FR-15).
- **Files**: `tests/unit/analysis/test_fallback.py`, `tests/unit/analysis/llm/test_anthropic.py`, `tests/unit/analysis/llm/test_openai.py`, `tests/unit/analysis/llm/test_local.py`, `tests/unit/analysis/llm/test_prompt_snapshot.py`.
- **Done when**: 11 cases pass.
- **Verify**: `uv run pytest tests/unit/analysis/ -q`
- **Commit**: `test(analysis): add FallbackIntentAnalyzer + 3 provider cassette tests + prompt snapshot`
- **References**: FR-13, FR-14, FR-15, AC-6.1, AC-6.2, AC-6.3, AC-6.6.

### [VERIFY] Task 3.8 — Quality checkpoint (test batch 2)
- **Do**: Run toolchain.
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit`
- **Done when**: All exit 0.
- **Commit**: `chore(tests): pass batch 2 checkpoint` (if fixes needed)

### Task 3.9 — Unit: `tests/unit/adapters/test_elasticsearch.py` + `test_rest.py` (incl. drift + SSRF)
- **Do**:
  - `test_elasticsearch.py`: (a) each operator in `_OPERATOR_ALLOWLIST` round-trips through the ES DSL per AC-8.2 — drift test (NFR-4), (b) bad `index` raises at connect, (c) `LIKE` leading-wildcard WARN but proceeds, (d) static grep: zero f-string+`Search.query(` within 5 lines in `elasticsearch.py` (AC-8.4).
  - `test_rest.py`: (a) operator→template drift test (every operator has a default or is explicitly-rejected, NFR-4 AC-9.5), (b) redirect to different host → `SSRFBlockedError` (NFR-17, AC-9.2), (c) undeclared endpoint path in scope → `ScopeEnforcementError`, (d) bearer/basic/mtls/none auth all construct, (e) respx mock end-to-end: GET /widgets with `f=x` query param.
- **Files**: `tests/unit/adapters/test_elasticsearch.py`, `tests/unit/adapters/test_rest.py`.
- **Done when**: 9 cases pass.
- **Verify**: `uv run pytest tests/unit/adapters/test_elasticsearch.py tests/unit/adapters/test_rest.py -q`
- **Commit**: `test(adapters): add ES + REST unit tests with drift-guard + SSRF`
- **References**: FR-20, FR-21, AC-8.1, AC-8.2, AC-8.4, AC-9.1, AC-9.2, AC-9.3, AC-9.4, AC-9.5, NFR-4, NFR-17.

### Task 3.10 — Unit: `tests/unit/adapters/test_neo4j.py` + `test_servicenow.py` (incl. drift + injection)
- **Do**:
  - `test_neo4j.py`: (a) operator→Cypher round-trip drift test (NFR-4), (b) bad label rejected at connect (AC-10.1), (c) `LIKE` with `like_style="starts_with"` → `STARTS WITH $p0`; with `"regex"` → `=~ $p0` + CONFIG WARN (AC-10.3), (d) property identifier regex-validated + backticked, (e) `close()` idempotent.
  - `test_servicenow.py`: (a) operator→encoded-query round-trip drift (NFR-4), (b) `_sanitize_sn_value("bad^value")` → `ScopeEnforcementError("sn-injection-rejected")` (NFR-18), (c) same for `\n` and `\r`, (d) respx mock: full operator set composes one `sysparm_query` string with `^` separators, (e) OAuth refresh NOT supported (no related code path).
- **Files**: `tests/unit/adapters/test_neo4j.py`, `tests/unit/adapters/test_servicenow.py`.
- **Done when**: 10 cases pass.
- **Verify**: `uv run pytest tests/unit/adapters/test_neo4j.py tests/unit/adapters/test_servicenow.py -q`
- **Commit**: `test(adapters): add Neo4j + ServiceNow unit tests with drift + injection`
- **References**: FR-22, FR-23, AC-10.1, AC-10.2, AC-10.3, AC-11.1, AC-11.2, AC-11.3, AC-11.4, NFR-4, NFR-18.

### Task 3.11 — Unit: `tests/unit/transport/test_auth.py`
- **Do**:
  - Cases: (a) `verify_api_key("good", ["good","other"])` passes; (b) `verify_api_key("bad", ["good"])` raises HTTP 401; (c) `secrets.compare_digest` is used (patch and assert call); (d) `proxy_trust` mode reads `X-Forwarded-User` header value as identity; (e) both modes return the resolved identity string.
- **Files**: `tests/unit/transport/test_auth.py`.
- **Done when**: 5 cases pass.
- **Verify**: `uv run pytest tests/unit/transport/test_auth.py -q`
- **Commit**: `test(transport): add auth unit tests (api_key + proxy_trust)`
- **References**: FR-26, AC-12.2, AC-12.3.

### [VERIFY] Task 3.12 — Quality checkpoint (test batch 3)
- **Do**: Run toolchain.
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit`
- **Done when**: All exit 0.
- **Commit**: `chore(tests): pass batch 3 checkpoint` (if fixes needed)

### Task 3.13 — Unit: `tests/unit/transport/test_fastapi_unit.py` + `test_mcp_unit.py` + `tests/unit/test_cli.py`
- **Do**:
  - `test_fastapi_unit.py` (uses `httpx.AsyncClient(transport=ASGITransport(app))`): (a) lifespan startup builds broker singleton; (b) `/healthz` → 200 static; (c) `/readyz` → 503 before startup, 200 after; (d) `POST /v1/request` → 200 + 1 audit line (NFR-15); (e) `POST /v1/query` behaves identically to `/v1/request` (alias, D-9); (f) missing/bad API key → 401 (AC-12.2); (g) `GET /v1/sources` returns metadata only (no secrets).
  - `test_mcp_unit.py`: session-id resolution table — (a) `context["session_id"]` present → used + `session_id_source="context"`; (b) http mode, no `context.session_id` → `ctx.session_id` used + `session_id_source="transport"`; (c) stdio, none present → `ctx.request_id` used + `session_id_source="stdio_request_id"`; (d) `agent_id` is verbatim, never `client_id` (AC-13.3).
  - `test_cli.py`: (a) `nautilus version` exit 0; (b) `nautilus health --url http://bogus` exit non-zero; (c) `nautilus serve --config /bogus` exits non-zero with error BEFORE network bind (AC-15.5); (d) `--air-gapped` overrides `analysis.mode` to `"pattern"` + WARN (AC-6.4, NFR-1).
- **Files**: `tests/unit/transport/test_fastapi_unit.py`, `tests/unit/transport/test_mcp_unit.py`, `tests/unit/test_cli.py`.
- **Done when**: 15 cases pass.
- **Verify**: `uv run pytest tests/unit/transport/test_fastapi_unit.py tests/unit/transport/test_mcp_unit.py tests/unit/test_cli.py -q`
- **Commit**: `test(transport+cli): add FastAPI + MCP + CLI unit tests`
- **References**: FR-25, FR-26, FR-27, FR-30, AC-6.4, AC-12.1, AC-12.2, AC-12.3, AC-12.4, AC-12.5, AC-13.3, AC-15.2, AC-15.3, AC-15.5, NFR-1, NFR-15.

### Task 3.14 — Integration: `test_session_store_e2e.py` + `test_backwards_compat.py`
- **Do**:
  - `test_session_store_e2e.py` (uses `pg_container` fixture): (a) `Broker.setup()` idempotent on repeated calls (AC-2.2); (b) 2 requests sharing `session_id` — second sees accumulated state in Fathom facts (AC-2.1); (c) restart broker — new broker sees same state via Postgres (AC-2.4); (d) unreachable DSN + `on_failure="fail_closed"` → request raises `SessionStoreUnavailableError` + audit entry with `error_type`.
  - `test_backwards_compat.py`: (a) `AuditEntry.model_validate_json(open("tests/fixtures/audit/phase1_audit_line.jsonl").read())` succeeds (NFR-5); (b) Phase 1 attestation token from `tests/fixtures/audit/phase1_attestation_token.jwt` verifies under the Phase 2 verifier unchanged (NFR-6, AC-7.5).
- **Files**: `tests/integration/test_session_store_e2e.py`, `tests/integration/test_backwards_compat.py`.
- **Done when**: 6 cases pass.
- **Verify**: `uv run pytest tests/integration/test_session_store_e2e.py tests/integration/test_backwards_compat.py -m integration -q`
- **Commit**: `test(integration): session store e2e + Phase 1 backwards-compat`
- **References**: FR-3, FR-4, NFR-5, NFR-6, AC-2.1, AC-2.2, AC-2.4, AC-2.5, AC-7.5, design §7.3.

### Task 3.15 — Integration: `test_elasticsearch_e2e.py` + `test_neo4j_e2e.py` + `test_rest_e2e.py` + `test_servicenow_e2e.py`
- **Do**:
  - `test_elasticsearch_e2e.py` (testcontainers ES): seed index with mixed docs; scoped query with `severity IN ('high','critical')` returns only matching; `LIKE` wildcard + operator allowlist drift round-trip (AC-8.5).
  - `test_neo4j_e2e.py` (testcontainers Neo4j): seeded `(:Person)` nodes; scoped WHERE returns matching rows; `close()` idempotent (AC-10.5).
  - `test_rest_e2e.py`: spin up a uvicorn mock upstream app in-process; `RestAdapter` round-trips a request against it; SSRF test asserts redirect to different host fails closed.
  - `test_servicenow_e2e.py`: use `httpx.MockTransport`; full operator set round-trips through `sysparm_query`; injection test rejects `^`/`\n`/`\r` (AC-11.5).
- **Files**: `tests/integration/test_elasticsearch_e2e.py`, `tests/integration/test_neo4j_e2e.py`, `tests/integration/test_rest_e2e.py`, `tests/integration/test_servicenow_e2e.py`.
- **Done when**: 4 integration tests pass (may be ~12 cases total).
- **Verify**: `uv run pytest tests/integration/test_elasticsearch_e2e.py tests/integration/test_neo4j_e2e.py tests/integration/test_rest_e2e.py tests/integration/test_servicenow_e2e.py -m integration -q`
- **Commit**: `test(integration): 4 new-adapter e2e tests (ES, Neo4j, REST, ServiceNow)`
- **References**: FR-20, FR-21, FR-22, FR-23, AC-8.5, AC-9.5, AC-10.5, AC-11.5, design §7.1.

### [VERIFY] Task 3.16 — Quality checkpoint (test batch 4)
- **Do**: Run toolchain + integration tier.
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit && uv run pytest -m integration -q`
- **Done when**: All exit 0.
- **Commit**: `chore(tests): pass batch 4 checkpoint` (if fixes needed)

### Task 3.17 — Integration harnesses: latency + fault-injection + determinism + forensic idempotency + MCP e2e
- **Do**:
  - `test_fastapi_latency_harness.py` (AC-12.6, design §7.5): `pg_container` + `create_app`; `httpx.AsyncClient(transport=ASGITransport(app))` issues 1000 sequential `POST /v1/request`; discard first 100; compute p95 over remaining 900 excluding `AdapterResult.duration_ms`; assert p95 < 200 ms. Mark `@pytest.mark.slow`.
  - `test_attestation_sink_fault_injection.py` (NFR-16, design §7.6): `HttpAttestationSink` wired to a mock that alternates success/raise; 1000 requests via `broker.arequest`; assert (a) all 1000 returned `BrokerResponse` (0 broker failures), (b) 1000 audit entries written, (c) WARN log per failed emit.
  - `test_llm_determinism_harness.py` (NFR-12, design §7.4): run each provider against recorded cassette over `intent_prompts_100.jsonl`; assert ≥95/100 match exactly on `data_types_needed` + `estimated_sensitivity`.
  - `test_forensic_worker_e2e.py` (FR-11, NFR-13, design §7.7): synthesize 10k-line audit log with embedded shared-session + source-overlap + classification-delta signals AND one declared handoff within window; run worker → verify expected `InferredHandoff`s emitted AND declared tuple NOT duplicated; re-run worker → 0 new records.
  - `test_mcp_e2e.py`: stdio transport via subprocess + in-process streamable-http; tool call `nautilus.request` produces exactly one audit entry; 1:1 ratio (NFR-15).
- **Files**: `tests/integration/test_fastapi_latency_harness.py`, `tests/integration/test_attestation_sink_fault_injection.py`, `tests/integration/test_llm_determinism_harness.py`, `tests/integration/test_forensic_worker_e2e.py`, `tests/integration/test_mcp_e2e.py`.
- **Done when**: All 5 harness files pass under `-m integration`.
- **Verify**: `uv run pytest tests/integration/test_fastapi_latency_harness.py tests/integration/test_attestation_sink_fault_injection.py tests/integration/test_llm_determinism_harness.py tests/integration/test_forensic_worker_e2e.py tests/integration/test_mcp_e2e.py -m integration -q`
- **Commit**: `test(integration): latency + fault-injection + determinism + forensic-idempotency + MCP e2e harnesses`
- **References**: FR-11, FR-27, NFR-12, NFR-13, NFR-15, NFR-16, AC-5.3, AC-5.4, AC-12.6, design §7.4, §7.5, §7.6, §7.7.

### Task 3.18 — Coverage gate (≥80% branch) + dedicated-unit-module presence check
- **Do**:
  - Run `uv run pytest -m "unit or integration" --cov=nautilus --cov-branch --cov-report=term-missing --cov-fail-under=80`. Add targeted tests or `# pragma: no cover` for genuinely unreachable branches (each with an inline comment). Pragma budget ≤ 5 additions above the current Phase-1 baseline.
  - Extend `tests/unit/test_module_presence.py` (from core-broker Task 3.19) to also assert the new test modules exist: `test_session_pg_unit.py`, `test_temporal.py`, `test_scope_hash_v2.py`, `test_attestation_sink.py`, `test_declare_handoff.py`, `test_elasticsearch.py`, `test_rest.py`, `test_neo4j.py`, `test_servicenow.py`, `test_fallback.py`, `test_auth.py`, `test_fastapi_unit.py`, `test_mcp_unit.py`, `test_cli.py`, `test_handoff_worker.py`, `test_offsets.py`, `test_sinks.py`, `test_contains_all_external.py`, `test_classification_rule.py`, `test_information_flow_rule.py`.
- **Files**: any `tests/unit/**/test_*.py` needing gap fill, `tests/unit/test_module_presence.py`.
- **Done when**: Branch coverage ≥80%; meta-test passes; ≤5 new `# pragma: no cover` lines added.
- **Verify**: `uv run pytest -m "unit or integration" --cov=nautilus --cov-branch --cov-fail-under=80 -q && uv run pytest tests/unit/test_module_presence.py -q`
- **Commit**: `test(coverage): raise branch coverage ≥80% + enforce dedicated-module presence`
- **References**: NFR-2, AC-9.4 (Phase 1), design §7.

### [VERIFY] Task 3.19 — Full test + coverage gate
- **Do**: Run full quality + coverage gate.
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit && uv run pytest -m integration -q && uv run pytest -m "unit or integration" --cov=nautilus --cov-branch --cov-fail-under=80 -q`
- **Done when**: All exit 0.
- **Commit**: `chore(tests): pass full Phase 3 gate` (if fixes needed)

---

## Phase 4: Quality Gates — CI, docs, PR lifecycle

### Task 4.1 — Polish `pyproject.toml` metadata + re-run `uv build`
- **Do**:
  - Update `[project].description` to include reasoning-engine scope; keep existing `authors`, `license`, `readme`, `classifiers`.
  - Confirm `[project.optional-dependencies]` includes `llm-anthropic`, `llm-openai`, and extended `dev`.
  - `uv build` produces a wheel without warnings.
- **Files**: `pyproject.toml`.
- **Done when**: `uv build` succeeds; wheel contains `nautilus/analysis/llm/prompts/intent_v1.txt` (a data file).
- **Verify**: `uv build && uv run python -c "import zipfile, glob; w = sorted(glob.glob('dist/nautilus-*.whl'))[-1]; names = zipfile.ZipFile(w).namelist(); assert any(n.endswith('intent_v1.txt') for n in names), names"`
- **Commit**: `chore(packaging): update pyproject metadata + confirm wheel includes prompt assets`
- **References**: NFR-10, NFR-11.

### Task 4.2 — License scan (reject GPL/AGPL/LGPL)
- **Do**:
  - Run `uv run pip-licenses --fail-on="GPL;AGPL;LGPL" --format=markdown` over the current environment.
  - If any license matches — substitute or pin-around the offending dep; document the choice in a code comment.
- **Files**: none (runtime check only; may update `pyproject.toml` if substitution needed).
- **Done when**: pip-licenses exits 0 with no GPL-family matches.
- **Verify**: `uv run pip-licenses --fail-on="GPL;AGPL;LGPL"`
- **Commit**: `chore(license): pass GPL-family license scan` (only if fixes needed)
- **References**: NFR-11.

### Task 4.3 — Docstring sweep for Phase 2 public surfaces
- **Do**:
  - Add Google-style docstrings (Args/Returns/Raises) to every NEW public class/method added in Phases 1–2: `PostgresSessionStore`, `AgentRegistry`, `Broker.declare_handoff`, `Broker.setup`, `FallbackIntentAnalyzer`, `AnthropicProvider`, `OpenAIProvider`, `LocalInferenceProvider`, `ElasticsearchAdapter`, `RestAdapter`, `Neo4jAdapter`, `ServiceNowAdapter`, `AttestationSink`, `NullAttestationSink`, `FileAttestationSink`, `HttpAttestationSink`, `TemporalFilter`, `run_worker`, `ProcessedOffsets`, `create_app`, `create_server`.
  - Extend the ast-based docstring scan from Phase 1 core-broker Task 4.3 to cover the new modules.
- **Files**: all new/modified Phase 1–2 public modules.
- **Done when**: ast scan finds zero undocumented public symbols under `nautilus/`.
- **Verify**: `uv run python -c "import ast, pathlib; missing=[]; [missing.extend([(str(p), n.name) for n in ast.walk(ast.parse(p.read_text(encoding='utf-8'))) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and not n.name.startswith('_') and not ast.get_docstring(n)]) for p in pathlib.Path('nautilus').rglob('*.py')]; assert not missing, missing[:5]"`
- **Commit**: `docs: add docstrings to reasoning-engine public surfaces`
- **References**: design §3.

### [VERIFY] Task 4.4 — Quality checkpoint (quality batch 1)
- **Do**: Run toolchain.
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit`
- **Done when**: All exit 0.
- **Commit**: `chore(quality): pass checkpoint after metadata + license + docstrings` (if fixes needed)

### Task 4.5 — README update: reasoning-engine quickstart
- **Do**:
  - Extend `README.md` with a new "Reasoning Engine" section: install extras (`uv add 'nautilus[llm-anthropic]'`), 15-line quickstart loading a YAML with `agents:` block + `session_store.backend: postgres`, calling `broker.declare_handoff(...)`, explaining `--air-gapped` and the `/v1/request` REST endpoint.
  - Link to `specs/reasoning-engine/design.md` and `specs/reasoning-engine/requirements.md`.
- **Files**: `README.md`.
- **Done when**: README contains string `declare_handoff` and `create_app` and `nautilus serve`; still ≤ 220 lines.
- **Verify**: `uv run python -c "import pathlib; t = pathlib.Path('README.md').read_text(encoding='utf-8'); assert 'declare_handoff' in t and 'create_app' in t and 'nautilus serve' in t and len(t.splitlines()) <= 220, len(t.splitlines())"`
- **Commit**: `docs: add reasoning-engine quickstart to README`
- **References**: design §3.15.

### Task 4.6 — Docker smoke test in CI (size + no-shell + health)
- **Do**:
  - Add `tests/integration/test_docker_image.py` (marked `@pytest.mark.docker`): builds image locally; asserts size ≤ 200 MB (NFR-10); asserts `docker run --entrypoint sh nautilus:test` fails (no shell in distroless — AC-16.5); asserts `HEALTHCHECK` directive invokes `nautilus health` (parsed from `docker image inspect`).
  - Test is skipped when Docker daemon is not available (`pytest.importorskip("docker")` or simple `shutil.which("docker")` gate).
- **Files**: `tests/integration/test_docker_image.py`.
- **Done when**: Test passes on a machine with docker; skips cleanly without docker.
- **Verify**: `uv run pytest tests/integration/test_docker_image.py -q`
- **Commit**: `test(integration): docker image size + no-shell + healthcheck assertions`
- **References**: FR-31, FR-32, AC-16.2, AC-16.4, AC-16.5, NFR-10.

### [VERIFY] Task 4.7 — Quality checkpoint (quality batch 2)
- **Do**: Run toolchain after README + Docker smoke land, before the adapter-safety grep/drift-guard batch. Keeps cadence inside Phase 4 aligned with Phase 1/2/3 gates.
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit && uv run pytest tests/integration/test_mvp_e2e.py -m integration -q`
- **Done when**: All exit 0; Phase-1 MVP E2E still passes.
- **Commit**: `chore(phase4): pass checkpoint after docs + docker smoke` (if fixes needed)

### Task 4.8 — Static grep checks for new adapters (SQL-injection-style)
- **Do**:
  - Extend `tests/unit/test_sql_injection_static.py` (from core-broker) to also scan `elasticsearch.py` for `f"..."` + `Search.query(` within 5 lines (AC-8.4), `neo4j.py` for f-string + `execute_query(`, `rest.py` for manual URL concatenation (no `f"{base_url}/"`), `servicenow.py` for f-string near encoded-query building.
  - Keep the `# noqa: SQLGREP` allowlist discipline.
- **Files**: `tests/unit/test_sql_injection_static.py`.
- **Done when**: Grep test passes across all four new adapter modules; 0 hits.
- **Verify**: `uv run pytest tests/unit/test_sql_injection_static.py -q`
- **Commit**: `test(adapters): extend injection grep to ES/Neo4j/REST/ServiceNow`
- **References**: AC-8.4, NFR-4.

### Task 4.9 — Operator-allowlist drift-guard meta-test for all 4 new adapters
- **Do**:
  - Create `tests/unit/adapters/test_allowlist_drift.py` (distinct from per-adapter drift inside Task 3.9 / 3.10): a single parametric meta-test that imports `_OPERATOR_ALLOWLIST` from `nautilus/adapters/base.py` and asserts each of ES, Neo4j, REST, ServiceNow declares a mapping (or per-endpoint rejection, REST only) for every listed operator. Fails loud when a new operator is added to the allowlist without updating ALL adapters (NFR-4, design §7.2).
- **Files**: `tests/unit/adapters/test_allowlist_drift.py`.
- **Done when**: Test passes. Removing any one operator from any one adapter's mapping fails it.
- **Verify**: `uv run pytest tests/unit/adapters/test_allowlist_drift.py -q`
- **Commit**: `test(adapters): cross-adapter operator-allowlist drift guard`
- **References**: NFR-4, design §7.2.

### Task 4.10 — Final local CI sweep
- **Do**: Run the complete gate as a single command chain:
  - `uv run ruff check && uv run ruff format --check`
  - `uv run pyright`
  - `uv run pytest -m unit`
  - `uv run pytest -m integration -q`
  - `uv run pytest -m "unit or integration" --cov=nautilus --cov-branch --cov-fail-under=80 -q`
  - `uv build`
  - `uv run pip-licenses --fail-on="GPL;AGPL;LGPL"`
- **Files**: none.
- **Done when**: every command exits 0.
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit && uv run pytest -m integration -q && uv run pytest -m "unit or integration" --cov=nautilus --cov-branch --cov-fail-under=80 -q && uv build && uv run pip-licenses --fail-on="GPL;AGPL;LGPL"`
- **Commit**: `chore(ci): pass final local gate` (if fixes needed)
- **References**: NFR-2, NFR-3, NFR-10, NFR-11.

### Task 4.11 — Create PR and verify CI
- **Do**:
  - Confirm current branch is a feature branch (not `main`/`master`): `git branch --show-current`.
  - `git push -u origin "$(git branch --show-current)"`.
  - `gh pr create --title "feat(reasoning-engine): Phase 2 + Phase 3 reasoning + transport + adapters" --body-file /tmp/pr-body.md` where `/tmp/pr-body.md` summarizes US-1..US-16 delivered, notable architectural decisions (D-1..D-20), Phase-1 backwards-compat preserved, and links to `specs/reasoning-engine/design.md`.
  - `gh pr checks --watch` until green.
- **Files**: none.
- **Done when**: All CI checks show passing.
- **Verify**: `gh pr checks | grep -qi "fail" && exit 1 || echo PR_GREEN`
- **Commit**: none (PR-level).
- **References**: NFR-2, NFR-3.

### Task 4.12 — Tag `v0.2.0-alpha`
- **Do**: After PR merge (or pre-merge if approved), `git tag -a v0.2.0-alpha -m "Nautilus Reasoning Engine Phase 2 + Phase 3 alpha"`; do NOT push unless operator approves.
- **Files**: none (git ref only).
- **Done when**: `git tag -l | grep -q "^v0.2.0-alpha$"`.
- **Verify**: `git tag -l | grep -q "^v0.2.0-alpha$" && echo TAG_CREATED`
- **Commit**: none (tag only).
- **References**: release hygiene.

---

## Phase 5: VE — full-pipeline end-to-end verification including forensic worker

Five sequential tasks: one startup, three checks (REST + MCP + declare_handoff + forensic), one cleanup. VE2 is decomposed into three check tasks for clarity and independent verify commands. VE-cleanup (VE3) MUST run even if prior checks fail.

### Task 5.1 — VE1: boot Postgres + pgvector + Elasticsearch testcontainers + launch `nautilus serve --transport both`
- **Do**:
  - Add `.ve-*.txt` to `.gitignore` if not already done.
  - Start Postgres+pgvector container detached: `docker run -d --rm -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres -e POSTGRES_DB=nautilus -p 0:5432 pgvector/pgvector:pg17 > .ve-pg-cid.txt`
  - Resolve port + DSN: `PG_PORT=$(docker port "$(cat .ve-pg-cid.txt)" 5432/tcp | awk -F: '{print $NF}' | head -n1)` → `echo "postgresql://postgres:postgres@localhost:${PG_PORT}/nautilus" > .ve-pg-dsn.txt`
  - Start Elasticsearch stub: `docker run -d --rm -e discovery.type=single-node -e xpack.security.enabled=false -p 0:9200 docker.elastic.co/elasticsearch/elasticsearch:8.15.0 > .ve-es-cid.txt`; resolve `ES_PORT` + write `.ve-es-url.txt`.
  - Healthcheck both (60 s ceiling each): `pg_isready` loop + `curl -sf "http://localhost:${ES_PORT}"` loop.
  - `psql "$(cat .ve-pg-dsn.txt)" -c "CREATE EXTENSION IF NOT EXISTS vector;" && psql "$(cat .ve-pg-dsn.txt)" -f tests/fixtures/seed.sql && psql "$(cat .ve-pg-dsn.txt)" -f tests/fixtures/reasoning/ve-seed.sql` (ve-seed adds `agents` table if needed for AgentRegistry tests).
  - Render `tests/fixtures/ve-config.yaml` (ship this file as part of this task): two sources (pgvector + elasticsearch), `session_store.backend: postgres` with `dsn: ${VE_PG_DSN}`, `attestation.sink.type: file, path: /tmp/ve-attestation.jsonl`, `api.keys: [${VE_API_KEY}]`, `agents:` block with two entries (`orch-a: clearance=secret`, `orch-b: clearance=cui`), audit path `/tmp/ve-audit.jsonl`.
  - Export `VE_PG_DSN="$(cat .ve-pg-dsn.txt)"`, `VE_ES_URL="$(cat .ve-es-url.txt)"`, `VE_API_KEY="ve-test-key"`.
  - Launch broker in background: `uv run nautilus serve --transport both --config tests/fixtures/ve-config.yaml --bind 127.0.0.1:18080 > .ve-serve.log 2>&1 & echo $! > .ve-serve-pid.txt`
  - Wait for `/readyz` 200 (60 s ceiling): `for i in $(seq 1 60); do curl -sf http://127.0.0.1:18080/readyz && break || sleep 1; done`
- **Files**: `tests/fixtures/reasoning/ve-seed.sql` (new), `tests/fixtures/ve-config.yaml` (new); `.gitignore` (extend). Ephemeral: `.ve-pg-cid.txt`, `.ve-pg-dsn.txt`, `.ve-es-cid.txt`, `.ve-es-url.txt`, `.ve-serve-pid.txt`, `.ve-serve.log`, `/tmp/ve-audit.jsonl`, `/tmp/ve-attestation.jsonl`.
- **Done when**: Both containers running; `/readyz` returns 200.
- **Verify**: `test -f .ve-pg-dsn.txt && test -f .ve-es-url.txt && test -f .ve-serve-pid.txt && curl -sf http://127.0.0.1:18080/readyz | grep -q '200\|ready\|ok' && echo VE1_PASS`
- **Commit**: `chore(ve): add ve-config fixture + VE seed SQL; ignore VE artifacts`
- **References**: FR-25, FR-27, AC-12.4, design §7.1.

### Task 5.2 — VE2a: REST end-to-end — classification + escalation + pattern-matcher + temporal + attestation
- **Do**:
  - `curl -sf -H "X-API-Key: ${VE_API_KEY}" -H "Content-Type: application/json" -X POST http://127.0.0.1:18080/v1/request -d '{"agent_id":"orch-a","intent":"enrich incident with email phone dob ssn for threat hunting","context":{"clearance":"secret","purpose":"threat-hunt","session_id":"ve-s1","compartments":"cti","embedding":[0.1,0.2,0.3]}}' -o .ve-resp-rest.json`
  - Assertions via `jq`:
    - `.attestation_token != null`
    - `.sources_queried | length > 0`
    - `.denial_records | map(.rule_name) | any(. == "escalation-confidential" or . == "default-classification-deny" or . == "pii-aggregation-confidential")` (escalation rule fired)
  - Tail `/tmp/ve-audit.jsonl`: parse last line as `AuditEntry`; assert `.scope_hash_version` in `["v1","v2"]`; `.session_store_mode == "primary"`; `.event_type == "request"`; `.fallback_used == null or .fallback_used == true` (no LLM provider configured → pattern analyzer used).
  - Issue a second request with `"expires_at":"2030-01-01T00:00:00Z"` on a scope constraint (via a scope-generating rule in the YAML's ruleset) — last audit line should carry `.scope_hash_version == "v2"`.
- **Files**: none (uses ephemeral artifacts from VE1).
- **Done when**: Both curl calls succeed; audit line assertions pass.
- **Verify**: `export VE_API_KEY=ve-test-key && curl -sf -H "X-API-Key: ${VE_API_KEY}" -H "Content-Type: application/json" -X POST http://127.0.0.1:18080/v1/request -d '{"agent_id":"orch-a","intent":"find pii","context":{"clearance":"secret","purpose":"t","session_id":"ve-s1","embedding":[0.1,0.2,0.3]}}' | uv run python -c "import sys, json; r = json.load(sys.stdin); assert r.get('attestation_token'); assert r.get('request_id'); print('VE2a_PASS')"`
- **Commit**: None
- **References**: FR-1, FR-2, FR-6, FR-7, FR-17, FR-19, FR-25, AC-1.3, AC-3.1, AC-7.4, AC-12.1, NFR-5, NFR-15.

### Task 5.3 — VE2b: MCP stdio tool-call round-trip + `Broker.declare_handoff` between two agents
- **Do**:
  - MCP round-trip: spawn an `mcp` client subprocess speaking stdio to a co-located `nautilus serve --transport mcp --mcp-mode stdio --config tests/fixtures/ve-config.yaml` instance; issue one `tools/call` for `nautilus_request` with `agent_id="orch-a"`, `intent="query vulns"`, `context={"session_id":"ve-mcp-1","clearance":"secret","purpose":"ops"}`.
  - Assert: response is a valid `BrokerResponse`; exactly one new line appended to `/tmp/ve-audit.jsonl`; that line's `.session_id_source == "stdio_request_id"` (no `context.session_id` supplied in a second test invocation) or `"context"` (when supplied).
  - `declare_handoff`: using a short Python script that imports `Broker.from_config` against the same config, call `await broker.declare_handoff(source_agent_id="orch-a", receiving_agent_id="orch-b", session_id="ve-handoff-1", data_classifications=["secret"])`. Assert `HandoffDecision.action == "deny"` (orch-b clearance is `cui` < `secret`) and one audit line appended with `event_type="handoff_declared"`.
- **Files**: `tests/fixtures/reasoning/ve-mcp-client.py` (small synchronous client script) + `tests/fixtures/reasoning/ve-handoff.py` (declare_handoff caller).
- **Done when**: Both scripts exit 0 with expected assertions; audit file has the expected new lines.
- **Verify**: `uv run python tests/fixtures/reasoning/ve-mcp-client.py && uv run python tests/fixtures/reasoning/ve-handoff.py && echo VE2b_PASS`
- **Commit**: `chore(ve): add VE MCP + declare_handoff client scripts`
- **References**: FR-8, FR-10, FR-27, AC-4.1, AC-4.3, AC-13.1, AC-13.3, NFR-15.

### Task 5.4 — VE2c: forensic worker over synthesized audit emits `InferredHandoff`
- **Do**:
  - Append a synthetic undeclared-handoff signal block to `/tmp/ve-audit.jsonl` (one `request` entry from `orch-c` on `session_id="ve-inferred-1"` followed by one from `orch-d` on the same `session_id` within window, sharing a source — NO matching `handoff_declared` event).
  - Run the forensic worker: `uv run python -m nautilus.forensics.handoff_worker --audit /tmp/ve-audit.jsonl --offsets /tmp/ve-forensic.offsets --out /tmp/ve-inferred.jsonl --window-s 3600`
  - Assertions:
    - Exit code 0.
    - `/tmp/ve-inferred.jsonl` contains exactly 1 line for `(session_id="ve-inferred-1", source_agent in {orch-c,orch-d})` parseable as `InferredHandoff`.
    - Re-run the worker; `/tmp/ve-inferred.jsonl` line count unchanged (idempotency, NFR-13).
    - The declared handoff from VE2b (session `ve-handoff-1`) does NOT produce an `InferredHandoff` (declared-precedence dedup, AC-5.3).
- **Files**: none (ephemeral).
- **Done when**: Worker emits expected `InferredHandoff`; re-run is a no-op.
- **Verify**: `uv run python -m nautilus.forensics.handoff_worker --audit /tmp/ve-audit.jsonl --offsets /tmp/ve-forensic.offsets --out /tmp/ve-inferred.jsonl --window-s 3600 && BEFORE=$(wc -l < /tmp/ve-inferred.jsonl) && uv run python -m nautilus.forensics.handoff_worker --audit /tmp/ve-audit.jsonl --offsets /tmp/ve-forensic.offsets --out /tmp/ve-inferred.jsonl --window-s 3600 && AFTER=$(wc -l < /tmp/ve-inferred.jsonl) && [ "$BEFORE" -eq "$AFTER" ] && uv run python -c "import json, pathlib; lines=[json.loads(l) for l in pathlib.Path('/tmp/ve-inferred.jsonl').read_text(encoding='utf-8').splitlines() if l]; assert any(r.get('session_id')=='ve-inferred-1' for r in lines); assert not any(r.get('session_id')=='ve-handoff-1' for r in lines), 'declared-precedence broken'; print('VE2c_PASS')"`
- **Commit**: None
- **References**: FR-11, FR-12, FR-33, NFR-13, AC-5.1, AC-5.2, AC-5.3, AC-5.4.

### Task 5.5 — VE3: clean shutdown + container teardown + archive audit.jsonl
- **Do**:
  - Kill serve process: `if [ -f .ve-serve-pid.txt ]; then kill "$(cat .ve-serve-pid.txt)" 2>/dev/null; sleep 2; kill -9 "$(cat .ve-serve-pid.txt)" 2>/dev/null || true; fi`
  - Force-remove containers: `for f in .ve-pg-cid.txt .ve-es-cid.txt; do [ -f "$f" ] && docker rm -f "$(cat $f)" 2>/dev/null || true; done`
  - Assert no stuck asyncio tasks: `! pgrep -f "nautilus serve" || (echo "serve process still running" && false)`
  - Archive audit: `mkdir -p .ve-archive && cp /tmp/ve-audit.jsonl /tmp/ve-inferred.jsonl /tmp/ve-attestation.jsonl .ve-archive/ 2>/dev/null || true` (best-effort).
  - Remove ephemeral files: `rm -f .ve-pg-cid.txt .ve-pg-dsn.txt .ve-es-cid.txt .ve-es-url.txt .ve-serve-pid.txt .ve-serve.log .ve-resp-rest.json .ve-forensic.offsets`
- **Files**: none (cleanup).
- **Done when**: No `nautilus serve` process running; no VE containers listed; ephemeral PID/DSN files removed; archive dir populated (best-effort).
- **Verify**: `! pgrep -f "nautilus serve" && ! test -f .ve-serve-pid.txt && ! test -f .ve-pg-cid.txt && echo VE3_PASS`
- **Commit**: `chore(ve): VE3 cleanup — no stuck processes; artifacts archived` (if .gitignore or scripts changed)
- **References**: cleanup protocol.

---

## Summary

- **Total tasks**: 79 (Phase 1: 15 including `[VERIFY]` × 2; Phase 2: 28 including `[VERIFY]` × 6; Phase 3: 19 including `[VERIFY]` × 5; Phase 4: 12 including `[VERIFY]` × 2; Phase 5: 5).
- **Phase breakdown**:
  - Phase 1 POC (tasks 1.1 – 1.15): scaffolds subpackages, extends config + templates + audit + scope_hash, lands PostgresSessionStore + classification rules + escalation + TemporalFilter + AttestationSink, ends at Task 1.15 **POC milestone** — `test_classification_e2e.py` proves the full reasoning surface through one adapter with `scope_hash_v2` emission.
  - Phase 2 completeness (tasks 2.1 – 2.28): follows design §9 build order strictly — `declare_handoff` + rule pack, LLM provider matrix (3 providers + fallback), 4 new adapters (ES → Neo4j → REST → ServiceNow), HTTP attestation sink, FastAPI transport, MCP transport, CLI, Dockerfile, forensic worker with declared-precedence dedup, recorded backwards-compat + LLM fixtures, config-loader extensions.
  - Phase 3 testing (tasks 3.1 – 3.19): dedicated unit module per new component; 5 integration harnesses (latency/fault-injection/determinism/forensic-idempotency/MCP e2e); backwards-compat + session-store e2e; cross-adapter operator drift guard; coverage ≥80%.
  - Phase 4 quality (tasks 4.1 – 4.12): pyproject polish, license scan, docstrings, README, Docker smoke, static grep guards, final local CI sweep, PR + tag.
  - Phase 5 VE (tasks 5.1 – 5.5): full-pipeline verification with real containers — REST flow + MCP flow + declare_handoff + forensic worker over synthesized audit.
- **POC milestone**: **Task 1.15** — `tests/integration/test_classification_e2e.py` proves first successful `POST /v1/request`-shape call through the reasoning-engine pipeline (classification rule + pattern-matcher + temporal filter + pgvector + `scope_hash_v2` + attestation sink dispatch) against Postgres + pgvector testcontainers.
- **Coverage target**: ≥80% branch coverage on `nautilus/` (NFR-2), enforced by Task 3.18 and verified in the final gate (Task 4.10).
- **Quality `[VERIFY]` checkpoints**: 15 total — inserted every 2–3 implementation tasks (1.6, 1.11, 2.5, 2.10, 2.14, 2.19, 2.24, 2.28, 3.4, 3.8, 3.12, 3.16, 3.19, 4.4, 4.7).
- **Tests/impl ratio**: Phase 3 alone adds ~19 test tasks (every new component + 5 integration harnesses + coverage gate + drift + docker); combined with Phase-1 + Phase-2 inline unit coverage, every new public surface has dedicated tests.
- **Backwards-compat gates (NFR-5/NFR-6)**: Task 2.25 records the Phase-1 fixtures; Task 3.14 asserts round-trip; `scope_hash_v1` frozen (Task 1.12); Phase-1 test suite runs in every `[VERIFY]` checkpoint.

---

## Traceability

Each requirement mapped to at least one implementation task (tests land in Phase 3 by design).

| ID | Tasks |
|---|---|
| **US-1** / FR-1, FR-2 | 1.5, 1.10, 3.2 |
| **US-2** / FR-3, FR-4, FR-5 | 1.5, 1.8, 1.14, 3.3, 3.14 |
| **US-3** / FR-6, FR-7 | 1.9, 3.1, 3.2 |
| **US-4** / FR-8, FR-9, FR-10 | 1.4, 2.1, 3.1, 3.5, 5.3 |
| **US-5** / FR-11, FR-12, FR-33 | 2.20, 2.21, 2.22, 2.23, 3.6, 3.17, 5.4 |
| **US-6** / FR-13, FR-14, FR-15 | 2.2, 2.3, 2.4, 2.6, 2.7, 2.26, 3.7, 3.17 |
| **US-7** / FR-17, FR-18, FR-19 | 1.5, 1.7, 1.12, 3.3 |
| **US-8** / FR-20 | 2.8, 3.9, 3.15, 4.8, 4.9 |
| **US-9** / FR-21 | 2.11, 3.9, 3.15, 4.8, 4.9 |
| **US-10** / FR-22 | 2.9, 3.10, 3.15, 4.8, 4.9 |
| **US-11** / FR-23 | 2.12, 3.10, 3.15, 4.8, 4.9 |
| FR-24 | 1.3, 2.27, 3.1 |
| **US-12** / FR-25, FR-26 | 2.15, 3.11, 3.13, 3.17, 5.1, 5.2 |
| **US-13** / FR-27 | 2.16, 3.13, 3.17, 5.3 |
| **US-14** / FR-28, FR-29 | 1.13, 2.13, 3.5, 3.17 |
| FR-16 | 1.7, 1.14, 3.14 |
| **US-15** / FR-30 | 2.17, 3.13 |
| **US-16** / FR-31, FR-32 | 2.18, 4.6 |
| **NFR-1** (air-gap) | 2.17, 3.13 |
| **NFR-2** (coverage) | 3.18, 3.19, 4.10 |
| **NFR-3** (pyright) | every `[VERIFY]` task |
| **NFR-4** (adapter drift) | 3.9, 3.10, 4.9 |
| **NFR-5** (audit parse) | 1.7, 2.25, 3.14 |
| **NFR-6** (attestation verify) | 1.12, 2.25, 3.14 |
| **NFR-7** (session degradation) | 1.8, 3.3 |
| **NFR-8** (p95 latency) | 3.17 |
| **NFR-9** (Fathom p95) | inherited from Phase 1 |
| **NFR-10** (image size) | 2.18, 4.6 |
| **NFR-11** (license) | 1.2, 4.2 |
| **NFR-12** (LLM determinism) | 2.26, 3.17 |
| **NFR-13** (forensic idempotency) | 2.20, 2.23, 3.6, 3.17, 5.4 |
| **NFR-14** (shared broker) | 2.17 |
| **NFR-15** (1:1 audit) | 1.14, 3.13, 3.17, 5.2 |
| **NFR-16** (sink availability) | 1.13, 3.5, 3.17 |
| **NFR-17** (SSRF) | 2.11, 3.9 |
| **NFR-18** (SN sanitizer) | 2.12, 3.10 |
| **D-1 – D-3** (session store) | 1.8, 3.3 |
| **D-4** (cooperative + forensic) | 2.1, 2.23 |
| **D-5, D-6** (LLM Protocol, fallback) | 2.2, 2.7 |
| **D-7** (conditional v2) | 1.12 |
| **D-8** (audit fields) | 1.7, 1.13 |
| **D-9** (/v1/query alias) | 2.15, 3.13 |
| **D-10** (MCP session id) | 2.16, 3.13 |
| **D-11, D-13, D-14** (REST) | 2.15, 3.13 |
| **D-12** (MCP stateless http) | 2.16 |
| **D-15** (argparse CLI) | 2.17 |
| **D-16, D-17** (Docker) | 2.18, 4.6 |
| **D-18** (Attestation Protocol) | 1.13, 2.13 |
| **D-19** (ServiceNow httpx) | 2.12 |
| **D-20** (forensic offline) | 2.23 |

**Coverage assertion**: Every FR (FR-1..FR-33), every NFR (NFR-1..NFR-18), every US (US-1..US-16), and every Decision (D-1..D-20) appears in at least one task. Phase 1 backwards-compat (NFR-5, NFR-6) is verified automatically by running Phase 1's existing `test_mvp_e2e.py` in `[VERIFY]` checkpoints 1.6, 1.11, 2.24, 2.28.

---
