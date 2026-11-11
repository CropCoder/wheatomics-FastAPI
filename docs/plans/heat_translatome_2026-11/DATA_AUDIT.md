# 热胁迫小麦籽粒 RNA-seq / Ribo-seq / TE 数据集体检与溯源报告

- 日期：2026-11-11
- 数据文件：`/Users/mashengwei/Desktop/markdown/陈甜甜/5_10_15DAA对照和热胁迫小麦籽粒的转录水平RNA_翻译水平Ribo_和翻译效率TE.xlsx`（11.9 MB）
- 分析对象：中国春（Triticum aestivum cv. Chinese Spring）发育籽粒 5/10/15 DAA，正常（CK）vs 42 °C 1 h 热胁迫（HS）的 RNA-seq FPKM、Ribo-seq FPKM、翻译效率 TE
- 结论先行：**数据本身可用且有上架价值（网站目前没有任何 Ribo-seq / translatome 项目），但它不是一份新的"再分析"结果，而是 Genome Biology 2025 论文补充表 S1 的逐格拷贝**。上架的关键工作不在"重算"，而在**基因 ID 版本转换、TE 缺失值处理、FPKM/TPM 口径说明、引用与授权**四处。

---

## 1. 文件结构

| 项 | 值 |
|---|---|
| 工作表 | 仅 1 个：`Table S1` |
| 尺寸 | 60,127 行 × 19 列（第 1 行分组表头，第 2 行列名，第 3–60,127 行为 60,125 个基因） |
| 第 1 行（合并单元格） | `B1:G1`=转录组；`H1:M1`=翻译组；`N1:S1`=翻译效率 |
| 第 2 行列名 | `Gene`、`RNA_5d_CK`、`RNA_5d_HS`、`RNA_10d_CK`、`RNA_10d_HS`、`RNA_15d_CK`、`RNA_15d_HS`、`Ribo_5d_CK`、`Ribo_5d_HS`、`Ribo_10d_CK`、`Ribo_10d_HS`、`Ribo_15d_CK`、`Ribo_15d_HS`、`TE_5DAA_CK`、`TE_5DAA_HS`、`TE_10DAA_CK`、`TE_10DAA_HS`、`TE_15DAA_CK`、`TE_15DAA_HS` |
| 数值列 | 12 列 FPKM + 6 列 TE = 18 列 |
| 基因数 | 60,125，无重复、无空行 |
| 附带信息 | 无样本元数据表、无重复列（标准差）、无原始 counts、无 TPM、无说明 sheet |

命名不一致：RNA/Ribo 列用 `5d`，TE 列用 `5DAA`（同为 5 days after anthesis）。列名里没有单位（需要额外说明是 FPKM）。

---

## 2. 数据溯源（本次核验的关键结论）

### 2.1 该文件 = GB 2025 补充表 S1，逐格一致

从 Genome Biology 2025 论文补充材料下载 `13059_2025_3848_MOESM2_ESM.xlsx`（23,142,257 bytes，md5 `85db3d05cae2e413b48c0739d0edc36d`），其 `Table S1` 为 60,129 行 × 20 列（多一个 `Description` 描述列、多一行分组表头）。

逐格比对结果：

- 基因集合完全一致（60,125 个，无重复、无一方独有）；
- 18 个数值列的 `NA` 模式完全一致；
- 所有可比数值的 **最大绝对差 = 0.0**；
- 差异只有两处：用户表删掉了 `Description` 列、删掉了分组表头行。

结论：**用户提供的 xlsx 就是该论文 Table S1 的干净版，不是重新定量/重新归一化的结果**。论文原文的方法学（STAR→IWGSC RefSeq v2.1、DESeq2 size factor、TE=Ribo/RNA 的 mean FPKM 比）就是这份表的定义。因此：

- 网站引用应写"数据来自 Chen et al. 2025 (Genome Biology) 补充表 S1"，不应写成"WheatOmics 重新分析"；
- 若确实做过再分析，需要提供与论文表不同的矩阵/方法说明，否则按论文数据处理（授权也按论文处理，见 §5）。

### 2.2 两篇论文的分工（已核实）

