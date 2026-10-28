#!/usr/bin/env python3
"""把 KnownGene JSONL 通过写接口批量入库（Excel → extract.py → 本脚本）。

背景：KnownGene 数据维护流程是「改 Excel → extract.py 生成 JSONL → API 批量写入」。
本脚本就是最后一步：读 JSONL，映射成写接口的 gene payload，按 ≤500 行 / ≤1.8MB
分批调用 ``POST /api/genes/known/write/bulk``（mode=upsert），默认 dry-run 预演，
加 ``--commit`` 才真正写库。

用法::

    # 1) 先 dry-run（默认）：只校验，不写库；逐行 status/errors
    KNOWN_GENE_API_KEY=kgw_xxx python3 scripts/known_gene_push.py \\
        --jsonl scripts/known_genes_v2055/out/known_genes_v2056.jsonl \\
        --base-url https://wheatomics.sdau.edu.cn --limit 20 --dry-run

    # 2) 确认无误后真正写入（upsert：已存在的 (gene_id, gene_name) 更新，否则新增）
    KNOWN_GENE_API_KEY=kgw_xxx python3 scripts/known_gene_push.py \\
        --jsonl scripts/known_genes_v2055/out/known_genes_v2056.jsonl \\
        --base-url https://wheatomics.sdau.edu.cn --commit

    # key 也可以从 600 权限文件读取（优先级：环境变量 > --key-file）
    python3 scripts/known_gene_push.py \\
        --jsonl scripts/known_genes_v2055/out/known_genes_v2056.jsonl \\
        --key-file /home/fei/known_gene_api_key_20261028.txt --dry-run

生成 JSONL（已有脚本，只读 Excel）::

    python3 scripts/known_genes_v2055/extract.py \\
        --xlsx "/path/to/已知基因逐条提取清单_20261019-合集_修正版v2056_20261028.xlsx" \\
        --outdir scripts/known_genes_v2055/out

安全性：
- 默认 dry-run；只有显式 ``--commit`` 才发 dry_run=false；
- 每批 ≤500 行且请求体 ≤1.8MB（服务端硬上限 2MB）；
- 单批失败（422/409/413/401/403）立即中止：服务端保证"单批全有或全无"，但
  **之前已成功的批次不会回滚**（脚本会打印已写入行数，必要时用审计 +
  known_gene_admin.py 修正）；
- 429/5xx 自动重试（指数退避 + Retry-After），不打印/记录 raw key。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterator

API_PATH = "/api/genes/known/write/bulk"
DEFAULT_KEY_FILE = "/home/fei/known_gene_api_key_20261028.txt"
#: 服务端单请求体上限 2MB；留 10% 余量。
DEFAULT_MAX_BYTES = 1_800_000
#: JSONL 中仅存在于导入管线的辅助字段，不进 API。
DROP_FIELDS = frozenset({"_row", "_tier", "_warn", "clone_id"})
#: DB 里用 ### 连接的多值字段：转成 API 接受的 list 形式。
MULTI_FIELDS = ("paper_title", "paper_doi", "publication_years")


# ---------------------------------------------------------------------------
# JSONL → API payload
# ---------------------------------------------------------------------------
def split_join_field(value: object) -> list[str]:
    """把 JSONL 里的 ``###`` 多值字段拆成 list（保留位置空串，去掉尾部空串）。"""

    if isinstance(value, list):
        items = [str(item).strip() for item in value]
    else:
        items = [part.strip() for part in str(value or "").split("###")]
    while items and not items[-1]:
        items.pop()
    return items


