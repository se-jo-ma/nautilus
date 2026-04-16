---
spec: core-broker
phase: research
created: 2026-04-14
---

# Research: core-broker

## Executive Summary

Nautilus is feasible to build on top of the Fathom rules engine. Fathom provides templates, fact assertion, forward-chaining evaluation, and a `route` action type -- exactly what Nautilus needs for source selection. The main architectural challenge is that Fathom's `EvaluationResult` uses last-write-wins for the `decision` field, so Nautilus must capture ALL `__fathom_decision` facts (via `rule_trace` parsing or direct CLIPS access) to build a complete routing table per request. The project starts from near-zero (empty `main.py`, single dependency), so all components are greenfield.

## Fathom-Rules API Findings

### Package Structure

Source: `C:\Projects\project-fathom\nautilus\.venv\Lib\site-packages\fathom\`

| Module | Purpose |
|--------|---------|
| `engine.py` | Core `Engine` class -- CLIPS environment wrapper |
| `models.py` | Pydantic models for templates, rules, modules, facts, results |
| `compiler.py` | YAML-to-CLIPS compilation |
| `evaluator.py` | Forward-chain evaluation, decision extraction |
| `facts.py` | `FactManager` -- validation, assertion, query, retraction |
| `attestation.py` | Ed25519 JWT signing/verification |
| `audit.py` | `AuditSink` protocol, `FileSink`, `NullSink`, `AuditLog` |
| `packs.py` | Rule pack discovery via entry points |
| `yaml_utils.py` | YAML validation helpers |

### Engine Lifecycle

```python
from fathom import Engine

# 1. Create engine (fail-closed by default)
engine = Engine(default_decision="deny")

# 2. Load rules from directory (templates -> modules -> functions -> rules)
engine = Engine.from_rules("path/to/rules/")

# Or load individually:
engine.load_templates("templates/")
engine.load_modules("modules/")
engine.load_functions("functions/")
engine.load_rules("rules/")

# Or load a rule pack:
engine.load_pack("owasp-agentic")

# 3. Assert facts into working memory
engine.assert_fact("template_name", {"slot1": "value1", "slot2": "value2"})
engine.assert_facts([("tmpl1", {...}), ("tmpl2", {...})])  # atomic batch

# 4. Evaluate (fires rules, returns result)
result = engine.evaluate()
# result.decision: str | None  (last-write-wins: "allow", "deny", "route", "scope", "escalate")
# result.reason: str | None
# result.rule_trace: list[str]  (ALL rules that fired, e.g. ["MAIN::route-nvd_db", "MAIN::skip-hr"])
# result.module_trace: list[str]
# result.duration_us: int
# result.attestation_token: str | None
# result.metadata: dict[str, str]

# 5. Query/manage working memory
facts = engine.query("template_name", {"slot": "filter_value"})
count = engine.count("template_name")
engine.retract("template_name", {"slot": "filter_value"})
engine.clear_facts()  # retract all user facts
engine.reset()  # full CLIPS reset
```

### Template Definition (YAML)

```yaml
templates:
  - name: tool_call
    slots:
      - name: tool_name
        type: symbol        # string | symbol | float | integer
        required: true
      - name: agent_id
        type: string
        required: true
      - name: arguments
        type: string
        default: ""
```

### Rule Definition (YAML)

```yaml
module: owasp              # must reference a loaded module
ruleset: owasp-agentic
version: "1.0"
rules:
  - name: deny-exec
    salience: 100           # higher = fires first
    when:
      - template: tool_call
        conditions:
          - slot: tool_name
            expression: "in([exec, shell, eval])"
    then:
      action: deny          # allow | deny | escalate | scope | route
      reason: "Dangerous tool"
      log: full             # none | summary | full
      attestation: true
```

### Decision Actions

| Action | Symbol | Use in Nautilus |
|--------|--------|-----------------|
| `allow` | General permit | Not primary for routing |
| `deny` | Block access | Source denied due to policy |
| `escalate` | Flag for review | Cumulative exposure threshold |
| `scope` | Apply constraints | WHERE clause restrictions |
| `route` | Select target | **Primary** -- select source for query |

### Critical Finding: Multi-Decision Handling

Fathom's `EvaluationResult.decision` is **last-write-wins** (the last `__fathom_decision` fact asserted). However, `rule_trace` captures ALL fired rules in order.

**Verified behavior:** When 3 sources match, 3 separate `route` rules fire, `rule_trace` contains all 3 rule names, but `decision` only reflects the last one.

**Nautilus strategy options:**

1. **Parse rule_trace + metadata** -- encode source IDs in rule names/metadata, reconstruct routing table from trace. Simple but fragile.
2. **Custom evaluator** -- subclass or wrap `Evaluator` to capture all `__fathom_decision` facts before cleanup. More robust.
3. **Separate fact template for routing** -- instead of using `__fathom_decision` for routing, have rules assert facts into a custom `routing_decision` template, then query it after evaluation. **Recommended** -- cleanest separation.

**Recommended approach:** Option 3. Define a `routing_decision` template. Routing rules assert facts into it. After `engine.evaluate()`, query `routing_decision` to get the full routing table. This uses Fathom's public API and avoids coupling to internal evaluator behavior.

### Built-in External Functions

Available in CLIPS rule conditions:
- `fathom-matches(str, pattern)` -- regex search
- `fathom-count-exceeds(template, slot, value, threshold)` -- count matching facts
- `fathom-rate-exceeds(template, slot, value, threshold, window, ts_slot)` -- rate limiting
- `fathom-dominates(level_a, comps_a, level_b, comps_b, hierarchy)` -- Bell-LaPadula clearance check
- `fathom-has-compartment(subject_comps, required_comp)` -- compartment membership
- `fathom-compartments-superset(subject_comps, required_comps)` -- compartment dominance
- `fathom-distinct-count(template, group_slot, count_slot, threshold)` -- cardinality check
- `fathom-sequence-detected(events_json, window_seconds)` -- ordered event pattern

### Attestation Service

```python
from fathom.attestation import AttestationService, verify_token

