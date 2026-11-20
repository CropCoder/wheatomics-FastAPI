"""Cross-version wheat gene IDs (IWGSC RefSeq v1 / v2 / v3).

Why this exists
---------------
Different platform modules store different annotation versions:

* eQTL Atlas (``eqtl.wheat``) and the scRNA / scRNA-seq atlases store IWGSC
  **v3** (``...03G...``) gene IDs;
* the WheatPPI tables store IWGSC **v2** (``...02G...``) IDs, with a transcript
  suffix in ``PPI_result``.

A reviewer who pastes a v2 (02G) or v1 (01G) ID into one of those modules gets
an empty payload with no explanation, which reads like "the platform has no
data". ``Genehub_DB.GenePageIWGSCv1_table`` carries the v1/v2/v3 triple for the
whole annotation set (including ``LC`` and chrUn ``CSU`` genes), so the routers
translate the user's ID to the version they need and can explain what was tried.

All lookups are cached per process; any DB problem degrades to "no mapping"
instead of breaking the module.
"""

from __future__ import annotations

import re

from app.core.config import settings
from app.db.mysql import mysql_cursor

#: Trailing transcript version (``TraesCS1A02G000100.1`` -> base gene ID).
_TRANSCRIPT_SUFFIX = re.compile(r"\.\d+$")

#: Version keys in the order they are usually preferred per module.
_VERSION_KEYS = ("v1", "v2", "v3")

#: Per-process cache: base gene ID -> (v1, v2, v3); None when not mapped.
_TRIPLE_CACHE: dict[str, tuple[str | None, str | None, str | None]] = {}
_TRIPLE_CACHE_MAX = 20_000


def base_id(gene_id: str) -> str:
    """Strip a transcript suffix: ``TraesCS1A02G000100.1`` -> ``...000100``."""
    return _TRANSCRIPT_SUFFIX.sub("", (gene_id or "").strip())


def _clean(value) -> str | None:
    text = base_id(value) if value else ""
    return text or None


def _load_triples(bases: list[str]) -> None:
    """Fill the cache for ``bases`` with one batched DB query."""
    pending = [b for b in dict.fromkeys(bases) if b and b not in _TRIPLE_CACHE]
    if not pending:
        return
    placeholders = ",".join(["%s"] * len(pending))
    try:
        with mysql_cursor(settings.DB_GENEHUB) as cursor:
            cursor.execute(
                "SELECT GeneIDv1, GeneIDv2, GeneIDv3 FROM GenePageIWGSCv1_table "
                f"WHERE GeneIDv1 IN ({placeholders}) OR GeneIDv2 IN ({placeholders}) "
                f"OR GeneIDv3 IN ({placeholders})",
                tuple(pending) * 3,
            )
            rows = cursor.fetchall()
    except Exception:  # noqa: BLE001 - a missing mapping must not break a module
        for base in pending:
            _TRIPLE_CACHE[base] = (None, None, None)
        return

    for row in rows:
        triple = (_clean(row.get("GeneIDv1")), _clean(row.get("GeneIDv2")),
                  _clean(row.get("GeneIDv3")))
        for value in triple:
            if value:
                _TRIPLE_CACHE[value] = triple
    for base in pending:
        _TRIPLE_CACHE.setdefault(base, (None, None, None))
    # Bound the cache so a huge batch request cannot grow it without limit.
    while len(_TRIPLE_CACHE) > _TRIPLE_CACHE_MAX:
        _TRIPLE_CACHE.pop(next(iter(_TRIPLE_CACHE)))
        break


def id_versions(gene_id: str) -> dict[str, str | None]:
    """Return ``{"input", "base", "v1", "v2", "v3"}`` for one gene ID."""
    return id_versions_many([gene_id])[gene_id]


def id_versions_many(gene_ids: list[str]) -> dict[str, dict[str, str | None]]:
    """Batched :func:`id_versions` (one DB round trip for the whole list)."""
    inputs = [str(gene_id or "").strip() for gene_id in gene_ids]
    _load_triples([base_id(gene) for gene in inputs])
    out: dict[str, dict[str, str | None]] = {}
    for gene in inputs:
        base = base_id(gene)
        triple = _TRIPLE_CACHE.get(base, (None, None, None))
        out[gene] = {
            "input": gene,
            "base": base or None,
            "v1": triple[0],
            "v2": triple[1],
            "v3": triple[2],
        }
    return out


def versions_map(gene_ids: list[str]) -> dict[str, dict[str, str | None]]:
    """``{input: {"v1","v2","v3"}}`` with ``None`` dropped (for JSON responses)."""
    out: dict[str, dict[str, str]] = {}
    for gene, info in id_versions_many(gene_ids).items():
        mapped = {key: info[key] for key in _VERSION_KEYS if info.get(key)}
        out[gene] = mapped
    return out


def variants(
    gene_id: str,
    prefer: tuple[str, ...] = ("v3", "v2", "v1"),
    *,
    transcript_suffix: bool = False,
) -> list[str]:
    """Ordered unique ID spellings to try against a module's data store.

    ``prefer`` lists the version keys in priority order; the caller's original
    spelling and its base form always come first/last so an exact match still
    wins. With ``transcript_suffix`` each form also gets a ``.1`` variant
    (``PPI_result`` stores transcript-level IDs).
    """
    info = id_versions(gene_id)
    ordered: list[str | None] = [info["input"], info["base"]]
    for key in prefer:
        ordered.append(info.get(key))
    out: list[str] = []
    for value in ordered:
        if not value:
            continue
        for form in ([value, value + ".1"] if transcript_suffix else [value]):
            if form not in out:
                out.append(form)
    return out


def variants_many(
    gene_ids: list[str],
    prefer: tuple[str, ...] = ("v3", "v2", "v1"),
    *,
    transcript_suffix: bool = False,
) -> dict[str, list[str]]:
    """Batched :func:`variants`."""
    return {
        gene: variants(gene, prefer, transcript_suffix=transcript_suffix)
        for gene in gene_ids
    }


def empty_hint(
    module: str,
    gene_id: str,
    stored_versions: str,
    *,
    extra: str = "",
) -> str:
    """Explain an empty result caused by an annotation-version mismatch."""
    info = id_versions(gene_id)
    mapped = ", ".join(
        f"{label}={info[key]}"
        for key, label in (("v1", "v1/01G"), ("v2", "v2/02G"), ("v3", "v3/03G"))
        if info.get(key)
    )
    if mapped:
        text = (
            f"No record for {gene_id} in {module}. This module stores "
            f"{stored_versions} gene IDs; the same gene in the other annotation "
            f"versions is: {mapped}. The lookup already tried all available "
            "versions, so the gene is likely absent from this dataset rather "
            "than mis-versioned."
        )
    else:
        text = (
            f"No record for {gene_id} in {module}. This module stores "
            f"{stored_versions} gene IDs and the platform could not map the "
            "input ID to another annotation version (it may be a non-IWGSC ID, "
            "e.g. from a different assembly or a transcript of a gene absent "
            "from the Chinese Spring annotation)."
        )
    return (text + " " + extra).strip()
