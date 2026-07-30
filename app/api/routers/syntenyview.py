"""SynTeny Viewer — JCVI-style gene neighborhood synteny across homoeologous groups.

Reads BED files from /var/www/html/col_bed, resolves homoeologous cluster
membership via SpeciesIDs_cluster.txt, and returns neighborhood + same-cluster
gene connections for a JCVI-style frontend visualization.
"""

import os
import re
from pathlib import Path
from typing import Optional

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

_cluster_cache: Optional[tuple] = None
_sorted_prefixes: Optional[list] = None

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

def _resolve_cluster(gene_id: str) -> Optional[int]:
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

_bed_cache: Optional[dict] = None
_chrom_lists: Optional[dict] = None  # (genome, subgenome, chrom) -> [(start, gene_id), ...]

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
    """Return chromosomal neighborhood with homoeologous cluster assignments
    across ALL genomes, styled for a JCVI synteny plot."""
    gene_id = _clean(q)
    if not gene_id:
        return {"error": "Please provide a gene ID"}

    bc_map = _load_bed_map()
    entry = bc_map.get(gene_id)
    if not entry:
        return {"error": f"Gene '{gene_id}' not found in BED files"}

    query_cluster = _resolve_cluster(gene_id)
    if query_cluster is None:
        return {"error": f"Gene '{gene_id}' could not be assigned to a homoeologous cluster"}

    ggenome, gsub, gchrom = entry["genome"], entry["subgenome"], entry["chrom"]
    gpos = entry["start"]

    # ---- Step 1: build ONE row per (genome, subgenome, chrom) where we find
    #      genes with the SAME cluster as the query gene ----
    rows: list[dict] = []
    seen_keys: set = set()

    # Always include the query genome as the first row
    q_key = (ggenome, gsub, gchrom)
    if q_key in _chrom_lists:
        seen_keys.add(q_key)
        rows.append({"genome": ggenome, "subgenome": gsub, "chrom": gchrom,
                     "genes": [], "is_query_genome": True})

    # Scan ALL chromosome gene lists and find ones that contain any gene
    # in the same cluster as the query
    for key, glist in _chrom_lists.items():
        gn, sg, ch = key
        if key in seen_keys:
            continue
        # Check if this chromosome has ANY gene in query_cluster
        has_cluster_gene = False
        for _, gid in glist:
            if _resolve_cluster(gid) == query_cluster:
                has_cluster_gene = True
                break
        if has_cluster_gene:
            seen_keys.add(key)
            rows.append({"genome": gn, "subgenome": sg, "chrom": ch,
                         "genes": [], "is_query_genome": False})

    # ---- Step 2: fill the gene lists for each row ----
    for row in rows:
        rkey = (row["genome"], row["subgenome"], row["chrom"])
        glist = _chrom_lists.get(rkey, [])
        if not glist:
            continue

        if row["is_query_genome"]:
            # For the query genome: show the neighborhood window around q
            q_idx = next((i for i, (_, gid) in enumerate(glist) if gid == gene_id), 0)
            lo, hi = max(0, q_idx - upstream), min(len(glist), q_idx + downstream + 1)
            for pos, gid in glist[lo:hi]:
                c = _resolve_cluster(gid)
                row["genes"].append({"gene_id": gid, "cluster": c, "start": pos,
                                     "is_query": gid == gene_id})
        else:
            # For other genomes: find the gene(s) in the same cluster nearest
            # to the position of the query gene, then show their neighborhood
            candidates = [(pos, gid) for pos, gid in glist
                          if _resolve_cluster(gid) == query_cluster]
            if not candidates:
                continue
            # pick the candidate closest to the query gene position
            best = min(candidates, key=lambda x: abs(x[0] - gpos))
            c_idx = next(i for i, (p, _) in enumerate(glist) if p == best[0])
            clo, chi = max(0, c_idx - upstream), min(len(glist), c_idx + downstream + 1)
            for pos, gid in glist[clo:chi]:
                c = _resolve_cluster(gid)
                row["genes"].append({"gene_id": gid, "cluster": c, "start": pos,
                                     "is_query": False})

    # ---- Step 3: build same-cluster connections across rows ----
    cluster_connections: list[dict] = []
    for i, row_a in enumerate(rows):
        for ga in row_a["genes"]:
            if ga["cluster"] != query_cluster:
                continue
            for j, row_b in enumerate(rows):
                if j <= i:
                    continue  # only forward connections
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
