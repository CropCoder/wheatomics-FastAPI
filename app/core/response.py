"""Standard response helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def ok(data: Any, message: str = "ok") -> dict[str, Any]:
    """Wrap successful payloads consistently."""

    return {
        "success": True,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
