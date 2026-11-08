#!/usr/bin/env python3
"""Create/refresh `journal_alias` + `journal_metrics` in the Triticeae papers DB.

Background
----------
`papers.journal` holds PubMed MedAbbr strings ("Theor Appl Genet", "Journal of
Experimental Botany " with a trailing space, ...) which cannot be reliably
matched to a JCR/JCR-like table by name.  The search therefore joins:

    papers.journal  ->  journal_alias.issn  ->  journal_metrics.jif / quartile

`journal_alias` is produced from PubMed's own ISSN for each journal (see
build_journal_issn_map.py); `journal_metrics` is loaded from a JCR export CSV
(ISSN / eISSN / JIF <year> / JIF Quartile / Journal Name).  A JCR export from
the institution is preferred; any CSV with those columns works, and the
`--source` label is shown in the UI next to the number.

This script needs DDL rights (CREATE TABLE), so it uses the DB *root* account:
env DB_ROOT_USER / DB_ROOT_PASSWORD, else `database` in
/var/www/html/literature_auto/config.example.json, else CLI flags.

Usage:
    python3 scripts/journal_metrics/import_journal_metrics.py \
        --jcr-csv /tmp/JCR_2024.csv \
        --issn-map /var/www/html/literature_auto/journal_issn_map.csv \
        --jcr-year 2024 --source JCR2024 \
        --alias-rename "0379-4172:1673-8527"   # Yi Chuan Xue Bao -> J Genet Genomics
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
from pathlib import Path

import pymysql

CONFIG_EXAMPLE = Path("/var/www/html/literature_auto/config.example.json")

DDL = [
    """
    CREATE TABLE IF NOT EXISTS journal_alias (
        journal_db  VARCHAR(255) NOT NULL,
        issn        VARCHAR(16)  NOT NULL,
        source      VARCHAR(32)  NOT NULL DEFAULT 'pubmed',
        PRIMARY KEY (journal_db),
        KEY idx_journal_alias_issn (issn)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS journal_metrics (
        issn              VARCHAR(16)  NOT NULL,
        journal_canonical VARCHAR(255) DEFAULT NULL,
        jif               DECIMAL(8,3)  DEFAULT NULL,
        jcr_year          SMALLINT      DEFAULT NULL,
        quartile          VARCHAR(4)    DEFAULT NULL,
        category          VARCHAR(255)  DEFAULT NULL,
        source            VARCHAR(64)   NOT NULL DEFAULT '',
        updated_at        TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                      ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (issn)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]

ISSN_RE = re.compile(r"^[0-9]{4}-[0-9]{3}[0-9Xx]$")


def clean_issn(value: str) -> str | None:
    value = str(value or "").strip().upper()
    return value if ISSN_RE.match(value) else None


def root_credentials(args) -> dict:
    if args.root_user and args.root_password:
        return {"user": args.root_user, "password": args.root_password, "host": args.db_host}
    if os.environ.get("DB_ROOT_USER") and os.environ.get("DB_ROOT_PASSWORD"):
        return {"user": os.environ["DB_ROOT_USER"], "password": os.environ["DB_ROOT_PASSWORD"],
                "host": os.environ.get("DB_HOST", args.db_host)}
    if CONFIG_EXAMPLE.exists():
        cfg = json.loads(CONFIG_EXAMPLE.read_text(encoding="utf-8"))["database"]
        return {"user": cfg["user"], "password": cfg["password"], "host": cfg.get("host", args.db_host)}
    raise SystemExit("No DB root credentials: set DB_ROOT_USER/DB_ROOT_PASSWORD or pass --root-user/--root-password")


def find_header(headers: list[str], *candidates: str) -> str | None:
    lower = {h.strip().lower(): h for h in headers}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jcr-csv", required=True, help="JCR/Journal-metric CSV (ISSN, eISSN, JIF <year>, JIF Quartile, Journal Name)")
    ap.add_argument("--issn-map", default="/var/www/html/literature_auto/journal_issn_map.csv",
                    help="CSV from build_journal_issn_map.py (journal_db, ..., issn)")
    ap.add_argument("--jcr-year", type=int, default=2024)
    ap.add_argument("--source", default="JCR2024", help="Label stored with each metric row and shown in the UI")
    ap.add_argument("--db", default="Triticeae_Research_filter")
    ap.add_argument("--db-host", default="localhost")
    ap.add_argument("--root-user", default="")
    ap.add_argument("--root-password", default="")
    ap.add_argument("--alias-rename", action="append", default=[],
                    help="OLD_ISSN:NEW_ISSN (journal renamed; alias keeps the new ISSN), repeatable")
    args = ap.parse_args()

    renames = {}
    for pair in args.alias_rename:
        old, _, new = pair.partition(":")
        old, new = clean_issn(old), clean_issn(new)
        if old and new:
            renames[old] = new

    creds = root_credentials(args)
    conn = pymysql.connect(host=creds["host"], user=creds["user"], password=creds["password"],
                           database=args.db, charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor, autocommit=False)
    cur = conn.cursor()
    for ddl in DDL:
        cur.execute(ddl)
    conn.commit()
    print("tables ready")

    # ---- 1) journal_alias from the PubMed-derived journal -> ISSN map --------
    alias_rows = []
    with open(args.issn_map, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            journal = (row.get("journal_db") or "").strip()
            issns = [clean_issn(x) for x in (row.get("issn") or "").split(";")]
            issns = [x for x in issns if x]
            if not journal or not issns:
                continue
            issn = issns[0]
            if issn in renames:
                issn = renames[issn]
            alias_rows.append((journal, issn))
    cur.executemany(
        "INSERT INTO journal_alias (journal_db, issn, source) VALUES (%s, %s, 'pubmed') "
        "ON DUPLICATE KEY UPDATE issn = VALUES(issn), source = VALUES(source)",
        alias_rows,
    )
    conn.commit()
    print("journal_alias rows:", len(alias_rows))

    # ---- 2) journal_metrics from the JCR CSV --------------------------------
    with open(args.jcr_csv, encoding="utf-8-sig", errors="replace") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        col_print = find_header(headers, "ISSN", "ISSN (Print)", "print ISSN")
        col_elect = find_header(headers, "eISSN", "ISSN (Electronic)", "electronic ISSN")
        col_name = find_header(headers, "Journal Name", "Journal Title", "journal")
        col_quart = find_header(headers, "JIF Quartile", "Quartile", "JCR Quartile")
        col_year = find_header(headers, "JCR Year", "Year")
        col_cat = find_header(headers, "Areas", "Category", "Subject")
        # "JIF 2024" is the year-specific factor; fall back to a plain "JIF".
        col_jif = None
        for h in headers:
            if re.match(r"^JIF\s+" + str(args.jcr_year) + r"$", h.strip(), re.I):
                col_jif = h
                break
        if not col_jif:
            col_jif = find_header(headers, "JIF", "Impact Factor", "JIF 2024")
        if not (col_print or col_elect) or not col_jif:
            raise SystemExit(f"cannot find ISSN/JIF columns in {args.jcr_csv}: {headers}")

        metric_rows = []
        for row in reader:
            name = (row.get(col_name) or "").strip() if col_name else ""
            try:
                jif = float(str(row.get(col_jif) or "").strip())
            except ValueError:
                continue
            quartile = (row.get(col_quart) or "").strip().upper() if col_quart else ""
            try:
                year = int(row.get(col_year) or args.jcr_year) if col_year else args.jcr_year
            except ValueError:
                year = args.jcr_year
            category = (row.get(col_cat) or "").strip()[:255] if col_cat else ""
            for raw in (row.get(col_print) or "", row.get(col_elect) or ""):
                issn = clean_issn(raw)
                if issn:
                    metric_rows.append((issn, name[:255], jif, year, quartile or None, category, args.source))
    # dedupe by ISSN (print row wins because it is inserted first)
    seen, deduped = set(), []
    for m in metric_rows:
        if m[0] in seen:
            continue
        seen.add(m[0])
        deduped.append(m)
    cur.executemany(
        "INSERT INTO journal_metrics (issn, journal_canonical, jif, jcr_year, quartile, category, source) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) "
        "ON DUPLICATE KEY UPDATE journal_canonical=VALUES(journal_canonical), jif=VALUES(jif), "
        "jcr_year=VALUES(jcr_year), quartile=VALUES(quartile), category=VALUES(category), source=VALUES(source)",
        deduped,
    )
    conn.commit()
    print("journal_metrics rows:", len(deduped))

    # ---- 3) coverage report --------------------------------------------------
    cur.execute("SELECT COUNT(*) AS n FROM journal_alias")
    n_alias = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM journal_metrics")
    n_metrics = cur.fetchone()["n"]
    cur.execute(
        "SELECT COUNT(*) AS n FROM papers p "
        "JOIN journal_alias ja ON ja.journal_db = p.journal "
        "JOIN journal_metrics jm ON jm.issn = ja.issn"
    )
    n_papers = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM papers")
    n_total = cur.fetchone()["n"]
    print("coverage: alias=%d metrics=%d | papers with metric=%d/%d (%.1f%%)"
          % (n_alias, n_metrics, n_papers, n_total, 100.0 * n_papers / max(1, n_total)))
    cur.execute(
        "SELECT p.journal, COUNT(*) AS n FROM papers p "
        "LEFT JOIN journal_alias ja ON ja.journal_db = p.journal "
        "LEFT JOIN journal_metrics jm ON jm.issn = ja.issn "
        "WHERE jm.issn IS NULL GROUP BY p.journal ORDER BY n DESC"
    )
    missing = cur.fetchall()
    if missing:
        print("journals without metric:")
        for row in missing:
            print("  %-45r %d" % (row["journal"], row["n"]))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
