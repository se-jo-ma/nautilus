"""Adapter SDK configuration models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class SourceConfig(BaseModel):
    """Configuration for a data source adapter."""

    model_config = ConfigDict(extra="allow")

    id: str
    type: str
    description: str = ""
    classification: str = ""
    data_types: list[str] = []
    allowed_purposes: list[str] = []
    connection: dict[str, Any] = {}
