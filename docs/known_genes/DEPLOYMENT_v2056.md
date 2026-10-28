# KnownGene v2056 上线执行记录（DEPLOYMENT）

> 计划：`KnownGenes_v2055_update_plan.md`；操作手册：`docs/known_genes/ROLLOUT_v2056.md`；
> 决策/冻结：`docs/known_genes/FREEZE_v2055.md`。执行日期：**2026-10-28 傍晚（CST）**。

## 1. 执行结果总览

| 步骤 | 结果 | 证据 |
|---|---|---|
| P0 基线备份 | ✅ | `/home/fei/backup/cloned_gene_tbl_pre_v2056.json.gz`（520 行，sha256 a591e183…）、`cloned_gene_tbl_pre_v2056_20261028.sql`（906,212 B）、`/home/fei/backup/known_all_pre_v2056.json`（97,894 B） |
| P1 DDL（root） | ✅ | 表 24 列、备份表 520 行、staging 0 行、4 个前缀索引；`ROW_FORMAT=Dynamic`；DDL 文件 `scripts/sql/known_genes_v2055_ddl.sql` |
| P2 后端代码上线 | ✅ | 生产 HEAD `14aa700`（后端+数据管线+docs）；`systemctl restart wheatomics-api` 成功；旧数据 520 行下新 API 冒烟通过（新列为 NULL 的防御路径） |
| P3 数据替换 | ✅ | 1420 行、distinct clone_id 1420、max clone_id 1625、继承旧 id 321、空值检查全 0、23 物种 / 38 染色体 / 5 功能大类 / 3 研究策略；`#` 保留 18 行 |
| P4 前端上线 | ✅ | 生产 HEAD `516de39`；`/genes/` 62,377 B、`/genes/detail.html` 31,069 B、`known_gene_common.js` 15,901 B（static 即时生效，无需重启） |
| P5 News 公告 | ✅ | `/var/www/html/V2.0/news.json` 首位新增 2026-10-28 条目（备份 `news.json.bak-20261028_known_gene`）；公网首页 News 条已实测显示 `OCT 28, 2026 KnownGene expanded to 1,420 curated functional genes…`（截图 `_evidence/ui/prod/home-news-w1440.png`） |
| P6 线上验收 | ✅ | 公网 API 冒烟全绿 + 多宽度视觉检查 PASS（见 §3） |

## 2. 关键口径（实际值）

- **数据源**：v2056（md5 `1dbbeff77f8f53eb33e8ea133d32cb65`）→ JSONL（md5 `33e7f2881c073f41776238ad7ef189b2`，1420 行，8,054,314 B）。
- **clone_id 映射**：`T2_v3` 290 + `T1_id` 10 + `T1_id_token` 3 + `T3_name_chrom` 5 + `T3_name` 13 = **321/520（61.73%）**；
  199 个未映射旧 ID 删除且不复用（用户决策 Q3：不建 legacy 回退表，详情 URL 用内部 `clone_id`）；
  1099 个新行 clone_id **527…1625**，AUTO_INCREMENT=1626。
- **API 验收数值**：`/known/all` total=1420；`/known/stats`：species 23 / chromosomes 38 / functional 5 / strategies 3 /
  species_raw_count 296 / references 1570·883 DOI / Σpublication_year 1570 / phenotype_tag_distinct 583 /
  notes {multi_year_rows 130, multi_species_rows 263, rows_without_tags 541, wheat_chromosomes_covered 21}；
  `/known/search?searchid=TaCRT` 的 publication_year=2008（旧 bug 已修）；`#` 在 `7S#1`/`hc#28`/`lines #1` 响应中原样保留；
  LIKE 转义 `70%` 只字面命中（16 条）；`/known/all` gzip 217,950 B。

## 3. 线上验证

### 3.1 API（公网 https://wheatomics.sdau.edu.cn）

| 检查 | 结果 |
|---|---|
| `/api/genes/known/all?limit=2` | 200，total=1420 |
| `/api/genes/known/stats` | 200，9,627 B，23 species / 38 chrom / 1570 refs·883 DOI |
| `/api/genes/known/12`（继承的旧 clone_id） | 200 |
| `/api/genes/known/527`（新行） | 200（HvPTR1） |
| `/api/genes/known/search?searchid=7S%231` | 200（`#` 正常） |
| 错误路径 bad field / blank searchid / missing searchid / bad chromosome / 99999 | 400 / 400 / 422 / 400 / 404 |
| `/cgi-bin/gene_search.py?searchid=VRN1` | 200（旧 CGI 仍可用） |
| `/cgi-bin/gene_search_by_id.py?searchid=TraesCS5A03G0935400` | 200（旧 CGI 读取新行正常） |
| `/GeneHub/?search=TraesCS5A03G0935400` | 200 |

