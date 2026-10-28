#!/usr/bin/env python3
"""Convert the curated TF workbook (new_tf.xlsx) into the TSV the atlas reads.

The workbook has 14 columns whose headers carry footnote letters ("Gene stable
ID v1.1 a", "TF classification b", ...). This script matches them by keyword,
renames them to stable snake_case keys and writes a tab-separated file that
app/api/routers/regulatory_tf_atlas.py loads (WHEAT_TF_CLASSIFICATION_TSV,
default <processed>/wheat_tf_classification.tsv).

Run on the server:

    python3 scripts/import_tf_classification.py \
        --xlsx /var/www/html/wheat-regulatory-hub/data/processed/new_tf.xlsx

    # preview without writing
    python3 scripts/import_tf_classification.py --xlsx ... --dry-run
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

try:
    import openpyxl
except ImportError:
    sys.exit("openpyxl is required: pip install openpyxl")

DEFAULT_OUT = Path(
    os.environ.get(
        "WHEAT_TF_CLASSIFICATION_TSV",
        "/var/www/html/wheat-regulatory-hub/data/processed/wheat_tf_classification.tsv",
    )
)

# (output column, substrings that must all appear in the normalised header)
COLUMN_MAP = [
    ("gene_id_v11", ["gene stable id v1.1"]),
    ("gene_id_v21", ["gene stable id v2.1"]),
    ("tf_classification", ["tf classification"]),
    ("planttfdb", ["planttfdb"]),
    ("ref_classification", ["classification from reference"]),
    ("iwgsc_v11_tf_family", ["iwgsc refseq v1.1"]),
    ("iwgsc_v21_tf_family", ["iwgsc refseq v2.1"]),
    ("gene_name", ["gene name"]),
    ("gene_start", ["gene start"]),
    ("gene_end", ["gene end"]),
    ("strand", ["strand"]),
    ("transcript_length", ["transcript length"]),
    ("gc_content", ["gc content"]),
    ("go_terms", ["go term"]),
]

_NULL = {"", "na", "nan", "none", "null", "-", "nat"}


def norm(text) -> str:
    """Lowercase, collapse whitespace/punctuation so header variants match."""
    return re.sub(r"[^a-z0-9.]+", " ", str(text or "").lower()).strip()


def clean(value) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    return "" if s.lower() in _NULL else s


def map_headers(header: list) -> dict:
    """Return {output_name: column_index} located by keyword."""
    normalised = [norm(h) for h in header]
    found: dict[str, int] = {}
    for name, needles in COLUMN_MAP:
        for idx, text in enumerate(normalised):
            if all(n in text for n in needles):
                found[name] = idx
                break
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--xlsx", required=True, help="new_tf.xlsx")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help=f"output TSV (default {DEFAULT_OUT})")
    ap.add_argument("--sheet", default=None, help="sheet name (default: the only sheet)")
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    src = Path(args.xlsx)
    if not src.is_file():
        ap.error(f"workbook not found: {src}")

    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    ws = wb[args.sheet] if args.sheet else wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = list(next(rows, ()))
    col = map_headers(header)
    print(f"sheet: {ws.title}  columns: {len(header)}")
    print(f"matched: {len(col)}/{len(COLUMN_MAP)} -> {sorted(col)}")

    missing = [n for n, _ in COLUMN_MAP if n not in col]
    if "gene_id_v11" not in col:
        ap.error(f"cannot locate 'Gene stable ID v1.1'; headers were: {header}")
    if missing:
        print(f"WARNING: unmatched columns will be left empty: {missing}")

    out_names = [n for n, _ in COLUMN_MAP]
    records = []
    seen = set()
    duplicates = 0
    for values in rows:
        values = list(values)
        def get(name: str) -> str:
            idx = col.get(name)
            return clean(values[idx]) if idx is not None and idx < len(values) else ""
        gene = get("gene_id_v11")
        if not gene:
            continue
        if gene in seen:
            duplicates += 1
            continue
        seen.add(gene)
        records.append({n: get(n) for n in out_names})

    named = sum(1 for r in records if r["gene_name"])
    classified = sum(1 for r in records if r["tf_classification"])
    print(f"rows kept: {len(records)}  duplicates skipped: {duplicates}")
    print(f"with gene name: {named}  with TF classification: {classified}")
    if records:
        print("sample:", {k: v for k, v in records[0].items() if v})

    if args.dry_run:
        print("\ndry run: nothing written")
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=out_names, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    tmp.replace(out)
    print(f"\nwrote {out}  ({len(records)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
