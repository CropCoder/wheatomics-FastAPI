#!/usr/bin/env python3
"""Backfill cloned_gene_tbl.publication_year from Crossref by DOI.

For every row where publication_year is empty but paper_doi is present,
look up each DOI via the Crossref REST API and set publication_year to
the earliest year found across that row's DOIs. Re-runs are idempotent:
only rows with NULL/empty publication_year are touched.

paper_doi is a legacy multi-value field joined with '###' (see
app/services/legacy_parsers.py::split_legacy_multi_value), so a single
record may carry several DOIs.

Run on the server (needs pymysql + requests + network):

    cd /var/www/FastAPI_backend_Port8000
    python3 scripts/backfill_publication_year.py            # apply
    python3 scripts/backfill_publication_year.py --dry-run  # preview only

Crossref's polite pool asks for a mailto in the User-Agent; we use the
project contact address. ~1 RPS is comfortably within Crossref limits.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

try:
    import pymysql
except ImportError:
    pymysql = None  # type: ignore[assignment]

try:
    import requests
except ImportError:
    sys.exit("requests is required: pip install requests")


# ---------------------------------------------------------------------------
# Configuration — mirrors app/core/config.py defaults
# ---------------------------------------------------------------------------
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "wheatomics_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "wheatomics115599")
DB_NAME = os.environ.get("DB_CLONED_GENE", "cloned_gene_db")

CROSSREF_BASE = "https://api.crossref.org/works"
CONTACT_MAILTO = os.environ.get("CROSSREF_MAILTO", "shengweima@icloud.com")
USER_AGENT = f"WheatOmics-backfill/1.0 (mailto:{CONTACT_MAILTO})"
TIMEOUT = 30
DELAY_SEC = 1.0


def split_dois(raw: str | None) -> list[str]:
    """Split a legacy '###'-joined paper_doi into clean DOI strings."""

    if not raw:
        return []
    out: list[str] = []
    for part in str(raw).split("###"):
        d = part.strip()
        if not d:
            continue
        # strip any URL prefix the submitter may have pasted
        d = d.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
        if d:
            out.append(d)
    return out


def fetch_year(doi: str) -> int | None:
    """Return the publication year for a DOI from Crossref, or None."""

    headers = {"User-Agent": USER_AGENT}
    url = f"{CROSSREF_BASE}/{requests.utils.quote(doi, safe='')}"
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as exc:
        print(f"  FAIL  {doi}  (network: {exc})")
        return None
    if resp.status_code == 404:
        print(f"  miss  {doi}  (not in Crossref)")
        return None
    if resp.status_code != 200:
        print(f"  FAIL  {doi}  (HTTP {resp.status_code})")
        return None

    try:
        msg = resp.json().get("message", {})
    except ValueError:
        print(f"  FAIL  {doi}  (bad JSON)")
        return None

    # Crossref stores dates as {'date-parts': [[YYYY, MM, DD]]}. Prefer
    # the formal publication date, then the online-ahead date, then the
    # issued/created fallbacks.
    for key in ("published", "published-online", "published-print", "issued", "created"):
        node = msg.get(key) or {}
        parts = node.get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            return int(parts[0][0])
    print(f"  miss  {doi}  (no date-parts in Crossref record)")
    return None


def pick_year(dois: list[str]) -> int | None:
    """Earliest publication year across a row's DOIs."""

    years: list[int] = []
    for doi in dois:
        y = fetch_year(doi)
        if y is not None:
            years.append(y)
        time.sleep(DELAY_SEC)
    if not years:
        return None
    return min(years)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="preview without writing to the DB")
    args = ap.parse_args()

    if pymysql is None:
        sys.exit("pymysql is required: pip install pymysql")

    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, charset="utf8mb4", autocommit=False,
    )

    total = filled = failed = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT clone_id, paper_doi FROM cloned_gene_tbl "
                "WHERE (publication_year IS NULL OR publication_year = '') "
                "AND paper_doi IS NOT NULL AND paper_doi != ''"
            )
            rows = cur.fetchall()
        total = len(rows)
        print(f"{total} row(s) with empty publication_year but a paper_doi.\n")

        for clone_id, paper_doi in rows:
            dois = split_dois(paper_doi)
            if not dois:
                print(f"skip  clone_id={clone_id}  (paper_doi unparsable: {paper_doi!r})")
                failed += 1
                continue
            print(f"clone_id={clone_id}  dois={dois}")
            year = pick_year(dois)
            if year is None:
                print(f"  → no year resolved; leaving publication_year empty\n")
                failed += 1
                continue
            print(f"  → publication_year = {year}\n")
            if not args.dry_run:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE cloned_gene_tbl SET publication_year = %s WHERE clone_id = %s",
                        (year, clone_id),
                    )
                conn.commit()
            filled += 1
    finally:
        conn.close()

    mode = "DRY-RUN" if args.dry_run else "APPLIED"
    print(f"done ({mode}): {total} candidates, {filled} filled, {failed} unresolved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
