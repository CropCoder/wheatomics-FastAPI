# KnownGene（已知基因）模块数据替换与前端改造计划（v2055，待确认）

> 触发：用户提供新整理的已知基因清单
> `已知基因逐条提取清单_20261019-合集_修正版v2055_20261019.xlsx`（1420 行 × 17 列），
> 要求替换网站 KnownGene 模块（前端 `/genes/`、后端 `/api/genes/known/*`、MySQL `cloned_gene_db.cloned_gene_tbl`）
> 的现有数据（520 行），并因字段/语义变化调整前端展示。
>
> 调查日期：2026-10-28 ｜ 依据：生产库**只读**实测（MySQL 5.7.33）、仓库代码、线上 API/页面实测、Excel 全表剖析
> 详细交付物：
> - `docs/known_genes/data_profile_v2055.md`（971 行：逐列剖析/字段映射/数据治理/校验规则）
> - `docs/known_genes/backend_investigation.md`（1298 行：代码影响面/完整 DDL/迁移脚本设计/4+1 端点 API/验证 SQL/回滚）
> - `docs/known_genes/frontend_change_spec.md`（1054 行：17 字段展示映射/Search/Stats/detail 重构/15 项前端任务）
> - `docs/known_genes/CONTEXT.md`（共享事实基线）、`docs/known_genes/_evidence/current_api_known_all.json`（旧数据快照）
>
> **本文件只是计划：本阶段未改动任何生产数据、代码或服务。**

---

## 0. 结论先行

| 维度 | 现状（生产） | 新数据（v2055） | 影响/结论 |
|---|---|---|---|
| 记录数 | 520 行（clone_id 1–526，缺 6 个） | 1420 行 × 17 列（100% 非空） | 数据量 ×2.7；列表/统计/导出都需重估 |
| 字段 | 14 列（clone_id + 13 数据列） | 17 列，其中 **5 个新语义字段** | 需 DDL 加列（+ 3 个派生/辅助列）+ API/前端扩展 |
| 字段长度 | phenotype ≤93、species ≤30、key_result ≤15000（被截断） | phenotype 最长 **1677**、species **668**、key_result 3051、protein_family 2657、验证方法 2114 | 现表 `varchar(1000)`/`varchar(500)` 在 STRICT 模式下会**报错**，必须加宽（建议 2000/1000 而非 TEXT，见 §3.1） |
| publication_year | year(4) | 115 行多值（`2008; 2024`），且 47 行多值非升序 | **保持 `year(4)` 存最早年份 + 新增 `publication_years VARCHAR(64)` 存原文**，旧 API/CGI/backfill 零改动 |
| 物种 | 自由文本、同义混杂（`Triticum aestivum` 244 / `wheat` 164 / `common wheat` 16…） | 296 个原始字符串 → **23 个归一化学名**（0 未命中） | 派生 `species_primary`，否则物种统计虚高 |
| 染色体 | 基本只有小麦可解析 | **38 种标签**：小麦 21 + 大麦 7 + 外来种 8 + `chr51/54`；非小麦 95 行；2 行无 `chr` 前缀需 fallback | 前端「覆盖小麦 21 条染色体」统计失效；`by-chromosome` 端点必须改按新 `chromosome` 列（旧 `chrom_pos LIKE '<x>%'` 会全部失配） |
| 多值字段 | 旧库 `###` 拼接、`;` 混用 | 统一 `; `；**1404/1420 严格对齐，16 行异常**；883 个唯一 DOI / 1570 条引用；题名内合法 `;` 13 行 | 导入按 `; ` 拆 + 位置配对 + 缺失补 null；严禁裸切 |
| 身份键 | clone_id 主键；旧行 gene_id 为 **v02（02G）461 行**/v01 10 行 | gene_id 重复 25 行、参考基因组ID 重复 34 行（`说明` sheet D7：**属预期**）；新参考基因组ID **v03（03G）1291 行** | 不能单列去重；clone_id 经 v1/v2→v3 映射后可继承 **321/520（62%）**，199 个旧 ID 孤儿（见 §3.5） |
| 数据质量 | — | 无 tab/换行、无 BMP 外字符、**真实 HTML 标签 0 行**（`<` 是 `P<0.01` 类数学符号）；**26 行含 `#`**（会被现有 `normalize_text()` 改成 `'`，后端必修）；`/search` SQL 漏 SELECT publication_year（旧 bug）；1 个 gene_id（`Yr87/Lr85`）含 `/` 无法作为路径参数 | 导入校验 + 2 个后端 bug 修复 + 路径限制文档化 |
| 前端 | Search + Stats + 详情，按 520 条/小麦 21 染色体设计；`detail.html` 仍旧框架（多宽度基线视觉检查 FAIL） | 1420 条、长文本、多种物种、5 大功能类 | 需重构；`/all` 若带长文本约 1.10 MB（现 97.9 KB）→ 列表分页 + `/stats` 服务端聚合 |

**结论：可做。建议「全量替换（1420 行）+ clone_id 稳定映射（62% 继承；可选 legacy 回退表补足 100% 旧链接）+ 向后兼容扩展 API + 前端重构」。**

**工作量：最小可用方案 ≈16 h（2 人日）；推荐完整方案 ≈37–40 h（约 5 人日；前端 24 h 为主，可 2 人并行压到 3–4 个日历日）。**

**关键前置决策见 §8**：v2055 是否冻结、是否全量替换、旧 URL 策略、16 行多值异常是否先修 Excel、新字段展示范围、detail 页是否本轮迁 `_v2` shell。

---

## 1. 目标与范围

### 本轮做

1. 把 KnownGene 后台数据整体换成 v2055（1420 行），旧表完整备份、可一键回滚；
2. 扩展 `cloned_gene_tbl`：**追加 8 列**（5 个内容字段 + `species_primary`/`chromosome`/`publication_years`）+ 加宽 2 列；
   `publication_year` 保持 `year(4)`（存最早年份）；`key_result` 保持 varchar(15000)；
3. 后端 API 向后兼容扩展（4 个旧端点 + 新增 `/stats`），修 2 个旧 bug，新增 `field`/`limit`/`offset`；
4. 前端 `/genes/`（列表 + 统计）与 `/genes/detail.html`（详情）按新数据重构（详见 frontend_change_spec.md）：
   新字段展示、搜索字段生效、分页、统计图表重做、CSV 19 列、长文本截断展开、详情页迁 `_v2` shell；
5. 导入脚本、校验脚本、迁移/回滚脚本、验证清单与维护文档；可选 legacy 回退表。

### 本轮不做

- 不改 GeneHub（`/api/genes/detail/*`）与基因功能表（Genefuncdb）——参考基因组ID 只做外链跳转；
- 不改旧 CGI 提交页面（`cgi-py-RawScript/gene_submit*.py` 仍只写旧列；**新列只允许追加在末尾**，因为 `gene_search_by_id.py` 用 `SELECT *` + 位置下标读列）；
- 不做全文检索/Elasticsearch；不做 `limit/offset` 以外的分页架构（1420 行规模足够）；
- 不转 utf8mb4（物理上行大小会超限，见 §3.1），不改 `key_result` 类型；
- 不清理历史遗留表（另立项，见 §8 Q9）；不动生产 `/var/www/html` 首页/News 静态页（除非用户要求公告）。

---

## 2. 调查结果

### 2.1 新数据（v2055）关键事实

主 sheet `数据（修正版v2055）`：1420 行 × 17 列，全部非空；另有 8 个辅助 sheet（修改记录 1153、物种改写明细 1024、文本清洗明细 338、K补写依据 36 等）。

