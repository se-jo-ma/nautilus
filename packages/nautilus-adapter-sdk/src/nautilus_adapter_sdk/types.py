"""Adapter SDK Pydantic models — independent copies of nautilus core types.

These are standalone mirrors so adapter packages have zero import dependency
on the ``nautilus`` core library.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class IntentAnalysis(BaseModel):
    """Structured intent output forwarded to adapters."""

    raw_intent: str
    normalized_intent: str
    data_types: list[str]
    purpose: str
    confidence: float


class ScopeConstraint(BaseModel):
    """Per-source WHERE-clause fragment passed to adapter execute()."""

    source_id: str
    operator: str
    field: str
    value: Any
    expires_at: str | None = None
    valid_from: str | None = None


class AdapterResult(BaseModel):
    """Single adapter execution result."""

    source_id: str
    data: Any
    metadata: dict[str, Any]


class ErrorRecord(BaseModel):
    """Adapter error report."""

    source_id: str
    error: str
    error_type: str


class AuthConfig(BaseModel):
    """Adapter authentication configuration."""

    auth_type: str
    credentials: dict[str, Any]


class EndpointSpec(BaseModel):
    """Adapter endpoint specification."""

    url: str
    method: str = "GET"
    headers: dict[str, str] | None = None
    timeout_s: float = 30.0
