#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JBrowse 卡片维护工具：保持卡片行 3 个/行，支持检查、修复、插入。

用法：
  # 检查是否有一行超过 3 张卡片（退出码 1 表示有问题）
  python3 scripts/jbrowse_card_tool.py --check

  # 自动把超出的卡片移到下一行（自动备份）
  python3 scripts/jbrowse_card_tool.py --fix --apply

  # 插入新卡片：优先补到目标行（<3 张时），否则另起一行
  python3 scripts/jbrowse_card_tool.py --insert \
      --data-name AABB_Wild_emmer_Zavitan \
      --title "Zavitan (near-complete, 2026)" \
      --doi 10.1038/s41588-026-02808-3 --apply

  # 指定插到某张卡片所在组之后
  python3 scripts/jbrowse_card_tool.py --insert ... --after AABB_Wild_emmerV2

默认 dry-run；--apply 才写文件，写前自动备份 .bak-YYYYmmdd_HHMMSS。
"""
from __future__ import annotations

import argparse
import html
import pathlib
import re
import shutil
import sys
import time

HTML_PATH = "/var/www/html/jbrowse.html"
GROUP_RE = re.compile(r'<div class="card-group">')
CARD_RE = re.compile(r'<div class="card">\s*<div class="card-body">.*?</div>\s*</div>', re.S)
MAX_PER_ROW = 3


def groups(s: str):
    starts = [m.start() for m in GROUP_RE.finditer(s)]
    out = []
    for i, st in enumerate(starts):
        nxt = starts[i + 1] if i + 1 < len(starts) else len(s)
        end = s.rfind("</div>", st, nxt)
        if end < 0:
            continue
        out.append({"start": st, "end": end + len("</div>"), "body": s[st:end + len("</div>")]})
    return out


def cards_in(seg: str):
    return [{"start": m.start(), "end": m.end(), "text": m.group(0)} for m in CARD_RE.finditer(seg)]


def card_data_name(card: str) -> str:
    m = re.search(r"\?data=([^\"']+)", card)
    return (m.group(1).strip() if m else "")


def make_card(data_name: str, title: str, doi: str, raw_title: bool = False) -> str:
    title_html = title if raw_title else html.escape(title)
    doi_line = (f'<a style="color: grey;"  href="https://doi.org/{html.escape(doi)}" '
                f'target="_blank">doi:{html.escape(doi)}</a>') if doi else \
               '<a style="color: grey;"  href="" target="_blank">doi:</a>'
    return f'''<div class="card">
          <div class="card-body">
            <h5 class="card-title"><a class="card-title" href="/jbrowse-1.12.3-release/?data={html.escape(data_name)}">{title_html}</a></h5>
            <p class="card-text" style="font-size:90%;">{doi_line}</p>
          </div>
        </div>'''


def check(s: str) -> list[dict]:
    bad = []
    for i, g in enumerate(groups(s)):
        cs = cards_in(g["body"])
        if len(cs) > MAX_PER_ROW:
            bad.append({"index": i, "count": len(cs), "cards": [card_data_name(c["text"]) for c in cs]})
    return bad


def fix_overfull(s: str, apply: bool) -> tuple[str, list[str]]:
    notes = []
    gs = groups(s)
    # 从后往前处理，避免位置漂移
    for g in reversed(gs):
        cs = cards_in(g["body"])
        if len(cs) <= MAX_PER_ROW:
            continue
        extra = cs[MAX_PER_ROW:]
        keep_end = extra[0]["start"]
        tail_start = extra[-1]["end"]
        kept = g["body"][:keep_end] + g["body"][tail_start:]
        new_groups = []
        for j in range(0, len(extra), MAX_PER_ROW):
            chunk = extra[j:j + MAX_PER_ROW]
            body = "\n        ".join(c["text"] for c in chunk)
            new_groups.append(f'\n      <div class="card-group">\n        {body}\n      </div>')
        replacement = kept + "".join(new_groups)
        s = s[:g["start"]] + replacement + s[g["end"]:]
        notes.append(f"group {g['index']}: moved {len(extra)} card(s) to new row")
    return s, notes


def insert_card(s: str, data_name: str, title: str, doi: str, after: str = "", raw_title: bool = False):
    card = make_card(data_name, title, doi, raw_title)
    gs = groups(s)
    target = None
    if after:
        for g in gs:
            if any(card_data_name(c["text"]) == after for c in cards_in(g["body"])):
                target = g
                break
        if target is None:
            return s, f"[ERR] --after 卡片未找到: {after}"
    else:
        target = gs[-1] if gs else None

    # 已存在同名卡片 → 更新其 href 文本（幂等）
    for g in gs:
        for c in cards_in(g["body"]):
            if card_data_name(c["text"]) == data_name:
                new = re.sub(r'(<h5 class="card-title"><a class="card-title" href="[^"]*">).*?(</a></h5>)',
                             lambda m: m.group(1) + (title if raw_title else html.escape(title)) + m.group(2),
                             c["text"], count=1, flags=re.S)
                s = s[:g["start"] + c["start"]] + new + s[g["start"] + c["end"]:]
                return s, f"updated existing card {data_name}"

    if target is None:
        return s, "[ERR] 未找到 card-group，无法插入"
    cs = cards_in(target["body"])
    if len(cs) < MAX_PER_ROW:
        pos = target["start"] + cs[-1]["end"] if cs else target["start"] + len('<div class="card-group">')
        s = s[:pos] + "\n        " + card + s[pos:]
        return s, f"inserted {data_name} into existing row ({len(cs) + 1}/3)"
    # 另起一行，紧跟目标行之后
    pos = target["end"]
    new_group = f'\n      <div class="card-group">\n        {card}\n      </div>'
    s = s[:pos] + new_group + s[pos:]
    return s, f"inserted {data_name} into a new row after group"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--html", default=HTML_PATH)
    ap.add_argument("--check", action="store_true", help="只检查 >3 卡片/行")
    ap.add_argument("--fix", action="store_true", help="把超出的卡片移到下一行")
    ap.add_argument("--insert", action="store_true", help="插入一张卡片")
    ap.add_argument("--data-name", help="JBrowse 数据集名（?data=）")
    ap.add_argument("--title", help="卡片标题（默认按纯文本转义）")
    ap.add_argument("--doi", default="", help="可选 DOI")
    ap.add_argument("--after", default="", help="插到某张卡片所在行（默认最后一行）")
    ap.add_argument("--raw-title", action="store_true", help="标题按 HTML 处理")
    ap.add_argument("--apply", action="store_true", help="实际写入（默认 dry-run）")
    args = ap.parse_args()

    path = pathlib.Path(args.html)
    s = path.read_text(encoding="utf-8", errors="replace")

    if args.check:
        bad = check(s)
        if not bad:
            print(f"[OK] {len(groups(s))} rows, 每行 <= {MAX_PER_ROW} 张卡片")
            return 0
        print(f"[WARN] 发现 {len(bad)} 行超过 {MAX_PER_ROW} 张卡片：")
        for b in bad:
            print(f"  row {b['index']}: {b['count']} cards -> {b['cards']}")
        return 1

    if args.fix:
        new, notes = fix_overfull(s, args.apply)
        print("\n".join(notes) if notes else "[OK] 无超行")
        if not args.apply:
            print("[DRY-RUN] 未写入；加 --apply 生效")
            return 0
        shutil.copy2(path, path.with_name(path.name + ".bak-" + time.strftime("%Y%m%d_%H%M%S")))
        path.write_text(new, encoding="utf-8")
        print(f"[OK] 已修复，共 {len(notes)} 行；卡片行数：{len(groups(new))}")
        return 0

    if args.insert:
        if not args.data_name or not args.title:
            print("[ERR] --insert 需要 --data-name 和 --title", file=sys.stderr)
            return 2
        new, note = insert_card(s, args.data_name, args.title, args.doi, args.after, args.raw_title)
        print(note)
        if not args.apply:
            print("[DRY-RUN] 未写入；加 --apply 生效")
            return 0 if not note.startswith("[ERR]") else 1
        if note.startswith("[ERR]"):
            return 1
        bad = check(new)
        if bad:
            print("[ERR] 插入后仍有超行，已中止写入：", bad, file=sys.stderr)
            return 1
        shutil.copy2(path, path.with_name(path.name + ".bak-" + time.strftime("%Y%m%d_%H%M%S")))
        path.write_text(new, encoding="utf-8")
        print(f"[OK] 已写入，卡片行数：{len(groups(new))}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
