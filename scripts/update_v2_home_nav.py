#!/usr/bin/env python3
"""Update the header navigation of the production V2.0 landing pages.

The WheatOmics 2.0 landing page (``/var/www/html/index.html`` and its
compatibility copy ``/var/www/html/V2.0/index.html``) is a standalone static
file that is **NOT tracked in this repository** (unlike the SPA pages, which
share ``/api/v2shell/shell.js``).  Its header still carries the old menu:
``About`` as the last dropdown and ``External Links`` as a top-level link.
This script edits those two files in place so the landing page matches the
rest of the site:

* ``About`` is renamed to ``More``;
* ``External Links`` moves from the top level into the ``More`` dropdown
  (first item, before Citation);
* a new ``Agent`` dropdown is added before ``More`` with the Agent / API
  entry points (``/agent.html``, ``/api/docs``, ``/api/redoc``,
  ``/api/openapi.json``).

Run on the production web node **after** the repo deploy (the ``Agent``
dropdown points at ``/agent.html``, which is published by
``scripts/deploy_doc_pages.py``).  The web node runs the site from the conda
environment ``zjw``::

    conda activate zjw
    python3 scripts/update_v2_home_nav.py            # patch both landing pages
    python3 scripts/update_v2_home_nav.py --check    # compare only, exit 1 on drift
    python3 scripts/update_v2_home_nav.py --dry-run  # show what would change

Testing against downloaded copies (no production access needed)::

    cp /tmp/live_root.html /tmp/test_index.html
    python3 scripts/update_v2_home_nav.py --target /tmp/test_index.html

Every target is backed up next to itself as ``<name>.bak-<timestamp>`` before
being rewritten; copy that file back to roll back.  Re-running the script is
safe: an already-updated page is reported as up to date and left untouched.

This is intentionally a plain text patch (not a DOM rewrite): the landing page
is a large hand-maintained file, and the anchors below are stable.
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

# --- stable anchors in the current landing page ------------------------------
EXTERNAL_TOP = (
    f'          <div class="nav-item"><a class="nav-link" href="{DOMAIN}/outsitelink.html">'
    "External Links</a></div>"
)
DOWNLOAD_ITEM = (
    f'          <div class="nav-item"><a class="nav-link" href="{DOMAIN}/download.html">'
    "Download Data</a></div>"
)
ABOUT_TRIGGER = 'aria-expanded="false">About'
EXTERNAL_LI = f'<li><a href="{DOMAIN}/outsitelink.html">External Links</a></li>'

AGENT_BLOCK = f"""          <div class="nav-item">
            <button class="nav-trigger" type="button" aria-expanded="false">Agent
              <svg class="nav-chevron" viewBox="0 0 12 12" aria-hidden="true"><path d="m3 4.5 3 3 3-3"/></svg>
            </button>
            <ul class="dropdown">
              <li><a href="{DOMAIN}/agent.html">Agent &amp; API</a></li>
              <li><a href="{DOMAIN}/agent.html#mcp">MCP Server (SSE)</a></li>
              <li><a href="/api/docs">API Documentation</a></li>
              <li><a href="/api/redoc">API Reference</a></li>
              <li><a href="/api/openapi.json">OpenAPI Schema</a></li>
            </ul>
          </div>"""

# Landing pages use in-page anchors (#citation); the regex also tolerates the
# /V2.0/#citation form in case a copy is generated from the canonical page.
CITATION_LI_RE = re.compile(
    r'^(?P<indent>[ \t]*)<li><a href="(?:/V2\.0/)?#citation">Citation</a></li>$',
    re.MULTILINE,
)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def count(text: str, needle: str) -> int:
    return text.count(needle)


def is_patched(text: str) -> bool:
    return (
        count(text, EXTERNAL_TOP) == 0
        and count(text, f'aria-expanded="false">More') == 1
        and count(text, f'aria-expanded="false">Agent') == 1
        and count(text, EXTERNAL_LI) == 1
    )


def patch(text: str) -> tuple[str, list[str]]:
    """Return (patched_text, checks) or raise SystemExit on a broken anchor."""
    problems: list[str] = []
    for label, needle, expected in (
        ("top-level External Links item", EXTERNAL_TOP, 1),
        ("Download Data nav item", DOWNLOAD_ITEM, 1),
        ("About nav trigger", ABOUT_TRIGGER, 1),
    ):
        found = count(text, needle)
        if found != expected:
            problems.append(f"expected {expected} x {label}, found {found}")
    citation_match = CITATION_LI_RE.search(text)
    if citation_match is None:
        problems.append("Citation dropdown item anchor not found")
    if problems:
        raise SystemExit("[ERR] unexpected landing-page markup: " + "; ".join(problems))

    assert citation_match is not None  # guarded above; helps readers/mypy
    indent = citation_match.group("indent")
    citation_line = citation_match.group(0)
    external_li_line = indent + EXTERNAL_LI
    before_items = count(text, '<div class="nav-item">')

    # 1) external links: top level -> first item of the More dropdown
    updated = text.replace(EXTERNAL_TOP + "\n", "", 1)
    updated = updated.replace(DOWNLOAD_ITEM, DOWNLOAD_ITEM + "\n" + AGENT_BLOCK, 1)
    updated = updated.replace(ABOUT_TRIGGER, 'aria-expanded="false">More', 1)
    updated = updated.replace(citation_line, external_li_line + "\n" + citation_line, 1)

    # 2) post-write assertions
    citation_after = CITATION_LI_RE.search(updated)
    checks = [
        ("no top-level External Links left", count(updated, EXTERNAL_TOP) == 0),
        ('exactly one "Agent" trigger', count(updated, 'aria-expanded="false">Agent') == 1),
        ('exactly one "More" trigger', count(updated, 'aria-expanded="false">More') == 1),
        ('no "About" trigger left', count(updated, ABOUT_TRIGGER) == 0),
        ("External Links inside More", count(updated, EXTERNAL_LI) == 1),
        ("External Links kept Citation indentation", external_li_line in updated),
        (
            "External Links before Citation",
            citation_after is not None
            and updated.index(EXTERNAL_LI) < citation_after.start(),
        ),
        (
            "same number of top-level nav items (External Links -> Agent swap)",
            count(updated, '<div class="nav-item">') == before_items,
        ),
    ]
    failed = [name for name, ok in checks if not ok]
    if failed:
        raise SystemExit("[ERR] post-patch assertion failed: " + ", ".join(failed))
    return updated, [name for name, _ in checks]


def process(path: Path, *, check: bool, dry_run: bool) -> bool:
    """Patch one target. Return True on success/up-to-date, False on failure."""
    if not path.is_file():
        print(f"[skip] {path}: not found (run on the web node, or pass --target)")
        return True
    try:
        text = read(path)
    except OSError as exc:
        print(f"[ERR] {path}: cannot read: {exc}")
        return False

    if is_patched(text):
        print(f"[ok] {path}: already up to date (Agent + More menus present)")
        return True
    if check:
        print(f"[MISMATCH] {path}: old About / top-level External Links nav is still live")
        return False

    try:
        updated, checks = patch(text)
    except SystemExit as exc:
        print(str(exc))
        return False

    added = len(updated.splitlines()) - len(text.splitlines())
    print(f"[{'dry-run' if dry_run else 'patch'}] {path}")
    print(f"          sha256 {sha256(text)} -> {sha256(updated)}  lines {added:+d}")
    for name in checks:
        print(f"          check: {name}")
    if dry_run:
        return True

    backup = path.with_name(path.name + ".bak-" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    try:
        shutil.copy2(path, backup)
        # open() rather than Path.write_text(): the ``newline`` argument of
        # write_text() only exists on Python 3.10+, and the exact same script
        # must also run on older web-node interpreters.
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
        ok &= process(target, check=args.check, dry_run=args.dry_run)

    if not found:
        print("\n[skip] no landing-page targets found (run this on the web node, or pass --target)")
    elif args.check:
        print("\n[check] all landing pages match the new menu" if ok else "\n[check] differences found")
    elif args.dry_run:
        print("\nDry run complete (nothing written).")
    else:
        print("\nDone." if ok else "\nCompleted with errors.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
