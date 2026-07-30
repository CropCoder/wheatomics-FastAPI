"""SynTeny Viewer — JCVI-style gene neighborhood synteny across homoeologous groups.

Reads BED files from /var/www/html/col_bed, resolves homoeologous cluster
membership via SpeciesIDs_cluster.txt, and finds orthologs via Orthogroups.txt.

Design:
  1. Query gene + 5 upstream + 5 downstream = 11 genes on the query chromosome.
  2. Resolve cluster (1-7) for each of the 11 genes.
  3. For the 11 neighborhood genes, look up their OrthoFinder OG (O(1) dict
     lookup per gene), then collect all OG members that are in the query cluster.
     Same speed as searching 1 gene — ~100ms after caches are warm.
  4. Return one track per (genome, subgenome, chrom) that has query-cluster
     orthologs, each showing the syntenic region (~11 genes).
  5. Frontend draws JCVI-style tracks with Bezier connections.

PERFORMANCE:
  - BED index, cluster cache, and OrthoFinder OG cache are built once.
  - Per-request: 11 dict lookups → union OG members → BED lookup.
  - No chromosome scanning; no cross-product of 94 genomes.
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
ORTHOFINDER_BASE_DIR = settings.ORTHOFINDER_BASE_DIR

_WS = " \t\n\r\x00\x0b'\""


def _clean(s: str) -> str:
    return str(s).strip(_WS)


# =========================================================================
# Cluster map  (SpeciesIDs_cluster.txt)
# =========================================================================

_cluster_cache: Optional[Tuple] = None
_sorted_prefixes: Optional[List] = None


def _load_cluster_map() -> Tuple[Dict, Dict]:
    """Return (prefix_map, chrom_map) mapping gene prefixes / chromosomes
    to homoeologous clusters 1-7."""
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


# =========================================================================
# Cached cluster resolution
# =========================================================================

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


# =========================================================================
# BED map
# =========================================================================

_bed_cache: Optional[Dict] = None
_chrom_lists: Optional[Dict] = None


def _load_bed_map() -> Dict:
    """Load all *.bed files into gene_id -> {chrom, start, end, genome, subgenome}
    plus _chrom_lists: (genome, subgenome, chrom) -> [(start, gene_id), ...]."""
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

    # Pre-build per-gene cluster cache
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


# =========================================================================
# OrthoGroups.txt — cached dict: {gene_id: og_id}, {og_id: [gene_id, ...]}
# =========================================================================

_orthogroups_cache: Optional[Dict] = None   # {og_id: [gene_id, ...]}
_gene_to_og_cache: Optional[Dict] = None    # {gene_id: og_id}


def _orthogroups_file() -> Path:
    base = ORTHOFINDER_BASE_DIR
    for p in [base / "Orthogroups" / "Orthogroups.txt",
              base / "WorkingDirectory" / "Orthogroups.txt",
              base.parent / "Orthogroups" / "Orthogroups.txt"]:
        if p.exists():
            return p
    return base / "Orthogroups" / "Orthogroups.txt"


def _load_orthogroups() -> Dict:
    """Parse Orthogroups.txt. Builds gene->OG and OG->genes indices."""
    global _orthogroups_cache, _gene_to_og_cache
    if _orthogroups_cache is not None:
        return _orthogroups_cache

    mp: Dict = {}
    g2og: Dict = {}
    f = _orthogroups_file()
    if f.exists():
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            og_id, genes_str = line.split(":", 1)
            og_id = _clean(og_id)
            genes = [_clean(g) for g in genes_str.strip().split() if _clean(g)]
            mp[og_id] = genes
            for g in genes:
                if g not in g2og:
                    g2og[g] = og_id
    _orthogroups_cache = mp
    _gene_to_og_cache = g2og
    return mp


def _find_og_for_gene(gene_id: str) -> Optional[str]:
    """O(1) dict lookup — sub-millisecond."""
    _load_orthogroups()
    return _gene_to_og_cache.get(gene_id)


# =========================================================================
# Eager cache warm-up — avoid first-request timeout
# =========================================================================

import threading


def _warm_bed_cache():
    try:
        _load_bed_map()
    except Exception:
        pass


_warm_thread = threading.Thread(target=_warm_bed_cache, daemon=True)
_warm_thread.start()


# =========================================================================
# Genomes listing
# =========================================================================

@router.get("/genomes")
def list_genomes():
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


# =========================================================================
# Neighborhood API — the core synteny endpoint
# =========================================================================

_SUBGENOME_ORDER = {"A": 0, "B": 1, "D": 2}


def _sort_key(key: Tuple[str, str, str], qgenome: str) -> Tuple:
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
    _load_orthogroups()  # ensure OG cache is warm

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

    # ---- Step 2: OG-based ortholog lookup — O(1) per gene, fast! ----
    # For each neighborhood gene, look up its OG, collect all OG members.
    # Filter to only genes that: (a) are in the BED index,
    # (b) belong to the query cluster.

    og_genes: Set[str] = set()
    for ng in neighborhood_genes:
        gid = ng["gene_id"]
        og_id = _find_og_for_gene(gid)
        if og_id and og_id in _orthogroups_cache:
            og_genes.update(_orthogroups_cache[og_id])
        # Also try version-suffixed form (e.g. "gene" -> "gene.1")
        if not re.search(r"\.\d+$", gid):
            og_id_v = _find_og_for_gene(gid + ".1")
            if og_id_v and og_id_v in _orthogroups_cache:
                og_genes.update(_orthogroups_cache[og_id_v])

    # Filter to only genes in BED + same cluster
    ortholog_genes: List[str] = []
    for og_gid in og_genes:
        if og_gid in bc_map and _cluster_gene_cache.get(og_gid) == query_cluster:
            ortholog_genes.append(og_gid)

    # ---- Step 3: Group orthologs by (genome, subgenome, chrom) ---------
    ortholog_map: Dict[Tuple, List] = {}

    for og_gid in ortholog_genes:
        be = bc_map[og_gid]
        key = (be["genome"], be["subgenome"], be["chrom"])
        if (be["genome"], be["subgenome"]) == (ggenome, gsub) and be["chrom"] == gchrom:
            continue
        ortholog_map.setdefault(key, []).append((be["start"], og_gid))

    for key in ortholog_map:
        ortholog_map[key].sort(key=lambda x: x[0])

    # ---- Step 4: Build tracks -------------------------------------------
    tracks: List[Dict] = []

    # 4a. Query genome track
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

    # 4b. All other tracks
    sorted_keys = sorted(ortholog_map.keys(), key=lambda k: _sort_key(k, ggenome))

    for key in sorted_keys:
        gn, sg, ch = key
        og_list = ortholog_map[key]
        gl = _chrom_lists.get(key, [])
        if not gl or not og_list:
            continue

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

    # ---- Step 5: Build connections --------------------------------------
    connections: List[Dict] = []

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
