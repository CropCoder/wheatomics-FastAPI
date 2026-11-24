#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 genome_registry 里被写错的 DOI / 标题（2026-11-24 核查批次）。

背景
----
`wheatomics_db.genome_registry` 的 DOI 来自三个来源（``--doi`` 参数、
``Genefuncdb.Genefunc_registry.Doi``、``jbrowse.html``/``cite.html`` 抓取），
历史上没有任何一处做 Crossref 校验。2026-11-24 核查发现两类错误：

1. ``cite.html`` 有若干条写成 ``…sequences,please cite:``（漏空格），旧解析
   正则会把下一条整段吞进 trigger，导致 DOI 串位 —— ``rye_weining2`` 和
   ``Elymus_sibiricus_cultivar_Gaomu`` 因此挂上了 Sumai 3 的 DOI；
2. ``jbrowse.html`` 升级 V2（``article.asm-card``）后，注册表脚本仍在找旧版
   ``div.card-body``，所有卡片 DOI 被丢弃，DOI 全部落到关键词回退 ——
   ``Keumkang``/``MOV``/``spelta``/``urartu`` 等因此挂上了别的论文
   （甚至 ``10.1038s41586-018-0108-0`` 这种漏斜杠的字符串）。

本脚本只修**已核实**的行（新 DOI 均经 Crossref 标题比对 + 站点卡片/cite.html/
Genefunc_registry 三方一致），并带 ``WHERE doi = <旧值>`` 保护：线上若已被人
改过就跳过，不会覆盖更新的人工修正。

用法（服务器上，先 source .env）：
    python3 scripts/fix_registry_metadata_2026_11_24.py --dry-run
    python3 scripts/fix_registry_metadata_2026_11_24.py --apply

