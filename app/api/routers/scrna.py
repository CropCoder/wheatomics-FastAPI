"""scRNA single-cell gene expression routes.

Port of the legacy PHP scRNA module (``/var/www/html/scRNA``). Data lives on
the filesystem under ``SCRNNA_DATA_DIR``:

  * ``<genome>/<folder>/dotplot_data.tsv``  — per-dataset dotplot matrix
  * ``<genome>/*/*.csv|tsv``                — marker-gene annotation tables

The dotplot TSV is filtered by gene on the fly; no MySQL is involved.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterator, List

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.exceptions import ResourceNotFound, ValidationFailure
from app.core.response import ok

router = APIRouter(prefix="/scrna", tags=["scRNA"])

# 基因组/数据集配置（对应原 index.php 的 $config）
SCRNNA_GENOMES = {
    "Chinese_Spring": {
        "label": "Chinese Spring",
        "datasets": {
            "root": {
                "label": "Organization: root Doi: 10.1016/j.celrep.2025.115240",
                "url": "https://linkinghub.elsevier.com/retrieve/pii/S2211124725000117",
            }
        },
    },
    "Kronos": {
        "label": "Kronos",
        "datasets": {
            "spike": {
                "label": "Organization: spike Doi: 10.1186/s13059-025-03811-3",
                "url": "https://doi.org/10.1186/s13059-025-03811-3",
            }
        },
    },
}

_ANNOTATION_LIMIT = 5000
_ALLOWED_PER_PAGE = (10, 20, 50)


def _split_genes(text: str) -> List[str]:
    """Split a gene list on comma/space/semicolon/newline, dedup preserving order."""
    parts = re.split(r"[\s,;，；]+", (text or "").strip())
    seen = set()
    out: List[str] = []
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _detect_delimiter(path: Path) -> str:
    try:
        sample = path.read_text(encoding="utf-8", errors="ignore")[:4096]
    except OSError:
        return "\t"
    return "\t" if sample.count("\t") >= sample.count(",") else ","


def _annotation_files(base_dir: Path) -> List[Path]:
    files: List[Path] = []
    if not base_dir.is_dir():
        return files
    for subdir in sorted(base_dir.iterdir()):
        if not subdir.is_dir():
            continue
        for f in sorted(subdir.iterdir()):
            if f.suffix.lower() in (".csv", ".tsv") and f.name != "dotplot_data.tsv":
                files.append(f)
    return files


def _load_annotation_rows(base_dir: Path, limit: int = _ANNOTATION_LIMIT) -> dict:
    """Merge all annotation CSV/TSV files into a single header + rows list."""
    header: List[str] = []
    rows: List[List[str]] = []
    count = 0
    for f in _annotation_files(base_dir):
        if count >= limit:
            break
        delimiter = _detect_delimiter(f)
        try:
            fh = f.open("r", encoding="utf-8", errors="ignore", newline="")
        except OSError:
            continue
        with fh:
            reader = csv.reader(fh, delimiter=delimiter)
            try:
                file_header = next(reader)
            except StopIteration:
                continue
            file_header = [c.strip() for c in file_header]
            if not header:
                header = file_header
            col_count = len(header)
            for row in reader:
                if count >= limit:
                    break
                normalized = [row[i] if i < len(row) else "" for i in range(col_count)]
                rows.append(normalized)
                count += 1
    return {"header": header, "rows": rows}


def _dataset_dirs(base_dir: Path, genome: str) -> dict:
    """Dataset directories: config-defined first, then any other subdirectories."""
    dirs: dict = {}
    config = SCRNNA_GENOMES.get(genome, {})
    for folder in config.get("datasets", {}):
        d = base_dir / folder
        if d.is_dir():
            dirs[folder] = d
    if base_dir.is_dir():
        for d in sorted(base_dir.iterdir()):
            if d.is_dir() and d.name not in dirs:
                dirs[d.name] = d
    return dirs


def _float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _read_dotplot(dir_path: Path, genes: List[str]) -> dict:
    """Read dotplot_data.tsv filtered by gene set."""
    file = dir_path / "dotplot_data.tsv"
    result: dict = {
        "rows": [],
        "found_genes": [],
        "missing_genes": list(genes),
        "clusters": [],
        "has_file": file.is_file(),
        "error": "",
    }
    if not file.is_file():
        result["error"] = "dotplot_data.tsv was not found."
        return result
    if not genes:
        result["error"] = "No gene submitted."
        return result

    gene_set = set(genes)
    found = set()
    clusters = set()
    rows: List[dict] = []

    try:
        fh = file.open("r", encoding="utf-8", errors="ignore", newline="")
    except OSError:
        result["error"] = "Cannot open dotplot_data.tsv."
        return result

    with fh:
        reader = csv.reader(fh, delimiter="\t")
        try:
            header = next(reader)
        except StopIteration:
            result["error"] = "Invalid dotplot_data.tsv header."
            return result
        header = [c.strip() for c in header]
        col = {name: i for i, name in enumerate(header)}
        required = ["gene", "cluster", "avg_exp", "pct_exp", "avg_exp_scaled"]
        for c in required:
            if c not in col:
                result["error"] = f"Missing required column: {c}"
                return result
        for row in reader:
            gene = (row[col["gene"]] if col["gene"] < len(row) else "").strip()
            if gene not in gene_set:
                continue
            cluster = (row[col["cluster"]] if col["cluster"] < len(row) else "").strip()
            if cluster and cluster not in clusters:
                clusters.add(cluster)
            found.add(gene)
            rows.append({
                "gene": gene,
                "cluster": cluster,
                "avg_exp": _float(row[col["avg_exp"]] if col["avg_exp"] < len(row) else 0),
                "pct_exp": _float(row[col["pct_exp"]] if col["pct_exp"] < len(row) else 0),
                "avg_exp_scaled": _float(row[col["avg_exp_scaled"]] if col["avg_exp_scaled"] < len(row) else 0),
            })

    result["rows"] = rows
    result["found_genes"] = [g for g in genes if g in found]
    result["missing_genes"] = [g for g in genes if g not in found]
    result["clusters"] = list(clusters)
    return result


def _iter_filtered_tsv(file: Path, gene_set: set) -> Iterator[str]:
    with file.open("r", encoding="utf-8", errors="ignore", newline="") as fh:
        header_line = fh.readline()
        yield header_line
        header = header_line.rstrip("\n").split("\t")
        gene_col = header.index("gene") if "gene" in header else -1
        for line in fh:
            if gene_col < 0:
                continue
            cols = line.rstrip("\n").split("\t")
            if gene_col < len(cols) and cols[gene_col].strip() in gene_set:
                yield line


@router.get("/genomes")
def api_genomes():
    """列出可用的 scRNA 基因组及其数据集。"""
    return ok({"genomes": SCRNNA_GENOMES})


@router.get("/annotation")
def api_annotation(
    genome: str = Query(..., description="Genome key, e.g. Chinese_Spring"),
    page: int = Query(1, ge=1),
    per_page: int = Query(10),
):
    """marker gene 预览表（合并该基因组下所有 annotation CSV/TSV，分页）。"""
    if genome not in SCRNNA_GENOMES:
        raise ValidationFailure(f"Unknown genome: {genome!r}")
    if per_page not in _ALLOWED_PER_PAGE:
        per_page = 10

    base_dir = settings.SCRNNA_DATA_DIR / genome
    data = _load_annotation_rows(base_dir)
    header = data["header"]
    rows = data["rows"]
    total_rows = len(rows)
    total_pages = max(1, (total_rows + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page
    return ok({
        "genome": genome,
        "header": header,
        "rows": rows[offset:offset + per_page],
        "total_rows": total_rows,
        "total_pages": total_pages,
        "page": page,
        "per_page": per_page,
    })


@router.get("/dotplot")
def api_dotplot(
    genome: str = Query(..., description="Genome key, e.g. Chinese_Spring"),
    genes: str = Query(..., description="Comma/space/newline separated gene IDs"),
):
    """按基因查询各数据集的 dotplot 数据。"""
    if genome not in SCRNNA_GENOMES:
        raise ValidationFailure(f"Unknown genome: {genome!r}")
    gene_list = _split_genes(genes)
    if not gene_list:
        raise ValidationFailure("No gene submitted.")

    base_dir = settings.SCRNNA_DATA_DIR / genome
    config = SCRNNA_GENOMES[genome]
    dataset_dirs = _dataset_dirs(base_dir, genome)

    datasets = []
    has_any_result = False
    for folder, dir_path in dataset_dirs.items():
        meta = config.get("datasets", {}).get(folder, {})
        dot = _read_dotplot(dir_path, gene_list)
        if dot["rows"]:
            has_any_result = True
        datasets.append({
            "folder": folder,
            "label": meta.get("label", f"Organization: {folder}"),
            "url": meta.get("url", ""),
            **dot,
        })

    return ok({
        "genome": genome,
        "genes": gene_list,
        "has_any_result": has_any_result,
        "datasets": datasets,
    })


@router.get("/dotplot/download")
def api_dotplot_download(
    genome: str = Query(...),
    folder: str = Query(...),
    genes: str = Query(...),
):
    """下载按基因过滤后的 dotplot TSV。"""
    if genome not in SCRNNA_GENOMES:
        raise ValidationFailure(f"Unknown genome: {genome!r}")
    gene_list = _split_genes(genes)
    if not gene_list:
        raise ValidationFailure("No gene submitted.")

    dir_path = settings.SCRNNA_DATA_DIR / genome / folder
    file = dir_path / "dotplot_data.tsv"
    if not file.is_file():
        raise ResourceNotFound("Data file not found.")

    gene_set = set(gene_list)
    filename = f"dotplot_{genome}_{folder}.tsv"
    return StreamingResponse(
        _iter_filtered_tsv(file, gene_set),
        media_type="text/tab-separated-values; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
