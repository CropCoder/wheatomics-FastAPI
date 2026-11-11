#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""renumber_gff_ids.py — 把 GFF3 的 gene/mRNA ID 重编号为平台风格

规则（WheatOmics 平台主流命名，如 TraesCS1A01G000100.1 / AeCom.PI551049.r1.1MG000010.1）：

  gene ID  =  <--id-prefix> + <染色体代号> + "G" + <位数固定、每 --step 递增的序号>
  mRNA ID  =  gene ID + "." + <该基因下 mRNA 的序号>

  * 每条染色体独立从 ``--step``（默认 100）开始，按基因 **起始坐标升序** 依次编号：
    000100 / 000200 / 000300 …
  * 未定位序列（ChrUn_*）统一用 ``--unplaced-token``（默认 ``Un``）作为染色体代号，
    跨所有未定位序列按（seqid, start）继续统一编号。
  * 原 ID 保留在 GFF 属性 ``original_id``（可关）并写入 ``--id-map``，可回溯作者注释。
  * exon/CDS/UTR 等派生 ID 会随父 ID 同步改写（保留平台不校验的派生 ID 习惯）。

输入要求：GFF3 的 seqid 已经是 ``Chr1M`` / ``ChrUn_*`` 形式
（先跑 ``normalize_diploid.py gff3`` 做 seqid 改名；本脚本只负责 ID 重编号）。

用法：
  # 重编号
  renumber_gff_ids.py --gff3 in.gff3[.gz] --out out.gff3[.gz] \\
      --id-prefix "AeCom.AE783.r1." --id-map out.idmap.tsv \\
      [--digits 6] [--step 100] [--unplaced-token Un] \\
      [--no-original-id-attr] [--original-id-attr original_id] [--dry-run]

  # 校验（服务器 G1/G2 闸门可直接用）
  renumber_gff_ids.py --check --gff3 out.gff3.gz --id-prefix "AeCom.AE783.r1."

选项：
  --digits N       序号位数（默认 6；6 位支持单染色体 ≤9999 个基因，本批最大 8332）
  --step N         序号步长（默认 100）
  --unplaced-token 未定位序列代号（默认 Un）
  --check          只校验不重写：ID 模式、每条染色体从 step 起严格 +step、坐标有序、唯一性
