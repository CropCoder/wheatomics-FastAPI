"""Triticeae Research Filter database — curated paper/trait lookup for AI agents.

Queries functional_gene_annotations LEFT JOIN papers for full annotation+metadata.
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.core.response import ok
from app.db.mysql import mysql_cursor
from app.schemas.triticeae import TriticeaePaper, TriticeaeSearchResult

# Note: router prefix is empty so the route decorators below define the
# full /api path themselves. include_router() in main.py already wraps
# this with settings.API_PREFIX ('/api'). Using prefix='/papers' here
# would produce the bugged path /api/papers/papers (double prefix).
router = APIRouter(prefix="", tags=["Triticeae Papers"])

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
        p.doi,
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

# Columns searched by the "All Fields" (q) parameter.
_Q_FIELDS = [
    "p.title",
    "p.abstract",
    "p.journal",
    "p.authors",
    "p.pubmed_keywords",
    "p.ai_tags",
    "p.function_gene_tags",
]

# Mapping: query param -> list of SQL column expressions for LIKE OR.
# Positive param and its <param>_exclude counterpart are both accepted.
_TEXT_FILTER_MAP: dict[str, list[str]] = {
    "q": _Q_FIELDS,
    "title": ["p.title"],
    "abstract": ["p.abstract"],
    "journal": ["p.journal"],
    "authors": ["p.authors"],
    "pubmed_keywords": ["p.pubmed_keywords"],
    "ai_tags": ["p.ai_tags"],
    "function_gene_tags": ["p.function_gene_tags"],
    # gene_name lives in functional_gene_annotations, but papers has two
    # paper-level gene tag columns we can search without a JOIN.
    "gene_name": ["p.function_gene_tags", "p.functional_gene_tags"],
}

# Exact-match filters (e.g. PMID).
_EXACT_FILTER_MAP: dict[str, str] = {
    "pmid": "TRIM(p.pmid)",
}

# Named flag/source filters kept for backward compatibility.
_NAMED_FILTER_MAP: dict[str, str] = {
    "functional_gene_source": "p.functional_gene_source",
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
        doi=str(row.get("doi") or "") or None,
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
    q_exclude: str | None = None,
    title: str | None = None,
    title_exclude: str | None = None,
    abstract: str | None = None,
    abstract_exclude: str | None = None,
    journal: str | None = None,
    journal_exclude: str | None = None,
    authors: str | None = None,
    authors_exclude: str | None = None,
    pubmed_keywords: str | None = None,
    pubmed_keywords_exclude: str | None = None,
    ai_tags: str | None = None,
    ai_tags_exclude: str | None = None,
    function_gene_tags: str | None = None,
    function_gene_tags_exclude: str | None = None,
    gene_name: str | None = None,
    gene_name_exclude: str | None = None,
    pmid: str | None = None,
    pmid_exclude: str | None = None,
    source_method: str | None = None,
    source_method_exclude: str | None = None,
    review_status: str | None = None,
    review_status_exclude: str | None = None,
    functional_gene_flag: str | None = None,
    functional_gene_source: str | None = None,
    function_gene_flag: str | None = None,
    pub_date_start: str | None = None,
    pub_date_end: str | None = None,
    since_days: int | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Search the papers table only (no JOIN). Annotation-only filters
    were dropped — use /papers/{pmid}/annotation for that data.
    """
    conditions: list[str] = []
    params: list = []

    # Text filters (positive): LIKE across one or more columns.
    for param_name, cols in _TEXT_FILTER_MAP.items():
        val = locals().get(param_name)
        if not val:
            continue
        like = f"%{val}%"
        clauses = [f"{col} LIKE %s" for col in cols]
        conditions.append(f"({' OR '.join(clauses)})")
        params.extend([like] * len(cols))

    # Text filters (exclude / NOT): NOT LIKE across all columns.
    for param_name, cols in _TEXT_FILTER_MAP.items():
        exclude_param = f"{param_name}_exclude"
        val = locals().get(exclude_param)
        if not val:
            continue
        like = f"%{val}%"
        clauses = [f"{col} NOT LIKE %s" for col in cols]
        conditions.append(f"({' AND '.join(clauses)})")
        params.extend([like] * len(cols))

    # Exact-match filters (positive).
    for param_name, sql_expr in _EXACT_FILTER_MAP.items():
        val = locals().get(param_name)
        if val:
            conditions.append(f"{sql_expr} = %s")
            params.append(val.strip())

    # Annotation-level filters (functional_gene_annotations) via EXISTS so the
    # papers query itself stays a single-table scan. Useful for finding papers
    # whose LLM annotation failed: source_method=llm_error.
    for field, positive, negative in (
        ("source_method", source_method, source_method_exclude),
        ("review_status", review_status, review_status_exclude),
    ):
        if positive:
            conditions.append(
                "EXISTS (SELECT 1 FROM functional_gene_annotations f "
                f"WHERE f.pubmedid = p.pmid AND f.{field} = %s)"
            )
            params.append(positive)
        if negative:
            conditions.append(
                "NOT EXISTS (SELECT 1 FROM functional_gene_annotations f "
                f"WHERE f.pubmedid = p.pmid AND f.{field} = %s)"
            )
            params.append(negative)

    # Exact-match filters (exclude).
    for param_name, sql_expr in _EXACT_FILTER_MAP.items():
        exclude_param = f"{param_name}_exclude"
        val = locals().get(exclude_param)
        if val:
            conditions.append(f"{sql_expr} != %s")
            params.append(val.strip())

    # Backward-compatible named filters.
    if functional_gene_flag is not None:
        conditions.append("p.functional_gene_flag = %s")
        params.append(functional_gene_flag)
    if function_gene_flag is not None:
        conditions.append("p.function_gene_flag = %s")
        params.append(function_gene_flag)
    if functional_gene_source:
        conditions.append("p.functional_gene_source LIKE %s")
        params.append(f"%{functional_gene_source}%")

    if pub_date_start:
        conditions.append("SUBSTRING(p.pub_date, 1, 4) >= %s")
        params.append(pub_date_start[:4])
    if pub_date_end:
        conditions.append("SUBSTRING(p.pub_date, 1, 4) <= %s")
        params.append(pub_date_end[:4])

    if since_days is not None and since_days > 0:
        # papers.created_at = row insertion time into the papers table
        # (when the PubMed fetch + import step ran). Distinct from
        # fga.created_at, which is when the LLM annotation was made.
        # Use since_days for "what new papers did we add this week".
        conditions.append("p.created_at >= (NOW() - INTERVAL %s DAY)")
        params.append(int(since_days))

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
    q: str | None = Query(None, description="Full-text keyword search (title / abstract / journal / authors / pubmed_keywords / ai_tags / function_gene_tags)"),
    q_exclude: str | None = Query(None, description="Excluded keywords (NOT semantics); same search scope as q"),
    title: str | None = Query(None, description="Fuzzy title match"),
    title_exclude: str | None = Query(None, description="Title exclusion"),
    abstract: str | None = Query(None, description="Fuzzy abstract match"),
    abstract_exclude: str | None = Query(None, description="Abstract exclusion"),
    journal: str | None = Query(None, description="Fuzzy journal match"),
    journal_exclude: str | None = Query(None, description="Journal exclusion"),
    authors: str | None = Query(None, description="Fuzzy author match (LIKE %...%, across whole words)"),
    authors_exclude: str | None = Query(None, description="Author exclusion"),
    pubmed_keywords: str | None = Query(None, description="Fuzzy PubMed keyword match"),
    pubmed_keywords_exclude: str | None = Query(None, description="PubMed keyword exclusion"),
    ai_tags: str | None = Query(None, description="Fuzzy AI tag match (papers.ai_tags)"),
    ai_tags_exclude: str | None = Query(None, description="AI tag exclusion"),
    function_gene_tags: str | None = Query(None, description="Fuzzy functional gene tag match (papers.function_gene_tags)"),
    function_gene_tags_exclude: str | None = Query(None, description="Functional gene tag exclusion"),
    gene_name: str | None = Query(None, description="Fuzzy gene name match (papers.function_gene_tags + functional_gene_tags)"),
    gene_name_exclude: str | None = Query(None, description="Gene name exclusion"),
    source_method: str | None = Query(None, description="Filter by LLM annotation source (functional_gene_annotations.source_method, EXISTS subquery), e.g. llm_error / rule+llm / seed_title_match"),
    source_method_exclude: str | None = Query(None, description="Exclude an annotation source (NOT EXISTS)"),
    review_status: str | None = Query(None, description="Filter by annotation review status (EXISTS subquery), e.g. negative / auto_pass / need_review"),
    review_status_exclude: str | None = Query(None, description="Exclude a review status (NOT EXISTS)"),
    pmid: str | None = Query(None, description="Exact PubMed ID match (whitespace is stripped automatically)"),
    pmid_exclude: str | None = Query(None, description="Exact PubMed ID exclusion"),
    functional_gene_flag: str | None = Query(None, description="Paper-level functional gene flag"),
    functional_gene_source: str | None = Query(None, description="Paper-level functional gene source"),
    function_gene_flag: str | None = Query(None, description="Second-set functional gene flag"),
    pub_date_start: str | None = Query(None, description="Publication year start"),
    pub_date_end: str | None = Query(None, description="Publication year end"),
    since_days: int | None = Query(None, ge=1, le=3650,
        description="Filter by papers-table insertion time (p.created_at) within the last N days"),
    limit: int = Query(20, ge=1, le=200, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> dict:
    """Search Triticeae paper metadata.

    Queries only the `papers` table (includes paper-level annotations such as
    functional_gene_flag / ai_tags / keywords_source); it no longer LEFT JOINs
    functional_gene_annotations. For fine-grained LLM annotations (gene_name /
    trait_label / confidence, etc.) call /papers/{pmid}/annotation.

    Every parameter also accepts a <param>_exclude variant for NOT semantics.

    `since_days` is anchored to `papers.created_at` (when the row was
    inserted), not `fga.created_at`. Use it for "what new papers did
    we add this week".

    Default order: paper_created_at DESC (most recently added first).
    """
    return _build_search(**locals())


# DOI enrichment for the papers list. The papers table has no DOI column, so
# resolve DOIs from PubMed on demand (one batch per rendered page) and cache
# them in-process; failures degrade gracefully to no DOI link.
_DOI_CACHE: dict[str, str] = {}
_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def _fetch_dois(pmids: list[str]) -> None:
    data = urllib.parse.urlencode(
        {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}
    ).encode()
    req = urllib.request.Request(
        _EFETCH_URL, data=data, headers={"User-Agent": "wheatomics-api/1.0"}
    )
    with urllib.request.urlopen(req, timeout=6) as resp:
        xml = resp.read().decode("utf-8", "replace")
    found: dict[str, str] = {}
    for block in re.findall(r"<PubmedArticle>.*?</PubmedArticle>", xml, re.S):
        m = re.search(r"<PMID[^>]*>(\d+)</PMID>", block)
        d = re.search(r'<ArticleId IdType="doi">([^<]+)</ArticleId>', block)
        if m and d:
            found[m.group(1)] = d.group(1).strip()
    for pmid in pmids:
        _DOI_CACHE[pmid] = found.get(pmid, "")
    if found:
        try:
            with mysql_cursor(settings.DB_TRITICEAE) as cursor:
                for pmid, doi in found.items():
                    cursor.execute(
                        "UPDATE papers SET doi=%s WHERE pmid=%s AND (doi IS NULL OR doi='')",
                        (doi, pmid),
                    )
        except Exception:
            pass


@router.get("/papers/dois")
def paper_dois(pmids: str = Query(..., description="Comma-separated PubMed IDs")):
    ids = [p.strip() for p in pmids.split(",") if p.strip().isdigit()][:100]
    missing = [p for p in ids if p not in _DOI_CACHE]
    if missing:
        try:
            _fetch_dois(missing)
        except Exception:
            pass
    return ok({p: _DOI_CACHE[p] for p in ids if _DOI_CACHE.get(p)})


@router.get("/papers/{pmid}/annotation")
def get_paper_annotation(pmid: str) -> dict:
    """Get the LLM annotation of a single paper by PMID (functional_gene_annotations table).

    Returns all annotation-layer fields: fga_id, is_functional_gene, confidence,
    gene_name, gene_type, trait_label, function_summary, evidence_type,
    new_tags, llm_reason, source_method, review_status, created_at,
    updated_at.

    If the paper has no annotation record (the AI judged it is not a
    functional gene study), returns has_annotation: false + annotation: null.
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


# Stats endpoint MUST be declared before /papers/{pubmedid}.
# Otherwise the wildcard route greedily matches /papers/stats and
# treats 'stats' as a PMID, returning 'Paper not found: stats'.
#
# Path uses /papers/stats (not /stats) so it's namespaced under the
# /papers resource — clearer for OpenAPI consumers and avoids
# conflicting with any future /api/stats resource shared by other
# routers.
@router.get("/papers/stats")
def stats() -> dict:
    """Dataset aggregate statistics: year distribution, top-20 journals, top-30 AI tags, functional gene ratio, review status distribution.

    All aggregations use SQL GROUP BY; 22K rows return in under 100ms. The papers
    table is counted with PMID de-duplication; functional_gene_annotations is
    counted per annotation record (one PMID may map to several annotations).
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
                COUNT(DISTINCT f.pubmedid)    AS annotated_papers,
                MAX(p.created_at)             AS latest_paper_added_at
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

        # --- top 期刊（按 PMID 去重；列出所有期刊，不做截断） ---
        cursor.execute("""
            SELECT TRIM(p.journal) AS journal, COUNT(DISTINCT p.pmid) AS cnt
            FROM papers p
            WHERE p.journal IS NOT NULL AND TRIM(p.journal) != ''
            GROUP BY journal
            ORDER BY cnt DESC, journal ASC
            LIMIT 1000
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

        # --- top 单个 AI 标签（按 ai_tags 里的分号拆分后 GROUP BY） ---
        # MySQL 没有内置 string_to_array 拆分分号分隔字符串，所以用 Python 拆。
        # 22K 行内存里跑 ~50ms，比复杂的 SUBSTRING_INDEX 链 JOIN 简单得多。
        tag_counter: dict[str, int] = {}
        for r in top_ai_tags:
            for tag in (r["tags"] or "").split(";"):
                tag = tag.strip()
                if tag:
                    tag_counter[tag] = tag_counter.get(tag, 0) + int(r["count"])
        top_individual_tags = sorted(
            ({"tag": k, "count": v} for k, v in tag_counter.items()),
            key=lambda x: x["count"],
            reverse=True,
        )[:30]

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
        "top_individual_tags": top_individual_tags,
        "functional_dist": functional_dist,
        "review_status_dist": review_status_dist,
        "source_method_dist": source_method_dist,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "latest_paper_added_at": (
            head["latest_paper_added_at"].isoformat()
            if head.get("latest_paper_added_at") else None
        ),
    })

@router.get("/papers/{pubmedid}")
def get_paper(pubmedid: str) -> dict:
    """Get the metadata of a single paper by PubMed ID (papers table only).

    Returns the papers.* fields; all fga_* fields are empty.
    For LLM annotations call /papers/{pmid}/annotation.

    Note the route order: this route must be declared **after**
    /papers/{pmid}/annotation, otherwise Starlette matches this single-segment
    route first and splits the request 42105133/annotation into
    pubmedid="42105133" plus an unknown "annotation" query parameter.
    """
    with mysql_cursor(settings.DB_TRITICEAE) as cursor:
        cursor.execute(f"{_SQL_SELECT} WHERE p.pmid = %s", (pubmedid,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Paper not found: {pubmedid}")

    return ok(_row_to_paper(row))


