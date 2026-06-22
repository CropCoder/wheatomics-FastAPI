import logging
import sys
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_primer_config
from .dependencies import get_settings, verify_api_key
from .routers import config, jobs, results, server


def configure_logging() -> None:
    """Configure structured logging for the application."""
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        stream=sys.stdout,
    )


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(
        title="PrimerServer API",
        description="REST API for PrimerServer primer design and specificity check.",
        version="2.1.0",
    )

    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if not origins:
        origins = ["http://localhost:5173", "http://localhost:3000"]

    # Only allow credentials when origins are explicitly set and not wildcard.
    allow_credentials = settings.cors_origins != "*" and origins != ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    app.include_router(config.router)
    app.include_router(server.router)
    # Write endpoints are already protected inside jobs.router.
    app.include_router(jobs.router)
    # Result and file endpoints must also respect the same optional API key.
    app.include_router(results.router, dependencies=[Depends(verify_api_key)])

    @app.get("/health")
    def health():
        config = get_primer_config()
        checks = {
            "config": config.path.exists(),
            "samtools": config.executable_available("samtools"),
            "primer3": config.executable_available("primer3"),
            "blastn": config.executable_available("blastn"),
            "makeblastdb": config.executable_available("makeblastdb"),
            "database_dir": bool(config.database_dir) and Path(config.database_dir).exists(),
            "workdir_base": settings.workdir_base.exists() or settings.workdir_base.parent.exists(),
        }
        healthy = all(checks.values())
        return {
            "status": "healthy" if healthy else "degraded",
            "checks": checks,
        }

    return app


app = create_app()
