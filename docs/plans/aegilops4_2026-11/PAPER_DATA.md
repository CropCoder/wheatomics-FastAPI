# PAPER_DATA — 4 个二倍体 Aegilops 基因组：论文与 Zenodo/NCBI 数据核查报告

> **任务**：共享任务板 `task-1`（owner: paper-data）。核查对象：Khadka et al., *BMC Plant Biology* 2026，DOI `10.1186/s12870-026-10046-2`；注释数据 Zenodo record `22681907`。
> **核查时间**：2026-11-11 17:53–18:35 CST。
> **证据口径**：① 论文 PDF（本目录 `khadka_2026_four_diploid_Aegilops_BMCPlantBiol.pdf`，24 页，md5 `09c2b1e4963706a29e7b5a19f36c6489`）；② 论文三个补充文件（`zenodo_probe/paper_supp/`）；③ Zenodo REST API 与本目录 `zenodo_probe/` 实测下载（全部 md5 对 Zenodo API 校验）；④ NCBI Datasets v2 API + Assembly FTP（`assembly_report.txt` / `md5checksums.txt` / `feature_count.txt`）；⑤ 实测命令（gzip/awk/python/gffread/NCBI efetch 区域回取）。
> **约束遵守**：只读生产系统，未改仓库源码、未 git commit、未访问生产服务器。除本文件外仅在 `zenodo_probe/` 下放探针下载（+ `paper_supp/` 三个补充文件）与本目录 1 个 PDF。
> **配套文件**：平台接入侧现状与命名方案见同目录 `PLATFORM_BASELINE.md`（task-2）；本报告只负责“论文与数据事实”。

---

## 0. 结论速览（上线计划可直接引用）

| # | 结论 | 证据 |
|---|---|---|
| C1 | **基因组 FASTA 可得，不是阻塞项**。4 个组装全部作为 **GenBank GCA** 沉积在 NCBI（Chromosome 级、各 7 条假染色体），BioProject 与论文 Data availability 逐字对应。Zenodo 确实没有 FASTA，但不需要向作者补要 | §4；论文 p17；Zenodo README；`api.ncbi.nlm.nih.gov/datasets/v2alpha/genome/accession/<GCA>/dataset_report` |
| C2 | 四者是**新组装、且是新材料登录号**：*Ae. comosa* IPK-AE783、*Ae. markgrafii* EKC105_RL5723、*Ae. umbellulata* IPK-AE740、*Ae. uniaristata* IPK-AE680；与平台现有 PI551049 / TA1851 / PI554389 不是同一材料；markgrafii 与 uniaristata 为该物种**首个**染色体级组装 | §4.1、§4.2；论文 p2（“first assemblies of Ae. markgrafii and Ae. uniaristata”）、p14（Discussion “The completion of all 11 diploid Aegilops genomes…”） |
| C3 | 注释数据齐（gene GFF + protein FASTA + TE GFF3），**缺 CDS**；CDS 必须用 `gffread` 从「NCBI FASTA + Zenodo GFF」生成。已在 4 物种 **16 个染色体位点 + 1 个未定位 scaffold 位点**上端到端验证：gffread 翻译产物与 Zenodo 蛋白 **100% 一致**（仅末端终止符差异） | §5.6；实测 `gffread -E ... -x/-y` |
| C4 | **GFF 归一化是主要工作量**（不是阻塞）：① 全部 seqid 需改名（NCBI FASTA 头是 GenBank/WGS 登录号，GFF 是 `1M..7M`/`1C..7C`/`1U..7U`/`1N..7N` + scaffold）；② **51,666 个 LC（TAMA/STRG 家族）mRNA ID 不以 `.数字` 结尾**（以 `.p1`…`.p10` 结尾），按平台 SOP §1.1 必须改写；③ pep 终止符 3 物种是 `.`、umbellulata 是 `*`，都不在氨基酸字母表内，需统一清理；④ ChrUn 基因 38/53/1,103/66 个必须保留为 `ChrUn_*` | §5.3、§6 |
| C5 | **TE 轨道可行但需按物种改名**：4 个 TE GFF 均为 EDTA v2.2.1 GFF3（SO 类型），可直接作 JBrowse GFF3 轨道；但 comosa 的 TE seqid 是裸数字 `1..7` + 数字 token，umbellulata/uniaristata 用缩写 `S_S_*`，markgrafii 与基因 GFF 一致。映射均可由 NCBI assembly_report 确定性推导（唯一例外：umbellulata `S_S_73_2` 对应 scaffold 不在 NCBI 提交中，仅 1 条 TE 特征） | §7 |
| C6 | 数据可镜像：论文 CC-BY-4.0（PDF 另标 © Crown 2026），Zenodo CC-BY-4.0；推荐引用文本见 §8 | §8 |
| C7 | 需要记录的**数据瑕疵**（不阻塞上线，但不要照抄）：Zenodo 的 `Ae.markgrafii_genes_LC.gff3.gz` 内容其实是 HC（与 HC 文件逐字节解压相同）；README 文件名/数字与实物有 4 处不一致；论文 Table 1 的 umbellulata 组装大小（4.40 Gb）与 NCBI（4.268 Gb）不符；论文 Table 3 与 Table S12、README 基因数互相差 1–2 个；comosa 蛋白 FASTA 有 6,573 条含内部终止符（注释帧移，需清洗）；论文当前为 **Article in Press** | §3.4、§3.5、§5.5、§9 |

**一句话给 Lead**：数据侧没有“拿不到 FASTA”的硬阻塞；真正要投入的是**一轮一次性归一化脚本 + 4 次 gffread + md5 校验**，之后即可按 SOP 跑 `check_genome_files.py` 闸门并进入流水线。建议在归一化后增加一条验收断言：**gffread 生成的 pep 条数 = 51,203/47,246/49,677/50,416，且抽样序列与 Zenodo 蛋白一致**（本报告已给出可直接复用的抽样方法）。

---

## 1. 论文元数据与获取证据

### 1.1 书目信息

| 字段 | 值 | 证据 |
|---|---|---|
| 标题（as published，注意末尾没有写出 4 个物种名） | *Chromosome-level reference genome assemblies and annotation of four diploid Aegilops* | Crossref `message.title`；BMC HTML `<title>`；PDF p1 |
| 作者（9 人） | Bijendra Khadka, Tara Edwards, Madeleine Lévesque-Lemay, Jennifer Ens, Harmeet S. Chawla, Chunfang Zheng, Frank M. You, Curtis J. Pozniak, Sylvie Cloutier | Crossref；PDF p1；Zenodo creators（含 ORCID：Khadka 0000-0001-5137-860X，Edwards 0009-0004-4450-6561） |
| 单位 | AAFC Ottawa Research and Development Centre；University of Saskatchewan Crop Development Centre；Chawla 另有 University of Manitoba（PDF p1 脚注） | PDF p1 |
| 期刊 / ISSN | *BMC Plant Biology*（1471-2229） | Crossref `container-title`；BMC HTML `citation_issn` |
| DOI | `10.1186/s12870-026-10046-2` | Crossref `message.DOI` |
| 出版日期 / 类型 | 2026-11-07；Research article，**Article in Press**（early access，正式版会替换；见 §1.4） | Crossref `published.date-parts`；BMC HTML `citation_online_date` / “Published: 07 November 2026” |
| 投稿/接收 | Received 2025-11-06 / Accepted 2026-09-22 | PDF p1 |
| 许可 | **CC-BY-4.0**（Crossref license URL `https://creativecommons.org/licenses/by/4.0`）；PDF 标注 **© Crown 2026**（加拿大政府 Crown copyright，仍以 CC-BY 发布） | Crossref `message.license`；PDF p1 与 p17 “Open Access” 段 |
| 关键词 | Aegilops; Pseudochromosome assembly; Annotation; Comparative genomics; Phylogenetic relationship | BMC HTML citation metadata |
| PubMed / PMC | 核查时 **PubMed 与 PMC 均未收录**（`esearch db=pubmed/pmc term="10.1186/s12870-026-10046-2[doi]"` count=0；Unpaywall 亦无记录） | 实测 E-utilities；`api.unpaywall.org/v2/10.1186/...` |
| 全文获取 | PDF 24 页、6,112,465 B。BMC 页面的 `citation_pdf_url` 直链返回 404，实际可用地址为 Springer 的 *reference PDF*：`https://link.springer.com/content/pdf/10.1186/s12870-026-10046-2_reference.pdf`（下载后 `file` = PDF 1.7，内容为完整 24 页正文） | 实测 curl（BMC track/pdf 返回 HTML 反爬页；Springer `_reference.pdf` 返回 200/6,112,465 B） |
| 补充材料 | Additional file 1（DOCX，15 张表，3,246,955 B）、Additional file 2（XLSX，Table S8/S14/S15，49,524 B）、Additional file 3（DOCX 方法细节，73,176 B）；均已下载到 `zenodo_probe/paper_supp/` | `https://static-content.springer.com/esm/art%3A10.1186%2Fs12870-026-10046-2/MediaObjects/12870_2026_10046_MOESM{1,2,3}_ESM.{docx,xlsx,docx}` |

### 1.2 摘要（原文英中对照，用于网页文案）

原文（PDF p1）要点：
- 用 **PacBio HiFi + BioNano optical mapping + Hi-C** 混合策略组装 4 个二倍体 Aegilops 染色体级参考基因组；
- 组装大小 **3.58–4.48 Gb**，BUSCO 完整度 **97.9–98.4%**；
- 整合多组织 RNASeq + IsoSeq 注释，共 **47,246–51,203** 个蛋白编码基因；
- 共线性/系统发育：4 个基因组的二倍体在 D-lineage 内聚为姐妹单系群；
- 结论：完成全部 11 个二倍体 Aegilops 物种的高质量组装集合。

