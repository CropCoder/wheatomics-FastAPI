# KnownGene v2056 — 多值字段对齐修正记录

> 从 v2055（md5 `85f3e6207bba347fb1d7dcddda881cd6`）到 v2056（md5 `1dbbeff77f8f53eb33e8ea133d32cb65`），
> 仅修改 16 行、共 19 个单元格；其余 1404 行、其余列逐单元格一致（脚本核验 changed_cells=19，全部落在目标 16 行）。

## 修正规则

`说明` sheet 约定：`title`/`doi`/`publication_year` 三列以 `; ` 分隔，第 k 个 DOI ↔ 第 k 个题名 ↔ 第 k 个年份一一对应。v2055 有 16 行三列数量不一致，按以下方式修正：

| 类型 | 行数 | 修正 |
|---|---|---|
| 2 DOI + 2 题名 + 1 年份 | 12 | 补第 2 篇文献年份（Crossref `issued` 年份） |
| 2 DOI + 1 题名 + 1 年份 | 3（TaGW8-7A/B/D） | 补第 2 篇文献题名 + 年份（Crossref `10.3389/fpls.2019.00212`） |
| 3 DOI + 4 题名 + 3 年份 | 1（VRN-D3/FT-D1） | 删除重复题名（第 3 条与第 2 条重复），保留 3 题名 3 年份 |

所有补写值均来自 Crossref `https://api.crossref.org/works/{doi}` 的 `title` / `issued`（2026-10-28 实时查询），
题名去除 Crossref 内嵌 HTML 标签并折叠空白；空行不补占位。修正后全表 1420 行三列数量 100% 对齐。

## 逐行明细

| Excel 行 | gene_name | 字段 | 原值 | 新值 | 依据 |
|---|---|---|---|---|---|
| 241 | DRG1/TaACT7/TaACTIN7-D | publication_year（入库） | 2023 | 2023; 2023 | 补第 2 篇文献年份（Crossref 10.1016/j.jgg.2023.09.001 = 2023） |
| 245 | TaSERK1-A | publication_year（入库） | 2023 | 2023; 2023 | 补第 2 篇文献年份（Crossref 10.1094/phyto-11-22-0429-r = 2023） |
| 249 | TaSERK1-B | publication_year（入库） | 2023 | 2023; 2023 | 补第 2 篇文献年份（Crossref 10.1094/phyto-11-22-0429-r = 2023） |
| 254 | TaSERK1-D | publication_year（入库） | 2023 | 2023; 2023 | 补第 2 篇文献年份（Crossref 10.1094/phyto-11-22-0429-r = 2023） |
| 283 | TaNF-YB1 | publication_year（入库） | 2023 | 2023; 2023 | 补第 2 篇文献年份（Crossref 10.1016/j.jgg.2023.04.002 = 2023） |
| 331 | TaABI3-A1/TaVP1-A | publication_year（入库） | 2024 | 2024; 2024 | 补第 2 篇文献年份（Crossref 10.1111/jipb.13600 = 2024） |
| 386 | RG1/TaAPA2 | publication_year（入库） | 2024 | 2024; 2024 | 补第 2 篇文献年份（Crossref 10.1007/s11427-024-2620-7 = 2024） |
| 439 | HvFT3 | publication_year（入库） | 2011 | 2011; 2011 | 补第 2 篇文献年份（Crossref 10.1186/1471-2229-11-164 = 2011） |
| 617 | TaGW8-7A/TaSPL16-7A | publication_year（入库） | 2019 | 2019; 2019 | 补第 2 篇文献年份（Crossref 10.3389/fpls.2019.00212 = 2019） |
| 617 | TaGW8-7A/TaSPL16-7A | title（入库） | Diversity and sub-functionalization of TaGW8 homoeologs hold potential for genetic yield improvement in wheat | Diversity and sub-functionalization of TaGW8 homoeologs hold potential for genetic yield improvement in wheat; Identification and Functional Characterization of… | 补第 2 篇文献题名（Crossref 10.3389/fpls.2019.00212） |
| 619 | TaGW8-7B/TaSPL16-7B | publication_year（入库） | 2019 | 2019; 2019 | 补第 2 篇文献年份（Crossref 10.3389/fpls.2019.00212 = 2019） |
| 619 | TaGW8-7B/TaSPL16-7B | title（入库） | Diversity and sub-functionalization of TaGW8 homoeologs hold potential for genetic yield improvement in wheat | Diversity and sub-functionalization of TaGW8 homoeologs hold potential for genetic yield improvement in wheat; Identification and Functional Characterization of… | 补第 2 篇文献题名（Crossref 10.3389/fpls.2019.00212） |
| 621 | TaGW8-7D/TaSPL16-7D | publication_year（入库） | 2019 | 2019; 2019 | 补第 2 篇文献年份（Crossref 10.3389/fpls.2019.00212 = 2019） |
| 621 | TaGW8-7D/TaSPL16-7D | title（入库） | Diversity and sub-functionalization of TaGW8 homoeologs hold potential for genetic yield improvement in wheat | Diversity and sub-functionalization of TaGW8 homoeologs hold potential for genetic yield improvement in wheat; Identification and Functional Characterization of… | 补第 2 篇文献题名（Crossref 10.3389/fpls.2019.00212） |
| 1094 | Lr1 | publication_year（入库） | 2007 | 2007; 2007 | 补第 2 篇文献年份（Crossref 10.1007/s00122-007-0551-z = 2007） |
| 1112 | TaARE1-7A | publication_year（入库） | 2021 | 2021; 2021 | 补第 2 篇文献年份（Crossref 10.1016/j.jgg.2021.07.003 = 2021） |
| 1117 | TaARE1-7B | publication_year（入库） | 2021 | 2021; 2021 | 补第 2 篇文献年份（Crossref 10.1016/j.jgg.2021.07.003 = 2021） |
| 1126 | TaARE1-7D | publication_year（入库） | 2021 | 2021; 2021 | 补第 2 篇文献年份（Crossref 10.1016/j.jgg.2021.07.003 = 2021） |
| 1402 | VRN-D3/FT-D1 | title（入库） | The wheat and barley vernalization gene VRN3 is an orthologue of FT; A comprehensive map of DNA-segment copy number variation in 491 genomes of common wheat unc… | The wheat and barley vernalization gene VRN3 is an orthologue of FT; A comprehensive map of DNA-segment copy number variation in 491 genomes of common wheat unc… | 删除重复题名（第 3 条与第 2 条重复；Crossref 10.1016/j.xplc.2024.101226 对应第 2 条） |

