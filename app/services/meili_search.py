"""Meilisearch-backed full-text search for the Triticeae papers module.

Why
---
The MySQL ``LIKE '%term%'`` search (with the singular/synonym expansion in
``app/services/literature_query.py``) cannot handle typos: ``strip rust``
matches nothing.  Meilisearch is used as the *text-matching* layer:

  1. the API asks Meilisearch for the ordered PMID list matching the user's
     text terms (typo tolerance, prefix search, synonyms can be configured in
     the index);
  2. the existing MySQL query then applies every structured filter (date,
     impact factor, quartile, annotation flags…), paginates and counts exactly.

MySQL therefore remains the single source of truth; if Meilisearch is down the
API silently falls back to the previous LIKE-based path.

Configuration (env vars, all optional):
  MEILI_URL      default http://127.0.0.1:7700
  MEILI_INDEX    default papers
  MEILI_TIMEOUT  default 2.5 s
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from app.services.literature_query import expand_text_variants

MEILI_URL = os.environ.get("MEILI_URL", "http://127.0.0.1:7700").rstrip("/")
MEILI_INDEX = os.environ.get("MEILI_INDEX", "papers")
MEILI_TIMEOUT = float(os.environ.get("MEILI_TIMEOUT", "2.5"))
MEILI_API_KEY = os.environ.get("MEILI_API_KEY") or os.environ.get("MEILI_MASTER_KEY") or ""

# Cap on how many PMIDs a single text query may return. The corpus is ~17k
# papers, so this is effectively "all"; if it is ever hit the caller falls back
# to MySQL so the reported total stays exact.
MEILI_MAX_RESULTS = 20000

# Fields the index marks as searchable (must mirror scripts/papers_meili_sync.py).
SEARCH_ATTRIBUTES = [
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

# Health-check cache: healthy for 60 s, unhealthy for 10 s (so a Meilisearch
# restart is picked up quickly without restarting the API workers).
_STATE = {"checked_at": 0.0, "ok": False}


def _request(method: str, path: str, payload: dict | None = None, timeout: float | None = None) -> dict:
    data = None
    headers = {"Accept": "application/json"}
    if MEILI_API_KEY:
        headers["Authorization"] = "Bearer " + MEILI_API_KEY
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(MEILI_URL + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout or MEILI_TIMEOUT) as response:
        body = response.read()
    return json.loads(body) if body else {}


def enabled() -> bool:
    """True when Meilisearch answers /health (short TTL cache)."""
    now = time.time()
    ttl = 60.0 if _STATE["ok"] else 10.0
    if now - _STATE["checked_at"] < ttl:
        return _STATE["ok"]
    ok = False
    try:
        health = _request("GET", "/health", timeout=1.5)
        ok = str(health.get("status", "")).lower() == "available"
    except Exception:
        ok = False
    _STATE.update(checked_at=now, ok=ok)
    return ok


def _search_one(term: str) -> list[str] | None:
    """One Meilisearch query; returns PMIDs in ranking order (None on error)."""
    ordered: list[str] = []
    seen: set[str] = set()
    offset = 0
    page = 1000
    while len(ordered) < MEILI_MAX_RESULTS:
        payload = {
            "q": term,
            "limit": page,
            "offset": offset,
            "attributesToSearchOn": SEARCH_ATTRIBUTES,
            "matchingStrategy": "all",
            "attributesToRetrieve": ["pmid"],
        }
        try:
            result = _request("POST", f"/indexes/{MEILI_INDEX}/search", payload)
        except Exception:
            _STATE.update(checked_at=0.0, ok=False)  # re-check health next call
            return None
        hits = result.get("hits") or []
        for hit in hits:
            pmid = str(hit.get("pmid") or "")
            if pmid and pmid not in seen:
                seen.add(pmid)
                ordered.append(pmid)
        if len(hits) < page:
            break
        offset += page
    return ordered


def search_pmids(terms: list[str]) -> list[str] | None:
    """Ordered PMIDs matching ALL user terms (union of each term's synonyms).

    Returns None when Meilisearch is unavailable or the result set is too large,
    which tells the caller to use the MySQL LIKE fallback instead.
    """
    if not terms or not enabled():
        return None

    ranked: list[str] | None = None
    for term in terms:
        union: list[str] = []
        seen: set[str] = set()
        for variant in expand_text_variants(term):
            matched = _search_one(variant)
            if matched is None:
                return None
            for pmid in matched:
                if pmid not in seen:
                    seen.add(pmid)
                    union.append(pmid)
        if len(union) >= MEILI_MAX_RESULTS:
            return None  # too broad to enumerate exactly -> MySQL fallback

        if ranked is None:
            ranked = union
        else:
            allowed = set(union)
            ranked = [pmid for pmid in ranked if pmid in allowed]
        if not ranked:
            return []
    return ranked
