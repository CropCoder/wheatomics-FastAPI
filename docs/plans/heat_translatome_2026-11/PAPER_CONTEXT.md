# 热胁迫小麦籽粒 RNA-seq / Ribo-seq / TE 数据集：论文溯源与实验设计核实报告

- 日期：2026-11-11
- 核实人：paper-scout（Team task-2）
- 核实方式：**只采用真实抓取内容**——Crossref REST、Europe PMC REST（题录 + 全文）、PMC 全文页、NCBI E-utilities（PubMed / BioProject / SRA run 元数据）、Springer 补充材料原文件（xlsx，已本地下载并解析）。PubMed 网页本身有 JS 人机验证，题录一律经 NCBI E-utilities `db=pubmed` 与 Europe PMC 记录交叉确认，不凭记忆补 PMID/样本数/温度/accession。
- 同目录 `DATA_AUDIT.md` 已逐格证明站内文件 = Genome Biology 2025 补充表 S1；本报告负责**论文身份、设计、定量口径、授权、citation 写法**，并纠正该文件中的两处元数据出入（见 §9）。

---

## 0. 结论速览（TL;DR）

1. **数据表来源 = Genome Biology 2025 论文的补充表 S1**（"Expression levels of genes"，60,125 行 × 18 个数值列，列名与站内表逐字相同）。该论文即用户所说的 "Translational regulation plasticity shapes wheat grain adaptation to heat stress"，**是这份 Ribo-seq/TE 数据的直接来源**。
2. **PlCell 2023（koad075）不是热胁迫论文**，它是同一课题组（中国农业大学 彭惠茹/孙其信 组）的**发育籽粒 translatome 资源**：中国春 5/10/15 DAA 的 RNA-seq + polysome-seq + Ribo-seq，**没有热胁迫处理**。它在本文数据中的角色是：①GB 2025 用来做 TE 计算的**方法学前身**（GB 原文引用其 ref 22）；②**CK（正常条件）RNA-seq / Ribo-seq 原始文库的来源**（GB 2025 Data availability 明说"从上一项研究获得"，SRA run 清单可验证）。
3. 设计关键数字：中国春（Chinese Spring）；籽粒 5 / 10 / 15 DAA；热胁迫 **42 °C、1 h**（处理后立即取样，无恢复期）；生物学重复 **RNA n=3、Ribo n=2**（CK 与 HS 相同）；Illumina NovaSeq 6000（RNA-seq 150 bp PE，Ribo-seq NEBNext 小 RNA 建库）。
4. 定量：**FPKM（不是 TPM）**；FeatureCounts 计数 → DESeq2 v1.24.0 size factor 归一化 → FPKM；**TE = 重复均值 Ribo-seq FPKM ÷ 重复均值 RNA-seq FPKM**；无样本间中位数/trimmed-mean 缩放；TE 与 RNA 比值的低表达截断实测为 **RNA FPKM < 0.2 → NA**（论文正文未写此阈值）。
5. 数据可用性：**PRJNA1135409**（热胁迫 21 runs：RNA 9 + Ribo 6 + sRNA 6）+ **PRJNA871371**（对照/发育 27 runs：RNA 9 + Ribo 6 + Poly 9 + pool 3）。
6. 授权：GB 2025 = **CC BY-NC-ND 4.0**（署名-非商业-禁止演绎）；PlCell 2023 = **© ASPB 2023, All rights reserved**（OUP Standard 复用条款，非 OA），商用/改编需授权。
7. 网站 citation 建议见 §8（已按 WheatOmics `project_meta.citation` 的 HTML 解析规则写成可直接入库的英文串）。

---

## 1. 论文一：Genome Biology 2025（数据来源）

### 1.1 完整题录（Crossref / Europe PMC / NCBI E-utilities 三源一致）

| 字段 | 值 |
|---|---|
| 标题 | Translational regulation plasticity shapes wheat grain adaptation to heat stress |
| 作者 | Chen Y, Guo Y, Ma M, Wang Y, Guo W, Hu Z, Xin M, Yao Y, Ni Z, Sun Q, Peng H（11 人；Chen Yongming、Guo Yiwen 共同一作，Peng Huiru 通讯） |
| 期刊 | Genome Biology（Genome Biol） |
| 年/卷/期/文章号 | 2025；26(1):382（article number 382） |
| 出版日期 | 在线 2025-11-10；收稿 2025-03-24，接收 2025-10-28 |
| DOI | 10.1186/s13059-025-03848-4 |
| PMID | 41214722 |
| PMCID | PMC12599102 |
| 开放获取 | 是；**CC BY-NC-ND 4.0**（Crossref license URL：https://creativecommons.org/licenses/by-nc-nd/4.0） |
| 单位 | 中国农业大学 前沿科学中心/杂种优势与利用重点实验室（第一单位）；Chen Yongming 另有北京大学现代农业研究院（潍坊）单位 |
| 链接 | https://doi.org/10.1186/s13059-025-03848-4 ；https://genomebiology.biomedcentral.com/articles/10.1186/s13059-025-03848-4 ；https://pmc.ncbi.nlm.nih.gov/articles/PMC12599102/ ；https://europepmc.org/article/MED/41214722 ；https://pubmed.ncbi.nlm.nih.gov/41214722/ |

题录核对来源：
- Crossref：https://api.crossref.org/works/10.1186/s13059-025-03848-4
- Europe PMC REST：https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:%2210.1186/s13059-025-03848-4%22&format=json&resultType=core
- NCBI E-utilities（db=pubmed）：https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id=41214722&retmode=json
- PMC 全文（本报告引文出处）：https://pmc.ncbi.nlm.nih.gov/articles/PMC12599102/

### 1.2 这篇论文提供了哪一层数据（原文摘录 + URL）

摘要 Results（https://pmc.ncbi.nlm.nih.gov/articles/PMC12599102/）：
> "We use ribosome profiling and high-throughput sequencing to investigate the translatome of wheat grains in response to high temperatures."

Results 第一节：
> "To investigate the translational dynamics and regulations of genes in the wheat grains in response to heat stress, we performed a 1-h 42 °C heat treatment on the developmental wheat grains at 5 days after anthesis (5 DAA), 10 DAA, and 15 DAA and collected the heat-treated grains for subsequent ribosome profiling and high-throughput sequencing … The samples under normal conditions and those under heat stress conditions were collected in the same experimental batch, with temperature being the only variable."

