"""``FathomRouter`` — thin wrapper around ``fathom.Engine`` (design §3.4).

Owns:
- Engine construction with built-in templates/module/rules + ``overlaps`` /
  ``not-in-list`` Python externals (registered BEFORE ``load_rules`` per the
  Task 1.12 SPIKE finding — CLIPS ``build`` errors with ``EXPRNPSR3`` if a
  rule LHS references an unknown function name).
- User-rule loading after defaults so user rules can override salience.
- Per-request fact assertion with multislot list-to-string encoding
  (design §5.4) and template readback for ``routing_decision`` /
  ``scope_constraint`` / ``denial_record``.
- Removal of denied sources from the routing set (design §5.4 last line).

``RouteResult`` is defined inline here for Phase 1; Task 2.1 promotes it to
``nautilus/core/models.py`` once the module shape stabilises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fathom import Engine

from nautilus.config.models import SourceConfig
from nautilus.core import PolicyEngineError
from nautilus.core.models import (
    DenialRecord,
    IntentAnalysis,
    RoutingDecision,
    ScopeConstraint,
)
from nautilus.rules.functions import register_not_in_list, register_overlaps

if TYPE_CHECKING:
    pass


@dataclass
class RouteResult:
    """Output of :meth:`FathomRouter.route` (design §3.4)."""

    routing_decisions: list[RoutingDecision]
    scope_constraints: dict[str, list[ScopeConstraint]]
    denial_records: list[DenialRecord]
    rule_trace: list[str]
    duration_us: int = 0
    facts_asserted_summary: dict[str, int] = field(default_factory=dict[str, int])


def _encode_multislot(values: list[str] | None) -> str:
    """Encode a ``list[str]`` slot as a CLIPS-safe space-separated string.

    Per design §5.4: list-typed multislot fields are joined with single
    spaces; any token containing whitespace is wrapped in double quotes so
    ``explode$`` / Python ``str.split`` reconstructs it as a single token.
    """
    if not values:
        return ""
    out: list[str] = []
    for raw in values:
        token = str(raw)
        if any(ch.isspace() for ch in token):
            # Quote the token so it survives split-on-whitespace round-trip.
            escaped = token.replace('"', '\\"')
            out.append(f'"{escaped}"')
        else:
            out.append(token)
    return " ".join(out)


class FathomRouter:
    """Wraps ``fathom.Engine`` with Nautilus templates, rules, and externals.

    Construction loads, in order: built-in templates → built-in modules →
    ``overlaps`` + ``not-in-list`` externals → built-in functions → built-in
    rules → user rules (one ``load_rules`` call per directory). Order is
    load-bearing; see Task 1.12 SPIKE notes in
    ``tests/integration/test_fathom_smoke.py``.
    """

    def __init__(
        self,
        built_in_rules_dir: Path,
        user_rules_dirs: list[Path],
        attestation: Any | None = None,  # AttestationService | None — typed loosely; jwt optional
    ) -> None:
        self._built_in_rules_dir = Path(built_in_rules_dir)
        self._user_rules_dirs = [Path(d) for d in user_rules_dirs]
        self._attestation = attestation
        try:
            self._engine: Engine = Engine()
            self._engine.load_templates(str(self._built_in_rules_dir / "templates"))
            self._engine.load_modules(str(self._built_in_rules_dir / "modules"))
            register_overlaps(self._engine)
            register_not_in_list(self._engine)
            self._engine.load_functions(str(self._built_in_rules_dir / "functions"))
            self._engine.load_rules(str(self._built_in_rules_dir / "rules"))
            for user_dir in self._user_rules_dirs:
                self._engine.load_rules(str(user_dir))
        except Exception as exc:  # noqa: BLE001 — re-wrap as PolicyEngineError per design §3.4
            raise PolicyEngineError(f"Fathom engine construction failed: {exc}") from exc

    @property
    def engine(self) -> Engine:
        """Underlying ``fathom.Engine`` (read-only handle for diagnostics)."""
        return self._engine

    def route(
        self,
        agent_id: str,
        context: dict[str, Any],
        intent: IntentAnalysis,
        sources: list[SourceConfig],
        session: dict[str, Any],
    ) -> RouteResult:
        """Run one routing pass; return populated :class:`RouteResult`.

        Steps (design §5.4):
        1. ``clear_facts()``
        2. assert ``agent``, ``intent``, each ``source``, ``session``
        3. ``evaluate()``
        4. read ``routing_decision`` / ``scope_constraint`` / ``denial_record``
        5. drop any denied source from ``routing_decisions``
        """
        try:
            self._engine.clear_facts()

            agent_fact = {
                "id": agent_id,
                "clearance": str(context.get("clearance", "")),
                "purpose": str(context.get("purpose", "")),
            }
            self._engine.assert_fact("agent", agent_fact)

            intent_fact = {
                "raw": intent.raw_intent,
                "data_types_needed": _encode_multislot(intent.data_types_needed),
                "entities": _encode_multislot(intent.entities),
            }
            self._engine.assert_fact("intent", intent_fact)

            for source in sources:
                source_fact = {
                    "id": source.id,
                    "type": source.type,
                    "classification": source.classification,
                    "data_types": _encode_multislot(source.data_types),
                    "allowed_purposes": _encode_multislot(source.allowed_purposes),
                }
                self._engine.assert_fact("source", source_fact)

            session_fact = {
                "id": str(session.get("id") or session.get("session_id") or ""),
                "pii_sources_accessed": int(session.get("pii_sources_accessed", 0)),
            }
            self._engine.assert_fact("session", session_fact)

            result = self._engine.evaluate()

            raw_routing = self._engine.query("routing_decision")
            raw_scopes = self._engine.query("scope_constraint")
            raw_denials = self._engine.query("denial_record")

            denials = [
                DenialRecord(
                    source_id=str(d["source_id"]),
                    reason=str(d["reason"]),
                    rule_name=str(d["rule_name"]),
                )
                for d in raw_denials
            ]
            denied_ids = {d.source_id for d in denials}

            routing = [
                RoutingDecision(
                    source_id=str(r["source_id"]),
                    reason=str(r["reason"]),
                )
                for r in raw_routing
                if str(r["source_id"]) not in denied_ids
            ]

            scopes_by_source: dict[str, list[ScopeConstraint]] = {}
            for s in raw_scopes:
                sid = str(s["source_id"])
                scopes_by_source.setdefault(sid, []).append(
                    ScopeConstraint(
                        source_id=sid,
                        field=str(s["field"]),
                        operator=s["operator"],  # validated by Pydantic Literal
                        value=s["value"],
                    )
                )

            duration_us = int(getattr(result, "duration_us", 0) or 0)
            rule_trace = list(getattr(result, "rule_trace", []) or [])

            facts_summary = {
                "agent": 1,
                "intent": 1,
                "source": len(sources),
                "session": 1,
            }

            return RouteResult(
                routing_decisions=routing,
                scope_constraints=scopes_by_source,
                denial_records=denials,
                rule_trace=rule_trace,
                duration_us=duration_us,
                facts_asserted_summary=facts_summary,
            )
        except PolicyEngineError:
            raise
        except Exception as exc:  # noqa: BLE001 — wrap any engine error
            raise PolicyEngineError(
                f"FathomRouter.route() failed for agent_id={agent_id!r}: {exc}"
            ) from exc

    def close(self) -> None:
        """No-op for the Phase 1 in-process Engine (kept for Protocol parity)."""
        return None


__all__ = ["FathomRouter", "RouteResult"]
