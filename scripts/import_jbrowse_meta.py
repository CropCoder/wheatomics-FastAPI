#!/usr/bin/env python3
"""Import JBrowse dataset/track metadata into the ``jbrowse_meta`` MySQL DB.

Scans the JBrowse data root (default /var/www/html/jbrowse-1.12.3-release)
for per-dataset ``trackList.json`` files and mirrors them into two tables:

  jbrowse_datasets — one row per dataset directory
  jbrowse_tracks   — one row per track, original order preserved

The tables are self-created (CREATE TABLE IF NOT EXISTS), and re-runs are
idempotent: each dataset's rows are replaced (DELETE + INSERT), so a stale
track disappears from the DB instead of lingering.

Run on the server:

    cd /var/www/FastAPI_backend_Port8000
    python3 scripts/import_jbrowse_meta.py                 # everything
    python3 scripts/import_jbrowse_meta.py --dataset Chinese_Spring1.0
    python3 scripts/import_jbrowse_meta.py --dry-run       # parse only

Requires pymysql (--dry-run works without it). The database itself must
already exist — see the deployment SQL in the Layer-1 plan / README.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    import pymysql
except ImportError:
    pymysql = None  # type: ignore[assignment]

# Same defaults as app/core/config.py (Settings).
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "wheatomics_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "wheatomics115599")
DB_NAME = os.environ.get("DB_JBROWSE", "jbrowse_meta")

DATA_ROOT = Path(os.environ.get(
    "JBROWSE_DATA_ROOT", "/var/www/html/jbrowse-1.12.3-release"))


# ---------------------------------------------------------------------------
# Table definitions — keep in sync with app/api/routers/jbrowse.py queries.
# ---------------------------------------------------------------------------
CREATE_DATASETS_SQL = """
CREATE TABLE IF NOT EXISTS jbrowse_datasets (
  id           VARCHAR(128) NOT NULL,
  dataset_id   VARCHAR(255) NULL,
  track_count  INT NOT NULL DEFAULT 0,
  has_names    TINYINT NOT NULL DEFAULT 0,
  names_json   JSON NULL,
  fetched_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                          ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
)
""".strip()

CREATE_TRACKS_SQL = """
CREATE TABLE IF NOT EXISTS jbrowse_tracks (
  dataset      VARCHAR(128) NOT NULL,
  ord          INT NOT NULL,
  track_key    VARCHAR(255) NULL,
  label        VARCHAR(255) NULL,
  track_type   VARCHAR(128) NULL,
  url_template TEXT NULL,
  category     VARCHAR(255) NULL,
  track_json   JSON NOT NULL,
  PRIMARY KEY (dataset, ord),
  KEY idx_tracks_type (track_type),
  KEY idx_tracks_category (category)
)
""".strip()

UPSERT_DATASET_SQL = """
INSERT INTO jbrowse_datasets
  (id, dataset_id, track_count, has_names, names_json)
VALUES
  (%(id)s, %(dataset_id)s, %(track_count)s, %(has_names)s, %(names_json)s)
ON DUPLICATE KEY UPDATE
  dataset_id  = VALUES(dataset_id),
  track_count = VALUES(track_count),
  has_names   = VALUES(has_names),
  names_json  = VALUES(names_json)
""".strip()

INSERT_TRACK_SQL = """
INSERT INTO jbrowse_tracks
  (dataset, ord, track_key, label, track_type, url_template, category, track_json)
VALUES
  (%(dataset)s, %(ord)s, %(track_key)s, %(label)s, %(track_type)s,
   %(url_template)s, %(category)s, %(track_json)s)
""".strip()

DELETE_TRACKS_SQL = "DELETE FROM jbrowse_tracks WHERE dataset = %s"


def ensure_tables(cursor) -> None:
    """Create both tables if missing (idempotent)."""
    cursor.execute(CREATE_DATASETS_SQL)
    cursor.execute(CREATE_TRACKS_SQL)


def _text(v: Any) -> str | None:
    """Coerce a JSON value to a string column, or NULL."""
    if v is None or v == "":
        return None
    return str(v)[:255] if not isinstance(v, str) else v[:255]


def parse_tracklist(path: Path) -> dict:
    """Parse one trackList.json into the dataset/track row shapes."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    tracks = raw.get("tracks")
    if not isinstance(tracks, list):
        raise ValueError(f"{path}: no 'tracks' array")

    names = raw.get("names")
    track_rows = []
    for i, track in enumerate(tracks):
        if not isinstance(track, dict):
            raise ValueError(f"{path}: track #{i} is not an object")
        track_rows.append({
            "dataset": path.parent.name,
            "ord": i,
            "track_key": _text(track.get("key")),
            "label": _text(track.get("label")),
            "track_type": _text(track.get("type")),
            "url_template": track.get("urlTemplate") or None,
            "category": _text(track.get("category")),
            "track_json": json.dumps(track, default=str),
        })

    dataset_id = raw.get("dataset_id")
    return {
        "dataset": {
            "id": path.parent.name,
            "dataset_id": _text(dataset_id) if dataset_id else None,
            "track_count": len(track_rows),
            "has_names": 1 if isinstance(names, dict) else 0,
            "names_json": json.dumps(names, default=str)
                          if isinstance(names, dict) else None,
        },
        "tracks": track_rows,
    }


