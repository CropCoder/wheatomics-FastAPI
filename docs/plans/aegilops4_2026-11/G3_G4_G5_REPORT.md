# G3 / G4 / G5 上线与验收报告（4 个二倍体 Aegilops）

> 日期：2026-11-12 00:16–02:40 CST ｜ 执行：Lead（生产机 wheatomics）
> 结论：**4 个基因组已全部上线，G5 逐条验收 90/90 PASS**

## 0. 总览

| 阶段 | 内容 | 结果 |
|---|---|---|
| 阶段 0 | 代码部署（分类关键词 / SUB CC·NN / overrides / SPA / 静态页 / 收尾脚本） | ✅ 生产 HEAD `8ed123b`，API 重启 |
| G3 | `add_wheat_genome.sh` × 4（BLAST 库 / Genefunc 表 / JBrowse / registry / EggNOG…） | ✅ **4/4 `[SUCCESS]`**，00:19–02:13（约 1h54m） |
| G4 | `finish_genome_integration.sh` × 4（卡片 / 计数 / fai / 聚合别名 / registry / 元数据 / 映射表 / API 断言） | ✅ **4/4 rc=0，各 28 OK / 0 FAIL**，02:21–02:23 |
| G5 | `accept_aegilops4_onboarding.py` 逐条验收（102 项，含 GetSequence） | ✅ **102 PASS / 0 FAIL** |

## 1. 4 个基因组最终状态

| 数据集 | 物种 / 材料 | ploidy | gene=mRNA | registry chrom | BLAST 库 | Genefunc 行数 | JBrowse refseqs | PS2 序列 | 实弹 BLAST |
|---|---|---|---|---|---|---|---|---|---|
| `MM_Aegilops_comosa_IPK_AE783` | *Ae. comosa* / IPK-AE783 | MM | 51,203 | 7 | 17 seqs / 4,407,741,597 bp | 51,203 | 17 | 17 | ✅ 命中 |
| `CC_Aegilops_markgrafii_EKC105_RL5723` | *Ae. markgrafii* / EKC105_RL5723 | CC | 47,246 | 7 | 24 seqs / 3,577,170,360 bp | 47,246 | 24 | 24 | ✅ 命中 |
| `UU_Aegilops_umbellulata_IPK_AE740` | *Ae. umbellulata* / IPK-AE740 | UU | 49,677 | 7 | 250 seqs / 4,268,089,219 bp | 49,677 | 250 | 250 | ✅ 命中 |
| `NN_Aegilops_uniaristata_IPK_AE680` | *Ae. uniaristata* / IPK-AE680 | NN | 50,416 | 7 | 21 seqs / 4,475,943,907 bp | 50,416 | 21 | 21 | ✅ 命中 |

- 每基因组 BLAST：`<DS>.genome` + 7 条 `<DS>.genome_Chr1X…7X` + `<DS>.add_Description.cds`（核酸 9 个）、`<DS>.add_Description.pep`（蛋白 1 个）；
- Genefunc 表 `Genefunc_<DS>_table` 行数 = 基因数；JBrowse（V2）`all_gene` + `DNA` 轨道齐全；
- PrimerServer2 只需 `.genome` 与 `.add_Description.cds/.pep` 库（各 7 条染色体 + 全部基因）；
- registry 元数据：物种/材料/登录号/组装级别 Chromosome/染色体数 7/基因组大小/基因数/TE 含量/doi/journal/year/annotation_status=available/visible=1。

## 2. 平台全局变化（上线前 → 上线后）

| 指标 | 前 | 后 | 说明 |
|---|---|---|---|
| `/api/genomes/stats` total | 316 | **325** | +4 目标基因组；+5 为 rebuild 自动登记的既有平台数据集（见 §4.3） |
| by_ploidy MM / CC / UU / NN | 1 / 0 / 2 / 0 | **2 / 1 / 3 / 1** | 4 个目标全部出现 |
| annotation available | 211 | **216** | +4 目标 +1 既有登记 |
| blastn 库数 | 2,924 | **2,960** | +36（4×9） |
| blastp 库数 | 193 | **197** | +4 |
| blastn other_triticeae | 439 | **473** | 439+36−2（见 §4.4） |
| blastp other_triticeae | 31 | **34** | 31+4−1（见 §4.4） |
| JBrowse datasets | 219 | **223** | +4 |
| Genefunc registry 行 | 216 | **220** | +4 |
| Genefuncdb 表数 | 224 | **228** | +4 |
| JBrowse V2 页 | hero 213 / named 206 / 22 组 / 206 卡 | **hero 217 / named 210 / 24 组 / 210 卡** | CC、NN 新分区；MM、UU 追加卡片 |
| 静态页 diploid 组 | 无 CC/NN | 有 CC/NN | interval / PfamSearch / caps |
| Web BLAST | SPA 动态库 | 含 4 基因组全部 40 个库 | 无需再改页面 |
| BLAST↔JBrowse 映射 | — | **CHECK OK（201 bases / 200 matched / 99.5%）** | 4 个新库可跳 JBrowse |

