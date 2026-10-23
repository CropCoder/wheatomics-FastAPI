#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JBrowse 卡片维护工具：每行严格 3 个卡片位（不足用空白卡补齐）。

规则（2026-10-23 用户确认）：
  * 一行（card-group）必须有 3 个卡片位；
  * 真实卡片不足 3 个时，用空白占位卡补齐，不能留 1-2 张的行；
  * 超过 3 张时，多出的卡片移到下一行；
  * 没有任何真实卡片的行（只有空位）直接删除。

用法：
  python3 scripts/jbrowse_card_tool.py --check
  python3 scripts/jbrowse_card_tool.py --fix --apply
  python3 scripts/jbrowse_card_tool.py --move --data-name Zavitan \
      --into-row-of AABB_Wild_emmer_Zavitan --apply
  python3 scripts/jbrowse_card_tool.py --insert --data-name NEW --title "New genome" --doi 10.xxxx/yyy --apply

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
MAX_PER_ROW = 3
GROUP_RE = re.compile(r'<div class="card-group">')
CARD_RE = re.compile(r'<div class="card">\s*<div class="card-body">.*?</div>\s*</div>', re.S)
PLACEHOLDER = '''<div class="card">
          <div class="card-body">
            <h5 class="card-title"><a class="card-title" href="/jbrowse-1.12.3-release/?data= "><i> </i></a></h5>
            <p class="card-text" style="font-size:90%;"><a style="color: grey;"  href="" target="_blank">  </a></p>
          </div>
        </div>'''


def groups(s: str) -> list[dict]:
    starts = [m.start() for m in GROUP_RE.finditer(s)]
    out = []
    for i, st in enumerate(starts):
        nxt = starts[i + 1] if i + 1 < len(starts) else len(s)
        end = s.rfind("</div>", st, nxt)
        if end < 0:
            continue
        out.append({"start": st, "end": end + len("</div>"), "body": s[st:end + len("</div>")]})
    return out


def cards_in(seg: str) -> list[dict]:
    return [{"start": m.start(), "end": m.end(), "text": m.group(0)} for m in CARD_RE.finditer(seg)]


def card_data_name(card: str) -> str:
    m = re.search(r"\?data=([^\"']+)", card)
    return (m.group(1).strip() if m else "")


def is_blank(card: str) -> bool:
    return card_data_name(card) == ""


def make_card(data_name: str, title: str, doi: str, raw_title: bool = False) -> str:
    title_html = title if raw_title else html.escape(title)
    doi_html = (f'<a style="color: grey;"  href="https://doi.org/{html.escape(doi)}" target="_blank">doi:{html.escape(doi)}</a>'
                if doi else '<a style="color: grey;"  href="" target="_blank">doi:</a>')
    return f'''<div class="card">
          <div class="card-body">
            <h5 class="card-title"><a class="card-title" href="/jbrowse-1.12.3-release/?data={html.escape(data_name)}">{title_html}</a></h5>
            <p class="card-text" style="font-size:90%;">{doi_html}</p>
          </div>
        </div>'''


def _group_replacement(g: dict, keep: list[dict], extras: list[dict]) -> tuple[str, int]:
    """把 group 重建为 keep+补齐空位，extra 另起新行；返回 (replacement, 被移动的 extra 数)。"""
    body = g["body"]
    cs = cards_in(body)
    prefix = body[:cs[0]["start"]] if cs else body[: len('<div class="card-group">')]
    suffix = body[cs[-1]["end"]:] if cs else "</div>"
    total = keep + [{"text": PLACEHOLDER} for _ in range(max(0, MAX_PER_ROW - len(keep)))]
    kept_text = "\n        ".join(c["text"] for c in total)
    new_groups = ""
    moved = 0
    if extras:
        for j in range(0, len(extras), MAX_PER_ROW):
            chunk = extras[j:j + MAX_PER_ROW]
            moved += len(chunk)
            pad = [{"text": PLACEHOLDER} for _ in range(MAX_PER_ROW - len(chunk))]
            cards = chunk + pad
            new_groups += ('\n      <div class="card-group">\n        ' +
                           "\n        ".join(c["text"] for c in cards) + '\n      </div>')
    return prefix + kept_text + suffix + new_groups, moved


