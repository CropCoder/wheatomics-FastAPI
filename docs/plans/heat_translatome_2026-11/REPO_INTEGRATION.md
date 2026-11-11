# 中国春籽粒热胁迫翻译组数据上架 — 仓库侧集成审计

> 数据：中国春小麦发育籽粒 5 / 10 / 15 DAA，正常（CK）vs 热胁迫 1 h（HS）的
> RNA-seq FPKM、Ribo-seq FPKM、翻译效率 TE（TE = Ribo/RNA）
> 审计日期：2026-11-11 ｜ 审计对象：`FastAPI_backend_Port8000` 仓库（只读）＋线上 API（只读 GET）
> 约束：**本次审计未修改 `app/`、`main.py`、任何数据库**；本文件是唯一写入物。
> 生产写库/重启服务需要马老师或运维账号在服务器上执行，本审计只在仓库侧给方案与脚本。

---

## 0. 结论先行

| 问题 | 结论 |
|---|---|
| 能不能直接塞进现有 expression 模块？ | **能，但必须先解决单位措辞**：模块把 y 轴、tooltip 硬编码成 `TPM`（5 处，`app/static/expression/index.html:83,86,631,675,840`），而本数据是 **FPKM + TE**。零代码硬塞会让 FPKM/TE 在页面上被标成 TPM（科研口径错误）。 |
| 一个项目是什么表？ | 一张「宽表」：`GeneID`（文本）+ N 个数值列（每个样本一列，`DOUBLE`），**没有 unit、没有必需主键、没有 `_std` 也能跑**；`project_meta` 一行描述它，`labels` 数组与数值列**按位置配对**。 |
| 基因 ID 用哪个版本？ | 现有 334 个项目的表都是 **02G（IWGSC RefSeq v2.1）**。API 会把用户输入的 01G/03G 自动转成 02G 再查（`app/api/routers/expression.py:129-173`），线上实测 `TraesCS5A03G0935400 → TraesCS5A02G391700`。**新表必须以 02G 为键**，否则现有查询链路查不到。 |
| 前端吃不吃得下 18 列？ | 18 个点非常轻松（15 点基线项目 `PRJEB5314_paired_tbl` 就是常态；10–20 点自动 10px 字号，`index.html:551-559`）。真正的可读性阈值在 **约 40–70 个标签**之后（审计实测 70/81 标签重叠、638 标签成黑带），18 完全不是问题。**但前端没有「按 RNA/Ribo/TE 分组」能力**，18 列只能平铺成一条 x 轴。 |
| 推荐怎么做？ | **方案 B（推荐）**：3 张 6 列表（RNA/Ribo/TE 各一）+ 3 行 `project_meta` + `project_meta.unit` 字段（DDL）＋前端 5 处绑定 unit。约 **1.5–2 人日**（含数据映射与验收）。见 §6。 |
| 上线数据迁移怎么做？ | 生产 `project_meta` **是手工维护的**：仓库 `init_project_meta.sql` 只有 69 行（2026-06-23 提交后没再更新，`init_project_meta.sql:27-29`），线上 334 行只存在于生产库；历史改动都是「一次性 Python 脚本 + 备份表 + dry-run/apply/rollback」手工跑（见 §2.2 与 §2.5）。本数据沿用同一模式即可，**只需 DDL + INSERT，不需要重启 API**（`/projects` 和 `/query` 每次都现查 `project_meta`）。 |

---

## 1. 审计范围、方法与证据

### 1.1 读了什么（只读）

| 面 | 文件/对象 |
|---|---|
| 路由/服务/Schema | `app/api/routers/expression.py`（278 行）、`app/services/expression_catalog.py`（155 行）、`app/schemas/expression.py`（32 行） |
| 数据库定义 | 仓库 `init_project_meta.sql`（69 行旧快照）、线上 `project_meta` 备份（`wheatomics_results/audit/project_meta_backup_20260806.sql` 512 行、`wheatomics_results/audit/fix_verification/project_meta_bak_20261028_b.sql` 332 行） |
| 前端 | `app/static/expression/index.html`（932 行）、`app/static/docpages/gene.html`（567 行）、`app/static/docpages/geneDetail.py`（312 行）、`app/static/genes/detail.html` |
| 挂载/部署 | `main.py:194-225`（SPA mounts）、`MAINTENANCE.md` §一/§三/§七/§九、`scripts/spa_visual_check.sh`、`scripts/extract_v2_shell.py`、`scripts/update_v2_home_nav.py`、`scripts/deploy_doc_pages.py` |
| MCP | `app/mcp/tool_specs.py:213-240`、`app/mcp/wheatomics_tools.py:106-109,216-236` |
| 历史 | `git log --oneline -5 -- app/api/routers/expression.py app/static/expression/index.html`；`git log -- init_project_meta.sql` |
| 线上真实结构 | `curl https://wheatomics.sdau.edu.cn/api/expression/projects`（2026-11-11 09:25 CST，610,497 B） |
| 数据文件 | `~/Desktop/markdown/陈甜甜/5_10_15DAA对照和热胁迫小麦籽粒的转录水平RNA_翻译水平Ribo_和翻译效率TE.xlsx`（仅本地只读抽查）；**已核实 = Genome Biology 2025 补充表 S1 的逐格副本**（唯一差异：删了 `Description` 列与分组表头行，见同目录 `DATA_AUDIT.md` §2.1） |
| 既有约定 | `~/Desktop/markdown/陈甜甜/网站表达量信息梳理/`（上架评估 T1/T2、citation 修正清单）、`WheatOmics_expression审计_2026-10-26/`（332 项目审计包，本仓库 `wheatomics_results/audit/` 是其副本） |

### 1.2 关键证据命令

```bash
# 1) 历史变更（expression 路由 + 前端）
git log --oneline -5 -- app/api/routers/expression.py app/static/expression/index.html
#  59527f3 docs(api): translate OpenAPI documentation to English
#  82e24c4 style(expression): indent subgroup labels under group headings for clearer hierarchy
#  dd16a94 fix(expression): keep subgroup labels when sub_subgroup level is empty
#  0dfc996 feat(spa): convert batch B data apps + outline button bridge   ← 2026-10-27 换成 V2 shell
#  691c399 fix(expression): surface API JSON detail when a query returns 503

# 2) project_meta 的代码史（只有一次提交，之后再没进仓库）
git log --oneline -- init_project_meta.sql
#  240e6c2 2026-06-23 feat(expression): dynamic project_meta with citation, frontend shows citation

# 3) 线上项目目录（只读）
curl -s https://wheatomics.sdau.edu.cn/api/expression/projects | ...
#   projects=334, groups=5, subgroups=49, sub_subgroups=49, payload=610,497 B

# 4) 03G → 02G 自动转换（线上实测）
curl -s 'https://wheatomics.sdau.edu.cn/api/expression/query?gene_ids=TraesCS5A03G0935400&project=PRJEB5314_paired_tbl'
#   "genes_converted": {"TraesCS5A03G0935400": "TraesCS5A02G391700"}, "genes_found": 1

# 5) LC 基因也能查（现有 02G 表里含 LC）
curl -s '.../api/expression/query?gene_ids=TraesCS1A03G0000100LC&project=PRJEB5314_paired_tbl'
#   genes_converted: TraesCS1A03G0000100LC → TraesCS1A02G000100LC, genes_found=1
```

> ⚠️ 任务书里写的「线上 668 个项目」与实测不符：`project_meta` 是 **334 行**。
> 668 更可能是 `gene_expression` 库的**表数量**：334 个项目 × (主表 + `_std` 表) ≈ 668；
> 审计还记录过 14 个项目主表缺失、4 个项目只剩 `_std`（`wheatomics_results/audit/server_verification_findings.md` §2），
> 所以真实表数会略偏离 668。本报告以 **334 个项目** 为准。

---

## 2. 现有 expression 模块的数据模型（实测）

### 2.1 一个「项目」= 一张基因 × 样本的宽表

| 元素 | 实测/约束 | 证据 |
|---|---|---|
| 行 | 一个基因一行。现有表是 **266,849 行**（02G 全注释，含 LC） | `server_verification_findings.md:16`（`266,849 行 × 12 列`，`GeneID text` + `double` 样本列） |
| 基因列名 | 必须**精确叫 `GeneID`**（大写 G、大写 ID）。路由的取值列排除集合是大小写敏感的 `{"GeneID","IWGSCV1_1_id","id","ID"}`；若列名写成 `gene_id`，字符串 ID 会被当成数值去 `float()` → 500 | `expression.py:245`、`:250`；同类 bug 实证 `server_verification_findings.md` §3（`IWGSCV1_1_id` bigint 造成标签整体左移） |
| 样本列 | 每个样本一个**数值列**（`double`），列顺序 = 展示顺序；`DESCRIBE` 顺序决定数值列顺序 | `expression.py:212-218` |
| 主键 | **代码不要求**主键。审计快照只记录到现有表 `GeneID text`（未记录索引情况），按最坏情况假设为无索引全表扫描（266k 行）——新表建议 `VARCHAR(50) PRIMARY KEY` 兜底性能 | `server_verification_findings.md:16`；`expression.py:230` |
| `_std` 表 | **可选**。查询时 `SELECT * FROM \`{project}_std\` WHERE GeneID = %s` 被 `try/except` 包住，表不存在静默跳过（无误差棒、表头无 `(SD)` 列）。注意 `_std` 的基因列**硬编码 `GeneID`**（`expression.py:238`） | `expression.py:236-241`；前端 `index.html:903,910-912` |
| `has_std_table` | 字段存在于 `project_meta`，但**全仓库无任何代码读取**（`git grep -l has_std_table -- app main.py scripts` 无命中；只出现在 SQL 定义里）→ 只能当注释用 | §2.2 DDL |
| labels | `project_meta.labels` 是 JSON 数组，**与数值列按位置 zip**，不按名字；长度不一致时路由回退用真实列名（`expression.py:261-262`），前端再把回退后的列名当 x 轴标签 | `expression.py:220-268` |
| 单位 | **没有 unit 字段**；前端硬编码 TPM | §3.3 |
| 访问控制 | 用户传的 `project` 必须先在 `project_meta` 里存在（`SELECT 1 ... WHERE table_name=%s`），走通后才被反引号拼进 SQL。**所以「插一行 project_meta」= 授权一张表可查** | `expression.py:114-120`、`:178`、`:230` |

