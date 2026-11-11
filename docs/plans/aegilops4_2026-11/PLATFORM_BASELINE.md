# PLATFORM_BASELINE — 4 个二倍体 Aegilops（M/C/U/N）平台现状与代码接入点基线

> 任务：共享任务板 `task-2`（owner: platform-baseline）。
> 论文：Khadka et al., BMC Plant Biology 2026, DOI `10.1186/s12870-026-10046-2`；注释数据 Zenodo record `22681907`。
> 审计时间：2026-11-11 17:54–18:20 CST。
> 证据来源：① 线上只读 API `https://wheatomics.sdau.edu.cn/api/...`；② 本仓库（HEAD `22a7157`，工作树另有 1 处与本任务无关的未提交改动 `app/api/routers/blast.py`，本项目未触碰）；③ 技能资产 `~/.agents/skills/lab-server/scripts/finish_genome_integration.sh`（2026-11-09 版）；④ task-1 已下载到 `docs/plans/aegilops4_2026-11/zenodo_probe/` 的 Zenodo 文件（GFF 实测计数）。
> 约束遵守：未改任何仓库源码、未 git commit、未访问生产服务器；本文件是本任务唯一产出。

---

## 0. 结论速览（先看这张表）

| 物种（基因组） | 平台现状（实测） | 推荐数据集名 `DS=${PLOIDY}_${MYTAG}` | 命名门禁 `--check-name` 结论 | 运行时 BLAST 分类 | JBrowse 落点 |
|---|---|---|---|---|---|
| *Ae. comosa*（M） | 1 条：`Aegilop_comosa_PI551049`（MM，annotation_status=**none**） | **`MM_Aegilops_comosa_IPK_AE783`** | 改代码后仅剩“收尾脚本 optgroup 环节过期”一个系统性问题；见 §3 | `other_triticeae`（与既有 MM/UU 一致） | 既有 `#group-mm` 加 1 卡 |
| *Ae. markgrafii*（C） | **0 条** | **`CC_Aegilops_markgrafii_EKC105_RL5723`** | 现在 **BLOCK**（`SUB[CC]` 缺失 + 分类 `other`）；需 2 处代码修改 | `other_triticeae`（需补关键词，见 §3.6） | **新建 `#group-cc`** |
| *Ae. umbellulata*（U） | 2 条：`…_PI554389`（annotation none）、`…_TA1851`（available） | **`UU_Aegilops_umbellulata_IPK_AE740`** | 分类/SUB 均通过；仅剩 optgroup 环节 | `other_triticeae` | 既有 `#group-uu` 加 1 卡 |
| *Ae. uniaristata*（N） | **0 条** | **`NN_Aegilops_uniaristata_IPK_AE680`** | 现在 **BLOCK**（`SUB[NN]` 缺失 + 分类 `other`）；需 2 处代码修改 | `other_triticeae`（需补关键词） | **新建 `#group-nn`** |

**一句话**：平台目前只有 3 条相关条目（M×1、U×2，C/N 为 0）；四个新基因组若按 `other_triticeae` 分类（与既有 Aegilops 行为一致）并采用“全物种名 + 下划线登录号”的 `${PLOIDY}_${MYTAG}` 命名，只需改 **3 个仓库文件 + 1 个收尾脚本 + 2 个前端页面** 即可过门禁；**没有**能让 C/N 零改动过门禁的命名方案（`markgrafii`/`uniaristata` 不在任何 `DB_CLASSIFICATION` 关键词里，且 `SUB` 映射缺 CC/NN）。

**最大风险**：`finish_genome_integration.sh --check-name` 的第 3/4 步按 **旧版** `blast.html`（手写 `<optgroup>`）和 **旧版** `jbrowse.html`（`<h5>` 分区 + `card-group`）设计；而线上这两个页面已在 2026-10/11 重写为新版（BLAST 2.0 动态分类、JBrowse 2.0 `asm-card`/`asm-group`）。实测线上 `blast.html` 的 `<optgroup>` 数量为 **0**，新版 `jbrowse.html` 无 `<div id="cite"></div>` 锚点 → **任何基因组现在跑 `--check-name` 都会被第 3 步 BLOCK**（不区分倍性）。详见 §6 R1。

---

## 1. 审计方法与证据口径

| 项 | 值 |
|---|---|
| API 根 | `https://wheatomics.sdau.edu.cn/api`（只读 GET；服务器返回 `timestamp` 2026-11-11T09:53Z 起） |
| 仓库 | `/Users/mashengwei/Desktop/markdown/wheatomics/FastAPI_backend_Port8000`，HEAD `22a7157`（2026-11-11 16:21） |
| 收尾脚本 | `~/.agents/skills/lab-server/scripts/finish_genome_integration.sh`，1022 行，2026-11-09 19:50；服务器副本按 SOP 在 `/var/www/data/masw_data/_prep/finish_genome_integration.sh` |
| 生产服务器 | **未访问**（SSH 不可用）。所有“服务器侧文件”结论来自线上 HTTP 页面/API 与仓库代码，非 SSH |
| `--check-name` 实测 | 将收尾脚本复制到 `/tmp` 并把 `REPO` 指向本仓库、`BLAST_HTML`/`JBROWSE_HTML` 指向**线上抓取的真实页面**、`BLASTDB` 指向空目录后执行（不改线上任何东西）；MySQL 不可达时脚本自身会 fallback（`display_order=500`）。输出摘录见 §3.4 与附录 A |
| 论文/注释数据 | Zenodo README（`zenodo_probe/README_zenodo_diploid_Aegilops.md`）与已下载 GFF 实测；未登录/未沉淀项标注“待 task-1 核实” |

---

## 2. 线上平台基线（全部为实测）

### 2.1 `/api/genomes/stats` 总览（2026-11-11）

```json
"totals": {"total":316,"jbrowse":"215","gene_function":"214","getfasta":"199",
           "primerserver":"203","web_blast":"200","synteny":"86","orthofinder":"43"}
"by_annotation_status": [{"none":104},{"pending":1},{"available":211}]
```

| by_ploidy（与本批相关） | n | 说明 |
|---|---|---|
| MM | 1 | `Aegilop_comosa_PI551049` |
| UU | 2 | `Aegilops_umbellulata_PI554389`、`…_TA1851` |
| CC | **0** | 无独立分组行（stats 不返回 n=0 的组） |
| NN | **0** | 同上 |
| DD | 11 | 10 条 Ae. tauschii + `DD_Aegilops_tauschii_Jia` |
| AA | 5 | Triticum monococcum / urartu 系 |
| SS | 10 | Sitopsis（Aegilops speltoides/longissima/sharonensis/searsii/bicornis/y2032） |
| TT | 1 | `Aegilops_mutica` |
| VV / EE / RR / II | 1 / 1 / 3 / 1 | Dasypyrum / Thinopyrum elongatum / rye / Hordeum brevisubulatum |
| MMUU | 1 | `Aegilops_geniculata` |
| DDNN | 1 | `RM271`（Ae. ventricosa） |
| AABBDD 102、AABB 22、AABBRR 2、HH 104、HHHH 24、PPPP 2、null 14 等 | — | 与本批无关，仅作总量核对：合计 **316** |

> 证据：`GET /api/genomes/stats`（上方 JSON 为原样摘录）。
> 备注：`total=316` 只统计 `visible=1`。`GET /api/genomes?limit=500&include_hidden=true` 返回 **318** 行（2 条隐藏）。

### 2.2 4 个物种的既有条目全表（`GET /api/genomes?q=<species>`）

| 查询 | 命中 | 关键结论 |
|---|---|---|
| `q=comosa` | 1 | 有，但 `annotation_status=none`（其 gene_table 实际存在，见 §6 R9） |
| `q=umbellulata` | 2 | 有 2 条不同登录号的 UU 条目（PI554389 未生成基因表） |
| `q=markgrafii` | **0** | 平台从未收录 |
| `q=uniaristata` | **0** | 平台从未收录 |
| `q=Aegilops`（含近缘种） | 25 | DD 11（tauschii）+ SS 9（Sitopsis）+ UU 2 + DDNN 1（RM271）+ MMUU 1（geniculata）+ TT 1（mutica）；**注意：既有 comosa 行 `Aegilop_comosa_PI551049` 因 dataset_id/species 拼写缺 s，`q=Aegilops` 搜不到它**（拼写坑见 §6 R21） |

**既有 3 条目的逐字段实测**（`GET /api/genomes?q=…`，字段取自返回 `items[]`）：

| 字段 | `Aegilop_comosa_PI551049` | `Aegilops_umbellulata_PI554389` | `Aegilops_umbellulata_TA1851` |
|---|---|---|---|
| species | Aegilop comosa | Aegilops umbellulata | Aegilops umbellulata |
| ploidy / subgenomes | MM / M | UU / U | UU / U |
| cultivar_or_line | Aegilop comosa PI551049 | Aegilops umbellulata PI554389 | Aegilops umbellulata TA1851 |
| assembly_accession | null | null | null |
| assembly_level / chromosome_count | Chromosome / 7 | Chromosome / 7 | Chromosome / 7 |
| genome_size (bp) | 4,470,000,000 | 4,230,000,000 | 4,230,000,000 |
| gene_count | 39,057 | 78,076 | 36,268 |
| te_content | 0.863 | 0.841 | 0.823 |
| DOI / journal / year | 10.1038/s41597-024-04346-1 / Scientific data / 2024 | 10.1111/pbi.14470 / Plant biotechnology journal / 2024 | 10.1038/s41588-023-01401-2 / Nature genetics / 2023 |
| annotation_status | **none** | **none** | **available** |
| gene_table | `Genefunc_MM_AeComosa_PI551049_table` | null | `Genefunc_UU_Aegilops_umbellulata_TA1851_table` |
| jbrowse_dataset | Aegilop_comosa_PI551049 | Aegilops_umbellulata_PI554389 | Aegilops_umbellulata_TA1851 |
| flags | jbrowse1 / getfasta1 / primer1 / web_blast1 / gene_ui1 / synteny0 / ortho0 | jbrowse1 / getfasta1 / primer1 / web_blast1 / **gene_ui0** / synteny0 / ortho0 | jbrowse1 / getfasta1 / primer1 / web_blast1 / gene_ui1 / synteny0 / ortho0 |

**新登录号是否存在（全平台，含隐藏行）**：

| 查询 | 结果 | 覆盖范围 |
|---|---|---|
| `q=AE783`、`q=AE740`、`q=AE680`、`q=EKC105`、`q=RL5723`、`q=IPK`、`q=IPK-AE`、`q=EKC`、`q=RL57` | **全部 `total=0`** | `/api/genomes` 的 dataset_id/display_name/species/cultivar_or_line 四个字段（`app/api/routers/genome.py:132-136`） |
| BLAST 库名扫描（2924 个核酸库 + 193 个蛋白库） | 0 命中 | `/api/blast/databases` 全量名字串匹配 |
| JBrowse 数据集（219 个） | 0 命中 | `/api/jbrowse/datasets` 全量 id |

