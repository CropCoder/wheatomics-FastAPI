#!/usr/bin/env python3
"""Server-side script: retarget the V2.0 homepage scRNA entry and add TF Atlas.

The V2.0 landing page (``/V2.0/index.html``) is a standalone static file that is
NOT tracked in this repository, so this script edits it in place (with a
timestamped backup) in two places:

* every ``/scRNA/`` link becomes ``/singlecell/`` (the new MySQL-backed module);
  the menu label stays "scRNA";
* a ``TF Atlas`` entry is inserted after scRNA in the header
  ``Tools/Browse`` dropdown and in the ``Analysis Tools`` card grid
  (``.tool-card`` + ``data-keywords`` so the instant filter picks it up).

Idempotent: re-running only reports what is already in place.

Run on the production web node:
    python3 scripts/update_v2_home_scRNA_tfatlas.py

Test against a copy:
    WHEATOMICS_V2_INDEX=/tmp/v2_index.html python3 scripts/update_v2_home_scRNA_tfatlas.py
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
from datetime import datetime

DEFAULT_INDEX = "/var/www/html/V2.0/index.html"

OLD_SCRNA = "https://wheatomics.sdau.edu.cn/scRNA/"
NEW_SCRNA = "https://wheatomics.sdau.edu.cn/singlecell/"
TF_ATLAS = "https://wheatomics.sdau.edu.cn/regulatoryhub/TF_Atlas.html"

NAV_RE = re.compile(
    r'^([ \t]*)(?=[^\n]*/singlecell/)(?=[^\n]*>scRNA</a>)[^\n]*</li>\s*$',
    re.M,
)
CARD_RE = re.compile(
    r'^([ \t]*)(?=[^\n]*class="tool-card")(?=[^\n]*/singlecell/)[^\n]*</a>\s*$',
    re.M,
)

NAV_NEW = f'<li><a href="{TF_ATLAS}">TF Atlas</a></li>'
CARD_NEW = (
    f'<a class="tool-card" href="{TF_ATLAS}" '
    'data-keywords="tf transcription factor atlas motif promoter jaspar regulatory '
    'variant expression binding">'
    '<span class="tool-icon"><svg class="icon"><use href="#{icon}"/></svg></span>'
    '<span><h3>TF Atlas</h3><p>Transcription Factor and Regulatory Atlas</p></span></a>'
)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def pick_icon(text: str) -> str:
    for name in ("i-nodes", "i-network", "i-flask", "i-search"):
        if f'id="{name}"' in text:
            return name
    return "i-search"


def main() -> int:
    path = os.environ.get("WHEATOMICS_V2_INDEX", DEFAULT_INDEX)
    if not os.path.exists(path):
        print(f"[ERR] not found: {path}")
        return 1

    original = open(path, encoding="utf-8").read()
    text = original

    # 1) scRNA -> singlecell (both the /scRNA/ and the suffix-less form)
    scRNA_hits = text.count(OLD_SCRNA)
    text = text.replace(OLD_SCRNA, NEW_SCRNA)
    text = text.replace("https://wheatomics.sdau.edu.cn/scRNA",
                        "https://wheatomics.sdau.edu.cn/singlecell")

    # 2) TF Atlas entry, inserted after the scRNA row in both places
    icon = pick_icon(text)
    added_nav = added_card = 0
    if TF_ATLAS in text:
        print("[ok] TF Atlas already linked, skipping the insert")
    else:
        nav = NAV_RE.search(text)
        if not nav:
            print("[ERR] anchor not found: scRNA entry in the header Tools/Browse dropdown")
        else:
            line = nav.group(0).rstrip("\n")
            indent = nav.group(1)
            text = text.replace(line, line + "\n" + indent + NAV_NEW, 1)
            added_nav = 1
            print(f"[ok] nav entry inserted (icon #{icon})")

        card = CARD_RE.search(text)
        if not card:
            print("[ERR] anchor not found: scRNA card in #tools-grid")
        else:
            line = card.group(0).rstrip("\n")
            indent = card.group(1)
            text = text.replace(line, line + "\n" + indent + CARD_NEW.format(icon=icon), 1)
            added_card = 1
            print(f"[ok] tool card inserted (icon #{icon})")

    if text == original:
        print(f"[ok] {path} already up to date, nothing written")
        return 0 if (added_nav or added_card or scRNA_hits or TF_ATLAS in original) else 1

    backup = path + ".bak-" + datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, backup)
    open(path, "w", encoding="utf-8", newline="").write(text)

    checks = {
        "scRNA links retargeted to /singlecell/": scRNA_hits,
        "remaining /scRNA/ links (expect 0)": text.count(OLD_SCRNA),
        "/singlecell/ references": text.count("/singlecell/"),
        "TF Atlas references (expect 2: nav + card)": text.count(TF_ATLAS),
        "tool cards": len(re.findall(r'class="tool-card"', text)),
        "lines added": text.count("\n") - original.count("\n"),
    }
    print(f"\n[done] {path}")
    print(f"       sha256 {sha256(original)} -> {sha256(text)}")
    print(f"       backup: {backup}")
    for label, value in checks.items():
        print(f"       {label}: {value}")

    if checks["remaining /scRNA/ links (expect 0)"] != 0:
        print("[ERR] some /scRNA/ links remain, check the backup")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
