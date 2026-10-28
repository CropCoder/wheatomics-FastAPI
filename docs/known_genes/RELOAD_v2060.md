# KnownGene v2060 全库重导入与 v2061 校正记录（2026-10-28）

> 用户提供新整理版 `已知基因逐条提取清单_20261019-合集_修正版v2060_20261019.xlsx`（md5 `3e5f42db018585a918516be56a21d976`），
> 要求「全库重新导入」并把「图位克隆（map-based cloning）基因放前面」。
> 结论：**812 行内容发生变化（1165 个单元格）+ 功能大类从 5 类拆成 6 类**，不适合走写接口逐条更新；执行**全库重导入**，
> clone_id 100% 继承（1420/1420），旧链接全部保持可用。

## 1. v2060 vs 已上线的 v2056：差异规模

| 项目 | 结果 |
|---|---|
| 行数 | 1420 → 1420（不变） |
| 列 | 17 列不变 |
| 身份变化 | 1 行改名：`TaSPL6B` → `TaSPL6-B`（gene_id 不变，clone_id 可继承）；无新增/删除基因 |
| 内容变化 | **811 行 / 1165 单元格** |
| 变化字段 | 功能大类 776、gene_phenotype 346、publication_year 17、function_description 9、title 6、doi 2、key_result 2、cloning_method 1、cloning_method_description 2、验证方法 2、研究策略 2 |
| 功能大类 | **由 5 类拆为 6 类**：`Biotic & Abiotic Stress`(776) → `Biotic Stress`(415) + `Abiotic Stress`(361)；其余 4 类不变 |
| 多值对齐 | v2060 又出现 16 行 title/doi/publication_year 数量不一致（与 v2055 相同的 16 行，content 与 v2055 一致），已用 Crossref 核实值重新修正 |

> 结论：811/1420 行变动（57%）且涉及受控词表变更，逐条走写接口会产生 800+ 请求且难以保证整体一致；**全库重导入更稳、可整体校验/回滚**。

## 2. 导入源校正：v2060 → v2061

按"原始表永不修改 + 版本化 patch"原则，生成修正副本（原始 v2060 未动）：

| 文件 | 位置 | md5 | 说明 |
|---|---|---|---|
| v2060（用户版） | 数据目录 + `frozen_20261028/` | `3e5f42db018585a918516be56a21d976` | 原始整理版，只读留档 |
| **v2061（导入源）** | `已知基因逐条提取清单_20261019-合集_修正版v2061_20261028.xlsx` + `frozen_20261028/` | `719f1616dd9a92917ad468e516ae9906` | v2060 + 16 行多值修正（19 个单元格，Crossref 核实）；主 sheet 改名 `数据（修正版v2061）`；新增 `修正记录v2061` sheet |
| JSONL | `scripts/known_genes_v2055/out/known_genes_v2061.jsonl`（生产 `/tmp/known_genes_v2061.jsonl`） | `d9ea60f06d1ae3e3c8907d0bdda99186` | 1420 行，fatal=0、多值异常=0 |

修正明细与 patch 文件：`scripts/known_genes_v2055/multi_value_patch_v2060.json`；提取器（`extract.py --patch`）只在当前 title/doi/year
仍等于 patch 记录的原始值时才应用，避免覆盖用户后续修改（v2061 上自动识别为 already-corrected，0 覆盖）。

## 3. 全库重导入执行（生产）

| 步骤 | 结果 |
|---|---|
| 备份（root） | `cloned_gene_tbl_backup_20261028_v2061`（重导前 v2056 数据 1420 行）；原 `cloned_gene_tbl_backup_20261028`（520 行原始数据）继续保留 |
| staging（root） | `cloned_gene_tbl_staging_20261028_v2061` |
| clone_id 映射 | **1420/1420 继承（100%）**：T0 pair（gene_id+gene_name 完全一致）1419 + T1 gene_id（TaSPL6B→TaSPL6-B）1；0 新行、0 孤儿、max clone_id 仍 1625 |
| 替换 | 单事务 `DELETE FROM cloned_gene_tbl` + `INSERT ... SELECT FROM staging`，staged 1420 / 目标 1420 |
| verify | PASS：1420 行 / distinct clone_id 1420 / 必填空 0 / 23 species / 38 chromosome / 6 functional categories / 3 strategies / `#` 保留 18 行 |
| 审计 | `known_gene_change_log` 新增 `full_import` 摘要行（id=9，actor=`script:known_genes_v2055.full_reload`，after_json 含行数/分类/clone_id 12 前后对照） |
| 表注释 | `cloned_gene_tbl` COMMENT 更新为 `data version v2061 (from v2060) imported 20261028` |

**回滚**（如需回到 v2056 数据）：
```bash
cd /var/www/FastAPI_backend_Port8000
/home/fei/mambaforge/envs/zjw/bin/python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py \
  --phase rollback --commit --jsonl /tmp/known_genes_v2061.jsonl --report-dir /tmp/kg_migration_v2061 \
  --backup-table cloned_gene_tbl_backup_20261028_v2061 \
  --staging-table cloned_gene_tbl_staging_20261028_v2061
```

## 4. 功能大类 6 值适配（前后端）

- 写接口受控词表（`app/services/known_gene_ingest.py`）更新为 6 值；旧值 `Biotic & Abiotic Stress` 现在会被 422 拒绝；
- 前端列表/详情徽章、Stats 图表、筛选 chips 支持 `Biotic Stress` / `Abiotic Stress`（旧合并值仍保留兼容 class，用于回滚窗口）；
- `docs/known_genes/WRITE_API.md` 示例与字段说明同步。

## 5. 「图位克隆基因放前面」（排序实现）

用户建议把 map-based cloning 的 184 个基因排在前面。实现为**服务端默认排序**（三处列表端点统一）：

```sql
ORDER BY (cloning_method = 'Map-based cloning') DESC, clone_id
```

- 生效端点：`GET /api/genes/known/all`、`/known/search`、`/known/by-chromosome/{chromosome}`；
- 前端列表信息栏显示 `· map-based cloning first`，搜索框 helper 也注明「Map-based cloning genes are listed first.」；
- 生产验证：前 50 行 **50/50 全部为 Map-based cloning**；全库 map-based 共 184 行；
- 说明：分页/筛选/导出均基于该排序；若以后需要其他排序（如按基因名/年份），可再加 `sort` 参数。

## 6. 生产验收（2026-10-28 20:0x）

| 检查 | 结果 |
|---|---|
| `/known/all` total | 1420 |
| `/known/stats` | 6 categories（Biotic 415 / Abiotic 361 / Quality 202 / Morphology 154 / Physiology 146 / Reproduction 142）、23 species、38 chromosome、refs 1570·883 DOI |
| 排序 | DB 按新 ORDER BY 取前 50 行 = 50 行 Map-based cloning |
| 旧链接稳定性 | `clone_id=12`（Sr60）前后完全一致；1420/1420 clone_id 继承 |
| v2060 内容生效 | `clone_id=17`（TaVRN-A1）已显示 v2060 更新后的 2 篇文献（DOI 10.1111/tpj.12326 / 10.1073/pnas.0937399100）、cloning_method=Map-based cloning |
| 写接口 | 新分类 `Biotic Stress` dry-run 200；旧合并值 422；`/write/changes` 首条为 full_import |
| 前端 | 列表显示 `map-based cloning first`；Stats KPI=6、图表 6 类；类别徽章新值正常；`spa_visual_check`/ego-browser 截图验证 |

截图：`docs/known_genes/_evidence/ui/prod/v2061-browse-w1440.png`、`v2061-stats-w1440.png`（PNG 本地留档，gitignore）。
