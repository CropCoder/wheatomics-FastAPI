"""Schemas for task-like bioinformatics workflows."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
#  Primer Design Request / Response
# ──────────────────────────────────────────────

class PrimerDesignRequest(BaseModel):
    """Full-featured primer design request matching PrimerServer capabilities.

    Mimics the PrimerServer pipeline_design_check.pl interface for AI agent use.
    """

    # ── Required ──
    markers: list[str] = Field(
        ...,
        description='Marker lines, each: "chr,pos,SEQUENCE[/SNP]". '
        'Example: "chr5A,587123456,ATGCNNN[A/G]TGCANNN"',
    )
    template: str = Field(
        ...,
        description='Genome database for template region extraction. '
        'Corresponds to a FASTA file (indexed by makeblastdb) in the BLAST database directory. '
        'Example: "Chinese_Spring_v2.1_chromosomes"',
    )

    # ── Primer3 Settings ──
    product_size_min: int = 100
    product_size_max: int = 1000
    primer_num_retain: int = 10
    ploidy: str = "allohexaploid"
    price: str = "3"
    caps: bool = True
    kasp: bool = True
    primer_tm: str = "60"
    pick: str = "1"

    # ── Specificity Checking ──
    checking_dbs: list[str] = Field(
        default_factory=lambda: ["primer_Chinese_Spring1.0.genome"],
        description='One or more genome FASTA databases (comma-separated) for specificity '
        'checking. The first database is treated as the primary reference for uniqueness '
        'judgment.',
    )
    checking_size_start: int = 50
    checking_size_stop: int = 5000
    min_tm_diff: float = 20
    max_report_amplicon: int = 50
    use_3end_mismatch: bool = False

    # ── BLAST Settings ──
    blast_e_value: float = 30000
    blast_word_size: int = 7
    blast_identity: float = 60
    blast_max_hsps: int = 500

    # ── Ionic Concentration (Tm calculation) ──
    primer_conc_nm: float = 100
    conc_na_mm: float = 0
    conc_k_mm: float = 50
    conc_tris_mm: float = 10
    conc_mg_mm: float = 1.5
    conc_dntp_mm: float = 0.2

    # ── System ──
    num_cpu: int = 4


class PrimerCheckRequest(BaseModel):
    """Specificity-check-only request for already-designed primers.

    Mimics the PrimerServer _run_specificity_check.pl interface.
    """

    primers: list[str] = Field(
        ...,
        description='Primer group lines, each: "ID [Rank] Seq1 Seq2 [Seq3 ...]". '
        'Rank is optional; if omitted defaults to 0.',
    )
    checking_dbs: list[str] = Field(
        ...,
        description='One or more genome FASTA databases for specificity checking.',
    )
    checking_size_start: int = 50
    checking_size_stop: int = 5000
    min_tm_diff: float = 20
    max_report_amplicon: int = 50
    use_3end_mismatch: bool = False
    blast_e_value: float = 30000
    blast_word_size: int = 7
    blast_identity: float = 60
    blast_max_hsps: int = 500
    primer_conc_nm: float = 100
    conc_na_mm: float = 0
    conc_k_mm: float = 50
    conc_tris_mm: float = 10
    conc_mg_mm: float = 1.5
    conc_dntp_mm: float = 0.2
    num_cpu: int = 4


class PrimerGroupResult(BaseModel):
    """Structured result for one primer group at one checking database."""

    site_id: str
    primer_rank: int
    database: str
    amplicon_count: int
    primer_seqs: list[str]
    is_unique: bool = False
    amplicons: list[dict] = Field(default_factory=list)


class PrimerJobResult(BaseModel):
    """Full structured result from a primer design/check job."""

    job_dir: str
    status: str = "completed"
    groups: list[PrimerGroupResult] = Field(default_factory=list)
    accepted_markers: list[str] = Field(default_factory=list)
    rejected_markers: list[str] = Field(default_factory=list)
    artifacts: list[dict] = Field(default_factory=list)


class PrimerDatabase(BaseModel):
    """Available primer design database entry."""

    file_name: str
    alias: str
    category: str  # "genome" or "gene"


# ── Legacy / Kept for backwards compatibility ──

class TaskArtifact(BaseModel):
    """Output artifact reference."""

    file_name: str
    path: str
