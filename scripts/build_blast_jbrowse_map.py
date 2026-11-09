#!/usr/bin/env python3
"""Build the BLAST-database -> JBrowse refseq mapping consumed by the BLAST UI.

Why
---
A BLAST subject id is not a JBrowse ``loc``. For the same assembly:

    BLAST .fai seqid        Chr1A_AK58
    annotation header loc=  Chr1A
    JBrowse refseq          chr1A

Name heuristics alone match almost nothing (9 / 203 genome databases in the
2026-11 audit), but both sides carry sequence **lengths**, and the same
assembly has identical chromosome lengths. So this script joins

    BLAST_DB_PATH/<base>.genome.fai          seqid + length
    JBROWSE_DATA_ROOT/<dataset>/seq/refSeqs.json   refseq + length
    genome_registry                          base -> jbrowse_dataset

length-first, name-normalisation second, and writes one compact JSON entry per
assembly base:

    {"AABBDD_AK58": {
       "dataset": "AK58", "browser": "jbrowse1",
       "assembly_match": true, "reason": null,
       "chroms": {"Chr1A_AK58": "chr1A", ..., "chr1a_ak58": "chr1A"},
       "norm":   {"1a": "chr1A", ...},          # annotation-style tokens
       "annotation_ok": true, "matched": 21, "total": 21, "mismatched": []
    }, ...}

A database whose lengths do not line up keeps ``assembly_match: false`` and the
UI disables the link (e.g. ``HH_Morex``: BLAST Morex chr1H 516,505,932 bp vs a
scaffold-level ``Morex`` JBrowse dataset whose first refseq is 680,018 bp).

Run on the web node (needs the BLAST db dir, the JBrowse data root and the
genome_registry MySQL database):

    python3 scripts/build_blast_jbrowse_map.py                 # build + report
    python3 scripts/build_blast_jbrowse_map.py --dry-run       # report only
    python3 scripts/build_blast_jbrowse_map.py --limit 5       # smoke test

For tests / offline runs the registry can come from a JSON file instead of
MySQL:  --registry-json dump.json  (list of genome_registry dicts).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

#: Keys written into the map, kept in sync with app/services/blast_jbrowse_map.py.
DEFAULT_DB_DIR = Path(os.environ.get("BLAST_DB_PATH", "/var/www/html/getfasta/blastdb"))
DEFAULT_JBROWSE_ROOT = Path(os.environ.get("JBROWSE_DATA_ROOT", "/var/www/html/jbrowse-1.12.3-release"))
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "app" / "services" / "data" / "blast_jbrowse_map.json"

#: Chromosome-level aliases stored per assembly ("1a" -> "chr1A"); a
#: chromosome-level assembly has a few dozen, so the cap is only a guard.
MAX_NORM_ALIASES = 1000

#: Max non-chromosome (contig/scaffold) exact aliases stored per assembly.
#: Those are only reachable by exact name, so they are kept as-is up to this
#: cap; chromosome tokens are resolved through the normalised `norm` table.
MAX_CHROM_ALIASES = 500

_STRIP_CHR = re.compile(r"^(chr|chromosome)", re.IGNORECASE)
_STRIP_SUFFIX = re.compile(r"_[a-z0-9.\-]+$", re.IGNORECASE)


def normalize_token(token: str) -> str:
    """``Chr1A_AK58`` / ``chr1A`` / ``Chr1A`` -> ``1a`` (see the runtime module)."""
    key = (token or "").strip().lower()
    key = _STRIP_CHR.sub("", key)
    key = _STRIP_SUFFIX.sub("", key)
    return key


#: Normalised chromosome-level token ("1a", "7d", "1h", "1r") — the sequences
#: whose length must match the JBrowse dataset for the assembly to be trusted.
_CHROM_TOKEN_RE = re.compile(r"^\d{1,2}[a-z]{0,4}$")


def is_chromosome_like(seqid: str) -> bool:
    """True for "Chr1A_AK58"-style names, False for Un/organelle/contig."""
    return bool(_CHROM_TOKEN_RE.match(normalize_token(seqid)))


def parse_fai(path: Path) -> list[tuple[str, int]]:
    """Seqid + length from a samtools/BLAST ``.fai`` (errors are not fatal)."""
    rows: list[tuple[str, int]] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parts = line.rstrip("\n").rstrip("\r").split("\t")
                if len(parts) < 2 or not parts[0].strip():
                    continue
                try:
                    rows.append((parts[0].strip(), int(parts[1])))
                except ValueError:
                    continue
    except OSError:
        return []
    return rows


def load_refseqs(root: Path, dataset: str) -> list[tuple[str, int]] | None:
    """Refseq names + lengths from ``<dataset>/seq/refSeqs.json``."""
    path = root / dataset / "seq" / "refSeqs.json"
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    rows = []
    for item in data if isinstance(data, list) else []:
        name = item.get("name") if isinstance(item, dict) else None
        length = item.get("length") if isinstance(item, dict) else None
        if name and isinstance(length, int):
            rows.append((name, length))
    return rows


def match_refseqs(
    fai_rows: list[tuple[str, int]],
    refseqs: list[tuple[str, int]],
) -> tuple[dict[str, str], list[str], dict[str, str]]:
    """Match BLAST seqids to JBrowse refseqs.

    Returns ``(chroms, mismatched, norm)`` where ``chroms`` maps BLAST seqid to
    refseq (length first, then normalised name) and ``norm`` maps the
    normalised chromosome token (annotation style) to refseq.
    """
    by_len: dict[int, list[str]] = {}
    for name, length in refseqs:
        by_len.setdefault(length, []).append(name)

    ref_by_norm: dict[str, str] = {}
    norm_ambiguous: set[str] = set()
    for name, _length in refseqs:
        key = normalize_token(name)
        if not key:
            continue
        if key in ref_by_norm and ref_by_norm[key] != name:
            norm_ambiguous.add(key)
        else:
            ref_by_norm[key] = name

    chroms: dict[str, str] = {}
    mismatched: list[str] = []
    for seqid, length in fai_rows:
        candidates = by_len.get(length) or []
        ref: str | None = None
        if len(candidates) == 1:
            ref = candidates[0]
        elif candidates:
            want = normalize_token(seqid)
            ref = next((c for c in candidates if normalize_token(c) == want), None)
        if ref is None:
            ref = ref_by_norm.get(normalize_token(seqid))
        if ref is None:
            mismatched.append(seqid)
        else:
            chroms[seqid] = ref
            chroms.setdefault(seqid.lower(), ref)

    # Normalised aliases for annotation-style chromosome tokens ("Chr1A",
    # "chr7A"). Only chromosome-level names go in: contig/scaffold names would
    # bloat the file and normalise ambiguously.
    norm: dict[str, str] = {}
    for key, name in ref_by_norm.items():
        if not key or key in norm_ambiguous or not is_chromosome_like(name):
            continue
        norm[key] = name
        if len(norm) >= MAX_NORM_ALIASES:
            break
    return chroms, mismatched, norm


def load_registry(registry_json: str | None) -> list[dict]:
    """genome_registry rows (JSON file for tests, MySQL in production)."""
    if registry_json:
        with open(registry_json, encoding="utf-8") as fh:
            data = json.load(fh)
        return [row for row in (data if isinstance(data, list) else data.get("rows", []))]

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.core.config import settings  # noqa: PLC0415 - deferred for --registry-json
    from app.db.mysql import mysql_cursor  # noqa: PLC0415

    with mysql_cursor(settings.DB_LITERATURE) as cursor:
        cursor.execute(
            "SELECT dataset_id, display_name, assembly_level, chromosome_count, "
            "jbrowse_dataset, blast_genome_db, blast_cds_db, blast_pep_db "
            "FROM genome_registry WHERE visible = 1"
        )
        return [dict(row) for row in cursor.fetchall()]


def clear_base(value: str | None) -> str:
    """Registry stores annotation bases with or without their file suffix."""
    base = (value or "").strip()
    for suffix in (".add_Description.cds", ".add_Description.pep"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return base


def build(rows: list[dict], db_dir: Path, jbrowse_root: Path,
          limit: int | None = None) -> tuple[dict, dict]:
    """Return (map entries, stats)."""
    entries: dict[str, dict] = {}
    stats = {"registry_rows": len(rows), "with_jbrowse": 0, "matched": 0,
             "mismatched": 0, "no_fai": 0, "no_refseqs": 0}
    refseq_cache: dict[str, list[tuple[str, int]] | None] = {}

    for row in rows[: limit or None]:
        dataset = (row.get("jbrowse_dataset") or "").strip()
        if not dataset:
            continue
        stats["with_jbrowse"] += 1

        # One entry per assembly base; nucleotide and annotation databases of
        # the same assembly share the same refseq mapping.
        genome_base = clear_base(row.get("blast_genome_db"))
        cds_base = clear_base(row.get("blast_cds_db"))
        pep_base = clear_base(row.get("blast_pep_db"))
        base = genome_base or cds_base or pep_base
        if not base:
            continue
        entry = entries.setdefault(base, {
            "dataset": dataset, "browser": "jbrowse1",
            "assembly_match": False, "reason": None,
            "chroms": {}, "norm": {},
            "annotation_ok": False, "matched": 0, "total": 0, "mismatched": [],
        })

        if dataset not in refseq_cache:
            refseq_cache[dataset] = load_refseqs(jbrowse_root, dataset)
        refseqs = refseq_cache[dataset]
        if refseqs is None:
            stats["no_refseqs"] += 1
            entry["reason"] = entry["reason"] or "jbrowse_refseqs_missing"
            continue

        if not genome_base:
            entry["reason"] = entry["reason"] or "no_nucleotide_database"
            continue

        fai_rows = parse_fai(db_dir / f"{genome_base}.genome.fai")
        if not fai_rows:
            stats["no_fai"] += 1
            entry["reason"] = entry["reason"] or "blast_fai_missing"
            continue

        chroms, mismatched, norm = match_refseqs(fai_rows, refseqs)
        # Chromosome tokens are resolved through `norm`; only unplaced
        # sequences (contigs/scaffolds/organelles) need exact aliases.
        exact: dict[str, str] = {}
        for seqid, refseq in chroms.items():
            if is_chromosome_like(seqid):
                continue
            if len(exact) >= MAX_CHROM_ALIASES:
                break
            # BLAST seqids come from the same FASTA as the .fai, so the exact
            # spelling is what the hit table will carry; no lower-case duplicate
            # is stored (the runtime falls back to lower-case on its own).
            exact[seqid] = refseq
        entry["chroms"] = exact
        entry["norm"] = norm
        entry["chromosome_aliases"] = len(norm)
        entry["matched"] = len(fai_rows) - len(mismatched)
        entry["total"] = len(fai_rows)
        entry["mismatched"] = mismatched[:20]
        # Extra sequences that JBrowse does not carry (ChrUn, organelles,
        # unplaced contigs) are normal and not a version mismatch; only a
        # chromosome-level sequence whose length differs means the two sides
        # are different assembly versions.
        unmatched_chromosomes = [sid for sid in mismatched if is_chromosome_like(sid)]
        if unmatched_chromosomes or not chroms:
            stats["mismatched"] += 1
            entry["assembly_match"] = False
            entry["reason"] = "assembly_version_mismatch"
            entry["mismatched"] = unmatched_chromosomes[:20] or mismatched[:20]
        else:
            stats["matched"] += 1
            entry["assembly_match"] = True
            entry["reason"] = None
        entry["annotation_ok"] = bool(
            entry["assembly_match"]
            and (cds_base == base or pep_base == base)
            and (entry["chroms"] or entry["norm"])
        )

    return entries, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-dir", type=Path, default=DEFAULT_DB_DIR,
                        help=f"BLAST database dir (default {DEFAULT_DB_DIR})")
    parser.add_argument("--jbrowse-root", type=Path, default=DEFAULT_JBROWSE_ROOT,
                        help=f"JBrowse data root (default {DEFAULT_JBROWSE_ROOT})")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help=f"output JSON (default {DEFAULT_OUT})")
    parser.add_argument("--registry-json", help="genome_registry dump (skip MySQL)")
    parser.add_argument("--limit", type=int, help="only the first N registry rows (smoke test)")
    parser.add_argument("--dry-run", action="store_true", help="report only, do not write")
    args = parser.parse_args()

    rows = load_registry(args.registry_json)
    entries, stats = build(rows, args.db_dir, args.jbrowse_root, args.limit)

    usable = sum(1 for e in entries.values() if e.get("assembly_match"))
    print(f"registry rows with JBrowse dataset : {stats['with_jbrowse']}")
    print(f"assembly bases in map             : {len(entries)}")
    print(f"assembly_match = true             : {usable}")
    print(f"length-mismatch / no .fai / no refseqs: "
          f"{stats['mismatched']} / {stats['no_fai']} / {stats['no_refseqs']}")

    payload = {
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "db_dir": str(args.db_dir),
            "jbrowse_root": str(args.jbrowse_root),
            "bases": len(entries),
            "assembly_match": usable,
            "stats": stats,
        },
        **entries,
    }
    if args.dry_run:
        print("dry-run: nothing written")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(args.out.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(args.out)
    print(f"wrote {args.out} ({args.out.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
