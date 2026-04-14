"""Unit tests for :class:`nautilus.Broker` construction and event-loop guard (Task 1.16).

Scope per Task 1.16 Done-when (and phase-planning fix #3):
- ``Broker.from_config`` wires every Phase-1 collaborator without raising.
- ``broker.request()`` inside a running event loop raises ``RuntimeError``
  whose message mentions ``arequest`` (UQ-4, AC-8.5).
- ``broker.close()`` / ``aclose()`` is idempotent (FR-17, AC-8.6).

End-to-end pipeline behaviour is out of scope here — the MVP e2e
integration test in Task 1.17 exercises that path against testcontainers.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from nautilus import Broker, BrokerResponse
from nautilus.core.broker import Broker as CoreBroker

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "nautilus.yaml"


@pytest.fixture(autouse=True)
def set_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide dummy DSNs so the config interpolator does not fail.

    Adapters are constructed but never ``connect()``-ed here; the DSN
    values just need to be non-empty strings.
    """
    monkeypatch.setenv("TEST_PG_DSN", "postgres://ignored/0")
    monkeypatch.setenv("TEST_PGV_DSN", "postgres://ignored/1")


@pytest.mark.unit
def test_from_config_returns_broker() -> None:
    broker = Broker.from_config(FIXTURE_PATH)
    try:
        assert isinstance(broker, Broker)
        # Same class identity whether imported from package root or core.
        assert isinstance(broker, CoreBroker)
        # Sources surface via the public ``sources`` property — exactly
        # the two entries in the fixture.
        source_ids = [s.id for s in broker.sources]
        assert source_ids == ["nvd_db", "internal_vulns"]
    finally:
        broker.close()


@pytest.mark.unit
def test_request_inside_running_loop_raises_runtime_error() -> None:
    """Sync request called inside an event loop must raise pointing at arequest."""
    broker = Broker.from_config(FIXTURE_PATH)

    async def _caller() -> None:
        with pytest.raises(RuntimeError, match=r"arequest"):
            broker.request(agent_id="agent-1", intent="ignored", context={})

    try:
        asyncio.run(_caller())
    finally:
        broker.close()


@pytest.mark.unit
def test_close_is_idempotent() -> None:
    broker = Broker.from_config(FIXTURE_PATH)
    broker.close()
    # Second close must not raise.
    broker.close()


@pytest.mark.unit
async def test_aclose_is_idempotent() -> None:
    broker = Broker.from_config(FIXTURE_PATH)
    await broker.aclose()
    await broker.aclose()


@pytest.mark.unit
def test_broker_response_reexport_is_pydantic_model() -> None:
    """Top-level ``BrokerResponse`` import is the Pydantic model from core.models."""
    # Construct a minimal instance to prove it is the real class.
    resp = BrokerResponse(
        request_id="req-1",
        data={},
        sources_queried=[],
        sources_denied=[],
        sources_skipped=[],
        sources_errored=[],
        scope_restrictions={},
        attestation_token=None,
        duration_ms=0,
    )
    assert resp.request_id == "req-1"
