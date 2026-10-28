# KnownGene 写接口（WRITE API）使用与运维文档

> 版本：v1（2026-10-28）｜实现：`app/api/routers/gene_write.py` +
> `app/services/known_gene_ingest.py` + `app/core/known_gene_auth.py`
> ｜DDL：`scripts/sql/known_gene_write_api.sql`
>
> 目标：让维护者在**不改代码、不碰数据库命令行**的前提下，通过受权限保护的
> HTTP API 新增/更新 KnownGene（`cloned_gene_db.cloned_gene_tbl`），且每次写操作
> 都有可追溯的审计记录。读接口（`/api/genes/known/*`）与旧 CGI 完全不受影响。

## 目录

1. [快速开始（5 分钟）](#1-快速开始5-分钟)
2. [鉴权模型](#2-鉴权模型)
3. [字段规格](#3-字段规格)
4. [端点参考](#4-端点参考)
5. [错误码](#5-错误码)
6. [审计与回滚](#6-审计与回滚)
7. [密钥轮换 / 泄露处置](#7-密钥轮换--泄露处置)
8. [维护者批量更新流程（Excel → API）](#8-维护者批量更新流程excel--api)
9. [部署与生产 smoke 清单](#9-部署与生产-smoke-清单)
10. [限制与已知风险](#10-限制与已知风险)

---

## 1. 快速开始（5 分钟）

### 1.1 建表（只需一次，MySQL root）

```bash
# 生产节点；root 免密：sudo mysql
sudo mysql < scripts/sql/known_gene_write_api.sql

# 自检：应看到 known_gene_api_keys / known_gene_change_log 两表，0 行，utf8mb4
sudo mysql -e "USE cloned_gene_db; SHOW TABLES LIKE 'known_gene_%';
  SELECT COUNT(*) FROM known_gene_api_keys; SELECT COUNT(*) FROM known_gene_change_log;"
```

> ⚠️ 该 DDL **只新增两张表**，不修改 `cloned_gene_tbl` 任何列/索引/数据，旧 CGI 与
> 读接口零影响。回滚只需 `DROP TABLE known_gene_change_log; DROP TABLE known_gene_api_keys;`。
>
> 权限：若 `wheatomics_user` 是库级授权（`ON cloned_gene_db.*`）则无需额外操作；
> 若是表级授权，root 需补 `GRANT SELECT, INSERT, UPDATE ON cloned_gene_db.known_gene_api_keys`
> 与 `... known_gene_change_log` 两条，然后 `FLUSH PRIVILEGES`。

### 1.2 创建 API Key（应用账号即可，无需 root）

```bash
cd /var/www/FastAPI_backend_Port8000   # 或本地仓库根目录
python3 scripts/known_gene_api_key.py create \
    --label tiantian-maintainer \
    --scopes write \
    --expires-days 365 \
    --out-file /home/fei/known_gene_api_key_20261028.txt

# raw key（kgw_ 开头 52 字符）只显示一次！文件权限自动 600。
# 另行创建一把 admin key（可查审计，也可写）：
python3 scripts/known_gene_api_key.py create --label auditor --scopes admin --out-file /home/fei/known_gene_admin_key.txt

# 查看 / 吊销
python3 scripts/known_gene_api_key.py list
python3 scripts/known_gene_api_key.py revoke --id 3
```

### 1.3 部署代码

`main.py` 已注册 `gene_write` router；`app/core/config.py` 新增 3 个配置项（默认值即可）。
代码上线后需重启 API（Python 改动）：

```bash
git pull && sudo systemctl restart wheatomics-api
sudo systemctl status wheatomics-api
```

### 1.4 自测（只读 + dry-run，不写库）

```bash
KNOWN_GENE_API_KEY=$(cat /home/fei/known_gene_api_key_20261028.txt) \
python3 scripts/known_gene_write_selftest.py --base-url https://wheatomics.sdau.edu.cn
```

### 1.5 第一个写请求（dry-run → 真写）

```bash
KEY=$(cat /home/fei/known_gene_api_key_20261028.txt)
BASE=https://wheatomics.sdau.edu.cn

# ① dry-run：只校验，不落库
curl -sS -X POST "$BASE/api/genes/known/write" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"dry_run": true, "gene": {
        "gene_id": "TraesCS7B03G0166400", "gene_name": "TaERF1-B",
        "reference_genome_id": "TraesCS7B03G0166400",
        "gene_species": "Triticum aestivum (bread wheat)",
        "chrom_pos": "Refv1.0 chr7B:112.264-112.266Mb",
        "gene_phenotype": "Drought tolerance",
        "functional_category": "Biotic & Abiotic Stress",
        "research_strategy": "Reverse genetics",
        "key_result": "Overexpression improves drought tolerance.",
        "paper_doi": "10.1007/s11103-007-9237-9"}}' | python3 -m json.tool

# ② 确认返回的 record（species_primary/chromosome/publication_year 派生正确）后，
#    同一请求把 "dry_run": true 改成 false 即落库。
```

成功响应（落库）：

```json
{
  "success": true,
  "message": "新增成功",
  "timestamp": "2026-10-28T19:30:00+00:00",
  "data": {
    "dry_run": false,
    "clone_id": 1626,
    "audit_id": 1,
    "record": { "...": "与 GET /api/genes/known/1626 完全同构" },
    "warnings": []
  }
}
```

---

## 2. 鉴权模型

### 2.1 请求头

```http
Authorization: Bearer kgw_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

兼容旧式服务端调用：

```http
X-API-Key: kgw_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

两种头同时出现时以 `Authorization` 为准；都没有 / 格式错误 → **401**。

### 2.2 Key 在数据库里怎么存

| 列 | 内容 |
|---|---|
| `key_hash` | `sha256(raw_key)` 的 64 位十六进制摘要（唯一索引）。**raw key 永不落库** |
| `key_prefix` | `kgw_` + raw key 前 8 位，仅用于人眼对照/日志定位 |
| `scopes` | `write`（可写）/ `admin`（可写 + 可查审计）；admin 隐含 write |
| `active` | 1=启用，0=吊销 |
| `expires_at` | NULL=永不过期；过期后统一 401 |
| `last_used_at` | 每次成功鉴权尽力更新（失败只记 warning，不阻断请求） |

生成算法（`app/core/known_gene_auth.py::generate_api_key`）：
`kgw_` + `secrets.token_urlsafe(36)`（48 位 url-safe 字符）。
校验时只计算 sha256 后按唯一索引查行，**应用层不比较明文**（无可计时比较泄露）。

### 2.3 失败语义

| 场景 | HTTP | 说明 |
|---|---|---|
| 没带 key / 头格式不是 `Bearer <token>` | 401 | |
| key 不存在 / 已吊销 / 已过期 | 401 | **统一文案，不区分原因**（原因只进服务端日志，日志里只有 key_prefix） |
| scope 不足（如 write key 访问 `/changes`） | 403 | 响应回显当前 scopes |
| 来源 IP 不在 `KNOWN_GENE_WRITE_ALLOW_IPS` | 403 | 默认配置为空=不限制 |
| 超过每 key 每分钟限流 | 429 | 响应带 `Retry-After` |
| 鉴权表未建 / DB 不可用 | 503 | 提示先执行 DDL |

**日志纪律**：服务端只记录 `key_id` / `label` / `key_prefix` / `client_ip` / 路径，
绝不记录 raw key、`Authorization` 头或 key 哈希；响应体也不回显 key。

### 2.4 限流

- 每 key **60 次/分钟**（`KNOWN_GENE_WRITE_RATE_PER_MINUTE`，0=关闭），滑动窗口；
- 进程内 `dict[key_id] -> deque`，**每个 gunicorn worker 各自计数**（生产 8 worker
  ⇒ 实际允许约 8×60 次/分钟）。这是为不引入 Redis 的取舍，用于防脚本误打，不做
  计费级精确限流。

### 2.5 请求体大小

写端点上限 **2MB**（`2 * 1024 * 1024`）：先看 `Content-Length`（超过直接 413），
无该头（chunked）时读取后按实际长度再判。批量一次最多 **500 行**
（`KNOWN_GENE_WRITE_BATCH_LIMIT`，见 §4.3）。

### 2.6 新增的配置项（`app/core/config.py`）

```dotenv
KNOWN_GENE_WRITE_BATCH_LIMIT=500        # 批量行数上限
KNOWN_GENE_WRITE_RATE_PER_MINUTE=60     # 每 key 每分钟写请求上限；0=关闭
KNOWN_GENE_WRITE_ALLOW_IPS=             # 逗号分隔 IP 白名单；空=不限制
```

> **IP 白名单生产注意**：生产 API 在 Apache 反代之后，`request.client.host` 是
> Apache 的 `127.0.0.1` 而不是真实客户端 IP。因此默认留空（不限制）；若确需限制，
> 请在 Apache/防火墙层做，而不是在这里填公网 IP。

---

## 3. 字段规格

`cloned_gene_tbl` v2056 共 24 列；写接口可写 **23 列**（`clone_id` 自增，不接收）。
字段分三类：**必填**、**可选**、**服务端派生**。

### 3.1 必填（新增时）

| API 字段 | DB 列 | 长度上限 | 说明 |
|---|---|---|---|
| `gene_id` | gene_id | 300 | 基因 ID。允许字符比读接口宽（读接口 `ensure_gene_like` 要求 `^[A-Za-z0-9_.:-]+$`；若含其它字符会 warning，详情用 clone_id 访问） |
| `gene_name` | gene_name | 500 | 基因名 |
| `reference_genome_id` | reference_genome_id | 100 | 参考基因组 ID（IWGSC v3 03G / HORVU / GenBank…） |
| `gene_species` | gene_species | 1000 | 物种原文（可含材料长描述；服务端据此派生 species_primary） |
| `chrom_pos` | chrom_pos | 500 | 形如 `Refv1.0 chr7B:112.264-112.266Mb`；服务端据此派生 chromosome |
| `gene_phenotype` | gene_phenotype | 2000 | 性状/表型长文本（`; ` 分隔多个性状） |
| `functional_category` | functional_category | 64 | **受控 5 值**，见 §3.4 |
| `research_strategy` | research_strategy | 32 | **受控 3 值**，见 §3.4 |
| `key_result` | key_result | 15000 | 关键结果（≤500 词英文） |

另外：**`paper_doi` 与 `paper_title` 至少提供一个**（可都多值）。

### 3.2 可选

| API 字段 | DB 列 | 上限 | 说明 |
|---|---|---|---|
| `paper_title` | paper_title | TEXT（软上限 65535） | 多值：list 或 `"; "` 字符串；存 `###` |
| `paper_doi` | paper_doi | TEXT（软上限 65535） | 多值；非标准 DOI 形式只 warning 不拒绝 |
| `publication_year` | publication_year | YEAR(4) | int；不传且传入 `publication_years` 时自动取最早年份 |
| `publication_years` | publication_years | 64 | 多值原始年份；存 `###`；`publication_year=min(4 位年份)` |
| `protein_family` | protein_family | TEXT | 蛋白家族 - 功能描述 |
| `validation_method` | validation_method | TEXT | 验证方法多值（list 自动用 `; ` 连接） |
| `cloning_method` | cloning_method | 255 | 克隆方法（自由文本） |
| `cloning_method_description` | cloning_method_description | TEXT | 克隆方法描述 |
| `function_description` | function_description | TEXT | 功能描述 |
| `author` | author | 100 | 缺省 `WheatOmics API`（DB NOT NULL；更新时不能改为空） |
| `author_mail` | author_mail | 200 | 缺省 `shengweima@icloud.com`（同上） |
| `submission_date` | submission_date | — | `YYYY-MM-DD`；缺省今天 |

### 3.3 服务端派生（可显式覆盖，会校验）

| 字段 | 派生规则 |
|---|---|
| `species_primary` | ① `gene_species` 原文整串命中 296 条映射（`app/services/data/known_gene_species_map.json`）→ 用映射值；② 取首个学名（截断到第一个 `(`/`;`，去掉 `cv.` 材料描述/命名人缩写）→ 按 23 个受控学名 + 英文常用名 + 同义名 + 属名缩写归一；③ 仍不命中 → 学名回退 + warning（提示补映射）。显式传入时必须属于 23 个受控学名。 |
| `chromosome` | 优先 `chr\s*([0-9]+[A-Za-z]{0,2})`，其次 `\b([0-9]+[A-Za-z]{0,2})\s*:`；字母 token 大写（`7a→7A`），纯数字存 `chr<N>`（`chr54`）。解析失败 → 空 + warning。 |
| `publication_year` | `int(min(publication_years 中的 4 位年份))`；只传 `publication_year` 时 `publication_years=该年份`。 |
| `phenotype_brief` / `genome_ref` | **不落库**，由读接口从 `gene_phenotype` / `chrom_pos` 实时派生（写接口返回的 record 已包含）。 |

### 3.4 受控词表

```text
functional_category（5 值）:
  Biotic & Abiotic Stress / Quality & Yield / Morphology & Domestication /
  Physiology & Metabolic Processes / Reproduction & Phenology

research_strategy（3 值）:
  Reverse genetics / Forward genetics / Not reported

cloning_method：自由文本（≤255），v2056 实测 8 种组合值，不强制枚举。
paper_title / paper_doi / publication_years：多值位置一一对应，DB 用 ### 连接。
```

### 3.5 多值字段写法（title / doi / year）

三种等价写法（按位置对齐，缺失位置由调用方补空串）：

```json
{"paper_title": ["Title A", "Title B"], "paper_doi": ["10.1/a", "10.1/b"], "publication_years": ["2008", "2024"]}
{"paper_title": "Title A; Title B", "paper_doi": "10.1/a; 10.1/b", "publication_years": "2008; 2024"}
{"paper_title": "Title A###Title B", "...": "（含 ### 时按 ### 拆，不按 ; 拆，避免误伤标题内的分号）"}
```

读接口会按位置把 `references[]` 还原为 `[{doi,title,year}, ...]`。

### 3.6 默认值 / 归一化小结

- `author` 默认 `WheatOmics API`（**不是**表格导入用的 `WheatOmics curation`，便于按来源区分）；
- `author_mail` 默认 `shengweima@icloud.com`；`submission_date` 默认今天；
- 文本统一：去首尾空白、`\r\n`→`\n`、拒绝 NUL；空字符串等价于 NULL；
- 所有长度按**字符数**校验（与 DB varchar 的字符语义一致）；TEXT 列 65535 字符软上限。

---

## 4. 端点参考

统一前缀：`/api/genes/known/write`（OpenAPI 文档：`/api/docs` → tag `Known Genes (write)`）。
成功响应统一 `{"success": true, "message": ..., "timestamp": ..., "data": ...}`。

### 4.1 `POST /api/genes/known/write` — 新增

- **权限**：`write`
- **请求体**（推荐 `gene` 嵌套；也支持裸对象）：

```json
{"dry_run": false, "gene": {
  "gene_id": "TraesCS7B03G0166400", "gene_name": "TaERF1-B",
  "reference_genome_id": "TraesCS7B03G0166400",
  "gene_species": "Triticum aestivum (bread wheat)",
  "chrom_pos": "Refv1.0 chr7B:112.264-112.266Mb",
  "gene_phenotype": "Drought tolerance",
  "functional_category": "Biotic & Abiotic Stress",
  "research_strategy": "Reverse genetics",
  "key_result": "Overexpression improves drought tolerance.",
  "paper_doi": "10.1007/s11103-007-9237-9",
  "publication_year": 2007
}}
```

- **dry_run=true**：只校验 + 查重，返回 `{"dry_run": true, "record": <23 列完整记录>, "warnings": [...]}`，不落库；
  不传 `dry_run` 时默认 **false（直接写入）**——所以生产操作请显式带 `"dry_run": true` 先预演；
- **成功**：`{"dry_run": false, "clone_id": 1626, "audit_id": 1, "record": <detail>, "warnings": [...]}`；
- **错误**：422 字段校验失败（`detail.errors` 逐条中文）、409 (gene_id,gene_name) 重复、413 过大、401/403/429。

```bash
curl -sS -X POST "$BASE/api/genes/known/write" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"dry_run": true, "gene": {...}}'
```

### 4.2 `PATCH /api/genes/known/write/{clone_id}` — 更新（另有 POST 别名）

> ⚠️ 公网入口提示：`wheatomics.sdau.edu.cn` 前面的校园网络边界会丢弃 **PATCH** 请求
> （curl 表现为 `Empty reply from server`；服务器本机直连 Apache/uvicorn 验证 PATCH 正常）。
> 因此同功能提供 **`POST /api/genes/known/write/update/{clone_id}`** 别名，公网调用请用它；
> PATCH 仍保留，供服务器本机/内网脚本与标准 HTTP 客户端使用。两者请求体、响应、错误码完全一致。

- 规范方法：`PATCH /api/genes/known/write/{clone_id}`
- 公网安全别名：`POST /api/genes/known/write/update/{clone_id}`

- **权限**：`write`
- **请求体**：`{"dry_run": false, "fields": {...}}`（或裸字段对象；`fields`/`gene` 均可）
- **语义**：只更新传入字段；`gene_species`→重算 `species_primary`、`chrom_pos`→重算
  `chromosome`、`publication_years`→重算 `publication_year`；`publication_year` 单独传
  只改标量年份、保留原多值年份原文；
- 更新前 `SELECT ... FOR UPDATE` 锁行；clone_id 不存在 → 404；
- 与库中值完全一致 → 不执行 UPDATE、不写审计，返回 `changed_fields: []` 与
  message「无字段变化，未写入」；
- **成功**：`{"dry_run": false, "clone_id": N, "audit_id": M, "changed_fields": [...], "record": {...}}`；
  dry-run 返回合并后的 record + 预计 `changed_fields`。

```bash
curl -sS -X PATCH "$BASE/api/genes/known/write/1626" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"fields": {"gene_phenotype": "Drought tolerance; Salt tolerance",
                  "publication_years": "2007; 2024"}}'
```

### 4.3 `POST /api/genes/known/write/bulk` — 批量

- **权限**：`write`
- **请求体**：

```json
{"rows": [{...}, {...}], "mode": "upsert", "dry_run": true}
```

| 参数 | 说明 |
|---|---|
| `rows` | 1–500 个 gene 对象；每行必须是**完整记录**（必填字段齐全，同 4.1） |
| `mode` | `upsert`（默认；按 (gene_id,gene_name) 匹配 → 更新，否则新增）/ `insert_only`（任一已存在则整批拒绝） |
| `dry_run` | **默认 true**；确认预演结果后显式传 false 才落库 |

- **非 dry-run 全有或全无**：任一行校验失败 → 422 + 每行错误，**整批不写库**；
- **dry-run** 返回每行 `would_create` / `would_update` / `error`；
- **dry_run 默认值为 true**（批量比单条更危险，默认先预演）；
- **成功**：`{"created": 0, "updated": 2, "errors": 0, "dry_run": false, "total": 2,
  "results": [{"row": 1, "status": "updated", "clone_id": 12, "audit_id": 5, "changed_fields": [...]}],
  "audit_ids": [5, 6]}`；
- 批内 (gene_id,gene_name) 重复 → 后出现的行为错误；
- 逐行审计：`bulk_create` / `bulk_update`（同一事务）。

```bash
curl -sS -X POST "$BASE/api/genes/known/write/bulk" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d @batch.json    # {"rows":[...],"mode":"upsert","dry_run":true}
```

### 4.4 `GET /api/genes/known/write/changes` — 审计查询

- **权限**：`admin`
- 参数：`clone_id`、`action`（create/update/delete/bulk_create/bulk_update）、
  `since`（`YYYY-MM-DD` 或 ISO 8601）、`limit`（默认 50，1–500）、`offset`、
  `include_snapshot`（默认 false；true 时返回 before/after 完整行快照）
- 响应：`{"total": N, "limit": 50, "offset": 0, "records": [{
  "id": 1, "action": "update", "clone_id": 1626, "gene_id": "...", "gene_name": "...",
  "changed_fields": ["gene_phenotype", "publication_year"],
  "actor_key_id": 1, "actor_label": "tiantian-maintainer",
  "client_ip": "127.0.0.1", "reason": null, "created_at": "2026-10-28T19:30:00"}]}`

```bash
curl -sS "$BASE/api/genes/known/write/changes?clone_id=1626&limit=10" \
  -H "Authorization: Bearer $ADMIN_KEY"
# 看完整快照（体积大，按需）：
curl -sS "$BASE/api/genes/known/write/changes?action=update&include_snapshot=true&limit=5" \
  -H "Authorization: Bearer $ADMIN_KEY"
```

### 4.5 `GET /api/genes/known/write/whoami` — 当前 Key 信息

- **权限**：任意有效 key（write/admin 均可）
- 响应：`{"key_id": 1, "label": "tiantian-maintainer", "scopes": ["write"],
  "expires_at": "2027-10-28T00:00:00", "last_used_at": "2026-10-28T19:30:00"}`
- **不含** key 本身/哈希。

```bash
curl -sS "$BASE/api/genes/known/write/whoami" -H "Authorization: Bearer $KEY"
```

---

## 5. 错误码

| HTTP | 场景 | 响应形态 |
|---|---|---|
| 400 | 请求体不是 JSON object / `dry_run` 非布尔 / 嵌套与顶层字段混用 / `since` 非法（部分为 422） | `{"detail": "<中文>"}` |
| 401 | 缺 key / Bearer 格式错 / key 不存在 / 已吊销 / 已过期 | `{"detail": "无效的 API Key"}`（统一文案） |
| 403 | scope 不足 / IP 不在白名单 | `{"detail": "<中文 + 当前 scopes>"}` |
| 404 | PATCH 的 clone_id 不存在 | `{"detail": "KnownGene 不存在: clone_id=N"}` |
| 409 | 新增/insert_only 批量命中已存在 (gene_id,gene_name) | `{"detail": "<中文 + 现有 clone_id>"}` |
| 413 | 请求体 >2MB / 批量 >500 行 | `{"detail": "<中文>"}` |
| 422 | 业务字段校验失败（必填缺失/枚举非法/超长/论文全空/未知字段） | `{"detail": {"errors": [...], "warnings": [...]}}` |
| 429 | 超过每 key 每分钟限流 | `{"detail": "<中文>"}` + `Retry-After` 头 |
| 503 | 鉴权表未初始化 / DB 不可用 | `{"detail": "<中文 + 处理办法>"}` |

> 422 的 `detail.errors` 是**逐条**中文错误，便于一次性修正全部字段；`warnings`
> 是"已接受但需注意"的提示（如物种未命中映射、gene_id 字符集偏宽、年份不一致）。
> FastAPI 自身的路径/查询参数类型错误（如 clone_id 非数字）也返回 422，形态由
> `main.py` 的全局 handler 统一为 `{"success": false, "error": "Validation error", ...}`。

---

## 6. 审计与回滚

### 6.1 审计表 `known_gene_change_log`

| 列 | 说明 |
|---|---|
| `action` | `create` / `update` / `delete` / `bulk_create` / `bulk_update` |
| `clone_id` | 操作的 clone_id（delete 后仍保留，便于追溯） |
| `gene_id` / `gene_name` | 操作对象快照 |
| `changed_fields` | 真实变化的列名，逗号分隔（create/delete 为空） |
| `before_json` | 更新/删除前**完整行** JSON（含长文本；date/Decimal 转字符串） |
| `after_json` | 新增/更新后完整行 JSON |
| `actor_key_id` / `actor_label` | 操作者 API key；CLI 维护操作为 NULL / `cli:known_gene_admin` |
| `client_ip` | `request.client.host`（反代场景为代理地址） |
| `reason` | 操作理由（delete 必填；API 写操作可选） |
| `created_at` | 审计写入时间 |

**关键保证**：审计 INSERT 与主表 INSERT/UPDATE/DELETE 使用**同一个 cursor 和同一个
事务**（`with mysql_cursor(...)` 成功才 commit，异常自动 rollback），因此不存在
"写了业务数据但没审计"或"有审计但业务没写"的中间态。

### 6.2 数据回滚

v1 API 没有删除端点，但支持 PATCH 回改。典型回滚步骤：

```bash
# ① 查审计，找到变更前的完整行
ADMIN=...  # admin key
curl -sS "$BASE/api/genes/known/write/changes?clone_id=1626&include_snapshot=true&limit=1" \
  -H "Authorization: Bearer $ADMIN" > /tmp/change_1626.json

# ② 从 before_json 里挑出要恢复的字段，用 PATCH 回写（或整行回写）
curl -sS -X PATCH "$BASE/api/genes/known/write/1626" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"fields": {"gene_phenotype": "<before_json 中的原值>"}}'
```

- 新增导致的数据错误：用维护 CLI 删除（见 §6.3），或在库内直接修正后补审计；
- 大面积回滚：恢复 `cloned_gene_tbl` 的备份（`cloned_gene_tbl_backup_20261028` 或
  `/home/fei/backup/cloned_gene_tbl_pre_v2056*.sql`），API 无写缓存，恢复即生效；
- 代码回滚：`git revert <commit>` + `sudo systemctl restart wheatomics-api`。

### 6.3 删除（仅维护 CLI，API 不暴露）

```bash
# 预演：只查行并校验 --confirm
python3 scripts/known_gene_admin.py delete --clone-id 1625 \
    --confirm TraesCS5A03G0935400 --reason "重复行，合并到 clone_id=12" --dry-run

# 真删：事务内写 delete 审计（before_json=完整行）→ DELETE → commit
python3 scripts/known_gene_admin.py delete --clone-id 1625 \
    --confirm TraesCS5A03G0935400 --reason "重复行，合并到 clone_id=12"
```

`--confirm` 必须与库内 `gene_id` 完全一致（防 clone_id 记错误删）；clone_id 不复用，
删除后旧详情 URL 会 404。删除前建议 `mysqldump --single-transaction cloned_gene_db cloned_gene_tbl`。

---

## 7. 密钥轮换 / 泄露处置

**轮换（推荐每 6–12 个月，或人员变动时）**

```bash
# ① 建新 key（同 label 加日期后缀）
python3 scripts/known_gene_api_key.py create --label tiantian-maintainer-2027 \
    --scopes write --expires-days 365 --out-file /home/fei/known_gene_api_key_2027.txt
# ② 客户端切到新 key（更新 CI/维护者本地环境变量或 key 文件）
# ③ 旧 key 观察 1–2 天无使用后吊销
python3 scripts/known_gene_api_key.py list      # 看 last_used_at
python3 scripts/known_gene_api_key.py revoke --id <旧 key id>
```

**泄露处置**：立即 `revoke` 旧 key（后续请求 401）→ 建新 key → 查审计
`GET /changes?since=<泄露时间段>` 评估是否有异常写入 → 必要时按 §6.2 回滚。
由于 DB 只有 sha256，**raw key 泄露后无法从库里找回/禁用明文**，只能吊销整行。

---

## 8. 维护者批量更新流程（Excel → API）

标准链路（全部脚本已入库）：

```text
① 修改并冻结 Excel（17 列，主 sheet 数据（修正版vXXXX））
        │
② scripts/known_genes_v2055/extract.py   → JSONL（1420 行 × 23 字段）
        │   python3 scripts/known_genes_v2055/extract.py \
        │     --xlsx "/path/to/已知基因逐条提取清单_....xlsx" \
        │     --outdir scripts/known_genes_v2055/out
        │
③ scripts/known_gene_push.py --dry-run   ← 预演（默认，不写库）
④ scripts/known_gene_push.py --commit    → POST /api/genes/known/write/bulk（mode=upsert）
        │
⑤ GET /api/genes/known/all + /stats + /known/{id} 抽查；审计 /changes 复核
```

### 8.1 push 脚本用法

```bash
# dry-run（默认）：逐批显示 would_create / would_update / error，不写库
KNOWN_GENE_API_KEY=kgw_xxx python3 scripts/known_gene_push.py \
    --jsonl scripts/known_genes_v2055/out/known_genes_v2056.jsonl \
    --base-url https://wheatomics.sdau.edu.cn --dry-run

# 真写：upsert（已存在则更新、否则新增），每批 ≤500 行 / ≤1.8MB
KNOWN_GENE_API_KEY=kgw_xxx python3 scripts/known_gene_push.py \
    --jsonl scripts/known_genes_v2055/out/known_genes_v2056.jsonl \
    --base-url https://wheatomics.sdau.edu.cn --commit

# key 也可以从 600 权限文件读（优先级：环境变量 > --key-file）
python3 scripts/known_gene_push.py --jsonl ...jsonl \
    --key-file /home/fei/known_gene_api_key_20261028.txt --dry-run
```

JSONL → API 字段映射：`_row` / `_tier` / `_warn` / `clone_id` 丢弃；
`paper_title` / `paper_doi` / `publication_years` 的 `###` 串转 list；
`publication_year` 数字串转 int；其余（含 `species_primary` / `chromosome`）原样透传，
服务端校验后采用。**先 dry-run 看错误，再 --commit**；upsert 可安全重跑（幂等）。

### 8.2 安全性

- 默认 dry-run，只有显式 `--commit` 才写库；
- 单批失败立即中止；服务端保证单批"全有或全无"，但**之前已成功的批次不回滚**
  （脚本会打印已处理行数；upsert 重跑即可对齐）；
- `429/5xx` 自动重试（指数退避 + `Retry-After`）；401/403/413/422 立即中止并提示；
- 脚本不打印 raw key，`--key-file` 建议 600 权限。

### 8.3 数据更新后的抽查清单

```bash
BASE=https://wheatomics.sdau.edu.cn
curl -s "$BASE/api/genes/known/all?limit=2" | python3 -m json.tool
curl -s "$BASE/api/genes/known/stats" | python3 -m json.tool
curl -s "$BASE/api/genes/known/search?searchid=TaCRT" | python3 -m json.tool
curl -s "$BASE/api/genes/known/<新 clone_id>" | python3 -m json.tool
curl -s -H "Authorization: Bearer $ADMIN_KEY" \
  "$BASE/api/genes/known/write/changes?limit=20" | python3 -m json.tool
```

---

## 9. 部署与生产 smoke 清单

### 9.1 上线顺序

1. **DB**：root 执行 `scripts/sql/known_gene_write_api.sql`（新增两表）；
2. **代码**：`git pull`（含 `gene_write.py` / `known_gene_ingest.py` /
   `known_gene_auth.py` / `species_map.json` / config / main 注册）→
   `sudo systemctl restart wheatomics-api`；
3. **密钥**：`known_gene_api_key.py create` 生成 write + admin key（raw 只显示一次，
   写入 600 文件 → 交给维护者）；
4. **自测**：`known_gene_write_selftest.py --base-url https://wheatomics.sdau.edu.cn`（带 key）；
5. **落库冒烟**（维护者，用一条临时测试数据）：
   - `POST /write` 真写 → 记 clone_id / audit_id；
   - `PATCH /write/{clone_id}` 改 `gene_phenotype` → 返回 changed_fields + audit_id；
   - `POST /write/bulk`（2 行，mode=upsert，dry_run=false）→ created/updated 正确；
   - `GET /write/changes?clone_id=...`（admin key）→ 看到 create/update 审计；
   - 读接口复查：`/known/{clone_id}`、`/known/all?limit=2`、`/known/search`、`/known/stats`；
   - `scripts/known_gene_admin.py delete` 删除测试行（写 delete 审计）；
6. **清理**：测试数据删除后 clone_id 不复用；确认审计记录保留（这是预期行为）。

### 9.2 回滚

- DDL 回滚：`DROP TABLE known_gene_change_log; DROP TABLE known_gene_api_keys;`
  （只删新表，不影响业务数据；已发放 key 一并失效）；
- 代码回滚：`git revert` + `systemctl restart wheatomics-api`；
- 数据回滚：§6.2。

### 9.3 验证用 curl（Lead 可直接复制）

```bash
BASE=https://wheatomics.sdau.edu.cn
KEY=$(cat /home/fei/known_gene_api_key_20261028.txt)
ADMIN=$(cat /home/fei/known_gene_admin_key.txt)

# 401（无 key）
curl -s -o /dev/null -w '%{http_code}\n' "$BASE/api/genes/known/write/whoami"
# 200 whoami（只返回 label/scopes，不返回 key）
curl -s -H "Authorization: Bearer $KEY" "$BASE/api/genes/known/write/whoami" | python3 -m json.tool
# dry-run 新增（不写库）
curl -sS -X POST "$BASE/api/genes/known/write" -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' -d '{"dry_run":true,"gene":{"gene_id":"SMOKE_20261028","gene_name":"smoke","reference_genome_id":"Refv1.0","gene_species":"Triticum aestivum (bread wheat)","chrom_pos":"Refv1.0 chr7A:1.0-1.1Mb","gene_phenotype":"smoke","functional_category":"Quality & Yield","research_strategy":"Not reported","key_result":"smoke","paper_doi":"10.0000/smoke"}}' | python3 -m json.tool
# 审计（admin）
curl -s -H "Authorization: Bearer $ADMIN" "$BASE/api/genes/known/write/changes?limit=3" | python3 -m json.tool
# 读接口未回归
curl -s -o /dev/null -w '%{http_code}\n' "$BASE/api/genes/known/all?limit=1"
```

---

## 10. 限制与已知风险

1. **限流是每 worker 计数的**（8 worker ⇒ 实际约 8×60 次/分钟）：防误用够用，不做
   精确配额；如需严格限流应上 Redis/网关层。
2. **IP 白名单在 Apache 反代后看到的是代理 IP**（默认空=不限制），真实来源限制请放
   在 Apache/防火墙层。
3. **批量非 dry-run 的"全有或全无"仅限单批**（≤500 行）；多批之间前批成功后批失败
   时前批已提交（脚本会打印进度，upsert 可安全重跑）。
4. **无 (gene_id, gene_name) 唯一索引**：并发新增同一自然键存在极小概率双写；如需
   强约束，可评估 `ALTER TABLE ... ADD UNIQUE KEY`（需先清理历史重复，另立项）。
5. **v1 不提供 API 删除**：删除只能走 `scripts/known_gene_admin.py`（写审计）；这是
   有意的安全边界。
6. **`client_ip` 审计值**受反代影响（见 2）；审计 JSON 快照含长文本，`/changes`
   默认不返回快照，需要时用 `include_snapshot=true` 且控制 `limit`。
7. **写接口不缓存**：读接口无缓存（/stats 可选缓存），写入后立即生效；若后续为
   `/known/stats` 加 TTL 缓存，写接口需同步失效（当前实现无缓存，无此问题）。
