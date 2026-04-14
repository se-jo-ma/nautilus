"""PostgreSQL adapter using asyncpg.

Implements design §3.5 (PostgresAdapter) and §6 (Scope Enforcement).

All scope values flow through ``$N`` positional placeholders; no user-supplied
value is ever string-interpolated (NFR-4, AC-4.1). The operator templates come
from the table at design §6.1.
"""

from __future__ import annotations

import time
from typing import Any, ClassVar, cast

import asyncpg  # pyright: ignore[reportMissingTypeStubs]

from nautilus.adapters.base import (
    AdapterError,
    ScopeEnforcementError,
    validate_field,
    validate_operator,
)
from nautilus.config.models import SourceConfig
from nautilus.core.models import AdapterResult, IntentAnalysis, ScopeConstraint

# Default row cap applied when the intent does not specify a ``LIMIT``.
_DEFAULT_LIMIT: int = 1000

# Array-cast hints used by the IN / NOT IN templates (design §6.1). ``asyncpg``
# will coerce to the column's actual type at execution; ``text[]`` is the
# universal default because scope values arrive as arbitrary Python objects.
_IN_ARRAY_CAST: str = "text[]"


class PostgresAdapter:
    """PostgreSQL adapter backed by an ``asyncpg.Pool``.

    Phase 1 shortcut: requires ``SourceConfig.table`` to be set (postgres and
    pgvector sources both carry it); the cross-cutting refactor lands in
    Phase 2.
    """

    source_type: ClassVar[str] = "postgres"

    def __init__(self, pool: Any = None) -> None:
        # ``pool`` is optional to support injecting a mock pool in unit tests
        # (Done-when requirement: instantiates against a mocked ``asyncpg.Pool``
        # without error). ``connect()`` is the normal construction path.
        self._pool: Any = pool
        self._config: SourceConfig | None = None
        self._closed: bool = False

    async def connect(self, config: SourceConfig) -> None:
        """Create the ``asyncpg.Pool`` from ``config.connection`` (DSN)."""
        if config.table is None:
            raise AdapterError(
                f"PostgresAdapter requires 'table' on source '{config.id}' (Phase 1 shortcut)"
            )
        self._config = config
        if self._pool is None:
            # asyncpg has no stubs; result is typed Any via the ignore above.
            self._pool = await asyncpg.create_pool(dsn=config.connection)  # pyright: ignore[reportUnknownMemberType]

    async def close(self) -> None:
        """Release the pool. Idempotent — second call is a no-op (FR-17)."""
        if self._closed:
            return
        self._closed = True
        pool = self._pool
        self._pool = None
        if pool is not None:
            await pool.close()

    def _build_sql(
        self,
        table: str,
        scope: list[ScopeConstraint],
        limit: int,
    ) -> tuple[str, list[Any]]:
        """Compose a parameterized ``SELECT`` using only positional placeholders.

        Returns ``(sql, params)`` where ``params`` are positional values aligned
        to ``$1..$N`` in ``sql``. ``table`` is treated as a trusted identifier
        (validated at config-load time) but is still quoted with double quotes.

        Each operator branch renders per the §6.1 template table.
        """
        validate_field(table.split(".")[-1])  # defensive: per-segment id check
        # Quote the table as a SQL identifier (double-quote; embedded quotes
        # escaped by doubling). This is identifier quoting, not value quoting
        # — user values never reach here.
        quoted_table = _quote_ident(table)

        where_clauses: list[str] = []
        params: list[Any] = []
        pidx = 1  # next positional placeholder index

        for constraint in scope:
            validate_operator(constraint.operator)
            validate_field(constraint.field)
            field_sql = _render_field(constraint.field)
            op = constraint.operator
            value = constraint.value

            if op in ("=", "!=", "<", ">", "<=", ">="):
                where_clauses.append(f"{field_sql} {op} ${pidx}")
                params.append(value)
                pidx += 1
            elif op == "IN":
                if not isinstance(value, list):
                    raise ScopeEnforcementError(
                        f"Operator 'IN' requires a list value, got {type(value).__name__}"
                    )
                where_clauses.append(f"{field_sql} = ANY(${pidx}::{_IN_ARRAY_CAST})")
                params.append(value)
                pidx += 1
            elif op == "NOT IN":
                if not isinstance(value, list):
                    raise ScopeEnforcementError(
                        f"Operator 'NOT IN' requires a list value, got {type(value).__name__}"
                    )
                where_clauses.append(f"{field_sql} <> ALL(${pidx}::{_IN_ARRAY_CAST})")
                params.append(value)
                pidx += 1
            elif op == "LIKE":
                if not isinstance(value, str):
                    raise ScopeEnforcementError(
                        f"Operator 'LIKE' requires a string value, got {type(value).__name__}"
                    )
                where_clauses.append(f"{field_sql} LIKE ${pidx}")
                params.append(value)
                pidx += 1
            elif op == "BETWEEN":
                if not (isinstance(value, (list, tuple)) and len(cast(Any, value)) == 2):
                    raise ScopeEnforcementError("Operator 'BETWEEN' requires a 2-tuple/list value")
                value_seq: list[Any] = list(cast(Any, value))
                where_clauses.append(f"{field_sql} BETWEEN ${pidx} AND ${pidx + 1}")
                params.extend(value_seq)
                pidx += 2
            elif op == "IS NULL":
                where_clauses.append(f"{field_sql} IS NULL")
            else:  # pragma: no cover  # unreachable: validate_operator guards this branch
                raise ScopeEnforcementError(f"Operator '{op}' unhandled in _build_sql")

        # ``LIMIT $N`` is always the last positional placeholder — asserts the
        # Done-when requirement that the generated SQL contains a positional
        # placeholder (even when ``scope`` is empty).
        where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        sql = f"SELECT * FROM {quoted_table}{where_sql} LIMIT ${pidx}"
        params.append(limit)
        return sql, params

    async def execute(
        self,
        intent: IntentAnalysis,
        scope: list[ScopeConstraint],
        context: dict[str, Any],
    ) -> AdapterResult:
        """Run the parameterized query against the pool and wrap rows."""
        del intent, context  # Phase 1: intent/context not consumed by postgres adapter
        if self._pool is None or self._config is None:
            raise AdapterError("PostgresAdapter.execute called before connect()")
        table = self._config.table
        if table is None:
            raise AdapterError(f"PostgresAdapter missing 'table' for source '{self._config.id}'")

        sql, params = self._build_sql(table, scope, _DEFAULT_LIMIT)

        started = time.perf_counter()
        async with self._pool.acquire() as conn:
            records = await conn.fetch(sql, *params)
        duration_ms = int((time.perf_counter() - started) * 1000)

        rows: list[dict[str, Any]] = [dict(r) for r in records]
        return AdapterResult(
            source_id=self._config.id,
            rows=rows,
            duration_ms=duration_ms,
        )


def _render_field(field: str) -> str:
    """Render a validated field reference as SQL.

    Plain identifier ``col`` → ``"col"``.
    Dotted identifier ``jsonb_col.key`` → ``"jsonb_col"->>'key'`` (JSONB text
    accessor). Both halves are regex-validated by ``validate_field`` upstream,
    so they are safe to splice.
    """
    if "." in field:
        parent, child = field.split(".", 1)
        # child is regex-clean — no quoting needed for the JSONB key literal
        # beyond wrapping in single quotes.
        return f"{_quote_ident(parent)}->>'{child}'"
    return _quote_ident(field)


def _quote_ident(ident: str) -> str:
    """Quote a SQL identifier by wrapping in ``"`` and doubling inner quotes."""
    return '"' + ident.replace('"', '""') + '"'


__all__ = ["PostgresAdapter"]
