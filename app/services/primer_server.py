"""PrimerServer pipeline wrapper — replicates the full PrimerServer workflow for AI agent use.

Provides Pythonic wrappers around the deployed Perl pipeline scripts
(pipeline_design_check.pl, _run_specificity_check.pl) and parses
their structured output into JSON-friendly dicts.
"""

from __future__ import annotations

import csv
import io
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.schemas.tasks import PrimerCheckRequest, PrimerDesignRequest, PrimerGroupResult, PrimerJobResult


# ──────────────────────────────────────────────
#  Known genome/gene databases (from PrimerServer config)
# ──────────────────────────────────────────────

GENOME_DATABASES: dict[str, str] = {
    "primer_Chinese_Spring1.0.genome": "Chinese Spring genome v1.0",
    "primer_Chinese_Spring2.1.genome": "Chinese Spring genome v2.1",
    "primer_Chinese_Spring_Triticum_4.0.genome": "Chinese Spring genome Triticum 4.0",
    "CS-IAAS_T2T.genome": "Chinese Spring genome CS-IAAS_T2T",
    "primer_Fielder.genome": "Fielder genome",
    "primer_Zang1817.genome": "Zang1817 genome",
    "primer_Barley.genome": "Barley genome v1 (cv. Morex)",
    "primer_Barley2.genome": "Barley genome v2 (cv. Morex)",
    "primer_Barley3.genome": "Barley genome v3 (cv. Morex)",
    "primer_Wild_emmer.genome": "Wild emmer genome",
    "primer_Triticum_urartu.genome": "Triticum urartu genome v2.0 (cv. G1812)",
    "primer_tauschii_Luo.genome": "Aegilops tauschii genome (cv. AL8/78)",
    "primer_rye_weining.genome": "Rye genome (cv. Weining)",
    "primer_rye_Lo7.genome": "Rye genome (cv. Lo7)",
}

GENE_DATABASES: dict[str, str] = {
    "Chinese_Spring_gene": "Chinese Spring gene v1.0",
    "Chinese_springv2.1_HC_and_LC_mrna.fasta": "Chinese Spring gene v2.1",
    "IWGSC_v1.1_HC_LC_20170706_transcripts": "Chinese Spring gene v1.1",
    "Fielder_gene": "Fielder gene",
    "Barley_gene": "Barley gene v1 (cv. Morex)",
    "Wild_emmer_gene": "Wild emmer gene",
}


def list_primer_databases(category: str | None = None) -> list[dict[str, str]]:
    """Return available primer-design databases.

    Args:
        category: Filter by "genome", "gene", or None for all.

    Returns:
        List of {file_name, alias, category} dicts.
    """
    result: list[dict[str, str]] = []
    if category in (None, "genome"):
        for fname, alias in GENOME_DATABASES.items():
            result.append({"file_name": fname, "alias": alias, "category": "genome"})
    if category in (None, "gene"):
        for fname, alias in GENE_DATABASES.items():
            result.append({"file_name": fname, "alias": alias, "category": "gene"})
    return result


# ──────────────────────────────────────────────
#  Input file building
# ──────────────────────────────────────────────

def build_marker_input(markers: list[str]) -> str:
    """Convert marker CSV lines to the tab-delimited format expected by
    pipeline_design_check.pl.

    Input marker format: "chr,pos,SEQUENCE[/SNP]"
    Output format (tab-delimited): ID<TAB>FLANK_SEQUENCE
    """
    lines: list[str] = []
    for i, marker in enumerate(markers, 1):
        fields = marker.split(",")
        if len(fields) < 3:
            continue
        seq = fields[2]
        lines.append(f"marker_{i}\t{seq}")
    return "\n".join(lines)


def build_primer_check_input(primers: list[str]) -> str:
    """Build the input file for _run_specificity_check.pl.

    Each line: "ID [Rank] Seq1 Seq2 [Seq3 ...]"
    If no rank is detected the rank defaults to 0.
    """
    lines: list[str] = []
    for line in primers:
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        # Check whether second token is a numeric rank
        try:
            int(parts[1])
            lines.append(line)  # already fully-formed
        except (ValueError, IndexError):
            # No rank — insert 0
            lines.append(f"{parts[0]}\t0\t" + "\t".join(parts[1:]))
    return "\n".join(lines)


# ──────────────────────────────────────────────
#  Result parsing helpers
# ──────────────────────────────────────────────

