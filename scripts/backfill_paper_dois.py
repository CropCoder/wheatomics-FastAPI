#!/usr/bin/env python3
"""Fill papers.doi for rows that have no DOI (run after the weekly import).

The weekly papers import may insert new PMIDs without a DOI; this script fetches
the missing DOIs from PubMed esummary in batches and updates the DB. App user
wheatomics_user has UPDATE on Triticeae_Research_filter.

cron example (Monday 05:00):
  0 5 * * 1 cd /var/www/FastAPI_backend_Port8000 && \
    /home/fei/mambaforge/envs/zjw/bin/python3 scripts/backfill_paper_dois.py
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql

from app.core.config import settings

ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


def fetch(batch: list[str]) -> dict:
    data = urllib.parse.urlencode(
        {"db": "pubmed", "id": ",".join(batch), "retmode": "json"}
    ).encode()
    req = urllib.request.Request(
        ESUMMARY, data=data, headers={"User-Agent": "wheatomics-doi-backfill/1.0"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def main() -> None:
    conn = pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_TRITICEAE,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pmid FROM papers WHERE (doi IS NULL OR doi='') "
                "AND pmid IS NOT NULL AND pmid <> ''"
            )
            pmids = sorted({str(r["pmid"]).strip() for r in cur.fetchall() if str(r["pmid"]).strip().isdigit()})
            print(f"missing DOIs: {len(pmids)}", flush=True)
            found = 0
            for i in range(0, len(pmids), 500):
                batch = pmids[i:i + 500]
                try:
                    res = fetch(batch).get("result", {})
                except Exception as exc:
                    print(f"batch {i} failed: {exc!r}", flush=True)
                    continue
                updates = []
                for pmid in batch:
                    entry = res.get(pmid) or {}
                    doi = ""
                    for aid in (entry.get("articleids") or []):
                        if str(aid.get("idtype", "")).lower() == "doi":
                            doi = (aid.get("value") or "").strip()
                            break
                    if not doi:
                        m = re.search(r"10\.\d{4,9}/[^\s\"<>]+", str(entry.get("elocationid") or ""))
                        if m:
                            doi = m.group(0).rstrip(".")
                    if doi:
                        updates.append((doi, pmid))
                if updates:
                    cur.executemany(
                        "UPDATE papers SET doi=%s WHERE pmid=%s AND (doi IS NULL OR doi='')",
                        updates,
                    )
                    found += len(updates)
                print(f"processed {min(i + 500, len(pmids))} / {len(pmids)} found {found}", flush=True)
                time.sleep(0.35)
            conn.commit()
            print(f"done: filled {found} DOIs", flush=True)


if __name__ == "__main__":
    main()
