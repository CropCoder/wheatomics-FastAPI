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
    """List the available primer-design reference genome / gene databases.

    Purpose:
        Return all reference genomes and gene databases configured in the
        system, including database file name, alias and category
        (genome / gene). Used for choosing among the primer-design and
        primer-check endpoints.

    Usage:
        GET /api/tasks/primer-databases?category=<all|genome|gene>

    Example:
        curl -X GET "http://localhost:8000/api/tasks/primer-databases"
        curl -X GET "http://localhost:8000/api/tasks/primer-databases?category=genome"

        Response:
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
    """Design SNP primers and run specificity checks.

    Purpose:
        Starting from the input SNP marker data, run the full pipeline:
        1. Marker validation and formatting
        2. BLAST against the reference genome to extract flanking sequences
        3. Primer3 primer design (CAPS / KASP)
        4. Multi-database specificity checks (BLAST → Tm calculation → product-size filtering)
        5. Return structured primer groups

    Parity with the PrimerServer web version:
        Corresponds to the full design + check pipeline of
        https://github.com/billzt/PrimerServer.

    Usage:
        POST /api/tasks/primer-design
        Body (JSON):
          - markers:      [required] list of marker rows, format "chr,pos,SEQUENCE[/SNP]"
          - template:     [required] reference genome database name
          - checking_dbs: [optional] list of database names for specificity checking

    Example:
        curl -X POST "http://localhost:8000/api/tasks/primer-design" \\
          -H "Content-Type: application/json" \\
          -d '{
            "markers": ["chr5A,587123456,ATGCNNN[A/G]TGCANNN"],
            "template": "primer_Chinese_Spring1.0.genome",
            "checking_dbs": ["primer_Chinese_Spring1.0.genome"],
            "product_size_min": 100,
            "product_size_max": 1000
          }'

        Response:
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
    """Run specificity checks on existing primers (no primer design).

    Purpose:
        Given primer sequence sets that have already been designed, run
        BLAST against multiple databases → Tm calculation → product-size
        filtering → 3'-end mismatch analysis.

    Parity with the PrimerServer web version:
        Corresponds to the "Directly checking specificity" mode.

    Usage:
        POST /api/tasks/primer-check

    Example:
        curl -X POST "http://localhost:8000/api/tasks/primer-check" \\
          -H "Content-Type: application/json" \\
          -d '{
            "primers": ["my_gene 1 ACTG ACTG"],
            "checking_dbs": ["primer_Chinese_Spring1.0.genome"]
          }'

        Response: { "success": true, "data": { "job_dir": "...", "groups": [...], "artifacts": [...] } }
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
    """List the result files of a primer design/check job.

    Purpose:
        Return all output files in the given job directory for a job_id, so
        agents can locate and download the result files.

    Usage:
        GET /api/tasks/primer-result/{job_id}

    Example:
        curl -X GET "http://localhost:8000/api/tasks/primer-result/abc123"

        Response:
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
