#!/usr/bin/env python3
"""Extract the curated KnownGene list (v2056 workbook) into DB-ready JSONL.

Source of truth
---------------
`已知基因逐条提取清单_20261019-合集_修正版v2056_20261028.xlsx`
(main sheet `数据（修正版v2056）`, 1420 x 17).  v2056 is v2055 with only the 16
multi-value alignment anomalies fixed (see docs/known_genes/multi_value_fixes_v2056.md).

What it does
------------
1. Reads the 17 Excel columns and maps them 1:1 onto the target `cloned_gene_tbl`
   columns (plus 3 derived columns added by the v2055 migration):
   `species_primary`, `chromosome`, and `publication_years`.
2. Splits the positional multi-value fields (`title`/`doi`/`publication_year`,
   separator `"; "`) and re-joins them with `###` (the CGI-era convention the
   current API already understands), padding short lists with empty slots so
   the three lists stay positionally aligned.
3. Derives `publication_year` (YEAR column) = earliest year of the row.
4. Runs per-column validation assertions and writes a human review report.
5. Emits:
     out/known_genes_v2056.jsonl          -- one JSON object per DB row
     out/validation_report.md / .json     -- fatal + warning findings
     out/api_fixtures/*.json              -- frontend mock fixtures (/all, /stats, details)
     out/clone_id_input.json              -- compact (reference_genome_id, gene_id,
                                             gene_name) triples for the server-side
                                             clone_id mapping step

Usage
-----
    python3 scripts/known_genes_v2055/extract.py \
        --xlsx "/path/to/...v2056....xlsx" \
        --outdir scripts/known_genes_v2055/out

Only the standard library + pandas/openpyxl are required (bundled Python has them).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter, OrderedDict

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    sys.exit("pandas is required to read the workbook")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_XLSX = "/Users/mashengwei/Desktop/markdown/陈甜甜/known-gene-paper-20260916/已知基因逐条提取清单_20261019-合集_修正版v2061_20261028.xlsx"
DEFAULT_PROFILE = os.path.join(REPO_ROOT, "docs", "known_genes", "_evidence", "profile_v2055.json")
DEFAULT_OUTDIR = os.path.join(REPO_ROOT, "scripts", "known_genes_v2055", "out")
DEFAULT_PATCH = os.path.join(REPO_ROOT, "scripts", "known_genes_v2055", "multi_value_patch_v2060.json")

SHEET_PREFIX = "数据（修正版"
MULTI_SEP = "; "
JOIN_SEP = "###"

# new curated rows have no submitter: use the curation identity (plan Q15 default)
AUTHOR = "WheatOmics curation"
AUTHOR_MAIL = "shengweima@icloud.com"
SUBMISSION_DATE = "2026-10-28"  # first v2056 import date; migration may override

COLUMNS = [
    # (excel column, db column, max length in chars, required)
    ("gene_id（入库）", "gene_id", 300, True),
    ("参考基因组ID（入库）", "reference_genome_id", 100, True),
    ("gene_name（入库）", "gene_name", 500, True),
    ("物种信息（入库）", "gene_species", 1000, True),
    ("chrom_pos（入库）", "chrom_pos", 500, True),
    ("gene_phenotype（入库）", "gene_phenotype", 2000, True),
    ("key_result（入库，≤500 词英文）", "key_result", 15000, True),
    ("function_description（入库）", "function_description", None, True),
    ("蛋白家族（入库）", "protein_family", None, True),
    ("cloning_method（入库）", "cloning_method", 255, True),
    ("cloning_method_description（入库）", "cloning_method_description", None, True),
    ("验证方法（入库）", "validation_method", None, True),
    ("研究策略（入库）", "research_strategy", 32, True),
    ("功能大类（入库）", "functional_category", 64, True),
    ("title（入库）", "paper_title", None, True),
    ("doi（入库）", "paper_doi", None, True),
    ("publication_year（入库）", "publication_year", 64, True),
]

TEXT_UNLIMITED = {None}

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
YEAR_RE = re.compile(r"^\d{4}$")
GENE_LIKE_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


def strip_html_tags(text: str) -> str:
    """Defensive only: the curated data has no real HTML tags (verified)."""
    import html as html_mod

    cleaned = re.sub(r"<[^>]+>", "", text)
    return html_mod.unescape(cleaned)


def clean_text(value) -> str:
    s = "" if value is None else str(value)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s.strip()


def split_multi(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(MULTI_SEP) if part.strip()]


def join_multi(parts: list[str]) -> str:
    return JOIN_SEP.join(p.strip() for p in parts)


def pad(parts: list[str], n: int) -> list[str]:
    return list(parts) + [""] * (n - len(parts))


def derive_species_primary(raw: str, raw_to_canonical: dict[str, str]) -> tuple[str, str | None]:
    """Return (species_primary, error_message)."""
    key = raw.strip()
    if key in raw_to_canonical:
        return raw_to_canonical[key], None
    # fall back to the leading Latin binomial before the first '('
    head = re.split(r"\s+\(", key, maxsplit=1)[0].strip()
    head = re.sub(r"\s+$", "", head)
    if head:
        return head, f"species not in mapping table; fallback={head!r}"
    return "", "empty species"


def derive_chromosome(pos: str) -> str:
    """Parse chromosome label from chrom_pos.

    Formats seen: ``Refv1.0 chr7A:112.264-112.266Mb``, ``MorexV3 chr3H:...``,
    ``AetTA1675 2D:2.33-2.45Mb`` (no 'chr'), ``T.ponticum.v1 chr54:...``.
    """
    m = re.search(r"chr\s*([0-9]+[A-Za-z]{0,2})", pos, re.IGNORECASE)
    if m:
        token = m.group(1)
        if re.search(r"[A-Za-z]", token):
            return token.upper() if len(token) <= 3 else token
        return "chr" + token
    m = re.search(r"\b([0-9]+[A-Za-z]{0,2})\s*:", pos)
    if m:
        token = m.group(1)
        return token.upper() if re.search(r"[A-Za-z]", token) else token
    return ""


def derive_genome_ref(pos: str) -> str:
    """Reference assembly label = first token of chrom_pos (e.g. Refv1.0)."""
    first = pos.split()[0] if pos.split() else ""
    return first if first and not re.fullmatch(r"[0-9]", first) else ""


def derive_phenotype_brief(pheno: str, limit: int = 500) -> str:
    s = pheno.strip()
    if not s:
        return ""
    brief = s.split(":", 1)[0].strip() if ":" in s else s.split(";")[0].strip()
    return brief[:limit]


def is_multi_species(species: str) -> bool:
    return len([p for p in species.split(";") if p.strip()]) > 1


_TAG_ABBREVIATIONS = {
    "yr": "Yr", "lr": "Lr", "sr": "Sr", "pm": "Pm", "fhb": "FHB", "fcr": "FCR",
    "snb": "SNB", "stb": "STB", "se": "SE", "wymv": "WYMV", "bydv": "BYDV",
}


def _split_top_level_semicolons(value: object) -> list[str]:
    """Split on ';' outside parentheses (phenotype free text has '(...; ...)')."""

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
    return pieces


def _normalize_tag(tag: str) -> str:
    return re.sub(
        r"\((yr|lr|sr|pm|fhb|fcr|snb|stb|se|wymv|bydv)\b",
        lambda m: "(" + _TAG_ABBREVIATIONS[m.group(1)],
        tag,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--xlsx", default=DEFAULT_XLSX)
    ap.add_argument("--sheet", default=None, help="main sheet name (default: auto-detect 数据（修正版*)")
    ap.add_argument("--profile", default=DEFAULT_PROFILE, help="profile_v2055.json for species mapping")
    ap.add_argument(
        "--patch",
        default=DEFAULT_PATCH,
        help="optional JSON patch for multi-value alignment anomalies (default: %(default)s)",
    )
    ap.add_argument("--no-patch", action="store_true", help="disable the multi-value alignment patch")
    ap.add_argument("--outdir", default=DEFAULT_OUTDIR)
    ap.add_argument("--skip-fixtures", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(args.xlsx):
        sys.exit(f"workbook not found: {args.xlsx}")

    with open(args.xlsx, "rb") as fh:
        xlsx_md5 = hashlib.md5(fh.read()).hexdigest()

    xls = pd.ExcelFile(args.xlsx)
    sheet = args.sheet
    if sheet is None:
        candidates = [s for s in xls.sheet_names if s.startswith(SHEET_PREFIX)]
        if not candidates:
            sys.exit(f"cannot find main sheet (expected name starting with {SHEET_PREFIX!r}); sheets={xls.sheet_names}")
        sheet = candidates[-1]
    df = pd.read_excel(args.xlsx, sheet_name=sheet, dtype=str).fillna("")
    patched_rows: list[dict] = []
    patch_path = None if args.no_patch else args.patch
    if patch_path and os.path.isfile(patch_path):
        patch = json.load(open(patch_path, encoding="utf-8"))
        for entry in patch.get("rows", []):
            mask = (df["gene_id（入库）"].str.strip() == str(entry["gene_id"]).strip()) & (
                df["gene_name（入库）"].str.strip() == str(entry["gene_name"]).strip()
            )
            idx = list(df.index[mask])
            if not idx:
                print(f"WARNING  : patch row not found in workbook: {entry['gene_name']}", file=sys.stderr)
                continue
            i = idx[0]
            exp, cor = entry["expected"], entry["corrected"]
            current = {col: str(df.at[i, col]).strip() for col in ("title（入库）", "doi（入库）", "publication_year（入库）")}
            already = {col: str(cor[k]).strip() for col, k in (
                ("title（入库）", "title"), ("doi（入库）", "doi"), ("publication_year（入库）", "publication_year"))}
            if current == already:
                patched_rows.append({"row": int(i) + 2, "gene_name": entry["gene_name"], "doi": cor["doi"], "already_corrected": True})
                continue
            if (current["doi（入库）"] != str(exp["doi"]).strip()
                    or current["title（入库）"] != str(exp["title"]).strip()
                    or current["publication_year（入库）"] != str(exp["publication_year"]).strip()):
                print(f"WARNING  : patch skipped (row changed since patch): {entry['gene_name']}", file=sys.stderr)
                continue
            df.at[i, "title（入库）"] = cor["title"]
            df.at[i, "doi（入库）"] = cor["doi"]
            df.at[i, "publication_year（入库）"] = cor["publication_year"]
            patched_rows.append({"row": int(i) + 2, "gene_name": entry["gene_name"], "doi": cor["doi"]})
        print(f"patch    : {patch_path} ({len(patched_rows)} rows applied)")
    elif patch_path:
        print(f"patch    : skipped (not found: {patch_path})")
    print(f"workbook : {args.xlsx}")
    print(f"md5      : {xlsx_md5}")
    print(f"sheet    : {sheet}")
    print(f"shape    : {df.shape[0]} rows x {df.shape[1]} cols")

    raw_to_canonical: dict[str, str] = {}
    common_name_map: dict[str, str] = {}
    if os.path.isfile(args.profile):
        prof = json.load(open(args.profile, encoding="utf-8"))
        raw_to_canonical = prof.get("species", {}).get("raw_to_canonical", {}) or {}
        common_name_map = prof.get("species", {}).get("common_name_map", {}) or {}
        print(f"profile  : {len(raw_to_canonical)} species mappings")
    else:
        print(f"WARNING  : species profile not found at {args.profile}; falling back to binomial regex", file=sys.stderr)

    records: list[dict] = []
    fatals: list[dict] = []
    warns: list[dict] = []
    multi_anomalies: list[dict] = []

    for idx, row in df.iterrows():
        excel_row = int(idx) + 2  # header is row 1

        def cell(name: str) -> str:
            return clean_text(row[name])

        rec: OrderedDict[str, object] = OrderedDict()
        rec["_row"] = excel_row

        # --- 1:1 columns ---------------------------------------------------
        for excel_col, db_col, max_len, required in COLUMNS:
            value = cell(excel_col)
            if required and value == "":
                fatals.append({"row": excel_row, "column": db_col, "error": "required but empty"})
            if max_len is not None and len(value) > max_len:
                fatals.append({
                    "row": excel_row, "column": db_col,
                    "error": f"length {len(value)} > DB limit {max_len} (STRICT mode would fail)",
                })
            rec[db_col] = value

        # --- multi-value positional fields --------------------------------
        title_parts = split_multi(rec["paper_title"])
        doi_parts = split_multi(rec["paper_doi"])
        year_parts = split_multi(rec["publication_year"])
        n = max(len(title_parts), len(doi_parts), len(year_parts), 1)
        if not (len(title_parts) == len(doi_parts) == len(year_parts)):
            multi_anomalies.append({
                "row": excel_row,
                "gene_name": rec["gene_name"],
                "n_title": len(title_parts), "n_doi": len(doi_parts), "n_year": len(year_parts),
                "doi": rec["paper_doi"],
            })
        title_parts, doi_parts, year_parts = pad(title_parts, n), pad(doi_parts, n), pad(year_parts, n)

        for i, doi in enumerate(doi_parts):
            if doi and not DOI_RE.match(doi):
                warns.append({"row": excel_row, "column": "paper_doi", "error": f"DOI format suspicious: {doi!r}"})
        for i, year in enumerate(year_parts):
            if year and not YEAR_RE.match(year):
                warns.append({"row": excel_row, "column": "publication_year", "error": f"year not 4-digit: {year!r}"})

        rec["paper_title"] = join_multi(title_parts)
        rec["paper_doi"] = join_multi(doi_parts)
        rec["publication_years"] = join_multi(year_parts)
        years = [int(y) for y in year_parts if YEAR_RE.match(y)]
        rec["publication_year"] = str(min(years)) if years else ""
        if not years:
            fatals.append({"row": excel_row, "column": "publication_year", "error": "no parsable year"})

        # --- derived columns ---------------------------------------------
        species_primary, sp_err = derive_species_primary(rec["gene_species"], raw_to_canonical)
        if sp_err:
            warns.append({"row": excel_row, "column": "species_primary", "error": sp_err})
        if len(species_primary) > 64:
            fatals.append({"row": excel_row, "column": "species_primary", "error": f"length {len(species_primary)} > 64"})
        rec["species_primary"] = species_primary

        chromosome = derive_chromosome(rec["chrom_pos"])
        if not chromosome:
            warns.append({"row": excel_row, "column": "chromosome", "error": f"cannot parse chrom_pos: {rec['chrom_pos']!r}"})
        if len(chromosome) > 16:
            fatals.append({"row": excel_row, "column": "chromosome", "error": f"length {len(chromosome)} > 16"})
        rec["chromosome"] = chromosome

        if len(rec["publication_years"]) > 64:
            fatals.append({"row": excel_row, "column": "publication_years",
                           "error": f"length {len(rec['publication_years'])} > 64"})

        # --- constant / identity columns ---------------------------------
        rec["author"] = AUTHOR
        rec["author_mail"] = AUTHOR_MAIL
        rec["submission_date"] = SUBMISSION_DATE

        # --- warnings -----------------------------------------------------
        if not GENE_LIKE_RE.match(rec["gene_id"]):
            warns.append({"row": excel_row, "column": "gene_id",
                          "error": f"not path-safe (ensure_gene_like): {rec['gene_id']!r}"})
        if "/" in rec["gene_name"]:
            warns.append({"row": excel_row, "column": "gene_name",
                          "error": "contains '/', needs URL encoding in frontend"})
        if "#" in rec["key_result"] or "#" in rec["gene_phenotype"] or "#" in rec["function_description"]:
            warns.append({"row": excel_row, "column": "text",
                          "error": "row contains '#' (must not be normalized to quote)"})

        records.append(rec)

    # ------------------------------------------------------------------
    # summaries for the report / fixtures
    # ------------------------------------------------------------------
    species_dist = Counter(r["species_primary"] for r in records)
    chrom_dist = Counter()
    wheat_chroms = [f"{g}{s}" for g in range(1, 8) for s in ("A", "B", "D")]
    wheat_set = set(wheat_chroms)
    for r in records:
        if r["chromosome"]:
            chrom_dist[r["chromosome"]] += 1
    category_dist = Counter(r["functional_category"] for r in records)
    strategy_dist = Counter(r["research_strategy"] for r in records)
    ref_entries = 0
    unique_dois: set[str] = set()
    year_token_counter: Counter[int] = Counter()
    multi_year_rows = 0
    for r in records:
        dois = [d for d in r["paper_doi"].split(JOIN_SEP) if d]
        years = [y for y in r["publication_years"].split(JOIN_SEP) if y]
        ref_entries += max(len(dois), len(years), 1)
        unique_dois.update(dois)
        if len(years) > 1:
            multi_year_rows += 1
        for y in years:
            if YEAR_RE.match(y):
                year_token_counter[int(y)] += 1

    # phenotype tags: split on ';', lower-case, de-duplicate per row, drop >80 chars
    phenotype_tags: Counter[str] = Counter()
    rows_without_tags = 0
    for r in records:
        tags = []
        for piece in _split_top_level_semicolons(r["gene_phenotype"]):
            t = _normalize_tag(piece.strip().lower())
            if not t or len(t) > 80:
                continue
            tags.append(t)
        tags = list(dict.fromkeys(tags))
        if not tags:
            rows_without_tags += 1
        phenotype_tags.update(tags)

    stats = {
        "total": len(records),
        "species": [
            {"name": name, "count": count, "raw_forms": len({r["gene_species"] for r in records if r["species_primary"] == name}),
             "common_name": common_name_map.get(name)}
            for name, count in species_dist.most_common()
        ],
        "species_raw_count": len({r["gene_species"] for r in records}),
        "chromosomes": [
            {"label": label, "count": count, "group": "wheat" if label in wheat_set else "other"}
            for label, count in sorted(chrom_dist.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "functional_category": [{"name": k, "count": v} for k, v in category_dist.most_common()],
        "research_strategy": [{"name": k, "count": v} for k, v in strategy_dist.most_common()],
        "phenotype_tags": [{"tag": k, "count": v} for k, v in phenotype_tags.most_common(100)],
        "phenotype_tag_distinct": len(phenotype_tags),
        "publication_year": [{"year": y, "count": c} for y, c in sorted(year_token_counter.items())],
        "references": {"entries": ref_entries, "unique_dois": len(unique_dois)},
        "notes": {
            "multi_year_rows": multi_year_rows,
            "multi_species_rows": sum(1 for r in records if is_multi_species(r["gene_species"])),
            "rows_without_tags": rows_without_tags,
            "wheat_chromosomes_covered": len(wheat_set & set(chrom_dist)),
        },
    }

    # ------------------------------------------------------------------
    # API fixtures (/all summary + representative details)
    # ------------------------------------------------------------------
    def to_summary(rec: dict, synthetic_clone_id: int) -> dict:
        years = [y for y in rec["publication_years"].split(JOIN_SEP) if y]
        dois = [d for d in rec["paper_doi"].split(JOIN_SEP) if d]
        return {
            "clone_id": synthetic_clone_id,
            "gene_id": rec["gene_id"],
            "gene_name": rec["gene_name"],
            "chrom_pos": rec["chrom_pos"],
            "phenotype": rec["gene_phenotype"],
            "species": rec["gene_species"],
            "publication_year": rec["publication_year"] or None,
            "dois": dois,
            "reference_genome_id": rec["reference_genome_id"],
            "species_primary": rec["species_primary"],
            "chromosome": rec["chromosome"],
            "genome_ref": derive_genome_ref(rec["chrom_pos"]),
            "phenotype_brief": derive_phenotype_brief(rec["gene_phenotype"]),
            "functional_category": rec["functional_category"],
            "research_strategy": rec["research_strategy"],
            "publication_years": years,
        }

    def to_detail(rec: dict, synthetic_clone_id: int) -> dict:
        titles = [t for t in rec["paper_title"].split(JOIN_SEP)]
        dois = [d for d in rec["paper_doi"].split(JOIN_SEP)]
        years = [y for y in rec["publication_years"].split(JOIN_SEP)]
        n = max(len(titles), len(dois), len(years), 1)
        titles, dois, years = pad(titles, n), pad(dois, n), pad(years, n)
        references = []
        for i in range(n):
            if not titles[i] and not dois[i] and not years[i]:
                continue
            references.append({
                "doi": dois[i] or None,
                "title": titles[i] or None,
                "year": int(years[i]) if years[i] and YEAR_RE.match(years[i]) else None,
            })
        validation_methods = [m.strip() for m in rec["validation_method"].split("; ") if m.strip()]
        return {
            "clone_id": synthetic_clone_id,
            "gene_id": rec["gene_id"],
            "gene_name": rec["gene_name"],
            "chrom_pos": rec["chrom_pos"],
            "phenotype": rec["gene_phenotype"],
            "species": rec["gene_species"],
            "paper_title": [t for t in titles if t],
            "references": references,
            "key_result": [rec["key_result"]] if rec["key_result"] else [],
            "publication_year": int(rec["publication_year"]) if rec["publication_year"] else None,
            "function_description": rec["function_description"],
            "cloning_method": rec["cloning_method"],
            "cloning_method_description": rec["cloning_method_description"],
            "author": rec["author"],
            "author_mail": rec["author_mail"],
            "submission_date": rec["submission_date"],
            "reference_genome_id": rec["reference_genome_id"],
            "protein_family": rec["protein_family"],
            "validation_method": rec["validation_method"],
            "validation_methods": validation_methods,
            "research_strategy": rec["research_strategy"],
            "functional_category": rec["functional_category"],
            "species_primary": rec["species_primary"],
            "chromosome": rec["chromosome"],
            "genome_ref": derive_genome_ref(rec["chrom_pos"]),
            "phenotype_brief": derive_phenotype_brief(rec["gene_phenotype"]),
            "publication_years": [int(y) for y in years if y and YEAR_RE.match(y)],
        }

    summary_records = [to_summary(rec, synthetic_clone_id=i + 1) for i, rec in enumerate(records)]
    fixture_all = {"success": True, "message": "ok", "data": {"total": len(summary_records), "records": summary_records}}

    # representative details for the frontend mock
    def pick(predicate, label):
        for i, rec in enumerate(records):
            if predicate(rec):
                return label, to_detail(rec, synthetic_clone_id=i + 1)
        return None

    detail_fixtures = {}
    for label, predicate in [
        ("wheat_long_text_multi_doi", lambda r: len(r["gene_phenotype"]) > 900 and JOIN_SEP in r["paper_doi"]),
        ("barley_3H", lambda r: r["chromosome"] == "3H"),
        ("hash_symbol_row", lambda r: "#" in (r["key_result"] + r["gene_phenotype"] + r["function_description"])),
        ("no_chr_prefix_row", lambda r: "#" not in r["chrom_pos"] and "chr" not in r["chrom_pos"].lower()),
        ("largest_protein_family", lambda r: len(r["protein_family"]) > 2000),
        ("multi_year_row", lambda r: len([y for y in r["publication_years"].split(JOIN_SEP) if y]) >= 2),
    ]:
        got = pick(predicate, label)
        if got:
            detail_fixtures[got[0]] = got[1]

    # ------------------------------------------------------------------
    # write outputs
    # ------------------------------------------------------------------
    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)
    fixtures_dir = os.path.join(outdir, "api_fixtures")
    os.makedirs(fixtures_dir, exist_ok=True)

    ver_match = re.search(r"v(\d+)", sheet)
    version_tag = f"v{ver_match.group(1)}" if ver_match else "v2056"
    jsonl_path = os.path.join(outdir, f"known_genes_{version_tag}.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    with open(os.path.join(outdir, "clone_id_input.json"), "w", encoding="utf-8") as fh:
        json.dump([[r["reference_genome_id"], r["gene_id"], r["gene_name"]] for r in records], fh, ensure_ascii=False)

    report = {
        "source": os.path.abspath(args.xlsx),
        "source_md5": xlsx_md5,
        "sheet": sheet,
        "rows": len(records),
        "columns": len(COLUMNS),
        "fatals": fatals,
        "warnings": warns,
        "multi_value_anomalies": multi_anomalies,
        "multi_value_patch_path": patch_path,
        "multi_value_patch_rows": patched_rows,
        "stats": {
            "species": len(species_dist),
            "species_raw": len({r["gene_species"] for r in records}),
            "chromosomes": len(chrom_dist),
            "functional_category": len(category_dist),
            "research_strategy": len(strategy_dist),
            "references": ref_entries,
            "unique_dois": len(unique_dois),
            "multi_year_rows": multi_year_rows,
        },
        "distributions": {
            "species": [{"name": k, "count": v} for k, v in species_dist.most_common()],
            "chromosomes": [{"label": k, "count": v, "group": "wheat" if k in wheat_set else "other"}
                            for k, v in sorted(chrom_dist.items(), key=lambda kv: (-kv[1], kv[0]))],
            "functional_category": [{"name": k, "count": v} for k, v in category_dist.most_common()],
            "research_strategy": [{"name": k, "count": v} for k, v in strategy_dist.most_common()],
        },
    }
    with open(os.path.join(outdir, "validation_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)

    md = []
    md.append("# KnownGene v2056 extraction & validation report\n")
    md.append(f"- workbook: `{args.xlsx}`")
    md.append(f"- md5: `{xlsx_md5}`")
    md.append(f"- sheet: `{sheet}`")
    md.append(f"- rows: **{len(records)}**, mapped columns: {len(COLUMNS) + 3} (17 + species_primary/chromosome/publication_years)\n")
    md.append("## verdict\n")
    md.append(f"- fatal errors: **{len(fatals)}**")
    md.append(f"- warnings: **{len(warns)}**")
    md.append(f"- multi-value anomalies: **{len(multi_anomalies)}**")
    md.append(f"- multi-value patch: `{patch_path or 'disabled'}` ({len(patched_rows)} rows applied)")
    md.append(f"- species: {len(species_dist)} (raw {len({r['gene_species'] for r in records})})")
    md.append(f"- chromosomes: {len(chrom_dist)} ({len(wheat_set & set(chrom_dist))} wheat)")
    md.append(f"- references: {ref_entries} entries / {len(unique_dois)} unique DOIs")
    md.append(f"- multi-year rows: {multi_year_rows}\n")
    if fatals:
        md.append("## FATAL\n")
        for f in fatals[:200]:
            md.append(f"- row {f['row']} `{f['column']}`: {f['error']}")
        md.append("")
    if warns:
        md.append("## warnings (first 200)\n")
        for w in warns[:200]:
            md.append(f"- row {w['row']} `{w['column']}`: {w['error']}")
        md.append("")
    md.append("## species distribution\n")
    md.append("| species_primary | rows |")
    md.append("|---|---|")
    for name, count in species_dist.most_common():
        md.append(f"| {name} | {count} |")
    md.append("\n## chromosome distribution\n")
    md.append("| chromosome | rows | group |")
    md.append("|---|---|---|")
    for label, count in sorted(chrom_dist.items(), key=lambda kv: (-kv[1], kv[0])):
        md.append(f"| {label} | {count} | {'wheat' if label in wheat_set else 'other'} |")
    md.append("\n## functional category / research strategy\n")
    for name, count in category_dist.most_common():
        md.append(f"- category `{name}`: {count}")
    for name, count in strategy_dist.most_common():
        md.append(f"- strategy `{name}`: {count}")
    with open(os.path.join(outdir, "validation_report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    if not args.skip_fixtures:
        with open(os.path.join(fixtures_dir, "known_all.json"), "w", encoding="utf-8") as fh:
            json.dump(fixture_all, fh, ensure_ascii=False)
        with open(os.path.join(fixtures_dir, "known_stats.json"), "w", encoding="utf-8") as fh:
            json.dump({"success": True, "message": "ok", "data": stats}, fh, ensure_ascii=False)
        for label, detail in detail_fixtures.items():
            with open(os.path.join(fixtures_dir, f"known_detail_{label}.json"), "w", encoding="utf-8") as fh:
                json.dump({"success": True, "message": "ok", "data": detail}, fh, ensure_ascii=False)

    print()
    print(f"JSONL    : {jsonl_path}")
    print(f"report   : {os.path.join(outdir, 'validation_report.md')}")
    print(f"fixtures : {fixtures_dir}")
    print(f"fatals   : {len(fatals)}, warnings: {len(warns)}, multi-value anomalies: {len(multi_anomalies)}")
    print(f"species  : {len(species_dist)}, chromosomes: {len(chrom_dist)}, refs: {ref_entries}, unique DOIs: {len(unique_dois)}")
    return 1 if fatals else 0


if __name__ == "__main__":
    raise SystemExit(main())
