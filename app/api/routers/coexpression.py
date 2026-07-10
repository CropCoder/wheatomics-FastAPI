"""Coexpression network routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.exceptions import ResourceNotFound
from app.core.response import ok
from app.core.security import COEXPRESSION_TABLES, ensure_allowed_table, ensure_gene_like
from app.db.mysql import mysql_cursor
from app.schemas.network import BioprojectMeta, CoexpressionPair

coexpression_router = APIRouter(tags=["Coexpression"])

@coexpression_router.get("/coexpression/databases")
def list_coexpression_databases() -> dict:
    """获取可用的共表达数据库列表。

    功能:
        返回系统支持的所有共表达数据集，每个数据集包含
        唯一标识 ID 和中文描述信息，供下游查询使用。

    用法:
        GET /api/coexpression/databases
        无需参数。

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/coexpression/databases"

        响应:
          {
            "success": true,
            "data": [
              { "id": "CO_result2", "description": "Wheat grain coexpression" },
              { "id": "CO_PRJEB25639", "description": "Wheat multiple tissues coexpression" }
            ]
          }
    """

    return ok([{"id": key, "description": value} for key, value in COEXPRESSION_TABLES.items()])


@coexpression_router.get("/coexpression/query")
def query_coexpression(
    gene_ids: str = Query(...),
    database: str = Query("CO_PRJEB25639"),
    filter_value: float = Query(300),
) -> dict:
    """查询基因的共表达关系对。

    功能:
        根据输入的基因 ID 列表，在指定的共表达数据库中查询
        与该基因存在共表达关系的基因对。支持两种筛选模式:
        - 小数模式（如 0.8）: 按 PCC (Pearson 相关系数) 筛选，
          返回 |PCC| >= filter_value 的记录
        - 整数模式（如 5）: 按 MR (Mutual Rank) 筛选，
          返回 MR <= filter_value 的记录

    用法:
        GET /api/coexpression/query?gene_ids=<基因1,基因2>&database=<数据库>&filter_value=<阈值>
        - gene_ids: 必填，逗号分隔的基因 ID 列表
        - database: 可选，共表达数据库 ID（CO_result2 或 CO_PRJEB25639），默认 CO_PRJEB25639
        - filter_value: 可选，筛选阈值，默认 300（MR 模式）

    案例:
        请求 (PCC 模式):
          curl -X GET "http://localhost:8000/api/coexpression/query?gene_ids=TraesCS5A02G391700&database=CO_PRJEB25639&filter_value=0.9"

        请求 (MR 模式):
          curl -X GET "http://localhost:8000/api/coexpression/query?gene_ids=TraesCS5A02G391700&database=CO_PRJEB25639&filter_value=5"

        响应:
          {
            "success": true,
            "data": {
              "database": "CO_PRJEB25639",
              "pairs": [
                { "gene1": "TraesCS5A02G391700", "gene2": "TraesCS5B02G391700", "pcc": 0.95, "mr": 3 }
              ]
            }
          }
    """

    database = ensure_allowed_table(database, COEXPRESSION_TABLES, "coexpression table")
    genes = [ensure_gene_like(gene.strip()) for gene in gene_ids.split(",") if gene.strip()]
    pairs: list[CoexpressionPair] = []
    seen: set[tuple[str, str]] = set()
    gene_present = False

    # Column-name casing differs across tables:
    #   CO_result2 / CO_PRJEB25639  → Gene1, Gene2, PCC, MR (PascalCase)
    #   coexpression_filter_ext    → gene1, gene2, pcc, mr (lowercase)
    #   (now renamed to CO_BioticStress_2026; same lowercase schema)
    # MySQL folds identifier case in expressions, so `Gene1` resolves to
    # `gene1` on the lowercase table. SELECT aliases the canonical names
    # in a fixed casing so the row dict is consistent regardless of
    # which table is queried.
    select_cols = "Gene1 AS gene1, Gene2 AS gene2, PCC AS pcc, MR AS mr"

    with mysql_cursor(settings.DB_COEXPRESSION) as cursor:
        for gene in genes:
            if "." in str(filter_value):
                cursor.execute(
                    f"""
                    SELECT {select_cols}
                    FROM `{database}`
                    WHERE (Gene1 = %s OR Gene2 = %s)
                    AND (CAST(PCC AS DECIMAL(10,4)) >= %s OR CAST(PCC AS DECIMAL(10,4)) <= %s)
                    ORDER BY CAST(PCC AS DECIMAL(10,4)) DESC
                    """,
                    (gene, gene, filter_value, -filter_value),
                )
            else:
                cursor.execute(
                    f"""
                    SELECT {select_cols}
                    FROM `{database}`
                    WHERE (Gene1 = %s OR Gene2 = %s)
                    AND CAST(MR AS UNSIGNED) <= %s
                    ORDER BY CAST(MR AS UNSIGNED) ASC
                    """,
                    (gene, gene, int(filter_value)),
                )
            for row in cursor.fetchall():
                gene1 = str(row["gene1"]).strip()
                gene2 = str(row["gene2"]).strip()
                key = tuple(sorted((gene1, gene2)))
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(
                    CoexpressionPair(
                        gene1=gene1,
                        gene2=gene2,
                        pcc=float(row["pcc"]),
                        mr=int(str(row["mr"]).split(".")[0]),
                    )
                )

    # If we found no pairs at all, probe whether the genes actually exist
    # in the chosen database so the caller can distinguish "no partners
    # for this gene" from "this gene is not in this database". Skip the
    # probe when the threshold already eliminates everything, but at
    # least one gene exists — that's a real "no partners" answer.
    if not pairs and genes:
        with mysql_cursor(settings.DB_COEXPRESSION) as cursor:
            # Probe one gene at a time; if any is found, gene_present=True.
            for gene in genes:
                cursor.execute(
                    f"SELECT 1 FROM `{database}` WHERE Gene1 = %s OR Gene2 = %s LIMIT 1",
                    (gene, gene),
                )
                if cursor.fetchone():
                    gene_present = True
                    break

    return ok({
        "database": database,
        "genes": genes,
        "gene_present": gene_present,
        "pairs": [pair.model_dump() for pair in pairs],
    })


# ---------------------------------------------------------------------------
# Bioproject metadata endpoints
# ---------------------------------------------------------------------------
# Reads from coexpressiondb.bioproject_meta, populated by
# scripts/crawl_bioprojects.py from NCBI E-utilities, ENA portal API, and
# CNGB. The bioproject_meta table must exist (init_bioproject_meta.sql)
# and have rows (run the crawler) before these endpoints return data.

def _bioproject_from_row(row: dict) -> BioprojectMeta:
    return BioprojectMeta(
        accession=str(row.get("accession", "")),
        source=str(row.get("source", "")),
        title=row.get("title"),
        description=row.get("description"),
        organism=row.get("organism"),
        submitter=row.get("submitter"),
        submission_date=row.get("submission_date"),
        publication_date=row.get("publication_date"),
        data_type=row.get("data_type"),
        sample_count=row.get("sample_count"),
        study_type=row.get("study_type"),
        related_pubmed=row.get("related_pubmed"),
        related_doi=row.get("related_doi"),
    )


@coexpression_router.get("/coexpression/projects")
def list_bioprojects(
    source: str | None = Query(None, pattern="^(NCBI|ENA|CNGB)$"),
    q: str | None = Query(None, description="Substring search over title/description/organism"),
) -> dict:
    """List bioproject metadata records.

    功能:
        返回 `coexpressiondb.bioproject_meta` 表中已爬取的 bioproject
        元数据。可选按数据源过滤（NCBI/ENA/CNGB），可选按标题/描述/
        物种做子串模糊搜索。

    用法:
        GET /api/coexpression/projects
        GET /api/coexpression/projects?source=NCBI
        GET /api/coexpression/projects?q=wheat
    """
    where = []
    params: list = []
    if source:
        where.append("source = %s")
        params.append(source)
    if q:
        like = f"%{q}%"
        where.append("(title LIKE %s OR description LIKE %s OR organism LIKE %s)")
        params.extend([like, like, like])

    sql = "SELECT * FROM bioproject_meta"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY source, accession"

    with mysql_cursor(settings.DB_COEXPRESSION) as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    records = [_bioproject_from_row(r).model_dump() for r in rows]
    return ok({"total": len(records), "records": records})


@coexpression_router.get("/coexpression/projects/{accession}")
def get_bioproject(accession: str) -> dict:
    """Return one bioproject's metadata, 404 if absent.

    用法:
        GET /api/coexpression/projects/PRJNA976214
    """
    with mysql_cursor(settings.DB_COEXPRESSION) as cursor:
        cursor.execute("SELECT * FROM bioproject_meta WHERE accession = %s", (accession,))
        row = cursor.fetchone()
    if not row:
        raise ResourceNotFound(f"Bioproject not found: {accession}")
    return ok(_bioproject_from_row(row).model_dump())

