#!/usr/bin/env python3
"""Fail if the public API documentation contains Chinese (CJK) text.

Since 2026-10-29 the API documentation reached from the header ``Agent`` menu
(`/api/docs`, `/api/redoc`, `/api/openapi.json`) is English: the Swagger/ReDoc
description, every operation docstring and all OpenAPI-visible
``description=`` values. Runtime response messages and code comments may stay
Chinese — only docs-visible strings are checked here.

Usage::

    # 1) Live schema (no Python dependencies; run anywhere)
    python3 scripts/check_api_docs_en.py --url https://wheatomics.sdau.edu.cn/api/openapi.json

    # 2) Local schema file (e.g. downloaded or dumped earlier)
    python3 scripts/check_api_docs_en.py --file /tmp/openapi.json

    # 3) Import this app and generate the schema in-process (needs the full
    #    runtime environment: on the server use conda `zjw`)
    python3 scripts/check_api_docs_en.py

Exit codes: 0 = all docs-visible strings are English, 1 = CJK found (prints
the OpenAPI paths/fields to fix), 2 = could not produce a schema.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

# Allow `python3 scripts/check_api_docs_en.py` to import the repo's `main` module.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CJK = re.compile(r"[\u4e00-\u9fff]")
METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}


def fetch(url: str) -> dict:
    # Some site front-ends reject the default Python-urllib user agent.
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; WheatOmics-docs-check/1.0)"})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - operator-supplied URL
        return json.load(response)


def load_app_schema() -> dict:
    from main import app  # imported lazily so --url/--file need no dependencies

    return app.openapi()


def scan(schema: dict) -> list[tuple[str, str]]:
    """Return (location, snippet) for every docs-visible string containing CJK."""
    hits: list[tuple[str, str]] = []

    def walk(prefix: str, value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                walk(f"{prefix}.{key}", item)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(f"{prefix}[{index}]", item)
        elif isinstance(value, str) and CJK.search(value):
            hits.append((prefix, " ".join(value.split())[:90]))

    walk("info", schema.get("info", {}))
    for path, operations in schema.get("paths", {}).items():
        for method, operation in operations.items():
            if method in METHODS:
                walk(f"{method.upper()} {path}", operation)
    walk("components", schema.get("components", {}))
    walk("tags", schema.get("tags", []))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--url", help="fetch the OpenAPI schema from this URL")
    source.add_argument("--file", help="read the OpenAPI schema from this JSON file")
    args = parser.parse_args()

    origin = "?"
    try:
        if args.url:
            schema = fetch(args.url)
            origin = args.url
        elif args.file:
            schema = json.loads(open(args.file, encoding="utf-8").read())
            origin = args.file
        else:
            schema = load_app_schema()
            origin = "main:app (in-process)"
    except Exception as exc:  # noqa: BLE001 - CLI reports and exits
        print(f"[ERR] cannot produce OpenAPI schema ({origin}): {exc}")
        return 2

    hits = scan(schema)
    title = schema.get("info", {}).get("title", "?")
    print(f"source: {origin}")
    print(f"title:  {title}")
    print(f"docs strings with CJK: {len(hits)}")
    for location, snippet in hits[:60]:
        print(f"  [CJK] {location}: {snippet}")
    if hits:
        print("\nFAIL: translate the listed docs-visible strings to English.")
        return 1
    print("\nPASS: all docs-visible strings are English.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
