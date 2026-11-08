#!/usr/bin/env python3
"""Build/refresh the Meilisearch index used by the Triticeae papers search.

The index is a denormalised copy of the searchable paper fields (papers +
functional-gene annotation + journal metrics). MySQL stays the source of truth:
the API asks Meilisearch only for the ranked PMID list, then applies the
structured filters/pagination in MySQL.

Usage (on the production node, repo root):
    # full rebuild (default; ~17k docs, a few seconds)
    python3 scripts/papers_meili_sync.py --rebuild

    # incremental: upsert all documents without dropping the index
    python3 scripts/papers_meili_sync.py

Environment:
    MEILI_URL    default http://127.0.0.1:7700
    MEILI_INDEX  default papers
    DB_HOST / DB_USER / DB_PASSWORD / DB_TRITICEAE (or the repo .env file)

Called at the end of run_weekly_v2_pipeline.sh (Step 6c) so new papers are
searchable right after the harvest. A Meilisearch outage never fails the
pipeline (the caller appends `|| true`).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pymysql

REPO = Path(__file__).resolve().parents[1]

SEARCHABLE = [
    "title",
    "abstract",
    "authors",
    "journal",
    "journal_canonical",
    "pubmed_keywords",
    "ai_tags",
    "function_gene_tags",
    "gene_names",
]
FILTERABLE = [
    "pmid",
    "journal",
    "journal_canonical",
    "pub_year",
    "is_functional_gene",
    "review_status",
    "source_method",
    "impact_factor",
    "jcr_quartile",
    "created_at",
]
SORTABLE = ["created_at", "pub_date", "pub_year", "journal", "impact_factor"]

BATCH = 5000


def load_db_config() -> dict:
    cfg = {
        "host": os.environ.get("DB_HOST", "localhost"),
        "user": os.environ.get("DB_USER", "wheatomics_user"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "database": os.environ.get("DB_TRITICEAE", "Triticeae_Research_filter"),
    }
    env_path = REPO / ".env"
    if not cfg["password"] and env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^(DB_[A-Z_]+)\s*=\s*(.*)$", line)
            if not m:
                continue
            key, val = m.group(1), m.group(2).strip().strip('"').strip("'")
            if not val:
                continue
            if key == "DB_HOST":
                cfg["host"] = val
            elif key == "DB_USER":
                cfg["user"] = val
            elif key == "DB_PASSWORD":
                cfg["password"] = val
            elif key == "DB_TRITICEAE":
                cfg["database"] = val
    return cfg


class Meili:
    def __init__(self, base_url: str, api_key: str = ""):
        self.base = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("MEILI_API_KEY") or os.environ.get("MEILI_MASTER_KEY") or ""

    def _call(self, method: str, path: str, payload=None, timeout: float = 30.0):
        data = None
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
            return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {"__status": 404}
            raise

    def wait(self, task_uid, label: str, timeout: float = 600.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            task = self._call("GET", f"/tasks/{task_uid}")
            status = str(task.get("status", "")).lower()
            if status == "succeeded":
                return task
            if status in ("failed", "canceled"):
                raise RuntimeError(f"Meilisearch task {label} {status}: {task.get('error')}")
            time.sleep(0.4)
        raise TimeoutError(f"Meilisearch task {label} timed out")

    def submit(self, method: str, path: str, payload=None) -> dict:
        result = self._call(method, path, payload)
        if result.get("__status") == 404:
            return result
        uid = result.get("taskUid")
        if uid is None:
            return result
        return self.wait(uid, path)


def build_documents(conn) -> list[dict]:
    sql = """
        SELECT p.pmid, p.title, p.abstract, p.authors, p.journal, p.pub_date, p.created_at,
               p.pubmed_keywords, p.ai_tags, p.function_gene_tags, p.functional_gene_tags,
               p.doi, p.link, p.keywords_source,
               f.is_functional_gene, f.review_status, f.source_method, f.confidence,
               f.gene_name, f.trait_label, f.new_tags,
               m.jif AS impact_factor, m.quartile AS jcr_quartile, m.jcr_year AS metric_year,
               m.journal_canonical
        FROM papers p
        LEFT JOIN functional_gene_annotations f ON f.pubmedid = p.pmid
        LEFT JOIN journal_alias ja ON ja.journal_db = p.journal
        LEFT JOIN journal_metrics m ON m.issn = ja.issn
    """
    docs = []
    with conn.cursor() as cur:
        cur.execute(sql)
        for row in cur.fetchall():
            pub_date = str(row.get("pub_date") or "")
            year_match = re.match(r"(\d{4})", pub_date)
            gene_bits = []
            for value in (row.get("gene_name"), row.get("function_gene_tags"), row.get("functional_gene_tags")):
                if not value:
                    continue
                text = str(value).strip()
                if text.startswith("["):
                    try:
                        text = "; ".join(str(x) for x in json.loads(text))
                    except Exception:
                        pass
                gene_bits.append(text)
            created = row.get("created_at")
            docs.append({
                "pmid": str(row.get("pmid") or ""),
                "title": row.get("title") or "",
                "abstract": row.get("abstract") or "",
                "authors": row.get("authors") or "",
                "journal": (row.get("journal") or "").strip(),
                "journal_canonical": row.get("journal_canonical") or "",
                "pub_date": pub_date,
                "pub_year": int(year_match.group(1)) if year_match else None,
                "created_at": created.strftime("%Y-%m-%d %H:%M:%S") if created else "",
                "pubmed_keywords": row.get("pubmed_keywords") or "",
                "ai_tags": row.get("ai_tags") or "",
                "function_gene_tags": row.get("function_gene_tags") or "",
                "gene_names": " ; ".join(gene_bits),
                "is_functional_gene": row.get("is_functional_gene"),
                "review_status": row.get("review_status") or "",
                "source_method": row.get("source_method") or "",
                "confidence": float(row["confidence"]) if row.get("confidence") is not None else None,
                "impact_factor": float(row["impact_factor"]) if row.get("impact_factor") is not None else None,
                "jcr_quartile": row.get("jcr_quartile") or "",
                "metric_year": row.get("metric_year"),
                "doi": row.get("doi") or "",
                "link": row.get("link") or "",
                "keywords_source": row.get("keywords_source") or "",
            })
    return docs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--meili-url", default=os.environ.get("MEILI_URL", "http://127.0.0.1:7700"))
    ap.add_argument("--index", default=os.environ.get("MEILI_INDEX", "papers"))
    ap.add_argument("--rebuild", action="store_true", help="drop and recreate the index before uploading")
    ap.add_argument("--batch", type=int, default=BATCH)
    args = ap.parse_args()

    meili = Meili(args.meili_url, api_key=os.environ.get("MEILI_API_KEY", ""))
    health = meili._call("GET", "/health", timeout=5)
    print("meilisearch health:", health)

    cfg = load_db_config()
    conn = pymysql.connect(host=cfg["host"], user=cfg["user"], password=cfg["password"],
                           database=cfg["database"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    docs = build_documents(conn)
    conn.close()
    print("documents:", len(docs))

    if args.rebuild:
        try:
            meili.submit("DELETE", f"/indexes/{args.index}")
            print("existing index removed")
        except RuntimeError as exc:
            if "index_not_found" in str(exc):
                print("no existing index to remove")
            else:
                raise

    meili.submit("POST", "/indexes", {"uid": args.index, "primaryKey": "pmid"})
    meili.submit("PATCH", f"/indexes/{args.index}/settings", {
        "searchableAttributes": SEARCHABLE,
        "filterableAttributes": FILTERABLE,
        "sortableAttributes": SORTABLE,
        # oneTypo=3 lets short morphological variants match (rust <-> rusts,
        # gene <-> genes); twoTypos=6 keeps longer-word typo tolerance sane.
        "typoTolerance": {
            "enabled": True,
            "minWordSizeForTypos": {"oneTypo": 3, "twoTypos": 6},
        },
        "pagination": {"maxTotalHits": 20000},
    })
    print("index + settings ready")

    for start in range(0, len(docs), args.batch):
        chunk = docs[start:start + args.batch]
        meili.submit("POST", f"/indexes/{args.index}/documents?primaryKey=pmid", chunk)
        print("uploaded %d/%d" % (min(start + args.batch, len(docs)), len(docs)))

    stats = meili._call("GET", f"/indexes/{args.index}/stats")
    print("index stats:", {k: stats.get(k) for k in ("numberOfDocuments", "isIndexing")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
