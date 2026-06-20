"""PrimerServer router — primer design & specificity checking for AI agents."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.core.exceptions import ResourceNotFound, ValidationFailure
from app.core.response import ok
from app.schemas.tasks import PrimerCheckRequest, PrimerDesignRequest
from app.services.files import make_job_dir
from app.services.primer_server import (
    build_marker_input,
    build_primer_check_input,
    list_primer_databases,
    run_pipeline_design_check,
    run_specificity_check,
)

router = APIRouter(prefix="/tasks", tags=["PrimerServer"])


@router.get("/primer-databases")
def get_primer_databases(
    category: str = Query("all", pattern="^(all|genome|gene)$"),
) -> dict:
    """获取可用的引物设计参考基因组/基因数据库列表。

    功能:
        返回系统配置的所有参考基因组和基因数据库，包含
        数据库文件名、别名和分类（genome / gene）。
        供 primer-design 和 primer-check 接口选择使用。

    用法:
        GET /api/tasks/primer-databases?category=<all|genome|gene>

    案例:
        curl -X GET "http://localhost:8000/api/tasks/primer-databases"
        curl -X GET "http://localhost:8000/api/tasks/primer-databases?category=genome"

        响应:
        {
          "success": true,
          "data": {
            "total": 2,
            "category": "genome",
            "databases": [
              { "file_name": "primer_Chinese_Spring1.0.genome",
                "alias": "Chinese Spring genome v1.0",
                "category": "genome" },
              ...
            ]
          }
        }
    """
    cat = None if category == "all" else category
    dbs = list_primer_databases(cat)
    return ok({
        "total": len(dbs),
        "category": category,
        "databases": dbs,
    })


@router.post("/primer-design")
def design_primers(payload: PrimerDesignRequest) -> dict:
    """设计 SNP 引物并进行特异性检查。

    功能:
        根据输入 SNP 标记数据，完成以下全流程:
        1. 标记验证与格式化
        2. BLAST 参考基因组提取侧翼序列
        3. Primer3 引物设计（CAPS / KASP）
        4. 多数据库特异性检查（BLAST → Tm 计算 → 产物筛选）
        5. 返回结构化的引物分组结果

    对标 PrimerServer 网页版:
        对应 https://github.com/billzt/PrimerServer 的完整设计+检查流程。

    用法:
        POST /api/tasks/primer-design
        Body (JSON):
          - markers:      [必填] 标记行列表，格式 "chr,pos,SEQUENCE[/SNP]"
          - template:     [必填] 参考基因组数据库名
          - checking_dbs: [可选] 特异性检查数据库名列表

    案例:
        curl -X POST "http://localhost:8000/api/tasks/primer-design" \\
          -H "Content-Type: application/json" \\
          -d '{
            "markers": ["chr5A,587123456,ATGCNNN[A/G]TGCANNN"],
            "template": "primer_Chinese_Spring1.0.genome",
            "checking_dbs": ["primer_Chinese_Spring1.0.genome"],
            "product_size_min": 100,
            "product_size_max": 1000
          }'

        响应:
        {
          "success": true,
          "data": {
            "job_dir": "/tmp/snprimer/abc123",
            "status": "completed",
            "accepted_markers": [...],
            "rejected_markers": [],
            "groups": [
              {
                "site_id": "marker_1",
                "primer_rank": 0,
                "database": "primer_Chinese_Spring1.0.genome",
                "amplicon_count": 1,
                "primer_seqs": ["ATGCN...", "TGCAN..."],
                "is_unique": true,
                "amplicons": [...]
              }
            ],
            "artifacts": [...]
          }
        }
    """
    if not payload.markers:
        raise ValidationFailure("markers are required")

    genome_db = settings.BLAST_DB_PATH / payload.template
    if not genome_db.exists():
        raise ResourceNotFound(f"Template genome database not found: {payload.template}")

    job_dir = make_job_dir(settings.SNPRIMER_TMP_DIR, "snprimer")
    input_text = build_marker_input(payload.markers)

    try:
        result = run_pipeline_design_check(job_dir, input_text, payload.template, payload.checking_dbs, payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")

    return ok(result.model_dump())


@router.post("/primer-check")
def check_primer_specificity(payload: PrimerCheckRequest) -> dict:
    """对已有引物进行特异性检查（不进行引物设计）。

    功能:
        输入已经设计好的引物序列组，在多数据库中进行
        BLAST 对比 → Tm 计算 → 产物大小筛选 → 3' 端错配分析。

    对标 PrimerServer 网页版:
        对应 "Directly checking specificity" 模式。

    用法:
        POST /api/tasks/primer-check

    案例:
        curl -X POST "http://localhost:8000/api/tasks/primer-check" \\
          -H "Content-Type: application/json" \\
          -d '{
            "primers": ["my_gene 1 ACTG ACTG"],
            "checking_dbs": ["primer_Chinese_Spring1.0.genome"]
          }'

        响应: { "success": true, "data": { "job_dir": "...", "groups": [...], "artifacts": [...] } }
    """
    if not payload.primers:
        raise ValidationFailure("primers are required")
    if not payload.checking_dbs:
        raise ValidationFailure("at least one checking database is required")

    job_dir = make_job_dir(settings.SNPRIMER_TMP_DIR, "snprimer_check")
    input_text = build_primer_check_input(payload.primers)

    try:
        result = run_specificity_check(job_dir, input_text, payload.checking_dbs, payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Specificity check error: {e}")

    return ok(result.model_dump())


@router.get("/primer-result/{job_id}")
def get_primer_result(job_id: str) -> dict:
    """获取引物设计/检查作业的结果文件列表。

    功能:
        根据 job_id 返回指定作业目录下的所有输出文件列表，
        方便 agent 定位并下载结果文件。

    用法:
        GET /api/tasks/primer-result/{job_id}

    案例:
        curl -X GET "http://localhost:8000/api/tasks/primer-result/abc123"

        响应:
        {
          "success": true,
          "data": {
            "job_dir": "/tmp/snprimer/abc123",
            "exists": true,
            "artifacts": [
              { "file_name": "specificity.check.result.txt",
                "path": "/tmp/snprimer/abc123/PrimerServerOutput/..." },
              ...
            ]
          }
        }
    """
    for base in [settings.SNPRIMER_TMP_DIR]:
        job_dir = base / job_id
        if job_dir.exists():
            artifacts = []
            for path in job_dir.rglob("*"):
                if path.is_file() and path.stat().st_size > 0:
                    artifacts.append({
                        "file_name": str(path.relative_to(job_dir)),
                        "path": str(path),
                    })
            return ok({"job_dir": str(job_dir), "exists": True, "artifacts": artifacts})

    raise ResourceNotFound(f"Job result not found: {job_id}")
