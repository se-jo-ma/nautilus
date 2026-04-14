"""Nautilus adapter package.

Exposes the ``Adapter`` Protocol, exception hierarchy, scope validators, and
the built-in ``PostgresAdapter`` / ``PgVectorAdapter`` (design §3.5), plus the
``Embedder`` Protocol and ``NoopEmbedder`` default (design §3.10).
"""

from nautilus.adapters.base import (
    Adapter,
    AdapterError,
    ScopeEnforcementError,
    validate_field,
    validate_operator,
)
from nautilus.adapters.embedder import (
    Embedder,
    EmbeddingUnavailableError,
    NoopEmbedder,
)
from nautilus.adapters.pgvector import PgVectorAdapter
from nautilus.adapters.postgres import PostgresAdapter

__all__ = [
    "Adapter",
    "AdapterError",
    "Embedder",
    "EmbeddingUnavailableError",
    "NoopEmbedder",
    "PgVectorAdapter",
    "PostgresAdapter",
    "ScopeEnforcementError",
    "validate_field",
    "validate_operator",
]
