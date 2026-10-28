# KnownGene 前端改造 — 本地验证报告（task-5）

> 验证对象：`app/static/genes/index.html`（重构）、`app/static/genes/detail.html`（重构）、
> `app/static/genes/known_gene_common.js`（新建）、`scripts/known_genes_v2055/frontend_mock_server.py`（本地验证用）。
> 依据：`docs/known_genes/frontend_change_spec.md`（权威）、`KnownGenes_v2055_update_plan.md` §3.3/§3.4。
> 数据：`scripts/known_genes_v2055/out/api_fixtures/`（`known_all.json` 1420 行、`known_stats.json`、6 个 `known_detail_*.json`）。
> 验证日期：2026-10-28。所有命令可复现（见 §6）。

---

## 1. 结论

| 检查 | 结果 | 证据目录 |
|---|---|---|
| 列表页浏览态（360/390/768/1024/1440） | **PASS**（唯一 Warn = shell footer "Back to top ↑" 小点击目标，MAINTENANCE §IX 允许） | `ui/index/` |
| Stats tab（360/390/768/1024/1440，点击 tab 后） | **PASS** | `ui/stats/` |
| 列表页搜索态（390/768/1440，`--fill '#searchInp=Drought' --click '#search-btn'`） | **PASS** | `ui/search/` |
| 详情页 6 个 fixture（390/768/1440） | **6/6 PASS**（唯一 Warn = footer back-top） | `ui/detail-1/`、`ui/detail-5/`、`ui/detail-280/`、`ui/detail-296/`、`ui/detail-771/`、`ui/detail-1158/` |
| 交互/数据验证（分页、搜索、field 下拉、筛选、CSV、Stats 数值） | **全部通过**（0 JS 错误） | `ui/interaction-checks.json`、§3 |
| 静态规范自检（spec §7.4 A） | **通过** | §2 |

所有页面：**0 横向溢出（scrollWidth = viewport）、0 破图、0 JS 错误、0 对比度 <3:1**；
`--wait` 选择器全部命中；对比度 3–4.5:1 警告为 0。

---

## 2. 静态规范自检（spec §7.4 A）

```text
$ node --check app/static/genes/known_gene_common.js                  # OK
$ node --check <index.html / detail.html 内联脚本>                     # OK（2 段内联脚本均通过）
$ grep -c "api/v2shell/shell" app/static/genes/index.html              # 2
$ grep -c "api/v2shell/shell" app/static/genes/detail.html             # 2
$ grep -cE "home_header|header-tabs|home_footer|visit-stats" detail    # 0
$ grep -c "api/track/visit" app/static/genes/detail.html               # 0（visit 由 shell.js 接管）
$ grep '<title>' 两页                                                  # KnownGene - WheatOmics（详情加载后动态改为 <gene_id> - WheatOmics）
```

- Bootstrap 4.5.3 + jQuery 1.9.1：均为本地路径引用（`/css/bootstrap-4.5.3-dist/...`、`/js/jquery/1.9.1/...`），无 CDN。
- 未覆盖 Bootstrap 内置类：新样式全部为 `.kg-*` 前缀（`.kg-cat-*`、`.kg-strategy`、`.kg-gene-card`、`.kg-clamp-*` 等）；
  分类/策略徽章不复用 Bootstrap 语义色，避免改主题。
- 新公共文件挂在现有 `/genes` 静态目录，无需改 `main.py`。
- 全部动态文本经 `KG.esc()` 输出；**不 strip HTML**（数据中 `<` 为数学符号，如 `p < 0.05`）。
  fixture `hash_symbol_row`（280）的 `#1`、以及 `largest_protein_family`（1158）的 `#` 均原样渲染（DOM 检查：`hasHashText=true`）。
- 链接白名单：DOI `^10\.\d{4,9}/\S+$`；GeneHub 仅 `^TraesCS\d` / `^Traes_` 且 `encodeURIComponent`。

---

## 3. 交互 / 数据验证（ego-browser 真实 Chromium，1440/390）

原始结果：`ui/interaction-checks.json`（`errors: []`）。

