# KnownGene v2055 — 前端展示调整方案

> 交付物：`docs/known_genes/frontend_change_spec.md`（task-3）
> 作者：frontend-ux｜日期：2026-10-28｜阶段：调查 + 计划（**本阶段不改代码**）
> 依据：`docs/known_genes/CONTEXT.md`（Lead 维护的事实基线）、v2055 Excel 实测（本文件 §2/§10 的补充实测）、线上只读 curl + 本机 ego-browser 多宽度基线检查。
> 范围：`app/static/genes/index.html`（556 行，已 V2 shell）与 `app/static/genes/detail.html`（395 行，仍是旧框架）；涉及 API 契约的部分只写「前端对 backend 的依赖」，契约最终以 Lead/backend 为准。
> 约束遵循：只读仓库；未改 `app/static/**`、未提交 git；本文所有行号基于 git HEAD `5364ca3`。

---

## 0. 一页结论（给 Lead 先看这 10 条）

1. **数据形态变了，页面职责要变**：旧库 520 行是「短摘要」（phenotype 均值 ~30 字符）；新库 1420 行是「文献级长摘要」——`gene_phenotype` 均值 368.9 / 最长 1677 字符，`key_result` 最长 3051，`function_description` 最长 2236，`蛋白家族` 最长 2657。**列表页必须只展示摘要 + 截断 + 徽章，全文交给详情页**；否则结果卡片不可读。
2. **列表首屏不能继续全量拉 `/known/all`**：按新字段估算，1420 行的 `/all` ≈ **1.10 MB** 未压缩（实测线上无 gzip/content-encoding），是现在 520 行 97.9 KB 的 11 倍；Stats tab 客户端 `Math` 聚合也因此不可持续。→ 前端吃 **`limit/offset` 分页**（50/页）+ Stats 改吃新 `/known/stats`。
3. **Stats tab 现有 4 个 KPI 全部失真**：`Total` 520→1420 只是数字变化，但「覆盖小麦染色体 21」「Distinct species 296」「Distinct phenotypes 1070」在新数据下**语义错误**（21/21 恒满、原始物种串 296 虚高、1070 个长文本没有统计意义）。改为 6 KPI + 7 组图（物种归一化 / 小麦 21 条 + 其他物种染色体 / 功能大类 / 研究策略 / 表型标签 Top N / 年份），全部由服务端聚合。
4. **新增 5 个字段是这次前端升级的核心卖点**：`reference_genome_id`、`protein_family`、`validation_methods[]`、`research_strategy`、`functional_category`。其中 3 个受控词表适合徽章化（功能大类 5 值 / 研究策略 3 值 / cloning_method 8 值），蛋白家族与验证方法适合「短标签 + 全文折叠」。
5. **参考基因组 ID 的链接目标已实测定案**：仓库与线上都已有 GeneHub 入口（shell 导航 + `/GeneHub/` 返回 200 + `?search=TraesCS…` 直达 `/cgi-bin/geneDetail.py`）。但 `/api/genes/resolve` 对 `HORVU.*` 与 GenBank 型 ID 实测返回 `count:0` → **只有 `^TraesCS\d`（1291 行）可链 `/GeneHub/?search=<id>`，其余 129 行纯文本**；`/api/genes/detail/{id}` 是 JSON API 且仅覆盖 CS IWGSCv1，不适合做用户链接。
6. **多 DOI/题名/年份按位置对应，但实测有 16 行数量不齐**（多为「2 DOI 只有 1 个年份」，另有 1 行 3 DOI/4 题名，题名重复）。→ 后端按位置对应、缺失补 `null`；前端引用列表必须容错（无年份显示 `—`、无题名显示占位），不能因为数量不齐而丢 DOI。
7. **detail.html 必须迁到 `_v2` shell**（现在还是 `#home_header/#header-tabs/#home_footer` 旧框架）。本机多宽度基线实测：`/genes/` **PASS**；`/genes/detail.html?id=1` **FAIL**（footer 邮箱对比度 2.82:1 < 3:1；5 张图片无 alt；多处 3.54:1 警告）。迁移后由 shell footer 统一解决，并去掉重复的每页 visit 统计脚本。
8. **CONTEXT.md 有两处与实测不符，需在计划里修正**（详见 §2.4）：①「37 种染色体标签」实测 **38 种**（21 小麦 + 17 非小麦，非小麦 95 行）；②「部分字段含 HTML 标签」实测 v2055 **0 行**含真实 HTML 标签，`<` 全部来自 `p < 0.05` 之类数学符号（但前端仍必须 `esc()`）。
9. **有一个后端坑必须提前排期**：新数据有 23 行 `#`（如 "Tahsfa1 lines #1 and #2"、染色体 "7S#1"），而现有 `normalize_text()` 会把每个 `#` 替换成 `'`（`app/services/legacy_parsers.py:19`）→ 前端会显示 "lines '1"。必须在 API 层改用「只处理 CGI 时代 `####`」的新归一化，否则前端无论怎么改都救不回来（详见 §9 R6/Q7）。
10. **工作量**：前端 15 个可执行子任务，约 **23–25 h**；关键路径 = backend 契约（`/stats`、`limit/offset`、详情新字段）→ 详情页 → 列表页 → Stats → 视觉/上线验收。拆分见 §8，开放决策见 §9。

---

## 1. 现状盘点：逐区块说明「数据变化后为何失真/失效」

> 行号格式：`index.html:NN` = `app/static/genes/index.html` 第 NN 行；`detail.html:NN` 同理。

### 1.1 页面骨架 / head / 框架

| 区块 | 现实现（行号） | 新数据下的问题 | 处置 |
|---|---|---|---|
| `<title>` | `index.html:6` `KnownGene \| WheatOmics 2.0`；`detail.html:6` `Gene Detail - WheatOmics` | 不符合任务验收的 `<title>KnownGene - WheatOmics</title>`；两页不一致 | 统一为 `KnownGene - WheatOmics`；详情页加载后动态 `document.title = gene_id + ' - WheatOmics'`（保留现有行为 `detail.html:285/375`）。注：`_v2/README.md` 写的是 `Module | WheatOmics 2.0`，与 MAINTENANCE §VII 冲突 → 走 Q11 决策 |
| 静态资源 | `index.html:8/12/13/14`：bootstrap 4.5.3 → jquery 1.9.1 → bootstrap.bundle → `/api/v2shell/shell.css`；`detail.html:8/46/47`：bootstrap、jquery、bundle | detail 缺 `shell.css`、缺 `<div id="v2-shell-*">` | 详情页按 §6.1 迁移；不改 `_v2/shell.css|js` 生成物 |
| 旧框架 | `detail.html:114-159`（`#home_header`/`#header-tabs` 22 项硬编码菜单）、`detail.html:234-257`（`#home_footer` + LOGO 图 + `#visit-stats`） | ① 与全站 V2.0 chrome 不一致；② 旧菜单是 §I 说的「22 份菜单副本」之一，长期漂移源；③ 基线 spa_visual_check FAIL（footer 邮箱对比度 2.82:1、5 图无 alt） | 删除旧框架（行号级步骤见 §6.1），由 shell.js 注入 |
| 每页 visit 统计 | `detail.html:10-44` 自带 `/api/track/visit` + `/api/track/stats` | shell.js 已统一做 visit 统计（`_v2/shell.js:170-188`）→ 迁移后**双计** | 迁移时删除该脚本块；analytics 行为变化：shell 只按 `location.pathname` 计，不再带 `?id=`（可接受，需知会） |
| Hero 文案 | `index.html:107-111`：`6 search fields` / `Curated annotations` / `Dataset statistics` | 「6 search fields」旧：field 下拉实际 6 项但从未生效；新版 field 变 9 项 | 改为 `9 search fields`（或由 `/stats` 的 `total` 动态填 `<strong>1,420</strong> curated genes`，纯增强） |

### 1.2 Search tab（`#tab-search`）

| 子区块 | 现实现（行号） | 新数据下的失真/失效 | 处置 |
|---|---|---|---|
| Field 下拉 | `index.html:137-146`（6 个 option：all/phenotype/chrom_pos/species/gene_name/gene_id） | **从未生效**：`runSearch()` 只发 `searchid`（`index.html:353`），所选 field 被丢弃；且 `chrom_pos` 不在 §4 `field` 枚举里 | 真正对接 §4 `field`（映射表 §4.1）；`chrom_pos` 需决策新增（Q2） |
| Search 按钮/计数 | `index.html:147-158`、`163` `#res-info` | 只有 `Showing N`；无分页、无范围、无筛选说明 | 改为 `Showing 1–50 of 1,420`（§4.3） |
| **结果卡片** | `index.html:329-347`（`.gene-card` 样式 `48-71`） | ① `phenotype` 全文直出（均值 369、最长 1677 字符）→ 每张卡 3–15 行，1420 张卡不可扫读；② `species` 原文直出（296 种原始串，60 行 >500 字符、最长 668）→ 卡片被材料描述撑爆；③ `chromLabel()`（`index.html:268-272`）正则 `/(\d+[A-Da-d])/` **只认 A–D 染色体**：大麦 `1H–7H`、`1R/6R`、`1S/2V/6S/6U/6V`、`7E`、T.ponticum `chr51/chr54` 共 17 种标签、**95 行**全部 fallback 成整条 `chrom_pos`（30–41 字符，如 `MorexV3 chr3H:595.906-595.909Mb`）→ 染色体 badge 失去意义；④ 新字段 `reference_genome_id/functional_category/research_strategy` 完全不显示；⑤ `publication_year` 不显示（且当前 `/search` SQL 没 SELECT 该列，线上恒 `null` —— backend bug，见 Q3） | 重做卡片（§4.2）：物种归一化、phenotype 2 行截断、染色体解析增强、徽章、参考基因组 ID、年份/引用数 |
| 初始加载 | `index.html:367-374`：空 term → `loadAllGenes()` 拉 `/all` 全量渲染 | 新 `/all` ≈1.10 MB 未压缩，首屏一次渲染 1420 张卡（含长文本）→ 白屏/卡顿/内存高；且 Stats 复用同一缓存 | 改为「分页首屏」：`/all?limit=50&offset=0`（§4.3），渲染 50 张；Statas 不再依赖该缓存 |
| 空态/错误态 | `index.html:320-325`、`356-366` | 只有一种 "No genes found"；无法区分「搜索无结果 / 筛选无结果 / 接口失败」 | 三种空态 + 重试按钮（§4.3） |
| 导出 CSV | `index.html:164-166`、`485-533` | 只有 7 列（gene_id/gene_name/chrom_pos/species/phenotype/dois/detail_url），缺 8 个新字段；`phenotype` 全文进 CSV（1677 字符/格，可接受但 Excel 观感差）；`csvField()` 已正确 RFC4180 转义 + BOM（`496-514`） | 新列清单 §4.5（19 列）；加 Excel 公式注入防护；导出「全部筛选结果」而非仅当前页 |

### 1.3 Stats tab（`#tab-stats`）

| 子区块 | 现实现（行号） | 新数据下的失真/失效 | 处置 |
|---|---|---|---|
| 数据来源说明 | `index.html:176-177`：「Aggregates are computed client-side from the full `/api/genes/known/all` response」 | 新 `/all` 1.1 MB，客户端聚合不可持续 | 改吃 `/api/genes/known/stats`，文案同步 |
| KPI: Total known genes | `179-184` | 520→1420 数值本身 OK | 保留，改 `1,420` 千分位 |
| KPI: Wheat chromosomes covered | `186-191`、`277-279`、`460-462`：`WHEAT_CHROMS` 固定 21，`kpi = covered/21` | 新数据 **38 种标签 / 95 行非小麦**；21 条小麦染色体本来就会 100% 覆盖 → 「21/21」恒满、无信息量；非小麦 95 行完全不进图（`isWheatChrom` 过滤 `455-456`） | 拆图：小麦 21 条（vbar）+ 其他物种染色体（bar-row）；KPI 改为「Wheat chromosomes 21/21」+ 副标题「+ 17 other chromosome types」 |
| KPI: Distinct species | `192-196`、`457`：`Object.keys(speciesMap)`，key 用原始 `species` | 296 个原始串（同义/带材料描述）→ 虚高；归一化后 ≈24–26 | 用服务端 `species_primary` 分布（Q4 定归一化规则） |
| KPI: Distinct phenotypes | `198-203`、`458`：原始 `phenotype` 去重计数 | 1070 个长文本，作为「repertoire 大小」没有解释力；Top15 更糟（见下） | 删除该 KPI；改「Phenotype trait tags（564 个可复用标签）」或并入 Top 图副标题 |
| Genes per chromosome | `206-211`、`466-469`：`renderVerticalBars(21 个小麦染色体)` | 95 行非小麦被丢弃；27 行「其他小麦参考基因组」的 A/B/D 染色体被算进 CS 图（口径混杂）；非小麦物种无法在页面看到 | 两段图（§5.2） |
| Top 15 phenotypes | `213-218`、`471-474`：按完整 `phenotype` 字符串计数 | 1070 个不同值、大量唯一 → Top15 高度碎片（最多 2–3 次）；且标签是长文本，柱状图 label 不可读 | 服务端按 `; ` 拆标签 + 行级去重 + 丢弃 >80 字符自由文本段 → Top 20（实测 Top：not determined 65 / drought tolerance 54 / salt tolerance 42 / stripe rust resistance 33…） |
| 缺失图表 | — | 新数据最有价值的聚类维度（功能大类 5 值、研究策略 3 值、物种 25 值、年份 1998–2026）全部缺失 | 新增 4 组图 + 2 KPI（§5） |
| 级联失败 | `loadStats()` 走 `loadAllGenes()`（`443`） | `/all` 一变慢/一大，Stats 首开即卡 | 独立请求 + 独立 loading/error + 缓存 |

