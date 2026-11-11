# 基因 ID 规范化与重编号报告（4 个二倍体 Aegilops）

> 日期：2026-11-11 ｜ 决策：用户确认「每染色体上的 ID 以 100 为单位」+ 保留 `.r1.` 注释版本标签
> 工具：`scripts/renumber_gff_ids.py`（新增）+ `scripts/normalize_diploid.py`（`--keep-author-ids` 模式）
> 实测数据：`docs/plans/aegilops4_2026-11/normalize_test/{step1,reid}/`（4 个真实 Zenodo GFF 全量）

## 0. 结论

| 项 | 结果 |
|---|---|
| 规则 | `gene = <物种.材料.r1.><染色体>G<6位号>`，`mRNA = gene + ".1"`；每染色体按坐标从 `000100` 起、每 **100** 递增 |
| 4 物种全量重编号 | ✅ gene/mRNA 计数全部保全：51,203 / 47,246 / 49,677 / 50,416 |
| 每条染色体 | ✅ 从 `000100` 起严格 +100，且编号顺序 = 基因坐标顺序（实测 28 条染色体） |
| 未定位序列 | ✅ 跨所有 `ChrUn_*` 统一编号（`UnG000100 …`），38/53/1103/66 个基因一个不丢 |
| 全局唯一 | ✅ 4 物种 mRNA ID 共 198,542 个，**重复 = 0**（前缀区分物种） |
| 平台规则 | ✅ 100% mRNA ID 以 `.数字` 结尾；Parent 引用 0 条未解析；`original_id` 属性 198,542+198,542 条 |
| 可回溯 | ✅ `original_id=` 保留作者原始 ID（EVM/STRG）；`idmap.tsv` 提供 原始ID→新ID |

## 1. 最终 ID 规则

```
gene  ID = <prefix><chr-token>G<6-digit>        例：AeCom.AE783.r1.1MG000100
mRNA  ID = gene ID + "." + 序号                 例：AeCom.AE783.r1.1MG000100.1
未定位  = <prefix>UnG<6-digit>                  例：AeCom.AE783.r1.UnG000100
```

- 前缀 `<物种缩写>.<登录号>.r1.`：`AeCom.AE783.r1.` / `AeMar.EKC105.r1.` / `AeUmb.AE740.r1.` / `AeUna.AE680.r1.`（`r1` = 注释 release 1，与平台现有 Aegilops 条目同风格）；
- 每条染色体独立从 `--step`（100）开始，按基因**起始坐标升序**编号；
- 未定位序列跨 scaffold 统一编号（按 seqid + 坐标排序）；
- 序号位数 6（实测最大单染色体基因数 8,332 → 最大编号 `833,200`，6 位容量 9,999 个基因足够）。

## 2. 4 物种样例

| 物种 | 作者原始 ID（保留在 `original_id`） | 规范化后 gene / mRNA |
|---|---|---|
| comosa（chr1M 第 1 个） | `evm.TU.1M.1` / `evm.model.1M.1` | `AeCom.AE783.r1.1MG000100` / `…1MG000100.1` |
| comosa（chr1M 最后） | — | `AeCom.AE783.r1.1MG672200` / `…1MG672200.1` |
| markgrafii（chr1C 第 1 个，LC/STRG） | `gene.model.STRG.315.1.p1` / `model.model.STRG.315.1.p1` | `AeMar.EKC105.r1.1CG000100` / `…1CG000100.1` |
| markgrafii（chr1C 最后） | — | `AeMar.EKC105.r1.1CG647100` |
| umbellulata（chr1U） | `evm.model.1U.1` | `AeUmb.AE740.r1.1UG000100` / `…1UG000100.1` |
| uniaristata（chr1N） | `evm.model.1N.1` | `AeUna.AE680.r1.1NG000100` / `…1NG000100.1` |
| comosa 未定位 | `evm.model.Super-Scaffold_100133_4M.1` | `AeCom.AE783.r1.UnG000100` / `…UnG000100.1` |
| umbellulata 未定位（181 scaffold / 1103 基因） | — | `AeUmb.AE740.r1.UnG000100 … UnG110300` |

GFF 行样例（markgrafii，作者注释 → 重编号后）：

