"""Schemas for network-style endpoints."""

from __future__ import annotations

from datetime import date

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


class BioprojectMeta(BaseModel):
    """Metadata for one bioproject (NCBI / ENA / CNGB)."""

    accession: str
    source: str
    title: str | None = None
    description: str | None = None
    organism: str | None = None
    submitter: str | None = None
    submission_date: date | str | None = None
    publication_date: date | str | None = None
    data_type: str | None = None
    sample_count: int | None = None
    study_type: str | None = None
    related_pubmed: str | None = None
    related_doi: str | None = None