> 结论：**4 个新登录号在平台上完全不存在**，不存在替换/合并冲突，可以“新增并存”。

### 2.3 BLAST 库基线（`GET /api/blast/databases`）

| 指标 | 实测值 |
|---|---|
| 核酸库总数 | **2924**（kind_counts：genome 218 / chromosome 2401 / cds 191 / other 111 / aggregate 3） |
| 蛋白库总数 | **193**（protein 192 / aggregate 1） |
| 合计 | **3117** |

**分类计数（核酸 / 蛋白）**：

| category id | label | nuc | prot |
|---|---|---|---|
| aggregated | All-in-one | 39 | 1 |
| hexaploid_wheat | Hexaploid wheat | 1198 | 54 |
| tetraploid_wheat | Tetraploid wheat | 326 | 18 |
| **diploid_wheat** | **Diploid wheat genome and wild relatives** | **164（仅 AA/DD）** | **15** |
| triticale | Triticale | 46 | 2 |
| thinopyrum_ponticum | Th. ponticum | 3 | 1 |
| rye | Rye | 26 | 1 |
| **other_triticeae** | **Other Triticeae genome** | **439** | **31** |
| barley | Barley | 665 | 70 |
| other | Other / Unclassified | 18 | 0 |
| 合计 | | **2924** | **193** |

**4 物种相关库的现状**（库名 → 归属）：

| 物种 | 核酸库 | 蛋白库 | 归属 |
|---|---|---|---|
| comosa（PI551049） | 10 个：`MM_AeComosa_PI551049.{genome, genome_Chr1M…Chr7M, genome_ChrUn, add_Description.cds}` | 1 个 `.add_Description.pep` | `other_triticeae` |
| umbellulata（PI554389） | 9 个：`UU_Aegilops_umbellulata_PI554389.{genome, Chr1U…Chr7U, ChrUn}`（**无 cds/pep**） | 0 | `other_triticeae` |
| umbellulata（TA1851） | 9 个：`.{genome, Chr1U…Chr7U}` + `.add_Description.cds`（无 ChrUn） | 1 个 `.pep` | `other_triticeae` |
| markgrafii / uniaristata | **0** | **0** | — |

> 既有 Aegilops/geniculata/mutica 库全部落在 `other_triticeae`（连 `MMUU_Aegilops_geniculata`、`TT_Aegilops_mutica` 也是），只有 tauschii（DD）在 `diploid_wheat`。这是“平台事实上的分类约定”，新条目的推荐落点即 `other_triticeae`。

### 2.4 JBrowse 基线（`GET /api/jbrowse/datasets` + `app/static/docpages/jbrowse.html`）

| 指标 | 实测值 | 证据 |
|---|---|---|
| JBrowse 数据集目录/`jbrowse_meta` 行 | **219** | `GET /api/jbrowse/datasets` → `data.total=219`（数据源是 `jbrowse_meta.jbrowse_datasets`，见 `app/api/routers/jbrowse.py:61-88`） |
| genome_registry 中 `jbrowse_dataset` 非空 | **215** | `/api/genomes/stats` → `totals.jbrowse=215` |
| 有目录但不在 registry 的 4 个 | `KeNong9204`、`Secale_cereale`、`fangenome`、`rye_weining2.0` | 集合差集计算 |
| 文档页 `?data=` 链接 | **213** | `grep -o '?data=' app/static/docpages/jbrowse.html` = 213 |
| 可见卡片 `article.asm-card` | **206** | 页面内计数（22 个 section 内 card 求和） |
| 隐藏占位卡 | 7（`asm-placeholders`，`jbrowse.html:1132`） | 206+7=213，正好等于 hero 数字 |
| hero 数字 | `213`（`jbrowse.html:68`） | 手工硬编码 |
| section 数（`section.asm-group`） | **22** | 逐 section 计数；JS 在加载后用 DOM 重算 `Showing 206 named assemblies in 22 genome groups`（`jbrowse.html:82`、`1209`） |
| “Jump to” chips | 6 个：AABBDD 55 / AABB 22 / DD 10 / SS 9 / AA 5 / HH 82 | `jbrowse.html:96-101`（手工硬编码，JS **不**重算） |

**22 个 section 的 id 与卡片数**（供定位插入点）：

| section id | 卡片数 | 相关 | section id | 卡片数 | 相关 |
|---|---|---|---|---|---|
| `#group-aabbdd` | 55 | | `#group-vv` | 1 | |
| `#group-aabb` | 22 | | `#group-sshh` | 1 | |
| `#group-aagg` | 1 | | `#group-ststyyhh` | 3 | |
| `#group-aa` | 5 | | **`#group-uu`** | **2** | 需 +1 |
| `#group-dd` | 10 | | **`#group-mm`** | **1** | 需 +1 |
| `#group-aabbrr` | 2 | | `#group-tt` | 1 | |
| `#group-hh` | 82 | | `#group-ee` | 1 | |
| `#group-rr` | 3 | | `#group-vvjjss` / `#group-ststvvjj` | 1 / 1 | |
| `#group-ss` | 9 | | `#group-ddnn` / `#group-nsnsxmxm` / `#group-mmuu` | 1 / 1 / 1 | |
| | | | `#group-thinopyrum` | 2 | |

**与 4 物种相关卡片**（当前仅 3 张）：

| 卡片 | 所在 section | 行号 | `?data=` |
|---|---|---|---|
| `Ae.umbellulata TA1851(UU)` | `#group-uu` | `jbrowse.html:997-1000` | `Aegilops_umbellulata_TA1851` |
| `Ae.umbellulata PI554389(UU)` | `#group-uu` | `jbrowse.html:1001-1005` | `Aegilops_umbellulata_PI554389` |
| `Ae.comosa PI551049(MM)` | `#group-mm` | `jbrowse.html:1014-1018` | `Aegilop_comosa_PI551049` |

> 无 `#group-cc`、`#group-nn`。

### 2.5 Genefunc 基线（`/api/genes/functions/{registry,tables,examples}`）

| 指标 | 实测值 | 证据 |
|---|---|---|
| `Genefunc_registry` 行数 | **216** | `GET /api/genes/functions/registry` → `data.count=216` |
| `Genefuncdb` 中的表数 | **224** | `GET /api/genes/functions/tables` → `data.total_tables=224` |
| `/api/genes/functions/examples` 条目 | **216** | 与 registry 一致；karyotype 分布：HH 79 / AABBDD 73 / AABB 20 / DD 10 / SS 10 / AA 5 / StStYYHH 3 / AABBRR 2 / StStVVJJ 2 / DDNN 2 / RR 2 / AAGG 1 / NsNsXmXm 1 / EE 1 / **MM 1** / **TT 1** / **UU 1** / VV 1 / Thinopyrum ponticum 1 |

**`Group` 列的实际取值（关键：没有 “Diploid”）**：

| Group 值 | 行数 |
|---|---|
| NULL | 182 |
| Allohexaploid | 25 |
| Tetraploid | 3 |
| Other Triticeae | 2 |
| Triticale | 2 |
| Barley / Thinopyrum ponticum | 1 / 1 |

**`Polyploidy` 列的实际取值**：HH 79、AABBDD 73、AABB 20、DD 10、SS 10、AA 5、StStYYHH 3、DDNN 2、RR 2、StStVVJJ 2、AABBRR 2、AAGG/EE/**MM**/NsNsXmXm/**TT**/**UU**/VV/Thinopyrum ponticum 各 1（合计 216）。**没有 CC、NN**。

**Aegilops 相关 registry 行（24 条）关键字段**（完整列表略，按需 `q=tables` 复核）：

| id | table_name | display_name | group | polyploidy |
|---|---|---|---|---|
| 351 | `Genefunc_MM_AeComosa_PI551049_table` | Ae. comosa PI551049 | NULL | MM |
| 356-364 | `Genefunc_SS_ae_{bicornis,longissima,searsii,sharonensis,speltoides}*` | Sitopsis 9 条 | NULL | SS |
| 370 | `Genefunc_TT_Aegilops_mutica_table` | Aegilops mutica | NULL | TT |
| 371 | `Genefunc_UU_Aegilops_umbellulata_TA1851_table` | Aegilops umbellulata TA1851 | NULL | UU |
| 63 | `Genefunc_ae_longissima_TAEG67822_table` | Ae. longissima TAEG67822 | **Other Triticeae** | SS |
| 69 | `Genefunc_Ae_ventricosa_RM271_table` | Ae. ventricosa RM271 | **Other Triticeae** | DDNN |
| 261-271 | `Genefunc_DD_*`（tauschii 11 条） | — | NULL | DD |

> 注意：`/api/genes/functions/examples` 中大部分 Aegilops 行（含 comosa PI551049、umbellulata TA1851）的 `region`/`gene` 示例为 **空**——历史行没有填 `example_*` 字段。新条目如果走收尾脚本会正确填 `example_species_chr_id` 等，属改进。
> `Genefunc_registry` **没有 “Diploid” Group 值**（只有 216 行里的 182 个 NULL + 6 种取值）。这一点直接影响 §3.5 的推荐值。

### 2.6 PrimerServer2 基线（`GET /api/PrimerServer2/databases`）

| group | 数量 | 本批相关 |
|---|---|---|
| `genome` | **203** | 含 `MM_AeComosa_PI551049.genome`、`UU_Aegilops_umbellulata_PI554389.genome`、`UU_…TA1851.genome`、`MMUU_Aegilops_geniculata.genome`、`TT_Aegilops_mutica.genome` 等 14 个 Aegilops 相关 `.genome` |
| `gene` | **194** | 含 `MM_AeComosa_PI551049.add_Description.cds`、`UU_…TA1851.add_Description.cds` 等 11 个 Aegilops 相关 `.add_Description.cds` |

> PrimerServer2 动态扫描 `BLAST_DB_PATH`（SOP 5.4），**不需要改代码**；只要求补 `.fai`（`samtools faidx`）。

### 2.7 getfasta 聚合库基线

| 指标 | 实测值 | 证据 |
|---|---|---|
| `all_genomes` 序列（seqid）总数 | **115354** | `GET /api/sequence/chromosomes?database=all_genomes` → `data.count=115354` |
| comosa PI551049 在其中 | 8 条：`Chr1M_AeComosa_PI551049`…`Chr7M_…` + `ChrUn_AeComosa_PI551049` | `…&pattern=comosa` |
| umbellulata 在其中 | 15 条：PI554389 8 条（7+ChrUn）+ TA1851 7 条 | `…&pattern=umbellulata` |
| markgrafii / uniaristata | **0** | 同 pattern 查询 |