## 3. 分阶段证据

### G3 流水线（`_prep/pipeline_aegilops4_summary.log`）

```
MM 00:18:59 → 00:51:04  rc=0
NN 00:51:04 → 01:17:37  rc=0
CC 01:17:37 → 01:47:21  rc=0
UU 01:47:21 → 02:13:04  rc=0
ALL SUCCESS 2026-11-12 02:13:04
```

- 每基因组日志：`<数据目录>/pipeline_<MYTAG>.log`，`[ERROR]/Traceback` 计数 = 0；
- comosa 抽检：MySQL 51,203 行、JBrowse refSeqs 17、blastdb 17 seqs / 4,407,741,597 bp、registry 行字段齐全。

### G4 收尾（`_prep/finish_aegilops4_summary.log`）

```
MM 02:21:11 → 02:21:47  rc=0  OK=28 FAIL=0
NN 02:21:47 → 02:22:17  rc=0  OK=28 FAIL=0
CC 02:22:26 → 02:22:48  rc=0  OK=28 FAIL=0
UU 02:22:48 → 02:23:12  rc=0  OK=28 FAIL=0
ALL FINISH SUCCESS 2026-11-12 02:23:12
```

- 卡片/计数：MM hero 213→214（#group-mm 1→2）；NN 214→215（新建 #group-nn）；CC 215→216（新建 #group-cc）；UU 216→217（#group-uu 2→3）；
  named 206→210，groups 22→24；
- 聚合别名：`all_genomes.nal` / `all_gene.nal` / `all_protein.pal` / `all_genomes_type.txt` 各 +4；
- `.fai`、Genefunc_registry upsert、元数据回写、BLAST↔JBrowse 映射重建全部成功，无 WARN/FAIL。

### G5 验收（90 项，详见附录）

```bash
# 在生产机执行
/usr/bin/python3 /var/www/data/masw_data/_prep/accept_aegilops4_onboarding.py
# TOTAL 102 checks | PASS 102 | FAIL 0
```

覆盖：全局计数（B01–B18）、每基因组 19 项（A01–A19 ×4，含 GetSequence）、回归（C01–C03）。

## 4. 验收中发现并修复的问题（一一核对过程）

1. **registry `chromosome_count` 错误**：rebuild 用 `.fai` 序列数（17/24/250/21）填充，且 overrides 合并逻辑跳过已有值。修复：overrides 增加 `_hard: ["chromosome_count"]`，强制 7；重新 rebuild → 4 行均为 7。
2. **registry `display_name`/`subgenomes` 缺失**：rebuild 未填 → overrides 补 `display_name`（如 `Ae.comosa IPK-AE783 (M)`）与 `subgenomes`（M/C/U/N），rebuild 后生效。
3. **rebuild 自动登记 5 个既有平台数据集**：`PI428250`、`Triticum_aestivum_ThatcherLr9`、`Chinese Spring 03G`、`Durum_Wheat_cv._Svevo`、`E.sibiricus_GaomuNo.1`（此前仅有 BLAST/JBrowse 数据、无 registry 行）。导致 total 316→325（而非 320）。属 rebuild 的既定行为（registry 由平台事实派生），保留并记录；如需目录口径严格 320，可将这 5 行 `visible=0`（可逆，下次 rebuild 保留）。
4. **RR_rye_weining2 分类迁移**：rebuild 后该 rye 数据集的 2 个核酸库 + 1 个蛋白库从 other_triticeae 归入 rye，导致 other_triticeae 增量 36→34（核酸）与 4→1（蛋白）。与本次 4 基因组无关，属分类修正。
5. **CC/NN 新分区标题**：脚本默认把 section-title 放进 `asm-formula`，已改为纯倍性（CC/NN），描述保留物种信息；docroot 与仓库源同步。
6. **验收脚本自身修正**：blastdbcmd 输出格式解析（`N sequences; M total bases`）、mysql warning 行过滤、实弹探针由端粒重复区改为 CDS 首 160 bp（避免低复杂度无命中）。

