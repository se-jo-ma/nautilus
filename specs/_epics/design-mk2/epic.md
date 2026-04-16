# Epic: design-mk2

## Vision

Complete the Nautilus design doc vision by delivering the Retentive Knowledge Model (Curator mode), Operator Platform, and cross-cutting hardening gaps -- transforming Nautilus from a static policy broker into a self-evolving knowledge system with operator tooling.

## Success Criteria

- All design doc goals (sections 01-05) either implemented or explicitly deferred with rationale
- Curator mode operational: meta-rules observe patterns, propose rules, validate them, promote or reject
- Operators can inspect routing decisions, audit trails, and rule proposals via UI
- Compliance regimes installable as rule packs without code changes
- Production hardening: metrics, schema drift detection, result transformations, WAL persistence

## Completed Specs (context)

- **core-broker** (59/59): Foundation broker, CLIPS routing, 2 adapters, audit, attestation, session store
- **reasoning-engine** (79/79): LLM intent, 4 more adapters, REST+MCP transport, CLI, Docker, forensics, session store (Postgres), classification, exposure tracking

---

## Specs

### retentive-knowledge-foundation

- **Goal**: As an operator, I can author relationship facts and meta-rules that observe request patterns and auto-propose new routing rules, so Nautilus evolves its routing intelligence from usage data.
- **Size**: L (4-6 weeks)
- **Dependencies**: none (builds on core-broker + reasoning-engine, both complete). Requires upstream Fathom changes (see prerequisite below).
- **Prerequisites**:
  - **Fathom module isolation enhancement**: Current Fathom compiler emits `(import MAIN ?ALL)` for all non-MAIN modules, meaning any module's rules can assert/retract any MAIN template's facts. To enforce curator isolation, Fathom needs selective `(export ...)` / `(import ...)` support so the curator module cannot modify policy/routing facts. This is a cross-repo change in the Fathom compiler (Nautilus team maintains Fathom).
- **Key deliverables**:
  - Relationship fact templates (`source_relationship`, `data_type_affinity`) asserted into CLIPS working memory
  - Manual relationship authoring via YAML config
  - `curator` CLIPS module with module isolation enforced by Fathom (requires Fathom selective-import enhancement)
  - Meta-rules: `pattern-tracker` ruleset -- track sequential request patterns, increment observation counts, auto-promote high-confidence relationships
  - Meta-rules: flag ambiguous patterns (observation count 3-9) for human review queue
  - Proactive suggestion rules (`suggestions` module, salience -20 to -99): suggest related data types via affinity scores, suggest alternative sources when primary is denied
  - Fuzzy similarity scoring deffunctions (`similarity_score`, `relevance_threshold`, `freshness_weight`) registered in CLIPS
  - Knowledge garbage collection: freshness decay on relationship facts, retract aged-out relationships
  - Multi-timescale observation: weekly pattern tracker ruleset running on aggregated access logs
  - Fathom DSL extension: `certainty` declaration on rules (slot on fact templates)
  - Human review queue data model (proposed rules with metadata: proposer, timestamp, observation count, confidence)
- **Interface contracts**:
  - `relationship_candidate` fact template: `{data_type_a, data_type_b, observation_count, first_observed}`
  - `source_relationship` fact template: `{source_a, source_b, relationship_type, field, confidence, discovered_by, timestamp, status}`
  - `data_type_affinity` fact template: `{type_a, type_b, strength, observation_count, last_observed}`
  - `propose_rule` action interface: meta-rules emit `RuleProposal(yaml, proposer, lineage_metadata)` -- consumed by rule-validation-pipeline spec
  - `review_queue` data model: `ReviewItem(rule_yaml, proposer, observation_data, status: pending|approved|rejected)`
  - Suggestion facts: `suggestion_addition(data_type, reason, confidence)`, `suggestion_alternative(original, alternative, reason)`
