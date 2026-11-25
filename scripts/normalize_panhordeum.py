#!/usr/bin/env python3
"""PanHordeum v1 单个基因组的平台归一化（ENA 组装 + PGSB/e!DAL 注释 → 平台四件套）。

输入（同一目录）：
  * ``*.ena.fa``     ENA browser API 下载的组装 FASTA，头形如
                      ``>ENA|OZ317656|OZ317656.1 Hordeum chilense genome assembly, chromosome: 1H``
  * ``*.gff3``       PGSB BPGv2 注释（main 集合），seqid 形如 ``chr1H`` / ``chr1H_1``
  * ``*.cds.fa``     与 GFF mRNA 一一对应的 CDS
  * ``*.aa.fa``      与 GFF mRNA 一一对应的蛋白（可能含 ``.``/``*`` 终止符）

输出（``--out`` 目录）：
  * ``<tag>.fa``       头统一为 ``Chr1H`` / ``Chr1H_1`` / ``ChrUn_<ACC>``
  * ``<tag>.gff3``     seqid 同步改写；mRNA ID 保持作者 ID（需以 ``.数字`` 结尾）
  * ``<tag>.cds``      ID 与 GFF mRNA 一致
  * ``<tag>.pep``      同上，清除 ``.`` / ``*``
  * ``seqid_mapping.tsv``、``normalize_report.txt``

用法：
  python3 scripts/normalize_panhordeum.py --dir /path/raw/Hordeum_chilense_GRA1000 \
      --tag Hordeum_chilense_GRA1000 --out /path/out
"""
from __future__ import annotations

import argparse
import gzip
import io
import re
import sys
from pathlib import Path

csv = None  # not used; keep imports light


def open_text(path: Path):
    if str(path).endswith(".gz"):
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8", errors="replace")
    return open(path, encoding="utf-8", errors="replace")


CHR_DESC = re.compile(r"chromosome:\s*(\S+)")
SCAFFOLD_DESC = re.compile(r"(?:scaffold|contig):\s*(\S+)")
ENA_HEAD = re.compile(r"^ENA\|([^|]+)\|(\S+)\s*(.*)$")
RE_MRNA_DIGIT = re.compile(r"\.\d+$")


def die(msg: str, code: int = 1):
    print("[ERROR] " + msg, file=sys.stderr)
    raise SystemExit(code)


def find_one(directory: Path, pattern: str) -> Path:
    hits = sorted(directory.glob(pattern))
    if not hits:
        die(f"missing input file: {directory}/{pattern}")
    if len(hits) > 1:
        print(f"[WARN] multiple matches for {pattern}: {[h.name for h in hits]}", file=sys.stderr)
    return hits[0]


# ------------------------------------------------------------------ FASTA
def build_seqid_map(ena_fa: Path) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """FASTA 记录 -> 平台 seqid；同时返回 (old_key, new) 列表。

    染色体：``chromosome: 1H`` -> ``Chr1H``
    未定位：``contig: contig_corrected_v1_185`` -> ``ChrUn_contig_corrected_v1_185``
            （无描述时退化为 ``ChrUn_<accession>``）
    返回的 mapping 同时包含 accession 和描述名两种 key，供 GFF seqid 查找。
    """
    mapping: dict[str, str] = {}
    order: list[tuple[str, str]] = []
    seen_new: dict[str, int] = {}
    with open_text(ena_fa) as fh:
        for line in fh:
            if not line.startswith(">"):
                continue
            header = line[1:].strip()
            m = ENA_HEAD.match(header)
            if m:
                acc, desc = m.group(2), m.group(3)
            else:  # defensive: some mirrors drop the ENA| wrapper
                parts = header.split(None, 1)
                acc, desc = parts[0], (parts[1] if len(parts) > 1 else "")
            chr_m = CHR_DESC.search(desc)
            scaf_m = SCAFFOLD_DESC.search(desc)
            if chr_m:
                token = chr_m.group(1).strip().rstrip(",;")
                new = "Chr" + token
                mapping[token] = new
            elif scaf_m:
                token = scaf_m.group(1).strip().rstrip(",;")
                new = "ChrUn_" + re.sub(r"[^A-Za-z0-9_]", "_", token)
                mapping[token] = new
            else:
                new = "ChrUn_" + re.sub(r"[^A-Za-z0-9_]", "_", acc)
            if new in seen_new:
                seen_new[new] += 1
                new = f"{new}_{seen_new[new]}"
            else:
                seen_new[new] = 0
            mapping[acc] = new
            order.append((acc, new))
    if not mapping:
        die(f"no FASTA records in {ena_fa}")
    return mapping, order


