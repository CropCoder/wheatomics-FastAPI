# 阶段 0 实现 A：核心代码修复（blast 关键词 / registry SUB+overrides+web_blast / 三个静态页）

> 任务：共享任务板 **task-4**（阶段 0 实现 A）。工作目录 `FastAPI_backend_Port8000`。
> 日期：2026-11-11。执行：teammate `impl-core`。
> 结论：**4 处代码修复全部完成，本地验证全部通过**；未跑任何需要 MySQL/服务的脚本，未 git commit，未碰生产服务器。

## 0. 一句话结论

4 个新二倍体 Aegilops 基因组（`MM_Aegilops_comosa_IPK_AE783` / `CC_Aegilops_markgrafii_EKC105_RL5723` / `UU_Aegilops_umbellulata_IPK_AE740` / `NN_Aegilops_uniaristata_IPK_AE680`）在**仓库代码层面已就绪**：

- BLAST 三库名（`.genome` / `.add_Description.cds` / `.add_Description.pep`）→ 全部归入 `other_triticeae`；
- `SUB[MM/CC/UU/NN]` 齐全（收尾脚本 `--check-name` step 1 可读）；
- registry `overrides` 含 4 条完整元数据（含 `chromosome_count=7`、`assembly_level=Chromosome`，不会被 `.fai` 序列数污染）；
- `web_blast_group` 判定已适配 wheatBLAST SPA（不再恒为 0）；
- 三个静态页 diploid 分类数组含 `CC`/`NN`。

## 1. 改动清单（file:line）

| # | 文件 | 行（改后） | 改动 | 生效方式 |
|---|---|---|---|---|
| 1 | `app/api/routers/blast.py` | **389–394** | `other_triticeae.keywords` 追加 7 个物种专名：`aegilops_markgrafii` `aegilops_uniaristata` `markgrafii` `uniaristata` `aemarkgrafii` `aeuniaristata` `aeumbellulata`（附 3 行中文说明） | `git pull` + `systemctl restart wheatomics-api` |
| 2 | `scripts/rebuild_genome_registry.py` | **606–607** | `SUB` 映射追加 `"CC": "C", "NN": "N"`（MM/UU 原有） | 无需重启；收尾脚本 step 1 直接解析本文件 |
| 3 | `scripts/rebuild_genome_registry.py` | **476–514** | Web BLAST flag 判定：先探测 SPA 页面（`wheatBLAST SPA` / `blast-db-cats` / 无 `<optgroup>` 且含 `api/blast/databases`）→ SPA 模式下 `blast_genome_db` 非空即 `web_blast_group=1`，`usage.frontend="/blast/blast.html (wheatBLAST SPA)"`；旧页面保留原 optgroup 判定 fallback | 下次跑 rebuild 生效 |
| 4 | `scripts/rebuild_genome_registry.py` | **891–957** | `overrides` 追加 4 条（`MM_…`/`CC_…`/`UU_…`/`NN_…`，键=数据集名），字段见 §2 | 下次跑 rebuild 生效 |
| 5 | `app/static/interval/index.html` | **255** | `TABLE_CATEGORIES` 的 `id:'diploid'` groups 加入 `'CC', 'NN'` | `git pull` 后刷新页面（StaticFiles 直接读仓库目录） |
| 6 | `app/static/PfamSearch/index.html` | **181** | 同上（`TABLE_CATEGORIES` diploid） | 同上 |
| 7 | `app/static/caps/index.html` | **431** | 同上（`BLAST_CATEGORIES` diploid，数组原已含 `MMUU`） | 同上 |

`git diff --numstat`（仅本任务 5 个文件）：

```
8	0	app/api/routers/blast.py
1	1	app/static/PfamSearch/index.html
1	1	app/static/caps/index.html
1	1	app/static/interval/index.html
90	1	scripts/rebuild_genome_registry.py
```

> ⚠ `app/api/routers/blast.py` 在本任务开始前工作树已有 **2 处未提交改动**（`FileResponse` import、`SEPARATE_AGGREGATE_DBS` 增 `PacBioFullLengthcDNA.Triticum_aestivum`）。本任务**只追加**了上述关键词块（`git diff` 中为 `@@ -384,6 +386,12 @@` 一个 hunk），其余原样未动。

## 2. overrides 数据（4 条，值与出处）

| 字段 | MM_comosa | CC_markgrafii | UU_umbellulata | NN_uniaristata |
|---|---|---|---|---|
| `ploidy` | MM | CC | UU | NN |
| `species` | Aegilops comosa | Aegilops markgrafii | Aegilops umbellulata | Aegilops uniaristata |
| `cultivar_or_line` | IPK-AE783 | EKC105_RL5723 | IPK-AE740 | IPK-AE680 |
| `assembly_accession` | GCA_052815735.2 | GCA_052815875.1 | GCA_060308565.1 | GCA_052815765.1 |
| `genome_size` (bp) | 4407741597 | 3577170360 | 4268089219 | 4475943907 |
| `gene_count` | 51203 | 47246 | 49677 | 50416 |
| `te_content` | 0.882 | 0.863 | 0.872 | 0.879 |
| `source_md5` | 38b8436f…1a122a | 2a55e0ca…6a077a | 1766c56e…6628bb | b9b85567…89123eb |

