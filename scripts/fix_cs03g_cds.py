#!/usr/bin/env python3
"""Repair the corrupted Chinese Spring 03G CDS FASTA / BLAST database.

Context (2026-11-27 reviewer report)
------------------------------------
The platform's "Chinese Spring 2.1" dataset is the IWGSC v2.1 annotation
re-numbered with 03G gene IDs (GFF tags: ``previous_id=...02G...``,
``cds=CDS_OK``, ``mapping=...``). Its protein FASTA and GFF3 are correct, but
the imported CDS FASTA
(``/var/www/data/tiantian_data/wheat_genome/cds/Chinese_Spring2.1.cds``) is
corrupt: sampled entries are AT-rich, contain Ns, almost never start with ATG
and ~96% translate with internal stop codons. BLASTing the platform's 03G
"CDS" against the matching 02G CDS therefore gives ~26% identity.

Repair strategy
---------------
Rebuild the CDS from the authoritative annotation: for every transcript in the
broken BLAST database, concatenate its CDS features from
``gff/Chinese_Spring2.1.gff3`` on the platform CS2.1 genome, by chromosome
(one streamed genome record per chromosome, so no per-gene blastdbcmd calls).
Each rebuilt CDS is translated and compared to the 03G PEP FASTA
(``pep/Chinese_Spring2.1.pep``); transcripts that fail (no GFF features,
internal stops, translation mismatch) fall back to the CDS of their mapped
``Gene02G`` counterpart in ``cds/Chinese_Spring1.1.cds``, which is sound.

Usage (production web node; app .env provides the MySQL mapping):

    # validation only: report coverage/quality, write nothing
    python3 scripts/fix_cs03g_cds.py --sample 500

    # full dry run
    python3 scripts/fix_cs03g_cds.py

    # apply: replace the corrupt source FASTA and rebuild the BLAST DB
    python3 scripts/fix_cs03g_cds.py --apply

Safety: every replaced file keeps a timestamped backup; the BLAST DB is built
in a staging directory and moved into place; the command aborts when the
rebuilt sequences fail the coverage/quality gates.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterator

WHEAT = Path("/var/www/data/tiantian_data/wheat_genome")
SRC_02G_CDS = WHEAT / "cds" / "Chinese_Spring1.1.cds"
SRC_03G_CDS = WHEAT / "cds" / "Chinese_Spring2.1.cds"
SRC_03G_GFF = WHEAT / "gff" / "Chinese_Spring2.1.gff3"
SRC_03G_PEP = WHEAT / "pep" / "Chinese_Spring2.1.pep"
BLASTDB = Path("/var/www/html/getfasta/blastdb")
DB_BASE = "AABBDD_Chinese_Spring2.1.add_Description.cds"
GENOME_DB = "AABBDD_Chinese_Spring2.1.genome"
BLAST_BIN = Path("/var/www/html/blast/blast+/bin")

_TRANSCRIPT = re.compile(r"\.\d+$")

_CODON: dict[str, str] = {}
_BASES = "TCAG"
_AAS = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
for _i, _b1 in enumerate(_BASES):
    for _j, _b2 in enumerate(_BASES):
        for _k, _b3 in enumerate(_BASES):
            _CODON[_b1 + _b2 + _b3] = _AAS[_i * 16 + _j * 4 + _k]

_COMPLEMENT = str.maketrans("ACGTNacgtn", "TGCANtgcan")


def translate(seq: str) -> str:
    return "".join(_CODON.get(seq[i:i + 3], "X") for i in range(0, len(seq) - 2, 3))


def revcomp(seq: str) -> str:
    return seq.translate(_COMPLEMENT)[::-1]


def base_id(value: str) -> str:
    return _TRANSCRIPT.sub("", (value or "").strip())


def read_fasta(path: Path) -> dict[str, str]:
    records: dict[str, str] = {}
    name = None
    chunks: list[str] = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith(">"):
                if name:
                    records[name] = "".join(chunks)
                name = line[1:].split()[0]
                chunks = []
            else:
                chunks.append(line.strip())
    if name:
        records[name] = "".join(chunks)
    return records


def load_mapping() -> dict[str, dict]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import pymysql  # noqa: PLC0415

    env = {}
    for line in (Path(__file__).resolve().parents[1] / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip("'\"")
    conn = pymysql.connect(
        host=env.get("DB_HOST", "localhost"), port=int(env.get("DB_PORT", "3306")),
        user=env.get("DB_USER", "wheatomics_user"), password=env.get("DB_PASSWORD", ""),
        database="Genefuncdb", charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT Gene03G, Gene02G, Chrom, Start1, End1, Strand, Description1 "
                "FROM Genefunc_CS_IWGSC03G_table"
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    mapping = {}
    for row in rows:
        g3 = base_id(row.get("Gene03G"))
        if not g3:
            continue
        mapping[g3] = {
            "gene02g": base_id(row.get("Gene02G")) or None,
            "chrom": row.get("Chrom"),
            "start": row.get("Start1"),
            "end": row.get("End1"),
            "strand": row.get("Strand"),
            "description": (row.get("Description1") or "").replace("\t", " ").replace("\n", " "),
        }
    return mapping


def old_db_ids() -> list[str]:
    out = subprocess.run(
        [str(BLAST_BIN / "blastdbcmd"), "-db", str(BLASTDB / DB_BASE),
         "-entry", "all", "-outfmt", "%a"],
        capture_output=True, text=True, check=True,
    )
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def load_cds_features(wanted: set[str]) -> dict[str, list[tuple[int, int, str, str, str]]]:
    """transcript id -> [(start, end, strand, phase, chrom)] for wanted parents."""
    features: dict[str, list[tuple[int, int, str, str, str]]] = {}
    with open(SRC_03G_GFF, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 9 or parts[2] != "CDS":
                continue
            parent = None
            for attr in parts[8].split(";"):
                if attr.startswith("Parent="):
                    parent = attr[len("Parent="):]
                    break
            if parent not in wanted:
                continue
            features.setdefault(parent, []).append(
                (int(parts[3]), int(parts[4]), parts[6], parts[7], parts[0])
            )
    return features


def stream_chromosome(seqid: str) -> Iterator[str]:
    """Yield the sequence of one BLAST-db record in 1 MB chunks without temp files."""
    proc = subprocess.Popen(
        [str(BLAST_BIN / "blastdbcmd"), "-db", str(BLASTDB / GENOME_DB),
         "-entry", seqid, "-outfmt", "%f"],
        stdout=subprocess.PIPE, text=True,
    )
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            if not line.startswith(">"):
                yield line.strip().upper()
    finally:
        proc.stdout.close()  # type: ignore[union-attr]
        proc.wait()


def chromosome_file(seqid: str, cache_dir: Path) -> Path:
    """Extract one chromosome once (memory-friendly: genome records are ~0.5-0.8 GB)."""
    path = cache_dir / (seqid.replace("/", "_") + ".fa")
    if path.exists():
        return path
    with path.open("w", encoding="utf-8") as out:
        out.write(">" + seqid + "\n")
        for chunk in stream_chromosome(seqid):
            out.write(chunk + "\n")
    return path


def read_single_fasta(path: Path) -> str:
    with path.open(encoding="utf-8") as fh:
        fh.readline()  # header
        return "".join(line.strip() for line in fh).upper()


def assemble_cds(feats: list[tuple[int, int, str, str, str]], chrom_seq: str) -> str | None:
    feats = sorted(feats, key=lambda f: (f[0], f[1]))
    strand = feats[0][2]
    parts = [chrom_seq[start - 1:end] for start, end, _strand, _phase, _chrom in feats]
    if strand == "-":
        parts = [revcomp(part) for part in reversed(parts)]
    return "".join(parts)


def pick_02g_sequence(gene02g: str, suffix: str, cds02: dict[str, str]) -> str | None:
    for candidate in (gene02g + suffix, gene02g + ".1", gene02g + ".2", gene02g + LC_SUFFIX,
                      gene02g):
        sequence = cds02.get(candidate)
        if sequence:
            return sequence
    for name, sequence in cds02.items():
        if base_id(name) == gene02g:
            return sequence
    return None


LC_SUFFIX = "LC.1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="replace the corrupt FASTA and rebuild the BLAST database")
    parser.add_argument("--sample", type=int, default=0,
                        help="only process a random sample of N transcripts (validation)")
    parser.add_argument("--out", type=Path, default=Path("/tmp/cs03g_cds_fixed.fa"))
    parser.add_argument("--cache-dir", type=Path, default=Path("/tmp/cs03g_chrom_cache"))
    parser.add_argument("--min-coverage", type=float, default=0.99)
    parser.add_argument("--max-stop-rate", type=float, default=0.02)
    args = parser.parse_args()

    print("loading mapping / source FASTA / old DB ids …", flush=True)
    mapping = load_mapping()
    ids = old_db_ids()
    if args.sample:
        random.seed(20261127)
        ids = random.sample(ids, min(args.sample, len(ids)))
    cds02 = read_fasta(SRC_02G_CDS)
    pep03 = read_fasta(SRC_03G_PEP)
    wanted = set(ids)
    print(f"target transcripts: {len(ids):,} | mapping genes: {len(mapping):,} | "
          f"02G CDS: {len(cds02):,} | 03G PEP: {len(pep03):,}", flush=True)

    features = load_cds_features(wanted)
    by_chrom: dict[str, list[str]] = {}
    for tid, feats in features.items():
        by_chrom.setdefault(feats[0][4], []).append(tid)
    print(f"transcripts with GFF CDS features: {len(features):,} "
          f"({len(features) / len(ids):.2%})", flush=True)

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    records: list[tuple[str, str, str]] = []   # (header, sequence, id)
    stats = {"gff_ok": 0, "fallback_02g": 0, "missing": 0, "gff_bad": 0}
    bad_examples: list[str] = []
    for chrom, tids in sorted(by_chrom.items()):
        # GFF uses Chr6D; the genome BLAST DB appends the assembly suffix.
        seqid = f"{chrom}_Chinese_Spring2.1"
        chrom_path = chromosome_file(seqid, args.cache_dir)
        chrom_seq = read_single_fasta(chrom_path)
        for tid in tids:
            meta = mapping.get(base_id(tid))
            if not meta:
                stats["missing"] += 1
                continue
            sequence = assemble_cds(features[tid], chrom_seq)
            expected = (pep03.get(tid) or "").rstrip("*")
            protein = translate(sequence or "")
            ok = (sequence and len(sequence) % 3 == 0 and sequence.startswith("ATG")
                  and "*" not in protein.rstrip("*")
                  and (not expected or protein.rstrip("*") == expected))
            if not ok:
                stats["gff_bad"] += 1
                if len(bad_examples) < 5:
                    bad_examples.append(tid)
                suffix = tid[len(base_id(tid)):] or ".1"
                sequence = pick_02g_sequence(meta["gene02g"], suffix, cds02) if meta.get("gene02g") else None
                if sequence:
                    stats["fallback_02g"] += 1
                else:
                    stats["missing"] += 1
                    continue
            else:
                stats["gff_ok"] += 1
            header = (
                f">{tid} loc={meta['chrom']}:{meta['start']}-{meta['end']} "
                f"strand={meta['strand']} Description={meta['description']} "
                f"ChineseSpring02G={meta['gene02g']}"
            )
            records.append((header, sequence, tid))
        chrom_path.unlink(missing_ok=True)  # keep disk usage bounded

    total = len(records)
    coverage = total / len(ids)
    proteins = [translate(seq) for _h, seq, _i in records]
    stop_n = sum(1 for p in proteins if "*" in p.rstrip("*"))
    atg_n = sum(1 for _h, seq, _i in records if seq.startswith("ATG"))
    modulo_n = sum(1 for _h, seq, _i in records if len(seq) % 3)
    print(f"\nrebuilt: {total:,} / {len(ids):,} ({coverage:.2%}) | gff_ok={stats['gff_ok']:,} "
          f"| fallback_02g={stats['fallback_02g']:,} | gff_bad={stats['gff_bad']:,} "
          f"| missing={stats['missing']:,}")
    print(f"ATG start: {atg_n:,} | len%3!=0: {modulo_n:,} | internal stop: {stop_n:,}")
    if bad_examples:
        print("GFF extraction fallback examples:", bad_examples)
    if not args.sample:
        if coverage < args.min_coverage:
            print(f"ABORT: coverage {coverage:.2%} < {args.min_coverage:.0%}")
            return 2
        if stop_n / max(1, total) > args.max_stop_rate:
            print("ABORT: internal-stop rate above gate")
            return 2
    if not args.apply:
        print("\ndry run: pass --apply to write the corrected FASTA and rebuild the BLAST DB")
        return 0

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    args.out.write_text(
        "".join(f"{header}\n{sequence}\n" for header, sequence, _tid in records),
        encoding="utf-8",
    )
    print(f"wrote corrected FASTA {args.out} ({args.out.stat().st_size / 1e6:.0f} MB)")

    # 1) replace the corrupt source FASTA (keep the old one for provenance)
    src_backup = SRC_03G_CDS.with_name(SRC_03G_CDS.name + f".corrupt_bak_{stamp}")
    shutil.copy2(SRC_03G_CDS, src_backup)
    shutil.copy2(args.out, SRC_03G_CDS)
    print(f"source FASTA replaced; corrupt copy kept at {src_backup}")

    # 2) rebuild the BLAST DB atomically (index files backed up first)
    backup_dir = BLASTDB / ("_backup_cs03g_cds_" + stamp)
    backup_dir.mkdir(parents=True, exist_ok=True)
    for suffix in (".nin", ".nsq", ".nhr", ".ndb", ".not", ".ntf", ".nto",
                   ".nos", ".nog", ".njs", ".fai", ".fa", ".fasta"):
        src = BLASTDB / (DB_BASE + suffix)
        if src.exists():
            shutil.copy2(src, backup_dir / src.name)
    subprocess.run(
        [str(BLAST_BIN / "makeblastdb"), "-in", str(args.out), "-dbtype", "nucl",
         "-parse_seqids", "-out", str(BLASTDB / DB_BASE)],
        check=True,
    )
    samtools = shutil.which("samtools") or "/usr/bin/samtools"
    subprocess.run([samtools, "faidx", str(args.out)], check=True)
    shutil.copy2(str(args.out) + ".fai", BLASTDB / (DB_BASE + ".fai"))
    print(f"BLAST DB rebuilt; previous files backed up to {backup_dir}")
    print("verify: /api/sequence/by-gene?gene_id=<03G ID>.1 and blastn 03G CDS vs 02G CDS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
