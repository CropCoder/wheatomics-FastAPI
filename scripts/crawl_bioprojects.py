#!/usr/bin/env python3
"""Crawl metadata for the 73 bioprojects that back CO_BioticStress_2026
and persist into `coexpressiondb.bioproject_meta`.

Sources:
  PRJNA*  → NCBI E-utilities (esearch + esummary)
  PRJEB*  → ENA portal API
  PRJCA*  → CNGB (best-effort; single project; skipped if API unreachable)

Run on the server (or any host with pymysql + requests + network access):

    cd /var/www/FastAPI_backend_Port8000
    python3 scripts/crawl_bioprojects.py

Re-runs are idempotent (INSERT ... ON DUPLICATE KEY UPDATE).

No retry, no rate-limit handling beyond a 1.0s sleep between NCBI calls
(E-utilities allows 3 RPS without an API key, so 1 RPS is comfortably safe).
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

try:
    import pymysql
except ImportError:
    sys.exit("pymysql is required: pip install pymysql")

try:
    import requests
except ImportError:
    sys.exit("requests is required: pip install requests")


# ---------------------------------------------------------------------------
# Configuration — same defaults as app/core/config.py
# ---------------------------------------------------------------------------
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "wheatomics_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "wheatomics115599")
DB_NAME = os.environ.get("DB_COEXPRESSION", "coexpressiondb")

NCBI_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
ENA_PORTAL = "https://www.ebi.ac.uk/ena/portal/api/expand"
CNGB_SEARCH = "https://db.cngb.org/api/v1/search/project/{acc}"

USER_AGENT = "wheatomics-fastapi/1.0 (coexpression-bioproject-crawler)"
TIMEOUT = 30  # seconds
NCBI_DELAY_SEC = 1.0  # stay under E-utilities' 3 RPS unofficial limit


# ---------------------------------------------------------------------------
# Accession list — kept in sync with the References block in
# app/static/coexpression/index.html
# ---------------------------------------------------------------------------
ACCESSIONS: list[str] = [
    # NCBI BioProject (PRJNA*)
    "PRJNA1006331", "PRJNA1013391", "PRJNA1103823", "PRJNA1120216",
    "PRJNA1139870", "PRJNA1183537", "PRJNA1186393", "PRJNA1265958",
    "PRJNA1390310", "PRJNA243835", "PRJNA263755", "PRJNA273659",
    "PRJNA297822", "PRJNA325136", "PRJNA387101", "PRJNA387602",
    "PRJNA391049", "PRJNA392366", "PRJNA395300", "PRJNA401295",
    "PRJNA415716", "PRJNA450087", "PRJNA476783", "PRJNA480952",
    "PRJNA484520", "PRJNA485724", "PRJNA523855", "PRJNA613349",
    "PRJNA629995", "PRJNA630776", "PRJNA655118", "PRJNA664372",
    "PRJNA664832", "PRJNA674985", "PRJNA681568", "PRJNA681989",
    "PRJNA683746", "PRJNA718488", "PRJNA731024", "PRJNA737275",
    "PRJNA743515", "PRJNA749387", "PRJNA786911", "PRJNA789469",
    "PRJNA791687", "PRJNA798111", "PRJNA826345", "PRJNA827248",
    "PRJNA836737", "PRJNA838495", "PRJNA842823", "PRJNA843683",
    "PRJNA868874", "PRJNA874550", "PRJNA883377", "PRJNA895679",
    "PRJNA896512", "PRJNA909039", "PRJNA923775", "PRJNA924088",
    "PRJNA957082", "PRJNA972630", "PRJNA972750", "PRJNA975982",
    "PRJNA976214",
    # EBI/ENA (PRJEB*)
    "PRJEB40834", "PRJEB41456", "PRJEB41503", "PRJEB4202",
    "PRJEB44166", "PRJEB63085", "PRJEB70648",
    # CNGB (PRJCA*)
    "PRJCA055232",
]


def source_for(acc: str) -> str:
    if acc.startswith("PRJNA"): return "NCBI"
    if acc.startswith("PRJEB"): return "ENA"
    if acc.startswith("PRJCA"): return "CNGB"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Fetchers — each returns a dict with the canonical keys, or None on failure.
# ---------------------------------------------------------------------------
def _get(url: str, params: dict | None = None) -> dict | None:
    try:
        r = requests.get(url, params=params or {}, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001
        print(f"      fetch error: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def fetch_ncbi(acc: str) -> dict | None:
    """Two-step: esearch resolves accession → UID, esummary returns the record."""
    es = _get(NCBI_ESEARCH, {"db": "bioproject", "term": acc, "retmode": "json"})
    if not es:
        return None
    uids = es.get("esearchresult", {}).get("idlist", [])
    if not uids:
        return None
    time.sleep(NCBI_DELAY_SEC)
    su = _get(NCBI_ESUMMARY, {"db": "bioproject", "id": uids[0], "retmode": "json"})
    if not su:
        return None
    rec = su.get("result", {}).get(uids[0], {})
    if not rec:
        return None
    return {
        "accession":         acc,
        "title":             rec.get("project_title") or rec.get("title"),
        "description":       rec.get("project_description") or rec.get("description"),
        "organism":          rec.get("organism_name") or rec.get("organism"),
        "submitter":         rec.get("submitter") or rec.get("submitter_organization"),
        "submission_date":   _ymd_to_iso(rec.get("registration_date")),
        "publication_date":  _ymd_to_iso(rec.get("publication_date")),
        "data_type":         rec.get("project_data_type") or rec.get("project_type"),
        "sample_count":      _to_int(rec.get("num_samples") or rec.get("sample_count")),
        "study_type":        rec.get("project_type") or rec.get("study_type"),
        "related_pubmed":    _first_pmid(rec.get("pubmedids") or rec.get("pmids")),
        "related_doi":       _first_doi(rec.get("dois") or rec.get("project_doi")),
        "raw_json":          json.dumps(rec, default=str),
    }


def fetch_ena(acc: str) -> dict | None:
    fields = ",".join([
        "study_accession", "study_title", "study_description", "study_abstract",
        "study_organism", "study_submitter", "first_public", "last_updated",
        "study_type", "study_ega_id", "study_links", "study_pubmed_id",
        "study_doi", "sample_count",
    ])
    data = _get(ENA_PORTAL, {"accession": acc, "format": "json", "fields": fields})
    if not data or not isinstance(data, list) or not data:
        return None
    rec = data[0]
    links = rec.get("study_links") or []
    pmid = rec.get("study_pubmed_id") or ""
    return {
        "accession":         acc,
        "title":             rec.get("study_title"),
        "description":       rec.get("study_abstract") or rec.get("study_description"),
        "organism":          rec.get("study_organism"),
        "submitter":         rec.get("study_submitter"),
        "submission_date":   _ymd_to_iso(rec.get("first_public")),
        "publication_date":  _ymd_to_iso(rec.get("last_updated")),
        "data_type":         None,
        "sample_count":      _to_int(rec.get("sample_count")),
        "study_type":        rec.get("study_type"),
        "related_pubmed":    str(pmid) if pmid else None,
        "related_doi":       rec.get("study_doi") or _extract_doi_from_links(links),
        "raw_json":          json.dumps(rec, default=str),
    }


def fetch_cngb(acc: str) -> dict | None:
    url = CNGB_SEARCH.format(acc=acc)
    data = _get(url)
    if not data:
        return None
    rec = data if isinstance(data, dict) else (data[0] if data else {})
    if not rec:
        return None
    return {
        "accession":         acc,
        "title":             rec.get("title") or rec.get("name"),
        "description":       rec.get("description") or rec.get("abstract"),
        "organism":          rec.get("organism") or rec.get("species"),
        "submitter":         rec.get("submitter") or rec.get("owner"),
        "submission_date":   _ymd_to_iso(rec.get("create_time") or rec.get("submission_date")),
        "publication_date":  _ymd_to_iso(rec.get("publish_time") or rec.get("publication_date")),
        "data_type":         rec.get("data_type") or rec.get("library_strategy"),
        "sample_count":      _to_int(rec.get("sample_count") or rec.get("samples")),
        "study_type":        rec.get("study_type") or rec.get("type"),
        "related_pubmed":    rec.get("pubmed_id"),
        "related_doi":       rec.get("doi"),
        "raw_json":          json.dumps(rec, default=str),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ymd_to_iso(s: Any) -> str | None:
    """NCBI / ENA return 'YYYY/MM/DD' or full ISO; pick a YYYY-MM-DD slice."""
    if not s:
        return None
    s = str(s)
    if len(s) >= 10 and s[4:5] in ("-", "/") and s[7:8] in ("-", "/"):
        return s[:4] + "-" + s[5:7] + "-" + s[8:10]
    return s


def _to_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _first_pmid(v: Any) -> str | None:
    if not v:
        return None
    if isinstance(v, str):
        return v.split(",")[0].strip() or None
    if isinstance(v, (list, tuple)) and v:
        return str(v[0])
    return None


def _first_doi(v: Any) -> str | None:
    if not v:
        return None
    if isinstance(v, str):
        return v.split(",")[0].strip() or None
    if isinstance(v, (list, tuple)) and v:
        return str(v[0])
    return None


def _extract_doi_from_links(links: Any) -> str | None:
    if not isinstance(links, list):
        return None
    for item in links:
        if not isinstance(item, dict):
            continue
        for key in ("doi", "DOI", "url"):
            v = item.get(key)
            if v and "doi.org" in str(v).lower():
                return str(v)
    return None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
UPSERT_SQL = """
INSERT INTO bioproject_meta
  (accession, source, title, description, organism, submitter,
   submission_date, publication_date, data_type, sample_count,
   study_type, related_pubmed, related_doi, raw_json)
