# WORKFLOW_GAP — 4 个二倍体 Aegilops 二倍体基因组上线：SOP 审阅 + 可执行清单 + 差距/阻塞

> **任务**：共享任务板 `task-3`（owner: workflow-gap）。把 WheatOmics「新基因组上线 SOP」审成*这 4 个基因组可直接照做*的清单，并标出差距/阻塞。
> **日期**：2026-11-11 ｜ **约束**：只读仓库，不改源码、不 git commit、不写生产数据；本文是 task-3 唯一产出。
> **配套（同任务组已交付，事实以其为准，本文不重复论证）**：
> - `docs/plans/aegilops4_2026-11/PAPER_DATA.md`（论文/Zenodo/NCBI 数据事实，task-1）
> - `docs/plans/aegilops4_2026-11/PLATFORM_BASELINE.md`（线上平台/仓库代码接入点，task-2）
> - `Aegilops4_diploid_genome_update_plan.md`（Lead 的总计划）
> **依据文件**：`~/.agents/skills/lab-server/references/wheatomics-new-genome-sop.md`（SOP，474 行）、`genome-only-then-annotation-update.md`、`~/.agents/skills/lab-server/scripts/finish_genome_integration.sh`（1022 行，md5 `e4886d0c21f1667be5e672e330ba75d7`）；生产脚本副本 `/tmp/wm_server/`（Lead 拷回）：`add_wheat_genome.sh`（1034 行，**md5 `70fb9ff21ed11417399f16fb489b1ad3`**）、`normalize_gff2.py`、`normalize2.sh`、`check_genome_files.py`（md5 `d774445172714d0d6b9127d4a21cc2a0`）、`annotation_update.sh`。

---

## 0. 结论先行（能否直接照 SOP 做？）

**结论：可以做，但「标准 SOP 原样照抄」会在 3 处 BLOCK/FAIL，必须先改 5 个文件 + 1 个前端页面；数据侧无硬阻塞（FASTA 在 NCBI，Zenodo 只有注释）。**

| 判定项 | 结论 | 依据/处置 |
|---|---|---|
| 4 个基因组是否同批做 | 可以，4 个都是 **7 条假染色体 + 少量 unplaced scaffold**，规模 3.58–4.48 Gb（合计 **16.73 Gb**） | §2 表；PAPER_DATA §4 |
| 基因组 FASTA | **可得，不是阻塞**：4 个 GCA 已定位（NCBI FTP，含 md5） | §2 表；G1 下载命令 |
| 注释四件套 | Zenodo 只有 gene GFF3(H C/LC) + protein FASTA + TE GFF3，**无 CDS** → 用 `gffread` 从「NCBI FASTA+GFF」生成；已端到端验过 17 个位点翻译 100% 一致 | PAPER_DATA §5.6 |
| 命名门禁 `--check-name` | **现在跑必 BLOCK**（step 3 旧 `blast.html` optgroup；CC/NN 还 BLOCK step 1/2） | §3.3 / §6-G1 |
| 流水线 `add_wheat_genome.sh` | 可跑；但生产版（70fb9ff2…）与 SOP 记录的 208f0653… **不同，SOP 已过期**，以生产副本为准 | §1.1 |
| 收尾 `finish_genome_integration.sh` | **现在跑必 FAIL**：step1/step2/验收项按旧页面（`<h5>`+`card-group` / ViroBLAST `<optgroup>`）写，线上已是 V2 docpage + wheatBLAST SPA | §1.3 / §3.4 |
| 二倍体 PLOIDY | MM/UU 已支持（有先例）；**CC/NN 缺 `SUB` 映射** → 必须改 2 行代码 | §3.2 |
| 与既有同物种条目 | **新增并存，不替换**（材料登录号/组装/DOI 均不同：M PI551049 vs IPK-AE783；U PI554389/TA1851 vs IPK-AE740） | §2.3 |
| 工作量（估算） | 磁盘 **+约 100–120 GB**（25–30 GB/个）；流水线 **25–45 min/个**，4 个顺序跑 **2–4 h**；全体人时约 10–14 h；API 重启 **1–2 次** | §6 |

---

## 1. 标准流程回顾（五阶段 / 产物 / 闸门 / 耗时）

**阶段图（一页版）**

```
G0 命名门禁 ──> G1 四件套归一化 ──> G2 官方质检 rc=0 ──> G3 流水线 10 步 ──> G4 收尾 10 项 ──> G5 验收
 --check-name     .fa/.gff3/.cds/.pep    check_genome_files.py   add_wheat_genome.sh   finish_genome_integration.sh   公网/API/回归
 --write-plan     + provenance/md5       （缺一不可）           （后台 setsid）        （自动备份 + 幂等）              stats/alias/映射
```

### 1.1 阶段表

| # | 阶段 | 关键命令/产物 | 闸门（必须过） | 历史耗时（先例） |
|---|---|---|---|---|
| **G0** | 命名/分类预检 + `name_plan.json` | `finish_genome_integration.sh <PLOIDY> <MYTAG> <DOI> --check-name [--write-plan --confirm] --cultivar … --accession …` → `<data_dir>/name_plan.json` | 材料身份齐备；`SUB[PLOIDY]` 有映射；`DB_CLASSIFICATION` 三库名分类不是 `other`；JBrowse 分区/optgroup 存在；`display_order` 记录 | 2–5 min |
| **G1** | 输入归一化（四件套 + provenance） | `<data_dir>/${MYTAG}.fa/.gff3/.cds/.pep`；`provenance.txt`；`seqid_mapping.tsv` | FASTA 头全 `Chr`；GFF 第 1 列 ⊆ FASTA；mRNA `ID=` 以 `.数字` 结尾；CDS/PEP ID 以 `.数字` 结尾；pep 序列行无 `.` | 归一化 PT 实测 ~7 min（六倍体 172 序列） |
| **G2** | 官方质检 | `python3 /var/www/html/Script/check_genome_files.py ${MYTAG}`（Step 0 会再查） | **rc=0**「所有文件均通过检查！」；注意会清理 pep `.` 并留 `.pep.bak` | 1–3 min |
| **G3** | 流水线 10 步 | `bash add_wheat_genome.sh ${MYTAG} /var/www/data/masw_data/${PLOIDY}_${MYTAG} ${PLOIDY}`（命名门禁校验 `name_plan.json`；`setsid --fork` 后台 + 日志） | 日志末尾 `[SUCCESS] ${MYTAG} 全部完成`；产物齐全（见 §1.2） | **PT 1h23**（13.9 Gb / 215,294 mRNA；EggNOG ~20 min、miniprot ~17 min）；CWI 22960 genome-only 估 4–6 h；**本批 25–45 min/个** |
| **G4** | 收尾 10 项 | `finish_genome_integration.sh ${PLOIDY} ${MYTAG} <DOI> [--dry-run]`（自动读 plan；备份到 `backup_<时间戳>/`） | 10 项验收全 `[OK]`；`/api/blast/databases` 分类正确；`blast_jbrowse_map.json` 含 `assembly_match=true` | 先例 5–10 min/个（本批需先 patch，见 §3.4） |
| **G5** | 验收/公网核验 | `/api/genomes/stats`、`/api/blast/databases`、`/api/jbrowse/datasets`、`/api/sequence/*`、`/api/PrimerServer2/databases`、`/api/jbrowse/coverage`；旧条目回归 | 断言见 §5；旧条目（PI551049/PI554389/TA1851 等）无回归 | 0.3–0.5 h（本批 4 个合计 1–2 h） |

### 1.2 `add_wheat_genome.sh`（生产版 70fb9ff2…，1034 行）实际 10 步

