"""``Broker`` — the public Nautilus facade (design §3.1, §8, §9).

Wires every Phase 1 collaborator (``SourceRegistry``,
:class:`PatternMatchingIntentAnalyzer`, :class:`FathomRouter`, per-source
``Adapter``, :class:`BasicSynthesizer`, :class:`AuditLogger`,
``AttestationService``, :class:`InMemorySessionStore`) behind a sync
``request`` / async ``arequest`` surface.

Key design points:
- Event-loop guard (design §8): sync ``request`` raises ``RuntimeError``
  with a pointer to ``arequest`` if called inside a running loop.
- Single audit entry per request — success OR failure (NFR-8, §9.2).
- Adapter runtime exceptions are caught per-source and surfaced in
  ``sources_errored``; Fathom/engine failures raise ``PolicyEngineError``
  to the caller after emitting the audit entry (design §10).
- Attestation auto-generates an Ed25519 keypair unless
  ``attestation.private_key_path`` is set; disabled via
  ``attestation.enabled: false`` — token is ``None`` in that case (§9.4).
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from fathom.attestation import AttestationService
from fathom.audit import FileSink

from nautilus.adapters.base import Adapter, AdapterError, ScopeEnforcementError
from nautilus.adapters.embedder import Embedder, NoopEmbedder
from nautilus.adapters.pgvector import PgVectorAdapter
from nautilus.adapters.postgres import PostgresAdapter
from nautilus.analysis.pattern_matching import PatternMatchingIntentAnalyzer
from nautilus.audit.logger import AuditLogger
from nautilus.config.agent_registry import AgentRegistry
from nautilus.config.loader import ConfigError, load_config
from nautilus.config.models import NautilusConfig, SourceConfig
from nautilus.config.registry import SourceRegistry
from nautilus.core import PolicyEngineError
from nautilus.core.attestation_payload import build_payload
from nautilus.core.fathom_router import FathomRouter
from nautilus.core.models import (
    AdapterResult,
    AuditEntry,
    BrokerResponse,
    ErrorRecord,
    IntentAnalysis,
    RoutingDecision,
    ScopeConstraint,
)
from nautilus.core.session import InMemorySessionStore, SessionStore
from nautilus.rules import BUILT_IN_RULES_DIR
from nautilus.synthesis.basic import BasicSynthesizer

if TYPE_CHECKING:
    from nautilus.analysis.base import IntentAnalyzer
    from nautilus.core.fathom_router import RouteResult
    from nautilus.synthesis.base import Synthesizer


@dataclass
class _RequestState:
    """Mutable per-request scratchpad shared by ``arequest`` helpers.

    Pre-declared so the broker's except blocks can still emit a best-effort
    audit entry even when the pipeline fails mid-flight (design §9.2).
    """

    request_id: str
    session_id: str
    started: float
    intent: str
    intent_analysis: IntentAnalysis
    routing_decisions: list[RoutingDecision] = field(default_factory=list[RoutingDecision])
    scope_by_source: dict[str, list[ScopeConstraint]] = field(
        default_factory=dict[str, list[ScopeConstraint]]
    )
    denial_records: list[Any] = field(default_factory=list[Any])
    rule_trace: list[str] = field(default_factory=list[str])
    facts_summary: dict[str, int] = field(default_factory=dict[str, int])
    sources_queried: list[str] = field(default_factory=list[str])
    sources_denied: list[str] = field(default_factory=list[str])
    sources_skipped: list[str] = field(default_factory=list[str])
    errored: list[ErrorRecord] = field(default_factory=list[ErrorRecord])
    data: dict[str, list[dict[str, Any]]] = field(default_factory=dict[str, list[dict[str, Any]]])
    attestation_token: str | None = None

    def apply_route_result(self, route_result: RouteResult) -> None:
        """Copy router output into the mutable request state."""
        self.routing_decisions = route_result.routing_decisions
        self.scope_by_source = route_result.scope_constraints
        self.denial_records = route_result.denial_records
        self.rule_trace = list(route_result.rule_trace)
        self.facts_summary = dict(route_result.facts_asserted_summary)

    def duration_ms(self) -> int:
        """Integer millisecond delta since ``started`` (design §4.1)."""
        return int((time.perf_counter() - self.started) * 1000)


def _new_request_state(context: dict[str, Any], intent: str) -> _RequestState:
    """Factory for a fresh per-request scratchpad."""
    return _RequestState(
        request_id=str(uuid.uuid4()),
        session_id=str(context.get("session_id", "")),
        started=time.perf_counter(),
        intent=intent,
        intent_analysis=IntentAnalysis(raw_intent=intent, data_types_needed=[], entities=[]),
    )


def _broker_error(exc: BaseException, request_id: str) -> ErrorRecord:
    """Wrap an unexpected broker-level exception as an :class:`ErrorRecord`."""
    return ErrorRecord(
        source_id="<broker>",
        error_type=type(exc).__name__,
        message=str(exc),
        trace_id=request_id,
    )


def _source_error(source_id: str, error_type: str, message: str, request_id: str) -> ErrorRecord:
    """Build a per-source :class:`ErrorRecord` tagged with the request trace id."""
    return ErrorRecord(
        source_id=source_id,
        error_type=error_type,
        message=message,
        trace_id=request_id,
    )


def _build_audit_entry(
    agent_id: str,
    state: _RequestState,
    attestation_token: str | None,
) -> AuditEntry:
    """Materialize a flat :class:`AuditEntry` from pipeline state (design §4.9)."""
    return AuditEntry(
        timestamp=AuditLogger.utcnow(),
        request_id=state.request_id,
        agent_id=agent_id,
        session_id=state.session_id or None,
        raw_intent=state.intent,
        intent_analysis=state.intent_analysis,
        facts_asserted_summary=state.facts_summary,
        routing_decisions=state.routing_decisions,
        scope_constraints=[c for cs in state.scope_by_source.values() for c in cs],
        denial_records=state.denial_records,
        error_records=state.errored,
        rule_trace=state.rule_trace,
        sources_queried=state.sources_queried,
        sources_denied=state.sources_denied,
        sources_skipped=state.sources_skipped,
        sources_errored=[e.source_id for e in state.errored],
        attestation_token=attestation_token,
        duration_ms=state.duration_ms(),
    )


class Broker:
    """Public Nautilus facade — the sole entry point per design §3.1.

    Construct via :meth:`from_config` for the normal flow; the constructor
    is kept public for unit tests that wire collaborators directly.
    """

    def __init__(
        self,
        *,
        config: NautilusConfig,
        registry: SourceRegistry,
        intent_analyzer: IntentAnalyzer,
        router: FathomRouter,
        adapters: dict[str, Adapter],
        synthesizer: Synthesizer,
        audit_logger: AuditLogger,
        attestation: AttestationService | None,
        session_store: SessionStore,
        agent_registry: AgentRegistry | None = None,
    ) -> None:
        self._config = config
        self._registry = registry
        self._intent_analyzer = intent_analyzer
        self._router = router
        self._adapters = adapters
        self._synthesizer = synthesizer
        self._audit_logger = audit_logger
        self._attestation = attestation
        self._session_store = session_store
        # Phase-1 YAML (no ``agents:``) yields an empty registry — preserves
        # NFR-5 backwards compatibility; the registry is not yet consulted in
        # the request flow (that wiring lands in a later task).
        self._agent_registry: AgentRegistry = agent_registry or AgentRegistry({})
        self._closed: bool = False
        # Tracks which adapter ids have already been ``connect()``-ed so
        # ``arequest`` can lazy-connect on first use and skip on subsequent
        # calls (design §3.5 — adapter lifecycle is owned by the broker).
        self._connected_adapters: set[str] = set()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, path: str | Path) -> Broker:
        """Build a fully-wired :class:`Broker` from a ``nautilus.yaml`` path.

        Order of operations mirrors design §15 build sequence:
        1. Load + validate config.
        2. Build :class:`SourceRegistry`.
        3. Build :class:`PatternMatchingIntentAnalyzer` from
           ``analysis.keyword_map``.
        4. Build :class:`FathomRouter` against the built-in rules tree +
           any configured user rules.
        5. Build per-source :class:`Adapter` instances (NOT connected —
           ``connect()`` is async; first ``arequest`` is responsible).
        6. Build :class:`AuditLogger` over ``FileSink(audit.path)``.
        7. Build :class:`AttestationService` (auto-generate unless
           ``private_key_path``; return ``None`` if disabled).
        8. Build :class:`InMemorySessionStore`.

        Raises :class:`ConfigError` on bad YAML / missing env vars and
        :class:`PolicyEngineError` on engine construction failure.
        """
        config = load_config(path)

        registry = SourceRegistry(config.sources)
        agent_registry = AgentRegistry(config.agents)

        intent_analyzer = PatternMatchingIntentAnalyzer(
            keyword_map=config.analysis.keyword_map,
        )

        attestation = cls._build_attestation(config)

        user_rules_dirs = [Path(d) for d in config.rules.user_rules_dirs]
        router = FathomRouter(
            built_in_rules_dir=BUILT_IN_RULES_DIR,
            user_rules_dirs=user_rules_dirs,
            attestation=attestation,
        )

        # Broker-default embedder: strict NoopEmbedder (design §3.10 — fail
        # loudly on missing embedder rather than silent zero vectors).
        broker_default_embedder: Embedder = NoopEmbedder(strict=True)

        adapters: dict[str, Adapter] = {}
        for source in registry:
            adapters[source.id] = cls._build_adapter(source, broker_default_embedder)

        audit_path = Path(config.audit.path)
        audit_logger = AuditLogger(sink=FileSink(path=audit_path))

        session_store = InMemorySessionStore()

        synthesizer = BasicSynthesizer()

        return cls(
            config=config,
            registry=registry,
            intent_analyzer=intent_analyzer,
            router=router,
            adapters=adapters,
            synthesizer=synthesizer,
            audit_logger=audit_logger,
            attestation=attestation,
            session_store=session_store,
            agent_registry=agent_registry,
        )

    @staticmethod
    def _build_attestation(config: NautilusConfig) -> AttestationService | None:
        """Construct the attestation service per design §9.4.

        - ``enabled: false`` → ``None`` (token omitted on every response).
        - ``private_key_path`` set → load PEM from path.
        - Otherwise → generate an ephemeral Ed25519 keypair.
        """
        if not config.attestation.enabled:
            return None
        key_path = config.attestation.private_key_path
        if key_path:
            key_bytes = Path(key_path).read_bytes()
            return AttestationService.from_private_key_bytes(key_bytes)
        return AttestationService.generate_keypair()

    @staticmethod
    def _build_adapter(
        source: SourceConfig,
        broker_default_embedder: Embedder,
    ) -> Adapter:
        """Instantiate the right adapter class for ``source.type``."""
        if source.type == "postgres":
            return PostgresAdapter()
        if source.type == "pgvector":
            return PgVectorAdapter(broker_default_embedder=broker_default_embedder)
        # pragma: no cover — config loader rejects unknown types upstream.
        raise ConfigError(f"Unsupported source type '{source.type}' for id='{source.id}'")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def sources(self) -> list[SourceConfig]:
        """Registered source configs (identifier + metadata) — design §3.1."""
        return self._registry.sources

    @property
    def agent_registry(self) -> AgentRegistry:
        """Registered agent identities (design §3.5, FR-9)."""
        return self._agent_registry

    def request(
        self,
        agent_id: str,
        intent: str,
        context: dict[str, Any] | None = None,
    ) -> BrokerResponse:
        """Sync request: guards against nested event loops, then runs pipeline.

        Per design §8, calling this while inside a running event loop
        raises :class:`RuntimeError` whose message mentions ``arequest``
        (UQ-4, AC-8.5). Outside a loop, we delegate to
        :meth:`arequest` via ``asyncio.run``.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — safe to take ownership of a fresh one.
            pass
        else:
            raise RuntimeError(
                "Broker.request() called inside a running event loop. "
                "Use Broker.arequest() (async) from async contexts."
            )
        return asyncio.run(self.arequest(agent_id, intent, context))

    async def arequest(
        self,
        agent_id: str,
        intent: str,
        context: dict[str, Any] | None = None,
    ) -> BrokerResponse:
        """Async request pipeline (design §3.1, §8, §9).

        Linear sequence of awaits; heavy lifting lives in private helpers
        (`_run_pipeline`, `_build_adapter_jobs`, `_gather_adapter_results`,
        `_build_response`, `_emit_audit`). On policy-engine or unexpected
        failure, a single audit entry is still emitted before re-raising.
        """
        context = dict(context) if context else {}
        state = _new_request_state(context, intent)
        try:
            await self._run_pipeline(agent_id, intent, context, state)
        except PolicyEngineError:
            self._emit_audit(agent_id, state, None)
            raise
        except Exception as exc:  # noqa: BLE001 — any unexpected error must still audit
            state.errored.append(_broker_error(exc, state.request_id))
            self._emit_audit(agent_id, state, None)
            raise
        self._emit_audit(agent_id, state, state.attestation_token)
        return self._build_response(state)

    async def _run_pipeline(
        self,
        agent_id: str,
        intent: str,
        context: dict[str, Any],
        state: _RequestState,
    ) -> None:
        """Happy-path pipeline body — mutates ``state`` in place."""
        state.intent_analysis = self._intent_analyzer.analyze(intent, context)
        self._route(agent_id, context, state)
        tasks, task_source_ids = await self._build_adapter_jobs(state, context)
        successful = await self._gather_adapter_results(state, tasks, task_source_ids)
        state.data = self._synthesizer.merge(successful)
        if self._attestation is not None:
            state.attestation_token = self._sign(
                request_id=state.request_id,
                agent_id=agent_id,
                sources_queried=state.sources_queried,
                scope_by_source=state.scope_by_source,
                rule_trace=state.rule_trace,
                session_id=state.session_id,
            )
        self._update_session(state)

    def _route(self, agent_id: str, context: dict[str, Any], state: _RequestState) -> None:
        """Invoke the Fathom router and classify sources into queried/denied/skipped."""
        session_state = self._session_store.get(state.session_id) if state.session_id else {}
        if state.session_id:
            session_state.setdefault("id", state.session_id)
        route_result = self._router.route(
            agent_id=agent_id,
            context=context,
            intent=state.intent_analysis,
            sources=self._registry.sources,
            session=session_state,
        )
        state.apply_route_result(route_result)
        state.sources_denied = sorted({d.source_id for d in state.denial_records})
        selected_ids = {rd.source_id for rd in state.routing_decisions}
        denied_ids = set(state.sources_denied)
        state.sources_skipped = sorted(
            s.id for s in self._registry if s.id not in selected_ids and s.id not in denied_ids
        )

    def _update_session(self, state: _RequestState) -> None:
        """Phase 1 cumulative-exposure bookkeeping (design §3.9 — update at end)."""
        if not state.session_id:
            return
        self._session_store.update(
            state.session_id,
            {
                "last_request_id": state.request_id,
                "last_sources_queried": state.sources_queried,
            },
        )

    async def _build_adapter_jobs(
        self,
        state: _RequestState,
        context: dict[str, Any],
    ) -> tuple[list[asyncio.Task[AdapterResult]], list[str]]:
        """Lazy-connect + spawn one task per routing decision (design §3.1)."""
        tasks: list[asyncio.Task[AdapterResult]] = []
        task_source_ids: list[str] = []
        for rd in state.routing_decisions:
            adapter = await self._prepare_adapter(rd.source_id, state)
            if adapter is None:
                continue
            scope = state.scope_by_source.get(rd.source_id, [])
            tasks.append(
                asyncio.create_task(
                    self._execute_adapter(
                        adapter, rd.source_id, state.intent_analysis, scope, context
                    )
                )
            )
            task_source_ids.append(rd.source_id)
        return tasks, task_source_ids

    async def _prepare_adapter(self, source_id: str, state: _RequestState) -> Adapter | None:
        """Resolve and lazy-connect the adapter for ``source_id``.

        Records per-source :class:`ErrorRecord`\\ s on lookup / connect failure
        and returns ``None`` so the caller can skip this source.
        """
        adapter = self._adapters.get(source_id)
        if adapter is None:
            state.errored.append(
                _source_error(
                    source_id,
                    "AdapterError",
                    f"No adapter registered for source '{source_id}'",
                    state.request_id,
                )
            )
            return None
        if source_id in self._connected_adapters:
            return adapter
        try:
            await adapter.connect(self._registry.get(source_id))
        except Exception as exc:  # noqa: BLE001 — surface as per-source error
            state.errored.append(
                _source_error(
                    source_id, type(exc).__name__, f"connect() failed: {exc}", state.request_id
                )
            )
            return None
        self._connected_adapters.add(source_id)
        return adapter

    async def _gather_adapter_results(
        self,
        state: _RequestState,
        tasks: list[asyncio.Task[AdapterResult]],
        task_source_ids: list[str],
    ) -> list[AdapterResult]:
        """Await ``tasks`` and split into successes / errors (into state)."""
        raw = await asyncio.gather(*tasks, return_exceptions=True)
        successful: list[AdapterResult] = []
        for source_id, res in zip(task_source_ids, raw, strict=True):
            if isinstance(res, BaseException):
                state.errored.append(
                    _source_error(source_id, type(res).__name__, str(res), state.request_id)
                )
                continue
            if res.error is not None:
                state.errored.append(res.error)
                continue
            successful.append(res)
            state.sources_queried.append(source_id)
        return successful

    def _build_response(self, state: _RequestState) -> BrokerResponse:
        """Materialize the user-facing :class:`BrokerResponse` from ``state``."""
        return BrokerResponse(
            request_id=state.request_id,
            data=state.data,
            sources_queried=sorted(state.sources_queried),
            sources_denied=state.sources_denied,
            sources_skipped=state.sources_skipped,
            sources_errored=state.errored,
            scope_restrictions=state.scope_by_source,
            attestation_token=state.attestation_token,
            duration_ms=state.duration_ms(),
        )

    def _emit_audit(
        self,
        agent_id: str,
        state: _RequestState,
        attestation_token: str | None,
    ) -> None:
        """Build and hand the :class:`AuditEntry` to the logger (NFR-8, §9.2)."""
        self._audit_logger.emit(_build_audit_entry(agent_id, state, attestation_token))

    async def _execute_adapter(
        self,
        adapter: Adapter,
        source_id: str,
        intent: IntentAnalysis,
        scope: list[ScopeConstraint],
        context: dict[str, Any],
    ) -> AdapterResult:
        """Run one adapter; catch scope/adapter errors into a typed AdapterResult."""
        try:
            return await adapter.execute(intent, scope, context)
        except ScopeEnforcementError as exc:
            return AdapterResult(
                source_id=source_id,
                rows=[],
                duration_ms=0,
                error=ErrorRecord(
                    source_id=source_id,
                    error_type="ScopeEnforcementError",
                    message=str(exc),
                    trace_id="",  # filled in by caller via sources_errored
                ),
            )
        except AdapterError as exc:
            return AdapterResult(
                source_id=source_id,
                rows=[],
                duration_ms=0,
                error=ErrorRecord(
                    source_id=source_id,
                    error_type=type(exc).__name__,
                    message=str(exc),
                    trace_id="",
                ),
            )

    def _sign(
        self,
        *,
        request_id: str,
        agent_id: str,
        sources_queried: list[str],
        scope_by_source: dict[str, list[ScopeConstraint]],
        rule_trace: list[str],
        session_id: str,
    ) -> str:
        """Compose the Nautilus attestation payload and sign it (design §9.3).

        Uses :func:`nautilus.core.attestation_payload.build_payload` so the
        ``scope_hash`` / ``rule_trace_hash`` derivation is deterministic
        (NFR-14) and unit-testable in isolation.

        ``AttestationService.sign()`` expects a Fathom ``EvaluationResult``;
        we shim one together (duck-typed via ``SimpleNamespace``) whose
        ``decision`` field carries a Nautilus marker. The Nautilus payload
        itself is passed via ``input_facts`` so the JWT's ``input_hash``
        covers the full (``scope_hash``, ``rule_trace_hash``, …) claim set.
        """
        if self._attestation is None:
            # pragma: no cover — caller guards on self._attestation
            raise RuntimeError("attestation is disabled")

        scope_payload = [
            {
                "source_id": c.source_id,
                "field": c.field,
                "operator": c.operator,
                "value": c.value,
            }
            for constraints in scope_by_source.values()
            for c in constraints
        ]
        nautilus_payload = build_payload(
            request_id,
            agent_id,
            sources_queried,
            scope_payload,
            list(rule_trace),
        )

        # Nautilus-specific decision marker; the Fathom JWT carries this as
        # the ``decision`` claim. The request_id and agent_id are embedded
        # so downstream verifiers don't need a separate Nautilus payload.
        decision = f"nautilus:{request_id}:agent={agent_id}"

        result = SimpleNamespace(
            decision=decision,
            rule_trace=list(rule_trace),
        )
        # Pass the full Nautilus payload as a single synthetic fact so the
        # JWT's ``input_hash`` binds both ``scope_hash`` and
        # ``rule_trace_hash`` (plus request_id / agent_id / sources_queried).
        input_facts: list[dict[str, Any]] = [nautilus_payload]
        session_ref = session_id or request_id
        return self._attestation.sign(
            result=result,  # type: ignore[arg-type]
            session_id=session_ref,
            input_facts=input_facts,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Idempotent sync close — FR-17, AC-8.6."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "Broker.close() called inside a running event loop. "
                "Use Broker.aclose() (async) from async contexts."
            )
        asyncio.run(self.aclose())

    async def aclose(self) -> None:
        """Idempotent async close. Safe to call multiple times (FR-17)."""
        if self._closed:
            return
        self._closed = True
        for adapter in self._adapters.values():
            try:
                await adapter.close()
            except Exception:  # noqa: BLE001 — close is best-effort
                continue
        self._router.close()

    # ------------------------------------------------------------------
    # Hashing helpers (exposed for tests / §9.3 verifiers)
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_scope(scope_by_source: dict[str, list[ScopeConstraint]]) -> str:
        """SHA-256 of the stringified scope constraints — design §9.3."""
        buf: list[str] = []
        for source_id in sorted(scope_by_source):
            for c in scope_by_source[source_id]:
                buf.append(f"{source_id}|{c.field}|{c.operator}|{c.value!r}")
        return hashlib.sha256("\n".join(buf).encode()).hexdigest()


__all__ = ["Broker", "BrokerResponse"]
