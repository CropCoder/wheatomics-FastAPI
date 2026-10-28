# KnownGene v2055 — 后端/DB 迁移与 API 设计方案

> 调查员：backend-db（task-2）｜阶段：**只读调查 + 方案**（本文件不含任何实际执行动作）
> 事实基线：`docs/known_genes/CONTEXT.md`（Lead 维护）+ Lead 2026-10-28 代查的生产库事实（§1.2）
> 新数据：`/Users/mashengwei/Desktop/markdown/陈甜甜/known-gene-paper-20260916/已知基因逐条提取清单_20261019-合集_修正版v2055_20261019.xlsx`
> 证据：`docs/known_genes/_evidence/current_api_known_all.json`（线上 520 行快照）
> 依赖：`docs/known_genes/data_profile_v2055.md`（data-profiler，task-1）只用于「296 物种串→受控 token 映射表」与受控词表；本文件对每个依赖点都写明了接口，未拿到时按 §2.6 的兜底规则实现。

---

## 0. 结论摘要（TL;DR）

1. **DDL 可以做到"零破坏 + 幂等可回滚"**：只做**追加列 + 两列加宽 + 4 个前缀索引**；不做 charset 转换、不改既有列序、不改 `key_result` 类型。完整 DDL 见 §4.2，已按生产 `sql_mode=STRICT_TRANS_TABLES` / 库默认 `latin1` / 应用账号无 DDL 三点校准。
2. **两段式迁移是唯一可行路径**：root 阶段（DDL + 备份表 + staging 表 + mysqldump）；应用账号阶段（校验 → staging → **单事务 `DELETE FROM` + `INSERT ... SELECT`**，**禁止 TRUNCATE**，因为应用账号无 TRUNCATE/DROP 权限且 TRUNCATE 隐式提交）。
3. **`publication_year` 保持 `year(4)` 存"最早年份"，新增 `publication_years VARCHAR(64)` 存原始多值（`###` 连接）**——旧 API/前端/backfill 脚本全部零改动，多值信息不丢。理由与备选见 §4.4。
4. **`utf8 → utf8mb4` 本轮必须放弃**：不是"不必要"，而是**物理上会失败**——按现有列定义转 utf8mb4 后行声明长度 = 73,470 B > 65,535 B，`ALTER` 直接报 ERROR 1118（除非先把 `key_result` 改 TEXT，而本轮没有必要）。数据实测 0 个 BMP 外字符（§2.1）。
5. **API 4+1 端点全部按 CONTEXT §4 契约落地**，并补三处契约缺口：`search.field` 白名单需补 `chrom_pos`（现前端下拉已有该选项）；`/known/stats` 必须注册在 `/known/{gene_id}` **之前**；`references[]` 需允许 `doi: null`（v2055 有 1 行 4 题名/3 DOI，第 4 条只有题名）且新增 `year` 键。
6. **代码影响面很小**：真正要改的只有 `app/api/routers/gene.py`、`app/schemas/gene.py`、`app/services/legacy_parsers.py` 3 个文件；`main.py` 只需（可选）改 OpenAPI 描述文案；CGI 4 个脚本、`scripts/backfill_publication_year.py`、`scripts/scan_gene_annotations.py` **零改动**；`scripts/import_cloned_genes.py` 保留但不适用于本次整表替换。
7. **必须修的后端 bug（顺带修）**：
   - ① `normalize_text()` 会把新数据里的 `#` 全部替换成 `'`（受影响 49 行，如 `T7AS-7S#1S`→`T7AS-7S'1S`、`lines #1 and #2`）。不能全局改 `normalize_text`（其它 15 个库依赖旧行为），必须在 known 端点里按行判别：`reference_genome_id IS NULL` → 旧数据/legacy，否则新数据原样返回（§2.4/附录B）。
   - ② `/known/search` 的 SQL **没 SELECT `publication_year`**，而响应模型读 `row.get("publication_year")` → 线上该字段恒 `null`（既有 bug，Lead 已确认）。修复 = SELECT 列表补该列（不改变旧键）。
   - ③ CGI `gene_search_by_id.py` 用 `SELECT *` 的**位置下标** `ele[0..11]` 读列 → 新列只允许**追加在末尾**（位置约束，§4.6）。
8. **clone_id 稳定映射（生产实测，Lead 2026-10-28 代查）**：旧库 461 行 v2.1(02G) + 10 行 v1；新数据 1291 行 v3(03G)；**直接 gene_id 匹配仅 7–10 行**。经 `Genehub_DB.GenePageIWGSCv1_table`（应用账号有 SELECT，列 `GeneIDv1/v2/v3`）把旧 v1/v2→v3 后 **继承 321/520 = 62%**，**199 个旧 clone_id 成为孤儿**（外部深链 404）。方案给两个选项：**A. 新增 `cloned_gene_tbl_legacy` 只读回退表 + `/known/{id}` 兜底返回旧行**（旧链仍可用，代码 +0.5–1h）；**B. 接受 404**（成本 0，需发布说明）。→ §2.3/§5.3/§5.8/§8.4/附录D-Q3。
9. **/known/all 迁移后 1.12 MB（gzip 180 KB）**，是现在 98 KB 的 11.5 倍；`/search?searchid=wheat` 最坏 932 KB（gzip 174 KB）。GZipMiddleware 已启用，可接受，但 Stats tab 必须切到 `/known/stats`；`limit/offset` 加成可选参数并保持默认全量（§6.6）。
10. **对 CONTEXT.md 的修正 6 处**（含"新 gene_id 全部可通过 ensure_gene_like"为假、chrom_pos "37 种标签"实为 38、"positional 一一对应"有 16 行不成立），详见 §附录C。

---

## 1. 事实基线

### 1.1 新数据（本地用 pandas/openpyxl 实测 v2055，1420 × 17）

所有 17 列 **100% 非空**；无 tab/newline/CR、无 4 字节（BMP 外）字符、无控制字符。逐列最大长度（字符 = 字节，因全 BMP）：

| Excel 列（简称） | max chars | 现 DB 列 / 类型 | 是否溢出 | 目标处理 |
|---|---|---|---|---|
| gene_id | 28 | `gene_id varchar(300)` | 否 | 不变 |
| 参考基因组ID | 42 | —（新列） | — | `reference_genome_id varchar(100)` |
| gene_name | 43 | `gene_name varchar(500)` | 否 | 不变 |
| 物种信息 | **668** | `gene_species varchar(500)` | **是（60 行 >500）** | 加宽 `varchar(1000)` |
| chrom_pos | 41 | `chrom_pos varchar(500)` | 否 | 不变（新增内部 `chromosome` 列，§4.2） |
| gene_phenotype | **1677** | `gene_phenotype varchar(1000)` | **是（99 行 >1000）** | 加宽 `varchar(2000)` |
| key_result | 3051 | `key_result varchar(15000)` | 否 | **保持 varchar(15000)**（§4.5） |
| function_description | 2236 | `function_description text` | 否 | 不变 |
| 蛋白家族 | 2657 | —（新列） | — | `protein_family TEXT` |
| cloning_method | 51 | `cloning_method varchar(255)` | 否 | 不变 |
| cloning_method_description | 1757 | `cloning_method_description text` | 否 | 不变 |
| 验证方法 | 2114 | —（新列） | — | `validation_method TEXT` |
| 研究策略 | 16 | —（新列） | — | `research_strategy varchar(32)`（3 受控值） |
| 功能大类 | 32 | —（新列） | — | `functional_category varchar(64)`（5 受控值） |
| title | 473 | `paper_title text` | 否 | 存储时 `; `→`###`（§3.3） |
| doi | 82 | `paper_doi text` | 否 | 存储时 `; `→`###`（§3.3） |
| publication_year | 16 | `publication_year year(4)` | **是（115 行多值）** | 见 §4.4：`year` 存最早年份 + 新列 `publication_years` |

### 1.2 生产库 + Excel 的交叉事实（Lead 2026-10-28 代查）

| 项 | 值 | 对方案的约束 |
|---|---|---|
| MySQL | 5.7.33 | 无窗口函数、无 `JSON_TABLE`、无 functional index；`REGEXP` = POSIX ERE |
| `sql_mode` | 含 `STRICT_TRANS_TABLES`、`ONLY_FULL_GROUP_BY` 等 | **超长/越界直接报错**（不会静默截断）→ 导入前离线校验是硬前提；stats 的 GROUP BY 必须全分组 |
| 库默认 charset | `latin1` / `latin1_swedish_ci`（表显式 utf8） | **root 建任何新表必须显式 `DEFAULT CHARSET=utf8`，或直接 `CREATE TABLE ... LIKE cloned_gene_tbl`**（LIKE 继承表 utf8），否则 staging/备份表会掉进 latin1 |
| 表 | `InnoDB`，`utf8/utf8_general_ci`，无二级索引，DATA_LENGTH 3.67 MB | LIKE 建表安全；索引只有 PK |
| 行数 / AUTO_INCREMENT | 520 / 527；clone_id 1–526（缺 6 个） | 新行 clone_id 从 527 起，与 AUTO_INCREMENT 自然衔接 |
| 应用账号权限 | `wheatomics_user@localhost`：`SELECT,INSERT,UPDATE,DELETE,EXECUTE,SHOW VIEW` on `cloned_gene_db`；**无 CREATE/ALTER/DROP/TRUNCATE** | 两段式：DDL 必须 root；数据阶段只能 DELETE+INSERT（事务内）；备份表/staging 只能 root 建；`mysqldump --single-transaction` 可用（仅需 SELECT） |
| `author`/`author_mail` | `varchar(100)/varchar(200) NOT NULL`，**无 DEFAULT** | 插值时显式写 `''` 即可（strict 模式允许空串），**不必** ALTER 这两列；或在 DDL 里加 `DEFAULT ''`（可选，§4.2 注释） |
| `pmid` 列 | **不存在** | 本次不加（v2055 无 PMID 列）；`import_cloned_genes.py --ensure-pmid-column` 保持现状 |
| 旧行最大长度 | gene_id 38 / gene_name 48 / chrom_pos 45 / gene_phenotype 93 / gene_species 30 / paper_title 8110 / paper_doi 116 / key_result 15000 / function_description 142 / cloning_method_description 124 / max(pub_year)=2026 | 佐证现 varchar 余量；`key_result` 旧数据已顶满 15000 |

### 1.3 本地实测的补充事实（后端/DB 直接相关）

| 事实 | 测量值 | 影响 |
|---|---|---|
| `ensure_gene_like` 失败行 | **gene_id 1 行**（`Yr87/Lr85`，含 `/`）；**gene_name 50 行**（34 行含 `/`、9 行含 `;`、2 行含空格）；reference_genome_id 1 行（`Ae.longissima_6S_ORF:51,756,423-51,772,629`，含逗号） | 详情页按 clone_id 走没问题；`/known/{gene_id}` 无法查询这 1 个 gene_id；参考基因组 ID 不能无脑做 GeneHub 外链（前端需先做格式判定） |
| `#` 字符 | 物种 3 行 / 表型 13 / key_result 14 / function_desc 10 / 蛋白家族 7 / 克隆描述 23 / 验证方法 19 行 | `normalize_text()` 会把 `#`→`'`，必须在 known 端点按行判别（§2.4/附录B） |
| `###` / `####` | 全部 17 列均 0 处 | 可安全用 `###` 做 legacy 多值连接符（与 CGI 兼容） |
| HTML 标签 | validation_method 3 行含 `<...>`；全表 58 行含 `<` 或 `>`（多为 `>350 isolates`、`C>G`、`<70%` 等比较符，不是真 HTML） | API 原样返回，前端统一 `esc()`；旧 CGI 不显示这些列 → 无 XSS 面 |
| 多值位置对应 | title/doi/year 三段计数组合：`(1,1,1)=1290, (2,2,2)=95, (3,3,3)=19, (2,2,1)=12, (1,2,1)=3, (4,3,3)=1` → **16 行不自洽（1.13%）** | 导入不能因这 16 行失败；requiring 严格相等会丢掉整行 → 采用"按 max 补齐 + 单年份复制"规则（§5.2、§6.4） |
| DOI 合法性 | `^10\.\d{4,9}/\S+$` 全部 100% 通过（含多值拆开后） | DOI 校验可作为硬校验 |
| 年份 | 全部 4 位数字，1998–2026；多值行 115 行；**47 行多值不是升序** | `publication_year = min(years)`（取最早，而非第一项）；`publication_years` 保留原顺序 |
| 染色体 | 归一化 token **38 种**：小麦 21 种（1325 行）、大麦 1H–7H（80 行）、1R(4)/6R(1)/7E(2)/1S(2)/6S(1)/2V(1)/6V(1)/6U(1)、`54`/`51`（T.ponticum 2 行）；**chrom_pos 原文 1389 种**，格式如 `Refv1.0 chr7A:112.264-112.266Mb` / `AetTA1675 2D:2.33-2.45Mb` / `T.ponticum.v1 chr54:437.839-437.843Mb` | **by-chromosome 不能再用 `chrom_pos LIKE '5A%'`**（新格式前缀是品种/版本名）→ 新增内部规范化列 `chromosome`，无列 fallback 见附录A |
| 物种 | 原始 296 串；1130 行是干净二名法，290 行带材料长描述；1787 个 `;` 分隔的物种段（263 行多物种） | `species_primary` 需受控映射（296→21/22），覆盖面必须 100%（§2.6） |
| 去重口径 | gene_id：23 组/48 行（max 3）；reference_genome_id：30 组/64 行（max 3，D7 预期）；`(gene_id,refid,name)`：仅 1 组 3 行（TaVRN-A1，D2 按 3 篇文献拆行，DOI 不同）；**整行指纹 1420/1420 唯一** | 唯一性验收口径 = 「整行指纹唯一」，而不是 gene_id/name 唯一；自然键建议 `(gene_id, reference_genome_id, gene_name, paper_doi)` |
| 表型分词 | `;` 拆出 2956 段 / 2101 个不同段；首段 Top：Drought tolerance 39、Salt tolerance 32、Stripe rust resistance 31、Powdery mildew resistance 18、Heat tolerance 9 | 旧 Stats "Top15 表型"（精确值聚合）迁移后几乎全是 1–2 次 → 语义作废，stats 改为受控维度 + 首段标签（§6.5） |
| 验证方法 | 8253 个 `;` token / 2896 distinct；Top：Expression analysis 738、Phenotyping 648、Overexpression 368、Subcellular localization 332、Transgenic transformation 322、VIGS 219 | `validation_methods[]` 按 `;` 拆分，不做受控归一（受控表见 task-1） |

---

## 2. 数据事实复核（与 CONTEXT 的差异点集中列在附录C）

### 2.1 charset：utf8mb3 足够（实测）

- 全表 16,922 个单元格（1420×17 再减空）中 **0 个 BMP 外字符**、0 个代理对；旧 520 行（`current_api_known_all.json`）也无。
- 因此 `utf8`（3 字节）能装下 v2055 全部文本；`utf8mb4` 的唯一收益是未来 emoji/古文字，本轮无收益。
- 转换的代价是**硬错误**：见 §4.3 行大小计算 → 转换后 73,470 B > 65,535 B，`ALTER` 报 `ERROR 1118 Row size too large`。**结论：不转 charset，新列继承表 utf8 即可**。
- 旧 CGI（`MySQLdb charset='utf8'`）与 FastAPI（pymysql `charset=utf8mb4`）读写 utf8mb3 表都正常（服务端按列 charset 转换）。

