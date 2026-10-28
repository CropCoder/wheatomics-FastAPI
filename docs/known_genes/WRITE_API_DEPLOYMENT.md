# KnownGene WRITE API — 上线部署与验收记录（2026-10-28）

> 需求：以后新增/修改基因可以通过受权限保护的接口完成，且能审计。
> 设计/使用文档：`docs/known_genes/WRITE_API.md`；维护流程：`MAINTENANCE.md` §13.1。
> 决策：B 方案（DB 多密钥 + 审计）、v1 仅新增+修改（无 API 删除）、批量 JSON/JSONL。

## 1. 部署结果

| 步骤 | 结果 | 证据 |
|---|---|---|
| DDL（root） | ✅ 两表创建成功，utf8mb4，0 行 | `known_gene_api_keys` / `known_gene_change_log`；`scripts/sql/known_gene_write_api.sql` |
| 代码上线 | ✅ 生产 HEAD `b3dcfbb`；`systemctl restart wheatomics-api` 成功 | 新路由已出现在 `/api/openapi.json` |
| 初始密钥 | ✅ 2 把：write（id=1, `kgw_dXtKw_SZ`）、admin（id=2, `kgw_YUA9ydfB`），有效期 1 年 | DB 只存 sha256（64 hex）；raw key 在服务器 600 文件与本地 `~/.config/lab-server/` |
| 自测 | ✅ `known_gene_write_selftest.py` **PASS=14 FAIL=0** | 含 401/403、dry-run、派生、缺字段/未知字段 422、PATCH 与 POST 别名、bulk |
| 生产落库冒烟 | ✅ create/duplicate/PATCH/bulk/upsert/审计/读接口回归全过 | 临时行 clone_id 1626–1628（APITEST_*）已用 admin CLI 删除（审计 id 6–8） |
| 清理后回归 | ✅ `/known/all` = **1420**、`/stats` total=1420、APITEST=0、已删行 404 | 业务数据与上线前一致 |
| 安全核查 | ✅ 服务日志中 raw key 出现次数 = **0/0**；DB 中仅 sha256；审计 8 条 | journalctl grep 全文 key、DB 查询 |
| 公网可用性 | ✅ whoami/changes/POST create/POST bulk/POST update 全 200；无 key=401；write key 查审计=403 | 经 `https://wheatomics.sdau.edu.cn` 实测 |
| 已知网络限制 | ⚠️ 公网 **PATCH 被校园网络边界丢弃**（`Empty reply from server`，服务器本机/直连 Apache·uvicorn 均 200）→ 提供等价 `POST /write/update/{clone_id}` 别名 | 已写入 WRITE_API.md §4.2 |

## 2. 写入路径验收（实际值）

| 操作 | 结果 |
|---|---|
| `POST /api/genes/known/write`（dry_run） | 200；派生 `species_primary=Triticum aestivum`、`chromosome=1A`、`publication_year=2026`；库不变 |
| 非法枚举 | 422（`detail.errors` 逐条中文错误） |
| 真写 | 200；clone_id=1626、audit_id=1；`/known/1626` 可读 |
| 重复新增（同 gene_id+gene_name） | 409 |
| `PATCH /write/1626` 与 `POST /write/update/1626`（dry_run） | 200；`changed_fields=['gene_phenotype','publication_year']`、audit_id=2 |
| PATCH 不存在 clone_id | 404 |
| `POST /write/bulk`（2 行 commit） | 200；created=2；total 1421→1423 |
| bulk `mode=upsert` | 200；updated=1 |
| `GET /write/changes`（admin） | 200；actions = `delete×3, bulk_update, bulk_create×2, update, create`；total=8 |
| admin CLI 删除测试行 | 每行写 `delete` 审计（before_json 完整快照），clone_id 不复用 |
| 读接口/统计 | `/known/all`、`/search?searchid=`、`/stats`、`/known/{id}` 全部正常，最终 total=1420 |

## 3. 密钥与权限现状

| label | scopes | 用途 | raw key 位置（600） |
|---|---|---|---|
| `shengwei-maintainer` | write | 日常新增/修改/批量 | 服务器 `/home/fei/known_gene_api_key_20261028.txt`；本地 `~/.config/lab-server/wheatomics_known_gene_write_key.txt` |
| `shengwei-admin` | admin（含 write） | 查审计 `/write/changes`、维护 | 服务器 `/home/fei/known_gene_admin_key_20261028.txt`；本地 `~/.config/lab-server/wheatomics_known_gene_admin_key.txt` |

- 管理命令（服务器）：`known_gene_api_key.py list / create / revoke --id N`；有效期 2027-10-28。
- 泄露处置：`revoke --id N` 后重建；旧 key 立即 401。
- 审计记录保留在 `known_gene_change_log`（本次冒烟 8 条，含 3 条 delete 快照，可作为审计演示；后续可按需清理/归档）。

## 4. 已知限制（文档已写）

1. 公网 PATCH 被边界拦截 → 用 `POST /write/update/{clone_id}`（等价）。
2. 限流是进程内计数（8 workers ≈ 8×60/min 的软上限），不是精确配额。
3. 未提供 API 删除（v1 决策）；删除走 `scripts/known_gene_admin.py delete`（带 confirm + 审计）。
4. `(gene_id, gene_name)` 无数据库唯一索引，极端并发新增有极小双写概率；重复检测在事务前完成，正常使用无影响。
5. 审计快照含完整长文本（每行约 20–40KB）；`/changes` 默认不返回快照，需要时配 `limit`。
6. `KNOWN_GENE_WRITE_ALLOW_IPS` 在 Apache 反代下看到的是反代地址，默认留空；真实 IP 限制建议放 Apache/边界层。

## 5. 日常使用

```bash
# 单条新增（公网，推荐先 dry_run）
curl -X POST https://wheatomics.sdau.edu.cn/api/genes/known/write \
  -H "Authorization: Bearer $(cat ~/.config/lab-server/wheatomics_known_gene_write_key.txt)" \
  -H "Content-Type: application/json" -d @gene.json        # gene.json 里 {"dry_run":true,"gene":{...}}

# 修改（公网用 POST 别名，避免 PATCH 被边界丢弃）
curl -X POST https://wheatomics.sdau.edu.cn/api/genes/known/write/update/1626 \
  -H "Authorization: Bearer $(cat ...write_key.txt)" -H "Content-Type: application/json" \
  -d '{"dry_run":false,"fields":{"gene_phenotype":"..."}}'

# 批量（Excel → extract.py JSONL → push，默认 dry-run）
python3 scripts/known_gene_push.py --jsonl scripts/known_genes_v2055/out/known_genes_v2056.jsonl --dry-run
python3 scripts/known_gene_push.py --jsonl ... --commit
```

**回滚**：只想撤掉写接口 → `git revert b3dcfbb`（或回退到 `25b9203`）+ restart；表可保留（读接口不依赖）。
彻底移除：`DROP TABLE known_gene_change_log; DROP TABLE known_gene_api_keys;`（只删新表，不动业务数据）。