def map_jsonl_row(raw: dict[str, Any]) -> dict[str, Any]:
    """JSONL 行 → 写接口 gene payload。

    映射规则：
    - 去掉 ``_row`` / ``_tier`` / ``_warn`` / ``clone_id``（导入管线内部字段）；
    - ``paper_title`` / ``paper_doi`` / ``publication_years``：``###`` 串 → list；
    - ``publication_year``：数字字符串 → int；
    - 其余字段 1:1 透传（``species_primary`` / ``chromosome`` 由服务端校验后采用，
      ``author`` / ``author_mail`` / ``submission_date`` 保留 JSONL 原值）；
    - 丢弃 None 值（API 中缺省即 None，减少请求体体积）。
    """

    payload: dict[str, Any] = {}
    for key, value in raw.items():
        if key in DROP_FIELDS or value is None:
            continue
        if key in MULTI_FIELDS:
            payload[key] = split_join_field(value)
            continue
        if key == "publication_year":
            text = str(value).strip()
            payload[key] = int(text) if text.isdigit() else value
            continue
        payload[key] = value
    return payload


def load_jsonl(path: str, limit: int | None) -> list[dict[str, Any]]:
    """读 JSONL（忽略空行）；``limit`` 只取前 N 行（便于小批量试跑）。"""

    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number} 不是合法 JSON: {exc}") from exc
            if not isinstance(raw, dict):
                raise ValueError(f"{path}:{line_number} 不是 JSON object")
            rows.append(map_jsonl_row(raw))
            if limit is not None and len(rows) >= limit:
                break
    return rows


def iter_batches(
    rows: list[dict[str, Any]],
    *,
    batch_size: int,
    max_bytes: int,
    mode: str,
    dry_run: bool,
) -> Iterator[list[dict[str, Any]]]:
    """按行数与请求体字节数双重上限切批（单行超限直接报错）。

    字节数按 ``json.dumps`` 的实际编码长度累加估算（含分隔符余量），避免对每个
    候选批次重复序列化整个 500 行的大 payload。
    """

    envelope = json.dumps(
        {"rows": [], "mode": mode, "dry_run": dry_run}, ensure_ascii=False
    ).encode("utf-8")
    # json.dumps 列表元素的默认分隔符是 ", "（2 字节）
    base_bytes = len(envelope) - 2  # "[]" 两个字符不计入
    row_sizes = [len(json.dumps(row, ensure_ascii=False).encode("utf-8")) for row in rows]

    batch: list[dict[str, Any]] = []
    current_bytes = base_bytes
    for row, row_size in zip(rows, row_sizes):
        # 每行占用 = JSON 长度 + 元素间 ", " 2 字节（列表为空时无分隔符）
        added = row_size + (2 if batch else 0)
        if batch and (len(batch) >= batch_size or current_bytes + added > max_bytes):
            yield batch
            batch = [row]
            current_bytes = base_bytes + row_size
            continue
        if not batch and base_bytes + row_size > max_bytes:
            raise ValueError(
                f"单行 payload 约 {row_size} 字节，超过 --max-bytes={max_bytes}；"
                "请调大 --max-bytes 或检查数据是否有异常超长字段"
            )
        batch.append(row)
        current_bytes += added
    if batch:
        yield batch


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def load_api_key(key_env: str, key_file: str | None) -> str:
    """读取 raw key：环境变量优先，其次 600 权限 key 文件。"""

    key = (key_env or "").strip()
    if key:
        return key
    if key_file and Path(key_file).expanduser().is_file():
        for line in Path(key_file).expanduser().read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    raise SystemExit(
        "未找到 API Key：请设置环境变量 KNOWN_GENE_API_KEY，或用 --key-file 指定 "
        f"600 权限 key 文件（默认 {DEFAULT_KEY_FILE}）"
    )


class ApiError(Exception):
    """写接口返回的非 429/5xx 错误（含 HTTP 状态码与响应体）。"""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body[:500]}")