> `all_genomes` 由 `scripts/rebuild_getfasta_aggregates.py` 动态维护（`app/services` 之外的脚本层），新基因组通过收尾脚本第 5 步（`finish_genome_integration.sh:733-774`）或重跑该脚本加入。**关键**：`is_chrom()` 优先看是否存在 `<db>_Chr*.nhr` 拆分索引（`scripts/rebuild_getfasta_aggregates.py:236-244`），所以 Aegilops 这种 7 条染色体的组装即使 registry 的 `assembly_level` 没填也能进 `all_genomes`；但 registry 的 `assembly_level`/`chromosome_count` 仍需单独修（§6 R8）。

### 2.8 论文/数据侧对基线的补充（来自 task-1 的 Zenodo 实测，供计数增量使用）

| 项 | Ae. comosa | Ae. markgrafii | Ae. umbellulata | Ae. uniaristata |
|---|---|---|---|---|
| 论文登录材料 | IPK-AE783 | EKC105_RL5723（原 PGRC CN 34579 / PGR 6682） | IPK-AE740 | IPK-AE680 |
| NCBI BioProject（README） | PRJNA1506336 | PRJNA1174795 | PRJNA1114735 | PRJNA1154594 |
| 蛋白编码基因（README） | 51,205（HC 37,623 / LC 13,582） | 47,246（34,133 / 13,113） | 49,677（35,799 / 13,878） | 50,416（35,816 / 14,600） |
| GFF 实测 gene=mRNA | **51,203**（HC 37,622） | **47,246**（HC 34,133） | **49,677** | 审计时文件仍在下载（9,471，**待 task-1 完成**） |
| Repeat content | 88.2% | 86.3% | 87.2% | 87.9% |
| 染色体 seqid（GFF 第一列） | `1M`…`7M` + 8 个 Super-Scaffold | `1C`…`7C` + 7 个 scaffold | `1U`…`7U` + **181** 个 ptg/Super_scaffold | 待核实 |
| 蛋白 fasta 头 | `>evm.model.1M.1 gene=…` | `>model.model.STRG…` | 带坐标描述 | 待核实 |

> 注意：README 的“Total protein-coding genes”与 GFF 实测相差 1–2 条（comosa 51,205 vs 51,203）；以流水线导入后的**实测 mRNA 行数**为准，论文值写 `gene_count` 时建议用 GFF 实测值并在 notes 注明口径。
> **跨物种重复 mRNA ID**：3 个已下载物种的 GFF 中 `model.model.STRG.*` 系 ID 存在大量重名——comosa∩markgrafii 1,240、comosa∩umbellulata 1,321、markgrafii∩umbellulata 1,302，三物种共有 203，去重后并集 144,466 < 总和 148,126（重复 3,457）。见 §6 R10。

---

## 3. 命名门禁（`finish_genome_integration.sh --check-name`）与分类判定

### 3.1 门禁逻辑拆解（脚本行号）

`check_name()` 位于 `~/.agents/skills/lab-server/scripts/finish_genome_integration.sh:149-365`，依次检查：

| 步骤 | 行号 | 检查内容 | 不通过即 `ok=False`（脚本最终 rc=3） |
|---|---|---|---|
| 0 | ~171-186 | 材料身份：`--cultivar` 或 `--accession` 至少一个；`--paper-code` 不能单独用 | 是 |
| 1 | 191-204 | 从仓库 `scripts/rebuild_genome_registry.py` 解析 `SUB` 映射，要求 `SUB[PLOIDY]` 存在 | 是 |
| 2 | 206-235 | 用仓库 `app/api/routers/blast.py` 的 `DB_CLASSIFICATION` 对 `DS+{.genome,.cds,.pep}` 做子串分类，结果不能是 `other`；可配合 `--expect-category` 断言 | 是 |
| 3 | 236-248 | 读 `/var/www/html/blast/blast.html` 的 `<optgroup label="…">`，按 `Group` 映射到目标 optgroup 且必须存在 | 是 |
| 4 | 249-269 | 读 `/var/www/html/jbrowse.html` 的 `<h5>&nbsp;…</h5>` 分区；给了 `--section-existing` 则必须存在 | 只警告（除非给 `--section-existing`） |
| 5 | 270-286 | 用 `blastdb` 目录估算 PrimerServer2 字母序位置 | 否（仅打印） |
| 6 | 287-300 | 查 MySQL `MAX(display_order)+1 WHERE Polyploidy=…`，失败 fallback 500 | 否（仅警告） |

默认 `GROUP` 映射（`finish_genome_integration.sh:354-361`）：`AABB→Tetraploid`、`AABBDD→Hexaploid`、`AABBRR→Triticale`、`DD|AA|BB|UU|HH|AABBCC→Diploid`、**其他（含 MM/CC/NN）→Other**。
第 3 步的 `gmap`（`:237-238`）：`Other → "Other Triticeae genome"`、`Diploid → "Diploid wheat genome"`。

**前置绑定关系**：`add_wheat_genome.sh` 启动时会校验 `<data_path>/name_plan.json` 的 `ds == PLOIDY_MYTAG`（SOP §0.5、`:147`），所以门禁必须先过、名字必须一次定死（DS 会绑定目录/BLAST 库名/MySQL 表名/JBrowse 数据集）。

### 3.2 候选数据集名判定表（主表）

> 判定口径：假设材料身份用 `--accession` 提供；`SUB` 与 `DB_CLASSIFICATION` 的“改前”= 当前仓库 HEAD；“改后”= 按 §4 建议修改后。`--check-name` 结果来自 §3.4 的实测模拟。

| # | 候选 `DS` | `SUB[PLOIDY]` 改前→后 | `DB_CLASSIFICATION`（改前） | 分类（改后） | 运行时 BLAST 分类（registry 行存在后） | `--check-name` 改前 | `--check-name` 改后* | JBrowse 落点 | Genefunc `Group`/`Polyploidy` 建议 | `Genefunc_<DS>_table` 长度 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **`MM_Aegilops_comosa_IPK_AE783`**（推荐） | `M` → `M` | **other_triticeae**（关键字 `aegilops_comosa`） | other_triticeae | other_triticeae | BLOCK（仅 step 3） | 仅 step 3（脚本未修）/ OK（`--group "Other Triticeae"`） | 既有 `#group-mm` | Other Triticeae / MM | 43 |
| 2 | `MM_AeComosa_IPK_AE783`（短名备选） | `M` | other_triticeae（`aecomosa`） | other_triticeae | other_triticeae | BLOCK（仅 step 3） | 同 #1 | 既有 `#group-mm` | Other Triticeae / MM | 36 |
| 3 | **`CC_Aegilops_markgrafii_EKC105_RL5723`**（推荐） | **缺失 → `C`** | **other** ❌ | other_triticeae（补 `markgrafii`/`aegilops_markgrafii`） | other_triticeae | BLOCK（step 1+2+3） | 仅 step 3 / OK（`--group "Other Triticeae"`） | **新建 `#group-cc`** | Other Triticeae / CC | 51 |
| 4 | `CC_AeMarkgrafii_EKC105_RL5723`（短名） | 缺失 → C | other | 需补 `aemarkgrafii` 等短关键词 | other_triticeae | BLOCK | 同 #3（多补 1 个关键词） | 新建 `#group-cc` | Other Triticeae / CC | 44 |
| 5 | **`UU_Aegilops_umbellulata_IPK_AE740`**（推荐） | `U` → `U` | other_triticeae（`aegilops_umbellulata`） | other_triticeae | other_triticeae | BLOCK（仅 step 3；step 3 目标是 “Diploid wheat genome”，但该页已无 optgroup） | 仅 step 3 / OK（`--group "Other Triticeae"`） | 既有 `#group-uu` | Other Triticeae / UU | 48 |
| 6 | `UU_AeUmbellulata_IPK_AE740`（短名） | `U` | **other** ❌（`aeumbellulata` 不是关键词） | 需补短关键词 | other_triticeae | BLOCK（step 2+3） | 同 #5 | 既有 `#group-uu` | Other Triticeae / UU | 41 |
| 7 | **`NN_Aegilops_uniaristata_IPK_AE680`**（推荐） | **缺失 → `N`** | **other** ❌ | other_triticeae（补 `uniaristata`/`aegilops_uniaristata`） | other_triticeae | BLOCK（step 1+2+3） | 仅 step 3 / OK（`--group "Other Triticeae"`） | **新建 `#group-nn`** | Other Triticeae / NN | 48 |
| 8 | `NN_AeUniaristata_IPK_AE680`（短名） | 缺失 → N | other | 需补短关键词 | other_triticeae | BLOCK | 同 #7 | 新建 `#group-nn` | Other Triticeae / NN | 41 |

\* “改后”指 §4 的 SUB + 关键词修改已 push 到服务器仓库；但 step 3（旧 `blast.html` optgroup）是**脚本与新版前端的结构性错配**，不修脚本时仍 BLOCK——用 `--group "Other Triticeae"` 可绕过（该值不在 `gmap` 里 → `want=""` → 不检查 optgroup；实测因此得到 `[OK] 命名可直接开跑`）。

**点名“命中哪个 JBrowse 分区 / BLAST optgroup / 关键词”：**

- JBrowse 分区：`MM → #group-mm`（`jbrowse.html:1008-1019`）；`UU → #group-uu`（`:991-1006`）；`CC/NN → 新建 #group-cc / #group-nn`（建议插在 `#group-tt`（`:1021-1032`）与 `#group-ee`（`:1034-1045`）之间）。
- BLAST optgroup：**新版 `/blast/blast.html`（BLAST 2.0 SPA）没有手写 optgroup**，分类完全由 `/api/blast/databases` 的 `categories[]` 动态渲染（`app/static/blast2/index.html:1672`、`:2098-2121`）。新库将落在 `label="Other Triticeae genome"` 的 `other_triticeae` 分类里。
- 需新增的 `DB_CLASSIFICATION` 关键词：`markgrafii`、`uniaristata`（建议同时加 `aegilops_markgrafii`、`aegilops_uniaristata` 以匹配全名）。`comosa`/`umbellulata` 已有关键词（`aegilops_comosa`、`aecomosa`、`aegilops_umbellulata`）。
- 需新增的 `SUB` 映射：`"CC": "C"`、`"NN": "N"`。
- 候选表（推荐名）**不需要**任何 `genome_ordering._CANONICAL` 之外的映射即可让 `karyotype_ploidy=2`（`"CC"`/`"NN"` 当前走 raw 值也能算对），但 `infer_karyotype` 在 `Polyploidy` 为空时会退化到 `Other`（§6 R5），故仍建议补 `_CANONICAL`。

### 3.3 候选名变体（连字符 / 点号）风险对照

