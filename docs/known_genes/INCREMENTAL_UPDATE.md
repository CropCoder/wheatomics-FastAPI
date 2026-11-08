# KnownGene 新增基因上线流程（增量更新，含防重）

> 适用场景：v2061 已上线（1420 行）之后，Excel 里新增/核实了基因行，需要把**新基因**增量更新到网站，
> 且**不能让数据库出现重复行**。
>
> 一句话流程：**冻结 Excel → extract.py 出 JSONL → 预检（查库防重）→ 人工看冲突 → 仅写 NEW_SAFE → 写后验证/审计**。

## 1. 为什么不能直接用旧 push 脚本

`scripts/known_gene_push.py` 是 bulk **upsert**，服务端匹配键只有 `(gene_id, gene_name)`：

- 已存在的键 → 更新（安全）；
- **但下面这些"其实已经存在"的情况会被当成新行插入，产生重复**：
  1. 同一基因换了 gene_name（`TaSPL6B` → `TaSPL6-B`、别名、拷贝命名）；
  2. 同一基因用 v1/v2 旧 ID（库里已是 v2.1/v3）；
  3. 同一参考位点已被另一个基因名占用（如 `PmL270` 与 `PmNCA6` 都用 `TraesCS7A03G1212700`）；
  4. gene_id 相同但名称不同的"等位/同名位点"。

所以增量新增必须以**数据库现状**为准做预检，而不是只依赖 upsert 键。

## 2. 三层防重（必须全部保留）

| 层 | 做什么 | 失败后果 |
|---|---|---|
| ① 预检 preflight | 拉线上全量快照，按多键匹配：`(gene_id,gene_name)`、gene_id、gene_name、reference_genome_id、chrom_pos 位点重叠、DOI（仅提示） | 冲突/无效行**不进入待写列表** |
| ② 写入 insert_only | `POST /api/genes/known/write/bulk`，`mode=insert_only`：服务端对任一已存在的 `(gene_id,gene_name)` **整批拒绝** | 不会重复插入 |
| ③ 写后验证 | 行数 +1 校验、按新 ID/名称搜索、`/write/changes` 审计、再跑一次预检应显示 `EXACT_KEY`、`计划写入 0` | 可及时发现异常 |

**写前会重新拉一次快照并复核**，避免两次检查之间被别的会话写入。

## 3. 标准流程

```text
① Excel 新增/修改（版本化：v2061 → v2062，原始表不改）
② scripts/known_genes_v2055/extract.py → JSONL（23 字段）
③ scripts/known_gene_incremental.py --dry-run   ← 预检报告（默认，不写库）
④ 人工审阅报告：NEW_SAFE / EXACT_KEY / CONFLICT_ID / CONFLICT_NAME / CONFLICT_REF /
   CONFLICT_LOCUS / DOI_NOTE / INVALID
⑤ 处理后 --commit（只写 NEW_SAFE，insert_only）
⑥ 写后验证 + 审计 + 再跑预检（应 0 待写）
```

### 3.1 预检（dry-run，默认）

```bash
python3 scripts/known_gene_incremental.py \
  --jsonl /tmp/kg_incremental/out/known_genes_v2062.jsonl \
  --report-dir /tmp/kg_incremental/report
```

输出：`preflight_<时间>.md/.tsv`（逐行状态 + 匹配到的 clone_id + 原因）。

### 3.2 提交

```bash
python3 scripts/known_gene_incremental.py \
  --jsonl /tmp/kg_incremental/out/known_genes_v2062.jsonl \
  --report-dir /tmp/kg_incremental/report --commit \
  --key-file ~/.config/lab-server/wheatomics_known_gene_write_key.txt
```

只写 `NEW_SAFE`，不会更新已有行、不会删除、不会插入已存在的基因。

## 4. 状态判定与处理

| 状态 | 含义 | 处理 |
|---|---|---|
| `EXACT_KEY` | 库内已有同 `(gene_id,gene_name)` | 跳过（如需改内容走 PATCH） |
| `NEW_SAFE` | 多键均未命中 | 可新增 |
| `INVALID` | 必填缺失或 `Not reported` 占位符 | 先补真实编号，不写库 |
| `CONFLICT_ID` | 同 gene_id、不同 gene_name | **人工确认**：改名重复→用 PATCH 改已有行；确属不同基因→需团队批准后放开（默认不写） |
| `CONFLICT_NAME` | 同 gene_name、不同 gene_id | 人工确认（拷贝/别名/重复） |
| `CONFLICT_REF` | 同 reference_genome_id（不同基因名） | 默认不写；若是 D7 允许的"同位点不同基因/等位"，需明确说明后人工放行 |
| `CONFLICT_LOCUS` | 坐标区间与库内行重叠 | 人工确认；确认是 **D7 允许的"同一位点不同基因/等位"** 后，用 `--allow-locus-shared` 放行（脚本会打印提示） |
| `DOI_NOTE` | 仅同文献 | 允许（同文献多基因正常） |

## 5. ⚠️ 重要发现：公网写接口会被校园边缘 WAF 拦截（2026-10-28 实测）

- 现象：同一行数据（YrKB/TaEDR2-B，约 4.7 KB JSON，含基因 ID、括号、数字、`EDR2-like` 等）：
  - 走公网 `https://wheatomics.sdau.edu.cn/api/genes/known/write/bulk` → `curl: (52) Empty reply from server`（HTTP 请求被边缘断开，服务端无日志）；
  - 走服务器本机 `http://127.0.0.1:8000/api/genes/known/write/bulk` → **正常返回**并成功入库；