### 1.4 detail.html（旧框架 + 旧 section）

| 子区块 | 现实现（行号） | 新数据下的失真/失效 | 处置 |
|---|---|---|---|
| head | `172-176`：gene_name / gene_id / meta（clone_id+submission_date） | 新行若没有 `author/submission_date`（新 Excel 无这三列），meta 只剩 clone_id；reference genome ID 无处展示 | 新增 ref genome 行 + 徽章行（§6.2） |
| Meta 卡 Chromosome | `178-184`、`296` | 值从 `5A` 变 30–41 字符的 `chrom_pos`（如 `Refv1.0 chr1A:108.687-108.691Mb`）；18px 居中卡会换 3 行，仍可读但信息密度差、且解析不出染色体标签 | 拆成「大 label + 小 mono 全文」（§6.2） |
| Meta 卡 Species | `185-190`、`297` | **最长 668 字符、288 行 >200 字符、263 行含多物种 `; `** → 18px 居中卡会变成 8–15 行大字块，页面直接崩坏 | 卡里只放归一化学名（italic），原始材料文本移到可折叠 Species 卡（§6.2/§6.3） |
| Meta 卡 Phenotype | `191-196`、`298` | **最长 1677 字符、均值 369** → 同样崩坏 | 移出 meta 卡，改为独立 `#card-phenotype` 全文卡（6 行截断+展开） |
| Meta 卡 Publication year | `197-203`、`299` | `year(4)` 装不下 `2008; 2024` 这类多值（115 行）→ API 会变 `publication_years[]`；卡片需展示多枚年份 chip | 改为 Years chips + References 内每项年份 |
| Key results | `205-208`、`338-349` | 新 `key_result` 是**单条 40–464 词长文本**（非旧 `###` 多值），`split_legacy_multi_value` 会返回「单元素数组」→ 一个 `<li>` 包 1270–3051 字符 | 保留卡，改为长文本 clamp 12 行 + 展开（§6.3） |
| Function description | `210-213`、`301-305` | 最长 2236 字符，直出成一个超长段落 | 长文本 clamp 8 行 + 展开 |
| Cloning method | `215-220`、`307-315` | `cloning_method` 出现组合值（`Homology-based cloning; Functional cloning` 等 4 行）→ 单个文本；描述最长 1757 字符 | chip 化 + Description 折叠 |
| References | `222-225`、`317-336` | ① 无 `year`（契约新增）；② 旧 `references[]` = doi + **按 `###` 切分的 title**，新数据 title/doi/year 要按 `; ` 位置对应（**实测 16 行数量不齐**）；③ 3 DOI 行有 20 行、2 DOI 110 行 | 重建引用列表：`[year] title — DOI link`，容错（§6.4） |
| Submitted by | `227-230`、`351-364` | 新数据无 `author/author_mail` 列；整表替换后新行这两列为空 → 页面出现整块「—」 | 空则**整卡隐藏**（§6.3） |
| 缺失 section | — | `reference_genome_id` / `protein_family` / `functional_category` / `research_strategy` / `validation_methods[]` / `species_primary` 全部无展示 | 新增 5 个 section（§6.2） |
| XSS/转义 | `260-265` `esc()` 有；`303/309/310` 等用 `.text()`；引用/作者用 `.html()`+`esc()` | 目前安全，但新增长文本+chips+链接后必须全程 esc；新数据无真实 HTML 标签但含裸 `<`（`p < 0.05`）→ 只能转义、不能 strip | §7.2 转义/URL 白名单规范 |

### 1.5 多宽度基线实测（2026-10-28，ego-browser，只读）

| 页面 | 宽度 | 结果 | 关键项 |
|---|---|---|---|
| `https://wheatomics.sdau.edu.cn/genes/` | 390/768/1440 | **PASS** | 0 溢出 / 0 破图 / 0 JS 错；390px 唯一 Warn：footer "Back to top ↑" 72×15px 小点击目标（主题自带，MAINTENANCE §IX 允许） |
| `https://wheatomics.sdau.edu.cn/genes/detail.html?id=1` | 390/768/1440 | **FAIL** | Floor：footer 邮箱 `shengweima@icloud.com` 对比度 2.82:1；另有 3.54:1 警告（gene id/meta/meta-label）、5 张图无 alt、1 个 4.34:1 — 全部来自旧 header/footer，迁 shell 后消除 |

复现命令见 §7.4；改造完成后的目标同样是 `Result: PASS`（只允许 footer back-top Warn）。

### 1.6 现状 vs 新数据量化对照

| 维度 | 现库/现页（520 行） | v2055（1420 行） | 前端后果 |
|---|---|---|---|
| phenotype | 短标签（`male sterility`、`grain weight`） | 均值 **368.9**，P95 ~1081，最长 **1677** 字符；1070 不同值 | 卡片必须截断、详情才放全文 |
| species | 自由文本 5 种写法混杂（`common wheat` 244…） | **296** 个原始串；归一化 ≈24–26；60 行 >500 字符 | 列表只显归一化学名，原文折叠 |
| chrom_pos | `5A` / `Refseq v1.0 chr3B:…` | **38** 种标签（21 小麦 + 17 其他）；**95 行非小麦**（大麦 80、黑麦/其他 15）；34 种参考基因组前缀 | 染色体解析要扩展；Stats 要分组 |
| DOI | 520 行、多值为 `;` 未拆 | **130 行多 DOI**（110×2 + 20×3）；参考文献条目 **1570**；唯一 DOI 元素 **883**（注：CONTEXT「820 个唯一 DOI」是「整格字符串去重 820」，元素级 883，见 §2.4） | 引用列表 + 列表页 `N references` |
| 年份 | `year(4)` 单值 | **115 行多值**（最多 3 个）；1998–2026 | `publication_years[]` → chips |
| 来源字段 | 无 | `reference_genome_id`（180 行 ≠ gene_id）、`蛋白家族`（1176 不同值）、`验证方法`（895 组合）、`研究策略`（3 值）、`功能大类`（5 值） | 新增徽章/chips/折叠 |
| `/all` payload | 97,894 B（实测 520 行） | 新口径估 **1.10 MB**（10 字段）未压缩 | 必须分页（§2.5） |

---

## 2. 新数据的前端约束（实测补充）

> 数据口径由 data-profiler/backend 最终定；以下为 frontend 视角必须知道的数字与样本（本文件实测，pandas 脚本见 §10.2）。

### 2.1 字段长度 / 分布（frontend 相关）

| 字段 | 不同值 | 中位长度 | 最长 | 列表页要处理的问题 |
|---|---|---|---|---|
| gene_id | 1395（25 行重复） | 18 | 28 | 1 行含 `/`（`Yr87/Lr85`）→ **详情 URL 只能用 clone_id**，不能用 gene_id |
| reference_genome_id | 1386（34 行重复，按 D7 属预期） | 19 | 42 | 1 行含逗号（`Ae.longissima_6S_ORF:51,756,423-51,772,629`）→ 不能进 URL |
| gene_name | 1418（2 行完全同名，归一化后 6 行） | 8 | 43 | 含 `/`、`;`、空格、希腊字母（`TdPIP2;1`、`Gli-γ2-1B`）→ 只能 esc 文本，不能进 URL |
| 物种信息 | **296** | 109.5 | 668 | 263 行含多物种 `; `；60 行 >500 字符 |
| chrom_pos | **1389 整串**（38 种染色体标签） | 30.6 | 41 | 解析标签 + 参考基因组前缀 |
| gene_phenotype | **1070** | 368.9 | 1677 | 897 行含 `;`（可提炼标签）；列表截断 |
| key_result | 1420 | 1180 | 3051 | 详情卡 clamp |
| function_description | — | 1141 | 2236 | 详情卡 clamp |
| 蛋白家族 | 1176 | 591 | 2657 | 短标签 + 详情 clamp |
| cloning_method | 8 | 19.3 | 51 | chip；4 行是组合值 |
| cloning_method_description | — | 909 | 1757 | 折叠 |
| 验证方法 | 895 组合 | 494 | 2114 | chips + 长自由文本折叠 |
| 研究策略 | 3 | 15.8 | 16 | badge（列表隐藏 Not reported） |
| 功能大类 | 5 | 23.2 | 32 | 彩色 badge |
| title | — | 124.9 | 473 | 只在详情 References 展示 |
| doi | 820 整格 / 883 元素 | 25.1 | 82 | `N references` + 详情链接 |
| publication_year | — | 4.6 | 16 | 多值 chips |

### 2.2 前端需要认识的枚举值（用于徽章/图表配色）

**功能大类（5，前端配色见 §3.3）**
`Biotic & Abiotic Stress` 776 / `Quality & Yield` 202 / `Morphology & Domestication` 154 / `Physiology & Metabolic Processes` 146 / `Reproduction & Phenology` 142。

**研究策略（3，列表隐藏 Not reported）**
`Reverse genetics` 1061 / `Forward genetics` 281 / `Not reported` 78。

**cloning_method（8 → 展示 5 个主值 + 组合拆分）**
`Homology-based cloning` 569 / `Not reported` 304 / `Transcriptome-based cloning` 250 / `Map-based cloning` 184 / `Functional`（+ `Functional cloning` 共 107）/ 组合值 6 行（按 `; ` 拆成多个 chip）。

**染色体标签（38 种；非小麦 95 行）**
小麦 21：`1A–7D`（1325 行，其中 1298 行前缀 `Refv1.0`，27 行来自其他小麦参考基因组如 `Zavitan.v1`/`Svevo`/`Tmonococcum`/`AK58` 等）。
非小麦 17 种 / 95 行：`1H 13, 2H 15, 3H 16, 4H 10, 5H 8, 6H 3, 7H 15`（大麦 80）、`1R 4, 6R 1`、`1S 2, 2V 1, 6S 1, 6U 1, 6V 1, 7E 2`、`51 1, 54 1`（T.ponticum，**建议显示原始 `chr51`/`chr54`，不要当数字**）。
参考基因组前缀 34 种（`Refv1.0` 1298 / `MorexV3` 72 / `Zavitan.v1.0` 6 …），建议在染色体 chip 旁以 muted 小字显示（title=完整 chrom_pos）。

**表型标签 Top 20（服务端按 `;` 拆 + 行内去重 + 丢弃 >80 字符自由文本段后实测）**
`not determined 65`、`drought tolerance 54`、`salt tolerance 42`、`stripe rust resistance 33`、`powdery mildew resistance 19`、`grain weight 14`、`flowering time 13`、`heat tolerance 11`、`grain yield 9`、`plant architecture 9`、`male sterility 8`、`tiller number 8`、`cadmium tolerance 8`、`sharp eyespot resistance 8`、`powdery mildew susceptibility 7`、`seedling growth 7`、`male fertility 7`、`seed dormancy 7`、`g3p accumulation 6`、`thermotolerance 6`；可用标签 564 个，757 行含 >80 字符自由文本段（这些段不进 Top 图）。

**验证方法高频标签**
`Expression analysis 738`、`Phenotyping 648`、`Overexpression 368`、`Subcellular localization 332`、`Transgenic transformation 322`、`VIGS 219`、`Heterologous expression 193`、`Interaction assays (Y2H/BiFC/Co-IP) 130`、`Promoter/transactivation assays 121`、`RNAi 97`、`Mutant sequencing 93`、`Haplotype/association analysis 78`、`CRISPR/Cas9 77`、`Biochemical activity assays 74`、`Transgenic complementation 34`。
⚠️ 该列 895 种组合、`; ` 切分后有 **2866 种 token 形态**，其中 2529 种是 >45 字符的自由文本片段（如 "Heterologous expression (yeast transport assay)"）：**只有白名单/短 token 做 chip，长片段进折叠文本**（§3.4）。

**出版年份（split 后计数，合计 1535 > 1420 因 115 行多值）**
1998…2026 共 29 年；峰值为 2022（254）、2024（248）、2023（180）、2021（154）。

### 2.3 多值字段（title / doi / publication_year）

拆分规则（与 说明 sheet 一致）：**半角 `; `（分号+空格）**，第 k 个 DOI ↔ 第 k 个题名 ↔ 第 k 个年份。

实测（用 `;\s+` 严格拆分）：
| 项 | 计数 |
|---|---|
| DOI 每行个数 | 1 → 1290 行；2 → 110 行；3 → 20 行 |
| 题名每行个数 | 1 → 1293；2 → 107；3 → 19；4 → 1 |
| 年份每行个数 | 1 → 1305；2 → 95；3 → 20 |
| **三者数量不齐** | **16 行** |

典型不齐样本（必须容错，不能丢 DOI）：
- `TraesCS1D03G0038800`：2 DOI / 2 title / **1 year**（`2023`）→ 第二个引用 year 应为 `null`。
- `TraesCS5D03G1233100`：2 DOI / 2 title / 1 year（`2007`）。
- `TraesCS7A03G0602700`：2 DOI / **1 title** / 1 year → 第二个引用 title 缺失。
- `TraesCS7D03G0250300`：3 DOI / **4 title**（其中 2 个题名重复）/ 3 year → 说明题名清洗有残留。
→ 前端渲染规则：按 DOI 数量逐个渲染；`title` 取 `titles[i]`，越界为 `null`；`year` 越界为 `null`；多余题名不丢（后端决定并入最后一项或忽略，前端 `null` 容错即可）。

