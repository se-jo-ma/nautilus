"""Shared pytest fixtures for Nautilus test suite.

Fixture bodies are intentionally stub-minimal for the scaffold task;
later tasks (1.10+, 1.14+, 1.16) flesh out real return values once the
`IntentAnalysis`, `AuditEntry`, and `Adapter` types exist.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest


@pytest.fixture(scope="session")
def fake_intent_analyzer() -> Any:
    """Returns a stand-in intent analyzer.

    Real implementation (Task 1.10) will return a Protocol impl producing a
    fixed `IntentAnalysis`. For now we return `None` so importing conftest
    does not depend on types that do not yet exist.
    """
    return None


@pytest.fixture(scope="session")
def in_memory_audit_sink() -> list[Any]:
    """Collect audit entries into a list for assertions.

    Real implementation (Task 1.16) collects `AuditEntry` instances; the
    list API is stable so tests can append/read today.
    """
    return []


@pytest.fixture(scope="session")
def fake_adapter() -> Callable[..., Any]:
    """Callable-configurable fake adapter factory.

    Real implementation (Task 1.14) returns an `Adapter` whose `.query()`
    either returns a configured `AdapterResult` or raises a configured
    exception. For now we expose a factory that echoes its arguments so
    tests can verify wiring without depending on unbuilt types.
    """

    def _factory(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"args": args, "kwargs": kwargs}

    return _factory