| Step | 动作 | 关键产物 |
|---|---|---|
| 0 | 内容质检 `check_genome_files.py ${MYTAG}` | rc=0 |
| 1 | 校验 FASTA 头/GFF seqid + 标准化头 `>{sid} {MYTAG} {PLOIDY} {chrom}` | `${PLOIDY}_${MYTAG}.genome`（**长名**，如 `Chr1M_MM_Aegilops_comosa_IPK_AE783`；`ChrUn_*` 原样保留不加后缀） |
| 2 | 按染色体拆分（`/var/www/html/Script/split_fasta_by_chrom.py`） | `${PLOIDY}_${MYTAG}.genome_Chr*`（**只拆 Chr+数字，ChrUn 不拆**） |
| 3 | 拷 genome 到 `/var/www/html/getfasta/blastdb/` | 主 genome 文件 |
| 4 | `makeblastdb` 核酸库（7 拆分库 + 整基因组库多卷 `.nal`） | `${DS}.genome*`、`${DS}.genome_Chr*` |
| 5 | 软链到 `/var/www/html/blast/db/nucleotide/` | — |
| 6a | 建 JBrowse 目录 `${PLOIDY}_${MYTAG}` | 空目录 |
| 7.1 | EggNOG emapper（`conda activate eggnog`，diamond，`--cpu 12 --num_servers 3 --num_workers 4 --dbmem`） | `${DS}_annotation.emapper.annotations` |
| 7.2 | jcvi GFF→BED + EggNOG/Pfam 注释 | `${DS}_with_annotation.bed` |
| 7.2.1 | `/var/www/cgi-bin/register_genome.n.py` 注册 MySQL | `Genefunc_${DS}_table` |
| 7.3 | `add_eggnogand02G_to_gff_cds.py`（miniprot `--threads 50`，CS1.0 mpi + IWGSC v1.1 GFF） | `${DS}.add_eggnog_ChineseSpring02G.gff3`、`.add_Description.cds/.pep` |
| 7.3.1/7.4/7.5 | 拷 CDS/PEP + makeblastdb（nucl/prot）+ 软链 | `${DS}.add_Description.cds/.pep*` |
| 7.6 | `flatfile-to-json.pl --trackLabel all_gene --type mRNA --nameAttributes ID` | JBrowse `trackList.json` + gene 轨道 |
| 6b | `prepare-refseqs.pl`（读最终 GFF 判断用长名 genome 还是短名 `${MYTAG}.fa`） | `seq/refSeqs.json`（本批应为**短名** `Chr1M…`） |
| 8 | `generate-names.pl --tracks all_gene --hashBits 16` | 搜索索引 |
| 9 | BED 加 ChineseSpring02G（行数 <2 报错） | `${DS}_with_annotation_ChineseSpring02G.bed` |
| 10 | `import_jbrowse_meta.py --dataset ${DS}` + `rebuild_genome_registry.py` | `jbrowse_meta`、`genome_registry` 基础行 |
| — | 最终检查 + `[SUCCESS]` | 日志 |

### 1.3 `finish_genome_integration.sh`（1022 行）实际 10 项 + `--check-name`

| # | 项 | 说明/现状 |
|---|---|---|
| 1 | JBrowse 卡片 | **按旧页面写**（`<h5>&nbsp;` + `<div class="card-group">` + `<div id="cite"></div>` 锚点）；线上 V2 页面无这些结构 → 会 `[ERR] 找不到 <div id="cite"></div>` 并 FAIL |
| 2 | Web BLAST group / hidden input / All genes / All proteins | **按旧 ViroBLAST 写**（`<optgroup>`/`N..._chromosomes`/`Nall_genes`）；线上是 wheatBLAST SPA（库清单动态来自 `/api/blast/databases`）→ `[ERR] 找不到 optgroup` 并 FAIL |
| 3 | PrimerServer2 `.fai` | `samtools faidx` genome + cds（幂等） |
| 4 | `Genefunc_registry` upsert | `display_order = MAX(同 Polyploidy)+1`；`Group` 取 `--group`（默认按 PLOIDY：MM/CC/NN→`Other`，UU→`Diploid`） |
| 5 | 聚合库 alias + `all_genomes_type.txt` | `all_genomes.nal`/`all_gene.nal`/`all_protein.pal` DBLIST 追加 |
| 6 | `import_jbrowse_meta.py --dataset` | API trackList 数据源 |
| 7 | `rebuild_genome_registry.py` | 从 JBrowse/blastdb/Genefunc_registry/聚合库/卡片重建（**注意其 V2 兼容性见 §3.4**） |
| 8 | `genome_registry` 元数据写回 | DOI/标题/期刊/年份/物种/登录号/source_url/md5 + 派生事实（gene_count/annotation_status/gene_table/各 usage flag） |
| 9 | `build_blast_jbrowse_map.py` 重建 + `--check` | BLAST 命中跳 JBrowse；按**染色体长度**匹配（长短名不同也能匹配） |
| 10 | 验收（10+ 项） | BLAST 库/alias/MySQL/`.fai`/API/HTML/映射；其中 HTML 两项（§1.3 #1/#2）对本批会 FAIL |
| — | `--write-plan` / `--check-name` | 预检模式；见 §3.3（第 3/4 步按旧页面写，会 BLOCK） |

---

## 2. 本批次 4 个二倍体 Aegilops 的适配差异

### 2.1 数据事实（可直接引用；证据见 PAPER_DATA）

| 物种（基因组） | 登录号（材料） | PLOIDY | NCBI GCA | BioProject | 总长 (bp) | 序列数（7 染色体+unplaced） | contig N50 | Zenodo 注释（HC_LC mRNA） | 建议 DS |
|---|---|---|---|---|---|---|---|---|---|
| *Ae. comosa* (M) | IPK-AE783 | MM | GCA_052815735.2（ASM5281573v2） | PRJNA1506336 | 4,407,741,597 | 17（7+10） | 9,246,063 | 51,203 | `MM_Aegilops_comosa_IPK_AE783` |
| *Ae. markgrafii* (C) | EKC105_RL5723 | CC | GCA_052815875.1（ASM5281587v1） | PRJNA1174795 | 3,577,170,360 | 24（7+17） | 9,048,916 | 47,246 | `CC_Aegilops_markgrafii_EKC105_RL5723` |
| *Ae. umbellulata* (U) | IPK-AE740 | UU | GCA_060308565.1（AAFC_Aeum_AE740_v02） | PRJNA1114735 | 4,268,089,219 | 250（7+243） | 7,445,361 | 49,677 | `UU_Aegilops_umbellulata_IPK_AE740` |
| *Ae. uniaristata* (N) | IPK-AE680 | NN | GCA_052815765.1（ASM5281576v1） | PRJNA1154594 | 4,475,943,907 | 21（7+14） | 31,980,500 | 50,416 | `NN_Aegilops_uniaristata_IPK_AE680` |
| **合计** | | | | | **16,728,945,083** | **312** | | **198,542** | |

**FTP（G1 用）**：`https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/<xxx>/<yyy>/<zzz>/<zzz>_genomic.fna.gz`（`<zzz>` = `<GCA>_<ASM名>`）；`*_assembly_report.txt`、`md5checksums.txt` 同目录。`genomic.fna.gz` md5：comosa `38b8436f9c4eb360a066a1c79f1a122a`；markgrafii `2a55e0ca2d74109c63c84dcb6d6a077a`；umbellulata `1766c56e9ed9f2d6bcf292925a6628bb`；uniaristata `b9b855678d7beba1cdd58f7ed89123eb`（assembly_report md5 见 PAPER_DATA §4.1）。

### 2.2 与六倍体/四倍体常规新增的逐条差异

