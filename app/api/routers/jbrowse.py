"""JBrowse genome-browser metadata routes.

Layer 1 of the JBrowse refactor: dataset and track metadata lives in the
``jbrowse_meta`` MySQL database (populated by scripts/import_jbrowse_meta.py),
and this router serves the dataset registry plus per-dataset ``trackList.json``
payloads reconstructed from those tables.

The ``trackList`` endpoint deliberately returns the *bare* JBrowse JSON (no
``ok()`` envelope): Apache proxies ``*/trackList.json`` requests to it and the
JBrowse client expects the top level of the response to be the config object
itself. The static data files (BAM/bigWig/tabix/name-trie) remain on disk and
keep being served by Apache.
"""

from __future__ import annotations

import json
import re

from fastapi import APIRouter
from fastapi.responses import Response

from app.core.config import settings
from app.core.exceptions import ResourceNotFound, ValidationFailure
from app.core.response import ok
from app.db.mysql import mysql_cursor
from app.services.blast_jbrowse_map import MAP_FILE as JBROWSE_LINK_MAP_FILE
from app.services.blast_jbrowse_map import load_map as load_jbrowse_link_map

router = APIRouter(tags=["JBrowse"])

#: Dataset ids are jbrowse-1.12.3-release subdirectory names; the same
#: allowlist pattern as the other db-name validators (no slashes, no spaces).
_DATASET_RE = re.compile(r"^[\w.\-]+$")

#: Cap on datasets whose refseq list is cached in memory. A scaffold-level
#: dataset can carry 10^5+ refseqs (AK58: 158k), so keep only a few.
_REFSEQ_CACHE_MAX = 4
_REFSEQ_CACHE: dict[str, tuple[float, list[dict]]] = {}


def _ensure_dataset_name(dataset: str) -> str:
    if not _DATASET_RE.fullmatch(dataset):
        raise ValidationFailure(f"Invalid dataset name: {dataset!r}")
    return dataset


def _loads_json(value):
    """Decode a JSON document stored as TEXT; pass through decoded values."""
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return {}
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        # A corrupted row must not take down the whole dataset listing.
        return value


@router.get("/jbrowse/datasets")
def list_jbrowse_datasets() -> dict:
    """List all JBrowse datasets and their track counts.

    Usage:
        GET /api/jbrowse/datasets

    Data comes from jbrowse_meta.jbrowse_datasets (imported by
    scripts/import_jbrowse_meta.py from the trackList.json files in the
    JBrowse data directory).
    """
    with mysql_cursor(settings.DB_JBROWSE) as cursor:
        cursor.execute(
            "SELECT id, dataset_id, track_count, has_names "
            "FROM jbrowse_datasets ORDER BY id"
        )
        rows = cursor.fetchall()

    datasets = [
        {
            "id": row["id"],
            "dataset_id": row.get("dataset_id"),
            "track_count": row["track_count"],
            "has_names": bool(row["has_names"]),
        }
        for row in rows
    ]
    return ok({"total": len(datasets), "datasets": datasets})


@router.get("/jbrowse/datasets/{dataset}/trackList")
def get_jbrowse_tracklist(dataset: str) -> Response:
    """Return the JBrowse trackList.json config of a dataset.

    Usage:
        GET /api/jbrowse/datasets/Chinese_Spring1.0/trackList

    The response is the bare JBrowse config object (not the unified ok()
    envelope), equivalent to the static trackList.json on disk:
    {formatVersion, dataset_id?, names?, tracks[]}.
    Tracks are rebuilt in their original order (ord) and each track object is
    preserved field by field.
    """
    _ensure_dataset_name(dataset)

    with mysql_cursor(settings.DB_JBROWSE) as cursor:
        cursor.execute(
            "SELECT dataset_id, has_names, names_json "
            "FROM jbrowse_datasets WHERE id = %s",
            (dataset,),
        )
        meta = cursor.fetchone()
        if not meta:
            raise ResourceNotFound(f"JBrowse dataset not found: {dataset}")

        cursor.execute(
            "SELECT track_json FROM jbrowse_tracks "
            "WHERE dataset = %s ORDER BY ord",
            (dataset,),
        )
        # `track_json` / `names_json` are stored as TEXT holding JSON docs.
        # Decode them so the payload matches the on-disk trackList.json
        # (tracks must be objects, names must be an object, not strings).
        tracks = [_loads_json(row["track_json"]) for row in cursor.fetchall()]

    payload: dict = {"formatVersion": 1, "tracks": tracks}
    if meta.get("dataset_id"):
        payload["dataset_id"] = meta["dataset_id"]
    if meta.get("has_names") and meta.get("names_json"):
        payload["names"] = _loads_json(meta["names_json"])

    return Response(content=json.dumps(payload), media_type="application/json")


# ---------------------------------------------------------------------------
# Refseq registry + BLAST/UI coverage report
# ---------------------------------------------------------------------------

