"""KnownGene 写接口的 API Key 鉴权 / 限流 / 请求体保护。

本模块只服务 ``app/api/routers/gene_write.py``（写接口），读接口
（``app/api/routers/gene.py``）保持匿名访问，不受影响。

鉴权模型（B 方案：DB 多密钥 + 审计表）
------------------------------------
- 原始 key 形如 ``kgw_<48 位 url-safe 字符>``（约 52 字符），**只在创建时返回一次**；
- 数据库 ``cloned_gene_db.known_gene_api_keys`` 只存 ``sha256(raw_key)`` 十六进制
  摘要（``key_hash CHAR(64)``）+ 展示用前缀 ``key_prefix``（``kgw_`` + 前 8 位），
  任何日志/审计都只记录 ``key_id`` / ``label`` / ``key_prefix``，绝不记录 raw key
  或完整 ``Authorization`` 头；
- 校验 = 先算 sha256 摘要，再按 ``key_hash`` 唯一索引查行（不在应用层逐字符比较
  明文，避免可计时比较泄露；摘要本身是定长 hex，查询走 B+Tree 唯一索引），
  然后校验 ``active=1`` 且未过期。出于安全考虑，**不存在 / 已停用 / 已过期
  统一返回 401**，响应体不区分原因（原因只写进服务端日志，且日志里也只有
  ``key_prefix``）；
- scope 不足返回 403；``admin`` scope 隐含 ``write`` 权限；
- 每次成功鉴权尽力更新 ``last_used_at``（尽力而为：失败只记 warning，不阻断请求）。

限流 / IP 白名单 / 请求体大小
-----------------------------
- 限流：进程内 ``dict[key_id] -> deque[monotonic 时间戳]`` 滑动 60s 窗口，
  超过 ``settings.KNOWN_GENE_WRITE_RATE_PER_MINUTE``（默认 60）→ 429。
  注意：生产是 8 个 gunicorn worker，**每个 worker 各自计数**，因此实际上限约为
  N × 配置值；这是为了避免引入 Redis 依赖而做的取舍，对"防误用/防脚本暴打"
  足够，不用于严格的计费级限流。
- IP 白名单：``settings.KNOWN_GENE_WRITE_ALLOW_IPS``（逗号分隔，空 = 不限制）。
  ``client_ip`` 取 ``request.client.host``。注意生产部署在 Apache 反代之后，
  该值通常是 127.0.0.1（Apache 自身地址），因此默认留空；如需白名单，请填
  Apache 节点地址或在外层完成限制。
- 请求体大小：写端点读取 body 前先看 ``Content-Length``（> 2MB → 413）；
  若客户端用 chunked（无 Content-Length），则在读取后按实际长度再检查一次。

用法（在路由中）
----------------
    from app.core.known_gene_auth import (
        AuthContext,
        enforce_known_gene_body_limit,
        require_known_gene_scope,
        verify_known_gene_key,
    )

    @router.post("", dependencies=[Depends(enforce_known_gene_body_limit)])
    async def create_gene(
        request: Request,
        ctx: AuthContext = Depends(require_known_gene_scope("write")),
    ) -> dict:
        payload = await read_json_object(request)
        ...

    @router.get("/changes")
    def list_changes(ctx: AuthContext = Depends(require_known_gene_scope("admin"))) -> dict:
        ...

命令行（scripts/known_gene_api_key.py）同样复用本模块的 ``generate_api_key`` /
``hash_api_key``，保证"生成算法"与"校验算法"只有一处实现。
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import pymysql
from fastapi import Depends, Header, HTTPException, Request, status

from app.core.config import settings
from app.db.mysql import mysql_cursor

logger = logging.getLogger(__name__)

#: 原始 key 前缀（便于在日志/密钥文件里一眼识别是 KnownGene 写接口的 key）。
RAW_KEY_PREFIX = "kgw_"
#: 展示用前缀长度：``kgw_`` + 8 位随机字符（足够区分轮换前后的 key）。
KEY_PREFIX_DISPLAY_LEN = len(RAW_KEY_PREFIX) + 8
#: ``secrets.token_urlsafe(36)`` 产生 48 位 url-safe 字符。
RAW_KEY_BODY_BYTES = 36
#: 写端点请求体硬上限：2 MB（批量 500 行 × 平均 4KB 已可覆盖）。
MAX_BODY_BYTES = 2 * 1024 * 1024
#: 限流窗口（秒）。
RATE_WINDOW_SECONDS = 60.0
#: 支持的业务 scope；admin 隐含 write。
SCOPE_WRITE = "write"
SCOPE_ADMIN = "admin"
_KNOWN_SCOPES = (SCOPE_WRITE, SCOPE_ADMIN)
_IMPLIED_SCOPES = {SCOPE_WRITE: frozenset({SCOPE_WRITE, SCOPE_ADMIN}), SCOPE_ADMIN: frozenset({SCOPE_ADMIN})}


# ---------------------------------------------------------------------------
# key 生成 / 哈希 / 解析（纯函数，CLI 与路由共用）
# ---------------------------------------------------------------------------
def generate_api_key() -> tuple[str, str, str]:
    """生成一个写接口 API key。

    返回 ``(raw_key, sha256_hex, key_prefix)``：
    - ``raw_key`` 只返回给调用方一次（打印/写入 600 权限文件），永不落库；
    - ``sha256_hex`` 存 ``known_gene_api_keys.key_hash``；
    - ``key_prefix`` 存 ``key_prefix`` 列，仅用于展示和日志定位。

    案例:
        >>> raw, digest, prefix = generate_api_key()
        >>> raw.startswith("kgw_"), len(digest), prefix
        (True, 64, 'kgw_xxxxxxxx')
    """

    raw_key = RAW_KEY_PREFIX + secrets.token_urlsafe(RAW_KEY_BODY_BYTES)
    return raw_key, hash_api_key(raw_key), raw_key[:KEY_PREFIX_DISPLAY_LEN]


def hash_api_key(raw_key: str) -> str:
    """返回 raw key 的 sha256 十六进制摘要（数据库只存这个值）。"""

    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def split_scopes(scopes_text: object) -> tuple[str, ...]:
    """把 ``scopes`` 列（``"write,admin"`` 或 ``"write"``）解析成去重元组。

    未知 scope 会被丢弃（数据库被手工改坏时不至于让请求失控）；
    允许用空格/逗号/分号分隔。
    """

    if scopes_text is None:
        return ()
    parts = str(scopes_text).replace(";", ",").replace(" ", ",").split(",")
    found = {part.strip().lower() for part in parts}
    # 固定顺序（write 在前），便于响应/日志稳定可断言。
    return tuple(scope for scope in _KNOWN_SCOPES if scope in found)


@dataclass(frozen=True)
class AuthContext:
    """一次成功鉴权的上下文；传给服务层写审计（actor_key_id / actor_label）。"""

    key_id: int
    label: str
    scopes: tuple[str, ...]
    key_prefix: str
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    client_ip: Optional[str] = None

    def has_scope(self, scope: str) -> bool:
        """判断是否具备某 scope；``admin`` 隐含 ``write``。"""

        implied = _IMPLIED_SCOPES.get(scope, frozenset({scope}))
        return bool(implied.intersection(self.scopes))


# ---------------------------------------------------------------------------
# 请求上下文 / 请求体读取
# ---------------------------------------------------------------------------
def get_client_ip(request: Request) -> Optional[str]:
    """返回客户端 IP（``request.client.host``）。

    故意不信任 ``X-Forwarded-For``：本接口的 IP 白名单只对"直连后端"有意义，
    由外层 Apache/防火墙做真实来源限制；信任可伪造的头会让白名单形同虚设。
    """

    return request.client.host if request.client else None


def _check_ip_allowlist(client_ip: Optional[str]) -> None:
    """可选的来源 IP 白名单校验（空配置 = 不限制）。"""

    raw = (settings.KNOWN_GENE_WRITE_ALLOW_IPS or "").strip()
    if not raw:
        return
    allowed = {part.strip() for part in raw.split(",") if part.strip()}
    if not allowed:
        return
    if not client_ip or client_ip not in allowed:
        logger.warning(
            "known_gene write key rejected: ip %s not in KNOWN_GENE_WRITE_ALLOW_IPS (prefix-only log)",
            client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"来源 IP {client_ip or 'unknown'} 不在 KnownGene 写接口白名单内",
        )


def _extract_raw_key(authorization: Optional[str], x_api_key: Optional[str]) -> str:
    """从 ``Authorization: Bearer <key>`` 或 ``X-API-Key`` 头里取 raw key。

    优先 ``Authorization``；两种头都没带 → 401；``Authorization`` 存在但格式
    不是 ``Bearer <token>`` → 401（同样的中文提示，不泄露细节）。
    """

    if authorization is not None:
        scheme, _, token = authorization.strip().partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="缺少或无效的 API Key：请使用 Authorization: Bearer <key>（或 X-API-Key: <key>）",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return token.strip()
    if x_api_key is not None and x_api_key.strip():
        return x_api_key.strip()
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="缺少 API Key：请在 Authorization 头使用 Bearer <key>（或 X-API-Key: <key>）",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def read_json_object(request: Request) -> dict[str, Any]:
    """读取并解析 JSON 请求体（要求为 object）。

    - 读取后按实际长度二次检查（Content-Length 缺失/chunked 场景的兜底）；
    - 非 JSON / 非 object → 400（业务字段校验由服务层做，错误为 422）。
    """

    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"请求体过大：{len(raw)} 字节 > 上限 {MAX_BODY_BYTES} 字节",
        )
    try:
        payload = json.loads(raw.decode("utf-8") or "null")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"请求体不是合法 JSON：{exc}",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请求体必须是 JSON object（如 {\"gene\": {...}} 或裸字段对象）",
        )
    return payload


async def enforce_known_gene_body_limit(request: Request) -> None:
    """写端点依赖：读取前检查 ``Content-Length``，超 2MB → 413。

    无 ``Content-Length``（chunked）时先读取 body（Starlette 会缓存，后续
    ``read_json_object`` 复用缓存），再按实际长度判断。
    """

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            size = int(content_length)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"非法 Content-Length: {content_length!r}",
            ) from None
        if size > MAX_BODY_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"请求体过大：Content-Length {size} 字节 > 上限 {MAX_BODY_BYTES} 字节",
            )
        return
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"请求体过大：{len(raw)} 字节 > 上限 {MAX_BODY_BYTES} 字节",
        )


# ---------------------------------------------------------------------------
# DB 读取 / last_used_at 更新
# ---------------------------------------------------------------------------
def _load_key_row(raw_key: str) -> Optional[dict]:
    """按 sha256 摘要查 key 行；鉴权表缺失时给出可操作的 503。"""

    digest = hash_api_key(raw_key)  # 先算摘要，任何分支耗时一致
    try:
        with mysql_cursor(settings.DB_CLONED_GENE) as cursor:
            cursor.execute(
                "SELECT id, label, scopes, key_prefix, active, expires_at, last_used_at "
                "FROM known_gene_api_keys WHERE key_hash = %s LIMIT 1",
                (digest,),
            )
            return cursor.fetchone()
    except pymysql.err.ProgrammingError as exc:
        # 1146 = table doesn't exist；缺表属于部署问题，返回 503 而不是 401，
        # 否则运维会误判为"密钥错误"。
        if exc.args and exc.args[0] == 1146:
            logger.error("known_gene auth table missing: run scripts/sql/known_gene_write_api.sql as root")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="KnownGene 写接口鉴权表未初始化：请先以 root 执行 scripts/sql/known_gene_write_api.sql",
            ) from exc
        raise
    except pymysql.err.OperationalError as exc:
        logger.error("known_gene auth DB error: %s", exc.args[0] if exc.args else "unknown")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="KnownGene 写接口鉴权暂时不可用（数据库连接失败）",
        ) from exc


def get_key_info(key_id: int) -> Optional[dict]:
    """读取 key 的最新状态（``GET /whoami`` 用；包含鉴权时刚更新的 last_used_at）。"""

    with mysql_cursor(settings.DB_CLONED_GENE) as cursor:
        cursor.execute(
            "SELECT id, label, scopes, key_prefix, active, created_at, expires_at, last_used_at "
            "FROM known_gene_api_keys WHERE id = %s LIMIT 1",
            (key_id,),
        )
        return cursor.fetchone()


def _touch_last_used(key_id: int) -> None:
    """更新 ``last_used_at``（尽力而为：失败只记 warning，不阻断请求）。"""

    try:
        with mysql_cursor(settings.DB_CLONED_GENE) as cursor:
            cursor.execute(
                "UPDATE known_gene_api_keys SET last_used_at = NOW() WHERE id = %s",
                (key_id,),
            )
    except Exception as exc:  # noqa: BLE001 - 审计用途的字段，不能阻断业务
        logger.warning("known_gene key %s last_used_at update failed: %s", key_id, exc)


# ---------------------------------------------------------------------------
# 进程内滑动窗口限流（每 worker 独立计数，见模块 docstring）
# ---------------------------------------------------------------------------
_rate_lock = threading.Lock()
_rate_buckets: dict[int, "Any"] = {}
_RATE_BUCKET_CLEANUP_THRESHOLD = 2048


def _check_rate_limit(key_id: int) -> None:
    """每 key 60 秒滑动窗口限流；超限 → 429（带 Retry-After）。"""

    limit = int(settings.KNOWN_GENE_WRITE_RATE_PER_MINUTE or 0)
    if limit <= 0:
        return
    now = time.monotonic()
    with _rate_lock:
        bucket = _rate_buckets.get(key_id)
        if bucket is None:
            from collections import deque

            bucket = deque()
            _rate_buckets[key_id] = bucket
        cutoff = now - RATE_WINDOW_SECONDS
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = max(1, int(RATE_WINDOW_SECONDS - (now - bucket[0])) + 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"请求过于频繁：每个 API Key 每分钟最多 {limit} 次，请 {retry_after} 秒后重试",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)
        if len(_rate_buckets) > _RATE_BUCKET_CLEANUP_THRESHOLD:
            # 顺手清理长期不活跃的 key，避免进程内字典无限增长。
            stale = [kid for kid, dq in _rate_buckets.items() if not dq or dq[-1] <= cutoff]
            for kid in stale:
                if kid != key_id:
                    _rate_buckets.pop(kid, None)


# ---------------------------------------------------------------------------
# FastAPI 依赖
# ---------------------------------------------------------------------------
def verify_known_gene_key(
    request: Request,
    authorization: Optional[str] = Header(None, description="Bearer <kgw_xxx>"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key", description="兼容头，等价于 Bearer"),
) -> AuthContext:
    """KnownGene 写接口的统一鉴权依赖（任意有效 key 即可，不校验具体 scope）。

    校验顺序：取 raw key → sha256 查表 → active/过期 → IP 白名单 → 限流
    → 尽力更新 last_used_at。失败响应：
    - 401：缺 key / 格式不对 / key 不存在 / 已停用 / 已过期（统一文案）；
    - 403：来源 IP 不在白名单；
    - 429：超过每 key 每分钟限流；
    - 503：鉴权表未初始化或数据库不可用。

    用法:
        ctx: AuthContext = Depends(verify_known_gene_key)
        ctx: AuthContext = Depends(require_known_gene_scope("write"))

    案例:
        curl -H "Authorization: Bearer kgw_xxx" \\
             https://wheatomics.sdau.edu.cn/api/genes/known/write/whoami
    """

    raw_key = _extract_raw_key(authorization, x_api_key)
    row = _load_key_row(raw_key)

    # 统一 401：响应不区分"不存在/停用/过期"；原因只进服务端日志。
    if not row or not int(row.get("active") or 0):
        logger.warning(
            "known_gene write key rejected: unknown-or-disabled key_prefix=%s ip=%s",
            (raw_key[:KEY_PREFIX_DISPLAY_LEN]),
            get_client_ip(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 API Key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    expires_at = row.get("expires_at")
    if expires_at is not None and expires_at <= datetime.now():
        logger.warning(
            "known_gene write key rejected: expired key_id=%s key_prefix=%s",
            row.get("id"),
            row.get("key_prefix"),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 API Key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    client_ip = get_client_ip(request)
    _check_ip_allowlist(client_ip)
    _check_rate_limit(int(row["id"]))
    _touch_last_used(int(row["id"]))

    ctx = AuthContext(
        key_id=int(row["id"]),
        label=str(row.get("label") or ""),
        scopes=split_scopes(row.get("scopes")),
        key_prefix=str(row.get("key_prefix") or ""),
        expires_at=expires_at,
        last_used_at=row.get("last_used_at"),
        client_ip=client_ip,
    )
    # 只记录 key_id/label/key_prefix/路径，绝不记录 raw key 或完整 Authorization。
    logger.info(
        "known_gene write auth ok: key_id=%s label=%s key_prefix=%s ip=%s path=%s",
        ctx.key_id,
        ctx.label,
        ctx.key_prefix,
        client_ip,
        request.url.path,
    )
    return ctx


def require_known_gene_scope(scope: str):
    """生成"要求指定 scope"的 FastAPI 依赖工厂。

    - ``require_known_gene_scope("write")``：write 或 admin 均可；
    - ``require_known_gene_scope("admin")``：仅 admin（``/changes`` 审计查询用）；
    - scope 不足 → 403（响应里回显当前 scope，便于维护者自查）。
    """

    if scope not in _KNOWN_SCOPES:
        raise ValueError(f"unknown known-gene scope: {scope!r}")

    def _dependency(ctx: AuthContext = Depends(verify_known_gene_key)) -> AuthContext:
        if not ctx.has_scope(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"API Key 缺少 {scope} 权限（当前 scopes: "
                    f"{', '.join(ctx.scopes) or '无'}）"
                ),
            )
        return ctx

    return _dependency
