# KnownGene v2055 数据剖析与导入字段映射（task-1 交付）

> 角色：data-profiler（只读调查）。本文件是**实现 importer 的直接依据**：逐列剖析 → 目标 DB 列/类型 → API 字段 → 前端展示 → 解析/校验规则。
> 输入（只读快照）：`/Users/mashengwei/Desktop/markdown/陈甜甜/known-gene-paper-20260916/已知基因逐条提取清单_20261019-合集_修正版v2055_20261019.xlsx`
> 快照指纹：size **1,688,313 B**，sha256 `e0e971c1a570904c…`（完整值见证据 JSON）。读取：`pandas.read_excel(sheet_name='数据（修正版v2055）', dtype=str, engine='openpyxl').fillna("")`。
> 对照证据：`docs/known_genes/_evidence/current_api_known_all.json`（线上 `/api/genes/known/all` 520 条摘要）。
> 聚合证据：`docs/known_genes/_evidence/profile_v2055.json`（本文件的机器可读版；不含整套数据）。

---

## 0. TL;DR（13 条关键结论）

1. **主 sheet 实测 = 1420 行 × 17 列，17 列去空白后 100% 非空**；无 tab/CR/LF，无 BMP 外字符（utf8mb3 足够）；**真实 HTML 标签 0 行**（58 行含 `<`/`>`，全部是 `P<0.05`、`E-value<0.001` 等数学比较符号 → **不要 strip，仅渲染时 HTML 转义**；见 §16 勘误）。
2. **必须改列类型的有 2 列**：`gene_phenotype`（现 `varchar(1000)`，新数据 **99 行 >1000**，max 1677 字符）、`gene_species`（现 `varchar(500)`，**60 行 >500**，max 668 字符）→ 必须改 `TEXT`；新增长字段 `protein_family`（max 2657）/`validation_method`（max 2114）也用 `TEXT`。
3. **行大小硬约束**：现表 utf8mb3 下 varchar 合计 **18,355 字符 = 55,065 字节**，距 InnoDB 单行 65,535 字节上限仅剩 ~3,490 字符。新增 varchar 只有 ~450 字符额度；**若未来改 utf8mb4（4 B/字符）会涨到 73,420 字节而建表失败**——必须先按 §11 方案把长 varchar 改 TEXT，或维持 utf8mb3。
4. **多值分隔符只有一种：半角分号+空格 `; `**。DOI/题名/年份按位置一一对应：1290 行 ×1、95 行 ×2、19 行 ×3 严格对齐；**16 行对齐异常**（12 行「2 DOI+2 题名+1 年份」、3 行「2 DOI+1 题名」、1 行「3 DOI+4 题名」），importer 不能做强断言，须按 §6 的**容许清单 + 修复规则**处理。
5. **物种：296 个原始字符串 → 23 个归一化学名**（规则+别名表覆盖 1420/1420 行，0 未命中）；主物种分布：`Triticum aestivum` 1260（88.7%）、`Hordeum vulgare` 79、`T. turgidum subsp. durum` 13……；**263 行含多物种/材料段**（181 行 2 段、58 行 3 段、24 行 4 段）。建议 `gene_species` 存原文 + `species_primary` 存学名；原文最长 668 字符（60 行 >500）。
6. **chrom_pos：37→实测 38 个染色体标签**（小麦 21 + 大麦 7 + 外来种 8：1R/7E/1S/2V/6R/6S/6V/6U + 特殊 `chr54`/`chr51` 2 个）；**2 行没有 `chr` 前缀**（`AetTA1675 2D:…`、`SYMattis 4A:…`，Excel 行 297/711），需 fallback 正则。1418/1420 行是完整 `…chr<label>:<start>-<end>Mb` 格式。
7. **`chrom_pos` 的坐标标签与 `reference_genome_id` 版本不一致**：1298 行 `Refv1.0`（IWGSC RefSeq v1.0 坐标）却配 v2.1 的 `TraesCS…03G…` 参考 ID；这是需要作者/Lead 决策的**语义问题**（详见 §8.4、§15-Q5）。
8. **受控词表：** `research_strategy` 3 值、`functional_category` 5 值、`cloning_method` 8 值（含 6 行组合值，需拆分/归一）；`protein_family`、`gene_phenotype`、`validation_method` 为**半结构自由文本**（后两者呈"早期标签体、后期叙述体"两段式写作风格，见 §9.1）。
9. **与现库 520 行对比（Lead 已核实）：** 旧库 TraesCS 类 480 行（v02 461 + v01 10 + 少量变体），新数据 v03 `TraesCS…03G…` 1291–1293 行 → **gene_id 直接命中仅 7–10 行（≈2%）**；仅靠名称/染色体的自动规则可继承 **272/520 = 52.31%**；**经 `Genehub_DB.GenePageIWGSCv1_table`（GeneIDv1/v2/v3）把 v01/v02→v03 后，clone_id 可继承 321/520 = 61.7%，199 个旧 clone_id 成为孤儿**（孤儿不复用）。
10. **clone_id 方案（321 方案）：** 能映射的 321 行旧 clone_id 不变；新插入 1099 行从 **527** 起显式赋值 → **527–1625**，导入后 `ALTER TABLE … AUTO_INCREMENT=1626`；**199 个孤儿旧 clone_id 永不复用**（删除或 is_active=0，见 §10.4）。若暂不接 genehub（仅自动规则 272 行）则插入 1148 行 → 527–1674 / AUTO_INCREMENT=1675。
11. **导入方式：** 用 **JSON Lines（UTF-8, ensure_ascii=False）** 作中间格式，不用 TSV/CSV（历史 `cloned_gene_bad_import_backup` 1636 行的引号/制表符错位即反例；本数据题名含双引号 3–8 行、分号、`; `、`###`、`|` 等，TSV 极脆弱）。1420 行规模用**单事务 executemany + staging 表 + 前后校验**即可，不需要 LOAD DATA。
12. **两个新增列建议必加：** `data_version`（如 `v2055`，用于回滚/溯源）与 `publication_years`（原文多值年，如 `2008; 2024`；现 `year(4)` 装不下 115 行）。旧字段名/语义全部不改，向后兼容 CGI 与现有 SPA。
13. **后端阻塞（新增发现，Lead 已记录）：26 行含 `#`**（species 3 / gene_phenotype 13 / key_result 14 / function_description 10 / protein_family 7 / cloning_method_description 23 / validation_method 19，多列重叠；如 `7S#1`、`6Ae#1`、`6Ae#3`、`hc#28`、`QTgw.cau-7D`），**现 `legacy_parsers.normalize_text()` 把 `#`→`'` 会破坏这些内容**（详情 API 直接受影响）。建议按 `data_version` 分支：新行用 raw/新 cleaner，旧行保留旧 `normalize_text`（见 §11.4、§15-Q13）。

---

## 1. 数据来源与读取口径

### 1.1 工作簿 9 个 sheet

| sheet | 尺寸（行×列） | 作用 / 导入影响 |
|---|---|---|
| **数据（修正版v2055）** | **1421×17**（表头 1 + 数据 1420） | 唯一导入来源 |
| 修改记录 | 1154×9（数据 1153） | 跨多轮版本的逐行修改日志；类别：清洗 464 / 新增 440 / D6 121 / K 36 / 删除 36 / 核查 17 / K(全文) 16 / D1 10 / U 10 / D2 3 |
| 物种改写明细 | 1025×6（数据 1024） | **权威物种归一化记录**：原写法→14 个 NCBI 学名，附"被移除的补充信息" |
| 文本清洗明细 | 339×4（数据 338） | 记录哪些行的哪些字段被清洗（不存原值） |
| 未决清单 | 1×8（**空**） | 无未决项 |
| D10 key_result草案 | 1×6（**空**） | 说明 sheet 称"40 行短 key_result 已列出"，实际已通过 K/KF 补写清空 |
| K补写依据 | 37×6（数据 36） | key_result 按 PubMed 摘要补写，4 个 PMID、18 个 DOI |
| K补写依据(全文) | 17×6（数据 16） | key_result 按全文补写（3 个 PMC 全文 + 1 个本地 PDF） |
| 说明 | 33×1 | 作者约定 D1–D10 / U1–U10 / W13 / W22 / K / KF（全文见 §14） |

### 1.2 读取注意事项（已实测）

- 用 `dtype=str` 可避免 `publication_year`、`gene_id` 被 pandas 误推断类型；`fillna("")` 后**无 NaN**。
- 文件可能被 Excel 占用：`openpyxl`/`pandas engine='openpyxl'` 只读打开可靠；**不要**依赖 `xlrd`。
- 表头含中文括号（如 `gene_id（入库）`），建议 importer **按列位（0–16）贴合**或做列名规范化（去 `（入库…）` 后缀），不要硬编码完整中文名。
- 单元格内无 `\t`/`\r`/`\n`；但**字段内存在双引号**（`function_description` 12 行、`protein_family` 10 行、`key_result` 8 行、`cloning_method_description` 3 行、`title` 3 行），这是弃用 TSV/CSV 的直接原因。
- 空白处理：所有列 `strip()` 后 100% 非空；`gene_name` 有 2 行含空格（`TaGly I`、`Pm60 (MlIW226 / MlIW6 / MlIW113; Hap 3/5/6)`），入库前仅 trim 首尾，**不要**删除内部空格。

---

## 2. 主 sheet 逐列剖析总表

| # | 列（Excel 原名） | 非空 | 唯一值 | 字符 min/median/p95/max | 字节 max | `<`（P值符号）行 | 分号 `;` 行 | `; ` 行 | 双引号行 | 典型值样本（截断） |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | gene_id | 1420 | 1395 | 5/19/21/28 | 28 | 0 | 0 | 0 | 0 | TraesCS5A03G0935400 / TraesCS1B03G0192900 |
| 2 | ref_genome_id | 1420 | 1386 | 8/19/25/42 | 42 | 0 | 0 | 0 | 0 | TraesCS4D03G0655500 / TraesCS7D03G0377400 |
| 3 | gene_name | 1420 | 1418 | 2/8/12/43 | 43 | 0 | 9 | 1 | 0 | TaVRN-A1 / HvPTR1 |
| 4 | species | 1420 | 296 | 15/31/487/668 | 668 | 0 | 263 | 263 | 0 | Triticum aestivum (bread wheat) / Hordeum vulgare (barley) |
| 5 | chrom_pos | 1420 | 1389 | 24/31/31/41 | 41 | 0 | 0 | 0 | 0 | Refv1.0 chr4D:447.639-447.642Mb / Refv1.0 chr7D:117.243-117.246Mb |
| 6 | gene_phenotype | 1420 | 1070 | 10/359/1081/1677 | 1677 | 5 | 897 | 897 | 0 | Not determined / Drought tolerance |
| 7 | key_result | 1420 | 1151 | 298/1270/1760/3051 | 3051 | 8 | 954 | 947 | 8 | We characterized seven GA3OX genes in br / In plant cells, Ca2+ ions are important |
| 8 | function_description | 1420 | 1420 | 343/1123/1650/2236 | 2236 | 12 | 1388 | 1388 | 12 | Encodes HvPTR1, a plasma-membrane peptid / Encodes TaERF1, a 355-amino-acid ERF/AP2 |
| 9 | protein_family | 1420 | 1176 | 22/366/1897/2657 | 2657 | 0 | 1025 | 1025 | 10 | HSP90 (heat shock protein 90) family - A / NAC transcription factor family |
| 10 | cloning_method | 1420 | 8 | 10/22/27/51 | 51 | 0 | 6 | 6 | 0 | Homology-based cloning / Not reported |
| 11 | cloning_method_description | 1420 | 1221 | 224/862/1412/1757 | 1757 | 7 | 974 | 966 | 3 | Haplotypes of TaCYP78A3/5/16/17-A were a / Homologs of the VACUOLAR IRON TRANSPORTE |
| 12 | validation_method | 1420 | 895 | 12/149/1443/2114 | 2114 | 9 | 1363 | 1363 | 0 | Expression analysis / VIGS; Expression analysis; Phenotyping |
| 13 | research_strategy | 1420 | 3 | 12/16/16/16 | 16 | 0 | 0 | 0 | 0 | Reverse genetics / Forward genetics |
| 14 | functional_category | 1420 | 5 | 15/23/32/32 | 32 | 0 | 0 | 0 | 0 | Biotic & Abiotic Stress / Quality & Yield |
| 15 | title | 1420 | 824 | 48/112/220/473 | 473 | 0 | 138 | 127 | 3 | Wheat V-H+-ATPase Subunit Genes Signific / Molecular analysis of common wheat genes |
| 16 | doi | 1420 | 820 | 13/25/47/82 | 82 | 0 | 130 | 130 | 0 | 10.1371/journal.pone.0086982 / 10.1111/j.1469-8137.2011.03715.x |
| 17 | publication_year | 1420 | 102 | 4/4/10/16 | 16 | 0 | 115 | 115 | 0 | 2022 / 2024 |

