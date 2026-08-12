"""WheatOmics BLAST job daemon — runs wait=false blast jobs outside gunicorn.

Why this exists
---------------
Blast jobs submitted with wait=false used to run as BackgroundTasks inside a
gunicorn worker. Worker recycling (max_requests=100) or `systemctl restart
wheatomics-api` killed them mid-run and left status.json stuck on "running"
(pollers hung until the stale check fired). This daemon is a standalone
process (systemd unit: scripts/wheatomics-blastd.service) that survives API
worker recycling and API deploys entirely:

  - scans settings.BLAST_RESULT_DIR for "pending" jobs every second,
  - claims them (pending -> running) and runs them on a small thread pool of
    BLAST_MAX_CONCURRENT workers — a true *global* cap, since there is exactly
    one daemon (the sync path in the API has its own per-worker cap),
  - writes done/error, and on startup reaps jobs left over from a previous
    daemon incarnation: "running" without a blast pid was claimed but never
    started and is requeued as pending; "running" whose blast pid is dead is
    marked stale.

Claim protocol: a job is written "running" *without* started_at at claim time
(executor queueing); started_at + blast_pid are written when the thread
actually spawns blast. blast_runner.read_status() only ages jobs that have a
started_at, so jobs waiting for a free slot are never falsely declared stale.

SIGTERM stops claiming new jobs and waits for in-flight blasts (worst case
~14 min); systemd's TimeoutStopSec=900 in the unit leaves margin.

Run:  python -m app.services.blast_daemon [--once JOB_ID]
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.core.config import settings
from app.services import blast_runner as runner

log = logging.getLogger("blastd")

POLL_INTERVAL_SECONDS = 1.0
CLEANUP_INTERVAL_SECONDS = 3600.0

_stop = threading.Event()


def _pid_alive(pid: int) -> bool:
    """True if a process with this pid exists (best effort)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def reap_leftover_jobs() -> None:
    """Recover jobs whose runner died (daemon restart / crash).

    Call at startup only, before any new jobs are claimed — no race with the
    executor exists yet at that point.
    """
    for job_id in runner.list_job_ids():
        data = runner.read_status_raw(job_id)
        if not data or data.get("status") != "running":
            continue
        created_at = data.get("created_at")
        started_at = data.get("started_at")
        blast_pid = data.get("blast_pid")
        if not started_at and not blast_pid:
            # Claimed but never started — safe to run again.
            runner.write_status(job_id, status="pending", created_at=created_at,
                                message="Requeued after daemon restart.")
            log.info("requeued job %s (claimed but never started)", job_id)
        elif blast_pid and not _pid_alive(blast_pid):
            runner.write_status(job_id, status="stale", created_at=created_at,
                                started_at=started_at, finished_at=time.time(),
                                message="Job interrupted (blast daemon restarted); please resubmit.")
            log.info("marked job %s stale (blast pid %s gone)", job_id, blast_pid)
        # else: the blast subprocess outlived its daemon (orphan). It keeps
        # burning CPU and finishes writing results, but nobody flips the
        # status; read_status() ages it into "stale" after STALE_SECONDS.


def _run_one(job_id: str) -> None:
    try:
        runner.execute_blast_job(job_id)
    except runner.BlastExecutionError as exc:
        log.warning("job %s failed: %s", job_id, exc.message)
    except Exception:
        log.exception("job %s crashed unexpectedly", job_id)


def _submit_pending(executor: ThreadPoolExecutor) -> None:
    """Claim every pending job (FIFO by created_at) onto the executor.

    Claiming writes status "running" without started_at; executor queueing is
    what actually enforces BLAST_MAX_CONCURRENT. Single-daemon assumption: no
    claim race (systemd unit runs exactly one instance).
    """
    pending = []
    for job_id in runner.list_job_ids():
        data = runner.read_status_raw(job_id)
        if data and data.get("status") == "pending":
            pending.append((data.get("created_at") or 0.0, job_id))
    pending.sort()
    for created_at, job_id in pending:
        if _stop.is_set():
            return
        runner.write_status(job_id, status="running", created_at=created_at,
                            message="BLAST running.")
        executor.submit(_run_one, job_id)


def _handle_signal(signum, frame):
    log.info("received signal %s — finishing in-flight jobs, then exiting", signum)
    _stop.set()


def run_daemon(executor: ThreadPoolExecutor) -> None:
    """Main loop: claim pending jobs, cleanup hourly, until _stop is set.

    Split from main() so tests can drive the loop with their own executor.
    """
    next_cleanup = time.time() + CLEANUP_INTERVAL_SECONDS
    while not _stop.is_set():
        try:
            _submit_pending(executor)
            if time.time() >= next_cleanup:
                runner.cleanup_old_results()
                next_cleanup = time.time() + CLEANUP_INTERVAL_SECONDS
        except Exception:
            log.exception("daemon loop error (continuing)")
        _stop.wait(POLL_INTERVAL_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(description="WheatOmics BLAST job daemon")
    parser.add_argument("--once", metavar="JOB_ID",
                        help="run a single job (from params.json) and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")

    if args.once:
        _run_one(args.once)
        return

    settings.BLAST_RESULT_DIR.mkdir(parents=True, exist_ok=True)
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    log.info("blast daemon starting: concurrency=%s result_dir=%s",
             settings.BLAST_MAX_CONCURRENT, settings.BLAST_RESULT_DIR)
    reap_leftover_jobs()
    runner.cleanup_old_results()

    # ThreadPoolExecutor.__exit__ -> shutdown(wait=True): after SIGTERM the
    # loop stops claiming and this waits for in-flight blasts before exiting.
    with ThreadPoolExecutor(max_workers=settings.BLAST_MAX_CONCURRENT,
                            thread_name_prefix="blastd") as executor:
        run_daemon(executor)
    log.info("blast daemon stopped")


if __name__ == "__main__":
    main()
