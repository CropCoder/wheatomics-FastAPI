#!/usr/bin/env python3
"""KnownGene 维护 CLI：按 clone_id 删除一条记录（写审计 + 快照）。

v1 写接口（API）**不暴露删除**——删除只能由维护者在服务器上通过本 CLI 执行，
并且必须同时满足：
- ``--clone-id``：内部自增主键；
- ``--confirm``：与库中 ``gene_id`` **完全一致**的确认值（防止 clone_id 记错误删）；
- ``--reason``：必填操作理由（写入审计 ``known_gene_change_log.reason``）。

事务语义：``SELECT ... FOR UPDATE`` 锁行 → 写 ``delete`` 审计（before_json=完整行）
→ DELETE → commit；任一步失败 rollback，不会出现"删了但没审计"。

用法（在仓库根目录运行，自动读 ``.env`` 的 DB 配置）::

    # 预演（只查行 + 校验 --confirm，不写库）
    python3 scripts/known_gene_admin.py delete --clone-id 1625 \\
        --confirm TraesCS5A03G0935400 --reason "重复行，合并到 clone_id=12" --dry-run

    # 真正删除（事务内写审计 + DELETE）
    python3 scripts/known_gene_admin.py delete --clone-id 1625 \\
        --confirm TraesCS5A03G0935400 --reason "重复行，合并到 clone_id=12"

    # 某条记录删除后，用审计表回溯（需要 admin key 的 /changes 或直接 SQL）
    SELECT id, action, clone_id, gene_id, before_json, actor_label, reason, created_at
      FROM known_gene_change_log WHERE clone_id = 1625;

注意：``cloned_gene_tbl`` 的 clone_id 不复用；删除后旧详情 URL 会 404。
删除前建议先 ``mysqldump --single-transaction cloned_gene_db cloned_gene_tbl``。
"""

from __future__ import annotations

import argparse
import json
import sys
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
from app.services.known_gene_ingest import delete_known_gene  # noqa: E402


def _connect() -> "pymysql.connections.Connection":
    """连接 cloned_gene_db（应用账号；DELETE 权限由 wheatomics_user 决定）。"""

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


def cmd_delete(args: argparse.Namespace) -> int:
    """删除一条 KnownGene：锁行 → 审计快照 → DELETE → commit。"""

    if not str(args.reason).strip():
        print("参数错误: --reason 必填（写入审计，便于日后追溯）", file=sys.stderr)
        return 1

    try:
        conn = _connect()
    except pymysql.err.OperationalError as exc:
        print(f"数据库连接失败: {exc}", file=sys.stderr)
        return 2

    try:
        with conn.cursor() as cursor:
            before = None
            # 预演：只读 + 校验，不进入写路径
            if args.dry_run:
                cursor.execute(
                    "SELECT * FROM cloned_gene_tbl WHERE clone_id = %s LIMIT 1", (args.clone_id,)
                )
                before = cursor.fetchone()
                if not before:
                    print(f"未找到 clone_id={args.clone_id}", file=sys.stderr)
                    return 1
                actual_gene_id = str(before.get("gene_id") or "")
                if actual_gene_id != args.confirm:
                    print(
                        f"--confirm 不匹配：clone_id={args.clone_id} 的 gene_id 是 {actual_gene_id!r}，"
                        f"而 --confirm 传的是 {args.confirm!r}",
                        file=sys.stderr,
                    )
                    return 1
                print("[dry-run] 将要删除以下记录（未写库、未写审计）：")
                print(
                    json.dumps(
                        {
                            key: (
                                value.isoformat()
                                if hasattr(value, "isoformat")
                                else value
                            )
                            for key, value in before.items()
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                return 0

            result = delete_known_gene(
                cursor,
                args.clone_id,
                confirm_gene_id=args.confirm,
                reason=args.reason,
                actor_label=args.actor_label,
            )
        conn.commit()
    except pymysql.err.ProgrammingError as exc:
        conn.rollback()
        if exc.args and exc.args[0] == 1146:
            print(
                "审计表 known_gene_change_log 不存在：请先以 MySQL root 执行 "
                "scripts/sql/known_gene_write_api.sql",
                file=sys.stderr,
            )
            return 2
        print(f"数据库错误: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - CLI 需要把业务错误清晰打印出来
        conn.rollback()
        print(f"删除失败（已 rollback，未写库）: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print("删除成功（审计与 DELETE 同一事务已提交）:")
    print(f"  clone_id = {result['clone_id']}")
    print(f"  gene_id  = {result['gene_id']}")
    print(f"  gene_name= {result['gene_name']}")
    print(f"  audit_id = {result['audit_id']}（action=delete，before_json=完整行快照）")
    print(f"  reason   = {args.reason}")
    print("提示：clone_id 不复用；审计可用 GET /api/genes/known/write/changes?clone_id=... 查询。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="KnownGene 维护 CLI（v1：按 clone_id 删除 + 审计）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python3 scripts/known_gene_admin.py delete --clone-id 1625 \\\n"
            "      --confirm TraesCS5A03G0935400 --reason '重复行，合并到 clone_id=12' --dry-run\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    delete = sub.add_parser("delete", help="删除一条 KnownGene（写 delete 审计）")
    delete.add_argument("--clone-id", type=int, required=True, help="要删除的 clone_id（自增主键）")
    delete.add_argument(
        "--confirm",
        required=True,
        help="确认值：必须与库中该行的 gene_id 完全一致（防误删）",
    )
    delete.add_argument("--reason", required=True, help="操作理由（写入审计 reason）")
    delete.add_argument(
        "--actor-label",
        default="cli:known_gene_admin",
        help="审计 actor_label（默认 cli:known_gene_admin）",
    )
    delete.add_argument("--dry-run", action="store_true", help="只查看将要删除的行，不写库")
    delete.set_defaults(func=cmd_delete)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
