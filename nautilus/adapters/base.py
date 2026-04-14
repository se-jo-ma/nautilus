"""Adapter protocol, exception hierarchy, and scope-enforcement validators.

Implements design §3.5 (Adapter Protocol) and §6 (Scope Enforcement Strategy).

The ``_OPERATOR_ALLOWLIST`` set here is the runtime counterpart to the
``Literal[...]`` on ``ScopeConstraint.operator`` in ``nautilus/core/models.py``
(design §6.1). Drift between the two is caught by a dedicated drift-guard test
(Task 3.14).
"""

from __future__ import annotations

import re
from typing import Any, ClassVar, Protocol, runtime_checkable

from nautilus.config.models import SourceConfig
from nautilus.core.models import AdapterResult, IntentAnalysis, ScopeConstraint


class AdapterError(Exception):
    """Base class for all adapter-layer failures (design §3.5 invariants)."""


class ScopeEnforcementError(AdapterError):
    """Raised when a scope constraint violates the operator/field allowlist.

    Per design §6.3, callers (the broker) convert this into a
    ``sources_errored`` entry rather than propagating to the agent.
    """


# Runtime operator allowlist — keep in sync with the ``Literal[...]`` on
# ``ScopeConstraint.operator`` in ``nautilus/core/models.py`` (design §6.1).
_OPERATOR_ALLOWLIST: frozenset[str] = frozenset(
    {
        "=",
        "!=",
        "IN",
        "NOT IN",
        "<",
        ">",
        "<=",
        ">=",
        "LIKE",
        "BETWEEN",
        "IS NULL",
    }
)


# Field-identifier regex from design §6.2.
_FIELD_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


def validate_operator(op: str) -> None:
    """Validate ``op`` against the design §6.1 operator allowlist.

    Raises ``ScopeEnforcementError`` when the operator is not on the allowlist.
    """
    if op not in _OPERATOR_ALLOWLIST:
        raise ScopeEnforcementError(
            f"Operator '{op}' not in allowlist: {sorted(_OPERATOR_ALLOWLIST)}"
        )


def validate_field(f: str) -> None:
    """Validate ``f`` matches the design §6.2 field-identifier regex.

    Accepts a simple identifier (``col``) or a single dotted pair
    (``json_col.key``) for JSONB access. Anything else raises
    ``ScopeEnforcementError``.
    """
    if not _FIELD_PATTERN.match(f):
        raise ScopeEnforcementError(f"Invalid field identifier '{f}'")


@runtime_checkable
class Adapter(Protocol):
    """Adapter Protocol mirroring design §3.5 verbatim."""

    source_type: ClassVar[str]

    async def connect(self, config: SourceConfig) -> None: ...

    async def execute(
        self,
        intent: IntentAnalysis,
        scope: list[ScopeConstraint],
        context: dict[str, Any],
    ) -> AdapterResult: ...

    async def close(self) -> None: ...


__all__ = [
    "Adapter",
    "AdapterError",
    "ScopeEnforcementError",
    "validate_field",
    "validate_operator",
]