即：**热胁迫（HS）部分的 RNA-seq + Ribo-seq 是本论文新产生的**；另有 5 DAA 的小 RNA 测序（sRNA-seq，CK/HS 各 3 重复，与本文 18 列数据表无关）。

论文主要数字（同页 Results）：90,213 个鉴定到的 ORF；21,964 个差异表达基因（转录或翻译层面）；11,343 个差异翻译基因（DTG，RiboDiff，FDR<0.05、|log2FC|>1；deltaTE 复核 87.1% 一致）。

### 1.3 这份 18 列表就是本文的补充表 S1（已下载核对）

- 文件：**Additional file 2**（xlsx，22.1 MB），内含 Table S1–S12；Table S1 标题为 "Expression levels of genes."。
- 下载（Springer 静态资源，实际抓取成功）：https://static-content.springer.com/esm/art%3A10.1186%2Fs13059-025-03848-4/MediaObjects/13059_2025_3848_MOESM2_ESM.xlsx
- 同一文件 PMC 镜像路径（PMC 有防抓取跳转，直接 curl 会返回 HTML 下载引导页）：https://pmc.ncbi.nlm.nih.gov/articles/instance/12599102/bin/13059_2025_3848_MOESM2_ESM.xlsx
- 本地下载文件大小 23,142,257 bytes，**md5 = 85db3d05cae2e413b48c0739d0edc36d**（与 `DATA_AUDIT.md` 记录一致，双方独立下载得到同一文件）。
- Table S1 结构：`Gene`、`Description` 两列 + **18 个数值列**，列名/顺序与站内表逐字相同：
  `RNA_5d_CK, RNA_5d_HS, RNA_10d_CK, RNA_10d_HS, RNA_15d_CK, RNA_15d_HS, Ribo_5d_CK, Ribo_5d_HS, Ribo_10d_CK, Ribo_10d_HS, Ribo_15d_CK, Ribo_15d_HS, TE_5DAA_CK, TE_5DAA_HS, TE_10DAA_CK, TE_10DAA_HS, TE_15DAA_CK, TE_15DAA_HS`
  （第 3 行分组表头：`Expression` = 前 12 列；`TE Ribo/RNA` = 后 6 列）
- 数据行数：**60,125 个唯一基因 ID**（openpyxl 逐行计数 60,129 − 4 行表头/空行）。其中 **10,567 个 `…LC`（低置信基因）**、**529 个 `TraesCSU…`（chrUn 未定位）**，其余位于 chr1A–7D；无重复 ID。
- 补充材料共 3 个文件：Additional file 1 = 补充图 S1–S12（PDF, 2 MB）；Additional file 2 = 表 S1–S12（xlsx, 22.1 MB）；Additional file 3 = PPTX（1.5 MB）。

---

## 2. 论文二：Plant Cell 2023（koad075，CK 数据 + 方法学基础）

### 2.1 完整题录

| 字段 | 值 |
|---|---|
| 标题 | The translational landscape of bread wheat during grain development |
| 作者 | Guo Y, Chen Y, Wang Y, Wu X, Zhang X, Mao W, Yu H, Guo K, Xu J, Ma L, Guo W, Hu Z, Xin M, Yao Y, Ni Z, Sun Q, Peng H（17 人；Guo Yiwen、Chen Yongming 共同一作，Peng Huiru 通讯） |
| 期刊 | The Plant Cell（Plant Cell） |
| 年/卷/期/页 | 2023；35(6):1848–1867 |
| 出版日期 | 在线 2023-03-11；印刷 2023-05-29；收稿 2022-09-02，接收 2023-02-19 |
| DOI | 10.1093/plcell/koad075 |
| PMID | 36905284 |
| PMCID | PMC10226598 |
| 开放获取 | **否**（Europe PMC `isOpenAccess: N`）；PMC 有免费全文，2024-03-11 起解除 embargo；版权声明见 §7 |
| 链接 | https://doi.org/10.1093/plcell/koad075 ；https://academic.oup.com/plcell/article/35/6/1848/7076157 ；https://pmc.ncbi.nlm.nih.gov/articles/PMC10226598/ ；https://pubmed.ncbi.nlm.nih.gov/36905284/ |

题录核对来源：
- Crossref：https://api.crossref.org/works/10.1093/plcell/koad075
- Europe PMC REST：https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:%2210.1093/plcell/koad075%22&format=json&resultType=core
- NCBI E-utilities（db=pubmed）：https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id=36905284&retmode=json
- PMC 全文：https://pmc.ncbi.nlm.nih.gov/articles/PMC10226598/

### 2.2 这篇论文是什么、提供了什么（原文摘录 + URL）

摘要（https://pmc.ncbi.nlm.nih.gov/articles/PMC10226598/）：
> "Here, we performed ribosome profiling and polysome profiling to obtain a comprehensive translatome data set of developing bread wheat (Triticum aestivum) grains."

Results 第一节：
> "we performed next-generation sequencing on the total mRNAs (RNA-seq), polysomal mRNAs (Poly-seq), and ribosome-protected mRNA fragments (Ribo-seq) of wheat grains at successive developmental stages, including 5 d after anthesis (DAA), 10 DAA, and 15 DAA"

关键判断：**全文没有任何热胁迫/高温处理实验**（"heat" 仅出现在 "wheat" 等词中）。它提供的是**正常生长条件**下的发育籽粒时间序列 translatome，包含 RNA-seq、Polysome-seq、Ribo-seq 三种文库。

### 2.3 与 GB 2025 的关系（已核实）

