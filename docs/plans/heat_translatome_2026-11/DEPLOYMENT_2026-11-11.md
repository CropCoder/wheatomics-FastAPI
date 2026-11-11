# Deployment record — 2026-11-11

WheatOmics **Phase 2 + 2.5**（热胁迫籽粒 translatome 模块，manifest/registry 驱动）已上线生产。

## 上线内容

| 项 | 内容 |
|---|---|
| 页面 | https://wheatomics.sdau.edu.cn/translatome/ |
| API | https://wheatomics.sdau.edu.cn/api/translatome/{datasets,meta,query,search,genes,tables,table/{id},dtgs,degs,download/...} |
| MCP | 新增 `list_translatome_datasets`、`query_translatome`、`list_translatome_dtgs`（server 共 31 tools） |
| 数据 | 中国春籽粒 5/10/15 DAA，CK vs 42 °C 1 h；RNA-seq/Ribo-seq FPKM + TE；60,125 基因、11,343 DTG、21,964 DEG；**02G+03G 双 ID** |
| 入口 | Tools 菜单 + 首页工具卡（`add_translatome_home_entry.py`）；`/agent.html` 文档同步 |

## 代码版本

- Gitee `origin/main`：`4b9827f`（translatome 模块）→ `9be43c2`（首页入口脚本）
- 服务器 `/var/www/FastAPI_backend_Port8000` HEAD：`9be43c2`
- 仓库内只含 `registry.json` + `manifest.json` + 脚本；`.tsv.gz` 在服务器
  `/var/www/data/translatome/chen2025_cs_grain_heat/`（`TRANSLATOME_DATA_DIR` 默认值）。

## 服务器变更

1. **数据资产**：`/var/www/data/translatome/chen2025_cs_grain_heat/{genes,dtg,deg}.tsv.gz`
   - 校验：`gzip -t` 全部 OK；行数 60,126 / 11,344 / 21,965（含表头）；sha256 与本机一致。
2. **Apache**（`/etc/apache2/sites-enabled/000-default.conf` 与 `000-default-ssl.conf`）：
   ```apache
   ProxyPass /translatome http://127.0.0.1:8000/translatome
   ProxyPassReverse /translatome http://127.0.0.1:8000/translatome
   ```
   备份：`/var/www/data/translatome/_deploy_backup_20261111_161251/`
3. **API**：`sudo systemctl restart wheatomics-api`（gunicorn 约 1–2 分钟完成 worker 启动，期间站点 API 短暂 503 属正常）
4. **docroot**：
   - `/var/www/html/agent.html` 更新（31 tools，备份 `agent.html.bak-20261111_161519`）
   - `/var/www/html/index.html` 与 `/var/www/html/V2.0/index.html` 增加 Translatome 菜单项+工具卡
     （备份 `*.bak-20261111_162013`）

## 上线后验证（2026-11-11 16:20 CST）

- `GET /` 200；`/translatome/` 200；`/api/translatome/datasets` 200 且 `assets_ready: true`
- `GET /api/translatome/query?gene_ids=TraesCS1A03G0004000` → 返回 02G=TraesCS1A02G001800、TE CK=7.47 / HS=14.41
- `GET /api/translatome/dtgs?stage=15DAA&direction=up` → total=3,302
- `GET /api/translatome/download/chen2025_cs_grain_heat/matrix` → 6,441,521 bytes
- MCP `initialize` + `tools/list`：**31 tools**，含 3 个 translatome 工具
- `scripts/spa_visual_check.sh https://…/translatome/?gene=…`：390 / 1024 / 1440 宽度 **PASS**，0 溢出/0 JS 错误
- `systemctl is-active wheatomics-api` = active；16:12 后日志无 error/traceback

## 回滚

| 层 | 操作 |
|---|---|
| 代码 | `cd /var/www/FastAPI_backend_Port8000 && git reset --hard 4b9827f~1`（或回到部署前 HEAD `0f8905c`）→ `sudo systemctl restart wheatomics-api` |
| Apache | `sudo cp /var/www/data/translatome/_deploy_backup_20261111_161251/000-default*.conf /etc/apache2/sites-enabled/` → `sudo apache2ctl configtest && sudo systemctl reload apache2` |
| docroot | 复制对应 `.bak-20261111_*` 回原文件 |
| 数据 | 删除 `/var/www/data/translatome/` 即可（不影响其他模块）；仓库内 manifest/registry 可保留 |

## 仍待处理

- **授权**：GB 2025 为 CC BY-NC-ND 4.0、PlCell 非 OA；页面已标注引用/license，但正式对外传播建议取得通讯作者书面同意（模板见 `PLAN.md` 附录 B）。
- 数据集状态 `prototype`；确认后可在 `registry.json` 改为 `public` 并更新页面。
- 后续新数据集：按 `PHASE2_EXTENSIBILITY.md` §6 加文件夹 + manifest + registry 一行，`sync_assets.sh` 上传资产即可（不改代码）。

## Post-deploy copy fix (2026-11-11 evening)

- Example chips on `/translatome/` no longer say "TE-rich" (TE = translation
  efficiency; the wording could be misread as transposable element). The chips
  now show plain gene IDs (02G/03G): `TraesCS1A02G001800`, `TraesCS1A03G0004000`,
  `TraesCS1A02G000300`, `TraesCS5A02G391700`.
- Changed `app/services/data/translatome/chen2025_cs_grain_heat/manifest.json`
  (`examples[].label`) and the builder output in
  `scripts/heat_translatome/build_data.py`; API restarted so the cached manifest
  is reloaded. Screenshots refreshed.

## Delta display clarification (2026-11-11 evening)

The per-stage contrast column was labelled `Δ HS/CK`, which could be read as a
percentage. It is a **log2 fold change** — e.g. `-0.13` means log2(HS/CK) =
-0.13, i.e. a **-8.5%** change, not -13%. The table now:

- labels the column `Δ log2 (HS/CK)`;
- shows the converted percent below each log2FC value
  (`percent = (2^Δlog2 − 1) × 100%`);
- adds a footnote explaining that the percentage is a conversion, not the log2
  value read as a percent.

No API change; this is a static frontend update (no restart needed).
