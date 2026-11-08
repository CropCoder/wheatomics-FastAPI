# AABB_Wild_emmer_Zavitan 上线计划（已确认版）

> 目标：把 *Nature Genetics* 2026（DOI 10.1038/s41588-026-02808-3）的野生二粒小麦 Zavitan
> 近完整基因组 **WEW_NT** 完整接入 WheatOmics 平台。
> 命名/分类方案 **2026-10-23 已确认（方案 B）**，依据：SOP §0.5 命名/分类预检。
> 依据 SOP：`~/.agents/skills/lab-server/references/wheatomics-new-genome-sop.md`

## 0. 已确认的命名与分类方案（不可再变）

| 项 | 值 |
|---|---|
| PLOIDY（亚基因组） | **AABB**（野生二粒小麦：A + B，四倍体） |
| MYTAG | **Wild_emmer_Zavitan** |
| 数据集 / 库 / 表 | **AABB_Wild_emmer_Zavitan**；`Genefunc_AABB_Wild_emmer_Zavitan_table` |
| 前端显示名 | Zavitan (near-complete, 2026) |
| getfasta / BLAST 库分类 | `tetraploid_wheat` → "Tetraploid wheat genome"（命中 `wild_emmer`，零代码改动）|
| Web BLAST 下拉 | Tetraploid wheat genome |
| JBrowse 分区 | **Allotetraploid Wheat JBrowse**（既有分区，22 个数据集） |
| PrimerServer2 位置 | 字母序第 69/205，`AABB_Wild_emmerV2` 之后 |
| Genefunc_registry | Polyploidy=AABB，Group=Tetraploid，display_order=98 |
| genome_registry | ploidy=AABB，subgenomes="A,B"，assembly_level=Chromosome |
| all_genomes_type.txt | `AABB_Wild_emmer_Zavitan.genome<TAB>AABB` |

> 命名沿革：初版拟用 `AABB_WEW_NT` → 因分类落 other 改为 `AABB_Wild_emmer_WEW_NT` → 按策展意见（基因组即 accession Zavitan）
> 于 16:00 定为 **`AABB_Wild_emmer_Zavitan`**（流水线在 Step 7.1 中止后按新名重跑，见 §6）。
> 说明：`AABB_WEW_NT` 这个名字会让库分类掉进 "Other / Unclassified"（库名子串匹配不到四倍体关键词），
> 故改用含 `Wild_emmer` 的 MYTAG —— 这是本计划与最初草案的唯一差别。

## 1. 现状

| 项 | 状态 |
|---|---|
| 基因组 FASTA（GWH `GWHHHUI00000000.1`，3.01 GB，md5 `663e9bd6d74195f4d0801a548c68f34f`） | 下载中（约 94%，临时目录 `AABB_WEW_NT/`） |
| Zenodo 注释 9 文件 | ✅ 已下完（GFF 解压 320 MB，92,943 基因 / 188,115 mRNA） |
| 流水线脚本 | md5 `208f065391ba86de39d41ea8530ff567`（10-23 版，含命名门禁） |
| 收尾脚本 | `finish_genome_integration.sh`（PT 实测 9/9 验收通过） |

## 2. 阶段计划

### Phase 0 — 下载收尾 + 目录改名（约 10 min）
1. 等 `fetch.log` 出现 `ALL DONE`，确认 `md5sum -c` 通过
2. 目录改名：`mv AABB_WEW_NT AABB_Wild_emmer_Zavitan`（同盘，秒级）
3. 写入命名方案（流水线门禁要求）：
   ```bash
   _prep/finish_genome_integration.sh AABB Wild_emmer_Zavitan 10.1038/s41588-026-02808-3 \
     --label "Zavitan (WEW_NT, 2026)" --section-existing "Allotetraploid Wheat JBrowse" \
     --accession GWHHHUI00000000.1 --species "Triticum turgidum ssp. dicoccoides" \
     --cultivar Zavitan --journal "Nature Genetics" --year 2026 \
     --title "Near-complete assembly of wild emmer wheat unveils centromere reorganization during polyploid evolution" \
     --source-url "https://download.cncb.ac.cn/gwh/Plants/Triticum_dicoccoides_WEW_NT_GWHHHUI00000000.1/GWHHHUI00000000.1.genome.fasta.gz" \
     --source-md5 663e9bd6d74195f4d0801a548c68f34f --check-name --write-plan --confirm
   ```
   → 生成 `AABB_Wild_emmer_Zavitan/name_plan.json`
- **闸门 G0**：md5 通过；`name_plan.json` 存在且 `ds` 正确

### Phase 1 — 归一化（约 40–60 min）

工作目录 `/var/www/data/masw_data/AABB_Wild_emmer_Zavitan/`，四件套名 `Wild_emmer_Zavitan.{fa,gff3,cds,pep}`
1. **FASTA 重命名**（`genome/*.fasta.gz` → 新目录）：`OriSeqID=chr1A` → `>Chr1A`；
   未定位序列 `contig_*` → `ChrUn_contig_*`；生成 `seqid_mapping.tsv`
2. **GFF 同步**：`chr1A`→`Chr1A`、`contig_99`→`ChrUn_contig_99`（4 条特征，若 FASTA 无对应序列则剔除并记录）
   - mRNA ID `TRIDC1AG...0001.1` 已合规，无需改写
3. **CDS/PEP**：用 Zenodo 官方文件，校验 ID 与 GFF mRNA 一一对应、pep 无 `.`；不合规则 gffread 重导
4. **质检**：`check_genome_files.py Wild_emmer_Zavitan` → rc=0
- **闸门 G1**：四件套齐备 + QC 通过

