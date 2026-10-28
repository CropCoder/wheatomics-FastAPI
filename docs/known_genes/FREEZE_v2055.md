# KnownGene v2055/v2056 数据冻结与用户决策记录（2026-10-28）

> 本文件记录用户对 `KnownGenes_v2055_update_plan.md` §8 决策的回答、数据冻结快照、以及
> 由这些决策产生的实施口径。后续所有脚本/DB/前端操作以此为准。

## 1. 用户决策（2026-10-28，逐条对应计划 §8）

| # | 决策项 | 用户决定 | 实施口径 |
|---|---|---|---|
| Q1 | v2055 是否冻结 | **冻结锁定** | v2055 只读留档（md5 见 §2）；先修 16 行异常产出 v2056，v2056 作为导入源并重新记录 md5 |
| Q2 | 替换策略 | **全量替换** | `cloned_gene_tbl` 内容最终 = v2056 的 1420 行；旧 520 行中未映射的 199 行删除（旧表全量备份） |
| Q3 | 旧详情页 URL | **只保留替换成功的；使用内部 ID** | 仅 321 个成功映射的旧 `clone_id` 保留并继续可用；199 个未映射旧 ID 不复用（旧链接 404）；**不建 legacy 回退表**；详情 URL 继续用内部 `clone_id`（`/genes/detail.html?id=<clone_id>`） |
| Q4 | 新字段展示 | **全部展示** | 参考基因组ID、蛋白家族、验证方法、研究策略、功能大类全部在列表/详情展示 |
| Q5 | 16 行多值异常 | **先试试修正** | 已用 Crossref 逐 DOI 核实并生成 v2056（16 行 / 19 单元格），修正后才导入；详见 `multi_value_fixes_v2056.md` |
| Q6 | 上线与公告 | **迁移（detail 迁 `_v2` shell）、需要更新 News 公开** | 前端 detail 本轮迁 `_v2` shell；上线后更新生产 `/var/www/html/V2.0/news.json` 公告 KnownGene 升级 |

**由计划默认值沿用（用户未另行否决）**：
- 物种展示：列表/统计用归一化学名（23 个），详情显示学名 + 英文常用名，材料长描述折叠；
- 新行作者占位：`author='WheatOmics curation'`、`author_mail='shengweima@icloud.com'`、`submission_date='2026-10-28'`；
- 标题规范：`KnownGene - WheatOmics`；
- 历史遗留表（cloned_gene_temp 1037 / bad_import 1636 / backup_null 575 / subdate_backup 575）本次不动，稳定 1–2 周后另立项清理；
- 不新增 `data_version` 列（版本溯源记录在表注释 `data version v2056 imported 20261028` 与本文档）；
- 页面标题/导航遵循 MAINTENANCE（Bootstrap 4.5.3 + jQuery 1.9.1 本地资源、`_v2` shell）。

## 2. 冻结快照

| 文件 | 位置 | md5 | 大小 | 说明 |
|---|---|---|---|---|
| v2055（冻结原始） | `/Users/mashengwei/Desktop/markdown/陈甜甜/known-gene-paper-20260916/已知基因逐条提取清单_20261019-合集_修正版v2055_20261019.xlsx`（及 `frozen_20261028/` 副本） | `85f3e6207bba347fb1d7dcddda881cd6` | 1,688,313 B | 用户冻结版；只读，不再改动 |
| v2056（修正后导入源） | 同目录 `已知基因逐条提取清单_20261019-合集_修正版v2056_20261028.xlsx`（及 `frozen_20261028/` 副本） | `1dbbeff77f8f53eb33e8ea133d32cb65` | 1,690,742 B | v2055 + 16 行多值修正；sheet 改名 `数据（修正版v2056）`；新增 `修正记录v2056` sheet |
| 提取 JSONL | `scripts/known_genes_v2055/out/known_genes_v2056.jsonl`（生产 `/tmp/known_genes_v2056.jsonl`） | `33e7f2881c073f41776238ad7ef189b2` | 8,054,314 B | 1420 行 × 23 字段，供迁移脚本 |
| 校验报告 | `scripts/known_genes_v2055/out/validation_report.md/json` | — | — | fatal 0；多值异常 0；23 物种 / 38 染色体 / 1570 引用·883 DOI |
| clone_id 映射报告 | `scripts/known_genes_v2055/out/migration/` | — | — | 321/520 继承（61.7%），199 孤儿，1099 新行 527…1625 |

## 3. 迁移口径（生产实测）

- 旧表：`cloned_gene_db.cloned_gene_tbl`，520 行，`MAX(clone_id)=526`，AUTO_INCREMENT=527。
- 映射分层（生产 `Genehub_DB.GenePageIWGSCv1_table` 只读查询 + 行级规则）：
  - `T2_v3` 290（旧 v1/v2 gene_id 映射到 v3 = 新参考基因组ID）
  - `T1_id` 10、`T1_id_token` 3（gene_id 直接/按 token 命中）
  - `T3_name_chrom` 5（同名 + 同染色体）、`T3_name` 13（同名，旧行无染色体）
  - **合计 321/520（61.73%）**；`T3_name` 不再跨染色体/跨物种错配（EGT2 5H 案例已保护）
- 旧行 199 个未映射（删除，clone_id 不复用）；新行 1099 个分配 `527…1625`，导入后 `AUTO_INCREMENT=1626`。
- 已知旧库异常：`clone_id 28/29` 的 gene_id/gene_name 两列错位（`TaBot1-4D`/`TraesCS4D02G326900` 等），
  映射阶段已自动交换修正（mapping CSV `swap_fixed=True`）。
- 旧库 2 行 `chrom_pos` 与 gene_id 染色体不一致（历史标注问题），映射以 gene_id→v3 为准，不影响结果。

## 4. 数据修正（v2055 → v2056）

详见 `docs/known_genes/multi_value_fixes_v2056.md`：16 行 / 19 单元格，
12 行补第 2 篇年份、3 行（TaGW8-7A/B/D）补题名+年份、1 行（VRN-D3/FT-D1）删除重复题名；
Crossref 实时核实；修正后全表 1420 行 title/doi/year 三列 100% 位置对齐。
