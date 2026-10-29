"""KnownGene write API routes: API Key auth + create / update / bulk + audit query.

Mounting (main.py)::

    from app.api.routers import gene_write
    ... for router in [... gene_write]: app.include_router(router, prefix="/api")

Final paths (include_router already adds the ``/api`` prefix, so this file never writes ``/api``):

===============================  ======  ========================================
Path                             Method  Description
===============================  ======  ========================================
/api/genes/known/write           POST    Create one KnownGene (dry_run supported)
/api/genes/known/write/{clone_id}  PATCH   Update by clone_id (only supplied fields change, dry_run supported)
/api/genes/known/write/bulk      POST    Bulk create/update (<=500 rows, dry_run supported)
/api/genes/known/write/changes   GET     Audit-log query (requires admin scope)
/api/genes/known/write/whoami    GET     Current API Key info (any valid key)
===============================  ======  ========================================

Auth / rate limiting / request-body protection live in ``app/core/known_gene_auth.py``;
field specs, derivation, transactional writes and auditing live in
``app/services/known_gene_ingest.py``. Responses use the unified ``ok(...)`` envelope;
errors use 401/403/404/409/413/422/429/503 + a Chinese detail message.

Security design (acceptance points):
- validation / rate limiting happen in the dependency layer; all business functions use parameterized SQL (no string-concatenated values);
- every write and its audit record share **one transaction** (``with mysql_cursor(...)`` commits only on success);
- rows are locked with ``SELECT ... FOR UPDATE`` before update, avoiding concurrent overwrites;
- logs record only key_id / label / key_prefix / client_ip, never the raw key.
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
    400: {"description": "Request body is not valid JSON / malformed parameters"},
    401: {"description": "Missing or invalid API Key (not found / disabled / expired all return 401)"},
    403: {"description": "API Key scope insufficient, or the source IP is not allowlisted"},
    404: {"description": "clone_id does not exist"},
    409: {"description": "(gene_id, gene_name) already exists"},
    413: {"description": "Request body exceeds 2MB"},
    422: {"description": "Business field validation failed (detail.errors lists each field error)"},
    429: {"description": "Write requests per Key per minute exceeded"},
    503: {"description": "Auth table not initialized / database unavailable"},
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
                        "Recommended form {\"dry_run\": false, \"gene\": {...}}; "
                        "the gene fields may also be placed at the top level (bare object)."
                    ),
                    "properties": {
                        "dry_run": {"type": "boolean", "default": False},
                        "gene": {
                            "type": "object",
                            "additionalProperties": True,
                            "description": "Gene fields; see the field table in the docs on the GET /api/genes/known/write/whoami page",
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
                        "functional_category": "Biotic Stress",
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
                        "Recommended form {\"dry_run\": false, \"fields\": {...}}; "
                        "the fields to change may also be placed at the top level (bare object)."
                    ),
                    "properties": {
                        "dry_run": {"type": "boolean", "default": False},
                        "fields": {
                            "type": "object",
                            "additionalProperties": True,
                            "description": "Fields to update (same whitelist as create, excluding clone_id)",
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
                            "description": "insert_only: reject the whole batch if any (gene_id,gene_name) already exists; upsert: update it if it exists",
                        },
                        "dry_run": {
                            "type": "boolean",
                            "default": True,
                            "description": "Defaults to true (dry-run first); pass false explicitly to persist after confirming",
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
                            "functional_category": "Biotic Stress",
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
    """Business validation error -> 422 (detail keeps the per-item error messages + hints)."""

    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=exc.as_detail(),
    )


def _http_duplicate_error(exc: ingest.DuplicateGeneError) -> HTTPException:
    """Unique-key conflict -> 409."""

    detail = (
        f"KnownGene 已存在：gene_id={exc.gene_id!r}, gene_name={exc.gene_name!r}"
        + (f"（clone_id={exc.clone_id}）" if exc.clone_id else "")
        + "；如需修改请使用 PATCH /api/genes/known/write/{clone_id}"
    )
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _detail_payload(row: dict) -> dict:
    """DB row -> detail payload (reuses the read endpoint's ``_row_to_known_detail``; identical shape)."""

    return _row_to_known_detail(row).model_dump()


def _iso(value: object) -> Optional[str]:
    """date/datetime -> ISO string (used in audit and key-info responses)."""

    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value if value is not None else None


def _split_body(
    payload: dict[str, Any],
    nested_keys: tuple[str, ...],
    *,
    default_dry_run: bool = False,
) -> tuple[dict[str, Any], bool]:
    """Split the request body into (fields dict, dry_run).

    Two forms are accepted:
    1. Recommended: ``{"dry_run": false, "<nested_key>": {...}}``;
    2. Convenience: a bare field object (e.g. ``{"gene_id": "..."}``, no dry_run).
    The nested field name may be ``gene`` (create) or ``fields`` (update); see each
    endpoint's docstring.
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
    """Parse the bulk request body and return ``(rows, mode, dry_run)``."""

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
    """Create one KnownGene record (requires write scope; dry_run supported).

    Purpose:
        Validate and write one known-function gene record, automatically deriving
        ``species_primary`` (296 source-text mappings + scientific-name aliases,
        with a warning when falling back), ``chromosome`` (chr regex over chrom_pos)
        and ``publication_year`` (minimum of the multi-valued years); multi-valued
        ``paper_title`` / ``paper_doi`` / ``publication_years`` accept a list or a
        ``"; "``-separated string, are aligned positionally and stored with ``###``.
        A duplicate (gene_id, gene_name) -> 409. The main-table write and the audit
        record (``known_gene_change_log``, action=create, after_json=full row) share
        one transaction.

    Parameters:
        - ``dry_run``: when true, only validate/deduplicate and return the "record that would be written"; nothing is persisted;
        - ``gene``: gene field object (the fields may also be placed at the top level).
        Required: gene_id / gene_name / reference_genome_id / gene_species / chrom_pos /
        gene_phenotype / functional_category / research_strategy / key_result;
        and at least one of paper_doi and paper_title.
        Optional: protein_family / validation_method / cloning_method /
        cloning_method_description / function_description / author / author_mail /
        submission_date / publication_year / publication_years / paper_title /
        paper_doi; the derived columns species_primary / chromosome may be explicitly
        overridden (they are validated).
        Defaults: author='WheatOmics API', author_mail='shengweima@icloud.com',
        submission_date=today.

    Usage:
        POST /api/genes/known/write
        Header: Authorization: Bearer kgw_xxx (or X-API-Key: kgw_xxx)
        Body: {"dry_run": false, "gene": {...}}

    Example:
        Request:
          curl -X POST "http://localhost:8000/api/genes/known/write" \\
            -H "Authorization: Bearer $KNOWN_GENE_API_KEY" \\
            -H "Content-Type: application/json" \\
            -d '{"dry_run": true, "gene": {
                  "gene_id": "TraesCS7B03G0166400", "gene_name": "TaERF1-B",
                  "reference_genome_id": "TraesCS7B03G0166400",
                  "gene_species": "Triticum aestivum (bread wheat)",
                  "chrom_pos": "Refv1.0 chr7B:112.264-112.266Mb",
                  "gene_phenotype": "Drought tolerance",
                  "functional_category": "Biotic Stress",
                  "research_strategy": "Reverse genetics",
                  "key_result": "Overexpression improves drought tolerance.",
                  "paper_doi": "10.1007/s11103-007-9237-9"}}'

        Response:
          {"success": true, "message": "dry-run: validation passed, nothing written",
           "timestamp": "...", "data": {"dry_run": true,
             "record": {"gene_id": "...", "species_primary": "Triticum aestivum",
                        "chromosome": "7B", "publication_year": 2007, ...},
             "warnings": []}}

        Persisted response data: {"dry_run": false, "clone_id": 1626, "audit_id": 1,
                        "record": {<detail shape, same as /api/genes/known/{clone_id}>},
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
    """Update a KnownGene by clone_id (requires write scope; only supplied fields change; dry_run supported).

    Purpose:
        Update only the fields present in the body (same whitelist as create,
        excluding clone_id); when a source field changes, recompute the derived
        columns (gene_species->species_primary, chrom_pos->chromosome,
        publication_years->publication_year). Rows are locked with
        ``SELECT ... FOR UPDATE`` before update; a missing clone_id -> 404. The audit
        record stores the full before/after rows plus the columns that actually
        changed (``changed_fields``), in the same transaction as the UPDATE.
        If the supplied values are identical to the stored row, no UPDATE is run and
        no audit is written (changed_fields=[]).

    Parameters:
        - ``clone_id``: path parameter, the internal auto-increment primary key (the id in the detail-page URL);
        - ``dry_run``: when true, return the merged record and changed_fields without persisting;
        - ``fields``: object of fields to update (the fields may also be placed at the top level).

    Usage:
        PATCH /api/genes/known/write/{clone_id}

    Example:
        Request:
          curl -X PATCH "http://localhost:8000/api/genes/known/write/1626" \\
            -H "Authorization: Bearer $KNOWN_GENE_API_KEY" \\
            -H "Content-Type: application/json" \\
            -d '{"fields": {"gene_phenotype": "Drought tolerance; Salt tolerance",
                            "publication_years": "2007; 2024"}}'

        Response:
          {"success": true, "message": "updated successfully", "data": {
            "dry_run": false, "clone_id": 1626, "audit_id": 2,
            "changed_fields": ["gene_phenotype", "publication_year", "publication_years"],
            "record": {<detail shape>}, "warnings": []}}
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
    """Bulk create/update KnownGene (<=500 rows per call, requires write scope; dry_run by default).

    Purpose:
        Validate each row as a "complete create record"; with ``mode=insert_only``
        the whole batch is rejected if any (gene_id, gene_name) already exists;
        with ``mode=upsert`` existing rows are updated (audit action=bulk_update),
        otherwise inserted (action=bulk_create).
        When not a dry run it is **all or nothing**: any row failing validation ->
        422 + per-row errors, nothing is written; after all rows pass, every row is
        written in one transaction with an audit record per row.
        dry_run (the default) returns ``would_create`` / ``would_update`` / ``error``
        for each row.

    Parameters:
        - ``rows``: array of gene objects (the per-row field spec is the same as POST / and must be complete);
        - ``mode``: ``insert_only`` | ``upsert`` (default upsert);
        - ``dry_run``: defaults to true; pass false to persist after confirming the dry-run result.

    Usage:
        POST /api/genes/known/write/bulk

    Example:
        Request:
          curl -X POST "http://localhost:8000/api/genes/known/write/bulk" \\
            -H "Authorization: Bearer $KNOWN_GENE_API_KEY" \\
            -H "Content-Type: application/json" \\
            -d '{"mode": "upsert", "dry_run": true, "rows": [{...}, {...}]}'

        Response (dry-run):
          {"success": true, "data": {"created": 1, "updated": 0, "errors": 0,
            "dry_run": true, "total": 1,
            "results": [{"row": 1, "status": "would_create", "clone_id": null}],
            "audit_ids": []}}

        Persisted response data: {"created": 0, "updated": 1, "errors": 0, "dry_run": false,
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
    clone_id: Optional[int] = Query(None, description="Only show the change history of a given clone_id"),
    action: Optional[str] = Query(
        None,
        description="Filter by action: create / update / delete / bulk_create / bulk_update",
    ),
    since: Optional[str] = Query(None, description="Start time (YYYY-MM-DD or ISO 8601)"),
    limit: int = Query(50, ge=1, le=500, description="Number of rows to return (default 50, max 500)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    include_snapshot: bool = Query(
        False,
        description="Whether to return the full before/after row snapshots (includes long text; not returned by default)",
    ),
    ctx: AuthContext = Depends(require_known_gene_scope("admin")),
) -> dict:
    """Query the KnownGene write audit log (requires admin scope).

    Purpose:
        Return ``known_gene_change_log`` records (newest id first), including the
        action, clone_id, gene_id/gene_name, changed_fields, actor key label,
        client_ip, timestamp and reason. The before/after snapshots are not returned
        by default (they can be large); with ``include_snapshot=true`` the parsed
        full row dicts are returned.

    Usage:
        GET /api/genes/known/write/changes?limit=20&action=update
        Header: Authorization: Bearer kgw_xxx (requires admin scope)

    Example:
        Request:
          curl "http://localhost:8000/api/genes/known/write/changes?clone_id=1626&limit=10" \\
            -H "Authorization: Bearer $KNOWN_GENE_ADMIN_KEY"

        Response:
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
    """Return the identity info of the current API Key (any valid key may call it).

    Purpose:
        For maintainer self-checks: key_id, label, scopes, expires_at,
        last_used_at (auth refreshes last_used_at on a best-effort basis). The
        response does **not** include the key itself or its hash.

    Usage:
        GET /api/genes/known/write/whoami
        Header: Authorization: Bearer kgw_xxx

    Example:
        Request:
          curl "http://localhost:8000/api/genes/known/write/whoami" \\
            -H "Authorization: Bearer $KNOWN_GENE_API_KEY"

        Response:
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
