# 新基因组上线：需要更新的全部地方（触点清单 / 2026-11-12）

> 目的：回答「一个基因组来了以后，需要更新哪些地方」。
> 本表由 4 个二倍体 Aegilops 实际上线（2026-11-11 ~ 11-12）逐项核对整理，标注每项是**自动派生**还是**需要人工/脚本**，以及怎么验证。
> 相关文档：[SOP](wheatomics-new-genome-sop.md) ｜ 实战报告：[G3_G4_G5_REPORT](../plans/aegilops4_2026-11/G3_G4_G5_REPORT.md)

约定：
- `DS = ${PLOIDY}_${MYTAG}`（例：`MM_Aegilops_comosa_IPK_AE783`），数据目录 `/var/www/data/masw_data/${DS}/`
- 图例：🤖 = 平台自动派生/无需改代码；🛠 = 脚本自动（收尾/流水线）；✍ = 需要人工改代码/页面；⚙️ = 需要运维动作（重启/发布）
- 「基础模块」= 一个基因组上线必须通的：BLAST / GetSequence / JBrowse / 基因功能表 / PrimerServer2 / CAPS / Web BLAST / registry。

## 0. 一图总览

```
             ┌──────────────── 输入（NCBI FASTA + 作者 GFF/蛋白）──────────────┐
             │ A2 归一化（prepare_aegilops4_dataset.sh）：fa/gff3/cds/pep + idmap │
             └──────────────────────────────┬─────────────────────────────────┘
                                            ▼
  G3 add_wheat_genome.sh（10 步）      G4 finish_genome_integration.sh（10 步）        G5 accept_aegilops4_onboarding.py
  ├ A1 格式/标准化/拆分/拷贝          ├ 1 JBrowse V2 卡片/计数（docroot）             ├ 102 项逐条验收
  ├ A3 BLAST 核酸/蛋白库              ├ 2 Web BLAST（SPA 动态，一般跳过）
  ├ B1 Genefunc 表 + 02G 映射         ├ 3 .fai（PrimerServer2/GetSequence）
  ├ C1 JBrowse 数据/轨道/名字索引     ├ 4 Genefunc_registry 行（GetSequence 面板）
  ├ B4 jbrowse_meta 导入              ├ 5  聚合别名（all_genomes/all_gene/all_genes/…）
                                      ├ 5b getsequence_search.txt 文档行
                                      ├ 6-8 jbrowse_meta 重导 / genome_registry 重建 / 元数据回写
                                      ├ 9  BLAST↔JBrowse 映射
                                      └ 10 验收断言
```

## 1. 数据与索引（A 组）

| # | 触点 | 位置 | 谁更新 | 验证 |
|---|---|---|---|---|
| A1 | 四件套归一化 FASTA/GFF3/CDS/PEP（含 ID 规范化） | `${DS}/<MYTAG>.{fa,gff3,cds,pep}` + `idmap.tsv` | 🛠 G1/A2（`prepare_aegilops4_dataset.sh`） | `check_genome_files.py` rc=0；ID 规则 `renumber_gff_ids.py --check` |
| A2 | `.fai` 索引（genome + CDS） | `/var/www/html/getfasta/blastdb/<DS>.genome.fai`、`.add_Description.cds.fai` | 🛠 finish step 3 | `samtools faidx` 可读；PS2/GetSequence 可用 |
| A3 | BLAST 库：整基因组（多卷）/ 7 条染色体拆分 / CDS / PEP + 软链 | `${BLASTDB}/<DS>.genome*`、`.genome_Chr*`、`.add_Description.{cds,pep}*` | 🛠 G3 steps 1–7.5 | `blastdbcmd -info` 序列数/总长 = FASTA |
| A4 | 聚合 BLAST 别名 | `all_genomes.nal`、`all_gene.nal`、`all_protein.pal`、**`all_genes.nal`、`all_proteins.pal`**、`all_genomes_type.txt` | 🛠 finish step 5 | 别名含 `<DS>.*`；`/api/sequence/by-interval`、`batch`、`by-gene` |
| A5 | GetSequence 文档示例表 | `/var/www/html/doc/getsequence_search.txt` | 🛠 finish step 5b（`update_getsequence_search.py`） | 外网 `/doc/getsequence_search.txt` 有行 |
| A6 | BLAST 库层级覆盖（条件项） | `app/services/data/blast_db_levels.json`（生成脚本 `scripts/make_level_overrides.py`） | ✍ 仅当平台把 chromosome-level 误判成 scaffold 时补 | `/api/blast/databases` 中 assembly_level 正确 |
| A7 | BLAST↔JBrowse 命中映射（生成文件，gitignored） | `app/services/data/blast_jbrowse_map.json` | 🛠 finish step 9（`build_blast_jbrowse_map.py`） | `--check` rc=0；`/api/jbrowse/coverage` ok=true |

