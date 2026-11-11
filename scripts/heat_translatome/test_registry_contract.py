#!/usr/bin/env python3
"""Contract test for the manifest-driven translatome service (Phase 2.5).

Proves that a new dataset needs **no code change**: this script writes a tiny
dataset folder + registry into a temporary data root, points the service at it
via ``TRANSLATOME_DATA_DIR``, and exercises the same public service functions
used by the HTTP API.  It then clears the environment and re-checks the real
dataset (60,125 genes / 11,343 DTG / 21,964 DEG) to catch regressions.

Run from the repository root:

    python3 scripts/heat_translatome/test_registry_contract.py
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import tempfile
from pathlib import Path


def write_gzip_tsv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.GzipFile(path, "wb", mtime=0) as handle:
        handle.write(("\t".join(header) + "\n").encode())
        for row in rows:
            handle.write(("\t".join(row) + "\n").encode())


def build_tiny_dataset(registry_root: Path, assets_root: Path) -> None:
    """Write registry+manifest into the repo-like root and assets into a separate root."""
    dataset_id = "test_tiny"
    manifest_dir = registry_root / dataset_id
    asset_dir = assets_root / dataset_id
    manifest_dir.mkdir(parents=True, exist_ok=True)
    asset_dir.mkdir(parents=True, exist_ok=True)

    samples = [
        {"id": "rna_2daa_ck", "label": "RNA 2 DAA CK", "role": "rna", "assay": "RNA-seq",
         "stage": "2DAA", "treatment": "CK", "column": "rna_2daa_ck", "n_reps": 1},
        {"id": "rna_2daa_hs", "label": "RNA 2 DAA HS", "role": "rna", "assay": "RNA-seq",
         "stage": "2DAA", "treatment": "HS", "column": "rna_2daa_hs", "n_reps": 1},
        {"id": "te_2daa_ck", "label": "TE 2 DAA CK", "role": "te", "assay": "TE",
         "stage": "2DAA", "treatment": "CK", "column": "te_2daa_ck"},
        {"id": "te_2daa_hs", "label": "TE 2 DAA HS", "role": "te", "assay": "TE",
         "stage": "2DAA", "treatment": "HS", "column": "te_2daa_hs"},
    ]
    manifest = {
        "schema_version": 1,
        "id": dataset_id,
        "title": "Tiny contract-test translatome",
        "short_title": "Tiny translatome",
        "description": "Synthetic dataset used to prove the manifest-driven loader.",
        "species": "Triticum aestivum",
        "tissue": "seedling",
        "stages": [{"id": "2DAA", "label": "2 DAA"}],
        "treatments": [{"id": "CK", "label": "Control"}, {"id": "HS", "label": "Heat"}],
        "assays": ["RNA-seq"],
        "roles": [
            {"id": "rna", "label": "RNA-seq FPKM", "assay": "RNA-seq", "unit": "FPKM", "metric": "fpkm"},
            {"id": "te", "label": "TE", "assay": "TE", "unit": "ratio", "metric": "te"},
        ],
        "contrasts": [{"id": "hs_vs_ck", "control": "CK", "treated": "HS", "label": "HS/CK"}],
        "samples": samples,
        "files": {"matrix": {"file": "genes.tsv.gz", "label": "Tiny matrix"}},
        "tables": [],
        "counts": {"genes": 1},
        "version": "v1",
        "generated": "2026-11-11",
    }
    (manifest_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_gzip_tsv(
        asset_dir / "genes.tsv.gz",
        ["gene02g", "gene03g", "description", "chromosome", "start", "end", "is_lc",
         "rna_2daa_ck", "rna_2daa_hs", "te_2daa_ck", "te_2daa_hs"],
        [["TraesCS1A02G000010", "TraesCS1A03G0000010", "Tiny protein", "chr1A", "1", "2", "0",
          "10", "20", "2", "3"]],
    )
    registry = {
        "schema_version": 1,
        "datasets": [{
            "id": dataset_id, "title": manifest["title"], "short_title": manifest["short_title"],
            "status": "public", "order": 1, "version": "v1", "updated": "2026-11-11",
        }],
    }
    (registry_root / "registry.json").write_text(json.dumps(registry, indent=2), encoding="utf-8")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root))
    original_registry = os.environ.get("TRANSLATOME_REGISTRY_DIR")
    original_assets = os.environ.get("TRANSLATOME_DATA_DIR")

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        registry_root = base / "registry"
        assets_root = base / "assets"
        build_tiny_dataset(registry_root, assets_root)
        os.environ["TRANSLATOME_REGISTRY_DIR"] = str(registry_root)
        os.environ["TRANSLATOME_DATA_DIR"] = str(assets_root)

        from app.services import translatome as service  # noqa: PLC0415 - after env is set
        service.clear_caches()

        datasets = service.list_datasets()
        assert [item["id"] for item in datasets] == ["test_tiny"], datasets
        assert service.default_dataset_id() == "test_tiny"

        meta = service.dataset_meta("test_tiny")
        assert meta["counts"]["genes"] == 1
        assert [stage["label"] for stage in meta["stages"]] == ["2 DAA"]
        assert [treatment["label"] for treatment in meta["treatments"]] == ["Control", "Heat"]

        # Both ID versions resolve to the same record; the payload is manifest-driven.
        record = service.resolve_gene("test_tiny", "TraesCS1A03G0000010")
        assert record is not None and record.gene02g == "TraesCS1A02G000010"
        payload = service.gene_payload("test_tiny", record)
        assert payload["gene03g"] == "TraesCS1A03G0000010"
        stage = payload["stages"][0]
        assert stage["metrics"]["rna"]["values"] == {"CK": 10.0, "HS": 20.0}, stage
        assert stage["metrics"]["rna"]["contrasts"]["hs_vs_ck"] == 0.9993, stage
        assert stage["metrics"]["te"]["values"] == {"CK": 2.0, "HS": 3.0}
        assert stage["metrics"]["te"]["contrasts"]["hs_vs_ck"] == 0.585, stage

        hits = service.search_genes("test_tiny", "TraesCS1A02G000010")
        assert hits and hits[0]["gene03g"] == "TraesCS1A03G0000010"
        assert service.table_catalog("test_tiny") == []
        path, name = service.download_file("test_tiny", "matrix")
        assert path.exists() and name.endswith(".tsv.gz")

        # A missing asset must produce a clear deployment hint (not a JSON 500).
        (assets_root / "test_tiny" / "genes.tsv.gz").unlink()
        service.clear_caches()
        try:
            service.query_genes("test_tiny", ["TraesCS1A03G0000010"])
        except service.TranslatomeDataUnavailable as exc:
            assert "TRANSLATOME_DATA_DIR" in str(exc), exc
        else:  # pragma: no cover - must not happen
            raise AssertionError("expected TranslatomeDataUnavailable for missing assets")
        build_tiny_dataset(registry_root, assets_root)  # restore for the remaining assertions
        service.clear_caches()
        print("PASS  new dataset loads/queries with zero code changes (test_tiny)")
        print("PASS  missing assets report a TRANSLATOME_DATA_DIR hint")

    # ------------------------------------------------------------------
    # Regression: the real dataset still behaves exactly as before.
    # ------------------------------------------------------------------
    os.environ["TRANSLATOME_REGISTRY_DIR"] = str(repo_root / "app" / "services" / "data" / "translatome")
    if original_assets:
        os.environ["TRANSLATOME_DATA_DIR"] = original_assets
    else:
        os.environ.pop("TRANSLATOME_DATA_DIR", None)
    from app.services import translatome as service  # noqa: PLC0415

    service.clear_caches()
    if not service.assets_ready("chen2025_cs_grain_heat"):
        print("SKIP  real-dataset regression: assets not found (set TRANSLATOME_DATA_DIR)")
        if original_registry:
            os.environ["TRANSLATOME_REGISTRY_DIR"] = original_registry
        else:
            os.environ.pop("TRANSLATOME_REGISTRY_DIR", None)
        return 0
    datasets = service.list_datasets()
    main_dataset = next(item for item in datasets if item["id"] == "chen2025_cs_grain_heat")
    assert main_dataset["counts"]["genes"] == 60125
    assert main_dataset["counts"]["dtg"] == 11343
    assert main_dataset["counts"]["deg"] == 21964

    meta = service.dataset_meta("chen2025_cs_grain_heat")
    assert [stage["id"] for stage in meta["stages"]] == ["5DAA", "10DAA", "15DAA"]
    assert [role["id"] for role in meta["roles"]] == ["rna", "ribo", "te"]

    record = service.resolve_gene("chen2025_cs_grain_heat", "TraesCS1A02G001800")
    assert record is not None and record.gene03g == "TraesCS1A03G0004000"
    payload = service.gene_payload("chen2025_cs_grain_heat", record)
    assert payload["stages"][0]["metrics"]["te"]["values"]["CK"] == 7.47096611
    assert payload["table_hits"]["dtg"]["cluster"] == "7"

    dtg = service.query_table("chen2025_cs_grain_heat", "dtg", stage="15DAA", direction="up", per_page=1)
    assert dtg["pagination"]["total"] == 3302
    deg = service.query_table("chen2025_cs_grain_heat", "deg", comparison="RNA_5", direction="down", per_page=1)
    assert deg["pagination"]["total"] == 3466

    print("PASS  real dataset regression (60,125 genes / 11,343 DTG / 21,964 DEG)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
