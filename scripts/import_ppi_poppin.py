#!/usr/bin/env python3
"""Import PoppIn wheat interaction predictions into wheatPPIdb.PPI_poppin.

Source: poppin_wheat_interactions.FINAL.tsv
    wheat_a  wheat_b  sub_a  sub_b  n_supporting_edges
    best_identity_a  best_identity_b  example_rice_pair

The wheatPPI router (app/api/routers/ppi.py) discovers columns *by position*,
so this table must keep the same layout as PPI_result:

    0 Nameid  1 WheatID1  2 WheatID2  3 ID1  4 ID2
    5 Score   6 Annotation1  7 Annotation2

Mapping:
    WheatID1      <- wheat_a                 WheatID2      <- wheat_b
    ID1           <- sub_a                   ID2           <- sub_b
    Score         <- n_supporting_edges       (1-9; the router filters Score >= N)
    Annotation1   <- example_rice_pair
    Annotation2   <- "identity_a: X, identity_b: Y"

Run on the server:
    export DB_PASSWORD=...
    python3 scripts/import_ppi_poppin.py --tsv /path/to/poppin_wheat_interactions.FINAL.tsv
    # dry run first (counts rows, no writes):
    python3 scripts/import_ppi_poppin.py --tsv ... --dry-run
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:
    sys.exit("pymysql is required: pip install pymysql")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "wheatomics_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_PPI", "wheatPPIdb")
TABLE = "PPI_poppin"
BATCH = 5000

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS `{TABLE}` (
  `Nameid`      int NOT NULL AUTO_INCREMENT,
  `WheatID1`    varchar(200) NOT NULL,
  `WheatID2`    varchar(200) NOT NULL,
  `ID1`         varchar(50)  DEFAULT NULL,
  `ID2`         varchar(50)  DEFAULT NULL,
  `Score`       double       NOT NULL,
  `Annotation1` text,
  `Annotation2` text,
  PRIMARY KEY (`Nameid`),
  KEY `idx_score` (`Score`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

INSERT_SQL = (
    f"INSERT INTO `{TABLE}` "
    "(`WheatID1`,`WheatID2`,`ID1`,`ID2`,`Score`,`Annotation1`,`Annotation2`) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s)"
)


def _clean(v: str) -> str:
    v = (v or "").strip()
    return "" if v.lower() in ("na", "nan", "none", "null", "-") else v


def parse_row(cols: list[str]):
    """Map one TSV row to the PPI_poppin insert tuple, or None if unusable."""
    if len(cols) < 8:
        return None
    wheat_a, wheat_b = _clean(cols[0]), _clean(cols[1])
    if not wheat_a or not wheat_b:
        return None
    sub_a, sub_b = _clean(cols[2]), _clean(cols[3])
    try:
        edges = int(float(cols[4]))
    except (TypeError, ValueError):
        return None
    id_a, id_b = _clean(cols[5]), _clean(cols[6])
    rice_pair = _clean(cols[7])
    identity = ""
    if id_a or id_b:
        identity = f"identity_a: {id_a or '-'}, identity_b: {id_b or '-'}"
    return (wheat_a, wheat_b, sub_a, sub_b, edges, rice_pair, identity)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tsv", required=True, help="poppin_wheat_interactions.FINAL.tsv")
    ap.add_argument("--dry-run", action="store_true", help="count rows only, no writes")
    ap.add_argument("--password", help="MySQL password (or export DB_PASSWORD)")
    args = ap.parse_args()

    password = args.password or DB_PASSWORD
    if not password:
        ap.error("--password is required (or export DB_PASSWORD)")
    if not os.path.isfile(args.tsv):
        ap.error(f"TSV not found: {args.tsv}")

    total = inserted = skipped = 0
    conn = None
    cur = None
    if not args.dry_run:
        conn = pymysql.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER, password=password,
            database=DB_NAME, charset="utf8mb4", autocommit=False,
            cursorclass=DictCursor,
        )
        cur = conn.cursor()
        cur.execute(CREATE_SQL)
        cur.execute(f"TRUNCATE TABLE `{TABLE}`")
        print(f"table {DB_NAME}.{TABLE} ready (truncated)")

    batch: list[tuple] = []
    with open(args.tsv, encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.reader(fh, delimiter="\t")
        next(reader, None)  # header
        for cols in reader:
            total += 1
            row = parse_row(cols)
            if row is None:
                skipped += 1
                continue
            if args.dry_run:
                continue
            batch.append(row)
            if len(batch) >= BATCH:
                cur.executemany(INSERT_SQL, batch)
                inserted += len(batch)
                batch.clear()
                print(f"  inserted {inserted:,}", flush=True)
    if not args.dry_run:
        if batch:
            cur.executemany(INSERT_SQL, batch)
            inserted += len(batch)
        conn.commit()
        cur.execute(f"SELECT COUNT(*) AS n FROM `{TABLE}`")
        db_count = cur.fetchone()["n"]
        conn.close()
        print(f"\nTSV rows: {total:,}  inserted: {inserted:,}  skipped: {skipped:,}")
        print(f"MySQL rows: {db_count:,}")
        print("MATCH" if db_count == inserted else "MISMATCH — check the table")
    else:
        print(f"dry run: TSV rows {total:,}, would insert {total - skipped:,}, "
              f"skipped {skipped:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
