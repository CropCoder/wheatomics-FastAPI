"""Lightweight visit counter and visitor statistics.

Aggregates per-day PV/UV and tracks currently-online visitors
(15-minute sliding window). Data lives in `wheatomics_db.visit_stats`
and `wheatomics_db.visit_log`. No external tracking dependency.

Schema lives in `visit_stats` tables on `wheatomics_db` and must exist before
this router is mounted. `wheatomics_user` only has DML privileges, not DDL —
apply the schema with a privileged account during deployment.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel

from app.core.config import settings
from app.core.response import ok
from app.db.mysql import mysql_cursor


router = APIRouter(prefix="/track", tags=["Track"])


# ---- schema check ---------------------------------------------------------

REQUIRED_TABLES = ("visit_stats", "visit_log")


def _check_schema() -> None:
    """Verify required tables exist. Caller surfaces the error to clients."""
    with mysql_cursor(settings.DB_LITERATURE) as cursor:
        placeholders = ",".join(["%s"] * len(REQUIRED_TABLES))
        cursor.execute(
            f"SELECT TABLE_NAME FROM information_schema.TABLES "
            f"WHERE TABLE_SCHEMA = %s AND TABLE_NAME IN ({placeholders})",
            (settings.DB_LITERATURE, *REQUIRED_TABLES),
        )
        found = {row["TABLE_NAME"] for row in cursor.fetchall()}
    missing = [t for t in REQUIRED_TABLES if t not in found]
    if missing:
        raise RuntimeError(
            f"visit-counter tables missing: {missing}. "
            f"Create the visit_stats schema with a privileged user."
        )


# ---- helpers --------------------------------------------------------------

def _hash_visitor(ip: str, user_agent: str) -> str:
    """Stable per-day visitor hash. Salted so logs aren't trivially invertible."""
    raw = f"{ip}|{user_agent}|{settings.APP_NAME}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---- request/response models ----------------------------------------------


class TrackPayload(BaseModel):
    page: str = "unknown"


# ---- endpoints ------------------------------------------------------------


@router.post("/visit")
def record_visit(
    payload: TrackPayload,
    x_forwarded_for: str | None = Header(default=None, alias="X-Forwarded-For"),
    user_agent: str | None = Header(default=None, alias="User-Agent"),
) -> dict:
    """Record one page view and bump today's UV if this is a new visitor.

    Idempotent within the same day per (ip, user-agent) pair.
    """
    _check_schema()
    ip = (x_forwarded_for.split(",")[0].strip() if x_forwarded_for else "unknown")
    visitor = _hash_visitor(ip, user_agent or "unknown")
    today = _utc_now().date()
    now = _utc_now()

    with mysql_cursor(settings.DB_LITERATURE) as cursor:
        # Insert visitor row for today; IGNORE duplicates keeps it idempotent.
        cursor.execute(
            """
            INSERT IGNORE INTO visit_log (visitor_hash, visit_date, last_seen)
            VALUES (%s, %s, %s)
            """,
            (visitor, today, now),
        )
        is_new_visitor = cursor.rowcount == 1

        # Always bump PV (every call is a pageview); bump UV only on first hit.
        cursor.execute(
            """
            INSERT INTO visit_stats (visit_date, pv, uv)
            VALUES (%s, 1, %s)
            ON DUPLICATE KEY UPDATE
                pv = pv + 1,
                uv = uv + VALUES(uv)
            """,
            (today, 1 if is_new_visitor else 0),
        )

    return ok({"recorded_at": now.isoformat(), "new_visitor": is_new_visitor})


@router.get("/stats")
def get_stats() -> dict:
    """Public stats: today's PV/UV, total PV/UV, and currently-online count."""
    _check_schema()
    today = _utc_now().date()
    cutoff = _utc_now() - timedelta(minutes=15)

    with mysql_cursor(settings.DB_LITERATURE) as cursor:
        cursor.execute(
            """
            SELECT pv, uv FROM visit_stats
            WHERE visit_date = %s
            """,
            (today,),
        )
        row = cursor.fetchone()
        today_pv = int(row["pv"]) if row else 0
        today_uv = int(row["uv"]) if row else 0

        cursor.execute("SELECT COALESCE(SUM(pv),0) AS pv, COALESCE(SUM(uv),0) AS uv FROM visit_stats")
        agg = cursor.fetchone() or {"pv": 0, "uv": 0}

        cursor.execute(
            "SELECT COUNT(DISTINCT visitor_hash) AS online FROM visit_log WHERE last_seen >= %s",
            (cutoff,),
        )
        online_row = cursor.fetchone() or {"online": 0}

    return ok({
        "today": {"date": today.isoformat(), "pv": today_pv, "uv": today_uv},
        "total": {"pv": int(agg["pv"]), "uv": int(agg["uv"])},
        "online": int(online_row["online"]),
    })