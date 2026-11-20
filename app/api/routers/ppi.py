"""PPI (protein-protein interaction) routes."""

from __future__ import annotations

import re
import time

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.exceptions import ValidationFailure
from app.core.response import ok
from app.core.security import PPI_TABLES, ensure_allowed_table, ensure_gene_like
from app.db.mysql import mysql_cursor
from app.schemas.network import PPIInteraction
from app.services.gene_id_versions import id_versions_many, variants
from app.services.legacy_parsers import normalize_text

ppi_router = APIRouter(tags=["Search Wheat Protein-Protein Interactions"])

#: The REGEXP scan over the ~3M-row PPI_result table takes seconds; a normalised
#: gene -> edge-index lookup makes it milliseconds. scripts/build_ppi_gene_index.py
#: builds ``wheatPPIdb.ppi_result_gene_index``; until it exists the endpoint
#: falls back to the (slow but correct) scan.
_PPI_INDEX_CACHE: dict[str, float | bool] = {"checked": 0.0, "available": False}



def _ppi_gene_index_available() -> bool:
    """Whether the normalised PPI gene index exists and has rows (cached 5 min)."""
    now = time.monotonic()
    if now - float(_PPI_INDEX_CACHE["checked"]) < 300:
        return bool(_PPI_INDEX_CACHE["available"])
    available = False
    try:
        with mysql_cursor(settings.DB_PPI) as cursor:
            cursor.execute("SELECT 1 FROM ppi_result_gene_index LIMIT 1")
            available = cursor.fetchone() is not None
    except Exception:  # noqa: BLE001 - fresh deployment before the build script
        available = False
    _PPI_INDEX_CACHE["checked"] = now
    _PPI_INDEX_CACHE["available"] = available
    return available


