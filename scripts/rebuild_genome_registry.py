#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重建 wheatomics_db.genome_registry（基因组信息库）。

数据来源（全部为服务器现有事实）：
  1. JBrowse 数据集目录          -> 平台数据集 id / refseq
  2. Genefuncdb.Genefunc_registry -> 基因注释表 / DOI / 标题 / 倍数性
  3. getfasta blastdb             -> 核酸库 / CDS/PEP 库 / .fai / 引物模板
  4. blast.html                   -> Web BLAST 前端分组
  5. all_genomes.nal              -> getfasta 聚合库成员
  6. synteny_mysql.genome_info    -> 比较基因组登记
  7. orthofinder_n.genome_type    -> OrthoFinder 登记

用法（服务器上，source .env 后）：
  python3 scripts/rebuild_genome_registry.py [--dry-run]
"""
from __future__ import annotations

import json
import os
import re
import sys

try:
    import pymysql
except ImportError:  # pragma: no cover
    raise SystemExit("需要 pymysql：source .env 后用 /home/fei/mambaforge/envs/zjw/bin/python3 运行")

JB = "/var/www/html/jbrowse-1.12.3-release"
BLASTDB = "/var/www/html/getfasta/blastdb"
BLAST_HTML = "/var/www/html/blast/blast.html"
ALL_GENOMES = os.path.join(BLASTDB, "all_genomes.nal")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "wheatomics_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_REGISTRY = "wheatomics_db"

if not DB_PASSWORD:
    raise SystemExit("[secrets] export DB_PASSWORD before running this script")

PLOIDY_RE = re.compile(
    r"^(AABBDD|AABBRR|AABBGG|AABBDD|AABB|AAGG|AA|BB|DD|HH|SS|TT|"
    r"StStYYHH|StStHH|NsNsXmXm|NN|CC|EE|FF|GG|JJ|KK|MM|UU|VV)(?:_|$)",
    re.I,
)
POSITION_RE = re.compile(r"^([A-Za-z0-9.\-_]+?)_([ABDRSNH]|E|S|T|U|V|W|X|Y|Z)$")


def norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")


def strip_ploidy(name: str) -> str:
    m = PLOIDY_RE.match(name or "")
    return (name or "")[m.end():] if m else (name or "")


def read_fai_lengths(path: str) -> tuple[int | None, int | None]:
    try:
        total = 0
        n = 0
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                p = line.split("\t")
                if len(p) >= 2:
                    total += int(p[1])
                    n += 1
        return total, n
    except Exception:
        return None, None


def mysql(db: str):
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
        database=db, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
    )


def gather_sources() -> dict:
    src: dict = {}

    # 1) JBrowse 数据集
    jb_ids = []
    for name in sorted(os.listdir(JB)):
        d = os.path.join(JB, name)
        if os.path.isdir(d) and os.path.isfile(os.path.join(d, "seq", "refSeqs.json")):
            jb_ids.append(name)
    src["jbrowse_ids"] = jb_ids

    # 2) Genefunc_registry
    with mysql("Genefuncdb") as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT table_name, display_name, `Group`, Polyploidy, chromosome_level, "
            "Accession, Doi, title, Abstract, created_at, updated_at, visible "
            "FROM Genefunc_registry"
        )
        src["genefunc"] = cur.fetchall()

    # 3) blastdb
    files = os.listdir(BLASTDB)
    src["blast_genome"] = sorted({f[: -len(".genome")] for f in files
                                  if f.endswith(".genome") and len(f) > len(".genome")})
    src["blast_cds"] = sorted({f[: -len(".add_Description.cds")] for f in files
                               if f.endswith(".add_Description.cds")})
    src["blast_pep"] = sorted({f[: -len(".add_Description.pep")] for f in files
                               if f.endswith(".add_Description.pep")})
    src["primerserver"] = sorted({f[: -len(".genome.fai")] for f in files
                                  if f.endswith(".genome.fai")})
    src["blastdb_files"] = set(files)

    # 4) blast.html
    try:
        src["blast_html"] = open(BLAST_HTML, encoding="utf-8", errors="replace").read()
    except OSError:
        src["blast_html"] = ""

    # 5) all_genomes.nal
    members = []
    try:
        for line in open(ALL_GENOMES, encoding="utf-8", errors="replace"):
            if line.startswith("DBLIST"):
                members.extend(line.split()[1:])
    except OSError:
        pass
    src["getfasta_members"] = members

    # 6) synteny genome_info
    with mysql("synteny_mysql") as conn, conn.cursor() as cur:
        cur.execute("SELECT genome_name, bed_file FROM genome_info")
        src["synteny"] = cur.fetchall()

    # 7) orthofinder genome_type
    with mysql("orthofinder_n") as conn, conn.cursor() as cur:
        cur.execute("SELECT genome_number, species, genome_type, subgenome FROM genome_type")
        src["orthofinder"] = cur.fetchall()

    return src


class Matcher:
    """把各模块命名（常带 ploidy 前缀/亚基因组后缀）匹配到 JBrowse 数据集 id。"""

    def __init__(self, jb_ids: list[str]):
        self.jb = sorted(jb_ids, key=len, reverse=True)
        self.norm_jb = {j: norm(j) for j in self.jb}

    def match(self, name: str) -> str | None:
        if not name:
            return None
        n = norm(name)
        n2 = norm(strip_ploidy(name))
        for j, nj in self.norm_jb.items():
            if n == nj or n2 == nj:
                return j
        for j, nj in self.norm_jb.items():
            if nj and n2.endswith("_" + nj) and len(nj) >= 4:
                return j
        for j, nj in self.norm_jb.items():
            if nj and nj.endswith("_" + n2) and len(n2) >= 4:
                return j
        return None


def main() -> int:
    dry = "--dry-run" in sys.argv
    src = gather_sources()
    m = Matcher(src["jbrowse_ids"])
    records: dict[str, dict] = {}

    def rec(key: str) -> dict:
        if key not in records:
            records[key] = {
                "dataset_id": key,
                "display_name": key,
                "aliases": {},
                "usage": {},
                "blast_genome_db": None,
                "blast_cds_db": None,
                "blast_pep_db": None,
                "gene_table": None,
                "jbrowse_dataset": None,
                "getfasta_member": 0,
                "primerserver_fai": 0,
                "web_blast_group": 0,
                "gene_function_ui": 0,
                "synteny_entry": 0,
                "orthofinder_entry": 0,
                "ploidy": None,
                "species": None,
                "doi": None,
                "paper_title": None,
                "genome_size": None,
                "chromosome_count": None,
                "visible": 1,
            }
        return records[key]

    # --- 种子：JBrowse 数据集 ---
    for j in src["jbrowse_ids"]:
        r = rec(j)
        r["jbrowse_dataset"] = j
        r["aliases"]["jbrowse"] = j
        r["usage"]["jbrowse"] = {"dataset": j, "path": f"{JB}/{j}"}

    # --- Genefunc_registry ---
    for row in src["genefunc"]:
        table = row["table_name"] or ""
        display = row["display_name"] or ""
        middle = table
        if middle.startswith("Genefunc_"):
            middle = middle[len("Genefunc_"):]
        if middle.endswith("_table"):
            middle = middle[: -len("_table")]
        key = m.match(display) or m.match(middle) or m.match(table)
        if not key:
            key = display or middle
        r = rec(key)
        r["display_name"] = display or r["display_name"]
        r["gene_table"] = table or r["gene_table"]
        r["gene_function_ui"] = 1 if table else r["gene_function_ui"]
        r["usage"]["gene_function"] = {
            "table": table,
            "api": "/api/genes/functions/registry",
            "frontend": "/genes/ (gene function tables dropdown)",
        }
        if row.get("Polyploidy"):
            r["ploidy"] = row["Polyploidy"]
        elif not r["ploidy"]:
            mm = PLOIDY_RE.match(display or middle)
            if mm:
                r["ploidy"] = mm.group(1).upper()
        if row.get("Doi") and not r["doi"]:
            r["doi"] = row["Doi"]
        if row.get("title") and not r["paper_title"]:
            r["paper_title"] = row["title"]
        if row.get("Group") and not r["species"]:
            r["species"] = row["Group"]
        r["aliases"]["genefunc"] = {"display": display, "table": table}

    # --- blastdb 核酸库 ---
    for prefix in src["blast_genome"]:
        key = m.match(prefix)
        if not key:
            key = prefix
        r = rec(key)
        r["blast_genome_db"] = prefix
        r["aliases"].setdefault("blast_genome", []).append(prefix)
        r["usage"].setdefault("blast", {})["nucleotide_db"] = f"{BLASTDB}/{prefix}.genome"
        if not r["ploidy"]:
            mm = PLOIDY_RE.match(prefix)
            if mm:
                r["ploidy"] = mm.group(1).upper()
        # 基因组大小 / 染色体数（.fai）
        size, n = read_fai_lengths(os.path.join(BLASTDB, prefix + ".genome.fai"))
        if size:
            r["genome_size"] = r["genome_size"] or size
            r["chromosome_count"] = r["chromosome_count"] or n

    # --- CDS / PEP BLAST 库 ---
    for prefix in src["blast_cds"]:
        key = m.match(prefix) or prefix
        r = rec(key)
        r["blast_cds_db"] = prefix
        r["aliases"].setdefault("blast_cds", []).append(prefix)
        r["usage"].setdefault("blast", {})["cds_db"] = f"{BLASTDB}/{prefix}.add_Description.cds"
    for prefix in src["blast_pep"]:
        key = m.match(prefix) or prefix
        r = rec(key)
        r["blast_pep_db"] = prefix
        r["aliases"].setdefault("blast_pep", []).append(prefix)
        r["usage"].setdefault("blast", {})["pep_db"] = f"{BLASTDB}/{prefix}.add_Description.pep"

    # --- PrimerServer2（.fai）---
    for prefix in src["primerserver"]:
        key = m.match(prefix) or prefix
        r = rec(key)
        r["primerserver_fai"] = 1
        r["usage"].setdefault("primerserver", {})["fai"] = f"{BLASTDB}/{prefix}.genome.fai"
        r["usage"]["primerserver"]["api"] = "/api/PrimerServer2/databases"

    # --- getfasta 聚合库 ---
    for member in src["getfasta_members"]:
        base = re.sub(r"\.(genome|scaffold|cds|pep)$", "", member)
        key = m.match(member) or m.match(base) or base
        r = rec(key)
        r["getfasta_member"] = 1
        r["usage"].setdefault("getfasta", {})["all_genomes_member"] = member
        r["usage"]["getfasta"]["api"] = "/api/sequence/by-interval (database=all_genomes)"

    # --- Web BLAST 前端 ---
    html = src["blast_html"]
    for key, r in list(records.items()):
        names = []
        if r["blast_genome_db"]:
            names.append(r["blast_genome_db"])
        names.extend(r["aliases"].get("blast_genome", []))
        hit = None
        for nm in names:
            if f"value='{nm}_chromosomes'" in html or f'value="{nm}_chromosomes"' in html:
                hit = f"{nm}_chromosomes"
                break
            if f"{nm}.genome" in html:
                hit = nm
                break
        if hit:
            r["web_blast_group"] = 1
            r["usage"].setdefault("web_blast", {})["databank"] = hit
            r["usage"]["web_blast"]["frontend"] = "/blast/blast.html"

    # --- synteny / orthofinder 登记 ---
    for row in src["synteny"]:
        name = row["genome_name"] or ""
        base = POSITION_RE.match(name)
        cands = [name, base.group(1) if base else name, strip_ploidy(base.group(1)) if base else name]
        key = next((m.match(c) for c in cands if m.match(c)), None)
        if not key:
            key = base.group(1) if base else name
            if not key:
                continue
        r = rec(key)
        r["synteny_entry"] = 1
        r["usage"].setdefault("synteny", {"genomes": []})["genomes"].append(name)
        if not r["species"]:
            r["species"] = r["species"]

    for row in src["orthofinder"]:
        name = row["species"] or ""
        base = POSITION_RE.match(name)
        cands = [name, base.group(1) if base else name, strip_ploidy(base.group(1)) if base else name]
        key = next((m.match(c) for c in cands if m.match(c)), None)
        if not key:
            key = base.group(1) if base else name
            if not key:
                continue
        r = rec(key)
        r["orthofinder_entry"] = 1
        r["usage"].setdefault("orthofinder", {"species": []})["species"].append(name)

    # --- 人工补充（论文/组装/注释状态）---
    overrides = {
        "AABBRR_PT": {
            "ploidy": "AABBRR", "species": "Triticale", "cultivar_or_line": "PT",
            "doi": "10.1002/imt2.70155",
            "paper_title": "Two near-complete assemblies reveal R-subgenome structural and centromeric divergence associated with reproductive isolation in hexaploid triticale",
            "annotation_status": "available", "annotation_source": "paper (HiTE + gene models)",
            "notes": "HiTE TE track in JBrowse; 12,441,462 TE features",
        },
        "AABBRR_ZX830": {
            "ploidy": "AABBRR", "species": "Triticale", "cultivar_or_line": "ZX830",
            "doi": "10.1002/imt2.70155",
            "paper_title": "Two near-complete assemblies reveal R-subgenome structural and centromeric divergence associated with reproductive isolation in hexaploid triticale",
            "annotation_status": "available", "annotation_source": "paper (HiTE + gene models)",
            "notes": "HiTE TE track in JBrowse; 11,689,370 TE features (chr only)",
        },
        "AABBDD_JM229": {
            "ploidy": "AABBDD", "species": "Triticum aestivum", "cultivar_or_line": "JM229 (济麦229)",
            "assembly_accession": "GWHJNDU00000000.1", "assembly_level": "draft chromosome level",
            "assembly_date": "2026-09-24",
            "genome_size": 13982229658, "chromosome_count": 21,
            "source_url": "https://ngdc.cncb.ac.cn/gwh/Assembly/133298/show",
            "source_file": "/var/www/html/data_genome/GWHJNDU00000000.1.genome.fasta.gz",
            "source_md5": "dded83d9ab6a514528e52c84c1159b27",
            "doi": "10.1111/jipb.70418",
            "paper_title": "Comparative genomics reveals hidden genetic determinants of wheat gluten quality",
            "annotation_status": "pending", "annotation_source": "",
            "notes": "genome-only phase A done 2026-10-22; GFF not published yet",
        },
    }
    for key, ov in overrides.items():
        r = rec(key)
        for k, v in ov.items():
            if k in ("genome_size", "chromosome_count") and r.get(k):
                continue
            r[k] = v

    # --- 统一补默认值 ---
    for r in records.values():
        if not r.get("ploidy"):
            mm = PLOIDY_RE.match(r["dataset_id"]) or PLOIDY_RE.match(r.get("display_name") or "")
            if mm:
                r["ploidy"] = mm.group(1).upper()
        if not r.get("annotation_status"):
            r["annotation_status"] = "available" if r.get("gene_table") else "none"
        r["aliases_json"] = json.dumps(r.pop("aliases"), ensure_ascii=False)
        r["usage_json"] = json.dumps(r.pop("usage"), ensure_ascii=False)

    records = list(records.values())
    records.sort(key=lambda x: x["dataset_id"])

    cols = [
        "dataset_id", "display_name", "species", "ploidy", "subgenomes",
        "cultivar_or_line", "jbrowse_dataset", "assembly_accession", "assembly_version",
        "assembly_level", "assembly_date", "genome_size", "chromosome_count",
        "source_url", "source_file", "source_md5", "doi", "paper_title",
        "annotation_status", "annotation_source", "annotation_doi", "gene_table",
        "blast_genome_db", "blast_cds_db", "blast_pep_db", "getfasta_member",
        "primerserver_fai", "web_blast_group", "gene_function_ui",
        "synteny_entry", "orthofinder_entry", "aliases_json", "usage_json",
        "notes", "visible",
    ]
    placeholders = ",".join(["%s"] * len(cols))
    update = ",".join(f"`{c}`=VALUES(`{c}`)" for c in cols if c != "dataset_id")
    sql = f"INSERT INTO genome_registry ({','.join('`'+c+'`' for c in cols)}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update}"

    preview = {
        "total": len(records),
        "jbrowse": sum(1 for r in records if r.get("jbrowse_dataset")),
        "gene_table": sum(1 for r in records if r.get("gene_table")),
        "blast": sum(1 for r in records if r.get("blast_genome_db")),
        "cds": sum(1 for r in records if r.get("blast_cds_db")),
        "getfasta": sum(1 for r in records if r.get("getfasta_member")),
        "primerserver": sum(1 for r in records if r.get("primerserver_fai")),
        "web_blast": sum(1 for r in records if r.get("web_blast_group")),
        "synteny": sum(1 for r in records if r.get("synteny_entry")),
        "orthofinder": sum(1 for r in records if r.get("orthofinder_entry")),
        "annotation_available": sum(1 for r in records if r.get("annotation_status") == "available"),
        "annotation_pending": sum(1 for r in records if r.get("annotation_status") == "pending"),
    }
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    if dry:
        for ds in ("AABBRR_PT", "AABBRR_ZX830", "AABBDD_JM229", "Abo"):
            r = next((x for x in records if x["dataset_id"] == ds), None)
            print(ds, "->", json.dumps({k: r.get(k) for k in ("jbrowse_dataset", "blast_genome_db", "gene_table", "annotation_status", "doi")}, ensure_ascii=False) if r else "MISSING")
        return 0

    conn = mysql(DB_REGISTRY)
    try:
        with conn.cursor() as cur:
            cur.executemany(sql, [[r.get(c) for c in cols] for r in records])
        conn.commit()
    finally:
        conn.close()
    print("upserted", len(records), "rows into", f"{DB_REGISTRY}.genome_registry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
