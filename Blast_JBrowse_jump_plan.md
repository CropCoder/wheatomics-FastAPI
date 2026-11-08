# BLAST 结果页自动跳转 JBrowse —— 判断方案（2026-11-08）

> 问题：BLAST 结果页想加"跳到 JBrowse 看命中位点"，但**怎么判断哪些基因组有 JBrowse**？
>
> 结论：这件事不需要猜。平台已经有两张权威表 + 一个可实时探测的目录结构，三者一 join 就是答案。
> 真正的工作量不在"判断有没有"，而在**三套命名体系的映射**（BLAST db 名 / FASTA header 名 / JBrowse refseq 名），
> 这一点下面用实测数据说明。

---

## 1. 结论先行

| 判断层级 | 判定依据（权威、可机器判定） | 现状（2026-11-08 实测） |
|---|---|---|
| ① 这个**基因组**有没有 JBrowse | `genome_registry.jbrowse_dataset`（非 NULL） | 316 可见基因组中 **215** 有 |
| ② 这个**数据集**是否真存在 | `jbrowse_meta.jbrowse_datasets.id` | **219** 个数据集；registry 的 215 个 **全部**能在 meta 中找到（0 失配）；meta 多出 4 个孤儿 |
| ③ 数据集是否活着 | `JBROWSE_DATA_ROOT/<dataset>/seq/refSeqs.json` 可读 | 实测的 197 个数据集里 **196** 可读（唯一例外 `AABB_IG77365` 缺 refSeqs.json） |
| ④ 这条**命中**能不能给出坐标 | 核酸库看 `sseqid+sstart/send`；蛋白/CDS 库看 header 里的 `loc=` | 蛋白库抽查 **14/14** 带 `loc=chrom:start-end` |

**不需要**任何"物种名/倍性/关键词"启发式判断——那是这份方案里最该避免的东西（反例见 §4）。

---

## 2. 现状盘点：可复用的资产（都已存在）

### 2.1 基因组 ↔ JBrowse 的映射表已经建好

`genome_registry`（`DB_LITERATURE`）由 `scripts/rebuild_genome_registry.py` 从 JBrowse 数据目录生成，
其中 `jbrowse_dataset` 就是 **JBrowse 数据子目录名**（等于 `jbrowse_meta.jbrowse_datasets.id`）：

- 路由：`app/api/routers/genome.py:161` `GET /api/genomes/{dataset_id}`（含 `jbrowse_dataset`）
- 统计：`app/api/routers/genome.py:68` `GET /api/genomes/stats` 已返回 `SUM(jbrowse_dataset IS NOT NULL)`
- 数据集清单：`app/api/routers/jbrowse.py:55` `GET /api/jbrowse/datasets`
- 公开网关页：`app/static/docpages/jbrowse.html`（213 个 `?data=` 链接，已有现成的"哪些基因组有 JBrowse"可视化列表）

实测一致性（本次用线上 API 交叉核对）：

```
genome_registry 可见 316 行，jbrowse_dataset 非空 215 行
jbrowse_meta 数据集 219 个
registry → meta 失配：0
meta 孤儿（有数据集、无 registry 行）：4 个
    fangenome / KeNong9204 / rye_weining2.0 / Secale_cereale
```

> 4 个孤儿里 `fangenome` 对应的 BLAST 库 `fangenome_final` 正被 registry 标成"无 JBrowse"——
> 这是**立刻能补的 1 个覆盖缺口**（表里加一行映射即可）。

### 2.2 BLAST 侧已经有一半映射代码

`app/api/routers/blast.py:224` `_assembly_level_map()` 已经：
- 从 `genome_registry` 读 `dataset_id / blast_genome_db / blast_cds_db / blast_pep_db / assembly_level`
- 按 BLAST 库 base 名建索引，供 `_db_meta()`（`blast.py:271`）给每个库打 `kind / assembly_level` 徽章

