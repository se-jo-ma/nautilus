---
spec: reasoning-engine
phase: brief
created: 2026-04-15
depends-on: core-broker
---

# Brief: reasoning-engine

## Theme

Complete Nautilus's reasoning surface and mainstream transport/adapter coverage. Combines design.md "Phase 2 — Policy and API" and "Phase 3 — Advanced Reasoning" (minus the Admin UI, which is deferred to spec `operator-platform`).

## Context

`core-broker` (Phase 1) shipped the foundational architecture: sync `Broker.request()` over an async pipeline, Fathom-backed routing, Postgres + pgvector adapters with scope enforcement, stable-hash audit, Ed25519 attestation. 59 tasks, 90.29% branch coverage, 145 tests.

What that foundation is missing before the broker is production-complete:
- **Policy depth:** Classification hierarchy with rank-based reasoning, cumulative exposure tracking across a session, cross-agent information flow detection, classification escalation rules.
- **Smarter intent analysis:** Optional LLM-backed analyzer as an alternative to pattern matching (air-gap-aware — pattern remains the default).
- **Temporal scoping:** Purpose-bound time windows asserted into Fathom's facts and enforced by adapters.
- **Mainstream adapter coverage:** Elasticsearch, REST API, Neo4j, ServiceNow — every new adapter follows the Phase 1 `Adapter` protocol template.
- **Transport surfaces:** FastAPI REST endpoint, MCP tool server, Docker image.
- **Attestation service integration:** Extend the existing PyJWT Ed25519 signing to publish to an external verifier (already signed — just needs dispatch).

## Dependency chain (rationale for one spec)

Classification hierarchy → cumulative exposure tracking → cross-agent flow → classification escalation form a natural stack: each later item requires the earlier item's facts/state. LLM analyzer and temporal scoping extend the same reasoning surface. New adapters all follow the Phase 1 template. Transport surfaces (REST/MCP) are thin wrappers over `broker.arequest` and reuse existing Pydantic models. Splitting these across two specs would force artificial coordination points.

## In scope

**Policy / reasoning (Phase 2 + Phase 3 carry-overs):**
- Classification hierarchy (YAML-driven, rank-based, custom-hierarchy support per design §Classification Hierarchy)
- Cumulative exposure tracking — session-scoped working memory, cross-source PII aggregation detection, profile-construction risk rules
- Classification escalation rules — combinations of unclassified data that escalate to classified-equivalent
- Cross-agent information flow tracking — data handoff detection with clearance comparison
- Purpose-bound temporal scoping — scope expiry / time-window constraints as Fathom facts

**Intent analysis:**
- LLM-based intent analyzer (optional, provider-abstracted, non-air-gapped) with fallback to pattern analyzer

**Adapters:**
- Elasticsearch adapter with query DSL filter injection
- REST API adapter with parameter constraints + endpoint allowlisting
- Neo4j adapter with Cypher pattern constraints
- ServiceNow adapter with GlideRecord encoded query scoping

**Transport:**
- FastAPI REST endpoint (`POST /v1/request`, `POST /v1/query`)
- MCP tool server (`NautilusMCPServer`)
- Docker container image (multi-stage, air-gap-capable base)

**Attestation:**
- Attestation service integration — dispatch signed tokens to external verifier endpoint

## Out of scope (deferred to `operator-platform`)

- Admin UI (source status dashboard, routing decision viewer, audit viewer)
- Rule packs (data-routing-nist, data-routing-hipaa)
- Grafana dashboard templates
- Benchmarking suite
- InfluxDB adapter
- S3/document store adapter
- Custom adapter SDK + documentation

## Success criteria

- All reasoning capabilities from design §Classification Hierarchy, §Cumulative Exposure Tracking, §Agent Interface are implemented with Fathom rules + tests
- REST API + MCP server both route through the existing `broker.arequest` pipeline with no bypass paths
- LLM analyzer fallback to pattern analyzer verified under simulated provider failure
- All new adapters pass the same quality gates as Phase 1 (SQL/query injection static guard, operator allowlist drift test where applicable)
- Branch coverage ≥80% (same gate as Phase 1)
- Docker image boots `nautilus serve --config ...` and handles a `POST /v1/request` end-to-end

## Rough task estimate

~55-60 tasks (scales comparably to Phase 1 because cross-agent tracking + LLM analyzer introduce new architectural surfaces while the adapter + transport work follows established templates).

## Open questions for research phase

- Shared session store for cross-agent tracking: in-process, Redis, or Postgres? (Air-gap requirement may force Postgres.)
- LLM provider abstraction: pluggable interface or concrete Anthropic/OpenAI/local-inference options?
- REST API authentication: assume upstream reverse proxy, or first-class API key support?
- MCP server: stdio-only or stdio+HTTP?
