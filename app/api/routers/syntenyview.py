"""SynTenyView MySQL-backed FastAPI router.

The BED files are imported into MySQL by import_bed_to_mysql.py.  This router
never loads the 6.3M+ BED records into Python memory.  Gene lookup, genome
listing, neighborhood extraction and orthogroup lookup are all performed by
MySQL, while only the small result set for the current query is kept in RAM.
"""

from __future__ import annotations

import os
import re
import threading
import time
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Query

from app.core.config import settings
from app.db.mysql import mysql_connection

router = APIRouter(prefix="/syntenyview", tags=["SynTeny Viewer"])

# ---------------------------------------------------------------------------
# Database configuration
# ---------------------------------------------------------------------------
DB_NAME = settings.DB_SYNTENY

COL_BED_DIR = os.getenv("COL_BED_DIR", "/var/www/html/col_bed")
TRITICEAE_FILE = os.path.join(COL_BED_DIR, "triticeae.txt")

# [CLUSTER-FIX] SpeciesIDs cluster mapping file
CLUSTER_FILE = os.getenv(
    "SPECIES_CLUSTER_FILE",
    "/var/www/html/orthefind/Results_Jul24/WorkingDirectory/SpeciesIDs_cluster.txt",
)

# [PLOIDY-FIX] genome_type.txt maps species -> (type, ploidy), used to order
# and label the target-genome picker by ploidy level instead of alphabetically.
GENOME_TYPE_FILE = os.getenv(
    "GENOME_TYPE_FILE",
    "/var/www/html/orthefind/genome_type.txt",
)

MAX_WINDOW = 50
DEFAULT_UPSTREAM = 5
DEFAULT_DOWNSTREAM = 5

# [COLLINEAR-FIX] Max allowed gap (bp) between consecutive target hits
MAX_SYNTENY_GAP = int(os.getenv("SYNTENY_MAX_GAP", "5000000"))  # 5 Mb

_QUERY_SEMAPHORE = threading.BoundedSemaphore(8)
_GENOME_CACHE = None
_GENOME_CACHE_TIME = 0.0
_GENOME_CACHE_TTL = 300.0

# [CLUSTER-FIX] Cache for the parsed cluster map.
_CLUSTER_CACHE = None
_CLUSTER_CACHE_TIME = 0.0
_CLUSTER_CACHE_TTL = 300.0

# [PLOIDY-FIX] Cache for the parsed genome_type.txt mapping.
_GENOME_TYPE_CACHE = None
_GENOME_TYPE_CACHE_TIME = 0.0


def _conn_cursor():
    return mysql_connection(settings.DB_SYNTENY)


def _split_label(label: str) -> Tuple[str, str]:
    m = re.match(r"^(.+)_([A-Za-z][A-Za-z0-9]*)$", label or "")
    return (m.group(1), m.group(2)) if m else (label or "", "")


def _label(genome: str, sub: str) -> str:
    return f"{genome}_{sub}" if sub else genome


def _genome_sort_key(label: str):
    if "_" in label:
        prefix, suffix = label.rsplit("_", 1)
        order = {"A": 0, "B": 1, "D": 2}
        return (order.get(suffix.upper(), 3), suffix.upper(), prefix.lower())
    return (4, "", label.lower())


def _genome_entry_sort_key(entry: dict) -> tuple:
    """Order genome entries for the picker.

    Within each subgenome (A/B/D) the ordering is: Chinese Spring genomes
    first, then by ploidy (from genome_type.txt), then by name.  This
    replaces the old alphabetical ordering so the picker groups genomes by
    ploidy level rather than by name.
    """
    name = entry["name"]
    ploidy = entry.get("ploidy") or ""
    if "_" in name:
        _, suffix = name.rsplit("_", 1)
        order = {"A": 0, "B": 1, "D": 2}
        sub = order.get(suffix.upper(), 3)
    else:
        sub = 4
    cs = 0 if "Chinese_Spring" in name else 1
    return (sub, cs, ploidy, name.lower())


def _mb_label(start, end):
    try:
        return "%.2f-%.2f Mb" % (float(start) / 1e6, float(end) / 1e6)
    except Exception:
        return ""


def _strip_version(gid: str) -> str:
    return re.sub(r"\.\d+$", "", gid or "")


