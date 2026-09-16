#!/usr/bin/env python3
"""Drop and rebuild Genefunc_* tables from add_Description bed files.

For each "<table><TAB><bed_file>" in the fix file, DROP the existing table and
recreate it from the bed. The bed has 10 tab-separated columns:

  0 species  1 karyotype  2 Chrom  3 Start1  4 End1
  5 Gene     6 Strand     7 Description  8 Domain  9 ChineseSpring02G

Columns 0 and 1 are not stored; the rest map onto the standard cultivar table
schema (same as the already-imported Genefunc_AABBDD_norin61_PGSBv2_1_table).

DESTRUCTIVE — DROP TABLE on every listed table. Dry-run by default; pass
--apply to actually drop/recreate/insert. Use --only for a smoke test.

Usage:
  DB_USER=root DB_PASSWORD='...' \
    python3 scripts/rebuild_genefunc_from_bed.py \
      --fix fix1.txt \
      --bed-dir /var/www/data/tiantian_data/wheat_genome/add_Description/gff3 \
      --apply --only Genefunc_Abo_table
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:
    sys.exit("pymysql is required: pip install pymysql")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "wheatomics_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
if not DB_PASSWORD:
    raise SystemExit("export DB_PASSWORD before running this script")
DB_NAME = os.environ.get("DB_GENEFUNC", "Genefuncdb")

_BATCH = 5000
# bed last-column values that mean "no ortholog"
_NULL_VALUES = {"", "null", "none", "-", ".", "na", "n/a"}


def _sql_col(col: str) -> str:
    return "`" + col.replace("`", "") + "`"


def create_table_sql(table: str) -> str:
    return (
        f"CREATE TABLE {_sql_col(table)} ("
        "`id` int(11) NOT NULL AUTO_INCREMENT, "
        "`Gene` varchar(200) NOT NULL, "
        "`Chrom` varchar(50) NOT NULL, "
        "`Start1` int(11) NOT NULL, "
        "`End1` int(11) NOT NULL, "
        "`Strand` varchar(5) DEFAULT NULL, "
        "`Description` text, "
        "`Domain` text, "
        "`ChineseSpring02G` varchar(200) DEFAULT NULL, "
        "PRIMARY KEY (`id`), "
        "KEY `Gene` (`Gene`), "
        "KEY `Chrom` (`Chrom`), "
        "KEY `Domain` (`Domain`(255)), "
        "KEY `idx_chrom_start_end` (`Chrom`, `Start1`, `End1`)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    )


def _nullable(v: str):
    v = (v or "").strip()
    return None if v.lower() in _NULL_VALUES else v


def connect():
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, charset="utf8mb4", autocommit=False, cursorclass=DictCursor,
    )


def read_fix(fix_path: str) -> list[tuple[str, str]]:
    rows = []
    with open(fix_path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                parts = line.split()
            if len(parts) < 2:
                continue
            rows.append((parts[0].strip(), parts[1].strip()))
    return rows


def parse_bed(bed_path: Path) -> list[tuple]:
    """Return rows of (Gene, Chrom, Start1, End1, Strand, Description, Domain, ChineseSpring02G)."""
    rows = []
    with open(bed_path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if not line.strip():
                continue
            cols = line.split("\t")
            if len(cols) < 10:
                continue
            gene = cols[5].strip()
            chrom = cols[2].strip()
            if not gene or not chrom:
                continue
            try:
                start = int(cols[3])
                end = int(cols[4])
            except ValueError:
                continue
            strand = _nullable(cols[6])
            desc = _nullable(cols[7])
            domain = _nullable(cols[8])
            cs = _nullable(cols[9])
            rows.append((gene, chrom, start, end, strand, desc, domain, cs))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fix", required=True, help="fix file: table<TAB>bed_file")
    ap.add_argument("--bed-dir", required=True, help="directory containing the bed files")
    ap.add_argument("--apply", action="store_true", help="actually DROP/CREATE/INSERT (default: dry-run)")
    ap.add_argument("--only", help="comma-separated table allowlist")
    args = ap.parse_args()

    allow = {t.strip() for t in args.only.split(",")} if args.only else None
    fix_rows = read_fix(args.fix)
    bed_dir = Path(args.bed_dir)

    conn = connect()
    cursor = conn.cursor()

    print(f"DB: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}  apply={args.apply}")
    print(f"fix entries: {len(fix_rows)}")
    print()

    done = skipped = failed = 0
    for i, (table, bed_name) in enumerate(fix_rows, 1):
        if allow is not None and table not in allow:
            continue
        prefix = f"[{i}/{len(fix_rows)}] {table}"

        bed_path = bed_dir / bed_name
        if not bed_path.is_file():
            print(f"{prefix} SKIP (bed not found: {bed_name})")
            skipped += 1
            continue

        rows = parse_bed(bed_path)
        if not rows:
            print(f"{prefix} SKIP (empty bed: {bed_name})")
            skipped += 1
            continue

        if not args.apply:
            print(f"{prefix} WOULD DROP + CREATE + INSERT {len(rows)} rows from {bed_name}")
            done += 1
            continue

        try:
            cursor.execute(f"DROP TABLE IF EXISTS {_sql_col(table)}")
            cursor.execute(create_table_sql(table))
            insert_sql = (
                f"INSERT INTO {_sql_col(table)} "
                "(`Gene`, `Chrom`, `Start1`, `End1`, `Strand`, `Description`, `Domain`, `ChineseSpring02G`) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            )
            for j in range(0, len(rows), _BATCH):
                cursor.executemany(insert_sql, rows[j:j + _BATCH])
            conn.commit()
            print(f"{prefix} OK rebuilt {len(rows)} rows from {bed_name}")
            done += 1
        except Exception as exc:
            conn.rollback()
            print(f"{prefix} FAIL {exc}")
            failed += 1

    print()
    print(f"summary: rebuilt={done} skipped={skipped} failed={failed}")
    conn.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