**但它把 `dataset_id` 丢掉了**（`_db_meta` 返回的 dict 里没有），也没读 `jbrowse_dataset`。
所以"哪个库所属基因组有 JBrowse"只差 **3 个字段**，不需要新的数据源。

### 2.3 两套"序列名"来源都是可编程读取的

| 侧 | 来源 | 内容 |
|---|---|---|
| BLAST 侧 | `BLAST_DB_PATH/<db>.fai`（seqid + length）；现成 API：`GET /api/blast/database-example?db=<db>` 给首条名字+长度，`GET /api/sequence/chromosomes?database=<db>` 给全部名字 | `Chr1A_AK58`（604,927,367 bp） |
| JBrowse 侧 | `JBROWSE_DATA_ROOT/<dataset>/seq/refSeqs.json`（**公开可访问**） | `[{"name":"chr1A","length":604927367,...}]` |

两者都在同一台机器上、同一域名下（`https://wheatomics.sdau.edu.cn/jbrowse-1.12.3-release/<ds>/seq/refSeqs.json`
可直接 `fetch`，同源无 CORS 问题），因此**映射表可以离线构建、运行时 O(1) 查询**。

---

## 3. 判断算法：四级门禁（每级都可机器判定）

```
BLAST 命中 (db, sseqid, sstart, send, stitle)
  │
  ├─ Gate 1  DB 类型/坐标来源                    → 决定"坐标从哪来"
  │    kind = _db_base_kind_chromosome(db)
  │    genome / chromosome  ── 核酸坐标：sseqid + min(sstart,send)..max(...)
  │    protein / cds        ── stitle 里正则 loc=(\S+?):(\d+)-(\d+)
  │    aggregate (all_*)    ── 无单一基因组：逐命中按基因 ID 推断，推断不出就不给按钮
  │    scaffold             ── 允许，但只支持 refseq 里真实存在的 scaffold 名
  │
  ├─ Gate 2  基因组级：该 db base 是否解析到一个"有 JBrowse"的基因组
  │    row = registry[base]                     # _assembly_level_map() 已有
  │    row.jbrowse_dataset != NULL && jbrowse_meta[row.jbrowse_dataset] 存在
  │
  ├─ Gate 3  数据集级：<dataset>/seq/refSeqs.json 可读（构建/部署时算好，运行时不读盘）
  │
  └─ Gate 4  坐标级：把 (chrom_token, start, end) 贴到某个 refseq 上
       token 归一化 → 命中 refseq；且 0 < start ≤ end ≤ refseq.length
       长度不一致 ⇒ "JBrowse 版本与 BLAST 库不是同一组装" ⇒ 禁用并给出原因
```

### 3.1 Gate 4 才是难点：三套命名体系 + 版本会错配

同一份 AK58 数据，三处叫法都不一样（本次实测）：

| 出处 | 写法 |
|---|---|
| BLAST 库 `.fai`（`?db=AABBDD_AK58.genome`） | `Chr1A_AK58` |
| 蛋白库 header（`/api/sequence/by-gene`） | `Chr1A:14083-14379`（无组装后缀，大小写不一） |
| JBrowse refseq（`AK58/seq/refSeqs.json`） | `chr1A` |
| 另一个数据集 Sumai3 | `Chr1A_Sumai3`（大写带后缀，与上面都不同） |

**按名字直接匹配的实测结果：203 个核酸 `.genome` 库里只有 9 个（4.4%）能靠名字对上。**
所以不能写"去掉 `_Assembly` 后缀再比"这种启发式——它会在 scaffold 库和部分命名上翻车。

**按染色体长度匹配才是可靠的**：`.fai` 和 `refSeqs.json` 都带长度，同一组装的染色体长度逐一相等。

```
203 个 .genome 库中：
   197 个所属基因组有 JBrowse 数据集
   196 个能读到 seq/refSeqs.json
   195 个"首条染色体长度"与 refSeqs.json 精确相等（99.5%）→ 同一组装，可安全跳转
     1 个长度不一致（RR_rye_weining：BLAST Chr1_part1_rye_weining 400,000,000 vs JBrowse 8 条 refseq）
   名字精确匹配 9 / 203
```

