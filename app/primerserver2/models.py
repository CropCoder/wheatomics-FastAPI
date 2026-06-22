import re
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class RegionType(str, Enum):
    SEQUENCE_TARGET = "SEQUENCE_TARGET"
    SEQUENCE_INCLUDED_REGION = "SEQUENCE_INCLUDED_REGION"
    FORCE_END = "FORCE_END"


class JobType(str, Enum):
    DESIGN = "design"
    CHECK = "check"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    STOPPED = "stopped"


class ConfigResponse(BaseModel):
    limitSite: int
    limitPrimer: int
    limitDatabase: int
    useCPU: int
    showInfo: bool
    removeTmp: bool


class DatabaseGroup(BaseModel):
    name: str
    databases: Dict[str, str]


class DatabasesResponse(BaseModel):
    groups: List[DatabaseGroup]


class ServerInfoResponse(BaseModel):
    currentTime: Optional[str] = None
    cpuInfo: Optional[str] = None
    memTotal: Optional[str] = None
    memFree: Optional[str] = None
    samtoolsVersion: Optional[str] = None
    blastnVersion: Optional[str] = None
    primer3Version: Optional[str] = None


# Maximum input sizes to prevent abuse / excessive disk usage.
MAX_TEMPLATE_REGIONS_LEN = 10_000
MAX_FASTA_LEN = 5_000_000
MAX_CHECK_PRIMERS_LEN = 500_000
MAX_PRIMER3_SETTINGS_LEN = 50_000

_FASTA_HEADER_RE = re.compile(r"^>\S+")
_TEMPLATE_REGION_LINE_RE = re.compile(r"^\S+\s+\d+\s+\d+(\s+\d+\s+\d+)?\s*$")


