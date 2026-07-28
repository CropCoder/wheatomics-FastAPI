#!/usr/bin/env python3
"""Convert sample736.txt to sample_meta JSON files for VariantHub.

Usage:
    python convert_sample736.py /var/www/html/variants/sample736.txt
"""

import json
import sys


def convert(path: str) -> dict:
    """Parse tab-separated sample metadata and return JSON payload."""
    samples: dict[str, dict[str, str]] = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        header = next(f).strip().split("\t")
        # Expected: Sampleid Type Subspecies Country "Publication doi" "Seed Source"
        field_map = [
            ("Sampleid", "sampleid"),
            ("Type", "type"),
            ("Subspecies", "subspecies"),
            ("Country", "country"),
            ("Publication doi", "publication_doi"),
            ("Seed Source", "seed_source"),
        ]
        for line in f:
            line = line.strip()
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) < 6:
                continue
            sample_name = cols[0].strip()
            samples[sample_name] = {
                "type": cols[1].strip(),
                "subspecies": cols[2].strip(),
                "country": cols[3].strip(),
                "publication_doi": cols[4].strip(),
                "seed_source": cols[5].strip(),
            }

    return {
        "fields": [
            {"key": "type", "label": "Type"},
            {"key": "subspecies", "label": "Subspecies"},
            {"key": "country", "label": "Country"},
            {"key": "publication_doi", "label": "Publication doi"},
            {"key": "seed_source", "label": "Seed Source"},
        ],
        "samples": samples,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <sample736.txt>")
        sys.exit(1)

    payload = convert(sys.argv[1])
    print(json.dumps(payload, indent=2))
    print(f"\n{len(payload['samples'])} samples parsed.", file=sys.stderr)