def discover_datasets(root: Path) -> list[Path]:
    """Return dataset directories (subdirs containing a trackList.json)."""
    if not root.is_dir():
        sys.exit(f"JBrowse data root not found: {root}")
    found, skipped = [], []
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        tl = sub / "trackList.json"
        if tl.is_file():
            found.append(tl)
        elif sub.name not in ("src", "css", "js", "docs", "plugins", "tests"):
            # JBrowse app dirs legitimately lack trackList.json; anything
            # else is suspicious and worth eyeballing.
            skipped.append(sub.name)
    return found, skipped


def _parse_args(argv: list[str] | None = None) -> dict:
    import argparse
    p = argparse.ArgumentParser(
        description="Import JBrowse trackList.json metadata into jbrowse_meta.",
    )
    p.add_argument("--root", metavar="DIR", default=str(DATA_ROOT),
                   help=f"JBrowse data root (default {DATA_ROOT})")
    p.add_argument("--dry-run", action="store_true",
                   help="Parse trackList.json files but don't touch MySQL.")
    p.add_argument("--limit", type=int, default=None,
                   help="Stop after N datasets (for testing).")
    p.add_argument("--dataset", metavar="NAME", default=None,
                   help="Import only this one dataset directory.")
    args = p.parse_args(argv)
    return {"root": Path(args.root), "dry_run": args.dry_run,
            "limit": args.limit, "dataset": args.dataset}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root: Path = args["root"]

    found, skipped = discover_datasets(root)
    if skipped:
        print(f"Warning: {len(skipped)} dirs without trackList.json "
              f"(likely JBrowse app dirs): {', '.join(skipped[:10])}",
              file=sys.stderr)
    if args["dataset"]:
        found = [tl for tl in found if tl.parent.name == args["dataset"]]
        if not found:
            sys.exit(f"Dataset not found under {root}: {args['dataset']}")
    if args["limit"] is not None:
        found = found[: args["limit"]]

    print(f"Found {len(found)} datasets in {root}")

    dry_run = args["dry_run"] or pymysql is None
    conn = None
    if not dry_run:
        print(f"Connecting to MySQL {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME} ...")
        try:
            conn = pymysql.connect(
                host=DB_HOST, port=DB_PORT, user=DB_USER,
                password=DB_PASSWORD, database=DB_NAME,
                charset="utf8mb4", autocommit=True,
            )
        except Exception as e:  # noqa: BLE001
            print(f"MySQL connection failed: {e}", file=sys.stderr)
            print("Re-run with --dry-run to parse without writing.")
            return 2
    else:
        print("Dry-run mode: skipping MySQL connection.")

    cur = conn.cursor() if conn else None
    if cur is not None:
        ensure_tables(cur)

    ok_count = fail_count = 0
    total_tracks = 0
    for i, tl in enumerate(found, 1):
        name = tl.parent.name
        try:
            parsed = parse_tracklist(tl)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            print(f"[{i:3d}/{len(found)}] {name} ... FAIL ({e})")
            fail_count += 1
            continue

        if cur is not None:
            cur.execute(UPSERT_DATASET_SQL, parsed["dataset"])
            cur.execute(DELETE_TRACKS_SQL, (name,))
            if parsed["tracks"]:
                cur.executemany(INSERT_TRACK_SQL, parsed["tracks"])

        total_tracks += len(parsed["tracks"])
        ok_count += 1
        print(f"[{i:3d}/{len(found)}] {name} ... OK "
              f"({len(parsed['tracks'])} tracks"
              f"{', names' if parsed['dataset']['has_names'] else ''})")

    if conn is not None:
        conn.close()
    print(f"\nDone. datasets OK={ok_count}, FAIL={fail_count}, "
          f"tracks={total_tracks}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