- 小 payload（短文本）走公网有时可通过，长科研文本累积触发 WAF 异常分（括号+数字+基因名等组合），
  不能用于稳定批量维护。
- **结论：新基因增量上线的正式路径 = 在服务器本机执行**（服务器本机还持有 `127.0.0.1:8000` 的 API），
  公网写接口只用于偶尔的小改动；若需公网稳定写入，请网络管理员把 `/api/genes/known/write/*` 加入 WAF 白名单。

### 5.1 服务器本机执行（推荐）

```bash
# 1) 从本机把 JSONL/脚本/密钥传到节点（经跳板机；密钥 600，用完删除）
scp -J <jump> <jsonl> <node>:/tmp/kg_incremental_v2062/
scp -J <jump> scripts/known_gene_incremental.py <node>:/tmp/kg_incremental_v2062/

# 2) 在节点上：预检（读 localhost API）
ssh -J <jump> <node> 'cd /tmp/kg_incremental_v2062 && \
  python3 known_gene_incremental.py --jsonl known_genes_v2062.jsonl \
    --base-url http://127.0.0.1:8000 --key-file key --report-dir report'

# 3) 确认后 --commit（insert_only）
ssh -J <jump> <node> 'cd /tmp/kg_incremental_v2062 && \
  python3 known_gene_incremental.py --jsonl known_genes_v2062.jsonl \
    --base-url http://127.0.0.1:8000 --key-file key --report-dir report --commit'

# 4) 删除临时密钥
ssh -J <jump> <node> 'rm -f /tmp/kg_incremental_v2062/key'
```

> 节点：`fei@202.194.139.32`（仅经跳板机 `nifei@202.194.133.96:222` 可达）。
> 若 GateShell 下 `-J` 认证异常，加 `-o PubkeyAuthentication=no -o PreferredAuthentications=password,keyboard-interactive -o NumberOfPasswordPrompts=3`。
> 密码见本机 `~/.config/lab-server/wheatomics.env`（600 权限）。

## 6. 本次实际执行记录（2026-10-28）

| 项目 | 结果 |
|---|---|
| 输入 | v2061（1420 行）+ 3 个候选新基因（YrKB、TaHDA8、PmL270）；发布后冻结为 **v2062（1421 行，仅含 YrKB）** |
| 预检（公网/本机一致） | `EXACT_KEY 1420`、`NEW_SAFE 1`（YrKB）、`INVALID 1`（TaHDA8 无真实编号）、`CONFLICT_ID 1`（PmL270 与 PmNCA6 共用 `TraesCS7A03G1212700`） |
| 写入 | 仅 **YrKB/TaEDR2-B** 入库：**clone_id = 1629**，审计 `bulk_create`（id=10） |
| 写后 | `/all` total **1420 → 1421**；`/known/search?searchid=YrKB` 命中 clone 1629；`/known/1629` 正常 |
| 再预检 | `EXACT_KEY 1421`，**计划写入 0**（证明重复会被挡住） |
| 冻结/一致 | `v2062 = v2061 + YrKB`（1421 行）；v2062 JSONL 预检 = `EXACT_KEY 1421`、计划写入 0，DB 与冻结表一致 |
| 未处理 | TaHDA8（补 Supp Table S1 编号后再加）；PmL270（与 PmNCA6 是否等位待定） |

## 7. 回滚 / 审计

- 审计：`GET /api/genes/known/write/changes?limit=20`（admin key），本次新增 `clone_id=1629` 的 `bulk_create`。
- 回滚单条（服务器上）：

```bash
python3 scripts/known_gene_admin.py delete --clone-id 1629 \
  --confirm TraesCS7B03G1236800 --reason "rollback: incremental test" --dry-run
# 确认后去掉 --dry-run 真删
```

- 删除前建议 `mysqldump --single-transaction cloned_gene_db cloned_gene_tbl`。

## 8. 安全与后续

- 临时拷贝到服务器的 API key 用完立即 `rm`；长期密钥只放本机 600 文件/服务器服务配置。
- 推荐把本流程接入服务器 cron/维护脚本，避免每次手传。
- 待办：给 `known_gene_incremental.py` 增加 `--allow-ref-shared`（D7 同位点不同基因的显式放行）与
  `--update-existing`（Excel 已合并多篇文献时，如何 PATCH 已有行）两个开关。
- 待办：向网络管理员申请 WAF 白名单 `POST /api/genes/known/write/*`，让公网也能稳定执行。


---

## 9. 增量发布实例（2026-10-28 v2063）

- 新增 **Yr5x**（TraesCS2B03G1231900，Yr5 位点新等位）→ clone_id **1630**；同物理位点已有 Yr5/Yr5b（不同等位/基因名，D7 允许）→ 预检报 `CONFLICT_LOCUS`，人工确认后用 `--allow-locus-shared` 放行。
- 更新已有行：Yr6-Yr6CNLI（clone 1524）、Pm5e（clone 197）→ push `updated=2`。
- 上线后 DB 1422 行；v2063 JSONL 再预检 `EXACT_KEY 1422 / 计划写入 0`。
- 命令示例：

```bash
python3 scripts/known_gene_incremental.py --jsonl known_genes_v2063.jsonl   --base-url http://127.0.0.1:8000 --key-file key   --report-dir report --allow-locus-shared          # 预检（仅确认 D7 等位行时使用）
```