class SpecificityParams(BaseModel):
    """Shared specificity-checking parameters for both design and check jobs."""

    sizeStart: int = Field(
        default=50,
        alias="size_start",
        ge=1,
        le=100_000,
        description="Minimum allowed amplicon size (bp) during specificity checking.",
    )
    sizeStop: int = Field(
        default=5000,
        alias="size_stop",
        ge=1,
        le=1_000_000,
        description="Maximum allowed amplicon size (bp) during specificity checking.",
    )
    minTmDiff: int = Field(
        default=20,
        alias="min_Tm_diff",
        ge=0,
        le=100,
        description="Minimum Tm difference (°C) required to keep a non-specific amplicon.",
    )
    retain: int = Field(
        default=10,
        ge=1,
        le=1000,
        description="Maximum number of primer pairs to return per site.",
    )
    end3MismatchThreshold: int = Field(
        default=5,
        alias="end3_mismatch_threshold",
        ge=0,
        le=5,
        description="Maximum mismatches allowed in the last 5 bp of the 3' end. "
                    "Use 5 to disable strict filtering (legacy behavior).",
    )
    maxReportAmplicon: int = Field(
        default=50,
        alias="max_report_amplicon",
        ge=1,
        le=10_000,
        description="Maximum number of amplicons reported per primer pair in specificity check.",
    )
    blastEValue: int = Field(
        default=30000,
        alias="blast_e_value",
        ge=1,
        description="BLAST e-value threshold for primer-to-database alignment.",
    )
    blastWordSize: int = Field(
        default=7,
        alias="blast_word_size",
        ge=4,
        le=11,
        description="BLAST word size for short primer sequences.",
    )
    blastIdentity: int = Field(
        default=60,
        alias="blast_identity",
        ge=0,
        le=100,
        description="Minimum BLAST identity (%) for a primer hit to be considered.",
    )
    blastMaxHsps: int = Field(
        default=500,
        alias="blast_max_hsps",
        ge=1,
        description="Maximum BLAST HSPs retained per primer query.",
    )

    # Ion concentrations
    concPrimer: float = Field(default=100.0, alias="conc_primer", ge=0, description="Primer concentration (nM).")
    concDntps: float = Field(default=0.2, alias="conc_dNTPs", ge=0, description="dNTP concentration (mM).")
    concNa: float = Field(default=0.0, alias="conc_Na", ge=0, description="Sodium ion concentration (mM).")
    concK: float = Field(default=50.0, alias="conc_K", ge=0, description="Potassium ion concentration (mM).")
    concTris: float = Field(default=10.0, alias="conc_Tris", ge=0, description="Tris buffer concentration (mM).")
    concMg: float = Field(default=1.5, alias="conc_Mg", ge=0, description="Magnesium ion concentration (mM).")

    # Databases
    selectedDatabases: List[str] = Field(
        default_factory=list,
        alias="selected-databases",
        description="List of database file names to check specificity against. "
                    "Use 'custom' together with customDbSequences for a custom FASTA database.",
    )
    customDbSequences: Optional[str] = Field(
        default=None,
        alias="custom-db-sequences",
        description="Custom database sequences in FASTA format. Only used when 'custom' is in selectedDatabases.",
    )

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("selectedDatabases", mode="before")
    @classmethod
    def split_databases(cls, v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v or []

    @field_validator("sizeStop")
    @classmethod
    def size_stop_gte_start(cls, v, info: ValidationInfo):
        if "sizeStart" in info.data and v < info.data["sizeStart"]:
            raise ValueError("size_stop must be greater than or equal to size_start")
        return v

    @field_validator("selectedDatabases")
    @classmethod
    def databases_not_empty(cls, v):
        if not v:
            raise ValueError("At least one database must be selected")
        return v

    @field_validator("customDbSequences")
    @classmethod
    def validate_custom_db(cls, v, info: ValidationInfo):
        if v == "":
            return None
        if v is not None:
            if len(v) > MAX_FASTA_LEN:
                raise ValueError(f"customDbSequences exceeds {MAX_FASTA_LEN} characters")
            if "custom" not in info.data.get("selectedDatabases", []):
                raise ValueError("customDbSequences provided but 'custom' database not selected")
            _validate_fasta(v, "customDbSequences")
        return v


class DesignJobRequest(SpecificityParams):
    """Request body for submitting a primer design & specificity-check job."""

    appType: JobType = Field(..., alias="app-type", description="Must be 'design'.")
    selectTemplate: str = Field(
        ...,
        description="Template database name (e.g. 'chinese_spring_v2.1.fa') or 'custom'.",
    )
    templateRegions: Optional[str] = Field(
        default=None,
        alias="template-regions",
        description="One region per line: TemplateID TargetPos TargetLength [ProductSizeMin] [ProductSizeMax]. "
                    "Required unless selectTemplate is 'custom'.",
    )
    customTemplateSequences: Optional[str] = Field(
        default=None,
        alias="custom-template-sequences",
        description="Template sequences in FASTA format. Required when selectTemplate is 'custom'.",
    )
    regionType: RegionType = Field(
        default=RegionType.SEQUENCE_TARGET,
        alias="region_type",
        description="How to interpret the target region.",
    )
    productSizeMin: int = Field(default=100, alias="product_size_min", ge=30, le=50_000, description="Minimum desired product size (bp).")
    productSizeMax: int = Field(default=1000, alias="product_size_max", ge=30, le=50_000, description="Maximum desired product size (bp).")

    # Primer3 settings
    PRIMER_MIN_SIZE: int = Field(default=18, ge=1, le=35, description="Minimum primer length (bp).")
    PRIMER_OPT_SIZE: int = Field(default=20, ge=1, le=35, description="Optimal primer length (bp).")
    PRIMER_MAX_SIZE: int = Field(default=23, ge=1, le=35, description="Maximum primer length (bp).")
    PRIMER_MIN_GC: float = Field(default=35.0, ge=0, le=100, description="Minimum GC content (%).")
    PRIMER_OPT_GC_PERCENT: float = Field(default=50.0, ge=0, le=100, description="Optimal GC content (%).")
    PRIMER_MAX_GC: float = Field(default=65.0, ge=0, le=100, description="Maximum GC content (%).")
    PRIMER_MIN_TM: float = Field(default=57.0, ge=0, le=100, description="Minimum melting temperature (°C).")
    PRIMER_OPT_TM: float = Field(default=60.0, ge=0, le=100, description="Optimal melting temperature (°C).")
    PRIMER_MAX_TM: float = Field(default=63.0, ge=0, le=100, description="Maximum melting temperature (°C).")
    PRIMER_PAIR_MAX_DIFF_TM: float = Field(default=3.0, ge=0, description="Maximum Tm difference between left and right primers (°C).")
    PRIMER_NUM_RETURN: int = Field(default=30, ge=1, le=1000, description="Number of candidate primer pairs designed by Primer3 per site.")
    PRIMER_MIN_LEFT_THREE_PRIME_DISTANCE: int = Field(default=3, ge=-1, le=10, description="Primer3 LEFT_THREE_PRIME_DISTANCE.")
    PRIMER_MIN_RIGHT_THREE_PRIME_DISTANCE: int = Field(default=3, ge=-1, le=10, description="Primer3 RIGHT_THREE_PRIME_DISTANCE.")
    PRIMER_MAX_END_STABILITY: float = Field(default=9.0, ge=0, description="Maximum 3' end stability.")
    PRIMER_LOWERCASE_MASKING: int = Field(default=0, ge=0, le=1, description="Treat lowercase sequence as masked (0=no, 1=yes).")
    PRIMER_MAX_SELF_ANY_TH: float = Field(default=45.0, ge=0, description="Maximum self-complementarity (any).")
    PRIMER_PAIR_MAX_COMPL_ANY_TH: float = Field(default=45.0, ge=0, description="Maximum pair complementarity (any).")
    PRIMER_MAX_SELF_END_TH: float = Field(default=35.0, ge=0, description="Maximum self-complementarity at 3' end.")
    PRIMER_PAIR_MAX_COMPL_END_TH: float = Field(default=35.0, ge=0, description="Maximum pair complementarity at 3' end.")
    PRIMER_MAX_HAIRPIN_TH: float = Field(default=24.0, ge=0, description="Maximum hairpin stability.")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "app-type": "design",
                "selectTemplate": "primer_Chinese_Spring2.1.genome",
                "template-regions": "chr1A 100000 200\nchr1B 200000 300 150 800",
                "region_type": "SEQUENCE_TARGET",
                "product_size_min": 150,
                "product_size_max": 800,
                "PRIMER_MIN_SIZE": 18,
                "PRIMER_OPT_SIZE": 20,
                "PRIMER_MAX_SIZE": 23,
                "PRIMER_MIN_TM": 57,
                "PRIMER_OPT_TM": 60,
                "PRIMER_MAX_TM": 63,
                "PRIMER_NUM_RETURN": 30,
                "size_start": 50,
                "size_stop": 5000,
                "min_Tm_diff": 20,
                "end3_mismatch_threshold": 5,
                "retain": 10,
                "blast_e_value": 30000,
                "blast_word_size": 7,
                "blast_identity": 60,
                "selected-databases": ["primer_Chinese_Spring2.1.genome"],
            }
        },
    )

    @field_validator("productSizeMax")
    @classmethod
    def product_size_max_gte_min(cls, v, info: ValidationInfo):
        if "productSizeMin" in info.data and v < info.data["productSizeMin"]:
            raise ValueError("product_size_max must be greater than or equal to product_size_min")
        return v

    @field_validator("PRIMER_MAX_SIZE")
    @classmethod
    def primer_size_order(cls, v, info: ValidationInfo):
        min_size = info.data.get("PRIMER_MIN_SIZE")
        opt_size = info.data.get("PRIMER_OPT_SIZE")
        if min_size is not None and v < min_size:
            raise ValueError("PRIMER_MAX_SIZE must be >= PRIMER_MIN_SIZE")
        if opt_size is not None and (opt_size < min_size or opt_size > v):
            raise ValueError("PRIMER_OPT_SIZE must be between PRIMER_MIN_SIZE and PRIMER_MAX_SIZE")
        return v

    @field_validator("PRIMER_MAX_TM")
    @classmethod
    def primer_tm_order(cls, v, info: ValidationInfo):
        min_tm = info.data.get("PRIMER_MIN_TM")
        opt_tm = info.data.get("PRIMER_OPT_TM")
        if min_tm is not None and v < min_tm:
            raise ValueError("PRIMER_MAX_TM must be >= PRIMER_MIN_TM")
        if opt_tm is not None and (opt_tm < min_tm or opt_tm > v):
            raise ValueError("PRIMER_OPT_TM must be between PRIMER_MIN_TM and PRIMER_MAX_TM")
        return v

    @field_validator("PRIMER_MAX_GC")
    @classmethod
    def primer_gc_order(cls, v, info: ValidationInfo):
        min_gc = info.data.get("PRIMER_MIN_GC")
        opt_gc = info.data.get("PRIMER_OPT_GC_PERCENT")
        if min_gc is not None and v < min_gc:
            raise ValueError("PRIMER_MAX_GC must be >= PRIMER_MIN_GC")
        if opt_gc is not None and (opt_gc < min_gc or opt_gc > v):
            raise ValueError("PRIMER_OPT_GC_PERCENT must be between PRIMER_MIN_GC and PRIMER_MAX_GC")
        return v

    @field_validator("selectTemplate")
    @classmethod
    def template_selected(cls, v):
        if not v or not v.strip():
            raise ValueError("selectTemplate is required")
        return v.strip()

    @field_validator("templateRegions")
    @classmethod
    def validate_template_regions(cls, v, info: ValidationInfo):
        select_template = info.data.get("selectTemplate")
        if select_template == "custom":
            if v == "":
                return None
            return v
        if v == "":
            raise ValueError("templateRegions is required when using a built-in template")
        if v is None or not v.strip():
            raise ValueError("templateRegions is required when using a built-in template")
        if len(v) > MAX_TEMPLATE_REGIONS_LEN:
            raise ValueError(f"templateRegions exceeds {MAX_TEMPLATE_REGIONS_LEN} characters")
        _validate_template_regions(v)
        return v

    @field_validator("customTemplateSequences")
    @classmethod
    def validate_custom_template(cls, v, info: ValidationInfo):
        if v == "":
            return None
        if v is not None:
            if len(v) > MAX_FASTA_LEN:
                raise ValueError(f"customTemplateSequences exceeds {MAX_FASTA_LEN} characters")
            if info.data.get("selectTemplate") != "custom":
                raise ValueError("customTemplateSequences provided but selectTemplate is not 'custom'")
            _validate_fasta(v, "customTemplateSequences")
        return v