def get_seqids(ena_fa: Path) -> set[str]:
    ids: set[str] = set()
    with open_text(ena_fa) as fh:
        for line in fh:
            if not line.startswith(">"):
                continue
            m = ENA_HEAD.match(line[1:].strip())
            ids.add(m.group(2) if m else line[1:].split()[0])
    return ids


def rewrite_fasta(src: Path, dst: Path, mapping: dict[str, str]) -> int:
    n = 0
    with open_text(src) as fi, open(dst, "w", encoding="utf-8") as fo:
        for line in fi:
            if line.startswith(">"):
                header = line[1:].strip()
                m = ENA_HEAD.match(header)
                acc = m.group(2) if m else header.split()[0]
                new = mapping.get(acc)
                if new is None:
                    die(f"FASTA record not in mapping: {acc}")
                fo.write(">" + new + "\n")
                n += 1
            else:
                fo.write(line)
    return n


# ------------------------------------------------------------------ GFF
def gff_seqid_map(seqid_mapping: dict[str, str]) -> dict[str, str]:
    """GFF seqid -> 平台 seqid。

    PGSB 用 ``chr1H`` / ``chr1H_1`` / ``contig_corrected_v1_127``；
    FASTA 侧可能是 accession 或描述名，统一从 build_seqid_map 的 key 建立别名。
    """
    out: dict[str, str] = {}
    for key, new in seqid_mapping.items():
        out[key] = new
        out[new] = new
        # chr1H 小写形式
        low = new[0].lower() + new[1:] if new[:3] == "Chr" else new
        out[low] = new
        # 长度前缀（chr1H_1 已是完整 token，仍安全）
        if new.startswith("ChrUn_"):
            token = new[len("ChrUn_"):]
            out[token] = new
    return out


