#!/usr/bin/env python3
"""Import human-approved gene candidates (from scan_gene_annotations.py) into
cloned_gene_tbl (the Known Genes database).

Reads the reviewed candidate_genes_*.csv: only rows with approve=1 are imported.
For each gene the script re-checks duplicates against cloned_gene_tbl (normalized
gene_name / gene_id matching, same rules as the scan step) so a re-run or a
concurrent manual submission can never create a duplicate row.

PMID provenance needs a one-time schema addition (nullable column; the existing
CGI INSERT/UPDATE statements name their columns explicitly, so they are unaffected):

    ALTER TABLE cloned_gene_tbl ADD COLUMN pmid VARCHAR(500) DEFAULT NULL;

The script detects the missing column: by default it prints the ALTER and skips
pmid; with --ensure-pmid-column it runs the ALTER itself.

Dry-run by default — pass --commit to actually insert.

Usage:
  python scripts/import_cloned_genes.py --csv scripts/output/candidate_genes_20260820.csv --dry-run
  python scripts/import_cloned_genes.py --csv scripts/output/candidate_genes_20260820.csv --commit
"""

import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:
    sys.exit("pymysql is required: pip install pymysql")

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 3306
DEFAULT_USER = "wheatomics_user"
DEFAULT_PASSWORD = "wheatomics115599"
DEFAULT_DB = "cloned_gene_db"

# Same allowlist as app/core/security.py ensure_gene_like: symbols ("TaARF4.1",
# "tae-miR5048") and GenBank accessions pass; spaces and other free text do not.
GENE_NAME_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")

INSERT_COLUMNS = [
    "gene_id", "gene_name", "chrom_pos", "gene_phenotype", "gene_species",
    "paper_title", "paper_doi", "key_result", "author", "submission_date",
    "function_description", "publication_year", "pmid",
]


def normalize(symbol):
    """Casefold + strip whitespace + drop '.', '-', '_' (same rule as scan script)."""
    return re.sub(r"[.\-_\s]+", "", symbol.casefold())


def load_known_gene_index(cursor):
    """Build normalized lookup indexes over cloned_gene_tbl.gene_name / .gene_id."""
    cursor.execute("SELECT clone_id, gene_id, gene_name FROM cloned_gene_tbl")
    name_norm, name_exact = defaultdict(list), defaultdict(list)
    id_norm, id_exact = defaultdict(list), defaultdict(list)
    for row in cursor.fetchall():
        cid = row["clone_id"]
        for col, exact_idx, norm_idx in (
            ("gene_name", name_exact, name_norm),
            ("gene_id", id_exact, id_norm),
        ):
            val = row.get(col)
            if val is None:
                continue
            s = str(val).strip()
            if not s:
                continue
            exact_idx[s.casefold()].append(cid)
            norm_idx[normalize(s)].append(cid)
    return name_norm, name_exact, id_norm, id_exact


def gene_exists(symbol, indexes):
    """True if a normalized match for `symbol` already exists in the table."""
    name_norm, name_exact, id_norm, id_exact = indexes
    norm = normalize(symbol)
    fold = symbol.casefold()
    return any(norm in idx or fold in idx
               for idx in (name_norm, id_norm, name_exact, id_exact))


def _split_multi(value):
    """Split a ###-joined legacy multi-value cell into non-empty parts."""
    return [p.strip() for p in str(value or "").split("###") if p.strip()]


def _first_year(pub_dates_cell):
    """Earliest 4-digit year across the gene's papers; None if unparseable."""
    years = []
    for d in _split_multi(pub_dates_cell):
        m = re.match(r"(\d{4})", d)
        if m:
            years.append(int(m.group(1)))
    return min(years) if years else None