| 论文 | 题录 | 数据集 | 在本表中的角色 |
|---|---|---|---|
| **PlCell 2023** | Guo Y, …, Peng H. *The translational landscape of bread wheat during grain development.* Plant Cell, 2023, 35(6):1848–1867. PMID [36905284](https://pubmed.ncbi.nlm.nih.gov/36905284/)，PMCID [PMC10226598](https://pmc.ncbi.nlm.nih.gov/articles/PMC10226598/)，DOI [10.1093/plcell/koad075](https://doi.org/10.1093/plcell/koad075)，非 OA（© ASPB） | 发育籽粒 5/10/15 DAA 的 RNA-seq、Ribo-seq、polysome-seq；BioProject [PRJNA871371](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA871371)（27 runs = RNA 9 + **Ribo 6** + Poly 9 + pool 3；即 RNA n=3、**Ribo n=2**） | 提供 **CK（正常）5/10/15 DAA 的 RNA + Ribo** 原始数据 |
| **Genome Biology 2025** | Chen Y, Guo Y, …, Peng H. *Translational regulation plasticity shapes wheat grain adaptation to heat stress.* Genome Biol, 2025, 26(1):382. PMID [41214722](https://pubmed.ncbi.nlm.nih.gov/41214722/)，PMCID [PMC12599102](https://pmc.ncbi.nlm.nih.gov/articles/PMC12599102/)，DOI [10.1186/s13059-025-03848-4](https://doi.org/10.1186/s13059-025-03848-4)，OA（CC BY-NC-ND 4.0） | 42 °C 处理 1 h 后 5/10/15 DAA 籽粒的 RNA-seq（n=3）、Ribo-seq（n=2）、sRNA-seq（仅 5 DAA 的 CK/HS）；BioProject [PRJNA1135409](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1135409)（21 runs，**实测无任何 CK RNA/Ribo run**） | 提供 **HS（热胁迫）5/10/15 DAA 的 RNA + Ribo**；其对照按论文 Data availability 说明取自上一项 PlCell 2023 研究（原文第二句把对照 ID 误写成 PRJNA1135409，结合 ref[107] 与 SRA run 清单，正确 ID 为 **PRJNA871371**） |

论文方法要点（GB 2025 正文，已核对原文）：

- 材料：中国春；5/10/15 DAA 籽粒；**42 °C 高温处理 1 h**；处理与对照在同一实验批次（"temperature being the only variable"）；每个生物学重复由 5 株的籽粒混合；
- 测序：Illumina NovaSeq 6000，RNA-seq 与 Ribo-seq；Ribo-seq footprint 约 27 nt，具 3-nt 周期性；
- 定量：reads 比对 IWGSC RefSeq v2.1；DESeq2 v1.24.0 估 size factor 后计算 FPKM；表达基因定义为 mean FPKM > 1；
- **TE = 平均 Ribo-seq FPKM ÷ 平均 RNA-seq FPKM**（与表内数值完全吻合）；
- 差异翻译基因（DTG）：RiboDiff v0.2.1，FDR<0.05 且 |log2FC|>1，共 11,343 个（另用 deltaTE 复核 87.1% 一致）；
- 差异表达基因（DEG，RNA 或 Ribo 层面）：共 21,964 个（Table S2）；
- 文章还提供了**作者自己的 translatome browser**：http://wheat.cau.edu.cn/heat_stress_response_wheat_grain_translatome_browser （上架时建议作为相关资源链接，避免重复建设）。

### 2.3 表内 TE 的精确定义（反推 + 原文双重确认）

- TE 数值 = 同一条件同一阶段的 `Ribo FPKM / RNA FPKM`（最大绝对差 ~1e-6，仅为存储精度）；
- TE 为 `NA` **当且仅当该样本 RNA FPKM < 0.2**（六个样本逐一验证：`RNA<0.2` 时 TE 全为 NA，`RNA≥0.2` 时 TE 全部有值；Ribo=0 但 RNA≥0.2 时 TE=0；有值单元 RNA 最小 0.200003，NA 单元 RNA 最大 0.199896）；
- 该 0.2 阈值在正文方法中没有显式写出（正文"expressed" 是 mean FPKM>1），属于 TE 展示/计算时的低表达截断，上架说明中要写清楚，不能把 NA 当 0。

---

## 3. 基因 ID 与平台映射可行性

### 3.1 ID 构成

- 全表 60,125 个基因均为 IWGSC RefSeq v2.1 的 **03G** ID（与论文"mapped to RefSeq v2.1"一致）；
- 59,596 个位于 chr1A–7D（A/B/D 三套亚基因组），529 个为 `TraesCSU03G...`（chrUn / 未定位）；
- 10,567 个为低置信基因（`LC` 后缀）；
- 平台 CS2.1 基因组登记 `gene_count = 105,534`（`/api/genomes/Chinese_Spring2.1`），本表 60,125 ≈ 57%，是**定量/过滤后的表达子集**，不是全注释基因集。

### 3.2 03G → 02G 映射抽样验证（通过线上 GeneHub API）

- 抽样 300 个基因（160 个非 LC + 140 个 LC，随机），调用 `GET /api/genes/detail/{03G_id}`；
- 结果：**300/300 均返回 02G 对应 ID**（含 LC 与 chrUn；例：`TraesCS1A03G0000100LC → TraesCS1A02G000100LC`、`TraesCSU03G0001100 → TraesCSU02G000700`）；
- 平台现有表达模块以 02G 为键：`/api/expression/query` 已实测能把 03G 查询自动转成 02G（`TraesCS5A03G0935400 → TraesCS5A02G391700`），转换表为 `Genehub_DB.GenePageIWGSCv1_table`。

结论：把数据转成 02G 键后接入现有表达模块**技术上可行**。

**全量审计已完成（2026-11-11，Phase 2 构建时）**：用 GeneHub `Genefunc_CS_IWGSC03G_table` 的 interval API 按 30 Mb 分块拉取 21 条染色体 + chrUn，共得到 **266,760 个 03G 基因**的对照；其中本数据集 60,125 个基因 **60,125/60,125 全部映射到 02G，0 缺失、0 个多对一冲突**（构建报告 `build_report.json`）。因此 02G 不仅是抽样可行，而是**全量可用**；映射与数据构建脚本见 `scripts/heat_translatome/`。

---

## 4. 数值体检

### 4.1 每个样本的 FPKM 分布

| 样本 | 中位数 | 均值 | %>1 FPKM | %>0 | 列和（FPKM） |
|---|---:|---:|---:|---:|---:|
| RNA_5d_CK | 2.90 | 11.15 | 78.5% | 93.5% | 670,241 |
| RNA_5d_HS | 2.87 | 15.22 | 78.0% | 94.0% | 915,193 |
| RNA_10d_CK | 2.94 | 19.57 | 78.4% | 93.9% | 1,176,769 |
| RNA_10d_HS | 3.14 | 25.33 | 78.9% | 94.1% | 1,522,914 |
| RNA_15d_CK | 3.08 | 24.19 | 79.0% | 92.8% | 1,454,594 |
| RNA_15d_HS | 3.22 | 24.94 | 81.5% | 94.7% | 1,499,269 |
| Ribo_5d_CK | 2.68 | 10.64 | 72.5% | 92.1% | 639,820 |
| Ribo_5d_HS | 2.61 | 17.20 | 70.8% | 89.9% | 1,034,202 |
| Ribo_10d_CK | 2.66 | 16.27 | 72.8% | 92.0% | 978,367 |
| Ribo_10d_HS | 2.64 | 20.71 | 71.8% | 90.0% | 1,244,949 |
| Ribo_15d_CK | 2.62 | 21.85 | 71.4% | 89.0% | 1,313,433 |
| Ribo_15d_HS | 2.59 | 27.32 | 70.1% | 86.9% | 1,642,544 |

- **列和不是 1e6**（0.64–1.64 M），进一步证明是 FPKM 而不是 TPM；网站表达页现在通篇写 "TPM"，直接放进去会口径不一致（处理方案见 `PLAN.md`）。
- CK 与 HS 同阶段的中位数几乎相同（2.90 vs 2.87、2.94 vs 3.14、3.08 vs 3.22），与论文把两批数据放在同一 DESeq2 归一化框架下分析一致；但 CK 来自 PlCell 2023、HS 来自 GB 2025 两套实验，**跨批次的组间差异仍需谨慎解释**，页面需注明来源。

### 4.2 TE 分布与缺失

| TE 列 | NA 数 | NA 比例 | 中位数 | q10 | q90 | 最大值 | TE>10 的基因数 |
|---|---:|---:|---:|---:|---:|---:|---:|
| TE_5DAA_CK | 6,645 | 11.05% | 0.796 | 0.08 | 2.16 | 643 | 419 |
| TE_5DAA_HS | 6,168 | 10.26% | 0.766 | 0.01 | 2.44 | 2,700 | 581 |
| TE_10DAA_CK | 5,840 | 9.71% | 0.721 | 0.07 | 2.34 | 2,044 | 446 |
| TE_10DAA_HS | 5,327 | 8.86% | 0.676 | 0.00 | 2.67 | 2,393 | 570 |
| TE_15DAA_CK | 6,253 | 10.40% | 0.682 | 0.01 | 2.63 | 9,121 | 483 |
| TE_15DAA_HS | 4,658 | 7.75% | 0.667 | 0.00 | 2.72 | 4,062 | 650 |

- TE>100 的极端值每列仍有 28–68 个（分母 RNA 接近 0.2 → 比值爆炸），做热图/排序时必须过滤或截断；
- 六个样本的 TE 中位数在 0.667–0.796 之间漂移（不是 1），说明 TE 本身是"论文口径的原始比值"，不是按样本中位数归一化的 TE。**展示可以保留原值，但跨样本比较 TE 排序时应加限制说明**（论文的差异 TE 分析用的是 RiboDiff 的 counts 模型，不是拿表里的比值直接比）。
- **NA 不能变 0**：现有 `/api/expression/query` 会把数据库 NULL 渲染成 `0.0`（`app/api/routers/expression.py` 中 `float(row[key]) if row[key] is not None else 0.0`），TE 若混入该接口会系统性把"低表达未计算"显示成"TE=0"，必须走独立接口或先改公共接口。

### 4.3 低/异常基因

- 2,309 个基因（3.8%）六个 RNA 样本 FPKM 全为 0，但部分 Ribo 样本 >0；
- 2,704 个基因（4.5%）六个 Ribo 样本全为 0，但部分 RNA 样本 >0；
- 没有"18 列全 0"的基因；
- 以上两类与 TE 阈值同一原因（低表达/低覆盖被置 0 或未检出），上架时不建议过滤掉，但在下载说明里标注"0 = 未检出/低表达"。

### 4.4 重复与误差棒

论文原始设计：**RNA n=3、Ribo n=2（CK 与 HS 相同）**（SRA run 清单与 GB 2025 补充图 S3 相关性矩阵均可验证；CK 的 Ribo 每个阶段只有 2 个重复）。**用户表里只有条件均值（FPKM）和由均值算出的 TE**，没有 SD 列，也没有 per-replicate 矩阵。因此：

- 不能生成 `_std` 表，前端表达谱页的误差棒对这两个项目无效；
- 若要误差棒/差异显著性可视化，只能回 SRA 重新定量（即真正的"再分析"），或从论文补充材料里找 per-replicate 表（本次核验的 GB 补充表 S1–S12 中没有 per-replicate 表达矩阵）。

### 4.5 配套差异结果表（GB 补充材料，建议一起上架）

| 表 | 内容 | 规模 | 建议用途 |
|---|---|---|---|
| Table S2 | RNA/Ribo 六个比较（5/10/15 DAA CK vs HS）的 fold change + padj | 21,964 个基因 | "热胁迫差异基因"检索/下载 |
| Table S3 | 差异翻译基因 DTG：8 个共翻译聚类 + 三阶段 padj/log2FC | 11,343 个基因 | "翻译效率差异基因"检索/下载（本数据集最有特色的部分） |
| Table S4 | 新注释翻译 ORF（uORF/dORF/lORF）及表达 | 7,681 个 ORF | 二期可选：uORF/lncRNA-ORF 浏览器 |
| Table S11 | 论文提及基因的 symbol ↔ 03G ID 对照 | 约 58 个 | 基因别名搜索 |

Table S2 各比较显著数（padj<0.05）：RNA 5/10/15 DAA = 8,139 / 9,316 / 13,464；Ribo 5/10/15 DAA = 4,627 / 3,392 / 2,361。Table S3 中三阶段分别有 4,121 / 2,812 / 6,322 个 DTG 达显著（有重叠，总 11,343）。

---

## 5. 上架前必须拍板/处理的 10 件事

| # | 事项 | 现状 / 风险 | 建议 |
|---|---|---|---|
| 1 | 数据身份与引用 | 文件 = GB 2025 Table S1，不是独立再分析 | 引用写清楚：数据来自 Chen et al. 2025 补充表 S1；对照数据来自 Guo et al. 2023（PlCell）；两者都放 DOI 链接 |
| 2 | 授权 | GB 2025 为 **CC BY-NC-ND 4.0**（署名-非商业-禁止演绎）；PlCell 非 OA | 学术网站展示/检索一般属非商业共享，但"转 ID、算 ΔTE、做图"可能触及 ND 条款；建议给通讯作者（彭惠茹，penghuiru@cau.edu.cn）发邮件确认并取得书面同意，页面同时保留原论文/补充表链接 |
| 3 | 基因 ID 版本 | 数据 03G，表达库 02G；**全量 60,125/60,125 已映射（0 缺失/0 冲突）** | 已完成；模块与下载表同时保留 03G+02G 两列，LC 单独标记 |
| 4 | FPKM vs TPM | 表达页现在写 "TPM"；本数据是 FPKM | 给 `project_meta` 增加 `unit`（或 `value_type`）字段，前端按项目显示 FPKM/TPM；最小改动是标签后缀 `_FPKM` + 页面文案改 "TPM/FPKM" |
| 5 | TE 缺失值 | 8–11% NA；现有 API 把 NULL 显示成 0 | **Phase 2 已解决**：`/api/translatome/query` 返回 `null`，页面显示 `n.a.`，图断开；不填 0 |
| 6 | 重复/误差棒 | 表中只有均值，无 SD | 不建 `_std`；页面注明"条件均值，n=3/2，无误差棒"；二期可回 SRA 重算 |
| 7 | 元数据 | 数据文件无样本表 | 新建 sample metadata（阶段、处理、组织、品种、42 °C 1 h、重复数、SRA run、文库类型）随项目展示并下载 |
| 8 | 派生指标 | 只有原始 FPKM/TE | 建议预计算/接口返回：log2(TE+ε)、给定阶段 Δlog2TE(HS/CK)、Δlog2RNA、Δlog2Ribo、以及"翻译特异变化"标记；数据规模 60k×18 很小，可实时算 |
| 9 | 下载包 | 现在只有 xlsx | **Phase 2 已提供**：genes/DTG/DEG 三个 gz TSV（均含 02G+03G）+ README + sha256，页面可下载 |
| 10 | 版本与校验 | 无版本号 | 记录来源 URL、下载日期、md5、论文版本；后续论文勘误时能追溯 |

---

## 6. 结论

1. **数据可用、价值明确**：这是网站第一个 Ribo-seq / translatome 资源，且同时有发育阶段（5/10/15 DAA）与热胁迫（42 °C 1 h）两个维度，配上已发表的 DEG/DTG 结果表，足以支撑一个独立模块，而不只是"再挂一个表达谱项目"。
2. **但它是已发表数据，不是新再分析**：60,125×18 逐格等于 GB 2025 Table S1。上架前必须先和老师确认口径（"引用论文数据"还是"我们自己的再分析"），因为这直接决定引用写法、授权和是否要重新定量。
3. **真正的技术工作量在适配层**：03G→02G 映射、TE 的 NA 语义、FPKM/TPM 单位、无重复无误差棒，这四点决定了"直接塞进现有 expression 模块"只能算半个方案；推荐方案见 `PLAN.md`。
4. **授权是唯一可能导致不能上架的因素**：CC BY-NC-ND 4.0 + PlCell 非 OA，建议先发邮件取得作者同意（模板见 `PLAN.md` 附录），再动数据库。

> 本报告的数值均由本地脚本对 xlsx 全量计算得出；论文题录、样本设计、TE 定义、accession 均来自 Europe PMC 全文 / ENA-SRA 元数据 / Springer 补充材料实测，未使用记忆推断。
