#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重建 getfasta 页面的 4 个聚合检索库 + 精简下拉框 + 文档 Library 列。

- all_genomes       : 所有染色体水平基因组（单个 .genome 库）
- all_other_genomes : 所有非染色体水平基因组（scaffold/contig/draft 等，合并成一个 alias 库）
- all_genes         : 所有转录本（*.add_Description.cds）
- all_proteins      : 所有蛋白（*.add_Description.pep）
同时：
- getfasta/index.html 下拉框只保留上述 4 项（不再逐基因组列出）
- getsequence_search.txt 增加第 4 列 Library（all_genomes / all_other_genomes）

默认 dry-run；--apply 才写文件。所有目标文件写前自动备份。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import pathlib
import re
import shutil
import sys
import time
import urllib.request

CHROM_LEVELS = {"Chromosome", "Complete Genome", "draft chromosome level", "Chromosome Level"}

# 已知有问题的 BLAST 库（blastdbcmd 打不开，放进 alias 会让整个库不可用）
INVALID_DB_MEMBERS = {
    "Foma.pep",  # 2026-10-23: blastdbcmd -info 报 mdb_env_open，排除出 all_proteins
}
OVERRIDES = {
    # 数据库名: chromosome-level?
    "Th.ponticum_public.genome": True,   # 2026 Mol Plant, 70 chr
    "Other_Thinopyrum_ponticum.genome": False,
}
PLOIDY_PREFIX = re.compile(
    r"^(AABBDD|AABBRR|AABBGG|AABB|AAGG|AA|BB|DD|HH|SS|TT|MM|UU|VV|EE|RR|CC|NN|JJ|KK|II|"
    r"PPPP|STSTYYHH|STSTVVJJ|NSNSXMXM|ATATGG)_",
    re.I,
)


