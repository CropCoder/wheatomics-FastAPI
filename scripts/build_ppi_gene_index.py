#!/usr/bin/env python3
"""Build the normalised gene -> PPI-edge lookup used by /api/ppi/query.

Why
---
``wheatPPIdb.PPI_result`` stores ~2.8M complex-pair rows whose ``WheatID1`` /
``WheatID2`` columns are ``#``-joined *lists* of IWGSC v2 (02G) transcript IDs
(e.g. ``TraesCS1D02G123600.1#TraesCS1A02G122700.1``). MySQL cannot index an
individual ID inside such a list, so the endpoint's ``REGEXP`` scan reads the
whole 1.4 GB table for every request: seconds when the InnoDB buffer pool is
warm and minutes when it is cold, which shows up as intermittent API timeouts.

This script derives a small aggregated index instead:

    wheatPPIdb.ppi_result_gene_index(gene VARCHAR(64) PRIMARY KEY,
                                     nameids MEDIUMTEXT NOT NULL)

``nameids`` is a comma-separated list of ``PPI_result.Nameid`` values for one
gene (base ID, transcript suffix stripped, duplicates collapsed). A query then
becomes one primary-key lookup plus an ``IN`` fetch by ``Nameid``.

Run on the production web node (writes to MySQL; needs the app .env):

    cd /var/www/FastAPI_backend_Port8000
    set -a; . ./.env; set +a
    /home/fei/mambaforge/envs/zjw/bin/python3 scripts/build_ppi_gene_index.py

Options: ``--rebuild`` (drop/recreate + refill), ``--dry-run`` (scan only),
``--limit N`` (smoke test), ``--batch-size``, ``--work-dir``, and
``--user/--password/--password-file`` for a DDL account (the default app user
cannot DROP/TRUNCATE; use e.g. the root credentials from
``/etc/wheatomics/db_ddl.env``).

Rebuild it whenever ``PPI_result`` is re-imported (new PPI upload); the API
falls back to the slow REGEXP scan while the table is missing.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TABLE = "ppi_result_gene_index"
SOURCE = "PPI_result"

_CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS `{TABLE}` (
  `gene` VARCHAR(64) NOT NULL,
  `nameids` MEDIUMTEXT NOT NULL,
  PRIMARY KEY (`gene`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""".strip()

_TRANSCRIPT = re.compile(r"\.\d+$")


def _load_settings():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.core.config import settings  # noqa: PLC0415 - deferred for --help

    return settings


def _password_from_file(path: str) -> str | None:
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() in ("DB_PASS", "DB_PASSWORD", "WHEATOMICS_DDL_PASS"):
                return value.strip().strip("'\"")
    except OSError:
        return None
    return None


