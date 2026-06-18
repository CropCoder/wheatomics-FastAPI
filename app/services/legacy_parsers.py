"""Normalization helpers for legacy table fields."""

from __future__ import annotations


def split_legacy_multi_value(value: object) -> list[str]:
    """Split CGI-era multi-value fields joined with ###."""

    if value is None:
        return []
    return [part.strip() for part in str(value).split("###") if part and part.strip()]


def normalize_text(value: object) -> str:
    """Normalize legacy escaped content."""

    if value is None:
        return ""
    return str(value).replace("####", "'").replace("#", "'").strip()


def pick_first(mapping: dict, *keys: str) -> object:
    """Return the first existing non-null value from a mapping."""

    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None
