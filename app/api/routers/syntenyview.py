"""SynTeny Viewer — port of col_orthe/app.py into FastAPI.

Path: /api/syntenyview/

Runs inside the existing FastAPI process (no separate Flask process needed).
All data files are loaded once at module import time in a background thread.
"""

import os
import re
import glob
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from fastapi import APIRouter, Query

from app.core.config import settings

router = APIRouter(prefix="/syntenyview", tags=["SynTeny Viewer"])

# ==================== Path configuration ====================
COL_BED_DIR  = "/var/www/html/col_bed"
RESULTS_DIR  = "/var/www/html/orthefind/Results_Jul24"
WD           = os.path.join(RESULTS_DIR, "WorkingDirectory")
CLUSTER_FILE = os.path.join(WD, "SpeciesIDs_cluster.txt")
OG_FILE      = os.path.join(RESULTS_DIR, "Orthogroups", "Orthogroups.txt")

TAB = chr(9)
NL  = chr(10)

BACKGROUND_WARMUP = True

_prefix_map = None
_chrom_map = None
_bed_gene = None
_chrom_lists = None
_gene2og = None
_og2genes = None
_cluster_cache = {}
_sorted_prefixes = None
_genomes_cache = None

_load_lock = threading.RLock()
_warmup_started = False
_load_status = {
    "state": "not_started",
    "message": "Full data have not been loaded.",
    "started_at": None,
    "finished_at": None,
    "error": None,
}


