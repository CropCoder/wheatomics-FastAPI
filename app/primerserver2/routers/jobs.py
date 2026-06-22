import datetime
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from ..config import PrimerServerConfig, get_primer_config
from ..dependencies import PrimerServer2Settings, get_primerserver2_settings, verify_api_key
from ..models import (
    CheckJobRequest,
    DesignJobRequest,
    JobResponse,
    JobResultResponse,
    JobStatus,
    ProgressResponse,
)
from ..services.pipeline import PipelineRunner
from ..services.storage import JobManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["PrimerServer2"], dependencies=[Depends(verify_api_key)])


def get_job_manager(settings: PrimerServer2Settings = Depends(get_primerserver2_settings)) -> JobManager:
    return JobManager.from_settings(settings)


def get_runner(
    config: PrimerServerConfig = Depends(get_primer_config),
    job_manager: JobManager = Depends(get_job_manager),
    settings: PrimerServer2Settings = Depends(get_primerserver2_settings),
) -> PipelineRunner:
    return PipelineRunner(config, job_manager, settings)


@router.post(
    "/jobs",
    response_model=JobResponse,
    summary="Submit a primer design & check job",
    description="Designs PCR primers with Primer3 and checks specificity against selected databases. "
                "Returns a jobId; poll GET /jobs/{job_id}/progress and GET /jobs/{job_id}/result.",
)
def create_job(
    background_tasks: BackgroundTasks,
    request: DesignJobRequest,
    config: PrimerServerConfig = Depends(get_primer_config),
    job_manager: JobManager = Depends(get_job_manager),
    runner: PipelineRunner = Depends(get_runner),
):
    # ---- 校验模板数据库 ----
    tmpl = request.selectTemplate
    if tmpl == "custom":
        if not request.customTemplateSequences:
            raise HTTPException(
                status_code=422,
                detail="selectTemplate='custom' 但未提供 customTemplateSequences (FASTA 格式)",
            )
    elif not config.database_exists(tmpl):
        avail = config.all_database_files()
        raise HTTPException(
            status_code=422,
            detail=(
                f"模板数据库 '{tmpl}' 不存在。可用数据库: {avail[:10]}... "
                f"注意: templateRegions 格式为每行一个 'TargetID TargetPos TargetLength [ProductSizeMin] [ProductSizeMax]'，"
                f"例如 'Chr3B 569382161 5017 150 800'，而不是 'geneID:start-end' 格式。"
            ),
        )

    # ---- 校验特异性检测数据库 ----
    for db_name in request.selectedDatabases:
        if db_name == "custom":
            if not request.customDbSequences:
                raise HTTPException(
                    status_code=422,
                    detail="已选择 'custom' 数据库但未提供 customDbSequences (FASTA 格式)",
                )
        elif not config.database_exists(db_name):
            avail = config.all_database_files()
            raise HTTPException(
                status_code=422,
                detail=f"特异性检测数据库 '{db_name}' 不存在。可用数据库: {avail}",
            )

    # ---- 创建任务 ----
    job_id = job_manager.create_job()

    if request.appType.value == "design":
        background_tasks.add_task(runner.run_design, job_id, request)
    elif request.appType.value == "check":
        raise HTTPException(
            status_code=400,
            detail="Use POST /api/jobs/check for specificity-check-only jobs",
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid appType")

    logger.info("Submitted design job %s", job_id)
    return JobResponse(
        jobId=job_id,
        status=JobStatus.PENDING,
        createdAt=datetime.datetime.now().isoformat(),
        message="Job accepted",
    )


@router.post(
    "/jobs/check",
    response_model=JobResponse,
    summary="Submit a specificity-check-only job",
    description="Checks the specificity of user-provided primer sequences against selected databases. "
                "Returns a jobId; poll GET /jobs/{job_id}/progress and GET /jobs/{job_id}/result.",
)
def create_check_job(
    background_tasks: BackgroundTasks,
    request: CheckJobRequest,
    job_manager: JobManager = Depends(get_job_manager),
    runner: PipelineRunner = Depends(get_runner),
):
    job_id = job_manager.create_job()
    background_tasks.add_task(runner.run_check, job_id, request)
    logger.info("Submitted check job %s", job_id)
    return JobResponse(
        jobId=job_id,
        status=JobStatus.PENDING,
        createdAt=datetime.datetime.now().isoformat(),
        message="Check job accepted",
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    summary="Get job status",
    description="Returns the current status and metadata of a submitted job.",
)
def get_job(
    job_id: str,
    job_manager: JobManager = Depends(get_job_manager),
):
    status = job_manager.get_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(
        jobId=status["jobId"],
        status=status["status"],
        createdAt=status["createdAt"],
        message=status.get("message"),
    )


@router.get(
    "/jobs/{job_id}/progress",
    response_model=ProgressResponse,
    summary="Get job progress",
    description="Returns the completion percentage and current pipeline stage.",
)
def get_progress(
    job_id: str,
    job_manager: JobManager = Depends(get_job_manager),
):
    status = job_manager.get_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found")
    progress = status.get("progress", {})
    return ProgressResponse(
        total=progress.get("total", 100),
        finished=progress.get("finished", 0),
        percent=progress.get("percent", 0),
        stage=progress.get("stage", "unknown"),
    )


@router.get(
    "/jobs/{job_id}/result",
    response_model=JobResultResponse,
    summary="Get job result",
    description="Returns the final result of a design or check job. Use job_type='design' or 'check'.",
)
def get_result(
    job_id: str,
    job_type: str = "design",
    job_manager: JobManager = Depends(get_job_manager),
    runner: PipelineRunner = Depends(get_runner),
):
    status = job_manager.get_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return runner.parse_result(job_id, job_type)


@router.delete(
    "/jobs/{job_id}",
    response_model=JobResponse,
    summary="Stop and delete a job",
    description="Terminates the running process and removes the job working directory.",
)
def delete_job(
    job_id: str,
    job_manager: JobManager = Depends(get_job_manager),
):
    status = job_manager.get_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found")
    job_manager.stop_process(job_id)
    job_manager.delete_job(job_id)
    logger.info("Deleted job %s", job_id)
    return JobResponse(
        jobId=job_id,
        status=JobStatus.STOPPED,
        createdAt=status.get("createdAt", ""),
        message="Job stopped and cleaned up",
    )


@router.post(
    "/jobs/cleanup",
    summary="Clean up old job directories",
    description="Manually trigger cleanup of expired job directories according to retention policy.",
)
def cleanup_jobs(
    job_manager: JobManager = Depends(get_job_manager),
):
    """Manually trigger cleanup of old job directories."""
    removed = job_manager.cleanup_old_jobs()
    logger.info("Cleanup removed %s job directories", removed)
    return {"removed": removed}
