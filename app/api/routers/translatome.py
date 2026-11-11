"""Generic routes for the translatome module (Phase 2.5, manifest-driven).

All endpoints accept an optional ``dataset`` query parameter (default: the first
public/prototype dataset in ``registry.json``), so the same API serves any
number of datasets added under ``app/services/data/translatome/`` without code
changes.  The legacy ``/dtgs`` and ``/degs`` paths remain as thin aliases for
the generic ``/table/{table_id}`` endpoint.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.exceptions import ResourceNotFound, ValidationFailure
from app.core.response import ok
from app.services import translatome as service

router = APIRouter(prefix="/translatome", tags=["Translatome"])

MAX_QUERY_GENES = 100


def _resolve_dataset(dataset: str | None) -> str:
    try:
        return service.resolve_dataset_id(dataset)
    except service.TranslatomeDataUnavailable as exc:  # pragma: no cover - deployment guard
        raise HTTPException(status_code=503, detail=f"Translatome data unavailable: {exc}")
    except ValueError as exc:
        raise ValidationFailure(str(exc))


def _split_gene_ids(raw: str | list[str]) -> list[str]:
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.replace("\n", ",").split(",")]
    else:
        parts = []
        for item in raw:
            parts.extend(part.strip() for part in str(item).replace("\n", ",").split(","))
    return [part for part in parts if part]


@router.get("/datasets")
def list_translatome_datasets(
    include_hidden: bool = Query(False, description="Include draft/retired datasets"),
) -> dict:
    """List all translatome datasets (id, title, species, tissue, assays, counts, status)."""
    try:
        return ok({"datasets": service.list_datasets(include_hidden=include_hidden)})
    except service.TranslatomeDataUnavailable as exc:  # pragma: no cover - deployment guard
        raise HTTPException(status_code=503, detail=f"Translatome data unavailable: {exc}")


@router.get("/meta")
def get_translatome_meta(dataset: str | None = Query(None, description="Dataset id; default = first visible")) -> dict:
    """Return the manifest of one dataset (samples, units, rules, citations, tables, counts)."""
    dataset_id = _resolve_dataset(dataset)
    try:
        return ok(service.dataset_meta(dataset_id))
    except service.TranslatomeDataUnavailable as exc:  # pragma: no cover - deployment guard
        raise HTTPException(status_code=503, detail=f"Translatome data unavailable: {exc}")


@router.get("/query")
def query_translatome(
    gene_ids: str | list[str] = Query(
        ...,
        description="Gene IDs (02G or 03G, comma-separated or repeated); transcript suffix .1 is tolerated.",
    ),
    dataset: str | None = Query(None, description="Dataset id; default = first visible"),
) -> dict:
    """Query one or more genes; always returns both 02G and 03G IDs."""
    genes = _split_gene_ids(gene_ids)
    if not genes:
        raise ResourceNotFound("No valid gene IDs provided")
    if len(genes) > MAX_QUERY_GENES:
        raise ValidationFailure(f"At most {MAX_QUERY_GENES} gene IDs per request")
    dataset_id = _resolve_dataset(dataset)
    try:
        result = service.query_genes(dataset_id, genes)
    except service.TranslatomeDataUnavailable as exc:  # pragma: no cover - deployment guard
        raise HTTPException(status_code=503, detail=str(exc))
    result["query"] = genes
    return ok(result)


@router.get("/search")
def search_translatome_genes(
    q: str = Query(..., min_length=1, description="02G/03G gene ID prefix or description keyword"),
    dataset: str | None = Query(None, description="Dataset id; default = first visible"),
    limit: int = Query(20, ge=1, le=200),
) -> dict:
    """Search genes by ID or annotation keyword; returns both ID versions."""
    dataset_id = _resolve_dataset(dataset)
    try:
        items = service.search_genes(dataset_id, q, limit=limit)
    except service.TranslatomeDataUnavailable as exc:  # pragma: no cover - deployment guard
        raise HTTPException(status_code=503, detail=str(exc))
    return ok({"dataset": dataset_id, "query": q, "items": items})


@router.get("/genes/{gene}")
def get_translatome_gene(
    gene: str,
    dataset: str | None = Query(None, description="Dataset id; default = first visible"),
) -> dict:
    """Fetch one gene by 02G or 03G ID (full matrix payload plus table hits)."""
    dataset_id = _resolve_dataset(dataset)
    try:
        record = service.resolve_gene(dataset_id, gene)
    except service.TranslatomeDataUnavailable as exc:  # pragma: no cover - deployment guard
        raise HTTPException(status_code=503, detail=str(exc))
    if record is None:
        raise ResourceNotFound(f"Gene not found in dataset '{dataset_id}': {gene}")
    return ok(service.gene_payload(dataset_id, record))


@router.get("/tables")
def list_translatome_tables(
    dataset: str | None = Query(None, description="Dataset id; default = first visible"),
) -> dict:
    """List optional tables declared by the dataset manifest (DTG, DEG, ...)."""
    dataset_id = _resolve_dataset(dataset)
    try:
        return ok({"dataset": dataset_id, "tables": service.table_catalog(dataset_id)})
    except service.TranslatomeDataUnavailable as exc:  # pragma: no cover - deployment guard
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/table/{table_id}")
def query_translatome_table(
    table_id: str,
    dataset: str | None = Query(None, description="Dataset id; default = first visible"),
    stage: str | None = Query(None, description="Stage id for kind=dtg tables"),
    comparison: str | None = Query(None, description="Comparison id for kind=deg tables"),
    direction: str = Query("both", description="both | up | down"),
    cluster: str | None = Query(None, description="Cluster filter (kind=dtg)"),
    gene: str | None = Query(None, description="02G/03G gene ID prefix"),
    padj_max: float = Query(0.05, ge=0.0, le=1.0),
    min_abs_log2fc: float = Query(0.0, ge=0.0),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=200),
) -> dict:
    """Generic query for an optional table declared in the manifest."""
    dataset_id = _resolve_dataset(dataset)
    try:
        result = service.query_table(
            dataset_id,
            table_id,
            stage=stage,
            comparison=comparison,
            direction=direction,
            cluster=cluster,
            gene=gene,
            padj_max=padj_max,
            min_abs_log2fc=min_abs_log2fc,
            page=page,
            per_page=per_page,
        )
    except ValueError as exc:
        raise ValidationFailure(str(exc))
    except service.TranslatomeDataUnavailable as exc:  # pragma: no cover - deployment guard
        raise HTTPException(status_code=503, detail=str(exc))
    return ok(result)


@router.get("/dtgs")
def list_dtgs(
    dataset: str | None = Query(None, description="Dataset id; default = first visible"),
    stage: str | None = Query(None, description="Stage id; default = first stage of the table"),
    direction: str = Query("both", description="both | up | down"),
    cluster: str | None = Query(None, description="Co-translation cluster"),
    gene: str | None = Query(None, description="02G/03G gene ID prefix"),
    padj_max: float = Query(0.05, ge=0.0, le=1.0),
    min_abs_log2fc: float = Query(0.0, ge=0.0),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=200),
) -> dict:
    """Backward-compatible alias for the dataset's kind=dtg table."""
    dataset_id = _resolve_dataset(dataset)
    table_id = service.find_table_by_kind(dataset_id, "dtg")
    if not table_id:
        raise ResourceNotFound(f"Dataset '{dataset_id}' has no DTG table")
    try:
        result = service.query_table(
            dataset_id, table_id, stage=stage, direction=direction, cluster=cluster, gene=gene,
            padj_max=padj_max, min_abs_log2fc=min_abs_log2fc, page=page, per_page=per_page,
        )
    except ValueError as exc:
        raise ValidationFailure(str(exc))
    except service.TranslatomeDataUnavailable as exc:  # pragma: no cover - deployment guard
        raise HTTPException(status_code=503, detail=str(exc))
    return ok(result)


