"""Query normalisation helpers for the Triticeae papers literature search.

Why this module exists
----------------------
The papers table is searched with ``LIKE '%term%'``.  Two classes of misses
used to happen:

1. **Singular / plural mismatch.**  ``stripe rusts`` did not match
   ``stripe rust`` because the SQL pattern kept the trailing ``s``.
2. **Synonym mismatch.**  ``yellow rust`` (the common alias) found far fewer
   hits than ``stripe rust`` (the tags use ``stripe_rust``), and
   ``wheat``/``Triticum``, ``FHB``/``Fusarium head blight`` were treated as
   unrelated strings.

The backend therefore expands every free-text term into a small set of LIKE
variants (original + singularised + a curated synonym list) and ORs them
together; multiple comma-separated terms stay AND-ed, mirroring the existing
query-builder semantics.

This is intentionally *not* a fuzzy/typo matcher (that is a later phase):
expansion is deterministic, cheap and auditable.
"""

from __future__ import annotations

import re

# Curated domain synonyms. Keys are lowercase, singular, space-separated.
# Values are additional search phrases that should be treated as equivalent.
SYNONYMS: dict[str, list[str]] = {
    # rust diseases (common name <-> pathosystem <-> pathogen)
    "yellow rust": ["stripe rust", "Puccinia striiformis"],
    "stripe rust": ["yellow rust", "Puccinia striiformis"],
    "leaf rust": ["brown rust", "Puccinia triticina"],
    "brown rust": ["leaf rust", "Puccinia triticina"],
    "stem rust": ["black rust", "Puccinia graminis"],
    "black rust": ["stem rust", "Puccinia graminis"],
    "powdery mildew": ["Blumeria graminis", "Erysiphe graminis"],
    "fusarium head blight": ["FHB", "scab", "Fusarium graminearum"],
    "fhb": ["fusarium head blight", "Fusarium graminearum"],
    "crown rot": ["Fusarium crown rot", "Fusarium pseudograminearum"],
    "take all": ["take-all", "Gaeumannomyces graminis"],
    "septoria": ["Septoria tritici", "Zymoseptoria tritici", "Mycosphaerella graminicola"],
    "spot blotch": ["Bipolaris sorokiniana"],
    "karnal bunt": ["Tilletia indica"],
    "common bunt": ["Tilletia caries", "Tilletia laevis"],
    "loose smut": ["Ustilago tritici"],
    "barley yellow dwarf": ["BYDV"],
    "wheat streak mosaic": ["WSMV"],
    # species / genera
    "wheat": ["Triticum"],
    "triticum": ["wheat"],
    "barley": ["Hordeum"],
    "hordeum": ["barley"],
    "rye": ["Secale"],
    "secale": ["rye"],
    "ae. tauschii": ["Aegilops tauschii"],
    "aegilops tauschii": ["Ae. tauschii"],
    "wild emmer": ["Triticum dicoccoides", "Triticum turgidum ssp. dicoccoides"],
    "einkorn": ["Triticum monococcum"],
    "emmer": ["Triticum dicoccon"],
    "durum": ["Triticum durum", "Triticum turgidum"],
    "triticale": ["x Triticosecale"],
    # traits and abbreviations
    "tgw": ["thousand grain weight"],
    "thousand grain weight": ["TGW"],
    "grain weight": ["kernel weight"],
    "grain yield": ["yield"],
    "salt stress": ["salinity"],
    "salinity": ["salt stress"],
    "drought": ["water deficit", "drought stress"],
    "cold": ["low temperature", "cold stress"],
    "heat": ["high temperature", "heat stress"],
    "lodging": ["lodging resistance"],
    "preharvest sprouting": ["pre-harvest sprouting"],
    "plant height": ["PH"],
    "heading date": ["HD", "flowering time"],
    "flowering time": ["heading date"],
    "stay green": ["stay-green"],
    "nitrogen use efficiency": ["NUE"],
    "nue": ["nitrogen use efficiency"],
    "water use efficiency": ["WUE"],
    "wue": ["water use efficiency"],
}


def normalize_phrase(value: str) -> str:
    """Lowercase, unify separators and drop punctuation for LIKE matching."""
    s = str(value or "").strip().lower()
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _singularize_word(word: str) -> str:
    """Very small English singulariser (no external stemmer dependency)."""
    if len(word) <= 3:
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("sses", "shes", "ches", "xes", "zes")):
        return word[:-2]
    if word.endswith("ss"):
        return word
    if word.endswith("s"):
        return word[:-1]
    return word


def singularize(phrase: str) -> str:
    return " ".join(_singularize_word(w) for w in phrase.split())


def split_terms(value: str) -> list[str]:
    """Split a filter value into AND-ed terms (the query builder joins with ',')."""
    if value is None:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def expand_text_variants(value: str) -> list[str]:
    """Return lowercase phrases that should be OR-ed for one text filter term.

    Order matters only for readability: raw form first, then normalised,
    then singularised, then synonyms.  Duplicates are removed.
    """
    raw = str(value or "").strip().lower()
    if not raw:
        return []

    variants: list[str] = []

    def _add(phrase: str) -> None:
        phrase = re.sub(r"\s+", " ", str(phrase or "").strip().lower())
        if phrase and phrase not in variants:
            variants.append(phrase)

    _add(raw)
    base = normalize_phrase(raw)
    _add(base)
    for key in (base, singularize(base)):
        _add(key)
        for extra in SYNONYMS.get(key, []):
            _add(normalize_phrase(extra))
    # Phrase-inside-value expansion, e.g. "wheat stripe rust resistance".
    for key, extras in SYNONYMS.items():
        if len(key) >= 5 and key in base and key != base:
            for extra in extras:
                _add(normalize_phrase(extra))
    return variants
