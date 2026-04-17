---
spec: reasoning-engine
phase: research
created: 2026-04-15
---

# Research: reasoning-engine

## Executive Summary

The spec is feasible: every Phase-2/3 reasoning capability lands on Fathom `>=0.3.0` surfaces already present (hierarchies, FactManager TTL, FactStore reference schema, existing rule-output templates), and all four new adapters (Elasticsearch, REST, Neo4j, ServiceNow) fit the Phase 1 `Adapter` Protocol without modification. Key architectural decisions are settled: the shared session store will be Postgres (reusing asyncpg + the Phase 1 pool conventions; Redis rejected as unneeded additional stateful component), the LLM analyzer is a pluggable `LLMIntentProvider` Protocol with pattern-matching fallback as the air-gap default, and a new `nautilus/cli.py` entry point (`serve`, `health`, `version`) must be added as net-new scope to make the Docker image and MCP/REST transports bootable. The single most important risk is audit/attestation hash canonicalization: several new reasoning fields (temporal scoping `expires_at`/`valid_from`, LLM provenance) and the new `AttestationSink` dispatch interact with Phase 1's `scope_hash` / `rule_trace_hash` and must be versioned, not silently extended, or every Phase-1 attestation verifier breaks.

## Feasibility / Risk / Effort

`Feasibility: High | Risk: Medium | Effort: L`

- **Feasibility High**: every capability resolves to either an existing Fathom external / template / store, or an additive Nautilus-local extension; no Fathom upstream changes are strictly required.
- **Risk Medium**: concentrated in three places — scope-hash versioning for attestation back-compat, LLM-analyzer determinism/air-gap posture, and cooperative (not forensic) handoff detection.
- **Effort L**: ~55–60 tasks estimated; the adapter + transport surface expands quickly but follows Phase 1 templates, while cross-agent flow + session-store + LLM analyzer introduce genuinely new architectural surfaces.

## Key Recommendations

1. Adopt `PostgresSessionStore` as the production cumulative-exposure backend, keep `InMemorySessionStore` as the air-gap-friendly default, and model the schema after `fathom/fleet_pg.py` (UUID + JSONB) without importing the `FactStore` API itself.
2. Implement classification hierarchy via Nautilus-local `classification.yaml` + a sibling sub-category hierarchy file pattern (two `fathom-dominates` calls) to avoid a Fathom upstream extension.
3. Require cross-agent information flow to be declared via an explicit `Broker.declare_handoff(...)` API (cooperative model, never silent) and reinforce it with the session-store-enforced cumulative exposure path.
4. Ship a pluggable `LLMIntentProvider` Protocol with three providers (Anthropic, OpenAI, local OpenAI-compatible) plus a `FallbackIntentAnalyzer` wrapper; the `nautilus serve --air-gapped` flag forces `analysis.mode = pattern` and warns on conflicting config.
5. Version the attestation `scope_hash` (`scope_hash_v2`) before adding `expires_at` / `valid_from` slots to `scope_constraint` — do not extend v1 silently.
6. Use `httpx.AsyncClient` for both the REST and ServiceNow adapters (no `aiosnow`), and add an `endpoints: list[EndpointSpec]` field to `SourceConfig` to drive REST's per-endpoint operator subset.
7. Ship a distroless runtime image via `ghcr.io/astral-sh/uv:python3.14-bookworm-slim` → `gcr.io/distroless/cc-debian13`, with `nautilus health` as the `HEALTHCHECK` subcommand (no shell in distroless).
8. Implement an `AttestationSink` Protocol parallel to `AuditSink` with `Null` / `File` / `Http` implementations; default for air-gap is `FileAttestationSink` with operator-owned drainer.

---

## Stream A — Reasoning Findings

### 1. Classification hierarchy

#### Finding
- Fathom already has `HierarchyDefinition` (`fathom/models.py:342`):
  ```python
  class HierarchyDefinition(BaseModel):
      name: str
      levels: list[str]              # rank = list index
      compartments: list[str] | None  # global, not per-level
  ```
  Rank comparison is implicit in `levels.index(...)` inside `dominates()` (`fathom/engine.py:106–129`). Compartments are handled by `fathom-has-compartment` / `fathom-compartments-superset` (space-separated strings).
- Hierarchy YAML is loaded via `FunctionDefinition.hierarchy_ref` → resolved against `{parent}/hierarchies/{file}` (`fathom/engine.py:700–744`), registered into `_hierarchy_registry`, then reachable from rules via the `"<name>"` argument to `fathom-dominates`.
- Fixture format (`fathom/tests/fixtures/hierarchies/classification.yaml`):
  ```yaml
  name: classification
  levels: [unclassified, cui, confidential, secret, top-secret]
  ```
- Nautilus templates today (`nautilus/rules/templates/nautilus.yaml`) model `source.classification` as a single `string` slot and `agent.clearance` likewise; **no compartments slot exists**. No rule currently calls `fathom-dominates`; denial is purpose-based only (`denial.yaml`).
- design.md §Classification Hierarchy asks for:
  - `sub_categories` per level (e.g. `cui` → `cui-sp-cti / cui-sp-prvcy / cui-sp-tax`)
  - per-level `compartments` (e.g. `top-secret` → `sci-a / sci-b / sci-c`)
  - custom hierarchies (commercial tiers)

#### Recommendation
Three concrete changes, in this order:
1. Nautilus-side: add `classification.yaml` under `nautilus/rules/hierarchies/` and a `classification` function YAML referencing it. Ship a `default-classification-deny` rule (salience 150) that emits `denial_record` when `(not (fathom-dominates ?clearance ?subj_comps ?source_cls ?src_comps "classification"))`.
2. Extend `source` and `agent` templates with `compartments` (space-separated string) and `sub_category` (string) slots. Feed them from `SourceConfig` / `context["compartments"]` in `FathomRouter.route()`.
3. For sub-categories: treat them as a second hierarchy file per level group (e.g. `cui-sub.yaml`). Two-step dominance check in a rule: first dominate on the top-level ladder, then — when `source.classification == "cui"` and `source.sub_category != ""` — also dominate on the `cui-sub` ladder. This keeps `HierarchyDefinition.levels` flat (what Fathom supports today) without forcing a Fathom change.

Custom hierarchies are already possible today — users drop a `custom-hierarchy.yaml` into their `user_rules_dirs` and reference it from their own rule. No code change needed; document the pattern.

#### Fathom gap?
**Mostly no.** `sub_categories` can be modeled as sibling hierarchy files + a second `fathom-dominates` call. Per-level compartments require a small Fathom extension if we want the dominance check to automatically include compartments *scoped to a level*; today compartments are a flat global set. **If** the user wants the cleaner `top-secret.compartments: [sci-a, sci-b]` encoding from design.md literally, `HierarchyDefinition` needs per-level `allowed_compartments` and `dominates()` needs to validate required compartments against the resource's level's compartment set. That is a ~30-line extension in `fathom/models.py` + `fathom/engine.py`. Recommend deferring until a concrete ruleset demands it — the two-hierarchy workaround is functionally equivalent.

#### Risk
Low. The two-hierarchy workaround reuses already-tested code paths. Main risk is rule-author confusion if we ship both a top-level and sub-category ladder without clear documentation.

---

### 2. Cumulative exposure tracking (session store)

#### Finding
- Phase 1 has `SessionStore` Protocol + `InMemorySessionStore` (`nautilus/core/session.py`). The broker calls `get` before routing and `update` after synthesis (`broker.py:_route`, `_update_session`). The session dict is flattened into a `session` fact with exactly two slots today (`id`, `pii_sources_accessed`).
- Fathom's `FactManager` **is not** session-scoped. `assert_fact` writes into the CLIPS environment's single global working memory, and `FathomRouter.route()` calls `clear_facts()` on every request (`fathom_router.py:98`). So cumulative state in Nautilus must live *outside* CLIPS between requests, then be re-asserted into working memory on each `route()` call.
- Fathom `>=0.2.0` ships a separate persistence layer — `FactStore` Protocol (`fathom/fleet.py`) with three implementations:
  - `InMemoryFactStore`
  - `PostgresFactStore` (`fathom/fleet_pg.py` — JSONB + LISTEN/NOTIFY, needs `fathom-rules[fleet-pg]`)
  - `RedisFactStore` (`fathom/fleet_redis.py` — hashes + Streams, needs `fathom-rules[fleet]`)
  This is an **async fact database** intended for multi-process "fleet" coordination. It is not automatically wired into the Engine — it is a standalone store.
