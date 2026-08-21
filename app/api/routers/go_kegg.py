"""
GO/KEGG Enrichment Analysis Router

Provides hypergeometric-test based enrichment for GO terms
and KEGG pathways against the wheat_function database.
"""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import json
import math
import re
from pathlib import Path
from typing import Optional, List

from app.core.config import settings
from app.db.mysql import mysql_cursor

# Router with no prefix — canonical endpoints are /go, /kegg, /go/genes,
# /kegg/genes. The legacy /go-kegg/... paths are kept as hidden aliases
# (include_in_schema=False) so existing links/scripts keep working.
router = APIRouter(prefix="", tags=["GO/KEGG Enrichment"])


# ============================================================
# Bundled KEGG annotation dictionaries
# ============================================================
# app/services/data/kegg_ko_defs.json / kegg_pathway_names.json are built by
# scripts/build_kegg_dicts.py from clusterProfiler reference outputs. They are
# used as a fallback when the kegg_pathway / gene_kegg tables lack a name or
# definition (the tables may store pathway ids with different prefixes).
_KEGG_KO_DEFS: Optional[dict] = None
_KEGG_PATHWAY_NAMES: Optional[dict] = None


def _data_file(name: str) -> Path:
    return Path(__file__).resolve().parent.parent.parent / "services" / "data" / name


