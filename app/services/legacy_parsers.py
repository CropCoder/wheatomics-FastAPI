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


# ---------------------------------------------------------------------------
# Helpers added for the curated KnownGene dataset (v2056 import).
# These are additive only: the legacy helpers above keep their exact behavior
# because 15+ other modules rely on them.
# ---------------------------------------------------------------------------


def normalize_known_text(value: object, legacy: bool) -> str:
    """Normalize a KnownGene text field without corrupting curated ``#``.

    Legacy rows (``reference_genome_id IS NULL``: pre-v2056 rows and CGI-era
    submissions) use the historical escape convention where ``#`` is stored as
    an apostrophe, so they keep ``normalize_text()`` behavior.  Curated v2056
    rows contain literal ``#`` characters (e.g. ``7S#1``, ``EMS lines #1/#2``)
    and must be returned verbatim (plain strip only).
    """

    if value is None:
        return ""
    if legacy:
        return normalize_text(value)
    return str(value).strip()


def split_aligned_multi_value(value: object) -> list[str]:
    """Split a CGI-era ``###`` multi-value field, preserving empty slots.

    ``split_legacy_multi_value()`` drops empty segments, which destroys the
    positional title/DOI/year alignment needed for ``references[]``.  This
    variant keeps every slot (the result length equals the segment count) so
    callers can pad/align by index.
    """

    if value is None:
        return []
    return [part.strip() for part in str(value).split("###")]
