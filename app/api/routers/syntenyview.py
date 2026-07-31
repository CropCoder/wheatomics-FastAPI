"""SynTeny Viewer — OG-based neighborhood synteny across homoeologous groups.

Based on the col_orthe/app.py architecture:
  1. Query gene + 5 upstream + 5 downstream = 11 neighborhood genes.
  2. Parallel OG lookup (ThreadPoolExecutor) for all 11 genes.
  3. For each OG, filter members by query cluster + BED presence.
  4. Build tracks grouped by (genome_subgenome), with region Mb labels.
  5. Build link_groups for pairwise connections between adjacent tracks
     sharing the same (order, OG) pair.

The frontend index.html renders a JCVI-style plot entirely client-side
from the JSON returned here.
"""

import os
import re
from concurrent.futures import ThreadPoolExecutor
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


def _mb_label(start, end):
    try:
        return "%.2f-%.2f Mb" % (float(start) / 1_000_000.0, float(end) / 1_000_000.0)
    except Exception:
        return ""


# =========================================================================
# Cluster map  (SpeciesIDs_cluster.txt)
# =========================================================================

_cluster_cache: Optional[Tuple] = None
_sorted_prefixes: Optional[List] = None


def _load_cluster_map() -> Tuple[Dict, Dict]:
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

_cluster_gene_cache: Optional[Dict] = None


def _resolve_cluster(gene_id: str) -> Optional[int]:
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
                if key not in cl:
                    cl[key] = []
                cl[key].append((s, gid))
        except Exception:
            continue

    for k in cl:
        cl[k].sort(key=lambda x: x[0])
    _bed_cache = mp
    _chrom_lists = cl

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
# OrthoGroups.txt
# =========================================================================

_orthogroups_cache: Optional[Dict] = None
_gene_to_og_cache: Optional[Dict] = None


def _orthogroups_file() -> Path:
    base = ORTHOFINDER_BASE_DIR
    for p in [base / "Orthogroups" / "Orthogroups.txt",
              base / "WorkingDirectory" / "Orthogroups.txt",
              base.parent / "Orthogroups" / "Orthogroups.txt"]:
        if p.exists():
            return p
    return base / "Orthogroups" / "Orthogroups.txt"


def _load_orthogroups() -> Dict:
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
    _load_orthogroups()
    og_id = _gene_to_og_cache.get(gene_id)
    if og_id:
        return og_id
    # Try version-suffixed/unsuffixed variants
    if not re.search(r"\.\d+$", gene_id):
        return _gene_to_og_cache.get(gene_id + ".1")
    else:
        return _gene_to_og_cache.get(re.sub(r"\.\d+$", "", gene_id))


# =========================================================================
# Eager cache warm-up
# =========================================================================

import threading


def _warm():
    try:
        _load_bed_map()
    except Exception:
        pass


_thread = threading.Thread(target=_warm, daemon=True)
_thread.start()


# =========================================================================
# Genomes listing
# =========================================================================

@router.get("/genomes")
def list_genomes():
    """Return genome labels from BED filenames (fast, no file content read)."""
    labels: List[str] = []
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
            sub = parts[1] if len(parts) == 2 and parts[1] in ("A", "B", "D") else ""
            label = f"{gn}_{sub}" if sub else gn
            if label not in seen:
                seen.add(label)
                labels.append(label)
    return {"genomes": sorted(labels)}


