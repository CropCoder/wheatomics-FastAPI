# 阶段 0 实现 C：finish_genome_integration.sh 适配 JBrowse V2.0 / wheatBLAST SPA（PHASE0_FINISH）

> 任务：task-6（阶段 0 实现 C）。产出：`scripts/finish_genome_integration.sh`（v2，仓库源）+ 本文档。
> 起点：`~/.agents/skills/lab-server/scripts/finish_genome_integration.sh`（1022 行，md5 `e4886d0c21f1667be5e672e330ba75d7`，**原文件未改**）。
> 测试：只在本机 `/tmp/wm_fake/` 的 fake docroot / fake repo 上跑，未连生产、未改仓库其它文件。

## 0. 结论摘要

| 项 | 结果 |
|---|---|
| 语法 | `bash -n` 通过；`--help` 正常（含新增选项与环境变量说明） |
| 版本 | 1022 行 → **1400 行**；md5 **`d8162ac0d61a3e503cfb81646c05ddc2`**；权限 `755` |
| `--check-name` ×4 DS（MM/CC/UU/NN） | **全部 `[OK] 命名可直接开跑`**（rc=0）；CC/NN 仅因 `#group-cc`/`#group-nn` 不存在给 WARN（收尾时自动新建） |
| V2 卡片插入（既有分区 `#group-mm`） | 卡进 `asm-grid` 末尾；hero `213→214`、`asm-status 206/22→207/22`、`#group-mm 1→2 assemblies`；`asm-card` 206→207；`blast.html` md5 不变 |
| V2 新建分区（CC） | 新建 `<section class="asm-group" id="group-cc">`；hero `213→214`、`asm-status 206/22→207/23`、新分区 `1 assembly` |
| 幂等 | 第二次运行 `[SKIP] 卡片已存在`，页面 md5 完全不变，计数不变 |
| Legacy 旧页面回退 | 旧 `<h5>`+`card-group` 插卡、旧 `<optgroup>`+hidden input+All genes/All proteins 全部照旧，verify rc=0 |
| BLAST 断言 | fake API 三分支：命中→OK；分类错→FAIL；缺库→FAIL；`curl` 不可达→WARN（不 FAIL） |
| 前置依赖 | CC/NN 门禁依赖 task-4 的 `SUB` + `DB_CLASSIFICATION` 关键词（当前**工作树已含未提交改动**，部署服务器前需一并提交/pull） |

---

## 1. 改动点（原行号 → 新逻辑）

> 原行号指 1022 行旧脚本；新行号指 1400 行新脚本。

