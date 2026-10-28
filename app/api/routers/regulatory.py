"""
Wheat Regulatory Hub API
Read-only access to regulatory.sqlite.
Python 3.8 compatible.
"""

import csv
import io
import os
import re
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

router = APIRouter(
    prefix="/regulatory",
    tags=["Wheat Regulatory Hub"]
)

DB_PATH = Path(
    os.environ.get(
        "WHEAT_REGULATORY_DB",
        "/var/www/html/wheat-regulatory-hub/"
        "data/processed/regulatory.sqlite"
    )
)

GENE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")

MAX_EXPORT_ROWS = 100000


def get_connection():
    if not DB_PATH.is_file():
        raise HTTPException(
            status_code=503,
            detail="Regulatory database not found"
        )

    uri = "file:{}?mode=ro".format(
        DB_PATH.resolve().as_posix()
    )

    try:
        con = sqlite3.connect(
            uri,
            uri=True,
            timeout=30
        )
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        con.execute("PRAGMA busy_timeout=30000")
        return con

    except sqlite3.Error:
        raise HTTPException(
            status_code=503,
            detail="Regulatory database unavailable"
        )


def validate_id(value):
    if not GENE_RE.fullmatch(value):
        raise HTTPException(
            status_code=400,
            detail="Invalid gene or transcript ID"
        )


def resolve_gene(con, identifier):
    gene = con.execute(
        """
        SELECT gene_id, chrom, start0, end0,
               strand, transcript_id, tss0, tes0
        FROM genes
        WHERE gene_id=?
        """,
        (identifier,)
    ).fetchone()

    if gene is None:
        transcript = con.execute(
            """
            SELECT gene_id
            FROM transcripts
            WHERE transcript_id=?
            """,
            (identifier,)
        ).fetchone()

        if transcript:
            gene = con.execute(
                """
                SELECT gene_id, chrom, start0, end0,
                       strand, transcript_id, tss0, tes0
                FROM genes
                WHERE gene_id=?
                """,
                (transcript["gene_id"],)
            ).fetchone()

    if gene is None:
        raise HTTPException(
            status_code=404,
            detail="Gene or transcript not found"
        )

    return dict(gene)


def get_region(con, gene_id, kind="upstream"):
    region = con.execute(
        """
        SELECT region_id, gene_id, kind,
               chrom, start0, end0
        FROM regions
        WHERE gene_id=? AND kind=?
        LIMIT 1
        """,
        (gene_id, kind)
    ).fetchone()

    if region is None:
        raise HTTPException(
            status_code=404,
            detail="Regulatory region not found"
        )

    return dict(region)


def filters(region_id, motif, strand, max_pvalue):
    clauses = ["h.region_id=?"]
    params = [region_id]

    if motif:
        clauses.append("h.motif_id LIKE ?")
        params.append("%" + motif + "%")

    if strand:
        clauses.append("h.strand=?")
        params.append(strand)

    if max_pvalue is not None:
        clauses.append("h.pvalue<=?")
        params.append(max_pvalue)

    return " AND ".join(clauses), params


@router.get("/health")
def health():
    con = get_connection()
    try:
        rows = con.execute(
            """
            SELECT batch_name
            FROM completed_batches
            WHERE batch_name LIKE '%_upstream'
            """
        ).fetchall()

        completed = [r["batch_name"] for r in rows]

        return {
            "status": "ok",
            "database": "regulatory.sqlite",
            "completed_upstream_batches": len(completed),
            "expected_upstream_batches": 21,
            "ready": len(completed) == 21
        }
    finally:
        con.close()


@router.get("/gene/{gene_id}")
def gene_profile(gene_id: str):
    validate_id(gene_id)
    con = get_connection()

    try:
        gene = resolve_gene(con, gene_id)
        region = get_region(con, gene["gene_id"])

        summary = con.execute(
            """
            SELECT COUNT(*) AS hit_count,
                   COUNT(DISTINCT motif_id) AS motif_count,
                   MIN(pvalue) AS min_pvalue
            FROM hits
            WHERE region_id=?
            """,
            (region["region_id"],)
        ).fetchone()

        return {
            "gene": gene,
            "region": region,
            "summary": dict(summary),
            "region_kind": "upstream",
            "assembly": "IWGSC RefSeq v1.0"
        }

    finally:
        con.close()


