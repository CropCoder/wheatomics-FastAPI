#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KnownGene 增量新增基因：**先查库防重，再只插入真正的新基因**。

为什么需要这个脚本
------------------
现有 `known_gene_push.py` 是 bulk **upsert**，匹配键只有 `(gene_id, gene_name)`。
如果新增基因出现下面任一情况，upsert 会把它当“新行”插入，造成库内重复：
  1. 同一基因换了 gene_name（别名、拷贝命名、`TaSPL6B` vs `TaSPL6-B`）；
  2. 同一基因用了 v1/v2 旧 ID（库内已是 v2.1/v3）；
  3. 同一参考位点已被另一个基因名占用（如 PmL270 与 PmNCA6 共用
     TraesCS7A03G1212700）；
  4. 同一基因在库里已存在，只是参考基因组 ID/坐标写法不同。

本脚本在写库前拉取线上 `/api/genes/known/all` 全量快照，做**多键查重**：
  - EXACT_KEY      (gene_id, gene_name) 已在库 → 跳过（绝不重复插入）
  - CONFLICT_ID    库内同 gene_id 但 gene_name 不同 → 人工确认（改名/拷贝）
  - CONFLICT_NAME  库内同 gene_name 但 gene_id 不同 → 人工确认
  - CONFLICT_REF   库内同 reference_genome_id（不同基因名）→ 位点已被占用
  - CONFLICT_LOCUS 同 genome_ref/染色体且区间重叠 → 位点重叠
  - DOI_NOTE       仅同一 DOI（同文献多基因，允许，但提示）
  - INVALID        必填缺失/占位符（Not reported 等）→ 拒绝
  - NEW_SAFE       以上都不命中 → 可安全新增

写入时使用 `POST /api/genes/known/write/bulk` 的 **mode=insert_only**：
服务端对任意已存在的 `(gene_id, gene_name)` 会整批拒绝（第二道保险）。
写前会**重新拉一次快照并复核**，避免两次检查之间被别的会话写入。

用法
----
    # 1) 默认 dry-run：只查重、出报告，不写库
    python3 scripts/known_gene_incremental.py \
        --jsonl /tmp/kg_incremental/known_genes_v2062.jsonl \
        --report-dir /tmp/kg_incremental/report

    # 2) 确认报告后提交（只写 NEW_SAFE 行）
    python3 scripts/known_gene_incremental.py \
        --jsonl /tmp/kg_incremental/known_genes_v2062.jsonl \
        --report-dir /tmp/kg_incremental/report --commit \
        --key-file ~/.config/lab-server/wheatomics_known_gene_write_key.txt

    # 可选：--admin-key-file 用于提交后查询 /write/changes 审计
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

BASE_DEFAULT = "https://wheatomics.sdau.edu.cn"
KEY_DEFAULT = os.path.expanduser("~/.config/lab-server/wheatomics_known_gene_write_key.txt")
ADMIN_KEY_DEFAULT = os.path.expanduser("~/.config/lab-server/wheatomics_known_gene_admin_key.txt")
BATCH_MAX_ROWS = 500
BATCH_MAX_BYTES = 1_800_000
REQUIRED = ("gene_id", "gene_name", "reference_genome_id", "gene_species",
            "chrom_pos", "gene_phenotype", "functional_category",
            "research_strategy", "key_result")
DROP_FIELDS = {"_row", "_tier", "_warn", "clone_id"}

CHROM_RE = re.compile(
    r"^(?P<ref>\S+)\s+chr(?P<chrom>[0-9]+[A-Za-z]{0,2}):(?P<start>[\d.]+)-(?P<end>[\d.]+)Mb$"
)