| # | 常规 SOP 假设 | 本批次实际 | 影响/处置 |
|---|---|---|---|
| D1 | 四件套现成（含 `.cds/.pep`） | Zenodo **无 CDS**，只有 gene GFF3 + protein FASTA | `gffread -g ${MYTAG}.fa -x … -y …` 生成；protein FASTA 只用于**交叉校验**（条数 + 抽样序列），不作流水线输入 |
| D2 | 基因组 FASTA 随注释一起给 | **Zenodo 无基因组 FASTA**；FASTA 在 NCBI GCA（4 个） | 不是硬阻塞；G1 下载 + md5 校验；SOP 的「genome-only 阻塞」不适用（本批注释齐全，走**完整四件套**流程，不是两阶段） |
| D3 | FASTA 头 = `Chr1A` 式 | NCBI FASTA 头第一 token 是 **GenBank/WGS 登录号**（`>CM127985.1 …`、`>JBHEGE020000008.1 …`） | 用 `assembly_report.txt` 第 1 列（Sequence-Name）↔ 第 5 列（GenBank-Accn）映射：7 条 chromosome → `Chr1M…Chr7M`；其余 → `ChrUn_<Sequence-Name>`；同时产出 `seqid_mapping.tsv` |
| D4 | GFF seqid = `Chr*` | GFF seqid 是 **`1M..7M` / `1C..7C` / `1U..7U` / `1N..7N`** + scaffold/contig（如 `scaffold_9`、`Super-Scaffold_…`、`ptg000155l`、`Super_scaffold_…`） | 归一化脚本必须同时处理「无 chr 前缀的 `1M`」和「scaffold→`ChrUn_*`」；**现有 `normalize_gff2.py` 只认 `^chr([1-7][ABR])$`，直接跑会把 `1M` 错改成 `ChrUn_1M`**（见 §3.1-Gap A） |
| D5 | mRNA ID 以 `.数字` 结尾 | **51,666 个 LC（TAMA/STRG 家族）mRNA ID 以 `.p1…p10` 结尾**（其中 6,401 个跨物种重名）；HC EVM / LC EVM 家族已合规 | 需 `\.p(\d+)$` → `.\1`（或追加 `.数字`），并**同步改 `ID=`/`Parent=`/`Derives_from=`** 及蛋白 FASTA 头（PAPER_DATA §5.3） |
| D6 | pep 干净 | 3 物种 pep 行尾是 `.`、umbellulata 是 `*`；comosa 还有 6,573 条含**内部终止符**（注释帧移，非提取错误） | `check_genome_files.py` 只清 `.`（会留 `.pep.bak`），**不清 `*`** → 归一化后需统一清行尾/内部 `*` 与 `.`；内部终止符记录到 provenance（不阻断，但 gffread 会告警 `In-frame STOP found`） |
| D7 | PLOIDY 双字母或已有 | **MM/UU 已有先例**（`MM_AeComosa_PI551049`、`UU_Aegilops_umbellulata_TA1851`）；**CC/NN 全新**：`rebuild_genome_registry.py` 的 `SUB` **缺 `CC/NN`** | 改 `SUB` 增 `"CC": "C", "NN": "N"`；否则 `--check-name` step 1 **BLOCK** |
| D8 | 分类关键词覆盖 | 现有 `other_triticeae` 关键词有 `aegilops_comosa`/`aegilops_umbellulata`/`aecomosa`，**无 markgrafii/uniaristata** | `app/api/routers/blast.py` `DB_CLASSIFICATION` 的 `other_triticeae.keywords` 追加 `"aegilops_markgrafii","aegilops_uniaristata","markgrafii","uniaristata"`（改后 `--check-name` step 2 通过；运行时 registry 行存在后分类由 ploidy 决定，仍为 `other_triticeae`） |
| D9 | `Group` 推导一致 | finish 脚本默认：`DD\|AA\|BB\|UU\|HH\|AABBCC→Diploid`，**`MM/CC/NN→Other`**（不一致）；线上旧 `blast.html` 已无 optgroup | 门禁绕过：`--group "Other Triticeae"`（不在 `gmap` → 不检查 optgroup；同时与既有 `Other Triticeae` 两行一致）；根治：patch 脚本 + 新页面（§3.4） |
| D10 | 收尾脚本适配生产页面 | step1/step2/验收按**旧页面**写；线上已是 `app/static/docpages/jbrowse.html` V2（`.asm-card`/`.asm-group`/`.asm-grid`）+ `app/static/blast2/index.html` SPA（无 optgroup） | **G0 前必改 finish 脚本**（或 G4 改为手工 8 步 + 手工 V2 卡片）；否则 `--check-name` step 3 必 BLOCK、G4 step1/2 + 验收项必 FAIL |
| D11 | `rebuild_genome_registry.py` 能解析页面 | 其 `CARD_RE` 是 `<div class="card-body">`（旧卡片）；`BLAST_HTML` 仍是 `/var/www/html/blast/blast.html` —— V2 改版后**卡片解析返回空、`web_blast_group` 判 0** | 新行四件套靠 finish step 8 元数据写回兜底（`web_blast_group=1` 等）；或给 rebuild 脚本加 V2 解析/override（建议，见 §3.4） |
| D12 | JBrowse 分区/前端 | MM/UU 分区已存在（`#group-mm`、`#group-uu`）；**CC/NN 无分区** | 改 repo `app/static/docpages/jbrowse.html`：MM/UU 各加 1 卡，新建 `#group-cc`/`#group-nn`；同步 hero 计数（213→217、206→210、22 groups→24）与 group-count |
| D13 | Web BLAST 前端手改 | 现行 SPA 动态读 `/api/blast/databases`，**无需改 blast.html** | 旧 SOP §5.2 的 option/hidden input 全部作废；分类由 `DB_CLASSIFICATION` 代码 + registry 决定 |
| D14 | TE 轨道 seqid 与基因一致 | 4 个 TE GFF 来自 EDTA v2.2.1，seqid 各物种不同：**comosa 裸数字 `1..7` + 数字 token；markgrafii 与基因 GFF 一致；umbellulata/uniaristata 用缩写 `S_S_*`** | TE 轨道另行映射（以 `assembly_report` + 基因归一化映射表为准；umbellulata 的 `S_S_73_2` 在 NCBI 提交中不存在，仅 1 条特征，丢弃并记录） |
| D15 | 与既有条目「替换/升级」 | 4 个均为**新组装、新材料登录号**（M/U 与既有 PI 条目不同；C/N 为该物种种首染色体级组装） | **新增并存**：旧条目、旧 BLAST 库、旧卡片一律保留；聚合库追加 4 个成员；registry 同 ploidy 多行（先例：DD 10 条、UU 2 条） |
| D16 | 表名/库名长度安全 | 推荐 DS 的 `Genefunc_<DS>_table` 实测：MM **43**、CC **51**、UU/NN **48** 字符（MySQL 上限 64）；BLAST 库名最长 `…add_Description.cds` 55 字符 | 安全；**不要用 `IPK-AE783`（连字符）作 MYTAG**（MySQL 未加反引号的标识符会报错），统一 `IPK_AE783` 下划线形式 |
| D17 | 流水线拆分库数 | `split_fasta_by_chrom.py` 只拆 `Chr+数字`，**ChrUn 不拆**（SOP 已知坑 #5） | 每基因组 **7 个染色体拆分库 + 1 个整基因组库**；正常 BLAST/前端行为；ChrUn 只进整基因组库/JBrowse refseq |
| D18 | 脚本版本 | 生产 `add_wheat_genome.sh` md5 `70fb9ff2…`（1034 行）≠ SOP 记录 `208f0653…`；`finish_genome_integration.sh` md5 `e4886d0c…` 与技能副本一致 | 以 `/tmp/wm_server/` 副本为准；SOP 的 §5.1/§5.2（旧页面）与脚本版本描述已过期 |

### 2.3 与平台既有 Aegilops 条目关系（只读 API 实测）

| 物种 | 既有条目 | 本批新条目 | 结论 |
|---|---|---|---|
| *Ae. comosa* | `Aegilop_comosa_PI551049`（MM，annotation none，BLAST/JBrowse 在） | `MM_Aegilops_comosa_IPK_AE783` | **并存**（不同登录号/组装/DOI） |
| *Ae. umbellulata* | `Aegilops_umbellulata_PI554389`（none）、`…_TA1851`（available） | `UU_Aegilops_umbellulata_IPK_AE740` | **并存**；UU 分区将变 3 卡 |
| *Ae. markgrafii* | 无 | `CC_Aegilops_markgrafii_EKC105_RL5723` | 新增（首条） |
| *Ae. uniaristata* | 无 | `NN_Aegilops_uniaristata_IPK_AE680` | 新增（首条） |