class CheckJobRequest(SpecificityParams):
    """Request body for submitting a primer specificity-check-only job."""

    appType: JobType = Field(..., alias="app-type", description="Must be 'check'.")
    checkPrimers: str = Field(
        ...,
        alias="check-primers",
        description="One primer group per line: PrimerID LeftSeq RightSeq [AdditionalSeq ...].",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "app-type": "check",
                "check-primers": "Primer1 TTCGATGCTGAGGAAGGCTG AGGAGAGAACGGAGACGAAG\nPrimer2 AGGAGAGAACGGAGACGAAG TTCGATGCTGAGGAAGGCTG",
                "size_start": 50,
                "size_stop": 5000,
                "min_Tm_diff": 20,
                "end3_mismatch_threshold": 5,
                "retain": 10,
                "blast_e_value": 30000,
                "blast_word_size": 7,
                "blast_identity": 60,
                "selected-databases": ["primer_Chinese_Spring2.1.genome"],
            }
        },
    )

    @field_validator("checkPrimers")
    @classmethod
    def validate_check_primers(cls, v):
        if not v or not v.strip():
            raise ValueError("checkPrimers is required")
        if len(v) > MAX_CHECK_PRIMERS_LEN:
            raise ValueError(f"checkPrimers exceeds {MAX_CHECK_PRIMERS_LEN} characters")
        _validate_check_primers(v)
        return v


