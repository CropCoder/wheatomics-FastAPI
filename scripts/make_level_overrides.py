#!/usr/bin/env python3
"""Generate blast_db_levels.json from the previous content audit.

Reads /tmp/level_audit.json (one row per suspicious genome DB with sequence
counts from the earlier run), re-lists accessions with a corrected prefix
regex, and writes a JSON override map:

    { "<db base>": {"assembly_level": "Chromosome"|"Scaffold", "chromosome_count": N} }

Only DBs with >= 6 sequences > 10 Mb are re-checked; chromosome-level means at
least 6 accessions named Chr<number><subgenome> and at least 6 large sequences.
"""
import json
import re
import subprocess
from pathlib import Path

DB_DIR = Path("/var/www/html/getfasta/blastdb")
BLASTDBCMD = "/var/www/html/blast/blast+/bin/blastdbcmd"
CHR_RE = re.compile(r"^(?:chr|chromosome)[\s_.-]?(\d{1,2}[A-Za-z]{0,4})", re.I)
rows = json.loads(Path("/tmp/level_audit.json").read_text())
overrides = {}
for row in rows:
    if row.get("error"):
        continue
    if row.get("seq_gt10Mb", 0) < 6:
        continue
    db = row["db"]
    try:
        proc = subprocess.run([BLASTDBCMD, "-db", str(DB_DIR / db), "-entry", "all",
                               "-outfmt", "%a\t%l"], capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        continue
    if proc.returncode != 0:
        continue
    total = 0
    chr_count = 0
    large = 0
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        total += 1
        acc, length = parts[0], parts[1]
        m = CHR_RE.match(acc)
        if m and not m.group(1).lower().startswith("un"):
            chr_count += 1
        try:
            if int(length) >= 10_000_000:
                large += 1
        except ValueError:
            pass
    if chr_count >= 6 and large >= 6:
        level, chrom_count = "Chromosome", chr_count
    elif total > 100:
        level, chrom_count = "Scaffold", None
    else:
        continue
    for key in {row["base"], db}:
        overrides[key] = {"assembly_level": level, "chromosome_count": chrom_count}
    print(json.dumps({"db": db, "base": row["base"], "sequences": total,
                      "chr_count": chr_count, "large": large, "level": level,
                      "chromosome_count": chrom_count}, ensure_ascii=False), flush=True)

out = Path("/tmp/blast_db_levels.json")
out.write_text(json.dumps(overrides, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
print("WROTE", out, len(overrides))