| 变体 | 分类可过？ | 风险 |
|---|---|---|
| `MM_AeComosa_IPK-AE783`（保留连字符） | ✅（`aecomosa` 子串） | `dataset_id` 允许连字符（`app/api/routers/genome.py:33` `^[\w.\-]+$`；BLAST 库名允许 `-`），但 MySQL 表名 `Genefunc_MM_AeComosa_IPK-AE783_table` 带 `-`：收尾脚本的 `SELECT COUNT(*) FROM Genefunc_${DS}_table`（`:908`）未加反引号会报 SQL 错；流水线很可能把 `-` 规整为 `_`，导致 `Genefunc_registry.table_name` 与真实表名不一致。**不推荐** |
| `CC_ae.markgrafii.EKC105_RL5723`（用 `ae.` 子串过分类） | ✅（命中 `ae.` 关键词） | 依赖“`ae.` 误吞”特性；`DS` 含 `.`，表名同样会被规整/需要转义；且不符合 `${PLOIDY}_${MYTAG}` 的“材料名”可读性要求。**不推荐**，仅作为“完全不想改 blast.py”的兜底 |
| 短名 `MM_AeComosa_…` / `CC_AeMarkgrafii_…` / `UU_AeUmbellulata_…` / `NN_AeUniaristata_…` | M 过、U/C/N 不过 | 与既有 `MM_AeComosa_PI551049` BLAST 库命名风格一致，但需要额外 4 个短关键词（`aemarkgrafii`/`aeumbellulata`/`aeuniaristata`），代码改动更大 |

> 结论：**推荐全物种名 + 下划线登录号**（即 §3.2 的 #1/#3/#5/#7）。数据集 id 与 Zenodo 文件前缀（`Aegilops_comosa_IPK-AE783`）只差一个连字符，建议在 `--accession`、`genome_registry.notes`、`display_name` 中保留原始连字符写法，便于回溯。

### 3.4 `--check-name` 实测模拟（关键输出摘录）

方法：把收尾脚本复制到 `/tmp`，`REPO` 指向本仓库、`BLAST_HTML`/`JBROWSE_HTML` 指向线上抓取的真实页面、`BLASTDB` 指向空目录（MySQL 不可达，脚本自动 fallback）。**以下为真实输出摘录。**

**A. 改前（当前仓库 HEAD）**

```
# MM_AeComosa_IPK_AE783（短名）；推荐全名 MM_Aegilops_comosa_IPK_AE783 的分类/SUB 结果完全相同
SUB[MM] = M
MM_AeComosa_IPK_AE783.genome               -> other_triticeae
Group=Other  → 目标 optgroup: Other Triticeae genome
现有 optgroup : []
WARN blast.html 里没有含 'Other Triticeae genome' 的 optgroup
BLOCK 先解决上面的 WARN 再跑流水线

# CC_Aegilops_markgrafii_EKC105_RL5723
SUB[CC] = (未登记)
CC_Aegilops_markgrafii_EKC105_RL5723.genome -> other
WARN ploidy 'CC' 不在 SUB 映射里
WARN 库名匹配不到任何分类，会掉进 'Other / Unclassified'
BLOCK

# UU_Aegilops_umbellulata_IPK_AE740
SUB[UU] = U
UU_Aegilops_umbellulata_IPK_AE740.genome   -> other_triticeae
Group=Diploid  → 目标 optgroup: Diploid wheat genome
现有 optgroup : []
BLOCK

# NN_Aegilops_uniaristata_IPK_AE680
SUB[NN] = (未登记)
NN_Aegilops_uniaristata_IPK_AE680.genome   -> other
BLOCK
```

**B. 改后（在 `/tmp` 的 fakerepo 副本里给 SUB 加 CC/NN、给 other_triticeae 加 markgrafii/uniaristata 关键词）**

```
# MM / CC：只剩 step 3（旧 blast.html 无 optgroup）一个 BLOCK
WARN blast.html 里没有含 'Other Triticeae genome' 的 optgroup
BLOCK

# NN_Aegilops_uniaristata_IPK_AE680 --group "Other Triticeae"
WARN 该倍性没有对应分区，脚本会新建一个 '<label> JBrowse' 分区（仅提示）
WARN 查 display_order 失败（本机无 /etc/wheatomics/db_ddl.env，回退 500）
[OK] 命名可直接开跑
```

**结论**：
1. C/N 必须做 `SUB` + `DB_CLASSIFICATION` 两项代码修改，**没有零改动命名**；
2. 改完代码后，唯一系统性卡点是收尾脚本第 3 步（旧 `blast.html`）——要么改脚本，要么在正式运行时传 `--group "Other Triticeae"`；
3. 第 4 步 JBrowse 分区检查因为新版页面用 `<h2 class="asm-group-title">` 而永远返回空（旧脚本用 `<h5>` 正则），只出 WARN、不 BLOCK，但 `--section-existing` 因此不可用（对我们的方案无影响：卡片是手工加到 docpages 页面）。

### 3.5 推荐命名与元数据（建议直接写入 `name_plan.json` 的字段）

| 物种 | `PLOIDY` | `MYTAG` | `DS` | 建议 `--label` | `--cultivar` | `--accession` | `--species` | `--group` | JBrowse 卡片目标 |
|---|---|---|---|---|---|---|---|---|---|
| Ae. comosa | `MM` | `Aegilops_comosa_IPK_AE783` | `MM_Aegilops_comosa_IPK_AE783` | `Ae.comosa IPK-AE783 (M)` | `IPK-AE783` | `IPK-AE783`（若 task-1 查到 GCA 号，改填 GCA） | `Aegilops comosa` | `Other Triticeae` | `#group-mm` 追加 |
| Ae. markgrafii | `CC` | `Aegilops_markgrafii_EKC105_RL5723` | `CC_Aegilops_markgrafii_EKC105_RL5723` | `Ae.markgrafii EKC105_RL5723 (C)` | `EKC105_RL5723` | `EKC105_RL5723`（或 GCA） | `Aegilops markgrafii` | `Other Triticeae` | 新建 `#group-cc` |
| Ae. umbellulata | `UU` | `Aegilops_umbellulata_IPK_AE740` | `UU_Aegilops_umbellulata_IPK_AE740` | `Ae.umbellulata IPK-AE740 (U)` | `IPK-AE740` | `IPK-AE740`（或 GCA） | `Aegilops umbellulata` | `Other Triticeae` | `#group-uu` 追加 |
| Ae. uniaristata | `NN` | `Aegilops_uniaristata_IPK_AE680` | `NN_Aegilops_uniaristata_IPK_AE680` | `Ae.uniaristata IPK-AE680 (N)` | `IPK-AE680` | `IPK-AE680`（或 GCA） | `Aegilops uniaristata` | `Other Triticeae` | 新建 `#group-nn` |

- 论文 DOI 统一 `10.1186/s12870-026-10046-2`；journal `BMC Plant Biology`；year `2026`；license 论文与 Zenodo 均 CC-BY-4.0（允许镜像展示）。
- `--paper-code` 可留空（本批材料名/登录号已足够；SOP 规定 paper-code 只能作补充）。
- `Genefunc_registry` 预期：`table_name=Genefunc_<DS>_table`、`Polyploidy=MM|CC|UU|NN`、`Group="Other Triticeae"`（与既有 id 63/69 两条 Aegilops 行的取值一致；**不要**用脚本默认的 `Other`/`Diploid`，见 §6 R6）、`chromosome_level="Yes"`（脚本固定写 Yes）、`display_order`：MM/UU 为同 Polyploidy 的 `MAX+1`（需 DB 才能查），CC/NN 因该 Polyploidy 尚无行 → 脚本会得 **1**（`finish_genome_integration.sh:669-732` 的 SQL 语义），如需与 LLM/前端排序一致可在落盘后手工调成 500+（非阻塞）。
- MySQL 表名长度（上限 64）：`Genefunc_<DS>_table` = 43 / 51 / 48 / 48 字符，余量 ≥13，安全。

### 3.6 运行时分类的“两条路径”（为什么关键词不是唯一决定因素）

`DB_CLASSIFICATION` 只是 **fallback**。`/api/blast/databases` 的真实分类逻辑（`app/api/routers/blast.py:702-749`）：

1. 先由 `_assembly_level_map()`（`:230-275`）从 `genome_registry` 取每个 BLAST 库基名对应的行，`_registry_category(row)`（`:207-227`）按 **ploidy** 分类：
   - `AA/DD → diploid_wheat`；`AABBDD→hexaploid_wheat`；`AABB→tetraploid_wheat`；`AABBRR→triticale`；`Hordeum/barley→barley`；`Secale/rye→rye`；`ponticum→thinopyrum_ponticum`；
   - **其他任何非空 ploidy（含 MM/CC/UU/NN/SS/TT/VV/EE/RR/II/MMUU/DDNN）→ other_triticeae**。
2. registry 没命中时，才回退到 `_classify_db()`（`:413-419`）的关键词子串匹配。

**推论（对 4 个新基因组）**：
- registry 行建好（收尾脚本第 7 步 `rebuild_genome_registry.py`）之后，4 个基因组的所有库**必然**进 `other_triticeae`，即使 `markgrafii`/`uniaristata` 没加关键词；
- 但 `--check-name` 第 2 步只用关键词（不读 DB），所以 **C/N 不加关键词就过不了门禁**；
- 集成过程中有一个短暂窗口：BLAST 库已建、registry 还没重建时，API 会把 C/N 的库归到 `other`（`Other / Unclassified`）——直到 `rebuild_genome_registry.py` 跑完并重启/等缓存。这不是持久问题，但验收时别在窗口期看分类。

---

## 4. 需改的代码/数据清单

> “重启 API”列：**是** = 改完必须 `sudo systemctl restart wheatomics-api`（python 代码或依赖进程内缓存的查询）；**否** = git pull / 重跑脚本 / 重新部署 docpage 即可。生产上的部署流程按 CLAUDE.md：`git fetch origin && git merge --ff-only origin/main` → 必要时 restart。

### 4.1 仓库代码（本仓库，需要 commit/push）