### 3.2 多宽度视觉检查（`scripts/spa_visual_check.sh`，ego-browser）

| 检查 | 宽度 | 结果 | 报告 |
|---|---|---|---|
| `/genes/` 浏览态 | 360–1920 全部 | **PASS**（0 溢出/0 破图/0 JS 错/对比度 floor 通过；仅 footer Back-to-top 小目标 Warn） | `_evidence/ui/prod/index/report.md` |
| Stats tab（点击后） | 360–1920 全部 | **PASS** | `_evidence/ui/prod/stats/report.md` |
| 搜索态 `Drought` | 390/768/1440 | **PASS**（结果卡片出现、无溢出） | `_evidence/ui/prod/search/report.md` |
| detail `?id=12`（321 个继承旧行之一） | 390/768/1440 | **PASS** | `_evidence/ui/prod/detail12/report.md` |
| detail `?id=527`（1099 个新行之一） | 390/768/1440 | **PASS** | `_evidence/ui/prod/detail527/report.md` |

生产截图（本地留档，PNG 已 gitignore）：`_evidence/ui/prod/*.png`。
- 本地 mock 阶段另有 9/9 次检查记录：`docs/known_genes/_evidence/ui/VERIFICATION.md`。

## 4. 备份与回滚（保留 ≥30 天）

- 旧表全量：`cloned_gene_db.cloned_gene_tbl_backup_20261028`（520 行，结构=新结构，新列 NULL）；
  `/home/fei/backup/cloned_gene_tbl_pre_v2056.json.gz`；`/home/fei/backup/cloned_gene_tbl_pre_v2056_20261028.sql`。
- 数据回滚：`python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py --phase rollback --commit`
  （从 `cloned_gene_tbl_backup_20261028` 恢复旧 16 列 / 520 行）。
- 代码/前端回滚：`git revert <commit>` 或 `git checkout 5364ca3 -- app/ static...` → `git pull` → 必要时重启。
- DDL 结构回滚：`scripts/sql/known_genes_v2055_ddl.sql` 末尾注释块（DROP 新列/索引）。
- News 回滚：恢复 `/var/www/html/V2.0/news.json.bak-20261028_known_gene`。

## 5. 遗留与后续

- 历史临时表（`cloned_gene_temp` 1037 / `cloned_gene_bad_import_backup` 1636 / `cloned_gene_tbl_backup_null` 575 /
  `cloned_gene_tbl_subdate_backup_20261020` 575）本次未清理，稳定 1–2 周后另立项（需 root）。
- 前端 CSV 全量导出会按行并发调 `/known/{id}` 富化长文本列（1420 行约 10–30 s）；如后续觉得慢，可加 `/known/all?full=1`
  批量导出端点（见前端 spec 偏差 D2）。
- 旧 199 条未映射 clone_id 的详情 URL 会 404（用户已确认接受；不建 legacy 表）。
- 生产本机 `/tmp` 迁移临时文件已清理（JSONL/映射报告留存于 `/home/fei/backup/`）。

## 6. 2026-10-28 后续调整：CSV 导出仅支持搜索结果

用户反馈浏览态（1,420 行）的 "Export Results (CSV)" 按钮暂时去掉/仅支持搜索结果导出。已按「仅支持搜索结果导出」实现：

- 浏览态（搜索词为空）：**隐藏导出按钮**（`.btn` 加 `hidden`），不再触发 1,420 行全量导出（该路径需逐行 `/known/{id}` 富化，代价大）；
- 搜索态：按钮显示、文案改为 **Export Search Results (CSV)**，仅导出当前查询（含筛选）的结果集；
- 搜索框下方 helper 文案补充 "CSV export is available for search results."；
- 本地 mock 验证：浏览态按钮 hidden=true / 不可见，搜索 `Drought`（167 条）按钮可见；导出 CSV 行数=167、19 列、UTF-8 BOM、0 JS 错误；多宽度 `spa_visual_check` 浏览/搜索态均 PASS；
- 变更文件仅 `app/static/genes/index.html`（静态文件，`git pull` 即生效，无需重启服务）。
