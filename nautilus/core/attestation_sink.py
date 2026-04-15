"""``AttestationSink`` Protocol and Phase-1/2 implementations (design §3.14, D-18).

Durable store-and-forward delivery of signed attestation payloads. Parallels
the Phase-1 :class:`nautilus.audit.sinks.AuditSink` Protocol but is kept as a
*separate* Protocol per D-18 — attestation has a different lifecycle (may
retry, may fail, may dead-letter) from audit (immutable local record, always
succeeds). Sharing a Protocol would force dual-purpose implementations.

Task 1.13 lands the Protocol, :class:`AttestationPayload` model, and the two
Phase-1-selectable sinks:

- :class:`NullAttestationSink` — the default; no-op ``emit``/``close``. Used
  when ``config.attestation.sink.type == "null"`` (or the subsection is
  omitted, preserving NFR-5 backwards compat).
- :class:`FileAttestationSink` — append-only JSONL with ``flush()`` +
  ``os.fsync(fd)`` per ``emit`` (AC-14.2, durable-before-ack).

:class:`HttpAttestationSink` lands in Phase 2 (design §3.14, AC-14.3) and is
deliberately NOT implemented here.

**Audit-first invariant (AC-14.5 / NFR-16).** An exception raised from any
sink's ``emit`` MUST NOT abort :meth:`nautilus.core.broker.Broker.arequest`.
The broker wraps each emit in ``try/except Exception`` and logs at WARNING;
the audit entry is still written and the response still returned.
"""

from __future__ import annotations

import contextlib
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class AttestationPayload(BaseModel):
    """Store-and-forward envelope for a single attestation emission.

    - ``token`` — the signed Fathom JWT (design §9.3).
    - ``nautilus_payload`` — the Nautilus claim set that was signed (mirrors
      :func:`nautilus.core.attestation_payload.build_payload` output).
    - ``emitted_at`` — broker-local timestamp at emit time; sinks may rewrite
      this on retry but the broker records the original attempt.
    """

    model_config = ConfigDict(extra="forbid")

    token: str
    nautilus_payload: dict[str, Any]
    emitted_at: datetime


@runtime_checkable
class AttestationSink(Protocol):
    """Store-and-forward target for signed attestation payloads.

    Implementations MUST be safe to call ``close`` multiple times (idempotent);
    in-flight ``emit`` calls after ``close`` should raise or no-op per the
    concrete sink's contract.
    """

    async def emit(self, payload: AttestationPayload) -> None:
        """Deliver one payload. May raise — broker wraps in try/except."""
        ...

    async def close(self) -> None:
        """Release any held resources. Must be idempotent."""
        ...


class NullAttestationSink:
    """Default sink: no-op ``emit`` and ``close``.

    Selected when ``config.attestation.sink.type == "null"`` (or the sink
    subsection is absent in a Phase-1 YAML fixture, preserving NFR-5
    backwards compatibility). The attestation token is still signed and
    returned on :attr:`nautilus.core.models.BrokerResponse.attestation_token`
    (AC-14.4) — the null sink only skips the store-and-forward step.
    """

    async def emit(self, payload: AttestationPayload) -> None:  # noqa: ARG002
        """No-op."""
        return None

    async def close(self) -> None:
        """No-op."""
        return None


class FileAttestationSink:
    """Append-only JSONL sink with ``flush`` + ``fsync`` per emit (AC-14.2).

    Opens ``path`` in text append mode at construction time so each
    :meth:`emit` is one ``write`` + ``flush`` + ``os.fsync`` syscall trio —
    durable-before-ack semantics (NFR-16). Writes are NOT batched; each
    emit is independently fsynced so a crash between two emits can only
    lose at most zero entries before the crashing emit.

    ``close`` is idempotent; subsequent ``emit`` calls after ``close``
    raise :class:`ValueError` (propagated from the closed handle). The
    broker's ``_emit_attestation`` wrapper swallows that exception per
    AC-14.5 so this failure mode never breaks the hot path.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        # Ensure parent directory exists so consumers can point at fresh
        # ``tempfile.mkstemp`` locations (as the Verify command does) or at
        # operator-provisioned mount points (``/audit/attestation.jsonl``).
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Text-mode append; line-buffering irrelevant because every emit
        # manually flushes + fsyncs. ``utf-8`` is explicit so Windows hosts
        # (which default to cp1252) don't silently mangle JSON.
        self._fh = self._path.open("a", encoding="utf-8")
        self._closed = False

    async def emit(self, payload: AttestationPayload) -> None:
        """Write one JSONL line + ``flush`` + ``os.fsync`` (AC-14.2)."""
        line = payload.model_dump_json() + "\n"
        self._fh.write(line)
        self._fh.flush()
        os.fsync(self._fh.fileno())

    async def close(self) -> None:
        """Idempotent close: close the handle iff still open."""
        if self._closed:
            return
        self._closed = True
        # Best-effort close per D-8; a failing underlying handle must not
        # propagate since aclose ordering requires sink.close() succeed for
        # the adapter release step to proceed.
        with contextlib.suppress(Exception):
            self._fh.close()


__all__ = [
    "AttestationPayload",
    "AttestationSink",
    "FileAttestationSink",
    "NullAttestationSink",
]
