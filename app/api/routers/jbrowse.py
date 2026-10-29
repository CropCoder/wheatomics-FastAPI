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

router = APIRouter(tags=["JBrowse"])

#: Dataset ids are jbrowse-1.12.3-release subdirectory names; the same
#: allowlist pattern as the other db-name validators (no slashes, no spaces).
_DATASET_RE = re.compile(r"^[\w.\-]+$")


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
