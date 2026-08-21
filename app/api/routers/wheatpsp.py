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
    """数据库统计：总蛋白数、预测 PSP 数、PrD 蛋白数（含百分比）+ 关键得分分布。"""
    with mysql_connection(settings.DB_WHEATPSP) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT cs_gene_id) AS total, "
                "COUNT(DISTINCT CASE WHEN is_psp = 1 THEN cs_gene_id END) AS psp, "
                "COUNT(DISTINCT CASE WHEN has_prd = 1 THEN cs_gene_id END) AS prd "
                "FROM wheat_psp WHERE cs_gene_id IS NOT NULL"
            )
            row = cur.fetchone()

            def dist(expr: str, width: float, nround: int) -> dict:
                """Histogram over proteins: bin start values + counts."""
                cur.execute(
                    f"SELECT FLOOR({expr}/{width}) AS b, COUNT(*) AS n "
                    f"FROM wheat_psp WHERE {expr} IS NOT NULL "
                    f"GROUP BY b ORDER BY b"
                )
                bins, counts = [], []
                for r in cur.fetchall():
                    bins.append(round(float(r["b"]) * width, nround))
                    counts.append(int(r["n"]))
                return {"bins": bins, "counts": counts}

            distributions = {
                "ps_score": dist("ps_score", 0.1, 1),
                "molphase_score": dist("molphase_score", 0.1, 1),
                "plaac_llr": dist("plaac_llr", 2.0, 0),
                "plaac_papa_prop": dist("plaac_papa_prop", 0.1, 1),
                "seq_length": dist("seq_length", 100.0, 0),
            }
    total = max(int(row["total"] or 0), 0)
    psp = int(row["psp"] or 0)
    prd = int(row["prd"] or 0)

    def pct(n: int) -> float:
        return round(n / total * 100, 1) if total else 0.0

    return ok({
        "total": total,
        "psp": psp,
        "prd": prd,
        "psp_pct": pct(psp),
        "prd_pct": pct(prd),
        "distributions": distributions,
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
        # Match any of the three ID sets: CS 02G gene id / pan-genome gene id / seq id
        where += " AND (cs_gene_id LIKE %s OR gene_id LIKE %s OR seq_id LIKE %s)"
        args = [like, like, like]
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


@router.get("/gene/{cs_gene_id}")
def api_gene(cs_gene_id: str):
    """一个基因（CS 02G id）下的所有转录本，相分离预测并列对比。"""
    with mysql_connection(settings.DB_WHEATPSP) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT p.*, f.sequence, f.new_molphase AS feature_molphase "
                "FROM wheat_psp p LEFT JOIN wheat_psp_feature f ON p.seq_id = f.seq_id "
                "WHERE p.cs_gene_id = %s ORDER BY p.id",
                (cs_gene_id,),
            )
            rows = cur.fetchall()
    if not rows:
        raise ResourceNotFound(f"No wheatPSP record for gene {cs_gene_id}.")
    return ok({"cs_gene_id": cs_gene_id, "transcripts": rows})


@router.get("/protein/{seq_id}")
def api_protein(seq_id: str):
    """单个蛋白的完整预测结果 + 序列 + 理化性质（来自 fangenome.csv）。"""
    with mysql_connection(settings.DB_WHEATPSP) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT p.*, f.sequence, f.new_molphase AS feature_molphase, "
                "f.idr_percentage, f.pi_pi, f.prion_like, f.lcr_percentage, "
                "f.shannon_entropy, f.fcr, f.ncpr, f.kappa, f.omega, "
                "f.hydrophobicity, f.ppii_propensity, f.aa_composition, "
                "f.polar, f.hydrophobic, f.aromatic, f.cationic, f.anionic, "
                "f.expanding, f.disorder_promoting "
                "FROM wheat_psp p LEFT JOIN wheat_psp_feature f ON p.seq_id = f.seq_id "
                "WHERE p.seq_id = %s",
                (seq_id,),
            )
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