| Excel 列 | 非空 | 最大字符 | 均值 | 语义要点 |
|---|---|---|---|---|
| gene_id（入库） | 1420 | 28 | 18.0 | 异构：TraesCS 1158（v03 为主）、GenBank-like 164、HORVU 56、其他 42；重复 25 行；1 行含 `/`（`Yr87/Lr85`，不能作路径参数） |
| 参考基因组ID（入库） | 1420 | 42 | 19.2 | **新增字段**；v03/03G 1291、HORVU 77、GenBank 24、TRITD 3；与 gene_id 不同的行 180 |
| gene_name（入库） | 1420 | 43 | 8.2 | 精确同名 2 行（TaVRN-A1×3，D2 预期）；含 `/` 34 行（URL 需 encode） |
| 物种信息（入库） | 1420 | 668 | 109.5 | 296 个原始字符串 → 23 个归一化学名；263 行含多物种/材料段 |
| chrom_pos（入库） | 1420 | 41 | 30.6 | 38 种标签；前缀=参考组装名（Refv1.0 1298 / MorexV3 72 / Zavitan.v1.0 6 / Lo7.v1 4…）；2 行无 `chr` 前缀（Excel 297/711） |
| gene_phenotype（入库） | 1420 | 1677 | 368.9 | 1070 个不同值；897 行含 `;`，99 行 >1000 字符；前 ~667 行「标签体」、其后「叙述体」 |
| key_result（≤500 词） | 1420 | 3051 | 1180 | 40–464 词（中位 178） |
| function_description（入库） | 1420 | 2236 | 1141 | 长文本 |
| 蛋白家族（入库） | 1420 | 2657 | 591 | **新增字段**；1176 个值，多为「family - 功能描述」 |
| cloning_method（入库） | 1420 | 51 | 19.3 | 8 种受控值（Homology-based 569 / Not reported 304 / Transcriptome-based 250 / Map-based 184 / Functional 106 + 6 行组合） |
| cloning_method_description（入库） | 1420 | 1757 | 909 | 长文本 |
| 验证方法（入库） | 1420 | 2114 | 494 | **新增字段**；895 种组合，`; ` 分隔方法标签，平均 5.8 个/行 |
| 研究策略（入库） | 1420 | 16 | 15.8 | **新增字段**；3 种受控值：Reverse 1061 / Forward 281 / Not reported 78 |
| 功能大类（入库） | 1420 | 32 | 23.2 | **新增字段**；5 种受控值：Biotic & Abiotic Stress 776 / Quality & Yield 202 / Morphology & Domestication 154 / Physiology & Metabolic Processes 146 / Reproduction & Phenology 142 |
| title（入库） | 1420 | 473 | 124.9 | 多值 `; ` 分隔，与 DOI/年份按位置对应 |
| doi（入库） | 1420 | 82 | 25.1 | 拆分后 883 个唯一 DOI / 1570 条引用；130 行多 DOI |
| publication_year（入库） | 1420 | 16 | 4.6 | 1998–2026；**115 行多值**（95 行 2 个、20 行 3 个，按 token 合计 **1555** 个年份）；47 行多值非升序 |

**`说明` sheet 的强制约定**：多值统一 `; `；第 k 个 DOI ↔ 题名 ↔ 年份**位置一一对应**；
同一参考基因组 ID 多行全部保留（D7）；gene_id 中的基因名保留不动（D5）；物种按 NCBI Taxonomy 统一（实测已统一为 23 个学名）。

**数据质量实测**：
- 无 tab/换行/CR、无 BMP 外字符；**真实 HTML 标签 0 行**（58 行含 `<`/`>`，均为 `P<0.01`、`<70% similarity` 类符号 → 只 `esc()`，**不要 strip 标签**）；
- **26 行含 `#`**（按列：cloning_method_description 23、validation_method 19、key_result 14、gene_phenotype 13、function_description 10、protein_family 7、gene_species 3，行间有重叠），如 `7S#1`、`6Ae#3`、`EMS lines #1/#2`；
- 16 行多值数量不对齐：12 行「2 DOI+2 题名+1 年份」、3 行「2 DOI+1 题名」、1 行「3 DOI+4 题名（题名重复）」；
- 题名内合法 `;` 13 行（如 `(1,3;1,4)-β-D-Glucan`、`HKT1;4`）→ 只按 `"; "` 拆；
- 物种/表型/功能描述含 `;` 属于内容而非多值（按列区分）。

### 2.2 现网数据与数据库（生产实测）

- 服务器：WheatOmics 生产节点（经跳板机 SSH），MySQL 5.7.33；库 `cloned_gene_db`。
- `cloned_gene_tbl`：**520 行**，`clone_id` 1–526（缺 3/7/8/13/15/25），AUTO_INCREMENT=527；`ENGINE=InnoDB DEFAULT CHARSET=utf8`（utf8_general_ci）。
  列：clone_id、gene_id(300)、gene_name(500)、chrom_pos(500)、gene_phenotype(1000)、gene_species(500)、paper_title(text)、
  paper_doi(text)、key_result(15000) NOT NULL、author(100) NOT NULL、author_mail(200) NOT NULL、submission_date(date)、
  publication_year(year)、function_description(text)、cloning_method(255)、cloning_method_description(text)；仅主键索引。
- 现有值：author/author_mail 520 行全为 `Shengwei Ma / shengweima@icloud.com`；submission_date 全有值；function_description 空 7 行；
  paper_title 最长 8110、key_result 最长 15000（CGI 时代多值拼接，存在截断）；gene_species 自由文本（`Triticum aestivum` 244、`wheat` 164…）；
  **2 行 gene_id/gene_name 列错位**（clone_id 28/29：`TaBot1-4D`/`TraesCS4D02G326900`），迁移时需修正。
- **旧行 ID 版本**：gene_id 461 行 v02（02G）、10 行 v01、30 行 GenBank、2 行 HORVU、仅 1 行 v03 → 与新数据（v03 为主）直接匹配仅 7–10 行。
- 服务器变量：`sql_mode` 含 `STRICT_TRANS_TABLES`（超长即报错，不会静默截断）；`character_set_server=latin1`；
  `innodb_default_row_format=dynamic`；`innodb_large_prefix=1`；`max_allowed_packet=4MB`；目标表实测 `ROW_FORMAT=Dynamic`。
- 应用账号 `wheatomics_user`@localhost 对 `cloned_gene_db` 只有 SELECT/INSERT/UPDATE/DELETE/EXECUTE/SHOW VIEW，**无 DDL 权限**
  （root 在服务器 `/root/.my.cnf`，`sudo mysql` 免密仅 root；fei 的 sudo (ALL:ALL) 需密码，另有 `systemctl restart wheatomics-api` 的 NOPASSWD；
  应用账号对 `Genehub_DB.GenePageIWGSCv1_table` 有 SELECT）。
- 行大小硬约束：现表 utf8mb3 varchar 合计 55,135 B / 65,535 B；本方案加宽+加列后 60,691 B（余量 4,844 B）✅；
  **直接转 utf8mb4 = 73,490 B → ALTER 报 ERROR 1118** ❌（除非先改 `key_result` 为 TEXT，本轮不做）。
- 同库历史遗留表（上次替换尝试的证据）：`cloned_gene_temp` 1037 行（上一轮 staging）、`cloned_gene_tbl_backup_null` 575、
  `cloned_gene_tbl_subdate_backup_20261020` 575、**`cloned_gene_bad_import_backup` 1636 行**（坏导入残骸：`paper_title` 混入整行 TSV、`\r\n`、引号错位）。
  → **本次导入必须 JSONL + 参数化 SQL，禁止拼 TSV。**
