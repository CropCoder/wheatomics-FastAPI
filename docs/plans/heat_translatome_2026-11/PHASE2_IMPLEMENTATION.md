# Phase 2 实现说明：`/translatome/` 独立模块（原型）

- 日期：2026-11-11
- 关联：`PLAN.md`（总体计划）、`DATA_AUDIT.md`（数据体检）、`PAPER_CONTEXT.md`（论文核实）、`REPO_INTEGRATION.md`（仓库审计）
- 状态：**已上线生产（2026-11-11 16:20 CST）**：Phase 2 原型 + Phase 2.5（manifest/registry 驱动）均已部署；线上页面 https://wheatomics.sdau.edu.cn/translatome/ ；部署记录见 `DEPLOYMENT_2026-11-11.md`。本地验证覆盖 API、页面渲染（390/768/1024/1440 宽度 PASS）与 deep link；生产部署还差 Apache ProxyPass、导航/首页发布与一次线上验收（见 §6）。

---

## 0. 一句话

新增 `/translatome/` 页面与 `/api/translatome/*` 接口：输入 **02G 或 03G** 基因 ID，返回 5/10/15 DAA × CK/HS 的 RNA-seq FPKM、Ribo-seq FPKM、TE，并可浏览 11,343 个 DTG 与 21,964 个 DEG；每条记录**同时携带 02G 和 03G 两个 ID**（API 导出表同样双 ID）。

---

## 1. 文件清单

### 新增

| 路径 | 说明 |
|---|---|
| `app/api/routers/translatome.py` | 通用 REST 路由（datasets/meta/query/search/genes/tables/table/dtgs/degs/download），响应统一 `ok()` 信封 |
| `app/services/translatome.py` | Phase 2.5 通用数据层：读 registry/manifest，任意 stage/treatment/role/可选表，双 ID 解析、查询、搜索、表格过滤、下载 |
| `app/static/translatome/index.html` | 单页前端（原生 JS + Highcharts，无 jQuery/CDN 依赖） |
| `app/services/data/translatome/registry.json` | 数据集注册表（顺序/状态/版本） |
| `app/services/data/translatome/chen2025_cs_grain_heat/manifest.json` | 该数据集的阶段/处理/样本/角色/对照/可选表/引用/license（**随代码走**） |
| `app/services/data/translatome/chen2025_cs_grain_heat/build_report.json` | 构建校验（与论文 Table S1 最大差 0、映射覆盖等；随代码走） |
| `$TRANSLATOME_DATA_DIR/chen2025_cs_grain_heat/genes.tsv.gz` | 60,125 行 ×（双 ID + Description + 位置 + LC + 18 数值列），6.1 MB —— **仓库外** |
| `$TRANSLATOME_DATA_DIR/chen2025_cs_grain_heat/dtg.tsv.gz` | 11,343 行（Table S3 + 双 ID），381 KB —— **仓库外** |
| `$TRANSLATOME_DATA_DIR/chen2025_cs_grain_heat/deg.tsv.gz` | 21,964 行（Table S2 + 双 ID），979 KB —— **仓库外** |
| `scripts/heat_translatome/fetch_id_map.py` | 从 GeneHub interval API 拉全量 03G→02G 映射（可复现） |
| `scripts/heat_translatome/build_data.py` | 由源 xlsx + 论文补充表 + 映射生成 manifest/registry（仓库）与 .gz 资产（`--assets-root`，仓库外），含逐格校验 |
| `scripts/heat_translatome/test_registry_contract.py` | 契约测试：临时 registry+assets 双目录新建假数据集，证明不改代码即可加载/查询；校验缺资产提示；再回归真实数据集 |
| `scripts/heat_translatome/sync_assets.sh` | rsync 本地资产到服务器 `TRANSLATOME_DATA_DIR`（dry-run/delete 可选） |
| `docs/plans/heat_translatome_2026-11/PHASE2_IMPLEMENTATION.md` | 本文件 |
| `docs/plans/heat_translatome_2026-11/PHASE2_EXTENSIBILITY.md` | 多数据集扩展设计（manifest + registry，Phase 2.5 方案） |
| `docs/plans/heat_translatome_2026-11/DEPLOYMENT_2026-11-11.md` | 上线记录：服务器变更、验证结果、回滚与备份 |

