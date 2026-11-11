"""scRNA-seq wheat atlas: per-gene expression, co-expression modules, hub genes.

Backed by the ``scrna_data`` MySQL database:

  scrna_samples             one row per imported dataset
  scrna_dotplot_expression  per gene x cell type averages
  scrna_networks            cell type key -> label, module/hub row counts
  scrna_gene_modules        gene -> module rows; attributes JSON holds kME_<module>
  scrna_hub_genes           gene -> hub rows; attributes JSON holds kME

Samples are read from ``scrna_samples`` on every request and no query hard-codes
a sample name, so newly imported datasets appear without a code change.
"""

from __future__ import annotations

import csv
import io
import json
import re
from functools import lru_cache

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.routers.go_kegg import EnrichmentError, enrich_go, enrich_kegg
from app.core.config import settings
from app.core.exceptions import ValidationFailure
from app.core.response import ok
from app.db.mysql import mysql_cursor

router = APIRouter(prefix="/scRNA-seq", tags=["scRNA-seq atlas"])

_GENE_RE = re.compile(r"^[A-Za-z0-9_.:-]{3,80}$")


# ---------------------------------------------------------------------------
# Display grouping
#
# class.txt maps each imported sample onto a user-facing dataset ("display")
# and a short within-dataset label ("type"). It may also carry study metadata
# for the display (description / Title / DOI / link), which the page shows
# above the dot plot:
#
#     display<TAB>type<TAB>sample<TAB>description<TAB>Title<TAB>DOI<TAB>link
#
# One display owns several samples (e.g. the salt-stress experiment has CK and
# NaCl runs), so the UI picks a display and plots all of its types together.
# ---------------------------------------------------------------------------
CLASS_FIELDS = ("description", "title", "doi", "link")

# class.txt ends each description with a "Data: <accession>." sentence; the
# page shows the biological context only, so that last sentence is dropped.
_DATA_SENTENCE = re.compile(r"\s*\bData:\s*[^.]*\.?")

# The descriptions also spell out how many cells/nuclei/clusters/cell types the
# study recovered. The page shows the experimental context only, so those
# count clauses are removed. Each rule targets a phrasing seen in class.txt.
_COUNT_RULES = (
    # "3,954 (CK) and 4,258 (T6) cells were obtained, 5,451 retained after filtering."
    (re.compile(r"\s*\b\d[\d,]*(?:\s*\([^)]*\))?"
                r"(?:\s*and\s+\d[\d,]*(?:\s*\([^)]*\))?)?"
                r"\s+(?:cells|nuclei)\s+were\s+obtained\b[^.]*\.", re.I), ""),
    # ", yielding 13,063 cells in 19 clusters annotated as 12 cell types."
    (re.compile(r",?\s*\byielding\b[^.]*\.", re.I), ""),
    # "26,009 cells were assigned to 23 clusters, "
    (re.compile(r"\b\d[\d,]*\s+(?:cells|nuclei)\s+were\s+assigned\s+to\s+"
                r"\d[\d,]*\s+clusters,\s*", re.I), ""),
    # "resolving 22 cell types and cell-type-specific regulatory networks"
    (re.compile(r"\bresolving\s+\d[\d,]*\s+cell\s+types\s+and\s+", re.I), "resolving "),
    # This module plots scRNA-seq only, so the snATAC-seq arm is irrelevant.
    (re.compile(r"\s*and\s+snATAC-seq\s*\([^)]*\)", re.I), ""),
)


def _clean_description(text: str) -> str:
    text = _DATA_SENTENCE.sub("", text or "")
    for rule, replacement in _COUNT_RULES:
        text = rule.sub(replacement, text)
    # Tidy the punctuation left behind by a removed clause.
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    if text and not text.endswith((".", "!", "?")):
        text += "."
    return text


