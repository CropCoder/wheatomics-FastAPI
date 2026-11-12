# 新基因组上线 · 一页操作清单（可勾选，2026-11 v2）

> 用法：复制本页到本次上线工单，逐项勾选。变量：
> `PLOIDY`（如 `MM`/`UU`/`AABBDD`）、`MYTAG`（数据目录后缀，如 `Aegilops_comosa_IPK_AE783`）、
> `DIR=$DATA_ROOT/${PLOIDY}_${MYTAG}`、`DOI`（论文 DOI）。
> 默认：数据根 `/var/www/data/masw_data`，脚本目录 `_prep/`。
> 图例：🤖自动 ｜ 🛠脚本 ｜ ✍人工代码/页面 ｜ ⚙️运维 ｜ ★ = 基础模块必须项
> 触点详情：[new-genome-update-checkpoints.md](new-genome-update-checkpoints.md) ｜ 完整 SOP：[wheatomics-new-genome-sop.md](wheatomics-new-genome-sop.md)

## 0. 准备（手工，一次性）

- [ ] 服务器 `_prep/` 脚本与仓库 `scripts/` md5 一致：`finish_genome_integration.sh`、`normalize_diploid.py`、`renumber_gff_ids.py`、`prepare_aegilops4_dataset.sh`、`rebuild_getfasta_aggregates.py`、`update_getsequence_search.py`、`accept_aegilops4_onboarding.py`
- [ ] 生产 repo 与 Gitee main 同步：`git fetch origin && git merge --ff-only origin/main`
- [ ] 数据目录已放好原始文件（NCBI FASTA/report + 作者 GFF/蛋白/TE）
- [ ] **仅当新 ploidy 代码 / 新类群 / 新材料** 才动代码（其余全部自动）：
  - [ ] `scripts/rebuild_genome_registry.py`：`SUB` 加新组成、overrides 加元数据（`display_name/subgenomes/chromosome_count(_hard)/genome_size/te_content/doi/...`）、必要时 `IGNORED_DATASETS`
  - [ ] `app/api/routers/blast.py`：`DB_CLASSIFICATION` 加新物种关键词（仅当库名不命中既有分类；需要重启）
  - [ ] `app/static/{interval,PfamSearch,caps}/index.html`：`groups: []` 加新 ploidy 代码（新 ploidy 才需要）
  - [ ] 以上改动 → commit/push（github+gitee）→ 生产 pull → **重启 API**

## 1. G0 命名 / 分类门禁（🛠 + ✍ 检查）

- [ ] 四件套就位（见 §2 产物）
- [ ] 预检：`finish_genome_integration.sh PLOIDY MYTAG DOI --check-name` → 出现 `[OK] 命名可直接开跑`
- [ ] 落盘：同上加 `--write-plan --confirm` → 生成 `${DIR}/name_plan.json`（`confirmed=true`）

## 2. G1/A2 归一化（🛠 一条命令）

- [ ] `bash _prep/prepare_aegilops4_dataset.sh PLOIDY MYTAG <Zenodo前缀>`
- [ ] `python3 /var/www/html/Script/check_genome_files.py MYTAG` → rc=0
- [ ] `python3 _prep/renumber_gff_ids.py --check --gff3 ${DIR}/MYTAG.gff3 --id-prefix <PFX>` → PASS
- [ ] 产物确认：`MYTAG.{fa,gff3,cds,pep}` + `idmap.tsv` + `fa.fai`

## 3. G3 流水线（🛠 25–45 min/个）

- [ ] `bash add_wheat_genome.sh MYTAG DIR PLOIDY` → `[SUCCESS]`（日志 `pipeline_MYTAG.log` 无 ERROR/Traceback）
- [ ] 抽检：`blastdbcmd -info ${DS}.genome` 序列数/总长 = FASTA；`Genefunc_${DS}_table` 行数=基因数；JBrowse `refSeqs.json`；`/api/genomes/${DS}` 已建行

## 4. G4 前（⚙️）

- [ ] 重启 API（让 `/api/blast/databases` 看到新库；worker 冷启动约 2–3 min）：
      `sudo systemctl restart wheatomics-api`，等 `/api/genomes/stats` 200