### 修改

| 文件 | 改动 |
|---|---|
| `main.py` | 注册 `translatome` router；新增 `app.mount("/translatome", ...)`；`/translatome/` 纳入 no-cache 中间件；MCP 工具数文案 28→31 |
| `app/api/routers/__init__.py` | 导出 `translatome` router |
| `app/mcp/tool_specs.py` | 新增 3 个 MCP 工具（`list_translatome_datasets`、`query_translatome`、`list_translatome_dtgs`）+ MODULE_CATALOG 行；工具支持 `dataset` 参数 |
| `app/mcp/wheatomics_tools.py` | 注册上述 3 个工具的同步 dispatch（28→31 tools 注释） |
| `app/static/docpages/agent.html` | MCP 工具表新增 Translatome 三行；28→31 tools 文案 |
| `app/static/_v2/shell.js` | Tools 下拉新增 `Translatome` 菜单项（手动单行插入，未重跑 extract，见 §6 注意） |
| `app/static/blast2/index.html` | 同一菜单项同步到 canonical chrome 源文件 |

> **数据资产不提交 git**：约 7.8 MB 的 `.tsv.gz` 放服务器 `TRANSLATOME_DATA_DIR`（默认 `/var/www/data/translatome`，由 `app/core/config.py` / `.env` 配置）；仓库只保留 registry、manifest、build_report 与脚本。`.gitignore` 已排除 `app/services/data/translatome/**/*.tsv.gz`。

---

## 2. 数据资产与 02G/03G 映射

### 2.1 全量映射（本次完成，替换了抽样估计）

- 用 `scripts/heat_translatome/fetch_id_map.py` 遍历 GeneHub `Genefunc_CS_IWGSC03G_table`（30 Mb 分块，含 `chrUn`），得到 **266,760 个 03G 基因**的 02G 对应（与平台 CS2.1 注释规模一致）；
- 本数据集 60,125 个基因：**60,125/60,125 有 02G**，**0 缺失、0 个多对一冲突**（构建报告 `build_report.json` 可查）；
- 每个数据行同时保留 `gene02g` 与 `gene03g`；查询、表格、下载、DTG/DEG 表全部一致。

### 2.2 资产构建校验

`build_data.py` 在生成资产前做硬校验：

- 用户 xlsx 与 Genome Biology 2025 补充表 S1 的基因顺序、18 列 NA 模式、数值逐格比对：**最大绝对差 0.0**，否则拒绝构建；
- `genes=60,125`、`dtg=11,343`、`deg=21,964`，与论文补充表一致；
- TE 的 `NA` 一律写空值（加载后为 `None`），**不会变成 0**。

### 2.3 字段说明（`genes.tsv.gz`）

`gene02g, gene03g, description, chromosome, start, end, is_lc,`
`rna_5d_ck, rna_5d_hs, rna_10d_ck, rna_10d_hs, rna_15d_ck, rna_15d_hs,`
`ribo_5d_ck, ribo_5d_hs, ribo_10d_ck, ribo_10d_hs, ribo_15d_ck, ribo_15d_hs,`
`te_5daa_ck, te_5daa_hs, te_10daa_ck, te_10daa_hs, te_15daa_ck, te_15daa_hs`

**TE 语义**：`TE = mean Ribo FPKM / mean RNA FPKM`；RNA FPKM < 0.2 → 空值（n.a.）；Ribo=0 且 RNA ≥0.2 → 0（真实零值）。

