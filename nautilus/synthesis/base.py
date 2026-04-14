"""Synthesizer Protocol (design §3.6).

Merges per-source :class:`AdapterResult` objects into the
``{source_id: rows}`` shape used by :class:`BrokerResponse.data`.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from nautilus.core.models import AdapterResult


@runtime_checkable
class Synthesizer(Protocol):
    """Merges successful adapter results (design §3.6).

    Implementations MUST NOT raise on per-adapter failure: the broker
    pre-filters failed adapters into ``sources_errored`` before calling
    :meth:`merge`.
    """

    def merge(self, results: list[AdapterResult]) -> dict[str, list[dict[str, Any]]]: ...


__all__ = ["Synthesizer"]