1. **数据层**：GB 2025 Data availability 明说其 RNA-seq/Ribo-seq 取自上一项研究（[22] 即本文），SRA 清单可验证（详见 §3）。
2. **方法层**：GB 2025 计算 TE 时明确写 "according to the previously reported method [22]"，ref 22 = Guo et al. 2023；籽粒发育相关基因集（936 个）与同源 triad 判定（GeneTribe）也沿用该文方法。
3. **人员层**：两文为同一课题组连续工作（Chen Yongming、Guo Yiwen 均为一作/共同一作，Peng Huiru 通讯；CAU 同一实验室）。
4. **术语差异（上架说明必须写清）**：PlCell 2023 的主体指标是 **translation state（TS）= Poly-seq FPKM / RNA-seq FPKM**；它只在 sORF/uORF 分析里用 **TE = Ribo-seq FPKM / RNA-seq FPKM**。GB 2025 才对全部基因统一用 **TE = Ribo/RNA**。因此：**站内 6 个 TE 列的数值来自 GB 2025 口径，不是 PlCell 的 TS**。
   - PlCell 原文：> "The translation state (TS; calculated as the ratio of polysomal mRNA abundance to that of total RNA) was used to measure the utilization efficiency of mRNA for protein synthesis."
   - PlCell 原文：> "In addition, we used the Ribo-seq data to investigate TEs of unannotated sORFs … The formula is FPKMRibo-seq/FPKMRNA-seq."

---

## 3. 两篇论文与这份数据表的血缘关系（证据链）

```
PRJNA871371  (PlCell 2023, 发育/正常条件)          PRJNA1135409  (Genome Biol 2025, 热胁迫)
  RNA-seq  9 runs = 3 阶段 × 3 重复                  RNA-seq  9 runs = 3 阶段 × 3 重复
  Ribo-seq 6 runs = 3 阶段 × 2 重复                  Ribo-seq 6 runs = 3 阶段 × 2 重复
  Poly-seq 9 runs (n=3) + pool 3 runs               sRNA-seq 6 runs (5 DAA CK/HS，本表不用)
            \                                        /
             → GB 2025 用同一流程（STAR→FeatureCounts→DESeq2 size factor→FPKM）统一定量
             → Genome Biol 2025 Additional file 2: Table S1
                 60,125 基因 × (Gene + Description + 18 数值列)
             → WheatOmics 表：删掉 Description 列，保留 18 列（RNA 6 + Ribo 6 + TE 6）
```

证据 1：**SRA run 清单**（NCBI E-utilities `db=sra` esummary，按 run 的 `LIBRARY_NAME` 字段；两项目全部 run 已逐个枚举，见附录 B）
- PRJNA1135409（21 runs）中**只有 HS 样本**：`RNA_5d/10d/15d_HS-1..3`（9）、`Ribo_5d/10d/15d_HS-1..2`（6）、`sRNA_5d_CK/HS-1..3`（6）。**没有 CK 的 RNA/Ribo run。**
- PRJNA871371（27 runs）：`RNA_5d/10d/15d-1..3`（9）、`Ribo_5d/10d/15d-1..2`（6）、`Poly_5d/10d/15d-1..3`（9）、`pool-1..3`（3）。
- 因此站内 CK 的 RNA/Ribo 只能来自 PRJNA871371，HS 的来自 PRJNA1135409。

证据 2：**GB 2025 补充图 S3 的相关性矩阵样本标签**（Additional file 1 PDF，https://pmc.ncbi.nlm.nih.gov/articles/instance/12599102/bin/13059_2025_3848_MOESM1_ESM.pdf）
- RNA-seq 面板共 18 个文库：`RNA_5d_CK−1/2/3, RNA_5d_heat−1/2/3, RNA_10d_CK−1/2/3, RNA_10d_heat−1/2/3, RNA_15d_CK−1/2/3, RNA_15d_heat−1/2/3`；
- Ribo-seq 面板共 12 个文库：`Ribo_5d_CK−1/2, Ribo_5d_heat−1/2, Ribo_10d_CK−1/2, Ribo_10d_heat−1/2, Ribo_15d_CK−1/2, Ribo_15d_heat−1/2`。
- 即 GB 2025 分析里 CK 的 RNA=3 重复、Ribo=2 重复，与 PRJNA871371 的 run 数完全对应（GB 把 PlCell 的 `RNA_5d-1` 等重命名为 `RNA_5d_CK-1`）。

证据 3：**论文 Data availability 原文**（https://pmc.ncbi.nlm.nih.gov/articles/PMC12599102/ ，Data availability 节）：
> "The transcriptome, translatome, and sRNA-seq data generated in this study are available at the NCBI Sequencing Read Archive, BioProject ID PRJNA1135409 [106]. In addition, the RNA-seq and Ribo-seq data from developing grains were obtained from the previous study [22], with the corresponding NCBI BioProject ID PRJNA1135409 [107]."

注意：这句话里的第二个 ID **写成 PRJNA1135409，与它引用的 ref [107] 矛盾**——ref [107] 明确指向 PRJNA871371（见参考文献列表："Guo Y, … The translational landscape of bread wheat during grain development. Datasets. Sequencing Read Archive. 2023. https://www.ncbi.nlm.nih.gov/bioproject/PRJNA871371"）。结合证据 1/2，应判定为**论文笔误，正确 ID 是 PRJNA871371**。另外，该表述与正文 "The control and heat-treated samples were collected in the same experimental batch" 存在口径冲突（同一批实验 vs 取自上一项研究）；**以 SRA 元数据 + 补充图样本标签为准**，上架说明建议写"CK 文库来自 Guo et al. 2023（PRJNA871371），HS 文库为 Chen et al. 2025 新测（PRJNA1135409）"。

---

## 4. 实验设计（两篇对照）

