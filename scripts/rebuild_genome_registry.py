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
JBROWSE_HTML = "/var/www/html/jbrowse.html"
CITE_HTML = "/var/www/html/cite.html"

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


CARD_RE = re.compile(r'<div class="card-body">(.*?)</div>', re.S)
SELF_LINK_RE = re.compile(r"\?data=([^\"']+)[\"'][^>]*>(.*?)</a>", re.S)
LINK_RE = re.compile(r'href="([^"]+)"[^>]*>(.*?)</a>', re.S)
DOI_RE = re.compile(r"(10\.\d{4,9}/[^\s\"'<>]+)")
ACC_RE = re.compile(
    r"\b(GWH[A-Za-z]{2,}[0-9]+(?:\.[0-9]+)?|GCA_[0-9]+\.[0-9]+|GCF_[0-9]+\.[0-9]+|"
    r"PRJ[A-Z]{2}[0-9]+|SAM[A-Z][0-9]+|CRA[0-9]+)\b"
)
REPO_DOMAINS = (
    "ngdc.cncb.ac.cn", "gwh", "ncbi.nlm.nih.gov", "ebi.ac.uk",
    "ensembl.org", "gramene.org", "urgi.versailles", "plants.ensembl.org",
)


def _strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _extract_doi(*texts: str) -> str | None:
    for t in texts:
        if not t:
            continue
        m = DOI_RE.search(t)
        if m:
            return m.group(1).rstrip(".,;")
        m = re.search(r"doi:\s*(10\.[^\s<]+)", t, re.I)
        if m:
            return m.group(1).rstrip(".,;")
    return None


def parse_jbrowse_cards() -> dict:
    """解析 jbrowse.html 卡片：dataset -> 标题/引文/数据源/组装号。"""
    try:
        html = open(JBROWSE_HTML, encoding="utf-8", errors="replace").read()
    except OSError:
        return {}
    cards = {}
    for block in CARD_RE.findall(html):
        m = SELF_LINK_RE.search(block)
        if not m:
            continue
        ds = m.group(1).strip()
        title = _strip_tags(m.group(2))
        doi = None
        repo_url = None
        link_label = None
        accession = None
        for href, label in LINK_RE.findall(block):
            if "data=" in href:
                continue
            label_s = _strip_tags(label)
            d = _extract_doi(href, label_s)
            if d:
                doi = d
                link_label = label_s
            if any(dom in href for dom in REPO_DOMAINS):
                repo_url = href
            a = ACC_RE.search(href + " " + label_s)
            if a and not accession:
                accession = a.group(1)
        # 有些卡片 DOI 不在 <a> 内，直接扫整块纯文本
        if not doi:
            doi = _extract_doi(_strip_tags(block))
        if not accession:
            a2 = ACC_RE.search(_strip_tags(block))
            if a2:
                accession = a2.group(1)
        ploidy = None
        pm = re.match(r"^(.*?)\s*\(([A-Za-z]{2,12})\)\s*$", title)
        if pm:
            title = pm.group(1).strip()
            ploidy = pm.group(2).upper()
        cards[ds] = {
            "title": title, "doi": doi, "repo_url": repo_url,
            "link_label": link_label, "ploidy": ploidy, "accession": accession,
        }
    return cards


