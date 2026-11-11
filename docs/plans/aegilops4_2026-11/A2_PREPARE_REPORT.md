# A2 归一化执行报告（4 个二倍体 Aegilops，生产机）

> 日期：2026-11-11 22:55–23:01 CST ｜ 执行：Lead（经 lab-server 隧道在 `wheatomics` 节点）
> 触发：用户确认「装到服务器 `_prep/` 并开始跑 A2 归一化；先 comosa 端到端，再批量其余 3 个」
> 工具（已安装到 `/var/www/data/masw_data/_prep/`，md5 与本机一致）：
> - `normalize_diploid.py`（`e2a13d8b…`）
> - `renumber_gff_ids.py`（`90b5d84e…`）
> - `prepare_aegilops4_dataset.sh`（`04a905cc…`，本批 A2 一键脚本：幂等、逐步校验、日志落盘）
> 日志：各数据集目录下 `prepare_<MYTAG>.log`

## 0. 结论

**4 个基因组的平台四件套（`.fa/.gff3/.cds/.pep`）已全部生成并通过验收**，总计约 **21.6 GB** 数据目录（含原始下载；磁盘仍剩 30 TB）。

| 数据集目录 | gene = mRNA | ChrUn 基因 | FASTA seqs（长度全部与 assembly_report 一致） | PEP/CDS | 平台质检 | 重编号闸门 |
|---|---|---|---|---|---|---|
| `MM_Aegilops_comosa_IPK_AE783` | 51,203 | 38 | 17 / 17 ✅ | 51,203 / 51,203 | rc=0 ✅ | PASS ✅ |
| `CC_Aegilops_markgrafii_EKC105_RL5723` | 47,246 | 53 | 24 / 24 ✅ | 47,246 / 47,246 | rc=0 ✅ | PASS ✅ |
| `UU_Aegilops_umbellulata_IPK_AE740` | 49,677 | 1,103 | 250 / 250 ✅ | 49,677 / 49,677 | rc=0 ✅ | PASS ✅ |
| `NN_Aegilops_uniaristata_IPK_AE680` | 50,416 | 66 | 21 / 21 ✅ | 50,416 / 50,416 | rc=0 ✅ | PASS ✅ |

跨 4 物种 mRNA ID：**198,542 个，唯一 198,542，重复 0**。

## 1. 每目录产物

| 文件 | 含义 | 大小（comosa / markgrafii / umbellulata / uniaristata） |
|---|---|---|
| `<MYTAG>.fa` | 归一化 FASTA（`Chr1M…`/`ChrUn_*`，含 `_MYTAG` 后缀在后续流水线 Step 1 加） | 4.46 / 3.62 / 4.32 / 4.53 GB |
| `<MYTAG>.gff3` | 平台风格 ID 的 GFF3（每染色体 100 步；`original_id` 留痕） | 54.1 / 52.2 / 53.0 / 53.1 MB |
| `<MYTAG>.cds` / `.pep` | gffread 产物（ID = 新 mRNA ID） | CDS 57.1/53.4/55.3/55.3 MB；PEP 20.0/18.7/19.3/19.4 MB |
| `<MYTAG>.idmap.tsv` | 作者 ID → 新 ID（含 gene/mRNA 类型） | 5.1 / 4.9 / 5.0 / 5.1 MB |
| `<MYTAG>.fa.fai` | FASTA 索引（PrimerServer2 需要） | 760 / 921 / 10,241 / 932 B |
| `<MYTAG>.rawseqids.gff3` | 仅改 seqid、保留作者 ID 的中间产物（`--keep-author-ids`） | 44.3 / 42.1 / 43.5 / 43.5 MB |
| `prepare_<MYTAG>.log` / `*.check_genome_files.log` / `*.gffread.log` | 过程日志 | — |

## 2. 执行步骤（`prepare_aegilops4_dataset.sh` 自动完成，幂等）

1. **FASTA 头映射**：NCBI GenBank 登录号（`CM127985.1` / `JBHEGE…`）→ `Chr1M…` / `ChrUn_*`，序列数/总长与 `assembly_report` 逐条核对；
2. **GFF3 seqid 归一化**（`--keep-author-ids`，只改 seqid，保留作者 ID 供留痕）；
3. **平台风格重编号**（`renumber_gff_ids.py`）：`gene = <prefix><chr>G<6位>`、`mRNA = gene + ".1"`；每染色体从 `000100` 起、每 100 递增；未定位 `UnG` 全局编号；作者 ID 写入 `original_id` + `idmap.tsv`；
4. **gffread** 生成 CDS/PEP；
5. **PEP 清洗**：`--stop-mode trim`（行尾 `.`/`*` 删除、内部终止符换 `X`）；comosa 有 6,573 条模型含终止符（与作者注释一致）；
6. **平台质检** `check_genome_files.py` → **4/4 rc=0**。

耗时：comosa 端到端约 2 分钟；其余 3 个并行约 2 分钟（合计 <10 分钟，未含下载）。

## 3. 额外交叉验证（comosa 深检，其余同规则）

- `.fa.fai` 17 条序列长度与 `assembly_report` **17/17 完全一致**；
- PEP 抽样 8 条（HC / LC-STRG / 未定位 scaffold 混合）与 Zenodo 作者蛋白 **8/8 一致**（仅少于末端终止符）；
- `renumber --check`：ID 模式、每染色体 100 步连续性、坐标顺序、`ChrUn` 全局连续性、mRNA `.数字` 后缀全部 PASS。

## 4. 下一步（G0 命名门禁 → G3 流水线）

```bash
# G0：生成 name_plan.json（V2 页面/SPA 已适配；旧脚本已升级）
bash scripts/finish_genome_integration.sh MM Aegilops_comosa_IPK_AE783 10.1186/s12870-026-10046-2 \
  --check-name --write-plan --confirm \
  --cultivar "IPK-AE783" --accession "GCA_052815735.2" --species "Aegilops comosa" \
  --group "Other Triticeae"
# 其余 3 个同法（CC/UU/NN 数据集名见上表）

# G3：流水线（每基因组 25–45 min；4 个顺序约 2–4 h，建议夜间）
cd /var/www/data/masw_data/MM_Aegilops_comosa_IPK_AE783
setsid --fork bash -c "exec bash /var/www/data/masw_data/add_wheat_genome.sh \
  Aegilops_comosa_IPK_AE783 /var/www/data/masw_data/MM_Aegilops_comosa_IPK_AE783 MM" \
  > pipeline_Aegilops_comosa_IPK_AE783.log 2>&1 < /dev/null
```

> 注意：`add_wheat_genome.sh` 的 `${MYTAG}.fa/.gff3/.cds/.pep` 已就位 → 可直接进入 Step 0；流水线会把染色体头加 `_${MYTAG}` 后缀（`ChrUn_*` 不加）。
