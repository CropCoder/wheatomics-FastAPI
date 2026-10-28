-- ============================================================================
-- KnownGene v2061 (from v2060) full reload — backup + staging tables
--
-- Executed once by MySQL root BEFORE the data phase:
--     sudo mysql < scripts/sql/known_gene_v2061_reload.sql
--
-- Only creates new tables / copies rows: cloned_gene_tbl is not modified here.
-- The pre-reload data (v2056, 1420 rows) is preserved in the backup table so
-- the data phase can be rolled back with:
--     migrate_known_genes_v2055.py --phase rollback --commit \
--       --backup-table cloned_gene_tbl_backup_20261028_v2061 ...
-- ============================================================================
USE cloned_gene_db;

-- 1) Pre-reload backup (re-runnable: clear then copy current rows)
CREATE TABLE IF NOT EXISTS cloned_gene_tbl_backup_20261028_v2061 LIKE cloned_gene_tbl;
DELETE FROM cloned_gene_tbl_backup_20261028_v2061;
INSERT INTO cloned_gene_tbl_backup_20261028_v2061 SELECT * FROM cloned_gene_tbl;

-- 2) Staging table for the single-transaction swap
CREATE TABLE IF NOT EXISTS cloned_gene_tbl_staging_20261028_v2061 LIKE cloned_gene_tbl;

-- 3) Record the new data version (metadata only)
ALTER TABLE cloned_gene_tbl
  COMMENT = 'Known genes curated list; data version v2061 (from v2060) imported 20261028';

-- 4) Self-check
SELECT 'backup_rows' AS k, COUNT(*) AS n FROM cloned_gene_tbl_backup_20261028_v2061
UNION ALL SELECT 'staging_rows', COUNT(*) FROM cloned_gene_tbl_staging_20261028_v2061
UNION ALL SELECT 'target_rows', COUNT(*) FROM cloned_gene_tbl;
