# PHASE0 实现 B：二倍体 Aegilops 四件套归一化脚本与实测

> **任务**：task-5 · 2026-11-11 · 交付 `scripts/normalize_diploid.py` v1.0.0 + 本文
> **输入数据**：Zenodo `10.5281/zenodo.22681907`（作者基因注释 GFF3 + 蛋白 FASTA，已下载于 `zenodo_probe/`）
> ＋ NCBI GCA 组装（`*_assembly_report.txt` 与基因组 FASTA；本机只取报告，FASTA 未下载）
> **实测证据目录**：`docs/plans/aegilops4_2026-11/normalize_test/`（`out/` 产物、`reports/` 报告原件、
> `logs/` 全部命令输出、`fixtures/` efetch 片段、`platform_equiv_check.py` 平台检查逻辑存档）
> **SOP 对照**：`docs/workflow/wheatomics-new-genome-sop.md` §4.3（v2 归一化工具）已按本脚本 CLI 编写，
> 两者命令行完全一致。

---

## 0. TL;DR

1. **脚本已交付**：`scripts/normalize_diploid.py`（单文件、纯 Python3 stdlib、Python 3.7+、四个子命令
   `fasta / gff3 / pep / check`、`--help` 完整、失败非零退出码，可直接作 G1/G2 闸门）。
2. **4 个真实 GFF3 全量归一化完成**（未抽样、全量 462k–514k 行/物种，总耗时 ~32 s）：
   seqid 100% `Chr*`/`ChrUn_*`、mRNA ID 100% 以 `.数字` 结尾、gene/mRNA ID 全局唯一、
   基因/mRNA 计数与 Zenodo 源文件**逐项一致**（51,203 / 47,246 / 49,677 / 50,416）。
3. **跨物种重名解决**：51,666 个 STRG mRNA（及同数量 gene）ID 加物种前缀并把 `.pN→.N`；
   4 物种合并 mRNA 重复从 **7,081 → 0**（gene 同），`--also-ids` 增量断言可逐物种把关。
4. **4 份 assembly_report 映射预检**：映射行数 **17 / 24 / 250 / 21**、每份 `assembled-molecule=7`、
   总长与 `PAPER_DATA.md` §4.1 完全一致（4,407,741,597 / 3,577,170,360 / 4,268,089,219 / 4,475,943,907 bp）。
   ⚠ 顺带修正 `PAPER_DATA.md` 的 markgrafii `assembly_report.txt` md5 末位笔误（见 §4.3）。
5. **平台等价断言**：平台 `check_genome_files.py` 的 `check_gff3` 逻辑对 4 个输出 **4/4 PASS**；
   本脚本 `check` 子命令 4 文件汇总 **ALL CHECKS PASSED**（含跨文件查重）。
6. **pep 子命令全量冒烟**（comosa 51,203 条）：ID 精确映射命中 51,203/51,203、与归一化 GFF 的
   mRNA ID 集合完全相等、输出无 `.`/`*`。
7. **未做（明确声明）**：4×~4.7 GB 基因组 FASTA 未下载 → `fasta` 子命令未在真实 FASTA 上整跑
   （已用 assembly_report 预检 + efetch 真实片段 fixtures 覆盖映射逻辑）；`gffread` 未在本任务重跑
   （`PAPER_DATA.md` §5.6 已用「NCBI FASTA + Zenodo GFF」做过 17 位点端到端验证，结论直接引用）。
   服务器侧执行清单见 §7。

---

## 1. 交付物与 task-5 验收对照

| task-5 要求 | 状态 | 证据 |
|---|---|---|
| A) `fasta` 子命令：assembly_report 映射 FASTA 头、写 mapping.tsv、校验替换率/序列数/总长 | ✅ 实现；报告解析+映射实测，真实 FASTA 整跑留服务器 | §2、§4；`logs/02_fasta_dryrun_*.json`、`out/*.fa_mapping.tsv` |
| B) `gff3` 子命令：seqid + ID 规范化、两遍流式、strg 前缀、校验 | ✅ 实现 + 4 物种全量实测 | §3；`logs/03_gff3_*.log`、`out/*.gff3.gz` |
| C) `check` 子命令：多文件汇总断言（Chr、`.数字`、唯一、计数、gene=mRNA、ChrUn 基因数） | ✅ 实现 + 4 文件实测 PASS | §3.5、§5；`logs/05_check_4species.log` |
| D) `pep` 子命令：ID 规范化 + 去终止符 `.`/`*` | ✅ 实现 + comosa 全量实测 | §6；`logs/07_pep_comosa.log` |
| 实测 1) 4 GFF 跑 gff3 → check 全过、计数、改名示例 | ✅ | §3 |
| 实测 2) 4 assembly_report 映射预检：17/24/250/21、assembled=7 | ✅ | §4 |
| 实测 3) 用平台 `check_genome_files.py` 逻辑等价断言 out.gff3 | ✅ 4/4 PASS | §5 |
| 实测 4) 报告含服务器侧执行清单 + 实测证据 | ✅ | §7、§8 |

