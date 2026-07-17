"""
GO/KEGG Enrichment Analysis Router

Provides hypergeometric-test based enrichment for GO terms
and KEGG pathways against the wheat_function database.
"""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import pymysql
import pymysql.cursors
from app.core.config import settings
from typing import Optional, List
import math

router = APIRouter(prefix="/go-kegg", tags=["GO/KEGG Enrichment"])


# ============================================================
# Database helper
# ============================================================
def get_wf_db():
    """Connect to wheat_function database."""
    return pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database="wheat_function",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


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
def go_enrichment(req: EnrichmentRequest):
    genes = list(set(req.genes))
    if not genes:
        return JSONResponse({"error": "No genes provided"}, status_code=400)

    db = get_wf_db()
    try:
        with db.cursor() as cur:
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
    finally:
        db.close()

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
def kegg_enrichment(req: EnrichmentRequest):
    genes = list(set(req.genes))
    if not genes:
        return JSONResponse({"error": "No genes provided"}, status_code=400)

    db = get_wf_db()
    try:
        with db.cursor() as cur:
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

            cur.execute(
                f"SELECT pathway_id, pathway_name FROM kegg_pathway WHERE pathway_id IN ({pw_ph})",
                pw_ids,
            )
            name_map = {r["pathway_id"]: r["pathway_name"] for r in cur.fetchall()}
    finally:
        db.close()

    results = []
    for pw_id in pw_ids:
        k = overlap_map.get(pw_id, 0)
        K = bg_map.get(pw_id, 0)
        if K == 0:
            continue
        pval = hypergeometric_pval(k, K, n, N)
        ratio = (k / n) / (K / N) if n > 0 and K > 0 else 0.0
        results.append(
            {
                "id": pw_id,
                "name": name_map.get(pw_id, pw_id),
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
@router.get("/go-genes")
def go_genes(go_id: str = Query(...), genes: str = Query("")):
    """Return which genes from the query list match a GO term."""
    gene_list = list(set([g.strip() for g in genes.split(",") if g.strip()]))
    if not gene_list:
        return {"go_id": go_id, "genes": []}

    db = get_wf_db()
    try:
        with db.cursor() as cur:
            ph = ",".join(["%s"] * len(gene_list))
            cur.execute(
                f"SELECT DISTINCT gene_id FROM gene_go WHERE go_id=%s AND gene_id IN ({ph}) ORDER BY gene_id",
                [go_id] + gene_list,
            )
            hits = [r["gene_id"] for r in cur.fetchall()]
    finally:
        db.close()
    return {"go_id": go_id, "genes": hits}


@router.get("/kegg-genes")
def kegg_genes(pathway: str = Query(...), genes: str = Query("")):
    """Return which genes from the query list match a KEGG pathway."""
    gene_list = list(set([g.strip() for g in genes.split(",") if g.strip()]))
    if not gene_list:
        return {"pathway": pathway, "genes": []}

    db = get_wf_db()
    try:
        with db.cursor() as cur:
            ph = ",".join(["%s"] * len(gene_list))
            cur.execute(
                f"""
                SELECT DISTINCT gk.gene_id
                FROM gene_kegg gk
                JOIN ko_pathway kp ON gk.ko = kp.ko
                WHERE kp.pathway=%s AND gk.gene_id IN ({ph})
                ORDER BY gk.gene_id
                """,
                [pathway] + gene_list,
            )
            hits = [r["gene_id"] for r in cur.fetchall()]
    finally:
        db.close()
    return {"pathway": pathway, "genes": hits}