- `/api/genes/known/all` 实测 520 行 97,894 B；新数据摘要若带长文本约 **1.10 MB**。仓库有 `GZipMiddleware(minimum_size=1000)`，
  直连 127.0.0.1:8000 与服务器本机 Apache 实测 gzip 生效（15.8 KB），但**公网 URL 实测未压缩**（可能被前置代理剥离 `Accept-Encoding`）
  → 不能依赖压缩，列表分页 + `/stats` 服务端聚合是必需项。

### 2.3 后端 API 现状（`app/api/routers/gene.py`，prefix `/genes`）

| 端点 | 行为 | 新数据下的问题 |
|---|---|---|
| `GET /known/search?searchid=` | 在 9 个字段上 `LIKE %term%` | 新字段搜不到；无字段过滤；**SQL 未 SELECT publication_year（现有 bug，返回恒 null）** |
| `GET /known/all` | 6 列摘要，520 条 97.9 KB | 1420 条约 270 KB（若带长文本 1.1 MB）；缺新摘要字段；无分页 |
| `GET /known/by-chromosome/{c}` | `chrom_pos LIKE 'c%'` | 新数据 `chrom_pos` 带 `Refv1.0 ` 前缀 → **全部失配**；非小麦标签也不支持 |
| `GET /known/{gene_id}` | 数字=clone_id，否则 gene_id/gene_name 精确匹配；references 由 `###` 拆分 | 新多值 `; ` 不识别；新字段缺失；`publication_years` 无法表达；`normalize_text` 破坏 `#` |
| 校验 | `ensure_gene_like`：`^[A-Za-z0-9_.:-]+$` | 新数据 1 个 gene_id（`Yr87/Lr85`）不通过 → 该行不能用 gene_id 作路径，但 UI 用 clone_id，可接受并文档化 |
| 文本归一化 | `legacy_parsers.normalize_text()`：`####`→`'`、`#`→`'` | **新数据 26 行含 `#` 会被破坏**；不能全局改（15+ 个库复用旧约定）→ known 端点内部按行判别 legacy，新数据原样返回 |
| 旧 CGI | `gene_search*.py`、`gene_submit*.py`、`gene_update.py` 直接读写该表 | 加列兼容；**`gene_search_by_id.py` 用 `SELECT *` + 位置下标 ele[0..11] → 新列只能追加在末尾**；不改旧列/列序 |

### 2.4 前端现状（`app/static/genes/`，FastAPI 挂载 `/genes`）

- `index.html`（556 行）：Search tab（Field 下拉**实际未生效**，永远全字段搜；结果卡片显示基因名/ID/染色体 badge/物种/表型/DOI 数；
  Export CSV 7 列）+ Stats tab（客户端 `GET /known/all` 聚合：总数、覆盖小麦染色体 21、物种数、表型数；染色体竖柱图 + Top15 表型横条图）。
- `detail.html`（395 行）：旧框架（`#home_header/#header-tabs/#home_footer`）；gene_name/ID、meta、4 张 meta 卡、5 个 section。
- 线上 `https://wheatomics.sdau.edu.cn/genes/` 200；`/api/genes/known/1` 正常；生产静态文件与仓库一致。
- 本机多宽度基线实测（ego-browser）：`/genes/` **PASS**；`/genes/detail.html?id=1` **FAIL**（footer 对比度 2.82:1、5 图无 alt）→ 本轮迁 `_v2` shell 顺带修复。
- 失效点：长 phenotype 撑爆卡片（1677 字符）、物种数虚高（296 原始值）、小麦 21 染色体统计错误（38 种标签）、
  DOI/年份多值、新字段无处展示、`/all` payload 变大、`/GeneHub/` 只对 `^TraesCS\d`/`^Traes_`（1291 行）可链。

### 2.5 部署与工作流

- 生产代码目录 `/var/www/FastAPI_backend_Port8000`（git HEAD `5364ca3` = 本地 HEAD）；systemd 单元 `wheatomics-api`（gunicorn，User=fei）；
  `sudo systemctl restart wheatomics-api` 无需密码；**重启后端口 8000 约需 2–3 分钟恢复监听**（MAINTENANCE.md）→ 需维护窗口。
- 部署 = `git pull` + 重启（static 文件 pull 即生效；Python 改动需重启；webhook 只 pull 不重启）。
- 本地无 `.env`（库仅 localhost），**本地开发服务器无法连生产库**；集成验证在生产节点进行（见 §6 上线顺序）。
- 规范：Bootstrap 4.5.3 + jQuery 1.9.1 本地资源、无 CDN；SPA 改动必须过 `bash scripts/spa_visual_check.sh` 多宽度渲染检查；
  标题规范 `KnownGene - WheatOmics`；`_v2` shell header/footer。

---

## 3. 目标设计

### 3.1 目标数据模型（DDL，root 一次性执行）

原则：**只追加列（不带 AFTER，保证 CGI `SELECT *` 位置下标不变）+ 加宽两列 + 索引**；**不删除/不改名/不重排旧列**；
字符集保持 **utf8mb3**（数据 0 个 4 字节字符；转 utf8mb4 行大小 73,490 B > 65,535 B 会失败）；`key_result` 保持 `varchar(15000)`。

```sql
-- 0) 逻辑备份（app 账号，SELECT 权限即可）：部署在服务器 /var/backups/
--    mysqldump --single-transaction --no-tablespaces --default-character-set=utf8mb4 \
--      cloned_gene_db cloned_gene_tbl > /var/backups/cloned_gene_tbl_pre_v2055_20261028.sql

-- 1) 结构变更（root）：加宽 2 列 + 追加 8 列 + 4 个前缀索引
ALTER TABLE cloned_gene_db.cloned_gene_tbl
  MODIFY COLUMN gene_phenotype VARCHAR(2000) DEFAULT NULL
    COMMENT 'Trait/phenotype free text; widened for v2055 (max 1677 chars)',
  MODIFY COLUMN gene_species VARCHAR(1000) DEFAULT NULL
    COMMENT 'Species free text incl. materials; widened for v2055 (max 668 chars)',
  ADD COLUMN reference_genome_id VARCHAR(100) DEFAULT NULL
    COMMENT 'v2055 col2: reference genome ID (IWGSC v3 03G / HORVU / GenBank); NULL = legacy row',
  ADD COLUMN protein_family TEXT
    COMMENT 'v2055 col9: protein family - function description (<=2657 chars)',
  ADD COLUMN validation_method TEXT
    COMMENT 'v2055 col12: semicolon-separated validation method tags; API splits to validation_methods[]',
  ADD COLUMN research_strategy VARCHAR(32) DEFAULT NULL
    COMMENT 'v2055 col13: Reverse genetics / Forward genetics / Not reported',
  ADD COLUMN functional_category VARCHAR(64) DEFAULT NULL
    COMMENT 'v2055 col14: one of 5 controlled categories',
  ADD COLUMN species_primary VARCHAR(64) DEFAULT NULL
    COMMENT 'Normalized NCBI binomial (23-value controlled map); stats/search dimension',
  ADD COLUMN publication_years VARCHAR(64) DEFAULT NULL
    COMMENT 'v2055 col17 multi-year raw values, "###"-joined (positional with paper_title/paper_doi)',
  ADD COLUMN chromosome VARCHAR(16) DEFAULT NULL
    COMMENT 'Normalized chromosome token parsed from chrom_pos (5A/3H/1R/54...); for by-chromosome/stats',
  ADD INDEX idx_kg_gene_id (gene_id(64)),
  ADD INDEX idx_kg_gene_name (gene_name(64)),
  ADD INDEX idx_kg_ref_id (reference_genome_id(64)),
  ADD INDEX idx_kg_chromosome (chromosome);
-- 备注：新列继承表默认 utf8；不建功能大类/研究策略索引（1420 行全表扫描 <10ms）。
-- 可选：data_version VARCHAR(16) DEFAULT NULL（批次溯源，data-profiler 建议；不影响 API）。

-- 2) 备份表 + staging 表（结构=变更后；内容=旧 520 行；新列 NULL）
CREATE TABLE cloned_gene_db.cloned_gene_tbl_backup_20261028 LIKE cloned_gene_db.cloned_gene_tbl;
INSERT INTO cloned_gene_db.cloned_gene_tbl_backup_20261028 SELECT * FROM cloned_gene_db.cloned_gene_tbl;
CREATE TABLE cloned_gene_db.cloned_gene_tbl_staging_20261028 LIKE cloned_gene_db.cloned_gene_tbl;

-- 3) 可选（若决策 Q3=A，保留旧链）：只读回退表，数据阶段只灌 199 个孤儿 clone_id
-- CREATE TABLE cloned_gene_db.cloned_gene_tbl_legacy LIKE cloned_gene_db.cloned_gene_tbl_backup_20261028;
```