公共字段：`assembly_level="Chromosome"`、`chromosome_count=7`、`doi="10.1186/s12870-026-10046-2"`、`paper_title="Chromosome-level reference genome assemblies and annotation of four diploid Aegilops"`、`journal="BMC Plant Biology"`、`publication_year=2026`、`annotation_status="available"`、`annotation_source="Zenodo 22681907 (4DWheat, HC+LC gene models + EDTA TE)"`、`annotation_doi="10.5281/zenodo.22681907"`、`source_url`（按 GCA 拼 NCBI FTP 目录，例 `https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/052/815/735/GCA_052815735.2_ASM5281573v2/`）、`notes`（一句话：seqs=chr+unplaced、HC/LC 拆分、BUSCO protein、HiFi+Bionano+Hi-C、Zenodo 22681907）。

**值出处**：`docs/plans/aegilops4_2026-11/PAPER_DATA.md` §2.2（Table 3 基因数/HC/LC/BUSCO protein）、§2.3（Table 2 Total TE）、§4.1（NCBI GCA/FTP/md5/总长/序列数）。

## 3. 验证命令与输出摘录（全部本地 python3，无 MySQL/服务）

### V1 语法

```bash
$ python3 -m py_compile app/api/routers/blast.py scripts/rebuild_genome_registry.py
PY_COMPILE OK
```

### V2 AST 读回 `DB_CLASSIFICATION`，12 库名分类模拟（4 DS × 3 后缀）

```
categories: ['aggregated', 'hexaploid_wheat', 'tetraploid_wheat', 'diploid_wheat', 'triticale',
             'thinopyrum_ponticum', 'rye', 'other_triticeae', 'barley']
other_triticeae keyword count: 21   # 原 14 + 新增 7
all 7 required keywords present: True

MM_Aegilops_comosa_IPK_AE783            genome=other_triticeae cds=other_triticeae pep=other_triticeae
CC_Aegilops_markgrafii_EKC105_RL5723    genome=other_triticeae cds=other_triticeae pep=other_triticeae
UU_Aegilops_umbellulata_IPK_AE740       genome=other_triticeae cds=other_triticeae pep=other_triticeae
NN_Aegilops_uniaristata_IPK_AE680       genome=other_triticeae cds=other_triticeae pep=other_triticeae
ALL 12 -> other_triticeae: True

# 无下划线缩写名同样命中
MM_AeComosa_AE783.genome           -> other_triticeae
CC_AeMarkgrafii_EKC105_RL5723.genome -> other_triticeae
NN_AeUniaristata_IPK_AE680.genome  -> other_triticeae
UU_AeUmbellulata_IPK_AE740.genome  -> other_triticeae

# 回归：既有库分类不变
AABBDD_AK58.genome                 -> hexaploid_wheat
AABB_Kronos.genome                 -> tetraploid_wheat
Aegilops_tauschii_AL8_78.genome    -> diploid_wheat
MM_AeComosa_PI551049.genome        -> other_triticeae
AABBRR_PT.genome                   -> triticale
Thinopyrum_ponticum_decaploid...   -> thinopyrum_ponticum
Secale_cereale.genome              -> rye
Hordeum_vulgare_Morex.genome       -> barley
```

### V3 AST 读回 `SUB` 与 `overrides`

```
SUB['MM'] = 'M' | SUB['CC'] = 'C' | SUB['UU'] = 'U' | SUB['NN'] = 'N'   # total keys: 21

[OK] MM_Aegilops_comosa_IPK_AE783          ploidy=MM chrom=7 size=4407741597 genes=51203 te=0.882 GCA=GCA_052815735.2
[OK] CC_Aegilops_markgrafii_EKC105_RL5723  ploidy=CC chrom=7 size=3577170360 genes=47246 te=0.863 GCA=GCA_052815875.1
[OK] UU_Aegilops_umbellulata_IPK_AE740     ploidy=UU chrom=7 size=4268089219 genes=49677 te=0.872 GCA=GCA_060308565.1
[OK] NN_Aegilops_uniaristata_IPK_AE680     ploidy=NN chrom=7 size=4475943907 genes=50416 te=0.879 GCA=GCA_052815765.1
all overrides match expected values: True      # 逐字段比对 source_url/source_md5/notes 存在性
```

### V4 Web BLAST 逻辑（**从源码行 476–514 抽取后真实执行**，三种 fixture）

