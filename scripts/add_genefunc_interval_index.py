#!/usr/bin/env python3
"""Add a (Chrom, Start1, End1) composite index to every Genefunc_* table.

The /api/genes/functions/interval endpoint runs:

    SELECT * FROM <table>
    WHERE Chrom = %s AND Start1 >= %s AND End1 <= %s

Without an index on (Chrom, Start1, End1) this is a full table scan — on a
269k-row table a 5Mb region query takes ~13s. With the index MySQL can do a
range scan along Start1 (and short-circuit once Start1 exceeds the window,
since End1 >= Start1), bringing it under ~100ms.

Run on the server (or any host with pymysql + access to the Genefuncdb
MySQL instance):

    # default creds read from env / fall back to the app's DML account;
    # but DDL needs a privileged user — pass one explicitly:
    DB_USER=root DB_PASSWORD='...' python3 scripts/add_genefunc_interval_index.py

    # dry-run first (shows what would happen, no writes):
    python3 scripts/add_genefunc_interval_index.py --dry-run

    # restrict to a few tables for a quick smoke test:
    python3 scripts/add_genefunc_interval_index.py --only Genefunc_table,Genefunc_IWGSC03G_table

The script is idempotent: it checks information_schema.statistics first and
skips tables that already have an index with the same name. Tables lacking
any of the Chrom / Start1 / End1 columns (e.g. Genefunc_registry) are
skipped with a note.
"""

from __future__ import annotations

import argparse
import os
import sys

try:
    import pymysql
except ImportError:
    pymysql = None  # type: ignore[assignment]


def _require_pymysql() -> None:
    if pymysql is None:
        print("pymysql is required: pip install pymysql", file=sys.stderr)
        sys.exit(2)


DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "wheatomics_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "wheatomics115599")
DB_NAME = os.environ.get("DB_GENEFUNC", "Genefuncdb")

INDEX_NAME = "idx_chrom_start_end"
REQUIRED_COLUMNS = ("Chrom", "Start1", "End1")


def connect() -> "pymysql.Connection":
    _require_pymysql()
    from pymysql.cursors import DictCursor

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


def list_tables(cursor) -> list[str]:
    cursor.execute("SHOW TABLES")
    return [list(row.values())[0] for row in cursor.fetchall()]


def table_columns(cursor, table: str) -> set[str]:
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM information_schema.columns
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        """,
        (DB_NAME, table),
    )
    return {row["COLUMN_NAME"] for row in cursor.fetchall()}


def index_exists(cursor, table: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.statistics
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND INDEX_NAME = %s
        LIMIT 1
        """,
        (DB_NAME, table, INDEX_NAME),
    )
    return cursor.fetchone() is not None


def add_index(cursor, table: str) -> None:
    cursor.execute(
        f"ALTER TABLE `{table}` ADD INDEX `{INDEX_NAME}` "
        f"(`Chrom`, `Start1`, `End1`)"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="actually run ALTER TABLE (default: dry-run)")
    ap.add_argument(
        "--only",
        help="comma-separated table allowlist (default: all Genefunc_* tables)",
    )
    args = ap.parse_args()

    allow = {t.strip() for t in args.only.split(",")} if args.only else None

    conn = connect()
    cursor = conn.cursor()
    tables = sorted(list_tables(cursor))
    candidates = [t for t in tables if allow is None or t in allow]

    print(f"DB: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"tables listed: {len(candidates)}  dry_run={args.dry_run}")
    print()

    done = skipped_index = skipped_cols = failed = 0
    for i, tbl in enumerate(candidates, 1):
        prefix = f"[{i}/{len(candidates)}] {tbl}"

        cols = table_columns(cursor, tbl)
        missing = [c for c in REQUIRED_COLUMNS if c not in cols]
        if missing:
            print(f"{prefix} SKIP (missing columns: {', '.join(missing)})")
            skipped_cols += 1
            continue

        if index_exists(cursor, tbl):
            print(f"{prefix} SKIP (index {INDEX_NAME} already exists)")
            skipped_index += 1
            continue

        if args.dry_run or not args.apply:
            print(f"{prefix} WOULD ADD INDEX {INDEX_NAME} (Chrom, Start1, End1)")
            done += 1
            continue

        try:
            add_index(cursor, tbl)
            print(f"{prefix} OK added {INDEX_NAME}")
            done += 1
        except Exception as exc:
            print(f"{prefix} FAIL {exc}")
            failed += 1

    print()
    print(
        f"summary: added={done}  already_indexed={skipped_index}  "
        f"no_columns={skipped_cols}  failed={failed}"
    )
    conn.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
