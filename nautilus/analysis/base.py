"""IntentAnalyzer Protocol — design §3.3."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from nautilus.core.models import IntentAnalysis


@runtime_checkable
class IntentAnalyzer(Protocol):
    """Extracts structured :class:`IntentAnalysis` from a raw intent string."""

    def analyze(self, intent: str, context: dict[str, Any]) -> IntentAnalysis: ...
