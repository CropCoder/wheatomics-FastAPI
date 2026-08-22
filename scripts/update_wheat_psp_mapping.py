"""Update wheat_psp mapping columns from the panref2traescs mapping TSV.

Sets cs_gene_id (02G) and cs_03g_id from panref2traescs_minimap_FINAL.tsv:
    panref_id<TAB>cs_03G<TAB>cs_02G<TAB>...

Only mapping columns are updated; prediction/score columns are untouched.

Usage (easiest: run on the server after copying the TSV, e.g.):
    cp panref2traescs_minimap_FINAL.tsv /tmp/
    python3 scripts/update_wheat_psp_mapping.py /tmp/panref2traescs_minimap_FINAL.tsv

Or from another machine against the remote DB:
    python3 scripts/update_wheat_psp_mapping.py mapping.tsv --host <db-host> --user root -p

Idempotent: safe to re-run; the final counts are printed for verification.
"""
from __future__ import annotations

import argparse
import csv
import sys

import pymysql


def load_mapping(path: str) -> dict:
    """panref gene id (no -P<n> suffix) -> (cs_gene_id 02G, cs_03g_id)."""
    mapping: dict = {}
    with open(path, encoding="utf-8", errors="ignore") as f:
        first = f.readline().rstrip("\r\n")
        cols = first.split("\t")
        if cols and cols[0] == "panref_id":
            cols_lower = [c.strip().lower() for c in cols]
            i_pid = cols_lower.index("panref_id")
            i_02 = cols_lower.index("cs_02g")
            i_03 = cols_lower.index("cs_03g") if "cs_03g" in cols_lower else None
            for line in f:
                row = line.rstrip("\r\n").split("\t")
                if len(row) <= max(i_pid, i_02):
                    continue
                pid = row[i_pid].strip()
                g2 = row[i_02].strip()
                g3 = row[i_03].strip() if i_03 is not None and len(row) > i_03 else ""
                if pid and g2:
                    mapping[pid] = (g2, g3 or None)
        else:
            # legacy: query<TAB>subject[<TAB>...] - subject -> 02G id
            for line in f:
                parts = line.rstrip("\r\n").split("\t")
                if len(parts) < 2:
                    continue
                q, s = parts[0].strip(), parts[1].strip()
                if q and s:
                    import re
                    mapping[q] = (re.sub(r"\.\d+$", "", s), None)
    return mapping


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mapping", help="panref2traescs_minimap_FINAL.tsv (or legacy 2-col tsv)")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=3306)
    ap.add_argument("--user", default="wheatomics_user")
    ap.add_argument("--password", default="wheatomics115599")
    ap.add_argument("--database", default="wheat_psp_db")
    ap.add_argument("--unmap-missing", action="store_true",
                    help="also NULL out cs_gene_id/cs_03g_id for gene_ids absent from the mapping")
    args = ap.parse_args()

    mapping = load_mapping(args.mapping)
    print(f"mapping loaded: {len(mapping)} panref genes", flush=True)
    if not mapping:
        print("[ERR] no mapping rows parsed")
        return 1

    conn = pymysql.connect(host=args.host, port=args.port, user=args.user,
                           password=args.password, database=args.database,
                           charset="utf8mb4", autocommit=False)
    try:
        cur = conn.cursor()

        # ---- ensure columns ----
        cur.execute("SHOW COLUMNS FROM wheat_psp")
        existing = {r[0] for r in cur.fetchall()}
        if "cs_gene_id" not in existing:
            cur.execute("ALTER TABLE wheat_psp ADD COLUMN cs_gene_id VARCHAR(100) DEFAULT NULL, "
                        "ADD INDEX idx_cs_gene (cs_gene_id)")
        if "cs_03g_id" not in existing:
            cur.execute("ALTER TABLE wheat_psp ADD COLUMN cs_03g_id VARCHAR(100) DEFAULT NULL, "
                        "ADD INDEX idx_cs_03g (cs_03g_id)")
        conn.commit()

        # ---- load mapping into a temp table (gene_id is the panref id column) ----
        cur.execute("DROP TEMPORARY TABLE IF EXISTS tmp_wpsp_map")
        cur.execute("CREATE TEMPORARY TABLE tmp_wpsp_map ("
                    "gene_id VARCHAR(100) PRIMARY KEY, "
                    "cs_gene_id VARCHAR(100), "
                    "cs_03g_id VARCHAR(100)) ENGINE=InnoDB")
        rows = [(pid, g2, g3) for pid, (g2, g3) in mapping.items()]
        cur.executemany("INSERT IGNORE INTO tmp_wpsp_map VALUES (%s,%s,%s)", rows)
        conn.commit()
        print(f"temp map table loaded: {len(rows)}", flush=True)

        # ---- apply to wheat_psp (predictions untouched) ----
        cur.execute("UPDATE wheat_psp p JOIN tmp_wpsp_map m ON p.gene_id = m.gene_id "
                    "SET p.cs_gene_id = m.cs_gene_id, p.cs_03g_id = m.cs_03g_id")
        updated = cur.rowcount
        if args.unmap_missing:
            cur.execute("UPDATE wheat_psp SET cs_gene_id = NULL, cs_03g_id = NULL "
                        "WHERE gene_id IS NOT NULL AND gene_id <> '' "
                        "AND gene_id NOT IN (SELECT gene_id FROM tmp_wpsp_map)")
            unmapped = cur.rowcount
        else:
            unmapped = 0
        conn.commit()

        # ---- report ----
        cur.execute("SELECT COUNT(*) AS total, "
                    "SUM(cs_gene_id IS NOT NULL) AS with_02g, "
                    "SUM(cs_03g_id IS NOT NULL) AS with_03g, "
                    "SUM(cs_gene_id LIKE '%LC') AS lc_02g "
                    "FROM wheat_psp")
        r = cur.fetchone()
        cur.execute("SELECT COUNT(DISTINCT cs_gene_id) AS gene02, "
                    "COUNT(DISTINCT cs_03g_id) AS gene03 "
                    "FROM wheat_psp")
        g = cur.fetchone()
        print("---- after update ----", flush=True)
        print(f"  rows updated with mapping : {updated}")
        if args.unmap_missing:
            print(f"  rows unmapped (set NULL)  : {unmapped}")
        print(f"  total rows                : {int(r['total'])}")
        print(f"  rows with cs_gene_id (02G): {int(r['with_02g'] or 0)}")
        print(f"  rows with cs_03g_id (03G) : {int(r['with_03g'] or 0)}")
        print(f"  distinct cs_gene_id (02G) : {int(g['gene02'] or 0)} (LC: {int(r['lc_02g'] or 0)})")
        print(f"  distinct cs_03g_id (03G)  : {int(g['gene03'] or 0)}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
