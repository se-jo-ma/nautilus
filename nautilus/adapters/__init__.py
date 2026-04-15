"""Nautilus adapter package.

Exposes the ``Adapter`` Protocol, exception hierarchy, scope validators, the
built-in ``PostgresAdapter`` / ``PgVectorAdapter`` (design §3.5), the Phase-2
``ElasticsearchAdapter`` (design §3.11), the ``Embedder`` Protocol +
``NoopEmbedder`` default (design §3.10), and the ``ADAPTER_REGISTRY`` mapping
``SourceConfig.type`` → adapter class for broker-side construction.
"""

from typing import Any

from nautilus.adapters.base import (
    Adapter,
    AdapterError,
    ScopeEnforcementError,
    quote_identifier,
    render_field,
    validate_field,
    validate_operator,
)
from nautilus.adapters.elasticsearch import ElasticsearchAdapter
from nautilus.adapters.embedder import (
    Embedder,
    EmbeddingUnavailableError,
    NoopEmbedder,
)
from nautilus.adapters.pgvector import PgVectorAdapter
from nautilus.adapters.postgres import PostgresAdapter

# ``SourceConfig.type`` literal -> adapter class. The broker uses this map to
# instantiate the right adapter for each source at startup (design §3.5,
# §3.11). Phase-2 adds elasticsearch; the remaining Phase-2 adapters land in
# Tasks 2.9 / 2.11 / 2.12 and extend this map.
ADAPTER_REGISTRY: dict[str, type[Any]] = {
    "postgres": PostgresAdapter,
    "pgvector": PgVectorAdapter,
    "elasticsearch": ElasticsearchAdapter,
}

__all__ = [
    "ADAPTER_REGISTRY",
    "Adapter",
    "AdapterError",
    "ElasticsearchAdapter",
    "Embedder",
    "EmbeddingUnavailableError",
    "NoopEmbedder",
    "PgVectorAdapter",
    "PostgresAdapter",
    "ScopeEnforcementError",
    "quote_identifier",
    "render_field",
    "validate_field",
    "validate_operator",
]