# ---------------------------------------------------------------------------
# 基础 HTTP
# ---------------------------------------------------------------------------
def http_json(url: str, *, method: str = "GET", body: Any = None,
              headers: dict[str, str] | None = None, timeout: int = 120) -> Any:
    """经 curl 走 HTTP（生产网关对 Python urllib 连接不友好，会直接断连）。"""
    import subprocess
    import tempfile
    cmd = ["curl", "-sS", "-m", str(timeout), "-A", "KnownGeneIncremental/1.0"]
    if method != "GET":
        cmd += ["-X", method]
    if headers:
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
    tmp = None
    if body is not None:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(body, tmp, ensure_ascii=False)
        tmp.close()
        cmd += ["--data-binary", f"@{tmp.name}"]
    cmd.append(url)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    finally:
        if tmp is not None:
            os.unlink(tmp.name)
    if proc.returncode != 0:
        raise RuntimeError(f"curl failed ({proc.returncode}) {url}: {proc.stderr[:300]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"非 JSON 响应 {url}: {proc.stdout[:200]!r}") from exc


def fetch_db_snapshot(base_url: str, page_size: int = 500) -> list[dict[str, Any]]:
    """拉取线上全量快照。

    注意：服务端对超大 limit（如 100000）会直接断开连接，因此用 500/页分页；
    当前 1400+ 行约 3 页，每页请求 ~0.5 MB。
    """
    recs: list[dict[str, Any]] = []
    offset = 0
    total = None
    while True:
        payload = http_json(
            f"{base_url}/api/genes/known/all?limit={page_size}&offset={offset}")
        data = payload.get("data") or {}
        total = int(data.get("total") or 0)
        page = data.get("records") or []
        recs.extend(page)
        if not page or len(recs) >= total:
            break
        offset += len(page)
    if not recs:
        raise RuntimeError("无法从 /api/genes/known/all 取得记录")
    if total and len(recs) != total:
        raise RuntimeError(f"分页拉取不完整：{len(recs)}/{total}")
    return recs


def read_key(path: str | None, env_name: str) -> str:
    key = os.environ.get(env_name, "").strip()
    if key:
        return key
    if path and os.path.exists(path):
        return Path(path).read_text(encoding="utf-8").strip()
    raise SystemExit(f"缺少 API key：请设 {env_name} 或 --key-file")


# ---------------------------------------------------------------------------
# 查重索引
# ---------------------------------------------------------------------------
def parse_locus(chrom_pos: str) -> tuple[str, str, float, float] | None:
    if not isinstance(chrom_pos, str):
        return None
    s = " ".join(chrom_pos.split())
    m = CHROM_RE.match(s)
    if not m:
        return None
    return (m.group("ref"), m.group("chrom").upper(),
            float(m.group("start")), float(m.group("end")))


def build_index(records: list[dict[str, Any]]) -> dict[str, Any]:
    idx: dict[str, Any] = {"by_key": {}, "by_id": {}, "by_name": {},
                           "by_ref": {}, "by_doi": {}, "loci": []}
    for r in records:
        gid = str(r.get("gene_id") or "").strip()
        gnm = str(r.get("gene_name") or "").strip()
        rid = str(r.get("reference_genome_id") or "").strip()
        idx["by_key"].setdefault((gid, gnm), r)
        if gid:
            idx["by_id"].setdefault(gid, []).append(r)
        if gnm:
            idx["by_name"].setdefault(gnm, []).append(r)
        if rid:
            idx["by_ref"].setdefault(rid, []).append(r)
        for d in r.get("dois") or r.get("paper_doi") or []:
            d = str(d).strip().lower()
            if d:
                idx["by_doi"].setdefault(d, []).append(r)
        loc = parse_locus(str(r.get("chrom_pos") or ""))
        if loc:
            idx["loci"].append((loc, r))
    return idx


def locus_overlap(a: tuple[str, str, float, float],
                  b: tuple[str, str, float, float], tol: float = 0.002) -> bool:
    if a[0] != b[0] or a[1] != b[1]:
        return False
    return a[2] <= b[3] + tol and b[2] <= a[3] + tol


def is_placeholder(value: str) -> bool:
    return value.strip().lower().startswith(("not reported", "not determined", "none", "null"))


def classify(row: dict[str, Any], idx: dict[str, Any]) -> dict[str, Any]:
    """返回 {status, matched, reason}。"""
    gid = str(row.get("gene_id") or "").strip()
    gnm = str(row.get("gene_name") or "").strip()
    rid = str(row.get("reference_genome_id") or "").strip()
    chrom = str(row.get("chrom_pos") or "").strip()
    doi = str(row.get("paper_doi") or row.get("doi") or "").strip().lower()

    missing = [f for f in REQUIRED if not str(row.get(f) or "").strip()]
    if missing:
        return {"status": "INVALID", "matched": None,
                "reason": "缺必填字段: " + ",".join(missing)}
    if is_placeholder(gid) or is_placeholder(rid):
        return {"status": "INVALID", "matched": None,
                "reason": "gene_id/reference_genome_id 仍为占位符（需先补真实编号）"}
    if is_placeholder(chrom):
        return {"status": "INVALID", "matched": None, "reason": "chrom_pos 为占位符"}

    key = (gid, gnm)
    if key in idx["by_key"]:
        r = idx["by_key"][key]
        return {"status": "EXACT_KEY", "matched": r,
                "reason": f"库内已有同一 (gene_id, gene_name)，clone_id={r.get('clone_id')}"}

    if gid in idx["by_id"]:
        r = idx["by_id"][gid][0]
        return {"status": "CONFLICT_ID", "matched": r,
                "reason": f"库内同 gene_id 但 gene_name={r.get('gene_name')!r}，clone_id={r.get('clone_id')}"}

    if rid and rid in idx["by_ref"]:
        r = idx["by_ref"][rid][0]
        return {"status": "CONFLICT_REF", "matched": r,
                "reason": f"库内同 reference_genome_id（{r.get('gene_name')!r}），clone_id={r.get('clone_id')}"}

    loc = parse_locus(chrom)
    if loc:
        for other_loc, r in idx["loci"]:
            if locus_overlap(loc, other_loc):
                return {"status": "CONFLICT_LOCUS", "matched": r,
                        "reason": f"位点与库内 {r.get('gene_name')!r}（clone_id={r.get('clone_id')}）重叠"}

    if gnm in idx["by_name"]:
        r = idx["by_name"][gnm][0]
        return {"status": "CONFLICT_NAME", "matched": r,
                "reason": f"库内同 gene_name 但 gene_id={r.get('gene_id')!r}，clone_id={r.get('clone_id')}"}

    if doi and doi in idx["by_doi"]:
        r = idx["by_doi"][doi][0]
        return {"status": "DOI_NOTE", "matched": r,
                "reason": f"同 DOI 已有 {r.get('gene_name')!r}（clone_id={r.get('clone_id')}），同文献多基因属正常"}

    return {"status": "NEW_SAFE", "matched": None, "reason": "多键查重均未命中，可新增"}


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------
def write_report(report_dir: Path, rows: list[dict[str, Any]],
                 results: list[dict[str, Any]], db_total: int) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tsv = report_dir / f"preflight_{ts}.tsv"
    with tsv.open("w", encoding="utf-8", newline="") as fh:
        fh.write("jsonl_row\tgene_id\tgene_name\tstatus\tmatched_clone_id\tmatched_gene\treason\n")
        for row, res in zip(rows, results):
            m = res.get("matched") or {}
            fh.write("\t".join(str(x) for x in [
                row.get("_row", ""), row.get("gene_id", ""), row.get("gene_name", ""),
                res["status"], m.get("clone_id", ""), m.get("gene_name", ""),
                res["reason"].replace("\t", " "),
            ]) + "\n")
    md = report_dir / f"preflight_{ts}.md"
    counts: dict[str, int] = {}
    for res in results:
        counts[res["status"]] = counts.get(res["status"], 0) + 1
    lines = [
        "# KnownGene 增量新增：库内查重报告",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 线上库当前行数：{db_total}",
        f"- 待处理行数：{len(rows)}",
        "",
        "## 状态汇总",
        "",
        "| 状态 | 行数 | 含义 |",
        "|---|---|---|",
    ]
    meaning = {
        "EXACT_KEY": "已存在（同 gene_id+gene_name）→ 跳过",
        "CONFLICT_ID": "同 gene_id 异名 → 人工确认",
        "CONFLICT_NAME": "同名异 ID → 人工确认",
        "CONFLICT_REF": "同参考位点被占用 → 人工确认",
        "CONFLICT_LOCUS": "坐标区间重叠 → 人工确认",
        "DOI_NOTE": "同文献多基因 → 允许，提示",
        "INVALID": "必填/编号占位符 → 拒绝",
        "NEW_SAFE": "可安全新增",
    }
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {k} | {v} | {meaning.get(k, '')} |")
    lines += ["", "## 需要处理的行", ""]
    for row, res in zip(rows, results):
        if res["status"] in ("NEW_SAFE", "EXACT_KEY"):
            continue
        m = res.get("matched") or {}
        lines.append(f"- `{row.get('gene_name')}` ({row.get('gene_id')}) — **{res['status']}**：{res['reason']}")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md


# ---------------------------------------------------------------------------
# 写库
# ---------------------------------------------------------------------------
def to_api_row(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in row.items() if k not in DROP_FIELDS}
    for k in ("paper_title", "paper_doi", "publication_years"):
        v = out.get(k)
        if isinstance(v, str) and "###" in v:
            out[k] = [x.strip() for x in v.split("###")]
    if isinstance(out.get("publication_year"), str):
        try:
            out["publication_year"] = int(out["publication_year"])
        except ValueError:
            pass
    return out


def push_new_safe(base_url: str, key: str, rows: list[dict[str, Any]],
                  dry_run: bool) -> dict[str, Any]:
    chunks: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    cur_bytes = 0
    for r in rows:
        b = len(json.dumps(to_api_row(r), ensure_ascii=False).encode("utf-8"))
        if cur and (len(cur) >= BATCH_MAX_ROWS or cur_bytes + b > BATCH_MAX_BYTES):
            chunks.append(cur); cur = []; cur_bytes = 0
        cur.append(r); cur_bytes += b
    if cur:
        chunks.append(cur)
    summary = {"created": 0, "updated": 0, "errors": 0, "batches": [],
               "created_clone_ids": []}
    for i, chunk in enumerate(chunks, 1):
        payload = {"rows": [to_api_row(r) for r in chunk],
                   "mode": "insert_only", "dry_run": dry_run}
        resp = http_json(f"{base_url}/api/genes/known/write/bulk",
                         method="POST", body=payload,
                         headers={"Authorization": f"Bearer {key}"})
        data = resp.get("data") or {}
        summary["created"] += int(data.get("created") or 0)
        summary["updated"] += int(data.get("updated") or 0)
        summary["errors"] += int(data.get("errors") or 0)
        for r in data.get("results") or []:
            if r.get("clone_id"):
                summary["created_clone_ids"].append(r["clone_id"])
        summary["batches"].append({"batch": i, "rows": len(chunk), "data": data})
        print(f"batch {i}/{len(chunks)}: created={data.get('created')} "
              f"updated={data.get('updated')} errors={data.get('errors')}")
        if data.get("errors"):
            print("  ✗ 服务端拒绝本批，停止后续写入（已成功批次不会回滚）")
            break
        if dry_run:
            # dry-run 不会创建，不需要继续打印大量结果
            pass
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jsonl", required=True, help="extract.py 生成的 JSONL（每行一个 23 字段 gene）")
    ap.add_argument("--base-url", default=BASE_DEFAULT)
    ap.add_argument("--key-file", default=KEY_DEFAULT)
    ap.add_argument("--admin-key-file", default=ADMIN_KEY_DEFAULT)
    ap.add_argument("--report-dir", default="/tmp/kg_incremental_report")
    ap.add_argument("--commit", action="store_true", help="真正写库（默认 dry-run）")
    ap.add_argument("--allow-status", default="NEW_SAFE",
                    help="允许写入的状态，逗号分隔（默认只写 NEW_SAFE）")
    ap.add_argument("--allow-locus-shared", action="store_true",
                    help="把 CONFLICT_LOCUS 视为可写（用于 D7 允许的“同一位点不同基因/等位”，需人工确认）")
    args = ap.parse_args()

    rows = [json.loads(line) for line in Path(args.jsonl).read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"待处理 JSONL 行数：{len(rows)}")
    print(f"模式：{'COMMIT（会写库）' if args.commit else 'DRY-RUN（不写库）'}")

    snapshot = fetch_db_snapshot(args.base_url)
    print(f"线上库当前行数：{len(snapshot)}")
    idx = build_index(snapshot)
    results = [classify(r, idx) for r in rows]
    counts: dict[str, int] = {}
    for res in results:
        counts[res["status"]] = counts.get(res["status"], 0) + 1
    print("查重状态：", counts)

    md = write_report(Path(args.report_dir), rows, results, len(snapshot))
    print("报告：", md)

    allowed = {s.strip() for s in args.allow_status.split(",") if s.strip()}
    if args.allow_locus_shared:
        allowed.add("CONFLICT_LOCUS")
        print("注意：--allow-locus-shared 已开启，CONFLICT_LOCUS 行将进入待写列表（请确认是同位点不同基因/等位）")
    to_write = [r for r, res in zip(rows, results) if res["status"] in allowed]
    print(f"计划写入（{','.join(sorted(allowed))}）：{len(to_write)} 行")
    for r in to_write:
        print("  +", r.get("gene_id"), "|", r.get("gene_name"))

    if not args.commit:
        print("dry-run 结束；确认报告后加 --commit 写库")
        return 0

    if not to_write:
        print("没有需要写入的行（数据库中已存在或全部为冲突/无效）")
        return 0

    key = read_key(args.key_file, "KNOWN_GENE_API_KEY")

    # 第二道保险：写前重拉快照并复核
    print("写前复核线上库…")
    snapshot2 = fetch_db_snapshot(args.base_url)
    idx2 = build_index(snapshot2)
    still: list[dict[str, Any]] = []
    for r, res in zip(rows, results):
        if res["status"] not in allowed:
            continue
        res2 = classify(r, idx2)
        if res2["status"] in allowed:
            still.append(r)
        else:
            print(f"  ✗ 写前复核发现状态变为 {res2['status']}：{r.get('gene_name')}；已从本批剔除")
    if not still:
        print("写前复核后无可写行，退出")
        return 0

    summary = push_new_safe(args.base_url, key, still, dry_run=False)
    print(json.dumps({k: v for k, v in summary.items() if k != "batches"},
                     ensure_ascii=False, indent=2))

    # 写后验证
    print("写后验证…")
    after = fetch_db_snapshot(args.base_url)
    print(f"线上库行数：{len(snapshot)} → {len(after)}（预期 +{len(still)}）")
    if summary["created_clone_ids"]:
        print("新 clone_id：", summary["created_clone_ids"])
        for cid in summary["created_clone_ids"]:
            try:
                d = http_json(f"{args.base_url}/api/genes/known/{cid}")
                rec = d.get("data") or {}
                print(f"  clone_id={cid}: {rec.get('gene_name')} / {rec.get('gene_id')}")
            except Exception as exc:  # noqa: BLE001
                print(f"  clone_id={cid}: 详情读取失败 {exc}")
    return 0 if summary["errors"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
