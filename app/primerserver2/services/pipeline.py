import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..config import PrimerServerConfig
from ..dependencies import PrimerServer2Settings
from ..models import CheckJobRequest, DesignJobRequest, JobResultResponse, JobStatus
from . import pipeline_design, selection_runner, specificity_runner
from .storage import JobManager

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Builds and executes PrimerServer2 pipelines using Python runners."""

    def __init__(
        self,
        config: PrimerServerConfig,
        job_manager: JobManager,
        settings: Optional[PrimerServer2Settings] = None,
    ):
        self.config = config
        self.job_manager = job_manager
        self.settings = settings
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._executor = ThreadPoolExecutor(
            max_workers=settings.max_concurrent_jobs if settings else 4,
            thread_name_prefix="primerserver2_",
        )

    def _write_text(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")

    def _build_p3_settings(self, request: DesignJobRequest) -> str:
        lines = [
            "Primer3 File - http://primer3.sourceforge.net",
            "P3_FILE_TYPE=settings",
            "",
            "PRIMER_EXPLAIN_FLAG=1",
            f"PRIMER_NUM_RETURN={request.PRIMER_NUM_RETURN}",
            f"PRIMER_MIN_SIZE={request.PRIMER_MIN_SIZE}",
            f"PRIMER_OPT_SIZE={request.PRIMER_OPT_SIZE}",
            f"PRIMER_MAX_SIZE={request.PRIMER_MAX_SIZE}",
            f"PRIMER_MIN_TM={request.PRIMER_MIN_TM}",
            f"PRIMER_OPT_TM={request.PRIMER_OPT_TM}",
            f"PRIMER_MAX_TM={request.PRIMER_MAX_TM}",
            f"PRIMER_PAIR_MAX_DIFF_TM={request.PRIMER_PAIR_MAX_DIFF_TM}",
            f"PRIMER_MIN_GC={request.PRIMER_MIN_GC}",
            f"PRIMER_OPT_GC_PERCENT={request.PRIMER_OPT_GC_PERCENT}",
            f"PRIMER_MAX_GC={request.PRIMER_MAX_GC}",
            f"PRIMER_MAX_END_STABILITY={request.PRIMER_MAX_END_STABILITY}",
            f"PRIMER_LOWERCASE_MASKING={request.PRIMER_LOWERCASE_MASKING}",
            f"PRIMER_MIN_LEFT_THREE_PRIME_DISTANCE={request.PRIMER_MIN_LEFT_THREE_PRIME_DISTANCE}",
            f"PRIMER_MIN_RIGHT_THREE_PRIME_DISTANCE={request.PRIMER_MIN_RIGHT_THREE_PRIME_DISTANCE}",
            f"PRIMER_MAX_SELF_ANY_TH={request.PRIMER_MAX_SELF_ANY_TH}",
            f"PRIMER_PAIR_MAX_COMPL_ANY_TH={request.PRIMER_PAIR_MAX_COMPL_ANY_TH}",
            f"PRIMER_MAX_SELF_END_TH={request.PRIMER_MAX_SELF_END_TH}",
            f"PRIMER_PAIR_MAX_COMPL_END_TH={request.PRIMER_PAIR_MAX_COMPL_END_TH}",
            f"PRIMER_MAX_HAIRPIN_TH={request.PRIMER_MAX_HAIRPIN_TH}",
            "=",
        ]
        return "\n".join(lines)

    def _resolve_databases(self, selected: List[str], job_dir: Path) -> List[str]:
        """Resolve selected database names to absolute paths."""
        resolved = []
        for db_name in selected:
            if db_name == "custom":
                resolved.append(str(job_dir / "customdb"))
            else:
                resolved.append(str(self.config.database_path(db_name)))
        return resolved

    def _prepare_custom_inputs(
        self,
        job_dir: Path,
        request: DesignJobRequest,
    ) -> None:
        """Write custom template/database FASTA files if requested."""
        if request.selectTemplate == "custom" and request.customTemplateSequences:
            self._write_text(job_dir / "custom", request.customTemplateSequences)

        if "custom" in request.selectedDatabases and request.customDbSequences:
            self._write_text(job_dir / "customdb", request.customDbSequences)

    def _validate_design_limits(self, request: DesignJobRequest) -> None:
        if self.config.limit_site > 0:
            lines = [ln for ln in (request.templateRegions or "").splitlines() if ln.strip() and not ln.strip().startswith("#")]
            if len(lines) > self.config.limit_site:
                raise ValueError(
                    f"Number of template regions ({len(lines)}) exceeds limitSite ({self.config.limit_site})"
                )

    def _validate_check_limits(self, request: CheckJobRequest) -> None:
        if self.config.limit_primer > 0:
            lines = [ln for ln in request.checkPrimers.splitlines() if ln.strip() and not ln.strip().startswith("#")]
            if len(lines) > self.config.limit_primer:
                raise ValueError(
                    f"Number of primer groups ({len(lines)}) exceeds limitPrimer ({self.config.limit_primer})"
                )

    def _validate_database_limits(self, selected: List[str]) -> None:
        if self.config.limit_database > 0 and len(selected) > self.config.limit_database:
            raise ValueError(
                f"Number of selected databases ({len(selected)}) exceeds limitDatabase ({self.config.limit_database})"
            )

    def prepare_design_inputs(
        self,
        job_id: str,
        request: DesignJobRequest,
    ) -> Dict[str, Any]:
        """Prepare files and return kwargs for pipeline_design.run."""
        self._validate_design_limits(request)
        self._validate_database_limits(request.selectedDatabases)

        job_dir = self.job_manager.get_job_dir(job_id)
        self._prepare_custom_inputs(job_dir, request)

        input_path = job_dir / "perl_input_region.tmp"
        self._write_text(input_path, request.templateRegions or "")

        p3_settings = job_dir / "p3_settings_file"
        self._write_text(p3_settings, self._build_p3_settings(request))

        # Persist design parameters so result parsing can reconstruct primer details.
        design_params = {
            "region_type": request.regionType.value,
            "product_size_min": request.productSizeMin,
            "product_size_max": request.productSizeMax,
            "retain": request.retain,
        }
        self._write_text(job_dir / "design_params.json", json.dumps(design_params))

        if request.selectTemplate == "custom":
            template_path = job_dir / "custom"
        else:
            template_path = self.config.database_path(request.selectTemplate)

        selected_dbs = ",".join(self._resolve_databases(request.selectedDatabases, job_dir))

        return {
            "input_path": input_path,
            "template": template_path,
            "checkingdb": selected_dbs,
            "outputdir": job_dir,
            "region_type": request.regionType.value,
            "product_size_min": request.productSizeMin,
            "product_size_max": request.productSizeMax,
            "primer_num_retain": request.retain,
            "size_start": request.sizeStart,
            "size_stop": request.sizeStop,
            "min_tm_diff": request.minTmDiff,
            "max_report_amplicon": request.maxReportAmplicon,
            "primer_conc": request.concPrimer,
            "Na": request.concNa,
            "K": request.concK,
            "Tris": request.concTris,
            "Mg": request.concMg,
            "dNTPs": request.concDntps,
            "blast_e_value": request.blastEValue,
            "blast_word_size": request.blastWordSize,
            "blast_identity": request.blastIdentity,
            "blast_max_hsps": request.blastMaxHsps,
            "num_cpu": self.config.use_cpu,
            "end3_mismatch_threshold": request.end3MismatchThreshold,
            "output_detail": True,
            "samtools": self.config.samtools,
            "primer3bin": self.config.primer3,
            "primer3setting": p3_settings,
            "blastn": self.config.blastn,
        }

    def prepare_check_inputs(
        self,
        job_id: str,
        request: CheckJobRequest,
    ) -> Dict[str, Any]:
        """Prepare files and return kwargs for specificity_runner.run."""
        self._validate_check_limits(request)
        self._validate_database_limits(request.selectedDatabases)

        job_dir = self.job_manager.get_job_dir(job_id)
        input_path = job_dir / "check.only.tmp"
        self._write_text(input_path, request.checkPrimers)

        if "custom" in request.selectedDatabases and request.customDbSequences:
            self._write_text(job_dir / "customdb", request.customDbSequences)

        selected_dbs = ",".join(self._resolve_databases(request.selectedDatabases, job_dir))

        params = specificity_runner.SpecificityParams(
            size_start=request.sizeStart,
            size_stop=request.sizeStop,
            min_tm_diff=request.minTmDiff,
            max_report_amplicon=request.maxReportAmplicon,
            primer_conc=request.concPrimer,
            Na=request.concNa,
            K=request.concK,
            Tris=request.concTris,
            Mg=request.concMg,
            dNTPs=request.concDntps,
            blast_e_value=request.blastEValue,
            blast_word_size=request.blastWordSize,
            blast_identity=request.blastIdentity,
            blast_max_hsps=request.blastMaxHsps,
            num_cpu=self.config.use_cpu,
            end3_mismatch_threshold=request.end3MismatchThreshold,
        )

        return {
            "input_path": input_path,
            "databases": [db.strip() for db in selected_dbs.split(",") if db.strip()],
            "outputdir": job_dir,
            "params": params,
            "samtools": self.config.samtools,
            "blastn": self.config.blastn,
            "detail": True,
        }

    async def run_python_task(
        self,
        job_id: str,
        func: Callable,
        **kwargs,
    ) -> None:
        """Run a synchronous Python pipeline function in a thread pool.

        Progress markers are written to the job log file so the existing
        log-based progress monitor continues to work.
        """
        if self._semaphore is None and self.settings and self.settings.max_concurrent_jobs > 0:
            self._semaphore = asyncio.Semaphore(self.settings.max_concurrent_jobs)

        job_dir = self.job_manager.get_job_dir(job_id)
        log_file = job_dir / "pipeline.log"

        self.job_manager.update_status(
            job_id,
            status="running",
            message="Pipeline started",
            progress={"total": 100, "finished": 0, "percent": 0, "stage": "initializing"},
        )

        monitor_task: Optional[asyncio.Task] = None
        try:
            monitor_task = asyncio.create_task(self._monitor_progress(job_id, log_file))

            # Treat 0 as "no timeout" to avoid an immediate asyncio.TimeoutError.
            job_timeout = self.settings.job_timeout if self.settings else None
            if job_timeout == 0:
                job_timeout = None

            with open(log_file, "w", encoding="utf-8") as log_fh:
                kwargs["progress_fh"] = log_fh
                loop = asyncio.get_event_loop()
                if self._semaphore:
                    async with self._semaphore:
                        await asyncio.wait_for(
                            loop.run_in_executor(self._executor, partial(func, **kwargs)),
                            timeout=job_timeout,
                        )
                else:
                    await asyncio.wait_for(
                        loop.run_in_executor(self._executor, partial(func, **kwargs)),
                        timeout=job_timeout,
                    )

            if monitor_task:
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass

            self._update_progress_from_log(job_id, log_file, final=True)
            self.job_manager.update_status(
                job_id,
                status="done",
                message="Pipeline completed",
                progress={"total": 100, "finished": 100, "percent": 100, "stage": "finished"},
            )
            logger.info("Job %s completed successfully", job_id)
        except asyncio.TimeoutError:
            logger.error("Job %s timed out", job_id)
            if monitor_task:
                monitor_task.cancel()
            self.job_manager.update_status(
                job_id,
                status="error",
                message="Pipeline timed out",
                progress={"total": 100, "finished": 0, "percent": 0, "stage": "timeout"},
            )
        except Exception as exc:
            logger.exception("Exception during pipeline execution for job %s", job_id)
            if monitor_task:
                monitor_task.cancel()
            self.job_manager.update_status(
                job_id,
                status="error",
                message=f"Pipeline error: {exc}",
                progress={"total": 100, "finished": 0, "percent": 0, "stage": "error"},
            )
        finally:
            self.job_manager.unregister_process(job_id)
            self.job_manager.cleanup_old_jobs()

    async def _monitor_progress(self, job_id: str, log_file: Path) -> None:
        """Periodically parse the pipeline log and update progress."""
        while True:
            await asyncio.sleep(2)
            self._update_progress_from_log(job_id, log_file)

    def _update_progress_from_log(self, job_id: str, log_file: Path, final: bool = False) -> None:
        """Parse __PRIMERSERVER_PROGRESS__ markers from the log file."""
        if not log_file.exists():
            return
        try:
            log_content = log_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return

        last_percent = 0
        last_stage = "running"
        for line in log_content.splitlines():
            if "__PRIMERSERVER_PROGRESS__" in line:
                parts = line.strip().split()
                if len(parts) >= 3:
                    try:
                        last_percent = int(parts[-2])
                        last_stage = parts[-1]
                    except ValueError:
                        continue

        if final:
            last_percent = 100
            last_stage = "finished"

        self.job_manager.update_status(
            job_id,
            progress={
                "total": 100,
                "finished": last_percent,
                "percent": last_percent,
                "stage": last_stage,
            },
        )

    async def run_design(self, job_id: str, request: DesignJobRequest) -> None:
        kwargs = self.prepare_design_inputs(job_id, request)
        await self.run_python_task(job_id, pipeline_design.run, **kwargs)

    async def run_check(self, job_id: str, request: CheckJobRequest) -> None:
        kwargs = self.prepare_check_inputs(job_id, request)
        await self.run_python_task(job_id, specificity_runner.run, **kwargs)

    def parse_result(self, job_id: str, job_type: str) -> JobResultResponse:
        """Parse pipeline outputs into a structured response."""
        job_dir = self.job_manager.get_job_dir(job_id)
        status = self.job_manager.get_status(job_id) or {}

        result_html = job_dir / "primer.final.result.html"
        check_html = job_dir / "specificity.check.result.html"
        result_txt = job_dir / "primer.final.result.txt"
        check_txt = job_dir / "specificity.check.result.txt"

        html: Optional[str] = None
        if result_html.exists():
            html = result_html.read_text(encoding="utf-8")
        elif check_html.exists():
            html = check_html.read_text(encoding="utf-8")

        design_primers: Optional[List[Dict[str, Any]]] = None
        no_primer_message: Optional[str] = None
        check_results: Optional[List[Dict[str, Any]]] = None

        if result_txt.exists():
            design_primers, no_primer_message = self._parse_design_result(result_txt, job_dir)
        if check_txt.exists():
            check_results = self._parse_check_result(check_txt, job_dir)

        error_message = status.get("message") if status.get("status") == "error" else None
        if not error_message and no_primer_message:
            error_message = no_primer_message

        return JobResultResponse(
            jobId=job_id,
            jobType=job_type,
            status=status.get("status", "unknown"),
            html=html,
            designPrimers=design_primers,
            checkResults=check_results,
            error=error_message,
        )

    def _parse_design_result(
        self,
        path: Path,
        job_dir: Path,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Parse primer.final.result.txt into structured data.

        Returns a tuple of (primers, no_primer_message). When primer3 could not
        design any primers for a site, the original Perl pipeline writes a
        "No_Primer" row; that message is returned so the frontend can display
        a meaningful warning instead of an empty result table.
        """
        primers: Dict[str, Dict[str, Any]] = {}
        no_primer_messages: List[str] = []
        current_site: Optional[str] = None
        try:
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line == "###":
                    current_site = None
                    continue
                if line.startswith("###"):
                    current_site = line.lstrip("#").strip()
                    continue
                parts = line.split("\t")
                if len(parts) < 9:
                    # The original pipeline emits a "No_Primer" row when no
                    # primers could be designed for a site.
                    if len(parts) >= 2 and parts[1] == "No_Primer":
                        site_id = parts[0]
                        reasons = "; ".join(parts[2:]) if len(parts) > 2 else "no reasons given"
                        no_primer_messages.append(f"{site_id}: No appropriate primers ({reasons})")
                    continue
                site_id, rank, left_seq, right_seq, size, penalty, database, amplicon_num, primer3_rank = parts[:9]
                key = f"{site_id}:{rank}"
                if key not in primers:
                    primers[key] = {
                        "siteId": site_id,
                        "rank": int(rank),
                        "leftSeq": left_seq,
                        "rightSeq": right_seq,
                        "productSize": int(size) if size.isdigit() else 0,
                        "penalty": float(penalty) if self._is_float(penalty) else 0.0,
                        "primer3Rank": int(primer3_rank) if primer3_rank.isdigit() else None,
                        "databases": [],
                    }
                primers[key]["databases"].append({
                    "name": database,
                    "ampliconNumber": int(amplicon_num) if amplicon_num.isdigit() else 0,
                })
        except Exception as exc:
            logger.warning("Failed to parse design result %s: %s", path, exc)
            return list(primers.values()), None

        # Enrich primer records with thermodynamic and positional details from
        # Primer3 output, plus amplicon coordinates from the specificity check.
        if primers:
            try:
                details = self._parse_primer3_details(job_dir)
                amplicons = self._parse_amplicon_details(job_dir)
                for key, primer in primers.items():
                    site_id = primer["siteId"]
                    p3_rank = primer.get("primer3Rank")
                    detail = details.get(site_id, {}).get(p3_rank)
                    if detail:
                        primer.update(detail)
                    for db in primer.get("databases", []):
                        db["amplicons"] = amplicons.get(site_id, {}).get(p3_rank, {}).get(
                            db["name"], []
                        )
                        alignment_path = (
                            job_dir
                            / "result.specificity.check"
                            / f"PrimerGroup.{db['name']}.{site_id}.{p3_rank}.txt"
                        )
                        if alignment_path.exists():
                            try:
                                db["alignment"] = alignment_path.read_text(encoding="utf-8")
                            except Exception as exc:
                                logger.warning("Failed to read alignment %s: %s", alignment_path, exc)
            except Exception as exc:
                logger.warning("Failed to enrich design result details: %s", exc)

        no_primer_message = "\n".join(no_primer_messages) if no_primer_messages else None
        return list(primers.values()), no_primer_message

    def _parse_primer3_details(self, job_dir: Path) -> Dict[str, Dict[int, Dict[str, Any]]]:
        """Extract per-primer thermodynamic/positional details from primer3output.txt."""
        details: Dict[str, Dict[int, Dict[str, Any]]] = {}
        p3_path = job_dir / "primer3output.txt"
        if not p3_path.exists():
            return details

        params_path = job_dir / "design_params.json"
        region_type = "SEQUENCE_TARGET"
        if params_path.exists():
            try:
                params = json.loads(params_path.read_text(encoding="utf-8"))
                region_type = params.get("region_type", region_type)
            except Exception:
                pass

        records = selection_runner.parse_primer3_result(p3_path, region_type, retain=1000)
        for record in records:
            details[record.site_id] = {}
            for pair in record.pairs:
                details[record.site_id][pair.rank] = {
                    "leftTm": self._round(pair.tm_left, 1),
                    "rightTm": self._round(pair.tm_right, 1),
                    "leftGc": self._round(pair.gc_left, 1),
                    "rightGc": self._round(pair.gc_right, 1),
                    "leftPos": f"{record.chrom}:{pair.pos_left}-{pair.pos_left + pair.len_left - 1}",
                    "rightPos": f"{record.chrom}:{pair.pos_right}-{pair.pos_right + pair.len_right - 1}",
                    "leftLen": pair.len_left,
                    "rightLen": pair.len_right,
                    "leftSelfAny": self._round(pair.self_any_left, 1),
                    "rightSelfAny": self._round(pair.self_any_right, 1),
                    "leftSelfEnd": self._round(pair.self_end_left, 1),
                    "rightSelfEnd": self._round(pair.self_end_right, 1),
                    "leftHairpin": self._round(pair.hairpin_left, 1),
                    "rightHairpin": self._round(pair.hairpin_right, 1),
                    "leftEndStability": self._round(pair.end_stability_left, 1),
                    "rightEndStability": self._round(pair.end_stability_right, 1),
                    "pairComplAny": self._round(pair.pair_compl_any, 1),
                    "pairComplEnd": self._round(pair.pair_compl_end, 1),
                }
        return details

    def _parse_amplicon_details(
        self, job_dir: Path
    ) -> Dict[str, Dict[int, Dict[str, List[Dict[str, Any]]]]]:
        """Parse specificity.check.result.amplicon into structured amplicon lists."""
        amplicons: Dict[str, Dict[int, Dict[str, List[Dict[str, Any]]]]] = {}
        path = job_dir / "specificity.check.result.amplicon"
        if not path.exists():
            return amplicons
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 7:
                    continue
                site_id, rank_str, db_name, target_id, tstart, tend, *_ = parts
                rank = int(rank_str)
                start = int(tstart)
                end = int(tend)
                size = abs(end - start) + 1
                amplicons.setdefault(site_id, {}).setdefault(rank, {}).setdefault(db_name, []).append(
                    {"chrom": target_id, "start": min(start, end), "end": max(start, end), "size": size}
                )
        except Exception as exc:
            logger.warning("Failed to parse amplicon details %s: %s", path, exc)
        return amplicons

    @staticmethod
    def _round(value: float, digits: int) -> float:
        """Round a float value, returning None for missing values."""
        if value is None:
            return None
        return round(float(value), digits)

    def _parse_check_result(
        self, path: Path, job_dir: Path
    ) -> List[Dict[str, Any]]:
        """Parse specificity.check.result.txt into structured data."""
        results: List[Dict[str, Any]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 5:
                    continue
                site_id, rank, database, amplicon_num, seqs = parts[:5]
                results.append({
                    "siteId": site_id,
                    "rank": int(rank),
                    "database": database,
                    "ampliconNumber": int(amplicon_num) if amplicon_num.isdigit() else 0,
                    "primerSeqs": seqs.split(),
                })
        except Exception as exc:
            logger.warning("Failed to parse check result %s: %s", path, exc)

        if results:
            try:
                amplicons = self._parse_amplicon_details(job_dir)
                for row in results:
                    site_id = row["siteId"]
                    rank = row["rank"]
                    db_name = row["database"]
                    db_amps = amplicons.get(site_id, {}).get(rank, {}).get(db_name, [])
                    row["amplicons"] = db_amps
                    row["sizes"] = [amp["size"] for amp in db_amps]
                    alignment_path = (
                        job_dir
                        / "result.specificity.check"
                        / f"PrimerGroup.{db_name}.{site_id}.{rank}.txt"
                    )
                    if alignment_path.exists():
                        try:
                            row["alignment"] = alignment_path.read_text(encoding="utf-8")
                        except Exception as exc:
                            logger.warning("Failed to read alignment %s: %s", alignment_path, exc)
            except Exception as exc:
                logger.warning("Failed to enrich check result details: %s", exc)

        return results

    @staticmethod
    def _is_float(value: str) -> bool:
        try:
            float(value)
            return True
        except ValueError:
            return False