- Fathom also has per-template `FactManager.set_ttl(template, seconds)` + `cleanup_expired()` (`fathom/facts.py:41, 166`). Used for time-bound facts within a single Engine's working memory.

#### Recommendation
**Use Postgres, not Redis, and not in-process.**

Tradeoffs (brief:82 open question):
| Backend | Air-gap-deployable | Durability across broker restart | Multi-process broker | Complexity to add |
|---|---|---|---|---|
| In-process (today) | yes | **no** (RAM) | **no** | 0 |
| Redis | yes (self-hosted) but adds a stateful process | yes (if AOF) | yes | med (new dep, ops) |
| Postgres | **yes** — we already ship asyncpg + pgvector, same process model | yes | yes | low (reuse connection pool) |

Nautilus already depends on `asyncpg>=0.30.0` and ships `PostgresAdapter`. A `PostgresSessionStore` reuses that dependency, the same connection-string env-var pattern (`${...}` interpolation in YAML), and the same air-gap story. Redis adds a second stateful component with no corresponding benefit — LISTEN/NOTIFY change-subscription is irrelevant to the session-store use case (the broker reads session state synchronously at the start of `route()`).

Implementation sketch:
- Promote `SessionStore` Protocol to async (`aget` / `aupdate` / `aappend`). Broker already awaits in `arequest`.
- New `nautilus/core/session_pg.py` with `PostgresSessionStore` — one table `nautilus_session_state (session_id TEXT PRIMARY KEY, state JSONB NOT NULL, updated_at TIMESTAMPTZ)`. Upsert on `update`.
- Config: `session_store.backend: memory|postgres`, `session_store.dsn: ${NAUTILUS_SESSION_DSN}`.
- For counters + multiset fields (`pii_sources_accessed`, `data_types_seen`, `sources_visited`), store as JSONB arrays; `FathomRouter.route()` expands them into multiple `session_exposure` facts (template TBD) before calling `evaluate()`.

**Do not** try to use `FactStore` as the session store. Its async-first API, subscription model, and fact-id semantics are mismatched — it is designed for cross-process fact synchronization, not for per-session state blobs. However, we can steal its wire format (`fleet_facts` schema — UUID + template + JSONB data) and table layout as a proven reference.

**FactManager session-scoping wrapper**: no. `FactManager` is single-environment; wrapping it is the wrong abstraction. The session store lives *above* CLIPS. `FactManager.set_ttl` is separately useful for temporal scoping (item 6 below) within a single request's working memory.

#### Fathom gap?
**No.** All plumbing already exists in Nautilus + Fathom; we just need a Postgres-backed `SessionStore` implementation and a richer `session` template (multislot for `data_types_seen`, `sources_visited`, `pii_sources_accessed_list`).

#### Risk
Medium — schema migration story. Nautilus doesn't currently own any DDL (adapters connect to pre-existing DBs). Adding `nautilus_session_state` means the broker needs a bootstrap/migrate step on first `arequest`. Recommend a `Broker.setup()` that runs `CREATE TABLE IF NOT EXISTS` once per pool, mirroring `PostgresFactStore._ensure_schema()` in `fleet_pg.py:165-195`. Alternative (simpler): `InMemorySessionStore` remains the default; `PostgresSessionStore` opt-in via config for production.

---

### 3. Cross-agent information flow tracking

#### Finding
- design.md §Cumulative Exposure Tracking gives a concrete rule shape:
  ```yaml
  - name: information-flow-violation
    when:
      data_handoff:
        source_agent_clearance: greater_than($receiving_agent.clearance)
        data_classification: greater_than($receiving_agent.clearance)
  ```
  This implies a `data_handoff` fact template and a mechanism for producing such facts.
- There is **no existing infrastructure for this** in Fathom or Nautilus:
  - `agent` template is single-slotted — one agent per request (`nautilus/rules/templates/nautilus.yaml:9-14`).
  - No agent registry exists; `agent_id` is just a `str` field on `BrokerResponse`.
  - No cross-request correlation primitive exists. `session_id` is per-session but scoped to a single logical actor.
- "Handoff" is fundamentally not detectable *from inside* the broker — the broker sees independent requests. Detection has to be explicit: either (a) the orchestration layer declares a handoff via a new `Broker.declare_handoff(from_agent, to_agent, data_refs, session_id)` API, or (b) we log enough data in the audit stream that a postmortem correlator can reconstruct it.

#### Recommendation
Go with an **explicit declaration API** — least-surprise, deterministic, auditable:
- New method `Broker.declare_handoff(*, from_agent_id, to_agent_id, session_id, data_classifications, rule_trace_refs)` that (i) asserts a `data_handoff` fact and (ii) runs a reasoning-only pass with NO adapter execution. Returns a `HandoffDecision` (allow / deny / escalate).
- New `data_handoff` Fathom template:
  ```yaml
  - name: data_handoff
    slots:
      - { name: from_agent_id,          type: string, required: true }
      - { name: to_agent_id,            type: string, required: true }
      - { name: from_agent_clearance,   type: string, required: true }
      - { name: to_agent_clearance,     type: string, required: true }
      - { name: data_classification,    type: string, required: true }
      - { name: data_compartments,      type: string, default: "" }
      - { name: session_id,             type: string, required: true }
  ```
- Persistent agent registry: add `agents:` top-level in `nautilus.yaml` (id → clearance, compartments, default_purpose). This is needed so `declare_handoff(from_agent_id=..., to_agent_id=...)` can look up the receiving agent's clearance without forcing callers to repeat it.
- Rule uses `fathom-dominates` (inverted) to detect the violation — zero new Fathom externals required.

#### Fathom gap?
**No.** Everything resolves to (a) a new Nautilus template, (b) a new Nautilus-side API, (c) reuse of `fathom-dominates`.

#### Risk
Medium. The explicit-declaration model puts the burden on the orchestrator to call `declare_handoff`. A malicious or buggy orchestrator can simply not call it. Mitigation: make this an *adjunct* signal — not the only line of defense. The cumulative-exposure session store (item 2) still enforces per-agent limits independently. Document that handoff detection is **cooperative, not forensic**.

---

### 4. Classification escalation rules

#### Finding
- design.md §Cumulative Exposure Tracking rule `classification-escalation` is stated declaratively:
  ```yaml
  when:
    session:
      accessed_data_types: contains_all($escalation_rule.trigger_combination)
    escalation_rule:
      as: $escalation_rule
  ```
- Fathom has no built-in `contains_all` external, but the rule can be expressed with existing primitives. `session.accessed_data_types` is a space-separated multislot (like `intent.data_types_needed`). We can express "contains all" via multiple CLIPS `(test (overlaps ...))` conjunctions, OR a small new `contains-all` external (~10 lines, mirrors `overlaps` in `nautilus/rules/functions/overlaps.py`).
- The "trigger combinations" need to be asserted as facts of a new template `escalation_rule` before `evaluate()`. Nautilus can load these from a YAML file — `config.escalation.path: ./escalation-rules.yaml`, parsed once at `Broker.from_config`, asserted once per request alongside the `source` facts.

#### Recommendation
- Add `contains-all` external function in `nautilus/rules/functions/` (Nautilus-local, not Fathom). Mirrors the existing `overlaps`/`not-in-list` registration pattern.
- Add `escalation_rule` template:
  ```yaml
  - name: escalation_rule
    slots:
      - { name: id,                    type: string, required: true }
      - { name: trigger_combination,   type: string, required: true }  # space-sep multislot
      - { name: resulting_level,       type: string, required: true }
      - { name: action,                type: symbol, required: true, allowed_values: [deny, escalate, notify] }
  ```
- Ship one default escalation-rules pack (`nautilus/rules/escalation/default.yaml`) with the canonical PII-aggregation case from design.md.
- Users extend via `config.rules.escalation_rules_dir`.

#### Fathom gap?
**No.** Everything is inside Nautilus-land. The `contains-all` external stays in Nautilus per the existing precedent (`overlaps`, `not-in-list`) — it's a policy primitive, not a Fathom-universal primitive.