VALUES
  (%(accession)s, %(source)s, %(title)s, %(description)s, %(organism)s,
   %(submitter)s, %(submission_date)s, %(publication_date)s,
   %(data_type)s, %(sample_count)s, %(study_type)s,
   %(related_pubmed)s, %(related_doi)s, %(raw_json)s)
ON DUPLICATE KEY UPDATE
  source           = VALUES(source),
  title            = VALUES(title),
  description      = VALUES(description),
  organism         = VALUES(organism),
  submitter        = VALUES(submitter),
  submission_date  = VALUES(submission_date),
  publication_date = VALUES(publication_date),
  data_type        = VALUES(data_type),
  sample_count     = VALUES(sample_count),
  study_type       = VALUES(study_type),
  related_pubmed   = VALUES(related_pubmed),
  related_doi      = VALUES(related_doi),
  raw_json         = VALUES(raw_json)
""".strip()


def upsert(cursor, source: str, row: dict) -> bool:
    payload = {"source": source, **row}
    cursor.execute(UPSERT_SQL, payload)
    return True


# ---------------------------------------------------------------------------
# Exporters
# ---------------------------------------------------------------------------
EXPORT_COLUMNS = [
    "accession", "source", "title", "description", "organism", "submitter",
    "submission_date", "publication_date", "data_type", "sample_count",
    "study_type", "related_pubmed", "related_doi", "raw_json",
]


def _sql_literal(v: Any) -> str:
    """Render a Python value as a MySQL SQL literal."""
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, bool):
        return "1" if v else "0"
    # String: escape backslash, single-quote, NUL, and embed.
    s = str(v).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{s}'"


def export_sql(path: str, records: list[tuple[str, dict]]) -> None:
    cols = ", ".join(f"`{c}`" for c in EXPORT_COLUMNS)
    lines = [
        "-- Generated by scripts/crawl_bioprojects.py",
        "-- Apply with: mysql -u <priv_user> -p coexpressiondb < this_file.sql",
        "",
        "USE coexpressiondb;",
        "",
        "INSERT INTO `bioproject_meta` (" + cols + ") VALUES",
    ]
    rows_sql: list[str] = []
    for source, row in records:
        vals = [_sql_literal(row.get(c)) for c in EXPORT_COLUMNS]
        rows_sql.append("  (" + ", ".join(vals) + ")")
    lines.append(",\n".join(rows_sql) + ";")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def export_tsv(path: str, records: list[tuple[str, dict]]) -> None:
    """Tab-separated, no raw_json column (huge); useful for quick review."""
    tsv_cols = [c for c in EXPORT_COLUMNS if c != "raw_json"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\t".join(tsv_cols) + "\n")
        for _source, row in records:
            cells = []
            for c in tsv_cols:
                v = row.get(c)
                if v is None:
                    cells.append("")
                else:
                    s = str(v).replace("\t", " ").replace("\n", " ")
                    cells.append(s)
            f.write("\t".join(cells) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _parse_args(argv: list[str] | None = None) -> dict:
    import argparse
    p = argparse.ArgumentParser(
        description="Crawl bioproject metadata into coexpressiondb.bioproject_meta.",
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Don't connect to MySQL; just fetch and print/save.")
    p.add_argument("--output", metavar="PATH",
                   help="Write the parsed rows to PATH (.tsv or .sql).")
    p.add_argument("--output-format", choices=("tsv", "sql"), default=None,
                   help="Force output format (default: inferred from --output suffix).")
    p.add_argument("--limit", type=int, default=None,
                   help="Stop after N records (for testing).")
    args = p.parse_args(argv)
    out_fmt = args.output_format
    if out_fmt is None and args.output:
        out_fmt = "sql" if args.output.lower().endswith(".sql") else "tsv"
    return {"dry_run": args.dry_run, "output": args.output,
            "output_format": out_fmt, "limit": args.limit}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    explicit_dry = args["dry_run"]
    output_path = args["output"]
    output_format = args["output_format"]
    limit = args["limit"]

    # If --dry-run was passed, or MySQL isn't importable (e.g. running on
    # a dev laptop), skip the connection and just print/save.
    can_db = True
    try:
        import pymysql  # noqa: F401
    except ImportError:
        can_db = False
    dry_run = explicit_dry or not can_db

    conn = None
    if not dry_run:
        print(f"Connecting to MySQL {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME} ...")
        try:
            conn = pymysql.connect(
                host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
                database=DB_NAME, charset="utf8mb4", autocommit=True,
            )
        except Exception as e:  # noqa: BLE001
            print(f"MySQL connection failed: {e}", file=sys.stderr)
            if not explicit_dry:
                print("Re-run with --dry-run to fetch without writing.")
                return 2
            conn = None
    else:
        print("Dry-run mode: skipping MySQL connection.")

    target = ACCESSIONS if limit is None else ACCESSIONS[:limit]
    print(f"Crawling {len(target)} accessions ...")

    ok = 0
    fail = 0
    saved: list[tuple[str, dict]] = []
    cur = conn.cursor() if conn else None
    for i, acc in enumerate(target, 1):
        source = source_for(acc)
        print(f"[{i:2d}/{len(target)}] {acc} ({source}) ... ", end="", flush=True)
        try:
            if source == "NCBI":
                row = fetch_ncbi(acc)
            elif source == "ENA":
                row = fetch_ena(acc)
            elif source == "CNGB":
                row = fetch_cngb(acc)
            else:
                print("SKIP (unknown source)")
                continue
            if row is None:
                print("FAIL (no data)")
                fail += 1
                continue
            if cur is not None:
                upsert(cur, source, row)
            saved.append((source, row))
            title = (row.get("title") or "")[:60]
            print(f"OK   {title!r}")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL ({type(e).__name__}: {e})")
            fail += 1

    if conn is not None:
        conn.close()
    print(f"\nDone. OK={ok}, FAIL={fail}")

    if output_path and saved:
        fmt = output_format or "tsv"
        if fmt == "sql":
            export_sql(output_path, saved)
        else:
            export_tsv(output_path, saved)
        print(f"Wrote {len(saved)} rows to {output_path} ({fmt})")

    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
