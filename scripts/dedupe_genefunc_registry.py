#!/usr/bin/env python3
"""Deduplicate Genefuncdb.Genefunc_registry rows that share one display name.

The registry accumulated two kinds of rows for the same genome annotation:

* legacy ``Genefunc_<Name>_table``          (old CGI-era import)
* modern ``Genefunc_<PLOIDY>_<Name>_table`` (current pipeline)

Both point at the same gene models, so the getfasta "Supported genomes" chips
and the gene-function table picker show each genome twice. This script keeps one
row per genome and hides the redundant one (``visible = 0``); tables and data are
never deleted.

Decision rules
--------------
1. Group visible rows by ``display_name``.
2. Row whose table does not exist in ``Genefuncdb`` -> hide (broken reference).
3. Otherwise compare row counts of every table in the group:
   * all equal  -> keep the modern table (``Genefunc_<PLOIDY>_..._table``),
                   hide the legacy one(s)
   * unequal    -> leave untouched and report (may be genuinely different
                   annotation versions; rename manually instead of hiding)
4. ``--apply`` writes ``visible = 0``; ``--dry-run`` (default) only reports.

Usage:
    python3 scripts/dedupe_genefunc_registry.py --dry-run
    python3 scripts/dedupe_genefunc_registry.py --apply
"""
from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path
import sys

PLOIDY_RE = re.compile(
    r"^Genefunc_(AABBDD|AABBRR|AABB|AAGG|DDNN|ATATGG|NSNSXMXM|STSTYYHH|STSTVVJJ|"
    r"HHHH|HH|AA|DD|SS|MM|RR|UU|VV|EE|TT|PP|GG)_",
    re.I,
)


def db():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.core.config import settings
    from app.db.mysql import mysql_cursor

    return settings, mysql_cursor


def is_modern(table: str) -> bool:
    return bool(PLOIDY_RE.match(table))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    dry = not args.apply

    settings, mysql_cursor = db()
    with mysql_cursor(settings.DB_GENEFUNC) as cur:
        cur.execute(
            "SELECT table_name, display_name, IFNULL(Doi,'') AS doi, visible "
            "FROM Genefunc_registry WHERE visible = 1 ORDER BY display_name, table_name"
        )
        rows = cur.fetchall()
        cur.execute("SHOW TABLES")
        existing = {list(r.values())[0] for r in cur.fetchall()}

    groups = defaultdict(list)
    for r in rows:
        groups[r["display_name"]].append(r)

    to_hide, untouched = [], []
    for name, items in groups.items():
        if len(items) < 2:
            continue
        missing = [i for i in items if i["table_name"] not in existing]
        if missing:
            to_hide.extend(missing)
            items = [i for i in items if i["table_name"] in existing]
            if len(items) < 2:
                continue
        counts = {}
        with mysql_cursor(settings.DB_GENEFUNC) as cur:
            for it in items:
                cur.execute(f"SELECT COUNT(*) AS n FROM `{it['table_name']}`")
                counts[it["table_name"]] = cur.fetchone()["n"]
        if len(set(counts.values())) != 1:
            untouched.append((name, counts))
            continue
        keep = next((i for i in items if is_modern(i["table_name"])), items[0])
        for it in items:
            if it is not keep:
                to_hide.append(it)

    print(f"duplicate groups        : {sum(1 for v in groups.values() if len(v) > 1)}")
    print(f"rows to hide            : {len(to_hide)}")
    print(f"groups with unequal rows: {len(untouched)}")
    for it in to_hide:
        print(f"  HIDE {it['table_name']:<58} ({it['display_name']})")
    for name, counts in untouched:
        print(f"  KEEP ALL {name:<40} {counts}")

    if dry:
        print("\n(dry-run: nothing written; re-run with --apply)")
        return 0

    with mysql_cursor(settings.DB_GENEFUNC) as cur:
        for it in to_hide:
            cur.execute(
                "UPDATE Genefunc_registry SET visible = 0 WHERE table_name = %s",
                (it["table_name"],),
            )
    print(f"\nhid {len(to_hide)} duplicate rows (visible=0, data untouched)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
