# `/translatome/` 多数据集扩展设计（回答"以后加新数据怎么展示"）

- 日期：2026-11-11
- 关联：`PHASE2_IMPLEMENTATION.md`（当前原型实现）、`PLAN.md`（总体计划）、`DATA_AUDIT.md`（数据集准入体检）
- 结论：**需要考虑，而且建议在添加第二个数据集之前就做一次"manifest + registry 驱动"的小重构**。当前原型是单数据集写死的，加新数据要改代码；重构后，新数据 = **一个数据文件夹 + 一个 manifest + registry 里一行**，前端/API 不用动。

---

## 0.5 实施状态（Phase 2.5 已完成，2026-11-11）

本设计中的 2.5 阶段已落地，当前代码已变成 manifest + registry 驱动：

| 项 | 状态 |
|---|---|
| 数据布局：仓库 `app/services/data/translatome/{registry.json,<dataset>/manifest.json}`；资产在 `$TRANSLATOME_DATA_DIR/<dataset>/` | ✅ 已迁移；`.gz` 不再进仓库（`.gitignore` 排除），缺资产时 `/datasets` 返回 `assets_ready=false` |
| 通用 service `app/services/translatome.py` | ✅ 不再有 `STAGES/DEG_COMPARISONS/GENE_VALUE_COLS` 常量；stage/treatment/role/表全部读 manifest；支持 `TRANSLATOME_DATA_DIR` |
| 通用 API | ✅ 新增 `/datasets`、`/tables`、`/table/{id}`、`/download/{dataset}/{file}`；所有端点支持 `dataset`（缺省=第一个可见数据集）；旧 `/dtgs` `/degs` `/download/{file}` 保留兼容 |
| 通用前端 | ✅ 数据集选择器（只有 1 个时隐藏）、标题/统计/阶段/处理/表/下载/citation 全部由 manifest 渲染 |
| 新数据集零代码证明 | ✅ `scripts/heat_translatome/test_registry_contract.py`：临时目录新建假数据集，不改代码即完成列出/查询/搜索/下载；再回归真实数据集 |
| 未来新增数据集 | 数据文件夹 + manifest + registry 一行；构建资产可用本数据集的专用 builder 或后续通用 builder |

**尚未做（按需）**：数据集中心卡片页（>5 个时）、跨数据集比较、MySQL 化、通用 builder。这些都不影响当前"加数据集不改代码"的能力。

多数据集效果截图见 `screenshots/translatome-multi-dataset.png`（第二个 `test_tiny` 数据集由契约测试临时生成，用于演示选择器与 manifest 动态渲染）。

---

## 0. 先分清"新数据"的三种情况

| 情况 | 例子 | 期望的展示方式 | 需要改什么 |
|---|---|---|---|
| **A. 同一实验新增样本/条件** | 再加 20 DAA、热胁迫 2 h、加重复 | 在当前数据集里多出对应的阶段/处理 | manifest 的 `samples` 增加；宽表重建（build 脚本按 manifest 生成） |
| **B. 新实验/新论文/新材料** | 另一个品种、另一个组织、另一个胁迫，或同一课题组新发 Ribo-seq | `/translatome/` 下多一个数据集：选择器/卡片切换；每个数据集有自己的标题、样本、引用、license、下载 | 数据文件夹 + manifest + registry 一行 |
| **C. 新数据类型** | uORF/lORF、蛋白组、polysome、更多差异表 | 作为该数据集的"附加表"（当前 DTG/DEG 就是这种） | manifest 里声明表格；页面自动多一个 tab/表格 |

设计目标就是让 A/B/C 三种情况都**不用改 Python/HTML 代码**。

---

## 1. 改造前实现的写死点（历史记录，Phase 2.5 已消除）

