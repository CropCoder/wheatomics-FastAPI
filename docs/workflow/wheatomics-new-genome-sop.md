# WheatOmics 新基因组上线 SOP（v2，2026-11-11 更新）

> 配套实现报告（2026-11-11）：`docs/plans/aegilops4_2026-11/PHASE0_CORE.md`（代码修复）、`PHASE0_NORMALIZE.md`（归一化脚本实测）、`PHASE0_FINISH.md`（收尾脚本适配实测）、主计划 `Aegilops4_diploid_genome_update_plan.md`。

> 目标：把一个新基因组完整接入 wheatomics.sdau.edu.cn —— **BLAST（核酸整基因组/染色体拆分/CDS/蛋白）→ MySQL Genefunc → 中国春 02G 同源映射 → JBrowse → getfasta → Web BLAST → PrimerServer2 → 前端卡片/分类 → genome_registry**。
>
> 本版相对 v1（2026-10-23）的变更（每次更新请改这里）：
> 1. **适配现行前端**：JBrowse 已是 **V2.0**（`app/static/docpages/jbrowse.html`，`.asm-group`/`.asm-card`/`.asm-grid`）；Web BLAST 已是 **wheatBLAST SPA**（`app/static/blast2/index.html`，库清单动态来自 `/api/blast/databases`，无手写 `<optgroup>`）。v1 的旧页面步骤已全部失效。
> 2. **收尾脚本重写**：新版 `finish_genome_integration.sh`（仓库 `scripts/`，本版配套）自动识别 V2/SPA 页面；`--check-name` 不再被旧页面卡死。
> 3. **支持任意倍性**，包括二倍体单字母双写（`AA/DD/MM/CC/UU/NN/SS/TT/VV/EE/RR/II/PP/GG`）：`SUB` 映射、`GROUP` 推导、静态页分类数组、JBrowse 分区全部配套。
> 4. **新增归一化工具**：仓库 `scripts/normalize_diploid.py`（`fasta/gff3/check/pep` 四个子命令），覆盖「NCBI GenBank 登录号 → Chr 名」「任意 `[1-7][A-Z]` 染色体」「跨物种重复 mRNA ID 加前缀」「`.pN` → `.数字`」「pep 终止符 `.`/`*` 清理」。
> 5. 记录 v1 遗留的 6 个已修复缺口（见 §12「v1→v2 修复记录」）。
> 6. 生产 `add_wheat_genome.sh` 版本更新（md5 `70fb9ff21ed11417399f16fb489b1ad3`，1034 行），以本文件 §7 为准（v1 记的 `208f0653…` 已过期）。
>
> 服务器访问：`bash ~/.agents/skills/lab-server/scripts/wheatomics.sh cmd '<命令>'`（自带跳板隧道）；大文件用 `tunnel` + `scp -P 2222`。
> 本文件安装位置：`~/.agents/skills/lab-server/references/wheatomics-new-genome-sop.md`（仓库留档 `docs/workflow/wheatomics-new-genome-sop.md`，安装时旧版备份为 `.bak-<日期>`）。

---

## 0. 前置条件（一次性 / 每次核对）

| 项 | 值 / 命令 |
|---|---|
| 数据根目录 | `/var/www/data/masw_data`（116T，2026-11-11 剩 ~30T） |
| 流水线脚本 | `/var/www/data/masw_data/add_wheat_genome.sh`（**md5 `70fb9ff21ed11417399f16fb489b1ad3`**，2026-11 版，1034 行，含命名门禁） |
| 收尾脚本 | 仓库 `scripts/finish_genome_integration.sh`（v2，含 GetSequence 同步 step 5b；**md5 `2bfcb1e2c59fcd447c4eb503f4410009`**）→ 安装到 `~/.agents/skills/lab-server/scripts/` 与服务器 `/var/www/data/masw_data/_prep/`（`md5sum` 对齐两边） |
| 归一化脚本 | 仓库 `scripts/normalize_diploid.py`（`fasta/gff3/pep/check`；**md5 `e2a13d8b64f6fb65ccd0be222e53e3ea`**）→ 服务器 `_prep/normalize_diploid.py` |
| 重编号脚本 | 仓库 `scripts/renumber_gff_ids.py`（每染色体 100 步平台 ID；**md5 `90b5d84e2fad765d70d7a723eabde00d`**）→ 服务器 `_prep/` |
| A2 一键脚本 | 仓库 `scripts/prepare_aegilops4_dataset.sh`（**md5 `04a905cc2a85828c3bdfc7f499d0f743`**）→ 服务器 `_prep/` |
| 数据下载脚本 | 仓库 `scripts/fetch_aegilops4_data.sh`（**md5 `7c0985d181ea430be3fff9330e859a72`**）→ 服务器 `_prep/` |
| 批量/验收脚本 | `scripts/pipeline_aegilops4_all.sh`、`scripts/finish_aegilops4_all.sh`、`scripts/accept_aegilops4_onboarding.py`（G5 逐条核对，含 GetSequence）→ 服务器 `_prep/` |
| GetSequence 聚合/文档 | `scripts/rebuild_getfasta_aggregates.py`（重建 all_genomes/all_genes/all_proteins 等别名 + 文档 Library 列）、`scripts/update_getsequence_search.py`（向 `getsequence_search.txt` 增/改本基因组示例行）→ 服务器 `_prep/` 或直接从生产 repo 运行 |
| 质检脚本 | `/var/www/html/Script/check_genome_files.py`（md5 `d774445172714d0d6b9127d4a21cc2a0`） |
| conda | `/home/fei/mambaforge/bin`（**跑流水线必须显式加 PATH**） |
| MySQL DDL 配置 | `/etc/wheatomics/db_ddl.env`（640 root:www-data；`fei` 需在 `www-data` 组） |
| gffread | `/home/fei/mambaforge/envs/new_env/bin/gffread`（0.12.9） |
| samtools / BLAST+ | `/usr/bin/samtools`；`/var/www/html/blast/blast+/bin/`（2.12.0） |
| JBrowse | `/var/www/html/jbrowse-1.12.3-release`（1.12.3）+ `jbrowse_meta` 库 |
| 服务 | `wheatomics-api`（systemd，改 Python/加库后重启，60–90 s 不可用）、`wheatomics-blastd` |
| API 端口 | `http://127.0.0.1:8000`（生产经 Apache/HTTPS 代理） |
| 仓库部署链 | 本地 commit → **github + gitee 双推** → 生产 `git fetch origin && git merge --ff-only` → `sudo systemctl restart wheatomics-api` |

**命名约定**：数据集 / BLAST 库 / JBrowse 数据集 / MySQL 表 = `${PLOIDY}_${MYTAG}`。
- `PLOIDY`：倍性代码，例 `AABBDD`、`AABB`、`AABBRR`、`DD`、`MM`、`CC`、`UU`、`NN`；二倍体 = 单字母双写。
- `MYTAG`：材料身份（物种简写 + 登录号），**只允许字母/数字/下划线**（`-` 会让 MySQL 表名报错、`.` 会被流水线规整）。
- 序列级命名：染色体 `Chr1A`、`Chr1M`…；未定位序列 `ChrUn_<原名>`；流水线 Step 1 再给染色体头加 `_${MYTAG}` 后缀（`ChrUn_*` 不加）。

