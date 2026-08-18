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


@router.get("/jbrowse/datasets")
def list_jbrowse_datasets() -> dict:
    """列出所有 JBrowse 数据集及轨道数。

    用法:
        GET /api/jbrowse/datasets

    数据来自 jbrowse_meta.jbrowse_datasets（由 scripts/import_jbrowse_meta.py
    从 JBrowse 数据目录的 trackList.json 导入）。
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
    """返回某个数据集的 JBrowse trackList.json 配置。

    用法:
        GET /api/jbrowse/datasets/Chinese_Spring1.0/trackList

    响应为裸的 JBrowse 配置对象（非统一 ok() 信封），与磁盘上的静态
    trackList.json 等价：{formatVersion, dataset_id?, names?, tracks[]}。
    tracks 按原始顺序（ord）重建，轨道对象逐字段保留。
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
        tracks = [row["track_json"] for row in cursor.fetchall()]

    payload: dict = {"formatVersion": 1, "tracks": tracks}
    if meta.get("dataset_id"):
        payload["dataset_id"] = meta["dataset_id"]
    if meta.get("has_names") and meta.get("names_json"):
        payload["names"] = meta["names_json"]

    return Response(content=json.dumps(payload), media_type="application/json")