| 文件 | 写死内容 | 新数据来了会怎样 |
|---|---|---|
| `app/services/heat_translatome.py:28` | `DATA_DIR = .../data/heat_translatome` 单目录 | 第二个数据集无处安放 |
| `:30-34` | `STAGES = ["5DAA","10DAA","15DAA"]`、标签、TE 键映射 | 新阶段/新处理直接失效 |
| `:35-44` | `DEG_COMPARISONS` 六个比较写死 | 新比较类型不支持 |
| `:45-52` | `GENE_VALUE_COLS` 18 列写死 | 样本列数一变就错位 |
| `:178-181` | `load_dataset()` 单例 + 固定 `meta.json` | 只能加载一个数据集 |
| `:452-461` | 下载文件名写死 | 新数据集下载要改代码 |
| `app/api/routers/translatome.py:94,123` | `stage`/`comparison` 默认值与枚举写死 | 新数据集参数不匹配 |
| `app/static/translatome/index.html:90-97,183,223` | 标题、统计数字、阶段/比较下拉、下载名写死 | 页面文案与选项错位 |

> 这些是 Phase 2 原型阶段的写死点；**Phase 2.5 已全部改为 manifest 驱动**（见 §0.5），以上清单仅作为设计依据保留。

---

## 2. 目标架构：三层，代码与数据解耦

```
数据层：app/services/data/translatome/
          registry.json                  ← 数据集清单（顺序、状态、manifest 路径）
          <dataset_id>/
            manifest.json                ← 这个数据集的全部元数据（见 §3.3）
            genes.tsv.gz                 ← 基因 × 样本 宽表（列顺序 = manifest.samples）
            dtg.tsv.gz / deg.tsv.gz      ← 可选附加表（manifest.tables 声明）
            README.md / checksums        ← 出处、许可、校验
服务层：app/services/translatome.py      ← 读 registry/manifest，按 dataset_id 懒加载
接口层：app/api/routers/translatome.py   ← 通用端点 + ?dataset=<id>
页面层：app/static/translatome/index.html ← 数据集选择器 + 由 manifest 动态渲染
```

### 2.1 `registry.json`（示例）

```json
{
  "schema_version": 1,
  "datasets": [
    {
      "id": "chen2025_cs_grain_heat",
      "title": "Heat-stress developing grain translatome (5/10/15 DAA, CK vs 42 °C 1 h)",
      "short_title": "Grain heat-stress translatome",
      "species": "Triticum aestivum cv. Chinese Spring",
      "tissue": "developing grain",
      "status": "prototype",
      "order": 10,
      "manifest": "chen2025_cs_grain_heat/manifest.json",
      "version": "v1",
      "updated": "2026-11-11"
    }
  ]
}
```

`status` 建议：`draft`（内部预览）→ `prototype`（可访问、未正式发布）→ `public`（对外）→ `retired`（被新版本替代，保留不显示在主列表）。

### 2.2 目录与版本

```
data/translatome/
  registry.json
  chen2025_cs_grain_heat/
    manifest.json
    genes.tsv.gz dtg.tsv.gz deg.tsv.gz
```

- 版本升级：`chen2025_cs_grain_heat/v2/` + registry 里 `version: "v2"`；旧版本保留（复现用），registry 决定显示哪个。
- 全局基因 ID 映射（03G↔02G）只维护一份（`scripts/heat_translatome/fetch_id_map.py` 生成的表），每个数据集 build 时 join，避免各自为政。

---

## 3. 数据规范

### 3.1 宽表规则（保持简单）

每个数据集一张 `genes.tsv.gz`：

- 前 7 列固定：`gene02g, gene03g, description, chromosome, start, end, is_lc`；
- 之后每列对应 `manifest.samples[]` 中的一个样本，**列顺序 = manifest 顺序**（不再写死列名数组）；
- 值统一 FPKM（或 manifest 声明的单位），TE 用 `te_<sample>` 单独列或由 service 按 manifest 的 paired 设计实时算；
- 缺失一律空值（`null`），绝不填 0。

### 3.2 `manifest.json` 关键字段