### 1.3 论文自述的方法链（综述用，页码为 PDF 页）

| 环节 | 关键参数 | 页码 |
|---|---|---|
| 材料 | 4 个登录号；*markgrafii* EKC105_RL5723 原始来源 PGRC CN 34579（原 PGR 6682）；每份材料自交 ≥3 代 | p3；Additional file 1 Table S1 |
| HiFi 测序 | PacBio Sequel II（Génome Québec）；SMRT Link v11.0.0.146107；`ccs --min-passes 3 --hifi-kinetics` | p3–4 |
| 组装 | **hifiasm v0.15.4-r347 `-l0`** | p4 |
| 光学图谱挂载 | Bionano Saphyr（CNRGV/INRAE）；**Bionano Solve v3.7 `hybridScaffold.pl`**（hybridScaffold_DLE1_config.xml） | p3–4 |
| Hi-C 挂载 | DpnII 建库、NovaSeq 6000 PE150；**YaHS**；juicer/Juicebox 人工校正 | p4 |
| 组装评估 | BUSCO genome mode：MetaEuk v5.34c21f2 + hmmsearch v3.1，embryophyta_odb10；统计脚本 custom Perl + BioKit | p4 |
| RNA 数据 | 4 物种 ×10 组织 ×3 生物学重复 ×3 子样本 = 360 份；120 个测序文库；STAR v2.7.10a | p4 |
| IsoSeq | SMRT Link v12.0.0；IsoSeq3（lima/refine/cluster v2.4.0/3.4.0）；minimap2 `-ax splice -uf --secondary=no -C5`；TAMA collapse | p4–5 |
| 重复序列 | **EDTA v2.2.1**（`--overwrite 1 --sensitive 1 --anno 1 --evaluate 1 --cds --curatedlib`）+ TREP 库；着丝粒= Cereba/Quinta LTR 密度；LTR 插入时间 T=Ks/2r（r=1.3×10⁻⁸） | p5 |
| 基因注释 | softmask（bedtools v2.30）→ BRAKER v3.0.3/AUGUSTUS v3.3.2、GeneMarkS-T、TSEBRA v1.0.3、StringTie2 v2.1.7、CD-HIT v4.7、**Miniprot v0.6**、**EVM** 合并；AHRD 功能描述；BUSCO protein mode | p5–6 |
| 比较/系统发育 | minimap2、D-GENIES、MCScanX、DupGen_finder、Orthofinder v2.5.5、MAFFT v7.5.20、Gblocks v0.91b、IQ-TREE 2 | p6 |

### 1.4 论文当前为 “Article in Press” 的原文与影响

PDF p1 / BMC 页面原文：

> “This Article in Press is shared early to give you faster access to new research. It is citable and carries a permanent DOI. The final edited version will replace it automatically.”
> BMC 页面：“We’re sharing this article early to provide faster access to peer-reviewed, accepted research. It is citable and carries a permanent DOI. **This version is subject to further edits and will be replaced automatically by the final Version of Record.** All legal disclaimers apply.”

影响：**所有数字以本报告实测 + NCBI 为准**；若正式 VOR 调整表格数字，不需要重新核查数据文件（Zenodo/NCBI 不变）。引用时应标注 “Article in press / 2026-11-07”。

### 1.5 Data availability 原文（PDF p17，逐字）

> “**Data availability** The genome assemblies and all raw sequencing data generated in this study including PacBio HiFi, Hi-C, IsoSeq and RNASeq have been deposited in the NCBI Assembly and Sequence Read Archive (SRA) database. Data for *Ae. comosa* IPK-AE783, *Ae. markgrafii* EKC105_RL5723, *Ae. umbellulata* IPK-AE740, and *Ae. uniaristata* IPK-AE680 are held under Bioproject accessions **PRJNA1506336, PRJNA1174795, PRJNA1114735, PRJNA1154594**, respectively. Bionano optical map data and the gene and repeat annotation datasets are available on Zenodo: **https://doi.org/10.5281/zenodo.22681907**.”

**落实核对（本报告 §3/§4 已逐一验证）**：
- 4 个 BioProject → NCBI Assembly 各有 1 个 GCA（Chromosome 级、7 条假染色体；BioProject 号与论文原文逐字一致）；详见 §4。
- SRA：每个 BioProject 在 SRA 有 **40 条记录**（`esearch db=sra term=<PRJNA>`）。
- Zenodo：25 个文件 = 标注 + 光学图，**不含组装 FASTA**（与 Data availability“组装在 NCBI”一致）。

**Code availability 原文（PDF p17）**：软件均为公开引用；自编脚本在 GitLab（PDF 中链接被零宽字符打断，可还原为 `https://gitlab.com/bijenro/chromosome-level-reference-genome-assemblies-and-annotation-of-four-diploid-aegilops`）。

---

## 2. 论文关键统计（与 NCBI 对照）

### 2.1 组装统计：论文 Table 1（p9） vs NCBI 当前组装（实测）

| 指标 | Ae. comosa IPK-AE783 | Ae. markgrafii EKC105_RL5723 | Ae. umbellulata IPK-AE740 | Ae. uniaristata IPK-AE680 |
|---|---|---|---|---|
| 论文 Genome size（流式，Gb） | 5.3 ± 0.01 | 4.3 ± 0.01 | 5.1 ± 0.01 | 5.4 ± 0.03 |
| 论文 Assembly size（Gb） | 4.41 | 3.58 | **4.40** ⚠ | 4.48 |
| NCBI total length（Gb） | 4.408 | 3.577 | **4.268** ⚠ | 4.476 |
| 论文 pseudochromosome（Gb/%） | 4.41 (99.90%) | 3.57 (99.72%) | 4.24 (96.40%) | 4.46 (99.70%) |
| 论文 unplaced scaffolds（n / Gb） | 10 / 0.004 | 17 / 0.013 | **244 / 0.160** ⚠ | 14 / 0.013 |
| NCBI unplaced（n / bp） | 10 / 2,636,236 | 17 / 7,326,274 | **243 / 32,570,956** | 14 / 9,381,524 |
| 假染色体数 | 7 | 7 | 7 | 7 |
| 论文 BUSCO genome mode（%） | 98.4 | 98.1 | 98.0 | 97.9 |
| NCBI contig N50（bp） | 9,246,063 | 9,048,916 | 7,445,361 | 31,980,500 |
| NCBI scaffold N50（bp） | 637,736,480 | 489,410,094 | 634,959,311 | 652,967,279 |
| NCBI GC（%） | 46.5 | 47.0 | 47.0 | 46.5 |
| HiFi 覆盖度 | 30.4× | 35.4× | 28.1× | 35.8× |
| Hi-C 覆盖度 | 55.7× | 91× | 43.5× | 72.5× |
| 论文 NCBI 备注 | GCA_052815735.**2**（Expected final version: Yes） | GCA_052815875.1（No） | GCA_060308565.1（No） | GCA_052815765.1（No；RefSeq category=Reference Genome，但无 GCF） |

> ⚠ **Ae. umbellulata 论文数字自相矛盾**：Table 1 写 Assembly 4.40 Gb / unplaced 0.160 Gb，而 Additional file 1 **Table S6**（组装比较表）与 **Table S7** 写 4.24 Gb / ChrUn 161 Mb、Table S14 中最大未定位 scaffold 仅 9.57 Mb；NCBI 提交实际 4.268 Gb / 32.6 Mb。**上线一律以 NCBI 数字为准**（并记录论文瑕疵，见 §9-R4）。

**附：论文 Additional file 1 Table S5（测序量；正文 p7 引用）**

| 物种 | HiFi reads 数 | 平均长度（bp） | HiFi 总量（Gb） | 覆盖度 | Hi-C reads 数 | Hi-C 覆盖度 |
|---|---|---|---|---|---|---|
| Ae. comosa | 10,884,361 | 14,800 | 161.09 | 30.4× | 1,968,858,824 | 55.72× |
| Ae. markgrafii | 10,420,633 | 14,617 | 152.32 | 35.4× | 2,609,112,652 | 91.02× |
| Ae. umbellulata | 9,097,241 | 15,769 | 143.45 | 28.1× | 1,478,391,360 | 43.48× |
| Ae. uniaristata | 13,917,751 | 13,988 | 194.68 | 35.8× | 2,611,156,516 | 72.53× |

（证据：`zenodo_probe/paper_supp/Additional_file_1.docx` 表 5；与论文 p7 “Between 143 and 195 Gb HiFi reads … coverage 28.1–35.8X” 一致。）

### 2.2 基因注释统计：论文 Table 3（p12） vs Zenodo GFF 实测 vs README

