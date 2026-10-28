"""Additive Wheat TF mapping and VariantHub-compatible indexed VCF query endpoints.

No guessed TF assignments. Curated mapping TSV is required for wheat gene identities.
No modifications to existing VariantHub router or data files.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/regulatory", tags=["Wheat Regulatory Integration"])
DB = Path(os.environ.get("WHEAT_REGULATORY_DB", "/var/www/html/wheat-regulatory-hub/data/processed/regulatory.sqlite"))
MAP = Path(os.environ.get("WHEAT_TF_MAPPING_TSV", "/var/www/html/wheat-regulatory-hub/data/processed/tf_motif_mapping.tsv"))
CATALOG = Path(os.environ.get("WHEAT_VARIANT_DATASETS_JSON", "/var/www/html/wheat-regulatory-hub/data/processed/variant_datasets.json"))
REQUIRED = ("motif_id", "wheat_tf_gene_id", "evidence_type", "source", "source_tf", "tf_family")
GENE = re.compile(r"^[A-Za-z0-9_.-]{3,100}$")
CHROM = re.compile(r"^(?:chr)?[1-7][ABD]$", re.IGNORECASE)


def load_mappings():
    result = defaultdict(list)
    if not MAP.is_file():
        return result, "mapping_file_missing"
    with MAP.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames or any(k not in reader.fieldnames for k in REQUIRED):
            raise HTTPException(503, "TF mapping TSV schema is invalid")
        for row in reader:
            if not all((row.get(k) or "").strip() for k in ("motif_id", "wheat_tf_gene_id", "evidence_type", "source")):
                continue
            if not GENE.fullmatch(row["wheat_tf_gene_id"]):
                continue
            result[row["motif_id"]].append({k: row.get(k, "") for k in REQUIRED})
    return result, "curated_mapping_loaded"


def load_catalog():
    if not CATALOG.is_file():
        return []
    try:
        entries = json.loads(CATALOG.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            raise ValueError("Catalog must be a JSON list")
        result = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            dataset_id = entry.get("dataset_id", "")
            assembly = entry.get("assembly", "")
            vcf = Path(entry.get("vcf_path", ""))
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", dataset_id):
                continue
            if assembly != "IWGSC RefSeq v1.0":
                continue
            if not vcf.is_absolute() or not vcf.is_file():
                continue
            if not (Path(str(vcf) + ".tbi").is_file() or Path(str(vcf) + ".csi").is_file()):
                continue
            result.append({"dataset_id": dataset_id, "assembly": assembly, "vcf_path": str(vcf)})
        return result
    except (OSError, ValueError, TypeError) as exc:
        raise HTTPException(503, "Invalid variant dataset catalog") from exc


@router.get("/gene/{gene_id}/candidate-tfs")
def candidate_tfs(gene_id: str, limit: int = Query(10000, ge=1, le=100000)):
    if not GENE.fullmatch(gene_id):
        raise HTTPException(400, "Invalid gene ID")
    if not DB.is_file():
        raise HTTPException(503, "Regulatory SQLite database missing")
    mappings, status = load_mappings()
    try:
        with sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5) as conn:
            exists = conn.execute("SELECT 1 FROM genes WHERE gene_id=? LIMIT 1", (gene_id,)).fetchone()
            if not exists:
                raise HTTPException(404, "Gene not found")
            rows = conn.execute(
                """SELECT DISTINCT h.motif_id
                   FROM hits h JOIN regions r ON h.region_id=r.region_id
                   WHERE r.gene_id=? LIMIT ?""", (gene_id, limit)
            ).fetchall()
    except sqlite3.Error as exc:
        raise HTTPException(503, "Regulatory database query failed") from exc
    ids = [r[0] for r in rows]
    matched = {mid: mappings[mid] for mid in ids if mappings.get(mid)}
    return {
        "gene_id": gene_id, "assembly": "IWGSC RefSeq v1.0", "status": status,
        "total_motif_models_checked": len(ids),
        "mapped_motif_models": len(matched), "mappings": matched,
        "note": "Candidate TF mapping is not experimental evidence of binding at this locus."
    }


@router.get("/variant-datasets")
def variant_datasets():
    return {"items": [{"dataset_id": d["dataset_id"], "assembly": d["assembly"]} for d in load_catalog()]}


@router.get("/variants/overlap")
def variants_overlap(
    dataset_id: str,
    assembly: str,
    chrom: str,
    start0: int = Query(ge=0),
    end0: int = Query(gt=0),
    limit: int = Query(100, ge=1, le=1000)
):
    if end0 <= start0 or end0 - start0 > 100000:
        raise HTTPException(400, "Invalid interval (maximum 100 kb)")
    if not CHROM.fullmatch(chrom):
        raise HTTPException(400, "Invalid chromosome")
    data = next((d for d in load_catalog() if d["dataset_id"] == dataset_id), None)
    if data is None:
        raise HTTPException(404, "Unknown or unconfigured dataset")
    if assembly != data["assembly"]:
        raise HTTPException(400, "Reference assembly mismatch")
    try:
        import pysam
    except ImportError as exc:
        raise HTTPException(503, "pysam unavailable in production environment") from exc
    records = []
    try:
        with pysam.VariantFile(data["vcf_path"]) as vcf:
            contigs = set(vcf.header.contigs)
            candidates = [chrom, chrom[3:] if chrom.startswith("chr") else "chr" + chrom]
            actual_chrom = next((c for c in candidates if c in contigs), None)
            if actual_chrom is None:
                raise HTTPException(422, "Chromosome absent from VCF")
            for rec in vcf.fetch(actual_chrom, start0, end0):
                if rec.stop <= start0 or rec.start >= end0:
                    continue
                if len(records) >= limit:
                    break
                records.append({
                    "dataset_id": dataset_id, "chrom": chrom, "pos1": rec.pos,
                    "start0": rec.start, "end0": rec.stop, "ref": rec.ref,
                    "alt": ",".join(str(a) for a in (rec.alts or [])),
                    "overlap_type": "genomic_overlap"
                })
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "Indexed VCF query failed; inspect VCF and index") from exc
    return {
        "dataset_id": dataset_id, "assembly": assembly, "chrom": chrom,
        "start0": start0, "end0": end0, "items": records, "limit": limit,
        "note": "Genomic overlap only. REF/ALT PWM effect not calculated."
    }


@router.get("/tf/search")
def search_wheat_tf(q: str = Query("", max_length=100), family: str = Query("", max_length=80),
                    limit: int = Query(50, ge=1, le=200)):
    """Search curated wheat TF atlas; no automatic motif-name-as-TF substitution."""
    atlas = Path(os.environ.get(
        "WHEAT_TF_ATLAS_TSV",
        "/var/www/html/wheat-regulatory-hub/data/processed/wheat_tf_atlas.tsv"))
    if not atlas.is_file():
        return {"items": [], "status": "atlas_not_configured"}
    items = []
    with atlas.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"wheat_tf_gene_id", "tf_family", "domain", "annotation_source", "assembly"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise HTTPException(503, "TF atlas TSV schema invalid")
        for row in reader:
            if row.get("assembly") != "IWGSC RefSeq v1.0":
                continue
            if q and q.lower() not in " ".join(str(x) for x in row.values()).lower():
                continue
            if family and family.lower() != row.get("tf_family", "").lower():
                continue
            items.append(row)
            if len(items) >= limit:
                break
    return {"items": items, "status": "curated_atlas", "limit": limit}