### 2.2 多值分隔与"位置一一对应"的例外

`说明` sheet 约定全表 `; ` 分隔、第 k DOI ↔ 第 k 题名 ↔ 第 k 年份。实测 1404/1420 行成立；16 行不成立：

| 形态 | 行数 | 例子 | 导入/API 处理 |
|---|---|---|---|
| 2 DOI / 2 题名 / **1 年份** | 12 | row 469 等 | 单年份**复制**给两条 reference（同一年两篇文献） |
| **1 题名** / 2 DOI / 1 年份 | 3 | row 615 `TaGW8`（CJ2019 + FPLS2019） | 第 2 条 reference 的 title = null |
| 4 题名 / 3 DOI / 3 年份 | 1 | row 1400 | 第 4 条 reference 只有 title，`doi: null` |

→ 导入层**不因计数不等报错**，写 warning 进报告；对象层用 `n = max(len(title), len(doi), len(year))` 对齐（§6.4）。这 16 行建议同步给 data-profiler/用户复核（v2055 仍可能继续修）。

### 2.3 clone_id 映射覆盖率（生产实测 = 最终口径；本地基线作对照）

**生产实测（Lead 代查，2026-10-28，权威数字）**：

| 项 | 数值 |
|---|---|
| 旧库 gene_id ID 体系 | 461 行 IWGSC **v2.1（02G）** + 10 行 **v1** + 49 行 HORVU/GenBank/其他 |
| 新数据 reference_genome_id 体系 | **1291 行 IWGSC v3（03G）** + HORVU/其他 |
| 直接 gene_id / gene_name 匹配 | 仅 **7–10 行** |
| 经 `Genehub_DB.GenePageIWGSCv1_table` 把旧 v1/v2→v3 后 | **继承 321 / 520 = 62%** |
| **孤儿旧 clone_id（新表中无对应行）** | **199** |
| 新行分配新 clone_id（从 527 起） | **1099**（1420−321） |
| 新 clone_id 区间 / 导入后 AUTO_INCREMENT | 527 … **1625** / **1626** |

本地用"gene_id 精确 + gene_name 归一化"两级基线只有 227/520（gene_id 精确 4 + gene_name 归一化 214），说明 **T1 的 Genehub_ID 转换是主力级，不能省**；同时也说明生产实测（321）与本地基线（227）的差值 ≈ 94 行，全部来自 v1/v2→v3 转换 + 生产 Genehub 表覆盖，脚本必须把 **每条映射的 tier/来源写进 CSV** 供人工复核（§5.3、§5.6）。

**199 个孤儿的两个选项**（Lead 写进决策 Q3）：

- **Option A（推荐，保留旧链）**：DDL 阶段（root，仍在窗口内）建只读回退表，数据阶段（应用账号）从备份表灌入孤儿行：
  ```sql
  -- root，DDL 脚本内（紧随 backup 表创建之后）
  CREATE TABLE cloned_gene_db.cloned_gene_tbl_legacy LIKE cloned_gene_tbl_backup_20261028;
  -- 数据阶段脚本从 mapping 报告拿到 199 个孤儿 clone_id，应用账号执行：
  INSERT INTO cloned_gene_tbl_legacy
  SELECT b.* FROM cloned_gene_tbl_backup_20261028 b
  WHERE b.clone_id IN (<199 个孤儿 id>);
  ```
  API `/known/{id}`：数字路径在主表查不到时，**再查 `cloned_gene_tbl_legacy`**，命中则在响应里加 `deprecated: true, replaced_by: null`（旧前端忽略新键，仍能渲染）；404 仍保留给真正不存在的号。成本：1 张表 + 1 条兜底查询（+0.5–1h），收益：199 条旧深链继续可用、可灰度下架。
- **Option B（零成本）**：不建回退表，旧链 404。需在发布说明/公告里写明 "旧 clone_id 链接已失效，请用基因检索"。

> 说明：无论 A/B，**新表内容严格 = v2055 的 1420 行**（不保留孤儿行），符合"替换"语义；A 只是加一个只读、不参与搜索/stats 的历史快照表。

**其它口径**：
- 一个旧 clone_id 对应新数据的多行时（如 TaVRN-A1 被 D2 按 3 篇文献拆成 3 行，旧表 1 行）：保留给 `_row` 最小/内容最全的那行，其余行拿新号，mapping CSV 标 `note=multi-row-gene`。
- 匹配到但内容大幅重写（同一 gene_name、不同基因别名）的行：mapping CSV 打 `tier=T2`，人工复核可拒绝（拒绝后该新行拿新号、旧号进孤儿池）。

### 2.4 `#` 与 `normalize_text()` 冲突（必修）

- `app/services/legacy_parsers.py::normalize_text`：`replace("####","'")` 再 `replace("#","'")`。
- 新数据 **49 行含单 `#`**（按列：cloning_method_description 23、validation_method 19、key_result 14、gene_phenotype 13、function_description 10、protein_family 7、gene_species 3；行间有重叠；生物学命名如 `7S#1`、`6Ae#3`、`EMS lines #1/#2`）；`0` 个 `####`。（Lead 口径的"23 行"= cloning_method_description 单列——同一事实，不冲突。）
- 受影响字段若经 `normalize_text()` 返回：`gene_species`（3 行）、`gene_phenotype`（13 行）、`function_description`（10 行）、`cloning_method_description`（23 行）→ API 会把 `#` 显示成 `'`（"数据看着像脏的"）。
- **不能全局改 `normalize_text`**：它被 15+ 个库/路由复用，旧数据（CGI 时代）用 `#` 当撇号是既定约定。
- **方案**：known 端点内部按行判别 legacy，新列/新数据走新归一化（代码片段 §附录B）：
  ```python
  is_legacy = row.get("reference_genome_id") is None   # 老 520 行回滚后 / CGI 新提交行 = NULL
  ```
  因为 v2055 的 `reference_genome_id` 100% 非空，这个判别是稳定且向后兼容的（回滚后旧行→legacy 行为；CGI 提交行→legacy 行为）。

### 2.5 染色体标签（by-chromosome 必须重写）

- 新 `chrom_pos` 是"品种/版本名 + chr + 区间"的自由格式（例：`MorexV3 chr3H:18.913-18.920Mb`、`AetTA1675 2D:2.33-2.45Mb`），**不是**以染色体开头的短串；旧端点 `WHERE chrom_pos LIKE '5A%'` 对新数据命中 0。
- 旧数据 chrom_pos 也很脏（`'2A'`、`'7EL'`、`'chr2A135.191-135.197Mb'`、`'IWGSC Ref v1.0 Un'`），268/520 行没有可解析 token。
- → 建**内部规范化列 `chromosome varchar(16)`**（导入时 Python 解析；**同时作为 `/all`、`/search`、`/by-chromosome`、`/known/{id}` 的顶层便利键返回**——前端 task-3 已定案，见 §6.1），by-chromosome 用 `WHERE chromosome=%s OR (chromosome IS NULL AND chrom_pos REGEXP ...)`；stats 用 `GROUP BY chromosome`。token 规则与无列 fallback 见附录A。

### 2.6 `species_primary`（依赖 task-1 的受控映射，必须有 100% 兜底）

- 目标：`Triticum aestivum (bread wheat)` → `Triticum aestivum`；多物种行取**第一段的主物种**（如 `Thinopyrum ponticum (...); Triticum aestivum (...)` → `Thinopyrum ponticum`）。
- 用"首段取二名法"的初版规则实测：**1420/1420 覆盖、21 个 token**（`Triticum aestivum` 1260、`Hordeum vulgare` 80、`Triticum turgidum` 22、`Triticum monococcum` 10、`Aegilops tauschii` 10、`Triticum urartu` 7、…、`×Triticosecale` 2）。
- 但纯正则会把 `Coorong carrying ...` 误抽成 `Coorong carrying`（首段是品种名而非物种名）→ **必须使用 task-1 产出的 296→token 显式映射表**（建议落为 `scripts/data/species_primary_map_v2055.csv`，列为 `raw_species,token`），脚本对未命中值**硬失败**（不是静默兜底），保证 stats 口径可控。
- `gene_species` 保留完整原文（加宽到 1000 后正好装下 668），供详情页展示材料细节。

---

## 3. 代码影响面清单（逐文件）

> 原则：**能不加文件就不加**；`/known/*` 全部在现有 `app/api/routers/gene.py` 的同一个 `router` 上，新增 `/known/stats` 不需要动路由注册。

| # | 文件 | 现状 | 要改什么 | 为什么 | 估算 |
|---|---|---|---|---|---|
| 1 | `app/api/routers/gene.py` | 4 个 known 端点；LIKE 搜索 9 字段；详情 references 只由 doi 构建；`normalize_text` 直用 | 见 §3.1：① 新归一化函数 + 行级 legacy 判别；② search `field` 白名单（含 chrom_pos）；③ `/all` 加 4 新字段 + 可选 limit/offset；④ detail 加 6 新字段 + references(title,doi,year) 对齐 + `publication_years[]`；⑤ 新增 `/known/stats`（**必须在 `/known/{gene_id}` 之前注册**）；⑥ by-chromosome 改 `chromosome` 列 + 兼容 fallback | 数据模型变了，旧代码会显示 `#` 被替换、搜不到新字段、references 无 year、chromosome 全查不到 | 3–4 h |
| 2 | `app/schemas/gene.py` | `KnownGeneSummary`(8 键)、`KnownGeneDetail`(17 键)、`DOIReference{doi,title}` | `KnownGeneSummary` +6 键（`reference_genome_id/functional_category/species_primary/research_strategy` + **`chromosome`/`genome_ref`**，全部 `str|None`）；`KnownGeneDetail` +8 键（上述 6 + `protein_family`、`validation_methods:list[str]`、`publication_years:list[str]`）；`DOIReference` 的 `doi` 改 `str|None`、新增 `year: int|str|None`；`GeneSubmissionRequest/UpdateRequest` 本轮不动（无对应 API 端点）。注：`chromosome`/`genome_ref` 是前端 task-3 明确要的便利键（`frontend_change_spec.md` §4.1/§6.2），Stats 口径同源 | 新字段必须进响应模型；doi 可空是 v2055 的 1 行 4 题名/3 DOI 场景 | 0.5 h |
| 3 | `app/services/legacy_parsers.py` | `split_legacy_multi_value`（**丢弃空段**，无法位置对齐）、`normalize_text` | **新增**（不动旧函数）：`split_aligned_multi_value()`（`###` 拆分保留空位）、`normalize_known_text(value, legacy)`；`normalize_text` 保持原样 | references 需要"保位拆分"；全局改 `normalize_text` 会破坏其它 15+ 模块 | 0.5 h |
| 4 | `app/core/security.py` | `GENE_ID_PATTERN = ^[A-Za-z0-9_.:-]+$`，`ensure_gene_like` | **不改**。文档化限制：v2055 有 1 个 gene_id（`Yr87/Lr85`）与 50 个 gene_name 无法通过路径参数校验；前端详情一律用 clone_id（已是现状） | 放宽正则也不能解决 `/` 在 URL path 中被路由拆段的问题；加宽会波及 GeneHub 等端点 | 0 |
| 5 | `app/db/mysql.py` | pymysql + DictCursor，`mysql_cursor` 成功 commit / 异常 rollback | **不改**。新列/加宽对 DictCursor 透明；事务语义足够（迁移脚本不用它，用裸 pymysql 更好控制批次与日志） | — | 0 |
| 6 | `app/core/config.py` | `DB_CLONED_GENE="cloned_gene_db"` 等已就绪 | **不改**（不新增配置项） | — | 0 |
| 7 | `main.py` | OpenAPI 描述表里 Known Genes 一行；11+ static mount（`/genes` 已挂）；路由注册列表引用 `gene.router` | 可选：OpenAPI 描述中 Known Genes 一行补一句 "含 /known/stats 统计聚合"；**无需**新增 router/mount | 文档一致性（低优先） | 0.25 h |
| 8 | `cgi-py-RawScript/gene_search.py` | 显式列 `SELECT gene_id,gene_name,chrom_pos,gene_phenotype,gene_species,paper_doi`；`###`→`;` 展示；DOI 按 `###` 拆 | **零改动**（追加列/加宽/类型变更都不影响显式列表查询）。注意：新数据 phenotype/species 变长，旧页面会显示长文本（纯展示问题，不阻断） | 兼容性确认 | 0 |
| 9 | `cgi-py-RawScript/gene_search_by_id.py` | **`SELECT *` + 位置下标 `ele[0]..ele[11]`** | **零改动的前提：新列只准 append 到末尾**（`ADD COLUMN` 不带 `AFTER`）。若插列到中间，`ele[6]=paper_title` 等全部错位 → 旧页面串列。§4.2 已遵守 | 位置下标是最强的兼容约束 | 0（约束） |
| 10 | `cgi-py-RawScript/gene_submit.py` / `gene_update.py` | `INSERT`/`UPDATE` 均**显式列名**，只写旧 11 列 | **零改动**。新列 DEFAULT NULL → 提交/更新行在新列上为 NULL；`author/author_mail NOT NULL` 由表单保证。注意这些新提交行会绕过 v2055 内容（不会被本次导入覆盖，除非重导） | 兼容性确认 | 0 |
| 11 | `cgi-py-RawScript/gene_search_old.py` / `gene_submit_old.py` | 归档副本（同逻辑） | 零改动（不在线上回退/调用路径） | — | 0 |
| 12 | `scripts/import_cloned_genes.py` | 面向"审阅后候选 CSV 逐行 INSERT"，按 gene_name/gene_id 去重后**跳过已存在行**，支持 `--ensure-pmid-column` | **不改、也不用于本次**：本次是"整表替换 + clone_id 映射 + staging + 事务"，语义完全不同（它 skip-existing，本次要 delete-replace）。保留作为未来单基因增量入库工具；v2055 之后 `pmid` 列仍不存在，行为不变 | 避免误用 | 0 |
| 13 | `scripts/backfill_publication_year.py` | 按 DOI 回填 `publication_year`（只补空值），Crosscheck 取最少年份 | **不改**。v2055 后 `publication_year` 100% 非空 → 该脚本变 no-op；保留。注意其 `WHERE publication_year=''` 对 YEAR 列的比较在新数据下不会命中 | 兼容性确认 | 0 |
| 14 | `scripts/scan_gene_annotations.py` | 只读 `SELECT clone_id,gene_id,gene_name` 做匹配 | **不改**，新 schema 兼容 | — | 0 |
| 15 | `app/static/genes/index.html` / `detail.html` | 前端（task-3 负责改） | 本文件不展开；后端约束：旧前端在"新后端+旧数据"和"新后端+新数据"两种组合下都必须可用（新增键、旧键不删） | 向后兼容约束 | — |
| 16 | MCP / 文档 / 首页 | grep 全仓：`app/mcp/sequence_tools.py` **没有** known 工具；`app/static/docpages/*` 无 KnownGene API 文档；`/V2.0` 首页卡片只指向 `/genes/`（不读 API） | 零改动 | 无隐藏调用点 | 0 |
| 17 | 其他 grep 命中 | `README.md` 只提到 CGI `gene_search.py`；`MAINTENANCE.md` 无 KnownGene 章节 | 可选：计划文档落地后在 MAINTENANCE 加一节"KnownGene 数据更新流程"（非必须） | 运维可复现性 | 0.25 h |

