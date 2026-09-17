#!/usr/bin/env python3
"""Audit project_meta.labels against the real MySQL columns of each expression table.

/api/expression/query pairs labels with values by ARRAY POSITION (zip), never by
name, so project_meta.labels must line up one-to-one with the table's data
columns. Nothing validates that today, and the failure is silent: zip() truncates
to the shorter side, and the response looks normal either way.

This script reads information_schema and re-derives the exact same four lists the
API builds, then reports every project where they disagree:

  n_labels      JSON_LENGTH(project_meta.labels)
  n_data_cols   non-string columns minus id/geneid/IWGSCV1_1_id/name
                (the fallback label list, built by DESCRIBE order)
  n_value_cols  row.keys() minus GeneID/IWGSCV1_1_id/id/ID
                (where the VALUES actually come from)

Read-only. Prints a report; --csv writes the full table for review.

Usage:
  python3 scripts/audit_project_labels.py
  python3 scripts/audit_project_labels.py --csv scripts/output/label_audit_$(date +%F).csv
"""

import argparse
import csv
import os
import re
import sys

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:
    sys.exit("pymysql is required: pip install pymysql")

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 3306
DEFAULT_USER = "wheatomics_user"
DEFAULT_DB = "gene_expression"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Mirrors app/api/routers/expression.py: the gene-ID column is the last
# string column not named "id"; data columns are the non-string ones.
STRING_TYPES = ("varchar", "char", "text")
DATA_COLUMN_EXCLUDE = ("id", "geneid", "iwgscv1_1_id", "name")
VALUE_COLUMN_EXCLUDE = ("GeneID", "IWGSCV1_1_id", "id", "ID")

