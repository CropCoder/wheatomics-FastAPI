#!/usr/bin/env python3
"""Renumber Genefunc_registry.display_order by Group + table name.

Orders the 86 visible genomes by the `Group` column using a fixed
priority (Allohexaploid -> Tetraploid -> Diploid -> Barley -> Other
Triticeae), and within each group by table_name (alphabetical).
display_order is reassigned 1, 2, 3, ... continuously.

Run on the server (UPDATE is DML, so wheatomics_user is enough):

    # dry-run (default): prints proposed new order, writes nothing
    python3 scripts/reorder_genefunc_registry.py

    # apply
    python3 scripts/reorder_genefunc_registry.py --apply

Any Group value not in the priority map sorts after the known ones
(alphabetically). Empty Group sorts last.
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

GROUP_PRIORITY = {
    "allohexaploid": 1,
    "tetraploid": 2,
    "diploid": 3,
    "barley": 4,
    "other triticeae": 5,
}

# Pinned to the top of the dropdown in this exact order, regardless of
# group / ploidy / name. Names must match Genefunc_registry.table_name
# AFTER any renames (e.g. the v1.0 table was Genefunc_table and is now
# Genefunc_CS_IWGSCv1.0_table).
PINNED_TABLES = [
    "Genefunc_CS_IWGSCv1.0_table",
    "Genefunc_CS_IWGSC03G_table",
    "Genefunc_CS_CAU_table",
    "Genefunc_CS_IAAS_table",
]

# Within the Diploid and Other-Triticeae groups, sort by the ploidy
# letters (Polyploidy column) before table_name. AABBDD/AABB/AA/DD/SS get
# a fixed priority; anything else falls to 6 and sorts alphabetically.
PLOIDY_LETTER_PRIORITY = {
    "aabbdd": 1,
    "aabb": 2,
    "aa": 3,
    "dd": 4,
    "ss": 5,
}

PLOIDY_SORTED_GROUPS = {"diploid", "other triticeae"}


def group_rank(value):
    if not value:
        return 99
    return GROUP_PRIORITY.get(value.strip().lower(), 50)


def ploidy_rank_for(group_value, ploidy_value):
    """Ploidy-based rank, but only for Diploid / Other Triticeae groups."""
    if (group_value or "").strip().lower() not in PLOIDY_SORTED_GROUPS:
        return 0
    if not ploidy_value:
        return 6
    return PLOIDY_LETTER_PRIORITY.get(ploidy_value.strip().lower(), 6)


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
        SELECT id, table_name, COALESCE(`Group`, '') AS grp,
               COALESCE(Polyploidy, '') AS ploidy,
               COALESCE(chromosome_level, '') AS chrom,
               display_order
        FROM Genefunc_registry
        WHERE visible = 1
        """
    )
    rows = cursor.fetchall()

    pinned_index = {name: i for i, name in enumerate(PINNED_TABLES)}

    def pin_rank(r):
        name = r["table_name"]
        return pinned_index.get(name, 9999)

    rows.sort(
        key=lambda r: (
            pin_rank(r),
            group_rank(r["grp"]),
            ploidy_rank_for(r["grp"], r["ploidy"]),
            # for Diploid/Other Triticeae: tiebreak by ploidy letters,
            # then table_name; for other groups ploidy_rank_for is 0 so
            # this collapses to table_name order.
            (r["ploidy"] or "").lower() if (r["grp"] or "").strip().lower() in PLOIDY_SORTED_GROUPS else "",
            (r["table_name"] or "").lower(),
            r["id"],
        )
    )

    print(f"DB: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"mode: {'APPLY' if args.apply else 'DRY-RUN'}  rows: {len(rows)}")
    print()
    print(f"{'new':>4}  {'old':>4}  {'group':<22} {'ploidy':<12} table_name")
    print("-" * 90)
    to_update = []
    for new_order, r in enumerate(rows, 1):
        old = r["display_order"]
        flag = "" if old == new_order else "  <- change"
        print(f"{new_order:>4}  {old!s:>4}  {r['grp']:<22} {r['ploidy']:<12} {r['table_name']}{flag}")
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