---

## 2. 脚本规格

### 2.1 子命令与 CLI（与 SOP §4.3 完全一致）

```bash
PY=python3
$PY scripts/normalize_diploid.py --help          # 子命令一览
$PY scripts/normalize_diploid.py <cmd> --help    # 各子命令参数

# ① FASTA：NCBI GenBank 登录号 -> Chr*/ChrUn_*（写 mapping.tsv）
$PY scripts/normalize_diploid.py fasta \
  --fasta GCA_xxx_genomic.fna.gz --assembly-report GCA_xxx_assembly_report.txt \
  --out ${MYTAG}.fa --mapping ${MYTAG}.fa.mapping.tsv
#    预检（不读 FASTA，只解析 report 并输出映射表；本任务用它做 4 物种预检）
$PY scripts/normalize_diploid.py fasta --dry-run \
  --assembly-report GCA_xxx_assembly_report.txt --mapping ${MYTAG}.fa.mapping.tsv

# ② GFF3：seqid 改名 + gene/mRNA ID 规范化（跨物种重复 ID 必加 --id-prefix）
$PY scripts/normalize_diploid.py gff3 \
  --gff3 genes_HC_LC.gff3.gz --assembly-report GCA_xxx_assembly_report.txt \
  --out ${MYTAG}.gff3 --mapping ${MYTAG}.gff3.seqid_mapping.tsv \
  --id-prefix "AeCom.AE783." \
  --id-map ${MYTAG}.idmap.tsv \
  [--also-ids 其他物种.idmap.json|tsv]     # 断言新 ID 与其他物种不冲突

# ③ 蛋白 FASTA：ID 规范化 + 去终止符（gffread 生成 pep 后清洗）
$PY scripts/normalize_diploid.py pep --pep in.pep --out ${MYTAG}.pep \
  [--id-map ${MYTAG}.idmap.tsv] [--stop-mode x|trim|drop]

# ④ 汇总断言（dataset 目录四件套齐全时）
$PY scripts/normalize_diploid.py check --dir .
#    多文件 / 跨物种断言（本任务用）
$PY scripts/normalize_diploid.py check \
  --gff3 a.gff3 b.gff3 c.gff3 d.gff3 \
  --expect-counts 51203,47246,49677,50416 --expect-unplaced 38,53,1103,66
```

关键参数：`--prefix`（染色体前缀，默认 `Chr`）、`--unplaced-prefix`（默认 `ChrUn_`）、
`--prefix-all-ids`（默认只给 STRG 家族加前缀；`--strg-only-prefix` 为显式默认写法）、
`--prefix-family-regex`（默认 `^(?:gene|model)\.model\.STRG\.`）、
`--seqid-map`（额外 seqid 映射，预留 TE GFF 的 comosa 裸数字 token）、
`--dry-run`、`--partial`（片段冒烟）、`--no-coord-check`、`--allow-unknown-seqids`。

输出/退出约定：日志写 stderr、`check` 摘要写 stdout；成功 `rc=0`，任一断言失败 `rc=1`；
`.gz` 输入按后缀或 gzip magic 自动识别，`--out/--mapping/--id-map` 以 `.gz` 结尾自动压缩写出。

### 2.2 映射规则（实现与实测一致）

**A. seqid（GFF3 与 FASTA 共用一套）**

