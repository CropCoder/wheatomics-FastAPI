"""Controlled subprocess helpers for external bioinformatics tools."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

from app.core.config import settings
from app.core.exceptions import ExternalToolFailure


def run_command(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int | None = None,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command without shell interpolation and raise a structured error on failure."""

    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            input=stdin,
            timeout=timeout or settings.REQUEST_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExternalToolFailure(f"Command timed out: {' '.join(command)}") from exc
    except OSError as exc:
        raise ExternalToolFailure(f"Failed to execute command: {' '.join(command)}") from exc

    if completed.returncode != 0:
        stderr = (completed.stderr or completed.stdout or "").strip()
        raise ExternalToolFailure(stderr or f"Command failed: {' '.join(command)}")

    return completed
