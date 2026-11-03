# KnownGene 论文作者/杂志入库（2026-11-03）

## 目标
References 的 `authors` / `journal` 不再只依赖 JSON 缓存，而是落到 MySQL：
- `cloned_gene_tbl.paper_authors`  TEXT
- `cloned_gene_tbl.paper_journal` TEXT

## 存储格式（与 DOI/title/year 位置对齐）
- 多值分隔：`###`（与 `paper_doi` / `paper_title` / `publication_years` 同一顺序）；
- `paper_authors` 每个 DOI 槽位内部：作者之间用 `"; "` 分隔；
- `paper_journal` 每个 DOI 槽位一个杂志名；
- 缺失槽位保留空串；全部缺失为 NULL。

示例（2 篇论文）：
```
paper_doi         10.1111/j.1469-8137.2011.03715.x###10.1111/pbi.13564
paper_authors     Author A; Author B###Author C; Author D
paper_journal     New Phytologist###Plant Biotechnology Journal
```

## 迁移
```bash
mysql -uroot cloned_gene_db < scripts/sql/known_gene_paper_meta_20261103.sql
```
回滚：
```sql
ALTER TABLE cloned_gene_tbl DROP COLUMN paper_authors, DROP COLUMN paper_journal;
```

## 回填现有数据
```bash
python3 scripts/known_genes_v2055/backfill_paper_meta.py \
  --ref-meta app/services/data/known_gene_reference_meta.json        # dry-run
python3 scripts/known_genes_v2055/backfill_paper_meta.py \
  --ref-meta app/services/data/known_gene_reference_meta.json --commit
```
DOI 大小写不敏感；无 DOI 行跳过。

## API 行为
`GET /api/genes/known/{id}` 的 `references[]`：
1. 优先用 DB 的 `paper_authors` / `paper_journal`（按 DOI 位置对齐）；
2. 对应槽位为空时回退 JSON 缓存；
3. `pmid` 仍来自缓存（如需要可后续加 `paper_pmid` 列）。

## 未来更新流程
1. 改 Excel；
2. `scripts/known_genes_v2055/extract.py` 生成 JSONL；
3. 更新 DOI 缓存：
   `python3 scripts/enrich_known_gene_references.py --xlsx <xlsx> --out app/services/data/known_gene_reference_meta.json --workers 8`
4. `scripts/known_gene_push.py` 会按 DOI 自动附加 `paper_authors` / `paper_journal`，随写接口一起入库；
5. 验证：`GET /api/genes/known/{id}` references 应显示 authors/journal，且 DB 两列非空。

## 验证点
- `information_schema.COLUMNS` 有 `paper_authors` / `paper_journal`；
- `SELECT clone_id, paper_authors, paper_journal FROM cloned_gene_tbl WHERE paper_doi IS NOT NULL` 覆盖率；
- API detail 的 references 与 DB 一致；
- 写接口 dry-run 对新字段 `errors=0`。
