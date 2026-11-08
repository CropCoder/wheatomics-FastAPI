#!/usr/bin/env python3
"""Build the journal -> ISSN map used by the literature search.

``papers.journal`` stores PubMed MedAbbr strings which are inconsistent
(trailing spaces, abbreviations, occasional renames).  Journal impact factors
are keyed by ISSN, so we resolve each distinct ``papers.journal`` value to the
ISSN(s) PubMed itself reports for that journal (MEDLINE ``IS`` field of any one
paper), which is authoritative and needs no fuzzy name matching.

Usage (on the production node, from the repo root):

    /home/fei/mambaforge/envs/new_env/bin/python \
        scripts/journal_metrics/build_journal_issn_map.py \
        --out /var/www/html/literature_auto/journal_issn_map.csv

The script reads DB credentials from the environment (DB_HOST/DB_USER/
DB_PASSWORD/DB_TRITICEAE), then falls back to the repo ``.env`` file.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

import pymysql

REPO = Path(__file__).resolve().parents[2]


def load_db_config() -> dict:
    cfg = {
        "host": os.environ.get("DB_HOST") or "localhost",
        "user": os.environ.get("DB_USER") or "wheatomics_user",
        "password": os.environ.get("DB_PASSWORD") or "",
        "database": os.environ.get("DB_TRITICEAE") or "Triticeae_Research_filter",
    }
    if not cfg["password"] and (REPO / ".env").exists():
        env = (REPO / ".env").read_text(encoding="utf-8", errors="replace")
        for line in env.splitlines():
            m = re.match(r"^(DB_[A-Z_]+)\s*=\s*(.*)$", line)
            if not m:
                continue
            key, value = m.group(1), m.group(2).strip().strip('"').strip("'")
            if value:
                if key == "DB_HOST":
                    cfg["host"] = value
                elif key == "DB_USER":
                    cfg["user"] = value
                elif key == "DB_PASSWORD":
                    cfg["password"] = value
                elif key == "DB_TRITICEAE":
                    cfg["database"] = value
    return cfg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/var/www/html/literature_auto/journal_issn_map.csv")
    ap.add_argument("--email", default="wheatomics@sdau.edu.cn", help="NCBI Entrez contact email")
    args = ap.parse_args()

    from Bio import Entrez, Medline  # imported lazily: only needed here

    cfg = load_db_config()
    conn = pymysql.connect(host=cfg["host"], user=cfg["user"], password=cfg["password"],
                           database=cfg["database"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    cur = conn.cursor()
    cur.execute("SELECT journal, COUNT(*) AS n FROM papers GROUP BY journal ORDER BY n DESC")
    journals = cur.fetchall()
    print("journals:", len(journals))

    Entrez.email = args.email
    sample_pmids: dict[str, str] = {}
    for row in journals:
        cur.execute("SELECT pmid FROM papers WHERE journal = %s ORDER BY id LIMIT 1", (row["journal"],))
        rec = cur.fetchone()
        if rec:
            sample_pmids[row["journal"]] = rec["pmid"]
    conn.close()

    ids = list(sample_pmids.values())
    records: dict[str, dict] = {}
    for start in range(0, len(ids), 50):
        handle = Entrez.efetch(db="pubmed", id=",".join(ids[start:start + 50]),
                               rettype="medline", retmode="text")
        for rec in Medline.parse(handle):
            records[rec.get("PMID")] = rec
        handle.close()

    out_rows = []
    for row in journals:
        pmid = sample_pmids.get(row["journal"], "")
        rec = records.get(pmid, {})
        issns = []
        raw = rec.get("IS") or []
        if isinstance(raw, str):
            raw = [raw]
        for value in raw:
            m = re.match(r"([0-9]{4}-[0-9]{3}[0-9Xx])", str(value).strip())
            if m and m.group(1).upper() not in issns:
                issns.append(m.group(1).upper())
        out_rows.append({
            "journal_db": row["journal"],
            "papers": row["n"],
            "pubmed_TA": rec.get("TA") or "",
            "issn": ";".join(issns),
            "sample_pmid": pmid,
        })
        print("%-45s | TA=%-28s | ISSN=%s" % (row["journal"], rec.get("TA") or "", ";".join(issns)))

    missing = [r["journal_db"] for r in out_rows if not r["issn"]]
    print("\njournals: %d | with ISSN: %d | missing: %s" % (len(out_rows), len(out_rows) - len(missing), missing))

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["journal_db", "papers", "pubmed_TA", "issn", "sample_pmid"])
        writer.writeheader()
        writer.writerows(out_rows)
    print("written:", args.out)
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
