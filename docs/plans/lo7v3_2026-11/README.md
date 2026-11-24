# 2026-11-25 · 黑麦 Lo7_V3 上线记录（RR_rye_Lo7_v3）

> 论文：Chen, E. et al. *Unveiling centromeric retrotransposon dynamics through a high-quality
> rye genome assembly*. Nature Communications (2026). [10.1038/s41467-026-76753-4](https://doi.org/10.1038/s41467-026-76753-4)
> 组装：**GCA_965641915.1**（`lpSecCere.Lo7.IPK.v3`，ENA PRJEB91463）
> 结论：**已上线**，JBrowse / BLAST / Genefunc / GetSequence / PrimerServer2 / CAPS 全部可用。

## 1. 流水线时间线（2026-11-24 → 11-25）

| 阶段 | 时间 | 结果 |
|---|---|---|
| 数据下载 | 23:03–23:18 | ENA 组装 6.4 GB + IPK e!DAL 注释（all/high/low GFF3） |
| G0 命名/DOI 门禁 | 23:08 | `[OK]`（DOI Crossref 校验通过；`RR_Lo7_v3` 分类不中 → 改名 `RR_rye_Lo7_v3`） |
| G1 归一化 | 23:09–23:20 | FASTA 242 条/6,702,647,067 bp；GFF 75,850 gene / 84,086 mRNA；gffread CDS/PEP 84,086 条 |
| G2 质检 | 23:20 | `所有文件均通过检查！` |
| G3 流水线 | 23:21–00:12 | `[SUCCESS]`（EggNOG + Pfam + CS02G miniprot + JBrowse） |
| G4 收尾 | 00:12–00:13 | 0 FAIL（card/alias/fai/registry/映射/验收全绿） |
| API 重启 + G5 | 00:14–00:20 | 全绿；BLAST 601 bp 探针 100% 命中 Chr3R 预期坐标 |

## 2. 数据来源

- 组装 FASTA：**ENA 流式** `browser/api/fasta/GCA_965641915?download=false`
  （NCBI FTP 单线程仅 ~0.6 MB/s；ENA 7–12 MB/s。ENA 头是 `ENA|OZ284382|OZ284382.1`，
  需按 `assembly_report` 的 GenBank-Accn 映射）
- assembly_report / md5：NCBI FTP `GCA_965641915.1_lpSecCere.Lo7.IPK.v3/`（源 fasta md5 `87177b78918660d6d88951317018dc7c`）
- 注释：**IPK e!DAL** [10.5447/ipk/2026/5](https://doi.org/10.5447/ipk/2026/5)
  `SECALE.CEREALE.Lo7.pgsb.r2.Feb2025.gff3`（all / high / low）
  （Zenodo 10.5281/zenodo.15801361 在本服务器网络被 403 "unusual traffic" 拦截）

## 3. 归一化与命名

| 步骤 | 命令/规则 | 结果 |
|---|---|---|
| FASTA | `normalize_diploid.py fasta` + assembly_report | `Chr1R…Chr7R` + `ChrUn_contig_corrected_v3_*`（235 条），映射率 100% |
| GFF seqid | `normalize_diploid.py gff3 --keep-author-ids` | 84 个 seqid 全部 `Chr*`；`##sequence-region` 84 条同步改写 |
| ID 重编号 | `renumber_gff_ids.py --id-prefix "SceLo7v3." --step 10 --digits 6` | `SceLo7v3.1RG000010` / `….1`；原 ID 留 `original_id` + idmap |
| CDS/PEP | `gffread -E` | 84,086 条，pep 无 `.`/`*` |

> Chr2R–Chr6R 单染色体基因数 >9,999，**6 位序号必须配 `--step 10`**（默认 step 100 直接报容量不足）。

## 4. 平台产物

| 模块 | 对象 | 规模 |
|---|---|---|
| BLAST genome | `RR_rye_Lo7_v3.genome` | 242 seqs / 6,702,647,067 bp |
| BLAST 染色体库 | `RR_rye_Lo7_v3.genome_Chr1R…Chr7R` | 7 个 |
| BLAST CDS / PEP | `RR_rye_Lo7_v3.add_Description.{cds,pep}` | 84,086 / 84,086 |
| JBrowse | `RR_rye_Lo7_v3`（#group-rr，track `all_gene`） | refSeqs 242 |
| 基因表 | `Genefunc_RR_rye_Lo7_v3_table` | 84,086 行；Description 覆盖 57,549（68%），Domain 84,086 |
| PrimerServer2 | `RR_rye_Lo7_v3.genome`（242 seqids） | ✓ |
| getfasta | `all_genomes` 成员，`Chr1R_rye_Lo7_v3` 可查 | ✓ |
| registry | `chromosome_count=7`、`gene_count=75850`、`genome_size=6702647067`、DOI/标题/期刊/年份齐 | ✓ |

## 5. 踩到的坑（已修进脚本）

1. **ENA 头无法映射**：`ENA|OZ284382|OZ284382.1` 被当成完整 ID →
   `normalize_diploid.py` 增加 ENA 头解析 + 版本号兜底。
2. **报告里是小写 `chr1R`**：`chrom_name()` 直接拼前缀得到 `Chrchr1R` →
   改为大小写不敏感剥离 `chr` 再拼 `Chr`。
3. **`##sequence-region` 未改写**：`normalize_diploid.py gff3` 只改特征行 → 本次用映射表补写 84 条
   （后续应在脚本内处理）。
4. **重编号容量**：单染色体 >9,999 基因时 `--step 100` 报错 → 用 `--step 10`。
5. **rebuild 覆盖修正后的 DOI**：G3 Step 10 / G4 第 6-8 步都会跑
   `rebuild_genome_registry.py`。生产仓当时还是旧版（卡片解析失效 + 策展表覆盖），
   把 2026-11-24 修好的 9 行 DOI 又写回了错值 —— 已在收尾后重新应用修正；
   永久解决需把 `46cce9e` 推到生产（见 §7）。
6. **`chromosome_count` 被写成 242**：rebuild 用 `.fai` 序列数 → 已在 overrides 加
   `"_hard": ["chromosome_count"]` 并手工改回 7。

## 6. 验收记录

- `/api/genomes/RR_rye_Lo7_v3`：字段齐全（species/ploidy/subgenomes/accession/level/size/cc/gene/doi/journal/year/annotation_status），`visible=1`
- `/api/genomes/stats`：352 → **353**，RR 2 → **3**
- BLAST 冒烟：601 bp 探针（Chr3R:2,000,000-2,000,600）→ 100% identity 命中预期坐标
- `/api/jbrowse/datasets` 含新数据集；`jbrowse.html` 卡片 + hero 244 / named 237 / #group-rr 4
- `/api/sequence/chromosomes?pattern=rye_Lo7_v3` → 7 条染色体；`by-interval` / `by-gene` 正常
- `/api/genes/functions/interval`（新表）返回基因；`/api/genes/functions/registry` 含新表
- `/api/PrimerServer2/databases` + `/databases/RR_rye_Lo7_v3.genome/sequences` 200
- 回归：`AABBDD_Chinese_Spring2.1.genome`、`RR_rye_Lo7.genome`、`RR_rye_weining.genome` 仍在，旧 rye_Lo7 基因表可查
- DOI：`verify_genome_doi.py --dataset RR_rye_Lo7_v3` → ok
- 新闻：`/V2.0/news.json` 新增 2026-11-25 条目（38 条）

## 7. 待办

- [ ] 把 `46cce9e`（DOI 修复 + 门禁）、`7988e1e`（本次上线代码/页面）推到 github + gitee，
      生产 `git fetch && git merge --ff-only` —— 否则下次上线 Step 10 仍会用旧 rebuild 脚本重写错 DOI
- [ ] 可选：HC/LC 两条 JBrowse 轨道（`SECALE.CEREALE.Lo7.pgsb.r2.Feb2025.{high,low}.gff3` 已下载到
      `downloads/`），可仿 rye_Lo7 的 HC_gene/LC_gene 轨道补建
- [ ] 可选：TE 轨道（IPK/Zenodo 的 EDTA TEanno gff3，1.46 GB）
- [ ] `provenance.txt` 已写入数据目录；如要做站点"Data source"展示可从 registry `source_url` 取