svc = AttestationService.generate_keypair()
engine = Engine(attestation_service=svc)
# ... assert facts, evaluate ...
result = engine.evaluate()
print(result.attestation_token)  # JWT signed with Ed25519

# Verify
payload = verify_token(result.attestation_token, svc.public_key)
```

### Audit System

```python
from fathom.audit import FileSink, AuditLog
sink = FileSink("audit.jsonl")
engine = Engine(audit_sink=sink)
# Evaluations auto-logged as JSON Lines with timestamp, session_id, rules_fired, decision
```

## Codebase Analysis

### Current State

| File | Content |
|------|---------|
| `main.py` | Placeholder `print("Hello from nautilus!")` |
| `pyproject.toml` | Project config, single dep: `fathom-rules>=0.1.0` |
| `design.md` | Complete architecture design (580 lines) |
| `CLAUDE.md` | Empty |
| `README.md` | Exists (unread) |
| `docs/_index.md` | Exists |

**No source code exists yet.** Everything is greenfield.

### Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `fathom-rules` | 0.1.0 | Core reasoning engine |
| `clipspy` | (transitive) | CLIPS bindings |
| `pydantic` | (transitive via fathom) | Data validation |
| `PyYAML` | (transitive via fathom) | YAML parsing |
| `PyJWT` | (transitive via fathom) | JWT attestation tokens |
| `cryptography` | (transitive via fathom) | Ed25519 keys |

### New Dependencies Needed

| Package | Purpose | Why |
|---------|---------|-----|
| `asyncpg` | PostgreSQL async driver | Connection pooling, parameterized queries |
| `pgvector` | pgvector extension support | Vector similarity search |
| `pytest` + `pytest-asyncio` | Testing | Async test support |

## Architectural Recommendations

### 1. Use Custom Routing Facts Instead of __fathom_decision

Define Nautilus-specific templates (`routing_decision`, `scope_constraint`, `denial_record`) that routing rules assert into. After evaluation, query these templates for the complete routing table. This decouples Nautilus from Fathom's internal decision mechanism.

### 2. Sync-First, Async Adapters

The Fathom engine is synchronous (CLIPS is single-threaded). Design:
- `Broker.request()` -- sync public API (wraps async internally if needed)
- Adapters use `asyncpg` pools for PostgreSQL/pgvector
- Fan-out queries via `asyncio.gather()` for concurrent multi-source execution
- Keep Fathom reasoning on the main thread (fast -- 15us per evaluation)

### 3. Pydantic Models for Everything

Fathom already uses Pydantic. Nautilus should follow the same pattern:
- `SourceConfig` -- YAML source registry validation
- `IntentAnalysis` -- parsed intent metadata
- `RoutingDecision` -- per-source routing result
- `BrokerResponse` -- final response to agent
- `AuditEntry` -- audit log records

### 4. YAML Config with Environment Variable Interpolation

Load `nautilus.yaml` via `yaml.safe_load()`, then Pydantic-validate. Support `${ENV_VAR}` interpolation for connection strings (matching design.md pattern). Fail fast on missing required env vars.

### 5. Intent Analyzer as Strategy Pattern

Phase 1 uses pattern-matching. Phase 3 adds LLM-based. Design as a protocol:
```python
class IntentAnalyzer(Protocol):
    def analyze(self, intent: str, context: dict) -> IntentAnalysis: ...
```

### 6. Adapter Base Class

```python
class BaseAdapter(ABC):
    source_type: str
    async def connect(self, config: SourceConfig) -> None: ...
    async def execute(self, query_intent: IntentAnalysis, scope: ScopeConstraints) -> AdapterResult: ...
    async def close(self) -> None: ...
