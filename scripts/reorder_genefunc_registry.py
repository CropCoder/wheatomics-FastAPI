#!/usr/bin/env python3
"""Renumber Genefunc_registry.display_order by chromosome_level + table name.

Orders the 86 visible genomes so the dropdown shows AABBDD (hexaploid
common wheat) first, then AABB (tetraploid), then the diploid subgenome
donors AA, DD, SS, then everything else — and within each group,
alphabetically by table_name. display_order is reassigned 1, 2, 3, ...
continuously.

Run on the server (UPDATE is DML, so wheatomics_user is enough):

    # dry-run (default): prints proposed new order, writes nothing
    python3 scripts/reorder_genefunc_registry.py

    # apply
    python3 scripts/reorder_genefunc_registry.py --apply

chromosome_level priority (lowest = shown first):
    AABBDD -> 1   (hexaploid common wheat)
    AABB   -> 2   (tetraploid)
    AA     -> 3   (A-subgenome diploid donor)
    DD     -> 4   (D-subgenome diploid donor)
    SS     -> 5   (S-subgenome diploid donor)
    <other> -> 6  (sorted alphabetically within)
Unknown/NULL chromosome_level falls into group 6. Within a group, ties
break by table_name (case-insensitive), then by id.
"""

from __future__ import annotations

import argparse
import os
import sys

try:
    import pymysql
except ImportError:
    pymysql = None  # type: ignore[assignment]


DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "wheatomics_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "wheatomics115599")
DB_NAME = os.environ.get("DB_GENEFUNC", "Genefuncdb")

CHROM_PRIORITY = {
    "aabbdd": 1,
    "aabb": 2,
    "aa": 3,
    "dd": 4,
    "ss": 5,
}


def chrom_rank(value):
    if not value:
        return 6
    return CHROM_PRIORITY.get(value.strip().lower(), 6)


def connect():
    if pymysql is None:
        print("pymysql is required: pip install pymysql", file=sys.stderr)
        sys.exit(2)
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write the new order (default: dry-run)")
    args = ap.parse_args()

    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, table_name, COALESCE(Polyploidy, '') AS ploidy,
               COALESCE(chromosome_level, '') AS chrom,
               COALESCE(`Group`, '') AS grp, display_order
        FROM Genefunc_registry
        WHERE visible = 1
        """
    )
    rows = cursor.fetchall()

    # NOTE: in this DB the `Polyploidy` column holds genome-composition
    # letters (AABBDD / AABB / AA / DD / SS / ...), NOT ploidy words.
    # `chromosome_level` is a Yes/No flag for assembly level. Sort by the
    # composition letters in Polyploidy using the AABBDD-priority map.
    rows.sort(
        key=lambda r: (
            chrom_rank(r["ploidy"]),
            (r["ploidy"] or "").lower(),
            (r["table_name"] or "").lower(),
            r["id"],
        )
    )

    print(f"DB: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"mode: {'APPLY' if args.apply else 'DRY-RUN'}  rows: {len(rows)}")
    print()
    print(f"{'new':>4}  {'old':>4}  {'ploidy':<12} {'chromlvl':<10} table_name")
    print("-" * 80)
    to_update = []
    for new_order, r in enumerate(rows, 1):
        old = r["display_order"]
        flag = "" if old == new_order else "  <- change"
        print(f"{new_order:>4}  {old!s:>4}  {r['ploidy']:<12} {r['chrom']:<10} {r['table_name']}{flag}")
        if old != new_order:
            to_update.append((new_order, r["id"], r["table_name"]))

    print()
    print(f"rows needing change: {len(to_update)} / {len(rows)}")

    if not args.apply:
        print("dry-run only — re-run with --apply to write.")
        conn.close()
        return 0

    if not to_update:
        print("nothing to change.")
        conn.close()
        return 0

    for new_order, _rid, _name in to_update:
        cursor.execute(
            "UPDATE Genefunc_registry SET display_order = %s WHERE id = %s",
            (new_order, _rid),
        )
    print(f"updated {len(to_update)} rows.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