def _connect(settings, args):
    """Open the DB with explicit DDL credentials when given (TABLE writes/DROP)."""
    import pymysql  # noqa: PLC0415

    password = args.password or os.environ.get("WHEATOMICS_DDL_PASS") or settings.DB_PASSWORD
    if not password and args.password_file:
        password = _password_from_file(args.password_file) or ""
    user = args.user or os.environ.get("WHEATOMICS_DDL_USER") or settings.DB_USER
    return pymysql.connect(
        host=args.host or settings.DB_HOST,
        port=args.port or settings.DB_PORT,
        user=user,
        password=password,
        database=settings.DB_PPI,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _split_ids(value: str) -> list[str]:
    ids: list[str] = []
    for part in str(value or "").split("#"):
        gene = _TRANSCRIPT.sub("", part.strip())
        if gene and gene not in ids:
            ids.append(gene)
    return ids


def dump_membership(settings, args, work_dir: Path, batch_size: int, limit: int | None) -> Path:
    """Stream PPI_result -> TSV of (gene, nameid) pairs, deduped per row."""
    raw = work_dir / "ppi_membership.tsv"
    rows = 0
    memberships = 0
    cursor_value = 0
    started = time.time()
    with _connect(settings, args) as conn:
        with conn.cursor() as cur:
            while True:
                cur.execute(
                    f"SELECT Nameid, WheatID1, WheatID2 FROM `{SOURCE}` "
                    f"WHERE Nameid > %s ORDER BY Nameid LIMIT %s",
                    (cursor_value, batch_size),
                )
                batch = cur.fetchall()
                if not batch:
                    break
                with raw.open("a", encoding="utf-8", newline="") as fh:
                    for row in batch:
                        cursor_value = int(row["Nameid"])
                        genes: list[str] = []
                        for value in (row.get("WheatID1"), row.get("WheatID2")):
                            for gene in _split_ids(value):
                                if gene not in genes:
                                    genes.append(gene)
                        for gene in genes:
                            fh.write(f"{gene}\t{cursor_value}\n")
                        memberships += len(genes)
                        rows += 1
                if rows % 200_000 < batch_size:
                    elapsed = time.time() - started
                    print(f"  scanned {rows:,} rows / {memberships:,} memberships "
                          f"({elapsed:.0f}s)", flush=True)
                if limit and rows >= limit:
                    break
    print(f"scanned {rows:,} rows, {memberships:,} (gene, edge) memberships "
          f"in {time.time() - started:.0f}s")
    return raw


def sort_dedupe(raw: Path) -> Path:
    """``sort -u`` the raw pairs so the aggregation step is a linear scan."""
    sorted_path = raw.with_name("ppi_membership.sorted.tsv")
    started = time.time()
    print("sorting membership pairs (external sort, may take a few minutes)…", flush=True)
    with sorted_path.open("wb") as out:
        subprocess.run(
            ["sort", "-u", "-T", str(raw.parent), str(raw)],
            stdout=out, check=True,
        )
    print(f"sorted -> {sorted_path} ({sorted_path.stat().st_size / 1e6:.0f} MB, "
          f"{time.time() - started:.0f}s)")
    return sorted_path


def aggregate(sorted_path: Path) -> dict[str, list[int]]:
    """gene -> [nameid, ...] from the sorted pair file."""
    grouped: dict[str, list[int]] = {}
    current = None
    ids: list[int] = []
    with sorted_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            gene, _, nameid = line.rstrip("\n").partition("\t")
            if not gene or not nameid:
                continue
            value = int(nameid)
            if gene != current:
                if current is not None:
                    grouped[current] = ids
                current, ids = gene, [value]
            else:
                ids.append(value)
    if current is not None:
        grouped[current] = ids
    return grouped


def load_index(grouped: dict[str, list[int]], settings, args) -> None:
    started = time.time()
    with _connect(settings, args) as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_SQL)
            cur.execute(f"TRUNCATE TABLE `{TABLE}`")
            sql = f"INSERT INTO `{TABLE}` (gene, nameids) VALUES (%s, %s)"
            batch: list[tuple[str, str]] = []
            for gene, ids in grouped.items():
                batch.append((gene, ",".join(str(i) for i in ids)))
                if len(batch) >= 2000:
                    cur.executemany(sql, batch)
                    batch.clear()
            if batch:
                cur.executemany(sql, batch)
            cur.execute(f"ANALYZE TABLE `{TABLE}`")
    print(f"loaded {len(grouped):,} genes into {TABLE} in {time.time() - started:.0f}s")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--batch-size", type=int, default=50_000,
                        help="rows fetched per batch (default 50000)")
    parser.add_argument("--limit", type=int, help="only scan the first N rows (smoke test)")
    parser.add_argument("--work-dir", type=Path,
                        help="scratch directory for the sorted TSV (default a temp dir)")
    parser.add_argument("--rebuild", action="store_true",
                        help="drop and recreate the index table (default: replace contents)")
    parser.add_argument("--dry-run", action="store_true",
                        help="scan and report only, do not write MySQL")
    parser.add_argument("--host", help="DB host (default: app settings)")
    parser.add_argument("--port", type=int, help="DB port (default: app settings)")
    parser.add_argument("--user", help="DB user with write/DDL rights "
                                       "(default: WHEATOMICS_DDL_USER or app user)")
    parser.add_argument("--password", help="DB password for --user "
                                           "(default: WHEATOMICS_DDL_PASS or app password)")
    parser.add_argument("--password-file",
                        help="read DB_PASS / WHEATOMICS_DDL_PASS from this file")
    args = parser.parse_args()

    settings = _load_settings()
    work_dir = args.work_dir or Path(tempfile.mkdtemp(prefix="ppi_index_"))
    work_dir.mkdir(parents=True, exist_ok=True)
    print(f"work dir: {work_dir}")

    raw = dump_membership(settings, args, work_dir, args.batch_size, args.limit)
    if args.dry_run:
        print("dry-run: nothing written to MySQL")
        return 0
    sorted_path = sort_dedupe(raw)
    grouped = aggregate(sorted_path)
    ids_total = sum(len(ids) for ids in grouped.values())
    print(f"aggregated {ids_total:,} memberships into {len(grouped):,} genes "
          f"(avg {ids_total / max(1, len(grouped)):.1f} edges/gene)")

    if args.rebuild:
        with _connect(settings, args) as conn:
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS `{TABLE}`")
    load_index(grouped, settings, args)
    print("done; the API picks the index up within 5 minutes (availability cache)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