def _candidate_gene_ids(gid: str) -> List[str]:
    ids = [gid]
    if re.search(r"\.\d+$", gid):
        ids.append(re.sub(r"\.\d+$", "", gid))
    else:
        ids.append(gid + ".1")
    return list(dict.fromkeys(x for x in ids if x))


def _gene_subgenome(gid: str) -> Optional[str]:
    g = _strip_version(gid)
    m = re.search(r"(?i)([1-7])([abd])(?=\d{3,})", g)
    if m:
        return m.group(2).upper()
    m = re.search(r"(?i)(?:^|[^0-9])([1-7])([abd])(?=\d)", g)
    if m:
        return m.group(2).upper()
    return None


def _chrom_subgenome(chrom: str) -> Optional[str]:
    m = re.search(r"(?i)(?:chr)?[1-7]\s*([abd])", str(chrom or ""))
    return m.group(1).upper() if m else None


def _gene_cluster(gid: str) -> Optional[int]:
    g = _strip_version(gid)
    m = re.search(r"(?i)([1-7])([abd])(?=\d{3,})", g)
    if m:
        return int(m.group(1))
    m = re.search(r"(?i)(?:^|[^0-9])([1-7])([abd])(?=\d)", g)
    return int(m.group(1)) if m else None


def _chrom_cluster(chrom: str) -> Optional[int]:
    m = re.search(r"(?i)(?:chr)?([1-7])\s*[abd]", str(chrom or ""))
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# [CLUSTER-FIX] Chromosome-group resolution from SpeciesIDs_cluster.txt
# ---------------------------------------------------------------------------
def _load_cluster_map() -> Dict[str, dict]:
    global _CLUSTER_CACHE, _CLUSTER_CACHE_TIME
    now = time.monotonic()
    if _CLUSTER_CACHE is not None and now - _CLUSTER_CACHE_TIME < _CLUSTER_CACHE_TTL:
        return _CLUSTER_CACHE

    out: Dict[str, dict] = {}
    if os.path.exists(CLUSTER_FILE):
        with open(CLUSTER_FILE, encoding="utf-8", errors="ignore") as fh:
            fh.readline()  # skip header
            for raw in fh:
                line = raw.rstrip("\n").rstrip("\r")
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) < 10:
                    parts = re.split(r"\s+", line.strip())
                if len(parts) < 10:
                    continue

                sp = re.sub(r"^\d+:\s*", "", parts[0]).strip()
                sp = re.sub(r"\.pep$", "", sp)

                clusters = parts[1:8]
                type1 = parts[8].strip().lower()
                type2 = parts[9].strip().lower()

                mode = "chrom" if (type2 == "yes" and type1 != "yes") else "prefix"

                tokens: Dict[str, int] = {}
                for i, tok in enumerate(clusters, start=1):
                    tok = (tok or "").strip()
                    if tok:
                        tokens[tok] = i

                if sp and tokens:
                    out[sp] = {"mode": mode, "tokens": tokens}

    _CLUSTER_CACHE = out
    _CLUSTER_CACHE_TIME = now
    return out


def _load_genome_type_map() -> Dict[str, dict]:
    """Parse genome_type.txt (Number<TAB>species<TAB>type<TAB>ploidy) into
    {species: {"type": ..., "ploidy": ...}}.  Tolerant of whitespace/tab
    delimiters; a species not present in the file simply falls back to an
    empty mapping (the picker then shows the raw genome name)."""
    global _GENOME_TYPE_CACHE, _GENOME_TYPE_CACHE_TIME
    now = time.monotonic()
    if _GENOME_TYPE_CACHE is not None and now - _GENOME_TYPE_CACHE_TIME < _GENOME_TYPE_CACHE_TTL:
        return _GENOME_TYPE_CACHE

    out: Dict[str, dict] = {}
    if os.path.exists(GENOME_TYPE_FILE):
        with open(GENOME_TYPE_FILE, encoding="utf-8", errors="ignore") as fh:
            fh.readline()  # skip header (Number species type ploidy)
            for raw in fh:
                line = raw.rstrip("\n").rstrip("\r")
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) < 4:
                    parts = re.split(r"\s+", line.strip())
                if len(parts) < 4:
                    continue
                species = parts[1].strip()
                typ = parts[2].strip()
                ploidy = parts[3].strip()
                if species:
                    out[species] = {"type": typ, "ploidy": ploidy}

    _GENOME_TYPE_CACHE = out
    _GENOME_TYPE_CACHE_TIME = now
    return out


