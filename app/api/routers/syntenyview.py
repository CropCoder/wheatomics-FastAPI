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

import pymysql
from fastapi import APIRouter, Query

router = APIRouter(prefix="/syntenyview", tags=["SynTeny Viewer"])

# ---------------------------------------------------------------------------
# MySQL configuration
# ---------------------------------------------------------------------------
DB_HOST = os.getenv("SYNTENY_DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("SYNTENY_DB_PORT", "3306"))
DB_USER = os.getenv("SYNTENY_DB_USER", "root")
DB_PASSWORD = os.getenv("SYNTENY_DB_PASSWORD", "rosa1212")
DB_NAME = os.getenv("SYNTENY_DB_NAME", "synteny_mysql")

COL_BED_DIR = os.getenv("COL_BED_DIR", "/var/www/html/col_bed")
TRITICEAE_FILE = os.path.join(COL_BED_DIR, "triticeae.txt")

MAX_WINDOW = 50
DEFAULT_UPSTREAM = 5
DEFAULT_DOWNSTREAM = 5

_QUERY_SEMAPHORE = threading.BoundedSemaphore(8)
_GENOME_CACHE = None
_GENOME_CACHE_TIME = 0.0
_GENOME_CACHE_TTL = 300.0


def get_conn():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
        read_timeout=60,
        write_timeout=60,
    )


def _split_label(label: str) -> Tuple[str, str]:
    """Split genome label like Chinese_Spring2.1_A into base + subgenome."""
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
    m = re.search(r"(?i)(?:chr)?[1-7]\s*([abd])\b", str(chrom or ""))
    return m.group(1).upper() if m else None


def _gene_cluster(gid: str) -> Optional[int]:
    g = _strip_version(gid)
    m = re.search(r"(?i)([1-7])([abd])(?=\d{3,})", g)
    if m:
        return int(m.group(1))
    m = re.search(r"(?i)(?:^|[^0-9])([1-7])([abd])(?=\d)", g)
    return int(m.group(1)) if m else None


def _chrom_cluster(chrom: str) -> Optional[int]:
    m = re.search(r"(?i)(?:chr)?([1-7])\s*[abd]\b", str(chrom or ""))
    return int(m.group(1)) if m else None


def _query_limit(fn):
    import functools

    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        if not _QUERY_SEMAPHORE.acquire(timeout=300):
            return {"error": "Server is busy processing other synteny queries; please retry shortly."}
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
        # Prefer complete annotation records, then stable database order.
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
    """Fetch only the requested local neighborhood using indexed LIMITs."""
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
            base
            + """
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
            base
            + """
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

    # Upstream query was intentionally descending for the index; restore
    # chromosome order for the frontend.
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
    """Fetch only target-genome records belonging to the relevant OGs."""
    if not ogs or not target_labels:
        return {}

    # Split labels into genome_name + subgenome, e.g. foo_A -> (foo, A).
    pairs = [_split_label(x) for x in target_labels]
    og_ph = ",".join(["%s"] * len(ogs))
    pair_sql = ",".join(["(%s,%s)"] * len(pairs))
    pair_args = [v for pair in pairs for v in pair]

    sql = f"""
        SELECT og.orthogroup, gp.id, gp.genome_name, gp.subgenome,
               gp.chromosome, gp.start_pos, gp.end_pos, gp.gene_id,
               gp.annotation, gp.family
        FROM gene_orthogroup og
        INNER JOIN gene_position gp ON gp.gene_id = og.gene_id
        WHERE og.orthogroup IN ({og_ph})
          AND (gp.genome_name, COALESCE(gp.subgenome, '')) IN ({pair_sql})
        ORDER BY gp.genome_name, gp.subgenome, gp.chromosome, gp.start_pos, gp.end_pos, gp.id
    """
    args = list(ogs) + pair_args
    out: Dict[str, List[dict]] = {}
    with conn.cursor() as cur:
        cur.execute(sql, args)
        for row in cur.fetchall():
            rec = _normalize_gene_row(row)
            rec["orthogroup"] = row["orthogroup"]
            out.setdefault(row["orthogroup"], []).append(rec)
    return out


