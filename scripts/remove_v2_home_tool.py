#!/usr/bin/env python3
"""Retire a tool from the production V2.0 landing pages.

The WheatOmics 2.0 landing page (``/var/www/html/index.html`` and its
compatibility copy ``/var/www/html/V2.0/index.html``) is a standalone static
file that is **NOT tracked in this repository**.  When a tool is retired it has
two entry points there:

1. an item in the header ``Tools`` mega dropdown;
2. a ``<a class="tool-card" ...>`` in the ``Analysis Tools`` grid.

This script removes both for the given tool (default: **SyntenySearch** →
``/symap/index.html``, retired 2026-10-29 because ``Collinearity`` covers
synteny browsing).  The tool page itself is left on the server; it is simply no
longer linked from the homepage.  The SPA chrome in this repository was
updated in the same change (``app/static/blast2/index.html``,
``app/static/_v2/shell.js``, ``app/static/wheatPTM/index.html`` and
``app/static/coexpression/stats.html``).

Run on the production web node **after** the repo deploy.  The web node runs in
the conda environment ``zjw``::

    conda activate zjw
    python3 scripts/remove_v2_home_tool.py                 # SyntenySearch (default)
    python3 scripts/remove_v2_home_tool.py --check         # compare only, exit 1 on drift
    python3 scripts/remove_v2_home_tool.py --dry-run       # show what would change
    python3 scripts/remove_v2_home_tool.py --name Foo --href /foo/index.html

Testing against downloaded copies (no production access needed)::

    python3 scripts/remove_v2_home_tool.py --target /tmp/test_index.html

Every target is backed up next to itself as ``<name>.bak-<timestamp>`` before
being rewritten; copy that file back to roll back.  Re-running is safe: an
already-cleaned page is reported as up to date and left untouched.

Exit codes: 0 = success/already clean, 1 = drift in ``--check`` mode, write
failure, or a broken anchor.
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
DEFAULT_TARGETS = (
    Path("/var/www/html/index.html"),
    Path("/var/www/html/V2.0/index.html"),
)
DEFAULT_NAME = "SyntenySearch"
DEFAULT_HREF = "/symap/index.html"

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def href_variants(href: str) -> list[str]:
    """Accept absolute and site-root-relative spellings of the same link."""

    href = href.strip()
    out = [href]
    if href.startswith(DOMAIN):
        out.append(href[len(DOMAIN):] or "/")
    else:
        out.append(DOMAIN + "/" + href.lstrip("/"))
    # preserve order, drop duplicates
    unique: list[str] = []
    for candidate in out:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def build_patterns(name: str, href: str) -> tuple[re.Pattern[str], re.Pattern[str]]:
    """Return (nav-item line regex, tool-card line regex) for one tool."""

    alts = "|".join(re.escape(h) for h in href_variants(href))
    nav = re.compile(
        r"^[ \t]*<li><a href=\"(?:" + alts + r")\">" + re.escape(name) + r"</a></li>\n",
        re.MULTILINE,
    )
    card = re.compile(
        r"^[ \t]*<a " + r'class="tool-card" href="(?:' + alts + r')"[^\n]*?</a>\n',
        re.MULTILINE,
    )
    return nav, card


def is_clean(text: str, name: str, href: str) -> bool:
    """True when neither managed entry point (nav item, tool card) is present."""

    nav, card = build_patterns(name, href)
    return not nav.search(text) and not card.search(text)


def links_tool(text: str, href: str) -> bool:
    return any(h in text for h in href_variants(href))


def patch(text: str, name: str, href: str) -> tuple[str, list[str], dict[str, int]]:
    """Remove the nav item and the tool card. Raises SystemExit on broken anchors."""
    nav_re, card_re = build_patterns(name, href)
    nav_hits = len(nav_re.findall(text))
    card_hits = len(card_re.findall(text))
    if nav_hits == 0 and card_hits == 0:
        raise SystemExit("[ERR] no nav item / tool card found for the given --name/--href")
    if nav_hits > 1 or card_hits > 1:
        raise SystemExit(
            f"[ERR] ambiguous anchors (nav={nav_hits}, card={card_hits}); refusing to guess"
        )

    before_cards = text.count('class="tool-card"')
    before_nav_items = text.count('<div class="nav-item">')
    updated = text
    if nav_hits:
        updated = nav_re.sub("", updated, count=1)
    if card_hits:
        updated = card_re.sub("", updated, count=1)

    checks = [
        ("nav Tools item removed", not nav_re.search(updated)),
        ("tool card removed", not card_re.search(updated)),
        (
            "other tool cards untouched",
            updated.count('class="tool-card"') == before_cards - card_hits,
        ),
        (
            "header nav item count unchanged",
            updated.count('<div class="nav-item">') == before_nav_items,
        ),
        ("header nav still present", '<nav class="main-nav"' in updated),
    ]
    failed = [label for label, ok in checks if not ok]
    if failed:
        raise SystemExit("[ERR] post-removal assertion failed: " + ", ".join(failed))
    return updated, [label for label, _ in checks], {"nav": nav_hits, "card": card_hits}


def process(
    path: Path, name: str, href: str, *, check: bool, dry_run: bool
) -> bool:
    if not path.is_file():
        print(f"[skip] {path}: not found (run on the web node, or pass --target)")
        return True
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[ERR] {path}: cannot read: {exc}")
        return False

    if is_clean(text, name, href):
        print(f"[ok] {path}: already up to date ({name} entry points absent)")
        return True
    if check:
        print(f"[MISMATCH] {path}: {name} is still linked from the homepage")
        return False

    try:
        updated, checks, removed = patch(text, name, href)
    except SystemExit as exc:
        print(str(exc))
        return False

    delta = len(updated.splitlines()) - len(text.splitlines())
    print(f"[{'dry-run' if dry_run else 'patch'}] {path}")
    print(
        f"          removed nav item x{removed['nav']}, tool card x{removed['card']}"
        f"  sha256 {sha256(text)} -> {sha256(updated)}  lines {delta:+d}"
    )
    for label in checks:
        print(f"          check: {label}")
    if links_tool(updated, href):
        print(
            f"          note: {href} is still referenced elsewhere on the page"
            " (left untouched; review manually if it should go too)"
        )
    if dry_run:
        return True

    backup = path.with_name(path.name + ".bak-" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    try:
        shutil.copy2(path, backup)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(updated)
    except PermissionError:
        print(f"[needs-sudo] cannot write {path} (owned by root/www-data).")
        print(f"             install once with: sudo cp {backup} {path} && sudo chmod 644 {path}")
        return False
    except OSError as exc:
        print(f"[ERR] {path}: write failed: {exc}")
        return False
    print(f"          backup: {backup}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default=DEFAULT_NAME, help="tool label (default: SyntenySearch)")
    parser.add_argument("--href", default=DEFAULT_HREF, help="tool URL (default: /symap/index.html)")
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

    ok = True
    found = [target for target in targets if target.is_file()]
    for target in targets:
        ok &= process(
            target, args.name, args.href, check=args.check, dry_run=args.dry_run
        )

    if not found:
        print("\n[skip] no landing-page targets found (run this on the web node, or pass --target)")
    elif args.check:
        print(
            "\n[check] all landing pages are clean of "
            f"{args.name}" if ok else f"\n[check] {args.name} is still linked"
        )
    elif args.dry_run:
        print("\nDry run complete (nothing written).")
    else:
        print("\nDone." if ok else "\nCompleted with errors.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