---

## 1. 流程总览（五阶段 + 闸门）

```
G0 命名门禁 ──► G1 输入四件套 ──► G2 质检 ──► G3 流水线(10步) ──► G4 收尾(10项) ──► G5 验收
   --check-name     归一化+生成        check_genome_files.py   add_wheat_genome.sh   finish_genome_integration.sh   API/页面/回归
   name_plan.json   .fa/.gff3/.cds/.pep                        [SUCCESS]             卡片/registry/映射/重启
```

| 闸门 | 内容 | 通过标准 | 产物 |
|---|---|---|---|
| **G0** | `finish_genome_integration.sh <PLOIDY> <MYTAG> <DOI> --check-name` | 材料身份齐、`SUB[PLOIDY]` 有映射、3 个库名分类非 `other`、SPA/V2 页面下无 BLOCK | `<data_dir>/name_plan.json` |
| **G1** | 四件套归一化（§5） | `.fa` 头全 `Chr`；`.gff3` 第 1 列全 `Chr`、mRNA ID 全 `.数字`；`.cds/.pep` ID 全 `.数字`、pep 无 `.`/`*`；四文件齐全 | 归一化后的 4 个文件 + `mapping.tsv` + `provenance.txt` |
| **G2** | `python3 check_genome_files.py <MYTAG>` | **rc=0**「所有文件均通过检查！」 | `.pep.bak`（如有清理） |
| **G3** | `add_wheat_genome.sh <MYTAG> <data_dir> <PLOIDY>` | 日志末 `[SUCCESS] <MYTAG> 全部完成`；BLAST 库/基因表/JBrowse/registry 行齐全 | `.genome`、BLAST 库、`Genefunc_*_table`、JBrowse 目录 |
| **G4** | `finish_genome_integration.sh <PLOIDY> <MYTAG> <DOI> [--label …]` | 自动验收全绿（或仅剩已知 WARN） | 卡片、alias、`.fai`、registry 元数据、BLAST↔JBrowse 映射 |
| **G5** | §10 手工验收 | API/页面/回归全过 | 可上线 |

历史耗时参考：PT（17.9 Gb，215k mRNA）流水线 1h23；二倍体 Aegilops（3.6–4.5 Gb，47–51k mRNA）约 25–45 min/个；4 个顺序跑 2–4 h。

---

## 2. G0 —— 命名/分类预检（**跑任何东西之前必做，强制**）

> 为什么强制：数据集名 `${PLOIDY}_${MYTAG}` 会**绑定** BLAST 库名（`${DS}.genome`、`${DS}.genome_ChrXX`、`${DS}.add_Description.cds|pep`）、JBrowse 数据集目录、MySQL 表名 `Genefunc_${DS}_table`、聚合库 alias、`all_genomes_type.txt`、前端卡片链接。跑完再改名 = 重建 BLAST 库 + 改表名 + 改 HTML + 重导 jbrowse_meta。

### 2.1 材料身份（必填）

新增基因组前必须明确三件事：

| 字段 | 含义 | 例子 |
|---|---|---|
| **材料名** `--cultivar` | 品种/品系/登录材料名 | `Zavitan`、`AK58`、`IPK-AE783` |
| **登录号** `--accession` | 组装/种质登录号 | `GCA_052815735.2`、`GWHHHUI00000000.1`、`PI192501` |
| **文章代号** `--paper-code` | 论文里的组装代号（**补充**，不可单独决定名字） | `WEW_NT` |

命名优先级：**材料名 > 登录号 >（仅两者都缺时才用）文章代号**。`--check-name` 在缺 `--cultivar` 且缺 `--accession` 时 → `[BLOCK]`（rc=3）。

建议数据集名 = `${PLOIDY}_<物种>_<材料/登录号>`，例：
- 四倍体：`AABB_Carthlicum_CWI22960`、`AABB_Wild_emmer_Zavitan`
- 二倍体 Aegilops（2026-11 批次）：`MM_Aegilops_comosa_IPK_AE783`、`CC_Aegilops_markgrafii_EKC105_RL5723`、`UU_Aegilops_umbellulata_IPK_AE740`、`NN_Aegilops_uniaristata_IPK_AE680`
- 表名长度：`Genefunc_${DS}_table` 必须 ≤64 字符（上例 43/51/48/48，安全）。**MYTAG 禁止 `-` 与 `.`**（收尾脚本对表名不做转义）。

### 2.2 命令（4 步）

```bash
# 1) 看归属（不接触线上数据）
bash scripts/finish_genome_integration.sh ${PLOIDY} ${MYTAG} ${DOI} --check-name \
  --cultivar "材料名" --accession "登录号" [--paper-code "文章代号"] \
  [--species "物种学名"] [--group "Other Triticeae"]   # 二倍体/野生近缘种建议显式指定 Group

# 2) 人工确认后落盘（流水线入口强校验）
bash scripts/finish_genome_integration.sh ${PLOIDY} ${MYTAG} ${DOI} --check-name --write-plan --confirm \
  --cultivar "…" --accession "…" --species "…" --group "Other Triticeae"
#   → 生成 <data_dir>/name_plan.json

# 3) 流水线（§7）
# 4) 收尾（§8）
```

### 2.3 判定标准（全部满足才能开跑）

0. 材料身份齐备（`--cultivar` 或 `--accession` 至少一个）；
1. `scripts/rebuild_genome_registry.py` 的 `SUB` 有 `PLOIDY` 映射（否则 `genome_registry.subgenomes` 空、G0 BLOCK）；
2. 3 个库名（`.genome`/`.add_Description.cds`/`.add_Description.pep`）经 `app/api/routers/blast.py` 的 `DB_CLASSIFICATION` 分类**都不是** `other`；
3. 前端归属明确：BLAST 分类（新版 SPA 自动按分类渲染，无需手改）+ JBrowse 分区（V2 页面 `id="group-<ploidy 小写>"`，不存在则新建）；
4. `Genefunc_registry.Group` 与 `Polyploidy` 值确定（见 §4）。

> **v2 行为**：`--check-name` 的 step3/step4 已适配现行页面——BLAST 页面检测到 SPA 时跳过 optgroup 断言；JBrowse 解析 `id="group-…"`，缺失只 WARN+建议新建（除非 `--require-section`）。v1 时代「任何基因组都被 step3 BLOCK」的问题已修复。

### 2.4 各模块分类的真实依据（v2）

| 模块 | 依据 | 说明 |
|---|---|---|
| getfasta / BLAST 库分类 | `app/api/routers/blast.py` 的 `DB_CLASSIFICATION`（库名子串）**+ `genome_registry.ploidy`（registry 行存在后优先）** | 运行时两条路径：先查 registry 按 ploidy 归类，再回退关键词 |
| BLAST 分类 → 前端分组 | wheatBLAST SPA 从 `/api/blast/databases.categories` 动态渲染 | **不手改 blast.html** |
| JBrowse 卡片 | `app/static/docpages/jbrowse.html` V2.0（手写 `.asm-card`，按 `id="group-<plody>"` 分区） | 收尾脚本自动插入 + 计数 |
| getfasta chips / 基因功能表列表 | MySQL `Genefuncdb.Genefunc_registry`（`Polyploidy` 分组） | 收尾脚本 upsert |
| IntervalTool / PfamSearch / CAPS 下拉 | 三个静态页内的 `diploid groups` 数组（`app/static/interval|PfamSearch|caps/index.html`） | **新倍性代码要补进数组**，否则落 "Other / Unclassified" |
| genome_registry | `scripts/rebuild_genome_registry.py` 的 `SUB` 映射 | 新倍性代码要补 |
| BLAST↔JBrowse 跳转 | `scripts/build_blast_jbrowse_map.py`（按染色体长度匹配 `.fai` 与 `refSeqs.json`） | 收尾脚本自动重建 |

