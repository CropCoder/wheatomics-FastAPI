"""Task-like endpoints for legacy external workflows."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.core.exceptions import ResourceNotFound, ValidationFailure
from app.core.response import ok
from app.schemas.tasks import PrimerDesignRequest
from app.services.command_runner import run_command
from app.services.files import make_job_dir, pack_directory, write_lines

router = APIRouter(prefix="/tasks", tags=["Tasks"])

@router.post("/primer-design")
def design_primers(payload: PrimerDesignRequest) -> dict:
    """运行 SNP 引物设计工作流。

    功能:
        提交 SNP 标记数据，运行 Polymarker 引物设计流水线。
        支持 CAPS 和 KASP 两种引物类型，可根据需求配置
        倍性、价格、Tm 值、扩增子大小等参数。
        返回验证通过的标记列表、被拒绝的标记列表，以及
        生成的输出文件（CAPS_output、KASP_output 压缩包
        和多序列比对文件）。

    用法:
        POST /api/tasks/primer-design
        Body (JSON):
          - markers: SNP 标记行列表（必填），每行格式: "chr,pos,SEQ[/SNP]"
          - querydb: 参考基因组 BLAST 数据库名（必填）
          - ploidy: 倍性，如 "allohexaploid"
          - price: 价格等级
          - caps: 是否运行 CAPS 引物设计（true/false）
          - kasp: 是否运行 KASP 引物设计（true/false）
          - tm: Tm 值
          - size: 扩增子大小范围，如 "100 300"
          - pick: 引物挑选策略

    案例:
        请求:
          curl -X POST "http://localhost:8000/api/tasks/primer-design" \\
            -H "Content-Type: application/json" \\
            -d '{
              "markers": ["chr5A,587123456,ATGCNNN[A/G]TGCANNN"],
              "querydb": "Chinese_Spring_genome",
              "ploidy": "allohexaploid",
              "price": "3",
              "caps": true,
              "kasp": true,
              "tm": "60",
              "size": "100 300",
              "pick": "1"
            }'

        响应:
          {
            "success": true,
            "data": {
              "job_dir": "/tmp/snprimer/abc123",
              "accepted_markers": ["chr5A,587123456,ATGCNNN[A/G]TGCANNN"],
              "rejected_markers": [],
              "artifacts": [
                { "file_name": "CAPS_output.tar.gz", "path": "/tmp/snprimer/abc123/CAPS_output.tar.gz" },
                { "file_name": "KASP_output.tar.gz", "path": "/tmp/snprimer/abc123/KASP_output.tar.gz" },
                { "file_name": "All_alignment_raw.fa", "path": "/tmp/snprimer/abc123/All_alignment_raw.fa" }
              ]
            }
          }
    """

    if not settings.SNPRIMER_PIPELINE.exists():
        raise ResourceNotFound(f"Primer pipeline not found: {settings.SNPRIMER_PIPELINE}")
    genome_db = settings.BLAST_DB_PATH / payload.querydb
    if not genome_db.exists():
        raise ResourceNotFound(f"Genome BLAST database not found: {genome_db}")
    if not payload.markers:
        raise ValidationFailure("markers are required")

    valid_markers: list[str] = []
    rejected_markers: list[str] = []
    for marker in payload.markers:
        fields = marker.split(",")
        sequence = fields[2].upper() if len(fields) == 3 else ""
        if (
            len(fields) == 3
            and sequence.count("[") == 1
            and sequence.count("]") == 1
            and sequence.count("/") == 1
            and sum(sequence.count(base) for base in ["A", "T", "C", "G", "N"]) == len(sequence) - 3
        ):
            valid_markers.append(marker)
        else:
            rejected_markers.append(marker)

    if not valid_markers:
        raise ValidationFailure("No valid marker lines were provided")

    job_dir = make_job_dir(settings.SNPRIMER_TMP_DIR, "snprimer")
    marker_file = job_dir / "for_polymarker.csv"
    write_lines(marker_file, valid_markers)

    command = [
        str(settings.SNPRIMER_PIPELINE),
        marker_file.name,
        payload.ploidy,
        payload.price,
        "1" if payload.caps else "0",
        "1" if payload.kasp else "0",
        "1",
        payload.tm,
        payload.size.split()[0],
        payload.pick,
        str(genome_db),
    ]
    run_command(command, cwd=job_dir)

    artifacts: list[TaskArtifact] = []
    for result_subdir_name in ["CAPS_output", "KASP_output"]:
        result_subdir = job_dir / result_subdir_name
        if result_subdir.exists():
            archive = pack_directory(result_subdir, job_dir / result_subdir_name)
            artifacts.append(TaskArtifact(file_name=archive.name, path=str(archive)))

    alignment_file = job_dir / "All_alignment_raw.fa"
    if alignment_file.exists():
        artifacts.append(TaskArtifact(file_name=alignment_file.name, path=str(alignment_file)))

    return ok(
        {
            "job_dir": str(job_dir),
            "accepted_markers": valid_markers,
            "rejected_markers": rejected_markers,
            "artifacts": [artifact.model_dump() for artifact in artifacts],
        }
    )