- **Acceptance criteria**:
  - Meta-rules detect a repeated A-then-B pattern over 10 requests and emit a `RuleProposal`
  - Suggestion rules fire during evaluation and suggest related types when affinity > 0.7
  - Freshness decay retracts relationships not observed for > configured TTL
  - Weekly pattern tracker produces `weekly_relationship_candidate` from aggregated logs
  - All auto-generated facts traceable to source observations via lineage metadata
  - `curator` module rules cannot modify/retract facts in `policy` or `routing` modules (requires Fathom selective-import enhancement — see prerequisites)
- **Advisory architecture**: Extend existing CLIPS environment setup in `core/fathom_router.py`. Relationship templates load alongside existing templates. Meta-rules are standard Fathom YAML rulesets loaded at startup. Suggestion module fires after transformation module per design doc module execution order. Similarity deffunctions registered via `clips.Environment.define_function()`.

---

### rule-validation-pipeline

- **Goal**: As an operator, I can trust that auto-generated and LLM-suggested rules are validated before reaching production, so self-evolution never degrades routing quality.
- **Size**: L (4-6 weeks)
- **Dependencies**: retentive-knowledge-foundation (consumes `RuleProposal` interface — only the interface definition is needed, not full spec completion; critical path can be shortened by defining the interface early)
- **Prerequisites**:
  - **Audit schema enrichment**: Current `AuditEntry.facts_asserted_summary` stores only counts (`{"agent": 1, "source": 3}`), not original fact slot values. Sandbox replay needs full fact reconstruction. Either enrich `AuditEntry` with original fact slots (preferred — simple, increases JSONL line size) or build a fact reconstruction service that joins audit entries with source/agent registries.
  - **clipspy introspection verification**: Stage 2 shadow analysis needs to compare rule LHS patterns. Verify that `clips.Environment.find_rule()` exposes LHS in a parseable form, or plan to operate on Fathom YAML AST instead.
- **Key deliverables**:
  - Audit schema enrichment: add `facts_snapshot` field to `AuditEntry` with original fact slot values for replay
  - 5-stage validation pipeline: static analysis, shadow/subsumption check, sandbox execution, confidence scoring, promotion/rejection
  - Stage 1 (static): Fathom compile, template validation, duplicate detection, module scope check
  - Stage 2 (shadow): compare new rule LHS against all existing rules in module -- detect subset/superset conditions, cascade risk from fact modification across salience boundaries
  - Stage 3 (sandbox): load proposed rule + production ruleset into isolated CLIPS environment, replay last N audit log entries (configurable, default 1000), measure: regressions (previously-allowed now denied), policy relaxations, dead rules, memory growth, cascade depth
  - Stage 4 (scoring): confidence formula -- base 1.0, -0.3/regression, -0.2/relaxation, -0.1/shadow flag, -0.1 if fire rate <5%, -0.05/cascade warning
  - Stage 5 (promotion): high >0.9 auto-promote, medium 0.6-0.9 human review, low <0.6 reject with explanation
  - Rule rollback: `nautilus rule retract <name> --reason "..."` -- marks rule as retired, flags dependent rules for re-evaluation
  - Rule lineage tracking: version numbers, timestamps, proposer, promotion method, sandbox results preserved
  - Direct contradiction resolution: deny-always-wins for conflicting routing decisions
- **Interface contracts**:
  - Input: `RuleProposal(yaml, proposer, lineage_metadata)` from retentive-knowledge-foundation or llm-knowledge-engineer
  - Output: `ValidationResult(rule_name, stage_results[], confidence_score, decision: promoted|review|rejected)`
  - Rollback: `retract_rule(name, reason) -> RetractResult(affected_rules[])`
  - Rule store: `RuleRecord(name, version, yaml, clips_compiled, status: active|retired|proposed, lineage: {proposer, promoted_at, sandbox_score, parent_rule?})`
  - Audit log entries for every validation run and every promotion/rejection
- **Acceptance criteria**:
  - A rule that causes a previously-allowed request to be denied is automatically rejected (regression detection)
  - A rule with confidence >0.9 is auto-promoted without human intervention
  - Retracted rule triggers re-evaluation flags on all rules whose lineage traces to it
  - Full pipeline runs against 1000 replayed audit entries in <30s
  - Every promoted rule has complete lineage metadata queryable from persistence
