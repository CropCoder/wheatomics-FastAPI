#!/usr/bin/env python3
"""Scan functional_gene_annotations for new cloned genes not yet in cloned_gene_tbl.

Reads the LLM annotation layer (Triticeae_Research_filter.functional_gene_annotations)
rows where is_functional_gene = 1, parses gene_name (JSON array or comma-separated
string; elements may contain ';'-joined symbols like "MLA3; SR50"), normalizes the
symbols and matches them against cloned_gene_db.cloned_gene_tbl (gene_name + gene_id).

Output (with --write):
  <out_dir>/matched_report_<date>.csv   genes already in the known-genes table (report only)
  <out_dir>/candidate_genes_<date>.csv  new-gene candidates for human review:
                                        fill approve=1 (and optionally species_override /
                                        chrom_pos_override) then run import_cloned_genes.py

This script is read-only against both databases; it never writes to MySQL.
Re-running it is safe and only refreshes the CSV reports.

Usage:
  python scripts/scan_gene_annotations.py                 # stats only
  python scripts/scan_gene_annotations.py --write         # stats + write CSVs
  python scripts/scan_gene_annotations.py --write --limit 200   # sample first
"""

import argparse
import csv
import json
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
DEFAULT_ANN_DB = "Triticeae_Research_filter"
DEFAULT_KNOWN_DB = "cloned_gene_db"

CANDIDATE_FIELDS = [
    "gene_name", "gene_type", "n_papers", "pmids", "paper_titles", "pub_dates",
    "traits", "function_summaries", "evidence_types", "max_confidence",
    "review_status", "source_method", "llm_reason",
    "species_override", "chrom_pos_override", "approve",
]

MATCHED_FIELDS = [
    "gene_name", "matched_clone_ids", "n_papers", "pmids", "review_status",
]


def parse_gene_names(raw):
    """Parse a gene_name cell: JSON array string or comma-separated list.
    Elements may themselves contain ';'-joined symbols ("MLA3; SR50").
    Mirrors app/api/routers/triticeae.py _parse_gene_name plus ';' splitting.
    """
    if not raw or not isinstance(raw, str):
        return []
    text = raw.strip()
    if not text:
        return []
    if text.startswith("[") or text.startswith("{"):
        try:
            items = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return []
    else:
        items = [g.strip() for g in text.split(",") if g.strip()]
    names = []
    for item in items:
        if not isinstance(item, str):
            continue
        for part in item.split(";"):
            part = part.strip()
            if part:
                names.append(part)
    return names


def normalize(symbol):
    """Casefold + strip whitespace + drop '.', '-', '_' for fuzzy matching.
    'TaARF4.1' -> 'taarf41'  /  'Ta-MFT_3B' -> 'tamft3b'"""
    return re.sub(r"[.\-_\s]+", "", symbol.casefold())


def load_known_gene_index(cursor):
    """Build lookup indexes over cloned_gene_tbl.gene_name and .gene_id.

    Returns (name_norm, name_exact, id_norm, id_exact): each maps a key to the
    list of clone_ids carrying it. Columns may be NULL; values are stripped.
    """
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


def match_gene(symbol, indexes):
    """Return sorted unique clone_ids matching the symbol, or []."""
    name_norm, name_exact, id_norm, id_exact = indexes
    norm = normalize(symbol)
    fold = symbol.casefold()
    # 1. normalized equality on gene_name  2. normalized equality on gene_id
    # 3. case-insensitive exact on gene_name 4. case-insensitive exact on gene_id
    for idx, key in ((name_norm, norm), (id_norm, norm), (name_exact, fold), (id_exact, fold)):
        if key in idx:
            return sorted(set(idx[key]))
    return []


def split_tokens(value):
    """Split a ';' or ',' joined field into unique ordered tokens."""
    if not value:
        return []
    tokens = []
    for part in re.split(r"[;,]", str(value)):
        part = part.strip()
        if part and part not in tokens:
            tokens.append(part)
    return tokens


def _connect(host, port, user, password, database):
    return pymysql.connect(
        host=host, port=port, user=user, password=password,
        database=database, charset="utf8mb4", cursorclass=DictCursor,
    )


