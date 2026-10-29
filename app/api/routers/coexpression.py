"""Coexpression network routes."""

from __future__ import annotations

import pymysql
from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.core.exceptions import ResourceNotFound, ValidationFailure
from app.core.response import ok
from app.core.security import COEXPRESSION_TABLES, ensure_allowed_table, ensure_gene_like
from app.db.mysql import mysql_cursor
from app.schemas.network import BioprojectMeta, CoexpressionPair

coexpression_router = APIRouter(tags=["Coexpression"])

@coexpression_router.get("/coexpression/databases")
def list_coexpression_databases() -> dict:
    """List the available coexpression databases.

    Purpose:
        Return all coexpression datasets supported by the system, each with a
        unique ID and a description, for downstream queries.

    Usage:
        GET /api/coexpression/databases
        No parameters.

    Example:
        Request:
          curl -X GET "http://localhost:8000/api/coexpression/databases"

        Response:
          {
            "success": true,
            "data": [
              { "id": "CO_result2", "description": "Wheat grain coexpression" },
              { "id": "CO_PRJEB25639", "description": "Wheat multiple tissues coexpression" }
            ]
          }
    """

    return ok([{"id": key, "description": value} for key, value in COEXPRESSION_TABLES.items()])


@coexpression_router.get("/coexpression/query")
def query_coexpression(
    gene_ids: str = Query(...),
    database: str = Query("CO_PRJEB25639"),
    filter_value: float = Query(300),
) -> dict:
    """Query coexpression relationships for genes.

    Purpose:
        Given a list of gene IDs, query the coexpression partners of these
        genes in the specified coexpression database. Two filter modes are
        supported:
        - Decimal mode (e.g. 0.8): filter by PCC (Pearson correlation
          coefficient), returning records with |PCC| >= filter_value
        - Integer mode (e.g. 5): filter by MR (Mutual Rank), returning
          records with MR <= filter_value

    Usage:
        GET /api/coexpression/query?gene_ids=<gene1,gene2>&database=<database>&filter_value=<threshold>
        - gene_ids: required, comma-separated list of gene IDs
        - database: optional, coexpression database ID (CO_result2 or CO_PRJEB25639), default CO_PRJEB25639
        - filter_value: optional, filter threshold, default 300 (MR mode)

    Example:
        Request (PCC mode):
          curl -X GET "http://localhost:8000/api/coexpression/query?gene_ids=TraesCS5A02G391700&database=CO_PRJEB25639&filter_value=0.9"

        Request (MR mode):
          curl -X GET "http://localhost:8000/api/coexpression/query?gene_ids=TraesCS5A02G391700&database=CO_PRJEB25639&filter_value=5"

        Response:
          {
            "success": true,
            "data": {
              "database": "CO_PRJEB25639",
              "pairs": [
                { "gene1": "TraesCS5A02G391700", "gene2": "TraesCS5B02G391700", "pcc": 0.95, "mr": 3 }
              ]
            }
          }
    """

    database = ensure_allowed_table(database, COEXPRESSION_TABLES, "coexpression table")
    genes = [ensure_gene_like(gene.strip()) for gene in gene_ids.split(",") if gene.strip()]
    if not genes:
        raise ValidationFailure("No valid gene IDs provided")
    if len(genes) > 200:
        raise ValidationFailure(f"Too many gene IDs ({len(genes)}); maximum is 200 per query")
    pairs: list[CoexpressionPair] = []
    seen: set[tuple[str, str]] = set()
    gene_present = False

    # Column-name casing differs across tables:
    #   CO_result2 / CO_PRJEB25639  → Gene1, Gene2, PCC, MR (PascalCase)
    #   coexpression_filter_ext    → gene1, gene2, pcc, mr (lowercase)
    #   (now renamed to CO_BioticStress_2026; same lowercase schema)
    # MySQL folds identifier case in expressions, so `Gene1` resolves to
    # `gene1` on the lowercase table. SELECT aliases the canonical names
    # in a fixed casing so the row dict is consistent regardless of
    # which table is queried.
    select_cols = "Gene1 AS gene1, Gene2 AS gene2, PCC AS pcc, MR AS mr"

    # Batched: one query for all genes (previously N queries, one per gene).
    # `(Gene1 IN (...) OR Gene2 IN (...))` keeps any pair touching a requested
    # gene; the per-row dedup below collapses the same pair seen from both ends.
    placeholders = ",".join(["%s"] * len(genes))
    with mysql_cursor(settings.DB_COEXPRESSION) as cursor:
        if "." in str(filter_value):
            cursor.execute(
                f"""
                SELECT {select_cols}
                FROM `{database}`
                WHERE (Gene1 IN ({placeholders}) OR Gene2 IN ({placeholders}))
                AND (CAST(PCC AS DECIMAL(10,4)) >= %s OR CAST(PCC AS DECIMAL(10,4)) <= %s)
                ORDER BY CAST(PCC AS DECIMAL(10,4)) DESC
                """,
                (*genes, *genes, filter_value, -filter_value),
            )
        else:
            cursor.execute(
                f"""
                SELECT {select_cols}
                FROM `{database}`
                WHERE (Gene1 IN ({placeholders}) OR Gene2 IN ({placeholders}))
                AND CAST(MR AS UNSIGNED) <= %s
                ORDER BY CAST(MR AS UNSIGNED) ASC
                """,
                (*genes, *genes, int(filter_value)),
            )
        for row in cursor.fetchall():
            gene1 = str(row["gene1"]).strip()
            gene2 = str(row["gene2"]).strip()
            key = tuple(sorted((gene1, gene2)))
            if key in seen:
                continue
            seen.add(key)
            pairs.append(
                CoexpressionPair(
                    gene1=gene1,
                    gene2=gene2,
                    pcc=float(row["pcc"]),
                    mr=int(str(row["mr"]).split(".")[0]),
                )
            )

    # If we found no pairs at all, probe whether the genes actually exist
    # in the chosen database so the caller can distinguish "no partners
    # for this gene" from "this gene is not in this database". Skip the
    # probe when the threshold already eliminates everything, but at
    # least one gene exists — that's a real "no partners" answer.
    if not pairs and genes:
        with mysql_cursor(settings.DB_COEXPRESSION) as cursor:
            # Batched existence probe (previously one query per gene).
            cursor.execute(
                f"SELECT 1 FROM `{database}` "
                f"WHERE Gene1 IN ({placeholders}) OR Gene2 IN ({placeholders}) LIMIT 1",
                (*genes, *genes),
            )
            if cursor.fetchone():
                gene_present = True

    return ok({
        "database": database,
        "genes": genes,
        "gene_present": gene_present,
        "pairs": [pair.model_dump() for pair in pairs],
    })