- **Advisory architecture**: Sandbox uses a fresh `clips.Environment()` per validation run. The forensic handoff worker (`nautilus/forensics/handoff_worker.py`) already demonstrates audit log replay and serves as a proven template for the sandbox stage. Fathom's existing compile-time checks form Stage 1. Shadow analysis should try clipspy introspection first; if rule LHS is not parseable, fall back to operating on Fathom YAML AST. Pipeline is a standalone module (`nautilus/validation/pipeline.py`) invoked by both meta-rule proposer and LLM knowledge engineer.

---

### llm-knowledge-engineer

- **Goal**: As an operator, I can enable periodic LLM-driven rule suggestion so Nautilus proposes routing improvements from observed patterns without manual analysis.
- **Size**: M (2-4 weeks)
- **Dependencies**: rule-validation-pipeline (all suggestions go through validation)
- **Key deliverables**:
  - `KnowledgeEngineer` class: configurable schedule (hourly/daily/on-demand), feeds recent request patterns + existing rules + source registry to LLM, receives YAML rule suggestions
  - Integration with existing LLM providers (Anthropic, OpenAI, local) from `nautilus/analysis/llm/`
  - Prompt engineering: classification-aware constraints (no source-name references in suggestions, only data types)
  - LLM-assisted vocabulary evolution: analyze low-confidence intent results and retry patterns, propose vocabulary/purpose mapping updates
  - Air-gapped mode: KnowledgeEngineer disabled, meta-rules-only knowledge retention
  - Output: `RuleProposal` objects submitted to rule-validation-pipeline
  - CLI command: `nautilus knowledge suggest --since 24h` for on-demand runs
- **Interface contracts**:
  - Consumes: audit log (recent requests), rule store (existing rules), source registry
  - Produces: `RuleProposal(yaml, proposer="llm-engineer", lineage_metadata={prompt_hash, model, request_window})`
  - Config: `knowledge_engineer` section in `nautilus.yaml` with schedule, provider, enabled flag
- **Acceptance criteria**:
  - LLM produces valid Fathom YAML that passes Stage 1 static analysis
  - Suggestions never reference specific source names (only data types)
  - Vocabulary update proposals go through same validation pipeline as rule proposals
  - Air-gapped config disables the engineer entirely with no runtime errors
  - On-demand CLI trigger produces proposals and shows validation results
- **Advisory architecture**: Reuse `nautilus/analysis/llm/` providers. KnowledgeEngineer is a new module (`nautilus/knowledge/engineer.py`). Schedule via background asyncio task in the FastAPI app or standalone CLI invocation. Prompt templates in `nautilus/knowledge/prompts/`.

---

### hardening

- **Goal**: As an operator deploying Nautilus to production, I have schema drift detection, result transformations, persistence resilience, metrics, and consistency checks so the system is reliable under real-world conditions.
- **Size**: L (4-5 weeks) — upgraded from M based on validation: 8 deliverables spanning adapters, CLIPS, broker pipeline, transport, persistence, and CLI
- **Dependencies**: none (builds on completed specs)
- **Key deliverables**:
  - **Schema drift detection**: adapter `get_schema()` method (column names + types), schema fingerprinting (hash), `source_schema` fact template, quarantine rule (salience 200, blocks routing to drifted sources), configurable check interval (default: hourly). Note: `get_schema()` is a Protocol addition affecting all 6 existing adapters — adapters that can't introspect (REST, ServiceNow) should raise `NotImplementedError` and gracefully degrade (schema status: `unknown`)
  - **Result transformation rules**: `transformation` module rules (salience -1 to -19) for redaction, aggregation, normalization -- authored in Fathom YAML. Note: this requires a new step in the broker pipeline (post-query, pre-synthesis) — not just new rules, but a new evaluation pass in `Broker.arequest()`
  - **Working memory consistency checks**: post-engine-run validation (required session facts present, routing decisions reference valid sources), rollback on failure (retract facts asserted during failed run), deny with `system-error` reason
  - **In-memory audit buffer**: bounded queue (default 10,000 entries) on persistence failure, flush on recovery, drop oldest + warn when buffer full
  - **WAL mode**: optional write-ahead log to local disk before CLIPS assertion, replay on crash recovery, configurable via `persistence.wal_enabled` in `nautilus.yaml`
  - **Prometheus metrics endpoint**: `/metrics` with counters/histograms per design doc (requests_total, clips_evaluation_ms, adapter_query_ms, adapter_errors_total, session_exposure_flags_total, working_memory_facts gauge, clips_lock_wait_ms)
  - **OpenTelemetry spans**: request lifecycle spans (intent analysis, CLIPS evaluation, adapter queries, synthesis)
  - **Key rotation**: `nautilus key rotate` CLI command, re-signs active session tokens