def _cell(row, name):
    return str(row.get(name) or "").strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, dest="csv_path",
                        help="reviewed candidate CSV from scan_gene_annotations.py")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--commit", action="store_true",
                        help="actually INSERT rows (default is dry-run)")
    parser.add_argument("--ensure-pmid-column", action="store_true",
                        help="run ALTER TABLE to add the pmid column if missing")
    args = parser.parse_args()

    if not os.path.isfile(args.csv_path):
        sys.exit("CSV not found: %s" % args.csv_path)

    try:
        conn = pymysql.connect(
            host=args.host, port=args.port, user=args.user, password=args.password,
            database=args.db, charset="utf8mb4", cursorclass=DictCursor,
        )
    except Exception as e:
        sys.exit("Cannot connect to MySQL (%s:%s/%s): %s" % (args.host, args.port, args.db, e))

    try:
        with conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM cloned_gene_tbl LIKE 'pmid'")
            has_pmid = cur.fetchone() is not None
            indexes = load_known_gene_index(cur)

        if not has_pmid:
            if args.ensure_pmid_column:
                with conn.cursor() as cur:
                    cur.execute("ALTER TABLE cloned_gene_tbl ADD COLUMN pmid VARCHAR(500) DEFAULT NULL")
                conn.commit()
                has_pmid = True
                print("pmid column added to cloned_gene_tbl")
            else:
                print("NOTE: cloned_gene_tbl has no `pmid` column; PMIDs will be dropped.")
                print("      Run once by hand (or pass --ensure-pmid-column):")
                print("      ALTER TABLE cloned_gene_tbl ADD COLUMN pmid VARCHAR(500) DEFAULT NULL;")

        # Collect rows to import; dedupe repeated genes within the CSV itself.
        with open(args.csv_path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            approved, skipped_invalid, seen = [], [], set()
            for row in reader:
                approve = _cell(row, "approve")
                if approve not in ("1", "y", "yes", "Y", "YES"):
                    continue
                name = _cell(row, "gene_name")
                if not name:
                    skipped_invalid.append(("", "empty gene_name"))
                    continue
                if not GENE_NAME_RE.match(name) or len(name) > 100:
                    skipped_invalid.append((name, "gene_name failed ^[A-Za-z0-9_.:-]+$ or >100 chars"))
                    continue
                key = normalize(name)
                if key in seen:
                    skipped_invalid.append((name, "duplicate row in CSV"))
                    continue
                seen.add(key)
                approved.append(row)

        inserted, skipped_existing = [], []
        for row in approved:
            name = _cell(row, "gene_name")
            if gene_exists(name, indexes):
                skipped_existing.append(name)
                continue

            values = {
                "gene_id": name,
                "gene_name": name,
                "chrom_pos": _cell(row, "chrom_pos_override"),
                "gene_phenotype": _cell(row, "traits"),
                "gene_species": _cell(row, "species_override"),
                "paper_title": "###".join(_split_multi(_cell(row, "paper_titles"))),
                "paper_doi": "",
                "key_result": "###".join(_split_multi(_cell(row, "function_summaries"))),
                "author": "",
                "submission_date": datetime.now().strftime("%Y-%m-%d"),
                "function_description": "%s; confidence=%s; evidence=%s" % (
                    _cell(row, "gene_type"),
                    _cell(row, "max_confidence"),
                    _cell(row, "evidence_types"),
                ),
                "publication_year": _first_year(_cell(row, "pub_dates")),
                "pmid": "###".join(_split_multi(_cell(row, "pmids"))) if has_pmid else None,
            }

            columns = [c for c in INSERT_COLUMNS if values.get(c) is not None]
            placeholders = ", ".join(["%s"] * len(columns))
            sql = "INSERT INTO cloned_gene_tbl (%s) VALUES (%s)" % (
                ", ".join(columns), placeholders)
            params = [values[c] for c in columns]

            if args.commit:
                try:
                    with conn.cursor() as cur:
                        cur.execute(sql, params)
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    sys.exit("INSERT failed for %s: %s" % (name, e))
                inserted.append("%s (clone_id=%s)" % (name, conn.insert_id()))
            else:
                inserted.append(name)

        print("=== import summary (%s) ===" % ("COMMITTED" if args.commit else "DRY-RUN"))
        print("rows to import:        %d" % len(inserted))
        print("skipped (existing):    %d" % len(skipped_existing))
        print("skipped (invalid):     %d" % len(skipped_invalid))
        if args.commit:
            print("\ninserted:")
            for line in inserted:
                print("  " + line)
        else:
            print("\nwould insert (sample):")
            for line in inserted[:20]:
                print("  " + line)
            print("\npass --commit to insert for real.")
        if skipped_existing:
            print("\nalready in table:")
            for name in skipped_existing:
                print("  " + name)
        if skipped_invalid:
            print("\ninvalid/skipped rows:")
            for name, why in skipped_invalid[:30]:
                print("  %r: %s" % (name, why))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
