"""Optional API key guard for PrimerServer2 endpoints."""

import secrets
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request

from app.core.config import settings


# Re-export settings so routers can keep their original Depends signatures.
class PrimerServer2Settings:
    """Thin wrapper exposing PrimerServer2 settings to keep router code unchanged."""

    def __init__(self):
        self.config_path = settings.PRIMERSERVER2_CONFIG_PATH
        self.workdir_base = settings.PRIMERSERVER2_WORKDIR_BASE
        self.api_key: Optional[str] = settings.PRIMERSERVER2_API_KEY
        self.cors_origins = settings.PRIMERSERVER2_CORS_ORIGINS
        self.job_timeout = settings.PRIMERSERVER2_JOB_TIMEOUT
        self.max_job_age_days = settings.PRIMERSERVER2_MAX_JOB_AGE_DAYS
        self.max_jobs_on_disk = settings.PRIMERSERVER2_MAX_JOBS_ON_DISK
        self.max_concurrent_jobs = settings.PRIMERSERVER2_MAX_CONCURRENT_JOBS


def get_settings() -> PrimerServer2Settings:
    return PrimerServer2Settings()


get_primerserver2_settings = get_settings


def get_app_settings() -> PrimerServer2Settings:
    return get_settings()


def verify_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    ps2_settings: PrimerServer2Settings = Depends(get_app_settings),
):
    """Optional API key guard.

    If PRIMERSERVER2_API_KEY is set, requests must include matching X-API-Key header.
    If it is not set, all requests are allowed (default open mode).
    """
    if not ps2_settings.api_key:
        return
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    if not secrets.compare_digest(x_api_key, ps2_settings.api_key):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key