def post_bulk(
    base_url: str,
    api_key: str,
    rows: list[dict[str, Any]],
    *,
    mode: str,
    dry_run: bool,
    timeout: float,
    retries: int,
) -> dict[str, Any]:
    """调用批量写接口；429/5xx 自动重试，其余 HTTP 错误抛 ``ApiError``。"""

    url = base_url.rstrip("/") + API_PATH
    body = json.dumps({"rows": rows, "mode": mode, "dry_run": dry_run}, ensure_ascii=False).encode(
        "utf-8"
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            if exc.code not in (429, 500, 502, 503, 504) or attempt >= retries:
                raise ApiError(exc.code, error_body) from exc
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            wait = float(retry_after) if retry_after and retry_after.isdigit() else 2.0 ** (attempt + 1)
            print(f"  · HTTP {exc.code}，{wait:.1f}s 后重试（{attempt + 1}/{retries}）", file=sys.stderr)
            time.sleep(wait)
    raise ApiError(0, "重试次数耗尽")  # pragma: no cover - 循环内必然 return/raise


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def _print_row_errors(results: list[dict[str, Any]], *, limit: int = 20) -> None:
    shown = 0
    for item in results:
        if item.get("status") != "error":
            continue
        shown += 1
        print(f"    row {item.get('row')}: {item.get('errors')}")
        if shown >= limit:
            remaining = sum(1 for r in results if r.get("status") == "error") - shown
            if remaining > 0:
                print(f"    … 其余 {remaining} 行错误省略")
            break


def _print_row_errors_from_http(detail: Any) -> None:
    if isinstance(detail, dict) and isinstance(detail.get("errors"), list):
        for message in detail["errors"][:20]:
            print(f"    {message}")
        remaining = len(detail["errors"]) - 20
        if remaining > 0:
            print(f"    … 其余 {remaining} 条错误省略")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="KnownGene JSONL → 写接口批量 upsert（默认 dry-run）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  KNOWN_GENE_API_KEY=kgw_xxx python3 scripts/known_gene_push.py \\\n"
            "      --jsonl scripts/known_genes_v2055/out/known_genes_v2056.jsonl --dry-run\n"
            "  KNOWN_GENE_API_KEY=kgw_xxx python3 scripts/known_gene_push.py \\\n"
            "      --jsonl scripts/known_genes_v2055/out/known_genes_v2056.jsonl --commit\n"
        ),
    )
    parser.add_argument("--jsonl", required=True, help="extract.py 生成的 JSONL 路径")
    parser.add_argument(
        "--base-url",
        default="https://wheatomics.sdau.edu.cn",
        help="API 根地址，默认生产 https://wheatomics.sdau.edu.cn（本地可 http://127.0.0.1:8000）",
    )
    parser.add_argument(
        "--key-file",
        default=DEFAULT_KEY_FILE,
        help=f"raw key 文件（600 权限），默认 {DEFAULT_KEY_FILE}；环境变量 KNOWN_GENE_API_KEY 优先",
    )
    parser.add_argument("--batch-size", type=int, default=500, help="每批行数（默认 500，服务端上限 500）")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help=f"每批请求体字节上限（默认 {DEFAULT_MAX_BYTES}；服务端硬上限 2MB）",
    )
    parser.add_argument("--mode", choices=("upsert", "insert_only"), default="upsert", help="批量模式")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 行（试跑用）")
    parser.add_argument("--timeout", type=float, default=900.0, help="单请求超时秒数（默认 900s）")
    parser.add_argument("--retries", type=int, default=2, help="429/5xx 重试次数（默认 2）")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="只预演不写库（默认行为；显式写出便于脚本自查）",
    )
    group.add_argument("--commit", action="store_true", help="真正写库（不加则为 dry-run）")
    args = parser.parse_args(argv)

    dry_run = not args.commit
    if args.batch_size < 1 or args.batch_size > 500:
        print("参数错误: --batch-size 必须在 1–500 之间（服务端上限 500）", file=sys.stderr)
        return 2
    if args.max_bytes < 10_000:
        print("参数错误: --max-bytes 过小（至少 10000）", file=sys.stderr)
        return 2

    try:
        rows = load_jsonl(args.jsonl, args.limit)
    except (OSError, ValueError) as exc:
        print(f"读取 JSONL 失败: {exc}", file=sys.stderr)
        return 2
    if not rows:
        print("JSONL 为空，无内容可推送", file=sys.stderr)
        return 1

    api_key = load_api_key(os.environ.get("KNOWN_GENE_API_KEY", ""), args.key_file)
    try:
        batches = list(
            iter_batches(
                rows,
                batch_size=args.batch_size,
                max_bytes=args.max_bytes,
                mode=args.mode,
                dry_run=dry_run,
            )
        )
    except ValueError as exc:
        print(f"分批失败: {exc}", file=sys.stderr)
        return 2
    total_batches = len(batches)
    print("=" * 78)
    print(f"JSONL: {args.jsonl}")
    print(f"目标:  {args.base_url}{API_PATH}  mode={args.mode}")
    print(f"模式:  {'DRY-RUN（不写库）' if dry_run else 'COMMIT（真正写库）'}")
    print(f"数据:  {len(rows)} 行 → {total_batches} 批（每批 ≤{args.batch_size} 行 / ≤{args.max_bytes} B）")
    print("=" * 78)

    totals = {"created": 0, "updated": 0, "errors": 0, "audit": 0}
    processed = 0
    failed = False
    for batch_no, batch in enumerate(batches, start=1):
        first_row = processed + 1
        last_row = processed + len(batch)
        print(f"[{batch_no}/{total_batches}] 行 {first_row}–{last_row}（{len(batch)} 行）… ", end="", flush=True)
        try:
            response = post_bulk(
                args.base_url,
                api_key,
                batch,
                mode=args.mode,
                dry_run=dry_run,
                timeout=args.timeout,
                retries=args.retries,
            )
        except ApiError as exc:
            print("失败")
            failed = True
            print(f"  HTTP {exc.status}（本批未写入；之前批次已提交的不会回滚）", file=sys.stderr)
            try:
                payload = json.loads(exc.body)
            except ValueError:
                payload = None
            if isinstance(payload, dict) and isinstance(payload.get("detail"), dict):
                _print_row_errors_from_http(payload["detail"])
            elif isinstance(payload, dict) and payload.get("detail"):
                print(f"  detail: {str(payload['detail'])[:1000]}", file=sys.stderr)
            if exc.status in (401, 403):
                print("  → API Key 无效或 scope 不足：请检查 KNOWN_GENE_API_KEY / --key-file", file=sys.stderr)
            elif exc.status == 413:
                print("  → 请求体过大：请调小 --batch-size / --max-bytes", file=sys.stderr)
            break
        except urllib.error.URLError as exc:
            print("连接失败")
            failed = True
            print(f"  无法连接 {args.base_url}: {exc.reason}", file=sys.stderr)
            break

        data = response.get("data") or {}
        created = int(data.get("created") or 0)
        updated = int(data.get("updated") or 0)
        errors = int(data.get("errors") or 0)
        results = data.get("results") or []
        totals["created"] += created
        totals["updated"] += updated
        totals["errors"] += errors
        totals["audit"] += len(data.get("audit_ids") or [])
        print(f"created={created} updated={updated} errors={errors}")
        if errors:
            _print_row_errors(results)
        processed += len(batch)
        if errors and not dry_run:
            # 服务端非 dry-run 时不会返回 errors（有错即 422），这里防御性检查。
            failed = True
            break

    print("-" * 78)
    print(
        f"汇总: 处理 {processed}/{len(rows)} 行 | "
        + ("将新增 " if dry_run else "新增 ")
        + f"{totals['created']} | "
        + ("将更新 " if dry_run else "更新 ")
        + f"{totals['updated']} | 错误 {totals['errors']}"
        + ("" if dry_run else f" | 审计记录 {totals['audit']}")
    )
    if dry_run:
        print("这是 dry-run：未写库。确认上述结果后加 --commit 真正写入。")
    if failed or totals["errors"]:
        print("存在错误，见上方明细；可修正数据后重试（upsert 可安全重跑）。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