- **`publication_year` 方案（已定）**：保持 `year(4)` = `min(该行全部年份)`（与 `backfill_publication_year.py` 旧语义一致；47 行多值非升序，不能取第一项）；
  新增 `publication_years` 存原始多值（`###` 连接，最长 18 字符）；旧 API/前端/脚本零改动，信息不丢。
- `author` / `author_mail` / `submission_date` 保持 NOT NULL：导入行写 `WheatOmics curation` / `shengweima@icloud.com` / 导入日（决策 Q15，可改）。
- 派生键 `genome_ref`（参考组装前缀，如 `Refv1.0`）与 `phenotype_brief`（性状简介）**不落库**，由 API 从 `chrom_pos`/`gene_phenotype` 派生，
  保证与 Stats 口径一致。
- 关于 `Refv1.0 坐标 + 03G ID`：**不是矛盾**——`Refv1.0` 是组装名（IWGSC RefSeq v1.0 assembly），`03G` 是同一组装上的 v2.1 注释 ID；
  已用 GeneHub API 抽查坐标一致（如 `TraesCS7A03G0370100` = chr7A:112,263,526–112,266,127 ↔ Excel 112.264–112.266 Mb）。

### 3.2 字段映射（Excel → DB → API → 前端）

| # | Excel 列 | 目标 DB 列（新增/复用） | API 字段 | 前端展示 |
|---|---|---|---|---|
| 1 | gene_id（入库） | `gene_id`（复用） | `gene_id` | 结果卡/详情标题下 ID（等宽字体） |
| 2 | 参考基因组ID（入库） | **`reference_genome_id`（新）** | 同名 | 详情 Overview 卡 + GeneHub 外链（仅 TraesCS/Traes_）；结果卡小字 |
| 3 | gene_name（入库） | `gene_name`（复用） | `gene_name` | 结果卡主标题（斜体）/详情标题 |
| 4 | 物种信息（入库） | `gene_species`（加宽）+ **`species_primary`（新）** | `species`（兼容）+ `species_primary` | 结果卡 `species_primary` badge；详情学名 + 材料长描述折叠 |
| 5 | chrom_pos（入库） | `chrom_pos`（复用）+ **`chromosome`（新）** | `chrom_pos` + `chromosome` + `genome_ref` | 结果卡染色体 badge；详情显示完整 chrom_pos |
| 6 | gene_phenotype（入库） | `gene_phenotype`（加宽） | `phenotype` + `phenotype_brief`（派生） | 结果卡 2 行截断 + Show more；详情 6 行 clamp |
| 7 | key_result（入库） | `key_result`（复用） | `key_result`（数组，兼容旧 `###` 拆分） | 详情 Key results（12 行 clamp） |
| 8 | function_description（入库） | `function_description`（复用） | 同名 | 详情 Function description（8 行 clamp） |
| 9 | 蛋白家族（入库） | **`protein_family`（新）** | 同名 | 详情 Overview 卡 + 段落（6 行 clamp）；家族头 chip |
| 10 | cloning_method（入库） | `cloning_method`（复用） | 同名（组合值拆分展示） | 详情 Cloning method chip |
| 11 | cloning_method_description（入库） | `cloning_method_description`（复用） | 同名 | 详情默认收起，Details 按钮 |
| 12 | 验证方法（入库） | **`validation_method`（新）** | `validation_method` + `validation_methods[]` | 详情 chips（≤12 + 折叠 +N） |
| 13 | 研究策略（入库） | **`research_strategy`（新）** | 同名 | 结果卡/详情 badge（3 值；Not reported 不渲染） |
| 14 | 功能大类（入库） | **`functional_category`（新）** | 同名 | 结果卡 badge（5 类配色）+ 筛选 + 统计图 |
| 15 | title（入库） | `paper_title`（复用，存 `###` 拼接原文） | `references[].title` + `paper_title[]`（兼容） | 详情 References（题名 + DOI + 年份逐一对应） |
| 16 | doi（入库） | `paper_doi`（复用，存 `###` 拼接原文） | `references[].doi`（允许 null）+ `dois[]`（兼容） | 详情 DOI 链接；结果卡 DOI 数 |
| 17 | publication_year（入库） | `publication_year`（year，最早年）+ **`publication_years`（新，原文 `###`）** | `publication_year` + `publication_years[]` | 详情 References 年 + meta 卡（多值 `2008, 2024`） |

**导入期转换规则**：
1. `; ` 拆分 → title/doi/year 各自拆分后按位置配对（不补空位，API 按 max 长度对齐，缺失补 null）；16 行异常不丢弃、报告列出；
2. 只按 `"; "` 拆，题名内合法 `;`（13 行）不受影响；
3. `species_primary`：规则 + 23 值别名表兜底（0 未命中目标）；原文保留在 `gene_species`；
4. `chromosome`：正则 `chr\s*([0-9]+[A-Za-z]{0,2})`；`chr51/chr54` 原样；2 行无 `chr` 前缀 fallback（Excel 297/711）；
5. 不做 HTML 清洗（无真实标签）；**不做 `#`→`'` 替换**（保留原始 `#`）；
6. 新数据无 author → 写占位（见 §3.1）；`submission_date` = 导入日；
7. 多值字段 DB 存原文（`###` 连接），API 负责拆分；JSONL 序列化规避引号/制表符。

### 3.3 API 契约（向后兼容扩展）

原则：旧字段名/语义保留；新字段用新名字；数字 ID 仍为 clone_id；**`/known/stats` 必须注册在 `/known/{gene_id}` 之前**（否则 404）。

1. `GET /api/genes/known/all`
   - 保持 6 字段，**新增**：`reference_genome_id`、`species_primary`、`chromosome`、`genome_ref`、`phenotype_brief`、
     `functional_category`、`research_strategy`；
   - **新增可选 `limit`/`offset`**（默认全量，旧行为不变；前端 50/页）；不返回长文本字段（payload ~350 KB）。
2. `GET /api/genes/known/search?searchid=&field=`
   - `field` 白名单：`all`(默认，旧 9 列 + 6 新列) | `gene_id` | `gene_name` | `reference_genome_id` | `phenotype` | `species` |
     `doi` | `protein_family` | `functional_category` | `chrom_pos`；未知值 400；LIKE 转义 `%`/`_`；
   - 返回同 `/all` 摘要 + `dois[]` + `publication_years[]`；支持 `limit/offset`；**补 SELECT `publication_year`（修旧 bug）**。
