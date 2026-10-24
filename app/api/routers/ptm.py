"""wheatPTM — wheat protein post-translational modification sites.

Data is imported from the PlantPTM-style CSV files (all_pho.csv, all_Ngly.csv,
...) into the ``ptm`` MySQL database by scripts/import_ptm_mysql.py. Each PTM
type lives in its own table with the same 8 columns:

    gene_id, Protein, Position, Residue, Peptide, PTM_type, Score, Confidence

This router searches a protein across all 9 PTM tables, returns the merged
site list (for the table + dot plot) and a CSV download.
"""

from __future__ import annotations

import csv
import io
from typing import Iterator

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.core.config import settings
from app.core.exceptions import ValidationFailure
from app.core.response import ok
from app.db.mysql import mysql_connection

router = APIRouter(prefix="/ptm", tags=["wheatPTM"])

#: PTM table name -> human label (used for the dot-plot legend / colour key).
PTM_TABLES = [
    ("pho", "Phosphorylation"),
    ("ngly", "N-glycosylation"),
    ("sacy", "S-acylation"),
    ("khib", "2-hydroxyisobutyrylation"),
    ("kcro", "Crotonylation"),
    ("ksucc", "Succinylation"),
    ("kmal", "Malonylation"),
    ("kac", "Acetylation"),
    ("kub", "Ubiquitination"),
]

#: Columns shared by every PTM table (in table order).
SITE_COLUMNS = [
    "gene_id", "Protein", "Position", "Residue", "Peptide",
    "PTM_type", "Score", "Confidence",
]


def _query_sites(protein: str) -> tuple[list[dict], list[dict]]:
    sites: list[dict] = []
    stats: list[dict] = []
    with mysql_connection(settings.DB_PTM) as conn:
        with conn.cursor() as cur:
            for table, label in PTM_TABLES:
                # 精确匹配（用户输入完整蛋白 ID），配合 Protein 索引可走索引查找
                cur.execute(
                    f"SELECT {', '.join('`' + c + '`' for c in SITE_COLUMNS)} "
                    f"FROM `{table}` WHERE Protein = %s",
                    (protein,),
                )
                rows = cur.fetchall()
                for row in rows:
                    row["ptm_table"] = table
                    row["ptm_label"] = label
                    sites.append(row)
                stats.append({"table": table, "label": label, "count": len(rows)})
    return sites, stats


def _query_length(protein: str) -> int | None:
    """查蛋白序列长度（用于 lollipop 图的 x 轴 0~length）。"""
    try:
        with mysql_connection(settings.DB_PTM) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT length FROM protein_length WHERE Protein = %s", (protein,)
                )
                row = cur.fetchone()
                return row["length"] if row else None
    except Exception:
        return None


@router.get("/search")
def search_ptm(
    protein: str = Query(..., min_length=1, description="Protein ID, e.g. TraesCS1A02G000100LC.1"),
) -> dict:
    """按蛋白 ID 搜索其所有 PTM 位点（跨 9 种 PTM 类型）。

    用法:
        GET /api/ptm/search?protein=TraesCS1A02G000100LC.1
    """
    protein = protein.strip()
    if not protein:
        raise ValidationFailure("protein is required")

    sites, stats = _query_sites(protein)
    length = _query_length(protein)
    return ok({
        "protein": protein,
        "length": length,
        "total": len(sites),
        "stats": stats,
        "sites": sites,
    })


@router.get("/download")
def download_ptm(
    protein: str = Query(..., min_length=1, description="Protein ID"),
) -> Response:
    """下载某蛋白的全部 PTM 位点为 CSV。"""
    protein = protein.strip()
    if not protein:
        raise ValidationFailure("protein is required")

    sites, _ = _query_sites(protein)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(SITE_COLUMNS + ["PTM_type_name"])
    for s in sites:
        writer.writerow(
            [s[c] for c in SITE_COLUMNS] + [s["ptm_label"]]
        )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{protein}_ptm_sites.csv"',
        },
    )
