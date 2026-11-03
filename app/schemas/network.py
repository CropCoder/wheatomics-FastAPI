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
    """Protein interaction record.

    PPI_result (plant.MAP CF-MS) uses eggnog/score/annotation fields; PPI_poppin
    (rice PoppIn mapped to wheat copies) uses subgenome/identity/supporting-edge
    fields.  Both share wheat_id1/wheat_id2, and fields absent from a dataset are
    omitted from the JSON payload.
    """

    wheat_id1: list[str]
    wheat_id2: list[str]
    eggnog_id1: str = ""
    eggnog_id2: str = ""
    score: float | None = None
    annotation1: str = ""
    annotation2: str = ""
    # Populated by the PoppIn dataset only; omitted from the payload when absent
    # (see model_dump(exclude_none=True) in the router).
    rice_pair: str | None = None
    experimental_score: float | None = None
    subgenome1: str | None = None
    subgenome2: str | None = None
    supporting_edges: int | None = None
    identity1: float | None = None
    identity2: float | None = None


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
