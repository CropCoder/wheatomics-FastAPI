"""Expression routes refactored from legacy CGI scripts."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.exceptions import ResourceNotFound
from app.core.response import ok
from app.core.security import EXPRESSION_PROJECTS, ensure_allowed_table, ensure_gene_like
from app.db.mysql import mysql_cursor
from app.schemas.expression import ExpressionGeneResult, ExpressionPoint, ExpressionQueryResponse
from app.services.expression_catalog import PROJECT_CATEGORIES, list_projects

router = APIRouter(prefix="/expression", tags=["Expression"])


@router.get("/projects")
def get_expression_projects() -> dict:
    """获取可用的基因表达项目列表。

    功能:
        返回系统支持的所有表达谱项目，按分类（Tissue、Abiotic、Biotic、Development）
        组织，每个项目包含名称和对应的数据表名。

    用法:
        GET /api/expression/projects
        无需参数。

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/expression/projects"

        响应:
          {
            "success": true,
            "data": {
              "Tissue": [
                { "name": "PRJEB5314 - Tissue Atlas", "table": "PRJEB5314_paired_tbl" }
              ],
              "Abiotic": [
                { "name": "PRJEB25639 - Drought Stress", "table": "PRJEB25639_tbl" }
              ],
              "Biotic": [...],
              "Development": [...]
            }
          }
    """

    return ok(list_projects())


@router.get("/query", response_model=ExpressionQueryResponse)
def query_expression(
    gene_ids: str = Query(..., description="Comma separated gene IDs"),
    project: str = Query("PRJEB5314_paired_tbl"),
) -> ExpressionQueryResponse:
    """查询基因在指定表达项目中的表达量。

    功能:
        查询一个或多个基因在指定表达谱项目中的表达值及标准差。
        支持多个基因同时查询（逗号分隔），返回每个基因在不同
        实验条件下的表达量点数据（含误差棒）。

    用法:
        GET /api/expression/query?gene_ids=<基因1,基因2>&project=<项目表名>
        - gene_ids: 必填，逗号分隔的基因 ID 列表
        - project: 可选，表达项目表名，默认 PRJEB5314_paired_tbl

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/expression/query?gene_ids=TraesCS5A02G391700,TraesCS5A02G123456&project=PRJEB5314_paired_tbl"

        响应:
          {
            "project": "PRJEB5314_paired_tbl",
            "genes_found": 2,
            "genes_not_found": [],
            "results": [
              {
                "gene_id": "TraesCS5A02G391700",
                "project": "PRJEB5314_paired_tbl",
                "points": [
                  { "label": "root", "value": 12.5, "std": 1.2, "error_bar": [11.3, 13.7] },
                  { "label": "leaf", "value": 45.2, "std": 3.1, "error_bar": [42.1, 48.3] }
                ]
              }
            ]
          }
    """

    project = ensure_allowed_table(project, EXPRESSION_PROJECTS, "expression project")
    requested_genes = [ensure_gene_like(gene.strip()) for gene in gene_ids.split(",") if gene.strip()]
    if not requested_genes:
        raise ResourceNotFound("No valid gene IDs provided")

    labels = PROJECT_CATEGORIES.get(project, [])
    results: list[ExpressionGeneResult] = []
    missing: list[str] = []

    with mysql_cursor(settings.DB_GENE_EXPRESSION) as cursor:
        for gene_id in requested_genes:
            cursor.execute(f"SELECT * FROM `{project}` WHERE GeneID = %s", (gene_id,))
            row = cursor.fetchone()
            if not row:
                missing.append(gene_id)
                continue

            std_row = None
            try:
                cursor.execute(f"SELECT * FROM `{project}_std` WHERE GeneID = %s", (gene_id,))
                std_row = cursor.fetchone()
            except Exception:
                std_row = None

            values = []
            std_values = []
            ordered_keys = [key for key in row.keys() if key not in {"GeneID", "IWGSCV1_1_id", "id", "ID"}]
            if not labels:
                labels = ordered_keys

            for key in ordered_keys:
                values.append(float(row[key]) if row[key] is not None else 0.0)
                if std_row and key in std_row and std_row[key] is not None:
                    std_values.append(float(std_row[key]))
                else:
                    std_values.append(None)

            points = []
            for label, value, std_value in zip(labels, values, std_values):
                error_bar = None
                if std_value is not None:
                    error_bar = [round(value - std_value, 2), round(value + std_value, 2)]
                points.append(ExpressionPoint(label=label, value=value, std=std_value, error_bar=error_bar))

            results.append(ExpressionGeneResult(gene_id=gene_id, project=project, points=points))

    return ExpressionQueryResponse(
        project=project,
        genes_found=len(results),
        genes_not_found=missing,
        results=results,
    )