3. `GET /api/genes/known/by-chromosome/{chromosome}`
   - `normalize_chromosome()`（去 `chr`/大小写/`^[0-9]{1,2}[A-Z]{0,2}$`）→ `WHERE chromosome=%s OR (chromosome IS NULL AND chrom_pos REGEXP %s)`；
     非法输入 400；返回同 `/all`。
4. `GET /api/genes/known/{gene_id}`（数字=clone_id；否则 gene_id/gene_name 精确匹配）
   - 详情**新增**：`reference_genome_id`、`species_primary`、`chromosome`、`genome_ref`、`phenotype_brief`、`protein_family`、
     `validation_method`、`validation_methods[]`、`research_strategy`、`functional_category`、`publication_years[]`；
   - `references[]` 每项 `{doi, title, year}`（按位置配对，缺失 null；1 行 3 DOI/4 题名时第 4 条只有题名、doi=null）；
   - `key_result` 旧数组语义保留（`###` 拆分；新数据单段返回 1 元素）；
   - 修复：known 端点改用不替换 `#` 的新归一化（按 `reference_genome_id IS NULL` 区分 legacy）；
   - 可选（Q3=A）：数字路径主表未命中时回退 `cloned_gene_tbl_legacy`，返回 `deprecated: true`。
5. **新增** `GET /api/genes/known/stats`（响应结构与 frontend_change_spec.md §5.1 对齐）
   ```json
   {"total": 1420,
    "species": [{"name": "Triticum aestivum", "count": 1260, "raw_forms": 42}, ...],
    "species_raw_count": 296,
    "chromosomes": [{"label": "1A", "count": 55, "group": "wheat"}, ..., {"label": "3H", "count": 16, "group": "other"}],
    "functional_category": [{"name": "Biotic & Abiotic Stress", "count": 776}, ...],
    "research_strategy": [{"name": "Reverse genetics", "count": 1061}, ...],
    "phenotype_tags": [{"tag": "not determined", "count": 65}, ...],
    "publication_year": [{"year": 2022, "count": 254}, ...],
    "references": {"entries": 1570, "unique_dois": 883},
    "notes": {"multi_year_rows": 115, "multi_species_rows": 263}}
   ```
   SQL：`COUNT/GROUP BY`（species_primary/functional_category/research_strategy/chromosome）；
   phenotype 标签、年份（多值按年重复计数，合计 1555）、references 计数在 Python 侧聚合（1420 行 <1 MB，可加进程内 TTL 缓存）。
6. 错误/空态保持现有 `ok()` 信封与 `ResourceNotFound`；OpenAPI docstring 同步。

### 3.4 前端信息架构（详见 frontend_change_spec.md）

**列表页 `/genes/`**
- Search：关键词 + **Field 下拉真正生效**（对接 `field`）+ 分页（50/页，`Showing 1–50 of 1,420`）+ 可选筛选
  （功能大类 5 值 / 研究策略 3 值 / 物种 Top N；Phase 1 客户端过滤）；
- 结果卡片：`gene_name`（斜体）+ `gene_id` + `chromosome` badge + `species_primary` + `functional_category` badge +
  `research_strategy` badge + `phenotype_brief`（2 行 clamp + Show more，全文保留 DOM）+ DOI 数；
- Export CSV：**19 列**（gene_id/name、reference_genome_id、chromosome、chrom_pos、genome_ref、species 归一化+原文、
  functional_category、research_strategy、phenotype 全文、protein_family、validation_methods、cloning_method、key_result、
  function_description、publication_years、DOIs、detail URL）+ UTF-8 BOM + **防 Excel 公式注入**；导出「筛选后全部结果」；
- Stats tab：改用 `/known/stats`，**6 KPI + 7 组图**：总量 / 归一化物种数 / 小麦 21 条 / 5 功能大类 / 3 研究策略 / 引用与 DOI；
  物种 Top15+Other、功能大类、研究策略、**小麦 21 条 vbar + 其他 17 种染色体 bar-row**、表型标签 Top20、年份 1998–2026；
- 抽公共 JS `app/static/genes/known_gene_common.js`（`/genes` 挂载自动可访问，无需改 main.py）。

**详情页 `/genes/detail.html`**（URL 不变：`?id=<clone_id>`）
- 迁 `_v2` shell（删旧 header/footer/重复 visit 脚本，修复视觉基线 FAIL）；
- Overview：基因名/ID、参考基因组ID（`^TraesCS\d`/`^Traes_` 1291 行链 `/GeneHub/?search=`，其余 129 行纯文本）、
  物种（学名 + 材料说明折叠）、染色体 + 参考组装前缀、表型简介、功能大类/研究策略徽章；
- 新 section：Protein family、Validation methods（chips ≤12 + 折叠）、Phenotype（6 行 clamp）、References（题名+DOI+年份，
  缺失年份 `—`）、Publication years；保留 Key results / Function description / Cloning method / Submitted by（空则隐藏）。
- 长文本统一 clamp + Show more；字段 `esc()`；响应式 360–1440 无横向溢出。

### 3.5 clone_id 稳定映射（保外链）

旧详情页 URL `/genes/detail.html?id=<clone_id>`。旧库 ID 为 v02/v01、新数据为 v03，直接匹配仅 7–10 行；用 ID 映射可大幅提升：

1. 读旧表 `(clone_id, gene_id, gene_name)`（含 2 行列错位需人工修正）；
2. 用 `Genehub_DB.GenePageIWGSCv1_table`（应用账号可读）把旧 v1/v2 映射到 v3（475/520 有映射）；
3. 第一轮：旧 gene_id 或映射 v3 == 新 `reference_genome_id` → 继承 clone_id；
4. 第二轮：归一化 `gene_name` 相同 → 继承剩余；
5. 未匹配新行：按 Excel 行序分配 `max(旧 clone_id)+1` 起；
6. 旧行未匹配：clone_id 不复用；
7. **生产实测结果**：继承 **321/520（62%）**；新行 **1099** 个 → clone_id **527…1625**；导入后 `AUTO_INCREMENT=1626`；孤儿旧 ID **199** 个。

> 旧 URL 兜底（决策 Q3）：
> **A（推荐，+0.5–1 h）**：root 建只读 `cloned_gene_tbl_legacy LIKE backup`，数据阶段只灌 199 个孤儿行；`/known/{id}` 主表未命中时回退查询并返回
> `deprecated: true`，详情页显示「该记录已被新版取代」横幅 → **旧链接 100% 可用**；新表内容仍严格 = 1420 行（legacy 不参与搜索/统计）。
> **B（零成本）**：接受 199 条旧链 404，发布说明写明。

---

## 4. 实施计划（阶段 / 任务 / 工时 / 闸门）

> 估算按 1 名熟悉仓库的工程师；含自测，不含用户评审等待。**最小可用 ≈16 h（2 人日）；推荐完整 ≈37–40 h（≈5 人日）**；
> 前端 24 h 与后端 5 h 可并行（2 人 → 3–4 个日历日）。

### Phase 0 — 冻结与备份（0.5 h）

- [ ] 用户确认 v2055 为最终版（当天 v2026–v2055 持续迭代），记录 md5 并把快照复制到 `docs/known_genes/_evidence/`；
- [ ] 确认 §8 决策 Q1–Q8；
- [ ] 建分支 `feat/known-genes-v2055`；生产表备份（root 建备份表 + mysqldump 逻辑备份）；
- [ ] 记录上线前基线：`/known/all` 快照、页面截图（桌面 + 移动）。
- **闸门 G0**：备份存在且可读，基线存档完成。