**当前分类关键词/映射（2026-11 核实）**：`AA/DD` → `diploid_wheat`；`AABBDD` → `hexaploid_wheat`；`AABB/AAGG` → `tetraploid_wheat`；`AABBRR` → `triticale`；`HH` → `barley`；`RR` → `rye`；`Thinopyrum ponticum` → `thinopyrum_ponticum`；**其他非空 ploidy（MM/CC/UU/NN/SS/TT/VV/EE/II/MMUU/DDNN…）→ `other_triticeae`**。若某新倍性不在 `SUB`，先补 `scripts/rebuild_genome_registry.py` 并部署，否则 G0 BLOCK。

---

## 3. 分类/前端归属速查（新增倍性代码时照表）

| 模块 | 新倍性代码要改哪里 |
|---|---|
| `SUB`（registry subgenomes） | `scripts/rebuild_genome_registry.py` 的 `SUB` |
| BLAST 分类关键词（仅门禁/窗口期需要） | `app/api/routers/blast.py` `DB_CLASSIFICATION` 对应分类的 `keywords` |
| Genefunc Group | 收尾脚本 `--group`；野生近缘种用 `Other Triticeae`；小麦系按 `Tetraploid/Hexaploid/…` |
| JBrowse 分区 | 收尾脚本自动：`id="group-<ploidy 小写>"`，不存在则新建；`--section-title/--section-desc/--search-extra` 可定制 |
| 静态页倍性分组数组 | `app/static/interval/index.html`、`app/static/PfamSearch/index.html`、`app/static/caps/index.html` 的 `id='diploid'`（或对应分类）`groups` 数组 |
| Web BLAST 前端 flag | `scripts/rebuild_genome_registry.py` 的 `web_blast_group` 判定（v2 已适配 SPA：有 `blast_genome_db` 即 1） |
| 「按染色体综合库」（可选） | 用 `blastdb_aliastool` 建 alias（`.nal`），新倍性需要时再建 |

---

## 4. G1 —— 输入四件套准备（归一化）

> 在 `/var/www/data/masw_data/${PLOIDY}_${MYTAG}/` 下准备 4 个文件：`${MYTAG}.fa`、`${MYTAG}.gff3`、`${MYTAG}.cds`、`${MYTAG}.pep`。四个都不能缺。

### 4.1 四件套来源

| 文件 | 来源 | 说明 |
|---|---|---|
| `.fa` | 组装方（NCBI/ENA/GWH/作者） | 染色体级或 scaffold 级；**未定位序列全保留** |
| `.gff3` | 作者/数据库注释 | 需含 `gene/mRNA/exon/CDS`；结构注释优先 |
| `.cds` / `.pep` | **由 `.fa` + `.gff3` 用 gffread 生成** | `gffread -E -g ${MYTAG}.fa -x ${MYTAG}.cds -y ${MYTAG}.pep ${MYTAG}.gff3` |

### 4.2 硬性命名规则（G1 闸门会查）

| 文件 | 要求 |
|---|---|
| `.fa` | 每条头以 `Chr` 开头；未定位序列 `ChrUn_*`（原为 contig/scaffold 的先改名） |
| `.gff3` | 第 1 列所有 seqid 以 `Chr` 开头；**mRNA 的 `ID=` 必须以 `.数字` 结尾** |
| `.cds` / `.pep` | 序列 ID（`>` 后第一个空格前）以 `.数字` 结尾；pep 序列行不能含 `.`（也不能含 `*`） |

### 4.3 归一化工具（v2 新增，优先级最高）

```bash
PY=python3   # 服务器用 /usr/bin/python3 即可
$PY scripts/normalize_diploid.py --help           # 看子命令

# ① FASTA：NCBI GenBank 登录号 → Chr*/ChrUn_*（用 assembly_report 的 Sequence-Name↔GenBank-Accn）
$PY scripts/normalize_diploid.py fasta \
  --fasta GCA_xxx_genomic.fna.gz --assembly-report GCA_xxx_assembly_report.txt \
  --out ${MYTAG}.fa --mapping ${MYTAG}.fa.mapping.tsv

# ② GFF3：seqid 改名 +（推荐）按染色体重编号为平台风格 ID
#    ②-1 seqid 归一化，保留作者 ID（供下一步留痕）
$PY scripts/normalize_diploid.py gff3 \
  --gff3 genes_HC_LC.gff3.gz --assembly-report GCA_xxx_assembly_report.txt \
  --keep-author-ids --out step1.gff3 --mapping step1.seqid_map.tsv
#    ②-2 重编号：每染色体按坐标从 000100 起、每 100 递增；未定位用 UnG 全局编号
$PY scripts/renumber_gff_ids.py \
  --gff3 step1.gff3 --out ${MYTAG}.gff3 \
  --id-prefix "AeCom.AE783.r1." --id-map ${MYTAG}.idmap.tsv \
  [--digits 6] [--step 100] [--unplaced-token Un]
#    若该物种作者 ID 本身已合规且无需重编号，可跳过 ②-2，改用：
#    normalize_diploid.py gff3 ... [--id-prefix "AeCom.AE783."]

# ③ 生成 CDS/PEP
/home/fei/mambaforge/envs/new_env/bin/gffread -E \
  -g ${MYTAG}.fa -x ${MYTAG}.cds -y ${MYTAG}.pep ${MYTAG}.gff3

# ④ 蛋白 FASTA 终止符清理（如用作者蛋白交叉验证/或直接作 PEP 输入）
$PY scripts/normalize_diploid.py pep --pep in.pep --out ${MYTAG}.pep

# ⑤ 汇总断言
$PY scripts/normalize_diploid.py check --dir .
```

**规则要点**（`normalize_diploid.py` 已实现）：
1. **seqid 映射**：`^[1-7][A-Z]$`（如 `1M`）→ `Chr1M`；assembly_report 的 assembled-molecule → `Chr`+Sequence-Name；其余（unplaced/unlocalized）→ `ChrUn_`+Sequence-Name；已 `Chr` 开头的保持不变。
2. **NCBI FASTA 头是 GenBank 登录号**（`CM127985.1` 染色体 / `JBHEGE020000008.1` scaffold），**不是** Sequence-Name —— 必须用 assembly_report 映射，否则 G1 第一条就挂。
3. **mRNA ID**：
   - **平台风格重编号（推荐，WheatOmics 主流）**：`gene = <prefix><chr>G<6位号>`、`mRNA = gene + ".1"`；每条染色体按坐标从 `000100` 起每 100 递增，未定位 `UnG` 全局编号；原 ID 留痕到 `original_id` 属性 + `idmap.tsv`（`scripts/renumber_gff_ids.py`，`--check` 可作 G1 闸门）；
   - 兼容旧规则：`-mRNA-N` → `.N`；`.p(\d+)$` → `.\1`；仍不以 `.数字` 结尾则追加 `.1`；
   - **跨物种重复 ID 必须先加前缀**（典型：TAMA/STRG 家族 `model.model.STRG.*`，多物种编号各自独立、会重名；平台先例 `AeCom.PI551049.…`、`AeUmb.TA1851.…`）；
   - 同步改写 `ID=` / `Parent=` / `Derives_from=`（两遍流式），并保留改名映射表。
