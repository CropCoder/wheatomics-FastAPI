"""Expression routes refactored from legacy CGI scripts."""

from __future__ import annotations

import re
from fastapi import APIRouter, HTTPException, Query

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
    """Get the list of available gene expression projects.

    Purpose:
        Return all expression profiling projects supported by the system, organized
        by category (Tissue, Abiotic, Biotic, Development); each project contains
        its name and the corresponding data table name.

    Usage:
        GET /api/expression/projects
        No parameters required.

    Example:
        Request:
          curl -X GET "http://localhost:8000/api/expression/projects"

        Response:
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


@router.get("/query")
def query_expression(
    gene_ids: str | list[str] = Query(
        ...,
        description="Gene IDs: comma-separated string (gene_ids=a,b) or repeated "
                    "params (gene_ids=a&gene_ids=b). Expression data is based on Chinese Spring IWGSC v2.1 (02G); see the notes."),
    project: str = Query("PRJEB5314_paired_tbl", examples=["PRJEB5314_paired_tbl", "PRJEB25639_tbl", "ABA_JA_6BA_DMSO3h_mean_tbl"]),
) -> dict:
    """Query gene expression values in a given expression project.

    Purpose:
        Query the expression values and standard deviations of one or more genes
        in a given expression profiling project. Multiple genes can be queried at
        once (comma-separated string or repeated parameters); returns each gene's
        expression points under different experimental conditions (with error bars).
        The response uses the platform's standard envelope
        {success, message, timestamp, data}.

    ⚠️  Gene ID version note:
        Expression data is based on the Chinese Spring IWGSC v2.1 annotation
        (gene IDs use the 02G format). If a v1 (01G) or v3 (03G) gene ID is
        provided, the API converts it to v2 before querying. Conversion results
        are recorded in the response's genes_converted field. If conversion fails,
        the query uses the original ID and most likely returns gene not found.

    Usage:
        GET /api/expression/query?gene_ids=<gene1,gene2>&project=<project table name>
        - gene_ids: required, comma-separated gene ID list (or repeated gene_ids parameters)
        - project: optional, expression project table name, default PRJEB5314_paired_tbl

    Example:
        Request:
          curl -X GET "http://localhost:8000/api/expression/query?gene_ids=TraesCS5A02G391700&project=PRJEB5314_paired_tbl"
          curl -X GET "http://localhost:8000/api/expression/query?gene_ids=TraesCS5A02G391700&gene_ids=TraesCS1A02G001000"

        Response:
          {
            "success": true, "message": "ok", "timestamp": "...",
            "data": {
              "project": "PRJEB5314_paired_tbl",
              "genes_found": 2,
              "genes_not_found": [],
              "results": [ ... ]
            }
          }
    """

    # Accept both the legacy comma-separated string and repeated-param /
    # list forms so agent clients can pass arrays positionally.
    def _split(raw: str) -> list[str]:
        return [g.strip() for g in raw.split(",") if g.strip()]

    if isinstance(gene_ids, str):
        gene_id_items = _split(gene_ids)
    else:
        gene_id_items = []
        for item in gene_ids:
            gene_id_items.extend(_split(str(item)))

    # 动态校验：从数据库 project_meta 验证项目是否存在
    from app.db.mysql import mysql_cursor
    with mysql_cursor(settings.DB_GENE_EXPRESSION) as cursor:
        cursor.execute("SELECT 1 FROM project_meta WHERE table_name = %s", (project,))
        if not cursor.fetchone():
            from app.core.exceptions import ValidationFailure
            raise ValidationFailure(f"Unsupported expression project: {project}")
    requested_genes = [ensure_gene_like(g) for g in gene_id_items]
    if not requested_genes:
        raise ResourceNotFound("No valid gene IDs provided")

    results: list[ExpressionGeneResult] = []
    missing: list[str] = []
    genes_converted: dict[str, str] = {}

    # --- Auto-convert non-v2 (non-02G) gene IDs to IWGSC v2.1 ---
    # Batched: a single SQL query to Genehub_DB.GenePageIWGSCv1_table resolves
    # every v1/v3 ID at once. Previously this issued one localhost HTTP
    # self-call per gene to /api/genes/detail/{g} — a self-inflicted deadlock
    # (sync urllib held a threadpool worker waiting for another request that
    # also needed a worker) plus an N+1 of DB round-trips.
    v1_to_v2: dict[str, str] = {}
    v3_to_v2: dict[str, str] = {}
    need_lookup = [
        g for g in requested_genes
        if re.search(r"(\d{2})G", g) and not g.__contains__("02G")
    ]
    if need_lookup:
        with mysql_cursor(settings.DB_GENEHUB) as cursor:
            placeholders = ",".join(["%s"] * len(need_lookup))
            cursor.execute(
                f"SELECT GeneIDv1, GeneIDv2, GeneIDv3 FROM GenePageIWGSCv1_table "
                f"WHERE GeneIDv1 IN ({placeholders}) OR GeneIDv3 IN ({placeholders})",
                (*need_lookup, *need_lookup),
            )
            for row in cursor.fetchall():
                v2 = row.get("GeneIDv2")
                if not v2:
                    continue
                if row.get("GeneIDv1"):
                    v1_to_v2[str(row["GeneIDv1"])] = str(v2)
                if row.get("GeneIDv3"):
                    v3_to_v2[str(row["GeneIDv3"])] = str(v2)

    for g in requested_genes:
        m = re.search(r"(\d{2})G", g)
        ver = m.group(1) if m else ""
        if ver == "02":
            continue
        if ver == "01":
            # 01G → 02G: 优先查 GenePageIWGSCv1_table 拿真实映射；
            # 未命中则按 ID 前缀规则字符串替换（IWGSC v1→v2 前缀一致）。
            v2_id = v1_to_v2.get(g) or g.replace("01G", "02G", 1)
            if v2_id != g:
                genes_converted[g] = v2_id
        elif ver == "03":
            # 03G → 02G: 优先查表，未命中则字符串替换兜底。
            v2_id = v3_to_v2.get(g) or g.replace("03G", "02G", 1)
            if v2_id != g:
                genes_converted[g] = v2_id

    with mysql_cursor(settings.DB_GENE_EXPRESSION) as cursor:
        # 探测表结构：找基因 ID 列名和数据列
        try:
            cursor.execute(f"DESCRIBE `{project}`")
            columns = cursor.fetchall()
        except Exception as exc:
            # Some project_meta rows point at data tables that do not exist (or are
            # unreadable). Return a clear JSON 503 instead of letting the connection
            # drop / a generic 500 bubble up (14 projects currently hit this path).
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Expression data for project '{project}' is currently unavailable "
                    f"(data table missing or unreadable: {type(exc).__name__})."
                ),
            )
        gene_id_column = "GeneID"
        data_columns = []

        # 1) 基因 ID 列：优先精确匹配 GeneID / gene_id / gene，
        #    避免被 IWGSCV1_1_id 等其他文本列覆盖（旧逻辑无 break 且未排除）。
        for col in columns:
            cname = (col.get("Field") or col[0]).strip()
            if cname.lower() in ("geneid", "gene_id", "gene"):
                gene_id_column = cname
                break
        else:
            # 回退：第一个非元数据的 varchar/char/text 列
            for col in columns:
                cname = (col.get("Field") or col[0]).strip()
                ctype = (col.get("Type") or col[1]).lower()
                if any(t in ctype for t in ("varchar", "char", "text")):
                    if cname.lower() not in ("id", "iwgscv1_1_id", "name"):
                        gene_id_column = cname
                        break

        # 2) 数据列：非文本、非元数据的列
        for col in columns:
            cname = (col.get("Field") or col[0]).strip()
            ctype = (col.get("Type") or col[1]).lower()
            if any(t in ctype for t in ("varchar", "char", "text")):
                continue
            if cname.lower() not in ("id", "geneid", "iwgscv1_1_id", "name"):
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
            # Positional pairing is only safe when both sides have the same length.
            # A numeric IWGSCV1_1_id column (or a stale project_meta.labels list) can
            # make len(labels) != len(values); fall back to the real column names so
            # that labels and values stay aligned instead of silently shifting.
            if len(labels) != len(values):
                labels = list(ordered_keys)

            for label, value, std_value in zip(labels, values, std_values):
                error_bar = None
                if std_value is not None:
                    error_bar = [round(value - std_value, 2), round(value + std_value, 2)]
                points.append(ExpressionPoint(label=label, value=value, std=std_value, error_bar=error_bar))

            results.append(ExpressionGeneResult(gene_id=gene_id, project=project, points=points))

    return ok(ExpressionQueryResponse(
        project=project,
        genes_found=len(results),
        genes_not_found=missing,
        genes_converted=genes_converted,
        results=results,
    ).model_dump())