| 原 seqid | 归一化后 | 实测例 |
|---|---|---|
| 已以 `Chr` 开头 | 原样保留 | — |
| `chr1A` 等任意大小写 `chr*` | `Chr` + 其余 | — |
| `^[1-7][A-Z]$`（任意倍性单字母） | `Chr` + 原名 | `1M→Chr1M`、`7C→Chr7C`、`1U→Chr1U`、`1N→Chr1N` |
| assembly_report `assembled-molecule` 的 Sequence-Name | `Chr` + 名 | `1M→Chr1M`（与上一行等价，双保险） |
| assembly_report 其它 role（unplaced/unlocalized-scaffold…） | `ChrUn_` + 原名 | `Super-Scaffold_100133_4M→ChrUn_Super-Scaffold_100133_4M`、`scaffold_9→ChrUn_scaffold_9`、`ptg000155l→ChrUn_ptg000155l` |
| report 中找不到 | 默认**报错**（防版本错配）；`--allow-unknown-seqids` 才按 `ChrUn_` | — |

FASTA 头（NCBI 实测第一 token 是登录号）→ 用 report 第 1 列（Sequence-Name）↔ 第 5 列
（GenBank-Accn，RefSeq-Accn 备用）：`CM127985.1→Chr1M`、`JBHEGE020000008.1→ChrUn_Super-Scaffold_100133_4M`，
头其余描述原样保留；同时校验替换率 100%、序列数一致、总长一致、无重复输出名。

**B. gene / mRNA ID（两遍流式：先收集映射，再重写）**

| 规则 | 实测数量 |
|---|---|
| `-mRNA-N` → `.N` | 0（本批无此命名） |
| `.p(\d+)$` → `.\1`（TAMA/STRG 家族：gene + mRNA 同步） | **103,332** 个 ID（51,666 gene + 51,666 mRNA） |
| STRG 家族加 `--id-prefix` 物种前缀 | 同上 103,332 个 |
| 仍不以 `.数字` 结尾 → 追加 `.1` | 0（`.pN→.N` 后已合规） |
| 同步改写 `ID=` / `Parent=` / `Derives_from=` / `Name=` 引用；exon/CDS 子 ID 随 Parent 派生改写 | 全部 460k 结构行 |

前缀取值（本任务实测用；最终数据集命名以 G0 `name_plan.json` 为准）：
`AeCom.AE783.` / `AeMar.EKC105.` / `AeUmb.AE740.` / `AeUna.AE680.`。
默认只给 STRG 家族加前缀（EVM 家族 `evm.model.<seqid>.<n>` 天然含 seqid、跨物种不重名，保持不变，
便于与 Zenodo 蛋白 FASTA 头直接对照）；`--prefix-all-ids` 可改为全部加。

**C. 校验断言**（`gff3` 子命令内置，任一失败 rc=1）

- 输出第 1 列全部以 `Chr` 开头；mRNA ID 全部 `.数字` 结尾、无残留 `.pN`；
- gene/mRNA ID 全局唯一；`Parent/Derives_from` 引用 100% 可解析（0 悬空）；
- feature 计数逐类型 preserved；gene 数 = mRNA 数（非 1:1 时告警）；
- 坐标合法且 `end ≤ assembly_report 序列长度`（防 FASTA/注释版本错配）；
- `--also-ids` 时与历史物种 ID 映射 0 交集；
- 说明：作者注释里 **CDS ID 是每个转录本共用一个**（`cds.<mRNA>`，本身不符合 GFF3 ID 唯一性），
  属输入原生特征（comosa 128,939 个重复等），脚本只提示不失败——平台 `check_genome_files.py`
  只校验 mRNA ID，gffread 用 `Parent` 解析不受影响。

---

## 3. 实测 A：4 个真实 GFF3 全量归一化（task-5 实测 1）

### 3.1 实际命令（按顺序执行，后一物种对前面所有物种做 `--also-ids` 断言）

```bash
Z=docs/plans/aegilops4_2026-11/zenodo_probe
T=docs/plans/aegilops4_2026-11/normalize_test
$PY scripts/normalize_diploid.py gff3 --gff3 $Z/Ae.comosa_genes_HC_LC.gff3.gz \
  --assembly-report $T/reports/GCA_052815735.2_ASM5281573v2_assembly_report.txt \
  --out $T/out/comosa.gff3.gz --mapping $T/out/comosa.gff3.seqid_mapping.tsv \
  --id-prefix "AeCom.AE783." --id-map $T/out/comosa.idmap.tsv.gz
# markgrafii / umbellulata / uniaristata 同理，分别加：
#   --id-prefix AeMar.EKC105. / AeUmb.AE740. / AeUna.AE680.
#   --also-ids $T/out/{已跑物种}.idmap.tsv.gz（逐一累加）
```

### 3.2 结果计数（全部逐项与 Zenodo 源文件一致）

