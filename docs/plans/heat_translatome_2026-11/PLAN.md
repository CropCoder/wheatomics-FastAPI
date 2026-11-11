# 热胁迫小麦籽粒 RNA-seq / Ribo-seq / TE 数据上架 WheatOmics：建议与实施计划

- 日期：2026-11-11
- 数据：`/Users/mashengwei/Desktop/markdown/陈甜甜/5_10_15DAA对照和热胁迫小麦籽粒的转录水平RNA_翻译水平Ribo_和翻译效率TE.xlsx`
- 关联报告：同目录 `DATA_AUDIT.md`（数据体检与溯源）、`PAPER_CONTEXT.md`（论文核实）、`REPO_INTEGRATION.md`（仓库侧集成审计）
- 一句话结论：**数据值得上，但应先按"已发表数据集整理"而不是"我们重新分析"来定位；推荐先做方案 B（约 2 人日，立即接入全站现有入口），再视需求追加独立 translatome 页面（约 4–6 人日）。**

---

## 0. 推荐结论（先看这一页）

| 决策点 | 建议 |
|---|---|
| **数据身份** | 这份 xlsx 与 Genome Biology 2025 补充表 S1 **逐格一致**（60,125 行 × 18 数值列；仅删了 `Description` 列和分组表头行）。对外应写"curated from Chen et al. 2025 (Genome Biol) Supplementary Table S1；对照数据来自 Guo et al. 2023 (Plant Cell)"，**不要写成 WheatOmics 再分析**（除非另做一套从 SRA 重新定量的矩阵）。 |
| **上架位置** | `wheat abiotic stresses → Temperature stress`（该子组现有 17 个项目；备选：`wheat developmental tissues → Seed / Grain`）。 |
| **呈现粒度** | **3 个项目 × 6 个点**：`RNA-seq FPKM`、`Ribo-seq FPKM`、`TE` 各一个项目；**不要**做成 1 个项目 18 个点（RNA/Ribo/TE 单位不同、量级差 3–4 个数量级、且前端没有分组能力）。 |
| **推荐路线** | **方案 B**：3 张 6 列表 + `project_meta` 3 行 + 新增 `project_meta.unit` 字段 + 前端 5 处单位绑定。现有 expression 页 / API / GeneHub 基因页 / MCP **全部自动生效**，不需要新路由、不需要改 Apache。 |
| **Phase 2.5（已完成 2026-11-11）** | 底层升级为 **registry + manifest 驱动**：新增数据集 = 数据文件夹 + manifest + registry 一行，无需改代码；契约测试用临时假数据集验证，并通过真实数据回归。**`.gz` 资产移出仓库**，由 `TRANSLATOME_DATA_DIR`（默认 `/var/www/data/translatome`）指向服务器数据目录；仓库仅留 registry/manifest/脚本。 |
| **生产上线（已完成 2026-11-11）** | `/translatome/` 页面 + API + MCP 已部署到生产：Apache `/translatome` 代理、API 重启、资产 `/var/www/data/translatome/`、`/agent.html` 与首页入口同步。线上验证与回滚见 `DEPLOYMENT_2026-11-11.md`。 |
| **Phase 2（本次已实现原型）** | 独立 `/translatome/` 页面 + `/api/translatome/*`：多基因查询（**02G/03G 双 ID**）、TE 保真（null 不显示为 0）、DTG/DEG 检索、论文补充表外链（页面不展示下载卡）、作者 browser/GeneHub 外链、MCP 3 个工具（含数据集清单）。本地已跑通并完成 390–1440 宽度视觉验收；详见 `PHASE2_IMPLEMENTATION.md`。生产部署还差 Apache ProxyPass、首页/导航发布与作者授权。 |
| **必须先解决** | ① 通讯作者授权（GB 2025 为 CC BY-NC-ND 4.0；PlCell 非 OA）② 全量 03G→02G 映射审计（已完成：60,125/60,125） ③ TE 缺失值/极端值展示口径 ④ 引用字符串与数据集说明。 |
| **总工作量** | 方案 B：约 **2 人日**（含映射审计、建表、代码、验收）。Phase 2 原型：**约 1 人日（已完成）**；生产部署与增强另计。 |

---

## 1. 这次要上的是什么

| 维度 | 内容 |
|---|---|
| 材料 | 中国春（Chinese Spring）发育籽粒，花后 5 / 10 / 15 天（DAA） |
| 处理 | 正常（CK）vs **42 °C 热胁迫 1 h 后立即取样**（HS） |
| 测定 | RNA-seq FPKM（转录水平）、Ribo-seq FPKM（翻译水平）、TE = 平均 Ribo FPKM / 平均 RNA FPKM（翻译效率） |
| 规模 | 60,125 个基因（IWGSC RefSeq v2.1 / 03G ID；含 10,567 个低置信 LC、529 个 chrUn `TraesCSU` 基因）× 18 个数值列 |
| 重复 | RNA n=3、Ribo n=2（CK 与 HS 相同）；表内是**条件均值**，无 per-replicate、无 SD |
| 来源 | **CK**：Guo et al. 2023 *Plant Cell* 35(6):1848–1867（PMID 36905284，DOI 10.1093/plcell/koad075，PRJNA871371）；**HS**：Chen et al. 2025 *Genome Biology* 26(1):382（PMID 41214722，DOI 10.1186/s13059-025-03848-4，PRJNA1135409）。表本身 = 后者补充表 S1。 |
| 配套结果 | 同篇论文补充表：Table S2 = 21,964 个 DEG（RNA/Ribo 六比较）；Table S3 = 11,343 个差异翻译基因 DTG（8 个共翻译聚类）；Table S4 = 7,681 个新注释 ORF |

