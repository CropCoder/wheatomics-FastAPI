#!/usr/bin/env python3
"""KnownGene 写接口冒烟自测（只读 + dry-run，不会写库）。

用途：部署后在新环境/生产上快速验证「鉴权 + 5 条新路由 + 读接口未回归」。
**本脚本只会调用 dry_run=true 的写端点**，不会真正写库；真正的落库冒烟由
维护者按 docs/known_genes/WRITE_API.md §9 的清单手动执行（或 known_gene_push.py）。

用法::

    # 匿名部分（401/读接口）不需要 key；带上 key 会额外验证 whoami/changes/dry-run
    KNOWN_GENE_API_KEY=kgw_xxx python3 scripts/known_gene_write_selftest.py \\
        --base-url https://wheatomics.sdau.edu.cn

    # key 从 600 权限文件读取（环境变量优先）
    python3 scripts/known_gene_write_selftest.py \\
        --base-url http://127.0.0.1:8000 \\
        --key-file /home/fei/known_gene_api_key_20261028.txt

    # 额外验证 2MB 请求体上限（会发送约 2.1MB 的非法请求，默认不测）
    python3 scripts/known_gene_write_selftest.py --check-body-limit

退出码：0=全部 PASS/WARN/SKIP；1=存在 FAIL；2=参数错误。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

DEFAULT_KEY_FILE = "/home/fei/known_gene_api_key_20261028.txt"

_PASS = "PASS"
_FAIL = "FAIL"
_WARN = "WARN"
_SKIP = "SKIP"

_results: list[tuple[str, str, str]] = []


def report(status: str, name: str, detail: str = "") -> None:
    """记录并打印一条检查结果。"""

    _results.append((status, name, detail))
    suffix = f" — {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")


def http_call(
    base_url: str,
    method: str,
    path: str,
    *,
    key: Optional[str] = None,
    payload: Any = None,
    timeout: float = 60.0,
    extra_headers: Optional[dict[str, str]] = None,
) -> tuple[int, Any, str]:
    """发请求，返回 ``(status, parsed_json_or_None, raw_text)``；网络错误 status=0。"""

    url = base_url.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return response.status, _try_json(raw), raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, _try_json(raw), raw
    except urllib.error.URLError as exc:
        return 0, None, str(exc.reason)


def _try_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except ValueError:
        return None


def selftest_gene_payload() -> dict[str, Any]:
    """构造一条**唯一**的测试基因记录（dry_run 用；不会落库）。"""

    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return {
        "gene_id": f"SELFTEST_{stamp}",
        "gene_name": f"selftest-{stamp}",
        "reference_genome_id": "Refv1.0",
        "gene_species": "Triticum aestivum (bread wheat)",
        "chrom_pos": "Refv1.0 chr7A:1.000-1.001Mb",
        "gene_phenotype": "selftest phenotype (dry-run only)",
        "functional_category": "Quality & Yield",
        "research_strategy": "Not reported",
        "key_result": "Selftest row for the KnownGene write API; never committed.",
        "paper_title": "Selftest paper title",
        "paper_doi": "10.0000/selftest",
        "publication_year": 2026,
    }


def run_checks(args: argparse.Namespace) -> int:
    base = args.base_url
    key = args.key

    # --- 0. 服务健康 / 读接口回归（匿名） ---------------------------------
    status, body, raw = http_call(base, "GET", "/api/health")
    if status == 200:
        report(_PASS, "GET /api/health", "200")
    else:
        report(_FAIL, "GET /api/health", f"status={status} body={raw[:200]}")

    status, body, raw = http_call(base, "GET", "/api/genes/known/all?limit=1")
    records = (body or {}).get("data", {}).get("records") if isinstance(body, dict) else None
    if status == 200 and isinstance(records, list) and records:
        report(_PASS, "GET /api/genes/known/all?limit=1", f"200，{len(records)} 条")
        first_clone_id = records[0].get("clone_id")
    else:
        report(_FAIL, "GET /api/genes/known/all?limit=1", f"status={status} body={raw[:200]}")
        first_clone_id = None

    status, body, raw = http_call(base, "GET", "/api/genes/known/stats")
    if status == 200 and isinstance(body, dict) and body.get("data", {}).get("total"):
        report(_PASS, "GET /api/genes/known/stats", f"200，total={body['data']['total']}")
    else:
        report(_WARN, "GET /api/genes/known/stats", f"status={status}（旧版本无此端点时可忽略）")

    # --- 1. 鉴权：匿名必须 401 --------------------------------------------
    for path, method in (
        ("/api/genes/known/write/whoami", "GET"),
        ("/api/genes/known/write/changes?limit=1", "GET"),
    ):
        status, _, _ = http_call(base, method, path)
        if status == 401:
            report(_PASS, f"{method} {path} 无 key", "401")
        elif status == 404:
            report(_FAIL, f"{method} {path} 无 key", "404：路由未注册（检查 main.py 是否 include gene_write）")
        else:
            report(_FAIL, f"{method} {path} 无 key", f"期望 401，实际 {status}")

    if not key:
        report(_SKIP, "带 key 的写接口检查", "未提供 KNOWN_GENE_API_KEY / --key-file")
        return 0 if all(item[0] != _FAIL for item in _results) else 1

    # --- 2. 无效 key 必须 401 ---------------------------------------------
    status, _, _ = http_call(base, "GET", "/api/genes/known/write/whoami", key="kgw_invalid_selftest_key")
    report(_PASS if status == 401 else _FAIL, "GET whoami 无效 key", f"期望 401，实际 {status}")

    # --- 3. whoami ---------------------------------------------------------
    status, body, raw = http_call(base, "GET", "/api/genes/known/write/whoami", key=key)
    if status == 200 and isinstance(body, dict):
        data = body.get("data") or {}
        scopes = data.get("scopes")
        report(
            _PASS,
            "GET whoami（有效 key）",
            f"key_id={data.get('key_id')} label={data.get('label')!r} scopes={scopes}",
        )
        is_admin = isinstance(scopes, list) and "admin" in scopes
    else:
        report(_FAIL, "GET whoami（有效 key）", f"status={status} body={raw[:300]}")
        is_admin = False

    # --- 4. 审计查询（admin 才有权限） ------------------------------------
    status, body, raw = http_call(base, "GET", "/api/genes/known/write/changes?limit=1", key=key)
    if status == 200 and isinstance(body, dict):
        report(_PASS, "GET changes（admin）", f"200，total={(body.get('data') or {}).get('total')}")
    elif status == 403 and not is_admin:
        report(_PASS, "GET changes（write-only key）", "403（符合预期：审计查询需要 admin scope）")
    else:
        report(_FAIL, "GET changes", f"status={status} body={raw[:300]}")

    # --- 5. 新增 dry-run ---------------------------------------------------
    payload = {"dry_run": True, "gene": selftest_gene_payload()}
    status, body, raw = http_call(base, "POST", "/api/genes/known/write", key=key, payload=payload)
    if status == 200 and isinstance(body, dict):
        data = body.get("data") or {}
        record = data.get("record") or {}
        ok_derived = bool(record.get("species_primary")) and bool(record.get("chromosome"))
        report(
            _PASS if ok_derived else _WARN,
            "POST /write（dry_run）",
            f"200，species_primary={record.get('species_primary')!r} "
            f"chromosome={record.get('chromosome')!r}",
        )
    elif status == 409:
        report(_WARN, "POST /write（dry_run）", "409 重复（同 gene_id+gene_name 已存在，换 key 重试即可）")
    else:
        report(_FAIL, "POST /write（dry_run）", f"status={status} body={raw[:400]}")

    # --- 6. 校验错误必须是 422 --------------------------------------------
    bad_payload = {"dry_run": True, "gene": {"gene_id": "SELFTEST_BAD"}}
    status, _, raw = http_call(base, "POST", "/api/genes/known/write", key=key, payload=bad_payload)
    report(_PASS if status == 422 else _FAIL, "POST /write 缺必填字段", f"期望 422，实际 {status}")

    bad_payload = {
        "dry_run": True,
        "gene": {**selftest_gene_payload(), "clone_id": 1},
    }
    status, _, _ = http_call(base, "POST", "/api/genes/known/write", key=key, payload=bad_payload)
    report(_PASS if status == 422 else _FAIL, "POST /write 未知字段", f"期望 422，实际 {status}")

    # --- 7. 更新 dry-run ---------------------------------------------------
    clone_id = args.clone_id or first_clone_id
    if clone_id is None:
        report(_SKIP, "PATCH dry-run", "没有可用 clone_id（--clone-id 或 /known/all 均为空）")
    else:
        status, body, raw = http_call(
            base,
            "PATCH",
            f"/api/genes/known/write/{clone_id}",
            key=key,
            payload={"dry_run": True, "fields": {"gene_phenotype": "selftest dry-run phenotype"}},
        )
        if status == 200:
            changed = (body.get("data") or {}).get("changed_fields")
            report(_PASS, f"PATCH /write/{clone_id}（dry_run）", f"200，changed_fields={changed}")
        elif status == 404:
            report(_FAIL, f"PATCH /write/{clone_id}（dry_run）", "404：clone_id 不存在")
        else:
            report(_FAIL, f"PATCH /write/{clone_id}（dry_run）", f"status={status} body={raw[:300]}")

    # --- 8. 批量 dry-run ---------------------------------------------------
    bulk_payload = {"rows": [selftest_gene_payload()], "mode": "upsert", "dry_run": True}
    status, body, raw = http_call(base, "POST", "/api/genes/known/write/bulk", key=key, payload=bulk_payload)
    if status == 200 and isinstance(body, dict):
        data = body.get("data") or {}
        rows = data.get("results") or []
        report(
            _PASS,
            "POST /write/bulk（dry_run）",
            f"200，created={data.get('created')} updated={data.get('updated')} "
            f"status={[row.get('status') for row in rows]}",
        )
    else:
        report(_FAIL, "POST /write/bulk（dry_run）", f"status={status} body={raw[:400]}")

    # --- 9. 批量超限（可选） ----------------------------------------------
    if args.check_batch_limit:
        too_many = {"rows": [{}] * 501, "mode": "upsert", "dry_run": True}
        status, _, _ = http_call(base, "POST", "/api/genes/known/write/bulk", key=key, payload=too_many)
        report(_PASS if status in (413, 422) else _FAIL, "POST /write/bulk 501 行", f"期望 413/422，实际 {status}")

    # --- 10. 请求体 > 2MB（可选） -----------------------------------------
    if args.check_body_limit:
        huge = {"dry_run": True, "gene": {**selftest_gene_payload(), "gene_phenotype": "x" * (2 * 1024 * 1024)}}
        status, _, _ = http_call(base, "POST", "/api/genes/known/write", key=key, payload=huge)
        report(_PASS if status == 413 else _FAIL, "POST /write >2MB body", f"期望 413，实际 {status}")

    return 0 if all(item[0] != _FAIL for item in _results) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="KnownGene 写接口 dry-run 冒烟自测（不写库）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  KNOWN_GENE_API_KEY=kgw_xxx python3 scripts/known_gene_write_selftest.py \\\n"
            "      --base-url https://wheatomics.sdau.edu.cn\n"
        ),
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API 根地址")
    parser.add_argument(
        "--key-file",
        default=DEFAULT_KEY_FILE,
        help=f"raw key 文件（600 权限）；环境变量 KNOWN_GENE_API_KEY 优先（默认 {DEFAULT_KEY_FILE}）",
    )
    parser.add_argument("--clone-id", type=int, default=None, help="PATCH dry-run 用的 clone_id（默认取 /known/all 第一条）")
    parser.add_argument(
        "--check-batch-limit",
        action="store_true",
        help="额外验证批量 501 行被拒绝（默认不测）",
    )
    parser.add_argument(
        "--check-body-limit",
        action="store_true",
        help="额外验证 >2MB 请求体返回 413（默认不测，会发送 2MB 请求）",
    )
    return parser


def _load_key(env_value: str, key_file: str) -> Optional[str]:
    key = (env_value or "").strip()
    if key:
        return key
    path = Path(key_file).expanduser()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.key = _load_key(os.environ.get("KNOWN_GENE_API_KEY", ""), args.key_file)
    print("=" * 78)
    print(f"KnownGene 写接口自测  base_url={args.base_url}")
    print(f"API Key: {'已提供（' + str(len(args.key)) + ' 字符）' if args.key else '未提供（跳过带 key 检查）'}")
    print("=" * 78)
    try:
        return run_checks(args)
    finally:
        failures = sum(1 for status, _, _ in _results if status == _FAIL)
        warnings = sum(1 for status, _, _ in _results if status == _WARN)
        skipped = sum(1 for status, _, _ in _results if status == _SKIP)
        passes = sum(1 for status, _, _ in _results if status == _PASS)
        print("-" * 78)
        print(f"结果: PASS={passes} WARN={warnings} SKIP={skipped} FAIL={failures}")
        if failures:
            print("存在 FAIL 项，请按上方提示排查。", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