def _load_data_dict(name: str) -> dict:
    try:
        return json.loads(_data_file(name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _kegg_ko_defs() -> dict:
    global _KEGG_KO_DEFS
    if _KEGG_KO_DEFS is None:
        _KEGG_KO_DEFS = _load_data_dict("kegg_ko_defs.json")
    return _KEGG_KO_DEFS


def _kegg_pathway_names() -> dict:
    global _KEGG_PATHWAY_NAMES
    if _KEGG_PATHWAY_NAMES is None:
        _KEGG_PATHWAY_NAMES = _load_data_dict("kegg_pathway_names.json")
    return _KEGG_PATHWAY_NAMES


#: Pathway ids may carry different prefixes across tables
#: (ko00360 vs path:ko00360 vs map00360) — normalize to the 5-digit core.
_PATHWAY_CORE_RE = re.compile(r"^(?:path:)?(?:ko|map)?(\d{5})$")


def _pathway_core(pw: str) -> str:
    m = _PATHWAY_CORE_RE.match((pw or "").strip())
    return m.group(1) if m else (pw or "").strip()


# ============================================================
# Database access
# ============================================================
# wheat_function is the 15th database, surfaced as settings.DB_WHEAT_FUNCTION
# so it goes through the shared pooled mysql_cursor helper (previously this
# module opened its own raw pymysql.connect per request, bypassing the pool).


# ============================================================
# Stirling's log-factorial
# ============================================================
def ln_factorial(n: int) -> float:
    if n < 0:
        return float("nan")
    if n <= 1:
        return 0.0
    if n < 20:
        s = 0.0
        for i in range(2, n + 1):
            s += math.log(i)
        return s
    return (n * math.log(n) - n + 0.5 * math.log(2.0 * math.pi * n)
            + 1.0 / (12.0 * n) - 1.0 / (360.0 * n * n * n))


def ln_choose(n: int, k: int) -> float:
    if k < 0 or k > n:
        return float("-inf")
    if k == 0 or k == n:
        return 0.0
    return ln_factorial(n) - ln_factorial(k) - ln_factorial(n - k)


# ============================================================
# Hypergeometric p-value (upper tail)
# ============================================================
def hypergeometric_pval(k: int, K: int, n: int, N: int) -> float:
    if k <= 0 or K <= 0 or n <= 0:
        return 1.0
    p_value = 0.0
    min_i = min(n, K)
    log_denom = ln_choose(N, n)
    expected = K * n / N

    if k > expected:
        lo = max(0, n + K - N)
        lower_tail = 0.0
        for i in range(lo, k):
            log_num = ln_choose(K, i) + ln_choose(N - K, n - i)
            lower_tail += math.exp(log_num - log_denom)
        return max(0.0, min(1.0, 1.0 - lower_tail))

    for i in range(k, min_i + 1):
        log_num = ln_choose(K, i) + ln_choose(N - K, n - i)
        prob = math.exp(log_num - log_denom)
        p_value += prob
        if prob < 1e-308:
            break

    return max(0.0, min(1.0, p_value))


# ============================================================
# Benjamini-Hochberg FDR correction (in-place)
# ============================================================
def bh_correction(items: List[dict], pval_key: str = "pvalue"):
    items.sort(key=lambda x: x.get(pval_key, 1.0))
    m = len(items)
    for i in range(m):
        rank = i + 1
        items[i]["padj"] = items[i][pval_key] * m / rank
    for i in range(m - 2, -1, -1):
        items[i]["padj"] = min(items[i]["padj"], items[i + 1]["padj"])
    for item in items:
        item["padj"] = min(item["padj"], 1.0)


# ============================================================
# Request / Response models
# ============================================================
class EnrichmentRequest(BaseModel):
    genes: List[str]
    padj_threshold: float = 0.05

    class Config:
        json_schema_extra = {
            "example": {
                "genes": ["TraesCS1A02G045300.1", "TraesCS1A02G104700.1", "TraesCS1A02G118400.1"],
                "padj_threshold": 0.05,
            }
        }


class EnrichmentResult(BaseModel):
    id: str
    term: Optional[str] = ""
    ontology: Optional[str] = ""
    name: Optional[str] = ""   # KEGG pathway name (GO results leave it empty)
    k: int
    K: int
    ratio: float
    pvalue: float
    padj: float


class EnrichmentResponse(BaseModel):
    N: int
    n: int
    results: List[EnrichmentResult]
    gene_count: int

    class Config:
        json_schema_extra = {
            "example": {
                "N": 73626,
                "n": 3,
                "results": [
                    {
                        "id": "GO:0043425",
                        "term": "bHLH transcription factor binding",
                        "ontology": "molecular_function",
                        "k": 1,
                        "K": 4,
                        "ratio": 6135.5,
                        "pvalue": 0.000162,
                        "padj": 0.009779,
                    }
                ],
                "gene_count": 3,
            }
        }


# ============================================================
# GO Enrichment
# ============================================================
@router.post(
    "/go",
    summary="GO Enrichment Analysis",
    description="对用户提交的基因列表进行 **GO (Gene Ontology) 富集分析**。\n\n"
                "**统计方法**: 超几何检验 (hypergeometric test) + Benjamini-Hochberg FDR 多重检验校正。\n\n"
                "**背景基因集**: wheat_function.gene_go 中所有有 GO 注释的基因。\n\n"
                "**输入**: 基因 ID 列表 (IWGSC RefSeq v1.1, 如 `TraesCS1A02G045300.1`)。\n\n"
                "**输出**: 显著富集的 GO term 列表。",
    response_model=EnrichmentResponse,
)
@router.post("/go-kegg/go", include_in_schema=False)
def go_enrichment(req: EnrichmentRequest):
    genes = list(set(req.genes))
    if not genes:
        return JSONResponse({"error": "No genes provided"}, status_code=400)
    if len(genes) > 2000:
        return JSONResponse(
            {"error": f"Too many genes ({len(genes)}); maximum is 2000 per enrichment request"},
            status_code=400,
        )

    with mysql_cursor(settings.DB_WHEAT_FUNCTION) as cur:
        cur.execute("SELECT COUNT(DISTINCT gene_id) AS cnt FROM gene_go")
        N = int(cur.fetchone()["cnt"])

        ph = ",".join(["%s"] * len(genes))
        cur.execute(
            f"SELECT DISTINCT gene_id FROM gene_go WHERE gene_id IN ({ph})", genes
        )
        valid = [r["gene_id"] for r in cur.fetchall()]
        n = len(valid)
        if n == 0:
            return {"N": N, "n": 0, "results": [], "gene_count": len(genes)}

        # Overlap counts
        ph = ",".join(["%s"] * len(valid))
        cur.execute(
            f"SELECT go_id, COUNT(DISTINCT gene_id) AS k FROM gene_go WHERE gene_id IN ({ph}) GROUP BY go_id",
            valid,
        )
        overlap_rows = cur.fetchall()
        go_ids = [r["go_id"] for r in overlap_rows]
        overlap_map = {r["go_id"]: int(r["k"]) for r in overlap_rows}

        # Background counts
        go_ph = ",".join(["%s"] * len(go_ids))
        cur.execute(
            f"SELECT go_id, COUNT(DISTINCT gene_id) AS K FROM gene_go WHERE go_id IN ({go_ph}) GROUP BY go_id",
            go_ids,
        )
        bg_map = {r["go_id"]: int(r["K"]) for r in cur.fetchall()}

        # Term names
        cur.execute(
            f"SELECT go_id, term, ontology FROM go_term WHERE go_id IN ({go_ph})",
            go_ids,
        )
        term_map = {r["go_id"]: r for r in cur.fetchall()}

    results = []
    for go_id in go_ids:
        k = overlap_map.get(go_id, 0)
        K = bg_map.get(go_id, 0)
        if K == 0:
            continue
        pval = hypergeometric_pval(k, K, n, N)
        ratio = (k / n) / (K / N) if n > 0 and K > 0 else 0.0
        term_info = term_map.get(go_id, {})
        results.append(
            {
                "id": go_id,
                "term": term_info.get("term", go_id),
                "ontology": term_info.get("ontology", "unknown"),
                "k": k,
                "K": K,
                "ratio": round(ratio, 4),
                "pvalue": pval,
            }
        )

    bh_correction(results)
    results = [r for r in results if r["padj"] <= req.padj_threshold]
    results.sort(key=lambda x: x["padj"])

    return {"N": N, "n": n, "results": results, "gene_count": len(genes)}


# ============================================================
# KEGG Enrichment
# ============================================================
@router.post(
    "/kegg",
    summary="KEGG Pathway Enrichment Analysis",
    description="对用户提交的基因列表进行 **KEGG 通路富集分析**。\n\n"
                "**统计方法**: 超几何检验 + Benjamini-Hochberg FDR 校正。\n\n"
                "**背景基因集**: wheat_function.gene_kegg 中所有有 KEGG 注释的基因。\n\n"
                "**映射链**: gene_id → KO → pathway (通过 ko_pathway 和 kegg_pathway 表关联)。\n\n"
                "**输入/输出**: 格式与 GO 富集一致。",
    response_model=EnrichmentResponse,
)
@router.post("/go-kegg/kegg", include_in_schema=False)
def kegg_enrichment(req: EnrichmentRequest):
    genes = list(set(req.genes))
    if not genes:
        return JSONResponse({"error": "No genes provided"}, status_code=400)
    if len(genes) > 2000:
        return JSONResponse(
            {"error": f"Too many genes ({len(genes)}); maximum is 2000 per enrichment request"},
            status_code=400,
        )

    with mysql_cursor(settings.DB_WHEAT_FUNCTION) as cur:
        cur.execute("SELECT COUNT(DISTINCT gene_id) AS cnt FROM gene_kegg")
        N = int(cur.fetchone()["cnt"])

        ph = ",".join(["%s"] * len(genes))
        cur.execute(
            f"SELECT DISTINCT gene_id FROM gene_kegg WHERE gene_id IN ({ph})", genes
        )
        valid = [r["gene_id"] for r in cur.fetchall()]
        n = len(valid)
        if n == 0:
            return {"N": N, "n": 0, "results": [], "gene_count": len(genes)}

        # Overlap via gene_kegg -> ko_pathway
        ph = ",".join(["%s"] * len(valid))
        cur.execute(
            f"""
            SELECT kp.pathway, COUNT(DISTINCT gk.gene_id) AS k
            FROM gene_kegg gk
            JOIN ko_pathway kp ON gk.ko = kp.ko
            WHERE gk.gene_id IN ({ph})
            GROUP BY kp.pathway
            """,
            valid,
        )
        overlap_rows = cur.fetchall()
        pw_ids = [r["pathway"] for r in overlap_rows]
        overlap_map = {r["pathway"]: int(r["k"]) for r in overlap_rows}

        pw_ph = ",".join(["%s"] * len(pw_ids))
        cur.execute(
            f"""
            SELECT kp.pathway, COUNT(DISTINCT gk.gene_id) AS K
            FROM gene_kegg gk
            JOIN ko_pathway kp ON gk.ko = kp.ko
            WHERE kp.pathway IN ({pw_ph})
            GROUP BY kp.pathway
            """,
            pw_ids,
        )
        bg_map = {r["pathway"]: int(r["K"]) for r in cur.fetchall()}

        # Fetch ALL pathway names and index by normalized core id — the DB may
        # store ids with different prefixes (ko00360 vs path:ko00360 vs
        # map00360), so an exact IN-match silently drops names. Fall back to
        # the bundled dictionary for pathways missing from kegg_pathway.
        cur.execute("SELECT pathway_id, pathway_name FROM kegg_pathway")
        db_names = {_pathway_core(r["pathway_id"]): r["pathway_name"]
                    for r in cur.fetchall()}
        bundle_names = _kegg_pathway_names()

    results = []
    for pw_id in pw_ids:
        k = overlap_map.get(pw_id, 0)
        K = bg_map.get(pw_id, 0)
        if K == 0:
            continue
        pval = hypergeometric_pval(k, K, n, N)
        ratio = (k / n) / (K / N) if n > 0 and K > 0 else 0.0
        core = _pathway_core(pw_id)
        name = (db_names.get(core) or bundle_names.get(pw_id)
                or bundle_names.get(core) or pw_id)
        results.append(
            {
                "id": pw_id,
                "name": name,
                "k": k,
                "K": K,
                "ratio": round(ratio, 4),
                "pvalue": pval,
            }
        )

    bh_correction(results)
    results = [r for r in results if r["padj"] <= req.padj_threshold]
    results.sort(key=lambda x: x["padj"])

    return {"N": N, "n": n, "results": results, "gene_count": len(genes)}


# ============================================================
# Gene lookup helpers (for inline table expansion in frontend)
# ============================================================
@router.get("/go/genes")
@router.get("/go-kegg/go-genes", include_in_schema=False)
def go_genes(go_id: str = Query(...), genes: str = Query("")):
    """Return which genes from the query list match a GO term."""
    gene_list = list(set([g.strip() for g in genes.split(",") if g.strip()]))
    if not gene_list:
        return {"go_id": go_id, "genes": []}

    with mysql_cursor(settings.DB_WHEAT_FUNCTION) as cur:
        ph = ",".join(["%s"] * len(gene_list))
        cur.execute(
            f"SELECT DISTINCT gene_id FROM gene_go WHERE go_id=%s AND gene_id IN ({ph}) ORDER BY gene_id",
            [go_id] + gene_list,
        )
        hits = [r["gene_id"] for r in cur.fetchall()]
    return {"go_id": go_id, "genes": hits}


@router.get("/kegg/genes")
@router.get("/go-kegg/kegg-genes", include_in_schema=False)
def kegg_genes(pathway: str = Query(...), genes: str = Query("")):
    """Return which genes from the query list match a KEGG pathway."""
    gene_list = list(set([g.strip() for g in genes.split(",") if g.strip()]))
    if not gene_list:
        return {"pathway": pathway, "genes": []}

    with mysql_cursor(settings.DB_WHEAT_FUNCTION) as cur:
        ph = ",".join(["%s"] * len(gene_list))
        cur.execute(
            f"""
            SELECT DISTINCT gk.gene_id, gk.ko
            FROM gene_kegg gk
            JOIN ko_pathway kp ON gk.ko = kp.ko
            WHERE kp.pathway=%s AND gk.gene_id IN ({ph})
            ORDER BY gk.gene_id
            """,
            [pathway] + gene_list,
        )
        rows = cur.fetchall()
        hits = sorted({r["gene_id"] for r in rows})
        ko_defs = _kegg_ko_defs()
        ko_details = []
        seen = set()
        for r in rows:
            ko = (r.get("ko") or "").replace("ko:", "")
            if (r["gene_id"], ko) in seen:
                continue
            seen.add((r["gene_id"], ko))
            ko_details.append(
                {
                    "gene_id": r["gene_id"],
                    "ko": ko,
                    "ko_description": ko_defs.get(ko, ""),
                }
            )
    return {"pathway": pathway, "genes": hits, "ko_details": ko_details}