@lru_cache(maxsize=4)
def _read_class(path: str, mtime: int) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh, delimiter="\t")
        header = next(reader, None)
        if not header:
            return rows
        lower = [h.strip().lower() for h in header]

        def index(*names: str) -> int:
            for name in names:
                if name in lower:
                    return lower.index(name)
            return -1

        di, ti, si = index("display"), index("type"), index("sample")
        if min(di, ti, si) < 0:
            return rows
        extra = (index("description"), index("title"), index("doi"),
                 index("link", "url"))

        def cell(row: list[str], i: int) -> str:
            return row[i].strip() if 0 <= i < len(row) else ""

        for row in reader:
            display, typ, sample = cell(row, di), cell(row, ti), cell(row, si)
            if sample:
                rows.append((display or sample, typ or sample, sample,
                             *[cell(row, i) for i in extra]))
    return rows


def class_map() -> dict:
    """{'by_sample': {sample: {display, type}}, 'displays': [{display, entries, ...}]}"""
    path = settings.SCRNNA_CLASS_FILE
    by_sample: dict[str, dict] = {}
    order: list[str] = []
    meta: dict[str, dict] = {}
    if path.is_file():
        for display, typ, sample, *rest in _read_class(str(path), path.stat().st_mtime_ns):
            if sample not in by_sample:
                by_sample[sample] = {"display": display, "type": typ}
            if display not in order:
                order.append(display)
            slot = meta.setdefault(display, {k: "" for k in CLASS_FIELDS})
            for key, value in zip(CLASS_FIELDS, rest):
                if value and not slot[key]:
                    slot[key] = value
    displays = []
    for display in order:
        entries = [{"type": v["type"], "sample": s}
                   for s, v in by_sample.items() if v["display"] == display]
        info = dict(meta[display])
        info["description"] = _clean_description(info["description"])
        displays.append({"display": display, "entries": entries, **info})
    return {"by_sample": by_sample, "displays": displays}


def _label(sample: str, mapping: dict) -> tuple[str, str]:
    """(display, type) for a sample; falls back to the sample name."""
    entry = mapping.get(sample)
    if entry:
        return entry["display"], entry["type"]
    return sample, sample


def _gene_id(value: str) -> str:
    value = (value or "").strip()
    if not _GENE_RE.match(value):
        raise ValidationFailure(
            f"Invalid gene ID: {value!r}. Expected an IWGSC ID such as "
            "TraesCS3D03G0096000."
        )
    return value


def _attrs(raw) -> dict:
    """attributes is a JSON column; pymysql may hand it back as str or bytes."""
    if raw is None:
        return {}
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "ignore")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _samples(cur, mapping: dict) -> list[dict]:
    cur.execute(
        "SELECT sample, imported_at, expression_rows, network_count "
        "FROM scrna_samples ORDER BY sample"
    )
    out = []
    for r in cur.fetchall():
        display, typ = _label(r["sample"], mapping)
        out.append({
            "sample": r["sample"],
            "display": display,
            "type": typ,
            "imported_at": r["imported_at"],
            "expression_rows": r["expression_rows"],
            "network_count": r["network_count"],
        })
    return out


def _celltype_labels(cur) -> dict:
    """(sample, celltype_key) -> display label."""
    cur.execute(
        "SELECT sample, celltype_key, celltype_label FROM scrna_networks"
    )
    return {
        (r["sample"], r["celltype_key"]): (r["celltype_label"] or r["celltype_key"])
        for r in cur.fetchall()
    }


@router.get("/samples")
def list_samples() -> dict:
    """List every imported single-cell dataset with its display grouping."""
    mapping = class_map()
    with mysql_cursor(settings.DB_SCRNA_DATA) as cur:
        samples = _samples(cur, mapping["by_sample"])
    return ok({"total": len(samples),
               "samples": samples,
               "displays": mapping["displays"]})


@router.get("/displays")
def list_displays() -> dict:
    """Datasets (display) with their samples/types, as maintained in class.txt."""
    mapping = class_map()
    return ok({"total": len(mapping["displays"]),
               "displays": mapping["displays"]})


