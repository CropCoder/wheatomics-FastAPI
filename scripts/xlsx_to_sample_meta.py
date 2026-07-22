#!/usr/bin/env python3
"""Convert a sample-metadata xlsx into a VariantHub sample_meta JSON file.

Usage:
    python scripts/xlsx_to_sample_meta.py \
        --xlsx /path/to/samples.xlsx \
        --dataset wheat660k_2191_CS2.1 \
        [--id-column "Analysis ID"] \
        [--vcf-dir /var/www/html/variants]

The script maps xlsx rows onto the dataset's VCF sample names, normalizing
IDs (strip + non-alphanumeric → "_") so e.g. "CDC Landmark" matches the VCF
sample "CDC_Landmark". It reports the match rate and writes the result to
app/services/data/sample_meta/<dataset>.json.

Requires: openpyxl (pip install openpyxl).
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from pathlib import Path

# Make the repo importable so we can reuse the dataset registry.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.routers.varianthub import VARIANTHUB_DATASETS  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "app" / "services" / "data" / "sample_meta"

_ID_COLUMN_HINTS = ("analysis", "sample", "id")


def snake_case(header: str) -> str:
    """'Accession name (Chinese)' -> 'accession_name_chinese'."""
    text = re.sub(r"[^0-9A-Za-z]+", "_", str(header).strip()).strip("_").lower()
    return re.sub(r"_+", "_", text)


def normalize_id(value: object) -> str:
    """Match VCF sample naming: strip, non-alphanumeric runs -> '_'."""
    return re.sub(r"[^0-9A-Za-z]+", "_", str(value).strip()).strip("_")


def find_id_column(headers: list[str], explicit: str | None) -> int:
    if explicit:
        for i, h in enumerate(headers):
            if str(h).strip().lower() == explicit.strip().lower():
                return i
        raise SystemExit(f"--id-column {explicit!r} not found in headers: {headers}")
    for i, h in enumerate(headers):
        lowered = str(h).strip().lower()
        if any(hint in lowered for hint in _ID_COLUMN_HINTS):
            return i
    raise SystemExit(
        f"Could not auto-detect an ID column in headers: {headers}. "
        "Pass --id-column explicitly."
    )


def vcf_samples(vcf_dir: Path, dataset: str) -> list[str]:
    filename = VARIANTHUB_DATASETS[dataset]["filename"]
    path = vcf_dir / filename
    if not path.exists():
        raise SystemExit(f"VCF not found: {path} (pass --vcf-dir)")
    with gzip.open(path, "rt") as fh:
        for line in fh:
            if line.startswith("#CHROM"):
                fields = line.rstrip("\n").split("\t")
                return fields[9:]
            if not line.startswith("#"):
                break
    raise SystemExit(f"No #CHROM header line found in {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--xlsx", required=True, type=Path)
    parser.add_argument("--dataset", required=True, choices=sorted(VARIANTHUB_DATASETS))
    parser.add_argument("--id-column", default=None)
    parser.add_argument("--vcf-dir", type=Path, default=Path("/var/www/html/variants"))
    parser.add_argument("--sheet", default=None, help="Sheet name (default: first sheet)")
    args = parser.parse_args()

    try:
        import openpyxl
    except ImportError:
        raise SystemExit("openpyxl is required: pip install openpyxl")

    wb = openpyxl.load_workbook(args.xlsx, read_only=True)
    ws = wb[args.sheet] if args.sheet else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise SystemExit("Empty xlsx")

    headers = [str(h) if h is not None else f"col{i}" for i, h in enumerate(rows[0])]
    id_idx = find_id_column(headers, args.id_column)
    field_keys: list[str] = []
    fields: list[dict] = []
    for i, header in enumerate(headers):
        if i == id_idx:
            continue
        key = snake_case(header)
        # Disambiguate duplicate keys after snake-casing.
        while key in field_keys:
            key += "_2"
        field_keys.append(key)
        fields.append({"key": key, "label": str(header).strip()})

    samples: dict[str, dict] = {}
    for row in rows[1:]:
        if row[id_idx] is None:
            continue
        sample_id = normalize_id(row[id_idx])
        entry = {}
        for i, field in enumerate(fields):
            col_idx = i if i < id_idx else i + 1
            value = row[col_idx] if col_idx < len(row) else None
            entry[field["key"]] = "" if value is None else str(value).strip()
        samples[sample_id] = entry

    # Validate against the VCF header sample names.
    vcf_names = vcf_samples(args.vcf_dir, args.dataset)
    vcf_set = set(vcf_names)
    matched = [s for s in vcf_names if s in samples]
    vcf_missing = [s for s in vcf_names if s not in samples]
    xlsx_extra = [s for s in samples if s not in vcf_set]

    print(f"ID column: {headers[id_idx]!r}")
    print(f"Fields: {[f['key'] for f in fields]}")
    print(f"xlsx samples: {len(samples)} | VCF samples: {len(vcf_names)} | matched: {len(matched)}")
    if vcf_missing:
        print(f"VCF samples without xlsx row ({len(vcf_missing)}): {vcf_missing[:10]}")
    if xlsx_extra:
        print(f"xlsx IDs not in VCF ({len(xlsx_extra)}): {xlsx_extra[:10]}")

    payload = {
        "dataset": args.dataset,
        "source_file": args.xlsx.name,
        "fields": fields,
        "samples": {name: samples[name] for name in vcf_names if name in samples},
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{args.dataset}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"Wrote {out_path} ({len(payload['samples'])} samples)")
    if vcf_missing or xlsx_extra:
        print("WARNING: match is incomplete — review the lists above before committing.")


if __name__ == "__main__":
    main()
