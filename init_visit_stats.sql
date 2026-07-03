-- WheatOmics FastAPI visit-counter schema.
-- The `track` router assumes these tables already exist and does NOT
-- run CREATE TABLE itself, because `wheatomics_user` does not have
-- CREATE privileges in `wheatomics_db` (DB_LITERATURE).
--
-- Apply once on the production server as a user with CREATE privilege:
--
--   mysql -u root -p wheatomics_db < init_visit_stats.sql
--
-- Or via a privileged user:
--
--   mysql -u admin -p wheatomics_db < init_visit_stats.sql

CREATE TABLE IF NOT EXISTS visit_stats (
    visit_date DATE NOT NULL PRIMARY KEY,
    pv INT NOT NULL DEFAULT 0,
    uv INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS visit_log (
    visitor_hash CHAR(32) NOT NULL,
    visit_date DATE NOT NULL,
    last_seen DATETIME NOT NULL,
    PRIMARY KEY (visitor_hash, visit_date),
    INDEX idx_last_seen (last_seen)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;