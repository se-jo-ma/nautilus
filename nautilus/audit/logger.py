"""``AuditLogger`` — thin wrapper over a Fathom :class:`AuditSink` (design §3.7).

The Fathom-provided :class:`fathom.audit.AuditSink` Protocol accepts a
:class:`fathom.audit.AuditRecord`, whose schema is Fathom-centric
(``modules_traversed``, ``rules_fired``, ``decision``, …). The Nautilus
:class:`AuditEntry` (design §4.9) is richer: it carries routing decisions,
scope constraints, denial records, error records, and per-category
source-ID buckets.

Mapping strategy:
- Populate the Fathom ``AuditRecord`` fields that align naturally
  (``timestamp`` ISO8601, ``session_id``, ``rules_fired`` ← ``rule_trace``,
  ``duration_us``, ``decision``/``reason`` synthesised from
  ``sources_queried``/``sources_denied`` summaries).
- Persist the full Nautilus ``AuditEntry`` JSON into ``metadata`` under a
  single key so the on-disk line is a complete, loss-less record of the
  request — satisfies NFR-8 "complete audit entry" and AC-7.1 / AC-7.3.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from fathom.models import AuditRecord

from nautilus.core.models import AuditEntry


@runtime_checkable
class AuditSink(Protocol):
    """Subset of the Fathom ``AuditSink`` Protocol used by Nautilus.

    Mirrors :class:`fathom.audit.AuditSink` so callers can inject any
    duck-typed sink (e.g. an in-memory list collector in tests) without
    depending on fathom's Protocol class directly.
    """

    def write(self, record: AuditRecord) -> None: ...


# Metadata key under which the full Nautilus AuditEntry JSON lives. Kept as
# a module constant so test helpers can re-deserialise with one import.
NAUTILUS_METADATA_KEY: str = "nautilus_audit_entry"


class AuditLogger:
    """Append-only audit logger backed by a Fathom ``AuditSink``.

    Per design §3.7 / §9.1 the default sink is ``fathom.audit.FileSink`` but
    any Protocol-compatible sink is accepted. :meth:`emit` converts a
    Nautilus :class:`AuditEntry` into a Fathom :class:`AuditRecord` and
    writes it to the sink. Writes are best-effort: sink failures propagate
    to the caller so the broker can still return a response while the
    operator sees the I/O error.
    """

    def __init__(self, sink: AuditSink) -> None:
        self._sink = sink

    def emit(self, entry: AuditEntry) -> None:
        """Serialise ``entry`` and write it to the underlying sink."""
        payload_json = entry.model_dump_json()
        # ``decision`` summary: "allow" if any source queried, "deny" if any
        # denied and none queried, "error" if only errors occurred, else
        # "skip". The full detail lives in ``metadata`` under
        # ``NAUTILUS_METADATA_KEY`` (loss-less JSON of the AuditEntry).
        if entry.sources_queried:
            decision = "allow"
        elif entry.sources_denied:
            decision = "deny"
        elif entry.sources_errored:
            decision = "error"
        else:
            decision = "skip"
        reason = (
            f"queried={len(entry.sources_queried)} "
            f"denied={len(entry.sources_denied)} "
            f"skipped={len(entry.sources_skipped)} "
            f"errored={len(entry.sources_errored)}"
        )

        ts = entry.timestamp if entry.timestamp.tzinfo else entry.timestamp.replace(tzinfo=UTC)
        record = AuditRecord(
            timestamp=ts.isoformat(),
            session_id=entry.session_id or entry.request_id,
            modules_traversed=[],
            rules_fired=list(entry.rule_trace),
            decision=decision,
            reason=reason,
            duration_us=entry.duration_ms * 1000,
            metadata={NAUTILUS_METADATA_KEY: payload_json},
        )
        self._sink.write(record)

    @classmethod
    def utcnow(cls) -> datetime:
        """UTC timestamp helper so broker callers don't import datetime directly."""
        return datetime.now(tz=UTC)


def decode_nautilus_entry(record: AuditRecord) -> AuditEntry:
    """Round-trip helper: extract the Nautilus ``AuditEntry`` from an ``AuditRecord``.

    Useful for tests and downstream verifiers that read the JSONL file via
    fathom and want to inspect the richer Nautilus structure.
    """
    raw = record.metadata.get(NAUTILUS_METADATA_KEY)
    if raw is None:
        raise KeyError(f"AuditRecord has no {NAUTILUS_METADATA_KEY!r} metadata")
    return AuditEntry.model_validate(json.loads(raw))


__all__ = ["AuditLogger", "AuditSink", "NAUTILUS_METADATA_KEY", "decode_nautilus_entry"]