## 2. MySQL（B 组）

| # | 触点 | 位置 | 谁更新 | 验证 |
|---|---|---|---|---|
| B1 | 基因功能表 | `Genefuncdb.Genefunc_<DS>_table`（行数=基因数） | 🛠 G3 step 7.2.1（register） | `SELECT COUNT(*)`；`/api/genes/functions/tables` |
| B2 | 基因功能注册表 | `Genefuncdb.Genefunc_registry`（`display_name`=友好名、`example_chr_id/example_species_chr_id/example_cds_id/example_protein_id`、`Group/Polyploidy/chromosome_level/Doi/title/display_order/visible`） | 🛠 finish step 4 | `/api/genes/functions/registry`；GetSequence 面板/示例 |
| B3 | 基因组注册表 | `wheatomics_db.genome_registry`（由平台事实派生：blast 库/JBrowse/Genefunc/getfasta、synteny、orthofinder、cite、策展表；`display_name/subgenomes/chromosome_count/genome_size/te_content/doi/...`；flags：`web_blast_group/getfasta_member/primerserver_fai/gene_function_ui/visible/display_order`） | 🛠 finish steps 6–8 + `rebuild_genome_registry.py`；**新类群/新材料元数据需在脚本 overrides/SUB 中加**（✍） | `/api/genomes/{DS}` 字段齐全；`/api/genomes/stats`；`chromosome_count=染色体数`（不是 scaffold 数） |
| B4 | JBrowse 元数据 | `jbrowse_meta.jbrowse_datasets` / `jbrowse_tracks` | 🛠 G3 step 10 / finish step 6（`import_jbrowse_meta.py`） | `/api/jbrowse/datasets` 含 `<DS>` 且 track 数正确 |
| B5 | 可选模块数据表（默认不需要） | `synteny_mysql.genome_info`、`orthofinder_n.genome_type`、`VariantHub`、表达/eQTL/共表达等 | ✍ 各自数据管线（见 §7） | 各自 API 面板 |

## 3. JBrowse（C 组）

| # | 触点 | 位置 | 谁更新 | 验证 |
|---|---|---|---|---|
| C1 | JBrowse 实例数据（refSeqs、trackList、`all_gene`/`DNA` 轨道、gene 名字索引） | `/var/www/html/jbrowse-1.12.3-release/<DS>/` | 🛠 G3 steps 6a/6b/7.6/8 | `seq/refSeqs.json` 序列数 = FASTA；`/api/jbrowse/datasets/{DS}/trackList` |
| C2 | JBrowse V2 网关页（卡片/hero/命名数/分组数/新分区） | 线上 `/var/www/html/jbrowse.html`；仓库源 `app/static/docpages/jbrowse.html` | 🛠 finish step 1 + **⚙️ 回写仓库并提交**（`deploy_doc_pages.py --check`） | 页面 hero/named/groups 计数；`?data=<DS>` 卡片存在；新分区标题/计数 |
| C3 | JBrowse API | `/api/jbrowse/datasets`、`/{DS}/trackList`、`/refseqs`、`/coverage` | 🤖（读 DB/磁盘） | 上述 API 200；`/api/jbrowse/coverage` ok |

