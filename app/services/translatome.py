"""Manifest-driven data layer for translatome datasets (Phase 2.5).

Each dataset is a folder under ``app/services/data/translatome/`` (overridable
with ``TRANSLATOME_DATA_DIR``)::

    <dataset_id>/manifest.json   # stages, treatments, roles, samples, tables, citations...
    <dataset_id>/genes.tsv.gz    # gene x sample matrix (columns named in manifest.samples)
    <dataset_id>/dtg.tsv.gz...   # optional tables declared in manifest.tables

``registry.json`` lists the datasets (order, status, version).  The service and
the HTTP/MCP layer never hard-code a stage, treatment, TE column or table: add
a folder + manifest + registry entry and the same API/UI serve the new dataset.
"""
from __future__ import annotations

import csv
import gzip
import json
import logging
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)

# Registry + manifests ship with the code; the large .tsv.gz assets live outside
# the repo on the web node (TRANSLATOME_DATA_DIR).
DEFAULT_REGISTRY_ROOT = Path(__file__).resolve().parent / "data" / "translatome"
DEFAULT_ASSETS_ROOT = Path("/var/www/data/translatome")
VISIBLE_STATUSES = ("public", "prototype")
BASE_MATRIX_COLUMNS = {
    "gene02g": "gene02g",
    "gene03g": "gene03g",
    "description": "description",
    "chromosome": "chromosome",
    "start": "start",
    "end": "end",
    "is_lc": "is_lc",
}


class TranslatomeDataUnavailable(RuntimeError):
    """Raised when the registry/manifest/assets are missing from the deployment."""


class GeneRecord(NamedTuple):
    gene02g: str
    gene03g: str
    description: str
    chromosome: str
    start: int | None
    end: int | None
    is_lc: bool
    values: tuple[float | None, ...]


# ---------------------------------------------------------------------------
# basic helpers
# ---------------------------------------------------------------------------
def registry_root() -> Path:
    """Directory holding registry.json + per-dataset manifest.json (in the repo)."""
    return Path(os.environ.get("TRANSLATOME_REGISTRY_DIR") or DEFAULT_REGISTRY_ROOT)


def data_root() -> Path:
    """Directory holding the gzipped data assets (outside the repo on the web node)."""
    value = os.environ.get("TRANSLATOME_DATA_DIR")
    if value:
        return Path(value)
    try:  # .env / server configuration
        from app.core.config import settings

        return Path(settings.TRANSLATOME_DATA_DIR)
    except Exception:  # pragma: no cover - config needs DB_PASSWORD in some contexts
        return DEFAULT_ASSETS_ROOT


def _dataset_dir(dataset_id: str) -> Path:
    """Assets folder for one dataset: <TRANSLATOME_DATA_DIR>/<dataset_id>."""
    return data_root() / dataset_id


def _manifest_dir(dataset_id: str) -> Path:
    """Manifest folder for one dataset: <registry_root>/<dataset_id>."""
    return registry_root() / dataset_id


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() == "NA":
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    return None if number is None else int(round(number))


def _read_gzip_tsv(path: Path) -> tuple[list[str], list[list[str]]]:
    if not path.exists():
        raise TranslatomeDataUnavailable(
            f"Translatome data asset missing: {path} "
            f"(assets live outside the repo; set TRANSLATOME_DATA_DIR to the server data directory)"
        )
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader, None)
        if not header:
            raise TranslatomeDataUnavailable(f"Translatome data asset is empty: {path}")
        return header, [row for row in reader if row]


def _normalise_gene(gene: str) -> str:
    text = str(gene).strip().upper()
    if text.endswith(".1"):
        text = text[:-2]
    return text


def _log2_fold_change(control: float | None, treated: float | None) -> float | None:
    if control is None or treated is None:
        return None
    return round(math.log2((treated + 0.01) / (control + 0.01)), 4)


def _log2_ratio(treated: float | None, control: float | None) -> float | None:
    if treated is None or control is None or treated <= 0 or control <= 0:
        return None
    return round(math.log2(treated / control), 4)


def _page_slice(rows: list[Any], page: int, per_page: int) -> tuple[list[Any], dict[str, int]]:
    total = len(rows)
    start = max(page - 1, 0) * per_page
    return rows[start:start + per_page], {
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, math.ceil(total / per_page)) if total else 0,
    }