@router.get("/gene/{gene_id}")
def gene_profile(gene_id: str) -> dict:
    """Expression by sample/cell type, co-expression modules and hub status."""
    g = _gene_id(gene_id)
    mapping = class_map()

    with mysql_cursor(settings.DB_SCRNA_DATA) as cur:
        samples = _samples(cur, mapping["by_sample"])
        labels = _celltype_labels(cur)

        cur.execute(
            "SELECT sample, celltype, n_cells, n_expr_cells, pct_expr, "
            "       mean_normalized, avg_log1p "
            "FROM scrna_dotplot_expression WHERE gene_id = %s "
            "ORDER BY sample, celltype",
            (g,),
        )
        expression_rows = cur.fetchall()

        cur.execute(
            "SELECT sample, celltype_key, module_name, attributes "
            "FROM scrna_gene_modules WHERE gene_id = %s",
            (g,),
        )
        module_rows = cur.fetchall()

        cur.execute(
            "SELECT sample, celltype_key, module_name, attributes "
            "FROM scrna_hub_genes WHERE gene_id = %s",
            (g,),
        )
        hub_rows = cur.fetchall()

        # Sizes of the gene sets behind each row, so the UI can show how many
        # genes a module/hub set holds before offering it for GO/KEGG export.
        module_sizes: dict[tuple, dict] = {}
        for pair in {(r["sample"], r["celltype_key"]) for r in module_rows}:
            cur.execute(
                "SELECT module_name, COUNT(*) AS n FROM scrna_gene_modules "
                "WHERE sample = %s AND celltype_key = %s GROUP BY module_name",
                pair,
            )
            module_sizes[pair] = {x["module_name"]: x["n"] for x in cur.fetchall()}

        hub_sizes: dict[tuple, int] = {}
        for pair in {(r["sample"], r["celltype_key"]) for r in hub_rows}:
            cur.execute(
                "SELECT COUNT(*) AS n FROM scrna_hub_genes "
                "WHERE sample = %s AND celltype_key = %s",
                pair,
            )
            row = cur.fetchone()
            hub_sizes[pair] = row["n"] if row else 0

    expression_by_sample: dict[str, list[dict]] = {}
    for r in expression_rows:
        expression_by_sample.setdefault(r["sample"], []).append({
            "celltype": r["celltype"],
            "n_cells": r["n_cells"],
            "n_expr_cells": r["n_expr_cells"],
            "pct_expr": _num(r["pct_expr"]),
            "mean_normalized": _num(r["mean_normalized"]),
            "avg_log1p": _num(r["avg_log1p"]),
        })

    modules = []
    for r in module_rows:
        a = _attrs(r["attributes"])
        module = r["module_name"] or a.get("module") or ""
        display, typ = _label(r["sample"], mapping["by_sample"])
        modules.append({
            "sample": r["sample"],
            "display": display,
            "type": typ,
            "celltype_key": r["celltype_key"],
            "celltype_label": labels.get((r["sample"], r["celltype_key"]),
                                         r["celltype_key"]),
            "module": module,
            "kME": _num(a.get("kME_" + module)) if module else None,
            "gene_name": a.get("gene_name"),
            "n_genes": module_sizes.get((r["sample"], r["celltype_key"]), {}).get(module),
        })
    modules.sort(key=lambda m: (m["sample"], m["celltype_label"], m["module"]))

    hubs = []
    for r in hub_rows:
        a = _attrs(r["attributes"])
        display, typ = _label(r["sample"], mapping["by_sample"])
        hubs.append({
            "sample": r["sample"],
            "display": display,
            "type": typ,
            "celltype_key": r["celltype_key"],
            "celltype_label": labels.get((r["sample"], r["celltype_key"]),
                                         r["celltype_key"]),
            "module": r["module_name"] or a.get("module") or "",
            "kME": _num(a.get("kME")),
            "gene_name": a.get("gene_name"),
            "n_genes": hub_sizes.get((r["sample"], r["celltype_key"])),
        })
    hubs.sort(key=lambda h: (h["sample"], h["celltype_label"]))

    celltypes = sorted({e["celltype"] for e in expression_rows})
    imported = {s["sample"] for s in samples}
    displays = [
        {"display": d["display"],
         "entries": [e for e in d["entries"] if e["sample"] in imported],
         **{k: d.get(k, "") for k in CLASS_FIELDS}}
        for d in mapping["displays"]
    ]
    displays = [d for d in displays if d["entries"]]
    disp_of = {s["sample"]: s["display"] for s in samples}
    expr_samples = set(expression_by_sample)
    displays_with_expression = sorted({disp_of[s] for s in expr_samples if s in disp_of})

    return ok({
        "gene": g,
        "found": bool(expression_rows or modules or hubs),
        "samples": samples,
        "displays": displays,
        "expression_by_sample": expression_by_sample,
        "modules": modules,
        "hub_genes": hubs,
        "summary": {
            "celltypes": celltypes,
            "samples_with_expression": sorted(expr_samples),
            "displays_with_expression": displays_with_expression,
            "n_celltypes": len(celltypes),
            "n_modules": len(modules),
            "n_hubs": len(hubs),
            "is_hub": bool(hubs),
            "hub_celltypes": sorted({h["celltype_label"] for h in hubs}),
        },
    })