def _resolve_cluster(
    genome_label: str,
    gene_id: str,
    chromosome: str,
    cluster_map: Dict[str, dict],
) -> Optional[int]:
    info = cluster_map.get(genome_label)
    if not info:
        return _gene_cluster(gene_id) or _chrom_cluster(chromosome)

    tokens = info["tokens"]

    if info["mode"] == "prefix":
        g = _strip_version(gene_id)
        best, best_len = None, -1
        for tok, cl in tokens.items():
            if g.startswith(tok) and len(tok) > best_len:
                best, best_len = cl, len(tok)
        if best is not None:
            return best
        return _gene_cluster(gene_id) or _chrom_cluster(chromosome)

    c = str(chromosome or "")
    best, best_len = None, -1
    for tok, cl in tokens.items():
        if (c == tok or c.startswith(tok)) and len(tok) > best_len:
            best, best_len = cl, len(tok)
    if best is not None:
        return best
    return _chrom_cluster(chromosome) or _gene_cluster(gene_id)


# ---------------------------------------------------------------------------
# [COLLINEAR-FIX] Local collinear-block filtering
# ---------------------------------------------------------------------------
def _gene_mid(g: dict) -> float:
    return (g["start"] + g["end"]) / 2.0


def _filter_collinear_block(
    genes: List[dict],
    query_order: Optional[int],
    max_gap: int = MAX_SYNTENY_GAP,
) -> Tuple[List[dict], int]:
    if not genes:
        return [], 0

    by_chrom: Dict[str, List[dict]] = {}
    for g in genes:
        by_chrom.setdefault(g.get("chrom") or "", []).append(g)

    scored = []
    for _chrom, items in by_chrom.items():
        items = sorted(items, key=_gene_mid)
        clusters: List[List[dict]] = []
        cur = [items[0]]
        for prev, g in zip(items, items[1:]):
            if _gene_mid(g) - _gene_mid(prev) <= max_gap:
                cur.append(g)
            else:
                clusters.append(cur)
                cur = [g]
        clusters.append(cur)

        for cl in clusters:
            has_anchor = (
                query_order is not None
                and any(g["order"] == query_order for g in cl)
            )
            score = (
                1 if has_anchor else 0,
                len({g["order"] for g in cl}),
                len(cl),
            )
            scored.append((score, cl))

    if not scored:
        return [], 0

    scored.sort(key=lambda x: x[0], reverse=True)
    kept = scored[0][1]
    kept_ids = {id(g) for g in kept}
    skipped = sum(1 for g in genes if id(g) not in kept_ids)
    return kept, skipped


def _query_limit(fn):
    import functools

    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        if not _QUERY_SEMAPHORE.acquire(timeout=300):
            return {"error": "Server is busy; please retry shortly."}
        try:
            return fn(*args, **kwargs)
        finally:
            _QUERY_SEMAPHORE.release()

    return wrapped


def _normalize_gene_row(row: dict) -> dict:
    genome = row["genome_name"]
    sub = row.get("subgenome") or ""
    return {
        "id": row["id"],
        "genome_name": genome,
        "subgenome": sub,
        "label": _label(genome, sub),
        "chromosome": row.get("chromosome") or "",
        "start_pos": int(row["start_pos"]),
        "end_pos": int(row["end_pos"]),
        "gene_id": row["gene_id"],
        "annotation": row.get("annotation") or "-",
        "family": row.get("family") or "-",
    }


def _choose_reference_record(rows: List[dict], submitted_gene: str) -> Optional[dict]:
    if not rows:
        return None

    wanted_sub = _gene_subgenome(submitted_gene)
    wanted_cluster = _gene_cluster(submitted_gene)

    def score(row):
        s = 0
        if row["gene_id"] == submitted_gene:
            s += 10000
        if wanted_sub and (row.get("subgenome") or "").upper() == wanted_sub:
            s += 1000
        chrom_sub = _chrom_subgenome(row.get("chromosome"))
        if wanted_sub and chrom_sub == wanted_sub:
            s += 500
        if wanted_cluster is not None and _chrom_cluster(row.get("chromosome")) == wanted_cluster:
            s += 400
        if row.get("annotation"):
            s += 1
        return s

    return sorted(rows, key=lambda r: (-score(r), r["genome_name"], r["subgenome"], r["chromosome"], r["start_pos"], r["id"]))[0]