| 项目 | Genome Biology 2025（HS 数据 + 表 S1 作者） | Plant Cell 2023（CK 数据） |
|---|---|---|
| 品种/材料 | 中国春 *Triticum aestivum* cv. Chinese Spring | 中国春（同上）；种子 4 °C 黑暗浸种 3 d 后入生长箱 |
| 生长条件 | 温室 22 °C/18 °C（昼/夜），16 h 光/8 h 暗，光强 3,000 lx（Philips Master GreenPower CG T 400 W E40），60% RH | 生长箱 22 °C/18 °C（昼/夜），16 h 光/8 h 暗，3,000 lux（同型号灯），60% RH |
| 取样组织/时间点 | 发育籽粒 **5、10、15 DAA**（days after anthesis，花后天数） | 发育籽粒 **5、10、15 DAA** |
| 热胁迫 | **42 °C 处理 1 h** 后立即取样；无恢复期；对照不做处理 | **无热胁迫**（仅正常生长） |
| 生物学重复 | "developing seeds from 5 different plants were mixed to represent one biological replicate, and at least 2 or 3 biological replicates were used" → 实际 **RNA n=3、Ribo n=2**（SRA run 与 Fig. S3 一致） | 同一句表述；实际 **RNA n=3、Ribo n=2、Poly n=3**（SRA run：RNA_*d-1..3、Ribo_*d-1..2、Poly_*d-1..3） |
| 文库/平台 | RNA-seq：Hieff NGS MaxUp II + poly(A) 富集，150 bp PE，**Illumina NovaSeq 6000**，约 76.8 M reads/库；Ribo-seq：RNase I 消化 → MicroSpin S-400 富集单体 → Ribo-Zero 去 rRNA → **NEBNext Multiplex Small RNA Library Prep**，NovaSeq 6000，约 58.1 M reads/库 | RNA-seq：链特异 dUTP 法，150 bp PE，Illumina NovaSeq，约 76.9 M reads/库；Poly-seq 约 75.7 M；Ribo-seq 约 60.0 M RF reads/库 |
| footprint 特征 | ~27 nt；CDS 富集；3-nt 周期性 | ~27 nt；3-nt 周期性；P site 12–14 nt |
| 比对/定量 | IWGSC **RefSeq v2.1**（下载自 wheat-urgi）；STAR v2.7.8a；FeatureCounts v1.5.2；DESeq2 v1.24.0 | IWGSC **RefSeq v2.1**；STAR；FeatureCounts；DESeq2 size factor |
| 数据 accession | **PRJNA1135409** | **PRJNA871371** |
| 作者浏览器 | http://wheat.cau.edu.cn/heat_stress_response_wheat_grain_translatome_browser | http://wheat.cau.edu.cn/wheat_grain_translatome_browser/ |

原文出处（Methods，URL 同上）：
- 生长条件与热胁迫（GB 2025）：
  > "The wheat materials (Triticum aestivum cv. Chinese Spring) were grown in a greenhouse at 22 °C/18 °C (day/night) with a 16 h-light/8-h-dark cycle, with a light intensity of 3,000 lx …, and 60% relative humidity."
  > "The plants were exposed to a 42 °C high temperature for 1 h, and then were harvested from different plants grown in the growth chamber. 42 °C is a classic temperature in the study of wheat heat stress …"
  > "Samples without heat treatment were employed as control plants. For each sample, developing seeds from 5 different plants were mixed to represent one biological replicate, and at least 2 or 3 biological replicates were used."
- 测序（GB 2025）：
  > "The RNA-seq libraries were sequenced to generate 150 bp paired-end reads on the Illumina NovaSeq 6000 platform. The Illumina sequencing platform yielded about 76.8 million reads from each total library."
  > "Ribosome-protected mRNA was used to prepare a library with the NEBNext Multiplex Small RNA Library Prep Set for Illumina … deep sequencing with an Illumina NovaSeq 6000 platform … about 58.1 million reads from each RF library."
- 取样（PlCell 2023）：
  > "The grain samples were sampled at 5, 10, and 15 d after anthesis (DAA) and were harvested from different plants grown in the growth chamber. For each sample, developing seeds from 5 different plants were mixed to represent one biological replicates, and at least 2 or 3 biological replicates were used."

---

## 5. 定量、归一化与 TE 的精确定义

### 5.1 表达量是 FPKM，不是 TPM

GB 2025 Methods（"Expression quantification"）：
> "Mapping reads were used to calculate the expression level (FPKM) of genes with DESeq2 v1.24.0 [86]. The read counts of libraries of grain tissues were normalized by sequencing depth with a sample-specific size factor estimation implemented in DESeq2 v1.24.0 [86]. To remove low-quality and low-expression gene models, only gene models with a mean FPKM of more than 1 were considered as expressed genes. … TE was calculated by dividing the average of Ribo-seq FPKM values by the average of RNA-seq FPKM values from replicates."

PlCell 2023 同样用 FPKM：
> "We took the average fragments per kilobase of exon per million mapped fragment (FPKM) values as the abundance of the associated genes. The read count was normalized by sequencing depth with a sample-specific size factor implemented in DESeq2."

**上架注意**：站内现有表达谱项目多为 TPM（如 `*_tpm_mean_tbl`），本数据集是 **FPKM**。若不显式标注，用户会把 FPKM 当 TPM 比较/跨库比较，产生口径错误（详见 `DATA_AUDIT.md` §4.1、§5 第 4 条）。

### 5.2 Ribo-seq 流程（GB 2025，Methods）

RNase I 消化（15 μL RNase I, Invitrogen AM2294）→ MicroSpin S-400 柱富集单体核糖体 → 胶回收 → Ribo-Zero Magnetic Kit 去细胞质/叶绿体 rRNA → NEBNext 小 RNA 建库 → NovaSeq 6000。
数据处理：
> "only trimmed reads between 18 and 40 nucleotides were retained for further mapping … the wheat rRNA, tRNA, and snoRNA sequences were acquired from RNAcentral [84] and were used to remove expected contaminant RNA sequences in each Ribo-seq library using bowtie2 v2.3.4 [85] … mapped to the IWGSC RefSeq v2.1 genome using STAR v2.7.8a with specific settings: –outFilterMultimapNmax 50 –outSAMmultNmax 1 –alignEndsType EndToEnd –outFilterMismatchNmax 2 –outMultimapperOrder Random … FeatureCounts v1.5.2 [83] with the default parameter."

### 5.3 TE 定义（含"是否做样本间归一化"）