#### Risk
Low. Same pattern as denial rules. Main concern: `escalation_rule` facts need to be asserted on every `route()` call; add one more `_engine.assert_fact` loop in `FathomRouter.route()`. Measured cost: negligible — rule-pack size is bounded and CLIPS handles thousands of facts per microsecond.

---

### 5. LLM-based intent analyzer

#### Finding
- Phase 1 already defines `IntentAnalyzer` Protocol (`nautilus/analysis/base.py`) — `analyze(intent, context) -> IntentAnalysis`. `PatternMatchingIntentAnalyzer` is the only implementation.
- `IntentAnalysis` is a Pydantic model with `raw_intent`, `data_types_needed: list[str]`, `entities: list[str]`. Sorted deterministically (NFR-13).
- No LLM dependency in nautilus pyproject today. Fathom is pure-Python + CLIPS; no LLM dep there either.
- Air-gap requirement is hard (design.md §Deployment Models, `nautilus serve --air-gapped`). Air-gap fallback is non-negotiable.

#### Recommendation

**Provider abstraction: pluggable interface, with 3 concrete implementations.** Don't pick one provider — pick a contract.

```python
# nautilus/analysis/llm/base.py
class LLMIntentProvider(Protocol):
    async def analyze(self, intent: str, context: dict[str, Any]) -> IntentAnalysis: ...
    def health_check(self) -> None: ...  # raises on startup if unreachable
```

Concrete providers:
1. `AnthropicProvider` (optional dep `anthropic>=0.40`, uses tool-use for structured output binding to `IntentAnalysis` Pydantic model).
2. `OpenAIProvider` (optional dep, JSON mode + Pydantic schema).
3. `LocalInferenceProvider` (calls a local OpenAI-compatible endpoint — vLLM, llama.cpp server). This is the **air-gap-compatible** path when organizations run their own inference.

**Structured output strategy: Pydantic round-trip via tool-use / JSON mode.** Both Anthropic and OpenAI support forcing a JSON schema. Pass `IntentAnalysis.model_json_schema()` → parse via `IntentAnalysis.model_validate_json()`. On parse failure → fall back to pattern analyzer (below).

**Fallback mechanism (opt-in LLM, pattern-default):**

```python
class FallbackIntentAnalyzer:
    def __init__(self, primary: LLMIntentProvider, fallback: PatternMatchingIntentAnalyzer,
                 timeout_s: float = 2.0):
        ...
    async def analyze(self, intent, context):
        try:
            async with asyncio.timeout(self.timeout_s):
                return await self._primary.analyze(intent, context)
        except (TimeoutError, LLMProviderError, ValidationError):
            return self._fallback.analyze(intent, context)
```

Three config modes:
- `analysis.mode: pattern` (Phase 1 default; air-gap default)
- `analysis.mode: llm-first` (LLM primary, pattern fallback on failure — this is the recommended production mode)
- `analysis.mode: llm-only` (fail-closed if LLM unreachable — for debugging / never air-gap)

The existing `PatternMatchingIntentAnalyzer` stays exactly as-is. It already implements the Protocol; the fallback wrapper composes it.

**Prompt template strategy**: ship one locked prompt template in `nautilus/analysis/llm/prompts/intent_v1.txt`, versioned via `analysis.prompt_version: v1` in config. Include the agent's configured `data_types` keyword map in the prompt so the LLM emits consistent labels. Deterministic `temperature: 0`.

#### Fathom gap?
**No.** Intent analysis is upstream of Fathom. Its output is already a `IntentAnalysis` Pydantic model the router consumes unchanged.