### Phase 1 — 数据抽取与校验（4 h）

- [ ] `scripts/known_genes_v2055/extract.py`：xlsx → `known_genes_v2055.jsonl`（DB 列名 + `_row`/`_warn`），JSON 序列化；
  多值 `; `→`###` 与位置配对；物种归一化（23 值映射表）；染色体解析；`publication_year=min()`；clone_id 映射（含 v3 转换）；
- [ ] 产出人工可读报告：`validation_report.md/json`、`clone_id_mapping.csv`、`unmatched_old.csv`、`unmatched_new.csv`；
  16 行多值异常、2 行错位列、2 行无 chr 前缀、26 行 `#` 复核清单；
- [ ] clone_id 映射人工抽检（gene_id→v3 映射条目 tier/来源 CSV）。
- **闸门 G1**：0 个 fatal 错误；warning 清单人工过目；映射报告确认（321/520 口径）。

### Phase 2 — DDL + 导入脚本（3 h）

- [ ] `scripts/sql/known_genes_v2055_ddl.sql`（§3.1）+ `scripts/migrate_known_genes_v2055.py`
  （`--phase prepare|ddl|data|verify|rollback`，`--dry-run/--commit/--staging/--target`；data 阶段应用账号）；
- [ ] 导入：JSONL → staging（应用账号）→ 校验 → 单事务 `DELETE FROM cloned_gene_tbl` + `INSERT ... SELECT FROM staging`（禁止 TRUNCATE）；
- [ ] 失败自动回滚；可选 legacy 表灌入（Q3=A）；
- [ ] 服务器上建 drill 表演练 `prepare→data→verify→rollback`（行数 520→1420→520）。
- **闸门 G2**：演练通过；dry-run 报告与 Excel 全表一致。

### Phase 3 — 后端 API（5 h）

- [ ] `app/schemas/gene.py` 扩展（新增字段，旧字段不动）；`app/services/legacy_parsers.py` 增新归一化（不改旧函数行为）；
- [ ] `app/api/routers/gene.py`：4 个旧端点扩展（field/limit/offset、多值拆分、chromosome/genome_ref 派生、修 2 bug）+ `/stats`（注册在 `{gene_id}` 之前）；
- [ ] OpenAPI docstring 更新；自测：1420 个 gene_id 过校验（记录唯一 1 个不可路由）、空结果/404 行为不变；
- **闸门 G3**：curl 冒烟全绿（旧响应字段不缺失、新字段正确、`/stats` 与 Excel 对账）。

### Phase 4 — 前端改造（24 h；最小可用版 6–8 h）

- [ ] `known_gene_common.js`：0.5 h
- [ ] `detail.html` 迁 `_v2` shell + 新 section + 长文本/References/空值：7 h
- [ ] `index.html` Search（field/分页/卡片/筛选/导出 CSV 19 列）：7.5 h
- [ ] `index.html` Stats（6 KPI + 7 图，对接 `/stats`）：5 h
- [ ] 响应式/对比度/XSS/视觉检查与修复：4 h
- **闸门 G4**：`bash scripts/spa_visual_check.sh` 通过；页面功能自测清单全过。

### Phase 5 — 联调、上线、回归（3 h）

- [ ] 上线窗口 T0（10–15 min，低峰期）：P0 备份 → P1 root DDL → P2 部署后端（重启，等 8000 恢复）→ P3 导入 + 校验 →
  P4 部署前端（static 即生效）→ P5 观察 30 min（`journalctl -u wheatomics-api -f`、`/all` 大小/耗时、错误率）；
- [ ] 回归：`/api/genes/known/*` 全端点（含异常路径）、旧 CGI 页面、GeneHub 链接、首页 KnownGene 卡；
- [ ] 公网目视 + `spa_visual_check`（生产 URL）；
- **闸门 G5**：验收清单全过；否则按 §6 回滚。

### Phase 6 — 收尾（1 h）

- [ ] 更新 `MAINTENANCE.md`（新增「KnownGene 数据更新流程」一节：xlsx→extract→validate→migrate→verify）与 `CLAUDE.md`（如需）；
- [ ] 保留 `cloned_gene_tbl_backup_20261028` 及 mysqldump；temp/staging/backup_null 等清理另立项（Q9）；
- [ ] 用户验收；如需 News 公告（生产 `/var/www/html/V2.0/news.json`，不在本仓库）。

---

## 5. 验证与验收

### 5.1 数据/SQL 校验（导入后必须全绿）

```sql
-- 行数 / 主键
SELECT COUNT(*) FROM cloned_gene_db.cloned_gene_tbl;                          -- =1420
SELECT COUNT(DISTINCT clone_id) FROM cloned_gene_db.cloned_gene_tbl;         -- =1420
SELECT MAX(clone_id) FROM cloned_gene_db.cloned_gene_tbl;                    -- =1625（321 继承 + 1099 新）
SELECT AUTO_INCREMENT FROM information_schema.TABLES
 WHERE TABLE_SCHEMA='cloned_gene_db' AND TABLE_NAME='cloned_gene_tbl';       -- =1626
-- 必填
SELECT SUM(reference_genome_id IS NULL OR reference_genome_id=''),           -- 0
       SUM(species_primary IS NULL OR species_primary=''),                   -- 0
       SUM(chromosome IS NULL OR chromosome=''),                             -- 0
       SUM(functional_category IS NULL OR functional_category=''),           -- 0
       SUM(research_strategy IS NULL OR research_strategy=''),               -- 0
       SUM(gene_id IS NULL OR gene_id='') FROM cloned_gene_db.cloned_gene_tbl;
-- 长度边界（抽取期已校验；再造一个 staging 表用 STRICT 模式实插一次最稳）
SELECT MAX(CHAR_LENGTH(gene_phenotype)), MAX(CHAR_LENGTH(gene_species)),
       MAX(CHAR_LENGTH(key_result)), MAX(CHAR_LENGTH(protein_family)) FROM cloned_gene_db.cloned_gene_tbl;
-- 分布对账
SELECT species_primary, COUNT(*) FROM cloned_gene_db.cloned_gene_tbl GROUP BY 1 ORDER BY 2 DESC;   -- 23 组
SELECT chromosome, COUNT(*) FROM cloned_gene_db.cloned_gene_tbl GROUP BY 1 ORDER BY 2 DESC;         -- 38 标签
SELECT functional_category, COUNT(*) FROM cloned_gene_db.cloned_gene_tbl GROUP BY 1;                -- 5 行
SELECT research_strategy, COUNT(*) FROM cloned_gene_db.cloned_gene_tbl GROUP BY 1;                  -- 3 行
-- clone_id 映射
SELECT COUNT(*) FROM cloned_gene_db.cloned_gene_tbl_backup_20261028 b
  JOIN cloned_gene_db.cloned_gene_tbl n USING (clone_id);                    -- =321
-- 多值 / `#` 保留
SELECT clone_id, gene_name, paper_doi, publication_year, publication_years
  FROM cloned_gene_db.cloned_gene_tbl WHERE paper_doi LIKE '%###%' LIMIT 5;
SELECT COUNT(*) FROM cloned_gene_db.cloned_gene_tbl
 WHERE key_result LIKE '%#%' OR gene_phenotype LIKE '%#%';                    -- >0（确认 # 未被改成 '）
