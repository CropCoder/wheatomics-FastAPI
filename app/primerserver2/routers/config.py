from fastapi import APIRouter, Depends

from ..config import PrimerServerConfig, get_primer_config
from app.core.config import settings
from pathlib import Path
import re
from ..models import ConfigResponse, DatabaseGroup, DatabasesResponse

router = APIRouter(prefix="", tags=["PrimerServer2"])


#: Per-chromosome BLAST databases are redundant for primer specificity
#: checks (the whole-genome DB covers every chromosome) and would drown the
#: picker; drop them from the list.
_PER_CHROM_RE = re.compile(r"genome_Chr\d|chr\d+[A-Za-z]?$")


def _blast_db_groups(nuc_dbs: list[str]) -> list[DatabaseGroup]:
    """Group the shared BLAST nucleotide databases for the picker UI.

    The legacy config.ini primer_* FASTA databases were removed from the
    server, so the specificity-check DB list now comes from the same BLAST
    library used by the BLAST search pages (settings.BLAST_DB_PATH).
    Groups mirror the old genome/gene split plus the aggregated all_* DBs.
    """
    groups_spec = []  # (group_name, [db_names])
    aggregated, genome, gene = [], [], []
    for name in nuc_dbs:
        if _PER_CHROM_RE.search(name):
            continue
        if name.startswith("all_"):
            aggregated.append(name)
        elif name.endswith(".genome"):
            genome.append(name)
        elif name.endswith(".cds") or "transcripts" in name or "mrna" in name:
            gene.append(name)
    groups_spec = [
        ("All-in-one", aggregated),
        ("genome", genome),
        ("gene", gene),
    ]

    fai_dir = settings.BLAST_DB_PATH
    groups = []
    for group_name, db_names in groups_spec:
        databases = {n: n for n in db_names}
        examples: dict[str, list[str]] = {}
        for db_file in db_names:
            seq_ids: list[str] = []
            fai_path = fai_dir / f"{db_file}.fai"
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
            examples[db_file] = seq_ids
        groups.append(DatabaseGroup(name=group_name, databases=databases, examples=examples))
    return groups


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
    description="Returns database groups (All-in-one / genome / gene) built from the "
                "shared BLAST library at settings.BLAST_DB_PATH. The legacy config.ini "
                "primer_* FASTA databases are no longer used. Use the file names in the "
                "`selected-databases` field when submitting jobs.",
)
def get_databases(config: PrimerServerConfig = Depends(get_primer_config)):
    from app.api.routers.blast import list_dbs
    nuc_dbs = list_dbs("blastn")
    return DatabasesResponse(groups=_blast_db_groups(nuc_dbs))
