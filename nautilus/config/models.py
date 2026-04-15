"""Nautilus configuration Pydantic models.

Mirrors design §4.1 and §4.10 verbatim, extended with Phase-2 additive fields
(design §3.5, §3.11): multi-adapter ``SourceConfig`` (elasticsearch/rest/neo4j/
servicenow), endpoint specs, auth discriminated union, agent registry records,
and top-level ``api`` / ``session_store`` / ``analysis`` / ``attestation``
subsections. All new fields have defaults so Phase-1 YAML fixtures continue to
load unchanged (NFR-5, AC-1.4).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Phase 2 auth discriminated union (design §3.5).
# ---------------------------------------------------------------------------


class BearerAuth(BaseModel):
    """Bearer-token auth config; token is resolved from env via interpolation."""

    type: Literal["bearer"] = "bearer"
    token: str


class BasicAuth(BaseModel):
    """HTTP Basic auth config."""

    type: Literal["basic"] = "basic"
    username: str
    password: str


class MtlsAuth(BaseModel):
    """Mutual-TLS auth config; paths are filesystem locations."""

    type: Literal["mtls"] = "mtls"
    cert_path: str
    key_path: str
    ca_path: str | None = None


class NoneAuth(BaseModel):
    """Explicit no-auth marker."""

    type: Literal["none"] = "none"


AuthConfig = Annotated[
    BearerAuth | BasicAuth | MtlsAuth | NoneAuth,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Phase 2 endpoint specs (design §3.5, REST/ServiceNow adapters).
# ---------------------------------------------------------------------------


class EndpointSpec(BaseModel):
    """Named REST/ServiceNow endpoint descriptor."""

    path: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    path_params: list[str] = Field(default_factory=list)
    query_params: list[str] = Field(default_factory=list)
    operator_templates: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# SourceConfig (Phase 1 fields + Phase 2 additive fields).
# ---------------------------------------------------------------------------


class SourceConfig(BaseModel):
    """Per-source YAML entry (design §4.1, extended §3.5, §3.11).

    Carries the adapter kind, classification metadata, connection DSN/base-URL
    (already env-interpolated), pgvector-only query shape options, and Phase-2
    additive fields for elasticsearch/rest/neo4j/servicenow adapters.
    """

    id: str
    type: Literal[
        "postgres",
        "pgvector",
        "elasticsearch",
        "rest",
        "neo4j",
        "servicenow",
    ]
    description: str
    classification: str
    data_types: list[str]
    allowed_purposes: list[str] | None = None
    connection: str  # post-interpolation DSN / base URL
    # pgvector-only
    table: str | None = None
    embedding_column: str | None = None
    metadata_column: str | None = None
    distance_operator: Literal["<=>", "<->", "<#>"] | None = "<=>"
    top_k: int = 10
    embedder: str | None = None  # name of registered embedder
    # Phase 2 additive fields (design §3.5, §3.11).
    index: str | None = None
    label: str | None = None
    endpoints: list[EndpointSpec] | None = None
    auth: AuthConfig | None = None
    compartments: str = ""
    sub_category: str = ""
    like_style: Literal["starts_with", "regex"] = "starts_with"


# ---------------------------------------------------------------------------
# Agent registry records (design §3.5, FR-9).
# ---------------------------------------------------------------------------


class AgentRecord(BaseModel):
    """Single agent identity declared in ``nautilus.yaml`` under ``agents``."""

    id: str
    clearance: str
    compartments: list[str] = Field(default_factory=list)
    default_purpose: str | None = None


# ---------------------------------------------------------------------------
# Top-level subsections.
# ---------------------------------------------------------------------------


class AttestationConfig(BaseModel):
    """Attestation subsection of ``nautilus.yaml`` (design §4.10)."""

    private_key_path: str | None = None
    enabled: bool = True


class RulesConfig(BaseModel):
    """Routing-rules subsection of ``nautilus.yaml`` (design §4.10)."""

    user_rules_dirs: list[str] = Field(default_factory=list)


class AuditConfig(BaseModel):
    """Audit-log subsection of ``nautilus.yaml`` (design §4.10)."""

    path: str = "./audit.jsonl"


class AnalysisConfig(BaseModel):
    """Intent-analyzer subsection of ``nautilus.yaml`` (design §4.10)."""

    keyword_map: dict[str, list[str]] = Field(default_factory=dict)


class ApiConfig(BaseModel):
    """FastAPI/MCP API subsection of ``nautilus.yaml`` (design §3.11).

    Minimal Phase-2 shell; later tasks extend with host/port/auth once the
    HTTP surface is defined.
    """

    host: str = "127.0.0.1"
    port: int = 8080


class SessionStoreConfig(BaseModel):
    """Session-store subsection of ``nautilus.yaml`` (design §3.11).

    Minimal Phase-2 shell; later tasks add backend-specific options once the
    session-store implementation lands.
    """

    backend: Literal["memory", "redis"] = "memory"
    ttl_seconds: int = 3600


# ---------------------------------------------------------------------------
# Root config document.
# ---------------------------------------------------------------------------


class NautilusConfig(BaseModel):
    """Root ``nautilus.yaml`` document (design §4.1, §4.10, extended §3.11)."""

    sources: list[SourceConfig]
    agents: dict[str, AgentRecord] = Field(default_factory=dict)
    attestation: AttestationConfig = Field(default_factory=AttestationConfig)
    rules: RulesConfig = Field(default_factory=RulesConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    session_store: SessionStoreConfig = Field(default_factory=SessionStoreConfig)