4. **pep 终止符**：作者蛋白常以 `.` 或 `*` 表示终止 —— 平台只自动清 `.`，`*` 必须预处理掉（`normalize_diploid.py pep`）。
5. **未定位序列/基因不能丢**：`ChrUn_*` 全部保留（先例 PT 保留 31 个未定位基因；除非原始 FASTA 根本没有该序列，如 ZX830，只能放弃并记录）。
6. `ChrUn_*` 头**不要**加 `_${MYTAG}` 后缀（流水线 Step 1 已特殊处理，否则与 GFF/BED 的 seqid 对不上）。

### 4.4 留痕

- `provenance.txt`：组装号/登录号、BioProject/BioSample、下载 URL、原始文件 md5、论文 DOI/期刊/年份、归一化规则与脚本版本、接入日期；
- `name_plan.json`（G0 生成）；
- `mapping.tsv`（FASTA/GFF 两张：原名→新名，便于回溯）。

---

## 5. G2 —— 质检

```bash
cd /var/www/data/masw_data/${PLOIDY}_${MYTAG}
python3 /var/www/html/Script/check_genome_files.py ${MYTAG}; echo "rc=$?"
```

必须 **rc=0**（输出「所有文件均通过检查！」）。注意：
- 脚本会**自动清理 pep 序列行中的 `.`** 并留 `.pep.bak`；`*` 不会自动清 → 用 §4.3 的 `pep` 子命令先清；
- `.fa` 检查会跳过含 `contig`/`scaffold` 字样的头，但 `.gff3`/`.cds`/`.pep` 的 ID 规则是硬性的。

**附加断言（v2 建议全做）**：

```bash
# seqid 全 Chr、mRNA ID 全 .数字、无重复
$PY scripts/normalize_diploid.py check --dir .
# 计数应与来源一致（例：4 个二倍体 Aegilops = 51,203/47,246/49,677/50,416 mRNA）
grep -c $'\tmRNA\t' ${MYTAG}.gff3
grep -c '^>' ${MYTAG}.fa ${MYTAG}.cds ${MYTAG}.pep
```

---

## 6. G3 —— 跑流水线（`add_wheat_genome.sh`，10 步）

> 输入：`${MYTAG}.fa/.gff3/.cds/.pep` 已过 G2；`${data_dir}/name_plan.json` 已生成。
> 命名门禁（2026-10-23 起）：脚本启动前检查 `name_plan.json` 存在且 `ds == ${PLOIDY}_${MYTAG}`，否则直接 `[ERROR]` 退出（临时绕过 `WHEATOMICS_SKIP_NAMING_GATE=1` 仅用于补历史/测试）。

```bash
export PATH=/var/www/html/blast/blast+/bin:/home/fei/mambaforge/bin:$PATH
export HOME=/home/fei
cd /var/www/data/masw_data/${PLOIDY}_${MYTAG}
setsid --fork bash -c "exec bash /var/www/data/masw_data/add_wheat_genome.sh \
  ${MYTAG} /var/www/data/masw_data/${PLOIDY}_${MYTAG} ${PLOIDY}" \
  > pipeline_${MYTAG}.log 2>&1 < /dev/null
```

流水线步骤（v2 实测版，1034 行）：

| Step | 内容 | 产物/校验 |
|---|---|---|
| 0 | `check_genome_files.py` 复检（4 文件） | 4 个文件存在 |
| 1 | FASTA 头标准化：`>Chr1A` → `>Chr1A_${MYTAG} ${MYTAG} ${PLOIDY} Chr1A`；`ChrUn_*` 原样保留。校验：头全 `Chr`、GFF 染色体都能在 FASTA 找到、标准化后无重复 ID | `${PLOIDY}_${MYTAG}.genome` |
| 2 | 按染色体拆分（`split_fasta_by_chrom.py`，只拆 `Chr+数字+字母`；`ChrUn_*` 不拆） | `${PLOIDY}_${MYTAG}.genome_Chr*` |
| 3 | 拷贝核酸序列到 BLAST 目录 + 建软链 | `blastdb/${DS}.genome*` |
| 4 | `makeblastdb` 整基因组库（自动分卷 + `.nal`） | 整基因组核酸库 |
| 5 | 建软链（BLAST 服务目录） | — |
| 6a | 建 JBrowse 数据集目录 | `jbrowse-1.12.3-release/${DS}/` |
| 7.1 | EggNOG emapper（12 CPU；`--pfam_realign`） | `${DS}_annotation.emapper.annotations` |
| 7.2 | BED（带 EggNOG/Pfam 注释） | `${DS}_with_annotation.bed` |
| 7.2.1 | BED 注册 MySQL | `Genefunc_${DS}_table`（行数 ≈ mRNA 数） |
| 7.3 | EggNOG/Pfam + 中国春 02G（miniprot 50 线程）→ 带 Description 的 GFF/CDS/PEP | `${DS}.add_eggnog_ChineseSpring02G.gff3`、`${DS}.add_Description.cds/.pep` |
| 7.3.1–7.3.2 | 拷贝并建 CDS/PEP BLAST 库 | `${DS}.add_Description.cds|pep` |
| 7.6 | `flatfile-to-json.pl` 导入 `all_gene` 轨道 | JBrowse trackList |
| 6b | `prepare-refseqs.pl`（自动判断长名/短名 GFF 与对应 FASTA） | `seq/refSeqs.json` |
| 8 | `generate-names.pl` 基因名搜索索引 | JBrowse names |
| 9 | 最终 BED（加 02G） | `${DS}_with_annotation_ChineseSpring02G.bed` |
| 10 | `import_jbrowse_meta.py --dataset ${DS}` + `rebuild_genome_registry.py` | `jbrowse_meta` 行、`genome_registry` 基础行 |

**G3 闸门（逐项断言）**

```bash
grep -E "\[SUCCESS\]|\[ERROR\]" pipeline_${MYTAG}.log
BB=/var/www/html/blast/blast+/bin
$BB/blastdbcmd -db /var/www/html/getfasta/blastdb/${DS}.genome -info | head -3
$BB/blastdbcmd -db /var/www/html/getfasta/blastdb/${DS}.add_Description.cds -info | head -3
PW=$(grep '^DB_PASS=' /etc/wheatomics/db_ddl.env | cut -d= -f2)
mysql -u wheatomics_ddl -p"$PW" -N -e "SELECT COUNT(*) FROM Genefuncdb.Genefunc_${DS}_table;"
python3 -c "import json;print(len(json.load(open('/var/www/html/jbrowse-1.12.3-release/${DS}/seq/refSeqs.json'))))"
```