# ---------------------------------------------------------------------------
# Gene sets behind a module or a cell type's hub list. These are the inputs a
# user pastes into the GO/KEGG enrichment page, so they download as plain lists.
# ---------------------------------------------------------------------------
_PARAM_RE = re.compile(r"^[A-Za-z0-9_.:\- ]{1,190}$")


def _param(value: str, label: str) -> str:
    value = (value or "").strip()
    if not _PARAM_RE.match(value):
        raise ValidationFailure(f"Invalid {label}: {value!r}")
    return value


def _module_genes(cur, sample: str, celltype_key: str, module: str) -> list[dict]:
    cur.execute(
        "SELECT gene_id, module_name, attributes FROM scrna_gene_modules "
        "WHERE sample = %s AND celltype_key = %s AND module_name = %s "
        "ORDER BY gene_id",
        (sample, celltype_key, module),
    )
    out = []
    for r in cur.fetchall():
        a = _attrs(r["attributes"])
        name = r["module_name"] or ""
        out.append({
            "gene_id": r["gene_id"],
            "module": name,
            "kME": _num(a.get("kME_" + name)) if name else None,
            "gene_name": a.get("gene_name"),
        })
    return out


def _hub_genes(cur, sample: str, celltype_key: str) -> list[dict]:
    cur.execute(
        "SELECT gene_id, module_name, attributes FROM scrna_hub_genes "
        "WHERE sample = %s AND celltype_key = %s ORDER BY gene_id",
        (sample, celltype_key),
    )
    out = []
    for r in cur.fetchall():
        a = _attrs(r["attributes"])
        out.append({
            "gene_id": r["gene_id"],
            "module": r["module_name"] or a.get("module") or "",
            "kME": _num(a.get("kME")),
            "gene_name": a.get("gene_name"),
        })
    return out


def _safe_filename(*parts: str) -> str:
    cleaned = [re.sub(r"[^A-Za-z0-9_.-]+", "_", p).strip("_") for p in parts]
    return "_".join(x for x in cleaned if x) or "geneset"


def _strip_key(celltype_key: str) -> str:
    """Drop the trailing hash from a cell type key: Epi_cells_3e2b16a2 -> Epi_cells."""
    return re.sub(r"_[0-9a-fA-F]{6,}$", "", celltype_key or "")


