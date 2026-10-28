# KnownGene 模块数据替换 — 共享调查上下文（Lead 维护）

> 本文件是团队共享的**事实基线**，Lead 已核实。队友只读；如需补充事实请在自己交付物中写明，并消息告知 Lead。
> 阶段：**调查 + 计划**。本阶段禁止改代码、禁止写生产库、禁止 git commit。

## 0. 任务目标

用新整理的已知基因清单（Excel v2055，1420 行 × 17 列）**替换** WheatOmics 网站 KnownGene 模块
（前端 `/genes/`，后端 `/api/genes/known/*`，MySQL `cloned_gene_db.cloned_gene_tbl`）的现有数据（520 行），
并因字段/数据语义变化调整前端展示与 API。本阶段产出实现计划，不实施。

- 新数据文件（快照，仍可能被继续编辑）：
  `/Users/mashengwei/Desktop/markdown/陈甜甜/known-gene-paper-20260916/已知基因逐条提取清单_20261019-合集_修正版v2055_20261019.xlsx`
- 仓库：`/Users/mashengwei/Desktop/markdown/wheatomics/FastAPI_backend_Port8000`（git HEAD `5364ca3`）
- 生产节点 git HEAD 相同；部署方式 = `git pull` + `sudo systemctl restart wheatomics-api`

## 1. 新 Excel 数据事实（已用 pandas 实测 v2055）

主 sheet `数据（修正版v2055）`：**1420 行 × 17 列，17 列全部 100% 非空**。

| # | 列名（入库） | 非空 | 最大字符 | 均值字符 | 语义/备注 |
|---|---|---|---|---|---|
| 1 | gene_id（入库） | 1420 | 28 | 18.0 | 混杂：TraesCS 1158、GenBank-like 164、HORVU 56、其他 42（如 `MLOC_7938.1`/`TRITD3Av1G083050`/`tplb0011k19`/`TuSPR`/`TCONS_00093333`） |
| 2 | 参考基因组ID（入库） | 1420 | 42 | 19.2 | TraesCS 1293、HORVU 77、other-alpha 26、GenBank-like 24；**新增字段**，与 gene_id 不同的行 180 行 |
| 3 | gene_name（入库） | 1420 | 43 | 8.2 | 同名重复 2 行；归一化后重复 6 行 |
| 4 | 物种信息（入库） | 1420 | 668 | 109.5 | **296 个不同字符串**；既含 `Triticum aestivum (bread wheat)` 也含带材料长描述的变体（最长 668 字符，60 行 >500 字符） |
| 5 | chrom_pos（入库） | 1420 | 41 | 30.6 | **38 种**染色体标签：小麦 21（1A–7D）+ 非小麦 17（大麦 1H–7H、黑麦 1R/6R、1S/2V/6S/6U/6V、7E、`chr51/chr54` 等），非小麦行 95；chrom_pos 前缀=参考组装名（Refv1.0 1298 / MorexV3 72 / Zavitan.v1.0 6 / …） |
| 6 | gene_phenotype（入库） | 1420 | 1677 | 368.9 | **1070 个不同值**；897 行含 `;`；多为「性状 + 机制说明」长文本，99 行 >1000 字符 |
| 7 | key_result（入库，≤500 词英文） | 1420 | 3051 | 1180 | 词数 40–464（无 >500），平均 166 词 |
| 8 | function_description（入库） | 1420 | 2236 | 1141 | 长文本 |
| 9 | 蛋白家族（入库） | 1420 | 2657 | 591 | **新增字段**；1176 个不同值；多为「family - 功能描述」长文本 |
| 10 | cloning_method（入库） | 1420 | 51 | 19.3 | 8 种受控值：Homology-based cloning 569 / Not reported 304 / Transcriptome-based 250 / Map-based 184 / Functional 106 / 组合值少量 |
| 11 | cloning_method_description（入库） | 1420 | 1757 | 909 | 长文本 |
| 12 | 验证方法（入库） | 1420 | 2114 | 494 | **新增字段**；895 种组合，`; ` 分隔的方法标签（Expression analysis / VIGS / CRISPR-Cas9 / Overexpression …） |
| 13 | 研究策略（入库） | 1420 | 16 | 15.8 | **新增字段**；3 种受控值：Reverse genetics 1061 / Forward genetics 281 / Not reported 78 |
| 14 | 功能大类（入库） | 1420 | 32 | 23.2 | **新增字段**；5 种受控值：Biotic & Abiotic Stress 776 / Quality & Yield 202 / Morphology & Domestication 154 / Physiology & Metabolic Processes 146 / Reproduction & Phenology 142 |
| 15 | title（入库） | 1420 | 473 | 124.9 | 多值以 `; ` 分隔（题名与 DOI/年份**按位置一一对应**） |
| 16 | doi（入库） | 1420 | 82 | 25.1 | 整格去重 820 个唯一值；**按 `; ` 拆分后 883 个唯一 DOI / 1570 条引用**；130 行含多 DOI；均为合法 DOI 格式 |
| 17 | publication_year（入库） | 1420 | 16 | 4.6 | 115 行是 `2008; 2024` 这类多值 → 现库 `year(4)` 装不下 |

