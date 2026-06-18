"""Filesystem helpers for task outputs."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path


def make_job_dir(base_dir: Path, prefix: str) -> Path:
    """Create an isolated job directory under the provided base directory."""

    job_dir = base_dir / f"{prefix}_{uuid.uuid4().hex[:10]}"
    job_dir.mkdir(parents=True, exist_ok=False)
    return job_dir


def write_lines(path: Path, lines: list[str]) -> None:
    """Write text lines preserving newline separation."""

    normalized = [line if line.endswith("\n") else f"{line}\n" for line in lines]
    path.write_text("".join(normalized), encoding="utf-8")


def pack_directory(source_dir: Path, archive_base: Path) -> Path:
    """Create a gzipped tar archive for a result directory."""

    archive_path = shutil.make_archive(str(archive_base), "gztar", root_dir=str(source_dir.parent), base_dir=source_dir.name)
    return Path(archive_path)