def _fetch_gene_candidates(conn, gene_id: str) -> List[dict]:
    candidates = _candidate_gene_ids(gene_id)
    placeholders = ",".join(["%s"] * len(candidates))
    sql = f"""
        SELECT id, genome_name, subgenome, chromosome, start_pos, end_pos,
               gene_id, annotation, family
        FROM gene_position
        WHERE gene_id IN ({placeholders})
        ORDER BY id
    """
    with conn.cursor() as cur:
        cur.execute(sql, candidates)
        return [_normalize_gene_row(r) for r in cur.fetchall()]


def _fetch_neighbors(conn, ref: dict, upstream: int, downstream: int) -> List[dict]:
    base = """
        SELECT id, genome_name, subgenome, chromosome, start_pos, end_pos,
               gene_id, annotation, family
        FROM gene_position
        WHERE genome_name = %s
          AND COALESCE(subgenome, '') = COALESCE(%s, '')
          AND chromosome = %s
    """

    with conn.cursor() as cur:
        cur.execute(
            base + """
              AND (start_pos < %s
                   OR (start_pos = %s AND end_pos < %s)
                   OR (start_pos = %s AND end_pos = %s AND id < %s))
              ORDER BY start_pos DESC, end_pos DESC, id DESC
              LIMIT %s
            """,
            (
                ref["genome_name"], ref["subgenome"], ref["chromosome"],
                ref["start_pos"], ref["start_pos"], ref["end_pos"],
                ref["start_pos"], ref["end_pos"], ref["id"], upstream,
            ),
        )
        up = [_normalize_gene_row(r) for r in cur.fetchall()]

        cur.execute(
            base + """
              AND (start_pos > %s
                   OR (start_pos = %s AND end_pos > %s)
                   OR (start_pos = %s AND end_pos = %s AND id > %s))
              ORDER BY start_pos ASC, end_pos ASC, id ASC
              LIMIT %s
            """,
            (
                ref["genome_name"], ref["subgenome"], ref["chromosome"],
                ref["start_pos"], ref["start_pos"], ref["end_pos"],
                ref["start_pos"], ref["end_pos"], ref["id"], downstream,
            ),
        )
        down = [_normalize_gene_row(r) for r in cur.fetchall()]

    up.reverse()
    return up + [ref] + down


def _fetch_orthogroups(conn, gene_ids: List[str]) -> Dict[str, List[str]]:
    if not gene_ids:
        return {}
    placeholders = ",".join(["%s"] * len(gene_ids))
    sql = f"""
        SELECT gene_id, orthogroup
        FROM gene_orthogroup
        WHERE gene_id IN ({placeholders})
    """
    out: Dict[str, List[str]] = {}
    with conn.cursor() as cur:
        cur.execute(sql, gene_ids)
        for row in cur.fetchall():
            out.setdefault(row["gene_id"], []).append(row["orthogroup"])
    return out


def _fetch_target_records_by_ogs(conn, ogs: List[str], target_labels: set) -> Dict[str, List[dict]]:
    if not ogs or not target_labels:
        return {}

    og_ph = ",".join(["%s"] * len(ogs))
    target_ph = ",".join(["%s"] * len(target_labels))
    sql = f"""
        SELECT og.orthogroup, gp.id, gp.genome_name, gp.subgenome,
               gp.chromosome, gp.start_pos, gp.end_pos, gp.gene_id,
               gp.annotation, gp.family
        FROM gene_orthogroup og
        INNER JOIN gene_position gp ON gp.gene_id = og.gene_id
        WHERE og.orthogroup IN ({og_ph})
          AND gp.genome_name IN ({target_ph})
        ORDER BY gp.genome_name, gp.chromosome, gp.start_pos, gp.end_pos, gp.id
    """
    args = list(ogs) + sorted(target_labels)
    out: Dict[str, List[dict]] = {}
    with conn.cursor() as cur:
        cur.execute(sql, args)
        for row in cur.fetchall():
            rec = _normalize_gene_row(row)
            rec["orthogroup"] = row["orthogroup"]
            out.setdefault(row["orthogroup"], []).append(rec)
    return out


