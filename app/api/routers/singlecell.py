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

import json
import re

from fastapi import APIRouter, Query

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
