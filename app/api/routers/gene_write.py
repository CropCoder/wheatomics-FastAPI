"""KnownGene 写接口路由：API Key 鉴权 + 新增 / 更新 / 批量 + 审计查询。

挂载方式（main.py）::

    from app.api.routers import gene_write
    ... for router in [... gene_write]: app.include_router(router, prefix="/api")

最终路径（prefix 已由 include_router 补 ``/api``，本文件不再写 ``/api``）:

===============================  ======  ========================================
路径                             方法    说明
===============================  ======  ========================================
/api/genes/known/write           POST    新增一条 KnownGene（支持 dry_run）
/api/genes/known/write/{clone_id} PATCH  按 clone_id 更新（只改传入字段，支持 dry_run）
/api/genes/known/write/bulk      POST    批量新增/更新（≤500 行，支持 dry_run）
/api/genes/known/write/changes   GET     审计日志查询（需要 admin scope）
/api/genes/known/write/whoami    GET     当前 API Key 信息（任意有效 key）
===============================  ======  ========================================

鉴权 / 限流 / 请求体保护见 ``app/core/known_gene_auth.py``；字段规格、派生、事务
写入与审计见 ``app/services/known_gene_ingest.py``。返回统一 ``ok(...)`` 信封；
错误用 401/403/404/409/413/422/429/503 + 中文 detail。

安全设计（验收点）:
- 校验/限流在依赖层完成，业务函数全部参数化 SQL（无字符串拼接值）；
- 每次写操作与审计写**同一事务**（``with mysql_cursor(...)`` 成功才 commit）；
- 更新前 ``SELECT ... FOR UPDATE`` 锁行，避免并发覆盖；
- 日志只记录 key_id / label / key_prefix / client_ip，绝不记录 raw key。
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.routers.gene import _row_to_known_detail
from app.core.config import settings
from app.core.exceptions import ResourceNotFound
from app.core.known_gene_auth import (
    AuthContext,
    enforce_known_gene_body_limit,
    get_key_info,
    read_json_object,
    require_known_gene_scope,
    split_scopes,
    verify_known_gene_key,
)
from app.core.response import ok
from app.db.mysql import mysql_cursor
from app.services import known_gene_ingest as ingest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/genes/known/write", tags=["Known Genes (write)"])

#: 写端点通用错误响应说明（OpenAPI 文档用）。
_WRITE_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "请求体不是合法 JSON / 参数格式错误"},
    401: {"description": "缺少或无效的 API Key（不存在/停用/过期统一 401）"},
    403: {"description": "API Key scope 不足，或来源 IP 不在白名单"},
    404: {"description": "clone_id 不存在"},
    409: {"description": "(gene_id, gene_name) 已存在"},
    413: {"description": "请求体超过 2MB"},
    422: {"description": "业务字段校验失败（detail.errors 为逐条中文错误）"},
    429: {"description": "超过每 Key 每分钟写请求上限"},
    503: {"description": "鉴权表未初始化 / 数据库不可用"},
}

#: ``POST /`` 的 OpenAPI 请求体声明（实际解析用手写逻辑，以兼容"裸对象"形式）。
_CREATE_REQUEST_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "description": (
                        "推荐形式 {\"dry_run\": false, \"gene\": {...}}；"
                        "也可直接把基因字段放在顶层（裸对象）。"
                    ),
                    "properties": {
                        "dry_run": {"type": "boolean", "default": False},
                        "gene": {
                            "type": "object",
                            "additionalProperties": True,
                            "description": "基因字段；详见 GET /api/genes/known/write/whoami 同页文档字段表",
                        },
                    },
                    "additionalProperties": True,
                },
                "example": {
                    "dry_run": True,
                    "gene": {
                        "gene_id": "TraesCS7B03G0166400",
                        "gene_name": "TaERF1-B",
                        "reference_genome_id": "TraesCS7B03G0166400",
                        "gene_species": "Triticum aestivum (bread wheat)",
                        "chrom_pos": "Refv1.0 chr7B:112.264-112.266Mb",
                        "gene_phenotype": "Drought tolerance; Salt tolerance",
                        "functional_category": "Biotic & Abiotic Stress",
                        "research_strategy": "Reverse genetics",
                        "key_result": "Overexpression of TaERF1 improves drought tolerance.",
                        "paper_title": "Isolation and molecular characterization of TaERF1",
                        "paper_doi": "10.1007/s11103-007-9237-9",
                        "publication_year": 2007,
                    },
                },
            }
        },
    }
}

_PATCH_REQUEST_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "description": (
                        "推荐形式 {\"dry_run\": false, \"fields\": {...}}；"
                        "也可直接把要改的字段放在顶层（裸对象）。"
                    ),
                    "properties": {
                        "dry_run": {"type": "boolean", "default": False},
                        "fields": {
                            "type": "object",
                            "additionalProperties": True,
                            "description": "要更新的字段（白名单同新增，不含 clone_id）",
                        },
                    },
                    "additionalProperties": True,
                },
                "example": {
                    "dry_run": True,
                    "fields": {
                        "gene_phenotype": "Drought tolerance; Salt tolerance; Heat tolerance",
                        "publication_years": "2007; 2024",
                    },
                },
            }
        },
    }
}

_BULK_REQUEST_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["rows"],
                    "properties": {
                        "rows": {
                            "type": "array",
                            "maxItems": 500,
                            "items": {"type": "object", "additionalProperties": True},
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["insert_only", "upsert"],
                            "default": "upsert",
                            "description": "insert_only：任一 (gene_id,gene_name) 已存在则整批拒绝；upsert：已存在则更新",
                        },
                        "dry_run": {
                            "type": "boolean",
                            "default": True,
                            "description": "默认 true（先预演）；确认后再显式传 false 落库",
                        },
                    },
                    "additionalProperties": False,
                },
                "example": {
                    "mode": "upsert",
                    "dry_run": True,
                    "rows": [
                        {
                            "gene_id": "TraesCS7B03G0166400",
                            "gene_name": "TaERF1-B",
                            "reference_genome_id": "TraesCS7B03G0166400",
                            "gene_species": "Triticum aestivum (bread wheat)",
                            "chrom_pos": "Refv1.0 chr7B:112.264-112.266Mb",
                            "gene_phenotype": "Drought tolerance",
                            "functional_category": "Biotic & Abiotic Stress",
                            "research_strategy": "Reverse genetics",
                            "key_result": "Overexpression of TaERF1 improves drought tolerance.",
                            "paper_doi": "10.1007/s11103-007-9237-9",
                        }
                    ],
                },
            }
        },
    }
}


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------
def _http_validation_error(exc: ingest.GeneWriteValidationError) -> HTTPException:
    """业务校验错误 → 422（detail 保留逐条中文错误 + 提示）。"""

    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=exc.as_detail(),
    )


def _http_duplicate_error(exc: ingest.DuplicateGeneError) -> HTTPException:
    """唯一键冲突 → 409。"""

    detail = (
        f"KnownGene 已存在：gene_id={exc.gene_id!r}, gene_name={exc.gene_name!r}"
        + (f"（clone_id={exc.clone_id}）" if exc.clone_id else "")
        + "；如需修改请使用 PATCH /api/genes/known/write/{clone_id}"
    )
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _detail_payload(row: dict) -> dict:
    """DB 行 → 详情 payload（复用读接口 ``_row_to_known_detail``，形状完全一致）。"""

    return _row_to_known_detail(row).model_dump()


def _iso(value: object) -> Optional[str]:
    """date/datetime → ISO 字符串（审计/密钥信息返回用）。"""

    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value if value is not None else None


def _split_body(
    payload: dict[str, Any],
    nested_keys: tuple[str, ...],
    *,
    default_dry_run: bool = False,
) -> tuple[dict[str, Any], bool]:
    """把请求体拆成 (字段 dict, dry_run)。

    兼容两种写法:
    1. 推荐：``{"dry_run": false, "<nested_key>": {...}}``；
    2. 便捷：裸字段对象（如 ``{"gene_id": "..."}``，不含 dry_run）。
    嵌套字段名允许 ``gene``（新增）/ ``fields``（更新），见各端点 docstring。
    """

    if "dry_run" in payload:
        dry_run = payload["dry_run"]
        if not isinstance(dry_run, bool):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="dry_run 必须是布尔值 true/false",
            )
    else:
        dry_run = default_dry_run

    provided_nested = [key for key in nested_keys if payload.get(key) is not None]
    if len(provided_nested) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不能同时提供多个嵌套字段对象: {provided_nested}；请只用 {provided_nested[0]}",
        )
    if provided_nested:
        nested_key = provided_nested[0]
        nested = payload[nested_key]
        if not isinstance(nested, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"字段 {nested_key} 必须是 JSON object",
            )
        extra = sorted(set(payload) - set(nested_keys) - {"dry_run"})
        if extra:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"使用 {nested_key} 嵌套形式时不能再传顶层字段: {extra}；"
                    f"或直接用裸对象形式（不带 {nested_key}）"
                ),
            )
        return nested, dry_run
    return {key: value for key, value in payload.items() if key != "dry_run"}, dry_run


def _parse_bulk_payload(payload: dict[str, Any]) -> tuple[list[dict], str, bool]:
    """解析批量请求体，返回 ``(rows, mode, dry_run)``。"""

    extra = sorted(set(payload) - {"rows", "mode", "dry_run"})
    if extra:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"批量请求体含未知字段: {extra}（允许 rows / mode / dry_run）",
        )
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"errors": ["rows 必须是非空 JSON 数组"]},
        )
    limit = int(settings.KNOWN_GENE_WRITE_BATCH_LIMIT or 500)
    if len(rows) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"批量行数 {len(rows)} 超过上限 {limit}；请分批提交（scripts/known_gene_push.py 会自动分批）",
        )
    mode = payload.get("mode", "upsert")
    if mode not in ingest.BULK_MODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"errors": [f"mode 取值非法: {mode!r}；允许值: insert_only / upsert"]},
        )
    dry_run = payload.get("dry_run", True)
    if not isinstance(dry_run, bool):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="dry_run 必须是布尔值 true/false（批量默认 true）",
        )
    return rows, str(mode), dry_run


# ---------------------------------------------------------------------------
# POST /api/genes/known/write — 新增
# ---------------------------------------------------------------------------
@router.post(
    "",
    dependencies=[Depends(enforce_known_gene_body_limit)],
    responses=_WRITE_ERROR_RESPONSES,
    openapi_extra=_CREATE_REQUEST_BODY,
)
async def create_known_gene(
    request: Request,
    ctx: AuthContext = Depends(require_known_gene_scope("write")),
) -> dict:
    """新增一条 KnownGene 记录（需要 write scope；支持 dry_run）。

    功能:
        校验并写入一条已知功能基因记录，自动派生 ``species_primary``
        （296 条原文映射 + 学名别名，回退时给 warning）、``chromosome``
        （chrom_pos 的 chr 正则）和 ``publication_year``（多值年份的最小值）；
        多值 ``paper_title`` / ``paper_doi`` / ``publication_years`` 接受 list 或
        ``"; "`` 分隔字符串，按位置对齐后以 ``###`` 存库。
        同一 (gene_id, gene_name) 重复 → 409。写入主表与审计
        （``known_gene_change_log``，action=create，after_json=完整行）同一事务。

    参数:
        - ``dry_run``: true 时只校验/查重并返回"将要写入的完整记录"，不落库；
        - ``gene``: 基因字段对象（也可直接把字段放顶层）。
        必填: gene_id / gene_name / reference_genome_id / gene_species / chrom_pos /
        gene_phenotype / functional_category / research_strategy / key_result；
        且 paper_doi 与 paper_title 至少一个。
        可选: protein_family / validation_method / cloning_method /
        cloning_method_description / function_description / author / author_mail /
        submission_date / publication_year / publication_years / paper_title /
        paper_doi；派生列 species_primary / chromosome 可显式覆盖（会校验）。
        缺省: author='WheatOmics API'、author_mail='shengweima@icloud.com'、
        submission_date=今天。

    用法:
        POST /api/genes/known/write
        Header: Authorization: Bearer kgw_xxx（或 X-API-Key: kgw_xxx）
        Body: {"dry_run": false, "gene": {...}}

    案例:
        请求:
          curl -X POST "http://localhost:8000/api/genes/known/write" \\
            -H "Authorization: Bearer $KNOWN_GENE_API_KEY" \\
            -H "Content-Type: application/json" \\
            -d '{"dry_run": true, "gene": {
                  "gene_id": "TraesCS7B03G0166400", "gene_name": "TaERF1-B",
                  "reference_genome_id": "TraesCS7B03G0166400",
                  "gene_species": "Triticum aestivum (bread wheat)",
                  "chrom_pos": "Refv1.0 chr7B:112.264-112.266Mb",
                  "gene_phenotype": "Drought tolerance",
                  "functional_category": "Biotic & Abiotic Stress",
                  "research_strategy": "Reverse genetics",
                  "key_result": "Overexpression improves drought tolerance.",
                  "paper_doi": "10.1007/s11103-007-9237-9"}}'

        响应:
          {"success": true, "message": "dry-run：校验通过，未写入",
           "timestamp": "...", "data": {"dry_run": true,
             "record": {"gene_id": "...", "species_primary": "Triticum aestivum",
                        "chromosome": "7B", "publication_year": 2007, ...},
             "warnings": []}}

        落库响应 data: {"dry_run": false, "clone_id": 1626, "audit_id": 1,
                        "record": {<detail 形状，同 /api/genes/known/{clone_id}>},
                        "warnings": []}
    """

    payload = await read_json_object(request)
    fields, dry_run = _split_body(payload, ("gene",))
    try:
        prepared = ingest.validate_create_payload(fields)
    except ingest.GeneWriteValidationError as exc:
        raise _http_validation_error(exc) from exc

    with mysql_cursor(settings.DB_CLONED_GENE) as cursor:
        if dry_run:
            duplicate = ingest.find_duplicate(
                cursor,
                str(prepared.columns.get("gene_id") or ""),
                str(prepared.columns.get("gene_name") or ""),
            )
            if duplicate:
                raise _http_duplicate_error(
                    ingest.DuplicateGeneError(
                        str(prepared.columns.get("gene_id") or ""),
                        str(prepared.columns.get("gene_name") or ""),
                        int(duplicate["clone_id"]),
                    )
                )
            projected = ingest.to_jsonable_row({**prepared.columns, "clone_id": None})
            return ok(
                {
                    "dry_run": True,
                    "record": projected,
                    "warnings": prepared.warnings,
                },
                message="dry-run：校验通过，未写入",
            )
        try:
            result = ingest.create_known_gene(
                cursor,
                prepared.columns,
                actor=ctx,
                client_ip=ctx.client_ip,
            )
        except ingest.DuplicateGeneError as exc:
            raise _http_duplicate_error(exc) from exc

    logger.info(
        "known_gene create ok: clone_id=%s key_id=%s label=%s ip=%s",
        result.clone_id,
        ctx.key_id,
        ctx.label,
        ctx.client_ip,
    )
    return ok(
        {
            "dry_run": False,
            "clone_id": result.clone_id,
            "audit_id": result.audit_id,
            "record": _detail_payload(result.row),
            "warnings": prepared.warnings,
        },
        message="新增成功",
    )


# ---------------------------------------------------------------------------
# PATCH /api/genes/known/write/{clone_id} — 更新
# ---------------------------------------------------------------------------
# NOTE: two equivalent routes for the update operation.
# - PATCH is the canonical HTTP method (used by our own scripts / direct API
#   access);
# - POST /update/{clone_id} is the public-proxy-safe alias: the campus network
#   edge in front of wheatomics.sdau.edu.cn drops PATCH requests (curl gets
#   "Empty reply from server") while POST/PUT pass through. Keeping both means
#   external maintainers are never blocked by that middlebox.
@router.patch(
    "/{clone_id}",
    dependencies=[Depends(enforce_known_gene_body_limit)],
    responses=_WRITE_ERROR_RESPONSES,
    openapi_extra=_PATCH_REQUEST_BODY,
)
@router.post(
    "/update/{clone_id}",
    dependencies=[Depends(enforce_known_gene_body_limit)],
    responses=_WRITE_ERROR_RESPONSES,
    openapi_extra=_PATCH_REQUEST_BODY,
)
async def update_known_gene(
    clone_id: int,
    request: Request,
    ctx: AuthContext = Depends(require_known_gene_scope("write")),
) -> dict:
    """按 clone_id 更新 KnownGene（需要 write scope；只改传入字段；支持 dry_run）。

    功能:
        只更新 body 中出现的字段（白名单同新增，不含 clone_id）；源字段变化时
        重算派生列（gene_species→species_primary、chrom_pos→chromosome、
        publication_years→publication_year）。更新前 ``SELECT ... FOR UPDATE``
        锁行；clone_id 不存在 → 404。审计写 before/after 完整行 +
        真实变化列 ``changed_fields``，与 UPDATE 同一事务。
        若传入值与库中完全一致，不执行 UPDATE、不写审计（changed_fields=[]）。

    参数:
        - ``clone_id``: 路径参数，内部自增主键（详情页 URL 的 id）；
        - ``dry_run``: true 时返回合并后的记录与 changed_fields，不落库；
        - ``fields``: 要更新的字段对象（也可直接把字段放顶层）。

    用法:
        PATCH /api/genes/known/write/{clone_id}

    案例:
        请求:
          curl -X PATCH "http://localhost:8000/api/genes/known/write/1626" \\
            -H "Authorization: Bearer $KNOWN_GENE_API_KEY" \\
            -H "Content-Type: application/json" \\
            -d '{"fields": {"gene_phenotype": "Drought tolerance; Salt tolerance",
                            "publication_years": "2007; 2024"}}'

        响应:
          {"success": true, "message": "更新成功", "data": {
            "dry_run": false, "clone_id": 1626, "audit_id": 2,
            "changed_fields": ["gene_phenotype", "publication_year", "publication_years"],
            "record": {<detail 形状>}, "warnings": []}}
    """

    payload = await read_json_object(request)
    fields, dry_run = _split_body(payload, ("fields", "gene"))

    with mysql_cursor(settings.DB_CLONED_GENE) as cursor:
        if dry_run:
            before_row = ingest.fetch_row(cursor, clone_id)
        else:
            before_row = ingest.fetch_row_for_update(cursor, clone_id)
        if not before_row:
            raise ResourceNotFound(f"KnownGene 不存在: clone_id={clone_id}")

        try:
            prepared = ingest.validate_update_payload(fields, before_row)
        except ingest.GeneWriteValidationError as exc:
            raise _http_validation_error(exc) from exc

        if dry_run:
            merged = {**before_row, **prepared.columns}
            return ok(
                {
                    "dry_run": True,
                    "clone_id": clone_id,
                    "changed_fields": ingest.changed_columns(before_row, merged),
                    "record": _detail_payload(merged),
                    "warnings": prepared.warnings,
                },
                message="dry-run：校验通过，未写入",
            )

        result = ingest.update_known_gene(
            cursor,
            clone_id,
            prepared.columns,
            actor=ctx,
            client_ip=ctx.client_ip,
        )

    if result.audit_id is None:
        message = "无字段变化，未写入"
    else:
        message = "更新成功"
    logger.info(
        "known_gene update ok: clone_id=%s changed=%s key_id=%s label=%s ip=%s",
        clone_id,
        ",".join(result.changed_fields) or "-",
        ctx.key_id,
        ctx.label,
        ctx.client_ip,
    )
    return ok(
        {
            "dry_run": False,
            "clone_id": result.clone_id,
            "audit_id": result.audit_id,
            "changed_fields": result.changed_fields,
            "record": _detail_payload(result.row),
            "warnings": prepared.warnings + result.warnings,
        },
        message=message,
    )


# ---------------------------------------------------------------------------
# POST /api/genes/known/write/bulk — 批量
# ---------------------------------------------------------------------------
@router.post(
    "/bulk",
    dependencies=[Depends(enforce_known_gene_body_limit)],
    responses=_WRITE_ERROR_RESPONSES,
    openapi_extra=_BULK_REQUEST_BODY,
)
async def bulk_upsert_known_genes(
    request: Request,
    ctx: AuthContext = Depends(require_known_gene_scope("write")),
) -> dict:
    """批量新增/更新 KnownGene（≤500 行/次，需要 write scope；默认 dry_run）。

    功能:
        逐行按"完整新增记录"校验；``mode=insert_only`` 时任一
        (gene_id, gene_name) 已存在则整批拒绝；``mode=upsert`` 时已存在则更新
        （审计 action=bulk_update），否则插入（action=bulk_create）。
        非 dry-run 时**全有或全无**：任一行校验失败 → 422 + 每行错误，不写库；
        全部通过后所有行在同一事务内写入并逐行写审计。
        dry_run（默认）返回每行 ``would_create`` / ``would_update`` / ``error``。

    参数:
        - ``rows``: 基因对象数组（每行字段规格同 POST /，必须完整）；
        - ``mode``: ``insert_only`` | ``upsert``（默认 upsert）；
        - ``dry_run``: 默认 true；确认预演结果后传 false 落库。

    用法:
        POST /api/genes/known/write/bulk

    案例:
        请求:
          curl -X POST "http://localhost:8000/api/genes/known/write/bulk" \\
            -H "Authorization: Bearer $KNOWN_GENE_API_KEY" \\
            -H "Content-Type: application/json" \\
            -d '{"mode": "upsert", "dry_run": true, "rows": [{...}, {...}]}'

        响应（dry-run）:
          {"success": true, "data": {"created": 1, "updated": 0, "errors": 0,
            "dry_run": true, "total": 1,
            "results": [{"row": 1, "status": "would_create", "clone_id": null}],
            "audit_ids": []}}

        落库响应 data: {"created": 0, "updated": 1, "errors": 0, "dry_run": false,
            "total": 1, "results": [{"row": 1, "status": "updated", "clone_id": 1626,
            "audit_id": 3, "changed_fields": ["gene_phenotype"]}], "audit_ids": [3]}
    """

    payload = await read_json_object(request)
    rows, mode, dry_run = _parse_bulk_payload(payload)
    prepared = ingest.prepare_bulk_rows(rows)

    with mysql_cursor(settings.DB_CLONED_GENE) as cursor:
        try:
            summary = ingest.run_bulk(
                cursor,
                prepared,
                mode=mode,
                dry_run=dry_run,
                actor=ctx,
                client_ip=ctx.client_ip,
            )
        except ingest.GeneWriteValidationError as exc:
            raise _http_validation_error(exc) from exc

    summary["total"] = len(rows)
    if dry_run:
        message = f"dry-run：{summary['created']} 行将新增，{summary['updated']} 行将更新，{summary['errors']} 行有错误"
    else:
        message = f"批量完成：新增 {summary['created']} 行，更新 {summary['updated']} 行"
    logger.info(
        "known_gene bulk ok: mode=%s dry_run=%s created=%s updated=%s errors=%s key_id=%s label=%s ip=%s",
        mode,
        dry_run,
        summary["created"],
        summary["updated"],
        summary["errors"],
        ctx.key_id,
        ctx.label,
        ctx.client_ip,
    )
    return ok(summary, message=message)


# ---------------------------------------------------------------------------
# GET /api/genes/known/write/changes — 审计查询
# ---------------------------------------------------------------------------
@router.get("/changes", responses=_WRITE_ERROR_RESPONSES)
def list_known_gene_changes(
    clone_id: Optional[int] = Query(None, description="只看某个 clone_id 的变更历史"),
    action: Optional[str] = Query(
        None,
        description="按动作过滤：create / update / delete / bulk_create / bulk_update",
    ),
    since: Optional[str] = Query(None, description="起始时间（YYYY-MM-DD 或 ISO 8601）"),
    limit: int = Query(50, ge=1, le=500, description="返回条数（默认 50，最大 500）"),
    offset: int = Query(0, ge=0, description="分页偏移"),
    include_snapshot: bool = Query(
        False,
        description="是否返回 before/after 完整行快照（含长文本，默认不返回）",
    ),
    ctx: AuthContext = Depends(require_known_gene_scope("admin")),
) -> dict:
    """查询 KnownGene 写操作审计日志（需要 admin scope）。

    功能:
        返回 ``known_gene_change_log`` 记录（按 id 倒序），含动作、clone_id、
        gene_id/gene_name、changed_fields、操作者 key label、client_ip、时间、
        reason。默认不返回 before/after 快照（可能很大），
        ``include_snapshot=true`` 时返回解析后的完整行 dict。

    用法:
        GET /api/genes/known/write/changes?limit=20&action=update
        Header: Authorization: Bearer kgw_xxx（需要 admin scope）

    案例:
        请求:
          curl "http://localhost:8000/api/genes/known/write/changes?clone_id=1626&limit=10" \\
            -H "Authorization: Bearer $KNOWN_GENE_ADMIN_KEY"

        响应:
          {"success": true, "data": {"total": 2, "limit": 10, "offset": 0,
            "records": [{"id": 2, "action": "update", "clone_id": 1626,
              "gene_id": "...", "gene_name": "...",
              "changed_fields": ["gene_phenotype", "publication_year"],
              "actor_key_id": 1, "actor_label": "maintainer-key",
              "client_ip": "127.0.0.1", "reason": null,
              "created_at": "2026-10-28T19:20:00"}]}}
    """

    with mysql_cursor(settings.DB_CLONED_GENE) as cursor:
        try:
            history = ingest.list_change_log(
                cursor,
                clone_id=clone_id,
                action=action,
                since=since,
                limit=limit,
                offset=offset,
                include_snapshot=include_snapshot,
            )
        except ingest.GeneWriteValidationError as exc:
            raise _http_validation_error(exc) from exc
    return ok(history)


# ---------------------------------------------------------------------------
# GET /api/genes/known/write/whoami — 当前 Key 信息
# ---------------------------------------------------------------------------
@router.get("/whoami", responses=_WRITE_ERROR_RESPONSES)
def known_gene_write_whoami(
    ctx: AuthContext = Depends(verify_known_gene_key),
) -> dict:
    """返回当前 API Key 的身份信息（任意有效 key 均可调用）。

    功能:
        用于维护者自查：key_id、label、scopes、expires_at、last_used_at
        （鉴权时已尽力更新 last_used_at）。响应**不含** key 本身或哈希。

    用法:
        GET /api/genes/known/write/whoami
        Header: Authorization: Bearer kgw_xxx

    案例:
        请求:
          curl "http://localhost:8000/api/genes/known/write/whoami" \\
            -H "Authorization: Bearer $KNOWN_GENE_API_KEY"

        响应:
          {"success": true, "data": {"key_id": 1, "label": "maintainer-key",
            "scopes": ["write"], "expires_at": "2027-10-28T00:00:00",
            "last_used_at": "2026-10-28T19:21:03"}}
    """

    info = get_key_info(ctx.key_id) or {}
    return ok(
        {
            "key_id": ctx.key_id,
            "label": info.get("label", ctx.label),
            "scopes": list(split_scopes(info.get("scopes", ",".join(ctx.scopes)))),
            "expires_at": _iso(info.get("expires_at", ctx.expires_at)),
            "last_used_at": _iso(info.get("last_used_at", ctx.last_used_at)),
        },
        message="ok",
    )
