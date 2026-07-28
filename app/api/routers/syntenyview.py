"""SynTeny Viewer — JCVI-style gene neighborhood synteny across homoeologous groups.

Reads BED files from /var/www/html/col_bed, resolves homoeologous cluster
membership via SpeciesIDs_cluster.txt, and returns neighborhood + same-cluster
gene connections for a JCVI-style frontend visualization.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import APIRouter, Query

from app.core.config import settings

router = APIRouter(prefix="/syntenyview", tags=["SynTeny Viewer"])

BED_DIR = Path("/var/www/html/col_bed")
CLUSTER_FILE = settings.ORTHOFINDER_CLUSTER_FILE

_WS = " \t\n\r\x00\x0b'\""

def _clean(s: str) -> str:
    return str(s).strip(_WS)


# ---------------------------------------------------------------------------
# Cluster map (shared logic with orthofinder — copied standalone for isolation)
# ---------------------------------------------------------------------------

_cluster_cache: tuple | None = None
_sorted_prefixes: list | None = None

def _load_cluster_map() -> tuple[dict, dict]:
    global _cluster_cache
    if _cluster_cache is not None:
        return _cluster_cache
    prefix_map: dict[str, int] = {}
    chrom_map: dict[str, int] = {}
    if CLUSTER_FILE.exists():
        for line in CLUSTER_FILE.read_text(encoding="utf-8").splitlines()[1:]:
            cols = line.split("\t")
            if len(cols) < 8:
                continue
            for c in range(1, 8):
                val = cols[c].strip()
                if not val:
                    continue
                if re.match(r"^chr\d+[ABD]$", val, re.I):
                    chrom_map[val.lower()] = c
                else:
                    prefix_map[val] = c
    _cluster_cache = (prefix_map, chrom_map)
    return _cluster_cache

def _get_sorted_prefixes() -> list:
    global _sorted_prefixes
    if _sorted_prefixes is not None:
        return _sorted_prefixes
    prefix_map, _ = _load_cluster_map()
    _sorted_prefixes = sorted(prefix_map.keys(), key=lambda x: -len(x))
    return _sorted_prefixes

def _resolve_cluster(gene_id: str) -> int | None:
    gene_id = _clean(gene_id)
    prefix_map, chrom_map = _load_cluster_map()
    # 1) prefix match
    for pfx in _get_sorted_prefixes():
        if gene_id.lower().startswith(pfx.lower()):
            return prefix_map[pfx]
    # 2) chromosome fallback via BED
    if chrom_map:
        entry = _load_bed_map().get(gene_id)
        if entry:
            chrom = entry["chrom"]
            if chrom and chrom.lower() in chrom_map:
                return chrom_map[chrom.lower()]
    return None


# ---------------------------------------------------------------------------
# BED map (full position data)
# ---------------------------------------------------------------------------

_bed_cache: dict | None = None
_chrom_lists: dict | None = None  # (genome, subgenome, chrom) -> [(start, gene_id), ...]

def _load_bed_map() -> dict:
    """Build gene_id -> {chrom, start, end, genome, subgenome} from BED_DIR."""
    global _bed_cache, _chrom_lists
    if _bed_cache is not None:
        return _bed_cache

    mp: dict = {}
    cl: dict = {}
    if not BED_DIR.exists():
        _bed_cache = mp; _chrom_lists = cl
        return mp

    for entry in sorted(BED_DIR.iterdir()):
        fname = entry.name
        if not fname.endswith(".bed"):
            continue
        # Parse file name: Genome_A.filter.bed or Genome_A.bed
        base = os.path.splitext(fname)[0]
        base = re.sub(r"\.filter$", "", base)
        parts = base.rsplit("_", 1)
        genome_name = parts[0] if len(parts) == 2 else base
        sub = parts[1] if len(parts) == 2 and parts[1] in ("A", "B", "D") else ""
        if not sub:
            continue
        try:
            for line in entry.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("track"):
                    continue
                cols = line.split("\t")
                if len(cols) < 4:
                    continue
                gid = _clean(cols[3])
                chrom = _clean(cols[0])
                if not (gid and chrom):
                    continue
                try:
                    s, e = int(cols[1]), int(cols[2])
                except ValueError:
                    s, e = 0, 0
                mp[gid] = {"chrom": chrom, "start": s, "end": e,
                           "genome": genome_name, "subgenome": sub}
                key = (genome_name, sub, chrom)
                cl.setdefault(key, []).append((s, gid))
        except Exception:
            continue

    for k in cl:
        cl[k].sort(key=lambda x: x[0])
    _bed_cache = mp
    _chrom_lists = cl
    return mp


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@router.get("/neighborhood")
def neighborhood(
    q: str = Query(..., description="Gene ID, e.g. TraesCS1A02G219700.1"),
    upstream: int = Query(5, ge=0, le=20),
    downstream: int = Query(5, ge=0, le=20),
):
    """Return chromosomal neighborhood with homoeologous cluster assignments."""
    gene_id = _clean(q)
    if not gene_id:
        return {"error": "Please provide a gene ID"}

    bc_map = _load_bed_map()
    entry = bc_map.get(gene_id)
    if not entry:
        return {"error": f"Gene '{gene_id}' not found in BED files"}

    gchrom, ggenome, gsub = entry["chrom"], entry["genome"], entry["subgenome"]
    gpos = entry["start"]

    # Get current chromosome gene window
    chrom_key = (ggenome, gsub, gchrom)
    if chrom_key not in _chrom_lists:
        return {"error": f"No gene list for {ggenome}_{gsub} chr{gchrom}"}

    gene_list = _chrom_lists[chrom_key]
    q_idx = next((i for i, (_, gid) in enumerate(gene_list) if gid == gene_id), None)
    if q_idx is None:
        return {"error": f"Gene '{gene_id}' not found on chromosome"}

    lo, hi = max(0, q_idx - upstream), min(len(gene_list), q_idx + downstream + 1)
    query_window = gene_list[lo:hi]

    # Build per-chromosome lists for ALL genomes (same cluster)
    query_cluster = _resolve_cluster(gene_id)

    # For the synteny view, we want: same genes on the query chromosome,
    # PLUS their same-cluster counterparts on OTHER chromosomes/genomes.
    rows: list[dict] = []
    cluster_connections: list[dict] = []  # {from_gene, to_gene, cluster}

    # Group all genes by (genome, subgenome, chrom) for the query window
    query_genes_by_pos: dict[str, list] = {}
    for pos, gid in query_window:
        c = _resolve_cluster(gid)
        query_genes_by_pos[gid] = c

    # Per-chromosome rows: one row per unique (genome, subgenome, chrom)
    seen_chroms: set = set()
    for pos, gid in query_window:
        info = bc_map.get(gid, {})
        ch = info.get("chrom", "?")
        gn = info.get("genome", "?")
        sg = info.get("subgenome", "?")
        sid = f"{gn}_{sg}_{ch}"
        if sid not in seen_chroms:
            seen_chroms.add(sid)
            rows.append({
                "genome": gn, "subgenome": sg, "chrom": ch,
                "genes": []  # will be filled from chrom gene list
            })

    # For each row, get all genes near the query position on that chrom
    for row in rows:
        rkey = (row["genome"], row["subgenome"], row["chrom"])
        if rkey in _chrom_lists:
            all_genes = _chrom_lists[rkey]
            # find nearest index to query position
            ri = min(range(len(all_genes)), key=lambda i: abs(all_genes[i][0] - gpos))
            rlo, rhi = max(0, ri - upstream), min(len(all_genes), ri + downstream + 1)
            for pos, gid in all_genes[rlo:rhi]:
                c = _resolve_cluster(gid)
                row["genes"].append({"gene_id": gid, "cluster": c, "start": pos})

    # Build cluster connections: for each query_cluster gene, find same-cluster
    # genes on other chromosomes
    for row_a in rows:
        for ga in row_a["genes"]:
            if ga["cluster"] != query_cluster or query_cluster is None:
                continue
            for row_b in rows:
                if row_b["chrom"] == row_a["chrom"] and row_b["genome"] == row_a["genome"]:
                    continue  # same chromosome — skip self-connections (not synteny)
                for gb in row_b["genes"]:
                    if gb["cluster"] == query_cluster:
                        cluster_connections.append({
                            "from_gene": ga["gene_id"],
                            "from_chrom": row_a["chrom"],
                            "from_genome": row_a["genome"],
                            "to_gene": gb["gene_id"],
                            "to_chrom": row_b["chrom"],
                            "to_genome": row_b["genome"],
                            "cluster": query_cluster,
                        })

    return {
        "query": gene_id,
        "query_cluster": query_cluster,
        "query_genome": ggenome,
        "query_subgenome": gsub,
        "query_chrom": gchrom,
        "rows": rows,
        "cluster_connections": cluster_connections,
    }
