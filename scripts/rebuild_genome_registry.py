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
CURATED_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "data", "triticeae_genome_metadata_v5.3.json")

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


def load_curated() -> dict:
    """加载策展表（陈甜甜 Triticeae Genome Metadata V5.3，289 行 x 29 列）。"""
    try:
        with open(CURATED_JSON, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"rows": []}


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
    src["curated"] = load_curated()
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
                "journal": None,
                "publication_year": None,
                "gene_count": None,
                "te_content": None,
                "curated_json": None,
                "curated_source": None,
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

    # --- 策展表：Triticeae_Genome_Metadata_V5.3（陈甜甜） ---
    curated = src.get("curated") or {"rows": []}
    if curated.get("rows"):
        VER_RE = re.compile(r"^(bpgv?\d+|clr|v\d+(\.\d+)?|hap\d+|t2t|refseq|draft|assembly|genome)$", re.I)
        STOP = {"genome", "genomes", "assembly", "assemblies", "version", "sp", "subsp",
                "cultivar", "cv", "line", "accession", "the", "and", "of", "none"}
        def _toks(x): return re.findall(r"[A-Za-z0-9]+", x or "")
        def _core(x): return [t.lower() for t in _toks(x)
                             if len(t) >= 2 and t.lower() not in STOP and not VER_RE.match(t)]
        SPECIES_ABBREV = {"ae": "aegilops", "aegilop": "aegilops"}
        def _vstrip_compact(x: str) -> str:
            core = [re.sub(r"v\d+$", "", t, flags=re.I) for t in _core(x)]
            core = [SPECIES_ABBREV.get(t, t) for t in core if t]
            return re.sub(r"[^a-z0-9]", "", " ".join(core))

        record_alias = {}
        for key, r in records.items():
            vals = [key, r.get("display_name") or ""]
            def _walk(x, _vals=vals):
                if isinstance(x, dict):
                    for v in x.values():
                        _walk(v, _vals)
                elif isinstance(x, list):
                    for v in x:
                        _walk(v, _vals)
                elif isinstance(x, str):
                    _vals.append(x)
            _walk(r.get("aliases") or {})
            alias_set = {norm(v) for v in vals if norm(v)}
            for v in vals:
                vc = _vstrip_compact(v)
                if vc:
                    alias_set.add(vc)
            record_alias[key] = alias_set

        def _match_curated(species: str):
            """严格匹配：精确/去版本 token 后精确，避免误配。"""
            sp = (species or "").replace("\xa0", " ").strip()
            base = re.sub(r"\(.*?\)", " ", sp).strip()
            parens = re.findall(r"\(([^)]*)\)", sp)
            fc = norm(sp)
            bc = _vstrip_compact(base)
            bc_full = _vstrip_compact(sp)
            paren_c = [_vstrip_compact(p) for p in parens if _vstrip_compact(p)]
            best = (0, None)
            for key, comp in record_alias.items():
                sc = 0
                if fc and fc in comp:
                    sc = 100
                elif bc_full and bc_full in comp:
                    sc = 97
                elif bc and bc in comp:
                    sc = 95
                elif paren_c and any(pc in comp for pc in paren_c) and len(bc) <= 2:
                    sc = 88
                if sc > best[0]:
                    best = (sc, key)
            return best

        PL_OVERRIDES = {
            "Chinese Spring": "Chinese_Spring2.0",
            "Chinese Spring v1.0": "Chinese_Spring1.0",
            "Chinese Spring v2.1": "Chinese_Spring2.1",
            "Abbondanza(Abo)": "Abo",
            "PT": "AABBRR_PT",
            "ZX830": "AABBRR_ZX830",
            "JM44": "Triticum_aestivum_JM44",
            "Jimai22(JM22)": "JM22",
            "Fielder v1.0": "Fielder",
            # 策展表用"全名_缩写"或"全名(缩写)"，平台已有缩写记录 -> 合并
            "Aikang58(AK58)": "AK58",
            "Aimengniu(AMN)": "AMN",
            "Beijing8(BJ8)": "BJ8",
            "Chuanmai42(CM42)": "CM42",
            "Handan6172(HD6172)": "HD6172",
            "Jinmai47(JM47)": "JM47",
            "Kuofan11(KF11)": "KF11",
            "Mazhamai(MZM)": "MZM",
            "Ningchun4(NC4)": "NC4",
            "Shi4185(S4185)": "S4185",
            "Xiaoyan6(XY6)": "XY6",
            "Xinong6028(XN6028)": "XN6028",
            "Yangmai158(YM158)": "YM158",
            "Zhengmai366(ZM366)": "ZM366",
            "Zhoumai16(ZM16)": "ZM16",
            "Zhoumai22(ZM22)": "ZM22",
            "Ae.speltoides (Y2032)": "y2032",
            "Aegilops ventricosa(cv. RM271)": "RM271",
            "Yangmai33": "YM33",
        }
        SUB = {"AABBDD": "A,B,D", "AABBRR": "A,B,R", "AABB": "A,B", "AA": "A", "DD": "D",
               "HH": "H", "SS": "S", "TT": "T", "MM": "M", "AAGG": "A,G", "DDNN": "D,N",
               "STSTYYHH": "St,Y,H", "STSTVVJJ": "St,V,J", "NSNSXMXM": "Ns,Ns,Xm,Xm",
               "UU": "U", "VV": "V", "EE": "E", "RR": "R", "ATATGG": "At,G"}
        def _num(v):
            if v is None:
                return None
            m = re.search(r"\d+(?:\.\d+)?", str(v).replace(",", ""))
            return int(float(m.group(0))) if m else None

        # DOI -> JBrowse 数据集（来自 jbrowse.html 卡片），用于名称不匹配时兜底
        card_doi_map: dict[str, list] = {}
        for _ds, _card in (src.get("jbrowse_cards") or {}).items():
            _doi = str(_card.get("doi") or "").strip()
            if _doi:
                card_doi_map.setdefault(_doi, []).append(_ds)

        matched_n = created_n = skipped_n = 0
        candidates: dict[str, list] = {}
        for row in curated["rows"]:
            species = str(row.get("Species") or "").strip()
            if not species or species == "None":
                skipped_n += 1
                continue
            cur_doi = str(row.get("DOI_cleaned") or row.get("DOI") or "").strip()
            _m = re.search(r"10\.\d{4,9}/\S+", cur_doi) if cur_doi else None
            cur_doi = _m.group(0).rstrip(".,;") if _m else None
            key, sc = PL_OVERRIDES.get(species), 100
            if not key:
                sc, key = _match_curated(species)
            # DOI 兜底：名称匹配不上时，按论文 DOI 找唯一对应的 JBrowse 数据集
            if not key and cur_doi:
                cands = [c for c in card_doi_map.get(cur_doi, []) if c in records]
                if len(cands) == 1:
                    key, sc = cands[0], 93
            existed = bool(key) and key in records
            if not existed:
                specific = bool(re.search(r"[()\d]", species))
                if not specific:
                    skipped_n += 1
                    continue
                ds = re.sub(r"[^A-Za-z0-9._-]+", "_", species).strip("_")[:150]
                if ds in records:
                    # 同名物种但 DOI 与已有记录不同：追加年份区分（例如 AL8/78 2013 vs 2017）
                    if cur_doi and records[ds].get("doi") == cur_doi:
                        key = ds
                        existed = True
                        matched_n += 1
                        candidates.setdefault(key, []).append((sc, row, existed))
                        continue
                    ds = f"{ds}_{row.get('Publication_Year') or 'x'}"
                if not ds:
                    ds = "curated_" + re.sub(r"[^A-Za-z0-9._-]+", "_", species).strip("_")[:140]
                key = ds
                created_n += 1
            else:
                matched_n += 1
            candidates.setdefault(key, []).append((sc, row, existed))

        def _apply_curated(r, row, existed):
            ploidy = str(row.get("Chromosome_Level") or "").strip().upper()
            genome_comp = str(row.get("Genome_Composition") or "").strip()
            if re.fullmatch(r"[A-Z]+", ploidy or ""):
                r["ploidy"] = ploidy
            if genome_comp:
                r["species"] = genome_comp
            if ploidy in SUB:
                r["subgenomes"] = SUB[ploidy]
            n = _num(row.get("Chromosome_Number"))
            if n:
                r["chromosome_count"] = n
            try:
                gb = float(str(row.get("Genome_Size_Gb")).strip())
                if 1.0 <= gb <= 40.0:  # Triticeae 合理范围，过滤异常值
                    r["genome_size"] = int(round(gb * 1e9))
            except (TypeError, ValueError):
                pass
            curated_doi = str(row.get("DOI_cleaned") or row.get("DOI") or "").strip()
            if curated_doi:
                _m = re.search(r"10\.\d{4,9}/\S+", curated_doi)
                if _m:
                    curated_doi = _m.group(0).rstrip(".,;")
                    if r.get("doi") and r.get("doi") != curated_doi:
                        r["notes"] = (r.get("notes") or "") + f" [原 DOI: {r['doi']}]"
                    r["doi"] = curated_doi
            if row.get("NCBI_Assembly_Level"):
                lv = str(row["NCBI_Assembly_Level"]).strip()
                if lv.lower() != "none":
                    r["assembly_level"] = lv
            else:
                cla = str(row.get("Chromosome_Level_Assembly") or "").strip().lower()
                era = str(row.get("Era") or "").strip()
                if cla == "yes":
                    r["assembly_level"] = "Chromosome"
                elif "partial" in cla:
                    r["assembly_level"] = "Partial chromosome"
                elif era == "Draft Era":
                    r["assembly_level"] = "Draft"
            if row.get("Journal"):
                j = str(row["Journal"]).strip()
                if j.lower() != "none":
                    r["journal"] = j
            y = _num(row.get("Publication_Year"))
            if y:
                r["publication_year"] = y
            gc = _num(row.get("Gene_Count"))
            if gc:
                r["gene_count"] = gc
            if row.get("TE_Content"):
                te = str(row["TE_Content"]).strip()
                if te.lower() != "not provided":
                    r["te_content"] = te
            if not r.get("cultivar_or_line"):
                mm = re.search(r"\(([^)]*)\)", species)
                r["cultivar_or_line"] = (mm.group(1) if mm else "")[:255] or None
            r["curated_json"] = json.dumps(row, ensure_ascii=False)
            r["curated_source"] = "Triticeae_Genome_Metadata_English_V5.3.xlsx/Sheet1"
            if not existed and not r.get("notes"):
                r["notes"] = "策展表 V5.3 收录；平台尚未上线（无 JBrowse/BLAST 记录）"

        ambiguous = 0
        for key, cands in candidates.items():
            cands.sort(key=lambda x: (-x[0], -(_num(x[1].get("Publication_Year")) or 0)))
            top = [c for c in cands if c[0] == cands[0][0]]
            if len(top) > 1:
                ambiguous += 1
            sc, row, existed = cands[0]
            _apply_curated(rec(key), row, existed)
            if len(top) > 1:
                r = records[key]
                r["notes"] = (r.get("notes") or "") + f" [策展表同分候选 {len(top)} 条，取最新年份]"

        print(f"curated: rows={len(curated['rows'])} matched={matched_n} created={created_n} skipped={skipped_n} ambiguous={ambiguous}")

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
    overrides["Kronos"] = {
        "display_name": "Kronos (pan-genome, 2026; Durum)",
        "species": "Triticum turgidum L. ssp. durum (Desf.) Husn.",
        "ploidy": "AABB", "assembly_level": "Chromosome",
        "jbrowse_dataset": "Kronos",
        "blast_genome_db": "AABB_Kronos",
        "blast_cds_db": "AABB_Kronos", "blast_pep_db": "AABB_Kronos",
        "gene_table": "Genefunc_Kronos_table",
        "cultivar_or_line": "Kronos", "sample_id": "PI576168",
        "common_name": "Durum", "sample_type": "Free-threshing tetraploid wheat",
        "notes": "四倍体泛基因组 2026（10.1038/s41588-026-02678-9）；pan-genome assembly（2,292 seqs / 10.82 Gb）",
    }
    overrides["Triticum_turgidum_Kronos"] = {
        "display_name": "Kronos v2.1 (New Phytologist 2026; Durum)",
        "species": "Triticum turgidum L. ssp. durum (Desf.) Husn.",
        "ploidy": "AABB", "assembly_level": "Chromosome",
        "jbrowse_dataset": "Triticum_turgidum_Kronos",
        "blast_genome_db": "AABB_Triticum_turgidum_Kronos",
        "gene_table": "Genefunc_AABB_Kronos_table",
        "cultivar_or_line": "Kronos", "sample_id": "PI576168",
        "common_name": "Durum", "sample_type": "Free-threshing tetraploid wheat",
        "doi": "10.1111/nph.71006", "journal": "New Phytologist", "publication_year": 2026,
        "paper_title": "The annotated blueprint: integrated functional genomic resources for a model tetraploid wheat Triticum turgidum cv Kronos",
        "notes": "Kronos v2.1 reference genome（15 seqs / 10.56 Gb）；New Phytologist 2026（10.1111/nph.71006）",
    }
    overrides["Thinopyrum_ponticum_decaploid"] = {
        "species": "Thinopyrum ponticum", "ploidy": "PPPP",
        "genome_size": 41330000000, "chromosome_count": 70,
        "doi": "10.1016/j.molp.2026.09.014",
        "journal": "Molecular Plant", "publication_year": 2026,
        "paper_title": ("The homoeolog-resolved assembly of the 40-Gb decaploid Thinopyrum ponticum "
                        "genome reveals extensive homoeologous exchange and recombination, "
                        "segmental allopolyploid organization, and allelic variations for wheat improvement"),
        "display_name": "Thinopyrum ponticum (Tpo.Acc-1)",
        "assembly_level": "Chromosome",
        "gene_table": "Genefunc_Thinopyrum_ponticum_decaploid_table",
        "assembly_accession": "Tpo.Acc-1",
        "cultivar_or_line": "Tpo.Acc-1",
        "notes": "材料登录号 Tpo.Acc-1；2026-10-23 完成 dataset_id 迁移；合规处理完成：43,558 unplaced 已重命名 ChrUn_*，官方 QC 通过；BLAST 核酸库/CDS/PEP 库已建；JBrowse 已用新命名重建（DNA+all_gene）；基因功能表/02G 已建",
    }

    for key, ov in overrides.items():
        r = rec(key)
        for k, v in ov.items():
            if k in ("genome_size", "chromosome_count") and r.get(k):
                continue
            r[k] = v

    # --- 人工确认忽略的基因组（无 JBrowse / 无可用数据），隐藏但保留溯源 ---
    IGNORED_DATASETS = {"Aegilops_tauschii_V1.1", "Aegilops_tauschii_AL8_78"}
    for _ds in IGNORED_DATASETS:
        _r = records.get(_ds)
        if _r is not None:
            _r["visible"] = 0
            _note = "已确认忽略（无 JBrowse/无可用数据，2026-10-23）"
            if _note not in (_r.get("notes") or ""):
                _r["notes"] = ((_r.get("notes") or "") + " [" + _note + "]").strip()

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
        "sample_id", "common_name", "sample_type",
        "assembly_version", "assembly_level", "assembly_date", "genome_size",
        "chromosome_count", "source_url", "source_file", "source_md5", "doi",
        "paper_title", "citation_text", "citation_source", "annotation_status",
        "annotation_source", "annotation_doi", "journal", "publication_year",
        "gene_count", "te_content", "curated_json", "curated_source", "notes", "visible",
    )
    for r in records.values():
        old = existing.get(r["dataset_id"])
        if not old:
            continue
        for f in preserve_fields:
            # 注意：visible=0 是"显式隐藏"，不能用 falsy 判断覆盖
            if r.get(f) in (None, "") and old.get(f) not in (None, ""):
                r[f] = old[f]

    # --- 四倍体泛基因组 2026（Nature Genetics）样本元数据 ---
    _tp_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tetraploid_pangenome_2026.json")
    try:
        with open(_tp_file, encoding="utf-8") as _fh:
            _tp = json.load(_fh)
    except (OSError, ValueError) as _exc:
        _tp = None
        print(f"[WARN] 读取 {_tp_file} 失败: {_exc}")
    if _tp:
        _src = _tp.get("source", {})
        _samples = dict(_tp.get("samples", {}))
        _samples.update(_tp.get("related_samples", {}))
        _found = 0
        for _ds, _m in _samples.items():
            _r = records.get(_ds)
            if _r is None:
                print(f"[WARN] tetraploid pangenome sample 未找到记录: {_ds}")
                continue
            _found += 1
            for _f, _k in (("cultivar_or_line", "sample_name"), ("sample_id", "sample_id"),
                           ("species", "subspecies"), ("sample_type", "sample_type"),
                           ("common_name", "common_name")):
                _v = (_m.get(_k) or "").strip()
                if _v:
                    _r[_f] = _v
            _paper = _m.get("paper_override")
            if _paper is None and _m.get("set_paper", True):
                _paper = _src
            if _paper and _paper.get("doi"):
                _prev = _r.get("doi")
                _notes = _r.get("notes") or ""
                # 去掉与新/旧 DOI 相关的历史注释（避免重复/误导）
                for _d in {_prev, _paper.get("doi"), _src.get("doi")}:
                    if _d:
                        _notes = _notes.replace(f" [原 DOI: {_d}]", "").replace(f"[原 DOI: {_d}]", "")
                if _m.get("strip_doi_notes"):
                    _notes = re.sub(r"\s*\[原 DOI: [^\]]+\]", "", _notes)
                if _prev and _prev != _paper["doi"] and not _m.get("strip_doi_notes"):
                    _note = f"[原 DOI: {_prev}]"
                    if _note not in _notes:
                        _notes = (_notes + " " + _note).strip()
                _r["notes"] = _notes
                _r["doi"] = _paper["doi"]
                for _pk, _rf in (("journal", "journal"), ("year", "publication_year"), ("title", "paper_title")):
                    if _paper.get(_pk):
                        _r[_rf] = _paper[_pk]
            try:
                _cj = json.loads(_r.get("curated_json") or "{}")
                if not isinstance(_cj, dict):
                    _cj = {}
            except (TypeError, ValueError):
                _cj = {}
            _entry = {**_m, "source_doi": _src.get("doi")}
            _paper_doi = (_paper or {}).get("doi")
            if _paper_doi:
                _entry["paper_doi"] = _paper_doi
            _cj["tetraploid_pangenome_2026"] = _entry
            _r["curated_json"] = json.dumps(_cj, ensure_ascii=False)
            _note = (f"四倍体泛基因组 2026 样本：{_m.get('sample_name','')}"
                     f"（{_m.get('common_name','')}；{_m.get('sample_type','')}）")
            if _note not in (_r.get("notes") or ""):
                _r["notes"] = ((_r.get("notes") or "") + " " + _note).strip()
        print(f"tetraploid pangenome metadata: matched={_found}/{len(_samples)}")

    # Thinopyrum_ponticum_decaploid：染色体数按论文 70（fai 里是全部序列数）
    _tpp = records.get("Thinopyrum_ponticum_decaploid")
    if _tpp is not None:
        _tpp["chromosome_count"] = 70
        _tpp["genome_size"] = 41328730192

    # 旧 Th.ponticum scaffold 组装：清除误记 DOI，注明状态
    _old = records.get("Thinopyrum_ponticum")
    if _old is not None:
        _old["doi"] = None
        _old["notes"] = ("旧 scaffold 组装（33.6 Gb / 99,148 scaffolds，BLAST 库 Other_Thinopyrum_ponticum）；"
                         "正式引用待确认（此前误记 10.1126/science.aan0032）")

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
        "cultivar_or_line", "sample_id", "common_name", "sample_type",
        "jbrowse_dataset", "assembly_accession", "assembly_version",
        "assembly_level", "assembly_date", "genome_size", "chromosome_count",
        "gene_count", "te_content",
        "source_url", "source_file", "source_md5", "doi", "paper_title",
        "journal", "publication_year",
        "annotation_status", "annotation_source", "annotation_doi", "gene_table",
        "citation_text", "citation_source",
        "blast_genome_db", "blast_cds_db", "blast_pep_db", "getfasta_member",
        "primerserver_fai", "web_blast_group", "gene_function_ui",
        "synteny_entry", "orthofinder_entry", "aliases_json", "usage_json",
        "curated_json", "curated_source",
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
    # 清理失效的"纯策展"行（别名合并后不再对应任何记录）
    keep = {r["dataset_id"] for r in records}
    try:
        conn2 = mysql(DB_REGISTRY)
        try:
            with conn2.cursor() as cur:
                cur.execute(
                    "SELECT dataset_id FROM genome_registry "
                    "WHERE curated_source IS NOT NULL AND jbrowse_dataset IS NULL "
                    "AND blast_genome_db IS NULL AND gene_table IS NULL"
                )
                stale = [row["dataset_id"] for row in cur.fetchall() if row["dataset_id"] not in keep]
                if stale:
                    placeholders = ",".join(["%s"] * len(stale))
                    cur.execute(f"DELETE FROM genome_registry WHERE dataset_id IN ({placeholders})", stale)
            conn2.commit()
        finally:
            conn2.close()
        print("pruned stale curated-only rows:", len(stale))
    except Exception as exc:  # noqa: BLE001
        print("prune failed:", exc)

    # --- 去重合并：同一基因组的多种命名（DD_/UU_ 前缀、dot/underscore 差异、缩写等）---
    PL_PREFIX = re.compile(
        r"^(AABBDD|AABBRR|AABBGG|AABB|AAGG|AA|BB|DD|HH|SS|TT|MM|UU|VV|EE|RR|CC|NN|JJ|KK|II|"
        r"PPPP|STSTYYHH|STSTVVJJ|NSNSXMXM|ATATGG)_", re.I
    )
    # 明确的"同一基因组不同命名"人工合并映射（全名/缩写/版本/clean 变体）
    FORCE_MERGE = {
        "CM104": "Chuanmai104",
        "CS_IWGSC03G": "IWGSC03G",
        "AABBDD_CS_CNAU": "CS-CAU",
        "Renan_v2": "Renan",
        "ArinaLrFor_PGSBv2": "ArinaLrFor",
        "Julius_PGSBv2": "Julius",
        "Norin61_PGSBv2": "Norin61",
        "Landmark_PGSBv2": "CDC_Landmark",
    }

    def _core_id(x: str) -> str:
        core = PL_PREFIX.sub("", x or "", count=1).lower()
        core = re.sub(r"[._-](clean|dedup|cleandedup|deduplicated)$", "", core)
        core = re.sub(r"[._-](clean|dedup|cleandedup|deduplicated)(?=[._-]|$)", "", core)
        core = re.sub(r"\bae\b", "aegilops", core)
        core = re.sub(r"\bae[._-]", "aegilops_", core)
        core = re.sub(r"[^a-z0-9]", "", core)
        # Aegilops/ae 前缀差异：AeComosa... / Aegilops_comosa... 视为同一 core
        for pfx in ("aegilops", "aegilop", "ae"):
            if core.startswith(pfx) and len(core) > len(pfx) + 3:
                return core[len(pfx):]
        return core
    fill_fields = (
        "species", "ploidy", "subgenomes", "cultivar_or_line", "assembly_accession",
        "sample_id", "common_name", "sample_type",
        "assembly_version", "assembly_level", "assembly_date", "genome_size",
        "chromosome_count", "source_url", "source_file", "source_md5", "doi",
        "paper_title", "journal", "publication_year", "gene_count", "te_content",
        "annotation_status", "annotation_source", "annotation_doi", "gene_table",
        "blast_genome_db", "blast_cds_db", "blast_pep_db", "getfasta_member",
        "primerserver_fai", "web_blast_group", "gene_function_ui",
        "synteny_entry", "orthofinder_entry", "curated_json", "curated_source", "notes",
    )
    try:
        conn3 = mysql(DB_REGISTRY)
        try:
            with conn3.cursor() as cur:
                cur.execute("SELECT * FROM genome_registry")
                all_rows = cur.fetchall()
                groups: dict[str, list] = {}
                for row in all_rows:
                    _target = FORCE_MERGE.get(row["dataset_id"])
                    key = _core_id(_target) if _target else _core_id(row["dataset_id"])
                    groups.setdefault(key, []).append(row)
                removed = 0
                for rows in groups.values():
                    if len(rows) < 2:
                        continue
                    def _score(r):
                        return ((3 if r.get("jbrowse_dataset") else 0)
                                + (2 if r.get("blast_genome_db") else 0)
                                + (1 if r.get("gene_table") else 0)
                                + (1 if r.get("curated_source") else 0)
                                + (1 if r.get("doi") else 0)
                                + (1 if r.get("species") else 0)
                                + (10 if r["dataset_id"] in FORCE_MERGE.values() else 0))
                    rows.sort(key=_score, reverse=True)
                    canon = rows[0]
                    try:
                        aliases = json.loads(canon.get("aliases_json") or "{}")
                    except (TypeError, ValueError):
                        aliases = {}
                    merged_ids = set(aliases.get("merged_ids") or [])
                    for dup in rows[1:]:
                        merged_ids.add(dup["dataset_id"])
                        updates = {}
                        for f in fill_fields:
                            if not canon.get(f) and dup.get(f):
                                canon[f] = dup[f]
                                updates[f] = dup[f]
                        aliases["merged_ids"] = sorted(merged_ids)
                        _merged_note = f"[合并自 {dup['dataset_id']}"
                        if dup.get("gene_table"):
                            _merged_note += f"（基因表 {dup['gene_table']}）"
                        _merged_note += "]"
                        if _merged_note not in (canon.get("notes") or ""):
                            canon["notes"] = ((canon.get("notes") or "") + " " + _merged_note).strip()
                            updates["notes"] = canon["notes"]
                        if updates:
                            sets = ",".join(f"`{k}`=%s" for k in updates)
                            cur.execute(
                                f"UPDATE genome_registry SET aliases_json=%s,{sets} WHERE dataset_id=%s",
                                [json.dumps(aliases, ensure_ascii=False)]
                                + list(updates.values()) + [canon["dataset_id"]],
                            )
                        else:
                            cur.execute(
                                "UPDATE genome_registry SET aliases_json=%s WHERE dataset_id=%s",
                                (json.dumps(aliases, ensure_ascii=False), canon["dataset_id"]),
                            )
                        cur.execute("DELETE FROM genome_registry WHERE dataset_id=%s", (dup["dataset_id"],))
                        removed += 1
                # 清理空壳记录（无任何模块/策展/DOI/物种）
                cur.execute(
                    "DELETE FROM genome_registry WHERE jbrowse_dataset IS NULL "
                    "AND blast_genome_db IS NULL AND gene_table IS NULL AND curated_source IS NULL "
                    "AND (doi IS NULL OR doi='') AND (species IS NULL OR species='') "
                    "AND (notes IS NULL OR notes='')"
                )
                empties = cur.rowcount
                print("pruned empty rows:", empties)
            conn3.commit()
        finally:
            conn3.close()
        print("dedupe merged/removed rows:", removed)
    except Exception as exc:  # noqa: BLE001
        print("dedupe failed:", exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
