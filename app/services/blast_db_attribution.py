"""Attribute every BLAST hit to the database it came from.

Why this module exists
----------------------
A job may search several databases in one BLAST run (``-db db1 db2 ...``).
BLAST+ then *merges* the hits of all databases into one result list, and the
tabular output format (``-outfmt 6``) has **no column identifying the
database** a hit came from: the only place the database list shows up is the
run-level header of the ASCII/XML formats, not per hit. A user who searched
five databases therefore cannot tell from ``result.tsv`` which genome a hit
belongs to — and the frontend needs exactly that to jump to the right genome
browser.

This module recovers the mapping *after* BLAST has finished, without
re-running or splitting the search (E-values, merged ranking and
``-max_target_seqs`` semantics stay exactly what BLAST produced): it asks
``blastdbcmd -entry_batch`` which of the job's databases actually contain each
subject id, then rewrites ``result.tsv`` with one extra trailing column,
``sdb`` (subject database).

Attribution rules — deliberately conservative, never a guess
------------------------------------------------------------
* single-database job  -> every row gets that database (no subprocess at all);
* exactly one database contains the subject id -> that database;
* several databases contain it (e.g. a genome db plus an aggregate) ->
  ``sdb`` stays empty: BLAST genuinely cannot say which one produced the hit,
  and an empty cell is more useful downstream than a fabricated answer;
* lookup failed / id count above the safety cap -> empty column, and the
  returned stats record why (``skipped``), so callers can surface it.

The extra column is appended so the first 15 columns keep their BLAST
meaning and ``stitle`` (column 15) still ends the free-text part.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Sequence

#: Name of the appended column (documented in README / result-file docs).
DB_COLUMN = "sdb"

#: Hard cap on distinct subject ids we are willing to look up. A result table
#: that large (many queries x max_target_seqs=50000) would make
#: ``blastdbcmd -entry_batch`` slower than the BLAST run itself; the column is
#: then emitted empty rather than delaying the job.
MAX_ATTRIBUTION_IDS = 200_000

#: Per-database ``blastdbcmd`` timeout (seconds). Attribution is best effort:
#: on timeout that database is treated as "cannot confirm" -> empty cell.
BATCH_TIMEOUT_SECONDS = 120

#: Fallback "read every entry id of the database" cache. Only used when
#: ``-entry_batch`` cannot answer for a database (old BLAST builds, aliases).
#: Bounded: protein databases can carry ~10^5 ids each.
_ENTRY_ALL_CACHE: MutableMapping[tuple[str, float], frozenset[str]] = {}
_ENTRY_ALL_CACHE_MAX = 4

DEFAULT_DB_DIR = os.environ.get("BLAST_DB_DIR", "/var/www/html/getfasta/blastdb")

#: The tabular column layout produced by blast_runner (outfmt 6). Kept here
#: as documentation for the parser below: subject id is column 2 (index 1).
TABULAR_COLUMNS = (
    "qseqid", "sseqid", "pident", "ppos", "length", "mismatch", "gapopen",
    "qstart", "qend", "sstart", "send", "evalue", "bitscore", "btop", "stitle",
)


def _default_blastdbcmd() -> str:
    found = shutil.which("blastdbcmd")
    return found or "/usr/bin/blastdbcmd"


def _db_path(db: str, db_dir: str | Path) -> str:
    """Resolve a BLAST database name inside ``db_dir`` (multi-volume aware)."""
    return os.path.join(str(db_dir), db)


def _db_mtime(db: str, db_dir: str | Path) -> float:
    """Newest index-file mtime for a database, used as cache key."""
    best = 0.0
    base = _db_path(db, db_dir)
    for ext in (".pin", ".psq", ".nin", ".nsq", ".pal", ".nal"):
        try:
            best = max(best, os.path.getmtime(base + ext))
        except OSError:
            continue
    return best


def _run_blastdbcmd(cmd: Sequence[str], timeout: float) -> tuple[str, str, int]:
    """Run blastdbcmd, returning (stdout, stderr, returncode); never raises."""
    try:
        proc = subprocess.run(
            list(cmd), capture_output=True, text=True, timeout=timeout
        )
        return proc.stdout or "", proc.stderr or "", proc.returncode
    except subprocess.TimeoutExpired:
        return "", f"timeout after {timeout}s", -1
    except OSError as exc:  # missing binary / permission
        return "", str(exc), -2


def _ids_by_entry_batch(
    db: str, ids: Sequence[str], *, blastdbcmd: str, db_dir: str | Path,
    timeout: float,
) -> frozenset[str] | None:
    """Return the subset of ``ids`` present in ``db`` (None = lookup failed).

    Uses one ``blastdbcmd -entry_batch`` call: a single subprocess per database
    per job, independent of the number of hits.
    """
    handle, batch_path = tempfile.mkstemp(prefix="blast_ids_", suffix=".txt")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as fh:
            for seqid in ids:
                fh.write(seqid + "\n")
        out, err, rc = _run_blastdbcmd(
            [blastdbcmd, "-db", _db_path(db, db_dir),
             "-entry_batch", batch_path, "-outfmt", "%a"],
            timeout,
        )
    finally:
        try:
            os.unlink(batch_path)
        except OSError:
            pass

    found = {line.strip() for line in out.splitlines() if line.strip()}
    if found:
        return frozenset(found)
    if rc == 0:
        # Clean run with no output: the database matched none of the ids.
        return frozenset()
    # rc != 0 with no parseable output -> caller may fall back to -entry all.
    return None


def _ids_by_entry_all(
    db: str, *, blastdbcmd: str, db_dir: str | Path, timeout: float,
) -> frozenset[str] | None:
    """Read every entry id of a database (cached, size-capped fallback)."""
    key = (db, _db_mtime(db, db_dir))
    cached = _ENTRY_ALL_CACHE.get(key)
    if cached is not None:
        return cached

    out, _err, rc = _run_blastdbcmd(
        [blastdbcmd, "-db", _db_path(db, db_dir), "-entry", "all", "-outfmt", "%a"],
        timeout,
    )
    if rc != 0 or not out:
        return None
    ids = frozenset(line.strip() for line in out.splitlines() if line.strip())
    if not ids:
        return None
    if len(ids) > MAX_ATTRIBUTION_IDS:
        return None
    while len(_ENTRY_ALL_CACHE) >= _ENTRY_ALL_CACHE_MAX:
        _ENTRY_ALL_CACHE.pop(next(iter(_ENTRY_ALL_CACHE)))
    _ENTRY_ALL_CACHE[key] = ids
    return ids


def _collect_subject_ids(tsv_path: Path) -> "OrderedDict[str, None]":
    """Distinct subject ids in file order, capped at MAX_ATTRIBUTION_IDS+1."""
    seen: "OrderedDict[str, None]" = OrderedDict()
    with open(tsv_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            cols = line.rstrip("\r\n").split("\t")
            if len(cols) < 2:
                continue
            seen.setdefault(cols[1], None)
            if len(seen) > MAX_ATTRIBUTION_IDS:
                break
    return seen


def _resolve(
    subject_ids: Iterable[str], dbs: Sequence[str], hits_by_db: Mapping[str, frozenset[str]]
) -> tuple[dict[str, str], dict[str, int]]:
    """Apply the attribution rules; returns (sdb map, counters)."""
    mapping: dict[str, str] = {}
    counters = {"attributed": 0, "ambiguous": 0, "unattributed": 0}
    if len(dbs) == 1:
        only = dbs[0]
        for sid in subject_ids:
            mapping[sid] = only
        counters["attributed"] = len(mapping)
        return mapping, counters

    for sid in subject_ids:
        candidates = [db for db in dbs if sid in hits_by_db[db]]
        if len(candidates) == 1:
            mapping[sid] = candidates[0]
            counters["attributed"] += 1
        elif len(candidates) > 1:
            counters["ambiguous"] += 1
        else:
            counters["unattributed"] += 1
    return mapping, counters


def _rewrite_with_db_column(tsv_path: Path, mapping: Mapping[str, str]) -> int:
    """Append the ``sdb`` column to every row; returns the number of rows."""
    tmp_path = tsv_path.with_name(tsv_path.name + ".tmp")
    rows = 0
    with open(tsv_path, "r", encoding="utf-8", errors="replace") as src, \
            open(tmp_path, "w", encoding="utf-8", newline="") as dst:
        for line in src:
            stripped = line.rstrip("\r\n")
            if not stripped:
                continue
            cols = stripped.split("\t")
            sdb = mapping.get(cols[1], "") if len(cols) > 1 else ""
            dst.write(stripped + "\t" + sdb + "\n")
            rows += 1
    os.replace(tmp_path, tsv_path)
    return rows


def attribute_tabular(
    tsv_path: str | Path,
    dbs: Sequence[str],
    *,
    blastdbcmd: str | None = None,
    db_dir: str | Path | None = None,
    timeout: float = BATCH_TIMEOUT_SECONDS,
) -> dict:
    """Rewrite a tabular BLAST result with a trailing ``sdb`` column.

    Args:
        tsv_path: path to ``result.tsv`` (outfmt 6, 15 columns, no header).
        dbs: the databases the job searched (from ``params.json``).
        blastdbcmd: blastdbcmd executable (defaults to PATH lookup).
        db_dir: BLAST database directory (defaults to ``$BLAST_DB_DIR``).
        timeout: per-database lookup timeout.

    Returns:
        Stats dict ``{rows, attributed, ambiguous, unattributed, databases,
        skipped}``. The file is always rewritten (possibly with an empty
        column), so the output schema does not depend on lookup success.

    The function is best effort by design: it never raises for a normal
    I/O/subprocess problem, and never fabricates an attribution.
    """
    path = Path(tsv_path)
    stats: dict = {
        "rows": 0,
        "attributed": 0,
        "ambiguous": 0,
        "unattributed": 0,
        "databases": {},
        "skipped": None,
    }
    if not path.is_file():
        stats["skipped"] = "missing_result_file"
        return stats

    dbs = [str(db).strip() for db in dbs if str(db or "").strip()]
    if not dbs:
        stats["skipped"] = "no_databases"
        return stats

    subject_ids = _collect_subject_ids(path)
    if not subject_ids:  # no hits at all
        return stats
    if len(subject_ids) > MAX_ATTRIBUTION_IDS:
        stats["skipped"] = "too_many_subject_ids"
        subject_ids = OrderedDict()
    elif len(dbs) > 1:
        exe = blastdbcmd or _default_blastdbcmd()
        directory = db_dir if db_dir is not None else DEFAULT_DB_DIR
        ids = list(subject_ids)
        hits_by_db: dict[str, frozenset[str]] = {}
        for db in dbs:
            found = _ids_by_entry_batch(
                db, ids, blastdbcmd=exe, db_dir=directory, timeout=timeout
            )
            if found is None:
                # Fallback: read the database's full entry list (cached).
                found = _ids_by_entry_all(
                    db, blastdbcmd=exe, db_dir=directory, timeout=timeout
                )
            if found is None:
                stats["skipped"] = f"lookup_failed:{db}"
                found = frozenset()
            hits_by_db[db] = found
    else:
        hits_by_db = {}

    mapping: dict[str, str] = {}
    if subject_ids:
        mapping, counters = _resolve(subject_ids, dbs, hits_by_db)
        stats["attributed"] = counters["attributed"]
        stats["ambiguous"] = counters["ambiguous"]
        stats["unattributed"] = counters["unattributed"]
        by_db: dict[str, int] = {}
        for db in mapping.values():
            by_db[db] = by_db.get(db, 0) + 1
        stats["databases"] = by_db

    stats["rows"] = _rewrite_with_db_column(path, mapping)
    return stats
