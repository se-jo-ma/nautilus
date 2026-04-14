"""IntentAnalyzer Protocol — design §3.3."""

from __future__ import annotations

from typing import Any, Protocol

from nautilus.core.models import IntentAnalysis


class IntentAnalyzer(Protocol):
    """Extracts structured :class:`IntentAnalysis` from a raw intent string."""

    def analyze(self, intent: str, context: dict[str, Any]) -> IntentAnalysis: ...
