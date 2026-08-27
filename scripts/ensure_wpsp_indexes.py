#!/usr/bin/env python3
"""Ensure lookup indexes exist on wheat_psp.wheat_psp (idempotent).

The CREATE TABLE in import_wheat_psp.py declares these indexes, but tables that
predated a column ADDed by ALTER may be missing them (e.g. idx_cs_gene on
databases where cs_gene_id was added manually). This script checks SHOW INDEX
and adds whatever is missing, then prints the final index inventory.

Usage:
    export DB_PASSWORD=...
    python3 scripts/ensure_wpsp_indexes.py [--database wheat_psp_db]
"""
from __future__ import annotations

import argparse
import os

import pymysql

# (index name, column) — kept in sync with import_wheat_psp.py CREATE TABLE
WANTED = (
    ("idx_seq_id", "seq_id"),
    ("idx_gene_id", "gene_id"),
    ("idx_cs_gene", "cs_gene_id"),
    ("idx_cs_03g", "cs_03g_id"),
    ("idx_is_psp", "is_psp"),
    ("idx_has_prd", "has_prd"),
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=3306)
    ap.add_argument("--user", default="wheatomics_user")
    ap.add_argument("--password", default=os.environ.get("DB_PASSWORD"),
                    help="DB password (or export DB_PASSWORD)")
    ap.add_argument("--database", default="wheat_psp_db")
    ap.add_argument("--table", default="wheat_psp")
    args = ap.parse_args()
    if not args.password:
        ap.error("--password is required (or export DB_PASSWORD)")

    conn = pymysql.connect(host=args.host, port=args.port, user=args.user,
                           password=args.password, database=args.database,
                           charset="utf8mb4", autocommit=False)
    try:
        cur = conn.cursor(pymysql.cursors.DictCursor)
        cur.execute(f"SHOW INDEX FROM {args.table}")
        existing = cur.fetchall()
        by_key: dict = {}
        for r in existing:
            by_key.setdefault(r["Key_name"], []).append(r["Column_name"])

        added = skipped = ok_n = 0
        for name, col in WANTED:
            if name not in by_key:
                try:
                    cur.execute(f"ALTER TABLE {args.table} ADD INDEX {name} ({col})")
                    conn.commit()
                    print(f"added  : {name} ({col})")
                    by_key[name] = [col]
                    added += 1
                except pymysql.err.MySQLError as e:
                    print(f"[skip] {name}: {e}")
                    skipped += 1
            elif col in by_key[name]:
                print(f"ok     : {name} ({col})")
                ok_n += 1
            else:
                print(f"[warn] {name} exists on {by_key[name]} - expected column {col};"
                      " inspect manually (DROP INDEX before re-running)")
                skipped += 1

        print(f"\nsummary: {ok_n} already present, {added} added, {skipped} skipped/warned")

        print(f"\nfinal index inventory of {args.database}.{args.table}:")
        cur.execute(f"SHOW INDEX FROM {args.table}")
        groups: dict = {}
        for r in cur.fetchall():
            groups.setdefault(r["Key_name"], []).append(r["Column_name"])
        for k in sorted(groups):
            print(f"  {k:<14} -> {', '.join(groups[k])}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
