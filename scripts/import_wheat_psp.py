"""Import fangenome_ps_results.csv into the wheat_psp MySQL table.

The CSV has 11 columns:
    seq_id, seq_length, ps_score, is_psp, molphase_score, has_prd,
    error, plaac_llr, plaac_core_score, plaac_papa_prop, plaac_papa_fi

``gene_id`` is derived from ``seq_id`` by stripping the ``-P<number>``
transcript suffix (e.g. PanRefChrChr1A_011243-P1 -> PanRefChrChr1A_011243).

``cs_gene_id`` is the Chinese Spring 02G id (e.g. TraesCS1A02G228500) looked
up from a blastp best-hit mapping file (``filtered_best.tsv``):
    query<TAB>subject<TAB>pident<...>
The subject's trailing ``.1`` transcript suffix is stripped.

Usage:
    python scripts/import_wheat_psp.py fangenome_ps_results.csv \
        --mapping filtered_best.tsv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re

import pymysql

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS wheat_psp (
    id INT AUTO_INCREMENT PRIMARY KEY,
    seq_id VARCHAR(100) NOT NULL,
    gene_id VARCHAR(100) NOT NULL,
    cs_gene_id VARCHAR(100) DEFAULT NULL,
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
    INDEX idx_cs_gene (cs_gene_id),
    INDEX idx_is_psp (is_psp),
    INDEX idx_has_prd (has_prd)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

INSERT_SQL = """
INSERT INTO wheat_psp
    (seq_id, gene_id, cs_gene_id, seq_length, ps_score, is_psp, molphase_score,
     has_prd, error, plaac_llr, plaac_core_score, plaac_papa_prop, plaac_papa_fi)
VALUES
    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

BATCH = 5000


def gene_id(seq_id: str) -> str:
    return re.sub(r"-P\d+$", "", seq_id)


def load_mapping(path: str | None) -> dict[str, str]:
    """Read blastp best-hit mapping: query seq_id -> CS gene id (no .1)."""
    mapping: dict[str, str] = {}
    if not path or not os.path.exists(path):
        return mapping
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if not line.strip():
                continue
            cols = line.split("\t")
            if len(cols) < 2:
                continue
            query = cols[0].strip()
            subject = cols[1].strip()
            if query and subject:
                mapping[query] = re.sub(r"\.\d+$", "", subject)
    return mapping


def to_float(v):
    v = (v or "").strip()
    if v in ("", "None", "nan", "NaN"):
        return None
    return float(v)


def to_int(v):
    v = (v or "").strip()
    if not v:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def to_bool(v):
    return 1 if str(v).strip().lower() == "true" else 0


AA_COLS = ["A", "C", "D", "E", "F", "G", "H", "I", "K", "L", "M", "N", "P", "Q", "R", "S", "T", "V", "W", "Y"]

FEATURE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS wheat_psp_feature (
    seq_id VARCHAR(100) PRIMARY KEY,
    sequence LONGTEXT,
    new_molphase DOUBLE,
    length INT,
    idr_percentage DOUBLE,
    pi_pi DOUBLE,
    prion_like DOUBLE,
    lcr_percentage DOUBLE,
    shannon_entropy DOUBLE,
    fcr DOUBLE,
    ncpr DOUBLE,
    kappa DOUBLE,
    omega DOUBLE,
    hydrophobicity DOUBLE,
    ppii_propensity DOUBLE,
    aa_composition TEXT,
    polar DOUBLE,
    hydrophobic DOUBLE,
    aromatic DOUBLE,
    cationic DOUBLE,
    anionic DOUBLE,
    expanding DOUBLE,
    disorder_promoting DOUBLE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

FEATURE_INSERT_SQL = """
INSERT IGNORE INTO wheat_psp_feature
    (seq_id, sequence, new_molphase, length, idr_percentage, pi_pi, prion_like,
     lcr_percentage, shannon_entropy, fcr, ncpr, kappa, omega, hydrophobicity,
     ppii_propensity, aa_composition, polar, hydrophobic, aromatic, cationic,
     anionic, expanding, disorder_promoting)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def import_feature(cur, path: str | None, batch_size: int = BATCH) -> int:
    """Import fangenome.csv (sequence + physicochemical properties)."""
    if not path or not os.path.exists(path):
        print("no feature file, skip", flush=True)
        return 0
    cur.execute(FEATURE_TABLE_SQL)
    cur.execute("TRUNCATE TABLE wheat_psp_feature")
    count = 0
    batch = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = (row.get("id") or "").strip()
            if not sid:
                continue
            aa = {a: to_float(row.get(a, "")) for a in AA_COLS}
            batch.append((
                sid,
                row.get("sequence", ""),
                to_float(row.get("new_molphase", "")),
                to_int(row.get("length", "")),
                to_float(row.get("IDR Percentage", "")),
                to_float(row.get("Pi-Pi Interaction", "")),
                to_float(row.get("Prion like domain", "")),
                to_float(row.get("LCR Percentage", "")),
                to_float(row.get("Shannon Entropy", "")),
                to_float(row.get("FCR", "")),
                to_float(row.get("NCPR", "")),
                to_float(row.get("kappa", "")),
                to_float(row.get("omega", "")),
                to_float(row.get("Hydrophobicity", "")),
                to_float(row.get("PPII Propensity", "")),
                json.dumps(aa),
                to_float(row.get("Polar", "")),
                to_float(row.get("Hydrophobic", "")),
                to_float(row.get("Aromatic", "")),
                to_float(row.get("Cationic", "")),
                to_float(row.get("Anionic", "")),
                to_float(row.get("Expanding", "")),
                to_float(row.get("Disorder Promoting", "")),
            ))
            if len(batch) >= batch_size:
                cur.executemany(FEATURE_INSERT_SQL, batch)
                count += len(batch)
                batch = []
    if batch:
        cur.executemany(FEATURE_INSERT_SQL, batch)
        count += len(batch)
    print(f"feature imported: {count} rows", flush=True)
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", help="path to fangenome_ps_results.csv")
    parser.add_argument("--mapping", help="path to filtered_best.tsv (PanRef -> CS gene id)")
    parser.add_argument("--feature", help="path to fangenome.csv (sequence + physicochemical properties)")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="wheatomics_user")
    parser.add_argument("--password", default=os.environ.get("DB_PASSWORD"),
                        help="DB password (or export DB_PASSWORD)")
    parser.add_argument("--database", default="wheat_psp_db")
    args = parser.parse_args()
    if not args.password:
        parser.error("--password is required (or export DB_PASSWORD)")

    mapping = load_mapping(args.mapping)
    print(f"loaded {len(mapping)} blastp mappings", flush=True)

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

    # 兼容已建表：若缺 cs_gene_id 列则补上
    cur.execute("SHOW COLUMNS FROM wheat_psp LIKE 'cs_gene_id'")
    if not cur.fetchone():
        cur.execute(
            "ALTER TABLE wheat_psp "
            "ADD COLUMN cs_gene_id VARCHAR(100) DEFAULT NULL, "
            "ADD INDEX idx_cs_gene (cs_gene_id)"
        )
        conn.commit()

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
                mapping.get(sid),
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
    import_feature(cur, args.feature)
    conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