def clear_caches() -> None:
    """Drop every cached registry/manifest/dataset (tests and hot reloads)."""
    _registry.cache_clear()
    load_manifest.cache_clear()
    load_dataset.cache_clear()


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _registry() -> dict[str, Any]:
    path = registry_root() / "registry.json"
    if not path.exists():
        raise TranslatomeDataUnavailable(
            f"Translatome registry missing: {path} (registry/manifests ship with the repo; "
            f"set TRANSLATOME_REGISTRY_DIR only if they live elsewhere)"
        )
    registry = json.loads(path.read_text(encoding="utf-8"))
    if "datasets" not in registry:
        raise TranslatomeDataUnavailable(f"Translatome registry has no 'datasets': {path}")
    return registry


def _entries() -> list[dict[str, Any]]:
    return list(_registry().get("datasets", []))


def _entry(dataset_id: str) -> dict[str, Any] | None:
    for entry in _entries():
        if entry.get("id") == dataset_id:
            return entry
    return None


def list_datasets(include_hidden: bool = False) -> list[dict[str, Any]]:
    """Return visible datasets (public/prototype) enriched with manifest counts."""
    items: list[dict[str, Any]] = []
    for entry in sorted(_entries(), key=lambda item: (item.get("order", 999), item.get("id", ""))):
        status = entry.get("status", "prototype")
        if not include_hidden and status not in VISIBLE_STATUSES:
            continue
        item = dict(entry)
        try:
            manifest = load_manifest(entry["id"])
            item.update({
                "title": manifest.get("title", entry.get("title")),
                "short_title": manifest.get("short_title", entry.get("short_title")),
                "species": manifest.get("species", entry.get("species")),
                "tissue": manifest.get("tissue", entry.get("tissue")),
                "assays": manifest.get("assays", []),
                "stages": [stage.get("label", stage.get("id")) for stage in manifest.get("stages", [])],
                "counts": manifest.get("counts", {}),
                "version": manifest.get("version", entry.get("version")),
                "assets_ready": assets_ready(entry["id"]),
            })
        except (TranslatomeDataUnavailable, ValueError):
            item.setdefault("counts", {})
        items.append(item)
    return items


def default_dataset_id() -> str:
    visible = list_datasets()
    if not visible:
        raise TranslatomeDataUnavailable("No visible translatome datasets in registry")
    for item in visible:
        if item.get("status") == "public":
            return item["id"]
    return visible[0]["id"]


def resolve_dataset_id(dataset_id: str | None) -> str:
    if dataset_id:
        if _entry(dataset_id) is None:
            raise ValueError(f"Unknown translatome dataset: {dataset_id}")
        return dataset_id
    return default_dataset_id()


# ---------------------------------------------------------------------------
# manifest / dataset loading
# ---------------------------------------------------------------------------
@lru_cache(maxsize=16)
def load_manifest(dataset_id: str) -> dict[str, Any]:
    entry = _entry(dataset_id)
    if entry is None:
        raise ValueError(f"Unknown translatome dataset: {dataset_id}")
    path = _manifest_dir(dataset_id) / "manifest.json"
    if not path.exists():
        raise TranslatomeDataUnavailable(
            f"Translatome manifest missing: {path} (manifests ship with the repo)"
        )
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("id") != dataset_id:
        raise TranslatomeDataUnavailable(
            f"Manifest id mismatch: registry '{dataset_id}' vs manifest '{manifest.get('id')}'"
        )
    return manifest