```
real repo app/static/blast2/index.html: len=176617 | optgroup=0 | 'wheatBLAST SPA'=True
                                        | blast-db-cats=True | api/blast/databases=True
blast html: wheatBLAST SPA detected -> web_blast_group = 1 when blast_genome_db exists

SPA fixture（真实 SPA 页面）:
  MM_Aegilops_comosa_IPK_AE783          web_blast_group=1 usage={"databank":"MM_Aegilops_comosa_IPK_AE783",
                                             "frontend":"/blast/blast.html (wheatBLAST SPA)"}
  CC_Aegilops_markgrafii_… / UU_… / NN_…  web_blast_group=1（同上，databank=各自库名）
  AABBDD_AK58                           web_blast_group=1
  NoBlastDb（无核酸库）                  web_blast_group=0   usage=null

old-page fallback（含 <optgroup> 的旧 ViroBLAST fixture）:
  Aegilops_tauschii_AL8_78   -> 1  databank="Aegilops_tauschii_AL8_78_chromosomes"
  AABBDD_AK58                -> 1  databank="AABBDD_AK58"
  CC_Aegilops_markgrafii_…   -> 0（旧页面未手写该库 → 保持原逻辑，符合 fallback 设计）

empty-html fixture: web_blast_group=0
```

### V5 三个静态页（python 精确解析数组 + node 语法校验 + 分类模拟）

```
app/static/interval/index.html:255     var TABLE_CATEGORIES : 8 categories | diploid = ['AA','DD','SS','MM','CC','NN','TT','UU','VV','DDNN']  (10)
app/static/PfamSearch/index.html:181   var TABLE_CATEGORIES : 8 categories | diploid = 同上                                            (10)
app/static/caps/index.html:431         var BLAST_CATEGORIES : 8 categories | diploid = ['AA','DD','SS','MM','CC','NN','TT','UU','VV','DDNN','MMUU'] (11)
'CC' present: True | 'NN' present: True（三页均 True，无重复、无跨分类重复）

categoryIdForGroup（页面 JS 逻辑复刻）：MM/CC/UU/NN/DDNN -> diploid（三页）；caps MMUU -> diploid
caps blastDbPrefix：MM_/CC_/UU_/NN_Aegilops_*.genome -> diploid

infer_karyotype(table, Polyploidy)（app/core/genome_ordering.py，未改）：
  Genefunc_MM_Aegilops_comosa_IPK_AE783_table        -> karyotype='MM' -> diploid
  Genefunc_CC_Aegilops_markgrafii_EKC105_RL5723_table-> karyotype='CC' -> diploid
  Genefunc_UU_Aegilops_umbellulata_IPK_AE740_table   -> karyotype='UU' -> diploid
  Genefunc_NN_Aegilops_uniaristata_IPK_AE680_table   -> karyotype='NN' -> diploid

node --check（node v22.22.3）:
  app/static/interval/index.html   node --check rc=0 | TABLE_CATEGORIES OK 8
  app/static/PfamSearch/index.html node --check rc=0 | TABLE_CATEGORIES OK 8
  app/static/caps/index.html       node --check rc=0 | BLAST_CATEGORIES OK 8
```

### V6 收尾脚本门禁模拟（`--check-name` step 1/2 的读取逻辑，直接作用于改后仓库文件）

```
gate step1 SUB parser（regex `SUB\s*=\s*\{(.*?)\}`）-> keys: 21
[OK] MM_Aegilops_comosa_IPK_AE783          SUB[MM]=M | classify=other_triticeae
[OK] CC_Aegilops_markgrafii_EKC105_RL5723  SUB[CC]=C | classify=other_triticeae
[OK] UU_Aegilops_umbellulata_IPK_AE740     SUB[UU]=U | classify=other_triticeae
[OK] NN_Aegilops_uniaristata_IPK_AE680     SUB[NN]=N | classify=other_triticeae
```

> step 2 的库名集合按 `<DS>.genome`、`<DS>.genome_Chr1M`、`<DS>.add_Description.cds|pep` 模拟。

## 4. 验收对照（task-4 要求 → 结果）

| task-4 验收项 | 结果 |
|---|---|
| `python3 -m py_compile` 两文件通过 | ✅ V1 |
| AST 读回 `DB_CLASSIFICATION`，4 DS×3 库名 → 全 `other_triticeae` | ✅ V2（且缩写名/回归库均验证） |
| AST/正则确认 `SUB` 含 CC/NN | ✅ V3、V6 |
| `overrides` 含 4 键且 `chromosome_count==7` | ✅ V3（全字段比对 + `source_url`/`notes` 非空） |
| 三页面 diploid groups 含 'CC','NN' | ✅ V5（python 解析数组 + node --check） |
| 不跑需要 MySQL 的脚本 | ✅ 未跑（本地无 MySQL/pymysql；`rebuild_genome_registry.py` 仅 AST/片段分析） |
| `bash -n scripts/finish_genome_integration.sh` | 不适用（该文件由 task-6 负责，不属于本任务 write scope） |
| 只改任务列出的文件、不 commit | ✅ 见 §1 numstat，5 个文件 |

