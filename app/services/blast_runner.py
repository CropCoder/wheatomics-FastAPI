"""BLAST execution engine + on-disk job state, shared by the API router and
the standalone job daemon (app/services/blast_daemon.py).

Why this module exists
----------------------
All BLAST jobs execute in one place: the blastd systemd daemon
(app/services/blast_daemon.py, unit in scripts/wheatomics-blastd.service) — a
separate process that survives worker recycling (max_requests=100) and API
deploys. The API router (app/api/routers/blast.py) only enqueues jobs and
polls their status files: wait=true waits for completion, wait=false returns
the job_id immediately. Daemon and router share the job-state format and the
execution logic defined here.

Job directory layout (per job, under ``settings.BLAST_RESULT_DIR/<uuid4>/``)::

    params.json   - validated submission parameters (query included)
    status.json   - pending | running | done | error | stale (+ timestamps)
    result.asn1   - transient BLAST archive (deleted after formatting)
    result.tsv    - tabular output (outfmt 6)
    result.txt    - traditional output (outfmt 0)

``status.json`` is written atomically (tmp + os.replace) so readers never see a
half-written file. The result tree is served by Apache at
``BLAST_RESULT_BASE_URL``; job ids are unguessable uuid4s, and the query
sequence is already present in result.txt (outfmt 0 prints the aligned query),
so params.json does not expose anything the result files do not already.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time as _time
from pathlib import Path
from typing import Optional

from app.core.config import settings

#: A blast subprocess may run up to 600s (+120s per formatter pass). A job in
#: "running" whose started_at is older than this is declared stale by
#: read_status() — the worker/daemon that ran it died before writing a
#: terminal state. (Claimed-but-queued jobs have no started_at and are never
#: stale — see the blast_daemon for the claim protocol.)
STALE_SECONDS = 610

# === 和 CGI 脚本 get_fasta_bedtools.py 完全一致的路径 ===
# === 路径检测（和 blast2.pl 逻辑一致） ===
# blast2.pl:
#   if (-e "/usr/bin/blastall") { $blastPath = "/usr/bin"; }
#   else { $blastPath = "."; }
#   push @cmd, "$blastPath/blastp";

BLAST_BIN = "/var/www/html/blast/blast+/bin"  # BLAST+ 程序目录
DB_DIR = "/var/www/html/getfasta/blastdb/"    # 和 CGI 的 DbPath 一致


class BlastExecutionError(Exception):
    """A blast run failed; carries the HTTP status used by the sync path."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _find_blast_prog(name: str) -> str:
    """查找可用的 BLAST 程序"""
    exe = os.path.join(BLAST_BIN, name)
    if os.path.exists(exe):
        return exe
    # 兜底：可能在别的路径
    for p in ["/usr/bin", "/usr/local/bin"]:
        exe = os.path.join(p, name)
        if os.path.exists(exe):
            return exe
    return f"{BLAST_BIN}/{name}"  # 默认


BLAST_PROGRAMS = {
    p: _find_blast_prog(p)
    for p in ["blastp", "blastn", "blastx", "tblastn", "tblastx"]
}
BLASTP = BLAST_PROGRAMS["blastp"]
BLASTN = BLAST_PROGRAMS["blastn"]
BLASTX = BLAST_PROGRAMS["blastx"]
TBLASTN = BLAST_PROGRAMS["tblastn"]
TBLASTX = BLAST_PROGRAMS["tblastx"]
BLASTDBCMD = _find_blast_prog("blastdbcmd")
BLAST_FORMATTER = _find_blast_prog("blast_formatter")

#: program name -> executable path, used by validation + the job runner.
BLAST_PROG_MAP = {
    "blastp": BLASTP, "blastn": BLASTN, "blastx": BLASTX,
    "tblastn": TBLASTN, "tblastx": TBLASTX,
}


# ---------------------------------------------------------------------------
# Job state files
# ---------------------------------------------------------------------------

def job_dir(job_id: str) -> Path:
    return settings.BLAST_RESULT_DIR / job_id


def status_path(job_id: str) -> Path:
    return job_dir(job_id) / "status.json"


def params_path(job_id: str) -> Path:
    return job_dir(job_id) / "params.json"


def write_status(job_id: str, **fields) -> None:
    """Atomically write job status.json (tmp + os.replace)."""
    d = job_dir(job_id)
    d.mkdir(parents=True, exist_ok=True)
    payload = {"job_id": job_id, **fields}
    tmp = d / "status.json.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    os.replace(tmp, d / "status.json")


