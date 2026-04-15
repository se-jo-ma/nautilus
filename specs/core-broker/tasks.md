---
spec: core-broker
phase: tasks
created: 2026-04-14
granularity: fine
total_tasks: 59
---

# Tasks: core-broker

## Overview

This breakdown translates the 14-step build sequence in design §15 into 59 atomic tasks across four POC-first phases. Phase 1 (17 tasks) drives end-to-end through the MVP e2e gate (AC-9.3, FR-16) against testcontainers PG+pgvector — that is the POC milestone. Phase 2 (10 tasks) refactors the POC shortcuts into Protocols, tightens typing, and promotes inline types to dedicated modules. Phase 3 (20 tasks) adds dedicated unit modules, coverage-gate enforcement, determinism property tests, SQL-injection static grep, and operator-allowlist drift guard. Phase 4 (11 tasks including VE1/VE2/VE3) polishes packaging, docs, final CI green, and the PR handoff. Quality `[VERIFY]` checkpoints run every 2–3 tasks throughout; each one runs `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`, `uv run pytest -m unit`.

---

## Phase 1: POC (proves Broker + Fathom + 2 adapters work e2e)

### Task 1.1 — Scaffold `nautilus/` subpackage skeleton [x]
- **Do**:
  - Create empty `__init__.py` in each of: `nautilus/core/`, `nautilus/config/`, `nautilus/analysis/`, `nautilus/adapters/`, `nautilus/synthesis/`, `nautilus/audit/`, `nautilus/rules/`, `nautilus/rules/templates/`, `nautilus/rules/modules/`, `nautilus/rules/functions/`, `nautilus/rules/rules/`.
  - Add `nautilus/__init__.py` with a placeholder `__all__ = []` (Broker re-export lands in Task 1.16).
- **Files**: `nautilus/__init__.py`, 10× subpackage `__init__.py` per design §11.
- **Done when**: `python -c "import nautilus"` and `python -c "import nautilus.core, nautilus.config, nautilus.analysis, nautilus.adapters, nautilus.synthesis, nautilus.audit, nautilus.rules"` both succeed.
- **Verify**: `uv run python -c "import nautilus, nautilus.core, nautilus.config, nautilus.analysis, nautilus.adapters, nautilus.synthesis, nautilus.audit, nautilus.rules"`
- **Commit**: `chore(scaffold): create nautilus subpackage skeleton`
- **References**: design §11, UQ-1.

### Task 1.2 — Extend `pyproject.toml` with deps + tooling [x]
- **Do**:
  - Add runtime deps `asyncpg>=0.30.0`, `pgvector>=0.3.0` to `[project].dependencies`.
  - Add `[project.optional-dependencies].dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "pytest-cov>=5.0", "testcontainers[postgres]>=4.0", "ruff>=0.5", "pyright>=1.1.370", "pip-licenses>=5.0"]`.
  - Add `[tool.ruff]` (line-length=100, target-version=py314), `[tool.ruff.lint]` (select=[E,F,W,I,B,UP,N,SIM,ASYNC]), `[tool.pyright]` (strict, include=nautilus+tests), `[tool.pytest.ini_options]` (asyncio_mode=auto, markers=unit+integration, addopts=`--strict-markers --cov=nautilus --cov-branch --cov-fail-under=80`).
  - Run `uv sync --extra dev`.
- **Files**: `pyproject.toml`, `uv.lock`.
- **Done when**: `uv sync --extra dev` resolves without error; `uv run ruff --version`, `uv run pyright --version`, `uv run pytest --version` all succeed.
- **Verify**: `uv sync --extra dev && uv run ruff --version && uv run pyright --version && uv run pytest --version`
- **Commit**: `chore(tooling): add asyncpg/pgvector/ruff/pyright/pytest deps`
- **References**: design §11 pyproject block, NFR-6, NFR-10, NFR-11.

### Task 1.3 — Create `tests/` skeleton with markers + shared `conftest.py` [x]
- **Do**:
  - Create `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/fixtures/` directory.
  - Create `tests/conftest.py` exposing session-scoped fixtures: `fake_intent_analyzer` (returns fixed `IntentAnalysis`), `in_memory_audit_sink` (collects entries into a list), `fake_adapter` (callable-configurable return/raise). Stubs may return `None` for now; body fills in later tasks.
  - Ship `tests/fixtures/nautilus.yaml` with a minimal two-source config (one `postgres`, one `pgvector`) using `${TEST_PG_DSN}` and `${TEST_PGV_DSN}` env placeholders matching design §12.
  - Ship `tests/fixtures/seed.sql` creating `vulns(id int pk, severity text, cve text)` with 3 rows and `vuln_embeddings(id int pk, embedding vector(3), metadata jsonb)` with 3 rows (requires `CREATE EXTENSION vector`).
- **Files**: `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/conftest.py`, `tests/fixtures/nautilus.yaml`, `tests/fixtures/seed.sql`.
- **Done when**: `uv run pytest --collect-only -q` shows zero tests but zero collection errors; fixtures importable.
- **Verify**: `uv run pytest --collect-only -q && uv run python -c "import tests.conftest"`
- **Commit**: `test(scaffold): add test skeleton, fixtures, seed SQL`
- **References**: design §11 test tree, §13.3, AC-9.1, AC-9.3.

### [VERIFY] Task 1.4 — Tooling gate after scaffold
- **Do**: Run full toolchain on the empty scaffold.
- **Files**: (none).
- **Done when**: All four commands exit 0.
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit`
- **Commit**: `chore(scaffold): pass quality checkpoint` (only if fixes needed)
- **References**: NFR-6, NFR-7.

### Task 1.5 — Implement `NautilusConfig` + `SourceConfig` Pydantic models [x]
- **Do**:
  - Create `nautilus/config/models.py` with `SourceConfig`, `AttestationConfig`, `RulesConfig`, `AuditConfig`, `AnalysisConfig`, `NautilusConfig` matching design §4.1, §4.10 verbatim.
  - Use `Literal["postgres", "pgvector"]` for `SourceConfig.type`; `Literal["<=>","<->","<#>"]` default `"<=>"` for `distance_operator`.
- **Files**: `nautilus/config/models.py`.
- **Done when**: Importing each model succeeds and `SourceConfig(id="x", type="postgres", description="d", classification="u", data_types=["v"], connection="postgres://x")` constructs without error.
- **Verify**: `uv run python -c "from nautilus.config.models import SourceConfig, NautilusConfig; SourceConfig(id='x', type='postgres', description='d', classification='u', data_types=['v'], connection='postgres://x')"`
- **Commit**: `feat(config): add NautilusConfig and SourceConfig Pydantic models`
- **References**: FR-1, AC-1.1, design §4.1, §4.10.

### Task 1.6 — Implement config loader with env interpolation [x]
- **Do**:
  - Create `nautilus/config/loader.py` with `class ConfigError(Exception)` and `def load_config(path: Path) -> NautilusConfig`.
  - Implement `EnvInterpolator` that replaces `${VAR}` patterns in any string field of the dict loaded from `yaml.safe_load`; missing var → raise `ConfigError(f"Missing env var '{var}' referenced by source id='{source_id}'")`.
  - Detect duplicate `id` before returning; detect unsupported `type` values; raise `ConfigError` in both cases.
  - Export `ConfigError` from `nautilus/config/__init__.py`.
- **Files**: `nautilus/config/loader.py`, `nautilus/config/__init__.py`.
- **Done when**: Given `tests/fixtures/nautilus.yaml` with env vars exported, `load_config()` returns a `NautilusConfig` with 2 sources; with env vars unset, raises `ConfigError` naming both variable and source id.
- **Verify**: `uv run python -c "import os; os.environ['TEST_PG_DSN']='postgres://x'; os.environ['TEST_PGV_DSN']='postgres://y'; from nautilus.config.loader import load_config; c = load_config('tests/fixtures/nautilus.yaml'); assert len(c.sources)==2, c"`
- **Commit**: `feat(config): add YAML loader with env interpolation and ConfigError`
- **References**: FR-1, FR-2, AC-1.1, AC-1.2, AC-1.3, NFR-5.

### Task 1.7 — Implement `SourceRegistry` [x]
- **Do**:
  - Create `nautilus/config/registry.py` with `class SourceRegistry` wrapping `list[SourceConfig]`; methods `get(source_id: str) -> SourceConfig` (raises `KeyError`) and `__iter__()` / `__len__()`.
  - Expose `SourceRegistry` from `nautilus/config/__init__.py`.
- **Files**: `nautilus/config/registry.py`, `nautilus/config/__init__.py`.
- **Done when**: `SourceRegistry` built from 2 configs returns each by id; duplicate-id construction raises `ConfigError`.
- **Verify**: `uv run python -c "from nautilus.config.models import SourceConfig; from nautilus.config.registry import SourceRegistry; s = SourceConfig(id='a', type='postgres', description='', classification='u', data_types=['x'], connection='c'); r = SourceRegistry([s]); assert r.get('a').id=='a' and len(list(r))==1"`
- **Commit**: `feat(config): add SourceRegistry`
- **References**: FR-1, AC-1.3, AC-1.4, design §3.2.

### [VERIFY] Task 1.8 — Quality checkpoint (config layer)
- **Do**: Run toolchain.
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit`
- **Done when**: All four commands exit 0.
- **Commit**: `chore(config): pass quality checkpoint` (if fixes needed)

