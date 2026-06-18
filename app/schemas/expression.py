"""Schemas for expression APIs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExpressionPoint(BaseModel):
    """One sample or tissue expression point."""

    label: str
    value: float
    std: float | None = None
    error_bar: list[float] | None = None


class ExpressionGeneResult(BaseModel):
    """Expression result per gene."""

    gene_id: str
    project: str
    points: list[ExpressionPoint]


class ExpressionQueryResponse(BaseModel):
    """Batch expression query response."""

    project: str
    genes_found: int
    genes_not_found: list[str] = Field(default_factory=list)
    results: list[ExpressionGeneResult]
