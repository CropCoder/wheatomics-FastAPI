# WheatOmics 1.0 — 麦族多组学数据平台更新说明

**网址**：[https://wheatomics.sdau.edu.cn](https://wheatomics.sdau.edu.cn)  
**API 文档**：[https://wheatomics.sdau.edu.cn/api/docs](https://wheatomics.sdau.edu.cn/api/docs)  
**更新日期**：2026年7月  

---

## 一、数据更新与梳理

随着小麦及麦族（Triticeae）基因组学研究的持续推进，WheatOmics 平台对以下数据资源进行了系统性更新和整理：

### 1.1 OrthoFinder 同源群升级

- **数据版本**：从 `Results_Jun30` → `Results_Jul23` → `Results_Jul24`，累计新增数十个小麦族基因组。
- **新增基因组**（不完全枚举）：
  - *Hordeum erectifolium*（大麦野生近缘种）
  - *Elymus nutans* Griseb.（披碱草）
  - *Aegilops tauschii* Aet6（节节麦）
  - *Triticum timopheevii* PI94760（提莫非维小麦）
  - *Wild emmer* V2（野生二粒小麦）
  - *Barley3*、*Dasypyrum villosum* 等多个麦族关键物种
- **分组体系升级**：在原有 7 个同源群（homoeologous group）基础上，新增 **type1/type2 双重分类**——
  - **Triticum aestivum（六倍体小麦）组**：type1 = yes 的物种
  - **Triticeae（小麦族）组**：type2 = yes 的物种
- **基因标签精准化**：基于 `genome_type.txt`（209 条记录）建立物种→亚基因组权威映射，修正了旧版中多物种标签错配问题（如 Barley3_H 被误标为 B 亚基因组等）。

### 1.2 VariantHub 变异数据库

- **参考基因组**：Chinese Spring v1.0（IWGSCv1.0）和 v2.1 双版本支持。
- **数据集**：目前已收录 **20+ 套 VCF 变异数据集**，涵盖：
  - 1000 小麦外显子组（1kEC）
  - 355 普通小麦全基因组重测序（WGS）
  - WEC 过滤 SNP 集、GBS SNP / InDel 集
  - Cheng et al. 2024、VMap 1.0 等近年重要研究数据
  - all491 CNV+SNP+InDel 综合变异图谱（Ma et al. 2025, *Plant Communications*）
  - 287exome + wgs2191（CS2.1 参考基因组）
- **样本元数据过滤**：支持按 country（国家）、population（群体）、growth_habit（生长习性）、status（品种状态）筛选样本。

### 1.3 多组学模块数据同步

- **基因表达**（GeneExpression）：多项目 RNA-seq 查询与可视化。
- **共表达网络**（Co-expression）：支持项目级共表达数据库检索。
- **蛋白质互作**（WheatPPI）：麦族蛋白互作网络。
- **GO/KEGG 富集**：基于超几何检验的通路富集分析。
- **文献检索**（Triticeae Papers）：超过万条麦族文献，支持 PMID 标注与关键词检索。
- **同源比对**（BLAST / preBLAST / HomologFinder / IDConvert）：多库比对与基因 ID 转换。

---

## 二、新模块设计

### 2.1 OrthoFinder 直系同源群浏览器（重大升级）

**访问地址**：[https://wheatomics.sdau.edu.cn/orthofinder/](https://wheatomics.sdau.edu.cn/orthofinder/)

- **双类型进化树展示**：输入任意麦族基因ID后，页面同时展示 **Triticum aestivum（六倍体小麦）** 和 **Triticeae（小麦族）** 两棵进化树，分别展示物种内和麦族内的基因家族演化关系。
- **交互式树操作**：每棵进化树独立支持圆形/矩形布局切换、缩放、重置，操作互不干扰。
- **一键下载**：每个结果页面提供 3 个下载按钮——
  - Download OG tree and protein alignment（完整同源群树+比对）
  - Download Triticum aestivum Homoeologous tree and protein alignment
  - Download Triticeae Homoeologous tree and protein alignment
  - 下载的 FASTA 序列严格按树的叶子顺序排列，确保一一对应。
- **无数据库依赖**：所有数据直接从 OrthoFinder 结果文件系统读取（Orthogroups.txt、SequenceIDs.txt、SpeciesIDs.txt、genome_type.txt、BED 文件、Trees_ids/ 目录），无需 MySQL 导入即可运行。

### 2.2 VariantHub 变异查询平台

**访问地址**：[https://wheatomics.sdau.edu.cn/VariantHub/](https://wheatomics.sdau.edu.cn/VariantHub/)

- **双参考基因组**：Chinese Spring 1.0 和 2.1 版本任意切换。
- **区域查询 + 变异ID查询**：支持 chr:start-end 区域查询和精确变异 ID 查询。
- **样本过滤**：支持手动输入样本 ID 列表，或通过元数据下拉框（国家/群体/生长习性等）交互式过滤。
- **分页浏览与 CSV 导出**：结果以表格形式分页展示，一键导出 CSV 格式供本地分析。

---

## 二（续）、多组学模块概览

除上述两大重点升级模块外，WheatOmics 平台还持续维护着完整的多组学数据分析工具链：

### 2.3 基因表达查询（GeneExpression）

**访问地址**：[https://wheatomics.sdau.edu.cn/expression/](https://wheatomics.sdau.edu.cn/expression/)

- 支持 **多项目 RNA-seq 表达谱检索**，覆盖不同组织、发育时期、胁迫处理的转录组数据。
- 提供基因在不同项目中的表达量（FPKM/RPKM）可视化，支持单个基因快速查询和批量比较。
- API 端点：`/api/expression/projects`（项目列表）、`/api/expression/query`（按基因 ID 查询）。

### 2.4 共表达网络分析（Co-expression）

**访问地址**：[https://wheatomics.sdau.edu.cn/coexpression/](https://wheatomics.sdau.edu.cn/coexpression/)

- 基于多个独立 RNA-seq 项目构建的 **基因共表达网络数据库**。
- 输入一个基因 ID，检索与之共表达的相关基因及其相关系数。
- 支持选择不同项目/数据库进行查询，适配不同生物学场景。
- API 端点：`/api/coexpression/databases`、`/api/coexpression/query`、`/api/coexpression/projects`。

### 2.5 蛋白质互作网络（WheatPPI）

**访问地址**：[https://wheatomics.sdau.edu.cn/wheatPPI/](https://wheatomics.sdau.edu.cn/wheatPPI/)

- 麦族（Triticeae）**蛋白质-蛋白质相互作用（PPI）数据库**，整合实验验证和预测的互作对。
- 支持按基因 ID 检索其互作伙伴，以网络图或列表形式展示。
- API 端点：`/api/ppi/query`。

### 2.6 GO/KEGG 富集分析

**访问地址**：[https://wheatomics.sdau.edu.cn/GO_KEGG/](https://wheatomics.sdau.edu.cn/GO_KEGG/)

- 基于 **超几何检验 + Benjamini-Hochberg 多重检验校正** 的经典富集分析方法。
- 支持 **GO（Gene Ontology）** 和 **KEGG 通路** 两种富集模式。
- 用户提交基因列表，系统返回显著富集的 GO 条目或 KEGG 通路及对应 p 值。
- 提供反向查询：从 GO 条目或 KEGG 通路查找已在数据库中注释的基因。
- API 端点：`/api/go-kegg/go-enrichment`、`/api/go-kegg/kegg-enrichment`、`/api/go-kegg/go-genes`、`/api/go-kegg/kegg-genes`。

### 2.7 文献检索（Triticeae Papers）

**访问地址**：[https://wheatomics.sdau.edu.cn/papers](https://wheatomics.sdau.edu.cn/papers)

- 收录 **数万条麦族（Triticeae）相关科研文献**，覆盖基因组学、功能基因、表达调控、遗传育种等方向。
- 支持按关键词、PMID、物种名等进行多维检索。
- 每篇文献提供摘要信息展示、PMID 链接，以及用户标注（annotation）功能。
- 支持文献统计数据查询（年度发表趋势、物种分布等）。
- API 端点：`/api/triticeae/papers`、`/api/triticeae/papers/{pmid}/annotation`、`/api/triticeae/papers/stats`。

### 2.8 多库同源比对（BLAST / preBLAST / HomologFinder / IDConvert）

- **BLAST 比对**（[https://wheatomics.sdau.edu.cn/blast/blast.html](https://wheatomics.sdau.edu.cn/blast/blast.html)）：
  支持 blastp/blastn/blastx/tblastn/tblastx 五种程序，可对 **蛋白库**（aggregated / 六倍体小麦 / 四倍体小麦 / 二倍体 / 大麦 / 山羊草等分类）和 **核酸库**（全基因组 CDS / 基因组序列库）进行在线比对，返回传统表格+可视化双格式结果。
  API 端点：`/api/blast/search`、`/api/blast/databases`、`/api/blast/status`。

- **preBLAST 预先比对数据库**（[https://wheatomics.sdau.edu.cn/preblast/](https://wheatomics.sdau.edu.cn/preblast/)）：
  针对常用物种预先计算的 BLAST 结果数据库，检索速度远快于实时 BLAST。

- **HomologFinder 同源基因搜索**：基于小麦-水稻-拟南芥直系同源关系表的快速同源基因查询。
  API 端点：`/api/comparative/homologs/wheat-rice-arabidopsis`。

- **IDConvert 基因 ID 转换**（[https://wheatomics.sdau.edu.cn/idConvert/](https://wheatomics.sdau.edu.cn/idConvert/)）：
  支持不同小麦基因组版本和不同命名体系之间的基因 ID 互转。
  API 端点：`/api/comparative/id-conversion`。

- **FASTA 序列获取（GetSequence）**（[https://wheatomics.sdau.edu.cn/getfasta/](https://wheatomics.sdau.edu.cn/getfasta/)）：
  支持基因 ID、批量 ID 和染色体区间三种模式的 CDS / 蛋白序列快速提取。
  API 端点：`/api/sequence/by-gene`、`/api/sequence/by-interval`、`/api/sequence/batch`。

---

## 三、已知问题与免责声明

本次升级涉及大量底层数据的迁移和模块重构，部分功能和数据集仍处于测试阶段：

- OrthoFinder 模块已从 `Results_Jun30` 迁移至 `Results_Jul24`，数据量显著增长，搜索速度可能受数据规模影响。
- 部分麦族物种的 type1/type2 分类依赖 `SpeciesIDs_cluster.txt` 和 BED 文件的联合解析，少数基因组（cluster 列空、仅靠 BED 判断分组）的分类结果可能与预期有偏差，欢迎通过反馈渠道指正。
- VariantHub 的样本元数据过滤为数据集特定功能——仅对提供元数据的 VCF 数据集生效；部分数据集的样本名称可能存在重复。
- 前端交互（进化树渲染、缩放、圆形/矩形切换）仍在持续优化中。

**Beta 版数据和模块可能存在不完整或不稳定的情况，请各位同行谅解。**

---

## 四、反馈与建议

WheatOmics 平台致力于服务麦族基因组学和功能基因组学研究社区。我们热烈欢迎各位研究者根据自身研究需求提出：

- **新数据需求**：希望新增哪些基因组、哪些数据集（变异、表达、共表达、文献等）
- **新功能建议**：当前工具无法满足的分析需求
- **问题反馈**：使用过程中发现的任何异常、错误或体验不佳之处

**联系邮箱**：[shengweima@icloud.com](mailto:shengweima@icloud.com)  
**平台网址**：[https://wheatomics.sdau.edu.cn](https://wheatomics.sdau.edu.cn)  

---

*WheatOmics 开发团队*  
*山东农业大学 · 2026年7月*