### Task 1.9 — Implement shared core models [x]
- **Do**: Create `nautilus/core/models.py` containing `IntentAnalysis`, `RoutingDecision`, `ScopeConstraint`, `DenialRecord`, `ErrorRecord`, `AdapterResult`, `BrokerResponse`, `AuditEntry` exactly per design §4.2–§4.9. Use `Literal` for `ScopeConstraint.operator` allowlist per design §6.1.
- **Files**: `nautilus/core/models.py`.
- **Done when**: All 8 models import, and instantiating `ScopeConstraint(source_id='x', field='y', operator='BADOP', value=1)` raises `pydantic.ValidationError` (Literal enforces allowlist — UQ-6).
- **Verify**: `uv run python -c "from nautilus.core.models import IntentAnalysis, ScopeConstraint, BrokerResponse, AuditEntry; from pydantic import ValidationError; import pytest; \nfrom pydantic import ValidationError\ntry:\n    ScopeConstraint(source_id='x', field='y', operator='BADOP', value=1)\n    raise SystemExit('allowlist not enforced')\nexcept ValidationError: pass"`
- **Commit**: `feat(core): add shared Pydantic models (IntentAnalysis, ScopeConstraint, BrokerResponse, AuditEntry)`
- **References**: FR-6, FR-13, AC-7.2, AC-8.3, UQ-5, UQ-6, design §4.

### Task 1.10 — Implement `IntentAnalyzer` Protocol + `PatternMatchingIntentAnalyzer` [x]
- **Do**:
  - `nautilus/analysis/base.py`: `class IntentAnalyzer(Protocol)` with `analyze(intent: str, context: dict) -> IntentAnalysis`.
  - `nautilus/analysis/pattern_matching.py`: `class PatternMatchingIntentAnalyzer` — constructor accepts `keyword_map: dict[str, list[str]]`. `analyze()` scans intent for keyword matches, regex-extracts CVE IDs (`CVE-\d{4}-\d{4,}`), applies deterministic ordering (sort output lists), returns `IntentAnalysis`.
  - Re-export both from `nautilus/analysis/__init__.py`.
- **Files**: `nautilus/analysis/base.py`, `nautilus/analysis/pattern_matching.py`, `nautilus/analysis/__init__.py`.
- **Done when**: For intent `"Find all known vulnerabilities, patches, and affected systems for CVE-2026-1234"` with the default keyword map from design §12, output satisfies AC-2.2: `data_types_needed ⊇ {'vulnerability','patch','asset'}`, `entities == ['CVE-2026-1234']`.
- **Verify**: `uv run python -c "from nautilus.analysis.pattern_matching import PatternMatchingIntentAnalyzer; a = PatternMatchingIntentAnalyzer({'vulnerability':['vulnerability','vuln'],'patch':['patch','fix'],'asset':['asset','system','host']}); r = a.analyze('Find all known vulnerabilities, patches, and affected systems for CVE-2026-1234', {}); assert 'CVE-2026-1234' in r.entities and {'vulnerability','patch','asset'}.issubset(set(r.data_types_needed)), r"`
- **Commit**: `feat(analysis): add PatternMatchingIntentAnalyzer with CVE extraction`
- **References**: FR-3, AC-2.1, AC-2.2, AC-2.3, AC-2.4, AC-2.5, NFR-13, design §3.3.

### [VERIFY] Task 1.11 — Quality checkpoint (analysis layer)
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit`
- **Done when**: All four commands exit 0.
- **Commit**: `chore(analysis): pass quality checkpoint` (if fixes needed)

### Task 1.12 — Author Nautilus Fathom templates + module + default rules (SPIKE) [x]
- **Do**:
  - Create `nautilus/rules/templates/nautilus.yaml` with the 7 templates from design §5.1 (agent, intent, source, session, routing_decision, scope_constraint, denial_record).
  - Create `nautilus/rules/modules/nautilus-routing.yaml` with the module declaration from design §5.1b.
  - Create `nautilus/rules/rules/routing.yaml` (match-sources-by-data-type, salience 100, uses `overlaps` external) per design §5.3.
  - Create `nautilus/rules/rules/denial.yaml` (deny-purpose-mismatch, salience 200) per design §5.3.
  - Create `nautilus/rules/functions/overlaps.py` defining `register_overlaps(engine)` and `register_not_in_list(engine)` (not-in-list returns `True` if purpose not in explode$(allowed_purposes)).
  - Create `nautilus/rules/__init__.py` that exports `BUILT_IN_RULES_DIR = Path(__file__).parent`.
  - SPIKE smoke test: write a throwaway `scripts/smoke_fathom.py` (gitignored via `.gitignore` if needed) that calls `fathom.Engine.from_rules(BUILT_IN_RULES_DIR)` with templates/module/rules registered and asserts construction succeeds. Keep the smoke script in-repo under `tests/integration/test_fathom_smoke.py` instead, marked `@pytest.mark.integration`, that validates the engine loads the rule tree without raising.
- **Files**: `nautilus/rules/templates/nautilus.yaml`, `nautilus/rules/modules/nautilus-routing.yaml`, `nautilus/rules/rules/routing.yaml`, `nautilus/rules/rules/denial.yaml`, `nautilus/rules/functions/overlaps.py`, `nautilus/rules/functions/__init__.py`, `nautilus/rules/__init__.py`, `tests/integration/test_fathom_smoke.py`.
- **Done when**: `uv run pytest tests/integration/test_fathom_smoke.py -m integration -q` passes (engine constructs from the YAML tree with `overlaps`/`not-in-list` registered). If the Fathom compiler rejects `then.assert`, THIS STEP IS THE SPIKE and must be resolved before proceeding per design §17 risk row.
- **Verify**: `uv run pytest tests/integration/test_fathom_smoke.py -m integration -q`
- **Commit**: `feat(rules): add Nautilus templates, module, default rules, overlaps external`
- **References**: FR-4, FR-5, AC-3.1, AC-3.6, AC-3.7, design §5, §17.

### Task 1.13 — Implement `FathomRouter` [x]
- **Do**:
  - Create `nautilus/core/fathom_router.py` with `FathomRouter(built_in_rules_dir, user_rules_dirs, attestation=None)`; constructor builds `fathom.Engine`, loads built-in templates+module+rules, registers `overlaps` and `not-in-list` externals, then loads user rules.
  - Implement `route()` per design §3.4 + §5.4: clear facts, encode multislot list fields to space-separated strings (quote values with whitespace), assert `agent`, `intent`, each `source`, `session`; `engine.evaluate()`; query `routing_decision`, `scope_constraint`, `denial_record`; capture `rule_trace`; return `RouteResult` dataclass.
  - Remove sources in `denial_records` from routing set.
  - Add `PolicyEngineError(Exception)` in `nautilus/core/__init__.py`.
  - Create `tests/unit/test_fathom_router_basic.py` exercising the basic routing flow with in-memory fakes (see Done-when).
- **Files**: `nautilus/core/fathom_router.py`, `nautilus/core/__init__.py`, `tests/unit/test_fathom_router_basic.py`.
- **Done when**: `tests/unit/test_fathom_router_basic.py` asserts: (a) a `SourceRegistry` is built with exactly 2 `SourceConfig` entries whose `data_types` overlap the fake `IntentAnalysis.data_types_needed`; (b) `FathomRouter.route(agent, intent_analysis, sources, session)` returns a `RouteResult` whose `routing_decisions` has exactly 2 entries and whose `source_id` values equal the 2 registered source ids (set-equal); (c) `rule_trace` is a non-empty list. Deep router-internals (trace determinism, denial paths) are covered later in Task 3.5.
- **Verify**: `uv run pytest tests/unit/test_fathom_router_basic.py -q`
- **Commit**: `feat(core): add FathomRouter with multislot encoding and template readback`
- **References**: FR-4, FR-6, FR-7, AC-3.2, AC-3.3, AC-3.4, AC-3.5, design §3.4, §5.4.

### Task 1.14 — Implement `Adapter` base + `PostgresAdapter` [x]
- **Do**:
  - `nautilus/adapters/base.py`: `class Adapter(Protocol)`, `class ScopeEnforcementError(Exception)`, `class AdapterError(Exception)`. Add operator allowlist validator `validate_operator(op: str) -> None` using design §6.1 set; regex field validator `validate_field(f: str) -> None` using `r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$"` from §6.2.
  - `nautilus/adapters/postgres.py`: `class PostgresAdapter` with `connect()` (creates `asyncpg.Pool`), `execute()` (builds `SELECT * FROM <table> WHERE <scope predicates> LIMIT $N` using positional placeholders only; operator template table from §6.1), `close()` (releases pool, idempotent).
  - No f-string interpolation of values anywhere. Accept `table` via `SourceConfig.table` — **shortcut: require `table` on both postgres and pgvector sources in Phase 1** (fix in Phase 2 refactor).