- **Interface contracts**:
  - `source_schema` fact template: `{source_id, schema_hash, columns, last_checked, status: current|drifted|unknown}`
  - `BaseAdapter.get_schema() -> SchemaInfo(columns: list[ColumnDef], hash: str)` -- new method on adapter protocol
  - Transformation rule interface: fires on `routing_decision` + `agent_context` facts, can modify response data via `transform_result` action
  - `/metrics` endpoint: Prometheus text format
  - WAL config: `persistence.wal_enabled: bool`, `persistence.wal_path: str`
- **Acceptance criteria**:
  - Schema change on a source triggers quarantine within one check interval; quarantined source excluded from routing
  - Transformation rules can redact fields from query results based on agent clearance
  - Consistency check detects missing session facts after engine run and rolls back
  - Audit buffer holds entries during simulated persistence outage, flushes on recovery
  - WAL replay restores last request's state after simulated crash
  - Prometheus metrics endpoint returns valid text format with all documented counters
  - `nautilus key rotate` generates new key and existing sessions remain valid
- **Advisory architecture**: Schema drift integrates into adapter base class. Transformation rules are standard Fathom YAML but require a new broker pipeline step. Consistency checks wrap the existing `fathom_router.run()` call. Prometheus: leverage Fathom's existing `MetricsCollector` (pass `metrics=True` to Engine constructor) for ~40% of target metrics, then layer Nautilus-specific counters (adapter_query_ms, clips_lock_wait_ms, session_exposure_flags_total). OpenTelemetry via `opentelemetry-api` + `opentelemetry-sdk`. WAL is a simple JSON-lines append file in `nautilus/core/wal.py`.

---

### operator-platform

- **Goal**: As a Nautilus operator (technical or compliance), I can inspect routing decisions, browse audit trails, manage rule proposals, and view source health through a web UI, so I can operate Nautilus without CLI access.
- **Size**: L-XL (5-8 weeks) — validation found this spec is dense; consider splitting into Phase A (Admin API + UI + S3 adapter) and Phase B (SDK + benchmarking + reference deployment + Grafana)
- **Dependencies**: hardening (metrics, schema drift data), rule-validation-pipeline (review queue, rule lineage). Note: source status, audit viewer, and routing decision views have NO dependency on rule-validation-pipeline — only the rule management UI does. Partial overlap is possible.
- **Key deliverables**:
  - **Admin UI** (air-gap-compatible SPA, bundled with Nautilus):
    - Source status view: per-source health, last query, scope policy summary, schema drift status
    - Routing decision viewer: per-request trace (facts asserted, rules fired, sources selected/denied/skipped, scope constraints)
    - Audit log viewer: filterable by agent, source, decision, time range; attestation token verification
    - Rule management: view active/proposed/retired rules, approve/reject proposals from review queue, rule lineage graph
    - Classification exposure dashboard: session exposure summaries, escalation events, cross-agent flow visualizations
  - **Authentication**: reverse-proxy SSO passthrough (operator-role only), API-key fallback for headless access
  - **Rule packs**: Nautilus-specific extensions to existing Fathom packs. Note: Fathom already ships `nist-800-53`, `hipaa`, `cmmc`, and `owasp-agentic` packs at `fathom/src/fathom/rule_packs/`. Nautilus work is wrapping these with Nautilus-specific templates (source_schema, routing_decision patterns) and validating they load correctly via `engine.load_pack()`. Estimated effort reduced from 2 weeks to ~3-5 days.
  - **S3/document store adapter**: prefix/tag-based access, classification label filtering
  - **Custom adapter SDK**: documented `Adapter` protocol surface, example adapter repo, "write your first adapter" tutorial
  - **Grafana dashboard templates**: request rate, routing distribution, scope-denial rate, attestation success, per-source latency
  - **Benchmarking suite**: load harness, latency/throughput report across all adapters, reproducible via Docker
  - **Reference deployment**: 5 sources, 3 agent personas demo, showcasing routing + exposure tracking + suggestions
