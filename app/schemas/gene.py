"""Schemas for gene-centric endpoints."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, EmailStr, Field


class DOIReference(BaseModel):
    """DOI plus optional title and publication year.

    ``doi`` is nullable because the v2056 curated data has one row with four
    titles but only three DOIs (the fourth reference has a title only).
    ``year`` was added for the structured references list; legacy rows keep
    returning ``None`` when no year is available.
    """

    doi: str | None = None
    title: str | None = None
    year: int | str | None = None


class KnownGeneSummary(BaseModel):
    """Known/cloned gene summary row.

    The first eight fields are the pre-v2056 contract and must never be
    removed or renamed.  ``clone_id``/``gene_id``/``gene_name``/``chrom_pos``/
    ``phenotype``/``species`` are kept verbatim because the legacy frontend and
    the CGI pages depend on them.
    """

    clone_id: int | str | None = None
    gene_id: str
    gene_name: str
    chrom_pos: str
    phenotype: str
    species: str
    publication_year: str | None = None
    dois: list[str] = Field(default_factory=list)
    # --- added for the v2056 curated dataset -------------------------------
    reference_genome_id: str | None = None
    species_primary: str | None = None
    chromosome: str | None = None
    genome_ref: str | None = None
    phenotype_brief: str | None = None
    functional_category: str | None = None
    research_strategy: str | None = None
    publication_years: list[str] = Field(default_factory=list)


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
    publication_year: int | str | None = None
    function_description: str | None = None
    cloning_method: str | None = None
    cloning_method_description: str | None = None
    author: str | None = None
    author_mail: str | None = None
    submission_date: date | str | None = None
    # --- added for the v2056 curated dataset -------------------------------
    reference_genome_id: str | None = None
    protein_family: str | None = None
    validation_method: str | None = None
    validation_methods: list[str] = Field(default_factory=list)
    research_strategy: str | None = None
    functional_category: str | None = None
    species_primary: str | None = None
    chromosome: str | None = None
    genome_ref: str | None = None
    phenotype_brief: str | None = None
    publication_years: list[int | str] = Field(default_factory=list)


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
    #: wheatPSP phase-separation summary, populated by gene.py from wheat_psp_db
    #: keys: any_psp, any_prd, transcripts[{seq_id, ps_score, is_psp,
    #: molphase_score, has_prd, plaac_llr, plaac_papa_prop}]. None when the gene
    #: has no wheatPSP records.
    phase_separation: dict | None = None


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
    chinese_spring_02g: str | None = None


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
