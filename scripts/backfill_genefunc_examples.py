#!/usr/bin/env python3
"""Backfill Genefunc_registry example columns by deriving demo regions.

Genomes imported without curated examples leave example_species_chr_id NULL;
the getfasta "Supported genomes" chips then have nothing to fill. This script
derives a guaranteed-valid demo region "<seqid>:200-500" for each such row by
matching the genome's species token against the real sequence names of the
all_genomes BLAST database, and writes the winner into example_species_chr_id.
Curated rows are never touched (guarded by IS NULL).

Matching is the Python twin of the frontend _genomeTokens/guessGenomeRegion,
so UI behaviour and stored values stay consistent. Run with no flags for a
dry-run report; add --write to persist.

Usage (on the server):
    export DB_PASSWORD=...
    python3 scripts/backfill_genefunc_examples.py              # dry run
    python3 scripts/backfill_genefunc_examples.py --write      # persist
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

import pymysql

BLASTDBCMD_DEFAULT = "/var/www/html/blast/blast+/bin/blastdbcmd"
BLAST_DB_DIR_DEFAULT = "/var/www/html/getfasta/blastdb"


# ---------------------------------------------------------------------------
# matching helpers (keep in sync with app/static/getfasta/index.html)
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def species_tokens(display_name: str) -> list[str]:
    """Token candidates from a registry display_name like AABBDD_arinalrfor_PGSBv2_1."""
    nm = display_name or ""
    if nm.startswith("Genefunc_"):
        nm = nm[len("Genefunc_"):]
    if nm.endswith("_table"):
        nm = nm[:-len("_table")]
    parts = nm.split("_")
    if len(parts) > 1 and re.fullmatch(r"[A-Za-z]{1,8}", parts[0] or ""):
        parts = parts[1:]                      # drop karyotype prefix
    toks = [_norm("_".join(parts))]
    if parts and parts[0]:
        toks.append(_norm(parts[0]))           # first word only
    if len(parts) > 1:
        toks.append(_norm("_".join(parts[:2])))
    # dedupe, drop tiny tokens, longest first
    out: list[str] = []
    for t in sorted({t for t in toks if len(t) >= 3}, key=len, reverse=True):
        if t not in out:
            out.append(t)
    return out


def _match_score(tokens: list[str], suf: str) -> int:
    """Two-tier scoring; -1 = no match (mirrors the frontend matcher)."""
    if not suf:
        return -1
    if suf in tokens:
        return 0
    if len(suf) >= 4 and any(suf in t for t in tokens):
        return 1
    if any(len(t) >= 5 and suf.find(t) != -1 for t in tokens):
        return 1
    return -1


def guess_region(tokens: list[str], chroms: list[str]) -> str | None:
    """Best match wins by (score, chr01-first, shortest); append :200-500.

    Both suffix candidates are tried per seqid: the last underscore segment
    and everything after the first one ('Chr1A_Svevo_V2' -> 'v2', 'svevov2').
    """
    best = None  # (score, rank, seqid)
    for c in chroms:
        us_first = c.find("_")
        us_last = c.rfind("_")
        last_seg = _norm(c[us_last + 1:]) if us_last >= 0 else _norm(c)
        rest_seg = _norm(c[us_first + 1:]) if us_first >= 0 else ""
        sc = max(_match_score(tokens, last_seg), _match_score(tokens, rest_seg))
        if sc < 0:
            continue
        rank = 0 if re.match(r"chr0?1[^0-9]", c, re.IGNORECASE) else 1
        if best is None or (sc, rank, len(c)) < (best[0], best[1], len(best[2])):
            best = (sc, rank, c)
    return f"{best[2]}:200-500" if best else None


def load_chromosomes(args) -> list[str]:
    """Real seqids of the merged database, filtered to chromosome-style names."""
    pat = re.compile(r"^chr", re.IGNORECASE)
    if args.chrom_list_file:
        with open(args.chrom_list_file, encoding="utf-8") as fh:
            raw = [ln.strip() for ln in fh if ln.strip()]
    else:
        cmd = [args.blastdbcmd, "-db", os.path.join(args.blast_db_dir, args.db_name),
               "-entry", "all", "-outfmt", "%a"]
        print(f"enumerating {args.db_name} seqids via blastdbcmd ...", flush=True)
        res = subprocess.run(cmd, cwd=args.blast_db_dir,
                             capture_output=True, text=True, check=True)
        raw = res.stdout.splitlines()
    return sorted({ln.strip() for ln in raw if ln.strip() and pat.match(ln.strip())})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=3306)
    ap.add_argument("--user", default="wheatomics_user")
    ap.add_argument("--password", default=os.environ.get("DB_PASSWORD"),
                    help="DB password (or export DB_PASSWORD)")
    ap.add_argument("--database", default="Genefuncdb")
    ap.add_argument("--blastdbcmd", default=BLASTDBCMD_DEFAULT)
    ap.add_argument("--blast-db-dir", default=BLAST_DB_DIR_DEFAULT)
    ap.add_argument("--db-name", default="all_genomes")
    ap.add_argument("--chrom-list-file",
                    help="optional newline file of seqids (skips blastdbcmd; for offline tests)")
    ap.add_argument("--write", action="store_true",
                    help="persist derived regions (default: dry run)")
    args = ap.parse_args()
    if not args.password:
        ap.error("--password is required (or export DB_PASSWORD)")

    chroms = load_chromosomes(args)
    print(f"chromosome-style seqids: {len(chroms)}")
    if not chroms:
        print("[ERR] empty chromosome list - aborting")
        return 1

    conn = pymysql.connect(host=args.host, port=args.port, user=args.user,
                           password=args.password, database=args.database,
                           charset="utf8mb4", autocommit=False)
    try:
        cur = conn.cursor(pymysql.cursors.DictCursor)
        cur.execute(
            "SELECT id, table_name, display_order "
            "FROM Genefunc_registry WHERE visible = 1 "
            "AND example_species_chr_id IS NULL ORDER BY display_order, id"
        )
        rows = cur.fetchall()
        print(f"registry rows without an example region: {len(rows)}\n")

        derived: list[tuple[int, str]] = []
        misses: list[str] = []
        for r in rows:
            tn = r["table_name"] or ""
            # table_name carries the genome words; display_name may be richer
            label = tn.replace("Genefunc_", "").replace("_table", "")
            toks = species_tokens(label)
            reg = guess_region(toks, chroms) if toks else None
            if reg:
                derived.append((r["id"], reg))
                print(f"  {label:<42} -> {reg}")
            else:
                misses.append(label)
                print(f"  {label:<42} -> (no match)")

        print(f"\nderived {len(derived)}, unmatched {len(misses)}")
        if misses:
            print("unmatched:", ", ".join(misses[:12]) + (" ..." if len(misses) > 12 else ""))

        if args.write and derived:
            cur.executemany(
                "UPDATE Genefunc_registry SET example_species_chr_id = %s "
                "WHERE id = %s AND example_species_chr_id IS NULL",
                [(reg, rid) for rid, reg in derived],
            )
            conn.commit()
            print(f"WROTE {cur.rowcount} example regions (rowcount reflects last batch stmt)")
        elif not args.write:
            print("\n(dry run: pass --write to store these into example_species_chr_id)")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
