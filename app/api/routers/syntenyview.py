"""SynTeny Viewer — port of col_orthe/app.py into FastAPI.

Path: /api/syntenyview/

Runs inside the existing FastAPI process (no separate Flask process needed).
All data files are loaded once at module import time in a background thread.

Key features:
- Reference-genome-aware query gene resolution (handles duplicated gene IDs across BED files).
- Gene ID cluster extraction (BJ81D040500.1 → group 1) with strict subgenome validation.
- Target tracks are subgenome-strict: a target ending with _A/_B/_D only accepts matching homologs.
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
_bed_gene = None                 # Legacy canonical map: gene_id -> first observed BED record.
_bed_gene_entries = None         # Robust map: gene_id -> [BED records from all files].
_bed_gene_by_genome = None       # Robust map: genome_label -> {gene_id -> BED record}.
_chrom_lists = None              # (genome, sub, chrom) -> [(start, gene_id)].
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


def _genome_label(genome, sub):
    return f"{genome}_{sub}" if sub else genome


def _genome_label_from_bed_path(path):
    base = re.sub(r"\.filter\.bed$|\.bed$", "", os.path.basename(path))
    genome, sub = _split_genome_sub(base)
    return _genome_label(genome, sub)


def _list_genomes_fast():
    """Build the genome list from BED filenames only."""
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
                    if re.match(r"(?i)chr\d+[abd]", val) or re.match(r"(?i)^\d+[abd]$", val):
                        chrom_map[val.lower()] = i
                        chrom_map[val.lower().replace("chr", "")] = i
                    else:
                        prefix_map[val] = i
        _prefix_map, _chrom_map = prefix_map, chrom_map


def _load_bed():
    global _bed_gene, _bed_gene_entries, _bed_gene_by_genome, _chrom_lists
    with _load_lock:
        if _bed_gene is not None:
            return
        if not os.path.isdir(COL_BED_DIR):
            return
        bed_files = glob.glob(os.path.join(COL_BED_DIR, "*.bed"))
        if not bed_files:
            return
        bed_gene, entries, by_genome, tmp = {}, {}, {}, {}
        for path in sorted(bed_files):
            base = re.sub(r"\.filter\.bed$|\.bed$", "", os.path.basename(path))
            genome, sub = _split_genome_sub(base)
            label = _genome_label(genome, sub)
            with open(path, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    p = line.rstrip(NL).rstrip(chr(13)).split(TAB)
                    if len(p) < 4:
                        continue
                    try:
                        chrom, start, end, gid = p[0], int(p[1]), int(p[2]), p[3]
                    except ValueError:
                        continue
                    rec = {
                        "chrom": chrom, "start": start, "end": end,
                        "genome": genome, "sub": sub, "label": label,
                        "bed_file": os.path.basename(path),
                    }
                    bed_gene.setdefault(gid, rec)
                    entries.setdefault(gid, []).append(rec)
                    by_genome.setdefault(label, {})[gid] = rec
                    by_genome.setdefault(genome, {})[gid] = rec
                    tmp.setdefault((genome, sub, chrom), []).append((start, gid))
        _bed_gene = bed_gene
        _bed_gene_entries = entries
        _bed_gene_by_genome = by_genome
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
                "BED genes=%d, BED entries=%d, OG=%d, prefixes=%d" %
                (len(_bed_gene or {}),
                 sum(len(v) for v in (_bed_gene_entries or {}).values()),
                 len(_og2genes or {}), len(_prefix_map or {})))
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


def _find_og(gid):
    if gid in _gene2og:
        return (gid, _gene2og[gid])
    alt = re.sub(r"\.\d+$", "", gid) if re.search(r"\.\d+$", gid) else gid + ".1"
    return (gid, _gene2og.get(alt))


# ==================== Gene ID / chromosome analysis ====================

def _strip_version(gid):
    return re.sub(r"\.\d+$", "", gid or "")


def _gene_id_cluster(gid):
    """Extract the chromosome group from wheat gene IDs.

    Examples: BJ81D040500.1 -> 1, Abo1A000100.1 -> 1, XXX4A012340 -> 4.
    """
    g = _strip_version(gid)
    m = re.search(r"(?i)([1-7])([abd])(?=\d{3,})", g)
    if m:
        return int(m.group(1))
    m = re.search(r"(?i)(?:^|[^0-9])([1-7])([abd])(?=\d)", g)
    if m:
        return int(m.group(1))
    return None


def _gene_id_subgenome(gid):
    """Extract A/B/D subgenome from a wheat gene ID."""
    g = _strip_version(gid)
    m = re.search(r"(?i)([1-7])([abd])(?=\d{3,})", g)
    if m:
        return m.group(2).upper()
    m = re.search(r"(?i)(?:^|[^0-9])([1-7])([abd])(?=\d)", g)
    if m:
        return m.group(2).upper()
    return None


def _chrom_cluster(chrom):
    if not chrom:
        return None
    c = str(chrom).strip().lower()
    if c in (_chrom_map or {}):
        return (_chrom_map or {}).get(c)
    c2 = c.replace("chr", "")
    if c2 in (_chrom_map or {}):
        return (_chrom_map or {}).get(c2)
    m = re.search(r"(?i)(?:chr)?([1-7])\s*([abd])\b", str(chrom))
    if m:
        return int(m.group(1))
    return None


def _chrom_subgenome(chrom):
    """Return A/B/D from chromosome names such as chr1A, 1D, chr4B."""
    if not chrom:
        return None
    m = re.search(r"(?i)(?:chr)?[1-7]\s*([abd])\b", str(chrom).strip())
    return m.group(1).upper() if m else None


def _label_subgenome(label):
    """Return A/B/D/H/etc. from a genome label suffix such as BJ8_A."""
    if not label or "_" not in str(label):
        return None
    sub = str(label).rsplit("_", 1)[1].strip().upper()
    return sub or None


def _is_abd_subgenome(sub):
    return str(sub or "").upper() in {"A", "B", "D"}


def _record_matches_query_and_target(hom_gene, rec, query_cluster, target_label):
    """Strict homolog validation for target track placement.

    Ensures that a target track ending with _A does not receive D-subgenome genes.
    Gene ID subgenome is treated as the strongest clue.
    """
    gene_cl = _gene_id_cluster(hom_gene)
    gene_sub = _gene_id_subgenome(hom_gene)
    chrom_cl = _chrom_cluster((rec or {}).get("chrom"))
    chrom_sub = _chrom_subgenome((rec or {}).get("chrom"))
    target_sub = _label_subgenome(target_label)

    if query_cluster is not None:
        if gene_cl is not None and gene_cl != query_cluster:
            return False, "gene_group_mismatch"
        if gene_cl is None and chrom_cl is not None and chrom_cl != query_cluster:
            return False, "chrom_group_mismatch"

    if gene_cl is not None and chrom_cl is not None and gene_cl != chrom_cl:
        return False, "gene_chrom_group_conflict"

    if _is_abd_subgenome(target_sub):
        if gene_sub is not None and gene_sub != target_sub:
            return False, "target_gene_subgenome_mismatch"
        if gene_sub is None and chrom_sub is not None and chrom_sub != target_sub:
            return False, "target_chrom_subgenome_mismatch"
        if gene_sub is not None and chrom_sub is not None and chrom_sub != gene_sub:
            return False, "gene_chrom_subgenome_conflict"

    return True, "ok"


def _resolve_cluster(gene_id, info=None):
    cache_key = (gene_id, (info or {}).get("label", ""), (info or {}).get("chrom", ""))
    if cache_key in _cluster_cache:
        return _cluster_cache[cache_key]

    cl = _gene_id_cluster(gene_id)

    if cl is None and info:
        cl = _chrom_cluster(info.get("chrom"))

    if cl is None:
        for rec in (_bed_gene_entries or {}).get(gene_id, []):
            cl = _chrom_cluster(rec.get("chrom"))
            if cl is not None:
                break

    if cl is None:
        global _sorted_prefixes
        if _sorted_prefixes is None:
            _sorted_prefixes = sorted((_prefix_map or {}).keys(), key=len, reverse=True)
        for pre in _sorted_prefixes:
            if gene_id.startswith(pre):
                cl = _prefix_map[pre]
                break

    _cluster_cache[cache_key] = cl
    return cl


def _candidate_gene_ids(gid):
    ids = [gid]
    if re.search(r"\.\d+$", gid):
        ids.append(re.sub(r"\.\d+$", "", gid))
    else:
        ids.append(gid + ".1")
    out = []
    for x in ids:
        if x and x not in out:
            out.append(x)
    return out


def _choose_gene_record(gene_id, requested_genome):
    """Resolve a query gene to the BED record inside the selected reference genome."""
    wanted = (requested_genome or "").strip()
    wanted_sub = None
    wanted_base = wanted
    if "_" in wanted:
        wanted_base, wanted_sub = wanted.rsplit("_", 1)
        wanted_sub = wanted_sub.upper()

    gene_sub = _gene_id_subgenome(gene_id)

    all_hits = []
    for gid in _candidate_gene_ids(gene_id):
        for rec in (_bed_gene_entries or {}).get(gid, []):
            all_hits.append((gid, rec))

    if not all_hits:
        return None, gene_id, []

    def score(item):
        gid, rec = item
        rec_label = rec.get("label", "")
        rec_base = rec.get("genome", "")
        rec_sub = str(rec.get("sub", "") or "").upper()
        s = 0
        if gid == gene_id:
            s += 1000
        if wanted:
            if rec_label == wanted:
                s += 10000
            if rec_base == wanted:
                s += 5000
            if rec_base == wanted_base:
                s += 3000
            if rec_label.startswith(wanted + "_"):
                s += 1500
            if wanted_sub and rec_sub == wanted_sub:
                s += 800
        if gene_sub and rec_sub == gene_sub:
            s += 600
        gid_cl = _gene_id_cluster(gid)
        chrom_cl = _chrom_cluster(rec.get("chrom"))
        if gid_cl is not None and chrom_cl == gid_cl:
            s += 400
        return s

    all_hits.sort(key=score, reverse=True)
    chosen_gid, chosen_rec = all_hits[0]

    if wanted:
        compatible = [
            (gid, rec) for gid, rec in all_hits
            if rec.get("label") == wanted
            or rec.get("genome") == wanted
            or rec.get("genome") == wanted_base
            or rec.get("label", "").startswith(wanted + "_")
        ]
        if compatible:
            compatible.sort(key=score, reverse=True)
            chosen_gid, chosen_rec = compatible[0]
        else:
            return None, gene_id, [rec for _, rec in all_hits]

    return chosen_rec, chosen_gid, [rec for _, rec in all_hits]


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
        "bed_gene_entries": sum(len(v) for v in (_bed_gene_entries or {}).values()),
        "orthogroups": len(_og2genes) if _og2genes else 0,
        "prefixes": len(_prefix_map) if _prefix_map else 0,
        "og_file": OG_FILE,
    }


def _parse_target_genomes(targets_str: str) -> set:
    if not targets_str:
        return set()
    return set(x.strip() for x in re.split(r"[,;|]", targets_str or "") if x.strip())


@router.get("/neighborhood")
def api_synteny(
    q: str = Query(..., description="Gene ID"),
    upstream: int = Query(5, ge=1, le=50),
    downstream: int = Query(5, ge=1, le=50),
    genome: str = Query("", description="Reference genome filter"),
    subgenome: str = Query("", description="Optional subgenome filter"),
    targets: str = Query("", description="Comma-separated target genome filter"),
):
    _ensure_loaded()

    gene_id = q.strip()
    if not gene_id:
        return {"error": "Missing gene parameter."}

    requested_genome = genome.strip()
    target_labels = _parse_target_genomes(targets)

    info, resolved_gene_id, candidate_records = _choose_gene_record(gene_id, requested_genome)
    if not info:
        if candidate_records and requested_genome:
            available = sorted(set(r.get("label", "") for r in candidate_records if r.get("label")))
            return {
                "error": "Gene was found in BED, but not in the selected reference genome.",
                "query": gene_id,
                "request_genome": requested_genome,
                "available_genomes_for_gene": available,
            }
        return {"error": "Gene was not found in BED: " + gene_id}

    key = (info["genome"], info["sub"], info["chrom"])
    gene_list = _chrom_lists.get(key, [])
    idx = next((i for i, (_, g) in enumerate(gene_list) if g == resolved_gene_id), None)
    if idx is None:
        return {
            "error": "Gene is not present in the chromosome list for the selected reference genome.",
            "query": gene_id,
            "resolved_gene": resolved_gene_id,
            "query_genome": info.get("label", _genome_label(info.get("genome"), info.get("sub"))),
            "query_chrom": info.get("chrom"),
        }

    lo, hi = max(0, idx - 5), min(len(gene_list), idx + 6)
    neighbors = [g for _, g in gene_list[lo:hi]]

    with ThreadPoolExecutor(max_workers=min(11, max(1, len(neighbors)))) as ex:
        og_results = dict(ex.map(_find_og, neighbors))

    query_cluster = _resolve_cluster(resolved_gene_id, info)
    qkey = info.get("label") or _genome_label(info["genome"], info["sub"])

    tracks = {}
    skipped_counts = {}

    # Query track: exact BED neighborhood (±5 genes)
    query_track = {
        "label": qkey,
        "chrom": info["chrom"],
        "genes": [],
        "is_query_track": True,
    }
    for order, ng in enumerate(neighbors):
        ninfo = None
        for rec in (_bed_gene_entries or {}).get(ng, []):
            if rec.get("genome") == info.get("genome") and rec.get("sub") == info.get("sub") and rec.get("chrom") == info.get("chrom"):
                ninfo = rec
                break
        if not ninfo:
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
            "is_query": ng == resolved_gene_id,
            "has_orthogroup": bool(og),
            "cluster": _resolve_cluster(ng, ninfo),
        })
    tracks[qkey] = query_track

    # Other genomes: only OG orthologs in the same cluster, subgenome-strict
    for order, ng in enumerate(neighbors):
        og = og_results.get(ng)
        if not og:
            continue
        for hom in _og2genes.get(og, []):
            for bi in (_bed_gene_entries or {}).get(hom, []):
                gk = bi.get("label") or _genome_label(bi["genome"], bi["sub"])

                if gk == qkey:
                    continue

                if target_labels and gk not in target_labels:
                    continue

                ok, skip_reason = _record_matches_query_and_target(hom, bi, query_cluster, gk)
                if not ok:
                    skipped_counts[skip_reason] = skipped_counts.get(skip_reason, 0) + 1
                    continue

                tr = tracks.setdefault(gk, {
                    "label": gk,
                    "chrom": bi["chrom"],
                    "genes": [],
                    "is_query_track": False,
                })
                tr["genes"].append({
                    "gene": hom,
                    "start": bi["start"],
                    "end": bi["end"],
                    "og": og,
                    "order": order,
                    "neighbor": ng,
                    "is_query": False,
                    "has_orthogroup": True,
                    "cluster": _resolve_cluster(hom, bi),
                    "gene_subgenome": _gene_id_subgenome(hom),
                    "chrom_subgenome": _chrom_subgenome(bi.get("chrom")),
                })

    for tr in tracks.values():
        seen = set()
        unique = []
        for g in tr["genes"]:
            sig = (g.get("gene"), g.get("start"), g.get("end"), g.get("og"), g.get("order"))
            if sig in seen:
                continue
            seen.add(sig)
            unique.append(g)
        tr["genes"] = unique
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
    matched_target_genomes = [t["label"] for t in ordered if t["label"] != qkey]

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
        "query": resolved_gene_id,
        "submitted_query": gene_id,
        "request_genome": requested_genome,
        "requested_targets": sorted(target_labels),
        "query_genome": qkey,
        "query_chrom": info["chrom"],
        "query_start": info["start"],
        "query_end": info["end"],
        "query_region_label": _mb_label(info["start"], info["end"]),
        "query_cluster": query_cluster,
        "query_gene_subgenome": _gene_id_subgenome(resolved_gene_id),
        "skipped_counts": skipped_counts,
        "target_genomes_requested": sorted(target_labels),
        "target_genomes_matched": matched_target_genomes,
        "neighbors": neighbors,
        "og_map": og_results,
        "tracks": ordered,
        "link_groups": list(link_groups.values()),
    }
