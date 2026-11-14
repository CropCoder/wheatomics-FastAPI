# CWI 22960 平台接入 · 执行记录（2026-11-14）

## 结果：已上线 ✅

数据集名 **AABB_Carthlicum_CWI22960**，显示名 "Carthlicum wheat CWI 22960 (AABB)"。

### 线上产物
| 模块 | 结果 |
|---|---|
| 数据目录 | `/var/www/data/masw_data/AABB_Carthlicum_CWI22960/`（fa/gff3/cds/pep + provenance） |
| BLAST | `.genome`（10,722 seq / 10,881,024,180 bp）+ 14 条染色体拆分库 + `.add_Description.cds/pep`（102,975）+ 带 EggNOG/02G Description |
| 基因功能表 | `Genefunc_AABB_Carthlicum_CWI22960_table` = 102,975 行；ChineseSpring02G 已回填 |
| JBrowse | 数据集 refSeqs 10,722；all_gene + DNA + **4 个 RNA-seq bigWig 轨道**（Leaf/Root/Stem/All CPM） |
| JBrowse V2 页面 | AABB 分区 22→23 张卡片；hero 217→218；status 210→211 |
| genome_registry | 行已写入（ploidy AABB、subgenomes A,B、chromosome_count 14、genome_size 10,881,024,180、gene_count、annotation available） |
| Genefunc_registry | 行已写入（Group=Tetraploid，示例 `Chr1A_Carthlicum_CWI22960:200-500` / `TrcarCWI22960.r1.1A01G000110.1`） |
| getfasta 聚合 | all_genomes/all_gene(s)/all_protein(s) 均含新基因组；`getsequence_search.txt` 已加示例行 |
| Web BLAST | `/api/blast/databases` 分类 = **Tetraploid wheat genome**（tetraploid_wheat 361 库） |
| PrimerServer2 | `/api/PrimerServer2/databases` 已含 `.genome` |
| BLAST↔JBrowse 映射 | 重建完成，`--check` CHECK OK（202 库 / 201 匹配 / 99.5%） |
| 计数 | 平台 total 325→326；AABB 21→22；JBrowse 219→220；getfasta 203→204 |

### 公网验收（https://wheatomics.sdau.edu.cn）
- `/api/genomes/AABB_Carthlicum_CWI22960` → 200 ✓
- `/api/jbrowse/datasets/…/trackList` → 6 轨（含 4 bigWig）✓
- bigWig Range 请求 → **206**（1024 bytes）✓
- `/jbrowse.html` → 卡片存在 ✓
- `/api/blast/databases` → 新库 51 处出现、分类 tetraploid_wheat ✓
- `/api/genes/functions/registry` → 新表存在（getfasta 面板数据源）✓
- `/api/sequence/by-interval?region=Chr1A_Carthlicum_CWI22960:200-500&database=all_genomes` → 返回序列 ✓
- `/api/sequence/by-gene?gene_id=TrcarCWI22960.r1.1A01G000110.1&protein_db=all_proteins` → 返回蛋白 ✓

## 代码改动
- commit `c408097`（github + gitee）：blast.py 加 carthlicum/dika 关键词；registry override；renumber_gff_ids `--chr-suffix` + 非编码转录本类型
- 生产已 pull；API 已重启两次
- `app/static/docpages/jbrowse.html` 回写（卡片/计数）并随本次提交入库

## 事故与修复（重要）
**现象**：G4 `finish_genome_integration.sh` 运行后，5 个聚合库别名（all_genomes/all_gene/all_genes/all_protein/all_proteins）被**覆盖为只含新基因组**，导致全平台 GetSequence 的 CWI22960 之外查询失效，`getfasta` 统计从 203 掉到 1。

**背景**：平台已于 2026-11-13 迁移到 **base + delta** 聚合库架构（`docs/workflow/blast-aggregate-base-delta.md`）：all_gene(s)/all_protein(s) 的 DBLIST 应为 `all_genes_base`/`all_proteins_base` + 增量成员；`all_genomes` 仍为 203 个 per-genome 成员（已超 200 上限）。

**修复**：从 G4 自动备份 `backup_20261114_100232` + 前置备份 `_backup_20261114_cwi22960` 恢复 5 个别名；再按新架构用 `scripts/update_blast_alias.py --mode append` 追加本基因组 cds/pep delta；`all_genomes` 因工具拒绝 >200 成员，采用手工原子写入（新成员前插，204 成员，已知超限限制）。最后重跑 `rebuild_genome_registry.py` 恢复 `getfasta_member` 标志（203→204），`getfasta` 统计恢复 203→204。

**遗留风险**：`finish_genome_integration.sh` 的 step_aliases 仍是旧「改写 DBLIST」逻辑，与 base+delta 架构不兼容；下一个新基因组接入前应改为调用 `update_blast_alias.py --mode append`（并对 all_genomes 的 200 上限单独处理）。建议后续更新 SOP + 脚本。

## 待办（可选）
- cite.html 增加论文引用块（DOI 10.1038/s42003-026-11303-8）
- 把本次经验回写 `docs/workflow/wheatomics-new-genome-sop.md`（base+delta 章节 + 别名事故）
