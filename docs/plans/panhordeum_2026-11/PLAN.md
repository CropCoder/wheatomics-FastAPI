# PanHordeum v1（大麦属泛基因组）接入 WheatOmics 计划

> 论文：Jia-Wu Feng et al. (2026) *Structural and regulatory evolution across the genus Hordeum*, Nature, DOI [10.1038/s41586-026-11332-7](https://doi.org/10.1038/s41586-026-11332-7)  
> 数据：IPK Galaxy 库 `PanHordeum v1 2025`（assemblies 26.7 GB tar.gz，需登录）；PGP/e!DAL [10.5447/ipk/2026/11](https://doi.org/10.5447/ipk/2026/11)（基因注释/TE/MSA，**匿名可下载**，已验证）；ENA umbrella BioProject **PRJEB128330**（24 个 GCA 组装，**公网可下载**，共 114.49 Gb）

## 0. 决策（2026-11-19 确认）

- 范围：**新增 24 个，先试点 3 个**（H. chilense GRA1000 / H. bogdanii H240 / H. intercedens NGB15676），验证全链路后批量
- ploidy：**HH / HHHH / HHHHHH**（平台惯例；HH 区已含 wild Hordeum）
- 注释：**main（全部注释）**：`*.gff3` + `*.cds.fa` + `*.aa.fa`
- TE 轨道：**本批不加**
- H559 组装：用户提供/联系作者补；本批先按 23 个 ENA 组装推进

## 0.1 结论先行

- 论文包含 **27 份材料 / 25 个物种**（22 二倍体 + 4 四倍体 + 1 六倍体）；可下载到 **26 个基因组注释**（e!DAL）+ **24 个 GCA 组装**（ENA）。
- 平台已有 3 个重复：H. vulgare（Morex 系列）、H. bulbosum（FB19 单倍型，HHHH）、H. erectifolium（NGB6816，HH）→ **建议新增 24 个基因组**（23 个 ENA 组装 + H. marinum H559 需另行获取）。
- 平台节点可直接访问外网（实测 ENA 7.6 MB/s、e!DAL 2.0 MB/s）→ **无需 Galaxy 登录、无需经跳板机中转大文件**，直接在 web 节点下载+处理。
- 预估：下载 3–6 h、归一化 1–2 h、逐基因组 G3 流水线 12–30 h（24 个）、收尾/验收 4–6 h；磁盘 +约 200–400 GB。

## 1. 目标清单（新增 24 个；2 个平台已有跳过）

规则：Diploid → `HH`；Tetraploid → `HHHH`；Hexaploid → `HHHHHH`（新代码）。名称 `DS=<PLOIDY>_Hordeum_<species>_<accession>`。

| # | e!DAL 注释名 | 物种 | 材料 | ENA GCA | 组装大小 (Gb) | 拟 ploidy | 平台 DS | 状态 |
|---|---|---|---|---|---|---|---|---|
| 1 | Hordeum_chilense_GRA1000 | chilense | GRA1000 | GCA_973571505 | 3.59 | HH | HH_Hordeum_chilense_GRA1000 | 新增 |
| 2 | Hordeum_jubatum_BCC2055 | jubatum | BCC2055 | GCA_973576795 | 7.49 | HHHH | HHHH_Hordeum_jubatum_BCC2055 | 新增 |
| 3 | Hordeum_intercedens_NGB15676 | intercedens | NGB15676 | GCA_973573815 | 2.92 | HH | HH_Hordeum_intercedens_NGB15676 | 新增 |
| 4 | Hordeum_euclaston_NGB90233 | euclaston | NGB90233 | GCA_973576735 | 2.90 | HH | HH_Hordeum_euclaston_NGB90233 | 新增 |
| 5 | Hordeum_brevisubulatum_PI401390 | brevisubulatum | PI401390 | GCA_973572355 | 4.03 | HH | HH_Hordeum_brevisubulatum_PI401390 | 新增 |
| 6 | Hordeum_gussoneanum_BCC2005 | gussoneanum | BCC2005 | GCA_973576905 | 4.32 | HHHH? | HHHH_Hordeum_gussoneanum_BCC2005 | 新增 |
| 7 | Hordeum_bogdanii_H240 | bogdanii | H240 | GCA_973568715 | 4.10 | HH | HH_Hordeum_bogdanii_H240 | 新增 |
| 8 | Hordeum_murinum_BCC2017 | murinum | BCC2017 | GCA_973573485 | 3.80 | HHHH? | HHHH_Hordeum_murinum_BCC2017 | 新增 |
| 9 | Hordeum_flexuosum_BCC2023 | flexuosum | BCC2023 | GCA_973576695 | 3.53 | HH | HH_Hordeum_flexuosum_BCC2023 | 新增 |
| 10 | Hordeum_bulbosum_FB19_011_3 | bulbosum | FB19_011_3 | 待补 | - | HH | HH_Hordeum_bulbosum_FB19_011_3 | 跳过（平台已有） |
| 11 | Hordeum_californicum_BCC2058 | californicum | BCC2058 | GCA_973579495 | 3.77 | HH | HH_Hordeum_californicum_BCC2058 | 新增 |
| 12 | Hordeum_comosum_NGB18417 | comosum | NGB18417 | GCA_973576465 | 3.82 | HH | HH_Hordeum_comosum_NGB18417 | 新增 |
| 13 | Hordeum_marinum_H559 | marinum | H559 | 待补（H559 原文） | - | HH | HH_Hordeum_marinum_H559 | 新增（需补组装） |
| 14 | Hordeum_cordobense_BCC2067 | cordobense | BCC2067 | GCA_973576565 | 3.89 | HH | HH_Hordeum_cordobense_BCC2067 | 新增 |
| 15 | Hordeum_stenostachys_NGB90152 | stenostachys | NGB90152 | GCA_973577565 | 3.97 | HH | HH_Hordeum_stenostachys_NGB90152 | 新增 |
| 16 | Hordeum_gussoneanum_BCC2011 | gussoneanum | BCC2011 | GCA_986450445 | 8.35 | HHHH? | HHHH_Hordeum_gussoneanum_BCC2011 | 新增 |
| 17 | Hordeum_secalinum_BCC2004 | secalinum | BCC2004 | GCA_973573685 | 8.56 | HHHH | HHHH_Hordeum_secalinum_BCC2004 | 新增 |
| 18 | Hordeum_marinum_BCC2001 | marinum | BCC2001 | GCA_973576855 | 3.81 | HH | HH_Hordeum_marinum_BCC2001 | 新增 |
| 19 | Hordeum_roshevitzii_BCC2069 | roshevitzii | BCC2069 | GCA_973573565 | 4.03 | HH | HH_Hordeum_roshevitzii_BCC2069 | 新增 |
| 20 | Hordeum_parodii_BCC2025 | parodii | BCC2025 | GCA_986451185 | 10.90 | HHHHHH | HHHHHH_Hordeum_parodii_BCC2025 | 新增 |
| 21 | Hordeum_patagonicum_BCC2065 | patagonicum | BCC2065 | GCA_973573515 | 3.90 | HH | HH_Hordeum_patagonicum_BCC2065 | 新增 |
| 22 | Hordeum_pusillum_NGB6888 | pusillum | NGB6888 | GCA_973577425 | 2.96 | HH | HH_Hordeum_pusillum_NGB6888 | 新增 |
| 23 | Hordeum_muticum_NGB90062 | muticum | NGB90062 | GCA_973577135 | 4.01 | HH | HH_Hordeum_muticum_NGB90062 | 新增 |
| 24 | Hordeum_murinum_BCC2009 | murinum | BCC2009 | GCA_973576975 | 8.25 | HHHH? | HHHH_Hordeum_murinum_BCC2009 | 新增 |
| 25 | Hordeum_erectifolium_NGB6816 | erectifolium | NGB6816 | GCA_973576575 | 4.00 | HH | HH_Hordeum_erectifolium_NGB6816 | 跳过（平台已有） |
| 26 | Hordeum_pubiflorum_BCC2028 | pubiflorum | BCC2028 | GCA_973577355 | 3.60 | HH | HH_Hordeum_pubiflorum_BCC2028 | 新增 |

> `HHHH?` = 该 accession 的组装可能只含部分亚基因组（如 murinum/gussoneanum），P1 按 GFF 实际 seqid 数（7/14/21 条染色体）判定 HH/HHHH/HHHHHH，必要时合并两个亚基因组组装为一个 HHHH 数据集。
> `Hordeum_marinum_H559`：论文更新版 v2 组装在 ENA **GCA_973576875**（PRJEB97630，3.82 Gb），GFF/CDS/PEP 在 e!DAL → **24 个基因组全部可自主下载**。
> 完整机器可读清单：[inventory.tsv](inventory.tsv)（含每条 ENA 下载 URL、e!DAL 注释路径）。

## 2. 数据源核实（2026-11-19 实测）

| 来源 | 内容 | 访问方式 | 实测速度 |
|---|---|---|---|
| ENA PRJEB128330 | 24 个 GCA 组装 FASTA（`https://www.ebi.ac.uk/ena/browser/api/fasta/GCA_xxx`） | 公网匿名 | **7.6 MB/s**（web 节点直连） |
| e!DAL 10.5447/ipk/2026/11 | 每基因组 43 个注释文件（GFF3/CDS/PEP/featuretable 等）；TE GFF（panEDTA） | 公网匿名（`.../FILE_UUID/1/DOWNLOAD`） | **2.0 MB/s** |
| IPK Galaxy PanHordeum v1 | 组装 tar.gz 26.7 GB；注释 tar.gz（GFF 1.3 GB 等） | 需登录/API key（匿名 403） | — |

**结论：ENA 组装 + e!DAL 注释即可覆盖 23/24 个基因组，无需 Galaxy。** Galaxy 仅作为 `H559` 或多倍体亚基因组缺失时的备选。

## 3. 注释选择策略

e!DAL 每个基因组含多套注释（main / high / longest / high_longest 等）。建议：
- GFF：`*.high_longest.gff3`（高置信基因 + 每基因最长转录本，`confidence=high`、`tag=protein_coding`）
- CDS/PEP：`*.high_longest.cds.fa` + `*.high_longest.aa.fa`
- ID：**保留作者 ID**（形如 `HCHILENSE.GRA1000.r1.1HG00000020.1`，天然满足平台 mRNA 以 `.数字` 结尾的规则）→ 不需要 renumber，便于回溯。
- 归一化：`chr1H` → `Chr1H`（首字母大写）；多倍体 `chr1H_1` → `Chr1H_1`；未定位序列 → `ChrUn_<ENA accession>`（用 ENA 组装报告的 sequence name 做映射）。
- aa 文件可能带终止符 `.`/`*` → 用 `normalize_diploid.py pep` 清理。

## 4. 阶段计划（P0–P7）

### P0 前置确认（0.5 h）
- [ ] 用户确认：范围（24 个）、ploidy/分组、注释变体、是否加 TE 轨道
- [ ] 磁盘确认（/var/www 30T 可用）；下载目录 `/var/www/data/masw_data/panhordeum_v1/`
- [ ] 记录平台现状（API counts：AABB/HH/HHHH、JBrowse、BLAST 库数）与备份

### P1 数据下载（3–6 h，web 节点直连，后台并行）
- [ ] ENA 23 个组装：`https://www.ebi.ac.uk/ena/browser/api/fasta/GCA_xxx`，保存 `${MYTAG}.ena.fa`，记录 md5/序列数/总长；校验总和 ≈ base_count
- [ ] e!DAL 注释：每基因组 3 个文件（`high_longest.gff3` / `.high_longest.cds.fa` / `.high_longest.aa.fa`）；校验 gzip/文件大小
- [~] `Hordeum_marinum_H559`：使用 ENA `GCA_973576875`（PRJEB97630）+ e!DAL 注释（已加入下载队列）
- [ ] 下载清单与 md5 落盘 `download_manifest.tsv`

### P2 归一化 + 四件套（1–2 h，可脚本化）
- [ ] FASTA：`>ENA|ACC|ACC.ver ... chromosome: 1H` → `>Chr1H`；`... chromosome: 1H_1` → `>Chr1H_1`；其余 scaffold → `>ChrUn_<ACC>`；总长/条数校验
- [ ] GFF：seqid `chr1H`→`Chr1H`、`chr1H_1`→`Chr1H_1`；检查 mRNA ID 全部 `.数字`；无 seqid 缺失
- [ ] CDS/PEP：ID 与 GFF mRNA 一致；PEP 清理 `.`/`*`；计数 = mRNA 数
- [ ] 产出 `${MYTAG}.fa/.gff3/.cds/.pep` + `provenance.txt` + `seqid_mapping.tsv` + `name_plan.json`
- [ ] 自动判定 ploidy：GFF 唯一染色体数 7/14/21 → HH/HHHH/HHHHHH

### P3 G2 质检（批量，0.5 h）
- [ ] `check_genome_files.py <MYTAG>` rc=0；`normalize_diploid.py check`；计数断言（fa/GFF/CDS/PEP）
- [ ] `renumber_gff_ids.py --check` 不适用（保留作者 ID）；改为自检 mRNA `.数字` + 唯一性

### P4 G3 批量流水线（12–30 h，建议并发 2–3）

> **建议先做 3 个试点**（如 H. chilense / H. bogdanii / H. intercedens，各 ~3–4 Gb 二倍体），
> 验证「ENA 组装 ↔ e!DAL 注释 seqid 对齐 → 四件套 → G3 → G4 → G5」全链路后再批量；
> 试点无问题再跑剩余 21 个（多倍体放在第二批，单独核对亚基因组）。
- [ ] 每个基因组：`add_wheat_genome.sh <MYTAG> <DIR> <PLOIDY>`
- [ ] 按批次（每批 3–4 个）监控 `[SUCCESS]`，失败隔离并记录
- [ ] 产物：BLAST genome/14?/7 染色体拆分库、CDS/PEP 库、`Genefunc_<DS>_table`、JBrowse 数据集、ChineseSpring02G 映射

### P5 G4 收尾（每基因组 2–5 min，批量）
- [ ] `finish_genome_integration.sh <PLOIDY> <MYTAG> <DOI> --label ... --group "Barley" ...`
- [ ] 注意：`--group Barley`（脚本默认 HH→Other）；多倍体 `--group Barley` 或 `Wild Hordeum`
- [ ] 聚合库 alias：使用已升级的 `update_blast_alias.py`（base+delta append；all_genomes 超限前插）——依次追加 24 个 genome/cds/pep 成员（每批后 `--check`）
- [ ] JBrowse 卡片：HH 分区 +17；HHHH 分区（若页面无此分区需新建）+7；HHHHHH 新分区 +1
- [ ] API 重启（2–3 min 不可用），刷新 BLAST/GetSequence 缓存

### P6 G5 验收（4–6 h）
- [ ] 逐基因组：`/api/genomes/<DS>`、JBrowse `refSeqs.json` 数、`blastdbcmd -info`、`Genefunc` 行数、BLAST↔JBrowse map
- [ ] 平台计数：total +24；HH +17；HHHH +7；HHHHHH +1；JBrowse +24；getfasta +24；BLAST 分类 barley
- [ ] 公网抽测：JBrowse 卡片/轨道、GetSequence 面板示例、Web BLAST 新库、PrimerServer2
- [ ] 回归：既有 barley/其他基因组查询正常；`getfasta` 统计不丢（alias 200 成员限制）

### P7 文档与交付
- [ ] 更新 `docs/plans/panhordeum_2026-11/`（清单/日志/验收）、SOP 增补（Hordeum 批量接入）
- [ ] commit + push（github+gitee）、生产 pull；记录 md5/统计

## 5. 需要改的代码
- [ ] `rebuild_genome_registry.py`：`SUB` 增加 `HHHH`=H,H（可选）、`HHHHHH`；新增 24 条 overrides（display_name/species/ploidy/subgenomes/genome_size/gene_count/doi/journal/year/accession/annotation_source/notes）
- [ ] `finish_genome_integration.sh`：GROUP 默认映射补 `HH) Barley`、`HHHH) Barley`、`HHHHHH) Barley`（或统一 `--group` 传入）
- [ ] `app/api/routers/blast.py`：确认 `hordeum_` 关键词可覆盖新库名（已是 barley 分类；必要时补 `wild_barley`）
- [ ] 静态页 `app/static/docpages/jbrowse.html`：HH 卡片追加；HHHH/HHHHHH 新分区与计数；`interval/PfamSearch/caps` 的 `groups` 数组（若需要）
- [ ] 可选：TE 轨道（panEDTA GFF → JBrowse CanvasFeatures），与 Aegilops4 的 TE 轨道一致

## 6. 风险
| 风险 | 处理 |
|---|---|
| ENA 组装与 e!DAL 注释 seqid 不一致 | P1/P2 逐基因组比对；不一致时用 ENA 组装报告或回退 Galaxy assemblies tar |
| 多倍体只发布了部分亚基因组组装 | ploidy 按实际 GFF seqid 判定；缺亚基因组的基因组暂缓并在清单标注 |
| H. marinum H559 组装拿不到 | 从原文 ref29 追溯（ENA/NCBI 其他项目）；拿不到则本批仅 23 个 |
| e!DAL 下载被限速/中断 | 断点续传 + 重试 + md5/大小校验；夜间跑 |
| 24 个基因组流水线时间/磁盘 | 分批（3–4 个/批），失败隔离重跑；磁盘预留 500 GB |
| getfasta 别名 200 成员上限 | 已升级 `update_blast_alias.py --allow-overlimit`（前插），但需留意尾部成员可读性；必要时用 base+delta 合并 |
| 平台计数/卡片遗漏 | P6 逐项断言 + accept 脚本模板 |

## 7. 交付物
- 24 个 `HH/HHHH/HHHHHH_Hordeum_*` 数据集：BLAST（整基因组+染色体拆分+CDS/PEP）、`Genefunc_*_table`、ChineseSpring02G 映射、JBrowse（refSeqs + all_gene；可选 TE 轨道）、getfasta/PrimerServer2/registry 全链路
- 清单/日志/验收报告：`docs/plans/panhordeum_2026-11/`
- 仓库代码改动（registry overrides、SOP、卡片/计数）

---

## 8. 追加基因组（2026-11-19）：四倍体 *Hordeum brevisubulatum*（GWH KGTW）

| 项 | 值 |
|---|---|
| 论文 | Xinying Liu et al. (2026) *The genome of tetraploid Hordeum brevisubulatum underpins its evolution and saline–alkali adaptation*, **The Plant Journal 128, e71199**, DOI [10.1111/tpj.71199](https://doi.org/10.1111/tpj.71199) |
| 材料 | 野生四倍体 *H. brevisubulatum*（黑龙江安达盐碱地采集），A/B 两个亚基因组 |
| 组装 | **GWHKGTW00000000.1**（CNCB-GWH，PRJCA042803，SAMC8834885），7,036,492,017 bp，14 条染色体，BUSCO 99.3%，HiFi 81× + Hi-C 146× |
| 注释 | 140,614 个蛋白编码基因（A 70,754 / B 69,860）、13,811 ncRNA、重复序列 89.35%；**注释文件未公开**（GWH 无 reannotation；GSA CRA027824 只有原始测序数据） |
| 平台现状 | **没有**（已查 registry/Genefunc/JBrowse/BLAST） |
| 拟接入 | ploidy=`HHHH`；DS=`HHHH_Hordeum_brevisubulatum_GWHKGTW`；subgenomes=A,B；Group=Barley |
| 数据状态 | 组装 FASTA 公开（GWH，2.0 GB gz，已加入下载队列）；**GFF/CDS/PEP 需向作者索取** |

**作者联系**：Su Chen <chensu@nefu.edu.cn>、Xingguo Lan <lanxingguo@nefu.edu.cn>、Xiangdong Fu <xdfu@genetics.ac.cn>（东北林业大学 / 中科院遗传发育所）。
**备选**：若拿不到作者注释，可用 PanHordeum 二倍体 *H. brevisubulatum* PI401390 注释做投影（不推荐，需单独评估）；或自行跑 EGAPx（约 7 Gb 基因组，2–3 天，需 RNA-seq 证据，CRA027824 有盐碱胁迫转录组可用）。

---

## 9. 运维修复记录（2026-11-23/24）

### 9.1 BCC2023 / BCC2025 组装不完整（已修复）
- 现象：`H. flexuosum BCC2023` 只有 1.63/3.53 Gb（46%）、`H. parodii BCC2025` 只有 2.85/10.90 Gb（26%）；基因分别丢失 55% / 28%
- 根因：批量下载时 ENA 响应被截断但 curl 静默退出；normalizer 对缺失 seqid 采用"丢弃并计数"
- 修复：按 ENA 记录用 wget 单流完整重下并校验碱基总数
  - flexuosum `GCA_973576695`：3,527,497,938 bp / 299 seqs
  - parodii `GCA_986451185`：10,897,801,576 bp / 1,629 seqs
- 重跑后：flexuosum 64,690 基因 / 99,697 mRNA；parodii 219,254 基因 / 223,335 mRNA；`missing_seqids=0`；G3 SUCCESS、G4 失败计数 0

### 9.2 流水线加固（`scripts/add_wheat_genome.sh` 已入仓库）
1. **跳过旧 BLAST 索引**：`genome_*` 通配会把上一轮的 `.ndb/.nhr/.nin` 当 FASTA 输入 → 只处理 `<DS>.genome_Chr*` 纯 FASTA
2. **EggNOG 残留清理**：运行 emapper 前删除 `*_annotation.emapper.*`，避免 `Output files detected in disk` 中止

### 9.3 上线验收（2026-11-24）
- 平台总计 **352** 个基因组；flexuosum/parodii 的 registry（HH→H，HHHHHH→H,H,H）、Genefunc（99,697 / 223,335 行）、JBrowse（299 / 1,629 refSeqs + all_gene 轨道 + 卡片）、BLAST（20 个库，Barley 分类）、聚合库别名、`by-interval`/`by-gene` API 全部通过
- News 合并为**单条统一公告**（2026-11-24：24 个野生大麦 + Keumkang），删除此前的 2 条分次公告，避免重复表述