| 指标 | Ae. comosa | Ae. markgrafii | Ae. umbellulata | Ae. uniaristata |
|---|---|---|---|---|
| 论文 Table 3 总基因 | **51,203** | **47,246** | **49,677** | **50,416** |
| Zenodo GFF 实测（gene=mRNA） | **51,203** | **47,246** | **49,677** | **50,416** |
| 论文 HC / LC（Table 3） | 37,622 / 13,581 | 34,133 / 13,113 | 35,799 / 13,878 | 35,816 / 14,600 |
| GFF 实测 HC / LC（ID 家族判定） | 37,622 / 13,581 | 34,133 / 13,113 | 35,799 / 13,878 | 35,816 / 14,600 |
| Zenodo README 汇总 | 51,205 / 37,623 / 13,582 ⚠ | 47,246 / 34,133 / 13,113 | 49,677 / 35,799 / 13,878 | 50,416 / 35,816 / 14,600 |
| Additional file 1 Table S12 汇总 | 37,623 / 13,582 ⚠ | 34,133 / 13,113 | 35,799 / 13,878 | 35,815 ⚠ / 14,600 |
| exon = CDS 数（实测） | 180,142 | 172,497 | 177,553 | 176,014 |
| 其他 feature 类型 | 无（仅 gene/mRNA/exon/CDS） | 同 | 同 | 同 |
| BUSCO protein mode（Table 3） | 97.2% | 96.6% | 96.9% | 96.6% |
| AHRD 有描述比例（p12） | 88.8–90.6%（42,388–46,400） | 同左 | 同左 | 同左 |

> ✅ **GFF 实测与 Table 3 完全一致**；README 与 Table S12 各差 1–2 个（README: comosa 51,205/37,623/13,582；S12: comosa 37,623/13,582，uniaristata HC 35,815）。以 **GFF 实测 + Table 3** 为准。

### 2.3 重复序列：论文 Table 2（p9）

| 类别 | Ae. comosa | Ae. markgrafii | Ae. umbellulata | Ae. uniaristata |
|---|---|---|---|---|
| Ty3/Gypsy（% / Mb） | 42.9 / 1889.17 | 45.2 / 1613.77 | 47.1 / 1990.00 | 39.5 / 1766.36 |
| Ty1/Copia | 23.3 / 1026.49 | 19.0 / 676.58 | 17.4 / 733.97 | 20.9 / 932.43 |
| Unclassified LTR-RT | 4.3 | 6.7 | 5.0 | 8.2 |
| LINE | 0.3 | 0.3 | 0.4 | 0.4 |
| SINE | 1.1 | 1.3 | 1.2 | 1.2 |
| CACTA | 9.3 | 7.5 | 9.9 | 11.2 |
| Mutator / PIF-Harbinger / Tc1-Mariner / hAT | 0.8 / 1.1 / 1.8 / 0.2 | 1.0 / 1.2 / 1.2 / 0.3 | 1.0 / 1.1 / 1.2 / 0.2 | 0.8 / 1.1 / 1.2 / 0.2 |
| Helitron | 2.1 | 1.8 | 1.8 | 2.5 |
| 45S rDNA | 0.02 | 0.04 | 0.00 | 0.01 |
| **Total TE** | **88.2% (3881.01 Mb)** | **86.3% (3079.81 Mb)** | **87.2% (3687.30 Mb)** | **87.9% (3931.90 Mb)** |

其他结果要点（引用时可写进网页/新闻）：LTR 插入时间分析显示 comosa/markgrafii 近期爆发（~0.5 Ma），uniaristata/umbellulata 以古老插入为主（p10–11）；着丝粒用 Cereba/Quinta 定位但**未提供坐标文件**（§7.4）；共线性发现多个种内/种间重排（p13–14）；系统发育见 Fig 4（p13）。

---

## 3. Zenodo record 22681907：清单与实测核验

### 3.1 record 元数据（REST API 实测）

| 字段 | 值 |
|---|---|
| record ID / 版本 | `22681907`；**单一版本**（`/api/records/22681907/versions` → total 1，无 version 字段） |
| DOI / Concept DOI | `10.5281/zenodo.22681907` / `10.5281/zenodo.22680410`（conceptrecid `22680410`） |
| 标题 | Gene and repeat annotations for reference genome assemblies of four diploid Aegilops species (Ae. comosa, Ae. markgrafii, Ae. umbellulata, Ae. uniaristata) |
| 发布日期 | `2026-09-09`（created 2026-09-09T19:48:18Z，modified 2026-09-09T19:51:11Z） |
| 许可 | **CC-BY-4.0**（`metadata.license.id = cc-by-4.0`） |
| 文件数 / 总大小 | **25 个 / 422,315,347 B（0.422 GB）** — 任务背景写“26 个”，以 API 为准：4 物种 ×(HC、LC、HC_LC.gff3、HC_LC.fasta、EDTA、OpticalMap)=24 + README = **25** |
| creators | 同论文 9 位作者（含单位与 ORCID） |
| related_identifiers | **null**（Zenodo 未挂论文 DOI —— 元数据瑕疵，不影响数据） |
| 描述 | “Structural and functional annotation datasets for chromosome-level reference genome assemblies of four diploid *Aegilops* species … For each species the record provides protein-coding gene models in GFF3 (high- and low-confidence combined), the corresponding protein sequences in FASTA, and the transposable element and repeat annotation in GFF3.” |
| API | `https://zenodo.org/api/records/22681907` |

### 3.2 全文件清单（25 个；md5 来自 Zenodo API）

| 文件名 | 大小（B） | md5 | 用途 |
|---|---|---|---|
| README_zenodo_diploid_Aegilops.md | 3,142 | `1c7451a4a25d10661daab953e7010e85` | 说明/汇总/NCBI 关联 |
| **Ae.comosa_genes_HC_LC.gff3.gz** | 4,708,571 | `8e05dc91f18fd4de746dcba363331cb5` | 结构注释（HC+LC）★ |
| **Ae.comosa_genes_HC_LC.fasta.gz** | 10,668,666 | `33ac7da82b136c5956f1970d3f78ae87` | 蛋白序列（全部模型）★ |
| Ae.comosa_genes_HC.gff3.gz | 3,820,597 | `dfdd27fe50dbf725d7d50979ddf8fb69` | 仅 HC 结构注释 |
| Ae.comosa_genes_LC.gff3.gz | 801,780 | `c8bc191d3a58328d7898359311e84aba` | 仅 LC 结构注释 |
| Ae.comosa.EDTA.TEanno.gff3.gz | 75,641,029 | `c863fc3aeafbf0d5fb67b85411346080` | TE/重复 GFF3（EDTA） |
| Ae.comosa_OpticalMap.cmap.gz | 13,509,563 | `700c6eb96e13efcecd07b2693dd2f4a9` | Bionano 光学图谱（非平台必需） |
| **Ae.markgrafii_genes_HC_LC.gff3.gz** | 4,456,369 | `a1e1c73fe12c3d11923bae0d879e47c5` | 结构注释（HC+LC）★ |
| **Ae.markgrafii_genes_HC_LC.fasta.gz** | 9,859,590 | `d51d58c9a15095f9c98f86b5ceffc3a5` | 蛋白序列 ★ |
| Ae.markgrafii_genes_HC.gff3.gz | 3,586,710 | `9715872029a34488bcc3a4c3f75df270` | 仅 HC |
| Ae.markgrafii_genes_LC.gff3.gz | 3,586,710 | `bca40c6f500a64d6cbf6518bc86dcd77` | ⚠ 内容=HC（见 §3.4），不要用 |
| Ae.markgrafii.EDTA.TEanno.gff3.gz | 62,222,449 | `29378012d071f016f13c00ba3c95c22a` | TE GFF3 |
| Ae.markgrafii_OpticalMap.cmap.gz | 11,739,901 | `2aaa9a78845784adc054737634ed64b0` | 光学图谱 |
| **Ae.umbellulata_genes_HC_LC.gff3.gz** | 4,637,390 | `6fadfa96c5bfdb9cd0900abcb7f851c5` | 结构注释 ★ |
| **Ae.umbellulata_genes_HC_LC.fasta.gz** | 11,846,334 | `f57298a557764fee668ab6b894be18f0` | 蛋白序列 ★ |
| Ae.umbellulata_genes_HC.gff3.gz | 3,733,405 | `14c848b52ec572d0db1b47e372d37271` | 仅 HC |
| Ae.umbellulata_genes_LC.gff3.gz | 899,496 | `c999954964f4c10ee11793c121dc8c8d` | 仅 LC |
| Ae.umbellulata.EDTA.TEanno.gff3.gz | 73,292,397 | `3dde75de58069ebb7e8845c1f3d008e9` | TE GFF3 |
| Ae.umbellulata_OpticalMap.cmap.gz | 12,418,936 | `77420028eb0e39d3d9526ebbc1d51e5f` | 光学图谱 |
| **Ae.uniaristata_genes_HC_LC.gff3.gz** | 4,613,254 | `286b2c5b6d183134f4bb9bb38788c43a` | 结构注释 ★ |
| **Ae.uniaristata_genes_HC_LC.fasta.gz** | 10,279,500 | `8f281f0817028b85f7747b77e83d0440` | 蛋白序列 ★ |
| Ae.uniaristata_genes_HC.gff3.gz | 3,682,232 | `e48d7d5a4db6bf6ae8732291a0914c16` | 仅 HC |
| Ae.uniaristata_genes_LC.gff3.gz | 841,283 | `aa76bac00ef1d0620abc1c69d6e59fd7` | 仅 LC |
| Ae.uniaristata.EDTA.TEanno.gff3.gz | 77,947,960 | `1c1d9f51a518dc23ae23ea6d6f01df53` | TE GFF3 |
| Ae.uniaristata_OpticalMap.cmap.gz | 13,518,083 | `e67b310a33c327cc6b7005de79ea27f8` | 光学图谱 |

★ = 上线主输入。**注意：Zenodo 没有基因组 FASTA、没有 CDS/GTF/BED。**

### 3.3 已下载探针文件与 md5 校验（全部通过）