长度门禁还顺带抓出一个真实事故级风险：

```
HH_Morex.genome  Chr1H_Morex = 516,505,932 bp
Morex JBrowse 数据集首条 refseq = 680,018 bp（290 条，scaffold 版 Morex）
⇒ 同一"Morex"名下 BLAST 库与 JBrowse 数据集是不同版本
⇒ 如果按物种名判断，用户会被送到错误坐标上
```

这类情况必须**禁用按钮 + 提示"该基因组 JBrowse 版本与 BLAST 库不一致"**，而不是硬跳。

### 3.2 蛋白/CDS 命中也有坐标（不用查基因表）

`scripts/enrich_all_blast_dbs.py` 重建 `.add_Description.{cds,pep}` 库时，
把注释字段写进了 FASTA header：`>geneID loc=Chr1A:14083-14379 strand=+ Description=... ChineseSpring02G=...`。
BLAST outfmt 6 的第 15 列 `stitle` 会原样带出，抽查 14 个不同组装 **14/14 都有 `loc=`**：

```
Abo        Abo1A000100.1            loc=Chr1A:1198637-1199530
AK58       TraesAK58CH1A01G000100.1 loc=Chr1A:14083-14379
Kariega    TraesKAR7A01G0000010LC.1 loc=chr7A:6495-6674
...
```

前端 `parseTsv()`（`app/static/blast2/index.html:2756`）目前只抓了 stitle 开头的 `chrom:start-end`
（老式 header），没有解析 `loc=`。补一个正则即可，**不需要新增后端查询**。

> CDS/PEP 库覆盖：193 个蛋白库中 172 个所属基因组有 JBrowse；191 个 CDS 库中 172 个有。
> 剩余 20 个是 `CS-IAAS / CWI86942 / Paragon_scaffolds / ...` 这类"平台有该组装的库、但没有为该组装建 JBrowse"。

### 3.3 一条命中属于哪个库？（多库搜索的归属问题）

**已落地（2026-11-08）**：`result.tsv` 现在有 **16 列**，末尾追加 `sdb`（subject database）。
BLAST 本身给不出来——outfmt 6 没有"数据库"列，多库搜索的结果是合并后的一张表
（列定义见 `app/services/blast_runner.py` 顶部 docstring）。实现方式：

- daemon 在 BLAST 跑完、写 `.gz` 之前，用 `blastdbcmd -entry_batch` 拿"本次任务选中的库"
  逐个核对每个 subject id 是否存在于该库（`app/services/blast_db_attribution.py`）；
- 单库任务直接填该库，**零额外开销**；
- 多库任务：只在 1 个库里出现 → 填该库；在多个库里都出现（如基因组库 + `all_*` 聚合库）
  → `sdb` 留空（**不猜**）；归因失败/跳过 → 留空并在 `status.json.attribution` 记录原因；
- `.gz` 在归因之后生成，下载的压缩包同样带 `sdb` 列。

对 JBrowse 跳转的影响：
- 多库搜索现在能直接判断"这条命中来自哪个库"，前端读第 16 列即可，**不需要再建 seqid→db 索引**；
- 但 `sdb` 只回答"哪个库"，不回答"聚合库内部是哪个基因组"——`all_genes/all_proteins` 的命中
  仍需按基因 ID 前缀推断基因组（推断不出就不给按钮）；
- 前端 `parseTsv()` 已兼容 15 列旧结果（无 `sdb`）与 16 列新结果，多库任务在命中行显示库名徽标。

---

## 4. 覆盖率总账（实测）