| 指标 | comosa | markgrafii | umbellulata | uniaristata | 合计 |
|---|---|---|---|---|---|
| 输入行数 | 513,894 | 486,733 | 454,461 | 503,277 | 1,958,365 |
| gene / mRNA | **51,203 / 51,203** | **47,246 / 47,246** | **49,677 / 49,677** | **50,416 / 50,416** | **198,542 / 198,542** |
| exon / CDS | 180,142 / 180,142 | 172,497 / 172,497 | 177,553 / 177,553 | 176,014 / 176,014 | 706,206 |
| seqid 数（染色体+未定位） | 15（7+8） | 14（7+7） | 188（7+181） | 15（7+8） | 232 |
| ChrUn_ 上基因数 | **38** | **53** | **1,103** | **66** | 1,260 |
| 加前缀 + `.pN→.N` 的 ID | 25,302 | 24,602 | 26,078 | 27,350 | 103,332 |
| gene/mRNA ID 映射表条数 | 102,406 | 94,492 | 99,354 | 100,832 | 397,084 |
| 输出 `.gff3.gz` 大小 | 4.71 MB | 4.46 MB | 4.66 MB | 4.62 MB | 18.45 MB |

> mRNA 源文件数 = 论文 Table 3 = 51,203 / 47,246 / 49,677 / 50,416 ✅；ChrUn_ 基因数 = PAPER_DATA §5.2 的
> 38 / 53 / 1,103 / 66 ✅（未定位序列全部保留，未丢基因）。

### 3.3 ID 改名示例（before → after）

```
# markgrafii · STRG/LC 家族（前缀 + .p1→.1，Parent 同步）
gene.model.STRG.315.1.p1   → AeMar.EKC105.gene.model.STRG.315.1.1
model.model.STRG.315.1.p1  → AeMar.EKC105.model.model.STRG.315.1.1     ← task 验收示例
cds.model.model.STRG.315…  → cds.AeMar.EKC105.model.model.STRG.315.1.1  (Parent=…315.1.1)

# comosa · 未定位 scaffold 上的 STRG 基因（seqid 同时改为 ChrUn_）
Super-Scaffold_100133_4M : model.model.STRG.53733.1.p1
  → ChrUn_Super-Scaffold_100133_4M : AeCom.AE783.model.model.STRG.53733.1.1
  （PAPER_DATA §5.6 用该基因做过 gffread 437 aa 验证，改名后结构仍完整：exon1/exon2…/CDS 全部 Parent 一致）

# comosa · HC/EVM 家族（无需改名，天然合规）
1M : evm.model.1M.1 → Chr1M : evm.model.1M.1
```

完整摘录见 `normalize_test/out/comosa.gff3.excerpt.txt`。

### 3.4 跨物种唯一性：before → after，以及反向验证

| 口径 | 归一化前 | 归一化后 |
|---|---|---|
| 4 物种 mRNA ID 总数 / 去重 | 198,542 / 191,461（**重复 7,081**） | 198,542 / **198,542（重复 0）** |
| 4 物种 gene ID 总数 / 去重 | 198,542 / 191,461（**重复 7,081**） | 198,542 / **198,542（重复 0）** |
| gene+mRNA 合并去重 | — | **397,084 = 198,542×2**（gene/mRNA 命名空间也无碰撞） |

- 全部重复都来自各物种独立编号的 STRG/TAMA 家族；加前缀后彻底消失。
- **反向验证**（证明守卫有效）：先跑一份**不加前缀**的 comosa id-map，再跑**不加前缀**的
  markgrafii 并 `--also-ids` → 脚本 `[ERROR] 与 --also-ids 历史映射存在 2480 个重复 ID`（=1,240
  mRNA + 1,240 gene，与两物种重名实测 1,240 一致），**rc=1**；加前缀后同样命令 rc=0。
- 串行的 4 次 `--also-ids` 断言日志：markgrafii 与 102,406 条历史 ID 无交集；umbellulata 与 196,898
  条无交集；uniaristata 与 296,252 条无交集（`logs/03_gff3_*.log`）。

### 3.5 `check` 汇总断言（4 文件，task-5 实测 3 的脚本侧）

