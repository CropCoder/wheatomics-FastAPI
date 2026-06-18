"""Schemas for network-style endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class CoexpressionPair(BaseModel):
    """Co-expression pair record."""

    gene1: str
    gene2: str
    pcc: float
    mr: int


class PPIInteraction(BaseModel):
    """Protein interaction record."""

    wheat_id1: list[str]
    wheat_id2: list[str]
    eggnog_id1: str
    eggnog_id2: str
    score: float
    annotation1: str
    annotation2: str


class NetworkNode(BaseModel):
    """Generic node."""

    id: str
    label: str
    is_query: bool


class NetworkEdge(BaseModel):
    """Generic edge."""

    source: str
    target: str
    value: float
