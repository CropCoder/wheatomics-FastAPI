#!/usr/bin/env python3
"""Build the manifest + data assets for one translatome dataset.

Output layout (Phase 2.5, manifest-driven)::

    app/services/data/translatome/
      registry.json                         # dataset list (order/status/version)
      chen2025_cs_grain_heat/
        manifest.json                       # samples/stages/treatments/roles/tables/...
        build_report.json

    <TRANSLATOME_DATA_DIR>/               # outside the repo (server data directory)
      chen2025_cs_grain_heat/
        genes.tsv.gz                        # gene x sample matrix
        dtg.tsv.gz / deg.tsv.gz             # optional tables declared in the manifest

The runtime (``app/services/translatome.py``) is fully generic: adding another
dataset means adding a folder like the one above + one registry entry, without
touching Python/HTML.  This builder is dataset-specific (it knows the column
layout of the Chen et al. 2025 Table S1/S2/S3 workbooks); a future dataset with
a different layout should get its own small builder or a shared conversion step.

Example
-------
python3 scripts/heat_translatome/build_data.py \
  --data-xlsx "/path/to/5_10_15DAA...TE.xlsx" \
  --supplementary-xlsx "/path/to/13059_2025_3848_MOESM2_ESM.xlsx" \
  --mapping-tsv "/path/to/gene_map_03g_02g.tsv"
"""
from __future__ import annotations

import argparse
import gzip
import os
import json
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Dataset-specific metadata (the only part that changes per dataset builder)
# ---------------------------------------------------------------------------
DATASET_ID = "chen2025_cs_grain_heat"
STAGES = [
    {"id": "5DAA", "label": "5 DAA", "days_after_anthesis": 5},
    {"id": "10DAA", "label": "10 DAA", "days_after_anthesis": 10},
    {"id": "15DAA", "label": "15 DAA", "days_after_anthesis": 15},
]
TREATMENTS = [
    {"id": "CK", "label": "Control"},
    {"id": "HS", "label": "42 °C, 1 h"},
]
CONTRASTS = [
    {"id": "hs_vs_ck", "control": "CK", "treated": "HS", "label": "HS/CK"},
]
ROLES = [
    {"id": "rna", "label": "RNA-seq FPKM", "assay": "RNA-seq", "unit": "FPKM", "metric": "fpkm"},
    {"id": "ribo", "label": "Ribo-seq FPKM", "assay": "Ribo-seq", "unit": "FPKM", "metric": "fpkm"},
    {"id": "te", "label": "TE (Ribo/RNA)", "assay": "TE", "unit": "ratio", "metric": "te"},
]

STAGE_LOWER = {"5DAA": "5d", "10DAA": "10d", "15DAA": "15d"}

# rows: sample id, label, role, stage, treatment, n_reps, SRA runs, BioProject
_BASE_SAMPLES = [
    ("rna_5d_ck", "RNA 5 DAA CK", "rna", "5DAA", "CK", 3, ["SRR21146765", "SRR21146764", "SRR21146753"], "PRJNA871371"),
    ("rna_10d_ck", "RNA 10 DAA CK", "rna", "10DAA", "CK", 3, ["SRR21146745", "SRR21146744", "SRR21146743"], "PRJNA871371"),
    ("rna_15d_ck", "RNA 15 DAA CK", "rna", "15DAA", "CK", 3, ["SRR21146742", "SRR21146741", "SRR21146740"], "PRJNA871371"),
    ("ribo_5d_ck", "Ribo 5 DAA CK", "ribo", "5DAA", "CK", 2, ["SRR21146755", "SRR21146754"], "PRJNA871371"),
    ("ribo_10d_ck", "Ribo 10 DAA CK", "ribo", "10DAA", "CK", 2, ["SRR21146752", "SRR21146751"], "PRJNA871371"),
    ("ribo_15d_ck", "Ribo 15 DAA CK", "ribo", "15DAA", "CK", 2, ["SRR21146750", "SRR21146749"], "PRJNA871371"),
    ("rna_5d_hs", "RNA 5 DAA HS", "rna", "5DAA", "HS", 3, ["SRR29816650", "SRR29816649", "SRR29816638"], "PRJNA1135409"),
    ("rna_10d_hs", "RNA 10 DAA HS", "rna", "10DAA", "HS", 3, ["SRR29816636", "SRR29816635", "SRR29816634"], "PRJNA1135409"),
    ("rna_15d_hs", "RNA 15 DAA HS", "rna", "15DAA", "HS", 3, ["SRR29816633", "SRR29816632", "SRR29816631"], "PRJNA1135409"),
    ("ribo_5d_hs", "Ribo 5 DAA HS", "ribo", "5DAA", "HS", 2, ["SRR29816630", "SRR29816648"], "PRJNA1135409"),
    ("ribo_10d_hs", "Ribo 10 DAA HS", "ribo", "10DAA", "HS", 2, ["SRR29816647", "SRR29816646"], "PRJNA1135409"),
    ("ribo_15d_hs", "Ribo 15 DAA HS", "ribo", "15DAA", "HS", 2, ["SRR29816645", "SRR29816644"], "PRJNA1135409"),
]
_TE_SAMPLES = [
    ("te_5daa_ck", "TE 5 DAA CK", "te", "5DAA", "CK"),
    ("te_5daa_hs", "TE 5 DAA HS", "te", "5DAA", "HS"),
    ("te_10daa_ck", "TE 10 DAA CK", "te", "10DAA", "CK"),
    ("te_10daa_hs", "TE 10 DAA HS", "te", "10DAA", "HS"),
    ("te_15daa_ck", "TE 15 DAA CK", "te", "15DAA", "CK"),
    ("te_15daa_hs", "TE 15 DAA HS", "te", "15DAA", "HS"),
]