### 2.4 与 `CONTEXT.md` 的事实核对（3 条需修正/补充）

| # | CONTEXT.md 表述 | 实测 | 对前端影响 | 建议 |
|---|---|---|---|---|
| 1 | §1「37 种染色体标签…T.ponticum chr54/chr51（2 行未匹配正则）」 | **38 种**：21 小麦 + 17 非小麦（含 `51`/`54` 两个 T.ponticum 标签；按 `chr(\d+[A-Za-z]{0,2})` 可正常解析，非「未匹配」） | Stats/卡片解析规则与验收数字 | 修正为 38；设计按「21 小麦 + 17 其他」分组 |
| 2 | §1 数据质量「部分字段含 HTML 标签（phenotype 10、key_result 20、function_description 35、验证方法 13、cloning_method_description 16+1 pipe）」 | v2055 实测 **0 行含真实 HTML 标签**；`<` 只出现在 5/8/12/9/7 行，全部是 `p < 0.05`、`<1,000` 之类数学/数量符号；`|` 1 行；无 tab/newline | 前端**不能**用 stripTags（会误删 `p < 0.05 … >` 合法内容），必须纯 `esc()`/`textContent`；后端导入也不要 strip | 修正表述；验收改为「`<` 全部按文本渲染」 |
| 3 | §1「doi 820 个唯一 DOI」 | 整格字符串去重 = **820**；拆开后唯一 DOI 元素 = **883**；参考文献条目 **1570** | Stats/CSV 的「references」口径 | 明确 KPI 口径：`references 1570 / unique DOIs 883`（推荐）或只用 820 |

补充（不改 CONTEXT，但必须进实施计划）：
- 新数据 **23 行含 `#`**（cloning_method_description 23、验证方法 19、key_result 14、phenotype 13、function_desc 10、蛋白家族 7、物种 3），如 "Tahsfa1 lines #1 and #2"、"7S#1"；现有 `normalize_text()` 会把 `#` 换成 `'` → **必须在 API 层停用该替换**（R6/Q7）。
- 新数据 1 行 gene_id 含 `/`（`Yr87/Lr85`）→ 详情 URL **必须**用 `clone_id`（现有 `detailUrl()` 已优先 clone_id，保留）。
- 新 Excel **没有** author / author_mail / submission_date / clone_id 列；整表替换后这些旧字段大面积空 → 详情页 Submitted by 要空则隐藏；clone_id 由迁移脚本分配（Q8）。

### 2.5 `/all` payload 估算（决定列表页分页策略）

按 17 列实测值构造 JSON 模拟（`separators=(',',':')`，无 gzip）：

| 方案 | 估算 payload（1420 行） | 结论 |
|---|---|---|
| 现契约 6 字段（只换新数据） | 865 KiB | 已不可接受 |
| §4 新契约 10 字段（+ref id/functional_category/species_primary/research_strategy） | **1099 KiB** | 必须分页 |
| 加分页后：50 行/页 | ~39 KiB | ✅ 推荐前端默认 |
| （备选）phenotype 截到 180 字符 | 742 KiB | 仍偏大，不单独采用 |

实测线上 `/api/genes/known/all`：`content-length: 97894`、`vary: Accept-Encoding` 但**响应无 `content-encoding`**（边缘未 gzip），所以按未压缩估算。

### 2.6 需要 backend/data-profiler 处理、前端无法兜底的数据问题

1. 16 行多 DOI/题名/年份不齐（§2.3）。
2. `normalize_text()` 的 `#`→`'` 破坏（§2.4）。
3. `/search` 当前 SQL 未 SELECT `publication_year`（`app/api/routers/gene.py:94`），线上 `publication_year` 恒 null；新契约 summary 要带年份。
4. `/known/stats` 路由必须注册在 `/known/{gene_id}` **之前**（`gene.py:205` 的 catch-all 会把 `stats` 当 gene_id → 404）。前端依赖此顺序，联调时要验。
5. 物种 `species_primary` 归一化规则（durum 的 `subsp.`/`ssp.` 合并、`x Triticosecale` 前缀、多物种行取第一个学名）由 backend 定；前端消费 `species_primary`，不自行硬编码 25 个名字。
6. `publication_year` 列需从 `year(4)` 改为可存多值的类型（如 `varchar(64)`）或新增 `publication_years` 列（DDL 归 backend）。

---

## 3. 17 字段展示映射表（每字段：展示与否/位置/形式/截断展开/空值策略）

> 「列表」= `index.html` 结果卡片；「详情」= `detail.html`。API key 以 CONTEXT §4 草案为准（summary 新增 4 键、detail 新增 6 键）。

| # | 字段（Excel / DB） | API key | 列表页 | 详情页 | 形式/样式 | 截断·展开 | 空值 / `Not reported` 策略 |
|---|---|---|---|---|---|---|---|
| 1 | gene_id | `gene_id` | ✅ 卡片标题行右侧，mono 13px，点击进详情 | ✅ head `<h2 class="kg-mono">` | mono 等宽 | 不截断（≤28），`overflow-wrap:anywhere` | 恒有；若空 → 用 `Clone #clone_id` 占位。**详情 URL 只用 clone_id**（`Yr87/Lr85` 含 `/`） |
| 2 | 参考基因组ID（新增） | `reference_genome_id` | ✅ 元信息行 `Ref: <mono>`；TraesCS 时带外链图标 | ✅ 独立 `#card-refgenome`：mono 值 + GeneHub 按钮 | mono + 链接 | 不截断（≤42），`break-all` | 空 → 整行隐藏。仅 `^TraesCS\d`/`^Traes_` 可链（§3.2） |
| 3 | gene_name | `gene_name` | ✅ 卡片第一行，italic 700 16px | ✅ head `<h1>` 24px italic | italic | 不截断（≤43） | 空 → 隐藏，标题用 gene_id |
| 4 | 物种信息（raw） | `species`（+ 新 `species_primary`） | ⚠️ 只显 `species_primary`（italic）；原文进 `title` tooltip（≤200 字符） | ✅ ① Overview 卡显示 primary；② 底部 `#card-species` 折叠显示 raw 全文 | italic 学名 + 折叠块 | primary 不截断；raw 默认折叠，展开显示全文（最长 668） | 空 → 隐藏；`species_primary` 缺失时前端 fallback：取 `(` 前第一个学名（含 `×/x` 前缀归一） |
| 5 | chrom_pos | `chrom_pos`（建议后端加 `chromosome`/`genome_ref`，Q3） | ✅ `badge-secondary` 染色体标签 + muted 参考基因组前缀，`title`=全文 | ✅ Overview 卡「Chromosome」大 label + 下方 mono 全文 | badge + mono | label ≤4 字符；全文 ≤41 不截断（break-all）；解析失败时显示 raw 前 24 字符 + `…`，title 全文 | 空 → 隐藏 badge |
| 6 | gene_phenotype | `phenotype` | ✅ 2 行截断（CSS line-clamp，全文仍在 DOM）+ `Show more` | ✅ `#card-phenotype` 全文，6 行 clamp + 展开 | 正文段落 14px/1.75 | 列表 2 行；详情 6 行；均可用 `Show more/less` 展开 | 空 → 隐藏整卡 |
| 7 | key_result | `key_result[]`（保留旧键；新数据为单元素） | ❌ 不显示（太长） | ✅ `#card-key-results`，12 行 clamp + 展开 | 正文段落 | 12 行 + 展开 | 空 → 「No key results recorded.」（旧文案保留） |
| 8 | function_description | `function_description` | ❌ | ✅ `#card-function-desc`，8 行 clamp + 展开 | 正文段落 | 8 行 + 展开 | 空 → 整卡隐藏（沿用旧行为 `detail.html:302-305`） |
| 9 | 蛋白家族（新增） | `protein_family` | ✅ 短 chip：`familyHead()`（见 §3.4），>48 字符截 + `…`，title=全文 | ✅ `#card-protein-family`，6 行 clamp + 展开 | chip + 段落 | 列表 chip ≤48 字符；详情 6 行 | 空 → 隐藏 chip/卡 |
| 10 | cloning_method | `cloning_method` | ❌（噪声） | ✅ `#card-annotations` 内 chip（`; ` 拆组合值） | chip | 不截断（≤51） | `Not reported` → 详情 muted 显示；列表不显示 |
| 11 | cloning_method_description | `cloning_method_description` | ❌ | ✅ `#card-cloning` 内「Details」折叠（默认收起），展开后 6 行 clamp + 展开 | 折叠块 | 默认收起；6 行 | 空 → 隐藏 Details |
| 12 | 验证方法（新增） | `validation_methods[]`（detail）；summary 可选 `validation_methods` | ❌（卡片噪声；或只显示数量 `8 assays`，Q12） | ✅ `#card-annotations` chips：按白名单/短 token；>12 个折叠 `+N`；长自由文本片段另起折叠段 | chips（≤40 字符 token） | chips 最多 12 个 + `+N`；长片段折叠 | 空 → 隐藏；`Not reported` → muted |
| 13 | 研究策略（新增） | `research_strategy` | ✅ 小 badge（`Not reported` 隐藏） | ✅ `#card-annotations` badge | badge | 不截断（≤16） | 列表隐藏 Not reported；详情 muted 显示 |
| 14 | 功能大类（新增） | `functional_category` | ✅ 彩色 badge（§3.3） | ✅ `#card-annotations` 同款 badge | badge | 不截断（≤32） | 空 → 隐藏 |
| 15 | title | 详情 `references[].title`（旧 `paper_title[]` 保留） | ❌ | ✅ `#card-references` 每项题名（esc 文本，≤473） | 引用列表 | 不截断（CSV 才需完整）；1 行 4 题名的容错见 §2.3 | 缺题名 → `(title not recorded)` |
| 16 | doi | 详情 `references[].doi`；列表 `dois[]` | ✅ 「N references」+ 首年份（`publication_years[0]`） | ✅ `#card-references` 每项 DOI link | 列表计数文本；详情 mono link | 不截断 | 无 DOI → 隐藏计数；坏格式（实测 0）不链，仅文本 |
| 17 | publication_year | `publication_years[]`（detail）；summary `publication_year` 或 `publication_years` | ✅ 年份（多值 `2008, 2024`；>2 显示 `2008 +1`） | ✅ Overview「Years」chips + References 每项 year badge | 文本 / chip | 不截断 | 空 → `—`；多值去重排序 |

**遗留字段（detail 必须保留/兼容）**

| 字段 | 展示策略 |
|---|---|
| `clone_id` | head meta 行小字 `Record #526`（支持/回滚定位用；数字详情 URL 依赖它） |
| `submission_date` | 有则 head meta 显示 `Submitted: YYYY-MM-DD`；空则不显示（新行大概率空） |
| `author` / `author_mail` | `#card-author`：**两者都空 → 整卡隐藏**；只有 mail → 只显示邮箱；both → `Name <mailto>`（旧 `detail.html:351-364` 逻辑保留，但改为空值隐藏） |
| `paper_title[]` / `key_result[]` | 契约保留旧键，详情优先用 `references[]`；`key_result` 按新语义单条长文本渲染 |

### 3.2 参考基因组 ID 链接目标（已实测定案）

| 候选 | 实测 | 结论 |
|---|---|---|
| `/GeneHub/` 搜索页（`app/static/docpages/genehub_index.html`，线上 `/GeneHub/` 200） | `?search=TraesCS…` → `isCsId()` 为真 → 直接跳 `/cgi-bin/geneDetail.py?search=…`（线上 200）；点击 header 搜索也是这个入口 | ✅ **主链接**：`/GeneHub/?search=<encodeURIComponent(refGenomeId)>`，`target="_blank" rel="noopener noreferrer"` |
| `/api/genes/detail/{gene_id}` | 200，但返回 JSON；且只查 `GenePageIWGSCv1_table`（仅 CS IWGSC v1/v2/v3） | ❌ 不做用户点击链接（可作为未来「嵌入元数据」的 API 源） |
| `/cgi-bin/geneDetail.py?search=` | 200，是 GeneHub 的底层结果页 | ⚠️ 不直接用（跳过 GeneHub 的 ID 解析流程；`/GeneHub/` 已封装） |
| `/api/genes/resolve?ID=` | 对 `HORVU.MOREX.r3.3HG0228170`、`AB029887` 实测 `count:0` | → 非 TraesCS **没有** GeneHub 结果，不要链 |
| `/genes/detail.html` | 那是 **KnownGene 自己的详情页**，不是 GeneHub | 不用于 refGenomeId（会形成自我循环） |

**链接规则（前端）**
```
isGeneHubLinkable(ref) = /^TraesCS\d/.test(ref) || /^Traes_/.test(ref)   // 1291/1420 行
```
- 可链：mono 值 + ↗ 图标（aria-label="Open in GeneHub"）。
- 不可链（129 行：HORVU 77 / GenBank-like 24 / other-alpha 等 28）：纯 mono 文本；可加 `title="No GeneHub record for this reference genome ID"`，不要做死链。
- 本地 dev（127.0.0.1:8000）没有 `/GeneHub/`（docroot 页）→ 视觉检查时链接 404 属预期，不算缺陷；线上验收时抽查 2 个 TraesCS 链接 200。

### 3.3 徽章规格（颜色/文案/长度）

> 只用自定义 `.kg-*` 类，不覆盖 Bootstrap `.badge-*`；前景/背景对比度 ≥4.5:1（详情小字必须 ≥4.5；列表 13px 文字同理）。最终以 `spa_visual_check` 对比度检查为准。

