"""Main design pipeline for PrimerServer2 (Python replacement for
pipeline_design_check.pl).

Orchestrates primer design, specificity checking, and final selection.
"""

import shutil
from pathlib import Path
from typing import Optional, TextIO

from . import primer3_runner, selection_runner, specificity_runner
from .progress import log_progress, set_progress_file


def run(
    input_path: Path,
    template: Path,
    checkingdb: str,
    outputdir: Path,
    region_type: str = "SEQUENCE_TARGET",
    product_size_min: int = 100,
    product_size_max: int = 1000,
    primer_num_retain: int = 10,
    size_start: int = 50,
    size_stop: int = 5000,
    min_tm_diff: float = 20.0,
    max_report_amplicon: int = 50,
    primer_conc: float = 100.0,
    Na: float = 0.0,
    K: float = 50.0,
    Tris: float = 10.0,
    Mg: float = 1.5,
    dNTPs: float = 0.2,
    blast_e_value: float = 30000,
    blast_word_size: int = 7,
    blast_identity: float = 60.0,
    blast_max_hsps: int = 500,
    num_cpu: int = 1,
    end3_mismatch_threshold: int = 3,
    report_last_5bp_in_3end: bool = True,
    output_detail: bool = False,
    samtools: str = "samtools",
    primer3bin: str = "primer3_core",
    primer3setting: Optional[Path] = None,
    blastn: str = "blastn",
    debug: bool = False,
    progress_fh: Optional[TextIO] = None,
) -> None:
    """Run the complete primer design + specificity-check pipeline."""
    outputdir = Path(outputdir)
    outputdir.mkdir(parents=True, exist_ok=True)
    if progress_fh:
        set_progress_file(progress_fh)

    log_progress(5, "primer3_design")
    primer3_runner.run(
        input_path=input_path,
        db=template,
        outputdir=outputdir,
        region_type=region_type,
        product_size_min=product_size_min,
        product_size_max=product_size_max,
        samtools=samtools,
        primer3bin=primer3bin,
        primer3setting=primer3setting,
        debug=debug,
    )
    log_progress(35, "specificity_check")

    databases = [db.strip() for db in checkingdb.split(",") if db.strip()]
    if not databases:
        databases = [str(template)]

    spec_params = specificity_runner.SpecificityParams(
        size_start=size_start,
        size_stop=size_stop,
        min_tm_diff=min_tm_diff,
        max_report_amplicon=max_report_amplicon,
        primer_conc=primer_conc,
        Na=Na,
        K=K,
        Tris=Tris,
        Mg=Mg,
        dNTPs=dNTPs,
        blast_e_value=blast_e_value,
        blast_word_size=blast_word_size,
        blast_identity=blast_identity,
        blast_max_hsps=blast_max_hsps,
        num_cpu=num_cpu,
        end3_mismatch_threshold=end3_mismatch_threshold,
        report_last_5bp_in_3end=report_last_5bp_in_3end,
        debug=debug,
    )

    primer3_simple = outputdir / "primer3output.simple.table.txt"
    specificity_runner.run(
        input_path=primer3_simple,
        databases=databases,
        outputdir=outputdir,
        params=spec_params,
        samtools=samtools,
        blastn=blastn,
        detail=output_detail,
    )
    log_progress(75, "final_selection")

    selection_runner.run(
        primer3result=outputdir / "primer3output.txt",
        specificity=outputdir / "specificity.check.result.txt",
        amplicon=outputdir / "specificity.check.result.amplicon",
        databases=[Path(db).name for db in databases],
        outputdir=outputdir,
        retain=primer_num_retain,
        region_type=region_type,
        detail=output_detail,
    )
    log_progress(100, "finished")

    if not debug:
        # Clean up intermediate files that are not needed for result parsing.
        for pattern in ["*.tmp", "*.out", "*.out.filterlength"]:
            for p in outputdir.glob(pattern):
                if p.is_file():
                    p.unlink()
        tmp_dir = outputdir / "tmp.specificity.check"
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
