"""Schemas for Triticeae Research Filter paper database."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class TriticeaePaper(BaseModel):
    """A single paper entry from the functional_gene_annotations LEFT JOIN papers."""

    # -- from functional_gene_annotations --
    fga_id: int | None = None
    pubmedid: str | None = None
    fga_title: str | None = None
    is_functional_gene: bool | None = None
    confidence: float | None = None
    gene_name: list[str] = Field(default_factory=list)
    gene_type: str | None = None
    trait_label: str | None = None
    function_summary: str | None = None
    evidence_type: str | None = None
    new_tags: str | None = None
    llm_reason: str | None = None
    source_method: str | None = None
    review_status: str | None = None
    fga_created_at: str | None = None
    fga_updated_at: str | None = None
    fga_disease_gene_tags: str | None = None

    # -- from papers --
    paper_id: int | None = None
    pmid: str | None = None
    pub_date: str | None = None
    paper_title: str | None = None
    journal: str | None = None
    authors: str | None = None
    abstract: str | None = None
    pubmed_keywords: str | None = None
    ai_tags: str | None = None
    keywords_source: str | None = None
    link: str | None = None
    paper_created_at: str | None = None
    functional_gene_flag: str | None = None
    functional_gene_tags: str | None = None
    functional_gene_source: str | None = None
    paper_disease_gene_tags: str | None = None
    function_gene_flag: str | None = None
    function_gene_tags: str | None = None


class TriticeaeSearchResult(BaseModel):
    """Paginated search results."""

    total: int = 0
    limit: int = 20
    offset: int = 0
    papers: list[TriticeaePaper] = Field(default_factory=list)