| # | 文件:行号 | 现状 | 建议改法 | 重启 API | 必要性 |
|---|---|---|---|---|---|
| C1 | `app/api/routers/blast.py:381-391`（`DB_CLASSIFICATION` 的 `other_triticeae.keywords`） | 无 `markgrafii`/`uniaristata` 关键词 | 在 `"aecomosa",` 附近追加 `"aegilops_markgrafii", "aegilops_uniaristata", "markgrafii", "uniaristata",`（若采用短名再加 `"aemarkgrafii","aeumbellulata","aeuniaristata"`） | **是**（且 `list_dbs` 缓存 TTL 1h，见 `blast.py:428-429`，必须重启才立刻可见） | **必改**（否则 C/N 过不了 `--check-name` step 2） |
| C2 | `scripts/rebuild_genome_registry.py:586-589`（`SUB` 映射） | 有 MM/UU，**无 CC/NN**（也无 II） | 末尾追加 `"CC": "C", "NN": "N"`（顺带 `"II": "I"`） | 否（脚本；但门禁读它，需 server 仓库更新后才生效） | **必改**（否则 `subgenomes` 为空且 `--check-name` step 1 BLOCK） |
| C3 | `app/core/genome_ordering.py:34-59`（`_CANONICAL`） | 有 AA/DD/HH/SS/MM/RR/UU/VV/EE/TT/PP/GG，**无 CC/NN**（也无 II/PPPP） | 追加 `"CC": "CC", "NN": "NN"`（顺带 `"II": "II", "PPPP": "PPPP"`） | **是**（`/api/genes/functions/examples`、registry 的 `infer_karyotype` 走这里） | 建议改（低风险；不改也能跑，但 `Polyploidy` 为空时前端会归入 “Other / Unclassified”） |
| C4 | `app/static/interval/index.html:255` | `TABLE_CATEGORIES` 的 diploid `groups` 数组无 `CC/NN` | 加入 `'CC','NN'` | 否（StaticFiles 直接从仓库目录读；git pull 后刷新即可） | **必改**（否则新表在 IntervalTool 下拉里落入 “Other / Unclassified”） |
| C5 | `app/static/PfamSearch/index.html:181` | 同上 | 同上 | 否 | **必改** |
| C6 | `app/static/caps/index.html:431` | 同上（已含 `MMUU`） | 同上 | 否 | **必改** |
| C7 | `app/static/docpages/jbrowse.html` | 无 CC/NN 分组；hero=213（`:68`）；UU/MM 分区数手工值（`:995`/`:1012`）；`asm-status` 默认文案 206/22（`:82`）；chips 手工值（`:96-101`） | ① `#group-uu` 卡片区（`:1005` 前）插 PI554389 之后的新卡；② `#group-mm`（`:1019` 前）插新卡；③ 在 `#group-tt` 结束（`:1032`）与 `#group-ee`（`:1034`）之间新建 `<section class="asm-group" id="group-cc">` 与 `#group-nn`；④ hero `213`→**217**；⑤ 各 section 的静态 `asm-group-count` 相应 +1/新建（JS 会在加载后重算，但 no-JS 要准）；⑥ `asm-status` 默认文案 206/22→210/24（可选）；⑦ chips 如需覆盖 CC/NN 再加（`:96-101`，6 个 chip 目前不含 MM/UU） | 否（页面经 `scripts/deploy_doc_pages.py:41` 复制到 docroot，无重启） | **必改**（否则 JBrowse 页看不到新基因组） |
| C8 | `scripts/rebuild_genome_registry.py:476-493`（Web BLAST 前端 flag 判定） | 通过旧 `blast.html` 的 `value='<db>_chromosomes'` / `<db>.genome` 判断，新版页面两者都没有 → 新行 `web_blast_group=0` | 改为“有 `blast_genome_db` 即 `web_blast_group=1`”（新版前端从 API 动态取库）；或改为探测 `/api/blast/databases` | 否（脚本；重跑生效） | 建议改（否则 `stats.web_blast` 不增长；收尾脚本后续 UPDATE 会补 1，但重建后又会归 0） |
| C9 | `scripts/rebuild_genome_registry.py:750-779`（`overrides` 字典）或 `scripts/data/triticeae_genome_metadata_v5.3.json`（`:35`） | 4 个新基因组不在策展表/overrides 中 | 为 4 个 DS 增加 overrides：`species`、`assembly_level="Chromosome"`、`chromosome_count=7`、`te_content`（0.882/0.863/0.872/0.879）、`doi/journal/publication_year/paper_title`、`cultivar_or_line`、`assembly_accession`（待 task-1 的 GCA）；**重点** `chromosome_count`/`assembly_level`（否则见 §6 R8） | 否（重跑 rebuild） | **强烈建议**（否则 registry 里 `chromosome_count` = fai 序列数（comosa 15、markgrafii 14、umbellulata 188）、`assembly_level=NULL`） |
| C10 | `scripts/rebuild_genome_registry.py:86,118-166`（`CARD_RE` 解析 jbrowse.html） | 只认旧 `<div class="card-body">` 卡片，新版 `asm-card` 匹配不到 → `parse_jbrowse_cards()` 返回 `{}` | 如需从卡片补 DOI/ploidy/accession，改成匹配 `article class="asm-card"` + `data-search`/`<h3 class="asm-name">`；不改则接受“卡片元数据不参与 registry，改用 C9 的 overrides / 收尾脚本写回” | 否 | 可选（当前任务用 C9 即可覆盖） |
| C11 | `app/static/blast2/index.html` | 已是从 `/api/blast/databases` 动态渲染分类（`:2098-2121`），无手写库清单 | **不需要改** | — | 无需 |
| C12 | `app/mcp/tool_specs.py:421-447,480-492` | `list_genomes`/`list_blast_databases` 等工具是 API 薄包装，无硬编码基因组/分类清单 | **不需要改**；`app/static/docpages/agent.html` 也没有具体基因组清单（只有 31 个工具说明） | — | 无需 |
| C13 | `app/api/routers/genome.py:33,99-148`、`scripts/sql/genome_registry.sql:12,34` | `dataset_id` 正则 `^[\w.\-]+$` 允许连字符；`ploidy varchar(100)`、`annotation_status enum('none','pending','available')` 可容纳 MM/CC/UU/NN | **不需要改 schema**；但**建议** MYTAG 用下划线（见 §6 R7） | — | 无需（命名层面规避） |
| C14 | `scripts/rebuild_getfasta_aggregates.py:28,45-48,112-133,236-244` | `PLOIDY_PREFIX` 已含 `CC/NN`；`is_chrom()` 优先看 `.genome_Chr*.nhr` | **不需要改**；重跑即可把新基因组建入 `all_genomes` | — | 无需 |
| C15 | `scripts/import_jbrowse_meta.py:160-175,188` | 动态扫描 `JBROWSE_DATA_ROOT/*/trackList.json`，`--dataset` 可选 | **不需要改**；收尾脚本第 6 步会跑 `--dataset <DS>` | — | 无需 |
| C16 | `scripts/deploy_doc_pages.py:41`、`scripts/deploy_blast2_preview.py`（源 `app/static/blast2/index.html`） | 部署 docroot 页面 | 改 `docpages/jbrowse.html` 后需跑 `deploy_doc_pages.py --check/--only jbrowse`；BLAST 页未改则无需部署 | 否 | 部署步骤 |

### 4.2 收尾脚本（技能资产，非本仓库；服务器副本在 `/var/www/data/masw_data/_prep/finish_genome_integration.sh`）

> **这些不是“可选优化”，而是本批次的硬阻塞**：当前脚本按 2026-10 之前的旧前端编写，对 2026-11 的线上页面已经失效。建议同步技能资产与服务器副本。

| # | 位置（`finish_genome_integration.sh`） | 现状 | 建议改法 | 重启 API |
|---|---|---|---|---|
| S1 | `:236-248`（check_name step 3） | 读 `<optgroup label="…">`；线上 `/blast/blast.html` 已是 BLAST 2.0 SPA，**optgroup 数=0** | 改为查 `/api/blast/databases` 的 `categories[]` 是否包含目标分类（或检测页面含 `blast-db-cats` 时跳过 optgroup 检查）；同时保留 `min` 兼容旧页 | 否 |
| S2 | `:249-269`（check_name step 4） | 用 `<h5>&nbsp;…</h5>` 找 JBrowse 分区；新版页面用 `<h2 class="asm-group-title">` + `id="group-<karyotype>"`，永远返回空 | 改为解析 `id="group-([a-z]+)"`；`--section-existing` 支持 `group-mm`/`group-uu`/`group-cc`/`group-nn` 这类 id | 否 |
| S3 | `:503-570`（`step_jbrowse_card`） | 旧格式：`<div class="card">`+`card-group`+`<div id="cite"></div>` 锚点；新版页面**没有 `cite` 锚点**，插入会 `[ERR] 找不到 <div id="cite"></div> 锚点` | 改为按 `#group-<PLOIDY 小写>` 在对应 `asm-grid` 末尾插入 `<article class="asm-card" data-search="…">`；没有该 section 则新建 `<section class="asm-group" id="group-cc">`；同时更新 hero/静态计数 | 否 |
| S4 | `:571-652`（`step_blast_html`） | 旧 ViroBLAST 机制（`<optgroup>`、`N<DS>_chromosomes` hidden input、`Nall_genes`/`Pall_proteins` 追加）；新版页面无这些元素 → `[ERR] 找不到 optgroup` 退出 2 | 本批次建议 **`--skip-html`**；长期把该步骤改为 no-op（新版前端动态取 API），或改为调用 `/api/blast/databases` 做验收 | 否 |
| S5 | `:877-973`（`verify`） | 仍 `grep "${DS}_chromosomes"` / `"${DS}.add_Description.cds=>"` 旧页面；`--skip-html` 后必然 2 个 fail（退出码 1） | 改为 `curl /api/blast/databases \| jq` 断言分类/计数、`grep "?data=${DS}"`（新页面仍有 `?data=`）、`/api/jbrowse/datasets` 断言 | 否 |
| S6 | `:354-361`（默认 `GROUP` 映射） | MM/CC/NN→`Other`、UU→`Diploid` | 增加 `MM/CC/NN/UU` → `Other Triticeae`（与既有 Aegilops 历史行 id 63/69 的 `Group` 值一致）；或统一要求显式 `--group` | 否 |
| S7 | `:669-732`（Genefunc_registry upsert） | `table_name = "Genefunc_${DS}_table"`、`Accession = ${MYTAG}`、`chromosome_level='Yes'`、`display_order` 同 Polyploidy MAX+1 | 若采用下划线命名则**无需改**；若坚持连字符/点号名，必须先补 `table_name` 的规整函数（与流水线一致） | 否 |

### 4.3 数据/运维动作（按 SOP 执行，均是既有脚本）

