"""eQTL Atlas routes.

Port of the legacy Flask eQTL app (``/var/www/eqtl/eqtl.py``) to the WheatOmics
FastAPI service. The legacy app queried the ``eqtl`` database's ``wheat`` table
(``SELECT * FROM wheat WHERE Geneid LIKE %s``) and served one FarmCPU Manhattan
plot per project (``static/image/{Project}_{gene}.FarmCPU.GWAS.png``).

The ``wheat`` table schema is discovered at query time via ``cursor.description``
(dynamic columns) rather than hard-coded — same defensive approach as
``app/api/routers/ppi.py`` — so the frontend renders whatever columns the table
actually exposes. The only two columns this module relies on are:

  * ``Geneid``   — search key (gene ID, ``Traes...``)
  * ``Project``  — used to attach a ``Project_url`` to each result row
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.exceptions import ResourceNotFound, ValidationFailure
from app.core.response import ok
from app.db.mysql import mysql_connection
from app.services.gene_id_versions import empty_hint, id_versions, variants

router = APIRouter(prefix="/eqtl", tags=["eQTL Atlas"])

#: Ordered project list — the legacy app iterates this exact order.
PROJECT_ORDER = [
    "PRJNA670223",
    "PRJNA795836",
    "PRJNA838764",
    "PRJNA912645",
    "CRA022107",
]

PROJECT_INFO = {
    "PRJNA670223": {
        "desc": "Ground tissue of 2-week-old plants ; Doi:10.1038/s41467-022-28453-y",
        "url": "https://www.nature.com/articles/s41467-022-28453-y#data-availability",
    },
    "PRJNA795836": {
        "desc": "Leaves at the three-leaf stage ; Doi:10.1093/plcell/koac248",
        "url": "https://academic.oup.com/plcell/article/34/11/4472/6663768#378211586",
    },
    "PRJNA838764": {
        "desc": "Roots at 14 days after germination ; Doi:10.1093/plphys/kiae270",
        "url": "https://academic.oup.com/plphys/article/196/1/47/7671041?login=true",
    },
    "PRJNA912645": {
        "desc": "The second or third seedling leaf ; Doi:10.1111/tpj.16248",
        "url": "https://onlinelibrary.wiley.com/doi/10.1111/tpj.16248",
    },
    "CRA022107": {
        "desc": " 2-week-old seedlings ; Doi:10.1038/s41467-025-66100-4",
        "url": "https://www.nature.com/articles/s41467-025-66100-4",
    },
}

#: Mirrors the legacy app's ``GENE_PATTERN``; rejects non-Traes paths early.
GENE_PATTERN = re.compile(r"^Traes[A-Za-z0-9_.]+$")


def _projects_for(gene: str) -> list[dict]:
    """Build the per-project photo list (with image URL only if the file exists)."""
    projects: list[dict] = []
    image_dir = settings.EQTL_IMAGE_DIR
    for project in PROJECT_ORDER:
        info = PROJECT_INFO[project]
        filename = f"{project}_{gene}.FarmCPU.GWAS.png"
        image_url = None
        if (image_dir / filename).is_file():
            image_url = f"/api/eqtl/image/{project}/{gene}"
        projects.append(
            {
                "project": project,
                "desc": info["desc"],
                "url": info["url"],
                "image": image_url,
            }
        )
    return projects


@router.get("/image/{project}/{gene}")
def manhattan_image(project: str, gene: str) -> FileResponse:
    """Serve the FarmCPU Manhattan plot for a gene in a project."""
    if project not in PROJECT_INFO:
        raise ValidationFailure(f"Unknown project: {project!r}")
    if not GENE_PATTERN.match(gene):
        raise ValidationFailure(f"Invalid gene ID: {gene!r}")
    # Images are named with the IWGSC v3 (03G) gene ID; accept a 01G/02G input
    # by resolving the same gene's other annotation versions.
    candidates = variants(gene, prefer=("v3", "v2", "v1"))
    for candidate in candidates:
        path = settings.EQTL_IMAGE_DIR / f"{project}_{candidate}.FarmCPU.GWAS.png"
        if path.is_file():
            return FileResponse(path, media_type="image/png")
    raise ResourceNotFound(
        f"No FarmCPU Manhattan plot for {gene} in {project} "
        f"(tried annotation versions: {', '.join(candidates)})"
    )


@router.get("/search")
def search_eqtl(
    gene: str = Query(..., min_length=1, description="Gene ID (Traes...) to search"),
) -> dict:
    """Query eQTL records by gene ID plus each project's FarmCPU Manhattan plot.

    Purpose:
        Fuzzy-match ``Geneid`` in the ``eqtl`` database's ``wheat`` table,
        return all matching records (column names discovered dynamically, see
        the module docstring) plus the Manhattan plot info of the 5 projects.

    Usage:
        GET /api/eqtl/search?gene=TraesCS1A03G0001700

    Response:
        {
          "success": true,
          "data": {
            "gene": "TraesCS1A03G0001700",
            "columns": ["Geneid", "Project", ...],
            "rows": [ {"Geneid": ..., "Project": ..., ...} ],
            "projects": [
              {"project": "PRJNA670223", "desc": "...", "url": "...", "image": "/api/eqtl/image/PRJNA670223/TraesCS1A03G0001700" | null}
            ]
          }
        }
    """

    gene = gene.strip()
    if not GENE_PATTERN.match(gene):
        raise ValidationFailure(
            f"Invalid gene ID: {gene!r}. eQTL Atlas genes follow the "
            "TraesCS1A03G0001700 (IWGSC RefSeq v2.1 / 03G) format."
        )

    # The eqtl.wheat table stores IWGSC v3 (03G) IDs; readers may paste the v1
    # (01G) or v2 (02G) spelling of the same gene, which used to return an
    # empty payload with no explanation. Look up every available version.
    info = id_versions(gene)
    lookup_ids = variants(gene, prefer=("v3", "v2", "v1"))
    placeholders = ",".join(["%s"] * len(lookup_ids))
    resolved_gene = info.get("v3") or info.get("v2") or info.get("v1") or gene

    with mysql_connection(settings.DB_EQTL) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT * FROM wheat WHERE Geneid IN ({placeholders})",
            tuple(lookup_ids),
        )
        rows = cursor.fetchall()
        columns = [d[0] for d in cursor.description] if cursor.description else []
        cursor.close()

    # Attach a Project_url to each row, mirroring the legacy app.
    for row in rows:
        row["Project_url"] = PROJECT_INFO.get(row.get("Project", ""), {}).get("url", "")

    hint = None
    if not rows:
        hint = empty_hint(
            "the eQTL Atlas",
            gene,
            "IWGSC RefSeq v3 (03G)",
            extra="Use the resolved 03G ID above; if it is also absent the gene "
                  "simply has no eQTL record in the five FarmCPU panels.",
        )

    return ok(
        {
            "gene": gene,
            "resolved_gene": resolved_gene,
            "id_versions": {
                key: info[key] for key in ("v1", "v2", "v3") if info.get(key)
            },
            "columns": columns,
            "rows": jsonable_encoder(rows),
            # Manhattan plots are stored per 03G ID, so the resolved ID is used.
            "projects": _projects_for(resolved_gene),
            "hint": hint,
        }
    )