## 4. GetSequence / getfasta（D 组）

| # | 触点 | 位置 | 谁更新 | 验证 |
|---|---|---|---|---|
| D1 | 支持基因组面板（chips）与示例区间/基因 | `/api/genes/functions/registry`（来自 B2） | 🛠 finish step 4 | 页面 `/getfasta/` 面板出现友好名 + 示例 |
| D2 | 页面 by-gene/batch 实际查询的**复数**别名 | `all_genes.nal`、`all_proteins.pal` | 🛠 finish step 5 + `rebuild_getfasta_aggregates.py --apply` | `batch?database=all_genes`、`by-gene?protein_db=all_proteins` 命中 |
| D3 | 示例文档表 | `getsequence_search.txt`（见 A5） | 🛠 finish step 5b | 外网文件有行 |
| D4 | 区间取序列 | `all_genomes.nal` + per-chrom 解析 | 🛠 finish step 5 | `/api/sequence/by-interval?...&database=all_genomes` |
| ⚠️ | **别名 200 成员上限** | `all_genes.nal`/`all_gene.nal` 已在 200 | 加新基因组前先清理（`rebuild_getfasta_aggregates.py` 已排除 PacBio*/Tae_TF/fangenome）；finish 用**前插**并告警 | `blastdbcmd -db all_genes -entry_batch -` 测尾部基因不 `Skipped` |
| ⚠️ | 平台既有限制 | `blastdbcmd -entry` 不支持**核酸别名库** | —（所有基因组一致） | GetSequence 单基因 CDS 走 `/api/sequence/batch` |

## 5. Web BLAST / PrimerServer2 / CAPS（E 组）

| # | 触点 | 位置 | 谁更新 | 验证 |
|---|---|---|---|---|
| E1 | BLAST 库清单分类 | `/api/blast/databases`：优先读 `genome_registry.ploidy`（🤖）；无 registry 时用 `app/api/routers/blast.py` 的 `DB_CLASSIFICATION` 关键词兜底 | 新物种名不命中既有关键词时 ✍ 加关键词（改代码→push→重启）；新类群分类需加 category | 新库出现在正确 category（如 `other_triticeae`） |
| E2 | Web BLAST 页面 | `app/static/blast2/index.html` / docroot `blast/blast.html`（SPA 动态取库） | 🤖（一般无需改；默认预设只有中麦系列，不影响新基因组可选） | 页面可选到新库并能搜索 |
| E3 | PrimerServer2 | 数据来源 = BLAST 库 + `.fai`；示例来自 Genefunc_registry | 🛠（finish step 3/4 后 🧊） | `/api/PrimerServer2/databases` genome/gene 组含新库；`/sequences` 条数对 |
| E4 | CAPS/dCAPS/KASP | 取库来自 PrimerServer2；静态页 `app/static/caps/index.html` 的 `groups` 数组只影响分组显示 | 🤖（取库）；**新 ploidy 代码才需 ✍ 加 group** | `/api/caps/design` 坐标模式实弹；页面有该基因组 |

## 6. 前端静态页 / 文档 / 证书（F 组）

