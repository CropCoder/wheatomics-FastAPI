-- bioproject_meta: metadata for the 73 NCBI/ENA/CNGB bioprojects that
-- back the CO_BioticStress_2026 coexpression database.
--
-- Apply once with a privileged account (wheatomics_user only has DML):
--   mysql -u <priv_user> -p <coexpressiondb> < init_bioproject_meta.sql
--
-- The crawler (scripts/crawl_bioprojects.py) populates this table by
-- calling NCBI E-utilities, the ENA portal API, and CNGB. Re-running
-- the script is idempotent (INSERT ... ON DUPLICATE KEY UPDATE).

USE coexpressiondb;

CREATE TABLE IF NOT EXISTS bioproject_meta (
  accession        VARCHAR(20)  NOT NULL,
  source           VARCHAR(16)  NOT NULL,                  -- 'NCBI' | 'ENA' | 'CNGB'
  title            TEXT         NULL,
  description      MEDIUMTEXT   NULL,
  organism         VARCHAR(255) NULL,
  submitter        VARCHAR(255) NULL,
  submission_date  DATE         NULL,
  publication_date DATE         NULL,
  data_type        VARCHAR(64)  NULL,
  sample_count     INT          NULL,
  study_type       VARCHAR(64)  NULL,
  related_pubmed   VARCHAR(64)  NULL,
  related_doi      VARCHAR(255) NULL,
  raw_json         JSON         NULL,
  fetched_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (accession),
  KEY idx_source (source),
  KEY idx_organism (organism),
  KEY idx_submission_date (submission_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