def _record_matches_query_and_target(hom_gene: str, rec: dict, query_cluster: Optional[int], target_label: str):
    gene_cl = _gene_cluster(hom_gene)
    gene_sub = _gene_subgenome(hom_gene)
    chrom_cl = _chrom_cluster(rec["chromosome"])
    chrom_sub = _chrom_subgenome(rec["chromosome"])
    target_sub = _split_label(target_label)[1].upper()

    if query_cluster is not None:
        if gene_cl is not None and gene_cl != query_cluster:
            return False, "gene_group_mismatch"
        if gene_cl is None and chrom_cl is not None and chrom_cl != query_cluster:
            return False, "chrom_group_mismatch"

    if gene_cl is not None and chrom_cl is not None and gene_cl != chrom_cl:
        return False, "gene_chrom_group_conflict"

    if target_sub in {"A", "B", "D"}:
        if gene_sub is not None and gene_sub != target_sub:
            return False, "target_gene_subgenome_mismatch"
        if gene_sub is None and chrom_sub is not None and chrom_sub != target_sub:
            return False, "target_chrom_subgenome_mismatch"
        if gene_sub is not None and chrom_sub is not None and chrom_sub != gene_sub:
            return False, "gene_chrom_subgenome_conflict"

    return True, "ok"


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

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT genome_name, bed_file FROM genome_info ORDER BY genome_name")
            labels = []
            for row in cur.fetchall():
                name = row["genome_name"]
                # The importer stores labels such as Triticum_turgidum_Svevo_A.
                labels.append(name)
        _GENOME_CACHE = sorted(set(labels), key=_genome_sort_key)
        _GENOME_CACHE_TIME = now
        return _GENOME_CACHE
    finally:
        conn.close()


@router.get("/gene-search")
def api_gene_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=50),
):
    """Autocomplete/search gene IDs directly from MySQL."""
    term = q.strip()
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Prefix search uses idx_gene_id efficiently.  Contains search is
            # allowed as a fallback for short/irregular identifiers.
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
    finally:
        conn.close()


@router.get("/status")
def api_status():
    conn = get_conn()
    try:
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
        }
    finally:
        conn.close()


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

    # Backward compatibility: if only window is supplied, use it symmetrically.
    if upstream == DEFAULT_UPSTREAM and downstream == DEFAULT_DOWNSTREAM and window != 5:
        upstream = downstream = window

    target_labels = {x.strip() for x in re.split(r"[,;|]", targets or "") if x.strip()}

    conn = get_conn()
    try:
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

        query_cluster = _gene_cluster(ref["gene_id"]) or _chrom_cluster(ref["chromosome"])
        query_label = ref["label"]

        # Reference track.
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
                "description": rec["annotation"],
                "pfams": rec["family"],
                "og": og,
                "order": order,
                "query_order": query_order,
                "neighbor": rec["gene_id"],
                "is_query": is_query,
                "has_orthogroup": bool(og),
                "cluster": _gene_cluster(rec["gene_id"]) or _chrom_cluster(rec["chromosome"]),
                "gene_subgenome": _gene_subgenome(rec["gene_id"]),
                "chrom_subgenome": _chrom_subgenome(rec["chromosome"]),
            })

        tracks = {
            query_label: {
                "label": query_label,
                "chrom": ref["chromosome"],
                "genes": query_track_genes,
                "is_query_track": True,
                "region_start": min(r["start_pos"] for r in neighbors),
                "region_end": max(r["end_pos"] for r in neighbors),
            }
        }
        skipped_counts: Dict[str, int] = {}

        # Fetch all genes belonging to the OGs represented by the reference
        # neighborhood in one bounded SQL query.
        ogs = sorted({x for x in og_results.values() if x})
        # Fetch only records in the user-selected target genomes. This is the
        # critical difference from the old in-memory implementation: the DB
        # does the filtering before rows reach Python.
        target_records_by_og = _fetch_target_records_by_ogs(conn, ogs, target_labels)

        for og in ogs:
            orders = [i for i, ng in enumerate(neighbor_ids) if og_results.get(ng) == og]
            for rec in target_records_by_og.get(og, []):
                hom = rec["gene_id"]
                gk = rec["label"]
                if gk == query_label:
                    continue
                ok, reason = _record_matches_query_and_target(hom, rec, query_cluster, gk)
                if not ok:
                    skipped_counts[reason] = skipped_counts.get(reason, 0) + 1
                    continue

                tr = tracks.setdefault(gk, {
                    "label": gk,
                    "chrom": rec["chromosome"],
                    "genes": [],
                    "is_query_track": False,
                })
                for order in orders:
                    tr["genes"].append({
                        "gene": hom,
                        "start": rec["start_pos"],
                        "end": rec["end_pos"],
                        "description": rec["annotation"],
                        "pfams": rec["family"],
                        "og": og,
                        "order": order,
                        "query_order": query_order,
                        "neighbor": neighbor_ids[order],
                        "is_query": False,
                        "has_orthogroup": True,
                        "cluster": _gene_cluster(hom) or _chrom_cluster(rec["chromosome"]),
                        "gene_subgenome": _gene_subgenome(hom),
                        "chrom_subgenome": _chrom_subgenome(rec["chromosome"]),
                    })

        # Deduplicate and add region labels.
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

        ordered = [tracks[query_label]] + sorted(
            [tr for key, tr in tracks.items() if key != query_label],
            key=lambda t: t["label"].lower(),
        )
        link_groups = []
        for ti, tr in enumerate(ordered):
            tr["track_index"] = ti
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

        return {
            "query": ref["gene_id"],
            "submitted_query": gene_id,
            "request_genome": query_label,
            "requested_targets": sorted(target_labels),
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
    finally:
        conn.close()
