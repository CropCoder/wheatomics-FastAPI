# CGI 盘点与替换（2026-11-23）

## 结论

`/var/www/cgi-bin/` **仍在使用**，不能直接删除。15 天日志（11-09 至 11-23）内
`/cgi-bin/` 共 **425,391** 次请求；前 5 个脚本占 **424,727** 次（99.8%）。
其中序列提取 CGI 仍占绝对多数，但抽样发现大量请求使用**旧 BLAST 库名**
（缺少倍性前缀），CGI 返回的是 HTTP 200 + HTML 里的 BLAST 错误文本。

## 数据来源

- 日志：`/var/log/apache2/access.log` + `.1` + `.2.gz` … `.14.gz`（11-09 ～ 11-23）
- 统计脚本：`/tmp/cgi_inventory.py`，明细 `/tmp/cgi_inventory.tsv`
- 状态码按 HTTP 状态统计；CGI 内部错误仍可能是 200（HTML 错误页）

## 流量排名（15 天）

| 脚本 | 请求数 | 状态 | 调用方/说明 | 替代 | 状态 |
|---|---:|---|---|---|---|
| `get_fasta_bedtools.py` | 385,266 | 200×385,259, 403×7 | 外部/无 referer 为主；少量来自首页 | `/api/sequence/by-interval`（区间）、`/api/sequence/by-gene`（基因） | 已抽样比对，序列一致；但旧库名需解析 |
| `geneDetail.py` | 27,951 | 302×27,878, 500×72 | 旧 GeneHub 链接、wheatPSP | `/GeneHub/gene.html?gene=`（302 目标） | 目标页 200，已验证 |
| `wheat_rice_arabidopsis.py` | 5,287 | 200×5,285 | `/homologtools/index.html`、旧 GeneHub | `/api/homologs/wheat-rice-arabidopsis` | 已验证 6/6 命中一致 |
| `geneDetail_get_sequence.py` | 3,303 | 200×3,302 | GeneHub 序列入口 | `/api/sequence/by-gene` + `by-interval` | 需组合页面，未逐项比对 |
| `triticeae_gene_search.py` | 2,920 | 200×2,920 | `/homologtools/index.html` | **无对应新 API** | 阻塞 |
| `gene_expression.py` | 243 | 200×243 | 旧基因页/书签 | `/api/expression/query` | 参数映射未验证 |
| `co-expression.py` | 93 | 200×93 | 旧基因页/书签 | `/api/coexpression/query` | 参数映射未验证 |
| `get_wheatPPI.py` | 68 | 200×68 | 旧基因页/书签 | `/api/ppi/query` | 参数映射未验证 |
| `gene_search_by_id.py` | 49 | 200×49 | 旧搜索/书签 | `/api/genes/known/...` | 未验证 |
| `gene_function_search.py` | 19 | 200×19 | `/tools/intervalTools.html` | `/api/genes/...` | 未验证 |
| `gene_search.py` | 14 | 200×14 | 旧搜索/书签 | `/api/genes/known/search` | 未验证 |
| `symap.py` | 13 | 200×13 | `/symap/index.html` | `/api/synteny/search` | 未验证 |
| `genome_examples.py` | 7 | 200×7 | `/tools/intervalTools.html` | `/api/genome/examples`（待确认） | 未验证 |
| `viewsymap.py` | 1 | 200×1 | — | — | 可归档 |
| `gene_expression_urartu.py` | 1 | 200×1 | — | — | 可归档 |

其余为 404/扫描器/非 CGI 路径：`genedetail.py`（大小写错误）、`authLogin.cgi`、
`main.pl`、`luci/api/env`、`sitemap.xml`、`img/JBrowseLogo_small.png` 等。
`geneDetail.py.bak-*` 两个可执行备份各被请求 1 次并返回 500，应清理。

## 已验证的替换

### 1. 序列提取（get_fasta_bedtools.py → /api/sequence/by-interval）

样本（当前库名）：

```
GET /cgi-bin/get_fasta_bedtools.py?ID=Chr6B_JM47:360536248-360536368&database=AABBDD_JM47.genome_Chr6B
GET /api/sequence/by-interval?region=Chr6B_JM47:360536248-360536368&database=AABBDD_JM47.genome_Chr6B
```