预期：整基因组库序列数 = FASTA 序列数、总长 = 组装总长；染色体拆分库数 = 染色体数（未定位不拆）；基因表行数 = mRNA 数；`refSeqs.json` 条数 = FASTA 序列数（含 `ChrUn_*`）。失败重跑前清理该基因组的半成品（`.genome_*`、blastdb 同名文件、JBrowse 目录）。

---

## 7. G4 —— 收尾（`finish_genome_integration.sh` v2，10 项）

> 前提：G3 已 `[SUCCESS]`，`name_plan.json` 存在。**先 `--dry-run`，再正式跑。**
> v2 适配：JBrowse V2.0（`.asm-card`/`asm-group` + hero/status/组计数）、wheatBLAST SPA（跳过 HTML、改 API 断言）、二倍体 `GROUP` 推导。
> 新增选项：`--section-title/--section-desc/--search-extra`（V2 新建分区与卡片搜索词）、`--require-section`（分区缺失时 BLOCK；默认只 WARN 并在收尾时新建）。
> 测试/非常规路径：所有路径可用 `WHEATOMICS_*` 环境变量覆盖（`WHEATOMICS_JBROWSE_HTML` / `WHEATOMICS_BLAST_HTML` / `WHEATOMICS_BLASTDB` / `WHEATOMICS_REPO` / `WHEATOMICS_DDL_ENV` / `WHEATOMICS_API` 等，默认值即生产路径），便于在 fake docroot 上演练。

```bash
bash scripts/finish_genome_integration.sh ${PLOIDY} ${MYTAG} ${DOI} \
  --title "论文标题" --label "Ae.comosa IPK-AE783 (M)" \
  --accession "GCA_…" --species "Aegilops comosa" --cultivar "IPK-AE783" \
  --journal "BMC Plant Biology" --year 2026 \
  --source-url "https://ftp.ncbi.nlm.nih.gov/…/" --source-md5 "…" \
  --group "Other Triticeae" \
  --section-title "MM Aegilops comosa" --section-desc "Aegilops comosa (M genome)" \
  --search-extra "aegilops comosa m genome ipk-ae783" \
  --dry-run
# 正式：
bash scripts/finish_genome_integration.sh …（同上，去掉 --dry-run）
```

自动完成（幂等，改动前自动备份到 `/var/www/data/masw_data/backup_<时间戳>/`）：

| # | 步骤 | 说明 |
|---|---|---|
| 1 | JBrowse 卡片 | V2：插入 `id="group-<ploidy>"` 的 `asm-grid` 末尾；无该分区则新建；同步 hero/asm-status/组计数 |
| 2 | Web BLAST | SPA：跳过 HTML（库清单动态）；旧页面：保留原 optgroup/hidden input 逻辑 |
| 3 | PrimerServer2 `.fai` | `samtools faidx ${DS}.genome`、`${DS}.add_Description.cds` |
| 4 | Genefunc_registry | upsert 1 行（`table_name/Polyploidy/Group/DOI/title/examples/display_name`） |
| 5 | 聚合库 alias | `all_genomes.nal` + `all_genomes_type.txt`（`${DS}.genome<TAB>${PLOIDY}`）、`all_gene.nal`、`all_protein.pal` |
| 6 | jbrowse_meta | `import_jbrowse_meta.py --dataset ${DS}` |
| 7 | genome_registry | 重建（读取 `overrides`，见 §9.2） |
| 8 | 元数据写回 | DOI/标题/期刊/年份/物种/材料/登录号/gene_count/subgenomes/flags |
| 9 | BLAST↔JBrowse 映射 | `build_blast_jbrowse_map.py` 重建（决定 BLAST 结果页的 JBrowse 按钮） |
| 10 | 自动验收 | BLAST 库/alias/MySQL/API/HTML/映射 10+ 项 |

**仍需人工的**：
- `cite.html` 引文（服务器 `/var/www/html/cite.html`，**不在 repo**；改前备份）；
- 额外注释轨道（TE/重复序列等，见 §8）；
- 首页/新闻公告（可选）；
- 最后一次 `sudo systemctl restart wheatomics-api`（让 Python 改动/分类缓存/sequence 缓存生效）。

### 7.1 额外注释轨道（TE/重复序列，可选）

1. **归一化 GFF**：seqid 必须与数据集 `seq/refSeqs.json` 一致（`Chr1A`/`ChrUn_*`）；属性简化（`ID=TE_<n>;Name=<motif>`）、type 统一为 `TE`、GFF3 头 `##gff-version 3`；TE 文件如果是 GFF2 `similarity` 风格要转换，EDTA 等标准 GFF3 直接可用；
2. **生成 NCList 轨道**（在数据集目录内执行，自动 merge 进 `trackList.json`）：
   ```bash
   JB=/var/www/html/jbrowse-1.12.3-release
   cd $JB/<DS>
   /home/fei/mambaforge/envs/new_env/bin/perl ../bin/flatfile-to-json.pl \
     --gff <归一化.gff3> --trackLabel TE --type TE --nameAttributes Name \
     --trackType CanvasFeatures --key "Transposons (TE)" \
     --clientConfig '{"style":{"color":"#7c3aed","height":6}}' \
     --config '{"category":"Annotation"}' --out ./ --sortMem 4000000000
   ```
   **必须用 `new_env` 的 perl**（系统 perl 缺 `PerlIO::gzip`）；PT 12.4M 特征约 19 min、~1.8G 轨道数据。
3. **同步 jbrowse_meta**：`import_jbrowse_meta.py --dataset <DS>`（否则 API 代理的 trackList 看不到轨道）；
4. **验证**：`curl -s "http://127.0.0.1:8000/api/jbrowse/datasets/<DS>/trackList" | grep -o TE`；`curl -sk -H 'Host: wheatomics.sdau.edu.cn' "https://127.0.0.1/jbrowse-1.12.3-release/<DS>/tracks/TE/Chr1A/trackData.json"` 200。
5. **改了 `seq/refSeqs.json`（增删/重命名 refseq、换组装）必须重建 BLAST↔JBrowse 映射**（见 §9.3）。

---

## 8. G5 —— 验收（硬指标）

| # | 项 | 断言 |
|---|---|---|
| 1 | `genome_registry` | `/api/genomes/{DS}`：species/ploidy/subgenomes/assembly_accession/assembly_level/genome_size/chromosome_count/gene_count/doi/annotation_status 齐全，`visible=1` |
| 2 | BLAST 库 | `/api/blast/databases?program=blastn` 出现 `${DS}.genome` + 每个染色体库 + `.add_Description.cds`；`program=blastp` 出现 `.add_Description.pep`；分类正确 |
| 3 | Web BLAST | SPA 下拉可见新库；提交一条测试序列能出结果，结果页有 JBrowse 按钮 |
| 4 | JBrowse | `/api/jbrowse/datasets` 含 DS；`/jbrowse-1.12.3-release/?data=${DS}` 200；refseq 数 = FASTA 序列数；`all_gene` 轨道有基因 |
| 5 | getfasta | `/api/sequence/chromosomes?database=all_genomes&pattern=${MYTAG}` 命中；`by-interval` 返回 FASTA |
| 6 | PrimerServer2 | `/api/PrimerServer2/databases` 含新库；`examples` 非空；`/databases/${DS}.genome/sequences` 200 |
| 7 | 基因功能 | `/api/genes/functions/tables` 含 `Genefunc_${DS}_table`；registry 分组正确；示例基因能查功能 |
| 8 | 前端 | JBrowse 页含新卡（hero/命名数/分区计数已 +1）；IntervalTool/PfamSearch/CAPS 下拉可见新表 |
| 9 | 回归 | 旧基因组（同物种旧条目、Chinese Spring、tauschii 等）BLAST/getfasta/JBrowse 正常；聚合库旧成员可查 |
| 10 | 映射 | `build_blast_jbrowse_map.py --check` 退出码 0；`/api/jbrowse/coverage` `ok=true`，新基因组 `assembly_match=true` |
| 11 | 计数 | `/api/genomes/stats` 总数/分类/`annotation_status` 按预期 +1；`Genefunc_registry`、`jbrowse_meta` 行数正常 |