> 平台分类先例（2026-11-11 实测 `/api/blast/databases`）：`MM_AeComosa_*`/`UU_Aegilops_umbellulata_*`/`SS_*`/`TT_*`/`MMUU_*` 全部落 **`other_triticeae`（Other Triticeae genome）**，本批 4 个按同口径处理，**不新建分类、不改 diploid_wheat**。

---

## 3. 代码/脚本差距清单（G0 前置改动）

### 3.1 Gap A — 归一化脚本只认 A/B/R（必改）

`normalize_gff2.py`（md5 `c7b1b3a9280dc839537bede8d5db5dda`）：

```python
CHROM = re.compile(r'^chr([1-7][ABR])$')      # ← 只认 chr1A..7A / 1B..7B / 1R..7R
```

`normalize2.sh`（md5 `f5133f22ae9186a80505263dcddf7f1e`）同样：`/^chr[1-7][ABR]$/`，且 `for MYTAG in PT ZX830` 循环写死、输入写死 `Aegilops4_...` 无关的 `${MYTAG}.chr.fa.gz`/`${MYTAG}.gene.gff`。

**改法（最小）**：

```python
# normalize_gff2.py
CHROM = re.compile(r'^(?:chr)?([1-7])([A-Za-z])$', re.I)
def seqid_new(seqid):
    m = CHROM.match(seqid)
    if m:
        return 'Chr%s%s' % (m.group(1), m.group(2).upper())
    if seqid.startswith('ChrUn_'):
        return seqid
    return 'ChrUn_' + seqid
```

并把 mRNA 规则改为：`\.p(\d+)$` → `.\1`（不足 `.数字` 时再追加 `.1`），改写 `ID=`/`Parent=`/`Derives_from=`（现有 `build_rename/rewrite_attrs` 已可复用）。`normalize2.sh` 建议参数化为 `normalize2.sh <MYTAG> <data_dir> <PLOIDY> <raw_fa_gz> <raw_gff>`，或直接写一次性 `aegilops4_normalize.py`（推荐：**一次脚本 + 4 组参数**，避免改 PT/ZX830 历史行为）。

### 3.2 Gap B — 二倍体 CC/NN 的 SUB 映射缺失（必改 2 行）

`scripts/rebuild_genome_registry.py` 的 `SUB`（第 586 行附近）现为：
`{"AABBDD":…,"AABB":…,"AA":"A","DD":"D","HH":"H","SS":"S","TT":"T","MM":"M","AAGG":…,"DDNN":"D,N",…,"UU":"U",…}` → **缺 CC/NN**。
改：`"CC": "C", "NN": "N"`。不改则 `--check-name` step 1 直接 BLOCK（`ploidy 'CC' 不在 SUB 映射里`）。

### 3.3 Gap C — 分类关键词缺 markgrafii/uniaristata（必改 2–4 行）

`app/api/routers/blast.py` `DB_CLASSIFICATION` → `other_triticeae.keywords` 追加：
`"aegilops_markgrafii", "aegilops_uniaristata", "markgrafii", "uniaristata"`。
注意：`aggregated` 关键词含 `all_`，新库名不得含 `all_`；关键词匹配顺序为 `aggregated → hexaploid → tetraploid → diploid → triticale → thinopyrum → rye → other_triticeae`。

### 3.4 Gap D — `finish_genome_integration.sh` 与生产页面结构性错配（必改或改流程）

**现状**（均已实测）：线上 `/jbrowse.html` = V2（`asm-card`/`asm-group`，无 `<h5>`/`card-group`/`<div id="cite">`）；线上 `/blast/blast.html` = wheatBLAST SPA（`<optgroup>` 数量 **0**）。因此：
- `--check-name` step 3（optgroup）→ **任何基因组必 BLOCK**（绕过：`--group "Other Triticeae"`）；
- step 4 若给 `--section-existing` → BLOCK（V2 无 `<h5>` 分区；不给则只 WARN，可过）；
- 正式运行 step1（卡片）→ `[ERR] 找不到 <div id="cite"></div>`；step2（optgroup）→ `[ERR]`；验收 grep `blast.html` 两项 → `[FAIL]`。

**推荐 patch（P1，约 80–120 行）**：
1. 页面模式探测：`grep -q 'asm-card' "$JBROWSE_HTML"` → `PAGE_MODE=v2`；
2. `step_jbrowse_card` v2 分支：在 `#group-<ploidy 小写>` 的 `.asm-grid` 末尾插入
   `<article class="asm-card" data-search="… ds … doi:…"><h3 class="asm-name"><a href="/jbrowse-1.12.3-release/?data=${DS}">${LABEL}</a></h3><p class="asm-doi"><a href="https://doi.org/${DOI}">doi:${DOI}</a></p></article>`；
   分区不存在则新建 `<section class="asm-group" id="group-xx">…`；同时更新 hero `213→217`、status `206→210 / 22→24`、对应 `asm-group-count`；
3. `step_blast_html` v2 分支：**跳过**（SPA 动态），改为在验收中断言 `/api/blast/databases` 含 `${DS}` 且分类 = `--expect-category`；
4. `verify()`：把两处 HTML grep 换成 API/registry 断言；保留 `/api/jbrowse/datasets`、`/api/sequence/by-interval`、registry、映射、coverage 检查。
   （或者 G4 完全手工：见 §4.6；但每次 4 个基因组手工成本高，建议 patch。）
5. 页面源文件在 repo `app/static/docpages/jbrowse.html`，改完 `python3 scripts/deploy_doc_pages.py --only jbrowse` 发布（docroot 权限不足时脚本会提示 `[needs-sudo]`，需 `sudo cp`；不改 Apache）。

**另建议（P2，非阻塞）**：给 `rebuild_genome_registry.py` 加 V2 卡片解析（`<article class="asm-card">` + `data-search` + `?data=`）与 `web_blast_group` 新判定（有 `.genome` BLAST 库即 1，或走 override）；否则新行 `web_blast_group/citation` 等只能靠 finish 元数据写回。

### 3.5 其它待核查（不改代码但影响可执行性）

| 项 | 为什么重要 | 核查命令（服务器） |
|---|---|---|
| `split_fasta_by_chrom.py` 是否认 `Chr1M/1C/1U/1N` | 只拆 `Chr+数字`；PT 的 `Chr1A` 可拆，字母 M/C/U/N 需确认 | `head -80 /var/www/html/Script/split_fasta_by_chrom.py`；或造 2 条 `Chr1M` 小 FASTA 干跑 |
| `register_genome.n.py` 是否与 ploidy/表名无关 | Step 7.2.1 用 `python`（可能 py2） | `head -60 /var/www/cgi-bin/register_genome.n.py` |
| `add_eggnogand02G_to_gff_cds.py` + CS mpi/GFF 存在 | Step 7.3 依赖 | `ls -l /var/www/html/Script/{add_eggnogand02G_to_gff_cds.py,Chinese_Spring1.0.mpi,IWGSC_v1.1.gff3}` |
| conda env `eggnog`/`new_env` + `zjw` python | Step 7.1/7.2/7.6/10 | `PATH=/home/fei/mambaforge/bin:$PATH conda env list` |
| 生产仓库 HEAD 与本地一致性 | 生产 `b7eb2fb`（lead 实测）≠ 本地 `22a7157`；代码改动需经 git 推送/服务端 pull 再重启 | `cd /var/www/FastAPI_backend_Port8000 && git rev-parse HEAD && git status --short` |
| docroot 写权限 | `deploy_doc_pages.py` 写 `/var/www/html/jbrowse.html` | `ls -l /var/www/html/jbrowse.html`（owner root/www-data 时需 sudo） |

---

## 4. 每基因组命令级步骤清单（含验证与回滚）

