"""Sequence retrieval and precomputed BLAST routes."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.exceptions import ResourceNotFound, ValidationFailure
from app.core.response import ok
from app.core.security import PREBLAST_TABLES, ensure_allowed_table, ensure_gene_like, ensure_interval_like
from app.db.mysql import mysql_cursor
from app.schemas.sequence import SequenceBundle, SequenceRecord
from app.services.command_runner import run_command

router = APIRouter(tags=["Sequences"])


def _blastdbcmd(*args: str) -> str:
    """Run blastdbcmd and return trimmed output."""

    result = run_command(["/usr/bin/blastdbcmd", *args])
    return result.stdout.strip()


def _try_interval(database: Path, chrom: str, start: int, end: int) -> str:
    """Try fetching interval with case-tolerant chromosome name matching (chr / Chr prefix)."""

    from app.core.exceptions import ExternalToolFailure

    candidates = [chrom]
    if chrom.startswith("Chr"):
        candidates.append("chr" + chrom[3:])
    elif chrom.startswith("chr"):
        candidates.append("Chr" + chrom[3:])

    last_error: Exception | None = None
    for name in candidates:
        try:
            return _blastdbcmd(
                "-db", str(database),
                "-line_length", "110",
                "-entry", name,
                "-range", f"{start}-{end}",
                "-strand", "plus",
            )
        except ExternalToolFailure as e:
            last_error = e
            continue

    raise ValidationFailure(
        f"Chromosome {chrom!r} not found in database. "
        "Check the naming convention at "
        "https://wheatomics.sdau.edu.cn/doc/getsequence_search.txt"
    )


@router.get("/sequence/by-gene")
def sequence_by_gene(
    gene_id: str = Query(...),
    gene_db: str = Query("all_gene"),
    protein_db: str = Query("all_protein"),
) -> SequenceBundle:
    """根据基因 ID 获取基因和蛋白质序列（FASTA 格式）。

    功能:
        通过 blastdbcmd 工具，根据基因 ID 从本地 BLAST 数据库中提取
        对应的基因序列（CDS）和蛋白质序列。如果基因 ID 不以 .1 结尾，
        将自动追加 .1 后缀进行查找。

    用法:
        GET /api/sequence/by-gene?gene_id=<基因ID>&gene_db=<基因库>&protein_db=<蛋白库>
        - gene_id: 必填，如 TraesCS5A02G391700
        - gene_db: 可选，基因 BLAST 数据库名，默认 all_gene
        - protein_db: 可选，蛋白 BLAST 数据库名，默认 all_protein

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/sequence/by-gene?gene_id=TraesCS5A02G391700"

        响应:
          {
            "gene_id": "TraesCS5A02G391700",
            "gene_sequence": ">TraesCS5A02G391700.1\nATGGCG...",
            "protein_sequence": ">TraesCS5A02G391700.1\nMAGD..."
          }
    """

    gene_id = ensure_gene_like(gene_id)
    gene_entry = gene_id if gene_id.endswith(".1") else f"{gene_id}.1"

    bundle = SequenceBundle(gene_id=gene_id)
    try:
        bundle.gene_sequence = _blastdbcmd("-db", str(settings.BLAST_DB_PATH / gene_db), "-entry", gene_entry)
    except Exception:
        bundle.gene_sequence = None
    try:
        bundle.protein_sequence = _blastdbcmd("-db", str(settings.BLAST_DB_PATH / protein_db), "-entry", gene_entry)
    except Exception:
        bundle.protein_sequence = None

    if not bundle.gene_sequence and not bundle.protein_sequence:
        raise ResourceNotFound(f"No sequence found for {gene_id}")
    return bundle


@router.get("/sequence/by-interval")
def sequence_by_interval(
    region: str = Query(...,
        description="Genomic interval, e.g. Chr1A_Abo:200-500. "
                    "See https://wheatomics.sdau.edu.cn/doc/getsequence_search.txt for the full list of genome-specific chromosome naming conventions."),
    database: str = Query(...,
        description="BLAST database name. For genome-wide queries use the aggregated databases:\n"
                    "  - all_genomes   (genomic sequences, recommended for interval queries)\n"
                    "  - all_gene      (gene CDS)\n"
                    "  - all_protein   (protein)\n"
                    "See GET /api/blast/databases?program=blastn for the full list.")
) -> dict:
    """Get genomic FASTA sequence by chromosome interval.

    Chromosome naming follows genome-specific conventions.
    See the full reference at:
    https://wheatomics.sdau.edu.cn/doc/getsequence_search.txt

    Examples:
      - Hexaploid wheat (Abbondanza):     Chr1A_Abo:200-500
      - Hexaploid wheat (Chinese Spring): chr1A:200-500
      - Barley v3:                         chr1H_Barley3:200-500
      - Aegilops tauschii TA1675:          chr1D_Aegilops_tauschii_TA1675:200-500
      - Wild emmer:                        chr1A_Wild_emmer:200-500
    """

    ensure_interval_like(region)

    chrom = region.split(":")[0]
    interval = region.split(":")[1].replace("..", "-")
    start_text, end_text = interval.split("-")
    start, end = int(start_text), int(end_text)
    if end <= start or end - start > 5_000_000:
        raise ValidationFailure("Region length must be > 0 and <= 5,000,000 bp")

    fasta = _try_interval(settings.BLAST_DB_PATH / database, chrom, start, end)
    return ok({"region": region, "database": database, "fasta": fasta})


@router.get("/sequence/batch")
def batch_sequence(
    database: str = Query(...),
    ids: str = Query(..., alias="ID"),
) -> dict:
    """批量获取多个基因的 FASTA 序列。

    功能:
        一次性查询多个基因的序列，使用空格分隔基因 ID 列表，
        通过 blastdbcmd 批量提取。

    用法:
        GET /api/sequence/batch?ID=<基因1 基因2 ...>&database=<数据库名>
        - ID: 必填，空格分隔的基因 ID 列表
        - database: 必填，BLAST 数据库名

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/sequence/batch?ID=TraesCS5A02G391700+TraesCS5A02G123456&database=all_gene"

        响应:
          {
            "success": true,
            "data": {
              "database": "all_gene",
              "records": [
                { "sequence_id": "TraesCS5A02G391700", "fasta": ">TraesCS5A02G391700.1\n..." },
                { "sequence_id": "TraesCS5A02G123456", "fasta": ">TraesCS5A02G123456.1\n..." }
              ]
            }
          }
    """

    identifiers = [ensure_gene_like(token.strip()) for token in ids.split() if token.strip()]
    records: list[SequenceRecord] = []
    for identifier in identifiers:
        fasta = _blastdbcmd("-db", str(settings.BLAST_DB_PATH / database), "-entry", identifier)
        records.append(SequenceRecord(sequence_id=identifier, fasta=fasta))
    return ok({"database": database, "records": [record.model_dump() for record in records]})


@router.get("/preblast")
def get_preblast_result(
    gene_id: str = Query(..., alias="ID"),
    species_table: str = Query(..., alias="blastp_species"),
) -> dict:
    """获取预计算的 BLAST 结果 URL。

    功能:
        根据基因 ID 和物种表，返回预计算好的 BLAST 比对结果链接。
        数据来源于预计算的物种 BLAST 结果表。

    用法:
        GET /api/preblast?ID=<基因ID>&blastp_species=<物种表名>
        - ID: 必填，基因 ID
        - blastp_species: 必填，预 BLAST 物种表名

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/preblast?ID=TraesCS5A02G391700&blastp_species=rice"

        响应:
          {
            "success": true,
            "data": {
              "gene_id": "TraesCS5A02G391700",
              "species_table": "rice",
              "url": "http://example.com/blast_result/abc123.html"
            }
          }
    """

    gene_id = ensure_gene_like(gene_id)
    species_table = ensure_allowed_table(species_table, PREBLAST_TABLES, "preblast table")
    with mysql_cursor(settings.DB_PREBLAST) as cursor:
        cursor.execute(f"SELECT * FROM `{species_table}` WHERE Geneid = %s", (gene_id,))
        row = cursor.fetchone()

    if not row:
        raise ResourceNotFound(f"{gene_id} not found")

    return ok({"gene_id": gene_id, "species_table": species_table, "url": row.get("Url") or row.get("url") or row.get("ResultUrl")})


@router.get("/novabrowse")
def novabrowse_run(
    chrom: str = Query(...),
    start: int = Query(..., ge=1),
    end: int = Query(..., ge=1),
) -> dict:
    """启动 NovaBrowse 基因组可视化工作流。

    功能:
        根据染色体和起止位置，动态加载并运行 NovaBrowse 服务模块，
        生成基因组区间可视化结果页面。返回任务 ID 和结果页面的 URL。

    用法:
        GET /api/novabrowse?chrom=<染色体>&start=<起始>&end=<结束>
        - chrom: 必填，染色体名称
        - start: 必填，起始位置（>=1）
        - end: 必填，结束位置（>=1，必须大于 start）

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/novabrowse?chrom=chr5A&start=587000000&end=588000000"

        响应:
          {
            "success": true,
            "data": {
              "run_id": "abc123",
              "url": "http://wheatomics.sdau.edu.cn/novabrowse/abc123/output.html"
            }
          }
    """

    if end <= start:
        raise ValidationFailure("end must be greater than start")

    module_path = settings.NOVABROWSE_SERVICE_DIR / "run_novabrowse.py"
    if not module_path.exists():
        raise ResourceNotFound(f"NovaBrowse service module not found: {module_path}")

    spec = importlib.util.spec_from_file_location("run_novabrowse", module_path)
    if spec is None or spec.loader is None:
        raise ResourceNotFound("Unable to load NovaBrowse service module")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("run_novabrowse", module)
    spec.loader.exec_module(module)
    run_id = module.run(chrom, start, end)
    return ok({"run_id": run_id, "url": f"{settings.NOVABROWSE_RESULT_BASE_URL}/{run_id}/output.html"})
