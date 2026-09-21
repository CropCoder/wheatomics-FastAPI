import asyncio
import datetime
import logging
import platform
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends

from app.core.config import settings as wheatomics_settings

from ..config import PrimerServerConfig, get_primer_config
from ..dependencies import PrimerServer2Settings, get_app_settings
from ..models import ServerInfoResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["PrimerServer2"])


async def _run_cmd(*cmd: str, timeout: float = 5.0) -> str:
    """Run a command and return stripped stdout."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode("utf-8", errors="ignore").strip()
    except asyncio.TimeoutError:
        logger.warning("Command timed out: %s", " ".join(cmd))
        return ""
    except FileNotFoundError:
        logger.warning("Command not found: %s", cmd[0] if cmd else "")
        return ""
    except Exception as exc:
        logger.warning("Failed to run command %s: %s", " ".join(cmd), exc)
        return ""


@router.get(
    "/server-info",
    response_model=ServerInfoResponse,
    summary="Get server runtime information",
    description="Returns current time and versions of external tools (samtools, blastn, primer3). "
                "CPU and memory details are only included when showInfo is enabled in config.",
)
async def get_server_info(config: PrimerServerConfig = Depends(get_primer_config)):
    response = ServerInfoResponse(currentTime=datetime.datetime.now().isoformat())

    if config.show_info:
        response.cpuInfo = platform.processor() or platform.machine()
        # Memory info is platform dependent; skip detailed mem on macOS/non-Linux
        if shutil.which("free"):
            mem = await _run_cmd("free", "-h")
            response.memTotal = mem.splitlines()[1] if mem else None
        else:
            response.memTotal = None
        response.memFree = None

    if config.executable_available("samtools"):
        response.samtoolsVersion = await _run_cmd(config.samtools, "--version")
    if config.executable_available("blastn"):
        response.blastnVersion = await _run_cmd(config.blastn, "-version")
    if config.executable_available("primer3"):
        response.primer3Version = await _run_cmd(config.primer3, "-version")

    return response


@router.get(
    "/health",
    summary="Check that the external tools and directories are in place",
    description="Returns status=healthy only when every check passes, plus the individual "
                "booleans. Useful straight after a deploy — a missing primer3 or blastn, or a "
                "database dir that does not exist, is otherwise only visible as a failed job. "
                "Tool paths come from the PRIMERSERVER2_* settings.",
)
def get_health(
    config: PrimerServerConfig = Depends(get_primer_config),
    settings: PrimerServer2Settings = Depends(get_app_settings),
):
    checks = {
        "samtools": config.executable_available("samtools"),
        "primer3": config.executable_available("primer3"),
        "blastn": config.executable_available("blastn"),
        "makeblastdb": config.executable_available("makeblastdb"),
        "database_dir": Path(wheatomics_settings.BLAST_DB_PATH).exists(),
        "workdir_base": settings.workdir_base.exists() or settings.workdir_base.parent.exists(),
    }
    return {"status": "healthy" if all(checks.values()) else "degraded", "checks": checks}
