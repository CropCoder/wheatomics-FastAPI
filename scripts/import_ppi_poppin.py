#!/usr/bin/env python3
"""Import the final PoppIn rice-to-wheat mapped PPI network into PPI_poppin.

Source
------
The final delivery `poppin_wheat_interactions.FINAL.tsv` contains one row per
unique wheat-wheat interaction:

    wheat_a  wheat_b  sub_a  sub_b  n_supporting_edges
    best_identity_a  best_identity_b  example_rice_pair

Construction (from the delivery reports):
- Start from the PoppIn rice PPI network (125,101 edges / 32,350 rice proteins).
- Map rice proteins to wheat A/B/D homoeologs by sequence homology
  (identity >= 60%, query coverage >= 50%) and Foldseek 3Di structural homology
  for copies missing from the sequence-based map.
- Expand each rice edge to wheat copy pairs, then collapse duplicate pairs.
- Final: 49,435 / 125,101 rice edges mapped (39.5%) -> 386,526 unique wheat
  pairs; wheat IDs are IWGSC RefSeq v1.1 (02G) IDs without transcript suffix.

The table is recreated atomically, keeping the previous table as
PPI_poppin_old_<date>. Run with a privileged MySQL account because the app
account has SELECT/INSERT only (no DROP/CREATE):

    MYSQL_PASS=... python3 scripts/import_ppi_poppin.py \
        --tsv /path/to/poppin_wheat_interactions.FINAL.tsv
"""

from __future__ import annotations

import argparse
import csv
import os

import pymysql

DB = os.environ.get("DB_PPI", "wheatPPIdb")
TABLE = "PPI_poppin"
NEW = "PPI_poppin_new"
OLD = os.environ.get("PPI_POPPIN_BACKUP_TABLE", "PPI_poppin_old_20261103")

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS `{NEW}` (
  `Nameid` int NOT NULL AUTO_INCREMENT,
  `WheatID1` varchar(100) NOT NULL,
  `WheatID2` varchar(100) NOT NULL,
  `Subgenome1` varchar(10) DEFAULT NULL,
  `Subgenome2` varchar(10) DEFAULT NULL,
  `SupportingEdges` int NOT NULL DEFAULT 0,
  `Identity1` double DEFAULT NULL,
  `Identity2` double DEFAULT NULL,
  `Rice_pair` varchar(200) DEFAULT NULL,
  PRIMARY KEY (`Nameid`),
  KEY `idx_w1` (`WheatID1`),
  KEY `idx_w2` (`WheatID2`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tsv", required=True)
    ap.add_argument("--batch", type=int, default=5000)
    args = ap.parse_args()
    password = os.environ.get("MYSQL_PASS") or os.environ.get("DB_PASSWORD")
    if not password:
        ap.error("set MYSQL_PASS or DB_PASSWORD")

    conn = pymysql.connect(host="localhost", user=os.environ.get("DB_USER", "root"),
                           password=password, database=DB, charset="utf8mb4",
                           autocommit=False)
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS `{NEW}`")
    cur.execute(CREATE_SQL)

    rows, total, batch = [], 0, []
    with open(args.tsv, encoding="utf-8") as fh:
        reader = csv.reader(fh, delimiter="\t")
        next(reader, None)
        for p in reader:
            if len(p) < 8 or not p[0] or not p[1]:
                continue
            batch.append((p[0], p[1], p[2] or None, p[3] or None,
                          int(float(p[4] or 0)),
                          float(p[5]) if p[5] else None,
                          float(p[6]) if p[6] else None,
                          p[7] or None))
            total += 1
            if len(batch) >= args.batch:
                cur.executemany(
                    f"INSERT INTO `{NEW}` (WheatID1,WheatID2,Subgenome1,Subgenome2,"
                    "SupportingEdges,Identity1,Identity2,Rice_pair) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", batch)
                rows += len(batch); batch.clear()

    if batch:
        cur.executemany(
            f"INSERT INTO `{NEW}` (WheatID1,WheatID2,Subgenome1,Subgenome2,"
            "SupportingEdges,Identity1,Identity2,Rice_pair) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", batch)
        rows += len(batch)
    if rows != total:
        raise SystemExit(f"imported {rows} of {total} rows")

    cur.execute(f"DROP TABLE IF EXISTS `{OLD}`")
    cur.execute(f"RENAME TABLE `{TABLE}` TO `{OLD}`, `{NEW}` TO `{TABLE}`")
    conn.commit()
    cur.execute(f"SELECT COUNT(*) FROM `{TABLE}`")
    print(f"PPI_poppin: {cur.fetchone()[0]:,} rows (backup: {OLD})")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
