"""wheatPSP — wheat phase separation-associated proteins.

Data is imported from fangenome_ps_results.csv into the ``wheat_psp`` MySQL
table (see scripts/import_wheat_psp.py). This router exposes search, PSP/PrD
listings, per-protein detail, and TSV downloads, backing a ricePSP-style SPA.
"""

from __future__ import annotations

from typing import Iterator

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.exceptions import ResourceNotFound, ValidationFailure
from app.core.response import ok
from app.db.mysql import mysql_connection

router = APIRouter(prefix="/wheatpsp", tags=["wheatPSP"])

_COLUMNS = (
    "id", "seq_id", "gene_id", "seq_length", "ps_score", "is_psp",
    "molphase_score", "has_prd", "error", "plaac_llr", "plaac_core_score",
    "plaac_papa_prop", "plaac_papa_fi",
)

_DOWNLOAD_TABLES = ("allProteins", "PredPSPs", "PrD_Pro")


def _fmt_ps(v) -> str:
    return "%.4f" % v if v is not None else ""


def _fmt_llr(v) -> str:
    return "%.3f" % v if v is not None else ""


def _list(where: str, args: list, page: int, per_page: int) -> dict:
    per_page = min(max(per_page, 1), 100)
    offset = (page - 1) * per_page
    with mysql_connection(settings.DB_WHEATPSP) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS n FROM wheat_psp {where}", args)
            total = cur.fetchone()["n"]
            cur.execute(
                f"SELECT * FROM wheat_psp {where} ORDER BY id LIMIT %s OFFSET %s",
                args + [per_page, offset],
            )
            rows = cur.fetchall()
    return {"total": total, "page": page, "per_page": per_page, "rows": rows}


def _iter_download(table: str) -> Iterator[str]:
    if table == "allProteins":
        sql = "SELECT seq_id, gene_id, ps_score FROM wheat_psp ORDER BY id"
    elif table == "PredPSPs":
        sql = "SELECT seq_id, gene_id, ps_score FROM wheat_psp WHERE is_psp = 1 ORDER BY id"
    else:  # PrD_Pro
        sql = "SELECT seq_id, gene_id, plaac_llr FROM wheat_psp WHERE has_prd = 1 ORDER BY id"

    with mysql_connection(settings.DB_WHEATPSP) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            i = 0
            for row in cur:
                i += 1
                if table == "PrD_Pro":
                    yield f"{i}. {row['seq_id']}\t{row['gene_id']}\t{_fmt_llr(row['plaac_llr'])}\t\n"
                else:
                    yield f"{row['seq_id']}\t{row['gene_id']}\t{_fmt_ps(row['ps_score'])}\n"


@router.get("/stats")
def api_stats():
    """数据库统计：总蛋白数、预测 PSP 数、PrD 蛋白数。"""
    with mysql_connection(settings.DB_WHEATPSP) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS total, "
                "COALESCE(SUM(is_psp), 0) AS psp, "
                "COALESCE(SUM(has_prd), 0) AS prd "
                "FROM wheat_psp WHERE cs_gene_id IS NOT NULL"
            )
            row = cur.fetchone()
    return ok({
        "total": int(row["total"]),
        "psp": int(row["psp"]),
        "prd": int(row["prd"]),
    })


@router.get("/search")
def api_search(
    q: str = Query("", description="seq_id / gene_id 模糊搜索"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20),
):
    """按 seq_id / gene_id 搜索蛋白，分页。"""
    q = q.strip()
    where = "WHERE cs_gene_id IS NOT NULL"
    args: list = []
    if q:
        like = f"%{q}%"
        where += " AND cs_gene_id LIKE %s"
        args = [like]
    return ok(_list(where, args, page, per_page))


@router.get("/psp")
def api_psp(
    page: int = Query(1, ge=1),
    per_page: int = Query(20),
    q: str = Query("", description="seq_id / gene_id 模糊过滤"),
):
    """预测的相分离相关蛋白（is_psp=1）列表，分页。"""
    where = "WHERE is_psp = 1 AND cs_gene_id IS NOT NULL"
    args: list = []
    if q.strip():
        like = f"%{q.strip()}%"
        where += " AND cs_gene_id LIKE %s"
        args = [like]
    return ok(_list(where, args, page, per_page))


@router.get("/prd")
def api_prd(
    page: int = Query(1, ge=1),
    per_page: int = Query(20),
    q: str = Query("", description="seq_id / gene_id 模糊过滤"),
):
    """预测的 PrD（prion-like domain）蛋白（has_prd=1）列表，分页。"""
    where = "WHERE has_prd = 1 AND cs_gene_id IS NOT NULL"
    args: list = []
    if q.strip():
        like = f"%{q.strip()}%"
        where += " AND cs_gene_id LIKE %s"
        args = [like]
    return ok(_list(where, args, page, per_page))


@router.get("/protein/{seq_id}")
def api_protein(seq_id: str):
    """单个蛋白的完整预测结果（11 个数据列）。"""
    with mysql_connection(settings.DB_WHEATPSP) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM wheat_psp WHERE seq_id = %s", (seq_id,))
            row = cur.fetchone()
    if not row:
        raise ResourceNotFound(f"Protein {seq_id} not found.")
    return ok({"protein": row})


@router.get("/download/{table}")
def api_download(table: str):
    """下载拆分表：allProteins / PredPSPs / PrD_Pro（TSV）。"""
    table = table.strip()
    if table not in _DOWNLOAD_TABLES:
        raise ValidationFailure(f"Unknown table: {table!r} (expected allProteins / PredPSPs / PrD_Pro)")
    filename = "PrD_Pro.txt" if table == "PrD_Pro" else f"{table}.table.txt"
    return StreamingResponse(
        _iter_download(table),
        media_type="text/tab-separated-values; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