| # | 动作 | 工具/命令（SOP 引用） | 重启 API | 备注 |
|---|---|---|---|---|
| D1 | 归一化 4 套 `fa/gff3/cds/pep`、`check_genome_files.py`、`add_wheat_genome.sh`（10 步） | SOP §1–§3 | 否 | **前置阻塞：需要 4 个组装 FASTA（来源=NCBI BioProject，见 §6 R15）** |
| D2 | `.fai`：`samtools faidx <DS>.genome`、`samtools faidx <DS>.add_Description.cds` | `finish_genome_integration.sh:653-668` | 否 | PrimerServer2 依赖 |
| D3 | Genefunc 建表 + EggNOG/Pfam/02G + `Genefunc_<DS>_table` | 流水线内部 | 否 | 行数 ≈ mRNA 数 |
| D4 | 聚合库别名：`all_genomes.nal` / `all_gene.nal` / `all_protein.pal` / `all_genomes_type.txt`（`<DS>.genome<TAB><PLOIDY>`） | `finish_genome_integration.sh:733-774` | **是**（否则 `/api/sequence/chromosomes` 进程内缓存 1h 不刷新，`app/api/routers/sequence.py:127` `_CHROM_CACHE_TTL=3600`） | 也可重跑 `scripts/rebuild_getfasta_aggregates.py --apply` |
| D5 | `Genefunc_registry` upsert（4 行） | `finish_genome_integration.sh:669-732` | 否（DB 直读，无缓存） | `Group="Other Triticeae"`、`Polyploidy=MM/CC/UU/NN` |
| D6 | `import_jbrowse_meta.py --dataset <DS>`（4 次或全量） | `finish_genome_integration.sh:775-851` | 否（DB 直读；`jbrowse_meta` 表） | → `/api/jbrowse/datasets` 219→223 |
| D7 | `rebuild_genome_registry.py` | 同上 | 否（DB 直读；但依赖 C2/C8/C9 已部署） | registry totals 变化见 §5 |
| D8 | 元数据写回（DOI/期刊/年份/物种/材料/登录号/gene_count/subgenomes/flags） | `finish_genome_integration.sh:775-851` | 否 | 会把 `web_blast_group` 等 4 个 flag 置 1 |
| D9 | `build_blast_jbrowse_map.py`（+ `--check`） | `finish_genome_integration.sh:852-876` | 否（映射按 mtime 自动重载，SOP 5.5） | 否则 BLAST 结果页没有 JBrowse 按钮；要求 BLAST `.fai` 与 JBrowse `refSeqs.json` 染色体长度一致 |
| D10 | 部署 docpages / blast2：`scripts/deploy_doc_pages.py --only jbrowse` | `deploy_doc_pages.py:41` | 否 | 改 C7 后执行；`--check` 可做漂移审计 |
| D11 | 重启 API（最后一次） | `sudo systemctl restart wheatomics-api` | **是** | 让 C1/C3 的 Python 改动、BLAST DB 缓存（`blast.py:428-429`）、sequence 缓存（`sequence.py:127`）同时生效 |
| D12 | 验收 | SOP §6 + 收尾脚本 `verify()`（修 S5 后） | 否 | 关键断言见 §5.2 |

### 4.4 已确认“无需改”的模块（避免过度改动）

| 模块 | 依据 |
|---|---|
| BLAST 2.0 前端 `app/static/blast2/index.html` | 分类/库清单全部动态来自 `/api/blast/databases`（`:1672`、`:2098-2121`；预设库只是演示默认值 `:2153-2161`） |
| getfasta SPA `app/static/getfasta/index.html` | 基因组 chips 来自 `/api/genes/functions/registry` 按 `polyploidy` 分组（`:425-445`、`:529-538`），无硬编码 |
| MCP `app/mcp/tool_specs.py` / `agent.html` | 工具目录为声明式 API 包装，无具体基因组清单（`tool_specs.py:421-447`、`:480-492`） |
| PrimerServer2 | 动态扫描 `BLAST_DB_PATH`，只需 `.fai` |
| `app/api/routers/genome.py` / `scripts/sql/genome_registry.sql` | schema 与正则都能容纳 MM/CC/UU/NN；`annotation_status` 枚举无需扩展 |
| `scripts/rebuild_getfasta_aggregates.py` | `PLOIDY_PREFIX` 已含 CC/NN（`:45-48`），动态枚举 |
| `scripts/import_jbrowse_meta.py` | 动态扫描数据集目录（`:160-175`） |
| `app/static/preblast` / `syntenyview` / `orthofinder` / `caps`（除分类数组） | 无本批所需硬编码基因组清单；synteny/orthofinder 为可选登记（不登记则 counts 不变） |

---

## 5. 计数增量（现状=实测；增量=按 1 次性集成 4 个基因组、每个 7 条染色体 + 未定位序列归并为 1 条 `ChrUn`、含注释估算）

### 5.1 前置假设

1. **一次性集成**（基因组 + 注释同批）：`add_wheat_genome.sh` 10 步全跑 → 有 `.genome`、7 个 `.genome_Chr*`、1 个 `.genome_ChrUn`、`.add_Description.cds`、`.add_Description.pep`、Genefunc 表、JBrowse 数据集。
2. 若采用 SOP 的“先基因组、后注释”两阶段：第一阶段的增量见 §5.3。
3. 每个基因组 BLAST 拆分库按“7 染色体 + 1 ChrUn”= 8 个（与既有 `MM_AeComosa_PI551049` 先例一致）。若某组装无未定位序列则少 1 个/基因组。
4. 基因数取 Zenodo README/GFF 的 **HC+LC 合计**（51,203 / 47,246 / 49,677 / 50,416）；若只导入 HC，则改为 37,622 / 34,133 / 35,799 / 35,816，且 `Genefunc_registry` 行数不变、表行数变少。

### 5.2 主表（前=实测现状，后=预期；均可复核）

| 指标 | 现状（实测） | 增量 | 预期值 | 证据/依据 |
|---|---|---|---|---|
| `/api/genomes/stats` `totals.total` | **316** | +4 | **320**（hidden 318→322） | 每基因组 1 条 registry 行（`visible=1`） |
| by_ploidy: MM | 1 | +1 | **2** | 新 comosa |
| by_ploidy: UU | 2 | +1 | **3** | 新 umbellulata |
| by_ploidy: CC | （无该组） | +1 | **1** | 新 markgrafii |
| by_ploidy: NN | （无该组） | +1 | **1** | 新 uniaristata |
| annotation_status: available | 211 | +4 | **215**（一次性集成） | 有 gene_table → `annotation_status=available` |
| annotation_status: none | 104 | +4→108 / 0 | **108**（两阶段 Phase A）/ 104（一次性） | 两阶段时 Phase A 无注释 |
| registry `totals.jbrowse` | **215** | +4 | **219** | 每基因组 1 个 JBrowse 数据集 |
| registry `totals.gene_function` | **214** | +4 | **218** | Genefunc 表 |
| registry `totals.getfasta` | **199** | +4 | **203** | all_genomes 成员 |
| registry `totals.primerserver` | **203** | +4 | **207** | `.genome.fai` |
| registry `totals.web_blast` | **200** | +4 | **204** | 收尾脚本 UPDATE 置 1（注意 C8 的 rebuild 覆盖问题） |
| registry `totals.synteny` / `orthofinder` | 86 / 43 | 0 | 86 / 43 | 未登记（可选后补） |
| `/api/jbrowse/datasets` total | **219** | +4 | **223** | `jbrowse_meta` 导入 |
| jbrowse 文档页 hero（`jbrowse.html:68`） | **213** | +4 | **217** | hero 数 = `?data=` 链接数 = 206 卡 + 7 占位 |
| jbrowse 可见卡片 `asm-card` | **206** | +4 | **210** | 手工加卡 |
| jbrowse section 数（`asm-group`） | **22** | +2 | **24** | 新建 CC/NN 两个 section |
| jbrowse “Jump to” chips | 6 个（UU 无 chip） | 0 或 +2 | 6（不改）或 8（若加 CC/NN chip） | `jbrowse.html:96-101` 手工维护 |
| jbrowse `asm-status`（JS 重算） | 206 / 22 | +4 / +2 | 210 / 24 | `jbrowse.html:82`、`:1209` |
| BLAST 核酸库数 | **2924** | +40（4×10） | **2964** | 每基因组 1 genome + 8 拆分 + 1 cds；无 ChrUn 则 +36 |
| BLAST 蛋白库数 | **193** | +4 | **197** | 每基因组 1 pep |
| BLAST 合计 | **3117** | +44 | **3161** | |
| BLAST `other_triticeae`（nuc） | **439** | +40 | **479** | registry 行存在后按 ploidy 归类 |
| BLAST `other_triticeae`（prot） | **31** | +4 | **35** | |
| BLAST `diploid_wheat`（nuc/prot） | 164 / 15 | 0 | 164 / 15 | 若改 `_registry_category` 把 MM/CC/UU/NN 归入 diploid 则另算（§7 D2） |
| PrimerServer2 `genome` 组 | **203** | +4 | **207** | 动态扫描 |
| PrimerServer2 `gene` 组 | **194** | +4 | **198** | `.cds.fai` |
| `Genefunc_registry` 行数 | **216** | +4 | **220** | 每基因组 1 行 |
| `Genefuncdb` 表数 | **224** | +4 | **228** | 每基因组 1 表 |
| `/api/genes/functions/examples` 条目 | **216** | +4 | **220** | 同 registry |
| getfasta chips 分组（按 Polyploidy） | 18 组（MM 1 / UU 1） | +2 组（CC/NN）+ MM→2 + UU→2 | 20 组 | `getfasta/index.html:425-445` 动态 |
| `all_genomes` seqid 数 | **115354** | +32（4×8） | **115386** | 既有 comosa PI551049 先例=8 条/基因组；若流水线保留全部未定位 scaffold 则增量为 comosa 15 + markgrafii 14 + umbellulata 188 + uniaristata 待定（**需流水线实测**） |
| registry 新行 `gene_count` | — | — | 51,203 / 47,246 / 49,677 / ~50,416（HC+LC） | GFF 实测/README；HC-only 见 §5.1 |
| `Genefunc_<DS>_table` 行数 | — | — | ≈ gene_count（每 gene 1 mRNA：comosa/markgrafii/umbellulata 的 GFF 实测 gene=mRNA） | GFF 实测 |
| `assembly_accession` 非空行 | 4 | +4 | 8 | 新条目建议填 GCA 号（待 task-1） |

### 5.3 两阶段（genome-only Phase A）增量变体

| 指标 | Phase A 增量 | Phase B（注释后）增量 |
|---|---|---|
| registry total | +4（annotation_status=none → none 104→108） | 0（annotation_status none→available，available 211→215） |
| BLAST nuc | +36（每基因组 1 genome + 8 拆分；4×9） | +4（`.add_Description.cds`） |
| BLAST prot | 0 | +4（`.pep`） |
| PrimerServer2 genome/gene | +4 / 0 | 0 / +4 |
| Genefunc_registry / tables / examples | 0 | +4 / +4 / +4 |
| JBrowse datasets / hero / cards | +4 / +4 / +4 | 0 |
| `all_genomes` seqid | +32 | 0 |
| BLAST `other_triticeae` | +36（nuc） | +4（nuc）/ +4（prot） |

### 5.4 线上 API 无法确认、需服务器实测的项

| 项 | 为什么查不到 | 核查方式（待服务器可用时） |
|---|---|---|
| `Genefunc_registry.display_order`（MM/UU 的 MAX+1） | `/api/genes/functions/registry` 不返回 `display_order` | `mysql -N -e "SELECT MAX(display_order) FROM Genefuncdb.Genefunc_registry WHERE Polyploidy='MM'"` |
| BLAST 库真实增量（是否含 ChrUn、cds、pep） | 取决于 `add_wheat_genome.sh` 与输入 | `ls /var/www/html/getfasta/blastdb/<DS>.genome* \| wc -l`；`blastdbcmd -info` |
| `all_genomes` seqid 真实增量 | 取决于归一化是否合并未定位 scaffold | `blastdbcmd -db all_genomes -entry <STD_FIRST>`；前后 `count` 对比 |
| JBrowse `refSeqs.json` 序列数 | 尚未生成 | `python3 -c "import json;print(len(json.load(open('/var/www/html/jbrowse-1.12.3-release/<DS>/seq/refSeqs.json'))))"` |
| 4 个组装 FASTA 是否可获取（GCA/BioProject） | 本次未查 NCBI（task-1 职责） | NCBI Assembly/ENA 按 BioProject 查；README 声称组装已存 NCBI |
| uniaristata GFF 完整计数 | 审计时 task-1 仍在下载 | 见 task-1 `PAPER_DATA.md` |