### 3.1 分页（服务端 limit/offset，50/页）

| 检查 | 实测 |
|---|---|
| 首屏 `#res-info` | `Showing 1–50 of 1,420 · Browse all` |
| 首屏卡片数 | 50 |
| 分页条 | `Page 1 / 29`；Prev disabled、Next enabled |
| 点击 Next | `Showing 51–100 of 1,420`；首卡 `TraesCS3A03G0229500`（offset=50 生效） |
| 点击 Prev | 回到 `Page 1 / 29` |
| 请求参数 | `/all?limit=50&offset=N`（mock 与 backend 契约一致） |

### 3.2 搜索 + Field 下拉真正生效

- `field=phenotype` + `Drought`：`Showing 1–50 of 167 · query "Drought" · field: Trait / Phenotype`（mock 按 field 过滤，total 167）。
- `field=gene_name` + `HvPTR1`：`Showing 1–1 of 1 · query "HvPTR1" · field: Gene name`。
- 全部 10 个下拉值逐一实测，请求均带对应 `field`，`#res-info` 回显正确：
  `all`(1,295) / `gene_name`(1) / `reference_genome_id`(1) / `phenotype`(167) / `species`(80) /
  `doi`(150) / `functional_category`(202) / `chrom_pos`(78)。
  `gene_id` 搜 `TraesCS7A03G0682600` 返回 0（该值是参考基因组 ID 而非 gene_id，行为正确）；
  `protein_family` 搜 `NLR` 返回 0 是 **mock 摘要不含 protein_family 字段** 所致（见 §5 偏差 D3），非前端缺陷。
- 空搜索自动回到浏览态（`/all?limit=50&offset=0`）。

### 3.3 筛选条（客户端，仅搜索态；Q10 决策）

- 浏览态不显示筛选条（避免对未加载全量数据计数误导）。
- 搜索 `Drought`（167 条）后自动加载该查询的完整结果集（`limit=5000`）并显示筛选计数：
  - Functional category：Biotic & Abiotic Stress (160) / Morphology & Domestication (2) / Physiology & Metabolic Processes (4) / Reproduction & Phenology (1)
  - Research strategy：Reverse genetics (152) / Forward genetics (14) / Not reported (1)
  - Species：Top 8 + Other（T. aestivum 158 / H. vulgare 6 / T. turgidum subsp. durum 2 / x Triticosecale 1）
- 选中 `Biotic & Abiotic Stress` → `Showing 1–50 of 160 · filtered from 167 · query "Drought" · field: Trait / Phenotype`，
  分页 `Page 1 / 4`；`Clear filters` 后回到 167。计数与 CSV 行数一致（见 3.4）。

### 3.4 CSV 导出（19 列 / UTF-8 BOM / 公式注入防护 / 筛选后全部结果）

| 检查 | 实测 |
|---|---|
| 表头 | 19 列，顺序与 spec §4.5 完全一致（Gene ID → Detail URL） |
| BOM | `hasBom: true`（`\uFEFF`） |
| 筛选后导出（160 条） | CSV 数据行 = **160**（= 筛选后全部结果，不是当前页 50） |
| 浏览态全量导出 | 数据行 = **1,420**，1.09 MB；含 Key results 全文与 Detail URL |
| 长文本列富化 | 单行搜索 `HvPTR1` 导出含 `NRT1/PTR`（protein family，来自 `/known/{id}` 详情） |
| 公式注入防护 | `KG.csvCell('=1+1')` → `"'=1+1"`；`@x`→`"'@x"`；`-2`→`"'-2"` |
| 文件名 | `known_genes_<term>_<timestamp>.csv`（空 term 为 `all`） |

> 说明：列表摘要契约不含 5 个长文本列（`protein_family` / `validation_methods` / `cloning_method` /
> `key_result` / `function_description`，见 fixtures 的 `known_all.json` 键集合）。为保证 19 列有值，
> 导出时按行并发（6）调用 `/api/genes/known/{id}` 富化，按钮显示 `Preparing CSV… (n/N)`；
> 单行失败仅该行对应列留空，不中断导出（详见 §5 偏差 D2）。

