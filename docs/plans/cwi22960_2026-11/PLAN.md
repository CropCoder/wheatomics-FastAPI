# CWI 22960（dika wheat / *T. turgidum* ssp. *carthlicum*, AABB）平台接入计划

> 日期：2026-11-13 ｜ 依据：`docs/workflow/wheatomics-new-genome-sop.md`（v2）+ `docs/workflow/new-genome-quick-checklist.md`
> 前置成果：EGAPx v3 注释已完成（`cwi22960_release/annotation_v3/`，BUSCO 99.2%，87.7% 模型有长读支持）
> 本计划逐项勾选执行，避免遗漏；⚠️ = 需要你先确认/提供的事项

## 0. 变量与决策

```
PLOIDY=AABB
MYTAG=Carthlicum_CWI22960
DS=AABB_Carthlicum_CWI22960
DIR=/var/www/data/masw_data/AABB_Carthlicum_CWI22960
DOI=10.1038/s42003-026-11303-8
ACC=GCA_977050835.1
SPECIES="Triticum turgidum subsp. carthlicum"
CULTIVAR="CWI 22960"
JOURNAL="Communications Biology"; YEAR=2026
LABEL="Carthlicum wheat CWI 22960 (AABB)"
GENOME_MD5=4458e202c46347798298a5624f71c47b
```

| # | 决策 | 推荐 | 状态 |
|---|---|---|---|
| D1 | 用哪个注释版本上平台 | **v3**（全量 IsoSeq + 质量过滤；BUSCO 99.2%；87.7% 模型有长读证据） | ✅ 已定（2026-11-13） |
| D2 | 基因 ID 方案 | **方案 A：保留 v3 规范化 ID**（基因 `CWI22960_XXXXXX`、转录本 `CWI22960_XXXXXX.k`，已满足平台硬约束：mRNA 以 `.数字` 结尾）｜方案 B：用 `renumber_gff_ids.py --id-prefix "CWI22960."` 改成 `CWI22960.1AG000100` 平台风格（多一步重编号+复核；若要与 AeCom 等先例完全一致可选 B） | ⚠️待确认 |
| D3 | ChrUn_scaffold_* 与未定位基因 | **全部保留**（10,708 scaffolds / 187 个未定位基因；JBrowse refSeqs 10,722 条） | 推荐已定 |
| D8 | 上平台 GFF 的范围 | **只保留 protein-coding gene/mRNA/exon/CDS（102,975 条）**，与平台基因表/BLAST CDS 口径一致；假基因 28,622 + lncRNA 10,188 + 其他 transcript 4,863 只留在交付包、不上平台（避免流水线/BED/基因表口径混乱） | ⚠️待确认 |
| D4 | JBrowse 加 RNA-seq bigWig 轨道（4 个） | **加**（平台首次有 bigWig 轨道，先 1 个试点再批量） | ✅ 已定（2026-11-13） |
| D5 | JBrowse 加 IsoQuant 转录本轨道（108,786 条） | 暂不加（保留脚本/文件，后续可加） | ✅ 已定（2026-11-13） |
| D6 | 代码改动（两处） | (a) `app/api/routers/blast.py`：`tetraploid_wheat.keywords` += `carthlicum`, `dika`（G0 门禁用；registry 建好后分类由 ploidy 决定）；(b) `scripts/rebuild_genome_registry.py`：加 CWI22960 override（display_name/subgenomes=["A","B"]/chromosome_count=14 `_hard`/genome_size=10881024180/annotation_status=available/gene_count=102975/doi/journal/year/accession/flags） | 必须做 |

## 0.1 执行状态（滚动更新）