- **Files**: `nautilus/adapters/base.py`, `nautilus/adapters/postgres.py`, `nautilus/adapters/__init__.py`.
- **Done when**: `PostgresAdapter` instantiates against a mocked `asyncpg.Pool` without error; `_build_sql()` returns a `str` that contains at least one `$1` positional parameter placeholder and whose IN-operator branch matches the operator template from design §6.1 (i.e. renders via `ANY(...)` or equivalent parameterized form, not string-interpolated). Exact SQL-string equality is deferred to Task 3.6.
- **Verify**: `uv run pytest tests/unit/ -k "postgres_adapter or base_adapter" -q` (the dedicated test file lands in Task 3.6; this verify runs whatever already exists).
- **Commit**: `feat(adapters): add Adapter protocol, operator allowlist, PostgresAdapter with asyncpg`
- **References**: FR-8, FR-17, FR-18, AC-4.1, AC-4.2, AC-4.3, AC-4.5, NFR-4, design §3.5, §6.

### Task 1.15 — Implement `PgVectorAdapter` + `Embedder` Protocol + `NoopEmbedder` [x]
- **Do**:
  - `nautilus/adapters/embedder.py`: `class Embedder(Protocol)` + `class NoopEmbedder(strict: bool = True)`; `embed()` raises `EmbeddingUnavailableError` when strict, else returns zero vector.
  - `nautilus/adapters/pgvector.py`: `class PgVectorAdapter` extending `PostgresAdapter` mechanics. Resolve embedding via `context["embedding"]` → per-source embedder → broker-default embedder (design §7.2). Build query `SELECT id, metadata, embedding FROM <table> WHERE <scope> ORDER BY <embedding_column> <op> $E LIMIT $L` per design §7.3. Dotted field `metadata.foo` → `metadata->>'foo'`.
  - `EmbeddingUnavailableError` exported from `nautilus/adapters/__init__.py`.
- **Files**: `nautilus/adapters/embedder.py`, `nautilus/adapters/pgvector.py`, `nautilus/adapters/__init__.py`.
- **Done when**: Unit test asserts generated SQL for pgvector source with 1 scope + `context["embedding"] = [0.1,0.2,0.3]` contains `ORDER BY embedding <=> $`, applies scope `WHERE` before `ORDER BY`, and `NoopEmbedder(strict=True).embed("x")` raises `EmbeddingUnavailableError`.
- **Verify**: `uv run pytest tests/unit/ -k "pgvector or embedder" -q`
- **Commit**: `feat(adapters): add PgVectorAdapter and Embedder protocol with NoopEmbedder`
- **References**: FR-9, AC-5.1, AC-5.2, AC-5.3, AC-5.4, UQ-3, design §3.10, §7.

### Task 1.16 — Implement `BasicSynthesizer`, `AuditLogger`, `SessionStore`, `Broker` facade [x]
- **Do**:
  - `nautilus/synthesis/base.py`: `Synthesizer` Protocol. `nautilus/synthesis/basic.py`: `BasicSynthesizer.merge(results)` returns `{source_id: rows}`; never raises on partial failure (failed adapters are pre-filtered to `sources_errored`).
  - `nautilus/audit/logger.py`: `AuditLogger(sink)` with `emit(entry: AuditEntry) -> None`; default sink is `fathom.audit.FileSink(path)`.
  - `nautilus/core/session.py`: `SessionStore` Protocol + `InMemorySessionStore`.
  - `nautilus/core/broker.py`: `Broker.from_config()` classmethod; constructor wires `SourceRegistry`, `PatternMatchingIntentAnalyzer`, `FathomRouter`, adapters-per-source (`PostgresAdapter`/`PgVectorAdapter`), `BasicSynthesizer`, `AuditLogger`, `AttestationService` (auto-generate Ed25519 unless `private_key_path`), `InMemorySessionStore`. `request()` event-loop guard per design §8 then `asyncio.run(self.arequest(...))`. `arequest()` runs the full pipeline: IntentAnalyzer → SessionStore.get → FathomRouter.route → `asyncio.gather(adapter.execute...)` → Synthesizer → AttestationService.sign → AuditLogger.emit → return `BrokerResponse`. On exception, still emit one audit entry.
  - `close()` idempotent: call each `adapter.close()`, `router.close()`; set flag so second call is no-op.
  - Re-export `Broker`, `BrokerResponse` from `nautilus/__init__.py`.
- **Files**: `nautilus/synthesis/base.py`, `nautilus/synthesis/basic.py`, `nautilus/synthesis/__init__.py`, `nautilus/audit/logger.py`, `nautilus/audit/__init__.py`, `nautilus/core/session.py`, `nautilus/core/broker.py`, `nautilus/core/__init__.py`, `nautilus/__init__.py`.
- **Done when**: `from nautilus import Broker; Broker.from_config("tests/fixtures/nautilus.yaml")` returns a `Broker` (with env vars exported). Calling `broker.request()` inside a running loop raises `RuntimeError` mentioning `arequest`.
- **Verify**: `uv run python -c "from nautilus import Broker; print('Broker imported')" && uv run pytest tests/unit/ -k "broker" -q`
- **Commit**: `feat(core): add Broker facade with event-loop guard, attestation, audit wiring`
- **References**: FR-10, FR-11, FR-12, FR-13, FR-14, FR-17, FR-18, AC-6.1, AC-6.2, AC-6.3, AC-7.1, AC-7.2, AC-8.1, AC-8.2, AC-8.3, AC-8.4, AC-8.5, AC-8.6, UQ-2, UQ-4, UQ-5, design §3.1, §3.6, §3.7, §3.8, §3.9, §8.

### Task 1.17 — **POC MILESTONE**: MVP e2e integration test (AC-9.3) [x]
- **Do**:
  - Create `tests/integration/test_mvp_e2e.py` marked `@pytest.mark.integration`.
  - Use `testcontainers.postgres.PostgresContainer("pgvector/pgvector:pg17")` session-scoped fixture (in `tests/conftest.py`); on startup execute `tests/fixtures/seed.sql` inside container after `CREATE EXTENSION vector`.
  - Export `TEST_PG_DSN` / `TEST_PGV_DSN` from the container URL into `os.environ` before `Broker.from_config`.
  - Test body: `broker = Broker.from_config("tests/fixtures/nautilus.yaml")`; `resp = broker.request("agent-alpha", "Find vulnerabilities for CVE-2026-1234", {"clearance": "unclassified", "purpose": "threat-analysis", "session_id": "s1", "embedding": [0.1,0.2,0.3]})`.
  - Assert: `set(resp.sources_queried) == {"nvd_db", "internal_vulns"}`; `resp.data["nvd_db"]` non-empty; `resp.data["internal_vulns"]` non-empty; `resp.attestation_token is not None` (UQ-2); `resp.request_id` matches UUID regex; `resp.duration_ms > 0`.
  - Read the JSONL audit file, assert exactly 1 line, round-trip via `AuditEntry.model_validate_json`, assert `entry.rule_trace` is non-empty list, `entry.facts_asserted_summary["source"] == 2`.
  - Call `broker.close()` twice; second call is no-op.
