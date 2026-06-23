"""Expression routes refactored from legacy CGI scripts."""

from __future__ import annotations

import re
from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.exceptions import ResourceNotFound
from app.core.response import ok
from app.core.security import ensure_gene_like
from app.db.mysql import mysql_cursor
from app.schemas.expression import ExpressionGeneResult, ExpressionPoint, ExpressionQueryResponse
from app.services.expression_catalog import list_projects, get_project_labels

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
    gene_ids: str = Query(..., description="Comma separated gene IDs. 表达数据基于中国春 IWGSC v2.1 (02G)，详见注释。"),
    project: str = Query("PRJEB5314_paired_tbl"),
) -> ExpressionQueryResponse:
    """查询基因在指定表达项目中的表达量。

    功能:
        查询一个或多个基因在指定表达谱项目中的表达值及标准差。
        支持多个基因同时查询（逗号分隔），返回每个基因在不同
        实验条件下的表达量点数据（含误差棒）。

    ⚠️  基因 ID 版本说明:
        表达量数据基于中国春 IWGSC v2.1 注释（基因 ID 含 02G 格式）。
        如果输入的是 v1（01G）或 v3（03G）格式的基因 ID，API 会自动
        将其转换为 v2 后再查询。转换结果记录在响应的 genes_converted 字段中。
        若转换失败则按原始 ID 查询，此时大概率会返回基因未找到。

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

    # 动态校验：从数据库 project_meta 验证项目是否存在
    from app.db.mysql import mysql_cursor
    with mysql_cursor(settings.DB_GENE_EXPRESSION) as cursor:
        cursor.execute("SELECT 1 FROM project_meta WHERE table_name = %s", (project,))
        if not cursor.fetchone():
            from app.core.exceptions import ValidationFailure
            raise ValidationFailure(f"Unsupported expression project: {project}")
    requested_genes = [ensure_gene_like(gene.strip()) for gene in gene_ids.split(",") if gene.strip()]
    if not requested_genes:
        raise ResourceNotFound("No valid gene IDs provided")

    results: list[ExpressionGeneResult] = []
    missing: list[str] = []
    genes_converted: dict[str, str] = {}

    # --- Auto-convert non-v2 (non-02G) gene IDs to IWGSC v2.1 ---
    with mysql_cursor(settings.DB_CONVERT_GENE_ID) as convert_cursor:
        for g in requested_genes:
            m = re.search(r"(\d{2})G", g)
            ver = m.group(1) if m else ""
            if ver == "02":
                continue
            table = {"01": "IWGSCv1_to_v2", "03": "IWGSCv3_to_v2"}.get(ver)
            if not table:
                continue
            convert_cursor.execute(f"SELECT * FROM `{table}` WHERE MIPS = %s", (g,))
            row = convert_cursor.fetchone()
            if row:
                v2_id = str(row.get("ReferenceGene") or row.get("reference_gene") or "")
                if v2_id:
                    genes_converted[g] = v2_id

    with mysql_cursor(settings.DB_GENE_EXPRESSION) as cursor:
        # 探测表结构：找基因 ID 列名和数据列
        cursor.execute(f"DESCRIBE `{project}`")
        columns = cursor.fetchall()
        gene_id_column = "GeneID"
        data_columns = []
        for col in columns:
            cname = (col.get("Field") or col[0]).strip()
            ctype = (col.get("Type") or col[1]).lower()
            # 找第一个 varchar/char/text 列作为基因 ID 列
            if any(t in ctype for t in ("varchar", "char", "text")):
                if cname.lower() not in ("id",):
                    gene_id_column = cname
            else:
                # 数值列作为数据列
                data_columns.append(cname)

        # labels 优先用 project_meta 定义，否则用数据列名
        labels = get_project_labels(project)
        if not labels and data_columns:
            labels = data_columns
        elif not labels:
            labels = [c for c in columns if (c.get("Field") or c[0]).strip().lower() not in ("id", gene_id_column.lower())]
            labels = [(c.get("Field") or c[0]) for c in labels]

        for orig_id in requested_genes:
            gene_id = genes_converted.get(orig_id, orig_id)
            cursor.execute(f"SELECT * FROM `{project}` WHERE `{gene_id_column}` = %s", (gene_id,))
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
        genes_converted=genes_converted,
        results=results,
    )
