# KnownGene v2056 上线操作手册（ROLLOUT）

> 对应计划 `KnownGenes_v2055_update_plan.md` §6；决策记录 `docs/known_genes/FREEZE_v2055.md`。
> 执行日期：2026-10-28（低峰期窗口）。所有步骤均有备份/回滚路径。

## 0. 上线前状态（记录基线）

- 生产 git HEAD：`5364ca3`（与本地一致）；服务 `wheatomics-api`（gunicorn）；重启后 8000 端口约 2–3 分钟恢复。
- 生产 DB：MySQL 5.7.33，`cloned_gene_db.cloned_gene_tbl` = 520 行，`MAX(clone_id)=526`，AUTO_INCREMENT=527。
- 数据源：v2056（md5 `1dbbeff77f8f53eb33e8ea133d32cb65`）→ JSONL（md5 `33e7f2881c073f41776238ad7ef189b2`，1420 行）。
- clone_id 映射预演：321/520 继承（61.73%）、199 孤儿、1099 新行 527…1625、AUTO_INCREMENT=1626。

## 1. 部署顺序（DDL → 代码 → 数据 → 前端 → News）

> 注意：后端新代码 SELECT 新列，**必须先执行 DDL**，否则 API 报 Unknown column。
> DDL 为纯追加（备份表/staging 表/新列），对旧代码与旧页面零影响。

### P0 备份（生产）

```bash
cd /var/www/FastAPI_backend_Port8000
curl -s http://127.0.0.1:8000/api/genes/known/all > /tmp/known_all_pre_v2056.json
mysqldump --single-transaction --no-tablespaces --default-character-set=utf8mb4 \
  cloned_gene_db cloned_gene_tbl > /var/backups/cloned_gene_tbl_pre_v2056_20261028.sql
# 记录：SELECT COUNT(*),MAX(clone_id) FROM cloned_gene_db.cloned_gene_tbl;
```

### P1 DDL（root；备份表 + staging 表 + 追加列）

```bash
sudo mysql < /var/www/FastAPI_backend_Port8000/scripts/sql/known_genes_v2055_ddl.sql
# 校验：columns=24、backup=520、staging=0、索引 4 个
sudo mysql -e "SELECT COUNT(*) FROM cloned_gene_db.cloned_gene_tbl; \
               SELECT COUNT(*) FROM cloned_gene_db.cloned_gene_tbl_backup_20261028;"
```

**闸门 A**：DDL 后目标表仍 520 行，旧 API 仍正常（结构只追加）。若 DDL 报错 → 执行 SQL 文件末尾的结构回滚块。

### P2 后端代码上线（git pull + 重启；此时数据仍 520 行）

```bash
# 本地：commit backend + scripts + docs → git push origin main && git push github main
# 生产：
rm -rf /var/www/FastAPI_backend_Port8000/scripts/known_genes_v2055   # 清掉临时上传的未跟踪脚本，避免 pull 冲突
cd /var/www/FastAPI_backend_Port8000 && git pull        # 或 bash auto_pull.sh + 看 git_update.log
sudo systemctl restart wheatomics-api
# 等 8000 端口恢复（2–3 min）：
for i in $(seq 1 40); do curl -s -o /dev/null http://127.0.0.1:8000/api/health && break; sleep 5; done
# 旧数据下冒烟：/known/all 520 条、新键存在但为 null、/stats 不报错、搜索正常
```

**闸门 A**：DDL 后表仍 520 行。

**闸门 B**：旧数据 520 行下 `/known/all`、`/known/search`、`/known/1`、`/known/stats` 全部 200 且结构正确；否则 `git checkout <旧commit>` + 重启回滚（数据未动，零风险）。

### P3 数据替换（应用账号，单事务）

```bash
cd /var/www/FastAPI_backend_Port8000
python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py --phase data --dry-run \
  --jsonl /tmp/known_genes_v2056.jsonl --report-dir /tmp/kg_migration
python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py --phase data --commit \
  --jsonl /tmp/known_genes_v2056.jsonl --report-dir /tmp/kg_migration
python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py --phase verify \
  --jsonl /tmp/known_genes_v2056.jsonl --report-dir /tmp/kg_migration
```

