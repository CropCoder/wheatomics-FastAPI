"""SynTeny Viewer — JCVI-style gene neighborhood synteny across homoeologous groups.

Reads BED files from /var/www/html/col_bed, resolves homoeologous cluster
membership via SpeciesIDs_cluster.txt.

Design:
  1. Query gene + 5 upstream + 5 downstream = 11 genes on the query chromosome.
  2. Resolve cluster for each of the 11 genes.
  3. Find the query gene's cluster group (1-7), then find ALL (genome, subgenome,
     chrom) across the dataset that have genes in that same cluster.
  4. Return one track per (genome, subgenome, chrom), with the orthologous
     region (~11 genes) around the best-matching ortholog.
  5. Frontend draws chromosome tracks with gene blocks and Bezier connections
     between same-cluster orthologs.

PERFORMANCE: Cluster resolution is cached globally (_cluster_gene_cache).
First request builds the cache by scanning all BED genes once (~5-10s),
subsequent requests are sub-second.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, Query

from app.core.config import settings

router = APIRouter(prefix="/syntenyview", tags=["SynTeny Viewer"])

BED_DIR = Path("/var/www/html/col_bed")
CLUSTER_FILE = settings.ORTHOFINDER_CLUSTER_FILE

_WS = " \t\n\r\x00\x0b'\""


def _clean(s: str) -> str:
    return str(s).strip(_WS)


# ---------------------------------------------------------------------------
# Cluster map  (SpeciesIDs_cluster.txt)
# ---------------------------------------------------------------------------

_cluster_cache: Optional[Tuple] = None
_sorted_prefixes: Optional[List] = None


def _load_cluster_map() -> Tuple[Dict, Dict]:
    """Return (prefix_map, chrom_map) mapping gene prefixes / chromosomes to
    homoeologous clusters 1-7."""
    global _cluster_cache
    if _cluster_cache is not None:
        return _cluster_cache
    prefix_map: Dict[str, int] = {}
    chrom_map: Dict[str, int] = {}
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


def _get_sorted_prefixes() -> List:
    global _sorted_prefixes
    if _sorted_prefixes is not None:
        return _sorted_prefixes
    prefix_map, _ = _load_cluster_map()
    _sorted_prefixes = sorted(prefix_map.keys(), key=lambda x: -len(x))
    return _sorted_prefixes


# ---------------------------------------------------------------------------
# Cached cluster resolution
# ---------------------------------------------------------------------------

_cluster_gene_cache: Optional[Dict] = None  # gene_id -> cluster (or None)


def _resolve_cluster(gene_id: str) -> Optional[int]:
    """Map a gene_id to its homoeologous cluster (1-7), cached."""
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

_bed_cache: Optional[Dict] = None
_chrom_lists: Optional[Dict] = None


def _load_bed_map() -> Dict:
    """Load all *.bed files into gene_id -> {chrom, start, end, genome, subgenome}
    plus a secondary index _chrom_lists: (genome, subgenome, chrom) -> [(start, gene_id), ...].

    Also pre-builds the per-gene cluster cache in one pass.
    """
    global _bed_cache, _chrom_lists
    if _bed_cache is not None:
        return _bed_cache

    mp: Dict = {}
    cl: Dict = {}
    if not BED_DIR.exists():
        _bed_cache = mp
        _chrom_lists = cl
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

    # Pre-build cluster cache for every gene
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
# Eager cache warm-up — avoids first-request timeout
# ---------------------------------------------------------------------------

import threading


def _warm_bed_cache():
    """Build the BED + cluster cache in a background thread so the first
    real request doesn't hit the Apache 60s ProxyTimeout."""
    try:
        _load_bed_map()
    except Exception:
        pass  # will retry on first request


_warm_thread = threading.Thread(target=_warm_bed_cache, daemon=True)
_warm_thread.start()


# ---------------------------------------------------------------------------
# Genomes listing
# ---------------------------------------------------------------------------

@router.get("/genomes")
def list_genomes():
    """Return the list of genome names discovered in the BED directory."""
    genomes: List[str] = []
    if BED_DIR.exists():
        seen: Set[str] = set()
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
# Neighborhood API  — the core synteny endpoint
# ---------------------------------------------------------------------------

_SUBGENOME_ORDER = {"A": 0, "B": 1, "D": 2}


def _sort_key(key: Tuple[str, str, str], qgenome: str) -> Tuple:
    """Sort tracks: query genome first (by subgenome A/B/D), then other
    genomes alphabetically by genome name then subgenome."""
    gn, sg, ch = key
    if gn == qgenome:
        return (0, _SUBGENOME_ORDER.get(sg, 99), gn, sg, ch)
    return (1, 0, gn.lower(), _SUBGENOME_ORDER.get(sg, 99), ch)


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

    ggenome = entry["genome"]
    gsub = entry["subgenome"]
    gchrom = entry["chrom"]
    gpos = entry["start"]

    # ---- Step 1: 11 neighborhood genes on the query chromosome ----------
    q_key = (ggenome, gsub, gchrom)
    glist = _chrom_lists.get(q_key, [])
    q_idx = next((i for i, (_, gid) in enumerate(glist) if gid == gene_id), 0)
    lo = max(0, q_idx - upstream)
    hi = min(len(glist), q_idx + downstream + 1)

    neighborhood_genes: List[Dict] = []
    for pos, gid in glist[lo:hi]:
        c = _cluster_gene_cache.get(gid)
        neighborhood_genes.append({
            "gene_id": gid, "cluster": c, "start": pos,
            "is_query": gid == gene_id,
        })

    # ---- Step 2: find ALL chromosomes that have query_cluster genes -----
    # ortholog_map: (genome, subgenome, chrom) -> [(pos, gene_id), ...]
    ortholog_map: Dict[Tuple, List] = {}

    for key, gl in _chrom_lists.items():
        gn, sg, ch = key
        if (gn, sg) == (ggenome, gsub) and ch == gchrom:
            continue  # skip query chromosome (handled above)
        cluster_genes = [(pos, gid) for pos, gid in gl
                         if _cluster_gene_cache.get(gid) == query_cluster]
        if cluster_genes:
            ortholog_map[key] = cluster_genes

    # ---- Step 3: Build tracks — one per (genome, subgenome, chrom) -----
    tracks: List[Dict] = []

    # 3a. Query genome track
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

    # 3b. All other tracks — sorted: same-genome subgenomes first, then
    #     other genomes alphabetically by genome name / subgenome.
    sorted_keys = sorted(ortholog_map.keys(),
                         key=lambda k: _sort_key(k, ggenome))

    for key in sorted_keys:
        gn, sg, ch = key
        og_list = ortholog_map[key]
        gl = _chrom_lists.get(key, [])
        if not gl or not og_list:
            continue

        # Show the region around the ortholog closest to query position
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

    # ---- Step 4: Build connections -------------------------------------
    # For each query-cluster gene in the query track, connect to its
    # nearest ortholog (by position) on each other track.
    connections: List[Dict] = []

    # Query-track cluster genes
    query_cluster_genes = [g for g in tracks[0]["genes"]
                           if g["cluster"] == query_cluster]

    for other_ti in range(1, len(tracks)):
        t = tracks[other_ti]
        other_cluster_genes = [g for g in t["genes"]
                               if g["cluster"] == query_cluster]
        if not other_cluster_genes:
            continue

        for qg in query_cluster_genes:
            qpos = qg["start"]
            best_og = min(other_cluster_genes,
                          key=lambda og: abs(og["start"] - qpos))
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
