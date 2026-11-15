#!/usr/bin/env python3
"""Safely update a BLAST aggregate alias (all_genomes.nal, all_genes.nal, ...).

The platform uses a **base + delta** layout for the aggregate libraries
(see ``docs/workflow/blast-aggregate-base-delta.md``):

* ``all_genes_base`` / ``all_proteins_base`` are physical merged databases
  built by ``build_blast_aggregate_base.py``; they hold the bulk of the old
  members;
* the public alias (``all_genes.nal`` ...) is a ``DBLIST`` of
  ``<base> <delta1> <delta2> ...``, where each delta is a new genome's
  per-genome BLAST database added after onboarding;
* ``all_genomes.nal`` is still a legacy per-genome ``DBLIST`` because the
  chromosome-level collection is too large to merge into one physical DB.

This helper is the single maintenance entry point for those alias files::

    # append a new genome's CDS/PEP DB to a base+delta alias
    python3 scripts/update_blast_alias.py --alias all_genes.nal \
        --mode append --members AABBDD_NewGenome.add_Description.cds --apply

    # append to an alias that is already at/over the 200-member BLAST limit
    # (all_genomes: the new member is prepended so that it stays readable)
    python3 scripts/update_blast_alias.py --alias all_genomes.nal \
        --mode append --members AABB_NewGenome.genome --allow-overlimit --apply

    # initial migration of a legacy alias to a merged base
    python3 scripts/update_blast_alias.py --alias all_genes.nal \
        --mode switch --base all_genes_base --apply

    # explicit alias set (compaction / recovery)
    python3 scripts/update_blast_alias.py --alias all_genes.nal \
        --mode set --members all_genes_base delta1 delta2 --apply

Safety properties:

* reads/validates members before writing, dedupes while keeping order;
* validates each *new* member database (files present + ``blastdbcmd -info``);
* takes an ``flock`` so two sessions cannot interleave writes;
* backs up the alias, writes a temporary file and atomically renames it;
* verifies the new alias with ``blastdbcmd -info`` (optional ``--check-entry``)
  and rolls back to the backup if verification fails;
* refuses to exceed BLAST's 200-member alias limit unless
  ``--allow-overlimit`` is given (then new members are prepended, because
  ``blastdbcmd -entry_batch`` only reads the first 200 members);
* prints the detected layout (base+delta vs legacy) before changing anything.

Environment overrides (handy for tests / staging):
``WHEATOMICS_BLASTDB``, ``WHEATOMICS_BLASTDBCMD``.
"""
from __future__ import annotations

import argparse
import fcntl
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

BLASTDB = Path(os.environ.get("WHEATOMICS_BLASTDB", "/var/www/html/getfasta/blastdb"))
BLASTDBCMD = Path(
    os.environ.get("WHEATOMICS_BLASTDBCMD", "/var/www/html/blast/blast+/bin/blastdbcmd")
)
ALIAS_LIMIT = 200          # blastdbcmd -entry_batch only reads the first 200 members
DEFAULT_WARN_AT = 180
DB_EXTENSIONS = ("nhr", "phr", "pdb", "pot", "nos", "nsq", "nin", "nog")  # nucl + prot

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_LIMIT = 2
EXIT_VERIFY = 3
EXIT_INVALID = 4
EXIT_LOCK = 5


# --------------------------------------------------------------------------- io
def read_alias(path: Path) -> tuple[str, list[str]]:
    """Return (title, members) of an alias file; raise SystemExit if missing."""
    if not path.exists():
        raise SystemExit(f"[ERROR] alias not found: {path}")
    title, members = "", []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.upper().startswith("TITLE"):
            title = line[5:].strip()
        elif line.upper().startswith("DBLIST"):
            members = line[6:].split()
    if not members:
        raise SystemExit(f"[ERROR] {path.name} has no DBLIST members")
    return title, members


def read_member_file(path: str) -> list[str]:
    members: list[str] = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            members.extend(line.split())
    return members


def dedupe_keep_order(items: list[str]) -> tuple[list[str], list[str]]:
    seen: set[str] = set()
    unique: list[str] = []
    dups: list[str] = []
    for item in items:
        if item in seen:
            dups.append(item)
        else:
            seen.add(item)
            unique.append(item)
    return unique, dups


def is_base_member(member: str) -> bool:
    """A base member is a merged physical DB (``all_genes_base``, ``x_base``)."""
    stem = member.rsplit(".", 1)[0]
    return stem.endswith("_base") or "_base__" in member


def layout_of(members: list[str]) -> str:
    bases = [m for m in members if is_base_member(m)]
    if not bases:
        return f"legacy ({len(members)} per-genome members)"
    deltas = len(members) - len(bases)
    return f"base+delta (base={'/'.join(bases)}, deltas={deltas})"