### Phase 2 — 流水线（约 2–2.5 h，后台）
```bash
export PATH=/var/www/html/blast/blast+/bin:/home/fei/mambaforge/bin:$PATH; export HOME=/home/fei
cd /var/www/data/masw_data/AABB_Wild_emmer_Zavitan
setsid --fork bash -c "exec bash /var/www/data/masw_data/add_wheat_genome.sh \
  Wild_emmer_Zavitan /var/www/data/masw_data/AABB_Wild_emmer_Zavitan AABB" \
  > pipeline_Wild_emmer_Zavitan.log 2>&1 < /dev/null
```
- 入口门禁会校验 `name_plan.json`（缺失/不符直接拒绝）
- **闸门 G2**：日志出现 `[SUCCESS] Wild_emmer_Zavitan 全部完成`

### Phase 3 — 验收（15 min，SOP §4）
MySQL 行数=188,115；BLAST 库（含整基因组）；JBrowse refSeqs；02G BED；`/api/jbrowse/datasets`
- **闸门 G3**：四项通过

### Phase 4 — 前端/接口接入（约 15 min，脚本化）
```bash
_prep/finish_genome_integration.sh AABB Wild_emmer_Zavitan 10.1038/s41588-026-02808-3 --dry-run   # 先看计划
_prep/finish_genome_integration.sh AABB Wild_emmer_Zavitan 10.1038/s41588-026-02808-3            # 正式
```
自动完成：JBrowse 卡片（插入 Allotetraploid Wheat 分区）、Web BLAST group/All genes/All proteins、
`.fai`、`Genefunc_registry`（display_order=98）、聚合库 alias、jbrowse_meta、genome_registry 重建 + 元数据写回、
9 项验收（含 `--expect-category` 断言分类归属，值来自 plan）。

**仍需人工**：getfasta 分类**无需改**（`wild_emmer` 关键词已覆盖）；cite.html 引文、TE/CENH3 轨道可选。
- **闸门 G4**：9 项验收全 OK

### Phase 5 — 收尾（10 min）
- 更新 `wheatomics.yaml`（新增基因组条目 + smoke）
- 记录 `AABB_Wild_emmer_Zavitan/provenance.txt`
- 公网核验：JBrowse 卡片、BLAST 实测、getfasta、PrimerServer2

## 3. 本轮不做（已确认）

- **SNP/Indel/SV VCF（约 135 GB 分片）**：不上线，仅在 genome_registry notes 里登记来源
- **CENH3 bigwig 轨道**（Zenodo 22198553）：暂不做，后续需要再加
- **Synteny / OrthoFinder**：需另建 genome_info/genome_type，本轮跳过

## 4. 风险与对策

| 风险 | 对策 |
|---|---|
| FASTA/GFF 命名不一致 | 统一映射表；跑前交叉核对 seqid 集合 |
| GFF 里 4 条 `contig_99` 特征无对应序列 | 核对后剔除并记录 |
| CDS/PEP 与 mRNA ID 不匹配 | gffread 重导 |
| EggNOG 超时 | 单步重跑 |
| API 重启 60–90 s | 放在最后一步；当前在线人数少 |
| 磁盘 | 增量约 60 GB，`/var/www` 剩 31 T |

## 5. 回滚

删目录 `AABB_Wild_emmer_Zavitan`；删 `blastdb/AABB_Wild_emmer_Zavitan.*` 与拆分库、软链；
删 JBrowse 数据集；DROP `Genefunc_AABB_Wild_emmer_Zavitan_table`；清 jbrowse_meta / genome_registry 行；
从 `all_*.nal/pal`、`all_genomes_type.txt` 移除成员；恢复 HTML 备份；重启 API。


## 6. 命名变更记录（2026-10-23 16:00）

- 15:25 以 `AABB_Wild_emmer_WEW_NT` 启动流水线，跑到 Step 7.1（EggNOG）时按策展意见改名
- 16:01 停止流水线、清理半成品（159 个 BLAST 库文件 + 159 个软链 + JBrowse 目录 + 15 个中间文件 + eggnog scratch）
- 16:02 目录/四件套改名 `Wild_emmer_Zavitan.*`，重写 `name_plan.json`（分类仍为 tetraploid_wheat）
- 16:03:44 流水线以新名重启（`Th.ponticum_public` 的流水线未受影响）
- 旧日志归档：`pipeline_aborted_WEW_NT.log`


## 7. 完成记录（2026-10-23）

| 阶段 | 结果 |
|---|---|
| Phase 0 下载+改名+plan | 14:59 下载完成，md5 `663e9bd6…` 一致；16:03 改名 `AABB_Wild_emmer_Zavitan` 并落盘 name_plan.json |
| Phase 1 归一化 | 15:25 完成，QC rc=0（114 seqs / 10.47 Gb；92,943 gene / 188,115 mRNA）|
| Phase 2 流水线 | 16:03→**17:09:38 [SUCCESS]** |
| Phase 3 验收 | MySQL 188,115；BLAST 114/188,115/188,115；JBrowse 114 refSeqs + 2 tracks；02G BED 188,115 |
| Phase 4 收尾 | `finish_genome_integration.sh` 13/13 OK：卡片（Allotetraploid Wheat 分区，25 卡）、BLAST group、fai×2、registry display_order=501、聚合库 alias、genome_registry 元数据+派生事实 |
| Phase 5 收尾 | manifest 已登记；provenance.txt 已写；公网核验通过 |
| 外部阻塞 | Th.ponticum 别名损坏已由用户修复，聚合库恢复（123,063 seqs / 1.66 Tb），本轮 20:31 复验通过 |

收尾脚本在实跑中修掉的 bug（已回写技能脚本）：DDL 凭据串味、ORD 未传入、转义错误、
新基因组的 subgenomes/gene_count/annotation_status/assembly_level 派生补齐、流水线 Step 10 的 LOG 变量 bug。