- **Files**: `tests/integration/test_mvp_e2e.py`, extended `tests/conftest.py` (pg_container fixture).
- **Done when**: `uv run pytest tests/integration/test_mvp_e2e.py -m integration -q` exits 0.
- **Verify**: `uv run pytest tests/integration/test_mvp_e2e.py -m integration -q`
- **Commit**: `test(integration): MVP e2e — broker + PG + pgvector + audit + attestation`
- **References**: FR-16, AC-9.2, AC-9.3, AC-8.6, NFR-8, NFR-9, UQ-2, design §15 step 13.

> **POC MILESTONE ACHIEVED** — broker.request() succeeds end-to-end against real PostgreSQL + pgvector, emits exactly one complete audit entry, produces a non-empty rule trace, and returns a signed attestation token. FR-16 / AC-9.3 satisfied.

### [VERIFY] Task 1.18 — Full gate after POC (unit + integration) [x]
- **Do**: Run full quality gate (integration tier included since testcontainers are now wired).
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit && uv run pytest -m integration`
- **Done when**: All five commands exit 0.
- **Commit**: `chore(poc): pass post-POC full gate` (if fixes needed)

---

## Phase 2: Refactor

### Task 2.1 — Promote inline RouteResult to `nautilus/core/models.py`
- **Do**: Move `RouteResult` dataclass from `fathom_router.py` into `nautilus/core/models.py` as a Pydantic model (timestamps/duration as `int` microseconds). Update imports.
- **Files**: `nautilus/core/models.py`, `nautilus/core/fathom_router.py`.
- **Done when**: Import graph unchanged externally; `RouteResult` available from both locations via re-export.
- **Verify**: `uv run pyright && uv run pytest -m unit`
- **Commit**: `refactor(core): promote RouteResult to models module`
- **References**: design §3.4, §4.

### Task 2.2 — Introduce explicit `EmbeddingUnavailableError` hierarchy [x]
- **Do**: Move `EmbeddingUnavailableError` from `embedder.py` to `nautilus/adapters/base.py` as subclass of `AdapterError`; keep re-export for back-compat.
- **Files**: `nautilus/adapters/base.py`, `nautilus/adapters/embedder.py`, `nautilus/adapters/__init__.py`.
- **Done when**: `issubclass(EmbeddingUnavailableError, AdapterError)` is True.
- **Verify**: `uv run python -c "from nautilus.adapters import EmbeddingUnavailableError, AdapterError; assert issubclass(EmbeddingUnavailableError, AdapterError)"`
- **Commit**: `refactor(adapters): unify error hierarchy under AdapterError`
- **References**: design §10.1.

### Task 2.3 — Extract CLIPS multislot encoder to dedicated helper [x]
- **Do**: Pull `encode_multislot(value: list[str]) -> str` out of `FathomRouter` into `nautilus/core/clips_encoding.py`. Add docstring with quoting rules (values containing whitespace get quoted).
- **Files**: `nautilus/core/clips_encoding.py`, `nautilus/core/fathom_router.py`.
- **Done when**: `encode_multislot(["a b", "c"])` returns `'"a b" c'`; all router call sites use helper.
- **Verify**: `uv run python -c "from nautilus.core.clips_encoding import encode_multislot; assert encode_multislot(['a b','c']) == '\"a b\" c'"`
- **Commit**: `refactor(core): extract CLIPS multislot encoder helper`
- **References**: design §3.4, §5.1.

### [VERIFY] Task 2.4 — Quality checkpoint (refactor batch 1) [x]
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit`
- **Done when**: All four exit 0.
- **Commit**: `chore(refactor): pass quality checkpoint` (if fixes needed)

### Task 2.5 — Split `broker.py` request pipeline into private helpers [x]
- **Do**: Within `Broker`, extract `_build_adapter_jobs`, `_gather_adapter_results`, `_build_response`, `_emit_audit` as async private methods; `arequest` becomes a linear sequence of awaits.
- **Files**: `nautilus/core/broker.py`.
- **Done when**: Each helper is ≤ 30 LOC; `arequest` body ≤ 40 LOC; public surface unchanged.
- **Verify**: `uv run pytest tests/unit/ tests/integration/test_mvp_e2e.py -m "unit or integration" -q`
- **Commit**: `refactor(core): decompose Broker.arequest into private helpers`
- **References**: design §3.1.

### Task 2.6 — Isolate attestation payload construction [x]
- **Do**: Extract `_build_attestation_payload(response, rule_trace) -> dict` per design §9.3 into `nautilus/core/attestation_payload.py`; add `scope_hash` + `rule_trace_hash` SHA-256 derivation (stable JSON canonicalization).
- **Files**: `nautilus/core/attestation_payload.py`, `nautilus/core/broker.py`.
- **Done when**: Two identical requests produce identical `scope_hash`/`rule_trace_hash` (determinism per NFR-14).
- **Verify**: `uv run python -c "from nautilus.core.attestation_payload import build_payload; import json; a=build_payload('r','a',['s'],[], {}); b=build_payload('r','a',['s'],[], {}); assert a['scope_hash']==b['scope_hash']"`
- **Commit**: `refactor(core): isolate attestation payload builder with stable hashing`
- **References**: design §9.3, NFR-14.

### Task 2.7 — Convert `Adapter`, `Synthesizer`, `Embedder`, `IntentAnalyzer`, `SessionStore` to runtime-checkable Protocols [x]
- **Do**: Add `@runtime_checkable` to all 5 Protocols. Verify `isinstance(PostgresAdapter(), Adapter)` works for duck typing in tests.
- **Files**: `nautilus/adapters/base.py`, `nautilus/adapters/embedder.py`, `nautilus/synthesis/base.py`, `nautilus/analysis/base.py`, `nautilus/core/session.py`.
- **Done when**: `pyright --strict` still clean; runtime isinstance check works.
- **Verify**: `uv run pyright && uv run python -c "from nautilus.synthesis.base import Synthesizer; from nautilus.synthesis.basic import BasicSynthesizer; assert isinstance(BasicSynthesizer(), Synthesizer)"`
- **Commit**: `refactor: mark all plug-in Protocols as runtime_checkable`
- **References**: design §3 (Protocol-first).

### Task 2.8 — Harden field-identifier quoting in Postgres adapter [x]
- **Do**: Replace manual quoting with `asyncpg`'s identifier-quoting helper (or a vetted one-liner); add explicit test cases for dotted JSONB field `metadata.classification`.
- **Files**: `nautilus/adapters/postgres.py`, `nautilus/adapters/pgvector.py`.
- **Done when**: Field `metadata.classification` emits `metadata->>'classification'`; field `valid_name` emits `"valid_name"`; field `1bad` raises `ScopeEnforcementError`.
- **Verify**: `uv run pytest tests/unit/ -k "field_identifier or sql_injection" -q`
- **Commit**: `refactor(adapters): tighten field identifier quoting`
- **References**: NFR-4, design §6.2, §7.3.

### [VERIFY] Task 2.9 — Quality checkpoint (refactor batch 2) [x]
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit`
- **Done when**: All four exit 0.
- **Commit**: `chore(refactor): pass quality checkpoint` (if fixes needed)

### Task 2.10 — Audit JSON serialization hardening [x]
- **Do**: Make `AuditLogger.emit` call `entry.model_dump_json(by_alias=False)`; assert newline appended; add `flush()` after every write. Ensure `timestamp` serializes as ISO8601 UTC with `Z` suffix.
- **Files**: `nautilus/audit/logger.py`.
- **Done when**: Written JSONL line re-parses via `AuditEntry.model_validate_json`; timestamp field ends with `Z`.
- **Verify**: `uv run pytest tests/unit/ -k "audit_logger" -q`
- **Commit**: `refactor(audit): stabilize JSONL serialization with flush and UTC timestamps`
- **References**: AC-7.3, AC-7.5, NFR-8.

---

## Phase 3: Testing

### Task 3.1 — `tests/unit/test_config_loader.py` [x]
- **Do**: Test cases: (a) valid YAML produces `NautilusConfig`, (b) missing env var → `ConfigError` naming var + source id, (c) unknown `type` → `ConfigError`, (d) duplicate id → `ConfigError`, (e) env interpolation in `connection` works, (f) optional `allowed_purposes` omitted → None.
- **Files**: `tests/unit/test_config_loader.py`.
- **Done when**: 6 test cases pass.
- **Verify**: `uv run pytest tests/unit/test_config_loader.py -q`
- **Commit**: `test(config): add config loader unit tests`
- **References**: AC-1.1, AC-1.2, AC-1.3, NFR-5, FR-1, FR-2.

### Task 3.2 — `tests/unit/test_source_registry.py` [x]
- **Do**: Snapshot test for AC-1.4 — registry exposes all fields identical to YAML dict; `.get("unknown")` raises `KeyError`; `len(registry) == N`.
- **Files**: `tests/unit/test_source_registry.py`.
- **Done when**: 3 test cases pass.
- **Verify**: `uv run pytest tests/unit/test_source_registry.py -q`
- **Commit**: `test(config): add source registry unit tests`
- **References**: AC-1.4.

### Task 3.3 — `tests/unit/test_pattern_analyzer.py` (incl. determinism property) [x]
- **Do**: Test cases: AC-2.2 CVE extraction, AC-2.3 zero match → empty list, keyword-map from config, NFR-13 determinism — 100 random intents × 5 repeats yield identical output per input (property test using `hypothesis` if available, else stdlib `random.seed`).
- **Files**: `tests/unit/test_pattern_analyzer.py`.
- **Done when**: All cases pass including determinism property (100×5).
- **Verify**: `uv run pytest tests/unit/test_pattern_analyzer.py -q`
- **Commit**: `test(analysis): add pattern analyzer unit tests with determinism property`
- **References**: AC-2.2, AC-2.3, AC-2.5, NFR-13.

### [VERIFY] Task 3.4 — Quality checkpoint (test batch 1) [x]
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit`
- **Done when**: All four exit 0.

