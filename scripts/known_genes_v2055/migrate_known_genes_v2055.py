#!/usr/bin/env python3
"""Migrate KnownGene data from the legacy 520-row table to the curated v2056 list.

Companion to:
  - scripts/known_genes_v2055/extract.py            (workbook -> JSONL)
  - scripts/sql/known_genes_v2055_ddl.sql           (root: ALTER + backup/staging tables)

Phases
------
prepare   read-only: load old rows from ``cloned_gene_tbl``, map old clone_ids onto
          the new JSONL rows (v1/v2 -> v3 ID resolution via Genehub_DB) and write
          ``clone_id_mapping.csv`` / ``unmatched_old.csv`` / ``unmatched_new.csv``.
data      write: load JSONL into the staging table, validate it with STRICT typing,
          then in one transaction ``DELETE FROM cloned_gene_tbl`` +
          ``INSERT ... SELECT FROM staging`` (never TRUNCATE: no privilege + implicit commit).
verify    read-only: post-import assertions (counts / fill rates / mapping coverage).
rollback  write: ``DELETE FROM cloned_gene_tbl`` + restore the 16 legacy columns from
          ``cloned_gene_tbl_backup_YYYYMMDD``.

All DB access uses the application account (``settings.DB_USER``); the DDL phase
(ALTER + backup/staging tables) must be executed once by MySQL root with the SQL
file first.  See docs/known_genes/backend_investigation.md §5.

Examples
--------
    # read-only mapping report (no writes)
    python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py --phase prepare

    # dry-run of the data phase (prints the plan, no writes)
    python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py --phase data --dry-run

    # actual replacement (single transaction)
    python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py --phase data --commit

    # post-import assertions
    python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py --phase verify

    # rollback if needed
    python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py --phase rollback --commit
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, OrderedDict

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:  # pragma: no cover
    sys.exit("pymysql is required")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.core.config import settings  # noqa: E402

DEFAULT_JSONL = os.path.join(REPO_ROOT, "scripts", "known_genes_v2055", "out", "known_genes_v2056.jsonl")
DEFAULT_REPORT_DIR = os.path.join(REPO_ROOT, "scripts", "known_genes_v2055", "out", "migration")
DEFAULT_DATE_TAG = "20261028"

# target table column order (used for SELECT/INSERT) — physical order is irrelevant
TARGET_INSERT_COLUMNS = [
    "clone_id", "gene_id", "reference_genome_id", "gene_name", "gene_species", "chrom_pos",
    "chromosome", "gene_phenotype", "key_result", "function_description", "protein_family",
    "cloning_method", "cloning_method_description", "validation_method", "research_strategy",
    "functional_category", "paper_title", "paper_doi", "publication_year", "publication_years",
    "species_primary", "author", "author_mail", "submission_date",
]

# legacy (pre-migration) columns restored by rollback
LEGACY_COLUMNS = [
    "clone_id", "gene_id", "gene_name", "chrom_pos", "gene_phenotype", "gene_species",
    "paper_title", "paper_doi", "key_result", "author", "author_mail", "submission_date",
    "publication_year", "function_description", "cloning_method", "cloning_method_description",
]

# gene_id / gene_name column swap seen in the legacy table (verified 2026-10-28)
SWAPPED_LEGACY_ROWS = {28: ("TraesCS4D02G326900", "TaBot1-4D"), 29: ("TraesCS4B02G330000", "TaBot1-4B")}

ID_TOKEN_SPLIT_RE = re.compile(r"[/;,|\s]+")
YEAR_RE = re.compile(r"^\d{4}$")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def norm_name(value: str) -> str:
    """Casefold + strip punctuation/whitespace, same intent as the scan script."""
    return re.sub(r"[.\-_\s'’]+", "", str(value or "").casefold())


def split_tokens(value: str) -> list[str]:
    return [t for t in ID_TOKEN_SPLIT_RE.split(str(value or "")) if t]


def split_hash(value: str) -> list[str]:
    return [p.strip() for p in str(value or "").split("###") if p.strip()]


def parse_chromosome(pos: str) -> str:
    """Chromosome token from either ChromPos format (legacy or curated)."""
    m = re.search(r"chr\s*([0-9]+[A-Za-z]{0,2})", str(pos or ""), re.IGNORECASE)
    if m:
        token = m.group(1)
        if re.search(r"[A-Za-z]", token):
            return token.upper()
        return "chr" + token
    m = re.search(r"\b([0-9]+[A-Za-z]{0,2})\s*:", str(pos or ""))
    if m:
        token = m.group(1)
        return token.upper() if re.search(r"[A-Za-z]", token) else token
    return ""


def connect(db: str | None = None):
    return pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=db or settings.DB_CLONED_GENE,
        charset="utf8mb4",
        cursorclass=DictCursor,
    )


def load_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_csv(path: str, header: list[str], rows: list[list]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# prepare: clone_id mapping
# ---------------------------------------------------------------------------

def build_genehub_mapping(old_ids: set[str]) -> dict[str, str]:
    """Map legacy IWGSC v1/v2 ids to v3 ids using Genehub_DB.GenePageIWGSCv1_table."""
    if not old_ids:
        return {}
    mapping: dict[str, str] = {}
    conn = connect(db="Genehub_DB")
    try:
        cur = conn.cursor()
        ids = sorted(old_ids)
        for i in range(0, len(ids), 200):
            chunk = ids[i:i + 200]
            ph = ",".join(["%s"] * len(chunk))
            cur.execute(
                "SELECT GeneIDv1, GeneIDv2, GeneIDv3 FROM GenePageIWGSCv1_table "
                f"WHERE GeneIDv2 IN ({ph}) OR GeneIDv1 IN ({ph})",
                chunk + chunk,
            )
            for row in cur.fetchall():
                v3 = row.get("GeneIDv3")
                if not v3:
                    continue
                for key in ("GeneIDv1", "GeneIDv2"):
                    token = row.get(key)
                    if token and token in old_ids:
                        mapping[token] = v3
    finally:
        conn.close()
    return mapping


def compute_mapping(old_rows: list[dict], new_rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (assignments, unmatched_old, unmatched_new).

    Greedy one-to-one mapping. Tier order:
      T1  legacy gene_id (raw or token) == new reference_genome_id
      T2  legacy gene_id mapped v1/v2 -> v3 == new reference_genome_id
      T3  legacy gene_name normalised == new gene_name normalised
      T4  shared DOI token between legacy paper_doi and new paper_doi
    """
    # fix known swapped gene_id/gene_name rows before indexing
    corrected = []
    for row in old_rows:
        row = dict(row)
        cid = int(row["clone_id"])
        if cid in SWAPPED_LEGACY_ROWS:
            expected_id, expected_name = SWAPPED_LEGACY_ROWS[cid]
            if str(row.get("gene_name")) == expected_id and str(row.get("gene_id")) == expected_name:
                row["gene_id"], row["gene_name"] = row["gene_name"], row["gene_id"]
                row["_swap_fixed"] = True
        corrected.append(row)

    old_ids: set[str] = set()
    for row in corrected:
        old_ids.update(split_tokens(row.get("gene_id")))
        old_ids.add(str(row.get("gene_id") or ""))
    old_ids.discard("")
    genehub_map = build_genehub_mapping(old_ids)

    new_by_ref: dict[str, list[int]] = {}
    new_by_name: dict[str, list[int]] = {}
    new_by_name_chrom: dict[tuple[str, str], list[int]] = {}
    new_by_doi: dict[str, list[int]] = {}
    for i, rec in enumerate(new_rows):
        for key in {rec.get("reference_genome_id"), rec.get("gene_id")}:
            if key:
                new_by_ref.setdefault(str(key), []).append(i)
        nname = norm_name(rec.get("gene_name"))
        new_by_name.setdefault(nname, []).append(i)
        new_by_name_chrom.setdefault((nname, str(rec.get("chromosome") or "")), []).append(i)
        for doi in split_hash(rec.get("paper_doi")):
            new_by_doi.setdefault(doi.strip().lower(), []).append(i)

    used: set[int] = set()
    assignments: list[dict] = []

    def take(candidates: list[int]) -> int | None:
        for i in candidates:
            if i not in used:
                return i
        return None

    for row in corrected:
        gid = str(row.get("gene_id") or "").strip()
        gname = str(row.get("gene_name") or "").strip()
        candidates: list[tuple[str, int]] = []

        ids_to_try = [gid] + split_tokens(gid)
        for token in dict.fromkeys(ids_to_try):
            if token in new_by_ref:
                n = take(new_by_ref[token])
                if n is not None:
                    candidates.append(("T1_id" if token == gid else "T1_id_token", n))
                    break
        if not candidates:
            mapped = {genehub_map.get(t) for t in ids_to_try} - {None}
            for v3 in mapped:
                if v3 in new_by_ref:
                    n = take(new_by_ref[v3])
                    if n is not None:
                        candidates.append(("T2_v3", n))
                        break
        if not candidates and norm_name(gname):
            old_chrom = parse_chromosome(row.get("chrom_pos"))
            n = take(new_by_name_chrom.get((norm_name(gname), old_chrom), [])) if old_chrom else None
            if n is not None:
                candidates.append(("T3_name_chrom", n))
            elif not old_chrom:
                # only accept a chromosome-less legacy row for a name-only match;
                # a legacy row with a known chromosome must not be redirected to a
                # different chromosome/species (wrong-link risk > 404 risk, Q3=B)
                n = take(new_by_name.get(norm_name(gname), []))
                if n is not None:
                    candidates.append(("T3_name", n))
        if not candidates:
            for doi in split_tokens(str(row.get("paper_doi") or "")):
                doi = doi.strip().lower()
                if doi in new_by_doi:
                    n = take(new_by_doi[doi])
                    if n is not None:
                        candidates.append(("T4_doi", n))
                        break

        if candidates:
            tier, n = candidates[0]
            used.add(n)
            assignments.append({
                "old_clone_id": int(row["clone_id"]),
                "old_gene_id": gid,
                "old_gene_name": gname,
                "tier": tier,
                "new_index": n,
                "new_row": new_rows[n].get("_row"),
                "new_reference_genome_id": new_rows[n].get("reference_genome_id"),
                "new_gene_id": new_rows[n].get("gene_id"),
                "new_gene_name": new_rows[n].get("gene_name"),
                "old_chrom": parse_chromosome(row.get("chrom_pos")),
                "new_chrom": new_rows[n].get("chromosome"),
                "swap_fixed": bool(row.get("_swap_fixed")),
            })

    unmatched_old = [
        {"clone_id": int(r["clone_id"]), "gene_id": r.get("gene_id"), "gene_name": r.get("gene_name"),
         "paper_doi": r.get("paper_doi"), "reason": "no tier match"}
        for r in corrected if int(r["clone_id"]) not in {a["old_clone_id"] for a in assignments}
    ]
    unmatched_new = [
        {"row": rec.get("_row"), "reference_genome_id": rec.get("reference_genome_id"),
         "gene_id": rec.get("gene_id"), "gene_name": rec.get("gene_name")}
        for i, rec in enumerate(new_rows) if i not in used
    ]
    return assignments, unmatched_old, unmatched_new


