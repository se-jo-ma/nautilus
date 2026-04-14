"""Nautilus adapter package.

Exposes the ``Adapter`` Protocol, exception hierarchy, scope validators, and
the built-in ``PostgresAdapter`` (design §3.5).
"""

from nautilus.adapters.base import (
    Adapter,
    AdapterError,
    ScopeEnforcementError,
    validate_field,
    validate_operator,
)
from nautilus.adapters.postgres import PostgresAdapter

__all__ = [
    "Adapter",
    "AdapterError",
    "PostgresAdapter",
    "ScopeEnforcementError",
    "validate_field",
    "validate_operator",
]