@router.get("/degs")
def list_degs(
    dataset: str | None = Query(None, description="Dataset id; default = first visible"),
    comparison: str | None = Query(None, description="Comparison id; default = first comparison"),
    direction: str = Query("both", description="both | up | down"),
    gene: str | None = Query(None, description="02G/03G gene ID prefix"),
    padj_max: float = Query(0.05, ge=0.0, le=1.0),
    min_abs_log2fc: float = Query(0.0, ge=0.0),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=200),
) -> dict:
    """Backward-compatible alias for the dataset's kind=deg table."""
    dataset_id = _resolve_dataset(dataset)
    table_id = service.find_table_by_kind(dataset_id, "deg")
    if not table_id:
        raise ResourceNotFound(f"Dataset '{dataset_id}' has no DEG table")
    try:
        result = service.query_table(
            dataset_id, table_id, comparison=comparison, direction=direction, gene=gene,
            padj_max=padj_max, min_abs_log2fc=min_abs_log2fc, page=page, per_page=per_page,
        )
    except ValueError as exc:
        raise ValidationFailure(str(exc))
    except service.TranslatomeDataUnavailable as exc:  # pragma: no cover - deployment guard
        raise HTTPException(status_code=503, detail=str(exc))
    return ok(result)


@router.get("/download/{dataset_id}/{file_id}")
def download_dataset_file(dataset_id: str, file_id: str) -> FileResponse:
    """Download one file of a dataset (matrix / dtg / deg / ... declared in manifest.files)."""
    try:
        resolved = service.resolve_dataset_id(dataset_id)
        path, download_name = service.download_file(resolved, file_id)
    except ValueError as exc:
        raise ValidationFailure(str(exc))
    except service.TranslatomeDataUnavailable as exc:  # pragma: no cover - deployment guard
        raise HTTPException(status_code=503, detail=str(exc))
    return FileResponse(path, media_type="application/gzip", filename=download_name)


@router.get("/download/{file_id}")
def download_default_dataset_file(file_id: str) -> FileResponse:
    """Backward-compatible download alias for the default dataset."""
    try:
        dataset_id = service.default_dataset_id()
    except service.TranslatomeDataUnavailable as exc:  # pragma: no cover - deployment guard
        raise HTTPException(status_code=503, detail=str(exc))
    return download_dataset_file(dataset_id, file_id)
