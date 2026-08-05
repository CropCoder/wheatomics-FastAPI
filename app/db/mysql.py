"""MySQL access helpers with dict cursors.

Connection pooling is provided per database via DBUtils.PooledDB. Pools are
created **lazily inside each worker** on first use (see ``_get_pool``), never
at module import — under gunicorn ``preload_app=True`` the master forks
workers, and a pool built in the master would be shared via copy-on-write and
corrupted by concurrent access from 8 processes. Each worker therefore owns
its own pool set, grown on demand.

If DBUtils is not installed, the helpers transparently fall back to the
original connect-per-call behaviour, so the app still runs (just without
pooling) — useful for local dev without the dependency.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

import pymysql
from pymysql.cursors import DictCursor

from app.core.config import settings

try:  # pragma: no cover - import guard, exercised only when DBUtils present
    from dbutils.pooled_db import PooledDB
    _HAS_POOL = True
except ImportError:  # pragma: no cover
    PooledDB = None  # type: ignore[assignment]
    _HAS_POOL = False

#: Per-worker pool registry: database name -> PooledDB. Built lazily; each
#: gunicorn worker gets its own (see module docstring for the COW rationale).
_pools: dict[str, "PooledDB"] = {}
_pools_lock = threading.Lock()


def _get_pool(database: str):
    """Return the (lazily-created) connection pool for ``database``.

    No-op when DBUtils is unavailable — returns None so callers fall back to
    a direct connect.
    """
    if not _HAS_POOL:
        return None
    pool = _pools.get(database)
    if pool is not None:
        return pool
    with _pools_lock:
        # Double-checked: another thread may have built it while we waited.
        pool = _pools.get(database)
        if pool is not None:
            return pool
        pool = PooledDB(
            creator=pymysql,
            mincached=2,
            maxcached=8,
            maxshared=0,
            maxconnections=64,
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=database,
            charset=settings.DB_CHARSET,
            cursorclass=DictCursor,
            autocommit=False,
        )
        _pools[database] = pool
        return pool


@contextmanager
def mysql_connection(database: str) -> Iterator[pymysql.connections.Connection]:
    """Yield a managed MySQL connection.

    With pooling: borrows a pooled connection (``close()`` returns it to the
    pool rather than destroying it). Without pooling: opens a fresh
    connection and closes it on exit, as before.
    """

    pool = _get_pool(database)
    if pool is not None:
        connection = pool.connection()
        try:
            yield connection
        finally:
            connection.close()
        return

    connection = pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=database,
        charset=settings.DB_CHARSET,
        cursorclass=DictCursor,
        autocommit=False,
    )
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def mysql_cursor(database: str) -> Iterator[pymysql.cursors.Cursor]:
    """Yield a managed cursor and commit on success."""

    with mysql_connection(database) as connection:
        cursor = connection.cursor()
        try:
            yield cursor
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