class JobResponse(BaseModel):
    """Response returned when a job is created or queried by ID."""

    jobId: str = Field(..., description="Unique job identifier (UUID).")
    status: JobStatus = Field(..., description="Current job status.")
    createdAt: str = Field(..., description="ISO 8601 timestamp when the job was created.")
    message: Optional[str] = Field(default=None, description="Human-readable status message.")


class ProgressResponse(BaseModel):
    """Progress information for a running or finished job."""

    total: int = Field(..., description="Total number of work units.")
    finished: int = Field(..., description="Number of completed work units.")
    percent: int = Field(..., description="Completion percentage (0-100).")
    stage: str = Field(..., description="Current pipeline stage description.")


class PrimerResult(BaseModel):
    """A single designed primer pair with thermodynamic and specificity details."""

    siteId: str = Field(..., description="Input site / primer group identifier.")
    rank: int = Field(..., description="Final rank after specificity filtering (1-based).")
    leftSeq: str = Field(..., description="Left primer sequence (5' -> 3').")
    rightSeq: str = Field(..., description="Right primer sequence (5' -> 3').")
    productSize: int = Field(..., description="Expected PCR product size (bp).")
    penalty: float = Field(..., description="Primer3 penalty score (lower is better).")
    leftTm: Optional[float] = Field(default=None, description="Left primer melting temperature (°C).")
    rightTm: Optional[float] = Field(default=None, description="Right primer melting temperature (°C).")
    leftGc: Optional[float] = Field(default=None, description="Left primer GC content (%).")
    rightGc: Optional[float] = Field(default=None, description="Right primer GC content (%).")
    leftPos: Optional[str] = Field(default=None, description="Left primer alignment position, e.g. 'chr1A:100025-100042 (+)'.")
    rightPos: Optional[str] = Field(default=None, description="Right primer alignment position, e.g. 'chr1A:100824-100841 (-)'.")
    leftLen: Optional[int] = Field(default=None, description="Left primer length (bp).")
    rightLen: Optional[int] = Field(default=None, description="Right primer length (bp).")
    leftSelfAny: Optional[float] = Field(default=None, description="Left primer self-complementarity (any).")
    rightSelfAny: Optional[float] = Field(default=None, description="Right primer self-complementarity (any).")
    leftSelfEnd: Optional[float] = Field(default=None, description="Left primer self-complementarity at 3' end.")
    rightSelfEnd: Optional[float] = Field(default=None, description="Right primer self-complementarity at 3' end.")
    leftHairpin: Optional[float] = Field(default=None, description="Left primer hairpin stability.")
    rightHairpin: Optional[float] = Field(default=None, description="Right primer hairpin stability.")
    leftEndStability: Optional[float] = Field(default=None, description="Left primer 3' end stability.")
    rightEndStability: Optional[float] = Field(default=None, description="Right primer 3' end stability.")
    pairComplAny: Optional[float] = Field(default=None, description="Pair complementarity (any).")
    pairComplEnd: Optional[float] = Field(default=None, description="Pair complementarity at 3' end.")
    primer3Rank: Optional[int] = Field(default=None, description="Original Primer3 rank before specificity filtering.")
    databases: List[Dict] = Field(..., description="Specificity-check results per database (amplicons, alignments, etc.).")