---

## 9. 登记与元数据

### 9.1 `Genefunc_registry`（每基因组 1 行，收尾脚本 upsert）

`table_name=Genefunc_${DS}_table`、`Polyploidy=${PLOIDY}`、`Group=（§3 规则）`、`chromosome_level='Yes'`、`Doi/title/Abstract`、`example_species_chr_id='Chr1X_${MYTAG}:200-500'`、`example_cds_id/example_protein_id` 用真实 ID、`visible=1`、`display_order`（同 Polyploidy 末尾或 500）。

### 9.2 `genome_registry`（`scripts/rebuild_genome_registry.py`）

- 脚本从「JBrowse / Genefunc_registry / blastdb / all_genomes.nal / synteny / orthofinder」等平台事实重建，**幂等 upsert**；
- 不在策展表里的新基因组，把手工字段写进 `overrides` 字典（**否则 rebuild 会把它们留空**）：`species/ploidy/subgenomes/cultivar_or_line/assembly_accession/assembly_level/chromosome_count/genome_size/gene_count/te_content/doi/paper_title/journal/publication_year/annotation_status/annotation_source/annotation_doi/notes`；
- **重点**：`chromosome_count` 必须写 overrides（rebuild 会用 `.genome.fai` 的**序列数**当染色体数，未定位 scaffold 会把 7 条写成几十/几百条）；`assembly_level` 同理；
- 收尾脚本第 8 步会再写回 DOI/标题/材料/基因数/flags，但 `overrides` 是重建时的兜底。

### 9.3 BLAST↔JBrowse 映射（必做）

```bash
cd /var/www/FastAPI_backend_Port8000
set -a; . ./.env; set +a
PY=/home/fei/mambaforge/envs/zjw/bin/python3
$PY scripts/build_blast_jbrowse_map.py           # 重建
$PY scripts/build_blast_jbrowse_map.py --check   # 期望 CHECK OK（0）；2=映射过期，1=匹配率过低
curl -s http://127.0.0.1:8000/api/jbrowse/coverage
```

映射按**染色体长度**把 BLAST `.fai` seqid 与 JBrowse `refSeqs.json` 匹配；长度不一致 = 不是同一组装 → 该库**故意不给**按钮（保护，不是 bug）。映射文件按 mtime 自动重载，**不需要重启 API**；但同一批改了 Python 代码则仍需重启。

### 9.4 服务器缓存

| 缓存 | TTL | 影响 |
|---|---|---|
| `/api/blast/databases` 磁盘列表 | 1 h | 新库/新分类必须重启 API 才立刻可见 |
| `/api/sequence/chromosomes` 进程内 `_CHROM_CACHE` | 1 h | 改了聚合库 alias 后重启/等过期 |
| JBrowse trackList 代理 | 按 mtime | 重导 jbrowse_meta 后立即生效 |

---

## 10. 部署与同步（改脚本/前端时）

1. **代码/页面**：本地改 → `git fetch origin`（Gitee）对齐 → commit → **github + gitee 双推** → 生产 `git -C /var/www/FastAPI_backend_Port8000 fetch origin && git merge --ff-only origin/main` → 需要时 `sudo systemctl restart wheatomics-api`；
2. **收尾脚本**：仓库 `scripts/finish_genome_integration.sh` 是源；安装到 `~/.agents/skills/lab-server/scripts/` 与服务器 `/var/www/data/masw_data/_prep/`，两边 `md5sum` 一致；
3. **归一化脚本**：仓库 `scripts/normalize_diploid.py` → 服务器 `_prep/normalize_diploid.py`（流水线前使用）；
4. **docpages 页面**（`app/static/docpages/*.html`）：改 repo 源文件 → `python3 scripts/deploy_doc_pages.py --only <page>`（自动备份，无需重启 Apache/API）；`--check` 可做漂移审计；
5. **静态 SPA 页面**（`app/static/interval|PfamSearch|caps/index.html`）：git pull 后浏览器刷新即可（StaticFiles 直读仓库目录）；
6. **BLAST 页面**（`app/static/blast2/index.html` → `/var/www/html/blast/blast.html`）：如确需改，`python3 scripts/deploy_blast2_preview.py`（带 `--check` 对账）；
7. **注意**：生产 `/var/www/FastAPI_backend_Port8000` 上手工改文件会被 Gitee webhook 的 `auto_pull.sh`（`git reset --hard FETCH_HEAD`）覆盖 —— 所有改动必须走 repo。

---

## 11. 已知坑（v2 版，都踩过）

| # | 坑 | 处置 |
|---|---|---|
| 1 | `run_cmd awk … > file` 会把 `[CMD]` 日志重定向进 `.genome` | 脚本 Step 1 已改为直接 awk；不要改回 |
| 2 | 生产手工改文件会被 webhook 覆盖 | 见 §10；改 repo |
| 3 | `/api/blast/databases` 缓存 1 h | 重启 API |
| 4 | GFF mRNA ID 不以 `.数字` 结尾 → Step 0 失败 | `normalize_diploid.py gff3`；改 ID 必须同步 `Parent=` |
| 5 | `ChrUn_*` 必须保留（否则丢基因）；`split_fasta_by_chrom.py` 只拆 `Chr+数字+字母`，不拆 ChrUn（符合预期） | 归一化时保留，`ChrUn_<原名>` |
| 6 | 原始组装缺 scaffold 序列（如 ZX830）→ 未定位基因无法纳入 | 记录到 manifest，等完整组装重跑 |
| 7 | 服务器 PATH 没有 conda → `activate_env` 失败 | 显式 `export PATH=/home/fei/mambaforge/bin:$PATH` |
| 8 | JBrowse trackList 由 Apache 代理到 API | 改 JBrowse 只需重建目录 + 重导 jbrowse_meta；不需要改 Apache |
| 9 | getfasta/PrimerServer2 示例依赖 `.fai` 与 `Genefunc_registry` | 补 `.fai`；registry 由收尾脚本 upsert |
| 10 | **数据集名决定分类归属**；跑完再改要重建库/表/HTML | G0 必做 `--check-name --write-plan --confirm` |
| 11 | BLAST 结果页 JBrowse 按钮来自离线映射 | 新增/换组装后必须 `build_blast_jbrowse_map.py` 重建，`--check` 应为 0 |
| 12 | **v1 遗留**：归一化脚本只认 A/B/R、NCBI FASTA 头是 GenBank 登录号、跨物种 mRNA ID 重名、pep 的 `*`、TE seqid 各物种不同 | v2 已修：`normalize_diploid.py`；见 §4.3/§4.4 |
| 13 | **v1 遗留**：收尾脚本按旧页面写（旧 optgroup/`card-group`/`#cite`）→ 门禁 BLOCK、卡片插错 | v2 已修：新版脚本识别 V2/SPA；见 §7 |
| 14 | **v1 遗留**：二倍体单字母倍性 GROUP 推导错、SUB 缺 CC/NN、静态页数组缺新倍性 | v2 已修：见 §3；新倍性照表补 |
| 15 | 表名/库名里带 `-`/`.` | MYTAG 只用字母/数字/下划线；原始连字符写 display_name/notes |
| 16 | `ae.` 是 BLAST 分类关键词（会命中任何含 `ae.` 的库名） | 命名不要带 `ae.`；不要新增过宽关键词 |
| 17 | `chromosome_count` 被 `.fai` 序列数污染 | overrides 显式写染色体数（§9.2） |
| 18 | 平台仍可能有未上线/隐藏条目（`visible=0`） | 新增前用 `/api/genomes?q=…&include_hidden=true` 查重 |
| 19 | **下载大批量数据时被限速/中断**：NCBI 国际链路单连接 ~150 KB/s；`pkill -f 脚本名` 只杀 bash、**curl 子进程会继续写文件**，续传会与残留 curl 并发写 → 文件损坏（gzip trailing garbage、md5 不符） | ① 并行下载（`fetch_aegilops4_data.sh --only <PLOIDY>` 每物种一进程，或单文件 6 路 Range 分段）；② 停任务用 `pkill -9 -f "<文件名/URL>"` 连 curl 一起杀，确认后再续传；③ 下载后必须 `md5sum` 对来源基准 + `gzip -t` 双校验 |

