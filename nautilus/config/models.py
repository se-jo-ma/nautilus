"""Nautilus configuration Pydantic models.

Mirrors design §4.1 and §4.10 verbatim.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SourceConfig(BaseModel):
    """Per-source YAML entry (design §4.1).

    Carries the adapter kind, classification metadata, connection DSN
    (already env-interpolated), and pgvector-only query shape options.
    """

    id: str
    type: Literal["postgres", "pgvector"]
    description: str
    classification: str
    data_types: list[str]
    allowed_purposes: list[str] | None = None
    connection: str  # post-interpolation DSN
    # pgvector-only
    table: str | None = None
    embedding_column: str | None = None
    metadata_column: str | None = None
    distance_operator: Literal["<=>", "<->", "<#>"] | None = "<=>"
    top_k: int = 10
    embedder: str | None = None  # name of registered embedder


class AttestationConfig(BaseModel):
    """Attestation subsection of ``nautilus.yaml`` (design §4.10)."""

    private_key_path: str | None = None
    enabled: bool = True


class RulesConfig(BaseModel):
    """Routing-rules subsection of ``nautilus.yaml`` (design §4.10)."""

    user_rules_dirs: list[str] = []


class AuditConfig(BaseModel):
    """Audit-log subsection of ``nautilus.yaml`` (design §4.10)."""

    path: str = "./audit.jsonl"


class AnalysisConfig(BaseModel):
    """Intent-analyzer subsection of ``nautilus.yaml`` (design §4.10)."""

    keyword_map: dict[str, list[str]] = {}


class NautilusConfig(BaseModel):
    """Root ``nautilus.yaml`` document (design §4.1, §4.10)."""

    sources: list[SourceConfig]
    attestation: AttestationConfig = AttestationConfig()
    rules: RulesConfig = RulesConfig()
    audit: AuditConfig = AuditConfig()
    analysis: AnalysisConfig = AnalysisConfig()
