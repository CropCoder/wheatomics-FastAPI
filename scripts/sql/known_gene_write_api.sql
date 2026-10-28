-- ============================================================================
-- KnownGene 写接口 — 鉴权 / 审计表 DDL（MySQL 5.7.33，库 cloned_gene_db）
--
-- 执行方式（只需执行一次；root 权限，先备份再执行）：
--     sudo mysql < scripts/sql/known_gene_write_api.sql
--
-- 影响面：**只新增两张表，不修改 cloned_gene_tbl 任何列/索引/数据**，
-- 因此旧 CGI（cgi-py-RawScript/gene_search*.py、gene_submit*.py）与现有读
-- 接口（/api/genes/known/*）完全不受影响。
--
-- 表说明：
--   1) known_gene_api_keys：写接口 API Key。只存 sha256(raw_key) 摘要 + 展示
--      前缀，raw key 永不落库；支持多 key、scope、停用/过期、last_used_at。
--   2) known_gene_change_log：每次写操作的审计（before/after 完整行快照 +
--      changed_fields + actor + client_ip + reason）；create/update/bulk/delete
--      全记录，便于回溯与回滚定位。
--
-- 回滚（仅在需要撤销写接口时）：
--     DROP TABLE IF EXISTS known_gene_change_log;
--     DROP TABLE IF EXISTS known_gene_api_keys;
--   （审计表先删；只删表不触碰业务数据）
--
-- 注意：应用账号 wheatomics_user 无 DDL 权限，本文件必须由 MySQL root 执行；
-- 应用运行期只对该两表做 SELECT/INSERT/UPDATE（无需 DDL）。字符集统一
-- utf8mb4，与 JSON 审计快照中的 emoji/四字节字符兼容（本表与 cloned_gene_tbl
-- 的 utf8mb3 相互独立，不影响业务表行宽）。
--
-- 授权（若 wheatomics_user 是库级授权 `ON cloned_gene_db.*` 则无需额外操作；
-- 若是表级授权，root 需补下面两条，否则 API 返回 503「鉴权表未初始化」/写入失败）：
--   GRANT SELECT, INSERT, UPDATE ON cloned_gene_db.known_gene_api_keys
--     TO 'wheatomics_user'@'localhost';
--   GRANT SELECT, INSERT, UPDATE ON cloned_gene_db.known_gene_change_log
--     TO 'wheatomics_user'@'localhost';
--   FLUSH PRIVILEGES;
-- ============================================================================

SET NAMES utf8mb4;

USE cloned_gene_db;

-- ---------------------------------------------------------------------------
-- 1) API Key 表
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS known_gene_api_keys (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键；审计表 actor_key_id 引用',
  key_prefix VARCHAR(16) NOT NULL COMMENT '展示用前缀 = kgw_ + raw key 前 8 位（仅用于日志/对照，不可用于鉴权）',
  key_hash CHAR(64) NOT NULL COMMENT 'sha256(raw_key) 十六进制小写；raw key 永不落库',
  label VARCHAR(100) NOT NULL COMMENT '维护者/用途标签，如 tiantian-maintainer',
  scopes VARCHAR(64) NOT NULL DEFAULT 'write' COMMENT '逗号分隔 scope：write / admin（admin 隐含 write）',
  active TINYINT(1) NOT NULL DEFAULT 1 COMMENT '1=启用；0=已吊销',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  created_by VARCHAR(100) NOT NULL DEFAULT 'cli:known_gene_api_key' COMMENT '创建来源（CLI/人工）',
  expires_at DATETIME DEFAULT NULL COMMENT '过期时间；NULL=永不过期；过期后鉴权统一 401',
  last_used_at DATETIME DEFAULT NULL COMMENT '最近一次成功鉴权时间（尽力更新，失败不阻断请求）',
  note VARCHAR(255) DEFAULT NULL COMMENT '备注（key 用途/负责人/轮换说明）',
  PRIMARY KEY (id),
  UNIQUE KEY uq_kg_api_key_hash (key_hash),
  KEY idx_kg_api_key_prefix (key_prefix),
  KEY idx_kg_api_key_active (active, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='KnownGene 写接口 API Key（只存 sha256 摘要；v1 写接口鉴权）';

-- ---------------------------------------------------------------------------
-- 2) 写操作审计表
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS known_gene_change_log (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '审计主键（自增，按 id 倒序即时间倒序）',
  action VARCHAR(32) NOT NULL COMMENT '动作：create / update / delete / bulk_create / bulk_update',
  clone_id INT UNSIGNED DEFAULT NULL COMMENT 'cloned_gene_tbl.clone_id；delete 后仍保留以便追溯',
  gene_id VARCHAR(300) DEFAULT NULL COMMENT '操作对象 gene_id 快照（便于按基因检索）',
  gene_name VARCHAR(500) DEFAULT NULL COMMENT '操作对象 gene_name 快照',
  changed_fields TEXT COMMENT '逗号分隔的真实变化列名（update/bulk_update）；create/delete 为空',
  before_json LONGTEXT COMMENT '更新/删除前完整行 JSON（含长文本；date/Decimal 转字符串）',
  after_json LONGTEXT COMMENT '新增/更新后完整行 JSON（含长文本）',
  actor_key_id INT UNSIGNED DEFAULT NULL COMMENT '操作者 API Key id（CLI 维护操作为 NULL）',
  actor_label VARCHAR(100) DEFAULT NULL COMMENT '操作者标签：API key 的 label 或 cli:known_gene_admin',
  client_ip VARCHAR(64) DEFAULT NULL COMMENT 'request.client.host（Apache 反代场景为代理地址）',
  reason VARCHAR(255) DEFAULT NULL COMMENT '操作理由（delete/批量维护建议填写）',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '审计写入时间（与主表写同事务）',
  PRIMARY KEY (id),
  KEY idx_kgcl_clone_id (clone_id),
  KEY idx_kgcl_action_created (action, created_at),
  KEY idx_kgcl_gene_id (gene_id(64)),
  KEY idx_kgcl_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='KnownGene 写接口审计日志（before/after 完整行快照；写操作与主表同事务）';

-- ---------------------------------------------------------------------------
-- 3) 上线后自检（期望：两表存在、0 行、字符集 utf8mb4）
-- ---------------------------------------------------------------------------
SELECT TABLE_NAME, ENGINE, TABLE_COLLATION, TABLE_ROWS
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'cloned_gene_db'
  AND TABLE_NAME IN ('known_gene_api_keys', 'known_gene_change_log');

SELECT COUNT(*) AS api_keys_rows FROM known_gene_api_keys;
SELECT COUNT(*) AS change_log_rows FROM known_gene_change_log;