| # | 原位置 | 旧逻辑（问题） | 新逻辑 |
|---|---|---|---|
| 1 | `:1-72` 头部注释 | 按 2026-10 旧页面描述 | 加「★ 2026-11 适配 JBrowse V2 / wheatBLAST SPA；二倍体 MM/CC/UU/NN 支持」；补 `WHEATOMICS_*` 路径 env 表、新选项、二倍体示例 |
| 2 | `:76-88` 常量路径 | 写死生产路径，无法本地测试 | 全部改为 `${WHEATOMICS_*:-默认值}`：`JBROWSE_HTML` / `BLAST_HTML` / `BLASTDB` / `JBROWSE` / `REPO` / `DDL_ENV` / `API` / `BACKUP_ROOT` / `DATA_ROOT` / `ZJW_PY` / `BLASTX`（默认值与旧版逐一相同；`APP_ENV="${REPO}/.env"` 不变） |
| 3 | `:91` `usage()` | `sed -n '2,64p'` 按固定行号截头部，头部改版即错位 | `awk` 打印第 2 行到第二个 `# ====` 分隔线（自适应行号） |
| 4 | `:96-132` 参数解析 | 无 V2/测试相关选项 | 新增 `--section-title` / `--section-desc` / `--search-extra` / `--require-section`；其余参数与语义不变 |
| 5 | `:236-248` check_name **step3** | 只读旧 ViroBLAST `<optgroup label>`，现网 SPA optgroup=0 → **任何基因组都 BLOCK** | 检测 `wheatBLAST SPA` / `blast-db-cats` / `api/blast/databases` 且无 `<optgroup>` → 打印 `[SPA] 新版 wheatBLAST 动态取库，跳过 optgroup 断言` 并**视为通过**；旧页面才做原 optgroup 断言；`gmap` 增补 `Other Triticeae → Other Triticeae genome`（旧页面回退用） |
| 6 | `:249-269` check_name **step4** | 用 `<h5>&nbsp;…</h5>` 找分区，V2 页面永远为空 | 先探测 V2（`class="…asm-grid"` 或 `section.asm-group`）；V2 解析 `id="group-([a-z0-9-]+)"` 与 `<h2 class="asm-group-title">` 标题。`--section-existing` 支持 **group-id / #group-id / 分区标题** 三种写法；目标分区 `#group-<ploidy 小写>` 不存在时只 WARN + 建议新建（`--require-section` 时才 BLOCK）。旧页面保留原 `<h5>` 逻辑 |
| 7 | `:322-348` check_name 落盘 | plan 里 `jbrowseSection` 按旧 `<label> JBrowse` 标题 | V2 页面写 `jbrowseSection="group-<ploidy 小写>"`、新增 `jbrowsePageVersion/sectionTitle/sectionDesc/searchExtra`；正式运行的 plan 读取（原 `:390-436`）同步回读这三项，G0 缺省的定制参数在 G4 自动生效 |
| 8 | `:354-361` `GROUP` 推导 | `MM/CC/NN→Other`、`UU/HH→Diploid` | `AABB→Tetraploid`、`AABBDD→Hexaploid`、`AABBRR→Triticale`、`DD\|AA\|BB→Diploid`、`MM\|CC\|UU\|NN\|SS\|TT\|VV\|EE\|RR\|II\|PP\|GG→Other Triticeae`、其余 `Other` |
| 9 | `:462-464` `mapfile -t CHROMS` | bash 4+ 语法（macOS 默认 bash 3.2 无法跑） | `while IFS= read -r` 收集，语义相同（**为完成本机实测所必需**） |
| 10 | `:503-568` `step_jbrowse_card` | 插旧 `<div class="card">`，锚点 `<div id="cite"></div>`——V2 页面无此锚点 → `[ERR] 找不到 … 锚点` | **V2 分支**：① 在 `id="group-<ploidy 小写>"` 的 `<div class="asm-grid">` 末尾插 `article.asm-card`（`h3.asm-name` 链 `/jbrowse-1.12.3-release/?data=<DS>`、`p.asm-doi`）；② 无该 section 时在 `id="asm-groups"` 容器闭合 `</div>` 前新建完整 `<section class="asm-group" id="group-<ploidy>">`（标题/描述取 `--section-title/--section-desc`，默认 `<PLOIDY> genome`/物种）；③ 同步该 section `asm-group-count`（含单复数）、hero `<span class="news-stat"><strong>N</strong> assemblies`、`#asm-status` 的命名数/组数（新建 section 才 +1）；全部用 python 按字符位置精确替换并打印变更摘要；④ `--force`/`--dry-run` 语义保留；**旧页面分支原样保留**（h5+card-group+cite 锚点） |
| 11 | `:571-650` `step_blast_html` | 旧 ViroBLAST 机制（optgroup / hidden input / All genes），SPA 页必然 `[ERR] 找不到 optgroup` | 先检测 SPA（同上三特征且无 `<optgroup>`）→ 打印 `[SPA] 库清单由 /api/blast/databases 动态生成，跳过 HTML 修改` 并 `return 0`（不 FAIL）；旧页面原逻辑不变 |
| 12 | `:877-973` `verify()`（HTML 断言 `:879-887`） | grep 旧 `${DS}_chromosomes` / `${DS}.add_Description.cds=>`，SPA 下必 2 个 FAIL | JBrowse：改 `grep -q "?data=${DS}"`（新旧页面通用）。BLAST：SPA 页面改 `curl "${API}/api/blast/databases?program=blastn"` + python 解析 JSON，断言含 `${DS}.genome` 且分类匹配（`EXPECT_CAT` 支持分类 id 或 label，缺省 `other_triticeae`）——缺库/分类错 → FAIL，API 不可达 → WARN 不 FAIL；旧页面保留原 HTML 断言。其余（MySQL 行数、`.fai`、alias、`/api/*`、BLAST↔JBrowse 映射、`EXPECT_CAT` label 断言）保持 |
| 13 | `:974-995` `print_next_steps` | `${PLOIDY,,}` 是 bash 4+ 语法 | `tr '[:upper:]' '[:lower:]'`（bash 3.2 兼容）；文案补充「Web BLAST 分类」「sequence 缓存 1h」 |
| 14 | `:8-11` 完成事项说明 | 只描述旧卡片/旧 optgroup | 改为描述 V2/SPA 分支行为（旧页面兼容说明） |

