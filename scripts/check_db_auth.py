#!/usr/bin/env python3
"""Quick authentication matrix: can the given MySQL user reach every app database?

Fast answer for 1045 (access denied) reports: run this with the password from
the server .env and see which databases open.

Usage:
    export DB_PASSWORD=...        # or --password ...
    python3 scripts/check_db_auth.py
"""
from __future__ import annotations

import argparse
import os
import sys

import pymysql

DB_NAMES = (
    'gene_expression', 'coexpressiondb', 'wheatPPIdb', 'cloned_gene_db',
    'orthofinder_n', 'Convert_gene_id', 'Comparative_Genomics_db', 'Genehub_DB',
    'Genefuncdb', 'pre_blast', 'wheatomics_blastp2', 'symapdb', 'wheatomics_db',
    'Triticeae_Research_filter', 'wheat_function', 'synteny_mysql', 'jbrowse_meta',
    'eqtl', 'wheat_psp_db',
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--host', default='localhost')
    ap.add_argument('--port', type=int, default=3306)
    ap.add_argument('--user', default='wheatomics_user')
    ap.add_argument('--password', default=os.environ.get('DB_PASSWORD'),
                    help='DB password (or export DB_PASSWORD)')
    args = ap.parse_args()
    if not args.password:
        ap.error('--password is required (or export DB_PASSWORD)')

    print('python', sys.version.split()[0], '| pymysql', pymysql.__version__)
    print('user=%s@%s:%s' % (args.user, args.host, args.port), '| password=...' + str(args.password)[-4:])
    print()

    ok = 0
    for db in DB_NAMES:
        try:
            conn = pymysql.connect(host=args.host, port=args.port,
                                   user=args.user, password=args.password,
                                   database=db, connect_timeout=5)
            with conn.cursor() as cur:
                cur.execute('SELECT 1')
                cur.fetchone()
            conn.close()
            print('  OK  ', db)
            ok += 1
        except pymysql.err.MySQLError as e:
            print('  FAIL', db.ljust(28), e)

    print()
    print('%d/%d databases reachable' % (ok, len(DB_NAMES)))
    return 0 if ok == len(DB_NAMES) else 1


if __name__ == '__main__':
    raise SystemExit(main())
