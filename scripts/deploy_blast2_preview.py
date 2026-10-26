#!/usr/bin/env python3
"""Deploy the BLAST+ SPA to the Apache docroot (preview URL /blast/blast2.html).

The BLAST pages live under the Apache docroot (/var/www/html/blast), outside any
Apache ProxyPass prefix, so the repo source is published by copying it there
(with a timestamped backup) instead of adding a new reverse-proxy rule.

Run on the production web node:

    python3 scripts/deploy_blast2_preview.py           # copy repo -> docroot
    python3 scripts/deploy_blast2_preview.py --check   # compare, exit 1 on drift

The canonical /blast/blast.html (ViroBlast) and /blast/blastresult2.php are left
untouched; switching them to the SPA is a separate product decision.
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
DEFAULT_DEST = Path(os.environ.get("WHEATOMICS_BLAST2_DEST", "/var/www/html/blast/blast2.html"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="only compare repo and docroot copies")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help=f"destination (default: {DEFAULT_DEST})")
    args = parser.parse_args()

    if not SRC.is_file():
        print(f"[ERR] source missing: {SRC}")
        return 1

    if args.check:
        if not args.dest.is_file():
            print(f"[MISMATCH] {args.dest} does not exist (repo {digest(SRC)})")
            return 1
        same = digest(SRC) == digest(args.dest)
        print(f"[{'OK' if same else 'MISMATCH'}] {args.dest}  repo={digest(SRC)} live={digest(args.dest)}")
        return 0 if same else 1

    if not args.dest.parent.is_dir():
        print(f"[ERR] destination directory missing: {args.dest.parent} (run on the web node)")
        return 1

    backup = None
    if args.dest.is_file():
        backup = args.dest.with_name(args.dest.name + ".bak-" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        shutil.copy2(args.dest, backup)
    shutil.copy2(SRC, args.dest)
    print(f"[done] {SRC} -> {args.dest}")
    print(f"       {args.dest.stat().st_size} bytes, sha256 {digest(args.dest)}")
    if backup:
        print(f"       backup: {backup}")
    print("       preview: https://wheatomics.sdau.edu.cn/blast/blast2.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
