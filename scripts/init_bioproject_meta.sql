-- Create the bioproject metadata table used by /api/coexpression/projects.
-- Normally the crawler creates it automatically (ensure_table); this file
-- exists for manual initialization / inspection. Keep in sync with
-- CREATE_TABLE_SQL in scripts/crawl_bioprojects.py.
--
-- Apply with:
--   mysql -u <user> -p coexpressiondb < scripts/init_bioproject_meta.sql

USE coexpressiondb;

CREATE TABLE IF NOT EXISTS `bioproject_meta` (
  `accession`        VARCHAR(32)  NOT NULL,
  `source`           VARCHAR(8)   NOT NULL,
  `title`            TEXT,
  `description`      TEXT,
  `organism`         VARCHAR(128),
  `submitter`        VARCHAR(256),
  `submission_date`  VARCHAR(32),
  `publication_date` VARCHAR(32),
  `data_type`        VARCHAR(64),
  `sample_count`     INT,
  `study_type`       VARCHAR(64),
  `related_pubmed`   VARCHAR(256),
  `related_doi`      TEXT,
  `raw_json`         LONGTEXT,
  PRIMARY KEY (`accession`),
  KEY `idx_source` (`source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
