# Research: design-mk2

## Executive Summary

Nautilus is a privacy/compliance reasoning engine acting as broker between AI agents and data sources. The design docs (§01-§05) describe a multi-phase system spanning core brokerage, retentive knowledge, and operator tooling. Two specs are complete (core-broker: 59/59 tasks, reasoning-engine: 79/79 tasks) delivering the foundational broker, 6 adapters, LLM intent analysis, REST+MCP transports, CLI, Docker, forensics, and 147+ tests. The major remaining work falls into three areas: (1) Retentive Knowledge Model (meta-rules, LLM knowledge engineer, expert networks, validation pipeline), (2) Operator Platform (admin UI, rule packs, observability, compliance reporting), and (3) cross-cutting gaps (agent identity, audit integrity, schema drift, result transformation).

## What's Already Built

### core-broker (Phase 1) — 59/59 tasks COMPLETE
- Sync Python SDK (`Broker.from_config()`, `broker.request()`)
- Fathom CLIPS rules engine with custom templates (routing_decision, scope_constraint, denial_record)
- Pattern-matching intent analyzer (deterministic, air-gap-capable)
- PostgreSQL + pgvector adapters
- Append-only audit log (Fathom AuditSink)
- Ed25519 attestation tokens
- Session store protocol (in-memory backend)
- 145 tests, 90.29% branch coverage

### reasoning-engine (Phase 2+3) — 79/79 tasks COMPLETE
- Classification hierarchy + cumulative exposure tracking
- PostgresSessionStore (async + fallback degradation)
- Cross-agent info-flow detection + escalation rules + temporal scoping
- LLM intent analysis: Anthropic, OpenAI, local providers + FallbackIntentAnalyzer
- 4 new adapters: Elasticsearch, REST, Neo4j, ServiceNow
- FastAPI REST transport + MCP tool server
- CLI (serve/health/version) + multi-stage Dockerfile (distroless)
- AttestationSink Protocol (Null/File/Http) + scope_hash_v2
- Forensic handoff worker + offset tracking
- 147 total tests across 83 files

### operator-platform — BRIEF ONLY (not started)
- Brief exists with scope + open questions
- Planned: 2 more adapters (InfluxDB, S3), rule packs, admin UI, Grafana dashboards, benchmarking, adapter SDK

## Design Doc Goals vs. Implementation Status

### §01-overview.md — Core Vision
| Goal | Status | Notes |
|------|--------|-------|
| Librarian (request-time routing) | DONE | core-broker + reasoning-engine |
| Curator (maintenance-time learning) | NOT STARTED | Retentive Knowledge Model (§03) |
| Gatekeeper (deterministic enforcement) | DONE | CLIPS rules, fail-closed, attestation |
| Cumulative exposure tracking | DONE | Session store + exposure facts + escalation rules |
| Source discovery | DONE | Intent analysis → source matching via CLIPS |

### §02-core-engine.md — Core Engine
| Component | Status | Gap |
|-----------|--------|-----|
| Intent Analyzer (pattern) | DONE | — |
| Intent Analyzer (LLM-assisted evolution) | NOT STARTED | LLM maintains vocabulary/mappings over time |
| Source Registry | DONE | Hot-reload not verified |
| Fathom DSL + CLIPS | DONE | — |
| Working Memory lifecycle | DONE | Consistency checks after run: NOT verified |
| 6 Adapters (PG, pgvector, ES, REST, Neo4j, SN) | DONE | — |
| S3/Document Store adapter | NOT STARTED | operator-platform scope |
| Result Synthesizer (structured merge) | DONE | — |
| Transformation rules (redaction, aggregation) | NOT STARTED | v2 design §02 |
| Persistence (Postgres + SQLite) | PARTIAL | Postgres done; SQLite fallback unclear |
| WAL mode (zero-loss) | NOT STARTED | Design §04 |
| Attestation service | DONE | — |
| Audit log | DONE | — |
| Prometheus metrics | NOT STARTED | Design §04 |
| Structured JSON logging | DONE | — |

