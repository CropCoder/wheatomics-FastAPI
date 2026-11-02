#!/usr/bin/env python3
"""Import the eggNOG/STRING-matched PoppIn pairs into wheatPPIdb.PPI_poppin.

Source (TSV, one header row):

    WheatID1  WheatID2  eggNOGID1  eggNOGID2  Annotation1  Annotation2
    example_rice_pair  Rice_STRING_score  Rice_experimental_score

The wheatPPI router discovers the first eight columns *by position*, so the
table keeps that layout and appends the two optional scores:

    0 Nameid  1 WheatID1  2 WheatID2  3 ID1(eggNOG1)  4 ID2(eggNOG2)
    5 Score(Rice_STRING_score)  6 Annotation1  7 Annotation2
    8 experimental(Rice_experimental_score)  9 rice_pair(example_rice_pair)

Gene IDs are stored exactly as supplied (no transcript suffix), which is how
this dataset is keyed.

Run on the server (the recreate step needs DROP/CREATE, so use a privileged
account; the app account has SELECT only):

    python3 scripts/import_ppi_poppin.py --tsv /path/WheatPPI_eggNOG_STRING_matched_simple.tsv --dry-run
    DB_USER=root DB_PASSWORD='...' python3 scripts/import_ppi_poppin.py \
        --tsv /path/WheatPPI_eggNOG_STRING_matched_simple.tsv
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
  `Nameid`       int NOT NULL AUTO_INCREMENT,
  `WheatID1`     varchar(200) NOT NULL,
  `WheatID2`     varchar(200) NOT NULL,
  `ID1`          varchar(50)  DEFAULT NULL,
  `ID2`          varchar(50)  DEFAULT NULL,
  `Score`        double       DEFAULT NULL,
  `Annotation1`  text,
  `Annotation2`  text,
  `experimental` double       DEFAULT NULL,
  `rice_pair`    varchar(200) DEFAULT NULL,
  PRIMARY KEY (`Nameid`),
  KEY `idx_w1` (`WheatID1`(100)),
  KEY `idx_w2` (`WheatID2`(100))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

INSERT_SQL = (
    f"INSERT INTO `{TABLE}` "
    "(`WheatID1`,`WheatID2`,`ID1`,`ID2`,`Score`,`Annotation1`,`Annotation2`,"
    "`experimental`,`rice_pair`) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

_NULL = {"", "na", "nan", "none", "null", "-"}

# Header keyword -> logical field (matched case-insensitively).
HEADER_MAP = {
    "wheatid1": "w1",
    "wheatid2": "w2",
    "eggnogid1": "e1",
    "eggnogid2": "e2",
    "annotation1": "a1",
    "annotation2": "a2",
    "example_rice_pair": "rice",
    "rice_string_score": "string",
    "rice_experimental_score": "exp",
}
REQUIRED = ("w1", "w2")


def _clean(v: str) -> str:
    v = (v or "").strip()
    return "" if v.lower() in _NULL else v


def _num(v: str):
    v = _clean(v)
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _indexes(header: list[str]) -> dict:
    idx = {}
    for i, name in enumerate(header):
        key = HEADER_MAP.get((name or "").strip().lower())
        if key and key not in idx:
            idx[key] = i
    return idx


def parse_row(cols: list[str], idx: dict):
    def get(key: str) -> str:
        i = idx.get(key)
        return _clean(cols[i]) if i is not None and i < len(cols) else ""

    w1, w2 = get("w1"), get("w2")
    if not w1 or not w2:
        return None
    return (
        w1, w2,
        get("e1") or None,
        get("e2") or None,
        _num(get("string")),
        get("a1") or None,
        get("a2") or None,
        _num(get("exp")),
        get("rice") or None,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tsv", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--password", help="MySQL password (or export DB_PASSWORD)")
    args = ap.parse_args()

    password = args.password or DB_PASSWORD
    if not args.dry_run and not password:
        ap.error("--password is required (or export DB_PASSWORD)")
    if not os.path.isfile(args.tsv):
        ap.error(f"TSV not found: {args.tsv}")

    total = inserted = skipped = 0
    conn = cur = None
    if not args.dry_run:
        conn = pymysql.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER, password=password,
            database=DB_NAME, charset="utf8mb4", autocommit=False,
            cursorclass=DictCursor,
        )
        cur = conn.cursor()
        # The schema changed (rice_pair / experimental were added), so recreate
        # rather than reuse an older table; the TSV is the source of truth.
        try:
            cur.execute(f"DROP TABLE IF EXISTS `{TABLE}`")
            cur.execute(CREATE_SQL)
        except pymysql.err.OperationalError as exc:
            code = exc.args[0] if exc.args else None
            conn.close()
            if code in (1044, 1142):     # access denied for database / table DDL
                sys.exit(
                    f"MySQL denied DDL to '{DB_USER}' ({exc.args[1]}).\n"
                    "Recreating PPI_poppin needs DROP + CREATE, so run this once\n"
                    "with a privileged account, e.g.:\n"
                    f"  DB_USER=root DB_PASSWORD='...' python3 {__file__} --tsv {args.tsv}"
                )
            raise
        print(f"table {DB_NAME}.{TABLE} recreated")

    batch: list[tuple] = []
    with open(args.tsv, encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.reader(fh, delimiter="\t")
        header = next(reader, None) or []
        idx = _indexes(header)
        print(f"header: {header}")
        print(f"matched: {sorted(idx)}")
        missing = [k for k in REQUIRED if k not in idx]
        if missing:
            ap.error(f"cannot locate columns for {missing}")
        for cols in reader:
            total += 1
            row = parse_row(cols, idx)
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
        print(f"MySQL rows: {db_count:,}  ({'MATCH' if db_count == inserted else 'MISMATCH'})")
    else:
        print(f"dry run: TSV rows {total:,}, would insert {total - skipped:,}, "
              f"skipped {skipped:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
