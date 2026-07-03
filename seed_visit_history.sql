-- Seed historical PV baseline.
-- Run AFTER init_visit_stats.sql has created the visit_stats table.
-- Estimates 7,000,000 PV from 2019-08-01 to 2026-07-03 (~2529 days,
-- ~2767/day). UV is left at 0 because we have no reliable estimate of
-- unique visitors from the lost historical data.
--
-- Apply once on the production server:
--
--   mysql -u root -p wheatomics_db < seed_visit_history.sql
--
-- Or run inline:
--   mysql -u root -p wheatomics_db
--   source /path/to/seed_visit_history.sql;

USE wheatomics_db;

-- Idempotent: clear existing baseline rows first so re-running gives the
-- same total (avoid double-counting if seed is run more than once).
DELETE FROM visit_stats
WHERE visit_date >= '2019-08-01'
  AND visit_date <= CURDATE();

-- Generate one row per day from 2019-08-01 to today, distributing
-- 7,000,000 PV evenly. We use a recursive CTE because MySQL 8 supports it.
-- Per-day baseline = FLOOR(7_000_000 / day_count); remainder gets added
-- to the final day so the total is exact.

INSERT INTO visit_stats (visit_date, pv, uv)
WITH RECURSIVE dates(d) AS (
    SELECT DATE('2019-08-01')
    UNION ALL
    SELECT DATE_ADD(d, INTERVAL 1 DAY) FROM dates
    WHERE d < CURDATE()
),
day_count AS (
    SELECT COUNT(*) AS n FROM dates
)
SELECT
    d,
    FLOOR(7000000 / day_count.n) + CASE WHEN d = CURDATE()
        THEN 7000000 - FLOOR(7000000 / day_count.n) * day_count.n
        ELSE 0 END,
    0
FROM dates, day_count;

-- Verify
SELECT
    COUNT(*)               AS rows_inserted,
    SUM(pv)                AS total_pv,
    MIN(visit_date)        AS first_day,
    MAX(visit_date)        AS last_day
FROM visit_stats;