| 维度 | 值 → 类名 | 样式（建议 token/hex） |
|---|---|---|
| 功能大类 | `Biotic & Abiotic Stress` → `.kg-cat-stress` | 背景 `#fdecea` / 文字 `#8f3428` |
| | `Quality & Yield` → `.kg-cat-quality` | `#fdf3dc` / `#6b4d0e` |
| | `Morphology & Domestication` → `.kg-cat-morph` | `#e9f3ea` / `#1e5a3d` |
| | `Physiology & Metabolic Processes` → `.kg-cat-phys` | `#e9f0f8` / `#1f4a70` |
| | `Reproduction & Phenology` → `.kg-cat-repro` | `#f2ecf8` / `#553a70` |
| 研究策略 | `Reverse genetics` → `.kg-strategy.k-reverse` | 白底 + `--line` 边框 + `--forest` 文字；前面小圆点 `●` |
| | `Forward genetics` → `.k-forward` | 同上，圆点 `--wheat` 色 |
| | `Not reported` | 列表**不渲染**；详情 `.kg-muted` 文本 |
| cloning_method | 5 主值 + 组合拆分 | `.v2-chip` 风格（`--mist` 背景 / `--forest` 文字），≤51 字符 |
| 验证方法 chips | 短 token（≤40 字符） | `.v2-chip` 同款；>12 个折叠为 `+N methods` 按钮 |
| 染色体 | `3B` / `1H` / `chr51` | `badge badge-secondary kg-chrom`（shell 桥接 `--mist/--forest`）；非小麦标签用 `badge-light` 区分 |
| 参考基因组前缀 | `Refv1.0` / `MorexV3` | `.kg-genome`（`--muted` 12px mono，不占 badge） |

### 3.4 长文本排版规范（phenotype / key_result / function_description / protein_family）

原则：**列表只给「可扫读摘要」，详情给「分段可展开全文」，任何长文本都不整段硬铺**。

| 场景 | 方案 | CSS/实现 |
|---|---|---|
| 列表 phenotype | **2 行截断** + `Show more` | `.kg-longtext.kg-clamp-2 { display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }`；展开 = 给容器加 `.is-open`（`display:block; overflow:visible`）。**全文保留在 DOM 文本节点里**（不用 JS 截字符串）→ 浏览器内查找/复制仍可用，展开零重排成本。Chromium（ego-browser）支持 `-webkit-line-clamp`；无需 polyfill |
| 列表蛋白家族 | 「家族头标签」+ tooltip | `familyHead(v) = v.split(/\s+-\s+|;|\(/)[0].trim()`，>48 字符 `slice(0,48)+'…'`，`title`=全文；实测 head 618 种（NLR 25、MADS-box TF 18、NAC 15、MYB TF 14…），可用作扫描线索 |
| 详情 phenotype | 6 行 clamp + 展开 | 同上，`kg-clamp-6` |
| 详情 key_result | 12 行 clamp + 展开 | `kg-clamp-12`（旧 `<ul><li>` 改为单段 `<p>`；新数据单条文本） |
| 详情 function_description | 8 行 clamp + 展开 | `kg-clamp-8` |
| 详情 protein_family | 6 行 clamp + 展开 | 顶部再放一个家族头 chip（同列表规则） |
| 详情 cloning_method_description | 默认收起，按钮 `Details` | 复用 Bootstrap collapse（bundle 已加载 `index.html:13` / `detail.html:47`）或自写 toggle；不用额外库 |
| 详情 验证方法长片段 | 默认收起 | 长自由文本（>45 字符 token）合成一段 `Other assays: …`，默认收起 |
| 通用 | 可读行宽 | `.kg-longtext { max-width: 78ch; font-size:14px; line-height:1.75; overflow-wrap:anywhere; }`（`pre-line` 不必开，新数据无换行） |

展开按钮统一规格：`<button type="button" class="btn btn-link btn-sm kg-expand" aria-expanded="false" aria-controls="<id>">Show more</button>`，事件用**事件委托**（`#list-content` / `#detail-content` 上监听），避免 1420 个 card 逐个绑事件。

### 3.5 多 DOI / 题名 / 年份展示

列表卡片：`<span class="kg-refcount">3 references</span>`（首个年份跟在后面，如 `3 references · 2012, 2024, 2002`；>3 年时 `2012 +2`）。
详情 References（顺序 = DOI 顺序）：
```html
<ol class="kg-refs">
  <li class="kg-ref">
    <span class="kg-ref-year">2012</span>
    <span class="kg-ref-title">Combinational transformation of three wheat genes …</span>
    <a class="kg-mono" href="https://doi.org/10.1007/s00299-012-1332-y" target="_blank" rel="noopener noreferrer">10.1007/s00299-012-1332-y</a>
  </li>
  …
</ol>
```
容错规则：
- `year` 为空 → `<span class="kg-ref-year kg-muted">—</span>`（不隐藏，保持对齐）。
- `title` 为空 → `(title not recorded)` muted。
- DOI 格式白名单 `^10\.\d{4,9}/\S+$`（883/883 实测通过）；不通过 → 纯文本不链。
- 绝不用 `paper_title[i]` 的旧 `###` 语义做新数据渲染；旧 `paper_title[]` 仅在 `references[]` 缺失时 fallback。

### 3.6 空值策略总表（快速实施依据）

| 情形 | 列表 | 详情 |
|---|---|---|
| 字段为空串 / null | 隐藏该片段（不显示 "—" 堆叠） | 短字段显 `—`；长文本区整卡隐藏（protein_family/phenotype/function_desc/cloning*/validation）；Submitted by 整卡隐藏 |
| 受控值 `Not reported` | 研究策略/功能大类：隐藏；cloning_method：显示（详情 muted） | muted 文本显示，不占徽章 |
| 多值字段只有 1 个 | 正常单值显示 | 正常单值显示 |
| 解析失败（chrom/DOI/species） | 显示原文截断 + title 全文 | 显示原文 + mono 样式，不链 |

---

## 4. Search tab 改造设计

> 落点：`index.html:131-170`（结构）、`index.html:234-554`（脚本）、`index.html:27-95`（自定义 CSS）。保持公共 ID 不变：`#searchField #searchInp #search-btn #reset-btn #res-info #export-btn #list-content #stats-*`。

### 4.1 Field 下拉真正生效（对接 §4 `field`）

| 下拉 label（建议文案） | option value | 请求 | 说明 |
|---|---|---|---|
| All Fields（默认） | `all` | `/search?searchid=T`（省略 field 或 `field=all`） | 保持现状；服务端 LIKE 字段集合沿用现有 9 列 + 新增列（蛋白家族/功能大类/参考基因组ID，Q1） |
| Gene ID | `gene_id` | `field=gene_id` | 精确感更强 |
| Gene name | `gene_name` | `field=gene_name` | |
| Reference genome ID | `reference_genome_id` | `field=reference_genome_id` | 新增 |
| Trait / Phenotype | `phenotype` | `field=phenotype` | 旧 option 是 `phenotype`，保留 value 兼容 |
| Species | `species` | `field=species` | 输入可建议归一化学名（help text） |
| Protein family | `protein_family` | `field=protein_family` | 新增 |
| Functional category | `functional_category` | `field=functional_category` | 新增；可配合筛选 chips |
| DOI | `doi` | `field=doi` | 新增 |
| Chromosome | `chromosome` | **Q2 决策**：① 建议 §4 `field` 枚举加 `chrom_pos`；② 或前端当 `chromosome` 时改调 `/by-chromosome/{q}`（但该端点返回无 `clone_id`/`dois`，卡片会退化为只能靠 gene_id，`Yr87/Lr85` 无法进详情） | 现 UI 已有该 option 但从未生效；建议走 ① |

其他 Search UX 改动：
- `#searchInp` placeholder 换成多物种示例：`e.g. VRN1, TraesCS5A02G391700, HORVU.MOREX.r3.3HG0228170, drought`（`index.html:149-150`）。
- Enter 提交、Reset 清空输入 + 清空筛选 + 回到浏览页（保留 `searchInp:539-541` / `resetSearch()` 行为并扩展）。
- 请求前 `#search-btn` 置 disabled + spinner 文案，响应后恢复（防连点）。
- 失败提示统一 `alert alert-danger` + Retry 按钮。

### 4.2 结果卡片重做（DOM / CSS 规格）

```html
<article class="kg-gene-card">
  <div class="kg-card-head">
    <span class="kg-gene-name">TaMs5-B</span>
    <a class="kg-gene-id" href="/genes/detail.html?id=12" target="_blank" rel="noopener">TraesCS3B02G392800LC</a>
    <span class="badge kg-cat kg-cat-stress">Biotic &amp; Abiotic Stress</span>
    <span class="badge kg-strategy k-reverse">Reverse genetics</span>
  </div>

  <div class="kg-card-meta">
    <span class="badge badge-secondary kg-chrom">3B</span>
    <span class="kg-genome">Refv1.0</span>
    <span class="kg-refid">Ref: <a class="kg-mono" href="/GeneHub/?search=TraesCS…" target="_blank" rel="noopener noreferrer">TraesCS3B02G392800LC</a></span>
    <span class="kg-species"><i>Triticum aestivum</i></span>
    <span class="kg-years">2019</span>
    <span class="kg-refcount">1 reference</span>
  </div>

  <p class="kg-longtext kg-clamp-2">Cell wall invertase positively regulating resistance to Fusarium crown rot …</p>
  <button type="button" class="btn btn-link btn-sm kg-expand" aria-expanded="false">Show more</button>
</article>
```

CSS 要点（新类名统一 `.kg-` 前缀，不覆盖 Bootstrap）：
```css
.kg-gene-card{background:#fff;border:1px solid var(--line);border-left:4px solid var(--leaf);
  border-radius:10px;padding:14px 16px;margin-bottom:10px}
.kg-gene-card:hover{border-color:rgba(17,134,83,.34);box-shadow:0 10px 26px rgba(8,69,47,.07)}
.kg-card-head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.kg-gene-name{font-size:16px;font-weight:700;color:var(--forest-deep);font-style:italic}
.kg-gene-id{font-size:12px;color:var(--forest);font-family:var(--utility);overflow-wrap:anywhere}
.kg-card-meta{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-top:6px;font-size:13px;color:#4d6559}
.kg-card-meta .badge{font-size:11px}
.kg-longtext{margin:8px 0 0;font-size:13px;line-height:1.7;color:#3b5347;max-width:90ch;overflow-wrap:anywhere}
.kg-clamp-2{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.kg-longtext.is-open{display:block;overflow:visible}
```
卡片整体可点击进详情？保留 **gene_id 链接**（与现在一致）+ gene_name 也链；不做整卡 `<a>`（避免嵌套交互元素）。

### 4.3 计数 / 空态 / 错误态 / 分页

| 状态 | 呈现 |
|---|---|
| 首屏（空 term） | 自动加载第 1 页（`/all?limit=50&offset=0`），`#res-info` = `Showing 1–50 of 1,420 · Browse all` |
| 搜索有结果 | `Showing 1–50 of N · query "VRN1" · field: All Fields` |
| 分页 | `‹ Prev   Page 1 / 29   Next ›`（每页 50，按钮 disabled 状态清晰；换页后滚动到结果区顶部） |
| 搜索无结果 | `alert alert-warning`：`No known gene matches "xxx". Try another keyword, or check the field selector.` + Reset 按钮 |
| 筛选后无结果 | `alert alert-warning`：`No genes match the current filters.` + `Clear filters` |
| 接口失败 | `alert alert-danger` + `Retry` 按钮（保留 HTTP status/detail 文案） |
| 加载中 | `#res-info` = `Searching…`，结果区 `role="status"` 文案 |

**分页对 backend 的依赖（Q1）**：`/known/all` 与 `/known/search` 增加可选 `limit`/`offset`（默认保持全量以兼容旧调用；前端永远显式传）；`total` 已存在。若 backend 本期不给：降级方案 = 前端拉全量后客户端分页（payload 1.1 MB，可接受但不推荐）+ 首屏只渲染 50 条。

### 4.4 可选筛选条（客户端 Phase-1 vs 服务端 Phase-2）

位置：结果区上方、`#res-info` 下一行；三个筛选组，每个 chip 显示 `值 (计数)`：

| 组 | 值来源 | 交互 |
|---|---|---|
| Functional category | 固定 5 值（§2.2）+ 计数从当前结果集算 | 多选 chip；未选 = 全选 |
| Research strategy | 3 值（Not reported 也列出，计数 78） | 多选 chip |
| Species | 当前结果集按 `species_primary` 聚合，取 Top 8 + `Other` | 多选 chip；单物种结果时不显示该组 |

- **Phase 1（推荐，随本次一起做）**：纯客户端过滤（`lastResults.filter(...)`），即时、零后端依赖，筛选后重新渲染当前页（分页基于过滤后数组）；计数基于「未筛选的当前结果集」。
- **Phase 2（可选）**：如果后端愿意给 `/search` 加 `functional_category`/`research_strategy`/`species` 参数，则改为服务端过滤 + 分页，前端只保留 UI。**本次不做**（§4 §4 契约没写，避免范围膨胀）。
- 筛选状态必须参与导出 CSV（导出「筛选后全部结果」）。
- 全量浏览（空 term）时，筛选只在已加载页范围内会误导 → 方案：空 term 走 `/all` 时**先不显示筛选计数**；或 Phase 1 只对搜索结果启用筛选，首屏浏览态不显示筛选条（推荐后者，简单且不误导）。→ 列入 Q10。