- **Interface contracts**:
  - Admin API: REST endpoints under `/admin/v1/` -- read-only over broker data, write for rule review actions
    - `GET /admin/v1/sources` -- source status + health
    - `GET /admin/v1/audit?agent=&source=&from=&to=` -- audit log query
    - `GET /admin/v1/decisions/{request_id}` -- full routing trace
    - `GET /admin/v1/rules?status=active|proposed|retired` -- rule listing
    - `POST /admin/v1/rules/{name}/approve` -- approve proposal
    - `POST /admin/v1/rules/{name}/reject` -- reject proposal with reason
    - `GET /admin/v1/sessions/{id}/exposure` -- exposure summary
  - Rule pack format: Fathom YAML files with `pack.yaml` manifest, installable via `fathom.packs` entry-point
  - S3 adapter: implements existing `BaseAdapter` protocol with `source_type = "s3"`
  - Adapter SDK: `nautilus-adapter-sdk` package with `BaseAdapter`, `AdapterResult`, `SchemaInfo` types + test harness
  - Grafana dashboards: JSON dashboard models, importable via Grafana API or file provisioning
- **Acceptance criteria**:
  - Admin UI renders decisions and audit entries from existing broker data with zero broker-side changes
  - UI works fully offline (no CDN dependencies) for air-gapped deployments
  - Rule packs pass Fathom pack validation and install via entry-point mechanism
  - S3 adapter passes scope enforcement tests (prefix filtering, tag-based access)
  - Adapter SDK includes working example adapter with green CI
  - Grafana dashboards render against audit sink output
  - Benchmarking suite produces reproducible report tagged to Docker image
  - Reference deployment boots with `docker compose up` and demonstrates full workflow
- **Advisory architecture**: UI tech TBD (HTMX+Jinja for air-gap simplicity vs. React+Vite for richer UX -- research phase should decide). Admin API is a separate FastAPI router mounted alongside the existing transport. Rule packs are YAML files under `rule-packs/` directory, published as separate packages on PyPI. S3 adapter uses `boto3`. Benchmarking via `locust` or `wrk`.

---

## Dependency Graph

```
                    (completed specs)
                  core-broker + reasoning-engine
                     |                    |
              +------+------+             |
              |             |             |
              v             v             v
    retentive-knowledge   hardening    (independent)
      -foundation           |
              |              |
              v              |
    rule-validation          |
      -pipeline              |
              |              |
              v              |
    llm-knowledge            |
      -engineer              |
              |              |
              +---------+----+
                        |
                        v
               operator-platform
```

**Parallel tracks**:
- `retentive-knowledge-foundation` and `hardening` can start simultaneously (no mutual dependency)
- `rule-validation-pipeline` blocks on `retentive-knowledge-foundation` for the `RuleProposal` interface definition only (not full spec completion — define the interface in early tasks to unblock)
- `llm-knowledge-engineer` blocks on `rule-validation-pipeline` (suggestions must go through validation)
- `operator-platform` blocks on `hardening` (metrics, schema drift) and `rule-validation-pipeline` (review queue UI only — source/audit views can start earlier)

**Critical path**: retentive-knowledge-foundation (interface definition) -> rule-validation-pipeline -> operator-platform (rule management UI)

**Upstream dependency**: retentive-knowledge-foundation requires Fathom selective-import enhancement (cross-repo)

---

## Deferred Work