- **TE = 重复均值 Ribo-seq FPKM ÷ 重复均值 RNA-seq FPKM**（GB 2025 Methods 原文，见 §5.1 引文；Results 亦称 "TE, expression level from Ribo-seq divided by expression levels from RNA-seq … according to the previously reported method [22]"）。
- **没有做 TE 的样本间中位数/trimmed-mean 缩放**：论文未提任何 TE 跨样本归一化步骤；对表 S1 实测六个 TE 列的中位数为 0.667–0.796（非 1），说明保留的是"原始比值"（与 `DATA_AUDIT.md` §4.2 结论一致）。
- FPKM 本身只做了**库内测序深度归一化**（DESeq2 size factor）以及基因长度归一化；没有跨批次（CK vs HS 两批文库）额外的表达量对齐步骤被描述。
- **TE 的缺失值规则（本次实测反推，论文正文未写）**：对 6 列 × 60,125 个单元逐一验证——
  - 有值单元：TE 与 `Ribo FPKM / RNA FPKM` **完全相等**（全部 360,750 个单元，零误差）；
  - `RNA FPKM > 0` 但 `< 0.2` 的单元：TE 一律为 `NA`（六个样本逐一验证：有值单元 RNA 最小值 = 0.200003；NA 且 RNA>0 的单元 RNA 最大值 = 0.199896）；
  - `Ribo = 0` 且 `RNA ≥ 0.2`：TE = 0（不是 NA）。
  - 结论：**TE = Ribo/RNA if RNA FPKM ≥ 0.2, else NA**。用户此前"RNA=0 时 TE=NA"的描述不完整，**上架说明必须写 0.2 截断**，且 NA ≠ 0。
- 低表达过滤的层次（避免混淆）：
  - "expressed genes" 定义（用于差异分析）：mean FPKM > 1；
  - DTG 分析（RiboDiff）：> "Due to the formula for calculating TE, very low expression at the transcriptional level causes errors in the TE calculation, so we did not consider such genes when analyzing DTGs." 即极低 RNA 的基因不进入 DTG 统计；
  - **Table S1 本身不是 mean FPKM>1 的子集**：表中存在 12 列均值 < 1 的基因（例：`TraesCS1A03G0000700LC` 六个 RNA 均 < 0.13），说明表是"定量后基因集"而非"表达基因集"。
- **低置信/未定位基因是否纳入**：纳入。Table S1 含 **10,567 个 `LC` 低置信基因**与 **529 个 `TraesCSU`（chrUn）基因**；站内表应保留并标注，不要静默丢弃。

### 5.4 差异分析参数（供网站筛选/解释说明）

GB 2025：RiboDiff v0.2.1 做差异 TE（FDR<0.05、|log2FC|>1 → 11,343 DTG；deltaTE 复核 87.1%，Jaccard 0.85）；DESeq2 v1.24.0 做差异表达（FDR<0.05、|log2FC|>1）；共 21,964 DEG。
PlCell 2023 用 translation state（Poly/RNA）做发育阶段差异翻译分析（19,363 个基因 TS 改变），与本表 TE 不是同一指标。

---

## 6. 数据可用性（accession、补充表、可下载性）

### 6.1 原始数据

| BioProject | 标题（NCBI） | 提交单位 | run 数 | 内容 |
|---|---|---|---|---|
| **PRJNA1135409** | "Translatome sequencing of the heat-treated wheat grains" | China Agricultural University | 21 | RNA-seq HS 9 + Ribo-seq HS 6 + sRNA-seq 5 DAA CK/HS 6 |
| **PRJNA871371** | "Translatome sequencing of developing wheat grains" | China Agricultural University | 27 | RNA-seq 9 + Ribo-seq 6 + Poly-seq 9 + pool RNA 3 |

- BioProject 页面：https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1135409 ；https://www.ncbi.nlm.nih.gov/bioproject/PRJNA871371
- 两个项目均为 SRA 公开原始 reads；NCBI 数据复用按 NCBI 数据使用政策执行。
- 完整 run 清单见附录 B（`LIBRARY_NAME` 与站内 18 列的对应关系）。

### 6.2 补充表（已核对内容）

- **GB 2025 Additional file 2: Table S1**（= 站内数据表来源）：60,125 基因 × 18 数值列 **FPKM 均值 + TE 比值**；**没有 TPM、没有原始 counts、没有 per-replicate 矩阵、没有 SD**。
- GB 2025 其余补充表（同上 xlsx）：Table S2 = 21,964 DEG（六个比较）；Table S3 = 11,343 DTG + 8 个共翻译聚类；Table S4 = 新注释 ORF；Table S5 = RBP–PCG 共翻译网络；Table S6 = 热响应 uORF/dORF；Table S7 = 同源 triad TE；Table S8 = 热响应 lORF；Table S9 = lORF10 互作蛋白；Table S10 = 引物；Table S11 = 基因 symbol ↔ ID；Table S12 = qRT-PCR 三重复原始值（**只有 qRT-PCR 有重复数据，表达矩阵没有**）。
- GB 补充图（Additional file 1 PDF）里有各文库相关性矩阵（Fig. S3），可用于核对重复结构，但不是可挖掘的表达矩阵。
- **PlCell 2023 补充材料**：官网列为 "Supplemental Data Set 1–12"（Data Set 2 = 各文库基因表达定量，Data Set 12 = 正文讨论基因的 accession numbers）。下载地址（PMC 镜像）：https://pmc.ncbi.nlm.nih.gov/articles/instance/10226598/bin/koad075_supplementary_data.zip —— **本次未取得**（PMC 对该 bin 路径有 JS 下载引导/防抓取，Europe PMC supplementaryFiles 端点对该文返回空错误），因此 **PlCell 补充表的具体内容未核实到**；不过其存在与标题已在 PMC 页面确认。

### 6.3 数据可用性声明原文（可直接引用）

GB 2025（https://pmc.ncbi.nlm.nih.gov/articles/PMC12599102/）：
> "The transcriptome, translatome, and sRNA-seq data generated in this study are available at the NCBI Sequencing Read Archive, BioProject ID PRJNA1135409. In addition, the RNA-seq and Ribo-seq data from developing grains were obtained from the previous study, with the corresponding NCBI BioProject ID PRJNA1135409 [107]. The genomic variation data are publicly available via Wheat SnpHub Portal (http://wheat.cau.edu.cn/Wheat_SnpHub_Portal/). The genome browser for the translatome is available through the link http://wheat.cau.edu.cn/heat_stress_response_wheat_grain_translatome_browser. No custom scripts and software were used other than those mentioned in Methods."

PlCell 2023（https://pmc.ncbi.nlm.nih.gov/articles/PMC10226598/）：
> "Sequencing data sets are available at the NCBI Sequencing Read Archive (SRA), BioProject ID PRJNA871371. Tracks for all the translatomic data are available through the genome browser (http://wheat.cau.edu.cn/wheat_grain_translatome_browser/)."