def _target_label_matches(rec: dict, target_labels: set) -> bool:
    return rec.get("genome_name", "") in target_labels


def _read_triticeae_targets() -> Tuple[List[str], Optional[str]]:
    if not os.path.exists(TRITICEAE_FILE):
        return [], None
    labels = []
    seen = set()
    with open(TRITICEAE_FILE, encoding="utf-8", errors="ignore") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            for item in re.split(r"\s+", line):
                item = re.sub(r"\.filter\.bed$|\.bed$", "", item.strip())
                if item and item not in seen:
                    seen.add(item)
                    labels.append(item)
    return labels, TRITICEAE_FILE


@router.get("/genomes")
def api_genomes():
    global _GENOME_CACHE, _GENOME_CACHE_TIME
    now = time.monotonic()
    if _GENOME_CACHE is not None and now - _GENOME_CACHE_TIME < _GENOME_CACHE_TTL:
        return _GENOME_CACHE

    with _conn_cursor() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT genome_name, bed_file FROM genome_info ORDER BY genome_name")
            labels = [row["genome_name"] for row in cur.fetchall()]

    type_map = _load_genome_type_map()
    entries = []
    for name in sorted(set(labels)):
        info = type_map.get(name, {})
        ploidy = info.get("ploidy", "")
        typ = info.get("type", "")
        label = f"{ploidy}_{typ}" if ploidy and typ else name
        entries.append({"name": name, "ploidy": ploidy, "type": typ, "label": label})

    entries.sort(key=_genome_entry_sort_key)
    names = [e["name"] for e in entries]
    meta = {e["name"]: {"ploidy": e["ploidy"], "type": e["type"], "label": e["label"]} for e in entries}
    _GENOME_CACHE = {"genomes": names, "meta": meta}
    _GENOME_CACHE_TIME = now
    return _GENOME_CACHE