## 5. G4 收尾（🛠 1–3 min/个）

- [ ] 若 `all_genes.nal` 将超 200：先 `python3 scripts/rebuild_getfasta_aggregates.py --apply`（脚本已排除 PacBio*/Tae_TF/fangenome）
- [ ] `bash _prep/finish_genome_integration.sh PLOIDY MYTAG DOI` → rc=0、**无 `[FAIL]`**
- [ ] ★ 聚合别名 5 个均含 `${DS}.*`：`all_genomes.nal`、`all_gene.nal`、`all_genes.nal`、`all_protein.pal`、`all_proteins.pal`（+ `all_genomes_type.txt`）
- [ ] ★ `doc/getsequence_search.txt` 新增本基因组行（4 列）
- [ ] ★ `Genefunc_registry`：`display_name`=友好名、`example_species_chr_id/example_cds_id/example_protein_id` 指向真实样本
- [ ] ★ `genome_registry`：`chromosome_count`=染色体数（**不是** scaffold 数）、`subgenomes`、`display_name`、flags（`web_blast_group/getfasta_member/primerserver_fai/gene_function_ui=1`）、`visible=1`
- [ ] ★ JBrowse V2 页：hero/命名数/分组数 +1、卡片存在、CC/NN 等新分区标题正确
- [ ] ⚙️ 回写仓库：`/var/www/html/jbrowse.html` → `app/static/docpages/jbrowse.html`，`python3 scripts/deploy_doc_pages.py --check` 无 drift
- [ ] （可选）`cite.html` 引用块、`/V2.0/news.json` 新闻条目
- [ ] ⚙️ 再重启 API（刷新 GetSequence/PS2/序列缓存）

## 6. G5 验收（🛠）

- [ ] `python3 _prep/accept_aegilops4_onboarding.py` → `PASS xx | FAIL 0`
- [ ] `python3 scripts/build_blast_jbrowse_map.py --check` → rc=0
- [ ] `curl -s ${API}/api/jbrowse/coverage` → `ok=true`
- [ ] 外网抽测：`/getfasta/`（面板+示例）、`/jbrowse.html`、Web BLAST（新库可选）、`/api/PrimerServer2/databases`、CAPS 坐标模式
- [ ] registry 别名行复核：total 增量 = 目标数 + 可能的历史别名行；多余别名 `visible=0`

## 7. 收尾登记（⚙️）

- [ ] `git add/commit/push`（github+gitee）；生产 `git fetch && git merge --ff-only origin/main`
- [ ] 记录到 `docs/plans/<campaign>/`：数据/DOI/产物/验收结果/AI 报告
- [ ] 若发现新坑：更新 [SOP](wheatomics-new-genome-sop.md) 与 [触点总表](new-genome-update-checkpoints.md)

## ⚠️ 常见坑速查

| 症状 | 原因 / 处理 |
|---|---|
| GetSequence 查不到新基因 | 页面查 `all_genes`/`all_proteins`（复数）；收尾 step 5/5b 已处理；>200 成员先 `rebuild_getfasta_aggregates.py --apply` |
| `batch` 返回 `Skipped` 尾部基因组 | BLAST 别名 200 成员上限；重建压回 ≤200（finish 新成员已改前插） |
| `/api/blast/databases` 看不到新库 | 1h 磁盘缓存；重启 API |
| 面板/基因组名显示技术名 | `Genefunc_registry.display_name`、`genome_registry.display_name` 用友好 label |
| `chromosome_count` 变成 17/24/250/21 | rebuild 用 `.fai` 序列数填充；overrides 加 `"_hard": ["chromosome_count"]` |
| API 重启后短暂 curl 000 | worker 冷启动 2–3 min，属正常 |
| docroot 改了页面上线后又被覆盖 | finish 改 docroot；须回写 repo 源 + `deploy_doc_pages.py` |
| 单基因 CDS 取不到（所有基因组） | 平台既有限制：`blastdbcmd -entry` 不支持核酸别名库；用 `/api/sequence/batch` |
