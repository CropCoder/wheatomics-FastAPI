"""Triticeae Research Filter database — curated paper/trait lookup for AI agents."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.core.response import ok
from app.db.mysql import mysql_cursor
from app.schemas.triticeae import TriticeaePaper, TriticeaeSearchResult

router = APIRouter(prefix="/triticeae", tags=["Triticeae Research Filter"])


@router.get("/papers/{pubmedid}")
def get_paper(pubmedid: str) -> dict:
    """按 PubMed ID 获取单篇论文详情。

    功能:
        从 Triticeae_Research_filter 数据库检索指定 PubMed ID 的论文，
        返回基因、性状、证据类型、AI 标签等完整信息。

    用法:
        GET /api/triticeae/papers/{pubmedid}

    案例:
        curl -X GET "http://localhost:8000/api/triticeae/papers/35839760"

        响应:
        {
          "success": true,
          "data": {
            "pubmedid": "35839760",
            "pub_date": "2022 Aug 4",
            "authors": "Ning Wang, ...",
            "paper_title": "Inactivation of a wheat ...",
            "gene_name": [],
            "trait_label": "",
            "evidence_type": "seed_title_match",
            "confidence": 0.98,
            "review_status": "auto_pass",
            ...
          }
        }
    """

    with mysql_cursor(settings.DB_TRITICEAE) as cursor:
        cursor.execute("SELECT * FROM Triticeae_Research_filter WHERE pubmedid = %s", (pubmedid,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Paper not found: {pubmedid}")

    return ok(_row_to_paper(row))


@router.get("/papers")
def search_papers(
    q: str | None = Query(None, description="全文关键词搜索（paper_title / abstract / authors）"),
    gene_name: str | None = Query(None, description="基因名称关键词，如 TaCPK-1"),
    trait_label: str | None = Query(None, description="性状标签精确匹配"),
    evidence_type: str | None = Query(None, description="证据类型精确匹配，如 seed_title_match"),
    min_confidence: float | None = Query(None, ge=0, le=1, description="最低置信度"),
    review_status: str | None = Query(None, description="审核状态，如 auto_pass"),
    ai_tags: str | None = Query(None, description="AI 标签关键词，如 stripe_rust"),
    functional_gene_tags: str | None = Query(None, description="功能基因标签关键词"),
    pubmed_keywords: str | None = Query(None, description="PubMed 关键词"),
    new_tags: str | None = Query(None, description="新标签关键词"),
    pub_date_start: str | None = Query(None, description="发布日期范围起始，格式 2022"),
    pub_date_end: str | None = Query(None, description="发布日期范围结束，格式 2024"),
    limit: int = Query(20, ge=1, le=200, description="返回条数上限"),
    offset: int = Query(0, ge=0, description="分页偏移量"),
) -> dict:
    """搜索 Triticeae 研究文献，支持多维度过滤。

    功能:
        根据基因名称、性状标签、证据类型、置信度、AI 标签等条件，
        组合过滤 Triticeae 研究文献库。支持全文关键词搜索和日期范围筛选。
        返回分页结果。

    用法:
        GET /api/triticeae/papers?gene_name=TaCPK-1&evidence_type=seed_title_match&min_confidence=0.9&limit=10

    案例:
        curl -X GET "http://localhost:8000/api/triticeae/papers?gene_name=TaCPK-1&limit=5"

        响应:
        {
          "success": true,
          "data": {
            "total": 1,
            "limit": 5,
            "offset": 0,
            "papers": [...]
          }
        }
    """

    conditions: list[str] = []
    params: list[str | int | float] = []

    if q:
        conditions.append("(paper_title LIKE %s OR abstract LIKE %s OR authors LIKE %s)")
        like = f"%{q}%"
        params.extend([like, like, like])

    if gene_name:
        conditions.append("gene_name LIKE %s")
        params.append(f"%{gene_name}%")

    if trait_label:
        conditions.append("trait_label = %s")
        params.append(trait_label)

    if evidence_type:
        conditions.append("evidence_type = %s")
        params.append(evidence_type)

    if min_confidence is not None:
        conditions.append("confidence >= %s")
        params.append(min_confidence)

    if review_status:
        conditions.append("review_status = %s")
        params.append(review_status)

    if ai_tags:
        conditions.append("ai_tags LIKE %s")
        params.append(f"%{ai_tags}%")

    if functional_gene_tags:
        conditions.append("functional_gene_tags LIKE %s")
        params.append(f"%{functional_gene_tags}%")

    if pubmed_keywords:
        conditions.append("pubmed_keywords LIKE %s")
        params.append(f"%{pubmed_keywords}%")

    if new_tags:
        conditions.append("new_tags LIKE %s")
        params.append(f"%{new_tags}%")

    if pub_date_start:
        conditions.append("SUBSTRING(pub_date, 1, 4) >= %s")
        params.append(pub_date_start[:4])
    if pub_date_end:
        conditions.append("SUBSTRING(pub_date, 1, 4) <= %s")
        params.append(pub_date_end[:4])

    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

    with mysql_cursor(settings.DB_TRITICEAE) as cursor:
        # Count total
        cursor.execute(f"SELECT COUNT(*) AS cnt FROM Triticeae_Research_filter{where_clause}", params)
        total = cursor.fetchone()["cnt"]

        # Fetch page
        cursor.execute(
            f"SELECT * FROM Triticeae_Research_filter{where_clause} ORDER BY pub_date DESC LIMIT %s OFFSET %s",
            [*params, limit, offset],
        )
        rows = cursor.fetchall()

    papers = [_row_to_paper(r) for r in rows]
    return ok(TriticeaeSearchResult(total=total, limit=limit, offset=offset, papers=papers).model_dump())


# ── helpers ───────────────────────────

def _row_to_paper(row: dict) -> dict:
    """Convert a raw MySQL row to a cleaned dict ready for JSON response."""

    gene_raw = row.get("gene_name")
    if isinstance(gene_raw, str) and gene_raw.startswith("["):
        import json
        try:
            gene_list = json.loads(gene_raw)
        except (json.JSONDecodeError, TypeError):
            gene_list = [g.strip() for g in gene_raw.strip("[]").split(",") if g.strip()]
    else:
        gene_list = []

    return TriticeaePaper(
        pubmedid=str(row.get("pubmedid") or ""),
        pub_date=str(row.get("pub_date") or ""),
        authors=str(row.get("authors") or ""),
        paper_title=str(row.get("paper_title") or ""),
        abstract=str(row.get("abstract") or ""),
        fga_title=str(row.get("fga_title") or ""),
        gene_name=gene_list or [],
        trait_label=str(row.get("trait_label") or ""),
        evidence_type=str(row.get("evidence_type") or ""),
        confidence=float(row["confidence"]) if row.get("confidence") else None,
        review_status=str(row.get("review_status") or ""),
        pubmed_keywords=str(row.get("pubmed_keywords") or ""),
        ai_tags=str(row.get("ai_tags") or ""),
        functional_gene_tags=str(row.get("functional_gene_tags") or ""),
        new_tags=str(row.get("new_tags") or ""),
        old_fga_disease_gene_tags=str(row.get("old_fga_disease_gene_tags") or ""),
        old_paper_disease_gene_tags=str(row.get("old_paper_disease_gene_tags") or ""),
        new_disease_gene_tags=str(row.get("new_disease_gene_tags") or ""),
        match_detail=str(row.get("match_detail") or ""),
    ).model_dump()