> 说明：`min/median/p95/max` 为**字符数**（MySQL varchar(N) 也按字符计）；"字节 max"为 UTF-8 字节数（=字符数，因全部字符 ≤ 3 字节且无 BMP 外字符，见 §11.3）。
> `<` 列不是 HTML 标签：全表 **58 行含 `<`/`>`**，全部是 `P<0.01`/`E-value<0.001`/`<70%`/`<8% SBR` 等数学比较符号（严格 HTML 标签正则 0 命中，见 §16.1）→ 导入保留原字符，**只在渲染层做 HTML 转义**。
> `;` 与 `; ` 的差异只有题名/基因名中合法的科学分号（如 `HKT1;4`、`(1,3;1,4)-β-d-Glucan`），**不可用 `;` 裸切**。

### 2.1 每列最长值（截断 120 字符，用于估类型）

| 列 | 最长值（截断 120 字符） | 长度 |
|---|---|---|
| gene_id | HORVU.MOREX.PROJ.1HG00011510 | 28 |
| ref_genome_id | Ae.longissima_6S_ORF:51,756,423-51,772,629 | 42 |
| gene_name | Pm60 (MlIW226 / MlIW6 / MlIW113; Hap 3/5/6) | 43 |
| species | Triticum aestivum (bread wheat: the winter and spring wheat varieties used for TaHST1L overexpression and RNAi lines, th | 668 |
| chrom_pos | Ae.umbellulata.v1 chr6U:472.602-472.618Mb | 41 |
| gene_phenotype | Cell wall invertase positively regulating resistance to Fusarium crown rot and sharp eyespot: FCR and SE are serious soi | 1677 |
| key_result | TaST (Triticum aestivum salt tolerance gene) was identified by screening a wheat cDNA microarray. Gene-chip analysis of | 3051 |
| function_description | RG1/TaAPA2 corresponds to TraesCS7D02G010200 on the short arm of wheat chromosome 7D and encodes a protein with a von Wi | 2236 |
| protein_family | PEBP family (FLOWERING LOCUS T-like) - VRN-D3/FT-D1 (TraesCS7D02G111600, printed in the 2024 Plant Communications paper | 2657 |
| cloning_method | Homology-based cloning; Transcriptome-based cloning | 51 |
| cloning_method_description | TaCRK10 was identified from the HTSP-resistant wheat cultivar Xiaoyan 6 (XY6): a 1,649-bp cDNA fragment up-regulated und | 1757 |
| validation_method | Fine mapping of Rph7 on the short arm of chromosome arm 3H near the telomere using a high-resolution F2 population of 22 | 2114 |
| research_strategy | Reverse genetics | 16 |
| functional_category | Physiology & Metabolic Processes | 32 |
| title | Combinational transformation of three wheat genes encoding fructan biosynthesis enzymes confers increased fructan conten | 473 |
| doi | 10.1016/j.molp.2021.05.009; 10.1016/j.molp.2021.05.010; 10.1038/s41588-022-01022-1 | 82 |
| publication_year | 2012; 2024; 2002 | 16 |

---

## 3. 逐列映射表（Excel → 目标 DB → API → 前端）

> 目标库：`cloned_gene_db.cloned_gene_tbl`。原则：**旧列名/语义不删不改**（CGI 与现有 SPA 兼容），新字段用新列名。类型建议的完整论证见 §11。

| # | Excel 列 | 目标 DB 列（建议类型） | API 字段（新增标 ★） | 前端展示建议 | 入库/派生规则与要点 |
|---|---|---|---|---|---|
| 1 | gene_id（入库） | `gene_id varchar(300)`（**保留**，实测 max 28） | `gene_id` | 详情页主 ID badge + 复制；可链到 `/api/genes/detail/{gene_id}`（GeneHub 支持 v1/v2/v3） | **原样入库**。1420/1420 通过 `ensure_gene_like ^[A-Za-z0-9_.:-]+$`；注意 25 行重复（D7/同基因多文献，见 §5） |
| 2 | 参考基因组ID（入库） | ★ `reference_genome_id varchar(128)`（实测 max 42） | ★ `reference_genome_id` | 详情"参考基因组"行（与 gene_id 不同则加 tag）；可用于"按基因组查" | **原样入库**；与 gene_id 相同 1240 行、不同 180 行（多为 GenBank 登录号 gene_id + v03 参考 ID，正常） |
| 3 | gene_name（入库） | `gene_name varchar(500)`（保留，max 43） | `gene_name` | 标题主行；含 `/` 的别名（34 行）拆为 chips，主名取第一段；含空格 2 行、含 `;` 9 行 | 原样入库 + 派生 `gene_name_primary`（第一段，`/` 与 `;` 切）可选；URL 参数必须 encode（34 行含 `/`） |
| 4 | 物种信息（入库） | `gene_species **TEXT**`（现 varchar(500) 会截断 60 行） | `species`（旧原文）、★`species_primary`、可选 ★`species_detail` | 列表/摘要展示 `species_primary`（学名）+ 英文常用名；详情"物种/材料"卡片显示原文（可折叠） | `gene_species`=原文；`species_primary`=首物种归一化学名（§7）；`species_detail`=原文或括号内材料描述（可选） |
| 5 | chrom_pos（入库） | `chrom_pos varchar(500)`（保留）+ ★`chromosome varchar(16)`（派生） | `chrom_pos`、★`chromosome` | 染色体 badge 用 `chromosome`（如 `3B`）；悬浮显示完整 `chrom_pos`（含组装前缀） | `chromosome`=`chr` 后 token（38 种，含 1R/7E/54/51…，§8）；by-chromosome 查询用它（兼容大小写与 `chr` 前缀） |
| 6 | gene_phenotype（入库） | `gene_phenotype **TEXT**`（现 varchar(1000)：99 行 >1000） + ★`phenotype_brief TEXT`（团队已定：冒号/分号前首段，max 666） + 可选 ★`phenotype_tags TEXT`（JSON array） | `phenotype`（旧原文）、★`phenotype_brief`、可选 ★`phenotype_tags[]` | 列表/摘要显示 `phenotype_brief`（clamp ~200 字符）；详情显示原文（clamp+展开）；chips 可选 `phenotype_tags` | 原文入库；`phenotype_brief` = 首段（括号感知按 `;` 切 → 取第一段 → 在首个 `:` 处截断；实测截断后 max 666，若首段无 `:` 且 >666 则按词边界截到 666）；`phenotype_tags` 为可选派生（§9.4） |
| 7 | key_result（入库，≤500 词英文） | `key_result varchar(15000)`（**保留**；实测 max 3051 字符/464 词，utf8mb3 占 ~45KB 行内） | `key_result[]` | 详情"关键结果"段落（clamp + 展开） | 新数据**单段无 `###`**；旧 API 的 `split_legacy_multi_value` 会返回单元素数组，兼容但语义变化需知会前端 |
| 8 | function_description（入库） | `function_description text`（保留，max 2236） | `function_description` | 段落 clamp | 原样 |
| 9 | 蛋白家族（入库） | ★ `protein_family **TEXT**`（max 2657） + 可选 ★`protein_family_label varchar(128)`（派生） | ★`protein_family`、★`protein_family_label` | "蛋白家族"卡片：label chip + 原文展开 | 原文入库；label=首分句（截 ` - ` 前，§9.5）；1176 个不同值、1025 行含 `;`、905 行含 ` - ` |
| 10 | cloning_method（入库） | `cloning_method varchar(255)`（保留，max 51） | `cloning_method` | 受控 badge（8 值→归一后 5 类） | 原样 + 归一：`Functional`→`Functional cloning`；6 行组合值拆 2 个标签（§9.2） |
| 11 | cloning_method_description（入库） | `cloning_method_description text`（保留，max 1757） | `cloning_method_description` | 段落 clamp | 原样（含 1 行 `|`，无需处理） |
| 12 | 验证方法（入库） | ★ `validation_method **TEXT**`（max 2114） + ★`validation_methods TEXT`（JSON array，派生/归一） | ★`validation_methods[]` | 方法 chips（受控 20–30 类）；未识别标签少用 | 原文入库；`validation_methods` 从 `; ` 拆 + 括号感知 + 别名归一（§9.3：6095 个 token→1087 唯一） |
| 13 | 研究策略（入库） | ★ `research_strategy varchar(40)`（3 值，max 16） | ★`research_strategy` | badge（3 色） | 受控词表，直接入库 + 枚举校验 |
| 14 | 功能大类（入库） | ★ `functional_category varchar(64)`（5 值，max 32） | ★`functional_category` | badge/筛选（5 类配色） | 受控词表，直接入库 + 枚举校验 |
| 15 | title（入库） | `paper_title text`（保留；max 473） | `paper_title[]`（旧）、★`references[].title` | References 卡片（每篇：题名+DOI+年份）；题名可截断 | 原样存 `; ` 连接原文；API 按 `; ` 位置拆分（§6）；旧库是 `###`，API 需双格式兼容 |
| 16 | doi（入库） | `paper_doi text`（保留；max 82） | `dois[]`（摘要）、★`references[].doi` | DOI 链接 `https://doi.org/{doi}` | 原样存 `; ` 连接；820 个唯一 DOI 字符串；130 行多 DOI；全部合法 DOI 格式（0 非法） |
| 17 | publication_year（入库） | `publication_year year(4)`（保留，**存首个/最小年份**） + ★`publication_years varchar(64)`（原文 `2008; 2024`） | `publication_year`（旧，int）、★`publication_years[]` | 详情显示首个年份；References 每篇年份 | 115 行多值 → 原文入 `publication_years`；`year(4)` 只放第 1 个（或最小）年份；所有年份 1998–2026 |
| — | *(无)* | `author varchar(100) NOT NULL` | `author` | 详情"Submitted by"（显示占位） | 新数据无作者 → **必须填占位值**（如 `WheatOmics curation`，否则 NOT NULL 报错）；建议同 author_mail |
| — | *(无)* | `author_mail varchar(200) NOT NULL` | `author_mail` | 同上 | 占位需是合法 email 形态（schema 用 EmailStr），如 `curation@wheatomics.sdau.edu.cn` |
| — | *(无)* | `submission_date date` | `submission_date` | meta 行 | 填导入日期 |
| — | *(无)* | ★`data_version varchar(32)` | ★`data_version` | 详情 meta / 调试 | 填 `v2055`（回滚与溯源，强烈建议） |
| — | *(无)* | `clone_id int unsigned AUTO_INCREMENT` | `clone_id` | meta | 见 §10：旧行保留、新行 527 起、退役 ID 不复用 |

> 派生列（建议在 importer 中生成并入库，API 只读）：`species_primary`、`species_detail`（可选）、`chromosome`、**`phenotype_brief`（团队已定）**、`phenotype_tags`（可选）、`validation_methods`、`protein_family_label`（可选）、`publication_years`、`data_version`。自然键/幂等键见 §5.4。

---

## 4. 数据规模与两段式写作风格（影响解析策略）

实测本工作簿由**两种写作风格**的行混合而成（按 Excel 行序，非随机）：

| 行区间（0-based idx） | 风格 | 判定依据 |
|---|---|---|
| 0–~667 | **标签体**：phenotype/验证方法等为短标签串 | `gene_phenotype` 分句 max ≤200 字符；`validation_method` 分句 max ≤80；`protein_family` 通常 <500 字符 |
| ~668–1419 | **叙述体**：同字段变成英文长句/机制描述 | `gene_phenotype` 有 >200 字符分句的行 **720 行**（最早 idx 668，且 668 以前 0 行）；`validation_method` >80 字符分句 **567 行**（最早 idx 824）；`protein_family` >500 字符 **592 行**（最早 idx 670） |
| ~1036–1419 | 物种也变成"材料长描述" | `species` >100 字符 **339 行**（最早 idx 1036，668 前 0 行）；>400 字符 126 行；>500 字符 60 行 |

**结论**：`gene_phenotype` / `validation_method` / `protein_family` 的"拆标签"只能作为**展示用派生**，不能作为唯一数据源；`species` 必须做归一化派生（§7）；前端对长文本一律 clamp+展开。

---

## 5. 身份、去重与自然键

### 5.1 重复模式（均按 `说明` sheet 的 D5/D7 判断为**预期**）

| 列 | 唯一值 | 重复行 | 典型重复 | 判断 |
|---|---|---|---|---|
| gene_id | 1395 / 1420 | 25 行（23 组） | `TraesCS5A03G0935400`×3、`TraesCS1B03G0192900`×3、`KF061193`×2… | **预期**：同一基因多个等位/多篇文献（D7 同理全部保留）；`TaVRN-A1`×3 是 D2 人为拆行 |
| 参考基因组ID | 1386 / 1420 | 34 行（30 组） | `TraesCS4D03G0655500`×3、`TraesCS7D03G0377400`×3… | **明确预期**（说明 D7：同一参考基因组 ID 多行全部保留） |
| gene_name | 1418 / 1420 | 2 行超额 | `TaVRN-A1`×3（Excel 行 470/471/472 附近） | **预期**（D2：同一基因 3 篇文献拆 3 行） |
| chrom_pos | 1389 / 1420 | 31 行（27 组） | 同一坐标多行（同基因多文献/同源拷贝） | 预期 |
| doi | 820 唯一字符串 / 1420 | 600 行 | 同一 DOI 出现在多行（同文献多基因/多拷贝） | 预期 |

**重要勘误**：把 `gene_name` 做「小写+去空格」归一化会出现 3 对"重复"：`V-ATPase-C` vs `V-ATPase-c`、`V-ATPase-D` vs `V-ATPase-d`、`V-ATPase-A` vs `V-ATPase-a`（共 6 行）。经 `protein_family` 核对，它们是 **不同亚基**（C/c、D/d、A/a 是 V-ATPase 不同亚基命名，大小写有意义），**不是重复行**。CONTEXT 中"归一化后重复 6 行"若被当作重复处理会误删。真正的重复只有 `TaVRN-A1`×3（D2 预期）。

### 5.2 基因 ID / 参考 ID 格式分布（决定 clone_id 映射难易）

- 新数据 `gene_id`：v03 `TraesCS…03G…` **1158**、INSDC 登录号 169、`HORVU…` 56、其他数据库 ID（`MLOC_/TRITD/TCONS_/tplb/TuSPR`）7、其他命名（`TraesFLD/TraesMAC/CSIAAS/Tel7E01T…` 等）30。
- 新数据 `参考基因组ID`：v03 `TraesCS…03G…` **1293**、`HORVU…` 77、其他/组装区段 26、INSDC 23、1 个组装区间（`Ae.longissima_6S_ORF:51,756,423-51,772,629`）。
- **旧库 `gene_id` 是 v02（`TraesCS…02G…`）480 行** + INSDC 24 + HORVU 2 + 基因名形态 6 + 其他 8；旧库 `gene_name` 463 唯一（57 行同源拷贝同名）。旧库还有 **2 行 gene_id/gene_name 列错位**（clone_id 28 `TaBot1-4D` / `TraesCS4D02G326900`；clone_id 29 同理），迁移时需修正。
- 旧 v02 → 新 v03 无法靠字符串（实测只换版本位仅 3 行命中），**必须用生产 `Genehub_DB.GenePageIWGSCv1_table`（GeneIDv1/v2/v3 三列）映射**（见 §10.3）。

### 5.3 自然键 / 幂等键（实测）

| 候选键 | 重复行数 |
|---|---|
| `gene_id + gene_name + doi` | **0** ✅ |
| `ref_genome_id + gene_name + doi` | **0** ✅ |
| 17 列全字段 hash | **0** ✅ |
| `gene_id + doi` | 6（同一基因多行共用同一 DOI 文件时） |
| `gene_id + title` | 6 |

**建议**：以 **`sha256(gene_id ‖ ref_genome_id ‖ gene_name ‖ doi_cell)`** 作为导入幂等键；`gene_id` 单独**不能**做唯一键（25 行重复，且 D7 要求保留）；不要按 ref ID 去重。

### 5.4 其他身份/展示细节

- `gene_name` URL 安全性：34 行含 `/`（如 `TaCRT-A/TaCRT3-A`、`Q/Rht23`）、2 行含空格、9 行含 `;`（如 `TdPIP2;1`）、1 行含括号（`Pm60 (MlIW226 / MlIW6 / MlIW113; Hap 3/5/6)`）。**详情页请坚持用 `clone_id` 作为路由参数**（现有代码注释也这么说），gene_name 仅作显示/搜索。
- `chrom_pos` 完整值含组装前缀（32 种，如 `Refv1.0` 1298、`MorexV3` 72、`Zavitan.v1.0` 6、`Lo7.v1` 4…），前端展示时建议 `chromosome` badge + tooltip 原文。

---

## 6. 多值字段（doi / title / publication_year）拆分规则

### 6.1 分隔符与位置对应（作者约定，实测验证）

- 唯一分隔符：**半角分号 + 一个空格 `; `**（说明 sheet 第 33 行原文；全表 130 行 DOI、127 行题名、115 行年份含 `; `）。
- 规则：第 k 个 DOI ↔ 第 k 个题名 ↔ 第 k 个年份。
- 实测每行数量分布（DOI/题名/年份组数）：

| (n_doi, n_title, n_year) | 行数 |
|---|---|
| (1,1,1) | 1290 |
| (2,2,2) | 95 |
| (3,3,3) | 19 |
| (2,2,1) | **12（异常）** |
| (2,1,1) | **3（异常）** |
| (3,4,3) | **1（异常）** |

→ 严格对齐 **1404/1420 = 98.87%**，**16 行异常**。单行最多 3 个 DOI、3 个年份、4 段题名。

### 6.2 16 行异常明细与建议

| Excel 行 | gene_id | gene_name | n_doi | n_title | n_year | 现象 / 建议 |
|---|---|---|---|---|---|---|
| 28 | EU182655.1 | TdPIP2;1 | 2 | 3 | 2 | title 多 1 段（第 2、3 段重复）→ 疑似复制错位，建议 author 修正或按 DOI 去重 |
| 241 | TraesCS1D03G0038800 | DRG1/TaACT7/TaACTIN7-D | 2 | 2 | 1 | 年份只填了 1 个（两篇同年或漏填）→ 导入时复制到每篇 + 标记复核 |
| 245 | TraesCS2A03G0801300 | TaSERK1-A | 2 | 2 | 1 | 年份只填了 1 个（两篇同年或漏填）→ 导入时复制到每篇 + 标记复核 |
| 249 | TraesCS2B03G0887400 | TaSERK1-B | 2 | 2 | 1 | 年份只填了 1 个（两篇同年或漏填）→ 导入时复制到每篇 + 标记复核 |
| 254 | TraesCS2D03G0741000 | TaSERK1-D | 2 | 2 | 1 | 年份只填了 1 个（两篇同年或漏填）→ 导入时复制到每篇 + 标记复核 |
| 283 | TraesCS6A03G0761900 | TaNF-YB1 | 2 | 2 | 1 | 年份只填了 1 个（两篇同年或漏填）→ 导入时复制到每篇 + 标记复核 |
| 331 | TraesCS3A03G0970200 | TaABI3-A1/TaVP1-A | 2 | 2 | 1 | 年份只填了 1 个（两篇同年或漏填）→ 导入时复制到每篇 + 标记复核 |
| 386 | TraesCS7D03G0023900 | RG1/TaAPA2 | 2 | 2 | 1 | 年份只填了 1 个（两篇同年或漏填）→ 导入时复制到每篇 + 标记复核 |
| 416 | HORVU.MOREX.r3.2HG0188290 | HvPIP1;6 | 1 | 2 | 1 | title 多 1 段（第 2、3 段重复）→ 疑似复制错位，建议 author 修正或按 DOI 去重 |
| 425 | HORVU.MOREX.r3.6HG0615280 | HvNIP2;1 | 1 | 2 | 1 | title 多 1 段（第 2、3 段重复）→ 疑似复制错位，建议 author 修正或按 DOI 去重 |
| 439 | HORVU.MOREX.r3.1HG0077240 | HvFT3 | 2 | 2 | 1 | 年份只填了 1 个（两篇同年或漏填）→ 导入时复制到每篇 + 标记复核 |
| 475 | TraesCS6D03G0476300 | TaPHT2 | 1 | 2 | 1 | title 多 1 段（第 2、3 段重复）→ 疑似复制错位，建议 author 修正或按 DOI 去重 |
| 595 | TraesCS1A03G0737000 | TaAMT2;3a | 1 | 2 | 1 | title 多 1 段（第 2、3 段重复）→ 疑似复制错位，建议 author 修正或按 DOI 去重 |
| 617 | TraesCS7A03G0602700 | TaGW8-7A/TaSPL16-7A | 2 | 1 | 1 | 年份只填了 1 个（两篇同年或漏填）→ 导入时复制到每篇 + 标记复核 |
| 619 | TraesCS7B03G0430500 | TaGW8-7B/TaSPL16-7B | 2 | 1 | 1 | 年份只填了 1 个（两篇同年或漏填）→ 导入时复制到每篇 + 标记复核 |
| 621 | TraesCS7D03G0590200 | TaGW8-7D/TaSPL16-7D | 2 | 1 | 1 | 年份只填了 1 个（两篇同年或漏填）→ 导入时复制到每篇 + 标记复核 |
| 986 | TraesCS4D03G0799400 | TaTIP4;1 | 1 | 2 | 1 | title 多 1 段（第 2、3 段重复）→ 疑似复制错位，建议 author 修正或按 DOI 去重 |
| 1069 | TraesCS4B03G0822800 | TaPHT1;9-4B | 1 | 2 | 1 | title 多 1 段（第 2、3 段重复）→ 疑似复制错位，建议 author 修正或按 DOI 去重 |
| 1076 | TraesCS4D03G0828800 | TaHKT1.5-D | 2 | 4 | 2 | title 多 1 段（第 2、3 段重复）→ 疑似复制错位，建议 author 修正或按 DOI 去重 |
| 1093 | TraesCS5D03G1120600 | TaSPL6-D | 1 | 2 | 1 | title 多 1 段（第 2、3 段重复）→ 疑似复制错位，建议 author 修正或按 DOI 去重 |
| 1094 | TraesCS5D03G1233100 | Lr1 | 2 | 2 | 1 | 年份只填了 1 个（两篇同年或漏填）→ 导入时复制到每篇 + 标记复核 |
| 1112 | TraesCS7A03G0678600 | TaARE1-7A | 2 | 2 | 1 | 年份只填了 1 个（两篇同年或漏填）→ 导入时复制到每篇 + 标记复核 |
| 1117 | TraesCS7B03G0545300 | TaARE1-7B | 2 | 2 | 1 | 年份只填了 1 个（两篇同年或漏填）→ 导入时复制到每篇 + 标记复核 |
| 1125 | TraesCS7D03G0615900 | TaMYB4-7D | 1 | 2 | 1 | title 多 1 段（第 2、3 段重复）→ 疑似复制错位，建议 author 修正或按 DOI 去重 |
| 1126 | TraesCS7D03G0650400 | TaARE1-7D | 2 | 2 | 1 | 年份只填了 1 个（两篇同年或漏填）→ 导入时复制到每篇 + 标记复核 |
| 1402 | TraesCS7D03G0250300 | VRN-D3/FT-D1 | 3 | 4 | 3 | title 多 1 段（第 2、3 段重复）→ 疑似复制错位，建议 author 修正或按 DOI 去重 |

处置建议：
- **12 行「1 个年份 + 多 DOI」**：该单元格只填了一个年份（两篇可能同年，也可能漏填）。导入时把该年份**复制给每个 DOI**，同时在 dry-run 报告里列为 `REVIEW_MULTIYEAR` 让作者复核；不要报错中断。
- **3 行「1 段题名 + 2 个 DOI」**（TaGW8-7A/B/D）：第 2 篇题名缺失。`references[1].title = null`；报告中列 `REVIEW_MISSING_TITLE`。
- **1 行「3 DOI + 4 段题名 + 3 年份」**（Excel 行 1402，`VRN-D3/FT-D1`）：第 2、3 段题名完全重复，应为 `T1; T2; T3`（第 3 篇是 `TaFT-D1 positively regulates grain weight…`）。**建议作者在下版 Excel 修正**；importer 兜底规则：题名数 > DOI 数时保留前 n 段并报 `REVIEW_TITLE_SHIFT`（或按题名去重后取前 n）。 

### 6.3 拆分函数语义（可直接照抄实现）

```python
SEP = "; "
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
YEAR_RE = re.compile(r"^\d{4}$")

def split_papers(doi_cell: str, title_cell: str, year_cell: str, row_id) -> list[dict]:
    dois   = [x.strip() for x in doi_cell.split(SEP)] if doi_cell else []
    titles = [x.strip() for x in title_cell.split(SEP)] if title_cell else []
    years  = [int(x) for x in (y.strip() for y in year_cell.split(SEP)) if YEAR_RE.match(x)]
    assert dois and all(DOI_RE.match(d) for d in dois), f"row {row_id}: bad DOI"
    assert len(set(dois)) == len(dois), f"row {row_id}: duplicate DOI in one row"
    n = len(dois)
    # --- 容许的 16 行异常（见 §6.2）---
    if len(years) == 1 and n > 1:
        years = years * n                     # 12 行：年份复制 + REVIEW_MULTIYEAR
    assert len(years) == n, f"row {row_id}: year count {len(years)} != doi count {n}"
    if len(titles) > n:
        titles = titles[:n]                   # 1 行：多余重复题名截断 + REVIEW_TITLE_SHIFT
    titles = titles + [None] * (n - len(titles))   # 3 行：缺题名 -> None
    return [{"doi": d, "title": t, "year": y} for d, t, y in zip(dois, titles, years)]
```

**边界情况（必须知道）**：
- `title` 单元格里存在**合法的 `;`（无空格）**：13 行，如 `HKT1;4`、`HKT1;5`、`(1,3;1,4)-β-d-Glucan`、`HvNIP2;1`。→ **只能用 `"; "` 切，永不按 `";"` 裸切**（否则 13 行题名被切碎，且与 DOI 数量对不上）。
- `doi` 单元格无 `;` 裸分隔（实测 0 行）；DOI 全部合法（0 非法），无需 URL 解码。
- 旧库 `paper_title/paper_doi` 是 `###` 连接（CGI 时代）；新旧混合期间 API 的兼容拆分应为：先按 `###` 切，长度 1 时再按 `"; "` 切（或统一 `re.split(r"###|; ", value)` 后过滤空串）。

### 6.4 「原样入库」vs「派生新列」

| 字段 | 原样入库（旧列） | 派生新列 | 说明 |
|---|---|---|---|
| doi | `paper_doi`（`; ` 连接原文） | ★`doi_list` 可省（API 现拆） | 入库存 raw，API 返回 `dois[]` 与 `references[].doi` |
| title | `paper_title`（`; ` 连接原文） | — | 同上 |
| publication_year | `publication_year`（首个/最小年）+ ★`publication_years`（raw） | ★API `publication_years[]` | `year(4)` 不能装多值 |
| references | — | 可选 `references_json TEXT`（`[{doi,title,year}]`） | 若追求查询/性能可物化；否则 API 动态拼装即可（1420 行规模无压力） |
| species | `gene_species`（raw） | ★`species_primary`、★`species_detail` | 见 §7 |
| phenotype | `gene_phenotype`（raw） | ★`phenotype_brief`（团队已定）、可选 `phenotype_tags` | 见 §9.4 |
| validation | `validation_method`（raw） | ★`validation_methods` | 见 §9.3 |
| protein family | `protein_family`（raw） | ★`protein_family_label`（可选） | 见 §9.5 |

---

## 7. 物种归一化（296 原始字符串 → 23 个学名）

### 7.1 原始数据状况

- **296 个不同原始字符串**（1420 行全部非空）；**263 行含 `; `**（一行多个物种/材料段）：181 行 2 段、58 行 3 段、24 行 4 段；1157 行单段。
- 长材料描述：`species` 长度 >100 字符 **339 行**、>400 字符 126 行、>500 字符 **60 行**、max **668 字符**；括号内容常是材料清单（品种、突变体、转基因系、异源宿主等）。
- 作者已在 `物种改写明细` sheet 对 1024 行给出「原写法 → 统一为（NCBI Taxonomy）」+「被移除的补充信息」，统一值仅 14 个学名；但主 sheet 仍有 433 行不在该改写表覆盖范围（新增行/未套用行），**因此导入层必须自己做统一（不能只用该 sheet 当映射表）**。
- 归一化实测：**1420/1420 行可提取主物种，0 未命中**（1 行 `x Triticosecale` 特例）。

### 7.2 归一化规则（正则 + 别名表兜底）

1. **主物种 = 字符串中第一个出现的分类学名**（作者排序即"基因来源种在前，验证材料/异源宿主在后"；例：`Aegilops tauschii (…); Triticum aestivum (…)` 的主物种是 `Aegilops tauschii`，其 `reference_genome_id` 也确实是 D 基因组 TraesCS…D…，规则自洽）。
2. 提取正则（行首锚定，覆盖 1420/1420）：
   ```python
   FIRST = re.compile(
       r"^\s*(x\s+Triticosecale|Triticosecale|Triticum|Aegilops|Hordeum|Secale|"
       r"Dasypyrum|Thinopyrum|Agropyron|Elymus|Haynaldia)\s+([a-z][a-z\-]+)"
       r"(?:\s+(subsp\.|ssp\.|var\.)\s+([a-z][a-z\-]+))?"
   )
   ```
   → 得到 base（如 `Triticum turgidum subsp. durum`），再经别名表去重（`ssp.`→`subsp.`、`T. dicoccoides`→`T. turgidum subsp. dicoccoides`、`Triticosecale`→`x Triticosecale`、`Functional` 类无关）。
3. **学名只用 NCBI 学名（不含英文常用名）** 作为 `species_primary`；英文常用名放后端常量映射（前端显示用），与 CONTEXT §4 的 `species_primary`（如 `Triticum aestivum`）一致。别名/常用名对照：`Triticum aestivum`=bread wheat；`Hordeum vulgare`=barley；`Triticum turgidum`=rivet wheat；`T. turgidum subsp. durum`=durum wheat；`T. turgidum subsp. dicoccoides`=wild emmer；`T. monococcum`=einkorn；`T. polonicum`=Polish wheat；`Secale cereale`=rye；`x Triticosecale`=triticale；`Agropyron cristatum`=crested wheatgrass；`Hordeum vulgare subsp. spontaneum`=wild barley。
4. **长材料描述保留策略**：`gene_species` 存**完整原文**（TEXT，max 668）；`species_primary` 存学名；可选 `species_detail` 存括号/补充说明（若不想加列，前端用 `gene_species` 展开原文即可）；`species_detail` 中位 13 字符、p95 469、max 650（括号感知提取）。
5. 一行多物种/材料段：**不丢失**——`gene_species` 原文保留；如需"验证材料"结构化，二期再拆 `species_all[]`（本期建议不做，避免语义误用）。

### 7.3 归一化后分布（23 个学名）

| # | species_primary（学名） | 行数 | 占比 | 不同原始写法数 | 原始写法示例（截断） |
|---|---|---|---|---|---|
| 1 | Triticum aestivum | 1260 | 88.73% | 229 | Triticum aestivum (bread wheat) |
| 2 | Hordeum vulgare | 79 | 5.56% | 4 | Hordeum vulgare (barley) |
| 3 | Triticum turgidum subsp. durum | 13 | 0.92% | 9 | Triticum turgidum ssp. durum (durum wheat) |
| 4 | Triticum monococcum | 10 | 0.70% | 6 | Triticum monococcum |
| 5 | Aegilops tauschii | 10 | 0.70% | 8 | Aegilops tauschii |
| 6 | Triticum turgidum subsp. dicoccoides | 9 | 0.63% | 7 | Triticum dicoccoides (wild emmer wheat, accession IW39; WEW_v1.0 Zavitan reference); Triti |
| 7 | Triticum urartu | 7 | 0.49% | 3 | Triticum urartu |
| 8 | Triticum turgidum | 4 | 0.28% | 3 | Triticum turgidum (tetraploid wheat cv. Kronos); reference locus from Triticum aestivum |
| 9 | Secale cereale | 4 | 0.28% | 4 | Secale cereale (rye: cv. Imperial, donor of the 1RS segment carrying Sr50/ScRGA1-A in the |
| 10 | Aegilops sharonensis | 3 | 0.21% | 3 | Aegilops sharonensis (accession AS_1644, donor of the 1Ssh segment carrying Sr62); Triticu |
| 11 | Aegilops peregrina | 2 | 0.14% | 1 | Aegilops peregrina |
| 12 | Dasypyrum villosum | 2 | 0.14% | 2 | Dasypyrum villosum |
| 13 | Triticum polonicum | 2 | 0.14% | 2 | Triticum polonicum (Polish wheat) |
| 14 | Triticum boeoticum | 2 | 0.14% | 2 | Triticum boeoticum |
| 15 | x Triticosecale | 2 | 0.14% | 2 | x Triticosecale (triticale) |
| 16 | Aegilops speltoides | 2 | 0.14% | 2 | Aegilops speltoides (Pm12 donor); Triticum aestivum (bread wheat introgression lines WL31/ |
| 17 | Thinopyrum elongatum | 2 | 0.14% | 2 | Thinopyrum elongatum (wild relative used in wheat distant-hybridization breeding, E genome |
| 18 | Thinopyrum ponticum | 2 | 0.14% | 2 | Thinopyrum ponticum (tall wheat grass, 2n = 10x = 70, donor of Sr26 on the 6Ae#1 segment); |
| 19 | Thinopyrum intermedium | 1 | 0.07% | 1 | Thinopyrum intermedium |
| 20 | Hordeum vulgare subsp. spontaneum | 1 | 0.07% | 1 | Hordeum vulgare subsp. spontaneum (wild barley) |
| 21 | Agropyron cristatum | 1 | 0.07% | 1 | Agropyron cristatum (2PL donor); Triticum aestivum (2PT5 translocation line and Fielder tr |
| 22 | Triticum timopheevii | 1 | 0.07% | 1 | Triticum timopheevii (tetraploid AAGG species, chromosome 2G donor of Pm6); Triticum aesti |
| 23 | Aegilops umbellulata | 1 | 0.07% | 1 | Aegilops umbellulata (accession TA1851, donor of the 6U segment carrying Lr9); Aegilops tr |

> 说明：`Triticum aestivum` 的 229 种原始写法里绝大多数是 `(bread wheat: …)` 或 `(bread wheat, cv. …)` 变体，归一到学名后 88.73%；大麦 5.56%；其余 21 个种合计 5.7%。归一化后物种数比作者 `物种改写明细` 的 14 个多 9 个（`Secale cereale`、`Thinopyrum elongatum/ponticum`、`Aegilops sharonensis/speltoides/umbellulata`、`Agropyron cristatum`、`T. turgidum subsp. dicoccoides`、`Triticum timopheevii`），来自后续新增行，合理。

### 7.4 一行多物种段分布

| 一行提到的物种/材料段数 | 行数 |
|---|---|
| 1 | 1157 |
| 2 | 181 |
| 3 | 58 |
| 4 | 24 |

---

## 8. chrom_pos 解析

### 8.1 格式实测

- 带 `chr` 前缀 + `:start-endMb` 完整坐标：**1418** 行
- 无 `chr` 前缀（`AetTA1675 2D:2.33-2.45Mb`、`SYMattis 4A:608.681-608.682Mb`）：**2** 行（Excel 行 297、711）
- 组装前缀（`chr` 前部分）共 **32** 种，前 6：Refv1.0 1298 / MorexV3 72 / Zavitan.v1.0 6 / Lo7.v1 4 / Morex.v3 3 / CSIAAS 2

### 8.2 染色体标签（38 种）与解析正则

推荐正则（`chromosome` 派生列；先按完整格式、再 fallback 无 `chr` 行）：

```python
CHROM_FULL = re.compile(
    r"^(?P<assembly>.+?)\s*chr\s*(?P<chrom>[0-9A-Za-z.]+)\s*:\s*"
    r"(?P<start>\d+(?:\.\d+)?)\s*-\s*(?P<end>\d+(?:\.\d+)?)\s*(?P<unit>Mb|Mbp)?$"
)
CHROM_FALLBACK = re.compile(r"\b(?P<chrom>[0-9][A-Z])\s*:")   # 只用于无 chr 的 2 行
```
→ 实测 `chromosome` 提取成功率 **1420/1420**。

38 个标签及行数：

| 染色体标签 | 行数 |
|---|---|
| 2B | 96 |
| 2A | 90 |
| 7A | 78 |
| 7D | 75 |
| 2D | 75 |
| 5B | 70 |
| 3B | 69 |
| 5A | 68 |
| 4D | 64 |
| 1B | 62 |
| 3A | 61 |
| 7B | 60 |
| 1D | 58 |
| 4B | 58 |
| 3D | 57 |
| 4A | 57 |
| 5D | 56 |
| 1A | 55 |
| 6A | 44 |
| 6B | 38 |
| 6D | 34 |
| 3H | 16 |
| 2H | 15 |
| 7H | 15 |
| 1H | 13 |
| 4H | 10 |
| 5H | 8 |
| 1R | 4 |
| 6H | 3 |
| 7E | 2 |
| 1S | 2 |
| 2V | 1 |
| 6R | 1 |
| 6S | 1 |
| 6V | 1 |
| 54 | 1 |
| 51 | 1 |
| 6U | 1 |

**要点**：
- 21 个小麦（1A–7D）+ 7 个大麦（1H–7H）+ 8 个外来种（1R,7E,1S,2V,6R,6S,6V,6U）+ 2 个特殊（`54`、`51`，仅 `Thinopyrum ponticum` 2 行，`T.ponticum.v1` 组装）。CONTEXT 说"37 种"应更正为 **38 种**（详见 §16.2）。
- `chr54`/`chr51` 是原文写法（非解析错误），对应 `MN531843.1`/`MN531844.1` 两行；**by-chromosome API 需原样接受**，不要映射成 5E/5J（含义待作者确认，§15-Q6）。
- `assembly` 前缀 32 种；新数据小麦坐标前缀统一 `Refv1.0`（1298 行，占 91.4%）——见 §8.4 的版本一致性问题。
- by-chromosome 端点建议：路径参数先 `strip().upper()`、去掉可选 `chr` 前缀，然后 `WHERE chromosome = %s`（新增列，可加索引）；**不要**再用 `chrom_pos LIKE '<x>%'`（新数据带组装前缀，旧逻辑会全部命中失败！这是必须改后端的点）。

### 8.3 按物种分组的染色体集合

| species_primary | 行数 | 染色体标签集合 |
|---|---|---|
| Aegilops peregrina | 2 | 2B, 2D |
| Aegilops sharonensis | 3 | 1S, 6S |
| Aegilops speltoides | 2 | 6B, 7A |
| Aegilops tauschii | 10 | 1D, 2D, 3D, 4D, 5D, 6D, 7D |
| Aegilops umbellulata | 1 | 6U |
| Agropyron cristatum | 1 | 2A |
| Dasypyrum villosum | 2 | 3B, 6V |
| Hordeum vulgare | 79 | 1H, 2H, 3H, 4H, 5H, 6H, 7H |
| Hordeum vulgare subsp. spontaneum | 1 | 3H |
| Secale cereale | 4 | 1R, 6R |
| Thinopyrum elongatum | 2 | 7E |
| Thinopyrum intermedium | 1 | 2V |
| Thinopyrum ponticum | 2 | 51, 54 |
| Triticum aestivum | 1260 | 1A, 1B, 1D, 1R, 2A, 2B, 2D, 3A, 3B, 3D, 4A, 4B, 4D, 5A, 5B, 5D, 6A, 6B, 6D, 7A, 7B, 7D |
| Triticum boeoticum | 2 | 4D, 7A |
| Triticum monococcum | 10 | 1A, 2A, 2B, 2D, 3A, 5A |
| Triticum polonicum | 2 | 7A, 7B |
| Triticum timopheevii | 1 | 2B |
| Triticum turgidum | 4 | 1A, 1B, 4B, 6B |
| Triticum turgidum subsp. dicoccoides | 9 | 2B, 3B, 6B, 7A |
| Triticum turgidum subsp. durum | 13 | 2A, 2B, 3A, 3B, 4A, 4B, 5A, 5B, 6A, 6D |
| Triticum urartu | 7 | 2A, 3A, 5A, 6A, 7B |
| x Triticosecale | 2 | 2B, 6B |

### 8.4 ⚠️ 组装/注释版本一致性问题（需作者确认）

- 新数据 `reference_genome_id` 为 v03（`TraesCS…03G…`，1293 行 = IWGSC RefSeq **v2.1** 注释），但 `chrom_pos` 的小麦坐标前缀是 **`Refv1.0`**（1298 行 = IWGSC RefSeq **v1.0** 坐标）。**同一条记录的基因 ID（v2.1）与坐标（v1.0）不同源**。
- 影响：`chrom_pos` 只用于展示/按染色体过滤时问题不大；但若将来做区间查询、与 JBrowse v1.0 轨道联动、或做基因 ID→坐标校验，就会出错。
- 建议：Lead/作者明确「chrom_pos 坐标基于哪个组装」；若确为 v1.0，则详情页应显示 `IWGSC RefSeq v1.0` 而非 v2.1，或由作者在下一版统一为 v2.1 坐标。**导入层先原样入库 + 解析出 `assembly`/`chromosome`，不擅自换算。**

---

## 9. 受控词表与自由文本边界

### 9.1 边界总览

| 字段 | 性质 | 取值/规模 | 导入策略 |
|---|---|---|---|
| `research_strategy` | **受控 3 值** | 见 §9.2 | 枚举校验后原样入库 |
| `functional_category` | **受控 5 值** | 见 §9.2 | 枚举校验后原样入库 |
| `cloning_method` | **受控 5 基础值 + 6 行组合值（8 字符串）** | 见 §9.2 | 归一到 5 类 + 可选多标签派生 |
| `protein_family` | 半结构自由文本（1176 值） | max 2657 字符 | 原文入库 + 派生 label（§9.5） |
| `validation_method` | 半结构（895 个整串 / 8185 个 `; ` 分句） | 早标签体、后叙述体 | 原文入库 + 派生 `validation_methods[]`（§9.3） |
| `gene_phenotype` | 半结构（1070 值 / 2779 个括号感知分句） | 早标签体、后叙述体 | 原文入库 + 派生 `phenotype_brief`（团队已定，首段）+ 可选 `phenotype_tags`（§9.4） |
| `gene_id` / `gene_name` / `ref_genome_id` / `chrom_pos` / `doi` / `title` | 结构化/半结构 | 见 §5/§6 | 校验后原样入库 |
| 长文本（`key_result`/`function_description`/`cloning_method_description`） | 自由文本 | 40–464 词 / max 2236 / max 1757 | 原样入库 |

### 9.2 research_strategy / functional_category / cloning_method

| research_strategy（3 值） | 行数 |
|---|---|
| Reverse genetics | 1061 |
| Forward genetics | 281 |
| Not reported | 78 |

| functional_category（5 值） | 行数 |
|---|---|
| Biotic & Abiotic Stress | 776 |
| Quality & Yield | 202 |
| Morphology & Domestication | 154 |
| Physiology & Metabolic Processes | 146 |
| Reproduction & Phenology | 142 |

| cloning_method（8 值） | 行数 |
|---|---|
| Homology-based cloning | 569 |
| Not reported | 304 |
| Transcriptome-based cloning | 250 |
| Map-based cloning | 184 |
| Functional | 106 |
| Homology-based cloning; Functional cloning | 3 |
| Homology-based cloning; Transcriptome-based cloning | 3 |
| Functional cloning | 1 |

**cloning_method 归一建议**：`Functional`（106）→ `Functional cloning`；6 行组合值（`Homology-based cloning; Functional cloning` ×3、`Homology-based cloning; Transcriptome-based cloning` ×3）拆成 2 个标签（若只保留单值列，则取第一个，另派生 `cloning_method_tags`）；归一后 5 类：Homology-based cloning 575、Not reported 304、Transcriptome-based cloning 253、Map-based cloning 184、Functional cloning 110（合计 1426 = 1420 + 6 组合拆分多算）。

### 9.3 validation_method → validation_methods[]（派生）

- 原始：1363 行含 `; `，895 个不同整串；`; ` 分句 **8185** 个；长度中位 32 字符但长尾到 636（叙述体行）。
- 拆分/清洗规则：括号感知按 `; ` 切 → 去掉 `(...)` 子句 → 去首尾标点 → **保留 ≤80 字符、不以 `.?!` 结尾、非 `Not reported/Not determined`** 的分句 → 得到 **6095 个方法 token / 1087 个唯一值**；48 行 0 token（原文只有 Not reported 之类）。
- 别名归一到 **~30 个受控方法标签**（频次 Top 30，含归一后名称）：

| # | 验证方法标签 | 行数 |
|---|---|---|
| 1 | Expression analysis | 819 |
| 2 | Phenotyping | 648 |
| 3 | Overexpression | 396 |
| 4 | Subcellular localization | 358 |
| 5 | Transgenic transformation | 329 |
| 6 | VIGS | 220 |
| 7 | Heterologous expression | 199 |
| 8 | Interaction assays | 181 |
| 9 | Promoter/transactivation assays | 123 |
| 10 | RNAi | 99 |
| 11 | Mutant sequencing | 93 |
| 12 | CRISPR/Cas9 | 92 |
| 13 | Haplotype/association analysis | 79 |
| 14 | Biochemical activity assays | 74 |
| 15 | Yeast two-hybrid | 50 |
| 16 | Y2H | 45 |
| 17 | Transgenic complementation | 37 |
| 18 | Transient expression | 34 |
| 19 | EMS mutants | 32 |
| 20 | Co-IP | 32 |
| 21 | Yeast one-hybrid | 32 |
| 22 | BiFC | 31 |
| 23 | Marker development | 27 |
| 24 | Virus-induced gene silencing | 21 |
| 25 | EMSA | 20 |
| 26 | BSMV-VIGS | 20 |
| 27 | Bimolecular fluorescence complementation | 17 |
| 28 | CRISPR/Cas9 knock-out | 15 |
| 29 | Luciferase complementation imaging | 15 |
| 30 | Metabolite/hormone profiling | 13 |

- 别名映射（同义合并，括号是原文计数）：`Virus-induced gene silencing`/`BSMV-VIGS`/`VIGS`→`VIGS`；`Yeast two-hybrid`/`Y2H`→`Y2H`；`Yeast one-hybrid`/`Y1H`→`Y1H`；`Expression analysis (qRT-PCR)`/`(qRT-PCR/RNA-seq)`→`Expression analysis`；`CRISPR/Cas9 knock-out`/`CRISPR-Cas9`→`CRISPR/Cas9`；`Interaction assays (Y2H/BiFC/Co-IP)`/`(Y2H/BiFC)`→`Interaction assays`；`Virus-induced gene silencing (VIGS)`→`VIGS`。**展示用 chips 用归一标签，搜索仍用原始列。**

### 9.4 gene_phenotype → phenotype_brief（团队已定派生列）/ phenotype_tags（可选）

- **`phenotype_brief`（团队已定，前端列表/摘要用）**：括号感知按 `;` 切 → 取第一段 → 在第一个 `:` 处截断 → 压空白/去首尾标点 → 得到「性状简述」。实测：首段全文 max 803，**在 `:` 处截断后 max = 666**；若首段无 `:` 且 >666，按词边界截到 666（与 Lead 约定一致）。该列可直接用于结果卡片与 Stats 的粗粒度表型聚合。
- 原始 1070 个不同值；括号感知 `;` 分句 2779 个（中位 149 字符，说明**大部分不是短标签**）。
- 提取规则（可复现）：括号感知按 `;` 切 → 每段取 `:` 之前部分 → 去掉括号内容 → 压空白/去首尾标点 → **保留 1–80 字符、不以 `.?!` 结尾、非 `Not determined/Not reported`** → 首字母大写。
- 结果：**1448 个标签 / 689 唯一 / 255 行 0 标签**；每行最多 7 个、中位 1 个。Top 30：

| # | 标签（清洗+首字母大写） | 行数 |
|---|---|---|
| 1 | Drought tolerance | 70 |
| 2 | Stripe rust resistance | 65 |
| 3 | Powdery mildew resistance | 51 |
| 4 | Salt tolerance | 45 |
| 5 | Leaf rust resistance | 17 |
| 6 | Stripe rust susceptibility | 15 |
| 7 | Flowering time | 14 |
| 8 | Grain weight | 14 |
| 9 | Stem rust resistance | 13 |
| 10 | Heat tolerance | 12 |
| 11 | Salinity tolerance | 11 |
| 12 | Drought and salt tolerance | 10 |
| 13 | Grain yield | 10 |
| 14 | Male sterility | 9 |
| 15 | Plant architecture | 9 |
| 16 | Male fertility | 9 |
| 17 | Cadmium tolerance | 9 |
| 18 | Sharp eyespot resistance | 9 |
| 19 | Powdery mildew susceptibility | 8 |
| 20 | Spike architecture | 8 |
| 21 | Tiller number | 8 |
| 22 | Seedling growth | 7 |
| 23 | Fusarium head blight resistance | 7 |
| 24 | Plant height | 7 |
| 25 | Seed dormancy | 7 |
| 26 | G3P accumulation | 6 |
| 27 | Negative regulation of stripe rust resistance | 6 |
| 28 | Heading date | 6 |
| 29 | Thermotolerance | 6 |
| 30 | Grain size | 6 |

- 原始未过滤分句 Top 12（说明为何必须过滤——叙述体行会把整段机制描述当一个"标签"）：

| 原始分句（未过滤） | 出现次数 |
|---|---|
| Not determined | 65 |
| Drought tolerance | 43 |
| Salt tolerance | 35 |
| Stripe rust resistance | 31 |
| Powdery mildew resistance | 18 |
| drought tolerance | 11 |
| Heat tolerance | 9 |
| Flowering time | 9 |
| Male sterility | 8 |
| Sharp eyespot resistance | 8 |
| Plant architecture | 7 |
| Grain weight | 7 |

- **结论**：该字段从 v2055 起是"性状标签 + 机制说明"混合体；**列表/摘要用 `phenotype_brief`（团队已定）**，`phenotype_tags` 仅作可选展示 chips / Stats Top 榜（若 Stats 需要更准的 Top 榜，用本规则统计并注明"粗粒度标签"，或二期人工映射 Top 50）。

### 9.5 protein_family → protein_family_label（可选派生）

- 1176 个不同值；22–2657 字符，中位 366；1025 行含 `;`、905 行含 ` - `、1362 行含 `(`。典型结构：`<家族名 (缩写)> [ - 功能/结构描述]`，如 `HSP90 (heat shock protein 90) family - ATP-dependent molecular chaperone…`。
- 规则：取第一段（`;` 前）→ 截断到 ` - ` 前 → 压空格，得到 label（≤120 字符）；1275/1420 行可提取非空 label，其余保留 NULL（前端直接显示原文前 80 字符）。Top label 示例：`NAC transcription factor family`、`R2R3-MYB transcription factor family`、`Ethylene response factor (ERF/AP2) transcription factor family`、`HSP90 … family`、`NRT1/PTR (POT) family`。
- **不建议**把 protein_family 变成严格受控词表（作者按论文原文写、信息量大，强控会丢信息）。

---

## 10. 与现库 520 行对比 与 clone_id 稳定映射

### 10.1 现库基线（证据快照 + Lead 核实）

| 指标 | 值 |
|---|---|
| 现库行数 | 520 |
| clone_id 范围 | 1–526（缺 6 个：3,7,8,13,15,25；缺号不复用） |
| clone_id / gene_id 唯一 | 520 / 520 |
| gene_name 唯一 | 463（57 行为同源拷贝同名） |
| 旧 gene_id 格式 | **TraesCS 类 480 行 = v02 `…02G…` 461 + v01 `…01G…` 10（Lead 核实；本地正则另计入 ~9 行大小写/拼接变体）+ 1 行 v03**；非 TraesCS 40 行（INSDC、HORVU、`MT783929/MT783930` 这类 `/`、`,` 拼接 ID 等；含 **2 行 gene_id/gene_name 字段错位**：clone_id 28/29） |
| 新数据 gene_id | 1420 行 / 1395 唯一（25 行重复）；v03 `TraesCS…03G…` 1158、INSDC 169、HORVU 56、其他 37 |
| 新数据 reference_genome_id | v03 1293、HORVU 77、其他 26、INSDC 23、1 个组装区间 |
| 同一 DOI 出现在多行 | 938 行含至少 1 个「在别处也出现」的 DOI token；`doi` 单元格完全重复的行 600 |
| **clone_id 继承（Lead 实测）** | **321 / 520 = 61.73%**（经 `Genehub_DB.GenePageIWGSCv1_table` 做 v01/v02→v03 映射） |
| **成为孤儿（不继承）的旧 clone_id** | **199（38.27%）**，永不复用 |
| 新数据需新 clone_id 的行 | **1099** |
| 新 clone_id 区间 / AUTO_INCREMENT | 527–1625 / **1626** |
| 全量替换后总行数 | 1420 |
| 若软保留孤儿行（is_active=0） | 1619 行（199 + 1420） |
| 仅名称/染色体自动规则（不含 genehub，基线） | 272 / 520 = 52.31%（用于交叉验证与无生产库时的兜底） |

### 10.2 匹配策略与实测覆盖率（4 层自动规则 + genehub 映射 + 人工兜底）

| 匹配层级 | 规则 | 本层命中旧行数 | 累计可稳定保留 clone_id |
|---|---|---|---|
| P1 | 旧 gene_id 与新 gene_id 完全一致（优先同名） | 10 | 10 (1.92%) |
| P2 | gene_name 完全一致，且新侧候选唯一、旧侧同名唯一 + 染色体兼容 | 211 | 221 (42.50%) |
| P3 | gene_name 归一化（去空格/大小写/别名斜杠切分/去同源后缀）后唯一 + 染色体兼容 | 12 | 233 (44.81%) |
| P4 | 归一化名 + 染色体号消歧（解决「旧 1 行 → 新 3 个同源拷贝」） | 39 | **272 (52.31%)** |
| P5 | **v01/v02→v03 映射**（`Genehub_DB.GenePageIWGSCv1_table` 的 GeneIDv1/GeneIDv2→GeneIDv3）后再匹配新行 `ref_genome_id`/`gene_id` | **+49** | **321 (61.73%)**（Lead 实测） |
| P6 | 人工映射表（199 行孤儿中"改名但同一基因"的，如旧 `TaVRN1-5A`→新 `TaVRN-A1`）/ 直接淘汰 | — | 100% |

- 规则细节：**P1** 旧 `gene_id` 与新 `gene_id` 完全一致（命中 10 行；同一 ID 优先同名）；**P2** `gene_name` 完全一致 + 新侧候选唯一 + 旧侧同名唯一 + 染色体兼容；**P3** 归一化名（小写/去空格/`/`与`;`切别名/去同源后缀 `-A/-B/-D/-A1/-2A`）唯一 + 染色体兼容；**P4** 归一化名 + 染色体号唯一（解决"旧 1 行 → 新 3 个同源拷贝"）。
- 自动规则同时要求**染色体兼容**（旧 `chrom_pos` 与新 `chrom_pos` 都能解析出染色体时必须相同），已剔除 8 个"同名但染色体不同"的疑似错配（如旧 `TaZIP4-A1` 3A 对到新 `TaZIP4-B2` 5B、旧 `VRN-B2/VRN2` 对到新 `VRN-B3/FT-B1`），这 8 行转人工。
- **无 genehub 基线**剩余 248 行分四类：`no_candidate` 200（旧名在新数据中不存在，含改名与旧数据质量问题）、`candidate_used` 40（旧多行同名 ↔ 新行已被占用，如 `Glu-D3` 旧 8 行、`TaSBEIIa` 旧 3 行）、`single_candidate_but_conflict` 7、`multi_candidate` 1；其中 **230 行是 v02 ID**。
- genehub 只把 272 再提高 +49（→321）：根因**不是映射脚本**，而是新清单是 curated 子集——旧库 199 行对应的基因/等位未被本期 1420 条收录或已改名/合并，v03 基因在清单里不存在。因此 61.7% 是本期数据的现实上限，剩余靠人工映射（作者只对"明确同一基因"的行给出 old clone_id → new 行映射）。
- 旧库 40 行非 TraesCS ID（含 `/`、`,` 拼接 ID、`TRIAE_CS42…TGACv1`、MIPS 等）无法用 genehub 三列映射，按 P2/P3/P4 名称规则尝试，未命中转人工。

### 10.3 P5 结论（Lead 已实测）与可复现要求

- **结论：clone_id 可继承 321/520 = 61.73%，199 个旧 clone_id 成为孤儿（不复用）。**
- 生产 `Genehub_DB.GenePageIWGSCv1_table` 有 `GeneIDv1`（01G）/`GeneIDv2`（02G）/`GeneIDv3`（03G）三列（`app/api/routers/gene.py`、`app/api/routers/expression.py` 已在用）。建议 Lead 在服务器执行只读 SQL 并导出 CSV：

```sql
-- 旧库 471 个 v01/v02 ID → v03（v02 用 GeneIDv2，v01 用 GeneIDv1）
SELECT GeneIDv2 AS old_id, GeneIDv3 AS new_id FROM Genehub_DB.GenePageIWGSCv1_table
WHERE GeneIDv2 IN (<461 个旧 v02 gene_id>);
SELECT GeneIDv1 AS old_id, GeneIDv3 AS new_id FROM Genehub_DB.GenePageIWGSCv1_table
WHERE GeneIDv1 IN (<10 个旧 v01 gene_id>);
```
- 建议产出 `clone_id_mapping_v2055.csv` 字段：`old_clone_id, old_gene_id, old_gene_name, mapped_v03, matched_new_gene_id, matched_new_ref_genome_id, status(inherit|orphan|manual), tier(P1–P6), reviewer`。该表是 importer 的唯一 clone_id 输入，也是永久存档（保证孤儿 ID 不复用、可追溯）。
- 并请用该映射对 P2/P3/P4 的 272 行做交叉验证（mapped_v03 应等于新行 `ref_genome_id`；不等则降级人工）。
- 提示：`GenePageIWGSCv1_table` 是 IWGSC 三版本对照；旧库中 `TRIAE_CS42…TGACv1`/MIPS 类 ID 需改用 `Convert_gene_id` 库表（`IWGSCv1_result`/`TGACv1_result`/`MIPS_result`，见 `/api/id-conversion`），预计收益很小（此类旧行 <15）。

### 10.4 clone_id 分配规则（可直接实现）

1. **旧行稳定**：321 行继承 `clone_id` 原值（1–526，含当前缺号 3/7/8/13/15/25，缺号**也不复用**）。
2. **新行插入（321 方案）**：按 Excel 行序，从 527 起连续显式赋值：插入 **1099** 行 → clone_id **527–1625**；事务后 `ALTER TABLE cloned_gene_tbl AUTO_INCREMENT = 1626;`。
3. **兜底方案（仅自动规则 272 行，不接 genehub）**：插入 1148 行 → clone_id **527–1674**，`AUTO_INCREMENT = 1675`。两方案都**显式写入 clone_id**（禁止依赖自增隐式分配，保证幂等/可重跑）。
4. **199 个孤儿旧 clone_id 两种策略（Lead 决策）**：
   - **A（推荐，全量替换）**：删除 199 行孤儿；主表最终 **1420 行**；导入前 `CREATE TABLE cloned_gene_tbl_backup_v2055 …` 全量备份；`clone_id_mapping_v2055.csv` 永久存档 → ID 不复用、可追溯。
   - **B（软保留）**：加 `is_active tinyint(1) default 1`，孤儿行置 0；主表 **1619 行**；所有 `/known/*` API 默认 `WHERE is_active=1`（需改 4 个只读端点 + CGI 页面，成本高，不推荐本期做）。
5. **不要**用 `AUTO_INCREMENT` 自增隐式分配新 ID：显式写入 clone_id 才能保证重复执行同批导入不换 ID。
6. 缺号 **3/7/8/13/15/25** 保持空缺（严禁填补）；未来 CGI 提交页新增行会从 AUTO_INCREMENT 继续，不撞号。


### 10.5 同 ID/同名但文献不同——本期无法从证据判断，需 Lead 补查

- 证据快照只有 6 个摘要字段（clone_id/gene_id/gene_name/chrom_pos/phenotype/species），**没有 DOI/title**，因此"同 gene_id/同名但文献不同"的冲突无法核验。
- 建议 Lead 对 **P1 的 10 行**（ID 完全一致）用生产 `GET /api/genes/known/{clone_id}` 取旧 DOI/title，再与 Excel 对应行比对，输出冲突清单；这 10 行是唯一"ID 可以直接对齐"的样本，冲突检测成本最低。

---

## 11. 列类型建议、行大小与字符集

### 11.1 现库类型 vs 新数据实测（会截断的行数）

| 目标现库列 | 现类型 | 上限(字符) | 新数据 max 字符 | 超限行数 | 处理建议 |
|---|---|---|---|---|---|
| gene_id | varchar(300) | 300 | 28 | 0 | 保留 |
| gene_name | varchar(500) | 500 | 43 | 0 | 保留 |
| chrom_pos | varchar(500) | 500 | 41 | 0 | 保留 |
| gene_species | varchar(500) | 500 | 668 | 60 | → TEXT（必须） |
| gene_phenotype | varchar(1000) | 1000 | 1677 | 99 | → TEXT（必须） |
| key_result | varchar(15000) | 15000 | 3051 | 0 | 保留 |
| cloning_method | varchar(255) | 255 | 51 | 0 | 保留 |
| paper_title | text | — | 473 | 0 | 保留 |
| paper_doi | text | — | 82 | 0 | 保留 |
| function_description | text | — | 2236 | 0 | 保留 |
| cloning_method_description | text | — | 1757 | 0 | 保留 |
| publication_year | year(4) | 单值 4 位年 | max 单元格 16（`2008; 2024`） | 115 行多位 | 保留首/最小年 + 新增 publication_years varchar(64) |

### 11.2 完整 schema 变更建议（DDL 草案）

```sql
-- 需 MySQL root（生产凭据见 CONTEXT §2；本阶段不执行）
-- 0) 备份
CREATE TABLE cloned_gene_tbl_backup_v2055 LIKE cloned_gene_tbl;
INSERT INTO cloned_gene_tbl_backup_v2055 SELECT * FROM cloned_gene_tbl;

-- 1) 改造会截断的旧列（varchar -> TEXT；释放行内 6000 字节）
ALTER TABLE cloned_gene_tbl
  MODIFY gene_phenotype TEXT,        -- 99 行 >1000
  MODIFY gene_species   TEXT;        -- 60 行 >500

-- 2) 新增列（顺序按展示/分组习惯）
ALTER TABLE cloned_gene_tbl
  ADD COLUMN reference_genome_id varchar(128) NULL AFTER gene_id,
  ADD COLUMN chromosome         varchar(16)  NULL AFTER chrom_pos,
  ADD COLUMN species_primary    varchar(128) NULL AFTER gene_species,
  ADD COLUMN protein_family     TEXT         NULL AFTER function_description,
  ADD COLUMN protein_family_label varchar(128) NULL AFTER protein_family,
  ADD COLUMN validation_method  TEXT         NULL AFTER cloning_method_description,
  ADD COLUMN validation_methods TEXT         NULL AFTER validation_method,
  ADD COLUMN phenotype_brief    TEXT         NULL AFTER gene_phenotype,
  ADD COLUMN phenotype_tags     TEXT         NULL,   -- 可选
  ADD COLUMN research_strategy  varchar(40)  NULL,
  ADD COLUMN functional_category varchar(64) NULL,
  ADD COLUMN publication_years  varchar(64)  NULL AFTER publication_year,
  ADD COLUMN data_version       varchar(32)  NULL,
  ADD COLUMN updated_at         timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

-- 3) 索引（先确认 row_format；utf8mb3 下 gene_id varchar(300)=900B，DYNAMIC 可全列，COMPACT 需前缀）
ALTER TABLE cloned_gene_tbl
  ADD INDEX idx_gene_id (gene_id(100)),
  ADD INDEX idx_gene_name (gene_name(100)),
  ADD INDEX idx_chromosome (chromosome),
  ADD INDEX idx_species_primary (species_primary);
-- 4) 导入后
ALTER TABLE cloned_gene_tbl AUTO_INCREMENT = 1626;  -- 321 方案；若仅自动规则 272 行则 1675
```

> 说明：`author/author_mail NOT NULL` 保持不动（占位值见 §3 第 18–19 行）；`publication_year year(4)` 保持（兼容 CGI）；`key_result varchar(15000)` 保持（实测 max 3051 字符；若改 utf8mb4 需同步改 TEXT，见 §11.3）。

### 11.3 utf8mb3 vs utf8mb4（实测结论）

- 全表 17 列扫描：**BMP 外字符（4 字节）0 个**；非 ASCII 字符仅 **14 种**：`α`(463) `β`(79) `°`(31) `“`(7) `”`(7) `Δ`(6) `–`(4) `γ`(3) `—`(2) `≤`(1) `µ`(1) `₂`(1) `μ`(1) `‐`(1) —— 全部 ≤3 字节，**utf8mb3（MySQL 的 `utf8`）足以存储**，不需要为本次数据升级 utf8mb4。
- **但**：现表 varchar 总字符 18,355 → utf8mb3 占 55,065 B；若 `ALTER … CONVERT TO CHARACTER SET utf8mb4`，行内占用变 73,420 B > 65,535 B **会失败**。若将来要 utf8mb4：必须先把 `gene_phenotype/gene_species`（以及 `key_result` 之外的 `paper_title/paper_doi/function_description/cloning_method_description` if varchar）改 TEXT。**结论：本期维持 utf8mb3；如需 utf8mb4，按 §11.2 第 1 步先改 TEXT 再迁移。**
- 连接字符集 `DB_CHARSET=utf8mb4` 读 utf8mb3 表没问题（数据本身无 4 字节字符）。

---

### 11.4 ⚠️ `#` 字符 vs `normalize_text()`（后端阻塞，Lead 已记录）

- 实测 **26 行含 `#`**（Lead 核实 23 行；按字段：species 3、gene_phenotype 13、key_result 14、function_description 10、protein_family 7、cloning_method_description 23、validation_method 19，多列重叠）。这些 `#` 是**语义字符**：`7S#1`、`6Ae#1`、`6Ae#3`、`hc#28`、`QTgw.cau-7D`、`#1/#2` 等（品种/染色体片段/突变体系编号）。
- 现 `app/services/legacy_parsers.py::normalize_text()`：先 `####`→`'`，再把所有 `#`→`'`；`gene.py` 的 search/all/by-chromosome/detail 对 `gene_name/chrom_pos/gene_phenotype/gene_species/function_description/cloning_method*/key_result` 都调用它 → **新数据经 API 会显示成 `7S'1` 这类错误**。
- 方案：
  - **A（推荐）**：按行/按批次分支——`data_version='v2055'` 的行用新 `safe_normalize()`（只 strip/压空白，不替换 `#`），旧行（data_version 为空）继续 `normalize_text()`；CGI 页面读同表，仅影响展示不影响存储。
  - B 全局改 `normalize_text()` 只处理 `####`、不动单 `#`：**风险**是旧 520 行里可能有旧数据把 `#` 当撇号（CGI 时代转义），需 Lead 抽样确认后再改。
  - C 入库前把 `#` 换成全角 `＃`/`No.`：**不推荐**（丢原文、与 Crossref 题名不一致）。
- 冒烟用例：`species` 行 1133/1147/1151（`7S#1`/`6Ae#1`/`6Ae#3`）、`validation_method` 行 996/1007（`hc#28`/`#1、#2`）应原样显示。

---

## 12. 导入前校验规则清单（每列 1–3 条可编程断言）

> 全局断言（先跑）：
> G1 `df.shape == (1420,17)` 且 17 列 strip 后 100% 非空；
> G2 无 `\t`/`\r`/`\n`/控制字符；无 4 字节字符；
> G3 **真实 HTML 标签 0 行**（`</?(i|b|sub|sup|br|p|span|em|strong)[^>]*>` 严格正则计 0）；`<`/`>` 允许存在（58 行数学比较符号），**不得 strip**，只在渲染层 HTML 转义；
> G4 17 列全字段 hash 无重复（幂等键唯一）；
> G5 输入文件 sha256 与冻结值一致（`e0e971c1…`）；
> G6 **`#` 原样保留**：26 行含 `#`（语义字符：`7S#1`/`6Ae#1`/`hc#28` 等），入库前后断言 `field.count('#')` 不变，禁止经 `normalize_text()`（它把 `#`→`'`）。

| 列 | 断言（1–3 条） | 失败处置 |
|---|---|---|
| gene_id | ① `^[A-Za-z0-9_.:-]{1,300}$`（1420/1420 通过）② 长度 ≤300 ③ 无首尾空白 | 硬失败（阻断） |
| 参考基因组ID | ① 非空 ② 长度 ≤128 ③ 格式属 {`TraesCS…0[123]G…`, `HORVU…`, INSDC `[A-Z]{1,3}_?\d{5,}(\.\d+)?`, 组装区间名} 之一（白名单+警告） | 格式警告不阻断 |
| gene_name | ① 非空、trim 后无首尾空白 ② 长度 ≤500 ③ 内部允许空格/`;`/`/`（不校验字符合集） | 硬失败 |
| species（原文） | ① 非空 ② 长度 ≤TEXT 上限（65835） ③ 首词须命中物种属名白名单（否则 warning 并人工复核） | 警告 |
| species_primary（派生） | ① 非空 ② ∈ 23 个学名枚举 ③ 长度 ≤128 | 硬失败（派生 bug） |
| chrom_pos | ① 非空 ② 正则解析成功率 100%（1418 full + 2 fallback） ③ `chromosome` ∈ 38 个标签集合 | 硬失败 |
| chromosome（派生） | ① 非空 ② `^[0-9][A-Z](\d)?$` 或特殊 `51/54` ③ 长度 ≤16 | 硬失败 |
| gene_phenotype | ① 非空 ② 字符长度 ≤65,535（TEXT） ③ 若派生 brief/tags 失败不阻断原始入库 | 警告 |
| phenotype_brief（派生，团队已定） | ① 非空（1420/1420 可提取） ② 长度 ≤666 ③ 等于规则结果（`;` 括号感知首段 + 第一个 `:` 截断 + 无冒号超长按词边界截断） | 硬失败（派生 bug） |
| phenotype_tags（可选派生） | ① 合法 JSON array ② 元素 ≤80 字符 ③ 不允许空串 | 警告 |
| key_result | ① 词数 40–500（实测 40–464） ② 非空 ③ 长度 ≤15000 字符（现列上限） | 警告/硬失败 |
| function_description | ① 非空 ② 长度 ≤65535 ③ 无 `###`（新数据应为单段；若出现则需确认） | 警告 |
| protein_family | ① 非空 ② 长度 ≤65535 ③ 若派生 label：非空率 ≥85%（实测可提取 1275/1420） | 警告 |
| cloning_method | ① ∈ 归一后 5 类（先应用归一映射） ② 组合值 6 行允许但需拆 | 硬失败 |
| cloning_method_description | ① 非空 ② 长度 ≤65535 | 警告 |
| validation_method | ① 非空 ② 长度 ≤65535 ③ 分句数 ≤50（实测 max ~? 长尾） | 警告 |
| validation_methods（派生） | ① 合法 JSON array ② 元素 ∈ 受控方法词表（未识别元素仅 warning） ③ 元素 ≤80 字符 | 警告 |
| research_strategy | ① ∈ {Reverse genetics, Forward genetics, Not reported} ② 非空 | 硬失败 |
| functional_category | ① ∈ 5 个枚举值 ② 非空 | 硬失败 |
| title | ① 非空 ② 长度 ≤65,535（TEXT） ③ `; ` 切分数与 DOI 数一致或命中 16 行容许清单 | 容许清单外硬失败 |
| doi | ① 每个 token `^10\.\d{4,9}/\S+$`（实测 0 非法） ② 行内无重复 DOI ③ token 数 1–3 | 硬失败 |
| publication_year | ① 每个 token `^(19\|20)\d{2}$` 且 1900–2100（实测 1998–2026） ② token 数 ∈ {1, n_doi} ③ 多值时原文入 `publication_years` | 硬失败 |
| publication_years | ① `^(\d{4})(; \d{4})*$` ② 长度 ≤64 | 硬失败 |
| data_version | ① == `v2055` | 硬失败 |
| author/author_mail | ① NOT NULL 占位非空 ② author_mail 满足 EmailStr ③ 长度 ≤100/200 | 硬失败 |
| clone_id（计划值） | ① 计划 id 全局唯一 ② 不覆盖仍在用的旧 clone_id ③ 新 id 从 527 起连续、不占用退役缺号 | 硬失败 |

**dry-run 报告字段建议**：输入 sha256/行数/列数；每列空值数、min/max 字符、超目标类型上限的行号；16 行多值异常分类明细（REVIEW_MULTIYEAR / REVIEW_MISSING_TITLE / REVIEW_TITLE_SHIFT）；物种归一化未命中清单（应为 0）；chromosome 解析失败行号（应为 0）；controlled vocab 非法值；clone_id 计划表（matched/insert/retired 计数 + 16 个样例）；DDL 语句清单；最终 JSONL sha256；导入后主表行数与 `SELECT COUNT(*)` 校验值。

---

## 13. 稳健序列化与导入流程（含历史 bad-import 教训）

### 13.1 为什么不用 TSV/CSV

- 历史事故：`cloned_gene_bad_import_backup` **1636 行**残骸，`paper_title` 混入整行 TSV、`\r\n`、引号错位（CONTEXT §2）。
- 本数据风险点：字段含双引号（`function_description` 12 行、`protein_family` 10 行、`key_result` 8 行、`cloning_method_description` 3 行、`title` 3 行）、`|`（1 行）、`; `、`###`、UTF-8 希腊字母/破折号；**未来 Excel 编辑可能引入 tab**。TSV 一旦有 tab 就整行错位；CSV 的引号转义在 MySQL `LOAD DATA` 与 Python csv 间很容易不一致。

### 13.2 推荐管线（JSONL + staging + 单事务）

```
xlsx（冻结 sha256）
  → openpyxl read_only 读取（dtype=str, fillna("")）
  → 归一/派生（species_primary/chromosome/phenotype_brief/可选 phenotype_tags/validation_methods/publication_years/clone_id 计划）
  → 校验（§12，失败即停，输出 dry-run 报告）
  → JSONL：每行 {"clone_id":..., "gene_id":..., ...}，utf-8, ensure_ascii=False, 每行独立 json.dumps
  → 计算 JSONL sha256（可复现）
  → INSERT 到 staging 表（CREATE TABLE cloned_gene_staging_v2055 LIKE cloned_gene_tbl）
  → staging 校验（行数=1420、每列非空、clone_id 唯一、抽样 20 行比对源文件）
  → 生产事务：
       BEGIN;
       DELETE FROM cloned_gene_tbl WHERE clone_id NOT IN (<272 个保留 id>);   -- 或按策略 B 置 is_active=0
       INSERT INTO cloned_gene_tbl (...) VALUES ...;                          -- 321 保留行（UPDATE clone_id 不变）+ 1099 新行 INSERT
       -- 若仅自动规则：272 保留 + 1148 新行
       COMMIT;
  → 事后校验：COUNT(*)=1420；clone_id 集合 = 1..526 中 321 个 + 527..1625（兜底方案 272 + 527..1674）；
      API 冒烟：/known/all total=1420、/known/search、/known/{clone_id}、/by-chromosome/3B
  → 备份留存：cloned_gene_tbl_backup_v2055 + JSONL + dry-run 报告 + clone_id 映射 CSV
```

要点：
- **JSONL 不依赖分隔符转义**，双引号/分号/换行都由 JSON 规范处理，是规避历史事故的最稳方案。
- 1420 行规模，Python `executemany` 分批（每批 200）在单事务内完成，秒级；**不要用 `LOAD DATA LOCAL INFILE`**（路径/权限/转义三重坑）。
- 事务期间表锁时间可接受；先在 staging 完成全部校验再动主表。
- **DDL（加列/改类型）与 DML 分开提交**：DDL 先做（root），DML 在事务里做；DDL 前先备份。
- 回滚：`RENAME TABLE cloned_gene_tbl TO cloned_gene_tbl_failed_v2055, cloned_gene_tbl_backup_v2055 TO cloned_gene_tbl;`（注意 FOREIGN KEY 无、可安全换名）。

---

## 14. 其他 sheet 对导入/展示的影响

### 修改记录（1153 行）

| 类别 | 行数 | 含义 |
|---|---|---|
| 清洗 | 464 | 字段级清洗（符号/Markdown 注记） |
| 新增 | 440 | 整行新增（相对旧版本） |
| D6 | 121 | 一行多 DOI 的题名/年份对齐 |
| K | 36 | key_result 按 PubMed 摘要补写 |
| 删除 | 36 | 整行删除 |
| 核查 | 17 | 整行复核修订 |
| K(全文) | 16 | key_result 按全文补写 |
| D1 | 10 | D1 交叉核验（DOI/题名/年份） |
| U | 10 | U1–U10 用户决定落实 |
| D2 | 3 | TaVRN-A1 拆行 |

### 文本清洗明细（338 行）

- 记录的是「哪些行的哪些字段被清洗过」，不保留原值（原值需回溯旧版本 Excel）。
- 涉及字段组合 Top 5：
  - 100 行：`gene_phenotype（入库）、function_description（入库）、蛋白家族（入库）、cloning_method_description（入库）`
  - 44 行：`gene_phenotype（入库）、key_result（入库，≤500 词英文）、function_description（入库）`
  - 40 行：`key_result（入库，≤500 词英文）、function_description（入库）、蛋白家族（入库）、cloning_method_description（入库）`
  - 34 行：`gene_phenotype（入库）、key_result（入库，≤500 词英文）、function_description（入库）、蛋白家族（入库）、cloning_method_description（入库）`
  - 20 行：`蛋白家族（入库）`

### 物种改写明细（1024 行）

- 记录 `原行号 / 新行号 / gene_name / 原写法 → 统一为（NCBI Taxonomy）/ 被移除的补充信息`。
 - `统一为` 共 14 个学名值；881 行有被移除补充信息（中位 11 字符，最长 551 字符——即原 `species` 括号内的材料描述）。
 - 34 行「新行号」为空 = 这些行在后续版本被删除（与 说明 sheet「删除 2 行」不矛盾：该表累计了多轮删除）。
 - 主 sheet 中 1420 行并非全部套用了该改写：仍有 433 行不在改写表覆盖范围（其中 379 行 species 长度 > 60、339 行 > 100）。

### K补写依据（36 行）/ K补写依据(全文)（16 行）

- 36 行按 PubMed 摘要补写（4 个 PMID 覆盖多行），补写后 key_result 词数 63–104（中位 ~90）。
- 16 行按本地全文补写（3 个 PMC XML/TXT + 1 个本地 PDF），词数 81–122。
- 目的：把 key_result 统一到 40–500 词/80–150 词的规范；实测当前 key_result 词数 40–464（中位 178），已达标。

### 未决清单 / D10 key_result草案

- 两表均**空表**（只有表头）。说明 sheet 第 26 行仍写「40 行 key_result < 40 词已列在 D10」——该问题已通过 K/KF 补写解决，说明文字滞后。

**对导入/展示的具体影响**：
1. **说明 sheet（作者约定）**：D2 解释 `TaVRN-A1`×3；D5 规定 `gene_id` 内基因名保留不动（所以 ID 异构是设计而非脏数据）；D6 规定 121 行一行多 DOI 用 `; ` 按位置对应；D7 规定同一参考基因组 ID 多行全部保留（导入**不得去重**）；D8/D9 规定物种统一与符号清洗；W22 行 506 `chrom_pos` 已改 `chr2A:743.110-743.115Mb`；K/KF 是把 `key_result` 补到 80–150 词的依据；另记录了 2 行删除（TaMIR397-6A、PG5 并入 Ms2）与 1 行撤回（TaBAH1 新增行）。
2. **未决清单 / D10 为空** → 作者侧没有待决项；D10 文字滞后（见 §16）。
3. **物种改写明细** 可直接当 `species_primary` 的**人工校验集**（14 个统一值 + 881 行"被移除的补充信息"），导入时用它抽查归一化一致性（注意其"新行号"与当前主 sheet 存在行号漂移：34 行空行 + 3 个重复行号，**不能按行号直接 join**，建议按 gene_name+原写法前缀匹配）。
4. **修改记录 1153 行是跨版本累计**（含 440 行"整行新增"、36 行"整行删除"），不能当作"仅本轮改动"；导入不消费该 sheet，但它是审计与回滚的依据。
5. **K补写依据**：36 行按 PubMed 摘要、16 行按全文补写 key_result；实测 key_result 词数 40–464（中位 178，mean 165.9），与作者 40–500 词规范一致，**导入无需再限制**。

---

## 15. 需要 Lead/作者决策的问题清单

| # | 问题 | 我的建议 | 阻塞什么 |
|---|---|---|---|
| Q1 | **clone_id 映射表落地**：请 Lead 按 §10.3 导出 `clone_id_mapping_v2055.csv`（321 inherit + 199 orphan），并用它对 272 行自动规则做交叉验证 | 已核实可继承 321/520=61.7%；导出 CSV 作为 importer 唯一输入并永久存档 | importer 核心逻辑、旧行删除策略 |
| Q2 | **199 行孤儿旧行**：删除（全量替换 1420 行）还是软保留（1619 行 + is_active）？ | A 删除 + 全量备份 + 映射 CSV 存档（推荐）；B 需改 4 个 API + CGI，本期成本高 | DDL/DML 方案 |
| Q3 | `species_primary` 命名：学名（`Triticum aestivum`）or 学名+英文名（`Triticum aestivum (bread wheat)`）？23 个枚举值是否接受？ | API 用学名；英文名由后端常量映射给前端（避免过滤/聚合歧义） | API schema/前端展示 |
| Q4 | **chrom_pos 坐标组装与 reference_genome_id 版本不一致**（`Refv1.0` 坐标 + `03G` v2.1 ID，1298 行）：以哪个为准？是否需要作者统一坐标？ | 先原样入库 + 解析 `assembly`；展示时标注如实；请作者下一版统一 | 详情页展示、未来区间查询 |
| Q5 | 16 行多值异常：是否请作者先在 Excel 修正（尤其行 1402 题名重复、3 行 TaGW8 缺题名、12 行缺年份）？ | 请作者修 Excel；importer 同时保留 §6.3 兜底规则 | 数据质量、references 正确性 |
| Q6 | `Thinopyrum ponticum` 的 `chr54`/`chr51` 是什么标签（5E/5J?）？ | 原样展示；by-chromosome 接受 `54/51`；请作者确认是否映射 | by-chromosome 端点/展示 |
| Q7 | 新数据无 author/author_mail（列 NOT NULL）：占位值用什么？是否改 NULL？ | 填 `WheatOmics curation` / `curation@wheatomics.sdau.edu.cn`（不改 NOT NULL，保持 CGI 兼容） | DML 必填列 |
| Q8 | 是否同意 `AUTO_INCREMENT=1626`（321 方案）/`1675`（272 兜底）+ 199 个孤儿 ID 永不复用 + 显式 clone_id 写入？ | 同意（确定性与幂等） | 导入脚本 |
| Q13 | **`#` 与 `normalize_text()` 冲突**（26 行含 `#`）：新数据需要 raw 显示，旧数据依赖 `#`→`'` 转义 | 推荐按 `data_version` 分支（新行 raw/新 cleaner，旧行旧 `normalize_text`），不用清理数据 | 详情 API 显示正确性（后端改动） |
| Q9 | **同 gene_id/同名但文献不同**的冲突核验：证据快照无 DOI/title，需 Lead 查生产详情端点（先查 P1 的 10 行） | 查 10 行即可覆盖 ID 可对齐样本 | 冲突清单 |
| Q10 | `key_result` 新数据为单段（旧 API 按 `###` 切分成数组）：前端是否需要改？ | 兼容（返回单元素数组），前端若假设多段需知会 | 前端 |
| Q11 | 是否本期就迁 utf8mb4？ | 不迁（本数据 0 个 4 字节字符；迁会因行大小失败，须先改 TEXT） | DDL |
| Q12 | `gene_species` 是否直接显示原文（最长 668 字符）还是只显示 `species_primary`？ | 列表/搜索显示 primary，详情显示原文（折叠） | 前端 |

---

## 16. 对 CONTEXT.md 事实基线的勘误与补充（已实测复核）

| # | CONTEXT 原文 | 实测 | 说明 |
|---|---|---|---|
| 16.1 | §1："部分字段含 HTML 标签（gene_phenotype 10 行、key_result 20、function_description 35、验证方法 13、cloning_method_description 16+1 pipe）" | **真实 HTML 标签 0 行**（严格标签正则全表 0 命中）；**58 行含 `<`/`>`**（Lead 已核实），全部是 `P<0.01`、`E-value<0.001`、`<70% similarity`、`<8% SBR` 等**数学比较符号**；`|` 仅 cloning_method_description 1 行 | CONTEXT 该条**需更正**；**不 strip、不清洗**，仅在渲染层 HTML 转义 |
| 16.2 | §1："37 种染色体标签；`T.ponticum chr54/chr51`（2 行未匹配正则）" | **38 种标签**（21 小麦 + 7 大麦 + 8 外来 + 54 + 51）；`chr54/chr51` **能**被 `chr([0-9A-Za-z.]+)` 匹配；真正"无 chr 前缀"的是另外 2 行：`AetTA1675 2D:2.33-2.45Mb`（Excel 297）、`SYMattis 4A:608.681-608.682Mb`（Excel 711） | 数字与对象均需更正 |
| 16.3 | §1："gene_name 同名重复 2 行；归一化后重复 6 行" | 精确同名重复 = `TaVRN-A1`×3（2 行超额，D2 预期）；"归一化后 6 行"是 `V-ATPase-C/c`、`V-ATPase-D/d`、`V-ATPase-A/a` 三对——经 `protein_family` 核对是**不同亚基**（大小写有意义），**不是重复行** | 勿按归一化名去重，否则误删 6 行 |
| 16.4 | §1："DOI 重复 600 行（同一文献多基因，属预期）" | 两种定义都成立：`doi` 单元格**完全相同**的行 600（=1420−820 唯一字符串）；**含至少一个在别处也出现的 DOI token** 的行 **938** | 建议统一口径：正文用"DOI 单元格重复 600 行 / token 级共享 938 行" |
| 16.5 | §1 未记录 | 新增实测：**两段式写作风格**（前 ~667 行标签体、之后叙述体，§4）；16 行多值不对齐（§6.2）；`gene_phenotype` 中位分句 149 字符（"标签"多非短标签）；`gene_name` 含 `/` 34 行需 URL encode | 影响派生规则与前端 |
| 16.6 | §1："60 行 >500 字符（species）" 等 | 均复核通过：296 原始物种串、1420 行 17 列全非空、60 行 >500、339 行 >100、max 668；gene_phenotype 897 行含 `;`、99 行 >1000；key_result 40–464 词（中位 178、均值 165.9）；protein_family 1176 唯一；validation 895 唯一；cloning 8；research 3；category 5；title max 473；DOI 130 行多值；year 115 行多值 | — |
| 16.7 | §2："旧库 gene_id 唯一、gene_name 463 唯一" | 复核通过；另实测旧库 **2 行 gene_id/gene_name 列错位**（clone_id 28/29：`TaBot1-4D`/`TraesCS4D02G326900`），迁移时需修正；旧库 TraesCS 类 480 行 = v02 461 + v01 10（Lead 核实）+ 1 行 v03，另有 40 行非 TraesCS（含 `/`、`,` 拼接 ID）→ 与新 v03 不同版本，是 CONTEXT 未强调的**最大迁移风险** | 补充事实 |
| 16.8 | §2："cloned_gene_tbl 520 行，AUTO_INCREMENT=527，clone_id 1–526 缺 6 个" | 复核通过（缺 3/7/8/13/15/25） | — |
| 16.9 | §1 未记录 | **26 行含 `#`**（species 3 / gene_phenotype 13 / key_result 14 / function_description 10 / protein_family 7 / cloning_method_description 23 / validation_method 19；Lead 核为 23 行）；`#` 是语义字符（`7S#1`、`6Ae#1`、`hc#28`、`QTgw.cau-7D`）。现后端 `legacy_parsers.normalize_text()` 把 `#`→`'`，会让详情页显示错乱 | **后端阻塞项**：按 `data_version` 分支 cleaner（§11.4/§15-Q13） |
| 16.10 | §0/§2 未记录 | clone_id 继承率：名称/染色体自动规则 272/520=52.31%；**经 Genehub v01/v02→v03 映射后 321/520=61.73%，199 孤儿（Lead 实测）** | CONTEXT 未给出该数字，实现以 321 为准 |

---

## 附录 A：证据与可复现性

- `docs/known_genes/_evidence/profile_v2055.json`：本文件全部可机读聚合（列统计/物种映射/受控词表/16 行异常/旧库映射计划/DDL 建议/其他 sheet 摘要）；**不含 1420 行原始数据**。
- 复现命令：
  ```bash
  /Users/mashengwei/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3 - <<'PY'
  import pandas as pd
  P="/Users/mashengwei/Desktop/markdown/陈甜甜/known-gene-paper-20260916/已知基因逐条提取清单_20261019-合集_修正版v2055_20261019.xlsx"
  df=pd.read_excel(P,sheet_name='数据（修正版v2055）',dtype=str,engine='openpyxl').fillna("")
  print(df.shape, df.columns.tolist())
  PY
  ```
- 限制：未读取生产库详情（仅用 Lead 提供的 520 条 6 字段快照）；clone_id 继承率已由 Lead 实测（321/520=61.73%），但"旧/新文献是否同一篇"仍需 Lead 查生产详情端点（§10.5）。

## 附录 B：待补充项（本版已完成度）

- [x] 17 列逐列剖析（非空/长度分位/特殊字符/样本/最长值）
- [x] 17 列 → DB/API/前端映射
- [x] 列类型与截断行数、行大小/字符集
- [x] 身份/去重/自然键
- [x] 多值拆分规则 + 16 行异常
- [x] 物种归一化规则 + 23 学名分布
- [x] chrom_pos 格式/38 标签/按物种集合
- [x] 受控词表 + 派生标签规则（phenotype/validation/protein family）
- [x] 与现库 520 对比 + 4 层自动规则（272/520）+ genehub 映射（321/520，199 孤儿）+ clone_id 方案
- [x] 校验规则清单 + JSONL/staging/事务流程
- [x] 其他 sheet 影响 + 说明 sheet D/U/W/K 条目
- [x] P5（genehub v01/v02→v03）实测覆盖率 —— Lead 已核实 321/520=61.73%，199 孤儿
- [ ] 10 行 P1 旧文献冲突核验 —— 待 Lead 查生产详情端点
- [x] `#` 字符与 `normalize_text()` 冲突盘点（§11.4，待后端决策）