### 4.5 导出 CSV 新列清单与顺序（19 列）

| # | Header | 数据源 | 说明 |
|---|---|---|---|
| 1 | Gene ID | `gene_id` | |
| 2 | Gene name | `gene_name` | |
| 3 | Reference genome ID | `reference_genome_id` | 新增 |
| 4 | Chromosome | 解析 label（`chromosome`/fallback） | 1A/1H/chr51 |
| 5 | Chromosome position | `chrom_pos` 全文 | 含参基因组前缀 |
| 6 | Genome / reference | 解析前缀（`Refv1.0`…） | |
| 7 | Species (normalized) | `species_primary` | 新增 |
| 8 | Species (raw) | `species` | 原文，含材料描述 |
| 9 | Functional category | `functional_category` | 新增 |
| 10 | Research strategy | `research_strategy` | 新增 |
| 11 | Phenotype | `phenotype` 全文 | 长文本，RFC4180 引号包裹 |
| 12 | Protein family | `protein_family` | 全文 |
| 13 | Validation methods | `validation_methods`（数组 join `; `） | |
| 14 | Cloning method | `cloning_method` | |
| 15 | Key results | `key_result`（join `\n\n` 或 `; `） | 全文；注意 Excel 单元格上限 32767 字符（最长 3051，安全） |
| 16 | Function description | `function_description` | 全文 |
| 17 | Publication year(s) | `publication_years` join `; ` | |
| 18 | DOIs | `references[].doi` join `; `（或 `dois[]`） | |
| 19 | Detail URL | `location.origin + detailUrl(r)` | 用 clone_id |

实现要点（在现有 `app/static/genes/index.html:485-531` 基础上改）：
- 保留 `csvField()` 的 RFC4180 转义与 UTF-8 BOM（`index.html:512-514`）。
- 加 **Excel 公式注入防护**：单元值 `^[=+\-@\t\r]` 时前置 `'`（防 `=HYPERLINK(...)` 型 payload；新数据虽无，但测试用例要覆盖）。
- 多值数组统一 `join('; ')`（现有 `csvField` 已处理 Array）。
- 导出范围：**当前查询的筛选后全部结果**，不是当前页。
  - **2026-10-28 调整（用户要求）**：导出按钮仅在有搜索结果时显示；浏览态（全量 1,420 行）隐藏，避免逐行 `/known/{id}` 富化的全量导出。文案改为 "Export Search Results (CSV)"。实现：点击导出时若 `filteredCount > loadedCount`，先 `GET` 剩余页（或一次 `limit=0`）再生成；按钮期间 disabled + 文案 `Preparing CSV…`。
- 文件名保持 `known_genes_<term>_<timestamp>.csv`（`index.html:521-525`），空 term 为 `all`。

### 4.6 Search 脚本改造清单（函数级）

| 现函数（行号） | 改造 |
|---|---|
| `esc()` `index.html:250-255` | 保留；新增 `escAttr()`（同实现即可）、`stripNothing()`（**不做标签剥离**，见 §2.4） |
| `detailUrl()` `260-263` | 保留 clone_id 优先；**不得** fallback 到含 `/` 的 gene_id（新增正则校验，非法则返回 `/genes/`） |
| `chromLabel()` `268-272` | 重写 `parseChrom(pos)`：`/chr\s*([0-9]+[A-Za-z]{0,2})/i` 优先，其次 `/\b([0-9]+[A-Za-z])\s*:/`，输出 `{label, genome}`；T.ponticum `51/54` 显示 `chr51/chr54`（见 §2.2） |
| `WHEAT_CHROMS/isWheatChrom` `277-279` | Stats 用新分组逻辑（服务端给 `group`）；列表不再用它过滤 |
| `loadAllGenes()` `281-303` | 改为 `fetchPage(term, field, offset, limit)`；缓存 `{records,total,query}`；Stats 不再复用 |
| `runSearch()` `308-375` | 增加 field/page 状态；统一空态/错误态；`renderResults()` 只渲染当前页 + 分页条 |
| `renderResults()` `316-348` | 按 §4.2 重写卡片；加徽章/ref id/年份/筛选后计数 |
| 新增 `applyFilters()/renderFilterBar()` | 客户端筛选（Phase 1） |
| 新增 `toggleLongText()` | 事件委托处理 `.kg-expand` |
| `loadStats()` `439-480` | 移到 §5（吃 `/stats`） |
| `CSV_COLUMNS` `485-493` / `buildCsv()` `502-514` / `exportCsv()` `516-531` | 按 §4.5 改列 + 导出全部筛选结果 + 注入防护 |
| 初始化 `551-553` | 保留「首屏自动加载」但改成分页；`statsLoaded` 逻辑保留 |

建议抽公共文件 `app/static/genes/known_gene_common.js`（新文件，`/genes` 静态挂载自动可访问）：放 `esc/parseChrom/parseRefGenome/splitMulti/familyHead/safeDoi/detailUrl/geneHubUrl/clamp toggle/csv helpers`，index/detail 共用（detail 也会用到 esc/split/safeDoi）。**注意**：新增静态文件不需要改 `main.py` mount（`main.py:143` 已挂 `/genes` 目录）。

---

## 5. Stats tab 重构（对接新 `/api/genes/known/stats`）

> 落点：`index.html:173-221`（DOM）、`index.html:74-94`（CSS）、`index.html:385-480`（渲染逻辑）。

### 5.1 建议的 `/stats` 响应契约（给 Lead/backend 对齐）

按 §4 草案细化（键名可微调，前端按下表消费；缺键用 `|| []` 容错）：

```json
{
  "success": true,
  "data": {
    "total": 1420,
    "species": [{"name": "Triticum aestivum", "count": 1260, "raw_forms": 42}, ...],
    "species_raw_count": 296,
    "chromosomes": [
      {"label": "1A", "count": 55, "group": "wheat"},
      {"label": "1H", "count": 13, "group": "other"}
    ],
    "functional_category": [{"name": "Biotic & Abiotic Stress", "count": 776}, ...],
    "research_strategy": [{"name": "Reverse genetics", "count": 1061}, ...],
    "phenotype_tags": [{"tag": "not determined", "count": 65}, ...],
    "phenotype_tag_distinct": 564,
    "publication_year": [{"year": 1998, "count": 2}, ...],
    "references": {"entries": 1570, "unique_dois": 883},
    "notes": {"multi_year_rows": 115, "multi_species_rows": 236, "rows_without_tags": 463}
  }
}
```

关键设计点（需 backend 确认，Q4）：
1. `species` 用归一化 `species_primary`，附 `raw_forms` 供 tooltip（如 `Triticum aestivum (42 raw forms)`）。
2. `chromosomes` 由服务端产出 **38 条**并带 `group: "wheat" | "other"`（避免前后端各自解析不一致）；`count` 口径：同一行同一标签只计一次（与本文件统计一致）。
3. `phenotype_tags` 服务端拆标签：`split(/;/)` → trim/lowercase → 去重（行内）→ 丢弃 >80 字符自由文本 → 计数；同时给 `distinct` 供 KPI 副标题。
4. `publication_year`：多值行按年份分别计数（合计 1535 > 1420，页面需注明）；另给 `multi_year_rows`。
5. `references.entries`/`unique_dois` 供 KPI（口径见 §2.4）。

### 5.2 页面结构与图表规格

```
#tab-stats
├─ #stats-loading（role=status）
├─ #stats-error（alert + Retry）
└─ #stats-content
   ├─ h5 Dataset Overview + muted 说明（已改为服务端聚合）
   ├─ #stats-kpi  （6 张 .kg-kpi-card，grid: 2/3/6 列）
   ├─ .row
   │   ├─ #chart-species     （Species distribution，Top 15 + Other）
   │   └─ #chart-category    （Functional category，5 条）
   ├─ #chart-chrom-wheat     （小麦 21 条，vbar）
   ├─ #chart-chrom-other     （其他 17 种标签，bar-row）
   ├─ .row
   │   ├─ #chart-strategy    （Research strategy，3 条）
   │   └─ #chart-year        （Publication year 1998–2026，vbar）
   └─ #chart-phenotype       （Top 20 phenotype tags，bar-row，label 2 行截断）
```

| 图 | 形式 | 数据 | 排序/规则 | 备注 |
|---|---|---|---|---|
| KPI×6 | `.kg-kpi-card` | total / species / wheat chrom / categories / strategies / references | — | 值 `1,420` 千分位；副标题小字给口径（如 `296 raw forms`、`21/21 + 17 other types`、`1,570 entries · 883 unique DOIs`） |
| Species distribution | 横向 `.kg-bar-row` | `species` | count desc，Top 15 + 其余合并 `Other (N species)` | label italic；太长截断 1 行 + title |
| Functional category | 横向 bar | `functional_category` | count desc；颜色与列表徽章一致 | 5 条 |
| Research strategy | 横向 bar | `research_strategy` | 固定顺序 reverse/forward/not reported | 3 条 |
| Chromosome（wheat） | 竖直 `.kg-vbar` | `chromosomes[group=wheat]` | 固定自然序 1A…7D；21 条全显（0 也画空柱） | `maxOverride` 固定同一 Y 轴 |
| Chromosome（other） | 横向 bar | `chromosomes[group=other]` | 自然序（1H…7H, 1R, 6R, 1S, 2V, 6S, 6U, 6V, 7E, chr51, chr54） | 17 条；非小麦标签与小麦区区分色（`--wheat` 系） |
| Publication year | 竖直 vbar | `publication_year` | 年份升序 1998–2026 | 注明「多文献行按年重复计数」（115 行多值） |
| Phenotype tags | 横向 bar | `phenotype_tags` | count desc，Top 20 | label 2 行截断（`.kg-bar-label.kg-clamp-2`），title 全文 |

### 5.3 DOM 骨架 + 渲染逻辑要点

```html
<h5 class="kg-section-h">Dataset Overview</h5>
<p class="text-muted small">Aggregated server-side from <code>/api/genes/known/stats</code>; the full dataset is no longer downloaded to the browser.</p>

<div id="stats-kpi" class="kg-kpi-grid"><!-- 6 × .kg-kpi-card --></div>

<div class="row">
  <div class="col-12 col-lg-6"><div class="card mb-4"><div class="card-body">
    <h6 class="card-title">Species distribution</h6><div id="chart-species" class="kg-chart"></div>
  </div></div></div>
  <div class="col-12 col-lg-6"><div class="card mb-4"><div class="card-body">
    <h6 class="card-title">Functional category</h6><div id="chart-category" class="kg-chart"></div>
  </div></div></div>
</div>

<div class="card mb-4"><div class="card-body">
  <h6 class="card-title">Genes per wheat chromosome</h6>
  <div id="chart-chrom-wheat" class="kg-chart"></div>
  <h6 class="card-title mt-4">Other Triticeae chromosome types (barley, rye, wild relatives)</h6>
  <div id="chart-chrom-other" class="kg-chart"></div>
</div></div>
<!-- strategy / year / phenotype 同构 -->
```

渲染函数（替换 `renderBars`/`renderVerticalBars`）：
- `renderKpi($el, items)`：`items = [{label, value, note}]`。
- `renderBarRows($el, entries, opts)`：`opts = {valueKey, labelKey, maxLabelClamp, colorClass, labelItalic, otherBucket}`；内部生成 `.kg-bar-row`（grid 布局，见 §7.3），`title` 放完整 label。
- `renderVBars($el, entries, opts)`：`opts = {labelKey, valueKey, maxBarLabelChars, minColWidth}`；21 帧自适应（`flex:1 1 0; min-width:22px`），不产生页面级横向溢出。
- `loadStats()`：`$.getJSON('/api/genes/known/stats')` 一次；`statsLoaded` 缓存 + 失败可重试；**不再调用 `loadAllGenes()`**。
- 全部使用 `esc()`；数字 `toLocaleString('en-US')`；空数组 → `No data.` muted。
- 不用任何图表库（保持本地 Bootstrap/jQuery 依赖，避免新增 CDN/库引入，符合 §VII.9）。

### 5.4 验收数值（上线前逐项对照）

| 指标 | 期望（v2055 全量） |
|---|---|
| total | 1420 |
| species（归一化） | ≈24–26（以 backend 规则为准；raw_forms 总数 296） |
| chromosomes | 38 条（wheat 21 + other 17）；非小麦行 95 |
| functional_category | 5 值：776/202/154/146/142 |
| research_strategy | 3 值：1061/281/78 |
| phenotype tags Top1 | `not determined` 65 |
| publication_year 合计 | 1535（=1420 + 115 多值行）；年份 1998–2026；2022 峰 254 |
| references | entries 1570 / unique DOIs 883 |
| `/stats` payload | 应 < 20 KB（远小于 /all） |

---

## 6. detail.html 重构

> 落点：整个文件（395 行）。目标：V2 shell 框架 + 新 section 顺序 + 长文本规范 + 新字段。**保持 URL 不变**：`/genes/detail.html?id=<clone_id>`（`index.html:260-263` 生成的链接不能失效）。

### 6.1 框架迁移到 `_v2` shell（照 §XII / `_v2/README.md` 步骤）