**DEG 语义**：论文 Table S2 的 `Fold_change` 列实际是**有符号 log2FC（HS/CK）**，负值 = 热胁迫后降低（构建时已在 `meta.json.deg_note` 注明）。

---

## 3. API

基址 `/api/translatome`，响应统一 `{success, message, timestamp, data}`。

| 方法/路径 | 参数 | 返回 |
|---|---|---|
| `GET /datasets` | — | 数据集清单（id/title/species/tissue/stages/assays/counts/status） |
| `GET /meta` | `dataset`(可选) | 单数据集 manifest（样本、单位、TE 规则、来源/license/citation、可选表、计数） |
| `GET /query` | `gene_ids`（必填，最多 100 个；02G/03G 均可）· `dataset`(可选) | `genes_found`、`genes_not_found`、`results[]`：双 ID、位置、`stages[].metrics[]`（每个 role 的各处理值 + contrast Δlog2）、`table_hits` |
| `GET /search` | `q`、`limit`、`dataset` | 命中双 ID + 描述（精确优先，其次前缀，再次描述） |
| `GET /genes/{gene}` | 路径参数（02G/03G）· `dataset` | 单基因完整 payload；未找到 404 |
| `GET /tables` | `dataset` | 该数据集声明的可选表（DTG/DEG/未来的表） |
| `GET /table/{table_id}` | `dataset` + 表相关过滤参数 | 通用表格查询（dtg 用 stage，deg 用 comparison；自动按 manifest 字段语义解析） |
| `GET /dtgs`（兼容别名） | `stage`、`direction`、`cluster`、`gene`、`padj_max`、`page`、`per_page`、`dataset` | 等价于 `/table/<kind=dtg 的表>`，按 |log2FC| 降序 |
| `GET /degs`（兼容别名） | `comparison`、`direction`、`gene`、`padj_max`、`page`、`per_page`、`dataset` | 等价于 `/table/<kind=deg 的表>` |
| `GET /download/{dataset}/{file}` | 文件 id 来自 manifest.files（matrix/dtg/deg/…） | gzip TSV 附件（含双 ID） |
| `GET /download/{file}`（兼容别名） | 同上 | 默认数据集文件下载 |

错误约定：未知阶段/比较 → 400；未知基因 → 404；数据资产缺失 → 503（提示部署方式）。

### 实测示例

```bash
B=http://127.0.0.1:8011/api/translatome
curl -s "$B/query?gene_ids=TraesCS1A02G000300" \
  # genes_found=1; gene02g=TraesCS1A02G000300; gene03g=TraesCS1A03G0000600
curl -s "$B/query?gene_ids=TraesCS1A03G0000600.1,TraesCS5A02G391700,NOTAGENE" \
  # genes_found=2; genes_not_found=["NOTAGENE"]
curl -s "$B/search?q=TraesCS5A02G391700&limit=3"      # 精确命中排第一
curl -s "$B/dtgs?stage=15DAA&direction=up&per_page=2"  # total=3,302
curl -s "$B/degs?comparison=RNA_5&direction=down"      # total=3,466
curl -sI "$B/download/genes"                            # 6.1 MB, attachment
```

---

## 4. 前端 `/translatome/`

- **查询卡**：02G/03G 多基因输入（逗号/空格/换行）、示例 chip、错误提示；
- **结果卡**（每基因）：02G/03G 徽章、description/位置、LC 标记、DTG/DEG 徽章（自动标注显著阶段与 cluster）、GeneHub 外链、作者 browser 定位外链；
- **数据表**：RNA FPKM / Ribo FPKM / TE × 3 阶段 ×（CK/HS/Δlog2）；TE 缺失显示 `n.a.` 并有说明；
- **图**：Highcharts 双图 —— FPKM 分组柱状（RNA/Ribo × CK/HS × 3 阶段）、TE 折线（CK/HS，缺口不连线；全 NA 时显示说明文字）；
- **DTG 浏览**：阶段/方向/cluster/基因过滤 + 分页；"view" 直接回填查询；
- **DEG 浏览**：比较/方向/基因过滤 + 分页；
- **来源与引用**：12 文库元数据表（折叠在 Source & citation 内）、两篇论文链接、SRA、补充表、作者 browser、license、provenance；**页面不再展示整表下载按钮**，完整数据从论文补充表链接获取（`/api/translatome/download/*` 接口保留，供程序化访问）。
- deep link：`/translatome/?gene=TraesCS1A02G001800` 自动查询（便于 GeneHub/其他页面跳转）。