**新增文件（实施阶段）**：`scripts/migrate_known_genes_v2055.py`、`scripts/sql/known_genes_v2055_ddl.sql`、`scripts/sql/known_genes_v2055_verify.sql`、可选 `scripts/data/species_primary_map_v2055.csv`。

### 3.1 `gene.py` 的逐端点改造点（实现级）

| 端点 | 现状（行号） | 改造 |
|---|---|---|
| `GET /known/search` | L50–123；9 列 LIKE；`KnownGeneSummary`；`dois` | 加 `field: str = Query("all")` → 白名单字典（§6.2），未知值 400；SELECT 增 4 新列 + **补 SELECT `publication_year`**（现 SQL 漏选该列 → `row.get(...)` 恒空 → 响应 `publication_year` 永远 `null`，**既有 bug，顺带修**，Lead 已确认）；结果仍返回 `KnownGeneSummary`（+新键，旧键不动） |
| `GET /known/all` | L125–168；6 列无分页 | SELECT 增 4 新列；加 `limit: int|None = Query(None, ge=1, le=5000)`、`offset: int = Query(0, ge=0)`；响应 `{total, records}`（未分页时 `total=len(records)` 与现在完全一致）；每行加便利键 `chromosome`（取 DB 列）与 `genome_ref`（从 chrom_pos 前缀派生，见 §6.1） |
| `GET /known/by-chromosome/{chromosome}` | L171–204；`chrom_pos LIKE '{chrom}%'` | `normalize_chromosome()`（去 `chr`/大小写/校验 `^[0-9]{1,2}[A-Z]{0,2}$`）→ `WHERE chromosome=%s OR (chromosome IS NULL AND chrom_pos REGEXP %s)`；返回同 /all（含 `chromosome`/`genome_ref`）；非法输入 400 |
| `GET /known/{gene_id}` | L205–277；`SELECT *`；references 仅 doi；`normalize_text` | 先注册 **`/known/stats`**（L205 之前）；新归一化 + 行级 legacy；references 对齐构建（title+doi+year），`DOIReference.doi` 可空；`validation_methods[]`；`publication_years[]`；`species_primary` 等新键 + `chromosome`/`genome_ref`；`publication_year` 仍是标量（最早年份）；数字路径在主表未命中时可选查 legacy 回退表（附录D-Q3 Option A） |
| `GET /known/stats`（新增） | — | 见 §6.5：与 `frontend_change_spec.md §5.1` 对齐的契约；5–6 条 GROUP BY + 2–3 条轻量列查询 + Python 聚合（chromosome 直接 GROUP BY；phenotype/年份/references 在 Python 聚合） |

---

## 4. 目标 Schema 与 DDL

### 4.1 Excel 列 → DB 列映射（目标态）

| Excel 列 | DB 列 | 类型 | 说明 |
|---|---|---|---|
| gene_id | `gene_id` | varchar(300)（不变） | 原样，异构 ID |
| 参考基因组ID | `reference_genome_id` **新** | varchar(100) NULL | 100% 有值；作为 legacy/新数据判别键 + T1 ID 映射键 |
| gene_name | `gene_name` | varchar(500)（不变） | 原样 |
| 物种信息 | `gene_species` | varchar(500)→**varchar(1000)** | 完整原文（≤668） |
| —（派生） | `species_primary` **新** | varchar(64) NULL | 受控映射（296→21/22），用于 stats/搜索/前端徽章 |
| chrom_pos | `chrom_pos` | varchar(500)（不变） | 原样长格式 |
| —（派生） | `chromosome` **新** | varchar(16) NULL | 归一化 token（5A/3H/1R/54…）；API 顶层便利键 + by-chromosome/stats 口径；见附录A |
| —（派生，不落库） | （API 键 `genome_ref`） | — | 从 `chrom_pos` 前缀派生（`Refv1.0`/`MorexV3`/`Zavitan.v1.0`…），后端 Python 计算，见 §6.1 |
| gene_phenotype | `gene_phenotype` | varchar(1000)→**varchar(2000)** | ≤1677 |
| key_result | `key_result` | varchar(15000)（不变） | ≤3051，保持 |
| function_description | `function_description` | text（不变） | 原样 |
| 蛋白家族 | `protein_family` **新** | TEXT | ≤2657，"family - 描述"整段 |
| cloning_method | `cloning_method` | varchar(255)（不变） | 8 种受控值+少量组合 |
| cloning_method_description | `cloning_method_description` | text（不变） | 原样 |
| 验证方法 | `validation_method` **新** | TEXT | 原样 `; ` 串；API 拆 `validation_methods[]` |
| 研究策略 | `research_strategy` **新** | varchar(32) NULL | 3 受控值 |
| 功能大类 | `functional_category` **新** | varchar(64) NULL | 5 受控值 |
| title | `paper_title` | text（不变） | 存储时 `; `→`###`（CGI 兼容，§3.3） |
| doi | `paper_doi` | text（不变） | 存储时 `; `→`###` |
| publication_year | `publication_year` | year(4)（不变，存**最早**年份） | 兼容旧语义 |
| —（多值） | `publication_years` **新** | varchar(64) NULL | 原始多年份，`###` 连接（与 title/doi 位置对齐），≤18 |
| —（提交信息） | `author` / `author_mail` | NOT NULL（不变） | 批量导入写 `''`；`submission_date` 写导入日 |
| —（预留） | `pmid` | **不加** | v2055 无 PMID；`import_cloned_genes.py` 的 `--ensure-pmid-column` 将来另行 root 执行 |

### 4.2 目标 DDL（完整可执行）

> 文件建议：`scripts/sql/known_genes_v2055_ddl.sql`（由 `migrate_known_genes_v2055.py --phase ddl --out ...` 生成或手工维护）
> 执行：**必须 root**：`sudo mysql < scripts/sql/known_genes_v2055_ddl.sql`
> 兼容性：**只追加列（不带 AFTER）、只加宽两列、不改既有列序**；因此对 `gene_search_by_id.py` 的 `SELECT *` 位置下标、对旧 API、对 `INSERT/UPDATE` 显式列名全部兼容。

```sql
-- ============================================================================
-- KnownGene v2055 DDL  (MySQL 5.7.33, db=cloned_gene_db)
-- 执行身份: MySQL root（sudo mysql），应用账号无 DDL 权限
-- 前置: 已记录当前状态 520 行 / AUTO_INCREMENT=527；已做逻辑备份（见 0 步）
-- 回滚: 见 docs/known_genes/backend_investigation.md §5.8（数据用备份表；
--       结构用本文件末尾的 DROP 语句或 root 恢复 mysqldump）
-- ============================================================================

-- 0) 逻辑备份（在 shell 执行，不在此 SQL 中；应用账号 SELECT 权限即可）：
--    mysqldump --single-transaction --no-tablespaces --default-character-set=utf8mb4 \
--      cloned_gene_db cloned_gene_tbl > /var/backups/cloned_gene_tbl_pre_v2055_20261028.sql

-- 1) 结构变更：加宽 2 列 + 追加 9 列 + 4 个索引
ALTER TABLE cloned_gene_tbl
  MODIFY COLUMN gene_phenotype VARCHAR(2000) DEFAULT NULL
    COMMENT 'Trait/phenotype free text; widened for v2055 (max 1677 chars)',
  MODIFY COLUMN gene_species VARCHAR(1000) DEFAULT NULL
    COMMENT 'Species free text incl. materials; widened for v2055 (max 668 chars)',
  ADD COLUMN reference_genome_id VARCHAR(100) DEFAULT NULL
    COMMENT 'v2055 col2: reference genome ID (IWGSC v3 03G / HORVU / GenBank); NULL = legacy row',
  ADD COLUMN protein_family TEXT
    COMMENT 'v2055 col9: protein family - function description (<=2657 chars)',
  ADD COLUMN validation_method TEXT
    COMMENT 'v2055 col12: semicolon-separated validation method tags; API splits to validation_methods[]',
  ADD COLUMN research_strategy VARCHAR(32) DEFAULT NULL
    COMMENT 'v2055 col13: Reverse genetics / Forward genetics / Not reported',
  ADD COLUMN functional_category VARCHAR(64) DEFAULT NULL
    COMMENT 'v2055 col14: one of 5 controlled categories',
  ADD COLUMN species_primary VARCHAR(64) DEFAULT NULL
    COMMENT 'Normalized NCBI binomial (controlled map); stats/search dimension',
  ADD COLUMN publication_years VARCHAR(64) DEFAULT NULL
    COMMENT 'v2055 col17 multi-year raw values, "###"-joined (positional with paper_title/paper_doi)',
  ADD COLUMN chromosome VARCHAR(16) DEFAULT NULL
    COMMENT 'Normalized chromosome token parsed from chrom_pos (5A/3H/1R/54...); internal, for by-chromosome/stats',
  ADD INDEX idx_kg_gene_id (gene_id(64)),
  ADD INDEX idx_kg_gene_name (gene_name(64)),
  ADD INDEX idx_kg_ref_id (reference_genome_id(64)),
  ADD INDEX idx_kg_chromosome (chromosome);
-- 说明：
-- * 新列未显式写 CHARACTER SET → 继承表默认 utf8/utf8_general_ci（不是库默认 latin1）
-- * 索引用 64 字符前缀：gene_id/gene_name 实际最大 38/48，前缀 64 覆盖全部取值；
--   且 64*3=192B 远低于 767B（即使表是 ROW_FORMAT=COMPACT / innodb_large_prefix=0 也可建）。
--   全列索引 gene_id varchar(300) 在 utf8mb3 下是 900B >767B，存在失败风险，故用前缀。
-- * 低选择度列（functional_category 5 值、research_strategy 3 值、publication_year 29 值）
--   不建索引：表仅 1420 行，stats 全表扫描 <10ms，索引无收益。

-- 2) 记录新版本标记（仅表注释，元数据变更，不重建表）
ALTER TABLE cloned_gene_tbl
  COMMENT = 'Known genes curated list; data version v2055 imported 20261028';

-- 3) 备份表：结构 = 变更后的新结构；内容 = 当前旧 520 行（新列为 NULL）
--    这样数据回滚 = 应用账号 DELETE + INSERT ... SELECT，不需要 root
CREATE TABLE cloned_gene_tbl_backup_20261028 LIKE cloned_gene_tbl;
INSERT INTO cloned_gene_tbl_backup_20261028 SELECT * FROM cloned_gene_tbl;

-- 4) staging 表：同理 LIKE 继承 utf8（若手写 CREATE 必须显式 DEFAULT CHARSET=utf8，
--    因为库默认是 latin1！）
CREATE TABLE cloned_gene_tbl_staging_20261028 LIKE cloned_gene_tbl;

-- 5) 权限补足（仅当 SHOW GRANTS 显示授权是"按表"而非 ON cloned_gene_db.* 时才需要；
--    按 Lead 提供的权限描述应为库级，则本段可整段跳过。先跑：
--    SHOW GRANTS FOR 'wheatomics_user'@'localhost';
-- 若为 ON `cloned_gene_db`.* → 无需 GRANT。
-- GRANT SELECT, INSERT, DELETE ON cloned_gene_db.cloned_gene_tbl_backup_20261028  TO 'wheatomics_user'@'localhost';
-- GRANT SELECT, INSERT, DELETE ON cloned_gene_db.cloned_gene_tbl_staging_20261028 TO 'wheatomics_user'@'localhost';

-- 6) 校验：列存在且类型正确
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, CHARACTER_SET_NAME, COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA='cloned_gene_db' AND TABLE_NAME='cloned_gene_tbl'
ORDER BY ORDINAL_POSITION;

-- 7) 记录当前状态，数据阶段脚本会复核
SELECT COUNT(*) AS rows_now, MAX(clone_id) AS max_id, MIN(clone_id) AS min_id FROM cloned_gene_tbl;
SELECT AUTO_INCREMENT FROM information_schema.TABLES
WHERE TABLE_SCHEMA='cloned_gene_db' AND TABLE_NAME='cloned_gene_tbl';
```

**可选**（若确认 root 想让旧行也"表结构一致但列序不动"地插入 `''`）：不需要，`author/author_mail` 保持 NOT NULL 无默认即可，数据阶段显式写 `''`（strict 模式允许空串）。**不要**在这轮给它们加 `DEFAULT ''`，避免引发不必要的表重建（`MODIFY ... DEFAULT` 会 COPY 重建，虽然 520 行也很快——能少一次就少一次）。

**结构回滚（仅当 DDL 本身有问题 / 还没导数据时）**：

```sql
-- root；确认数据阶段尚未 import 才可执行（会丢新列数据）
ALTER TABLE cloned_gene_tbl
  DROP INDEX idx_kg_gene_id,
  DROP INDEX idx_kg_gene_name,
  DROP INDEX idx_kg_ref_id,
  DROP INDEX idx_kg_chromosome,
  DROP COLUMN reference_genome_id,
  DROP COLUMN protein_family,
  DROP COLUMN validation_method,
  DROP COLUMN research_strategy,
  DROP COLUMN functional_category,
  DROP COLUMN species_primary,
  DROP COLUMN publication_years,
  DROP COLUMN chromosome,
  MODIFY COLUMN gene_phenotype VARCHAR(1000) DEFAULT NULL,
  MODIFY COLUMN gene_species VARCHAR(500) DEFAULT NULL;
ALTER TABLE cloned_gene_tbl COMMENT = '';
```

### 4.3 行大小计算（决定 key_result / utf8mb4）

MySQL 行声明长度上限 65,535 B（varchar 按 charset 最大字节数计；TEXT 计 ~12 B 指针）：

| 方案 | 声明长度合计 | 结论 |
|---|---|---|
| 现状 utf8mb3 | 55,135 B | 现有表成立（实测一致） |
| **本方案 utf8mb3（+9 列、加宽 2 列）** | **60,691 B** | < 65,535 ✅ 余量 4,844 B；因此 **`key_result varchar(15000)` 可以保持** |
| 现状列直接转 utf8mb4 | 73,490 B | **> 65,535 → ERROR 1118，ALTER 失败** ❌ |
| 转 utf8mb4 且 `key_result`→TEXT | ~13,500 B + 新列 ≈ 21,000 B | 可行但无收益（无 4 字节字符）❌ 本轮不做 |

→ **结论：保持 utf8mb3、保持 `key_result varchar(15000)`**。若未来一定要 utf8mb4，先把 `key_result` 改 TEXT（会立即腾出 60 KB 额度），再 `CONVERT TO CHARACTER SET utf8mb4`；本轮不引入这个变量。

### 4.4 `publication_year` 方案（已选定 B）

