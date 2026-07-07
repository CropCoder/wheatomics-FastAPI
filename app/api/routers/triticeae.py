"""Triticeae Research Filter database — curated paper/trait lookup for AI agents.

Queries functional_gene_annotations LEFT JOIN papers for full annotation+metadata.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.core.response import ok
from app.db.mysql import mysql_cursor
from app.schemas.triticeae import TriticeaePaper, TriticeaeSearchResult

router = APIRouter(prefix="/papers", tags=["Triticeae Papers"])

# papers 表是论文元数据的主表（来自 PubMed + 论文级 AI 标注）；
# functional_gene_annotations 是 LLM 标注层（细粒度）。两个独立查询：
#   /api/triticeae/papers           → 只查 papers
#   /api/triticeae/papers/{pmid}/annotation → 只查 annotations
# 这样 /papers 不再 LEFT JOIN，每次查询只跑一张表。

_SQL_COLUMNS = """p.id AS paper_id,
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

_SQL_FROM = """FROM papers p"""

_SQL_COUNT = f"""SELECT COUNT(*) AS cnt {_SQL_FROM}"""
_SQL_SELECT = f"""SELECT {_SQL_COLUMNS} {_SQL_FROM}"""

# Mapping: query param -> SQL column expression for WHERE.
# Annotation-only filters (gene_name / trait_label / new_tags / gene_type /
# source_method / is_functional_gene / evidence_type / review_status) were
# dropped here — those columns live in functional_gene_annotations, and
# /papers no longer joins that table. Use /papers/{pmid}/annotation to
# fetch annotation details for a single paper.
_FILTER_MAP: dict[str, str] = {
    "ai_tags": "p.ai_tags",
    "functional_gene_tags": "p.functional_gene_tags",
    "pubmed_keywords": "p.pubmed_keywords",
    "functional_gene_flag": "p.functional_gene_flag",
    "functional_gene_source": "p.functional_gene_source",
    "function_gene_flag": "p.function_gene_flag",
    "function_gene_tags": "p.function_gene_tags",
}


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
    """Convert a raw `papers` row to a cleaned dict for JSON response.

    Annotation-level fields (fga_*) live in TriticeaePaper schema with default
    None / "" so the existing front-end can still render the row; clients
    that want them populated should call /papers/{pmid}/annotation.
    """
    return TriticeaePaper(
        # annotation fields — always None / empty here
        fga_id=None,
        pubmedid="",
        fga_title="",
        is_functional_gene=None,
        confidence=None,
        gene_name=[],
        gene_type="",
        trait_label="",
        function_summary="",
        evidence_type="",
        new_tags="",
        llm_reason="",
        source_method="",
        review_status="",
        fga_created_at="",
        fga_updated_at="",
        fga_disease_gene_tags="",

        # paper fields — populated from SELECT
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
    authors: str | None = None,
    pmid: str | None = None,
    ai_tags: str | None = None,
    functional_gene_tags: str | None = None,
    pubmed_keywords: str | None = None,
    functional_gene_flag: str | None = None,
    functional_gene_source: str | None = None,
    function_gene_flag: str | None = None,
    function_gene_tags: str | None = None,
    pub_date_start: str | None = None,
    pub_date_end: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Search the papers table only (no JOIN). Annotation-only filters
    were dropped — use /papers/{pmid}/annotation for that data.
    """
    conditions: list[str] = []
    params: list = []

    if q:
        conditions.append(
            "(p.title LIKE %s OR p.abstract LIKE %s)")
        like = f"%{q}%"
        params.extend([like, like])

    if authors:
        # FIND_IN_SET for exact author match within comma-separated list
        conditions.append("FIND_IN_SET(%s, p.authors) > 0")
        params.append(authors)

    if pmid:
        # TRIM for exact PMID match (handles whitespace)
        conditions.append("TRIM(p.pmid) = %s")
        params.append(pmid.strip())

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
            f"{_SQL_SELECT}{where} "
            "ORDER BY p.created_at DESC, p.pub_date DESC "
            "LIMIT %s OFFSET %s",
            [*params, limit, offset],
        )
        rows = cursor.fetchall()

    papers = [_row_to_paper(r) for r in rows]
    return ok(TriticeaeSearchResult(total=total, limit=limit, offset=offset, papers=papers).model_dump())


@router.get("/papers")
def search_papers(
    q: str | None = Query(None, description="全文关键词搜索（paper_title / abstract）"),
    authors: str | None = Query(None, description="作者精确匹配（逗号分隔列表中精确查找）"),
    pmid: str | None = Query(None, description="PubMed ID 精确匹配（自动去除空白字符）"),
    ai_tags: str | None = Query(None, description="AI 标签（papers.ai_tags）"),
    functional_gene_tags: str | None = Query(None, description="论文级功能基因标签"),
    pubmed_keywords: str | None = Query(None, description="PubMed 关键词"),
    functional_gene_flag: str | None = Query(None, description="论文级功能基因标记"),
    functional_gene_source: str | None = Query(None, description="论文级功能基因来源"),
    function_gene_flag: str | None = Query(None, description="第二套功能基因标记"),
    function_gene_tags: str | None = Query(None, description="第二套功能基因标签"),
    pub_date_start: str | None = Query(None, description="发布年份起始"),
    pub_date_end: str | None = Query(None, description="发布年份结束"),
    limit: int = Query(20, ge=1, le=200, description="返回条数上限"),
    offset: int = Query(0, ge=0, description="分页偏移量"),
) -> dict:
    """搜索 Triticeae 论文元数据。

    只查 `papers` 表（包含论文级标注：functional_gene_flag / ai_tags / keywords_source 等），
    不再 LEFT JOIN functional_gene_annotations。需要细粒度 LLM 标注（gene_name /
    trait_label / confidence 等）请调 /papers/{pmid}/annotation。

    默认排序：paper_created_at DESC（最近入库优先）。
    """
    return _build_search(**locals())


@router.get("/papers/{pmid}/annotation")
def get_paper_annotation(pmid: str) -> dict:
    """按 PMID 获取单篇论文的 LLM 标注（functional_gene_annotations 表）。

    返回标注层全部字段：fga_id, is_functional_gene, confidence,
    gene_name, gene_type, trait_label, function_summary, evidence_type,
    new_tags, llm_reason, source_method, review_status, created_at,
    updated_at。

    如果该论文没有 annotation 记录（AI 判定不是 functional gene study），
    返回 has_annotation: false + annotation: null。
    """
    with mysql_cursor(settings.DB_TRITICEAE) as cursor:
        cursor.execute("""
            SELECT id AS fga_id,
                   pubmedid,
                   title AS fga_title,
                   is_functional_gene,
                   confidence,
                   gene_name,
                   gene_type,
                   trait_label,
                   function_summary,
                   evidence_type,
                   new_tags,
                   llm_reason,
                   source_method,
                   review_status,
                   created_at AS fga_created_at,
                   updated_at AS fga_updated_at,
                   disease_gene_tags AS fga_disease_gene_tags
            FROM functional_gene_annotations
            WHERE pubmedid = %s
        """, (pmid,))
        row = cursor.fetchone()

    if not row:
        return ok({"pmid": pmid, "has_annotation": False, "annotation": None})

    annotation = {
        "fga_id":               row.get("fga_id"),
        "pubmedid":             str(row.get("pubmedid") or ""),
        "fga_title":            str(row.get("fga_title") or ""),
        "is_functional_gene":   bool(row.get("is_functional_gene")) if row.get("is_functional_gene") is not None else None,
        "confidence":           float(row["confidence"]) if row.get("confidence") is not None else None,
        "gene_name":            _parse_gene_name(row.get("gene_name")),
        "gene_type":            str(row.get("gene_type") or ""),
        "trait_label":          str(row.get("trait_label") or ""),
        "function_summary":     str(row.get("function_summary") or ""),
        "evidence_type":        str(row.get("evidence_type") or ""),
        "new_tags":             str(row.get("new_tags") or ""),
        "llm_reason":           str(row.get("llm_reason") or ""),
        "source_method":        str(row.get("source_method") or ""),
        "review_status":        str(row.get("review_status") or ""),
        "fga_created_at":       str(row.get("fga_created_at") or ""),
        "fga_updated_at":       str(row.get("fga_updated_at") or ""),
        "fga_disease_gene_tags": str(row.get("fga_disease_gene_tags") or ""),
    }
    return ok({"pmid": pmid, "has_annotation": True, "annotation": annotation})


@router.get("/papers/{pubmedid}")
def get_paper(pubmedid: str) -> dict:
    """按 PubMed ID 获取单篇论文元数据（只查 papers 表）。

    返回 papers.* 字段；fga_* 字段全部为空。
    需要 LLM 标注请调 /papers/{pmid}/annotation。

    注意路由顺序：必须在 /papers/{pmid}/annotation **之后**声明，否则
    Starlette 会先匹配这个单段路径，把请求 42105133/annotation 拆成
    pubmedid="42105133" + 一个未知的 "annotation" 查询参数。
    """
    with mysql_cursor(settings.DB_TRITICEAE) as cursor:
        cursor.execute(f"{_SQL_SELECT} WHERE p.pmid = %s", (pubmedid,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Paper not found: {pubmedid}")

    return ok(_row_to_paper(row))


@router.get("/stats")
def stats() -> dict:
    """数据集聚合统计：年份分布、期刊 top-20、AI 标签 top-30、功能基因比例、审核状态分布。

    所有聚合走 SQL GROUP BY，22K 行在 100ms 内返回。papers 表按 PMID 去重统计；
    functional_gene_annotations 表按标注记录统计（一个 PMID 可对应多条标注）。
    """
    with mysql_cursor(settings.DB_TRITICEAE) as cursor:

        # --- 基础计数 ---
        cursor.execute("""
            SELECT
                COUNT(DISTINCT p.pmid)        AS total_papers,
                COUNT(DISTINCT p.pmid, CASE WHEN TRIM(IFNULL(p.abstract, '')) != '' THEN 1 END) AS with_abstract,
                COUNT(DISTINCT p.pmid, CASE WHEN p.journal IS NOT NULL AND TRIM(p.journal) != '' THEN 1 END) AS with_journal,
                MIN(SUBSTRING(p.pub_date, 1, 4)) AS year_min,
                MAX(SUBSTRING(p.pub_date, 1, 4)) AS year_max,
                COUNT(f.id)                   AS total_annotations,
                COUNT(DISTINCT f.pubmedid)    AS annotated_papers
            FROM papers p
            LEFT JOIN functional_gene_annotations f ON p.pmid = f.pubmedid
        """)
        head = cursor.fetchone() or {}

        # --- 年份直方图（按 PMID 去重，避免一个 PMID 多条标注时重复计数） ---
        cursor.execute("""
            SELECT SUBSTRING(p.pub_date, 1, 4) AS year, COUNT(DISTINCT p.pmid) AS cnt
            FROM papers p
            WHERE p.pub_date IS NOT NULL AND SUBSTRING(p.pub_date, 1, 4) REGEXP '^[0-9]{4}$'
            GROUP BY year
            ORDER BY year DESC
        """)
        year_histogram = [
            {"year": int(r["year"]), "count": int(r["cnt"])}
            for r in cursor.fetchall() if r["year"]
        ]

        # --- top 期刊（按 PMID 去重） ---
        cursor.execute("""
            SELECT TRIM(p.journal) AS journal, COUNT(DISTINCT p.pmid) AS cnt
            FROM papers p
            WHERE p.journal IS NOT NULL AND TRIM(p.journal) != ''
            GROUP BY journal
            ORDER BY cnt DESC
            LIMIT 20
        """)
        top_journals = [
            {"journal": r["journal"], "count": int(r["cnt"])}
            for r in cursor.fetchall()
        ]

        # --- top AI 标签（按整字段 GROUP BY，因为 ai_tags 是分号分隔长串，无法精确拆分） ---
        cursor.execute("""
            SELECT TRIM(p.ai_tags) AS tags, COUNT(*) AS cnt
            FROM papers p
            WHERE p.ai_tags IS NOT NULL AND TRIM(p.ai_tags) != ''
            GROUP BY tags
            ORDER BY cnt DESC
            LIMIT 30
        """)
        top_ai_tags = [
            {"tags": r["tags"], "count": int(r["cnt"])}
            for r in cursor.fetchall()
        ]

        # --- 功能基因比例（基于标注层 f.） ---
        cursor.execute("""
            SELECT
                SUM(CASE WHEN f.is_functional_gene = 1 THEN 1 ELSE 0 END) AS functional,
                SUM(CASE WHEN f.is_functional_gene = 0 THEN 1 ELSE 0 END) AS non_functional,
                SUM(CASE WHEN f.is_functional_gene IS NULL THEN 1 ELSE 0 END) AS unknown,
                COUNT(*) AS total
            FROM functional_gene_annotations f
        """)
        fg = cursor.fetchone() or {}
        functional_dist = {
            "functional": int(fg.get("functional") or 0),
            "non_functional": int(fg.get("non_functional") or 0),
            "unknown": int(fg.get("unknown") or 0),
            "total": int(fg.get("total") or 0),
        }

        # --- 审核状态分布 ---
        cursor.execute("""
            SELECT COALESCE(NULLIF(TRIM(f.review_status), ''), '(empty)') AS status, COUNT(*) AS cnt
            FROM functional_gene_annotations f
            GROUP BY status
            ORDER BY cnt DESC
        """)
        review_status_dist = [
            {"status": r["status"], "count": int(r["cnt"])}
            for r in cursor.fetchall()
        ]

        # --- 来源方法分布 ---
        cursor.execute("""
            SELECT COALESCE(NULLIF(TRIM(f.source_method), ''), '(empty)') AS method, COUNT(*) AS cnt
            FROM functional_gene_annotations f
            GROUP BY method
            ORDER BY cnt DESC
        """)
        source_method_dist = [
            {"method": r["method"], "count": int(r["cnt"])}
            for r in cursor.fetchall()
        ]

    return ok({
        "total_papers": int(head.get("total_papers") or 0),
        "with_abstract": int(head.get("with_abstract") or 0),
        "with_journal": int(head.get("with_journal") or 0),
        "year_min": int(head["year_min"]) if head.get("year_min") else None,
        "year_max": int(head["year_max"]) if head.get("year_max") else None,
        "total_annotations": int(head.get("total_annotations") or 0),
        "annotated_papers": int(head.get("annotated_papers") or 0),
        "year_histogram": year_histogram,
        "top_journals": top_journals,
        "top_ai_tags": top_ai_tags,
        "functional_dist": functional_dist,
        "review_status_dist": review_status_dist,
        "source_method_dist": source_method_dist,
    })