```

### 5.2 API 冒烟

```bash
curl -s "$HOST/api/genes/known/all" | jq '.data.total'                          # 1420
curl -s "$HOST/api/genes/known/all?limit=50&offset=0" | jq '.data.records|length' # 50
curl -s "$HOST/api/genes/known/all" | jq '.data.records[0]'                     # 含 7 新键
curl -s "$HOST/api/genes/known/search?searchid=VRN1" | jq '.data.total'         # >0
curl -s "$HOST/api/genes/known/search?searchid=Drought&field=phenotype" | jq '.data.total'
curl -s "$HOST/api/genes/known/search?searchid=10.1093/jxb/erm369&field=doi" | jq '.data.total'
curl -s "$HOST/api/genes/known/search?searchid=x&field=BAD" -o /dev/null -w '%{http_code}\n'  # 400
curl -s "$HOST/api/genes/known/by-chromosome/3h" | jq '.data.total'             # 大麦，大小写兼容
curl -s "$HOST/api/genes/known/1" | jq '.data.reference_genome_id,.data.species_primary'
curl -s "$HOST/api/genes/known/527" | jq '.data.gene_name'                     # 新行
curl -s "$HOST/api/genes/known/stats" | jq '.data.total,.data.species[0],.data.references'
curl -s "$HOST/api/genes/known/stats" -o /dev/null -w '%{http_code}\n'          # 200（不能 404/422）
curl -s -o /dev/null -w '%{http_code}\n' "$HOST/api/genes/known/999999"         # 404
```

### 5.3 页面/回归验收

- `/genes/`：搜索（含 Field 切换）、分页、筛选、空态、CSV 导出（19 列、UTF-8 BOM、无公式注入）、
  Stats 与 `/stats` 数值一致（验收数值：total 1420 / 物种 23 / 染色体 38 条 / 功能大类 776+202+154+146+142 /
  研究策略 1061+281+78 / references 1570·883 DOI / 年份 1998–2026 合计 1555）；
- `/genes/detail.html?id=<继承的旧 clone_id>`：数据正确、新 section 齐全、长文本可展开、References 多条按序；
- 旧 CGI：`/cgi-bin/gene_search.py?...`、`/cgi-bin/gene_search_by_id.py?...` 页面 200、数据可显示（新列不参与，旧列有值）；
- 首页 `/V2.0/` KnownGene 卡片入口可用；`/api/genes/detail/{TraesCS...}`（GeneHub）正常；
- 多宽度渲染（360/768/1024/1440）无横向溢出 + 无对比度 FAIL；控制台无 JS 报错。

---

## 6. 上线与回滚

### 上线顺序（P0–P5，见 §4 Phase 5）

```
P0 备份（mysqldump + 记录 COUNT/MAX/AUTO_INCREMENT + /all 快照）
P1 root: DDL（ALTER + backup + staging [+ legacy]）
P2 部署后端代码（git pull → restart → 等 8000 恢复 → 旧数据下冒烟）
P3 应用账号: 导入（staging 校验 → 单事务替换 → verify → API/页面冒烟）
P4 部署前端（git pull，static 即生效）
P5 观察 30 min + 验收
```
> 为什么代码先于数据：DDL 纯追加对旧代码零影响；新代码对旧数据做了防御（新列 NULL、`publication_years` 回退、
> `chromosome` fallback），任何时刻用户看到的都是自洽的一侧；前端最后上（依赖 `/stats` 与新字段）。

### 回滚

| 场景 | 回滚动作 | 恢复时间 |
|---|---|---|
| 导入失败/校验不过 | 脚本异常自动 `ROLLBACK`；或 `DELETE FROM cloned_gene_tbl; INSERT ... SELECT ... FROM cloned_gene_tbl_backup_20261028;` | <5 min |
| 上线后后端/前端异常 | `git revert` / 回退到旧 commit → `git pull` → 重启（旧代码+旧数据兼容） | 10–15 min（含重启等待） |
| DDL 后想完全回退 | root：`DROP TABLE cloned_gene_tbl; RENAME TABLE cloned_gene_tbl_backup_20261028 TO cloned_gene_tbl;`（+ mysqldump 兜底） | <10 min |
| 数据错误（部分行） | 修正 Excel → 重跑 `extract → validate → data --commit`（脚本幂等） | ~15 min |

---

## 7. 风险与缓解

| # | 风险 | 概率/影响 | 缓解 |
|---|---|---|---|
| R1 | **v2055 未冻结**（当天 v2026→v2055 快速迭代） | 高/高 | Phase 0 冻结快照 + md5；导入文件从快照生成 |
| R2 | 多值拆分歧义（16 行数量异常、13 行题名含合法分号） | 中/中 | 位置配对 + 缺失补 null；报告列异常；前端容错显示 `—`；建议先修 Excel（Q13） |
| R3 | 物种长描述/混杂（296 值、60 行超长） | 高/中 | 23 值归一化映射 + 人工兜底；原文保留；统计用 `species_primary` |
| R4 | STRICT 模式下超长报错（phenotype 99 行 >1000、species 60 行 >500） | 高/高 | DDL 先加宽（2000/1000）；抽取期逐列长度校验 fatal 阻断 |
| R5 | clone_id 变化导致旧链接 404（映射后仍 199 条孤儿） | 中/中 | v3 映射保留 62%；可选 legacy 回退表实现 100%（Q3） |
| R6 | **历史坏导入重演**（1636 行残骸仍在库中） | 中/高 | JSONL + 参数化 INSERT；禁止 TSV；staging/事务/备份/校验四道闸 |
| R7 | 生产 DDL 权限（应用账号无 DDL、sudo 需密码） | 确定/低 | 两段式：root 执行 ddl.sql，数据阶段应用账号；DDL 前备份 |
| R8 | `#` 被 `normalize_text()` 改写（26 行） | 中/中 | known 端点按行判别 legacy，新数据原样；验收 SQL 检查 |
| R9 | 前端长文本撑爆布局 / `<` 数学符号被误清洗 | 中/中 | clamp + Show more；不 strip 标签、只 `esc()`；多宽度视觉检查 |
| R10 | 旧 CGI 位置下标读列（`SELECT *` + ele[0..11]） | 中/高 | **新列只追加在末尾、不改列序**；CGI 回归 |
| R11 | `/all` 全量 1.1 MB 拖慢首屏（公网实测未 gzip） | 中/低 | 默认分页 50/页 + `/stats` 服务端聚合；核查链路上 `Accept-Encoding` |
| R12 | detail.html 迁 `_v2` shell 范围扩大（视觉基线 FAIL） | 中/中 | 单独 FE 任务（7 h）；如时间紧可先内容+最小样式，shell 迁移另列（Q11） |
| R13 | 重启后 8000 端口 2–3 分钟不可用 | 确定/低 | 低峰期窗口；公告/维护页可选；回滚同样需等待 |
| R14 | `Refv1.0`/03G 版本标签被误解为数据错误 | 低/低 | 已核实为「组装名 vs 注释 ID」；详情页显示 `genome_ref` 说明 |

---

## 7.5 决策已确认（2026-10-28）

用户已确认：① **v2055 冻结锁定** → 先修 16 行多值异常生成 **v2056**（Crossref 核实，16 行/19 单元格，见
`docs/known_genes/multi_value_fixes_v2056.md`），v2056 为导入源；② **全量替换**（新表 = 1420 行）；
③ 旧 URL **只保留映射成功的 321 个 clone_id，使用内部 ID**，199 个未映射旧 ID 不复用、**不建 legacy 回退表**；
④ **5 个新字段全部展示**；⑤ detail 页**本轮迁 `_v2` shell**；⑥ 上线后**更新生产 News 公告**。
冻结快照/md5/映射口径见 `docs/known_genes/FREEZE_v2055.md`。实施以该文件为准，§8 保留作背景。

