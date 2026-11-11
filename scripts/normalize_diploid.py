#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""normalize_diploid.py -- WheatOmics 二倍体（及一般单字母倍性）基因组四件套归一化工具.

为什么需要它
------------
作者提交的基因组 FASTA / GFF3 通常不满足平台 SOP 的硬性命名规则：

1. 基因组 FASTA 头是 NCBI GenBank/WGS 登录号（``>CM127985.1 ...`` /
   ``>JBHEGE020000008.1 ...``），而不是 ``Chr`` 名；
2. GFF3 的 seqid 是作者命名（``1M``..``7M`` / ``1C``..``7C`` / ``1U``..``7U`` /
   ``1N``..``7N`` + scaffold），不是 ``Chr*`` / ``ChrUn_*``；
3. TAMA/GeneMarkS-T 的 ``STRG`` 家族 mRNA ID 以 ``.pN`` 结尾（不满足平台
   "mRNA ID 以 .数字 结尾"），且各物种编号独立，**跨物种重名**；
4. 作者蛋白 FASTA 用 ``.``（部分物种用 ``*``）表示终止符，含内部终止符。

本脚本用 ``assembly_report.txt`` 做 ``Sequence-Name <-> GenBank-Accn`` 的确定性映射，
一次解决上述问题，并提供多文件汇总断言：

子命令
------
* ``fasta``  基因组 FASTA 头改名（GenBank accn -> Chr*/ChrUn_*），写 mapping.tsv
* ``gff3``   GFF3 seqid 改名 + gene/mRNA ID 规范化（两遍流式），写 mapping.tsv /
             id-map，支持跨物种唯一性断言
* ``pep``    蛋白 FASTA 头 ID 规范化（与 gff3 同一套规则）+ ``.``/``*`` 清理
* ``check``  对归一化产物做平台规则的汇总断言（可多文件、可跨物种查重）

平台硬性规则（SOP）
-------------------
* ``.fa``  每条头以 ``Chr`` 开头（未定位序列 ``ChrUn_*``）；
* ``.gff3`` 第 1 列 seqid 以 ``Chr`` 开头；``mRNA`` 的 ``ID=`` 以 ``.数字`` 结尾；
* ``.cds`` / ``.pep`` 序列 ID 以 ``.数字`` 结尾，pep 序列行不含 ``.``（也不应含 ``*``）。

典型用法
--------
::

    # 1) FASTA 改名（NCBI genomic.fna.gz）
    python3 normalize_diploid.py fasta \\
        --fasta GCA_xxx_genomic.fna.gz \\
        --assembly-report GCA_xxx_assembly_report.txt \\
        --out MMTAG.fa --mapping MMTAG.fa.mapping.tsv

    # 1b) 只解析 assembly_report、校验映射（不读 FASTA，适合先做预检）
    python3 normalize_diploid.py fasta --dry-run \\
        --assembly-report GCA_xxx_assembly_report.txt --mapping map.tsv

    # 2) GFF3 归一化（跨物种重复 ID 时必须给 --id-prefix）
    python3 normalize_diploid.py gff3 \\
        --gff3 genes_HC_LC.gff3.gz \\
        --assembly-report GCA_xxx_assembly_report.txt \\
        --out MMTAG.gff3 --mapping MMTAG.gff3.mapping.tsv \\
        --id-prefix "AeCom.AE783." --id-map MMTAG.idmap.tsv \\
        --also-ids /path/to/other_species.idmap.json

    # 3) gffread 生成 CDS/PEP 后清蛋白终止符
    python3 normalize_diploid.py pep --pep in.pep --out MMTAG.pep

    # 4) 汇总断言（dataset 目录含 <MYTAG>.fa/.gff3/.cds/.pep）
    python3 normalize_diploid.py check --dir .

    # 4b) 多文件 / 跨物种断言
    python3 normalize_diploid.py check \\
        --gff3 a.gff3 b.gff3 c.gff3 d.gff3 \\
        --expect-counts 51203,47246,49677,50416 \\
        --expect-unplaced 38,53,1103,66

设计要点
--------
* 纯 Python3 标准库，单文件；Python 3.7+ 可运行（服务器 ``/usr/bin/python3``）。
* 两遍流式处理 GFF3（第一遍收集 gene/mRNA ID 映射，第二遍重写），内存只存 ID 映射，
  不把大文件整体读入内存。
* ``.gz`` 输入按后缀或 gzip magic 自动识别；``--out``/``--mapping`` 以 ``.gz`` 结尾时自动
  压缩写出。
* 只有 ``ID`` / ``Parent`` / ``Derives_from`` / ``Name`` 四个属性的**引用值**会被改写；
  exon/CDS 等子特征的 ID 通过其 ``Parent`` 派生改写，保证父子一致。
* 所有断言失败均以非零退出码结束，便于 CI / 流水线闸门使用。

