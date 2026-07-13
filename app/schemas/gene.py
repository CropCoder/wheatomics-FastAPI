"""Schemas for gene-centric endpoints."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, EmailStr, Field


class DOIReference(BaseModel):
    """DOI plus optional title."""

    doi: str
    title: str | None = None


class KnownGeneSummary(BaseModel):
    """Known/cloned gene summary row."""

    clone_id: int | str | None = None
    gene_id: str
    gene_name: str
    chrom_pos: str
    phenotype: str
    species: str
    publication_year: str | None = None
    dois: list[str] = Field(default_factory=list)


class KnownGeneDetail(BaseModel):
    """Full cloned_gene_tbl record in normalized form."""

    clone_id: int | str
    gene_id: str
    gene_name: str
    chrom_pos: str
    phenotype: str
    species: str
    paper_title: list[str] = Field(default_factory=list)
    references: list[DOIReference] = Field(default_factory=list)
    key_result: list[str] = Field(default_factory=list)
    publication_year: str | None = None
    function_description: str | None = None
    cloning_method: str | None = None
    cloning_method_description: str | None = None
    author: str | None = None
    author_mail: str | None = None
    submission_date: date | str | None = None


class GeneDetailResponse(BaseModel):
    """Normalized gene detail record."""

    query_gene: str
    gene_ids: list[str]
    description: str | None = None
    genome: str | None = None
    chromosome: str | None = None
    start: int | None = None
    end: int | None = None
    strand: str | None = None
    protein_length: str | None = None
    molecular_weight: str | None = None
    isoelectric_point: str | None = None
    functions: list[str] = Field(default_factory=list)
    jbrowse_links: dict[str, str] = Field(default_factory=dict)
    external_links: dict[str, str] = Field(default_factory=dict)


class GeneFunctionRecord(BaseModel):
    """Functional annotation row."""

    chromosome: str
    start_mb: float
    end_mb: float
    gene_primary: str
    gene_secondary: str | None = None
    strand: str | None = None
    description: str | None = None
    domain: str | None = None


class GeneSubmissionRequest(BaseModel):
    """Known gene submission/update payload."""

    gene_id: str
    gene_name: str
    chrom_pos: str
    phenotype: str
    gene_species: str
    paper_title: str
    paper_doi: str
    key_result: str
    author: str
    author_mail: EmailStr
    password: str


class GeneUpdateRequest(GeneSubmissionRequest):
    """Known gene update payload."""

    clone_id: int
