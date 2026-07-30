"""SynTeny Viewer — JCVI-style gene neighborhood synteny across homoeologous groups.

Reads BED files from /var/www/html/col_bed, resolves homoeologous cluster
membership via SpeciesIDs_cluster.txt.

Design:
  1. Query gene + 5 upstream + 5 downstream = 11 genes on the query chromosome.
  2. Resolve cluster for each of the 11 genes.
  3. For the query gene's cluster, find same-cluster orthologs across genomes.
  4. Frontend draws chromosome tracks with gene blocks and Bezier connections
     between same-cluster orthologs, focused on the query gene's cluster group.

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
# Cached cluster resolution
# ---------------------------------------------------------------------------

_cluster_gene_cache: Optional[dict] = None   # gene_id -> cluster (or None)

def _resolve_cluster(gene_id: str) -> Optional[int]:
    """Cached cluster resolution. First call builds cache via prefix-only match."""
    global _cluster_gene_cache
    if _cluster_gene_cache is not None and gene_id in _cluster_gene_cache:
        return _cluster_gene_cache[gene_id]

    gene_id = _clean(gene_id)
    prefix_map, chrom_map = _load_cluster_map()

    for pfx in _get_sorted_prefixes():
        if gene_id.lower().startswith(pfx.lower()):
            c = prefix_map[pfx]
            if _cluster_gene_cache is not None:
                _cluster_gene_cache[gene_id] = c
            return c

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

    # ---- Pre-build cluster cache for all genes ----
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
# Neighborhood API
# ---------------------------------------------------------------------------

@router.get("/neighborhood")
def neighborhood(
    q: str = Query(..., description="Gene ID"),
    upstream: int = Query(5, ge=1, le=50),
    downstream: int = Query(5, ge=1, le=50),
    genome: str = Query("", description="Optional genome filter"),
    subgenome: str = Query("", description="Optional subgenome filter (A/B/D)"),
):
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

    # ---- Step 1: 11 neighborhood genes on the query chromosome ----
    q_key = (ggenome, gsub, gchrom)
    glist = _chrom_lists.get(q_key, [])
    q_idx = next((i for i, (_, gid) in enumerate(glist) if gid == gene_id), 0)
    lo = max(0, q_idx - upstream)
    hi = min(len(glist), q_idx + downstream + 1)

    neighborhood_genes: list[dict] = []
    for pos, gid in glist[lo:hi]:
        c = _cluster_gene_cache.get(gid)
        neighborhood_genes.append({
            "gene_id": gid, "cluster": c, "start": pos,
            "is_query": gid == gene_id,
        })

    # ---- Step 2: find same-cluster orthologs in OTHER genomes ----
    # For each neighborhood gene in the query cluster, find its orthologs
    # in other genome+subgenome combinations.
    # Build: { (genome, subgenome, chrom): [(ortholog_gene, pos), ...] }

    query_cluster_genes = [ng for ng in neighborhood_genes if ng["cluster"] == query_cluster]
    ortholog_map: dict[tuple, list] = {}  # (genome, subgenome, chrom) -> [(gid, pos), ...]

    for key, gl in _chrom_lists.items():
        gn, sg, ch = key
        if (gn, sg) == (ggenome, gsub) and ch == gchrom:
            continue  # skip query chromosome itself
        # Check if this chromosome has any query_cluster genes
        has_cluster = False
        for _, gid in gl:
            if _cluster_gene_cache.get(gid) == query_cluster:
                has_cluster = True
                break
        if not has_cluster:
            continue
        # Collect all query_cluster genes on this chromosome
        cluster_genes_on_chrom = [(pos, gid) for pos, gid in gl
                                   if _cluster_gene_cache.get(gid) == query_cluster]
        ortholog_map[key] = cluster_genes_on_chrom

    # ---- Step 3: Build tracks ----
    # Query track: shows the 11 neighborhood genes
    tracks: list[dict] = []

    # Query genome track
    query_genes = []
    for ng in neighborhood_genes:
        query_genes.append({
            "gene_id": ng["gene_id"], "cluster": ng["cluster"],
            "start": ng["start"], "is_query": ng["is_query"],
        })
    tracks.append({
        "genome": ggenome, "subgenome": gsub, "chrom": gchrom,
        "is_query_genome": True,
        "genes": query_genes,
    })

    # Same-genome other subgenomes: show orthologous chromosome regions
    # e.g., for AK58_A chr1A, also show AK58_B chr1B and AK58_D chr1D
    same_genome_keys = sorted(
        [k for k in ortholog_map if k[0] == ggenome],
        key=lambda k: k[2]  # sort by chrom
    )
    for key in same_genome_keys:
        gn, sg, ch = key
        og_list = ortholog_map[key]
        gl = _chrom_lists.get(key, [])
        if not gl or not og_list:
            continue
        # Show region around the best-match ortholog (closest position to query gene)
        best = min(og_list, key=lambda x: abs(x[0] - gpos))
        best_idx = next((i for i, (p, _) in enumerate(gl) if p == best[0]), 0)
        rlo = max(0, best_idx - upstream)
        rhi = min(len(gl), best_idx + downstream + 1)
        genes = []
        for pos, gid in gl[rlo:rhi]:
            c = _cluster_gene_cache.get(gid)
            genes.append({"gene_id": gid, "cluster": c, "start": pos,
                          "is_query": False})
        tracks.append({
            "genome": gn, "subgenome": sg, "chrom": ch,
            "is_query_genome": False,
            "genes": genes,
        })

    # Other genomes: add one track per distinct genome (pick first subgenome+chrom found)
    other_genomes: dict[str, list] = {}  # genome_name -> list of (key, og_list)
    for key in sorted(ortholog_map.keys()):
        gn = key[0]
        if gn == ggenome:
            continue
        if gn not in other_genomes:
            other_genomes[gn] = []
        other_genomes[gn].append((key, ortholog_map[key]))

    for gn, entries in other_genomes.items():
        # Pick the entry with the closest ortholog to gpos
        best_entry = None
        best_dist = float("inf")
        for key, og_list in entries:
            best_og = min(og_list, key=lambda x: abs(x[0] - gpos))
            dist = abs(best_og[0] - gpos)
            if dist < best_dist:
                best_dist = dist
                best_entry = (key, og_list, best_og)
        if best_entry is None:
            continue
        key, og_list, best_og = best_entry
        gn, sg, ch = key
        gl = _chrom_lists.get(key, [])
        if not gl:
            continue
        best_idx = next((i for i, (p, _) in enumerate(gl) if p == best_og[0]), 0)
        rlo = max(0, best_idx - upstream)
        rhi = min(len(gl), best_idx + downstream + 1)
        genes = []
        for pos, gid in gl[rlo:rhi]:
            c = _cluster_gene_cache.get(gid)
            genes.append({"gene_id": gid, "cluster": c, "start": pos,
                          "is_query": False})
        tracks.append({
            "genome": gn, "subgenome": sg, "chrom": ch,
            "is_query_genome": False,
            "genes": genes,
        })

    # ---- Step 4: Build connections ----
    # Connect each query-cluster gene in the query track to its nearest
    # same-cluster ortholog on each other track
    connections: list[dict] = []

    # Index gene positions across all tracks for connection lookup
    track_gene_map: dict[str, dict] = {}  # gene_id -> {track_idx, pos, ...}
    for ti, t in enumerate(tracks):
        for g in t["genes"]:
            track_gene_map[g["gene_id"]] = {
                "track_idx": ti, "pos": g["start"],
                "genome": t["genome"], "subgenome": t["subgenome"],
                "chrom": t["chrom"],
            }

    # Build per-track list of query-cluster genes for fast lookup
    track_cluster_genes: dict[int, list] = {}
    for ti, t in enumerate(tracks):
        track_cluster_genes[ti] = [
            g for g in t["genes"] if g["cluster"] == query_cluster
        ]

    # For each query-cluster gene in the query track, connect to best matches
    query_cluster_in_track0 = track_cluster_genes.get(0, [])
    for other_ti in range(1, len(tracks)):
        other_cluster_genes = track_cluster_genes.get(other_ti, [])
        if not other_cluster_genes:
            continue
        t = tracks[other_ti]
        # For each query-track cluster gene, find nearest ortholog on this other track
        for qg in query_cluster_in_track0:
            qpos = qg["start"]
            best_og = min(other_cluster_genes, key=lambda og: abs(og["start"] - qpos))
            connections.append({
                "from_gene": qg["gene_id"],
                "from_genome": ggenome,
                "from_subgenome": gsub,
                "from_chrom": gchrom,
                "from_start": qpos,
                "to_gene": best_og["gene_id"],
                "to_genome": t["genome"],
                "to_subgenome": t["subgenome"],
                "to_chrom": t["chrom"],
                "to_start": best_og["start"],
                "cluster": query_cluster,
            })

    return {
        "query": gene_id,
        "query_cluster": query_cluster,
        "query_genome": ggenome,
        "query_subgenome": gsub,
        "query_chrom": gchrom,
        "tracks": tracks,
        "connections": connections,
    }
