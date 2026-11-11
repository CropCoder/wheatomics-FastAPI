# 四个二倍体 *Aegilops* 参考基因组（M / C / U / N）上线评估与计划

> 触发来源：*BMC Plant Biology* 2026（Article in Press，2026-11-07 上线），DOI [10.1186/s12870-026-10046-2](https://doi.org/10.1186/s12870-026-10046-2)
> —— "Chromosome-level reference genome assemblies and annotation of four diploid Aegilops"（Khadka, Edwards, …, Pozniak, Cloutier；AAFC Ottawa + USask，4D Wheat 项目）
> 数据：组装/原始数据在 NCBI（4 个 BioProject），基因 + TE 注释在 Zenodo DOI [10.5281/zenodo.22681907](https://doi.org/10.5281/zenodo.22681907)
>
> 计划日期：2026-11-11 ｜ 依据：`~/.agents/skills/lab-server/references/wheatomics-new-genome-sop.md` + **本次实测的生产脚本**
> （`add_wheat_genome.sh` md5 `70fb9ff2…`、`finish_genome_integration.sh` md5 `e4886d0c…`）｜ 先例：`CWI22960_genome_update_plan.md`、`Sumai3_genome_update_plan.md`
>
> **本文件是评估与计划；阶段 0 起的所有生产改动需你确认后执行。**

---

## 0. 结论先行

**这批数据"齐"了：4 个组装是 NCBI 上的染色体级公开发布（4DWheat），4 套基因注释 + TE 注释在 Zenodo，不是"只有序列"也不是"只有注释"。可以直接走完整流水线（核酸 + CDS/PEP + EggNOG/Pfam + 中国春 02G + JBrowse），不需要 CWI 22960 那种 genome-only 的两阶段妥协。**

| 检查项 | 现状（2026-11-11 实测） | 结论 |
|---|---|---|
| 4 个组装是否公开 | ✅ NCBI：`GCA_052815735.2`(comosa) / `GCA_052815875.1`(markgrafii) / `GCA_060308565.1`(umbellulata) / `GCA_052815765.1`(uniaristata)，均 Chromosome level、7 条染色体、3.58–4.48 Gb | ✅ 可直接下载（含 md5） |
| 基因注释 | ✅ Zenodo：每物种 HC+LC 合并 GFF3（含 gene/mRNA/exon/**CDS**）+ 蛋白 FASTA；基因数 51,203 / 47,246 / 49,677 / 50,416（与论文 Table 3 一致） | ✅ 可上完整注释层 |
| TE 注释 | ✅ Zenodo：EDTA `*.TEanno.gff3.gz`（62–78 MB gz，重复含量 86.3–88.2%） | ✅ 可选做 JBrowse 轨道 |
| 注释 ↔ 组装 兼容性 | ✅ 实测：4 套 GFF 的 seqid **全部**能在对应 NCBI 组装的序列名中找到（`1M`…`7M` 等），且每条序列上 GFF 最大坐标 < NCBI 序列长度（0 条越界） | ✅ 坐标体系一致 |
| 平台是否已有 | `/api/genomes` 316 个中：Ae. comosa 1 个（PI551049）、Ae. umbellulata 2 个（TA1851 / PI554389），**markgrafii / uniaristata 0 个**；本次 4 个登录号（AE783/AE740/AE680/EKC105）0 命中 | ⚠️ 同物种已有别的材料 → **本批是"新增并存"，不是替换** |
| 上线路径 | 完整流水线（`add_wheat_genome.sh` 10 步）+ 收尾；**但流程本身有 6 处已过期/不支撑二倍体的硬伤**（见 §3.2） | ⚠️ 需要先修流程（阶段 0）再跑 |
| 工作量 / 磁盘 | 4 个基因组 **约 5–8 h 机时**（下载+流水线+轨道）+ **约 2–3 个工作日人工**（含流程修复与归一化脚本）；磁盘 **+80–120 GB**（`/var/www` 现剩 30 TB） | 低-中 |
| 注释归一化工作量 | 全部 seqid 需按 assembly_report 改名（NCBI FASTA 头是 `CM…`/WGS 登录号）；**51,666 个 LC 模型 mRNA ID**（`model.model.STRG.n.1.p1`）不以 `.数字` 结尾必须改写（其中 6,401 个跨物种重名）；pep 需清 `.`/`*` 终止符 | ⚠️ 中（脚本化，1 次性，0.5–1 d） |

**建议路线：先 `阶段 0` 修流程（半天）→ 先拿 1 个基因组（推荐 *Ae. uniaristata*）走通全流程 → 再批量 3 个。**
理由：这是平台第一次接入 M/C/U/N 这四个倍性代码，问题大概率集中在"二倍体单字母倍性"和"新页面（V2 JBrowse / wheatBLAST SPA）"两处；先拿结构最简单的 *Ae. uniaristata*（注释只落在 15 条序列：7 染色体 + 8 scaffold，无复杂 scaffold 命名）验证，比一次跑 4 个再回滚便宜得多。

**需要你拍板的 6 件事（见 §12）：①是否现在做/是否先试点；②命名方案；③HC+LC 还是仅 HC；④是否加 TE 轨道；⑤旧条目的处置；⑥执行授权与时间窗。**

---

## 1. 论文与数据源（已核实）

### 1.1 论文

| 项 | 值 |
|---|---|
| 标题 | Chromosome-level reference genome assemblies and annotation of four diploid Aegilops |
| 作者 | Bijendra Khadka, Tara Edwards, Madeleine Lévesque-Lemay, Jennifer Ens, Harmeet S. Chawla, Chunfang Zheng, Frank M. You, Curtis J. Pozniak, Sylvie Cloutier |
| 期刊 / DOI | *BMC Plant Biology*（Article in Press）｜ 10.1186/s12870-026-10046-2 |
| 时间 / 许可 | Received 2025-11-06；Accepted 2026-09-22；上线 2026-11-07 ｜ **CC BY 4.0**（Crown 2026） |
| 组装策略 | PacBio HiFi（28.1–35.8×）+ Bionano 光学图谱 + Hi-C（43.5–91×）→ hifiasm + YaHS |
| 注释策略 | RNASeq（10 组织 × 3 重复）+ IsoSeq（~30 样本池化）→ EVM/TAMA + 同源预测（Ae. tauschii、Ae. speltoides、Ae. longissima 等）+ AHRD 功能描述；HC/LC 分级 |
| Data availability 原文 | "The genome assemblies and all raw sequencing data … have been deposited in the NCBI Assembly and SRA … Bioproject accessions **PRJNA1506336, PRJNA1174795, PRJNA1114735, PRJNA1154594** … Bionano optical map data and the gene and repeat annotation datasets are available on Zenodo: https://doi.org/10.5281/zenodo.22681907" |
| 关键生物学结论（供卡片/引文说明，不进数据库） | 4 个二倍体在 D 谱系内构成姐妹单系群；与 Ae. tauschii / 四倍体 / 六倍体比较揭示多个染色体间重排；补齐 11 个二倍体 Aegilops 的高质量组装 |

### 1.2 四个材料与组装（NCBI 实测）

| 物种（基因组） | 材料 / 登录号 | NCBI 组装号 | BioProject / BioSample | 组装级别 | 总长 (bp) | 序列数（染色体+未定位） | contig N50 | scaffold N50 | 覆盖度 | 发布日期 |
|---|---|---|---|---|---|---|---|---|---|---|
| *Ae. comosa*（M） | **IPK-AE783** | **GCA_052815735.2**（`ASM5281573v2`） | PRJNA1506336 / SAMN43422618 | Chromosome | **4,407,741,597** | 17（7 + 10） | 9,246,063 | 637,736,480 | 30.4× | 2026-09-18 |
| *Ae. markgrafii*（C） | **EKC105_RL5723** | **GCA_052815875.1**（`ASM5281587v1`） | PRJNA1174795 / SAMN44347220 | Chromosome | **3,577,170,360** | 24（7 + 17） | 9,048,916 | 489,410,094 | 35.4× | 2025-09-24 |
| *Ae. umbellulata*（U） | **IPK-AE740** | **GCA_060308565.1**（`AAFC_Aeum_AE740_v02`） | PRJNA1114735 / SAMN41492411 | Chromosome | **4,268,089,219** | 250（7 + 243） | 7,445,361 | 634,959,311 | 28.1× | 2026-08-21 |
| *Ae. uniaristata*（N） | **IPK-AE680** | **GCA_052815765.1**（`ASM5281576v1`） | PRJNA1154594 / SAMN43422673 | Chromosome | **4,475,943,907** | 21（7 + 14） | 31,980,500 | 652,967,279 | 35.8× | 2025-09-24 |

**NCBI 序列命名（易踩坑，实测）**：assemblies 的 `*_assembly_report.txt` 里 **Sequence-Name** 是 `1M`–`7M` / `1C`–`7C` / `1U`–`7U` / `1N`–`7N`（**无 `Chr` 前缀**），未定位为 `Super-Scaffold_*` / `Super_scaffold_*` / `scaffold_*` / `ptg*`；但 **FASTA 头用的是 GenBank 登录号**（染色体 `CM127985.1` 等，scaffold `JBHEGE020000008.1` / `JBDZUH…` / `JBLROG…`），**不是** Sequence-Name。→ 归一化必须用 assembly_report 的第 1 列（Sequence-Name）↔ 第 5 列（GenBank-Accn）建映射，把 FASTA 头替换成 `Chr*`/`ChrUn_*`（§6 A2）。

**FASTA 下载（NCBI FTP，均可直接取）**

| 物种 | 目录 | `*_genomic.fna.gz` md5 |
|---|---|---|
| comosa | `https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/052/815/735/GCA_052815735.2_ASM5281573v2/` | `38b8436f9c4eb360a066a1c79f1a122a` |
| markgrafii | `.../GCA/052/815/875/GCA_052815875.1_ASM5281587v1/` | `2a55e0ca2d74109c63c84dcb6d6a077a` |
| umbellulata | `.../GCA/060/308/565/GCA_060308565.1_AAFC_Aeum_AE740_v02/` | `1766c56e9ed9f2d6bcf292925a6628bb` |
| uniaristata | `.../GCA/052/815/765/GCA_052815765.1_ASM5281576v1/` | `b9b855678d7beba1cdd58f7ed89123eb` |

> 版本提示（实测）：
> - comosa 有 v1（`GCA_052815735.1`）与 v2（`.2`）两版，**仅 3M 长度不同**（v2 = 678,435,315 vs v1 = 678,382,411，+52,904 bp）；本计划用 **v2**（最新，2026-09-18）。
> - umbellulata NCBI 只有 v02（4.27 Gb；论文 Table 1 的 4.40 Gb / 未定位 160 Mb 是更早版本口径），注释 GFF 的 seqid 是 v02 名字的子集、坐标不越界 → 以 **v02** 为准。
> - markgrafii 另有一个北京大学的 `GCA_062042614.1`（PI369571，2026-10-16），**不是本文材料**，不要用错。

### 1.3 注释数据（Zenodo 22681907 实测）

record 22681907（concept 22680410，CC BY 4.0，2026-09-09 发布），每物种 5 类文件（record 共 **25 个文件** + README；README 另数列了 `*_proteins.fasta.gz` 等不符实的名字）：

| 文件 | 内容 | 平台用途 |
|---|---|---|
| `<Sp>_genes_HC_LC.gff3.gz` | 全部蛋白编码基因（HC+LC 合并），含 `gene/mRNA/exon/CDS` | **主注释** → 平台 `.gff3` |
| `<Sp>_genes_HC.gff3.gz` / `<Sp>_genes_LC.gff3.gz` | HC / LC 子集 | 备用（仅 HC 方案时用） |
| `<Sp>_genes_HC_LC.fasta.gz` | 全部基因模型翻译蛋白（**未做 CDS**） | 交叉验证用；平台 CDS/PEP 由 gffread 从 GFF+FASTA 生成 |
| `<Sp>.EDTA.TEanno.gff3.gz` | EDTA TE/重复注释（62–78 MB gz） | 可选 JBrowse TE 轨道 |
| `<Sp>_OpticalMap.cmap.gz` | Bionano 光学图谱 | 平台不用 |

**注释规模（GFF 实测 vs 论文 Table 3）**

| 项 | comosa | markgrafii | umbellulata | uniaristata |
|---|---|---|---|---|
| gene / mRNA | 51,203 | 47,246 | 49,677 | 50,416 |
| 论文 Table 3 总数（HC+LC） | 51,203（HC 37,622 / LC 13,581） | 47,246（34,133 / 13,113） | 49,677（35,799 / 13,878） | 50,416（35,816 / 14,600） |
| 注释覆盖的序列数（GFF seqid） | 15（7 chr + 8 scaffold） | 14（7 + 7） | 188（7 + 181） | 15（7 + 8） |
| 染色体上的基因 | 51,165（99.93%） | 47,193（99.89%） | 48,574（97.78%） | 50,350（99.87%） |
| scaffold 上的基因 | 38 | 53 | **1,103** | 66 |
| BUSCO（蛋白模式，embryophyta_odb10） | 97.2% | 96.6% | 96.9% | 96.6% |
| 重复含量（占组装） | 88.2% | 86.3% | 87.2% | 87.9% |

> 注：Zenodo README 的 comosa 记 51,205（HC 37,623 / LC 13,582），与论文 Table 3 的 51,203 差 2 条（版本微差）；平台以**实测 GFF 51,203** 写入。
>
> **数据瑕疵（不阻塞，但要避开）**：
> - Zenodo 的 `Ae.markgrafii_genes_LC.gff3.gz` 内容其实是 HC（与 HC 文件解压后逐字节相同，Zenodo 打包 bug）→ **只用 `*_genes_HC_LC.gff3.gz`**，不要用 LC-only 文件；建议顺手向作者反馈。
> - Zenodo README 与实际文件有 4 处文件名/数字不一致（如蛋白文件实际叫 `*_genes_HC_LC.fasta.gz`）→ 以 API 清单 + 实测为准。
> - 论文 Table 1 的 umbellulata 组装 4.40 Gb 与 NCBI v02（4.268 Gb）不符；comosa chr7 长度 Table S14（688.03 Mb）与 NCBI（690.83 Mb）不符 → **组装大小/序列数一律以 NCBI 为准**。
> - 论文目前是 **Article in Press**（2026-11-07 early access，会被 VOR 替换）：引用标 "in press"，数字以实测为准。
> - 3 个组装在 NCBI 标 "Expected final version: No"（仅 comosa v2 为 Yes）→ 作者未来可能更新组装；记录 md5，上游更新时重跑归一化。

### 1.4 注释 ↔ 组装 兼容性（本次实测，关键闸门）

| 物种 | GFF seqid 是否都在 NCBI 组装里 | 有无序列坐标越界 | 备注 |
|---|---|---|---|
| comosa | ✅ 15/15 | 0 | 染色体 `1M`…`7M`；TE GFF 的 seqid 需另做 token 映射（§8.7） |
| markgrafii | ✅ 14/14 | 0 | 染色体 `1C`…`7C` |
| umbellulata | ✅ 188/188 | 0 | 62 条未注释 scaffold 不建轨道即可 |
| uniaristata | ✅ 15/15 | 0 | — |

**端到端验证（已做，强证据）**：从 NCBI `nuccore` 按坐标回取基因区段 → 用「NCBI 序列 + Zenodo GFF」跑 `gffread -E -x -y` → 与 Zenodo 蛋白比对：**4 物种 × 4 个染色体位点 + 1 个未定位 scaffold 位点 = 17/17 完全一致**（仅 Zenodo 蛋白末尾多终止符）。覆盖 HC / LC-EVM / LC-STRG 三类 ID 家族与染色体两端 → **注释可以直接配 NCBI 组装 FASTA 使用，不需要 liftover**。

仍保留两道质量闸门：
- G1：全量 gffread pep 与 Zenodo 蛋白做条数 + 抽样/哈希比对（差异应只来自末端终止符）；
- G2：蛋白内部终止符比例**与 Zenodo 蛋白基线一致**（comosa 有 6,573 条模型含内部 `.`/终止符异常、umbellulata 为 0；这是作者注释模型本身的特征，不是错配信号）。若某物种比例远高于基线，则说明装配/注释版本错配。

### 1.5 与平台现有同物种条目的关系

| 物种 | 平台现有条目 | 本次新增 | 关系 |
|---|---|---|---|
| *Ae. comosa* | `Aegilop_comosa_PI551049`（MM，4.47 Gb，39,057 基因，DOI 10.1038/s41597-024-04346-1） | `MM_Aegilops_comosa_IPK_AE783`（4.41 Gb，51,203 基因） | 同物种、**不同材料**，并存 |
| *Ae. umbellulata* | `Aegilops_umbellulata_TA1851`（UU，4.23 Gb，36,268 基因，DOI 10.1038/s41588-023-01401-2）；`Aegilops_umbellulata_PI554389`（UU，78,076 基因，DOI 10.1111/pbi.14470） | `UU_Aegilops_umbellulata_IPK_AE740`（4.27 Gb，49,677 基因） | 同物种第 3 个材料，并存 |
| *Ae. markgrafii* | 无 | `CC_Aegilops_markgrafii_EKC105_RL5723`（3.58 Gb，47,246 基因） | 平台**首个 C 基因组** |
| *Ae. uniaristata* | 无 | `NN_Aegilops_uniaristata_IPK_AE680`（4.48 Gb，50,416 基因） | 平台**首个 N 基因组** |

> SOP 按"材料不同 = 独立数据集"处理（同 CWI 22960 vs NU00021 的先例）。本批 4 个新增后，平台 Aegilops 条目 25 → 29。

---

## 2. 平台现状核查（2026-11-11 线上只读实测）

| 检查 | 实测值 | 本批变化 |
|---|---|---|
| `/api/genomes` 总数 | **316** | → 320 |
| 倍性分组 | `MM`=1、`UU`=2；**无 `CC`、无 `NN`** | +MM1 +CC1 +UU1 +NN1 |
| `/api/blast/databases` | 核酸 **2,924**（other_triticeae 439 / diploid_wheat 164）；蛋白 **193**（other_triticeae 31 / diploid_wheat 15） | 每基因组：核酸 +9（1 整基因组 + 7 染色体拆分 + 1 CDS）、蛋白 +1（PEP）→ 核酸 **+36 → 2,960**、蛋白 **+4 → 197**；“other_triticeae” 核酸 +36、蛋白 +4 |
| `/api/jbrowse/datasets` | **219** | → 223 |
| `Genefunc_registry` 行数 | **216**（`/api/genes/functions/registry`） | → 220 |
| JBrowse 页面（`app/static/docpages/jbrowse.html` V2.0） | hero **213** assemblies；状态 **206** named / **22** groups；已有 `group-mm`（1 卡）、`group-uu`（2 卡）；**无 `group-cc`、`group-nn`** | 卡片 213→217、named 206→210、groups 22→24；MM 1→2、UU 2→3；新建 CC/NN 分区各 1 卡 |
| 生产机 | `/var/www` 116 TB，已用 81 TB，**剩 30 TB**（74%）；128 核、负载 ~11.7；gffread / samtools / blast+ 2.12.0 齐备 | 磁盘、算力充足 |
| `/var/www/data/masw_data/` | **无任何 Aegilops 数据目录** | 需新建 4 个 `PLOIDY_MYTAG/` |
| 生产代码版本 | 生产 HEAD = Gitee main = **`b7eb2fb`**；本地 = `22a7157`（github 领先 4 个未推 commit，且本地缺 `b7eb2fb`） | 阶段 0 必须先 `git fetch origin` 对齐（§3.2 观察） |

---

## 3. 我们的基因组更新流程（现状回顾 + 本次暴露的缺口）

### 3.1 标准流程（SOP，五阶段）

| 阶段 | 内容 | 产物 | 闸门 |
|---|---|---|---|
| ⓪ 命名门禁（跑前必做） | `finish_genome_integration.sh <PLOIDY> <MYTAG> <DOI> --check-name [--write-plan --confirm]`：校验材料身份、`SUB` 映射、`DB_CLASSIFICATION` 命中、BLAST optgroup、JBrowse 分区、display_order | `<data_dir>/name_plan.json` | 6 项全过才允许开跑（`add_wheat_genome.sh` 入口校验） |
| ① 输入归一化 | 四件套 `.fa/.gff3/.cds/.pep`：染色体 `Chr1A`、未定位 `ChrUn_*`、mRNA ID 以 `.数字` 结尾；`gffread` 生成 CDS/PEP | 4 个文件 | `check_genome_files.py` rc=0 |
| ② 流水线 | `add_wheat_genome.sh` 10 步：标准化 `.genome` → 拆分 → 核酸 BLAST（整基因组+按染色体）→ BED→MySQL Genefunc 表 → EggNOG/Pfam → 中国春 02G（miniprot）→ CDS/PEP BLAST → JBrowse refseq + all_gene 轨道 → `jbrowse_meta` 导入 → `genome_registry` 重建 | `.genome`、BLAST 库、`Genefunc_*_table`、JBrowse 目录、registry 行 | 日志 `[SUCCESS]`；Step 校验文件齐全 |
| ③ 收尾（前端/登记） | `finish_genome_integration.sh`：JBrowse 卡片、Web BLAST group/All genes/All proteins、`.fai`、`Genefunc_registry` upsert、聚合库 alias + `all_genomes_type.txt`、`import_jbrowse_meta`、`rebuild_genome_registry`、元数据写回、BLAST↔JBrowse 映射重建、10+ 项自动验收 | 页面卡片、registry 元数据、聚合库成员 | 自动验收全绿 |
| ④ 验收 | API/页面/BLAST 实测 + 回归旧基因组；`build_blast_jbrowse_map.py --check` | — | §9 清单 |

历史耗时参考：PT（六倍体小黑麦，17.9 Gb，215k mRNA）流水线 **1h23**；本批每个基因组 3.58–4.48 Gb、47–51k mRNA，预计单基因组 **25–45 min**。

### 3.2 本次实测发现的 6 个流程缺口（**上线前必须处理**）

| # | 缺口 | 证据（本次实测） | 影响 | 处理 |
|---|---|---|---|---|
| 1 | **SOP 文档已漂移**：生产 `add_wheat_genome.sh` md5 = `70fb9ff2…`，SOP 记的是 `208f0653…`（2026-10-23 版） | `md5sum /var/www/data/masw_data/add_wheat_genome.sh` | 照 SOP 做可能踩已修掉的坑 / 漏掉新增校验 | 以本计划 §6/§7 为准；事后更新 SOP |
| 2 | **染色体归一化只认 A/B/R**：`_prep/normalize_gff2.py` 的 `CHROM = ^chr([1-7][ABR])$`、`normalize2.sh` 的 `^chr[1-7][ABR]$`；且 `normalize2.sh` 循环硬编码 `PT ZX830` | 读脚本 | M/C/U/N 染色体 `1M` 会被错写成 **`ChrUn_1M`** → 基因全部"掉到未定位" | 阶段 0 写通用版本（`[1-7][A-Z]`）+ 本批专用参数化脚本 |
| 3 | **收尾脚本前端步骤已过期**：`finish_genome_integration.sh` step1 按旧 `<h5>&nbsp;`/`card-group` 结构插 JBrowse 卡片、step2 按旧 ViroBLAST `<optgroup>` 插 BLAST 下拉；现行生产页是 `app/static/docpages/jbrowse.html` V2.0（`.asm-group`/`.asm-card`）与 `app/static/blast2/index.html`（wheatBLAST SPA，库清单动态来自 `/api/blast/databases`，**无 optgroup**） | 脚本 md5 `e4886d0c…`；jbrowse.html V2.0 结构；blast2 SPA | `--check-name` 的第 3/4 项必 BLOCK；正式运行 step1/2 与验收项 FAIL；**不修就过不了门禁** | 阶段 0：给脚本加"SPA / V2 页面"分支（检测到无 optgroup 则跳过 BLAST HTML；卡片改成插 `.asm-grid` 并同步 hero/status/group 计数），或本批先 `--skip-html` 后手工按 §8 做 |
| 4 | **二倍体单字母倍性的 GROUP 推导不一致**：`finish_genome_integration.sh` 中 `DD\|AA\|BB\|UU\|HH\|AABBCC) GROUP="Diploid"`，其余 `GROUP="Other"` → `MM/CC/NN` 落 Other、`UU` 落 Diploid | 脚本 356–360 行 | `Genefunc_registry.Group` 分组错乱（应为 `Other Triticeae`） | 阶段 0：加 `MM\|CC\|NN` 到 Diploid 行，或本批显式 `--group "Other Triticeae"` |
| 5 | **registry 脚本缺 CC/NN 的亚基因组映射**：`rebuild_genome_registry.py` 的 `SUB` 有 `MM`、`UU`，**缺 `CC`、`NN`** | 代码 `scripts/rebuild_genome_registry.py:586` | `genome_registry.subgenomes` 为空（其余字段正常） | 阶段 0：加 2 个键值（2 行改动）。注：`app/core/genome_ordering.py` 已实测支持（`karyotype_ploidy("CC"/"NN")=2`），无需改 |
| 6 | **BLAST 分类关键词缺 2 个物种**：`other_triticeae` 已有 `aecomosa`、`aegilops_umbellulata` 等，但**没有** markgrafii / uniaristata 相关词。注意运行时分类实际有两条路径：registry 行建好后按 `ploidy` 自动归 `other_triticeae`；关键词只是 registry 行建立前的窗口期与 `--check-name` 门禁的依据 | `app/api/routers/blast.py:381-391`；实测：`CC_Aegilops_markgrafii_…`/`NN_Aegilops_uniaristata_…` → `other`（BLOCK） | 门禁不过；集成窗口期 getfasta 里看不到 | 阶段 0：`other_triticeae.keywords` 加 `aegilops_markgrafii`、`aegilops_uniaristata`（可选再加 `markgrafii`、`uniaristata` 兜底） |

> 另外两个**非阻塞**观察：
> - **本地 / Gitee / 生产三处 git 历史不一致**（实测）：本地 `main` = `22a7157`（比 `github/main` 多 4 个未推送 commit，含 translatome 相关）；Gitee `origin/main` = 生产 HEAD = **`b7eb2fb`**，且该 commit **不在本地历史里**。阶段 0 改代码前必须先 `git fetch origin`（Gitee）把 `b7eb2fb` 合进来，再基于最新代码提交，然后 **github + gitee 双推** → 生产 `git fetch && git merge --ff-only`。不要直接把本地未部署的 4 个 commit 推上生产。
> - 页面部署现状：生产 `/var/www/html/jbrowse.html` 与 repo 源文件 **byte-identical**（md5 `5c278cca…`，`deploy_doc_pages.py --check` 应可过）；生产 `blast.html` 与 repo `blast2/index.html` md5 不同（生产是 Gitee 版部署产物，本地 `blast2/index.html` 有未部署改动）——本批不需要改 BLAST 页面，勿顺手 deploy。
> - `/api/blast/databases` 磁盘缓存 TTL 1 h，改分类/加库后**必须** `sudo systemctl restart wheatomics-api`（60–90 s 不可用）。

---

## 4. 命名与分类方案

### 4.1 命名（SOP：数据集/库/表 = `${PLOIDY}_${MYTAG}`，PLOIDY 二倍体 = 单字母双写）

材料身份（SOP §0.5 必填）：**材料名/登录号** 是唯一权威身份，文章代号只能作补充。

| 物种 | PLOIDY | MYTAG | 数据集 / BLAST 库 / JBrowse / MySQL 表 | 显示名（label） | 材料身份（registry 字段） |
|---|---|---|---|---|---|
| *Ae. comosa* | `MM` | `Aegilops_comosa_IPK_AE783` | **`MM_Aegilops_comosa_IPK_AE783`** / `Genefunc_MM_Aegilops_comosa_IPK_AE783_table`（43 字符） | `Ae.comosa IPK-AE783 (M)` | cultivar=`IPK-AE783`；assembly_accession=`GCA_052815735.2` |
| *Ae. markgrafii* | `CC` | `Aegilops_markgrafii_EKC105_RL5723` | **`CC_Aegilops_markgrafii_EKC105_RL5723`** / `Genefunc_CC_Aegilops_markgrafii_EKC105_RL5723_table`（51） | `Ae.markgrafii EKC105_RL5723 (C)` | cultivar=`EKC105_RL5723`；assembly_accession=`GCA_052815875.1` |
| *Ae. umbellulata* | `UU` | `Aegilops_umbellulata_IPK_AE740` | **`UU_Aegilops_umbellulata_IPK_AE740`** / `Genefunc_UU_Aegilops_umbellulata_IPK_AE740_table`（48） | `Ae.umbellulata IPK-AE740 (U)` | cultivar=`IPK-AE740`；assembly_accession=`GCA_060308565.1` |
| *Ae. uniaristata* | `NN` | `Aegilops_uniaristata_IPK_AE680` | **`NN_Aegilops_uniaristata_IPK_AE680`** / `Genefunc_NN_Aegilops_uniaristata_IPK_AE680_table`（48） | `Ae.uniaristata IPK-AE680 (N)` | cultivar=`IPK-AE680`；assembly_accession=`GCA_052815765.1` |

- **为什么用全物种名**：MySQL 表名余量充足（最长 51/64）；与平台既有 Aegilops 条目（`Aegilops_umbellulata_TA1851`）风格一致；数据集名本身含完整登录号，直接命中 `/api/genomes?q=AE783` 搜索（`q` **不搜** `assembly_accession` 字段，见 `app/api/routers/genome.py:132-136`）。
- **备选短名**：`MM_AeComosa_AE783` / `CC_AeMarkgrafii_EKC105` / `UU_AeUmbellulata_AE740` / `NN_AeUniaristata_AE680`（表名 32–37 字符，序列名更短；代价是要多补 `aemarkgrafii`/`aeumbellulata`/`aeuniaristata` 3 个短关键词，且与既有 `Aegilops_*` 命名风格不一致）。
- **不用的坏名字**：`MM_AE783` / `CC_EKC105`（看不出物种）；任何带 `-` 的名字：`IPK-AE783` 直塞 MYTAG 会让 MySQL 表名带连字符——收尾脚本的 `SELECT COUNT(*) FROM Genefunc_${DS}_table`（`finish_genome_integration.sh:908`）未加反引号会直接 SQL 报错；`.` 同理（先例 `ae.longissima.AEG-6782-2` 的表名被规整成 `Genefunc_SS_ae_longissima_AEG_6782_2_table`）。原始连字符写法请写进 `display_name` / `notes`。
- 序列名（流水线 Step 1 自动生成）：`Chr1M_Aegilops_comosa_IPK_AE783`、`ChrUn_Super-Scaffold_100133_4M`（未定位保持原名加 `ChrUn_` 前缀，不加 `_MYTAG` 后缀，SOP 约定）。

### 4.2 分类归属

| 模块 | 归属 | 依据 |
|---|---|---|
| getfasta / BLAST 分类 | **`other_triticeae`（Other Triticeae genome）** | 与现有 non-tauschii Aegilops 一致（comosa/umbellulata/geniculata 都在此）；`diploid_wheat` 语义是"小麦供体"（tauschii/urartu/monococcum），不适用于 M/C/U/N |
| BLAST optgroup | 动态：wheatBLAST SPA 按分类渲染，**无需手改** | `app/static/blast2/index.html` 从 `/api/blast/databases.categories` 生成 |
| JBrowse 分区 | `group-mm`（+1）、`group-uu`（+1）、**新建 `group-cc`、`group-nn`** | `app/static/docpages/jbrowse.html` |
| Genefunc_registry | `Group='Other Triticeae'`、`Polyploidy=MM/CC/UU/NN` | 先例：Ae. ventricosa RM271、ae.longissima TAEG67822 |
| 基因功能下拉排序 | 无需改代码（`karyotype_ploidy("MM"/"CC"/"UU"/"NN")` 实测均 = 2，自动进二倍体组） | `app/core/genome_ordering.py`（已核实） |
| **IntervalTool / PfamSearch / CAPS 的基因组分组数组** | **需补 `CC`/`NN`**（否则新表在这三个页面的下拉里落 "Other / Unclassified"） | `app/static/interval/index.html:255`、`app/static/PfamSearch/index.html:181`、`app/static/caps/index.html:431`（静态文件，git pull 后刷新即生效） |
| Web BLAST 旧 flag（`web_blast_group`） | 新版 SPA 从 API 动态取库，但 `rebuild_genome_registry.py` 仍按旧 `blast.html` 的 `value='<db>_chromosomes'` 判定 → 会把新行标 0 | 阶段 0 修 `rebuild_genome_registry.py`（有 `blast_genome_db` 即 =1），否则 `stats.web_blast` 不增长 |

---

## 5. 阶段 0 —— 流程修复（上线前，预计 0.5–1 个工作日）—— ✅ 已实现（2026-11-11）

> 目标：把 §3.2 的 6 个缺口修掉，并新增本批专用归一化脚本。**这一步只改代码/脚本，不动生产数据。**
>
> **实现状态（2026-11-11 20:15）**：0.1–0.6 全部完成并本地验证；产物与报告见
> `docs/plans/aegilops4_2026-11/PHASE0_CORE.md`（代码修复）、`PHASE0_NORMALIZE.md`（归一化脚本）、
> `PHASE0_FINISH.md`（收尾脚本）；流程文档 v2 见 `docs/workflow/wheatomics-new-genome-sop.md`。
> **尚未部署到生产**（未 commit/push、未装服务器 _prep、未重启 API）——待确认后执行 §5.1 部署。

| # | 改动 | 文件 | 验收 |
|---|---|---|---|
| 0.1 | `other_triticeae.keywords` 增加 `"aegilops_markgrafii", "aegilops_uniaristata"`（可选再加短词 `"markgrafii","uniaristata"`；`aegilops_comosa`/`aecomosa`/`aegilops_umbellulata` 已有） | `app/api/routers/blast.py:381-391` | 分类模拟：4 个库名均 → `other_triticeae`（不加则 CC/NN 落 `other`，**已实测**） |
| 0.2 | `SUB` 增加 `"CC": "C", "NN": "N"`；`overrides` 增加 4 条（元数据见 §8.4；重点 `chromosome_count=7`、`assembly_level="Chromosome"`、`gene_count`、`te_content`），否则 rebuild 会把 `.fai` 序列数（15/14/188/15）写成染色体数 | `scripts/rebuild_genome_registry.py:586,750` | rebuild 后 registry 行字段正确、annotation_status=`available`、subgenomes `C`/`N` 非空 |
| 0.3 | 新增 `_prep/normalize_gff_diploid.py`：①**通用染色体规则** `^[1-7][A-Z]$ → Chr+原名`、其余 → `ChrUn_<原名>`；②mRNA/gene **ID 全局唯一化**：给 `model.model.STRG.*` 系 ID 加物种+材料前缀（本批 4 个物种的 STRG 模型 ID 大量重名；平台先例 `AeCom.PI551049.…`/`AeUmb.TA1851.…`），`evm.model.<chr>.<n>` 系本身含染色体号可保留；③ID 规则：`.p(\d+)$ → .\1`、`-mRNA-N → .N`、兜底追加 `.1`；④同步 `ID/Parent/Derives_from`；⑤保留全部记录并输出改名映射 + 冲突检查 | 新文件（服务器 `_prep/`，同时留档到仓库 `scripts/`） | 4 套 GFF 归一化后 `check_genome_files.py` rc=0、mRNA 数不变（51,203/47,246/49,677/50,416）、**跨物种重复 ID = 0** |
| 0.4 | `finish_genome_integration.sh` 适配现页面：S1 `--check-name` step3 改为查 `/api/blast/databases` 分类（或检测 SPA 后跳过）；S2 step4 改为解析 `id="group-<karyotype>"`；S3 `step_jbrowse_card` 改为插 `.asm-card` 到对应 `asm-grid`、无分区则新建 `asm-group`、同步 hero/status 计数；S4 `step_blast_html` 对 SPA 改为 no-op；S5 `verify()` 改用 API 断言；S6 `GROUP` 推导加 `MM\|CC\|NN` | `~/.agents/skills/lab-server/scripts/finish_genome_integration.sh`（同步服务器 `_prep/`） | `--check-name` 对 4 个候选名给出 `[OK]`；`--dry-run` 计划正确；正式运行不再因 HTML 步骤返回 1 |
| 0.5 | 域名分类数组补 `CC`/`NN`：`app/static/interval/index.html`、`app/static/PfamSearch/index.html`、`app/static/caps/index.html` | 三个静态页 | 新表（`Genefunc_CC_*`/`NN_*`）在三个页面的下拉里归入二倍体组 |
| 0.6 | `web_blast_group` 判定改造：`rebuild_genome_registry.py` 有 `blast_genome_db` 即置 1（新版前端动态取库） | `scripts/rebuild_genome_registry.py:476-493` | `stats.web_blast` 200→204 |
| 0.7 | （可选）给 `finish_genome_integration.sh` 加 `--te-track` 步骤（EDTA GFF → JBrowse CanvasFeatures，SOP §5.7） | 同上 | 单基因组 TE 轨道可渲染 |

> **`--check-name` 的临时绕过**（不改脚本也能先过门禁，供试点用）：脚本第 3 步只在 `gmap` 里能映射出 optgroup 名时检查；传 `--group "Other Triticeae"`（不在 `gmap` 内）→ `want=""` → 跳过该检查，可得到 `[OK] 命名可直接开跑`。**正式收尾仍建议修脚本**（S3/S4/S5），否则 `--skip-html` + 手工步骤 + verify 失败是必然的。

## 6.5 阶段 A 执行进展（2026-11-11 20:21–21:40，生产机下载完成 ✅）

> 用户确认「先在 wheatomics 上下载基因组和注释数据」。已在生产机 `/var/www/data/masw_data/` 建 4 个数据目录并后台下载
> （`setsid`，与登录会话解耦），使用仓库新增的幂等脚本 `scripts/fetch_aegilops4_data.sh`（已装到服务器
> `/var/www/data/masw_data/_prep/`，md5 `d074024d…`；断点续传 + md5 校验 + provenance.txt）。

| 物种 / 目录 | NCBI（GCA + FASTA + report + md5checksums） | Zenodo（HC+LC GFF3 / 蛋白 FASTA / EDTA TE） |
|---|---|---|
| `MM_Aegilops_comosa_IPK_AE783` | GCA_052815735.2 | Ae.comosa_* |
| `CC_Aegilops_markgrafii_EKC105_RL5723` | GCA_052815875.1 | Ae.markgrafii_* |
| `UU_Aegilops_umbellulata_IPK_AE740` | GCA_060308565.1 | Ae.umbellulata_* |
| `NN_Aegilops_uniaristata_IPK_AE680` | GCA_052815765.1 | Ae.uniaristata_* |

- 预计磁盘 ~5.3 GB（FASTA gz 4.7 GB + 注释 0.6 GB）；生产 `/var/www` 当前剩 30 TB。
- 日志：`/var/www/data/masw_data/_prep/fetch_aegilops4_<时间戳>.log`；每物种目录内 `provenance.txt` 记录 URL/md5/来源。
- **✅ 完成结果（21:40 校验通过）**：4 个 FASTA md5 与 NCBI `md5checksums.txt` 一致；12 个 Zenodo 文件 md5 与 API 一致；
  全部 `gzip -t` OK；每目录 7 文件 + `provenance.txt`，无残留分片；共 **~5.32 GB**（磁盘仍剩 30 TB）。
  明细见 `docs/plans/aegilops4_2026-11/DATA_DOWNLOAD_REPORT.md`（含一次 comosa 并发写损坏事故与 6 路分段重下修复记录）。
- **✅ A2 归一化已完成（2026-11-11 23:01）**：4 个基因组四件套已生成并通过验收（`check_genome_files.py` 4/4 rc=0；
  gene=mRNA 51,203 / 47,246 / 49,677 / 50,416；ChrUn 基因 38/53/1103/66；FASTA 序列数与长度全部匹配 assembly_report；
  跨物种 mRNA ID 重复=0）。产物与证据见 `docs/plans/aegilops4_2026-11/A2_PREPARE_REPORT.md`。
  工具已装服务器 `_prep/`：`normalize_diploid.py` / `renumber_gff_ids.py` / `prepare_aegilops4_dataset.sh`。
- **✅ G0 命名门禁已完成（2026-11-12 00:12）**：4 份 `name_plan.json` 已落盘，4/4 `[OK] 命名可直接开跑`
  （`ploidy` MM/CC/UU/NN、`group`=Other Triticeae、分类 other_triticeae、JBrowse `group-mm/cc/uu/nn`；
  CC/NN 分区收尾时新建）。本地副本 `docs/plans/aegilops4_2026-11/name_plans/`，明细见 `G0_NAME_PLAN_REPORT.md`。
- **✅ 阶段 0 代码已部署生产（2026-11-12 00:16，e06cb8c；overrides 补 display_name/subgenomes 于 01:20 部署 c8dfca5）**：
  `blast.py` 关键词、`SUB` CC/NN、4 条 overrides、SPA web_blast 判定、静态页 CC/NN 全部生效；API 已重启。
- **✅ G3 流水线完成（2026-11-12 02:13）**：4/4 `[SUCCESS]`（MM 00:19–00:51、NN 00:51–01:17、CC 01:17–01:47、UU 01:47–02:13，共约 1h54m）。
  BLAST 库（每基因组核酸 9 + 蛋白 1）、Genefunc 表、JBrowse（all_gene/DNA）、registry 行、EggNOG 注释全部生成。
- **✅ G4 收尾完成（02:23）**：4/4 rc=0、各 28 OK / 0 FAIL；JBrowse V2 卡片（hero 213→217、named 206→210、groups 22→24，
  CC/NN 新建分区）、`.fai`、聚合别名、registry 元数据、BLAST↔JBrowse 映射全部就绪。
- **✅ G5 验收完成（90/90 PASS）**：`scripts/accept_aegilops4_onboarding.py` 逐条核对（全局计数/前端/映射 23 项 +
  每基因组 16 项×4 + 回归 3 项），报告见 `docs/plans/aegilops4_2026-11/G3_G4_G5_REPORT.md`。
- **✅ 阶段 0 代码已部署生产**（HEAD `8ed123b`，API 已重启）。

> 收尾：阶段 0 代码已部署（分类关键词/SUB/overrides/SPA/静态页/收尾脚本），4 个基因组已上线并逐条验收通过。
> 遗留（非阻塞）：cite.html 引用块可选；`~/.agents` 技能目录安装受沙箱限制（脚本已版本化在仓库，服务器 `_prep/` 已最新）。
- 下一步：全部 `[SUCCESS]` 后 → 重启 API（刷新 BLAST 库清单缓存）→ **G4 收尾**（`finish_aegilops4_all.sh`）→ 再重启 API → **G5 验收**（`accept_aegilops4_onboarding.py` 逐条核对）。

**闸门 G0**：0.1–0.6 全部验收通过；代码 commit 到本地 → **github + gitee 双推** → 生产 `git fetch origin && git merge --ff-only` → `sudo systemctl restart wheatomics-api` → `/api/blast/databases` 分类计数正确、`/api/genomes/stats` 无异常。

### 5.1 阶段 0 实现产物与部署步骤（2026-11-11）

| 产物 | 位置 | 验证 |
|---|---|---|
| 分类关键词（7 个） | `app/api/routers/blast.py` | 4 DS × 3 库名 12/12 → `other_triticeae` |
| `SUB` CC/NN + 4 条 overrides + web_blast SPA 判定 | `scripts/rebuild_genome_registry.py` | AST 读回 + SPA/legacy 双分支模拟 |
| 三个静态页 diploid 数组 +CC/NN | `app/static/{interval,PfamSearch,caps}/index.html` | JSON 解析 + node --check |
| 归一化工具 | `scripts/normalize_diploid.py`（新，1671 行，md5 `727a0dff…`，`fasta/gff3/pep/check`） | 4 个真实 GFF 全量：计数保全（51,203/47,246/49,677/50,416）、seqid 全 Chr、mRNA ID 全 `.数字`、跨物种重复 7,081→0、平台 `check_gff3` 等价 4/4 PASS |
| 收尾脚本 v2 | `scripts/finish_genome_integration.sh`（1022→1400 行，md5 `d8162ac0…`） | fake docroot：4 DS `--check-name` 全 `[OK]`；V2 插卡 + 计数 + 幂等；SPA/legacy 双分支 |
| 流程文档 v2 | `docs/workflow/wheatomics-new-genome-sop.md` + `README.md` | 五阶段 G0–G5、v1→v2 修复记录 |

```bash
# ① 本地代码（仓库）→ 双推
git add app/api/routers/blast.py scripts/rebuild_genome_registry.py \
        app/static/interval/index.html app/static/PfamSearch/index.html app/static/caps/index.html \
        scripts/normalize_diploid.py scripts/finish_genome_integration.sh \
        docs/workflow docs/plans/aegilops4_2026-11
git commit -m "feat(genome-workflow): v2 onboarding — diploid Aegilops support, V2/SPA frontend, normalize tool"
git push github main && git push origin main     # github + gitee

# ② 生产更新代码 + 重启（让 blast.py / 静态页 / overrides 生效）
ssh … 'cd /var/www/FastAPI_backend_Port8000 && git fetch origin && git merge --ff-only origin/main'
sudo systemctl restart wheatomics-api            # 60–90 s 不可用

# ③ 安装流程脚本到技能目录与服务器 _prep
cp docs/workflow/wheatomics-new-genome-sop.md ~/.agents/skills/lab-server/references/wheatomics-new-genome-sop.md
cp scripts/finish_genome_integration.sh ~/.agents/skills/lab-server/scripts/
scp -P 2222 scripts/finish_genome_integration.sh scripts/normalize_diploid.py \
    fei@127.0.0.1:/var/www/data/masw_data/_prep/
md5sum scripts/finish_genome_integration.sh scripts/normalize_diploid.py   # 两边对齐

# ④ 部署后自检
curl -s 'https://wheatomics.sdau.edu.cn/api/genomes/stats' | head -c 400
curl -s 'https://wheatomics.sdau.edu.cn/api/blast/databases?program=blastn' | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["data"]["nucleotide"]["count"], [c["count"] for c in d["data"]["categories"] if c["id"]=="other_triticeae"])'
```

---

## 6. 阶段 A —— 数据准备（脚本就绪后每基因组 15–30 min；首次含脚本开发约 0.5–1 天）

工作目录：`/var/www/data/masw_data/${PLOIDY}_${MYTAG}/`（服务器）。例：`MM_Aegilops_comosa_IPK_AE783`（与数据集名完全一致）。

### A1 下载与校验

```bash
# 例：comosa（数据目录名 = 数据集名）
cd /var/www/data/masw_data/MM_Aegilops_comosa_IPK_AE783
curl -O https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/052/815/735/GCA_052815735.2_ASM5281573v2/GCA_052815735.2_ASM5281573v2_genomic.fna.gz
curl -O https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/052/815/735/GCA_052815735.2_ASM5281573v2/GCA_052815735.2_ASM5281573v2_assembly_report.txt
md5sum -c   # 期望 38b8436f9c4eb360a066a1c79f1a122a

# Zenodo 注释（每物种 2 个文件：GFF3 + 蛋白 FASTA；共约 4.7 GB FASTA gz + 注释 gz）
curl -LO https://zenodo.org/api/records/22681907/files/Ae.comosa_genes_HC_LC.gff3.gz/content
curl -LO https://zenodo.org/api/records/22681907/files/Ae.comosa_genes_HC_LC.fasta.gz/content
# 可选 TE：Ae.comosa.EDTA.TEanno.gff3.gz（75.6 MB）
```

### A2 归一化（`normalize_diploid.py` + `normalize_diploid.sh`）

> 两套映射必须收敛到同一套名字：**FASTA 用 GenBank 登录号**（`CM127985.1` / `JBHEGE020000008.1` …），**GFF 用 Sequence-Name**（`1M` / `Super-Scaffold_100133_4M` …）。统一从 `*_assembly_report.txt` 的第 1 列（Sequence-Name）↔ 第 5 列（GenBank-Accn）建映射表。

1. **FASTA**：`CM…` → `Chr1M`…`Chr7M`；`JB…`（WGS scaffold 登录号）→ `ChrUn_<Sequence-Name>`；`grep -c '^>'` 必须 = 17/24/250/21，**全部保留**（umbellulata 243 条未定位 scaffold 一条都不能丢，其中 181 条有基因）；
2. **GFF3**：`1M`→`Chr1M`…；`Super-Scaffold_*`/`Super_scaffold_*`/`scaffold_*`/`ptg*` → `ChrUn_<原名>`（与 FASTA 侧收敛到同一名字）；保留 `gene/mRNA/exon/CDS` 全部层级；
3. **mRNA/gene ID 规范化** —— **最终方案（2026-11-11 用户确认）：按平台风格重编号**，每染色体按坐标从 `000100` 起、每 100 递增：
   `gene = <物种.材料.r1.><染色体>G<6位号>`（例 `AeCom.AE783.r1.1MG000100`），`mRNA = gene + ".1"`；未定位 `UnG` 全局编号；作者原 ID 保留在 `original_id` 属性 + `idmap.tsv`（工具 `scripts/renumber_gff_ids.py`，`--check` 做闸门）。详见 `docs/plans/aegilops4_2026-11/ID_RENUMBER_REPORT.md`。
   以下旧规则仅用于旧条目/备选场景：
   （实测 4 物种合计 198,542 个 mRNA ID）：
   - 51,666 个 `model.model.STRG.<n>.<iso>.p<k>`（LC/TAMA 家族，各物种 12,301–13,675 条）**不以 `.数字` 结尾**，必须改写：`.p(\d+)$ → .\1`（或追加 `.1`）；
   - 其中 **6,401 个 ID 字符串跨物种重复、7,081 个多余拷贝**（两两交集 1,237–1,410）。平台 `all_gene`/`all_protein` 是跨基因组聚合库，重复 ID 会让 `blastdbcmd -entry` 返回多条、`/api/sequence/by-gene` 歧义 → **建议给这 51,666 个 STRG 系 ID 加"物种缩写+材料"前缀**（对齐平台先例 `AeCom.PI551049.…`、`AeUmb.TA1851.…`）：
     `model.model.STRG.315.1.p1` → `AeMar.EKC105.model.model.STRG.315.1.1`；
   - `evm.model.<chr>.<n>` / `model.model.evm.model.<chr>.<n>` 系（含 1M/1C/1U/1N 染色体字母）跨物种天然不重复，**保留原名**；
   - 同步改写 `ID=` / `Parent=` / `Derives_from=`，并输出"旧 ID → 新 ID"映射表留档；
4. `gffread -E -g ${MYTAG}.fa -x ${MYTAG}.cds -y ${MYTAG}.pep ${MYTAG}.gff3`（**CDS/PEP 必须由平台侧生成**，Zenodo 只给蛋白 FASTA）；
5. **清理 PEP 终止符**：三物种末端是 `.`，**umbellulata 末端是 `*`** → 统一去掉行尾 `.` 与 `*`（保留内部 `X`）；平台 `check_genome_files.py` 只自动清 `.`，`*` 要预处理脚本清好；
6. 交叉验证：全量 gffread pep 与 Zenodo 蛋白按 ID 映射比对（条数 + 抽样≥20 或全量哈希）；已知 17 位点 100% 一致，差异应只来自末端终止符；
7. 注意：**markgrafii 的 Zenodo `*_genes_LC.gff3.gz` 内容其实是 HC**（打包 bug）——一律只用 `*_genes_HC_LC.gff3.gz`。

### A3 质检与留痕

```bash
python3 /var/www/html/Script/check_genome_files.py ${MYTAG}; echo rc=$?   # 必须 rc=0
```
- `provenance.txt`：GCA/BioProject/BioSample、FTP URL、`genomic.fna.gz` md5、Zenodo DOI + 文件 md5、论文 DOI、归一化规则、接入日期；
- `name_plan.json`：阶段 0 的 `--check-name --write-plan --confirm` 生成（流水线入口强校验）。

**闸门 G1**：md5 通过；FASTA 序列头已用 assembly_report 映射为 `Chr*`/`ChrUn_*`（残留 `CM…`/`JB…` 登录号 = 0）；`grep -c '^>' .fa` = NCBI 序列数（17/24/250/21）、长度和 = 4,407,741,597 / 3,577,170,360 / 4,268,089,219 / 4,475,943,907；`.fai` 行数一致；`check_genome_files.py` rc=0；mRNA 数 = 51,203 / 47,246 / 49,677 / 50,416；GFF 第 1 列 100% 以 `Chr` 开头、mRNA ID 100% 以 `.数字` 结尾；gffread CDS/PEP 条数 = mRNA 数（626/577/637/668 条 CDS 长度非 3 倍数的模型保留，与论文口径一致）；pep 中无 `.`/`*`；**跨 4 物种 mRNA ID 重复数 = 0**；gffread pep 与 Zenodo 蛋白全量/抽样比对一致（差异仅末端终止符）；基因落在染色体上的比例 ≥97.7%（论文 97.8–99.9%）。

---

## 7. 阶段 B —— 流水线（每基因组 25–45 min，可后台）

```bash
export PATH=/var/www/html/blast/blast+/bin:/home/fei/mambaforge/bin:$PATH
export HOME=/home/fei
cd /var/www/data/masw_data/${PLOIDY}_${MYTAG}
setsid --fork bash -c "exec bash /var/www/data/masw_data/add_wheat_genome.sh \
  ${MYTAG} /var/www/data/masw_data/${PLOIDY}_${MYTAG} ${PLOIDY}" \
  > pipeline_${MYTAG}.log 2>&1 < /dev/null
```

- 产出：`${PLOIDY}_${MYTAG}.genome`（头已标准化为 `>Chr1M_${MYTAG} …`）、整基因组 + 7 条染色体 BLAST 库、`Genefunc_${PLOIDY}_${MYTAG}_table`、EggNOG/Pfam、中国春 02G BED、`.add_Description.cds/.pep` BLAST 库、JBrowse 目录（refseq + `all_gene`）、`jbrowse_meta`、`genome_registry` 基础行；
- **顺序跑**（不要 4 个并发）：EggNOG 用 12 CPU/库、miniprot 用 50 线程，并发会互相抢资源且日志/临时目录难排障；单基因组 25–45 min，4 个约 2–4 h，可挂夜间；
- 失败重跑前清理该基因组半成品（`.genome_*`、blastdb 同名文件、JBrowse 目录），或先确认 Step 号。

**闸门 G2**（每基因组）：
- 日志末尾 `[SUCCESS] ${MYTAG} 全部完成`；
- `blastdbcmd -info`：整基因组库序列数 = NCBI 序列数、总长 = §1.2；
- `SELECT COUNT(*) FROM Genefuncdb.Genefunc_${PLOIDY}_${MYTAG}_table` = mRNA 数；
- JBrowse `seq/refSeqs.json` 条数 = FASTA 序列数（含 `ChrUn_*`）；
- **翻译质量抽检**：gffread 产物与 Zenodo 蛋白基线一致（抽样比对 + 内部终止符比例与 §1.4 G2 基线一致；明显偏高=坐标/版本错配，立即停下查 §1.4）；
- BLAST 实测：用该物种一条保守基因（如 `TraesCS` 同源序列）blastn 能命中。

---

## 8. 阶段 C —— 前端 / 登记 / 收尾（每基因组 10–15 min）

### 8.1 聚合库与 `.fai`（SOP §5.4/§5.6）

| 项 | 操作 |
|---|---|
| `.fai` | `cd /var/www/html/getfasta/blastdb && samtools faidx ${PLOIDY}_${MYTAG}.genome && samtools faidx ${PLOIDY}_${MYTAG}.add_Description.cds`（PrimerServer2 用） |
| `all_genomes` | `${PLOIDY}_${MYTAG}.genome` 追加进 `all_genomes.nal` 的 `DBLIST`；`all_genomes_type.txt` 追加 4 行 `…genome<TAB>${PLOIDY}`。**成员是整基因组库（含 ChrUn），所以 seqid 增量 = 4 个组装的总序列数 17+24+250+21 = 312**（当前 `all_genomes` 约 115,354 seqid） |
| `all_gene` / `all_protein` | `${PLOIDY}_${MYTAG}.add_Description.cds` → `all_gene.nal`；`.pep` → `all_protein.pal`（+4 成员各） |
| 可选 | `scripts/rebuild_getfasta_aggregates.py --apply`（registry 驱动，默认 dry-run）复核 |

### 8.2 JBrowse 卡片（V2.0 页面，`app/static/docpages/jbrowse.html`）

- 4 张 `.asm-card`（`data-search` 含 `ae.comosa / ae783 / ipk-ae783 / mm`、DOI 等关键词；`<h3 class="asm-name">` 链接 `/jbrowse-1.12.3-release/?data=…`；`<p class="asm-doi">`）；
- MM 组计数 1→2、UU 组 2→3；**新建** `group-cc`、`group-nn` 两个 `.asm-group`（各 1 卡）；
- hero `213`→`217`；`asm-status` 静态文案 `206 named / 22 groups` → `210 / 24`（页面 JS 会按 DOM 自动重算，但静态值也要改，避免无 JS 时显示旧数）；
- 部署：**改 repo 源文件** → `python3 scripts/deploy_doc_pages.py --only jbrowse`（自动备份，无需重启 Apache）。

### 8.3 Web BLAST / getfasta / PrimerServer2

- wheatBLAST SPA 动态读取 `/api/blast/databases`：**无需改页面**，重启 API 后自动出现在 `other_triticeae` 组；
- getfasta 分类由 `DB_CLASSIFICATION` 决定（阶段 0.1 已加关键词）；
- PrimerServer2 动态扫描 `.genome` / `.add_Description.cds`，补过 `.fai` 后自动可见。

### 8.4 `genome_registry` 元数据（每基因组一行，写进脚本 overrides 防止 rebuild 覆盖）

| 列 | 值（以 comosa 为例） |
|---|---|
| `dataset_id` / `display_name` | `MM_Aegilops_comosa_IPK_AE783` / `Ae.comosa IPK-AE783 (M)` |
| `species` | `Aegilops comosa` |
| `common_name` | `Aegilops comosa (M genome)` |
| `ploidy` / `subgenomes` | `MM` / `M` |
| `cultivar_or_line` / `sample_id` | `IPK-AE783` / `IPK-AE783` |
| `assembly_accession` / `assembly_level` / `assembly_date` | `GCA_052815735.2` / `Chromosome` / `2026-09-18` |
| `genome_size` / `chromosome_count` / `gene_count` / `te_content` | `4407741597` / **`7`** / `51203` / `0.882`（`chromosome_count`/`assembly_level` 必须写 overrides，否则 rebuild 用 `.fai` 序列数当染色体数） |
| `doi` / `journal` / `publication_year` | `10.1186/s12870-026-10046-2` / `BMC Plant Biology` / `2026` |
| `paper_title` | `Chromosome-level reference genome assemblies and annotation of four diploid Aegilops` |
| `source_url` / `source_md5` | NCBI FTP 目录 / `38b8436f9c4eb360a066a1c79f1a122a` |
| `annotation_status` / `annotation_source` / `annotation_doi` | `available` / `Zenodo (4DWheat, HC+LC gene models + EDTA TE)` / `10.5281/zenodo.22681907` |
| flags | `getfasta_member=1`、`primerserver_fai=1`、`web_blast_group=1`、`gene_function_ui=1`、`synteny_entry=0`、`orthofinder_entry=0`（收尾脚本写回；`web_blast_group` 需阶段 0.6 修 rebuild 判定） |
| `notes` | `GCA_052815735.2 (4DWheat); 7 chr + 10 unplaced; 51,203 genes (HC 37,622/LC 13,581); BUSCO 97.2% (protein, embryophyta_odb10); assembly BUSCO 98.4%; HiFi 30.4x + Bionano + Hi-C; annotation on Zenodo 22681907` |

其余 3 个按 §1.2/§1.3 数值替换；markgrafii 的 `cultivar_or_line` 写 `EKC105_RL5723`、`chromosome_count=7`、`genome_size=3577170360`、`gene_count=47246`、`te_content=0.863`。

### 8.5 BLAST↔JBrowse 映射与重启

```bash
cd /var/www/FastAPI_backend_Port8000
set -a; . ./.env; set +a
PY=/home/fei/mambaforge/envs/zjw/bin/python3
$PY scripts/rebuild_genome_registry.py
$PY scripts/build_blast_jbrowse_map.py           # 重建映射
$PY scripts/build_blast_jbrowse_map.py --check   # 期望 CHECK OK（0）
curl -s http://127.0.0.1:8000/api/jbrowse/coverage
sudo systemctl restart wheatomics-api            # 分类缓存 1h，必须重启
```

### 8.6 引文 / 公告（可选）

- 服务器 `/var/www/html/cite.html`（**不在 repo**）加论文引文块（附录 B），改前备份；
- `app/static/docpages/help_news.html` 加一条 2026-11 新闻（可选，先例：每次新基因组上线会发）；
- 首页/微信稿可选（不在本计划内）。

### 8.7 可选：EDTA TE 轨道（决策点 ④，SOP §5.7）

4 个 TE GFF 都是 EDTA v2.2.1 标准 GFF3（SO 类型 `Gypsy_LTR_retrotransposon` / `CACTA_TIR_transposon` / `helitron` …，**无需 GFF2 转换**），但 **seqid 命名各物种不同**，必须按物种做映射（与基因 GFF/FASTA 收敛到同一套 refseq 名，否则轨道静默空显示）：

| 物种 | TE features | TE seqid 命名 | 处理 |
|---|---|---|---|
| comosa | 3,398,055 | 裸数字 `1`…`7` + 数字 token（`100133`/`166`/`846`…） | `N`→`ChrNM`；token→`ChrUn_Super-Scaffold_<token>_*`（用 assembly_report 消歧） |
| markgrafii | 2,786,519 | `1C`…`7C` + `scaffold_*`（与基因 GFF 同） | `Chr` 前缀改名即可 |
| umbellulata | 3,264,607 | `1U`…`7U` + `S_S_*` + `ptg*` | `S_S_`→`Super_scaffold_` 展开后改名；`Super_scaffold_73_2` 不在 NCBI（1 条特征，丢弃并记录） |
| uniaristata | 3,466,840 | `1N`…`7N` + `S_S_*` | `S_S_`→`Super-Scaffold_` 展开后改名 |

生成轨道（先例 PT/ZX830）：归一化 GFF → `flatfile-to-json.pl --trackLabel TE --type <top 类别> --trackType CanvasFeatures`（建议按 top 类别分 2–3 条轨道：LTR / DNA / 其它）→ `import_jbrowse_meta.py --dataset <DS>` 同步 → 验证 trackData.json 200。预计每基因组 15–25 min、轨道 1–2 GB。

**不可得**：着丝粒坐标（论文只有密度图）、45S rDNA 位点、UTR、ncRNA —— 不要在卡片/公告里承诺这些轨道。

---

## 9. 验收标准（硬指标）

| # | 项 | 断言 |
|---|---|---|
| 1 | `genome_registry` | `/api/genomes/{ds}`：species/ploidy/subgenomes(`M`/`C`/`U`/`N`)/accession/genome_size/`chromosome_count=7`/gene_count/doi/annotation_status=`available` 齐全，`visible=1`；`/api/genomes/stats` total 320、by_ploidy 出现 CC=1/NN=1、MM=2、UU=3 |
| 2 | BLAST 库 | `/api/blast/databases` 核酸 2,924→**2,960**、蛋白 193→**197**；`other_triticeae` 核酸 +36（每基因组 1 整基因组 + 7 染色体 + 1 CDS）、蛋白 +4；`blastdbcmd -info` 序列数/总长与 §1.2 一致 |
| 3 | Web BLAST | SPA 下拉可见 4 个 `*.genome` 及 28 条染色体库（4×7）；提交测试序列能出结果，且结果页有 JBrowse 按钮（映射 OK） |
| 4 | JBrowse | `/api/jbrowse/datasets` 219→**223**；`?data={ds}` 200；refseq 数 = FASTA 序列数（17/24/250/21）；`all_gene` 轨道有基因 |
| 5 | getfasta | `/api/sequence/chromosomes?database=all_genomes&pattern={MYTAG}` 命中；`by-interval` 返回 FASTA；基因组 chips 分组出现 CC/NN |
| 6 | PrimerServer2 | `/api/PrimerServer2/databases` genome 203→207、gene 194→198；4 个新库 examples 非空 |
| 7 | 基因功能 | `/api/genes/functions/tables` 含 4 张新表（registry 216→220）；`Group='Other Triticeae'`；示例基因能查功能；**IntervalTool / PfamSearch / CAPS 下拉**中 4 张表归入二倍体组（阶段 0.5 验证） |
| 8 | 前端 | `jbrowse.html` 含 4 张卡（hero 217 / named 210 / groups 24）；MM 2 卡、UU 3 卡；CC/NN 新分区各 1 卡 |
| 9 | 回归 | 旧条目（PI551049 / TA1851 / PI554389 / Ae. tauschii 等）BLAST、getfasta、JBrowse 正常；`all_genomes` 旧成员可查 |
| 10 | 映射 | `build_blast_jbrowse_map.py --check` 退出码 0；`/api/jbrowse/coverage` `ok=true`，4 个新基因组 `assembly_match=true` |

---

## 10. 风险与回滚

| 风险 | 概率/影响 | 对策 |
|---|---|---|
| 注释与组装版本错配（comosa v1/v2 的 3M 差 52.9 kb；umbellulata 论文 4.40 Gb vs NCBI v02 4.27 Gb） | 中/高 | 已实测 seqid 全匹配、坐标不越界、17 位点 gffread 翻译与 Zenodo 蛋白 100% 一致；G1 再全量比对 pep，G2 对比内部终止符基线；异常则退回逐基因校验 |
| **跨物种 mRNA ID 重名**（STRG 系，实测 6,401 个重复字符串 / 7,081 个多余拷贝） | 确定/中 | 阶段 0.3 给 STRG 系 ID 加物种前缀 + G1 断言跨物种重复=0；否则 `all_gene`/`by-gene` 歧义 |
| LC 模型 ID 改名引入冲突/丢失 | 中/中 | 脚本内置冲突检查（三种规则实测均 0 重复）；保留改名映射表 |
| `normalize_gff2.py` 把 M/C/U/N 染色体当 ChrUn | 确定/高 | 阶段 0.3 通用化（缺口 #2），G1 断言"7 条 Chr 染色体、97.7%+ 基因在染色体上" |
| `finish_genome_integration.sh` 过不了 `--check-name` / HTML 步骤失败 | 确定/中 | 阶段 0.4 修脚本；试点期兜底 `--group "Other Triticeae"`；正式收尾 `--skip-html` + §8 手工步骤 |
| `Group` 分类错（MM/CC/NN → Other） | 高/低 | 阶段 0.4 修；或显式 `--group "Other Triticeae"` |
| `chromosome_count` 被 `.fai` 序列数污染（15/14/188/15） | 确定/中 | 阶段 0.2 overrides 显式 `chromosome_count=7`、`assembly_level=Chromosome` |
| IntervalTool/PfamSearch/CAPS 下拉把新表归 "Other / Unclassified" | 确定/低 | 阶段 0.5 补 `CC`/`NN` 到三个静态页的分类数组 |
| `web_blast_group` 被 rebuild 归 0（`stats.web_blast` 不增长） | 确定/低 | 阶段 0.6 改判定；验收单独看 API 分类即可 |
| `ae.` 关键词误吞：任何库名子串含 `ae.` 都会归 `other_triticeae` | 低/低 | 本批命名不含 `ae.`；不要新增宽泛关键词 |
| 既有 comosa 行 `annotation_status=none` 但 gene_table 存在（口径不一致） | 确定/低 | 本批新行明确写 `available`；旧行是否顺手修正见 §12-⑤ |
| 4 个基因组顺序跑时间长 | 中/低 | 挂夜间；单基因组失败不影响已完成；并发上限 2（磁盘 IO 允许但 EggNOG 抢 CPU） |
| 磁盘（+80–120 GB） | 低/低 | `/var/www` 剩 30 TB；先用 `du` 复核同类已有目录（U 基因组 4.27 Gb → JBrowse 约 5.2 G，整库约 15 G） |
| API 重启 60–90 s 不可用 | 确定/低 | 低峰执行，一次重启覆盖 4 个基因组 |
| 本地 / Gitee / 生产 git 历史不一致（本地 `22a7157`、本地未推 4 个 commit；Gitee/生产 `b7eb2fb` 本地缺失） | 确定/中 | 阶段 0 先 `git fetch origin` 合并 `b7eb2fb` 再改代码；只推本计划相关 commit，**不要把本地未部署的 4 个 commit 带上生产** |
| 老同物种条目被误当重复删除 | 低/高 | 本计划**不删不改**旧条目；如需隐藏单独确认（§12-⑤） |

**回滚（任一步失败）**：
1. 恢复前端页面：`deploy_doc_pages.py` 的 `.bak-<时间戳>` 拷回；`blast2/index.html` 源在 repo，回滚即 `git checkout`；
2. 删 BLAST 库：`rm /var/www/html/getfasta/blastdb/${DS}.genome* ${DS}.add_Description.*` + `/var/www/html/blast/db/nucleotide/` 软链；
3. 删 JBrowse 目录 + `import_jbrowse_meta.py` 重导（或恢复 `jbrowse_meta` 备份）；
4. 删 `Genefunc_${DS}_table`（`wheatomics_ddl` 账号）+ `Genefunc_registry` 对应行；
5. 聚合库 alias 脱敏：备份的 `all_genomes.nal` / `all_gene.nal` / `all_protein.pal` / `all_genomes_type.txt` 拷回；
6. `genome_registry` 行删除（或恢复 SQL dump）；
7. `sudo systemctl restart wheatomics-api`。

---

## 11. 时间与资源

| 阶段 | 内容 | 人工 | 机时 | 备注 |
|---|---|---|---|---|
| 0 | 流程修复（0.1–0.6 共 6 项 + 新归一化脚本 + 收尾脚本适配，0.7 TE 可选） | 0.5–1 d | — | 含 1 次 API 重启；git 先与 Gitee 对齐 |
| A | 数据准备 ×4（NCBI FASTA ~4.7 GB 下载 + 归一化脚本开发/跑批 + gffread + 全量比对） | **0.5–1 d**（脚本为主） | 2–3 h（含 NCBI 下载） | 可与阶段 0 并行；用 `zenodo_probe/` 已下载注释先开发脚本 |
| B | 流水线 ×4（顺序） | 0.5 h（看日志） | **2–4 h** | 建议挂夜间 |
| C | 前端/登记/收尾 ×4 | 1–1.5 h | 0.5 h | JBrowse 卡片 + registry + 映射 |
| D | 验收 + 回归 | 0.5 h | — | — |
| **合计** | | **≈ 2–3 个工作日**（含试点） | **≈ 5–8 h** | 磁盘 +80–120 GB |

磁盘拆解（单基因组，按 Ae. tauschii 4.15 Gb 同量级实测：JBrowse 4.0 G、数据目录约 10–15 G）：
`fa 4.5 G + .genome 4.5 G + 染色体拆分 4.5 G + BLAST 整库 ~5 G + 7 染色体库 ~4.5 G + CDS/PEP/BED/EggNOG ~1.5 G + JBrowse ~5 G ≈ 25–30 G`（TE 轨道再 +1–2 G）。×4 ≈ 80–120 GB，对 30 TB 余量无压力。

---

## 12. 待你拍板的事项

1. **是否现在做 / 先试点？**
   - **A（推荐）**：阶段 0 修流程 → 先拿 ***Ae. uniaristata*（`NN_Aegilops_uniaristata_IPK_AE680`）** 走通全流程（结构最简单：注释只落在 15 条序列 = 7 染色体 + 8 scaffold）→ 确认无误再批量另外 3 个；预计 1.5–2 天出全部 4 个。
   - B：4 个一起直接跑（省 0.5 天，但出问题回滚面大）。
   - C：只做 1–2 个（如 markgrafii + uniaristata 补齐平台空白的 C/N 基因组），其余等。
2. **命名方案**：A（推荐）= 全物种名 `MM_Aegilops_comosa_IPK_AE783` / `CC_Aegilops_markgrafii_EKC105_RL5723` / `UU_Aegilops_umbellulata_IPK_AE740` / `NN_Aegilops_uniaristata_IPK_AE680`（表名 43/51/48/48 字符，与既有 Aegilops 条目风格一致）；B = 短名 `MM_AeComosa_AE783` / `CC_AeMarkgrafii_EKC105` / `UU_AeUmbellulata_AE740` / `NN_AeUniaristata_AE680`（序列名/库名更短，多补 3 个短关键词）。
3. **注释口径**：A（推荐）= **HC+LC 合并**（与论文 Table 3 一致，51k 基因）；B = 仅 HC（~36k，更干净但丢 LC，且与论文/引用口径不一致）。
4. **是否加 EDTA TE 轨道？** A（推荐）= 加（4 个 TE GFF 共 1,291 万个 features：3.40M / 2.79M / 3.26M / 3.47M；标准 GFF3/SO 类型，需按物种做 seqid 映射 → 每基因组 flatfile-to-json 约 15–25 min、轨道 1–2 GB → 4 个约 **+4–8 GB / +1–1.5 h**）；B = 暂不加（后续随时可补，重跑单步即可）。
5. **旧同物种条目处置**：A（推荐）= 保留并存（材料不同，命名/DOI 不同）；B = 把旧 `Aegilops_umbellulata_PI554389` 等标记 `visible=0` 或在卡片标 deprecated。
6. **执行授权与时间窗**：是否授权我在你确认后操作生产（SSH + 改代码 + 重启 API + 夜间流水线）；建议时段：低峰（夜间 22:00 后）跑流水线，API 重启挑凌晨或低访问时段。

---

## 附录 A：论文引文（cite.html / 卡片用）

> Khadka, B., Edwards, T., Lévesque-Lemay, M., Ens, J., Chawla, H. S., Zheng, C., You, F. M., Pozniak, C. J., & Cloutier, S. (2026). Chromosome-level reference genome assemblies and annotation of four diploid Aegilops. *BMC Plant Biology*. https://doi.org/10.1186/s12870-026-10046-2

数据引用：Khadka et al. (2026). Gene and repeat annotations for reference genome assemblies of four diploid Aegilops species. Zenodo. https://doi.org/10.5281/zenodo.22681907

## 附录 B：每基因组命令清单（占位符）

```bash
# 变量：PLOIDY=MM  MYTAG=Aegilops_comosa_IPK_AE783  GCA=GCA_052815735.2  MD5=38b8436f9c4eb360a066a1c79f1a122a
#       ZSPECIES=Ae.comosa  NCHR=7  NSEQ=17  NGENE=51203  ZPREFIX=AeCom.AE783.
DS=${PLOIDY}_${MYTAG}; DIR=/var/www/data/masw_data/${DS}
# A1 下载+校验（FTP 路径按 §1.2 拼）
# A2 normalize_diploid.sh ${DIR} ${ZSPECIES} ${ZPREFIX}
# A3 check_genome_files.py ${MYTAG}  → rc=0
# B  流水线（§7）
# C  .fai / alias / registry / 卡片 / 映射 / 重启（§8）
```

## 附录 C：本次核查证据（只读）

- 论文 PDF 全文（本地 `docs/plans/aegilops4_2026-11/khadka_2026_four_diploid_Aegilops_BMCPlantBiol.pdf` + `paper.txt`）：Table 1（组装）、Table 2（重复）、Table 3（注释）、Data availability
- Zenodo API：`https://zenodo.org/api/records/22681907`（25 文件清单 + md5 + README）
- NCBI：`https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=assembly&…`（4 个 GCA 的 BioSample/覆盖度/contig N50/发布日期）；FTP `*_assembly_stats.txt` / `*_assembly_report.txt` / `md5checksums.txt`
- 平台：`/api/genomes/stats`（316；MM=1、UU=2、无 CC/NN）、`/api/genomes?q=comosa|umbellulata|markgrafii|uniaristata`（1/2/0/0）、`/api/blast/databases?program=blastn`（2,924；other_triticeae 439）、`/api/jbrowse/datasets`（219）、`/api/genes/functions/registry`（216）
- 服务器实测（只读）：`/var/www` 30 TB free；`add_wheat_genome.sh` md5 `70fb9ff2…`；`finish_genome_integration.sh` md5 `e4886d0c…`；`_prep/` 脚本清单；gffread/samtools/blast+ 2.12.0
- 仓库：`app/api/routers/blast.py`（DB_CLASSIFICATION）、`app/core/genome_ordering.py`（已验证支持 MM/CC/UU/NN）、`scripts/rebuild_genome_registry.py`（SUB/overrides）、`app/static/docpages/jbrowse.html`（V2.0，与生产 byte-identical）、`app/static/blast2/index.html`（wheatBLAST SPA）、`scripts/deploy_doc_pages.py`、`scripts/build_blast_jbrowse_map.py`
- 本批注释实测（`docs/plans/aegilops4_2026-11/zenodo_probe/`）：GFF seqid/ID/坐标/计数分析脚本输出
- **支撑文档**（同目录，供逐项复核）：
  - `PAPER_DATA.md` —— 论文与 Zenodo 数据的逐项核查（发表信息、Data availability、GFF 实测、许可）
  - `PLATFORM_BASELINE.md` —— 线上平台/仓库代码逐行基线（`--check-name` 门禁实测模拟、需改代码清单 file:line、24 条风险）
  - `WORKFLOW_GAP.md` —— SOP 与生产脚本的差距分析、可执行步骤清单
  - `zenodo_probe/` —— 已下载的 README、GFF/蛋白 FASTA 探针文件、论文补充材料（Additional file 1–3）