回滚：/var/www/data/masw_data/_prep/backup_20261124/genome_registry_20261124.sql
"""
from __future__ import annotations

import argparse
import os
import sys

try:
    import pymysql
except ImportError:  # pragma: no cover
    raise SystemExit("需要 pymysql：用 /home/fei/mambaforge/envs/zjw/bin/python3 运行")

DB = "wheatomics_db"
TAG = "2026-11-24 DOI 核查修正"

# dataset_id -> (旧 doi, {字段: 新值})
FIXES: dict[str, tuple[str | None, dict]] = {
    # 站点数据 = Ensembl rye Lo7（GCA_902687465.1, 6,735,227,109 bp）+ 2021 注释
    # （SECCE1Rv1G* 57,222 基因）。策展表里的 2017 草稿行（27,784 HC 基因）与
    # 本站数据不符，不能用来填 DOI/gene_count。
    "rye_Lo7": ("10.1111/tpj.13436", {
        "doi": "10.1038/s41588-021-00807-0",
        "journal": "Nature Genetics",
        "publication_year": 2021,
        "paper_title": "Chromosome-scale genome assembly provides insights into rye biology, "
                       "evolution and agronomic potential",
        "assembly_accession": "GCA_902687465.1",
        "assembly_level": "Chromosome",
        "gene_count": 57222,
        "cultivar_or_line": "Lo7",
        "citation_source": "jbrowse card + cite.html（2026-11-24 人工核对）",
        "notes": f"[{TAG}] DOI 由 2017 草稿改为 Ensembl Lo7 参考基因组论文；"
                 "基因数按 Genefunc_RR_rye_Lo7_table 57,222 计",
    }),
    # 引文写成 ",please cite:" 导致吞掉下一个块，DOI 变成 Sumai 3 的
    "rye_weining2": ("10.1002/tpg2.70285", {
        "doi": "10.1186/s13059-025-03792-3",
        "journal": "Genome Biology",
        "publication_year": 2025,
        "paper_title": "High-resolution genome assembly reveals retrotransposon-mediated "
                       "centromere dynamics in rye",
        "species": "Secale cereale",
        "cultivar_or_line": "Weining",
        "chromosome_count": 7,
        "gene_count": 135453,
        "citation_source": "jbrowse card + cite.html（2026-11-24 人工核对）",
        "notes": f"[{TAG}] 原 DOI 为 Sumai 3（cite.html 串块 bug）；"
                 "Weining v2.0 = 7 chr + ChrUn（7,748,120,638 bp），Genefunc 表 135,453 个 EVM 模型",
    }),
    # 旧解析只认 div.card-body，V2 卡片被整条丢弃后 DOI 来自关键词回退
    "AABBDD_Triticum_aestivum_Keumkang": ("10.1038s41586-018-0108-0", {
        "doi": "10.1038/s41597-026-08617-x",
        "journal": "Scientific Data",
        "publication_year": 2026,
        "paper_title": "Chromosome-level genome assembly of the Korean wheat cultivar Keumkang",
        "citation_source": "jbrowse card + Genefunc_registry（2026-11-24 人工核对）",
        "notes": f"[{TAG}] 原 DOI 为漏斜杠的 T.urartu DOI（关键词回退误写）",
    }),
    "Triticum_spelta_PI190962": ("10.1038s41586-018-0108-0", {
        "doi": "10.1038/s41586-020-2961-x",
        "journal": "Nature",
        "publication_year": 2020,
        "paper_title": "Multiple wheat genomes reveal global variation in modern breeding",
        "citation_source": "jbrowse card（2026-11-24 人工核对）",
        "notes": f"[{TAG}] 原 DOI 为漏斜杠的 T.urartu DOI（关键词回退误写）",
    }),
    "Triticum_aestivum_MOV": ("10.1038s41586-018-0108-0", {
        "doi": "10.1073/pnas.2510889122",
        "journal": "Proceedings of the National Academy of Sciences",
        "publication_year": 2025,
        "paper_title": "WUSCHEL-D1 upregulation enhances grain number by inducing formation "
                       "of multiovary-producing florets in wheat",
        "citation_source": "jbrowse card（2026-11-24 人工核对）",
        "notes": f"[{TAG}] 原 DOI 为漏斜杠的 T.urartu DOI（关键词回退误写）",
    }),
    "Triticum_urartu_PI428250": ("10.1038s41586-018-0108-0", {
        "doi": "10.1038/s41467-026-71539-0",
        "journal": "Nature Communications",
        "publication_year": 2026,
        "paper_title": "LOX-A4 shapes Triticum urartu gene pools and contributions to the "
                       "A subgenome of polyploid wheat",
        "citation_source": "jbrowse card（2026-11-24 人工核对）",
        "notes": f"[{TAG}] 原 DOI 为漏斜杠的 T.urartu v2 DOI；按卡片改为 PI428250 论文",
    }),
    "Elymus_sibiricus_cultivar_Gaomu": ("10.1002/tpg2.70285", {
        "doi": "10.1038/s41597-024-03622-4",
        "journal": "Scientific Data",
        "publication_year": 2024,
        "paper_title": "Chromosome-scale assembly of the wild cereal relative Elymus sibiricus",
        "citation_source": "jbrowse card + cite.html（2026-11-24 人工核对）",
        "notes": f"[{TAG}] 原 DOI 为 Sumai 3（cite.html 串块 bug）",
    }),
    # 卡片无 DOI、Genefunc_registry Doi 为空、策展表无此材料：宁可为空
    "Triticum_aestivum_alchemy": ("10.1038s41586-018-0108-0", {
        "doi": None,
        "journal": None,
        "publication_year": None,
        "paper_title": None,
        "citation_source": None,
        "notes": f"[{TAG}] 清除误填的 T.urartu DOI；该材料在卡片/Genefunc/策展表中均无 DOI，待人工核实",
    }),
}

# 只改标题、不动 DOI 的行（DOI 本身是对的，标题被串块 bug 写成了 Sumai 3）
TITLE_ONLY = {
    "rye_weining": {
        "paper_title": "A high-quality genome assembly highlights rye genomic characteristics "
                       "and agronomically important genes",
        "citation_source": "cite.html（2026-11-24 人工核对）",
    },
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正写库（默认只打印）")
    ap.add_argument("--dry-run", action="store_true", help="只打印将要执行的变更")
    args = ap.parse_args()
    apply = args.apply and not args.dry_run

    conn = pymysql.connect(host=os.environ.get("DB_HOST", "localhost"),
                           port=int(os.environ.get("DB_PORT", "3306")),
                           user=os.environ.get("DB_USER", "wheatomics_user"),
                           password=os.environ.get("DB_PASSWORD"),
                           database=DB, charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    changed = 0
    try:
        with conn.cursor() as cur:
            for ds, (old_doi, fields) in {**FIXES}.items():
                cur.execute("SELECT dataset_id, doi FROM genome_registry WHERE dataset_id=%s", (ds,))
                row = cur.fetchone()
                if not row:
                    print(f"[skip] {ds}: 不在 registry")
                    continue
                if old_doi is not None and (row["doi"] or "") != old_doi:
                    print(f"[skip] {ds}: 当前 doi={row['doi']!r} 已不是已知错误值 {old_doi!r}")
                    continue
                sets = ", ".join(f"`{k}`=%s" for k in fields)
                params = list(fields.values()) + [ds]
                sql = f"UPDATE genome_registry SET {sets} WHERE dataset_id=%s"
                print(f"[{'apply' if apply else 'dry'}] {ds}: {fields.get('doi', '(仅元数据)')}")
                if apply:
                    cur.execute(sql, params)
                changed += 1
            for ds, fields in TITLE_ONLY.items():
                cur.execute("SELECT paper_title FROM genome_registry WHERE dataset_id=%s", (ds,))
                row = cur.fetchone()
                if not row:
                    print(f"[skip] {ds}: 不在 registry")
                    continue
                if "Sumai" not in (row["paper_title"] or ""):
                    print(f"[skip] {ds}: 标题已不是 Sumai 3，跳过")
                    continue
                sets = ", ".join(f"`{k}`=%s" for k in fields)
                print(f"[{'apply' if apply else 'dry'}] {ds}: 仅修标题")
                if apply:
                    cur.execute(f"UPDATE genome_registry SET {sets} WHERE dataset_id=%s",
                                list(fields.values()) + [ds])
                changed += 1
        if apply:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(f"{'已更新' if apply else '将更新'} {changed} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