## 5. 风险与遗留（交接给 Lead / 服务器执行阶段）

| # | 事项 | 说明 | 建议动作 |
|---|---|---|---|
| P1 | **`web_blast_group` 判定语义变化** | SPA 模式下所有「有核酸库」的 registry 行都会置 1（原来靠页面手写字符串命中）。这是修复"恒 0"的预期行为，但 `stats.web_blast`（线上当前 200）会变成约等于核酸 BLAST 库记录数。**未在本地对生产数据做 dry-run**（无 MySQL）。 | 服务器上先 `python3 scripts/rebuild_genome_registry.py --dry-run` 看 `preview.web_blast` 与 diff 范围，再正式跑。 |
| P2 | **4 条 overrides 会让 registry 出现 4 个新行** | 只要跑 rebuild，`/api/genomes` totals 316→320、`by_ploidy` 增加 MM/CC/UU/NN 各 1；在 JBrowse/BLAST 数据未上传前这些行 `jbrowse_dataset/blast_*` 为空（页面无链接）。任务未要求在 overrides 里加 `visible=0`，故未加。 | 正常流程：数据就绪后由收尾脚本 step 7 重跑 rebuild + step 8 写回 flags，最终一致；若需"先藏后显"，可在收尾完成后重跑，或临时加 `"visible": 0`（需 Lead 决定）。 |
| P3 | `subgenomes` 不由 overrides 写入 | `SUB` 在 rebuild 中仅用于策展表行（`:674`）；新 4 行的 `subgenomes` 由**收尾脚本 step 8**从 `SUB` 写回（`finish_genome_integration.sh:190-203、:823`），`SUB[CC/NN]` 已补齐，链路 OK。 | 无需改；若只跑 rebuild 不跑 finish，`subgenomes` 为空属预期中间态。 |
| P4 | `parse_jbrowse_cards()` 仍按旧 `card-body` 解析 | 新版 JBrowse V2 `asm-card` 匹配不到 → 卡片元数据不影响 registry，本批由 overrides 覆盖。 | 长期可另立任务适配（不在本任务 scope；见 PLATFORM_BASELINE C10）。 |
| P5 | `blast.py` 工作树既有未提交改动 | 2 处（`FileResponse`、`PacBioFullLengthcDNA.Triticum_aestivum`）在任务开始前已存在，本任务未动。 | 提交/下发时与本次关键词改动一并 review（属同一工作树既有 M 状态）。 |
| P6 | interval / PfamSearch 分类数组不含 `MMUU` | 仅 caps 数组有 `MMUU`（既有历史差异；4 个新 DS 为 MM/CC/UU/NN 不受影响）。 | 不在本任务范围；若后续有 MMUU 表需展示，另补两页。 |
| P7 | 无法本地端到端跑 rebuild | 本地 python3=3.7 且无 pymysql/MySQL；脚本用 `str | None`（3.10 语义）+ `from __future__ import annotations`，线上环境（≥3.10）可用；本地 `py_compile` 通过。 | 服务器执行时按 SOP：`source .env` → `--dry-run` → 正式；Python 用仓库约定解释器（`/home/fei/mambaforge/envs/zjw/bin/python3`）。 |

## 6. 服务器生效步骤（本任务相关的 3 类改动）

```bash
# 1) Python 改动（blast.py）需重启 API
cd /var/www/FastAPI_backend_Port8000 && git pull origin main
sudo systemctl restart wheatomics-api

# 2) registry 脚本改动：不需要重启，收尾流程 step 7 会执行（或手工）
source .env && python3 scripts/rebuild_genome_registry.py --dry-run   # 先看 preview
source .env && python3 scripts/rebuild_genome_registry.py             # 正式

# 3) 三个静态页：StaticFiles 直接读仓库目录，git pull 后刷新（无缓存版本号时 Ctrl+F5）
```

## 7. 参考（只读，未改动）

- `docs/plans/aegilops4_2026-11/PAPER_DATA.md`（§2.2/§2.3/§4.1/§5）
- `docs/plans/aegilops4_2026-11/PLATFORM_BASELINE.md`（C2/C4-C6/C8/C9、R2/R8）
- `docs/plans/aegilops4_2026-11/WORKFLOW_GAP.md`（§3.2 SUB gap、D11 web_blast）
- `/Users/mashengwei/.agents/skills/lab-server/scripts/finish_genome_integration.sh`（门禁 step 1/2 读取逻辑，只读模拟）