# =========================================================================
# Neighborhood API
# =========================================================================

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
    _load_orthogroups()

    entry = bc_map.get(gene_id)
    if not entry:
        return {"error": f"Gene '{gene_id}' not found in BED files"}

    query_cluster = _resolve_cluster(gene_id)
    if query_cluster is None:
        return {"error": f"Gene '{gene_id}' not assigned to a homoeologous cluster"}

    ggenome = entry["genome"]
    gsub = entry["subgenome"]
    gchrom = entry["chrom"]
    gpos = entry["start"]

    # ---- Step 1: 11 neighborhood genes ---------------------------------
    q_key = (ggenome, gsub, gchrom)
    glist = _chrom_lists.get(q_key, [])
    q_idx = next((i for i, (_, gid) in enumerate(glist) if gid == gene_id), 0)
    lo = max(0, q_idx - upstream)
    hi = min(len(glist), q_idx + downstream + 1)

    neighbors: List[str] = []
    for pos, gid in glist[lo:hi]:
        neighbors.append(gid)

    # ---- Step 2: Parallel OG lookup for all 11 neighbors ---------------
    with ThreadPoolExecutor(max_workers=min(11, max(1, len(neighbors)))) as ex:
        og_results = dict(ex.map(_find_og_for_gene, neighbors))

    # ---- Step 3: Build tracks from OG orthologs ------------------------
    # tracks: {genome_subgenome: {label, chrom, genes: [...]}}
    tracks: Dict[str, dict] = {}

    for order, ng in enumerate(neighbors):
        og_id = og_results.get(ng)
        if not og_id or og_id not in _orthogroups_cache:
            continue

        for hom in _orthogroups_cache[og_id]:
            if hom not in bc_map:
                continue
            if _cluster_gene_cache.get(hom) != query_cluster:
                continue

            bi = bc_map[hom]
            tk = f"{bi['genome']}_{bi['subgenome']}" if bi["subgenome"] else bi["genome"]

            if tk not in tracks:
                tracks[tk] = {
                    "label": tk,
                    "chrom": bi["chrom"],
                    "genes": [],
                }
            tracks[tk]["genes"].append({
                "gene": hom,
                "start": bi["start"],
                "end": bi["end"],
                "og": og_id,
                "order": order,
                "neighbor": ng,
                "is_query": hom == gene_id,
            })

    # Sort genes per track + compute region stats
    for tr in tracks.values():
        tr["genes"].sort(key=lambda x: (x["start"], x["end"], x["gene"]))
        starts = [g["start"] for g in tr["genes"]]
        ends = [g["end"] for g in tr["genes"]]
        if starts and ends:
            tr["region_start"] = min(starts)
            tr["region_end"] = max(ends)
            tr["region_label"] = _mb_label(tr["region_start"], tr["region_end"])
        else:
            tr["region_start"] = None
            tr["region_end"] = None
            tr["region_label"] = ""

    # Sort tracks: query genome first, then alphabetically
    qlabel = f"{ggenome}_{gsub}" if gsub else ggenome
    ordered = sorted(tracks.values(), key=lambda t: (0 if t["label"] == qlabel else 1, t["label"]))
    for ti, tr in enumerate(ordered):
        tr["track_index"] = ti

    # ---- Step 4: Build link_groups (pairwise connections) ---------------
    # Group by (order, og) — genes that share the same neighborhood gene and OG
    link_groups: Dict[str, dict] = {}
    for ti, tr in enumerate(ordered):
        for g in tr["genes"]:
            key = "%s|%s" % (g["order"], g["og"])
            if key not in link_groups:
                link_groups[key] = {
                    "order": g["order"],
                    "og": g["og"],
                    "neighbor": g.get("neighbor", ""),
                    "points": [],
                }
            link_groups[key]["points"].append({
                "track_index": ti,
                "track_label": tr["label"],
                "chrom": tr["chrom"],
                "gene": g["gene"],
                "start": g["start"],
                "end": g["end"],
            })

    return {
        "query": gene_id,
        "request_genome": genome,
        "query_genome": qlabel,
        "query_chrom": gchrom,
        "query_start": gpos,
        "query_end": entry["end"],
        "query_region_label": _mb_label(gpos, entry["end"]),
        "query_cluster": query_cluster,
        "neighbors": neighbors,
        "og_map": og_results,
        "tracks": ordered,
        "link_groups": list(link_groups.values()),
    }