### §03-living-brain.md — Retentive Knowledge Model (ALL NOT STARTED)
| Component | Status | Complexity |
|-----------|--------|-----------|
| Meta-rules (pattern tracking) | NOT STARTED | Medium — CLIPS rule authoring + observation facts |
| Auto-promotion of relationships | NOT STARTED | Medium — threshold logic + human review queue |
| LLM Knowledge Engineer | NOT STARTED | High — periodic analysis + YAML rule generation |
| Fuzzy similarity scoring (deffunctions) | NOT STARTED | Medium — custom CLIPS deffunctions |
| Expert Networks | NOT STARTED | Very High — CLIPS→network translation + backpropagation |
| Relationship Facts (auto-discovery) | NOT STARTED | Medium — templates exist, auto-assertion missing |
| Rule Validation Pipeline | NOT STARTED | High — 5-stage: static, shadow, sandbox, score, promote |
| Rule Rollback & Lineage | NOT STARTED | Medium — version tracking + cascade re-evaluation |
| Proactive Suggestions | NOT STARTED | Medium — suggestion rules at low salience |
| Multi-timescale observation | NOT STARTED | Medium — weekly/monthly pattern aggregation |
| Knowledge garbage collection | NOT STARTED | Low — freshness decay + aged-out relationship cleanup |
| Schema drift detection & quarantine | NOT STARTED | Medium — adapter schema hashing + quarantine rule |
| Blackboard Architecture | NOT STARTED | Very High — coordinator + domain workers + event sourcing |

### §04-architecture-operations.md — Operations
| Component | Status | Gap |
|-----------|--------|-----|
| Health check endpoint | DONE | /healthz + /readyz |
| Session lifecycle (create/TTL/close) | DONE | — |
| Session provenance tokens (JWT) | PARTIAL | JWT exists but enforcement unclear |
| Working memory consistency checks | NOT STARTED | Post-run validation + rollback |
| Failure mode handling | PARTIAL | Adapter isolation done; persistence buffering NOT done |
| In-memory audit buffer on persistence failure | NOT STARTED | Design §04 |
| Key rotation | NOT STARTED | `nautilus key rotate` command |
| Admin UI | NOT STARTED | operator-platform scope |

### §05-ecosystem-roadmap.md — Ecosystem
| Component | Status | Gap |
|-----------|--------|-----|
| Rule packs (NIST, HIPAA) | NOT STARTED | operator-platform scope |
| Custom Adapter SDK | NOT STARTED | BaseAdapter exists but no SDK docs/packaging |
| Grafana dashboard templates | NOT STARTED | operator-platform scope |
| Benchmarking suite | NOT STARTED | Latency harness exists; formal suite missing |
| Reference deployment (5 sources, 3 agents) | NOT STARTED | Demo/showcase |
| Open source launch post | NOT STARTED | — |

## External Research

### Industry Validation
- CSA NIST Agentic Profile validates "Tool-Gateway Chokepoint" pattern = Nautilus broker architecture
- Nautilus maps to XACML PDP/PEP/PAP/PIP: CLIPS=PDP, adapters=PEP, operator UI=PAP, registry=PIP
- Stateful session-based exposure tracking has no market equivalent (OPA, Permit.io are stateless per-request)
- Cooperative trust model (explicit declare_handoff) is correct scope boundary

### Key Gaps Identified by Domain Research
1. **Agent Identity**: SPIFFE/SPIRE emerging as standard for Non-Human Identity; current agent_id string is a gap
2. **Audit Integrity**: Hash chain (HMAC) is minimal; Merkle tree (RFC 6962) with inclusion/consistency proofs is production target
3. **Compliance Reporting**: Per-regime report generation from audit data (NIST, HIPAA, EU AI Act)
4. **Operator UX**: Must serve both technical operators and compliance officers; air-gapped requires bundled SPA
5. **Observability**: OpenTelemetry becoming standard for AI observability

