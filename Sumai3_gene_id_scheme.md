# Sumai3 基因 ID 方案（中国春 02G 风格）

> 日期：2026-10-29
> 状态：**已确认**（按 2026-10-29 22:41 用户决定执行）
> 关联：`Sumai3_annotation_update_plan.md`（D1 决策项、§6.1 归一化规则）

## 最终决定（2026-10-29 22:41）

- **基因 ID 格式**：`TraesSM3_<chr>01G<6 位数字>`
  - 例：`TraesSM3_1A01G000100`
  - `<chr>` = `1A…7D`；`01G` 按用户给定原样保留（如果 `01G` 是 `02G` 的笔误，请尽快说，归一化后改回会牵动全部 ID）
- **转录本 ID**：`<geneID>.<n>`，例 `TraesSM3_1A01G000100.1`
- **假基因**：基因 ID 追加 `LC`，例 `TraesSM3_1A01G000300LC`；37,573 条 `pseudo=true` 的 mRNA 转为 `pseudogenic_transcript`（D2 确认）
- **旧 ID 不保留**：GFF/站点文件中不写 `SUM3_…` 旧 ID；仅内部保留一份 mapping 供 QA，不发布/不上传
- **编号**：每条染色体的 `gene`+`pseudogene` 位点按坐标排序，序号从 `000100` 起、步长 `100`；转录本按基因内坐标 `.1/.2/...`

---

## 1. 目标

把 EGAPx 注释里的 `SUM3_000001` 这类 ID，改成**类似中国春 RefSeq 02G 的形式**，同时满足 WheatOmics 站点和下游 BLAST/JBrowse/MySQL 的要求。

中国春 02G 的典型 ID（站内 `Genefunc_AABBDD_Chinese_Spring2_1_table` 的 `ChineseSpring02G` 列实测）：

```
TraesCS1A02G000100
TraesCS1A02G000200
TraesCS1A02G000300LC
TraesCS1A02G000100.1      # 转录本：基因 ID + .1
```

规则概括：

- 主体：`TraesCS<chr>02G<6 位数字>`；
- 数字通常按注释顺序递增（常见步长 100）；
- `LC` = low-confidence 后缀（可选）；
- 转录本在基因 ID 后加 `.1/.2/...`；
- 基因 ID 不带版本后缀，转录本带 `.数字`。

站点基因功能表的 `Gene` 列实际存的是**转录本 ID**（如 `TraesCS1A03G0000200.1`），另有 `ChineseSpring02G` 列存真实 CS 02G 同源映射。也就是说：

- **基因表主键/显示用 ID** → 我们要生成的转录本 ID；
- **`ChineseSpring02G` 列** → 由 02G miniprot 管线计算出的真实 CS 同源 ID，与本方案要改的“基因 ID”是两回事，不能混用。

站点约束（已核对 `app/core/security.py`、`check_genome_files.py`）：

- `GENE_ID_PATTERN = ^[A-Za-z0-9_.:-]+$`，允许 `TraesSM3_1A01G000100`、`...LC.1`；
- GFF 的 mRNA `ID=` 必须以 `.数字` 结尾；
- CDS/PEP 的 `>` 头 ID 也以 `.数字` 结尾，pep 序列行不能含 `.`；
- Genefunc 表行数 = mRNA 数（按 D2 方案为 151,286）。

---

## 2. 关键设计问题：前缀要不要用 `TraesCS`？

中国春真实 ID 就是 `TraesCS1A02G000100`。如果 Sumai3 也用完全相同的 `TraesCS…`，会出现：

| 风险 | 说明 |
|---|---|
| **与实际中国春 ID 冲突** | `TraesCS1A02G000100` 在 CS 注释里已经存在；站内全局搜索/`all_gene` BLAST 会出现同名不同基因 |
| **用户误解** | 用户可能以为是 CS 的同一个基因，但坐标/序列/功能都不同 |
| **BLAST 聚合库歧义** | `all_gene` = 所有基因组的 CDS 聚合 BLAST 库；同名 ID 会让 `blastdbcmd -entry` / 结果展示歧义 |
| **与 `ChineseSpring02G` 列混淆** | 我们的 `ChineseSpring02G` 列是真实 CS 同源映射；基因 ID 若也长成 CS 样，容易混 |

因此方案分两类：**“格式像 CS”** 和 **“前缀也像 CS”**。

---

## 3. 候选方案

