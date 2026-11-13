#!/usr/bin/env python3
"""Strip transcript suffixes (.1, .2, ...) from coexpression gene pairs.

``coexpressiondb.CO_BioticStress_2026`` was imported with transcript-level gene
IDs (``TraesCS1A02G001800.1``) while every other coexpression table — and the
web app's gene input — uses the bare gene ID, so lookups matched nothing.

The table has ~77M rows. Updating indexed columns row by row is slow, so this
script:

1. records the existing secondary indexes and drops them;
2. rewrites ``gene1``/``gene2`` in primary-key batches (one commit per batch);
3. rebuilds the indexes from their recorded definitions.

Run on the server:

    DB_USER=root DB_PASSWORD='...' python3 scripts/strip_coexpression_suffix.py --dry-run
    DB_USER=root DB_PASSWORD='...' python3 scripts/strip_coexpression_suffix.py

    # continue after an interruption (batches are idempotent; indexes are only
    # dropped again if they are still present)
    DB_USER=root DB_PASSWORD='...' python3 scripts/strip_coexpression_suffix.py --start 45000000

Run it inside ``tmux``/``screen`` (or with nohup). Check ``df -h`` first — the
update writes roughly one row-image per changed row to the binlog.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

try:
    import pymysql
except ImportError:
    sys.exit("pymysql is required: pip install pymysql")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_COEXPRESSION", "coexpressiondb")
TABLE = "CO_BioticStress_2026"
BATCH = 20000


def update_sql(table: str) -> str:
    # "%%" because these statements are executed with parameters (pymysql
    # unescapes them to a single % before sending).
    return (
        f"UPDATE `{table}` "
        "SET gene1 = SUBSTRING_INDEX(gene1, '.', 1), "
        "    gene2 = SUBSTRING_INDEX(gene2, '.', 1) "
        "WHERE id >= %s AND id < %s "
        "  AND (gene1 LIKE '%%.%%' OR gene2 LIKE '%%.%%')"
    )


def index_defs(cur, table: str) -> dict[str, list[str]]:
    """Secondary index name -> column list, in index order."""
    cur.execute(
        "SELECT index_name, column_name FROM information_schema.statistics "
        "WHERE table_schema = DATABASE() AND table_name = %s "
        "  AND index_name <> 'PRIMARY' "
        "ORDER BY index_name, seq_in_index",
        (table,),
    )
    out: dict[str, list[str]] = {}
    for name, column in cur.fetchall():
        out.setdefault(name, []).append(column)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=DB_NAME)
    ap.add_argument("--table", default=TABLE)
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--start", type=int, help="first id to process (resume point)")
    ap.add_argument("--keep-index", action="store_true",
                    help="keep the secondary indexes (much slower)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--password", help="MySQL password (or export DB_PASSWORD)")
    args = ap.parse_args()

    password = args.password or DB_PASSWORD
    if not password:
        ap.error("--password is required (or export DB_PASSWORD)")

    conn = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER,
                           password=password, database=args.db, charset="utf8mb4",
                           autocommit=False)
    cur = conn.cursor()
    cur.execute(f"SELECT MIN(id), MAX(id) FROM `{args.table}`")
    low, high = cur.fetchone()
    if low is None:
        print(f"{args.table}: empty table, nothing to do")
        return 0
    start = args.start if args.start is not None else low
    print(f"{args.db}.{args.table}: id {low:,}..{high:,}, "
          f"processing from {start:,} in batches of {args.batch:,}")

    cur.execute(
        f"SELECT COUNT(*) FROM `{args.table}` "
        "WHERE gene1 LIKE '%.%' OR gene2 LIKE '%.%'"
    )
    pending = cur.fetchone()[0]
    print(f"rows still carrying a dot in gene1/gene2: {pending:,} (full-scan count)")
    if args.dry_run:
        print("dry run: nothing written")
        return 0
    if pending == 0:
        print("nothing to do")
        return 0

    defs = index_defs(cur, args.table)
    if defs and not args.keep_index:
        cur.execute(f"ALTER TABLE `{args.table}` " + ", ".join(
            f"DROP INDEX `{name}`" for name in defs))
        conn.commit()
        print(f"dropped {len(defs)} index(es): {', '.join(defs)}")

    changed_total = 0
    t0 = time.time()
    cursor_id = start
    while cursor_id <= high:
        batch_end = cursor_id + args.batch
        cur.execute(update_sql(args.table), (cursor_id, batch_end))
        changed = cur.rowcount
        conn.commit()
        changed_total += max(changed, 0)
        if changed:
            elapsed = time.time() - t0
            rate = changed_total / elapsed if elapsed else 0
            print(f"  id {cursor_id:,}..{batch_end - 1:,}  changed {changed:,}  "
                  f"total {changed_total:,}  {rate:,.0f} rows/s", flush=True)
        cursor_id = batch_end

    if defs and not args.keep_index:
        print("rebuilding indexes ...", flush=True)
        t1 = time.time()
        cur.execute(f"ALTER TABLE `{args.table}` " + ", ".join(
            f"ADD INDEX `{name}` ({', '.join(f'`{c}`' for c in cols)})"
            for name, cols in defs.items()))
        conn.commit()
        print(f"  indexes rebuilt in {time.time() - t1:.0f}s")

    cur.execute(
        f"SELECT COUNT(*) FROM `{args.table}` "
        "WHERE gene1 LIKE '%.%' OR gene2 LIKE '%.%'"
    )
    remaining = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM `{args.table}`")
    total = cur.fetchone()[0]
    conn.close()

    print(f"\nrows changed this run: {changed_total:,} in {time.time() - t0:.0f}s")
    print(f"rows with a dot left: {remaining:,} (expect 0)")
    print(f"table rows: {total:,}")
    return 0 if remaining == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
