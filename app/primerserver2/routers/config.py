from fastapi import APIRouter, Depends

from ..config import PrimerServerConfig, get_primer_config
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
    for name, databases in config.databases().items():
        groups.append(DatabaseGroup(name=name, databases=databases))
    return DatabasesResponse(groups=groups)