"""
from __future__ import annotations

import argparse
import gzip
import io
import re
import sys
from collections import defaultdict, OrderedDict

__version__ = "1.0.0"

RE_CHR = re.compile(r"^Chr(\d+[A-Za-z])$")
RE_MRNA_TYPES = ("mRNA", "transcript")
RE_DIGIT_END = re.compile(r"\.\d+$")


# ---------------------------------------------------------------- I/O helpers
def open_text(path):
    if path.endswith(".gz"):
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def open_out(path):
    if path.endswith(".gz"):
        return io.TextIOWrapper(gzip.open(path, "wb"), encoding="utf-8")
    return open(path, "w", encoding="utf-8")


def log(msg):
    print(msg, file=sys.stderr)


def die(msg, code=1):
    print("[ERROR] " + msg, file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- GFF helpers
def parse_attrs(attr):
    items = []
    for item in attr.rstrip("\n").split(";"):
        if "=" in item:
            key, value = item.split("=", 1)
            items.append((key, value))
        elif item:
            items.append((item, None))
    return items


def format_attrs(items):
    out = []
    for key, value in items:
        out.append(key if value is None else "%s=%s" % (key, value))
    return ";".join(out)


def get_attr(items, key):
    for k, v in items:
        if k == key:
            return v
    return None


def seqid_token(seqid, unplaced_token):
    m = RE_CHR.match(seqid)
    if m:
        return m.group(1)
    if seqid.startswith("ChrUn_"):
        return unplaced_token
    return None


def derived_id_fix(value, parents, id_map):
    """exon/CDS 等派生 ID：把父 ID 子串替换成新父 ID（父 ID 越长的先替换）。"""
    for old_parent in sorted(parents, key=len, reverse=True):
        new_parent = id_map.get(old_parent)
        if new_parent and old_parent in value:
            return value.replace(old_parent, new_parent, 1)
    return value


# ---------------------------------------------------------------- 收集与分配
def collect_records(path):
    """扫描一遍 GFF，收集 gene、mRNA 的坐标与父子关系。"""
    genes = OrderedDict()   # old gene ID -> dict(seqid,start,end,order)
    mrnas = OrderedDict()   # old mRNA ID -> dict(parent,start,end,order)
    n_other = defaultdict(int)
    for order, parts in enumerate(_iter_data_lines(path)):
        ftype = parts[2]
        attrs = parse_attrs(parts[8])
        rid = get_attr(attrs, "ID")
        if not rid:
            continue
        if ftype == "gene":
            genes[rid] = {
                "seqid": parts[0],
                "start": _to_int(parts[3]),
                "end": _to_int(parts[4]),
                "order": order,
            }
        elif ftype in RE_MRNA_TYPES:
            parent = get_attr(attrs, "Parent")
            parent = parent.split(",")[0] if parent else None
            mrnas[rid] = {
                "parent": parent,
                "start": _to_int(parts[3]),
                "end": _to_int(parts[4]),
                "order": order,
            }
        else:
            n_other[ftype] += 1
    return genes, mrnas, n_other


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def iter_data_lines(path):
    in_fasta = False
    with open_text(path) as fh:
        for line in fh:
            if in_fasta:
                continue
            if line.startswith("##FASTA"):
                in_fasta = True
                continue
            if line.startswith("#") or not line.strip():
                continue
            parts = line.rstrip("\n").rstrip("\r").split("\t")
            if len(parts) < 9:
                continue
            yield parts


_iter_data_lines = iter_data_lines  # noqa: F811  (alias for明确语义)


def build_id_map(genes, mrnas, id_prefix, digits, step, unplaced_token):
    """按染色体分组、坐标排序，生成 old ID -> new ID 映射。"""
    children = defaultdict(list)
    for mid, meta in mrnas.items():
        if meta["parent"]:
            children[meta["parent"]].append(mid)

    per_seq = defaultdict(list)
    for gid, meta in genes.items():
        per_seq[meta["seqid"]].append(gid)

    id_map = OrderedDict()
    stats = {"per_seq": {}, "unplaced_genes": 0, "chr_genes": 0,
             "genes": len(genes), "mrnas": len(mrnas), "missing_parent": 0}

    def assign(gid, gnew):
        id_map[gid] = gnew
        kids = sorted(children.get(gid, []),
                      key=lambda m: (mrnas[m]["start"], mrnas[m]["end"], mrnas[m]["order"]))
        for k, mid in enumerate(kids, 1):
            id_map[mid] = "%s.%d" % (gnew, k)

    # ① 染色体：每条染色体独立从 step 开始编号
    unplaced = []   # (seqid, start, end, order, gid)
    for seqid in sorted(per_seq):
        token = seqid_token(seqid, unplaced_token)
        if token is None:
            die("seqid 不是 ChrN? / ChrUn_* 形式（请先跑 normalize_diploid.py gff3）: %r" % seqid)
        if seqid.startswith("ChrUn_"):
            for gid in per_seq[seqid]:
                unplaced.append((seqid, genes[gid]["start"], genes[gid]["end"],
                                 genes[gid]["order"], gid))
            continue
        gids = sorted(per_seq[seqid],
                      key=lambda g: (genes[g]["start"], genes[g]["end"], genes[g]["order"]))
        if len(gids) > (10 ** digits - 1) // step:
            die("seqid %s 有 %d 个基因，超出 %d 位序号 × step=%d 的容量"
                % (seqid, len(gids), digits, step))
        for i, gid in enumerate(gids):
            num = (i + 1) * step
            assign(gid, "%s%sG%0*d" % (id_prefix, token, digits, num))
        stats["per_seq"][seqid] = {
            "token": token, "genes": len(gids),
            "first_id": id_map[gids[0]] if gids else None,
            "last_id": id_map[gids[-1]] if gids else None,
        }
        stats["chr_genes"] += len(gids)

    # ② 未定位序列：跨所有 ChrUn_* 统一编号（按 seqid + 坐标排序）
    if unplaced:
        unplaced.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
        if len(unplaced) > (10 ** digits - 1) // step:
            die("未定位序列共 %d 个基因，超出 %d 位序号 × step=%d 的容量"
                % (len(unplaced), digits, step))
        for i, (seqid, _start, _end, _order, gid) in enumerate(unplaced):
            num = (i + 1) * step
            assign(gid, "%s%sG%0*d" % (id_prefix, unplaced_token, digits, num))
            stats["per_seq"].setdefault(seqid, {
                "token": unplaced_token, "genes": 0, "first_id": None, "last_id": None})
            ps = stats["per_seq"][seqid]
            ps["genes"] += 1
            ps["first_id"] = ps["first_id"] or id_map[gid]
            ps["last_id"] = id_map[gid]
        stats["unplaced_genes"] = len(unplaced)

    for mid, meta in mrnas.items():
        if mid not in id_map:
            stats["missing_parent"] += 1
    return id_map, children, stats


def rewrite_file(src, dst, id_map, original_id_attr, keep_original):
    n_lines = 0
    n_mapped = 0
    unresolved = 0
    in_fasta = False
    with open_text(src) as fin, open_out(dst) as fout:
        for line in fin:
            n_lines += 1
            if in_fasta:
                fout.write(line)
                continue
            if line.startswith("##FASTA"):
                in_fasta = True
                fout.write(line if line.endswith("\n") else line + "\n")
                continue
            if line.startswith("#") or not line.strip():
                fout.write(line if line.endswith("\n") else line + "\n")
                continue
            parts = line.rstrip("\n").rstrip("\r").split("\t")
            if len(parts) < 9:
                fout.write(line)
                continue
            ftype = parts[2]
            items = parse_attrs(parts[8])
            old_id = get_attr(items, "ID")
            old_parents = [x for x in (get_attr(items, "Parent") or "").split(",") if x]

            new_items = []
            for key, value in items:
                if value is None:
                    new_items.append((key, None))
                    continue
                if key == "ID":
                    new_value = id_map.get(value)
                    if new_value is None and old_parents:
                        new_value = derived_id_fix(value, old_parents, id_map)
                    if new_value is None:
                        new_value = value
                        unresolved += 1
                    elif new_value != value:
                        n_mapped += 1
                    new_items.append((key, new_value))
                elif key in ("Parent", "Derives_from"):
                    mapped = [id_map.get(t, t) for t in value.split(",")]
                    new_items.append((key, ",".join(mapped)))
                elif key == "Name":
                    new_items.append((key, id_map.get(value, value)))
                else:
                    new_items.append((key, value))

            # 原始 ID 留痕（仅 gene/mRNA 行，且确有改名时）
            if keep_original and old_id and old_id in id_map and ftype in ("gene",) + RE_MRNA_TYPES:
                if not any(k == original_id_attr for k, _ in new_items):
                    new_items.append((original_id_attr, old_id))

            parts[8] = format_attrs(new_items)
            fout.write("\t".join(parts) + "\n")
    return {"lines": n_lines, "mapped_ids": n_mapped, "unresolved_ids": unresolved}


# ---------------------------------------------------------------- 校验模式
def check_file(path, id_prefix, digits, step, unplaced_token):
    errors, warns = [], []
    genes = OrderedDict()  # seqid -> [(num, gid, start)]
    mrna_count = 0
    gene_ids, mrna_ids = set(), set()
    bad_gene_pattern, bad_mrna = [], []
    gene_pat = re.compile(r"^%s(?:%s|%s)G\d{%d}$"
                          % (re.escape(id_prefix),
                             re.escape(unplaced_token),
                             r"\d+[A-Za-z]", digits))
    for parts in iter_data_lines(path):
        ftype = parts[2]
        attrs = parse_attrs(parts[8])
        rid = get_attr(attrs, "ID")
        if ftype == "gene":
            if not rid:
                errors.append("gene 行缺 ID")
                continue
            if rid in gene_ids:
                errors.append("gene ID 重复: %s" % rid)
            gene_ids.add(rid)
            if not gene_pat.match(rid):
                bad_gene_pattern.append(rid)
                continue
            token = seqid_token(parts[0], unplaced_token)
            if token is None:
                errors.append("seqid 非法: %s" % parts[0])
                continue
            m = re.search(r"G(\d+)$", rid)
            num = int(m.group(1)) if m else -1
            genes.setdefault(parts[0], []).append((num, rid, _to_int(parts[3])))
        elif ftype in RE_MRNA_TYPES:
            mrna_count += 1
            if not rid:
                errors.append("mRNA 行缺 ID")
                continue
            if rid in mrna_ids:
                errors.append("mRNA ID 重复: %s" % rid)
            mrna_ids.add(rid)
            if not RE_DIGIT_END.search(rid):
                bad_mrna.append(rid)
    if bad_gene_pattern:
        errors.append("%d 个 gene ID 不符合 %s<token>G<%d位数字>（示例: %s）"
                      % (len(bad_gene_pattern), id_prefix, digits, ", ".join(bad_gene_pattern[:5])))
    if bad_mrna:
        errors.append("%d 个 mRNA ID 不以 .数字 结尾（示例: %s）"
                      % (len(bad_mrna), ", ".join(bad_mrna[:5])))
    # ① 每条染色体：编号从 step 起严格 +step，且与坐标顺序一致
    unplaced_rows = []   # (num, gid, seqid, start)
    for seqid, rows in genes.items():
        if seqid.startswith("ChrUn_"):
            for num, gid, start in rows:
                unplaced_rows.append((num, gid, seqid, start))
            continue
        rows_sorted = sorted(rows, key=lambda x: x[0])
        expect = step
        for num, gid, start in rows_sorted:
            if num != expect:
                errors.append("%s 编号不连续：期望 %d 实得 %d（%s）"
                              % (seqid, expect, num, gid))
                break
            expect += step
        if len(rows) > 1:
            by_coord = [gid for _, gid, _ in sorted(rows, key=lambda x: (x[2], x[1]))]
            by_num = [gid for _, gid, _ in rows_sorted]
            if by_coord != by_num:
                errors.append("%s 编号顺序与基因坐标顺序不一致" % seqid)
    # ② 未定位序列：跨所有 ChrUn_* 全局编号连续（按 seqid+坐标排序）
    if unplaced_rows:
        unplaced_rows.sort(key=lambda x: x[0])
        expect = step
        for num, gid, seqid, start in unplaced_rows:
            if num != expect:
                errors.append("ChrUn 全局编号不连续：期望 %d 实得 %d（%s / %s）"
                              % (expect, num, seqid, gid))
                break
            expect += step
        by_coord = [gid for _, gid, _, _ in
                    sorted(unplaced_rows, key=lambda x: (x[2], x[3], x[1]))]
        by_num = [gid for _, gid, _, _ in unplaced_rows]
        if by_coord != by_num:
            errors.append("ChrUn 编号顺序与（seqid,坐标）顺序不一致")
    # 汇总
    log("[CHECK] %s" % path)
    log("  gene=%d  mRNA=%d  染色体数=%d（其中未定位 %d）"
        % (len(gene_ids), mrna_count,
           len([s for s in genes if not s.startswith("ChrUn_")]),
           len([s for s in genes if s.startswith("ChrUn_")])))
    for seqid in sorted(genes):
        rows = sorted(genes[seqid], key=lambda x: x[0])
        if rows:
            log("  %-28s genes=%-5d  %s … %s"
                % (seqid, len(rows), rows[0][1], rows[-1][1]))
    if errors:
        for e in errors[:20]:
            log("  [FAIL] " + e)
        return False
    log("  [PASS] 重编号规则全部通过（%d 位序号 / step=%d / 前缀 %r）"
        % (digits, step, id_prefix))
    return True


# ---------------------------------------------------------------- 主流程
def build_parser():
    p = argparse.ArgumentParser(
        prog="renumber_gff_ids.py",
        description="按染色体重编号 gene/mRNA ID 为平台风格（每步 --step 递增），或校验重编号产物。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("用法：", 1)[-1])
    p.add_argument("--version", action="version", version="renumber_gff_ids.py " + __version__)
    p.add_argument("--gff3", required=True, help="输入 GFF3（seqid 需已归一化为 Chr*/ChrUn_*）")
    p.add_argument("--out", help="输出 GFF3（--check 模式可省略；支持 .gz）")
    p.add_argument("--id-prefix", required=True,
                   help="ID 前缀，例：AeCom.AE783.r1.（务必以 . 结尾）")
    p.add_argument("--id-map", help="输出 old_id<TAB>new_id<TAB>type 映射表")
    p.add_argument("--digits", type=int, default=6, help="序号位数（默认 6）")
    p.add_argument("--step", type=int, default=100, help="序号步长（默认 100）")
    p.add_argument("--unplaced-token", default="Un", help="未定位序列代号（默认 Un）")
    p.add_argument("--original-id-attr", default="original_id",
                   help="保留原 ID 的属性名（默认 original_id）")
    p.add_argument("--no-original-id-attr", action="store_true", help="不写 original_id 属性")
    p.add_argument("--dry-run", action="store_true", help="只计算并打印摘要，不写文件")
    p.add_argument("--check", action="store_true", help="只校验现有 GFF 是否满足重编号规则")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.id_prefix.endswith("."):
        die("--id-prefix 必须以 '.' 结尾（例 AeCom.AE783.r1.）")
    if args.digits < 3 or args.step < 1:
        die("--digits 至少 3，--step 至少 1")
    if args.check:
        ok = check_file(args.gff3, args.id_prefix, args.digits, args.step, args.unplaced_token)
        return 0 if ok else 1
    if not args.out:
        die("重编号模式需要 --out（或用 --check 只校验）")

    genes, mrnas, n_other = collect_records(args.gff3)
    log("[collect] gene=%d mRNA=%d 其它特征=%s"
        % (len(genes), len(mrnas), dict(n_other)))
    id_map, children, stats = build_id_map(genes, mrnas, args.id_prefix,
                                           args.digits, args.step, args.unplaced_token)
    log("[assign] 染色体基因 %d / 未定位基因 %d；缺父 mRNA %d"
        % (stats["chr_genes"], stats["unplaced_genes"], stats["missing_parent"]))
    for seqid in sorted(stats["per_seq"]):
        s = stats["per_seq"][seqid]
        log("  %-28s %5d genes  %s … %s"
            % (seqid, s["genes"], s["first_id"], s["last_id"]))
    if args.dry_run:
        log("[DRY] 未写文件；如需落盘去掉 --dry-run")
        return 0

    res = rewrite_file(args.gff3, args.out, id_map,
                       args.original_id_attr, not args.no_original_id_attr)
    if args.id_map:
        with open(args.id_map, "w", encoding="utf-8") as fh:
            fh.write("#old_id\tnew_id\tfeature_type\n")
            for old_id, new_id in id_map.items():
                ftype = "gene" if old_id in genes else ("mRNA" if old_id in mrnas else "?")
                fh.write("%s\t%s\t%s\n" % (old_id, new_id, ftype))
        log("[id-map] %s（%d 条）" % (args.id_map, len(id_map)))
    log("[write] %s（行数 %d，改名 ID %d，未解析 %d）"
        % (args.out, res["lines"], res["mapped_ids"], res["unresolved_ids"]))

    # 写后自检
    ok = check_file(args.out, args.id_prefix, args.digits, args.step, args.unplaced_token)
    if not ok:
        die("重编号后自检失败", 2)
    log("[SUCCESS] 重编号完成并通过校验")
    return 0


if __name__ == "__main__":
    sys.exit(main())