| 方案 | 优点 | 缺点 | 采用 |
|---|---|---|---|
| A. 改 `publication_year VARCHAR(64)` 存 `"2008; 2024"` | 实现最省事 | 旧字段语义从"单一年份"变成"字符串"；`backfill_publication_year.py` 的 `year` 语义、前端 `d.publication_year` 展示、stats 按年聚合都要跟着改；CGI 时代以来该字段一直是单值，外部消费者可能按数字排序 | ❌ |
| **B. 保持 `year(4)` = 最早年份 + 新增 `publication_years VARCHAR(64)`（原多值，`###` 连接）** | 旧 API/前端/脚本零改动；`publication_year` 仍是数字语义（1998–2026 全部在 YEAR 合法区间内）；多值信息完整保留；stats 用 `publication_year` 直接 GROUP BY；详情页 `publication_years[]` 展示全部 | 需要新列 + 导入时多一步 `min()` | ✅ |
| C. 拆 `paper` 子表（year 随 paper 走） | 最规范 | 改动面爆炸（CGI/旧 API 全要 join），完全不值得 | ❌ |

细节：`publication_year = min(该行全部年份)`（不是第一项——实测 **47 行**多值年份不是升序）；`publication_years` 保留原顺序 `###` 连接（最长 18 字符）。旧语义 `backfill_publication_year` 也是取最早年份，一致。

### 4.5 `key_result` 保持 `varchar(15000)` 的理由

- 新数据 max 3051 字符（40–464 词），旧数据已存在 15000 字符满值；`varchar(15000)` 对 v2055 富余 5 倍。
- 改成 TEXT 的唯一收益是腾出 45 KB 行额度（为 utf8mb4 铺路）；本轮不做 utf8mb4 → 收益为零。
- TEXT 语义差异（不能有 DEFAULT、排序/前缀行为）对当前代码无影响，但**没有必要引入变更**。→ **保持**。

### 4.6 DDL 对 CGI / 旧 API 的兼容性矩阵

| 消费者 | 依赖 | 本 DDL 影响 | 结论 |
|---|---|---|---|
| `cgi/gene_search.py` | 显式 6 列 SELECT + `###` 展示 | 列存在、类型可读；新行长文本纯展示 | ✅ |
| `cgi/gene_search_by_id.py` | **`SELECT *` + `ele[0..11]` 位置** | 只 append 列 → 位置不变 | ✅（若插列即 💥，DDL 已约束） |
| `cgi/gene_submit.py` | `INSERT` 显式 11 列 | 新列 DEFAULT NULL | ✅ |
| `cgi/gene_update.py` | `UPDATE` 显式 11 列 | 新列不被触碰 | ✅ |
| 旧 FastAPI `/known/all`、`/search`、`/by-chromosome`、`/{id}` | 代码按列名取 | 追加列不破坏；加宽/改 YEAR 不变 | ✅（注意：`normalize_text` 的 `#` 问题与本 DDL 无关，是代码问题，§2.4） |
| 旧前端（发版前的 `/genes/`） | `/known/all` 6 键 | 新增键被忽略；旧键保留 | ✅ |
| `scripts/backfill_publication_year.py` | 读空 `publication_year` | v2055 后无空值 → no-op | ✅ |
| `scripts/scan_gene_annotations.py` | 只读 3 列 | 兼容 | ✅ |

---

## 5. 数据替换流程（可执行级）

### 5.1 总体：两段式 6 步

```
[0] 冻结窗口记录现状（mysqldump + 证据快照 + COUNT/AUTO_INCREMENT）
[1] root 阶段：run ddl.sql（ALTER + backup 表 + staging 表 + 表注释 + 可选 legacy 表）
[2] 离线阶段（本机/服务器均可）：xlsx → 中间 JSONL → 校验报告 → clone_id 映射报告（人工复核）
[3] 应用账号阶段：dry-run → 载入 staging → staging 校验 SQL
[4] 应用账号阶段：单事务 DELETE FROM cloned_gene_tbl + INSERT ... SELECT FROM staging → COMMIT
[5] （附录D-Q3 选 Option A 时）应用账号：199 孤儿行灌入 cloned_gene_tbl_legacy
[6] 校验 SQL + API 冒烟 + CGI 回归；失败走 §5.8 回滚
```

### 5.2 中间文件规范（规避历史 bad-import）

历史事故 `cloned_gene_bad_import_backup` 1636 行 = TSV/引号序列化错位。本方案**不用 TSV**：

- 中间格式：**JSON Lines（UTF-8, `ensure_ascii=False`, 一行一条记录）**，字段为「DB 列名」，另带 `_row`（Excel 行号，便于回溯）、`_warn`（该行 warning 列表）。
- 由转换阶段做**唯一一次** `; ` → `###` 的多值转换（只对 `paper_title`/`paper_doi`/`publication_years` 三列；其它列保持原样）：
  ```python
  def aligned_join(parts: list[str]) -> str:
      return "###".join(p.strip() for p in parts if p.strip())   # 不补空位；API 端按计数对齐
  ```
  - `paper_title` = `"###".join(split_cell(title))`；`paper_doi` 同理；`publication_years` = `"###".join(split_cell(year))`。
  - **位置对齐不需要补空**：详情端按 `n=max(len(title),len(doi),len(year))` 读取，缺位自然补 `None`（§6.4）。
- `publication_year`（int） = `min(int(y) for y in year_parts)`。
- `species_primary`/`chromosome` 在转换阶段计算（规则 §2.6/附录A），写入 JSONL。
- `author=""`、`author_mail=""`、`submission_date=导入日` 由转换阶段写入。
- 序列化安全：JSON `\n` 转义自动处理；**禁止手工拼 SQL**——数据阶段全部 `cursor.execute(sql, params)` 参数化。
- 中间文件大小估算：1420 行 × 平均 ~5.5 KB ≈ **8 MB JSONL**（含长文本）；另出 3 个人工可读 CSV：`clone_id_mapping.csv`、`unmatched_old.csv`、`unmatched_new.csv`。

### 5.3 clone_id 稳定映射算法（脚本核心）

目标：旧 520 行里"新数据仍存在"的行保留原 clone_id；新行从 527 起分配；消失旧行的 id **不复用**。

```
输入: old = SELECT clone_id, gene_id, gene_name, chrom_pos, paper_doi FROM cloned_gene_tbl  (520 行)
      new = 1420 条标准化记录
步骤:
 0) 构建 old 索引:
    old_id_tokens[casefold(token)]  ← 每个旧 gene_id 按 [/,;] 拆 token + 原值
    old_name_norm[normalize(gene_name)] ← normalize = casefold + 去 [. _ - 空白]
    old_chrom[clone_id] ← 从 chrom_pos 解析的 chromosome token（附录A规则，可为 None）
 1) 构建 T1 映射（需生产 Genehub_DB，应用账号可读）:
    SELECT GeneIDv1, GeneIDv2, GeneIDv3 FROM Genehub_DB.GenePageIWGSCv1_table
    → 双向 dict: 02G↔03G、v1↔v2.1/v3
 2) 对每条 new 行计算候选 (tier, old_clone_id)：
    T1: new.reference_genome_id / new.gene_id  token ∈ old_id_tokens, 或经 T1 映射后 ∈ old_id_tokens
    T2: normalize(new.gene_name) ∈ old_name_norm
    T3(默认关, 需 --fuzzy-name): 去 subgenome/chrom 后缀（-A/-B/-D/-5A…）后相等
 3) 1:1 贪心分配（保证不把同一个旧 clone_id 分给两行）：
    按 (tier asc, _row asc, candidate_clone_id asc) 排序；候选 >1 时先用 chromosome token 相同者消歧；
    仍多候选 → 记入 review 列表，不自动分配（默认继续，--strict-mapping 可中止）
 4) new.clone_id = 匹配到则 old.clone_id，否则 next_id++（从 527 开始；跳过任何已被保留的号，天然不会冲突）
 5) 输出:
    clone_id_mapping.csv  (row, new_gene_id, new_refid, new_gene_name, old_clone_id, tier)
    unmatched_old.csv     (将被删除的旧行明细：clone_id, gene_id, gene_name, chrom_pos, doi)
    unmatched_new.csv     (将拿新 clone_id 的行)
    mapping_stats: preserved / dropped / new, tier 分布, 歧义列表
```

- **覆盖率（生产实测，Lead 代查）= 321/520 = 62%**；直接 gene_id 匹配仅 7–10 行 → T1（Genehub_DB v1/v2→v3）是主力级。本地两级基线 227/520 仅作回归对照（脚本自检：生产跑出的 preserved 不应低于本地基线）。
- 映射结果必须人工过一遍 `clone_id_mapping.csv` 再 `--commit`；--dry-run 默认不写库。脚本必须输出 tier 分布（T1/T2/T3）与每条的映射依据（旧 gene_id、新 refid、GeneIDv2/v3、gene_name 归一值）。
- 若某旧 clone_id 对应的新行有 **多行**（如 TaVRN-A1 被 D2 拆成 3 行）：clone_id 给第一行（`_row` 最小、tier 最高），其余行拿新号；在 mapping CSV 中标记 `note=multi-row-gene`。
- **新行 clone_id 区间：527 … 527+1099−1 = 1625；导入后 AUTO_INCREMENT = 1626**（生产实测 321 保留 / 1099 新行；若人工复核拒绝部分 T2/T3 映射，则保留数略降、新区间右移，以报告为准）。`AUTO_INCREMENT` 随显式插入自动推进到 max+1，无需手工 `ALTER ... AUTO_INCREMENT`。
- **199 个孤儿旧 clone_id**：脚本在报告里单列 `orphan_old_clone_ids.csv`；若选附录D-Q3 Option A，`--commit` 时顺带把 199 行从 `cloned_gene_tbl_backup_20261028` 灌入 `cloned_gene_tbl_legacy`（**孤儿 id 绝不分配给任何新行**，保证"不复用"）。

### 5.4 staging 表与目标事务（应用账号可执行）

```python
# 伪代码（scripts/migrate_known_genes_v2055.py --phase data --commit 的核心）
conn = pymysql.connect(host=..., user=app_user, password=..., database="cloned_gene_db",
                       charset="utf8mb4", autocommit=False, cursorclass=DictCursor)

# 前置检查（全部只读）
assert columns_exist(conn, NEW_COLUMNS), "先跑 root DDL"
assert backup_table_rows(conn, "cloned_gene_tbl_backup_20261028") == 520
assert table_rows(conn, "cloned_gene_tbl") == 520, "表格已被导入过？用 --force 或先回滚"
assert table_rows(conn, "cloned_gene_tbl_staging_20261028") in (0, 1420), "staging 脏"

# 1) 载入 staging（可重复执行，先清空）
with conn.cursor() as cur:
    cur.execute("DELETE FROM cloned_gene_tbl_staging_20261028")
    for batch in chunks(rows, 100):            # 100×~8KB < max_allowed_packet 4MB
        cur.executemany(
            "INSERT INTO cloned_gene_tbl_staging_20261028 "
            "(clone_id, gene_id, gene_name, chrom_pos, gene_phenotype, gene_species, paper_title, "
            " paper_doi, key_result, author, author_mail, submission_date, publication_year, "
            " function_description, cloning_method, cloning_method_description, "
            " reference_genome_id, protein_family, validation_method, research_strategy, "
            " functional_category, species_primary, publication_years, chromosome) "
            "VALUES (%s,...)",
            batch)
conn.commit()
run_staging_checks(conn)                       # §7.2 的校验 SQL 作用在 staging 上

# 2) 目标表替换：单事务，原子
try:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM cloned_gene_tbl")             # 520 行，DML 允许；禁 TRUNCATE
        cur.execute(
            "INSERT INTO cloned_gene_tbl "
            "(clone_id, gene_id, gene_name, ... , chromosome) "     # 与 staging 同列序，显式列名
            "SELECT clone_id, gene_id, gene_name, ... , chromosome "
            "FROM cloned_gene_tbl_staging_20261028")
        run_post_checks(conn)                                  # 事务内即可断言，失败即 rollback
    conn.commit()
except Exception:
    conn.rollback()      # 目标表仍是旧 520 行；staging 保留现场
    raise
```

要点：
- **禁止 `TRUNCATE`**：应用账号无权限，且 TRUNCATE 隐式提交会破坏原子性。`DELETE FROM` 520 行在事务内瞬间完成（InnoDB，MVCC 对读无阻塞；并发写会短暂等锁）。
- 列名全部显式；**不要 `INSERT INTO ... SELECT *`**（依赖列序，未来加列会错位）。
- 事务大小：520 删 + 1420 插 ≈ 5–10 MB redo，<1s；`max_allowed_packet=4MB` 只影响单条语句，`INSERT...SELECT` 是单条语句但行数据在服务端流转，无 packet 风险；staging 分批 100 行/批（每批 ~800KB）安全。
- 导入后保留 staging（审计复现）；root 确认后可 `DROP TABLE cloned_gene_tbl_staging_20261028`（不阻塞上线）。

### 5.5 备份策略

| 备份 | 创建者 | 内容 | 用途 | 保留 |
|---|---|---|---|---|
| `mysqldump` 文件 `/var/backups/cloned_gene_tbl_pre_v2055_20261028.sql` | 应用账号（`--single-transaction --no-tablespaces`，仅需 SELECT）或 root | DDL+数据，**DDL 前结构** | 最坏情况整表恢复（需 root 执行） | ≥30 天 |
| `cloned_gene_tbl_backup_20261028` 表 | root（DDL 脚本内） | 旧 520 行，新列 NULL | **常规数据回滚**（应用账号可执行，§5.8） | ≥30 天（root 后续清理） |
| `cloned_gene_tbl_staging_20261028` 表 | root（DDL 脚本内） | v2055 1420 行预处理结果 | 审计/复跑/不重跑 xlsx 直接重导入 | 上线稳定后 root 清理 |
| `cloned_gene_tbl_legacy` 表（**仅 Option A**） | root（DDL 脚本内建结构）+ 应用账号灌 199 孤儿行 | 199 个孤儿旧 clone_id 的旧行快照（只读，不参与搜索/stats） | 旧深链 `/known/{id}` 兜底（`deprecated:true`） | ≥1 年（或产品确认下架） |
| 旧备份表（`*_backup_null`/`*_subdate_backup_20261020`/`cloned_gene_bad_import_backup`/`cloned_gene_temp`） | 历史 | 历史遗留 | 本轮**不动**；`cloned_gene_temp`(latin1,1037) 与 bad_import(1636) 只作为反例证据 | 不在本轮清理范围 |

### 5.6 `scripts/migrate_known_genes_v2055.py` 接口设计

