"""Genome/karyotype ordering helpers.

The gene-function dropdowns (IntervalTool, PfamSearch) list every installed
genome. Their display order is derived from the karyotype (subgenome
composition) rather than from the registry's manual ``display_order`` so that
newly imported genomes automatically land in the right group.

Order convention
----------------
1. Group by ploidy level, high -> low (hexaploid first, then tetraploid,
   diploid, ...).
2. Within the same ploidy, groups sort by karyotype string.
3. Within a group, items sort by display name.

Examples
--------
>>> karyotype_ploidy("AABBDD")
6
>>> karyotype_ploidy("StStYYHH")
6
>>> karyotype_ploidy("NsNsXmXm")
4
>>> karyotype_ploidy("AA")
2
>>> infer_karyotype("Genefunc_AABBDD_Abo_table", "")
'AABBDD'
"""
from __future__ import annotations

import re

# Mixed-case canonical spellings for karyotypes that also appear upper-cased in
# the registry (legacy imports stored them as STSTYYHH etc.).
_CANONICAL = {
    "AABBDD": "AABBDD",
    "AABBRR": "AABBRR",
    "AABB": "AABB",
    "AAGG": "AAGG",
    "DDNN": "DDNN",
    "ATATGG": "AtAtGG",
    "NSNSXMXM": "NsNsXmXm",
    "STSTYYHH": "StStYYHH",
    "STSTVVJJ": "StStVVJJ",
    "HHHH": "HHHH",
    "AA": "AA",
    "DD": "DD",
    "HH": "HH",
    "SS": "SS",
    "MM": "MM",
    "RR": "RR",
    "UU": "UU",
    "VV": "VV",
    "EE": "EE",
    "TT": "TT",
    "PP": "PP",
    "GG": "GG",
    "OTHER": "Other",
}

# Species-style karyotype values (registry stores the species name for the
# decaploid Thinopyrum) -> (ploidy, canonical label).
_SPECIES = {
    "thinopyrum ponticum": (10, "Thinopyrum ponticum"),
}

_GENOME_UNIT = re.compile(r"[A-Z][a-z]?")
_PLOIDY_PREFIXES = sorted(_CANONICAL, key=len, reverse=True)


def normalize_karyotype(raw: str | None) -> str:
    """Return the canonical mixed-case karyotype, or '' when unknown."""
    if not raw:
        return ""
    key = raw.strip().upper().replace("_", "")
    if key in _CANONICAL:
        return _CANONICAL[key]
    return raw.strip()


def karyotype_ploidy(karyotype: str | None) -> int:
    """Number of subgenome copies, e.g. AABBDD=6, StStYYHH=6, AA=2."""
    if not karyotype:
        return 0
    spec = _SPECIES.get(karyotype.strip().lower())
    if spec:
        return spec[0]
    units = _GENOME_UNIT.findall(karyotype)
    if not units:
        return 0
    # Count genome units where a repeated pair (StSt, YY, HH) is one genome
    # present as a disomic pair (2 copies).
    total = 0
    i = 0
    while i < len(units):
        unit = units[i]
        if i + 1 < len(units) and units[i + 1] == unit:
            total += 2
            i += 2
        else:
            total += 1
            i += 1
    return total


def infer_karyotype(table_name: str | None, polyploidy: str | None) -> str:
    """Best-effort karyotype from the registry Polyploidy or the table prefix."""
    ploid = normalize_karyotype(polyploidy)
    if ploid and karyotype_ploidy(ploid):
        return ploid
    rest = re.sub(r"^Genefunc_", "", table_name or "")
    upper = rest.upper()
    for prefix in _PLOIDY_PREFIXES:
        if upper.startswith(prefix + "_"):
            return _CANONICAL[prefix]
    return "Other"


def sort_key(item: dict) -> tuple:
    """Sort key for example/registry items carrying karyotype + display_name."""
    karyotype = item.get("karyotype") or ""
    ploidy = karyotype_ploidy(karyotype)
    return (-ploidy, karyotype.casefold(), (item.get("display_name") or "").casefold())
