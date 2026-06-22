"""Triticeae Research Filter database — curated paper/trait lookup for AI agents.

Queries functional_gene_annotations LEFT JOIN papers for full annotation+metadata.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.core.response import ok
from app.db.mysql import mysql_cursor
from app.schemas.triticeae import TriticeaePaper, TriticeaeSearchResult

router = APIRouter(prefix="/triticeae", tags=["Triticeae Papers"])

_SQL_COLUMNS = """f.id AS fga_id,
        f.pubmedid,
        f.title AS fga_title,
        f.is_functional_gene,
        f.confidence,
        f.gene_name,
        f.gene_type,
        f.trait_label,
        f.function_summary,
        f.evidence_type,
        f.new_tags,
        f.llm_reason,
        f.source_method,
        f.review_status,
        f.created_at AS fga_created_at,
        f.updated_at AS fga_updated_at,
        f.disease_gene_tags AS fga_disease_gene_tags,
        p.id AS paper_id,
        p.pmid,
        p.pub_date,
        p.title AS paper_title,
        p.journal,
        p.authors,
        p.abstract,
        p.pubmed_keywords,
        p.ai_tags,
        p.keywords_source,
        p.link,
        p.created_at AS paper_created_at,
        p.functional_gene_flag,
        p.functional_gene_tags,
        p.functional_gene_source,
        p.disease_gene_tags AS paper_disease_gene_tags,
        p.function_gene_flag,
        p.function_gene_tags"""

_SQL_FROM = """FROM functional_gene_annotations f LEFT JOIN papers p ON f.pubmedid COLLATE utf8mb4_general_ci = p.pmid"""

_SQL_COUNT = f"""SELECT COUNT(*) AS cnt {_SQL_FROM}"""
_SQL_SELECT = f"""SELECT {_SQL_COLUMNS} {_SQL_FROM}"""

# Mapping: query param -> SQL column expression for WHERE
_FILTER_MAP: dict[str, str] = {
    "gene_name": "f.gene_name",
    "trait_label": "f.trait_label",
    "evidence_type": "f.evidence_type",
    "review_status": "f.review_status",
    "ai_tags": "p.ai_tags",
    "functional_gene_tags": "p.functional_gene_tags",
    "pubmed_keywords": "p.pubmed_keywords",
    "new_tags": "f.new_tags",
    "gene_type": "f.gene_type",
    "source_method": "f.source_method",
    "is_functional_gene": "f.is_functional_gene",
    "functional_gene_flag": "p.functional_gene_flag",
    "functional_gene_source": "p.functional_gene_source",
    "function_gene_flag": "p.function_gene_flag",
    "function_gene_tags": "p.function_gene_tags",
}


def _apply_q_filter(conditions: list, params: list, q: str, field_expr: str):
    """Add a LIKE filter on multiple text fields."""
    conditions.append(f"({field_expr} LIKE %s)")
    params.append(f"%{q}%")


def _parse_gene_name(raw) -> list[str]:
    """Parse gene_name from JSON string or comma-separated list."""
    if not raw or not isinstance(raw, str):
        return []
    if raw.startswith("["):
        import json
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    return [g.strip() for g in raw.split(",") if g.strip()]


def _row_to_paper(row: dict) -> dict:
    """Convert a raw MySQL row to a cleaned dict ready for JSON response."""
    return TriticeaePaper(
        fga_id=row.get("fga_id"),
        pubmedid=str(row.get("pubmedid") or ""),
        fga_title=str(row.get("fga_title") or ""),
        is_functional_gene=bool(row.get("is_functional_gene")) if row.get("is_functional_gene") is not None else None,
        confidence=float(row["confidence"]) if row.get("confidence") is not None else None,
        gene_name=_parse_gene_name(row.get("gene_name")),
        gene_type=str(row.get("gene_type") or ""),
        trait_label=str(row.get("trait_label") or ""),
        function_summary=str(row.get("function_summary") or ""),
        evidence_type=str(row.get("evidence_type") or ""),
        new_tags=str(row.get("new_tags") or ""),
        llm_reason=str(row.get("llm_reason") or ""),
        source_method=str(row.get("source_method") or ""),
        review_status=str(row.get("review_status") or ""),
        fga_created_at=str(row.get("fga_created_at") or ""),
        fga_updated_at=str(row.get("fga_updated_at") or ""),
        fga_disease_gene_tags=str(row.get("fga_disease_gene_tags") or ""),
        paper_id=row.get("paper_id"),
        pmid=str(row.get("pmid") or ""),
        pub_date=str(row.get("pub_date") or ""),
        paper_title=str(row.get("paper_title") or ""),
        journal=str(row.get("journal") or ""),
        authors=str(row.get("authors") or ""),
        abstract=str(row.get("abstract") or ""),
        pubmed_keywords=str(row.get("pubmed_keywords") or ""),
        ai_tags=str(row.get("ai_tags") or ""),
        keywords_source=str(row.get("keywords_source") or ""),
        link=str(row.get("link") or ""),
        paper_created_at=str(row.get("paper_created_at") or ""),
        functional_gene_flag=str(row.get("functional_gene_flag") or ""),
        functional_gene_tags=str(row.get("functional_gene_tags") or ""),
        functional_gene_source=str(row.get("functional_gene_source") or ""),
        paper_disease_gene_tags=str(row.get("paper_disease_gene_tags") or ""),
        function_gene_flag=str(row.get("function_gene_flag") or ""),
        function_gene_tags=str(row.get("function_gene_tags") or ""),
    ).model_dump()


def _build_search(
    q: str | None = None,
    gene_name: str | None = None,
    trait_label: str | None = None,
    evidence_type: str | None = None,
    min_confidence: float | None = None,
    review_status: str | None = None,
    ai_tags: str | None = None,
    functional_gene_tags: str | None = None,
    pubmed_keywords: str | None = None,
    new_tags: str | None = None,
    gene_type: str | None = None,
    source_method: str | None = None,
    is_functional_gene: bool | None = None,
    functional_gene_flag: str | None = None,
    functional_gene_source: str | None = None,
    function_gene_flag: str | None = None,
    function_gene_tags: str | None = None,
    pub_date_start: str | None = None,
    pub_date_end: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Shared search logic for single-paper and multi-paper endpoints."""
    conditions: list[str] = []
    params: list = []

    if q:
        _apply_q_filter(conditions, params, q,
            "p.title LIKE %s OR p.abstract LIKE %s OR p.authors LIKE %s")
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
        # Reset — _apply_q_filter added one placeholder, replace the logic
        conditions.pop()
        params.pop()
        conditions.append(
            "(p.title LIKE %s OR p.abstract LIKE %s OR p.authors LIKE %s)")
        like = f"%{q}%"
        params.extend([like, like, like])

    # Named filters
    for param_name, sql_col in _FILTER_MAP.items():
        val = locals().get(param_name)
        if val is None:
            continue
        if param_name == "is_functional_gene":
            conditions.append(f"{sql_col} = %s")
            params.append(1 if val else 0)
        elif param_name == "gene_name" and val:
            conditions.append(f"{sql_col} LIKE %s")
            params.append(f"%{val}%")
        elif val:
            conditions.append(f"{sql_col} LIKE %s")
            params.append(f"%{val}%")

    if min_confidence is not None:
        conditions.append("f.confidence >= %s")
        params.append(min_confidence)

    if pub_date_start:
        conditions.append("SUBSTRING(p.pub_date, 1, 4) >= %s")
        params.append(pub_date_start[:4])
    if pub_date_end:
        conditions.append("SUBSTRING(p.pub_date, 1, 4) <= %s")
        params.append(pub_date_end[:4])

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    with mysql_cursor(settings.DB_TRITICEAE) as cursor:
        cursor.execute(f"{_SQL_COUNT}{where}", params)
        total = cursor.fetchone()["cnt"]

        cursor.execute(
            f"{_SQL_SELECT}{where} ORDER BY p.pub_date DESC LIMIT %s OFFSET %s",
            [*params, limit, offset],
        )
        rows = cursor.fetchall()

    papers = [_row_to_paper(r) for r in rows]
    return ok(TriticeaeSearchResult(total=total, limit=limit, offset=offset, papers=papers).model_dump())


