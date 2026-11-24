#!/usr/bin/env python3
"""Normalize an EGAPx annotation (GFF3 + CDS/PEP FASTA) into WheatOmics platform files.

EGAPx labels transcripts like ``<locus_tag>_<n>`` / ``...t1`` / ``....1``; the
platform requires every mRNA ID to end with ``.<digit>``.  This script:
  * rewrites mRNA IDs (and Parent attributes) to ``<id>.<k>`` when needed,
  * keeps sequence IDs as-is (must already be ``Chr*``; use the GWH/normalized genome),
  * writes ``<tag>.gff3`` / ``<tag>.cds`` / ``<tag>.pep`` and reports counts.

Usage: python3 scripts/normalize_egapx.py --gff ann.gff --cds cds.fna --pep prot.faa \
          --tag Hordeum_brevisubulatum_GWHKGTW --out /path/to/AABBDD_...
"""
from __future__ import annotations
import argparse, re, sys
from pathlib import Path

DIGIT = re.compile(r"\.\d+$")

def parse_attrs(a: str) -> dict[str, str]:
    d = {}
    for kv in a.split(";"):
        if "=" in kv:
            k, v = kv.split("=", 1); d[k] = v
    return d

def fmt_attrs(d: dict[str, str]) -> str:
    return ";".join(f"{k}={v}" for k, v in d.items())

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gff", required=True)
    ap.add_argument("--cds", required=True)
    ap.add_argument("--pep", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--keep-seqids", default="")
    args = ap.parse_args(argv)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    # pass 1: map mRNA id -> platform id
    idmap: dict[str, str] = {}
    with open(args.gff, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("#"): continue
            f = line.rstrip("\n").split("\t")
            if len(f) < 9 or f[2] != "mRNA": continue
            a = parse_attrs(f[8]); mid = a.get("ID", "")
            if mid and not DIGIT.search(mid):
                idmap[mid] = mid + ".1"
    # pass 2: rewrite GFF
    n_mrna = 0
    with open(args.gff, encoding="utf-8", errors="replace") as fi, open(out/f"{args.tag}.gff3", "w", encoding="utf-8") as fo:
        fo.write("##gff-version 3\n")
        for line in fi:
            if line.startswith("#"): continue
            f = line.rstrip("\n").split("\t")
            if len(f) < 9: continue
            a = parse_attrs(f[8])
            if f[2] == "mRNA":
                n_mrna += 1
                a["ID"] = idmap.get(a.get("ID", ""), a.get("ID", ""))
                if "Name" in a: a["Name"] = a["ID"]
            if "Parent" in a:
                a["Parent"] = ",".join(idmap.get(p, p) for p in a["Parent"].split(","))
            f[8] = fmt_attrs(a)
            fo.write("\t".join(f) + "\n")
    # FASTA rewrite
    for src, dst in ((args.cds, "cds"), (args.pep, "pep")):
        n = 0
        with open(src, encoding="utf-8", errors="replace") as fi, open(out/f"{args.tag}.{dst}", "w", encoding="utf-8") as fo:
            skip = False
            for line in fi:
                if line.startswith(">"):
                    mid = line[1:].split()[0]; n += 1
                    new = idmap.get(mid, mid)
                    skip = not DIGIT.search(new)
                    if not skip: fo.write(">" + new + "\n")
                elif not skip:
                    s = line.rstrip("\n")
                    if dst == "pep": s = s.replace("*", "").replace(".", "")
                    fo.write(s + "\n")
        print(f"{dst}: {n} records")
    print(f"mRNA: {n_mrna}, renamed: {len(idmap)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