```
用法:
  # A. 生成/检查 DDL（应用账号即可，只读 information_schema；产出 SQL 由 root 执行）
  python3 scripts/migrate_known_genes_v2055.py --phase ddl --out scripts/sql/known_genes_v2055_ddl.sql

  # B. 转换 + 校验（不需要数据库；本机有 pandas/openpyxl 时可用 --xlsx）
  python3 scripts/migrate_known_genes_v2055.py --phase prepare \
      --xlsx "/path/...v2055....xlsx" --out-jsonl /tmp/known_genes_v2055.jsonl \
      --mapping-dir /tmp/known_genes_v2055_reports [--species-map scripts/data/species_primary_map_v2055.csv]

  # C. 映射 + dry-run（读 DB，不写；输出 mapping/报告 + 校验结果）
  python3 scripts/migrate_known_genes_v2055.py --phase data --jsonl /tmp/known_genes_v2055.jsonl \
      --dry-run --mapping-dir /tmp/known_genes_v2055_reports

  # D. 载入 staging 并校验（写 staging，不动目标表）
  python3 scripts/migrate_known_genes_v2055.py --phase data --jsonl ... --load-staging

  # E. 正式替换（staging 已校验通过后）
  python3 scripts/migrate_known_genes_v2055.py --phase data --jsonl ... \
      --commit --mapping-dir /tmp/known_genes_v2055_reports

  # F. 只读校验（目标表）
  python3 scripts/migrate_known_genes_v2055.py --phase verify

  # G. 回滚（数据回滚到备份表；应用账号即可）
  python3 scripts/migrate_known_genes_v2055.py --phase rollback \
      --from-backup cloned_gene_tbl_backup_20261028 --commit

参数:
  --phase {ddl,prepare,data,verify,rollback}      必填
  --xlsx PATH            转换阶段输入（需要 pandas+openpyxl）
  --jsonl PATH           数据阶段输入（纯 stdlib，服务器无需 pandas；推荐路径）
  --out-jsonl PATH       prepare 输出
  --mapping-dir DIR      报告输出目录（mapping/unmatched/stats/validation）
  --dry-run              默认行为；不写任何表
  --load-staging         只写 staging 并跑校验
  --commit               真正写；与 --dry-run 互斥
  --force                允许目标表行数 != 520 时继续（危险，需二次确认）
  --legacy-fallback      孤儿行灌入 cloned_gene_tbl_legacy（附录D-Q3 Option A；默认关=Option B）
  --target TABLE         默认 cloned_gene_tbl；drill 演练时指向 cloned_gene_tbl_migration_drill
  --from-backup NAME     rollback 用；默认 cloned_gene_tbl_backup_20261028
  --staging NAME         默认 cloned_gene_tbl_staging_20261028
  --species-map PATH     物种受控映射 CSV；缺省则用内置规则，并在报告里列出 unmapped（默认硬失败）
  --strict-mapping       映射有歧义时中止（默认只告警并留给人工）
  --batch-size N         默认 100
  --host/--port/--user/--password/--db   与 import_cloned_genes.py 一致：CLI > env > 仓库 .env
  --root-socket PATH     仅 ddl/--phase ddl-exec 用；默认 /var/run/mysqld/mysqld.sock
```

**凭据模型（与 Lead 确认的两段式一致）**：

- **root 阶段**：脚本**不代跑 DDL**。`--phase ddl` 只生成 SQL + 前置检查报告（应用账号读 `information_schema` 足够），维护者执行：
  `sudo mysql < scripts/sql/known_genes_v2055_ddl.sql`
  （服务器上 `sudo mysql` = root socket 认证；本机 `~/.config/lab-server/wheatomics.env` 的 `WHEATOMICS_MYSQL_ROOT_PASS` 只作为隧道备用，**不做主路径**）。
  可选 `--phase ddl-exec`：仅当脚本以 `sudo` 运行时，用 unix_socket 连 root（检测 `SELECT CURRENT_USER()` = `root@localhost`），否则拒绝执行。
- **数据阶段**：应用账号 `wheatomics_user`（仓库 `.env` 的 `DB_*`），只需要 SELECT/INSERT/UPDATE/DELETE + SELECT on staging/backup；**不碰 DDL**。
- 脚本启动时打印：`current_user()`、`@@sql_mode`、目标表行数、AUTO_INCREMENT、备份表/staging 是否存在 → 进报告 JSON。

**报告字段（`validation_report.json`）**：xlsx sha256/路径/mtime、总行数、逐列空值/最大长度、`#`/HTML/控制字符统计、多值计数不匹配行清单、DOI 非法清单、gene_id/name/refid 正则例外清单、species_primary 未映射值、chromosome 解析失败行、clone_id mapping 统计（preserved 321/dropped 199/new 1099/tier 分布/歧义）、**`orphan_old_clone_ids.csv`（199 个孤儿）**、staging 行数/指纹、目标表前后状态、每条校验 PASS/FAIL（含 SQL 与期望值）。

### 5.7 校验 SQL 的三种作用域

同一套 SQL（§7.2）在三处复用：
1. **staging 作用域**：把表名换成 `cloned_gene_tbl_staging_20261028`，在 `--load-staging` 后、事务前跑 → 提前发现数据问题，目标表零风险。
2. **事务内**：`run_post_checks` 在 DELETE+INSERT 后、COMMIT 前跑 → 任何 FAIL 直接 rollback。
3. **上线后**：`--phase verify` 再跑一遍 + 与 staging 交叉核对。

### 5.8 回滚

| 场景 | 操作 | 权限 | 预期 |
|---|---|---|---|
| 离线校验/映射不通过 | 什么都不用做（未写库） | — | 修数据/映射后重跑 |
| staging 校验不通过 | `--phase data` 中止；staging 可用 `DELETE FROM staging` 清空重来 | 应用账号 | 目标表未变 |
| 目标事务异常 | pymysql 自动 rollback | 应用账号 | 目标表仍 520 行（staging 保留现场） |
| **已 commit 但冒烟失败 → 数据回滚** | `python3 scripts/migrate_known_genes_v2055.py --phase rollback --commit`（内部：单事务 `DELETE FROM cloned_gene_tbl; INSERT INTO cloned_gene_tbl (显式列) SELECT (显式列) FROM cloned_gene_tbl_backup_20261028`） | 应用账号 | 回到旧 520 行；新列 NULL；API/旧前端立即回到旧数据（新代码需对 NULL 新列兼容——设计已要求）。若启用 Option A，同时 `DELETE FROM cloned_gene_tbl_legacy`（旧链兜底随主表回滚一起失效，符合预期） |
| DDL 本身有问题（未导数据） | §4.2 末尾的 DROP 语句 | root | 结构回原 |
| 最坏：整表报废 | `sudo mysql cloned_gene_db < /var/backups/cloned_gene_tbl_pre_v2055_20261028.sql`（dump 含 DROP/CREATE） | root | 原表结构+数据 |
| 代码回滚 | 本地 `git revert <sha>` push → 服务器 webhook 拉取 → `sudo systemctl restart wheatomics-api`；或服务器手动 `git pull` 后重启 | 维护者 | 旧代码；数据可保持新（旧代码对新数据兼容：新数据按 `###` 存储 + 旧字段语义不变） |

**回滚演练（上线前必须做一次）**：在正式表上**不演练**；用 root 建 `cloned_gene_tbl_migration_drill`（LIKE 新结构），脚本 `--staging cloned_gene_tbl_migration_drill` 全流程跑一遍（含 mapping/校验/事务/回滚到 drill_backup），确认：
`drill 520→1420→520` 且指纹一致；然后 root `DROP TABLE` 清掉 drill 表。

---

## 6. API 变更（按 CONTEXT §4 契约逐端点）

### 6.0 通用约定

- 响应包装不变：`{"success":true,"message":"ok","timestamp":"<UTC ISO>","data":{...}}`（`app/core/response.py::ok`）。
- **向后兼容铁律**：旧键一个不删、不改名、不改类型（除 `DOIReference.doi` 允许 null，见下）；新键一律新增。旧前端在旧数据/新数据下都能工作。
- `null` 策略：新列可能为 NULL（回滚后的旧行、CGI 提交行）→ 新键返回 `null`（不是 `""`）；字符串字段维持旧行为（`normalize_text(...) or None`，空串→None）。
- 错误：非法输入 400（`ValidationFailure`）、查无 404（`ResourceNotFound`）、缺参 422（FastAPI Query 校验）。
- **路由顺序**：`/known/stats` 必须定义在 `/known/{gene_id}` **之前**；否则 `stats` 会被当成 gene_id 命中详情路由并返回 404 `Known gene not found: stats`。同理 `search/all/by-chromosome` 已在前，不用动。
- GZipMiddleware 已启用（min 1000B），大响应自动压缩；不建议在本轮加 HTTP 缓存头（数据静态，前端已有 JS 缓存；发版后强制刷新由前端加 cache-buster 解决，归 task-3）。
- 搜索词处理沿用现状：`searchid.strip().replace('"','')`；LIKE 通配符（`%`/`_`）不转义（保持现在行为，**不做**转义以免改变语义）。

### 6.1 `GET /api/genes/known/all`

请求：`GET /api/genes/known/all[?limit=500&offset=0]`（limit 可选 1–5000，offset ≥0；**不带参数 = 全量，行为与现在完全一致**）

响应示例（带新字段；`clone_id` 示例值仅为示意）：

```json
{
  "success": true, "message": "ok", "timestamp": "2026-10-28T08:00:00+00:00",
  "data": {
    "total": 1420,
    "records": [
      {
        "clone_id": 528,
        "gene_id": "EF452301",
        "gene_name": "TaCRT-A/TaCRT3-A",
        "chrom_pos": "Refv1.0 chr3A:646.127-646.132Mb",
        "phenotype": "Drought tolerance; Powdery mildew resistance (Bgt)",
        "species": "Triticum aestivum (bread wheat)",
        "reference_genome_id": "TraesCS3A03G0936700",
        "functional_category": "Biotic & Abiotic Stress",
        "species_primary": "Triticum aestivum",
        "research_strategy": "Reverse genetics",
        "chromosome": "3A",
        "genome_ref": "Refv1.0"
      }
    ]
  }
}
```

- `total`：不带分页时 `= len(records)`（与现在一致）；带分页时 `= COUNT(*)`。
- **已与前端 task-3 定案的两个便利键（必加）**：
  - `chromosome`：直接取 DB 新列（§2.5/附录A），如 `"3A"`、`"1H"`、`"54"`；解析失败 = `null`。
  - `genome_ref`：从 `chrom_pos` 前缀派生（API 层 Python 计算，**不落库**）：
    ```python
    def genome_ref(chrom_pos: str) -> str | None:
        # "Refv1.0 chr3A:..." -> "Refv1.0"; "AetTA1675 2D:..." -> "AetTA1675"; 无前缀 -> None
        m = re.search(r"\bchr\s*[0-9]{1,2}[A-Za-z]{0,2}\b|(?:^|[^0-9A-Za-z])[0-9]{1,2}[A-Za-z]{1,2}\s*:", str(chrom_pos))
        if not m:
            return None
        return str(chrom_pos)[:m.start()].strip().rstrip(".,;").strip() or None
    ```
    新数据实测 34 种前缀（`Refv1.0` 1298、`MorexV3` 72、`Zavitan.v1.0` 6、`Lo7.v1` 4…），0 行无前缀（旧行可能 `null`）。
- `limit/offset` 语义：默认全量（旧行为）；前端列表页用 `limit=50&offset=…` 分页，`total` 给全量计数。

### 6.2 `GET /api/genes/known/search`

请求：`GET /api/genes/known/search?searchid=<term>[&field=all]`

`field` 白名单（**含补齐的 `chrom_pos`**，未知值 → 400）：

| field | SQL 列 |
|---|---|
| `all`（默认） | gene_id, gene_name, reference_genome_id, chrom_pos, gene_phenotype, gene_species, species_primary, paper_doi, function_description, cloning_method, paper_title, protein_family, validation_method, functional_category, research_strategy（= 旧 9 列 + 6 新列） |
| `gene_id` | gene_id |
| `gene_name` | gene_name |
| `reference_genome_id` | reference_genome_id |
| `chrom_pos` | chrom_pos（旧前端下拉已有，CONTEXT 漏列） |
| `phenotype` | gene_phenotype |
| `species` | gene_species, species_primary |
| `doi` | paper_doi |
| `protein_family` | protein_family |
| `functional_category` | functional_category |
| `research_strategy`（建议加） | research_strategy |

实现：`KNOWN_SEARCH_FIELDS: dict[str, tuple[str,...]]`；校验 `field in dict`；SQL `WHERE col1 LIKE %s OR col2 LIKE %s`（列名只来自白名单，不拼接用户输入）；`term` 作为 param。

响应（`KnownGeneSummary` + 新键；示例）：

```json
{
  "success": true, "message": "ok", "timestamp": "...",
  "data": {
    "query": "drought",
    "total": 2,
    "records": [
      {
        "clone_id": 528,
        "gene_id": "EF452301",
        "gene_name": "TaCRT-A/TaCRT3-A",
        "chrom_pos": "Refv1.0 chr3A:646.127-646.132Mb",
        "phenotype": "Drought tolerance; Powdery mildew resistance (Bgt)",
        "species": "Triticum aestivum (bread wheat)",
        "publication_year": "2008",
        "dois": ["10.1093/jxb/erm369", "10.1094/phyto-08-23-0276-r"],
        "reference_genome_id": "TraesCS3A03G0936700",
        "functional_category": "Biotic & Abiotic Stress",
        "species_primary": "Triticum aestivum",
        "research_strategy": "Reverse genetics",
        "chromosome": "3A",
        "genome_ref": "Refv1.0"
      }
    ]
  }
}
```

> 同时修复既有 bug：SQL 的 SELECT 列表补 `publication_year`（现在漏选 → `publication_year` 恒 `null`）。

非法示例：`?searchid=x&field=bogus` → `400 {"detail":"Unsupported search field: 'bogus'. Valid: all, gene_id, ..."}`；`?searchid=%20` → `400 {"detail":"searchid is required"}`。

### 6.3 `GET /api/genes/known/by-chromosome/{chromosome}`

- `normalize_chromosome()`：`strip()` → 去大小写统一 upper → 去前缀 `chr`/`Chr`/`CHR` → 校验 `^[0-9]{1,2}[A-Z]{0,2}$`（接受 `5A`、`chr5A`、`3h`、`1R`、`54`）；非法 → 400。
- SQL：
  ```sql
  SELECT clone_id, gene_id, gene_name, chrom_pos, gene_phenotype, gene_species,
         reference_genome_id, functional_category, species_primary, research_strategy, chromosome
  FROM cloned_gene_tbl
  WHERE chromosome = %s
     OR (chromosome IS NULL AND chrom_pos REGEXP %s)   -- legacy/CGI 行 fallback
  ORDER BY clone_id
  ```
  fallback 正则在 Python 里生成（输入已校验，无转义风险）：
  `rf"(^|[^0-9A-Za-z])(chr)?{chrom}([^0-9A-Za-z]|$)"`（MySQL 5.7 REGEXP 对 utf8_general_ci 大小写不敏感）。
  每条记录同样补 `genome_ref`（§6.1 的 `genome_ref()` helper），保证与 /all 同构。
- 响应（同 /all + `chromosome` 回显）：

```json
{"success":true,"message":"ok","timestamp":"...",
 "data":{"total":68,"chromosome":"5A","records":[ ... 同 /all 记录 ... ]}}
```

示例请求：`/api/genes/known/by-chromosome/5A` → 68 条；`/1H` → 13 条；`/chr7B` → 60 条；`/54` → 1 条；`/XX` → 400。

### 6.4 `GET /api/genes/known/{gene_id}`

- 数字 → clone_id（不变）；否则 gene_id/gene_name 精确匹配（不变；`Yr87/Lr85` 等 4 个含 `/` 的无法走路径参数，前端用 clone_id）。
- 新增返回键：`reference_genome_id`, `protein_family`, `validation_methods[]`, `research_strategy`, `functional_category`, `publication_years[]`, `species_primary`, **`chromosome`**, **`genome_ref`**；`references[]` 每项 `{doi, title, year}`。
- 数字路径（clone_id）在主表查不到时：若启用附录D-Q3 **Option A**，再查 `cloned_gene_tbl_legacy`；命中则返回旧行 + `deprecated: true`；否则 404。
- **references 对齐算法**（`###` 存储、`; ` 语义）：

