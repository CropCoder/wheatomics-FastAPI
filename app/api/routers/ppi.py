"""PPI (protein-protein interaction) routes."""

from __future__ import annotations

import re

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.exceptions import ValidationFailure
from app.core.response import ok
from app.core.security import PPI_TABLES, ensure_allowed_table, ensure_gene_like
from app.db.mysql import mysql_cursor
from app.schemas.network import PPIInteraction
from app.services.legacy_parsers import normalize_text

ppi_router = APIRouter(tags=["Search Wheat Protein-Protein Interactions"])


@ppi_router.get("/ppi/query")
def query_ppi(
    gene_ids: str = Query(...),
    table: str = Query("PPI_result"),
    min_score: float = Query(0.5),
) -> dict:
    """Query protein-protein interaction (PPI) relationships.

    ⚠️  Gene ID notes:
        This module uses wheat protein interaction data (wheatPPI), based on
        the Chinese Spring IWGSC v2.1 annotation. Input must be transcript IDs
        (the gene ID with a ".1" suffix appended), e.g.
        "TraesCS6D02G084800.1". If a gene ID without ".1" is supplied, the
        query will not match any results.

    Purpose:
        Given a list of gene IDs, query the protein pairs that interact with
        those proteins in the protein interaction database. Returns the gene
        IDs of both interacting partners, eggNOG IDs, functional annotations
        and interaction scores (Score).

        Score threshold notes (CF-MS score):
        - 0.5: medium confidence (default)
        - 0.2: low confidence
        - 0: no filtering, return all records

    Usage:
        GET /api/ppi/query?gene_ids=<gene1,gene2>&table=<table>&min_score=<minimum score>
        - gene_ids: required, comma-separated list of gene IDs (transcript IDs with the ".1" suffix)
        - table: optional, PPI data table name, default PPI_result
        - min_score: optional, CF-MS interaction score threshold, default 0.5. Common values: 0.5 (medium), 0.2 (low), 0 (all)

    Example:
        Request:
          curl -X GET "http://localhost:8000/api/ppi/query?gene_ids=TraesCS6D02G084800.1&table=PPI_result&min_score=0.5"

        Response:
          {
            "success": true,
            "data": {
              "interactions": [
                {
                  "wheat_id1": ["TraesCS6D02G084800"],
                  "wheat_id2": ["TraesCS6D02G084800.1"],
                  "eggnog_id1": "ENOG410XNNN",
                  "eggnog_id2": "ENOG410XMMM",
                  "score": 0.95,
                  "annotation1": "MADS-box transcription factor",
                  "annotation2": "Flowering time protein"
                }
              ]
            }
          }
    """

    table = ensure_allowed_table(table, PPI_TABLES, "ppi table")
    genes = [ensure_gene_like(gene.strip()) for gene in gene_ids.split(",") if gene.strip()]
    if not genes:
        raise ValidationFailure("No valid gene IDs provided")
    if len(genes) > 200:
        raise ValidationFailure(f"Too many gene IDs ({len(genes)}); maximum is 200 per query")
    interactions: list[PPIInteraction] = []

    # Batched: one query for all genes (previously N queries, one per gene).
    # REGEXP can't use an index, so we still scan once per table, but now it's
    # one scan matching any of the requested genes via alternation, not N scans.
    # WheatID columns store multiple IDs joined by '#' (e.g. "A.1#B.1#C.1"), so
    # anchor each gene with (^|#)...(#|$) instead of ^...$ to match one ID inside
    # the multi-value field without matching an unrelated prefix.
    patterns = [f"(^|#){re.escape(g)}(#|$)" for g in genes]
    # MySQL REGEXP supports alternation; join into one pattern so a single scan
    # matches any requested gene in either WheatID column.
    combined = "|".join(patterns)
    with mysql_cursor(settings.DB_PPI) as cursor:
        cursor.execute(
            f"""
            SELECT * FROM `{table}`
            WHERE (WheatID1 REGEXP %s OR WheatID2 REGEXP %s) AND Score >= %s
            """,
            (combined, combined, min_score),
        )
        # Discover actual column names from cursor.description (positional, like CGI)
        col_map = {}
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
        for row in cursor.fetchall():
            interactions.append(
                PPIInteraction(
                    wheat_id1=[item.strip() for item in str(row[col_map["WheatID1"]]).split("#") if item.strip()],
                    wheat_id2=[item.strip() for item in str(row[col_map["WheatID2"]]).split("#") if item.strip()],
                    eggnog_id1=str(row[col_map["eggNOGID1"]]),
                    eggnog_id2=str(row[col_map["eggNOGID2"]]),
                    score=float(row[col_map["Score"]]),
                    annotation1=normalize_text(str(row[col_map["Annotation1"]])),
                    annotation2=normalize_text(str(row[col_map["Annotation2"]])),
                )
            )

    return ok({"interactions": [interaction.model_dump() for interaction in interactions]})