### Task 3.5 — `tests/unit/test_fathom_router.py` [x]
- **Do**: Test cases: (a) templates registered on engine construction, (b) facts asserted in correct order (patch `engine.assert_facts` to record calls), (c) 3-source scenario: 3 `routing_decision` facts round-trip (FR-6), (d) `rule_trace` non-empty passthrough (FR-7), (e) denial removes source from route set, (f) determinism — same input produces identical `rule_trace` (NFR-14).
- **Files**: `tests/unit/test_fathom_router.py`.
- **Done when**: 6 cases pass.
- **Verify**: `uv run pytest tests/unit/test_fathom_router.py -q`
- **Commit**: `test(core): add FathomRouter unit tests incl. rule_trace determinism`
- **References**: AC-3.1, AC-3.2, AC-3.3, AC-3.4, AC-3.5, FR-6, FR-7, NFR-14.

### Task 3.6 — `tests/unit/test_postgres_adapter.py` [x]
- **Do**: Test cases (using `unittest.mock.AsyncMock` for pool): (a) each operator in allowlist emits correct SQL template, (b) unknown operator → `ScopeEnforcementError`, (c) bad field name → `ScopeEnforcementError`, (d) multiple scopes combine with `AND`, (e) `close()` idempotency, (f) connection failure → `AdapterError`.
- **Files**: `tests/unit/test_postgres_adapter.py`.
- **Done when**: 6 cases pass.
- **Verify**: `uv run pytest tests/unit/test_postgres_adapter.py -q`
- **Commit**: `test(adapters): add PostgresAdapter SQL construction + error unit tests`
- **References**: AC-4.1, AC-4.2, AC-4.3, AC-4.5, FR-8, FR-17, FR-18.

### Task 3.7 — `tests/unit/test_pgvector_adapter.py` [x]
- **Do**: Test cases: (a) embedder precedence — context wins over per-source wins over default, (b) similarity query shape: metadata WHERE applied BEFORE ORDER BY, (c) three distance operators `<=>`, `<->`, `<#>` all emit correct SQL, (d) `NoopEmbedder(strict=True)` triggers `EmbeddingUnavailableError`, (e) dotted field `metadata.foo` → `metadata->>'foo'`.
- **Files**: `tests/unit/test_pgvector_adapter.py`.
- **Done when**: 5 cases pass.
- **Verify**: `uv run pytest tests/unit/test_pgvector_adapter.py -q`
- **Commit**: `test(adapters): add PgVectorAdapter embedder precedence + query shape tests`
- **References**: AC-5.1, AC-5.2, AC-5.3, FR-9, UQ-3.

### [VERIFY] Task 3.8 — Quality checkpoint (test batch 2) [x]
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit`
- **Done when**: All four exit 0.

### Task 3.9 — `tests/unit/test_synthesizer.py` [x]
- **Do**: Test cases: (a) AC-6.1 `{source_id: rows}` shape for N inputs, (b) AC-6.2 one adapter error → synthesis returns OTHER sources, never raises, (c) AC-6.4 `sources_queried` order derived from routing decisions (stable, not completion-based).
- **Files**: `tests/unit/test_synthesizer.py`.
- **Done when**: 3 cases pass.
- **Verify**: `uv run pytest tests/unit/test_synthesizer.py -q`
- **Commit**: `test(synthesis): add BasicSynthesizer partial-failure tests`
- **References**: AC-6.1, AC-6.2, AC-6.4, FR-10, FR-18.

### Task 3.10 — `tests/unit/test_audit_logger.py` [x]
- **Do**: Test cases: (a) `AuditEntry` shape matches AC-7.2 schema, (b) append-only — 2 requests produce 2 lines, first line byte-identical after second write (AC-7.3), (c) round-trip `AuditEntry.model_validate_json` on every line (AC-7.5), (d) audit written even on full denial (AC-7.4), (e) audit written on adapter exception (AC-7.4).
- **Files**: `tests/unit/test_audit_logger.py`.
- **Done when**: 5 cases pass.
- **Verify**: `uv run pytest tests/unit/test_audit_logger.py -q`
- **Commit**: `test(audit): add audit logger round-trip + append-only tests`
- **References**: AC-7.1, AC-7.2, AC-7.3, AC-7.4, AC-7.5, FR-11, NFR-8.

### Task 3.11 — `tests/unit/test_broker.py` [x]
- **Do**: Test cases: (a) AC-8.5 nested-loop detection — call inside running loop raises `RuntimeError` mentioning `arequest`, (b) AC-8.6 `close()` idempotency — call twice, second is no-op, (c) attestation token present on successful response (UQ-2), (d) `attestation.enabled=false` → token is `None`, (e) FR-18 one adapter raising does not break the others (use `fake_adapter` from conftest), (f) NFR-3 concurrent execution — two sleep-instrumented adapters overlap ≥50% of their durations (patch adapters with `asyncio.sleep(0.1)` and measure wall time).
- **Files**: `tests/unit/test_broker.py`.
- **Done when**:
  - 6 test cases above pass.
  - Assert `Broker.request()` raises `RuntimeError` whose message mentions `arequest()` when called inside a running event loop (UQ-4) — moved from Task 1.16 `Verify`.
  - Assert `not hasattr(broker, 'reload')` (AC-1.5: no public reload API in Phase 1).
  - Assert `not hasattr(broker, 'query')` (AC-8.7: `broker.query()` deferred to Phase 2).
- **Verify**: `uv run pytest tests/unit/test_broker.py -q`
- **Commit**: `test(core): add Broker unit tests (loop guard, close, attestation, concurrency, absence guards)`
- **References**: AC-1.5, AC-8.5, AC-8.6, AC-8.7, FR-17, FR-18, NFR-3, UQ-2, UQ-4.

### [VERIFY] Task 3.12 — Quality checkpoint (test batch 3) [x]
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit`
- **Done when**: All four exit 0.

### Task 3.13 — `tests/unit/test_sql_injection_static.py` (grep test) [x]
- **Do**: Write a unit test that walks every `.py` file under `nautilus/adapters/` and scans each file with a **5-line sliding window** for a co-occurring f-string + DB-call pair. Use these canonical patterns (pinned here, copy verbatim into the test):
  - f-string pattern: `FSTRING = re.compile(r"f['\"][^'\"]*\{[^}]+\}")`
  - db-call pattern: `DBCALL = re.compile(r"\b(execute|executemany|fetch|fetchrow|fetchval)\s*\(")`
  - For each file, read lines, slide a 5-line window; if `FSTRING.search(window_text)` AND `DBCALL.search(window_text)` both hit, fail with a message pointing to file + starting line number.
  - Additionally scan for `%s`-style formatting (`% (`-style or `"%s" %`) on the same 5-line window adjacent to `DBCALL`. Fail on any hit.
  - Allowlist exemption: lines tagged with trailing comment `# noqa: SQLGREP` are excluded (reserved for the rare legitimate f-string near a DB call, e.g. a quoted identifier already hardened via Task 2.8).