```

### 7. PostgreSQL Scope Enforcement

Use parameterized queries exclusively (asyncpg uses server-side prepared statements, immune to SQL injection by design). Build WHERE clauses programmatically using parameter placeholders (`$1`, `$2`). Never interpolate values into SQL strings.

### 8. pgvector Metadata Filtering

pgvector similarity search with metadata filtering:
```sql
SELECT * FROM embeddings
WHERE metadata->>'classification' = $1
ORDER BY embedding <=> $2
LIMIT $3
```
Scope enforcement via WHERE clause on metadata JSONB column before vector similarity.

## Quality Commands

| Type | Command | Source |
|------|---------|--------|
| Lint | Not found | No linting configured yet |
| TypeCheck | Not found | No type checker configured |
| Unit Test | Not found | No test framework configured |
| Build | Not found | No build scripts |

**Note:** Testing infrastructure must be set up as part of Phase 1. Recommend: `pytest` + `pytest-asyncio` + `pytest-cov`. Consider adding `ruff` for linting and type checking.

## Verification Tooling

No automated E2E tooling detected. This is a library/SDK project.

**Project Type**: Library / SDK
**Verification Strategy**: Build and verify import, run unit/integration tests against PostgreSQL/pgvector test containers.

## Feasibility Assessment

| Aspect | Assessment | Notes |
|--------|------------|-------|
| Technical Viability | **High** | Fathom API is well-designed, `route`/`scope` actions exist, templates are flexible |
| Effort Estimate | **L** | ~9 components to build, but most are straightforward given Fathom's foundation |
| Risk Level | **Medium** | Multi-decision handling requires custom routing fact pattern; async/sync bridge needs care |

### Key Risks

1. **Multi-decision extraction** -- Fathom's last-write-wins model doesn't natively support "route to N sources". Mitigated by custom routing templates.
2. **CLIPS string limitations** -- JSON in CLIPS metadata slots requires careful escaping. Verified that complex JSON in metadata can be lossy. Use separate fact slots instead of JSON-in-metadata.
3. **Async/sync boundary** -- Fathom engine is sync, adapters should be async. Need `asyncio.run()` or event loop management.
4. **pgvector dependency** -- Requires PostgreSQL with pgvector extension installed for integration testing.

## Related Specs

No other specs found in the project. `core-broker` is the first and only spec.

## Open Questions

1. **Should the Broker API be sync or async?** Design.md shows `broker.request()` as sync. But adapters need async for concurrent queries. Options: (a) sync API wrapping async internals, (b) dual sync/async API, (c) async-first with `asyncio.run()` convenience wrapper.
2. **Session state storage** -- For cumulative exposure tracking (Phase 2), where does session state persist between requests? In-memory dict for Phase 1, Redis/Postgres for Phase 2?
3. **Rule pack or inline rules?** -- Should Nautilus routing rules ship as a Fathom rule pack (entry point discovery) or be loaded inline from the nautilus.yaml config?
4. **Test database strategy** -- Use testcontainers for PostgreSQL/pgvector integration tests, or mock the database layer?

## Recommendations for Requirements

1. **Start with sync Broker API**, async adapters internally. Matches design.md examples. Add async Broker in Phase 2.
2. **Define custom Fathom templates** for routing decisions -- don't rely on `__fathom_decision` for multi-source routing.
3. **Use Pydantic for all config/data models** -- already a transitive dependency via Fathom.
4. **Pattern-matching intent analyzer** should use keyword extraction + configurable intent templates (YAML).
5. **PostgreSQL adapter** should use `asyncpg` with connection pooling and parameterized queries only.
6. **pgvector adapter** extends PostgreSQL adapter, adds similarity search with metadata WHERE filters.
7. **Audit log** should use Fathom's `AuditSink` protocol for consistency, with a Nautilus-specific `AuditRecord` model.
8. **Test suite**: pytest + pytest-asyncio. Unit tests for each component. Integration tests for adapters (can use mocks initially, testcontainers later).
9. **Project structure**: `nautilus/` package with subpackages: `core/`, `adapters/`, `analysis/`, `config/`.

## Sources

- Fathom-rules 0.1.0 installed package source code (`C:\Projects\project-fathom\nautilus\.venv\Lib\site-packages\fathom\`)
- Nautilus design document (`C:\Projects\project-fathom\nautilus\design.md`)
- [Mediator Pattern in Python -- Refactoring.Guru](https://refactoring.guru/design-patterns/mediator/python/example)
- [asyncpg Documentation](https://magicstack.github.io/asyncpg/current/usage.html)
- [pgvector -- Vector Similarity Search for Postgres](https://github.com/pgvector/pgvector)
- [Pydantic Settings Management](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [Pydantic YAML Config Best Practices](https://github.com/pydantic/pydantic-settings/issues/185)
- [Semantic Search with Filters using pgvector -- Timescale](https://medium.com/timescale/what-is-semantic-search-with-filters-and-how-to-implement-it-with-pgvector-and-python-bec9cf827e69)
- [CLIPSpy Documentation](https://clipspy.readthedocs.io/)
- [Preventing SQL Injection -- Real Python](https://realpython.com/prevent-python-sql-injection/)
- [Psycopg3 Parameterized Queries](https://www.psycopg.org/psycopg3/docs/basic/params.html)
