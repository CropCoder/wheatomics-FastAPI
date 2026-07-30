"""SynTeny Viewer — JCVI-style gene neighborhood synteny across homoeologous groups.

Reads BED files from /var/www/html/col_bed, resolves homoeologous cluster
membership via SpeciesIDs_cluster.txt, and returns neighborhood + same-cluster
gene connections for a JCVI-style frontend visualization.

PERFORMANCE: Cluster resolution is cached globally (_cluster_gene_cache).
First request builds the cache by scanning all BED genes once (~5-10s),
subsequent requests are sub-second.
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
# Cluster map
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

# ---------------------------------------------------------------------------
# Cached cluster resolution — avoids repeated O(N) scans
# ---------------------------------------------------------------------------

_cluster_gene_cache: Optional[dict] = None   # gene_id -> cluster (or None)

def _resolve_cluster(gene_id: str) -> Optional[int]:
    """Cached cluster resolution. First call builds cache via prefix-only match."""
    global _cluster_gene_cache
    if _cluster_gene_cache is not None and gene_id in _cluster_gene_cache:
        return _cluster_gene_cache[gene_id]

    gene_id = _clean(gene_id)
    prefix_map, chrom_map = _load_cluster_map()

    # prefix match (no BED fallback — fast)
    for pfx in _get_sorted_prefixes():
        if gene_id.lower().startswith(pfx.lower()):
            c = prefix_map[pfx]
            if _cluster_gene_cache is not None:
                _cluster_gene_cache[gene_id] = c
            return c

    # chromosome fallback
    if chrom_map:
        entry = _load_bed_map().get(gene_id)
        if entry:
            chrom = entry["chrom"]
            if chrom and chrom.lower() in chrom_map:
                c = chrom_map[chrom.lower()]
                if _cluster_gene_cache is not None:
                    _cluster_gene_cache[gene_id] = c
                return c

    if _cluster_gene_cache is not None:
        _cluster_gene_cache[gene_id] = None
    return None


# ---------------------------------------------------------------------------
# BED map
# ---------------------------------------------------------------------------

_bed_cache: Optional[dict] = None
_chrom_lists: Optional[dict] = None

def _load_bed_map() -> dict:
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

    # ---- Pre-build cluster cache for all genes (prefix-only, fast) ----
    global _cluster_gene_cache
    if _cluster_gene_cache is None:
        _cluster_gene_cache = {}
        prefix_map, _ = _load_cluster_map()
        sp = _get_sorted_prefixes()
        for gid in mp:
            for pfx in sp:
                if gid.lower().startswith(pfx.lower()):
                    _cluster_gene_cache[gid] = prefix_map[pfx]
                    break

    return mp


# ---------------------------------------------------------------------------
# Genomes listing
# ---------------------------------------------------------------------------

@router.get("/genomes")
def list_genomes():
    genomes: list[str] = []
    if BED_DIR.exists():
        seen = set()
        for entry in sorted(BED_DIR.iterdir()):
            fname = entry.name
            if not fname.endswith(".bed"):
                continue
            base = os.path.splitext(fname)[0]
            base = re.sub(r"\.filter$", "", base)
            parts = base.rsplit("_", 1)
            gn = parts[0] if len(parts) == 2 else base
            if gn not in seen:
                seen.add(gn)
                genomes.append(gn)
    return {"genomes": genomes}


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@router.get("/neighborhood")
def neighborhood(
    q: str = Query(..., description="Gene ID"),
    upstream: int = Query(10, ge=0, le=50),
    downstream: int = Query(10, ge=0, le=50),
    genome: str = Query("", description="Optional genome"),
    subgenome: str = Query("", description="Optional subgenome (A/B/D)"),
):
    gene_id = _clean(q)
    if not gene_id:
        return {"error": "Please provide a gene ID"}

    bc_map = _load_bed_map()  # triggers cache build on first call

    entry = bc_map.get(gene_id)
    if not entry:
        if genome and subgenome:
            return {"error": f"Gene '{gene_id}' not found in {genome}_{subgenome}"}
        return {"error": f"Gene '{gene_id}' not found in BED files"}

    query_cluster = _resolve_cluster(gene_id)
    if query_cluster is None:
        return {"error": f"Gene '{gene_id}' could not be assigned to a homoeologous cluster"}

    ggenome, gsub, gchrom = entry["genome"], entry["subgenome"], entry["chrom"]
    gpos = entry["start"]

    # ---- Build rows using cached cluster lookup (FAST, O(chrom_count)) ----
    rows: list[dict] = []
    cluster_chroms: set = set()  # (genome, subgenome, chrom) that contain query_cluster genes

    # First pass: find all chromosomes that have any gene in this cluster
    for key, glist in _chrom_lists.items():
        for _, gid in glist:  # check first few genes only for speed
            if _cluster_gene_cache.get(gid) == query_cluster:
                cluster_chroms.add(key)
                break

    # Ensure query chromosome is included
    q_key = (ggenome, gsub, gchrom)
    cluster_chroms.add(q_key)

    # Build rows (limit to top 30 for performance)
    for key in sorted(cluster_chroms)[:30]:
        gn, sg, ch = key
        glist = _chrom_lists.get(key)
        if not glist:
            continue
        is_query = (key == q_key)
        row = {"genome": gn, "subgenome": sg, "chrom": ch,
               "genes": [], "is_query_genome": is_query}

        if is_query:
            q_idx = next((i for i, (_, gid) in enumerate(glist) if gid == gene_id), 0)
            lo, hi = max(0, q_idx - upstream), min(len(glist), q_idx + downstream + 1)
        else:
            # Find cluster gene nearest to query position
            candidates = [(pos, gid) for pos, gid in glist
                          if _cluster_gene_cache.get(gid) == query_cluster]
            if not candidates:
                continue
            best = min(candidates, key=lambda x: abs(x[0] - gpos))
            c_idx = next(i for i, (p, _) in enumerate(glist) if p == best[0])
            lo, hi = max(0, c_idx - upstream), min(len(glist), c_idx + downstream + 1)

        for pos, gid in glist[lo:hi]:
            c = _cluster_gene_cache.get(gid)
            row["genes"].append({"gene_id": gid, "cluster": c, "start": pos,
                                 "is_query": gid == gene_id})
        rows.append(row)

    # ---- Connections ----
    cluster_connections: list[dict] = []
    for i, ra in enumerate(rows):
        for ga in ra["genes"]:
            if ga["cluster"] != query_cluster:
                continue
            for j, rb in enumerate(rows):
                if j <= i:
                    continue
                for gb in rb["genes"]:
                    if gb["cluster"] == query_cluster:
                        cluster_connections.append({
                            "from_gene": ga["gene_id"], "from_chrom": ra["chrom"],
                            "from_genome": ra["genome"],
                            "to_gene": gb["gene_id"], "to_chrom": rb["chrom"],
                            "to_genome": rb["genome"],
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
