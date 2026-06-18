"""Shared schema types."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    """Simple status response."""

    message: str


class GenericEnvelope(BaseModel):
    """Common response envelope."""

    success: bool = True
    message: str = "ok"
    data: Any = Field(default=None)