（注：GB 声明第二句的 ID 为笔误，见 §3 证据 3；引用给用户看时建议直接写正确的 PRJNA871371。）

---

## 7. License / 复用 / 署名要求

| 论文 | 授权 | 原文/出处 | 对 WheatOmics 的含义 |
|---|---|---|---|
| Genome Biol 2025 | **CC BY-NC-ND 4.0** | "Open Access This article is licensed under a Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License …"（https://pmc.ncbi.nlm.nih.gov/articles/PMC12599102/ ；license URL https://creativecommons.org/licenses/by-nc-nd/4.0） | 允许非商业共享（含转载 Table S1），须署名 + 链接许可 + 注明是否修改；**不允许发布改编版本**。站内"原样展示 + 明确引用"风险最低；若做 ID 转换、TE 重算、ΔTE 派生指标并对外提供，可能触及 ND，建议先取得作者书面同意或明确标注"derived, for research use only"。 |
| Plant Cell 2023 | **© American Society of Plant Biologists 2023. All rights reserved.**；OUP Standard Journals Publication Model | "© American Society of Plant Biologists 2023. All rights reserved. For permissions, please e-mail: journals.permissions@oup.com"；"This article is published and distributed under the terms of the Oxford University Press, Standard Journals Publication Model (https://academic.oup.com/pages/standard-publication-reuse-rights)"（https://pmc.ncbi.nlm.nih.gov/articles/PMC10226598/） | 非 OA、非 CC；表格/图的再发布需 OUP 授权。**但本数据集的 CK 数值实际经由 GB 2025 的 Table S1 再发布（受 CC BY-NC-ND 约束）**，原始 reads 在 SRA。引用 PlCell 题录时必须署名，不复制其图表。 |
| 原始测序数据 | NCBI SRA 公开数据 | PRJNA871371 / PRJNA1135409 | 按 NCBI 数据使用政策；建议在下载页同时给出两个 BioProject 链接。 |

**署名/联系建议**：两文通讯作者均为 彭惠茹（Huiru Peng，penghuiru@cau.edu.cn，CAU；邮箱见 Europe PMC 记录）。若网站要明确"数据再发布/再分析"身份或做派生指标，建议先发邮件取得作者确认（与 `DATA_AUDIT.md` §5 第 2 条一致）。

---

## 8. 网站 citation 字段建议（WheatOmics 现有格式）

### 8.1 WheatOmics 的 citation 规则（从代码核对）

- 存储：`gene_expression.project_meta.citation TEXT`（HTML 格式），见 `init_project_meta.sql` 表结构与 69 条示例；前端在`app/static/expression/index.html` 的 `parseCitation()` 中解析。
- 实际生效的写法模式：`'<一句英文描述>. <a href=\'<链接>\'>出版信息/accession</a>'`，例：
  `'Tolerant and susceptible wheat cultivar under heat stress. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA171754\'>PRJNA171754</a>'`
- 解析器能力（决定了 citation 该怎么写）：
  - 第一个 `<a href>` 会被当作"归档链接"（若文本匹配 PRJ/ERP/CRA 等 accession，会自动生成 NCBI/CNCB 链接）；
  - 剩余文本中**第一个** PubMed URL → PubMed 链接；**第一个** doi.org URL → DOI 链接；
  - 第二个及之后的 URL 会被清除、不显示；第二个 anchor 标签不会被移除，会以原始 HTML 文本漏出（**不要写第二个 `<a>`**）；
  - 支持 `Publication:` 标签分段（现有条目基本不用，可不写）。
- 因此 citation 里**最多渲染 3 个链接**（accession · PubMed · DOI）。要把两篇论文都列出来，另一篇只能用纯文本（推荐写 PMID 数字）。

### 8.2 推荐 citation 字符串（英文，可直接入库；3 链接安全版）

```
Chinese Spring wheat developing grains at 5, 10, 15 DAA under control and 1-h 42 °C heat stress; RNA-seq and Ribo-seq FPKM with translation efficiency (TE = Ribo-seq/RNA-seq FPKM). Heat-stress data from Chen et al. 2025 Genome Biol (PMID 41214722); control RNA-seq/Ribo-seq data from Guo et al. 2023 Plant Cell (PMID 36905284). <a href='https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1135409'>PRJNA1135409</a> https://www.ncbi.nlm.nih.gov/pubmed/41214722 https://doi.org/10.1186/s13059-025-03848-4
```

- 渲染结果：描述文本 + 三个链接 `PRJNA1135409` · `PubMed` · `DOI`；
- 入库前注意单引号转义（SQL 中写成 `\'`，与 `init_project_meta.sql` 现有风格一致）。

若希望与库内大多数条目风格完全一致（单链接），可用：

```
Chinese Spring wheat developing grains (5, 10, 15 DAA) under control and 1-h 42 °C heat stress; RNA-seq and Ribo-seq FPKM with translation efficiency (TE). Heat-stress data from Chen et al. 2025 Genome Biol; control RNA-seq/Ribo-seq data from Guo et al. 2023 Plant Cell. <a href='https://www.ncbi.nlm.nih.gov/pubmed/41214722'>Genome Biol 2025, doi: 10.1186/s13059-025-03848-4</a>
```

### 8.3 完整英文题录（用于数据集详情页/README/References 区块）

1. Chen Y, Guo Y, Ma M, Wang Y, Guo W, Hu Z, Xin M, Yao Y, Ni Z, Sun Q, Peng H. Translational regulation plasticity shapes wheat grain adaptation to heat stress. *Genome Biol.* 2025;26(1):382. doi:10.1186/s13059-025-03848-4. PMID: 41214722. PMCID: PMC12599102.
2. Guo Y, Chen Y, Wang Y, Wu X, Zhang X, Mao W, Yu H, Guo K, Xu J, Ma L, Guo W, Hu Z, Xin M, Yao Y, Ni Z, Sun Q, Peng H. The translational landscape of bread wheat during grain development. *Plant Cell.* 2023;35(6):1848–1867. doi:10.1093/plcell/koad075. PMID: 36905284. PMCID: PMC10226598.

### 8.4 其他元数据建议（供 Lead 参考）