def _celltype_label(cur, sample: str, celltype_key: str) -> str:
    cur.execute(
        "SELECT celltype_label FROM scrna_networks "
        "WHERE sample = %s AND celltype_key = %s",
        (sample, celltype_key),
    )
    row = cur.fetchone()
    if row and row["celltype_label"]:
        return row["celltype_label"]
    return _strip_key(celltype_key)


def _csv_response(filename: str, header: list[str], rows: list[list]) -> StreamingResponse:
    def gen():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(header)
        yield "﻿" + buf.getvalue()
        for row in rows:
            buf.seek(0)
            buf.truncate(0)
            writer.writerow(row)
            yield buf.getvalue()
    return StreamingResponse(
        gen(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


_GENESET_HEADER = ["gene_id", "module", "kME", "gene_name"]


def _geneset_rows(genes: list[dict]) -> list[list]:
    return [[g["gene_id"], g["module"], g["kME"], g["gene_name"] or ""] for g in genes]


# ---------------------------------------------------------------------------
# GO / KEGG enrichment on module and hub gene sets
#
# The scRNA-seq tables use IWGSC RefSeq v2.1 (03G) gene IDs, while
# wheat_function's gene_go / gene_kegg tables are keyed by v1.1 (02G).
# CS_2G_3G_MAP is the two-column translation table that bridges them.
# ---------------------------------------------------------------------------
_GENE_SUFFIX = re.compile(r"\.\d+$")


@lru_cache(maxsize=4)
def _read_cs_map(path: str, mtime: int) -> dict[str, str]:
    """03G gene ID -> 02G gene ID (the TSV lists CS-2G first, CS-3G second)."""
    table: dict[str, str] = {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh, delimiter="\t")
        header = next(reader, None) or []
        lower = [h.strip().lower() for h in header]
        col2 = next((i for i, h in enumerate(lower) if "02g" in h), 0)
        col3 = next((i for i, h in enumerate(lower) if "03g" in h), 1)
        for row in reader:
            if len(row) <= max(col2, col3):
                continue
            g2, g3 = row[col2].strip(), row[col3].strip()
            if g2 and g3:
                table[g3] = g2
    return table


def _annotation_ids(genes: list[str]) -> tuple[list[str], dict]:
    """Map gene IDs onto the 02G annotation space used by GO/KEGG.

    Both the bare ID and the ".1" transcript form are emitted: the annotation
    tables store whichever form their pipeline produced, and the enrichment
    queries match ``gene_id`` exactly. Genes without a mapping are counted so
    the page can say how much of the set was actually tested.
    """
    path = settings.CS_2G_3G_MAP
    table = _read_cs_map(str(path), path.stat().st_mtime_ns) if path.is_file() else {}
    ids: list[str] = []
    seen: set[str] = set()
    mapped = 0
    for gene in genes:
        base = _GENE_SUFFIX.sub("", gene)
        target = table.get(base) if table else base
        if target is None:
            continue
        mapped += 1
        for form in (target, target + ".1"):
            if form not in seen:
                seen.add(form)
                ids.append(form)
    return ids, {"genes": len(genes), "mapped": mapped,
                 "unmapped": len(genes) - mapped}


_ANNOT_TABLES = {"go": "gene_go", "kegg": "gene_kegg"}


def _annotated_ids(ids: list[str], database: str) -> list[str]:
    """Keep only the IDs that exist in the GO/KEGG annotation table.

    Called before the enrichment so its 2000-gene input limit applies to the
    annotated subset (the mapping step emits two ID forms per gene) and so the
    page can report exactly how many genes carry an annotation.
    """
    table = _ANNOT_TABLES[database]
    found: list[str] = []
    with mysql_cursor(settings.DB_WHEAT_FUNCTION) as cur:
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            ph = ",".join(["%s"] * len(chunk))
            cur.execute(
                f"SELECT DISTINCT gene_id FROM `{table}` WHERE gene_id IN ({ph})",
                chunk,
            )
            found.extend(row["gene_id"] for row in cur.fetchall())
    return found


@router.get("/enrich")
def api_enrich(sample: str, celltype_key: str, module: str = "",
               kind: str = "module", database: str = "go",
               padj_threshold: float = 0.05) -> dict:
    """Run GO or KEGG enrichment on one co-expression module or hub gene set."""
    if kind not in ("module", "hub"):
        raise ValidationFailure(f"Unsupported gene set: {kind}")
    if database not in ("go", "kegg"):
        raise ValidationFailure(f"Unsupported database: {database}")
    if not 0 < padj_threshold <= 1:
        raise ValidationFailure("padj_threshold must be in (0, 1]")
    s = _param(sample, "sample")
    k = _param(celltype_key, "celltype_key")
    with mysql_cursor(settings.DB_SCRNA_DATA) as cur:
        if kind == "module":
            module = _param(module, "module")
            items = _module_genes(cur, s, k, module)
        else:
            module = ""
            items = _hub_genes(cur, s, k)
        label = _celltype_label(cur, s, k)

    genes = [item["gene_id"] for item in items]
    ids, stats = _annotation_ids(genes)
    payload = {"kind": kind, "sample": s, "celltype_key": k,
               "celltype_label": label, "module": module,
               "database": database, "padj_threshold": padj_threshold,
               "stats": stats, "N": 0, "n": 0, "annotated": 0, "results": []}
    if not ids:
        return ok(payload)

    annotated = _annotated_ids(ids, database)
    stats["annotated"] = len(annotated)
    payload["annotated"] = len(annotated)
    if not annotated:
        return ok(payload)
    if len(annotated) > 2000:
        raise ValidationFailure(
            f"{len(annotated)} annotated genes is above the 2000-gene enrichment "
            "limit; narrow the gene set first"
        )
    try:
        result = (enrich_go if database == "go" else enrich_kegg)(annotated, padj_threshold)
    except EnrichmentError as exc:
        raise ValidationFailure(str(exc))
    payload.update({"N": result["N"], "n": result["n"],
                    "results": result["results"]})
    return ok(payload)


@router.get("/module/genes")
def api_module_genes(sample: str, celltype_key: str, module: str) -> dict:
    """Every gene of one co-expression module (a GO/KEGG-ready gene set)."""
    s = _param(sample, "sample")
    k = _param(celltype_key, "celltype_key")
    m = _param(module, "module")
    with mysql_cursor(settings.DB_SCRNA_DATA) as cur:
        genes = _module_genes(cur, s, k, m)
        label = _celltype_label(cur, s, k)
    return ok({"sample": s, "celltype_key": k, "celltype_label": label,
               "module": m, "count": len(genes), "genes": genes})


@router.get("/module/genes.csv")
def api_module_genes_csv(sample: str, celltype_key: str, module: str) -> StreamingResponse:
    s = _param(sample, "sample")
    k = _param(celltype_key, "celltype_key")
    m = _param(module, "module")
    with mysql_cursor(settings.DB_SCRNA_DATA) as cur:
        genes = _module_genes(cur, s, k, m)
        label = _celltype_label(cur, s, k)
    return _csv_response(
        _safe_filename(s, label, m) + ".csv", _GENESET_HEADER, _geneset_rows(genes))


@router.get("/hub/genes")
def api_hub_genes(sample: str, celltype_key: str) -> dict:
    """Every hub gene of one cell type (a GO/KEGG-ready gene set)."""
    s = _param(sample, "sample")
    k = _param(celltype_key, "celltype_key")
    with mysql_cursor(settings.DB_SCRNA_DATA) as cur:
        genes = _hub_genes(cur, s, k)
        label = _celltype_label(cur, s, k)
    return ok({"sample": s, "celltype_key": k, "celltype_label": label,
               "count": len(genes), "genes": genes})


@router.get("/hub/genes.csv")
def api_hub_genes_csv(sample: str, celltype_key: str) -> StreamingResponse:
    s = _param(sample, "sample")
    k = _param(celltype_key, "celltype_key")
    with mysql_cursor(settings.DB_SCRNA_DATA) as cur:
        genes = _hub_genes(cur, s, k)
        label = _celltype_label(cur, s, k)
    return _csv_response(
        _safe_filename(s, label, "hub_genes") + ".csv", _GENESET_HEADER,
        _geneset_rows(genes))


# ---------------------------------------------------------------------------
# Batch lookup: a summary row per gene so a pasted list can be screened quickly.
# ---------------------------------------------------------------------------
BATCH_LIMIT = 50


def _parse_genes(raw: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"[\s,;]+", raw or "") if p.strip()]
    ids: list[str] = []
    for p in parts:
        if p not in ids:
            ids.append(p)
    if not ids:
        raise ValidationFailure("No gene IDs provided")
    if len(ids) > BATCH_LIMIT:
        raise ValidationFailure(
            f"Too many gene IDs ({len(ids)}); maximum is {BATCH_LIMIT} per query")
    for p in ids:
        if not _GENE_RE.match(p):
            raise ValidationFailure(f"Invalid gene ID: {p!r}")
    return ids


@router.get("/genes")
def genes_batch(genes: str) -> dict:
    """Summarise up to 50 genes: datasets, cell types, modules and hub status."""
    ids = _parse_genes(genes)
    mapping = class_map()
    ph = ",".join(["%s"] * len(ids))

    with mysql_cursor(settings.DB_SCRNA_DATA) as cur:
        cur.execute(
            f"SELECT gene_id, sample FROM scrna_dotplot_expression "
            f"WHERE gene_id IN ({ph}) GROUP BY gene_id, sample", ids)
        expr_pairs = cur.fetchall()

        cur.execute(
            f"SELECT gene_id, COUNT(DISTINCT celltype) AS nct "
            f"FROM scrna_dotplot_expression WHERE gene_id IN ({ph}) "
            f"GROUP BY gene_id", ids)
        expr_counts = {r["gene_id"]: r["nct"] for r in cur.fetchall()}

        cur.execute(
            f"SELECT gene_id, COUNT(*) AS n FROM scrna_gene_modules "
            f"WHERE gene_id IN ({ph}) GROUP BY gene_id", ids)
        module_counts = {r["gene_id"]: r["n"] for r in cur.fetchall()}

        cur.execute(
            f"SELECT gene_id, sample, celltype_key FROM scrna_hub_genes "
            f"WHERE gene_id IN ({ph})", ids)
        hub_rows = cur.fetchall()
        labels = _celltype_labels(cur)

    samples_of: dict[str, list[str]] = {}
    for r in expr_pairs:
        samples_of.setdefault(r["gene_id"], []).append(r["sample"])

    hubs_of: dict[str, list[str]] = {}
    hub_count: dict[str, int] = {}
    for r in hub_rows:
        gid = r["gene_id"]
        hub_count[gid] = hub_count.get(gid, 0) + 1
        label = labels.get((r["sample"], r["celltype_key"]),
                           _strip_key(r["celltype_key"]))
        bucket = hubs_of.setdefault(gid, [])
        if label not in bucket:
            bucket.append(label)

    out = []
    for g in ids:
        sams = sorted(samples_of.get(g, []))
        displays: list[str] = []
        for s in sams:
            display, _ = _label(s, mapping["by_sample"])
            if display not in displays:
                displays.append(display)
        hub_labels = sorted(hubs_of.get(g, []))
        out.append({
            "gene": g,
            "found": bool(sams or module_counts.get(g) or hub_labels),
            "n_samples": len(sams),
            "displays": displays,
            "n_celltypes": expr_counts.get(g, 0),
            "n_modules": module_counts.get(g, 0),
            "n_hubs": hub_count.get(g, 0),
            "hub_celltypes": hub_labels,
        })
    return ok({"total": len(out), "limit": BATCH_LIMIT, "genes": out})