| 方案 | 基因 ID 示例 | 转录本示例 | 优点 | 缺点 |
|---|---|---|---|---|
| **S0 现状** | `SUM3_000001` | `SUM3_000001.1` | 简单、无冲突 | 不像 CS 02G |
| **S1 完全 CS 样式（从 000100 起）** | `TraesCS1A02G000100` | `TraesCS1A02G000100.1` | 最像 CS；正则/用户习惯完全兼容 | **与真实 CS 基因同名**；全局搜索/BLAST 歧义 |
| **S2 CS 样式 + 独立号段** | `TraesCS1A02G900100` | `TraesCS1A02G900100.1` | 保留 `TraesCS…02G` 外观，号段 900000+ 避免与 CS 前 1 万个基因冲突 | 仍可能被误认为 CS ID；号段不自然 |
| **S5 最终采用（`TraesSM3_` + `01G`）** | `TraesSM3_1A01G000100` | `TraesSM3_1A01G000100.1` | 唯一、不会与 CS/其他基因组冲突；满足 02G 风格；站内正则完全接受 | 前缀不是 `TraesCS`，与真实 CS 不同 |
| **S4 材料名显式前缀** | `Sumai3CS1A02G000100` | `Sumai3CS1A02G000100.1` | 最明确、可读性最好 | 最长；不像 CS 的 `TraesCS` 前缀 |

### 最终采用

**S5：`TraesSM3_<chr>01G<6 位数字>`**（2026-10-29 22:41 确认），理由：

1. 站点工具只做 `[A-Za-z0-9_.:-]+` 校验，`TraesSM3_…01G…` 与 `TraesCS…02G…` 一样可用；
2. 不会与真实中国春 02G ID 冲突，也不会污染 `all_gene`/`all_protein` 聚合 BLAST 库；
3. 用户一眼能看出这是 Sumai3 的“02G 风格”ID；
4. 与 `ChineseSpring02G`（真实同源映射列）在语义上区分清楚。

如果你明确希望 **ID 前缀也用 `TraesCS`**（例如给外部脚本/用户习惯），建议采用 **S2**：`TraesCS<chr>02G9xxxxx`，从 `900100` 起编号，避开真实 CS 的号段；同时需要在 registry `notes` 里说明“Sumai3 合成 ID，不是 CS 同源 ID”。

---

## 4. 最终方案 S5 的编号算法

### 4.1 处理范围

- 只对 21 条染色体（`Chr1A…Chr7D`）编号；本注释无 `ChrUn`/scaffold；
- 参与编号的对象：GFF 中所有 `gene` 和 `pseudogene` 特征（共 **165,398** 个位点）；
  - `gene`（protein_coding / lncRNA / misc_RNA 等）→ 正常 ID；
  - `pseudogene` → 基因 ID 追加 `LC` 后缀（推荐；如不想加可关闭）；
- 转录本：每个基因的所有 RNA 特征（mRNA / lncRNA / transcript / 假基因 mRNA）按坐标顺序编号 `.1/.2/...`。

### 4.2 排序与编号

按染色体顺序（1A, 1B, 1D, 2A…7D）逐个处理：

1. 取该染色体所有 `gene`/`pseudogene` 特征，按 `start`、`end`、旧基因 ID 排序；
2. 序号从 **100** 开始，步长 **100**：`000100, 000200, 000300, …`；
3. 基因 ID = `TraesSM3` + 染色体（如 `1A`）+ `01G` + `%06d`(序号) + （假基因 ? `LC` : ``）；
4. 转录本 ID = 基因 ID + `.` + 该基因内转录本序号（按坐标排序，从 1 开始）。

每染色体最多 9,673 个位点（实测），`9,673 × 100 = 967,300`，6 位数字足够；如未来注释超过 9,999 个位点/染色体，再升级为 7 位。

### 4.3 示例（按当前 GFF 实测，Chr1A 前 6 个位点）

| 旧 ID | 类型 | 新基因 ID | 新转录本 ID |
|---|---|---|---|
| `SUM3_000001` | gene/lncRNA | `TraesSM3_1A01G000100` | `TraesSM3_1A01G000100.1` |
| `SUM3_000002` | gene/lncRNA | `TraesSM3_1A01G000200` | `TraesSM3_1A01G000200.1` |
| `SUM3_000003` | gene/lncRNA | `TraesSM3_1A01G000300` | `TraesSM3_1A01G000300.1` |
| `SUM3_000004` | gene/lncRNA | `TraesSM3_1A01G000400` | `TraesSM3_1A01G000400.1` |
| `SUM3_000005` | gene/lncRNA | `TraesSM3_1A01G000500` | `TraesSM3_1A01G000500.1` |
| `SUM3_000006` | gene/lncRNA | `TraesSM3_1A01G000600` | `TraesSM3_1A01G000600.1` |

（注：Chr1A 最前面恰好都是 lncRNA；再往后才出现 protein_coding 和 pseudogene。编号按坐标，不按基因类型。）

蛋白编码基因示例（形式）：

```
基因：    TraesSM3_2B01G012300
转录本：  TraesSM3_2B01G012300.1
          TraesSM3_2B01G012300.2
假基因：  TraesSM3_2D01G004500LC
转录本：  TraesSM3_2D01G004500LC.1   # 转成 pseudogenic_transcript，不进 Genefunc/BLAST
```