**为什么值得上**：截至 2026-11-11，线上 `gene_expression` 共 **334 个表达项目**，其中没有任何 Ribo-seq / translatome 项目；grain 相关的 30 个项目全是 RNA-level。本数据集可以补上"翻译水平"这一层，而且同时带发育阶段和热胁迫两个维度，加上已发表的 DEG/DTG 表，足够支撑一个独立小模块，而不是简单再挂一个表达谱。

**数据本身的三个要点**（详见 `DATA_AUDIT.md`）：

1. **TE = Ribo/RNA 的原始比值**，只在 RNA FPKM ≥ 0.2 时计算，否则为 `NA`（六列 NA 4,658–6,645 个，占 7.8–11.1%）；Ribo=0 时 TE=0。**NA ≠ 0**，这是展示层最大的坑。
2. TE 极端值最大 9,120（RNA 接近 0.2 时比值爆炸），每列 TE>10 的基因有 419–650 个；直接画等距 y 轴会被极端值压扁。
3. 网站现有表达页把 y 轴/文案硬编码为 **TPM**（5 处），而本数据是 **FPKM + TE**；不处理单位就上线 = 对外标注错误。

---

## 2. 网站侧现状与可挂接点（已实测）

| 触点 | 现状 | 上 3 个项目后 |
|---|---|---|
| 数据模型 | 一个项目 = 一张宽表：`GeneID`（文本）+ N 个 double 样本列；`project_meta` 一行描述，`labels` JSON 与数值列**按位置**配对；`_std` 表可选 | 建 3 张 7 列表 + 3 行 meta 即可 |
| 基因 ID | 查询链路先把 01G/03G 批量转 02G 再查（转换表 `Genehub_DB.GenePageIWGSCv1_table`）；线上实测 03G→02G 正常 | **新表必须以 02G 为键**；数据侧先做映射 |
| `/expression/` 页面 | 自动读取全部项目；18 个标签完全可读（10–20 个点是常态，>70 才不可读）；无 RNA/Ribo/TE 分组能力；TPM 硬编码 5 处 | 自动出现 3 项；需加 `unit` 才能正确标单位 |
| `/api/expression/*` | 每次请求现查 `project_meta`；插元数据立即生效，无需重启 | 自动生效 |
| GeneHub 基因页 `/GeneHub/gene.html` | 表达下拉框动态加载全部项目，表格展示 Stage/tissue/Value/Std | **自动出现**，无需改代码 |
| MCP | `list_expression_projects` / `query_expression` 走同一 API | **自动出现** |
| KnownGene 页 `app/static/genes/` | 没有表达入口 | 不需要动（若要深链到表达页，需给 expression 页加 `?gene=` 支持，0.5 人日，可选） |
| 旧版 `/cgi-bin/geneDetail.py` | 硬编码 69 项，但已 302 跳新版 | 不碰 |
| JBrowse | 无表达量轨道支持 | 本期不做（需服务器侧 BigWig，3 人日+） |
| 共表达 | 数据库白名单硬编码 | 本期不做（每层仅 6 个样本，PCC 样本量不足） |

> 详细证据见 `REPO_INTEGRATION.md` §2–§5、附录 A（file:line 级）。

---

## 3. 上架前必须先拍板的 3 个口径

### 3.1 口径 A（推荐）：已发表数据集的整理与检索

- 定位：把 GB 2025 的 Table S1/S2/S3 以结构化方式接入平台，提供查询、作图、下载；
- 引用：写清两篇论文与两个 BioProject；页面标注 "curated from published supplementary data"；
- 工作量小、风险低、可立即上线；
- 授权：CC BY-NC-ND 4.0 允许非商业共享（署名、不改编）；**转 ID / 算 ΔTE 属于"改编"灰区**，正式对外前给通讯作者（彭惠茹，penghuiru@cau.edu.cn）发一封确认邮件（模板见附录 B）。

### 3.2 口径 B：作为 WheatOmics 的再分析数据集

- 需要：从 PRJNA871371 + PRJNA1135409 重新比对/定量（STAR + FeatureCounts + DESeq2 + RiboDiff），产出 per-replicate 矩阵与可复现流程；
- 优点：可以自证数据来源、可以加 SD/误差棒、可以做自己的差异分析；
- 成本：**至少 1–2 周**（12 个 RNA 文库 + 12 个 Ribo 文库，含质控与验证），且结果会和论文表不完全一致（反而增加解释成本）；
- 建议：**除非马老师明确要"我们的再分析"品牌，否则不要走 B**；论文已有成熟的定量与差异结果，直接引用更稳。