def parse_attrs(attr: str) -> dict[str, str]:
    d = {}
    for kv in attr.strip().split(";"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            d[k] = v
    return d


def collect_keep_ids(src: Path, keep_tag: str) -> tuple[set[str], set[str], dict]:
    """选 tag=keep_tag 的 gene 及其 mRNA（PGSB main 里混有 transposon-/plastid-related 模型）。"""
    genes: set[str] = set()
    mrnas: set[str] = set()
    tag_counts: dict[str, int] = {}
    with open_text(src) as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 9:
                continue
            ftype = parts[2]
            if ftype not in ("gene", "mRNA"):
                continue
            a = parse_attrs(parts[8])
            tag = a.get("tag", "")
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
            if tag != keep_tag:
                continue
            if ftype == "gene":
                hid = a.get("ID")
                if hid:
                    genes.add(hid)
            else:
                parent = (a.get("Parent") or "").split(",")[0]
                mid = a.get("ID")
                if mid and (not genes or parent in genes):
                    mrnas.add(mid)
    return genes, mrnas, tag_counts


def rewrite_gff(src: Path, dst: Path, seqid_map: dict[str, str],
                keep_genes: set[str] | None = None,
                keep_mrnas: set[str] | None = None) -> dict:
    stats = {"rows": 0, "mapped": 0, "missing_seqids": set(), "bad_mrna": [],
             "mrna": 0, "gene": 0, "types": {}, "dropped": 0}
    with open_text(src) as fi, open(dst, "w", encoding="utf-8") as fo:
        for line in fi:
            if line.startswith("#"):
                if line.startswith("##sequence-region"):
                    parts = line.rstrip("\n").split()
                    if len(parts) >= 2 and parts[1] in seqid_map:
                        parts[1] = seqid_map[parts[1]]
                        line = " ".join(parts) + "\n"
                    elif len(parts) >= 2:
                        stats["missing_seqids"].add(parts[1])
                        continue
                fo.write(line)
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 9:
                continue
            old = parts[0]
            new = seqid_map.get(old)
            if new is None:
                stats["missing_seqids"].add(old)
                stats["dropped"] += 1
                continue
            stats["mapped"] += 1
            parts[0] = new
            ftype = parts[2]
            a = parse_attrs(parts[8])
            if keep_genes is not None:
                if ftype == "gene":
                    if a.get("ID") not in keep_genes:
                        stats["dropped"] += 1
                        continue
                elif ftype == "mRNA":
                    if a.get("ID") not in (keep_mrnas or set()):
                        stats["dropped"] += 1
                        continue
                elif ftype in ("exon", "CDS", "five_prime_UTR", "three_prime_UTR"):
                    parent = (a.get("Parent") or "").split(",")[0]
                    if parent not in (keep_mrnas or set()):
                        stats["dropped"] += 1
                        continue
            stats["types"][ftype] = stats["types"].get(ftype, 0) + 1
            if ftype == "mRNA":
                stats["mrna"] += 1
                tid = a.get("ID", "")
                if not RE_MRNA_DIGIT.search(tid):
                    stats["bad_mrna"].append(tid)
            elif ftype in ("gene", "pseudogene"):
                stats["gene"] += 1
            fo.write("\t".join(parts) + "\n")
            stats["rows"] += 1
    return stats


def gff_mrna_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    with open_text(path) as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 9 and parts[2] == "mRNA":
                tid = parse_attrs(parts[8]).get("ID")
                if tid:
                    ids.add(tid)
    return ids


# ------------------------------------------------------------------ FASTA (CDS/PEP)
def fasta_header_id(header: str) -> str:
    return header.split()[0]


def rewrite_cds_pep(src: Path, dst: Path, mrna_ids: set[str], is_pep: bool) -> dict:
    stats = {"n": 0, "mapped": 0, "unmapped": [], "dots": 0, "stars": 0}
    with open_text(src) as fi, open(dst, "w", encoding="utf-8") as fo:
        for line in fi:
            if line.startswith(">"):
                skip = False
                tid = fasta_header_id(line[1:].strip())
                # tolerate suffixes such as .cds / .pep
                base = re.sub(r"\.(cds|pep|protein)$", "", tid)
                if base in mrna_ids:
                    new = base
                    stats["mapped"] += 1
                elif tid in mrna_ids:
                    new = tid
                    stats["mapped"] += 1
                else:
                    # 被 tag 过滤掉的转录本（transposon-/plastid-related）
                    stats["unmapped"].append(tid)
                    skip = True
                if skip:
                    continue
                fo.write(">" + new + "\n")
                stats["n"] += 1
            else:
                if skip:
                    continue
                seq = line.rstrip("\n")
                if is_pep:
                    if "." in seq:
                        stats["dots"] += 1
                    if "*" in line:
                        stats["stars"] += 1
                    seq = seq.replace("*", "").replace(".", "")
                fo.write(seq + "\n")
    return stats


# ------------------------------------------------------------------ main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Normalize one PanHordeum genome into platform files.")
    ap.add_argument("--dir", required=True, help="raw genome directory (ENA fa + PGSB annotation)")
    ap.add_argument("--tag", required=True, help="platform MYTAG, e.g. Hordeum_chilense_GRA1000")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--gff", default="", help="override GFF path")
    ap.add_argument("--ena-fa", default="", help="override ENA FASTA path")
    ap.add_argument("--cds", default="", help="override CDS FASTA path")
    ap.add_argument("--pep", default="", help="override protein FASTA path")
    ap.add_argument("--keep-tag", default="protein_coding",
                    help="GFF gene/mRNA tag to keep (default: protein_coding; PGSB main also has TE/plastid models)")
    ap.add_argument("--keep-all", action="store_true", help="keep every gene model regardless of tag")
    args = ap.parse_args(argv)

    raw = Path(args.dir)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    ena_fa = Path(args.ena_fa) if args.ena_fa else find_one(raw, "*.ena.fa")
    gff = Path(args.gff) if args.gff else find_one(raw, "*.gff3")
    cds = Path(args.cds) if args.cds else find_one(raw, "*.cds.fa")
    pep = Path(args.pep) if args.pep else find_one(raw, "*.aa.fa")

    mapping, order = build_seqid_map(ena_fa)
    fasta_ids = set(mapping.values())
    report = [f"tag: {args.tag}", f"ena_fa: {ena_fa.name} ({len(mapping)} records)",
              f"gff: {gff.name}", f"cds: {cds.name}", f"pep: {pep.name}"]

    # FASTA
    fa_out = out / f"{args.tag}.fa"
    n_fa = rewrite_fasta(ena_fa, fa_out, mapping)
    report.append(f"fasta: {n_fa} records -> {fa_out.name}")
    with open(out / "seqid_mapping.tsv", "w", encoding="utf-8") as fh:
        fh.write("#ena_accession\tplatform_seqid\n")
        for acc, new in order:
            fh.write(f"{acc}\t{new}\n")

    # GFF（main 集合过滤：只保留 tag=protein_coding 的 gene/mRNA 及其子行）
    gff_out = out / f"{args.tag}.gff3"
    smap = gff_seqid_map(mapping)
    if args.keep_all:
        keep_genes, keep_mrnas = None, None
        tag_counts = {}
    else:
        keep_genes, keep_mrnas, tag_counts = collect_keep_ids(gff, args.keep_tag)
        report.append(f"keep tag={args.keep_tag}: genes={len(keep_genes)} mRNAs={len(keep_mrnas)} "
                      f"| tags={tag_counts}")
    gstats = rewrite_gff(gff, gff_out, smap, keep_genes, keep_mrnas)
    report.append(f"gff: rows={gstats['rows']} genes={gstats['gene']} mRNA={gstats['mrna']} "
                  f"mapped={gstats['mapped']} dropped={gstats['dropped']} "
                  f"missing_seqids={len(gstats['missing_seqids'])}")
    report.append(f"gff types: {gstats['types']}")
    if gstats["missing_seqids"]:
        report.append("gff missing seqids: " + ",".join(sorted(gstats["missing_seqids"])[:10]))
    if gstats["bad_mrna"]:
        report.append(f"[ERROR] {len(gstats['bad_mrna'])} mRNA IDs without .digit suffix; "
                      f"examples: {gstats['bad_mrna'][:3]}")

    mrna_ids = gff_mrna_ids(gff_out)
    report.append(f"mRNA ids: {len(mrna_ids)}")

    cds_out = out / f"{args.tag}.cds"
    pep_out = out / f"{args.tag}.pep"
    cstats = rewrite_cds_pep(cds, cds_out, mrna_ids, is_pep=False)
    pstats = rewrite_cds_pep(pep, pep_out, mrna_ids, is_pep=True)
    report.append(f"cds: {cstats['n']} seqs, mapped={cstats['mapped']}, unmapped={len(cstats['unmapped'])}")
    report.append(f"pep: {pstats['n']} seqs, mapped={pstats['mapped']}, unmapped={len(pstats['unmapped'])}, "
                  f"dotted-seq={pstats['dots']}, star-lines={pstats['stars']}")
    if cstats["unmapped"]:
        report.append("cds unmapped examples: " + ",".join(cstats["unmapped"][:3]))
    if pstats["unmapped"]:
        report.append("pep unmapped examples: " + ",".join(pstats["unmapped"][:3]))

    # gzip FASTA? platform pipeline reads plain; keep plain for direct use
    (out / "normalize_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))
    if gstats["bad_mrna"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