def parse_cite_blocks() -> tuple[dict, list[dict]]:
    """解析 cite.html：返回 (doi -> 引文, 全部块列表)。"""
    try:
        html = open(CITE_HTML, encoding="utf-8", errors="replace").read()
    except OSError:
        return {}, []
    blocks = re.findall(
        r"If you use (.+?) please cite:(.*?)(?=<br>\s*<br>|If you use |$)",
        html, re.S,
    )
    by_doi = {}
    all_blocks = []
    for trigger, body in blocks:
        trigger_s = _strip_tags(trigger)
        citation = _strip_tags(body)[:1500]
        doi = _extract_doi(citation)
        title = None
        tm = re.search(r"\((?:19|20)\d{2}\)\s*(.+?)(?:\.\s|\?|$)", citation)
        if tm:
            title = tm.group(1).strip()[:500]
        all_blocks.append({"trigger": trigger_s, "citation": citation,
                           "doi": doi, "title": title})
        if doi:
            by_doi.setdefault(doi, {"citation": citation, "title": title})
    return by_doi, all_blocks


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

    # 8) 页面来源：jbrowse.html 卡片 + cite.html 引文
    src["jbrowse_cards"] = parse_jbrowse_cards()
    src["cite_by_doi"], src["cite_blocks"] = parse_cite_blocks()
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

    # --- jbrowse.html 卡片 + cite.html 引文/数据源 ---
    cards = src.get("jbrowse_cards", {})
    cite_by_doi = src.get("cite_by_doi", {})
    for ds, card in cards.items():
        r = records.get(ds)
        if not r:
            continue
        if card.get("doi") and not r.get("doi"):
            r["doi"] = card["doi"]
        cite_info = cite_by_doi.get(card.get("doi") or "")
        if cite_info and not r.get("citation_text"):
            r["citation_text"] = cite_info.get("citation")
            r["citation_source"] = "cite.html"
            if not r.get("paper_title") and cite_info.get("title"):
                r["paper_title"] = cite_info["title"]
        if card.get("repo_url") and not r.get("source_url"):
            r["source_url"] = card["repo_url"]
        if card.get("ploidy") and not r.get("ploidy"):
            r["ploidy"] = card["ploidy"]
        if card.get("accession") and not r.get("assembly_accession"):
            r["assembly_accession"] = card["accession"]
        if card.get("title") and r.get("display_name") in (None, "", ds):
            r["display_name"] = card["title"]

    # 对仍缺 doi/引文的记录，用 cite.html 的 "If you use ..." 描述做关键词回退
    stop_words = {"genome", "genomes", "transcripts", "transcript", "sequences",
                  "sequence", "proteins", "protein", "genes", "gene", "please", "cite"}
    for r in records.values():
        if r.get("doi") and r.get("citation_text"):
            continue
        kws = [w for w in re.split(r"[^A-Za-z0-9]+", r.get("display_name") or r["dataset_id"])
               if len(w) >= 4 and w.lower() not in stop_words]
        if not kws:
            continue
        for blk in src.get("cite_blocks", []):
            trig = (blk.get("trigger") or "").lower()
            if trig and any(k.lower() in trig for k in kws):
                if not r.get("doi") and blk.get("doi"):
                    r["doi"] = blk["doi"]
                if not r.get("citation_text") and blk.get("citation"):
                    r["citation_text"] = blk["citation"]
                    r["citation_source"] = "cite.html (keyword match)"
                if not r.get("paper_title") and blk.get("title"):
                    r["paper_title"] = blk["title"]
                break

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

    # --- 保留数据库中已有字段（只补空，不覆盖已有数据）---
    existing: dict[str, dict] = {}
    try:
        with mysql(DB_REGISTRY) as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM genome_registry")
            existing = {row["dataset_id"]: row for row in cur.fetchall()}
    except Exception:
        existing = {}
    preserve_fields = (
        "species", "subgenomes", "cultivar_or_line", "assembly_accession",
        "assembly_version", "assembly_level", "assembly_date", "genome_size",
        "chromosome_count", "source_url", "source_file", "source_md5", "doi",
        "paper_title", "citation_text", "citation_source", "annotation_source",
        "annotation_doi", "notes", "visible",
    )
    for r in records.values():
        old = existing.get(r["dataset_id"])
        if not old:
            continue
        for f in preserve_fields:
            if not r.get(f) and old.get(f) not in (None, ""):
                r[f] = old[f]

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
        "citation_text", "citation_source",
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
        "doi": sum(1 for r in records if r.get("doi")),
        "citation": sum(1 for r in records if r.get("citation_text")),
        "source_url": sum(1 for r in records if r.get("source_url")),
        "accession": sum(1 for r in records if r.get("assembly_accession")),
        "paper_title": sum(1 for r in records if r.get("paper_title")),
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