| 步骤 | 操作 | 行号 |
|---|---|---|
| 1 | 删除每页 visit 统计脚本块（shell.js 统一接管，避免双计） | 删 `detail.html:10-44` |
| 2 | 保留本地资源：bootstrap css / jquery / bootstrap.bundle；在 bootstrap css **之后**加 `<link rel="stylesheet" href="/api/v2shell/shell.css">` | 在 `detail.html:8` 后插入；`46-47` 保留 |
| 3 | 改写 `<title>`（按 Q11 定：推荐 `KnownGene - WheatOmics`） | 改 `detail.html:6` |
| 4 | 删除旧框架 CSS（`#home_header`/`#header-tabs`/`#home_footer`/visit-stats 共 61-86 行） | 删 `detail.html:61-86` |
| 5 | 删除旧 header DOM | 删 `detail.html:114-159` |
| 6 | 删除旧 footer DOM（LOGO 图/邮箱/visit-stats） | 删 `detail.html:234-257` |
| 7 | body 骨架改为：`<div id="v2-shell-header"></div>` + `<main id="main-content">`（含 `.news-hero` 与 `.news-body > .container`）+ `<div id="v2-shell-footer"></div>` + `<script src="/api/v2shell/shell.js"></script>`（在页面业务脚本之前） | 插在 `113` 之后、`161` 前后 |
| 8 | 页面自有 CSS 改用 token（`--forest/--leaf/--line/--muted/--ink`），组件优先用 `.card/.btn/.badge/.v2-chip`；新类统一 `.kg-` | 重写 `detail.html:88-109` |
| 9 | 保留全部功能 id 与页面 JS 结构，只替换框架；`document.title = gene_id + ' - WheatOmics'` 保留 | `detail.html:285` |
| 10 | 静态自检：`grep -c "api/v2shell/shell" detail.html` → 期望 2；`grep -cE "home_header|header-tabs|home_footer|visit-stats"` → 期望 0 | §7.4 |

注意：
- shell.js 注入在 DOMContentLoaded；页面脚本用 `$(function(){…})` 不冲突，但`shell.js` 要在业务脚本前 include（沿用 index.html:232-234 顺序）。
- 旧 footer 的「访问统计」被 shell footer 替代；analytics 从 `pathname+search` 变为 `pathname`（行为变化，知会即可）。
- 迁移后基线 spa_visual_check 的 FAIL 项（footer 邮箱对比度、无 alt LOGO）自然消失；新内容需保证正文对比度 ≥4.5（`--muted` `#66766e` on white ≈4.6，正文用 `--ink` `#163128`）。

### 6.2 新 section 顺序与 DOM 骨架

顺序（按任务要求重排）：
**Detail head → Overview meta 4 卡 → Reference genome ID(+GeneHub) → Protein family → Functional category / Research strategy / Validation methods 徽章 → Phenotype（全文）→ Key results → Function description → Cloning method(+details 折叠) → References（含 year）→ Species（学名+材料说明折叠）→ Submitted by（空则隐藏）**

```html
<main id="main-content">
  <section class="news-hero">
    <div class="container news-hero-inner">
      <div>
        <p class="news-kicker">WheatOmics 2.0 · Data resource</p>
        <h1 class="news-title">Known <em>Gene</em></h1>
        <p class="news-lead">Curated functional annotation, evidence and references for one known gene.</p>
      </div>
      <div class="news-hero-mark" aria-hidden="true"><svg class="icon"><use href="#i-gene"/></svg></div>
    </div>
  </section>

  <section class="news-body"><div class="container">
    <a href="/genes/" class="back-link kg-back">← Back to KnownGene search</a>

    <div id="loading" class="loading-wrap"><div class="spinner-border text-primary" role="status"></div>
      <p class="mt-2 text-muted">Loading gene…</p></div>
    <div id="error-box" class="alert alert-danger" hidden></div>

    <div id="detail-content" hidden>
      <!-- 1) head -->
      <header class="kg-detail-head">
        <h2 class="kg-gene-name" id="d-gene-name"></h2>
        <p class="kg-gene-id" id="d-gene-id">—</p>
        <div class="kg-badges" id="d-badges"></div>
        <p class="kg-meta" id="d-meta"></p>
      </header>

      <!-- 2) Overview meta 4 卡 -->
      <div class="row" id="d-overview">
        <div class="col-6 col-md-3"><div class="kg-meta-card">
          <div class="kg-meta-label">Chromosome</div>
          <div class="kg-meta-value"><span id="d-chrom" class="badge badge-secondary kg-chrom">—</span></div>
          <div class="kg-meta-sub kg-mono" id="d-chrom-pos"></div>
        </div></div>
        <div class="col-6 col-md-3"><div class="kg-meta-card">
          <div class="kg-meta-label">Species</div>
          <div class="kg-meta-value"><i id="d-species">—</i></div>
          <div class="kg-meta-sub" id="d-species-sub"></div>
        </div></div>
        <div class="col-6 col-md-3"><div class="kg-meta-card">
          <div class="kg-meta-label">Publication years</div>
          <div class="kg-meta-value kg-years" id="d-pubyear">—</div>
        </div></div>
        <div class="col-6 col-md-3"><div class="kg-meta-card">
          <div class="kg-meta-label">References</div>
          <div class="kg-meta-value" id="d-refcount">—</div>
        </div></div>
      </div>

      <!-- 3) Reference genome ID -->
      <section class="card kg-section" id="card-refgenome" hidden><div class="card-body">
        <h6 class="card-title">Reference genome ID</h6>
        <p class="mb-0"><span class="kg-mono" id="d-refgenome">—</span>
          <a class="btn btn-sm btn-outline-primary ml-2" id="d-genehub" target="_blank" rel="noopener noreferrer" hidden>Open in GeneHub ↗</a></p>
      </div></section>

      <!-- 4) Protein family -->
      <section class="card kg-section" id="card-protein-family" hidden><div class="card-body">
        <h6 class="card-title">Protein family</h6>
        <span class="v2-chip" id="d-protein-family-head"></span>
        <p class="kg-longtext kg-clamp-6" id="d-protein-family"></p>
        <button type="button" class="btn btn-link btn-sm kg-expand" aria-expanded="false" aria-controls="d-protein-family">Show more</button>
      </div></section>

      <!-- 5) Annotation badges -->
      <section class="card kg-section" id="card-annotations" hidden><div class="card-body">
        <h6 class="card-title">Functional category &amp; research strategy</h6>
        <div class="kg-badges" id="d-badges-detail"></div>
        <h6 class="mt-3">Validation methods</h6>
        <div class="v2-chip-row" id="d-validation"></div>
        <div class="kg-other-assays" id="d-validation-other" hidden></div>
      </div></section>

      <!-- 6) Phenotype 全文 -->
      <section class="card kg-section" id="card-phenotype" hidden><div class="card-body">
        <h6 class="card-title">Phenotype</h6>
        <p class="kg-longtext kg-clamp-6" id="d-phenotype"></p>
        <button type="button" class="btn btn-link btn-sm kg-expand" aria-expanded="false" aria-controls="d-phenotype">Show more</button>
      </div></section>

      <!-- 7-9) Key results / Function description / Cloning method -->
      <section class="card kg-section" id="card-key-results"><div class="card-body">
        <h6 class="card-title">Key results</h6>
        <p class="kg-longtext kg-clamp-12" id="d-key-result"></p>
        <button type="button" class="btn btn-link btn-sm kg-expand" aria-expanded="false" aria-controls="d-key-result">Show more</button>
      </div></section>

      <section class="card kg-section" id="card-function-desc" hidden><div class="card-body">
        <h6 class="card-title">Function description</h6>
        <p class="kg-longtext kg-clamp-8" id="d-function"></p>
        <button type="button" class="btn btn-link btn-sm kg-expand" aria-expanded="false" aria-controls="d-function">Show more</button>
      </div></section>

      <section class="card kg-section" id="card-cloning" hidden><div class="card-body">
        <h6 class="card-title">Cloning method</h6>
        <div class="v2-chip-row" id="d-cloning-method"></div>
        <button class="btn btn-link btn-sm" type="button" data-toggle="collapse" data-target="#d-cloning-desc-wrap" aria-expanded="false" aria-controls="d-cloning-desc-wrap" id="d-cloning-desc-label" hidden>Details</button>
        <div class="collapse" id="d-cloning-desc-wrap"><p class="kg-longtext" id="d-cloning-desc"></p></div>
      </div></section>

      <!-- 10) References（安静标题：纯 h6，不加 card-title，MAINTENANCE §VII.4） -->
      <section class="card kg-section" id="card-references"><div class="card-body">
        <h6>References</h6>
        <ol class="kg-refs" id="d-references"></ol>
      </div></section>

      <!-- 11) Species + material（默认折叠） -->
      <section class="card kg-section" id="card-species" hidden><div class="card-body">
        <h6 class="card-title">Species &amp; materials</h6>
        <p class="kg-longtext kg-clamp-4" id="d-species-raw"></p>
        <button type="button" class="btn btn-link btn-sm kg-expand" aria-expanded="false" aria-controls="d-species-raw">Show more</button>
      </div></section>

      <!-- 12) Submitted by（空则隐藏） -->
      <section class="card kg-section" id="card-author" hidden><div class="card-body">
        <h6 class="card-title">Submitted by</h6>
        <p class="mb-0" id="d-author"></p>
      </div></section>
    </div>
  </div></section>
</main>
<div id="v2-shell-footer"></div>
<script src="/api/v2shell/shell.js"></script>
<script>/* 页面业务脚本（保留现有 esc/doiUrl/showError/renderDetail 骨架，按 §6.4 扩展） */</script>
```

### 6.3 旧 section 去留表

| 旧 section（行号） | 处置 |
|---|---|
| head gene_name/gene_id/meta（`172-176`） | **保留 + 扩展**（加徽章行；ref genome 独立卡） |
| Meta 卡 Chromosome（`178-184`） | **保留卡位，改内容**（badge label + mono 全文） |
| Meta 卡 Species（`185-190`） | **保留卡位，只放归一化学名**；原文移到新 `#card-species` |
| Meta 卡 Phenotype（`191-196`） | **删除卡位**，改为独立全文 section `#card-phenotype` |
| Meta 卡 Publication year（`197-203`） | **保留卡位，改多值 chips**；同时 References 每项显示 year |
| Key results（`205-208`） | **保留**，长文本 clamp + 展开；合并「新数据单条文本」渲染 |
| Function description（`210-213`） | **保留**，clamp + 展开 |
| Cloning method（`215-220`） | **保留并合并**：method chips + description 折叠 |
| References（`222-225`） | **保留重写**：year + title + DOI；标题改纯 h6 |
| Submitted by（`227-230`） | **保留但空则整卡隐藏** |
| —（新增） | `#card-refgenome`、`#card-protein-family`、`#card-annotations`（category/strategy/validation）、`#card-species` |

### 6.4 详情页 JS 改造清单

| 现函数（行号） | 改造 |
|---|---|
| `esc()` `detail.html:260-265` | 保留 + 移入公共 JS（若抽公共文件） |
| `doiUrl()` `267-272` | 保留但加白名单：`^10\.\d{4,9}/\S+$` → `https://doi.org/…`；`http(s)://` 仅当 host 为 doi.org 时保留；其他返回 `''` |
| `showError()` `274-278` | 保留（错误态 DOM id 不变） |
| `renderDetail()` `280-365` | 拆为：`renderHead(d)` / `renderOverview(d)` / `renderRefGenome(d)` / `renderProteinFamily(d)` / `renderAnnotations(d)` / `renderPhenotype(d)` / `renderKeyResults(d)` / `renderFunction(d)` / `renderCloning(d)` / `renderReferences(d)` / `renderSpecies(d)` / `renderAuthor(d)`；每个函数负责「有值显示 / 无值隐藏」 |
| `renderMeta` `290-294` | clone_id + submission_date（空则不显示）；补 `reference_genome_id` 行？不，ref 独立卡 |
| `renderReferences` `317-336` | 按 §3.5 重写；优先 `d.references[]`；`d.paper_title`/`d.publication_years` 兜底；数量不齐容错 |
| `renderKeyResults` `338-349` | 新数据 `key_result` 为单元素数组 → 渲染为单段 `<p>`（不再是 `<li>` 列表） |
| `renderAuthor` `351-364` | 空则 `#card-author` 隐藏（不再显示 `—`） |
| 新增 `toggleLongText()` | 事件委托 `.kg-expand`（同一按钮切换 `is-open` + `aria-expanded` + 文案 `Show more/Show less`） |
| 新增 `familyHead()` / `splitMulti()` / `parseChrom()` / `safeDoi()` / `fmtYears()` | 公共工具（建议放 `known_gene_common.js`，index/detail 共用） |
| `$.getJSON('/api/genes/known/' + id)` `378` | 保留；URLSearchParams 读 `id`（`367-373`）保留；`document.title` 逻辑保留 |

### 6.5 详情页 CSS 规范（token 化）