| Item | Reason | Revisit |
|------|--------|---------|
| **Expert Networks** (CLIPS-to-neural-network translation, backpropagation on certainty factors) | Very high risk -- novel research with no existing Python implementation. Requires stable rule base + 1000+ labeled audit decisions. Parser is primary engineering effort with uncertain scope. | After rule-validation-pipeline is battle-tested and sufficient audit history exists. Spike first. |
| **Blackboard Architecture** (coordinator + domain workers + event sourcing) | Scaling concern for 50k+ facts. Single-instance CLIPS handles current scale. Major architectural change with event-sourcing persistence model. | When RETE performance degrades measurably in production deployments. Design spike only. |
| **Knowledge Federation** (cross-instance knowledge sharing) | v3 concept. Depends on stable RKM, battle-tested validation pipeline, settled fact schemas, and cross-org legal agreements. | After v2 proves itself in multi-deployment scenarios. |
| **SQLite persistence backend** | Postgres-only is acceptable for all current deployment targets including Docker. SQLite adds test surface without clear user demand. | If single-file deployment demand materializes. |
| **InfluxDB adapter** | Lower priority than S3. No current user demand. | Community contribution opportunity. |
| **SPIFFE/SPIRE agent identity** | Current `agent_id` string is sufficient for initial deployments. SPIFFE integration is infrastructure-level and can be added without broker changes. | When zero-trust deployment requirements emerge. |
| **EU AI Act rule pack** | Regulation fully applicable Aug 2026. NIST and HIPAA are higher priority for initial users. | After NIST + HIPAA packs validate the rule-pack packaging model. |
| **Audit integrity (Merkle tree)** | Current HMAC hash chain is minimal viable. Merkle tree with inclusion/consistency proofs is production target but not blocking. | After audit log has production volume and verification tooling is needed. |

---

## Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Sandbox replay performance** -- replaying 1000 audit entries per validation run may be slow with complex rule sets | Pipeline latency makes auto-promotion impractical | Medium | Benchmark early. Consider sampling strategies. Parallelize sandbox runs. |
| **Meta-rule self-modification cycles** -- rules that write rules could create infinite loops or retraction cascades | System instability, runaway fact growth | Medium | Module isolation (curator cannot touch policy/routing). Depth limits on meta-rule chains. Cascade depth monitoring in validation pipeline. |
| **LLM suggestion quality** -- LLM may generate syntactically valid but semantically harmful rules | Bad rules reach review queue frequently, operator fatigue | Medium | Validation pipeline catches regressions automatically. Classification-aware prompt constraints. Operator can disable LLM engineer. |
| **Admin UI air-gap constraint** -- bundled SPA must work with zero external dependencies | Tech choice constrains UX capabilities | Low | Decide tech stack in research phase. HTMX+Jinja is safest for air-gap. |
| **Rule pack portability** -- NIST/HIPAA rules may be too organization-specific to generalize | Packs require heavy customization, reducing value | Medium | Design packs as composable building blocks (base rules + customization overlay) rather than monolithic policy sets. |
| **Fathom DSL extension risk** -- adding `certainty` declaration requires upstream Fathom changes | Dependency on Fathom release cycle | Low | Nautilus team maintains Fathom. Can be coordinated. Implement as slot on fact templates first, DSL sugar later. |
| **Scope creep on operator-platform** -- UI features tend to expand | Spec exceeds L estimate | High | Strict MVP: read-only views first, rule management second. No custom dashboards in v1. |
| **CLIPS module isolation gap** -- Fathom `(import MAIN ?ALL)` means curator rules can modify policy/routing facts today | Security isolation promise broken; meta-rules could corrupt routing | High | Prerequisite: Fathom selective-import enhancement. Must be completed before retentive-knowledge-foundation reaches curator module tasks. |
| **Audit replay fidelity** -- `AuditEntry` lacks original fact slot values for sandbox replay | Validation pipeline produces inaccurate regression/relaxation results | Medium | Enrich AuditEntry with `facts_snapshot` field early in rule-validation-pipeline. Increases JSONL line size but ensures faithful replay. |
| **get_schema() Protocol change** -- adding method to BaseAdapter affects all 6 existing adapters | Breaking Protocol change; regression risk | Low | Use `NotImplementedError` default for adapters that can't introspect. Add per-adapter implementation incrementally. |