---

## 6. 风险与坑（按影响排序）

| # | 风险 | 证据 | 影响 | 建议 |
|---|---|---|---|---|
| **R1** | **收尾脚本与 2026-11 新前端结构性错配**：`--check-name` step 3 找 `<optgroup>`（线上=0）、step 4 找 `<h5>` 分区（新版用 `asm-group`）；`step_jbrowse_card` 锚点 `<div id="cite"></div>` 新版不存在；`step_blast_html` 整套旧机制无效；`verify()` grep 旧元素 | 线上 `GET /blast/blast.html` 0 个 `optgroup`、含 `blast-db-cats`；线上 `GET /jbrowse.html` 与 `app/static/docpages/jbrowse.html` **sha256 完全相同**（`b834e155…`，均 133,228 B），无 `id="cite"`；脚本 `:236-248`、`:249-269`、`:556`、`:571-652`、`:879-887` | **任何基因组现在跑 `--check-name` 都被 step 3 BLOCK**；收尾正式运行 `--skip-html` 也会 verify 失败（退出码 1），但不改数据 | 短期：`--check-name --group "Other Triticeae"` 跳过 optgroup 断言；正式收尾 `--skip-html` + 手工 C7；长期：按 §4.2 修脚本 |
| **R2** | `SUB` 缺 CC/NN | `scripts/rebuild_genome_registry.py:586-589`；模拟输出 `SUB[CC] = (未登记)` | `subgenomes` 为空 + `--check-name` step 1 BLOCK | C2 补 `"CC":"C","NN":"N"` |
| **R3** | `DB_CLASSIFICATION` 缺 `markgrafii`/`uniaristata` | `app/api/routers/blast.py:381-391`；模拟输出 C/N → `other` | `--check-name` step 2 BLOCK；集成窗口期（registry 未重建）API 分类短暂落 `other` | C1 补关键词（全名+短名各 2 个） |
| **R4** | **`ae.` 关键词误吞**：任何库名子串含 `ae.` 都会被归入 other_triticeae；且匹配是 `lower()` 后子串，`AE.`、`..._ae.xxx` 也会命中 | `blast.py:386` `"ae.",  # matches ae.speltoides...`；`:413-419` 子串匹配 | 若命名用 `ae.markgrafii...` 风格会被“特性”救活分类，但也会让任何含 `ae.` 的非 Aegilops 名字误分类；`diploid_wheat` 在列表更靠前（`:349` vs `:381`），所以 `tauschii` 不受影响；**不建议**加宽泛 `"aegilops"` 关键词（会再吞其他库，虽仍被 diploid 先匹配救回 tauschii） | 只加精确物种词；命名避免 `.`/`ae.` 形式 |
| **R5** | `_CANONICAL` 缺 CC/NN（也缺 II/PPPP） | `app/core/genome_ordering.py:34-59`；`_PLOIDY_PREFIXES` 由它生成（`:90`） | registry `Polyploidy` 为空时 `infer_karyotype("Genefunc_CC_…")` → `"Other"` → 前端 “Other / Unclassified”；`karyotype_ploidy` 不受影响（`"CC"`→2，`:103-126`）；排序把 CC/NN 排在 `AABBDD` 之后的字母序位置（预期的二倍体段内） | C3 补 `CC/NN`（顺带 II/PPPP） |
| **R6** | `Genefunc_registry` **没有 “Diploid” Group**；`Group` 大多是 NULL | `/api/genes/functions/registry` 216 行：NULL 182、Allohexaploid 25、Tetraploid 3、Other Triticeae 2、Triticale 2、Barley 1、Thinopyrum ponticum 1 | 若用脚本默认 `--group Diploid`（UU）或 `Other`（MM/CC/NN）会写进新的、与既有 Aegilops 行不一致的值；前端目前不读 `Group`（IntervalTool 用 `karyotype`），但会造成数据口径混乱 | 显式 `--group "Other Triticeae"`（与 id 63/69 一致）；R6 与 R1 的 `--group` 绕过技巧兼容 |
| **R7** | **表名长度/字符**：MySQL 表名上限 64；`Genefunc_<DS>_table` 长度：推荐名 43/51/48/48（安全）；但 MYTAG 若含 `-`/`.`，流水线很可能规整为 `_`，而收尾脚本用未转义的 `FROM Genefunc_${DS}_table`（`finish_genome_integration.sh:908`）和 `table_name='Genefunc_${DS}_table'`，会指向不存在的表 | `scripts/sql/genome_registry.sql`；既有证据：`ae.longissima.AEG-6782-2` → 表名 `Genefunc_SS_ae_longissima_AEG_6782_2_table`（点/连字符→下划线） | registry 行写入但 `gene_table` 指向错误表 → 基因功能页/例子 chips 404 | 用下划线 `IPK_AE783` 等；原始连字符写入 `--accession`/`display_name`/`notes` |
| **R8** | **`chromosome_count` / `assembly_level` 会被 fai 序列数污染**：`rebuild_genome_registry.py:440-443` 用 `.genome.fai` 的序列数作为 `chromosome_count`（仅当记录里为空）；新基因组 fai 序列数 = 7 + 未定位 scaffold（实测 GFF seqid：comosa 15、markgrafii 14、umbellulata 188、uniaristata 待定） | `rebuild_genome_registry.py:440-443`；GFF seqid 统计（§2.8） | `/api/genomes` 显示 chromosome_count=15/14/188；`/api/blast/databases` 的 `database_meta.chromosome_count` 错误；`rebuild_getfasta_aggregates` 的 `all_genomes` 归组不受影响（`is_chrom` 优先看拆分索引），但导出/筛选可能受影响 | C9 overrides 显式 `chromosome_count=7`、`assembly_level="Chromosome"`（或在 curated JSON 加行） |
| **R9** | 既有 comosa 行 `annotation_status=none` 但 `gene_table` 存在（39,602 行）——`annotation_status` 被 `preserve_fields` 保留，不随 `gene_table` 自动修正 | 线上 comosa 行 `annotation_status=none`；`/api/genes/functions/tables` 有 `Genefunc_MM_AeComosa_PI551049_table rows=39,602`；`rebuild_genome_registry.py:895-916,996-1002` | “available 计数”口径不一致；新条目若继承同流程可能再次错标 | 决策：新条目明确按“有 gene table → available”写；顺手修 comosa 行（单条 SQL UPDATE） |
| **R10** | **跨物种 mRNA ID 重复**：3 个已下载 GFF 的 `model.model.STRG.*` 系 ID 存在 3,457 个跨物种重名（comosa∩markgrafii 1,240、comosa∩umbellulata 1,321、markgrafii∩umbellulata 1,302、三物种共有 203） | GFF 实测（§2.8）；ID → `all_genes`/`all_proteins` 是跨基因组聚合 BLAST 库（`rebuild_getfasta_aggregates.py:308-315`） | `blastdbcmd -entry <重复ID>` 会返回多条；`/api/sequence/by-gene` 对无 table 上下文的查询可能取到别的物种序列；基因 ID 全局检索歧义 | 二选一：① 数据准备时给 4 个基因组的基因 ID 加物种后缀（如 `_AE783`，需同步 gff3/cds/pep/BED，平台先例：`ae_longissima_TAEG67822` 用 `AE.LONG.r1…` 前缀）；② 接受重复，文档声明“基因查询须带 table 上下文” |
| **R11** | `q` 搜索**不搜 `assembly_accession`** | `app/api/routers/genome.py:132-136` 只 LIKE `dataset_id/display_name/species/cultivar_or_line`；全平台仅 4 条 `assembly_accession` 非空 | 若把 `IPK-AE783` 只写进 `assembly_accession`，用户按登录号搜索命中 0 | 推荐 DS/`--label` 本身含登录号（本文推荐名已含），`--cultivar` 也写登录号 |
| **R12** | 进程内缓存导致“数据已上线但 API 看不到” | `blast.py:428-429` `_DB_LIST_CACHE` TTL 3600s；`sequence.py:127` `_CHROM_CACHE_TTL=3600`；JBrowse refseq 缓存按 mtime | 验收时误判失败 | 最后一次统一 `sudo systemctl restart wheatomics-api`（D11） |
| **R13** | JBrowse hero/chips 是**手工数字**，JS 只重算 section 计数与状态行 | `jbrowse.html:68`（213 硬编码）、`:96-101`（chips 手工）、`:82`/`:1209`（JS 重算）；7 个隐藏占位卡（`:1132`）使 hero=cards+7 | 加 4 张卡后 hero 必须手工 213→217，否则页面数字不一致；状态行会自动变 210/24 | C7 一次性改全 |
| **R14** | 跨源计数不一致：JBrowse 目录 219 ≠ registry jbrowse 215（4 个孤儿目录 `KeNong9204`/`Secale_cereale`/`fangenome`/`rye_weining2.0`）≠ 文档页 `?data=` 213 | `/api/jbrowse/datasets` 219；`stats.jbrowse=215`；docpage 213 | 验收时拿 219+4 对不上；不要把某一源当唯一真值 | 验收分别断言（§5.2 各行独立） |
| **R15** | **数据阻塞**：Zenodo 只有注释（gene GFF、protein FASTA、TE GFF、光学图），**没有基因组 FASTA**；README 称组装已存 NCBI（BioProject PRJNA1506336/1174795/1114735/1154594），但本次未验证 GCA | `zenodo_probe/README_zenodo_diploid_Aegilops.md` “Assemblies and raw sequencing reads are deposited at NCBI… This record contains … annotation files” | 没有组装 FASTA 时流水线**无法启动**（0 步都跑不了） | 由 task-1 核实 4 个 GCA/BioSample/下载 URL + md5；不可得则向作者索取 |
| **R16** | 只有蛋白 FASTA、无现成 CDS；GFF 的 seqid 是 `1M..7M`/`1C..7C`/`1U..7U`+散在 scaffold，需归一化为 `Chr1X…`/`ChrUn_*` 才能与平台既有命名/`blast_jbrowse_map` 对齐 | Zenodo 文件清单（无 cds）；GFF seqid 实测；SOP §1.1–§1.2（归一化 4 件套） | 归一化错误会导致 JBrowse refseq ↔ BLAST seqid 长度对不上 → BLAST 跳 JBrowse 无按钮（D9 会失败） | 按 SOP 归一化；`gffread -g <fa> -x cds -y pep` 生成 CDS/PEP；用 `check_genome_files.py` 闸门 |
| **R17** | 既有同物种条目“并存 vs 替换”决策 | comosa 1 条（PI551049，annotation none）、umbellulata 2 条（PI554389 无基因表、TA1851 有） | 新增后搜索 “comosa” 2 条 / “umbellulata” 3 条，用户可能混淆；`rebuild_genome_registry._core_id` 会把同 core 的行合并（`:1084-1107`） | 推荐**新增并存**（不同登录号/不同组装）；`display_name` 必须含登录号；不要命名成 `…_PI551049_v2` 之类会触发 `_core_id` 合并的名字 |
| **R18** | `blast_jbrowse_map` 未重建 → BLAST 结果页无 JBrowse 按钮 | `scripts/build_blast_jbrowse_map.py`；收尾脚本 step 9（`:852-876`） | 功能缺失（非数据错误） | D9 重建并 `--check` |
| **R19** | `--check-name` 读取的是**服务器仓库**的 `blast.py`/`rebuild_genome_registry.py` | 脚本 `check_name()` 中 `REPO="/var/www/FastAPI_backend_Port8000"`（`:79`） | C1/C2 未部署到服务器前，门禁仍然 BLOCK | 先 commit/push → 服务器 `git fetch && git merge --ff-only` → 再跑 `--check-name` |
| **R20** | 收尾脚本最终退出码会被旧 HTML 校验拉成 1，但数据其实成功 | `verify()` `:879-887`；`FAILED` 计数在 `:970-972` | 误判为失败 | 看 `CHANGED/FAILED` 明细与 §5.2 各项独立断言；修 S5 |
| **R21** | 既有 `Aegilop_comosa_PI551049` 是拼写缺 s 的历史 id：**`q=Aegilops` 搜不到它**（species=`Aegilop comosa`、dataset_id 也缺 s；`q=comosa` 能搜到，靠 display_name=`Ae.comosa`）；`_core_id` 会剥离 `aegilops/aegilop/ae` 前缀再比较 | `rebuild_genome_registry.py:1084-1107`；`_core_id("Aegilop_comosa_PI551049")="comosapi551049"`、新名 `"comosaipkae783"`（不同，不会误合并）；实测 `q=Aegilops` 25 条不含 comosa | 用户按物种名找不到既有 comosa；新条目建议顺手把该行 `species` 改为 `Aegilops comosa`（单条 SQL，可选）；别用与既有材料过于相似的 MYTAG（如 `Comosa_PI551049_v2`） | 推荐名已规避；按需修旧行拼写 |
| **R22** | BLAST 2.0 前端生产文件与仓库有轻微漂移（线上 176,860 B vs 仓库 `app/static/blast2/index.html` 176,953 B） | 线上抓取 vs 本地 size/sha256 | 若本批需要改 blast2 前端，先 `deploy_blast2_preview.py --check` 对账；本批无需改 | 注意即可 |
| **R23** | `Gene ID` 校验：`^[A-Za-z0-9_.:-]+$` 允许点号，`evm.model.1M.1` 可通过；区域正则也允许 `Chr1M_AeComosa…:200-500` | `app/core/security.py:61-62` | 无阻塞（已核对） | 无需改 |
| **R24** | 4 个基因组组装质量/染色体命名可能互不相同（comosa `1M..7M`；markgrafii `1C..7C`；umbellulata `1U..7U`；uniaristata 待定），`split_fasta_by_chrom.py` 依赖命名规则 | GFF 实测；SOP §1.2 | 归一化失败/漏染色体 | 归一化后逐一核对 7 条染色体 + ChrUn；`check_genome_files.py` 闸门 |

