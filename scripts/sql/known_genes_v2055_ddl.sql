-- ============================================================================
-- KnownGene v2056 data replacement — schema migration (MySQL 5.7.33, cloned_gene_db)
--
-- Execute ONCE as MySQL root on the production node, BEFORE the data phase:
--     sudo mysql < scripts/sql/known_genes_v2055_ddl.sql
--
-- Design constraints (see docs/known_genes/backend_investigation.md §4):
--   * append-only columns, no AFTER, no rename: the legacy CGI page
--     cgi-py-RawScript/gene_search_by_id.py reads rows with SELECT * and uses
--     positional indexes ele[0..11], so column order must stay stable.
--   * widen only two columns that the v2056 data overflows:
--       gene_phenotype  max 1677 chars > varchar(1000)
--       gene_species    max  668 chars > varchar(500)
--   * keep utf8mb3 and key_result VARCHAR(15000): converting the table to
--     utf8mb4 would need 73,490 B > 65,535 B row size and fail with ERROR 1118.
--     This migration stays at 60,691 B (< 65,535 B).
--   * publication_year keeps its YEAR(4) meaning (= earliest year); the raw
--     multi-value list goes to the new publication_years column.
--
-- Rollback (only if the DDL itself is wrong, before data import):
--   see the commented block at the bottom.
-- ============================================================================

USE cloned_gene_db;

-- 0) Pre-flight: record the current state (expect 520 rows / max clone_id 526 /
--    AUTO_INCREMENT 527). Run also a logical backup from the shell:
--    mysqldump --single-transaction --no-tablespaces --default-character-set=utf8mb4 \
--      cloned_gene_db cloned_gene_tbl > /var/backups/cloned_gene_tbl_pre_v2056_20261028.sql
SELECT COUNT(*) AS rows_now, MIN(clone_id) AS min_id, MAX(clone_id) AS max_id FROM cloned_gene_tbl;
SELECT AUTO_INCREMENT FROM information_schema.TABLES
 WHERE TABLE_SCHEMA = 'cloned_gene_db' AND TABLE_NAME = 'cloned_gene_tbl';

-- 1) Schema change: widen 2 columns + append 8 columns + 4 prefix indexes
ALTER TABLE cloned_gene_tbl
  MODIFY COLUMN gene_phenotype VARCHAR(2000) DEFAULT NULL
    COMMENT 'Trait/phenotype free text; widened for v2056 (max 1677 chars)',
  MODIFY COLUMN gene_species VARCHAR(1000) DEFAULT NULL
    COMMENT 'Species free text incl. materials; widened for v2056 (max 668 chars)',

  ADD COLUMN reference_genome_id VARCHAR(100) DEFAULT NULL
    COMMENT 'v2056 col2: reference genome ID (IWGSC v3 03G / HORVU / GenBank); NULL = legacy row',
  ADD COLUMN protein_family TEXT
    COMMENT 'v2056 col9: protein family - function description (<=2657 chars)',
  ADD COLUMN validation_method TEXT
    COMMENT 'v2056 col12: semicolon-separated validation method tags; API splits to validation_methods[]',
  ADD COLUMN research_strategy VARCHAR(32) DEFAULT NULL
    COMMENT 'v2056 col13: Reverse genetics / Forward genetics / Not reported',
  ADD COLUMN functional_category VARCHAR(64) DEFAULT NULL
    COMMENT 'v2056 col14: one of 5 controlled categories',
  ADD COLUMN species_primary VARCHAR(64) DEFAULT NULL
    COMMENT 'Normalized NCBI binomial (23-value controlled map); stats/search dimension',
  ADD COLUMN publication_years VARCHAR(64) DEFAULT NULL
    COMMENT 'v2056 col17 raw multi-year values, ###-joined (positional with title/doi)',
  ADD COLUMN chromosome VARCHAR(16) DEFAULT NULL
    COMMENT 'Normalized chromosome token parsed from chrom_pos (5A/3H/1R/chr51...); by-chromosome/stats',

  ADD INDEX idx_kg_gene_id (gene_id(64)),
  ADD INDEX idx_kg_gene_name (gene_name(64)),
  ADD INDEX idx_kg_ref_id (reference_genome_id(64)),
  ADD INDEX idx_kg_chromosome (chromosome);

-- 2) Table comment records the data version (metadata-only change)
ALTER TABLE cloned_gene_tbl
  COMMENT = 'Known genes curated list; data version v2056 imported 20261028';

-- 3) Full-table backup (structure = post-migration; content = legacy 520 rows,
--    new columns NULL). Used by rollback and by the clone_id inheritance check.
CREATE TABLE cloned_gene_tbl_backup_20261028 LIKE cloned_gene_tbl;
INSERT INTO cloned_gene_tbl_backup_20261028 SELECT * FROM cloned_gene_tbl;

-- 4) Staging table for the data phase (CREATE ... LIKE inherits utf8; the
--    database default is latin1, so never hand-write CREATE TABLE here).
CREATE TABLE cloned_gene_tbl_staging_20261028 LIKE cloned_gene_tbl;

-- 5) Post-DDL checks (expect the new columns/indexes and the same 520 rows)
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, CHARACTER_SET_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'cloned_gene_db' AND TABLE_NAME = 'cloned_gene_tbl'
ORDER BY ORDINAL_POSITION;

SELECT COUNT(*) AS rows_after_ddl FROM cloned_gene_tbl;
SELECT COUNT(*) AS backup_rows FROM cloned_gene_tbl_backup_20261028;
SELECT COUNT(*) AS staging_rows FROM cloned_gene_tbl_staging_20261028;
SHOW INDEX FROM cloned_gene_tbl;

-- ============================================================================
-- Structure rollback (ONLY if the DDL itself is broken and NO data has been
-- imported yet — it drops the new columns and their data):
--
-- ALTER TABLE cloned_gene_tbl
--   DROP INDEX idx_kg_gene_id,
--   DROP INDEX idx_kg_gene_name,
--   DROP INDEX idx_kg_ref_id,
--   DROP INDEX idx_kg_chromosome,
--   DROP COLUMN reference_genome_id,
--   DROP COLUMN protein_family,
--   DROP COLUMN validation_method,
--   DROP COLUMN research_strategy,
--   DROP COLUMN functional_category,
--   DROP COLUMN species_primary,
--   DROP COLUMN publication_years,
--   DROP COLUMN chromosome,
--   MODIFY COLUMN gene_phenotype VARCHAR(1000) DEFAULT NULL,
--   MODIFY COLUMN gene_species VARCHAR(500) DEFAULT NULL;
-- ALTER TABLE cloned_gene_tbl COMMENT = '';
-- DROP TABLE cloned_gene_tbl_staging_20261028;
-- -- keep cloned_gene_tbl_backup_20261028 until the migration is accepted
-- ============================================================================