class AliasLock:
    """Advisory ``flock`` around the whole read-modify-write sequence."""

    def __init__(self, blastdb: Path, timeout: float = 30.0):
        self.path = blastdb / ".alias_update.lock"
        self.timeout = timeout
        self._fh = None

    def __enter__(self):
        self._fh = open(self.path, "w")
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    self._fh.close()
                    raise SystemExit(
                        f"[ERROR] could not lock {self.path} within {self.timeout:g}s "
                        "(another alias update is running?)"
                    )
                time.sleep(0.2)

    def __exit__(self, *exc):
        if self._fh:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
            self._fh.close()


# ---------------------------------------------------------------- validation
def member_db_files(member: str, blastdb: Path) -> list[Path]:
    """Existing physical files of an alias member (``db.00.nhr`` included)."""
    found: list[Path] = []
    for ext in DB_EXTENSIONS:
        for candidate in (blastdb / f"{member}.{ext}", blastdb / f"{member}.00.{ext}"):
            if candidate.exists():
                found.append(candidate)
    return found


def validate_member(member: str, blastdb: Path, blastdbcmd: Path) -> tuple[bool, str]:
    """Check that a member is a real, readable BLAST database under ``blastdb``."""
    if member.startswith("-") or "/" in member or "\\" in member:
        return False, "invalid member name"
    if not member_db_files(member, blastdb):
        return False, "no BLAST database files found"
    if not blastdbcmd.exists():
        return True, "files present (blastdbcmd missing; skipped -info)"
    try:
        proc = subprocess.run(
            [str(blastdbcmd), "-db", member, "-info"],
            cwd=str(blastdb),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:  # pragma: no cover - env
        return False, f"blastdbcmd failed: {exc}"
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, f"blastdbcmd -info failed: {msg[0] if msg else 'unknown error'}"
    return True, (proc.stdout or "").strip().splitlines()[0] if proc.stdout else "ok"


def verify_alias(alias: Path, blastdb: Path, blastdbcmd: Path,
                 check_entry: str | None) -> bool:
    if not blastdbcmd.exists():
        print("[WARN] blastdbcmd not found; skipping alias verification", file=sys.stderr)
        return True
    db_name = alias.stem
    proc = subprocess.run(
        [str(blastdbcmd), "-db", db_name, "-info"],
        cwd=str(blastdb),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        print((proc.stderr or proc.stdout)[:1000], file=sys.stderr)
        return False
    for line in (proc.stdout or "").splitlines()[:3]:
        print("  " + line)
    if check_entry:
        proc = subprocess.run(
            [str(blastdbcmd), "-db", db_name, "-entry", check_entry],
            cwd=str(blastdb),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=180,
        )
        if proc.returncode != 0 or not (proc.stdout or "").strip():
            print(f"[ERROR] --check-entry {check_entry!r} not found in {db_name}",
                  file=sys.stderr)
            return False
        print(f"  entry {check_entry}: found")
    return True


# --------------------------------------------------------------------- write
def write_atomic(path: Path, text: str) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(path.name + ".bak-" + stamp)
    shutil.copy2(path, backup)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return backup


def build_plan(args, current: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Return (new_members, new_delta_candidates, notes)."""
    notes: list[str] = []
    requested = list(args.members or [])
    if args.member_file:
        requested = read_member_file(args.member_file) + requested

    if args.mode == "switch":
        if not args.base:
            raise SystemExit("[ERROR] --base is required for switch mode")
        new = [args.base] + (current if args.keep_deltas else [])
        return new, [args.base], notes
    if args.mode == "append":
        if not requested:
            raise SystemExit("[ERROR] --members (or --member-file) is required for append mode")
        position = args.position
        # Keep the base first; by default append new deltas at the end.
        if position == "append":
            new = current + requested
        else:
            base = [m for m in current if is_base_member(m)]
            new = base + requested + [m for m in current if not is_base_member(m)]
        return new, requested, notes
    # set
    if not requested:
        raise SystemExit("[ERROR] --members (or --member-file) is required for set mode")
    notes.append(f"replacing legacy member list of {len(current)} entries")
    return requested, requested, notes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="update_blast_alias.py",
        description="Safely update a BLAST aggregate alias (base + delta aware).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Modes:", 1)[0].split("Safety properties:", 1)[0],
    )
    ap.add_argument("--alias", required=True,
                    help="alias filename, e.g. all_genes.nal / all_genomes.nal / all_proteins.pal")
    ap.add_argument("--blastdb", default=str(BLASTDB), help="BLAST DB directory")
    ap.add_argument("--blastdbcmd", default=str(BLASTDBCMD), help="blastdbcmd binary")
    ap.add_argument("--mode", choices=("switch", "append", "set"), required=True)
    ap.add_argument("--base", default="", help="physical base DB name (switch mode)")
    ap.add_argument("--members", nargs="*", default=None,
                    help="delta members (append) or complete member list (set)")
    ap.add_argument("--member-file", default="", help="file with member names (one per line)")
    ap.add_argument("--position", choices=("append", "prepend"), default="append",
                    help="where to put new deltas (default: after base/existing members)")
    ap.add_argument("--keep-deltas", action="store_true",
                    help="switch mode: keep current non-base members as deltas")
    ap.add_argument("--allow-overlimit", action="store_true",
                    help=f"allow >{ALIAS_LIMIT} members (new members are prepended)")
    ap.add_argument("--skip-invalid", action="store_true",
                    help="skip new members whose BLAST DB cannot be validated")
    ap.add_argument("--check-entry", default="",
                    help="optional sequence id that must be retrievable after writing")
    ap.add_argument("--warn-at", type=int, default=DEFAULT_WARN_AT)
    ap.add_argument("--lock-timeout", type=float, default=30.0)
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = ap.parse_args(argv)

    blastdb = Path(args.blastdb)
    blastdbcmd = Path(args.blastdbcmd)
    alias = Path(args.alias)
    if not alias.is_absolute():
        alias = blastdb / alias

    with AliasLock(blastdb, args.lock_timeout):
        title, current = read_alias(alias)
        print(f"alias={alias.name} title={title or '-'}")
        print(f"layout: {layout_of(current)}")

        planned, new_members, notes = build_plan(args, current)
        for note in notes:
            print(f"note: {note}")

        # validate the members we are about to add
        valid_new: list[str] = []
        for member in new_members:
            ok, detail = validate_member(member, blastdb, blastdbcmd)
            if ok:
                valid_new.append(member)
                print(f"  [ok] {member}: {detail}")
            else:
                print(f"  [INVALID] {member}: {detail}", file=sys.stderr)
                if not args.skip_invalid:
                    print("[ERROR] aborting; use --skip-invalid to drop invalid members",
                          file=sys.stderr)
                    return EXIT_INVALID
        if new_members and not valid_new:
            if args.mode == "append" and args.skip_invalid:
                print("[WARN] all new members invalid and skipped; alias unchanged")
                return EXIT_OK
            print("[ERROR] no valid new members; nothing to do", file=sys.stderr)
            return EXIT_INVALID

        if args.mode == "append":
            position = args.position
            # If we are about to exceed the alias limit, put new members first so
            # that they stay inside blastdbcmd's first-200-member window.
            if len(current) + len(valid_new) > ALIAS_LIMIT and args.allow_overlimit:
                position = "prepend"
                print(f"note: alias would exceed {ALIAS_LIMIT} members -> prepending deltas")
            base = [m for m in current if is_base_member(m)]
            rest = [m for m in current if not is_base_member(m)]
            if position == "append":
                planned = current + [m for m in valid_new if m not in current]
            else:
                planned = base + [m for m in valid_new if m not in current] + rest
        elif args.mode == "set":
            planned = valid_new
        # switch mode already built planned; filter to valid new members only
        elif args.mode == "switch":
            planned = [args.base] + [m for m in planned[1:] if m in current]

        planned, dups = dedupe_keep_order(planned)
        if dups:
            print(f"note: removed {len(dups)} duplicate member(s)")

        print(f"members: old={len(current)} new={len(planned)}")
        if len(planned) > ALIAS_LIMIT:
            if not args.allow_overlimit:
                print(
                    f"[ERROR] {len(planned)} members exceeds BLAST alias limit "
                    f"{ALIAS_LIMIT}; re-run with --allow-overlimit (new members will be "
                    "prepended, tail members may be unreadable by blastdbcmd)",
                    file=sys.stderr,
                )
                return EXIT_LIMIT
            print(f"[WARN] {len(planned)} members > {ALIAS_LIMIT}: only the first "
                  f"{ALIAS_LIMIT} are guaranteed to be readable by blastdbcmd")
        elif len(planned) >= args.warn_at:
            print(f"[WARN] alias members={len(planned)} approaching limit {ALIAS_LIMIT}",
                  file=sys.stderr)

        print("DBLIST " + " ".join(planned[:4]) + (" ..." if len(planned) > 4 else ""))
        text = "TITLE " + (title or "aggregate") + "\nDBLIST " + " ".join(planned) + "\n"

        if not args.apply:
            print("[DRY-RUN] not writing; add --apply to update the alias")
            return EXIT_OK

        backup = write_atomic(alias, text)
        print(f"backup={backup.name}")
        if not verify_alias(alias, blastdb, blastdbcmd, args.check_entry or None):
            shutil.copy2(backup, alias)
            print("[ERROR] verification failed; rolled back to backup", file=sys.stderr)
            return EXIT_VERIFY
        print("ALIAS_OK")
        return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