- `display_name` 建议：`Chinese Spring developing grain heat-stress translatome (5/10/15 DAA, RNA & Ribo, FPKM)`（一定要带 **FPKM**，避免与站内 TPM 项目混淆）。
- `group_name`：`wheat abiotic stresses`；`has_std_table = 0`（无 SD 表）。
- `labels`（18 项，与列顺序一致）：
  `["RNA_5d_CK","RNA_5d_HS","RNA_10d_CK","RNA_10d_HS","RNA_15d_CK","RNA_15d_HS","Ribo_5d_CK","Ribo_5d_HS","Ribo_10d_CK","Ribo_10d_HS","Ribo_15d_CK","Ribo_15d_HS","TE_5DAA_CK","TE_5DAA_HS","TE_10DAA_CK","TE_10DAA_HS","TE_15DAA_CK","TE_15DAA_HS"]`
- 数据集说明（英文一句话，可放页面）：
  "RNA-seq and Ribo-seq FPKM values, and translation efficiency (TE = Ribo-seq/RNA-seq FPKM), for developing wheat grains (cv. Chinese Spring) at 5, 10 and 15 DAA under control and 1-h 42 °C heat stress. TE is reported only when RNA-seq FPKM ≥ 0.2 (otherwise NA). Data are condition means (RNA n=3, Ribo n=2) from Chen et al. 2025 (Genome Biol) with control libraries from Guo et al. 2023 (Plant Cell)."

---

## 9. 未核实到 / 存疑 / 与其他报告的出入（必须如实标注）

1. **60,125 与 RefSeq v2.1 全注释总数的关系：未核实到。** 60,125 是 Table S1 的数据行数（本地逐行确认），但 URGI 的 RefSeq v2.1 注释说明 PDF（https://urgi.versailles.inra.fr/download/iwgsc/IWGSC_RefSeq_Annotations/v2.1/iwgsc_refseqv2.1_annotation_README.pdf）未给出基因总数，且注释 GFF 属 IWGSC sponsor 受限资源；论文正文也未写"60,125"。可参考 `DATA_AUDIT.md` §3.1 的平台登记（Chinese_Spring2.1 `gene_count = 105,534`），本表约为其 57%，判断为"定量后的表达子集"（此判断为推断，非论文原文）。
2. **CK 数值是否被 GB 2025 重新定量：未核实到。** 论文只说"从上一项研究获得数据"，未说明是重新跑 TMM/DESeq2/FPKM 还是直接沿用已发表 FPKM；Table S1 的 CK 列无法与 PlCell 补充表逐格比对（PlCell 补充材料下载受阻，见 §6.2）。
3. **与合作报告的数据出入（建议 Lead 修正 `DATA_AUDIT.md`）**：
   - `DATA_AUDIT.md` §2.2 写 "PRJNA871371（27 runs：RNA 9 + Ribo 9 + Poly 9，均为 n=3）" —— **Ribo 实为 6 runs（每阶段 n=2）**，另有 `pool-1..3` 3 个 RNA run；27 = RNA 9 + Ribo 6 + Poly 9 + pool 3（证据：NCBI E-utilities SRA esummary 的 `LIBRARY_NAME`，见附录 B）。
   - `DATA_AUDIT.md` §4.4 写 "CK RNA n=3、CK Ribo n=3、HS RNA n=3、HS Ribo n=2" —— **CK Ribo 应为 n=2**（PRJNA871371 中 `Ribo_5d-1/2`、`Ribo_10d-1/2`、`Ribo_15d-1/2` 共 6 个 run；GB 2025 补充图 S3 的 Ribo-seq 相关性矩阵也只有 `Ribo_*d_CK−1/−2` 两个 CK 重复）。正确口径：**RNA n=3、Ribo n=2（CK 与 HS 相同）**。
4. **PubMed 网页未直接抓取成功**（JS 人机验证，HTTP 203 只返回空壳）：PMID 与题录改由 NCBI E-utilities `db=pubmed`（权威 MEDLINE 记录）与 Europe PMC REST 确认，三者一致；上述 PubMed URL 仍是可点击的规范链接。
5. **PlCell 2023 补充表内容未核实到**（下载受阻），仅有 PMC 页面上的清单标题；其 Data Set 2 是否含 per-replicate FPKM 未能确认。
6. **更细的栽培细节未核实到**：播种/春化/温室批次编号、单株取样部位（穗中部/全部籽粒）、RNA 提取试剂盒等；两文 Methods 只涉及其一（PlCell 有浸种与生长箱描述，GB 只说温室）。以上不影响本数据集元数据。
7. GB 2025 Data availability 第二句 accession 笔误（PRJNA1135409 vs ref [107]=PRJNA871371）——已按 SRA 元数据判定正确值，见 §3。

---

## 10. 抓取记录（逐条 URL 与用途）

