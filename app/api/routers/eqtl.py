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

from app.core.config import settings
from app.core.exceptions import ValidationFailure
from app.core.response import ok
from app.db.mysql import mysql_connection

router = APIRouter(prefix="/eqtl", tags=["eQTL Atlas"])

#: Image URL prefix under which the Manhattan plots are mounted (see main.py).
IMAGE_URL_PREFIX = "/eqtl-image"

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
            image_url = f"{IMAGE_URL_PREFIX}/{filename}"
        projects.append(
            {
                "project": project,
                "desc": info["desc"],
                "url": info["url"],
                "image": image_url,
            }
        )
    return projects


@router.get("/search")
def search_eqtl(
    gene: str = Query(..., min_length=1, description="Gene ID (Traes...) to search"),
) -> dict:
    """按基因 ID 查询 eQTL 记录及其各 project 的 FarmCPU 曼哈顿图。

    功能:
        在 ``eqtl`` 库的 ``wheat`` 表中按 ``Geneid`` 模糊匹配，返回命中的全部
        记录（列名动态发现，见模块 docstring）以及 5 个 project 的曼哈顿图信息。

    用法:
        GET /api/eqtl/search?gene=TraesCS5A02G391700

    响应:
        {
          "success": true,
          "data": {
            "gene": "TraesCS5A02G391700",
            "columns": ["Geneid", "Project", ...],
            "rows": [ {"Geneid": ..., "Project": ..., ...} ],
            "projects": [
              {"project": "PRJNA670223", "desc": "...", "url": "...", "image": "/eqtl-image/PRJNA670223_TraesCS5A02G391700.FarmCPU.GWAS.png" | null}
            ]
          }
        }
    """

    gene = gene.strip()
    if not GENE_PATTERN.match(gene):
        raise ValidationFailure(
            f"Invalid gene ID: {gene!r}. eQTL Atlas genes follow the "
            "TraesCS5A02G391700 (IWGSC) format."
        )

    with mysql_connection(settings.DB_EQTL) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM wheat WHERE Geneid LIKE %s",
            (f"%{gene}%",),
        )
        rows = cursor.fetchall()
        columns = [d[0] for d in cursor.description] if cursor.description else []
        cursor.close()

    # Attach a Project_url to each row, mirroring the legacy app.
    for row in rows:
        row["Project_url"] = PROJECT_INFO.get(row.get("Project", ""), {}).get("url", "")

    return ok(
        {
            "gene": gene,
            "columns": columns,
            "rows": jsonable_encoder(rows),
            "projects": _projects_for(gene),
        }
    )
