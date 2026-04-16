"""No-op stubs for when OpenTelemetry is not installed."""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
from typing import Any


@contextmanager
def NoOpSpan(name: str = "", **kwargs: Any) -> Iterator[_NoOpSpanObj]:  # noqa: N802
    """Context manager that yields a no-op span object."""
    yield _NoOpSpanObj()


class _NoOpSpanObj:
    """Dummy span with no-op methods."""

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: ARG002
        pass

    def set_status(self, *args: Any, **kwargs: Any) -> None:  # noqa: ARG002
        pass

    def record_exception(self, exception: BaseException) -> None:  # noqa: ARG002
        pass


class NoOpMetrics:
    """No-op metrics that silently discard all recordings."""

    def counter(self, name: str, value: float = 1, **attrs: Any) -> None:  # noqa: ARG002
        pass

    def histogram(self, name: str, value: float = 0, **attrs: Any) -> None:  # noqa: ARG002
        pass