### 3.3 呈现粒度（两个子决策）

1. **3 个项目 vs 1 个项目**：选 3 个项目（RNA/Ribo/TE 各自 y 轴与单位），见 §0；
2. **是否做独立页面**：先做方案 B 接入现有 expression 模块；若未来还要接其他 Ribo-seq 数据集、或需要 TE 专属视图（NA 保真、log 轴、DTG 检索），再上方案 C。

---

## 4. 推荐路线图（三期）

### Phase 1（推荐，约 2 人日）：方案 B — 3 个 expression 项目 + 单位字段

| 步骤 | 内容 | 产出 | 工时 |
|---|---|---|---|
| 1.1 授权与文案 | 给通讯作者发确认邮件；定 3 个 `display_name`、citation 串、数据集说明（含 NA/无重复/仅 60,125 基因） | 邮件、文案 | 0.2 |
| 1.2 映射审计 | **已完成**：GeneHub interval API 全量拉取，60,125/60,125 映射，0 缺失/0 冲突；脚本与报告已入库 | `scripts/heat_translatome/` + `build_report.json` | ✅ |
| 1.3 数据打包 | 生成 3 张 02G 键 CSV（RNA/Ribo/TE；TE 的 `NA` 保持 NULL）+ 下载包（Table S1/S2/S3 + README + md5） | CSV ×3、下载包 | 0.3 |
| 1.4 建表灌数 | 3 张 7 列表（`GeneID VARCHAR(50) PRIMARY KEY` + 6 个 double），灌数、SQL 验收 | 线上表 | 0.3 |
| 1.5 `unit` 字段 + 代码 | `ALTER TABLE project_meta ADD COLUMN unit ...`；`expression_catalog.py` 透出 unit；`app/static/expression/index.html` 5 处按项目 unit 渲染（缺省回落 TPM）；可选：schema 返回 unit、MCP 描述补一句 | 代码 diff（约 30 行） | 0.5 |
| 1.6 插入元数据 | 备份 `project_meta` → 事务插入 3 行 → 立即 API/页面验收 | 3 行 meta | 0.1 |
| 1.7 验收与回滚演练 | 按 §6 清单逐项验收；删 meta 再插一遍验证可重放 | 验收记录 | 0.3 |

**Phase 1 完成后的效果**：`/expression/` 选择器多出 3 个项目；任意基因（02G/03G 均可）能查 6 个条件点；GeneHub 基因页表达下拉自动出现；MCP 可直接查询；下载包可下载。TE 的 NA 在现有页面会显示 0（**必须在 citation/说明里写清**），极端值会压轴（**数据侧可截断 p99 用于展示、下载保留原值，或加一句说明；建议 Phase 2 再用 log 轴/专用视图解决**）。

### Phase 2（原型已完成，2026-11-11；生产部署待做）：方案 C — 独立 `/translatome/` 页面

> 扩展性：**Phase 2.5 已完成（2026-11-11）**，service/API/前端已改为 registry + manifest 驱动；之后新数据 = 数据文件夹 + manifest + registry 一行，无需改代码（契约测试见 `scripts/heat_translatome/test_registry_contract.py`）。详见 `PHASE2_EXTENSIBILITY.md`。

> 实现状态：本次已按方案 C 做出可运行原型（静态数据资产版，零 DB 依赖）：`/api/translatome/*` 7 个端点 + `/translatome/` 页面 + 双 ID + DTG/DEG 检索 + MCP 2 工具；本地 API/页面/多宽度验收均已通过。详见 `PHASE2_IMPLEMENTATION.md`。以下保留原设计说明，便于后续扩展。

目标：把 TE 的语义做对，并让 DEG/DTG 可检索。建议只在"值得做成平台长期模块"时做：

- 新路由 `/api/translatome/*`：
  - `GET /api/translatome/projects`：项目/样本元数据 + citation + 下载链接；
  - `GET /api/translatome/query?gene_ids=...&stage=5|10|15`：返回 RNA/Ribo/TE（CK/HS）、log2FC、Δlog2TE（**保留 null**）；
  - `GET /api/translatome/dtgs?stage=&direction=&cluster=&gene=&limit=&offset=`：查 Table S3 的 11,343 个 DTG；
  - `GET /api/translatome/degs?comparison=&gene=`：查 Table S2 的 21,964 个 DEG；
  - `GET /api/translatome/download?dataset=t1|t2|t3&format=tsv`。
- 新 SPA `/translatome/`：
  - 基因搜索（02G/03G/symbol，支持逗号多基因）；
  - 单基因卡片：RNA CK/HS、Ribo CK/HS、TE CK/HS（NA 显示 "n.a."），ΔRNA/ΔRibo/ΔTE；
  - 多基因热图/表格；
  - DTG/DEG 表（按阶段、方向、cluster 过滤）+ 下载；
  - 样本元数据、citation、PRJNA 链接、作者自建 translatome browser 外链；
  - 与基因页互链（expression 页加 `?gene=`，基因页加"Translatome"按钮）。
