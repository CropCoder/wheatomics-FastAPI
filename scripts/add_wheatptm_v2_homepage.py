#!/usr/bin/env python3
"""Server-side script: add wheatPTM to the WheatOmics V2.0 homepage.

The V2.0 landing page (``/V2.0/index.html``) is a standalone static file that is
NOT tracked in this repository, so this script edits it in place (with a
timestamped backup) in two places, right after the wheatPSP entries:

* the header ``Tools/Browse`` dropdown navigation;
* the ``Analysis Tools`` card grid (``.tool-card`` + ``data-keywords`` so the
  existing instant filter picks it up).

Run on the production web node (the file is owned by the service account, so no
sudo is needed)::

    python3 scripts/add_wheatptm_v2_homepage.py

Test against a copy without touching production::

    WHEATOMICS_V2_INDEX=/tmp/v2_index.html python3 scripts/add_wheatptm_v2_homepage.py

Idempotent: safe to run twice.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
from datetime import datetime

DEFAULT_INDEX = "/var/www/html/V2.0/index.html"

NAV_ANCHOR = '<li><a href="https://wheatomics.sdau.edu.cn/wheatPSP/">wheatPSP</a></li>'
NAV_NEW = '<li><a href="https://wheatomics.sdau.edu.cn/wheatPTM/">wheatPTM</a></li>'

CARD_RE = re.compile(
    r'[ \t]*<a class="tool-card" href="https://wheatomics\.sdau\.edu\.cn/wheatPSP/"[^\n]*</a>'
)
CARD_NEW = (
    '<a class="tool-card" href="https://wheatomics.sdau.edu.cn/wheatPTM/" '
    'data-keywords="ptm post-translational modification phosphorylation glycosylation '
    'acetylation ubiquitination crotonylation succinylation malonylation protein site">'
    '<span class="tool-icon"><svg class="icon"><use href="#i-flask"/></svg></span>'
    '<span><h3>wheatPTM</h3><p>Protein Post-translational Modification Sites</p></span></a>'
)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    path = os.environ.get("WHEATOMICS_V2_INDEX", DEFAULT_INDEX)
    if not os.path.exists(path):
        print(f"[ERR] not found: {path}")
        return 1

    text = open(path, encoding="utf-8").read()
    if "/wheatPTM/" in text:
        print(f"[ok] {path} already links wheatPTM ({text.count('/wheatPTM/')} references), nothing to do")
        return 0

    if NAV_ANCHOR not in text:
        print("[ERR] anchor not found: wheatPSP entry in the header Tools/Browse dropdown")
        return 1
    nav_line = next(line for line in text.splitlines() if NAV_ANCHOR in line)
    nav_indent = nav_line[: len(nav_line) - len(nav_line.lstrip())]

    card_match = CARD_RE.search(text)
    if not card_match:
        print("[ERR] anchor not found: wheatPSP tool card in #tools-grid")
        return 1
    card_line = card_match.group(0)
    card_indent = card_line[: len(card_line) - len(card_line.lstrip())]

    backup = path + ".bak-" + datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, backup)

    updated = text.replace(nav_line, nav_line + "\n" + nav_indent + NAV_NEW, 1)
    updated = updated.replace(card_line, card_line + "\n" + card_indent + CARD_NEW, 1)
    open(path, "w", encoding="utf-8", newline="").write(updated)

    checks = {
        "wheatPTM references (expect 2: nav + card)": updated.count("/wheatPTM/"),
        "wheatPSP references (expect 2, unchanged)": updated.count("/wheatPSP/"),
        "tool cards (expect 25)": len(re.findall(r'class="tool-card"', updated)),
        "tools-grid container (expect 1)": updated.count('id="tools-grid"'),
        "lines added (expect 2)": updated.count("\n") - text.count("\n"),
    }
    print(f"[done] {path}")
    print(f"       sha256 {sha256(text)} -> {sha256(updated)}")
    print(f"       backup: {backup}")
    for label, value in checks.items():
        print(f"       {label}: {value}")
    if checks["wheatPTM references (expect 2: nav + card)"] != 2 or checks["lines added (expect 2)"] != 2:
        print("[ERR] unexpected result, restore backup if the page looks wrong")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
