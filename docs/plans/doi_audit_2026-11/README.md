# 2026-11-24 · genome_registry DOI 全库核查与修复

> 触发：核查黑麦 Lo7_V3（[10.1038/s41467-026-76753-4](https://doi.org/10.1038/s41467-026-76753-4)）是否入库时，
> 顺手发现 `rye_weining2` 的 DOI 指向 Sumai 3 小麦论文，进而做了一次全库体检。
> 结论：**该 Lo7_V3 尚未入库**（站内只有 2017 Lo7 草稿 + 两个 Weining），另修掉 9 条记录的错误元数据。

## 1. 根因（两个 bug，都不是"手滑"）

| 现象 | 根因 |
|---|---|
| `rye_weining2` / `Elymus_sibiricus_cultivar_Gaomu` 的 DOI 是 Sumai 3 的 `10.1002/tpg2.70285`，`rye_weining` 的 `paper_title` 也是 Sumai 3 | `cite.html` 有若干条写成 `…sequences,please cite:`（**漏空格**）；`rebuild_genome_registry.py` 用 `If you use (.+?) please cite:` 跨块匹配，于是把下一条整段吞进 trigger，DOI/标题整体串位 |
| `Keumkang`/`MOV`/`spelta`/`urartu_PI428250` 的 DOI 变成 `10.1038s41586-018-0108-0`（漏斜杠的 urartu DOI）；`alchemy` 也是 | JBrowse 页面已升级 V2（`article.asm-card`），注册表脚本仍在找旧版 `div.card-body` → **所有卡片 DOI 被丢弃**，DOI 全部落到关键词回退；回退用的关键词含 `triticum` 这类属名，于是整属记录被指到同一篇论文 |
| `rye_Lo7` 的 DOI 是 2017 草稿（`tpj.13436`）、`gene_count` 27,784，而站点实际服务的是 2021 参考基因组注释（57,222 基因） | 策展表同一物种有两行（2017 草稿 / 2021 参考），`_apply_curated` 无条件用策展表 DOI 覆盖卡片 DOI |

配套事实：`genome_registry` 的 DOI 有三个来源（`--doi` 参数、`Genefunc_registry.Doi`、页面抓取），
**此前没有任何一处做 Crossref 校验**，所以错值可以长期存在且站点表现完全正常。

## 2. 修了什么

**数据（生产库 `wheatomics_db.genome_registry`，9 行）**

| dataset_id | 旧 | 新 | 依据 |
|---|---|---|---|
| `rye_weining2` | 10.1002/tpg2.70285（Sumai 3） | 10.1186/s13059-025-03792-3 | 卡片 + cite.html + 策展表 + Crossref |
| `rye_weining` | DOI 对，标题是 Sumai 3 | 标题改为 2021  rye 论文 | 卡片 + cite.html |
| `rye_Lo7` | 10.1111/tpj.13436（2017 草稿） | 10.1038/s41588-021-00807-0 | 卡片 + cite.html + Ensembl（GCA_902687465.1，57,222 基因） |
| `AABBDD_Triticum_aestivum_Keumkang` | 10.1038s41586-018-0108-0 | 10.1038/s41597-026-08617-x | 卡片 + `Genefunc_registry.Doi` |
| `Triticum_spelta_PI190962` | 同上 | 10.1038/s41586-020-2961-x | 卡片 |
| `Triticum_aestivum_MOV` | 同上 | 10.1073/pnas.2510889122 | 卡片 |
| `Triticum_urartu_PI428250` | 同上 | 10.1038/s41467-026-71539-0 | 卡片 |
| `Elymus_sibiricus_cultivar_Gaomu` | 10.1002/tpg2.70285 | 10.1038/s41597-024-03622-4 | 卡片 + cite.html + 策展表 |
| `Triticum_aestivum_alchemy` | 10.1038s41586-018-0108-0 | 置空 | 卡片/Genefunc/策展表均无 DOI，待人工核实 |

改库脚本：[scripts/fix_registry_metadata_2026_11_24.py](../../../scripts/fix_registry_metadata_2026_11_24.py)（带 `WHERE doi=<旧值>` 保护，可重入）；
备份：`/var/www/data/masw_data/_prep/backup_20261124/genome_registry_20261124.sql`（795 KB）。
`cite.html` 三处漏斜杠 DOI 已在服务器修正，备份 `cite.html.bak-20261124_doi`。

**代码（防复发）**

- `scripts/rebuild_genome_registry.py`
  - JBrowse V2 `article.asm-card` 解析（兼容旧 `div.card-body`），卡片 id 大小写不敏感匹配；
  - `cite.html` 改为按 `If you use ` 切片解析，漏空格不再跨块；
  - 关键词回退只认材料级词、且要求唯一命中，命中多条则放弃并写 note；
  - 策展表 DOI 与卡片冲突时**不覆盖**，只记 `[策展表 DOI 冲突: …]`；
  - 新增 `--diff` 只读对比；`overrides` 里钉死上述 8 条（含 `_clear` 清空能力）。
- `scripts/finish_genome_integration.sh`：启动即跑 `verify_doi`（Crossref）——格式错/404 直接 `[FATAL]`，
  标题与材料对不上 `[WARN]`（`--skip-doi-check` 可跳过），避免 `--doi` 再被随手粘错。
- `scripts/verify_genome_doi.py`：全库 DOI 体检（Crossref + 期刊/年份/物种/同 DOI 跨属），产出 Markdown + JSON，可作门禁。
- 文档：SOP §14「DOI 核查」、一页清单 §0/G0/G4/G5。

## 3. 复核结果

```
python3 scripts/verify_genome_doi.py --report … --json …
[result] error=0 suspect=10 info=30 ok=314（354 条）
```

10 条 suspect 均为"标题未点名该材料"的可解释情况（Ae. tauschii 泛基因组、TRITEX 方法论文、
Fhb7 水平转移、Sitopsis 属级论文等），已逐条人工确认不需要改 DOI；`info` 多为无 DOI 的 scaffold/占位记录。

页面复核（`/api/genomes/<id>`）：9 条记录的 `doi/paper_title/journal/publication_year` 已全部与论文一致。

## 4. 未处理 / 待办

- `CWI86942`、`TaesCWI86942` 挂 10.1038/s41586-024-07808-z（Ae. tauschii D 基因组论文），三处平台来源一致但与
  "Triticum aestivum CWI86942" 的物种对不上，需业务确认是同一篇论文附带材料还是错挂。
- `qingke`：站内 10.1073/pnas.1423628112（2015 PNAS 草稿）vs 策展表 10.1111/pbi.12826（2017 PBJ qingke 参考），
  需确认平台实际用的是哪套组装再定。
- `durum_PI192051`：现挂 Svevo 2019 论文 DOI，材料不同源，需补正确文献。
- `Triticum_aestivum_alchemy`：DOI 待人工核实（现为空）。
- 残留：`/api/jbrowse/datasets` 里的 `Secale_cereale` 数据集在服务器上无对应目录（疑似僵尸条目）。
- **Lo7_V3 本身仍未入库**：Ena PRJEB91463 / GCA_965641915（`lpSecCere.Lo7.IPK.v3`，6.70 Gb，7 条染色体），
  注释在 IPK 10.5447/ipk/2026/5；若要上线按 SOP G0→G5 走，建议 dataset_id `rye_Lo7_V3`。

## 5. 复现

```bash
# 全库体检（只读，公开 API；约 4 分钟）
python3 scripts/verify_genome_doi.py --report wheatomics_results/reports/doi_audit_2026-11-24.md \
    --json wheatomics_results/json/doi_audit_2026-11-24.json
# 单条
python3 scripts/verify_genome_doi.py --dataset rye_weining2
# 重建注册表前先看会改哪些字段（服务器）
python3 _prep/rebuild_genome_registry.py --diff | less
```