- 新表（建议）：`heat_translatome_dtg_tbl`、`heat_translatome_deg_tbl`、`heat_translatome_gene_meta_tbl`（symbol↔ID）；或先把 S2/S3 做成静态 TSV 下载（更省）。
- 导航/首页/文档/MCP：按仓库 SPA 4 步流程（`main.py` mount、Apache ProxyPass、`shell.js` 菜单、`update_v2_home_nav.py`、`deploy_doc_pages.py`、MCP `tool_specs.py`）。

### Phase 3（可选，1–2 周+）：延伸

- per-replicate 再定量（若要做误差棒/自有差异分析）；
- uORF/dORF/lORF 浏览器（Table S4/S6/S8）；
- JBrowse RNA/Ribo 覆盖度轨道（需 BigWig）；
- 共表达/翻译调控网络整合（样本量不足，需先有更多 Ribo 数据）。

---

## 5. 技术方案（Phase 1 落地）

### 5.1 数据准备

输入：用户 xlsx（= GB 2025 Table S1）。输出建议：

```
heat_translatome_2026-11/
├── genes_03g.txt                 # 60,125 个 03G ID
├── mapping_03g_02g.tsv           # 03G, 02G, 是否LC, 是否chrUn, 映射来源
├── RNA_FPKM_6col.csv             # GeneID(02G) + 6 个 RNA 列
├── Ribo_FPKM_6col.csv            # GeneID(02G) + 6 个 Ribo 列
├── TE_6col.csv                   # GeneID(02G) + 6 个 TE 列（NA→空/NULL）
├── tableS1_annotated.tsv         # 18 列 + 03G/02G/Description/LC 标记（下载用）
├── tableS2_DEG.tsv / tableS3_DTG.tsv  # 论文补充表转 TSV（下载用）
├── sample_metadata.tsv           # 12 个文库：stage/treatment/replicate/SRR/文库类型
├── README.md                     # 来源、方法、TE 定义、NA 规则、license、citation
└── md5sums.txt
```

映射规则：

- 用 `Genehub_DB.GenePageIWGSCv1_table` 的 `GeneIDv3 → GeneIDv2`（**不要用字符串 `replace('03G','02G')` 生成假 ID**）；
- 多对一（多个 03G → 同一 02G）：默认取表达量最高/主基因，其余列清单人工确认；
- 映射失败：单独输出清单；若失败率 >2%，暂停并评估方案 C（03G 直存 + 新查询路径）；
- **已完成全量审计**：GeneHub interval API 遍历 21 条染色体 + chrUn，得到 266,760 个 03G 对照；本数据集 60,125/60,125 映射成功、0 缺失、0 多对一冲突（早期 `/api/genes/detail` 随机 300 个抽样也是 300/300，作为交叉验证）。

TE 处理：

- 文件里的 `NA` → 数据库 `NULL`（绝不存字符串、绝不填 0）；
- 展示层（Phase 1 的 expression 页）会显示 0：在 citation/说明里明确"RNA FPKM < 0.2 时 TE 不可计算，页面显示为 0"；
- 极端值：建议展示层把 TE 截断到 p99（≈10）并在下载文件保留原值，或不做截断但写说明；**需要马老师确认口径**。

### 5.2 数据库（`gene_expression` 库）

```sql
-- ① 单位字段（先 DDL，再发代码；默认 TPM 兼容老项目）
ALTER TABLE project_meta
  ADD COLUMN unit VARCHAR(32) NOT NULL DEFAULT 'TPM'
  COMMENT '数值单位：TPM/FPKM/TE/…；前端据此绑定 y 轴与 tooltip'
  AFTER has_std_table;

-- ② 三张数据表（列名 = labels 顺序；只允许 GeneID + 6 个数值列）
CREATE TABLE `CS_grain_heat_RNAseq_FPKM_tbl` (
  `GeneID`   VARCHAR(50) NOT NULL COMMENT 'IWGSC RefSeq v2.1 (02G) gene ID',
  `5DAA_CK`  DOUBLE DEFAULT NULL,
  `5DAA_HS`  DOUBLE DEFAULT NULL,
  `10DAA_CK` DOUBLE DEFAULT NULL,
  `10DAA_HS` DOUBLE DEFAULT NULL,
  `15DAA_CK` DOUBLE DEFAULT NULL,
  `15DAA_HS` DOUBLE DEFAULT NULL,
  PRIMARY KEY (`GeneID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
  COMMENT='CS grain 5/10/15 DAA CK vs 1-h 42C heat stress - RNA-seq FPKM (condition means)';