> 下列命令中占位符：`PL`=PLOIDY、`MYTAG`=数据标签、`DS=${PL}_${MYTAG}`、`ACC`=材料登录号、`GCA`/`Z`=NCBI 组装目录名。**4 个基因组各跑一遍 G1–G5；G0 一次做完（代码改动 + 4 份 name_plan.json）。**
> 执行环境：`export PATH=/var/www/html/blast/blast+/bin:/home/fei/mambaforge/bin:$PATH; export HOME=/home/fei`；`GR=/home/fei/mambaforge/envs/new_env/bin/gffread`；`ZP=/home/fei/mambaforge/envs/zjw/bin/python3`；`B=/var/www/html/getfasta/blastdb`。

### 4.0 每基因组参数表

| 变量 | comosa | markgrafii | umbellulata | uniaristata |
|---|---|---|---|---|
| `PL` | MM | CC | UU | NN |
| `MYTAG` | `Aegilops_comosa_IPK_AE783` | `Aegilops_markgrafii_EKC105_RL5723` | `Aegilops_umbellulata_IPK_AE740` | `Aegilops_uniaristata_IPK_AE680` |
| `DS` | `MM_Aegilops_comosa_IPK_AE783` | `CC_Aegilops_markgrafii_EKC105_RL5723` | `UU_Aegilops_umbellulata_IPK_AE740` | `NN_Aegilops_uniaristata_IPK_AE680` |
| `GCA` | GCA_052815735.2 | GCA_052815875.1 | GCA_060308565.1 | GCA_052815765.1 |
| 注释集合（建议） | HC_LC | HC_LC | HC_LC | HC_LC |
| 染色体名 | `Chr1M..Chr7M` | `Chr1C..Chr7C` | `Chr1U..Chr7U` | `Chr1N..Chr7N` |
| 预计 MySQL 行数 | 51,203 | 47,246 | 49,677 | 50,416 |
| `--group`（门禁绕过） | Other Triticeae | Other Triticeae | Other Triticeae | Other Triticeae |
| 预计拆分库数 | 7 | 7 | 7 | 7 |
| `Genefunc_<DS>_table` 长度 | 43 | 51 | 48 | 48 |

### 4.1 G0（一次）— 代码前置 + 命名门禁（G0 闸门）

```bash
# 0) 服务器现状核查（只读）
df -h /var/www; md5sum /var/www/data/masw_data/add_wheat_genome.sh
cd /var/www/FastAPI_backend_Port8000 && git rev-parse HEAD
# 1) 代码改动（§3.1–3.4）走本地 commit → push(github+gitee) → 服务器 git fetch && git merge --ff-only
#    → 重启 API 一次（或留到 G5 一起重启；--check-name 读磁盘文件，不依赖服务进程）
# 2) 4 份 name_plan.json（每基因组一次；--group 用 "Other Triticeae" 绕过旧页面 optgroup 检查）
cd ~/.agents/skills/lab-server/scripts
./finish_genome_integration.sh "$PL" "$MYTAG" 10.1186/s12870-026-10046-2 --check-name \
  --cultivar "<IPK-AE783 等>" --accession "$GCA" \
  --label "Ae. <species> <ACC>" --group "Other Triticeae" \
  --species "Aegilops <species>" --journal "BMC Plant Biology" --year 2026 \
  --title "Chromosome-level reference genome assemblies and annotation of four diploid Aegilops"
# 期望最后一行：[OK] 命名可直接开跑
./finish_genome_integration.sh "$PL" "$MYTAG" 10.1186/s12870-026-10046-2 --check-name --write-plan --confirm ...同上...
# 期望：已写入 /var/www/data/masw_data/$DS/name_plan.json；检查 cat 该文件 ds 字段
```

**G0 验证**：4 个 `name_plan.json` 均 `"ds":"<PL>_<MYTAG>"`；`jq .classification` = `other_triticeae`；`jq .group` = `Other Triticeae`。
**回滚**：删 `name_plan.json`（无生产影响）；代码改动 `git revert <sha>` + 重启。
**注意**：`--check-name` step 1 依赖 `SUB`（Gap B）、step 2 依赖关键词（Gap C），**必须先部署代码再跑**。

### 4.2 G1 — 下载 + FASTA 归一化（G1 闸门）

```bash
P=/var/www/data/masw_data; D=$P/$DS; mkdir -p "$D/raw"; cd "$D/raw"
BASE=https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/<xxx>/<yyy>/<zzz>
curl -fL -o genomic.fna.gz "$BASE/<zzz>_genomic.fna.gz"
curl -fL -o assembly_report.txt "$BASE/<zzz>_assembly_report.txt"
curl -fL -o md5checksums.txt "$BASE/md5checksums.txt"
md5sum genomic.fna.gz            # = 上表 md5
grep -q "$(md5sum genomic.fna.gz | cut -d' ' -f1)  ./<zzz>_genomic.fna.gz" md5checksums.txt && echo OK
# 用 assembly_report 映射：SeqName(第1列) <- GenBank-Accn(第5列)；assembled-molecule→Chr<SeqName>，其余→ChrUn_<SeqName>
python3 - "$D/raw/assembly_report.txt" "$D/raw/genomic.fna.gz" "$D/$MYTAG.fa" <<'PY'
import sys, gzip
rep, fna_gz, out = sys.argv[1], sys.argv[2], sys.argv[3]
mp = {}
for line in open(rep):
    if line.startswith('#') or not line.strip(): continue
    f = line.rstrip('\n').split('\t')
    if len(f) < 9 or not f[0] or f[0] == 'na': continue
    mp[f[4]] = ('Chr'+f[0]) if f[1] == 'assembled-molecule' else ('ChrUn_'+f[0])
with gzip.open(fna_gz, 'rt') as fi, open(out, 'w') as fo:
    for line in fi:
        if line.startswith('>'):
            h = line[1:].rstrip('\n'); tok = h.split()[0]
            name = mp.get(tok)
            if not name: raise SystemExit('unmapped FASTA token: '+tok)
            fo.write('>' + name + (' ' + h[len(tok):].strip() if h[len(tok):].strip() else '') + '\n')
        else:
            fo.write(line)
PY
grep -c '^>' "$D/$MYTAG.fa"                      # 期望 17 / 24 / 250 / 21
grep '^>' "$D/$MYTAG.fa" | grep -cE '^>Chr[1-7][MCUN]$'   # 期望 7
samtools faidx "$D/$MYTAG.fa"; awk '{s+=$2} END{print s}' "$D/$MYTAG.fa.fai"   # 期望总长=4,407,741,597 / 3,577,170,360 / 4,268,089,219 / 4,475,943,907
# provenance.txt
cat > "$D/provenance.txt" <<EOF
dataset=$DS
source=NCBI $GCA (assembly_report/md5checksums in raw/)
genomic_fna_gz_md5=$(md5sum raw/genomic.fna.gz | cut -d' ' -f1)
paper=10.1186/s12870-026-10046-2
annotation=Zenodo 10.5281/zenodo.22681907 (gene GFF HC_LC + protein FASTA + EDTA TE GFF3; no genome FASTA, no CDS)
normalized=$(date -Iseconds)
EOF
```

**G1 验证**：序列数/染色体数/总长三项与 §2.1 一致；FASTA 头全部以 `Chr` 开头；无重复头；`seqid_mapping.tsv`（accn→Chr*）已生成。
**回滚**：`rm -rf $D`（仅数据目录，未触生产）。

### 4.3 G2 — 注释归一化 + gffread 生成 CDS/PEP（G2 闸门）