`zenodo_probe/` 下 14 个文件逐个 `md5` 与 Zenodo API `checksum` 比对：**14/14 一致**。其中全量下载：4 物种 `*_genes_HC_LC.gff3.gz` + `*_genes_HC_LC.fasta.gz`、comosa HC/LC GFF、markgrafii HC/LC GFF、markgrafii EDTA（62 MB）、README；comosa/umbellulata/uniaristata 的 EDTA 用于全量 seqid 核验后放在 `/tmp`（62–78 MB，未进工作区）。

| 文件 | 大小（B） | md5 与 Zenodo 一致 |
|---|---|---|
| README_zenodo_diploid_Aegilops.md | 3,142 | ✅ |
| Ae.comosa_genes_HC_LC.gff3.gz / .fasta.gz | 4,708,571 / 10,668,666 | ✅ / ✅ |
| Ae.comosa_genes_HC.gff3.gz / _LC.gff3.gz | 3,820,597 / 801,780 | ✅ / ✅ |
| Ae.markgrafii_genes_HC_LC.gff3.gz / .fasta.gz | 4,456,369 / 9,859,590 | ✅ / ✅ |
| Ae.markgrafii_genes_HC.gff3.gz / _LC.gff3.gz | 3,586,710 / 3,586,710 | ✅ / ✅（内容问题见 §3.4） |
| Ae.markgrafii.EDTA.TEanno.gff3.gz | 62,222,449 | ✅ |
| Ae.umbellulata_genes_HC_LC.gff3.gz / .fasta.gz | 4,637,390 / 11,846,334 | ✅ / ✅ |
| Ae.uniaristata_genes_HC_LC.gff3.gz / .fasta.gz | 4,613,254 / 10,279,500 | ✅ / ✅ |
| （额外全量核验）Ae.comosa / Ae.umbellulata / Ae.uniaristata EDTA.TEanno.gff3.gz | 75,641,029 / 73,292,397 / 77,947,960 | ✅ / ✅ / ✅ |

### 3.4 ⚠ 数据瑕疵 1：`Ae.markgrafii_genes_LC.gff3.gz` 的内容其实是 HC

实测证据：

```bash
diff <(gzip -dc Ae.markgrafii_genes_HC.gff3.gz) <(gzip -dc Ae.markgrafii_genes_LC.gff3.gz)
# 无输出（逐行完全相同）；两者非#行数都是 364,696；gene 数都是 34,133（=HC 数，不是 LC 13,113）
gzip -dc Ae.markgrafii_genes_LC.gff3.gz | awk -F'\t' '$3=="gene"' | grep -c 'ID=gene.model'   # → 0
```

- 两个文件大小相同（3,586,710 B）但 md5 不同（`971587…` vs `bca40c…`）→ 只是 gzip 头/时间戳差异，**解压内容相同**；md5 与 Zenodo API 一致，说明**打包侧错误**，不是下载损坏。
- 正确的 LC 数据在 `Ae.markgrafii_genes_HC_LC.gff3.gz` 中：HC 34,133 + LC 13,113 = 47,246 ✅。
- **结论**：上线一律用 `*_genes_HC_LC.gff3.gz`（4 物种都如此），不使用 markgrafii 的独立 HC/LC 文件；建议在网页/README 注明并向作者反馈该 Zenodo 打包 bug。

### 3.5 ⚠ 数据瑕疵 2：README 与实际文件/数字的 4 处不一致

| README 写的 | 实际 | 影响 |
|---|---|---|
| 文件名模板 `<Species>_proteins.fasta.gz` | 实际为 `<Species>_genes_HC_LC.fasta.gz` | 照 README 写脚本会 404 |
| 前缀 `Aegilops_comosa_IPK-AE783` 等（全物种名 + 材料名） | 实际文件前缀 `Ae.comosa_*`、`Ae.markgrafii_*`… | 同上 |
| 总基因 comosa **51,205**（HC 37,623 / LC 13,582） | 实测 GFF/Table 3 = **51,203**（37,622 / 13,581） | 引用数字应以 GFF/Table 3 为准 |
| 文件数/内容说明未提光学图 README 中有 6 类 | 实际 25 个文件（含 4 个 OpticalMap，README 表格漏列） | 仅清单核对用 |

### 3.6 README 关键原文（摘录，`zenodo_probe/README_zenodo_diploid_Aegilops.md`）

> “The gene and transposable elements (TEs) annotation datasets for four diploid *Aegilops* chromosome-level reference genome assemblies … **Assemblies and raw sequencing reads are deposited at NCBI (see Linked NCBI records below). This record contains the structural and functional annotation files, which are not part of the NCBI submission.**”

> Linked NCBI records：comosa `PRJNA1506336`；markgrafii `PRJNA1174795`；umbellulata `PRJNA1114735`；uniaristata `PRJNA1154594`。
> License：“Creative Commons Attribution 4.0 International (CC BY 4.0)”。

---

## 4. NCBI 组装登录实证（关键：FASTA 来源）

### 4.1 主表（4/4 全部查到，均为 Chromosome 级）

| 项目 | Ae. comosa | Ae. markgrafii | Ae. umbellulata | Ae. uniaristata |
|---|---|---|---|---|
| 材料 / 基因组 | IPK-AE783 / M | EKC105_RL5723 / C | IPK-AE740 / U | IPK-AE680 / N |
| **GCA 登录号** | **GCA_052815735.2** | **GCA_052815875.1** | **GCA_060308565.1** | **GCA_052815765.1** |
| Assembly name | ASM5281573v2 | ASM5281587v1 | AAFC_Aeum_AE740_v02 | ASM5281576v1 |
| Assembly level / type | Chromosome / haploid | Chromosome / haploid | Chromosome / haploid | Chromosome / haploid |
| Release date | 2026-09-13 | 2025-09-24 | 2026-08-21 | 2025-09-24 |
| BioProject | PRJNA1506336 | PRJNA1174795 | PRJNA1114735 | PRJNA1154594 |
| BioSample | SAMN43422618 | SAMN44347220 | SAMN41492411 | SAMN43422673 |
| WGS project | JBHEGE02 | JBLROG01 | JBDZUH01 | JBHEGF01 |
| 总长（bp / Gb） | 4,407,741,597 / 4.408 | 3,577,170,360 / 3.577 | 4,268,089,219 / 4.268 | 4,475,943,907 / 4.476 |
| 序列数（染色体+未定位） | 17（7+10） | 24（7+17） | 250（7+243） | 21（7+14） |
| contig N50 / contig 数 | 9,246,063 / 826 | 9,048,916 / 721 | 7,445,361 / 1,178 | 31,980,500 / 299 |
| scaffold N50 / 数 | 637,736,480 / 17 | 489,410,094 / 24 | 634,959,311 / 250 | 652,967,279 / 21 |
| GC% / 覆盖度 | 46.5 / 30.4× | 47.0 / 35.4× | 47.0 / 28.1× | 46.5 / 35.8× |
| 组装方法（NCBI 记录） | HiFiasm v0.15.4-r347 | 同 | 同 | 同 |
| Expected final version | **Yes** | No | No | no（RefSeq category=Reference Genome，但无 GCF） |
| 浏览器页面 | https://www.ncbi.nlm.nih.gov/assembly/GCA_052815735.2 | …/GCA_052815875.1 | …/GCA_060308565.1 | …/GCA_052815765.1 |
| FASTA FTP 目录 | https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/052/815/735/GCA_052815735.2_ASM5281573v2/ | …/GCA/052/815/875/GCA_052815875.1_ASM5281587v1/ | …/GCA/060/308/565/GCA_060308565.1_AAFC_Aeum_AE740_v02/ | …/GCA/052/815/765/GCA_052815765.1_ASM5281576v1/ |
| `*_genomic.fna.gz` md5 | `38b8436f9c4eb360a066a1c79f1a122a` | `2a55e0ca2d74109c63c84dcb6d6a077a` | `1766c56e9ed9f2d6bcf292925a6628bb` | `b9b855678d7beba1cdd58f7ed89123eb` |
| `*_assembly_report.txt` md5 | `0dec99d5610b511856625b83e23f6b6d` | `4e31f0cad2191e46e670e94fc0e8deb5` | `f005dec95b7e253ab9beb8e9033f135a` | `0abc640548aa96a5de13c50075b21a0a` |
| 下载体积（Datasets API） | all_genomic_fasta 1,239.9 MB | 1,008.0 MB | 1,209.8 MB | 1,279.5 MB |

**证据 URL/命令**
- Datasets API：`https://api.ncbi.nlm.nih.gov/datasets/v2alpha/genome/accession/<GCA>/dataset_report`（stats/level/biosample/wgs），`.../download_summary`（文件种类与体积）。
- FTP 目录 + `md5checksums.txt` + `*_assembly_report.txt`（seqid ↔ GenBank 登录号映射）。
- NCBI `feature_count.txt`：4 个组装的 `gene / protein_coding` = **0** → **NCBI 上没有基因注释**，注释只能来自 Zenodo（印证 README）。

### 4.2 假染色体命名与 seqid 映射（JBrowse/BLAST 归一化必需）

