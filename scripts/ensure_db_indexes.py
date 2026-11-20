#!/usr/bin/env python3
"""Ensure the MySQL indexes the fast-query paths need (idempotent).

Two schema objects are required for the reviewer-facing response times:

1. ``eqtl.wheat`` needs an index on ``Geneid``.  The table has 778k rows and no
   secondary indexes at all; without it every eQTL lookup scans the table.
2. ``wheatPPIdb.ppi_result_gene_index`` is the normalised gene -> PPI-edge map
   read by ``/api/ppi/query`` (see ``scripts/build_ppi_gene_index.py``, which
   fills it).  This script only guarantees the table exists.

Run with a DDL-capable account on the production node::

    export WHEATOMICS_DDL_USER=root
    export WHEATOMICS_DDL_PASS='***'   # or --password-file /etc/wheatomics/db_ddl.env
    python3 scripts/ensure_db_indexes.py            # apply what is missing
    python3 scripts/ensure_db_indexes.py --dry-run  # report only

The statements are DDL: MySQL 5.7 cannot run them inside a transaction, so each
step is reported separately (``[ok]``/``[created]``/``[failed]``).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

INDEX_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS `wheatPPIdb`.`ppi_result_gene_index` (
  `gene` VARCHAR(64) NOT NULL,
  `nameids` MEDIUMTEXT NOT NULL,
  PRIMARY KEY (`gene`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""".strip()

EQTL_INDEX_NAME = "idx_geneid"


def _settings():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.core.config import settings  # noqa: PLC0415

    return settings


def _read_password_file(path: str) -> str | None:
    """Read DB_PASS / DB_PASSWORD from a shell-style env file."""
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() in ("DB_PASS", "DB_PASSWORD"):
                return value.strip().strip("'\"")
    except OSError:
        return None
    return None


def _connect(host: str, port: int, user: str, password: str):
    import pymysql  # noqa: PLC0415 - only needed for this admin script

    return pymysql.connect(host=host, port=port, user=user, password=password,
                           charset="utf8mb4", autocommit=True)


def _has_index(cur, schema: str, table: str, column: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) AS n FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s",
        (schema, table, column),
    )
    row = cur.fetchone()
    return bool(row and row[0])


def _table_exists(cur, schema: str, table: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
        (schema, table),
    )
    row = cur.fetchone()
    return bool(row and row[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=os.environ.get("DB_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DB_PORT", "3306")))
    parser.add_argument("--user", default=os.environ.get("WHEATOMICS_DDL_USER", "root"))
    parser.add_argument("--password", default=os.environ.get("WHEATOMICS_DDL_PASS", ""))
    parser.add_argument("--password-file",
                        help="read DB_PASS/DB_PASSWORD from this file (e.g. /etc/wheatomics/db_ddl.env)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.password and args.password_file:
        args.password = _read_password_file(args.password_file) or ""
    if not args.password:
        print("ERROR: no DDL password (use --password, WHEATOMICS_DDL_PASS or --password-file)")
        return 2

    settings = _settings()
    failures = 0
    try:
        conn = _connect(args.host, args.port, args.user, args.password)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: cannot connect as {args.user}@{args.host}: {exc}")
        return 2

    with conn:
        with conn.cursor() as cur:
            # 1) eqtl.wheat(Geneid)
            if _has_index(cur, "eqtl", "wheat", "Geneid"):
                print("[ok] eqtl.wheat already has an index on Geneid")
            elif args.dry_run:
                print("[dry-run] would create eqtl.wheat index on Geneid")
            else:
                started = time.time()
                try:
                    cur.execute(f"ALTER TABLE `eqtl`.`wheat` "
                                f"ADD INDEX `{EQTL_INDEX_NAME}` (`Geneid`)")
                    print(f"[created] eqtl.wheat index {EQTL_INDEX_NAME} "
                          f"({time.time() - started:.1f}s)")
                except Exception as exc:  # noqa: BLE001
                    failures += 1
                    print(f"[failed] eqtl.wheat index: {exc}")

            # 2) ppi_result_gene_index table
            if _table_exists(cur, settings.DB_PPI, "ppi_result_gene_index"):
                cur.execute(
                    f"SELECT COUNT(*) FROM `{settings.DB_PPI}`.`ppi_result_gene_index`")
                rows = cur.fetchone()[0]
                if rows:
                    print(f"[ok] ppi_result_gene_index exists ({rows:,} genes)")
                else:
                    print("[warn] ppi_result_gene_index is empty — run "
                          "scripts/build_ppi_gene_index.py")
            elif args.dry_run:
                print("[dry-run] would create wheatPPIdb.ppi_result_gene_index")
            else:
                try:
                    cur.execute(INDEX_TABLE_DDL)
                    print("[created] wheatPPIdb.ppi_result_gene_index "
                          "(empty — run scripts/build_ppi_gene_index.py next)")
                except Exception as exc:  # noqa: BLE001
                    failures += 1
                    print(f"[failed] ppi_result_gene_index: {exc}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