## Crossref 原始元数据（21 个 DOI）

| DOI | Crossref year | Crossref title |
|---|---|---|
| 10.1002/advs.202401383 | 2024 | Deciphering the Transcriptional Regulatory Network Governing Starch and Storage Protein Biosynthesis in Wheat for Breedi… |
| 10.1007/s00122-007-0551-z | 2007 | Physical mapping and identification of a candidate for the leaf rust resistance gene Lr1 of wheat |
| 10.1007/s11103-007-9201-8 | 2007 | Leaf rust resistance gene Lr1, isolated from bread wheat (Triticum aestivum L.) is a member of the large psr567 gene fam… |
| 10.1007/s11427-022-2286-0 | 2023 | TaMADS29 interacts with TaNF-YB1 to synergistically regulate early grain development in bread wheat |
| 10.1007/s11427-024-2620-7 | 2024 | Mutations in wheat TaAPA2 gene result in pleiotropic effects on plant architecture |
| 10.1007/s11427-024-2629-1 | 2024 | Identification of a von Willebrand factor type A protein affecting both grain and flag leaf morphologies in wheat |
| 10.1016/j.cj.2019.09.006 | 2019 | Diversity and sub-functionalization of TaGW8 homoeologs hold potential for genetic yield improvement in wheat |
| 10.1016/j.ijbiomac.2022.12.240 | 2023 | The somatic embryogenesis receptor kinase TaSERK1 participates in the immune response to Rhizoctonia cerealis infection … |
| 10.1016/j.jgg.2021.07.003 | 2021 | Genetic manipulations of TaARE1 boost nitrogen utilization and grain yield in wheat |
| 10.1016/j.jgg.2023.04.002 | 2023 | TabHLH95-TaNF-YB1 module promotes grain starch synthesis in bread wheat |
| 10.1016/j.jgg.2023.09.001 | 2023 | TaACTIN7-D regulates plant height and grain shape in bread wheat |
| 10.1016/j.xplc.2024.101226 | 2025 | A comprehensive map of DNA-segment copy number variation in 491 genomes of common wheat uncovers genes associated with m… |
| 10.1073/pnas.0607142103 | 2006 | The wheat and barley vernalization gene VRN3 is an orthologue of FT |
| 10.1093/jxb/erq382 | 2011 | Expression analysis of vernalization and day-length response genes in barley (Hordeum vulgare L.) indicates that VRNH2 i… |
| 10.1094/phyto-11-22-0429-r | 2023 | The Leucine-Rich Repeat Receptor-Like Kinase Protein TaSERK1 Positively Regulates High-Temperature Seedling Plant Resist… |
| 10.1111/jipb.13151 | 2021 | Increasing yield potential through manipulating of an ARE1 ortholog related to nitrogen use efficiency in wheat by CRISP… |
| 10.1111/jipb.13600 | 2024 | TaSRO1 interacts with TaVP1 to modulate seed dormancy and pre‐harvest sprouting resistance in wheat |
| 10.1111/nph.19246 | 2023 | A Glu209Lys substitution in DRG1/TaACT7, which disturbs F‐actin organization, reduces plant height and grain length in b… |
| 10.1111/pbi.70032 | 2025 | TaFT‐D1 positively regulates grain weight by acting as a coactivator of TaFDL2 in wheat |
| 10.1186/1471-2229-11-164 | 2011 | Adaptation of barley to mild winters: A role for PPDH2 |
| 10.3389/fpls.2019.00212 | 2019 | Identification and Functional Characterization of Squamosa Promoter Binding Protein-Like Gene TaSPL16 in Wheat (Triticum… |

## 复现

```
python3 scripts/known_genes_v2055/extract.py --xlsx "..._修正版v2056_20261028.xlsx"
# 校验：fatals=0, multi_value_anomalies=0, rows=1420
```