未改动：step3 `.fai`、step4 Genefunc_registry、step5 聚合库 alias、step6-8 jbrowse_meta/registry/元数据写回、step9 BLAST↔JBrowse 映射、备份机制、`--skip-html`/`--skip-registry`/`--restart-api`/`--no-plan-check` 等参数语义。

### 1.1 V2 卡片 `data-search` 组成

`label` + `DS` + `doi:<DOI>` + `https://doi.org/<DOI>` + `--species` + `--search-extra` + `PLOIDY` + `GROUP` + `genome other triticeae species jbrowse`，全部小写、按空格切词去重。实测（MM）：

```
ae.comosa ipk-ae783 (m) mm_aegilops_comosa_ipk_ae783 doi:10.1186/s12870-026-10046-2
https://doi.org/10.1186/s12870-026-10046-2 aegilops comosa m genome mm other triticeae species jbrowse
```

### 1.2 计数规则（与页面 JS 重算口径一致）

| 元素 | 既有分区插入 | 新建分区插入 |
|---|---|---|
| `#group-<id> .asm-group-count` | N → N+1（**单复数正确**：`1 assembly` / `2 assemblies`） | `1 assembly` |
| hero `<span class="news-stat"><strong>N</strong> assemblies</span>` | +1 | +1 |
| `#asm-status` 命名数 | +1 | +1 |
| `#asm-status` 组数 | 不变 | +1 |

---

## 2. 本地实测（fake docroot，未接触生产）

### 2.1 测试环境搭建

```bash
F=/tmp/wm_fake
mkdir -p $F/{doc/blast,doc/blastdb,doc/jbrowse-1.12.3-release/{<DS>/seq},data,backup,repo/app/api/routers,repo/scripts,bin}

# 1) fake docroot：直接拷仓库里的现行页面（= 线上页面）
cp app/static/docpages/jbrowse.html   $F/doc/jbrowse.html
cp app/static/blast2/index.html       $F/doc/blast/blast.html
# 2) fake BLAST 库/数据集（MM、CC 各一套：.genome/.cds/.pep + 7 条 .genome_Chr* + refSeqs.json）
# 3) 聚合库 alias（DBLIST 行）、all_genomes_type.txt
# 4) 假 DB 账号/DDL env、假 repo（.env；SUB 已含 CC/NN、blast.py 已含 markgrafii/uniaristata 关键词）
# 5) PATH 前置假 mysql（COUNT(*) 查询回 1，其余空），API 指向不可达端口或本地 fake HTTP server
```

关键：**所有路径都用 `WHEATOMICS_*` 覆盖**，脚本不碰 `/var/www`。

```bash
export WHEATOMICS_REPO=/tmp/wm_fake/repo \
       WHEATOMICS_JBROWSE_HTML=/tmp/wm_fake/doc/jbrowse.html \
       WHEATOMICS_BLAST_HTML=/tmp/wm_fake/doc/blast/blast.html \
       WHEATOMICS_BLASTDB=/tmp/wm_fake/doc/blastdb \
       WHEATOMICS_JBROWSE=/tmp/wm_fake/doc/jbrowse-1.12.3-release \
       WHEATOMICS_DDL_ENV=/tmp/wm_fake/ddl.env \
       WHEATOMICS_DATA_ROOT=/tmp/wm_fake/data \
       WHEATOMICS_BACKUP_ROOT=/tmp/wm_fake/backup \
       WHEATOMICS_API=http://127.0.0.1:59999 \
       WHEATOMICS_BLASTX=/tmp/wm_fake/nonexistent-blastx
export PATH=/tmp/wm_fake/bin:$PATH
```

> 说明：check-name 的 step1/step2 读**仓库源码**，实测用**真实工作树**（`WHEATOMICS_REPO=$PWD`）跑通——
> task-4 的 `scripts/rebuild_genome_registry.py`（`SUB` 加 `"CC": "C", "NN": "N"`）与
> `app/api/routers/blast.py`（`other_triticeae.keywords` 加 `markgrafii/uniaristata`）已落在工作树
> （尚未 git commit），所以本次无需 fake repo 临时补丁即可通过。正式部署前仍需把这两处一并提交/pull。

### 2.2 `--check-name` ×4 DS（真实输出摘录）