### 4.4 多转录本、假基因、ncRNA

| 情况 | 处理 |
|---|---|
| 一个基因多个 mRNA | 按坐标排序 `.1/.2/...`；只有带 CDS 的才是 `mRNA`，进 Genefunc/BLAST |
| 假基因 mRNA（`pseudo=true`，无 CDS） | 基因 ID 加 `LC`；特征类型改为 `pseudogenic_transcript`（保留 GFF 结构，不进功能表/BLAST） |
| lncRNA / transcript 基因 | 基因 ID 正常（不加 LC），RNA 类型保留，转录本 ID `.n`；不进 Genefunc/BLAST，但保留在 GFF/JBrowse |
| 旧 ID 追溯 | GFF 保留 `locus_tag=SUM3_xxxxxx`，并生成 `gene_id_mapping.tsv`（旧→新、染色体、坐标、类型） |

### 4.5 属性改写

- `gene`/`pseudogene`：`ID=<geneID>`，`Name=<geneID>`，`locus_tag=<旧 SUM3 ID>`（保留追溯），其余 `gene_biotype`/`description` 保留；
- `mRNA`/`lncRNA`/`transcript`/`pseudogenic_transcript`：`ID=<transcriptID>`，`Parent=<geneID>`，`Name`/`locus_tag` 保留旧值；
- `CDS`：`ID=cds-<transcriptID>`（同一转录本多个片段同 ID），`Parent=<transcriptID>`；
- `exon`：`ID=exon-<transcriptID>-<n>`，`Parent=<transcriptID>`；
- `Derives_from`、`orig_transcript_id` 等属性如含旧 ID，做对应替换；
- `##sequence-region` 用 `Chr1A_Sumai3…`。

---

## 5. 与站点/下游的衔接

1. **GFF**：`Sumai3.gff3` 用新 ID；mRNA ID 151,286 条，全部 `.数字` 结尾；
2. **CDS/PEP**：`Sumai3.cds` / `Sumai3.pep` 的头 ID = 新转录本 ID（`TraesSM3_…01G…100.1`）；151,286 条；
3. **MySQL Genefunc**：`Gene` 列 = 新转录本 ID；`ChineseSpring02G` 列由 02G 管线生成，保持真实 CS 同源映射；
4. **BLAST**：`AABBDD_Sumai3.add_Description.cds/.pep` 的 ID = 新转录本 ID；`all_gene`/`all_protein` 聚合库使用同一套 ID，无跨基因组冲突；
5. **JBrowse**：`all_gene` 轨道 ID/Name = 新 ID；旧 ID 可通过 `locus_tag`/mapping 表追溯；
6. **下载文件**：GFF3/CDS/PEP 都用新 ID；另外提供 `gene_id_mapping.tsv` 和原版 EGAPx 文件（保留旧 ID）供追溯。

---

## 6. 实现与验证

### 6.1 实现

在现有归一化脚本（`normalize_egapx_gff.py`）第 2 步（ID 分配）替换为上述算法：

```text
输入：Sumai3_EGAPx.gff3 + seqid_mapping_CM_to_Chr_Sumai3.tsv
输出：Sumai3.gff3 + gene_id_mapping.tsv + normalize_summary.txt
```

### 6.2 验证（必须全部通过）

- 165,398 个 gene/pseudogene 的**新基因 ID 唯一**；
- 188,859 个 RNA 的**新转录本 ID 唯一**；
- 151,286 条 `mRNA` 的 ID 全部 `.数字` 结尾；
- 所有 mRNA/CDS/exon 的 `Parent` 都能解析；
- `check_annotation_compat.py` rc=0；
- `check_genome_files.py` rc=0（cds/pep 头 ID 也需 `.数字`）；
- gffread 后 CDS/PEP 条数 = 151,286；
- 抽样：`TraesSM3_1A01G000100` 在 GFF/JBrowse/Genefunc 表中一致；
- 跨库检查：`all_gene`/`all_protein` 中无同名冲突（与 `TraesCS…` 不重名）。

---

## 7. 已确认并开始执行

- **前缀/格式**：`TraesSM3_<chr>01G<6 位数字>`（2026-10-29 确认；`01G` 按用户原样保留）
- **假基因**：加 `LC`；37,573 条 `pseudo=true` 的 mRNA 转 `pseudogenic_transcript`
- **编号范围**：所有 `gene` + `pseudogene` 位点，按染色体坐标排序，从 `000100` 起、步长 100
- **旧 ID**：不保留在 GFF/站点文件；仅 Ma 上内部 `gene_id_mapping.tsv` 供 QA

归一化脚本已在 Ma 上执行并通过计数校验（详见 `normalize_summary.json` / `gene_id_mapping.tsv`）；下一步按 `Sumai3_annotation_update_plan.md` 执行 Phase 1/2。