def fix_layout(s: str) -> tuple[str, list[str]]:
    notes = []
    gs = groups(s)
    for g in reversed(gs):
        cs = cards_in(g["body"])
        real = [c for c in cs if not is_blank(c["text"])]
        if not real:
            s = s[:g["start"]] + s[g["end"]:]
            notes.append(f"removed empty row at group starting {g['start']}")
            continue
        keep, extras = real[:MAX_PER_ROW], real[MAX_PER_ROW:]
        if len(cs) != MAX_PER_ROW or len(real) != MAX_PER_ROW:
            repl, moved = _group_replacement(g, keep, extras)
            s = s[:g["start"]] + repl + s[g["end"]:]
            if moved:
                notes.append(f"moved {moved} extra card(s) to new row")
            if len(real) < MAX_PER_ROW:
                notes.append(f"padded {MAX_PER_ROW - len(real)} placeholder card(s)")
    return s, notes


def find_card_group(s: str, data_name: str):
    for gi, g in enumerate(groups(s)):
        for c in cards_in(g["body"]):
            if card_data_name(c["text"]) == data_name:
                return gi, g, c
    return None, None, None


def move_card(s: str, data_name: str, into_row_of: str) -> tuple[str, str]:
    gi, g, c = find_card_group(s, data_name)
    if g is None:
        return s, f"[ERR] 未找到卡片: {data_name}"
    card_text = c["text"]
    # 从原行移除
    s = s[:g["start"] + c["start"]] + s[g["start"] + c["end"]:]
    # 目标行：优先替换空位，否则追加
    gs = groups(s)
    target = None
    for tg in gs:
        if any(card_data_name(x["text"]) == into_row_of for x in cards_in(tg["body"])):
            target = tg
            break
    if target is None:
        return s, f"[ERR] 未找到目标行（含 {into_row_of}）"
    tcs = cards_in(target["body"])
    blank = next((x for x in tcs if is_blank(x["text"])), None)
    if blank:
        pos = target["start"] + blank["start"]
        s = s[:pos] + card_text + s[pos + len(blank["text"]):]
    else:
        pos = target["start"] + tcs[-1]["end"]
        s = s[:pos] + "\n        " + card_text + s[pos:]
    return s, f"moved {data_name} into row of {into_row_of}"