def _source_column(sample: dict[str, Any]) -> str:
    """Map a uniform sample description to a source-workbook column name."""
    stage = sample["stage"]
    treatment = sample["treatment"]
    if sample["role"] == "rna":
        return f"RNA_{STAGE_LOWER[stage]}_{treatment}"
    if sample["role"] == "ribo":
        return f"Ribo_{STAGE_LOWER[stage]}_{treatment}"
    return f"TE_{stage}_{treatment}"


def build_samples() -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for sid, label, role, stage, treatment, n_reps, runs, bioproject in _BASE_SAMPLES:
        sample = {
            "id": sid, "label": label, "role": role,
            "assay": next(r["assay"] for r in ROLES if r["id"] == role),
            "stage": stage, "treatment": treatment, "column": sid,
            "n_reps": n_reps, "sra_runs": runs, "bioproject": bioproject,
        }
        samples.append(sample)
    for sid, label, role, stage, treatment in _TE_SAMPLES:
        samples.append({
            "id": sid, "label": label, "role": role, "assay": "TE",
            "stage": stage, "treatment": treatment, "column": sid,
        })
    return samples


SAMPLES = build_samples()

RNA_COLS = ["RNA_5d_CK", "RNA_5d_HS", "RNA_10d_CK", "RNA_10d_HS", "RNA_15d_CK", "RNA_15d_HS"]
RIBO_COLS = ["Ribo_5d_CK", "Ribo_5d_HS", "Ribo_10d_CK", "Ribo_10d_HS", "Ribo_15d_CK", "Ribo_15d_HS"]
TE_COLS = ["TE_5DAA_CK", "TE_5DAA_HS", "TE_10DAA_CK", "TE_10DAA_HS", "TE_15DAA_CK", "TE_15DAA_HS"]

DTG_STAGES = [("5_CK_vs_HS", "dtg_5daa"), ("10_CK_vs_HS", "dtg_10daa"), ("15_CK_vs_HS", "dtg_15daa")]
DTG_STAGE_KEY = {"5DAA": "5daa", "10DAA": "10daa", "15DAA": "15daa"}
DEG_COMPS = ["RNA_5", "RNA_10", "RNA_15", "Ribo_5", "Ribo_10", "Ribo_15"]
DEG_LABELS = {
    "RNA_5": {"label": "RNA-seq, 5 DAA", "assay": "RNA-seq", "stage": "5DAA"},
    "RNA_10": {"label": "RNA-seq, 10 DAA", "assay": "RNA-seq", "stage": "10DAA"},
    "RNA_15": {"label": "RNA-seq, 15 DAA", "assay": "RNA-seq", "stage": "15DAA"},
    "Ribo_5": {"label": "Ribo-seq, 5 DAA", "assay": "Ribo-seq", "stage": "5DAA"},
    "Ribo_10": {"label": "Ribo-seq, 10 DAA", "assay": "Ribo-seq", "stage": "10DAA"},
    "Ribo_15": {"label": "Ribo-seq, 15 DAA", "assay": "Ribo-seq", "stage": "15DAA"},
}