### Architectural Patterns
- Rule packs per compliance regime (not code changes) is the industry standard
- Audit verification should be a separate tool, not embedded in the broker
- Governance UIs serve two personas: technical operators + compliance officers
- Authentication should defer to reverse proxy for enterprise SSO

## Feasibility Assessment

| Area | Assessment | Notes |
|------|-----------|-------|
| Retentive Knowledge Model (meta-rules, suggestions) | High feasibility | CLIPS infrastructure exists; rule authoring is well-understood |
| LLM Knowledge Engineer | High feasibility | LLM providers already integrated; maintenance-time-only simplifies |
| Rule Validation Pipeline | Medium feasibility | Requires audit log replay infrastructure; sandbox isolation |
| Expert Networks | Low feasibility (research) | Novel; CLIPS→network translation is uncharted; defer or spike |
| Blackboard Architecture | Low feasibility (v2+) | Major architectural change; event sourcing adds complexity |
| Operator Platform (UI) | High feasibility | Read-only over existing data; standard web patterns |
| Rule Packs | High feasibility | Fathom entry-point discovery exists; packaging is straightforward |
| Schema Drift | High feasibility | Adapter hooks exist; quarantine rule is standard CLIPS |
| Transformation Rules | Medium feasibility | New rule module; needs design for redaction/aggregation DSL |

## Recommendations for Decomposition

1. **Retentive Knowledge Model** should be its own epic or large spec — it's the entire §03 of the design
2. **Expert Networks** should be deferred or treated as a research spike — highest risk, lowest certainty
3. **Blackboard Architecture** should be deferred — it's a scaling concern for 50k+ facts, not needed now
4. **Operator Platform** is a natural separate spec with clear boundaries (read-only over broker data)
5. **Rule Packs + Adapter SDK** could be a focused spec or part of operator-platform
6. **Cross-cutting gaps** (schema drift, transformation rules, consistency checks, metrics) should be grouped into a "hardening" spec

## Open Questions
1. Is SQLite persistence actually needed or is Postgres-only acceptable?
2. What's the priority order: RKM features vs. operator platform vs. hardening?
3. Should expert networks be deferred entirely to a future phase?
4. What's the deployment target for admin UI (air-gapped mandatory or cloud-first)?
5. Is SPIFFE agent identity in scope or a future concern?

## Sources
- Design docs: design-docs/01-overview.md through 05-ecosystem-roadmap.md
- Existing specs: specs/core-broker/, specs/reasoning-engine/, specs/operator-platform/
- CSA NIST Agentic Profile, EU AI Act, IAPP, Permit.io, OPA, RFC 6962, Sigstore
- Full domain research: ./specs/_epics/design-mk2/.research-domain.md

---

## Validation Findings

*Validated 2026-04-15 against codebase at commit `2987062` (main).*

### Codebase Verification Results

#### Q1: Does fathom_router.py already have relationship fact templates or meta-rule support?

**No.** `nautilus/rules/templates/nautilus.yaml` defines 11 templates: `agent`, `intent`, `source`, `session`, `routing_decision`, `scope_constraint`, `denial_record`, `data_handoff`, `escalation_rule`, `session_exposure`, `audit_event`, `inferred_handoff`. None relate to relationships, meta-rules, suggestions, or curator functionality. `FathomRouter` (334 lines) is a thin wrapper that asserts agent/intent/source/session facts, evaluates, and reads back routing_decision/scope_constraint/denial_record. No hooks for curator-mode facts exist.

**Impact on retentive-knowledge-foundation:** All new templates (`relationship_candidate`, `source_relationship`, `data_type_affinity`, suggestion facts) must be created from scratch. The epic correctly identifies this as greenfield work.

#### Q2: Does the adapter base class already have get_schema() or drift detection?