```python
titles = split_aligned(row.get("paper_title"))       # ### 拆分，保留空位
dois   = split_aligned(row.get("paper_doi"))
years_raw = split_aligned(row.get("publication_years")) or \
            ([str(row["publication_year"])] if row.get("publication_year") else [])   # 回滚/CGI 行兜底
n = max(len(titles), len(dois), len(years_raw))
if len(years_raw) == 1 and n > 1:
    years_raw = years_raw * n          # 单年份复制（12 行 2 DOI/1 年份场景）
refs = []
for i in range(n):
    doi   = dois[i] if i < len(dois) else None
    title = titles[i] or None if i < len(titles) else None
    year  = years_raw[i] if i < len(years_raw) else None
    if doi is None and title is None and year is None:
        continue
    refs.append(DOIReference(doi=doi or None, title=title,
                             year=int(year) if str(year).isdigit() else year))
```

- `paper_title[]` 保持旧行为（`split_legacy_multi_value`，丢空段）；`key_result[]` 保持旧行为。
- `normalize_text` 只用于 legacy 行；新行原样（§附录B）。

响应示例（row 4，2 DOI/2 题名/2 年份；长文本截断示意）：

```json
{
  "success": true, "message": "ok", "timestamp": "...",
  "data": {
    "clone_id": 528,
    "gene_id": "EF452301",
    "gene_name": "TaCRT-A/TaCRT3-A",
    "chrom_pos": "Refv1.0 chr3A:646.127-646.132Mb",
    "phenotype": "Drought tolerance; Powdery mildew resistance (Bgt)",
    "species": "Triticum aestivum (bread wheat)",
    "paper_title": [
      "Molecular cloning and characterization of wheat calreticulin (CRT) gene involved in drought-stressed responses",
      "TaCRT3 Is a Positive Regulator of Resistance to Blumeria graminis f. sp. tritici in Wheat"
    ],
    "references": [
      {"doi": "10.1093/jxb/erm369", "title": "Molecular cloning and characterization of wheat calreticulin (CRT) gene involved in drought-stressed responses", "year": 2008},
      {"doi": "10.1094/phyto-08-23-0276-r", "title": "TaCRT3 Is a Positive Regulator of Resistance to Blumeria graminis f. sp. tritici in Wheat", "year": 2024}
    ],
    "key_result": ["…（单段长文本，≤3051 chars）…"],
    "publication_year": 2008,
    "publication_years": ["2008", "2024"],
    "function_description": "…",
    "cloning_method": "Homology-based cloning; Functional cloning",
    "cloning_method_description": "…",
    "author": null,
    "author_mail": null,
    "submission_date": "2026-10-28",
    "reference_genome_id": "TraesCS3A03G0936700",
    "protein_family": "Calreticulin (CRT3) family; calcium-binding ER chaperone …",
    "validation_methods": ["Expression analysis","Overexpression","VIGS","Subcellular localization","Phenotyping"],
    "research_strategy": "Reverse genetics",
    "functional_category": "Biotic & Abiotic Stress",
    "species_primary": "Triticum aestivum",
    "chromosome": "3A",
    "genome_ref": "Refv1.0"
  }
}
```

对齐特例（row 615：1 题名/2 DOI/1 年份）→

```json
"references": [
  {"doi": "10.1016/j.cj.2019.09.006", "title": "Diversity and sub-functionalization of TaGW8 homoeologs …", "year": 2019},
  {"doi": "10.3389/fpls.2019.00212", "title": null, "year": 2019}
]
```

（row 1400：4 题名/3 DOI/3 年份 → 第 4 条 `{"doi": null, "title": "...", "year": null}`；`DOIReference.doi` 因此改为可空。）

### 6.5 `GET /api/genes/known/stats`（新增，服务端聚合）

设计目标：替代前端 `/all` 客户端聚合（1.12 MB → <20 KB），口径由后端统一。**响应契约已与 `frontend_change_spec.md §5.1` 对齐**（键名以下表为准；前端对缺键用 `|| []` 容错）。路由必须注册在 `/known/{gene_id}` 之前。

#### 6.5.1 SQL（全部小表扫描；`ONLY_FULL_GROUP_BY` 安全）

```sql
-- 1) 总量 / KPI
SELECT COUNT(*) AS total FROM cloned_gene_tbl;

-- 2) 物种分布（受控 token；raw_forms 需 Python 关联原始串→token 映射）
SELECT species_primary AS name, COUNT(*) AS count
FROM cloned_gene_tbl WHERE species_primary IS NOT NULL
GROUP BY species_primary ORDER BY count DESC, name;
SELECT COUNT(DISTINCT gene_species) AS species_raw_count FROM cloned_gene_tbl;

-- 3) 染色体分布（下游 Python 补 group 与 21 小麦固定序/0 值）
SELECT chromosome AS label, COUNT(*) AS count
FROM cloned_gene_tbl WHERE chromosome IS NOT NULL
GROUP BY chromosome ORDER BY count DESC, label;

-- 4) 功能大类 / 研究策略
SELECT functional_category AS name, COUNT(*) AS count FROM cloned_gene_tbl
WHERE functional_category IS NOT NULL GROUP BY functional_category ORDER BY count DESC, name;
SELECT research_strategy AS name, COUNT(*) AS count FROM cloned_gene_tbl
WHERE research_strategy IS NOT NULL GROUP BY research_strategy ORDER BY count DESC, name;

-- 5) 供 Python 聚合的 3 个轻量列（1420 行 × 短文本，总计 <1.5 MB 内存，不返回给前端）
SELECT gene_phenotype FROM cloned_gene_tbl WHERE gene_phenotype IS NOT NULL;   -- 表型标签
SELECT publication_years FROM cloned_gene_tbl;                                  -- 多年份 token 计数
SELECT paper_doi FROM cloned_gene_tbl;                                          -- references 统计
-- 6) 可选：验证方法标签（本轮前端未画，先不做；如做同 5 的方式）
```

#### 6.5.2 Python 聚合规则（与前端契约逐项对齐）

| 键 | 规则 | v2055 实测值（验收用） |
|---|---|---|
| `total` | `COUNT(*)` | **1420** |
| `species` | 按 `species_primary` 计数降序；每项 `{name,count,raw_forms}`，`raw_forms` = 映射到该 token 的**不同原始 `gene_species` 串数量**（Σ raw_forms = 296） | 21 个 token；`Triticum aestivum` 1260（raw_forms 229）、`Hordeum vulgare` 80、`Triticum turgidum` 22 …（前端原估 24–26 个，实际以受控映射为准，联调时以本接口返回值为准） |
| `species_raw_count` | `COUNT(DISTINCT gene_species)` | **296** |
| `chromosomes` | 每项 `{label,count,group}`；`group="wheat"`（21 条固定序 1A…7D，缺失补 0）/ `"other"`（自然序） | **38 条 = 21 wheat + 17 other**；非小麦行 **95**；计数与 §6.5.2 表一致 |
| `functional_category` | `{name,count}` 降序 | 5 项：776/202/154/146/142 |
| `research_strategy` | `{name,count}`；前端按固定顺序渲染（reverse/forward/not reported） | 3 项：1061/281/78 |
| `phenotype_tags` | `gene_phenotype` 按 `;` 拆分 → `strip` → `lower()` → **行内去重** → 丢弃空串与 >80 字符的机制长句 → 全局计数降序，**返回 Top 50**（前端只画 Top 20） | 规则实现后实测：tags 总计数 1168 / distinct 583 / top1 `not determined` 65、`drought tolerance` 54、`salt tolerance` 42…（前端 spec 的 583→564、rows_without→463 为不同微口径估算，**以本接口返回为准**，见 §9 联调任务 F1） |
| `phenotype_tag_distinct` | 上述规则下的 distinct 数 | **583**（规则定稿后以接口为准） |
| `publication_year` | `publication_years` **按 token 逐年计一次**（多值行重复计入）；`{year,count}` 升序 | **合计 1555**（=1420 + 95 行×1 + 20 行×2 额外年份）；1998–2026；峰 2022=254、2024=248（前端 spec 写的 1535 是"1420+115"的估算，口径应改为"按 token 计数=1555"） |
| `references` | 由 `paper_doi` 按 `###` 拆分：`entries` = token 总数；`unique_dois` = distinct | **entries 1570 / unique_dois 883** ✓ 与前端 spec 一致 |
| `notes.multi_year_rows` | `publication_years` 含 `###` 的行数 | **115** |
| `notes.multi_species_rows` | `gene_species` 含 `;` 的行数 | **263**（前端 spec 估 236，以本接口为准） |
| `notes.rows_without_tags` | 上述 phenotype 规则下无可用 tag 的行数 | 规则定稿后计算（当前规则≈541） |

#### 6.5.3 响应示例（键与 `frontend_change_spec.md §5.1` 完全一致）

```json
{
  "success": true, "message": "ok", "timestamp": "2026-10-28T08:00:00+00:00",
  "data": {
    "total": 1420,
    "species": [
      {"name": "Triticum aestivum", "count": 1260, "raw_forms": 229},
      {"name": "Hordeum vulgare", "count": 80, "raw_forms": 5},
      {"name": "Triticum turgidum", "count": 22, "raw_forms": 17},
      {"name": "Triticum monococcum", "count": 10, "raw_forms": 6},
      {"name": "Aegilops tauschii", "count": 10, "raw_forms": 8}
    ],
    "species_raw_count": 296,
    "chromosomes": [
      {"label": "1A", "count": 55, "group": "wheat"},
      {"label": "1B", "count": 62, "group": "wheat"},
      {"label": "2B", "count": 96, "group": "wheat"},
      {"label": "3H", "count": 16, "group": "other"},
      {"label": "1R", "count": 4, "group": "other"},
      {"label": "51", "count": 1, "group": "other"},
      {"label": "54", "count": 1, "group": "other"}
    ],
    "functional_category": [
      {"name": "Biotic & Abiotic Stress", "count": 776},
      {"name": "Quality & Yield", "count": 202},
      {"name": "Morphology & Domestication", "count": 154},
      {"name": "Physiology & Metabolic Processes", "count": 146},
      {"name": "Reproduction & Phenology", "count": 142}
    ],
    "research_strategy": [
      {"name": "Reverse genetics", "count": 1061},
      {"name": "Forward genetics", "count": 281},
      {"name": "Not reported", "count": 78}
    ],
    "phenotype_tags": [
      {"tag": "not determined", "count": 65},
      {"tag": "drought tolerance", "count": 54},
      {"tag": "salt tolerance", "count": 42},
      {"tag": "stripe rust resistance", "count": 33},
      {"tag": "powdery mildew resistance", "count": 19}
    ],
    "phenotype_tag_distinct": 583,
    "publication_year": [
      {"year": 1998, "count": 2},
      {"year": 2021, "count": 154},
      {"year": 2022, "count": 254},
      {"year": 2024, "count": 248},
      {"year": 2026, "count": 39}
    ],
    "references": {"entries": 1570, "unique_dois": 883},
    "notes": {"multi_year_rows": 115, "multi_species_rows": 263, "rows_without_tags": 541}
  }
}
```

（示例里 `chromosomes` 只列了部分条目，实际响应必须 38 条齐全；`species` 全量 21 项；`phenotype_tags` Top 50。）

实现注意：
- 共 6–8 条查询 + 3 条轻量列查询，1420 行全量聚合单次 <50 ms；建议加**进程内 60s TTL 缓存**（无外部依赖、导入后自然失效；gunicorn 8 worker 各自缓存，不要求跨 worker 一致，数据本身幂等）。
- `species.raw_forms` 需要"原始串→token"映射：转换阶段生成 `species_primary` 时把 `gene_species→species_primary` 映射写入 staging 旁的报告；stats 实现可简单用 `species_raw_forms` 内存表（从 `SELECT gene_species, species_primary` 现算，1420 行），无需额外 DB 列。
- 旧行（回滚后）/CGI 提交行：`species_primary`/`chromosome` 为 NULL → 分别计入 `chromosomes.unclassified` 与 `species` 的 `null` 分组（或前端"Other/unclassified"），不丢总量。
- 响应 payload 目标 <20 KB（实测估算：21+38+5+3+50 条 + 年份 ≈ 8–12 KB）。

### 6.6 payload / 分页评估（实测估算）

| 端点 | 迁移前 | 迁移后 | gzip 后 | 结论 |
|---|---|---|---|---|
| `/known/all` 全量 | 97,894 B（520 行，含 envelope） | **≈1.18 MB（1.07 MiB + chromosome/genome_ref 两键 ≈ +57 KB）** | **≈190 KB** | GZip 后约 180KB，可接受；前端 Stats 改走 `/stats`；`limit/offset` 可选 |
| `/known/search?searchid=wheat`（最坏命中 1330 行） | — | ≈932,341 B | ≈173,650 B | 可接受；`searchid` 越具体越小（VRN1 → 个位数行） |
| `/known/{id}` | ~1–2 KB | 平均 **5.4 KB**，最大 **9.8 KB**（按全部长文本估算） | ~2.6 KB | 无压力 |
| `/known/stats` | 不存在 | **8–12 KB（<20 KB）** | — | 新增替代前端聚合；契约对齐 `frontend_change_spec.md §5.1`（§6.5） |
| `/known/by-chromosome/2B` | — | ≈96 行 × ~800B ≈ 77 KB | ~15 KB | 无压力 |

`limit/offset` 设计：`limit` 默认 None（全量）；带分页时多一次 `SELECT COUNT(*)`。响应加 `limit`/`offset` 回显（可选，不破坏旧键）。

---

## 7. 验证清单

### 7.1 离线校验（`--phase prepare` + `--dry-run`，硬失败/警告分级）

| # | 校验 | 期望 | 级别 |
|---|---|---|---|
| 1 | 行数 / 列数 | 1420 × 17，列名与 v2055 完全一致 | 硬失败 |
| 2 | 17 列非空率 | 100% | 硬失败 |
| 3 | 每列最大字符长度 vs 目标列上限 | 见 §1.1；`gene_phenotype≤2000, gene_species≤1000, publication_years≤64, reference_genome_id≤100, chromosome≤16, …` | 硬失败 |
| 4 | gene_id 空值 / 超 300 / 含 tab/nl/CR | 0 | 硬失败 |
| 5 | `###` 出现在 title/doi/year 原始值 | 0（否则分隔符冲突） | 硬失败 |
| 6 | DOI 全量正则 `^10\.\d{4,9}/\S+$` | 100%（拆多值后逐个） | 硬失败 |
| 7 | 年份 token 4 位数字 / 范围 1901–2155 / 可 min() | 100% | 硬失败 |
| 8 | species_primary 映射 | 1420/1420 命中受控表（未映射值 0） | 硬失败（先补映射表） |
| 9 | chromosome 解析 | 1420/1420 成功 | 硬失败 |
| 10 | UTF-8 可编码 / 无控制字符 | 全部 | 硬失败 |
| 11 | 多值 title/doi/year 计数不匹配行 | 16 行（warning 清单，不阻断；人工复核） | 警告 |
| 12 | gene_id / gene_name / refid 不支持 `ensure_gene_like` 的行 | gene_id 1、gene_name 50、refid 1（warning 清单） | 警告 |
| 13 | `#` 字符行（区分为 legacy 归一化问题） | 物种 3/表型 13/…（warning + 已由行级归一化解决） | 警告 |
| 14 | HTML 标签 / 比较符 `<` `>` | 58 行（warning；前端 esc()） | 警告 |
| 15 | 行指纹唯一性 | 1420/1420（`md5("\x1f".join(17列))`） | 硬失败 |
| 16 | 自然键重复 | `(gene_id,refid,name)` 允许 1 组 3 行（D2 拆行，DOI 不同）；其它 0 | 警告 |
| 17 | clone_id 映射 | 无重复分配；保留数>0；歧义清单人工确认 | 硬失败（映射）|
| 18 | `key_result` 词数 | 40–464（记录分布） | 信息 |

