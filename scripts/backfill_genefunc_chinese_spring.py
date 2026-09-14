#!/usr/bin/env python3
"""Backfill the ChineseSpring02G column in Genefunc_* tables from bed files.

Input: fix.txt with one "<table_name><TAB><bed_file>" per line. The bed files
have 10 columns; column 6 is the gene ID (matches the table's `Gene` column)
and column 10 is the Chinese Spring 02G ID.

For each table the script:
  1. adds a `ChineseSpring02G` column if missing,
  2. loads the bed file into {gene_id: cs_02g},
  3. runs UPDATE ... SET ChineseSpring02G = cs WHERE Gene = gene_id.

Tables without a `Gene` column (CS reference tables, registry tables) and
missing bed files are skipped. Dry-run by default — pass --apply to write.

Usage:
  DB_USER=root DB_PASSWORD='...' \
    python3 scripts/backfill_genefunc_chinese_spring.py \
      --fix /var/www/data/tiantian_data/wheat_genome/add_Description/gff3/fix.txt \
      --bed-dir /var/www/data/tiantian_data/wheat_genome/add_Description/gff3 \
      --dry-run

  # apply a single table first to smoke-test, then the rest:
  ... --apply --only Genefunc_Abo_table
  ... --apply
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

COLUMN_NAME = "ChineseSpring02G"
# Values in the bed's last column that mean "no ortholog" — skip these rows.
_NULL_VALUES = {"", "null", "none", "-", ".", "na", "n/a"}


def connect():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=DictCursor,
    )


def table_columns(cursor, table: str) -> set:
    cursor.execute(
        "SELECT COLUMN_NAME FROM information_schema.columns "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
        (DB_NAME, table),
    )
    return {r["COLUMN_NAME"] for r in cursor.fetchall()}


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


def load_bed(bed_path: Path) -> dict:
    """Return {gene_id: cs_02g} from a 10-column bed (col 6 gene, col 10 cs)."""
    mapping = {}
    with open(bed_path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if not line.strip():
                continue
            cols = line.split("\t")
            if len(cols) < 10:
                continue
            gene_id = cols[5].strip()
            cs = cols[9].strip()
            if gene_id and cs and cs.lower() not in _NULL_VALUES:
                mapping[gene_id] = cs
    return mapping


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fix", required=True, help="fix.txt: table<TAB>bed_file")
    ap.add_argument("--bed-dir", required=True, help="directory containing the bed files")
    ap.add_argument("--apply", action="store_true", help="actually ALTER/UPDATE (default: dry-run)")
    ap.add_argument("--dry-run", action="store_true", help="dry-run (default; no writes)")
    ap.add_argument("--only", help="comma-separated table allowlist")
    args = ap.parse_args()

    allow = {t.strip() for t in args.only.split(",")} if args.only else None
    fix_rows = read_fix(args.fix)
    bed_dir = Path(args.bed_dir)

    conn = connect()
    cursor = conn.cursor()

    print(f"DB: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}  apply={args.apply}")
    print(f"fix.txt entries: {len(fix_rows)}")
    print()

    added = updated = skipped = failed = 0
    for i, (table, bed_name) in enumerate(fix_rows, 1):
        if allow is not None and table not in allow:
            continue
        prefix = f"[{i}/{len(fix_rows)}] {table}"

        cols = table_columns(cursor, table)
        if "Gene" not in cols:
            print(f"{prefix} SKIP (no Gene column)")
            skipped += 1
            continue

        bed_path = bed_dir / bed_name
        if not bed_path.is_file():
            print(f"{prefix} SKIP (bed not found: {bed_name})")
            skipped += 1
            continue

        mapping = load_bed(bed_path)
        if not mapping:
            print(f"{prefix} SKIP (empty bed: {bed_name})")
            skipped += 1
            continue

        # 1) add column if missing
        if COLUMN_NAME not in cols:
            if args.apply:
                try:
                    cursor.execute(
                        f"ALTER TABLE `{table}` ADD COLUMN `{COLUMN_NAME}` varchar(100) DEFAULT NULL"
                    )
                    print(f"{prefix} ADD COLUMN {COLUMN_NAME}")
                except Exception as exc:
                    print(f"{prefix} FAIL alter: {exc}")
                    failed += 1
                    continue
            else:
                print(f"{prefix} (would add column {COLUMN_NAME})")

        # 2) dry-run: sample match rate
        if not args.apply:
            sample = list(mapping.keys())[:200]
            ph = ",".join(["%s"] * len(sample))
            cursor.execute(
                f"SELECT COUNT(*) AS n FROM `{table}` WHERE `Gene` IN ({ph})",
                sample,
            )
            matched = cursor.fetchone()["n"]
            print(
                f"{prefix} bed genes={len(mapping)}  "
                f"sample {len(sample)} -> {matched} matched in table"
            )
            continue

        # 3) apply: batch update
        cnt = 0
        for gene_id, cs in mapping.items():
            cursor.execute(
                f"UPDATE `{table}` SET `{COLUMN_NAME}`=%s WHERE `Gene`=%s",
                (cs, gene_id),
            )
            cnt += cursor.rowcount
        updated += cnt
        print(f"{prefix} OK {len(mapping)} genes mapped -> {cnt} rows updated")

    print()
    print(f"summary: columns_added={added} rows_updated={updated} skipped={skipped} failed={failed}")
    conn.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
