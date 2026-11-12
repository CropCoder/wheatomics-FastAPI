#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""accept_aegilops4_onboarding.py — 4 个二倍体 Aegilops 上线验收（服务器侧，逐条核对规则）

运行位置：生产机 wheatomics（fei），在 /var/www/data/masw_data 可写、API 127.0.0.1:8000 可访问。
输出：逐条 [PASS]/[FAIL] 清单 + JSON 汇总（--json out.json）；任一 FAIL 退出码 1。

覆盖规则（对应 SOP G5 / 主计划 §9）：
  A. 每基因组：genome_registry 行、BLAST 库（含分类）、blastdbcmd 统计、JBrowse refseq/轨道/API、
     getfasta（all_genomes + by-interval）、PrimerServer2、Genefunc 表行数、registry 行、
     实弹 BLAST（自身基因组库）、BLAST↔JBrowse 跳转
  B. 全局计数：/api/genomes/stats、blast 库计数与分类、jbrowse datasets、Genefunc registry/tables、
     docroot jbrowse.html（hero/命名数/组数/卡片数/每卡存在）、静态页 CC/NN 数组、BLAST↔JBrowse 映射
  C. 回归：既有基因组 API / getfasta / BLAST 库仍在
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

API = os.environ.get("WHEATOMICS_API", "http://127.0.0.1:8000")
DATA_ROOT = os.environ.get("WHEATOMICS_DATA_ROOT", "/var/www/data/masw_data")
REPO = os.environ.get("WHEATOMICS_REPO", "/var/www/FastAPI_backend_Port8000")
DOCROOT = os.environ.get("WHEATOMICS_DOCROOT", "/var/www/html")
BLASTBIN = os.environ.get("WHEATOMICS_BLASTX", "/var/www/html/blast/blast+/bin")
BLASTDB = os.environ.get("WHEATOMICS_BLASTDB", "/var/www/html/getfasta/blastdb")
JBROWSE = os.environ.get("WHEATOMICS_JBROWSE", "/var/www/html/jbrowse-1.12.3-release")
DDL_ENV = os.environ.get("WHEATOMICS_DDL_ENV", "/etc/wheatomics/db_ddl.env")
ZJW_PY = os.environ.get("WHEATOMICS_ZJW_PY", "/home/fei/mambaforge/envs/zjw/bin/python3")

# 期望值（4 个二倍体 Aegilops）
SPECS = [
    dict(ploidy="MM", tag="Aegilops_comosa_IPK_AE783", prefix="AeCom.AE783.r1.",
         acc="GCA_052815735.2", species="Aegilops comosa", cultivar="IPK-AE783",
         nseq=17, nchr=7, genes=51203, size=4407741597, unplaced_genes=38, chr1="Chr1M"),
    dict(ploidy="CC", tag="Aegilops_markgrafii_EKC105_RL5723", prefix="AeMar.EKC105.r1.",
         acc="GCA_052815875.1", species="Aegilops markgrafii", cultivar="EKC105_RL5723",
         nseq=24, nchr=7, genes=47246, size=3577170360, unplaced_genes=53, chr1="Chr1C"),
    dict(ploidy="UU", tag="Aegilops_umbellulata_IPK_AE740", prefix="AeUmb.AE740.r1.",
         acc="GCA_060308565.1", species="Aegilops umbellulata", cultivar="IPK-AE740",
         nseq=250, nchr=7, genes=49677, size=4268089219, unplaced_genes=1103, chr1="Chr1U"),
    dict(ploidy="NN", tag="Aegilops_uniaristata_IPK_AE680", prefix="AeUna.AE680.r1.",
         acc="GCA_052765.1", species="Aegilops uniaristata", cultivar="IPK-AE680",
         nseq=21, nchr=7, genes=50416, size=4475943907, unplaced_genes=66, chr1="Chr1N"),
]
SPECS[3]["acc"] = "GCA_052815765.1"   # 防手误

PLOIDY_EXPECT = {"MM": 2, "CC": 1, "UU": 3, "NN": 1}
BASELINE = dict(genomes=316, blastn=2924, blastp=193, jbrowse=219, genefunc=216, tables=224)
EXPECT = dict(genomes=320, blastn=2960, blastp=197, jbrowse=223, genefunc=220, tables=228,
              hero=217, named=210, groups=24, cards=214)

RESULTS = []