| 库类型 | 库数 | 所属基因组有 JBrowse | 说明 |
|---|---|---|---|
| 核酸 `.genome` | 203 | **197 (97.0%)** | 主场景，长度匹配 195 可用 |
| 核酸 `.genome_Chr*`（拆分库） | 2366 | 2282 (96.4%) | 同上，按单染色体库搜索时命中 |
| 核酸 `.add_Description.cds` | 191 | 172 | 坐标来自 header `loc=` |
| 蛋白 `.add_Description.pep` | 193 | 172 | 同上 |
| 聚合库 `all_*` | 36 | — | 无单一基因组，需逐命中推断 |

**没有 JBrowse 的 6 个 genome 库（应显示"不支持跳转"）**：

```
AABBDD_CS-IAAS                 （JBrowse 里只有 CS-IAAS_T2T，另一个组装）
AABBDD_CWI86942                （JBrowse 里只有 TaesCWI86942）
AABBDD_Chinese_Spring_Triticum_4.0
DD_Aegilops_tauschii_Jia
SSHH_Elymus_sibiricus_Gaomu
fangenome_final                （孤儿数据集 fangenome 存在 → 可立刻补映射）
```

> 注意：**不要用"物种有 JBrowse"去判断"这个组装有 JBrowse"**。
> 同一物种在 registry 里是多行的（如 `AABBDD_CS-IAAS` 无 JBrowse、`CS-IAAS_T2T` 有；
> `CWI86942` 无、`TaesCWI86942` 有）。判断粒度必须是 **assembly 行**，即 `genome_registry.dataset_id`。

---

## 5. 数据层：一张离线映射表 + 一个构建脚本

### 5.1 新脚本 `scripts/build_blast_jbrowse_map.py`

产物：`app/services/data/blast_jbrowse_map.json`（与现有 `blast_db_levels.json` 同一模式，带 mtime 缓存）。

输入（全在服务器本地，无需 DB 连接即可跑）：
1. `BLAST_DB_PATH/<base>.genome.fai` → `seqid, length`
2. `JBROWSE_DATA_ROOT/<dataset>/seq/refSeqs.json` → `name, length`
3. `genome_registry`（可选，用于补 `dataset_id/ploidy/可见性`；读不到时退化到 API/JSON）

匹配算法（长度优先，名字兜底）：

```python
def map_refseqs(fai_rows, refseqs):
    """fai_rows: [(seqid, length)]; refseqs: [(name, length)] -> {fai_seqid: refseq_name}"""
    by_len = {}
    for name, length in refseqs:
        by_len.setdefault(length, []).append(name)
    out = {}
    for seqid, length in fai_rows:
        cands = by_len.get(length) or []
        if len(cands) == 1:                      # 长度唯一 → 直接定
            out[seqid] = cands[0]
        elif cands:                              # 长度撞车（如 1A/1B 等分片或同长 scaffold）
            out[seqid] = pick_by_norm(seqid, cands)   # 归一化名字（大小写/去 chr/去 _assembly）兜底
        else:
            out[seqid] = None                    # 长度对不上 → 该染色体不可跳（版本不一致）
    return out
```

输出结构（按 BLAST 库 base 索引，运行时只返回需要的 seqid，避免把 158k scaffold 全量塞给浏览器）：

```json
{
  "AABBDD_AK58": {
    "genome_dataset_id": "AK58",
    "jbrowse_dataset": "AK58",
    "assembly_match": true,
    "refseqs": { "Chr1A_AK58": "chr1A", "Chr1B_AK58": "chr1B", "...": "..." },
    "mismatch": []
  },
  "HH_Morex": { "jbrowse_dataset": "Morex", "assembly_match": false, "reason": "chrom length mismatch (516,505,932 vs 680,018)" }
}
```

### 5.2 映射表的键必须覆盖"别名"，而不只是 base 名

`_assembly_level_map()` 的键集合是 `blast_genome_db / blast_cds_db / blast_pep_db / dataset_id`，
实测还有 25 个库落不进这个键集合（`AABBDD_arinalrfor.PGSBv2.1` vs registry `AABBDD_arinalrfor_PGSBv2_1` 等点/下划线差异）。
对策：构建脚本额外写入一条 `alias` 表（`{blast_base: assembly_dataset_id}`），
落不进时**不要猜**——写进 `coverage` 报告的 `unresolved` 列表，由人补一行。