```bash
P=/var/www/data/masw_data; D=$P/$DS; cd "$D/raw"
Z=https://zenodo.org/api/records/22681907/files
curl -fL -o genes_HC_LC.gff3.gz "$Z/Ae.<species>_genes_HC_LC.gff3.gz"
curl -fL -o proteins.fasta.gz   "$Z/Ae.<species>_genes_HC_LC.fasta.gz"   # 注意：README 名与实际文件名不一致，实际为 *_genes_HC_LC.fasta.gz
curl -fL -o TE.gff3.gz          "$Z/Ae.<species>.EDTA.TEanno.gff3.gz"
md5sum *.gz    # 与 Zenodo API checksum 对：HC_LC GFF/FASTA/TE 见 PAPER_DATA §3
# 归一化（使用 §3.1 修正后的 normalize 脚本；输入 seqid 1M.. + scaffold）
python3 /var/www/data/masw_data/_prep/normalize_gff2.py raw/genes_HC_LC.gff3.gz "$D/$MYTAG.gff3"
# 产物要求：GFF seqid = Chr1M..Chr7M / ChrUn_<原 scaffold>；mRNA ID 全部 .数字 结尾（STRG .pN→.N）
awk -F'\t' '!/^#/ && NF>=9 && $3=="mRNA"{print $9}' "$D/$MYTAG.gff3" | grep -cE 'ID=[^;]*\.[0-9]+;'      # 应 = mRNA 总数（51,203 / …）
awk -F'\t' '!/^#/ && NF>=9 {print $1}' "$D/$MYTAG.gff3" | sort -u | grep -vE '^Chr' && echo "!! 非Chr seqid" || echo "seqid OK"
# 生成 CDS/PEP（用 NCBI FASTA + 归一化 GFF）
nice -n 10 $GR -g "$D/$MYTAG.fa" -x "$D/$MYTAG.cds" -y "$D/$MYTAG.pep" "$D/$MYTAG.gff3" 2> "$D/gffread.stderr"
grep -c '^>' "$D/$MYTAG.cds"; grep -c '^>' "$D/$MYTAG.pep"    # 期望 51,203/47,246/49,677/50,416
# 清理 pep 行尾/内部 . 与 *（check 脚本只清 '.'）
sed -i '/^>/!s/[.*]//g' "$D/$MYTAG.pep"
# 交叉校验：与 Zenodo 蛋白 FASTA 同 ID 数（允许末端终止符差异；comosa 内部终止符 6,573 条属注释帧移，记录不阻断）
gzip -dc raw/proteins.fasta.gz | grep -c '^>'
# 官方质检
python3 /var/www/html/Script/check_genome_files.py "$MYTAG"   # rc=0，注意会生成 $MYTAG.pep.bak
```

**G2 验证**：`check_genome_files.py` rc=0；四件套齐；mRNA ID 规则；GFF seqid ⊆ FASTA；pep 无 `.`/`*`。
**回滚**：重跑归一化（幂等，覆盖输出）；`rm -f $MYTAG.cds $MYTAG.pep` 后重跑 gffread。

### 4.4 G3 — 流水线（G3 闸门）

```bash
P=/var/www/data/masw_data; D=$P/$DS; cd "$D"
export PATH=/var/www/html/blast/blast+/bin:/home/fei/mambaforge/bin:$PATH; export HOME=/home/fei
setsid --fork bash -c "exec bash /var/www/data/masw_data/add_wheat_genome.sh \
  ${MYTAG} ${D} ${PL}" > pipeline_${MYTAG}.log 2>&1 < /dev/null
tail -f pipeline_${MYTAG}.log     # 期望末行 [SUCCESS] ${MYTAG} 全部完成
```

**G3 验证**：
```bash
grep -E "\[SUCCESS\]|\[ERROR\]" pipeline_${MYTAG}.log
PW=$(grep '^DB_PASS=' /etc/wheatomics/db_ddl.env | cut -d= -f2)
mysql -u wheatomics_ddl -p"$PW" -N -e "SELECT COUNT(*) FROM Genefuncdb.Genefunc_${DS}_table;"   # = mRNA 数
B=/var/www/html/getfasta/blastdb; BB=/var/www/html/blast/blast+/bin
$BB/blastdbcmd -db "$B/${DS}.genome" -info | head -2                      # 序列数=17/24/250/21
ls "$B/${DS}.genome_Chr"* 2>/dev/null | wc -l                            # 期望 7（拆分库）
$BB/blastdbcmd -db "$B/${DS}.add_Description.cds" -info | head -2         # = mRNA 数
python3 -c "import json;print(len(json.load(open('/var/www/html/jbrowse-1.12.3-release/${DS}/seq/refSeqs.json'))))"  # = 17/24/250/21
wc -l "${DS}_with_annotation_ChineseSpring02G.bed"
```
**回滚**：删 `$B/${DS}.genome*`、`${DS}.add_Description.*`、`/var/www/html/blast/db/{nucleotide,protein}/${DS}*` 软链、`/var/www/html/jbrowse-1.12.3-release/${DS}`；`DROP TABLE Genefuncdb.Genefunc_${DS}_table;`（流水线可重跑，幂等性以 TRUNCATE/重灌为准）。

### 4.5 G4 — 收尾（G4 闸门；patch 后一条命令，未 patch 则手工）

```bash
# 先 dry-run 看计划
bash ~/.agents/skills/lab-server/scripts/finish_genome_integration.sh "$PL" "$MYTAG" 10.1186/s12870-026-10046-2 --dry-run
# 正式（patch 后；--group 已在 plan 中；备份自动到 /var/www/data/masw_data/backup_<时间戳>/）
bash ~/.agents/skills/lab-server/scripts/finish_genome_integration.sh "$PL" "$MYTAG" 10.1186/s12870-026-10046-2 \
  --no-plan-check --group "Other Triticeae" --restart-api
# 未 patch 时的等价手工 8 步：
samtools faidx "$B/${DS}.genome"; samtools faidx "$B/${DS}.add_Description.cds"        # 3)
# 4) Genefunc_registry 行：SQL 见 SOP §5.6 / finish step4 SQL（Group='Other Triticeae'）
# 5) alias 追加：all_genomes.nal += ${DS}.genome；all_gene.nal += ${DS}.add_Description.cds；all_protein.pal += ${DS}.add_Description.pep；all_genomes_type.txt += "${DS}.genome\t$PL"
# 6-8) cd /var/www/FastAPI_backend_Port8000 && set -a; . ./.env; set +a
$ZP scripts/import_jbrowse_meta.py --dataset "$DS"
$ZP scripts/rebuild_genome_registry.py
# 9) $ZP scripts/build_blast_jbrowse_map.py && $ZP scripts/build_blast_jbrowse_map.py --check
# 10) V2 卡片：改 repo app/static/docpages/jbrowse.html（本批 4 卡一次改完）→ python3 scripts/deploy_doc_pages.py --only jbrowse
```

**G4 验证**：
```bash
curl -s "http://127.0.0.1:8000/api/blast/databases?program=blastn" | grep -o "${DS}" | head -1
curl -s "http://127.0.0.1:8000/api/jbrowse/datasets" | grep -o "${DS}" | head -1
curl -s "http://127.0.0.1:8000/api/genes/functions/registry" | grep -o "Genefunc_${DS}_table" | head -1
curl -s "http://127.0.0.1:8000/api/sequence/by-interval?region=Chr1M_${MYTAG}:200-500&database=all_genomes" | head -2
curl -s "http://127.0.0.1:8000/api/PrimerServer2/databases" | grep -o "${DS}.genome" | head -1
$BB/blastdbcmd -db "$B/all_genomes" -entry "Chr1M_${MYTAG}" -range 1-40 | head -2
$ZP scripts/build_blast_jbrowse_map.py --check && echo MAP_OK   # 期望 CHECK OK（rc=0）
curl -s http://127.0.0.1:8000/api/jbrowse/coverage | head -c 300  # ok=true
```
**回滚**：恢复 `backup_<时间戳>/`（jbrowse.html/all_genomes.nal/all_gene.nal/all_protein.pal/all_genomes_type.txt）；`DELETE FROM Genefuncdb.Genefunc_registry WHERE table_name='Genefunc_${DS}_table';`；`DELETE FROM wheatomics_db.genome_registry WHERE dataset_id='${DS}';`；重跑 `import_jbrowse_meta.py`、`rebuild_genome_registry.py`、`build_blast_jbrowse_map.py`；`sudo systemctl restart wheatomics-api`。