def scan(conn_ann, conn_known, limit=None):
    """Return (gene_records, stats): gene_records keyed by normalized symbol
    with merged cross-paper data, plus scan statistics."""
    with conn_ann.cursor() as cur:
        sql = (
            "SELECT f.id, f.pubmedid, f.is_functional_gene, f.confidence, "
            "f.gene_name, f.gene_type, f.trait_label, f.function_summary, "
            "f.evidence_type, f.llm_reason, f.source_method, f.review_status, "
            "p.title AS paper_title, p.pub_date "
            "FROM functional_gene_annotations f "
            "LEFT JOIN papers p ON p.pmid = f.pubmedid "
            "WHERE f.is_functional_gene = 1 "
            "ORDER BY f.id"
        )
        if limit:
            sql += " LIMIT %d" % int(limit)
        cur.execute(sql)
        rows = cur.fetchall()

    with conn_known.cursor() as cur:
        indexes = load_known_gene_index(cur)

    genes = {}
    empty_name_rows = 0
    for row in rows:
        names = parse_gene_names(row.get("gene_name"))
        if not names:
            empty_name_rows += 1
            continue
        title = str(row.get("paper_title") or "")
        pub_date = str(row.get("pub_date") or "")
        pmid = str(row.get("pubmedid") or "")
        for symbol in names:
            key = normalize(symbol)
            rec = genes.setdefault(key, {
                "norm": key,
                "gene_name": symbol,
                "gene_types": [],
                "papers": [],           # ordered unique (pmid, title, pub_date)
                "traits": [],
                "summaries": [],
                "evidence": [],
                "max_confidence": None,
                "review_status": [],
                "source_method": [],
                "llm_reason": "",
            })
            if row.get("gene_type") and row["gene_type"] not in rec["gene_types"]:
                rec["gene_types"].append(row["gene_type"])
            paper = (pmid, title, pub_date)
            if paper not in rec["papers"]:
                rec["papers"].append(paper)
            for t in split_tokens(row.get("trait_label")):
                if t not in rec["traits"]:
                    rec["traits"].append(t)
            summary = str(row.get("function_summary") or "").strip()
            if summary and summary not in rec["summaries"]:
                rec["summaries"].append(summary)
            for e in split_tokens(row.get("evidence_type")):
                if e not in rec["evidence"]:
                    rec["evidence"].append(e)
            conf = row.get("confidence")
            if conf is not None:
                rec["max_confidence"] = max(rec["max_confidence"] or 0, float(conf))
            if row.get("review_status") and row["review_status"] not in rec["review_status"]:
                rec["review_status"].append(row["review_status"])
            if row.get("source_method") and row["source_method"] not in rec["source_method"]:
                rec["source_method"].append(row["source_method"])
            if not rec["llm_reason"]:
                rec["llm_reason"] = str(row.get("llm_reason") or "").strip()

    stats = {
        "annotation_rows": len(rows),
        "empty_gene_name_rows": empty_name_rows,
        "gene_records": len(genes),
    }
    return genes, indexes, stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--ann-db", default=DEFAULT_ANN_DB,
                        help="annotation database (default: %s)" % DEFAULT_ANN_DB)
    parser.add_argument("--known-db", default=DEFAULT_KNOWN_DB,
                        help="known-genes database (default: %s)" % DEFAULT_KNOWN_DB)
    parser.add_argument("--limit", type=int, default=None,
                        help="only scan the first N annotation rows (for testing)")
    parser.add_argument("--write", action="store_true",
                        help="write matched_report_*.csv and candidate_genes_*.csv")
    parser.add_argument("--out-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "output"),
                        help="directory for CSV output (default: scripts/output)")
    args = parser.parse_args()

    try:
        conn_ann = _connect(args.host, args.port, args.user, args.password, args.ann_db)
        conn_known = _connect(args.host, args.port, args.user, args.password, args.known_db)
    except Exception as e:  # pymysql OperationalError etc.
        sys.exit("Cannot connect to MySQL (%s:%s): %s" % (args.host, args.port, e))

    genes, indexes, stats = scan(conn_ann, conn_known, args.limit)
    conn_ann.close()
    conn_known.close()

    matched = []
    candidates = []
    for key in sorted(genes):
        rec = genes[key]
        clone_ids = match_gene(rec["gene_name"], indexes)
        if clone_ids:
            matched.append((rec, clone_ids))
        else:
            candidates.append(rec)

    print("=== scan stats ===")
    print("annotation rows read (is_functional_gene=1): %d" % stats["annotation_rows"])
    print("rows with empty/unparseable gene_name:      %d" % stats["empty_gene_name_rows"])
    print("distinct gene records:                      %d" % stats["gene_records"])
    print("already in cloned_gene_tbl (matched):       %d" % len(matched))
    print("new candidates (unmatched):                 %d" % len(candidates))

    type_dist = defaultdict(int)
    status_dist = defaultdict(int)
    for rec in candidates:
        for t in rec["gene_types"]:
            type_dist[t] += 1
        for s in rec["review_status"]:
            status_dist[s] += 1
    print("candidate gene_type distribution: %s" % dict(type_dist))
    print("candidate review_status distribution: %s" % dict(status_dist))

    if not args.write:
        print("\n(dry run: pass --write to emit CSV reports)")
        return

    os.makedirs(args.out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    matched_path = os.path.join(args.out_dir, "matched_report_%s.csv" % stamp)
    cand_path = os.path.join(args.out_dir, "candidate_genes_%s.csv" % stamp)

    with open(matched_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MATCHED_FIELDS)
        writer.writeheader()
        for rec, clone_ids in matched:
            writer.writerow({
                "gene_name": rec["gene_name"],
                "matched_clone_ids": "###".join(str(c) for c in clone_ids),
                "n_papers": len(rec["papers"]),
                "pmids": "###".join(p[0] for p in rec["papers"]),
                "review_status": ";".join(rec["review_status"]),
            })

    with open(cand_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANDIDATE_FIELDS)
        writer.writeheader()
        for rec in candidates:
            writer.writerow({
                "gene_name": rec["gene_name"],
                "gene_type": ";".join(rec["gene_types"]),
                "n_papers": len(rec["papers"]),
                "pmids": "###".join(p[0] for p in rec["papers"]),
                "paper_titles": "###".join(p[1] for p in rec["papers"]),
                "pub_dates": "###".join(p[2] for p in rec["papers"]),
                "traits": ";".join(rec["traits"]),
                "function_summaries": "###".join(rec["summaries"]),
                "evidence_types": ";".join(rec["evidence"]),
                "max_confidence": rec["max_confidence"],
                "review_status": ";".join(rec["review_status"]),
                "source_method": ";".join(rec["source_method"]),
                "llm_reason": rec["llm_reason"],
                "species_override": "",
                "chrom_pos_override": "",
                "approve": "",
            })

    print("\nwritten: %s (%d rows)" % (matched_path, len(matched)))
    print("written: %s (%d rows)" % (cand_path, len(candidates)))
    print("review %s: set approve=1 per gene, fill species_override/"
          "chrom_pos_override if known, then run import_cloned_genes.py" % cand_path)


if __name__ == "__main__":
    main()
