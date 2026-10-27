#!/usr/bin/env python3
"""Build the committed wheatPTM dataset snapshot (app/static/wheatPTM/stats.json).

The ``ptm`` database holds ~44M site rows, so the landing-page overview must not
run ``COUNT(*)``/``GROUP BY`` per request. This script performs the heavy
aggregation once and writes a small JSON snapshot that the static page fetches
directly at ``/wheatPTM/stats.json``.

Run it on a host that can reach the ``ptm`` MySQL database (in production: the
web node itself, where ``.env`` lives):

    /home/fei/mambaforge/envs/zjw/bin/python scripts/build_ptm_stats.py
    # optional: --out /tmp/stats.json --examples 6

Refresh this snapshot whenever the PTM tables are re-imported, then commit the
regenerated ``app/static/wheatPTM/stats.json``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.api.routers.ptm import NON_PTM, PTM_TABLES  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.mysql import mysql_connection  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "app" / "static" / "wheatPTM" / "stats.json"

#: Confidence classes sorted strongest -> weakest; "Non-PTM" is the negative class.
CONFIDENCE_ORDER = ["Extremely high", "High", "Medium", "Low", NON_PTM]

#: Example-protein sampling: candidate pool size and a sane site-count window.
EXAMPLE_SAMPLE_SIZE = 600
EXAMPLE_MIN_SITES = 40
EXAMPLE_MAX_SITES = 400


def _confidence_counts(cur, table: str) -> tuple[int, dict[str, int]]:
    """One GROUP BY per table; returns (row count, confidence -> count)."""
    cur.execute(
        f"SELECT `Confidence` AS c, COUNT(*) AS n FROM `{table}` GROUP BY `Confidence`"
    )
    counts: dict[str, int] = {}
    total = 0
    for row in cur.fetchall():
        label = (row["c"] or "Unknown").strip()
        n = int(row["n"] or 0)
        counts[label] = counts.get(label, 0) + n
        total += n
    return total, counts


def _protein_count(cur) -> int:
    cur.execute("SELECT COUNT(*) AS n FROM `protein_length`")
    row = cur.fetchone()
    return int(row["n"] or 0) if row else 0


def _site_count_for(cur, protein: str) -> int:
    """Total predicted sites for one protein across all PTM tables (indexed lookups)."""
    subqueries = " + ".join(
        f"(SELECT COUNT(*) FROM `{table}` WHERE `Protein` = %s)"
        for table, _ in PTM_TABLES
    )
    cur.execute(f"SELECT ({subqueries}) AS n", (protein,) * len(PTM_TABLES))
    row = cur.fetchone()
    return int(row["n"] or 0) if row else 0


def _chromosome(protein: str) -> str:
    """Homeologous group of an IWGSC protein ID (e.g. TraesCS6B02G137300.1 -> 6B)."""
    match = re.match(r"TraesCS([1-7][ABD])", protein or "")
    return match.group(1) if match else "?"


def _examples(cur, limit: int) -> list[dict]:
    """Pick a handful of ordinary wheat proteins with a moderate number of sites.

    Sampling ``protein_length`` (instead of taking the most-modified proteins) keeps
    the examples representative; the site window avoids both near-empty and
    pathological giant proteins. At most one example per homeologous group.
    """
    cur.execute(
        "SELECT `Protein` AS p FROM `protein_length` "
        "WHERE `Protein` LIKE 'TraesCS%' ORDER BY RAND() LIMIT %s",
        (EXAMPLE_SAMPLE_SIZE,),
    )
    candidates = [row["p"] for row in cur.fetchall() if row["p"]]
    scored: list[dict] = []
    for protein in candidates:
        sites = _site_count_for(cur, protein)
        if EXAMPLE_MIN_SITES <= sites <= EXAMPLE_MAX_SITES:
            scored.append({"protein": protein, "sites": sites, "chromosome": _chromosome(protein)})
    scored.sort(key=lambda item: item["sites"], reverse=True)

    examples: list[dict] = []
    used: set[str] = set()
    for item in scored:
        if item["chromosome"] in used:
            continue
        used.add(item["chromosome"])
        examples.append({"protein": item["protein"], "sites": item["sites"]})
        if len(examples) >= limit:
            return examples
    for item in scored:  # fewer chromosomes than requested: fill up
        if all(item["protein"] != e["protein"] for e in examples):
            examples.append({"protein": item["protein"], "sites": item["sites"]})
            if len(examples) >= limit:
                break
    return examples


def build(out_path: Path, example_count: int = 6) -> dict:
    types: list[dict] = []
    total_sites = 0
    total_ptm_calls = 0
    confidence_totals: dict[str, int] = {}

    with mysql_connection(settings.DB_PTM) as conn:
        with conn.cursor() as cur:
            proteins_indexed = _protein_count(cur)
            for table, label in PTM_TABLES:
                print(f"[stats] {table} ...", file=sys.stderr, flush=True)
                sites, counts = _confidence_counts(cur, table)
                non_ptm = counts.get(NON_PTM, 0)
                ptm_calls = sites - non_ptm
                total_sites += sites
                total_ptm_calls += ptm_calls
                for key, n in counts.items():
                    confidence_totals[key] = confidence_totals.get(key, 0) + n
                types.append({
                    "table": table,
                    "label": label,
                    "sites": sites,
                    "ptm_calls": ptm_calls,
                    "non_ptm": non_ptm,
                })
            print("[stats] examples ...", file=sys.stderr, flush=True)
            examples = _examples(cur, example_count)

    confidence = {
        key: confidence_totals[key]
        for key in CONFIDENCE_ORDER
        if key in confidence_totals
    }
    for key in sorted(set(confidence_totals) - set(confidence)):
        confidence[key] = confidence_totals[key]

    snapshot = {
        "generated_at": date.today().isoformat(),
        "source": "PlantPTM predictions imported into the ptm MySQL database",
        "proteins_indexed": proteins_indexed,
        "totals": {
            "sites": total_sites,
            "ptm_calls": total_ptm_calls,
            "non_ptm": total_sites - total_ptm_calls,
        },
        "confidence_counts": confidence,
        "types": types,
        "examples": examples,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[stats] wrote {out_path}", file=sys.stderr)
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output JSON path")
    parser.add_argument("--examples", type=int, default=6, help="number of example proteins")
    args = parser.parse_args()
    snapshot = build(args.out, args.examples)
    print(json.dumps({k: snapshot[k] for k in ("proteins_indexed", "totals")}, indent=2))


if __name__ == "__main__":
    main()