### 7.2 SQL 校验（staging / 事务内 / 上线后三处复用；`<T>` = `cloned_gene_tbl` 或 staging 表）

```sql
-- V1 行数
SELECT COUNT(*) AS n FROM <T>;                          -- 期望 1420
-- V2 关键必填非空
SELECT
  SUM(gene_id IS NULL OR gene_id='')            AS bad_gene_id,
  SUM(reference_genome_id IS NULL)              AS bad_ref_id,
  SUM(gene_name IS NULL OR gene_name='')        AS bad_gene_name,
  SUM(gene_phenotype IS NULL)                   AS bad_phenotype,
  SUM(species_primary IS NULL)                  AS bad_species_primary,
  SUM(chromosome IS NULL)                       AS bad_chromosome,
  SUM(publication_year IS NULL)                 AS bad_pub_year,
  SUM(author IS NULL)                           AS bad_author,
  SUM(author_mail IS NULL)                      AS bad_author_mail   -- 期望全 0
FROM <T>;
-- V3 长度（strict 模式已兜底，这里显式验收）
SELECT MAX(CHAR_LENGTH(gene_phenotype)) a, MAX(CHAR_LENGTH(gene_species)) b,
       MAX(CHAR_LENGTH(publication_years)) c, MAX(CHAR_LENGTH(reference_genome_id)) d,
       MAX(CHAR_LENGTH(key_result)) e, MAX(CHAR_LENGTH(paper_title)) f
FROM <T>;   -- a<=2000 b<=1000 c<=64 d<=100 e<=15000 f<=65535
-- V4 clone_id 结构
SELECT COUNT(*) total, COUNT(DISTINCT clone_id) distinct_ids, MIN(clone_id) min_id, MAX(clone_id) max_id FROM <T>;
-- 期望 total=1420=distinct_ids；min_id=1；max_id=1625（生产实测：321 保留 + 1099 新行）
-- V5 与备份表交叉：保留的旧 clone_id 仍在（生产实测预期 321）
SELECT COUNT(*) AS preserved FROM cloned_gene_tbl_backup_20261028 b
  JOIN cloned_gene_tbl t ON b.clone_id = t.clone_id;                       -- 期望 321
SELECT COUNT(*) AS dropped FROM cloned_gene_tbl_backup_20261028 b
  LEFT JOIN cloned_gene_tbl t ON b.clone_id = t.clone_id WHERE t.clone_id IS NULL;  -- 期望 520-preserved
-- V6 新行不复用旧号：1–526 段只应包含保留行（期望 321）；≥527 段全部是新行（期望 1099）
SELECT
  SUM(clone_id BETWEEN 1 AND 526) AS in_old_range,
  SUM(clone_id >= 527)            AS new_range
FROM cloned_gene_tbl;   -- in_old_range = preserved；new_range = 1420-preserved
-- V7 AUTO_INCREMENT 已推进
SELECT AUTO_INCREMENT FROM information_schema.TABLES
 WHERE TABLE_SCHEMA='cloned_gene_db' AND TABLE_NAME='cloned_gene_tbl';   -- >= max_id+1
-- V8 重复口径（记录性）
SELECT gene_id, COUNT(*) c FROM cloned_gene_tbl GROUP BY gene_id HAVING c>1;                       -- 23 组（预期）
SELECT reference_genome_id, COUNT(*) c FROM cloned_gene_tbl GROUP BY reference_genome_id HAVING c>1; -- 30 组（D7 预期）
-- V9 行指纹唯一（应=1420）
SELECT COUNT(DISTINCT MD5(CONCAT_WS(0x1f, gene_id, gene_name, chrom_pos, gene_phenotype, gene_species,
  paper_title, paper_doi, key_result, author, author_mail, submission_date, publication_year,
  function_description, cloning_method, cloning_method_description, reference_genome_id,
  protein_family, validation_method, research_strategy, functional_category, species_primary,
  publication_years, chromosome))) AS fingerprints FROM cloned_gene_tbl;
-- V10 受控值域
SELECT functional_category, COUNT(*) FROM cloned_gene_tbl GROUP BY functional_category;   -- 5 值
SELECT research_strategy, COUNT(*) FROM cloned_gene_tbl GROUP BY research_strategy;      -- 3 值
-- V11 物种归一化覆盖率（期望 1420）
SELECT SUM(species_primary IS NOT NULL) AS covered FROM cloned_gene_tbl;
-- V12 多值位置一致性（导入后 paper_title ### 段数 vs paper_doi ### 段数；
--     只统计「题名数≠DOI 数」的行：3 行 (1,2,1) + 1 行 (4,3,3) = 4；
--     12 行 (2,2,1) 是 DOI/题名一致、仅年份单值，不属此处）
SELECT COUNT(*) AS mismatch FROM cloned_gene_tbl
 WHERE (CHAR_LENGTH(paper_title)-CHAR_LENGTH(REPLACE(paper_title,'###','')))/3 + 1
    <> (CHAR_LENGTH(paper_doi)-CHAR_LENGTH(REPLACE(paper_doi,'###','')))/3 + 1;   -- 期望 4
-- V13 与 staging 完全一致（正式导入后）
SELECT COUNT(*) FROM cloned_gene_tbl t
  LEFT JOIN cloned_gene_tbl_staging_20261028 s ON s.clone_id=t.clone_id
 WHERE s.clone_id IS NULL;   -- 期望 0
```

### 7.3 API 冒烟（生产或本机；`B=http://127.0.0.1:8000/api`；不假设服务器有 jq，用 python3）

```bash
# S0 服务活着
curl -sS -o /dev/null -w '%{http_code}\n' "$B/health"                       # 200

# S1 /all 全量：total=1420；新键存在（含前端定案的 chromosome/genome_ref）
curl -sS "$B/genes/known/all" | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print(d['total'], sorted(d['records'][0].keys()))"
#   expect: 1420 [... 'chromosome','functional_category','genome_ref','reference_genome_id','research_strategy','species_primary' ...]

# S2 /all 分页
curl -sS "$B/genes/known/all?limit=10&offset=0" | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print(d['total'], len(d['records']))"   # 1420 10

# S3 搜索：默认 all（旧行为）+ 修复后 publication_year 不再是 null
curl -sS "$B/genes/known/search?searchid=TaCRT" | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print(d['total'], d['records'][0]['gene_id'], d['records'][0]['publication_year'])"
#   expect: >=1 EF452301 2008   （修复前恒为 None —— bug 回归断言）
# S4 搜索 field=species / protein_family / functional_category / chrom_pos
curl -sS "$B/genes/known/search?searchid=Hordeum&field=species" ...
curl -sS "$B/genes/known/search?searchid=Calreticulin&field=protein_family" ...
curl -sS "$B/genes/known/search?searchid=Biotic&field=functional_category" ...
curl -sS "$B/genes/known/search?searchid=7B&field=chrom_pos" ...
# S5 搜索异常：未知 field=400；空 searchid=400；缺参=422
curl -sS -o /dev/null -w '%{http_code}\n' "$B/genes/known/search?searchid=x&field=bogus"     # 400
curl -sS -o /dev/null -w '%{http_code}\n' "$B/genes/known/search?searchid=%20%20"            # 400
curl -sS -o /dev/null -w '%{http_code}\n' "$B/genes/known/search"                            # 422

# S6 by-chromosome：5A / chr7B / 1H / 3h / 54 / 非法
curl -sS "$B/genes/known/by-chromosome/5A" | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print(d['total'],d['chromosome'])"   # 68 5A
curl -sS "$B/genes/known/by-chromosome/chr7B" | python3 -c "..."   # 60
curl -sS -o /dev/null -w '%{http_code}\n' "$B/genes/known/by-chromosome/XX"   # 400

# S7 详情：保留 clone_id（旧链接仍可用）/ 新 clone_id / 404 / gene_id 查询
curl -sS "$B/genes/known/12" | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print(d['gene_name'], d['clone_id'], len(d['references']), d['publication_years'])"
curl -sS "$B/genes/known/527" | python3 -c "..."
curl -sS -o /dev/null -w '%{http_code}\n' "$B/genes/known/99999"                 # 404
curl -sS -o /dev/null -w '%{http_code}\n' "$B/genes/known/TraesCS3A03G0936700"   # 200
# 已知限制（文档化，不算回归）：含 '/' 的 gene_id 无法走路径
curl -sS -o /dev/null -w '%{http_code}\n' "$B/genes/known/Yr87%2FLr85"           # 400 或 404

# S8 stats：契约键与数字口径（对齐 frontend_change_spec.md §5.1）
curl -sS "$B/genes/known/stats" | python3 -c "
import sys,json; d=json.load(sys.stdin)['data']
print(d['total'], len(d['species']), len(d['chromosomes']), len(d['functional_category']), len(d['research_strategy']))
print(d['species_raw_count'], d['references']['entries'], d['references']['unique_dois'], sum(x['count'] for x in d['publication_year']))
"
#   expect: 1420 21 38 5 3 / 296 1570 883 1555
#   （chromosomes 必须 38 条且每条有 group=wheat|other；species 21 项；publication_year 按 token 计数=1555）
# S9 大响应压缩
curl -sS -H 'Accept-Encoding: gzip' -o /dev/null -w '%{size_download} %{http_code}\n' "$B/genes/known/all"   # <=200000,200

# S10 OpenAPI 已包含新端点与 field 参数（重启后）
curl -sS "$B/openapi.json" | python3 -c "import sys,json;d=json.load(sys.stdin);print('/api/genes/known/stats' in d['paths'])"
```

### 7.4 CGI 旧页面回归（加列兼容的实证）

```bash
# 旧检索页：显式列查询，应正常返回行（用新数据里的基因）
curl -sS 'https://wheatomics.sdau.edu.cn/cgi-bin/gene_search.py?searchid=TaCRT' | grep -c 'doi.org'    # >=1
# 旧详情页（位置下标路径！）：用一个保留 clone_id 对应的 gene_id + 一个新 gene_id（多 DOI，验证 ### 拆分不串列）
curl -sS 'https://wheatomics.sdau.edu.cn/cgi-bin/gene_search_by_id.py?searchid=EF452301' | grep -o 'Reference' | head -1
curl -sS 'https://wheatomics.sdau.edu.cn/cgi-bin/gene_search_by_id.py?searchid=EF452301' | grep -c 'doi.org'   # 2（2 DOI 两个链接）
# 旧提交页只做"能打开 + 密码门"检查（不要真提交，避免污染新数据）
curl -sS -o /dev/null -w '%{http_code}\n' 'https://wheatomics.sdau.edu.cn/cgi-bin/gene_submit.py'
```
（CGI 路径以服务器实际 `/etc/apache2/conf-enabled/*cgi*` 为准；若 CGI 已下线则跳过并在计划里注明。）

### 7.5 回滚演练（上线前）

1. root 建 drill 表：`CREATE TABLE cloned_gene_tbl_migration_drill LIKE cloned_gene_tbl;`（DDL 阶段顺带建）+ 其 backup/staging。
2. 以 drill 为目标跑通 `prepare → data --load-staging → --commit → verify`（脚本支持 `--staging/--target` 参数，见 §5.6）。
3. 跑回滚：`--phase rollback --from-backup cloned_gene_tbl_drill_backup --staging cloned_gene_tbl_migration_drill --commit`。
4. 断言：drill 行数 520→1420→520；旧 520 行指纹与备份一致；`AUTO_INCREMENT` 不回退（可接受）。
5. root 清理 drill 表。

---

## 8. 部署步骤与顺序

### 8.1 前置事实

- 生产仓库 `/var/www/FastAPI_backend_Port8000`，部署 = `git pull` + `sudo systemctl restart wheatomics-api`；webhook 只 pull 不重启（MAINTENANCE.md）。
- 服务 unit：`wheatomics-api.service`（gunicorn 8 workers，`TimeoutStopSec`/`graceful_timeout=60`）；重启后 **端口 8000 约需 2–3 分钟恢复监听**（MAINTENANCE.md §部署注意）→ 需维护窗口。
- static 文件 `git pull` 后即时生效（StaticFiles 读磁盘），Python 改动必须重启。

### 8.2 推荐顺序（4 阶段；与"DDL→导入→代码→重启"的差异见 8.3）

```
窗口 T0（约 10–15 min，低峰期）：
 P0 记录现状 + 备份
    - curl /api/genes/known/all > evidence_pre.json；记录 COUNT/MAX(clone_id)/AUTO_INCREMENT
    - mysqldump --single-transaction --no-tablespaces --default-character-set=utf8mb4 \
        cloned_gene_db cloned_gene_tbl > /var/backups/cloned_gene_tbl_pre_v2055_20261028.sql
    - (可选) 停 CGI 提交入口 / 公告
 P1 root: sudo mysql < scripts/sql/known_genes_v2055_ddl.sql     # ALTER + backup + staging
    - 校验 §7.2 V1 在 backup 表上 =520；新列存在
 P2 应用账号: 部署"后端改造"提交（只改 .py，前端未动）
    - git pull → sudo systemctl restart wheatomics-api → 等 8000 起 → S0/S1~S8 冒烟（旧数据下新代码防御性通过）
 P3 应用账号: 导入（JSONL 已离线校验+映射复核）
    - --load-staging → staging 校验 → --commit → 事务内校验 → --phase verify
    - 立即跑 §7.3 S1~S9 + §7.4 CGI 回归
 P4 部署"前端改造"提交（git pull，static 即时生效；如无 .py 改动无需重启）
    - bash scripts/spa_visual_check.sh http://127.0.0.1:8000/genes/ 
    - 视觉/功能验收（含 detail/stats/搜索/导出）
 P5 观察 30 min：journalctl -u wheatomics-api -f、/all 响应时间/大小、错误率；保留 backup/staging ≥30 天
```

若 P3 失败 → §5.8 数据回滚（应用账号，秒级），代码/前端可留在新版本（对旧数据有防御）；修复后重跑 P3。若 P2 失败 → git revert + 重启，数据尚未动，零风险。

### 8.3 为什么把"后端代码"放在"导入"之前（而不是"DDL→导入→代码"）

