import datetime
import json
import logging
import shutil
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from ..dependencies import PrimerServer2Settings

logger = logging.getLogger(__name__)


class JobManager:
    """Manages job working directories and status files."""

    def __init__(self, workdir_base: Path, max_age_days: int = 7, max_jobs: int = 1000):
        self.workdir_base = Path(workdir_base)
        self.workdir_base.mkdir(parents=True, exist_ok=True)
        self.max_age_days = max_age_days
        self.max_jobs = max_jobs
        self._running: Dict[str, int] = {}  # job_id -> process pid

    @classmethod
    def from_settings(cls, settings: PrimerServer2Settings) -> "JobManager":
        return cls(
            workdir_base=settings.workdir_base,
            max_age_days=settings.max_job_age_days,
            max_jobs=settings.max_jobs_on_disk,
        )

    def _job_dir(self, job_id: str) -> Path:
        return self.workdir_base / job_id

    def create_job(self) -> str:
        job_id = str(uuid.uuid4())
        job_dir = self._job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        self._write_status(
            job_id,
            {
                "jobId": job_id,
                "status": "pending",
                "createdAt": datetime.datetime.now().isoformat(),
                "message": "Job created",
                "progress": {"total": 100, "finished": 0, "percent": 0, "stage": "waiting"},
            },
        )
        logger.info("Created job %s in %s", job_id, job_dir)
        return job_id

    def _status_file(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "status.json"

    def _write_status(self, job_id: str, status: Dict) -> None:
        status_file = self._status_file(job_id)
        try:
            status_file.write_text(json.dumps(status, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to write status for job %s: %s", job_id, exc)
            raise

    def update_status(self, job_id: str, **kwargs) -> None:
        status = self.get_status(job_id)
        if status is None:
            logger.warning("Cannot update status for missing job %s", job_id)
            return
        status.update(kwargs)
        self._write_status(job_id, status)

    def get_status(self, job_id: str) -> Optional[Dict]:
        status_file = self._status_file(job_id)
        if not status_file.exists():
            return None
        try:
            return json.loads(status_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.error("Corrupted status file for job %s: %s", job_id, exc)
            return None
        except Exception as exc:
            logger.error("Failed to read status for job %s: %s", job_id, exc)
            return None

    def get_job_dir(self, job_id: str) -> Path:
        return self._job_dir(job_id)

    def exists(self, job_id: str) -> bool:
        return self._job_dir(job_id).exists()

    def register_process(self, job_id: str, pid: int) -> None:
        self._running[job_id] = pid
        logger.debug("Registered process %s for job %s", pid, job_id)

    def unregister_process(self, job_id: str) -> None:
        self._running.pop(job_id, None)

    def get_process_pid(self, job_id: str) -> Optional[int]:
        return self._running.get(job_id)

    def stop_process(self, job_id: str) -> bool:
        """Send SIGTERM to a running process and its children (best effort)."""
        import os
        import signal

        pid = self._running.pop(job_id, None)
        if pid is None:
            return False
        try:
            os.kill(pid, signal.SIGTERM)
            logger.info("Sent SIGTERM to process %s for job %s", pid, job_id)
            return True
        except ProcessLookupError:
            logger.debug("Process %s for job %s already exited", pid, job_id)
            return False
        except Exception as exc:
            logger.warning("Failed to stop process %s for job %s: %s", pid, job_id, exc)
            return False

    def delete_job(self, job_id: str) -> bool:
        job_dir = self._job_dir(job_id)
        if not job_dir.exists():
            return False
        self.stop_process(job_id)
        try:
            shutil.rmtree(job_dir)
            logger.info("Deleted job directory for %s", job_id)
            return True
        except Exception as exc:
            logger.error("Failed to delete job directory for %s: %s", job_id, exc)
            return False

    def list_jobs(self) -> List[str]:
        """Return all job IDs currently stored on disk."""
        try:
            return [p.name for p in self.workdir_base.iterdir() if p.is_dir()]
        except Exception as exc:
            logger.error("Failed to list jobs in %s: %s", self.workdir_base, exc)
            return []

    def cleanup_old_jobs(self) -> int:
        """Remove jobs older than max_age_days or exceeding max_jobs."""
        removed = 0
        now = time.time()
        max_age_seconds = self.max_age_days * 86400

        jobs = []
        for job_id in self.list_jobs():
            job_dir = self._job_dir(job_id)
            try:
                mtime = job_dir.stat().st_mtime
                jobs.append((mtime, job_id))
            except Exception as exc:
                logger.warning("Cannot stat job dir %s: %s", job_dir, exc)

        jobs.sort(key=lambda x: x[0], reverse=True)

        for idx, (mtime, job_id) in enumerate(jobs):
            age = now - mtime
            if age > max_age_seconds or idx >= self.max_jobs:
                if self.delete_job(job_id):
                    removed += 1

        if removed:
            logger.info("Cleaned up %s old job directories", removed)
        return removed
