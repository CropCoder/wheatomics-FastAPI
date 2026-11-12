# WheatOmics 新基因组上线流程（v2，2026-11-11）

这个目录是「新基因组上线 SOP」的**仓库留档**（源），配套脚本也在仓库里，便于 code review / 版本追踪；生产上实际使用的脚本副本安装在服务器与 lab-server 技能目录（见下）。

## 文件

| 文件 | 作用 | 生产安装位置 |
|---|---|---|
| `new-genome-update-checkpoints.md` | **触点总表**：新基因组上线需要更新的全部地方（A 数据/索引、B MySQL、C JBrowse、D GetSequence、E BLAST/PS2/CAPS、F 前端/文档、G 运维缓存）+ 顺序清单 + 本次实战核对 | 参考（无需安装） |
| `wheatomics-new-genome-sop.md` | **SOP v2**：五阶段 G0–G5、归一化规则、收尾/验收清单、已知坑、案例 | `~/.agents/skills/lab-server/references/wheatomics-new-genome-sop.md`（旧版备份 `.bak-<日期>`） |
| `../../scripts/finish_genome_integration.sh` | 收尾脚本 v2：识别 JBrowse V2.0 / wheatBLAST SPA、二倍体 GROUP、卡片/计数同步、API 断言 | `~/.agents/skills/lab-server/scripts/` 与服务器 `/var/www/data/masw_data/_prep/` |
| `../../scripts/normalize_diploid.py` | 四件套归一化工具（`fasta/gff3/pep/check` 子命令），支持任意 `[1-7][A-Z]` 染色体与 NCBI assembly_report 映射 | 服务器 `/var/www/data/masw_data/_prep/` |
| `../../scripts/renumber_gff_ids.py` | gene/mRNA ID 平台风格重编号（每染色体按坐标 100 步；`--check` 可作闸门） | 服务器 `_prep/` |
| `../../scripts/prepare_aegilops4_dataset.sh` | A2 一键脚本（FASTA/GFF 归一化 → 重编号 → gffread → pep 清洗 → 平台质检，幂等） | 服务器 `_prep/` |
| `../../scripts/rebuild_getfasta_aggregates.py` | GetSequence 聚合 BLAST 别名重建（all_genomes/all_genes/all_proteins；含 200 成员上限处理） | 服务器 `_prep/`（或生产 repo） |
| `../../scripts/update_getsequence_search.py` | 向 `getsequence_search.txt` 增/改本基因组示例行（页面链接文档） | 服务器 `_prep/`（或生产 repo） |
| `../../scripts/accept_aegilops4_onboarding.py` | G5 逐条验收（90 项：计数/registry/BLAST/JBrowse/getfasta/PS2/Genefunc/实弹 BLAST/前端/映射/回归） | 服务器 `_prep/` |
| `../../scripts/fetch_aegilops4_data.sh` | 4 个二倍体 Aegilops 数据下载（NCBI + Zenodo，断点续传/md5/互斥锁） | 服务器 `_prep/` |

## 安装（部署到生产侧脚本目录）

```bash
# 1) lab-server 技能目录（本机可写时）
cp docs/workflow/wheatomics-new-genome-sop.md \
   ~/.agents/skills/lab-server/references/wheatomics-new-genome-sop.md
cp scripts/finish_genome_integration.sh \
   ~/.agents/skills/lab-server/scripts/finish_genome_integration.sh
chmod +x ~/.agents/skills/lab-server/scripts/finish_genome_integration.sh

# 2) 生产服务器（经 lab-server 隧道）
bash ~/.agents/skills/lab-server/scripts/wheatomics.sh tunnel   # 另开一个终端保持隧道
scp -P 2222 scripts/finish_genome_integration.sh scripts/normalize_diploid.py \
    scripts/renumber_gff_ids.py scripts/prepare_aegilops4_dataset.sh \
    scripts/fetch_aegilops4_data.sh scripts/accept_aegilops4_onboarding.py \
    fei@127.0.0.1:/var/www/data/masw_data/_prep/
# 校验两边一致
md5sum scripts/finish_genome_integration.sh scripts/normalize_diploid.py
```

## 与代码仓库的关系

- 本目录 SOP 与 `scripts/` 下的两个脚本属于**流程资产**，改动走正常 git 流程（github + gitee 双推，生产 `git fetch && git merge --ff-only`）；
- 页面类改动（JBrowse 卡片页 `app/static/docpages/jbrowse.html`、静态 SPA 分类数组）在代码仓库内，按 SOP §10 部署；
- 上游原始 SOP（v1，2026-10-23）仍在 skills 目录，v2 安装后请保留 `.bak` 以便对比。

## 背景

2026-11-11 对流程做了一次全面审阅（见 `docs/plans/aegilops4_2026-11/`），发现 v1 有 9 处与生产现状不一致/不支撑二倍体的问题（脚本版本漂移、归一化只认 A/B/R、收尾脚本按旧页面写、GROUP/SUB/分类关键词缺新倍性、跨物种 ID 重复、pep `*` 终止符、静态页数组缺 CC/NN、`web_blast_group` 旧判定）。v2 已全部修复，修复记录见 SOP §12。
