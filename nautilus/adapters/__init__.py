"""Nautilus adapter package.

Exposes the ``Adapter`` Protocol, exception hierarchy, scope validators, the
built-in ``PostgresAdapter`` / ``PgVectorAdapter`` (design §3.5), the Phase-2
``ElasticsearchAdapter`` / ``Neo4jAdapter`` (design §3.11), the ``Embedder``
Protocol + ``NoopEmbedder`` default (design §3.10), and the
``ADAPTER_REGISTRY`` mapping ``SourceConfig.type`` → adapter class for
broker-side construction.
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
from nautilus.adapters.neo4j import Neo4jAdapter
from nautilus.adapters.pgvector import PgVectorAdapter
from nautilus.adapters.postgres import PostgresAdapter
from nautilus.adapters.rest import RestAdapter, SSRFBlockedError

# ``SourceConfig.type`` literal -> adapter class. The broker uses this map to
# instantiate the right adapter for each source at startup (design §3.5,
# §3.11). Phase-2 adds elasticsearch + neo4j + rest; the remaining Phase-2
# adapter (servicenow) lands in Task 2.12 and extends this map.
ADAPTER_REGISTRY: dict[str, type[Any]] = {
    "postgres": PostgresAdapter,
    "pgvector": PgVectorAdapter,
    "elasticsearch": ElasticsearchAdapter,
    "neo4j": Neo4jAdapter,
    "rest": RestAdapter,
}

__all__ = [
    "ADAPTER_REGISTRY",
    "Adapter",
    "AdapterError",
    "ElasticsearchAdapter",
    "Embedder",
    "EmbeddingUnavailableError",
    "Neo4jAdapter",
    "NoopEmbedder",
    "PgVectorAdapter",
    "PostgresAdapter",
    "RestAdapter",
    "SSRFBlockedError",
    "ScopeEnforcementError",
    "quote_identifier",
    "render_field",
    "validate_field",
    "validate_operator",
]