| # | 触点 | 位置 | 谁更新 | 验证 |
|---|---|---|---|---|
| F1 | 分类分组数组（新 **ploidy 代码** 才需要） | `app/static/interval/index.html`、`PfamSearch/index.html`、`caps/index.html` 的 `groups: [...]` | ✍ 手工加代码到对应 category（如 diploid 数组） | 页面分组下出现该基因组 |
| F1b | 已有 ploidy 代码（如再加一个 MM） | 同上 | 🤖 无需改 | — |
| F2 | GetSequence 示例链接（可选） | `app/static/getfasta/index.html` 的 example links | ✍ 可选补充 | — |
| F3 | GeneHub / 基因检索 | 基因详情仅 CS（`GenePageIWGSCv1_table`，平台既有设计）；基因功能检索走 `Genefunc_registry`/表自动 | 🤖（基础） | 功能检索可按表查 |
| F4 | 首页/新闻/引用 | docroot `/V2.0/index.html`（计数动态）、`/V2.0/news.json`、`/cite.html`（非 repo 管理） | ✍ 可选（cite/news 手工补） | 页面显示 |
| F5 | 下载页 | `app/static/docpages/download.html` | 🤖 一般无需改（不逐基因组列） | — |

## 7. 可选模块（不在基础四件套上线范围，需各自数据管线）

以下模块**只有拿到对应数据才需要更新**；否则新基因组只进基础模块，这些面板不出现新条目是正常的：

- 表达/共表达/eQTL/PPI/PTM/regulatory/scRNA/translatome：需表达矩阵、互作表等（`expression`/`eqtl`/`coexpression`/`ppi`/`ptm`/`regulatory*`/`scrna*`/`translatome` 路由）
- VariantHub：需 VCF 数据集注册（CAPS 的 VCF 模式依赖它）
- SyntenyView / OrthoFinder：需 `synteny_mysql.genome_info` / `orthofinder_n.genome_type` 条目
- GO/KEGG 富集：依赖基因功能注释列（Genefunc 表）+ GO/KEGG 映射
- Triticeae homolog（`triticeae` 路由）、comparative（`blast_extra`）：需同源表数据
- KnownGene（人工策展表）：与新基因组无关，除非新基因组作为 reference genome 被引用

## 8. 运维 / 缓存 / 发布（G 组）

| # | 动作 | 说明 |
|---|---|---|
| G1 | **重启 API**：`sudo systemctl restart wheatomics-api` | 建 BLAST 库后 `/api/blast/databases` 磁盘缓存 TTL 1h；`/api/sequence/chromosomes` 进程缓存 TTL 1h；PrimerServer2 库清单继承 BLAST 缓存。worker 冷启动约 2–3 分钟 |
| G2 | 缓存机制速查 | `blast.py:_DB_LIST_CACHE`(1h)、`sequence.py:_CHROM_CACHE`(1h)、`_DB_LEVELS_CACHE`(mtime)、`jbrowse.py:_REFSEQ_CACHE`(mtime)；Genefunc_registry/genome_registry 无缓存，改库即生效 |
| G3 | docroot ↔ 仓库 | finish 改的是 docroot `jbrowse.html` → 收尾后回写 `app/static/docpages/jbrowse.html`，`python3 scripts/deploy_doc_pages.py --check` 必须无 drift |
| G4 | 页面静态文件 | `app/static/**` 由 FastAPI StaticFiles 直接从仓库目录读，git pull 即生效（无需重启）；浏览器缓存需刷新 |
| G5 | 分类代码改动 | 改 `app/api/routers/blast.py` 后需 git push（github+gitee）→ 服务器 pull → **重启 API** |
| G6 | 脚本资产 | 仓库 `scripts/` → 服务器 `/var/www/data/masw_data/_prep/`（`md5sum` 对齐），SOP 副本到技能目录 |
| G7 | 验收 | `accept_aegilops4_onboarding.py`（102 项；覆盖 §1–§6 的自动检查） |

## 9. 推荐执行顺序（可勾选清单）

**G0 命名门禁**
- [ ] 数据目录放好四件套 + `name_plan.json`（`finish_genome_integration.sh --check-name --write-plan --confirm`）
- [ ] 如为新 **ploidy/类群**：确认 `SUB`/`DB_CLASSIFICATION`/静态页 groups 数组需要改的地方（✍）

