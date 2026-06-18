"""Co-expression and PPI network routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.response import ok
from app.core.security import COEXPRESSION_TABLES, PPI_TABLES, ensure_allowed_table, ensure_gene_like
from app.db.mysql import mysql_cursor
from app.schemas.network import CoexpressionPair, NetworkEdge, NetworkNode, PPIInteraction
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


@coexpression_router.get("/coexpression/network")
def coexpression_network(
    gene_ids: str = Query(...),
    database: str = Query("CO_PRJEB25639"),
    pcc_threshold: float = Query(0.8),
) -> dict:
    """生成共表达网络图数据（节点和边）。

    功能:
        根据输入的基因 ID 列表，在指定共表达数据库中查询并构建
        网络图数据。返回 nodes（节点列表，标注哪些是查询基因）
        和 edges（边列表，含 PCC 绝对值作为边的权重），
        可直接用于前端网络可视化（如 Cytoscape.js / ECharts）。

    用法:
        GET /api/coexpression/network?gene_ids=<基因1,基因2>&database=<数据库>&pcc_threshold=<阈值>
        - gene_ids: 必填，逗号分隔的基因 ID 列表
        - database: 可选，共表达数据库 ID，默认 CO_PRJEB25639
        - pcc_threshold: 可选，PCC 阈值（绝对值），默认 0.8

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/coexpression/network?gene_ids=TraesCS5A02G391700,TraesCS5A02G123456&pcc_threshold=0.9"

        响应:
          {
            "success": true,
            "data": {
              "nodes": [
                { "id": "TraesCS5A02G391700", "label": "TraesCS5A02G391700", "is_query": true },
                { "id": "TraesCS5B02G654321", "label": "TraesCS5B02G654321", "is_query": false }
              ],
              "edges": [
                { "source": "TraesCS5A02G391700", "target": "TraesCS5B02G654321", "value": 0.95 }
              ]
            }
          }
    """

    database = ensure_allowed_table(database, COEXPRESSION_TABLES, "coexpression table")
    genes = [ensure_gene_like(gene.strip()) for gene in gene_ids.split(",") if gene.strip()]
    query_genes = set(genes)
    nodes: dict[str, NetworkNode] = {}
    edges: dict[tuple[str, str], NetworkEdge] = {}

    with mysql_cursor(settings.DB_COEXPRESSION) as cursor:
        for gene in genes:
            cursor.execute(
                f"""
                SELECT Gene1, Gene2, PCC FROM `{database}`
                WHERE (Gene1 = %s OR Gene2 = %s)
                AND (CAST(PCC AS DECIMAL(10,4)) >= %s OR CAST(PCC AS DECIMAL(10,4)) <= %s)
                ORDER BY CAST(PCC AS DECIMAL(10,4)) DESC
                """,
                (gene, gene, pcc_threshold, -pcc_threshold),
            )
            for row in cursor.fetchall():
                gene1 = str(row["Gene1"]).strip()
                gene2 = str(row["Gene2"]).strip()
                nodes.setdefault(gene1, NetworkNode(id=gene1, label=gene1, is_query=gene1 in query_genes))
                nodes.setdefault(gene2, NetworkNode(id=gene2, label=gene2, is_query=gene2 in query_genes))
                key = tuple(sorted((gene1, gene2)))
                edges.setdefault(key, NetworkEdge(source=gene1, target=gene2, value=abs(float(row["PCC"]))))

    return ok({"nodes": [node.model_dump() for node in nodes.values()], "edges": [edge.model_dump() for edge in edges.values()]})


@ppi_router.get("/ppi/query")
def query_ppi(
    gene_ids: str = Query(...),
    table: str = Query("PPI_result"),
    min_score: float = Query(0.5),
) -> dict:
    """查询蛋白质互作（PPI）关系。

    功能:
        根据基因 ID 列表，在蛋白质互作数据库中查询与该蛋白
        存在相互作用的蛋白对。返回互作双方的基因 ID、
        eggNOG ID、功能注释和互作得分（Score）。

    用法:
        GET /api/ppi/query?gene_ids=<基因1,基因2>&table=<表名>&min_score=<最小得分>
        - gene_ids: 必填，逗号分隔的基因 ID 列表
        - table: 可选，PPI 数据表名，默认 PPI_result
        - min_score: 可选，最低互作得分阈值，默认 0.5

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/ppi/query?gene_ids=TraesCS5A02G391700&min_score=0.7"

        响应:
          {
            "success": true,
            "data": {
              "interactions": [
                {
                  "wheat_id1": ["TraesCS5A02G391700"],
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
            for row in cursor.fetchall():
                interactions.append(
                    PPIInteraction(
                        wheat_id1=[item.strip() for item in str(row["WheatID1"]).split("#") if item.strip()],
                        wheat_id2=[item.strip() for item in str(row["WheatID2"]).split("#") if item.strip()],
                        eggnog_id1=str(row["eggNOGID1"]),
                        eggnog_id2=str(row["eggNOGID2"]),
                        score=float(row["Score"]),
                        annotation1=normalize_text(row["Annotation1"]),
                        annotation2=normalize_text(row["Annotation2"]),
                    )
                )

    return ok({"interactions": [interaction.model_dump() for interaction in interactions]})