```bash
DOI=10.1186/s12870-026-10046-2
bash scripts/finish_genome_integration.sh MM Aegilops_comosa_IPK_AE783 "$DOI" --check-name \
  --group "Other Triticeae" --cultivar IPK-AE783 --accession IPK-AE783 --species "Aegilops comosa"
# （CC/UU/NN 同理：CC_Aegilops_markgrafii_EKC105_RL5723 / UU_Aegilops_umbellulata_IPK_AE740 / NN_Aegilops_uniaristata_IPK_AE680）
```

| DS | SUB[PLOIDY] | 3 库分类 | step3（BLAST） | step4（JBrowse） | 结论 |
|---|---|---|---|---|---|
| `MM_Aegilops_comosa_IPK_AE783` | `M` ✓ | `other_triticeae` ×3 | `[SPA]` 通过 | `#group-mm` 存在 ✓ | **`[OK]`** rc=0 |
| `CC_Aegilops_markgrafii_EKC105_RL5723` | `C` ✓ | `other_triticeae` ×3 | `[SPA]` 通过 | `#group-cc` 不存在 → WARN「收尾时会新建」 | **`[OK]`** rc=0 |
| `UU_Aegilops_umbellulata_IPK_AE740` | `U` ✓ | `other_triticeae` ×3 | `[SPA]` 通过 | `#group-uu` 存在 ✓ | **`[OK]`** rc=0 |
| `NN_Aegilops_uniaristata_IPK_AE680` | `N` ✓ | `other_triticeae` ×3 | `[SPA]` 通过 | `#group-nn` 不存在 → WARN「收尾时会新建」 | **`[OK]`** rc=0 |

负向用例：`CC … --check-name --require-section` → `[WARN] 缺少目标分区 #group-cc（--require-section 已指定）` + `[BLOCK]` rc=3（符合「缺失默认只 WARN、显式要求才 BLOCK」）。

### 2.3 `--dry-run`（MM，自动读 name_plan.json）

```
[DRY] 将插入 #group-mm 的 asm-grid 末尾：Ae.comosa IPK-AE783 (M)
[DRY] 将同步计数：hero 213 → 214；asm-status 206/22 → 207/22；#group-mm 计数 1 → 2 assemblies
[SPA] 库清单由 /api/blast/databases 动态生成，跳过 HTML 修改
[DRY] samtools faidx …
```

> 注：`--dry-run` 末尾仍会跑 verify，对「尚未改动」的文件报 FAIL，因此 rc=1（**与 v1 语义相同**，不是回归）；
> 正式运行 rc=0。运维按 `[DRY]` 行核对计划即可。

### 2.4 V2 真实插入 + 幂等（既有分区 `#group-mm`）

```bash
bash scripts/finish_genome_integration.sh MM Aegilops_comosa_IPK_AE783 "$DOI" --skip-registry
# rc=0；执行步骤计数 5；失败计数 0
```

输出：

```
[OK] 已插入 #group-mm 的 asm-grid 末尾：Ae.comosa IPK-AE783 (M)
[OK] 计数已同步：hero 213 → 214；asm-status 206/22 → 207/22；#group-mm 计数 1 → 2 assemblies
[SPA] 库清单由 /api/blast/databases 动态生成，跳过 HTML 修改
[OK] jbrowse.html 含卡片（?data=MM_Aegilops_comosa_IPK_AE783）
```

diff 摘要（`app/static/docpages/jbrowse.html` 拷贝 → fake docroot）：

```diff
-            <span class="news-stat"><strong>213</strong> assemblies</span>
+            <span class="news-stat"><strong>214</strong> assemblies</span>
-…Showing <strong>206</strong> named assemblies in <strong>22</strong> genome groups…
+…Showing <strong>207</strong> named assemblies in <strong>22</strong> genome groups…
-            <span class="asm-group-count">1 assembly</span>
+            <span class="asm-group-count">2 assemblies</span>
             <article class="asm-card" data-search="ae.comosa pi551049(mm) …">…</article>
+            <article class="asm-card" data-search="ae.comosa ipk-ae783 (m) mm_aegilops_comosa_ipk_ae783 doi:10.1186/…">
+              <h3 class="asm-name"><a href="/jbrowse-1.12.3-release/?data=MM_Aegilops_comosa_IPK_AE783">Ae.comosa IPK-AE783 (M)</a></h3>
+              <p class="asm-doi"><a href="https://doi.org/10.1186/s12870-026-10046-2" target="_blank" rel="noopener">doi:10.1186/s12870-026-10046-2</a></p>
+            </article>
```