版本：1.0.0
"""

import argparse
import gzip
import json
import os
import re
import sys

__version__ = "1.0.0"

GZIP_MAGIC = b"\x1f\x8b"

# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------

RE_CHROM_STD = re.compile(r"^[1-7][A-Z]$")          # 1M / 7C / 2U / 3N ...
RE_CHR_PREFIX = re.compile(r"^Chr")                  # 已是 Chr*（大小写敏感，平台要求 Chr 大写）
RE_CHR_ANY_CASE = re.compile(r"^chr(.+)$", re.I)     # chr1A -> Chr1A
RE_MRNA_DASH = re.compile(r"-mRNA-(\d+)$")           # xxx-mRNA-2 -> xxx.2
RE_P_SUFFIX = re.compile(r"\.p(\d+)$")               # xxx.p10 -> xxx.10
RE_DIGIT_END = re.compile(r"\.\d+$")                 # 平台要求：以 .数字 结尾
RE_ID_ATTR = re.compile(r"(?:^|;)ID=([^;]+)")

DEFAULT_PREFIX_FAMILY = r"^(?:gene|model)\.model\.STRG\."


def log(msg):
    sys.stderr.write(msg + "\n")


def die(msg, code=1):
    log("[ERROR] " + msg)
    sys.exit(code)


def fmt_int(n):
    return "{:,}".format(n)


def open_text(path):
    """按后缀或 gzip magic 打开文本文件读（支持 .gz）。"""
    if path == "-":
        return sys.stdin
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    with open(path, "rb") as fh:
        magic = fh.read(2)
    if magic == GZIP_MAGIC:
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def open_out(path):
    """按后缀打开文本文件写（.gz 结尾自动 gzip 压缩）。"""
    if path.endswith(".gz"):
        return gzip.open(path, "wt", encoding="utf-8", compresslevel=6)
    return open(path, "w", encoding="utf-8")


def ensure_parent_dir(path):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)


# ---------------------------------------------------------------------------
# assembly_report 解析
# ---------------------------------------------------------------------------

class AssemblyReport(object):
    """NCBI ``*_assembly_report.txt`` 解析结果。

    数据行为制表符分隔 10 列（见文件内 ``# Sequence-Name ...`` 表头）：

    ====  ============================  =========================================
    列    含义                          用途
    ====  ============================  =========================================
    0     Sequence-Name                 作者 seqid（如 1M / Super-Scaffold_...）
    1     Sequence-Role                 assembled-molecule -> Chr；其它 -> ChrUn_
    4     GenBank-Accn                  NCBI FASTA 头的登录号（如 CM127985.1）
    6     RefSeq-Accn                   备用登录号（可能为 na）
    8     Sequence-Length               长度校验 / 坐标校验
    ====  ============================  =========================================

    映射规则：
    * ``assembled-molecule`` -> ``<chrom_prefix>`` + Sequence-Name（如 ``1M`` -> ``Chr1M``）
    * 其它 role（unplaced/unlocalized-scaffold 等）-> ``<unplaced_prefix>`` + Sequence-Name
      （如 ``Super-Scaffold_100133_4M`` -> ``ChrUn_Super-Scaffold_100133_4M``）
    """

    def __init__(self, path, chrom_prefix="Chr", unplaced_prefix="ChrUn_"):
        self.path = path
        self.chrom_prefix = chrom_prefix
        self.unplaced_prefix = unplaced_prefix
        self.rows = []
        self.by_name = {}
        self.by_accn = {}
        self.warnings = []
        self._parse()

    def _parse(self):
        header_seen = False
        for lineno, line in enumerate(open_text(self.path), 1):
            line = line.rstrip("\n").rstrip("\r")
            if not line:
                continue
            if not header_seen:
                if "Sequence-Name" in line and "Sequence-Role" in line:
                    header_seen = True
                continue
            if line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 10:
                # 容错：极少数报告用空格对齐，但 NCBI 官方文件是制表符
                parts = re.split(r"\s{2,}", line)
                if len(parts) < 10:
                    self.warnings.append(
                        "第 %d 行无法解析（列数 %d），已跳过: %r" % (lineno, len(parts), line[:80]))
                    continue
            row = {
                "seq_name": parts[0].strip(),
                "role": parts[1].strip(),
                "assigned": parts[2].strip(),
                "location_type": parts[3].strip(),
                "genbank": parts[4].strip(),
                "refseq": parts[6].strip() if len(parts) > 6 else "na",
                "length": None,
                "unit": parts[7].strip() if len(parts) > 7 else "",
            }
            try:
                row["length"] = int(parts[8])
            except (ValueError, IndexError):
                row["length"] = None
            self.rows.append(row)
            self.by_name[row["seq_name"]] = row
            if row["genbank"] and row["genbank"] != "na":
                self.by_accn[row["genbank"]] = row
            if row["refseq"] and row["refseq"] != "na":
                self.by_accn[row["refseq"]] = row
        if not self.rows:
            die("assembly_report 解析失败（未找到 'Sequence-Name/Sequence-Role' 表头或数据行）: %s"
                % self.path)

    # -- 映射 ---------------------------------------------------------------
    def chrom_name(self, row):
        """按报告行计算规范化 seqid。"""
        name = row["seq_name"]
        if row["role"] == "assembled-molecule":
            if name.startswith(self.chrom_prefix):
                return name
            return self.chrom_prefix + name
        if name.startswith(self.unplaced_prefix):
            return name
        return self.unplaced_prefix + name

    def expected_names(self):
        """报告全部序列的规范化名字 -> row 的字典（保持报告顺序）。"""
        out = {}
        for row in self.rows:
            out[self.chrom_name(row)] = row
        return out

    def map_gff_seqid(self, seqid):
        """GFF3 seqid -> 规范化 seqid。

        规则顺序：
        1. 已以 ``Chr`` 开头 -> 原样保留；
        2. ``^[1-7][A-Z]$`` -> ``Chr`` + 原名；
        3. assembly_report 的 Sequence-Name（assembled-molecule）-> ``Chr`` + 名；
        4. assembly_report 的 GenBank/RefSeq 登录号 -> 对应行规则；
        5. 其它（scaffold / contig / 报告内未定位序列）-> ``ChrUn_`` + 原名；
        6. 报告里完全没有的 seqid -> 当未知处理（调用方决定是否报错）。
        """
        if seqid.startswith(self.chrom_prefix):
            return seqid
        m = RE_CHR_ANY_CASE.match(seqid)
        if m:
            return self.chrom_prefix + m.group(1)
        row = self.by_name.get(seqid)
        if row is not None:
            return self.chrom_name(row)
        row = self.by_accn.get(seqid)
        if row is not None:
            return self.chrom_name(row)
        if RE_CHROM_STD.match(seqid):
            return self.chrom_prefix + seqid
        return self.unplaced_prefix + seqid

    def is_known(self, seqid):
        """seqid 是否能在 report 中确定性定位（含已是 Chr* 与标准染色体名）。"""
        if seqid.startswith(self.chrom_prefix) or RE_CHR_ANY_CASE.match(seqid):
            return True
        if seqid in self.by_name or seqid in self.by_accn:
            return True
        return bool(RE_CHROM_STD.match(seqid))

    def role_of(self, seqid):
        row = self.by_name.get(seqid) or self.by_accn.get(seqid)
        return row["role"] if row else "not-in-report"

    def length_map(self):
        """规范化 seqid -> 长度（bp）。"""
        out = {}
        for row in self.rows:
            if row["length"] is not None:
                out[self.chrom_name(row)] = row["length"]
        return out

    def stats(self):
        roles = {}
        total = 0
        for row in self.rows:
            roles[row["role"]] = roles.get(row["role"], 0) + 1
            if row["length"] is not None:
                total += row["length"]
        return {
            "report": self.path,
            "rows": len(self.rows),
            "assembled_molecule": roles.get("assembled-molecule", 0),
            "roles": roles,
            "total_length": total,
        }


# ---------------------------------------------------------------------------
# GFF3 / FASTA 行级工具
# ---------------------------------------------------------------------------

def parse_gff_attrs(attr):
    """'a=1;b=2' -> [('a','1'), ('b','2')]；无 '=' 的项 value 为 None（如 '###' 后的空）。"""
    items = []
    for chunk in attr.split(";"):
        if chunk == "":
            continue
        if "=" in chunk:
            key, value = chunk.split("=", 1)
            items.append((key, value))
        else:
            items.append((chunk, None))
    return items


def format_gff_attrs(items):
    out = []
    for key, value in items:
        out.append(key if value is None else key + "=" + value)
    return ";".join(out)


def split_header(header_line):
    """'>ID description...' -> ('ID', ' description...')；保留原描述文本。"""
    text = header_line.rstrip("\n").rstrip("\r")
    m = re.match(r"^>\s*(\S+)(.*)$", text)
    if not m:
        return None, ""
    return m.group(1), m.group(2)


# ---------------------------------------------------------------------------
# ID 规范化
# ---------------------------------------------------------------------------

class IdNormalizer(object):
    """gene / mRNA ID 规范化（gff3 与 pep 子命令共用同一套规则）。

    规则（按顺序）：
    1. ``-mRNA-N`` -> ``.N``；
    2. ``.pN`` -> ``.N``（TAMA/STRG 家族，51,666 条）；
    3. 跨物种重名家族加 ``--id-prefix`` 前缀（默认只加 ``STRG`` 家族，
       ``--prefix-all-ids`` 可改为所有 gene/mRNA ID）；
    4. mRNA ID 仍不以 ``.数字`` 结尾时追加 ``.1``。
    """

    def __init__(self, args):
        self.prefix = args.id_prefix or ""
        self.prefix_all = bool(getattr(args, "prefix_all_ids", False))
        self.family = re.compile(args.prefix_family_regex or DEFAULT_PREFIX_FAMILY)
        self.n_prefixed = 0
        self.n_dash_fixed = 0
        self.n_p_fixed = 0
        self.n_appended = 0

    def _wants_prefix(self, old_id):
        if not self.prefix:
            return False
        if self.prefix_all:
            return True
        return bool(self.family.match(old_id))

    @staticmethod
    def is_mrna_like(feature_type):
        return feature_type in ("mRNA", "transcript")

    @staticmethod
    def is_gene_like(feature_type):
        return feature_type == "gene"

    def normalize(self, old_id, feature_type):
        """返回规范化后的 ID；统计计数在实例上累计。"""
        new_id = old_id
        m = RE_MRNA_DASH.search(new_id)
        if m:
            new_id = RE_MRNA_DASH.sub(r".\1", new_id)
            self.n_dash_fixed += 1
        if RE_P_SUFFIX.search(new_id):
            new_id = RE_P_SUFFIX.sub(r".\1", new_id)
            self.n_p_fixed += 1
        if self._wants_prefix(old_id):
            new_id = self.prefix + new_id
            self.n_prefixed += 1
        # 平台规则：mRNA ID 必须以 .数字 结尾
        if self.is_mrna_like(feature_type) and not RE_DIGIT_END.search(new_id):
            new_id = new_id + ".1"
            self.n_appended += 1
        return new_id


def resolve_dup(new_id, used, feature_type):
    """极小概率的 ID 撞名兜底：追加数字直到唯一（并保持以 .数字 结尾）。"""
    candidate = new_id
    while candidate in used:
        candidate = candidate + "1"
    return candidate


# ---------------------------------------------------------------------------
# fasta 子命令
# ---------------------------------------------------------------------------

def cmd_fasta(args):
    report = AssemblyReport(args.assembly_report, args.prefix, args.unplaced_prefix)
    st = report.stats()
    for w in report.warnings:
        log("[WARN] " + w)
    log("[assembly_report] %s: rows=%d assembled-molecule=%d total_length=%s"
        % (os.path.basename(report.path), st["rows"], st["assembled_molecule"],
           fmt_int(st["total_length"])))
    log("[assembly_report] roles: " + ", ".join(
        "%s=%d" % (k, v) for k, v in sorted(st["roles"].items())))

    # 额外 seqid 映射（如 TE GFF 的特殊 token），格式：旧名<TAB>新名
    extra = {}
    if args.seqid_map:
        for line in open_text(args.seqid_map):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t") if "\t" in line else line.split()
            if len(parts) >= 2:
                extra[parts[0]] = parts[1]
        log("[seqid-map] 额外映射 %d 条: %s" % (len(extra), args.seqid_map))

    expected = report.expected_names()
    report_rows = list(report.rows)

    # --dry-run：只解析报告并输出映射表
    if args.dry_run:
        mapping_path = args.mapping or (args.out + ".mapping.tsv" if args.out else None)
        if mapping_path:
            _write_fasta_mapping(mapping_path, report, observed=None, extra=extra)
        print(json.dumps({
            "mode": "dry-run",
            "assembly_report": report.path,
            "report_rows": st["rows"],
            "assembled_molecule": st["assembled_molecule"],
            "unplaced_or_other": st["rows"] - st["assembled_molecule"],
            "roles": st["roles"],
            "total_length": st["total_length"],
            "mapping_rows": st["rows"],
            "mapping_tsv": mapping_path,
        }, ensure_ascii=False, indent=2))
        return 0

    if not args.fasta:
        die("fasta 子命令需要 --fasta（或加 --dry-run 只做映射预检）")
    if not args.out:
        die("fasta 子命令需要 --out")

    mapped_names = set(expected.keys())
    accn_map = report.by_accn
    name_map = report.by_name

    n_in = 0
    n_out_headers = 0
    total_len_in = 0
    total_len_out = 0
    mapped = 0
    already = 0
    unmapped = []
    seen_out = set()
    dup_out = []
    seen_in = set()

    ensure_parent_dir(args.out)
    fin = open_text(args.fasta)
    fout = open_out(args.out)
    try:
        seq_len = 0
        header_buf = None
        for line in fin:
            if line.startswith(">"):
                if header_buf is not None:
                    total_len_in += seq_len
                    total_len_out += seq_len
                name, rest = split_header(line)
                n_in += 1
                n_out_headers += 1
                seen_in.add(name)
                new_name = None
                src = None
                if name in accn_map:
                    new_name = report.chrom_name(accn_map[name])
                    src = "genbank-accn"
                elif name in name_map:
                    new_name = report.chrom_name(name_map[name])
                    src = "sequence-name"
                elif name in extra:
                    new_name = extra[name]
                    src = "seqid-map"
                elif name.startswith(report.chrom_prefix):
                    new_name = name
                    src = "already-chr"
                if new_name is None:
                    unmapped.append(name)
                    if name in seen_out:
                        dup_out.append(name)
                    seen_out.add(name)
                    # 保留原头，避免静默丢序列；最终断言会失败
                    fout.write(">" + name + rest + "\n")
                else:
                    mapped += 1
                    if src == "already-chr":
                        already += 1
                    if new_name in seen_out:
                        dup_out.append(new_name)
                    seen_out.add(new_name)
                    fout.write(">" + new_name + rest + "\n")
                header_buf = new_name
                seq_len = 0
                continue
            if header_buf is None:
                continue
            seq_len += len(line.strip())
            fout.write(line if line.endswith("\n") else line + "\n")
        if header_buf is not None:
            total_len_in += seq_len
            total_len_out += seq_len
    finally:
        if fin is not sys.stdin:
            fin.close()
        fout.close()

    mapping_path = args.mapping or (args.out + ".mapping.tsv")
    _write_fasta_mapping(mapping_path, report, seen_in, extra)

    # -- 断言 ---------------------------------------------------------------
    errors = []
    expected_count = len(report_rows)
    report_total = st["total_length"]
    mapping_rate = (float(mapped) / n_in) if n_in else 0.0

    if unmapped:
        msg = "%d 条 FASTA 头无法映射到 assembly_report（替换率 %.2f%%）: %s" % (
            len(unmapped), mapping_rate * 100.0, ", ".join(unmapped[:10]))
        if args.allow_unmapped:
            log("[WARN] " + msg)
        else:
            errors.append(msg)
    if dup_out:
        errors.append("改名后出现重复序列名 %d 个: %s" % (len(dup_out), ", ".join(dup_out[:10])))
    if not args.partial:
        if n_in != expected_count:
            errors.append("FASTA 序列数 %d != assembly_report 行数 %d" % (n_in, expected_count))
        if report_total and total_len_in != report_total:
            errors.append("FASTA 总长 %d != assembly_report 总长 %d"
                          % (total_len_in, report_total))
        missing = mapped_names - seen_out
        if missing:
            errors.append("assembly_report 中 %d 条序列在 FASTA 缺失（示例: %s）"
                          % (len(missing), ", ".join(sorted(missing)[:10])))
        unexpected = seen_out - mapped_names - set(extra.values())
        if unexpected:
            errors.append("FASTA 中出现 assembly_report 未列出的新名 %d 个: %s"
                          % (len(unexpected), ", ".join(sorted(unexpected)[:10])))
        if total_len_out != total_len_in:
            errors.append("输出总长 %d != 输入总长 %d" % (total_len_out, total_len_in))
        if mapping_rate < 1.0:
            errors.append("替换率 %.2f%% != 100%%" % (mapping_rate * 100.0))
    else:
        log("[WARN] --partial：跳过序列数/总长/覆盖率全量断言（片段冒烟测试模式）")

    log("[fasta] 序列数: 输入 %d -> 输出 %d；总长: %d -> %d；映射 %d (%.2f%%)，"
        "原已是 Chr 头 %d" % (n_in, n_out_headers, total_len_in, total_len_out, mapped,
                              mapping_rate * 100.0, already))
    log("[mapping] %s" % mapping_path)

    if errors:
        for e in errors:
            log("[FAIL] " + e)
        return 1
    log("[PASS] fasta 归一化完成：%d 条序列，映射率 100%%，总长 %s"
        % (n_in, fmt_int(total_len_out)))
    return 0


def _write_fasta_mapping(path, report, observed, extra):
    """写出 FASTA 映射表：新名 <-> 原 FASTA 头第一个 token。"""
    ensure_parent_dir(path)
    with open_out(path) as fh:
        fh.write("#new_name\told_name\tsequence_role\tsequence_name\tlength\tin_fasta\n")
        used_old = set()
        for row in report.rows:
            new_name = report.chrom_name(row)
            old_name = row["genbank"]
            if not old_name or old_name == "na":
                old_name = row["refseq"] if row["refseq"] and row["refseq"] != "na" \
                    else row["seq_name"]
            if observed is None:
                in_fasta = "NA"
            elif old_name in observed or row["seq_name"] in observed or new_name in observed:
                in_fasta = "yes"
            else:
                in_fasta = "no"
            used_old.add(old_name)
            fh.write("%s\t%s\t%s\t%s\t%d\t%s\n" % (
                new_name, old_name, row["role"], row["seq_name"],
                row["length"] if row["length"] is not None else -1, in_fasta))
        for old, new in extra.items():
            if old in used_old:
                continue
            if observed is None:
                in_fasta = "NA"
            else:
                in_fasta = "yes" if old in observed else "no"
            fh.write("%s\t%s\textra-seqid-map\t-\t-1\t%s\n" % (new, old, in_fasta))


# ---------------------------------------------------------------------------
# gff3 子命令
# ---------------------------------------------------------------------------

def _load_prior_idmaps(paths):
    """加载 --also-ids 历史 ID 映射（.json 或 .tsv），返回 (id_set, n_map, files)。"""
    ids = set()
    loaded = []
    for path in paths:
        n = 0
        if path.endswith(".json"):
            with open(path, "r", encoding="utf-8") as fh:
                obj = json.load(fh)
            if not isinstance(obj, dict):
                die("--also-ids 的 JSON 必须是 {old_id: new_id} 对象: %s" % path)
            for value in obj.values():
                if isinstance(value, str):
                    ids.add(value)
                    n += 1
        else:
            for lineno, line in enumerate(open_text(path)):
                line = line.rstrip("\n")
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                ids.add(parts[1])
                n += 1
        loaded.append((path, n))
        log("[also-ids] 载入 %s：%d 条新 ID" % (path, n))
    return ids, loaded


def cmd_gff3(args):
    report = AssemblyReport(args.assembly_report, args.prefix, args.unplaced_prefix)
    for w in report.warnings:
        log("[WARN] " + w)
    st = report.stats()
    log("[assembly_report] rows=%d assembled-molecule=%d total_length=%s"
        % (st["rows"], st["assembled_molecule"], fmt_int(st["total_length"])))

    normalizer = IdNormalizer(args)
    keep_author_ids = bool(getattr(args, "keep_author_ids", False))
    if keep_author_ids:
        log("[keep-author-ids] 保留作者 gene/mRNA ID（只改 seqid）；"
            "最终 ID 由 renumber_gff_ids.py 按平台规则重编号")
    if args.id_prefix and not keep_author_ids:
        scope = "全部 gene/mRNA" if normalizer.prefix_all else \
            "家族 %s" % (args.prefix_family_regex or DEFAULT_PREFIX_FAMILY)
        log("[id-prefix] '%s' 将加到 %s 的 ID 前" % (args.id_prefix, scope))
    else:
        log("[id-prefix] 未指定：不改前缀（跨物种重名风险由 --also-ids/check 兜底）")

    prior_ids, _ = _load_prior_idmaps(args.also_ids or [])

    # ---- 第一遍：收集 gff seqid、feature 计数、gene/mRNA ID 映射 ----
    id_map = {}
    used_ids = set()
    id_map_feature = {}
    seqid_counter = {}
    seqid_genes = {}
    missing_id = 0
    n_features_in = {}
    in_fasta_section = False
    n_lines = 0

    for line in open_text(args.gff3):
        n_lines += 1
        if in_fasta_section:
            continue
        if line.startswith("##FASTA"):
            in_fasta_section = True
            continue
        if line.startswith("#") or not line.strip():
            continue
        parts = line.rstrip("\n").rstrip("\r").split("\t")
        if len(parts) < 9:
            continue
        seqid = parts[0]
        ftype = parts[2]
        n_features_in[ftype] = n_features_in.get(ftype, 0) + 1
        seqid_counter[seqid] = seqid_counter.get(seqid, 0) + 1
        if normalizer.is_gene_like(ftype):
            seqid_genes[seqid] = seqid_genes.get(seqid, 0) + 1
        if not (normalizer.is_gene_like(ftype) or normalizer.is_mrna_like(ftype)):
            continue
        m = RE_ID_ATTR.search(parts[8])
        if not m:
            missing_id += 1
            continue
        old_id = m.group(1)
        new_id = old_id if keep_author_ids else normalizer.normalize(old_id, ftype)
        if new_id in used_ids:
            fixed = resolve_dup(new_id, used_ids, ftype)
            log("[WARN] ID 撞名: %r -> %r（已改为 %r）" % (old_id, new_id, fixed))
            new_id = fixed
        used_ids.add(new_id)
        id_map[old_id] = new_id
        id_map_feature[old_id] = ftype

    # 未知 seqid 检查（必须在写输出前）
    unknown_seqids = [s for s in seqid_counter if not report.is_known(s)]
    if unknown_seqids:
        msg = "%d 个 GFF seqid 不在 assembly_report 中（示例: %s）" % (
            len(unknown_seqids), ", ".join(sorted(unknown_seqids)[:10]))
        if args.allow_unknown_seqids:
            log("[WARN] " + msg + "；--allow-unknown-seqids 已放行，按 ChrUn_ 规则处理")
        else:
            die(msg + "\n  若确认可接受，请加 --allow-unknown-seqids；"
                      "也可检查 --assembly-report 是否与注释版本匹配")

    # 跨物种/跨文件唯一性断言（gene + mRNA）
    if prior_ids:
        conflicts = sorted(set(id_map.values()) & prior_ids)
        if conflicts:
            die("与 --also-ids 历史映射存在 %d 个重复 ID（跨物种冲突），示例: %s"
                % (len(conflicts), ", ".join(conflicts[:10])))
        log("[also-ids] 跨文件重复 ID = 0（%d 条新 ID 与 %d 条历史 ID 无交集）"
            % (len(id_map), len(prior_ids)))

    log("[gff3] 输入: %d 行, %d 个 seqid, gene/mRNA ID 映射 %d 条"
        % (n_lines, len(seqid_counter), len(id_map)))
    log("[gff3] ID 统计: 加前缀 %d, .pN->.N %d, -mRNA-N->.N %d, 追加 .1 %d"
        % (normalizer.n_prefixed, normalizer.n_p_fixed, normalizer.n_dash_fixed,
           normalizer.n_appended))

    # ---- dry-run：只输出映射与统计 ----
    if args.dry_run:
        mapping_path = args.mapping or (args.out + ".mapping.tsv" if args.out else None)
        if mapping_path:
            _write_gff_mapping(mapping_path, report, seqid_counter, seqid_genes,
                               set(seqid_counter))
        print(json.dumps({
            "mode": "dry-run",
            "gff3": args.gff3,
            "lines": n_lines,
            "seqids": len(seqid_counter),
            "features": n_features_in,
            "feature_total": sum(n_features_in.values()),
            "gene": n_features_in.get("gene", 0),
            "mRNA": n_features_in.get("mRNA", 0),
            "id_map_size": len(id_map),
            "id_stats": {"prefixed": normalizer.n_prefixed,
                         "p_to_digit": normalizer.n_p_fixed,
                         "mrna_dash": normalizer.n_dash_fixed,
                         "appended_dot1": normalizer.n_appended},
            "mapping_tsv": mapping_path,
        }, ensure_ascii=False, indent=2))
        return 0

    if not args.out:
        die("gff3 子命令需要 --out（或加 --dry-run 只做映射预检）")

    # ---- 第二遍：流式重写 ----
    ensure_parent_dir(args.out)
    seqid_cache = {}
    new_gene_mrna_ids = set(id_map.values())
    written_gene_mrna = set()
    derived_ids = set()
    derived_dup_out = 0
    dup_written = []
    unresolved_parents = []
    coords_bad = 0
    coords_over = 0
    coords_example = []
    count_out = {}
    n_out = 0
    lengths = report.length_map()

    def map_seqid_cached(seqid):
        new = seqid_cache.get(seqid)
        if new is None:
            new = report.map_gff_seqid(seqid)
            seqid_cache[seqid] = new
        return new

    def rewrite_attrs(attr):
        items = parse_gff_attrs(attr)
        values = {}
        for key, value in items:
            if value is not None:
                values[key] = value
        old_parents = [x for x in values.get("Parent", "").split(",") if x]
        new_out = []
        for key, value in items:
            if value is None:
                new_out.append((key, None))
                continue
            if key == "ID":
                new_value = id_map.get(value)
                if new_value is None and old_parents:
                    # 子特征（exon/CDS/UTR…）ID 由父 ID 派生：替换父 ID 子串
                    new_value = value
                    for old_parent in sorted(old_parents, key=len, reverse=True):
                        mapped_parent = id_map.get(old_parent)
                        if mapped_parent and old_parent in new_value:
                            new_value = new_value.replace(old_parent, mapped_parent, 1)
                            break
                if new_value is None:
                    new_value = value
                new_out.append((key, new_value))
            elif key in ("Parent", "Derives_from"):
                tokens = value.split(",")
                mapped = []
                for token in tokens:
                    mt = id_map.get(token)
                    if mt is None:
                        if token:
                            unresolved_parents.append(token)
                        mapped.append(token)
                    else:
                        mapped.append(mt)
                new_out.append((key, ",".join(mapped)))
            elif key == "Name":
                new_out.append((key, id_map.get(value, value)))
            else:
                new_out.append((key, value))
        return format_gff_attrs(new_out)

    fin = open_text(args.gff3)
    fout = open_out(args.out)
    in_fasta_section = False
    try:
        for line in fin:
            if in_fasta_section:
                fout.write(line)
                continue
            if line.startswith("##FASTA"):
                in_fasta_section = True
                fout.write(line if line.endswith("\n") else line + "\n")
                continue
            if line.startswith("#") or not line.strip():
                fout.write(line if line.endswith("\n") else line + "\n")
                continue
            parts = line.rstrip("\n").rstrip("\r").split("\t")
            if len(parts) < 9:
                # 非标准行原样保留
                fout.write(line if line.endswith("\n") else line + "\n")
                continue
            ftype = parts[2]
            parts[0] = map_seqid_cached(parts[0])
            parts[8] = rewrite_attrs(parts[8])

            # 坐标合法性 / 越界检查
            try:
                start = int(parts[3])
                end = int(parts[4])
                if start < 1 or end < start:
                    coords_bad += 1
                    if len(coords_example) < 5:
                        coords_example.append("%s:%s-%s(%s)" % (parts[0], parts[3],
                                                                parts[4], ftype))
                seq_len = lengths.get(parts[0])
                if seq_len is not None and end > seq_len:
                    coords_over += 1
                    if len(coords_example) < 5:
                        coords_example.append("%s:%s-%s>len%d(%s)" % (
                            parts[0], parts[3], parts[4], seq_len, ftype))
            except ValueError:
                coords_bad += 1

            # ID 唯一性：
            # - gene / mRNA ID 必须全局唯一（平台聚合库的主键语义）；
            # - exon/CDS 等派生 ID 允许作者原生重复（本批 CDS ID 每个转录本
            #   共用同一个 "cds.<mRNA>"，属作者输出瑕疵，不影响 gffread/Parent 解析），
            #   只统计并在日志中提示。
            m = RE_ID_ATTR.search(parts[8])
            if m:
                rid = m.group(1)
                if rid in new_gene_mrna_ids:
                    if rid in written_gene_mrna:
                        dup_written.append(rid)
                    written_gene_mrna.add(rid)
                else:
                    if rid in derived_ids:
                        derived_dup_out += 1
                    derived_ids.add(rid)

            count_out[ftype] = count_out.get(ftype, 0) + 1
            fout.write("\t".join(parts) + "\n")
            n_out += 1
    finally:
        if fin is not sys.stdin:
            fin.close()
        fout.close()

    mapping_path = args.mapping or (args.out + ".mapping.tsv")
    _write_gff_mapping(mapping_path, report, seqid_counter, seqid_genes, set(seqid_counter))
    idmap_path = None
    if args.id_map:
        _write_id_map(args.id_map, id_map, id_map_feature)
        idmap_path = args.id_map

    # ---- 断言 -------------------------------------------------------------
    errors = []
    if missing_id:
        errors.append("%d 条 gene/mRNA 记录缺 ID 属性" % missing_id)
    if dup_written:
        errors.append("gene/mRNA ID 不唯一 %d 个（示例: %s）"
                      % (len(dup_written), ", ".join(dup_written[:10])))
    else:
        log("[gff3] gene/mRNA ID 唯一: %d 个（%s gene + %s mRNA）"
            % (len(written_gene_mrna), fmt_int(n_features_in.get("gene", 0)),
               fmt_int(n_features_in.get("mRNA", 0))))
    if derived_dup_out:
        log("[gff3] [INFO] exon/CDS 派生 ID 有 %d 个重复（作者注释原生特征，"
            "非归一化引入；平台 check 只校验 mRNA ID，gffread 用 Parent 解析不受影响）"
            % derived_dup_out)
    if unresolved_parents:
        errors.append("有 %d 个 Parent/Derives_from 引用无法解析（示例: %s）"
                      % (len(unresolved_parents), ", ".join(unresolved_parents[:10])))
    if n_features_in != count_out:
        diff = {k: (n_features_in.get(k, 0), count_out.get(k, 0))
                for k in set(n_features_in) | set(count_out)
                if n_features_in.get(k, 0) != count_out.get(k, 0)}
        errors.append("feature 计数不一致: %r" % (diff,))
    # mRNA ID 规则（重写后）
    bad_mrna = []
    for old, new in id_map.items():
        if normalizer.is_mrna_like(id_map_feature.get(old, "")):
            if not RE_DIGIT_END.search(new):
                bad_mrna.append(new)
    if bad_mrna and not keep_author_ids:
        errors.append("%d 个 mRNA ID 不以 .数字 结尾（示例: %s）"
                      % (len(bad_mrna), ", ".join(sorted(bad_mrna)[:10])))
    elif bad_mrna and keep_author_ids:
        log("[keep-author-ids] 跳过 mRNA ID 后缀断言（%d 条，交给 renumber_gff_ids.py）"
            % len(bad_mrna))
    if not args.no_coord_check:
        if coords_bad:
            errors.append("%d 条记录坐标非法（start<1 或 end<start，示例: %s）"
                          % (coords_bad, ", ".join(coords_example[:5])))
        if coords_over:
            errors.append("%d 条记录 end 超出 assembly_report 序列长度（示例: %s）"
                          % (coords_over, ", ".join(coords_example[:5])))

    gene_in = n_features_in.get("gene", 0)
    mrna_in = n_features_in.get("mRNA", 0)
    seqids_out = set(seqid_cache.values())
    non_chr = [s for s in seqids_out if not s.startswith(report.chrom_prefix)]
    if non_chr:
        errors.append("%d 个输出 seqid 不以 %s 开头: %s"
                      % (len(non_chr), report.chrom_prefix, ", ".join(sorted(non_chr)[:10])))

    log("[gff3] 输出: %d 行 -> %s（%.1f MB）"
        % (n_out, args.out, os.path.getsize(args.out) / 1024.0 / 1024.0))
    log("[gff3] seqid: %d 个 -> chr数 %d / ChrUn_数 %d"
        % (len(seqids_out),
           sum(1 for s in seqids_out if not s.startswith(report.unplaced_prefix)),
           sum(1 for s in seqids_out if s.startswith(report.unplaced_prefix))))
    log("[gff3] feature: " + ", ".join("%s=%d" % (k, v) for k, v in sorted(count_out.items())))
    if gene_in != mrna_in:
        log("[WARN] 输入 gene=%d != mRNA=%d（非 1:1 注释，请人工确认）" % (gene_in, mrna_in))
    log("[mapping] seqid 映射表: %s" % mapping_path)
    if idmap_path:
        log("[id-map] gene/mRNA ID 映射表: %s" % idmap_path)

    if errors:
        for e in errors:
            log("[FAIL] " + e)
        return 1
    if keep_author_ids:
        log("[PASS] gff3 seqid 归一化完成（保留作者 ID，待 renumber）："
            "gene=%d / mRNA=%d" % (gene_in, mrna_in))
    else:
        log("[PASS] gff3 归一化完成：seqid 全 Chr*，mRNA ID 全 .数字 结尾，"
            "gene/mRNA ID 唯一，计数 preserved (gene=%d / mRNA=%d)" % (gene_in, mrna_in))
    return 0


def _write_gff_mapping(path, report, seqid_counter, seqid_genes, present):
    """写出 GFF seqid 映射表（按 assembly_report 顺序，再补报告外 seqid）。"""
    ensure_parent_dir(path)
    with open_out(path) as fh:
        fh.write("#old_seqid\tnew_seqid\tsequence_role\tn_features\tn_genes\n")
        written = set()
        for row in report.rows:
            old = row["seq_name"]
            if old not in present:
                continue
            new = report.chrom_name(row)
            fh.write("%s\t%s\t%s\t%d\t%d\n" % (
                old, new, row["role"], seqid_counter.get(old, 0), seqid_genes.get(old, 0)))
            written.add(old)
        for old in sorted(present - written):
            new = report.map_gff_seqid(old)
            fh.write("%s\t%s\t%s\t%d\t%d\n" % (
                old, new, "not-in-report" if not report.is_known(old) else "chr-name",
                seqid_counter.get(old, 0), seqid_genes.get(old, 0)))


def _write_id_map(path, id_map, id_map_feature):
    """写出 gene/mRNA 改名映射；.json 后缀输出 JSON，其它输出 TSV。"""
    ensure_parent_dir(path)
    if path.endswith(".json"):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(id_map, fh, ensure_ascii=False, sort_keys=True, indent=0)
        return
    with open_out(path) as fh:
        fh.write("#old_id\tnew_id\tfeature_type\n")
        for old in id_map:
            fh.write("%s\t%s\t%s\n" % (old, id_map[old], id_map_feature.get(old, "")))


# ---------------------------------------------------------------------------
# pep 子命令
# ---------------------------------------------------------------------------

def cmd_pep(args):
    normalizer = IdNormalizer(args)
    exact = {}
    if args.id_map:
        if args.id_map.endswith(".json"):
            with open(args.id_map, "r", encoding="utf-8") as fh:
                exact = json.load(fh)
        else:
            for line in open_text(args.id_map):
                line = line.rstrip("\n")
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    exact[parts[0]] = parts[1]
        if not isinstance(exact, dict):
            die("--id-map 必须是 TSV（old_id<TAB>new_id）或 JSON 对象")
        log("[id-map] 载入 %d 条精确 ID 映射: %s" % (len(exact), args.id_map))
    else:
        log("[id-map] 未指定：按 gff3 同套规则推导 ID")

    ensure_parent_dir(args.out)
    n_in = 0
    n_out = 0
    residues_in = 0
    residues_out = 0
    stop_chars = 0
    stop_seqs = 0
    bad_ids = []
    seen_ids = set()
    dup_ids = []
    mapped_exact = 0

    fin = open_text(args.pep)
    fout = open_out(args.out)
    try:
        cur_id = None
        cur_changed = False
        for line in fin:
            if line.startswith(">"):
                if cur_id is not None:
                    n_out += 1
                    if cur_changed:
                        stop_seqs += 1
                name, rest = split_header(line)
                n_in += 1
                if name in exact:
                    new_id = exact[name]
                    mapped_exact += 1
                else:
                    new_id = normalizer.normalize(name, "mRNA")
                if new_id in seen_ids:
                    dup_ids.append(new_id)
                seen_ids.add(new_id)
                if not RE_DIGIT_END.search(new_id):
                    bad_ids.append(new_id)
                cur_id = new_id
                cur_changed = False
                fout.write(">" + new_id + rest + "\n")
                continue
            if cur_id is None:
                continue
            residues_in += len(line.strip())
            cleaned = line
            if args.stop_mode != "keep":
                n_stop = len(re.findall(r"[.*]", line))
                if n_stop:
                    stop_chars += n_stop
                    cur_changed = True
                if args.stop_mode == "x":
                    cleaned = re.sub(r"[.*]", "X", line)
                elif args.stop_mode == "trim":
                    body = line.rstrip("\n")
                    body = body.rstrip(".*")
                    body = re.sub(r"[.*]", "X", body)
                    cleaned = body + ("\n" if line.endswith("\n") else "")
                elif args.stop_mode == "drop":
                    cleaned = re.sub(r"[.*]", "", line)
            residues_out += len(cleaned.strip())
            fout.write(cleaned)
        if cur_id is not None:
            n_out += 1
    finally:
        if fin is not sys.stdin:
            fin.close()
        fout.close()

    errors = []
    if bad_ids:
        errors.append("%d 个蛋白 ID 不以 .数字 结尾（示例: %s）"
                      % (len(bad_ids), ", ".join(bad_ids[:10])))
    if dup_ids:
        errors.append("%d 个蛋白 ID 重复（示例: %s）" % (len(dup_ids), ", ".join(dup_ids[:10])))

    # 复核输出中是否仍含 . 或 *
    bad_seq_lines = 0
    with open_text(args.out) as fh:
        for line in fh:
            if line.startswith(">"):
                continue
            if "." in line or "*" in line:
                bad_seq_lines += 1
    if bad_seq_lines:
        msg = "%d 行蛋白序列仍含 '.' 或 '*'（--stop-mode %s）" % (bad_seq_lines, args.stop_mode)
        if args.stop_mode == "keep":
            log("[WARN] " + msg + "；--stop-mode keep 为调试模式，生产请用 x/trim/drop")
        else:
            errors.append(msg)

    log("[pep] 序列数: 输入 %d / 输出 %d；残基: %d -> %d；"
        "替换终止符 %d 个 / 涉及 %d 条序列"
        % (n_in, n_out, residues_in, residues_out, stop_chars, stop_seqs))
    if exact:
        log("[pep] 精确 ID 映射命中: %d/%d" % (mapped_exact, n_in))
        if mapped_exact != n_in:
            errors.append("有 %d 条蛋白头未在 --id-map 中找到（%d/%d 命中）"
                          % (n_in - mapped_exact, mapped_exact, n_in))
    log("[pep] --stop-mode=%s" % args.stop_mode)

    if errors:
        for e in errors:
            log("[FAIL] " + e)
        return 1
    log("[PASS] pep 归一化完成：ID 全 .数字 结尾、唯一，序列行无 '.'/'*'")
    return 0


# ---------------------------------------------------------------------------
# check 子命令
# ---------------------------------------------------------------------------

def _ints_arg(value):
    """'51203,47246' 或 '51203 47246' -> [51203, 47246]"""
    if value is None:
        return None
    return [int(x) for x in re.split(r"[,\s]+", value.strip()) if x]


class Checker(object):
    def __init__(self):
        self.errors = []
        self.warnings = []

    def err(self, msg):
        self.errors.append(msg)
        log("  [FAIL] " + msg)

    def warn(self, msg):
        self.warnings.append(msg)
        log("  [WARN] " + msg)

    def ok(self, msg):
        log("  [PASS] " + msg)


def _iter_data_lines(path):
    in_fasta = False
    for line in open_text(path):
        if in_fasta:
            continue
        if line.startswith("##FASTA"):
            in_fasta = True
            continue
        if line.startswith("#") or not line.strip():
            continue
        yield line.rstrip("\n").rstrip("\r").split("\t")


def check_gff(path, checker, expected_count=None, expected_unplaced=None,
              require_gene_eq_mrna=True):
    """单个 GFF3 的平台规则断言；返回统计 dict。"""
    log("[GFF3] %s" % path)
    n_features = 0
    feature_types = {}
    gene_ids = set()
    mrna_ids = set()
    mrna_id_list = []
    all_ids = set()
    dup_gene_mrna = []
    derived_dup = 0
    non_chr_seqids = set()
    seqid_counter = {}
    unplaced_genes = 0
    unplaced_mrna = 0
    bad_mrna = []
    leftover_p = 0
    coords_bad = 0
    n_gene = 0
    n_mrna = 0

    for parts in _iter_data_lines(path):
        if len(parts) < 9:
            continue
        n_features += 1
        seqid = parts[0]
        ftype = parts[2]
        feature_types[ftype] = feature_types.get(ftype, 0) + 1
        seqid_counter[seqid] = seqid_counter.get(seqid, 0) + 1
        if not seqid.startswith("Chr"):
            non_chr_seqids.add(seqid)
        try:
            start = int(parts[3])
            end = int(parts[4])
            if start < 1 or end < start:
                coords_bad += 1
        except ValueError:
            coords_bad += 1
        attrs = {}
        for item in parts[8].split(";"):
            if "=" in item:
                key, value = item.split("=", 1)
                attrs[key] = value
        rid = attrs.get("ID")
        if rid:
            if rid in all_ids:
                # gene/mRNA 重复 = 平台级问题；exon/CDS 重复 = 作者原生特征（只提示）
                if ftype in ("gene", "mRNA"):
                    dup_gene_mrna.append(rid)
                else:
                    derived_dup += 1
            all_ids.add(rid)
        if ftype == "gene":
            n_gene += 1
            if rid:
                gene_ids.add(rid)
            if seqid.startswith("ChrUn_"):
                unplaced_genes += 1
        elif ftype == "mRNA":
            n_mrna += 1
            if seqid.startswith("ChrUn_"):
                unplaced_mrna += 1
            if rid:
                mrna_ids.add(rid)
                mrna_id_list.append(rid)
                if not RE_DIGIT_END.search(rid):
                    bad_mrna.append(rid)
                if RE_P_SUFFIX.search(rid):
                    leftover_p += 1

    # -- 平台硬性规则 --
    if non_chr_seqids:
        checker.err("第 1 列有 %d 个 seqid 不以 'Chr' 开头: %s"
                    % (len(non_chr_seqids), ", ".join(sorted(non_chr_seqids)[:10])))
    else:
        checker.ok("第 1 列 seqid 全部以 'Chr' 开头（%d 个 seqid）" % len(seqid_counter))
    if bad_mrna:
        checker.err("%d 个 mRNA ID 不以 '.数字' 结尾（示例: %s）"
                    % (len(bad_mrna), ", ".join(bad_mrna[:10])))
    else:
        checker.ok("mRNA ID 全部以 '.数字' 结尾（%d 条）" % n_mrna)
    if leftover_p:
        checker.err("%d 个 mRNA ID 仍以 '.pN' 结尾（未归一化）" % leftover_p)
    if dup_gene_mrna:
        checker.err("gene/mRNA ID 不唯一 %d 个（示例: %s）"
                    % (len(dup_gene_mrna), ", ".join(dup_gene_mrna[:10])))
    else:
        checker.ok("gene/mRNA ID 唯一（共 %d 个 gene+mRNA ID）" % (n_gene + n_mrna))
    if derived_dup:
        checker.warn("exon/CDS 等派生 ID 作者原生重复 %d 个（非平台规则；"
                     "平台 check_genome_files 只校验 mRNA ID，gffread 用 Parent 解析）"
                     % derived_dup)
    if coords_bad:
        checker.err("%d 条记录坐标非法（start<1 或 end<start）" % coords_bad)
    if require_gene_eq_mrna:
        if n_gene == n_mrna:
            checker.ok("gene 数 = mRNA 数 = %d" % n_gene)
        else:
            checker.err("gene 数 %d != mRNA 数 %d" % (n_gene, n_mrna))

    # -- 期望计数 --
    if expected_count is not None:
        if n_mrna == expected_count and n_gene == expected_count:
            checker.ok("计数符合预期: gene=mRNA=%s" % fmt_int(expected_count))
        else:
            checker.err("计数不符: gene=%s / mRNA=%s，预期 %s"
                        % (fmt_int(n_gene), fmt_int(n_mrna), fmt_int(expected_count)))
    if expected_unplaced is not None:
        if unplaced_genes == expected_unplaced:
            checker.ok("ChrUn_ 上基因数符合预期: %d" % unplaced_genes)
        else:
            checker.err("ChrUn_ 上基因数 %d != 预期 %d" % (unplaced_genes, expected_unplaced))

    log("  [INFO] features=%d（%s）, seqid=%d, gene=%s, mRNA=%s, ChrUn_基因=%d"
        % (n_features,
           ", ".join("%s=%d" % (k, v) for k, v in sorted(feature_types.items())),
           len(seqid_counter), fmt_int(n_gene), fmt_int(n_mrna), unplaced_genes))
    return {
        "path": path,
        "features": n_features,
        "feature_types": feature_types,
        "seqids": seqid_counter,
        "gene": n_gene,
        "mRNA": n_mrna,
        "gene_ids": gene_ids,
        "mrna_ids": mrna_ids,
        "mrna_id_list": mrna_id_list,
        "unplaced_genes": unplaced_genes,
        "unplaced_mrna": unplaced_mrna,
    }


def check_fasta(path, checker, role="fa"):
    """FASTA 头规则检查；返回头 ID 列表。"""
    log("[%s] %s" % (role.upper(), path))
    ids = []
    seen = set()
    dups = []
    bad = []
    n = 0
    with open_text(path) as fh:
        for line in fh:
            if not line.startswith(">"):
                continue
            n += 1
            name, _ = split_header(line)
            if name is None:
                continue
            ids.append(name)
            if name in seen:
                dups.append(name)
            seen.add(name)
            if role == "fa":
                if not name.startswith("Chr"):
                    bad.append(name)
            else:
                if not RE_DIGIT_END.search(name):
                    bad.append(name)
    if role == "fa":
        if bad:
            checker.err("%d 个 FASTA 头不以 'Chr' 开头（示例: %s）"
                        % (len(bad), ", ".join(bad[:10])))
        else:
            checker.ok("FASTA 头全部以 'Chr' 开头（%d 条）" % n)
    else:
        if bad:
            checker.err("%d 个序列 ID 不以 '.数字' 结尾（示例: %s）"
                        % (len(bad), ", ".join(bad[:10])))
        else:
            checker.ok("序列 ID 全部以 '.数字' 结尾（%d 条）" % n)
    if dups:
        checker.err("FASTA 序列 ID 重复 %d 个（示例: %s）"
                    % (len(dups), ", ".join(dups[:10])))
    else:
        checker.ok("FASTA 序列 ID 唯一")
    return ids


def check_pep_clean(path, checker):
    log("[PEP-CLEAN] %s" % path)
    bad = 0
    bad_example = []
    with open_text(path) as fh:
        cur = None
        for line in fh:
            if line.startswith(">"):
                cur, _ = split_header(line)
                continue
            if "." in line or "*" in line:
                bad += 1
                if len(bad_example) < 5:
                    bad_example.append(cur or "?")
    if bad:
        checker.err("%d 行蛋白序列含 '.' 或 '*'（示例: %s）"
                    % (bad, ", ".join(bad_example)))
    else:
        checker.ok("蛋白序列行无 '.'/'*'（平台 check_genome_files 硬性规则）")


def _guess_companion(gff_path, ext):
    base = gff_path
    for suffix in (".gff3.gz", ".gff3"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    for candidate in (base + "." + ext, base + "." + ext + ".gz"):
        if os.path.isfile(candidate):
            return candidate
    return None


def cmd_check(args):
    checker = Checker()
    gff_paths = []
    if args.gff3:
        gff_paths = list(args.gff3)
    elif args.dir:
        if not os.path.isdir(args.dir):
            die("--dir 不是目录: %s" % args.dir)
        for name in sorted(os.listdir(args.dir)):
            if name.endswith(".gff3") or name.endswith(".gff3.gz"):
                gff_paths.append(os.path.join(args.dir, name))
    if not gff_paths:
        die("check 需要 --gff3 FILE... 或 --dir DIR（目录中需有 *.gff3）")
    for path in gff_paths:
        if not os.path.isfile(path):
            die("GFF3 文件不存在: %s" % path)

    expect_counts = _ints_arg(args.expect_counts)
    expect_unplaced = _ints_arg(args.expect_unplaced)
    if expect_counts is not None and len(expect_counts) != len(gff_paths):
        die("--expect-counts 给了 %d 个值，但 GFF 文件有 %d 个"
            % (len(expect_counts), len(gff_paths)))
    if expect_unplaced is not None and len(expect_unplaced) != len(gff_paths):
        die("--expect-unplaced 给了 %d 个值，但 GFF 文件有 %d 个"
            % (len(expect_unplaced), len(gff_paths)))

    log("=" * 72)
    log("normalize_diploid.py check -- %d 个 GFF3" % len(gff_paths))
    log("=" * 72)

    results = []
    for idx, path in enumerate(gff_paths):
        ec = expect_counts[idx] if expect_counts else None
        eu = expect_unplaced[idx] if expect_unplaced else None
        results.append(check_gff(path, checker, ec, eu))

    # 跨文件 / 跨物种唯一性
    log("-" * 72)
    log("[CROSS-FILE] 跨文件 ID 唯一性")
    if len(results) > 1:
        mrna_owner = {}
        gene_owner = {}
        dup_mrna = []
        dup_gene = []
        for res in results:
            for rid in res["mrna_ids"]:
                if rid in mrna_owner:
                    dup_mrna.append(rid)
                else:
                    mrna_owner[rid] = res["path"]
            for rid in res["gene_ids"]:
                if rid in gene_owner:
                    dup_gene.append(rid)
                else:
                    gene_owner[rid] = res["path"]
        total_mrna = sum(len(r["mrna_ids"]) for r in results)
        total_gene = sum(len(r["gene_ids"]) for r in results)
        if dup_mrna:
            checker.err("跨文件重复 mRNA ID %d 个（合并 %d 条 / 去重 %d 条，示例: %s）"
                        % (len(dup_mrna), total_mrna, len(mrna_owner),
                           ", ".join(sorted(dup_mrna)[:10])))
        else:
            checker.ok("跨文件 mRNA ID 无重复（%d 条，去重 %d 条）"
                       % (total_mrna, len(mrna_owner)))
        if dup_gene:
            checker.err("跨文件重复 gene ID %d 个（合并 %d 条 / 去重 %d 条，示例: %s）"
                        % (len(dup_gene), total_gene, len(gene_owner),
                           ", ".join(sorted(dup_gene)[:10])))
        else:
            checker.ok("跨文件 gene ID 无重复（%d 条，去重 %d 条）"
                       % (total_gene, len(gene_owner)))

    # 伴生文件（fa / cds / pep）：显式参数优先，否则 --dir 模式下按同名推导
    log("-" * 72)
    log("[COMPANION] 四件套配套检查")
    fa_paths = {}
    cds_paths = {}
    pep_paths = {}
    if args.fa or args.cds or args.pep:
        if args.fa:
            fa_paths[gff_paths[0]] = args.fa
        if args.cds:
            cds_paths[gff_paths[0]] = args.cds
        if args.pep:
            pep_paths[gff_paths[0]] = args.pep
    elif args.dir:
        found_any = False
        for path in gff_paths:
            fa = _guess_companion(path, "fa")
            cds = _guess_companion(path, "cds")
            pep = _guess_companion(path, "pep")
            if fa:
                fa_paths[path] = fa
                found_any = True
            if cds:
                cds_paths[path] = cds
                found_any = True
            if pep:
                pep_paths[path] = pep
                found_any = True
        if not found_any:
            checker.warn("目录中没有 .fa/.cds/.pep 伴生文件，只检查 GFF3")

    mrna_id_set = set()
    for res in results:
        mrna_id_set |= res["mrna_ids"]

    for path, fa in fa_paths.items():
        fa_ids = check_fasta(fa, checker, role="fa")
        res = next(r for r in results if r["path"] == path)
        gff_seqids = set(res["seqids"].keys())
        missing = gff_seqids - set(fa_ids)
        if missing:
            checker.err("GFF seqid 有 %d 个不在 FASTA 中（示例: %s）"
                        % (len(missing), ", ".join(sorted(missing)[:10])))
        else:
            checker.ok("GFF 的 %d 个 seqid 全部存在于 FASTA" % len(gff_seqids))
    for path, cds in cds_paths.items():
        cds_ids = check_fasta(cds, checker, role="cds")
        res = next(r for r in results if r["path"] == path)
        mrna = res["mrna_ids"]
        missing = mrna - set(cds_ids)
        extra = set(cds_ids) - mrna
        if missing or extra:
            checker.err("CDS 序列 ID 与 mRNA ID 不一致：缺 %d / 多 %d（示例: %s）"
                        % (len(missing), len(extra),
                           ", ".join(sorted(missing)[:5] + sorted(extra)[:5])))
        else:
            checker.ok("CDS 序列 ID 与 mRNA ID 完全一致（%d 条）" % len(cds_ids))
    for path, pep in pep_paths.items():
        pep_ids = check_fasta(pep, checker, role="pep")
        res = next(r for r in results if r["path"] == path)
        mrna = res["mrna_ids"]
        missing = mrna - set(pep_ids)
        extra = set(pep_ids) - mrna
        if missing or extra:
            checker.err("PEP 序列 ID 与 mRNA ID 不一致：缺 %d / 多 %d（示例: %s）"
                        % (len(missing), len(extra),
                           ", ".join(sorted(missing)[:5] + sorted(extra)[:5])))
        else:
            checker.ok("PEP 序列 ID 与 mRNA ID 完全一致（%d 条）" % len(pep_ids))
        check_pep_clean(pep, checker)

    # ---- 汇总 ----
    log("=" * 72)
    if checker.warnings:
        log("[SUMMARY] warning: %d" % len(checker.warnings))
    if checker.errors:
        log("[SUMMARY] FAIL: %d 个错误 / %d 个文件" % (len(checker.errors), len(gff_paths)))
        for e in checker.errors:
            log("  [FAIL] " + e)
        return 1
    log("[SUMMARY] ALL CHECKS PASSED（%d 个 GFF3%s）"
        % (len(gff_paths),
           ("，包含 fa/cds/pep 伴生文件" if (fa_paths or cds_paths or pep_paths) else "")))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _add_id_prefix_args(parser, for_pep=False):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--strg-only-prefix", action="store_true",
                       help="显式声明只对 STRG 家族加前缀（这是默认行为；与 "
                            "--prefix-all-ids 互斥，便于命令自解释）")
    group.add_argument("--prefix-all-ids", action="store_true",
                       help="对所有 gene/mRNA ID 加 --id-prefix 前缀（默认只加 STRG 家族）")
    parser.add_argument("--prefix-family-regex", default=DEFAULT_PREFIX_FAMILY,
                        help="需要加前缀的 ID 家族正则（默认 %r，只匹配 gene/model.model.STRG.*）"
                             % DEFAULT_PREFIX_FAMILY)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="normalize_diploid.py",
        description="WheatOmics 二倍体基因组四件套归一化工具：FASTA 头 / GFF3 seqid / "
                    "gene-mRNA ID / pep 终止符 + 多文件汇总断言。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例：
  %(prog)s fasta --assembly-report report.txt --fasta genome.fna.gz --out MT.fa
  %(prog)s fasta --dry-run --assembly-report report.txt --mapping map.tsv
  %(prog)s gff3 --gff3 genes.gff3.gz --assembly-report report.txt --out MT.gff3 \\
      --id-prefix "AeCom.AE783." --mapping MT.gff3.mapping.tsv --id-map MT.idmap.tsv
  %(prog)s pep --pep proteins.fasta.gz --out MT.pep
  %(prog)s check --dir . 
  %(prog)s check --gff3 a.gff3 b.gff3 --expect-counts 51203,47246 --expect-unplaced 38,53
""")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    # fasta
    p = sub.add_parser("fasta", help="基因组 FASTA 头改名（GenBank accn -> Chr*/ChrUn_*）")
    p.add_argument("--fasta", help="输入 FASTA（.fa/.fna/.fa.gz，支持 stdin '-'）")
    p.add_argument("--assembly-report", required=True, help="NCBI *_assembly_report.txt")
    p.add_argument("--out", help="输出 FASTA；以 .gz 结尾自动压缩")
    p.add_argument("--mapping", help="输出映射表 TSV（默认 <out>.mapping.tsv）")
    p.add_argument("--prefix", default="Chr", help="染色体前缀（默认 Chr）")
    p.add_argument("--unplaced-prefix", default="ChrUn_",
                   help="未定位序列前缀（默认 ChrUn_）")
    p.add_argument("--seqid-map", help="额外 seqid 映射 TSV（旧名<TAB>新名），优先级最高")
    p.add_argument("--dry-run", action="store_true",
                   help="只解析 assembly_report 并输出映射预检（不读 FASTA）")
    p.add_argument("--partial", action="store_true",
                   help="片段/冒烟测试：跳过序列数、总长、覆盖率 100%% 的全量断言")
    p.add_argument("--allow-unmapped", action="store_true",
                   help="允许无法映射的 FASTA 头（只告警，不失败）")
    p.set_defaults(func=cmd_fasta)

    # gff3
    p = sub.add_parser("gff3", help="GFF3 seqid 改名 + gene/mRNA ID 规范化")
    p.add_argument("--gff3", required=True, help="输入 GFF3（.gff3/.gff3.gz）")
    p.add_argument("--assembly-report", required=True, help="NCBI *_assembly_report.txt")
    p.add_argument("--out", help="输出 GFF3；以 .gz 结尾自动压缩")
    p.add_argument("--mapping", help="输出 seqid 映射表 TSV（默认 <out>.mapping.tsv）")
    p.add_argument("--id-prefix", default="",
                   help="跨物种重复 ID 前缀，如 'AeCom.AE783.'（默认只加 STRG 家族，见 "
                        "--prefix-all-ids / --strg-only-prefix）")
    p.add_argument("--keep-author-ids", action="store_true",
                   help="只改 seqid，保留作者 gene/mRNA ID 原样（供 renumber_gff_ids.py 后续按平台规则重编号）")
    p.add_argument("--id-map", help="输出 gene/mRNA ID 改名映射（.json 或 .tsv）")
    p.add_argument("--also-ids", nargs="+", metavar="MAP",
                   help="其它物种已生成的 id-map（.json/.tsv），断言新 ID 不与之冲突")
    p.add_argument("--allow-unknown-seqids", action="store_true",
                   help="允许 assembly_report 中不存在的 seqid（按 ChrUn_ 规则处理）")
    p.add_argument("--no-coord-check", action="store_true",
                   help="跳过坐标合法性/越界检查")
    p.add_argument("--prefix", default="Chr", help="染色体前缀（默认 Chr）")
    p.add_argument("--unplaced-prefix", default="ChrUn_",
                   help="未定位序列前缀（默认 ChrUn_）")
    p.add_argument("--dry-run", action="store_true",
                   help="只做第一遍解析与映射预检，不写输出 GFF3")
    _add_id_prefix_args(p)
    p.set_defaults(func=cmd_gff3)

    # pep
    p = sub.add_parser("pep", help="蛋白 FASTA 头 ID 规范化 + '.'/'*' 终止符清理")
    p.add_argument("--pep", required=True, help="输入蛋白 FASTA")
    p.add_argument("--out", required=True, help="输出蛋白 FASTA；.gz 结尾自动压缩")
    p.add_argument("--id-map", help="gff3 生成的精确 ID 映射（.json/.tsv），优先使用")
    p.add_argument("--stop-mode", choices=["x", "trim", "drop", "keep"], default="x",
                   help="终止符处理：x=全部替换为 X（默认，保长度）；"
                        "trim=去行尾、内部换 X；drop=全部删除；keep=不动")
    p.add_argument("--id-prefix", default="",
                   help="与 gff3 相同的跨物种 ID 前缀")
    _add_id_prefix_args(p)
    p.set_defaults(func=cmd_pep)

    # check
    p = sub.add_parser("check", help="归一化产物汇总断言（多文件 / 跨物种查重）")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--dir", help="dataset 目录（自动找 *.gff3 及同名 .fa/.cds/.pep）")
    src.add_argument("--gff3", nargs="+", metavar="FILE",
                     help="一个或多个归一化 GFF3（多文件时做跨文件查重）")
    p.add_argument("--fa", help="显式指定 .fa（单文件模式）")
    p.add_argument("--cds", help="显式指定 .cds（单文件模式）")
    p.add_argument("--pep", help="显式指定 .pep（单文件模式）")
    p.add_argument("--expect-counts", help="各 GFF 预期 mRNA 数，逗号分隔，按顺序对应")
    p.add_argument("--expect-unplaced", help="各 GFF 预期 ChrUn_ 上基因数，逗号分隔")
    p.set_defaults(func=cmd_check)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