| 物种 | 染色体 seqid（NCBI Sequence-Name） | GenBank 登录号（示例） | 未定位序列 |
|---|---|---|---|
| comosa | **1M, 2M, 3M, 4M, 5M, 6M, 7M** | CM127985.2 … CM127991.1 | 10 条：`Super-Scaffold_100133_4M`, `_100148_5M`, `_100175_6M`, `_100178_6M`, `_100180_1M`, `_100184_5M`, `_166_2_7M`, `_1707_5M`, `_639_2_7M`, `_846_5M` |
| markgrafii | **1C … 7C** | CM128012.1 … CM128018.1 | 17 条：`scaffold_8` … `scaffold_24` |
| umbellulata | **1U … 7U** | CM191168.1 … CM191174.1 | 243 条：`Super_scaffold_*` 与 `ptg*`（如 `Super_scaffold_20_4` 9.57 Mb） |
| uniaristata | **1N … 7N** | CM127992.1 … CM127998.1 | 14 条：`Super-Scaffold_100184`, `_100228`, `_100233`, `_100465_1`, `_144_2`, `_1_2`, `_205`, `_237_2`, `_2458_2`, `_255_2`, `_262`, `_4894_2`, `_4894_3`, `_57` |

⚠ **NCBI FASTA 头的第一 token 是 GenBank/WGS 登录号**（实测 `efetch`：`>CM127985.1 Aegilops comosa isolate IPK-AE783 chromosome 1, whole genome shotgun sequence`；scaffold 头为 `>JBHEGE020000008.1 ... Super-Scaffold_100133_4M ...`），与 GFF 的 seqid（`1M` 等）**不一致**，必须用 `*_assembly_report.txt` 的 `Sequence-Name ↔ GenBank-Accn` 做改名（§6.2 给出映射规则）。

### 4.3 版本/历史说明与“新组装”判定

- **comosa 有 2 代提交**：旧 `GCA_052815735.1`（PRJNA1154588、WGS JBHEGE01、2025-09-24，`Expected final version: No`）→ 现行 `GCA_052815735.2`（PRJNA1506336、JBHEGE02、2026-09-13，`Yes`）。**论文 Data availability 写的是 PRJNA1506336 = v2**；上线用 v2。v1 目录仍可下载但已被取代。
- 与平台既有材料不同：comosa 平台现有 `Aegilop_comosa_PI551049`（M，无注释）；umbellulata 现有 `…_PI554389`（无注释）与 `…_TA1851`（有注释）——**4 个新组装都是新登录号，属于新增并存，不覆盖现有条目**（平台侧实证见 `PLATFORM_BASELINE.md` §2.2）。
- markgrafii / uniaristata 在 NCBI 与平台均为首次（论文 p2：“With the first assemblies of Ae. markgrafii and Ae. uniaristata, this work completes the availability of high-quality genome assemblies of all diploid Aegilops species”）。
- **SRA 原始数据**：每个 BioProject 40 条 SRA 记录（HiFi/Hi-C/IsoSeq/RNAseq 全套，与 Data availability 一致）。

---

## 5. Zenodo 注释文件实测（4 物种）

### 5.1 GFF3 结构

- 所有 4 个 `*_genes_HC_LC.gff3.gz` 均以 `##gff-version 3` 开头；feature 类型**只有 gene / mRNA / exon / CDS 四类**（无 UTR、无 ncRNA）；基因间用 `###` 分隔；**每个 gene 恰好 1 个 mRNA（无可变剪接）**；exon 数 = CDS 数。
- 属性格式：`ID=...;Name=EVM prediction ...`（gene）；mRNA 有 `ID=...;Parent=<gene>;Name=...`；exon/CDS 有 `ID=...;Parent=<mRNA>`，CDS 第 8 列为 phase。
- 示例（comosa）：
  ```
  1M  EVM  gene  4210451  4210996  .  -  .  ID=evm.TU.1M.1;Name=EVM prediction 1M.1
  1M  EVM  mRNA  4210451  4210996  .  -  .  ID=evm.model.1M.1;Parent=evm.TU.1M.1;Name=EVM prediction 1M.1
  1M  EVM  exon  4210451  4210996  .  -  .  ID=evm.model.1M.1.exon1;Parent=evm.model.1M.1
  1M  EVM  CDS   4210451  4210996  .  -  0  ID=cds.evm.model.1M.1;Parent=evm.model.1M.1
  ```

### 5.2 计数实测（与论文 Table 3 / Table S12 对照）

| 物种 | gene = mRNA | HC（`evm.TU`） | LC（`gene.model.*`） | exon = CDS | seqid 数（7 染色体 + 未定位） | ChrUn 上的基因 |
|---|---|---|---|---|---|---|
| Ae. comosa | **51,203** | 37,622 | 13,581 | 180,142 | 15（7+8） | 38（HC 27 / LC 11） |
| Ae. markgrafii | **47,246** | 34,133 | 13,113 | 172,497 | 14（7+7） | 53（HC 35 / LC 18） |
| Ae. umbellulata | **49,677** | 35,799 | 13,878 | 177,553 | 188（7+181） | **1,103**（HC 666 / LC 437） |
| Ae. uniaristata | **50,416** | 35,816 | 14,600 | 176,014 | 15（7+8） | 66（HC 49 / LC 17） |

- 每染色体 HC/LC 实测与论文 **Additional file 1 Table S12** 一致（comosa 1M 4,915/1,807 … uniaristata 7N 5,211/2,496 等逐格吻合）；唯一差异：uniaristata ChrUn/合计比 S12 多 1 个 HC（GFF 35,816 vs S12 35,815），与 Table 3 的 35,816 一致。
- 论文 p11 称 “97.8–99.9% 的基因位于 7 条染色体”，实测：comosa 99.93%、markgrafii 99.89%、umbellulata 97.78%、uniaristata 99.87% ✅（与 Table 1/S7 同量级）。

### 5.3 ⚠ ID 命名三个家族（决定归一化工作量）

| 家族 | 计数（comosa/markgrafii/umbellulata/uniaristata） | gene ID | mRNA ID | 以 `.数字` 结尾？ |
|---|---|---|---|---|
| HC（EVM） | 37,622 / 34,133 / 35,799 / 35,816 | `evm.TU.<seqid>.<n>` | `evm.model.<seqid>.<n>` | ✅ `.n` |
| LC（EVM 输出） | 930 / 812 / 839 / 925 | `gene.model.evm.model.<seqid>.<n>` | `model.model.evm.model.<seqid>.<n>` | ✅ `.n` |
| **LC（TAMA/GeneMarkS-T，`STRG`）** | **12,651 / 12,301 / 13,039 / 13,675** | `gene.model.STRG.<n>.<m>.p<k>` | `model.model.STRG.<n>.<m>.p<k>`（k=1…10，p1 为主） | ❌ 以 `.p<k>` 结尾 |

**合计 51,666 个 mRNA ID 需要按平台 SOP §1.1 追加 `.数字` 后缀**（最短路径：`\.p(\d+)$` → `.\1` 或直接追加 `.1`，并**同步改写 ID=/Parent=/Derives_from=** 以及蛋白 FASTA 头、gffread 输出名）。其余 3 类家族已满足规则。
另注意：**gene ID 与 mRNA ID 基名不同**（`evm.TU.*` vs `evm.model.*`），若下游需要 gene↔mRNA 映射，用 `Parent` 属性（1 gene : 1 mRNA，无歧义）。

### 5.4 seqid 与坐标兼容性实测（关键风险检查）

| 检查 | comosa | markgrafii | umbellulata | uniaristata |
|---|---|---|---|---|
| GFF 全部 seqid 都能在 NCBI assembly_report 找到 | ✅ 0 缺失 | ✅ 0 缺失 | ✅ 0 缺失 | ✅ 0 缺失 |
| GFF 最大坐标 ≤ NCBI 序列长度 | ✅ 全部 15 条 | ✅ 全部 14 条 | ✅ 全部 188 条 | ✅ 全部 15 条 |
| GFF 最大坐标与 NCBI 染色体长度差（最小值/最大值） | 5,250 / 2,797,925 bp | 18,782 / 377,359 bp | 618 / 489,910 bp | 102,328 / 1,242,508 bp |
| 未定位 scaffold 覆盖 | GFF 8/10（2 条无基因） | GFF 7/17 | GFF 181/243 | GFF 8/14 |
| GFF 未定位 scaffold 上最大坐标合计 vs NCBI 未定位总长 | 2.32 vs 2.64 Mb | 4.93 vs 7.33 Mb | 25.35 vs 32.57 Mb | 5.61 vs 9.38 Mb |

**解读**：论文 Table S14 的“Size (bp)”列与 GFF 最大基因坐标高度吻合（多数完全相同），说明该列很可能是**按注释最大坐标统计**而非组装真实长度；NCBI 每条染色体比 GFF 最大坐标长 0.6 kb–2.8 Mb（基因区之外）。**结论：以 NCBI GCA 作 FASTA 源、Zenodo GFF 作注释，坐标系统兼容**（且 §5.6 的 16 个位点翻译验证全部通过）。

### 5.5 蛋白 FASTA 实测

| 物种 | 序列数 | 头格式 | 长度范围（aa） | 字符集/终止符 | 与 GFF mRNA ID 交集 |
|---|---|---|---|---|---|
| comosa | 51,203 | `>evm.model.1M.1 gene=EVM prediction 1M.1` | 50–5,065 | 20 种氨基酸 + `X`(34 条) + 末端 `.`（43,062 条；另有 6,573 条含**内部** `.`） | 51,203/51,203 |
| markgrafii | 47,246 | 同（`model.model.*` 家族同规则） | 50–5,356 | 20 种氨基酸 + `X` 极少 + 末端 `.`（44,918 条；内部 `.` 449 条） | 47,246/47,246 |
| **umbellulata** | 49,677 | 同上 | **49–5,354** | **末端 `*`（47,247 条）**，`X` 1 条 | 49,677/49,677 |
| uniaristata | 50,416 | 同上 | 50–5,209 | 20 种氨基酸 + 末端 `.`（47,703 条；内部 `.` 509 条） | 50,416/50,416 |

