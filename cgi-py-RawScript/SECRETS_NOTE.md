# 关于本目录的密码占位符

本目录是早已停用的 CGI 旧后端存档。2026-08 安全清理时，其中所有硬编码的
数据库密码已被替换为 `<REDACTED>`（旧密码已轮换作废，见仓库根 MAINTENANCE.md）。

- 这些脚本不再运行，无需恢复真实密码；
- 若确需复活某个脚本，请从环境变量读取凭据：`os.environ["DB_PASSWORD"]`；
- `bash scripts/check_secrets.sh` 会防止旧密码再次进入代码库。
