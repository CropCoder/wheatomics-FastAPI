# 野生二粒小麦 WEW_NT 基因组 — 论文与下载资源清单

> 文献：Yi C., Liu Q., Shen L., Zhang J., Zhu C., Wang T., Han F., Liu Y.
> **Near-complete assembly of wild emmer wheat unveils centromere reorganization during polyploid evolution**
> *Nature Genetics* (2026), online 2026-10-22. DOI: [10.1038/s41588-026-02808-3](https://doi.org/10.1038/s41588-026-02808-3)
> 单位：中科院遗传与发育生物学研究所（韩方普组）；对象材料：野生二粒小麦 Zavitan（*Triticum turgidum* ssp. *dicoccoides*，AABB）
> 核对日期：2026-10-23（数据可用性声明取自原文页面）

## 1. 基因组组装（GWH）

| 项 | 内容 |
|---|---|
| 组装名 / accession | **WEW_NT** / **GWHHHUI00000000.1** |
| 物种 | *Triticum dicoccoides*（野生二粒小麦） |
| 序列文件 | `GWHHHUI00000000.1.genome.fasta.gz` — **3,012,294,318 B（约 3.01 GB 压缩）** |
| 直链 | <https://download.cncb.ac.cn/gwh/Plants/Triticum_dicoccoides_WEW_NT_GWHHHUI00000000.1/GWHHHUI00000000.1.genome.fasta.gz> |
| md5 文件 | <https://download.cncb.ac.cn/gwh/Plants/Triticum_dicoccoides_WEW_NT_GWHHHUI00000000.1/GWHHHUI00000000.1_md5.txt> |
| md5 | `663e9bd6d74195f4d0801a548c68f34f` |
| 目录索引 | <https://download.cncb.ac.cn/gwh/Plants/Triticum_dicoccoides_WEW_NT_GWHHHUI00000000.1/> |
| 数据量亮点（论文） | contig N50 74.58 Mb；14 条染色体锚定率 99.81%；14 个着丝粒全部拼通（6.3–9.2 Mb，均值 7.7 Mb）；补回约 400 Mb 新解析序列 |

**FASTA 头格式（关键）**：GWH 命名，需重命名后才符合平台流水线要求：

```
>GWHHHUI00000001.1	Chromosome 1	Complete=T	Circular=F	OriSeqID=chr1A	Len=611773303
```

→ 按 `OriSeqID` 映射为平台要求的 `>Chr1A`（大写 Chr；第 1 条 Chr1A = 611,773,303 bp）。

## 2. 注释与表达（Zenodo，论文引用的 DOI）

记录：[10.5281/zenodo.19882165](https://doi.org/10.5281/zenodo.19882165)（v1，concept DOI 10.5281/zenodo.19882164）

| 文件 | 大小 | 内容 |
|---|---|---|
| `WEW_NT.final.gff.zip` | 32.3 MB | GFF3 注释（md5 89433d0b8dc3f02252e6271552b145b7） |
| `WEW_NT.final.cds.zip` | 37.8 MB | CDS 序列（md5 d4a70859931d6e1b4931e8358209de0d） |
| `WEW_NT.final.protein.aa.zip` | 22.6 MB | 蛋白序列（md5 846d1aab7bea076f378a27af928939d5） |
| `WEW_NT.final.gtf.zip` | 15.4 MB | GTF 注释（md5 de62874ee174a53977fd0b086c65ae2f） |
| `old_on_new.liftoff.gff3.zip` | 3.8 MB | LiftOff 旧注释提升版（md5 1934ac37818014236742af6792659881） |
| `WEW_NT.all_gene_TPM.tsv.zip` | 71.5 MB | 基因 × 样本 TPM 矩阵（md5 59ea32724779b6cf35797a74199df549） |
| `WEW_NT_all_genes_TPM.tsv.zip` | 71.5 MB | TPM 矩阵（另一版本，md5 aae60899e18ab81c38f815be15e12ab6） |
| `WEW_NT.final.featureCounts.txt.zip` | 16.1 MB | featureCounts 原始计数（md5 ec2b835f384544c25212d1a51bc3c595） |

下载模板：`https://zenodo.org/api/records/19882165/files/<文件名>/content`

## 3. 原始测序数据（NGDC GSA，BioProject PRJCA051525）

项目页：<https://ngdc.cncb.ac.cn/bioproject/browse/PRJCA051525>（2025-11-18 提交，35 个 BioSample）

| GSA 项目 | 体量 | 内容 | 下载入口 |
|---|---|---|---|
| **CRA034670** | 34 文件 / **1790.47 GB** | Zavitan 主要测序（HiFi、ONT、Illumina、Hi-C、RNA-seq） | `https://download.cncb.ac.cn/gsa6/CRA034670`（FTP: `ftp://download.big.ac.cn/gsa6/CRA034670`） |
| **CRA043542** | 26 文件 / **17.09 GB** | CENH3 ChIP-seq 系列（Zavitan ×2、Langdon ×3、Kronos、Renmin、PI192501、Italy363、8155-B1 等） | `https://download.cncb.ac.cn/gsa5/CRA043542`（FTP: `ftp://download.big.ac.cn/gsa5/CRA043542`） |

提示：HTTP 限速明显，建议 FTP（FileZilla/`wget -c`）或 Qtrans。

## 4. 变异数据（SNP/Indel/SV VCF，Zenodo 分片）

论文正文只给了 19882165，但 VCF 实际在**同一 concept DOI 的后续版本**里，且按 1.07 GB 切片：

| Zenodo 记录 | 文件数 / 体量 | 内容 |
|---|---|---|
| [20551640](https://zenodo.org/records/20551640) | 92 / 98.07 GB | `final.QC_snp.vcf.gz.part_0000 … part_0111`（SNP VCF 全部分片） |
| [20593962](https://zenodo.org/records/20593962) | 21 / 21.47 GB | `final.QC_snp.vcf.gz.part_0030 … part_0049` + `split..md5sum.txt` |
| [20539165](https://zenodo.org/records/20539165) | 17 / 15.01 GB | `final.sv.vcf.gz`（0.16 GB）+ indel VCF 分片 + md5 |
| [20623802](https://zenodo.org/records/20623802) | 5 / 0.07 GB | full-length LTR 系统发育树与比对 |
| [22198553](https://zenodo.org/records/22198553) | 3 / 0.01 GB | `zavitan.cent/CENH3.q20.bg` 等 CENH3 信号 bigwig |

分片恢复方法：`cat final.QC_snp.vcf.gz.part_* > final.QC_snp.vcf.gz`，先核对 `split..md5sum.txt`，再 `tabix -p vcf`。

## 5. 分析代码

- GitHub：<https://github.com/CongyangY/WEW_centromere>（R 脚本按主题分组；另含 `Genome_assembly_annotation_workflow.md`、`BinBash_WGS_workflow.md`）
- Zenodo：10.5281/zenodo.22177298（`WEW_centromere-ff95fe5.zip`，60 KB）
- 注意：仓库无开源 license，复用需按作者条款。

## 6. 与 WheatOmics 平台集成的关键结论

1. **命名冲突**：平台现有 `Zavitan`（AABB）是北大泛基因组论文用的**另一套组装**（GWHJKYG00000000.1，818 条序列，10.51 Gb，DOI 10.1038/s41588-026-02678-9，已有 `Genefunc_AABB_Zavitan_table`）。本文这套必须新数据集 ID，建议 **`AABB_WEW_NT`**（与 GWH 组装名 WEW_NT 一致）。
2. **FASTA 头**是 GWH 命名（`OriSeqID=chr1A`），上线前必须重命名为 `>Chr1A`；`add_wheat_genome.sh` 要求 FASTA 头为 `Chr` + 染色体号。
3. **注释 ID 格式待核**（已下载，待检查）：流水线要求 GFF 第 1 列与 FASTA 染色体名一致、mRNA ID 以 `.数字` 结尾，且 CDS/PEP 的 ID 与之对应；不满足需 gffread 重导出。
4. 平台流水线会补齐 EggNOG/Pfam、CDS/PEP BLAST 库、JBrowse、GetFasta/PrimerServer2 登记、genome_registry 元数据（DOI/期刊/年份）。
5. 论文的 SNP/Indel/SV VCF 体量约 135 GB（分片），是否上线平台需单独评估（VariantHub 数据接入口径与体积）。

## 7. 本次已启动的服务器下载

- 位置：`/var/www/data/masw_data/AABB_WEW_NT/{genome,annotation}`
- 方式：后台 `wget -c`（无限重试、断点续传），日志 `AABB_WEW_NT/fetch.log`
- 内容：基因组 FASTA + md5 + 8 个 Zenodo 注释/表达文件
- 完成后自动 `md5sum -c` 校验
