#!/usr/bin/env python3
"""KnownGene 写接口 API Key 管理 CLI（create / list / revoke）。

鉴权模型见 ``app/core/known_gene_auth.py``：数据库只存 ``sha256(raw_key)``，
raw key（``kgw_<48 位>``）只在 ``create`` 时输出一次。

前置：先以 MySQL root 执行 ``scripts/sql/known_gene_write_api.sql`` 建表。

用法（在仓库根目录运行，自动读 ``.env`` 的 DB 配置）::

    # 创建一个 write key，raw key 打印一次并写入 600 权限文件
    python3 scripts/known_gene_api_key.py create \\
        --label tiantian-maintainer \\
        --scopes write \\
        --expires-days 365 \\
        --out-file /home/fei/known_gene_api_key_20261028.txt

    # 创建 admin key（可查审计 /changes + 可写入）
    python3 scripts/known_gene_api_key.py create --label auditor --scopes admin

    # 列出全部 key（只显示前缀，不显示 key 本身）
    python3 scripts/known_gene_api_key.py list

    # 吊销（停用）一个 key；已用旧 key 的客户端立即 401
    python3 scripts/known_gene_api_key.py revoke --id 3

退出码：0=成功；1=参数/业务错误；2=数据库错误（含"表不存在"提示）。
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:  # pragma: no cover
    sys.exit("pymysql is required: run with the repo's .venv/bin/python or install pymysql")

from app.core.config import settings  # noqa: E402
from app.core.known_gene_auth import (  # noqa: E402
    SCOPE_ADMIN,
    SCOPE_WRITE,
    generate_api_key,
)

_KNOWN_SCOPES = (SCOPE_WRITE, SCOPE_ADMIN)
_TABLE_HINT = (
    "鉴权表 known_gene_api_keys 不存在：请先以 MySQL root 执行 "
    "scripts/sql/known_gene_write_api.sql"
)


def _connect() -> "pymysql.connections.Connection":
    """连接 cloned_gene_db（应用账号；只做 SELECT/INSERT/UPDATE，无需 DDL 权限）。"""

    return pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_CLONED_GENE,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )


def _parse_scopes(text: str) -> str:
    """校验并规范化 ``--scopes``（write[,admin]）。"""

    parts = [part.strip().lower() for part in text.replace(";", ",").split(",") if part.strip()]
    if not parts:
        raise ValueError("--scopes 不能为空（write 或 write,admin）")
    unknown = [part for part in parts if part not in _KNOWN_SCOPES]
    if unknown:
        raise ValueError(f"--scopes 含未知值 {unknown}；允许: write, admin")
    # 去重且保持稳定顺序（write 在前）
    ordered = [scope for scope in _KNOWN_SCOPES if scope in parts]
    return ",".join(ordered)


def _write_key_file(path: str, raw_key: str, *, force: bool) -> None:
    """把 raw key 写到 600 权限文件（默认拒绝覆盖已有文件）。"""

    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not force:
        raise FileExistsError(f"{target} 已存在；为避免覆盖旧 key，请换路径或加 --force")
    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if force else os.O_EXCL)
    fd = os.open(str(target), flags, 0o600)
    try:
        os.write(fd, (raw_key + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(str(target), 0o600)  # 兜底：无论 umask 如何都强制 600
    mode = oct(target.stat().st_mode & 0o777)
    print(f"raw key 已写入 {target}（权限 {mode}；请妥善保管，勿提交 git）")


def cmd_create(args: argparse.Namespace) -> int:
    """create：生成 raw key，存 sha256 摘要，并只输出一次 raw key。"""

    try:
        scopes = _parse_scopes(args.scopes)
    except ValueError as exc:
        print(f"参数错误: {exc}", file=sys.stderr)
        return 1
    if args.expires_days < 0:
        print("参数错误: --expires-days 不能为负数（0 表示永不过期）", file=sys.stderr)
        return 1

    raw_key, key_hash, key_prefix = generate_api_key()
    expires_at = (
        datetime.now() + timedelta(days=args.expires_days) if args.expires_days > 0 else None
    )
    try:
        conn = _connect()
    except pymysql.err.OperationalError as exc:
        print(f"数据库连接失败: {exc}", file=sys.stderr)
        return 2
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO known_gene_api_keys "
                "(key_prefix, key_hash, label, scopes, active, created_by, expires_at, note) "
                "VALUES (%s, %s, %s, %s, 1, %s, %s, %s)",
                (
                    key_prefix,
                    key_hash,
                    args.label,
                    scopes,
                    args.created_by,
                    expires_at,
                    args.note,
                ),
            )
            key_id = int(cursor.lastrowid)
        conn.commit()
    except pymysql.err.ProgrammingError as exc:
        conn.rollback()
        if exc.args and exc.args[0] == 1146:
            print(_TABLE_HINT, file=sys.stderr)
            return 2
        print(f"数据库错误: {exc}", file=sys.stderr)
        return 2
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print("=" * 78)
    print(f"API Key 创建成功: id={key_id}  label={args.label}  scopes={scopes}")
    print(f"key_prefix: {key_prefix}（数据库/日志只显示这个前缀）")
    print(f"expires_at: {expires_at.isoformat() if expires_at else '永不过期'}")
    print("-" * 78)
    print("raw key（只显示这一次，请立即保存到 600 权限文件/密码管理器）：")
    print(raw_key)
    print("=" * 78)
    print(f"用法: Authorization: Bearer {raw_key[:12]}...（完整 key 见上方）")
    if args.out_file:
        try:
            _write_key_file(args.out_file, raw_key, force=args.force)
        except FileExistsError as exc:
            print(f"警告: {exc}（raw key 只打印在 stdout，未写文件）", file=sys.stderr)
            return 1
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """list：列出 key 元信息（绝不输出 raw key / hash）。"""

    try:
        conn = _connect()
    except pymysql.err.OperationalError as exc:
        print(f"数据库连接失败: {exc}", file=sys.stderr)
        return 2
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, key_prefix, label, scopes, active, created_at, expires_at, last_used_at "
                "FROM known_gene_api_keys ORDER BY id"
            )
            rows = cursor.fetchall() or []
    except pymysql.err.ProgrammingError as exc:
        if exc.args and exc.args[0] == 1146:
            print(_TABLE_HINT, file=sys.stderr)
            return 2
        raise
    finally:
        conn.close()

    if not rows:
        print("（无 API Key；用 create 子命令创建）")
        return 0
    now = datetime.now()
    header = f"{'id':>4}  {'key_prefix':<16}  {'label':<24}  {'scopes':<10}  {'状态':<8}  {'过期时间':<19}  {'最后使用':<19}"
    print(header)
    print("-" * len(header))
    for row in rows:
        expires = row.get("expires_at")
        if not int(row.get("active") or 0):
            status = "已吊销"
        elif expires is not None and expires <= now:
            status = "已过期"
        else:
            status = "有效"
        fmt = lambda value: value.isoformat(sep=" ", timespec="seconds") if value else "-"  # noqa: E731
        print(
            f"{int(row['id']):>4}  {str(row['key_prefix']):<16}  {str(row['label'])[:24]:<24}  "
            f"{str(row['scopes']):<10}  {status:<8}  {fmt(expires):<19}  {fmt(row.get('last_used_at')):<19}"
        )
    print(f"\n共 {len(rows)} 个 key；raw key 不在数据库中（只存 sha256），无法找回，丢失请吊销后重建。")
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    """revoke：把 key 置为 active=0（不删除行，保留审计线索）。"""

    try:
        conn = _connect()
    except pymysql.err.OperationalError as exc:
        print(f"数据库连接失败: {exc}", file=sys.stderr)
        return 2
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE known_gene_api_keys SET active = 0 WHERE id = %s", (args.id,))
            affected = cursor.rowcount
        conn.commit()
    except pymysql.err.ProgrammingError as exc:
        conn.rollback()
        if exc.args and exc.args[0] == 1146:
            print(_TABLE_HINT, file=sys.stderr)
            return 2
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    if not affected:
        print(f"未找到 id={args.id} 的 key", file=sys.stderr)
        return 1
    print(f"key id={args.id} 已吊销（active=0）；该 key 的后续请求立即返回 401。")
    print("如需重新启用：mysql> UPDATE known_gene_api_keys SET active=1 WHERE id=%s;" % args.id)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="KnownGene 写接口 API Key 管理（create/list/revoke）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python3 scripts/known_gene_api_key.py create --label maintainer --scopes write \\\n"
            "      --expires-days 365 --out-file /home/fei/known_gene_api_key_20261028.txt\n"
            "  python3 scripts/known_gene_api_key.py list\n"
            "  python3 scripts/known_gene_api_key.py revoke --id 3\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="创建一个 API Key（raw key 只输出一次）")
    create.add_argument("--label", required=True, help="key 标签（维护者/用途），如 tiantian-maintainer")
    create.add_argument("--scopes", default="write", help="scope，默认 write；可 write,admin")
    create.add_argument("--expires-days", type=int, default=365, help="有效天数，默认 365；0=永不过期")
    create.add_argument("--note", default=None, help="备注（用途/负责人/轮换说明）")
    create.add_argument("--created-by", default="cli:known_gene_api_key", help="创建来源标签")
    create.add_argument("--out-file", default=None, help="把 raw key 写入该文件（强制 600 权限）")
    create.add_argument("--force", action="store_true", help="允许覆盖已存在的 --out-file")
    create.set_defaults(func=cmd_create)

    list_cmd = sub.add_parser("list", help="列出全部 key（只显示前缀）")
    list_cmd.set_defaults(func=cmd_list)

    revoke = sub.add_parser("revoke", help="吊销（停用）指定 id 的 key")
    revoke.add_argument("--id", type=int, required=True, help="key id（list 子命令可见）")
    revoke.set_defaults(func=cmd_revoke)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