校验：`article.asm-card` 206→**207**；`section.asm-group` 保持 **22**；`?data=` 链接 213→**214**（与 hero 一致）；
结构标签 `section/div/article/main/nav` 配平；`blast.html` md5 前后一致（`0ba52e21…`，SPA 未改）；备份目录生成 6 个 `.bak`（jbrowse/blast/3 个 alias/type 表）；`.fai` 生成。

**幂等（第二次同命令）**：`[SKIP] 卡片已存在（?data=MM_Aegilops_comosa_IPK_AE783）`，jbrowse/blast md5 完全不变，计数保持 207/214/2，rc=0。

### 2.5 V2 新建分区（CC，`#group-cc` 不存在）

```bash
bash scripts/finish_genome_integration.sh CC Aegilops_markgrafii_EKC105_RL5723 "$DOI" --skip-registry
```

```
[INFO] 目标分区 #group-cc 尚不存在 → 收尾时新建
[OK] 已新建 section #group-cc：Ae.markgrafii EKC105_RL5723 (C)
[OK] 计数已同步：hero 213 → 214；asm-status 206/22 → 207/23；新建 #group-cc（1 assembly）
```

diff 摘要：在 `id="asm-groups"` 容器闭合 `</div>` 前新建完整 section（标题/描述/搜索词来自 G0 落盘的
`--section-title "CC Aegilops markgrafii"`、`--section-desc "Aegilops markgrafii (C genome)"`、`--search-extra`）：

```html
<section class="asm-group" id="group-cc" aria-labelledby="group-cc-title">
  <div class="asm-group-head">
    <h2 class="asm-group-title" id="group-cc-title"><span class="asm-formula">CC Aegilops markgrafii</span> <span class="asm-desc"><i>Aegilops markgrafii (C genome)</i></span></h2>
    <span class="asm-group-count">1 assembly</span>
  </div>
  <div class="asm-grid">
    <article class="asm-card" data-search="ae.markgrafii ekc105_rl5723 (c) cc_aegilops_markgrafii_ekc105_rl5723 doi:10.1186/… aegilops markgrafii c genome ekc105 cc other triticeae species jbrowse">…</article>
  </div>
</section>
```

校验：`asm-group` 22→**23**；`asm-card` 206→**207**；hero **214**；`asm-status 207/23`；结构配平；第二次运行 md5 不变。

### 2.6 Legacy 旧页面回退（合成旧版页面）

用旧格式合成页验证（`<h5>` 分区 + `card-group` + `<div id="cite"></div>`；`<optgroup>` + hidden input + All genes/All proteins）：

- `--section-existing "Allotetraploid Wheat JBrowse"` → `[OK] 已插入 'Allotetraploid Wheat JBrowse' 分区`；
- 无 `--section-existing` → `[OK] 已新建分区并插入卡片`（锚点 `#cite` 前）；
- `step_blast_html` → `[OK] 已修改: group option, hidden input, all_genes, all_proteins`；
- `verify()` 走旧页面分支：`[OK] blast.html 含 group` + `[OK] blast.html All genes 含成员`，rc=0。

### 2.7 BLAST API 断言三分支（本地 fake HTTP server）

| 场景 | 输出 | 结果 |
|---|---|---|
| `categories[].id=other_triticeae` 含 `${DS}.genome` | `[OK] /api/blast/databases 含 …（分类 Other Triticeae genome）` | rc=0 |
| 分类错为 `diploid_wheat` | `[FAIL] BLAST 分类不符：diploid_wheat:…（期望含 'Other Triticeae genome'）` | rc=1 |
| 库清单缺 `${DS}.genome` | `[FAIL] /api/blast/databases 未含 …` | rc=1 |
| curl 不可达 | `[WARN] … 不可达，跳过 BLAST 库清单断言` | 不 FAIL |

### 2.8 语法 / 帮助

```bash
bash -n scripts/finish_genome_integration.sh && echo SYNTAX OK   # SYNTAX OK
scripts/finish_genome_integration.sh --help                      # 头部说明 + env 表 + 新选项正常
```

---

## 3. 服务器安装 / 部署（本会话未执行，仅列命令）