IDENT_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _dotenv(key):
    """Read KEY from the repo-root .env — the same file Pydantic loads for the app."""
    try:
        with open(os.path.join(REPO_ROOT, ".env"), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() != key:
                    continue
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    return v[1:-1]
                return re.split(r"\s+#", v, 1)[0].strip()
    except OSError:
        return None
    return None


def fetch_columns(cur, table):
    """Column names of `table` in physical order, plus the numeric ones.

    Returns (all_names, string_names, numeric_names) or None if the table is
    absent. Mirrors what DESCRIBE + row.keys() give the API.
    """
    cur.execute(
        "SELECT COLUMN_NAME, DATA_TYPE FROM information_schema.columns "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
        (cur.database, table),
    )
    rows = cur.fetchall()
    if not rows:
        return None
    all_names = [r["COLUMN_NAME"] for r in rows]
    string_names = [r["COLUMN_NAME"] for r in rows
                    if any(t in (r["DATA_TYPE"] or "").lower() for t in STRING_TYPES)]
    numeric_names = [r["COLUMN_NAME"] for r in rows
                     if not any(t in (r["DATA_TYPE"] or "").lower() for t in STRING_TYPES)]
    return all_names, string_names, numeric_names


def audit_one(cur, table_name, labels):
    """Return a verdict dict for one project."""
    cols = fetch_columns(cur, table_name)
    rec = {
        "table_name": table_name,
        "n_labels": len(labels),
        "n_data_cols": "",
        "n_value_cols": "",
        "gene_id_col": "",
        "status": "OK",
        "detail": "",
    }
    if cols is None:
        rec["status"] = "MISSING_TABLE"
        rec["detail"] = "project_meta has a row but the data table does not exist"
        return rec

    all_names, string_names, numeric_names = cols

    # gene-id column: last string column not named "id" (else the literal default)
    gene_id_col = "GeneID"
    for cname in string_names:
        if cname.lower() not in ("id",):
            gene_id_col = cname

    data_cols = [c for c in numeric_names if c.lower() not in DATA_COLUMN_EXCLUDE]
    value_cols = [c for c in all_names if c not in VALUE_COLUMN_EXCLUDE]

    rec["gene_id_col"] = gene_id_col
    rec["n_data_cols"] = len(data_cols)
    rec["n_value_cols"] = len(value_cols)

    if not labels:
        rec["status"] = "NO_LABELS"
        rec["detail"] = "falls back to raw column names of data_cols"
        return rec

    problems = []
    if len(labels) != len(value_cols):
        problems.append("labels=%d vs value_cols=%d" % (len(labels), len(value_cols)))
    if len(data_cols) != len(value_cols):
        problems.append("data_cols=%d vs value_cols=%d (API's two lists disagree)"
                        % (len(data_cols), len(value_cols)))
    dupes = sorted({l for l in labels if labels.count(l) > 1})
    if dupes:
        problems.append("duplicate labels: %s" % ", ".join(dupes))
    if labels == data_cols:
        problems.append("labels are identical to the raw column names")

    if problems:
        rec["status"] = "MISMATCH"
        rec["detail"] = "; ".join(problems)
        rec["_labels"] = labels
        rec["_value_cols"] = value_cols
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default=None, help="MySQL host (default: $DB_HOST, .env, localhost)")
    ap.add_argument("--port", type=int, default=None, help="MySQL port (default: $DB_PORT, .env, 3306)")
    ap.add_argument("--user", default=None, help="MySQL user (default: $DB_USER, .env, wheatomics_user)")
    ap.add_argument("--password", default=None, help="MySQL password (default: $DB_PASSWORD, then .env)")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--csv", default=None, dest="csv_path", help="write the full audit table here")
    ap.add_argument("--show-ok", action="store_true", help="also list projects that passed")
    args = ap.parse_args()

    args.host = args.host or os.environ.get("DB_HOST") or _dotenv("DB_HOST") or DEFAULT_HOST
    args.port = int(args.port or os.environ.get("DB_PORT") or _dotenv("DB_PORT") or DEFAULT_PORT)
    args.user = args.user or os.environ.get("DB_USER") or _dotenv("DB_USER") or DEFAULT_USER
    args.password = args.password or os.environ.get("DB_PASSWORD") or _dotenv("DB_PASSWORD")
    if not args.password:
        ap.error("--password is required (or export DB_PASSWORD, or set it in .env)")

    try:
        conn = pymysql.connect(host=args.host, port=args.port, user=args.user,
                               password=args.password, database=args.db,
                               charset="utf8mb4", cursorclass=DictCursor)
    except Exception as e:
        sys.exit("Cannot connect to MySQL (%s:%s/%s): %s" % (args.host, args.port, args.db, e))

    import json
    records = []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT table_name, group_name, labels FROM project_meta ORDER BY table_name")
            meta_rows = cur.fetchall()

            for row in meta_rows:
                table_name = row["table_name"]
                if not IDENT_RE.match(table_name):
                    records.append({"table_name": table_name, "n_labels": "", "n_data_cols": "",
                                    "n_value_cols": "", "gene_id_col": "", "status": "BAD_NAME",
                                    "detail": "table_name is not a plain identifier; skipped"})
                    continue
                raw = row.get("labels")
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except json.JSONDecodeError:
                        raw = []
                labels = [str(x) for x in (raw or [])]

                rec = audit_one(cur, table_name, labels)
                rec["group"] = row.get("group_name") or ""
                records.append(rec)
    finally:
        conn.close()

    by_status = {}
    for r in records:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    print("=== project_meta.labels audit ===")
    print("projects in project_meta: %d" % len(records))
    for status in sorted(by_status):
        print("  %-14s %d" % (status, by_status[status]))

    label_cols = ["table_name", "group", "n_labels", "n_data_cols", "n_value_cols",
                  "gene_id_col", "status", "detail"]
    flagged = [r for r in records if r["status"] not in ("OK", "NO_LABELS")]
    if args.show_ok:
        flagged = records

    if flagged:
        print("\n=== projects needing attention (%d) ===" % len(flagged))
        for r in flagged:
            print("\n  %s  [%s]" % (r["table_name"], r["status"]))
            print("    labels=%s  data_cols=%s  value_cols=%s  gene_id=%s"
                  % (r["n_labels"], r["n_data_cols"], r["n_value_cols"], r["gene_id_col"]))
            if r["detail"]:
                print("    %s" % r["detail"])
            if r.get("_labels") is not None:
                n = max(len(r["_labels"]), len(r["_value_cols"]))
                print("    %-4s %-34s | %s" % ("#", "project_meta.labels", "table column"))
                for i in range(min(n, 12)):
                    lab = r["_labels"][i] if i < len(r["_labels"]) else "<missing>"
                    col = r["_value_cols"][i] if i < len(r["_value_cols"]) else "<missing>"
                    print("    %-4d %-34s | %s" % (i, lab, col))
                if n > 12:
                    print("    ... %d more" % (n - 12))
                print("    (pairs are positional — check that each label really"
                      " describes the column on its right)")
    else:
        print("\nno label/column mismatches found")

    if args.csv_path:
        os.makedirs(os.path.dirname(os.path.abspath(args.csv_path)), exist_ok=True)
        with open(args.csv_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=label_cols, extrasaction="ignore")
            w.writeheader()
            for r in records:
                w.writerow(r)
        print("\nwritten: %s (%d rows)" % (args.csv_path, len(records)))


if __name__ == "__main__":
    main()
