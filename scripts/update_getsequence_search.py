#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""维护 /var/www/html/doc/getsequence_search.txt（getsequence 页面示例）。

规则（用户 2026-10-23 定）：
- 按基因组组成（第一列前缀，如 AABBDD / AABB / DD / HH）分块排序；
- 新增行插入到同组成块的最后一行之后；
- 组成未知（或文件里还没有该组成块）时，直接追加到文件末尾；
- 同名行已存在则原地更新 region/gene 两列；写入前自动备份。

用法：
  update_getsequence_search.py --doc /var/www/html/doc/getsequence_search.txt \
      --name AABBDD_NewGenome --region Chr1A_NewGenome:200-500 \
      --gene NewGenome1A000100.1 [--composition AABBDD] [--dry-run]
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import sys
import time

HEADER = "Getsequence Name\tGetsequence Search example\tGene example\tLibrary"


def composition_of(name: str) -> str:
    return name.split("_", 1)[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--doc", required=True, help="getsequence_search.txt 路径")
    ap.add_argument("--name", required=True, help="第一列：genome / 数据集名")
    ap.add_argument("--region", required=True, help="第二列：区间示例，如 Chr1A_xxx:200-500")
    ap.add_argument("--gene", required=True, help="第三列：基因示例 ID")
    ap.add_argument("--composition", default="", help="基因组组成前缀（如 AABBDD）；省略/未知时排到最后")
    ap.add_argument("--library", default="", help="第 4 列：all_genomes / all_other_genomes")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    for label, value in (("name", args.name), ("region", args.region), ("gene", args.gene)):
        if not value or any(ch in value for ch in "\t\r\n"):
            print(f"[ERROR] --{label} 不能为空或含制表符/换行", file=sys.stderr)
            return 2

    doc = pathlib.Path(args.doc)
    if not doc.is_file():
        print(f"[ERROR] 文件不存在: {doc}", file=sys.stderr)
        return 2

    raw = doc.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    if not lines:
        lines = [HEADER]
    if not lines[0].startswith("Getsequence Name"):
        lines.insert(0, HEADER)
    elif len(lines[0].split("\t")) == 3:
        lines[0] = lines[0] + "\tLibrary"
    for _i in range(1, len(lines)):
        if lines[_i].strip() and len(lines[_i].split("\t")) == 3:
            lines[_i] = lines[_i] + "\t?"

    new_row = f"{args.name}\t{args.region}\t{args.gene}\t{args.library or '?'}"
    comp = (args.composition or "").strip()
    if comp and not comp.startswith(composition_of(args.name)):
        # 允许显式指定（如 Th.ponticum_public 的组成前缀），但记录提示
        print(f"[INFO] composition={comp}（第一列前缀为 {composition_of(args.name)}）")

    # 找到已有同名行
    existing_idx = None
    for i in range(1, len(lines)):
        fields = lines[i].split("\t")
        if fields and fields[0].strip() == args.name:
            existing_idx = i
            break

    if existing_idx is not None:
        action = f"update line {existing_idx + 1}"
        target_idx = existing_idx
    elif comp:
        last_same = None
        for i in range(1, len(lines)):
            fields = lines[i].split("\t")
            if fields and fields[0].strip() and composition_of(fields[0].strip()) == comp:
                last_same = i
        if last_same is not None:
            action = f"insert after line {last_same + 1} (composition={comp})"
            target_idx = last_same + 1
        else:
            action = f"append at end (composition={comp} not found in doc)"
            target_idx = len(lines)
    else:
        action = "append at end (composition unknown)"
        target_idx = len(lines)

    if args.dry_run:
        print(f"[DRY-RUN] {action}: {new_row}")
        return 0

    if existing_idx is not None:
        lines[target_idx] = new_row
    else:
        # 避免在文件末尾的空行之后追加
        while target_idx > 0 and lines[target_idx - 1].strip() == "":
            target_idx -= 1
        lines.insert(target_idx, new_row)

    backup = doc.with_name(doc.name + ".bak-" + time.strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(doc, backup)
    doc.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] {action}")
    print(f"[OK] backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