实测渲染（`scripts/spa_visual_check.sh`）：**390 / 768 / 1024 / 1440 宽度全部 PASS**，无横向溢出、无 JS 错误、无坏图；唯一 warning 是页脚 "Back to top" 触控高度（全站既有，非本页引入）。

Phase 2.5 契约测试：`python3 scripts/heat_translatome/test_registry_contract.py` → 用临时目录新建一个假数据集，**不改任何代码**即可被 `/datasets` 列出、被查询/搜索/下载；随后回归真实数据集（60,125 genes / 11,343 DTG / 21,964 DEG）通过。

---

## 5. MCP

新增 3 个工具（tools/list 自动包含，`/agent.html` 已同步表格与 31 tools 计数）：

| 工具 | 参数 | 说明 |
|---|---|---|
| `list_translatome_datasets` | — | 数据集清单（manifest/registry 驱动） |
| `query_translatome` | `gene_ids`, `dataset` | 02G/03G 均可，返回双 ID + manifest 定义的 stages/roles |
| `list_translatome_dtgs` | `dataset`, `stage`, `direction`, `cluster`, `gene`, `per_page` | 分页 DTG（双 ID、cluster、Padj、log2FC） |

> 同步改了 `app/mcp/tool_specs.py`、`app/mcp/wheatomics_tools.py`、`app/static/docpages/agent.html`、`main.py` 里的 28→30 文案。

---

## 6. 部署步骤（生产）

1. **代码/静态页**：正常 `git pull` 部署代码（仓库只含 registry + manifest + SPA/路由；不含 .gz）。
2. **数据资产**：把 `.gz` 放到服务器 `TRANSLATOME_DATA_DIR/<dataset_id>/`：
   ```bash
   # 方式 A：从本地 build 目录 rsync
   TRANSLATOME_DATA_DIR=~/wheatomics/translatome_data \
     bash scripts/heat_translatome/sync_assets.sh <ssh-target> /var/www/data/translatome
   # 方式 B：服务器上用 build_data.py 现场生成（需源 xlsx/补充表/映射）
   ```
   在服务器 `.env` 设置 `TRANSLATOME_DATA_DIR=/var/www/data/translatome`，然后 `sudo systemctl restart wheatomics-api`；
   `curl .../api/translatome/datasets` 应显示 `"assets_ready": true`。
3. **Apache**：新增顶层路径需要两条 ProxyPass（SSL 与非 SSL 两个 conf 都加）：
   ```apache
   ProxyPass        /translatome http://127.0.0.1:8000/translatome
   ProxyPassReverse /translatome http://127.0.0.1:8000/translatome
   ```
   然后 `sudo apachectl restart`；`/api/translatome/*` 走已有 `/api` 代理，无需额外规则。
4. **导航/首页**：`app/static/_v2/shell.js` 已手动加 Tools→Translatome；首页工具卡（`/var/www/html/index.html` 与 `/V2.0/index.html`，不在仓库）用 `scripts/update_v2_home_nav.py` / 手工补一张 Translatome 卡。
5. **验收**：
   ```bash
   curl -s https://wheatomics.sdau.edu.cn/api/translatome/meta | head
   curl -s "https://wheatomics.sdau.edu.cn/api/translatome/query?gene_ids=TraesCS5A02G391700"
   curl -sI https://wheatomics.sdau.edu.cn/translatome/           # 200 (Apache → FastAPI)
   bash scripts/spa_visual_check.sh https://wheatomics.sdau.edu.cn/translatome/ \
     --label translatome-online --fill '#gene-input=TraesCS1A02G001800' --click '#query-btn' \
     --wait '#result-area .tl-charts'
   ```
