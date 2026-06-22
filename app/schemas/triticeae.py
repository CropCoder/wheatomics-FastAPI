"""Schemas for Triticeae Research Filter paper database."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class TriticeaePaper(BaseModel):
    """A single paper entry from the Triticeae_Research_filter database."""

    pubmedid: str | None = None
    pub_date: str | None = None
    authors: str | None = None
    paper_title: str | None = None
    abstract: str | None = None
    fga_title: str | None = None
    gene_name: list[str] = Field(default_factory=list)
    trait_label: str | None = None
    evidence_type: str | None = None
    confidence: float | None = None
    review_status: str | None = None
    pubmed_keywords: str | None = None
    ai_tags: str | None = None
    functional_gene_tags: str | None = None
    new_tags: str | None = None
    old_fga_disease_gene_tags: str | None = None
    old_paper_disease_gene_tags: str | None = None
    new_disease_gene_tags: str | None = None
    match_detail: str | None = None


class TriticeaeSearchResult(BaseModel):
    """Paginated search results."""

    total: int = 0
    limit: int = 20
    offset: int = 0
    papers: list[TriticeaePaper] = Field(default_factory=list)