@router.get("/gene-search")
def api_gene_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=50),
):
    term = q.strip()
    with _conn_cursor() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT gene_id, MIN(genome_name) AS genome_name,
                       MIN(subgenome) AS subgenome
                FROM gene_position
                WHERE gene_id LIKE %s
                GROUP BY gene_id
                ORDER BY gene_id
                LIMIT %s
                """,
                (term + "%", limit),
            )
            return [
                {
                    "gene_id": r["gene_id"],
                    "genome": _label(r["genome_name"], r.get("subgenome") or ""),
                }
                for r in cur.fetchall()
            ]


@router.get("/status")
def api_status():
    with _conn_cursor() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM genome_info")
            genomes = int(cur.fetchone()["n"])
            cur.execute("SELECT COUNT(*) AS n FROM gene_position")
            genes = int(cur.fetchone()["n"])
            cur.execute("SELECT COUNT(*) AS n FROM gene_orthogroup")
            mappings = int(cur.fetchone()["n"])
            cur.execute("SELECT COUNT(DISTINCT orthogroup) AS n FROM gene_orthogroup")
            ogs = int(cur.fetchone()["n"])
    return {
        "state": "ready",
        "database": DB_NAME,
        "genomes": genomes,
        "gene_position_rows": genes,
        "gene_orthogroup_rows": mappings,
        "orthogroups": ogs,
        "data_source": "MySQL",
        "api_version": "V4",
    }


@router.get("/triticeae")
def api_triticeae():
    labels, source = _read_triticeae_targets()
    genomes = set(api_genomes())
    matched = [g for g in labels if g in genomes]
    missing = [g for g in labels if g not in genomes]
    return {
        "source": source,
        "targets": labels,
        "matched_targets": matched,
        "missing_targets": missing,
        "matched_count": len(matched),
        "missing_count": len(missing),
        "error": None if source else "triticeae.txt was not found.",
    }


@router.get("/neighborhood")
@_query_limit
def api_synteny(
    q: str = Query(..., description="Gene ID"),
    upstream: int = Query(DEFAULT_UPSTREAM, ge=0, le=MAX_WINDOW),
    downstream: int = Query(DEFAULT_DOWNSTREAM, ge=0, le=MAX_WINDOW),
    targets: str = Query("", description="Comma-separated target genome labels"),
    window: int = Query(5, ge=0, le=MAX_WINDOW),
):
    gene_id = q.strip()
    if not gene_id:
        return {"error": "Missing gene parameter."}

    if upstream == DEFAULT_UPSTREAM and downstream == DEFAULT_DOWNSTREAM and window != 5:
        upstream = downstream = window

    target_labels = {x.strip() for x in re.split(r"[,;|]", targets or "") if x.strip()}

    cluster_map = _load_cluster_map()

    with _conn_cursor() as conn:
        candidates = _fetch_gene_candidates(conn, gene_id)
        if not candidates:
            return {"error": "Gene was not found in MySQL BED data: " + gene_id}

        ref = _choose_reference_record(candidates, gene_id)
        if not ref:
            return {"error": "Unable to resolve reference record for gene: " + gene_id}

        neighbors = _fetch_neighbors(conn, ref, upstream, downstream)
        neighbor_ids = [r["gene_id"] for r in neighbors]
        og_map_multi = _fetch_orthogroups(conn, neighbor_ids)
        og_results = {gid: (ogs[0] if ogs else None) for gid, ogs in og_map_multi.items()}

        query_cluster = _resolve_cluster(
            ref["genome_name"], ref["gene_id"], ref["chromosome"], cluster_map
        )
        query_label = ref["label"]

        query_track_genes = []
        query_order = None
        for order, rec in enumerate(neighbors):
            og = og_results.get(rec["gene_id"])
            is_query = rec["id"] == ref["id"]
            if is_query:
                query_order = order
            query_track_genes.append({
                "gene": rec["gene_id"],
                "start": rec["start_pos"],
                "end": rec["end_pos"],
                "chrom": rec["chromosome"],
                "description": rec["annotation"],
                "pfams": rec["family"],
                "og": og,
                "order": order,
                "query_order": query_order,
                "neighbor": rec["gene_id"],
                "is_query": is_query,
                "has_orthogroup": bool(og),
                "cluster": _resolve_cluster(rec["genome_name"], rec["gene_id"], rec["chromosome"], cluster_map),
                "gene_subgenome": _gene_subgenome(rec["gene_id"]),
                "chrom_subgenome": _chrom_subgenome(rec["chromosome"]),
            })

        tracks = {
            query_label: {
                "label": query_label,
                "chrom": ref["chromosome"],
                "genes": query_track_genes,
                "is_query_track": True,
                "root": True,
                "region_start": min(r["start_pos"] for r in neighbors),
                "region_end": max(r["end_pos"] for r in neighbors),
            }
        }
        skipped_counts: Dict[str, int] = {}

        ogs = sorted({x for x in og_results.values() if x})
        target_records_by_og = _fetch_target_records_by_ogs(conn, ogs, target_labels)

        for target_label in sorted(target_labels, key=_genome_sort_key):
            if target_label == query_label:
                continue
            tracks.setdefault(target_label, {
                "label": target_label,
                "chrom": "",
                "genes": [],
                "is_query_track": False,
                "root": False,
                "no_homologs": True,
            })

        for og in ogs:
            orders = [i for i, ng in enumerate(neighbor_ids) if og_results.get(ng) == og]
            for rec in target_records_by_og.get(og, []):
                hom = rec["gene_id"]
                gk = rec["genome_name"]
                if gk == query_label or gk not in target_labels:
                    continue

                rec_cluster = _resolve_cluster(
                    rec["genome_name"], hom, rec["chromosome"], cluster_map
                )
                if (
                    query_cluster is not None
                    and rec_cluster is not None
                    and rec_cluster != query_cluster
                ):
                    skipped_counts[gk] = skipped_counts.get(gk, 0) + 1
                    continue

                tr = tracks.setdefault(gk, {
                    "label": gk,
                    "chrom": rec["chromosome"] or "",
                    "genes": [],
                    "is_query_track": False,
                    "root": False,
                })
                tr["no_homologs"] = False
                if not tr.get("chrom"):
                    tr["chrom"] = rec["chromosome"] or ""
                for order in orders:
                    tr["genes"].append({
                        "gene": hom,
                        "start": rec["start_pos"],
                        "end": rec["end_pos"],
                        "chrom": rec["chromosome"] or "",
                        "description": rec["annotation"],
                        "pfams": rec["family"],
                        "og": og,
                        "order": order,
                        "query_order": query_order,
                        "neighbor": neighbor_ids[order],
                        "is_query": False,
                        "has_orthogroup": True,
                        "cluster": rec_cluster,
                        "gene_subgenome": _gene_subgenome(hom),
                        "chrom_subgenome": _chrom_subgenome(rec["chromosome"]),
                    })

        for key, tr in tracks.items():
            if key == query_label:
                continue
            kept, skipped = _filter_collinear_block(tr["genes"], query_order)
            if skipped:
                skipped_counts[key] = skipped_counts.get(key, 0) + skipped
            tr["genes"] = kept

        for tr in tracks.values():
            seen = set()
            unique = []
            for g in tr["genes"]:
                sig = (g["gene"], g["start"], g["end"], g["og"], g["order"])
                if sig in seen:
                    continue
                seen.add(sig)
                unique.append(g)
            unique.sort(key=lambda x: (x["start"], x["end"], x["gene"]))
            tr["genes"] = unique
            if unique:
                tr["region_start"] = min(g["start"] for g in unique)
                tr["region_end"] = max(g["end"] for g in unique)
                tr["region_label"] = _mb_label(tr["region_start"], tr["region_end"])
            else:
                tr["region_start"] = None
                tr["region_end"] = None
                tr["region_label"] = ""

        for key, tr in tracks.items():
            if key == query_label:
                continue
            if not tr.get("genes"):
                tr["no_homologs"] = True

        # [ROOT-FIX] Query track always first (index 0 = top row)
        ordered = [tracks[query_label]] + sorted(
            [tr for key, tr in tracks.items() if key != query_label],
            key=lambda t: _genome_sort_key(t["label"]),
        )
        for ti, tr in enumerate(ordered):
            tr["track_index"] = ti
            tr["root"] = (ti == 0)
            tr["is_query_track"] = (ti == 0)

        grouped = {}
        for ti, tr in enumerate(ordered):
            for g in tr["genes"]:
                if not g.get("og"):
                    continue
                key = f'{g["order"]}|{g["og"]}'
                grouped.setdefault(key, {
                    "order": g["order"],
                    "og": g["og"],
                    "neighbor": g.get("neighbor", ""),
                    "points": [],
                })["points"].append({
                    "track_index": ti,
                    "track_label": tr["label"],
                    "chrom": tr["chrom"],
                    "gene": g["gene"],
                    "start": g["start"],
                    "end": g["end"],
                })
        link_groups = list(grouped.values())

        target_summary = []
        for target_label in sorted(target_labels, key=_genome_sort_key):
            tr = tracks.get(target_label, {})
            genes = tr.get("genes") or []
            target_summary.append({
                "label": target_label,
                "genes": len(genes),
                "orthogroups": len({g.get("og") for g in genes if g.get("og")}),
                "status": "ok" if genes else "no_homologs",
                "skipped_out_of_region": skipped_counts.get(target_label, 0),
            })

        return {
            "query": ref["gene_id"],
            "submitted_query": gene_id,
            "request_genome": query_label,
            "root_track": query_label,
            "requested_targets": sorted(target_labels, key=_genome_sort_key),
            "target_summary": target_summary,
            "upstream": upstream,
            "downstream": downstream,
            "window": max(upstream, downstream),
            "max_window": MAX_WINDOW,
            "query_genome": query_label,
            "query_chrom": ref["chromosome"],
            "query_start": ref["start_pos"],
            "query_end": ref["end_pos"],
            "query_description": ref["annotation"],
            "query_pfams": ref["family"],
            "query_region_label": _mb_label(ref["start_pos"], ref["end_pos"]),
            "query_cluster": query_cluster,
            "query_gene_subgenome": _gene_subgenome(ref["gene_id"]),
            "query_order": query_order,
            "skipped_counts": skipped_counts,
            "neighbors": neighbor_ids,
            "og_map": og_results,
            "tracks": ordered,
            "link_groups": link_groups,
            "data_source": "MySQL",
        }