### 5.3 判断"有 JBrowse"的推荐 SQL（运维/覆盖率页用）

跨库 join 即可（同实例、不同 schema；`mysql_cursor(DB_LITERATURE)` 里可写全名）：

```sql
SELECT g.dataset_id, g.display_name, g.ploidy, g.assembly_level,
       g.jbrowse_dataset,
       d.id IS NOT NULL            AS jbrowse_meta_ok,
       COALESCE(d.track_count, 0)  AS track_count
FROM genome_registry g
LEFT JOIN jbrowse_meta.jbrowse_datasets d ON d.id = g.jbrowse_dataset
WHERE g.visible = 1;
```

---

## 6. 接口改动（尽量小、可灰度）

### 6.1 `app/api/routers/blast.py`

1. `_assembly_level_map()`：查询里加 `jbrowse_dataset`，entry 带上它（`blast.py:224-266`）。
2. `_db_meta()`：返回体加 3 个字段（`blast.py:271-291`）：

```python
if info.get("jbrowse_dataset"):
    meta["jbrowse"] = {
        "dataset": info["jbrowse_dataset"],
        "available": True,          # 构建脚本判定；dataset 缺失/长度不匹配时为 False
        "reason": info.get("jbrowse_reason"),   # 例如 "assembly version mismatch"
    }
```

   → 前端 `applyDatabases()`（`index.html:2073`）本来就把 `database_meta` 存进 `state.dbMeta`，
   **这一步做完前端就已经知道"哪些库能跳"，零额外请求。**

3. 新增懒加载端点（结果页只对结果里出现的库调用一次，响应体只含该库 FAI 的 seqid 列表，通常 21~70 条 / 2 KB）：

```
GET /api/blast/database/{db}/jbrowse[?seqids=Chr1A_AK58,Chr1B_AK58]
→ {"success":true,"data":{"database":"AABBDD_AK58.genome","dataset":"AK58",
   "template":"/jbrowse-1.12.3-release/?data=AK58&loc={loc}",
   "assembly_match":true,
   "refseqs":{"Chr1A_AK58":"chr1A",...},
   "missing":["ChrUn_AK58"]}}
```

4. `blast_job_status()`（`blast.py:632`）补 `program` / `database`：

```python
data = read_status(job_id)
params = read_params(job_id) or {}      # blast_runner 已有 read_params()
return {..., "program": params.get("program"), "database": params.get("dbs", [])}
```

   **必要性**：结果页的 db 列表目前只从 `localStorage` 的 ctx 恢复（`index.html:2593`、`2611`），
   别人打开分享链接时 ctx 为空 → 不知道用了哪些库 → 跳转按钮无法渲染。这是现成功能的洞。

5. （可选）`POST /api/blast/jbrowse-links`：传 job_id + 命中列表，一次批量返回每个命中的
   `{available, url, reason}`，把映射逻辑完全留在后端，前端只负责渲染。适合 gate 4 规则以后还要改的情况。

### 6.2 `app/api/routers/jbrowse.py`

- 新增 `GET /api/jbrowse/datasets/{dataset}/refseqs`：读 `JBROWSE_DATA_ROOT/<ds>/seq/refSeqs.json`（缓存 + mtime），
  返回 `[{name,length}]`；顺便做 404/损坏的降级。
- 新增 `GET /api/jbrowse/coverage`：§5.3 的 join 结果 + 缺口清单
  （`no_jbrowse_dbs` / `registry_missing_meta` / `meta_orphans` / `length_mismatch` / `unresolved_alias`）。
  这个端点是"判断逻辑"唯一的可视化出口，运维每次重建 JBrowse 后看一眼即可。