**No.** `nautilus/adapters/base.py` defines the `Adapter` Protocol with three methods: `connect()`, `execute()`, `close()`. No `get_schema()` method exists. The word "drift" appears only in comments referring to operator-allowlist drift between `ScopeConstraint.operator` Literal types and `_OPERATOR_ALLOWLIST` (a code consistency check, not schema drift detection).

**Impact on hardening:** `get_schema()` must be added to the Adapter Protocol. This is a breaking change to the Protocol surface -- all 6 existing adapters (postgres, pgvector, elasticsearch, rest, neo4j, servicenow) need implementations. The epic mentions this in hardening but underestimates the adapter-by-adapter implementation effort.

#### Q3: Are there any transformation rule mechanisms already in place?

**No.** Zero matches for "transformation", "transform_result", or "redact" in the nautilus codebase. The current pipeline is: route -> execute adapters -> synthesize results. There is no post-query transformation step. The design doc places transformation rules at salience -1 to -19, between routing and synthesis, but no module, template, or rule infrastructure exists for this.

**Impact on hardening:** The transformation module is entirely new work -- new CLIPS module definition, new templates, new rules, and a new step in the broker pipeline where transformation rules are evaluated post-query. This is more than a "hardening" task; it's a new feature within the engine pipeline.

#### Q4: What's the current state of the audit log schema -- can it support replay?

**Partially.** The audit log uses Fathom's `FileSink` writing JSONL. Each line wraps a Fathom `AuditRecord` with the full Nautilus `AuditEntry` serialized into `metadata["nautilus_audit_entry"]`. The `AuditEntry` model carries: timestamp, request_id, agent_id, session_id, raw_intent, intent_analysis, facts_asserted_summary, routing_decisions, scope_constraints, denial_records, error_records, rule_trace, sources_queried/denied/skipped/errored, attestation_token, duration_ms, plus optional LLM provenance fields.

The forensic handoff worker (`nautilus/forensics/handoff_worker.py`) already demonstrates audit log replay: it tails the JSONL file, parses entries back into `AuditEntry` objects, and re-asserts them as facts into a fresh Fathom engine. This is the exact pattern the validation pipeline sandbox stage needs.

**Impact on rule-validation-pipeline:** The forensic worker is a proven template for sandbox replay. However, the current `AuditEntry` stores routing decisions but NOT the original facts (agent context, intent, sources). To replay accurately, the sandbox needs to reconstruct the original facts. `facts_asserted_summary` only stores counts (e.g., `{"agent": 1, "source": 3}`), not the actual fact slot values. **This is a gap**: the validation pipeline either needs to join audit entries with source registry + agent registry to reconstruct facts, or the `AuditEntry` schema needs enrichment to store the original fact slot values. The epic does not acknowledge this gap.

#### Q5: Does the existing CLIPS setup support module isolation (curator module)?

**Partially, with caveats.** Fathom's module system compiles every non-MAIN module as `(defmodule <name> (import MAIN ?ALL))` -- this imports ALL constructs from MAIN. The current codebase has one module (`nautilus-routing`) and one forensic module (`nautilus-forensics`). CLIPS modules provide namespace isolation for rules (rules in module A cannot directly fire rules in module B unless focus is switched), but facts asserted into MAIN are globally visible.

**Critical finding:** The epic states: "`curator` module rules cannot modify/retract facts in `policy` or `routing` modules (Fathom compile-time enforcement)." This claim needs verification against CLIPS semantics. CLIPS `(import MAIN ?ALL)` makes all MAIN templates available for assertion/retraction by any module's rules. Module isolation in CLIPS controls *rule activation scope* (which module's rules are eligible to fire), NOT *fact modification permissions*. A rule in the `curator` module can assert and retract facts using any template from MAIN.