| 时间 | 事项 | 状态 |
|---|---|---|
| 2026-11-13 23:10 | 计划落盘；清理跳板残留隧道 52416；验证隧道可建 | ✅ |
| 2026-11-13 23:15 | **节点密码被拒**（USM userauth failed，4 个实例 IP 均试）→ 等用户更新 `WHEATOMICS_NODE_ENV` 中 NODE_PASS | ⏳ 阻塞 |
| 2026-11-13 23:18 | 本地准备：v3 GFF 组成拆解（146,648 转录本 = 102,975 protein-coding + 28,622 pseudogene-mRNA + 10,188 lncRNA + 4,863 transcript）；生成 protein-coding-only 平台候选 GFF3（80,158 基因 / 102,975 mRNA / 580,440 exon / 520,785 CDS） | ✅ |
| 2026-11-13 23:19 | 平台套装：`cwi22960_release/platform_bundle/`（gff3/cds/pep + provenance + MD5SUMS）；基因组 fa 在 Ma 上 gzip 中 | ✅/⏳ |
| 2026-11-14 00:05 | **登录问题定位**：节点 USM 门禁接受 publickey 后拒绝 exec（误导性 "check password"）→ 强制 `PubkeyAuthentication=no -o PreferredAuthentications=password` 即通；密码本身无需修改 | ✅ |
| 2026-11-14 00:20 | 服务器现状核查、AABB 先例调研（NU00021=TrcarPEA1A01G000020.1，Group=Tetraploid）；备份 `_backup_20261114_cwi22960` | ✅ |
| 2026-11-14 00:21 | 代码改动已提交并双推（github+gitee `c408097`）：blast.py 加 carthlicum/dika 关键词、registry override、renumber_gff_ids 加 --chr-suffix + 非编码转录本类型；生产已 pull + API 重启；`_prep/renumber_gff_ids.py` 已同步 | ✅ |
| 2026-11-14 00:22 | ID 方案落地：`TrcarCWI22960.r1.<chr>01G<6位>.k`，step=10（对齐 NU00021 先例；Chr2B 10,195 基因，step=100 会溢出 6 位）；GFF 保留全部转录本（pseudogene mRNA→pseudogenic_transcript、lncRNA/transcript 保留；BED/Gene 表=102,975 mRNA） | ✅ |
| 2026-11-14 00:25 | **G0 通过**：`finish_genome_integration.sh ... --check-name --write-plan --confirm` → `[OK] 命名可直接开跑`；name_plan.json 已生成 | ✅ |
| 2026-11-14 00:27 | 数据上传：fa.gz 分 4 片并行（3.39 GB）+ 注释已传完并 md5 校验（gff3/cds/pep）；预计 ~01:30 完成 | ⏳ |
| 2026-11-14 00:28 | 已挂自动 watcher：分片合并+md5校验 → 解压 faidx → G2 质检 → 自动启动 G3 流水线（日志 `pipeline_Carthlicum_CWI22960.log`） | ✅ |
| 2026-11-14 01:46 | **G3 流水线 [SUCCESS]**（~1h02m）：BLAST 库/基因表/JBrowse/02G 全部产出 | ✅ |
| 2026-11-14 10:03 | **G4 收尾**：卡片/registry/别名/示例行/映射全部完成（0 FAIL） | ✅ |
| 2026-11-14 10:06 | **4 个 RNA-seq bigWig 轨道**加入 JBrowse 并通过 Range 校验 | ✅ |
| 2026-11-14 10:12 | **事故修复**：G4 旧版 step_aliases 覆盖 base+delta 聚合库 → 恢复 + 用 update_blast_alias 正确追加；getfasta 203→204 | ✅ |
| 2026-11-14 10:15 | **G5 公网验收全过**（详见 DEPLOY_LOG.md） | ✅ |

## 1. 触点总表（一个基因组要动的地方，逐项打勾）