```bash
# 0) 前置：task-4 的代码改动必须先到服务器（否则 CC/NN 的 check-name 仍会 BLOCK）
#    app/api/routers/blast.py（DB_CLASSIFICATION 关键词）
#    scripts/rebuild_genome_registry.py（SUB 的 CC/NN）
#    本地 commit → push（github+gitee）→ 服务器 git fetch && git merge --ff-only

# 1) 本机 lab-server 技能目录（源：仓库 scripts/）
cp scripts/finish_genome_integration.sh ~/.agents/skills/lab-server/scripts/finish_genome_integration.sh
chmod +x ~/.agents/skills/lab-server/scripts/finish_genome_integration.sh
md5sum scripts/finish_genome_integration.sh ~/.agents/skills/lab-server/scripts/finish_genome_integration.sh
#   期望均为 d8162ac0d61a3e503cfb81646c05ddc2

# 2) 生产服务器 _prep 目录（经 lab-server 隧道，见 docs/workflow/README.md）
bash ~/.agents/skills/lab-server/scripts/wheatomics.sh tunnel   # 另开终端保持隧道
scp -P 2222 scripts/finish_genome_integration.sh \
    fei@127.0.0.1:/var/www/data/masw_data/_prep/
ssh -p 2222 fei@127.0.0.1 'chmod +x /var/www/data/masw_data/_prep/finish_genome_integration.sh && \
  md5sum /var/www/data/masw_data/_prep/finish_genome_integration.sh'

# 3) 服务器上先 --dry-run，再正式跑（G4）
ssh -p 2222 fei@127.0.0.1
cd /var/www/data/masw_data/_prep
./finish_genome_integration.sh MM Aegilops_comosa_IPK_AE783 10.1186/s12870-026-10046-2 \
  --skip-registry --dry-run     # 先看计划
```

> ⚠️ 页面落点：脚本改的是 **docroot** 的 `/var/www/html/jbrowse.html`（生产生效页）。仓库源页
> `app/static/docpages/jbrowse.html` 必须同步加上同样的卡片（本批按计划 C7 手工/其它任务维护），
> 否则下次 `scripts/deploy_doc_pages.py` 会用旧源覆盖回去。BLAST 页无需任何改动（SPA 动态取库）。

---

## 4. 已知行为 / 注意事项

1. **依赖 task-4 代码**：`--check-name` 的 step1/step2 读**服务器仓库**的 `rebuild_genome_registry.py` / `blast.py`；
   `SUB` 缺 CC/NN 或分类缺 `markgrafii/uniaristata` 关键词时，CC/NN 仍会 BLOCK（MM/UU 不受影响）。
2. **`--dry-run` rc=1**：与 v1 相同——dry-run 不改文件，verify 对未改动项报 FAIL。正式运行 rc=0。
3. **Jump-to chips 不自动更新**：`jbrowse.html` 的 6 个 `v2-chip` 是手工硬编码、JS 不重算（本任务范围外）。
4. **卡片标题为纯文本**：`--label` 会做 HTML escape（防止注入）；页面既有卡片用 `<i>` 斜体物种名，属装饰差异，可在页面源里手工润色。
5. **新建分区位置**：按任务要求插在 `#asm-groups` 容器闭合 `</div>` 前（即隐藏的 `asm-placeholders` 之后），
   因此视觉顺序在列表末尾；如需紧邻某个分区，可改用 `--section-existing <邻近分区 group-id/标题>` 让卡片插进该分区。
6. **hero / `#asm-status` 静态计数仅 +1**：页面加载后 JS 仍会按 DOM 重算（口径一致）。
7. **bash 兼容性**：为在本机（macOS bash 3.2）完成强制实测，`mapfile`/`${VAR,,}` 两个 bash 4 语法已换成等价写法；
   在 Linux 生产上行为不变。
8. 其余步骤（`.fai`、Genefunc_registry、聚合库 alias、jbrowse_meta、registry 重建、元数据写回、BLAST↔JBrowse 映射）代码零改动。

---

## 5. 交付物

| 文件 | 说明 |
|---|---|
| `scripts/finish_genome_integration.sh` | v2 收尾脚本（1400 行，md5 `d8162ac0…`，`755`），仓库源 |
| `docs/plans/aegilops4_2026-11/PHASE0_FINISH.md` | 本文档（改动点 / 实测 / 安装 / 注意事项） |

测试产生的全部 fake 环境在 `/tmp/wm_fake/`（不入库）。
