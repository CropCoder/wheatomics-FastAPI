"""Co-expression and PPI network routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.response import ok
from app.core.security import COEXPRESSION_TABLES, PPI_TABLES, ensure_allowed_table, ensure_gene_like
from app.db.mysql import mysql_cursor
from app.schemas.network import CoexpressionPair, PPIInteraction
from app.services.legacy_parsers import normalize_text

coexpression_router = APIRouter(tags=["Coexpression"])
ppi_router = APIRouter(tags=["PPI"])


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
              { "id": "CO_PRJEB25639", "description": "干旱胁迫共表达网络" },
              { "id": "CO_PRJEB5314", "description": "组织表达共表达网络" }
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
        - database: 可选，共表达数据库 ID，默认 CO_PRJEB25639
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
                { "gene1": "TraesCS5A02G391700", "gene2": "TraesCS5B02G123456", "pcc": 0.95, "mr": 3 }
              ]
            }
          }
    """

    database = ensure_allowed_table(database, COEXPRESSION_TABLES, "coexpression table")
    genes = [ensure_gene_like(gene.strip()) for gene in gene_ids.split(",") if gene.strip()]
    pairs: list[CoexpressionPair] = []
    seen: set[tuple[str, str]] = set()

    with mysql_cursor(settings.DB_COEXPRESSION) as cursor:
        for gene in genes:
            if "." in str(filter_value):
                cursor.execute(
                    f"""
                    SELECT * FROM `{database}`
                    WHERE (Gene1 = %s OR Gene2 = %s)
                    AND (CAST(PCC AS DECIMAL(10,4)) >= %s OR CAST(PCC AS DECIMAL(10,4)) <= %s)
                    ORDER BY CAST(PCC AS DECIMAL(10,4)) DESC
                    """,
                    (gene, gene, filter_value, -filter_value),
                )
            else:
                cursor.execute(
                    f"""
                    SELECT * FROM `{database}`
                    WHERE (Gene1 = %s OR Gene2 = %s)
                    AND CAST(MR AS UNSIGNED) <= %s
                    ORDER BY CAST(MR AS UNSIGNED) ASC
                    """,
                    (gene, gene, int(filter_value)),
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


@ppi_router.get("/ppi/query")
def query_ppi(
    gene_ids: str = Query(...),
    table: str = Query("PPI_result"),
    min_score: float = Query(0.5),
) -> dict:
    """查询蛋白质互作（PPI）关系。

    ⚠️  基因 ID 说明:
        本模块使用小麦蛋白互作数据（wheatPPI），基于中国春 IWGSC v2.1 注释。
        需要输入转录本 ID（即基因 ID 后加 ".1" 后缀），例如
        "TraesCS6D02G084800.1"。若输入不带 ".1" 的基因 ID，
        查询将无法匹配到结果。

    功能:
        根据基因 ID 列表，在蛋白质互作数据库中查询与该蛋白
        存在相互作用的蛋白对。返回互作双方的基因 ID、
        eggNOG ID、功能注释和互作得分（Score）。

        Score 筛选阈值说明（CF-MS 得分）:
        - 0.5: 中等置信度（默认）
        - 0.2: 低置信度
        - 0: 不筛选，返回所有记录

    用法:
        GET /api/ppi/query?gene_ids=<基因1,基因2>&table=<表名>&min_score=<最小得分>
        - gene_ids: 必填，逗号分隔的基因 ID 列表（需带 ".1" 后缀的转录本 ID）
        - table: 可选，PPI 数据表名，默认 PPI_result
        - min_score: 可选，CF-MS 互作得分阈值，默认 0.5。常用值 0.5（中）、0.2（低）、0（全部）

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/ppi/query?gene_ids=TraesCS6D02G084800.1&min_score=0.5"

        响应:
          {
            "success": true,
            "data": {
              "interactions": [
                {
                  "wheat_id1": ["TraesCS6D02G084800"],
                  "wheat_id2": ["TraesCS5B02G123456"],
                  "eggnog_id1": "ENOG410XNNN",
                  "eggnog_id2": "ENOG410XMMM",
                  "score": 0.95,
                  "annotation1": "MADS-box transcription factor",
                  "annotation2": "Flowering time protein"
                }
              ]
            }
          }
    """

    table = ensure_allowed_table(table, PPI_TABLES, "ppi table")
    genes = [ensure_gene_like(gene.strip()) for gene in gene_ids.split(",") if gene.strip()]
    interactions: list[PPIInteraction] = []

    with mysql_cursor(settings.DB_PPI) as cursor:
        for gene in genes:
            cursor.execute(
                f"""
                SELECT * FROM `{table}`
                WHERE (WheatID1 REGEXP %s OR WheatID2 REGEXP %s) AND Score >= %s
                """,
                (gene, gene, min_score),
            )
            # Discover actual column names from cursor.description (positional, like CGI)
            col_map = {}
            if cursor.description:
                cnames = [d[0] for d in cursor.description]
                # Map by position to match CGI select * order
                col_map = {
                    "WheatID1":     cnames[1] if len(cnames) > 1 else "WheatID1",
                    "WheatID2":     cnames[2] if len(cnames) > 2 else "WheatID2",
                    "eggNOGID1":    cnames[3] if len(cnames) > 3 else "eggNOGID1",
                    "eggNOGID2":    cnames[4] if len(cnames) > 4 else "eggNOGID2",
                    "Score":        cnames[5] if len(cnames) > 5 else "Score",
                    "Annotation1":  cnames[6] if len(cnames) > 6 else "Annotation1",
                    "Annotation2":  cnames[7] if len(cnames) > 7 else "Annotation2",
                }
            for row in cursor.fetchall():
                interactions.append(
                    PPIInteraction(
                        wheat_id1=[item.strip() for item in str(row[col_map["WheatID1"]]).split("#") if item.strip()],
                        wheat_id2=[item.strip() for item in str(row[col_map["WheatID2"]]).split("#") if item.strip()],
                        eggnog_id1=str(row[col_map["eggNOGID1"]]),
                        eggnog_id2=str(row[col_map["eggNOGID2"]]),
                        score=float(row[col_map["Score"]]),
                        annotation1=normalize_text(str(row[col_map["Annotation1"]])),
                        annotation2=normalize_text(str(row[col_map["Annotation2"]])),
                    )
                )

    return ok({"interactions": [interaction.model_dump() for interaction in interactions]})