- 是**蛋白**序列（不是 CDS；字符为氨基酸），1 条/基因（LC 也在内）。
- **终止符/内部终止符（按序列统计）：**comosa 的蛋白 FASTA 质量明显差于另外 3 个物种——
  | 物种 | 末端 `.`/`*` | 无终止符 | **含内部终止符（帧移模型）** |
  |---|---|---|---|
  | comosa | 43,062（`.`） | 8,141 | **6,573**（HC 4,657 / LC-EVM 557 / STRG 1,359；单条最多 233 个） |
  | markgrafii | 44,918（`.`） | 2,328 | 449（LC-EVM 447 / STRG 2） |
  | umbellulata | 47,247（`*`） | 2,430 | 0 |
  | uniaristata | 47,703（`.`） | 2,713 | 509（LC-EVM） |
- **内部终止符是注释本身的帧移/不完整模型，不是我们提取错误**：以 comosa `evm.model.2M.3642`（CDS 总长 mod3=1）为例，我们从 NCBI 序列 + Zenodo GFF 跑 `gffread`，得到与 Zenodo 蛋白**逐字符相同**的 4,749 aa 序列（含 233 个内部 `.`），gffread 同时告警 `Warning: In-frame STOP found`。
- ⚠ 平台清洗必须处理**内部** `.`/`*`（不能只去行尾）；否则蛋白 BLAST 库可能建库失败/告警。建议统一替换为 `X` 或删除后再 `makeblastdb`，并保留原文件。
- ⚠ 平台 `check_genome_files.py` 的清洗行为需确认（SOP 只说“清理 pep 里的 `.`”，未说明是否只去尾）；**umbellulata 的 `*` 与 comosa 的内部 `.` 都必须额外处理**（见上一条），建议在归一化脚本中统一做。

### 5.6 CDS 必须自行生成 + 端到端验证（本报告最关键的可行性证据）

**结论：Zenodo 无 CDS；`gffread` 从「NCBI FASTA + Zenodo GFF」直接生成 CDS/PEP 可行，且产物与 Zenodo 蛋白一致。**

验证方法（可复用）：从 NCBI `nuccore` 用 `efetch ... &seq_start=&seq_stop=` 取基因区段 → 按 SeqID 建 mini-genome、GFF 坐标平移 → `gffread -E` → 与 Zenodo 蛋白比对。

| 物种 | 验证位点（gene → 染色体） | gffread 产物 vs Zenodo 蛋白 |
|---|---|---|
| comosa | evm.TU.1M.1、gene.model.STRG.3763.1.p1、evm.TU.7M.1、evm.TU.7M.3118 | **4/4 MATCH**（181/198/363/234 aa） |
| markgrafii | gene.model.STRG.315.1.p1、evm.TU.1C.2229、evm.TU.7C.1、evm.TU.7C.1923 | **4/4 MATCH**（212/743/859/132 aa） |
| umbellulata | gene.model.STRG.2.1.p1、gene.model.STRG.3219.1.p1、evm.TU.7U.1、evm.TU.7U.3071 | **4/4 MATCH**（235/142/559/74 aa） |
| uniaristata | evm.TU.1N.1、gene.model.STRG.3176.1.p1、evm.TU.7N.1、gene.model.STRG.54187.1.p1 | **4/4 MATCH**（119/258/338/142 aa） |
| comosa（未定位 scaffold 全量） | Super-Scaffold_100133_4M 上唯一基因 `model.model.STRG.53733.1.p1` | **MATCH**（437 aa；gffread pep 与 Zenodo 逐残基相同，仅 Zenodo 末尾多 `.`） |

- 本地测试 `gffread 0.12.1`（服务器 SOP 用 0.12.9，语法相同）；命令：`gffread -E <gff3> -g <genome.fa> -x cds.fa -y pep.fa`。
- 建议上线时把**全量** `gffread` 输出的 pep 与 Zenodo 蛋白做一次批量比对（条数 + 抽样/哈希），作为归一化验收断言；本报告 17 个位点已覆盖 4 物种 HC/LC/STRG 三家族与染色体两端。

### 5.7 可译性/完整性风险（记录，不阻塞）

- CDS 总长不是 3 的倍数的 mRNA：**626 / 577 / 637 / 668**（comosa/markgrafii/umbellulata/uniaristata），按家族：HC 78/86/105/106；LC-EVM 548/491/532/562；**STRG 家族 0**。推测为基因模型边界不完整的 LC-EVM 模型（与 §5.5 中无终止符的序列数同量级）。
- 没有 CDS 的 mRNA：**0**（每个 mRNA 都有 CDS 记录）。
- gffread 会为含有内部终止符的模型产生 `Warning: In-frame STOP found` 告警但仍输出序列（已实测与 Zenodo 蛋白一致），**不要剔除这些模型**（否则基因数与论文差 6.5k+）；在 pep 清洗阶段把内部 `.`/`*` 统一替换为 `X` 即可满足平台/BLAST 要求。
- GFF 不含 UTR/ncRNA；若 JBrowse 需要 UTR 轨道，只能以现有 exon/CDS 表达（论文本来就没做 UTR）。

---

## 6. 上线输入四件套：来源 → 缺口 → 补齐 → 工作量/风险

> 平台侧规范来自 `~/.agents/skills/lab-server/references/wheatomics-new-genome-sop.md` §1（2026-10-23 固化）与 `finish_genome_integration.sh`。硬性要求：`.fa`/`.gff3` 的 seqid 都以 `Chr` 开头；**GFF 的 mRNA `ID=` 必须以 `.数字` 结尾**；`.cds/.pep` 的序列 ID 以 `.数字` 结尾、pep 序列行不能含 `.`；四个文件都不能缺。

### 6.1 四件套来源表

| 输入 | 来源（推荐） | 现状 | 缺什么 / 要做什么 | 工作量 | 风险 |
|---|---|---|---|---|---|
| **`.fa`** | NCBI GCA `*_genomic.fna.gz`（4 个，共约 4.7 GB gz；或 `datasets download genome accession`） | ✅ 公开可下，md5 已有（§4.1） | ① 下载 + md5 校验；② 用 `*_assembly_report.txt` 把 GenBank 登录号头改为 `Chr1M..Chr7M`（`seqid`）与 `ChrUn_<原名>`；③ 平台 Step 1 会自动给染色体头加 `_<MYTAG>` 后缀，`ChrUn_*` 不加（SOP §1.2-6） | 下载 4×1.0–1.3 GB（视带宽 ~1–3 h）；改名脚本 ~10 min；`samtools faidx` 秒级 | 低。注意不要丢掉未定位 scaffold（否则丢 38/53/1103/66 个基因） |
| **`.gff3`** | Zenodo `*_genes_HC_LC.gff3.gz`（**不要用** markgrafii 的独立 LC 文件） | ✅ 有；HC+LC 合计与论文 Table 3 一致 | ① seqid 改名（§6.2）；② **51,666 个 STRG mRNA ID 追加 `.数字`**（同步 ID/Parent/Derives_from）；③ 保留全部记录（含 `###`），按平台 `normalize_gff2.py` 思路两遍流式处理并校验 mRNA ID 唯一 | 写一次性归一化脚本 + 4 物种跑批：**0.5–1 天**（含校验） | 中。ID 改写若漏同步 `Parent` 会导致 gffread 生成失败 / 基因数与预期不符 → 用 `gffread` 产物条数 = 51,203/47,246/49,677/50,416 作为断言 |
| **`.cds`** | **必须由 `gffread` 生成**（`gffread -E <归一化gff3> -g <归一化fa> -x <cds> -y <pep>`） | ❌ Zenodo 没有 | 归一化完成后生成 | 4 物种全量 ~10–30 min（含 gffread 告警） | 低-中。§5.6 已验证 17 位点一致；建议全量比对 pep 与 Zenodo 蛋白（§6.4 验收） |
| **`.pep`** | 首选同一 `gffread -y` 产物（与 CDS 严格配套）；Zenodo 蛋白 FASTA 作为**交叉验证**（不建议直接当输入，因为 ID 需改、终止符需清） | ✅ 有（51,203/47,246/49,677/50,416 条） | 若用 Zenodo 版：清理 `.`/`*` + 改 ID；若用 gffread 版：已天然匹配归一化 ID，但仍需清洗内部/末端终止符 | 含在 gffread 步骤 | 中低。**umbellulata 用 `*`、3 物种用 `.`；comosa 有 6,573 条含内部终止符（帧移模型）** → 必须统一清理全部 `.`/`*`（`sed`/python 层过滤），否则蛋白 BLAST 库可能建库失败 |

### 6.2 归一化映射规则（可直接给实现同学）

**A. seqid 映射（4 物种一致规则）**

| 原 seqid（GFF） | 归一化后 | 备注 |
|---|---|---|
| `1M`…`7M`（comosa） | `Chr1M`…`Chr7M` | NCBI FASTA 头对应 `CM127985.x`…`CM127991.1` |
| `1C`…`7C`（markgrafii） | `Chr1C`…`Chr7C` | `CM128012~018` |
| `1U`…`7U`（umbellulata） | `Chr1U`…`Chr7U` | `CM191168~174` |
| `1N`…`7N`（uniaristata） | `Chr1N`…`Chr7N` | `CM127992~998` |
| `Super-Scaffold_*` / `scaffold_*` / `Super_scaffold_*` / `ptg*` | `ChrUn_<原 seqid>` | 保留原名做后缀，避免多物种撞名；**不要丢弃** |
| NCBI FASTA 的 `CM…` / `JBDZUH…` 头 | 用 assembly_report 的 `Sequence-Name ↔ GenBank-Accn` 一一替换为上述 `Chr*` / `ChrUn_*` | 4 份 assembly_report 已实测可解析（每行 10 列，第 1 列 Sequence-Name、第 5 列 GenBank-Accn） |