```
$PY scripts/normalize_diploid.py check \
  --gff3 out/comosa.gff3.gz out/markgrafii.gff3.gz out/umbellulata.gff3.gz out/uniaristata.gff3.gz \
  --expect-counts 51203,47246,49677,50416 --expect-unplaced 38,53,1103,66
→ rc=0
  [PASS] 第 1 列 seqid 全部以 'Chr' 开头（15 / 14 / 188 / 15 个 seqid）
  [PASS] mRNA ID 全部以 '.数字' 结尾（51,203 / 47,246 / 49,677 / 50,416 条）
  [PASS] gene/mRNA ID 唯一；gene 数 = mRNA 数
  [PASS] 计数符合预期（4 物种逐项）
  [PASS] ChrUn_ 上基因数符合预期（38 / 53 / 1103 / 66）
  [PASS] 跨文件 mRNA ID 无重复（198,542 条，去重 198,542 条）
  [PASS] 跨文件 gene ID 无重复（198,542 条，去重 198,542 条）
  [SUMMARY] warning: 4（每个文件各 1 条：作者原生 CDS ID 重复，非平台规则）
  [SUMMARY] ALL CHECKS PASSED（4 个 GFF3）
```

---

## 4. 实测 B：assembly_report → FASTA 映射预检（task-5 实测 2）

### 4.1 `fasta --dry-run` 结果（4 份真实报告，`logs/02_fasta_dryrun_*.json`）

| 指标 | comosa | markgrafii | umbellulata | uniaristata | 期望值 |
|---|---|---|---|---|---|
| GCA | GCA_052815735.2 | GCA_052815875.1 | GCA_060308565.1 | GCA_052815765.1 | §4.1 |
| 映射行数（mapping.tsv 数据行） | **17** | **24** | **250** | **21** | 17/24/250/21 ✅ |
| assembled-molecule | **7** | **7** | **7** | **7** | 7 ✅ |
| unplaced/其它 | 10 | 17 | 243 | 14 | ✅ |
| 序列总长（bp） | 4,407,741,597 | 3,577,170,360 | 4,268,089,219 | 4,475,943,907 | 与 §4.1 完全一致 ✅ |

映射表示例（`out/comosa.fa_mapping.tsv`）：

```
#new_name                       old_name             sequence_role        sequence_name
Chr1M                           CM127985.1           assembled-molecule   1M
ChrUn_Super-Scaffold_100133_4M  JBHEGE020000008.1    unplaced-scaffold    Super-Scaffold_100133_4M
ChrUn_Super-Scaffold_846_5M     JBHEGE020000017.1    unplaced-scaffold    Super-Scaffold_846_5M
```

### 4.2 FASTA 子命令真实数据路径

因本机不下载 4.7 GB FASTA，做了两层替代验证（fixtures 已留存，可复现）：

1. **报告 → 映射表 → 全 17/24/250/21 条目标名生成**（上表，`--dry-run`）；
2. **NCBI efetch 真实序列片段**（`fixtures/efetch_*.fna`，真实 FASTA 头 `>CM127985.1 …`、
   `>JBHEGE020000008.1 …`）→ 按 NCBI genomic FASTA 的真实头格式重写后跑 `fasta --partial`，
   应得 `Chr1M` / `ChrUn_Super-Scaffold_100133_4M` 且描述保留。

> 服务器侧对真实 `*_genomic.fna.gz` 整跑时，脚本会自动断言替换率 100%、序列数 = report 行数、
> 总长 = report 总长、无缺失/多余序列名；任一不满足 `rc=1`。§7 给出命令。

### 4.3 ⚠ 数据修正：markgrafii `assembly_report.txt` 的 md5 笔误

实测下载并对 NCBI FTP `md5checksums.txt` 校验（`normalize_test/reports/assembly_report_md5.tsv`）：

| GCA | 实测 = NCBI 官方 | PAPER_DATA.md §4.1 记录 | 结论 |
|---|---|---|---|
| GCA_052815735.2 | `0dec99d5610b511856625b83e23f6b6d` | 同 | 一致 |
| **GCA_052815875.1** | **`4e31f0cad2191e46e670e94fc0e8deb9`** | `…e8deb5` | **PAPER_DATA 末位笔误**（b5→b9），以 NCBI 实测为准 |
| GCA_060308565.1 | `f005dec95b7e253ab9beb8e9033f135a` | 同 | 一致 |
| GCA_052815765.1 | `0abc640548aa96a5de13c50075b21a0a` | 同 | 一致 |

四份报告原件已存入 `normalize_test/reports/`（含上述 md5 对照表），供 G1 直接复用。

