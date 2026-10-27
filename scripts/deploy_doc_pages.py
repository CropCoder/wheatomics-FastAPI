#!/usr/bin/env python3
"""Publish repo-managed doc pages to the Apache docroot.

Several pages of the site are not SPAs but still need to live under the repo's
source control — the legacy gateway pages (JBrowse, download, contact, news,
external links) and the GeneHub result CGI. They cannot be FastAPI static
mounts because their public URLs are plain docroot files outside any
ProxyPass prefix, so the repo copies are published by this script (copy +
timestamped backup), the same pattern as scripts/deploy_blast2_preview.py.
No Apache reload or service restart is needed.

Source of truth: app/static/docpages/

Run on the production web node:

    python3 scripts/deploy_doc_pages.py             # publish changed pages
    python3 scripts/deploy_doc_pages.py --check     # compare only, exit 1 on drift
    python3 scripts/deploy_doc_pages.py --dry-run   # list what would change
    python3 scripts/deploy_doc_pages.py --only jbrowse download

Rollback: every target keeps its previous copy next to it as
`<name>.bak-<timestamp>`; copy that file back to restore.
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
SRC_DIR = REPO / "app" / "static" / "docpages"
DOCROOT = Path(os.environ.get("WHEATOMICS_DOCROOT", "/var/www/html"))
CGI_BIN = Path(os.environ.get("WHEATOMICS_CGI_BIN", "/var/www/cgi-bin"))

# key -> (source file, target path, description)
PAGES = {
    "jbrowse": ("jbrowse.html", DOCROOT / "jbrowse.html", "JBrowse gateway"),
    "download": ("download.html", DOCROOT / "download.html", "Download data"),
    "contact": ("help_contact.html", DOCROOT / "help" / "contact.html", "Contact page"),
    "news": ("help_news.html", DOCROOT / "help" / "news.html", "News & updates"),
    "outsitelink": ("outsitelink.html", DOCROOT / "outsitelink.html", "External links"),
    "genehub_result": ("geneDetail.py", CGI_BIN / "geneDetail.py", "GeneHub result CGI"),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def publish(key: str, src: Path, dest: Path, desc: str, *, check: bool, dry_run: bool) -> bool:
    if not src.is_file():
        print(f"[skip] {key}: repo source missing ({src})")
        return True
    if not dest.parent.is_dir():
        if check:
            print(f"[MISMATCH] {key}: target dir missing ({dest.parent})")
            return False
        if dry_run:
            print(f"[dry-run] would create {dest.parent}")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)

    src_digest = digest(src)
    if dest.is_file() and digest(dest) == src_digest:
        print(f"[ok] {key}: {dest} already up to date ({desc}, sha256 {src_digest})")
        return True
    if check:
        live = digest(dest) if dest.is_file() else "missing"
        print(f"[MISMATCH] {key}: {dest} repo={src_digest} live={live}")
        return False
    if dry_run:
        print(f"[dry-run] would publish {dest}  <- {src.relative_to(REPO)}  ({desc})")
        return True

    # copy2/copystat can fail with EPERM when the docroot filesystem refuses
    # utime changes (seen on /var/www/html); copy the bytes ourselves.
    if dest.is_file():
        backup = dest.with_name(dest.name + ".bak-" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        shutil.copyfile(dest, backup)
        print(f"[updated] {key}: {dest}  ({desc})")
        print(f"          backup: {backup}")
    else:
        print(f"[created] {key}: {dest}  ({desc})")
    shutil.copyfile(src, dest)
    dest.chmod(0o755 if dest.suffix == ".py" else 0o644)
    print(f"          size={dest.stat().st_size} sha256={digest(dest)}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="only compare repo and live copies")
    parser.add_argument("--dry-run", action="store_true", help="show planned changes without writing")
    parser.add_argument("--only", nargs="*", choices=sorted(PAGES), help="publish only these pages")
    args = parser.parse_args()

    keys = args.only or sorted(PAGES)
    ok = True
    for key in keys:
        src_name, dest, desc = PAGES[key]
        ok &= publish(key, SRC_DIR / src_name, dest, desc, check=args.check, dry_run=args.dry_run)

    if args.check:
        print("\n[check] all pages match the repo" if ok else "\n[check] differences found")
        return 0 if ok else 1
    print("\nDone." if not args.dry_run else "\nDry run complete (nothing written).")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