def insert_card(s: str, data_name: str, title: str, doi: str, after: str = "", raw_title: bool = False) -> tuple[str, str]:
    card = make_card(data_name, title, doi, raw_title)
    # 已存在则更新标题
    gi, g, c = find_card_group(s, data_name)
    if g is not None:
        card_text = c["text"]
        new = re.sub(r'(<h5 class="card-title"><a class="card-title" href="[^"]*">).*?(</a></h5>)',
                     lambda m: m.group(1) + (title if raw_title else html.escape(title)) + m.group(2),
                     card_text, count=1, flags=re.S)
        s = s[:g["start"] + c["start"]] + new + s[g["start"] + c["end"]:]
        return s, f"updated existing card {data_name}"

    gs = groups(s)
    target = None
    if after:
        for tg in gs:
            if any(card_data_name(x["text"]) == after for x in cards_in(tg["body"])):
                target = tg
                break
        if target is None:
            return s, f"[ERR] --after 卡片未找到: {after}"
    else:
        target = gs[-1] if gs else None
    if target is None:
        return s, "[ERR] 未找到 card-group"

    tcs = cards_in(target["body"])
    blank = next((x for x in tcs if is_blank(x["text"])), None)
    tcs_real = [x for x in tcs if not is_blank(x["text"])]
    if blank:
        pos = target["start"] + blank["start"]
        s = s[:pos] + card + s[pos + len(blank["text"]):]
        return s, f"inserted {data_name} into existing row (replaced placeholder)"
    if len(tcs_real) < MAX_PER_ROW:
        pos = target["start"] + tcs[-1]["end"]
        s = s[:pos] + "\n        " + card + s[pos:]
        return s, f"inserted {data_name} into existing row"
    # 目标行已满 → 另起一行，带 2 个占位卡
    pos = target["end"]
    new_group = ('\n      <div class="card-group">\n        ' + card + '\n        ' +
                 "\n        ".join([PLACEHOLDER, PLACEHOLDER]) + '\n      </div>')
    s = s[:pos] + new_group + s[pos:]
    return s, f"inserted {data_name} into a new row"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--html", default=HTML_PATH)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--move", action="store_true")
    ap.add_argument("--insert", action="store_true")
    ap.add_argument("--data-name")
    ap.add_argument("--title")
    ap.add_argument("--doi", default="")
    ap.add_argument("--after", default="")
    ap.add_argument("--into-row-of", default="")
    ap.add_argument("--raw-title", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    path = pathlib.Path(args.html)
    s = path.read_text(encoding="utf-8", errors="replace")

    if args.check:
        bad = []
        for i, g in enumerate(groups(s)):
            cs = cards_in(g["body"])
            if len(cs) != MAX_PER_ROW:
                bad.append((i, len(cs), [card_data_name(c["text"]) or "<blank>" for c in cs]))
        if not bad:
            print(f"[OK] {len(groups(s))} rows, 每行恰好 {MAX_PER_ROW} 个卡片位")
            return 0
        print(f"[WARN] {len(bad)} 行不是恰好 {MAX_PER_ROW} 个卡片位：")
        for b in bad:
            print(f"  row {b[0]}: {b[1]} cards -> {b[2]}")
        return 1

    if args.fix:
        new, notes = fix_layout(s)
        print("\n".join(notes) if notes else "[OK] 无需调整")
        if not args.apply:
            print("[DRY-RUN] 未写入；加 --apply 生效")
            return 0
        shutil.copy2(path, path.with_name(path.name + ".bak-" + time.strftime("%Y%m%d_%H%M%S")))
        path.write_text(new, encoding="utf-8")
        print(f"[OK] 已写入；行数：{len(groups(new))}")
        return 0

    if args.move:
        if not args.data_name or not args.into_row_of:
            print("[ERR] --move 需要 --data-name 和 --into-row-of", file=sys.stderr)
            return 2
        new, note = move_card(s, args.data_name, args.into_row_of)
        print(note)
        if note.startswith("[ERR]"):
            return 1
        new, fixes = fix_layout(new)
        print("\n".join(fixes) if fixes else "[OK] 布局已满足 3 卡/行")
        if not args.apply:
            print("[DRY-RUN] 未写入；加 --apply 生效")
            return 0
        shutil.copy2(path, path.with_name(path.name + ".bak-" + time.strftime("%Y%m%d_%H%M%S")))
        path.write_text(new, encoding="utf-8")
        print(f"[OK] 已写入；行数：{len(groups(new))}")
        return 0

    if args.insert:
        if not args.data_name or not args.title:
            print("[ERR] --insert 需要 --data-name 和 --title", file=sys.stderr)
            return 2
        new, note = insert_card(s, args.data_name, args.title, args.doi, args.after, args.raw_title)
        print(note)
        if note.startswith("[ERR]"):
            return 1
        new, fixes = fix_layout(new)
        print("\n".join(fixes) if fixes else "[OK] 布局已满足 3 卡/行")
        if not args.apply:
            print("[DRY-RUN] 未写入；加 --apply 生效")
            return 0
        shutil.copy2(path, path.with_name(path.name + ".bak-" + time.strftime("%Y%m%d_%H%M%S")))
        path.write_text(new, encoding="utf-8")
        print(f"[OK] 已写入；行数：{len(groups(new))}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
