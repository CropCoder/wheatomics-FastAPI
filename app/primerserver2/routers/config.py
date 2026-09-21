from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..config import PrimerServerConfig, blast_db_exists, get_primer_config
from app.core.config import settings
from ..models import ConfigResponse, DatabaseGroup, DatabasesResponse

from pathlib import Path
import re
from typing import Dict, Iterator, List, Set, Tuple


router = APIRouter(prefix="", tags=["PrimerServer2"])


#: Per-chromosome BLAST databases are redundant for primer specificity
#: checks (the whole-genome DB covers every chromosome) and would drown the
#: picker; drop them from the list.
_PER_CHROM_RE = re.compile(r"genome_Chr\d|chr\d+[A-Za-z]?$")


def _is_picker_database(name: str) -> bool:
    """True for the databases GET /databases exposes.

    Per-chromosome DBs are redundant (the whole-genome DB covers every
    chromosome) and the all_* aggregates give hits that cannot be attributed to
    one genome, so neither is offered. Shared by the picker and the per-database
    sequence list so the two cannot drift apart.
    """
    return not (_PER_CHROM_RE.search(name) or name.startswith("all_"))


#: Number of sequence IDs shown as examples for each database.
#: For a wheat genome this will normally produce examples such as:
#: 1A, 1B, 1D, 2A, 2B, ...
_MAX_FAI_EXAMPLES = 10


def _read_fai_examples(
    db_name: str,
    fai_dir: Path,
    max_examples: int = _MAX_FAI_EXAMPLES,
) -> List[str]:
    """
    Read sequence/chromosome IDs from <db_name>.fai.

    The first column of a FASTA .fai file is the sequence ID.

    For example:

        1A    594102056    ...
        1B    689851870    ...
        1D    509857785    ...

    The function returns only the sequence IDs, e.g.:

        ["1A", "1B", "1D", ...]

    No FASTA sequence itself is read.
    """

    db_name = str(db_name).strip()

    if not db_name:
        return []

    # Prevent accidental path traversal.
    if "/" in db_name or "\\" in db_name or ".." in db_name:
        return []

    fai_path = Path(fai_dir) / "{}.fai".format(db_name)

    if not fai_path.is_file():
        return []

    examples: List[str] = []
    seen: Set[str] = set()

    try:
        with fai_path.open(
            "r",
            encoding="utf-8",
            errors="replace",
        ) as fh:

            for line in fh:
                line = line.strip()

                if not line:
                    continue

                # .fai format:
                #
                # sequence_name
                # length
                # offset
                # linebases
                # linewidth
                #
                # The first column is the sequence/chromosome ID.
                seq_id = line.split("\t", 1)[0].strip()

                if not seq_id:
                    continue

                if seq_id in seen:
                    continue

                seen.add(seq_id)
                examples.append(seq_id)

                if len(examples) >= max_examples:
                    break

    except (FileNotFoundError, OSError):
        return []

    return examples


def _blast_db_groups(nuc_dbs: List[str]) -> List[DatabaseGroup]:
    """
    Group the shared BLAST nucleotide databases for the picker UI.

    The legacy primer_* FASTA databases — once listed in PrimerServer's
    config.ini, both since removed — are gone, so the specificity-check DB list
    now comes from the same BLAST library used by the BLAST search pages:

        settings.BLAST_DB_PATH

    Groups mirror the old genome/gene split.

    The all_* aggregated databases are intentionally excluded because they
    concatenate many genomes, so hits in them are not useful for selecting
    a specific genome database for primer specificity checking.

    In addition, for every selected database we read:

        <BLAST_DB_PATH>/<database_name>.fai

    and expose the first several sequence IDs through the API as examples.

    For wheat genomes this will typically produce values such as:

        1A, 1B, 1D, 2A, 2B, ...

    These examples are consumed by the PrimerServer2 frontend and displayed
    beside the database name in the Species / Template selector.
    """

    genome: List[str] = []
    gene: List[str] = []

    for name in nuc_dbs:

        name = str(name).strip()

        if not name:
            continue

        if not _is_picker_database(name):
            continue

        # ------------------------------------------------------------
        # Genome databases.
        # ------------------------------------------------------------
        if name.endswith(".genome"):
            genome.append(name)

        # ------------------------------------------------------------
        # Gene / transcript databases.
        # ------------------------------------------------------------
        elif (
            name.endswith(".cds")
            or "transcripts" in name
            or "mrna" in name
        ):
            gene.append(name)

    # ------------------------------------------------------------
    # Chinese Spring genomes go first.
    #
    # v2.1 is the platform default and ranks highest;
    # other Chinese Spring references come next;
    # everything else remains alphabetical.
    # ------------------------------------------------------------
    def _genome_sort_key(name: str) -> Tuple[int, str]:

        if name == "AABBDD_Chinese_Spring2.1.genome":
            return (0, name)

        if (
            "Chinese_Spring" in name
            or "CS-CAU" in name
            or "CS-IAAS" in name
        ):
            return (1, name)

        return (2, name)

    genome.sort(key=_genome_sort_key)
    gene.sort()

    # ------------------------------------------------------------
    # Build the two database groups.
    # ------------------------------------------------------------
    groups_spec = [
        ("genome", genome),
        ("gene", gene),
    ]

    # settings.BLAST_DB_PATH is expected to point to:
    #
    #     /var/www/html/getfasta/blastdb
    #
    # Convert it to Path explicitly so both str and Path configurations
    # are handled safely.
    fai_dir = Path(settings.BLAST_DB_PATH)

    groups: List[DatabaseGroup] = []

    for group_name, db_names in groups_spec:

        # Database selector mapping:
        #
        # {
        #     "database_name": "database_name"
        # }
        databases: Dict[str, str] = {
            name: name
            for name in db_names
        }

        # Sequence examples read from .fai files:
        #
        # {
        #     "AABBDD_Chinese_Spring2.1.genome":
        #         ["1A", "1B", "1D", ...]
        # }
        examples: Dict[str, List[str]] = {}

        for db_name in db_names:

            seq_ids = _read_fai_examples(
                db_name=db_name,
                fai_dir=fai_dir,
                max_examples=_MAX_FAI_EXAMPLES,
            )

            # Always create an examples entry.
            #
            # If the .fai file is missing, the value will simply be [].
            # This makes the API response structure consistent for every
            # database.
            examples[db_name] = seq_ids

        groups.append(
            DatabaseGroup(
                name=group_name,
                databases=databases,
                examples=examples,
            )
        )

    return groups