**`说明` sheet 关键约定（作者原文）**：
- 全表统一用**半角分号+空格 `; `** 分隔多值；第 k 个 DOI ↔ 第 k 个题名 ↔ 第 k 个年份一一对应。
- D7：同一参考基因组 ID 的多行**全部保留**（不是重复行，是不同的基因名/等位/文献）。
- D5：gene_id 里的基因名保留不动（所以 gene_id 会是大麦/粗山羊草/GenBank 等异构 ID）。
- 物种按 NCBI Taxonomy 统一为「学名 (英文常用名)」——但实测仍有 60 行带长材料描述（未完全清理，需在导入层归一化）。

**数据质量实测（2026-10-28 复核）**：无 tab/newline/CR 字符；无 BMP 外字符；**真实 HTML 标签 0 行**（58 行含 `<`/`>` 但均为 `p < 0.05` 类数学符号，前端只需 `esc()`，不要 strip 标签）；**23 行含 `#`**（如 `Tahsfa1 lines #1 and #2`、`7S#1`）——现有 `app/services/legacy_parsers.py:normalize_text()` 会把 `#` 换成 `'`，属**必须修的后端 bug**；gene_id 重复 25 行、参考基因组ID 重复 34 行（按 D7 属预期）、DOI 重复 600 行（同一文献多基因，属预期）；另：`/api/genes/known/search` 的 SQL 未 SELECT publication_year（现有 bug，返回恒 null）。
**另有 8 个辅助 sheet**：修改记录(1153)、物种改写明细(1024)、文本清洗明细(338)、未决清单(空)、D10 key_result草案(空)、K补写依据(36)、K补写依据(全文)(16)、说明(32)。详见 data-profiler 交付物。

## 2. 现有生产库事实（2026-10-28 实测，MySQL 5.7.33）

库 `cloned_gene_db`（服务器 localhost，应用账号 `wheatomics_user`，**无 DDL 权限**；DDL 需 MySQL root，
root 凭据在服务器 `/root/.my.cnf`（`sudo mysql` 免密仅 root）与本机 `~/.config/lab-server/wheatomics.env`
的 `WHEATOMICS_MYSQL_ROOT_PASS`；fei 的 `sudo` 需要密码）。

`cloned_gene_tbl`（**520 行**，AUTO_INCREMENT=527，clone_id 1–526，缺 6 个）：
```sql
clone_id int(10) unsigned NOT NULL AUTO_INCREMENT,
gene_id varchar(300), gene_name varchar(500), chrom_pos varchar(500),
gene_phenotype varchar(1000), gene_species varchar(500),
paper_title text, paper_doi text,
key_result varchar(15000) NOT NULL,
author varchar(100) NOT NULL, author_mail varchar(200) NOT NULL,
submission_date date,
publication_year year(4),
function_description text,
cloning_method varchar(255),
cloning_method_description text,
PRIMARY KEY (clone_id)
-- ENGINE=InnoDB DEFAULT CHARSET=utf8（3 字节，非 utf8mb4）；gene_id/gene_name 无索引
```
现有列填充：除 function_description 空 7、cloning_method/cloning_method_description 空 4 外全部有值；
`paper_title` 最长 8110、`key_result` 最长 15000（均为 CGI 时代 `###`/制表符多值拼接）；
`gene_species` 是自由文本（`Triticum aestivum` 244 / `wheat` 164 / `Hordeum vulgare` 27 / `common wheat` 16 … 同义写法混杂）；
`gene_name` 唯一 463（同源拷贝同名）；`paper_doi` 有 `;` 分隔的多 DOI 元素（未拆开）。

