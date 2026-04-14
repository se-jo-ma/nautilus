"""Nautilus shared core Pydantic models.

Mirrors design §4.2–§4.9 verbatim. The ``ScopeConstraint.operator`` allowlist is
pinned via ``typing.Literal`` per design §6.1 (UQ-6); drift between the model
allowlist and the adapter runtime validator is caught by pyright + a dedicated
drift-guard test.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class IntentAnalysis(BaseModel):
    raw_intent: str
    data_types_needed: list[str]
    entities: list[str]
    temporal_scope: str | None = None
    estimated_sensitivity: str | None = None


class RoutingDecision(BaseModel):
    source_id: str
    reason: str


class ScopeConstraint(BaseModel):
    source_id: str
    field: str
    operator: Literal[
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
    ]
    value: Any  # validated by operator-specific rules


class DenialRecord(BaseModel):
    source_id: str
    reason: str
    rule_name: str


class ErrorRecord(BaseModel):
    source_id: str
    error_type: str  # e.g. "ScopeEnforcementError", "AdapterError"
    message: str
    trace_id: str  # correlation to request_id


class AdapterResult(BaseModel):
    source_id: str
    rows: list[dict[str, Any]]
    duration_ms: int
    error: ErrorRecord | None = None


class BrokerResponse(BaseModel):
    request_id: str
    data: dict[str, list[dict[str, Any]]]
    sources_queried: list[str]
    sources_denied: list[str]
    sources_skipped: list[str]
    sources_errored: list[ErrorRecord]
    scope_restrictions: dict[str, list[ScopeConstraint]]
    attestation_token: str | None
    duration_ms: int


class AuditEntry(BaseModel):
    timestamp: datetime  # UTC ISO8601
    request_id: str
    agent_id: str
    session_id: str | None
    raw_intent: str
    intent_analysis: IntentAnalysis
    facts_asserted_summary: dict[str, int]  # template -> count
    routing_decisions: list[RoutingDecision]
    scope_constraints: list[ScopeConstraint]
    denial_records: list[DenialRecord]
    error_records: list[ErrorRecord]
    rule_trace: list[str]
    sources_queried: list[str]
    sources_denied: list[str]
    sources_skipped: list[str]
    sources_errored: list[str]  # source IDs only; full error detail lives in error_records
    attestation_token: str | None
    duration_ms: int