To achieve the stated isolation (curator cannot modify/retract policy/routing facts), Fathom would need to either:
- a) Not export policy/routing templates to the curator module (use selective `(export ...)` / `(import ...)`)
- b) Add a compile-time check in Fathom's compiler that blocks `retract`/`modify` actions on certain templates from certain modules

Neither mechanism exists today. The current compiler always emits `(import MAIN ?ALL)`. **This is a significant gap** -- the security isolation promise in the epic's acceptance criteria for retentive-knowledge-foundation requires Fathom-level changes not captured in any spec.

#### Q6: Are there existing Prometheus or metrics hooks?

**Yes, in Fathom; No, in Nautilus.** Fathom's `Engine` has a built-in `MetricsCollector` (enabled via `metrics=True` or `FATHOM_METRICS=1`). It tracks: `fathom_evaluations_total`, `fathom_evaluation_duration_seconds`, `fathom_facts_asserted_total`, `fathom_working_memory_facts`, `fathom_rules_fired_total`, `fathom_denials_total`, `fathom_sessions_active`, plus loader counters. It uses `prometheus_client` library (optional import).

However, Nautilus's `FathomRouter` instantiates `Engine()` WITHOUT `metrics=True`. The FastAPI transport has no `/metrics` endpoint. No OpenTelemetry instrumentation exists anywhere in the nautilus codebase.

**Impact on hardening:** Enabling Fathom metrics is trivial (pass `metrics=True`). The real work is: (1) exposing `/metrics` on FastAPI, (2) adding Nautilus-level metrics beyond what Fathom tracks (adapter_query_ms, clips_lock_wait_ms, session_exposure_flags_total), and (3) OTel spans. The Fathom metrics cover ~40% of the design doc's target metrics. The epic correctly scopes this but doesn't mention leveraging Fathom's existing MetricsCollector.

---

### Per-Spec Validation

#### 1. retentive-knowledge-foundation (L)

| Aspect | Verdict | Detail |
|--------|---------|--------|
| Independent buildable? | YES, with caveat | No code dependencies on other new specs. BUT requires Fathom changes for module isolation (see Q5). |
| Interface contracts valid? | MOSTLY | Templates and fact shapes are well-defined. `RuleProposal` output interface cleanly consumed by rule-validation-pipeline. |
| Hidden dependencies? | YES | Fathom compiler changes needed for selective module imports (curator isolation). Currently all modules get `(import MAIN ?ALL)`. |
| Scope realistic for L? | TIGHT | 11 deliverables including DSL extension, multiple CLIPS modules, garbage collection, multi-timescale observation, human review queue. Each is individually medium complexity. L (4-6 weeks) is aggressive for a solo implementer. |

**Recommendations:**
- Add an explicit prerequisite task: "Fathom module isolation enhancement" to support selective `(import ...)` / `(export ...)` on non-MAIN modules.
- Consider splitting: Phase A (relationship templates, meta-rules, basic pattern tracking) vs Phase B (suggestions, garbage collection, multi-timescale, DSL extensions). Phase A is the core value; Phase B is refinement.
- The "Fathom DSL extension: `certainty` declaration" is noted as low risk since the Nautilus team maintains Fathom, but it IS a cross-repo change that needs coordination.

#### 2. rule-validation-pipeline (L)

| Aspect | Verdict | Detail |
|--------|---------|--------|
| Independent buildable? | YES | Correctly depends on retentive-knowledge-foundation for RuleProposal interface. |
| Interface contracts valid? | MOSTLY | Inputs/outputs well-defined. BUT sandbox replay has a gap (see Q4): AuditEntry lacks original fact slot values for faithful replay. |
| Hidden dependencies? | YES | (1) Audit schema enrichment or fact reconstruction logic. (2) clipspy introspection for shadow analysis -- need to verify clipspy exposes compiled rule LHS patterns for subset/superset comparison. |
| Scope realistic for L? | REALISTIC | 5-stage pipeline is well-decomposed. Forensic worker provides a replay template. L (4-6 weeks) is reasonable if the audit replay gap is addressed. |

