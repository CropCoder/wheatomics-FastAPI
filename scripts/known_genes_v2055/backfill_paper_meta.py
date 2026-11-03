#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backfill cloned_gene_tbl.paper_authors / paper_journal from the DOI cache.

Usage (on the server, repo root):
  python3 scripts/known_genes_v2055/backfill_paper_meta.py --ref-meta app/services/data/known_gene_reference_meta.json
  python3 scripts/known_genes_v2055/backfill_paper_meta.py --ref-meta ... --commit

The DOI lists in ``paper_doi`` are ``###``-joined; authors/journal are written in
the same positional order. Each authors entry is ``; ``-joined.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pymysql
from pymysql.cursors import DictCursor

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from app.core.config import settings  # noqa: E402


def split_multi(value: object) -> list[str]:
    if value is None:
        return []
    return [part.strip() for part in str(value).split("###")]


def align(values: list[str], n: int) -> list[str]:
    out = values[:n] + [""] * max(0, n - len(values))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref-meta", default=str(REPO / "app/services/data/known_gene_reference_meta.json"))
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()
    meta = json.loads(Path(args.ref_meta).read_text(encoding="utf-8"))
    doi_map = meta.get("doi") or {}
    conn = pymysql.connect(
        host=settings.DB_HOST, port=settings.DB_PORT, user=settings.DB_USER,
        password=settings.DB_PASSWORD, database=settings.DB_CLONED_GENE,
        charset="utf8mb4", cursorclass=DictCursor, autocommit=False,
    )
    updated = skipped = 0
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT clone_id, paper_doi, paper_authors, paper_journal FROM cloned_gene_tbl ORDER BY clone_id")
            rows = cur.fetchall()
            for row in rows:
                dois = split_multi(row.get("paper_doi"))
                if not dois:
                    skipped += 1
                    continue
                authors: list[str] = []
                journals: list[str] = []
                for doi in dois:
                    rec = doi_map.get((doi or "").strip().lower()) or {}
                    authors.append("; ".join(str(a).strip() for a in (rec.get("authors") or []) if str(a).strip()))
                    journals.append(str(rec.get("journal") or "").strip())
                while authors and not authors[-1]:
                    authors.pop()
                while journals and not journals[-1]:
                    journals.pop()
                authors_text = "###".join(authors) if authors else None
                journals_text = "###".join(journals) if journals else None
                if authors_text == row.get("paper_authors") and journals_text == row.get("paper_journal"):
                    continue
                updated += 1
                if args.commit:
                    cur.execute(
                        "UPDATE cloned_gene_tbl SET paper_authors=%s, paper_journal=%s WHERE clone_id=%s",
                        (authors_text, journals_text, row["clone_id"]),
                    )
                if updated <= 10 or updated % 100 == 0:
                    print(f"clone {row['clone_id']}: DOI={dois[:2]} → authors={len(authors)} journal={journals[:2]}")
        if args.commit:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(f"{'updated' if args.commit else 'would update'}={updated}, no_doi={skipped}, total={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
