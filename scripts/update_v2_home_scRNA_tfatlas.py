#!/usr/bin/env python3
"""Retarget scRNA and add a TF Atlas entry on the production V2.0 landing pages.

The WheatOmics 2.0 landing page exists twice as a standalone static file that
is **NOT tracked in this repository**:

    /var/www/html/index.html        -> served at https://wheatomics.sdau.edu.cn/
    /var/www/html/V2.0/index.html   -> compatibility copy served at /V2.0/

This script patches both (same convention as ``update_v2_home_nav.py``):

* every ``/scRNA/`` link becomes ``/singlecell/`` (the menu label stays
  "scRNA");
* a ``TF Atlas`` entry is cloned from the existing scRNA entry in the header
  ``Tools`` dropdown and in the ``Analysis Tools`` card grid, so the markup,
  the icon and the ``data-keywords`` used by the instant filter all match the
  page being edited.

Idempotent: entries already in place are reported and left alone.  Every target
is backed up as ``<name>.bak-<timestamp>`` before being rewritten; copy that
file back to roll back.

Run on the production web node::

    python3 scripts/update_v2_home_scRNA_tfatlas.py            # patch both pages
    python3 scripts/update_v2_home_scRNA_tfatlas.py --check    # compare only
    python3 scripts/update_v2_home_scRNA_tfatlas.py --dry-run  # write nothing
    python3 scripts/update_v2_home_scRNA_tfatlas.py --target /tmp/index.html
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

DOMAIN = "https://wheatomics.sdau.edu.cn"
OLD_SCRNA = f"{DOMAIN}/scRNA"
NEW_SCRNA = f"{DOMAIN}/singlecell"
TF_ATLAS = f"{DOMAIN}/regulatoryhub/TF_Atlas.html"

DEFAULT_TARGETS = (
    Path("/var/www/html/index.html"),
    Path("/var/www/html/V2.0/index.html"),
)

# Absolute form first, then the root-relative form some copies use.
SUBS = (
    (f"{DOMAIN}/scRNA/", f"{DOMAIN}/singlecell/"),
    (f"{DOMAIN}/scRNA", f"{DOMAIN}/singlecell"),
    ('"/scRNA/', '"/singlecell/'),
    ("'/scRNA/", "'/singlecell/"),
)

NAV_ENTRY = f'<li><a href="{TF_ATLAS}">TF Atlas</a></li>'
CARD_KEYWORDS = (
    "tf transcription factor atlas motif promoter jaspar regulatory "
    "variant expression binding"
)
CARD_TITLE = "TF Atlas"
CARD_TEXT = "Transcription Factor and Regulatory Atlas"

# Whole-line anchor for the nav item (it is always a single ``<li>`` line);
# the lookaheads keep the match independent of attribute order.
NAV_RE = re.compile(
    r'^([ \t]*)(?=[^\n]*/singlecell/)(?=[^\n]*>scRNA</a>)[^\n]*</li>[ \t]*$',
    re.MULTILINE,
)
CARD_OPEN_RE = re.compile(r'^([ \t]*)<a\b[^>]*>', re.MULTILINE)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def pick_icon(text: str) -> str:
    for name in ("i-nodes", "i-network", "i-flask", "i-search", "i-cells"):
        if f'id="{name}"' in text:
            return name
    return ""


def retarget(text: str) -> tuple[str, int]:
    hits = 0
    for old, new in SUBS:
        found = text.count(old)
        if found:
            text = text.replace(old, new)
            hits += found
    return text, hits


def clone_nav(line: str) -> str:
    nav = re.sub(r'href="[^"]*"', f'href="{TF_ATLAS}"', line, count=1)
    return re.sub(r'>[^<]*</a>', f'>{CARD_TITLE}</a>', nav, count=1)


def clone_card(line: str, icon: str) -> str:
    card = re.sub(r'href="[^"]*"', f'href="{TF_ATLAS}"', line, count=1)
    card = re.sub(r'<h3>.*?</h3>', f'<h3>{CARD_TITLE}</h3>', card, count=1, flags=re.S)
    card = re.sub(r'<p>.*?</p>', f'<p>{CARD_TEXT}</p>', card, count=1, flags=re.S)
    if 'data-keywords="' in card:
        card = re.sub(r'data-keywords="[^"]*"', f'data-keywords="{CARD_KEYWORDS}"', card, count=1)
    else:
        card = card.replace('class="tool-card"', f'class="tool-card" data-keywords="{CARD_KEYWORDS}"', 1)
    if icon:
        card = re.sub(r'(<use href="#)[^"]*(")', rf'\g<1>{icon}\g<2>', card, count=1)
    return card


def find_card(text: str, needle: str) -> tuple[str, str, int] | None:
    """Return (block, indent, end) for the first ``.tool-card`` linking ``needle``.

    Cards are often wrapped over several lines, so locate the opening ``<a>``
    and walk to its matching ``</a>`` instead of matching a single line.
    """
    for match in CARD_OPEN_RE.finditer(text):
        if 'class="tool-card"' not in match.group(0):
            continue
        end = text.find('</a>', match.end())
        if end < 0:
            continue
        end += len('</a>')
        block = text[match.start():end]
        if needle in block:
            return block, match.group(1), end
    return None


def patch(text: str) -> tuple[str, list[str]]:
    """Return (patched_text, notes); raise SystemExit on a broken anchor."""
    notes: list[str] = []

    text, hits = retarget(text)
    if hits:
        notes.append(f"scRNA links retargeted to /singlecell/: {hits}")
    elif "/scRNA/" not in text:
        notes.append("scRNA links already retargeted")

    if NAV_ENTRY in text:
        notes.append("nav entry already present")
    else:
        match = NAV_RE.search(text)
        if match is None:
            raise SystemExit(
                "[ERR] anchor not found: the scRNA row in the header Tools dropdown"
            )
        line = match.group(0)
        indent = match.group(1)
        text = text.replace(line, line + "\n" + indent + clone_nav(line.lstrip()), 1)
        notes.append("nav entry inserted")

    if find_card(text, TF_ATLAS) is not None:
        notes.append("tool card already present")
    else:
        match = find_card(text, "/singlecell/")
        if match is None:
            raise SystemExit(
                "[ERR] anchor not found: the scRNA card in the Analysis Tools grid"
            )
        block, indent, end = match
        icon = pick_icon(text)
        text = text[:end] + "\n" + indent + clone_card(block.lstrip(), icon) + text[end:]
        notes.append(f"tool card inserted (icon #{icon or 'inherited'})")

    checks = {
        "no /scRNA/ links left": text.count("/scRNA/") == 0,
        "/singlecell/ references (>=2)": text.count("/singlecell/") >= 2,
        "TF Atlas nav entry": text.count(NAV_ENTRY) == 1,
        "TF Atlas tool card": find_card(text, TF_ATLAS) is not None,
        "TF Atlas references (2)": text.count(TF_ATLAS) == 2,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("[ERR] post-patch assertion failed: " + ", ".join(failed))
    return text, notes


def process(path: Path, *, check: bool, dry_run: bool) -> bool:
    if not path.is_file():
        print(f"[skip] {path}: not found (run on the web node, or pass --target)")
        return True
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[ERR] {path}: cannot read: {exc}")
        return False

    if check and not dry_run:
        missing = []
        if "/scRNA/" in text:
            missing.append("scRNA links still point at /scRNA/")
        if NAV_ENTRY not in text:
            missing.append("no TF Atlas nav entry")
        if find_card(text, TF_ATLAS) is None:
            missing.append("no TF Atlas tool card")
        if missing:
            print(f"[MISMATCH] {path}: {'; '.join(missing)}")
            return False
        print(f"[ok] {path}: already up to date")
        return True

    try:
        updated, notes = patch(text)
    except SystemExit as exc:
        print(str(exc))
        return False

    if updated == text:
        print(f"[ok] {path}: already up to date, nothing written")
        return True

    print(f"[{'dry-run' if dry_run else 'patch'}] {path}")
    print(f"          sha256 {sha256(text)} -> {sha256(updated)}  "
          f"lines {len(updated.splitlines()) - len(text.splitlines()):+d}")
    for note in notes:
        print(f"          {note}")
    if dry_run:
        return True

    backup = path.with_name(path.name + ".bak-" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    try:
        shutil.copy2(path, backup)
        # open() rather than Path.write_text(): the ``newline`` argument of
        # write_text() only exists on Python 3.10+, and this script also runs
        # on older web-node interpreters.
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(updated)
    except PermissionError:
        print(f"[needs-sudo] cannot write {path} (root/www-data owned).")
        print(f"             install once with: sudo cp {backup} {path} && sudo chmod 644 {path}")
        return False
    except OSError as exc:
        print(f"[ERR] {path}: write failed: {exc}")
        return False
    print(f"          backup: {backup}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        action="append",
        metavar="PATH",
        help="landing page to patch (repeatable; default: /var/www/html/index.html "
        "and /var/www/html/V2.0/index.html)",
    )
    parser.add_argument("--check", action="store_true", help="only compare, exit 1 on drift")
    parser.add_argument("--dry-run", action="store_true", help="show planned changes, write nothing")
    args = parser.parse_args()

    if args.target:
        targets = [Path(p) for p in args.target]
    elif os.environ.get("WHEATOMICS_V2_HOMES"):
        targets = [Path(p) for p in os.environ["WHEATOMICS_V2_HOMES"].split(",") if p]
    elif os.environ.get("WHEATOMICS_V2_HOME"):
        targets = [Path(os.environ["WHEATOMICS_V2_HOME"])]
    else:
        targets = list(DEFAULT_TARGETS)

    found = [target for target in targets if target.is_file()]
    ok = True
    for target in targets:
        ok &= process(target, check=args.check, dry_run=args.dry_run)

    if not found:
        print("\n[skip] no landing-page targets found (run on the web node, or pass --target)")
    elif args.check:
        print("\n[check] all landing pages are current" if ok else "\n[check] differences found")
    elif args.dry_run:
        print("\nDry run complete (nothing written).")
    else:
        print("\nDone." if ok else "\nCompleted with errors.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
