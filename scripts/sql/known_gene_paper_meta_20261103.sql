-- ============================================================================
-- KnownGene: store paper authors/journal in MySQL (v2172+)
--
-- Adds two TEXT columns to cloned_gene_tbl:
--   paper_authors  -- '###'-joined, positionally aligned with paper_doi/title/year;
--                     each entry is '; '-joined author names
--   paper_journal  -- '###'-joined, positionally aligned with paper_doi/title/year
--
-- Row-size note: TEXT columns store only a 20-byte pointer inline, so the
-- existing ~60 KB row remains under MySQL's 65,535-byte limit.
--
-- Rollback:
--   ALTER TABLE cloned_gene_tbl DROP COLUMN paper_authors, DROP COLUMN paper_journal;
-- ============================================================================
USE cloned_gene_db;

ALTER TABLE cloned_gene_tbl
  ADD COLUMN paper_authors TEXT
    COMMENT 'v2172+: ###-joined author lists, positionally aligned with paper_doi/title/year; each entry ; -joined',
  ADD COLUMN paper_journal TEXT
    COMMENT 'v2172+: ###-joined journal names, positionally aligned with paper_doi/title/year';

-- verify
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'cloned_gene_db'
  AND TABLE_NAME = 'cloned_gene_tbl'
  AND COLUMN_NAME IN ('paper_authors','paper_journal');