---

## 7. 待 Lead 决策项

| # | 决策 | 选项 A（推荐） | 选项 B | 影响 |
|---|---|---|---|---|
| D1 | 命名风格 | 全物种名 + 下划线登录号：`MM_Aegilops_comosa_IPK_AE783` 等（本文 §3.5） | 短名 `MM_AeComosa_IPK_AE783` 等 | A 只补 2 个关键词；B 需补 4 个短关键词；A 与既有 `Aegilops_umbellulata_*` registry 命名更一致 |
| D2 | BLAST 分类归属 | **保持 `other_triticeae`**（与既有 MM/UU/SS/TT/VV/MMUU 等全部 Aegilops 一致，零额外代码） | 改 `_registry_category`（`blast.py:207-227`）让 MM/CC/UU/NN 进 `diploid_wheat` | B 会让**所有**非 AA/DD 二倍体（SS/TT/VV/MMUU/DDNN…）一起搬家，`diploid_wheat` 164→大幅增加、`other_triticeae` 439→减少，属平台级行为变更，不建议在本批做 |
| D3 | Genefunc `Group` 值 | `"Other Triticeae"`（既有 Aegilops 两条历史行同值；也可顺带绕开 R1 optgroup） | 脚本默认：UU=`Diploid`、MM/CC/NN=`Other` | A 数据口径统一；B 会引入两个从未出现过的 Group 值 |
| D4 | 注释导入口径 | **HC+LC 合计**（51,203 / 47,246 / 49,677 / ~50,416，与论文 “Total protein-coding genes” 一致） | 仅 HC（37,622 / 34,133 / 35,799 / 35,816） | 影响 Genefunc 表行数、`gene_count`；两者都需在 `notes` 写明口径 |
| D5 | mRNA ID 重复处理 | 给新基因组基因 ID 加物种后缀（如 `_AE783`），保证跨库唯一 | 接受重复（沿用平台既有行为），查询须带 table 上下文 | A 需改 GFF 属性（数据准备阶段）；B 有 R10 的歧义风险 |
| D6 | 前端接入路径 | **`--skip-html`** + 手工改 `docpages/jbrowse.html`（C7）+ 后端代码改动（C1/C2/C3/C8/C9）+ 修收尾脚本 S1–S6（长期） | 只做数据、不动前端 | A 才能让 4 个基因组在 JBrowse/BLAST/基因功能页可见；B 只有 API/registry 有数据 |

---

## 8. 证据索引

**API（只读 URL，均已实测）**

| 用途 | URL |
|---|---|
| 总量/倍性/注释状态 | `https://wheatomics.sdau.edu.cn/api/genomes/stats` |
| 列基因组（分页，`q` 模糊搜索） | `https://wheatomics.sdau.edu.cn/api/genomes?q=comosa&limit=200` |
| 4 物种检索 | `…/api/genomes?q=comosa`、`q=umbellulata`、`q=markgrafii`、`q=uniaristata` |
| 新登录号检索 | `…/api/genomes?q=AE783`（AE740/AE680/EKC105/RL5723/IPK/… 同） |
| BLAST 库/分类 | `…/api/blast/databases?program=blastn`、`…?program=blastp` |
| JBrowse 数据集 | `…/api/jbrowse/datasets` |
| Genefunc 注册表/表/例子 | `…/api/genes/functions/registry`、`…/tables`、`…/examples` |
| PrimerServer2 | `…/api/PrimerServer2/databases` |
| all_genomes 序列列表 | `…/api/sequence/chromosomes?database=all_genomes`（+`&pattern=comosa` / `umbellulata`） |
| 线上 JBrowse 页 | `https://wheatomics.sdau.edu.cn/jbrowse.html`（133,228 B，sha256 与 `app/static/docpages/jbrowse.html` 相同） |
| 线上 BLAST 页 | `https://wheatomics.sdau.edu.cn/blast/blast.html`（BLAST 2.0，0 个 optgroup） |

**仓库 file:line**

| 主题 | 位置 |
|---|---|
| 分类体系 `DB_CLASSIFICATION` / `_classify_db` / `_registry_category` / `_assembly_level_map` / `/databases` | `app/api/routers/blast.py:207-227`、`:230-275`、`:304-410`（diploid `:349-357`、other_triticeae `:381-392`）、`:413-419`、`:428-429`、`:702-760` |
| 核型排序/推断 | `app/core/genome_ordering.py:34-59`（`_CANONICAL`）、`:90`、`:103-126`、`:128-146` |
| registry 重建（SUB/overrides/cards/web_blast/preserve/defaults/dedupe） | `scripts/rebuild_genome_registry.py:86`、`:118-166`、`:440-443`、`:476-493`、`:586-589`、`:750-779`、`:895-916`、`:996-1002`、`:1084-1107` |
| 聚合库重建 | `scripts/rebuild_getfasta_aggregates.py:28`、`:45-48`、`:74-108`、`:112-133`、`:236-244` |
| jbrowse_meta 导入 | `scripts/import_jbrowse_meta.py:48`、`:160-175`、`:180-190` |
| genome registry API/字段 | `app/api/routers/genome.py:33`、`:61-88`、`:99-148`；`scripts/sql/genome_registry.sql:12`、`:34` |
| 基因 ID/区域校验 | `app/core/security.py:61-62` |
| JBrowse 页面（hero/chips/sections/MM/UU/占位/JS 计数） | `app/static/docpages/jbrowse.html:68`、`:82`、`:96-101`、`:991-1006`、`:1008-1019`、`:1021-1032`、`:1132`、`:1209` |
| 基因功能页分类数组（需加 CC/NN） | `app/static/interval/index.html:253-262`（diploid `:255`）；`app/static/PfamSearch/index.html:179-188`（`:181`）；`app/static/caps/index.html:429-437`（`:431`） |
| getfasta chips（动态） | `app/static/getfasta/index.html:425-445`、`:529-538` |
| BLAST 2.0 动态分类 | `app/static/blast2/index.html:1672`、`:2098-2121`、`:2153-2161` |
| MCP 目录（动态，无硬编码基因组） | `app/mcp/tool_specs.py:421-447`、`:480-492` |
| docpage 部署 | `scripts/deploy_doc_pages.py:41`；`scripts/deploy_blast2_preview.py`（源 `app/static/blast2/index.html`） |
| 收尾脚本（门禁/HTML/registry/验收） | `~/.agents/skills/lab-server/scripts/finish_genome_integration.sh:79`、`:149-365`（step1 `:191-204`、step2 `:206-235`、step3 `:236-248`、step4 `:249-269`、step6 `:287-300`）、`:354-361`、`:503-570`（锚点 `:556`）、`:571-652`（optgroup `:593`、`:599`）、`:653-668`、`:669-732`、`:733-774`、`:775-851`、`:852-876`、`:877-973`（`:879-887`）、`:908` |

**附录 A. `--check-name` 模拟运行（完整输出位置）**

模拟脚本副本与线上页面 fixture 在 `/tmp/sim/`（本机临时目录，非仓库）：
- `/tmp/sim/finish_sim.sh`（收尾脚本副本，仅替换 REPO/BLASTDB/HTML 路径）
- `/tmp/sim/fakerepo/`（仅含 `scripts/rebuild_genome_registry.py` + `app/api/routers/blast.py` 的补丁副本，用于验证“改后”门禁）
- fixture：`/tmp/prod_jbrowse.html`、`/tmp/prod_blast.html`

关键输出已在 §3.4 摘录；改后 + `--group "Other Triticeae"` 的结论为 `[OK] 命名可直接开跑`。

---

*本文件由 platform-baseline（task-2）产出；所有数字均可按 §8 的 URL/行号复核。未改动本仓库任何源码，未 git commit。*