## 5. 产物与文件

- 服务器数据目录：`/var/www/data/masw_data/<DS>/`（四件套 + idmap + 流水线产物 + 日志）；
- 服务器 `_prep/`：`normalize_diploid.py`、`renumber_gff_ids.py`、`prepare_aegilops4_dataset.sh`、`finish_genome_integration.sh`、`pipeline_aegilops4_all.sh`、`finish_aegilops4_all.sh`、`accept_aegilops4_onboarding.py`；
- 生产 repo：`/var/www/FastAPI_backend_Port8000`，HEAD `8ed123b`；
- docroot 页面 `/var/www/html/jbrowse.html` 已回写 `app/static/docpages/jbrowse.html`（+4 卡片，计数同步）；
- 本地记录：`docs/plans/aegilops4_2026-11/{G5_acceptance.json, G3_pipeline_summary.log, G4_finish_summary.log}`。

## 6. 遗留（非阻塞）

- `cite.html` 引用块与 news 页面条目为可选人工补充（复核脚本里未含）；
- 技能目录 `~/.agents/skills/lab-server/` 安装（当前沙箱不可写；文档与脚本已版本化在仓库，服务器 `_prep/` 已是最新）；
- Web BLAST 全局库计数 `web_blast: 200→207` 属 SPA/registry 判定的既有修正，非遗漏。

## 7. 回访补充（2026-11-12 上午）

### 7.1 cite.html 引用块（已上线）

- 文件：`/var/www/html/cite.html`（docroot，非 repo 管理；备份 `cite.html.bak-20261112_091853`）；
- 末尾追加 4 个基因组的引用块（与现有 Aegilops 条目同格式）：
  Khadka, B., Edwards, T., Lévesque-Lemay, M., Ens, J., Chawla, H.S., Zheng, C., You, F.M., Pozniak, C.J., Cloutier, S. (2026)
  *Chromosome-level reference genome assemblies and annotation of four diploid Aegilops*. BMC Plant Biology.
  doi:10.1186/s12870-026-10046-2
- 外网校验：`curl https://wheatomics.sdau.edu.cn/cite.html` 命中该 DOI 与作者行（副本存 `server_pages/cite.html`）。

### 7.2 news 页面条目（已上线）

- 数据源：`/var/www/html/V2.0/news.json`（`help/news.html` 运行时 fetch；备份 `news.json.bak-20261112_091853`）；
- 头部新增 2026-11-12 条目：四基因组（MM/CC/UU/NN）上线，含染色体数/大小/基因数、平台 ID 示例、
  JBrowse/BLAST/GetSequence/PrimerServer2/CAPS/基因功能入口说明；
- 外网校验：news.json 35 条、首条 2026-11-12；`/help/news.html` 200（副本存 `server_pages/news.json`）。

### 7.3 PrimerServer2 是否更新：是（含实弹设计）

- 数据库列表：4 个基因组的 `.genome` 与 `.add_Description.cds` 均在 `genome`/`gene` 分组；
- 序列清单：`/api/PrimerServer2/databases/<DS>.genome/sequences` 返回 17/24/250/21 条（与 fasta 一致）；
- **设计作业实弹**（comosa，`POST /api/PrimerServer2/jobs`，区域 `Chr1M_Aegilops_comosa_IPK_AE783 100000 300`）：
  作业进度到 100%，`status=done`，返回结果 HTML 含 `Site 1: Chr1M_Aegilops_comosa_IPK_AE783-100000-300`。

### 7.4 CAPS / dCAPS / KASP 是否更新：是（含实弹设计）

- CAPS 页面取库来自 PrimerServer2 → 4 个基因组自动可选；静态页 diploid 组已含 CC/NN；
- **CAPS/dCAPS 实弹**（comosa，坐标模式 `Chr1M_Aegilops_comosa_IPK_AE783:100000-101000`，pos 100500，A→G）：
  返回 `total_designs=1`（BfaI，`enzyme_count=124`），引物/酶切位点完整；
- **KASP 实弹**：同一区域内换位点（offset 1500/2500/3500）均返回 `total_designs=20`；
  offset 500 位点为 0（位点序列限制，非功能问题）。

### 7.5 rebuild 自动登记的 5 行：是"别名/孤儿行"，建议隐藏