**B. mRNA/gene ID 归一化（51,666 条）**

- 规则：对 `model.model.STRG.<n>.<m>.p<k>`（以及对应 gene `gene.model.STRG.<n>.<m>.p<k>`）→ 追加 `.1`（或把 `\.p(\d+)$` 替换为 `.\1`），并同步：GFF 的 `ID=`、`Parent=`、`Derives_from=`（若有），以及蛋白 FASTA 头、gffread 生成的 cds/pep 头。
- 其余家族（`evm.model.*`、`model.model.evm.model.*`）已满足 `.数字` 结尾，不需要改。
- 注意：gene ID 与 mRNA ID 基名不同（`evm.TU.*` vs `evm.model.*`）属于作者 EVM 输出惯例；若平台 Genefunc 表以 mRNA ID 为主键则无影响。

**C. 序列文件字符清理**

- pep：**去掉全部** `*` 与 `.`（含内部；建议替换为 `X` 以保留长度），保留内部 `X`；4 物种统一。`gffread` 产物与 Zenodo 蛋白都会带 `.`（comosa 内部终止符 6,573 条），必须处理。
- `.fa`：保留 `ChrUn_*` 全部序列；建议用 `samtools faidx` 生成 `.fai`（平台 PrimerServer2 需要 genome/cds 的 `.fai`，由收尾脚本补）。

### 6.3 工作量与关键路径估计

| 步骤 | 估时 | 依赖 |
|---|---|---|
| 下载 4 个 NCBI FASTA（~4.7 GB）+ md5 校验 | 1–3 h（视带宽） | 无 |
| 写/调 seqid 与 mRNA ID 归一化脚本（4 物种跑批 + 校验） | 0.5–1 天 | GFF 下载（已完成探针） |
| gffread 生成 cds/pep（4 物种） | 10–30 min | 归一化后的 fa/gff |
| `check_genome_files.py` 闸门 + 修问题 | 1–2 h | 上两步 |
| 与 Zenodo 蛋白全量/抽样比对（验收断言） | 1 h | gffread 产物 |
| **合计（数据准备）** | **约 2–3 人日**（含下载等待） | — |

> 平台流水线本身 ~1–2 h/物种（EggNOG/miniprot 占大头，参见 SOP 的 PT 参考耗时），不属于本任务。

### 6.4 建议的归一化验收断言（可直接写进上线计划）

1. `*.gff3` 第 1 列 100% 以 `Chr` 开头（0 例外）；
2. mRNA `ID=` 100% 以 `.数字` 结尾（0 例外；改写 51,666 条后）；
3. 每个物种 `grep -c $'\tmRNA\t'` = **51,203 / 47,246 / 49,677 / 50,416**；
4. `gffread -x/-y` 产出的 cds/pep 条数与上面一致；**抽样 ≥20 条**与 Zenodo 蛋白一致（本报告 17/17 已通过）；若做全量：perl/python 汇总 md5 或序列长度分布对比，差异应只来自末端终止符；
5. pep 文件中 `*`、`.` 均不出现；
6. `.fa` 序列数 = 17 / 24 / 250 / 21（含 ChrUn；与 NCBI 一致），且长度和 = 4,407,741,597 / 3,577,170,360 / 4,268,089,219 / 4,475,943,907。

---

## 7. TE / JBrowse 轨道可行性

### 7.1 4 个 TE GFF 实测（全部 md5 通过）

| 物种 | 文件大小（B） | feature 数 | seqid 数 | seqid 命名 | 与基因 GFF/NCBI 一致性 | 处理 |
|---|---|---|---|---|---|---|
| comosa | 75,641,029 | **3,398,055** | 17 | 裸数字 `1`…`7` + 数字 token（`100133`, `100148`, `100175`, `100178`, `100180`, `100184`, `166`, `639`, `1707`, `846`） | ❌ 与基因 GFF（`1M`/`Super-Scaffold_*`）不同；**但 token 与 10 条未定位 scaffold 一一对应** | 需改名：`N`→`ChrNM`；`<token>`→`ChrUn_Super-Scaffold_<token>_*`（用 assembly_report 消歧） |
| markgrafii | 62,222,449 | **2,786,519** | 22 | `1C`…`7C` + `scaffold_8`…`scaffold_24` | ✅ 与基因 GFF 同命名，22/22 全部在 NCBI assembly_report 中 | 只做标准 `Chr` 前缀改名 |
| umbellulata | 73,292,397 | **3,264,607** | 248 | `1U`…`7U` + `S_S_*`（Super_scaffold 缩写）+ `ptg*` | ⚠ `S_S_` 需展开为 `Super_scaffold_`；展开后 **247/248** 在 NCBI（`Super_scaffold_73_2` 不在，仅 1 条 TE 特征）；3 条 NCBI scaffold 无 TE | 展开 + 标准改名；1 条哑 seqid 可丢/单独记录 |
| uniaristata | 77,947,960 | **3,466,840** | 21 | `1N`…`7N` + `S_S_*`（Super-Scaffold 缩写） | ✅ 展开 `S_S_`→`Super-Scaffold_` 后 **21/21** 全部在 NCBI（14/14 未定位 scaffold 覆盖） | 展开 + 标准改名 |

- 头部均为 EDTA v2.2.1 标准 GFF3：`##gff-version 3` + EDTA 注释块（`##date`、列说明），可直接被 JBrowse 1.12.3 的 GFF3 轨道读取（需 seqid 与 refSeqs 一致、按坐标排序）。
- feature 的 `type`（第 3 列）是 **Sequence Ontology 风格**，不是 GFF2 similarity 风格；markgrafii 全量统计的 20 类：`Gypsy_LTR_retrotransposon`(671,893)、`CACTA_TIR_transposon`(343,242)、`LTR_retrotransposon`(334,100)、`Copia_LTR_retrotransposon`(246,125)、`helitron`(194,135)、`long_terminal_repeat`(171,204)、`target_site_duplication`(171,102)、`Tc1_Mariner_TIR_transposon`(170,934)、`PIF_Harbinger_TIR_transposon`(107,572)、`Mutator_TIR_transposon`(88,387)、`repeat_region`(85,602)、`SINE_element`(78,027)、`repeat_fragment`(67,050)、`hAT_TIR_transposon`(29,313)、`L1_LINE_retrotransposon`(21,170)、`DNA_transposon`(2,979)、`rRNA_gene`(2,092)、`Endogenous_Retrovirus_LTR_retrotransposon`(929)、`Ngaro_YR_retrotransposon`(586)、`Kolobok_TIR_transposon`(77)。
- 属性含 `ID/Name/classification/sequence_ontology/identity/method`（homology/structural），可直接用于 JBrowse 弹窗。

### 7.2 JBrowse 1.12.3 轨道结论

- **可行**：4 个 TE GFF 均为合法 GFF3，seqid 可由 assembly_report 确定性映射到 NCBI `Chr*`/`ChrUn_*`（comosa 需 token 映射表，其余为字符串替换）。
- **前提**：归一化时把 TE GFF 的 seqid 与 FASTA/GFF 用**同一套改名规则**；否则轨道静默空显示（最隐蔽的坑：comosa 的裸数字会被命名成 `Chr1` 等不在 refSeqs 的名字）。
- 建议：TE 轨道按 `type`/`classification` 分层（LTR/Gypsy、LTR/Copia、DNA/CACTA 等 top 类别 + 其余），文件 60–78 MB gz → 解压 2.8–3.5 M 行，JBrowse 建议用 BED/GFF sorted 索引（平台既有做法）。
- **不可得**：着丝粒坐标（论文只用 Cereba/Quinta 密度图，Fig 2B/p10，没有坐标文件）、45S rDNA 具体位点、UTR、ncRNA——不要在计划里承诺这些轨道。

---

## 8. 许可与引用

| 对象 | 许可 | 允许镜像/展示？ | 证据 |
|---|---|---|---|
| 论文 | **CC-BY-4.0**（Crossref license；BMC “Open Access”）；PDF 标 © Crown 2026（AAFC 皇家版权，按 CC-BY 发布） | ✅ 允许再分发/展示，需署名（作者、标题、DOI、CC-BY 链接）与“是否修改”的说明 | Crossref `license[0].URL`；BMC HTML；PDF p17 Open Access |
| Zenodo 数据 | **CC-BY-4.0** | ✅ 允许镜像标注/GFF/TE 数据，需署名 + 引用 DOI | Zenodo API `metadata.license.id=cc-by-4.0`；README “License” 段 |
| NCBI 组装 | NCBI 数据使用政策（公共领域/无限制，需引用 GCA + BioProject） | ✅ | NCBI Assembly 页面 / FTP README |

**推荐引用文本（网站 JBrowse 卡片/数据来源页可直接用）**

- 论文：
  > Khadka B, Edwards T, Lévesque-Lemay M, Ens J, Chawla HS, Zheng C, You FM, Pozniak CJ, Cloutier S. Chromosome-level reference genome assemblies and annotation of four diploid Aegilops. *BMC Plant Biology*. 2026. doi:10.1186/s12870-026-10046-2（Article in press / published 2026-11-07）