### 3.5 Stats tab（/api/genes/known/stats，6 KPI + 7 组图）

| 检查 | 实测 |
|---|---|
| 数据来源 | 只用 `/api/genes/known/stats`，**不再请求 `/all`**（Network 仅 stats；KPI/图一次渲染） |
| KPI 数 | 6（Total 1,420 / Species 23 + 296 raw forms / Wheat 21 of 21 + 17 other types / Categories 5 / Strategies 3 / References 1,570 · 883 DOIs） |
| 物种分布 | 16 行 = Top 15 + `Other (8 species)`；学名斜体，title 含 raw_forms |
| 功能大类 | 5 行（同徽章色系），776/202/154/146/142 |
| 小麦染色体 | 21 根 vbar，顺序 1A–7D（2B 96 最高；0 也画空柱） |
| 其他染色体 | 17 行 bar-row：1H–7H、1R、6R、1S、2V、6S、6U、6V、7E、chr51、chr54 |
| 研究策略 | 3 行（1,061 / 281 / 78） |
| 年份 | 29 根 vbar，1998–2026；副标题注明「多文献行按年重复计数（130 行）」 |
| 表型 Top20 | 20 行，label 2 行截断 + title 全文；副标题 583 distinct tags |
| 390px | 6 KPI（2 列）、图表 0 横向溢出；小麦 21 柱可横向滚动 |

截图：`ui/stats/w{360,390,768,1024,1440}.png`、`ui/stats/w1440-section.png`（染色体两图）、
`ui/stats-charts-lower-1440.png`（年份/表型下半部）、`ui/stats-phenotype-390.png`（移动端表型图）。

### 3.6 详情页 17 字段 / 12 section（6 个 fixture 全覆盖）

`ui/interaction-checks.json` → `detail.*`，每项均无 JS 错误。

| fixture | clone_id | 覆盖点 | 结果 |
|---|---|---|---|
| `wheat_long_text_multi_doi` | 771 | 长 phenotype/Key results/Function/cloning desc（clamp+Show more）、2 references（year+title+DOI）、TraesCS 可链 GeneHub、年份 chips 2022/2023 | PASS |
| `barley_3H` | 1 | 大麦染色体 `3H`（非小麦 badge-light）、HORVU 参考 ID **不链**、`Not reported` cloning_method muted、参考基因组/验证方法 chips | PASS |
| `hash_symbol_row` | 280 | `#` 原文显示不变成 `'`、TraesCS 可链、8 个验证方法 chips、cloning 组合值 | PASS |
| `no_chr_prefix_row` | 296 | 无 `chr` 前缀 `AetTA1675 2D:...` 解析出 `2D`、`AeT.TA1675...` 非 TraesCS **不链**、cloning Details 折叠 | PASS |
| `multi_year_row` | 5 | 多文献（2008+2024）Reference 逐条年份、`2008 2024` 年份 chips、cloning 组合拆分 2 chips | PASS |
| `largest_protein_family` | 1158 | 2026 字符蛋白家族 clamp-6 + Show more、验证方法全部为长文本 → `Other assays (8)` 折叠（0 chips）、Species 长材料文本 clamp-4 + Show more、PP537390.1 **不链** | PASS |

补充：`detail-empty-fields-390-fullpage.png`（无 author/cloning 的合成行：Submitted by 与 Cloning 卡整卡隐藏，
不出现 `—` 空壳）、`detail-404-390.png`（错误态 + Back to search）。

展开交互：点击 `Show more` 后 `.kg-longtext.is-open` 生效、按钮文案变 `Show less`（DOM 检查 `phenotypeOpen=true`）。
`sectionsShown` 在 6 个 fixture 上均为 10 个 section（Ref genome / Protein family / Annotations / Phenotype /
Key results / Function / Cloning / References / Species / Submitted by）+ head + overview 4 卡。

---

## 4. 截图归档

