-- Seed historical PV baseline.
-- Run AFTER init_visit_stats.sql has created the visit_stats table.
-- Estimates 7,000,000 PV from 2019-08-01 to 2026-07-03 (~2529 days,
-- ~2767/day). UV is left at 0 because we have no reliable estimate of
-- unique visitors from the lost historical data.
--
-- MySQL 5.x compatible: uses a stored procedure instead of CTE.
--
-- Apply once on the production server:
--
--   mysql -u root -p wheatomics_db < seed_visit_history.sql

USE wheatomics_db;

DELETE FROM visit_stats
WHERE visit_date >= '2019-08-01'
  AND visit_date <= CURDATE();

DROP PROCEDURE IF EXISTS seed_visit_history;

DELIMITER //
CREATE PROCEDURE seed_visit_history()
BEGIN
    DECLARE v_start DATE DEFAULT '2019-08-01';
    DECLARE v_end   DATE;
    DECLARE v_days  INT;
    DECLARE v_per   INT;
    DECLARE v_rem   INT;
    DECLARE v_cur   DATE;
    DECLARE v_pv    INT;

    SET v_end = CURDATE();
    SET v_days = DATEDIFF(v_end, v_start) + 1;
    SET v_per = FLOOR(7000000 / v_days);
    SET v_rem = 7000000 - v_per * v_days;
    SET v_cur = v_start;

    WHILE v_cur <= v_end DO
        SET v_pv = v_per;
        IF v_cur = v_end THEN
            SET v_pv = v_pv + v_rem;
        END IF;
        INSERT INTO visit_stats (visit_date, pv, uv) VALUES (v_cur, v_pv, 0);
        SET v_cur = DATE_ADD(v_cur, INTERVAL 1 DAY);
    END WHILE;
END //
DELIMITER ;

CALL seed_visit_history();
DROP PROCEDURE seed_visit_history;

SELECT COUNT(*) AS rows_inserted, SUM(pv) AS total_pv,
       MIN(visit_date) AS first_day, MAX(visit_date) AS last_day
FROM visit_stats;