| # | URL | 用途/结果 |
|---|---|---|
| 1 | https://api.crossref.org/works/10.1186/s13059-025-03848-4 | GB 2025 题录、卷期文章号、作者、license、参考文献（含数据集引用 PRJNA1135409/PRJNA871371） |
| 2 | https://api.crossref.org/works/10.1093/plcell/koad075 | PlCell 2023 题录、卷期页、作者、license URL |
| 3 | https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:%2210.1186/s13059-025-03848-4%22&format=json&resultType=core | PMID/PMCID、OA 状态、license、Data availability 链接 |
| 4 | https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:%2210.1093/plcell/koad075%22&format=json&resultType=core | PMID/PMCID、isOpenAccess=N、embargo 日期、PMC 全文链接 |
| 5 | https://pmc.ncbi.nlm.nih.gov/articles/PMC12599102/ | GB 2025 全文（Methods/Results/Data availability/版权） |
| 6 | https://pmc.ncbi.nlm.nih.gov/articles/PMC10226598/ | PlCell 2023 全文（Methods/Results/Data availability/版权） |
| 7 | https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id=41214722,36905284&retmode=json | 两条 PubMed 权威题录确认（标题/期刊/卷期页/PMID/PMCID） |
| 8 | https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=sra&term=PRJNA1135409 | SRA run 数（21） |
| 9 | https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=sra&term=PRJNA871371 | SRA run 数（27） |
| 10 | https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=sra&id=…（两项目全部 run ID） | 逐个 run 的 `LIBRARY_NAME`/策略（附录 B） |
| 11 | https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=bioproject&id=1135409 / 871371 | BioProject 标题、提交单位、注册日期 |
| 12 | https://static-content.springer.com/esm/art%3A10.1186%2Fs13059-025-03848-4/MediaObjects/13059_2025_3848_MOESM2_ESM.xlsx | 下载补充表原文件（md5 85db3d05cae2e413b48c0739d0edc36d），解析 Table S1 全表 |
| 13 | https://pmc.ncbi.nlm.nih.gov/articles/instance/12599102/bin/13059_2025_3848_MOESM1_ESM.pdf | 补充图 PDF（Fig. S3 相关性矩阵样本标签） |
| 14 | https://pmc.ncbi.nlm.nih.gov/articles/instance/10226598/bin/koad075_supplementary_data.zip | PlCell 补充材料（**未取得**，返回下载引导页） |
| 15 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12599102/supplementaryFiles | GB 补充材料 EPMC 打包（备用路径，成功取得 zip） |
| 16 | https://urgi.versailles.inra.fr/download/iwgsc/IWGSC_RefSeq_Annotations/v2.1/iwgsc_refseqv2.1_annotation_README.pdf | RefSeq v2.1 注释说明（未给基因总数；注释数据领取受限） |
| 17 | https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1135409 ; https://www.ncbi.nlm.nih.gov/bioproject/PRJNA871371 | BioProject 规范链接（用于 citation/下载页） |
| 18 | http://wheat.cau.edu.cn/heat_stress_response_wheat_grain_translatome_browser ; http://wheat.cau.edu.cn/wheat_grain_translatome_browser/ | 作者自建 translatome 浏览器（论文给出；建议作为相关资源外链） |

---

## 附录 A：Table S1 抽查行（供 Lead 核对站内表数值）

列顺序 = 18 数值列（RNA 6 → Ribo 6 → TE 6）：

```
TraesCS1A03G0000100LC | 0.07557901 | 0.34874251 | 0.0188027 | 0.21293392 | 0.03740228 | 0.17166459 | 0.32854396 | 2.85886138 | 0.39928751 | 1.34702109 | 1.53606741 | 7.62280857 | NA | 8.19762807 | NA | 6.3260051 | NA | NA
TraesCS1A03G0000700LC | 0.03290344 | 0.09923111 | 0.00872977 | 0.1255907 | 0.01819504 | 0.07709784 | 2.16484703 | 4.44257218 | 2.68129686 | 2.79853439 | 10.3674283 | 66.2021043 | NA | NA | NA | NA | NA | NA
TraesCSU03G0557400   | 161.3333 | 15.29611 | 12996.46 | 3492.3 | 13815.63 | 7345.932 | 7.65184 | 2.474266 | 851.7052 | 1255.205 | 2223.93 | 2871.16 | 0.04742877 | 0.16175786 | 0.06553363 | 0.35942073 | 0.16097203 | 0.39085034
```

校验要点：
- `TraesCS1A03G0000100LC`：`TE_5DAA_HS = 2.85886138 / 0.34874251 = 8.19762807` ✓；`TE_5DAA_CK` 为 NA（RNA 0.0756 < 0.2）。
- `TraesCS1A03G0000700LC`：六个 RNA 均 < 0.2，故六个 TE 全 NA（若站内表该基因 TE 为 0，说明建库时把 NA 误转 0）。
- 全表唯一 ID 60,125 个；LC 10,567 个；`TraesCSU` 529 个；无"18 列全 0"基因（有 2,309 个六 RNA 全 0、2,704 个六 Ribo 全 0）。

## 附录 B：30 个用于本数据表的 SRA run 与 18 列对应

**PRJNA871371（CK / 正常条件，PlCell 2023）**

| 站内列 | run LIBRARY_NAME | SRR |
|---|---|---|
| RNA_5d_CK | RNA_5d-1 / -2 / -3 | SRR21146765 / SRR21146764 / SRR21146753 |
| RNA_10d_CK | RNA_10d-1 / -2 / -3 | SRR21146745 / SRR21146744 / SRR21146743 |
| RNA_15d_CK | RNA_15d-1 / -2 / -3 | SRR21146742 / SRR21146741 / SRR21146740 |
| Ribo_5d_CK | Ribo_5d-1 / -2 | SRR21146755 / SRR21146754 |
| Ribo_10d_CK | Ribo_10d-1 / -2 | SRR21146752 / SRR21146751 |
| Ribo_15d_CK | Ribo_15d-1 / -2 | SRR21146750 / SRR21146749 |
| （本表不用） | Poly_5d/10d/15d-1..3；pool-1..3 | SRR21146739 等 9 个 + SRR21146748/47/46 |

**PRJNA1135409（HS / 1 h 42 °C，Genome Biol 2025）**

| 站内列 | run LIBRARY_NAME | SRR |
|---|---|---|
| RNA_5d_HS | RNA_5d_HS-1 / -2 / -3 | SRR29816650 / SRR29816649 / SRR29816638 |
| RNA_10d_HS | RNA_10d_HS-1 / -2 / -3 | SRR29816636 / SRR29816635 / SRR29816634 |
| RNA_15d_HS | RNA_15d_HS-1 / -2 / -3 | SRR29816633 / SRR29816632 / SRR29816631 |
| Ribo_5d_HS | Ribo_5d_HS-1 / -2 | SRR29816630 / SRR29816648 |
| Ribo_10d_HS | Ribo_10d_HS-1 / -2 | SRR29816647 / SRR29816646 |
| Ribo_15d_HS | Ribo_15d_HS-1 / -2 | SRR29816645 / SRR29816644 |
| （本表不用） | sRNA_5d_CK-1..3 / sRNA_5d_HS-1..3 | SRR29816643/42/41 / 40/39/37 |

18 个数值列 = 上述 12 个条件均值（RNA 为 3 重复均值，Ribo 为 2 重复均值）+ 6 个由均值算出的 TE。**表中没有 per-replicate 值、没有 SD**；论文补充材料也未提供 per-replicate 表达矩阵（GB Table S12 仅有 qRT-PCR 重复）。