- **Files**: `tests/unit/test_sql_injection_static.py`.
- **Done when**: Test runs and asserts 0 matches across `nautilus/adapters/*.py` (excluding `# noqa: SQLGREP`-tagged lines).
- **Verify**: `uv run pytest tests/unit/test_sql_injection_static.py -q`
- **Commit**: `test(adapters): add SQL injection static grep guard`
- **References**: NFR-4, design §13.1, §17 (SQL-injection risk row).

### Task 3.14 — `tests/unit/test_operator_allowlist_drift.py` [x]
- **Do**: Parametric test that imports the `Literal` type on `ScopeConstraint.operator` AND the runtime allowlist constant in `nautilus/adapters/base.py`; asserts the two sets are equal. Breaks if one drifts without the other (design §17 risk row).
- **Files**: `tests/unit/test_operator_allowlist_drift.py`.
- **Done when**: Test passes with current allowlist; removing one operator from either side fails the test.
- **Verify**: `uv run pytest tests/unit/test_operator_allowlist_drift.py -q`
- **Commit**: `test(adapters): guard against operator allowlist drift`
- **References**: UQ-6, design §6.1, §17.

### [VERIFY] Task 3.15 — Quality checkpoint (test batch 4)
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit`
- **Done when**: All four exit 0.

### Task 3.16 — Integration test: `tests/integration/test_postgres_scope.py`
- **Do**: Seed `vulns` table with 5 rows varying `severity`. Issue request with scope `severity IN ('high','critical')`; assert only matching rows returned. Issue a second request with `severity = 'low'`; assert non-matching rows excluded. Uses `pg_container` fixture.
- **Files**: `tests/integration/test_postgres_scope.py`.
- **Done when**: 2 assertions pass against real PG.
- **Verify**: `uv run pytest tests/integration/test_postgres_scope.py -m integration -q`
- **Commit**: `test(integration): postgres scope enforcement against testcontainers`
- **References**: AC-4.6, FR-8.

### Task 3.17 — Integration test: `tests/integration/test_pgvector_similarity.py`
- **Do**: Seed `vuln_embeddings` with 5 rows; 3 with `metadata.classification='cui'`, 2 with `'unclassified'`. Issue similarity query scoped to `metadata.classification = 'cui'`; assert (a) only `cui` rows returned, (b) row ordering matches similarity to supplied query embedding (decreasing).
- **Files**: `tests/integration/test_pgvector_similarity.py`.
- **Done when**: Both assertions pass.
- **Verify**: `uv run pytest tests/integration/test_pgvector_similarity.py -m integration -q`
- **Commit**: `test(integration): pgvector similarity + metadata filter order test`
- **References**: AC-5.5, FR-9.

### Task 3.18 — Coverage gate enforcement
- **Do**: Run `uv run pytest -m "unit or integration" --cov=nautilus --cov-branch --cov-report=term-missing --cov-fail-under=80`. If any module is under 80%, add targeted tests or `# pragma: no cover` for genuinely unreachable branches (document each pragma with a comment).
- **Pragma budget**: ≤ 3 `# pragma: no cover` additions total across the entire task. Each one must carry an inline comment that justifies why the branch is unreachable (e.g. `# pragma: no cover  # Python 3.14 typing.Protocol import guard`). More than 3 additions indicates missing tests, not unreachable branches — split out a new unit test instead.
- **Files**: any `tests/unit/test_*.py` that need gap-filling.
- **Done when**: Command exits 0 with branch coverage ≥80% AND `grep -rn "pragma: no cover" nautilus/ | wc -l` shows a net addition of ≤ 3 over the pre-task count (each addition paired with a justifying comment).
- **Verify**: `uv run pytest -m "unit or integration" --cov=nautilus --cov-branch --cov-fail-under=80 -q`
- **Commit**: `test(coverage): raise branch coverage to 80%`
- **References**: NFR-6, AC-9.4.

### Task 3.19 — Dedicated unit module existence check (AC-9.5)
- **Do**: Add a meta-test `tests/unit/test_module_presence.py` that asserts each of `test_config_loader.py`, `test_source_registry.py`, `test_pattern_analyzer.py`, `test_fathom_router.py`, `test_postgres_adapter.py`, `test_pgvector_adapter.py`, `test_synthesizer.py`, `test_audit_logger.py`, `test_broker.py` exists in `tests/unit/`.
- **Files**: `tests/unit/test_module_presence.py`.
- **Done when**: Meta-test passes (all 9 files exist).
- **Verify**: `uv run pytest tests/unit/test_module_presence.py -q`
- **Commit**: `test(meta): enforce dedicated unit-test module per component`
- **References**: AC-9.5.

### [VERIFY] Task 3.20 — Full test gate (unit + integration + coverage)
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit && uv run pytest -m integration && uv run pytest -m "unit or integration" --cov=nautilus --cov-branch --cov-fail-under=80 -q`
- **Done when**: All commands exit 0.
- **Commit**: `chore(tests): pass full quality + coverage gate` (if fixes needed)

---

## Phase 4: Quality

### Task 4.1 — Polish `pyproject.toml` metadata
- **Do**: Fill in `description = "Nautilus data broker: intent-aware scoped query execution via Fathom rules"`, `authors`, `license = "MIT"`, `readme = "README.md"`, `[project.urls]` block, `classifiers` (Python 3.14, OSI MIT, Topic :: Security). Verify `uv build` succeeds.
- **Files**: `pyproject.toml`.
- **Done when**: `uv build` emits `dist/nautilus-0.1.0-*.whl` without warnings.
- **Verify**: `uv build`
- **Commit**: `chore(packaging): fill pyproject metadata`
- **References**: NFR-10, NFR-12.

### Task 4.2 — README quickstart
- **Do**: Rewrite `README.md` to include: install (`uv add nautilus`), 10-line quickstart (load YAML, call `broker.request`, print response), links to `design.md` and `requirements.md`.
- **Files**: `README.md`.
- **Done when**: README is ≤120 lines and the quickstart block is runnable verbatim against `tests/fixtures/nautilus.yaml`.
- **Verify**: `uv run python -c "import re, pathlib; txt = pathlib.Path('README.md').read_text(encoding='utf-8'); assert 'Broker.from_config' in txt and 'uv add' in txt"`
- **Commit**: `docs: rewrite README with quickstart`
- **References**: AC-8.1, NFR-10.

### Task 4.3 — Public-surface docstring sweep
- **Do**: Add Google-style docstrings to every public class and method on `Broker`, `BrokerResponse`, `IntentAnalysis`, `ScopeConstraint`, `RoutingDecision`, `DenialRecord`, `Adapter` Protocol, `Synthesizer` Protocol, `IntentAnalyzer` Protocol, `Embedder` Protocol, `SessionStore` Protocol, `AuditLogger`, `FathomRouter`. Include `Args:`, `Returns:`, `Raises:`.
- **Files**: `nautilus/core/broker.py`, `nautilus/core/models.py`, `nautilus/adapters/base.py`, `nautilus/synthesis/base.py`, `nautilus/analysis/base.py`, `nautilus/adapters/embedder.py`, `nautilus/core/session.py`, `nautilus/audit/logger.py`, `nautilus/core/fathom_router.py`.
- **Done when**: Every public symbol has a non-empty docstring; a grep for class/def followed immediately by another code line (no docstring) returns zero hits.
- **Verify**: `uv run python scripts/check_docstrings.py || uv run python -c "import ast, pathlib; missing=[]; [missing.extend([(p, n.name) for n in ast.walk(ast.parse(p.read_text(encoding='utf-8'))) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and not n.name.startswith('_') and not ast.get_docstring(n)]) for p in pathlib.Path('nautilus').rglob('*.py')]; assert not missing, missing"`
- **Commit**: `docs: add docstrings to public surfaces`
- **References**: design §3.

### [VERIFY] Task 4.4 — Quality checkpoint (quality batch 1)
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit`
- **Done when**: All four exit 0.
- **Commit**: `chore(quality): pass checkpoint` (if fixes needed)

### Task 4.5 — Ensure `broker.close()` idempotency across all adapter types (NFR + AC-8.6 recheck)
- **Do**: Add `tests/unit/test_close_idempotency.py` that constructs a broker with 2 PG + 2 pgvector sources (mocked pools), calls `close()` three times, asserts `pool.close` called exactly once per adapter. Also asserts `broker._closed` flag set.
- **Files**: `tests/unit/test_close_idempotency.py`.
- **Done when**: Test passes.
- **Verify**: `uv run pytest tests/unit/test_close_idempotency.py -q`
- **Commit**: `test(core): lock in broker.close() idempotency across adapter mix`
- **References**: FR-17, AC-8.6.