def _load_refseqs(dataset: str) -> list[dict]:
    """Names + lengths of a dataset's refseqs (the JBrowse loc vocabulary).

    ``<JBROWSE_DATA_ROOT>/<dataset>/seq/refSeqs.json`` is the authoritative
    list the JBrowse 1 client itself uses, so callers can build guaranteed
    valid ``loc`` strings without guessing naming conventions. Cached by file
    mtime; only a few datasets are kept in memory (a scaffold assembly has 10^5
    refseqs).
    """
    _ensure_dataset_name(dataset)
    path = settings.JBROWSE_DATA_ROOT / dataset / "seq" / "refSeqs.json"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        raise ResourceNotFound(
            f"JBrowse dataset {dataset!r} has no seq/refSeqs.json "
            f"(dataset missing or not a chromosome-level build)"
        )
    cached = _REFSEQ_CACHE.get(dataset)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ResourceNotFound(f"Cannot read refSeqs.json for {dataset!r}: {exc}")
    rows = [
        {"name": item.get("name"), "length": item.get("length")}
        for item in (data if isinstance(data, list) else [])
        if isinstance(item, dict) and item.get("name") and isinstance(item.get("length"), int)
    ]
    while len(_REFSEQ_CACHE) >= _REFSEQ_CACHE_MAX:
        _REFSEQ_CACHE.pop(next(iter(_REFSEQ_CACHE)))
    _REFSEQ_CACHE[dataset] = (mtime, rows)
    return rows


@router.get("/jbrowse/datasets/{dataset}/refseqs")
def list_jbrowse_refseqs(dataset: str) -> dict:
    """Refseq names + lengths of one JBrowse dataset (the ``loc`` vocabulary).

    Usage:
        GET /api/jbrowse/datasets/AK58/refseqs

    Read from ``seq/refSeqs.json`` (the same list JBrowse 1 uses), so a client
    never has to guess chromosome spelling (``chr1A`` vs ``Chr1A_Sumai3``).
    """
    rows = _load_refseqs(dataset)
    return ok({"dataset": dataset, "count": len(rows), "refseqs": rows})


@router.get("/jbrowse/coverage")
def jbrowse_coverage() -> dict:
    """How well the platform can link a BLAST hit to a genome browser.

    Reports the three joins that decide whether the BLAST result page may show
    a JBrowse button:

      1. genome_registry.jbrowse_dataset  (declared browser per assembly)
      2. jbrowse_meta.jbrowse_datasets    (the dataset really exists)
      3. blast_jbrowse_map.json           (BLAST db -> JBrowse refseq mapping,
                                           assembly version checked by length)

    Intended as an ops report: run it after rebuilding JBrowse data, after
    scripts/import_jbrowse_meta.py, and after scripts/build_blast_jbrowse_map.py.
    """
    with mysql_cursor(settings.DB_LITERATURE) as cursor:
        cursor.execute(
            "SELECT dataset_id, jbrowse_dataset, blast_genome_db, "
            "blast_cds_db, blast_pep_db, visible FROM genome_registry"
        )
        registry = [dict(row) for row in cursor.fetchall()]
    with mysql_cursor(settings.DB_JBROWSE) as cursor:
        cursor.execute("SELECT id FROM jbrowse_datasets")
        jbrowse_ids = {row["id"] for row in cursor.fetchall()}

    declared = [row for row in registry if (row.get("jbrowse_dataset") or "").strip()]
    declared_ids = {(row["jbrowse_dataset"] or "").strip() for row in declared}
    declared_missing_meta = sorted(declared_ids - jbrowse_ids)
    meta_orphans = sorted(jbrowse_ids - declared_ids)
    no_jbrowse = sorted(
        row["dataset_id"] for row in registry
        if not (row.get("jbrowse_dataset") or "").strip()
    )

    link_map = load_jbrowse_link_map()
    map_meta = link_map.get("_meta") or {}
    bases = {key: value for key, value in link_map.items() if key != "_meta"}
    matched = [key for key, value in bases.items() if value.get("assembly_match")]
    mismatched = [
        {
            "base": key,
            "dataset": value.get("dataset"),
            "reason": value.get("reason"),
            "matched": value.get("matched"),
            "total": value.get("total"),
            "example": (value.get("mismatched") or [None])[0],
        }
        for key, value in sorted(bases.items())
        if not value.get("assembly_match")
    ]

    return ok({
        "registry": {
            "rows": len(registry),
            "visible": sum(1 for row in registry if row.get("visible")),
            "declares_jbrowse": len(declared),
            "no_jbrowse": len(no_jbrowse),
            "no_jbrowse_examples": no_jbrowse[:30],
        },
        "jbrowse_meta": {
            "datasets": len(jbrowse_ids),
            "declared_missing_meta": declared_missing_meta,
            "meta_orphans": meta_orphans,
        },
        "blast_link_map": {
            "file": str(JBROWSE_LINK_MAP_FILE),
            "exists": bool(bases),
            "generated_at": map_meta.get("generated_at"),
            "bases": len(bases),
            "assembly_match": len(matched),
            "mismatched": len(mismatched),
            "mismatched_examples": mismatched[:30],
            "stats": map_meta.get("stats"),
        },
        "ok": (
            not declared_missing_meta
            and bool(bases)
            and len(matched) >= max(1, int(len(bases) * 0.9))
        ),
    })