---

## 5. 实测 C：平台 `check_genome_files.py` 逻辑等价断言（task-5 实测 3）

平台脚本原件 `/tmp/wm_server/check_genome_files.py` 在验收时已被清理（`/tmp` 被清理），
因此将其 `check_gff3`（以及 `check_fasta_headers`/`check_fasta_ids`）**逐字存档**为
`normalize_test/platform_equiv_check.py`（逻辑零改动，来源 md5 见 WORKFLOW_GAP §1：
`d774445172714d0d6b9127d4a21cc2a0`；原脚本 `main()` 需要四件套齐全才能整跑，本任务无 `.fa`，
故按 task-5 建议只调用函数）。

```
$PY normalize_test/platform_equiv_check.py out/comosa.gff3.gz out/markgrafii.gff3.gz \
    out/umbellulata.gff3.gz out/uniaristata.gff3.gz
→ [PASS] comosa (check_gff3) … [PASS] uniaristata (check_gff3)
→ PLATFORM_EQUIV_RESULT: PASS   rc=0
```

即平台 G2 闸门对 `.gff3` 的两条硬性规则（第 1 列 `Chr` 开头、mRNA `ID=` 以 `.数字` 结尾）
在 4 个输出上 **0 错误**。`.fa/.cds/.pep` 的等价检查函数已一并存档，服务器生成四件套后可直接跑。

---

## 6. 实测 D：`pep` 子命令（comosa 全量冒烟，task-5 D 选做）

```bash
$PY scripts/normalize_diploid.py pep \
  --pep $Z/Ae.comosa_genes_HC_LC.fasta.gz --out /tmp/comosa.pep \
  --id-map $T/out/comosa.idmap.tsv.gz --stop-mode x
```

| 指标 | 结果 |
|---|---|
| 序列数 | 51,203 → 51,203（无丢失） |
| 精确 ID 映射命中 | **51,203 / 51,203**（`--id-map` 来自 gff3 子命令） |
| 输出 ID 集合 vs GFF mRNA ID 集合 | **完全相等（set_equal=True）**，0 重复，全部 `.数字` 结尾 |
| 终止符清理 | 替换 `.`/`*` 共 156,375 个 / 涉及 49,335 条序列（`--stop-mode x` 换为 `X` 保长度） |
| 输出序列行含 `.`/`*` | 0 |
| 输出大小/md5（未留存，21.1 MB） | 21,122,264 B / `229f4d1a8ab82b31091410df167538cd` |

> 生产建议：`.pep` 优先用 `gffread -y` 产物（ID 天然与归一化 GFF 一致），再用本子命令清终止符；
> 作者 Zenodo 蛋白 FASTA 只作交叉验证（本任务即用其验证了 ID 映射闭合性）。

---

## 7. 服务器侧执行清单（G1→G2，可直接照抄；未在本机执行）

