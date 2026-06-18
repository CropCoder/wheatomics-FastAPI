"""Application configuration for the refactored WheatOmics FastAPI service."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    APP_NAME: str = "WheatOmics API for Ai Agent - FastAPI"
    APP_VERSION: str = "2.0"
    API_PREFIX: str = "/api"
    DEBUG: bool = True

    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "wheatomics_user"
    DB_PASSWORD: str = "wheatomics115599"
    DB_CHARSET: str = "utf8mb4"

    DB_GENE_EXPRESSION: str = "gene_expression"
    DB_COEXPRESSION: str = "coexpressiondb"
    DB_PPI: str = "wheatPPIdb"
    DB_CLONED_GENE: str = "cloned_gene_db"
    DB_CONVERT_GENE_ID: str = "Convert_gene_id"
    DB_GENEFUNC: str = "Genefuncdb"
    DB_PREBLAST: str = "pre_blast"
    DB_SYMAP: str = "symapdb"
    DB_LITERATURE: str = "wheatomics_db"

    BLAST_DB_PATH: Path = Path("/var/www/html/getfasta/blastdb")
    FASTA_DB_PATH: Path = Path("/data/fasta")
    SNPRIMER_TMP_DIR: Path = Path("/var/www/html/snprimer/tmp")
    SNPRIMER_RESULT_DIR: Path = Path("/var/www/html/snprimer/result")
    SNPRIMER_PIPELINE: Path = Path("/var/www/html/snprimer/SNP_Primer_Pipeline/run_getkasp.py")
    SYMAP_RESULT_DIR: Path = Path("/var/www/html/symap/result")
    SYMAP_DEFAULT_BED: Path = Path("/var/www/html/symap/CS_CS_durum_emmer_urartu_tauschii.bed")
    NOVABROWSE_SERVICE_DIR: Path = Path("/var/www/novabrowse_service")
    NOVABROWSE_RESULT_BASE_URL: str = "/novabrowse_results"

    CGI_SUBMISSION_PASSWORD: str = Field(default="wheatomics")
    REQUEST_TIMEOUT_SECONDS: int = 120

    WEBHOOK_SECRET: str = "Zjw_Super_Secret_Token_2026"
    AUTO_PULL_SCRIPT: Path = Path("/var/www/FastAPI_backend_Port8000/auto_pull.sh")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