**G1/A2 归一化**（🛠 一条命令）
- [ ] `bash prepare_aegilops4_dataset.sh <PLOIDY> <MYTAG> <ZENODO前缀>`
- [ ] `check_genome_files.py` rc=0；ID 规则 `renumber_gff_ids.py --check`

**G3 流水线**（🛠 25–45 min/个）
- [ ] `add_wheat_genome.sh <MYTAG> <DIR> <PLOIDY>` → `[SUCCESS]`
- [ ] 抽检：BLAST 库序列数/总长、`Genefunc_<DS>_table` 行数、JBrowse refSeqs、registry 行已建

**G4 收尾**（🛠 1–3 min/个；建议 API 先重启一次让 BLAST 库清单可见）
- [ ] `finish_genome_integration.sh <PLOIDY> <MYTAG> <DOI>`，rc=0 / 无 FAIL
- [ ] 如果 `all_genes` 等别名 >200 → 先 `rebuild_getfasta_aggregates.py --apply` 压回 ≤200
- [ ] 回写 `jbrowse.html` 源 + `deploy_doc_pages.py --check`
- [ ] 补 cite.html / news.json（可选）
- [ ] 重启 API（刷新 GetSequence/PS2 缓存）

**G5 验收**（🛠）
- [ ] `accept_aegilops4_onboarding.py` 全 PASS（含 GetSequence A17–A19）
- [ ] `build_blast_jbrowse_map.py --check`；`/api/jbrowse/coverage` ok
- [ ] registry 别名行复核（rebuild 可能自动多登记历史别名：`visible=0` 处理）

## 10. 本次 4 基因组实战触点核对（哪些自动/哪些人工）

| 组 | 自动完成 | 本次人工/代码修补 |
|---|---|---|
| A 数据/索引 | A1–A5、A7 全自动 | A6 未触发（层级正确） |
| B MySQL | B1、B4 自动；B3 由 facts 派生 | B2 `display_name` 改友好名；B3 overrides 加 `display_name/subgenomes/_hard:chromosome_count` |
| C JBrowse | C1/C3 自动 | C2 docroot→repo 回写；CC/NN 分区标题格式修正 |
| D GetSequence | D4 自动 | **D1–D3 本次发现未同步，已修 + 脚本补步骤**；200 成员上限已处理 |
| E BLAST/PS2/CAPS | E1–E4 基本自动 | E1 为 Ae. markgrafii/uniaristata 补了关键词 |
| F 前端/文档 | F1b/F3/F5 无需改动 | F1 的 MM/CC/NN 早已在数组（若新 ploidy 需加）；F4 cite/news 手工补 |
| G 运维 | — | API 重启 ×2、页面回写、脚本同步、102 项验收 |

## 11. 相关脚本/文档索引

| 资产 | 用途 |
|---|---|
| `scripts/prepare_aegilops4_dataset.sh` | A2 一键归一化 |
| `scripts/normalize_diploid.py` / `renumber_gff_ids.py` | 归一化 / ID 规范 |
| `add_wheat_genome.sh`（服务器数据目录） | G3 流水线 |
| `scripts/finish_genome_integration.sh` | G4 收尾（含 GetSequence step 5/5b） |
| `scripts/rebuild_genome_registry.py` | B3 registry 重建（SUB/overrides/IGNORED） |
| `scripts/rebuild_getfasta_aggregates.py` / `update_getsequence_search.py` | D2/D3 GetSequence 同步 |
| `scripts/import_jbrowse_meta.py` / `build_blast_jbrowse_map.py` | B4 / A7 |
| `scripts/make_level_overrides.py` | A6（条件） |
| `scripts/accept_aegilops4_onboarding.py` | G5 102 项验收 |
| `docs/workflow/wheatomics-new-genome-sop.md` | 完整 SOP（含坑与命令） |
| `docs/plans/aegilops4_2026-11/G3_G4_G5_REPORT.md` | 本次实战逐条记录 |
