#!/usr/bin/env python3
"""Create the indexes the TF Atlas needs on regulatory.sqlite.

The atlas resolves a gene through regions(gene_id, kind) and then joins its
motif hits by region_id. Without these indexes SQLite scans the whole `hits`
table on every gene search, which is what makes a search slow.

Run once on the server (the file is read-only for the API, so this must be done
outside the service):

    sudo systemctl stop wheatomics-api            # optional but avoids readers
    python3 scripts/add_regulatory_indexes.py
    sudo systemctl start wheatomics-api

    # check only, change nothing:
    python3 scripts/add_regulatory_indexes.py --dry-run
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

DEFAULT_DB = Path(
    "/var/www/html/wheat-regulatory-hub/data/processed/regulatory.sqlite"
)

# name -> (table, columns)
INDEXES = {
    "idx_regions_gene_kind": ("regions", "gene_id, kind"),
    "idx_hits_region_start": ("hits", "region_id, start0"),
}

MOTIF_QUERY = """
SELECT COUNT(*) FROM (
  SELECT h.hit_id
  FROM regions r JOIN hits h ON h.region_id = r.region_id
  WHERE r.gene_id = ? AND r.kind IN ('upstream','downstream','gene_body')
)
"""


def existing_indexes(con) -> set:
    return {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}


def explain(con, gene: str) -> list:
    sql = """
    SELECT h.hit_id
    FROM regions r JOIN hits h ON h.region_id = r.region_id
    WHERE r.gene_id = ? AND r.kind IN ('upstream','downstream','gene_body')
    """
    return [tuple(r) for r in con.execute("EXPLAIN QUERY PLAN " + sql, (gene,))]


def timed_count(con, gene: str) -> float:
    start = time.perf_counter()
    con.execute(MOTIF_QUERY, (gene,)).fetchone()
    return (time.perf_counter() - start) * 1000.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--gene", default="TraesCS2A02G305400",
                    help="gene used for the timing probe")
    ap.add_argument("--dry-run", action="store_true", help="report only")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.is_file():
        ap.error(f"database not found: {db}")

    con = sqlite3.connect(str(db))
    try:
        have = existing_indexes(con)
        print(f"database: {db}")
        print(f"existing indexes: {sorted(have) or '(none)'}")

        for name, (table, cols) in INDEXES.items():
            if name in have:
                print(f"  {name}: already present")
                continue
            if args.dry_run:
                print(f"  {name}: WOULD CREATE on {table}({cols})")
                continue
            print(f"  {name}: creating on {table}({cols}) ...", flush=True)
            start = time.perf_counter()
            con.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table}({cols})")
            con.commit()
            print(f"  {name}: done in {time.perf_counter() - start:.1f}s")

        print("\nplan before/after ANALYZE:")
        for row in explain(con, args.gene):
            print("  ", row)

        print(f"\nprobe query on {args.gene}: {timed_count(con, args.gene):.0f} ms")

        if not args.dry_run:
            print("running ANALYZE ...", flush=True)
            con.execute("ANALYZE")
            con.commit()
            print(f"probe after ANALYZE: {timed_count(con, args.gene):.0f} ms")
            print("\nindexes now:", sorted(existing_indexes(con)))
        else:
            print("\ndry run: nothing changed")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