### 6.3 `app/core/config.py`

现在 URL 前缀散落硬编码（`gene.py:1260`、`geneDetail.py:176` 里 `http://wheatomics.sdau.edu.cn/jbrowse-1.12.3-release/`）。
建议加：

```python
JBROWSE_WEB_PATH: str = "/jbrowse-1.12.3-release"   # 相对路径，避免 http/https 混用
JBROWSE2_WEB_PATH: str = "/genome_browser"          # 服务器另有 JBrowse 2 v4.1.15
```

`template` 用相对路径，前端拼 `loc` 即可；将来迁 JBrowse 2 只改配置 + 加一种模板
（JBrowse2 是 `?config=X_config.json&loc=chr:start-end`）。

---

## 7. 前端改动（`app/static/blast2/index.html`）

### 7.1 命中行按钮

`renderDescriptions()`（`index.html:2883`）里 subject 列已经有一个 `.blast-row-align` 小按钮的模式，
照抄一个 `.blast-row-jbrowse`：

```js
// 结果渲染时：state.jbrowseMaps = {dbBase: <GET /api/blast/database/{db}/jbrowse 的 data>}
//               state.seqidIndex = {"Chr1A_AK58": ["AABBDD_AK58.genome"], ...}  （P2 多库归属用）
function coordsOf(hit, db) {                      // 坐标来源按库类型分流（Gate 1）
  var meta = state.dbMeta[db] || {};
  if (meta.kind === 'genome' || meta.kind === 'chromosome') {
    return { token: hit.sseqid,
             start: Math.min(hit.sstart, hit.send), end: Math.max(hit.sstart, hit.send) };
  }
  var m = (hit.stitle || '').match(/(?:^|\s)loc=(\S+?):(\d+)-(\d+)/);   // 蛋白/CDS：header 里的 loc=
  return m ? { token: m[1], start: +m[2], end: +m[3] } : null;
}

function jbrowseButton(hit, db) {                 // db 由 §3.3 的归属规则给出；归属不了就传 null
  var map = db && state.jbrowseMaps[db];
  if (!map || !map.assembly_match) return '';     // 不可用 → 不渲染（不要灰按钮、不要 toast）
  var c = coordsOf(hit, db);
  if (!c) return '';
  var ref = map.refseqs[c.token];
  if (!ref) return '';
  var pad = 2000;
  var s = Math.max(1, c.start - pad), e = c.end + pad;
  if (e - s > 100000) { s = c.start; e = Math.min(c.end, s + 100000); }   // JBrowse1 大区间很慢
  var url = map.template.replace('{loc}', encodeURIComponent(ref + ':' + s + '..' + e));
  return '<a class="blast-row-jbrowse" target="_blank" rel="noopener" href="' + url +
         '" data-why="' + esc(map.reason || '') + '" title="Open this hit in JBrowse">JBrowse</a>';
}
```

要点：
- **不可用就不渲染**，把原因写到 `data-why` 或 title（便于排查），不要弹窗。
- 坐标：`min(sstart,send)..max(sstart,send)`（BLAST 1-based inclusive，JBrowse1 的 loc 也是 1-based）；
  跨度设上限（建议 100 kb）并在超出时提示，JBrowse1 大区间渲染很慢（`maxExportSpan` 只有 1 Mb）。
- 蛋白命中：`stitle.match(/loc=(\S+?):(\d+)-(\d+)/)`；`strand=-` 只影响显示，不影响 loc。
- 聚合库（`all_genes/all_proteins/all_Allohexaploid*`）：结果里没有"库→基因组"关系，
  逐命中按基因 ID 前缀推断（`TraesCS*` → 该组装；识别不出 → 不渲染），或直接回退到现有 GeneHub 链接
  （`index.html:2897` 已经对 `^Traes` 的 sseqid 做了 GeneHub 跳转）。
