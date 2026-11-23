#!/usr/bin/env python3
"""Merge-safe WheatOmics news updater.

The site reads ``/V2.0/news.json`` at runtime (help/news.html + index.html fetch
it with a cache-buster), so adding an entry needs no page rebuild.  Multiple
agents/curators edit the same file, so this tool:

* takes an exclusive ``flock`` on ``<news.json>.lock``;
* loads the existing list, drops any entry with the same ``title`` (idempotent);
* inserts the new entry and sorts by ``date`` descending (stable);
* keeps a timestamped backup and writes atomically (tmp + os.replace).

Usage::

    python3 scripts/add_news.py --json /var/www/html/V2.0/news.json \
        --date 2026-11-23 \
        --title "..." --summary "..." \
        --url https://doi.org/... --journal "Scientific Data"

Use ``--dry-run`` to preview the resulting head without writing.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path


def load(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise SystemExit(f"{path}: expected a JSON array")
    return data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Insert one entry into V2.0/news.json safely.")
    ap.add_argument("--json", default="/var/www/html/V2.0/news.json")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--title", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--url", default="")
    ap.add_argument("--journal", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    datetime.strptime(args.date, "%Y-%m-%d")  # validate

    path = Path(args.json)
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.touch(exist_ok=True)
    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not path.exists():
            raise SystemExit(f"missing {path}")
        entries = load(path)
        entry = {"date": args.date, "title": args.title, "summary": args.summary}
        if args.url:
            entry["url"] = args.url
        if args.journal:
            entry["journal"] = args.journal

        before = len(entries)
        entries = [e for e in entries if e.get("title") != args.title]
        entries.append(entry)
        entries.sort(key=lambda e: e.get("date", ""), reverse=True)

        print(f"{path}: {before} -> {len(entries)} entries")
        for e in entries[:3]:
            print(f"  {e.get('date')}  {e.get('title', '')[:70]}")
        if args.dry_run:
            return 0

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(path, path.with_name(path.name + f".bak-{stamp}"))
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".news.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(entries, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            # mkstemp creates 0600 -> Apache (www-data) must be able to read the file
            os.chmod(tmp, 0o644)
            os.replace(tmp, path)
            os.chmod(path, 0o644)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        print("written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