- DDL 是**纯追加**的，对旧代码/旧前端零影响 → 可以先做。
- 若先导入、后上代码：旧代码会按旧逻辑读新数据（能跑，但 `/all` 的 `species` 会显示 296 种原始串、`#` 被替换、chromosome 统计失真），这个"半新半旧"窗口可能被用户看到；且新 API 的验收要等到重启后才能做。
- 先上代码、后导入：新代码对**旧数据**必须全程防御（新列为 NULL、`publication_years` 缺失→回退到 `publication_year`、`chromosome` NULL→REGEX fallback），这本就是"可回滚"的硬要求；这样任何时刻用户看到的都是自洽的一侧（要么旧数据+新代码，要么新数据+新代码）。
- 前端改动最后上：新前端依赖 `/known/stats` 与新字段，等后端+数据就绪再切，避免 404/空图表。
- 代价：重启只能做一次（P2），P4 若只改 static 不重启；好处是**回滚粒度清晰**：DDL（root 可逆）→ 代码（git revert）→ 数据（备份表），互不耦合。

### 8.4 风险表

| # | 风险 | 概率/影响 | 缓解 |
|---|---|---|---|
| R1 | 应用账号权限实际是"按表授权"，staging/backup 表不可读写 | 中/高 | P1 前先 `SHOW GRANTS`；DDL 脚本用 `CREATE TABLE ... LIKE`（新表名）；若按表授权，DDL 里补 GRANT（root）；或退化方案：数据阶段改由 root 用 `sudo` 跑同一脚本（脚本支持 root socket） |
| R2 | 库默认 latin1 导致 staging/backup 建错字符集 | 中/高 | 只用 `CREATE TABLE ... LIKE`（继承 utf8）；禁止手写无 charset 的 CREATE；P1 后 `SHOW CREATE TABLE` 复核 |
| R3 | strict 模式导致 INSERT 报 1406/1264 | 高/中 | 离线校验 + staging 校验双保险；字段长度按 §1.1 上限；`publication_year=min()` 保证在 YEAR 区间 |
| R4 | **199 个孤儿旧 clone_id 深链失效（404）** | 确定/中 | 附录D-Q3：Option A（`cloned_gene_tbl_legacy` 只读回退表 + `/known/{id}` 兜底，旧链保留）或 Option B（接受 404 + 发布说明）；T1 映射已把保留率提到 62%，剩余 199 无法映射（新清单里确实没有该基因） |
| R5 | `#` 被 `normalize_text` 替换 | 确定/中 | §2.4/附录B 行级归一化 + API 冒烟断言（抽查含 `#` 的行：`grep -c '#'`/JSON） |
| R6 | `/known/stats` 路由注册顺序错误 → 404 | 中/低 | 实现时把 stats 放 `/known/{gene_id}` 之前；S8 冒烟断言 |
| R7 | `/all` 1.12MB 慢网络/移动端 | 中/中 | gzip 181KB；前端 Stats 改 `/stats`；可选 `limit`；监控 P5 |
| R8 | 重启窗口 2–3 min 503 | 确定/低 | 低峰窗口；一次性重启；前端提示 |
| R9 | 浏览器/中间缓存旧 `/all` | 低/低 | JSON 无缓存头，通常不缓存；前端发版可加 `?v=`；必要时 Nginx/Apache 侧对 `/api/genes/known/*` 加 `Cache-Control: no-store`（非必需） |
| R10 | 导入事务期间 CGI 提交并发 | 低/低 | 维护窗口内不提交；事务短（<1s）；DELETE 会短暂锁行 |
| R11 | 数据 v2055 仍在被编辑（快照后变化） | 中/低 | 报告记录 xlsx sha256/mtime；导入前与用户确认文件为最终版；重跑成本低（脚本幂等：prepare→load-staging→commit） |
| R12 | Genehub_DB 映射表缺失/ID 口径不同 | 中/中 | 脚本 T1 失败自动降级 T2 并打印覆盖率；映射明细人工复核后再 commit |
| R13 | 未来若加 utf8mb4 转换失败 | 低/低 | 本轮不转；文档记录"必须先 key_result→TEXT" |
| R14 | `key_result`/长文本撑大 `mysqldump`/事务 | 低/低 | 表仅 1420 行 ~10–15MB，无压力 |
| R15 | OpenAPI 文档/第三方按旧 schema 解析 | 低/低 | 纯追加，旧键不删；`DOIReference.doi` 可空是唯一"旧字段语义放宽"（旧行永远有 doi，仅新数据 1 条 reference 为 null） |

---

## 9. 实施阶段待办拆分（0.5–3 h 粒度，供 Lead 排期）

> 负责人建议：backend=本调查员；data=数据同学；fe=frontend-ux。前置依赖用 → 表示。

| # | 任务 | 产物 | 估算 | 依赖 |
|---|---|---|---|---|
| B1 | 定稿 DDL 脚本（含 backup/staging/索引/表注释）并评审 | `scripts/sql/known_genes_v2055_ddl.sql` | 1.0 h | — |
| B2 | `migrate_known_genes_v2055.py --phase ddl/prepare`：xlsx 读取、规范化（`###` 连接、year min、species_primary、chromosome）、JSONL 输出、离线校验报告 | 脚本 + 报告样例 | 2.5 h | task-1 的物种映射表（可并行，先用兜底规则） |
| B3 | `--phase data`：clone_id 映射（T1/T2+歧义处理）、staging 装载、事务 DELETE+INSERT、事务内校验、报告 | 脚本 | 2.0 h | B2 |
| B4 | `--phase verify` + `--phase rollback` + drill 模式 | 脚本 + `scripts/sql/known_genes_v2055_verify.sql` | 1.0 h | B3 |
| B5 | `gene.py`：known 端点改造（归一化/新字段/search field/all 分页/by-chromosome/detail references） | 代码 | 2.5 h | B1（字段名定稿） |
| B6 | `schemas/gene.py` + `legacy_parsers.py`（对齐拆分、行级 normalize） | 代码 | 0.5 h | B5 |
| B7 | `/known/stats`（SQL + Python 聚合 + 可选 TTL 缓存） | 代码 | 1.5 h | B5 |
| B8 | 本地联调：造 1420 行临时 MySQL 库（本机 docker/mysql）跑全量 API 冒烟脚本 | 冒烟脚本 `scripts/smoke_known_genes.sh` | 1.0 h | B5–B7 |
| B9 | 生产预演：生成 DDL + dry-run 报告 + 映射 CSV，人工复核 16 行位置异常/50 行 gene_name 异常/物种映射 | 复核记录 | 1.0 h | B1–B4 |
| B10 | 上线窗口执行 P0–P3（备份→DDL→后端部署→导入）并跑验证 SQL/API 冒烟 | 执行日志 + 报告 JSON | 1.5 h | B8,B9 + 前端就绪(可选) |
| B11 | CGI 回归 + 前端联调验收（与 task-3 配合） | 验收记录 | 1.0 h | B10 |
| B12 | 文档：MAINTENANCE 增"KnownGene 数据更新流程"小节（DDL/导入/回滚命令） | MAINTENANCE.md 片段（计划内） | 0.5 h | B10 |
| B13 | `chromosome`/`genome_ref` 便利键加入 summary/detail 响应（**已与前端定案，必做**，不再是可选）；与 Stats 口径联调 | 代码 + 联调记录 | 0.75 h | B5 + task-3 |
| B14 | 修既有 bug：`/known/search` SELECT 补 `publication_year`（当前恒 null） | 代码（1 行） | 0.25 h | B5 |
| B15 | （若附录D-Q3 选 Option A）`cloned_gene_tbl_legacy` 回退表：DDL 增加建表、导入脚本灌 199 孤儿行、`/known/{id}` 兜底查询 + `deprecated:true` | 代码 + SQL | 1.0 h | B1,B3 |
| B16 | `/stats` 与 `frontend_change_spec.md §5.1` 联调：键名/数字口径（phenotype_tags 分词语义、publication_year 按 token=1555、species 21 项）对齐 | 联调记录 | 0.75 h | B7 + task-3 |

合计后端/DB 约 **16–18 h**（不含前端页面改造与数据复核时间）。关键路径：B1→B5→B7→B8→B10；B2–B4 与 B5–B7 可并行（不同文件）。

---

## 附录A：`chromosome` 归一化规则（导入时 Python 计算）与无列 fallback

```python
_TOKEN_PATTERNS = [
    r"\bchr\s*([0-9]{1,2}[A-Za-z]{1,2})\b",      # "chr7A:" / "chr1H:" / "chr54"
    r"(?:^|[^0-9A-Za-z])([0-9]{1,2}[A-Za-z]{1,2})\s*:",  # "2D:2.33-..."（无 chr 前缀）
    r"\bchr\s*([0-9]{1,3})\b",                    # 兜底：chr54/chr51
    r"^([0-9]{1,2}[A-Za-z]{1,2})$",               # 旧格式 "2A"
]

def normalize_chromosome(chrom_pos: str) -> str | None:
    if not chrom_pos:
        return None
    for pat in _TOKEN_PATTERNS:
        m = re.search(pat, str(chrom_pos))
        if m:
            return m.group(1).upper()
    return None
```

- 实测 v2055：1420/1420 可解析；distinct 38（21 小麦 + 11 大麦 H + 1R/6R/7E/1S/6S/2V/6V/6U/54/51）。
- **无 `chromosome` 列时的 fallback**（如果 Lead 拒绝新增该内部列）：by-chromosome 用
  `WHERE chrom_pos REGEXP '(^|[^0-9A-Za-z])(chr)?' + token + '([^0-9A-Za-z]|$)'`（token 已白名单校验，无注入面）；stats 用 `SELECT chrom_pos, COUNT(*)` 拉一列在 Python 聚合。性能同样是 1420 行全扫，可运行；代价是代码复杂度 + 边界错误风险，故仍推荐加列。

## 附录B：known 端点的行级 legacy 归一化（局部修改，不碰全局 `normalize_text`）

```python
# app/services/legacy_parsers.py 新增
def normalize_known_text(value: object, legacy: bool) -> str:
    """known 端点专用：legacy 行保持老行为（# → '），v2055 行原样（数据带真实 #）。"""
    if value is None:
        return ""
    if legacy:
        return normalize_text(value)
    return str(value).strip()

def split_aligned_multi_value(value: object) -> list[str]:
    """按 ### 拆分并保留空位（references 位置对齐用）。"""
    if value is None:
        return []
    return [part.strip() for part in str(value).split("###")]
```

```python
# app/api/routers/gene.py 内
row = ...
legacy = row.get("reference_genome_id") is None      # v2055 全部非 NULL；回滚行/CGI 提交行 = NULL
gene_name = normalize_known_text(row.get("gene_name"), legacy)
phenotype = normalize_known_text(row.get("gene_phenotype"), legacy)
species   = normalize_known_text(row.get("gene_species"), legacy)
# 新列一律原样（不做 legacy 归一化）
protein_family = (row.get("protein_family") or "").strip() or None
```

注意：`split_legacy_multi_value` 对 `paper_title`/`paper_doi`/`key_result` 的行为**不变**（v2055 存储为 `###` 连接，与 CGI 兼容）；只有新增的 `publication_years` 解析用 `split_aligned_multi_value`。

## 附录C：CONTEXT.md 事实修正清单（请 Lead 更新共享基线）

| # | CONTEXT 原文位置 | 原文说法 | 实测/代码事实 | 影响 |
|---|---|---|---|---|
| C1 | §3 末尾 / task 描述 | "ensure_gene_like 对新数据全部 gene_id 可通过" | **不成立**：`Yr87/Lr85`（含 `/`）1 行无法通过；另 gene_name 50 行、reference_genome_id 1 行也不通过 | 详情页必须用 clone_id；参考基因组 ID 外链前需格式判定 |
| C2 | §1 行 5 | "chrom_pos → 37 种染色体标签，T.ponticum chr54/chr51（2 行未匹配正则）" | 归一化后 **38 种**；且 chrom_pos 原文格式是 `品种/版本名 + chr+区间`（1389 种不同串），旧 `LIKE '5A%'` 对新数据 0 命中 | by-chromosome 端点必须重写（§2.5/6.3） |
| C3 | §1 行 6/行 15 | "title/doi/year 按 `; ` 位置一一对应"（无例外） | 1404 行成立；**16 行计数不自洽**（12×(2,2,1)、3×(1,2,1)、1×(4,3,3)） | 导入需容错 + 报告；references 需补齐规则 |
| C4 | §4.2 | search field 枚举：`all|gene_id|gene_name|reference_genome_id|phenotype|species|doi|protein_family|functional_category` | **缺 `chrom_pos`**，而现前端下拉已有 Chromosome 选项 | 契约需补（否则旧 UI 选项会被 400） |
| C5 | §2 | "character_set / collation" 未提库默认 latin1 | 库 `character_set_database=latin1`，表显式 utf8；root 建新表必须显式 charset 或用 LIKE | DDL 脚本必须遵守（§4.2） |
| C6 | §2 | 未提 `author/author_mail NOT NULL` 无默认值 | 批量导入必须显式写 `''`（strict 模式允许空串），否则 INSERT 报 1364 | 数据阶段列清单必须含这两列 |

## 附录D：待 Lead/用户决策的问题

1. **`species_primary` 的最终 token 表**（21 个二名法 + `×Triticosecale` 显示名）以 task-1 交付为准；是否接受 `×Triticosecale` 作为 `Triticosecale`（ASCII）存库？**stats.species 实际 21 项**（前端 spec 原估 24–26，以接口为准）。
2. ~~新增内部列 `chromosome` 是否批准~~ → **已定案（前端 task-3 明确要 `chromosome` + `genome_ref` 便利键）**；按 §4.2 加列 + §6.1 返回。
3. **199 个孤儿旧 clone_id 的策略**（`/known/{id}` 旧深链）：
   - **Option A（推荐）**：建 `cloned_gene_tbl_legacy` 只读回退表 + `/known/{id}` 兜底（旧链保留，代码 +0.5–1h，表常驻 1 年）；
   - **Option B**：接受 404（成本 0，发布说明提示用基因检索）。
4. **新行的 `author` / `author_mail` 填什么**：默认 `''`（详情页"Submitted by"显示 —）；或统一填 `WheatOmics curation v2055` + 联系邮箱？（影响 1420 行展示）
5. **`/known/all` 分页默认值**：默认全量（旧行为）已定；是否给 `limit` 一个服务端上限（建议 5000）——前端分页 50/页，上限只防滥用。
6. **stats 数字口径最终确认**（与前端 spec 的估算差异，建议以前端消费本接口返回值为准，不要硬编码）：
   - `publication_year` 按 token 计数 **1555**（spec 写 1535 = 1420+115 的估算；差异=20 行有 3 个年份）；
   - `phenotype_tags` 规则（lower + 行内去重 + 丢弃 >80 字符）实测 583 distinct / 541 rows_without（spec 估 564/463）→ 建议接口返回什么前端就显示什么；
   - `references` 1570/883 与 spec 一致；`multi_species_rows` 实测 263（spec 估 236）。
7. **v2055 文件是否已定稿**（16 行位置不自洽 + 50 行 gene_name 含 `/`/`;` 是否先回修数据再导入？还是按当前快照导入 + 报告留痕）。
8. **是否在窗口期暂时关闭 CGI 提交入口**（gene_submit/gene_update），避免并发写入被替换。

---

*本文件为调查/方案交付物，未执行任何代码/DB/部署动作。实施前请先由 Lead 确认附录D。*