### 4.6 G5 — TE 轨道（可选阶段；用 Zenodo EDTA GFF）

```bash
JB=/var/www/html/jbrowse-1.12.3-release; D=/var/www/data/masw_data/$DS
# 1) 用 §4.2 的 seqid 映射表把 TE seqid 映射到 JBrowse refseq 名（Chr1M / ChrUn_*；umbellulata 的 S_S_* 需额外映射，S_S_73_2 无对应，丢弃并记录）
# 2) 归一化 GFF：type→TE，属性→ID=TE_<n>;Name=<classification>，输出 ##gff-version 3
awk -F'\t' 'BEGIN{OFS="\t"; print "##gff-version 3"} !/^#/ && NF>=9 { $1=map[$1]; $3="TE"; $9="ID=TE_" ++n ";Name=" $3_orig }' ...
# 3) 生成 NCList 轨道（必须 new_env 的 perl）
cd "$JB/$DS" && /home/fei/mambaforge/envs/new_env/bin/perl ../bin/flatfile-to-json.pl --gff <norm.gff3> \
  --trackLabel TE --type TE --nameAttributes Name --trackType CanvasFeatures --key "Transposons (EDTA)" \
  --clientConfig '{"style":{"color":"#7c3aed","height":6}}' --config '{"category":"Annotation"}' --out ./ --sortMem 4000000000
# 4) 同步 API
cd /var/www/FastAPI_backend_Port8000 && set -a; . ./.env; set +a && $ZP scripts/import_jbrowse_meta.py --dataset "$DS"
# 5) 验证
curl -s "http://127.0.0.1:8000/api/jbrowse/datasets/${DS}/trackList" | grep -o TE | head -1
```
**规模参照**：PT HiTE 12.4M 特征 ~19 min、track 数据 ~1.8 GB；本批 comosa EDTA 6.34M 行（其他 60–78 MB gz 量级相近），预计 **8–15 min/个、~0.8–1.2 GB/个**。
**回滚**：删除 `tracks/TE/` + 从 `trackList.json` 移除 TE 轨道（先备份），重跑 `import_jbrowse_meta.py`。

---

## 5. 验收断言（G5，硬指标）

| # | 项 | 断言 |
|---|---|---|
| 1 | `/api/genomes/stats` | total 316→**320**；jbrowse 215→**219**；gene_function 214→**218**；getfasta 199→**203**；primerserver 203→**207**；web_blast 200→**204**；by_ploidy：MM 1→**2**、UU 2→**3**、CC 0→**1**、NN 0→**1** |
| 2 | `/api/blast/databases?program=blastn` | total 2,924→**2,960**（+4×9）；4 个 `${DS}.genome`、`${DS}.genome_Chr1..7`、`${DS}.add_Description.cds` 均在 `other_triticeae`；`blastp` 193→**197** |
| 3 | `/api/jbrowse/datasets` | 219→**223**；每个 `${DS}` refseq 数 = 17/24/250/21 |
| 4 | MySQL | `Genefunc_${DS}_table` 行数 = 51,203/47,246/49,677/50,416；`Genefunc_registry` 216→**220**，4 行 `Polyploidy`/`Group='Other Triticeae'`/`display_order` 正确 |
| 5 | `genome_registry` | 4 行 `ploidy/subgenomes`（MM/M、CC/C、UU/U、NN/N）、DOI/期刊/2026/assembly_accession=`GCA_*`/assembly_level=Chromosome/**chromosome_count=7（覆盖 `.fai` 的 17/24/250/21）**/`annotation_status=available`/`gene_count`/`te_content`/`visible=1` 齐全 |
| 6 | getfasta | `/api/sequence/chromosomes?database=all_genomes&pattern=<Chr1>` 命中；`by-interval` 正常；`by-gene` 返回 CDS/蛋白 |
| 7 | PrimerServer2 | `${DS}.genome` 与 `${DS}.add_Description.cds` 的 `.fai` 存在；`/databases` examples 非空、`/sequences` 200 |
| 8 | BLAST↔JBrowse 映射 | `build_blast_jbrowse_map.py --check` rc=0；4 个 base `assembly_match=true`（按染色体长度匹配，长短名不同亦可）；`/api/jbrowse/coverage` ok=true |
| 9 | 前端 | `/jbrowse.html` 含 4 张新卡（MM/UU 分区 +1、CC/NN 新分区）；hero 217/210/24；blast2/getfasta/PrimerServer2 公网 200 |
| 10 | 回归 | 旧 Aegilops 条目（PI551049/PI554389/TA1851、SS/TT/MMUU）BLAST/JBrowse/getfasta 正常；聚合库旧成员可查（如 `Chr1A_Abo`）；`/api/genomes/stats` 其它计数不变 |

---

## 6. 阻塞 / 风险 / 工作量

### 6.1 阻塞与风险清单

| 级别 | 项 | 结论/处置 |
|---|---|---|
| **硬阻塞（0）** | 基因组 FASTA | 无：4 个 GCA 已定位、md5 已取；Zenodo 无 FASTA 不影响 |
| **条件阻塞（数据质量）** | GFF/FASTA 版本一致性 | PAPER_DATA 已验：GFF 全部 seqid 在 NCBI assembly_report 中，坐标不越界（0 缺失/0 越界）→ 兼容；14 个位点 gffread 翻译与 Zenodo 蛋白一致 |
| **条件阻塞（注释质量）** | comosa 6,573 条内部终止符（帧移）；STRG ID 需改；pep 终止符 `.`/`*` | 归一化阶段处理并记录；不阻断上线，但需在 registry `notes` 标注 |
| **代码阻塞（必改）** | Gap A 归一化正则；Gap B `SUB[CC/NN]`；Gap C 关键词；Gap D finish 脚本 V2 错配 | 4 处改完才能「一条命令」跑通门禁+收尾；否则手工绕过（`--group "Other Triticeae"` + 手工 8 步 + 手工卡片） |
| **待服务器核查** | `split_fasta_by_chrom.py` 认字母 M/C/U/N；`register_genome.n.py`；`add_eggnogand02G_to_gff_cds.py` 依赖；conda env；生产 HEAD；docroot 写权限 | 命令见 §3.5 |
| **待用户确认** | ①注释集合 HC vs HC+LC（建议 HC_LC：51,203/47,246/49,677/50,416）；②命名方案（建议 §2.1；连字符禁用）；③TE 轨道本批做否（4 个全做 / 延后）；④unplaced scaffold 基因是否保留（建议保留 38/53/1,103/66 个）；⑤旧同物种条目并存确认；⑥finish 脚本 patch 授权；⑦`cite.html`/周报同步 | 见 §8 |
| **低风险** | 磁盘（30 T 余量）、API 重启（60–90 s）、docroot 权限、生产仓库落后本地 | 计划内 |

### 6.2 工作量与资源表（估算依据：PT 1h23/13.9 Gb/215k mRNA；本批 16.73 Gb/198.5k mRNA）

