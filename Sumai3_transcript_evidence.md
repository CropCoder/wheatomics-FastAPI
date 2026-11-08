# Sumai 3（PRJNA1247523）转录水平证据清单

> 查询日期：2026-10-26 ｜ 来源：NCBI SRA / ENA / BioSample / BioProject
> 项目：BioProject **PRJNA1247523**（Study **SRP696590**；Triticum aestivum cultivar Sumai 3 genome sequencing）
> Run Selector：https://www.ncbi.nlm.nih.gov/Traces/study/?acc=PRJNA1247523
> 说明：本文只统计“文章公布的 project 号”下公开可见的数据；作者注释（GFF）不在此项目中。

## 1. 项目总览（41 个 SRA runs）

| 类型 | runs | 平台 | 说明 |
|---|---|---|---|
| WGS（基因组） | 21 | PacBio Sequel | 21 个 HiFi cell，组装修建用 |
| Hi-C | 1 | Illumina HiSeq 4000 | 样本 SAMN57648996；ENA 元数据显示 0 reads/0 bases，仅作 scaffolding 辅助 |
| **转录组（RNA-Seq）** | **19** | **PacBio Sequel ×1 + Illumina NovaSeq X ×18** | 即 IsoSeq + 18 个 RNA-seq 样本 |

## 2. IsoSeq（全长转录本，1 个 run）

| 项 | 内容 |
|---|---|
| Run / Experiment | **SRR38604212** / SRX33410438 |
| Library | `m54336U_220703_090327`，标题 `IsoSeq_Sumai3` |
| 平台/建库 | PacBio Sequel；LIBRARY_SELECTION=PolyA，SINGLE |
| 样本 | 挂在基因组 BioSample **SAMN47817036**（`Sumai3_fgl_pseudomolecule_2025`，tissue=Leaf, dev_stage=Tillering, 2021-06, China/Jiangsu） |
| 数据量（SRA/ENA） | **182,402 reads / 324,352,326 bases（≈324 Mb）**；平均 1,778 bp，最长 8,306 bp，N50 1,932 bp |
| ENA 文件名与真实内容 | ENA 的 FASTQ 名为 `SRR38604212_subreads.fastq.gz`（PacBio run 的通用命名），但**内容是 IsoSeq FLNC/CCS 全长转录本**：headers `@SRR38604212.N transcript_N/1`；`run_alias = Sumai3_flnc_polished.hq.renamed.fasta.gz`（FLNC polished HQ 改名后的文件）；reads/bases 与 SRA run 统计完全一致。FASTQ 质量行是 `?`（FASTA→FASTQ 占位符），按 FASTA 使用即可 |
| 论文描述 | 茎、叶、小穗、穗轴 4 个组织总 RNA 等摩尔混合，1 个 IsoSeq 文库、1 个 PacBio HiFi cell，**7.3 Gb 原始数据** |
| 说明 | 7.3 Gb 是原始 IsoSeq 数据量；SRA/ENA 实际提交的是 FLNC polished HQ 集（324 Mb），两者量级不矛盾，**不是 subreads** |

## 3. RNA-seq（Illumina，18 个样本 / 18 个 run）

**设计**：品种 Sumai 3；2 个组织（spikelet 小穗、rachis 穗轴）× 3 个处理（接种 F. graminearum 5 dpi、mock 接种 5 dpi、不接种 0 dpi）× 3 个生物学重复 = 18。
实验标题（experiment_title）与 library_name（`JF_7IRR1` 等）可唯一标识；每个样本 1 个 run。

| 处理/组织 | runs | spots | bases |
|---|---|---|---|
| Inoculated spikelet（接种小穗 5dpi） | SRR38409713 / 714 / 715 | 134,158,539 | 40.2 Gb |
| Mock inoculated spikelet（mock 小穗 5dpi） | SRR38409709 / 723 / 724 | 117,509,946 | 35.3 Gb |
| No inoculation spikelet（不接种小穗 0dpi） | SRR38409717 / 718 / 719 | 120,146,047 | 36.0 Gb |
| Inoculated rachis（接种穗轴 5dpi） | SRR38409716 / 725 / 726 | 127,092,775 | 38.1 Gb |
| Mock inoculated rachis（mock 穗轴 5dpi） | SRR38409710 / 711 / 712 | 122,983,041 | 36.9 Gb |
| No inoculation rachis（不接种穗轴 0dpi） | SRR38409720 / 721 / 722 | 149,341,820 | 44.8 Gb |
| **合计** | 18 | 771,232,168 | **231.4 Gb** |

- 每个样本 33–61 M spots（PE），9.9–18.3 Gb，论文称“约 10 Gb/sample”，实际平均 12.85 Gb；
- 建库策略均为 RNA-Seq / TRANSCRIPTOMIC / PAIRED。

## 4. 可用于注释/表达的“证据”边界

**有：**

- IsoSeq full-length reads（1 个文库，4 组织混合）——可作 Mikado/EM 的 isoform/UTR 证据；
- 18 个 RNA-seq（2 组织 × 3 处理 × 3 重复）——可作剪接/表达证据（HISAT2 → StringTie/Mikado）。

**没有（本 project 内）：**

- 没有转录本组装 FASTA/GFF、没有 count matrix / DE 结果表、没有 GEO series（GEO 查询 0 条）；
- 论文正文 Fhb1 候选基因 DE 提到的 7 个品种（Sumai 3、ND2710、Alsen、Wheaton、Steele-ND、Rollag、Glenn）中，**本 project 只含 Sumai 3 的 18 个 RNA-seq 样本**，其他品种数据未在此 project 的 SRA 列表中，Data availability 也未给出其他 accession；
- 无 IsoSeq 单独 BioSample：IsoSeq run 挂在基因组 DNA 的 BioSample 上，样本级组织信息缺失。

## 5. BioSample 元数据质量问题（重要）

18 个 RNA-seq BioSample 的 `cultivar` 字段被错填为 `Sumai 5` … `Sumai 24`（像是样本顺序号），而 `sample_title`/`experiment_title` 均为 “Sumai3”。若用这些数据做自动注释/表达，**不要用 cultivar 字段分组**，应以 `experiment_title` / library_name（`JF_7…`）为准。

## 6. 对平台注释工作的意义

- 这些数据可以在拿到作者 GFF 后用于：注释结构校验（IsoSeq 支持 UTR/isoform）、表达验证（Fhb1 区域/候选基因）；
- 也可以在作者不提供 GFF 时，作为“转录证据”参与平台自己的注释评估，但不能替代作者的 HC 基因集（104,620 基因）；
- 若要上平台“表达谱”模块，需另行比对/定量（RNA-seq 231 Gb、IsoSeq 324 Mb），建议另立任务。
