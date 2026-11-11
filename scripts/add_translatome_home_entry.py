#!/usr/bin/env python3
"""Add the Translatome entry to the production landing page(s) (idempotent).

Run on the production web node (docroot files are owned by ``fei``):

    python3 scripts/add_translatome_home_entry.py
    python3 scripts/add_translatome_home_entry.py --check
    python3 scripts/add_translatome_home_entry.py --dry-run


The landing page (/var/www/html/index.html + /V2.0/index.html) is hand
maintained and not tracked in the repo. This script:
  * adds a Tools-dropdown item after GeneExpression;
  * adds a tool card after the GeneExpression card;
with a timestamped backup per file.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

TARGETS = [Path("/var/www/html/index.html"), Path("/var/www/html/V2.0/index.html")]
NAV_OLD = '<li><a href="https://wheatomics.sdau.edu.cn/expression/index.html">GeneExpression</a></li>'
NAV_NEW = NAV_OLD + '\n              <li><a href="https://wheatomics.sdau.edu.cn/translatome/">Translatome</a></li>'
CARD_OLD = ('<a class="tool-card" href="https://wheatomics.sdau.edu.cn/expression/index.html" '
            'data-keywords="gene expression rna tissue"><span class="tool-icon"><svg class="icon">'
            '<use href="#i-chart"/></svg></span><span><h3>GeneExpression</h3>'
            '<p>Query by Gene ID</p></span></a>')
CARD_NEW = CARD_OLD + (
    '\n          <a class="tool-card" href="https://wheatomics.sdau.edu.cn/translatome/" '
    'data-keywords="translatome ribo-seq rna-seq translation efficiency te heat stress grain">'
    '<span class="tool-icon"><svg class="icon"><use href="#i-chart"/></svg></span>'
    '<span><h3>Translatome</h3><p>RNA-seq / Ribo-seq / TE</p></span></a>')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--target", action="append", default=[])
    args = ap.parse_args()
    targets = [Path(t) for t in args.target] if args.target else TARGETS
    status = 0
    for path in targets:
        if not path.is_file():
            print(f"[skip] missing: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        has_nav = "/translatome/" in text and "Translatome</a></li>" in text
        has_card = 'href="https://wheatomics.sdau.edu.cn/translatome/"' in text and "<h3>Translatome</h3>" in text
        if has_nav and has_card:
            print(f"[ok] already patched: {path}")
            continue
        status = 1
        if args.check:
            print(f"[drift] {path}: nav={has_nav} card={has_card}")
            continue
        if args.dry_run:
            print(f"[dry-run] would patch: {path}")
            continue
        if NAV_OLD not in text or CARD_OLD not in text:
            print(f"[error] anchor missing in {path} (nav={NAV_OLD in text}, card={CARD_OLD in text})")
            status = 2
            continue
        backup = path.with_name(path.name + ".bak-" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        shutil.copyfile(path, backup)
        text = text.replace(NAV_OLD, NAV_NEW, 1).replace(CARD_OLD, CARD_NEW, 1)
        path.write_text(text, encoding="utf-8")
        print(f"[patched] {path}  backup: {backup}")
    return status


if __name__ == "__main__":
    sys.exit(main())