def assign_clone_ids(new_rows: list[dict], assignments: list[dict], old_max_id: int) -> list[dict]:
    """Attach clone_id to every new row (inherited where mapped, else next sequential)."""
    inherited = {a["new_index"]: a["old_clone_id"] for a in assignments}
    next_id = old_max_id + 1
    out = []
    for i, rec in enumerate(new_rows):
        rec = dict(rec)
        if i in inherited:
            rec["clone_id"] = inherited[i]
            rec["_tier"] = next(a["tier"] for a in assignments if a["new_index"] == i)
        else:
            rec["clone_id"] = next_id
            rec["_tier"] = "new"
            next_id += 1
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# phases
# ---------------------------------------------------------------------------

def phase_prepare(args) -> int:
    new_rows = load_jsonl(args.jsonl)
    print(f"new rows (JSONL): {len(new_rows)}")
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT clone_id, gene_id, gene_name, paper_doi, chrom_pos FROM cloned_gene_tbl ORDER BY clone_id")
        old_rows = cur.fetchall()
        cur.execute("SELECT MAX(clone_id) AS mx, COUNT(*) AS n FROM cloned_gene_tbl")
        info = cur.fetchone()
    finally:
        conn.close()
    print(f"old rows (DB)   : {len(old_rows)} (max clone_id={info['mx']})")
    old_max_id = int(info["mx"] or 0)

    assignments, unmatched_old, unmatched_new = compute_mapping(old_rows, new_rows)
    tier_counts = Counter(a["tier"] for a in assignments)
    print(f"mapped          : {len(assignments)} / {len(old_rows)} ({100.0 * len(assignments) / max(len(old_rows), 1):.1f}%)")
    print(f"tiers           : {dict(tier_counts)}")
    print(f"unmatched old   : {len(unmatched_old)} (will be dropped)")
    print(f"new rows without legacy id: {len(unmatched_new)} -> assigned clone_id {old_max_id + 1}..{old_max_id + len(unmatched_new)}")

    os.makedirs(args.report_dir, exist_ok=True)
    write_csv(
        os.path.join(args.report_dir, "clone_id_mapping.csv"),
        ["old_clone_id", "old_gene_id", "old_gene_name", "tier", "new_row", "new_reference_genome_id",
         "new_gene_id", "new_gene_name", "old_chrom", "new_chrom", "swap_fixed"],
        [[a["old_clone_id"], a["old_gene_id"], a["old_gene_name"], a["tier"], a["new_row"],
          a["new_reference_genome_id"], a["new_gene_id"], a["new_gene_name"], a["old_chrom"],
          a["new_chrom"], a["swap_fixed"]]
         for a in sorted(assignments, key=lambda x: x["old_clone_id"])],
    )
    write_csv(os.path.join(args.report_dir, "unmatched_old.csv"),
              ["clone_id", "gene_id", "gene_name", "paper_doi", "reason"],
              [[r["clone_id"], r["gene_id"], r["gene_name"], r["paper_doi"], r["reason"]] for r in unmatched_old])
    write_csv(os.path.join(args.report_dir, "unmatched_new.csv"),
              ["row", "reference_genome_id", "gene_id", "gene_name"],
              [[r["row"], r["reference_genome_id"], r["gene_id"], r["gene_name"]] for r in unmatched_new])
    summary = {
        "jsonl": os.path.abspath(args.jsonl),
        "new_rows": len(new_rows),
        "old_rows": len(old_rows),
        "old_max_clone_id": old_max_id,
        "mapped": len(assignments),
        "mapped_pct": round(100.0 * len(assignments) / max(len(old_rows), 1), 2),
        "tiers": dict(tier_counts),
        "unmatched_old": len(unmatched_old),
        "unmatched_new": len(unmatched_new),
        "new_id_first": old_max_id + 1,
        "new_id_last": old_max_id + len(unmatched_new),
        "tables": {"target": "cloned_gene_tbl", "staging": args.staging_table, "backup": args.backup_table},
    }
    with open(os.path.join(args.report_dir, "mapping_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    print(f"report dir      : {args.report_dir}")
    return 0


def phase_data(args) -> int:
    new_rows = load_jsonl(args.jsonl)
    if not os.path.isfile(os.path.join(args.report_dir, "mapping_summary.json")):
        print("ERROR: run --phase prepare first (mapping report missing)", file=sys.stderr)
        return 2
    summary = json.load(open(os.path.join(args.report_dir, "mapping_summary.json"), encoding="utf-8"))
    old_max_id = int(summary["old_max_clone_id"])

    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM cloned_gene_tbl")
        current_n = int(cur.fetchone()["n"])
        cur.execute(
            "SELECT COUNT(*) AS n FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s",
            (args.backup_table,),
        )
        backup_exists = int(cur.fetchone()["n"]) == 1
        if backup_exists:
            cur.execute(f"SELECT COUNT(*) AS n FROM `{args.backup_table}`")
            backup_n = int(cur.fetchone()["n"])
        else:
            backup_n = None
    finally:
        conn.close()

    print(f"target table    : {settings.DB_CLONED_GENE}.cloned_gene_tbl (current {current_n} rows)")
    print(f"backup table    : {args.backup_table} -> {backup_n} rows")
    print(f"staging table   : {args.staging_table}")
    print(f"new rows        : {len(new_rows)} (mapping report: {summary['mapped']} inherited clone_ids, "
          f"{summary['unmatched_new']} new ids starting at {old_max_id + 1})")
    if not backup_exists or backup_n != current_n:
        print("REFUSING: backup table missing or row count != current table. Run the DDL SQL first.", file=sys.stderr)
        return 2
    if args.dry_run:
        print("\n--dry-run: no writes performed. Planned actions:")
        print(f"  1) DELETE FROM `{args.staging_table}`")
        print(f"  2) INSERT {len(new_rows)} rows into `{args.staging_table}`")
        print("  3) validate staging (count / nulls / lengths)")
        print("  4) BEGIN; DELETE FROM cloned_gene_tbl; INSERT ... SELECT FROM staging; COMMIT;")
        return 0
    if not args.commit:
        print("REFUSING: pass --commit to actually replace the data (or --dry-run to inspect).", file=sys.stderr)
        return 2

    # recompute mapping exactly like prepare (deterministic)
    new_rows = load_jsonl(args.jsonl)
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT clone_id, gene_id, gene_name, paper_doi, chrom_pos FROM cloned_gene_tbl ORDER BY clone_id")
        old_rows = cur.fetchall()
    finally:
        conn.close()
    assignments, _, _ = compute_mapping(old_rows, new_rows)
    rows_with_ids = assign_clone_ids(new_rows, assignments, old_max_id)
    assert len(rows_with_ids) == len(new_rows)

    values = []
    for rec in rows_with_ids:
        values.append([rec[c] if c in rec else None for c in TARGET_INSERT_COLUMNS])

    conn = connect()
    try:
        cur = conn.cursor()
        # --- staging ------------------------------------------------------
        cur.execute(f"DELETE FROM `{args.staging_table}`")
        placeholders = ",".join(["%s"] * len(TARGET_INSERT_COLUMNS))
        cols = ",".join(f"`{c}`" for c in TARGET_INSERT_COLUMNS)
        cur.executemany(f"INSERT INTO `{args.staging_table}` ({cols}) VALUES ({placeholders})", values)
        conn.commit()
        cur.execute(f"SELECT COUNT(*) AS n FROM `{args.staging_table}`")
        staged = int(cur.fetchone()["n"])
        print(f"staged rows     : {staged}")
        if staged != len(new_rows):
            raise RuntimeError(f"staging count mismatch: {staged} != {len(new_rows)}")

        # --- validation before swap --------------------------------------
        checks = {
            "required_gene_id": "SELECT COUNT(*) AS n FROM `{t}` WHERE gene_id IS NULL OR gene_id=''",
            "required_ref_id": "SELECT COUNT(*) AS n FROM `{t}` WHERE reference_genome_id IS NULL OR reference_genome_id=''",
            "required_species": "SELECT COUNT(*) AS n FROM `{t}` WHERE species_primary IS NULL OR species_primary=''",
            "required_chrom": "SELECT COUNT(*) AS n FROM `{t}` WHERE chromosome IS NULL OR chromosome=''",
            "required_category": "SELECT COUNT(*) AS n FROM `{t}` WHERE functional_category IS NULL OR functional_category=''",
            "required_strategy": "SELECT COUNT(*) AS n FROM `{t}` WHERE research_strategy IS NULL OR research_strategy=''",
            "dup_clone_id": "SELECT COUNT(*) AS n FROM (SELECT clone_id FROM `{t}` GROUP BY clone_id HAVING COUNT(*)>1) x",
        }
        for name, sql in checks.items():
            cur.execute(sql.format(t=args.staging_table))
            n = int(cur.fetchone()["n"])
            if n:
                raise RuntimeError(f"staging validation failed: {name}={n}")
        print("staging validation: OK (required columns filled, clone_id unique)")

        # --- single-transaction swap -------------------------------------
        conn.begin()
        cur.execute("DELETE FROM cloned_gene_tbl")
        cur.execute(
            f"INSERT INTO cloned_gene_tbl ({cols}) SELECT {cols} FROM `{args.staging_table}`"
        )
        conn.commit()
        cur.execute("SELECT COUNT(*) AS n FROM cloned_gene_tbl")
        final_n = int(cur.fetchone()["n"])
        print(f"replace done    : cloned_gene_tbl = {final_n} rows")
        if final_n != len(new_rows):
            raise RuntimeError(f"post-commit count mismatch: {final_n} != {len(new_rows)}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return 0


VERIFY_SQL = {
    "rows": "SELECT COUNT(*) AS n FROM cloned_gene_tbl",
    "distinct_clone_id": "SELECT COUNT(DISTINCT clone_id) AS n FROM cloned_gene_tbl",
    "max_clone_id": "SELECT MAX(clone_id) AS n FROM cloned_gene_tbl",
    "inherited": "SELECT COUNT(*) AS n FROM cloned_gene_tbl n JOIN `{backup}` b USING (clone_id)",
    "empty_reference_genome_id": "SELECT COUNT(*) AS n FROM cloned_gene_tbl WHERE reference_genome_id IS NULL OR reference_genome_id=''",
    "empty_species_primary": "SELECT COUNT(*) AS n FROM cloned_gene_tbl WHERE species_primary IS NULL OR species_primary=''",
    "empty_chromosome": "SELECT COUNT(*) AS n FROM cloned_gene_tbl WHERE chromosome IS NULL OR chromosome=''",
    "empty_functional_category": "SELECT COUNT(*) AS n FROM cloned_gene_tbl WHERE functional_category IS NULL OR functional_category=''",
    "empty_research_strategy": "SELECT COUNT(*) AS n FROM cloned_gene_tbl WHERE research_strategy IS NULL OR research_strategy=''",
    "hash_preserved": "SELECT COUNT(*) AS n FROM cloned_gene_tbl WHERE key_result LIKE '%#%' OR gene_phenotype LIKE '%#%'",
}


def phase_verify(args) -> int:
    new_rows = load_jsonl(args.jsonl)
    expected = len(new_rows)
    errors = 0
    conn = connect()
    try:
        cur = conn.cursor()
        for name, sql in VERIFY_SQL.items():
            cur.execute(sql.format(backup=args.backup_table))
            n = int(cur.fetchone()["n"])
            print(f"{name:<26}: {n}")
            if name in ("rows", "distinct_clone_id") and n != expected:
                print(f"  ERROR: expected {expected}")
                errors += 1
            if name.startswith("empty_") and n:
                errors += 1
        cur.execute("SELECT species_primary, COUNT(*) AS n FROM cloned_gene_tbl GROUP BY species_primary ORDER BY n DESC")
        species = cur.fetchall()
        print(f"species groups             : {len(species)}")
        cur.execute("SELECT COUNT(DISTINCT chromosome) AS n FROM cloned_gene_tbl")
        print(f"chromosome labels         : {int(cur.fetchone()['n'])}")
        cur.execute("SELECT functional_category, COUNT(*) AS n FROM cloned_gene_tbl GROUP BY functional_category")
        print(f"functional categories     : {[r['functional_category'] for r in cur.fetchall()]}")
        cur.execute("SELECT research_strategy, COUNT(*) AS n FROM cloned_gene_tbl GROUP BY research_strategy")
        print(f"research strategies       : {[r['research_strategy'] for r in cur.fetchall()]}")
    finally:
        conn.close()
    print("VERIFY:", "PASS" if errors == 0 else f"FAIL ({errors} errors)")
    return 0 if errors == 0 else 1


def phase_rollback(args) -> int:
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) AS n FROM `{args.backup_table}`")
        backup_n = int(cur.fetchone()["n"])
        if backup_n <= 0:
            raise RuntimeError(f"backup table {args.backup_table} is empty; refusing rollback")
        print(f"rollback to {args.backup_table} ({backup_n} rows)")
        if args.dry_run:
            print("--dry-run: no writes performed")
            return 0
        if not args.commit:
            print("REFUSING: pass --commit to rollback", file=sys.stderr)
            return 2
        cols = ",".join(f"`{c}`" for c in LEGACY_COLUMNS)
        conn.begin()
        cur.execute("DELETE FROM cloned_gene_tbl")
        cur.execute(f"INSERT INTO cloned_gene_tbl ({cols}) SELECT {cols} FROM `{args.backup_table}`")
        conn.commit()
        cur.execute("SELECT COUNT(*) AS n FROM cloned_gene_tbl")
        print("restored rows:", int(cur.fetchone()["n"]))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", required=True, choices=["prepare", "data", "verify", "rollback"])
    ap.add_argument("--jsonl", default=DEFAULT_JSONL)
    ap.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    ap.add_argument("--staging-table", default=f"cloned_gene_tbl_staging_{DEFAULT_DATE_TAG}")
    ap.add_argument("--backup-table", default=f"cloned_gene_tbl_backup_{DEFAULT_DATE_TAG}")
    ap.add_argument("--commit", action="store_true", help="perform writes (data/rollback phases)")
    ap.add_argument("--dry-run", action="store_true", help="print planned actions without writing")
    args = ap.parse_args()

    if not os.path.isfile(args.jsonl) and args.phase != "rollback":
        sys.exit(f"JSONL not found: {args.jsonl}")

    if args.phase == "prepare":
        return phase_prepare(args)
    if args.phase == "data":
        return phase_data(args)
    if args.phase == "verify":
        return phase_verify(args)
    if args.phase == "rollback":
        return phase_rollback(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