6. **回滚**：删 `app/static/translatome/`、撤 `main.py` 的 router/mount、回退 shell.js/agent.html/blast2 一行、重启 API + Apache；静态数据无 DB 写入，回滚无残留。

### ⚠️ shell.js 注意

本次**没有**重跑 `scripts/extract_v2_shell.py`：仓库里的 `app/static/blast2/index.html` 与当前 `_v2/shell.js` 已有漂移（当前 shell 含 Neighborhood / TF Atlas / scRNA 链接等，而 blast2 源页较旧），直接重跑会把线上菜单回退。因此 Translatome 菜单项是**手动单行插入 shell.js**，并把同一条加到 blast2 canonical 源页。以后若从正确的 canonical chrome 重新生成 shell.js，请确认包含本项。

---

## 7. 仍待办 / 后续

- **数据授权**：GB 2025 为 CC BY-NC-ND 4.0、PlCell 非 OA；上线前按 `PLAN.md` 附录 B 取得通讯作者书面同意，页面已带 license 说明。
- **是否进 MySQL**：当前 Phase 2 原型用静态资产（零 DB 依赖、易回滚）。若平台要求统一走 `gene_expression` 库，可按 `PLAN.md` §5.2 建表（`genes`/`dtg`/`deg` 三张，列结构同 TSV）并把 service 换成 SQL 查询；接口与前端无需改。
- **Phase 1（expression 3 项目）仍可并行做**：把 RNA/Ribo/TE 作为 3 个 expression 项目 + `project_meta.unit` 字段，基因页/MCP 自动可见；与本模块不冲突（详见 `PLAN.md` Phase 1）。
- **功能增强**：按 cluster/方向过滤已支持；后续可加 uORF/lORF（Table S4/S6/S8）、作者 JBrowse 覆盖度互链的批量跳转、下载 TSV 的 README、基因页/共表达联动。
- **多数据集扩展（Phase 2.5 已完成）**：service/API/前端已改为 registry + manifest 驱动；新增数据集 = 数据文件夹 + manifest + registry 一行，无需改代码（契约测试已覆盖）。builder 仍是本数据集专用，后续可补通用 builder 或按需手写 manifest。
- **本地测试限制**：当前 `.venv` 缺 `mcp` 与生产 DB 依赖，`main.py` 无法完整启动；本地用最小 ASGI harness 验证 router + SPA（同一套路由和静态页）。生产环境依赖齐全，普通重启即可。

---

## 8. 复现命令

```bash
# 1) 全量 03G->02G 映射（约 5-8 分钟，只读 GeneHub API）
python3 scripts/heat_translatome/fetch_id_map.py \
  --out /tmp/gene_map_03g_02g.tsv --genes /tmp/genes_03g.txt

# 2) 构建资产（需用户 xlsx + GB 2025 补充表 xlsx）
python3 scripts/heat_translatome/build_data.py \
  --data-xlsx "/path/to/5_10_15DAA...TE.xlsx" \
  --supplementary-xlsx "/path/to/13059_2025_3848_MOESM2_ESM.xlsx" \
  --mapping-tsv /tmp/gene_map_03g_02g.tsv \
  --registry-root app/services/data/translatome \
  --assets-root /path/to/translatome_data \
  --dataset-id chen2025_cs_grain_heat

# 契约测试（新数据集零代码 + 真实数据回归）
python3 scripts/heat_translatome/test_registry_contract.py

# 3) 本地跑模块（生产用 uvicorn main:app --port 8000）
TRANSLATOME_DATA_DIR=/path/to/translatome_data uvicorn main:app --host 0.0.0.0 --port 8000
```
