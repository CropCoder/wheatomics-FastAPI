#!/usr/bin/env python3
"""Preflight audit for merging BLAST aggregate alias members.

Read-only by default.  It inspects an aggregate alias such as ``all_genes.nal``
or ``all_proteins.pal`` and reports:

* member count and whether each member database is readable;
* sequence/base counts from ``blastdbcmd -info``;
* duplicate sequence IDs across members (the blocker for a merged physical DB);
* a duplicate map (ID -> first/canonical member) that the build script uses.

The aliases are plain text files with a ``DBLIST <member> <member> ...`` line.
BLAST aliases are limited to 200 members in this installation (see
``rebuild_getfasta_aggregates.py``); this script reports the limit explicitly.

Examples on the web node::

    python3 scripts/plan_blast_aggregate_merge.py \
        --alias all_genes.nal --dup-map /tmp/all_genes.dups.tsv \
        --report /tmp/all_genes.audit.json

    # quick smoke audit of five members
    python3 scripts/plan_blast_aggregate_merge.py \
        --alias all_proteins.pal --limit 5 --sample 20

No files in the BLAST database directory are modified.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

BLASTDB = Path("/var/www/html/getfasta/blastdb")
BLASTDBCMD = Path("/var/www/html/blast/blast+/bin/blastdbcmd")
ALIAS_MEMBER_LIMIT = 200


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


def db_info(member: str) -> dict:
    """Return a small info dict; do not raise on a broken member."""
    result = {
        "member": member,
        "exists": False,
        "sequences": 0,
        "bases": 0,
        "date": "",
        "error": "",
    }
    try:
        proc = subprocess.run(
            [str(BLASTDBCMD), "-db", member, "-info"],
            cwd=str(BLASTDB),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["error"] = str(exc)
        return result
    if proc.returncode != 0:
        result["error"] = (proc.stderr or proc.stdout).strip()[:400]
        return result
    result["exists"] = True
    for line in proc.stdout.splitlines():
        clean = line.replace(",", "").strip()
        if "sequences" in clean:
            try:
                result["sequences"] = int(clean.split()[0])
            except (ValueError, IndexError):
                pass
        if "total bases" in clean or "total residues" in clean:
            try:
                result["bases"] = int(clean.split()[0])
            except (ValueError, IndexError):
                pass
        if clean.startswith("Date:"):
            result["date"] = clean[5:].strip()
    return result


def iter_member_ids(member: str, strip_suffix: bool = True):
    """Yield sequence IDs from a member DB, streaming.

    Some legacy DBs were built without -parse_seqids; fall back from -outfmt %a
    to the default FASTA headers if -outfmt returns no ids.
    """
    cmd = [str(BLASTDBCMD), "-db", member, "-entry", "all", "-outfmt", "%a"]
    proc = subprocess.Popen(
        cmd,
        cwd=str(BLASTDB),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    yielded = 0
    assert proc.stdout is not None
    for line in proc.stdout:
        text = line.strip()
        if not text:
            continue
        # -outfmt %a prints the accession; default FASTA fallback starts with >
        ident = text[1:].split(None, 1)[0] if text.startswith(">") else text.split(None, 1)[0]
        if not ident:
            continue
        yielded += 1
        yield ident
    rc = proc.wait()
    if yielded == 0 or rc != 0:
        # Retry with the default FASTA output.
        proc = subprocess.Popen(
            [str(BLASTDBCMD), "-db", member, "-entry", "all"],
            cwd=str(BLASTDB),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            if line.startswith(">"):
                ident = line[1:].split(None, 1)[0]
                if ident:
                    yield ident
        proc.wait()


def main() -> int:
    global BLASTDB
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--alias", required=True,
                    help="Alias filename, e.g. all_genes.nal or all_proteins.pal")
    ap.add_argument("--blastdb", default=str(BLASTDB),
                    help="BLAST database directory")
    ap.add_argument("--members", nargs="*", default=None,
                    help="Audit only these members (default: all alias members)")
    ap.add_argument("--limit", type=int, default=0,
                    help="Audit only the first N members (pilot mode)")
    ap.add_argument("--no-id-audit", action="store_true",
                    help="Skip the sequence-ID duplicate scan (fast metadata only)")
    ap.add_argument("--report", default="",
                    help="Write JSON audit report to this path")
    ap.add_argument("--dup-map", default="",
                    help="Write TSV of duplicate IDs and their first member")
    ap.add_argument("--sample", type=int, default=20,
                    help="Number of duplicate examples in the report")
    args = ap.parse_args()

    BLASTDB = Path(args.blastdb)
    alias_path = Path(args.alias)
    if not alias_path.is_absolute():
        alias_path = BLASTDB / alias_path
    title, alias_members = read_alias(alias_path)
    members = args.members or alias_members
    if args.limit > 0:
        members = members[: args.limit]

    seen_members: dict[str, str] = {}
    duplicate_members: list[dict] = []
    for member in members:
        if member in seen_members:
            duplicate_members.append({"member": member, "first_member": seen_members[member]})
        else:
            seen_members[member] = member

    infos = [db_info(member) for member in members]
    total_sequences = sum(i["sequences"] for i in infos)
    total_bases = sum(i["bases"] for i in infos)

    duplicate_ids: list[dict] = []
    id_count = 0
    unique_ids = 0
    seen_ids: dict[str, str] = {}
    if not args.no_id_audit:
        for info in infos:
            member = info["member"]
            if not info["exists"]:
                continue
            for ident in iter_member_ids(member):
                id_count += 1
                first = seen_ids.get(ident)
                if first is None:
                    seen_ids[ident] = member
                    unique_ids += 1
                elif first != member:
                    duplicate_ids.append({
                        "id": ident,
                        "first_member": first,
                        "duplicate_member": member,
                    })
    else:
        unique_ids = -1

    report = {
        "alias": str(alias_path),
        "title": title,
        "alias_member_count": len(alias_members),
        "members_audited": len(members),
        "alias_limit": ALIAS_MEMBER_LIMIT,
        "over_alias_limit": len(alias_members) > ALIAS_MEMBER_LIMIT,
        "duplicate_member_entries": duplicate_members,
        "total_sequences_reported": total_sequences,
        "total_bases_reported": total_bases,
        "id_audit": not args.no_id_audit,
        "id_count": id_count,
        "unique_ids": unique_ids,
        "duplicate_id_count": len(duplicate_ids),
        "duplicate_id_examples": duplicate_ids[: max(0, args.sample)],
        "broken_members": [i for i in infos if not i["exists"]],
        "members": infos,
    }

    if args.report:
        Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.dup_map:
        with open(args.dup_map, "w", encoding="utf-8") as fh:
            fh.write("#id\tfirst_member\tduplicate_member\n")
            for row in duplicate_ids:
                fh.write(f"{row['id']}\t{row['first_member']}\t{row['duplicate_member']}\n")

    print(json.dumps({
        "alias": alias_path.name,
        "members": len(alias_members),
        "audited": len(members),
        "over_limit": len(alias_members) > ALIAS_MEMBER_LIMIT,
        "duplicate_member_entries": len(duplicate_members),
        "broken_members": len(report["broken_members"]),
        "id_count": id_count,
        "unique_ids": unique_ids,
        "duplicate_id_count": len(duplicate_ids),
        "report": args.report,
        "dup_map": args.dup_map,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
