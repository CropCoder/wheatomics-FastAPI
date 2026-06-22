"""PPI (protein-protein interaction) routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.response import ok
from app.core.security import PPI_TABLES, ensure_allowed_table, ensure_gene_like
from app.db.mysql import mysql_cursor
from app.schemas.network import PPIInteraction
from app.services.legacy_parsers import normalize_text

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