| # | 触点 | 产物/校验 | 计划阶段 |
|---|---|---|---|
| 1 | 数据目录四件套 `.fa/.gff3/.cds/.pep` | md5 双端一致、check_genome_files rc=0 | P1 |
| 2 | `name_plan.json` 命名门禁 | `--check-name` OK、`confirmed=true` | P2 |
| 3 | BLAST 核酸库（整基因组 + 14 染色体拆分） | blastdbcmd -info 序列数/总长 | P3 |
| 4 | CDS/PEP BLAST 库（`.add_Description.cds/.pep`） | 库存在、序列数=102,975 | P3 |
| 5 | MySQL `Genefunc_${DS}_table` | 行数=102,975 | P3 |
| 6 | 中国春 02G 同源映射（miniprot） | `ChineseSpring02G` 列非空率抽查 | P3 |
| 7 | JBrowse 数据集（refSeqs/trackList/names） | refSeqs.json=10,722；`/api/jbrowse/datasets/${DS}` | P3 |
| 8 | `jbrowse_meta` 库（tracks 导入） | `/api/jbrowse/datasets/${DS}/trackList` 有轨道 | P3/P5 |
| 9 | **bigWig 轨道 ×4（新能力）** | trackList 含 4 轨、Range 请求 206 | P5 |
| 10 | **IsoQuant 转录本轨道（可选）** | trackList 含 isoseq 轨 | P5 |
| 11 | `genome_registry` 行 + 元数据 | `/api/genomes/${DS}` 字段全 | P3/P4 |
| 12 | `Genefunc_registry` 行（display_name/examples） | 示例 ID 指向真实基因 | P4 |
| 13 | getfasta 聚合库（all_genomes/all_gene(s)/all_protein(s)） | 5 个别名均含 `${DS}.*` | P4 |
| 14 | `doc/getsequence_search.txt` 一行 | 页面示例表出现 | P4 |
| 15 | BLAST→JBrowse 映射 | `build_blast_jbrowse_map.py --check` rc=0 | P6 |
| 16 | JBrowse V2 页面卡片/分区/计数 | 卡片存在、AABB 分区 +1 | P4 |
| 17 | `cite.html` 引用 | 可选 | P4 |
| 18 | PrimerServer2 `.fai` / databases | `/api/PrimerServer2/databases` 含 DS | P6 |
| 19 | 前端分类（wheatBLAST SPA / getfasta 面板） | 动态，无需改 HTML | P6 |
| 20 | 文档/SOP 更新 + 验收报告 | `docs/plans/cwi22960_2026-11/` | P7 |

## 2. P0 —— 服务器访问与前置（⚠️ 目前卡在凭据）

**现状（2026-11-13 实测）**
- ✅ 跳板隧道可建：`ssh -p 222 nifei@202.194.133.96 -N -L 2222:202.194.139.32:22`（跳板密码 `~/.config/lab-server/wheatomics.env`；已 kill 一个残留隧道进程 52416 释放会话名额）
- ❌ **节点登录被拒**：`ssh -p 2222 fei@127.0.0.1` → `[USM] 'exec' userauth failed, please check fei@... password`；试了 004/003/005/006 四个实例 IP 全部被拒 → **`WHEATOMICS_NODE_PASS` 可能已过期/改密，或账号受限**
- 备注：节点有 USM 门禁代理，公钥认证被拒，只能密码

**待你提供/确认**
1. 更新 `~/.config/lab-server/wheatomics.env` 里的 `WHEATOMICS_NODE_PASS`（fei@节点密码），或告知其他可登录账号；
2. 确认可走 SSH 密码方式（我们已用 `SSH_ASKPASS` 绕过本地 pty 沙箱限制，隧道通、只差节点密码）。

**P0 后续步骤（凭据就绪后执行）**
- [ ] 验证：`ssh -p 2222 fei@127.0.0.1 'hostname; whoami; df -h /var/www/data | tail -1'`
- [ ] 生产 repo 版本、`_prep` 脚本 md5 与仓库一致（finish_genome_integration.sh / normalize_diploid.py / renumber_gff_ids.py / add_wheat_genome.sh）
- [ ] 服务器磁盘 ≥ 60 GB；`/var/www/html/getfasta/blastdb` 可写
- [ ] 备份到 `/var/www/data/masw_data/_backup_20261114/`：`jbrowse.html`、`cite.html`、`all_genomes.nal`、`all_genes.nal`、`all_proteins.pal`、`all_genomes_type.txt`、`genome_registry`/`Genefunc_registry` SQL、`doc/getsequence_search.txt`
- [ ] 确认既有 AABB 先例的 ID 风格（NU00021 / 其他 AABB GFF 前几行）与 `Genefunc_registry` 的 GROUP 值 → 用于 D2 决策与 `--group` 参数

## 3. P1 —— 数据准备与传输

- [ ] 生成平台四件套（命名按 MYTAG）：
  - `Carthlicum_CWI22960.fa` = `inputs/CWI22960.fa`（10,722 条：Chr1A…Chr7B + ChrUn_scaffold_*；10,881,024,180 bp）
  - `Carthlicum_CWI22960.gff3` = v3 平台规范化 GFF3（436 MB；若 D8=推荐方案则裁剪为 protein-coding 102,975 条转录本：gene/mRNA/exon/CDS）
  - `Carthlicum_CWI22960.cds` = v3 CDS FASTA（102,975 条）
  - `Carthlicum_CWI22960.pep` = v3 蛋白 FASTA（102,975 条；无 `.`/`*`/内部终止）