class CheckResult(BaseModel):
    """Specificity-check result for one primer group against one database."""

    siteId: str = Field(..., description="Primer group identifier.")
    rank: int = Field(..., description="Primer pair rank (1-based).")
    database: str = Field(..., description="Database name used for the check.")
    ampliconNumber: int = Field(..., description="Total number of amplicons found.")
    primerSeqs: List[str] = Field(..., description="Input primer sequences.")


class JobResultResponse(BaseModel):
    """Final result of a primer design or specificity-check job."""

    jobId: str = Field(..., description="Unique job identifier.")
    jobType: str = Field(..., description="'design' or 'check'.")
    status: JobStatus = Field(..., description="Final job status.")
    html: Optional[str] = Field(default=None, description="URL/path to legacy HTML result when available.")
    designPrimers: Optional[List[PrimerResult]] = Field(default=None, description="Designed primer pairs (design jobs).")
    checkResults: Optional[List[CheckResult]] = Field(default=None, description="Specificity check summaries (check jobs).")
    error: Optional[str] = Field(default=None, description="Error message if the job failed.")


def _validate_fasta(value: str, field_name: str) -> None:
    """Basic FASTA format validation."""
    lines = value.splitlines()
    if not lines:
        raise ValueError(f"{field_name} is empty")
    if not any(line.startswith(">") for line in lines):
        raise ValueError(f"{field_name} is not in FASTA format (missing '>' header)")
    sequence_started = False
    for line in lines:
        if not line.strip():
            continue
        if line.startswith(">"):
            sequence_started = True
            continue
        if not sequence_started:
            raise ValueError(f"{field_name}: sequence appears before any FASTA header")
        if not re.match(r"^[ACGTURYKMSWBDHVNacgturykmswbdhvn]*$", line):
            raise ValueError(f"{field_name}: invalid FASTA sequence characters")


def _validate_template_regions(value: str) -> None:
    """Validate template regions format."""
    lines = value.splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not _TEMPLATE_REGION_LINE_RE.match(line):
            raise ValueError(
                "Invalid template region line. Expected: TemplateID TargetPos TargetLength "
                "[ProductSizeMin] [ProductSizeMax]"
            )


def _validate_check_primers(value: str) -> None:
    """Validate check-primers format."""
    lines = value.splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3:
            raise ValueError(
                "Invalid check-primers line. Expected: PrimerID Seq1 Seq2 ..."
            )
