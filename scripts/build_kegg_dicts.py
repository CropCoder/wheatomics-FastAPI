#!/usr/bin/env python3
"""Build bundled KEGG annotation dictionaries for the GO/KEGG enrichment module.

Reads clusterProfiler reference outputs (outside the repo) and emits:
  app/services/data/kegg_ko_defs.json         {KO_id: definition}
  app/services/data/kegg_pathway_names.json   {pathway_id: short_name}

Sources:
  kegg_ko_cache.json      ko:Kxxxxx -> definition (clean, 5128 entries)
  cp_KEGG_ko.tsv          ko:Kxxxxx + Description (clean, enrichment run)
  cp_KEGG_Pathway.tsv     ko/map pathway ids + Description (ko rows carry the
                          full KEGG entry, so the short name is cut at the
                          first KO/module/compound token)
"""
import csv
import json
import re
from pathlib import Path

SRC = Path("/Users/mashengwei/Desktop/markdown/陈甜甜/小麦泛基因组序列-0601/enrichment_top1000_union/out_clusterProfiler")
OUT = Path(__file__).resolve().parent.parent / "app" / "services" / "data"

# --- 1. KO definitions -------------------------------------------------------
ko_defs = {}
try:
    cache = json.loads((SRC / "kegg_ko_cache.json").read_text(encoding="utf-8"))
    for k, v in cache.items():
        ko = str(k).replace("ko:", "").strip()
        if not ko or not v:
            continue
        v = str(v).strip()
        if v in (ko, "ko:" + ko):      # placeholder entry (definition not fetched)
            continue
        ko_defs[ko] = v
except FileNotFoundError as e:
    print("WARN: missing", e)

try:
    with open(SRC / "cp_KEGG_ko.tsv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            ko = (row.get("ID") or "").replace("ko:", "").strip()
            desc = (row.get("Description") or "").strip()
            if ko and desc:
                ko_defs.setdefault(ko, desc)
except FileNotFoundError as e:
    print("WARN: missing", e)

# --- 2. Pathway short names --------------------------------------------------
pw_names = {}
try:
    with open(SRC / "cp_KEGG_Pathway.tsv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            pid = (row.get("ID") or "").replace("path:", "").strip()
            desc = (row.get("Description") or "").strip()
            if not pid or not desc:
                continue
            # ko: rows embed the whole KEGG entry; cut at first KO/module/compound
            clean = re.split(r"\s+[KMC]\d{5}\b", desc)[0].strip()
            if clean:
                pw_names.setdefault(pid, clean)
except FileNotFoundError as e:
    print("WARN: missing", e)

# Final cleanup: drop any leftover placeholder values (value == key).
for d in (ko_defs, pw_names):
    for k in [k for k, v in d.items() if v in (k, "ko:" + k)]:
        del d[k]

OUT.mkdir(parents=True, exist_ok=True)
for fname, data in (("kegg_ko_defs.json", ko_defs), ("kegg_pathway_names.json", pw_names)):
    (OUT / fname).write_text(
        json.dumps(dict(sorted(data.items())), ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
print(f"kegg_ko_defs.json:        {len(ko_defs)} entries -> {OUT / 'kegg_ko_defs.json'}")
print(f"kegg_pathway_names.json:  {len(pw_names)} entries -> {OUT / 'kegg_pathway_names.json'}")
