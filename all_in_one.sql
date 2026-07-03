-- WheatOmics FastAPI visit-counter: 一次性建表 + 种子 + 授权
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

-- 3. 写入 7,000,000 PV 种子（均匀分布到 2019-08-01 ~ 今天）
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

-- 4. 给应用账号授权
GRANT SELECT, INSERT, UPDATE ON wheatomics_db.visit_stats TO 'wheatomics_user'@'localhost';
GRANT SELECT, INSERT, UPDATE ON wheatomics_db.visit_log  TO 'wheatomics_user'@'localhost';
FLUSH PRIVILEGES;

-- 5. 验证
SELECT COUNT(*) AS rows_inserted, SUM(pv) AS total_pv,
       MIN(visit_date) AS first_day, MAX(visit_date) AS last_day
FROM visit_stats;
