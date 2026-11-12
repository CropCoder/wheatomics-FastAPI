#!/usr/bin/env python3
"""Import a ``*_filter_MR900_P0.2`` coexpression directory into MySQL.

Each directory holds one TSV per gene with this header::

    Gene  Target  Co-exp_Str  Co-exp_Str_MR  zScore(Co-exp_Str_MR)

The web app queries one table per dataset (``Gene1``/``Gene2``/``PCC``/``MR``),
so every directory becomes a table in ``coexpressiondb`` and must also be
registered in ``app/core/security.py`` (``COEXPRESSION_TABLES``) to appear in
the page's dropdown.

Run on the server:

    # size check first (reads every file, writes nothing)
    python3 scripts/import_coexpression_filter.py --source DIR --table NAME --dry-run

    DB_USER=root DB_PASSWORD='...' python3 scripts/import_coexpression_filter.py \
        --source /var/www/html/coexpression/cs_filter_MR900_P0.2 \
        --table CO_CS_Filter_MR900

The target table is dropped and rebuilt, so re-running is safe. Import one
dataset at a time; each one is tens of millions of rows.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

try:
    import pymysql
except ImportError:
    sys.exit("pymysql is required: pip install pymysql")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "wheatomics_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_COEXPRESSION", "coexpressiondb")
BATCH = 5000

CREATE_SQL = """
CREATE TABLE `{table}` (
  `id`    bigint unsigned NOT NULL AUTO_INCREMENT,
  `gene1` varchar(80) NOT NULL,
  `gene2` varchar(80) NOT NULL,
  `pcc`   double DEFAULT NULL,
  `mr`    double DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_gene1` (`gene1`),
  KEY `idx_gene2` (`gene2`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

INSERT_SQL = (
    "INSERT INTO `{table}` (`gene1`,`gene2`,`pcc`,`mr`) VALUES (%s,%s,%s,%s)"
)

# Header keyword -> logical column (matched case-insensitively, ignoring spaces)
HEADER_MAP = {
    "gene": "gene1",
    "target": "gene2",
    "co-exp_str": "pcc",
    "co-exp_str_mr": "mr",
    "zscore(co-exp_str_mr)": None,   # not stored
}


def _float(value: str):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_header(path: Path) -> dict[str, int] | None:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh, delimiter="\t")
        header = next(reader, None) or []
    lower = [h.strip().lower() for h in header]
    index: dict[str, int] = {}
    for i, name in enumerate(lower):
        key = HEADER_MAP.get(name)
        if key and key not in index:
            index[key] = i
    if "gene1" not in index or "gene2" not in index:
        return None
    return index


def rows_of(path: Path, index: dict[str, int]):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh, delimiter="\t")
        next(reader, None)                       # header
        gi, ti = index["gene1"], index["gene2"]
        pi, mi = index.get("pcc"), index.get("mr")
        for row in reader:
            if len(row) <= max(gi, ti):
                continue
            gene1, gene2 = row[gi].strip(), row[ti].strip()
            if not gene1 or not gene2:
                continue
            pcc = _float(row[pi]) if pi is not None and pi < len(row) else None
            mr = _float(row[mi]) if mi is not None and mi < len(row) else None
            yield gene1, gene2, pcc, mr


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", required=True, help="directory holding *filter*.txt files")
    ap.add_argument("--table", required=True, help="target MySQL table name")
    ap.add_argument("--db", default=DB_NAME)
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--password", help="MySQL password (or export DB_PASSWORD)")
    args = ap.parse_args()

    source = Path(args.source)
    if not source.is_dir():
        ap.error(f"not a directory: {source}")
    files = sorted(p for p in source.iterdir()
                   if p.is_file() and not p.name.startswith("."))
    if not files:
        ap.error(f"no files in {source}")

    print(f"{source}: {len(files):,} file(s)")
    sample = files[0]
    index = read_header(sample)
    if index is None:
        ap.error(f"{sample.name}: header lacks Gene/Target columns")
    print(f"  columns: {index}")
    size_mb = sum(p.stat().st_size for p in files) / 1e6
    print(f"  total input size: {size_mb:,.1f} MB")

    password = args.password or DB_PASSWORD
    if not args.dry_run and not password:
        ap.error("--password is required (or export DB_PASSWORD)")

    total = 0
    t0 = time.time()
    if args.dry_run:
        for path in files:
            header_index = read_header(path)
            if header_index is None:
                print(f"  [skip] {path.name}: unexpected header")
                continue
            for _ in rows_of(path, header_index):
                total += 1
        print(f"\ndry run: would insert {total:,} rows into {args.db}.{args.table}")
        return 0

    conn = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER,
                           password=password, database=args.db, charset="utf8mb4",
                           autocommit=False)
    cur = conn.cursor()
    try:
        cur.execute(f"DROP TABLE IF EXISTS `{args.table}`")
        cur.execute(CREATE_SQL.format(table=args.table))
    except pymysql.err.OperationalError as exc:
        code = exc.args[0] if exc.args else None
        conn.close()
        if code in (1044, 1142):
            sys.exit(f"MySQL denied DDL to '{DB_USER}' ({exc.args[1]}).\n"
                     "Run this with a privileged account, e.g.:\n"
                     f"  DB_USER=root DB_PASSWORD='...' python3 {__file__} "
                     f"--source {args.source} --table {args.table}")
        raise
    print(f"table {args.db}.{args.table} recreated")

    insert_sql = INSERT_SQL.format(table=args.table)
    batch: list[tuple] = []
    for path in files:
        header_index = read_header(path)
        if header_index is None:
            print(f"  [skip] {path.name}: unexpected header")
            continue
        for row in rows_of(path, header_index):
            batch.append(row)
            if len(batch) >= args.batch:
                cur.executemany(insert_sql, batch)
                total += len(batch)
                batch.clear()
                if total % (args.batch * 20) == 0:
                    rate = total / (time.time() - t0)
                    print(f"  {total:,} rows  ({rate:,.0f} rows/s)", flush=True)
        conn.commit()          # one commit per file keeps the undo log small
    if batch:
        cur.executemany(insert_sql, batch)
        total += len(batch)
    conn.commit()

    cur.execute(f"SELECT COUNT(*) FROM `{args.table}`")
    db_count = cur.fetchone()[0]
    conn.close()
    print(f"\ninserted {total:,} rows in {time.time() - t0:.0f}s "
          f"({total / max(time.time() - t0, 1):,.0f} rows/s)")
    print(f"MySQL rows: {db_count:,} ({'MATCH' if db_count == total else 'MISMATCH'})")
    return 0 if db_count == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