- [ ] 计数校准（v3 全量 GFF 组成：基因 114,659 = gene 86,322 + pseudogene 28,337；转录本 146,648 = mRNA 131,597 + lncRNA 10,188 + transcript 4,863；其中有 CDS 的蛋白编码转录本 102,975）
- [ ] 传输：Mac → 节点（`scp -P 2222`，经隧道）；或 Ma → 节点直连（若 Ma 可达 202.194.139.32）；`fa` 先在 Ma 上 `pigz`（~3.2 GB）
- [ ] 目标目录：`$DIR`；传输后两端 `md5sum` 对拍
- [ ] `provenance.txt`（GCA/PRJEB101210/BioSample SAMEA120412366/下载 URL/md5/DOI/期刊/年份/归一化规则/接入日期）
- [ ] `seqid_mapping.tsv`（GenBank accn ↔ Chr 名）已有，拷入

## 4. P2 —— G0 命名门禁

- [ ] 先部署 D6 代码改动（commit → push github+gitee → 生产 `git fetch && git merge --ff-only`）→ 重启 API
- [ ] `finish_genome_integration.sh AABB Carthlicum_CWI22960 $DOI --check-name --cultivar "$CULTIVAR" --accession $ACC --species "$SPECIES" --group "<确认值>"` → `[OK] 命名可直接开跑`
- [ ] 同命令加 `--write-plan --confirm` → `$DIR/name_plan.json`（`ds=AABB_Carthlicum_CWI22960`、confirmed=true）
- [ ] G0 通过记录：SUB[AABB] 映射、3 个库名分类 = tetraploid_wheat

## 5. P3 —— G2 质检 + G3 流水线

**G2**
- [ ] `python3 /var/www/html/Script/check_genome_files.py Carthlicum_CWI22960` → rc=0
- [ ] `normalize_diploid.py check --dir $DIR`；计数断言：fa 10,722 / 10,881,024,180 bp；GFF genes 114,659 / mRNA 102,975；cds/pep 102,975
- [ ] 若 D2=B：`renumber_gff_ids.py --check --gff3 $DIR/Carthlicum_CWI22960.gff3 --id-prefix "CWI22960."` PASS（并重生成 cds/pep）

**G3**
- [ ] `export PATH=/var/www/html/blast/blast+/bin:/home/fei/mambaforge/bin:$PATH; export HOME=/home/fei`
- [ ] `setsid --fork bash /var/www/data/masw_data/add_wheat_genome.sh Carthlicum_CWI22960 $DIR AABB > $DIR/pipeline_Carthlicum_CWI22960.log 2>&1`
- [ ] 监控日志；预期 1.5–2.5 h；`[SUCCESS]`
- [ ] 断言：整基因组库 10,722 seqs / 10,881,024,180 bp；14 染色体库齐；`Genefunc_${DS}_table` 行数 = BED/转录本数（D8 推荐方案下 = 102,975；以流水线 BED 实测为准）；`refSeqs.json` = 10,722；`/api/genomes/${DS}` 已建行
- [ ] 失败重跑前清理半成品（`.genome_*`、同名 blastdb、JBrowse 目录）

## 6. P4 —— 重启 API + G4 收尾

- [ ] `sudo systemctl restart wheatomics-api`；等 `/api/genomes/stats` 200（2–3 min）
- [ ] `finish_genome_integration.sh AABB Carthlicum_CWI22960 $DOI --label "$LABEL" --accession $ACC --species "$SPECIES" --cultivar "$CULTIVAR" --journal "$JOURNAL" --year 2026 --source-url "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/977/050/835/GCA_977050835.1_CWI22960/" --source-md5 $GENOME_MD5 --group "<确认值>" --section-title "AABB" --section-desc "Carthlicum wheat (AABB)" --search-extra "carthlicum dika cwi 22960 aabb tetraploid turgidum" --dry-run`
- [ ] 正式跑；rc=0、无 `[FAIL]`
- [ ] 断言：JBrowse V2 卡片存在、AABB 分区计数 +1；`Genefunc_registry` display_name/examples 正确；5 个 getfasta 别名含 `${DS}.*`；`getsequence_search.txt` 新增行；`genome_registry` 字段（chromosome_count=14、subgenomes=A,B、visible=1、flags）

