#!/usr/bin/env python3
"""Audit (and optionally clean) the WheatOmics BLAST database directory.

Checks, in one pass:
  1. every BLAST database base (nucleotide/protein, single- and multi-volume)
     opens with `blastdbcmd -info`;
  2. every alias file (*.nal/*.pal with a DBLIST header) has all members
     present and the alias itself opens;
  3. the four maintained getfasta aggregates and the legacy aliases;
  4. every `blast_genome_db` recorded in MySQL `genome_registry` exists and
     opens.

Broken alias files are reported; `--apply-clean` moves them (only the alias
file, never member DBs) into a timestamped backup directory.

Run on the web node with the app env (pymysql available):
  /home/fei/mambaforge/envs/zjw/bin/python /tmp/blast_audit/audit.py \
      --json /tmp/blast_audit/report.json --md /tmp/blast_audit/report.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

DB_DIR = Path(os.environ.get("WHEATOMICS_BLASTDB", "/var/www/html/getfasta/blastdb"))
BLASTDBCMD = os.environ.get("WHEATOMICS_BLASTDBCMD", "/var/www/html/blast/blast+/bin/blastdbcmd")
PRIMARY_SUFFIXES = (".nhr", ".nin", ".nsq", ".phr", ".pin", ".psq", ".nal", ".pal")
ALIAS_SUFFIXES = (".nal", ".pal")
MAINTAINED_ALIASES = ["all_genomes", "all_other_genomes", "all_genes", "all_proteins"]
LEGACY_ALIASES = ["all_Diploid", "all_OtherTriticeae", "all_tri6", "all_Allohexaploid",
                  "all_Allotetraploid", "all1_genomes", "all2_genomes", "all3_genomes",
                  "all4_genomes", "all5_genomes", "all6_genomes", "all7_genomes"]
ENV_FILE = "/var/www/FastAPI_backend_Port8000/.env"


def db_cmd(*args: str, timeout: int = 15) -> tuple[int, str]:
    try:
        proc = subprocess.run([BLASTDBCMD, *args], capture_output=True, text=True, timeout=timeout)
        return proc.returncode, ((proc.stderr or "") + (proc.stdout or "")).strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except OSError as exc:
        return 125, str(exc)


def db_base_of(filename: str) -> str | None:
    name = filename
    m = re.match(r"^(.*)\.(\d{2,})" + r"(\.(?:nhr|nin|nsq|phr|pin|psq))$", name)
    if m:
        return m.group(1)
    m = re.match(r"^(.*)\.(nhr|nin|nsq|phr|pin|psq|nal|pal)$", name)
    if m:
        return m.group(1)
    return None


def member_exists(base: str) -> bool:
    return any((DB_DIR / (base + suf)).exists() for suf in PRIMARY_SUFFIXES)


def find_openable(db: str) -> str | None:
    """Resolve a registry base name to an openable DB base.

    `genome_registry.blast_genome_db` stores names without the file suffix
    (e.g. ``AABBDD_Fielder``), while the files on disk are
    ``AABBDD_Fielder.genome`` / ``AABBDD_Fielder.add_Description.cds`` / ...
    Try the bare name first, then every base derived from ``<db>.*`` files.
    """
    rc, _ = db_cmd("-info", "-db", str(DB_DIR / db))
    if rc == 0:
        return db
    try:
        names = os.listdir(DB_DIR)
    except OSError:
        return None
    seen = {db}
    for name in names:
        if not name.startswith(db + "."):
            continue
        base = db_base_of(name)
        if base and base not in seen:
            seen.add(base)
    for base in sorted(seen):
        if base == db:
            continue
        rc, _ = db_cmd("-info", "-db", str(DB_DIR / base))
        if rc == 0:
            return base
    return None


def read_alias_members(path: Path) -> list[str] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if "DBLIST" not in text:
        return None
    members: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("DBLIST"):
            members.extend(line.split()[1:])
    return members


def registry_dbs() -> list[dict]:
    env = {}
    try:
        for line in open(ENV_FILE, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    try:
        import pymysql
        conn = pymysql.connect(
            host=env.get("DB_HOST", "localhost"), user=env.get("DB_USER", "wheatomics_user"),
            password=env.get("DB_PASSWORD", ""), database="wheatomics_db", charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
        with conn.cursor() as cur:
            cur.execute("SELECT dataset_id, blast_genome_db, assembly_level, visible FROM genome_registry")
            rows = cur.fetchall()
        conn.close()
        return rows
    except Exception as exc:
        print(f"[warn] genome_registry not checked: {exc}", file=sys.stderr)
        return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", type=Path, default=Path("/tmp/blast_audit/report.json"))
    ap.add_argument("--md", type=Path, default=Path("/tmp/blast_audit/report.md"))
    ap.add_argument("--apply-clean", action="store_true", help="move broken alias files to a backup dir")
    ap.add_argument("--skip-base-scan", action="store_true", help="skip per-base blastdbcmd scan (fast re-check)")
    args = ap.parse_args()

    start = time.time()
    files = [p.name for p in DB_DIR.iterdir() if p.is_file()] if DB_DIR.is_dir() else []
    bases = sorted({b for b in (db_base_of(n) for n in files) if b})
    print(f"[audit] {len(files)} files, {len(bases)} database bases", flush=True)

    db_fail: list[dict] = []
    checked = 0
    for i, base in enumerate([] if args.skip_base_scan else bases):
        rc, out = db_cmd("-info", "-db", str(DB_DIR / base))
        checked += 1
        if rc != 0:
            db_fail.append({"db": base, "rc": rc, "error": out.splitlines()[0][:200] if out else ""})
        if i and i % 500 == 0:
            print(f"[audit] {i}/{len(bases)} bases, {len(db_fail)} failing", flush=True)

    # aliases
    aliases: list[dict] = []
    for base in bases:
        for suf in ALIAS_SUFFIXES:
            path = DB_DIR / (base + suf)
            if not path.exists():
                continue
            members = read_alias_members(path)
            if members is None:
                continue  # multi-volume index, covered by the base check
            dangling = [m for m in members if not member_exists(m)]
            rc, out = db_cmd("-info", "-db", str(DB_DIR / base))
            aliases.append({
                "alias": base, "file": path.name, "members": len(members),
                "dangling": dangling, "opens": rc == 0,
                "error": "" if rc == 0 else (out.splitlines()[0][:200] if out else ""),
            })

    grouped: dict[str, dict] = {}
    for a in aliases:
        g = grouped.setdefault(a["alias"], {"alias": a["alias"], "files": [], "members": 0,
                                            "dangling": [], "opens": True, "error": ""})
        g["files"].append(a["file"])
        g["members"] = max(g["members"], a["members"])
        g["dangling"] = sorted(set(g["dangling"]) | set(a["dangling"]))
        g["opens"] = g["opens"] and a["opens"]
        g["error"] = g["error"] or a["error"]
    aliases = list(grouped.values())
    broken_aliases = [a for a in aliases if not a["opens"] or a["dangling"]]
    maintained = []
    for name in MAINTAINED_ALIASES:
        rc, out = db_cmd("-info", "-db", str(DB_DIR / name))
        maintained.append({"name": name, "present": (DB_DIR / name).exists() or member_exists(name),
                           "opens": rc == 0, "error": "" if rc == 0 else out.splitlines()[0][:160]})

    registry = registry_dbs()
    registry_missing = []
    for row in registry:
        db = (row.get("blast_genome_db") or "").strip()
        if not db:
            continue
        if find_openable(db) is None:
            rc, out = db_cmd("-info", "-db", str(DB_DIR / db))
            registry_missing.append({"dataset_id": row.get("dataset_id"), "blast_genome_db": db,
                                     "error": out.splitlines()[0][:160] if out else "",
                                     "candidates": []})

    cleaned = []
    if args.apply_clean and broken_aliases:
        backup = Path("/var/www/data/masw_data/blastdb_alias_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        backup.mkdir(parents=True, exist_ok=True)
        for item in broken_aliases:
            for name in item.get("files") or []:
                src = DB_DIR / name
                if src.exists():
                    shutil.move(str(src), str(backup / src.name))
                    cleaned.append(str(src))
        print(f"[audit] cleaned {len(cleaned)} alias file(s) -> {backup}", flush=True)

    report = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "db_dir": str(DB_DIR),
        "elapsed_seconds": round(time.time() - start, 1),
        "files": len(files), "database_bases": len(bases), "checked": checked,
        "open_failures": db_fail,
        "aliases_total": len(aliases),
        "broken_aliases": broken_aliases,
        "maintained_aliases": maintained,
        "legacy_aliases": [a for a in aliases if a["alias"] in LEGACY_ALIASES],
        "registry_dbs": len(registry), "registry_missing": registry_missing,
        "cleaned_files": cleaned,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    md = [
        "# BLAST database audit — " + report["checked_at"], "",
        f"- DB dir: `{DB_DIR}`",
        f"- Files: {report['files']}; database bases: {report['database_bases']}; "
        f"open failures: **{len(db_fail)}**",
        f"- Alias files (DBLIST): {report['aliases_total']}; broken: **{len(broken_aliases)}**",
        f"- genome_registry entries: {len(registry)}; missing/broken: **{len(registry_missing)}**",
        f"- Elapsed: {report['elapsed_seconds']}s", "",
        "## Broken aliases", "",
    ]
    if broken_aliases:
        md += ["| alias | members | dangling (first 5) | opens | error |", "|---|---|---|---|---|"]
        for a in broken_aliases:
            md.append(f"| {a['alias']} | {a['members']} | {', '.join(a['dangling'][:5]) or '-'} | "
                      f"{'yes' if a['opens'] else 'no'} | {a['error'][:90]} |")
    else:
        md.append("_none_")
    md += ["", "## Open failures (non-alias / volumes)", ""]
    if db_fail:
        md += ["| db | rc | error |", "|---|---|---|"]
        md += [f"| {d['db']} | {d['rc']} | {d['error'][:100]} |" for d in db_fail[:60]]
        if len(db_fail) > 60:
            md.append(f"| … | | {len(db_fail) - 60} more |")
    else:
        md.append("_none_")
    md += ["", "## Maintained aggregates", "", "| name | present | opens | error |", "|---|---|---|---|"]
    md += [f"| {m['name']} | {m['present']} | {m['opens']} | {m['error'][:80]} |" for m in maintained]
    md += ["", "## genome_registry missing", ""]
    if registry_missing:
        md += [f"- {r['dataset_id']}: `{r['blast_genome_db']}` — {r['error'][:100]}" for r in registry_missing]
    else:
        md.append("_none_")
    if cleaned:
        md += ["", f"## Cleaned files ({len(cleaned)})", ""] + [f"- {c}" for c in cleaned]
    args.md.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("files", "database_bases", "open_failures", "aliases_total",
                                           "broken_aliases", "registry_missing", "cleaned_files")},
                     ensure_ascii=False)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