def norm_name(s: str) -> str:
    s = PLOIDY_PREFIX.sub("", s or "")
    s = s.lower()
    s = re.sub(r"\.(genome|scaffold|scaffolds|genome_Chr.*|add_description\.(cds|pep)|cds|pep)$", "", s)
    s = re.sub(r"^(aegilops|aegilop|ae)[._-]", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def _load_env(path: str = "/var/www/FastAPI_backend_Port8000/.env") -> dict:
    env = {}
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return env


def fetch_registry(api: str) -> list[dict]:
    """优先从 MySQL 直读（API list 不含 blast_genome_db/aliases），失败再退回 API。"""
    env = _load_env()
    try:
        import pymysql
        conn = pymysql.connect(
            host=env.get("DB_HOST", "localhost"),
            user=env.get("DB_USER", "wheatomics_user"),
            password=env.get("DB_PASSWORD", ""),
            database="wheatomics_db",
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT dataset_id, blast_genome_db, assembly_level, chromosome_count, "
                "visible, aliases_json FROM genome_registry"
            )
            rows = cur.fetchall()
        conn.close()
        for r in rows:
            try:
                aliases = json.loads(r.get("aliases_json") or "{}")
            except (TypeError, ValueError):
                aliases = {}
            r["merged_ids"] = aliases.get("merged_ids") or []
        return rows
    except Exception as exc:
        print(f"[WARN] MySQL 直读失败（{exc}），退回 API（缺 blast_genome_db）", file=sys.stderr)
    url = api.rstrip("/") + "/api/genomes?limit=500&include_hidden=true"
    with urllib.request.urlopen(url, timeout=60) as resp:
        payload = json.load(resp)
    data = payload.get("data")
    if isinstance(data, dict):
        data = data.get("items") or data.get("genomes") or []
    return data or []


def enumerate_dbs(blastdb: pathlib.Path):
    """返回 (genome_dbs, transcript_dbs, protein_dbs)。

    - genome: *.genome / *.scaffold 的 BLAST 库（含多卷 .nal）
    - transcript: 其余核苷酸库（排除基因组库、按染色体拆分库、all_* 聚合库）
    - protein: 其余蛋白库（排除 all_* 聚合库）
    """
    nuc, prot = set(), set()
    for p in blastdb.glob("*"):
        n = p.name
        for suf in (".nhr", ".nal"):
            if n.endswith(suf):
                b = re.sub(r"\.\d{2,}$", "", n[: -len(suf)])
                nuc.add(b)
        for suf in (".phr", ".pal"):
            if n.endswith(suf):
                b = re.sub(r"\.\d{2,}$", "", n[: -len(suf)])
                prot.add(b)
    genomes = {b for b in nuc if b.endswith((".genome", ".scaffold"))}
    split = {b for b in nuc if re.search(r"\.(genome|scaffold)_Chr", b)}
    cds = {b for b in nuc - genomes - split if not b.startswith("all_") and not re.match(r"all\d+_genomes$", b)}
    pep = {b for b in prot if not b.startswith("all_") and not re.match(r"all\d+_genomes$", b)}
    return genomes, cds, pep



def parse_html_options(html_path: str) -> list[str]:
    try:
        text = pathlib.Path(html_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    vals = re.findall(r'<option\s+[Vv][Aa][Ll][Uu][Ee]\s*=\s*"(.*?)"', text, re.S | re.I)
    vals += re.findall(r"<option\s+[Vv][Aa][Ll][Uu][Ee]\s*=\s*'(.*?)'", text, re.S | re.I)
    return [v.strip() for v in vals]


GENE_PROT_SUFFIX = re.compile(r"(\.(pep|cds)$|_pep$|_protein$|__pro$|_cds$)", re.I)


def is_genome_option(v: str) -> bool:
    if not v or v in ("all_genomes", "all_gene", "all_genes", "all_protein", "all_proteins"):
        return False
    if v.startswith("all_") or GENE_PROT_SUFFIX.search(v):
        return False
    return True


def has_split(blastdb: pathlib.Path, db: str) -> bool:
    return bool(glob.glob(str(blastdb / (db + "_Chr*.nhr"))) or glob.glob(str(blastdb / (db + "_Chr*.nal"))))


def alias_text(title: str, members: list[str]) -> str:
    return f"TITLE {title}\nDBLIST " + " ".join(sorted(members)) + "\n"


def backup(path: pathlib.Path) -> pathlib.Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dst = path.with_name(path.name + ".bak-" + stamp)
    shutil.copy2(path, dst)
    return dst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blastdb", default="/var/www/html/getfasta/blastdb")
    ap.add_argument("--html", default="/var/www/html/getfasta/index.html")
    ap.add_argument("--doc", default="/var/www/html/doc/getsequence_search.txt")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--legacy-html", default="/var/www/html/getfasta/index.html.bak-20261023_160218",
                    help="含旧下拉框（逐基因组选项）的 HTML 备份，用于发现自定义命名的组装库")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    bd = pathlib.Path(args.blastdb)
    reg = fetch_registry(args.api)
    print(f"registry rows: {len(reg)}")
    db_level = {}
    ds_meta = {}
    alias_meta = {}
    for r in reg:
        ds = r.get("dataset_id") or ""
        db = (r.get("blast_genome_db") or "").strip()
        lvl = (r.get("assembly_level") or "").strip()
        ds_meta[ds] = {"db": db, "level": lvl, "chr": r.get("chromosome_count")}
        for key in (db, db + ".genome" if db and not db.endswith(".genome") else ""):
            if key:
                db_level[key] = lvl
        for old in (r.get("merged_ids") or []):
            alias_meta[old] = ds_meta[ds]
    genomes, cds, pep = enumerate_dbs(bd)
    # 旧页面里非 .genome/.scaffold 后缀、但确实是组装库的（TGACv2 / TGAC_WGS_* / TSL_WGS_* / .all.denovo 等）
    legacy = args.legacy_html
    if legacy and pathlib.Path(legacy).is_file():
        legacy_vals = parse_html_options(legacy)
    else:
        legacy_vals = []
    CUSTOM_GENOME_SKIP = re.compile(r"(NLR|_gene$|gene$|transcript|mrna|cdna|\.pep$|_pep$|_protein$|\.protein$|__pro$|\.cds$|_cds$)", re.I)
    for v in legacy_vals:
        if not is_genome_option(v) or CUSTOM_GENOME_SKIP.search(v):
            continue
        if (bd / (v + ".nhr")).exists() or (bd / (v + ".nal")).exists():
            genomes.add(v)
    # 自定义组装库归入 genome 后，从 transcript 集合里剔除；NLR 等非转录本集合也排除
    cds = {c for c in cds if c not in genomes and not re.search(r"NLR", c, re.I)}

    # registry 里的 blast_genome_db（可能不以 .genome 结尾，如 TGACv2 / 自定义名）
    for r in reg:
        db = (r.get("blast_genome_db") or "").strip()
        if not db or db in genomes:
            continue
        if (bd / (db + ".nhr")).exists() or (bd / (db + ".nal")).exists():
            genomes.add(db)
    # 旧页面下拉里的 genome 选项（排除 gene/protein 选项），能对应到索引文件的也纳入
    old_opts = parse_html_options(args.html)
    for v in old_opts:
        if not is_genome_option(v):
            continue
        if (bd / (v + ".nhr")).exists() or (bd / (v + ".nal")).exists():
            genomes.add(v)
    print(f"enumerated: genomes={len(genomes)} cds={len(cds)} pep={len(pep)} (old options: {len(old_opts)})")

    def is_chrom(db: str) -> bool:
        if db in OVERRIDES:
            return OVERRIDES[db]
        # 有按染色体拆分库 = 染色体水平（最可靠，不依赖 registry 是否填了 level）
        if has_split(bd, db) or has_split(bd, db + ".genome"):
            return True
        lvl = db_level.get(db) or db_level.get(db + ".genome", "")
        return lvl in CHROM_LEVELS

    chrom = sorted(d for d in genomes if is_chrom(d))
    other = sorted(d for d in genomes if d not in set(chrom))
    print(f"chromosome-level: {len(chrom)} | other: {len(other)}")
    print("  chrom sample:", chrom[:3], "...", chrom[-2:])
    print("  other:", other)

    # 文档 Library 列回填
    doc_lines = pathlib.Path(args.doc).read_text(encoding="utf-8", errors="replace").splitlines()
    header = doc_lines[0].split("\t") if doc_lines else []
    if header and len(header) == 3 and header[0].startswith("Getsequence Name"):
        doc_lines[0] = doc_lines[0] + "\tLibrary"
    elif header and len(header) >= 4:
        pass
    else:
        doc_lines.insert(0, "Getsequence Name\tGetsequence Search example\tGene example\tLibrary")

    by_ds = ds_meta
    by_norm = {}
    for ds, meta in ds_meta.items():
        if meta["db"]:
            for k in (ds, meta["db"]):
                by_norm.setdefault(norm_name(k), meta)
    for old, meta in alias_meta.items():
        if meta["db"]:
            by_norm.setdefault(norm_name(old), meta)
    all_db_norm = {norm_name(d): d for d in genomes}

    stats = {"all_genomes": 0, "all_other_genomes": 0, "?": 0}
    unknown_names = []
    for i in range(1, len(doc_lines)):
        if not doc_lines[i].strip():
            continue
        cols = doc_lines[i].split("\t")
        if len(cols) < 3:
            continue
        name = cols[0].strip()
        meta = by_ds.get(name) or by_norm.get(norm_name(name))
        db = meta["db"] if meta else all_db_norm.get(norm_name(name))
        if not db:
            db = name if name.endswith((".genome", ".scaffold")) else name + ".genome"
        db_for = db
        if db_for and not db_for.endswith((".genome", ".scaffold")):
            db_for = db_for + ".genome"
        if db_for and db_for.endswith((".genome", ".scaffold")):
            lib = "all_genomes" if is_chrom(db_for) else "all_other_genomes"
        else:
            lib = "?"
            unknown_names.append(name)
        stats[lib] += 1
        doc_lines[i] = "\t".join(cols[:3] + [lib] + cols[4:])
    print("doc library stats:", stats, "total rows:", len(doc_lines) - 1)
    if unknown_names:
        print("unmatched doc rows:", unknown_names)

    # 新下拉框
    html = pathlib.Path(args.html).read_text(encoding="utf-8", errors="replace")
    new_select = (
        '<select name="database">\n'
        '        <option VALUE="all_genomes">all genomes (chromosome level)</option>\n'
        '        <option VALUE="all_genes">all genes (transcripts)</option>\n'
        '        <option VALUE="all_proteins">all proteins</option>\n'
        '        <option VALUE="all_other_genomes">other genomes (non-chromosome level, combined)</option>\n'
        '    </select>'
    )
    html2, n_sub = re.subn(r'<select name="database">.*?</select>', new_select, html, count=1, flags=re.S)
    print("select replaced:", n_sub)

    chrom = [m for m in chrom if m not in INVALID_DB_MEMBERS]
    other = [m for m in other if m not in INVALID_DB_MEMBERS]
    cds = [m for m in sorted(cds) if m not in INVALID_DB_MEMBERS]
    pep = [m for m in sorted(pep) if m not in INVALID_DB_MEMBERS]
    alias_files = {
        "all_genomes.nal": alias_text("all_genomes_at_chromosome_level", chrom),
        "all_other_genomes.nal": alias_text("all_other_genomes_non_chromosome_level", other),
        "all_genes.nal": alias_text("ALL gene/transcript database", cds),
        "all_gene.nal": alias_text("ALL gene database", cds),
        "all_proteins.pal": alias_text("ALL proteins", pep),
        "all_protein.pal": alias_text("ALL proteins", pep),
    }
    if not args.apply:
        print("\n[DRY-RUN] 待写入 aggregate 文件:")
        for fn, text in alias_files.items():
            print(f"  {fn}: members={len(text.split('DBLIST ')[1].split())}")
        print("[DRY-RUN] html select 已生成，未写文件")
        return 0

    # 写 aliases
    for fn, text in alias_files.items():
        p = bd / fn
        if p.exists():
            b = backup(p)
            print(f"backup {fn} -> {b.name}")
        p.write_text(text, encoding="utf-8")
        print(f"[OK] {fn}")
    # 写 html
    hp = pathlib.Path(args.html)
    hb = backup(hp)
    hp.write_text(html2, encoding="utf-8")
    print(f"[OK] {args.html}（备份 {hb.name}）")
    # 写 doc
    dp = pathlib.Path(args.doc)
    db_ = backup(dp)
    dp.write_text("\n".join(doc_lines) + "\n", encoding="utf-8")
    print(f"[OK] {args.doc}（备份 {db_.name}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