@ppi_router.get("/ppi/query")
def query_ppi(
    gene_ids: str = Query(...),
    table: str = Query("PPI_result"),
    min_score: float = Query(0.5),
) -> dict:
    """Query protein-protein interaction (PPI) relationships.

    Datasets:
        PPI_result
            plant.MAP CF-MS wheat complex map (McWhite et al. 2020).  Wheat
            UniProt IDs were mapped to IWGSC RefSeq v1.1; Score is the CF-MS
            confidence score.  Input transcript IDs should keep the ".1" suffix.
        PPI_poppin
            PoppIn rice PPI network (125,101 rice edges / 32,350 rice proteins)
            transferred to wheat A/B/D homoeologs.  Rice proteins were mapped
            by sequence homology (identity >= 60%, qcov >= 50%) plus Foldseek
            structural homology to recover missing copies; each rice edge was
            expanded to wheat copy pairs and duplicate pairs collapsed.  Input
            wheat gene IDs are IWGSC RefSeq v1.1 (02G) IDs without a transcript
            suffix.  supporting_edges is the number of rice edges supporting the
            wheat pair; identity1/identity2 are the best rice-to-wheat mapping
            identities; rice_pair is one underlying rice interaction.

    Usage:
        GET /api/ppi/query?gene_ids=<gene1,gene2>&table=<PPI_result|PPI_poppin>
        - gene_ids: required, comma-separated (max 200)
        - table: optional, PPI_result (default) or PPI_poppin
        - min_score: CF-MS threshold for PPI_result (0.5/0.2/0); ignored for
          PPI_poppin, which is a discrete rice-supported network
    """

    table = ensure_allowed_table(table, PPI_TABLES, "ppi table")
    genes = [ensure_gene_like(gene.strip()) for gene in gene_ids.split(",") if gene.strip()]
    if not genes:
        raise ValidationFailure("No valid gene IDs provided")
    if len(genes) > 200:
        raise ValidationFailure(f"Too many gene IDs ({len(genes)}); maximum is 200 per query")
    interactions: list[PPIInteraction] = []

    # Cross-version compatibility: these tables store IWGSC v2 (02G) IDs
    # (PPI_result keeps the transcript suffix). Resolve the caller's 01G/03G ID
    # to its other spellings so any annotation version works.
    info_map = id_versions_many(genes)
    base_forms: list[str] = []
    for gene in genes:
        for form in variants(gene, prefer=("v2", "v1", "v3")):
            base = re.sub(r"\.\d+$", "", form)
            if base and base not in base_forms:
                base_forms.append(base)
    version_map = {
        gene: {key: info[key] for key in ("v1", "v2", "v3") if info.get(key)}
        for gene, info in info_map.items()
    }

    # Batched: one query for all genes (previously N queries, one per gene).
    # REGEXP can't use an index, so we still scan once per table, but now it's
    # one scan matching any of the requested genes via alternation, not N scans.
    # WheatID columns store multiple IDs joined by '#' (e.g. "A.1#B.1#C.1"), so
    # anchor each gene with (^|#)...(#|$) instead of ^...$ to match one ID inside
    # the multi-value field without matching an unrelated prefix.
    if table == "PPI_poppin":
        # PoppIn wheat IDs carry no transcript suffix and its ID columns are
        # indexed, so an IN lookup on every annotation version is fast.
        placeholders = ",".join(["%s"] * len(base_forms))
        with mysql_cursor(settings.DB_PPI) as cursor:
            cursor.execute(
                f"SELECT * FROM `PPI_poppin` WHERE WheatID1 IN ({placeholders}) "
                f"OR WheatID2 IN ({placeholders})",
                tuple(base_forms) * 2,
            )
            for row in cursor.fetchall():
                interactions.append(
                    PPIInteraction(
                        wheat_id1=[str(row["WheatID1"])],
                        wheat_id2=[str(row["WheatID2"])],
                        subgenome1=row.get("Subgenome1") or None,
                        subgenome2=row.get("Subgenome2") or None,
                        supporting_edges=int(row.get("SupportingEdges") or 0),
                        identity1=float(row["Identity1"]) if row.get("Identity1") is not None else None,
                        identity2=float(row["Identity2"]) if row.get("Identity2") is not None else None,
                        rice_pair=normalize_text(str(row.get("Rice_pair") or "")) or None,
                    )
                )
        hint = None
        if not interactions:
            hint = (
                "No PoppIn interaction for the requested gene(s). The network "
                "stores IWGSC v2 (02G) gene IDs; looked up: "
                + ", ".join(base_forms)
                + ". An empty result means none of the transferred rice "
                "interactions involve these genes."
            )
        return ok({
            "interactions": [i.model_dump(exclude_none=True) for i in interactions],
            "id_versions": version_map,
            "hint": hint,
        })

    # Choose the index-backed lookup when the normalised gene index exists;
    # otherwise fall back to the REGEXP scan over the ~3M-row table.
    placeholders = ",".join(["%s"] * len(base_forms))
    if _ppi_gene_index_available():
        with mysql_cursor(settings.DB_PPI) as cursor:
            cursor.execute(
                f"SELECT nameids FROM ppi_result_gene_index WHERE gene IN ({placeholders})",
                tuple(base_forms),
            )
            nameids: list[int] = []
            for row in cursor.fetchall():
                for token in str(row.get("nameids") or "").split(","):
                    token = token.strip()
                    if token.isdigit():
                        nameids.append(int(token))
        if nameids:
            id_ph = ",".join(["%s"] * len(nameids))
            sql = f"SELECT * FROM `PPI_result` WHERE Nameid IN ({id_ph}) AND Score >= %s"
            params: tuple = tuple(sorted(set(nameids))) + (min_score,)
        else:
            sql = "SELECT * FROM `PPI_result` WHERE 1=0"
            params = ()
    else:
        patterns = []
        for gene in genes:
            for form in variants(gene, prefer=("v2", "v1", "v3")):
                base = re.sub(r"\.\d+$", "", form)
                pattern = f"(^|#){re.escape(base)}(\\.\\d+)?(#|$)"
                if pattern not in patterns:
                    patterns.append(pattern)
        combined = "|".join(patterns)
        sql = (
            "SELECT * FROM `PPI_result` "
            "WHERE (WheatID1 REGEXP %s OR WheatID2 REGEXP %s) AND Score >= %s"
        )
        params = (combined, combined, min_score)

    with mysql_cursor(settings.DB_PPI) as cursor:
        cursor.execute(sql, params)
        # Discover actual column names from cursor.description (positional, like CGI)
        col_map = {}
        extras = {}
        if cursor.description:
            cnames = [d[0] for d in cursor.description]
            col_map = {
                "WheatID1":     cnames[1] if len(cnames) > 1 else "WheatID1",
                "WheatID2":     cnames[2] if len(cnames) > 2 else "WheatID2",
                "eggNOGID1":    cnames[3] if len(cnames) > 3 else "eggNOGID1",
                "eggNOGID2":    cnames[4] if len(cnames) > 4 else "eggNOGID2",
                "Score":        cnames[5] if len(cnames) > 5 else "Score",
                "Annotation1":  cnames[6] if len(cnames) > 6 else "Annotation1",
                "Annotation2":  cnames[7] if len(cnames) > 7 else "Annotation2",
            }
            # Optional columns that only the PoppIn table carries.
            lowered = {c.lower(): c for c in cnames}
            extras = {
                "rice_pair": lowered.get("rice_pair"),
                "experimental": lowered.get("experimental"),
            }
        for row in cursor.fetchall():
            rice_col = extras.get("rice_pair")
            exp_col = extras.get("experimental")
            rice_pair = normalize_text(str(row[rice_col])) if rice_col else ""
            exp_value = row[exp_col] if exp_col else None
            interactions.append(
                PPIInteraction(
                    wheat_id1=[item.strip() for item in str(row[col_map["WheatID1"]]).split("#") if item.strip()],
                    wheat_id2=[item.strip() for item in str(row[col_map["WheatID2"]]).split("#") if item.strip()],
                    eggnog_id1=str(row[col_map["eggNOGID1"]]),
                    eggnog_id2=str(row[col_map["eggNOGID2"]]),
                    score=float(row[col_map["Score"]]),
                    annotation1=normalize_text(str(row[col_map["Annotation1"]])),
                    annotation2=normalize_text(str(row[col_map["Annotation2"]])),
                    rice_pair=rice_pair or None,
                    experimental_score=float(exp_value) if exp_value is not None else None,
                )
            )

    hint = None
    if not interactions:
        hint = (
            "No CF-MS interaction above the requested score for the requested "
            "gene(s). WheatPPI stores IWGSC v2 (02G) IDs; looked up: "
            + ", ".join(base_forms)
            + ". Lower min_score to include weaker interactions, or check the "
            "gene's annotation versions with /api/genes/detail."
        )
    return ok({
        "interactions": [i.model_dump(exclude_none=True) for i in interactions],
        "id_versions": version_map,
        "hint": hint,
    })