期望：1420 行、distinct clone_id=1420、max clone_id=1625、inherited=321、
23 species groups、38 chromosome labels、5 functional categories、3 research strategies。

**闸门 C**：verify PASS + API 冒烟（`/all` total=1420、`/known/1` 新字段、`/stats` 各分布与
`scripts/known_genes_v2055/out/api_fixtures/known_stats.json` 一致、`#` 未被改写、`/search?field=...` 正常）。
失败 → `--phase rollback --commit`（恢复 520 行）+ 排查。

### P4 前端上线（static 即时生效，无需重启）

```bash
# 本地：commit frontend → push；生产 git pull
cd /var/www/FastAPI_backend_Port8000 && git pull
# 生产多宽度检查（本机可跑，或服务器本机）：
bash scripts/spa_visual_check.sh http://127.0.0.1:8000/genes/ --label kg-prod-index \
  --click 'a[href="#tab-stats"]' --wait '#stats-content' --settle 1200
bash scripts/spa_visual_check.sh "http://127.0.0.1:8000/genes/detail.html?id=<映射保留的id>" \
  --label kg-prod-detail
# 公网复验：https://wheatomics.sdau.edu.cn/genes/ 与 /genes/detail.html?id=17
```

**闸门 D**：列表页/详情页 PASS（无横向溢出、无 JS 错误、对比度 floor 通过），搜索/分页/筛选/CSV/Stats 手测通过。
失败 → `git checkout` 旧静态文件（或 revert 前端 commit）+ pull（static 生效，无需重启）。

### P5 News 公告（生产静态文件，不在本仓库）

```bash
cp /var/www/html/V2.0/news.json /var/www/html/V2.0/news.json.bak-20261028
# 在数组最前面插入一条（date 2026-10-28，KnownGene 升级公告；title/url/journal/summary 见文末）
# 校验：python3 -c "import json;json.load(open('/var/www/html/V2.0/news.json'))"
```

**闸门 E**：`/V2.0/` 首页 News 与 `/help/news.html` 首条显示新公告；链接指向 `/genes/`。

### P6 观察与收尾

- 观察 30 min：`journalctl -u wheatomics-api -f`、`/api/track/stats`、`/all` 响应时间与大小（分页后首屏 50 条）；
- 保留 `cloned_gene_tbl_backup_20261028` + mysqldump ≥30 天；staging 表可保留或清理（root）；
- 更新 `MAINTENANCE.md`（KnownGene 数据更新流程一节）与 `CLAUDE.md`（如需要）；
- 提交 `docs/known_genes/ROLLOUT_v2056.md` 执行记录（本文件 + 实际结果）。

## 2. 回滚（任一闸门失败）

| 阶段 | 回滚动作 | 时间 |
|---|---|---|
| P1 后端代码 | `git checkout <旧commit>` → `git pull` → `sudo systemctl restart wheatomics-api` | 10–15 min（含重启） |
| P2 DDL | 执行 `scripts/sql/known_genes_v2055_ddl.sql` 末尾结构回滚块（DROP 新列/索引） | <5 min |
| P3 数据 | `python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py --phase rollback --commit` | <1 min |
| P4 前端 | `git checkout <旧commit> -- app/static/genes/` → `git pull` 或直接 checkout 旧静态文件（static 即时生效） | <2 min |
| P5 News | 恢复 `news.json.bak-20261028` | <1 min |

数据层最坏情况：`backup_20261028` 表或 `/var/backups/cloned_gene_tbl_pre_v2056_20261028.sql` 完整恢复旧 520 行。

## 3. News 公告文案（P5 使用）

```json
{
  "date": "2026-10-28",
  "title": "KnownGene expanded to 1,420 curated functional genes with new annotations.",
  "summary": "Recently, the KnownGene module was upgraded to a curated list of 1,420 cloned/functional genes from wheat and its Triticeae relatives. Each record now carries a reference genome ID, protein family, functional category, research strategy, experimental validation methods and full publication metadata. The module adds field-specific search, filtering, dataset statistics and a 19-column CSV export.",
  "url": "https://wheatomics.sdau.edu.cn/genes/",
  "journal": "Platform"
}
```