| 项 | 每基因组 | 4 个合计 | 说明 |
|---|---|---|---|
| **新增磁盘** | **25–30 GB** | **100–120 GB** | FASTA 3.6–4.5 + BLAST（整基因组+7 拆分+CDS/PEP）~18 + JBrowse refseq ~4.5 + 注释中间产物/备份 1–2 + TE 轨道 0.8–1.2；下载 gz 另 ~5.4 GB（可删）；`/var/www` 余 30 T，充裕 |
| **流水线机时** | **25–45 min/个** | **2–4 h**（顺序跑；2 并发约 1.5–2.5 h） | 依据 PT：EggNOG ~20 min、miniprot ~17 min 按 mRNA 数（215k→50k）与基因组（14→4.4 Gb）折算；固定步（makeblastdb/prepare-refseqs/flatfile-to-json/generate-names）~15–20 min |
| 归一化+gffread 机时 | 10–20 min/个 | 0.7–1.3 h | gffread 4.4 Gb + 5 万 mRNA |
| TE 轨道机时（可选） | 8–15 min/个 | 0.6–1 h | comosa 6.34M 行参照 PT 12.4M/19 min |
| 收尾+验收机时 | 5–10 min/个 | 0.4–0.7 h | patch 后 |
| **人时** | 2.5–3.5 h | **10–14 h** | 下载/归一化/校验 4–5 h、门禁+代码 1–2 h、监控/收尾 3–4 h、TE 1–2 h、公网核验 1 h |
| **API 重启** | — | **1–2 次**（每次 60–90 s 不可用） | 最少 1 次（全部数据+registry 就绪后清 `/api/blast/databases` 1 h 缓存）；若代码先部署验证则 2 次 |
| **前端改动点** | — | 1 文件（4 卡 + 2 新分区 + 3 处计数）+ 可选 chips | `app/static/docpages/jbrowse.html` → `deploy_doc_pages.py --only jbrowse`；blast2/getfasta/PrimerServer2 动态无需改 |
| **代码改动** | — | 4 个仓库文件 + 1 个脚本 patch | `normalize_gff2.py`(+`normalize2.sh` 或新增归一化脚本)、`rebuild_genome_registry.py`(SUB，建议再+overrides/V2 解析)、`blast.py`(关键词)、`finish_genome_integration.sh`(V2)、`docpages/jbrowse.html`(卡片) |
| 并发策略 | — | 建议 **2 并发 × 2 批**，TE 串行 | EggNOG `--cpu 12`、miniprot `--threads 50`、128 核/504 G；4 并发会线程/IO 争用；顺序跑最稳（2–4 h） |

---

## 7. 时间安排建议（在用户授权后）

| 批次 | 内容 | 预计 |
|---|---|---|
| T0 | 代码 4 处改动 + patch finish 脚本 → push → 服务器 pull（暂不重启）；4 份 `name_plan.json` | 1.5–2 h（人） |
| T1 | G1+G2：4 个基因组下载/归一化/gffread/质检（可并行 2 个下载） | 2–3 h（人+机） |
| T2 | G3：2 并发×2 批跑流水线（后台） | 1.5–2.5 h（机） |
| T3 | G4：收尾 4 次 + 元数据写回 + 映射重建 + 重启 API | 1–1.5 h |
| T4 | 前端 V2 卡片（4 卡+2 分区+计数）+ deploy + TE 轨道（可选） | 1–2 h |
| T5 | G5 验收/公网核验/回归 + 写执行记录 | 1–1.5 h |

---

## 8. 需要用户拍板的事项

1. **注释集合**：HC_LC（全基因集，51,203/47,246/49,677/50,416）还是仅 HC（37,623/34,133/35,799/35,816）？建议 **HC_LC**（含 LC/TAMA 模型，需先做 ID 归一化）；若只上 HC，工作量更小但平台与其他 Aegilops 条目口径可能不一致。
2. **命名方案**：采用 §2.1 推荐名（`MM_Aegilops_comosa_IPK_AE783` 等，表名 43/51/48/48，均 <64，无连字符）？还是缩短 MYTAG（如 `AeComosa_AE783`）？**不建议用 `IPK-AE783` 连字符原样**。
3. **TE 轨道**：本批 4 个都做（+0.6–1 h 机时、+3–5 GB）？还是先上基因轨道、TE 延后？
4. **unplaced scaffold 基因**：保留（38/53/1,103/66 个，JBrowse refseq 含 ChrUn_*）还是仅染色体？建议**保留**（否则丢基因，且当前 FASTA/GFF 已一一对应）。
5. **旧条目处置**：确认 4 个新条目**新增并存**（不隐藏、不改旧 JBrowse 数据集/旧 BLAST 库）？
6. **代码/patch 授权**：授权修改 §3 的 4 个仓库文件 + `finish_genome_integration.sh`（本地 commit→push→服务器 pull→重启）；以及 `deploy_doc_pages.py` 发布 docpage（可能需要 sudo）。
7. **执行窗口**：流水线+重启 API 是否安排在低峰时段（重启 60–90 s 不可用）。
8. **可选同步**：`cite.html` 引文、周报/首页公告、`servers/wheatomics.yaml` manifest。

---

## 9. 附：改动位置速查

| 文件 | 位置 | 改动 |
|---|---|---|
| `scripts/rebuild_genome_registry.py` | `SUB`（~586 行） | `"CC": "C", "NN": "N"` |
| `app/api/routers/blast.py` | `DB_CLASSIFICATION` → `other_triticeae.keywords`（~386 行） | `"aegilops_markgrafii","aegilops_uniaristata","markgrafii","uniaristata"` |
| `/var/www/data/masw_data/_prep/normalize_gff2.py` + `normalize2.sh`（或新增 `aegilops4_normalize.py`） | `CHROM` 正则 / AWK 判断 | `^(?:chr)?([1-7])([A-Za-z])$`；scaffold→`ChrUn_*`；`\.p(\d+)$`→`.\1`；同步 `ID/Parent/Derives_from` |
| `~/.agents/skills/lab-server/scripts/finish_genome_integration.sh`（+服务器 `_prep` 副本） | `step_jbrowse_card` / `step_blast_html` / `verify` | V2 页面分支（`.asm-card` 插入 + 计数更新；BLAST SPA 跳过、改 API 断言） |
| `app/static/docpages/jbrowse.html` | `#group-mm`/`#group-uu` + 新增 `#group-cc`/`#group-nn`；hero/status/group-count | 4 卡 + 计数 213→217、206→210、22→24、MM 1→2、UU 2→3 |
| `scripts/rebuild_genome_registry.py`（建议 P2） | `CARD_RE`/`BLAST_HTML` 使用处 | V2 卡片解析 + `web_blast_group` 新判定（或 override） |

## 10. 附：证据与文件

- SOP：`~/.agents/skills/lab-server/references/wheatomics-new-genome-sop.md`（474 行；§0.5 命名门禁、§3 流水线、§5 前端、§7 已知坑）
- 收尾脚本：`~/.agents/skills/lab-server/scripts/finish_genome_integration.sh`（1022 行，md5 `e4886d0c…`）；生产 `add_wheat_genome.sh` 1034 行 md5 `70fb9ff2…`（SOP 记的 `208f0653…` 已过期）
- 先例：`CWI22960_genome_update_plan.md`（genome-only 4–6 h、磁盘 +45–55 GB/10.9 Gb）、`Sumai3_genome_update_plan.md`（两阶段/替换 vs 新增）
- 数据：NCBI FTP 4 个 GCA（§2.1）；Zenodo record `10.5281/zenodo.22681907`（25 文件，无 FASTA/CDS/GTF/BED，CC-BY-4.0）；论文 `10.1186/s12870-026-10046-2`（BMC Plant Biology，2026-11-07，CC-BY-4.0）
- 线上只读实测（2026-11-11）：`/api/genomes/stats`（316/215/214/199/203/200/86/43；MM=1、UU=2、CC=0、NN=0）、`/api/blast/databases?program=blastn`（2,924 库；MM/UU/SS/TT/MMUU→`other_triticeae`）、`/api/jbrowse/datasets`（219；`Aegilop_comosa_PI551049`、`Aegilops_umbellulata_PI554389/TA1851` 在，无 markgrafii/uniaristata）、`/api/genes/functions/registry`（216 行；最长表名 55 字符 `<64`）
- 服务器事实（Lead 2026-11-11 实测）：`/var/www` 116 T/已用 81 T/余 30 T（74%）；128 核、负载 11.7、内存 504 G；`/var/www/data/masw_data/` 下无 Aegilops 目录；`gffread=/home/fei/mambaforge/envs/new_env/bin/gffread`、`samtools=/usr/bin/samtools`、blast+ 2.12.0；生产 git HEAD `b7eb2fb`（本地 `22a7157`）
- 配套报告：`PAPER_DATA.md`（论文/Zenodo/NCBI 事实、GFF 统计、gffread 验证）、`PLATFORM_BASELINE.md`（平台基线、`--check-name` 模拟、命名方案表）
