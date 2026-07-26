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