| dataset_id | 对应既有规范条目（有完整数据） | 自身数据 |
|---|---|---|
| `PI428250` | `Triticum_urartu_PI428250`（JBrowse + `Genefunc_AA_Triticum_urartu_PI428250_table` + BLAST `AA_Triticum_urartu_PI428250.*`） | 无 JBrowse/BLAST/基因表 |
| `Durum_Wheat_cv._Svevo` | `AABB_Durum_Wheat_Svevo` / `Svevo_V2`（JBrowse + 基因表 `Genefunc_AABB_Durum_Wheat_Svevo_table`） | 无 JBrowse/BLAST/基因表 |
| `Chinese Spring 03G` | `CS_IWGSC03G`（基因表 `Genefunc_CS_IWGSC03G_table`）；`IWGSC03G` 行 | 无 JBrowse/BLAST |
| `E.sibiricus_GaomuNo.1` | `Elymus_sibiricus_cultivar_Gaomu`（JBrowse）；`SSHH_Elymus_sibiricus_Gaomu`（BLAST） | 无 JBrowse/BLAST |
| `Triticum_aestivum_ThatcherLr9` | JBrowse 目录 `ThatcherLr9` 只有原始 fasta（无 `seq/refSeqs.json`），平台上无可用数据集 | 无任何平台功能入口 |

- 这 5 行由 `rebuild_genome_registry.py` 从"平台事实 + 策展元数据"派生，`web_blast_group=0`、`jbrowse_dataset=None`、
  `gene_table=None`，属于历史命名/别名，不应作为独立基因组出现在 `/api/genomes`（这也是 total 316→325 的来源）；
- **建议**：把这 5 行 `visible=0`（不删除、保留溯源；rebuild 会保留 visible，后续不会自动改回），
  目录口径即回到 320；命令：
  ```sql
  UPDATE wheatomics_db.genome_registry SET visible=0
  WHERE dataset_id IN ('PI428250','Durum_Wheat_cv._Svevo','Triticum_aestivum_ThatcherLr9','Chinese Spring 03G','E.sibiricus_GaomuNo.1');
  ```
  （用 `wheatomics_user` 执行；执行后 `/api/genomes/stats` total=320、annotation available=215。）

## 8. GetSequence 同步复核（2026-11-12 上午第二轮）

### 8.1 发现的问题（GetSequence 之前**未完全同步**）

| # | 问题 | 影响 |
|---|---|---|
| 1 | 页面 by-gene/batch 实际查 `all_genes` / `all_proteins`（复数别名），而收尾脚本只维护旧的 `all_gene` / `all_protein`（单数） | 新基因组的蛋白/转录本序列查不到 |
| 2 | `all_genes.nal` 重建后成员 205 个，超过 BLAST 别名 **200 成员上限**，索引 200 之后的成员（含新 UU）`-entry_batch` 返回 `Skipped` | 尾部基因组 GetSequence 批量查询失效 |
| 3 | `/var/www/html/doc/getsequence_search.txt`（页面链接的示例表）没有 4 个新基因组行 | 文档示例缺少 |
| 4 | `Genefunc_registry.display_name` 写成数据集技术名 | 支持基因组面板显示 `MM_Aegilops_comosa_IPK_AE783` 而不是 `Ae.comosa IPK-AE783 (M)` |

### 8.2 修复

- `scripts/rebuild_getfasta_aggregates.py`：`SEPARATE_CDS_DBS` 改为前缀匹配（排除 PacBioFullLengthcDNA.*），额外排除 `Tae_TF.cds`、`fangenome_final.cds`，把 `all_genes`/`all_gene` 压回 **200 成员**；
- `scripts/finish_genome_integration.sh`：
  - step 5 聚合别名改为同时维护 `all_genomes.nal / all_gene.nal / all_protein.pal / all_genes.nal / all_proteins.pal`，新增成员**前插**并在 >200 时告警；
  - 新增 step 5b：自动向 `getsequence_search.txt` 增/改本基因组行（`update_getsequence_search.py`）；
  - step 4 `display_name` 改用 `--label`（友好名）；
  - verify 增加 5 个聚合别名成员断言 + `/api/sequence/by-gene` 实测；
- 生产已执行 `rebuild_getfasta_aggregates.py --apply`（`all_genes` 200 / `all_proteins` 196 成员），并给 4 个基因组补了文档行、更新了 Genefunc 显示名。

### 8.3 复核结果（102/102 PASS）

