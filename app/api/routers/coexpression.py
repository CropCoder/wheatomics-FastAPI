"""Coexpression network routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.response import ok
from app.core.security import COEXPRESSION_TABLES, ensure_allowed_table, ensure_gene_like
from app.db.mysql import mysql_cursor
from app.schemas.network import CoexpressionPair

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
    filter_value: float = Query(0.8),
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
        - filter_value: 可选，筛选阈值，默认 0.8（PCC 模式）

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

    # SELECT aliases make the row dict case-insensitive: existing tables
    # (CO_result2, CO_PRJEB25639) use Gene1/Gene2/PCC/MR (PascalCase),
    # while coexpression_filter_ext uses lowercase gene1/gene2/pcc/mr.
    select_cols = """
        COALESCE(NULLIF(Gene1, ''), gene1) AS Gene1,
        COALESCE(NULLIF(Gene2, ''), gene2) AS Gene2,
        COALESCE(NULLIF(PCC,   ''), pcc)   AS PCC,
        COALESCE(NULLIF(MR,    ''), mr)    AS MR
    """

    with mysql_cursor(settings.DB_COEXPRESSION) as cursor:
        for gene in genes:
            if "." in str(filter_value):
                cursor.execute(
                    f"""
                    SELECT {select_cols}
                    FROM `{database}`
                    WHERE (Gene1 = %s OR Gene2 = %s OR gene1 = %s OR gene2 = %s)
                    AND (CAST(PCC AS DECIMAL(10,4)) >= %s OR CAST(PCC AS DECIMAL(10,4)) <= %s)
                    ORDER BY CAST(PCC AS DECIMAL(10,4)) DESC
                    """,
                    (gene, gene, gene, gene, filter_value, -filter_value),
                )
            else:
                cursor.execute(
                    f"""
                    SELECT {select_cols}
                    FROM `{database}`
                    WHERE (Gene1 = %s OR Gene2 = %s OR gene1 = %s OR gene2 = %s)
                    AND CAST(MR AS UNSIGNED) <= %s
                    ORDER BY CAST(MR AS UNSIGNED) ASC
                    """,
                    (gene, gene, gene, gene, int(filter_value)),
                )
            for row in cursor.fetchall():
                gene1 = str(row["Gene1"]).strip()
                gene2 = str(row["Gene2"]).strip()
                key = tuple(sorted((gene1, gene2)))
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(
                    CoexpressionPair(
                        gene1=gene1,
                        gene2=gene2,
                        pcc=float(row["PCC"]),
                        mr=int(str(row["MR"]).split(".")[0]),
                    )
                )

    return ok({"database": database, "pairs": [pair.model_dump() for pair in pairs]})