**Recommendations:**
- Address the audit replay gap: either enrich `AuditEntry` with original fact slot values (simple but increases JSONL line size) or build a fact reconstruction service that joins audit entries with source registry snapshots. The former is simpler and should be preferred.
- Verify clipspy introspection capabilities early: does `clips.Environment.find_rule()` expose LHS patterns in a parseable form for shadow/subsumption analysis? If not, Stage 2 may need to operate on the Fathom YAML AST instead of compiled CLIPS.
- The 30-second benchmark for 1000 entries is reasonable -- the forensic worker already processes audit entries at high throughput.

#### 3. llm-knowledge-engineer (M)

| Aspect | Verdict | Detail |
|--------|---------|--------|
| Independent buildable? | YES | Correctly depends on rule-validation-pipeline. |
| Interface contracts valid? | YES | Clean producer of RuleProposal objects. Reuses existing LLM providers from `nautilus/analysis/llm/`. |
| Hidden dependencies? | NO | Existing LLM provider infrastructure (Anthropic, OpenAI, local) is well-established. |
| Scope realistic for M? | YES | M (2-4 weeks) is appropriate. Prompt engineering is iterative but the integration surface is small. |

**Recommendations:**
- No major issues. This is the cleanest spec in the epic.
- Consider making the vocabulary evolution feature (low-confidence intent analysis) a stretch goal rather than core deliverable -- it touches the intent analyzer pipeline which is already complex.

#### 4. hardening (M)

| Aspect | Verdict | Detail |
|--------|---------|--------|
| Independent buildable? | YES | No dependencies on other new specs. |
| Interface contracts valid? | MOSTLY | `get_schema()` on BaseAdapter is a Protocol change affecting all 6 adapters. Transformation module needs more design (new CLIPS module + broker pipeline integration). |
| Hidden dependencies? | YES | (1) Transformation rules require a new step in the broker pipeline, not just new rules. (2) Consistency checks wrap `FathomRouter.route()` -- this modifies the broker hot path. (3) WAL mode adds a persistence layer before CLIPS assertion. |
| Scope realistic for M? | TIGHT | 8 distinct deliverables spanning the full stack (adapters, CLIPS, broker, transport, persistence, CLI). M (3-4 weeks) may be too tight; closer to L (4-5 weeks). |

**Recommendations:**
- **Upgrade to L** or split into two specs: "hardening-observability" (schema drift, metrics, OTel, key rotation -- these are relatively isolated) and "hardening-resilience" (transformation rules, consistency checks, audit buffer, WAL -- these modify the broker pipeline).
- Leverage Fathom's existing `MetricsCollector` -- pass `metrics=True` to Engine constructor and expose Fathom's metrics on the `/metrics` endpoint as a starting point, then layer Nautilus-specific metrics.
- The `get_schema()` Protocol addition should include a `NotImplementedError` default so adapters that can't introspect their schema (REST, ServiceNow) gracefully degrade rather than requiring stub implementations.

#### 5. operator-platform (L)

| Aspect | Verdict | Detail |
|--------|---------|--------|
| Independent buildable? | MOSTLY | Depends on hardening (metrics, schema drift) and rule-validation-pipeline (review queue). Some deliverables (source status, audit viewer) could start independently. |
| Interface contracts valid? | YES | Admin API is read-only over existing broker data. Rule pack format uses Fathom's entry-point mechanism which is already implemented. |
| Hidden dependencies? | YES | (1) NIST and HIPAA rule packs ALREADY EXIST in the fathom repo (`fathom/src/fathom/rule_packs/nist_800_53/`, `hipaa/`, `cmmc/`, `owasp_agentic/`). The epic proposes creating these as Nautilus deliverables, but they may already be loadable via `engine.load_pack("nist-800-53")`. (2) The `operator-platform` brief (already written at `specs/operator-platform/brief.md`) scopes InfluxDB adapter, which the epic dropped to deferred. |
| Scope realistic for L? | TIGHT TO XL | Admin UI + S3 adapter + Adapter SDK + Grafana dashboards + benchmarking + reference deployment + rule packs. This is realistically 6-8 weeks of work, especially with UI tech decision and air-gap constraint. |

