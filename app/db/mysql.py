"""MySQL access helpers with dict cursors."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import pymysql
from pymysql.cursors import DictCursor

from app.core.config import settings


@contextmanager
def mysql_connection(database: str) -> Iterator[pymysql.connections.Connection]:
    """Yield a managed MySQL connection."""

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