```bash
PY=/usr/bin/python3
NORM=/var/www/data/masw_data/_prep/normalize_diploid.py   # scp 自仓库 scripts/，md5 入库
BASE=/var/www/data/masw_data; D=$BASE/<PLOIDY>_<MYTAG>; RAW=$D/raw; GR=/home/fei/mambaforge/envs/new_env/bin/gffread

# 0) 脚本部署与留痕（仓库 → _prep）
md5sum $NORM   # 记录进 provenance.txt

# 1) 下载 4 个基因组 FASTA + assembly_report，并按 §4.3 md5 校验（示例 comosa）
curl -fL -o $RAW/genomic.fna.gz https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/052/815/735/<ASMv2>/<ASMv2>_genomic.fna.gz
curl -fL -o $RAW/assembly_report.txt 同目录/<ASMv2>_assembly_report.txt
md5sum $RAW/*; # 期望：comosa 38b8436f9c4eb360a066a1c79f1a122a / markgrafii 2a55e0ca2d74109c63c84dcb6d6a077a
              #       umbellulata 1766c56e9ed9f2d6bcf292925a6628bb / uniaristata b9b855678d7beba1cdd58f7ed89123eb（§4.1）

# 2) G1 FASTA 归一化（Chr*/ChrUn_*，写 mapping.tsv；自动断言替换率/序列数/总长）
$PY $NORM fasta --fasta $RAW/genomic.fna.gz --assembly-report $RAW/assembly_report.txt \
  --out $D/${MYTAG}.fa --mapping $D/${MYTAG}.fa.mapping.tsv
grep -c '^>' $D/${MYTAG}.fa            # 期望 17/24/250/21（4 物种）
grep '^>' $D/${MYTAG}.fa | grep -cE '^>Chr[1-7][MCUN]$'   # 期望 7
awk '{s+=$2} END{print s}' <(samtools faidx $D/${MYTAG}.fa && cat $D/${MYTAG}.fa.fai)  # 期望总长见 §4.1

# 3) G1 注释归一化（跨物种前缀；后 3 个物种逐一累加 --also-ids）
$PY $NORM gff3 --gff3 $RAW/genes_HC_LC.gff3.gz --assembly-report $RAW/assembly_report.txt \
  --out $D/${MYTAG}.gff3 --mapping $D/${MYTAG}.gff3.seqid_mapping.tsv \
  --id-prefix "<AeCom.AE783.|AeMar.EKC105.|AeUmb.AE740.|AeUna.AE680.>" \
  --id-map $D/${MYTAG}.idmap.tsv.gz \
  --also-ids <其他物种>.idmap.tsv.gz      # 断言跨物种重复 ID = 0
grep -c $'\tmRNA\t' $D/${MYTAG}.gff3     # 期望 51,203/47,246/49,677/50,416

# 4) 生成 CDS/PEP（Zenodo 无 CDS，必须自建）
$GR -E -g $D/${MYTAG}.fa -x $D/${MYTAG}.cds -y $D/${MYTAG}.pep $D/${MYTAG}.gff3 2> $D/gffread.stderr
# （可选）gffread 产物 pep 再清一次终止符：
$PY $NORM pep --pep $D/${MYTAG}.pep --out $D/${MYTAG}.pep.clean --id-map $D/${MYTAG}.idmap.tsv.gz && mv ...

# 5) G2 闸门：本脚本 check + 平台 check_genome_files
$PY $NORM check --dir $D
( cd $D && $PY /var/www/html/Script/check_genome_files.py ${MYTAG}; echo rc=$? )   # 必须 rc=0

# 6) 交叉验证：gffread pep vs Zenodo 蛋白（PAPER_DATA §5.6 方法）
#    条数应相等；ID 经 idmap 对应；序列差异应仅来自终止符 `.`/`*`（建议替换为 X 后全量比较）
```

> 注意：`check_genome_files.py` 的 `.fa` 检查会跳过含 `contig/scaffold` 字样的头（本脚本 check 更严格：
> 全部要求 `Chr` 开头）；`ChrUn_*` 头**不要**加 `_${MYTAG}` 后缀（流水线 Step 1 已特殊处理）。

---

## 8. 剩余风险 / 未验证项 / 决策记录

