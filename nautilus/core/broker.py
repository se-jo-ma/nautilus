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
from nautilus.config.loader import ConfigError, load_config
from nautilus.config.models import NautilusConfig, SourceConfig
from nautilus.config.registry import SourceRegistry
from nautilus.core import PolicyEngineError
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
    from nautilus.synthesis.base import Synthesizer


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
        self._closed: bool = False

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

        Steps:
        1. Intent analysis.
        2. Session read.
        3. Fathom routing → routing decisions, scope constraints, denials.
        4. Concurrent adapter execution via ``asyncio.gather``.
        5. Split success/error results; pre-filter errors out of synthesis.
        6. Synthesize merged ``{source_id: rows}``.
        7. Sign attestation (if enabled).
        8. Emit single :class:`AuditEntry` — success OR failure.
        9. Session update, return :class:`BrokerResponse`.
        """
        context = dict(context) if context else {}
        request_id = str(uuid.uuid4())
        session_id = str(context.get("session_id", ""))
        started = time.perf_counter()

        # Pre-declared so the except block can still emit an audit entry.
        intent_analysis: IntentAnalysis = IntentAnalysis(
            raw_intent=intent,
            data_types_needed=[],
            entities=[],
        )
        routing_decisions: list[RoutingDecision] = []
        scope_by_source: dict[str, list[ScopeConstraint]] = {}
        denial_records: list[Any] = []
        rule_trace: list[str] = []
        facts_summary: dict[str, int] = {}
        sources_queried: list[str] = []
        sources_denied: list[str] = []
        sources_skipped: list[str] = []
        sources_errored_records: list[ErrorRecord] = []
        data: dict[str, list[dict[str, Any]]] = {}
        attestation_token: str | None = None

        try:
            intent_analysis = self._intent_analyzer.analyze(intent, context)

            session_state = self._session_store.get(session_id) if session_id else {}
            if session_id:
                session_state.setdefault("id", session_id)

            route_result = self._router.route(
                agent_id=agent_id,
                context=context,
                intent=intent_analysis,
                sources=self._registry.sources,
                session=session_state,
            )
            routing_decisions = route_result.routing_decisions
            scope_by_source = route_result.scope_constraints
            denial_records = route_result.denial_records
            rule_trace = list(route_result.rule_trace)
            facts_summary = dict(route_result.facts_asserted_summary)

            selected_ids = {rd.source_id for rd in routing_decisions}
            denied_ids = {d.source_id for d in denial_records}
            sources_denied = sorted(denied_ids)
            sources_skipped = sorted(
                s.id for s in self._registry if s.id not in selected_ids and s.id not in denied_ids
            )

            # Concurrent adapter fan-out — design §3.1 / NFR-3.
            adapter_tasks: list[asyncio.Task[AdapterResult]] = []
            task_source_ids: list[str] = []
            for rd in routing_decisions:
                source_id = rd.source_id
                adapter = self._adapters.get(source_id)
                if adapter is None:
                    sources_errored_records.append(
                        ErrorRecord(
                            source_id=source_id,
                            error_type="AdapterError",
                            message=f"No adapter registered for source '{source_id}'",
                            trace_id=request_id,
                        )
                    )
                    continue
                scope = scope_by_source.get(source_id, [])
                adapter_tasks.append(
                    asyncio.create_task(
                        self._execute_adapter(adapter, source_id, intent_analysis, scope, context)
                    )
                )
                task_source_ids.append(source_id)

            raw_results = await asyncio.gather(*adapter_tasks, return_exceptions=True)

            successful_results: list[AdapterResult] = []
            for source_id, res in zip(task_source_ids, raw_results, strict=True):
                if isinstance(res, BaseException):
                    sources_errored_records.append(
                        ErrorRecord(
                            source_id=source_id,
                            error_type=type(res).__name__,
                            message=str(res),
                            trace_id=request_id,
                        )
                    )
                    continue
                if res.error is not None:
                    sources_errored_records.append(res.error)
                    continue
                successful_results.append(res)
                sources_queried.append(source_id)

            data = self._synthesizer.merge(successful_results)

            if self._attestation is not None:
                attestation_token = self._sign(
                    request_id=request_id,
                    agent_id=agent_id,
                    sources_queried=sources_queried,
                    scope_by_source=scope_by_source,
                    rule_trace=rule_trace,
                    session_id=session_id,
                )

            # Phase 1: cumulative-exposure bookkeeping per design §3.9 (get at
            # start, update at end). Concrete reasoning rules land in Phase 2.
            if session_id:
                self._session_store.update(
                    session_id,
                    {
                        "last_request_id": request_id,
                        "last_sources_queried": sources_queried,
                    },
                )
        except PolicyEngineError:
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._emit_audit(
                request_id=request_id,
                agent_id=agent_id,
                session_id=session_id,
                intent=intent,
                intent_analysis=intent_analysis,
                facts_summary=facts_summary,
                routing_decisions=routing_decisions,
                scope_by_source=scope_by_source,
                denial_records=denial_records,
                errored=sources_errored_records,
                rule_trace=rule_trace,
                sources_queried=sources_queried,
                sources_denied=sources_denied,
                sources_skipped=sources_skipped,
                attestation_token=None,
                duration_ms=duration_ms,
            )
            raise
        except Exception as exc:  # noqa: BLE001 — any unexpected error must still audit
            sources_errored_records.append(
                ErrorRecord(
                    source_id="<broker>",
                    error_type=type(exc).__name__,
                    message=str(exc),
                    trace_id=request_id,
                )
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._emit_audit(
                request_id=request_id,
                agent_id=agent_id,
                session_id=session_id,
                intent=intent,
                intent_analysis=intent_analysis,
                facts_summary=facts_summary,
                routing_decisions=routing_decisions,
                scope_by_source=scope_by_source,
                denial_records=denial_records,
                errored=sources_errored_records,
                rule_trace=rule_trace,
                sources_queried=sources_queried,
                sources_denied=sources_denied,
                sources_skipped=sources_skipped,
                attestation_token=None,
                duration_ms=duration_ms,
            )
            raise

        duration_ms = int((time.perf_counter() - started) * 1000)

        self._emit_audit(
            request_id=request_id,
            agent_id=agent_id,
            session_id=session_id,
            intent=intent,
            intent_analysis=intent_analysis,
            facts_summary=facts_summary,
            routing_decisions=routing_decisions,
            scope_by_source=scope_by_source,
            denial_records=denial_records,
            errored=sources_errored_records,
            rule_trace=rule_trace,
            sources_queried=sources_queried,
            sources_denied=sources_denied,
            sources_skipped=sources_skipped,
            attestation_token=attestation_token,
            duration_ms=duration_ms,
        )

        return BrokerResponse(
            request_id=request_id,
            data=data,
            sources_queried=sorted(sources_queried),
            sources_denied=sources_denied,
            sources_skipped=sources_skipped,
            sources_errored=sources_errored_records,
            scope_restrictions=scope_by_source,
            attestation_token=attestation_token,
            duration_ms=duration_ms,
        )

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

        ``AttestationService.sign()`` expects a Fathom ``EvaluationResult``;
        we shim one together (duck-typed via ``SimpleNamespace``) whose
        ``decision`` / ``rule_trace`` fields carry the Nautilus-specific
        payload. The resulting JWT payload contains ``iss=fathom``,
        ``decision`` (a ``nautilus:<request_id>`` marker), ``rule_trace``,
        ``input_hash`` (SHA-256 of scope constraints), and ``session_id``.
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
        # Nautilus-specific decision marker; the Fathom JWT carries this as
        # the ``decision`` claim. The request_id and agent_id are embedded
        # so downstream verifiers don't need a separate Nautilus payload.
        decision = f"nautilus:{request_id}:agent={agent_id}"

        result = SimpleNamespace(
            decision=decision,
            rule_trace=list(rule_trace),
        )
        # AttestationService.sign wants a list[dict]; we pass the scope
        # payload so input_hash derives from it. Additional Nautilus context
        # (sources_queried) goes in via a synthetic fact entry.
        input_facts = [
            *scope_payload,
            {
                "__nautilus_request__": True,
                "request_id": request_id,
                "agent_id": agent_id,
                "sources_queried": list(sources_queried),
            },
        ]
        session_ref = session_id or request_id
        return self._attestation.sign(
            result=result,  # type: ignore[arg-type]
            session_id=session_ref,
            input_facts=input_facts,
        )

    def _emit_audit(
        self,
        *,
        request_id: str,
        agent_id: str,
        session_id: str,
        intent: str,
        intent_analysis: IntentAnalysis,
        facts_summary: dict[str, int],
        routing_decisions: list[RoutingDecision],
        scope_by_source: dict[str, list[ScopeConstraint]],
        denial_records: list[Any],
        errored: list[ErrorRecord],
        rule_trace: list[str],
        sources_queried: list[str],
        sources_denied: list[str],
        sources_skipped: list[str],
        attestation_token: str | None,
        duration_ms: int,
    ) -> None:
        """Build the :class:`AuditEntry` and hand it to the logger (NFR-8)."""
        flat_scope: list[ScopeConstraint] = [
            c for constraints in scope_by_source.values() for c in constraints
        ]
        entry = AuditEntry(
            timestamp=AuditLogger.utcnow(),
            request_id=request_id,
            agent_id=agent_id,
            session_id=session_id or None,
            raw_intent=intent,
            intent_analysis=intent_analysis,
            facts_asserted_summary=facts_summary,
            routing_decisions=routing_decisions,
            scope_constraints=flat_scope,
            denial_records=denial_records,
            error_records=errored,
            rule_trace=rule_trace,
            sources_queried=sources_queried,
            sources_denied=sources_denied,
            sources_skipped=sources_skipped,
            sources_errored=[e.source_id for e in errored],
            attestation_token=attestation_token,
            duration_ms=duration_ms,
        )
        self._audit_logger.emit(entry)

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
