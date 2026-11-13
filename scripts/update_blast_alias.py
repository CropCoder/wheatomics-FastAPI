#!/usr/bin/env python3
"""Safely update a BLAST aggregate alias (all_genes.nal, all_proteins.pal, ...).

BLAST+ cannot append sequences to a physical database, but the alias mechanism
can add new per-genome DBs incrementally.  This helper keeps that maintenance
step explicit and reversible:

* backup the current alias;
* build the new DBLIST (base + delta members or an explicit set);
* write a temporary file and atomically rename it;
* verify the resulting alias with ``blastdbcmd -info``;
* warn/fail when the BLAST 200-member alias limit is approached.

Modes::

    # initial switch: the merged base already contains all old members
    python3 scripts/update_blast_alias.py --alias all_genes.nal \
        --mode switch --base all_genes_base --apply

    # incremental: add a new per-genome DB after integration
    python3 scripts/update_blast_alias.py --alias all_genes.nal \
        --mode append --members AABBDD_NewGenome.add_Description.cds --apply

    # explicit alias set (compaction / recovery)
    python3 scripts/update_blast_alias.py --alias all_genes.nal \
        --mode set --members all_genes_base delta1 delta2 --apply
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

BLASTDB = Path("/var/www/html/getfasta/blastdb")
BLASTDBCMD = Path("/var/www/html/blast/blast+/bin/blastdbcmd")
ALIAS_LIMIT = 200
DEFAULT_WARN_AT = 180


def read_alias(path: Path) -> tuple[str, list[str]]:
    title, members = "", []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.upper().startswith("TITLE"):
            title = line[5:].strip()
        elif line.upper().startswith("DBLIST"):
            members = line[6:].split()
    return title, members


def write_atomic(path: Path, text: str) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(path.name + ".bak-" + stamp)
    shutil.copy2(path, backup)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return backup


def verify(alias: Path) -> bool:
    # blastdbcmd expects the DB name, not the alias filename with .nal/.pal.
    db_name = alias.stem
    proc = subprocess.run(
        [str(BLASTDBCMD), "-db", db_name, "-info"],
        cwd=str(alias.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        print((proc.stderr or proc.stdout)[:1000], file=sys.stderr)
        return False
    print(proc.stdout.splitlines()[0] if proc.stdout else "verified")
    return True


def main() -> int:
    global BLASTDB, BLASTDBCMD
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--alias", required=True,
                    help="Alias filename (all_genes.nal, all_gene.nal, all_proteins.pal, ...)")
    ap.add_argument("--blastdb", default=str(BLASTDB))
    ap.add_argument("--mode", choices=("switch", "append", "set"), required=True)
    ap.add_argument("--base", default="", help="Physical base DB name for switch mode")
    ap.add_argument("--members", nargs="*", default=None,
                    help="Delta members (append) or complete member list (set)")
    ap.add_argument("--warn-at", type=int, default=DEFAULT_WARN_AT)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--blastdbcmd", default=str(BLASTDBCMD))
    args = ap.parse_args()

    BLASTDB = Path(args.blastdb)
    BLASTDBCMD = Path(args.blastdbcmd)
    alias = Path(args.alias)
    if not alias.is_absolute():
        alias = BLASTDB / alias
    title, current = read_alias(alias)

    if args.mode == "switch":
        if not args.base:
            ap.error("--base is required for switch mode")
        members = [args.base]
    elif args.mode == "append":
        if not args.members:
            ap.error("--members is required for append mode")
        members = current + [m for m in args.members if m not in current]
    else:  # set
        if not args.members:
            ap.error("--members is required for set mode")
        seen = set()
        members = [m for m in members if not (m in seen or seen.add(m))]

    if len(members) > ALIAS_LIMIT:
        print(f"ERROR: {len(members)} members exceeds BLAST alias limit {ALIAS_LIMIT}",
              file=sys.stderr)
        return 2
    if len(members) >= args.warn_at:
        print(f"WARNING: alias members={len(members)} approaching limit {ALIAS_LIMIT}",
              file=sys.stderr)

    text = "TITLE " + (title or "aggregate") + "\nDBLIST " + " ".join(members) + "\n"
    print(f"alias={alias.name} old_members={len(current)} new_members={len(members)}")
    print(f"DBLIST {' '.join(members[:3])}{' ...' if len(members) > 3 else ''}")
    if not args.apply:
        print("[DRY-RUN] not writing")
        return 0

    backup = write_atomic(alias, text)
    print(f"backup={backup.name}")
    if not verify(alias):
        # Restore the backup if the new alias is unreadable.
        shutil.copy2(backup, alias)
        print("rollback: restored alias", file=sys.stderr)
        return 3
    print("ALIAS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