# ---------------------------------------------------------------------------
# Bioproject metadata endpoints
# ---------------------------------------------------------------------------
# Reads from coexpressiondb.bioproject_meta, populated by
# scripts/crawl_bioprojects.py from NCBI E-utilities, ENA portal API, and
# CNGB. The bioproject_meta table must exist (init_bioproject_meta.sql)
# and have rows (run the crawler) before these endpoints return data.

def _bioproject_from_row(row: dict) -> BioprojectMeta:
    return BioprojectMeta(
        accession=str(row.get("accession", "")),
        source=str(row.get("source", "")),
        title=row.get("title"),
        description=row.get("description"),
        organism=row.get("organism"),
        submitter=row.get("submitter"),
        submission_date=row.get("submission_date"),
        publication_date=row.get("publication_date"),
        data_type=row.get("data_type"),
        sample_count=row.get("sample_count"),
        study_type=row.get("study_type"),
        related_pubmed=row.get("related_pubmed"),
        related_doi=row.get("related_doi"),
    )


def _query_bioprojects(sql: str, params: list) -> list[dict]:
    """Run a bioproject_meta query, turning a missing table into a clear 503.

    Without this, a never-initialized table surfaces as a generic 500 with a
    full traceback in the journal on every frontend poll.
    """
    try:
        with mysql_cursor(settings.DB_COEXPRESSION) as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()
    except pymysql.err.ProgrammingError as exc:
        if exc.args[0] == 1146:  # ER_NO_SUCH_TABLE
            raise HTTPException(
                status_code=503,
                detail="bioproject_meta 元数据表尚未初始化：请在服务器运行 "
                       "python3 scripts/crawl_bioprojects.py（自动建表并爬取 NCBI/ENA 元数据）。",
            ) from exc
        raise


@coexpression_router.get("/coexpression/projects")
def list_bioprojects(
    source: str | None = Query(None, pattern="^(NCBI|ENA|CNGB)$"),
    q: str | None = Query(None, description="Substring search over title/description/organism"),
) -> dict:
    """List bioproject metadata records.

    Purpose:
        Return the bioproject metadata crawled into the
        `coexpressiondb.bioproject_meta` table. Optionally filter by data
        source (NCBI/ENA/CNGB), and optionally substring-search over
        title / description / species.

    Usage:
        GET /api/coexpression/projects
        GET /api/coexpression/projects?source=NCBI
        GET /api/coexpression/projects?q=wheat
    """
    where = []
    params: list = []
    if source:
        where.append("source = %s")
        params.append(source)
    if q:
        like = f"%{q}%"
        where.append("(title LIKE %s OR description LIKE %s OR organism LIKE %s)")
        params.extend([like, like, like])

    sql = "SELECT * FROM bioproject_meta"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY source, accession"

    rows = _query_bioprojects(sql, params)

    records = [_bioproject_from_row(r).model_dump() for r in rows]
    return ok({"total": len(records), "records": records})


@coexpression_router.get("/coexpression/projects/{accession}")
def get_bioproject(accession: str) -> dict:
    """Return one bioproject's metadata, 404 if absent.

    Usage:
        GET /api/coexpression/projects/PRJNA976214
    """
    rows = _query_bioprojects(
        "SELECT * FROM bioproject_meta WHERE accession = %s", [accession])
    if not rows:
        raise ResourceNotFound(f"Bioproject not found: {accession}")
    return ok(_bioproject_from_row(rows[0]).model_dump())