---

## 7.6 实施状态：已完成上线（2026-10-28）

| 项 | 结果 |
|---|---|
| 冻结 | v2055 md5 `85f3e6207bba347fb1d7dcddda881cd6`；修正版 v2056 md5 `1dbbeff77f8f53eb33e8ea133d32cb65`（16 行多值修正，见 `multi_value_fixes_v2056.md`） |
| 数据管线 | `extract.py` → JSONL 1420 行（md5 `33e7f288…`，fatal 0 / 多值异常 0 / 23 物种 / 38 染色体 / 1570 引用·883 DOI） |
| 生产 DDL | ✅ 24 列 / 备份表 520 / staging 0 / 4 索引（root，`scripts/sql/known_genes_v2055_ddl.sql`） |
| 生产数据替换 | ✅ 1420 行 / distinct clone_id 1420 / max 1625 / 继承旧 id 321 / 23 物种 / 38 染色体 / 5 大类 / 3 策略；verify PASS |
| 后端 | ✅ commit `14aa700`（4 端点兼容扩展 + `/stats` + 两处旧 bug）；smoke S1–S13 全绿 |
| 前端 | ✅ commit `516de39`（index/detail/common.js 重构 + `_v2` shell + 19 列 CSV + 6 KPI/7 图）；生产视觉检查 index/stats 360–1920、search/detail 390–1440 全部 PASS |
| News | ✅ 生产 `/var/www/html/V2.0/news.json` 首位 2026-10-28 公告（备份 `.bak-20261028_known_gene`） |
| 回滚 | 数据 `--phase rollback --commit`；备份表 `cloned_gene_tbl_backup_20261028` + `/home/fei/backup/*`；代码 revert；News 恢复备份 |
| 记录 | `docs/known_genes/DEPLOYMENT_v2056.md`、`ROLLOUT_v2056.md`、`FREEZE_v2055.md`；维护流程写入 `MAINTENANCE.md` §十三 |

**备注**：旧 199 个未映射 `clone_id` 的详情链接按决策 Q3 不再保留（不建 legacy 表）；前端 CSV 全量导出对长文本列走逐行详情富化（1420 行约 10–30 s，后续可加批量端点优化）。

---

## 8. 待你确认的决策

> 注：以下决策已于 2026-10-28 确认，见 §7.5 与 `docs/known_genes/FREEZE_v2055.md`。

| # | 问题 | 建议/默认 |
|---|---|---|
| Q1 | **v2055 是否已冻结为最终版？** 同一天还有 v2026–v2055 多个版本，Excel 可能继续改 | 冻结并给出 md5；之后改动走"重跑导入"（幂等） |
| Q2 | **替换策略**：全量替换（删除旧 520 行中不在新表的 199 条记录）？还是软保留（1668 行 + `is_active` 过滤）？ | 全量替换（用户原话"替换"）+ 备份；软保留需改 4 个 API + CGI，本期不值 |
| Q3 | **旧详情页 URL**：只做 clone_id 继承（62% 保留、199 条 404）？还是加 legacy 只读回退表做到 100% 可用？ | 建议 legacy 回退（+0.5–1 h，旧表仅 199 行，不参与搜索/统计） |
| Q4 | **5 个新字段是否全部前端展示？**（参考基因组ID/蛋白家族/验证方法/研究策略/功能大类） | 建议全部展示；"研究策略/验证方法"如属内部质控可仅详情页显示 |
| Q5 | **物种展示口径**：只显示学名（23 值），还是学名+英文常用名？材料长描述是否折叠？ | 卡片学名 badge；详情学名+英文名，材料说明折叠 |
| Q6 | **旧 CGI 提交页是否继续维护？**（只写旧列；新数据 author 为占位） | 保留不破坏；详情页隐藏空 Submitted by |
| Q7 | **`/all` 加 `limit/offset` + 新增 `/stats`**（均向后兼容）？ | 建议做（否则前端 1.1 MB 全量拉取） |
| Q8 | **上线窗口与公告**：避开高峰？是否发 News/首页公告？ | 低峰期；公告需另改生产 `/var/www/html/V2.0/news.json` |
| Q9 | **是否顺带清理历史遗留表**（temp 1037 / bad_import 1636 / backup_null 575 / subdate_backup 575）？ | 本次不动；稳定 1–2 周后另立项（需 root） |
| Q10 | **API 文档/README/MAINTENANCE 是否同步更新？** | 建议同步（新增「KnownGene 数据更新流程」一节） |
| Q11 | **detail.html 是否本轮迁 `_v2` shell？**（+3–4 h，顺带修视觉基线 FAIL） | 建议本轮迁；或内容先上、shell 下轮 |
| Q12 | **title 用 `KnownGene - WheatOmics` 还是现页面的 `KnownGene | WheatOmics 2.0`？** | 建议按 MAINTENANCE `KnownGene - WheatOmics` |
| Q13 | **16 行多值异常是否先在 Excel 修正？**（12 行缺年份、3 行缺题名、1 行题名重复） | 建议作者修 Excel；同时 importer 保留容错规则（不阻塞上线） |
| Q14 | **`Thinopyrum ponticum` 的 `chr51/chr54` 是什么染色体？**（5E/5J?） | 原样展示/按 `chr51`、`chr54` 入库；请作者确认是否映射 |
| Q15 | **新行 author/author_mail/submission_date 占位值？**（列 NOT NULL） | 建议 `WheatOmics curation` / `shengweima@icloud.com` / 导入日；或空串+NULL（详情页隐藏） |

---

## 9. 附录：关键文件与证据

| 内容 | 路径 |
|---|---|
| 共享调查事实基线 | `docs/known_genes/CONTEXT.md` |
| 新数据逐列剖析与字段映射 | `docs/known_genes/data_profile_v2055.md` |
| 后端/DB 迁移设计（完整 DDL/脚本/API/验证 SQL） | `docs/known_genes/backend_investigation.md` |
| 前端展示改造方案 | `docs/known_genes/frontend_change_spec.md` |
| 线上旧数据快照（520 条摘要） | `docs/known_genes/_evidence/current_api_known_all.json` |
| 后端路由/模型 | `app/api/routers/gene.py`、`app/schemas/gene.py`、`app/core/security.py`、`app/services/legacy_parsers.py` |
| 前端页面 | `app/static/genes/index.html`、`app/static/genes/detail.html` |
| 旧 CGI 兼容参考 | `cgi-py-RawScript/gene_search*.py`、`gene_submit*.py`、`gene_update.py` |
| 历史导入脚本（参考） | `scripts/import_cloned_genes.py`、`scripts/backfill_publication_year.py` |
| 生产部署 | systemd `wheatomics-api`（`/var/www/FastAPI_backend_Port8000`） |

**生产只读调查留痕**：MySQL 5.7.33；`cloned_gene_tbl` 520 行 / AUTO_INCREMENT=527 / utf8_general_ci / DATA_LENGTH≈3.67MB；
`SHOW GRANTS` 确认应用账号无 DDL；`sql_mode` 含 STRICT_TRANS_TABLES；`SHOW COLUMNS LIKE 'pmid'` 为空；
旧行 ID 461 v02 / 10 v01；v1/v2→v3 映射 475/520；clone_id 继承实测 321/520（新 id 527–1625，AUTO_INCREMENT 1626）；
线上 `/api/genes/known/all` 97,894 B（公网未压缩；直连后端 gzip 15.8 KB）。