```gff
# 原始（seqid 已改名前）
1C  EVM  gene  357751  358650  .  +  .  ID=gene.model.STRG.315.1.p1;Name=EVM prediction
# 重编号后
Chr1C  EVM  gene  357751  358650  .  +  .  ID=AeMar.EKC105.r1.1CG000100;Name=EVM prediction;original_id=gene.model.STRG.315.1.p1
Chr1C  EVM  mRNA  357751  358650  .  +  .  ID=AeMar.EKC105.r1.1CG000100.1;Parent=AeMar.EKC105.r1.1CG000100;Name=EVM prediction;original_id=model.model.STRG.315.1.p1
Chr1C  EVM  CDS   357751  358349  .  +  .  ID=cds.AeMar.EKC105.r1.1CG000100.1;Parent=AeMar.EKC105.r1.1CG000100.1
```

- `Name=` 保留作者描述（如 `EVM prediction 1M.1`），不参与平台查询；
- exon/CDS/UTR 等派生 ID 同步替换父 ID（平台不校验派生 ID 唯一性，gffread 用 `Parent` 解析）；
- HC/LC 信息不再编码进 ID，但 `original_id` 可区分（`evm.*` = HC；`model.model.STRG.*` / `model.model.evm.*` = LC），且计数分别可查。

## 3. 生产执行顺序（A2 归一化）

```bash
cd /var/www/data/masw_data/<DS>
PY=python3
# ① seqid 归一化（保留作者 ID，供下一步留痕）
$PY /var/www/data/masw_data/_prep/normalize_diploid.py gff3 \
  --gff3 Ae.<sp>_genes_HC_LC.gff3.gz --assembly-report GCA_*_assembly_report.txt \
  --keep-author-ids --out step1.gff3.gz --mapping step1.seqid_map.tsv
# ② 按染色体重编号（平台风格；100 步）
$PY /var/www/data/masw_data/_prep/renumber_gff_ids.py \
  --gff3 step1.gff3.gz --out <MYTAG>.gff3.gz \
  --id-prefix "AeCom.AE783.r1." --id-map <MYTAG>.idmap.tsv
# ③ FASTA 头映射（assembly_report GenBank 登录号 → Chr*）
$PY /var/www/data/masw_data/_prep/normalize_diploid.py fasta \
  --fasta GCA_*_genomic.fna.gz --assembly-report GCA_*_assembly_report.txt --out <MYTAG>.fa
# ④ gffread 生成 CDS/PEP（ID 自动继承 mRNA ID）→ ⑤ 清 pep 终止符 → ⑥ 平台质检
gffread -E -g <MYTAG>.fa -x <MYTAG>.cds -y <MYTAG>.pep <MYTAG>.gff3
$PY /var/www/data/masw_data/_prep/normalize_diploid.py pep --pep <MYTAG>.pep --out <MYTAG>.pep
$PY /var/www/html/Script/check_genome_files.py <MYTAG>
```

## 4. 验收断言（可直接写进 G1/G2 闸门）

```bash
$PY scripts/renumber_gff_ids.py --check --gff3 <MYTAG>.gff3.gz --id-prefix "AeCom.AE783.r1."
# 期望：[PASS] 重编号规则全部通过
```

检查项：ID 模式（`prefix` + 染色体 + `G` + 6 位）；每染色体从 `100` 起严格 +100 且与坐标顺序一致；ChrUn 全局连续；mRNA ID 全 `.数字` 结尾；gene/mRNA ID 唯一；计数 = 51,203 / 47,246 / 49,677 / 50,416。

## 5. 实测记录

| 物种 | gene=mRNA | 染色体 | 未定位 gene / scaffold | chr1 首/末 ID |
|---|---|---|---|---|
| comosa | 51,203 | 7 | 38 / 8 | `AeCom.AE783.r1.1MG000100 … 1MG672200` |
| markgrafii | 47,246 | 7 | 53 / 7 | `AeMar.EKC105.r1.1CG000100 … 1CG647100` |
| umbellulata | 49,677 | 7 | 1,103 / 181 | `AeUmb.AE740.r1.1UG000100 … 1UG523000` |
| uniaristata | 50,416 | 7 | 66 / 8 | `AeUna.AE680.r1.1NG000100 … 1NG516500` |

跨 4 物种 mRNA ID：198,542 个，唯一 198,542，重复 0；Parent 未解析 0；`original_id` 属性 102,406+94,492+99,354+100,832 条。

## 6. 备注

- 已确认 `.r1.` 为**注释版本**（release 1），非组装版本；comosa 组装 v2 不影响 ID 中的 r1。
- 若未来作者发布新注释（Zenodo 新版本），可用 `r2` 前缀导入为新一版基因集，ID 不冲突。
- 若想改风格（去掉 `.r1.`、7 位序号、或 HC/LC 编码进 ID），只需改 `--id-prefix` / `--digits` / 自定义模板，重跑本脚本即可。