```json
{
  "id": "chen2025_cs_grain_heat",
  "title": "...", "short_title": "...",
  "species": "Triticum aestivum", "cultivar": "Chinese Spring",
  "genome": "IWGSC RefSeq v2.1 (03G) + platform 02G",
  "tissue": "developing grain",
  "stages":   [{"id":"5DAA","label":"5 DAA","days_after_anthesis":5}, ...],
  "treatments":[{"id":"CK","label":"Control","protocol":"-" },
                {"id":"HS","label":"42 °C 1 h","protocol":"42 °C, 1 h, sampled immediately"}],
  "assays": ["RNA-seq","Ribo-seq"],
  "samples": [{"id":"rna_5d_ck","label":"RNA 5DAA CK","assay":"RNA-seq",
               "stage":"5DAA","treatment":"CK","n_reps":3,"sra_runs":[...]}],
  "units": {"rna":"FPKM","ribo":"FPKM","te":"ratio"},
  "derived": [{"id":"delta_te","numerator":"HS","denominator":"CK",
               "value":"te","label":"Δlog2 TE (HS/CK)"}],
  "tables": [
    {"id":"dtg","file":"dtg.tsv.gz","label":"Differentially translated genes",
     "kind":"dtg","stage_field":true,"direction":"log2fc"},
    {"id":"deg","file":"deg.tsv.gz","label":"Differentially expressed genes",
     "kind":"deg","comparisons":["RNA_5","RNA_10","..."]}
  ],
  "rules": {"te_rule":"...", "deg_note":"...", "replicates":"..."},
  "counts": {"genes":60125,"dtg":11343,"deg":21964},
  "sources": [{"role":"heat","citation":"...","doi":"...","bioproject":"..."}],
  "license": {"...":"..."},
  "links": {"authors_browser":"...", "supplement":"..."},
  "version": "v1", "generated": "2026-11-11"
}
```

service 只依赖这份 manifest：阶段/处理/样本/单阶段比较/附加表/文案全部由它生成；**不再出现任何 `STAGES`/`DEG_COMPARISONS` 常量**。

### 3.3 附加表（DTG/DEG/uORF…）

manifest 的 `tables[]` 描述可选表格（文件、类型、字段语义）。前端只渲染 manifest 里存在的表；以后加 uORF/lORF 表只需加一个 `tables` 项 + 一个文件，不需要新页面。

---

## 4. API 设计（向后兼容）

| 端点 | 说明 |
|---|---|
| `GET /api/translatome/datasets` | 数据集清单（id、标题、物种、组织、assay、状态、版本、计数） |
| `GET /api/translatome/meta?dataset=<id>` | 单数据集 manifest（缺省 = registry 中第一个 public） |
| `GET /api/translatome/query?gene_ids=...&dataset=<id>` | 同现有返回；`dataset` 可省略 |
| `GET /api/translatome/search?q=...&dataset=<id>` | 同现有；另可 `scope=all` 跨数据集搜索（结果按数据集分组） |
| `GET /api/translatome/tables?dataset=<id>` | 可选表清单（前端渲染 DTG/DEG 等面板） |
| `GET /api/translatome/table/{table}?dataset=<id>&...` | 通用表格查询（当前 `/dtgs`、`/degs` 变成它的特例） |
| `GET /api/translatome/download/{dataset}/{file}` | 数据集级下载 |
| `GET /api/translatome/compare?gene_ids=...&datasets=a,b` | （Phase 3）跨数据集同基因比较，仅当单位/阶段编码兼容 |

所有端点默认 `dataset` 取 registry 第一个 public 数据集，因此**当前前端不改也能工作**，可分步迁移。

---

## 5. 展示设计（UI）

### 5.1 第一阶段：选择器（数据集 2–5 个时）

- 页面顶部加一个 `Dataset` 下拉：选项来自 `/api/translatome/datasets`；
- URL 同步 `?dataset=<id>`（可分享/收藏）；
- 标题、副标题、统计数字（genes/DTG/DEG）、阶段下拉、比较下拉、下载名、citation/license 全部由 manifest 渲染；
- 只有一个 public 数据集时选择器自动隐藏（保持当前页面观感）。

### 5.2 第二阶段：数据集中心（>5 个或类型差异大时）

- `/translatome/` 变成"数据集中心"：卡片列表（标题、物种/组织、阶段、assay、数据量、状态、引用），点击进入 `/translatome/?dataset=<id>` 或独立路径；
- 每张卡带 `status` 标记（draft/prototype/public/retired），避免用户误用未发布数据。