最小可查表（与代码完全兼容）：

```sql
-- 每项目一张表；下面以 RNA 为例（Ribo/TE 同构）。列名 = labels 的书写顺序。
CREATE TABLE `CS_grain_heat_RNAseq_FPKM_tbl` (
  `GeneID`   VARCHAR(50) NOT NULL COMMENT 'IWGSC RefSeq v2.1 (02G) 基因 ID',
  `5DAA_CK`  DOUBLE DEFAULT NULL,
  `5DAA_HS`  DOUBLE DEFAULT NULL,
  `10DAA_CK` DOUBLE DEFAULT NULL,
  `10DAA_HS` DOUBLE DEFAULT NULL,
  `15DAA_CK` DOUBLE DEFAULT NULL,
  `15DAA_HS` DOUBLE DEFAULT NULL,
  PRIMARY KEY (`GeneID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
  COMMENT='CS grain 5/10/15 DAA CK vs 1h heat stress — RNA-seq FPKM (condition means, RNA n=3; no SD)';
```

> 硬要求汇总：①列名恰好 `GeneID`；②除 `GeneID` 外**只放数值当量列**（不要放 `IWGSCV1_1_id`、`id`、注释列——会破坏 labels/值的按位置对齐）；③`project_meta.labels` 长度必须等于数值列数且顺序一致；④表名全局唯一。

### 2.2 `project_meta`：线上真实 DDL 与字段

线上结构与仓库 `init_project_meta.sql:13-25` 已经**不一致**（仓库缺 `subgroup`、`sub_subgroup`，且数据只有 69 行）。以线上备份为准（`wheatomics_results/audit/fix_verification/project_meta_bak_20261028_b.sql:25-38`，MySQL 5.7.33）：

```sql
CREATE TABLE `project_meta` (
  `id`            int(11) NOT NULL AUTO_INCREMENT,
  `table_name`    varchar(100) NOT NULL,   -- 数据表名（UNIQUE）
  `display_name`  varchar(300) NOT NULL,   -- 选择器/标题显示名
  `group_name`    varchar(50)  NOT NULL,   -- 一级分组（5 个）
  `labels`        json         DEFAULT NULL, -- 与数据列按位置对齐的标签数组
  `citation`      text,                    -- HTML 片段（Description:/Publication:/PubMed/DOI/archive <a>）
  `has_std_table` tinyint(1)   DEFAULT '1',-- 代码不读，仅注释
  `subgroup`      varchar(255) DEFAULT NULL,
  `sub_subgroup`  varchar(120) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_table_name` (`table_name`),
  KEY `idx_group_name` (`group_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;   -- AUTO_INCREMENT=515 @2026-10-28
```

仓库 `init_project_meta.sql` 的问题：`init_project_meta.sql:27-29` 注释「总共 69 条记录」；只建了 `group_name/labels/citation/has_std_table`，**没有 subgroup/sub_subgroup 的 ALTER 记录**；2026-06-23 之后没有任何迁移再进仓库 → 线上元数据事实上由手工 SQL 维护（§2.5）。

### 2.3 线上 334 个项目怎么分组

`GET /api/expression/projects` 的数据结构（实测 2026-11-11）：

```json
{"success": true, "data": {
  "projects": [{"id": "..._tbl", "description": "...", "categories": ["标签数组"],
                "citation": "Description:... Publication:...", "group": "...",
                "subgroup": "...", "sub_subgroup": ""}],
  "groups":   [{"name": "wheat abiotic stresses",
                "subgroups": [{"name": "Temperature stress",
                               "sub_subgroups": [{"name": "", "projects": [
                                  {"id": "...", "description": "...", "categories": [], "citation": "..."}]}]}]}]
}}
```

分组逻辑在 `app/services/expression_catalog.py`：

* 树为 `group_name → subgroup → sub_subgroup → projects`（`expression_catalog.py:62-137`）。
* **一级组顺序固定**：`wheat developmental tissues → wheat biotic interaction → wheat abiotic stresses → wheat population → wheat genetic material`，不在列表里的组按名称排在最后（`expression_catalog.py:108-126`）。
* **子组顺序**：`wheat developmental tissues` 用 `SUBGROUP_ORDER`（Root/Stem/Leaf/Spike/Seed…，`expression_catalog.py:12-19,99-102`）；`wheat abiotic stresses` / `biotic` / `genetic material` 按**项目数降序**（`expression_catalog.py:23-27,94-104`）；其余按名称。
* **`sub_subgroup` 为空时前端自动折叠该层**（`app/static/expression/index.html:320-330`），所以新项目设 `sub_subgroup=''` 即可，不会出现多余空层级。

线上实测分布（334 个项目）：

| group | 项目数 | 与本数据的相关子组（实测项目数） |
|---|---|---|
| wheat genetic material | 97 | — |
| wheat abiotic stresses | **96** | **Temperature stress 17**、Multi-treatments 16、Drought 12、Salt 12 … |
| wheat biotic interaction | 70 | — |
| wheat developmental tissues | 55 | Seed / Grain 29、Spike/Floral organs 12 … |
| wheat population | 16 | — |
| **合计** | **334** | 49 个 subgroup / 49 个 sub_subgroup 层级 |

→ **本数据的落位建议：`group_name='wheat abiotic stresses'`、`subgroup='Temperature stress'`、`sub_subgroup=''`。**
理由：处理是热胁迫（不是发育本身）；该子组已有 17 个项目、按项目数降序会自然上浮；3 个项目同时进组后=20，位置靠前；不新增子组，选择器不膨胀。备选：`wheat developmental tissues` / `Seed / Grain`（若马老师希望按组织检索）。

### 2.4 查询链路（`/api/expression/query`）

1. `project` 必须在 `project_meta` 中存在，否则 400 `Unsupported expression project`（`expression.py:114-120`）。
2. 基因 ID 校验（只允许 `[A-Za-z0-9_.:-]`，`app/core/security.py:60,72-83`）。
3. 非 02G 批量转 02G：一条 SQL 查 `Genehub_DB.GenePageIWGSCv1_table` 的 `GeneIDv1/v2/v3`；未命中按字符串 `01G→02G` / `03G→02G` 兜底；转换结果写进 `genes_converted`（`expression.py:129-173`）。
4. `DESCRIBE` 表结构；表不存在则返回 **503 + JSON 说明**（`expression.py:175-190`，2026-10-26 修复）。
5. 按位置取 `labels`；每个基因 `SELECT *`；可选读 `_std`；`NULL` 数值统一变 **`0.0`**（`expression.py:250`）；labels 长度不等于数值数时回退真实列名（`expression.py:261-262`）。
6. 返回 `{project, genes_found, genes_not_found, genes_converted, results:[{gene_id, points:[{label,value,std,error_bar}]}]}`（`app/schemas/expression.py:8-31`）。

**没有缓存**：每次 `/projects` 都全量读 `project_meta`（`expression_catalog.py:30-59`），每次 `/query` 都现查库 → **插元数据立即生效，无需重启**。

### 2.5 一条重要历史线索（说明「动态元数据」的边界）

`240e6c2`（2026-06-23）把硬编码项目列表改成 `project_meta` 表 + 前端 citation 渲染（提交同时加入 69 行 `init_project_meta.sql`）。之后 10-26~10-29 的格式修复、V2 shell 改造、发育组织重分组等都只改了代码，**元数据变更没有回到仓库**。因此：

* 新增项目**不需要改任何代码**（方案 A 零代码成立）；
* 但「仓库里没有权威数据源」是长期维护风险（本报告 §8 Phase 5 建议把本数据的 DDL/INSERT 脚本落库到 `scripts/sql/` 或本计划目录以留痕）。

---

## 3. 前端能力评估（`app/static/expression/index.html`，当前线上一致）

### 3.1 点数/标签容量

| 能力 | 实测行为 | 证据 |
|---|---|---|
| x 轴标签数 | 标签=API `points[].label` 顺序（`index.html:526-528`）；字号按数量自动 11→10→9→8px（`>10 → 10px`，18 个标签=10px）；`>80` 才抽稀（`step=ceil(n/80)`） | `index.html:551-559,801` |
| 下限 | 15 标签（默认项目 PRJEB5314）是日常基线；**18 标签完全够用** | 线上项目实测 |
| 可读性阈值 | 审计实测：70/81 标签相邻重叠、638 标签成黑带（`wheatomics_results/audit/page_findings.md:48,53,128-133`）。**>40 开始不可读，>70 不可用**。18 远低于阈值 | 同上 |
| 表格 | 列 = `Gene ID` + N 标签 +（有 std 时）N 个 `(SD)`；18 列 ≈ 19 列，可正常横向滚动 | `index.html:902-928` |
| 多项目 | 勾选几个项目就发几次 `/query`（每项目一个请求），结果块按选择顺序预建；**前端无项目数上限**（全选 334 会发 334 个请求，不建议） | `index.html:444-497` |
| 错误处理 | 单项目失败只在该块显示文字（503 detail 可读，`index.html:482-496`） | — |

### 3.2 分组能力

**没有。** x 轴是扁平的 `labels` 数组；只能靠「标签文本前缀」伪装分组，没有第二个轴/面板/色带。想要「RNA/Ribo/TE 分组」只有两条路：**拆成 3 个项目**（推荐）或**做独立 SPA**。

### 3.3 单位措辞（TPM vs FPKM）— 冲突成本

硬编码 TPM 共 5 处（当前行号，线上与仓库一致）：

| 位置 | 内容 | 行 |
|---|---|---|
| hero 导语 | "Plot and tabulate **TPM** expression profiles …" | `index.html:83` |
| hero 标签 | "**TPM expression**" | `index.html:86` |
| 柱状图 tooltip | `{point.y:.2f} TPM` | `index.html:631` |
| 误差棒 tooltip | `{point.low:.2f} - {point.high:.2f} TPM` | `index.html:675` |
| y 轴标题 | `Expression (TPM)` | `index.html:840` |

其它位置：`/api/expression/projects` **不返回 unit**（实测字段只有 `id/description/categories/citation/group/subgroup/sub_subgroup`）；`schemas/expression.py` 无 unit 字段；`TF_Atlas.html:311` 的 TPM 是另一个模块的数据，不在本次范围。

**结论**：若要把 FPKM/TE 放进 expression 页，**必须加一个 unit 维度**（否则对外就是错误标注）。好在成本很低：

* `project_meta` 加一列 `unit`（DDL 1 条，默认 `'TPM'`，现有 334 行自动继承 → 330/334 正确，2 个已确认非 TPM 项目可顺手修正）；
* `expression_catalog.py` 的 SELECT 和扁平/树两个 dict 各加一个字段（约 5 行）；
* 前端 5 处字符串改成按项目 unit 渲染（约 20 行，缺失时回落 TPM 保证兼容）；
* 合计 **约 0.5 人日工程**，同时把「TPM 硬编码」这个审计遗留 P2 一起修掉（`wheatomics_results/audit/page_findings.md:51,169-177`）。

### 3.4 Citation 渲染约定（新项目必须遵守）

`parseCitation`（`index.html:177-226`）按固定格式拆字段，**新项目的 `project_meta.citation` 必须写成**：

```
Description:<一句话描述> Publication:<文献标题/期刊> PubMed Link:<https://pubmed.ncbi.nlm.nih.gov/PMID/>;DOI Link:<https://doi.org/10.xxxx/xxxx> <a href="<archive-url>">ACCESSION</a>
```

* 至少一段 `Description:`；有 `Publication:` 才会拆出第二段；
* `PubMed`/`DOI` 要写成**可被正则识别的 URL**（`https://pubmed.ncbi.nlm.nih.gov/<数字>/`、`https://doi.org/10…`）；
* 归档号用**恰好一个 `<a href>`**，前端按前缀补全到 NCBI/ENA/CNCB（`index.html:166-175`）；
* description 里的原始前缀会被 `scrub()` 清掉，但**不要嵌套 HTML**（`citation` 会被 `.text()` 渲染，链接只从解析结果重建）。

### 3.5 其它前端事实

* 默认勾选只有 `PRJEB5314_paired_tbl`（`index.html:280`）。
* 不支持 `?gene=` / `?project=` 深链（页面没有读 `location.search`）——从基因详情页跳转/带预选基因需要另加约 20 行（方案 C 或后续增强）。
* 页面标题/描述来自 `display_name`，选择器按 description 字母序排列（`index.html:286-290`）→ 3 个项目的 `display_name` 用同一前缀可保证相邻。
* `/expression/index.html` **不在** no-cache 白名单里（`main.py:173-193` 只覆盖 `/genes/` 与 `/api/v2shell/`）→ 前端改版后用户可能读到浏览器缓存的旧页面，需要强刷或把 `/expression/` 加进该中间件（1 行条件）。

---

## 4. 新数据与现有模型的硬约束

数据文件本地抽查（只读）：60,125 个基因 × 18 个数值列（RNA 6 + Ribo 6 + TE 6），无重复基因；**全部 03G 格式**，其中 **10,567 个 LC**、529 个 `TraesCSU03G…`（unplaced）；RNA/Ribo 列和 0.64–1.64×10⁶（**不是 TPM**，TPM 定义要求每样本和=10⁶）；TE=Ribo/RNA 抽样 3,004 个点 **100% 吻合**；TE 中位数 0.72、p99 9.74、**最大 9120**（RNA FPKM 很小时的比值放大）；**表内是条件均值：RNA n=3、Ribo n=2，无 per-replicate 列、无 SD**；TE 实测口径 **RNA FPKM ≥ 0.2 才计算 TE，否则 NA**（六列 NA 各 4,658–6,645 个；9,189 个基因至少 1 个 TE NA、3,965 个基因 6 个 TE 全 NA）；2,309 个基因 RNA 全 0。数据溯源：该 xlsx 与 Genome Biology 2025 补充表 S1 **逐格一致**（`DATA_AUDIT.md` §2.1），不是本平台重新定量。

| # | 硬约束 | 影响 | 处理 |
|---|---|---|---|
| H1 | **表必须以 02G 为键**（查询链路先把 03G 转 02G） | 直接以 03G 建表 → 用户传 03G 会被转成 02G 后查不到；传 02G 才能命中，违背数据来源标注 | 导入前做 03G→02G 映射（`Genehub_DB.GenePageIWGSCv1_table`，见 §7.4）；映射丢失的基因列清单后处理 |
| H2 | **TE 不是表达量**（Ribo/RNA 比值，无量纲，0–9000） | 放进 expression 页会被当作表达量画柱状图，且与 FPKM 同轴/同单位；一个 9000 的 TE 会把同基因其它 5 根柱子压成 0 | **TE 单独一个项目**（推荐），ylabel 绑定 `Translation efficiency (TE)`；极端值需数据侧截断/说明，或走方案 C 用 log 轴 |
| H3 | **FPKM ≠ TPM**（页面 5 处硬编码 TPM） | 对外标注错误 | 方案 B 加 unit 字段；方案 A 不能正式上线 |
| H4 | **表内是条件均值（RNA n=3、Ribo n=2），无 per-replicate 列、无 SD**；TE 对 RNA FPKM < 0.2 记为 NA | 不能画误差棒；`label` 只有条件名；TE NA 在 API 里会变 0.0（`expression.py:250`） | `has_std_table=0`、不建 `_std` 表（代码容错）；citation 写 "condition means (RNA n=3, Ribo n=2; no SD)"；TE NA 建议**入库 NULL**并说明「TE 不可计算显示为 0」，或 TE 走方案 C 保留 NA |
| H5 | **60,125 行 < 现有 266,849 行**（子集） | 其它基因查询本数据会 `genes_not_found`——正常；但用户可能误以为「没表达」 | display_name/citation 里写明「仅含 RNA-seq/Ribo-seq 检出的 60,125 个基因」 |
| H6 | **03G→02G 映射覆盖率未知**（尤其 10,567 个 LC） | 若映射丢失多，方案 A/B 的数据不完整 | **Phase 0 必须先量化**：`DATA_AUDIT.md` §3.2 抽样 300/300（160 非 LC + 140 LC，含 chrUn）可映射，但抽样不等于全量；目标 ≥98%，否则转方案 C |
| H7 | **数据来源已确认（不再是"文献未定"）**：热胁迫 = Chen et al. 2025 *Genome Biol* 26(1):382（PMID 41214722，PMCID PMC12599102，DOI 10.1186/s13059-025-03848-4，**CC BY-NC-ND 4.0**），原始数据 PRJNA1135409；对照 = Guo et al. 2023 *Plant Cell* 35(6):1848–1867（PMID 36905284，DOI 10.1093/plcell/koad075，**© ASPB 非 OA**），PRJNA871371 | citation 已可写真实串；**再发布授权**需注意：CC BY-NC-ND（非商用/禁演绎）+ PlCell 非 OA → 建议先取得通讯作者（彭惠茹组）同意并写清两篇来源 | citation 用 `PAPER_CONTEXT.md` §8.2 的 3 链接安全版（accession · PubMed · DOI，**只 1 个 `<a>`**）；上架前确认授权 |
| H8 | 现有表 `GeneID` 为 `text`（索引情况未核实，见 §2.1） | 每基因每次查询可能扫全表；60k 行可接受但可更好 | 新表用 `VARCHAR(50) PRIMARY KEY`（代码兼容，见 §2.1） |

---

## 5. 挂接点盘点（改动成本）

| 挂接点 | 现状 | 加新项目后 | 成本 |
|---|---|---|---|
| `/expression/` 页面 | 读 `/api/expression/projects`，全部项目自动出现 | **自动出现 3 项**；选择后 3 个块、每块 6 点 | 0（方案 A）；unit 方案约 0.5 人日 |
| `/api/expression/*` | 动态读 `project_meta`，项目级校验 | **自动生效**（无需注册路由/重启） | 0 |
| GeneHub 基因页 `app/static/docpages/gene.html` | 下拉框动态加载全部 334 项（`:138,396-415`），表格三列 `Stage / tissue`、`Value`、`Std`（`:419-440`） | **自动出现**；表格 6 行；页面无「TPM」字样，单位冲突小 | 0（可选：表头加 unit，1 行 + `deploy_doc_pages.py` 发布） |
| 旧版基因页 `/cgi-bin/geneDetail.py` | **硬编码 69 项** `<select>`（`app/static/docpages/geneDetail.py:178-237`）→ 表单指向旧 CGI `/cgi-bin/gene_expression.py`（3,198 行、逐项目硬编码 if 链，`cgi-py-RawScript/gene_expression.py:61+`） | **不会自动出现**；但新版 CGI 默认 302 到 `/GeneHub/gene.html`（`geneDetail.py:19-29`），用户实际看不到旧表单 | 0（不碰旧 CGI）；如非要支持 ≈ 2 个 CGI + 一轮 root 部署，不推荐 |
| KnownGene `app/static/genes/`（任务书提到的「基因详情页」） | **没有表达入口**（`grep -c expression app/static/genes/detail.html` = 0） | 不需要改 | 0；若想从 KnownGene 深链到表达页，需给 expression 页加 `?gene=` 支持（约 20 行）+ 详情页加链接（可选，0.5 人日） |
| MCP | `list_expression_projects` / `query_expression` 动态走同一 API（`app/mcp/tool_specs.py:213-240`、`wheatomics_tools.py:106-109,216-236`） | **自动出现**（compact 视图含 id/description/categories/group/subgroup） | 0（若加 unit，工具描述补 1 行） |
| 共表达 | 数据库白名单硬编码 3 个（`app/core/security.py:11-15`） | 18 个样本（每 assay 仅 6 个）算 PCC 样本量不足，**不建议**建 CO 库 | 若要建：白名单 +1 行 + 数据侧计算 |
| JBrowse | 仓库无表达量 track 支持（`app/api/routers/jbrowse.py` 无 expression），实例配置在服务器 `/jbrowse-1.12.3-release`、`/jbrowse2/` 外部 | 若要「基因组轨道看 RNA/Ribo 覆盖」需服务器侧做 BigWig + trackList；FPKM/TE 本身也不是轨道数据 | 3 人日+，**不推荐** |
| 下载页 `/download.html` | 服务器 docroot 页面，仓库源 `app/static/docpages/download.html`；现有 4 个板块（基因组/转录本/共表达/660K） | 可加「热胁迫翻译组」板块 + 数据压缩包链接；论文 Table S2（21,964 DEG）/ Table S3（11,343 DTG + 8 clusters）可作二期下载 | 0.5 人日（需要数据托管位置） |
| 导航 | SPA 共用 `/api/v2shell/shell.js`；源在 `app/static/blast2/index.html`，由 `scripts/extract_v2_shell.py` 再生成；首页 `/var/www/html/index.html` 不在仓库，用 `scripts/update_v2_home_nav.py` 打补丁 | 方案 A/B **不加新页面 → 导航不用改**；方案 C 才需要 | 0 / 方案 C 加 0.5 人日 |
| 文档 `/agent.html` | 28 个 MCP 工具表 + REST 模块表 | 方案 B 不需要改；方案 C 新 API 需要加文档 | 0 / 0.5 人日 |

---

## 6. 三个方案（取舍 / 工作量）

> 工作量按「数据侧 1 份 xlsx 已就绪、映射 SQL 可跑、服务器可写」估算；含验证与上线，不含马老师审文案的时间。

### 方案 A — 最小改动（零代码，**只适合内部预览 / 抢时间上线**）

* **做法**：3 张 6 列表（RNA/Ribo/TE）+ 3 行 `project_meta`；`labels` 各 6 个；不建 `_std`；不引入 unit。
* **优点**：不碰任何代码，1 条路线；DDL + 3 条 INSERT 即可；全套现有页面/MCP/基因页自动生效；**0.5–1 人日**（主要是映射 + 导入 + 验证）。
* **缺点**：①页面把 FPKM/TE 标成 `Expression (TPM)`（5 处）；②TE 与 FPKM 单位混用但至少分 3 个项目、不共图；③TE NA 显示 0；④对外发布口径不严谨，审计已把「TPM 硬编码」列为 P2，本数据会把它从「设计问题」变成「事实错误」。
* **替代「绝对最小」**：1 张 18 列表 + 1 行 meta（1 条 DDL + 1 条 INSERT）。**不推荐**：18 个标签平铺把 RNA/Ribo/TE 混在一条 x 轴、同一 y 轴，TE 与 FPKM 数量级差 3–4 个量级，图不可读、语义错误更严重。

### 方案 B — 推荐（expression 模块 + `unit` 字段，**1.5–2 人日**）

* **做法**：在 A 的基础上：① `project_meta` 加 `unit`（默认 `'TPM'`，3 行分别为 `FPKM/FPKM/TE`）；② `expression_catalog.py` 透出 unit；③ 前端 5 处按 unit 渲染（缺省回落 TPM）；④ 3 张表仍以 02G 为键；⑤ `display_name/citation` 按现有格式写清单位与 NA 处理。
* **优点**：所有现有触点（expression 页 / API / GeneHub 基因页 / MCP / citation）一次性覆盖；把全站单位语义一次修对（现有 334 项目中 2 个已确认非 TPM 可顺手标注）；TE 单独项目、单独 y 轴；改动量小（1 个服务文件 + 1 个前端文件 + 1 条 DDL），无新路由、无新 mount、无 Apache 改动。
* **缺点**：TE 仍是「柱状图 + 线性轴」，极端值（9120）需要数据侧处理或文案说明；TE NA 仍是 0。若这两点不可接受 → 升 C。
* **工作量**：数据映射/导入 0.5–1 人日 + DDL/INSERT 0.2 + 代码 0.5 + 验证/上线 0.5 ≈ **1.5–2 人日**。

### 方案 C — 长期（独立 `/translatome/` SPA + `/api/translatome`，**5–8 人日**）

* **做法**：新 SPA + 新 router（03G 直存或 02G 映射均可自定），按 RNA/Ribo/TE 三面板/分组展示，支持 NA 显示、log 轴、阈值/排序、下载、样本元数据、citation；导航/首页/文档/MCP 同步。
* **优点**：语义最正确（TE 独立视觉、NA 不丢、可做分组与筛选）；不再受 expression 模块「宽表+TPM 柱状图」约束；以后可扩其他 translatome 数据集。
* **缺点**：新前端 + 新后端 + 新挂载 + Apache 两条 ProxyPass + 导航/落地页/文档/MCP 全链路；双份维护；**5–8 人日**；对单个数据集性价比低。
* **折中 C-lite（可选）**：只做独立前端、复用 3 张 02G 表 + 现有 `/api/expression/query`，约 1.5–2 人日；但 TE NA 仍 0、仍需 unit 语义（可在前端自己带单位），不如 B 干净。

### 推荐结论

**先做方案 B**。它用 ~1.5–2 人日把数据放进平台全部现有入口，并把单位问题一次性修对；等 translatome 数据集变多、或马老师明确要「TE 独立可视化 / NA 保真 / 阈值筛选」时，再上方案 C。**方案 A 仅在「今天就要给链接、且明确接受页面标 TPM」时使用**，并应排期尽快升级到 B。

> **与同目录报告的衔接**：`PAPER_CONTEXT.md` §8.4 给出的 `labels` 是 **1 个项目 18 项**（对应「1 张 18 列宽表」），那是方案 A 的「绝对最小」形态；本报告推荐拆 3 个项目（每个 6 项 labels），原因是 TE 不是表达量、必须独立 y 轴（见 §3.2/§4 H2）。两种写法的 `labels` 都已在各自报告中给出，Lead 拍板方案后直接取对应数组即可。`DATA_AUDIT.md` §3.2 抽样 300/300 个 03G 基因可映射到 02G，支持方案 A/B 的可行性；全量 60,125 的映射审计仍需在 Phase 0 完成。

---

## 7. 方案 B 落地细节

### 7.1 DDL（`gene_expression` 库；MySQL 5.7.33）

```sql
-- ① 元数据：单位字段（先跑这条，再发代码；代码 SELECT 依赖它）
ALTER TABLE project_meta
  ADD COLUMN `unit` VARCHAR(32) NOT NULL DEFAULT 'TPM'
  COMMENT '数值单位：TPM/FPKM/TE/…；前端据此绑定 y 轴与 tooltip'
  AFTER `has_std_table`;

-- 可选：顺手修正审计已确认的 2 个非 TPM 项目（需马老师同意改显示口径）
-- UPDATE project_meta SET unit='a.u.' WHERE table_name IN ('PRJEB51827_tpm','PRJNA325489_tbl');

-- ② 三张数据表（列名 = labels 顺序；只允许 GeneID + 数值列）
CREATE TABLE `CS_grain_heat_RNAseq_FPKM_tbl` (
  `GeneID`   VARCHAR(50) NOT NULL,
  `5DAA_CK`  DOUBLE DEFAULT NULL, `5DAA_HS`  DOUBLE DEFAULT NULL,
  `10DAA_CK` DOUBLE DEFAULT NULL, `10DAA_HS` DOUBLE DEFAULT NULL,
  `15DAA_CK` DOUBLE DEFAULT NULL, `15DAA_HS` DOUBLE DEFAULT NULL,
  PRIMARY KEY (`GeneID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
  COMMENT='CS grain 5/10/15 DAA CK vs 1h heat stress — RNA-seq FPKM';

CREATE TABLE `CS_grain_heat_RiboSeq_FPKM_tbl` LIKE `CS_grain_heat_RNAseq_FPKM_tbl`;
ALTER TABLE `CS_grain_heat_RiboSeq_FPKM_tbl` COMMENT='... — Ribo-seq FPKM';

CREATE TABLE `CS_grain_heat_TE_tbl` LIKE `CS_grain_heat_RNAseq_FPKM_tbl`;
ALTER TABLE `CS_grain_heat_TE_tbl` COMMENT='... — translation efficiency (TE = Ribo/RNA)';
```

> 表名只是建议（≤100 字符、全局唯一）；`CREATE TABLE ... LIKE` 会连列顺序一起复制，正好保证 labels 对齐。

### 7.2 `project_meta` INSERT（含 citation 示例）

```sql
-- 上线前先备份（沿用仓库既有做法，见 §2.5）
CREATE TABLE project_meta_bak_20261111 LIKE project_meta;
INSERT INTO project_meta_bak_20261111 SELECT * FROM project_meta;

START TRANSACTION;

INSERT INTO project_meta
  (table_name, display_name, group_name, subgroup, sub_subgroup,
   labels, citation, has_std_table, unit)
VALUES
 ('CS_grain_heat_RNAseq_FPKM_tbl',
  'Chinese Spring - grain 5/10/15 DAA - 1 h heat stress vs control - RNA-seq FPKM',
  'wheat abiotic stresses', 'Temperature stress', '',
  '["5DAA_CK","5DAA_HS","10DAA_CK","10DAA_HS","15DAA_CK","15DAA_HS"]',
  'Chinese Spring wheat developing grains at 5, 10, 15 DAA, control (CK); RNA-seq FPKM. Data are condition means (RNA n=3, Ribo n=2; no SD). Control RNA-seq libraries from Guo et al. 2023 Plant Cell (PMID 36905284). <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA871371\'>PRJNA871371</a> https://pubmed.ncbi.nlm.nih.gov/36905284/ https://doi.org/10.1093/plcell/koad075',
  0, 'FPKM'),

 ('CS_grain_heat_RiboSeq_FPKM_tbl',
  'Chinese Spring - grain 5/10/15 DAA - 1 h heat stress vs control - Ribo-seq FPKM',
  'wheat abiotic stresses', 'Temperature stress', '',
  '["5DAA_CK","5DAA_HS","10DAA_CK","10DAA_HS","15DAA_CK","15DAA_HS"]',
  'Chinese Spring wheat developing grains at 5, 10, 15 DAA, control (CK) vs 1 h 42 °C heat stress (HS); Ribo-seq FPKM. Data are condition means (RNA n=3, Ribo n=2; no SD). HS data from Chen et al. 2025 Genome Biol (PMID 41214722); CK data from Guo et al. 2023 Plant Cell (PMID 36905284, PRJNA871371). <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1135409\'>PRJNA1135409</a> https://pubmed.ncbi.nlm.nih.gov/41214722/ https://doi.org/10.1186/s13059-025-03848-4',
  0, 'FPKM'),

 ('CS_grain_heat_TE_tbl',
  'Chinese Spring - grain 5/10/15 DAA - 1 h heat stress vs control - translation efficiency (TE)',
  'wheat abiotic stresses', 'Temperature stress', '',
  '["5DAA_CK","5DAA_HS","10DAA_CK","10DAA_HS","15DAA_CK","15DAA_HS"]',
  'Chinese Spring wheat developing grains at 5, 10, 15 DAA, control (CK) vs 1 h 42 °C heat stress (HS); translation efficiency TE = mean Ribo-seq FPKM / mean RNA-seq FPKM; TE is reported only when RNA-seq FPKM ≥ 0.2, otherwise NA (per TE column 4,658–6,645 genes). Data are condition means (RNA n=3, Ribo n=2; no SD). Source: Chen et al. 2025 Genome Biol (PMID 41214722); CK libraries from Guo et al. 2023 Plant Cell (PMID 36905284, PRJNA871371). <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1135409\'>PRJNA1135409</a> https://pubmed.ncbi.nlm.nih.gov/41214722/ https://doi.org/10.1186/s13059-025-03848-4',
  0, 'TE');

COMMIT;
```

要点：

* `labels` 是 **JSON 字符串**，长度必须 = 数值列数（6），顺序 = `CREATE TABLE` 的列顺序（5/10/15 × CK/HS）。
* `sub_subgroup=''`（不是 NULL 也可以，前端会折叠）。
* `display_name` 用统一前缀（`Chinese Spring - grain 5/10/15 DAA ...`），且**必须带单位**（`RNA-seq FPKM` / `Ribo-seq FPKM` / `translation efficiency (TE)`）——否则用户会与站内 TPM 项目混淆（马老师口径）；同一前缀保证选择器按 description 排序时 3 项相邻。
* 没有 `_std` 表 → `has_std_table=0`（仅注释；代码不读）。
* citation 按 §3.4 格式；上面的文本取自已核实的论文溯源报告（同目录 `PAPER_CONTEXT.md` §8.2）：**只放 1 个 `<a>`**（第二个 anchor 会以原始 HTML 漏出），第二篇论文用 `PMID 36905284` 纯文本；单引号在 SQL 里写成 `\'`（与 `init_project_meta.sql` 现有风格一致）。
* **授权需先确认**：热胁迫数据论文 Genome Biol 2025 为 **CC BY-NC-ND 4.0**，对照数据论文 Plant Cell 2023 为 **© ASPB，非 OA**（`PAPER_CONTEXT.md` §0/§5）→ 站点再发布 FPKM/TE 衍生值前请马老师确认许可/致谢写法。

### 7.3 代码改动点（方案 B，约 30 行）

| 文件 | 改动 | 行 |
|---|---|---|
| `app/services/expression_catalog.py` | `SELECT … group_name, subgroup, sub_subgroup, unit FROM project_meta`；`projects.append({... "unit": (row.get("unit") or "TPM").strip()})`；`tree...append({... "unit": ...})` | `:34-56`、`:77-82`、`:129-135` |
| `app/static/expression/index.html` | ① 加载 project 目录时建 `projectUnits[proj.id] = proj.unit \|\| 'TPM'`（紧挨 `projectCitations`，`:270-273`）；② hero 文案去 TPM（`:83`）或保留通用描述；③ stat 标签（`:86`）；④ 每个结果块取 `unit`，tooltip（`:631`）、误差棒 tooltip（`:675`）、yAxis（`:840`）用 unit；⑤ `unit === 'TE'` 时 y 轴标题用 `Translation efficiency (TE = Ribo/RNA)` | 5 处 |
| `app/schemas/expression.py`（可选） | `ExpressionQueryResponse` 加 `unit: str = "TPM"`，路由返回；MCP/第三方可直接拿到单位 | `:25-31` |
| `app/mcp/tool_specs.py`（可选） | `query_expression` 描述补一句「返回值的单位见 project_meta.unit（TPM/FPKM/TE）」 | `:229-240` |
| `main.py`（可选） | 把 `/expression/` 加进 no-cache 中间件，避免上线后用户看旧页 | `:173-193` |

> 若不想动 `app/`：只做 §7.1 的表 + §7.2 的 INSERT 就是方案 A；但**正式对外发布不建议**（TPM 误标）。

### 7.4 数据导入流程（03G → 02G → 3 张表）

**Phase 0（数据侧，必须先跑）**：量化映射覆盖率。

**初步证据（Lead 2026-11-11，已核实）**：用线上 `GET /api/genes/detail/{03G_id}` 随机抽样 300 个 03G 基因（160 非 LC + 140 LC，含 chrUn）→ **300/300 都拿到 02G 对应 ID（100%，n=300）**（`DATA_AUDIT.md` §3.2）。这是可行性证据，**不能代替全量审计**——全量 60,125 个仍须按下面的 SQL 做一遍并交付未命中/多对一清单。

```sql
-- 在服务器上导出映射（只读）：
-- Genehub_DB.GenePageIWGSCv1_table 的列名由 expression.py:145 与 docs/known_genes/* 证据确认
SELECT GeneIDv3 AS g03, MIN(GeneIDv2) AS g02
FROM Genehub_DB.GenePageIWGSCv1_table
WHERE GeneIDv3 IS NOT NULL AND GeneIDv2 IS NOT NULL AND GeneIDv3 <> ''
GROUP BY GeneIDv3;

-- 覆盖率（把 60,125 个 03G ID 先灌进临时表）：
CREATE TEMPORARY TABLE tmp_g03 (gene_id VARCHAR(50) PRIMARY KEY);
-- LOAD DATA LOCAL INFILE '/tmp/genes_03g.txt' INTO TABLE tmp_g03 LINES TERMINATED BY '\n';
SELECT COUNT(*) AS n_03g,
       SUM(m.g02 IS NOT NULL) AS n_mapped,
       ROUND(SUM(m.g02 IS NOT NULL)/COUNT(*)*100, 2) AS pct_mapped
FROM tmp_g03 t
LEFT JOIN (SELECT GeneIDv3 AS g03, MIN(GeneIDv2) AS g02
           FROM Genehub_DB.GenePageIWGSCv1_table GROUP BY GeneIDv3) m
  ON m.g03 = t.gene_id;
```

* **门槛建议**：`pct_mapped ≥ 98%` 且 LC 子集映射丢失可接受 → 走 A/B；否则走 C（03G 直存 + 新查询路径），或先让数据组补映射。
* **不要**在导入阶段用 `replace('03G','02G')` 兜底生成假 ID——那是查询期的兜底逻辑，不代表真实同源关系；导入必须用映射表，未命中就剔除并输出清单。
* 同一 02G ID 若被多个 03G 命中也需去重策略（保留表达量最高/明确主基因，其余列清单）。

**导入（建议做成可复现脚本，放 `scripts/expression/import_heat_translatome.py`）**：

```python
# 读取本地 xlsx → 映射 → 3 张 CSV；服务器端只依赖 pymysql（不装 openpyxl）
# 1) 本地：openpyxl 读 Table S1（第 3 行起为数据；18 列列名固定）
# 2) join 03G→02G 映射（未命中计数/落盘）
# 3) TE 列 'NA' → None（入库 NULL）
# 4) 写 rna.csv / ribo.csv / te.csv（首列 GeneID_02G）
# 5) 服务器：pymysql executemany 批量 INSERT（每 1000 行 commit），失败回滚
```

服务器端导入命令（`wheatomics_user` 需有 `gene_expression` 的 CREATE/INSERT 权限，先 `SHOW GRANTS` 确认）：

```bash
# 只读校验：表结构/行数
mysql -u wheatomics_user -p gene_expression -e "
  SELECT COUNT(*) FROM CS_grain_heat_RNAseq_FPKM_tbl;
  SELECT GeneID FROM CS_grain_heat_RNAseq_FPKM_tbl LIMIT 3;"
```

> 备选：若 `wheatomics_user` 有 FILE 权限或运维可用 root `LOAD DATA LOCAL INFILE`，可直接灌 CSV；
> 否则用上面的 Python 批量 INSERT（与仓库既有一次性脚本风格一致，如 `scripts/crawl_bioprojects.py`）。

### 7.5 TE 处理建议

| 项 | 建议 |
|---|---|
| NA 语义 | 文件里 `NA` 表示 **RNA FPKM < 0.2 导致 TE 不可计算**（实测口径，不是只看 RNA=0）；六列 NA 各 4,658–6,645 个。**入库 NULL**（不要存字符串 `NA`，否则 `float('NA')` 会 500） |
| 展示 | 当前 API 把 NULL 变 0.0（`expression.py:250`），页面显示 0；在 `display_name`/`citation` 里写明「RNA FPKM < 0.2 的基因 TE 不可计算，页面显示为 0」——或在方案 C 里保留 NA |
| 极端值 | TE max 9120；同一基因 6 个 TE 点若含极端值会压扁柱状图。建议数据侧**截断到 p99（≈10）并单独给完整值下载**，或在方案 C 用 log 轴；两者都需要马老师确认口径 |
| 重复/均值 | 表内是**条件均值**（RNA n=3、Ribo n=2），不是单样本；citation/说明必须写 "condition means (RNA n=3, Ribo n=2; no SD)"，避免被误读成 n=1 |
| 单位 | `unit='TE'`，y 轴不写 TPM/FPKM |

---

## 8. 分阶段执行步骤（方案 B）

> 原则：**先建表（不可见）→ 再改代码/DDL → 最后插元数据（一插即上线）→ 验收 → 可回滚**。
> `project_meta` 是每次请求现查的，插行即生效；但代码依赖新的 `unit` 列，所以 **① DDL 必须先于代码部署**。

### Phase 0 — 数据侧（Lead/数据组，0.5–1 人日）

1. 03G→02G **全量**映射审计（§7.4 SQL；已有 300/300 抽样初步证据，仍须全量），输出未命中/多对一清单；确认 LC/chrUn 处理策略。
2. 确认单位（FPKM / TE）、**TE 的 RNA FPKM < 0.2 → NA 规则**、极端值截断、基因子集说明。
3. 产出 3 张 02G 键 CSV（或 SQL），记录行数/列和/空值统计；冻结输入 xlsx 的 md5（该文件 = GB 2025 Table S1，`DATA_AUDIT.md` §2.1，无需重算）。
4. citation/授权：采用已核实的 GB 2025 + PlCell 2023 引用（§7.2 已给真实串），确认 **CC BY-NC-ND / PlCell 非 OA** 的再发布许可；确定 3 个**带单位**的 `display_name` 文案。

### Phase 1 — 建表 + 灌数（0.5 人日，线上 DB，写入前备份）

1. `mysql` 执行 §7.1 两张/三张 DDL（表建好但**没有 project_meta 行 → 前端/API 不可见**，安全）。
2. 灌数（§7.4），跑 SQL 验收（§9 第 1–3 条）。
3. 若灌数失败：`DROP TABLE` 三张新表即可，无其他影响。

### Phase 2 — `unit` DDL + 代码（0.5 人日）

1. `ALTER TABLE project_meta ADD COLUMN unit ...`（§7.1）。
2. 按 §7.3 改 `expression_catalog.py` + `app/static/expression/index.html`（＋可选 schema/MCP/no-cache）。
3. 本地起服自测：`uvicorn main:app --reload --port 8000`，浏览器打开 `/expression/` 选 3 个新项目。
4. 跑 `bash scripts/spa_visual_check.sh http://127.0.0.1:8000/expression/ --wait '#project-list .proj-check'`（390/768/1440 全 PASS 再继续，见 MAINTENANCE §九 `:778+`）。

### Phase 3 — 提交 + 部署（0.2 人日）

1. `git commit`（建议 2 个 commit：DDL/SQL 文档 + 代码；代码 message 例：`feat(expression): per-project unit (TPM/FPKM/TE) for heat translatome dataset`）。
2. 服务器：`git pull`（webhook 只 pull 不重启，`MAINTENANCE.md:65-78`）→ `sudo systemctl restart wheatomics-api`。
3. 静态文件无需 Apache 改动（`/expression` 与 `/api` 早已 ProxyPass，`main.py:194`、`MAINTENANCE.md:34-53`）；但前端 HTML 有浏览器缓存风险（§3.5），验收时强刷。

### Phase 4 — 元数据上线（0.2 人日，**一插即对外**）

1. 备份 `project_meta`（§7.2 前两行；沿用 `project_meta_bak_YYYYMMDD` 命名，与 10-26/10-28/10-29 三次操作一致）。
2. `START TRANSACTION; INSERT 3 行; COMMIT;`。
3. 立即跑 §9 API/UI 验收；有问题 `DELETE FROM project_meta WHERE table_name IN (...)` 即回退（数据表可留）。

### Phase 5 — 收尾（0.2 人日）

1. 截图存证（桌面/移动 2 个宽度 + 3 个项目结果块 + GeneHub 基因页下拉）。
2. 记录到仓库：把 DDL/INSERT/导入脚本放 `scripts/sql/` 或本计划目录，避免重演「线上元数据无版本化」问题。
3. 如加 unit：更新 `/agent.html` MCP 工具说明（可选）。

---

## 9. 验收清单（可直接抄成 checklist）

### 9.1 SQL / DB

```sql
-- 1) 表结构：必须恰好 1 个字符列 + 6 个数值列，列名/顺序 = labels
SELECT TABLE_NAME, ORDINAL_POSITION, COLUMN_NAME, DATA_TYPE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA='gene_expression' AND TABLE_NAME LIKE 'CS_grain_heat%'
ORDER BY TABLE_NAME, ORDINAL_POSITION;
-- 期望：每表 7 行；第 1 行 varchar(GeneID)，其余 double；无 IWGSCV1_1_id 等额外数值列

-- 2) 行数/唯一性/LC
SELECT 'RNA' t, COUNT(*) n, COUNT(DISTINCT GeneID) uniq, SUM(GeneID LIKE '%LC') lc FROM CS_grain_heat_RNAseq_FPKM_tbl
UNION ALL SELECT 'Ribo', COUNT(*), COUNT(DISTINCT GeneID), SUM(GeneID LIKE '%LC') FROM CS_grain_heat_RiboSeq_FPKM_tbl
UNION ALL SELECT 'TE',   COUNT(*), COUNT(DISTINCT GeneID), SUM(GeneID LIKE '%LC') FROM CS_grain_heat_TE_tbl;
-- 期望：n = uniq = 映射成功数（待填），无重复；LC 数接近 10,567（取决于映射）

-- 3) 非数值污染 / 极端值 / 空值
SELECT SUM(GeneID NOT LIKE 'TraesCS%02G%') AS bad_id FROM CS_grain_heat_RNAseq_FPKM_tbl;
SELECT MAX(`5DAA_CK`) mx, MIN(`5DAA_CK`) mn FROM CS_grain_heat_RNAseq_FPKM_tbl;
SELECT SUM(`5DAA_CK` IS NULL) nulls FROM CS_grain_heat_TE_tbl;  -- NA 预期非 0

-- 4) labels 数与列数对齐（关键！）
SELECT m.table_name, JSON_LENGTH(m.labels) n_labels,
       (SELECT COUNT(*) FROM information_schema.COLUMNS c
        WHERE c.TABLE_SCHEMA='gene_expression' AND c.TABLE_NAME=m.table_name
          AND c.DATA_TYPE IN ('double','float','decimal','int','bigint')) n_value_cols
FROM project_meta m WHERE m.table_name LIKE 'CS_grain_heat%';
-- 期望：n_labels = n_value_cols = 6

-- 5) 元数据字段
SELECT table_name, group_name, subgroup, sub_subgroup, unit, has_std_table
FROM project_meta WHERE table_name LIKE 'CS_grain_heat%';
-- 期望：wheat abiotic stresses / Temperature stress / '' / FPKM,FPKM,TE / 0
```

### 9.2 API（线上/本机 curl）

```bash
B=https://wheatomics.sdau.edu.cn
# a) 目录：项目数 334→337，3 项出现在 Temperature stress 下
curl -s $B/api/expression/projects | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print(sum(len(ss['projects']) for g in d['groups'] for sg in g['subgroups'] for ss in sg['sub_subgroups']));print([p['id'] for p in d['projects'] if p['id'].startswith('CS_grain_heat')])"
# b) 查询：每项目 6 点；02G=03G 输入都能命中
for p in CS_grain_heat_RNAseq_FPKM_tbl CS_grain_heat_RiboSeq_FPKM_tbl CS_grain_heat_TE_tbl; do
  curl -s "$B/api/expression/query?gene_ids=TraesCS5A02G391700&project=$p" | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print(d['project'],d['genes_found'],len(d['results'][0]['points']))"
done
curl -s "$B/api/expression/query?gene_ids=TraesCS5A03G0935400&project=CS_grain_heat_RNAseq_FPKM_tbl" | grep -o '"genes_converted":{[^}]*}'
# c) 不存在的项目仍 400；表缺失仍 503（不回归）
curl -s -o /dev/null -w '%{http_code}\n' "$B/api/expression/query?gene_ids=TraesCS5A02G391700&project=nope_tbl"   # 400
```

### 9.3 页面 / 脚本

- [ ] `/expression/`：3 个新项目出现在 `wheat abiotic stresses → Temperature stress`；勾选 3 个 → 3 个结果块、每块 6 个点、无 SD 列；y 轴/tooltip 单位分别 FPKM / FPKM / TE（方案 B）或都是 TPM（方案 A，记录为已知缺陷）。
- [ ] `/GeneHub/gene.html?gene=TraesCS5A02G391700`：表达下拉出现 3 项，选中后表格 6 行、无报错。
- [ ] MCP：`list_expression_projects`（compact）包含 3 项；`query_expression` 返回 6 点（可跑 `python3 scripts/mcp_selftest.py`，如环境允许）。
- [ ] `bash scripts/spa_visual_check.sh https://wheatomics.sdau.edu.cn/expression/ --label expr-translatome --fill '#gene-input=TraesCS5A02G391700' --wait '#project-list .proj-check'`（8 宽度；选择器需手动勾选，可加 `--click`）。
- [ ] `python3 scripts/audit_project_labels.py --csv /tmp/label_audit_$(date +%F).csv`（服务器上跑）：3 个新项目应为 `OK`（labels 数与列数一致），不得 `MISMATCH`。
- [ ] 页面缓存验证：`curl -s $B/expression/index.html | grep -c "TPM"` 与本地文件一致（部署一致性检查）。

### 9.4 数据质量（数据侧）

- [ ] RNA/Ribo None 值=0、TE NULL 数=文件 NA 数（`NA` 不得以字符串入库）。
- [ ] 每列和与 xlsx 抽查一致（例如 `RNA_5d_CK` 列和 670,200 量级；若用 02G 映射后行数减少，列和应等比例核对）。
- [ ] 抽 3 个基因（普通/LC/`TraesCSU03G`）在 3 张表的 6 个值与 xlsx 逐一对上（浮点误差 <1e-6）。

---

## 10. 回滚清单

| 层 | 操作 | 影响 |
|---|---|---|
| 元数据（最快） | `DELETE FROM project_meta WHERE table_name IN ('CS_grain_heat_RNAseq_FPKM_tbl','CS_grain_heat_RiboSeq_FPKM_tbl','CS_grain_heat_TE_tbl');` | 立即从选择器/API/GeneHub/MCP 消失；无需重启 |
| 元数据（完整） | `DROP TABLE IF EXISTS project_meta_bak_20261111;` 后按备份恢复，或 `CREATE TABLE project_meta_restore LIKE project_meta_bak_20261111; INSERT ... SELECT...` | 恢复到上线前 334 行状态 |
| 数据表 | `DROP TABLE IF EXISTS CS_grain_heat_RNAseq_FPKM_tbl, CS_grain_heat_RiboSeq_FPKM_tbl, CS_grain_heat_TE_tbl;` | 释放存储；不影响其他项目 |
| DDL（unit） | 保留即可（默认 TPM，老代码不读）；若必须回退：`ALTER TABLE project_meta DROP COLUMN unit;` | 需先回退读取 unit 的代码 |
| 代码 | `git revert <unit commit>` → `sudo systemctl restart wheatomics-api` | 前端缺省回 TPM；如果前端已加 `unit \|\| 'TPM'` 兜底，可只回退后端 |
| 前端 | 强刷缓存/回退静态文件 | `/expression/` 有浏览器缓存风险（§3.5） |

**回滚演练建议**：Phase 4 完成后再做一次「删元数据 → 确认 334 项 → 重新 INSERT」的 2 分钟演练，确保脚本可重放。

---

## 11. 若走方案 C：独立 SPA 的完整流程（仓库内可复用模板）

仓库对「新增一个 SPA」有明确 4 步（`MAINTENANCE.md:9-64`），另外还有导航/落地页/文档三处配套：

### 第 1 步 — 建静态页

```bash
mkdir -p app/static/translatome
cp app/static/_v2/template.html app/static/translatome/index.html
```

* 模板：`app/static/_v2/template.html`（53 行，注释明确写「Reference skeleton for a converted WheatOmics SPA」）。**只写内容区**，header/footer 由 `/api/v2shell/shell.js` 注入（`<div id="v2-shell-header">`/`<div id="v2-shell-footer">`），不要复制头尾（`MAINTENANCE.md:19`）。
* 必须有 `<meta charset>`、`<meta name="viewport">`、`<title>Translatome | WheatOmics 2.0</title>`、`/favicon.ico`、`/api/v2shell/shell.css`（样式规范 `MAINTENANCE.md` §七）。
* 现成可抄的同类页：`app/static/expression/index.html`（Highcharts + 表格 + citation）、`app/static/genes/`、`app/static/coexpression/`。

### 第 2 步 — FastAPI 静态挂载

在 `main.py` 的 mount 区块（当前 `:194-225`）加一行：

```python
app.mount("/translatome", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "translatome", html=True), name="translatome")
```

⚠️ 目录名必须与 `app/static/` 下实际目录完全一致，否则启动报 `RuntimeError: Directory does not exist`（`MAINTENANCE.md:32`）。

### 第 3 步 — Apache 反向代理（SSL 和非 SSL 两个文件都要）

```apache
ProxyPass        /translatome http://127.0.0.1:8000/translatome
ProxyPassReverse /translatome http://127.0.0.1:8000/translatome
```

```bash
sudo sed -i '/ProxyPassReverse \/interval/a\    ProxyPass /translatome http://127.0.0.1:8000/translatome\n    ProxyPassReverse /translatome http://127.0.0.1:8000/translatome' /etc/apache2/sites-enabled/000-default-ssl.conf
sudo sed -i '/ProxyPassReverse \/interval/a\    ProxyPass /translatome http://127.0.0.1:8000/translatome\n    ProxyPassReverse /translatome http://127.0.0.1:8000/translatome' /etc/apache2/sites-enabled/000-default.conf
sudo apachectl restart
```

（命令与锚点来自 `MAINTENANCE.md:34-53`；常见故障：本地 200、线上 404 = 少了 ProxyPass，`MAINTENANCE.md:236-243`。Apache 配置文件在服务器上，仓库不含。）

### 第 4 步 — 重启 API

```bash
sudo systemctl restart wheatomics-api
sudo systemctl status wheatomics-api
sudo journalctl -u wheatomics-api -f
```

（`MAINTENANCE.md:55-78`；webhook 只 `git pull` 不重启，**改 Python 必须手动重启**。）

### 配套：导航 / 首页 / API / MCP / 文档 / 验收

| 项 | 做法 |
|---|---|
| 全站菜单 | 菜单由 `app/static/_v2/shell.js` 的 `HEADER` 提供，**源文件**是 `app/static/blast2/index.html`（`scripts/extract_v2_shell.py:1-20,26`）。改 canonical 页面后在仓库跑 `python3 scripts/extract_v2_shell.py` 重新生成 `shell.css/js`，再提交（不要手改 shell.js）。注意 `MAINTENANCE.md:136-138` 的「22 份副本」历史教训——新页面一律用共享 shell，不要再复制头尾。 |
| 首页（docroot） | `/var/www/html/index.html` 与 `/V2.0/index.html` **不在仓库**，由服务器脚本打补丁：`scripts/update_v2_home_nav.py`（`:1-40`，锚点式 patch，带备份/`--check`/`--dry-run`）；工具卡片用 `scripts/add_homepage_cards.py`（`:1-30`）。新增模块时两者都要扩展/执行。 |
| API | 新 router `app/api/routers/translatome.py`；在 `app/api/routers/__init__.py` 导入、`main.py:271-300` 的 `for router in [...]` 里注册（`prefix=settings.API_PREFIX` = `/api`）；schema 放 `app/schemas/`。参考 `MAINTENANCE.md` §二。 |
| MCP | `app/mcp/tool_specs.py` 加 `TOOL_SPECS` 条目 + `app/mcp/wheatomics_tools.py` 的 `_SYNC_TOOLS` 注册；同步 `app/static/docpages/agent.html` 的工具表与「N tools」计数（`MAINTENANCE.md:211`）。 |
| 文档页 | `/agent.html` 是 docroot 页面，源在 `app/static/docpages/`，用 `python3 scripts/deploy_doc_pages.py` 发布（带备份/`--check`/`--dry-run`，见 `app/static/docpages/README.md`）。 |
| 验收 | `bash scripts/spa_visual_check.sh http://127.0.0.1:8000/translatome/ --widths 360,768,1024,1440`（工具说明 `scripts/spa_visual_check.sh:1-33`；必跑 390/768/1440，`MAINTENANCE.md:778+`）。 |

**方案 C 的工作量拆分**：前端（含 3 面板/NA/log/阈值/下载）2–3 人日；后端 router/schema/查询 1 人日；挂载/Apache/导航/首页/文档/MCP 1–1.5 人日；数据导入（03G 直存，可省映射）0.5–1 人日；验收/回归 1 人日 → **合计 5–8 人日**。

---

## 12. 风险与待确认

### 12.1 风险

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| R1 | **03G→02G 映射覆盖率不足**（10,567 LC 中未知比例无 v2 同源） | 高 | Phase 0 先量化；≥98% 走 B，否则 C 或补映射；未命中清单必须交付 |
| R1b | **再发布授权**：GB 2025 为 CC BY-NC-ND 4.0、PlCell 2023 为 © ASPB 非 OA | 中 | 上架前由马老师确认许可/致谢；citation 写清两篇来源（`PAPER_CONTEXT.md` §0/§5/§8） |
| R2 | **TPM 误标**（若走方案 A 就上线） | 高 | 走方案 B；对外文案审核 |
| R3 | **TE NA 显示 0** + **TE 极端值压轴** | 中 | citation/说明写明；数据侧截断到 p99 并保留全量下载；或走 C |
| R4 | ~~citation 无文献~~ → **已确认**：GB 2025（PMID 41214722）+ PlCell 2023（PMID 36905284），PRJNA1135409 / PRJNA871371；剩余风险是**再发布授权**（见 R1b） | 中 | citation 用 §7.2 已给真实串（3 链接安全版）；先确认作者许可 |
| R5 | **浏览器缓存**：`/expression/index.html` 无 no-cache，前端改动后用户看旧版 | 中 | 上线后强刷验证；或把 `/expression/` 加进 `main.py:173-193` |
| R6 | **元数据无版本化**（本次再手工 INSERT） | 中 | 把 DDL/INSERT/导入脚本提交进仓库（`scripts/sql/` 或本目录），下次可复现 |
| R7 | 生产 DB 权限：`wheatomics_user` 是否有 `gene_expression` 的 CREATE | 低 | 上线前 `SHOW GRANTS`；无权限则找 DBA/运维（历史脚本曾用该账号 `CREATE TABLE ... LIKE` 备份） |
| R8 | 上线窗口/回滚：INSERT 即对外生效 | 低 | 先在 Phase 1 建表灌数（不可见），最后一步才 INSERT；备份表可秒回 |
| R9 | 60,125 行只覆盖部分基因，用户会查不到 | 低 | display_name/citation 写明「仅 60,125 个检出基因」 |
| R10 | 18 列若做成 1 个项目会混轴 | — | 3 个项目已规避 |

### 12.2 需要马老师/数据组拍板

1. **方案**：接受方案 B（1.5–2 人日，含 `app/` 小改 + unit 字段）还是先方案 A（零代码、页面标 TPM）？
2. **TE 处理**：TE 是否进 expression 页（接受 RNA FPKM < 0.2 的 NA 显示为 0、极端值截断）；还是要等方案 C 的独立 TE 视图？
3. **文献与 accession**：已由 `PAPER_CONTEXT.md` 核实为 Chen et al. 2025 Genome Biol（PMID 41214722）+ Guo et al. 2023 Plant Cell（PMID 36905284），accession PRJNA1135409 / PRJNA871371；请确认 **授权（CC BY-NC-ND / 非 OA 再发布）** 与最终 citation 文案。
4. **基因映射**：03G→02G 映射未命中的基因是丢弃、还是要求平台支持 03G 原生表（→ 方案 C）？
5. **分组位置**：`wheat abiotic stresses → Temperature stress` 是否认可（备选 `developmental tissues → Seed / Grain`）？
6. **命名/标签**：3 个项目名与 6 个短标签（`5DAA_CK` …）是否认可；TE NA 的展示文案。
7. **是否顺手修掉现有 2 个已确认非 TPM 项目的 unit 标注**（`PRJEB51827_tpm`、`PRJNA325489_tbl`）。

---

## 附录 A：证据索引

| 结论 | 证据位置 |
|---|---|
| 项目校验动态来自 `project_meta` | `app/api/routers/expression.py:114-120` |
| 03G/01G→02G 转换（批量 SQL + 字符串兜底） | `app/api/routers/expression.py:129-173` |
| 表结构探测、缺失表 503、labels 兜底 | `app/api/routers/expression.py:175-226` |
| `_std` 可选、hardcode `GeneID` | `app/api/routers/expression.py:236-241` |
| labels/值按位置 zip + 长度保护 | `app/api/routers/expression.py:245-268` |
| NULL→0.0 | `app/api/routers/expression.py:250` |
| 项目目录/树/分组顺序/unit 缺失 | `app/services/expression_catalog.py:12-27,30-59,62-137,140-155` |
| 响应 schema（无 unit） | `app/schemas/expression.py:8-31` |
| 线上 `project_meta` DDL（含 subgroup/sub_subgroup） | `wheatomics_results/audit/fix_verification/project_meta_bak_20261028_b.sql:25-38` |
| 仓库旧快照只 69 行、无 ALTER | `init_project_meta.sql:13-25,27-29`；`git log -- init_project_meta.sql` |
| 现有表 266,849 行、`GeneID text` + double、14 缺表/4 只剩 `_std` | `wheatomics_results/audit/server_verification_findings.md:16,23-24,84` |
| 单位 TPM 列和判定、2 个非 TPM | `wheatomics_results/audit/server_verification_findings.md` §4 |
| 页面硬编码 TPM（5 处） | `app/static/expression/index.html:83,86,631,675,840` |
| 标签容量/重叠加实测 | `wheatomics_results/audit/page_findings.md:21,48,51,53,128-133,169-177` |
| 层级重复/`\r`/描述缺陷 | `wheatomics_results/audit/metadata_findings.md:24-26,122-124` |
| GeneHub 基因页动态加载 expression | `app/static/docpages/gene.html:138-139,396-440` |
| 旧基因页硬编码 69 项、302 跳新页 | `app/static/docpages/geneDetail.py:19-29,178-237`；`cgi-py-RawScript/gene_expression.py:61+` |
| KnownGene 详情页无表达入口 | `app/static/genes/detail.html`（`grep -c expression` = 0） |
| MCP expression 工具 | `app/mcp/tool_specs.py:213-240`；`app/mcp/wheatomics_tools.py:106-109,216-236` |
| SPA 4 步/Apache/重启/多宽度验收 | `MAINTENANCE.md:9-64,34-53,55-78,236-243,778+` |
| 共享 shell 生成方式/菜单单源 | `scripts/extract_v2_shell.py:1-20,26`；`app/static/_v2/shell.js`；`MAINTENANCE.md:136-138` |
| 首页/文档页发布脚本 | `scripts/update_v2_home_nav.py:1-40`；`scripts/deploy_doc_pages.py`；`app/static/docpages/README.md` |
| 多宽度检查用法 | `scripts/spa_visual_check.sh:1-33` |
| 一次性 `project_meta` 维护先例（备份/dry-run/apply/rollback） | `~/Desktop/markdown/陈甜甜/WheatOmics_expression审计_2026-10-26/09_元数据清理与上线记录/project_meta_cleanup.py`、`10_发育组织重分组_2026-10-28/dev_group_regroup.py` |
| 本数据文件结构（60,125 × 18、全 03G、10,567 LC、TE=Ribo/RNA、NA 统计） | 本地 xlsx `Table S1` 只读抽查（2026-11-11，脚本输出见正文 §4） |
| 数据溯源 = GB 2025 补充表 S1（逐格一致）、CK/HS 两批原始数据 | 同目录 `DATA_AUDIT.md` §2.1–§2.2 |
| 论文题录/授权/推荐 citation 串 | 同目录 `PAPER_CONTEXT.md` §1、§5、§8.2 |
| 线上 334 项目/5 组/49 子组/610KB | `curl /api/expression/projects`（2026-11-11 09:25 CST） |

## 附录 B：线上 API 实测片段

```json
// GET /api/expression/projects （截断）
{"success":true,"message":"ok","timestamp":"2026-11-11T01:25:07Z",
 "data":{"projects":[{"id":"ABA_JA_6BA_DMSO3h_mean_tbl","description":"Fielder - ABA/6-BA/SA hormone-treated leaf",
   "categories":["DMSO3h","6BA3h","ABA3h","SA3h"],"citation":"Description: Publication:...","group":"wheat abiotic stresses",
   "subgroup":"Chemical / exogenous treatment","sub_subgroup":""}, ...],
  "groups":[{"name":"wheat abiotic stresses","subgroups":[{"name":"Temperature stress","sub_subgroups":[{"name":"","projects":[...]}]}, ...]}]}}

// GET /api/expression/query?gene_ids=TraesCS5A03G0935400&project=PRJEB5314_paired_tbl （截断）
{"success":true,"data":{"project":"PRJEB5314_paired_tbl","genes_found":1,"genes_not_found":[],
 "genes_converted":{"TraesCS5A03G0935400":"TraesCS5A02G391700"},
 "results":[{"gene_id":"TraesCS5A02G391700","project":"PRJEB5314_paired_tbl",
   "points":[{"label":"root_Z10","value":0.020154,"std":0.020154,"error_bar":[0.0,0.04]}, ...]}]}}
```

---

*本报告由仓库侧审计产出，未修改 `app/`、`main.py` 或任何数据库；所有生产写入步骤均需在服务器上由有权限账号执行，并先备份。*