## 7. P5 —— JBrowse 轨道（bigWig ×4 + IsoQuant）

> 平台此前无 bigWig 轨道，这是首次；先做 1 条试点，确认 API/前端后再批量。

- [ ] 拷贝 4 个 bw 到 `/var/www/html/jbrowse-1.12.3-release/${DS}/tracks/`
- [ ] 用 `bin/add-bw-track.pl`（或手改 trackList.json）添加 4 轨：`rnaseq_leaf/root/stem/all`（CPM，autoscale）
- [ ] `import_jbrowse_meta.py --dataset ${DS}` 重新导入
- [ ] 校验：`/api/jbrowse/datasets/${DS}/trackList` 含 4 轨；Apache Range 请求 `.bw` 返回 206；JBrowse 页面能看到轨道
- [ ] （D5 若加）IsoQuant：`OUT.transcript_models.gff3` → `flatfile-to-json.pl`（NCList，track `isoseq_transcripts`）→ 重新 import meta → 校验 trackList/页面
- [ ] 回滚：删除 track 条目 + 重新 import meta

## 8. P6 —— 收尾核验（G5）

- [ ] `jbrowse.html` docroot 回写仓库 `app/static/docpages/jbrowse.html`；`deploy_doc_pages.py --check` 无 drift
- [ ] `cite.html` 加论文引用（可选）
- [ ] `build_blast_jbrowse_map.py --check` rc=0（不通过则先运行重建）
- [ ] aggregate aliases 复核；若 all_genes 成员超 200 → `rebuild_getfasta_aggregates.py --apply`
- [ ] 再重启 API；全量 smoke：
  - `/api/genomes/${DS}`、`/api/genomes/stats`、`/api/blast/databases`（新库分类 tetraploid_wheat）、`/api/jbrowse/datasets`、`/api/sequence/chromosomes?database=${DS}.genome`、`/api/sequence/by-gene?gene_id=<example>&protein_db=all_proteins`、`/api/sequence/by-interval?region=Chr1A_${MYTAG}:200-500&database=all_genomes`、`/api/PrimerServer2/databases`
  - 页面：`/getfasta/`（面板+示例）、`/jbrowse.html`（卡片+轨道）、wheatBLAST SPA、`cite.html`
- [ ] 回归：NU00021 等既有 AABB 查询仍正常；AABB 计数 22→23；其他基因组 API 无异常
- [ ] G5 验收脚本：复制 `accept_aegilops4_onboarding.py` → `accept_cwi22960_onboarding.py`（改 DS/计数/示例ID）；`PASS xx | FAIL 0`
- [ ] 记录验收报告到 `docs/plans/cwi22960_2026-11/`

## 9. P7 —— 登记与交付

- [ ] 更新 `CWI22960_genome_update_plan.md` / `STATUS.md`；仓库 commit（github+gitee）→ 生产 pull → 重启 API
- [ ] 若遇到新坑：更新 SOP + quick-checklist
- [ ] 交付清单：平台 URL、JBrowse 数据集名、BLAST 库名、示例基因 ID、验收结果

## 10. 时间与风险

| 项 | 估计 |
|---|---|
| P0 访问修复 | 取决于凭据（⚠️） |
| P1 传输+准备 | 0.5–1 h（fa ~3.2 GB gz + 注释 0.6 GB） |
| P2 G0 | 10 min（含一次 API 重启） |
| P3 G3 流水线 | 1.5–2.5 h |
| P4 G4 收尾 | 20–30 min |
| P5 轨道 | 0.5–1.5 h（IsoQuant 转换 ~20 min） |
| P6 验收 | 1–2 h |
| 合计 | **约 5–8 h**（同一天可完成）+ 1 次/2 次 API 重启（各 60–90 s 不可用，建议低峰执行） |

风险与回滚：
- API 重启短暂不可用 → 低峰执行；回滚 = 重启旧代码
- G4 改 docroot/DB → 已有备份；回滚 = 还原文件 + SQL dump + 重启
- bigWig 轨道首次落地 → 先 1 轨试点；回滚 = 删 track 条目 + re-import meta
- 流水线中途失败 → 按 SOP §6 清理半成品重跑
- D2 若之后反悔改 ID → 成本高（全平台引用），务必现在定
- ChrUn 10,708 条 → JBrowse/BLAST 体积大但已有先例（PT 等）