---

### 11.x 2026-11-12 四基因组上线补充经验（Aegilops MM/CC/UU/NN）

- **API 缓存**：`/api/blast/databases` 等磁盘缓存 1h；G3 建库后、G4 收尾前必须 `sudo systemctl restart wheatomics-api`
  （worker 冷启动约 2–3 分钟，期间 curl 000 属正常）；G4 完成后再重启一次刷新 alias/PrimerServer2 缓存。
- **registry rebuild 会从平台事实自动登记数据集**：首次跑 `rebuild_genome_registry.py` 可能新增几行 registry
  （本次 5 行：PI428250 / ThatcherLr9 / Chinese Spring 03G / Durum_Wheat_cv._Svevo / E.sibiricus_GaomuNo.1），
  `/api/genomes/stats` total 因此 316→325；验收按「316 + 4 + 自动登记」口径核对，勿当成错误。
- **`chromosome_count` 需强制覆盖**：rebuild 用 `.fai` 序列数填 chromosome_count（含 scaffold，如 17/24/250/21），
  overrides 默认跳过已有值；在 overrides 里加 `"_hard": ["chromosome_count"]` 强制为 7，并补 `display_name`/`subgenomes`。
- **V2 新分区标题**：`section-title` 会被放进 `asm-formula`（应为纯倍性代码）；新分区建议 `--section-title "CC"`，
  描述放 `--section-desc`（如 `Aegilops markgrafii (C genome)`）。
- **docroot 页面回写**：G4 直接改 `/var/www/html/jbrowse.html`；收尾后必须拷回 `app/static/docpages/jbrowse.html`
  并提交，否则下次 `deploy_doc_pages.sh` 会覆盖新卡片。
- **验收工具**：`accept_aegilops4_onboarding.py` 覆盖 90 项（全局计数/前端/映射、每基因组 16 项×4、回归 3 项），
  可作后续新基因组 G5 模板；报告中 90/90 PASS。

### 11.y GetSequence（/getfasta/）必查项（2026-11-12 补充）

页面的三块数据来源不同，缺一不可：

1. **支持基因组面板/示例**：运行时读 `/api/genes/functions/registry`（Genefunc_registry）。
   必须确保本基因组行存在且 `example_species_chr_id` / `example_cds_id` / `example_protein_id`
   指向**染色体上的真实基因**（不要用 ChrUn 基因作示例更直观）；`display_name` 用友好名
   （如 `Ae.comosa IPK-AE783 (M)`），否则面板显示技术名。收尾脚本 step 4 已按 `--label` 写入。
2. **聚合 BLAST 别名**：页面下拉只有 `all_genomes / all_genes / all_proteins / all_other_genomes`。
   收尾脚本只维护了旧的 `all_gene.nal / all_protein.pal`，**页面 by-gene/batch 实际查
   `all_genes / all_proteins`（复数）** —— 必须同时维护。收尾脚本 step 5 已改为同时写 5 个别名。
   - **BLAST 别名 200 成员上限**：`blastdbcmd -entry_batch` 只读前 200 个成员，第 201 个起
     返回 `Skipped`。all_genes 已到 200：新增成员用**前插**（收尾脚本已实现），并运行
     `scripts/rebuild_getfasta_aggregates.py --apply` 重建（脚本会排除 PacBioFullLengthcDNA、
     Tae_TF、fangenome 等非基因组注释库，把成员压回 ≤200）。再加基因组前需再清理成员。
   - `blastdbcmd -entry` 对**核酸别名库**不支持（报 "DB contains no accession info"），
     这是平台既有现象（所有基因组一致）；CDS 单基因查询请用 `/api/sequence/batch`。
3. **文档示例表**：`/var/www/html/doc/getsequence_search.txt`（页面链接；188 行，4 列）。
   每个新基因组需加一行：`<DS>\t<Chr1X_DS:200-500>\t<example_cds>\tall_genomes`；
   用 `scripts/update_getsequence_search.py --doc ... --name DS --region ... --gene ... --composition PLOIDY --library all_genomes`
   （收尾脚本 step 5b 自动完成）。

验收（G5）：
```bash
curl -s "http://127.0.0.1:8000/api/sequence/by-gene?gene_id=<example_cds>&protein_db=all_proteins" | grep -q protein_sequence
curl -s "http://127.0.0.1:8000/api/sequence/batch?database=all_genes&ID=<example_cds>" | grep -q '"succeeded":1'
curl -s "http://127.0.0.1:8000/api/genes/functions/registry" | grep -q "Genefunc_<DS>_table"
curl -s "http://127.0.0.1:8000/api/sequence/by-interval?region=<Chr1X_DS:200-500>&database=all_genomes" | grep -q ">"
curl -s https://<host>/doc/getsequence_search.txt | grep -q "<DS>"
```
注意：by-gene 返回的是**裸对象**（`gene_sequence`/`protein_sequence` 在顶层，不在 `data` 里）。

## 12. v1→v2 修复记录（2026-11-11）