def add(rule, desc, ok, detail=""):
    RESULTS.append(dict(rule=rule, desc=desc, ok=bool(ok), detail=str(detail)[:500]))
    print(("[PASS] " if ok else "[FAIL] ") + rule + " " + desc + (("  | " + str(detail)[:300]) if detail else ""))


def http_get(path, timeout=60, raw=False):
    url = API + path
    with urllib.request.urlopen(url, timeout=timeout) as r:
        data = r.read()
    if raw:
        return data
    return json.loads(data.decode("utf-8"))


def http_post_form(path, fields, timeout=180):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(API + path, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def run(cmd, timeout=120, cwd=None):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def read_fai(path):
    d = {}
    if not os.path.isfile(path):
        return d
    for line in open(path):
        f = line.rstrip("\n").split("\t")
        if len(f) >= 2:
            d[f[0]] = int(f[1])
    return d


def read_ddl_env():
    cred = {}
    try:
        for line in open(DDL_ENV):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                cred[k.strip()] = v.strip()
    except OSError:
        pass
    return cred


def mysql_scalar(sql, timeout=60):
    cred = read_ddl_env()
    cmd = ["mysql", "-h", cred.get("DB_HOST", "localhost"),
           "-u", cred.get("DB_USER", "wheatomics_ddl"),
           "-p" + cred.get("DB_PASS", ""), "-N", "-B", "-e", sql]
    rc, out = run(cmd, timeout=timeout)
    lines = [ln.strip() for ln in out.splitlines()
             if ln.strip() and not ln.startswith("mysql: [Warning]")
             and not ln.startswith("ERROR")]
    return rc, "\n".join(lines)


def blastdb_info(db):
    rc, out = run([os.path.join(BLASTBIN, "blastdbcmd"), "-db", db, "-info"], timeout=120)
    if rc != 0:
        return None, out
    info = {"sequences": None, "total_length": None}
    m = re.search(r"(\d+) sequences;\s*([\d,]+) total bases", out)
    if m:
        info["sequences"] = int(m.group(1))
        info["total_length"] = int(m.group(2).replace(",", ""))
    return info, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="/tmp/accept_aegilops4_onboarding.json")
    ap.add_argument("--skip-blast", action="store_true", help="跳过实弹 BLAST（省时间）")
    args = ap.parse_args()

    # ---------- B 全局：counts ----------
    try:
        stats = http_get("/api/genomes/stats")["data"]
        totals, by_ploidy, by_ann = stats["totals"], stats["by_ploidy"], stats["by_annotation_status"]
        add("B01", "/api/genomes/stats total == 325（316 基线 + 4 新 + 5 个 rebuild 登记的既有平台数据集）", totals.get("total") == 325, totals.get("total"))
        pl = {x["ploidy"]: x["n"] for x in by_ploidy}
        ok = all(pl.get(k) == v for k, v in PLOIDY_EXPECT.items())
        add("B02", "by_ploidy MM/CC/UU/NN = 2/1/3/1", ok, {k: pl.get(k) for k in PLOIDY_EXPECT})
        ann = {x["annotation_status"]: x["n"] for x in by_ann}
        add("B03", "annotation_status available == 216（211 + 4 新 + 1 既有登记）", ann.get("available") == 216, ann.get("available"))
        add("B04", "registry totals (jbrowse/gene_function/getfasta/primerserver)",
            totals.get("jbrowse") == "219" and totals.get("gene_function") == "219"
            and totals.get("getfasta") == "203" and totals.get("primerserver") == "207",
            {k: totals.get(k) for k in ("jbrowse", "gene_function", "getfasta", "primerserver", "web_blast")})
    except Exception as e:  # noqa: BLE001
        add("B01", "/api/genomes/stats 可访问", False, repr(e))

    try:
        bn = http_get("/api/blast/databases?program=blastn")
        bp = http_get("/api/blast/databases?program=blastp")
        nuc = bn["nucleotide"]["count"]
        prot = bp["protein"]["count"]
        cats_n = {c["id"]: c["count"] for c in bn["categories"]}
        cats_p = {c["id"]: c["count"] for c in bp["categories"]}
        add("B05", "blastn 库数 == %d" % EXPECT["blastn"], nuc == EXPECT["blastn"], nuc)
        add("B06", "blastn other_triticeae == 473（439 + 新 36 − 2 个 RR_rye_weining2 归入 rye）", cats_n.get("other_triticeae") == 473, cats_n.get("other_triticeae"))
        add("B07", "blastp 库数 == %d" % EXPECT["blastp"], prot == EXPECT["blastp"], prot)
        add("B08", "blastp other_triticeae == 34（31 + 新 4 − 1 个 RR_rye_weining2 归入 rye）", cats_p.get("other_triticeae") == 34, cats_p.get("other_triticeae"))
    except Exception as e:  # noqa: BLE001
        add("B05", "blast databases API", False, repr(e))

    try:
        jb = http_get("/api/jbrowse/datasets")["data"]
        add("B09", "jbrowse datasets == %d" % EXPECT["jbrowse"], jb.get("total") == EXPECT["jbrowse"], jb.get("total"))
    except Exception as e:  # noqa: BLE001
        add("B09", "jbrowse datasets API", False, repr(e))

    try:
        reg = http_get("/api/genes/functions/registry")["data"]
        rows = reg.get("records", [])
        add("B10", "Genefunc_registry rows == %d" % EXPECT["genefunc"], len(rows) == EXPECT["genefunc"], len(rows))
        add("B11", "Genefunc_registry 4 张新表", all(any(r.get("table_name") == "Genefunc_%s_%s_table" % (s["ploidy"], s["tag"]) for r in rows) for s in SPECS))
    except Exception as e:  # noqa: BLE001
        add("B10", "Genefunc registry API", False, repr(e))

    try:
        tb = http_get("/api/genes/functions/tables")["data"]
        add("B12", "Genefuncdb total_tables == %d" % EXPECT["tables"], tb.get("total_tables") == EXPECT["tables"], tb.get("total_tables"))
    except Exception as e:  # noqa: BLE001
        add("B12", "genes/functions/tables API", False, repr(e))

    # ---------- B 前端 ----------
    jb_html = os.path.join(DOCROOT, "jbrowse.html")
    try:
        html = open(jb_html, encoding="utf-8", errors="replace").read()
        hero = re.search(r'news-stat"><strong>(\d+)</strong> assemblies', html)
        named = re.search(r'Showing <strong>(\d+)</strong> named assemblies in <strong>(\d+)</strong> genome groups', html)
        cards = len(re.findall(r'<article class="asm-card"', html))
        add("B13", "jbrowse.html hero == %d" % EXPECT["hero"], hero and int(hero.group(1)) == EXPECT["hero"], hero.group(1) if hero else "n/a")
        add("B14", "jbrowse.html named/groups == %d/%d" % (EXPECT["named"], EXPECT["groups"]),
            named and int(named.group(1)) == EXPECT["named"] and int(named.group(2)) == EXPECT["groups"],
            (named.group(1), named.group(2)) if named else "n/a")
        add("B15", "jbrowse.html asm-card 数 == 210（206 基线 + 4）", cards == 210, cards)
        for s in SPECS:
            ds = s["ploidy"] + "_" + s["tag"]
            add("B16." + s["ploidy"], "jbrowse 卡片存在：%s" % ds, ("?data=" + ds) in html)
    except Exception as e:  # noqa: BLE001
        add("B13", "读取 docroot jbrowse.html", False, repr(e))

    pages = {
        "interval": "app/static/interval/index.html",
        "PfamSearch": "app/static/PfamSearch/index.html",
        "caps": "app/static/caps/index.html",
    }
    for name, rel in pages.items():
        try:
            txt = open(os.path.join(REPO, rel), encoding="utf-8", errors="replace").read()
            m = re.search(r"id:\s*'diploid'[^\n]*groups:\s*\[([^\]]+)\]", txt)
            groups = [x.strip().strip("'") for x in m.group(1).split(",")] if m else []
            add("B17." + name, "%s diploid 数组含 CC/NN" % name, "CC" in groups and "NN" in groups, groups)
        except Exception as e:  # noqa: BLE001
            add("B17." + name, "读取 %s" % rel, False, repr(e))

    # ---------- B BLAST↔JBrowse map ----------
    try:
        rc, out = run([ZJW_PY, "scripts/build_blast_jbrowse_map.py", "--check"], cwd=REPO, timeout=600)
        add("B18", "build_blast_jbrowse_map.py --check rc=0", rc == 0, out.strip().splitlines()[-1] if out.strip() else "rc=%d" % rc)
    except Exception as e:  # noqa: BLE001
        add("B18", "BLAST↔JBrowse 映射检查", False, repr(e))

    # ---------- A 每基因组 ----------
    for s in SPECS:
        ds = s["ploidy"] + "_" + s["tag"]
        tag = s["tag"]
        dir_ = os.path.join(DATA_ROOT, ds)
        # A01 registry row
        try:
            row = http_get("/api/genomes/" + urllib.parse.quote(ds)).get("data") or {}
            checks = {
                "species": row.get("species") == s["species"],
                "ploidy": row.get("ploidy") == s["ploidy"],
                "subgenomes": (row.get("subgenomes") or "") == s["ploidy"][0],
                "accession": row.get("assembly_accession") == s["acc"],
                "assembly_level": (row.get("assembly_level") or "").lower() == "chromosome",
                "chromosome_count": row.get("chromosome_count") == 7,
                "genome_size": row.get("genome_size") == s["size"],
                "gene_count": row.get("gene_count") == s["genes"],
                "doi": row.get("doi") == "10.1186/s12870-026-10046-2",
                "annotation_status": row.get("annotation_status") == "available",
            }
            bad = [k for k, v in checks.items() if not v]
            add("A01." + s["ploidy"], "%s genome_registry 字段齐全正确" % ds, not bad, "bad=" + ",".join(bad) if bad else "ok")
        except Exception as e:  # noqa: BLE001
            add("A01." + s["ploidy"], "%s /api/genomes/{ds}" % ds, False, repr(e))

        # A02 blast dbs & classification
        try:
            bn = http_get("/api/blast/databases?program=blastn")
            bp = http_get("/api/blast/databases?program=blastp")
            names_n = set(bn["nucleotide"]["databases"])
            names_p = set(bp["protein"]["databases"])
            need_n = {ds + ".genome"} | {("%s.genome_Chr%s%s" % (ds, c, s["ploidy"][0])) for c in "1234567"} | {ds + ".add_Description.cds"}
            missing = sorted(need_n - names_n)
            need_p = {ds + ".add_Description.pep"}
            missing_p = sorted(need_p - names_p)
            add("A02." + s["ploidy"], "%s 核酸库(+9)/蛋白库(+1)存在" % ds,
                not missing and not missing_p,
                ("missing_nuc=" + ",".join(missing[:5]) if missing else "") +
                (" missing_prot=" + ",".join(missing_p[:5]) if missing_p else "") or "ok")
            other = next((c for c in bn["categories"] if c["id"] == "other_triticeae"), None)
            other_dbs = set((other or {}).get("databases") or [])
            add("A03." + s["ploidy"], "%s 分类 other_triticeae" % ds,
                other is not None and (ds + ".genome") in other_dbs,
                "genome_in_other=%s" % ((ds + ".genome") in other_dbs))
        except Exception as e:  # noqa: BLE001
            add("A02." + s["ploidy"], "%s blast 库清单" % ds, False, repr(e))

        # A04 blastdbcmd 统计
        try:
            info, raw = blastdb_info(os.path.join(BLASTDB, ds + ".genome"))
            ok = info and info["sequences"] == s["nseq"] and info["total_length"] == s["size"]
            add("A04." + s["ploidy"], "%s 整基因组库 %d seqs / %d bp" % (ds, s["nseq"], s["size"]), ok,
                info if info else raw[-150:])
            fai = read_fai(os.path.join(dir_, tag + ".fa.fai"))
            chr_len = fai.get(s["chr1"])
            cinfo, craw = blastdb_info(os.path.join(BLASTDB, "%s.genome_%s" % (ds, s["chr1"])))
            add("A05." + s["ploidy"], "%s 染色体库 %s（1 seq / 长度一致）" % (ds, s["chr1"]),
                cinfo and cinfo["sequences"] == 1 and cinfo["total_length"] == chr_len,
                (cinfo, chr_len) if cinfo else craw[-150:])
        except Exception as e:  # noqa: BLE001
            add("A04." + s["ploidy"], "%s blastdbcmd" % ds, False, repr(e))

        # A06 JBrowse
        try:
            refs = json.load(open(os.path.join(JBROWSE, ds, "seq", "refSeqs.json")))
            add("A06." + s["ploidy"], "%s JBrowse refSeqs == %d" % (ds, s["nseq"]), len(refs) == s["nseq"], len(refs))
            tl = os.path.join(JBROWSE, ds, "trackList.json")
            txt = open(tl, encoding="utf-8").read() if os.path.isfile(tl) else ""
            add("A07." + s["ploidy"], "%s JBrowse all_gene 轨道存在" % ds, "all_gene" in txt)
            td = os.path.join(JBROWSE, ds, "tracks", "all_gene", s["chr1"], "trackData.json")
            add("A08." + s["ploidy"], "%s all_gene/%s trackData.json 存在" % (ds, s["chr1"]), os.path.isfile(td))
            api = http_get("/api/jbrowse/datasets/" + urllib.parse.quote(ds) + "/trackList")
            add("A09." + s["ploidy"], "%s trackList API 200" % ds, isinstance(api, dict))
        except Exception as e:  # noqa: BLE001
            add("A06." + s["ploidy"], "%s JBrowse 检查" % ds, False, repr(e))

        # A10 getfasta
        try:
            chr_api = http_get("/api/sequence/chromosomes?database=all_genomes&pattern=" + urllib.parse.quote(tag))["data"]
            cnt = chr_api.get("count", 0)
            add("A10." + s["ploidy"], "%s all_genomes 染色体命中 >= %d" % (ds, s["nchr"]), cnt >= s["nchr"], cnt)
            region = "%s_%s:1000-1080" % (s["chr1"], tag)
            fa = http_get("/api/sequence/by-interval?region=%s&database=all_genomes" % urllib.parse.quote(region))["data"]["fasta"]
            add("A11." + s["ploidy"], "%s by-interval 返回 FASTA" % ds, fa.startswith(">") and len(fa) > 100, fa[:80].replace("\n", " "))
        except Exception as e:  # noqa: BLE001
            add("A10." + s["ploidy"], "%s getfasta" % ds, False, repr(e))

        # A12 PrimerServer2
        try:
            ps = json.loads(http_get("/api/PrimerServer2/databases", raw=True).decode())
            groups = {g["name"]: g.get("databases", {}) for g in ps.get("groups", [])}
            has_g = (ds + ".genome") in groups.get("genome", {})
            has_c = (ds + ".add_Description.cds") in groups.get("gene", {})
            add("A12." + s["ploidy"], "%s PrimerServer2 genome/gene 库在列" % ds, has_g and has_c)
            raw = http_get("/api/PrimerServer2/databases/%s.genome/sequences" % urllib.parse.quote(ds), raw=True)
            nlines = len([l for l in raw.decode().splitlines() if l.strip()])
            add("A13." + s["ploidy"], "%s PrimerServer2 sequences == %d" % (ds, s["nseq"]), nlines == s["nseq"], nlines)
        except Exception as e:  # noqa: BLE001
            add("A13." + s["ploidy"], "%s PrimerServer2" % ds, False, repr(e))

        # A14 MySQL 行数
        try:
            rc, out = mysql_scalar("SELECT COUNT(*) FROM Genefuncdb.Genefunc_%s_%s_table;" % (s["ploidy"], tag))
            digits = "".join(ch for ch in out if ch.isdigit())
            n = int(digits) if rc == 0 and digits else None
            add("A14." + s["ploidy"], "%s Genefunc 表行数 == %d" % (ds, s["genes"]), n == s["genes"], out[-120:])
        except Exception as e:  # noqa: BLE001
            add("A14." + s["ploidy"], "%s MySQL" % ds, False, repr(e))

        # A15 BLAST 实弹
        if not args.skip_blast:
            try:
                cds_path = os.path.join(dir_, tag + ".cds")
                seq = ""
                with open(cds_path) as fh:
                    for line in fh:
                        if line.startswith(">"):
                            if seq:
                                break
                            continue
                        seq += line.strip()
                        if len(seq) >= 160:
                            break
                seq = seq[:160]
                r = http_post_form("/api/blast/search", {
                    "program": "blastn", "database": ds + ".genome",
                    "query": ">probe\n" + seq, "wait": "true", "evalue": "1e-5"})
                rows = (r.get("attribution") or {}).get("rows", 0)
                add("A15." + s["ploidy"], "%s 实弹 blastn（CDS 探针→整基因组库）有命中" % ds,
                    bool(r.get("success")) and rows > 0, "rows=%s" % rows)
            except Exception as e:  # noqa: BLE001
                add("A15." + s["ploidy"], "%s 实弹 BLAST" % ds, False, repr(e))

        # A16 BLAST↔JBrowse 跳转
        try:
            j = http_get("/api/blast/database/%s.genome/jbrowse" % urllib.parse.quote(ds))
            add("A16." + s["ploidy"], "%s BLAST 结果可跳 JBrowse" % ds, bool(j.get("available")), j.get("reason"))
        except Exception as e:  # noqa: BLE001
            add("A16." + s["ploidy"], "%s BLAST↔JBrowse API" % ds, False, repr(e))

        # A17 GetSequence by-gene（蛋白侧，all_proteins）
        try:
            gids = s.get("example_cds")
            if not gids:
                # 从 Genefunc_registry 取该数据集的 example_cds（页面芯片同一来源）
                reg = http_get("/api/genes/functions/registry")["data"]["records"]
                row = next((r for r in reg if r.get("table_name") == "Genefunc_%s_%s_table" % (s["ploidy"], tag)), None)
                gids = (row or {}).get("example_cds")
            bg = http_get("/api/sequence/by-gene?gene_id=%s&protein_db=all_proteins"
                          % urllib.parse.quote(gids or ""), timeout=60)
            prot = (bg.get("data") or bg or {}).get("protein_sequence") or ""
            add("A17." + s["ploidy"], "%s GetSequence by-gene 蛋白可取（%s）" % (ds, gids), len(prot) > 0,
                "protein_len=%d" % len(prot))
        except Exception as e:  # noqa: BLE001
            add("A17." + s["ploidy"], "%s GetSequence by-gene 蛋白" % ds, False, repr(e))

        # A18 GetSequence batch（CDS 聚合库 all_genes）
        try:
            gids = s.get("example_cds")
            if not gids:
                reg = http_get("/api/genes/functions/registry")["data"]["records"]
                row = next((r for r in reg if r.get("table_name") == "Genefunc_%s_%s_table" % (s["ploidy"], tag)), None)
                gids = (row or {}).get("example_cds")
            bt = http_get("/api/sequence/batch?database=all_genes&ID=%s" % urllib.parse.quote(gids or ""), timeout=90)
            okn = (bt.get("data") or {}).get("succeeded", 0)
            add("A18." + s["ploidy"], "%s GetSequence batch 可取 CDS（all_genes）" % ds, okn == 1, "succeeded=%s" % okn)
        except Exception as e:  # noqa: BLE001
            add("A18." + s["ploidy"], "%s GetSequence batch CDS" % ds, False, repr(e))

        # A19 GetSequence 文档示例行（getsequence_search.txt）
        try:
            doc = os.path.join(DOCROOT, "doc", "getsequence_search.txt")
            lines = [ln.rstrip("\n") for ln in open(doc, encoding="utf-8", errors="replace")]
            want = ds + "\t"
            hit = [ln for ln in lines if ln.startswith(want)]
            add("A19." + s["ploidy"], "%s getsequence_search.txt 有本基因组行" % ds, bool(hit),
                (hit[0].split("\t")[1] if hit else "missing"))
        except Exception as e:  # noqa: BLE001
            add("A19." + s["ploidy"], "%s getsequence_search.txt" % ds, False, repr(e))

    # ---------- C 回归 ----------
    try:
        r = http_get("/api/genomes?q=AK58")
        add("C01", "旧基因组 AK58 registry 可查", r["data"]["total"] >= 1, r["data"]["total"])
        fa = http_get("/api/sequence/by-interval?region=Chr1A_AK58:1000-1080&database=all_genomes")["data"]["fasta"]
        add("C02", "旧序列 all_genomes by-interval 正常", fa.startswith(">Chr1A_AK58"), fa[:60].replace("\n", " "))
        bn = http_get("/api/blast/databases?program=blastn")
        add("C03", "旧 BLAST 库 AABBDD_AK58.genome 仍在", "AABBDD_AK58.genome" in set(bn["nucleotide"]["databases"]))
    except Exception as e:  # noqa: BLE001
        add("C01", "回归检查", False, repr(e))

    # ---------- 汇总 ----------
    fails = [r for r in RESULTS if not r["ok"]]
    print()
    print("=" * 78)
    print("TOTAL %d checks | PASS %d | FAIL %d" % (len(RESULTS), len(RESULTS) - len(fails), len(fails)))
    if fails:
        print("FAILED RULES:", ", ".join(r["rule"] for r in fails))
    payload = {"total": len(RESULTS), "pass": len(RESULTS) - len(fails), "fail": len(fails), "results": RESULTS}
    with open(args.json, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print("json:", args.json)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