def read_status_raw(job_id: str) -> Optional[dict]:
    """Read a job's status.json without any stale rewriting; None if absent."""
    path = status_path(job_id)
    if not path.is_file():
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def read_status(job_id: str) -> Optional[dict]:
    """Read a job's status.json; None if the job doesn't exist.

    A job left in "running" past STALE_SECONDS is rewritten as "stale" so
    pollers always reach a terminal state (worker recycling, an API deploy or
    a daemon crash can kill the runner mid-job). Jobs without started_at are
    claimed-but-queued, not executing — those are never aged out here.
    """
    data = read_status_raw(job_id)
    if data is None:
        return None
    if data.get("status") == "running":
        started = data.get("started_at")
        if started and _time.time() - float(started) > STALE_SECONDS:
            write_status(job_id, status="stale",
                         message="Job interrupted (runner restarted or killed); please resubmit.",
                         created_at=data.get("created_at"),
                         started_at=data.get("started_at"),
                         finished_at=_time.time())
            data["status"] = "stale"
    return data


def write_params(job_id: str, **fields) -> None:
    """Atomically write the validated submission parameters for a job."""
    d = job_dir(job_id)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "params.json.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(fields, fh, ensure_ascii=False)
    os.replace(tmp, d / "params.json")


def read_params(job_id: str) -> Optional[dict]:
    path = params_path(job_id)
    if not path.is_file():
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def list_job_ids() -> list[str]:
    """All job ids on disk (directory entries under the result dir)."""
    result_dir = settings.BLAST_RESULT_DIR
    if not result_dir.is_dir():
        return []
    return sorted(p.name for p in result_dir.iterdir() if p.is_dir())


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def _spawn_blast(cmd: list[str]) -> subprocess.Popen:
    """Spawn a blast subprocess with stdin piped and stdout to devnull.

    Returns the Popen handle immediately so the caller can record proc.pid
    in the job status *while the process is alive* — a restarted daemon uses
    that pid to tell "blast still running (orphan)" from "blast died with
    its runner".
    """
    try:
        return subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        raise BlastExecutionError(500, f"BLAST 可执行文件未找到: {cmd[0]}")