### 5.3 跨数据集比较（慎重）

- 只有**阶段/处理词汇对齐**（如都用 `5DAA`、`CK`/`HS_42C_1H`）且**TE 定义一致**时才允许并排比较；
- 单位不同（FPKM vs TPM）或 TE 定义不同（Ribo/RNA vs Poly/RNA 的 translation state）时只做"分开展示 + 明确标注"，绝不静默合并；
- `scope=all` 搜索可以跨数据集，但结果要显示来源数据集。

---

## 6. 新增数据集的 SOP（可复制）

1. **准入体检**（复用 `DATA_AUDIT.md` 清单）：来源/DOI/SRA、license、重复数、TE 定义、低表达阈值、NA 规则；
2. **基因 ID 映射**：用 `scripts/heat_translatome/fetch_id_map.py`（全局映射表复用），join 出 02G/03G，检查覆盖率与多对一（目标 ≥98%、冲突人工裁定）；
3. **打数据包**：`build_data.py` 泛化为按 manifest 生成 `genes.tsv.gz` + 可选表；生成 checksums；
4. **写 manifest**：阶段/处理/样本/单位/TE 规则/引用/license/下载文件；
5. **注册**：`registry.json` 加一行（或未来 DB 表一行），`status` 先 `draft`；
6. **验收**：API 冒烟 + 页面多宽度渲染（390/768/1440）+ 与源数据抽查比对；
7. **发布**：状态改 `public`，补 citation/首页入口，记录 release note（日期、版本、变更）。

---

## 7. 存储与规模策略

| 规模 | 建议 |
|---|---|
| 1–3 个数据集（每个 ~5–10 MB） | 继续静态 gz 资产（当前方案），随代码部署；简单、零 DB、易回滚 |
| 4–10 个 | **已采用**：资产放服务器数据目录（`TRANSLATOME_DATA_DIR`，默认 `/var/www/data/translatome/`），仓库只保留 manifest/脚本；rsync 工具 `scripts/heat_translatome/sync_assets.sh` |
| >10 个或需要管理后台/复杂统计 | 进 MySQL：`translatome_dataset`（注册表）+ `translatome_sample`（样本）+ `translatome_value`（长表：dataset_id, gene02g, sample_id, value）或每数据集宽表；接口层不变 |

> 单数据集基因 × 样本约 60k×18 ≈ 108 万个数；长表存 MySQL 完全可行（加 `(dataset_id, gene02g)` 索引）。前端/接口不需要随存储切换而改。

---

## 8. 迁移路线与工作量

| 步骤 | 内容 | 工作量 |
|---|---|---|
| **Phase 2.5（已完成 2026-11-11）** | manifest + registry 驱动：service/API/前端通用化 + 契约测试 | ✅ 已完成 |
| Phase 3 | 数据集中心卡片页（>5 个时）+ 跨数据集搜索/比较 | 0.5–2 人日 |
| 可选 | MySQL 化 + 管理后台（非开发者上传/发布） | 1–2 人日 |

**为什么现在做最划算**：只有 1 个数据集时改动面最小、回归成本最低；等第二个数据集来了再改，就要同时动数据、接口、页面，容易把已上线的数据集改坏。本次已按此判断在第二个数据集到来前完成。

---

## 9. 推荐结论

1. ~~先做 Phase 2.5（manifest + registry 化）~~ ✅ 已完成；
2. 第二个数据集按 §6 SOP 接入，页面只多一个选择器项；
3. 数据集数量到 5 个以上再考虑"数据集中心 + MySQL"，不要提前过度设计；
4. 从第一个数据开始就强制的三条纪律：**双 ID（02G+03G）+ manifest 里写清 TE 定义/NA 规则 + 每个数据集独立 citation/license**。

> Phase 2.5 已完成并通过契约测试；下一步是第二个数据集接入时的实操（按 §6 SOP），以及数据集数量上来后的 Phase 3（中心页/跨数据集/MySQL）。
