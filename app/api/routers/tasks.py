"""Task-like endpoints for legacy external workflows."""

from __future__ import annotations

import sys

from fastapi import APIRouter

from app.core.config import settings
from app.core.exceptions import ResourceNotFound, ValidationFailure
from app.core.response import ok
from app.core.security import FIGURE_FORMATS, SYNTENY_SHADE_STYLES, SYNTENY_STYLE_VALUES
from app.schemas.tasks import PrimerDesignRequest, SyntenyFigureRequest, TaskArtifact
from app.services.command_runner import run_command
from app.services.files import make_job_dir, pack_directory, write_lines

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("/synteny-figure")
def render_synteny_figure(payload: SyntenyFigureRequest) -> dict:
    """渲染共线性（Synteny）图。

    功能:
        提交共线性数据（block 文件和 layout 文件），调用 jcvi.graphics.synteny
        工具渲染高质量的共线性图。支持自定义 DPI、输出格式（PNG/PDF/SVG）、
        字体、颜色样式、阴影样式、图像尺寸等参数。可选用默认 BED 文件
        或自定义 BED 内容。

    用法:
        POST /api/tasks/synteny-figure
        Body (JSON):
          - block: 共线性区块数据（行列表，必填）
          - layout: 布局配置数据（行列表，必填）
          - bed: 自定义 BED 内容（use_default_bed=false 时必填）
          - use_default_bed: 是否使用默认 BED 文件（默认 false）
          - format: 输出格式，如 "png" / "pdf" / "svg"
          - dpi: 图像 DPI，默认 300
          - font: 字体名称，默认 "Arial"
          - diverge: 颜色发散值
          - shadestyle: 阴影样式
          - style: 颜色样式
          - figsize: 图像尺寸，如 "10x8"
          - scalebar: 是否添加比例尺

    案例:
        请求:
          curl -X POST "http://localhost:8000/api/tasks/synteny-figure" \\
            -H "Content-Type: application/json" \\
            -d '{
              "block": ["chr1A chr1B 90.5", "chr2A chr2B 85.3"],
              "layout": ["chr1A,chr1B", "chr2A,chr2B"],
              "use_default_bed": true,
              "format": "png",
              "dpi": 300,
              "font": "Arial",
              "diverge": "0.5",
              "shadestyle": "light",
              "style": "dark",
              "figsize": "12x8"
            }'

        响应:
          {
            "success": true,
            "data": {
              "job_dir": "/tmp/synteny/abc123",
              "artifacts": [
                { "file_name": "input.block", "path": "/tmp/synteny/abc123/input.block" },
                { "file_name": "input.layout", "path": "/tmp/synteny/abc123/input.layout" },
                { "file_name": "output.png", "path": "/tmp/synteny/abc123/output.png" }
              ]
            }
          }
    """

    if payload.format not in FIGURE_FORMATS:
        raise ValidationFailure(f"Unsupported figure format: {payload.format}")
    if payload.style not in SYNTENY_STYLE_VALUES:
        raise ValidationFailure(f"Unsupported style: {payload.style}")
    if payload.shadestyle not in SYNTENY_SHADE_STYLES:
        raise ValidationFailure(f"Unsupported shade style: {payload.shadestyle}")
    if payload.use_default_bed and not settings.SYMAP_DEFAULT_BED.exists():
        raise ResourceNotFound(f"Default BED file not found: {settings.SYMAP_DEFAULT_BED}")
    if not payload.use_default_bed and not payload.bed:
        raise ValidationFailure("bed content is required when use_default_bed is false")

    job_dir = make_job_dir(settings.SYMAP_RESULT_DIR, "synteny")
    block_file = job_dir / "input.block"
    layout_file = job_dir / "input.layout"
    write_lines(block_file, payload.block)
    write_lines(layout_file, payload.layout)

    bed_file = settings.SYMAP_DEFAULT_BED
    if not payload.use_default_bed:
        bed_path = job_dir / "input.bed"
        write_lines(bed_path, payload.bed or [])
        bed_file = bed_path

    command = [
        sys.executable,
        "-m",
        "jcvi.graphics.synteny",
        str(block_file),
        str(bed_file),
        str(layout_file),
        f"--dpi={payload.dpi}",
        f"--format={payload.format}",
        f"--font={payload.font}",
        f"--diverge={payload.diverge}",
        f"--shadestyle={payload.shadestyle}",
        f"--style={payload.style}",
        f"--figsize={payload.figsize}",
    ]
    if payload.scalebar:
        command.append("--scalebar")

    run_command(command, cwd=job_dir)

    figure = next(job_dir.glob(f"*.{payload.format}"), None)
    if figure is None:
        raise ResourceNotFound("Synteny figure was not generated")

    artifacts = [
        TaskArtifact(file_name=block_file.name, path=str(block_file)),
        TaskArtifact(file_name=layout_file.name, path=str(layout_file)),
        TaskArtifact(file_name=figure.name, path=str(figure)),
    ]
    if not payload.use_default_bed:
        artifacts.append(TaskArtifact(file_name="input.bed", path=str(job_dir / "input.bed")))

    return ok({"job_dir": str(job_dir), "artifacts": [artifact.model_dump() for artifact in artifacts]})


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
