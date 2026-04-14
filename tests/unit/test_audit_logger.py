"""Unit tests for :class:`nautilus.audit.logger.AuditLogger` (Task 2.10).

Covers AC-7.3 (deterministic JSONL output), AC-7.5 (ISO8601 UTC with ``Z``
suffix) and NFR-8 (flush-after-write durability). The scope is narrow: we
only probe the serialization hardening contract; the end-to-end broker
wiring of the logger is covered by the MVP integration test.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timezone
from pathlib import Path

import pytest
from fathom.audit import FileSink

from nautilus.audit.logger import (
    NAUTILUS_METADATA_KEY,
    AuditLogger,
    decode_nautilus_entry,
)
from nautilus.core.models import (
    AuditEntry,
    IntentAnalysis,
)


def _make_entry(ts: datetime) -> AuditEntry:
    return AuditEntry(
        timestamp=ts,
        request_id="req-7f3a",
        agent_id="agent-42",
        session_id=None,
        raw_intent="list customers",
        intent_analysis=IntentAnalysis(
            raw_intent="list customers",
            data_types_needed=["customer"],
            entities=["customer"],
        ),
        facts_asserted_summary={"source": 2},
        routing_decisions=[],
        scope_constraints=[],
        denial_records=[],
        error_records=[],
        rule_trace=["rule:routing/allow-basic"],
        sources_queried=["pg"],
        sources_denied=[],
        sources_skipped=[],
        sources_errored=[],
        attestation_token=None,
        duration_ms=12,
    )


@pytest.mark.unit
def test_audit_logger_writes_jsonl_line_with_trailing_newline(
    tmp_path: Path,
) -> None:
    """Written line must end with ``\\n`` (JSONL framing, AC-7.3)."""
    sink = FileSink(tmp_path / "audit.jsonl")
    logger = AuditLogger(sink)

    logger.emit(_make_entry(AuditLogger.utcnow()))

    raw = (tmp_path / "audit.jsonl").read_bytes()
    assert raw.endswith(b"\n"), f"audit file must end with newline, got {raw!r}"
    # Exactly one line produced for one emit.
    assert raw.count(b"\n") == 1


@pytest.mark.unit
def test_audit_logger_timestamp_ends_with_z(tmp_path: Path) -> None:
    """AC-7.5: the Nautilus timestamp field must serialise with a ``Z`` suffix."""
    sink = FileSink(tmp_path / "audit.jsonl")
    logger = AuditLogger(sink)

    ts = datetime(2026, 4, 14, 12, 34, 56, 789012, tzinfo=UTC)
    logger.emit(_make_entry(ts))

    line = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip()
    outer = json.loads(line)
    # Outer AuditRecord timestamp is also Z-suffixed for consistency.
    assert outer["timestamp"].endswith("Z"), (
        f"outer timestamp must end with 'Z', got {outer['timestamp']!r}"
    )
    entry_json = outer["metadata"][NAUTILUS_METADATA_KEY]
    entry_dict = json.loads(entry_json)
    assert entry_dict["timestamp"].endswith("Z"), (
        f"inner timestamp must end with 'Z', got {entry_dict['timestamp']!r}"
    )
    # No leftover numeric offset.
    assert "+00:00" not in entry_dict["timestamp"]


@pytest.mark.unit
def test_audit_logger_roundtrips_through_model_validate_json(
    tmp_path: Path,
) -> None:
    """Done-when: written JSONL line re-parses via ``AuditEntry.model_validate_json``."""
    sink = FileSink(tmp_path / "audit.jsonl")
    logger = AuditLogger(sink)

    ts = datetime(2026, 4, 14, 12, 0, 0, tzinfo=UTC)
    original = _make_entry(ts)
    logger.emit(original)

    line = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip()
    outer = json.loads(line)
    entry_json: str = outer["metadata"][NAUTILUS_METADATA_KEY]

    # Must parse cleanly (Pydantic accepts ISO8601 with Z as UTC).
    parsed = AuditEntry.model_validate_json(entry_json)
    assert parsed.request_id == original.request_id
    assert parsed.agent_id == original.agent_id
    assert parsed.rule_trace == original.rule_trace
    assert parsed.sources_queried == original.sources_queried
    # Round-tripped timestamp equals the original (UTC-normalised).
    assert parsed.timestamp == ts

    # decode_nautilus_entry helper must also round-trip.
    from fathom.models import AuditRecord

    rec = AuditRecord.model_validate(outer)
    decoded = decode_nautilus_entry(rec)
    assert decoded.request_id == original.request_id


@pytest.mark.unit
def test_audit_logger_normalises_non_utc_timestamp_to_z(tmp_path: Path) -> None:
    """A non-UTC timestamp must still serialise with a ``Z`` suffix (AC-7.5)."""
    sink = FileSink(tmp_path / "audit.jsonl")
    logger = AuditLogger(sink)

    # 10:00 in +02:00 == 08:00 UTC
    from datetime import timedelta

    tz = timezone(timedelta(hours=2))
    ts = datetime(2026, 4, 14, 10, 0, 0, tzinfo=tz)
    logger.emit(_make_entry(ts))

    line = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip()
    outer = json.loads(line)
    entry_dict = json.loads(outer["metadata"][NAUTILUS_METADATA_KEY])
    assert entry_dict["timestamp"].endswith("Z")
    assert entry_dict["timestamp"].startswith("2026-04-14T08:00:00")


@pytest.mark.unit
def test_audit_logger_flushes_sink_when_flush_available() -> None:
    """NFR-8: the logger must call ``flush()`` on sinks that expose it."""

    class RecordingSink:
        def __init__(self) -> None:
            self.records: list[object] = []
            self.flush_calls: int = 0

        def write(self, record: object) -> None:
            self.records.append(record)

        def flush(self) -> None:
            self.flush_calls += 1

    sink = RecordingSink()
    logger = AuditLogger(sink)  # type: ignore[arg-type]

    logger.emit(_make_entry(AuditLogger.utcnow()))
    logger.emit(_make_entry(AuditLogger.utcnow()))

    assert len(sink.records) == 2
    assert sink.flush_calls == 2, f"expected one flush per emit, got {sink.flush_calls}"


@pytest.mark.unit
def test_audit_logger_multiple_writes_append_lines(tmp_path: Path) -> None:
    """Each ``emit`` appends exactly one newline-terminated line."""
    sink = FileSink(tmp_path / "audit.jsonl")
    logger = AuditLogger(sink)

    logger.emit(_make_entry(AuditLogger.utcnow()))
    logger.emit(_make_entry(AuditLogger.utcnow()))
    logger.emit(_make_entry(AuditLogger.utcnow()))

    raw = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    assert len(lines) == 3
    for line in lines:
        outer = json.loads(line)
        AuditEntry.model_validate_json(outer["metadata"][NAUTILUS_METADATA_KEY])