### Task 4.6 — VE1: Start pgvector container (via docker run) and seed fixtures
- **Do**:
  - Add `.ve-dsn.txt` and `.ve-cid.txt` to `.gitignore` (project root) so VE artifacts never accidentally land in a commit. These ephemeral files live at the project root (NOT `/tmp/`) so the VE sweep is Windows/git-bash portable.
  - Start the container detached so its lifecycle is independent of the starter process (avoids the testcontainers atexit-teardown bug where the DSN goes dead as soon as the starter Python exits):
    - `docker run -d --rm -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres -e POSTGRES_DB=nautilus -p 0:5432 pgvector/pgvector:pg17 > .ve-cid.txt`
    - Resolve the published host port: `PORT=$(docker port "$(cat .ve-cid.txt)" 5432/tcp | awk -F: '{print $NF}' | head -n1)`
    - Construct and persist DSN: `echo "postgresql://postgres:postgres@localhost:${PORT}/nautilus" > .ve-dsn.txt`
  - Healthcheck poll (60 s ceiling): `for i in $(seq 1 60); do pg_isready -d "$(cat .ve-dsn.txt)" >/dev/null 2>&1 && break || sleep 1; done`.
  - Bootstrap pgvector + seed fixtures: `psql "$(cat .ve-dsn.txt)" -c "CREATE EXTENSION IF NOT EXISTS vector;" && psql "$(cat .ve-dsn.txt)" -f tests/fixtures/seed.sql`.
  - Export for downstream VE tasks (VE2 reads `.ve-dsn.txt` fresh): `export TEST_PG_DSN="$(cat .ve-dsn.txt)" TEST_PGV_DSN="$(cat .ve-dsn.txt)"` (single container hosts both sources' tables for the VE sweep).
- **Files**: `.gitignore` (add `.ve-dsn.txt` and `.ve-cid.txt` entries). Ephemeral runtime artifacts: `.ve-dsn.txt`, `.ve-cid.txt` (project-root-relative).
- **Done when**: `.ve-cid.txt` + `.ve-dsn.txt` exist, container is running, and `psql "$(cat .ve-dsn.txt)" -c "SELECT count(*) FROM vulns"` returns `3`; `vector` extension present.
- **Verify**: `test -f .ve-dsn.txt && test -f .ve-cid.txt && docker ps --no-trunc | grep -q "$(cat .ve-cid.txt)" && psql "$(cat .ve-dsn.txt)" -c "SELECT count(*) FROM vulns" | grep -q 3 && echo VE1_PASS`
- **Commit**: `chore(ve): ignore ephemeral VE artifacts` (only for the `.gitignore` change; the container start itself is ephemeral and has no commit)
- **References**: AC-9.2, AC-9.3, FR-16.

### Task 4.7 — VE2: Run MVP e2e test + assert complete audit entry
- **Do**:
  - Read DSN from VE1's artifact: `export TEST_PG_DSN="$(cat .ve-dsn.txt)" TEST_PGV_DSN="$(cat .ve-dsn.txt)"`.
  - Run `uv run pytest tests/integration/test_mvp_e2e.py -m integration -q` against that DSN.
  - After test, inspect `./audit.jsonl`: assert exactly 1 line, parse via `AuditEntry.model_validate_json`, assert `rule_trace` non-empty, `attestation_token` non-null, `facts_asserted_summary["source"] >= 2`, `sources_queried` contains both source ids, `duration_ms > 0`.
- **Files**: none; reads `./audit.jsonl` produced by the test and `.ve-dsn.txt` from VE1.
- **Done when**: MVP e2e test passes AND audit assertions pass.
- **Verify**: `test -f .ve-dsn.txt && export TEST_PG_DSN="$(cat .ve-dsn.txt)" TEST_PGV_DSN="$(cat .ve-dsn.txt)" && uv run pytest tests/integration/test_mvp_e2e.py -m integration -q && uv run python -c "from nautilus.core.models import AuditEntry; import pathlib; lines=pathlib.Path('audit.jsonl').read_text(encoding='utf-8').splitlines(); assert len(lines)==1; e=AuditEntry.model_validate_json(lines[0]); assert e.rule_trace and e.attestation_token and e.duration_ms>0 and e.facts_asserted_summary.get('source',0)>=2; print('VE2_PASS')"`
- **Commit**: None
- **References**: FR-16, AC-9.3, NFR-8, NFR-9, UQ-2.

### Task 4.8 — VE3: Tear down pgvector container, clean artifacts
- **Do**:
  - Force-remove the container (covers both running and stopped): `if [ -f .ve-cid.txt ]; then docker rm -f "$(cat .ve-cid.txt)" 2>/dev/null || true; fi`
  - Remove ephemeral files: `rm -f .ve-dsn.txt .ve-cid.txt audit.jsonl`
- **Files**: none.
- **Done when**: Container no longer listed by `docker ps -a`; ephemeral files removed.
- **Verify**: `! test -f .ve-cid.txt && ! test -f .ve-dsn.txt && ! test -f audit.jsonl && echo VE3_PASS`
- **Commit**: None
- **References**: cleanup protocol.

### Task 4.9 — Final local CI sweep
- **Do**: Run the complete quality gate as a single command chain, including a dependency license scan (NFR-12 — no GPL-family licenses in the closure).
- **Verify**: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -m unit && uv run pytest -m integration && uv run pytest -m "unit or integration" --cov=nautilus --cov-branch --cov-fail-under=80 && uv build && (uv run pip-licenses --fail-on="GPL;AGPL;LGPL" || echo "pip-licenses not installed — skip")`
- **Done when**: Every command exits 0 and the license scan either passes with no GPL-family matches or prints the skip sentinel.
- **Commit**: `chore(ci): pass final local gate` (if fixes needed)
- **References**: NFR-6, NFR-7, NFR-10, NFR-12, AC-9.4.

### Task 4.10 — Create PR and verify CI
- **Do**:
  - Confirm current branch is a feature branch (not `main`/`master`): `git branch --show-current`.
  - `git push -u origin "$(git branch --show-current)"`.
  - `gh pr create --title "feat(core-broker): Phase 1 Nautilus Core Broker" --body-file /tmp/pr-body.md` where `/tmp/pr-body.md` contains a summary of delivered US-1..US-9, notable shortcuts, and link to `specs/core-broker/design.md`.
  - `gh pr checks --watch` until green.
- **Verify**: `gh pr checks | grep -qi "fail" && exit 1 || echo PR_GREEN`
- **Done when**: All CI checks show passing.
- **Commit**: none (PR-level).
- **References**: NFR-7, NFR-10.

### Task 4.11 — Tag `v0.1.0-alpha`
- **Do**: After PR merge (or pre-merge if tagging on feature branch is allowed), `git tag -a v0.1.0-alpha -m "Nautilus Core Broker Phase 1 alpha"`; do NOT push the tag unless the user explicitly approves.
- **Files**: none (git ref only).
- **Done when**: `git tag -l | grep -q "^v0.1.0-alpha$"`.
- **Verify**: `git tag -l | grep -q "^v0.1.0-alpha$" && echo TAG_CREATED`
- **Commit**: none (tag only).
- **References**: release hygiene.

---

## POC Milestone

**Task 1.17** completes when `uv run pytest tests/integration/test_mvp_e2e.py -m integration -q` passes against testcontainers PG+pgvector — proving FR-16 / AC-9.3. At that point Nautilus satisfies the Phase 1 MVP gate: a single `broker.request()` call routes via Fathom to both a PostgreSQL and a pgvector source, executes scoped parameterized queries concurrently, writes exactly one complete audit entry with non-empty `rule_trace`, and returns a signed Ed25519 attestation token.

---

## Task Index

| #    | Title                                                         | Phase | FR / AC refs                                        |
|------|---------------------------------------------------------------|-------|-----------------------------------------------------|
| 1.1  | Scaffold `nautilus/` subpackage skeleton                      | 1     | design §11, UQ-1                                    |
| 1.2  | Extend `pyproject.toml` with deps + tooling                   | 1     | NFR-6, NFR-10, NFR-11                               |
| 1.3  | Create `tests/` skeleton + conftest + fixtures + seed.sql     | 1     | AC-9.1, AC-9.3, §13.3                               |
| 1.4  | [VERIFY] Tooling gate after scaffold                          | 1     | NFR-6, NFR-7                                        |
| 1.5  | Implement config Pydantic models                              | 1     | FR-1, AC-1.1                                        |
| 1.6  | Config loader + env interpolation                             | 1     | FR-1, FR-2, AC-1.1, AC-1.2, AC-1.3, NFR-5          |
| 1.7  | `SourceRegistry`                                              | 1     | FR-1, AC-1.3, AC-1.4                                |
| 1.8  | [VERIFY] Quality checkpoint (config)                          | 1     | —                                                   |
| 1.9  | Shared core Pydantic models                                   | 1     | FR-6, FR-13, AC-7.2, AC-8.3, UQ-5, UQ-6             |
| 1.10 | `IntentAnalyzer` Protocol + `PatternMatchingIntentAnalyzer`   | 1     | FR-3, AC-2.1..2.5, NFR-13                           |
| 1.11 | [VERIFY] Quality checkpoint (analysis)                        | 1     | —                                                   |
| 1.12 | Fathom templates + module + default rules (SPIKE)             | 1     | FR-4, FR-5, AC-3.1, AC-3.6, AC-3.7                  |
| 1.13 | `FathomRouter`                                                | 1     | FR-4, FR-6, FR-7, AC-3.2..3.5                       |
| 1.14 | `Adapter` base + `PostgresAdapter`                            | 1     | FR-8, AC-4.1..4.5, NFR-4                            |
| 1.15 | `PgVectorAdapter` + `Embedder` + `NoopEmbedder`               | 1     | FR-9, AC-5.1..5.4, UQ-3                             |
| 1.16 | `Broker` facade + synth + audit + session                     | 1     | FR-10..14, FR-17, FR-18, AC-6, AC-7, AC-8, UQ-2,4,5 |
| 1.17 | **POC**: MVP e2e integration test                             | 1     | FR-16, AC-9.3, NFR-8, NFR-9                         |
| 1.18 | [VERIFY] Full gate after POC                                  | 1     | —                                                   |
| 2.1  | Promote `RouteResult` to `core/models.py`                     | 2     | design §3.4                                         |
| 2.2  | Unify error hierarchy under `AdapterError`                    | 2     | design §10.1                                        |
| 2.3  | Extract CLIPS multislot encoder                               | 2     | design §3.4, §5.1                                   |
| 2.4  | [VERIFY] Quality checkpoint (refactor 1)                      | 2     | —                                                   |
| 2.5  | Decompose `Broker.arequest` into helpers                      | 2     | design §3.1                                         |
| 2.6  | Isolate attestation payload builder                           | 2     | design §9.3, NFR-14                                 |
| 2.7  | Runtime-checkable Protocols                                   | 2     | design §3                                           |
| 2.8  | Harden field-identifier quoting                               | 2     | NFR-4, §6.2, §7.3                                   |
| 2.9  | [VERIFY] Quality checkpoint (refactor 2)                      | 2     | —                                                   |
| 2.10 | Audit JSON serialization hardening                            | 2     | AC-7.3, AC-7.5, NFR-8                               |
| 3.1  | `test_config_loader.py`                                       | 3     | AC-1.1, AC-1.2, AC-1.3, NFR-5                       |
| 3.2  | `test_source_registry.py`                                     | 3     | AC-1.4                                              |
| 3.3  | `test_pattern_analyzer.py` + determinism property             | 3     | AC-2.2, AC-2.3, AC-2.5, NFR-13                      |
| 3.4  | [VERIFY] Quality checkpoint (tests 1)                         | 3     | —                                                   |
| 3.5  | `test_fathom_router.py` + rule_trace determinism              | 3     | AC-3, FR-6, FR-7, NFR-14                            |
| 3.6  | `test_postgres_adapter.py`                                    | 3     | AC-4, FR-8, FR-17, FR-18                            |
| 3.7  | `test_pgvector_adapter.py`                                    | 3     | AC-5, FR-9, UQ-3                                    |
| 3.8  | [VERIFY] Quality checkpoint (tests 2)                         | 3     | —                                                   |
| 3.9  | `test_synthesizer.py`                                         | 3     | AC-6, FR-10, FR-18                                  |
| 3.10 | `test_audit_logger.py`                                        | 3     | AC-7, FR-11, NFR-8                                  |
| 3.11 | `test_broker.py` (loop guard, close, concurrency, absence)    | 3     | AC-1.5, AC-8.5, AC-8.6, AC-8.7, FR-17, FR-18, NFR-3, UQ-2, UQ-4 |
| 3.12 | [VERIFY] Quality checkpoint (tests 3)                         | 3     | —                                                   |
| 3.13 | `test_sql_injection_static.py` grep guard                     | 3     | NFR-4, design §17                                   |
| 3.14 | `test_operator_allowlist_drift.py`                            | 3     | UQ-6, §6.1, §17                                     |
| 3.15 | [VERIFY] Quality checkpoint (tests 4)                         | 3     | —                                                   |
| 3.16 | Integration: `test_postgres_scope.py`                         | 3     | AC-4.6, FR-8                                        |
| 3.17 | Integration: `test_pgvector_similarity.py`                    | 3     | AC-5.5, FR-9                                        |
| 3.18 | Coverage gate enforcement (≥80% branch)                       | 3     | NFR-6, AC-9.4                                       |
| 3.19 | Module-presence meta test                                     | 3     | AC-9.5                                              |
| 3.20 | [VERIFY] Full test gate (unit + integration + coverage)       | 3     | —                                                   |
| 4.1  | `pyproject.toml` metadata polish                              | 4     | NFR-10, NFR-12                                      |
| 4.2  | README quickstart                                             | 4     | AC-8.1, NFR-10                                      |
| 4.3  | Public-surface docstring sweep                                | 4     | design §3                                           |
| 4.4  | [VERIFY] Quality checkpoint (quality 1)                       | 4     | —                                                   |
| 4.5  | `broker.close()` idempotency recheck across adapter mix       | 4     | FR-17, AC-8.6                                       |
| 4.6  | **VE1**: Startup testcontainers + seed fixtures               | 4     | AC-9.2, AC-9.3, FR-16                               |
| 4.7  | **VE2**: Run MVP e2e + assert complete audit entry            | 4     | FR-16, AC-9.3, NFR-8, NFR-9, UQ-2                   |
| 4.8  | **VE3**: Tear down testcontainers + clean artifacts           | 4     | cleanup                                             |
| 4.9  | Final local CI sweep                                          | 4     | NFR-6, NFR-7, NFR-10, NFR-12, AC-9.4                |
| 4.10 | Create PR + verify CI                                         | 4     | NFR-7, NFR-10                                       |
| 4.11 | Tag `v0.1.0-alpha`                                            | 4     | release hygiene                                     |

---

## Notes

- **POC shortcuts taken in Phase 1 (paid down in Phase 2):**
  - Inline `RouteResult` dataclass in `fathom_router.py` (promoted to `core/models.py` in Task 2.1).
  - `EmbeddingUnavailableError` lives in `embedder.py` (moved to `adapters/base.py` in Task 2.2).
  - CLIPS multislot encoding inlined in `FathomRouter` (extracted in Task 2.3).
  - `Broker.arequest` is a single monolithic method (decomposed in Task 2.5).
  - Protocols not yet `@runtime_checkable` (fixed in Task 2.7).
  - Field-identifier quoting uses a hand-rolled regex check (hardened in Task 2.8).
  - Audit JSONL write lacks explicit `flush()` per entry (hardened in Task 2.10).
  - Phase 1 requires `table` on `SourceConfig` even for `postgres` sources (acceptable for MVP — no routing rules create scopes without a known table in Phase 1).

- **Phase 1 shortcuts that remain acceptable:**
  - `NoopEmbedder` with `strict=True` is the default broker embedder — pluggable real embedder is explicitly Phase 3 (UQ-3).
  - Ephemeral Ed25519 keypair regenerated per process unless `attestation.private_key_path` is set (documented, not a defect).
  - `InMemorySessionStore` — Phase 2 swap target.

- **Risks being tracked during execution:**
  - Task 1.12 is the SPIKE (design §17): if Fathom's compiler rejects `then.assert`, resolve before proceeding. If blocked, fall back to `assert-fact` action form per fathom-rules documentation.
  - Task 1.17 depends on testcontainers Docker availability locally; Task 4.6/4.7/4.8 re-validate in the VE sweep.
  - NFR-3 concurrency test (Task 3.11 case f) is timing-sensitive on slow CI; use relative overlap (≥50%) not absolute duration.

- **NFR-1 coverage (informational):** NFR-1 (Fathom `engine.evaluate()` p95 < 5 ms) is **informational for Phase 1** — not verified by any gate task. A micro-benchmark may be added in Phase 2 if observed latency regresses.
