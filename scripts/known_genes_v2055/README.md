# KnownGene v2056 data pipeline

把 v2056 已整理清单（1420 行 × 17 列）替换进生产 `cloned_gene_db.cloned_gene_tbl` 的脚本与产物。
设计与验收标准见仓库根目录 `KnownGenes_v2055_update_plan.md`、`docs/known_genes/backend_investigation.md`、
`docs/known_genes/FREEZE_v2055.md`。

## 目录

```
scripts/known_genes_v2055/
├── extract.py                      # xlsx -> JSONL + 校验报告 + 前端 fixtures
├── migrate_known_genes_v2055.py    # clone_id 映射 / staging 导入 / 替换 / 校验 / 回滚
├── README.md                       # 本文件
└── out/                            # 生成产物（gitignore；含 JSONL 8MB 与 fixtures）
    ├── known_genes_v2056.jsonl
    ├── validation_report.md/json
    ├── api_fixtures/               # 前端 mock：/all、/stats、6 个详情
    └── migration/                  # clone_id_mapping.csv / unmatched_*.csv / summary
scripts/sql/known_genes_v2055_ddl.sql   # root 执行：ALTER + backup/staging 表
```

## 标准流程

```bash
# 1) 提取 + 校验（本地，pandas/openpyxl）
python3 scripts/known_genes_v2055/extract.py \
  --xlsx "/Users/mashengwei/Desktop/markdown/陈甜甜/known-gene-paper-20260916/已知基因逐条提取清单_20261019-合集_修正版v2056_20261028.xlsx"
# 期望：fatals=0, multi_value_anomalies=0, 1420 rows, 23 species, 38 chromosomes, 1570 refs/883 DOIs

# 2) 只读映射预演（生产节点，应用账号）
python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py --phase prepare \
  --jsonl /tmp/known_genes_v2056.jsonl --report-dir /tmp/kg_migration
# 2026-10-28 实测：mapped 321/520 (61.73%), 199 unmatched old, 1099 new ids 527..1625

# 3) root 执行 DDL（备份表 + staging 表 + 追加列）
sudo mysql < scripts/sql/known_genes_v2055_ddl.sql

# 4) 数据替换（应用账号，单事务）
python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py --phase data --dry-run   # 先看计划
python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py --phase data --commit

# 5) 校验
python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py --phase verify

# 6) 回滚（仅在需要时；恢复旧 520 行的 16 个旧列）
python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py --phase rollback --commit
```

## 说明

- **clone_id 映射（用户决策 Q3）**：只保留映射成功的旧 clone_id（321/520）；199 个未映射旧 ID 不复用；
  不建 legacy 回退表；旧详情 URL（`/genes/detail.html?id=<clone_id>`）对未映射行 404。
  - 映射层级：`T2_v3`（gene_id v1/v2→v3 via `Genehub_DB.GenePageIWGSCv1_table`）、`T1_id`/`T1_id_token`、
    `T3_name_chrom`（同名同染色体）、`T3_name`（同名且旧行无染色体）。
  - 旧库 `clone_id 28/29` 的 gene_id/gene_name 列错位在映射时自动交换修正。
- **禁止 TRUNCATE**：应用账号无 DDL 权限且 TRUNCATE 隐式提交；data 阶段用单事务 DELETE + INSERT...SELECT。
- **中间格式 JSONL**：历史 `cloned_gene_bad_import_backup`（1636 行）是 TSV/引号错位事故，禁止再走 TSV。
- `out/` 与 JSONL 不入库（`.gitignore`）；生产端临时文件位于 `/tmp/known_genes_v2056.jsonl`。