def _wait_blast(proc: subprocess.Popen, query: str, timeout: int) -> tuple[str, int]:
    """Feed the query to a spawned blast and wait; returns (stderr, returncode)."""
    try:
        _, err = proc.communicate(input=query, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise BlastExecutionError(504, "BLAST 超时（>10分钟）")
    return err or "", proc.returncode


def _base_cmd(blast_path: str, program: str, dbs: list[str], outfmt: str,
              out_path: Path, evalue: float, max_targets: int,
              word_size: Optional[int], matrix: Optional[str]) -> list[str]:
    """Shared argv body for the archive pass and the two-format fallback."""
    cmd = [
        blast_path, "-task", program,
        "-db", " ".join(os.path.join(DB_DIR, d) for d in dbs),
        "-outfmt", outfmt,
        "-out", str(out_path),
        "-evalue", str(evalue),
        "-max_target_seqs", str(max_targets),
        "-num_threads", "4",
    ]
    if word_size is not None:
        cmd += ["-word_size", str(word_size)]
    if matrix is not None:
        cmd += ["-matrix", matrix]
    return cmd


def execute_blast_job(job_id: str, params: Optional[dict] = None) -> dict:
    """Run one BLAST job to completion (blocking) and return download_urls.

    Writes the status transitions itself: running (+ blast_pid) -> done/error.
    ``params`` supplies the submission parameters; when None (daemon path)
    they are loaded from the job dir's params.json. The blast daemon is the
    only caller in production — the API just enqueues jobs and polls.
    Raises BlastExecutionError on failure; the "error" status (with the
    matching HTTP status_code) is written first, so pollers always see it.
    """
    if params is None:
        params = read_params(job_id)
        if params is None:
            # Write the terminal state too, otherwise the daemon would keep
            # re-claiming this job forever.
            msg = f"Job {job_id}: params.json missing"
            write_status(job_id, status="error", message=msg,
                         finished_at=_time.time())
            raise BlastExecutionError(500, msg)
    else:
        write_params(job_id, **params)

    jd = job_dir(job_id)
    jd.mkdir(parents=True, exist_ok=True)
    created_at = (read_status_raw(job_id) or {}).get("created_at") or _time.time()
    started_at = _time.time()

    def _write_error(message: str, status_code: int = 500) -> None:
        # status_code is recorded so the wait=true endpoint can reproduce the
        # same HTTP status a caller would have gotten from a direct run
        # (504 for blast timeout, 500 for execution errors).
        write_status(job_id, status="error", message=message,
                     status_code=status_code,
                     created_at=created_at, started_at=started_at,
                     finished_at=_time.time())

    # ---- 构造结果格式映射 ----
    fmt_defs = {
        "tabular": ("6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore stitle", ".tsv"),
        "traditional": ("0", ".txt"),
    }

    download_urls = {}
    try:
        program = params["program"]
        dbs = params["dbs"]
        query = params["query"]
        evalue = params["evalue"]
        max_targets = params["max_targets"]
        word_size = params.get("word_size")
        matrix = params.get("matrix")

        blast_path = BLAST_PROG_MAP.get(program, BLASTP)
        # ---- 优先 blast_formatter（ASN.1 archive + 转换，BLAST 只跑一次）----
        if os.path.exists(BLAST_FORMATTER):
            archive_path = jd / "result.asn1"
            cmd = _base_cmd(blast_path, program, dbs, "11", archive_path,
                            evalue, max_targets, word_size, matrix)
            proc = _spawn_blast(cmd)
            write_status(job_id, status="running", blast_pid=proc.pid,
                         created_at=created_at, started_at=started_at,
                         message="BLAST running.")
            err, rc = _wait_blast(proc, query, 600)
            if rc != 0:
                archive_path.unlink(missing_ok=True)
                raise BlastExecutionError(500, f"BLAST 执行错误: {err.strip()}")

            for name, (oflag, ext) in fmt_defs.items():
                out_path = jd / f"result{ext}"
                subprocess.run(
                    [BLAST_FORMATTER, "-archive", str(archive_path),
                     "-outfmt", oflag, "-out", str(out_path)],
                    timeout=120,
                )
                download_urls[name] = f"{settings.BLAST_SITE_BASE_URL}{settings.BLAST_RESULT_BASE_URL}/{job_id}/result{ext}"

            archive_path.unlink(missing_ok=True)
        else:
            # ---- 降级：BLAST 跑两次 ----
            for name, (oflag, ext) in fmt_defs.items():
                fname = f"result{ext}"
                filepath = jd / fname
                cmd = _base_cmd(blast_path, program, dbs, oflag, filepath,
                                evalue, max_targets, word_size, matrix)
                proc = _spawn_blast(cmd)
                write_status(job_id, status="running", blast_pid=proc.pid,
                             created_at=created_at, started_at=started_at,
                             message="BLAST running.")
                err, rc = _wait_blast(proc, query, 600)
                if rc != 0:
                    filepath.unlink(missing_ok=True)
                    raise BlastExecutionError(500, f"BLAST 执行错误: {err.strip()}")

                download_urls[name] = f"{settings.BLAST_SITE_BASE_URL}{settings.BLAST_RESULT_BASE_URL}/{job_id}/{fname}"

        write_status(job_id, status="done", download_urls=download_urls,
                     created_at=created_at, started_at=started_at,
                     finished_at=_time.time(), message="")
    except BlastExecutionError as exc:
        _write_error(exc.message, exc.status_code)
        raise
    except KeyError as exc:  # corrupt params.json (defensive)
        _write_error(f"Job {job_id}: params.json missing field: {exc.args[0]}")
        raise BlastExecutionError(
            500, f"Job {job_id}: params.json missing field: {exc.args[0]}"
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive
        _write_error(str(exc))
        raise BlastExecutionError(500, str(exc)) from exc
    return download_urls


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def cleanup_old_results():
    """清理过期的 BLAST 结果（job 目录 + legacy 平铺文件）。

    两阶段: 先按年龄删（超过 EXPIRE_DAYS 的），若删除后条目数仍超过
    MAX_FILES，再按最老的删到上限以内。每个 job 是一个目录（含结果文件
    + status.json + params.json），整体删除；旧版平铺的 blast_*.tsv/.txt
    也兼容清理。Owned by the blast daemon (hourly + at startup).
    """
    result_dir = settings.BLAST_RESULT_DIR
    if not result_dir.is_dir():
        return
    cutoff = _time.time() - settings.BLAST_RESULT_EXPIRE_DAYS * 86400

    def _mtime(p):
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    # 条目 = job 目录 + legacy 平铺文件。
    entries = [p for p in result_dir.iterdir() if p.is_dir() or p.is_file()]
    expired = [p for p in entries if _mtime(p) < cutoff]
    for p in expired:
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink()
        except OSError:
            pass

    remaining = [p for p in entries if p not in expired]
    over = len(remaining) - settings.BLAST_RESULT_MAX_FILES
    if over > 0:
        remaining.sort(key=_mtime)
        for p in remaining[:over]:
            try:
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink()
            except OSError:
                pass