**Recommendations:**
- **Rule packs are partially done.** Fathom already ships NIST 800-53, HIPAA, CMMC, and OWASP Agentic packs. The epic should clarify: are the Nautilus rule packs *wrapping* the existing Fathom packs (adding Nautilus-specific templates like `source_schema` or `routing_decision` patterns), or are they independent? If wrapping, the scope shrinks significantly.
- The existing `specs/operator-platform/brief.md` includes InfluxDB adapter which the epic defers. Reconcile these.
- Consider splitting: Phase A (Admin API + basic UI views + S3 adapter) vs Phase B (Adapter SDK + benchmarking + reference deployment + Grafana). Phase A delivers operator value; Phase B is ecosystem/documentation.

---

### Dependency Graph Validation

The proposed dependency graph is **mostly correct** with these findings:

1. **Missing edge: retentive-knowledge-foundation -> Fathom (upstream).** Module isolation for the curator module requires Fathom compiler changes. This is an external dependency not captured in the graph.

2. **Missing edge: hardening -> all adapters.** The `get_schema()` Protocol addition touches all 6 existing adapters. This is not a spec dependency per se, but it's a cross-cutting change that should be coordinated.

3. **Potential parallel: rule-validation-pipeline does not strictly need ALL of retentive-knowledge-foundation.** It only needs the `RuleProposal` interface definition. The spec could start once the interface is defined (task 1-2 of retentive-knowledge-foundation), not after the full spec completes. **The dependency could be weakened to "interface definition only"** to reduce critical path length.

4. **operator-platform dependency on rule-validation-pipeline is partial.** Only the rule management UI views need the review queue. Source status, audit viewer, and routing decision viewer can start immediately. Consider allowing partial overlap.

---

### Missing Specs

1. **Fathom module isolation enhancement.** The epic assumes compile-time enforcement of module-scoped fact modification, which doesn't exist. Either add a Fathom-side spec or add explicit Fathom tasks within retentive-knowledge-foundation.

2. **Audit schema enrichment.** For sandbox replay to work faithfully, `AuditEntry` needs original fact slot values. This could be a task within rule-validation-pipeline or a small standalone spec.

---

### Unnecessary/Already-Done Work

1. **Rule packs (NIST, HIPAA).** Fathom already ships these at `fathom/src/fathom/rule_packs/`. The epic should scope as "Nautilus-specific extensions to existing Fathom packs" rather than "create rule packs from scratch." Estimated effort reduction: 1-2 weeks.

2. **Prometheus metrics foundation.** Fathom already has a `MetricsCollector` with `prometheus_client` integration. The epic correctly identifies this as new work for Nautilus, but the Fathom-level plumbing is ready.

---

### Overall Assessment

| Aspect | Rating | Notes |
|--------|--------|-------|
| Completeness | 8/10 | Covers all design doc goals. Missing Fathom isolation work. |
| Accuracy | 7/10 | Module isolation claim unverified. Rule packs already partially exist. Audit replay gap. |
| Dependency graph | 8/10 | Mostly correct. Could optimize critical path with weaker dependencies. |
| Sizing | 6/10 | hardening underestimated (M -> L). operator-platform tight (L -> XL). retentive-knowledge-foundation aggressive. |
| Feasibility | 8/10 | All specs are feasible. Risk is primarily in scope underestimation, not technical barriers. |

**Total estimated effort:** Epic claims ~18-24 weeks. Realistic estimate with findings: **22-30 weeks** for a single implementer, or **14-18 weeks** with 2 parallel tracks (retentive-knowledge track + hardening track).
