import asyncio
import datetime
import logging
import platform
import shutil
from typing import Optional

from fastapi import APIRouter, Depends

from ..config import PrimerServerConfig, get_primer_config
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
