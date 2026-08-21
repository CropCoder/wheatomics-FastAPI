"""Import fangenome_ps_results.csv into the wheat_psp MySQL table.

The CSV has 11 columns:
    seq_id, seq_length, ps_score, is_psp, molphase_score, has_prd,
    error, plaac_llr, plaac_core_score, plaac_papa_prop, plaac_papa_fi

``gene_id`` is derived from ``seq_id`` by stripping the ``-P<number>``
transcript suffix (e.g. PanRefChrChr1A_011243-P1 -> PanRefChrChr1A_011243).
Missing / nan numeric fields are stored as NULL.

Usage:
    python scripts/import_wheat_psp.py /path/to/fangenome_ps_results.csv
"""

from __future__ import annotations

import argparse
import csv
import re

import pymysql

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS wheat_psp (
    id INT AUTO_INCREMENT PRIMARY KEY,
    seq_id VARCHAR(100) NOT NULL,
    gene_id VARCHAR(100) NOT NULL,
    seq_length INT,
    ps_score DOUBLE,
    is_psp TINYINT(1) NOT NULL DEFAULT 0,
    molphase_score DOUBLE,
    has_prd TINYINT(1) NOT NULL DEFAULT 0,
    error VARCHAR(255),
    plaac_llr DOUBLE,
    plaac_core_score DOUBLE,
    plaac_papa_prop DOUBLE,
    plaac_papa_fi DOUBLE,
    INDEX idx_seq_id (seq_id),
    INDEX idx_gene_id (gene_id),
    INDEX idx_is_psp (is_psp),
    INDEX idx_has_prd (has_prd)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

INSERT_SQL = """
INSERT INTO wheat_psp
    (seq_id, gene_id, seq_length, ps_score, is_psp, molphase_score, has_prd,
     error, plaac_llr, plaac_core_score, plaac_papa_prop, plaac_papa_fi)
VALUES
    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

BATCH = 5000


def gene_id(seq_id: str) -> str:
    return re.sub(r"-P\d+$", "", seq_id)


def to_float(v):
    v = (v or "").strip()
    if v in ("", "None", "nan", "NaN"):
        return None
    return float(v)


def to_int(v):
    v = (v or "").strip()
    return int(v) if v else None


def to_bool(v):
    return 1 if str(v).strip().lower() == "true" else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", help="path to fangenome_ps_results.csv")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="wheatomics_user")
    parser.add_argument("--password", default="wheatomics115599")
    parser.add_argument("--database", default="wheat_psp_db")
    args = parser.parse_args()

    conn = pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        charset="utf8mb4",
        autocommit=False,
    )
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{args.database}` DEFAULT CHARACTER SET utf8mb4")
    cur.execute(f"USE `{args.database}`")
    cur.execute(CREATE_TABLE_SQL)
    cur.execute("TRUNCATE TABLE wheat_psp")
    conn.commit()

    batch = []
    count = 0
    with open(args.csv, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = row["seq_id"].strip()
            batch.append((
                sid,
                gene_id(sid),
                to_int(row.get("seq_length", "")),
                to_float(row.get("ps_score", "")),
                to_bool(row.get("is_psp", "")),
                to_float(row.get("molphase_score", "")),
                to_bool(row.get("has_prd", "")),
                row.get("error", "").strip() or None,
                to_float(row.get("plaac_llr", "")),
                to_float(row.get("plaac_core_score", "")),
                to_float(row.get("plaac_papa_prop", "")),
                to_float(row.get("plaac_papa_fi", "")),
            ))
            if len(batch) >= BATCH:
                cur.executemany(INSERT_SQL, batch)
                conn.commit()
                count += len(batch)
                print(f"imported {count} rows", flush=True)
                batch = []

    if batch:
        cur.executemany(INSERT_SQL, batch)
        conn.commit()
        count += len(batch)

    print(f"done: {count} rows total")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
