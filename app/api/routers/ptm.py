"""wheatPTM — wheat protein post-translational modification sites.

The wheat sites are predicted with PlantPTM (Dou et al., Molecular Plant
19:1979-1995, 2026; doi:10.1016/j.molp.2026.08.002) and imported from its
output CSV files (all_pho.csv, all_NGly.csv, ...) into the ``ptm`` MySQL
database by ``scripts/import_ptm_mysql.py``. Each PTM type lives in its own
table with the same 8 columns:

    gene_id, Protein, Position, Residue, Peptide, PTM_type, Score, Confidence

This router searches a protein across all 9 PTM tables and returns the merged
site list (for the table + dot plot) plus a CSV download.

Source tables contain *predictions*, including rows whose ``Confidence`` is
``Non-PTM`` (the source tools' negative class). Callers can therefore narrow a
query with ``scope``::

    all   — every predicted row (default, backward compatible)
    ptm   — PTM calls only, i.e. ``Confidence != 'Non-PTM'``
    high  — ``Confidence IN ('High', 'Extremely high')``

Every response also reports a ``known`` flag (is the protein in the dataset at
all?) and ``confidence_counts`` so the UI can label counts honestly instead of
calling every prediction a "PTM site".
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter

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

#: Confidence label used by the source predictors for their negative class.
NON_PTM = "Non-PTM"

#: Confidence labels treated as "high confidence" by the ``high`` scope.
HIGH_CONFIDENCE = ("High", "Extremely high")

#: Accepted ``scope`` values -> human description (used for error messages).
SCOPE_LABELS = {
    "all": "all predicted sites, including Non-PTM",
    "ptm": "PTM calls only (Non-PTM excluded)",
    "high": "high-confidence calls only (High / Extremely high)",
}


def _validate_scope(scope: str) -> str:
    """Normalise and validate the ``scope`` query parameter."""
    scope = (scope or "all").strip().lower()
    if scope not in SCOPE_LABELS:
        raise ValidationFailure(
            f"scope must be one of {', '.join(SCOPE_LABELS)}, got {scope!r}"
        )
    return scope


def _scope_clause(scope: str) -> tuple[str, tuple]:
    """Return the extra SQL fragment + params that narrow rows to ``scope``."""
    if scope == "ptm":
        return " AND `Confidence` <> %s", (NON_PTM,)
    if scope == "high":
        return " AND `Confidence` IN (%s, %s)", HIGH_CONFIDENCE
    return "", ()


def _query_sites(protein: str, scope: str = "all") -> tuple[list[dict], list[dict]]:
    sites: list[dict] = []
    stats: list[dict] = []
    extra_sql, extra_params = _scope_clause(scope)
    columns = ", ".join("`" + c + "`" for c in SITE_COLUMNS)
    with mysql_connection(settings.DB_PTM) as conn:
        with conn.cursor() as cur:
            for table, label in PTM_TABLES:
                # 精确匹配（用户输入完整蛋白 ID），配合 Protein 索引可走索引查找
                cur.execute(
                    f"SELECT {columns} FROM `{table}` "
                    f"WHERE `Protein` = %s{extra_sql}",
                    (protein, *extra_params),
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


def _protein_exists(protein: str) -> bool:
    """Is this protein referenced by at least one PTM row?

    Only needed for the edge case where a caller narrows ``scope`` so much that
    every row is filtered out: ``total == 0`` alone would then be mistaken for
    "protein not in the dataset".
    """
    try:
        with mysql_connection(settings.DB_PTM) as conn:
            with conn.cursor() as cur:
                for table, _ in PTM_TABLES:
                    cur.execute(
                        f"SELECT 1 FROM `{table}` WHERE `Protein` = %s LIMIT 1",
                        (protein,),
                    )
                    if cur.fetchone():
                        return True
    except Exception:
        return False
    return False


def _safe_filename(protein: str) -> str:
    """Keep protein IDs from breaking the Content-Disposition header."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", protein) or "protein"


@router.get("/search")
def search_ptm(
    protein: str = Query(..., min_length=1, description="Protein ID, e.g. TraesCS1A02G000100LC.1"),
    scope: str = Query("all", description="all | ptm | high"),
) -> dict:
    """按蛋白 ID 搜索其所有 PTM 位点（跨 9 种 PTM 类型）。

    用法:
        GET /api/ptm/search?protein=TraesCS1A02G000100LC.1
        GET /api/ptm/search?protein=TraesCS1A02G000100LC.1&scope=ptm

    ``sites``/``stats``/``confidence_counts`` always describe the requested
    ``scope``; ``known`` says whether the protein exists in the dataset at all.
    """
    protein = protein.strip()
    if not protein:
        raise ValidationFailure("protein is required")
    scope = _validate_scope(scope)

    sites, stats = _query_sites(protein, scope)
    length = _query_length(protein)
    total = len(sites)
    confidence_counts = dict(Counter((s.get("Confidence") or "Unknown") for s in sites))
    known = (
        length is not None
        or total > 0
        or (scope != "all" and _protein_exists(protein))
    )

    return ok({
        "protein": protein,
        "length": length,
        "known": known,
        "scope": scope,
        "total": total,
        "total_ptm_calls": total - confidence_counts.get(NON_PTM, 0),
        "total_non_ptm": confidence_counts.get(NON_PTM, 0),
        "confidence_counts": confidence_counts,
        "stats": stats,
        "sites": sites,
    })


@router.get("/download")
def download_ptm(
    protein: str = Query(..., min_length=1, description="Protein ID"),
    scope: str = Query("all", description="all | ptm | high"),
) -> Response:
    """下载某蛋白的全部 PTM 位点为 CSV（``scope`` 与搜索接口一致）。"""
    protein = protein.strip()
    if not protein:
        raise ValidationFailure("protein is required")
    scope = _validate_scope(scope)

    sites, _ = _query_sites(protein, scope)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(SITE_COLUMNS + ["PTM_type_name"])
    for s in sites:
        writer.writerow(
            [s[c] for c in SITE_COLUMNS] + [s["ptm_label"]]
        )
    suffix = "" if scope == "all" else f"_{scope}"
    filename = f"{_safe_filename(protein)}_ptm_sites{suffix}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-PTM-Scope": scope,
            "X-PTM-Rows": str(len(sites)),
        },
    )