@router.get("/gene/{gene_id}/hits")
def gene_hits(
    gene_id: str,
    motif: str = Query("", max_length=100),
    strand: str = Query("", pattern=r"^$|^[+-]$"),
    max_pvalue: float = Query(0.0001, gt=0, le=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200)
):
    validate_id(gene_id)

    con = get_connection()

    try:
        gene = resolve_gene(con, gene_id)
        region = get_region(con, gene["gene_id"])

        where, params = filters(
            region["region_id"],
            motif,
            strand,
            max_pvalue
        )

        total = con.execute(
            "SELECT COUNT(*) FROM hits h WHERE " + where,
            params
        ).fetchone()[0]

        offset = (page - 1) * page_size

        rows = con.execute(
            """
            SELECT h.hit_id,
                   h.motif_id,
                   m.name AS motif_name,
                   m.source AS motif_source,
                   h.chrom, h.start0, h.end0,
                   h.strand, h.score, h.pvalue,
                   h.qvalue, h.matched_sequence
            FROM hits h
            LEFT JOIN motifs m
              ON h.motif_id=m.motif_id
            WHERE {}
            ORDER BY h.start0, h.hit_id
            LIMIT ? OFFSET ?
            """.format(where),
            params + [page_size, offset]
        ).fetchall()

        return {
            "gene_id": gene["gene_id"],
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [dict(r) for r in rows]
        }

    finally:
        con.close()


@router.get("/gene/{gene_id}/track")
def gene_track(
    gene_id: str,
    max_pvalue: float = Query(0.000001, gt=0, le=1),
    limit: int = Query(250, ge=1, le=1000)
):
    validate_id(gene_id)
    con = get_connection()

    try:
        gene = resolve_gene(con, gene_id)
        region = get_region(con, gene["gene_id"])

        rows = con.execute(
            """
            SELECT hit_id, motif_id,
                   start0, end0, strand, pvalue
            FROM hits
            WHERE region_id=? AND pvalue<=?
            ORDER BY pvalue, hit_id
            LIMIT ?
            """,
            (region["region_id"], max_pvalue, limit)
        ).fetchall()

        return {
            "gene_id": gene["gene_id"],
            "gene_strand": gene["strand"],
            "region": region,
            "items": [dict(r) for r in rows],
            "limit": limit,
            "display_mode": "strongest_hits"
        }

    finally:
        con.close()


@router.get("/motifs")
def search_motifs(
    q: str = Query("", max_length=100),
    limit: int = Query(30, ge=1, le=100)
):
    con = get_connection()

    try:
        rows = con.execute(
            """
            SELECT motif_id, name, source
            FROM motifs
            WHERE motif_id LIKE ? OR name LIKE ?
            ORDER BY motif_id
            LIMIT ?
            """,
            ("%" + q + "%", "%" + q + "%", limit)
        ).fetchall()

        return {
            "items": [dict(r) for r in rows]
        }

    finally:
        con.close()


@router.get("/gene/{gene_id}/export")
def export_gene_hits(
    gene_id: str,
    motif: str = Query("", max_length=100),
    strand: str = Query("", pattern=r"^$|^[+-]$"),
    max_pvalue: float = Query(0.0001, gt=0, le=1)
):
    validate_id(gene_id)

    con = get_connection()

    try:
        gene = resolve_gene(con, gene_id)
        region = get_region(con, gene["gene_id"])
        region_id = region["region_id"]
        resolved_id = gene["gene_id"]

        where, params = filters(
            region_id, motif, strand, max_pvalue
        )

        count = con.execute(
            "SELECT COUNT(*) FROM hits h WHERE " + where,
            params
        ).fetchone()[0]

        if count > MAX_EXPORT_ROWS:
            raise HTTPException(
                status_code=413,
                detail=(
                    "Export exceeds 100000 rows. "
                    "Please apply stricter filters."
                )
            )

    finally:
        con.close()

    def stream_csv():
        connection = get_connection()

        try:
            where, params = filters(
                region_id, motif, strand, max_pvalue
            )

            cursor = connection.execute(
                """
                SELECT h.motif_id, h.chrom,
                       h.start0, h.end0,
                       h.strand, h.score,
                       h.pvalue, h.qvalue,
                       h.matched_sequence
                FROM hits h
                WHERE {}
                ORDER BY h.start0, h.hit_id
                LIMIT ?
                """.format(where),
                params + [MAX_EXPORT_ROWS]
            )

            buffer = io.StringIO()
            writer = csv.writer(buffer)

            writer.writerow([
                "motif_id", "chrom", "start0", "end0",
                "strand", "score", "pvalue",
                "qvalue", "matched_sequence"
            ])

            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

            for row in cursor:
                # Prevent spreadsheet formula injection.
                values = []
                for value in row:
                    if (
                        isinstance(value, str)
                        and value.startswith(
                            ("=", "+", "-", "@", "\t", "\r")
                        )
                    ):
                        value = "'" + value
                    values.append(value)

                writer.writerow(values)
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate(0)

        finally:
            connection.close()

    return StreamingResponse(
        stream_csv(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":
            'attachment; filename="{}_motifs.csv"'.format(
                resolved_id
            )
        }
    )