```
docs/known_genes/_evidence/ui/
├── index/            w360/w390/w768/w1024/w1440.png + report.md/report.json   （浏览态 PASS）
├── stats/            w*.png + w*-section.png + report.md                       （Stats PASS）
├── search/           w390/w768/w1440.png + w*-section.png + report.md          （搜索态 PASS）
├── detail-1/         w*.png + report.md                                        （大麦 3H，PASS）
├── detail-5/         w*.png + report.md                                        （多文献，PASS）
├── detail-280/       w*.png + report.md                                        （# 行，PASS）
├── detail-296/       w*.png + report.md                                        （无 chr 前缀，PASS）
├── detail-771/       w*.png + report.md                                        （长文本+多 DOI，PASS）
├── detail-1158/      w*.png + report.md                                        （最长蛋白家族/验证方法，PASS）
├── index-1440-page1.png / index-1440-page2.png                                  （分页）
├── index-search-1440.png / index-search-390.png / index-search-genename-1440.png
├── index-filtered-1440.png / index-filtered-1440-after-export.png              （筛选条/CSV 导出后）
├── index-after-full-export-1440.png                                            （全量导出后状态）
├── detail-<fixture>-1440-fullpage.png / -expanded.png                          （整页长图，6 个 fixture）
├── detail-empty-fields-390-fullpage.png / detail-404-390.png
├── stats-charts-lower-1440.png / stats-phenotype-390.png
└── interaction-checks.json                                                     （交互/数据断言原始值）
```

---

## 5. 与 spec 的偏差 / 实现取舍（需 Lead 知会）

| # | 项 | spec 原文 | 实际实现 | 原因/风险 |
|---|---|---|---|---|
| D1 | 搜索分页 | `/search` 也用服务端 `limit/offset` 翻页 | 首屏仍按 `limit=50&offset=0` 请求；同时后台拉取该查询完整结果集（`limit=5000`）用于筛选计数；**翻页是否走服务端**：无筛选时走服务端，进入筛选态后在已加载结果集上客户端翻页 | 筛选条计数/CSV 需要完整结果集；搜索命中通常远小于 1420，额外 payload 小。浏览态始终服务端分页 |
| D2 | CSV 长文本列 | §4.5 假设摘要记录可直接导出 19 列 | `/all`、`/search` 摘要契约（fixtures 权威）不含 5 个长文本字段 → 导出时按行并发调 `/known/{id}` 富化（6 并发，按钮进度） | 1420 行全量导出约 1420 个详情请求（本地 mock ~10 s）；若 backend 希望避免，可在 `/all` 增加可选 `full=1`/批量导出端点。单行失败仅留空 |
| D3 | protein_family 搜索 | `field=protein_family` | 前端已对接，mock 摘要无该字段故本地返回 0；真实 backend 在 DB 查 `protein_family` 列，不受影响 | mock 数据限制，非前端缺陷 |
| D4 | 详情页 head 层级 | §3.1 建议 head `<h1>`；§6.2 骨架给 `<h2>` | 采用骨架 `<h2>`（页面 hero 已有 h1，避免双 h1） | 与 §6.2 一致 |
| D5 | 分类/策略徽章在 head 与 annotations 卡重复 | §6.2 骨架两处都有容器 | 两处都填充（head 便于首屏识别；annotations 卡保留完整语义） | 轻微重复，视觉可接受 |
| D6 | 详情 References DOI 对齐 | §3.5 顺序 `year — title — DOI` | flex 行：year chip + title（flex:1）+ DOI 右对齐 | 桌面更易扫读，移动端自动换行；不改变内容顺序 |
| D7 | 页面 title | 任务要求 `KnownGene - WheatOmics`；spec 保留动态 | 静态 title 两页均为 `KnownGene - WheatOmics`；详情接口返回后动态 `document.title = <gene_id> - WheatOmics`（保留旧行为） | 与 spec §3.1 一致 |
| D8 | 筛选条启用范围 | spec Q10 建议仅搜索态 | 已按建议实现（浏览态不显示） | — |

---

## 6. 复现步骤