同库其他表（历史遗留，都在 `cloned_gene_db`）：
- `cloned_gene_temp` 1037 行（上一轮导入用的 staging 表，latin1，列与现表不同，无 clone_id）
- `cloned_gene_tbl_backup_null` 575 行（2026-10-20 前后的整表备份）
- `cloned_gene_tbl_subdate_backup_20261020` 575 行（只备份 clone_id+submission_date）
- `cloned_gene_bad_import_backup` **1636 行**（上一次「坏导入」的残骸：`paper_title` 里混入整行 TSV、
  `\r\n`、引号错位，证明**制表符/引号导入曾失败**——本次导入必须用可靠序列化 + 事务 + staging）
> 注意：`cloned_gene_bad_import_backup` 的 1636 行说明历史上曾尝试导入约 1636 行的同类清单但没有成功上线。

### 2.4 新旧 ID 版本与 clone_id 映射（Lead 2026-10-28 生产实测）

- 旧库 520 行 gene_id 版本：v02（02G）461、v01 10、GenBank 30、HORVU 2、v03 仅 1、其他 16；
  新数据参考基因组ID：**v03（03G）1291**、HORVU 77、GenBank 24、TRITD 3、其他 25 → 直接 gene_id 匹配只有 7–10 行。
- 通过 `Genehub_DB.GenePageIWGSCv1_table`（应用账号有 SELECT）把旧 v1/v2 → v3：475/520 有映射；
  匹配结果：gene_id 直配 7、映射后 v3 匹配 290、gene_name 匹配 226、任一匹配 324。
- **clone_id 继承（gene_id → 映射 v3 → gene_name 优先级，一对一）= 321/520（62%）；199 个旧 clone_id 会孤儿（旧 URL 404）**。
  → 若要求旧链接 100% 可用，需保留旧 520 行到 `cloned_gene_tbl_legacy` 并让 `/known/{id}` 回退查询（见计划 §8 Q3）。
- `/api/genes/known/all` 新数据 payload 估算：若摘要加长文本约 **1.10 MB**（现 520 行 97.9 KB）→ 列表分页 + `/stats` 服务端聚合是必需项。

## 3. 现有后端/前端事实

后端（`app/api/routers/gene.py`，router prefix `/genes`）：
- `GET /api/genes/known/search?searchid=`：在 gene_id/gene_name/chrom_pos/gene_phenotype/gene_species/
  paper_doi/function_description/cloning_method/paper_title 上 `LIKE %term%`，返回 `records[]`（含 dois）。
- `GET /api/genes/known/all`：仅 6 列摘要（clone_id/gene_id/gene_name/chrom_pos/phenotype/species）。
- `GET /api/genes/known/by-chromosome/{chromosome}`：`chrom_pos LIKE '<chrom>%'`。
- `GET /api/genes/known/{gene_id}`：数字 → clone_id；否则 gene_id/gene_name 精确匹配；返回详情
  （paper_title[]/references{doi,title}[]/key_result[] 由 `split_legacy_multi_value` 按 `###` 切分）。
- 校验 `ensure_gene_like`：`^[A-Za-z0-9_.:-]+$`（新 gene_id 全部可通过）。
- schemas：`app/schemas/gene.py` KnownGeneSummary/KnownGeneDetail；CGI 旧页面（`cgi-py-RawScript/gene_search*.py`、
  `gene_submit*.py`）也直接读写该表（只用固定旧列，**加列兼容**，但删列/改名会破坏它们）。
- 相关脚本：`scripts/import_cloned_genes.py`（批量导入，按 gene_name/gene_id 查重，支持 `--dry-run/--commit`）、
  `scripts/backfill_publication_year.py`（Crossref 回填）、`scripts/scan_gene_annotations.py`。