两边返回的 FASTA 序列**逐字符一致**（header 也一致）。旧库名
`JM47.genome_Chr6B`、`Chinese_Spring2.1.genome_chr1A` 已不存在，CGI 会在
HTML 里打印 `BLAST Database error`，但 HTTP 仍是 200。

结论：新 API 可以作为内部替换；对外部旧 URL 需要兼容层（把旧库名映射到
当前带倍性前缀的库名，或要求客户端改用新 API）。

### 2. GeneHub 跳转（geneDetail.py → /GeneHub/gene.html）

```
GET /cgi-bin/geneDetail.py?search=TraesCS5A02G391700
→ 302 /GeneHub/gene.html?gene=TraesCS5A02G391700
GET https://wheatomics.sdau.edu.cn/GeneHub/gene.html?gene=TraesCS5A02G391700
→ 200，title "GeneHub gene | WheatOmics 2.0"
```

当前 `wheatPSP` 页面的 3 处链接已改为直接指向
`/GeneHub/gene.html?gene=...`（见本仓库 diff），不再经过 CGI。
旧 URL 仍保留 302，兼容书签。

### 3. 水稻/拟南芥同源（wheat_rice_arabidopsis.py → /api/homologs/wheat-rice-arabidopsis）

样本 `TraesCS5A02G391700`：

- CGI 命中：`Os03g54160`、`Os07g01820`、`Os07g41370`、`AT1G26310`、`AT1G69120`、`AT5G60910`
- API：`count=6`，水稻 3 条 + 拟南芥 3 条，目标 ID 与 CGI 一致
- 参数：`gene_id`、`max_targets`（默认 3）

## 阻塞项

1. **Triticeae 同源搜索没有新 API**：`triticeae_gene_search.py`（2,920 次/15 天）
   查询 `Triticeae_table`，新 `/api/homologs/wheat-rice-arabidopsis` 只覆盖水稻/拟南芥。
   需要新增 `/api/homologs/triticeae`（或类似）才能替换 `/homologtools/index.html`。
2. **基因序列页是组合页**：`geneDetail_get_sequence.py` 同时输出 genome/CDS/protein
   三段；新 API 分开返回，需要前端组合（或新增一个聚合端点）后再替换。
3. **BLAST 聚合库别名损坏**：`all_genomes` / `all_gene` 的 `.nal` 引用了不存在的
   volume（例如 `HHHHHH_Hordeum_parodii_BCC2025.genome`、
   `HH_Hordeum_flexuosum_BCC2023.add_Description.cds`），CGI 和 API 都会失败。
   这与 CGI 迁移无关，但会影响序列服务，建议先修复别名或重建聚合库。
4. **低流量脚本**（gene_expression、co-expression、PPI、symap、gene_search*）
   有 JSON API，但参数/输出尚未逐项比对；可先保留 CGI，逐个验证后迁移。

## 建议的迁移顺序

1. 修复 `all_genomes` / `all_gene` 别名（或重建聚合库），确认新 API 的序列服务恢复。
2. 在 FastAPI 增加旧路径兼容层（例如 `/cgi-bin/get_fasta_bedtools.py`），
   保留旧响应格式，内部解析旧库名；用本次样本做逐字符回归。Apache 侧在
   `ScriptAlias` 前加 `ProxyPass` 指向 FastAPI，验证后再停用 CGI。
3. 新增 Triticeae 同源 API，替换 `/homologtools/index.html` 的调用。
4. 将 `geneDetail_get_sequence.py` 替换为前端组合的序列页。
5. 逐项验证 gene_expression / co-expression / PPI / symap / gene_search 的 API 映射。
6. 全部调用方迁移后，先让 `/cgi-bin/*` 返回 410 观察 30 天，再移除
   `ScriptAlias` 和目录；`.bak-*`、`wheat_dbpass.py`、`__pycache__`、`tmp` 先归档清理。

## 当前清理状态

- 已删除并归档：`snprimer_index.py`、`snprimer_index_bak.py`
  （见 `/var/www/data/masw_data/legacy_primerserver2_cgi_20261123.tar.zst`）
- 已归档并删除：`/var/www/html/primerserver2` 旧 Flask 应用
- 仍保留：`/var/www/html/snprimer`（约 7.1T 旧结果/流水线，待决定）
- 本文件只做盘点与替换验证，未改动服务端 CGI 目录。
