#!/usr/bin/env python3
"""Rewrite live legacy CGI scripts so they read the DB password from
wheat_dbpass.py (which loads it from the app .env), instead of the
hardcoded leaked literal that the 2026-08 rotation invalidated.

Usage:
    python3 scripts/fix_legacy_cgi_passwords.py             # dry run
    python3 scripts/fix_legacy_cgi_passwords.py --yes       # apply
    python3 scripts/fix_legacy_cgi_passwords.py --dir /var/www/html/cgi-bin --yes

Idempotent; originals are copied to <dir>/.secret_backup_<ts>/ before edits.
"""
from __future__ import annotations

import argparse
import os
import shutil
import time
from pathlib import Path

LEAKS = ("'wheatomics115599'", '"wheatomics115599"', "'<REDACTED>'", '"<REDACTED>"')
REPL = "__import__('wheat_dbpass').DB_PASSWORD"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dir', default='/var/www/html/cgi-bin')
    ap.add_argument('--helper', default='cgi-py-RawScript/wheat_dbpass.py')
    ap.add_argument('--yes', action='store_true', help='apply changes (default: dry run)')
    args = ap.parse_args()

    d = Path(args.dir)
    if not d.is_dir():
        print('[ERR] not a directory:', d)
        return 2
    helper = Path(args.helper)
    if not helper.is_file():
        print('[ERR] helper not found:', helper)
        return 2

    targets = []
    for f in sorted(d.glob('*.py')):
        if f.name == 'wheat_dbpass.py':
            continue
        text = f.read_text(encoding='utf-8', errors='replace')
        if any(leak in text for leak in LEAKS):
            targets.append((f, text))

    print(f'dir: {d} | files with leaked literals: {len(targets)}')
    for f, _ in targets:
        print('  fix:', f.name)

    if not args.yes:
        print('(dry run: re-run with --yes to apply)')
        return 0

    # Always (re)install the helper, even when every CGI file was already
    # rewritten in a previous run - the helper itself may have been upgraded.
    shutil.copyfile(helper, d / 'wheat_dbpass.py')
    print('installed:', d / 'wheat_dbpass.py')
    if not targets:
        print('no CGI files need rewriting (already converted)')
        return 0

    backup = d / f'.secret_backup_{time.strftime("%Y%m%d%H%M%S")}'
    backup.mkdir()

    for f, text in targets:
        shutil.copyfile(f, backup / f.name)
        new = text
        for leak in LEAKS:
            new = new.replace(leak, REPL)
        f.write_text(new, encoding='utf-8')
        print('rewritten:', f.name)

    print('backup kept in:', backup)
    print('done')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