LINKS = {
    "paper_hs": "https://doi.org/10.1186/s13059-025-03848-4",
    "paper_ck": "https://doi.org/10.1093/plcell/koad075",
    "pubmed_hs": "https://pubmed.ncbi.nlm.nih.gov/41214722/",
    "pubmed_ck": "https://pubmed.ncbi.nlm.nih.gov/36905284/",
    "pmc_hs": "https://pmc.ncbi.nlm.nih.gov/articles/PMC12599102/",
    "pmc_ck": "https://pmc.ncbi.nlm.nih.gov/articles/PMC10226598/",
    "sra_hs": "https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1135409",
    "sra_ck": "https://www.ncbi.nlm.nih.gov/bioproject/PRJNA871371",
    "supplement": (
        "https://static-content.springer.com/esm/art%3A10.1186%2Fs13059-025-03848-4/"
        "MediaObjects/13059_2025_3848_MOESM2_ESM.xlsx"
    ),
    "authors_browser_hs": "https://wheat.cau.edu.cn/heat_stress_response_wheat_grain_translatome_browser/",
    "authors_browser_dev": "https://wheat.cau.edu.cn/wheat_grain_translatome_browser/",
    "genehub": "/GeneHub/gene.html?gene=",
}

CITATION = (
    "Chen Y, Guo Y, Ma M, Wang Y, Guo W, Hu Z, Xin M, Yao Y, Ni Z, Sun Q, Peng H. "
    "Translational regulation plasticity shapes wheat grain adaptation to heat stress. "
    "Genome Biol. 2025;26(1):382. doi:10.1186/s13059-025-03848-4; "
    "Guo Y, Chen Y, Wang Y, Wu X, Zhang X, Mao W, Yu H, Guo K, Xu J, Ma L, Guo W, Hu Z, "
    "Xin M, Yao Y, Ni Z, Sun Q, Peng H. The translational landscape of bread wheat during "
    "grain development. Plant Cell. 2023;35(6):1848-1867. doi:10.1093/plcell/koad075"
)


def _num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value == "" or value.upper() == "NA":
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def _fmt(value: Any) -> str:
    number = _num(value)
    return "" if number is None else f"{number:.10g}"


def _fmt_int(value: Any) -> str:
    number = _num(value)
    return "" if number is None else str(int(round(number)))


def read_source(path: str | Path) -> pd.DataFrame:
    raw = pd.read_excel(path, header=None, engine="openpyxl")
    df = raw.iloc[2:].copy()
    df.columns = list(raw.iloc[1])
    df = df.reset_index(drop=True)
    df["Gene"] = df["Gene"].astype(str).str.strip()
    return df