CREATE TABLE `CS_grain_heat_RiboSeq_FPKM_tbl` LIKE `CS_grain_heat_RNAseq_FPKM_tbl`;
CREATE TABLE `CS_grain_heat_TE_tbl` LIKE `CS_grain_heat_RNAseq_FPKM_tbl`;
```

`project_meta` 3 行（完整 SQL 见附录 A）：

| table_name | display_name | group / subgroup | labels | unit | has_std_table |
|---|---|---|---|---|---|
| CS_grain_heat_RNAseq_FPKM_tbl | Chinese Spring - grain 5/10/15 DAA - heat stress 1 h vs control - RNA-seq FPKM | wheat abiotic stresses / Temperature stress | 6 个 `5DAA_CK…15DAA_HS` | FPKM | 0 |
| CS_grain_heat_RiboSeq_FPKM_tbl | … - Ribo-seq FPKM | 同上 | 同上 | FPKM | 0 |
| CS_grain_heat_TE_tbl | … - translation efficiency (TE) | 同上 | 同上 | TE | 0 |

注意：`labels` 必须与数值列**数量一致、顺序一致**；`display_name` 要带单位（FPKM/TE），避免与站内 TPM 项目混淆。

### 5.3 代码改动（方案 B，约 30 行）

| 文件 | 改动 |
|---|---|
| `app/services/expression_catalog.py` | SELECT 增加 `unit`；扁平列表与树结构都透出 `unit`（缺省 `TPM`） |
| `app/static/expression/index.html` | 目录加载时记录 `projectUnits[id]`；hero 文案/stat 标签/柱图 tooltip/误差棒 tooltip/y 轴标题按 unit 渲染（`index.html:83,86,631,675,840`）；TE 项目的 y 轴标题用 `Translation efficiency (TE)` |
| `app/schemas/expression.py`（可选） | 响应加 `unit: str = "TPM"` |
| `app/mcp/tool_specs.py`（可选） | `query_expression` 描述补一句"单位见 project_meta.unit" |
| `main.py`（可选） | 把 `/expression/` 加进 no-cache 中间件，避免上线后浏览器读旧页 |

### 5.4 前端（Phase 2 预览）

- 复用 `app/static/_v2/template.html` + `shell.css/js`（不要复制头尾；菜单由共享 shell 注入）；
- 图表用站点现有 Highcharts（`app/static/expression/highcharts.js`），不引 CDN；
- 布局建议：顶部搜索 + 阶段 tab；左侧单基因卡片/右侧 DEG-DTG 表；底部 citation（整表数据从论文补充表获取，站点不重复提供下载）；
- 18 列数据很小，API 可实时算 ΔTE（log2((TE_HS)/(TE_CK))），不需要预计算表。

### 5.5 挂接点与部署

- Phase 1：**不用改路由、不用改 Apache、不用改导航**；只需 DDL + 代码（unit）+ 元数据 INSERT，`sudo systemctl restart wheatomics-api` 生效；
- Phase 2：按 `MAINTENANCE.md` SPA 4 步 + 导航/首页/文档/MCP 配套（详见 `REPO_INTEGRATION.md` §11）；
- 下载页：建议在服务器 `/var/www/html/download/` 下建 `heat_translatome/` 目录（约 10–30 MB），下载页加一个板块；仓库侧保留生成脚本与 README。

---

## 6. 分阶段计划与工时

| 阶段 | 内容 | 工时 | 负责建议 | 依赖 | 完成标志 |
|---|---|---|---|---|---|
| **P0 决策** | 口径 A/B、方案 B/C、分组位置、TE 展示口径、授权邮件 | 0.2 人日（马老师拍板） | 马老师 + 陈甜甜 | — | 决策记录写进本目录 `DECISIONS.md` |
| **P1 数据准备** | 全量映射审计、3 张 CSV、下载包、样本元数据、README | 0.5–0.8 人日 | 陈甜甜（数据） | P0 | 审计报告 + CSV + md5 |
| **P2 建表灌数** | DDL、灌数、SQL 验收、备份 | 0.3 人日 | 后端/DBA | P1 | 3 表行数/NA 数/抽查通过 |
| **P3 代码 unit** | `project_meta.unit` DDL、catalog + 前端 5 处 | 0.4 人日 | 前端/后端 | P2 | 本地 3 项目显示 FPKM/TE |
| **P4 元数据上线** | 备份 → 事务 INSERT → 线上验收 | 0.2 人日 | 后端 | P3 | 线上 337 项、API/页面正常 |
| **P5 验收收尾** | 多宽度渲染检查、缓存验证、MCP/基因页验证、回滚演练、文档留痕 | 0.3 人日 | 陈甜甜 + 后端 | P4 | §7 清单全过 |
| **P6 独立页面（已完成原型）** | `/api/translatome/*` + `/translatome/` + DEG/DTG + 双 ID + MCP | 原型已完成；生产部署（Apache/导航/授权/验收）约 0.5–1 人日 | 前端 + 后端 | P1（映射） | 页面 390–1440 宽度 PASS（本地已过）；线上待部署 |

**关键路径**：P1 的映射审计是最可能卡住的一步；建议第一天先跑映射，拿到覆盖率再决定是否继续方案 B。

---

## 7. 验收清单

### 7.1 数据/SQL

- [ ] 3 张表行数一致（映射成功数），`COUNT(DISTINCT GeneID)=COUNT(*)`；
- [ ] 每表恰好 7 列：`GeneID` + 6 个 double，无多余文本列（否则 labels 会错位）；
- [ ] `project_meta.labels` 的 JSON 长度 = 6，且顺序与列顺序一致；
- [ ] TE 表 `NULL` 数 = 源文件对应列 NA 数（5DAA_CK 6,645；…；15DAA_HS 4,658）；
- [ ] 抽查 3 个基因（普通/LC/chrUn）在 3 张表的 6 个值与 xlsx 逐一吻合（<1e-6）；
- [ ] 每列列和/分位数与源文件一致（映射丢行时按比例核对）。

### 7.2 API/页面

- [ ] `GET /api/expression/projects`：项目数 334→337，3 项在 `wheat abiotic stresses → Temperature stress`；
- [ ] `GET /api/expression/query?gene_ids=<02G>&project=<3 个项目>`：各 6 个点；
- [ ] `GET /api/expression/query?gene_ids=<03G>&project=...`：`genes_converted` 正常、能命中；
- [ ] `/expression/` 页面 y 轴/tooltip 分别显示 `FPKM`/`FPKM`/`TE`（不是 TPM）；
- [ ] GeneHub 基因页 `/GeneHub/gene.html?gene=...` 表达下拉自动出现 3 项；
- [ ] MCP `list_expression_projects` 能看到 3 项、`query_expression` 返回 6 点；
- [ ] 错误路径不回归：不存在的项目仍 400，缺表仍 503。

### 7.3 视觉/部署

- [ ] `bash scripts/spa_visual_check.sh http://127.0.0.1:8000/expression/` 在 390/768/1440 宽度 PASS；
- [ ] 线上 `/expression/index.html` 与本地文件一致（强制刷新后无 "TPM" 误标）；
- [ ] `project_meta` 备份表存在；`DELETE` 元数据后 3 项立即消失、重新 INSERT 后恢复（2 分钟回滚演练）。

### 7.4 回滚

| 层 | 操作 |
|---|---|
| 元数据 | `DELETE FROM project_meta WHERE table_name IN (...)` → 立即从所有入口消失，无需重启 |
| 数据表 | `DROP TABLE IF EXISTS CS_grain_heat_*` |
| 代码 | `git revert` + `sudo systemctl restart wheatomics-api` |
| DDL | `unit` 列可保留（默认 TPM 兼容）；必要时 `ALTER TABLE project_meta DROP COLUMN unit;` |

---

## 8. 风险与授权

| # | 风险 | 等级 | 应对 |
|---|---|---|---|
| R1 | **授权**：GB 2025 = CC BY-NC-ND 4.0（转 ID/派生指标可能触及 ND）；PlCell 2023 = © ASPB 非 OA | **高** | 先发邮件取得通讯作者书面同意；页面显著标注来源与 license；如不获批，只做"外链 + 说明"不复制数据 |
| R2 | **03G→02G 映射缺口**（尤其 10,567 个 LC） | 高 | P1 全量审计；覆盖率 ≥98% 才继续；输出未命中清单 |
| R3 | FPKM 被标成 TPM（若跳过 unit 改动） | 高 | 必须做方案 B 的 unit 字段 |
| R4 | TE NA 显示 0 / 极端值压轴 | 中 | Phase 1 文案说明 + 展示截断；Phase 2 专用页面保留 NA/log 轴 |
| R5 | 引用写错（数据不是本站再分析） | 中 | 统一写 "curated from Chen et al. 2025 Table S1; control from Guo et al. 2023" |
| R6 | 元数据手工 INSERT 无版本化 | 中 | 把 DDL/INSERT/导入脚本提交到 `scripts/sql/` 或本目录，留痕可重放 |
| R7 | 浏览器缓存导致用户看旧页 | 低 | 上线后强刷；或把 `/expression/` 加入 no-cache 中间件 |
| R8 | 用户查不到基因（表只含 60,125 个） | 低 | display_name/citation 写明"仅含检出的 60,125 个基因" |
| R9 | 生产库权限不足（CREATE/INSERT） | 低 | 提前 `SHOW GRANTS`；无权限找 DBA/运维 |

**授权邮件要点**（中英文模板见附录 B）：说明用途（学术网站非商业展示 + 检索）、不会修改原始数据、会署名并链接原文与 SRA、请求确认是否可将 Table S1 以结构化形式再发布（含 03G→02G ID 转换与图表展示）。

---

## 9. 需要马老师拍板的 7 件事

1. **口径**：按"已发表数据整理（口径 A）"上架，还是坚持"WheatOmics 再分析（口径 B，需 1–2 周重跑）"？
2. **方案**：Phase 1 走推荐方案 B（约 2 人日，新增 unit 字段），还是先零代码方案 A（会继续把 FPKM/TE 标成 TPM，不建议），或直接上方案 C？
3. **TE 展示口径**：NA 在页面显示为 0（现有接口行为，需文案说明）是否可以接受；极端值是否允许展示层截断到 p99（下载保留原值）？
4. **分组位置**：`wheat abiotic stresses → Temperature stress` 还是 `wheat developmental tissues → Seed / Grain`？
5. **映射未命中**：03G→02G 映射失败的基因（预计很少）是丢弃、人工确认，还是要求平台支持 03G 原生表？
6. **配套数据**：是否把 Table S2（DEG）与 Table S3（DTG）一起做成下载/检索（推荐至少放下载包）？
7. **执行与窗口**：是否由陈甜甜负责数据准备与上线验收、后端配合 unit 改动；上线时间窗口（建议避开有课/汇报的日期）。

---

## 附录 A：`project_meta` 入库 SQL 草案

```sql
-- 上线前备份（沿用仓库既有做法）
CREATE TABLE project_meta_bak_20261111 LIKE project_meta;
INSERT INTO project_meta_bak_20261111 SELECT * FROM project_meta;

START TRANSACTION;

INSERT INTO project_meta
  (table_name, display_name, group_name, subgroup, sub_subgroup,
   labels, citation, has_std_table, unit)
VALUES
('CS_grain_heat_RNAseq_FPKM_tbl',
 'Chinese Spring - grain 5/10/15 DAA - heat stress 1 h vs control - RNA-seq FPKM',
 'wheat abiotic stresses', 'Temperature stress', '',
 '["5DAA_CK","5DAA_HS","10DAA_CK","10DAA_HS","15DAA_CK","15DAA_HS"]',
 'Description:Chinese Spring developing grains at 5, 10 and 15 days after anthesis (DAA), control (CK) vs 1-h 42 °C heat stress (HS); RNA-seq FPKM (condition means; RNA n=3). Heat-stress data from Chen et al. 2025 Genome Biol; control data from Guo et al. 2023 Plant Cell. Publication:Translational regulation plasticity shapes wheat grain adaptation to heat stress. Genome Biol 2025;26:382. PubMed Link:https://pubmed.ncbi.nlm.nih.gov/41214722/;DOI Link:https://doi.org/10.1186/s13059-025-03848-4 <a href=''https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1135409''>PRJNA1135409</a>',
 0, 'FPKM'),

('CS_grain_heat_RiboSeq_FPKM_tbl',
 'Chinese Spring - grain 5/10/15 DAA - heat stress 1 h vs control - Ribo-seq FPKM',
 'wheat abiotic stresses', 'Temperature stress', '',
 '["5DAA_CK","5DAA_HS","10DAA_CK","10DAA_HS","15DAA_CK","15DAA_HS"]',
 'Description:Chinese Spring developing grains at 5, 10 and 15 days after anthesis (DAA), control (CK) vs 1-h 42 °C heat stress (HS); Ribo-seq FPKM (condition means; Ribo n=2). Heat-stress data from Chen et al. 2025 Genome Biol; control data from Guo et al. 2023 Plant Cell. Publication:Translational regulation plasticity shapes wheat grain adaptation to heat stress. Genome Biol 2025;26:382. PubMed Link:https://pubmed.ncbi.nlm.nih.gov/41214722/;DOI Link:https://doi.org/10.1186/s13059-025-03848-4 <a href=''https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1135409''>PRJNA1135409</a>',
 0, 'FPKM'),

('CS_grain_heat_TE_tbl',
 'Chinese Spring - grain 5/10/15 DAA - heat stress 1 h vs control - translation efficiency (TE)',
 'wheat abiotic stresses', 'Temperature stress', '',
 '["5DAA_CK","5DAA_HS","10DAA_CK","10DAA_HS","15DAA_CK","15DAA_HS"]',
 'Description:Translation efficiency (TE = mean Ribo-seq FPKM / mean RNA-seq FPKM). TE is not computed when RNA-seq FPKM < 0.2 (stored NULL; the current expression page displays NULL as 0; please use the download file for exact missing values). Heat-stress data from Chen et al. 2025 Genome Biol; control data from Guo et al. 2023 Plant Cell. Publication:Translational regulation plasticity shapes wheat grain adaptation to heat stress. Genome Biol 2025;26:382. PubMed Link:https://pubmed.ncbi.nlm.nih.gov/41214722/;DOI Link:https://doi.org/10.1186/s13059-025-03848-4 <a href=''https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1135409''>PRJNA1135409</a>',
 0, 'TE');

COMMIT;
```

> citation 的解析规则：`parseCitation()` 只取**第一个** `<a>`（accession）、**第一个** PubMed URL、**第一个** DOI URL；不要写第二个 `<a>`。入库前在 staging 页面核对渲染效果。SQL 中单引号按服务器客户端要求转义（`''` 或 `\'`）。

---

## 附录 B：给通讯作者的授权邮件模板

**中文**

> 彭老师，您好！
>
> 我们是中国农业大学小麦多组学平台 WheatOmics（https://wheatomics.sdau.edu.cn）的维护团队。您课题组 2025 年发表在 *Genome Biology* 的论文（Chen et al., 2025, 26:382）提供了小麦籽粒热胁迫的 Ribo-seq/RNA-seq 数据，我们希望在 WheatOmics 上以**学术、非商业**方式展示该论文补充表 S1 的 FPKM 与翻译效率（TE）数据：包括按基因查询、作图、下载，并链接原文、DOI 与 PRJNA1135409 / PRJNA871371。我们会完整署名并注明数据来源，不会修改原始数值；为方便站内基因检索，仅做 IWGSC RefSeq v2.1（03G）到 v2.1（02G）的基因 ID 对照。
>
> 请问您是否同意我们以上述方式在平台展示这批数据？如需，我们可以先提供页面预览。非常感谢！
>
> 马省伟 / 陈甜甜
> WheatOmics 团队

**English**

> Dear Prof. Peng,
>
> We are the WheatOmics team (https://wheatomics.sdau.edu.cn). We would like to present the RNA-seq/Ribo-seq FPKM values and translation efficiency (TE) from Supplementary Table S1 of your 2025 *Genome Biology* paper (Chen et al., 2025, 26:382) on WheatOmics in a non-commercial, academic manner: gene-level query, visualization, and download, with full attribution and links to the paper, DOI, and the SRA BioProjects PRJNA1135409 / PRJNA871371. We will not alter the original values; the only transformation is a gene-ID cross-reference from IWGSC RefSeq v2.1 (03G) to the platform's 02G IDs for search compatibility.
>
> May we have your permission to display these data in this way? We would be happy to share a preview before release.
>
> Best regards,
> Shengwei Ma / Tiantian Chen
> WheatOmics team

---

## 附录 C：参考与交付物

**论文/数据**

- Chen Y, et al. *Translational regulation plasticity shapes wheat grain adaptation to heat stress.* Genome Biol. 2025;26(1):382. DOI [10.1186/s13059-025-03848-4](https://doi.org/10.1186/s13059-025-03848-4)；PMID [41214722](https://pubmed.ncbi.nlm.nih.gov/41214722/)；PMCID [PMC12599102](https://pmc.ncbi.nlm.nih.gov/articles/PMC12599102/)；SRA [PRJNA1135409](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1135409)
- Guo Y, et al. *The translational landscape of bread wheat during grain development.* Plant Cell. 2023;35(6):1848–1867. DOI [10.1093/plcell/koad075](https://doi.org/10.1093/plcell/koad075)；PMID [36905284](https://pubmed.ncbi.nlm.nih.gov/36905284/)；PMCID [PMC10226598](https://pmc.ncbi.nlm.nih.gov/articles/PMC10226598/)；SRA [PRJNA871371](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA871371)
- 补充表 S1（数据来源）：[Springer 静态文件](https://static-content.springer.com/esm/art%3A10.1186%2Fs13059-025-03848-4/MediaObjects/13059_2025_3848_MOESM2_ESM.xlsx)（md5 `85db3d05cae2e413b48c0739d0edc36d`）
- 作者自建 genome browser（2026-11-11 实测均可访问，JBrowse 1.x，托管在 CAU `wheat.cau.edu.cn`）：
  - GB 2025 热胁迫版：https://wheat.cau.edu.cn/heat_stress_response_wheat_grain_translatome_browser/ —— 16 条轨道：参考序列、IWGSC RefSeq v2.1 基因、lncRNA、新注释 ORF，外加 6 条 RNA-seq（5/10/15 DAA × CK/HS）和 6 条 Ribo-seq 覆盖度轨道；
  - PlCell 2023 发育版：https://wheat.cau.edu.cn/wheat_grain_translatome_browser/ —— 14 条轨道：RNA-seq / Poly-seq / Ribo-seq 各 3 个发育阶段的覆盖度，加注释与 miRNA target；
  - 定位：**基因组浏览器（覆盖度轨道）**，不提供基因级 FPKM/TE 矩阵查询与整表下载；与本站计划的"基因级查询 / 作图 / 下载 / MCP"互补。上架时以**互链**为主（项目 citation 或页面加 "Genome browser" 按钮），不重复做覆盖度 track。

**本目录交付物**

| 文件 | 内容 |
|---|---|
| `PLAN.md` | 本文件（建议与实施计划） |
| `DATA_AUDIT.md` | 数据体检、逐格溯源、QC 统计、上架前问题清单 |
| `PAPER_CONTEXT.md` | 两篇论文的题录/设计/定量/TE 定义/accession/license/citation 核实 |
| `REPO_INTEGRATION.md` | 仓库侧集成审计（数据模型、前端能力、DDL、迁移、回滚、验收） |
| `PHASE2_IMPLEMENTATION.md` | Phase 2 原型实现说明：文件清单、API、双 ID/数据资产、前端、MCP、部署步骤与待办 |
| `PHASE2_EXTENSIBILITY.md` | 多数据集扩展设计（Phase 2.5 **已实施**）：manifest + registry、新增数据 SOP、UI/存储策略 |
| `screenshots/` | 本地渲染验收截图（桌面/移动/图表） |

**下一步（建议本周内）**：马老师拍板 §9 的 7 个问题 → 发授权邮件 → 陈甜甜跑全量映射审计 → 后端建表 + unit 改动 → 上线验收。