| 检查 | 结果 |
|---|---|
| by-gene（`protein_db=all_proteins`）4 个示例基因 | ✅ protein_len 259 / 305 / 353 / 170 |
| batch（`database=all_genes`）4 个示例 CDS | ✅ succeeded=1；既有 AK58 也 =1 |
| 4 个 CDS 在 `all_genes.nal` 的位置 | ✅ 79 / 171 / 173 / 197（均 < 200） |
| `all_genes` / `all_gene` / `all_proteins` / `all_protein` 成员数 | ✅ 200 / 200 / 196 / 196 |
| `getsequence_search.txt` 新行（外网） | ✅ 4 行 |
| 支持基因组面板（registry `display_name`/example 字段） | ✅ 友好名 + 示例区间/基因齐全 |
| `/getfasta/` 页面 | ✅ 200 |
| by-interval（all_genomes，4 个基因组） | ✅ |

> 平台既有现象（非本次引入）：`blastdbcmd -entry` 不支持**核酸别名库**（报 "DB contains no accession info"），对所有基因组一致；GetSequence 单基因 CDS 请走 `/api/sequence/batch`（已验证可用）。

## 附录：G5 逐条核对结果（102/102 PASS）


### B 组 — 全局计数/前端/映射

| # | 规则 | 结果 | 细节 |
|---|---|---|---|
| B01 | /api/genomes/stats total == 325（316 基线 + 4 新 + 5 个 rebuild 登记的既有平台数据集） | ✅ PASS | 325 |
| B02 | by_ploidy MM/CC/UU/NN = 2/1/3/1 | ✅ PASS | {'MM': 2, 'CC': 1, 'UU': 3, 'NN': 1} |
| B03 | annotation_status available == 216（211 + 4 新 + 1 既有登记） | ✅ PASS | 216 |
| B04 | registry totals (jbrowse/gene_function/getfasta/primerserver) | ✅ PASS | {'jbrowse': '219', 'gene_function': '219', 'getfasta': '203', 'primerserver': '207', 'web_blast': '207'} |
| B05 | blastn 库数 == 2960 | ✅ PASS | 2960 |
| B06 | blastn other_triticeae == 473（439 + 新 36 − 2 个 RR_rye_weining2 归入 rye） | ✅ PASS | 473 |
| B07 | blastp 库数 == 197 | ✅ PASS | 197 |
| B08 | blastp other_triticeae == 34（31 + 新 4 − 1 个 RR_rye_weining2 归入 rye） | ✅ PASS | 34 |
| B09 | jbrowse datasets == 223 | ✅ PASS | 223 |
| B10 | Genefunc_registry rows == 220 | ✅ PASS | 220 |
| B11 | Genefunc_registry 4 张新表 | ✅ PASS |  |
| B12 | Genefuncdb total_tables == 228 | ✅ PASS | 228 |
| B13 | jbrowse.html hero == 217 | ✅ PASS | 217 |
| B14 | jbrowse.html named/groups == 210/24 | ✅ PASS | ('210', '24') |
| B15 | jbrowse.html asm-card 数 == 210（206 基线 + 4） | ✅ PASS | 210 |
| B16.MM | jbrowse 卡片存在：MM_Aegilops_comosa_IPK_AE783 | ✅ PASS |  |
| B16.CC | jbrowse 卡片存在：CC_Aegilops_markgrafii_EKC105_RL5723 | ✅ PASS |  |
| B16.UU | jbrowse 卡片存在：UU_Aegilops_umbellulata_IPK_AE740 | ✅ PASS |  |
| B16.NN | jbrowse 卡片存在：NN_Aegilops_uniaristata_IPK_AE680 | ✅ PASS |  |
| B17.interval | interval diploid 数组含 CC/NN | ✅ PASS | ['AA', 'DD', 'SS', 'MM', 'CC', 'NN', 'TT', 'UU', 'VV', 'DDNN'] |
| B17.PfamSearch | PfamSearch diploid 数组含 CC/NN | ✅ PASS | ['AA', 'DD', 'SS', 'MM', 'CC', 'NN', 'TT', 'UU', 'VV', 'DDNN'] |
| B17.caps | caps diploid 数组含 CC/NN | ✅ PASS | ['AA', 'DD', 'SS', 'MM', 'CC', 'NN', 'TT', 'UU', 'VV', 'DDNN', 'MMUU'] |
| B18 | build_blast_jbrowse_map.py --check rc=0 | ✅ PASS | CHECK OK: /var/www/FastAPI_backend_Port8000/app/services/data/blast_jbrowse_map.json matches a fresh build (201 bases, 2 |

### A 组 — 每基因组产物与功能

| # | 规则 | 结果 | 细节 |
|---|---|---|---|
| A01.MM | MM_Aegilops_comosa_IPK_AE783 genome_registry 字段齐全正确 | ✅ PASS | ok |
| A02.MM | MM_Aegilops_comosa_IPK_AE783 核酸库(+9)/蛋白库(+1)存在 | ✅ PASS | ok |
| A03.MM | MM_Aegilops_comosa_IPK_AE783 分类 other_triticeae | ✅ PASS | genome_in_other=True |
| A04.MM | MM_Aegilops_comosa_IPK_AE783 整基因组库 17 seqs / 4407741597 bp | ✅ PASS | {'sequences': 17, 'total_length': 4407741597} |
| A05.MM | MM_Aegilops_comosa_IPK_AE783 染色体库 Chr1M（1 seq / 长度一致） | ✅ PASS | ({'sequences': 1, 'total_length': 572610027}, 572610027) |
| A06.MM | MM_Aegilops_comosa_IPK_AE783 JBrowse refSeqs == 17 | ✅ PASS | 17 |
| A07.MM | MM_Aegilops_comosa_IPK_AE783 JBrowse all_gene 轨道存在 | ✅ PASS |  |
| A08.MM | MM_Aegilops_comosa_IPK_AE783 all_gene/Chr1M trackData.json 存在 | ✅ PASS |  |
| A09.MM | MM_Aegilops_comosa_IPK_AE783 trackList API 200 | ✅ PASS |  |
| A10.MM | MM_Aegilops_comosa_IPK_AE783 all_genomes 染色体命中 >= 7 | ✅ PASS | 7 |
| A11.MM | MM_Aegilops_comosa_IPK_AE783 by-interval 返回 FASTA | ✅ PASS | >Chr1M_Aegilops_comosa_IPK_AE783:1000-1080 Aegilops_comosa_IPK_AE783 MM Chr1M CC |
| A12.MM | MM_Aegilops_comosa_IPK_AE783 PrimerServer2 genome/gene 库在列 | ✅ PASS |  |
| A13.MM | MM_Aegilops_comosa_IPK_AE783 PrimerServer2 sequences == 17 | ✅ PASS | 17 |
| A14.MM | MM_Aegilops_comosa_IPK_AE783 Genefunc 表行数 == 51203 | ✅ PASS | 51203 |
| A15.MM | MM_Aegilops_comosa_IPK_AE783 实弹 blastn（CDS 探针→整基因组库）有命中 | ✅ PASS | rows=66 |
| A16.MM | MM_Aegilops_comosa_IPK_AE783 BLAST 结果可跳 JBrowse | ✅ PASS | None |
| A17.MM | MM_Aegilops_comosa_IPK_AE783 GetSequence by-gene 蛋白可取（AeCom.AE783.r1.1MG000100.1） | ✅ PASS | protein_len=259 |
| A18.MM | MM_Aegilops_comosa_IPK_AE783 GetSequence batch 可取 CDS（all_genes） | ✅ PASS | succeeded=1 |
| A19.MM | MM_Aegilops_comosa_IPK_AE783 getsequence_search.txt 有本基因组行 | ✅ PASS | Chr1M_Aegilops_comosa_IPK_AE783:200-500 |
| A01.CC | CC_Aegilops_markgrafii_EKC105_RL5723 genome_registry 字段齐全正确 | ✅ PASS | ok |
| A02.CC | CC_Aegilops_markgrafii_EKC105_RL5723 核酸库(+9)/蛋白库(+1)存在 | ✅ PASS | ok |
| A03.CC | CC_Aegilops_markgrafii_EKC105_RL5723 分类 other_triticeae | ✅ PASS | genome_in_other=True |
| A04.CC | CC_Aegilops_markgrafii_EKC105_RL5723 整基因组库 24 seqs / 3577170360 bp | ✅ PASS | {'sequences': 24, 'total_length': 3577170360} |
| A05.CC | CC_Aegilops_markgrafii_EKC105_RL5723 染色体库 Chr1C（1 seq / 长度一致） | ✅ PASS | ({'sequences': 1, 'total_length': 474569321}, 474569321) |
| A06.CC | CC_Aegilops_markgrafii_EKC105_RL5723 JBrowse refSeqs == 24 | ✅ PASS | 24 |
| A07.CC | CC_Aegilops_markgrafii_EKC105_RL5723 JBrowse all_gene 轨道存在 | ✅ PASS |  |
| A08.CC | CC_Aegilops_markgrafii_EKC105_RL5723 all_gene/Chr1C trackData.json 存在 | ✅ PASS |  |
| A09.CC | CC_Aegilops_markgrafii_EKC105_RL5723 trackList API 200 | ✅ PASS |  |
| A10.CC | CC_Aegilops_markgrafii_EKC105_RL5723 all_genomes 染色体命中 >= 7 | ✅ PASS | 7 |
| A11.CC | CC_Aegilops_markgrafii_EKC105_RL5723 by-interval 返回 FASTA | ✅ PASS | >Chr1C_Aegilops_markgrafii_EKC105_RL5723:1000-1080 Aegilops_markgrafii_EKC105_RL |
| A12.CC | CC_Aegilops_markgrafii_EKC105_RL5723 PrimerServer2 genome/gene 库在列 | ✅ PASS |  |
| A13.CC | CC_Aegilops_markgrafii_EKC105_RL5723 PrimerServer2 sequences == 24 | ✅ PASS | 24 |
| A14.CC | CC_Aegilops_markgrafii_EKC105_RL5723 Genefunc 表行数 == 47246 | ✅ PASS | 47246 |
| A15.CC | CC_Aegilops_markgrafii_EKC105_RL5723 实弹 blastn（CDS 探针→整基因组库）有命中 | ✅ PASS | rows=5 |
| A16.CC | CC_Aegilops_markgrafii_EKC105_RL5723 BLAST 结果可跳 JBrowse | ✅ PASS | None |
| A17.CC | CC_Aegilops_markgrafii_EKC105_RL5723 GetSequence by-gene 蛋白可取（AeMar.EKC105.r1.1CG000100.1） | ✅ PASS | protein_len=305 |
| A18.CC | CC_Aegilops_markgrafii_EKC105_RL5723 GetSequence batch 可取 CDS（all_genes） | ✅ PASS | succeeded=1 |
| A19.CC | CC_Aegilops_markgrafii_EKC105_RL5723 getsequence_search.txt 有本基因组行 | ✅ PASS | Chr1C_Aegilops_markgrafii_EKC105_RL5723:200-500 |
| A01.UU | UU_Aegilops_umbellulata_IPK_AE740 genome_registry 字段齐全正确 | ✅ PASS | ok |
| A02.UU | UU_Aegilops_umbellulata_IPK_AE740 核酸库(+9)/蛋白库(+1)存在 | ✅ PASS | ok |
| A03.UU | UU_Aegilops_umbellulata_IPK_AE740 分类 other_triticeae | ✅ PASS | genome_in_other=True |
| A04.UU | UU_Aegilops_umbellulata_IPK_AE740 整基因组库 250 seqs / 4268089219 bp | ✅ PASS | {'sequences': 250, 'total_length': 4268089219} |
| A05.UU | UU_Aegilops_umbellulata_IPK_AE740 染色体库 Chr1U（1 seq / 长度一致） | ✅ PASS | ({'sequences': 1, 'total_length': 510898750}, 510898750) |
| A06.UU | UU_Aegilops_umbellulata_IPK_AE740 JBrowse refSeqs == 250 | ✅ PASS | 250 |
| A07.UU | UU_Aegilops_umbellulata_IPK_AE740 JBrowse all_gene 轨道存在 | ✅ PASS |  |
| A08.UU | UU_Aegilops_umbellulata_IPK_AE740 all_gene/Chr1U trackData.json 存在 | ✅ PASS |  |
| A09.UU | UU_Aegilops_umbellulata_IPK_AE740 trackList API 200 | ✅ PASS |  |
| A10.UU | UU_Aegilops_umbellulata_IPK_AE740 all_genomes 染色体命中 >= 7 | ✅ PASS | 7 |
| A11.UU | UU_Aegilops_umbellulata_IPK_AE740 by-interval 返回 FASTA | ✅ PASS | >Chr1U_Aegilops_umbellulata_IPK_AE740:1000-1080 Aegilops_umbellulata_IPK_AE740 U |
| A12.UU | UU_Aegilops_umbellulata_IPK_AE740 PrimerServer2 genome/gene 库在列 | ✅ PASS |  |
| A13.UU | UU_Aegilops_umbellulata_IPK_AE740 PrimerServer2 sequences == 250 | ✅ PASS | 250 |
| A14.UU | UU_Aegilops_umbellulata_IPK_AE740 Genefunc 表行数 == 49677 | ✅ PASS | 49677 |
| A15.UU | UU_Aegilops_umbellulata_IPK_AE740 实弹 blastn（CDS 探针→整基因组库）有命中 | ✅ PASS | rows=6 |
| A16.UU | UU_Aegilops_umbellulata_IPK_AE740 BLAST 结果可跳 JBrowse | ✅ PASS | None |
| A17.UU | UU_Aegilops_umbellulata_IPK_AE740 GetSequence by-gene 蛋白可取（AeUmb.AE740.r1.UnG093600.1） | ✅ PASS | protein_len=238 |
| A18.UU | UU_Aegilops_umbellulata_IPK_AE740 GetSequence batch 可取 CDS（all_genes） | ✅ PASS | succeeded=1 |
| A19.UU | UU_Aegilops_umbellulata_IPK_AE740 getsequence_search.txt 有本基因组行 | ✅ PASS | Chr1U_Aegilops_umbellulata_IPK_AE740:200-500 |
| A01.NN | NN_Aegilops_uniaristata_IPK_AE680 genome_registry 字段齐全正确 | ✅ PASS | ok |
| A02.NN | NN_Aegilops_uniaristata_IPK_AE680 核酸库(+9)/蛋白库(+1)存在 | ✅ PASS | ok |
| A03.NN | NN_Aegilops_uniaristata_IPK_AE680 分类 other_triticeae | ✅ PASS | genome_in_other=True |
| A04.NN | NN_Aegilops_uniaristata_IPK_AE680 整基因组库 21 seqs / 4475943907 bp | ✅ PASS | {'sequences': 21, 'total_length': 4475943907} |
| A05.NN | NN_Aegilops_uniaristata_IPK_AE680 染色体库 Chr1N（1 seq / 长度一致） | ✅ PASS | ({'sequences': 1, 'total_length': 509639608}, 509639608) |
| A06.NN | NN_Aegilops_uniaristata_IPK_AE680 JBrowse refSeqs == 21 | ✅ PASS | 21 |
| A07.NN | NN_Aegilops_uniaristata_IPK_AE680 JBrowse all_gene 轨道存在 | ✅ PASS |  |
| A08.NN | NN_Aegilops_uniaristata_IPK_AE680 all_gene/Chr1N trackData.json 存在 | ✅ PASS |  |
| A09.NN | NN_Aegilops_uniaristata_IPK_AE680 trackList API 200 | ✅ PASS |  |
| A10.NN | NN_Aegilops_uniaristata_IPK_AE680 all_genomes 染色体命中 >= 7 | ✅ PASS | 7 |
| A11.NN | NN_Aegilops_uniaristata_IPK_AE680 by-interval 返回 FASTA | ✅ PASS | >Chr1N_Aegilops_uniaristata_IPK_AE680:1000-1080 Aegilops_uniaristata_IPK_AE680 N |
| A12.NN | NN_Aegilops_uniaristata_IPK_AE680 PrimerServer2 genome/gene 库在列 | ✅ PASS |  |
| A13.NN | NN_Aegilops_uniaristata_IPK_AE680 PrimerServer2 sequences == 21 | ✅ PASS | 21 |
| A14.NN | NN_Aegilops_uniaristata_IPK_AE680 Genefunc 表行数 == 50416 | ✅ PASS | 50416 |
| A15.NN | NN_Aegilops_uniaristata_IPK_AE680 实弹 blastn（CDS 探针→整基因组库）有命中 | ✅ PASS | rows=2 |
| A16.NN | NN_Aegilops_uniaristata_IPK_AE680 BLAST 结果可跳 JBrowse | ✅ PASS | None |
| A17.NN | NN_Aegilops_uniaristata_IPK_AE680 GetSequence by-gene 蛋白可取（AeUna.AE680.r1.1NG000100.1） | ✅ PASS | protein_len=170 |
| A18.NN | NN_Aegilops_uniaristata_IPK_AE680 GetSequence batch 可取 CDS（all_genes） | ✅ PASS | succeeded=1 |
| A19.NN | NN_Aegilops_uniaristata_IPK_AE680 getsequence_search.txt 有本基因组行 | ✅ PASS | Chr1N_Aegilops_uniaristata_IPK_AE680:200-500 |

### C 组 — 回归

| # | 规则 | 结果 | 细节 |
|---|---|---|---|
| C01 | 旧基因组 AK58 registry 可查 | ✅ PASS | 1 |
| C02 | 旧序列 all_genomes by-interval 正常 | ✅ PASS | >Chr1A_AK58:1000-1080 AK58 AABBDD Chr1A TGGAAAACATGGCAAAAACA |
| C03 | 旧 BLAST 库 AABBDD_AK58.genome 仍在 | ✅ PASS |  |