#### Risk
Medium. Risks split across three axes:
- **Provider drift**: Anthropic/OpenAI APIs change — pin SDK versions, test via recorded fixtures (`pytest-recording`).
- **Determinism**: Even `temperature: 0` is not perfectly reproducible across model snapshots. Audit log must capture `llm_provider`, `llm_model`, `llm_version`, `raw_response_hash` so failures can be reconstructed. This is a **new field on `AuditEntry`** — coordinate with audit-canonicalization rules (don't break Phase-1 hashes; add fields as opt-in metadata).
- **Air-gap regression**: Easy to accidentally default to `llm-first` and break air-gap. Add a CLI assertion: `nautilus serve --air-gapped` forces `analysis.mode = pattern` and warns if config says otherwise.

---

### 6. Purpose-bound temporal scoping

#### Finding
- design.md mentions "purpose-bound temporal scoping — scope expiry / time-window constraints as Fathom facts" (brief:37). The existing `scope_constraint` template has `source_id`, `field`, `operator`, `value` (`nautilus/rules/templates/nautilus.yaml:43-49`). No `expires_at` or `valid_from` slot.
- Fathom `FactManager` supports per-template TTL (`set_ttl(template, seconds)` + `cleanup_expired()` — `fathom/facts.py:41, 166`). TTL is measured against `time.time()` at assertion; `cleanup_expired()` must be called explicitly.
- `fathom-changed-within(timestamp_value, window_seconds)` is an available external (`fathom/engine.py:318`) — checks if a timestamp fact is recent.
- Nothing in `FathomRouter.route()` currently calls `cleanup_expired()`.

#### Recommendation

Scope expiry has **two meaningfully different semantics**:
1. **Per-request**: "this scope constraint only applies if the request arrives within window X of the declared purpose start." Evaluated every `route()` by comparing `context["purpose_start"]` or `session.purpose_start_ts` to `time.time()`. Implemented via `fathom-changed-within` in the rule LHS.
2. **At session start**: "the purpose itself expires N minutes after session creation; after that, fall back to unpurposed scope." This is session-state evaluated when the session fact is asserted.

Recommend supporting **both** — they're independent:
- Extend `scope_constraint` template with two optional slots:
  ```yaml
  - { name: expires_at,  type: string, default: "" }   # ISO-8601; empty = no expiry
  - { name: valid_from,  type: string, default: "" }   # ISO-8601; empty = immediate
  ```
- Broker-side enforcement: after `route_result`, filter `scope_constraints` whose `expires_at` is past or `valid_from` is future. This is a policy-visible filter — log dropped constraints to `denial_records` so the audit trail still shows them.
- For the "purpose expires" semantic: extend `session` template with `purpose_start_ts: float` (epoch seconds), `purpose_ttl_seconds: integer`. Rule `purpose-expired-deny` uses `fathom-changed-within` to check freshness.

**Do not** try to hang scope expiry off `FactManager.set_ttl`. That expires the fact from working memory, which means by the time `scope_constraint` is queried it's gone — you can't distinguish "expired" from "never existed" for audit purposes. Explicit `expires_at` slot + broker-side filter is the right model.

#### Fathom gap?
**No.** All slots are additive to the Nautilus `scope_constraint` template. The one existing Fathom external we reuse (`fathom-changed-within`) is already registered.

#### Risk
Low. One subtle issue: the stable-hash audit canonicalization in Phase 1 (attestation payload §9.3, `broker.py:_hash_scope`) hashes `(source_id, field, operator, value)` — the current 4-tuple. Adding `expires_at` / `valid_from` to the hash would change all Phase-1 hashes. Recommend (a) making the new slots audit-visible but **excluded from `_hash_scope`** for backward compatibility, OR (b) versioning the scope hash (`scope_hash_v2`) so old verifiers keep working. Coordinate with stream-B attestation work.

---

## Stream B — Adapters + Transport Findings

### 1. Elasticsearch adapter

#### Finding

- Library split: `elasticsearch-py` (core client, always present) and `elasticsearch-dsl` (now merged as `elasticsearch.dsl` inside the same package — `AsyncSearch`, `Query`, `Bool`, `Term`, `Terms`, `Range`, `Match`, `Wildcard`). Both are sync+async; `AsyncElasticsearch` is the async client class. Auth: `basic_auth=(user, pw)`, `api_key`, `ca_certs=`, `ssl_assert_fingerprint=` — all air-gap friendly (no cloud callback).
- Operator → DSL mapping (SQL-flavored allowlist → ES query DSL, all inside `bool.filter` so no scoring):
  | Nautilus op | ES DSL           | Value shape       |
  |-------------|------------------|-------------------|
  | `=`         | `Term(field, v)` | scalar            |
  | `!=`        | `Bool(must_not=[Term(field, v)])` | scalar |
  | `IN`        | `Terms(field, [vs])` | list          |
  | `NOT IN`    | `Bool(must_not=[Terms(field, [vs])])` | list |
  | `<` `>` `<=` `>=` | `Range(field, lt/gt/lte/gte=v)` | scalar |
  | `BETWEEN`   | `Range(field, gte=a, lte=b)` | 2-tuple |
  | `LIKE`      | `Wildcard(field, value=pat)` where `%`→`*`, `_`→`?` (translation layer) | string |
  | `IS NULL`   | `Bool(must_not=[Exists(field=...)])` | none |
- Index allowlisting: analog to Phase 1 `SourceConfig.table` — new field `SourceConfig.index` (single index name, regex-validated identical to `validate_field` with colons/dashes allowed: `^[a-z0-9][a-z0-9._-]*$` per ES naming rules). Adapter refuses `connect()` if not set, mirroring `PostgresAdapter.connect()` guard.
- Scope values go through the DSL API as Python values — never string-concatenated into query JSON. The client serializes to JSON and ES does type coercion against the mapping, so no manual type-cast analog to `text[]` is required.
- `LIKE` carries a known perf cliff; the adapter emits a warning when a `LIKE` pattern is fully-unanchored (leading `*`). Not blocked — policy question.

#### Recommendation

`elasticsearch>=8.x` (official client) via `AsyncElasticsearch` + the bundled `elasticsearch.dsl` submodule. Implement scope translation in an `_apply_scope(search: AsyncSearch, scope)` helper that returns an `AsyncSearch` with `filter(...)` / `exclude(...)` chained — mirror of `PostgresAdapter._build_sql`.

#### Template reuse?

~80%. Lifecycle (`connect`/`execute`/`close`), `validate_operator` usage, per-constraint dispatch loop, `SourceConfig`-driven target (`index` instead of `table`), `source_type = "elasticsearch"` are identical. What changes: operator branches compose DSL objects instead of SQL fragments; result shape is `hits.hits._source` rather than asyncpg records.

#### Risk

`LIKE` → `Wildcard` mapping is semantically different from SQL LIKE (ES analyzes tokens, not strings). Mitigation: require `keyword` subfield (doc standard) and translate operand with `%→*`, `_→?` in one vetted helper with a drift-guard test. If a source's mapping lacks a `keyword` subfield, `LIKE` fails loud rather than silently wrong.

---

### 2. REST API adapter

#### Finding

- Library: `httpx` `AsyncClient` — already in the project's dep-neighborhood via transitive deps. Connection pool, base_url, default headers, `httpx.Timeout(connect=, read=, write=, pool=)`, context-manager lifecycle — all first-class.
- Scope enforcement for someone-else's REST API maps to three constraint classes, which we can express by extending `SourceConfig` rather than inventing new scope primitives:
  1. Endpoint allowlist — `SourceConfig.endpoints: list[EndpointSpec]` where each `EndpointSpec` names a path template, method, and per-param scope-binding map (e.g., `path_params: {tenant_id: scope_field}`). Anything not in the allowlist → `ScopeEnforcementError` at adapter load time (fail fast, design §6.3).
  2. Parameter binding — each `ScopeConstraint` is matched to the endpoint's declared parameter slot; operator determines serialization:
     | Op     | Query-param shape (typical REST convention)   |
     |--------|-----------------------------------------------|
     | `=`    | `?field=v`                                    |
     | `!=`   | `?field__ne=v` (per-source convention; configurable) |
     | `IN`   | repeated: `?field=v1&field=v2` or `?field=v1,v2` (configurable) |
     | `<` `>` `<=` `>=` | `?field__lt=v` etc. (configurable) |
     | `BETWEEN` | two params (`?field__gte=a&field__lte=b`) |
     | `LIKE` | `?field__contains=pat` (configurable)         |
     | `IS NULL` | `?field__isnull=true` (configurable)       |
     `NOT IN` is rejected by default (most REST APIs have no idiomatic form) unless the endpoint declares a per-op template.
  3. SSRF defense — the HTTP client is constructed with a fixed `base_url` per source and the adapter refuses to follow redirects to a different host (`follow_redirects=False` or manual validation). Outbound host is pinned by `SourceConfig.connection` (URL); path is assembled only from the allowlisted `EndpointSpec`. An additional belt-and-braces check: `httpx-secure` (`/zaczero/httpx-secure`) provides drop-in SSRF blocking of private-IP egress — opt-in for non-air-gap deployments only (air-gap already isolates this).
- Auth: per-source. Supported in `SourceConfig.auth`:
  - `{type: bearer, token_env: NAUTILUS_MY_SOURCE_TOKEN}` — loaded once at `connect()`, set as default `Authorization: Bearer ...` header.
  - `{type: basic, username_env, password_env}`.
  - `{type: mtls, cert_path, key_path}` — `httpx.AsyncClient(verify=..., cert=(cert, key))`.
  - `{type: none}`.
  No OAuth2 client-credentials in Phase 2 (air-gap IdP not assumed); `httpx-oauth` available if operator-platform adds it later.

#### Recommendation

`httpx>=0.27` `AsyncClient` with per-source base_url + default-headers construction at `connect()`. Extend `SourceConfig` with `endpoints: list[EndpointSpec]` and `auth: AuthConfig` (Pydantic discriminated union). Scope-constraint → query-param translation routed through a small config-driven operator template table (same Literal union as §6.1, but with a per-endpoint `param_style` override).

#### Template reuse?

~60%. Protocol shape + operator-allowlist loop + error taxonomy carry over; the `_build_sql` equivalent (`_build_request`) has to walk `EndpointSpec` declarations and compose `httpx.Request`, which is net-new logic. This is the adapter with the most new surface area.

#### Risk

Semantic drift between Nautilus operators and the remote API's filter convention (there is no REST standard). Mitigation: per-source `operator_templates` config block with a drift-guard test that every declared operator round-trips through the allowlist. If an API demands an operator the allowlist forbids, stream-A's rule changes — we do NOT loosen the allowlist.

---

### 3. Neo4j adapter

#### Finding

- Library: official `neo4j>=5` driver — ships async via `AsyncGraphDatabase.driver(uri, auth=(user, pw))` and `AsyncDriver.session() → AsyncSession` with `await session.run(cypher, parameters=dict)` or `await driver.execute_query(cypher, parameters_=dict, routing_=READ, database_="neo4j")`. Parameters use `$name` placeholders — the Cypher analog of asyncpg's `$N` positional. Cypher forbids parameterizing labels/relationship-types/property-names, only values.
- Scope enforcement model: `MATCH (n:<Label> {<prop_filters>}) WHERE <scope-WHERE> RETURN n LIMIT $nautilus_limit`.
  - Label allowlist: `SourceConfig.label` (single primary label per source, regex `^[A-Z][A-Za-z0-9_]*$`). Not parameterizable — treat as trusted identifier like Postgres's `table`, validated + quoted with backticks (`` `Label` ``).
  - Operator → WHERE clause:
    | Op       | Cypher                      | Param style    |
    |----------|-----------------------------|----------------|
    | `=`      | `n.field = $p0`             | scalar         |
    | `!=`     | `n.field <> $p0`            | scalar         |
    | `IN`     | `n.field IN $p0`            | list           |
    | `NOT IN` | `NOT n.field IN $p0`        | list           |
    | `<` `>` `<=` `>=` | `n.field < $p0` etc. | scalar      |
    | `BETWEEN`| `n.field >= $p0 AND n.field <= $p1` | 2-tuple |
    | `LIKE`   | `n.field =~ $p0` (regex) OR `n.field STARTS WITH $p0` per config | string |
    | `IS NULL`| `n.field IS NULL`           | none           |
  Property-name (`n.field`) is a static identifier — reuse the existing `validate_field` regex, then render as backticked: `` n.`field` ``. Do NOT parameterize property names (Cypher does not allow it).
  - `LIKE`: pick `STARTS WITH` (safer, indexable) as the default; regex `=~` available when `SourceConfig.like_style: "regex"` is set. User-controlled regex is an injection-adjacent concern — regex input from scope is a rule-author problem, not an agent problem, so acceptable.
- Use `driver.execute_query(...)` convenience (auto-managed read-transaction, retries for transient errors) rather than hand-rolled sessions for Phase 2.
- Auth: `auth=(user, pw)` from env, or `neo4j.basic_auth`, or `neo4j.bearer_auth`. TLS via `neo4j+s://` URI scheme.

#### Recommendation

`neo4j>=5` via `AsyncGraphDatabase.driver` + `driver.execute_query(..., routing_=READ)`. Validate `label` at `connect()`, build Cypher string from vetted templates keyed on operator, pass a dict of `$p0..$pN` parameters.

#### Template reuse?

~85%. Same lifecycle (`driver.close()` is `await`able and idempotent-ish — wrap with `_closed` flag for FR-17), same operator-dispatch loop, same `validate_field` usage, same `source_type` constant. Only the parameter-binding convention differs ($name dict vs $N positional list).

#### Risk

Cypher allows label-list MATCH (`MATCH (n:A:B)`) — useful for multi-label scoping but tempts multi-label injection. Mitigation: only one label per `SourceConfig.label`; no multi-label until Phase 3 if needed. Also: `=~` (regex LIKE) permits catastrophic-backtracking regex — default to `STARTS WITH` and require explicit config opt-in for regex.

---

### 4. ServiceNow adapter

#### Finding

- Library options (as of April 2026):
  - `pysnow` (rbw/pysnow) — stable but maintenance-only, no async. Not recommended for Phase 2.
  - `aiosnow` (rbw/aiosnow) — async, asyncio-native, successor to pysnow. Current version 0.6.0, active. Uses aiohttp internally (extra dep).
  - Direct `httpx.AsyncClient` against Table API (`/api/now/table/<table>?sysparm_query=...`) — zero extra deps beyond what REST adapter already needs.
- "ACL passthrough" clarification: ServiceNow enforces ACLs server-side based on the authenticated user. Nautilus layers scope on top by composing encoded queries — we do NOT disable ServiceNow's ACLs. Layering works because encoded-query filters are intersection (AND) with ACL-enforced row filtering; our scope constraints further narrow, never widen, the result set. No double-filter concern.
- `sysparm_query` encoded-query format:
  - AND: `^`; OR: `^OR`; expression format: `field<OP>value`.
  - Operator → encoded-query mapping:
    | Nautilus op | GlideRecord operator  | Example                     |
    |-------------|-----------------------|------------------------------|
    | `=`         | `=`                   | `priority=1`                |
    | `!=`        | `!=`                  | `priority!=1`               |
    | `IN`        | `IN`                  | `priority IN 1,2,3`         |
    | `NOT IN`    | `NOT IN`              | `priority NOT IN 1,2,3`     |
    | `<`         | `<`                   | `priority<3`                |
    | `>`         | `>`                   | `priority>3`                |
    | `<=`        | `<=`                  | `priority<=3`               |
    | `>=`        | `>=`                  | `priority>=3`               |
    | `BETWEEN`   | `BETWEEN`             | `created BETWEEN ...@...`   |
    | `LIKE`      | `LIKE`                | `short_description LIKE error` |
    | `IS NULL`   | `ISEMPTY`             | `short_descriptionISEMPTY`  |
- Security critical: ServiceNow encoded queries have a known injection vector — concatenating untrusted input allows attackers to inject `^OR` and widen the result set. Since scope values come from the Fathom router (not agent input directly), the risk surface is limited, but we still MUST:
  1. Validate values never contain `^`, newline, or `OR ` keyword.
  2. Use the Table API's query-parameter boundary (`sysparm_query=<value>` URL-encoded) — the HTTP client handles URL encoding; we handle the encoded-query syntax.
  3. Never interpolate scope values that contain `^`.
  Add a `_sanitize_sn_value(v) -> str` helper that rejects any input containing `^`, `\n`, `\r`. This is belt-and-braces on top of `validate_operator`.
- Table allowlist: `SourceConfig.table` regex `^[a-z][a-z0-9_]*$` (ServiceNow table naming).
- Auth: OAuth2 password-grant, basic, or instance-level token. In air-gap this means basic (username/password) or pre-fetched bearer. OAuth refresh flow needs an external IdP endpoint — incompatible with strict air-gap, so basic/bearer-via-env is the default.

#### Recommendation

Phase 2: `httpx.AsyncClient` direct against the Table REST API. Compose `sysparm_query` from the scope constraints via an `_encode_sn_query(scope)` helper with the sanitization above. Skip `aiosnow` for now (one fewer dep, keeps the adapter on a dep profile we already use for REST). Revisit if advanced features (attachment handling, batch ops) are demanded.

#### Template reuse?

~70%. Lifecycle + operator-dispatch + validate_field usage carry over; REST client plumbing shared with the REST adapter (both use `httpx.AsyncClient`); encoded-query assembly is net-new logic. Can literally subclass / compose the REST adapter's `_request` machinery.

#### Risk

Encoded-query syntax has the `^OR` injection foot-gun documented above — mitigated by sanitization + the fact that values originate from rule-authored scope, not agent text. If a future rule-pack hands through agent text as a scope value, the sanitization catches it.

---

### 5. FastAPI REST endpoint

#### Finding

- Model reuse: `nautilus/core/models.py` already defines `BrokerResponse` and everything it composes (`RoutingDecision`, `ScopeConstraint`, `ErrorRecord`, `IntentAnalysis`, `AuditEntry`) as pydantic v2 `BaseModel`s. FastAPI consumes these directly as `response_model=BrokerResponse`. The request body needs a new `BrokerRequest(BaseModel)` wrapping `(agent_id: str, intent: str, context: dict[str, Any] = {})` — 1 new model, 3 fields.
- `arequest` returning `BrokerResponse` fits FastAPI natively; no `run_in_executor` bridge, no `asyncio.run` — async handler calls `await broker.arequest(...)`. Aligns with design §8 ("`arequest` is safe to call from any event loop").
- Lifespan: FastAPI's `asynccontextmanager` lifespan param is the canonical home for `broker = Broker.from_config(path)` on startup and `await broker.aclose()` on shutdown. Construct in `lifespan()` and stash on `app.state.broker`; inject per-request via a `Depends(get_broker)` that reads `app.state.broker`. This keeps the broker a singleton across the ASGI worker.
- Auth (the brief's open question): recommended answer is **both tiers available, first-class API key is default**:
  - Default: `APIKeyHeader(name="X-API-Key", auto_error=True)` dependency. Keys loaded from `config.api.keys: list[str]` (env-interpolated) and compared with `secrets.compare_digest` (constant-time, standard FastAPI pattern).
  - Escape hatch: `config.api.auth.mode: "proxy_trust"` — require a header (e.g., `X-Forwarded-User`) set by the upstream reverse proxy and trust it (for deployments behind an auth gateway). Default off.
  - OAuth2 / OIDC deferred to operator-platform (requires an IdP which is incompatible with strict air-gap default).
- Air-gap friendliness: API key is local-only; no token introspection endpoint, no JWKS fetch. Matches core-broker posture.
- Endpoints:
  - `POST /v1/request` — body `BrokerRequest`, returns `BrokerResponse`.
  - `POST /v1/query` — (brief) — recommend this be an alias of `/v1/request` for now; otherwise defer until there's a semantic split. Document as "same request model, reserved for Phase 3 query-style semantics."
  - `GET /v1/sources` — list configured sources (metadata only, no secrets). Nice-to-have for operators.
  - `GET /healthz`, `GET /readyz` — needed for Docker-image `HEALTHCHECK` + k8s probes. `/readyz` returns 200 only after lifespan-startup completes.

#### Recommendation

FastAPI `>=0.115`, uvicorn `>=0.30` for serving. One module `nautilus/transport/rest.py` exporting `create_app(config_path) -> FastAPI`. Lifespan-based Broker singleton. `APIKeyHeader` + `secrets.compare_digest` default auth, `proxy_trust` escape hatch. No `run_in_executor` — `arequest` directly (confirmed viable per design §8).

#### Template reuse?

N/A (new subsystem). But the request/response models are already-shipped Pydantic v2 models — zero new DTO code for the 90% case. One new `BrokerRequest` model.

#### Risk

Single-broker-per-process model means a broken `Broker.from_config` kills the entire app at startup. Mitigation: lifespan raises → uvicorn exits non-zero → container orchestrator restarts. This is correct behavior, not a bug. For graceful degradation, `/readyz` stays 503 until `from_config` succeeds.

---

### 6. MCP tool server

#### Finding

- Library: official `mcp` Python SDK (`/modelcontextprotocol/python-sdk`), latest v1.12.4. Use `mcp.server.fastmcp.FastMCP` for the high-level decorator API.
- Transports supported: `stdio`, `sse` (legacy), `streamable-http` (recommended for production). Selected at `mcp.run(transport="...")` call. Streamable HTTP supports both stateful (session-managed) and stateless modes; stateless + `json_response=True` is the production-friendly combo.
- Tool schema: FastMCP auto-generates JSON schema from Python type hints. Pydantic `BaseModel` inputs and outputs are structured. One tool proposal:
  ```
  @mcp.tool()
  async def nautilus_request(
      agent_id: str,
      intent: str,
      context: dict[str, Any] = {},
      ctx: Context | None = None,
  ) -> BrokerResponse: ...
  ```
  Reuses `BrokerResponse` verbatim (it is a Pydantic v2 model → FastMCP gives it a structured-output schema automatically).
- Session mapping (brief question): MCP defines its own `ctx.request_id` and `ctx.client_id` (may be None) via `Context` injection. For Nautilus:
  - `agent_id` — always passed explicitly in the tool call arg (do NOT derive from MCP client_id; `agent_id` is a first-class security identity under our threat model).
  - `session_id` — if caller supplies it in `context` arg, use it; otherwise derive from MCP's transport session (streamable-http session id) or tool-call request id (stdio). Document this clearly; do NOT silently mint a session so cumulative-exposure tracking doesn't accidentally conflate unrelated callers.
- Auth: MCP itself has no auth layer at the protocol level (2026 roadmap mentions it). For streamable-http transport, the SDK mounts a Starlette sub-app — we can wrap it with the same `APIKeyHeader` middleware as the FastAPI surface. For stdio, auth is the parent process's responsibility (the invoking user already controls the subprocess).

#### Recommendation

Ship both stdio and streamable-http transports. CLI flag `nautilus serve --transport stdio|http [--bind 0.0.0.0:8766]`. `stateless_http=True, json_response=True` for HTTP. Single tool `nautilus.request` whose signature mirrors `Broker.arequest`. Reuse `BrokerResponse` as the return type (structured output, no custom schema).

#### Template reuse?

N/A (new subsystem). Under-the-hood call is `await broker.arequest(agent_id, intent, context)` — one line inside the tool handler.

#### Risk

MCP's session/identity story is still stabilizing (per 2026 roadmap post) — treat our `agent_id` as authoritative and ignore MCP's `client_id` until the protocol stabilizes a signed-identity claim. Document this in design so future versions can bind in an MCP-native identity without breaking callers.

---

### 7. Docker image

#### Finding

- Base-image options evaluated:
  | Option | Size (approx) | Python 3.14 | Air-gap | Notes |
  |--------|---------------|-------------|---------|-------|
  | `python:3.14-slim` (Debian-slim) | ~55 MB | yes | yes | Straightforward, full glibc, familiar. |
  | `python:3.14-alpine` | ~20 MB | yes | yes | musl — asyncpg/cryptography wheels may need `-alpine` variants; avoid. |
  | `gcr.io/distroless/cc-debian13` + copy-in venv | ~25 MB | yes (via venv) | yes | Smallest attack surface; requires multi-stage. |
  | `ghcr.io/astral-sh/uv:debian-slim` for builder, distroless for runtime | ~25 MB | yes | yes | `uv` already used for dep mgmt (`uv.lock` present). |
- Python 3.14 is GA in distroless-python images and in `uv` managed Python as of 2026. Satisfies `requires-python = ">=3.14"` in `pyproject.toml`.
- Multi-stage pattern (recommended):
  1. Stage `builder`: `ghcr.io/astral-sh/uv:python3.14-bookworm-slim` → `uv sync --frozen --no-dev` → produces `/app/.venv`.
  2. Stage `runtime`: `gcr.io/distroless/cc-debian13` → `COPY --from=builder /app/.venv /app/.venv` → `COPY nautilus /app/nautilus` → `ENV PYTHONPATH=/app PATH=/app/.venv/bin:$PATH` → `ENTRYPOINT ["/app/.venv/bin/python", "-m", "nautilus"]` → `CMD ["serve", "--config", "/config/nautilus.yaml"]`.
- Mount points: `/config/nautilus.yaml` (read-only), `/rules` (read-only, user rules dir), `/audit` (read-write, audit.jsonl), `/keys` (read-only, attestation private key if configured). All surface in `NautilusConfig` as absolute paths; documented in the image's `README`.
- Entry point: `nautilus serve` CLI does NOT exist yet. Confirmed by grep of `nautilus/` — no `__main__.py`, no `cli/`. Add to spec scope: new `nautilus/cli.py` implementing at minimum `serve` (launches REST/MCP from config) and `version`. Use `argparse` — avoids adding Click/Typer for air-gap dep minimalism.
- Image size budget: ~120 MB target (distroless ~25 + venv ~90). `python:3.14-slim` direct would be ~200 MB. Preference: distroless.
- Air-gap: no `RUN pip install` at runtime; all deps baked at build. No `apt-get install` at runtime. `HEALTHCHECK CMD` can shell out to `curl -f http://localhost:8000/readyz || exit 1` — but distroless has no curl. Options: (a) use `python -c "import urllib.request; urllib.request.urlopen(...)"`; (b) ship a tiny built-in `nautilus health` subcommand. Prefer (b) — no shell dependency, fully self-contained.

#### Recommendation

Multi-stage: `ghcr.io/astral-sh/uv:python3.14-bookworm-slim` (builder) → `gcr.io/distroless/cc-debian13` (runtime). Entry point `nautilus serve --config /config/nautilus.yaml`. New `nautilus/cli.py` using stdlib `argparse`. `HEALTHCHECK CMD ["/app/.venv/bin/python", "-m", "nautilus", "health"]`. Size target ~120 MB.

#### Template reuse?

N/A (net-new).

#### Risk

Distroless has no shell, no package manager, no debugger — harder to poke inside a running container. Mitigation: ship a `-debug` image tag variant based on `python:3.14-slim` with `bash` for ops use; default deployment uses distroless.

---

### 8. Attestation service dispatch

#### Finding

- Current state: `nautilus.core.broker.Broker._sign` produces a signed JWT via Fathom's `AttestationService`. Token is attached to `BrokerResponse.attestation_token` and written into `AuditEntry.attestation_token` — full round-trip in-process but never dispatched anywhere.
- "Integration" options:
  1. Fire-and-forget HTTP POST after signing: blocks broker latency, risks tail-latency cascade on verifier outage.
  2. Background task (asyncio): non-blocking, but loses the signal when the process dies (air-gap: not acceptable for audit).
  3. Store-and-forward via a durable queue (file-based JSONL, Postgres table, Redis stream): crash-safe, retries possible, decouples broker hot path from network. This matches how the existing `AuditSink` interface works — append to a sink, let something else consume it.
- Air-gap reality: verifier may be unreachable for extended windows. Store-and-forward is the only correct answer for air-gap.
- Symmetry with `AuditSink` — the cleanest design:
  ```
  class AttestationSink(Protocol):
      async def emit(self, payload: AttestationPayload) -> None: ...
      async def close(self) -> None: ...
  ```
  Shipped implementations:
  - `NullAttestationSink` — default when no verifier configured (current behavior; token still signed + returned).
  - `FileAttestationSink(path)` — append-only JSONL queue; a sidecar / cron job can drain it.
  - `HttpAttestationSink(url, retry_policy)` — best-effort POST; on failure falls through to a wrapped `FileAttestationSink` (dead-letter). Useful for mostly-connected deployments.
- Broker integration: after `self._sign(...)` completes in `_run_pipeline`, if a sink is configured call `await sink.emit(payload)`. Swallow and log exceptions — never let verifier-dispatch failure mask a successful request (audit-first ordering preserved from Phase 1). `Broker.aclose` should `await sink.close()`.
- Payload: reuse `build_payload(...)` from `nautilus/core/attestation_payload.py` — already emits the deterministic (`request_id`, `agent_id`, `sources_queried`, `scope_hash`, `rule_trace_hash`) structure §9.3 defines. Wrap as `AttestationPayload(token: str, nautilus_payload: dict, emitted_at: datetime)`.

#### Recommendation

Add `AttestationSink` Protocol in `nautilus/audit/attestation_sink.py` (or `nautilus/core/attestation_sink.py`) with three implementations (`Null`, `File`, `Http`). Wire through `NautilusConfig.attestation.sink` config block. Broker calls `sink.emit(...)` post-sign. Default for air-gap: `FileAttestationSink(path=/audit/attestation.jsonl)`.

#### Template reuse?

~95% follows the `AuditSink`/`AuditLogger` template from Phase 1 — same Protocol shape, same lifecycle, same file-sink semantics. Minimal new design surface.

#### Risk

An unbounded `FileAttestationSink` queue grows forever if no drainer runs. Mitigation: document retention/rotation as an operator concern (same posture as `audit.jsonl`). Add an optional `max_bytes` config key for Phase 3 if it matters.

---

### Cross-cutting notes (stream B)

- **Zero changes to `Adapter` Protocol.** All four new adapters implement `source_type`, `connect`, `execute`, `close` unchanged. The `_OPERATOR_ALLOWLIST` remains the single source of truth — no adapter adds or removes operators.
- **Zero changes to `validate_field` / `validate_operator`.** Every new adapter either reuses them verbatim (Neo4j, ES with label/index identifier validation piggy-backing on the regex with minor char-set relaxation per-source) or adds a belt-and-braces sanitizer on top (ServiceNow `^`-rejection).
- **Dependency additions (all maintained, popular, BSD/MIT/Apache):**
  - `elasticsearch>=8` (Apache-2.0)
  - `neo4j>=5` (Apache-2.0)
  - `httpx>=0.27` (BSD-3)
  - `fastapi>=0.115` (MIT)
  - `uvicorn[standard]>=0.30` (BSD-3)
  - `mcp>=1.12` (MIT)
  No `pysnow`/`aiosnow` — ServiceNow goes through `httpx`.
- **New SourceConfig fields (additive, non-breaking):**
  - `index: str | None` (ES)
  - `label: str | None` (Neo4j)
  - `endpoints: list[EndpointSpec] | None` (REST)
  - `auth: AuthConfig | None` (REST, ServiceNow)
  - Existing `table: str | None` continues to serve Postgres, pgvector, ServiceNow.
- **Transport endpoint list (confirmed):**
  - `POST /v1/request` (FastAPI), `POST /v1/query` (alias for now), `GET /v1/sources`, `GET /healthz`, `GET /readyz`.
  - MCP tool: `nautilus.request`.
- **CLI:** new `nautilus/cli.py` with `serve --transport rest|mcp|both --config PATH`, `health`, `version`. Add to spec scope (confirmed absent today).

---

## Resolved Open Questions

Each brief question with the answer derived from the streams:

1. **Shared session store for cross-agent tracking: in-process, Redis, or Postgres?** — **Postgres** (stream A §2). Already ship `asyncpg>=0.30.0` and `PostgresAdapter`; same air-gap story, same env-var/DSN pattern. Redis rejected: adds a second stateful process with no corresponding benefit. `InMemorySessionStore` remains the default; `PostgresSessionStore` opt-in via config. Schema mirrors `fathom/fleet_pg.py` layout but does not import `FactStore` itself.
2. **LLM provider abstraction: pluggable interface or concrete Anthropic/OpenAI/local-inference options?** — **Pluggable interface + all three concrete options** (stream A §5). Ship `LLMIntentProvider` Protocol plus `AnthropicProvider`, `OpenAIProvider`, `LocalInferenceProvider`. Pattern-matching remains the Phase-1 default and the air-gap-forced mode.
3. **REST API authentication: assume upstream reverse proxy, or first-class API key support?** — **First-class API key by default, `proxy_trust` mode as escape hatch** (stream B §5). `APIKeyHeader(name="X-API-Key")` + `secrets.compare_digest`. `config.api.auth.mode: "proxy_trust"` supports deployments behind an auth gateway. OAuth2/OIDC deferred to operator-platform.
4. **MCP server: stdio-only or stdio+HTTP?** — **Both stdio and streamable-http** (stream B §6). CLI flag `nautilus serve --transport stdio|http [--bind ...]`. `stateless_http=True, json_response=True` for HTTP. HTTP transport wraps the Starlette sub-app with the same `APIKeyHeader` middleware as the REST surface.

No brief questions are punted — all four are settled.

---

## New Open Questions for Requirements Phase

1. **Per-level compartments in `HierarchyDefinition`** — is a two-hierarchy workaround acceptable, or should we land a Fathom extension (small but upstream)? (Stream A §1)
2. **`PostgresSessionStore` schema migration** — does Nautilus own `CREATE TABLE` DDL (new `Broker.setup()` pattern), or do we document the SQL and require operators to provision? Phase 1 has no DDL today. (Stream A §2)
3. **Cross-agent handoff detection cooperative vs. forensic** — is there a requirement that Nautilus detect handoffs an orchestrator didn't declare? If yes, the audit-stream correlation model needs research (out of scope here). (Stream A §3)
4. **LLM determinism audit fields** — is it acceptable to add `llm_provider` / `llm_model` / `raw_response_hash` to `AuditEntry` and break Phase-1 audit-line compatibility? Or do these go into a separate `intent_analysis_trace` sidecar? (Stream A §5)
5. **Scope expiry hash versioning** — freeze `scope_hash_v1` and land new fields as `scope_hash_v2`, or extend v1 hash and accept the bump? This interacts with the new `AttestationSink` dispatch (stream B §8) because any verifier consuming dispatched payloads must know the hash version. (Stream A §6 + Stream B §8)
6. **`/v1/query` endpoint semantics** — does Phase 2 ship it as a literal alias of `/v1/request`, or hold the path reserved until Phase 3 defines a query-style split? (Stream B §5)
7. **MCP session identity binding** — do we derive `session_id` from MCP's transport session id (streamable-http) / request id (stdio) as a fallback, or REQUIRE the caller to always pass `session_id` explicitly in `context`? (Stream B §6)
8. **Docker debug image publication** — do we publish the `-debug` (python-slim + bash) tag as a first-class release artifact, or leave it as an operator-local build recipe? (Stream B §7)

---

## Scope Additions Beyond Brief

Items the streams identified as net-new, not explicitly enumerated in `brief.md`:

1. **`nautilus/cli.py`** (stream B §7, §6) — new module implementing `nautilus serve --transport rest|mcp|both --config PATH`, `nautilus health`, `nautilus version`. Confirmed absent from `nautilus/` today. Required so the Docker image has a bootable entrypoint and the MCP server has a CLI flag for transport selection. Use stdlib `argparse` to avoid a Click/Typer dep for air-gap minimalism.
2. **`AttestationSink` Protocol + three implementations** (stream B §8) — brief:54 says "extend PyJWT Ed25519 signing to publish to an external verifier", but the store-and-forward design (Null/File/Http sinks) is a genuinely new Nautilus subsystem mirroring `AuditSink`. Not a reshape of existing signing code.
3. **Agent registry (`agents:` top-level in `nautilus.yaml`)** (stream A §3) — brief does not call out an agent registry; it is a prerequisite for cross-agent handoff detection so `declare_handoff` can look up the receiving agent's clearance without forcing callers to repeat it.
4. **`Broker.declare_handoff(...)` public API** (stream A §3) — brief lists "cross-agent information flow tracking" as a capability but not as an API surface. Streams concluded a new public method is required.
5. **`Broker.setup()` DDL bootstrap** (stream A §2) — if Postgres session-store is used, Nautilus must run `CREATE TABLE IF NOT EXISTS` on first use. Phase 1 owns no DDL, so this is a new responsibility.
6. **`session_exposure` fact template + richer `session` template** (stream A §2) — multi-slot `data_types_seen`, `sources_visited`, `pii_sources_accessed_list`, plus a derived `session_exposure` template asserted per multiset element during `route()`.
7. **`escalation_rule` template + `contains-all` external** (stream A §4) — new Nautilus-local fact template and CLIPS external function; parallel to existing `overlaps` / `not-in-list` precedent.
8. **`data_handoff` fact template** (stream A §3) — new Fathom template asserted by `declare_handoff`.
9. **Drift-guard tests** (stream B §1, §2) — explicit tests asserting that operator → DSL / query-param translations cover the full `_OPERATOR_ALLOWLIST` and fail loud on missed ops. Not called out by brief but consistent with Phase 1's "operator allowlist drift test" gate (brief:71).

---

## Cross-Stream Coordination Points

Places where stream A and stream B interact and must be resolved together:

1. **Temporal scoping's `expires_at` / `valid_from` slots affect `scope_hash` canonicalization.**
   Stream A §6 adds two optional slots to the `scope_constraint` template. Stream B §8 dispatches attestation payloads (via `AttestationSink`) that include a `scope_hash` computed by `nautilus/core/attestation_payload.py`. If the new slots land in the hash, every Phase-1 verifier breaks; if they are excluded, the attestation underrepresents the actual scope enforced. Resolution path: version the hash (`scope_hash_v2`) and include a hash-version discriminator in `AttestationPayload`. Requirements phase must pick v1-frozen vs v1-extended — see new open question 5.

2. **LLM analyzer failures must be observable in the audit log.**
   Stream A §5 requires audit provenance fields (`llm_provider`, `llm_model`, `llm_version`, `raw_response_hash`) so non-deterministic LLM behavior can be reconstructed. Stream B §8 is the subsystem that dispatches the resulting signed attestation. Coordination: either the audit-record canonicalization absorbs these fields (breaking Phase-1 line compatibility) or they live in an `intent_analysis_trace` sidecar that the `AttestationSink` picks up alongside the primary payload. Requirements phase must pick — see new open question 4.

3. **Session store in Postgres needs a migration strategy that reuses Phase 1's connection-pool conventions.**
   Stream A §2 proposes `PostgresSessionStore` + a `Broker.setup()` bootstrap running `CREATE TABLE IF NOT EXISTS`. Stream B's adapter template (the Phase 1 `PostgresAdapter` model — `asyncpg` pool, `${ENV_VAR}` DSN interpolation, `.close()` idempotency) is the canonical template that `PostgresSessionStore` must follow: same pool lifecycle, same env-var interpolation in `NautilusConfig`, same `_closed` flag pattern for idempotent shutdown. If stream A's session store and the Phase 2 REST adapter (`httpx.AsyncClient`) live side-by-side, both must register into `Broker.aclose()` in a deterministic order so session-store flush happens before adapter teardown.

4. **`AttestationSink` + LLM provenance + scope-hash versioning form a single audit-surface package.**
   All three sit on the same attestation payload; changes to any one ripple into the others. Recommend requirements phase treat them as one coherent design unit rather than three independent decisions.

5. **Transport surfaces (REST, MCP) must not bypass session-store or handoff enforcement.**
   Stream B §5 (FastAPI) and §6 (MCP) both call `await broker.arequest(...)` directly — no bypass. But stream A §3's `Broker.declare_handoff(...)` has no transport surface in stream B; requirements phase must decide whether to expose it as `POST /v1/handoff` + an MCP tool `nautilus.declare_handoff`, or keep it library-only.

---

## Sources

### Stream A (reasoning)

- `C:/Projects/project-fathom/fathom/src/fathom/engine.py` — externals registration (lines 80-412), hierarchy registry (170, 583)
- `C:/Projects/project-fathom/fathom/src/fathom/models.py` — `HierarchyDefinition` (342), `FunctionDefinition.hierarchy_ref` (326)
- `C:/Projects/project-fathom/fathom/src/fathom/facts.py` — `FactManager.set_ttl` (41), `cleanup_expired` (166), `clear_all` (149)
- `C:/Projects/project-fathom/fathom/src/fathom/fleet.py` — `FactStore` Protocol (20-46)
- `C:/Projects/project-fathom/fathom/src/fathom/fleet_pg.py` — Postgres JSONB reference schema (37-69)
- `C:/Projects/project-fathom/fathom/src/fathom/fleet_redis.py` — Redis tradeoffs (1-60)
- `C:/Projects/project-fathom/fathom/tests/test_classification_integration.py` — end-to-end `fathom-dominates` usage example
- `C:/Projects/project-fathom/fathom/tests/fixtures/hierarchies/classification.yaml` — hierarchy YAML shape
- `C:/Projects/project-fathom/nautilus/nautilus/core/broker.py` — Phase 1 pipeline (`_run_pipeline`, `_route`, `_update_session`, `_sign`)
- `C:/Projects/project-fathom/nautilus/nautilus/core/fathom_router.py` — current fact assertion (100-128), template readback (132-165)
- `C:/Projects/project-fathom/nautilus/nautilus/core/session.py` — `SessionStore` Protocol + Phase-1 in-memory impl
- `C:/Projects/project-fathom/nautilus/nautilus/rules/templates/nautilus.yaml` — current template shape
- `C:/Projects/project-fathom/nautilus/nautilus/rules/rules/routing.yaml`, `denial.yaml` — current rule patterns
- `C:/Projects/project-fathom/nautilus/nautilus/analysis/base.py`, `pattern_matching.py` — `IntentAnalyzer` Protocol + default impl
- `C:/Projects/project-fathom/nautilus/design.md` — §Classification Hierarchy, §Cumulative Exposure Tracking, §Deployment Models
- `C:/Projects/project-fathom/nautilus/pyproject.toml` — confirms `fathom-rules>=0.3.0` + `asyncpg>=0.30.0` already present

### Stream B (adapters + transport)

- `/elastic/elasticsearch-py` — AsyncElasticsearch, elasticsearch.dsl, basic_auth, ca_certs, ssl_assert_fingerprint. [elasticsearch-py docs](https://github.com/elastic/elasticsearch-py/blob/main/docs/reference/connecting.md), [DSL how-to](https://github.com/elastic/elasticsearch-py/blob/main/docs/reference/dsl_how_to_guides.md)
- [Elasticsearch Query DSL reference](https://www.elastic.co/docs/explore-analyze/query-filter/languages/querydsl)
- `/neo4j/neo4j-python-driver` — AsyncDriver, AsyncSession, `execute_query`, parameterized Cypher. [neo4j-python-driver async_api docs](https://github.com/neo4j/neo4j-python-driver/blob/6.x/docs/source/async_api.md)
- `/modelcontextprotocol/python-sdk` — FastMCP, streamable-http transport, structured output with Pydantic. [python-sdk README](https://github.com/modelcontextprotocol/python-sdk/blob/main/README.md)
- [MCP 2026 transport roadmap](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/), [MCP transports spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- `/fastapi/fastapi` — lifespan asynccontextmanager, APIKeyHeader, security tools. [FastAPI events](https://github.com/fastapi/fastapi/blob/master/docs/en/docs/advanced/events.md), [security tools](https://github.com/fastapi/fastapi/blob/master/docs/en/docs/reference/security/index.md)
- `/encode/httpx` — AsyncClient, Timeout, base_url, mTLS via cert=, context manager lifecycle. [httpx API](https://github.com/encode/httpx/blob/master/docs/api.md), [httpx timeouts](https://github.com/encode/httpx/blob/master/docs/advanced/timeouts.md)
- [aiosnow README](https://github.com/rbw/aiosnow), [pysnow status](https://github.com/rbw/pysnow)
- [snowcoder: 10 common ServiceNow script vulns (sysparm_query injection)](https://snowcoder.ai/blog/servicenow-security-vulnerabilities)
- [distroless-python 3.14 images](https://github.com/alexdmoss/distroless-python), [uv in Docker guide](https://docs.astral.sh/uv/guides/integration/docker/), [pythonspeed Feb 2026 base image guide](https://pythonspeed.com/articles/base-image-python-docker-images/)
- Internal: `nautilus/adapters/base.py`, `nautilus/adapters/postgres.py`, `nautilus/core/broker.py`, `nautilus/core/models.py`, `nautilus/core/attestation_payload.py`, `specs/core-broker/design.md` §6–§10.
