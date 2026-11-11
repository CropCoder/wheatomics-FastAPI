# Heat-stress grain translatome: build & test scripts

The translatome runtime is **manifest-driven**
(`app/services/translatome.py`): it needs a `registry.json` plus per-dataset
folders (`manifest.json` + gzipped TSVs) under
`app/services/data/translatome/`, and never hard-codes stages/treatments/tables.
These scripts generate that data for the Chen et al. 2025 dataset and validate
the contract.

Both scripts are read-only with respect to the platform: `fetch_id_map.py` only
issues GET requests to the public GeneHub API; `build_data.py` reads local
workbooks and writes the data root; the contract test writes only a temporary
directory (and, in its second phase, reads the real dataset).

## 1. `fetch_id_map.py` — full 03G → 02G cross-reference

The source publication uses IWGSC RefSeq v2.1 (`03G`) gene IDs, while WheatOmics
is keyed by `02G`. GeneHub's interval annotation table
`Genefunc_CS_IWGSC03G_table` exposes both (`gene_primary` / `gene_secondary`);
the API caps one interval at 30 Mb, so the script walks the 21 chromosomes and
`chrUn` in 30 Mb chunks (4 workers, retries). It can optionally retry genes
missing from the interval table through `GET /api/genes/detail/{id}`.

Latest full run (2026-11-11): **266,760 genes** returned; for the 60,125 genes
used by this dataset the mapping is **100% complete with no many-to-one
collisions**.

```bash
python3 scripts/heat_translatome/fetch_id_map.py \
  --out /tmp/gene_map_03g_02g.tsv \
  --genes /tmp/genes_03g.txt      # optional: one 03G ID per line
```

## 2. `build_data.py` — build one dataset folder + registry entry

Output layout (repo vs server data directory split):

```
app/services/data/translatome/            # repo (committed)
  registry.json
  chen2025_cs_grain_heat/
    manifest.json
    build_report.json

<TRANSLATOME_DATA_DIR>/                    # outside the repo (not committed)
  chen2025_cs_grain_heat/
    genes.tsv.gz
    dtg.tsv.gz
    deg.tsv.gz
```

Inputs: `--data-xlsx` (user workbook), `--supplementary-xlsx` (Genome Biology
2025 Additional file 2: Table S1 with descriptions + S2/S3), `--mapping-tsv`
(output of step 1). The script refuses to build unless the workbook matches the
published Table S1 cell-for-cell (gene order, NA pattern, max abs difference 0).

```bash
python3 scripts/heat_translatome/build_data.py \
  --data-xlsx "/path/to/5_10_15DAA...TE.xlsx" \
  --supplementary-xlsx "/path/to/13059_2025_3848_MOESM2_ESM.xlsx" \
  --mapping-tsv /tmp/gene_map_03g_02g.tsv \
  --registry-root app/services/data/translatome \
  --assets-root /path/to/translatome_data \
  --dataset-id chen2025_cs_grain_heat \
  --status prototype
```

`--assets-root` (or `TRANSLATOME_DATA_DIR`) is required: the gzipped matrices
must not live in the repo.

Build-time dependencies: pandas + openpyxl. The runtime loader only uses the
standard library (`gzip`, `csv`, `json`).

> This builder encodes the Chen et al. 2025 column layout (one-off conversion).
> A future dataset with a different workbook layout gets its own small builder
> or a manual conversion; the **runtime needs no change**.

## 3. `test_registry_contract.py` — prove new data needs no code changes

Creates a tiny synthetic dataset + registry in a temporary directory, points the
service at it with `TRANSLATOME_DATA_DIR`, asserts that it is listed, resolvable,
queryable and downloadable, then clears the environment and re-checks the real
dataset (60,125 genes / 11,343 DTG / 21,964 DEG).

```bash
TRANSLATOME_DATA_DIR=/path/to/translatome_data \
  python3 scripts/heat_translatome/test_registry_contract.py
# PASS  new dataset loads/queries with zero code changes (test_tiny)
# PASS  missing assets report a TRANSLATOME_DATA_DIR hint
# PASS  real dataset regression (60,125 genes / 11,343 DTG / 21,964 DEG)
```

Without `TRANSLATOME_DATA_DIR` the real-dataset phase is skipped
(`SKIP  real-dataset regression: assets not found`); the synthetic dataset phase
always runs because it creates both a temporary registry root and asset root.

## 4. `sync_assets.sh` — upload assets to the server

```bash
TRANSLATOME_DATA_DIR=~/wheatomics/translatome_data \
  bash scripts/heat_translatome/sync_assets.sh <ssh-target> /var/www/data/translatome
# add --dry-run to preview, --delete to remove remote files not present locally
```

After syncing, set `TRANSLATOME_DATA_DIR=/var/www/data/translatome` in the
server `.env`, restart `wheatomics-api`, and check
`/api/translatome/datasets` → `"assets_ready": true`.

## Notes

* **DEG column semantics**: Table S2's `Fold_change` column is a signed
  **log2 fold change** (HS vs CK), not a ratio; negative = lower after heat
  stress. The API exposes it as `log2fc` (declared in the manifest).
* **TE missing**: the workbook uses the literal `NA` when RNA-seq FPKM < 0.2;
  the build converts it to an empty field and the API returns `null`.
* **License**: heat-stress data are CC BY-NC-ND 4.0 (Genome Biology 2025);
  control libraries are © ASPB (Plant Cell 2023). Academic display with
  attribution; obtain author permission before redistribution/derivatives
  (see `docs/plans/heat_translatome_2026-11/PLAN.md` Appendix B).
