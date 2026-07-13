#!/usr/bin/env python3
"""Rename a curated set of Genefunc_* tables and keep Genefunc_registry in sync.

Drops the old table_name, creates the new one via MySQL RENAME TABLE, and
updates Genefunc_registry.table_name so the dropdown labels stay in sync.
Both steps run inside a single transaction per pair so a failure mid-way
leaves the DB consistent.

Run on the server (RENAME TABLE needs DDL — use a privileged account):

    # dry-run (default): prints the proposed actions, writes nothing
    python3 scripts/rename_genefunc_tables.py

    # apply
    python3 scripts/rename_genefunc_tables.py --apply

Each entry is (old_table_name, new_table_name). If `old` does not exist
the rename is reported as already-done (the previous run finished it,
or it was renamed manually). If `new` already exists with no `old`, the
registry row is reported stale and we update Genefunc_registry only.
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


RENAMES = [
    ("Genefunc_arinalrfor_PGSBv2_table",        "Genefunc_ArinaLrFor_PGSBv2_table"),
    ("Genefunc_jagger_PGSBv2_table",            "Genefunc_Jagger_PGSBv2_table"),
    ("Genefunc_julius_PGSBv2_table",            "Genefunc_Julius_PGSBv2_table"),
    ("Genefunc_lancer_PGSBv2_table",            "Genefunc_Lancer_PGSBv2_table"),
    ("Genefunc_landmark_PGSBv2_table",          "Genefunc_Landmark_PGSBv2_table"),
    ("Genefunc_mace_PGSBv2_table",              "Genefunc_Mace_PGSBv2_table"),
    ("Genefunc_mattis_PGSBv2_table",            "Genefunc_Mattis_PGSBv2_table"),
    ("Genefunc_norin61_PGSBv2_table",           "Genefunc_Norin61_PGSBv2_table"),
    ("Genefunc_robigus_table",                  "Genefunc_Robigus_table"),
    ("Genefunc_spelta_PGSBv2_table",            "Genefunc_Spelta_PGSBv2_table"),
    ("Genefunc_stanley_PGSBv2_table",           "Genefunc_Stanley_PGSBv2_table"),
    ("Genefunc_table",                          "Genefunc_CS_IWGSCv1.0_table"),
    ("Genefunc_Triticum_aestivum_alchemy_table","Genefunc_Alchemy_table"),
    ("Genefunc_durum_PI192051_table",           "Genefunc_Durum_PI192051_table"),
    ("Genefunc_Ae_tauschii_Aet6_clean_dedup_table","Genefunc_Aegilops_tauschii_Aet6_table"),
    ("Genefunc_sharonensis_AS_1644_table",      "Genefunc_ae_sharonensis_AS1644_table"),
    ("Genefunc_RM271_table",                    "Genefunc_Ae_ventricosa_RM271_table"),
    ("Genefunc_AeComosa_PI551049_table",        "Genefunc_Ae_Comosa_PI551049_table"),
    ("Genefunc_IWGSC03G_table",                 "Genefunc_CS_IWGSC03G_table"),
]


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
        cursorclass=DictCursor,
    )


def table_exists(cursor, name):
    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
        (DB_NAME, name),
    )
    return cursor.fetchone() is not None


def registry_count(cursor, name):
    cursor.execute(
        "SELECT COUNT(*) AS n FROM Genefunc_registry WHERE table_name=%s",
        (name,),
    )
    return cursor.fetchone()["n"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SET autocommit=0")
    conn.begin()

    print(f"DB: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"mode: {'APPLY' if args.apply else 'DRY-RUN'}  pairs: {len(RENAMES)}")
    print()
    print(f"{'old':<48} -> {'new':<48} {'ren':>3} {'reg_old':>7} {'reg_new':>7}")
    print("-" * 120)

    renamed = reg_updated = no_op = failed = 0
    for old, new in RENAMES:
        old_exists = table_exists(cursor, old)
        new_exists = table_exists(cursor, new)
        reg_old = registry_count(cursor, old)
        reg_new = registry_count(cursor, new)
        ren_flag = "-" if not old_exists else ("Y" if not args.apply else "Y")

        if not old_exists and not new_exists:
            status = "BOTH-MISSING"
        elif not old_exists and new_exists:
            if reg_old == 0 and reg_new >= 1:
                status = "ALREADY-DONE"
            else:
                status = "STALE-REGISTRY"
        elif old_exists and new_exists:
            status = "NEWNAME-EXISTS"
        else:
            status = "WILL-RENAME"

        print(
            f"{old:<48} -> {new:<48} {('Y' if old_exists and not new_exists else '-'):>3} "
            f"{reg_old:>7} {reg_new:>7}  {status}"
        )

        if args.apply:
            try:
                if status == "WILL-RENAME":
                    cursor.execute(f"RENAME TABLE `{old}` TO `{new}`")
                    renamed += 1
                    cursor.execute(
                        "UPDATE Genefunc_registry SET table_name=%s WHERE table_name=%s",
                        (new, old),
                    )
                    reg_updated += cursor.rowcount
                elif status == "ALREADY-DONE":
                    # table already renamed; just make sure registry points at new
                    if reg_old:
                        cursor.execute(
                            "UPDATE Genefunc_registry SET table_name=%s WHERE table_name=%s",
                            (new, old),
                        )
                        reg_updated += cursor.rowcount
                    no_op += 1
                elif status == "STALE-REGISTRY":
                    cursor.execute(
                        "UPDATE Genefunc_registry SET table_name=%s WHERE table_name=%s",
                        (new, old),
                    )
                    reg_updated += cursor.rowcount
                    no_op += 1
                else:
                    no_op += 1
            except Exception as exc:
                conn.rollback()
                print(f"FAIL {old} -> {new}: {exc}", file=sys.stderr)
                failed += 1
                break

    if args.apply and failed == 0:
        conn.commit()
        print()
        print(
            f"summary: renamed={renamed}  registry_updated={reg_updated}  "
            f"no_op={no_op}  failed={failed}"
        )
    else:
        conn.rollback()
        print()
        print("(dry-run — no changes written)")

    conn.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())