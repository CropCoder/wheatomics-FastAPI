# 文献检索 v2（Meilisearch + 影响因子 + 勾选导出）

> 2026-11-08 上线。适用于 `Triticeae Papers` 模块（`/papers/`）与 `/api/papers`。

## 架构

```
前端 /papers/  ──►  FastAPI /api/papers
                      │
                      ├─ 文本匹配：Meilisearch (127.0.0.1:7700, index=papers)
                      │     · 拼写容错、前缀、单复数近似
                      │     · 返回按相关度排序的 PMID 列表
                      │
                      └─ 结构化过滤 + 精确计数 + 分页：MySQL
                            · 日期 / 影响因子 / 分区 / 注释状态 / PMID 等
                            · LEFT JOIN journal_alias → journal_metrics
                            · Meilisearch 不可用时自动回退到 LIKE 检索
```

MySQL 始终是唯一事实来源；Meilisearch 只是文本匹配层。

## 数据链路

```
papers.journal（PubMed MedAbbr，命名不统一）
  → journal_alias（93 行；ISSN 来自 PubMed IS 字段）
  → journal_metrics（ISSN → JIF / 分区 / 年份 / 来源）
```

- 期刊名不一致不影响 join：**用 ISSN 桥接，不用名字**
- 期刊改名用 `--alias-rename OLD_ISSN:NEW_ISSN` 处理（如 Yi Chuan Xue Bao → J Genet Genomics）
- 当前数据：JCR 2024，覆盖 16,836/16,840 篇（99.99%）；`Crop Health`、`MicroPubl Biol` 无指标

## 索引刷新

`scripts/papers_meili_sync.py` 把 papers + fga + journal_metrics 反范式化为 Meilisearch 文档：

```bash
# 生产机（fei）
source /home/fei/meilisearch/meili.env
cd /var/www/FastAPI_backend_Port8000
python3 scripts/papers_meili_sync.py --rebuild     # 全量重建（~17k 文档，秒级）
python3 scripts/papers_meili_sync.py               # upsert（不删索引）
```

周流水线 `run_weekly_v2_pipeline.sh` 的 **Step 6c** 已自动调用 `--rebuild`；
Meilisearch 故障只打印告警，不会让流水线失败。

## 服务与配置

| 项 | 值 |
|---|---|
| Meilisearch | `systemd meilisearch.service`，监听 `127.0.0.1:7700`，data `/home/fei/meilisearch/data` |
| 主密钥 | `/home/fei/meilisearch/meili.env`（600，`MEILI_MASTER_KEY`） |
| API 侧环境 | `wheatomics-api.service` drop-in `EnvironmentFile=/home/fei/meilisearch/meili.env` |
| API 可调 | `MEILI_URL` / `MEILI_INDEX` / `MEILI_TIMEOUT` / `MEILI_API_KEY`（或 `MEILI_MASTER_KEY`） |
| 索引设置 | typoTolerance oneTypo=3 / twoTypos=6；searchable 9 字段；filterable/sortable 按脚本 |

## API 参数（`/api/papers`）

新增：`sort`(`relevance|created_at|pub_date|journal|title|impact_factor`)、`order`、
`min_if`、`max_if`、`quartile`、`pmids`（≤200 批量）、`fuzzy`（1/0，0=旧 LIKE 回退）。

响应每篇新增：`impact_factor`、`jcr_quartile`、`metric_year`、`metric_source`。
注意 **影响因子是期刊级指标**，不是论文级分数；页面显示年份与来源（JCR 2024）。

## MCP

`search_papers` 工具已暴露 `pmids`、`min_if`、`max_if`、`quartile`、`sort`、`order`、`fuzzy`
（`app/mcp/tool_specs.py`），后端 handler 直接复用同一路由函数。

## 维护要点

- 换用机构版 JCR 导出表时：按同结构 CSV 重跑 `scripts/journal_metrics/import_journal_metrics.py`
  （`--source` 改名以在 UI 标注新来源），再跑一次 Meili 同步脚本。
- 新增期刊：先跑 `build_journal_issn_map.py` 生成/更新 journal→ISSN CSV，再导入 metric。
- 删除/合并论文后：重跑 `papers_meili_sync.py --rebuild`，否则索引里会有孤儿文档
  （不会导致 500，因为 SQL 端用 pmid IN 过滤，但会浪费查询）。

## 验证基线（2026-11-08）

```
stripe rust = stripe rusts = 986      （单复数一致）
strip rust (typo)            = 841
yellwo rust (transposition)  = 226
min_if=10                    = 1,670
sort=impact_factor&order=desc→ Nature 48.5 Q1 first
mtimes: relevance query ≈ 0.52 s
spa_visual_check.sh 360–1920 → PASS
```
