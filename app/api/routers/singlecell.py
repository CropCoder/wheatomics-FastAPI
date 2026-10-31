"""Single-cell wheat atlas: per-gene expression, co-expression modules, hub genes.

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

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.exceptions import ValidationFailure
from app.core.response import ok
from app.db.mysql import mysql_cursor

router = APIRouter(prefix="/singlecell", tags=["Single-cell atlas"])

_GENE_RE = re.compile(r"^[A-Za-z0-9_.:-]{3,80}$")


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


def _samples(cur) -> list[dict]:
    cur.execute(
        "SELECT sample, imported_at, expression_rows, network_count "
        "FROM scrna_samples ORDER BY sample"
    )
    return [
        {
            "sample": r["sample"],
            "imported_at": r["imported_at"],
            "expression_rows": r["expression_rows"],
            "network_count": r["network_count"],
        }
        for r in cur.fetchall()
    ]


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
    """List every imported single-cell dataset."""
    with mysql_cursor(settings.DB_SCRNA_DATA) as cur:
        samples = _samples(cur)
    return ok({"total": len(samples), "samples": samples})


@router.get("/gene/{gene_id}")
def gene_profile(gene_id: str) -> dict:
    """Expression by sample/cell type, co-expression modules and hub status."""
    g = _gene_id(gene_id)

    with mysql_cursor(settings.DB_SCRNA_DATA) as cur:
        samples = _samples(cur)
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
        modules.append({
            "sample": r["sample"],
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
        hubs.append({
            "sample": r["sample"],
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
    return ok({
        "gene": g,
        "found": bool(expression_rows or modules or hubs),
        "samples": samples,
        "expression_by_sample": expression_by_sample,
        "modules": modules,
        "hub_genes": hubs,
        "summary": {
            "celltypes": celltypes,
            "samples_with_expression": sorted(expression_by_sample),
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


@router.get("/module/genes")
def api_module_genes(sample: str, celltype_key: str, module: str) -> dict:
    """Every gene of one co-expression module (a GO/KEGG-ready gene set)."""
    s = _param(sample, "sample")
    k = _param(celltype_key, "celltype_key")
    m = _param(module, "module")
    with mysql_cursor(settings.DB_SCRNA_DATA) as cur:
        genes = _module_genes(cur, s, k, m)
    return ok({"sample": s, "celltype_key": k, "module": m,
               "count": len(genes), "genes": genes})


@router.get("/module/genes.csv")
def api_module_genes_csv(sample: str, celltype_key: str, module: str) -> StreamingResponse:
    s = _param(sample, "sample")
    k = _param(celltype_key, "celltype_key")
    m = _param(module, "module")
    with mysql_cursor(settings.DB_SCRNA_DATA) as cur:
        genes = _module_genes(cur, s, k, m)
    return _csv_response(
        _safe_filename(s, k, m) + ".csv", _GENESET_HEADER, _geneset_rows(genes))


@router.get("/hub/genes")
def api_hub_genes(sample: str, celltype_key: str) -> dict:
    """Every hub gene of one cell type (a GO/KEGG-ready gene set)."""
    s = _param(sample, "sample")
    k = _param(celltype_key, "celltype_key")
    with mysql_cursor(settings.DB_SCRNA_DATA) as cur:
        genes = _hub_genes(cur, s, k)
    return ok({"sample": s, "celltype_key": k,
               "count": len(genes), "genes": genes})


@router.get("/hub/genes.csv")
def api_hub_genes_csv(sample: str, celltype_key: str) -> StreamingResponse:
    s = _param(sample, "sample")
    k = _param(celltype_key, "celltype_key")
    with mysql_cursor(settings.DB_SCRNA_DATA) as cur:
        genes = _hub_genes(cur, s, k)
    return _csv_response(
        _safe_filename(s, k, "hub_genes") + ".csv", _GENESET_HEADER,
        _geneset_rows(genes))
