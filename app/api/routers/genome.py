"""Genome registry (基因组信息库) routes.

The authoritative store is ``wheatomics_db.genome_registry``, rebuilt from
platform facts by ``scripts/rebuild_genome_registry.py``:

- JBrowse 数据集目录
- Genefuncdb.Genefunc_registry（基因注释表 / DOI / 倍数性）
- getfasta blastdb（核酸库 / CDS/PEP 库 / .fai）
- blast.html（Web BLAST 前端分组）
- all_genomes.nal（getfasta 聚合库成员）
- synteny_mysql.genome_info / orthofinder_n.genome_type（比较基因组 / OrthoFinder 登记）

每条记录同时保留 ``aliases_json``（各模块中的命名）与 ``usage_json``
（网站各模块使用证据：表名 / 路径 / 接口），便于溯源追踪。
"""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.exceptions import ResourceNotFound, ValidationFailure
from app.core.response import ok
from app.db.mysql import mysql_cursor

router = APIRouter(tags=["Genome Registry"])

_TABLE = "genome_registry"
_DATASET_RE = re.compile(r"^[\w.\-]+$")

#: 列表接口返回的精简字段（详情接口返回全部）
_LIST_COLUMNS = (
    "dataset_id, display_name, species, common_name, sample_type, ploidy, subgenomes, "
    "cultivar_or_line, sample_id, jbrowse_dataset, assembly_accession, assembly_level, genome_size, "
    "chromosome_count, gene_count, te_content, doi, journal, "
    "publication_year, annotation_status, gene_table, "
    "getfasta_member, primerserver_fai, web_blast_group, gene_function_ui, "
    "synteny_entry, orthofinder_entry, visible, updated_at"
)
_JSON_COLUMNS = ("aliases_json", "usage_json")


def _ensure_dataset_name(dataset: str) -> str:
    if not _DATASET_RE.fullmatch(dataset):
        raise ValidationFailure(f"Invalid dataset_id: {dataset!r}")
    return dataset


def _decode_json(row: dict) -> dict:
    for col in _JSON_COLUMNS:
        value = row.get(col)
        if isinstance(value, (str, bytes)):
            try:
                row[col] = json.loads(value)
            except (ValueError, TypeError):
                pass
    return row


@router.get("/genomes/stats")
def genome_registry_stats() -> dict:
    """基因组信息库统计（按倍数性/注释状态/模块覆盖）。"""
    with mysql_cursor(settings.DB_LITERATURE) as cursor:
        cursor.execute(
            "SELECT ploidy, COUNT(*) AS n FROM genome_registry "
            "WHERE visible=1 GROUP BY ploidy ORDER BY n DESC"
        )
        by_ploidy = cursor.fetchall()
        cursor.execute(
            "SELECT annotation_status, COUNT(*) AS n FROM genome_registry "
            "WHERE visible=1 GROUP BY annotation_status"
        )
        by_annotation = cursor.fetchall()
        cursor.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(jbrowse_dataset IS NOT NULL) AS jbrowse, "
            "SUM(gene_table IS NOT NULL) AS gene_function, "
            "SUM(getfasta_member=1) AS getfasta, "
            "SUM(primerserver_fai=1) AS primerserver, "
            "SUM(web_blast_group=1) AS web_blast, "
            "SUM(synteny_entry=1) AS synteny, "
            "SUM(orthofinder_entry=1) AS orthofinder "
            "FROM genome_registry WHERE visible=1"
        )
        totals = cursor.fetchone()
    return ok(
        {
            "totals": totals,
            "by_ploidy": by_ploidy,
            "by_annotation_status": by_annotation,
        }
    )


@router.get("/genomes")
def list_genomes(
    ploidy: str | None = Query(None, description="按倍数性过滤，如 AABBDD / AABBRR"),
    annotation_status: str | None = Query(
        None, description="注释状态：none / pending / available"
    ),
    has_annotation: bool | None = Query(
        None, description="True=仅有注释；False=无注释/待补"
    ),
    q: str | None = Query(None, description="按 dataset_id/展示名/物种/品种模糊搜索"),
    include_hidden: bool = Query(False, description="是否包含 visible=0 的记录"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """列出基因组信息库记录（支持倍数性/注释状态/关键词过滤）。"""
    where: list[str] = []
    params: list[object] = []
    if ploidy:
        where.append("ploidy=%s")
        params.append(ploidy)
    if annotation_status:
        if annotation_status not in ("none", "pending", "available"):
            raise ValidationFailure(
                "annotation_status 只能是 none / pending / available"
            )
        where.append("annotation_status=%s")
        params.append(annotation_status)
    if has_annotation is True:
        where.append("annotation_status='available'")
    elif has_annotation is False:
        where.append("annotation_status<>'available'")
    if q:
        like = f"%{q}%"
        where.append(
            "(dataset_id LIKE %s OR display_name LIKE %s OR species LIKE %s "
            "OR cultivar_or_line LIKE %s)"
        )
        params.extend([like, like, like, like])
    if not include_hidden:
        where.append("visible=1")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    with mysql_cursor(settings.DB_LITERATURE) as cursor:
        cursor.execute(f"SELECT COUNT(*) AS n FROM {_TABLE} {where_sql}", params)
        total = cursor.fetchone()["n"]
        cursor.execute(
            f"SELECT {_LIST_COLUMNS} FROM {_TABLE} {where_sql} "
            "ORDER BY (ploidy IS NULL), ploidy, dataset_id LIMIT %s OFFSET %s",
            params + [limit, offset],
        )
        rows = cursor.fetchall()

    return ok(
        {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [_decode_json(dict(row)) for row in rows],
        }
    )


@router.get("/genomes/{dataset_id}")
def get_genome(dataset_id: str) -> dict:
    """单条基因组记录（含 aliases_json / usage_json 完整溯源信息）。"""
    dataset = _ensure_dataset_name(dataset_id)
    with mysql_cursor(settings.DB_LITERATURE) as cursor:
        cursor.execute(
            f"SELECT * FROM {_TABLE} WHERE dataset_id=%s", (dataset,)
        )
        row = cursor.fetchone()
    if not row:
        raise ResourceNotFound(f"Genome not found: {dataset}")
    return ok(_decode_json(dict(row)))