def _set_load_status(state, message="", error=None):
    _load_status["state"] = state
    _load_status["message"] = message
    if state == "loading" and _load_status["started_at"] is None:
        _load_status["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if state in ("ready", "error"):
        _load_status["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _load_status["error"] = error


def _mb_label(start, end):
    try:
        return "%.2f-%.2f Mb" % (float(start) / 1_000_000.0, float(end) / 1_000_000.0)
    except Exception:
        return ""


def _split_genome_sub(base):
    m = re.match(r"(.+)_([A-Za-z]\w*)$", base)
    return (m.group(1), m.group(2)) if m else (base, "")


def _genome_label_from_bed_path(path):
    base = re.sub(r"\.filter\.bed$|\.bed$", "", os.path.basename(path))
    genome, sub = _split_genome_sub(base)
    return f"{genome}_{sub}" if sub else genome


def _list_genomes_fast():
    global _genomes_cache
    if _genomes_cache is not None:
        return _genomes_cache
    if not os.path.isdir(COL_BED_DIR):
        return []
    labels = []
    for path in glob.glob(os.path.join(COL_BED_DIR, "*.bed")):
        labels.append(_genome_label_from_bed_path(path))
    _genomes_cache = sorted(set(labels))
    return _genomes_cache


def _load_cluster_map():
    global _prefix_map, _chrom_map
    with _load_lock:
        if _prefix_map is not None:
            return
        if not os.path.exists(CLUSTER_FILE):
            return
        prefix_map, chrom_map = {}, {}
        with open(CLUSTER_FILE, encoding="utf-8", errors="ignore") as f:
            next(f, None)
            for line in f:
                cols = line.rstrip(NL).rstrip(chr(13)).split(TAB)
                if len(cols) < 8:
                    continue
                for i in range(1, 8):
                    val = cols[i].strip()
                    if not val:
                        continue
                    if re.match(r"(?i)chr\d+[abd]", val):
                        chrom_map[val.lower()] = i
                    else:
                        prefix_map[val] = i
        _prefix_map, _chrom_map = prefix_map, chrom_map


def _load_bed():
    global _bed_gene, _chrom_lists
    with _load_lock:
        if _bed_gene is not None:
            return
        if not os.path.isdir(COL_BED_DIR):
            return
        bed_files = glob.glob(os.path.join(COL_BED_DIR, "*.bed"))
        if not bed_files:
            return
        bed_gene, tmp = {}, {}
        for path in bed_files:
            base = re.sub(r"\.filter\.bed$|\.bed$", "", os.path.basename(path))
            genome, sub = _split_genome_sub(base)
            with open(path, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    p = line.rstrip(NL).rstrip(chr(13)).split(TAB)
                    if len(p) < 4:
                        continue
                    try:
                        chrom, start, end, gid = p[0], int(p[1]), int(p[2]), p[3]
                    except ValueError:
                        continue
                    bed_gene[gid] = {
                        "chrom": chrom, "start": start, "end": end,
                        "genome": genome, "sub": sub,
                    }
                    if (genome, sub, chrom) not in tmp:
                        tmp[(genome, sub, chrom)] = []
                    tmp[(genome, sub, chrom)].append((start, gid))
        _bed_gene = bed_gene
        _chrom_lists = {k: sorted(v) for k, v in tmp.items()}


def _load_orthogroups():
    global _gene2og, _og2genes
    with _load_lock:
        if _gene2og is not None:
            return
        if not os.path.exists(OG_FILE):
            return
        gene2og, og2genes = {}, {}
        with open(OG_FILE, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if ":" not in line:
                    continue
                og, rest = line.split(":", 1)
                og = og.strip()
                genes = rest.split()
                og2genes[og] = genes
                for g in genes:
                    if g not in gene2og:
                        gene2og[g] = og
        _gene2og, _og2genes = gene2og, og2genes


def _ensure_loaded():
    if _bed_gene is not None and _gene2og is not None and _prefix_map is not None:
        return
    with _load_lock:
        if _bed_gene is not None and _gene2og is not None and _prefix_map is not None:
            return
        _set_load_status("loading", "Loading cluster map, BED files, and Orthogroups.")
        try:
            _load_cluster_map()
            _load_bed()
            _load_orthogroups()
            _set_load_status("ready",
                "BED genes=%d, OG=%d, prefixes=%d" %
                (len(_bed_gene or {}), len(_og2genes or {}), len(_prefix_map or {})))
        except Exception as e:
            _set_load_status("error", "Data loading failed.", repr(e))


def _warmup_full_data():
    try:
        _ensure_loaded()
    except Exception:
        pass


def _start_warmup_once():
    global _warmup_started
    if _warmup_started or not BACKGROUND_WARMUP:
        return
    _warmup_started = True
    th = threading.Thread(target=_warmup_full_data, name="synteny_warmup", daemon=True)
    th.start()


def _resolve_cluster(gene_id):
    if gene_id in _cluster_cache:
        return _cluster_cache[gene_id]
    global _sorted_prefixes
    if _sorted_prefixes is None:
        _sorted_prefixes = sorted((_prefix_map or {}).keys(), key=len, reverse=True)
    cl = None
    for pre in _sorted_prefixes:
        if gene_id.startswith(pre):
            cl = _prefix_map[pre]
            break
    if cl is None:
        info = (_bed_gene or {}).get(gene_id)
        if info:
            cl = (_chrom_map or {}).get(info["chrom"].lower())
    _cluster_cache[gene_id] = cl
    return cl


def _find_og(gid):
    if gid in _gene2og:
        return (gid, _gene2og[gid])
    alt = re.sub(r"\.\d+$", "", gid) if re.search(r"\.\d+$", gid) else gid + ".1"
    return (gid, _gene2og.get(alt))


# ---- Eager warm-up ----
_start_warmup_once()


# ---- FastAPI endpoints ----

@router.get("/genomes")
def api_genomes():
    return _list_genomes_fast()


@router.get("/status")
def api_status():
    return {
        "status": _load_status,
        "background_warmup": BACKGROUND_WARMUP,
        "genomes_cached": _genomes_cache is not None,
        "bed_loaded": _bed_gene is not None,
        "orthogroups_loaded": _gene2og is not None,
        "cluster_loaded": _prefix_map is not None,
        "bed_genes": len(_bed_gene) if _bed_gene else 0,
        "orthogroups": len(_og2genes) if _og2genes else 0,
        "prefixes": len(_prefix_map) if _prefix_map else 0,
        "og_file": OG_FILE,
    }


@router.get("/neighborhood")
def api_synteny(
    q: str = Query(..., description="Gene ID"),
    upstream: int = Query(5, ge=1, le=50),
    downstream: int = Query(5, ge=1, le=50),
    genome: str = Query("", description="Optional genome filter"),
    subgenome: str = Query("", description="Optional subgenome filter"),
):
    _ensure_loaded()

    gene_id = q.strip()
    if not gene_id:
        return {"error": "Missing gene parameter."}

    info = (_bed_gene or {}).get(gene_id)
    if not info:
        return {"error": "Gene was not found in BED: " + gene_id}

    key = (info["genome"], info["sub"], info["chrom"])
    gene_list = (_chrom_lists or {}).get(key, [])
    idx = next((i for i, (_, g) in enumerate(gene_list) if g == gene_id), None)
    if idx is None:
        return {"error": "Gene is not present in the chromosome list."}

    lo, hi = max(0, idx - 5), min(len(gene_list), idx + 6)
    neighbors = [g for _, g in gene_list[lo:hi]]

    with ThreadPoolExecutor(max_workers=min(11, max(1, len(neighbors)))) as ex:
        og_results = dict(ex.map(_find_og, neighbors))

    query_cluster = _resolve_cluster(gene_id)
    qkey = f"{info['genome']}_{info['sub']}" if info["sub"] else info["genome"]

    tracks = {}

    # Query track: exact BED neighborhood (±5 genes)
    query_track = {
        "label": qkey,
        "chrom": info["chrom"],
        "genes": [],
        "is_query_track": True,
    }
    for order, ng in enumerate(neighbors):
        ninfo = (_bed_gene or {}).get(ng)
        if not ninfo:
            continue
        og = og_results.get(ng)
        query_track["genes"].append({
            "gene": ng,
            "start": ninfo["start"],
            "end": ninfo["end"],
            "og": og,
            "order": order,
            "neighbor": ng,
            "is_query": ng == gene_id,
            "has_orthogroup": bool(og),
        })
    tracks[qkey] = query_track

    # Other genomes: only OG orthologs in the same cluster
    for order, ng in enumerate(neighbors):
        og = og_results.get(ng)
        if not og or og not in (_og2genes or {}):
            continue
        for hom in (_og2genes or {}).get(og, []):
            if hom not in (_bed_gene or {}):
                continue
            if _resolve_cluster(hom) != query_cluster:
                continue
            bi = _bed_gene[hom]
            gk = f"{bi['genome']}_{bi['sub']}" if bi["sub"] else bi["genome"]
            if gk == qkey:
                continue
            if gk not in tracks:
                tracks[gk] = {
                    "label": gk,
                    "chrom": bi["chrom"],
                    "genes": [],
                    "is_query_track": False,
                }
            tracks[gk]["genes"].append({
                "gene": hom,
                "start": bi["start"],
                "end": bi["end"],
                "og": og,
                "order": order,
                "neighbor": ng,
                "is_query": False,
                "has_orthogroup": True,
            })

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

    ordered = sorted(tracks.values(), key=lambda t: (0 if t["label"] == qkey else 1, t["label"]))

    link_groups = {}
    for ti, tr in enumerate(ordered):
        tr["track_index"] = ti
        for g in tr["genes"]:
            if not g.get("og"):
                continue
            k = "%s|%s" % (g["order"], g["og"])
            if k not in link_groups:
                link_groups[k] = {
                    "order": g["order"],
                    "og": g["og"],
                    "neighbor": g.get("neighbor", ""),
                    "points": [],
                }
            link_groups[k]["points"].append({
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
        "query_genome": qkey,
        "query_chrom": info["chrom"],
        "query_start": info["start"],
        "query_end": info["end"],
        "query_region_label": _mb_label(info["start"], info["end"]),
        "query_cluster": query_cluster,
        "neighbors": neighbors,
        "og_map": og_results,
        "tracks": ordered,
        "link_groups": list(link_groups.values()),
    }