- 注释数据：
  > Khadka B, Edwards T, Lévesque-Lemay M, Ens J, Chawla HS, Zheng C, You FM, Pozniak CJ, Cloutier S. Gene and repeat annotations for reference genome assemblies of four diploid Aegilops species (Ae. comosa, Ae. markgrafii, Ae. umbellulata, Ae. uniaristata). Zenodo. 2026. doi:10.5281/zenodo.22681907（CC-BY-4.0）
- 组装：
  > Genome assemblies: NCBI GenBank GCA_052815735.2 (Ae. comosa IPK-AE783, PRJNA1506336); GCA_052815875.1 (Ae. markgrafii EKC105_RL5723, PRJNA1174795); GCA_060308565.1 (Ae. umbellulata IPK-AE740, PRJNA1114735); GCA_052815765.1 (Ae. uniaristata IPK-AE680, PRJNA1154594).

建议在 JBrowse/基因组详情页同时展示“论文 DOI + Zenodo DOI + GCA + 许可 CC-BY-4.0”，既满足署名，也方便用户下载原始数据。

---

## 9. 不确定项与风险登记

| ID | 事项 | 现状/证据 | 影响 | 建议动作 |
|---|---|---|---|---|
| R1 | 论文是 **Article in Press**（2026-11-07 early access，会被 VOR 替换） | PDF p1/BMC 横幅 | 个别表格数字可能微调；不影响数据文件 | 引用加 “in press”；VOR 出来后核对 Table 1/3 数字 |
| R2 | Zenodo `Ae.markgrafii_genes_LC.gff3.gz` 内容=HC（打包 bug） | §3.4 实测 diff 空 | 若误用会少 13,113 个 LC 基因 | 只用 `*_genes_HC_LC.gff3.gz`；向作者反馈 |
| R3 | README 与实物文件名/数字不一致（4 处） | §3.5 | 照 README 写脚本/引用会错 | 以 API 清单 + GFF 实测为准 |
| R4 | 论文自身数字不一致：umbellulata 组装 4.40 Gb（Table 1）vs 4.24/4.27（S6/NCBI）；comosa chr7 688.03（S14）vs 690.83（NCBI）；Table 3 vs Table S12/README 基因数差 1–2 | §2.1/§2.2 | 网页元数据若照抄会与 NCBI/BLAST 对不上 | **组装大小/seq 数一律用 NCBI**；基因数用 GFF/Table 3（51,203/47,246/49,677/50,416） |
| R5 | 3 个组装标 “Expected final version: No”（只有 comosa v2 是 Yes） | NCBI assembly_report | 作者未来可能发 v2，导致序列/坐标变化 | 记录版本号与 md5；上游更新时按新 md5 重跑归一化 |
| R6 | 未做**全量** gffread vs Zenodo pep 比对（已抽检 17 位点全 MATCH） | §5.6 | 个别模型可能有差异 | 上线验收按 §6.4 第 4 条全量/大样本比对 |
| R7 | 论文 Table S14 的染色体 “Size” 与 NCBI 不一致，且与 GFF 最大基因坐标高度重合 | §5.4 | 解释：该列可能是按注释坐标生成，不是组装长度 | 引用组装长度以 NCBI 为准；不引用 S14 的 Size 列 |
| R8 | 平台 pep 清洗只处理 `.`，umbellulata 用 `*` | §5.5/SOP 注意项 | 残留 `*` 可能影响 BLAST/展示 | 归一化时统一去除行尾 `*`/`.` |
| R9 | umbellulata TE 的 `Super_scaffold_73_2` 不在 NCBI 提交里（1 条 TE 特征） | §7.1 | 该 1 条特征无法显示 | 丢弃并记录；或向作者确认 |
| R10 | 未在 ENA 镜像/Nucleotide 层逐条核对 | 本次只查 NCBI Datasets/FTP；ENA API assembly 查询为空（INSDC 镜像通常滞后） | 低 | 不需要；下载以 NCBI FTP md5 为准 |
| R11 | 未联系作者确认（Zenodo 元数据未挂论文 DOI、无 version） | Zenodo API `related_identifiers=null`、单版本 | 低 | 可在网站引用页手工关联论文 DOI；无需等作者 |
| R12 | 无 CDS/UTR/ncRNA/着丝粒/45S rDNA 坐标文件 | §5.1/§7.2 | JBrowse 不能承诺这些轨道；CDS 需自建 | 计划中明确“CDS 由 gffread 生成”，不承诺 UTR/着丝粒轨道 |
| R13 | 蛋白 FASTA 中有 `X`（comosa 34 条、umbellulata 1 条）与不完整模型 | §5.5 | 不影响 BLAST/CDS 主流程 | 保留（与 Zenodo/论文一致） |
| R14 | **comosa 蛋白有 6,573 条含内部终止符（帧移注释；单条最多 233 个）**，其余 3 物种 0–509 条 | §5.5/§5.7；已实测 gffread 复现 1 例与 Zenodo 完全一致 | 若只清行尾 `.`/`*`，蛋白 BLAST 建库可能失败或出现无效字符 | pep 清洗时替换全部 `.`/`*`（建议→`X`）；保留基因数不变；记录该质量问题 |

---

## 10. 附录：证据 URL、命令与工作区文件

### 10.1 关键 URL

| 用途 | URL |
|---|---|
| Crossref 元数据 | https://api.crossref.org/works/10.1186/s12870-026-10046-2 |
| 论文 HTML（BMC/Springer） | https://bmcplantbiol.biomedcentral.com/articles/10.1186/s12870-026-10046-2 ；https://link.springer.com/article/10.1186/s12870-026-10046-2 |
| 论文 PDF（可用直链） | https://link.springer.com/content/pdf/10.1186/s12870-026-10046-2_reference.pdf |
| 补充文件 | https://static-content.springer.com/esm/art%3A10.1186%2Fs12870-026-10046-2/MediaObjects/12870_2026_10046_MOESM{1,2,3}_ESM.{docx,xlsx,docx} |
| Zenodo record API | https://zenodo.org/api/records/22681907 |
| Zenodo 文件下载 | https://zenodo.org/api/records/22681907/files/<文件名>/content |
| Zenodo DOI | https://doi.org/10.5281/zenodo.22681907（concept 10.5281/zenodo.22680410） |
| NCBI Datasets 报告 | https://api.ncbi.nlm.nih.gov/datasets/v2alpha/genome/accession/<GCA>/dataset_report |
| NCBI 下载摘要 | https://api.ncbi.nlm.nih.gov/datasets/v2alpha/genome/accession/<GCA>/download_summary |
| NCBI FASTA FTP | https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/052/815/735/GCA_052815735.2_ASM5281573v2/ 等（见 §4.1） |
| NCBI Assembly 页面 | https://www.ncbi.nlm.nih.gov/assembly/GCA_052815735.2 等 |
| BioProject | https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1506336 等 |

### 10.2 复现实测命令（节选）

```bash
# 1) Zenodo 清单 + md5
curl -s https://zenodo.org/api/records/22681907 | python3 -c "import json,sys;d=json.load(sys.stdin);[print(f['key'],f['size'],f['checksum']) for f in d['files']]"
md5 -q Ae.comosa_genes_HC_LC.gff3.gz    # 与 API checksum 比对

# 2) GFF 计数 / ID 家族
gzip -dc Ae.comosa_genes_HC_LC.gff3.gz | awk -F'\t' '$3=="gene"' | wc -l                     # 51,203
gzip -dc Ae.comosa_genes_HC_LC.gff3.gz | awk -F'\t' '$3=="gene"{print $9}' | grep -c 'ID=evm.TU'      # HC 37,622
gzip -dc Ae.comosa_genes_HC_LC.gff3.gz | awk -F'\t' '$3=="mRNA"{print $9}' | grep -c '\.p[0-9]*;'     # STRG 家族（需改写）

# 3) FASTA 类型/终止符
gzip -dc Ae.umbellulata_genes_HC_LC.fasta.gz | grep -v '^>' | tr -d '\n' | fold -w1 | sort | uniq -c   # 见 '*' 
gzip -dc Ae.comosa_genes_HC_LC.fasta.gz | grep -c '^>'                                       # 51,203（=gene 数）

# 4) NCBI 区域回取 + gffread 验证（脚本见 docs/plans/.../zenodo_probe 思路，本文 §5.6）
curl -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&id=CM127985.1&rettype=fasta&retmode=text&seq_start=4210451&seq_stop=4210996"
gffread -E mini.gff3 -g mini.fa -x cds.fa -y pep.fa

# 5) TE seqid 核对（以 comosa 为例，下载后）
gzip -dc Ae.comosa.EDTA.TEanno.gff3.gz | grep -v '^#' | awk -F'\t' '{print $1}' | sort | uniq -c
```

### 10.3 本任务写出的文件

| 文件 | 说明 |
|---|---|
| `docs/plans/aegilops4_2026-11/PAPER_DATA.md` | 本报告 |
| `docs/plans/aegilops4_2026-11/khadka_2026_four_diploid_Aegilops_BMCPlantBiol.pdf` | 论文 PDF（24 页，6,112,465 B，md5 `09c2b1e4963706a29e7b5a19f36c6489`） |
| `docs/plans/aegilops4_2026-11/zenodo_probe/` | README + 4 物种 HC_LC gff3/fasta + comosa HC/LC + markgrafii HC/LC + markgrafii TE + `paper_supp/`（Additional file 1/2/3） |

（未改动任何仓库源码、未 git commit、未访问生产服务器。）
