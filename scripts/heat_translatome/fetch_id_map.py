#!/usr/bin/env python3
"""Fetch the full 03G -> 02G gene-ID cross-reference from the public GeneHub API.

The translatome source table uses IWGSC RefSeq v2.1 (03G) IDs, while the
WheatOmics expression/browser modules are keyed by the older 02G IDs.  GeneHub
exposes a per-interval annotation table (``Genefunc_CS_IWGSC03G_table``) whose
``gene_primary``/``gene_secondary`` columns are exactly this mapping; the API
caps one request at 30 Mb, so chromosomes are walked in 30 Mb chunks.

The generated TSV is consumed by ``build_data.py`` (and can also seed the MySQL
``GeneID_02G`` columns if the dataset is later moved into ``gene_expression``).

Example
-------
python3 scripts/heat_translatome/fetch_id_map.py \
  --out /tmp/gene_map_03g_02g.tsv --genes /tmp/genes_03g.txt
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DEFAULT = "https://wheatomics.sdau.edu.cn"
TABLE = "Genefunc_CS_IWGSC03G_table"
STEP = 30_000_000
CHROMS = [f"chr{n}{s}" for n in range(1, 8) for s in ("A", "B", "D")]


def fetch_interval(base: str, chrom: str, start: int, end: int, attempts: int = 3) -> tuple[list[dict], str | None]:
    query = urllib.parse.urlencode({"ID": f"{chrom}:{start}..{end}", "table": TABLE})
    url = f"{base}/api/genes/functions/interval?{query}"
    last_error: str | None = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "wheatomics-heat-translatome-build/1.0"})
            with urllib.request.urlopen(req, timeout=90) as resp:
                payload = json.loads(resp.read().decode())
            data = payload.get("data") or {}
            return (data.get("records") or []), None
        except Exception as exc:  # noqa: BLE001 - network retries
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(1.5 * (attempt + 1))
    return [], last_error


def collect(base: str, workers: int, max_chunks: int) -> tuple[dict[str, dict], list[str]]:
    rows: dict[str, dict] = {}
    errors: list[str] = []

    def add(records: list[dict]) -> None:
        for rec in records:
            g3 = (rec.get("gene_primary") or "").strip()
            if not g3:
                continue
            g2 = (rec.get("gene_secondary") or rec.get("chinese_spring_02g") or "").strip()
            rows[g3] = {
                "gene03g": g3,
                "gene02g": g2,
                "chrom": (rec.get("chromosome") or "").strip(),
                "start_mb": rec.get("start_mb"),
                "end_mb": rec.get("end_mb"),
                "strand": (rec.get("strand") or "").strip(),
            }

    for chrom in CHROMS:
        consecutive_empty = 0
        for i in range(max_chunks):
            start, end = i * STEP, (i + 1) * STEP
            records, error = fetch_interval(base, chrom, start, end)
            if error:
                errors.append(f"{chrom}:{start}..{end} {error}")
            add(records)
            consecutive_empty = 0 if records else consecutive_empty + 1
            if consecutive_empty >= 2 and i >= 1:
                break

    # chrUn is a single artificial sequence; walk until five empty chunks.
    consecutive_empty = 0
    for i in range(max_chunks):
        records, error = fetch_interval(base, "chrUn", i * STEP, (i + 1) * STEP)
        if error:
            errors.append(f"chrUn:{i * STEP} {error}")
        add(records)
        consecutive_empty = 0 if records else consecutive_empty + 1
        if consecutive_empty >= 5 and i >= 2:
            break
    return rows, errors


def fill_missing_from_detail(base: str, rows: dict[str, dict], genes: list[str]) -> list[str]:
    """Fallback for genes absent from the interval table: query GeneHub per gene."""
    missing = [g for g in genes if g not in rows]
    if not missing:
        return []

    def one(g3: str) -> tuple[str, dict | None]:
        url = f"{base}/api/genes/detail/{urllib.parse.quote(g3)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "wheatomics-heat-translatome-build/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode())
            data = payload.get("data") or {}
            ids = data.get("gene_ids") or []
            g2 = next((x for x in ids if "02G" in str(x)), "")
            if g2:
                return g3, {"gene03g": g3, "gene02g": g2, "chrom": data.get("chromosome") or "",
                            "start_mb": None, "end_mb": None, "strand": data.get("strand") or ""}
        except Exception:  # noqa: BLE001
            pass
        return g3, None

    with ThreadPoolExecutor(max_workers=4) as pool:
        for g3, record in pool.map(one, missing):
            if record:
                rows[g3] = record
    return [g for g in missing if g not in rows]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="Output TSV path")
    ap.add_argument("--base", default=BASE_DEFAULT, help="WheatOmics base URL")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-chunks", type=int, default=40)
    ap.add_argument("--genes", help="Optional file with one 03G ID per line; missing IDs are retried via /api/genes/detail")
    args = ap.parse_args()

    rows, errors = collect(args.base, args.workers, args.max_chunks)
    print(f"interval mapping: {len(rows)} genes, {len(errors)} request errors", file=sys.stderr)

    if args.genes:
        genes = [line.strip() for line in open(args.genes, encoding="utf-8") if line.strip()]
        still_missing = fill_missing_from_detail(args.base, rows, genes)
        print(f"after /genes/detail fallback: {len(rows)} genes, still missing {len(still_missing)}", file=sys.stderr)
        for g3 in still_missing[:50]:
            print(f"UNMAPPED {g3}", file=sys.stderr)

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(["gene03g", "gene02g", "chrom", "start_mb", "end_mb", "strand"])
        for g3 in sorted(rows):
            r = rows[g3]
            writer.writerow([r["gene03g"], r["gene02g"], r["chrom"], r["start_mb"], r["end_mb"], r["strand"]])
    print(f"wrote {args.out} ({len(rows)} genes)", file=sys.stderr)


if __name__ == "__main__":
    main()