@router.get("/papers/{pubmedid}")
def get_paper(pubmedid: str) -> dict:
    """按 PubMed ID 获取单篇论文详情。
    """
    with mysql_cursor(settings.DB_TRITICEAE) as cursor:
        cursor.execute(f"{_SQL_SELECT} WHERE f.pubmedid = %s", (pubmedid,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Paper not found: {pubmedid}")

    return ok(_row_to_paper(row))


@router.get("/papers")
def search_papers(
    q: str | None = Query(None, description="全文关键词搜索（paper_title / abstract / authors）"),
    gene_name: str | None = Query(None, description="基因名称关键词"),
    trait_label: str | None = Query(None, description="性状标签"),
    evidence_type: str | None = Query(None, description="证据类型"),
    min_confidence: float | None = Query(None, ge=0, le=1, description="最低置信度(0-1)"),
    review_status: str | None = Query(None, description="审核状态"),
    ai_tags: str | None = Query(None, description="AI 标签"),
    functional_gene_tags: str | None = Query(None, description="功能基因标签"),
    pubmed_keywords: str | None = Query(None, description="PubMed 关键词"),
    new_tags: str | None = Query(None, description="新标签"),
    gene_type: str | None = Query(None, description="基因类型"),
    source_method: str | None = Query(None, description="标注来源方法"),
    is_functional_gene: bool | None = Query(None, description="是否为功能基因(true/false)"),
    functional_gene_flag: str | None = Query(None, description="功能基因标记"),
    functional_gene_source: str | None = Query(None, description="功能基因来源"),
    function_gene_flag: str | None = Query(None, description="新增功能基因标记"),
    function_gene_tags: str | None = Query(None, description="新增功能基因标签"),
    pub_date_start: str | None = Query(None, description="发布年份起始"),
    pub_date_end: str | None = Query(None, description="发布年份结束"),
    limit: int = Query(20, ge=1, le=200, description="返回条数上限"),
    offset: int = Query(0, ge=0, description="分页偏移量"),
) -> dict:
    """搜索 Triticeae 研究文献，支持多维度过滤。
    """
    return _build_search(**locals())
