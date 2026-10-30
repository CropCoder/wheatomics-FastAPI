# 参考文献卡片：作者 / 杂志 / 年份补全（Crossref + PubMed）

日期：2026-10-29　状态：已上线生产

## 1. 需求
KnownGene 详情页的 References 卡片原来只有「年份 + 题名（DOI 链接）」；数据库只有 `paper_title / paper_doi / publication_years`，**没有作者和杂志**。
目标：卡片增加**作者、杂志、年份**，作者/杂志缺失时用 **DOI（优先）或 PubMed** 补全，并且**必须验证 DOI↔题名匹配**后才展示。

## 2. 实现方案
- 新增**参考文献元数据缓存**：`app/services/data/known_gene_reference_meta.json`
  - 以 DOI（小写）为键：`{authors, journal, year, title, source, title_similarity, verified, pmid?}`
  - 生成脚本：`scripts/enrich_known_gene_references.py`
- 数据来源/顺序：
  1. Crossref `https://api.crossref.org/works/{DOI}`（作者、container-title、issued 年份、题名）；
  2. Crossref 失败/题名不匹配 → PubMed `esearch?term="{DOI}"[DOI]` + `esummary` 兜底；
  3. 所有候选都做**题名归一化相似度**校验（≥0.6 才 `verified=true`），并记录 `title_similarity`、`year_delta`；
  4. 预印本（10.1101/*）Crossref 无 journal → 标 `bioRxiv (preprint)`。
- 后端 API：
  - `DOIReference` 新增 `authors: list[str] | None`、`journal: str | None`、`pmid: str | None`；
  - `_build_known_references()` 从缓存按 DOI 查元数据；题名 key 兜底；
  - 只返回经过校验的元数据（未校验的 DOI 不填 authors/journal）。
- 前端 `app/static/genes/detail.html`：
  - References 卡片布局：`[年份 chip] 作者（全部作者，Family + 首字母缩写） · 杂志（斜体）` 下一行题名（DOI 链接）；
  - 作者格式化为 `Family G.`（如 `Lang J., Fu Y., Zhou Y., …（全部 30 位）`）；
  - 缺少作者/杂志时仅省略对应部分，不破坏卡片。

## 3. 覆盖与验证（2026-10-29）
- 参考文献总数 **1,574** 条，覆盖 **883 个唯一 DOI**；
- `doi_with_meta = 883 / 883`，`doi_verified = 883 / 883`，`title mismatch = 0`（全部题名相似度 ≥0.6）；
- 抽样 20 个基因、24 条参考文献：缺作者 0、缺杂志 0（预印本已标 bioRxiv）；
- 例：`clone_id 20`（Myb10-D/PHS-3D/Tamyb10-3D）
  - 参考文献：`2021 · Lang J., Fu Y., Zhou Y., Cheng M., Deng M.et al. (25 more) · New Phytologist · Myb10-D confers PHS-3D resistance ...`（点击后展开全部 30 位）
  - 截图：`docs/known_genes/_evidence/known_gene_references_card_20261029.png`

## 4. 部署/回滚
- 已拷贝并重启生产（`wheatomics-api`）：
  - `app/schemas/gene.py`
  - `app/api/routers/gene.py`
  - `app/services/data/known_gene_reference_meta.json`
  - `app/static/genes/detail.html`
  - `scripts/enrich_known_gene_references.py`
- 回滚：恢复 `/tmp/kg_ref_backup_20261029/` 的 3 个源文件（schema/router/detail.html），删除/恢复缓存 JSON，`sudo systemctl restart wheatomics-api`。
- 刷新缓存流程（新增论文/修正 DOI 后）：
  ```bash
  python3 scripts/enrich_known_gene_references.py \
    --input /tmp/refs.json --out app/services/data/known_gene_reference_meta.json --workers 8
  # 上传缓存 + 重启 wheatomics-api
  ```

## 5. 已知情况
- 5 条 bioRxiv 预印本 Crossref 无 `container-title`，已按 `bioRxiv (preprint)` 标注；
- 缓存按 DOI 命中；如后续表里新增 DOI，需要重跑脚本补元数据（否则卡片只显示年份/题名，不显示作者/杂志）；
- `DOIReference.title` 仍以数据库题名为准（缓存题名只用于校验，不覆盖表内题名）。

## 6. 技能固化
本要求已写入 `wheat-known-gene-curation` 技能，后续基因更新必须按同一标准执行：
- `SKILL.md` §0 规则 9（参考文献卡片三要素 MANDATORY）；
- `references/reference-metadata.md`（完整标准/数据流/检查/上线步骤）；
- `scripts/enrich_known_gene_references.py`（支持 `--xlsx` 或 `--input`）；
- `scripts/check_reference_metadata.py`（发布前检查，`ok == unique_doi` 才算通过）。
