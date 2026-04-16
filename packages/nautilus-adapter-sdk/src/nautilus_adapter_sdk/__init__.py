"""Nautilus Adapter SDK — public API."""

__version__ = "0.1.0"

from .config import SourceConfig
from .exceptions import AdapterError, ScopeEnforcementError
from .protocols import Adapter, Embedder
from .scope import render_field, validate_field, validate_operator
from .types import (
    AdapterResult,
    AuthConfig,
    EndpointSpec,
    ErrorRecord,
    IntentAnalysis,
    ScopeConstraint,
)

__all__ = [
    "Adapter",
    "AdapterError",
    "AdapterResult",
    "AuthConfig",
    "Embedder",
    "EndpointSpec",
    "ErrorRecord",
    "IntentAnalysis",
    "ScopeConstraint",
    "ScopeEnforcementError",
    "SourceConfig",
    "render_field",
    "validate_field",
    "validate_operator",
]
