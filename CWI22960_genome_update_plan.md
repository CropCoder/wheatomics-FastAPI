# CWI 22960（dika 小麦，*Triticum turgidum* ssp. *carthlicum*）基因组上线评估与计划

> 触发来源：*Communications Biology* 2026 (Article in Press)，DOI [10.1038/s42003-026-11303-8](https://doi.org/10.1038/s42003-026-11303-8)
> —— "Tracing the origin of non-brittle rachis TtBTR1 alleles in wheat"（Emile Cavalet-Giorsa, Thomas Wicker, Simon G. Krattinger）
>
> 计划日期：2026-11-08 ｜ 依据：`~/.agents/skills/lab-server/references/wheatomics-new-genome-sop.md`、
> `genome-only-then-annotation-update.md` ｜ 先例：`Sumai3_genome_update_plan.md`、`WEW_NT_integration_plan.md`
>
> **本文件是评估与计划；阶段 A 起的所有生产改动需你确认后执行。**

---

## 0. 结论先行

**这篇论文里"新"的基因组只有一个：CWI 22960（dika wheat，四倍体 AABB）。平台目前没有它，且它是"新增"而不是"更新"——平台上现有的 carthlicum 条目是另一个材料 NU00021（四倍体泛基因组 2026，带基因注释）。**

| 检查项 | 现状（2026-11-08 实测） | 结论 |
|---|---|---|
| 组装是否公开 | ENA/NCBI **GCA_977050835.1**（2026-10-07 发布），Chromosome level，34×，hifiasm + Omni-C/YaHS | ✅ 可直接下载 |
| 组装规模 | 14 条染色体 10,395,351,798 bp + 10,708 条 unplaced scaffolds 485,672,382 bp = **10,881,024,180 bp**（沉积版；论文 Supplementary Data 1 记 10,881,601,880 bp，差 577,700 bp——版本/口径差异） | ✅ 与论文 10.88 Gb 一致 |
| 基因注释 | **无**：NCBI `feature_count` gene=0；ENA 无 GFF；Zenodo 21902085 只有 11 KB 代码包；论文未报告基因模型 | ❌ 阶段 B 被阻塞 |
| 平台是否已有 | `/api/genomes`（316 个）、BLAST 库（3,115 个）、JBrowse 数据集（219 个）中 **0 命中** `22960/carthlicum/dika` | ❌ 需新增 |
| 平台已有 carthlicum | `NU00021`（"Persian wheat"，10.497 Gb，注释 available，17 个 BLAST 库，JBrowse 有） | ⚠️ 有重叠，但材料不同 |
| 上线路径 | 只能走 **genome-only（阶段 A：序列层）**，注释后补；`finish_genome_integration.sh` 当前**不支持** genome-only（会 die） | ⚠️ 需手工 + 少量脚本改动 |
| 工作量 / 磁盘 | 约 4–6 h（含后台 BLAST/JBrowse 约 3–4 h）；磁盘 **+45–55 GB** | 中 |

**建议：先做阶段 A（序列层），`annotation_status=pending`。**

- 若目标是让用户能 BLAST / 提取 CWI 22960 序列（Ttbtr1-Ab 位点、~140 Mb judaicum 渐渗区、dika 材料本身），值得做；
- 若平台价值主要来自基因功能/表达/同源查询，则本基因组（无注释）收益有限，可等作者补注释或暂缓；
- 与 NU00021 不冲突：不同登录号、不同组装、不同 DOI（NU00021 来自四倍体泛基因组 Nat Genet 2026，本论文的 CWI 22960 是全新的染色体级组装，且是论文里 Ttbtr1-Ab 与 judaicum 渐渗分析的参考基因组）。

**需要你拍板的 4 件事（见 §9）：①是否现在做；②命名方案 A/B；③unplaced scaffolds 是否进 JBrowse；④是否授权生产执行。**

---

## 1. 论文与数据源（已核实）

### 1.1 论文

| 项 | 值 |
|---|---|
| 标题 | Tracing the origin of non-brittle rachis TtBTR1 alleles in wheat |
| 作者 | Emile Cavalet-Giorsa (KAUST), Thomas Wicker (Univ. Zurich), Simon G. Krattinger (KAUST, 通讯) |
| 期刊 | *Communications Biology*（Nature Portfolio，Article in Press） |
| DOI | 10.1038/s42003-026-11303-8 |
| 时间 | Received 2026-04-26；Accepted 2026-10-16 |
| 数据 | ENA **PRJEB101210**（CWI 22960 组装 + 论文声明含 Omni-C + 24 份重测序；Omni-C 实际未见公开，见 §2）、**PRJEB101209**（PacBio HiFi reads） |
| 代码 | https://github.com/emilecg/btr_analysis ；Zenodo 10.5281/zenodo.21902084（解析到 record 21902085，仅代码 11 KB） |

### 1.2 基因组（GCA_977050835.1，assembly name `CWI22960`）

| 项 | 值 |
|---|---|
| 物种 | *Triticum turgidum*（dika wheat / Persian wheat；论文：*T. turgidum* ssp. *carthlicum*） |
| 登录号 | **GCA_977050835.1**（ENA/NCBI 一致）；WGS 项目 **CDRTBV01**；BioSample **SAMEA120412366**（ERS27113052） |
| 组装级别 | **Chromosome**（14 条 pseudomolecule，`chr1A…chr7B`；ENA 内部名 1A…7B，accession `OZ367120.1`–`OZ367133.1`） |
| 总长 | **10,881,024,180 bp**（ungapped 10,880,961,880 bp） |
| 染色体 | 14 条，合计 **10,395,351,798 bp** |
| 未定位 | 10,708 条 unplaced scaffolds，合计 **485,672,382 bp**（4.5%），命名 `scaffold_15…`（GenBank `CDRTBV010000001.1…`） |
| contig N50 | NCBI 沉积版 **40,143,117 bp**；论文正文 42.6 Mb、Supplementary Data 1 42,620,968 bp（沉积版略低，属版本/口径差异，见 §7） |
| scaffold N50 | 755,996,689 bp；contigs 11,345；scaffolds 10,722 |
| 覆盖度/方法 | 34×；PacBio Revio + hifiasm v0.19.8；Omni-C + YaHS v1.1；Juicebox/CHROMEISTER 手工校正 |
| FASTA（推荐） | `https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/977/050/835/GCA_977050835.1_CWI22960/GCA_977050835.1_CWI22960_genomic.fna.gz`（3,255,246,645 B ≈ 3.03 GiB，md5 **4458e202c46347798298a5624f71c47b**） |
| FASTA（备选） | ENA `CDRTBV01.fasta.gz`（141,717,256 B）**只含 10,708 条 scaffold，不含 14 条染色体**；染色体需另取 `OZ367120.1`–`OZ367133.1`（`https://www.ebi.ac.uk/ena/browser/api/fasta/<acc>`）或直接走 NCBI 单文件 |
| 序列头格式 | `>OZ367120.1 Triticum turgidum genome assembly, chromosome: 1A`（染色体系）；scaffold 记录为 `scaffold: scaffold_15` 形式 |
| 质量 | BUSCO 98.5%（论文 Supplementary Data 1）；contigs 11,269（论文）/ 11,345（沉积版） |
| 注释 | **无**（NCBI feature_count：gene/protein_coding = 0，annotation_hashes = 空文件 md5；ENA 无 annotation；Zenodo 仅 11 KB 代码；论文未报告基因模型） |

**14 条染色体长度（bp，来自 NCBI assembly_report）：**

| 染色体 | 长度 | 染色体 | 长度 |
|---|---|---|---|
| chr1A | 607,068,812 | chr1B | 719,777,107 |
| chr2A | 804,814,643 | chr2B | 820,782,014 |
| chr3A | 762,198,704 | chr3B | 861,037,182 |
| chr4A | 766,263,445 | chr4B | 704,679,301 |
| chr5A | 720,345,150 | chr5B | 741,133,630 |
| chr6A | 627,435,842 | chr6B | 736,406,096 |
| chr7A | 755,996,689 | chr7B | 767,413,183 |

> 论文中与平台有关的关键生物学结果（供卡片/引文说明，不进数据库）：Ttbtr1-Ab = TtBTR1-A 内 459 bp 处 5,029 bp 逆转座子插入（248 bp LTR）；Ttbtr1-B 的插入实为 **11.97 kb**（此前短读长组装低估为 ~4 kb），LTR ~3,894 bp；Ttbtr1-Aa 与 Ttbtr1-Ab 位于来自 judaicum 的 ~140 Mb 渐渗片段上。

### 1.3 与平台现有 carthlicum（NU00021）的关系

| 项 | NU00021（平台已有） | CWI 22960（本论文） |
|---|---|---|
| 材料 | NU00021（IPK 泛基因组面板材料） | **CWI 22960**（CIMMYT 种质库登录号，1924 年采集自格鲁吉亚） |
| 来源论文 | Bian et al. 2026 *Nat Genet*（四倍体泛基因组，DOI 10.1038/s41588-026-02678-9） | Cavalet-Giorsa et al. 2026 *Commun Biol*（本论文） |
| 组装 | 泛基因组组装（10.497 Gb，14 条染色体 + scaffolds） | 染色体级 HiFi+Omni-C 组装（10.881 Gb，14 条染色体 + 10,708 scaffolds） |
| 注释 | **有**（`Genefunc_AABB_NU00021_table`） | **无** |
| 平台状态 | BLAST 17 库 / JBrowse / getfasta / 基因功能 / Synteny 均已上线 | 全无 |

**结论：CWI 22960 是新增的独立材料，不能"替换/更新" NU00021；两者可并存（同属 AABB 分区）。**

---

## 2. 平台现状核查（2026-11-08，只读）

| 检查 | 实测 | 结论 |
|---|---|---|
| `/api/genomes` 总数 / AABB 数 | 316 / 22 | AABB 分区 +1（→23） |
| CWI 22960 检索（`?q=22960`、`CWI`、`carthlicum`） | 0 命中；`CWI` 只命中 CWI86942/TaesCWI86942（六倍体，不同材料） | 平台确无 |
| `/api/blast/databases`（nuc 2,922 + prot 193） | `22960/carthlicum/dika` = 0；`AABB_NU00021.*` = 17 库 | 平台确无 |
| `/api/jbrowse/datasets`（219） | 无 22960 | 平台确无 |
| repo `jbrowse.html` 卡片（206 张命名卡） | 无 | 需新增卡片 |
| `cite.html` | 无该文引文 | 可选补充 |
| 论文数据声明与 ENA 实际 | 论文称 Omni-C reads 在 PRJEB101210，但 ENA 中 CWI22960 的 BioSample 只有 4 个 Revio 运行（PRJEB101209），**无 Omni-C/Hi-C 数据**；PRJEB101210 的 24 个运行是 Illumina WGS 面板材料 | ⚠️ 复现性提示，不影响平台接入 |
| 分类机制（`app/api/routers/blast.py`） | `_category_for()` 先查 `genome_registry`（ploidy AABB → `tetraploid_wheat`），再退回关键词 `DB_CLASSIFICATION`；四倍体关键词 = `wild_emmer, durum, langdon, triticum_timopheevii, triticum_turgidum, kronos, chili, mahmoudi, pi192051, pi94760` | `carthlicum/dika/turgidum(单)` 均**不是**关键词 |
| 收尾脚本 `finish_genome_integration.sh` | 不支持 genome-only：缺 `.add_Description.cds/.pep` 时直接 `die`；JBrowse 卡片步骤 grep 的是旧 `<h5>&#160;` 结构，现行页面（`app/static/docpages/jbrowse.html`，2026-10-27 V2.0 改版）已无此结构 | 阶段 A 需手工等价步骤 |
| Web BLAST 前端 | 现行入口 `/blast/blast.html` 是 wheatBLAST SPA，库清单与分类来自 `/api/blast/databases`（动态） | **无需手改 blast.html** |
| getfasta / PrimerServer2 / jbrowse_meta | 均动态扫描（API/DB 驱动） | 建库 + 重启 API 即可见 |
| 聚合库 | `all_genomes.nal` + `all_genomes_type.txt` 需追加成员 | 必需 |

---

## 3. 命名与分类方案（SOP §0.5）

材料身份：**账号 = CWI 22960**（CIMMYT 种质登录号，唯一权威身份；无栽培品种名）；无论文内部代号。

| 候选数据集名（`PLOIDY_MYTAG`） | `--check-name` | 说明 |
|---|---|---|
| **`AABB_Carthlicum_CWI22960`**（方案 A，推荐） | 需给 `carthlicum`/`dika` 加关键词后通过 | 名字直观、用户可按 carthlicum/dika/CWI 22960 检索；`Genefunc_…_table` = 39 字符（<64）；需 2 行代码 + 部署 |
| `AABB_Triticum_turgidum_CWI22960`（方案 B，零改动） | ✅ 命中 `triticum_turgidum` | 立刻过 gate，但名字长、语义差；表名 46 字符（<64，可接受） |
| `AABB_Durum_CWI22960` / `AABB_Wild_emmer_CWI22960` | ✅ 命中关键词 | **物种错误，禁止使用** |
| `AABB_CWI22960` / `AABB_Dika_CWI22960` | ❌ `other` → BLOCK | 无关键词 |
| `AABB_…CWI86942…` | ❌ 命中 `cwi86942` → **hexaploid_wheat** | 不要复用六倍体关键词 |

**推荐方案 A：**
- 数据集 / BLAST 库 / JBrowse 目录 / 表名 = `AABB_Carthlicum_CWI22960`；
- 前端显示名 = `Carthlicum wheat CWI 22960 (AABB)`（与 NU00021 的 "Persian wheat NU00021" 区分）；
- 代码改动：`app/api/routers/blast.py` 的 `DB_CLASSIFICATION` → `tetraploid_wheat.keywords` 追加 `"carthlicum", "dika"`（2 行，可复用；注意 hexaploid 关键词 `cwi86942` 不冲突）；
- 部署：commit → push → 服务器 `git pull` → `sudo systemctl restart wheatomics-api`（约 60–90 s 不可用）。

> 说明：注册表 `genome_registry` 行建好后，分类实际由 registry 的 ploidy 决定（NU00021 即如此），关键词只影响"registry 行存在之前"的窗口和 `--check-name` 门禁。为让名字更直观，仍建议加关键词。

---

## 4. 阶段 A —— 序列层上线（预计 4–6 h；本阶段即可交付）

> 目标：BLAST（核酸：整基因组 + 14 条染色体拆分库）+ JBrowse refseq + getfasta 聚合库 + PrimerServer2 `.fai` + `genome_registry` 元数据 + JBrowse 卡片/引文。**不建 CDS/PEP 库、不建基因功能表、不建 All genes/All proteins。**

### A0 预检与备份（0.2 h）

- 备份：`jbrowse.html`、`cite.html`、`all_genomes.nal`、`all_genomes_type.txt`、`genome_registry` 相关行（SQL dump）、`blast.html`（若需回滚）→ `backup_cwi22960_<时间戳>/`；
- 确认服务器：`/var/www/data/masw_data` 磁盘余量 ≥ 60 GB；`/var/www/html/getfasta/blastdb` 可写；`add_wheat_genome.sh` 版本（不用于本流程，仅供参照）。

**闸门 G0**：备份清单落盘，可回滚。

### A1 数据获取与归一化（0.5–1 h）

1. 下载 NCBI `GCA_977050835.1_CWI22960_genomic.fna.gz`（3,255,246,645 B），`md5sum` 核对 `4458e202c46347798298a5624f71c47b`；**不要**改用 ENA `CDRTBV01.fasta.gz`——它只有 unplaced scaffolds；
2. 建目录 `/var/www/data/masw_data/AABB_Carthlicum_CWI22960/`，解压为 `CWI22960.fa`（NCBI 头形如 `>OZ367120.1 Triticum turgidum genome assembly, chromosome: 1A`）；
3. **序列重命名**（用 `GCA_977050835.1_CWI22960_assembly_report.txt` 的 `Sequence-Name`↔`GenBank-Accn` 做映射）：
   - 染色体：`>OZ367120.1 … chromosome: 1A` → `>Chr1A`（14 条：Chr1A…Chr7B）；
   - 未定位：`>CDRTBV01… scaffold: scaffold_15` → `>ChrUn_scaffold_15`（10,708 条，**保留**，不许丢弃，见决策点 ③）；
   - 生成 `seqid_mapping.tsv`（旧头 → 新 refseq 名 → 长度）留档；
4. `samtools faidx CWI22960.fa`（14 条染色体 + 10,708 条 ChrUn，合计 10,881,024,180 bp）；
5. 写 `provenance.txt`：GCA/BioProject/BioSample、下载 URL、genomic.fna.gz md5、论文 DOI、接入日期、`name_plan.json`（`--check-name --write-plan --confirm` 生成，流水线门禁用）；
6. 轻量质检（genome-only 阶段**不跑** `check_genome_files.py`，它要求 `.fa/.gff3/.cds/.pep` 四件套）：`grep -c '^>'` = 10,722；所有头以 `Chr` 开头；`.fai` 行数 = 10,722；SUM(长度) = 10,881,024,180。

**闸门 G1**：md5 通过；14 条染色体长度与 assembly_report 一致；`.fai` 齐全；`name_plan.json` 就位。

### A2 核酸 BLAST 库（1.5–2 h，可后台）

```bash
export PATH=/var/www/html/blast/blast+/bin:$PATH
cd /var/www/data/masw_data/AABB_Carthlicum_CWI22960
# 整基因组库（10.88 Gb，makeblastdb 自动分卷 + .nal）
makeblastdb -in CWI22960.fa -dbtype nucl -parse_seqids -out /var/www/html/getfasta/blastdb/AABB_Carthlicum_CWI22960.genome
# 14 条染色体拆分库
for c in 1A 1B 2A 2B 3A 3B 4A 4B 5A 5B 6A 6B 7A 7B; do
  samtools faidx CWI22960.fa "Chr$c" > "Chr$c.fa"
  makeblastdb -in "Chr$c.fa" -dbtype nucl -parse_seqids \
    -out "/var/www/html/getfasta/blastdb/AABB_Carthlicum_CWI22960.genome_Chr$c"
done
# 软链到 BLAST 服务目录
cd /var/www/html/blast/db/nucleotide && ln -sf /var/www/html/getfasta/blastdb/AABB_Carthlicum_CWI22960.genome* .
```

- 产物：1 个整基因组库 + 14 个染色体库（**无** `.add_Description.cds/.pep`）；
- 预期 `blastdbcmd -info`：整基因组库 10,722 条序列、10,881,024,180 bp；染色体库各自条数/长度 = assembly_report。

**闸门 G2**：`blastdbcmd -info` 正常；`/api/blast/databases?program=blastn` 出现 15 个新库。

### A3 JBrowse（0.5–1 h）

```bash
cd /var/www/html/jbrowse-1.12.3-release
./bin/prepare-refseqs.pl --fasta /var/www/data/masw_data/AABB_Carthlicum_CWI22960/CWI22960.fa \
  --out AABB_Carthlicum_CWI22960
cd /var/www/FastAPI_backend_Port8000
set -a; . ./.env; set +a
/home/fei/mambaforge/envs/zjw/bin/python3 scripts/import_jbrowse_meta.py --dataset AABB_Carthlicum_CWI22960
```

- 两种收录口径（决策点 ③）：
  - **默认（SOP 一致）**：refseq = 14 条染色体 + 10,708 条 `ChrUn_*`（数量与 `.fai` 一致，未来注释若含 scaffold 基因也能显示）；
  - **精简**：只放 14 条染色体（`ChrUn_*` 仅进 BLAST/getfasta），JBrowse 下拉更轻，但 scaffold 上的序列不可浏览。
- `?data=AABB_Carthlicum_CWI22960` 200；`/api/jbrowse/datasets/AABB_Carthlicum_CWI22960/trackList` 200（仅 refseq，无轨道）。

### A4 getfasta 聚合库（0.2 h）

- 把 `AABB_Carthlicum_CWI22960.genome` 追加进 `all_genomes.nal`（聚合 alias 成员）；
- `all_genomes_type.txt` 追加行：`AABB_Carthlicum_CWI22960.genome<TAB>AABB`；
- 也可用 `scripts/rebuild_getfasta_aggregates.py --apply`（registry 驱动，默认 dry-run）自动重算，降低手误；
- 验证：`/api/sequence/chromosomes?database=all_genomes&pattern=CWI` 返回 14/10,722 条；`/api/sequence/by-interval?region=Chr3A:61200000-61200100&database=AABB_Carthlicum_CWI22960.genome` 返回 FASTA。

### A5 前端 / 元数据（0.3–0.5 h）

| 项 | 操作 |
|---|---|
| JBrowse 卡片 | 改 **repo** `app/static/docpages/jbrowse.html`：`<section id="group-aabb">` 的 `.asm-grid` 内加一张卡（模板同 NU00021 卡，`data-search` 含 `carthlicum/dika/cwi 22960/tetraploid/turgidum`、DOI 链接）；同步顶部统计：`213 assemblies → 214`、`206 named assemblies → 207`、chip `AABB … 22 → 23`、组标题 `22 assemblies → 23`；**不要直接改 docroot**，改完 `python3 scripts/deploy_doc_pages.py --only jbrowse`（自动备份，无需重启 Apache） |
| cite.html | 服务器 `/var/www/html/cite.html`（**不在 repo**）加引文块（附录 A 文本），改前备份；`rebuild_genome_registry.py` 会解析它填 `citation_text` |
| genome_registry | ① 跑 `scripts/rebuild_genome_registry.py` 生成基础行；② SQL 写回手动列（§4.1 表）；③ 在脚本 `overrides` 字典加一条（否则下次 rebuild 会把 `annotation_status` 覆盖回 `none`、`chromosome_count` 覆盖成 `.fai` 的 10,722） |
| 聚合库/flags | `getfasta_member`、`primerserver_fai`、`web_blast_group` 由脚本自动判定；`gene_table/gene_function_ui/synteny_entry/orthofinder_entry` 保持 0 |
| 重启 API | `sudo systemctl restart wheatomics-api`（BLAST 库清单缓存 1 h，必须重启才立即可见） |

**genome_registry 手动列（建议值）：**

| 列 | 值 |
|---|---|
| `species` | `Triticum turgidum L. ssp. carthlicum (Nevski) A. Love & D. Love` |
| `ploidy` / `subgenomes` | `AABB` / `A,B` |
| `cultivar_or_line` / `sample_id` | `CWI 22960` / `CWI 22960` |
| `common_name` | `dika wheat`（NCBI sample comment：Dika wheat；checklist 记 cone wheat） |
| `assembly_accession` | `GCA_977050835.1` |
| `assembly_level` / `chromosome_count` | `Chromosome` / `14`（**必须覆盖**，脚本会按 `.fai` 写成 10,722） |
| `genome_size` | `10881024180` |
| `te_content` / `gene_count` | `NULL` |
| `doi` / `journal` / `publication_year` | `10.1038/s42003-026-11303-8` / `Communications Biology` / `2026` |
| `paper_title` | `Tracing the origin of non-brittle rachis TtBTR1 alleles in wheat` |
| `source_url` / `source_md5` | NCBI datasets 页 / `4458e202c46347798298a5624f71c47b` |
| `annotation_status` | **`pending`**（写进 overrides，否则被 rebuild 覆盖） |
| `notes` | `GCA_977050835.1 (2026-10-07); 14 chr 10.395 Gb + 10,708 unplaced scaffolds 0.486 Gb; contig N50 40.14 Mb (paper: 42.6 Mb); no gene annotation (NCBI gene=0, no GFF in ENA/Zenodo); genome-only phase A <日期>` |

### A6 验收（0.3 h，见 §6）

**闸门 G3（阶段 A 完成）**：§6 的 1–9 项全过。

---

## 5. 阶段 B —— 注释上线（外部阻塞）

**现状：无 GFF 来源。**

- NCBI `feature_count`：gene/protein_coding = **0**；ENA portal 无 annotation 记录；
- Zenodo 21902085 只有 11 KB 代码包；GitHub `emilecg/btr_analysis` 为分析脚本；
- 论文 Methods 未做基因注释（分析依赖 k-mer、SNP、LTR 定年），补充材料只有组装统计表。

**可选路径：**

1. **向作者索取**（附录 B 邮件草稿）——推荐，作者为 KAUST Krattinger 组，论文 CC BY-NC-ND 4.0，需确认镜像许可；
2. 等 ENA/NCBI 更新该组装（若作者后续提交 GFF）；
3. **不推荐**：把 Svevo.v1（GCA_900231445.1，63,862 个蛋白编码基因）注释 liftover 过来——不同登录号、9.96 Gb vs 10.88 Gb，liftover 会大量丢失/错位；若确需临时注释，必须单独评估并标注 `annotation_source`。

**若拿到注释 →** 按 `genome-only-then-annotation-update.md` 阶段 B 一条命令增量上线：
   `annotation_update.sh <MYTAG> /var/www/data/masw_data/AABB_Carthlicum_CWI22960 AABB`
   （指纹核验 → `check_annotation_compat.py` → gffread CDS/PEP → EggNOG/Pfam → `Genefunc_AABB_Carthlicum_CWI22960_table` → 中国春 02G 映射 → `all_gene` 轨道 → `Genefunc_registry` → All genes/All proteins）

**闸门 G4**：`genome_fingerprint.txt` 一致 + 注释兼容性校验通过；否则禁止增量更新（不同组装版本不能混用注释）。

---

## 6. 验收标准（硬指标，阶段 A）

| # | 项 | 断言 |
|---|---|---|
| 1 | genome_registry | `/api/genomes/AABB_Carthlicum_CWI22960`：species/ploidy=AABB/subgenomes=A,B/assembly_accession=GCA_977050835.1/assembly_level=Chromosome/genome_size=10881024180/doi/journal/year 齐全，`annotation_status=pending`，`visible=1` |
| 2 | BLAST 库 | `blastdbcmd -info` 整基因组库 10,722 seqs / 10,881,024,180 bp；14 个染色体库正常；`/api/blast/databases` 分类 `tetraploid_wheat` +15 |
| 3 | Web BLAST | SPA 下拉可见 `AABB_Carthlicum_CWI22960.genome` 及 14 条染色体库；提交一条 3A 区域靶序列（Ttbtr1-A 附近）能出结果 |
| 4 | JBrowse | `/api/jbrowse/datasets/AABB_Carthlicum_CWI22960` 存在；`?data=AABB_Carthlicum_CWI22960` 200；refseq 数 = 14（精简）或 10,722（默认） |
| 5 | getfasta | `/api/sequence/chromosomes?database=all_genomes&pattern=CWI` 命中；`by-interval` 对 Chr1A/Chr3A 正常返回 FASTA |
| 6 | PrimerServer2 | `/api/PrimerServer2/databases` 含该 genome 库，examples 非空；`/databases/<db>/sequences` 200 |
| 7 | 前端卡片 | `/jbrowse.html` 含该卡（AABB 分区计数 22→23、hero 213→214、named 206→207） |
| 8 | 引文 | `cite.html` 含该文引文块；`genome_registry.citation_text` 已填 |
| 9 | 回归 | NU00021 / Zavitan / Chinese Spring 的 BLAST、getfasta、JBrowse 正常；`/api/genomes/stats` AABB 22→23 |
| 10 | 明示无注释 | 卡片/notes 标注 "genome-only, gene models pending"；`gene_function_ui=0` 是预期，不视为缺陷 |

---

## 7. 风险与回滚

| 风险 | 概率/影响 | 对策 |
|---|---|---|
| 无基因注释被用户误读为"数据缺失" | 高/中 | 卡片 + registry notes 明示 genome-only；`annotation_status=pending` |
| JBrowse 收录 10,708 条 ChrUn → 下拉过长、prepare-refseqs 慢 | 中/中 | 决策点 ③ 可只放 14 条染色体；ChrUn 仅进 BLAST/getfasta |
| `genome_registry` rebuild 覆盖 `annotation_status=pending` 和 `chromosome_count=14` | 高/中 | 写入 `scripts/rebuild_genome_registry.py` 的 `overrides`（先例：JM229） |
| 分类窗口期（registry 行建成前）落 `other` | 中/低 | 命名方案 A：提前加 `carthlicum/dika` 关键词 |
| 生产 HTML 被后续 `deploy_doc_pages.py` 覆盖 | 中/中 | 改 repo 源文件再部署，不直接改 docroot |
| 下载/校验失败（今日 EBI/NCBI 访问偶发超时） | 中/低 | 断点续传 + md5；留 `provenance.txt` |
| 误建 CDS/PEP、All genes 等（无注释时不应有） | 低/高 | 明确跳过，`finish_genome_integration.sh` 的注释步骤不跑 |
| 磁盘（+45–55 GB） | 低/低 | A0 预检余量；可先只建整基因组库（跳过 14 拆分库）过渡 |
| API 重启 60–90 s 不可用 | 确定/低 | 低峰执行 |
| 论文统计（10,881,601,880 bp / contig N50 42.62 Mb / 11,269 contigs）与沉积版（10,881,024,180 / 40.14 Mb / 11,345）不一致 | 确定/低 | 平台以**沉积版**为准写入 notes，并注明论文 Supplementary Data 1 数值；14 条染色体长度两版一致（10,395,351,798 bp） |
| Omni-C 数据未公开（论文声明与实际不符） | 确定/低 | 不影响平台接入；在 `provenance.txt` 备注，不据此复现组装 |

**回滚（任一步失败）：**

1. 恢复 `jbrowse.html` / `cite.html` / `all_genomes.nal` / `all_genomes_type.txt` 备份；
2. 删除 `/var/www/html/getfasta/blastdb/AABB_Carthlicum_CWI22960.genome*` 与 `/var/www/html/blast/db/nucleotide/` 软链；
3. 删除 JBrowse 目录 `AABB_Carthlicum_CWI22960/`（含 `seq/`），重跑 `import_jbrowse_meta.py` 或恢复 jbrowse_meta；
4. 删除 `genome_registry` 行（或恢复 SQL dump）；
5. 如需：`sudo systemctl restart wheatomics-api`。

---

## 8. 时间与资源

| 阶段 | 内容 | 预计 |
|---|---|---|
| A0 | 备份 + 预检 | 0.2 h |
| A1 | 下载 + 归一化（14 染色体 + 10,708 ChrUn） | 0.5–1 h |
| A2 | 核酸 BLAST（整基因组 + 14 拆分库） | 1.5–2 h（后台） |
| A3 | JBrowse refseq + jbrowse_meta | 0.5–1 h |
| A4 | getfasta 聚合库 | 0.2 h |
| A5 | 卡片/引文/registry/重启 | 0.3–0.5 h |
| A6 | 验收 | 0.3 h |
| **合计** | | **4–6 h**（后台约 3–4 h） |

磁盘粗算：`fna.gz` 3.26 GB + `fa` 10.9 GB + BLAST 库（整基因组 ~11 GB + 14 拆分库 ~10.4 GB）+ JBrowse refseq ~10.9 GB ≈ **+45–55 GB**；`/var/www` 当前余量按 Sumai3 计划记录约 31 T，充裕。

---

## 9. 待确认事项（决策点）

1. **是否现在做？**
   - A. 现在做阶段 A（序列层），注释 `pending`（**推荐**，若希望 CWI 22960 可 BLAST/可浏览）；
   - B. 只做元数据 + 卡片 + 引文（不建 BLAST/JBrowse，1 h 内）；
   - C. 暂缓，等作者提供 GFF 再整体上线（平台已有 NU00021，短期不影响 carthlicum 覆盖）。
2. **命名方案**：A. `AABB_Carthlicum_CWI22960` + 加关键词（推荐）；B. `AABB_Triticum_turgidum_CWI22960`（零代码）。
3. **unplaced scaffolds（10,708 条 / 486 Mb）**：
   - A. 全部收录（JBrowse 10,722 refseq，SOP 一致，推荐）；
   - B. JBrowse 只放 14 条染色体，`ChrUn_*` 仅进 BLAST/getfasta（下拉轻，scaffold 不可浏览）。
4. **执行授权**：是否授权我在你确认后直接操作生产服务器（SSH + 备份 + 重启 API）；`cite.html` / 首页公告是否同步。
5. **可选后续（不在本计划内）**：平台已知基因库**查无 TtBTR1/TtBtr1**（`/api/genes/known/search?searchid=BTR1` = 0）；若要把本文三个等位（Ttbtr1-Aa 2 bp 缺失 / Ttbtr1-Ab 5,029 bp 插入 / Ttbtr1-B 11.97 kb 插入）与定年结果补进已知基因模块，建议按 `wheat-known-gene-curation` 流程另立任务。

---

## 附录 A：论文 / 数据源 / 引文

- 论文：Cavalet-Giorsa, E., Wicker, T., & Krattinger, S. G. (2026). Tracing the origin of non-brittle rachis TtBTR1 alleles in wheat. *Communications Biology*. https://doi.org/10.1038/s42003-026-11303-8
- 组装：**GCA_977050835.1**（NCBI/ENA），assembly name `CWI22960`，WGS `CDRTBV01`，BioProject **PRJEB101210**，BioSample **SAMEA120412366**，2026-10-07 发布，Chromosome level，14 条染色体
- HiFi reads：**PRJEB101209**（4 个 Revio 运行，364.62 Gb）；24 份重测序：PRJEB101210（24 个 Illumina NovaSeq X WGS 运行）
- 论文补充材料：Supplementary Data 1（组装统计：10,881,601,880 bp、contig N50 42,620,968、BUSCO 98.5%、无基因数）；Supplementary Data 2–9（样本/k-mer/LTR 等）
- ⚠️ 论文 Data availability 称 Omni-C reads 在 PRJEB101210，但 ENA 实际无 CWI 22960 的 Omni-C/Hi-C 运行
- 最近可参考注释：Svevo.v1 **GCA_900231445.1**（63,862 个蛋白编码基因，`*_genomic.gff.gz` 可用；与 CWI 22960 不同组装）
- 代码：https://github.com/emilecg/btr_analysis（MIT）；Zenodo 10.5281/zenodo.21902084
- 通讯作者：Simon G. Krattinger（KAUST，`simon.krattinger@kaust.edu.sa`）；第一作者 Emile Cavalet-Giorsa（KAUST）
- 平台证据：
  - `https://wheatomics.sdau.edu.cn/api/genomes?q=CWI`、`?q=carthlicum`、`?q=22960`
  - `https://wheatomics.sdau.edu.cn/api/blast/databases`（3,115 库，0 命中 22960）
  - `https://wheatomics.sdau.edu.cn/api/jbrowse/datasets`（219 数据集）
  - NCBI：`https://www.ncbi.nlm.nih.gov/datasets/genome/GCA_977050835.1/`；FTP 目录 `https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/977/050/835/GCA_977050835.1_CWI22960/`

## 附录 B：GFF 索取邮件草稿（英文，待你确认后发送）

> Subject: Request for CWI 22960 (dika wheat) genome annotation for WheatOmics integration
>
> Dear Dr. Krattinger,
>
> We are the WheatOmics team (https://wheatomics.sdau.edu.cn), a public wheat multi-omics platform integrating genome assemblies with BLAST, JBrowse, gene-function and primer-design modules.
>
> We have followed your *Communications Biology* paper (DOI 10.1038/s42003-026-11303-8) and would like to integrate the new CWI 22960 assembly (GCA_977050835.1, 14 pseudomolecules, 10,881,024,180 bp) at the sequence level. Since the GenBank record contains no gene features, users will not be able to browse gene models or query TtBTR1 and the judaicum introgression region as annotated features.
>
> Could you share, if available:
> 1. the GFF3 of the gene set (gene/mRNA/exon/CDS), if the assembly was annotated;
> 2. CDS / protein FASTA (if generated);
> 3. the annotation version and the assembly coordinates it corresponds to (GCA_977050835.1?);
> 4. whether genes on the 10,708 unplaced scaffolds are included;
> 5. data-use / mirroring terms (the paper is CC BY-NC-ND 4.0) so that we can display the annotation with full citation and DOI link.
>
> We will cite the paper and link the DOI on every relevant page. We are also happy to host the assembly at the sequence level in the meantime and update it once an annotation becomes available.
>
> Best regards,
> [name / WheatOmics team]

## 附录 C：本次核查证据（只读）

- 论文 PDF（本地 `/Users/mashengwei/Downloads/s42003-026-11303-8_reference.pdf`）：Data availability、Methods（组装流程）、Results（10.88 Gb / contig N50 42.6 Mb / Ttbtr1 等位）
- ENA：`https://www.ebi.ac.uk/ena/browser/api/xml/PRJEB101210`（public 2026-10-05）、`.../xml/GCA_977050835`（14 染色体、总长 10,881,024,180、N50 755,996,689、CDRTBV01）、`.../filereport?accession=PRJEB101210&result=assembly`（GCA_977050835）
- NCBI FTP：`GCA_977050835.1_CWI22960_assembly_report.txt`（14 染色体 + 10,708 unplaced，长度表）、`assembly_stats.txt`、`feature_count.txt`（gene 0）、`md5checksums.txt`
- Zenodo：`https://zenodo.org/api/records/21902085`（btr_analysis v1.0，单文件 11,040 B）
- 平台：`/api/genomes`（316；AABB 22）、`/api/genomes/NU00021`、`/api/blast/databases`（nuc 2,922 + prot 193；NU00021 17 库；0 命中 22960）、`/api/jbrowse/datasets`（219）、`/api/genes/known/search?searchid=BTR1`（0）
- repo：`app/api/routers/blast.py`（`DB_CLASSIFICATION` / `_category_for` / `_registry_category`）、`app/static/docpages/jbrowse.html`（`group-aabb`，213/206/22/22 计数）、`scripts/deploy_doc_pages.py`、`scripts/rebuild_genome_registry.py`（overrides / preserve_fields）、`scripts/rebuild_getfasta_aggregates.py`、`~/.agents/skills/lab-server/scripts/finish_genome_integration.sh`（无 --genome-only）

---

## 进展记录：自行补注释（2026-11-09，Ma）

> 作者未提供 GFF，改由平台侧用 **EGAPx 1.0.1** 自行注释；证据使用 NU00021（同亚种 carthlicum）的 RNA-seq + IsoSeq（GSA CRA029005）。

**输入（均已校验）**
- 基因组：`GCA_977050835.1` → `CWI22960.fa`（10,722 seqs / 10,881,024,180 bp；`Chr1A..Chr7B` + `ChrUn_scaffold_*`；md5 `4458e202c46347798298a5624f71c47b`）
- RNA-seq：NU00021 Leaf/Root/Stem（CRR2096842/43/44，6 个 fastq，md5 与 GSA 一致）
- IsoSeq：NU00021 FLNC BAM（CRR2096857，md5 `3e5cf3df2313f7c7f8ff4a43bee655cd`）+ FLNC fastq（md5 `8dade19e3a63324376d93b80f023b1a1`）
- 工作区：`/data/masw_data/CWI22960_20261108/`（`STATUS.md`、`scripts/`、`logs/`）

**已交付：JBrowse 用 RNA-seq bigWig（CPM，binSize 50，染色体名与平台一致）**
- `bw/CWI22960_RNAseq_Leaf_CPM.bw`（CRR2096842）
- `bw/CWI22960_RNAseq_Root_CPM.bw`（CRR2096843）
- `bw/CWI22960_RNAseq_Stem_CPM.bw`（CRR2096844）
- `bw/CWI22960_RNAseq_All_CPM.bw`（三组织合并）
- 来源：EGAPx 内部 STAR 比对 → `samtools reheader` 去 `lcl|` 前缀 → CSI 索引 → deeptools bamCoverage；BAM 保留在 `align/bams/`
- 本地副本：仓库 `cwi22960_release/`（md5 与 Ma 一致）

**进行中：EGAPx 注释**
- 2026-11-09 00:44 启动（Nextflow 24.10.4 + singularity SIF）
- 当前进度：>217 tasks 完成、0 失败；卡在长读 IsoSeq minimap2（14 分块中 11 完成、3 运行），之后 rnaseq_collapse → gnomon 基因预测 → 最终 GFF3
- 预计 2–3 天出注释产物；随后执行 `scripts/finalize_annotation.sh`（去 `lcl|` 前缀、mRNA ID 归一化 `.数字`、gffread 生成 CDS/PEP、统计）
- 平台接入仍按本计划 §4 Phase A/B 执行；注释层直接从 EGAPx 产物导入（不再依赖作者 GFF）

## ✅ 注释完成（2026-11-10 23:02，EGAPx 1.0.1）

- 流程跑通：Nextflow "Execution complete -- Goodbye"，340 tasks COMPLETED（早期 24 个 FAILED 均为修复前手工 kill 的 chainer 任务，重试后全部成功，不影响产物）
- 关键修复：`support/gnomon/2/hmm_parameters/4565.params` 在支持数据下载时被截断（staged 6,523,240 B vs 完整 6,983,203 B），导致 gnomon chainer_wnode 空转（CPU 0、无输出）。用完整文件替换后 chainer 立即满负荷运行
- 统计：基因 113,393（protein_coding 79,049 / pseudogene 28,652 / ncRNA 5,692）；mRNA 94,509；外显子 652,934；CDS 467,141
- BUSCO（poales_odb10, protein mode）：C 99.1% [S 9.6%, D 89.5%]，F 0.0%，M 0.9%（duplication 高符合 AABB 同源基因预期）
- 平台规范化产物（`cwi22960_release/annotation/`）：`CWI22960_EGAPx.platform.gff3`（基因 `CWI22960_XXXXXX`、转录本 `CWI22960_XXXXXX.k`）、`CWI22960_EGAPx.cds.fna`、`CWI22960_EGAPx.pep.faa`、`README_ANNOTATION.md`
- JBrowse bigWig（此前已交付）：`cwi22960_release/CWI22960_RNAseq_{Leaf,Root,Stem,All}_CPM.bw`