| # | 项 | 状态 / 处置 |
|---|---|---|
| R1 | **4×~4.7 GB 基因组 FASTA 未下载** | `fasta` 子命令的「真实 FASTA 整跑」未在本机执行；已用 assembly_report 预检（17/24/250/21 行、assembled=7、总长一致）+ efetch 真实头片段覆盖映射逻辑。**服务器 G1 首跑时即完成最终验证**（断言替换率 100%/序列数/总长，失败即 rc=1，不会静默出错） |
| R2 | **gffread 未在本任务重跑** | PAPER_DATA §5.6 已用「NCBI FASTA + Zenodo GFF」对 4 物种 17 个位点做过 gffread 端到端验证（17/17 MATCH，含本批 scaffold STRG 基因 437 aa），本任务归一化不改坐标、只改 seqid/ID，且已断言坐标未越界、Parent 全解析，风险低。服务器 G2 首次跑 gffread 时验证 pep 条数 = mRNA 数即可 |
| R3 | **CDS ID 重复（作者原生）** | comosa/markgrafii/umbellulata/uniaristata 分别 128,939 / 125,251 / 127,876 / 125,598 个重复（每转录本共用一个 `cds.<mRNA>` ID）。平台只校验 mRNA ID；gffread 按 `Parent` 解析不受影响。**不擅自改**（改 CDS ID 会偏离作者注释；如平台后续需要 GFF3 严格合法，可再加 `--dedupe-derived-ids`） |
| R4 | **内部终止符（comosa 6,573 条帧移模型）** | pep 子命令默认 `--stop-mode x`（`.`/`*`→`X`，保长度，BLAST 可接受）；若平台要求纯 AA，可 `--stop-mode drop`。内部终止符属注释质量问题，记录 provenance、不剔除模型（否则基因数差 6.5k+） |
| R5 | **跨物种重复口径** | 本次 4 物种全量实测重复 7,081（198,542→191,461）；PAPER_BASELINE 的 3,457 为 3 物种口径，WORKFLOW_GAP 的 6,401 口径不同。以本次可复现实测为准；归一化后为 0 |
| R6 | **前缀方案未最终定名** | 本任务用 `AeCom.AE783.` 等（与 task 验收示例一致）；最终以 G0 `name_plan.json`/registry 命名为准，脚本 `--id-prefix` 任意字符串即可，重跑幂等 |
| R7 | **TE GFF（EDTA）未纳入本脚本实测** | 4 个 TE GFF 的 seqid 规则不同（comosa 裸数字 `1..7`+纯数字 token；umbellulata/uniaristata 缩写 `S_S_*`；umbellulata `S_S_73_2` 不在 NCBI）。脚本已预留 `--seqid-map`（额外映射 TSV）可复用；TE 属于 JBrowse 轨道阶段（D14），建议届时用 `--seqid-map` + 同一套 Chr 命名 |
| R8 | **平台 check_genome_files 原脚本已从 /tmp 清理** | 已把 3 个检查函数逐字存档为 `normalize_test/platform_equiv_check.py` 并跑出 4/4 PASS；服务器侧仍以 `/var/www/html/Script/check_genome_files.py` 为准（§7 步骤 5） |
| R9 | **存储** | 4 个归一化 GFF 未压缩为 ~168 MB，故实测产物以 `.gff3.gz` 存放（18.45 MB）+ id-map `.tsv.gz`（2.4 MB）+ 小映射表，总计 20 MB（符合 task-5「换压缩」要求）。服务器生产用未压缩 `.gff3`（gffread/JBrowse 直接读） |
| R10 | **脚本版本与兼容性** | v1.0.0，纯 stdlib，Python 3.7+ 实测通过（本机 3.7.3）；服务器 `/usr/bin/python3`（3.8+）兼容。mRNA 规则以 `mRNA` 为主、兼容 `transcript` 类型；仅改 `ID/Parent/Derives_from/Name` 四类引用 |

---

## 9. 产物清单（`normalize_test/out/`，md5 见 `logs/09_artifacts_md5.txt`）

| 文件 | 大小 | md5 | 说明 |
|---|---|---|---|
| `comosa.gff3.gz` | 4,713,411 | `d520cc501d5ae996e6face11fd60ad2b` | 归一化 GFF3 |
| `markgrafii.gff3.gz` | 4,464,548 | `ab822efc6552180eabdf3567469de9a8` | 同上（含 task 验收示例改名） |
| `umbellulata.gff3.gz` | 4,660,974 | `e71259d7165751607e48eb757d60e39c` | 同上（188 seqid） |
| `uniaristata.gff3.gz` | 4,620,690 | `042128b6eae084a2f0ddc5a04cda85f9` | 同上 |
| `*.gff3.seqid_mapping.tsv` | 0.7–9.6 KB | — | seqid 原名→新名（含 role/feature/gene 数） |
| `*.idmap.tsv.gz` | 574–620 KB | — | gene/mRNA 原名→新名（`--also-ids`/pep 用） |
| `*.fa_mapping.tsv` | 1.4–18.7 KB | — | FASTA 登录号→Chr 映射（4 份 assembly_report 预检） |
| `comosa.gff3.excerpt.txt` | 2,033 | — | 归一化样例摘录（报告引用） |

其他证据：`reports/`（4 份 assembly_report 原件 + md5 对照）、`logs/`（02–09 全部命令输出）、
`fixtures/`（NCBI efetch 真实序列片段 3 个）。

## 10. 复现

```bash
T=docs/plans/aegilops4_2026-11/normalize_test
cat $T/logs/02_fasta_dryrun_*.json          # FASTA 映射预检（17/24/250/21）
cat $T/logs/03_gff3_*.log                   # 4 物种归一化（含 also-ids 断言）
cat $T/logs/05_check_4species.log           # check 4 文件 ALL PASSED
cat $T/logs/06_platform_equiv_check.log     # 平台 check_gff3 等价 4/4 PASS
cat $T/logs/07_pep_comosa.log               # pep 全量冒烟
```

脚本本身：`scripts/normalize_diploid.py --help`（四个子命令各有 `--help` 与示例）。