前端（`app/static/genes/`，由 main.py 挂载 `/genes`）：
- `index.html`：Search tab（field 下拉**实际未生效**，只发 searchid）+ 结果卡片（gene_name/gene_id/染色 badge/
  species/phenotype/DOI 数）+ 导出 CSV + Stats tab（**客户端**用 `/known/all` 自行聚合：总基因数、覆盖小麦染色体 21、
  物种数、表型数；染色体柱状图与 Top15 phenotype）。
- `detail.html`：gene_name/gene_id、meta(clone_id/submission_date)、Chromosome/Species/Phenotype/Publication year
  四卡片、Key results / Function description / Cloning method / References / Submitted by。
- 线上 `https://wheatomics.sdau.edu.cn/genes/` 200；线上数据 520 条；`/api/genes/known/1` 实测返回正常。
- 生产 `/var/www/html` 下还有 V2.0 首页等静态页（**不在本仓库**），首页有 KnownGene 工具卡（指向 `/genes/`，本次预计不需改）。
- 前端详细改造方案见 `docs/known_genes/frontend_change_spec.md`（1054 行）：含 17 字段展示映射、GeneHub 链接定案（仅 `^TraesCS\d`/`^Traes_` 1291 行可链 `/GeneHub/?search=`）、`/stats` 建议契约、CSV 19 列、detail 迁 `_v2` shell（现基线视觉检查 FAIL）、15 项 FE 任务 ≈23–25 h。

部署/验证约束（`CLAUDE.md`/`MAINTENANCE.md`）：Bootstrap 4.5.3 + jQuery 1.9.1 本地资源、无 CDN；
SPA 改动前必须 `bash scripts/spa_visual_check.sh <url>` 通过多宽度渲染检查；标题 `ModuleName - WheatOmics`。

## 4. 目标 API 契约草案（Lead 定，后端/前端都按此对齐；实现阶段可微调但要双方同步）

原则：**向后兼容**（现有字段名/语义不删不改），新增字段用新名称；详情页字段语义从「旧多值」升级为「结构化列表」。

1. `GET /api/genes/known/all`：保持现有 6 字段不变；**新增** `reference_genome_id`, `functional_category`,
   `species_primary`（归一化物种，如 `Triticum aestivum`）, `research_strategy`；可选 `limit/offset`（默认全量）。
2. `GET /api/genes/known/search`：保持 `searchid` 必填；**新增可选 `field`**：
   `all`(默认) | `gene_id` | `gene_name` | `reference_genome_id` | `phenotype` | `species` | `doi` |
   `protein_family` | `functional_category`。返回摘要记录同 `/all` + `dois`。
3. `GET /api/genes/known/by-chromosome/{chromosome}`：大小写/`chr` 前缀兼容；chrom_pos 匹配支持 `3H`/`1R` 等非小麦；
   返回同 `/all`。
4. `GET /api/genes/known/{gene_id}`：数字仍按 clone_id；新增 `reference_genome_id`, `protein_family`,
   `validation_methods[]`, `research_strategy`, `functional_category`, `publication_years[]`,
   `species_primary`；`references[]` 由 title/doi/year 按 `; ` **位置对应**拆分（每项 `{doi,title,year}`）；
   旧字段 `paper_title[]`/`key_result[]`/`function_description`/`cloning_method*` 保留。
5. **新增** `GET /api/genes/known/stats`：服务端聚合（total、species_primary 分布、染色体分布、functional_category、
   research_strategy、top phenotype 标签、publication_year 分布），供 Stats tab 使用，避免前端拉全量长文本。

## 5. 证据文件（本地）

- `docs/known_genes/_evidence/current_api_known_all.json`：线上 `/api/genes/known/all` 全量 520 条快照。
- 生产 DB 元数据/列统计：由 Lead 随查随记，见本文件第 2 节。

## 6. 团队边界与纪律

- **只读生产**：可通过 Lead 约定方式读取生产库；**任何写操作（DDL/DML/部署）都不在本阶段**。
- 不要自行开 SSH 会话（跳板机并发会话有限；需要远程查询时消息 Lead 代查）。
- 只在各自交付文件里写内容，不改代码、不改 CONTEXT.md、不 git commit。
- 路径解析：Excel 用本机 `/Users/mashengwei/.dsh/.../python/bin/python3`（含 pandas/openpyxl）。
- 完成后用 `send_message` 给 lead：交付文件路径 + 5–10 条关键结论 + 未决问题。
