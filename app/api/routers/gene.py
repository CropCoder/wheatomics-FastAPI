"""Gene and cloned-gene routes."""

from __future__ import annotations

import html
import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.genome_ordering import infer_karyotype, sort_key as genome_sort_key
from app.core.exceptions import ResourceNotFound, ValidationFailure
from app.core.response import ok
from app.core.security import (
    GENE_FUNCTION_TABLES,
    GENEFUNC_TABLE_ALIASES,
    ensure_allowed_table,
    ensure_gene_like,
    ensure_interval_like,
)

def _validate_genefunc_table(table: str) -> str:
    """Validate that a table exists in Genefuncdb. Replaces static allowlist.

    Legacy ids from the CGI era (e.g. Genefunc_IWGSC03G_table, renamed to
    Genefunc_CS_IWGSC03G_table) are resolved through GENEFUNC_TABLE_ALIASES so
    old URLs keep returning data. Returns the canonical table name.
    """
    from app.db.mysql import mysql_cursor
    table = GENEFUNC_TABLE_ALIASES.get(table, table)
    with mysql_cursor(settings.DB_GENEFUNC) as cursor:
        cursor.execute("SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
                       (settings.DB_GENEFUNC, table))
        if not cursor.fetchone():
            from app.core.exceptions import ValidationFailure
            raise ValidationFailure(
                f"Unknown gene function table: {table}. "
                "Call GET /api/genes/functions/tables for the list of available tables."
            )
    return table
from app.db.mysql import mysql_connection, mysql_cursor
from app.schemas.gene import DOIReference, GeneDetailResponse, GeneFunctionRecord, KnownGeneDetail, KnownGeneSummary
from app.services.genome_examples import GENOME_EXAMPLES  # noqa: F401  (legacy re-export)
from app.services.legacy_parsers import (
    normalize_known_text,
    normalize_text,
    split_aligned_multi_value,
    split_legacy_multi_value,
)

router = APIRouter(prefix="/genes", tags=["Known Genes"])
genehub_router = APIRouter(prefix="/genes", tags=["GeneHub"])
pfam_router = APIRouter(prefix="/genes/functions", tags=["PfamSearch"])
interval_router = APIRouter(prefix="/genes/functions", tags=["IntervalTool"])


# ---------------------------------------------------------------------------
# KnownGene (curated cloned-gene list) helpers — data version v2056
# ---------------------------------------------------------------------------
# The curated import appends 8 columns to
# `cloned_gene_db.cloned_gene_tbl`: reference_genome_id, protein_family,
# validation_method, research_strategy, functional_category, species_primary,
# publication_years, chromosome (see docs/known_genes/backend_investigation.md
# §4.2).  Every curated row has reference_genome_id set; legacy rows (pre-v2056
# data or CGI-era submissions) have NULL there.  That single flag drives both
# the "keep literal '#'" normalization fix (§2.4/附录B) and the fallbacks that
# keep the endpoints working on old data before the import runs.

_KNOWN_SUMMARY_COLUMNS = (
    "clone_id, gene_id, gene_name, chrom_pos, gene_phenotype, gene_species, "
    "publication_year, paper_doi, reference_genome_id, species_primary, "
    "chromosome, functional_category, research_strategy, publication_years"
)

_KNOWN_DETAIL_COLUMNS = _KNOWN_SUMMARY_COLUMNS + (
    ", paper_title, key_result, function_description, cloning_method, "
    "cloning_method_description, author, author_mail, submission_date, "
    "protein_family, validation_method"
)

#: `/known/search` field whitelist: public field name -> DB columns to LIKE.
#: Only these names ever reach the SQL string, so the parameter cannot inject.
_KNOWN_SEARCH_FIELDS: dict[str, tuple[str, ...]] = {
    "all": (
        "gene_id",
        "gene_name",
        "reference_genome_id",
        "chrom_pos",
        "gene_phenotype",
        "gene_species",
        "species_primary",
        "paper_doi",
        "function_description",
        "cloning_method",
        "paper_title",
        "protein_family",
        "validation_method",
        "functional_category",
        "research_strategy",
    ),
    "gene_id": ("gene_id",),
    "gene_name": ("gene_name",),
    "reference_genome_id": ("reference_genome_id",),
    "chrom_pos": ("chrom_pos",),
    "phenotype": ("gene_phenotype",),
    "species": ("gene_species", "species_primary"),
    "doi": ("paper_doi",),
    "protein_family": ("protein_family",),
    "functional_category": ("functional_category",),
    "research_strategy": ("research_strategy",),
}

_KNOWN_CHROMOSOME_PATTERN = re.compile(r"^[0-9]{1,2}[A-Z]{0,2}$")
_KNOWN_WHEAT_CHROMOSOMES = frozenset(
    f"{group}{sub}" for group in range(1, 8) for sub in ("A", "B", "D")
)
#: Default list ordering for KnownGene list endpoints: genes cloned by
#: map-based cloning (positional cloning) first (user request 2026-10-28),
#: then the historical clone_id order. MySQL 5.7 accepts the boolean expression
#: in ORDER BY; the column is always populated for curated rows.
_KNOWN_LIST_ORDER = "(cloning_method = 'Map-based cloning') DESC, clone_id"

_KNOWN_TAG_MAX_CHARS = 80
_KNOWN_TAG_LIMIT = 100
#: Canonical case for disease/abbreviation tokens that commonly appear in
#: parentheses inside phenotype free text (e.g. "(Pm)" / "(Yr)"); the
#: phenotype tag chart should never show "(pm" / "(yr".
_PHENOTYPE_ABBREVIATIONS = {
    "yr": "Yr", "lr": "Lr", "sr": "Sr", "pm": "Pm", "fhb": "FHB", "fcr": "FCR",
    "snb": "SNB", "stb": "STB", "se": "SE", "wymv": "WYMV", "bydv": "BYDV",
}
#: Parenthetical provenance qualifiers such as "(family-level; not copy-specific)"
#: describe evidence scope, not a phenotype trait; strip them from stats tags.
_PHENOTYPE_PROVENANCE_RE = re.compile(
    r"\s*\([^()]*?(?:family-level|copy-specific)[^()]*\)", re.IGNORECASE
)
#: Disease abbreviations (Pm/Yr/...) are resistance-gene designations; on a
#: *susceptibility* tag they read wrong (user request 2026-10-28), so drop the
#: abbreviation parenthetical there, e.g. "powdery mildew susceptibility (Pm)".
_PHENOTYPE_ABBR_PAREN_RE = re.compile(
    r"\(\s*(?:yr|lr|sr|pm|fhb|fcr|snb|stb|se|wymv|bydv)\s*\)", re.IGNORECASE
)


def _split_phenotype_tags(value: object) -> list[str]:
    """Split a phenotype string into display tags on top-level semicolons only.

    Phenotype free text frequently contains semicolons inside parentheses
    (e.g. ``Male fertility (...)(family-level; not copy-specific)``); a naive
    ``str.split(";")`` produced fragments such as ``not copy-specific)`` or
    ``powdery mildew resistance (pm`` in the stats chart.  Track parenthesis
    depth so only separators outside ``(...)`` split, strip parenthetical
    provenance qualifiers (``(family-level; not copy-specific)``) that are not
    phenotype traits, then normalize the canonical case of common disease
    abbreviations (Pm, Yr, Lr, ...).
    """

    text = str(value or "")
    pieces: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
        if ch == ";" and depth == 0:
            pieces.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    pieces.append("".join(buf))

    tags: list[str] = []
    for piece in pieces:
        tag = piece.strip().lower()
        if not tag:
            continue
        tag = _PHENOTYPE_PROVENANCE_RE.sub("", tag)
        if "susceptib" in tag:
            tag = _PHENOTYPE_ABBR_PAREN_RE.sub("", tag)
        tag = re.sub(r"\s+", " ", tag).strip(" ;,")
        if not tag or "copy-specific" in tag or "family-level" in tag:
            continue
        tag = re.sub(
            r"\((yr|lr|sr|pm|fhb|fcr|snb|stb|se|wymv|bydv)\b",
            lambda m: "(" + _PHENOTYPE_ABBREVIATIONS[m.group(1)],
            tag,
        )
        if len(tag) > _KNOWN_TAG_MAX_CHARS:
            continue
        tags.append(tag)
    return tags
_KNOWN_YEAR_PATTERN = re.compile(r"^\d{4}$")