def parse_specificity_result(result_path: Path) -> list[dict[str, Any]]:
    """Parse specificity.check.result.txt into structured records.

    Format:
    #Site_ID    Primer_Rank    Database    Possible_Amplicon_Number    Primer_Seqs
    marker_1    0    primer_Chinese_Spring1.0.genome    3    ATGC...
    """
    records: list[dict[str, Any]] = []
    if not result_path.exists():
        return records
    with open(result_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 5:
                records.append({
                    "site_id": parts[0],
                    "primer_rank": int(parts[1]),
                    "database": parts[2],
                    "amplicon_count": int(parts[3]),
                    "primer_seqs": parts[4].split(),
                })
    return records


def parse_amplicon_result(amplicon_path: Path) -> list[dict[str, Any]]:
    """Parse specificity.check.result.amplicon into structured records."""
    records: list[dict[str, Any]] = []
    if not amplicon_path.exists():
        return records
    with open(amplicon_path) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            records.append(dict(row))
    return records


# ──────────────────────────────────────────────
#  Pipeline runner
# ──────────────────────────────────────────────

def run_pipeline_design_check(
    job_dir: Path,
    input_text: str,
    template: str,
    checking_dbs: list[str],
    params: PrimerDesignRequest,
) -> PrimerJobResult:
    """Run the full pipeline_design_check.pl workflow.

    Args:
        job_dir: Working directory for the job.
        input_text: Tab-delimited input content.
        template: Genome database for template extraction.
        checking_dbs: List of genome FASTA databases for specificity checking.
        params: Full primer design parameters.

    Returns:
        PrimerJobResult with parsed output.
    """
    input_file = job_dir / "for_polymarker.csv"
    input_file.write_text(input_text)

    db_path = str(settings.BLAST_DB_PATH)
    template_path = f"{db_path}/{template}"
    checking_paths = ",".join(f"{db_path}/{d}" for d in checking_dbs)
    pipeline = str(settings.SNPRIMER_PIPELINE)

    # Build command matching pipeline_design_check.pl options
    cmd = [
        sys.executable, pipeline,
        "--input", str(input_file),
        "--template", template_path,
        "--checkingdb", checking_paths,
        "--samtools", str(settings.SAMTOOLS_PATH),
        "--blastn", str(settings.BLASTN_PATH),
        "--primer3bin", str(settings.PRIMER3_PATH),
        f"--product_size_min={params.product_size_min}",
        f"--product_size_max={params.product_size_max}",
        f"--primer_num_retain={params.primer_num_retain}",
        f"--checking_size_start={params.checking_size_start}",
        f"--checking_size_stop={params.checking_size_stop}",
        f"--blast_e_value={params.blast_e_value}",
        f"--blast_word_size={params.blast_word_size}",
        f"--blast_identity={params.blast_identity}",
        f"--blast_max_hsps={params.blast_max_hsps}",
        f"--conc_primer={params.primer_conc_nm}",
        f"--conc_Na={params.conc_na_mm}",
        f"--conc_K={params.conc_k_mm}",
        f"--conc_Tris={params.conc_tris_mm}",
        f"--conc_Mg={params.conc_mg_mm}",
        f"--conc_dNTPs={params.conc_dntp_mm}",
        f"--min_Tm_diff={params.min_tm_diff}",
        f"--max_report_amplicon={params.max_report_amplicon}",
        f"--num_cpu={params.num_cpu}",
        "--outputdir", str(job_dir),
    ]
    if params.use_3end_mismatch:
        cmd.append("--use_3end")

    subprocess.run(cmd, check=True, cwd=job_dir)

    # Parse results
    result_dir = job_dir / "PrimerServerOutput"
    specificity_file = result_dir / "specificity.check.result.txt"
    amplicon_file = result_dir / "specificity.check.result.amplicon"

    records = parse_specificity_result(specificity_file)
    amplicons = parse_amplicon_result(amplicon_file)

    groups: list[PrimerGroupResult] = []
    for rec in records:
        group_amplicons = [
            a for a in amplicons
            if a.get("ID") == rec["site_id"]
            and int(a.get("Rank", 0)) == rec["primer_rank"]
            and a.get("Database") == rec["database"]
        ]
        groups.append(PrimerGroupResult(
            site_id=rec["site_id"],
            primer_rank=rec["primer_rank"],
            database=rec["database"],
            amplicon_count=rec["amplicon_count"],
            primer_seqs=rec["primer_seqs"],
            is_unique=(rec["amplicon_count"] == 1),
            amplicons=group_amplicons,
        ))

    accepted, rejected = _validate_markers(params.markers)

    return PrimerJobResult(
        job_dir=str(job_dir),
        groups=groups,
        accepted_markers=accepted,
        rejected_markers=rejected,
        artifacts=_collect_artifacts(job_dir),
    )


def _validate_markers(markers: list[str]) -> tuple[list[str], list[str]]:
    """Basic marker validation — replicates PrimerServer frontend logic."""
    accepted: list[str] = []
    rejected: list[str] = []
    for marker in markers:
        fields = marker.split(",")
        if len(fields) != 3:
            rejected.append(marker)
            continue
        seq = fields[2].upper()
        if (seq.count("[") == 1 and seq.count("]") == 1
                and seq.count("/") == 1
                and sum(seq.count(b) for b in "ATCGN") >= len(seq) - 3):
            accepted.append(marker)
        else:
            rejected.append(marker)
    return accepted, rejected


def _collect_artifacts(job_dir: Path) -> list[dict[str, str]]:
    """Gather output artifacts from the job directory."""
    artifacts: list[dict[str, str]] = []
    for path in job_dir.rglob("*"):
        if path.is_file() and path.stat().st_size > 0:
            rel = path.relative_to(job_dir)
            artifacts.append({"file_name": str(rel), "path": str(path)})
    return artifacts


# ──────────────────────────────────────────────
#  Check-only runner
# ──────────────────────────────────────────────

def run_specificity_check(
    job_dir: Path,
    input_text: str,
    checking_dbs: list[str],
    params: PrimerCheckRequest,
) -> PrimerJobResult:
    """Run the _run_specificity_check.pl workflow.

    Args:
        job_dir: Working directory for the job.
        input_text: Formatted primer input.
        checking_dbs: List of genome FASTA databases.
        params: Specificity check parameters.

    Returns:
        PrimerJobResult with parsed output.
    """
    input_file = job_dir / "primer_input.txt"
    input_file.write_text(input_text)

    db_path = str(settings.BLAST_DB_PATH)
    checking_paths = ",".join(f"{db_path}/{d}" for d in checking_dbs)
    check_script = settings.SNPRIMER_PIPELINE.parent / "_run_specificity_check.pl"

    cmd = [
        sys.executable, str(check_script),
        "--input", str(input_file),
        "--db", checking_paths,
        "--samtools", str(settings.SAMTOOLS_PATH),
        "--blastn", str(settings.BLASTN_PATH),
        f"--size_start={params.checking_size_start}",
        f"--size_stop={params.checking_size_stop}",
        f"--blast_e_value={params.blast_e_value}",
        f"--blast_word_size={params.blast_word_size}",
        f"--blast_identity={params.blast_identity}",
        f"--blast_max_hsps={params.blast_max_hsps}",
        f"--conc_primer={params.primer_conc_nm}",
        f"--conc_Na={params.conc_na_mm}",
        f"--conc_K={params.conc_k_mm}",
        f"--conc_Tris={params.conc_tris_mm}",
        f"--conc_Mg={params.conc_mg_mm}",
        f"--conc_dNTPs={params.conc_dntp_mm}",
        f"--min_Tm_diff={params.min_tm_diff}",
        f"--max_report_amplicon={params.max_report_amplicon}",
        f"--num_cpu={params.num_cpu}",
        "--outputdir", str(job_dir),
    ]
    if params.use_3end_mismatch:
        cmd.append("--use_3end")

    subprocess.run(cmd, check=True, cwd=job_dir)

    result_dir = job_dir / "PrimerServerOutput"
    specificity_file = result_dir / "specificity.check.result.txt"
    amplicon_file = result_dir / "specificity.check.result.amplicon"

    records = parse_specificity_result(specificity_file)
    amplicons = parse_amplicon_result(amplicon_file)

    groups: list[PrimerGroupResult] = []
    for rec in records:
        group_amplicons = [
            a for a in amplicons
            if a.get("ID") == rec["site_id"]
            and int(a.get("Rank", 0)) == rec["primer_rank"]
            and a.get("Database") == rec["database"]
        ]
        groups.append(PrimerGroupResult(
            site_id=rec["site_id"],
            primer_rank=rec["primer_rank"],
            database=rec["database"],
            amplicon_count=rec["amplicon_count"],
            primer_seqs=rec["primer_seqs"],
            is_unique=(rec["amplicon_count"] == 1),
            amplicons=group_amplicons,
        ))

    return PrimerJobResult(
        job_dir=str(job_dir),
        groups=groups,
        artifacts=_collect_artifacts(job_dir),
    )
