"""``SessionStore`` Protocol + ``InMemorySessionStore`` (design §3.9).

Phase 1 uses an in-memory dict keyed by ``session_id``; the Protocol is
documented so Phase 2 can swap in a Redis/Postgres-backed implementation
without touching broker call sites.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SessionStore(Protocol):
    """Cumulative per-session state — design §3.9."""

    def get(self, session_id: str) -> dict[str, Any]: ...

    def update(self, session_id: str, entry: dict[str, Any]) -> None: ...


class InMemorySessionStore:
    """Dict-backed :class:`SessionStore` (Phase 1 swap-target for Phase 2).

    All state lives in a single process; restart wipes the store. Phase 2
    will introduce persistent backends (Redis, Postgres); the Protocol
    contract is stable so broker call sites do not change.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def get(self, session_id: str) -> dict[str, Any]:
        """Return the stored dict for ``session_id`` (empty dict if absent)."""
        # Return a shallow copy so callers mutating the returned dict do not
        # accidentally persist changes without going through ``update``.
        return dict(self._store.get(session_id, {}))

    def update(self, session_id: str, entry: dict[str, Any]) -> None:
        """Merge ``entry`` into the stored state for ``session_id``.

        Phase 1 semantics: later keys overwrite earlier keys (dict.update).
        Phase 2 may introduce richer merge strategies per design §3.9.
        """
        current = self._store.setdefault(session_id, {})
        current.update(entry)


__all__ = ["InMemorySessionStore", "SessionStore"]
