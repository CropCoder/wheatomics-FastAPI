"""Schemas for Triticeae Research Filter paper database."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class TriticeaePaper(BaseModel):
    """Full functional-gene annotation of one paper
    (functional_gene_annotations LEFT JOIN papers)."""

    # ===== functional_gene_annotations 表 (f.) — AI/人工标注层 =====
    # 这一层记录的是"这篇论文被 AI 标注为什么"，是核心标注产出

    fga_id: int | None = None
    """Annotation record ID (functional_gene_annotations.id)"""

    pubmedid: str | None = None
    """PubMed unique identifier (f.pubmedid), used to link the papers table"""

    fga_title: str | None = None
    """Snapshot of the paper title at annotation time (f.title); may differ slightly from papers.title"""

    is_functional_gene: bool | None = None
    """AI verdict on whether this is a functional gene (1=yes, 0=no); core filter field"""

    confidence: float | None = None
    """AI confidence (0~1); higher means more reliable"""

    gene_name: list[str] = Field(default_factory=list)
    """List of functional gene names mentioned in the paper, e.g. ["TaCPK-1", "TaCDPK2"]"""

    gene_type: str | None = None
    """Gene type label, e.g. known_positive_by_seed_title (positive seed sample), nlr, rlp, etc."""

    trait_label: str | None = None
    """Trait label, e.g. stripe_rust, heat_tolerance, yield; the agronomic trait involved"""

    function_summary: str | None = None
    """Brief textual rationale for the functional gene verdict"""

    evidence_type: str | None = None
    """Evidence type, e.g. seed_title_match (title match), llm_determined (LLM verdict)"""

    new_tags: str | None = None
    """Newly annotated tags (JSON array string)"""

    llm_reason: str | None = None
    """Detailed LLM reasoning behind the functional gene verdict (natural language)"""

    source_method: str | None = None
    """Annotation source method, e.g. seed_title_match (seed title match), llm_review (LLM re-review)"""

    review_status: str | None = None
    """Review status: auto_pass (automatic pass), pending_review (awaiting manual review), etc."""

    fga_created_at: str | None = None
    """Annotation record creation time (f.created_at), i.e. when the paper was first annotated by AI"""

    fga_updated_at: str | None = None
    """Annotation record last update time (f.updated_at), i.e. when the AI re-judged it or a human edited it"""

    fga_disease_gene_tags: str | None = None
    """Disease/resistance gene tags (JSON string)"""

    # ===== papers 表 (p.) — 论文元数据层 =====
    # 这一层记录的是"这篇论文本身的基本信息"，来自 PubMed 导入

    paper_id: int | None = None
    """Paper metadata record ID (papers.id)"""

    pmid: str | None = None
    """PubMed ID (p.pmid), equal to pubmedid; used for cross-table joins"""

    pub_date: str | None = None
    """Publication date, e.g. 2024 Jun or 2024 Jun 15"""

    paper_title: str | None = None
    """Full paper title from PubMed (p.title)"""

    journal: str | None = None
    """Journal name, e.g. 3 Biotech, BMC Plant Biol"""

    authors: str | None = None
    """Author list string"""

    abstract: str | None = None
    """Full paper abstract"""

    pubmed_keywords: str | None = None
    """Keyword list supplied by PubMed (semicolon-separated)"""

    ai_tags: str | None = None
    """AI-generated paper tags (automatic tagging), semicolon- or space-separated"""

    keywords_source: str | None = None
    """Keyword source marker: ai_generated (AI-generated), pubmed (native PubMed), mixed (mixed)"""

    link: str | None = None
    """Link to the PubMed record"""

    doi: str | None = None
    """DOI (papers.doi, maintained by the weekly import/backfill script)"""

    paper_created_at: str | None = None
    """Time the paper metadata was first imported into WheatOmics (p.created_at)"""

    functional_gene_flag: str | None = None
    """Paper-level functional gene flag (1/0/empty), similar to is_functional_gene but annotated independently"""

    functional_gene_tags: str | None = None
    """Paper-level functional gene name tags, e.g. TaCPK-1 (single/multiple genes, comma-separated)"""

    functional_gene_source: str | None = None
    """Source of the paper-level functional gene annotation, e.g. seed_title_match"""

    paper_disease_gene_tags: str | None = None
    """Paper-level disease/resistance gene tags (JSON string)"""

    function_gene_flag: str | None = None
    """[Backup] Functional gene flag (second annotation scheme; temporarily stores results of the new method)"""

    function_gene_tags: str | None = None
    """[Backup] Functional gene tags (second annotation scheme, corresponding to function_gene_flag)"""


class TriticeaeSearchResult(BaseModel):
    """Paginated search result."""

    total: int = 0
    """Total number of matching papers"""
    limit: int = 20
    """Number of results per page (default 20, max 200)"""
    offset: int = 0
    """Pagination offset"""
    papers: list[TriticeaePaper] = Field(default_factory=list)
    """Papers on the current page"""
