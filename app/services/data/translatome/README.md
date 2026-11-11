# Translatome registry & manifests (assets live outside the repo)

Runtime loader: `app/services/translatome.py`.

**Split layout (since 2026-11-11):**

- **In this repo** (versioned with the code): `registry.json`, every dataset's
  `manifest.json`, `build_report.json`, and the scripts under
  `scripts/heat_translatome/`.
- **Outside the repo** (server data directory, pointed to by the
  `TRANSLATOME_DATA_DIR` env var / `app/core/config.py`): the gzipped matrices
  `genes.tsv.gz`, `dtg.tsv.gz`, `deg.tsv.gz`, one folder per dataset:
  `<TRANSLATOME_DATA_DIR>/<dataset_id>/`.

```
app/services/data/translatome/            # repo (this folder)
  registry.json
  chen2025_cs_grain_heat/
    manifest.json
    build_report.json

$TRANSLATOME_DATA_DIR/                     # server (not committed)
  chen2025_cs_grain_heat/
    genes.tsv.gz  dtg.tsv.gz  deg.tsv.gz
```

Adding a dataset never needs code changes: put its `manifest.json` here, put its
assets under `$TRANSLATOME_DATA_DIR/<dataset_id>/`, add one entry to
`registry.json`; the API (`/api/translatome/*`) and `/translatome/` page pick it
up automatically. `/api/translatome/datasets` reports `assets_ready` so a
missing upload is visible before queries fail.

## Asset checksums (chen2025_cs_grain_heat)

| file (under `$TRANSLATOME_DATA_DIR`) | size | sha256 |
|---|---|---|
| `chen2025_cs_grain_heat/deg.tsv.gz` | 1,002,485 B | `02fa07d408093c840c32d049f918ffce7e8080b3bd98931cbecedda3b231744f` |
| `chen2025_cs_grain_heat/dtg.tsv.gz` | 390,326 B | `837c3ee47c00bbbce5e9b606788dffe7512518c5c1f5682e601628092fbe7ce2` |
| `chen2025_cs_grain_heat/genes.tsv.gz` | 6,441,521 B | `764a47e105a567db5db18c5b39a7b5fb95d5b64a9e838d8dc54c845a7171f0da` |

## Server placement (2026-11-11)

The `chen2025_cs_grain_heat` assets are already uploaded to the web node at
`/var/www/data/translatome/chen2025_cs_grain_heat/` (the `app/core/config.py`
default for `TRANSLATOME_DATA_DIR`), verified with `gzip -t` and line counts
(60,125 genes / 11,343 DTG / 21,964 DEG). No `.env` change is required for the
default path; future datasets can be synced with
`scripts/heat_translatome/sync_assets.sh`.

## Local development

```bash
export TRANSLATOME_DATA_DIR=/path/to/translatome_data
uvicorn main:app --port 8000        # or: pkill -f dev_app; see scripts/heat_translatome/README.md
```

## Production deployment

1. Build or copy the assets into `<TRANSLATOME_DATA_DIR>/<dataset_id>/` on the
   web node (e.g. `/var/www/data/translatome/`). `bash
   scripts/heat_translatome/sync_assets.sh <ssh-target>` does this with rsync.
2. Set `TRANSLATOME_DATA_DIR=/var/www/data/translatome` in the server `.env`.
3. `sudo systemctl restart wheatomics-api`.
4. `curl -s https://wheatomics.sdau.edu.cn/api/translatome/datasets` →
   `"assets_ready": true`.

## Provenance (chen2025_cs_grain_heat)

- Numeric matrix (18 columns) is identical (max abs diff 0.0, NA pattern identical)
  to Supplementary Table S1 of **Chen et al. 2025, Genome Biology 26(1):382**
  (`10.1186/s13059-025-03848-4`, CC BY-NC-ND 4.0). Control RNA-seq/Ribo-seq
  libraries come from **Guo et al. 2023, Plant Cell 35(6):1848-1867**
  (`10.1093/plcell/koad075`, © ASPB), BioProject PRJNA871371; heat-stress libraries
  are PRJNA1135409.
- Transformations: add the platform 02G gene ID via the GeneHub annotation table;
  rename columns/add description+chromosome; split Supplementary Table S2/S3 into
  DTG/DEG tables; keep TE missing values empty (never 0).
- TE definition: mean Ribo-seq FPKM / mean RNA-seq FPKM; undefined (empty) when
  RNA-seq FPKM < 0.2. Data are condition means (RNA n=3, Ribo n=2; no SD).
