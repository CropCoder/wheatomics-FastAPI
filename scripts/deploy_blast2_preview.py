#!/usr/bin/env python3
"""Publish the BLAST+ SPA to the Apache docroot.

Canonical URL:  /blast/blast.html   (replaces the legacy ViroBlast form page)
Alias URL:      /blast/blast2.html  (same file, kept for the preview link and
                                     for any bookmarks created while testing)

The BLAST pages live under the Apache docroot (/var/www/html/blast), outside any
Apache ProxyPass prefix, so the repo source is published by copying it there
(with a timestamped backup) instead of adding a reverse-proxy rule. No service
restart is needed. The legacy result viewer blastresult2.php is intentionally
left untouched so old result links keep working; only the form page is replaced.

Source of truth: app/static/blast2/index.html

Run on the production web node:

    python3 scripts/deploy_blast2_preview.py              # publish both targets
    python3 scripts/deploy_blast2_preview.py --check      # compare, exit 1 on drift
    python3 scripts/deploy_blast2_preview.py --canonical-only
    python3 scripts/deploy_blast2_preview.py --alias-only

Rollback (the previous page is saved next to the target, timestamped):

    cp /var/www/html/blast/blast.html.bak-<timestamp> /var/www/html/blast/blast.html
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "app" / "static" / "blast2" / "index.html"
DEFAULT_DIR = Path(os.environ.get("WHEATOMICS_BLAST_DIR", "/var/www/html/blast"))

TARGET_CANONICAL = "blast.html"
TARGET_ALIAS = "blast2.html"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def publish(dest: Path, check: bool) -> bool:
    """Copy the SPA to *dest* unless it is already identical. Returns success."""
    src_digest = digest(SRC)
    if not dest.is_file():
        if check:
            print(f"[MISMATCH] {dest} missing (repo {src_digest})")
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SRC, dest)
        print(f"[created] {dest}  ({dest.stat().st_size} bytes, sha256 {digest(dest)})")
        return True
    if digest(dest) == src_digest:
        print(f"[ok] {dest} already up to date (sha256 {src_digest})")
        return True
    if check:
        print(f"[MISMATCH] {dest}  repo={src_digest} live={digest(dest)}")
        return False
    backup = dest.with_name(dest.name + ".bak-" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(dest, backup)
    shutil.copy2(SRC, dest)
    print(f"[updated] {dest}  ({dest.stat().st_size} bytes, sha256 {digest(dest)})")
    print(f"          backup: {backup}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="only compare repo and docroot copies")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help=f"docroot directory (default: {DEFAULT_DIR})")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--canonical-only", action="store_true", help="only publish /blast/blast.html")
    group.add_argument("--alias-only", action="store_true", help="only publish /blast/blast2.html")
    args = parser.parse_args()

    if not SRC.is_file():
        print(f"[ERR] source missing: {SRC}")
        return 1
    if not args.dir.is_dir():
        print(f"[ERR] docroot directory missing: {args.dir} (run this on the web node)")
        return 1

    targets = []
    if not args.alias_only:
        targets.append(args.dir / TARGET_CANONICAL)
    if not args.canonical_only:
        targets.append(args.dir / TARGET_ALIAS)

    ok = all([publish(target, args.check) for target in targets])
    if ok:
        print("")
        print("Canonical: https://wheatomics.sdau.edu.cn/blast/blast.html")
        print("Alias:     https://wheatomics.sdau.edu.cn/blast/blast2.html")
        print("Legacy result viewer left in place: /blast/blastresult2.php")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