def read_supplementary(path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    s1_raw = pd.read_excel(path, sheet_name="Table S1", header=None, engine="openpyxl")
    s1 = s1_raw.iloc[4:].copy()
    s1.columns = ["Gene", "Description"] + [str(c) for c in s1_raw.iloc[3, 2:]]
    s1 = s1[s1["Gene"].notna()].reset_index(drop=True)
    s1["Gene"] = s1["Gene"].astype(str).str.strip()

    s2_raw = pd.read_excel(path, sheet_name="Table S2", header=None, engine="openpyxl")
    s2 = s2_raw.iloc[4:].copy()
    s2.columns = ["Gene", "Description"] + [f"{g}_{k}" for g in DEG_COMPS for k in ("Fold_change", "Padj")]
    s2 = s2[s2["Gene"].notna()].reset_index(drop=True)
    s2["Gene"] = s2["Gene"].astype(str).str.strip()

    s3_raw = pd.read_excel(path, sheet_name="Table S3", header=None, engine="openpyxl")
    s3 = s3_raw.iloc[4:].copy()
    s3.columns = ["Gene", "Description", "Cluster"] + [
        f"{st}_{k}" for st in ("5_CK_vs_HS", "10_CK_vs_HS", "15_CK_vs_HS") for k in ("Padj", "log2FC")
    ]
    s3 = s3[s3["Gene"].notna()].reset_index(drop=True)
    s3["Gene"] = s3["Gene"].astype(str).str.strip()
    return s1, s2, s3


def read_mapping(path: str | Path) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    with open(path, encoding="utf-8") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        idx = {name: i for i, name in enumerate(header)}
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if not parts or not parts[0]:
                continue
            g3 = parts[idx["gene03g"]].strip()
            if not g3:
                continue
            mapping[g3] = {
                "g02": parts[idx["gene02g"]].strip(),
                "chrom": parts[idx.get("chrom", 2)].strip(),
                "start": parts[idx.get("start_mb", 3)].strip(),
                "end": parts[idx.get("end_mb", 4)].strip(),
            }
    return mapping


def write_gzip_tsv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.GzipFile(path, "wb", mtime=0) as fh:
        fh.write(("\t".join(header) + "\n").encode("utf-8"))
        for row in rows:
            fh.write(("\t".join(row) + "\n").encode("utf-8"))


def build_manifest(counts: dict[str, int]) -> dict[str, Any]:
    tables = [
        {
            "id": "dtg",
            "kind": "dtg",
            "file_id": "dtg",
            "label": "Differentially translated genes (DTG)",
            "description": "Genes with altered translation efficiency (RiboDiff, FDR < 0.05, |log2FC| > 1); "
                           "cluster = co-translation cluster 1-8.",
            "gene_columns": {"gene02g": "gene02g", "gene03g": "gene03g", "description": "description"},
            "cluster_column": "cluster",
            "stage_columns": {
                stage["id"]: {
                    "padj": f"dtg_{DTG_STAGE_KEY[stage['id']]}_padj",
                    "log2fc": f"dtg_{DTG_STAGE_KEY[stage['id']]}_log2fc",
                }
                for stage in STAGES
            },
        },
        {
            "id": "deg",
            "kind": "deg",
            "file_id": "deg",
            "label": "Differentially expressed genes (DEG)",
            "description": "Genes differentially expressed at the RNA or Ribo level (DESeq2); values are "
                           "signed log2 fold changes (HS vs CK), FDR < 0.05, |log2FC| > 1.",
            "gene_columns": {"gene02g": "gene02g", "gene03g": "gene03g", "description": "description"},
            "comparisons": [
                {
                    "id": comp,
                    "label": DEG_LABELS[comp]["label"],
                    "assay": DEG_LABELS[comp]["assay"],
                    "stage": DEG_LABELS[comp]["stage"],
                    "log2fc_column": f"{comp.lower()}_fold_change",
                    "padj_column": f"{comp.lower()}_padj",
                }
                for comp in DEG_COMPS
            ],
        },
    ]
    return {
        "schema_version": 1,
        "id": DATASET_ID,
        "title": "Heat-stress developing grain translatome (5/10/15 DAA, CK vs 42 °C 1 h)",
        "short_title": "Grain heat-stress translatome",
        "description": (
            "RNA-seq (transcriptome) and Ribo-seq (translatome) of developing wheat grains "
            "(cv. Chinese Spring) at 5, 10 and 15 DAA, control vs. 1-h 42 °C heat stress."
        ),
        "species": "Triticum aestivum",
        "cultivar": "Chinese Spring",
        "genome": "IWGSC RefSeq v2.1 (03G) + platform 02G",
        "tissue": "developing grain",
        "stages": STAGES,
        "treatments": TREATMENTS,
        "assays": ["RNA-seq", "Ribo-seq"],
        "roles": ROLES,
        "contrasts": CONTRASTS,
        "samples": SAMPLES,
        "units": {"rna": "FPKM", "ribo": "FPKM", "te": "ratio (Ribo FPKM / RNA FPKM)"},
        "files": {
            "matrix": {"file": "genes.tsv.gz", "label": f"RNA / Ribo / TE matrix ({counts['genes']:,} genes)"},
            "dtg": {"file": "dtg.tsv.gz", "label": f"DTG table ({counts['dtg']:,} genes, Table S3)"},
            "deg": {"file": "deg.tsv.gz", "label": f"DEG table ({counts['deg']:,} genes, Table S2)"},
        },
        "tables": tables,
        "counts": counts,
        "sources": [
            {
                "role": "RNA-seq and Ribo-seq of heat-treated grains",
                "citation": "Chen Y, et al. Translational regulation plasticity shapes wheat grain "
                            "adaptation to heat stress. Genome Biol. 2025;26(1):382.",
                "doi": "10.1186/s13059-025-03848-4",
                "pmid": "41214722",
                "pmcid": "PMC12599102",
                "bioproject": "PRJNA1135409",
            },
            {
                "role": "RNA-seq and Ribo-seq of developing grains under normal growth conditions",
                "citation": "Guo Y, et al. The translational landscape of bread wheat during grain "
                            "development. Plant Cell. 2023;35(6):1848-1867.",
                "doi": "10.1093/plcell/koad075",
                "pmid": "36905284",
                "pmcid": "PMC10226598",
                "bioproject": "PRJNA871371",
            },
        ],
        "citation": CITATION,
        "links": LINKS,
        "license": {
            "heat_stress": "CC BY-NC-ND 4.0 (Genome Biology 2025)",
            "control": "© American Society of Plant Biologists 2023 (Plant Cell); reuse by permission",
            "note": "Academic, non-commercial display with attribution; contact the corresponding "
                    "author for redistribution/derivative use.",
        },
        "provenance_note": "The data were obtained from Chen et al., 2025 (DOI: 10.1186/s13059-025-03848-4); the only two transformations made here are a "
                           "03G-to-02G gene-ID cross-reference and row/column renaming for web display.",
        "examples": [
            {"label": "TraesCS1A02G001800", "gene": "TraesCS1A02G001800"},
            {"label": "TraesCS1A03G0004000", "gene": "TraesCS1A03G0004000"},
            {"label": "TraesCS1A02G000300", "gene": "TraesCS1A02G000300"},
            {"label": "TraesCS5A02G391700", "gene": "TraesCS5A02G391700"},
        ],
        "version": "v1",
        "generated": "2026-11-11",
    }


def update_registry(data_root: Path, manifest: dict[str, Any], status: str) -> None:
    registry_path = data_root / "registry.json"
    registry: dict[str, Any] = {"schema_version": 1, "datasets": []}
    if registry_path.exists():
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    entries = [d for d in registry.get("datasets", []) if d.get("id") != manifest["id"]]
    entries.append({
        "id": manifest["id"],
        "title": manifest["title"],
        "short_title": manifest["short_title"],
        "species": manifest["species"],
        "tissue": manifest["tissue"],
        "status": status,
        "order": 10,
        "version": manifest.get("version", "v1"),
        "updated": manifest.get("generated", ""),
    })
    entries.sort(key=lambda d: (d.get("order", 999), d.get("id", "")))
    registry["datasets"] = entries
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-xlsx", required=True, help="User workbook (Table S1, 18 numeric columns)")
    ap.add_argument("--supplementary-xlsx", required=True, help="GB 2025 Additional file 2 (Table S1/S2/S3)")
    ap.add_argument("--mapping-tsv", required=True, help="gene03g -> gene02g mapping")
    ap.add_argument("--registry-root", default="app/services/data/translatome",
                    help="Repo directory that holds registry.json + per-dataset manifests")
    ap.add_argument("--assets-root", default=os.environ.get("TRANSLATOME_DATA_DIR", ""),
                    help="Server data directory for the .tsv.gz assets (default: $TRANSLATOME_DATA_DIR)")
    ap.add_argument("--dataset-id", default=DATASET_ID)
    ap.add_argument("--status", default="prototype", choices=["draft", "prototype", "public", "retired"])
    args = ap.parse_args()

    assert args.dataset_id == DATASET_ID, (
        "This builder encodes the Chen et al. 2025 column layout; "
        "write a dataset-specific builder for other datasets."
    )
    if not args.assets_root:
        ap.error("--assets-root (or TRANSLATOME_DATA_DIR) is required: assets must not live in the repo")
    registry_root = Path(args.registry_root)
    assets_root = Path(args.assets_root)
    manifest_dir = registry_root / DATASET_ID
    asset_dir = assets_root / DATASET_ID
    manifest_dir.mkdir(parents=True, exist_ok=True)
    asset_dir.mkdir(parents=True, exist_ok=True)

    df = read_source(args.data_xlsx)
    s1, s2, s3 = read_supplementary(args.supplementary_xlsx)
    mapping = read_mapping(args.mapping_tsv)

    # Cross-check: the workbook must be the published Table S1, cell for cell.
    if list(df["Gene"]) != list(s1["Gene"]):
        raise SystemExit("ERROR: gene order/IDs differ between workbook and supplementary Table S1")
    max_diff = 0.0
    for col in RNA_COLS + RIBO_COLS + TE_COLS:
        left = df[col].map(_num)
        right = s1[col].map(_num)
        for a, b in zip(left, right):
            if (a is None) != (b is None):
                raise SystemExit(f"ERROR: NA pattern mismatch in {col}")
            if a is not None and b is not None:
                max_diff = max(max_diff, abs(a - b))
    if max_diff > 1e-9:
        raise SystemExit(f"ERROR: value mismatch vs published Table S1 (max diff {max_diff})")

    description = dict(zip(s1["Gene"], s1["Description"].fillna("").astype(str)))

    # ---- genes.tsv.gz ---------------------------------------------------
    gene_header = ["gene02g", "gene03g", "description", "chromosome", "start", "end", "is_lc"]
    gene_header += [sample["column"] for sample in SAMPLES]
    rows: list[list[str]] = []
    unmatched: list[str] = []
    collisions: dict[str, list[str]] = {}
    for _, record in df.iterrows():
        g3 = record["Gene"]
        mapped = mapping.get(g3) or {}
        g2 = mapped.get("g02", "")
        if not g2:
            unmatched.append(g3)
        else:
            collisions.setdefault(g2, []).append(g3)
        start = _fmt_int(float(mapped["start"]) * 1_000_000) if mapped.get("start") else ""
        end = _fmt_int(float(mapped["end"]) * 1_000_000) if mapped.get("end") else ""
        row = [g2, g3, description.get(g3, ""), mapped.get("chrom", ""), start, end,
               "1" if g3.endswith("LC") else "0"]
        row += [_fmt(record[_source_column(sample)]) for sample in SAMPLES]
        rows.append(row)
    write_gzip_tsv(asset_dir / "genes.tsv.gz", gene_header, rows)

    # ---- dtg.tsv.gz (Table S3) ------------------------------------------
    s3_by_gene = {r["Gene"]: r for _, r in s3.iterrows()}
    dtg_header = ["gene02g", "gene03g", "description", "cluster"] + [
        f"{name}_{kind}" for _, name in DTG_STAGES for kind in ("padj", "log2fc")
    ]
    dtg_rows: list[list[str]] = []
    for _, record in df.iterrows():
        g3 = record["Gene"]
        row = s3_by_gene.get(g3)
        if row is None:
            continue
        mapped = mapping.get(g3) or {}
        dtg_rows.append([mapped.get("g02", ""), g3, description.get(g3, ""), _fmt(row["Cluster"])] +
                        [_fmt(row[f"{stage}_{kind}"]) for stage, _ in DTG_STAGES for kind in ("Padj", "log2FC")])
    write_gzip_tsv(asset_dir / "dtg.tsv.gz", dtg_header, dtg_rows)

    # ---- deg.tsv.gz (Table S2) ------------------------------------------
    s2_by_gene = {r["Gene"]: r for _, r in s2.iterrows()}
    deg_header = ["gene02g", "gene03g", "description"] + [
        f"{comp.lower()}_{kind}" for comp in DEG_COMPS for kind in ("fold_change", "padj")
    ]
    deg_rows: list[list[str]] = []
    for _, record in df.iterrows():
        g3 = record["Gene"]
        row = s2_by_gene.get(g3)
        if row is None:
            continue
        mapped = mapping.get(g3) or {}
        deg_rows.append([mapped.get("g02", ""), g3, description.get(g3, "")] +
                        [_fmt(row[f"{comp}_{kind}"]) for comp in DEG_COMPS for kind in ("Fold_change", "Padj")])
    write_gzip_tsv(asset_dir / "deg.tsv.gz", deg_header, deg_rows)

    counts = {
        "genes": len(rows),
        "genes_with_02g": len(rows) - len(unmatched),
        "genes_without_02g": len(unmatched),
        "dtg": len(dtg_rows),
        "deg": len(deg_rows),
        "rna_libraries": 12,
        "ribo_libraries": 12,
        "samples": len(SAMPLES),
    }
    manifest = build_manifest(counts)
    (manifest_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    many = {g2: g3s for g2, g3s in collisions.items() if len(g3s) > 1}
    report = {
        "max_abs_diff_vs_published_table_s1": max_diff,
        "genes": len(rows),
        "genes_without_02g": len(unmatched),
        "unmatched_examples": unmatched[:20],
        "many_to_one_02g": {k: v for k, v in list(many.items())[:20]},
        "many_to_one_count": len(many),
        "dtg_rows": len(dtg_rows),
        "deg_rows": len(deg_rows),
        "samples": len(SAMPLES),
    }
    (manifest_dir / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    update_registry(registry_root, manifest, args.status)
    print(json.dumps({
        **report,
        "registry_dir": str(manifest_dir),
        "assets_dir": str(asset_dir),
        "status": args.status,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
