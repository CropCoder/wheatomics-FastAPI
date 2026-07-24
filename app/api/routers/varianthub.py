"""VariantHub — query bgzipped, tabix-indexed VCF files via bcftools.

All datasets are against the Chinese_Spring1.0 (IWGSCv1.0) reference genome.
New datasets / new reference genomes: add entries to VARIANTHUB_DATASETS (and
VARIANTHUB_REFERENCES for a new genome) — no other code changes needed.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.exceptions import ExternalToolFailure, ResourceNotFound, ValidationFailure
from app.core.response import ok
from app.core.security import GENE_ID_PATTERN, ensure_allowed_table, ensure_interval_like
from app.services.command_runner import run_command

router = APIRouter(tags=["VariantHub"])

# Reference genome machine name -> display name
VARIANTHUB_REFERENCES: dict[str, str] = {
    "Chinese_Spring1.0": "Chinese Spring (IWGSCv1.0)",
    "Chinese_Spring2.1": "Chinese Spring (IWGSCv2.1)",
}

# Dataset key -> {label, filename, source, reference}
VARIANTHUB_DATASETS: dict[str, dict[str, str]] = {
    "WEC_filtered_SNPs": {
        "label": "WEC_filtered_SNPs",
        "filename": "WEC_SNP_IWGSCv1.0.eff.vcf.gz",
        "source": "WEC SNP (PMID 25886949)",
        "reference": "Chinese_Spring1.0",
    },
    "WEC_filtered_INDELs": {
        "label": "WEC_filtered_INDELs",
        "filename": "WEC_INDEL_IWGSCv1.0.eff.vcf.gz",
        "source": "WEC InDel",
        "reference": "Chinese_Spring1.0",
    },
    "whealbi_minocc10": {
        "label": "whealbi.minocc10",
        "filename": "whealbi.minocc10.imputed.vcf.gz",
        "source": "Whealbi 群体（已插补）",
        "reference": "Chinese_Spring1.0",
    },
    "Aus_UG_eff": {
        "label": "Aus.UG.eff",
        "filename": "Aus.UG.dedup.whole.eff.vcf.gz",
        "source": "六倍体面包小麦泛基因组 (PMID 28231383)",
        "reference": "Chinese_Spring1.0",
    },
    "Exon_dedup_HCandUG": {
        "label": "Exon.dedup.HCandUG",
        "filename": "Exom.dedup.HCandUG.eff.vcf.gz",
        "source": "外显子组 HC+UG 去重",
        "reference": "Chinese_Spring1.0",
    },
    "PRJNA381058_exome": {
        "label": "PRJNA381058_exome",
        "filename": "PRJNA381058_exome_whole_eff.vcf.gz",
        "source": "外显子组（重组率研究）",
        "reference": "Chinese_Spring1.0",
    },
    "Exome_PRJEB30905": {
        "label": "Exome_PRJEB30905",
        "filename": "Exome_PRJEB30905_whole_eff.vcf.gz",
        "source": "VRN1 等发育响应 (PRJEB30905)",
        "reference": "Chinese_Spring1.0",
    },
    "1000_wheat_exomes": {
        "label": "1000 wheat exomes",
        "filename": "1kEC_genotype_eff.vcf.gz",
        "source": "1kEC（KSU wheatgenomics）",
        "reference": "Chinese_Spring1.0",
    },
    "Canadian_wheat_lines": {
        "label": "Canadian wheat lines",
        "filename": "161010_Chinese_Spring_v1.novoalign.raw.whole.eff.vcf.gz",
        "source": "加拿大小麦种质 novoalign 原始变异",
        "reference": "Chinese_Spring1.0",
    },
    "1000_wheat_exomes_imputed": {
        "label": "1000 wheat exomes after imputation and filtering",
        "filename": "all.GP08_mm75_het3_publication01142019_eff.vcf.gz",
        "source": "1kEC 插补过滤版",
        "reference": "Chinese_Spring1.0",
    },
    "NewExomeCapute": {
        "label": "NewExomeCapute",
        "filename": "NewExomeCapute.whole.eff.vcf.gz",
        "source": "新版外显子捕获（GigaScience 2019）",
        "reference": "Chinese_Spring1.0",
    },
    "90_mini_core_rna_seq_HC": {
        "label": "90_mini_core_rna_seq_HC",
        "filename": "90_mini_core_rna_seq_whole.eff.vcf.gz",
        "source": "90 份 mini-core RNA-seq (PMC5619896)",
        "reference": "Chinese_Spring1.0",
    },
    "355_common_wheat_WGS": {
        "label": "355 common wheat WGS",
        "filename": "all355.maf01.mis25.het03.eff.vcf.gz",
        "source": "355 份普通小麦 WGS 整合（Plant Cell 2023）",
        "reference": "Chinese_Spring1.0",
    },
    "Vmap_1.0": {
        "label": "Vmap 1.0",
        "filename": "414WGS.vcf.eff.vcf.gz",
        "source": "VMap 1.0 群体（414 份 WGS, Nat Genet 2020）",
        "reference": "Chinese_Spring1.0",
    },
    "35_grain_rna_seq_HC": {
        "label": "35_grain_rna_seq_HC",
        "filename": "35_grain_rna_seq_whole.eff.vcf.gz",
        "source": "35 份籽粒 RNA-seq (PMC5637334)",
        "reference": "Chinese_Spring1.0",
    },
    "GBS_filtered_SNPs": {
        "label": "GBS_filtered_SNPs",
        "filename": "GBS_filtered_SNPs_IWGSCv1.0.eff.vcf.gz",
        "source": "GBS SNP 过滤",
        "reference": "Chinese_Spring1.0",
    },
    "GBS_filtered_Indels": {
        "label": "GBS_filtered_Indels",
        "filename": "GBS_filtered_Indels_IWGSCv1.0.eff.vcf.gz",
        "source": "GBS InDel 过滤",
        "reference": "Chinese_Spring1.0",
    },
    "GBS_NG_GWAS": {
        "label": "GBS_NG_GWAS",
        "filename": "GBS_NG_GWAS_eff1.vcf.gz",
        "source": "GBS NG GWAS 面板 (Nat Genet 2019)",
        "reference": "Chinese_Spring1.0",
    },
    "commonwheat63WGS": {
        "label": "commonwheat63WGS",
        "filename": "commonwheat63WGS.eff.sort.filter.vcf.gz",
        "source": "普通小麦 63 份 WGS（PMID 30081829）",
        "reference": "Chinese_Spring1.0",
    },
    "WildEmmer20WGS_SNP": {
        "label": "WildEmmer20WGS_SNP",
        "filename": "WildEmmer20WGS_SNP_eff.vcf.gz",
        "source": "野生二粒麦 20× WGS SNP",
        "reference": "Chinese_Spring1.0",
    },
    "WildEmmer10WGS_INDEL": {
        "label": "WildEmmer10WGS_INDEL",
        "filename": "WildEmmer10WGS_INDEL_eff.vcf.gz",
        "source": "野生二粒麦 10× WGS InDel",
        "reference": "Chinese_Spring1.0",
    },
    "SHW_GBS_SNP": {
        "label": "SHW_GBS_SNP",
        "filename": "SHW_GBS_SNP_eff.vcf.gz",
        "source": "合成六倍体小麦 SHW GBS SNP",
        "reference": "Chinese_Spring1.0",
    },
    "Cheng_2024": {
        "label": "Cheng, S. et al. 2024",
        "filename": "merge.SNP.Missing-unphasing.ID.ann.finalSID.allele2_retain.hard_retain.InbreedingCoeff_retain.clean.anno.vcf.gz",
        "source": "Cheng 等 2024 整合 SNP（Nature 2024）",
        "reference": "Chinese_Spring1.0",
    },
    "287exome_CS2.1": {
        "label": "287exome_raw (CS2.1)",
        "filename": "287exome.SnpSiftfilter.edit.eff.vcf.gz",
        "source": "Mol Plant 2022 (10.1016/j.molp.2022.01.004)",
        "reference": "Chinese_Spring2.1",
    },
    "wheat660k_2191_CS2.1": {
        "label": "wgs2191 (CS2.1)",
        "filename": "wgs.1618.wheat660k.623.merge.maf0.01.2191.ann.vcf.gz",
        "source": "Nat Genet 2025 (10.1038/s41588-025-02259-2)",
        "reference": "Chinese_Spring2.1",
    },
    "all491_cnv_snp_indel": {
        "label": "Triticum_aestivum.AABBDD.491.WGS",
        "filename": "all491.cnv.snp.indel.missingrate0.25.maf0.01.abd.vcf.gz",
        "source": "491 份材料 CNV/SNP/InDel 整合（missing rate<0.25, MAF>0.01, A/B/D 亚基因组）",
        "reference": "Chinese_Spring1.0",
    },
}

_MAX_REGION_BP = 5_000_000


def _bcftools_path() -> str:
    """Locate bcftools binary. Prefer settings.BCFTOOLS_BIN, fall back to
    common system paths. Mirrors _blastdbcmd_path in sequence.py.
    """
    candidates = [
        settings.BCFTOOLS_BIN,
        Path("/usr/bin/bcftools"),
        Path("/usr/local/bin/bcftools"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    # Return default; run_command will surface a clear error if missing
    return str(settings.BCFTOOLS_BIN)


def _vcf_path(dataset: str) -> Path:
    """Validate dataset key and return the on-disk VCF path (must have .tbi)."""
    ensure_allowed_table(dataset, VARIANTHUB_DATASETS.keys(), "dataset")
    path = settings.VARIANTHUB_VCF_DIR / VARIANTHUB_DATASETS[dataset]["filename"]
    if not path.exists():
        raise ResourceNotFound(f"VCF file not found on server: {path.name}")
    if not Path(str(path) + ".tbi").exists():
        raise ResourceNotFound(f"Tabix index missing: {path.name}.tbi")
    return path


_SAMPLE_META_DIR = Path(__file__).resolve().parents[2] / "services" / "data" / "sample_meta"
# dataset -> (mtime_seconds, payload); None payload = known-missing file
_sample_meta_cache: dict[str, tuple[float, dict | None]] = {}


def _sample_meta(dataset: str) -> dict | None:
    """Load sample metadata for a dataset, or None if it has none.

    Cached with an mtime check so a newly added JSON file is picked up
    without restarting uvicorn.
    """
    path = _SAMPLE_META_DIR / f"{dataset}.json"
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        _sample_meta_cache[dataset] = (0.0, None)
        return None
    cached = _sample_meta_cache.get(dataset)
    if cached and cached[0] == mtime:
        return cached[1]
    payload = json.loads(path.read_text(encoding="utf-8"))
    _sample_meta_cache[dataset] = (mtime, payload)
    return payload


# Aliases from query-parameter names to sample_meta field keys. These match
# the snake_cased headers produced by scripts/xlsx_to_sample_meta.py.
_META_FILTER_PARAMS: dict[str, str] = {
    "country": "country",
    "continent": "continent",
    "status": "status",
    "growth_habit": "growth_habit",
    "population": "major_population",
}


def _filter_samples_by_meta(
    dataset: str, filters: dict[str, str]
) -> tuple[dict, list[str]]:
    """Resolve meta filters to a list of VCF sample names.

    Raises ResourceNotFound if the dataset has no metadata, ValidationFailure
    for unknown filter fields or zero matches.
    """
    meta = _sample_meta(dataset)
    if meta is None:
        raise ResourceNotFound(f"No sample metadata for dataset: {dataset}")

    field_keys = {f["key"] for f in meta["fields"]}
    resolved: dict[str, str] = {}
    for param, value in filters.items():
        field = _META_FILTER_PARAMS.get(param, param)
        if field not in field_keys:
            raise ValidationFailure(
                f"Unknown metadata filter '{param}' for dataset {dataset}. "
                f"Available fields: {sorted(field_keys)}"
            )
        resolved[field] = value

    matched = [
        name
        for name, entry in meta["samples"].items()
        if all(entry.get(field, "").lower() == value.lower() for field, value in resolved.items())
    ]
    if not matched:
        raise ValidationFailure(
            f"No samples match the metadata filter(s): "
            + ", ".join(f"{k}={v}" for k, v in filters.items())
        )
    return meta, matched


def _parse_region(region: str) -> list[str]:
    """Validate a region string and return candidate `chr:start-end` strings.

    Chromosome names differ in case between datasets (chr1A vs Chr1A), so
    when the name starts with chr/Chr we return both casings — the caller
    tries the first, then falls back to the second on error or empty result.
    """
    ensure_interval_like(region)
    chrom = region.split(":")[0]
    interval = region.split(":")[1].replace("..", "-")
    start_text, end_text = interval.split("-")
    start, end = int(start_text), int(end_text)
    if end <= start or end - start > _MAX_REGION_BP:
        raise ValidationFailure(f"Region length must be > 0 and <= {_MAX_REGION_BP} bp")

    candidates = [f"{chrom}:{start}-{end}"]
    if chrom.startswith("Chr"):
        candidates.append(f"chr{chrom[3:]}:{start}-{end}")
    elif chrom.startswith("chr") and len(chrom) > 3:
        candidates.append(f"Chr{chrom[3:]}:{start}-{end}")
    return candidates


def _parse_vcf_header(header_text: str) -> tuple[list[str], list[str]]:
    """Split a VCF header into (## meta lines, sample names from #CHROM)."""
    meta_lines: list[str] = []
    samples: list[str] = []
    for line in header_text.splitlines():
        if line.startswith("##"):
            meta_lines.append(line)
        elif line.startswith("#CHROM"):
            fields = line.split("\t")
            samples = fields[9:] if len(fields) > 9 else []
    return meta_lines, samples


def _vcf_header(vcf: Path) -> tuple[list[str], list[str]]:
    """Read the VCF header directly from the (bg)gzipped file.

    Reading with gzip avoids bcftools' strict header validation — some files
    (e.g. 287exome) have duplicated sample names that make `bcftools view`
    abort with "could not parse header".
    """
    header_lines: list[str] = []
    with gzip.open(vcf, "rt") as fh:
        for line in fh:
            if not line.startswith("#"):
                break
            header_lines.append(line.rstrip("\n"))
    return _parse_vcf_header("\n".join(header_lines))


def _dedupe_samples(samples: list[str]) -> list[str]:
    """Make sample names unique by appending _2, _3, ... to repeats.

    bcftools refuses duplicated sample names; renaming lets queries proceed.
    """
    seen: dict[str, int] = {}
    result: list[str] = []
    for name in samples:
        seen[name] = seen.get(name, 0) + 1
        result.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    return result


def _tabix_records(vcf: Path, region: str) -> str:
    """Fetch raw VCF lines for a region via tabix (tolerant, uses the .tbi index)."""
    result = run_command([_tabix_path(), str(vcf), region])
    return result.stdout


def _zcat_records(vcf: Path) -> str:
    """Dump the full VCF via gzip -dc (tolerant fallback for full-file ID scans)."""
    result = run_command(["gzip", "-dc", str(vcf)])
    return result.stdout


def _tabix_path() -> str:
    """Locate tabix binary (used only for files whose headers bcftools rejects)."""
    candidates = [
        settings.BCFTOOLS_BIN.parent / "tabix",
        Path("/usr/bin/tabix"),
        Path("/usr/local/bin/tabix"),
        Path("/home/fei/data/tiantian_data/soft/htslib-1.6/bin/tabix"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return str(candidates[0])


def _parse_info(info_raw: str) -> dict[str, object]:
    """Parse a VCF INFO column into a dict. Flag keys (no '=') map to True."""
    info: dict[str, object] = {}
    for item in info_raw.split(";"):
        if not item:
            continue
        if "=" in item:
            key, value = item.split("=", 1)
            info[key] = value
        else:
            info[item] = True
    return info


def _parse_vcf_records(text: str, samples: list[str] | None = None) -> tuple[list[str], list[dict]]:
    """Parse VCF text into (samples, records).

    Samples come from the #CHROM line unless `samples` is passed explicitly
    (used by the tabix fallback, which outputs no header). Each record
    carries raw genotype strings in the same order as the returned samples.
    """
    if samples is None:
        samples = []
        for line in text.splitlines():
            if line.startswith("#CHROM"):
                fields = line.split("\t")
                samples = fields[9:] if len(fields) > 9 else []
                break
    records: list[dict] = []
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) < 8:
            continue
        record = {
            "chrom": fields[0],
            "pos": int(fields[1]),
            "id": fields[2],
            "ref": fields[3],
            "alt": fields[4],
            "qual": fields[5],
            "filter": fields[6],
            "info": _parse_info(fields[7]),
            "info_raw": fields[7],
        }
        if len(fields) > 8:
            record["format"] = fields[8]
            record["genotypes"] = fields[9:]
        records.append(record)
    return samples, records


@router.get("/VariantHub/datasets")
def varianthub_datasets() -> dict:
    """List all VCF datasets, grouped by reference genome."""
    references: dict[str, list[dict]] = {}
    for key, meta in VARIANTHUB_DATASETS.items():
        references.setdefault(meta["reference"], []).append(
            {
                "key": key,
                "label": meta["label"],
                "source": meta["source"],
                "has_sample_meta": _sample_meta(key) is not None,
            }
        )
    return ok({
        "references": [
            {
                "name": name,
                "display": VARIANTHUB_REFERENCES.get(name, name),
                "datasets": datasets,
            }
            for name, datasets in references.items()
        ]
    })


@router.get("/VariantHub/dataset_info")
def varianthub_dataset_info(
    dataset: str = Query(..., description="Dataset key from /api/VariantHub/datasets"),
) -> dict:
    """Return a dataset's VCF header: ## meta lines and sample IDs."""
    vcf = _vcf_path(dataset)
    meta_lines, raw_samples = _vcf_header(vcf)
    duplicated = len(set(raw_samples)) != len(raw_samples)
    # Expose the deduplicated names — these are what /query accepts in its
    # `samples` parameter and what result columns are labelled with.
    samples = _dedupe_samples(raw_samples) if duplicated else raw_samples
    sample_meta = _sample_meta(dataset)
    meta = VARIANTHUB_DATASETS[dataset]
    return ok({
        "dataset": dataset,
        "label": meta["label"],
        "source": meta["source"],
        "reference": meta["reference"],
        "reference_display": VARIANTHUB_REFERENCES.get(meta["reference"], meta["reference"]),
        "meta_lines": meta_lines,
        "samples": samples,
        "duplicated_samples": duplicated,
        "has_sample_meta": sample_meta is not None,
        "sample_meta_fields": sample_meta["fields"] if sample_meta else [],
        "n_samples": len(samples),
    })


@router.get("/VariantHub/samples")
def varianthub_samples(
    dataset: str = Query(..., description="Dataset key from /api/VariantHub/datasets"),
    country: str | None = Query(None),
    continent: str | None = Query(None),
    status: str | None = Query(None),
    growth_habit: str | None = Query(None),
    population: str | None = Query(None, description="Maps to the major_population field"),
) -> dict:
    """List sample metadata for a dataset, optionally filtered.

    Filters are exact matches (case-insensitive) on the corresponding
    metadata fields, e.g. &country=Turkey&status=Landrace.
    """
    filters = {
        k: v
        for k, v in {
            "country": country,
            "continent": continent,
            "status": status,
            "growth_habit": growth_habit,
            "population": population,
        }.items()
        if v is not None
    }
    ensure_allowed_table(dataset, VARIANTHUB_DATASETS.keys(), "dataset")
    if filters:
        meta, matched = _filter_samples_by_meta(dataset, filters)
    else:
        meta = _sample_meta(dataset)
        if meta is None:
            raise ResourceNotFound(f"No sample metadata for dataset: {dataset}")
        matched = list(meta["samples"])

    return ok({
        "dataset": dataset,
        "fields": meta["fields"],
        "total": len(matched),
        "samples": [{"sample": name, **meta["samples"][name]} for name in matched],
    })


@router.get("/VariantHub/query")
def varianthub_query(
    dataset: str = Query(..., description="Dataset key from /api/VariantHub/datasets"),
    region: str | None = Query(None, description="Genomic interval, e.g. chr1A:1000-50000"),
    variant_id: str | None = Query(None, description="Variant ID (exact match on the ID column)"),
    samples: str | None = Query(None, description="Comma-separated sample IDs; omit for all samples"),
    country: str | None = Query(None, description="Sample metadata filter (exact, case-insensitive)"),
    continent: str | None = Query(None, description="Sample metadata filter"),
    status: str | None = Query(None, description="Sample metadata filter, e.g. Landrace"),
    growth_habit: str | None = Query(None, description="Sample metadata filter, e.g. Winter"),
    population: str | None = Query(None, description="Sample metadata filter (major_population)"),
    limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0),
) -> dict:
    """Query variants by genomic region or by variant ID.

    Exactly one of `region` / `variant_id` is required. Region queries use the
    tabix index (`bcftools view -r`); ID queries filter on the ID column
    (`bcftools view -i 'ID="..."'`, a full-file scan that can be slow on the
    large population VCFs).

    Samples default to all; narrow them either explicitly with `samples` or
    via sample-metadata filters (country/continent/status/growth_habit/
    population) — the two are mutually exclusive.
    """
    if (region is None) == (variant_id is None):
        raise ValidationFailure("Provide exactly one of 'region' or 'variant_id'")

    meta_filters = {
        k: v
        for k, v in {
            "country": country,
            "continent": continent,
            "status": status,
            "growth_habit": growth_habit,
            "population": population,
        }.items()
        if v is not None
    }
    if meta_filters and samples:
        raise ValidationFailure(
            "'samples' and metadata filters (country/status/...) are mutually exclusive"
        )

    vcf = _vcf_path(dataset)
    _, available_samples = _vcf_header(vcf)
    has_duplicates = len(set(available_samples)) != len(available_samples)

    requested: list[str] | None = None
    if samples:
        requested = [s.strip() for s in samples.split(",") if s.strip()]
        if not requested:
            raise ValidationFailure("Empty samples list")
        # For duplicated-sample files the addressable names are the
        # deduplicated ones (CS_A, CS_B, CS_A_2, ...).
        valid_names = _dedupe_samples(available_samples) if has_duplicates else available_samples
        unknown = [s for s in requested if s not in valid_names]
        if unknown:
            raise ValidationFailure(
                f"Unknown sample(s) for dataset {dataset}: {', '.join(unknown)}. "
                "See /api/VariantHub/dataset_info for the full sample list."
            )
    elif meta_filters:
        _, matched = _filter_samples_by_meta(dataset, meta_filters)
        available_set = set(available_samples)
        requested = [s for s in matched if s in available_set]
        if not requested:
            raise ValidationFailure(
                "Metadata filters matched samples, but none are present in this VCF"
            )

    if has_duplicates:
        # bcftools aborts on duplicated sample names. Fall back to tolerant
        # tools: tabix for region slices, zcat for full-file ID scans, and
        # column-based sample selection. Sample names in the response are
        # deduplicated (Wumangchunmai, Wumangchunmai_2, ...).
        all_samples = _dedupe_samples(available_samples)
        if region is not None:
            text = ""
            for candidate in _parse_region(region):
                try:
                    text = _tabix_records(vcf, candidate)
                except ExternalToolFailure:
                    continue
                if text.strip():
                    break
        else:
            assert variant_id is not None
            if not GENE_ID_PATTERN.match(variant_id):
                raise ValidationFailure(f"Invalid variant_id: {variant_id!r}")
            text = _zcat_records(vcf)
        _, records = _parse_vcf_records(text, all_samples)
        if variant_id is not None:
            records = [r for r in records if r["id"] == variant_id]
        if requested is not None:
            keep = [all_samples.index(s) for s in requested]
            all_samples = requested
            for record in records:
                genotypes = record.get("genotypes")
                if genotypes is not None:
                    record["genotypes"] = [genotypes[i] for i in keep]
    else:
        cmd = [_bcftools_path(), "view", str(vcf)]
        if requested is not None:
            cmd += ["-s", ",".join(requested)]

        if region is not None:
            # Try the chromosome name as given, then the chr/Chr casing
            # variant if the tool errors or the slice comes back empty.
            result = None
            records = []
            candidates = _parse_region(region)
            for i, candidate in enumerate(candidates):
                last = i == len(candidates) - 1
                try:
                    result = run_command(cmd + ["-r", candidate])
                except ExternalToolFailure:
                    if last:
                        raise
                    continue
                all_samples, records = _parse_vcf_records(result.stdout)
                if records or last:
                    break
        else:
            assert variant_id is not None
            if not GENE_ID_PATTERN.match(variant_id):
                raise ValidationFailure(f"Invalid variant_id: {variant_id!r}")
            result = run_command(cmd + ["-i", f'ID="{variant_id}"'])
            all_samples, records = _parse_vcf_records(result.stdout)

    page = records[offset:offset + limit]
    meta = VARIANTHUB_DATASETS[dataset]
    return ok({
        "dataset": dataset,
        "reference": meta["reference"],
        "region": region,
        "variant_id": variant_id,
        "samples": all_samples,
        "n_samples": len(all_samples),
        "meta_filters": meta_filters or None,
        "total": len(records),
        "limit": limit,
        "offset": offset,
        "total_shown": len(page),
        "has_more": offset + limit < len(records),
        "records": page,
    })
