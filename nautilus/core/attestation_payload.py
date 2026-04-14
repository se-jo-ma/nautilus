"""Nautilus attestation payload builder (design §9.3).

Isolated from :mod:`nautilus.core.broker` so hash determinism (NFR-14)
can be unit-tested without spinning the full broker pipeline.

The payload shape mirrors design §9.3:

.. code-block:: json

    {
      "iss": "nautilus",
      "request_id": "uuid",
      "agent_id": "agent-alpha",
      "sources_queried": ["nvd_db", "internal_vulns"],
      "rule_trace_hash": "sha256:...",
      "scope_hash": "sha256:..."
    }

``iat`` is deliberately *not* emitted here — the Fathom
``AttestationService.sign()`` stamps its own ``iat`` on the outer JWT
claim set; embedding a second timestamp here would break determinism.

Hashes are derived via canonical JSON (``sort_keys=True`` and
separators ``(",", ":")``) so structurally-identical inputs with
different dict ordering produce identical digests.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

_SHA256_PREFIX = "sha256:"


def _stable_json(value: Any) -> str:
    """Canonical JSON encoding used for deterministic hashing.

    - ``sort_keys=True`` — dict key order is irrelevant.
    - ``separators=(",", ":")`` — no incidental whitespace.
    - ``default=str`` — falls back to ``str(obj)`` for non-JSON-native
      values (e.g. ``datetime``, ``Decimal``) so hashing never raises.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: Any) -> str:
    """Return ``sha256:<hex>`` of the canonical JSON encoding of ``value``."""
    digest = hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()
    return f"{_SHA256_PREFIX}{digest}"


def build_payload(
    request_id: str,
    agent_id: str,
    sources_queried: list[str],
    scope_constraints: Any,
    rule_trace: Any,
) -> dict[str, Any]:
    """Build the Nautilus attestation payload (design §9.3).

    Parameters are positional-friendly so callers can mirror the
    arguments they would otherwise stuff into an inline dict.

    ``scope_constraints`` may be a ``list[dict]`` (already-flattened
    scope payload) or a ``dict[str, list[ScopeConstraint]]`` (broker
    internal shape); either is accepted as long as it is JSON-able (or
    has stringifiable members — see ``_stable_json``).

    ``rule_trace`` is typically a ``list[str]`` but any JSON-able value
    is accepted for flexibility.

    Returns a ``dict`` with keys ``iss``, ``request_id``, ``agent_id``,
    ``sources_queried``, ``scope_hash``, ``rule_trace_hash``. Given
    identical inputs the returned dict is bitwise identical (NFR-14).
    """
    return {
        "iss": "nautilus",
        "request_id": request_id,
        "agent_id": agent_id,
        "sources_queried": list(sources_queried),
        "scope_hash": _sha256(scope_constraints),
        "rule_trace_hash": _sha256(rule_trace),
    }


__all__ = ["build_payload"]
