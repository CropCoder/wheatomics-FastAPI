"""Progress reporting helpers for PrimerServer2 pipeline."""

import sys
from typing import Optional, TextIO


PROGRESS_MARKER = "__PRIMERSERVER_PROGRESS__"


_progress_fh: Optional[TextIO] = None


def set_progress_file(fh: Optional[TextIO]) -> None:
    """Set a default file handle for progress markers."""
    global _progress_fh
    _progress_fh = fh


def log_progress(percent: int, stage: str, fh: Optional[TextIO] = None) -> None:
    """Write a PrimerServer2 progress marker to the log stream.

    The pipeline log parser looks for lines matching:
        __PRIMERSERVER_PROGRESS__ {percent} {stage}
    """
    target = fh or _progress_fh or sys.stderr
    try:
        target.write(f"{PROGRESS_MARKER} {percent} {stage}\n")
        target.flush()
    except ValueError:
        # File handle closed (timeout/restart), fall back to stderr
        sys.stderr.write(f"{PROGRESS_MARKER} {percent} {stage}\n")
        sys.stderr.flush()