```bash
cd /Users/mashengwei/Desktop/markdown/wheatomics/FastAPI_backend_Port8000

# 0) 静态资源（生产 docroot 不在仓库）：预下载到 /tmp/kg_assets（只读生产，~2-6 min，已缓存）
#    mock server 会在 cache miss 时用 8s 超时尝试下载；失败自动用空 CSS/1x1 PNG stub

# 1) 启动 mock（后台）
python3 scripts/known_genes_v2055/frontend_mock_server.py --port 8100 &
curl -s "http://127.0.0.1:8100/api/genes/known/all?limit=50&offset=0" | head -c 200

# 2) 视觉检查（--out 必须用绝对路径；报告查看 <out>/report.md）
UI=$PWD/docs/known_genes/_evidence/ui
bash scripts/spa_visual_check.sh http://127.0.0.1:8100/genes/ \
  --label kg-index --widths 360,390,768,1024,1440 --out "$UI/index" --settle 1200
bash scripts/spa_visual_check.sh http://127.0.0.1:8100/genes/ \
  --label kg-index-stats --widths 360,390,768,1024,1440 --out "$UI/stats" \
  --click 'a[href="#tab-stats"]' --wait '#stats-content' --scroll-to '#chart-chrom-wheat' --settle 1500
bash scripts/spa_visual_check.sh http://127.0.0.1:8100/genes/ \
  --label kg-index-search --widths 390,768,1440 --out "$UI/search" \
  --fill '#searchInp=Drought' --click '#search-btn' --wait '.gene-card' --settle 1200
for id in 1 5 280 296 771 1158; do
  bash scripts/spa_visual_check.sh "http://127.0.0.1:8100/genes/detail.html?id=$id" \
    --label "kg-detail-$id" --widths 390,768,1440 --out "$UI/detail-$id" \
    --wait '#detail-content' --settle 1200
done
```

mock 契约（与 fixtures 对齐，可直接用于 backend 联调前自测）：
- `GET /api/genes/known/all?limit=&offset=`（total 语义：传 limit 时为全表总数）
- `GET /api/genes/known/search?searchid=&field=&limit=&offset=`（field 白名单 11 值，未知 → 400）
- `GET /api/genes/known/stats`
- `GET /api/genes/known/{clone_id|gene_id|gene_name}`（6 个 fixture 精确返回；其余行合成摘要详情以覆盖空值隐藏路径）
- `POST /api/track/visit`、`GET /api/track/stats`（shell footer 用）

---

## 7. 遗留风险 / 上线前注意

1. **未连真实 MySQL/真实 API 验证**：本报告全部基于 fixtures mock。上线前必须用生产/预发 `/api/genes/known/*`
   冒烟（`curl` 5 个端点 + 1 次 `spa_visual_check` 线上 URL），重点核对 `/known/stats` 是否注册在 `/known/{gene_id}` 之前。
2. **CSV 富化成本（D2）**：全量导出 = 1420 次详情请求。若生产端并发/超时担心，建议 backend 增加批量导出端点
   或在 `/all` 增加 `full=1`；当前实现在 6 并发下预计 1–2 min（本机 mock ~10 s）。
3. **`/GeneHub/` 本地 404 属预期**：mock 未实现 GeneHub 页面；链接规则已按 fixture 验证（TraesCS/Traes_ 链、
   其余纯文本），线上需抽查 2 个 TraesCS 链接 200。
4. **参照系基因前缀 `Refv1.0`**：fixtures 的 `genome_ref` 由后端派生；前端同时保留 `parseRefGenome()` 兜底。
5. **mock 的 `protein_family`/`doi` 等字段搜索**：mock 摘要没有 `protein_family` 列（fixtures 如此），
   故该 field 本地返回 0；真实 backend 查询 DB 列不受影响（D3）。
6. **生产静态资源**：Bootstrap/jQuery/logo/footer 图从生产 docroot 下载（只读）；若 CI 无外网，
   需把 `/tmp/kg_assets` 缓存随验证环境带上，或接受空 CSS fallback（此时视觉检查不作数）。
7. 详情页动态 title 会用 gene_id 覆盖静态 `KnownGene - WheatOmics`（旧行为保留），grep 验收以静态文件为准。
