"""OrthoFinder orthogroup browser routes.

Provides search and download endpoints for OrthoFinder results:
query a protein/gene ID → find orthogroup → return members, tree, alignment.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.response import ok
from app.db.mysql import mysql_cursor

ORTHOFINDER_BASE_DIR = settings.ORTHOFINDER_BASE_DIR
ORTHOFINDER_DB = settings.DB_ORTHOFINDER

router = APIRouter(prefix="/orthofinder", tags=["OrthoFinder"])


@router.get("/search", summary="Search by protein ID")
def search_orthofinder(
    q: str = Query(..., description="Protein/gene ID to search, e.g. TraesCS1A03G0053300.1"),
) -> dict:
    """Search for a protein/gene ID and return its orthogroup details.

    Function:
        Look up the query protein ID in the OrthoFinder database to find
        which orthogroup it belongs to, then return orthogroup members,
        gene tree (Newick format), and multiple sequence alignment.

    Usage:
        GET /api/orthofinder/search?q=<gene_id>

    Example:
        Request:
          curl -X GET "http://localhost:8000/api/orthofinder/search?q=TraesCS1A03G0053300.1"

        Response:
          {
            "success": true,
            "data": {
              "query": "TraesCS1A03G0053300.1",
              "orthogroup": "OG0001897",
              "gene_count": 25,
              "genes": ["TraesCS1A03G0053300.1", "TraesCS1B03G0060100.1", ...],
              "tree": "(seq1:0.05,seq2:0.03);",
              "alignment": ">seq1\nMASS...\n>seq2\nMASS...\n",
              "sequence_map": {
                "seq1": "TraesCS1A03G0053300.1",
                "seq2": "TraesCS1B03G0060100.1"
              }
            }
          }

    Errors:
        404 - Protein ID not found or orthogroup not found
    """
    q = q.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Query protein ID is required")

    gene_hash = hashlib.md5(q.encode("utf-8")).hexdigest()

    with mysql_cursor(ORTHOFINDER_DB) as cursor:
        # Step 1: Find orthogroup for query gene
        cursor.execute(
            "SELECT og_id FROM gene_to_og WHERE gene_hash = %s AND gene_id = %s LIMIT 1",
            (gene_hash, q),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Protein ID not found: {q}")

        og_id = row["og_id"]

        # Step 2: Get orthogroup details
        cursor.execute(
            "SELECT og_id, genes, gene_count FROM orthogroups WHERE og_id = %s LIMIT 1",
            (og_id,),
        )
        og_row = cursor.fetchone()
        if not og_row:
            raise HTTPException(status_code=404, detail=f"Orthogroup not found: {og_id}")

        genes = og_row["genes"].split() if og_row["genes"] else []
        gene_count = og_row["gene_count"]

        # Step 3: Read tree file from disk
        tree_file = (
            ORTHOFINDER_BASE_DIR
            / "WorkingDirectory"
            / "Resolved_Gene_Trees"
            / f"{og_id}.txt"
        )
        tree = tree_file.read_text(encoding="utf-8") if tree_file.exists() else ""

        # Step 4: Read alignment file from disk
        aln_file = (
            ORTHOFINDER_BASE_DIR
            / "WorkingDirectory"
            / "Alignments_ids"
            / f"{og_id}.fa"
        )
        alignment = aln_file.read_text(encoding="utf-8") if aln_file.exists() else ""

        # Step 5: Extract short IDs from alignment headers
        short_ids: set[str] = set()
        if alignment:
            short_ids = set(re.findall(r"^>(\S+)", alignment, re.MULTILINE))

        # Step 6: Map short IDs to full gene IDs
        seq_map: dict[str, str] = {}
        if short_ids:
            short_list = list(short_ids)
            placeholders = ",".join(["%s"] * len(short_list))
            cursor.execute(
                f"SELECT short_id, gene_id FROM sequence_ids WHERE short_id IN ({placeholders})",
                short_list,
            )
            for r in cursor.fetchall():
                seq_map[r["short_id"]] = r["gene_id"]

        return ok({
            "query": q,
            "orthogroup": og_id,
            "gene_count": gene_count,
            "genes": genes,
            "tree": tree,
            "alignment": alignment,
            "sequence_map": seq_map,
        })


@router.get("/download", summary="Download tree or alignment file")
def download_orthofinder_file(
    og: str = Query(..., description="OrthoFinder OG ID, e.g. OG0001897"),
    type: str = Query(..., description="File type: 'tree' or 'alignment'"),
) -> FileResponse:
    """Download the orthogroup gene tree or multiple sequence alignment file.

    Function:
        Download the gene tree (Newick text format) or multiple sequence
        alignment (FASTA format) file for a given orthogroup.

    Usage:
        GET /api/orthofinder/download?og=<og_id>&type=<tree|alignment>

    Examples:
        Download gene tree:
          curl -X GET "http://localhost:8000/api/orthofinder/download?og=OG0001897&type=tree"

        Download MSA:
          curl -X GET "http://localhost:8000/api/orthofinder/download?og=OG0001897&type=alignment"

    Errors:
        400 - Invalid OG ID format or type
        404 - File not found on disk
    """
    if not re.match(r"^OG\d+$", og):
        raise HTTPException(status_code=400, detail="Invalid orthogroup ID format")

    if type == "tree":
        file_path = (
            ORTHOFINDER_BASE_DIR
            / "WorkingDirectory"
            / "Resolved_Gene_Trees"
            / f"{og}.txt"
        )
        filename = f"{og}.tree.txt"
        media_type = "text/plain"
    elif type == "alignment":
        file_path = (
            ORTHOFINDER_BASE_DIR
            / "WorkingDirectory"
            / "Alignments_ids"
            / f"{og}.fa"
        )
        filename = f"{og}.alignment.fa"
        media_type = "text/plain"
    else:
        raise HTTPException(status_code=400, detail="Invalid type; must be 'tree' or 'alignment'")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=filename,
    )
