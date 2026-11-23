"""Compatibility endpoint for the legacy get_fasta_bedtools.py CGI.

The old PrimerServer-era page and many external clients still call

    GET /cgi-bin/get_fasta_bedtools.py?ID=<interval|gene>&database=<db>

Apache currently serves that URL through ScriptAlias. This route implements the
same contract in the FastAPI app so the CGI can be retired: it resolves the
legacy database name (the old names often lack the ploidy prefix), fetches the
sequence with blastdbcmd (list arguments, never a shell), and returns the same
HTML shell with a `<div id="seq">` block.

The route is registered without the `/api` prefix in main.py.
"""

from __future__ import annotations

import glob
import html
import re
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from app.core.config import settings
from app.core.exceptions import ExternalToolFailure, ValidationFailure
from app.api.routers.sequence import (
    _blastdbcmd_path,
    _candidate_entries,
    _check_db_exists,
    _pick_existing_entry,
    _try_interval,
)
from app.services.command_runner import run_command

router = APIRouter(tags=["Legacy CGI compatibility"])

_INTERVAL_RE = re.compile(r"^([^:]+):(\d+)-(\d+)$")


def _resolve_database(name: str) -> str:
    """Resolve an old database name to the current BLAST database name.

    Exact names win. Old PrimerServer URLs often omit the ploidy prefix
    (JM47.genome_Chr6B), while the current library stores
    AABBDD_JM47.genome_Chr6B; try that suffix match and prefer AABBDD_*.
    """
    name = (name or "").strip()
    if not name or "/" in name or "\\" in name or ".." in name:
        raise ValidationFailure(f"Invalid database name: {name!r}")

    root = Path(settings.BLAST_DB_PATH)
    if _check_db_exists(root / name):
        return name

    pattern = str(root / ("*" + glob.escape(name)))
    candidates = []
    for path in glob.glob(pattern):
        if _check_db_exists(Path(path)):
            candidates.append(Path(path).name)
    if candidates:
        # Prefer the hexaploid aggregate-style prefix, then the shortest name.
        candidates.sort(key=lambda item: (0 if item.startswith("AABBDD_") else 1, len(item), item))
        return candidates[0]

    raise ValidationFailure(
        f"BLAST database {name!r} not found under {root} (old name without a "
        "ploidy prefix is supported only when a matching database exists)."
    )


def _fetch_entry(db: str, entry: str) -> str:
    """Fetch one whole sequence by entry name (gene mode of the old CGI)."""
    database = Path(settings.BLAST_DB_PATH) / db
    try:
        completed = run_command([
            _blastdbcmd_path(), "-db", str(database), "-entry", entry,
            "-line_length", "110",
        ])
        return completed.stdout
    except ExternalToolFailure:
        return ""


def _fetch_fasta(db: str, raw_id: str) -> str:
    raw_id = raw_id.strip()
    if not raw_id:
        return ""
    match = _INTERVAL_RE.match(raw_id)
    if match:
        chrom, start_text, end_text = match.groups()
        start, end = int(start_text), int(end_text)
        if start < 1 or end <= start:
            raise ValidationFailure(f"Invalid interval: {raw_id!r}")
        return _try_interval(Path(settings.BLAST_DB_PATH) / db, chrom, start, end)

    # Gene mode: old CGI accepts one or more IDs; keep the interface permissive
    # but never interpolate an ID into a shell command.
    for candidate in _candidate_entries(raw_id):
        entry = _pick_existing_entry(candidate, Path(settings.BLAST_DB_PATH) / db)
        if entry:
            return _fetch_entry(db, entry)
    raise ValidationFailure(f"No BLAST entry found for {raw_id!r} in {db!r}")


def _page(sequence_text: str) -> str:
    safe = html.escape(sequence_text or "")
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        "<title>Get Sequence</title>"
        "<link rel=\"shortcut icon\" href=\"/favicon.ico\">"
        "<link rel=\"stylesheet\" href=\"/css/bootstrap-4.5.3-dist/css/bootstrap.css\">"
        "</head><body><div id=\"home_content\"><pre>"
        "<div id=\"seq\">" + safe + "</div></pre></div></body></html>"
    )


@router.get("/cgi-bin/get_fasta_bedtools.py", response_class=HTMLResponse)
def legacy_get_fasta(
    ID: str = Query(..., description="One or more intervals/IDs, whitespace-separated"),
    database: str = Query(..., description="BLAST database name (legacy or current)"),
) -> HTMLResponse:
    """Drop-in replacement for the legacy get_fasta_bedtools.py CGI."""
    try:
        db = _resolve_database(database)
        chunks = []
        for raw_id in str(ID).split():
            fasta = _fetch_fasta(db, raw_id)
            if fasta.strip():
                chunks.append(fasta.rstrip())
        if not chunks:
            raise ValidationFailure("No sequence returned for the requested ID(s)")
        return HTMLResponse(_page("\n".join(chunks)))
    except ValidationFailure as exc:
        return HTMLResponse(_page(f"Error: {exc.detail}"))
    except Exception as exc:  # keep the legacy page shape even on failure
        return HTMLResponse(_page(f"Error: {exc}"))