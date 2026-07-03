-- WheatOmics FastAPI visit-counter: 一次性建表 + 种子 + 授权
-- 兼容 MySQL 5.x（不支持 CTE），用存储过程生成种子
-- 在你当前 MySQL 会话里直接 source 这个文件即可

USE wheatomics_db;

-- 1. 建表
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

-- 2. 清掉可能存在的旧种子（2019-08-01 起）
DELETE FROM visit_stats
WHERE visit_date >= '2019-08-01'
  AND visit_date <= CURDATE();

-- 3. 用存储过程生成 7,000,000 PV 种子
--    2019-08-01 到今天 均匀分布；最后一天补余数保证总和精确
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
    DECLARE v_idx   INT DEFAULT 0;

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
        SET v_idx = v_idx + 1;
    END WHILE;
END //
DELIMITER ;

CALL seed_visit_history();
DROP PROCEDURE seed_visit_history;

-- 4. 给应用账号授权
GRANT SELECT, INSERT, UPDATE ON wheatomics_db.visit_stats TO 'wheatomics_user'@'localhost';
GRANT SELECT, INSERT, UPDATE ON wheatomics_db.visit_log  TO 'wheatomics_user'@'localhost';
FLUSH PRIVILEGES;

-- 5. 验证
SELECT COUNT(*) AS rows_inserted, SUM(pv) AS total_pv,
       MIN(visit_date) AS first_day, MAX(visit_date) AS last_day
FROM visit_stats;