```css
.kg-detail-head{background:#fff;border:1px solid var(--line);border-left:4px solid var(--leaf);
  border-radius:12px;padding:20px 24px;margin-bottom:16px}
.kg-detail-head .kg-gene-name{font-size:24px;color:var(--forest-deep);font-style:italic;font-weight:700;margin:0 0 4px}
.kg-gene-id{font-family:var(--utility);font-size:13px;color:var(--muted);margin:0 0 6px;overflow-wrap:anywhere}
.kg-badges{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.kg-meta{font-size:12px;color:var(--muted);margin:6px 0 0}
.kg-meta-card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px;height:100%}
.kg-meta-label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
.kg-meta-value{font-size:16px;color:var(--ink);margin-top:4px;font-weight:600;overflow-wrap:anywhere}
.kg-meta-sub{font-size:11px;color:var(--muted);margin-top:2px;overflow-wrap:anywhere}
.kg-section .card-body h6.card-title{font-size:14px;color:var(--forest-deep)}
.kg-longtext{font-size:14px;line-height:1.75;color:var(--ink);max-width:78ch;overflow-wrap:anywhere}
.kg-clamp-4/6/8/12{display:-webkit-box;-webkit-box-orient:vertical;overflow:hidden}
.kg-refs{padding-left:20px;margin:0}
.kg-ref{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline;margin-bottom:10px;line-height:1.6}
.kg-ref-year{font-family:var(--utility);font-size:12px;color:var(--forest);background:var(--mist);
  border:1px solid var(--line);border-radius:6px;padding:1px 6px}
.kg-ref-title{flex:1 1 320px;min-width:0;color:var(--ink);overflow-wrap:anywhere}
.kg-ref a{font-family:var(--utility);font-size:12px;color:var(--leaf);overflow-wrap:anywhere}
```

（`--ink` `#163128` on white ≈ 13:1；`--muted` 仅用于小字，需 ≥4.5 → 实测 #66766e on #fff ≈ 4.6，边缘通过，建议小字仍优先用 `#4d6559` 类深色，最终以 spa_visual_check 为准。）

---

## 7. 兼容、规范与验收

### 7.1 规范 checklist（MAINTENANCE §VII / §XII）

| 项 | 要求 | 落点/验法 |
|---|---|---|
| `lang` | `en` | 两页 `<html lang="en">`（已满足） |
| charset/viewport/title/favicon | 4 件齐全；title 统一 `KnownGene - WheatOmics` | `index.html:4-7`、`detail.html:4-7`；§7.4 grep |
| Bootstrap/jQuery | 只允许本地 4.5.3 / 1.9.1，无 CDN | `index.html:8/12/13`、`detail.html:8/46/47`；新增代码不引任何第三方库 |
| `_v2` shell | `<div id="v2-shell-header|footer">` + `/api/v2shell/shell.css|js` | 两页各 2 处引用；detail 迁移后旧框架关键字为 0 |
| 标题层级 | 页面标题 hero `h1`；卡片内小节 `h6`；References 用纯 `h6` 不加 card-title | detail §6.2 已按此写；index 保持现有 hero h1 |
| 卡片/自定义 CSS | 不改 Bootstrap 内置类；新类 `.kg-` 前缀；引用块独立卡 | §4.2/§6.5 |
| 静态挂载 | `/genes` 目录已挂载（`main.py:143`），新增 `known_gene_common.js` 无需改 Python | 部署后 `curl /genes/known_gene_common.js` → 200 |
| 不改生成物 | 不手改 `_v2/shell.*`（由 `scripts/extract_v2_shell.py` 生成） | code review |
| 文案 | 英文 UI；`Dataset Overview` 说明改为服务端聚合 | stats 文案 |

### 7.2 XSS / URL / CSV 安全

| 风险 | 规则 |
|---|---|
| 文本字段（含 `<`、`&`、引号） | **所有** dynamic 值经 `esc()` 后再拼 HTML，或用 `.text()`/`textContent`；禁止裸 `innerHTML` |
| 不做 stripTags | 新数据无真实 HTML 标签；`p < 0.05` 等 `<` 是合法文本，粗暴 `stripTags` 会误删 → 只转义 |
| 链接 href | DOI 只允许 `^10\.\d{4,9}/\S+$` → `https://doi.org/`；GeneHub 只允许 `^TraesCS\d`/`^Traes_` 且 `encodeURIComponent`；全部 `target="_blank" rel="noopener noreferrer"` |
| 属性注入 | `title=`/`aria-label=` 等属性值用 `esc()` 并对 `"` 转义；`data-*` 不放原始长文本 |
| CSV 公式注入 | 单元格以 `= + - @ \t \r` 开头时前置 `'` |
| 后端文本损坏 | `#` 不能被替换成 `'`（§2.4/R6）——验收用例：详情页出现 `lines #1 and #2` 字样 |
| 搜索 term 回显 | `#res-info` 用 `.text()` 或 `esc()`（当前 `326` 已用 `.text()`，保持） |

### 7.3 响应式（360/390/768/1024/1440，无页面级横向溢出）

| 组件 | 360–480 | 768 | 1024/1440 |
|---|---|---|---|
| 结果卡片 | 单列；head 换行；meta wrap | 单列；badge 同行 | 单列（内容区 max 1180/`--page`），行宽受 `max-width:90ch` 约束 |
| KPI（6） | grid 2 列 | 3 列 | 6 列（`grid-template-columns:repeat(6,minmax(0,1fr))`） |
| 横向 bar-row | grid `minmax(0,46%) 1fr auto`，label `overflow-wrap:anywhere` | `minmax(0,34%) 1fr auto` | 同左；label 最长 2 行截断 |
| 小麦染色体 vbar（21） | 内部 `overflow-x:auto`，列 `flex:1 1 0;min-width:20px`（不撑破页面） | ≥768 时列宽 36–48px | 列宽 48px，居中 |
| 其他染色体 / 表型 Top20 | 横向 bar-row（label 2 行截断） | 同 | 同 |
| 详情 meta 4 卡 | `col-6`（2×2） | `col-6 col-md-3`（4×1） | 4×1 |
| 长文本 | clamp 更少行（如 phenotype 移动端 4 行）可选；不强制 | 同 | 6/8/12 行 |
| 校验 | `spa_visual_check` floor 的 `scrollWidth > viewport` 必须 0px | 同 | 同 |

### 7.4 验收步骤（命令级）

**A. 静态自检**
```bash
cd /Users/mashengwei/Desktop/markdown/wheatomics/FastAPI_backend_Port8000
node --check app/static/_v2/shell.js                       # 不改生成物，仅确认现状可解析
grep -c "api/v2shell/shell" app/static/genes/index.html      # 期望 2
grep -c "api/v2shell/shell" app/static/genes/detail.html     # 期望 2
grep -cE "home_header|header-tabs|home_footer|visit-stats" app/static/genes/detail.html  # 期望 0
grep -c "api/track/visit" app/static/genes/detail.html       # 期望 0（shell 接管）
curl -sI http://127.0.0.1:8000/genes/ | head                # 200 / uvicorn / text/html
curl -s  http://127.0.0.1:8000/genes/ | head -10            # charset/viewport/title/favicon/bootstrap/jquery
curl -s  http://127.0.0.1:8000/genes/known_gene_common.js | head -3   # 200（若新增公共文件）
```

**B. 本地起服务**（需 `.env`/DB；若本机无生产库，可用只读隧道或 §XII 的 scratch static server 做纯布局检查）
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**C. 多宽度渲染（本任务必跑，验收核心）**
```bash
# 列表页首屏（浏览态）
bash scripts/spa_visual_check.sh http://127.0.0.1:8000/genes/ \
  --label kg-new-index --widths 390,768,1440 --settle 1500

# 列表页搜索结果 + 结果区截图
bash scripts/spa_visual_check.sh http://127.0.0.1:8000/genes/ \
  --label kg-new-index-search --widths 768,1440 \
  --fill '#searchInp=VRN1' --click '#search-btn' --wait '#list-content .kg-gene-card' \
  --scroll-to '#list-content' --settle 1500

# Stats tab（点击后等 KPI/图出现）
bash scripts/spa_visual_check.sh http://127.0.0.1:8000/genes/ \
  --label kg-new-index-stats --widths 390,768,1440 \
  --click 'a[href="#tab-stats"]' --wait '#stats-kpi .kg-kpi-card' \
  --scroll-to '#stats-content' --settle 1500

# 详情页
bash scripts/spa_visual_check.sh "http://127.0.0.1:8000/genes/detail.html?id=1" \
  --label kg-new-detail --widths 390,768,1440 --wait '#detail-content' \
  --scroll-to '#detail-content' --settle 1500
```
期望：`Result: PASS`；唯一允许的 Warn = footer "Back to top ↑" 小点击目标。**任何 floor（横向溢出 / 破图 / JS 错 / 对比度 <3:1）都必须修。**

**D. 数据抽查（本地或线上）**
- 长文本：`gene_phenotype` 1677 字符行 → 列表 2 行截断、详情可展开全文。
- 大麦：搜索 `HORVU` → 卡片染色体 badge 应为 `3H` 而不是一长串 `chrom_pos`。
- 多 DOI：3 DOI 行 → 列表 `3 references`；详情 3 条含 year/title/DOI。
- 多 DOI 但不齐的行（§2.3 样本）→ 不丢 DOI，缺失年份显示 `—`。
- 空 author 行 → 详情无 Submitted by 卡。
- `#` 行（如 "lines #1"）→ 显示 `#1` 不是 `'1`。
- `<` 行（`p < 0.05`）→ 原样显示，不破版。
- 参考基因组 ID：TraesCS 行有 GeneHub 链接且 200；HORVU 行无链接、无死链。

**E. CSV**
- 导出（小结果集/全量各一次）→ Excel 打开：19 列、BOM 中文正常、长文本不串列、公式注入防护生效。
- 列顺序与 §4.5 一致；detail URL 可点开。

**F. 线上验收（部署后，Lead 批量执行）**
```bash
bash scripts/spa_visual_check.sh https://wheatomics.sdau.edu.cn/genes/ --label v2-genes --widths 390,768,1440
bash scripts/spa_visual_check.sh "https://wheatomics.sdau.edu.cn/genes/detail.html?id=1" --label v2-genes-detail --widths 390,768,1440
curl -s "https://wheatomics.sdau.edu.cn/api/genes/known/stats" | head -c 400   # success:true
```
与 §1.5 基线对比：列表页维持 PASS；详情页 FAIL → PASS（floor 清零）。

### 7.5 上线前对比截图检查点

| # | 页面/状态 | 宽度 | 检查点 |
|---|---|---|---|
| 1 | `/genes/` 初始浏览 | 390/768/1440 | hero 文案数字正确；首屏 50 张卡；分页条；无横向滚动 |
| 2 | `/genes/` 搜索结果 | 768/1440 | 徽章/物种/染色体/年份/ref genome 行齐全；phenotype 2 行；Show more 可用 |
| 3 | `/genes/` 筛选后 | 1440 | 计数 `Showing X of Y`；Clear filters；导出不报错 |
| 4 | `/genes/` Stats | 390/768/1440 | 6 KPI、7 图全出现；长 label 不溢出；无 `/all` 请求（DevTools Network） |
| 5 | `/genes/` 导出 CSV | — | 19 列 + 行数 = 筛选结果数 |
| 6 | `/genes/detail.html?id=1` | 390/768/1440 | 新 section 顺序；3 个长文本 Show more；References year；GeneHub 链接 |
| 7 | detail 空值行（无 author / 无 phenotype） | 390 | 对应卡隐藏，不留 `—` 空壳 |
| 8 | detail `p < 0.05` 行 / `#1` 行 | 768 | 原样文本、无转义痕迹、不破版 |

---

## 8. 实施拆分（15 项，0.5–3 h/项，含依赖与验收）

> 依赖顺序：**backend 契约 →（可先做 UI 骨架+fixtures）→ 详情页 → 列表页 → Stats → 视觉/上线**。每项都可独立提交、独立跑一次视觉检查。

| ID | 任务 | 文件/落点 | 估算 | 依赖 | 验收标准 |
|---|---|---|---|---|---|
| FE-1 | 契约冻结 + fixtures：把 §4 最终字段名、§5.1 `/stats` 形状、§2.3 引用容错规则写成 `docs/known_genes/_evidence/frontend_fixtures/*.json`（从 backend 联调样本存 3 份：普通行/长文本行/多 DOI 行） | `docs/known_genes/_evidence/` | 1 h | Q1/Q4/Q5 决策 | fixtures 可直接被本地 mock（临时改 `$.getJSON` 或 `python -m http.server` 替身）使用 |
| FE-2 | 公共 JS 工具：`esc/splitMulti/parseChrom/parseRefGenome/familyHead/safeDoi/detailUrl/geneHubUrl/fmtYears/toggleLongText` | 新文件 `app/static/genes/known_gene_common.js` | 2 h | FE-1 | `node --check` 通过；单测脚本（node 内联）覆盖 parseChrom 38 标签样本 |
| FE-3 | detail 框架迁移 shell（§6.1 行号级 10 步：删旧 header/footer/visit 脚本，加 shell） | `detail.html` | 2 h | — | grep 自检全过；`spa_visual_check` 不再 FAIL（此时内容仍是旧的） |
| FE-4 | detail 新 section/CSS（§6.2 骨架 + §6.5 CSS） | `detail.html` | 3 h | FE-3 | 8 类卡片齐；390/768/1440 无溢出 |
| FE-5 | detail JS 渲染（§6.4 12 个 render 函数 + 容错 + GeneHub/DOI 链接 + 空值隐藏） | `detail.html` + FE-2 | 3 h | FE-1/FE-2/FE-4 | 7 类数据抽查（§7.4 D）通过；XSS 探针通过 |
| FE-6 | detail 验收：spa_visual_check 3 宽度 + 交互（展开/折叠）+ 对比基线 | — | 1 h | FE-5 | §7.4 C/D 通过；截图存档 |
| FE-7 | index 头部/hero/field 下拉/placeholder/搜索请求加 `field`+分页参数 | `index.html:1-160, 308-380` | 1.5 h | FE-1（field 契约） | 选每个 field 发对应请求（DevTools 验证）；hero 文案更新 |
| FE-8 | index 结果卡片重做 + 分页 + 空态/错误态 + 长文本展开 | `index.html:161-170, 316-348, 485-553` + CSS | 3 h | FE-2/FE-7 | 浏览 50/页、搜索、翻页、空态、全部数据抽查通过 |
| FE-9 | index CSV 导出 19 列 + 导出全部筛选结果 + 注入防护 | `index.html:485-531` | 1.5 h | FE-8 | Excel 打开正常；行数=筛选数；§7.4 E |
| FE-10 | index 筛选条（Phase 1 客户端：category/strategy/species） | `index.html` 新增 DOM/CSS/JS | 2 h | FE-8 | 选中/取消即时生效；计数正确；导出跟随筛选（Q10 决策后） |
| FE-11 | Stats 接 `/stats` + 6 KPI + loading/error/retry | `index.html:173-221, 439-480` | 1 h | FE-1/backend `/stats` | Network 只有 `/stats`，无 `/all`；KPI 数值=§5.4 |
| FE-12 | Stats 7 组图表 + 响应式 CSS（§5.2/§5.3） | `index.html` + CSS | 2.5 h | FE-11 | 38 条染色体分组正确；390 无溢出；Top20 标签可读 |
| FE-13 | Stats 验收：spa_visual_check 点击 tab + 数据对照 + payload | — | 1 h | FE-12 | §5.4 全对；`/stats` <20 KB；截图存档 |
| FE-14 | 跨页收尾：title/aria/对比度小字/# 与 `<` 探针/无 alt 图/hero 静态数字 | 两页 | 1.5 h | FE-6/FE-10/FE-13 | 对比度 Warn 只剩 footer back-top；grep 自检全过 |
| FE-15 | 预发布检查单：本地 5 条命令 + 线上 2 条命令 + 8 张截图归档 + 回滚开关说明 | `docs/known_genes/`（记录） | 1 h | FE-14 | Lead 按单验收；线上与 §1.5 基线对比通过 |

