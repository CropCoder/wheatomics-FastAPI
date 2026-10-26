#!/usr/bin/env python3
"""Check whether suspicious 'scaffold'/unknown genome DBs are actually chromosome-level.

For every genome-level BLAST DB (.genome or .scaffold, not per-chromosome) whose
registry assembly_level is missing or non-chromosome, list its accessions with
blastdbcmd and count chromosome-like names (chr1A / chromosome1 / ...) and
sequences longer than 10 Mb. Prints JSON rows plus a suggested level.
"""
import json
import os
import re
import subprocess
from pathlib import Path

DB_DIR = Path("/var/www/html/getfasta/blastdb")
BLASTDBCMD = "/var/www/html/blast/blast+/bin/blastdbcmd"
CHR_RE = re.compile(r"^(?:chr|chromosome)[\s_.-]?(\d{1,2}[A-Za-z]{0,4})$", re.I)
CHROMOSOME_LEVELS = {"Chromosome", "Complete Genome", "Complete genome",
                     "Partial chromosome", "draft chromosome level"}


def registry_rows():
    env = {}
    for line in open("/var/www/FastAPI_backend_Port8000/.env"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    import pymysql
    conn = pymysql.connect(host=env.get("DB_HOST", "localhost"),
                           user=env.get("DB_USER", "wheatomics_user"),
                           password=env.get("DB_PASSWORD", ""),
                           database="wheatomics_db", charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as cur:
        cur.execute("SELECT dataset_id, blast_genome_db, assembly_level, chromosome_count FROM genome_registry")
        rows = cur.fetchall()
    conn.close()
    return rows


def base_of(name):
    if name.endswith(".genome"):
        return name[:-len(".genome")]
    if ".scaffold" in name:
        return re.sub(r"\.scaffold.*$", "", name)
    return name


def main():
    reg = registry_rows()
    by_base = {}
    for r in reg:
        for key in (r.get("blast_genome_db"), r.get("dataset_id")):
            key = (key or "").strip()
            if key:
                by_base.setdefault(key, r)
    names = set()
    for p in DB_DIR.iterdir():
        n = p.name
        for suf in (".nhr", ".nin", ".nsq", ".nal"):
            if n.endswith(suf):
                names.add(n[: -len(suf)])
    names = {n for n in names if ".genome_Chr" not in n and ".genome_chr" not in n
             and not re.search(r"[Cc]hr\d", n)}
    suspect = []
    for name in sorted(names):
        if not (name.endswith(".genome") or ".scaffold" in name):
            continue
        base = base_of(name)
        r = by_base.get(base) or by_base.get(name) or {}
        level = (r.get("assembly_level") or "").strip() or None
        if level in CHROMOSOME_LEVELS and ".scaffold" not in name:
            continue
        suspect.append((name, base, level, r.get("chromosome_count"), r.get("dataset_id")))
    out = []
    for name, base, level, chrom_count, dataset in suspect:
        try:
            proc = subprocess.run([BLASTDBCMD, "-db", str(DB_DIR / name), "-entry", "all",
                                   "-outfmt", "%a\t%l"], capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            out.append({"db": name, "base": base, "registry_level": level, "chromosome_count": chrom_count,
                        "dataset_id": dataset, "error": "timeout"})
            continue
        if proc.returncode != 0:
            out.append({"db": name, "base": base, "registry_level": level, "chromosome_count": chrom_count,
                        "dataset_id": dataset, "error": (proc.stderr or "").strip()[:160]})
            continue
        total = 0
        chr_like = 0
        large = 0
        samples = []
        for line in proc.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            total += 1
            acc, length = parts[0], parts[1]
            if CHR_RE.match(acc):
                chr_like += 1
            try:
                if int(length) >= 10_000_000:
                    large += 1
            except ValueError:
                pass
            if len(samples) < 5:
                samples.append(acc)
        actual = "Chromosome" if (chr_like >= 6 and large >= 6) else ("Scaffold/Contig" if total > 100 else "unclear")
        out.append({"db": name, "base": base, "registry_level": level, "chromosome_count": chrom_count,
                    "dataset_id": dataset, "sequences": total, "chr_like": chr_like, "seq_gt10Mb": large,
                    "suggested": actual, "samples": samples})
        print(json.dumps(out[-1], ensure_ascii=False), flush=True)
    Path("/tmp/level_audit.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("DONE", len(out))


if __name__ == "__main__":
    main()
