#!/usr/bin/env python3
"""Build a merged physical BLAST base from aggregate alias members.

This is the build side of the base+delta migration plan:

    all_genes.nal  -> all_genes_base + future per-genome delta DBs
    all_proteins.pal -> all_proteins_base + future delta DBs

The BLAST database file itself cannot be appended to with stock BLAST+; the
alias is what provides incremental additions.  This script builds only the
physical base (or a pilot subset).  Alias switching is deliberately left to a
separate verified step.

Duplicate sequence IDs
----------------------
A merged DB must have unique sequence IDs for ``-parse_seqids`` and
``blastdbcmd -entry`` to work.  Duplicate IDs from another member are renamed
with a member namespace, e.g. ``AABBDD_AK58__dup__TraesCS...``.  The first
member (canonical member from the preflight duplicate map) keeps the original
ID so existing by-gene lookups keep working.  Pass ``--dup-map`` produced by
``plan_blast_aggregate_merge.py``; without one the script still detects
duplicates on the fly but has to keep a global ID set in memory.

Safety
------
By default this is a dry run.  It only writes when ``--apply`` is supplied, and
even then writes into ``--staging-dir``; it never modifies the existing alias or
database.  ``makeblastdb`` runs against the staging FASTA.

Examples::

    # pilot: 5 members, no alias switch
    python3 scripts/build_blast_aggregate_base.py \
        --alias all_genes.nal --limit 5 --out-base all_genes_base_pilot \
        --staging-dir /var/www/html/getfasta/blastdb_migration_20261113 \
        --apply

    # full build with preflight duplicate map
    python3 scripts/build_blast_aggregate_base.py \
        --alias all_genes.nal --dup-map /tmp/all_genes.dups.tsv \
        --out-base all_genes_base \
        --staging-dir /var/www/html/getfasta/blastdb_migration_20261113 \
        --apply
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

BLASTDB = Path("/var/www/html/getfasta/blastdb")
BLASTDBCMD = Path("/var/www/html/blast/blast+/bin/blastdbcmd")
MAKEBLASTDB = Path("/var/www/html/blast/blast+/bin/makeblastdb")
DEFAULT_STAGING = Path("/var/www/html/getfasta/blastdb_migration_20261113")


def read_alias(path: Path) -> tuple[str, list[str]]:
    title = ""
    members: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.upper().startswith("TITLE"):
            title = line[5:].strip()
        elif line.upper().startswith("DBLIST"):
            members = line[6:].split()
    return title, members


def load_dup_map(path: Path) -> dict[str, str]:
    """id -> canonical first member."""
    out: dict[str, str] = {}
    if not path:
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) >= 2 and cols[0] and cols[0] not in out:
            out[cols[0]] = cols[1]
    return out


def iter_fasta(member: str):
    """Yield (header, sequence_lines) from a member BLAST DB."""
    proc = subprocess.Popen(
        [str(BLASTDBCMD), "-db", member, "-entry", "all"],
        cwd=str(BLASTDB),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    assert proc.stdout is not None
    header = ""
    seq: list[str] = []
    for line in proc.stdout:
        if line.startswith(">"):
            if header:
                yield header, seq
            header = line.rstrip("\n")
            seq = []
        elif header:
            seq.append(line)
    if header:
        yield header, seq
    proc.wait()


def short_member_prefix(index: int) -> str:
    # BLAST local IDs are limited to 50 characters; a full member name in the
    # prefix overflows.  Keep a short deterministic namespace and write the
    # mapping to <base>.idmap.tsv for traceability.
    return f"m{index:04d}_"


def fit_prefixed_id(prefix: str, ident: str, seen: set[str]) -> str:
    max_len = 50
    suffix = prefix
    keep = max(1, max_len - len(suffix))
    candidate = suffix + ident[-keep:]
    n = 1
    while candidate in seen:
        tail = f"_{n}"
        keep = max(1, max_len - len(suffix) - len(tail))
        candidate = suffix + ident[-keep:] + tail
        n += 1
    return candidate


def main() -> int:
    global BLASTDB, BLASTDBCMD, MAKEBLASTDB
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--alias", required=True)
    ap.add_argument("--blastdb", default=str(BLASTDB))
    ap.add_argument("--staging-dir", default=str(DEFAULT_STAGING))
    ap.add_argument("--out-base", required=True,
                    help="Output BLAST DB base name, e.g. all_genes_base")
    ap.add_argument("--dup-map", default="",
                    help="TSV from plan_blast_aggregate_merge.py (id, first_member, duplicate_member)")
    ap.add_argument("--members", nargs="*", default=None)
    ap.add_argument("--limit", type=int, default=0,
                    help="Pilot: only the first N members")
    ap.add_argument("--apply", action="store_true",
                    help="Actually write staging FASTA and run makeblastdb")
    ap.add_argument("--makeblastdb", default=str(MAKEBLASTDB))
    ap.add_argument("--blastdbcmd", default=str(BLASTDBCMD))
    ap.add_argument("--known-id", default="",
                    help="Optional sequence ID to retrieve after building")
    args = ap.parse_args()

    BLASTDB = Path(args.blastdb)
    BLASTDBCMD = Path(args.blastdbcmd)
    MAKEBLASTDB = Path(args.makeblastdb)

    alias_path = Path(args.alias)
    if not alias_path.is_absolute():
        alias_path = BLASTDB / alias_path
    title, alias_members = read_alias(alias_path)
    members = args.members or alias_members
    if args.limit > 0:
        members = members[: args.limit]
    if not members:
        print("No members selected", file=sys.stderr)
        return 1

    dbtype = "prot" if args.alias.endswith(".pal") else "nucl"
    dup_first = load_dup_map(Path(args.dup_map)) if args.dup_map else {}
    staging = Path(args.staging_dir)
    fasta_path = staging / (args.out_base + ".fa")
    db_path = staging / args.out_base

    print(f"alias={alias_path} title={title!r}")
    print(f"members={len(members)} dbtype={dbtype} staging={staging}")
    print(f"dup_map_ids={len(dup_first)}")
    if not args.apply:
        print("\n[DRY-RUN] would write", fasta_path, "and build", db_path)
        return 0

    staging.mkdir(parents=True, exist_ok=True)
    seen_ids: set[str] = set()
    duplicate_prefixes = 0
    records = 0
    id_map_path = staging / (args.out_base + ".idmap.tsv")
    id_map = open(id_map_path, "w", encoding="utf-8")
    id_map.write("#new_id\told_id\tmember\n")
    tmp_fasta = fasta_path.with_suffix(".fa.tmp")
    with open(tmp_fasta, "w", encoding="utf-8") as out:
        for member_idx, member in enumerate(members, 1):
            prefix = short_member_prefix(member_idx)
            per_member_seen: set[str] = set()
            for header, seq_lines in iter_fasta(member):
                if not header.startswith(">"):
                    continue
                parts = header[1:].split(None, 1)
                if not parts:
                    continue
                ident = parts[0]
                if len(ident) > 50:
                    print(f"ERROR: original sequence id longer than 50 chars: {ident}", file=sys.stderr)
                    return 2
                # If this ID is known to be duplicated and this member is not
                # the canonical owner, rename it.  Also protect against a
                # duplicate inside the same member, and (when no preflight map
                # was supplied) duplicate IDs across members seen earlier.
                if ident in dup_first:
                    must_prefix = (dup_first[ident] != member or ident in per_member_seen)
                else:
                    must_prefix = ident in seen_ids or ident in per_member_seen
                if must_prefix:
                    old_id = ident
                    ident = fit_prefixed_id(prefix, old_id, seen_ids)
                    id_map.write(f"{ident}\t{old_id}\t{member}\n")
                    duplicate_prefixes += 1
                seq = "".join(seq_lines)
                if not seq:
                    continue
                desc = parts[1] if len(parts) > 1 else ""
                out.write(">" + ident + ((" " + desc) if desc else "") + "\n")
                # Keep the original line wrapping if possible; BLAST does not care.
                for line in seq_lines:
                    out.write(line if line.endswith("\n") else line + "\n")
                seen_ids.add(ident)
                per_member_seen.add(parts[0])
                records += 1
    id_map.close()
    tmp_fasta.replace(fasta_path)
    print(f"wrote {fasta_path} records={records} prefixed_duplicates={duplicate_prefixes}")
    print(f"id_map={id_map_path}")

    # Remove stale index files from a previous failed build; keep the FASTA.
    for suffix in (".ndb", ".nhr", ".nin", ".nog", ".nos", ".not", ".nsq", ".ntf", ".nto",
                   ".pdb", ".phr", ".pin", ".pog", ".pos", ".pot", ".psq", ".ptf", ".pto"):
        stale = Path(str(db_path) + suffix)
        if stale.exists():
            stale.unlink()

    # Build only after the FASTA is complete.
    cmd = [
        str(MAKEBLASTDB),
        "-in", str(fasta_path),
        "-dbtype", dbtype,
        "-parse_seqids",
        "-out", str(db_path),
    ]
    print("running:", " ".join(cmd))
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        print((proc.stderr or proc.stdout)[:2000], file=sys.stderr)
        return proc.returncode

    info = subprocess.run(
        [str(BLASTDBCMD), "-db", str(db_path), "-info"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    print(info.stdout.strip()[:1000] if info.stdout else info.stderr[:1000])
    if args.known_id:
        lookup = subprocess.run(
            [str(BLASTDBCMD), "-db", str(db_path), "-entry", args.known_id, "-range", "1-60"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        print(f"known_id {args.known_id}: rc={lookup.returncode}")
        print((lookup.stdout or lookup.stderr)[:800])
        if lookup.returncode != 0 or not lookup.stdout.strip():
            print("Known-ID verification FAILED", file=sys.stderr)
            return 2
    print("BUILD_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
