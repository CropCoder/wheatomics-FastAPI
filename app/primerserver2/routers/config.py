from fastapi import APIRouter, Depends

from ..config import PrimerServerConfig, get_primer_config
from app.core.config import settings
from pathlib import Path
from ..models import ConfigResponse, DatabaseGroup, DatabasesResponse

router = APIRouter(prefix="", tags=["PrimerServer2"])


@router.get(
    "/config",
    response_model=ConfigResponse,
    summary="Get public server configuration",
    description="Returns input limits and system flags (CPU count, cleanup policy, etc.).",
)
def get_config_endpoint(config: PrimerServerConfig = Depends(get_primer_config)):
    return config.to_public_dict()


@router.get(
    "/databases",
    response_model=DatabasesResponse,
    summary="List available specificity-check databases",
    description="Returns database groups with file names and human-readable aliases. "
                "Use the file names in the `selected-databases` field when submitting jobs.",
)
def get_databases(config: PrimerServerConfig = Depends(get_primer_config)):
    groups = []
    # .fai 文件可能在 database_dir 或 BLAST_DB_PATH 下
    fai_dirs = [Path(config.database_dir), settings.BLAST_DB_PATH]
    for name, databases in config.databases().items():
        examples: dict[str, list[str]] = {}
        for db_file in databases:
            seq_ids: list[str] = []
            for d in fai_dirs:
                fai_path = d / f"{db_file}.fai"
                try:
                    with open(fai_path) as f:
                        for _ in range(3):
                            line = f.readline()
                            if not line:
                                break
                            seq_id = line.split("\t")[0].strip()
                            if seq_id:
                                seq_ids.append(seq_id)
                except (FileNotFoundError, OSError):
                    continue
                if seq_ids:
                    break  # 找到就跳过其他目录
            examples[db_file] = seq_ids
        groups.append(DatabaseGroup(name=name, databases=databases, examples=examples))
    return DatabasesResponse(groups=groups)