@router.get(
    "/config",
    response_model=ConfigResponse,
    summary="Get public server configuration",
    description=(
        "Returns input limits and system flags "
        "(CPU count, cleanup policy, etc.)."
    ),
)
def get_config_endpoint(
    config: PrimerServerConfig = Depends(get_primer_config),
):
    return config.to_public_dict()


@router.get(
    "/databases",
    response_model=DatabasesResponse,
    summary="List available specificity-check databases",
    description=(
        "Returns database groups (genome / gene) built from the shared "
        "BLAST library at settings.BLAST_DB_PATH, and the all_* "
        "aggregated databases are excluded because hits in multi-genome "
        "aggregates are not useful for genome-specific primer specificity "
        "checking. For each database, sequence IDs are read from the "
        "corresponding .fai file and returned through the examples field. "
        "Use the file names in the selected-databases field when submitting "
        "jobs."
    ),
)
def get_databases():
    from app.api.routers.blast import list_dbs

    # Obtain the same BLAST nucleotide database list already used by
    # the BLAST search functionality.
    nuc_dbs = list_dbs("blastn")

    return DatabasesResponse(
        groups=_blast_db_groups(nuc_dbs)
    )


def _iter_fai_id_length(fai_path: Path) -> Iterator[str]:
    """Yield 'sequence_id<TAB>length' for every sequence in a .fai.

    .fai columns are name, length, offset, linebases, linewidth; only the first
    two matter for picking a TargetID.
    """
    with fai_path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[0]:
                yield "{}\t{}\n".format(parts[0], parts[1])


@router.get(
    "/databases/{db_name}/sequences",
    summary="List every acceptable template ID in one database",
    description=(
        "Streams the full `sequence_id<TAB>length` list read from "
        "<BLAST_DB_PATH>/<db_name>.fai — the IDs that are acceptable as the "
        "TargetID in a design job. A genome database has ~21 rows; a gene "
        "database can exceed 100k rows and several MB, so the body is streamed "
        "as text/plain rather than wrapped in JSON. This is the same list the "
        "legacy PrimerServer offered through script/modal_help_list_ID.php.\n\n"
        "db_name must be one of the names from GET /databases."
    ),
    responses={
        404: {"description": "Not a picker database, or no .fai beside it"},
    },
)
def get_database_sequences(db_name: str):
    name = str(db_name).strip()

    # Reject separators before touching the filesystem: the name is about to
    # become a path component, and an allowlist check alone would leave the
    # resolution order to chance.
    if not name or "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=404, detail="未知数据库: {}".format(db_name))

    if not _is_picker_database(name) or not blast_db_exists(name):
        raise HTTPException(status_code=404, detail="未知数据库: {}".format(name))

    fai_path = Path(settings.BLAST_DB_PATH) / "{}.fai".format(name)
    if not fai_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="数据库 {} 没有 .fai 文件，无法列出序列 ID".format(name),
        )

    return StreamingResponse(
        _iter_fai_id_length(fai_path),
        media_type="text/plain; charset=utf-8",
    )
