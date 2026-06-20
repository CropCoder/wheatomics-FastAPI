"""Task-like endpoints for legacy external workflows — PrimerServer replica."""

from __future__ import annotations

from pathlib import Path

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

router = APIRouter(prefix="/tasks", tags=["SNP Marker Design"])


# ──────────────────────────────────────────────
#  GET /api/tasks/primer-databases
# ──────────────────────────────────────────────

@router.get("/primer-databases")
def get_primer_databases(
    category: str = Query("all", regex="^(all|genome|gene)$"),
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


# ──────────────────────────────────────────────
#  POST /api/tasks/primer-design
# ──────────────────────────────────────────────

@router.post("/primer-design")
def design_primers(payload: PrimerDesignRequest) -> dict:
    """设计 SNP 引物并进行特异性检查。

    功能:
        根据输入 SNP 标记数据，完成以下全流程:
        1. 标记验证与格式化
        2. BLAST 参考基因组提取侧翼序列
        3. Primer3 引物设计（CAPS / KASP）
        4. 多数据库特异性检查（BLAST → Tm 计算 → 产物筛选）
        5. 返回结构化的引物分组结果（含产物号、Tm、3'端差异）

    对标 PrimerServer 网页版:
        对应 https://github.com/billzt/PrimerServer 的完整设计+检查流程。

    用法:
        POST /api/tasks/primer-design
        Body (JSON):
          - markers:      [必填] 标记行列表，格式 "chr,pos,SEQUENCE[/SNP]"
          - template:     [必填] 参考基因组数据库名
          - checking_dbs: [可选] 特异性检查数据库名列表，默认 ["primer_Chinese_Spring1.0.genome"]

          - product_size_min / product_size_max: 产物大小范围，默认 100-1000
          - primer_num_retain: 每个标记保留的候选引物数，默认 10
          - caps / kasp: 是否生成 CAPS / KASP 引物，默认 true
          - ploidy: 倍性，默认 "allohexaploid"
          - price: 价格等级，默认 "3"
          - primer_tm: 目标 Tm 值，默认 "60"
          - pick: 引物挑选策略，默认 "1"

          - blast_e_value:   BLAST e-value 阈值，默认 30000
          - blast_word_size: BLAST word size，默认 7
          - blast_identity:  BLAST 最低序列相似度，默认 60
          - blast_max_hsps:  BLAST 最大 HSP 数，默认 500

          - checking_size_start / checking_size_stop: 产物大小筛选范围，默认 50-5000
          - min_tm_diff: Tm 偏差阈值，默认 20
          - max_report_amplicon: 每个引物每组最多报道的产物数，默认 50
          - use_3end_mismatch: 是否启用 3' 端错配过滤，默认 false

          - primer_conc_nm: 引物浓度 (nM)，默认 100
          - conc_na_mm / conc_k_mm / conc_tris_mm: 离子浓度
          - conc_mg_mm / conc_dntp_mm: Mg2+ 和 dNTP 浓度

          - num_cpu: CPU 数，默认 4

    案例:
        curl -X POST "http://localhost:8000/api/tasks/primer-design" \\
          -H "Content-Type: application/json" \\
          -d '{
            "markers": ["chr5A,587123456,ATGCNNN[A/G]TGCANNN"],
            "template": "primer_Chinese_Spring1.0.genome",
            "checking_dbs": ["primer_Chinese_Spring1.0.genome"],
            "product_size_min": 100,
            "product_size_max": 1000,
            "blast_identity": 60,
            "num_cpu": 4
          }'

        响应:
        {
          "success": true,
          "data": {
            "job_dir": "/tmp/snprimer/abc123",
            "status": "completed",
            "accepted_markers": ["chr5A,587123456,ATGCNNN[A/G]TGCANNN"],
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
            "artifacts": [
              { "file_name": "PrimerServerOutput/specificity.check.result.txt",
                "path": "/tmp/snprimer/abc123/PrimerServerOutput/..." }
            ]
          }
        }
    """
    if not payload.markers:
        raise ValidationFailure("markers are required")

    # Validate required DB exists
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


# ──────────────────────────────────────────────
#  POST /api/tasks/primer-check
# ──────────────────────────────────────────────

@router.post("/primer-check")
def check_primer_specificity(payload: PrimerCheckRequest) -> dict:
    """对已有引物进行特异性检查（不进行引物设计）。

    功能:
        输入已经设计好的引物序列组，在多数据库中进行
        BLAST 对比 → Tm 计算 → 产物大小筛选 → 3' 端错配分析，
        返回每个引物组在各数据库中的可能产物数及相关信息。

    对标 PrimerServer 网页版:
        对应 "Directly checking specificity" 模式。

    用法:
        POST /api/tasks/primer-check
        Body (JSON):
          - primers:       [必填] 引物组行，格式 "ID [Rank] Seq1 Seq2 [Seq3...]"
          - checking_dbs:  [必填] 特异性检查数据库名列表
          - (其他参数同 primer-design)

    案例:
        curl -X POST "http://localhost:8000/api/tasks/primer-check" \\
          -H "Content-Type: application/json" \\
          -d '{
            "primers": ["my_gene 1 ACTG ACTG"],
            "checking_dbs": ["primer_Chinese_Spring1.0.genome"],
            "checking_size_start": 50,
            "checking_size_stop": 5000,
            "min_tm_diff": 20,
            "num_cpu": 4
          }'

        响应:
        {
          "success": true,
          "data": {
            "job_dir": "...",
            "status": "completed",
            "groups": [...],
            "artifacts": [...]
          }
        }
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


# ──────────────────────────────────────────────
#  GET /api/tasks/primer-result/{job_id}
# ──────────────────────────────────────────────

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
    # Search in both snprimer and snprimer_check directories
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