- 多库搜索的归属按 §3.3；如果以后规则复杂化（更多别名、更多版本门禁），把 `coordsOf + 归属 + Gate4`
  整体搬到后端 `POST /api/blast/jbrowse-links`（传 job_id + sseqid 列表），前端只渲染返回的 `{available,url,reason}`。
- Graphic Summary（`index.html:3013`）的行标签旁也可以加一个小图标，同样的判定，成本很低。

### 7.2 "自动跳转"的两种形态

| 形态 | 建议 |
|---|---|
| 点击行内链接/按钮 | **默认做这个**：可控、不打断结果浏览、无弹窗拦截问题 |
| 结果加载完成后自动 `window.open` | 不推荐：被浏览器拦截、多命中时开一堆标签页 |
| 结果页内嵌 JBrowse iframe（`tracklist=0&nav=0&overview=0&fullviewlink=0`，基因详情页已有先例） | 可选（"自动预览"开关存 localStorage）：适合"只有 1~3 个命中"的场景，命中多时反而慢 |

### 7.3 结果头部的汇总入口

`renderMeta()`（`index.html:2638`）旁边加一个：
"命中来自 N 个基因组，其中 M 个有 JBrowse → 查看最佳命中"（M=0 时整块不显示）。
这条比逐行按钮更能回答用户"我这个结果到底能不能看基因组"。

---

## 8. 验收用例（可直接照抄当回归测试）

| # | 输入 | 期望 |
|---|---|---|
| 1 | `blastn` vs `AABBDD_AK58.genome`，命中 `Chr1A_AK58:14083-14379` | 跳到 `?data=AK58&loc=chr1A:12083..16379`；长度 604,927,367 一致 |
| 2 | `blastp` vs `AABBDD_AK58.add_Description.pep`，`TraesAK58CH1A01G000100.1` | 从 stitle `loc=` 取坐标，同上 |
| 3 | `blastn` vs `AABBDD_Fielder.genome` | `?data=Fielder&loc=chr1A:...`（Fielder 数据集只有 22 条 refseq，大写 `Chr1A_Fielder` → 需归一化） |
| 4 | `blastn` vs `HH_Morex.genome` | **按钮不出现**，coverage 里记录 `length_mismatch`（Morex JBrowse 是 scaffold 版） |
| 5 | `blastn` vs `AABBDD_CS-IAAS.genome` | **按钮不出现**（该组装无 JBrowse；CS-IAAS_T2T 是另一个组装，不得借用） |
| 6 | `blastp` vs `all_proteins` | 逐命中：能推断基因组则给按钮，否则回退 GeneHub；不得猜 |
| 7 | 分享结果链接（新浏览器、无 localStorage） | 仍能显示按钮（依赖 §6.1 第 4 条的 status 兜底） |
| 8 | `GET /api/jbrowse/coverage` | `genome_db_resolved_rate ≥ 97%`、`length_match_rate ≥ 95%`、`unresolved_alias` 有清单 |

人工验证 3~5 条 URL 用现成命名：`https://wheatomics.sdau.edu.cn/jbrowse-1.12.3-release/?data=<dataset>&loc=<refseq>:<s>..<e>`。

---

## 9. 分阶段落地

| 阶段 | 内容 | 产出 | 工作量 |
|---|---|---|---|
| **P0** | `_assembly_level_map` 带 `jbrowse_dataset`；`_db_meta` 加 `jbrowse` 三字段；`GET /api/jbrowse/coverage` | 判断结论可查、页面不动 | 0.5 d |
| **P1** | `scripts/build_blast_jbrowse_map.py` + `GET /api/blast/database/{db}/jbrowse`；前端行内按钮；`status` 补 program/db | 核酸命中可跳（~97% 覆盖） | 1 d |
| **P2** | 蛋白命中 `loc=` 解析；聚合库逐命中推断；GeneHub 分工 | 蛋白库命中可跳（~89% 覆盖） | 1 d |
| **P3** | 4 个孤儿数据集接回 registry（`fangenome` 等）+ 缺口清单修复 | 覆盖率 +1~2% | 0.5 d |
| **P4** | JBrowse2 模板（`/genome_browser/?config=...`）、iframe 预览开关 | 双浏览器可切 | 1 d |