#: NCBI common names for the controlled `species_primary` tokens (v2056).
#: Mirrors profile_v2055.json::species.common_name_map; the DB has no
#: common-name column, so the display mapping lives here.
_KNOWN_SPECIES_COMMON_NAMES: dict[str, str] = {
    "Triticum aestivum": "bread wheat",
    "Hordeum vulgare": "barley",
    "Triticum turgidum": "rivet wheat",
    "Triticum turgidum subsp. durum": "durum wheat",
    "Triticum turgidum subsp. dicoccoides": "wild emmer wheat",
    "Triticum monococcum": "einkorn wheat",
    "Triticum polonicum": "Polish wheat",
    "Secale cereale": "rye",
    "x Triticosecale": "triticale",
    "Agropyron cristatum": "crested wheatgrass",
    "Hordeum vulgare subsp. spontaneum": "wild barley",
}


def _known_row_is_legacy(row: dict) -> bool:
    """True for pre-v2056 / CGI-era rows (the ones needing legacy escaping)."""

    return row.get("reference_genome_id") is None


def _optional_text(value: object) -> str | None:
    """Return a stripped string or None (curated columns are raw, not escaped)."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _escape_like(term: str) -> str:
    """Escape LIKE wildcards so a user term is matched literally."""

    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _derive_genome_ref(chrom_pos: object) -> str | None:
    """Derive the reference-assembly label from the chrom_pos prefix.

    v2056 stores chrom_pos as ``<assembly> <chrom>:<start>-<end>Mb`` (e.g.
    ``Refv1.0 chr3A:646.127-646.132Mb`` / ``AetTA1675 2D:2.33-2.45Mb``), so the
    first token is the assembly label.  Legacy rows hold bare chromosome labels
    (``5A``) or unparsable free text; those return None instead of a bogus
    assembly name.  Matches the fixture generator (extract.py::derive_genome_ref).
    """

    text = str(chrom_pos or "").strip()
    if not text:
        return None
    token = text.split()[0]
    if not token or token.isdigit():
        return None
    if re.fullmatch(r"(?:chr)?[0-9]{1,2}[A-Za-z]{0,2}", token, flags=re.IGNORECASE):
        return None
    return token.rstrip(".,;") or None


def _derive_phenotype_brief(phenotype: object, limit: int = 500) -> str | None:
    """Short phenotype label: text before the first ``:`` else first ``;`` part.

    Mirrors extract.py::derive_phenotype_brief so the list card always shows a
    concise trait name instead of the full mechanism sentence.
    """

    text = str(phenotype or "").strip()
    if not text:
        return None
    brief = text.split(":", 1)[0].strip() if ":" in text else text.split(";")[0].strip()
    brief = brief.strip()
    return brief[:limit] or None


def _row_to_known_summary(row: dict) -> KnownGeneSummary:
    """Map one cloned_gene_tbl row to the `/known/all` summary payload."""

    legacy = _known_row_is_legacy(row)
    phenotype = normalize_known_text(row.get("gene_phenotype"), legacy)
    publication_years = split_legacy_multi_value(row.get("publication_years"))
    if not publication_years:
        # Legacy/CGI rows predate the multi-value column: expose the scalar
        # publication_year as a single-element list (same fallback as detail).
        scalar_year = _optional_text(row.get("publication_year"))
        publication_years = [scalar_year] if scalar_year else []
    return KnownGeneSummary(
        clone_id=row.get("clone_id", row.get("id")),
        gene_id=str(row.get("gene_id") or ""),
        gene_name=normalize_known_text(row.get("gene_name"), legacy),
        chrom_pos=normalize_known_text(row.get("chrom_pos"), legacy),
        phenotype=phenotype,
        species=normalize_known_text(row.get("gene_species"), legacy),
        publication_year=_optional_text(row.get("publication_year")),
        dois=split_legacy_multi_value(row.get("paper_doi")),
        reference_genome_id=_optional_text(row.get("reference_genome_id")),
        species_primary=_optional_text(row.get("species_primary")),
        chromosome=_optional_text(row.get("chromosome")),
        genome_ref=_derive_genome_ref(row.get("chrom_pos")),
        phenotype_brief=_derive_phenotype_brief(phenotype),
        functional_category=_optional_text(row.get("functional_category")),
        research_strategy=_optional_text(row.get("research_strategy")),
        publication_years=publication_years,
    )


_REF_META_PATH = Path(__file__).resolve().parents[3] / "app/services/data/known_gene_reference_meta.json"


@lru_cache(maxsize=1)
def _reference_meta() -> dict:
    """Load the Crossref/PubMed-enriched reference metadata cache (once)."""
    try:
        return json.loads(_REF_META_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"doi": {}, "title": {}}


def _ref_norm_title(text: object) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", str(text or ""))).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _reference_meta_for(doi: str | None, title: str | None) -> dict | None:
    meta = _reference_meta()
    if doi:
        hit = (meta.get("doi") or {}).get(doi.strip().lower())
        if hit:
            return hit
    if title:
        hit = (meta.get("title") or {}).get(_ref_norm_title(title))
        if hit:
            return hit
    return None


def _build_known_references(row: dict) -> list[DOIReference]:
    """Build the positionally-aligned ``references[]`` list.

    ``paper_title``/``paper_doi``/``publication_years`` are stored as
    ``###``-joined lists where the k-th title belongs to the k-th DOI/year
    (CGI-era convention).  Up to v2055 a few rows had unequal list lengths, so
    the lists are aligned by index, padded with None and built to
    ``n = max(len(title), len(doi), len(year))``.  A single year is replicated
    across references (two papers in the same year); a DOI-less / year-less
    slot keeps ``None`` (``DOIReference.doi`` is nullable by design).
    """

    titles = split_aligned_multi_value(row.get("paper_title"))
    dois = split_aligned_multi_value(row.get("paper_doi"))
    years = split_aligned_multi_value(row.get("publication_years"))
    if not any(years):
        # Legacy/CGI rows have no multi-value year column: fall back to the
        # scalar publication_year so references still show a year.
        scalar_year = _optional_text(row.get("publication_year"))
        years = [scalar_year] if scalar_year else []
    count = max(len(titles), len(dois), len(years))
    if count == 0:
        return []
    known_years = [year for year in years if year]
    if len(known_years) == 1 and count > 1:
        years = [known_years[0]] * count

    references: list[DOIReference] = []
    for index in range(count):
        doi = (dois[index] or None) if index < len(dois) else None
        title = (titles[index] or None) if index < len(titles) else None
        year_text = (years[index] or None) if index < len(years) else None
        if doi is None and title is None and year_text is None:
            continue
        year: int | str | None = year_text
        if year_text is not None and year_text.isdigit():
            year = int(year_text)
        meta = _reference_meta_for(doi, title)
        if meta:
            if meta.get("year") and year is None:
                year = meta["year"]
            if meta.get("title") and not title:
                title = meta["title"]
        references.append(
            DOIReference(
                doi=doi,
                title=title,
                year=year,
                authors=(meta or {}).get("authors") or None,
                journal=(meta or {}).get("journal") or None,
                pmid=(meta or {}).get("pmid") or None,
            )
        )
    return references


def _split_semicolon_values(value: object) -> list[str]:
    """Split a ``;``-separated tag field, trimming and dropping empty tokens."""

    if value is None:
        return []
    return [part.strip() for part in str(value).split(";") if part.strip()]


def _row_to_known_detail(row: dict) -> KnownGeneDetail:
    """Map one cloned_gene_tbl row to the `/known/{gene_id}` detail payload."""

    legacy = _known_row_is_legacy(row)
    phenotype = normalize_known_text(row.get("gene_phenotype"), legacy)
    publication_years: list[int | str] = []
    for token in split_aligned_multi_value(row.get("publication_years")):
        if not token:
            continue
        publication_years.append(int(token) if token.isdigit() else token)
    if not publication_years:
        # Legacy/CGI rows: fall back to the scalar year (same as references[]).
        scalar_year = _optional_text(row.get("publication_year"))
        if scalar_year:
            publication_years = [int(scalar_year) if scalar_year.isdigit() else scalar_year]
    return KnownGeneDetail(
        clone_id=row.get("clone_id", row.get("id", 0)),
        gene_id=str(row.get("gene_id") or ""),
        gene_name=normalize_known_text(row.get("gene_name"), legacy),
        chrom_pos=normalize_known_text(row.get("chrom_pos"), legacy),
        phenotype=phenotype,
        species=normalize_known_text(row.get("gene_species"), legacy),
        paper_title=split_legacy_multi_value(row.get("paper_title")),
        references=_build_known_references(row),
        key_result=split_legacy_multi_value(row.get("key_result")),
        publication_year=row.get("publication_year"),
        function_description=normalize_known_text(row.get("function_description"), legacy) or None,
        cloning_method=normalize_known_text(row.get("cloning_method"), legacy) or None,
        cloning_method_description=normalize_known_text(row.get("cloning_method_description"), legacy) or None,
        author=normalize_known_text(row.get("author"), legacy) or None,
        author_mail=normalize_known_text(row.get("author_mail"), legacy) or None,
        submission_date=row.get("submission_date"),
        reference_genome_id=_optional_text(row.get("reference_genome_id")),
        protein_family=_optional_text(row.get("protein_family")),
        validation_method=_optional_text(row.get("validation_method")),
        validation_methods=_split_semicolon_values(row.get("validation_method")),
        research_strategy=_optional_text(row.get("research_strategy")),
        functional_category=_optional_text(row.get("functional_category")),
        species_primary=_optional_text(row.get("species_primary")),
        chromosome=_optional_text(row.get("chromosome")),
        genome_ref=_derive_genome_ref(row.get("chrom_pos")),
        phenotype_brief=_derive_phenotype_brief(phenotype),
        publication_years=publication_years,
    )


def _normalize_chromosome(value: str) -> str:
    """Normalize a chromosome path parameter (``3h``/``chr3H`` -> ``3H``)."""

    text = (value or "").strip()
    if text[:3].lower() == "chr":
        text = text[3:]
    text = text.strip().upper()
    if not _KNOWN_CHROMOSOME_PATTERN.match(text):
        raise ValidationFailure(
            f"Invalid chromosome: {value!r}. Expected formats like 5A, chr5A, 3H or 54."
        )
    return text


def _chromosome_match_tokens(token: str) -> list[str]:
    """DB `chromosome` values that represent ``token``.

    v2056 keeps the explicit prefix for numeric-only labels (``chr51`` /
    ``chr54`` for T. ponticum), so both spellings must be queried.
    """

    tokens = [token]
    if token.isdigit():
        tokens.append(f"chr{token}")
    return tokens


def _chromosome_fallback_regex(token: str) -> str:
    """POSIX-ERE pattern matching ``token`` in legacy ``chrom_pos`` free text.

    Used only for rows whose `chromosome` column is NULL (pre-v2056 data).
    The token is already validated (`^[0-9]{1,2}[A-Z]{0,2}$`), so there is no
    injection surface.  MySQL 5.7 REGEXP is case-insensitive for the utf8
    collation, so lowercase legacy labels match the upper-case token.
    """

    if token.isdigit():
        # Require the explicit 'chr' prefix (or a standalone label) so we do
        # not match a coordinate such as "51.2Mb" in an unrelated position.
        return (
            rf"(^|[^0-9A-Za-z])chr{token}([^0-9A-Za-z]|$)"
            rf"|^(chr)?{token}([^0-9A-Za-z]|$)"
        )
    return rf"(^|[^0-9A-Za-z])(chr)?{token}([^0-9A-Za-z]|$)"


def _build_known_stats(
    *,
    total: int,
    species_rows: list[dict],
    species_raw_count: int,
    chromosome_rows: list[dict],
    category_rows: list[dict],
    strategy_rows: list[dict],
    light_rows: list[dict],
) -> dict:
    """Aggregate the `/known/stats` payload from SQL GROUP BY results + rows.

    The four controlled dimensions come straight from SQL GROUP BY; the
    free-text aggregations (phenotype tags, publication years, reference
    counts, notes) are computed here in Python, mirroring the fixture
    generator (scripts/known_genes_v2055/extract.py) rule by rule.
    """

    phenotype_tags: Counter[str] = Counter()
    rows_without_tags = 0
    year_counter: Counter[int] = Counter()
    multi_year_rows = 0
    multi_species_rows = 0
    reference_entries = 0
    unique_dois: set[str] = set()

    for row in light_rows:
        # --- phenotype tags: paren-aware ';' split -> trim/lower/abbrev case ->
        #     row dedupe -> count
        deduped_tags = list(dict.fromkeys(_split_phenotype_tags(row.get("gene_phenotype"))))
        if deduped_tags:
            phenotype_tags.update(deduped_tags)
        else:
            rows_without_tags += 1

        # --- species notes
        species_text = str(row.get("gene_species") or "")
        if len([part for part in species_text.split(";") if part.strip()]) > 1:
            multi_species_rows += 1

        # --- publication years: count each token of a multi-year row
        years = [
            token
            for token in split_aligned_multi_value(row.get("publication_years"))
            if token
        ]
        if len(years) > 1:
            multi_year_rows += 1
        if not years:
            scalar_year = _optional_text(row.get("publication_year"))
            years = [scalar_year] if scalar_year else []
        for token in years:
            if _KNOWN_YEAR_PATTERN.match(token):
                year_counter[int(token)] += 1

        # --- references: entries = max(#DOIs, #years, 1) per row
        dois = [
            token
            for token in split_aligned_multi_value(row.get("paper_doi"))
            if token
        ]
        unique_dois.update(dois)
        reference_entries += max(len(dois), len(years), 1)

    chromosome_items = [
        {
            "label": row["label"],
            "count": int(row["count"]),
            "group": "wheat" if row["label"] in _KNOWN_WHEAT_CHROMOSOMES else "other",
        }
        for row in chromosome_rows
    ]
    covered_wheat_chromosomes = len(
        _KNOWN_WHEAT_CHROMOSOMES & {item["label"] for item in chromosome_items}
    )

    return {
        "total": int(total),
        "species": [
            {
                "name": row["name"],
                "count": int(row["count"]),
                "raw_forms": int(row.get("raw_forms") or 0),
                "common_name": _KNOWN_SPECIES_COMMON_NAMES.get(row["name"]),
            }
            for row in species_rows
        ],
        "species_raw_count": int(species_raw_count),
        "chromosomes": chromosome_items,
        "functional_category": [
            {"name": row["name"], "count": int(row["count"])} for row in category_rows
        ],
        "research_strategy": [
            {"name": row["name"], "count": int(row["count"])} for row in strategy_rows
        ],
        "phenotype_tags": [
            {"tag": tag, "count": count}
            for tag, count in phenotype_tags.most_common(_KNOWN_TAG_LIMIT)
        ],
        "phenotype_tag_distinct": len(phenotype_tags),
        "publication_year": [
            {"year": year, "count": count}
            for year, count in sorted(year_counter.items())
        ],
        "references": {"entries": reference_entries, "unique_dois": len(unique_dois)},
        "notes": {
            "multi_year_rows": multi_year_rows,
            "multi_species_rows": multi_species_rows,
            "rows_without_tags": rows_without_tags,
            "wheat_chromosomes_covered": covered_wheat_chromosomes,
        },
    }


@router.get("/known/search")
def search_known_genes(
    search: str = Query(..., alias="searchid", description="Search keyword (required, partial match supported)"),
    field: str = Query(
        "all",
        description=(
            "Search field whitelist: all | gene_id | gene_name | reference_genome_id | "
            "phenotype | species | doi | protein_family | functional_category | "
            "chrom_pos | research_strategy; unknown values return 400"
        ),
    ),
    limit: int | None = Query(
        None, ge=1, le=5000, description="Optional cap on returned rows (1-5000); omit = all rows (legacy behavior)"
    ),
    offset: int = Query(0, ge=0, description="Optional pagination offset; only effective together with limit"),
) -> dict:
    """Search cloned genes with known functions (v2056: field-targeted search + pagination + multi-year fix).

    Purpose:
        Fuzzy-search the curated cloned-gene library of known-function genes using a
        user-supplied keyword. The default field=all covers the 9 legacy fields plus
        the 6 fields added in v2056, and returns a summary list structurally identical
        to /known/all (including dois / publication_years, etc.).
        v2056 also fixes: the SQL now selects publication_year (this field used to be
        always null).

    Usage:
        GET /api/genes/known/search?searchid=<keyword>[&field=all][&limit=50&offset=0]
        - searchid: required, search keyword (LIKE wildcards % / _ are escaped to literals)
        - field: optional, default all; whitelist:
          all | gene_id | gene_name | reference_genome_id | phenotype | species |
          doi | protein_family | functional_category | chrom_pos | research_strategy
          unknown values return 400
        - limit: optional 1-5000; omit = all rows (legacy behavior)
        - offset: optional >=0, default 0; only effective together with limit
        total: without pagination = number of rows returned (legacy behavior); with pagination = total number of matches

    Example:
        Request:
          curl -X GET "http://localhost:8000/api/genes/known/search?searchid=TaCRT"

        Response:
          {
            "success": true, "message": "ok", "data": {
              "query": "TaCRT",
              "total": 1,
              "records": [{
                "clone_id": 5, "gene_id": "EF452301", "gene_name": "TaCRT-A/TaCRT3-A",
                "chrom_pos": "Refv1.0 chr3A:646.127-646.132Mb",
                "phenotype": "Drought tolerance; Powdery mildew resistance (Bgt)",
                "species": "Triticum aestivum (bread wheat)",
                "publication_year": "2008",
                "dois": ["10.1093/jxb/erm369", "10.1094/phyto-08-23-0276-r"],
                "reference_genome_id": "TraesCS3A03G0936700",
                "species_primary": "Triticum aestivum",
                "chromosome": "3A", "genome_ref": "Refv1.0",
                "phenotype_brief": "Drought tolerance",
                "functional_category": "Biotic Stress",
                "research_strategy": "Reverse genetics",
                "publication_years": ["2008", "2024"]
              }]
            }
          }

        Error example:
          ?searchid=x&field=bogus -> 400 Unsupported search field
          ?searchid=%20%20        -> 400 searchid is required
    """

    term = search.strip().replace('"', "")
    if not term:
        raise ValidationFailure("searchid is required")
    if field not in _KNOWN_SEARCH_FIELDS:
        raise ValidationFailure(
            f"Unsupported search field: {field!r}. "
            "Valid fields: " + ", ".join(_KNOWN_SEARCH_FIELDS) + "."
        )

    columns = _KNOWN_SEARCH_FIELDS[field]
    pattern = f"%{_escape_like(term)}%"
    where_sql = " OR ".join(f"{column} LIKE %s" for column in columns)
    params: tuple = tuple(pattern for _ in columns)

    sql = (
        f"SELECT {_KNOWN_SUMMARY_COLUMNS} FROM cloned_gene_tbl "
        f"WHERE {where_sql} ORDER BY {_KNOWN_LIST_ORDER}"
    )
    count_sql = f"SELECT COUNT(*) AS total FROM cloned_gene_tbl WHERE {where_sql}"
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"

    with mysql_cursor(settings.DB_CLONED_GENE) as cursor:
        cursor.execute(sql, params + ((limit, offset) if limit is not None else ()))
        rows = cursor.fetchall()
        if limit is None:
            total = len(rows)
        else:
            cursor.execute(count_sql, params)
            total = int((cursor.fetchone() or {}).get("total") or 0)

    records = [_row_to_known_summary(row).model_dump() for row in rows]
    return ok({"query": term, "total": total, "records": records})

@router.get("/known/all")
def list_known_genes(
    limit: int | None = Query(
        None, ge=1, le=5000, description="Optional cap on returned rows (1-5000); omit = all rows (legacy behavior)"
    ),
    offset: int = Query(0, ge=0, description="Optional pagination offset; only effective together with limit"),
) -> dict:
    """List all cloned genes with known functions (v2056 summary fields).

    Purpose:
        Query summary records for all known-function genes from cloned_gene_tbl.
        The 6 legacy keys (clone_id / gene_id / gene_name / chrom_pos / phenotype /
        species) are unchanged; v2056 adds reference_genome_id, species_primary,
        chromosome, genome_ref, phenotype_brief, functional_category,
        research_strategy, dois[] and publication_years[].
        total semantics: when limit is omitted = number of rows returned (legacy
        behavior); with limit = total row count of the table, records = current page.

    Usage:
        GET /api/genes/known/all[?limit=50&offset=0]
        - limit: optional 1-5000; omit = all rows (legacy behavior, about 1.1 MB, about 190 KB after gzip)
        - offset: optional >=0, default 0; only effective together with limit

    Example:
        curl "http://localhost:8000/api/genes/known/all?limit=2"

        Response:
        {
          "total": 1420,
          "records": [{
            "clone_id": 528, "gene_id": "EF452301",
            "gene_name": "TaCRT-A/TaCRT3-A",
            "chrom_pos": "Refv1.0 chr3A:646.127-646.132Mb",
            "phenotype": "Drought tolerance; Powdery mildew resistance (Bgt)",
            "species": "Triticum aestivum (bread wheat)",
            "publication_year": "2008",
            "dois": ["10.1093/jxb/erm369", "10.1094/phyto-08-23-0276-r"],
            "reference_genome_id": "TraesCS3A03G0936700",
            "species_primary": "Triticum aestivum", "chromosome": "3A",
            "genome_ref": "Refv1.0", "phenotype_brief": "Drought tolerance",
            "functional_category": "Biotic Stress",
            "research_strategy": "Reverse genetics",
            "publication_years": ["2008", "2024"]
          }]
        }
    """

    sql = f"SELECT {_KNOWN_SUMMARY_COLUMNS} FROM cloned_gene_tbl ORDER BY {_KNOWN_LIST_ORDER}"
    params: tuple = ()
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params = (limit, offset)

    with mysql_cursor(settings.DB_CLONED_GENE) as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        if limit is None:
            total = len(rows)
        else:
            cursor.execute("SELECT COUNT(*) AS total FROM cloned_gene_tbl")
            total = int((cursor.fetchone() or {}).get("total") or 0)

    records = [_row_to_known_summary(row).model_dump() for row in rows]
    return ok({"total": total, "records": records})


@router.get("/known/by-chromosome/{chromosome}")
def list_known_genes_on_chromosome(
    chromosome: str,
) -> dict:
    """List all cloned genes with known functions on a given chromosome.

    Purpose:
        Chromosome names are case-insensitive and tolerate a chr prefix
        (5A / chr5A / 3h / 54 / chr54). v2056 first matches the normalized
        chromosome column (the new chrom_pos is free-form
        "<reference genome> chr...", so the old LIKE '5A%' matched 0 new rows);
        rows not migrated / CGI-era submissions (chromosome is NULL) fall back to
        a chrom_pos regex match. Illegal chromosome names return 400. Returned
        records are structurally identical to /known/all.

    Usage:
        GET /api/genes/known/by-chromosome/{chromosome}
        - chromosome: chromosome label, e.g. 5A, chr5A, 3H, 1R, 54, chr54

    Example:
        curl "http://localhost:8000/api/genes/known/by-chromosome/chr7B"

        Response:
        {
          "success": true, "data": {
            "total": 60,
            "chromosome": "7B",
            "records": [ ... same records as /known/all ... ]
          }
        }

        Error example:
          /api/genes/known/by-chromosome/XX -> 400 Invalid chromosome
    """

    token = _normalize_chromosome(chromosome)
    match_tokens = _chromosome_match_tokens(token)
    placeholders = ", ".join(["%s"] * len(match_tokens))
    sql = (
        f"SELECT {_KNOWN_SUMMARY_COLUMNS} FROM cloned_gene_tbl "
        f"WHERE chromosome IN ({placeholders}) "
        f"OR (chromosome IS NULL AND chrom_pos REGEXP %s) "
        f"ORDER BY {_KNOWN_LIST_ORDER}"
    )
    params = tuple(match_tokens) + (_chromosome_fallback_regex(token),)

    with mysql_cursor(settings.DB_CLONED_GENE) as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    records = [_row_to_known_summary(row).model_dump() for row in rows]
    return ok({"total": len(records), "chromosome": token, "records": records})


@router.get("/known/stats")
def get_known_gene_stats() -> dict:
    """Statistical aggregates for the known-function cloned-gene library (for the Stats tab, replacing client-side aggregation).

    Purpose:
        Server-side aggregation of the v2056 dataset: total count, normalized
        species distribution (with raw_forms and the NCBI common name),
        chromosome distribution (38 entries, group=wheat|other), functional
        categories, research strategies, top 100 phenotype tags, publication-year
        distribution (multi-valued entries counted once per token), reference /
        unique-DOI counts, and data-quality notes.
        The response is about 8-12 KB, replacing the client-side fetch of the full
        /known/all payload (about 1.1 MB) followed by aggregation.
        Implemented as 7 small table scans (4 GROUP BYs on controlled dimensions
        plus 1 light column query aggregated in Python); 1420 rows take < 50 ms per
        call, so no cache is added.

    Notes:
        This route must be registered before /known/{gene_id}; otherwise "stats"
        is treated as a gene_id, hits the detail route and returns 404.

    Usage:
        GET /api/genes/known/stats

    Example:
        curl "http://localhost:8000/api/genes/known/stats"

        Response (excerpt):
        {
          "success": true, "data": {
            "total": 1420,
            "species": [
              {"name": "Triticum aestivum", "count": 1260,
               "raw_forms": 229, "common_name": "bread wheat"},
              {"name": "Hordeum vulgare", "count": 79,
               "raw_forms": 4, "common_name": "barley"}
            ],
            "species_raw_count": 296,
            "chromosomes": [
              {"label": "2B", "count": 96, "group": "wheat"},
              {"label": "3H", "count": 16, "group": "other"}
            ],
            "functional_category": [
              {"name": "Biotic Stress", "count": 415}, {"name": "Abiotic Stress", "count": 361}
            ],
            "research_strategy": [
              {"name": "Reverse genetics", "count": 1061}
            ],
            "phenotype_tags": [
              {"tag": "not determined", "count": 65}
            ],
            "phenotype_tag_distinct": 583,
            "publication_year": [{"year": 1998, "count": 2}],
            "references": {"entries": 1570, "unique_dois": 883},
            "notes": {
              "multi_year_rows": 130,
              "multi_species_rows": 263,
              "rows_without_tags": 541,
              "wheat_chromosomes_covered": 21
            }
          }
        }
    """

    with mysql_cursor(settings.DB_CLONED_GENE) as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM cloned_gene_tbl")
        total = int((cursor.fetchone() or {}).get("total") or 0)

        cursor.execute(
            """
            SELECT species_primary AS name, COUNT(*) AS `count`,
                   COUNT(DISTINCT gene_species) AS raw_forms,
                   MIN(clone_id) AS first_id
            FROM cloned_gene_tbl
            WHERE species_primary IS NOT NULL
            GROUP BY species_primary
            ORDER BY `count` DESC, first_id ASC
            """
        )
        species_rows = cursor.fetchall()

        cursor.execute("SELECT COUNT(DISTINCT gene_species) AS n FROM cloned_gene_tbl")
        species_raw_count = int((cursor.fetchone() or {}).get("n") or 0)

        cursor.execute(
            """
            SELECT chromosome AS label, COUNT(*) AS `count`
            FROM cloned_gene_tbl
            WHERE chromosome IS NOT NULL
            GROUP BY chromosome
            ORDER BY `count` DESC, label ASC
            """
        )
        chromosome_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT functional_category AS name, COUNT(*) AS `count`
            FROM cloned_gene_tbl
            WHERE functional_category IS NOT NULL
            GROUP BY functional_category
            ORDER BY `count` DESC, name ASC
            """
        )
        category_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT research_strategy AS name, COUNT(*) AS `count`
            FROM cloned_gene_tbl
            WHERE research_strategy IS NOT NULL
            GROUP BY research_strategy
            ORDER BY `count` DESC, name ASC
            """
        )
        strategy_rows = cursor.fetchall()

        # Free-text fields aggregated in Python (small table, ~1.5 MB max).
        cursor.execute(
            """
            SELECT gene_species, gene_phenotype, publication_years,
                   publication_year, paper_doi
            FROM cloned_gene_tbl
            ORDER BY clone_id
            """
        )
        light_rows = cursor.fetchall()

    payload = _build_known_stats(
        total=total,
        species_rows=species_rows,
        species_raw_count=species_raw_count,
        chromosome_rows=chromosome_rows,
        category_rows=category_rows,
        strategy_rows=strategy_rows,
        light_rows=light_rows,
    )
    return ok(payload)


@router.get("/known/{gene_id}")
def get_known_gene(gene_id: str) -> dict:
    """Get detailed information for a given cloned gene (v2056 structured fields + positionally aligned references).

    Purpose:
        Look up the full record of a cloned gene by gene ID. Numeric IDs still
        query by clone_id (legacy semantics, detail page URL ?id=<clone_id>);
        non-numeric values match gene_id / gene_name exactly (legacy semantics).
        All legacy response keys are kept; v2056 adds reference_genome_id,
        protein_family, validation_method, validation_methods[],
        research_strategy, functional_category, species_primary, chromosome,
        genome_ref, phenotype_brief, publication_years[].
        references[] is built positionally from the paper_title / paper_doi /
        publication_years columns aligned on `###`, each entry {doi, title, year};
        missing positions are null (v2056 has one row with 4 titles / 3 DOIs, so
        the 4th entry has a title only and doi may be null).
        key_result keeps the legacy array semantics (`###` split; a single segment
        in new data -> a 1-element array).
        Normalization: new-data rows with a non-null reference_genome_id keep a
        literal `#`; legacy rows keep the old # -> ' escape behavior.

    Usage:
        GET /api/genes/known/{gene_id}
        - gene_id: path parameter; a number = clone_id, e.g. 12; or a gene ID/name,
          e.g. TraesCS3A03G0936700

    Example:
        Request:
          curl -X GET "http://localhost:8000/api/genes/known/5"

        Response (excerpt):
          {
            "success": true, "data": {
              "clone_id": 5, "gene_id": "EF452301",
              "gene_name": "TaCRT-A/TaCRT3-A",
              "chrom_pos": "Refv1.0 chr3A:646.127-646.132Mb",
              "phenotype": "Drought tolerance; Powdery mildew resistance (Bgt)",
              "species": "Triticum aestivum (bread wheat)",
              "paper_title": ["...", "..."],
              "references": [
                {"doi": "10.1093/jxb/erm369", "title": "...", "year": 2008,
                 "authors": ["Family A", "Family B"], "journal": "Journal of Experimental Botany", "pmid": null},
                {"doi": "10.1094/phyto-08-23-0276-r", "title": "...", "year": 2024,
                 "authors": ["..."], "journal": "Phytopathology", "pmid": null}
              ],
              "key_result": ["..."],
              "publication_year": 2008,
              "function_description": "...",
              "cloning_method": "Homology-based cloning; Functional cloning",
              "cloning_method_description": "...",
              "author": "WheatOmics curation",
              "author_mail": "shengweima@icloud.com",
              "submission_date": "2026-10-28",
              "reference_genome_id": "TraesCS3A03G0936700",
              "protein_family": "Calreticulin (CRT3) family; calcium-binding ER chaperone",
              "validation_method": "Expression analysis; Overexpression; VIGS",
              "validation_methods": ["Expression analysis", "Overexpression", "VIGS"],
              "research_strategy": "Reverse genetics",
              "functional_category": "Biotic Stress",
              "species_primary": "Triticum aestivum",
              "chromosome": "3A", "genome_ref": "Refv1.0",
              "phenotype_brief": "Drought tolerance",
              "publication_years": [2008, 2024]
            }
          }
    """

    gene_id = ensure_gene_like(gene_id)
    with mysql_cursor(settings.DB_CLONED_GENE) as cursor:
        # Try clone_id first (numeric path-param), then fall back to
        # gene_id / gene_name. The URL detail page prefers clone_id
        # because gene_id can contain slashes, spaces, or DOI strings
        # (e.g. "MT783929/MT783930") that complicate URL encoding.
        if gene_id.isdigit():
            cursor.execute(
                f"SELECT {_KNOWN_DETAIL_COLUMNS} FROM cloned_gene_tbl "
                "WHERE clone_id = %s LIMIT 1",
                (int(gene_id),),
            )
        else:
            cursor.execute(
                f"SELECT {_KNOWN_DETAIL_COLUMNS} FROM cloned_gene_tbl "
                "WHERE gene_id = %s OR gene_name = %s ORDER BY clone_id LIMIT 1",
                (gene_id, gene_id),
            )
        row = cursor.fetchone()

    if not row:
        raise ResourceNotFound(f"Known gene not found: {gene_id}")

    detail = _row_to_known_detail(row)
    return ok(detail.model_dump())



@genehub_router.get("/detail/{gene_id}")
def get_gene_detail(gene_id: str) -> dict:
    """Get normalized detailed information for a gene.

    Purpose:
        Look up GenePageIWGSCv1_table by gene ID (IWGSC v1/v2/v3 versions all
        supported) and return the gene description, chromosome location, protein
        length, molecular weight, isoelectric point, functional annotations, etc.,
        plus a JBrowse genome-browser link and an Ensembl external link.

    Usage:
        GET /api/genes/detail/{gene_id}
        - gene_id: path parameter, any of v1 (TraesCS5A02G391700), v2 (TraesCS5A02G391700.1), v3 (TraesCS5A03G1158600)

    Example:
        Request:
          curl -X GET "http://localhost:8000/api/genes/detail/TraesCS5A02G391700"

        Response:
          {
            "success": true,
            "data": {
              "query_gene": "TraesCS5A02G391700",
              "gene_ids": ["TraesCS5A02G391700", "TraesCS5A01G391700", "TraesCS5A03G1158600"],
              "description": "MADS-box transcription factor",
              "genome": "A",
              "chromosome": "chr5A",
              "start": 587123456,
              "end": 587125000,
              "strand": "+",
              "protein_length": "240",
              "molecular_weight": "27.5",
              "isoelectric_point": "6.2",
              "functions": ["vernalization response", "flowering time regulation"],
              "jbrowse_links": { "structure_center": "http://..." },
              "external_links": { "ensembl": "https://ensembl.gramene.org/..." }
            }
          }
    """

    gene_id = ensure_gene_like(gene_id)
    with mysql_cursor(settings.DB_GENEHUB) as cursor:
        cursor.execute(
            """
            SELECT * FROM GenePageIWGSCv1_table
            WHERE GeneIDv2=%s OR GeneIDv1=%s OR GeneIDv3=%s
            """,
            (gene_id, gene_id, gene_id),
        )
        row = cursor.fetchone()

    if not row:
        raise ResourceNotFound(f"Gene detail not found: {gene_id}")

    gene_v2 = str(row.get("GeneIDv2", ""))
    chromosome = str(row.get("Chrom", row.get("Chromosome", "")))
    genome = str(row.get("Genome", row.get("SubGenome", "")))
    start = int(row.get("Start", row.get("Start1", 0)) or 0)
    end = int(row.get("End", row.get("End1", 0)) or 0)
    loc = f"{chromosome}:{max(start - 200, 1)}..{end + 200}" if chromosome and start and end else ""

    detail = GeneDetailResponse(
        query_gene=gene_id,
        gene_ids=[value for value in [row.get("GeneIDv2"), row.get("GeneIDv1"), row.get("GeneIDv3")] if value],
        description=normalize_text(row.get("Description")) or normalize_text(row.get("description")) or None,
        genome=genome or None,
        chromosome=chromosome or None,
        start=start or None,
        end=end or None,
        strand=normalize_text(row.get("Strand")) or None,
        protein_length=str(row.get("Protein_length", row.get("ProteinLength", "")) or "") or None,
        molecular_weight=str(row.get("MolecularWeight", row.get("Molecular_Weight", "")) or "") or None,
        isoelectric_point=str(row.get("IsoelectricPoint", row.get("Isoelectric_points", "")) or "") or None,
        functions=[
            item
            for item in [
                normalize_text(row.get("Function")),
                normalize_text(row.get("Function2")),
                normalize_text(row.get("Function3")),
            ]
            if item
        ],
        jbrowse_links={
            "structure_center": f"http://wheatomics.sdau.edu.cn/jbrowse-1.12.3-release/?data=Chinese_Spring1.0&loc={loc}&tracks=IWGSCv1.1_HC_LC&tracklist=0&nav=0&overview=0&fullviewlink=0"
            if loc
            else ""
        },
        external_links={
            "ensembl": f"https://ensembl.gramene.org/Triticum_aestivum/Gene/Summary?g={gene_v2}" if gene_v2 else "",
        },
    )

    # wheatPSP: phase-separation predictions for this gene (any transcript).
    # Normalize gene ids to the CS 02G form (strip numeric transcript suffix)
    # and match against wheat_psp.cs_gene_id. Never fails the gene detail —
    # on any error the field stays None.
    phase_sep = None
    try:
        candidates: list[str] = []
        for gid in detail.gene_ids or []:
            g2 = re.sub(r"\.\d+$", "", str(gid))
            if g2 and g2 not in candidates:
                candidates.append(g2)
        if candidates:
            with mysql_connection(settings.DB_WHEATPSP) as conn:
                with conn.cursor() as cur:
                    ph = ",".join(["%s"] * len(candidates))
                    cur.execute(
                        "SELECT seq_id, gene_id, cs_gene_id, ps_score, is_psp, "
                        "molphase_score, has_prd, plaac_llr, plaac_core_score, "
                        "plaac_papa_prop, plaac_papa_fi "
                        f"FROM wheat_psp WHERE cs_gene_id IN ({ph}) ORDER BY id",
                        candidates,
                    )
                    rows = cur.fetchall()
            if rows:
                phase_sep = {
                    "any_psp": bool(any(r.get("is_psp") for r in rows)),
                    "any_prd": bool(any(r.get("has_prd") for r in rows)),
                    "transcripts": rows,
                }
    except Exception:
        phase_sep = None
    detail.phase_separation = phase_sep

    return ok(detail.model_dump())

_NULL_CS02G = {"", "-", ".", "null", "none", "na", "n/a"}


def _clean_cs02g(value):
    """Normalize placeholder values in ChineseSpring02G to None."""
    text = normalize_text(value) or ""
    return None if text.strip().lower() in _NULL_CS02G else text


def _make_function_record(row, table):
    """Build a GeneFunctionRecord from a DB row, handling different table schemas."""
    # The IWGSC v1.0 (v2) tables only have Gene03G/Gene02G columns; every
    # other Genefunc_* table uses `Gene`. Match both the old
    # Genefunc_IWGSC03G_table name and the renamed
    # Genefunc_CS_IWGSC03G_table so this works after the rename.
    is_iwgsc_v2 = table in ("Genefunc_IWGSC03G_table", "Genefunc_CS_IWGSC03G_table")
    if is_iwgsc_v2:
        return GeneFunctionRecord(
            chromosome=str(row["Chrom"]),
            start_mb=round(float(row["Start1"]) / 1_000_000.0, 6),
            end_mb=round(float(row["End1"]) / 1_000_000.0, 6),
            gene_primary=str(row["Gene03G"]),
            gene_secondary=str(row["Gene02G"]),
            strand=normalize_text(row["Strand"]) or None,
            description=normalize_text(row.get("Description") or row.get("description") or "") or None,
            domain=normalize_text(row["Domain"]) or None,
            chinese_spring_02g=_clean_cs02g(row.get("ChineseSpring02G") or row.get("Gene02G")),
        )
    return GeneFunctionRecord(
        chromosome=str(row["Chrom"]),
        start_mb=round(float(row["Start1"]) / 1_000_000.0, 6),
        end_mb=round(float(row["End1"]) / 1_000_000.0, 6),
        gene_primary=str(row["Gene"]),
        strand=normalize_text(row["Strand"]) or None,
        description=normalize_text(row.get("Description") or row.get("description") or "") or None,
        domain=normalize_text(row["Domain"]) or None,
        chinese_spring_02g=_clean_cs02g(row.get("ChineseSpring02G")),
    )

@pfam_router.get("/pfam")
def search_pfam(
    domain: str = Query(..., alias="ID"),
    table: str = Query("Genefunc_CS_IWGSC03G_table"),
) -> dict:
    """PfamSearch: search genes by PFAM domain [gene family]

    Purpose:
        Given a PFAM domain ID (starting with PF), return the list of all genes
        containing that domain. The queried table can be specified (default
        Genefunc_CS_IWGSC03G_table; see /api/genes/functions/tables for the full
        list). Note the direction: this endpoint finds genes by PFAM; to look up
        the domains of a single gene, use /api/genes/functions/interval (the
        returned Domain column is the PFAM annotation).

    Related site:
        Corresponds to the PfamSearch tool: https://wheatomics.sdau.edu.cn/tools/proteinfamily.html

    Usage:
        GET /api/genes/functions/pfam?ID=<PFAM domain ID>&table=<table name>
        - ID: required, PFAM domain ID, e.g. PF00319
        - table: optional, default Genefunc_CS_IWGSC03G_table (Chinese Spring IWGSC v2.1)

    Example:
        Request:
          curl -X GET "http://localhost:8000/api/genes/functions/pfam?ID=PF00319"

        Response:
          {
            "success": true,
            "data": {
              "table": "Genefunc_CS_IWGSC03G_table",
              "domain": "PF00319",
              "count": 5,
              "records": [
                {
                  "chromosome": "chr5A",
                  "start_mb": 587.123456,
                  "end_mb": 587.125000,
                  "gene_primary": "TraesCS5A02G391700",
                  "strand": "+",
                  "description": "MADS-box transcription factor",
                  "domain": "PF00319"
                }
              ]
            }
          }
    """

    if not domain.startswith("PF"):
        raise ValidationFailure("PFAM domain ID must start with PF (e.g. PF00319)")

    table = _validate_genefunc_table(table)
    records: list[GeneFunctionRecord] = []

    with mysql_cursor(settings.DB_GENEFUNC) as cursor:
        cursor.execute(f"SELECT * FROM `{table}` WHERE Domain REGEXP %s", (domain,))
        for row in cursor.fetchall():
            records.append(_make_function_record(row, table))

    return ok({"table": table, "domain": domain, "count": len(records), "records": [record.model_dump() for record in records]})


@interval_router.get("/tables")
def list_gene_function_tables() -> dict:
    """Query information about all tables in Genefuncdb.

    Purpose:
        Connect directly to the Genefuncdb database, run SHOW TABLES to get all
        table names, and query each table's row count and column list, returning
        the structured information.

    Usage:
        GET /api/genes/functions/tables
        No parameters.

    Example:
        Request:
          curl -X GET "http://localhost:8000/api/genes/functions/tables"

        Response:
          {
            "success": true,
            "data": {
              "database": "Genefuncdb",
              "total_tables": 5,
              "tables": [
                { "name": "Genefunc_CS_IWGSCv1.0_table", "rows": 168900, "columns": ["Chrom", "Start1", ...] },
                ...
              ]
            }
          }
    """

    tables: list[dict] = []
    with mysql_cursor(settings.DB_GENEFUNC) as cursor:
        # Pull row counts and column names from information_schema in two
        # queries instead of running SHOW TABLES + COUNT(*) + DESCRIBE per
        # table (88 tables × 2 queries = 176 round-trips, ~68s). The
        # registry rarely changes, so approximate table_rows is fine.
        cursor.execute(
            """
            SELECT TABLE_NAME, TABLE_ROWS
            FROM information_schema.tables
            WHERE TABLE_SCHEMA = %s
            """,
            (settings.DB_GENEFUNC,),
        )
        rows_map = {
            row["TABLE_NAME"]: row.get("TABLE_ROWS")
            for row in cursor.fetchall()
        }

        cursor.execute(
            """
            SELECT TABLE_NAME, COLUMN_NAME
            FROM information_schema.columns
            WHERE TABLE_SCHEMA = %s
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """,
            (settings.DB_GENEFUNC,),
        )
        cols_map: dict[str, list[str]] = {}
        for row in cursor.fetchall():
            cols_map.setdefault(row["TABLE_NAME"], []).append(
                row["COLUMN_NAME"]
            )

    for tbl_name in sorted(rows_map):
        tables.append(
            {
                "name": tbl_name,
                "rows": rows_map[tbl_name],
                "columns": cols_map.get(tbl_name, []),
            }
        )

    return ok({"database": "Genefuncdb", "total_tables": len(tables), "tables": tables})


def _friendly_name(tbl):
    # Turn 'Genefunc_<species>_<cultivar>_table' into a short human label
    # like 'CS_IWGSCv1.0' / 'Abo' for the frontend (used by /examples and
    # /registry). Falls back to the raw name if the pattern doesn't match.
    # table_name itself is unchanged so queries (?table=...) keep working.
    if not tbl:
        return tbl
    s = tbl
    if s.startswith("Genefunc_"):
        s = s[len("Genefunc_"):]
    if s.endswith("_table"):
        s = s[: -len("_table")]
    return s


def _infer_karyotype(table_name):
    """Infer the chromosome composition from the table name (Genefunc_AABBDD_xxx_table -> AABBDD).

    The first segment of a Genefunc_* table name is usually the chromosome
    composition (AABBDD/AABB/AA/DD/HH/RR/SS/...); Chinese Spring IWGSC tables use
    the CS prefix (hexaploid AABBDD). Used as a fallback when the Polyploidy
    column is empty.
    """
    if not table_name:
        return None
    s = table_name
    if s.startswith("Genefunc_"):
        s = s[len("Genefunc_"):]
    if s.endswith("_table"):
        s = s[: -len("_table")]
    first = s.split("_")[0] if s else ""
    if not first:
        return None
    if first.upper().startswith("CS"):
        return "AABBDD"
    return first


def _display_name(polyploidy, table_name):
    """Build the display name, avoiding a duplicated karyotype prefix (new table names already include it)."""
    friendly = _friendly_name(table_name)
    if polyploidy and friendly and not friendly.startswith(polyploidy + "_"):
        return f"{polyploidy}_{friendly}"
    return friendly


@interval_router.get("/examples")
def list_genome_examples() -> dict:
    """Get example query data for all genomes.

    Purpose:
        Return the example Region, Gene ID and Pfam ID for each genome, used by
        the Interval Tool frontend to display example links.

    Usage:
        GET /api/genes/functions/examples
        No parameters.

    Example:
        Request:
          curl -X GET "http://localhost:8000/api/genes/functions/examples"

        Response:
          {
            "success": true,
            "data": {
              "examples": [
                { "table_name": "Genefunc_CS_IWGSCv1.0_table", "display_name": "Chinese Spring genome v1.0",
                  "region": "chr1A:1-141522", "gene": "TraesCS1A01G000100LC", "pfam": "" },
                ...
              ]
            }
          }
    """

    # Read from Genefunc_registry so the dropdown stays in sync with
    # the actual list of installed genomes. Row count grows with each
    # genome import (was 104 in mid-2026, 222 by late-2026) - never
    # hardcode it; read /registry's count field instead. Legacy history:
    # the old hardcoded GENOME_EXAMPLES list only had 32 entries.
    # We use the legacy example_chr_id / example_gene_id columns
    # (not example_species_chr_id / example_cds_id) per user request.
    # display_name is curated in the registry (e.g. "Chinese Spring 03G",
    # "Durum Wheat cv. Svevo V2 (AABB)"); fall back to the polyploidy +
    # table-name form only when it is empty.
    sql = """
        SELECT table_name,
               COALESCE(NULLIF(display_name, ''), table_name) AS display_name,
               example_chr_id, example_gene_id,
               COALESCE(Polyploidy, '') AS polyploidy
        FROM Genefunc_registry
        WHERE visible = 1
        ORDER BY display_order, id
    """
    with mysql_cursor(settings.DB_GENEFUNC) as cursor:
        cursor.execute(sql)
        rows = cursor.fetchall()

        # Pull column names so the frontend can decide which tables are
        # valid for a given tool (e.g. PfamSearch needs a `Domain` column).
        cursor.execute(
            """
            SELECT TABLE_NAME, COLUMN_NAME
            FROM information_schema.columns
            WHERE TABLE_SCHEMA = %s
            """,
            (settings.DB_GENEFUNC,),
        )
        cols_map: dict[str, list[str]] = {}
        for row in cursor.fetchall():
            cols_map.setdefault(row["TABLE_NAME"], []).append(row["COLUMN_NAME"])

    def _ensure_range(chr_id):
        # example_chr_id may store only a chromosome (e.g. "chr1A") without
        # a start-end range. The interval frontend expects "chr:start-end",
        # so append a default 1-5000000 window when no ":" is present.
        s = (chr_id or "").strip()
        if not s:
            return s
        return s if ":" in s else f"{s}:1-5000000"

    seen = set()
    examples = []
    for r in rows:
        table_name = r.get("table_name")
        display_name = (r.get("display_name") or "").strip() \
            or _display_name(r.get("polyploidy") or None, table_name)
        if display_name in seen:
            continue
        seen.add(display_name)
        examples.append({
            "table_name":   table_name,
            "display_name": display_name,
            # Karyotype (subgenome composition) drives the dropdown grouping;
            # computed from Polyploidy or the table prefix so new genomes sort
            # themselves (see app/core/genome_ordering.py).
            "karyotype":    infer_karyotype(table_name, r.get("polyploidy")),
            # Frontend keys are region / gene / pfam for backward compat.
            "region":       _ensure_range(r.get("example_chr_id")),
            "gene":         r.get("example_gene_id"),
            # Genefunc_registry has no Pfam-domain column; use a default.
            "pfam":         "PF00931",
            # Columns of the underlying Genefunc_* table, so the frontend
            # can filter to tables that support its query (e.g. PfamSearch
            # needs a `Domain` column).
            "columns":      cols_map.get(table_name, []),
        })
    examples.sort(key=genome_sort_key)
    return ok({"examples": examples})
@interval_router.get("/registry")
def list_gene_function_registry() -> dict:
    """Query the Genefuncdb.Genefunc_registry table.

    Purpose:
        Return the metadata of all registered gene-function tables in the
        Genefunc_registry table. Includes id, table_name, display_name, Subgenome,
        Polyploidy, chromosome_level, Doi, title, Abstract, example_chr, example_id
        and other fields.

    Notes:
        Table names are case-sensitive (MySQL `lower_case_table_names=0` on Linux),
        so `Genefunc_registry` must be written with a capital G; otherwise MySQL
        raises 1146 table does not exist.

    Usage:
        GET /api/genes/functions/registry
        No parameters.

    Example:
        Request:
          curl -X GET "http://localhost:8000/api/genes/functions/registry"

        Response:
          {
            "success": true,
            "data": {
              "database": "genefunc_registry",
              "count": 2,
              "records": [
                {
                  "id": 1,
                  "table_name": "Genefunc_Abo_table",
                  "display_name": "Abbondanza (Abo)",
                  "subgenome": "ABD",
                  "polyploidy": "Allohexaploid",
                  "chromosome_level": "AABBDD",
                  "doi": "10.1038/s41586-024-08277-0",
                  "title": "Unraveling Allelic Impacts...",
                  "abstract": "The TaVP1-B gene...",
                  "example_species_chr": "chr1A_Abo",
                  "example_cds": "Abo1A000100.1",
                  "example_protein": "Abo1A000100.1.p"
                }
              ]
            }
          }
    """
    records: list[dict] = []
    with mysql_cursor(settings.DB_GENEFUNC) as cursor:
        # MySQL table names are case-sensitive on Linux. The actual table on
        # Genefuncdb is `Genefunc_registry` (capital G), per /tables endpoint.
        cursor.execute("""
            SELECT
                id,
                table_name,
                Accession,
                `Group`,
                Polyploidy,
                chromosome_level,
                Doi,
                title,
                Abstract,
                example_species_chr_id,
                example_cds_id,
                example_protein_id,
                display_name,
                display_order,
                visible
            FROM Genefunc_registry
            WHERE visible = 1
            ORDER BY display_order, id
        """)
        seen = set()
        for row in cursor.fetchall():
            table_name = row.get("table_name")
            polyploidy = row.get("Polyploidy") or _infer_karyotype(table_name)
            display_name = (row.get("display_name") or "").strip() or _display_name(polyploidy, table_name)
            if display_name in seen:
                continue
            seen.add(display_name)
            records.append({
                "id": row.get("id"),
                "table_name": table_name,
                "display_name": display_name,
                "subgenome": row.get("Accession"),
                "group": row.get("Group"),
                "polyploidy": polyploidy,
                "chromosome_level": row.get("chromosome_level"),
                "doi": row.get("Doi"),
                "title": row.get("title"),
                "abstract": row.get("Abstract"),
                "example_species_chr": row.get("example_species_chr_id"),
                "example_cds": row.get("example_cds_id"),
                "example_protein": row.get("example_protein_id"),
            })
    return ok({"database": "genefunc_registry", "count": len(records), "records": records})

@interval_router.get("/interval")
def search_gene_interval(
    region: str = Query(..., alias="ID"),
    table: str = Query("Genefunc_CS_IWGSC03G_table"),
) -> dict:
    """Search genes by chromosomal interval.

    Purpose:
        Given a chromosomal interval (e.g. chr5A:587000000..587200000), return the
        list of all genes within that interval. The queried table can be specified
        (default Genefunc_CS_IWGSC03G_table; see /api/genes/functions/tables for
        the full list).

    Related site:
        Corresponds to IntervalTool: https://wheatomics.sdau.edu.cn/tools/intervalTools.html

    Usage:
        GET /api/genes/functions/interval?ID=<interval>&table=<table name>
        - ID: required, chromosomal interval in the form chr5A:587000000..587200000
        - table: optional, default Genefunc_CS_IWGSC03G_table (Chinese Spring IWGSC v2.1)

    Example:
        Request:
          curl -X GET "http://localhost:8000/api/genes/functions/interval?ID=chr5A:587000000..587200000"

        Response:
          {
            "success": true,
            "data": {
              "table": "Genefunc_CS_IWGSC03G_table",
              "region": "chr5A:587000000..587200000",
              "count": 5,
              "records": [
                {
                  "chromosome": "chr5A",
                  "start_mb": 587.123456,
                  "end_mb": 587.125000,
                  "gene_primary": "TraesCS5A02G391700",
                  "strand": "+",
                  "description": "MADS-box transcription factor",
                  "domain": null
                }
              ]
            }
          }
    """

    table = _validate_genefunc_table(table)
    records: list[GeneFunctionRecord] = []

    # 如果不是区间格式（不含:），按基因 ID 搜索
    if ":" not in region:
        # 支持换行/逗号/空格分隔的多个 ID；版本号（.1、.2）自动 strip，
        # 因为各 Genefunc 表存的是不带版本的基因 ID。
        gene_ids = [g for g in re.split(r"[\s,;]+", region.strip()) if g]
        if not gene_ids:
            raise ValidationFailure("No gene ID provided")
        if len(gene_ids) > 200:
            raise ValidationFailure(f"Too many gene IDs ({len(gene_ids)}); maximum is 200 per query")
        with mysql_cursor(settings.DB_GENEFUNC) as cursor:
            # 根据表类型动态选择基因列
            if table in ("Genefunc_IWGSC03G_table", "Genefunc_CS_IWGSC03G_table"):
                gene_cols = ["Gene03G", "Gene02G"]
            else:
                gene_cols = ["Gene"]
            # Batched: match both the versioned and the version-stripped id.
            # Older tables store `TraesCS1A03G0000100LC` while the pipeline
            # tables (Abo, Svevo V2, ...) store `Abo1A000100.1`, so a single
            # form never matches every table.
            base_ids = [re.sub(r"\.\d+$", "", gid) for gid in gene_ids]
            candidates = list(dict.fromkeys(base_ids + gene_ids))
            placeholders = ",".join(["%s"] * len(candidates))
            where_clause = " OR ".join(f"`{col}` IN ({placeholders})" for col in gene_cols)
            # One placeholder group per gene column: flatten the ids for pymysql
            # (a nested tuple of lists raised "not enough arguments for format string"
            # for any multi-ID batch query).
            args = tuple(candidates) * len(gene_cols)
            cursor.execute(f"SELECT * FROM `{table}` WHERE {where_clause}", args)
            for row in cursor.fetchall():
                records.append(_make_function_record(row, table))
        return ok({"table": table, "region": region, "count": len(records), "records": [record.model_dump() for record in records]})

    ensure_interval_like(region)
    chrom = region.split(":")[0]
    interval = region.split(":")[1].replace("..", "-")
    start_text, end_text = interval.split("-")
    start, end = int(start_text), int(end_text)

    if end <= start:
        raise ValidationFailure("End number should be more than start number")
    if end - start > 30_000_000:
        raise ValidationFailure("Region is too large: maximum interval is 30 Mb")

    with mysql_cursor(settings.DB_GENEFUNC) as cursor:
        cursor.execute(
            f"SELECT * FROM `{table}` WHERE Chrom=%s AND Start1 <= %s AND End1 >= %s",
            (chrom, end, start),
        )
        for row in cursor.fetchall():
            records.append(_make_function_record(row, table))

    return ok({"table": table, "region": region, "count": len(records), "records": [record.model_dump() for record in records]})




@genehub_router.get("/resolve")
def resolve_gene_id(
    gene_id: str = Query(..., alias="ID"),
) -> dict:
    """Resolve a gene ID across the Genefunc tables and return its Chinese Spring 02G mappings.

    Fallback for non-Chinese-Spring IDs in GeneHub: scans the Gene/Gene02G/Gene03G
    columns of all visible Genefunc tables and returns the matching records with
    their ChineseSpring02G mappings.
    """
    gene_id = (gene_id or "").strip()
    if not re.match(r"^[A-Za-z0-9_.:-]{2,200}$", gene_id):
        raise ValidationFailure("Invalid gene ID")
    base_id = re.sub(r"\.\d+$", "", gene_id)
    candidates = list(dict.fromkeys([gene_id, base_id]))

    mappings: list[dict] = []
    seen = set()
    with mysql_cursor(settings.DB_GENEFUNC) as cursor:
        cursor.execute(
            "SELECT table_name, display_name, `Group`, Polyploidy "
            "FROM Genefunc_registry WHERE visible=1 ORDER BY display_order, table_name"
        )
        registry = cursor.fetchall()
        cursor.execute(
            "SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=%s AND COLUMN_NAME IN ('Gene','Gene02G','Gene03G')",
            (settings.DB_GENEFUNC,),
        )
        table_columns: dict[str, list[str]] = {}
        for row in cursor.fetchall():
            table_columns.setdefault(row["TABLE_NAME"], []).append(row["COLUMN_NAME"])

        for meta in registry:
            table = str(meta.get("table_name") or "")
            if not re.match(r"^Genefunc_[A-Za-z0-9_]+_table$", table):
                continue
            gene_columns = table_columns.get(table)
            if not gene_columns:
                continue
            display = normalize_text(meta.get("display_name")) or table
            for col in gene_columns:
                try:
                    cursor.execute(
                        f"SELECT * FROM `{table}` WHERE `{col}` IN (%s,%s) LIMIT 10",
                        (gene_id, base_id),
                    )
                    rows = cursor.fetchall() or []
                except Exception:
                    continue
                for row in rows:
                    record = _make_function_record(row, table)
                    key = (table, record.gene_primary, record.chinese_spring_02g)
                    if key in seen:
                        continue
                    seen.add(key)
                    data = record.model_dump()
                    data.update(
                        table=table,
                        dataset=display,
                        group=normalize_text(meta.get("Group")) or None,
                        ploidy=normalize_text(meta.get("Polyploidy")) or None,
                    )
                    mappings.append(data)

    return ok({"query": gene_id, "count": len(mappings), "mappings": mappings})