| # | v1 问题 | v2 处置 | 状态 |
|---|---|---|---|
| 1 | SOP 文档漂移（`add_wheat_genome.sh` md5 与记录不符） | 本文件按生产实测版重写；md5 记在 §0 | ✅ |
| 2 | 归一化只认 A/B/R 染色体 | 新脚本 `normalize_diploid.py`（任意 `[1-7][A-Z]` + assembly_report 映射） | ✅ |
| 3 | 收尾脚本与 V2/SPA 页面结构性错配（门禁 BLOCK、卡片/下拉 FAIL） | 新版 `scripts/finish_genome_integration.sh`（SPA 跳过 HTML、V2 卡片插入 + 计数、API 断言） | ✅ |
| 4 | 二倍体 GROUP 推导不一致（MM/CC/NN→Other、UU→Diploid） | `GROUP` 映射按倍性分类重写；`--group` 可显式覆盖 | ✅ |
| 5 | `SUB` 缺 CC/NN、registry `_CANONICAL`/静态页缺新倍性 | `SUB` 补 CC/NN；静态页 diploid 数组补 CC/NN；`_CANONICAL` 已核实无需改（`karyotype_ploidy` 可算） | ✅ |
| 6 | BLAST 分类缺 markgrafii/uniaristata 关键词 + `web_blast_group` 旧判定永远 0 | `DB_CLASSIFICATION` 补关键词；`web_blast_group` 判 SPA（有库即 1） | ✅ |
| 7 | 跨物种重复 mRNA ID（TAMA/STRG 家族） | `normalize_diploid.py gff3 --id-prefix` 加物种前缀；G1 断言跨物种重复=0 | ✅ |
| 8 | pep `*` 终止符平台不清 | `normalize_diploid.py pep` 统一清 `.`/`*` | ✅ |
| 9 | NCBI FASTA 头是 GenBank 登录号（v1 误以为是 `1M`） | `normalize_diploid.py fasta --assembly-report`；G1 断言无残留登录号 | ✅ |

---

## 13. 案例记录

- **PT / ZX830**（2026-10-22/23，六倍体小黑麦 AABBRR）：PT 172 序列/215,294 mRNA，流水线 1h23；ZX830 21 染色体/217,020 mRNA；旧页面时代（v1 流程）。
- **CWI 22960**（2026-11-08，四倍体 carthlicum，genome-only + 后补 EGAPx 注释）：无公开注释，走两阶段流程（见 `genome-only-then-annotation-update.md`）。
- **4 个二倍体 Aegilops**（2026-11，M/C/U/N；BMC Plant Biology 2026，Zenodo 22681907）：本 SOP v2 的首批用例——NCBI 4 个 GCA 组装 + Zenodo HC/LC 注释 + EDTA TE；归一化用 `normalize_diploid.py`，命名 `MM_Aegilops_comosa_IPK_AE783` 等；详见仓库 `Aegilops4_diploid_genome_update_plan.md` 与 `docs/plans/aegilops4_2026-11/`。

---

## 附录 A：一键核验脚本（按需改占位符）

```bash
PLOIDY=MM; MYTAG=Aegilops_comosa_IPK_AE783
DS=${PLOIDY}_${MYTAG}
B=/var/www/html/getfasta/blastdb
BB=/var/www/html/blast/blast+/bin
PW=$(grep '^DB_PASS=' /etc/wheatomics/db_ddl.env | cut -d= -f2)
PY=/home/fei/mambaforge/envs/zjw/bin/python3

echo "== MySQL =="; mysql -u wheatomics_ddl -p"$PW" -N -e "SELECT COUNT(*) FROM Genefuncdb.Genefunc_${DS}_table;"
echo "== BLAST genome =="; $BB/blastdbcmd -db "$B/${DS}.genome" -info | head -2
echo "== BLAST cds/pep =="; $BB/blastdbcmd -db "$B/${DS}.add_Description.cds" -info | head -2; $BB/blastdbcmd -db "$B/${DS}.add_Description.pep" -info | head -2
echo "== JBrowse =="; python3 -c "import json;print(len(json.load(open('/var/www/html/jbrowse-1.12.3-release/${DS}/seq/refSeqs.json'))))"
echo "== API =="; curl -s http://127.0.0.1:8000/api/genomes/${DS} | head -c 300; echo
echo "== getfasta =="; curl -s "http://127.0.0.1:8000/api/sequence/chromosomes?database=${DS}.genome" | head -c 200; echo
echo "== PrimerServer2 =="; curl -s "http://127.0.0.1:8000/api/PrimerServer2/databases" | grep -o "${DS}.genome" | head -1
echo "== .fai =="; ls -la "$B/${DS}.genome.fai" "$B/${DS}.add_Description.cds.fai"
echo "== JBrowse 映射 =="; ( cd /var/www/FastAPI_backend_Port8000 && $PY scripts/build_blast_jbrowse_map.py --check )
```

## 附录 B：命令模板（新基因组从零到上线）

```bash
# 变量
PLOIDY=MM; MYTAG=Aegilops_comosa_IPK_AE783; DOI=10.1186/s12870-026-10046-2
DS=${PLOIDY}_${MYTAG}; DIR=/var/www/data/masw_data/${DS}

# G0 命名门禁
bash scripts/finish_genome_integration.sh ${PLOIDY} ${MYTAG} ${DOI} --check-name \
  --cultivar "IPK-AE783" --accession "GCA_052815735.2" --species "Aegilops comosa" \
  --group "Other Triticeae"
bash scripts/finish_genome_integration.sh ${PLOIDY} ${MYTAG} ${DOI} --check-name --write-plan --confirm \
  --cultivar "IPK-AE783" --accession "GCA_052815735.2" --species "Aegilops comosa" --group "Other Triticeae"

# G1 归一化（A2）：一条命令（幂等、逐步校验）——二倍体 Aegilops 专用
bash scripts/prepare_aegilops4_dataset.sh ${PLOIDY} ${MYTAG} <Zenodo前缀>   # 例 MM Aegilops_comosa_IPK_AE783 Ae.comosa
# 等价手工步骤（其他物种可参考）：
#   normalize_diploid.py fasta  → GenBank 登录号 → Chr*/ChrUn_*
#   normalize_diploid.py gff3 --keep-author-ids → 只改 seqid
#   renumber_gff_ids.py --id-prefix "AeCom.AE783.r1." → gene/mRNA 平台风格 ID（100 步）
#   gffread -E → cds/pep
#   normalize_diploid.py pep --stop-mode trim → 清 ./*
#   check_genome_files.py → rc=0

# G2 质检
python3 /var/www/html/Script/check_genome_files.py ${MYTAG}

# G3 流水线
export PATH=/var/www/html/blast/blast+/bin:/home/fei/mambaforge/bin:$PATH
export HOME=/home/fei
setsid --fork bash -c "exec bash /var/www/data/masw_data/add_wheat_genome.sh ${MYTAG} ${DIR} ${PLOIDY}" \
  > pipeline_${MYTAG}.log 2>&1 < /dev/null

# G4 收尾（先 --dry-run）
bash scripts/finish_genome_integration.sh ${PLOIDY} ${MYTAG} ${DOI} --label "Ae.comosa IPK-AE783 (M)" \
  --accession "GCA_052815735.2" --species "Aegilops comosa" --cultivar "IPK-AE783" \
  --journal "BMC Plant Biology" --year 2026 \
  --source-url "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/052/815/735/GCA_052815735.2_ASM5281573v2/" \
  --source-md5 "38b8436f9c4eb360a066a1c79f1a122a" --group "Other Triticeae" \
  --section-title "MM Aegilops comosa" --section-desc "Aegilops comosa (M genome)" \
  --search-extra "aegilops comosa m genome ipk-ae783" --dry-run

# G5 验收：附录 A + 手工页面检查 + 重启 API
sudo systemctl restart wheatomics-api
```