灰度：P1 的按钮可以先用 URL 参数/后端开关（如 `BLAST_JBROWSE_LINKS=0/1`）控制，
或者只在 `coverage` 达标的库上显示——反正判断是数据驱动的，天然可灰度。

---

## 10. 风险与对策（每条都有实测依据）

| 风险 | 依据 | 对策 |
|---|---|---|
| 名称/版本不一致导致跳到错误坐标 | Morex：BLAST 516,505,932 vs JBrowse 680,018 | Gate 4 用**长度相等**做硬门禁；不相等 → 禁用 + 原因 |
| 按物种判断导致串组装 | `CS-IAAS`(无) vs `CS-IAAS_T2T`(有)；`CWI86942`(无) vs `TaesCWI86942`(有) | 判断粒度锁死到 assembly 行（`dataset_id`），永不按 species/ploidy 推断 |
| 命名启发式在 scaffold 库翻车 | 名字精确匹配只有 9/203 | 长度优先 + 名字归一化仅作为同长度时的 tie-break |
| registry 与 jbrowse_meta 失同步 | 4 个孤儿数据集；`AABB_IG77365` 缺 refSeqs.json | `/api/jbrowse/coverage` 每次重建 JBrowse / 跑 `import_jbrowse_meta.py` 后必查 |
| 分享链接丢上下文 | `status` 只返回 `download_urls`，db 列表在 localStorage | §6.1 第 4 条 |
| 聚合库命中跨基因组 | `all_genes/all_proteins` 36 个聚合库 | 逐命中推断；推断不出 → 不给按钮（宁缺勿错） |
| 大区间拖垮 JBrowse1 | 现有页面默认 `maxExportSpan=1,000,000` | 跨度截断/上限 100 kb，超出提示 |
| http/https 混用 | `geneDetail.py` 里硬编码 `http://...` | 统一相对路径，配置化 |
| 未来迁 JBrowse 2 | 服务器已有 `/genome_browser/`（Sumai3 计划 §13.5 有记录） | 映射表里 `browser` 字段 + 两种 URL 模板，不要在前端硬编码版本号 |

---

## 11. 明确不做的事（避免过度设计）

1. **不要**在 `/api/blast/databases` 里给每个库内联全量 refseq 映射（2922 库 × 21~70 条会膨胀到 MB 级）——用懒加载端点。
2. **不要**按物种名/倍性关键词判断"有没有 JBrowse"（§4 的反例）。
3. **不要**为聚合库臆测一个"代表基因组"。
4. **不要**在 `genome_registry` 里塞 refseq 映射 JSON（那是 JBrowse 侧的事实，变更由 JBrowse 数据目录驱动）——独立 JSON 产物 + `coverage` 端点更可控。
5. **不要**默认自动 `window.open`。

---

## 附：一分钟核对清单

```bash
# 1) 有多少基因组有 JBrowse
curl -s https://wheatomics.sdau.edu.cn/api/genomes/stats | jq '.data.totals'
# {"total":316,"jbrowse":"215", ...}

# 2) JBrowse 数据集清单
curl -s https://wheatomics.sdau.edu.cn/api/jbrowse/datasets | jq '.data.total'   # 219

# 3) 某个 BLAST 库所属组装 & 序列命名
curl -s "https://wheatomics.sdau.edu.cn/api/blast/database-example?db=AABBDD_AK58.genome"
curl -s "https://wheatomics.sdau.edu.cn/api/sequence/chromosomes?database=AABBDD_AK58.genome"

# 4) 对应 JBrowse 数据集的权威 refseq 名与长度
curl -s https://wheatomics.sdau.edu.cn/jbrowse-1.12.3-release/AK58/seq/refSeqs.json | head -c 200
```