**合计 ≈ 23–24 h**（不含 backend）。关键路径：FE-1 →（FE-3→FE-4→FE-5→FE-6）/（FE-7→FE-8→FE-9/10）/（FE-11→FE-12→FE-13）→ FE-14 → FE-15；其中 FE-8 与 FE-12 可并行（不同区域；但都改 `index.html`，建议串行提交避免冲突）。

**回滚开关**：两个 HTML 文件改前 `git diff` 留档；上线出问题 `git checkout -- app/static/genes/` 即可回旧版（静态文件部署后立即生效，不需重启；注意 `/api/v2shell` 是 Python 挂载，改它才要重启）。

---

## 9. 风险与开放问题

### 9.1 风险

| ID | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | backend 契约漂移（字段名/`/stats` 形状/引用拆分规则未定） | 前端返工 | FE-1 冻结 + fixtures；联调 curl 冒烟纳入验收 |
| R2 | `/all` 不分页仍 1.1 MB | 首屏慢、内存高 | 前端强制 `limit=50`；若 backend 不加参数则客户端分页降级（§4.3） |
| R3 | 长文本/超长 label 造成移动端横向溢出 | 视觉检查 FAIL | clamp + `overflow-wrap:anywhere` + grid `minmax(0,1fr)`；每阶段跑 spa_visual_check |
| R4 | 非 TraesCS 的 ref ID 死链 | 用户体验/404 | 只对 `^TraesCS`/`^Traes_` 生成链接；非可链纯文本 |
| R5 | XSS / CSV 注入 | 安全 | esc 全量、DOI/GeneHub 白名单、CSV 前缀转义；验收含探针 |
| R6 | `normalize_text` 把 `#` 改写为 `'` | 数据展示错误（"lines '1"）且前端无法修 | 作为 backend 阻塞项（Q7）；验收加 `#` 探针 |
| R7 | 详情页迁 shell 后访问统计口径变化（丢 `?id=`） | 统计轻微变化 | 知会 Lead；如必须保留 query 统计，可在 shell 之外补一次带 query 的 track（不推荐双计） |
| R8 | 1420 张卡片 + 7 图在低端机上卡顿 | 体验 | 分页 50 + 事件委托 + 无图表库；避免一次性 innerHTML 拼接 1420 卡 |
| R9 | 物种归一化由 backend 定，前端 KPI 数字可能与 data-profiler 报告不一致 | 验收数字争议 | KPI 副标题标注口径（raw_forms/归一化规则）；以 `/stats` 返回为准 |
| R10 | `/known/stats` 若注册在 `/known/{gene_id}` 之后会 404 | Stats 全挂 | backend 实施时前置路由（`gene.py:205` 之前）；联调第一件事 curl |
| R11 | "Not reported" 等受控值在列表隐藏策略变化 | 用户以为数据缺失 | 详情页明确展示；列表隐藏属于降噪，验收截图对比确认 |

### 9.2 待 Lead 决策（按优先级）

| Q | 问题 | 建议 | 影响面 |
|---|---|---|---|
| Q1 | `/all` 与 `/search` 是否加可选 `limit/offset`（默认保持全量兼容）？ | **加**；前端永远显式传 50/页。`/search` 同时修好 `publication_year` 的 SELECT | 列表首屏、payload、导出实现 |
| Q2 | `field` 枚举是否加 `chrom_pos`（现 §4 没有，但旧 UI 有 Chromosome 选项）？ | **加**（`LIKE %term%` on chrom_pos）；不要用 `/by-chromosome` 顶替（缺 clone_id/dois） | Search 下拉第 9 项 |
| Q3 | summary/detail 是否加便利解析键 `chromosome`（label）与 `genome_ref`（前缀）？ | 加则前端零解析、Stats/列表口径一致；不加则前端 `parseChrom` 兜底 | 卡片 badge、Stats 分组、CSV 第 4/6 列 |
| Q4 | `/stats` 最终 schema（§5.1）、物种归一化规则、染色体 `group` 字段、表型标签提取规则（丢弃 >80 字符自由段）、年份多值计数口径 | 按 §5.1 执行；`species_primary` 由 backend 统一 | Stats 全部图 |
| Q5 | references 拆分算法：按 `; ` 位置对应，16 行不齐时 year/title 补 `null`；多余题名如何处理？ | 按 §2.3/§3.5 容错；后端在响应里保序不丢 DOI | 详情 References、列表年限 |
| Q6 | `/all` 是否加 `slim=true`（长 phenotype 截断）或只靠分页？ | **只靠分页**（避免语义分叉）；搜索大结果集时若仍慢，再加 `limit` | payload |
| Q7 | `normalize_text()` 的 `#`→`'` 谁来修（backend 停用替换/新函数）？ | backend 必须修；前端不做任何补偿 | 详情/列表文本正确性（R6） |
| Q8 | 新数据没有 author/author_mail/submission_date：整表替换后是否保留旧 520 行的这些字段（按 gene_id/gene_name 匹配时）？ | 能保留则保留（详情「Submitted by」仅老行显示）；否则全部隐藏 | 详情 Submitted by、CSV |
| Q9 | 参考基因组链接目标确认：`/GeneHub/?search=<id>`（仅 TraesCS） | 采纳（已实测 200；HORVU/GenBank resolve 空） | 详情 ref 卡、列表 ref 行 |
| Q10 | 筛选条 Phase 1 只在「搜索结果」启用（浏览态不显示筛选）是否可接受？ | 可接受；避免对未加载全量数据做计数误导 | Search UX |
| Q11 | `<title>` 统一 `KnownGene - WheatOmics`（任务要求）还是 `KnownGene | WheatOmics 2.0`（`_v2/README` 新约定）？ | 按任务用 `KnownGene - WheatOmics`；若全站统一改新约定则两页都改 | 两页 title、验收 grep |
| Q12 | 列表卡片是否显示验证方法数量（`8 assays`）？ | 可显示为灰色小字（非必需） | 卡片信息密度 |
| Q13 | 导出 CSV 是否包含 `Key results`/`Function description` 全文（会让 1420 行 CSV ≈4–5 MB）？ | 默认包含（研究用途完整）；若在意文件大小可拆「摘要 CSV / 全文 CSV」 | CSV 体积 |

### 9.3 CONTEXT.md 修正建议（供 Lead 更新基线）

1. §1 第 5 行：`37 种染色体标签` → **38 种（21 小麦 + 17 其他；非小麦 95 行）**；T.ponticum `chr51/chr54` 可被 `chr(\d+[A-Za-z]{0,2})` 解析，不是「未匹配正则」。
2. §1 数据质量：`部分字段含 HTML 标签` → **v2055 实测 0 行真实 HTML 标签**；`<` 是 `p < 0.05` 等数学符号（5/8/12/9/7 行），`|` 1 行。前端仍全量转义，但不 strip。
3. §1 第 16 行：「820 个唯一 DOI」→ 明确为「整格字符串去重 820；拆分后唯一 DOI 元素 883；参考文献条目 1570」。
4. 建议新增一条事实：**新数据 23 行含 `#`**，与现有 `normalize_text` 冲突（R6/Q7）。

---

## 10. 附录

### 10.1 证据与基线

- 线上只读探测（2026-10-28）：`/genes/` 200；`/api/genes/known/all` 200（97,894 B，520 条）；`/api/genes/known/1` 200；`/api/genes/known/search?searchid=VRN1` 200（注意 `publication_year` 返回 null）；`/GeneHub/` 200；`/cgi-bin/geneDetail.py?search=TraesCS5A02G391700` 200；`/api/genes/detail/TraesCS5A02G391700` 200；`/api/genes/resolve?ID=HORVU.MOREX.r3.3HG0228170` → `count:0`；`/api/genes/resolve?ID=AB029887` → `count:0`。
- 基线多宽度报告（本机 ego-browser，`scripts/spa_visual_check.sh`，`--widths 390,768,1440`）：
  - `/genes/` → `PASS`（仅 footer back-top 小目标 Warn）
  - `/genes/detail.html?id=1` → `FAIL`（footer 邮箱对比度 2.82:1；5 图无 alt；3.54:1 警告若干）
  - 报告目录（临时，会过期）：`$TMPDIR/spa-check/kg-current-index-20261028-165759/`、`kg-current-detail-20261028-165759/`；重跑命令见 §7.4。
- 现行接口/字段事实：`app/api/routers/gene.py:50-277`（4 个 known 端点）、`app/schemas/gene.py:17-48`、`app/services/legacy_parsers.py:6-19`、`app/static/_v2/shell.js:34-138`（header/footer）、`app/static/_v2/README.md`、MAINTENANCE.md §VII（风格规范）/§IX（多宽度检查）/§XII（V2 shell）。

### 10.2 本文件用到的实测脚本（只读，可复现）

```bash
/Users/mashengwei/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3 - <<'PY'
import pandas as pd, re, collections, json
p="/Users/mashengwei/Desktop/markdown/陈甜甜/known-gene-paper-20260916/已知基因逐条提取清单_20261019-合集_修正版v2055_20261019.xlsx"
df=pd.read_excel(p, sheet_name=0, dtype=str).fillna('')
cols=list(df.columns); c=lambda i: df[cols[i]].astype(str).str.strip()
def spl(x): return [t.strip() for t in re.split(r';\s+', x) if t.strip()]
# 1) 染色体标签
lab=lambda x: (re.search(r'\bchr\s*([0-9]+[A-Za-z]{0,2})\b',x,re.I) or [None,''])[1]
# 2) payload 估算：用 §2.5 的口径构造 dict 后 json.dumps(..., separators=(',',':')) 求和
# 3) 引用数量不齐：比较 len(spl(col15)), len(spl(col14)), len(spl(col16))
print("shape", df.shape, "phenotype distinct", c(5).nunique(), "ref ids", c(1).nunique())
PY
```

> 具体数字推导（染色体 38 标签、`#` 23 行、16 行引用不齐、payload 1.10 MB 等）均来自上述同款 pandas 只读脚本；若后续 Excel 版本变动（v2055 仍可能被编辑），以 Lead/backend 的最终导入快照为准重新核对 §5.4 验收数值。

### 10.3 关键样本（UI 联调可直接用）

| 用途 | 样本 |
|---|---|
| 长 phenotype（1677 字符） | `phenotype` 最长行（"Cell wall invertase positively regulating resistance to Fusarium crown rot…"） |
| 多物种 + 材料长文本 | `Aegilops speltoides (donor of the Lr47 segment from chromosome 7S#1;…); Triticum aestivum (…)` |
| 大麦行（染色体解析） | `MorexV3 chr3H:595.906-595.909Mb` / `HORVU.MOREX.r3.3HG0228170` |
| T.ponticum（chr51/54） | `T.ponticum.v1 chr51:46.014-46.017Mb` |
| 多 DOI 正常行 | `AB029887`：2012 + 2024 + 2002 三篇 |
| 多 DOI 数量不齐行 | `TraesCS1D03G0038800`（2 DOI / 2 title / 1 year）、`TraesCS7A03G0602700`（2 DOI / 1 title） |
| 含 `#` 行（R6 探针） | `Tahsfa1 lines #1 and #2`、`7S#1` 染色体 |
| 含 `<` 行（转义探针） | key_result 中 `p < 0.05` |
| 空 author 行（迁移后） | 新数据所有行（除非保留旧字段）→ Submitted by 隐藏 |
| TraesCS 参考 ID 可链 | `TraesCS3B02G392800LC` → `/GeneHub/?search=TraesCS3B02G392800LC` |
| 非 TraesCS 不可链 | `HORVU.MOREX.r3.3HG0228170`、`AB029887`（GeneHub resolve 空） |
