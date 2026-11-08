# Sumai3 基因组更新计划（待确认，尚未改动生产环境）

> 触发来源：*The Plant Genome* 2026, DOI [10.1002/tpg2.70285](https://doi.org/10.1002/tpg2.70285)
> —— "Chromosome-scale assembly of wheat cultivar Sumai 3, a major germplasm source for Fusarium head blight resistance"
>
> 计划日期：2026-10-26 ｜ 依据 SOP：`~/.agents/skills/lab-server/references/wheatomics-new-genome-sop.md`、
> `genome-only-then-annotation-update.md` ｜ 生产脚本：`/var/www/data/masw_data/_prep/annotation_update.sh`、`finish_genome_integration.sh`
>
> **本文件只是计划；Phase 1 起的所有生产改动需你确认后执行。**

---

## 0. 结论先行

**网站上“有”Sumai3，但只是序列层的半成品，不是按现行基因组更新流程完整上线的状态。**

| 检查项 | 现状 | 结论 |
|---|---|---|
| JBrowse | 数据集 `Sumai3`，21 条 refseq（名 `chr1A_Sumai3…`），**只有 DNA 轨道**，无基因结构轨道 | ⚠️ 仅序列 |
| 卡片 | `jbrowse.html` 有卡片 “Sumai3(AABBDD)”，**DOI 为空** | ⚠️ 缺元数据 |
| 核酸 BLAST | `AABBDD_Sumai3.genome` + 21 个染色体拆分库，Web BLAST 分组 “Sumai3 chromosomes” | ✅ 已上线 |
| CDS/PEP BLAST | 无 `AABBDD_Sumai3.add_Description.cds/.pep` | ❌ 缺注释层 |
| JBrowse 基因轨道 | 无 `all_gene`；Web BLAST 无 All genes / All proteins 的 Sumai3 条目 | ❌ 缺注释层 |
| 基因功能表 | 无 `Genefunc_AABBDD_Sumai3_table`，`Genefunc_registry` 无行 | ❌ 缺注释层 |
| getfasta | `all_genomes` 聚合库成员（染色体名 `Chr1A_Sumai3…`） | ✅ 可用 |
| PrimerServer2 | `AABBDD_Sumai3.genome` 已收录，`.fai` 存在（2026-09-08） | ✅ 可用 |
| genome_registry | 行 `Sumai3`：`annotation_status=none`，DOI / 论文 / 组装号 / 物种 全空，`gene_count=null` | ⚠️ 元数据缺失 |
| 数据目录 / 指纹 | `/var/www/data/masw_data` 下**没有** Sumai3 目录，无 `genome_fingerprint.txt`，无 provenance | ❌ 非标准归档 |
| cite.html | 无 Sumai 3 引文条目 | ⚠️ 缺引用 |

**序列身份核对（已逐条比对，确定是同一套组装）：**

- 现网 21 条染色体长度与论文 **Table S1 逐条完全一致**，合计 **14,408,607,908 bp**；
- 该总长与 NCBI 组装 **[GCA_051988995.1](https://www.ncbi.nlm.nih.gov/datasets/genome/GCA_051988995.1/)**（ASM5198899v1，2025-08-13，21 条染色体，contig N50 37.61 Mb）及论文 Table S4 的 “Genome size (bp)” 完全一致；
- 论文摘要的 **14.6 Gb** = 14.41 Gb + Table S2 的 `ChrUnknown` **234.6 Mb**（4417 条 unanchored contigs 拼接，N50 仅 0.1 Mb）。该 unknown 序列 **NCBI 未收录**，现网也没有。

**注释为什么还没有：** 论文报告 104,620 个高置信蛋白编码基因（注释方法：Evidence Modeler + Helixer + Mikado，基因 ID 形如 `TRAES.SUM.r1.3BG00516290`），但注释文件**未公开**：

- NCBI 组装 `feature_count` = `gene 0`（只有序列，无基因注释）；
- 论文 Data availability 只登记 PRJNA1247523 的 pseudomolecules + HiFi/RNA-Seq/HiC reads；
- 补充材料只有图 docx + 表 xlsx（S1–S5），没有 GFF/CDS/PEP。

**所以“基因组更新”要做的是：** ① 补元数据与规范化收尾（不依赖作者，今天就能做）；② 向作者取得 GFF 后做注释增量上线（外部依赖，是本计划的关键路径）。

---

## 1. 目标与范围

**目标**：把 Sumai 3（AABBDD，GCA_051988995.1）按平台两阶段流程补到“序列 + 注释 + 元数据 + 各模块入口 + 基因组信息库”完整状态。

**本轮做：**

1. 元数据补齐：DOI、论文标题、期刊、年份、物种、品种、组装号、组装级别、TE 含量、来源 URL/md5、registry notes；
2. 数据目录 + FASTA 指纹归档（为注释增量更新做前置）；
3. 命名一致性收尾（JBrowse refseq 大小写、`all_genomes_type.txt` 成员名、JBrowse 目录冗余 FASTA 清理）；
4. cite.html 引文 + JBrowse 卡片 DOI/NCBI 链接；
5. 取得 GFF 后：注释增量上线（EggNOG/Pfam、MySQL 基因功能表、中国春 02G 映射、CDS/PEP BLAST、JBrowse all_gene、聚合库、PrimerServer2 基因模板、BLAST 前端 All genes/All proteins）；
6. 验收、公网核验、manifest/周报（可选）与回滚预案。

**本轮不做（建议另立任务）：**

- 论文 `ChrUnknown`（234.6 Mb / 4417 contigs）补序列——NCBI 没有，需作者提供；平台现有 21 条染色体与论文 Table S1 完全一致，不影响主体；
- SyntenyView / OrthoFinder（需另建 genome_info/genome_type 库）；
- 表达谱、TE/CENH3 轨道、VCF/SV 数据；
- 重新做结构注释（平台无此流水线，且作者已有官方注释）。

---

## 2. 执行计划

### Phase 0 — 只读核查与备份（0.2 h，本次已完成 90%）

已完成的只读核查（未改任何生产文件）：

- 网站 5 个入口（JBrowse / BLAST / getfasta / PrimerServer2 / genome_registry）现状；
- 服务器侧：JBrowse 目录、BLAST 库文件与时间戳、`.fai`、`all_genomes.nal`/`type.txt`、`_prep` 脚本；
- 论文与 NCBI 数据核对（Table S1/S2/S4、feature_count、assembly_report、md5）；
- 本地与服务器均未发现 Sumai3 的 GFF/CDS/PEP。

执行时补做：

- 备份：`jbrowse.html`、`blast.html`、`cite.html`、`jbrowse-1.12.3-release/Sumai3/`（trackList.json + seq/ 清单）、`all_genomes.nal`、`all_genomes_type.txt`、`Genefunc_registry` 相关行、`genome_registry` 行（SQL dump）；
- 记录备份目录到 `provenance.txt`。

**闸门 G0**：备份清单落盘、可回滚。

---

### Phase 1 — 元数据 + 目录/指纹 + 命名一致性（1.5–2.5 h，不依赖 GFF）

> 目的：先把“序列层”从手工状态整理成可增量更新的标准状态，并让网站上的 Sumai3 信息完整、可引用。
> 推荐方案：**保留公开数据集 ID `Sumai3`（旧链接不变），内部序列名统一为 `Chr1A_Sumai3`，表/库使用 `AABBDD_Sumai3`。**

1. **数据目录与指纹**
   - 新建 `/var/www/data/masw_data/AABBDD_Sumai3/`；
   - 把现网标准 FASTA `/var/www/html/getfasta/blastdb/AABBDD_Sumai3.genome`（21 条头 `>Chr1A_Sumai3 Sumai3 AABBDD Chr1A`，即 BLAST 库的源文件）复制为 `Sumai3.fa`；
   - `samtools faidx Sumai3.fa`（21 条，合计 14,408,607,908 bp，作为唯一事实源）；
   - 写 `provenance.txt`（NCBI GCA、BioProject、下载 URL、genomic.fna.gz md5 `97cc06136176b8a880c21c0b1e7d6f86`、论文 DOI、接入日期）；
   - `annotation_update.sh Sumai3 /var/www/data/masw_data/AABBDD_Sumai3 AABBDD --init-fingerprint` → `genome_fingerprint.txt`（后续 GFF 兼容性校验的闸门）。
2. **JBrowse 规范化（保留数据集 ID `Sumai3`）**
   - 备份现有 `seq/` + `trackList.json`；把数据集目录里残留的两份 14.6 GB 源 FASTA（`GCA_051988995.1_ASM5198899v1_genomic.fna`、小写头的 `Sumai3.genome`）移出/归档（可省约 29 GB）；
   - 用 `Sumai3.fa` 重建 refseq（`prepare-refseqs.pl --fasta … --out Sumai3`）→ refseq 名统一为 `Chr1A_Sumai3…`，与 BLAST/getfasta 一致；
   - `import_jbrowse_meta.py --dataset Sumai3`，确认 API trackList 正常。
3. **卡片与引文**
   - `jbrowse.html` 卡片（保持标题 `Sumai3(AABBDD)` 以兼容 registry 的倍性解析）：
     - DOI 链接 `https://doi.org/10.1002/tpg2.70285`；
     - NCBI 链接 `https://www.ncbi.nlm.nih.gov/datasets/genome/GCA_051988995.1/`（卡片解析器会据 `GCA_…` 自动填 `assembly_accession`，并据 `ncbi.nlm.nih.gov` 填 `source_url`）；
   - `cite.html` 增加引文块（见附录 A）。
4. **getfasta 成员名修正**
   - `all_genomes_type.txt` 现有 `Sumai3.genome` 与聚合库成员 `AABBDD_Sumai3.genome` 不一致 → 统一为 `AABBDD_Sumai3.genome`（备份后改）。
5. **genome_registry 元数据写回**（rebuild 后直接 SQL UPDATE，`rebuild_genome_registry.py` 会保留已有字段）
   - `doi=10.1002/tpg2.70285`、`paper_title=…`、`journal=The Plant Genome`、`publication_year=2026`
   - `species=Triticum aestivum`、`cultivar_or_line=Sumai 3`、`subgenomes=A,B,D`
   - `assembly_accession=GCA_051988995.1`、`assembly_level=Chromosome`
   - `te_content=92.67%`（论文摘要）、`genome_size=14408607908`、`chromosome_count=21`
   - `annotation_status=pending`（注释上线前；JM229 同样用 pending）
   - `notes=NCBI GCA_051988995.1 (2025-08-13); 21 pseudomolecules; paper 14.6 Gb includes ChrUnknown 234.6 Mb (4417 contigs, not in NCBI/platform); authors' GFF not public yet`
6. **验收**
   - `/api/genomes/Sumai3` 字段齐全（DOI/组装号/物种/品种/TE/pending）；
   - JBrowse 卡片 DOI 可点、`?data=Sumai3` 200、21 条 refseq 名为 `Chr1A_Sumai3…`；
   - getfasta `/api/sequence/chromosomes?database=all_genomes&pattern=Sumai` 仍为 21 条；`/api/sequence/by-interval?region=Chr1A_Sumai3:1-60` 正常；
   - 回归：其他基因组（JM229/Zavitan/CS）BLAST、getfasta 正常。

**闸门 G1**：`genome_fingerprint.txt` 存在且 fa md5 与 BLAST 源一致；registry 元数据齐全；JBrowse 卡片 DOI 上线。

---

### Phase 2 — 注释获取（0.5 h 起草，等待外部）

> 这是唯一的外部阻塞项；Phase 1 不依赖它。

1. **向通讯作者索取**（草稿见附录 B）：
   - Jason D. Fiedler（USDA-ARS，通讯作者，`jason.fiedler@usda.gov`）；
   - 可抄送 IPK 合作者（M. Mascher / M. Spannagl，注释流程执行方）。
2. **索取清单**：
   - GFF3（gene/mRNA/exon/CDS 完整结构；HC 基因集）；
   - 注释版 CDS / protein FASTA（若已有，可省 gffread 校验）；
   - 基因/转录本 ID 规则与注释版本号（`TRAES.SUM.r1.*`）；
   - 注释对应的基因组版本（是否即 GCA_051988995.1 的 21 条 pseudomolecules；`ChrUnknown` 上是否也有 HC 基因）；
   - 数据使用/镜像许可（论文为 CC BY-NC-ND 4.0，需确认允许平台公开提供注释查询）。
3. **备选渠道**：第一作者 Rubylyn D. Mijan（NDSU）；USDA-ARS 数据联系人；IPK PGSB 数据发布渠道。
4. **决策闸门 G2**：
   - 拿到 GFF → 进 Phase 3；
   - 短期拿不到 → 保持 `annotation_status=pending`（网站已有序列层和元数据，比现状完整），下一轮再补。

---

### Phase 3 — 注释增量上线（GFF 到手后 3–4 h，其中流水线后台 2–2.5 h）

按 `genome-only-then-annotation-update.md` 的“阶段 B”执行（不重建核酸 BLAST、不影响 JBrowse 序列层）。

1. **GFF 归一化**
   - seqid → `Chr1A_Sumai3…`（对照 `Sumai3.fa.fai`）；
   - mRNA ID 必须以 `.数字` 结尾（不满足的追加 `.1`，同步 `ID=`/`Parent=`/`Derives_from=`）；
   - 不在 21 条染色体上的记录（如 `ChrUnknown`/scaffold）先统计再决定剔除，并在日志/notes 记录条数。
2. **兼容性闸门（先 `--check`，不写入）**
   - 指纹核验（fa md5 一致）；
   - `check_annotation_compat.py`：GFF seqid ⊆ FASTA、坐标 ≤ 染色体长度、mRNA ID 合法且无重复；
   - **不一致就停，禁止绕过**（不同组装版本不能混用注释）。
3. **执行 `annotation_update.sh`**（预计 2–2.5 h）
   - 建议给脚本加一个可选 `JBROWSE_DS` 覆盖参数（默认 = DS，`Sumai3` 场景传 `Sumai3`，其他基因组行为不变），服务器副本与技能副本同步；
   - 命令形如：`JBROWSE_DS=Sumai3 bash _prep/annotation_update.sh Sumai3 /var/www/data/masw_data/AABBDD_Sumai3 AABBDD`
   - 依次产出：gffread CDS/PEP → `check_genome_files.py` rc=0 → EggNOG emapper → jcvi BED + 注释 → MySQL `Genefunc_AABBDD_Sumai3_table` → 中国春 02G miniprot 映射 → `AABBDD_Sumai3.add_Description.cds/.pep` BLAST 库 + 软链 → JBrowse `all_gene` 轨道 + FeatureSequence + names → BED 02G → jbrowse_meta → `Genefunc_registry` 行 / all_gene·all_protein 聚合库 / cds `.fai` / `blast.html` All genes·All proteins → 验证。
4. **元数据收尾**
   - `Genefunc_registry` 行补 `Doi/title/Abstract/Group/Accession/display_name=Sumai3`，`display_order` 按 AABBDD 组追尾；
   - `genome_registry`：`annotation_status=available`、`gene_count`（GFF gene 数，预期 104,620）、`annotation_source=Mijan et al. 2026 (Evidence Modeler+Helixer+Mikado, HC)`、`annotation_doi=10.1002/tpg2.70285`、`gene_table=Genefunc_AABBDD_Sumai3_table`、`gene_function_ui=1`；
   - 重启 `wheatomics-api`（BLAST 库清单缓存 1 h，必须重启才立即可见）。

**闸门 G3**：MySQL 行数 = mRNA 数；CDS/PEP BLAST 库 info 正常；JBrowse trackList 含 `all_gene`；API registry/tables 可见。

---

### Phase 4 — 收尾与验收（0.5–1 h）

1. 公网核验（7 项，见 §3）；
2. 更新 `~/.agents/skills/lab-server/servers/wheatomics.yaml`（新增 Sumai3 条目：数据目录、命令、产物、遗留、smoke），`bash scripts/validate.sh` 0 error；
3. `provenance.txt`、`annotation_update_*.log` 归档；清理 `_prep` 中间文件与临时 FASTA；
4. 周报/首页公告（可选，建议下期周报补一条：Sumai 3 基因组 + FHB 抗性注释上线）；
5. 在本仓库提交计划/执行记录（生产 HTML 不在仓库，服务器改动均有备份）。

---

## 3. 验收标准（硬指标）

| # | 项 | 断言 |
|---|---|---|
| 1 | genome_registry | `/api/genomes/Sumai3`：DOI、GCA_051988995.1、Triticum aestivum、Sumai 3、A,B,D、annotation_status=available、gene_count=104620、te_content=92.67%、gene_table=`Genefunc_AABBDD_Sumai3_table` |
| 2 | MySQL | `SELECT COUNT(*) FROM Genefuncdb.Genefunc_AABBDD_Sumai3_table` = GFF mRNA 数（预期 ~10.6–11 万，以实际 GFF 为准） |
| 3 | BLAST | `blastdbcmd -info`：`AABBDD_Sumai3.add_Description.cds` / `.pep` 条数 = mRNA / peptide 数 |
| 4 | JBrowse | `/api/jbrowse/datasets/Sumai3/trackList` 含 `all_gene`；`?data=Sumai3` 200；基因结构可显示（可用 Fhb1 区域 ~Chr3B:12 Mb 做视觉核验）；FeatureSequence 菜单存在 |
| 5 | 基因功能 | `/api/genes/functions/registry`、`/tables`、`/examples` 均含新表；按基因 ID/区间/Pfam 可查 |
| 6 | getfasta / PrimerServer2 | `/api/sequence/by-gene?gene_id=<首个 mRNA>` 返回 CDS/蛋白；PrimerServer2 出现 `AABBDD_Sumai3.add_Description.cds` 且 examples 非空 |
| 7 | Web BLAST | 前端 All genes / All proteins 含 Sumai3 条目，实测一条 CDS 比对出结果 |
| 8 | 回归 | JM229 / Zavitan / CS 的 BLAST、getfasta、JBrowse 正常；`/api/genomes/stats` 计数正确 |

---

## 4. 风险与回滚

| 风险 | 概率/影响 | 对策 |
|---|---|---|
| 作者迟迟不提供 GFF | 中 / 阻塞 Phase 3 | Phase 1 先上线元数据；registry 标 `pending`；持续跟进（邮件 + 合作者渠道） |
| GFF 与现网 FASTA 版本不一致（论文 14.6 Gb vs 现网 14.41 Gb） | 中 / 高 | 指纹 + `check_annotation_compat.py` 拦截；确认 21 条染色体长度一致后再跑；不一致则要求作者按 GCA_051988995.1 坐标导出，或走完整上线流程 |
| GFF 含 `ChrUnknown`/scaffold 基因 | 中 / 中 | 统计后剔除并在 `notes`/日志记录；如确需保留，另立“补 ChrUnknown 序列”任务（重建 BLAST/JBrowse，成本高） |
| mRNA ID 不规范（如不带 `.数字`） | 中 / 低 | 归一化脚本处理并同步 Parent/ID；QC 拦截 |
| EggNOG / miniprot 超时 | 低 / 低 | 单步重跑（脚本可重复执行，表 TRUNCATE 重灌） |
| JBrowse refseq 重建影响旧坐标链接 | 低 / 低 | 目前无基因轨道、无已保存 session；备份 `seq/` 可回滚 |
| `blast.html`/`jbrowse.html` 手工改被覆盖 | 低 / 中 | 改动前备份；`/var/www/html` 不在 git 仓库，不受 webhook 覆盖；记录 diff |
| API 重启 60–90 s 短暂不可用 | 确定 / 低 | 低峰执行；重启后立即跑验收 |
| 磁盘 | 低 | 清理 JBrowse 目录冗余 FASTA 约 −29 GB；注释产物约 +5–10 GB；`/var/www` 现剩 31 T |

**回滚**（任一步失败）：

1. 恢复 `jbrowse.html` / `blast.html` / `cite.html` / `trackList.json` / `seq/` 备份；
2. DROP `Genefuncdb.Genefunc_AABBDD_Sumai3_table`，删除 `Genefunc_registry` 该行；
3. 删 `AABBDD_Sumai3.add_Description.cds/.pep` 库、软链、`.fai`；
4. 从 `all_gene.nal` / `all_protein.pal` / `blast.html` 移除 Sumai3 成员（恢复备份）；
5. `genome_registry` 恢复备份行（annotation_status 回 `pending` 或 `none`）；
6. `sudo systemctl restart wheatomics-api`。

---

## 5. 时间与资源

| 阶段 | 内容 | 预计 |
|---|---|---|
| Phase 0 | 备份 + 只读核查补完 | 0.2 h |
| Phase 1 | 数据目录/指纹 + JBrowse refseq 重建 + 元数据/卡片/引文 | 1.5–2.5 h |
| Phase 2 | 索取邮件（起草 0.5 h） | 0.5 h + 等回复 |
| Phase 3 | GFF 归一化 + 注释流水线 + 验收 | 3–4 h（后台 2–2.5 h） |
| Phase 4 | 收尾/公网核验/manifest/周报 | 0.5–1 h |

执行窗口建议：Phase 1/3 选在线人数少的时段；Phase 3 结束后重启 API。

---

## 6. 待你确认的事项（决策点）

1. **注释来源（关键路径）**
   - A. 我按附录 B 起草索取邮件，你确认后由你/平台名义发送（推荐）；
   - B. 你已有 GFF（或能从合作者拿到），直接给我文件/路径；
   - C. 本轮只做 Phase 1（元数据+规范化），注释等以后。
2. **命名方案**
   - A. **保留公开数据集 ID `Sumai3`**，内部 refseq 统一 `Chr1A_Sumai3`，表/库用 `AABBDD_Sumai3`（推荐：旧链接不变，与 BLAST/getfasta 单一事实源；需给两个收尾脚本加 `JBROWSE_DS` 覆盖，约 10 行，默认行为不变）；
   - B. 整体改名 `AABBDD_Sumai3`（与 JM229 等新基因组一致，脚本零改动，但旧 `?data=Sumai3` 链接失效，需软链/公告过渡）。
3. **`ChrUnknown` 234.6 Mb**：是否一并向作者要序列并补成 `ChrUn_*`？**建议本轮不补**（NCBI 未收录、质量低、需重建 BLAST/JBrowse），先在 registry `notes` 注明。
4. **附加范围**：周报/首页公告是否同步？SyntenyView / OrthoFinder / 表达数据是否另立任务（建议另立）。
5. **执行授权**：是否授权我在你确认后直接操作生产服务器（SSH + 备份 + 重启 API）？

---

## 附录 A：论文 / 数据源 / 引文

- 论文：Mijan, R. D., Poudel, B., Thapa, S., Ajayi-Moses, O., Lux, T., Avni, R., Xu, S., Spannagl, M., Mascher, M., Maughan, J., & Fiedler, J. D. (2026). Chromosome-scale assembly of wheat cultivar Sumai 3, a major germplasm source for Fusarium head blight resistance. *The Plant Genome*, 19(3), e70285. https://doi.org/10.1002/tpg2.70285
- PMID 42576375 ｜ PMCID PMC13459071 ｜ 许可 CC BY-NC-ND 4.0
- 通讯作者：Jason D. Fiedler（USDA-ARS, Fargo, ND, USA，`jason.fiedler@usda.gov`）
- 组装：NCBI **GCA_051988995.1**（ASM5198899v1），BioProject **PRJNA1247523**，BioSample SAMN47817036，2025-08-13 发布，21 条染色体，14,408,607,908 bp，contig N50 37,611,858 bp，949 contigs，覆盖度 26×，PacBio Sequel，TRITEX
- 论文关键数字：832 contigs（21 条染色体）+ ChrUnknown 4417 contigs / 234.6 Mb；contig N50 41.90 Mb；最长 contig 245.2 Mb；BUSCO 99.7%；104,620 HC genes；重复序列 92.67%；基因 ID `TRAES.SUM.r1.*`
- 现网证据：
  - `https://wheatomics.sdau.edu.cn/api/genomes?q=Sumai`
  - `https://wheatomics.sdau.edu.cn/api/jbrowse/datasets/Sumai3/trackList`
  - `https://wheatomics.sdau.edu.cn/api/blast/databases`（Hexaploid wheat genome 分类含 22 个 Sumai3 库）
  - `https://wheatomics.sdau.edu.cn/api/PrimerServer2/databases`
  - NCBI：`https://www.ncbi.nlm.nih.gov/datasets/genome/GCA_051988995.1/`

## 附录 B：GFF 索取邮件草稿（英文，待你确认后发送）

> Subject: Request for Sumai 3 genome annotation (GFF3/CDS/PEP) for WheatOmics integration
>
> Dear Dr. Fiedler,
>
> We are the WheatOmics team (https://wheatomics.sdau.edu.cn), a public wheat multi-omics platform that integrates genome assemblies with BLAST, JBrowse, gene-function and primer-design modules.
>
> We have integrated the Sumai 3 assembly (NCBI GCA_051988995.1, 21 pseudomolecules, 14,408,607,908 bp) from your *The Plant Genome* 2026 paper (DOI 10.1002/tpg2.70285) at the sequence level and would like to add the gene annotation so users can browse gene models and query genes.
>
> The annotation does not appear to be deposited at NCBI (the GenBank record has no gene features) and is not in the Supporting Information. Could you share:
> 1. the GFF3 of the high-confidence gene set (gene/mRNA/exon/CDS);
> 2. CDS and protein FASTA files (if already generated);
> 3. the annotation release/version and the exact assembly coordinates it corresponds to (GCA_051988995.1 21 chromosomes?);
> 4. whether any HC genes are located on the ChrUnknown pseudo-molecule (234.6 Mb) and, if so, whether that sequence can be shared;
> 5. the data-use/mirroring terms (the paper is CC BY-NC-ND 4.0) so we can display the annotation with proper citation and a link to the DOI.
>
> We will cite your paper and link the DOI on every relevant page. Happy to discuss any conditions or coordinate the release.
>
> Best regards,
> [name / WheatOmics team]

## 附录 C：本次核查使用的主要命令/证据（只读）

- 站点：`/api/genomes?q=Sumai`、`/api/genomes/Sumai3`、`/api/jbrowse/datasets/Sumai3/trackList`、`/api/blast/databases`、`/api/blast/database-example?db=AABBDD_Sumai3.genome`、`/api/PrimerServer2/databases`、`/api/sequence/chromosomes?database=all_genomes&pattern=Sumai`
- 服务器（只读）：JBrowse `Sumai3` 目录与 `seq/refSeqs.json`、`trackList.json`；`getfasta/blastdb/AABBDD_Sumai3*`；`all_genomes.nal`/`all_genomes_type.txt`；`_prep/annotation_update.sh`、`finish_genome_integration.sh`；无 `*sumai*.gff/cds/pep`、无 data 目录/指纹
- NCBI：assembly report/stats、feature_count（gene 0）、md5checksums、FTP 文件清单
- 论文：Europe PMC 全文 XML、补充材料 zip（Table S1–S5）、Crossref 元数据

## 进展记录

**2026-10-26：已补“DOI + 组装身份”元数据（本轮只动元数据/卡片/引文，未动序列层与注释层）**

| 项 | 结果 |
|---|---|
| JBrowse 卡片 | `Sumai3(AABBDD)` 卡片**只展示 DOI** 链接 `10.1002/tpg2.70285`（按策展意见不展示 NCBI 组装号；`GCA_051988995.1` 只保留在 genome_registry/API 与 notes 中） |
| cite.html | 新增 “If you use Sumai 3 genome…” 引文块（作者/标题/The Plant Genome 19(3), e70285/DOI） |
| genome_registry | `doi`、`paper_title`、`journal=The Plant Genome`、`publication_year=2026`、`citation_text/source`、`species=Triticum aestivum`、`cultivar_or_line=Sumai 3`、`subgenomes=A,B,D`、`assembly_accession=GCA_051988995.1`、`assembly_level=Chromosome`、`te_content=92.67%`、`source_url`（NCBI）、`source_md5`（NCBI genomic.fna.gz）、`notes`（ChrUnknown/注释未公开说明） |
| 备份 | `backup_sumai3_doi_20261026_113347/`、`backup_sumai3_meta_20261026_135618/`（服务器 `/var/www/data/masw_data/` 下） |
| 公网核验 | `/api/genomes/Sumai3` 字段齐全；`/jbrowse.html`、`/cite.html`、`?data=Sumai3` 均 200；卡片解析器可自动提取 DOI/NCBI/accession（供未来 rebuild） |

**仍未执行（待确认后继续）：**

1. Phase 1 剩余：数据目录 `AABBDD_Sumai3/` + FASTA 指纹、JBrowse refseq 命名统一（`chr1A_Sumai3` → `Chr1A_Sumai3`）、清理 JBrowse 目录冗余 FASTA、`all_genomes_type.txt` 成员名修正；`annotation_status` 仍为 `none`（可在注释上线前改 `pending`）。
2. Phase 2：向通讯作者索取 GFF3/CDS/PEP（邮件草稿见附录 B，待确认后发送）。
3. Phase 3：注释增量上线（依赖 GFF）。