def _load_table(base: Path, manifest: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    file_id = spec.get("file_id")
    file_entry = (manifest.get("files") or {}).get(file_id or "")
    if not file_entry:
        raise TranslatomeDataUnavailable(f"Table '{spec.get('id')}' has no file entry in manifest.files")
    header, rows = _read_gzip_tsv(base / file_entry["file"])
    idx = {name: position for position, name in enumerate(header)}
    gene_columns = {**BASE_MATRIX_COLUMNS, **spec.get("gene_columns", {})}
    parsed: list[dict[str, str]] = []
    by_gene: dict[str, dict[str, str]] = {}
    by_gene02g: dict[str, dict[str, str]] = {}
    for row in rows:
        item = {name: (row[idx[name]] if name in idx else "") for name in header}
        parsed.append(item)
        g3 = item.get(gene_columns["gene03g"], "").strip()
        g2 = item.get(gene_columns["gene02g"], "").strip()
        if g3:
            by_gene.setdefault(g3, item)
        if g2:
            by_gene02g.setdefault(g2, item)
    return {
        "spec": spec,
        "header": header,
        "rows": parsed,
        "by_gene": by_gene,
        "by_gene02g": by_gene02g,
    }


@lru_cache(maxsize=4)
def load_dataset(dataset_id: str) -> dict[str, Any]:
    manifest = load_manifest(dataset_id)
    base = _dataset_dir(dataset_id)
    files = manifest.get("files") or {}
    matrix_entry = files.get("matrix")
    if not matrix_entry:
        raise TranslatomeDataUnavailable(f"Dataset '{dataset_id}' has no matrix file in manifest.files")
    header, rows = _read_gzip_tsv(base / matrix_entry["file"])
    idx = {name: position for position, name in enumerate(header)}
    gene_columns = {**BASE_MATRIX_COLUMNS, **matrix_entry.get("gene_columns", {})}
    samples = manifest.get("samples") or []
    missing_columns = [sample["column"] for sample in samples if sample.get("column") not in idx]
    if missing_columns:
        raise TranslatomeDataUnavailable(
            f"Dataset '{dataset_id}' manifest references missing matrix columns: {missing_columns[:5]}"
        )
    sample_positions = [idx[sample["column"]] for sample in samples]
    records: list[GeneRecord] = []
    by_02g: dict[str, int] = {}
    by_03g: dict[str, int] = {}
    for row in rows:
        if len(row) < len(header):
            continue
        values = tuple(_to_float(row[position]) for position in sample_positions)
        record = GeneRecord(
            gene02g=row[idx[gene_columns["gene02g"]]].strip(),
            gene03g=row[idx[gene_columns["gene03g"]]].strip(),
            description=row[idx[gene_columns["description"]]].strip(),
            chromosome=row[idx[gene_columns["chromosome"]]].strip() if gene_columns["chromosome"] in idx else "",
            start=_to_int(row[idx[gene_columns["start"]]]) if gene_columns["start"] in idx else None,
            end=_to_int(row[idx[gene_columns["end"]]]) if gene_columns["end"] in idx else None,
            is_lc=row[idx[gene_columns["is_lc"]]].strip() == "1" if gene_columns["is_lc"] in idx else False,
            values=values,
        )
        position = len(records)
        records.append(record)
        if record.gene02g:
            by_02g.setdefault(record.gene02g.upper(), position)
        if record.gene03g:
            by_03g.setdefault(record.gene03g.upper(), position)

    sample_by_key: dict[tuple[str, str, str], int] = {}
    for position, sample in enumerate(samples):
        key = (sample.get("stage", ""), sample.get("treatment", ""), sample.get("role", ""))
        sample_by_key.setdefault(key, position)

    tables: dict[str, dict[str, Any]] = {}
    for spec in manifest.get("tables") or []:
        tables[spec["id"]] = _load_table(base, manifest, spec)

    logger.info("translatome dataset '%s' loaded: %s genes, %s tables", dataset_id, len(records), len(tables))
    return {
        "id": dataset_id,
        "manifest": manifest,
        "records": records,
        "by_02g": by_02g,
        "by_03g": by_03g,
        "sample_by_key": sample_by_key,
        "samples": samples,
        "tables": tables,
    }


# ---------------------------------------------------------------------------
# gene payload / search
# ---------------------------------------------------------------------------
def resolve_gene(dataset_id: str, gene: str) -> GeneRecord | None:
    dataset = load_dataset(dataset_id)
    key = _normalise_gene(gene)
    position = dataset["by_03g"].get(key)
    if position is None:
        position = dataset["by_02g"].get(key)
    return None if position is None else dataset["records"][position]


def _table_hits(dataset: dict[str, Any], record: GeneRecord) -> dict[str, Any]:
    hits: dict[str, Any] = {}
    for table_id, loaded in dataset["tables"].items():
        spec = loaded["spec"]
        row = loaded["by_gene"].get(record.gene03g) or loaded["by_gene02g"].get(record.gene02g)
        if row is None:
            continue
        kind = spec.get("kind")
        if kind == "dtg":
            cluster_column = spec.get("cluster_column", "cluster")
            stages: dict[str, Any] = {}
            for stage_id, columns in (spec.get("stage_columns") or {}).items():
                padj = _to_float(row.get(columns.get("padj", ""), ""))
                log2fc = _to_float(row.get(columns.get("log2fc", ""), ""))
                if padj is None and log2fc is None:
                    continue
                stages[stage_id] = {"padj": padj, "log2fc": log2fc}
            if stages:
                hits[table_id] = {"kind": kind, "label": spec.get("label", table_id),
                                  "cluster": row.get(cluster_column, ""), "stages": stages}
        elif kind == "deg":
            comparisons: dict[str, Any] = {}
            for comp in spec.get("comparisons") or []:
                log2fc = _to_float(row.get(comp.get("log2fc_column", ""), ""))
                padj = _to_float(row.get(comp.get("padj_column", ""), ""))
                if log2fc is None and padj is None:
                    continue
                comparisons[comp["id"]] = {
                    "label": comp.get("label", comp["id"]),
                    "assay": comp.get("assay"),
                    "stage": comp.get("stage"),
                    "log2fc": log2fc,
                    "padj": padj,
                }
            if comparisons:
                hits[table_id] = {"kind": kind, "label": spec.get("label", table_id),
                                  "comparisons": comparisons}
    return hits


def gene_payload(dataset_id: str, record: GeneRecord) -> dict[str, Any]:
    dataset = load_dataset(dataset_id)
    manifest = dataset["manifest"]
    stages: list[dict[str, Any]] = []
    for stage in manifest.get("stages") or []:
        stage_id = stage["id"]
        metrics: dict[str, Any] = {}
        for role in manifest.get("roles") or []:
            role_id = role["id"]
            values: dict[str, float | None] = {}
            for treatment in manifest.get("treatments") or []:
                position = dataset["sample_by_key"].get((stage_id, treatment["id"], role_id))
                values[treatment["id"]] = record.values[position] if position is not None else None
            contrasts: dict[str, float | None] = {}
            for contrast in manifest.get("contrasts") or []:
                control_value = values.get(contrast.get("control", ""))
                treated_value = values.get(contrast.get("treated", ""))
                if role.get("metric") == "te":
                    contrasts[contrast["id"]] = _log2_ratio(treated_value, control_value)
                else:
                    contrasts[contrast["id"]] = _log2_fold_change(control_value, treated_value)
            metrics[role_id] = {
                "label": role.get("label", role_id),
                "unit": role.get("unit", ""),
                "metric": role.get("metric", "fpkm"),
                "values": values,
                "contrasts": contrasts,
                "missing": {treatment_id: value is None for treatment_id, value in values.items()},
            }
        stages.append({"stage": stage_id, "label": stage.get("label", stage_id), "metrics": metrics})
    return {
        "gene02g": record.gene02g,
        "gene03g": record.gene03g,
        "description": record.description,
        "chromosome": record.chromosome,
        "start": record.start,
        "end": record.end,
        "is_lc": record.is_lc,
        "roles": manifest.get("roles") or [],
        "treatments": manifest.get("treatments") or [],
        "contrasts": manifest.get("contrasts") or [],
        "stages": stages,
        "table_hits": _table_hits(dataset, record),
    }


def query_genes(dataset_id: str, gene_ids: list[str]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    not_found: list[str] = []
    seen: set[str] = set()
    for gene in gene_ids:
        key = _normalise_gene(gene)
        if not key or key in seen:
            continue
        seen.add(key)
        record = resolve_gene(dataset_id, key)
        if record is None:
            not_found.append(gene)
        else:
            results.append(gene_payload(dataset_id, record))
    return {"dataset": dataset_id, "genes_found": len(results), "genes_not_found": not_found, "results": results}


def search_genes(dataset_id: str, query: str, limit: int = 20) -> list[dict[str, Any]]:
    dataset = load_dataset(dataset_id)
    text = _normalise_gene(query)
    if not text:
        return []
    needle = query.strip().lower()
    exact: list[GeneRecord] = []
    prefix: list[GeneRecord] = []
    description: list[GeneRecord] = []
    seen: set[str] = set()
    record = resolve_gene(dataset_id, text)
    if record is not None:
        exact.append(record)
        seen.add(record.gene03g)
    for candidate in dataset["records"]:
        if candidate.gene03g in seen:
            continue
        if candidate.gene02g.upper().startswith(text) or candidate.gene03g.upper().startswith(text):
            prefix.append(candidate)
        elif needle and needle in candidate.description.lower():
            description.append(candidate)
        if len(prefix) >= limit and len(description) >= limit:
            break

    def light(item: GeneRecord) -> dict[str, Any]:
        return {
            "gene02g": item.gene02g,
            "gene03g": item.gene03g,
            "description": item.description,
            "chromosome": item.chromosome,
            "is_lc": item.is_lc,
        }

    return [light(item) for item in (exact + prefix + description)[:limit]]


# ---------------------------------------------------------------------------
# optional tables (DTG/DEG/... declared in the manifest)
# ---------------------------------------------------------------------------
def table_catalog(dataset_id: str) -> list[dict[str, Any]]:
    manifest = load_manifest(dataset_id)
    catalog: list[dict[str, Any]] = []
    for spec in manifest.get("tables") or []:
        item = {
            "id": spec["id"],
            "kind": spec.get("kind"),
            "label": spec.get("label", spec["id"]),
            "description": spec.get("description", ""),
        }
        if spec.get("kind") == "dtg":
            item["stages"] = list((spec.get("stage_columns") or {}).keys())
        elif spec.get("kind") == "deg":
            item["comparisons"] = [
                {"id": comp["id"], "label": comp.get("label", comp["id"]),
                 "assay": comp.get("assay"), "stage": comp.get("stage")}
                for comp in spec.get("comparisons") or []
            ]
        catalog.append(item)
    return catalog


def find_table_by_kind(dataset_id: str, kind: str) -> str | None:
    for spec in load_manifest(dataset_id).get("tables") or []:
        if spec.get("kind") == kind:
            return spec["id"]
    return None


def _direction_matches(value: float | None, direction: str) -> bool:
    if value is None:
        return direction in ("both", "")
    if direction == "up":
        return value > 0
    if direction == "down":
        return value < 0
    return True


def query_table(
    dataset_id: str,
    table_id: str,
    *,
    stage: str | None = None,
    comparison: str | None = None,
    direction: str = "both",
    cluster: str | None = None,
    gene: str | None = None,
    padj_max: float = 0.05,
    min_abs_log2fc: float = 0.0,
    page: int = 1,
    per_page: int = 25,
) -> dict[str, Any]:
    dataset = load_dataset(dataset_id)
    loaded = dataset["tables"].get(table_id)
    if loaded is None:
        raise ValueError(f"Unknown table: {table_id}")
    spec = loaded["spec"]
    kind = spec.get("kind")
    gene_key = _normalise_gene(gene) if gene else ""
    rows: list[dict[str, Any]] = []

    if kind == "dtg":
        stages = spec.get("stage_columns") or {}
        stage_id = stage or next(iter(stages), None)
        if stage_id not in stages:
            raise ValueError(f"stage must be one of {list(stages)}")
        columns = stages[stage_id]
        cluster_column = spec.get("cluster_column", "cluster")
        for item in loaded["rows"]:
            padj = _to_float(item.get(columns.get("padj", ""), ""))
            log2fc = _to_float(item.get(columns.get("log2fc", ""), ""))
            if padj is None or log2fc is None or padj > padj_max or abs(log2fc) < min_abs_log2fc:
                continue
            if not _direction_matches(log2fc, direction):
                continue
            row_cluster = item.get(cluster_column, "")
            if cluster and row_cluster != cluster.strip():
                continue
            g3 = item.get("gene03g", "")
            g2 = item.get("gene02g", "")
            if gene_key and not (g3.upper().startswith(gene_key) or g2.upper().startswith(gene_key)):
                continue
            rows.append({
                "gene02g": g2,
                "gene03g": g3,
                "description": item.get("description", ""),
                "table_id": table_id,
                "kind": "dtg",
                "stage": stage_id,
                "cluster": row_cluster,
                "padj": padj,
                "log2fc": round(log2fc, 4),
            })
        rows.sort(key=lambda row: abs(row["log2fc"]), reverse=True)
        filters = {"stage": stage_id, "direction": direction, "cluster": cluster or "",
                   "gene": gene or "", "padj_max": padj_max, "min_abs_log2fc": min_abs_log2fc}
    elif kind == "deg":
        comparisons = spec.get("comparisons") or []
        by_id = {comp["id"]: comp for comp in comparisons}
        comparison_id = comparison or next(iter(by_id), None)
        if comparison_id not in by_id:
            raise ValueError(f"comparison must be one of {list(by_id)}")
        comp = by_id[comparison_id]
        for item in loaded["rows"]:
            log2fc = _to_float(item.get(comp.get("log2fc_column", ""), ""))
            padj = _to_float(item.get(comp.get("padj_column", ""), ""))
            if log2fc is None or padj is None or padj > padj_max or abs(log2fc) < min_abs_log2fc:
                continue
            if not _direction_matches(log2fc, direction):
                continue
            g3 = item.get("gene03g", "")
            g2 = item.get("gene02g", "")
            if gene_key and not (g3.upper().startswith(gene_key) or g2.upper().startswith(gene_key)):
                continue
            rows.append({
                "gene02g": g2,
                "gene03g": g3,
                "description": item.get("description", ""),
                "table_id": table_id,
                "kind": "deg",
                "comparison": comparison_id,
                "comparison_label": comp.get("label", comparison_id),
                "assay": comp.get("assay"),
                "stage": comp.get("stage"),
                "padj": padj,
                "log2fc": round(log2fc, 4),
            })
        rows.sort(key=lambda row: abs(row["log2fc"]), reverse=True)
        filters = {"comparison": comparison_id, "direction": direction, "gene": gene or "",
                   "padj_max": padj_max, "min_abs_log2fc": min_abs_log2fc}
    else:
        raise ValueError(f"Unsupported table kind for query: {kind}")

    rows_page, pagination = _page_slice(rows, page, per_page)
    return {
        "dataset": dataset_id,
        "table": {"id": table_id, "kind": kind, "label": spec.get("label", table_id)},
        "filters": filters,
        "items": rows_page,
        "pagination": pagination,
    }


# ---------------------------------------------------------------------------
# metadata / downloads
# ---------------------------------------------------------------------------
def dataset_meta(dataset_id: str) -> dict[str, Any]:
    """Manifest-only metadata (does not require the data assets to be present)."""
    manifest = load_manifest(dataset_id)
    meta = dict(manifest)
    meta["dataset"] = dataset_id
    meta["available_tables"] = table_catalog(dataset_id)
    meta["counts"] = dict(manifest.get("counts") or {})
    meta["counts"]["samples"] = len(manifest.get("samples") or [])
    meta["assets_ready"] = assets_ready(dataset_id)
    return meta


def assets_ready(dataset_id: str) -> bool:
    """True when every file declared in manifest.files exists under TRANSLATOME_DATA_DIR."""
    try:
        manifest = load_manifest(dataset_id)
    except (TranslatomeDataUnavailable, ValueError):
        return False
    files = manifest.get("files") or {}
    base = _dataset_dir(dataset_id)
    return bool(files) and all((base / entry["file"]).is_file() for entry in files.values() if entry.get("file"))


def download_file(dataset_id: str, file_id: str) -> tuple[Path, str]:
    manifest = load_manifest(dataset_id)
    aliases = {"genes": "matrix"}
    file_id = aliases.get(file_id, file_id)
    entry = (manifest.get("files") or {}).get(file_id)
    if not entry:
        raise ValueError(f"Unknown translatome file: {file_id}")
    path = _dataset_dir(dataset_id) / entry["file"]
    if not path.exists():
        raise TranslatomeDataUnavailable(
            f"Translatome data asset missing: {path} "
            f"(assets live outside the repo; set TRANSLATOME_DATA_DIR to the server data directory)"
        )
    download_name = entry.get("download_name") or f"{dataset_id}_{entry['file']}"
    return path, download_name
