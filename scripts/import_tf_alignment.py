#!/usr/bin/env python3
"""Import iTAK TF domain alignments and classifications into MySQL.

Each iTAK job writes one output folder under ``/var/www/html/TF/data``::

    P926441958164_output/    (and P994821431338_output, ... more later)
        tf_alignment.txt
        tf_classification.txt

Source files (tab-separated, no header)::

    tf_alignment.txt      gene  pfam  query_start  query_end  hit_start  hit_end
                          align_query_end  -  align_hit_end  score  evalue
                          description  protein_length
    tf_classification.txt gene  family  type(TF/TR)  hierarchy

The three middle columns of ``tf_alignment.txt`` are what iTAK's
``online_display_align.cgi`` prints in the "Alignment:" block
(``Query:<end>`` / ``Align:`` / ``Hit :<end>``); the sample files leave the
sequence strings out, so only the end coordinates are kept.

Rows keep iTAK's transcript-level gene ID verbatim (``TraesCS2A02G116100.1``).
The API looks a gene up by ``gene_id = X OR gene_id LIKE 'X.%'`` so every
transcript suffix of a gene is returned together.  Each row also records the
``source`` folder name, so adding a new job folder never overwrites an older
one: re-importing a folder replaces only that folder's rows.

Run on the server (creating the database/table needs more than the read-only
app account)::

    # every subfolder of /var/www/html/TF/data that has tf_alignment.txt
    DB_USER=root DB_PASSWORD='...' python3 scripts/import_tf_alignment.py

    # one or two specific job folders
    DB_USER=root DB_PASSWORD='...' python3 scripts/import_tf_alignment.py \\
        --dir /var/www/html/TF/data/P926441958164_output \\
        --dir /var/www/html/TF/data/P994821431338_output

    # preview without touching MySQL
    python3 scripts/import_tf_alignment.py --dry-run

    # rebuild both tables from scratch (drops everything first)
    DB_USER=root DB_PASSWORD='...' python3 scripts/import_tf_alignment.py --recreate
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import pymysql
except ImportError:
    sys.exit("pymysql is required: pip install pymysql")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "wheatomics_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_TF", "wheatTFdb")
BATCH = 5000
DEFAULT_ROOT = "/var/www/html/TF/data"

ALIGN_TABLE = "tf_alignment"
CLASS_TABLE = "tf_classification"
GENOME_TABLE = "tf_genomes"

ALIGN_DDL = f"""
CREATE TABLE IF NOT EXISTS `{ALIGN_TABLE}` (
  `id`              bigint unsigned NOT NULL AUTO_INCREMENT,
  `source`          varchar(64)  NOT NULL,
  `genome`          varchar(80)  NOT NULL DEFAULT '',
  `gene_id`         varchar(120) NOT NULL,
  `pfam`            varchar(80)  NOT NULL DEFAULT '',
  `query_start`     int DEFAULT NULL,
  `query_end`       int DEFAULT NULL,
  `hit_start`       int DEFAULT NULL,
  `hit_end`         int DEFAULT NULL,
  `align_query_end` int DEFAULT NULL,
  `align_hit_end`   int DEFAULT NULL,
  `score`           double DEFAULT NULL,
  `evalue`          varchar(40) DEFAULT NULL,
  `description`     text,
  `protein_length`  int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_gene` (`gene_id`),
  KEY `idx_source` (`source`),
  KEY `idx_genome` (`genome`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

CLASS_DDL = f"""
CREATE TABLE IF NOT EXISTS `{CLASS_TABLE}` (
  `source`    varchar(64)  NOT NULL,
  `genome`    varchar(80)  NOT NULL DEFAULT '',
  `gene_id`   varchar(120) NOT NULL,
  `family`    varchar(120) DEFAULT NULL,
  `tf_type`   varchar(20)  DEFAULT NULL,
  `hierarchy` varchar(200) DEFAULT NULL,
  PRIMARY KEY (`source`,`gene_id`),
  KEY `idx_gene` (`gene_id`),
  KEY `idx_genome` (`genome`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

GENOME_DDL = f"""
CREATE TABLE IF NOT EXISTS `{GENOME_TABLE}` (
  `genome`       varchar(80)  NOT NULL,
  `label`        varchar(120) DEFAULT NULL,
  `genes`        int DEFAULT NULL,
  `example_gene` varchar(120) DEFAULT NULL,
  PRIMARY KEY (`genome`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

ALIGN_INSERT = (
    f"INSERT INTO `{ALIGN_TABLE}` (`source`,`genome`,`gene_id`,`pfam`,"
    "`query_start`,`query_end`,`hit_start`,`hit_end`,`align_query_end`,"
    "`align_hit_end`,`score`,`evalue`,`description`,`protein_length`) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

CLASS_INSERT = (
    f"INSERT INTO `{CLASS_TABLE}` (`source`,`genome`,`gene_id`,`family`,"
    "`tf_type`,`hierarchy`) VALUES (%s,%s,%s,%s,%s,%s)"
)


def _int(value: str):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float(value: str):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_alignment(line: str):
    """Return one alignment row, or None for a header/blank/short line.

    Score/e-value/description/length are read from the right so a description
    that happens to contain tabs cannot shift the coordinates.
    """
    fields = line.rstrip("\r\n").split("\t")
    if len(fields) < 10:
        return None
    gene = fields[0].strip()
    if not gene or gene.lower() in ("gene", "gene_id", "protein", "protein_id"):
        return None
    align_query_end = _int(fields[6]) if len(fields) >= 13 else None
    align_hit_end = _int(fields[8]) if len(fields) >= 13 else None
    row = (
        gene,
        fields[1].strip() or None,
        _int(fields[2]),
        _int(fields[3]),
        _int(fields[4]),
        _int(fields[5]),
        align_query_end,
        align_hit_end,
        _float(fields[-4]),
        fields[-3].strip() or None,
        fields[-2].strip() or None,
        _int(fields[-1]),
    )
    if row[2] is None and row[4] is None:
        return None
    return row


def parse_classification(line: str):
    fields = line.rstrip("\r\n").split("\t")
    if len(fields) < 2:
        return None
    gene = fields[0].strip()
    if not gene or gene.lower() in ("gene", "gene_id", "protein", "protein_id"):
        return None
    family = fields[1].strip() or None
    tf_type = (fields[2].strip() or None) if len(fields) > 2 else None
    hierarchy = (fields[3].strip() or None) if len(fields) > 3 else None
    return (gene, family, tf_type, hierarchy)


def stream(path: Path, parser):
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = parser(line)
            if row is not None:
                yield row


def discover(root: Path) -> list[Path]:
    """Every immediate subfolder of ``root`` that carries tf_alignment.txt."""
    if not root.is_dir():
        return []
    return [p for p in sorted(root.iterdir())
            if p.is_dir() and (p / "tf_alignment.txt").is_file()]


def genome_of(folder: Path) -> str:
    """Genome key from the job folder: ``itak_AABBDD_Abo_output`` -> ``AABBDD_Abo``."""
    name = folder.name
    if name.startswith("itak_"):
        name = name[5:]
    if name.endswith("_output"):
        name = name[:-7]
    return name or folder.name


def table_columns(cur, table: str) -> set[str]:
    cur.execute(f"SHOW COLUMNS FROM `{table}`")
    return {row[0] for row in cur.fetchall()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=DEFAULT_ROOT,
                    help=f"folder holding the iTAK job subfolders (default: {DEFAULT_ROOT})")
    ap.add_argument("--dir", action="append", dest="dirs", metavar="PATH",
                    help="job output folder (repeatable); default: every subfolder of "
                         "--root that contains tf_alignment.txt")
    ap.add_argument("--db", default=DB_NAME)
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--genome", help="genome key for every folder in this run "
                                     "(default: derived from the folder name)")
    ap.add_argument("--recreate", action="store_true",
                    help="drop both tables and rebuild them before importing")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--password", help="MySQL password (or export DB_PASSWORD)")
    args = ap.parse_args()

    if args.dirs:
        folders = [Path(p) for p in args.dirs]
    else:
        folders = discover(Path(args.root))
    missing = [p for p in folders if not (p / "tf_alignment.txt").is_file()]
    if missing:
        ap.error("tf_alignment.txt not found in: " + ", ".join(str(p) for p in missing))
    if not folders:
        ap.error(f"no job folders found under {args.root} (or pass --dir)")

    password = args.password or DB_PASSWORD
    if not args.dry_run and not password:
        ap.error("--password is required (or export DB_PASSWORD)")

    print(f"{len(folders)} job folder(s):")
    for folder in folders:
        print(f"  - {folder}")

    conn = cur = None
    if not args.dry_run:
        conn = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER,
                               password=password, charset="utf8mb4",
                               autocommit=False)
        cur = conn.cursor()
        try:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{args.db}` "
                        "DEFAULT CHARACTER SET utf8mb4")
            cur.execute(f"USE `{args.db}`")
            if args.recreate:
                cur.execute(f"DROP TABLE IF EXISTS `{ALIGN_TABLE}`")
                cur.execute(f"DROP TABLE IF EXISTS `{CLASS_TABLE}`")
                cur.execute(f"DROP TABLE IF EXISTS `{GENOME_TABLE}`")
                print(f"{ALIGN_TABLE}, {CLASS_TABLE} and {GENOME_TABLE} dropped")
            cur.execute(ALIGN_DDL)
            cur.execute(CLASS_DDL)
            cur.execute(GENOME_DDL)
        except pymysql.err.OperationalError as exc:
            code = exc.args[0] if exc.args else None
            conn.close()
            if code in (1044, 1045, 1142):
                sys.exit(f"MySQL denied DDL to '{DB_USER}' ({exc.args[1]}).\n"
                         "Run this once with a privileged account, e.g.:\n"
                         f"  DB_USER=root DB_PASSWORD='...' python3 {__file__}")
            raise

        for table in (ALIGN_TABLE, CLASS_TABLE):
            cols = table_columns(cur, table)
            missing_cols = [c for c in ("source", "genome") if c not in cols]
            if missing_cols:
                conn.close()
                sys.exit(f"`{table}` exists with the old schema "
                         f"(missing {', '.join(missing_cols)}).\n"
                         f"Re-run with --recreate to rebuild the tables.")

    total_align = total_class = 0
    summary = []
    for folder in folders:
        source = folder.name
        genome = args.genome or genome_of(folder)
        if not args.dry_run:
            cur.execute(f"DELETE FROM `{ALIGN_TABLE}` WHERE source=%s", (source,))
            cur.execute(f"DELETE FROM `{CLASS_TABLE}` WHERE source=%s", (source,))

        n_align = n_class = 0
        batch = []
        for row in stream(folder / "tf_alignment.txt", parse_alignment):
            n_align += 1
            if args.dry_run:
                continue
            batch.append((source, genome, *row))
            if len(batch) >= args.batch:
                cur.executemany(ALIGN_INSERT, batch)
                batch.clear()
        if batch:
            cur.executemany(ALIGN_INSERT, batch)

        class_file = folder / "tf_classification.txt"
        if class_file.is_file():
            seen = set()
            batch = []
            for row in stream(class_file, parse_classification):
                if row[0] in seen:
                    continue
                seen.add(row[0])
                n_class += 1
                if args.dry_run:
                    continue
                batch.append((source, genome, *row))
                if len(batch) >= args.batch:
                    cur.executemany(CLASS_INSERT, batch)
                    batch.clear()
            if batch:
                cur.executemany(CLASS_INSERT, batch)

        if not args.dry_run:
            conn.commit()
        summary.append((source, genome, n_align, n_class))
        total_align += n_align
        total_class += n_class
        print(f"  {source} [{genome}]: {n_align:,} alignment rows, "
              f"{n_class:,} classifications", flush=True)

    if args.dry_run:
        print(f"\ndry run: would import {total_align:,} alignment rows and "
              f"{total_class:,} classifications from {len(folders)} folder(s), "
              "nothing written")
        return 0

    cur.execute(f"SELECT source,COUNT(*) FROM `{ALIGN_TABLE}` GROUP BY source ORDER BY source")
    counts = {row[0]: row[1] for row in cur.fetchall()}
    ok = True
    print("\nMySQL check:")
    for source, genome, n_align, _ in summary:
        got = counts.get(source, 0)
        state = "MATCH" if got == n_align else "MISMATCH"
        ok &= got == n_align
        print(f"  {source} [{genome}]: {got:,} rows ({state})")

    # Refresh the genome catalogue the page's dropdown reads. Existing labels
    # are preserved; stale genomes (no rows left) are removed.
    cur.execute(
        f"INSERT INTO `{GENOME_TABLE}` (genome,label,genes,example_gene) "
        f"SELECT genome, genome, COUNT(DISTINCT gene_id), MIN(gene_id) "
        f"FROM `{ALIGN_TABLE}` WHERE genome <> '' GROUP BY genome "
        "ON DUPLICATE KEY UPDATE genes=VALUES(genes), example_gene=VALUES(example_gene)"
    )
    cur.execute(
        f"DELETE FROM `{GENOME_TABLE}` WHERE genome NOT IN "
        f"(SELECT genome FROM `{ALIGN_TABLE}`)"
    )
    conn.commit()
    cur.execute(f"SELECT COUNT(*), COALESCE(SUM(genes),0) FROM `{GENOME_TABLE}`")
    n_genomes, n_genes = cur.fetchone()
    print(f"genomes in {GENOME_TABLE}: {n_genomes:,} ({n_genes:,} distinct genes)")

    cur.execute(f"SELECT COUNT(*) FROM `{ALIGN_TABLE}`")
    print(f"total alignment rows: {cur.fetchone()[0]:,}")
    conn.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
