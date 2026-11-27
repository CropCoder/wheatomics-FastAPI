#!/usr/bin/env python3
"""Replace the corrupt CS 03G CDS records inside the `all_genes_base` aggregate.

`all_gene` / `all_genes` (the defaults of the GetFasta download page and the
combined BLAST search) are BLAST **aliases** whose first member is the volume
database `all_genes_base`, built on 2026-11-13 from
`blastdb_migration_20261113/all_genes_base.fa`.  Rebuilding the individual
`AABBDD_Chinese_Spring2.1.add_Description.cds` database (see
``fix_cs03g_cds.py``) therefore does **not** change what alias-based downloads
return: the old corrupt 03G CDS records still live in the aggregate.

This script streams the 34 GB aggregate FASTA, swaps the 130,365 corrected 03G
records in place, rebuilds `all_genes_base` and (with ``--apply``) installs it
into the BLAST database directory, keeping the aliases unchanged.

    # 1) patch FASTA only (fast, ~10-20 min on the data disk)
    python3 scripts/fix_all_genes_base.py --patch

    # 2) build the replacement BLAST DB + install it (makeblastdb is the slow part)
    python3 scripts/fix_all_genes_base.py --apply

Run from the FastAPI repo root on the production web node.  Corrupt sources and
old index files are kept with timestamped names.
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path

MIGRATION = Path("/var/www/html/getfasta/blastdb_migration_20261113")
SOURCE_FA = MIGRATION / "all_genes_base.fa"
PATCHED_FA = MIGRATION / "all_genes_base.fixed.fa"
STAGING_DB = MIGRATION / "all_genes_base_fixed"
BLASTDB = Path("/var/www/html/getfasta/blastdb")
DB_NAME = "all_genes_base"
BLAST_BIN = Path("/var/www/html/blast/blast+/bin")
CORRECTED_FA = Path("/tmp/cs03g_cds_fixed.fa")


def read_corrected(path: Path) -> dict[str, tuple[str, str]]:
    records: dict[str, tuple[str, str]] = {}
    header = None
    chunks: list[str] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith(">"):
                if header:
                    records[header[1:].split()[0]] = (header, "".join(chunks))
                header = line.rstrip("\n")
                chunks = []
            else:
                chunks.append(line.strip())
    if header:
        records[header[1:].split()[0]] = (header, "".join(chunks))
    return records


def patch_fasta(corrected: dict[str, tuple[str, str]], resume: bool = True) -> tuple[int, int]:
    """Stream SOURCE_FA, replacing records whose ID is in ``corrected``."""
    if resume and PATCHED_FA.exists() and PATCHED_FA.stat().st_size > SOURCE_FA.stat().st_size * 0.95:
        print(f"reusing existing {PATCHED_FA} ({PATCHED_FA.stat().st_size / 1e9:.1f} GB)")
        return len(corrected), 0
    tmp = PATCHED_FA.with_suffix(".tmp")
    replaced = passthrough = 0
    current_is_target = False
    with SOURCE_FA.open(encoding="utf-8", errors="replace") as src, tmp.open("w", encoding="utf-8") as out:
        for line in src:
            if line.startswith(">"):
                gene_id = line[1:].split()[0]
                if gene_id in corrected:
                    header, seq = corrected[gene_id]
                    out.write(header + "\n")
                    for i in range(0, len(seq), 70):
                        out.write(seq[i:i + 70] + "\n")
                    replaced += 1
                    current_is_target = True
                else:
                    out.write(line)
                    current_is_target = False
                    passthrough += 1
            elif not current_is_target:
                out.write(line)
    tmp.replace(PATCHED_FA)
    print(f"patched FASTA: replaced {replaced:,} records, kept {passthrough:,} others -> {PATCHED_FA}")
    return replaced, passthrough


def build_db() -> None:
    for old in MIGRATION.glob("all_genes_base_fixed.*"):
        old.unlink()
    cmd = [
        str(BLAST_BIN / "makeblastdb"), "-in", str(PATCHED_FA), "-dbtype", "nucl",
        "-parse_seqids", "-out", str(STAGING_DB),
    ]
    print("running:", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)
    print("staging DB built")


def verify_db() -> bool:
    out = subprocess.run(
        [str(BLAST_BIN / "blastdbcmd"), "-db", str(STAGING_DB),
         "-entry", "TraesCS6D03G0644700.1", "-outfmt", "%f"],
        capture_output=True, text=True, check=True,
    ).stdout
    seq = "".join(line.strip() for line in out.splitlines() if not line.startswith(">"))
    ok = seq.upper().startswith("ATG") and len(seq) == 330 and "N" not in seq.upper()
    print("staging DB check:", "OK" if ok else "FAILED", f"(len={len(seq)})")
    return ok


def install() -> None:
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BLASTDB / ("_backup_all_genes_base_" + stamp)
    backup.mkdir(parents=True, exist_ok=True)
    moved = 0
    for src in sorted(BLASTDB.glob(DB_NAME + ".*")):
        shutil.move(str(src), backup / src.name)
        moved += 1
    print(f"moved {moved} old index files to {backup}")

    new_files = sorted(MIGRATION.glob("all_genes_base_fixed.*"))
    for src in new_files:
        # volume names look like all_genes_base_fixed.00.nsq -> all_genes_base.00.nsq
        target = BLASTDB / src.name.replace("all_genes_base_fixed", DB_NAME)
        shutil.copy2(src, target)
    print(f"installed {len(new_files)} new index files as {DB_NAME}.*")

    # provenance: replace the aggregate source FASTA too
    backup_fa = SOURCE_FA.with_name(SOURCE_FA.name + f".corrupt_bak_{stamp}")
    shutil.move(str(SOURCE_FA), backup_fa)
    shutil.move(str(PATCHED_FA), SOURCE_FA)
    print(f"source FASTA replaced ({backup_fa} keeps the corrupt aggregate)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corrected", type=Path, default=CORRECTED_FA)
    parser.add_argument("--patch", action="store_true", help="only patch the aggregate FASTA")
    parser.add_argument("--apply", action="store_true",
                        help="build the replacement DB and install it")
    args = parser.parse_args()
    if not args.patch and not args.apply:
        parser.print_help()
        return 0

    print("loading corrected records …", flush=True)
    corrected = read_corrected(args.corrected)
    print(f"corrected records: {len(corrected):,}")
    if not SOURCE_FA.exists():
        print("ERROR: source aggregate FASTA missing:", SOURCE_FA)
        return 2
    print(f"source aggregate FASTA: {SOURCE_FA.stat().st_size / 1e9:.1f} GB")

    replaced, _ = patch_fasta(corrected)
    if replaced < len(corrected):
        print(f"ABORT: only {replaced:,} of {len(corrected):,} records patched")
        return 2
    if args.patch and not args.apply:
        return 0

    build_db()
    if not verify_db():
        return 2
    install()
    print("done — verify /api/sequence/by-gene?gene_id=<03G ID>.1 (default db) and "
          "a BLAST search against all_gene")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
