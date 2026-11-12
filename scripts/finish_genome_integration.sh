#!/bin/bash
# ============================================================================
# finish_genome_integration.sh — WheatOmics 新基因组上线收尾（前端 + 登记 + 元数据）
#
# 把 SOP (references/wheatomics-new-genome-sop.md) §5 / §6 的手工步骤固化为
# 一条幂等命令。前提：add_wheat_genome.sh 流水线已跑完（[SUCCESS]）。
#
# ★ 2026-11 适配 JBrowse V2 / wheatBLAST SPA；二倍体 MM/CC/UU/NN 支持
#   · JBrowse 已是 V2.0（app/static/docpages/jbrowse.html：.asm-group / .asm-card /
#     .asm-grid + hero/静态计数）；旧脚本按 <h5> 分区 + <div class="card-group"> +
#     <div id="cite"></div> 锚点写，现网会找不到锚点/插错位置。
#   · Web BLAST 已是 wheatBLAST SPA（app/static/blast2/index.html，线上 /blast/blast.html），
#     库清单由 /api/blast/databases 动态生成、页面无手写 <optgroup>；旧逻辑必 FAIL。
#   本版自动识别页面版本：V2/SPA 走新逻辑，旧页面保留原 legacy 逻辑（向后兼容）。
#
# 完成的事：
#   1) JBrowse 前端卡片      $JBROWSE_HTML（V2：asm-card 插到 id="group-<ploidy 小写>"
#                                           的 asm-grid 末尾，并同步 hero 数 / asm-status /
#                                           asm-group-count 计数；无该分区则新建整个 section）
#   2) Web BLAST group       $BLAST_HTML（SPA：跳过 HTML 改写，库清单动态来自 API；
#                                          旧页面：option + hidden input + All genes/All proteins）
#   3) PrimerServer2 .fai     samtools faidx（genome / add_Description.cds）
#   4) Genefunc_registry 行   Genefuncdb.Genefunc_registry（upsert）
#   5) 聚合库 alias           all_genomes.nal / all_gene.nal / all_protein.pal
#                            + all_genes.nal / all_proteins.pal（GetSequence by-gene 用）
#                            + all_genomes_type.txt
#   5b) GetSequence 文档示例   /var/www/html/doc/getsequence_search.txt（新增/更新本基因组行）
#   6) jbrowse_meta 导入       scripts/import_jbrowse_meta.py --dataset
#   7) genome_registry 重建    scripts/rebuild_genome_registry.py
#   8) 元数据写回              genome_registry 的 DOI/标题/期刊/年份/物种等
#   9) BLAST↔JBrowse 映射      scripts/build_blast_jbrowse_map.py（BLAST 命中可跳 JBrowse）
#  10) 验收                    BLAST 库 / alias / MySQL / API / HTML / JBrowse 映射 共 10+ 项检查
#
# 每次改动前自动备份到 /var/www/data/masw_data/backup_<时间戳>/
#
# 不做（需人工，脚本会打印提示）：
#   - getfasta 分类：要改 app/api/routers/blast.py 的 DB_CLASSIFICATION
#     → 本地 commit + push(github+gitee) → 服务器 git pull → 重启 API
#   - cite.html 引文（可选；本次上线已手工补充）
#   - GetSequence 支持基因组面板由 Genefunc_registry 动态渲染（本脚本已写 registry + 示例字段）
#
# 路径均可被 WHEATOMICS_* 环境变量覆盖（默认=生产路径；本地 fake docroot 测试用）：
#   WHEATOMICS_REPO         仓库根              (默认 /var/www/FastAPI_backend_Port8000)
#   WHEATOMICS_JBROWSE_HTML JBrowse 页面         (默认 /var/www/html/jbrowse.html)
#   WHEATOMICS_BLAST_HTML   BLAST 页面           (默认 /var/www/html/blast/blast.html)
#   WHEATOMICS_BLASTDB      BLAST 库目录         (默认 /var/www/html/getfasta/blastdb)
#   WHEATOMICS_JBROWSE      JBrowse 程序/数据集根 (默认 /var/www/html/jbrowse-1.12.3-release)
#   WHEATOMICS_DDL_ENV      DDL 账号 env         (默认 /etc/wheatomics/db_ddl.env)
#   WHEATOMICS_API          API base URL         (默认 http://127.0.0.1:8000)
#   WHEATOMICS_BACKUP_ROOT  备份根目录           (默认 /var/www/data/masw_data)
#   WHEATOMICS_DATA_ROOT    数据根目录           (默认 /var/www/data/masw_data)
#   WHEATOMICS_ZJW_PY       服务端 python        (默认 /home/fei/mambaforge/envs/zjw/bin/python3)
#   WHEATOMICS_BLASTX       BLAST+ bin 目录      (默认 /var/www/html/blast/blast+/bin)
#
# 用法：
#   finish_genome_integration.sh <PLOIDY> <MYTAG> <DOI> [选项]
#
# 选项：
#   --title  "论文标题"        写入 Genefunc_registry.title / genome_registry.paper_title
#   --label  "前端显示名"      默认 <MYTAG>（如 "Zavitan (WEW_NT)"）
#   --section "JBrowse 分区名" 默认 "<LABEL> JBrowse"
#   --group  "Tetraploid"      Genefunc 分组；默认按倍性映射
#   --accession "GWH…"         组装号/登录号（GWH/GenBank/PI/CItr…）
#   --paper-code "WEW_NT"      文章给出的基因组代号（补充信息，写入 plan 与 registry notes）
#                              ⚠ --cultivar 与 --accession 至少要有一个（材料身份必填）
#   --species "Triticum …"     物种
#   --cultivar "Zavitan"       品种/材料名
#   --journal "Nature Genetics"
#   --year "2026"
#   --source-url "https://…"   序列来源 URL
#   --source-md5 "…"           序列文件 md5
#   --write-plan               与 --check-name 连用：把确认后的命名/分类方案写入
#                              /var/www/data/masw_data/<DS>/name_plan.json（需同时给 --confirm）
#   --confirm                  人工确认标记；--write-plan 必须带它才会落盘
#   --no-plan-check            正式运行时跳过 name_plan.json 校验（不推荐）
#   --check-name               跑流水线**之前**的命名/分类预检（不改任何东西）：
#                              分类归属、JBrowse 分区（V2 解析 id="group-…"）、
#                              BLAST 库清单（SPA 自动跳过 optgroup 断言）、PrimerServer2 排序、
#                              Genefunc 分组、subgenomes、display_order —— 名字确定前先跑这个
#   --section-existing "名"    把卡片插进已有的 JBrowse 分区；V2 页面支持 group-id
#                              （如 group-mm / #group-uu）或分区标题（如 "MM Aegilops comosa"）；
#                              旧页面支持 <h5> 分区标题（如 "Allotetraploid Wheat JBrowse"）。
#                              省略则按倍性落到 #group-<ploidy>，不存在则新建
#   --section-title "标题"     V2 新建分区的标题（默认 "<PLOIDY> genome"）
#   --section-desc "描述"      V2 新建分区的描述（默认 --species，缺省用 --label）
#   --search-extra "关键词…"   V2 卡片 data-search 追加搜索词（物种/倍性/登录号等）
#   --require-section          分区不存在时 BLOCK（默认只 WARN + 收尾时自动新建）
#   --expect-category ID       验收时断言 getfasta/BLAST 分类 id（如 tetraploid_wheat），不符则报错
#   --dry-run                  只打印计划，不改任何东西
#   --skip-html                只做 DB/fai/alias，不动 HTML
#   --skip-registry            不跑 import_jbrowse_meta / rebuild_genome_registry /
#                              build_blast_jbrowse_map（三者都依赖 registry）
#   --restart-api              结束时重启 wheatomics-api（需要 sudo 免密或 WHEATOMICS_SUDO_PASS）
#   --force                    即使 HTML 里已存在也重新插入（默认幂等跳过）
#   -h|--help
#
# 示例：
#   finish_genome_integration.sh AABB WEW_NT 10.1038/s41588-026-02808-3 \
#     --title "Near-complete assembly of wild emmer wheat unveils centromere reorganization during polyploid evolution" \
#     --label "Zavitan (WEW_NT)" --accession GWHHHUI00000000.1 \
#     --species "Triticum turgidum ssp. dicoccoides" --cultivar Zavitan \
#     --journal "Nature Genetics" --year 2026 \
#     --source-url "https://download.cncb.ac.cn/gwh/Plants/Triticum_dicoccoides_WEW_NT_GWHHHUI00000000.1/GWHHHUI00000000.1.genome.fasta.gz" \
#     --source-md5 663e9bd6d74195f4d0801a548c68f34f --dry-run
#
#   finish_genome_integration.sh MM Aegilops_comosa_IPK_AE783 10.1186/s12870-026-10046-2 \
#     --label "Ae.comosa IPK-AE783 (M)" --accession IPK-AE783 \
#     --species "Aegilops comosa" --cultivar IPK-AE783 --group "Other Triticeae" \
#     --section-title "MM Aegilops comosa" --section-desc "Aegilops comosa (M genome)" \
#     --search-extra "aegilops comosa m genome ipk-ae783" --dry-run
# ============================================================================

set -uo pipefail

# ---------------------------------------------------------------- 常量路径
# 全部支持 WHEATOMICS_* 环境变量覆盖（默认值=生产路径；本地 fake docroot 测试不碰生产）
BLASTDB="${WHEATOMICS_BLASTDB:-/var/www/html/getfasta/blastdb}"
JBROWSE="${WHEATOMICS_JBROWSE:-/var/www/html/jbrowse-1.12.3-release}"
JBROWSE_HTML="${WHEATOMICS_JBROWSE_HTML:-/var/www/html/jbrowse.html}"
BLAST_HTML="${WHEATOMICS_BLAST_HTML:-/var/www/html/blast/blast.html}"
REPO="${WHEATOMICS_REPO:-/var/www/FastAPI_backend_Port8000}"
DDL_ENV="${WHEATOMICS_DDL_ENV:-/etc/wheatomics/db_ddl.env}"
APP_ENV="${REPO}/.env"
BACKUP_ROOT="${WHEATOMICS_BACKUP_ROOT:-/var/www/data/masw_data}"
DATA_ROOT="${WHEATOMICS_DATA_ROOT:-/var/www/data/masw_data}"
ZJW_PY="${WHEATOMICS_ZJW_PY:-/home/fei/mambaforge/envs/zjw/bin/python3}"
BLASTX="${WHEATOMICS_BLASTX:-/var/www/html/blast/blast+/bin}"
API="${WHEATOMICS_API:-http://127.0.0.1:8000}"

# ---------------------------------------------------------------- 参数解析
usage() {
  # 打印文件头注释（第 2 行到第二个 "# ====" 分隔线之前），去掉行首 "# "
  awk 'NR==1 { next } /^# =+$/ { n++; if (n == 2) exit; next } { sub(/^# ?/, ""); print }' "$0"
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then usage; exit 0; fi
if [ "$#" -lt 3 ]; then usage; exit 1; fi

PLOIDY="$1"; MYTAG="$2"; DOI="$3"; shift 3

LABEL="$MYTAG"; SECTION=""; GROUP=""; TITLE=""; ACCESSION=""; SPECIES=""
CULTIVAR=""; JOURNAL=""; YEAR=""; SOURCE_URL=""; SOURCE_MD5=""; PAPER_CODE=""
DRY=0; SKIP_HTML=0; SKIP_REGISTRY=0; RESTART=0; FORCE=0
CHECK_NAME=0; SECTION_EXISTING=""; EXPECT_CAT=""
WRITE_PLAN=0; CONFIRM=0; SKIP_PLAN_CHECK=0
SECTION_TITLE=""; SECTION_DESC=""; SEARCH_EXTRA=""; REQUIRE_SECTION=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --title)      TITLE="${2:-}";      shift 2 ;;
    --label)      LABEL="${2:-}";      shift 2 ;;
    --section)    SECTION="${2:-}";    shift 2 ;;
    --group)      GROUP="${2:-}";      shift 2 ;;
    --accession)  ACCESSION="${2:-}";  shift 2 ;;
    --paper-code) PAPER_CODE="${2:-}"; shift 2 ;;
    --species)    SPECIES="${2:-}";    shift 2 ;;
    --cultivar)   CULTIVAR="${2:-}";   shift 2 ;;
    --journal)    JOURNAL="${2:-}";    shift 2 ;;
    --year)       YEAR="${2:-}";       shift 2 ;;
    --source-url) SOURCE_URL="${2:-}"; shift 2 ;;
    --source-md5) SOURCE_MD5="${2:-}"; shift 2 ;;
    --section-title) SECTION_TITLE="${2:-}"; shift 2 ;;
    --section-desc)  SECTION_DESC="${2:-}";  shift 2 ;;
    --search-extra)  SEARCH_EXTRA="${2:-}";  shift 2 ;;
    --check-name)     CHECK_NAME=1; shift ;;
    --write-plan)     WRITE_PLAN=1; shift ;;
    --confirm)        CONFIRM=1; shift ;;
    --no-plan-check)  SKIP_PLAN_CHECK=1; shift ;;
    --section-existing) SECTION_EXISTING="${2:-}"; shift 2 ;;
    --expect-category)  EXPECT_CAT="${2:-}";  shift 2 ;;
    --require-section) REQUIRE_SECTION=1; shift ;;
    --dry-run)        DRY=1; shift ;;
    --skip-html)      SKIP_HTML=1; shift ;;
    --skip-registry)  SKIP_REGISTRY=1; shift ;;
    --restart-api)    RESTART=1; shift ;;
    --force)          FORCE=1; shift ;;
    -h|--help)        usage; exit 0 ;;
    *) echo "未知参数: $1" >&2; usage; exit 1 ;;
  esac
done

DS="${PLOIDY}_${MYTAG}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="${BACKUP_ROOT}/backup_${STAMP}"
FAILED=0
CHANGED=0

log()  { echo "[$(date +%H:%M:%S)] $*"; }
warn() { echo "[$(date +%H:%M:%S)] [WARN] $*" >&2; }
fail() { echo "[$(date +%H:%M:%S)] [FAIL] $*" >&2; FAILED=$((FAILED+1)); }
die()  { echo "[$(date +%H:%M:%S)] [FATAL] $*" >&2; exit 2; }

[ "$DRY" = 1 ] && log "*** DRY-RUN：只打印计划，不修改任何文件 ***"

# ---------------------------------------------------------------- 命名/分类预检
# 跑流水线之前的唯一必做检查：确认 DS=PLOIDY_MYTAG 在各模块里的分类/排序归属。
check_name() {
  log "=== 命名/分类预检：${DS}（不接触任何线上数据）==="
  PLOIDY="$PLOIDY" MYTAG="$MYTAG" DS="$DS" GROUP="$GROUP" LABEL="$LABEL" DOI="$DOI" \
  TITLE="$TITLE" ACCESSION="$ACCESSION" SPECIES="$SPECIES" CULTIVAR="$CULTIVAR" \
  SOURCE_URL="$SOURCE_URL" SOURCE_MD5="$SOURCE_MD5" \
  JOURNAL="$JOURNAL" YEAR="$YEAR" SECTION_NAME="$SECTION" \
  REPO="$REPO" BLASTDB="$BLASTDB" JBROWSE_HTML="$JBROWSE_HTML" BLAST_HTML="$BLAST_HTML" \
  SECTION_EXISTING="$SECTION_EXISTING" EXPECT_CAT="$EXPECT_CAT" DDL_ENV="$DDL_ENV" PAPER_CODE="$PAPER_CODE" \
  SECTION_TITLE="$SECTION_TITLE" SECTION_DESC="$SECTION_DESC" SEARCH_EXTRA="$SEARCH_EXTRA" \
  REQUIRE_SECTION="$REQUIRE_SECTION" \
  DATA_ROOT="$DATA_ROOT" WRITE_PLAN="$WRITE_PLAN" CONFIRM="$CONFIRM" \
  python3 - <<'PY'
import ast, os, re, subprocess, pathlib

ploidy = os.environ["PLOIDY"]; mytag = os.environ["MYTAG"]; ds = os.environ["DS"]
group = os.environ["GROUP"]; repo = os.environ["REPO"]
blastdb = os.environ["BLASTDB"]; jbh = pathlib.Path(os.environ["JBROWSE_HTML"])
blh = pathlib.Path(os.environ["BLAST_HTML"])
sec_existing = os.environ.get("SECTION_EXISTING", "")
expect_cat = os.environ.get("EXPECT_CAT", "")
require_section = os.environ.get("REQUIRE_SECTION") == "1"
section_title = os.environ.get("SECTION_TITLE", "")
section_desc = os.environ.get("SECTION_DESC", "")
search_extra = os.environ.get("SEARCH_EXTRA", "")
ok = True
is_v2 = False
warn = []

def hdr(s): print(f"\n--- {s} ---")
ord_guess = 500

print(f"数据集/库/表名 : {ds}")

# 0) 材料身份（必填）
hdr("0) 材料身份（材料名 / 登录号 / 文章基因组代号）")
ident = os.environ.get("CULTIVAR", ""); acc = os.environ.get("ACCESSION", "")
paper = os.environ.get("PAPER_CODE", "")
print(f"  材料名（品种/品系）: {ident or '(未提供)'}")
print(f"  登录号/组装号      : {acc or '(未提供)'}")
print(f"  文章基因组代号     : {paper or '(未提供)'}")
if not ident and not acc:
    ok = False
    warn.append("缺少材料身份：新基因组必须提供 --cultivar（材料/品种/品系名）或 --accession（GWH/GenBank/PI/CItr 等登录号）；\n"
                "         文章里的基因组代号（--paper-code，如 WEW_NT）只能作补充，不能单独决定数据集名")
print(f"  BLAST      : {ds}.genome / {ds}.genome_ChrXX / {ds}.add_Description.cds|pep")
print(f"  JBrowse    : {ds}")
print(f"  MySQL      : Genefunc_{ds}_table ; Polyploidy={ploidy} ; Group={group}")

# 1) subgenomes（读 rebuild 脚本里的 SUB 映射，保证与 registry 一致）
hdr("1) 亚基因组组成（genome_registry.subgenomes）")
sub = {}
try:
    tx = (pathlib.Path(repo) / "scripts/rebuild_genome_registry.py").read_text()
    m = re.search(r"SUB\s*=\s*\{(.*?)\}", tx, re.S)
    if m:
        for k, v in re.findall(r'"([A-Z]+)"\s*:\s*"([^"]+)"', m.group(1)):
            sub[k] = v
except Exception as e:
    warn.append(f"读 SUB 映射失败：{e}")
print(f"  SUB[{ploidy}] = {sub.get(ploidy, '(未登记)')}")
if ploidy not in sub:
    ok = False; warn.append(f"ploidy '{ploidy}' 不在 SUB 映射里 → genome_registry.subgenomes 不会自动填，需要补 rebuild 脚本")

# 2) getfasta / Web BLAST 库分类（DB 名子串匹配）
hdr("2) getfasta / BLAST 库分类（DB_CLASSIFICATION 子串匹配）")
cats = []
try:
    tree = ast.parse((pathlib.Path(repo) / "app/api/routers/blast.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t2, "id", "") == "DB_CLASSIFICATION" for t2 in node.targets):
            cats = ast.literal_eval(node.value)
except Exception as e:
    warn.append(f"解析 DB_CLASSIFICATION 失败：{e}")

def classify(name):
    n = name.lower()
    for c in cats:
        if any(k in n for k in c["keywords"]):
            return c["id"]
    return "other"

for suffix in (".genome", ".add_Description.cds", ".add_Description.pep"):
    got = classify(ds + suffix)
    print(f"  {ds+suffix:<42} -> {got}")
cat_verdict = classify(ds + ".genome")
if cat_verdict == "other":
    ok = False
    warn.append("库名匹配不到任何分类，会掉进 'Other / Unclassified'（getfasta 分类里看不到）\n"
                "         解决二选一：① 给 tetraploid_wheat 的 keywords 加 \"wew_nt\"（改 blast.py → commit/push/重启）\n"
                "                    ② MYTAG 改用含关键词的名字，如 Wild_emmer_WEW_NT（DS=AABB_Wild_emmer_WEW_NT，零代码改动）")
if expect_cat and cat_verdict != expect_cat:
    ok = False; warn.append(f"分类结果 {cat_verdict} != 期望 {expect_cat}")

# 3) Web BLAST 库清单分组（旧页面 optgroup / 新页面 wheatBLAST SPA 动态取库）
hdr("3) Web BLAST 库清单分组（blast.html）")
gmap = {"Tetraploid": "Tetraploid wheat genome", "Hexaploid": "Hexaploid wheat genome",
        "Allohexaploid": "Allohexaploid chr genome", "Diploid": "Diploid wheat genome",
        "Triticale": "Hexaploid Triticale genome", "Other": "Other Triticeae genome",
        "Other Triticeae": "Other Triticeae genome"}
want = gmap.get(group, "")
try:
    btxt = blh.read_text(encoding="utf-8", errors="replace")
except Exception as e:
    btxt = ""
    warn.append(f"读 blast.html 失败：{e}")
is_spa = bool(re.search(r"wheatBLAST SPA|blast-db-cats|api/blast/databases", btxt)) \
         and "<optgroup" not in btxt
if is_spa:
    print("  [SPA] 新版 wheatBLAST 动态取库，跳过 optgroup 断言")
    print(f"  目标分类 : {want or '(未映射)'} ← 运行期由 /api/blast/databases 决定（verify() 做 API 断言）")
else:
    groups = [m.group(1).strip("- ").strip()
              for m in re.finditer(r'<optgroup label="([^"]*)"', btxt)]
    print(f"  现有 optgroup : {groups}")
    print(f"  Group={group}  → 目标 optgroup: {want or '(未映射，将插到第一个 optgroup)'}")
    if want and not any(want in g for g in groups):
        ok = False; warn.append(f"blast.html 里没有含 '{want}' 的 optgroup")

# 4) JBrowse 卡片分区（新增：V2 asm-group；旧页面仍解析 h5 分区）
hdr("4) JBrowse 卡片分区（jbrowse.html）")
try:
    h = jbh.read_text(encoding="utf-8", errors="replace")
    v2_sections = []       # [(group-id, plain title)]
    for m in re.finditer(r'<section\b[^>]*>', h):
        tag = m.group(0)
        if not re.search(r'class="[^"]*\basm-group\b', tag):
            continue
        mid = re.search(r'\bid="(group-[a-z0-9-]+)"', tag)
        if not mid:
            continue
        end = h.find('</section>', m.end())
        body = h[m.end():end] if end > 0 else ""
        tm = re.search(r'<h2[^>]*class="[^"]*asm-group-title[^"]*"[^>]*>(.*?)</h2>', body, re.S)
        plain = re.sub(r'<[^>]+>', ' ', tm.group(1)) if tm else ""
        plain = re.sub(r'\s+', ' ', plain).strip()
        v2_sections.append((mid.group(1), plain))
    is_v2 = bool(v2_sections) or bool(re.search(r'class="[^"]*\basm-grid\b', h))
    if is_v2:
        ids = [g for g, _ in v2_sections]
        want_id = "group-" + ploidy.lower()
        print(f"  页面版本 : V2.0（{len(ids)} 个 asm-group）")
        print(f"  现有分组 : {['#' + i for i in ids]}")
        print(f"  倍性 {ploidy} → 目标分组 #{want_id} : {'存在 ✓' if want_id in ids else '不存在（收尾时自动新建）'}")
        if sec_existing:
            se = sec_existing.strip()
            sid = se[1:] if se.startswith('#') else se
            if sid in ids:
                print(f"  --section-existing = '{sec_existing}' → 匹配分区 id #{sid} ✓")
            else:
                hit = [g for g, t in v2_sections if se.lower() in t.lower()]
                if hit:
                    print(f"  --section-existing = '{sec_existing}' → 匹配分区标题 #{hit[0]} ✓")
                else:
                    msg = (f"jbrowse.html 里没有分区 '{sec_existing}'（group-id 或标题）"
                           + ("；--require-section 已指定 → BLOCK" if require_section
                              else f"；收尾时将按 #{want_id} 新建"))
                    if require_section: ok = False
                    warn.append(msg)
        elif want_id not in ids:
            if require_section:
                ok = False; warn.append(f"缺少目标分区 #{want_id}（--require-section 已指定）")
            else:
                warn.append(f"没有 #{want_id} 分区：收尾时会新建 "
                            f"<section class=\"asm-group\" id=\"{want_id}\">（hero/status/组数同步 +1）")
        else:
            print(f"  插入点   : #{want_id} 的 asm-grid 末尾（收尾时追加 asm-card）")
    else:
        secs = re.findall(r"<h5>&nbsp;&nbsp;&nbsp;&nbsp;([^<]*?)(?:&nbsp;)*</h5>", h)
        secs = [s.replace("&nbsp;", "").strip() for s in secs]
        print(f"  页面版本 : legacy（{len(secs)} 个 h5 分区）")
        print(f"  现有分区 : {secs}")
        if sec_existing:
            found = any(sec_existing in s for s in secs)
            print(f"  --section-existing = '{sec_existing}' → {'存在 ✓' if found else '不存在 ✗'}")
            if not found:
                if require_section:
                    ok = False; warn.append(f"jbrowse.html 里没有分区 '{sec_existing}'")
                else:
                    warn.append(f"jbrowse.html 里没有分区 '{sec_existing}'（收尾将新建分区）")
        else:
            slog = {"AABB": "Allotetraploid Wheat JBrowse", "AABBDD": "Allohexaploid Wheat JBrowse",
                    "DD": "Diploid Wheat JBrowse", "AABBRR": "Hexaploid Triticale JBrowse"}
            rec = slog.get(ploidy)
            print(f"  建议分区 : {rec or '(未映射，将新建分区)'}  ← 用 --section-existing 指定可插进既有分区")
            if not rec:
                warn.append("该倍性没有对应分区，脚本会新建一个 '<label> JBrowse' 分区")
except Exception as e:
    warn.append(f"读 jbrowse.html 失败：{e}")

# 5) PrimerServer2 排序（_genome_sort_key：CS2.1 最前、其余按名称字母序）
hdr("5) PrimerServer2 排序（字母序，Chinese Spring 优先）")
try:
    names = [n for n in os.listdir(blastdb) if n.endswith(".genome")]
    def key(n):
        if n == "AABBDD_Chinese_Spring2.1.genome": return (0, n)
        if "Chinese_Spring" in n or "CS-CAU" in n or "CS-IAAS" in n: return (1, n)
        return (2, n)
    names.sort(key=key)
    newname = ds + ".genome"
    idx = next((i for i, n in enumerate(names) if key(n) > key(newname)), len(names))
    prev_n = names[idx-1] if idx > 0 else "(最前)"
    print(f"  预估位置 : 第 {idx+1} / {len(names)+1}")
    print(f"  相邻     : 前 = {prev_n}  ；后 = {names[idx] if idx < len(names) else '(最后)'}")
except Exception as e:
    warn.append(f"列 blastdb 失败：{e}")

# 6) Genefunc_registry display_order（同 Polyploidy 里追加到末尾）
hdr("6) Genefunc_registry display_order")
cred = {}
try:
    for line in pathlib.Path(os.environ.get("DDL_ENV", "")).read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1); cred[k.strip()] = v.strip()
    sql = ("SELECT COALESCE(MAX(display_order),0)+1 FROM Genefuncdb.Genefunc_registry "
           f"WHERE Polyploidy='{ploidy}'")
    r = subprocess.run(["mysql", "-h", cred.get("DB_HOST", "localhost"),
                        "-u", cred.get("DB_USER", "") or "wheatomics_ddl",
                        "-p" + cred.get("DB_PASS", ""), "-N", "-B", "-e", sql],
                       capture_output=True, text=True, timeout=20)
    val = (r.stdout or "").strip().splitlines()
    if val and val[0]:
        ord_guess = int(val[0])
    print(f"  建议 display_order = {ord_guess}（同 Polyploidy 末尾）")
except Exception as e:
    warn.append(f"查 display_order 失败：{e}（脚本会自动用 500）")

# 结论
print("\n=== 预检结论 ===")
for w in warn:
    print("  [WARN] " + w)
print("  [OK] 命名可直接开跑" if ok else "  [BLOCK] 先解决上面的 WARN 再跑流水线")

# 落盘：确认后的命名/分类方案（后续 finish 正式运行会校验它）
if os.environ.get("WRITE_PLAN") == "1":
    if os.environ.get("CONFIRM") != "1":
        print("  [BLOCK] --write-plan 需要同时给 --confirm（人工确认后才落盘）")
        raise SystemExit(3)
    if not ok:
        print("  [BLOCK] 预检未通过，不写 plan")
        raise SystemExit(3)
    import json, datetime
    cat_label = next((c["label"] for c in cats if c["id"] == cat_verdict), "")
    scol = {"AABB": "Allotetraploid Wheat JBrowse", "AABBDD": "Allohexaploid Wheat JBrowse",
            "DD": "Diploid Wheat JBrowse", "AABBRR": "Hexaploid Triticale JBrowse"}
    if is_v2:
        # V2 页面以 group-id 定位插入点，plan 里落 #group-<ploidy>
        sec = sec_existing or ("group-" + ploidy.lower())
    else:
        sec = sec_existing or scol.get(ploidy) or (os.environ.get("SECTION_NAME") or "")
    plan = {
        "ds": ds, "ploidy": ploidy, "myTag": mytag, "subgenomes": sub.get(ploidy, ""),
        "group": group, "label": os.environ.get("LABEL") or mytag,
        "doi": os.environ.get("DOI", ""), "title": os.environ.get("TITLE", ""),
        "accession": os.environ.get("ACCESSION", ""),
        "species": os.environ.get("SPECIES", ""), "cultivar": os.environ.get("CULTIVAR", ""),
        "paperCode": os.environ.get("PAPER_CODE", ""),
        "sourceUrl": os.environ.get("SOURCE_URL", ""),
        "sourceMd5": os.environ.get("SOURCE_MD5", ""),
        "journal": os.environ.get("JOURNAL", ""), "year": os.environ.get("YEAR", ""),
        "classification": cat_verdict, "expectedCategoryLabel": cat_label,
        "blastOptgroup": want, "jbrowseSection": sec,
        "jbrowsePageVersion": "v2" if is_v2 else "legacy",
        "sectionTitle": section_title, "sectionDesc": section_desc,
        "searchExtra": search_extra,
        "displayOrder": globals().get("ord_guess", 500),
        "confirmed": True,
        "createdAt": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    outdir = pathlib.Path(os.environ["DATA_ROOT"]) / ds
    try:
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "name_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [OK] 已写入 {outdir/'name_plan.json'}")
    except Exception as e:
        print(f"  [WARN] 写 plan 失败：{e}")
raise SystemExit(0 if ok else 3)
PY
}

# ---------------------------------------------------------------- 前置检查
# 默认分组映射（2026-11：二倍体 Aegilops MM/CC/UU/NN → Other Triticeae，与既有
# Aegilops 历史行 Group 取值一致；只有 DD/AA/BB 归 Diploid wheat）
if [ -z "$GROUP" ]; then
  case "$PLOIDY" in
    AABB)   GROUP="Tetraploid" ;;
    AABBDD) GROUP="Hexaploid" ;;
    AABBRR) GROUP="Triticale" ;;
    DD|AA|BB) GROUP="Diploid" ;;
    MM|CC|UU|NN|SS|TT|VV|EE|RR|II|PP|GG) GROUP="Other Triticeae" ;;
    *)      GROUP="Other" ;;
  esac
fi
[ -z "$SECTION" ] && SECTION="${LABEL} JBrowse"

if [ "${CHECK_NAME:-0}" = 1 ]; then check_name; exit $?; fi

# ---- 正式运行前：必须已有确认过的命名/分类方案（--check-name --write-plan 产生）----
PLAN_FILE="${DATA_ROOT}/${DS}/name_plan.json"
PLAN_ORD=""
if [ "${SKIP_PLAN_CHECK:-0}" = 0 ]; then
  if [ ! -f "$PLAN_FILE" ]; then
    cat >&2 <<EOF

[BLOCK] 缺少命名/分类方案 ${PLAN_FILE}

  **跑流水线之前必须先把命名/分类确认下来**（数据集名会绑定 BLAST 库名、
  JBrowse 数据集、MySQL 表名、聚合库 alias，跑完再改代价极高）。

  正确的顺序：
    $0 ${PLOIDY} ${MYTAG} ${DOI} --check-name              # 1. 看分类归属
    $0 ${PLOIDY} ${MYTAG} ${DOI} --check-name --write-plan --confirm   # 2. 人工确认后落盘
    add_wheat_genome.sh ${MYTAG} ... ${PLOIDY}             # 3. 跑流水线
    $0 ${PLOIDY} ${MYTAG} ${DOI} ...                       # 4. 收尾（即本脚本正常模式）

  确需跳过：加 --no-plan-check（不推荐）

EOF
    exit 4
  fi
  while IFS=$'\t' read -r k v; do
    case "$k" in
      ds)        PLAN_DS="$v" ;;
      label)     PLAN_LABEL="$v" ;;
      cat)       PLAN_CAT="$v" ;;
      section)   PLAN_SECTION="$v" ;;
      ord)       PLAN_ORD="$v" ;;
      title)     PLAN_TITLE="$v" ;;
      journal)   PLAN_JOURNAL="$v" ;;
      year)      PLAN_YEAR="$v" ;;
      species)   PLAN_SPECIES="$v" ;;
      cultivar)  PLAN_CULTIVAR="$v" ;;
      accession) PLAN_ACCESSION="$v" ;;
      papercode) PLAN_PAPERCODE="$v" ;;
      sourceurl) PLAN_SOURCEURL="$v" ;;
      sourcemd5) PLAN_SOURCEMD5="$v" ;;
      subgenomes) PLAN_SUBGENOMES="$v" ;;
      sectiontitle) PLAN_SECTIONTITLE="$v" ;;
      sectiondesc)  PLAN_SECTIONDESC="$v" ;;
      searchextra)  PLAN_SEARCHEXTRA="$v" ;;
    esac
  done < <(python3 - "$PLAN_FILE" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
for k,v in (("ds",d.get("ds","")),("label",d.get("label","")),
            ("cat",d.get("expectedCategoryLabel","")),("section",d.get("jbrowseSection","")),
            ("ord",str(d.get("displayOrder") or "")),
            ("title",d.get("title","")),("journal",d.get("journal","")),
            ("year",str(d.get("year") or "")),("species",d.get("species","")),
            ("cultivar",d.get("cultivar","")),("accession",d.get("accession","")),
            ("papercode",d.get("paperCode","")),("sourceurl",d.get("sourceUrl","")),
            ("sourcemd5",d.get("sourceMd5","")),("subgenomes",d.get("subgenomes","")),
            ("sectiontitle",d.get("sectionTitle","")),("sectiondesc",d.get("sectionDesc","")),
            ("searchextra",d.get("searchExtra",""))):
    print(f"{k}\t{v}")
PY
)
  [ "${PLAN_DS:-}" = "$DS" ] || die "name_plan.json 里的 ds=${PLAN_DS:-?} 与本次 ${DS} 不一致（改名了？需重新 --check-name --write-plan）"
  [ -n "${PLAN_CAT:-}" ]     && [ -z "$EXPECT_CAT" ]       && EXPECT_CAT="$PLAN_CAT"
  [ -n "${PLAN_SECTION:-}" ] && [ -z "$SECTION_EXISTING" ] && SECTION_EXISTING="$PLAN_SECTION"
  [ -n "${PLAN_LABEL:-}" ]   && [ "$LABEL" = "$MYTAG" ]    && LABEL="$PLAN_LABEL"
  [ -z "${SECTION_TITLE:-}" ] && [ -n "${PLAN_SECTIONTITLE:-}" ] && SECTION_TITLE="$PLAN_SECTIONTITLE"
  [ -z "${SECTION_DESC:-}" ]  && [ -n "${PLAN_SECTIONDESC:-}" ]  && SECTION_DESC="$PLAN_SECTIONDESC"
  [ -z "${SEARCH_EXTRA:-}" ]  && [ -n "${PLAN_SEARCHEXTRA:-}" ]  && SEARCH_EXTRA="$PLAN_SEARCHEXTRA"
  [ -z "${TITLE:-}" ]      && [ -n "${PLAN_TITLE:-}" ]      && TITLE="$PLAN_TITLE"
  [ -z "${JOURNAL:-}" ]    && [ -n "${PLAN_JOURNAL:-}" ]    && JOURNAL="$PLAN_JOURNAL"
  [ -z "${YEAR:-}" ]       && [ -n "${PLAN_YEAR:-}" ]       && YEAR="$PLAN_YEAR"
  [ -z "${SPECIES:-}" ]    && [ -n "${PLAN_SPECIES:-}" ]    && SPECIES="$PLAN_SPECIES"
  [ -z "${CULTIVAR:-}" ]   && [ -n "${PLAN_CULTIVAR:-}" ]   && CULTIVAR="$PLAN_CULTIVAR"
  [ -z "${ACCESSION:-}" ]  && [ -n "${PLAN_ACCESSION:-}" ]  && ACCESSION="$PLAN_ACCESSION"
  [ -z "${PAPER_CODE:-}" ] && [ -n "${PLAN_PAPERCODE:-}" ]  && PAPER_CODE="$PLAN_PAPERCODE"
  [ -z "${SOURCE_URL:-}" ] && [ -n "${PLAN_SOURCEURL:-}" ]  && SOURCE_URL="$PLAN_SOURCEURL"
  [ -z "${SOURCE_MD5:-}" ] && [ -n "${PLAN_SOURCEMD5:-}" ]  && SOURCE_MD5="$PLAN_SOURCEMD5"
  SUBGENOMES="${PLAN_SUBGENOMES:-}"
  log "命名方案：${PLAN_FILE}（分类=${EXPECT_CAT:-?}，分区=${SECTION_EXISTING:-新建}，order=${PLAN_ORD:-自动}）"
fi

log "=== 前置检查：${DS} ==="
[ -s "${BLASTDB}/${DS}.genome" ]                || die "缺少 ${BLASTDB}/${DS}.genome（先跑 add_wheat_genome.sh）"
[ -s "${BLASTDB}/${DS}.add_Description.cds" ]   || die "缺少 ${BLASTDB}/${DS}.add_Description.cds"
[ -s "${BLASTDB}/${DS}.add_Description.pep" ]   || die "缺少 ${BLASTDB}/${DS}.add_Description.pep"
[ -d "${JBROWSE}/${DS}" ]                       || die "缺少 JBrowse 数据集目录 ${JBROWSE}/${DS}"
[ -s "${JBROWSE}/${DS}/seq/refSeqs.json" ]      || die "缺少 ${JBROWSE}/${DS}/seq/refSeqs.json"
for c in python3 mysql samtools curl; do command -v "$c" >/dev/null || die "缺少命令: $c"; done
[ -r "${DDL_ENV}" ]  || die "读不到 ${DDL_ENV}（需要 fei 属 www-data 组）"
[ -r "${APP_ENV}" ]  || die "读不到 ${APP_ENV}"
[ -w "${JBROWSE_HTML}" ] && [ -w "${BLAST_HTML}" ] || die "对 jbrowse.html / blast.html 没有写权限"
[ -x "${ZJW_PY}" ]   || warn "找不到 ${ZJW_PY}，jbrowse_meta/registry 步骤会跳过"

# ---------------------------------------------------------------- 事实收集
STD_FIRST="$(grep -m1 '^>' "${BLASTDB}/${DS}.genome" | awk '{print substr($1,2)}')"
[ -n "$STD_FIRST" ] || die "无法从 ${DS}.genome 读取第一条序列名"
EXAMPLE_SPECIES_CHR="${STD_FIRST}:200-500"

FIRST_CDS="$(grep -m1 '^>' "${BLASTDB}/${DS}.add_Description.cds" | awk '{print substr($1,2)}')"
FIRST_PEP="$(grep -m1 '^>' "${BLASTDB}/${DS}.add_Description.pep" | awk '{print substr($1,2)}')"
[ -n "$FIRST_CDS" ] || die "无法从 .add_Description.cds 读取第一条序列名"
[ -n "$FIRST_PEP" ] || die "无法从 .add_Description.pep 读取第一条序列名"

# 拆分库里的染色体名（去掉 BLAST 索引后缀）
# 注：用 while-read 收集而非 mapfile —— 兼容 bash 3.2（macOS 默认），语义相同。
CHROMS=()
while IFS= read -r _chrom; do
  [ -n "$_chrom" ] && CHROMS+=("$_chrom")
done < <(
  ls "${BLASTDB}" 2>/dev/null | sed -n "s/^${DS}\.genome_\(Chr[0-9][0-9A-Za-z]*\)\..*$/\1/p" | sort -u
)
[ "${#CHROMS[@]}" -gt 0 ] || die "找不到 ${DS}.genome_Chr* 拆分库（流水线 Step 2/4 没跑？）"

# JBrowse 参考序列名（卡片/registry 用）
JB_FIRST="$(python3 - "${JBROWSE}/${DS}/seq/refSeqs.json" <<'PY'
import json,sys
try:
    arr=json.load(open(sys.argv[1]))
except Exception:
    print(""); raise SystemExit
names=[a.get("name","") for a in arr]
pref=[n for n in names if n.upper().startswith("CHR1A")] or [n for n in names if n.upper().startswith("CHR")] or names
print(pref[0] if pref else "")
PY
)"
[ -n "$JB_FIRST" ] || warn "无法从 refSeqs.json 取参考序列名"

log "事实收集："
log "  标准化首序列     : ${STD_FIRST}"
log "  JBrowse 首参考   : ${JB_FIRST:-?}"
log "  染色体拆分库     : ${#CHROMS[@]} 条（${CHROMS[*]:0:4}${CHROMS[*]:4:0}…）"
log "  首 mRNA / 蛋白   : ${FIRST_CDS} / ${FIRST_PEP}"
log "  分组 / 显示名    : ${GROUP} / ${LABEL}"

# ---------------------------------------------------------------- 备份
backup_files() {
  [ "$DRY" = 1 ] && { log "(dry-run) 将备份到 ${BACKUP}"; return 0; }
  mkdir -p "$BACKUP" || die "无法创建备份目录 ${BACKUP}"
  local f
  for f in "$JBROWSE_HTML" "$BLAST_HTML" \
           "${BLASTDB}/all_genomes.nal" "${BLASTDB}/all_gene.nal" \
           "${BLASTDB}/all_protein.pal" "${BLASTDB}/all_genomes_type.txt"; do
    [ -f "$f" ] && cp -a "$f" "$BACKUP/$(basename "$f").bak" && log "备份 $(basename "$f")"
  done
  # Linux 上 cp -a 会把 all_genomes.nal 的 777 保留下来；这里再确保一次
  chmod -R u+rw "$BACKUP" 2>/dev/null || true
}

# ---------------------------------------------------------------- 1) JBrowse 卡片
step_jbrowse_card() {
  log "--- 1) JBrowse 卡片 ---"
  if [ "$SKIP_HTML" = 1 ]; then log "跳过（--skip-html）"; return 0; fi
  DS="$DS" LABEL="$LABEL" SECTION="$SECTION" DOI="$DOI" FORCE="$FORCE" DRY="$DRY" \
  SECTION_EXISTING="$SECTION_EXISTING" PLOIDY="$PLOIDY" SPECIES="$SPECIES" GROUP="$GROUP" \
  SEARCH_EXTRA="${SEARCH_EXTRA:-}" SECTION_TITLE="${SECTION_TITLE:-}" SECTION_DESC="${SECTION_DESC:-}" \
  python3 - "$JBROWSE_HTML" <<'PY'
import os,re,sys,pathlib

p = pathlib.Path(sys.argv[1]); t = p.read_text(encoding="utf-8")
ds = os.environ["DS"]; label = os.environ["LABEL"]; section = os.environ["SECTION"]
doi = os.environ.get("DOI",""); force = os.environ.get("FORCE")=="1"; dry = os.environ.get("DRY")=="1"
ploidy = os.environ.get("PLOIDY",""); species = os.environ.get("SPECIES","")
group = os.environ.get("GROUP",""); search_extra = os.environ.get("SEARCH_EXTRA","")
sec_existing = os.environ.get("SECTION_EXISTING","").strip()
section_title = os.environ.get("SECTION_TITLE","").strip() or ((ploidy + " genome") if ploidy else section)
section_desc = os.environ.get("SECTION_DESC","").strip() or species or label

if f"?data={ds}" in t and not force:
    print("  [SKIP] 卡片已存在（?data=%s）" % ds); raise SystemExit(0)

def esc(s):
    return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def build_search():
    words = [label, ds, ("doi:" + doi) if doi else "", ("https://doi.org/" + doi) if doi else "",
             species, search_extra, ploidy, group, "genome", "other triticeae", "species", "jbrowse"]
    toks = []
    for w in words:
        for tok in (w or "").lower().split():
            if tok not in toks:
                toks.append(tok)
    return " ".join(toks)

def build_card(indent):
    """V2.0 卡片：article.asm-card + h3.asm-name + p.asm-doi（与既有卡片同构）"""
    pad = " " * indent
    lines = [pad + '<article class="asm-card" data-search="%s">' % esc(build_search())]
    lines.append(pad + '  <h3 class="asm-name"><a href="/jbrowse-1.12.3-release/?data=%s">%s</a></h3>'
                 % (ds, esc(label)))
    if doi:
        lines.append(pad + '  <p class="asm-doi"><a href="https://doi.org/%s" target="_blank" rel="noopener">doi:%s</a></p>'
                     % (esc(doi), esc(doi)))
    else:
        lines.append(pad + '  <p class="asm-doi"><span class="asm-doi-none">DOI not listed</span></p>')
    lines.append(pad + '</article>')
    return "\n".join(lines) + "\n"

def line_indent(text, pos):
    ls = text.rfind("\n", 0, pos) + 1
    m = re.match(r"[ \t]*", text[ls:])
    return m.group(0) if m else ""

def find_v2_sections(text):
    out = []
    for m in re.finditer(r'<section\b[^>]*>', text):
        tag = m.group(0)
        if not re.search(r'class="[^"]*\basm-group\b', tag):
            continue
        mid = re.search(r'\bid="(group-[a-z0-9-]+)"', tag)
        if not mid:
            continue
        end = text.find('</section>', m.end())
        if end < 0:
            continue
        body = text[m.end():end]
        tm = re.search(r'<h2[^>]*class="[^"]*asm-group-title[^"]*"[^>]*>(.*?)</h2>', body, re.S)
        plain = re.sub(r'<[^>]+>', ' ', tm.group(1)) if tm else ""
        plain = re.sub(r'\s+', ' ', plain).strip()
        out.append({"gid": mid.group(1), "start": m.start(), "end": end,
                    "open_end": m.end(), "body": body, "title": plain})
    return out

def grid_close(text, sec):
    gm = re.search(r'<div\b[^>]*class="[^"]*\basm-grid\b[^"]*"[^>]*>', sec["body"])
    if not gm:
        return None
    pos = sec["open_end"] + gm.end()
    depth = 1
    tok = re.compile(r'<div\b[^>]*>|</div>')
    for m in tok.finditer(text, pos):
        depth += -1 if m.group(0) == '</div>' else 1
        if depth == 0:
            return m.start()
    return None

def find_asm_groups_close(text):
    m = re.search(r'<div\b[^>]*\bid="asm-groups"[^>]*>', text)
    if not m:
        return None
    depth = 1
    tok = re.compile(r'<div\b[^>]*>|</div>')
    for mm in tok.finditer(text, m.end()):
        depth += -1 if mm.group(0) == '</div>' else 1
        if depth == 0:
            return mm.start()
    return None

# ================= 分支 A：JBrowse V2.0（.asm-group / .asm-card / .asm-grid）=================
is_v2 = bool(re.search(r'class="[^"]*\basm-grid\b', t)) or bool(find_v2_sections(t))
if is_v2:
    sections = find_v2_sections(t)
    ids = [s["gid"] for s in sections]
    target = None
    if sec_existing:
        sid = sec_existing[1:] if sec_existing.startswith("#") else sec_existing
        for s in sections:
            if s["gid"] == sid:
                target = s; break
        if target is None:
            for s in sections:
                if sec_existing.lower() in s["title"].lower():
                    target = s; break
        if target is None:
            if sid == "group-" + ploidy.lower():
                print("  [INFO] 目标分区 #%s 尚不存在 → 收尾时新建" % sid)
            else:
                print("  [WARN] 找不到分区 '%s'（group-id/标题），改为按 #group-%s 处理（存在则插入，不存在则新建）"
                      % (sec_existing, ploidy.lower()))
    want_id = "group-" + ploidy.lower()
    if target is None:
        for s in sections:
            if s["gid"] == want_id:
                target = s; break

    ops = []          # (start, end, replacement)，end==start 表示插入；统一从后往前 apply
    new_section = False
    if target is not None:
        at = grid_close(t, target)
        if at is None:
            print("  [ERR] 分区 #%s 里找不到 asm-grid" % target["gid"]); raise SystemExit(2)
        card_indent = len(line_indent(t, at)) + 2
        at_line = t.rfind("\n", 0, at) + 1          # 插到闭合 </div> 所在行的行首，保留原缩进
        ops.append((at_line, at_line, build_card(card_indent)))
        cm = re.search(r'(<span class="asm-group-count">)(\s*)(\d+)(\s+assembl(?:y|ies))(\s*</span>)',
                       target["body"])
        if cm:
            old_n = int(cm.group(3)); new_n = old_n + 1
            word = "assembly" if new_n == 1 else "assemblies"
            ops.append((target["open_end"] + cm.start(3),
                        target["open_end"] + cm.end(4), "%d %s" % (new_n, word)))
            count_msg = "#%s 计数 %d → %d %s" % (target["gid"], old_n, new_n, word)
        else:
            count_msg = "#%s 未找到 asm-group-count（计数未改）" % target["gid"]
        target_msg = "插入 #%s 的 asm-grid 末尾" % target["gid"]
    else:
        close = find_asm_groups_close(t)
        if close is None:
            print('  [ERR] 找不到 id="asm-groups" 容器'); raise SystemExit(2)
        close_line = t.rfind("\n", 0, close) + 1    # 插到容器闭合 </div> 所在行行首
        s_ind = line_indent(t, close)
        grid_ind = s_ind + "  "
        card_ind = len(grid_ind) + 2
        sec_id = want_id
        head = "\n".join([
            "",
            '%s<section class="asm-group" id="%s" aria-labelledby="%s-title">' % (s_ind, sec_id, sec_id),
            '%s  <div class="asm-group-head">' % s_ind,
            '%s    <h2 class="asm-group-title" id="%s-title"><span class="asm-formula">%s</span> '
            '<span class="asm-desc"><i>%s</i></span></h2>' % (s_ind, sec_id, esc(section_title), esc(section_desc)),
            '%s    <span class="asm-group-count">1 assembly</span>' % s_ind,
            '%s  </div>' % s_ind,
            '%s  <div class="asm-grid">' % s_ind,
            build_card(card_ind).rstrip("\n"),
            '%s  </div>' % s_ind,
            '%s</section>' % s_ind,
            "",
        ]) + "\n"
        ops.append((close_line, close_line, head))
        new_section = True
        count_msg = "新建 #%s（1 assembly）" % sec_id
        target_msg = "新建 section #%s" % sec_id

    hero_re = re.compile(r'(<span class="news-stat"><strong>)(\d+)(</strong> assemblies</span>)')
    status_re = re.compile(r'(id="asm-status"[^>]*>\s*Showing <strong>)(\d+)(</strong>\s*named assemblies in <strong>)(\d+)(</strong>\s*genome groups)')
    hm = hero_re.search(t); sm = status_re.search(t)
    if hm:
        ops.append((hm.start(2), hm.end(2), str(int(hm.group(2)) + 1)))
        hero_msg = "hero %s → %d" % (hm.group(2), int(hm.group(2)) + 1)
    else:
        hero_msg = "hero 数字未找到（未改）"
    if sm:
        n_asm = int(sm.group(2)) + 1
        n_grp = int(sm.group(4)) + (1 if new_section else 0)
        ops.append((sm.start(2), sm.end(2), str(n_asm)))
        ops.append((sm.start(4), sm.end(4), str(n_grp)))
        status_msg = "asm-status %s/%s → %d/%d" % (sm.group(2), sm.group(4), n_asm, n_grp)
    else:
        status_msg = "asm-status 文案未找到（未改）"

    if dry:
        print("  [DRY] 将%s：%s" % (target_msg, label))
        print("  [DRY] 将同步计数：%s；%s；%s" % (hero_msg, status_msg, count_msg))
        raise SystemExit(0)
    for s, e, rep in sorted(ops, key=lambda x: -x[0]):
        t = t[:s] + rep + t[e:]
    tmp = p.with_suffix(".html.tmp")
    tmp.write_text(t, encoding="utf-8"); tmp.replace(p)
    print("  [OK] 已%s：%s" % (target_msg, label))
    print("  [OK] 计数已同步：%s；%s；%s" % (hero_msg, status_msg, count_msg))
    raise SystemExit(0)

# ================= 分支 B：legacy 旧页面（<h5> 分区 + card-group + #cite 锚点）=================
doi_html = (f'          <p class="card-text" style="font-size:90%;">'
            f'<a style="color: grey;" href="https://doi.org/{doi}" target="_blank">doi:{doi}</a></p>\n'
            if doi else "")
card = (f'      <div class="card">\n        <div class="card-body">\n'
        f'          <h5 class="card-title"><a class="card-title" href="/jbrowse-1.12.3-release/?data={ds}">{label}</a></h5>\n'
        f'{doi_html}'
        f'        </div>\n      </div>\n')
new_section = (f'    <div align="center"><span class="badge badge-primary badge-pill">'
               f'<h5>&nbsp;&nbsp;&nbsp;&nbsp;{section}&nbsp;&nbsp;&nbsp;&nbsp;</h5></span></div>\n'
               f'    <div class="card-group">\n{card}    </div>\n    <br>\n')

def insert_into_section(text, name):
    """把单张卡插到既有分区 card-group 的末尾"""
    h = re.search(r'<h5>(?:&nbsp;)*\s*' + re.escape(name), text)
    if not h:
        return None
    g = text.find('<div class="card-group">', h.end())
    if g < 0:
        return None
    pos = g + len('<div class="card-group">')
    depth = 1
    tok = re.compile(r'<div\b[^>]*>|</div>')
    for m in tok.finditer(text, pos):
        depth += -1 if m.group(0) == '</div>' else 1
        if depth == 0:
            return m.start()          # card-group 的闭合 </div> 之前
    return None

if sec_existing:
    at = insert_into_section(t, sec_existing)
    if at is None:
        print(f"  [WARN] 找不到分区 '{sec_existing}'，改为新建分区")
        sec_existing = ""
    else:
        if dry:
            print(f"  [DRY] 将插入 '{sec_existing}' 分区：", label); raise SystemExit(0)
        tmp = p.with_suffix(".html.tmp")
        tmp.write_text(t[:at] + card + t[at:], encoding="utf-8"); tmp.replace(p)
        print(f"  [OK] 已插入 '{sec_existing}' 分区：", label); raise SystemExit(0)

anchor='<div id="cite"></div>'
i=t.rfind(anchor)
if i<0: print("  [ERR] 找不到 <div id=\"cite\"></div> 锚点"); raise SystemExit(2)
if dry:
    print("  [DRY] 将新建分区并插入卡片:", label); raise SystemExit(0)
tmp=p.with_suffix(".html.tmp")
tmp.write_text(t[:i]+new_section+t[i:], encoding="utf-8"); tmp.replace(p)
print("  [OK] 已新建分区并插入卡片:", label)
PY
  RC_CARD=$?
  [ "${RC_CARD:-1}" -eq 0 ] && CHANGED=$((CHANGED+1))
  [ "${RC_CARD:-1}" -ne 0 ] && fail "JBrowse 卡片插入失败"
}

# ---------------------------------------------------------------- 2) Web BLAST
step_blast_html() {
  log "--- 2) Web BLAST（group / hidden input / All genes / All proteins）---"
  if [ "$SKIP_HTML" = 1 ]; then log "跳过（--skip-html）"; return 0; fi
  # 新版 wheatBLAST SPA：库清单由 /api/blast/databases 动态生成，页面无手写 <optgroup>，
  # 改 HTML 反而会写坏 SPA → 直接跳过（验收改走 API，见 verify()）。
  if [ -f "$BLAST_HTML" ] \
     && grep -qE 'wheatBLAST SPA|blast-db-cats|api/blast/databases' "$BLAST_HTML" 2>/dev/null \
     && ! grep -q '<optgroup' "$BLAST_HTML" 2>/dev/null; then
    log "  [SPA] 库清单由 /api/blast/databases 动态生成，跳过 HTML 修改"; return 0
  fi
  DS="$DS" LABEL="$LABEL" GROUP="$GROUP" CHROMS_JOINED="$(printf '%s,' "${CHROMS[@]}")" DRY="$DRY" \
  python3 - "$BLAST_HTML" <<'PY'
import os,re,sys,pathlib
p=pathlib.Path(sys.argv[1]); t=p.read_text(encoding="utf-8")
ds=os.environ["DS"]; label=os.environ["LABEL"]; group=os.environ["GROUP"]
dry=os.environ.get("DRY")=="1"
chroms=[c for c in os.environ["CHROMS_JOINED"].split(",") if c]
changes=[]

# (a) group option —— 插到与分组匹配的 optgroup 末尾
if f"value='{ds}_chromosomes'" in t or f'value="{ds}_chromosomes"' in t:
    print("  [SKIP] group option 已存在")
else:
    gmap={"Tetraploid":"Tetraploid wheat genome","Hexaploid":"Hexaploid wheat genome",
          "Allohexaploid":"Allohexaploid chr genome","Diploid":"Diploid wheat genome",
          "Triticale":"Hexaploid Triticale genome","Other":"Other Triticeae genome"}
    key=gmap.get(group,"")
    pos=-1
    if key:
        m=re.search(r'<optgroup label="[^"]*'+re.escape(key)+r'[^"]*"[^>]*>', t)
        if m:
            end=t.find("</optgroup>", m.end())
            if end>0: pos=end
    if pos<0:
        m=re.search(r'<optgroup[^>]*>', t)
        if not m: print("  [ERR] 找不到 optgroup"); raise SystemExit(2)
        end=t.find("</optgroup>", m.end()); pos=end if end>0 else len(t)
    opt=f"<option value='{ds}_chromosomes'>{label} chromosomes</option>\n"
    t=t[:pos]+opt+t[pos:]
    changes.append("group option")

# (b) hidden input
if f"id='N{ds}_chromosomes'" in t or f'id="N{ds}_chromosomes"' in t:
    print("  [SKIP] hidden input 已存在")
else:
    items=[f"{ds}.genome=>{label} all chromosomes"]
    for c in chroms:
        short=c.replace("Chr","",1)
        items.append(f"{ds}.genome_{c}=>{label} chromosome {short}")
    val=",".join(items)
    line=(f"\t<input id='N{ds}_chromosomes' type ='hidden' "
          f"name='N{ds}_chromosomesdb[]' value='{val}'>\n")
    m=None
    for m in re.finditer(r"^[ \t]*<input id='N[^']*_chromosomes'[^\n]*\n", t, re.M):
        pass
    if m:
        pos=m.end()
    else:
        # 兜底：插到 <select name="group"> 所在 form 的末尾附近
        pos=t.find("</select>")
        pos=t.find("\n",pos)+1 if pos>0 else len(t)
    t=t[:pos]+line+t[pos:]
    changes.append("hidden input")

# (c) All genes / All proteins
def append_agg(text, input_id, member):
    m=re.search(r"<input id='"+re.escape(input_id)+r"'[^>]*?value='([^']*)'", text, re.S)
    if not m: return text, f"[ERR] 找不到 {input_id} 的 value"
    body=m.group(1)
    if member.split("=>")[0] in body:
        return text, f"[SKIP] {input_id} 已含成员"
    return text[:m.start(1)]+body+","+member+text[m.end(1):], f"{input_id} 追加"

t,msg=append_agg(t,"Nall_genes", f"{ds}.add_Description.cds=>{label} gene"); print("  "+msg)
if msg.endswith("追加"): changes.append("all_genes")
t,msg=append_agg(t,"Pall_proteins", f"{ds}.add_Description.pep=>{label} protein"); print("  "+msg)
if msg.endswith("追加"): changes.append("all_proteins")

if dry:
    print("  [DRY] 将修改:", (", ".join(changes) if changes else "（无，全部已存在）")); raise SystemExit(0)
tmp=p.with_suffix(".html.tmp"); tmp.write_text(t,encoding="utf-8"); tmp.replace(p)
print("  [OK] 已修改:", ", ".join(changes))
PY
  RC_BLAST=$?
  [ "${RC_BLAST:-1}" -eq 0 ] && CHANGED=$((CHANGED+1))
  [ "${RC_BLAST:-1}" -ne 0 ] && fail "blast.html 修改失败"
}

# ---------------------------------------------------------------- 3) .fai
step_fai() {
  log "--- 3) PrimerServer2 所需的 .fai ---"
  local f
  for f in "${BLASTDB}/${DS}.genome" "${BLASTDB}/${DS}.add_Description.cds"; do
    if [ -s "${f}.fai" ]; then
      log "  [SKIP] $(basename "$f").fai 已存在"
    elif [ "$DRY" = 1 ]; then
      log "  [DRY] samtools faidx $(basename "$f")"
    else
      samtools faidx "$f" && log "  [OK] $(basename "$f").fai（$(wc -l < "${f}.fai") 条）" || fail "faidx $(basename "$f") 失败"
      CHANGED=$((CHANGED+1))
    fi
  done
}

# ---------------------------------------------------------------- 4) Genefunc_registry
step_genefunc_registry() {
  log "--- 4) Genefunc_registry 行 ---"
  local LABEL="${LABEL:-$DS}"
  # display_order：同 Polyploidy 分组末尾 +1（失败时退回 500）
  local ORD="${PLAN_ORD:-500}"
  if [ -z "${PLAN_ORD:-}" ] && [ -r "$DDL_ENV" ]; then
    local DDL_USER DDL_PASS DDL_HOST
    DDL_USER="$(grep -E '^DB_USER=' "$DDL_ENV" | cut -d= -f2-)"
    DDL_PASS="$(grep -E '^DB_PASS=' "$DDL_ENV" | cut -d= -f2-)"
    DDL_HOST="$(grep -E '^DB_HOST=' "$DDL_ENV" | cut -d= -f2-)"
    ORD="$(mysql -h"${DDL_HOST:-localhost}" -u"${DDL_USER}" -p"${DDL_PASS}" -N -B \
            -e "SELECT COALESCE(MAX(display_order),0)+1 FROM Genefuncdb.Genefunc_registry WHERE Polyploidy='${PLOIDY}'" \
            2>/dev/null | head -1)"
    [ -n "$ORD" ] || ORD=500
  fi
  local sql
  sql="$(DS="$DS" LABEL="$LABEL" MYTAG="$MYTAG" PLOIDY="$PLOIDY" GROUP="$GROUP" DOI="$DOI" \
        TITLE="$TITLE" JB_FIRST="$JB_FIRST" FIRST_CDS="$FIRST_CDS" FIRST_PEP="$FIRST_PEP" \
        EXAMPLE_SPECIES_CHR="$EXAMPLE_SPECIES_CHR" ORD="$ORD" python3 - <<'PY'
import os
def q(s): return "'" + (s or "").replace("\\","\\\\").replace("'","''") + "'"
ds=os.environ["DS"]; label=os.environ["LABEL"]; tag=os.environ["MYTAG"]
ploidy=os.environ["PLOIDY"]; group=os.environ["GROUP"]; doi=os.environ["DOI"]
title=os.environ.get("TITLE","")
jb=os.environ.get("JB_FIRST",""); cds=os.environ["FIRST_CDS"]; pep=os.environ["FIRST_PEP"]
esc=os.environ.get("EXAMPLE_SPECIES_CHR","")
ordv=int(os.environ.get("ORD","500") or 500)
table=f"Genefunc_{ds}_table"
sql=f"""INSERT INTO Genefuncdb.Genefunc_registry
 (table_name, Accession, `Group`, Polyploidy, chromosome_level, Doi, title, Abstract,
  example_chr_id, example_gene_id, visible, display_order,
  example_species_chr_id, example_cds_id, example_protein_id, display_name)
VALUES
 ({q(table)}, {q(tag)}, {q(group)}, {q(ploidy)}, 'Yes', {q(doi)}, {q(title)}, '',
  {q(jb)}, {q(cds)}, 1, {ordv},
  {q(esc)}, {q(cds)}, {q(pep)}, {q(label)})
ON DUPLICATE KEY UPDATE
  Accession=VALUES(Accession), `Group`=VALUES(`Group`), Polyploidy=VALUES(Polyploidy),
  chromosome_level=VALUES(chromosome_level), Doi=VALUES(Doi), title=VALUES(title),
  example_chr_id=VALUES(example_chr_id), example_gene_id=VALUES(example_gene_id),
  example_species_chr_id=VALUES(example_species_chr_id), example_cds_id=VALUES(example_cds_id),
  example_protein_id=VALUES(example_protein_id), display_name=VALUES(display_name),
  display_order=VALUES(display_order), visible=1;"""
print(sql)
PY
)"
  if [ "$DRY" = 1 ]; then log "  [DRY] 将执行 upsert：table_name=Genefunc_${DS}_table, display_name=${LABEL}, group=${GROUP}, display_order=${ORD}"; return 0; fi
  local DDL_USER DDL_PASS DDL_HOST
  DDL_USER="$(grep -E '^DB_USER=' "$DDL_ENV" | cut -d= -f2-)"
  DDL_PASS="$(grep -E '^DB_PASS=' "$DDL_ENV" | cut -d= -f2-)"
  DDL_HOST="$(grep -E '^DB_HOST=' "$DDL_ENV" | cut -d= -f2-)"
  local MYSQL="mysql -h${DDL_HOST:-localhost} -u${DDL_USER} -p${DDL_PASS} --default-character-set=utf8mb4"
  local UPSERT_OUT
  UPSERT_OUT="$(printf '%s\n' "$sql" | $MYSQL 2>&1 | grep -v -E "Using a password|^mysql: \[Warning\]")"
  if printf '%s' "$UPSERT_OUT" | grep -qi "ERROR"; then
    warn "registry upsert 报错：$(printf '%s' "$UPSERT_OUT" | head -2)"
  fi
  if $MYSQL -B -N -e "SELECT COUNT(*) FROM Genefuncdb.Genefunc_registry WHERE table_name='Genefunc_${DS}_table'" 2>/dev/null | grep -qx 1; then
    log "  [OK] Genefunc_registry 行已存在"; CHANGED=$((CHANGED+1))
  else
    fail "Genefunc_registry 行未写入"
  fi
}

# ---------------------------------------------------------------- 5) 聚合库 alias
step_aliases() {
  log "--- 5) 聚合库 alias（all_genomes / all_gene / all_protein / type 表）---"
  ALIASES="1" DS="$DS" PLOIDY="$PLOIDY" BLASTDB="$BLASTDB" DRY="$DRY" \
  python3 - <<'PY'
import os,re,pathlib
b=pathlib.Path(os.environ["BLASTDB"]); ds=os.environ["DS"]; ploidy=os.environ["PLOIDY"]
dry=os.environ.get("DRY")=="1"
targets=[("all_genomes.nal", f"{ds}.genome"),
         ("all_gene.nal",     f"{ds}.add_Description.cds"),
         ("all_protein.pal",  f"{ds}.add_Description.pep"),
         ("all_genes.nal",    f"{ds}.add_Description.cds"),
         ("all_proteins.pal", f"{ds}.add_Description.pep")]
for fn,member in targets:
    p=b/fn
    if not p.exists(): print(f"  [WARN] 缺少 {fn}"); continue
    t=p.read_text(encoding="utf-8",errors="replace")
    if member in t.split():
        print(f"  [SKIP] {fn} 已含 {member}"); continue
    m=re.search(r"^(DBLIST[ \t]+)(.*)$", t, re.M)
    if not m: print(f"  [ERR] {fn} 里找不到 DBLIST 行"); continue
    if dry: print(f"  [DRY] {fn} DBLIST += {member}"); continue
    # 前插：BLAST 别名库最多读取前 200 个成员（blastdbcmd -entry_batch 会
    # "Skipped" 第 201 个及之后），前插保证新基因组立即可查，并提示超限。
    t=t[:m.start(2)]+member+((" " if m.group(2) else ""))+t[m.end(2):]
    tmp=p.with_suffix(p.suffix+".tmp"); tmp.write_text(t,encoding="utf-8"); tmp.replace(p)
    n_members=len(t[m.start(2):t.index("\n", m.start(2))].split())
    msg=f"  [OK] {fn} DBLIST += {member}（成员 {n_members}）"
    if n_members > 200:
        msg += f" [WARN] 超过 BLAST 别名 200 成员上限，尾部成员 -entry_batch 不可达"
    print(msg)
# all_genomes_type.txt
p=b/"all_genomes_type.txt"
if p.exists():
    t=p.read_text(encoding="utf-8",errors="replace")
    if f"{ds}.genome\t" in t or f"{ds}.genome " in t:
        print("  [SKIP] all_genomes_type.txt 已含该基因组")
    elif dry:
        print(f"  [DRY] all_genomes_type.txt += {ds}.genome\\t{ploidy}")
    else:
        if not t.endswith("\n"): t+="\n"
        t+=f"{ds}.genome\t{ploidy}\n"
        p.write_text(t,encoding="utf-8")
        print(f"  [OK] all_genomes_type.txt += {ds}.genome<tab>{ploidy}")
PY
  RC_ALIAS=$?
  [ "${RC_ALIAS:-1}" -eq 0 ] && CHANGED=$((CHANGED+1))
  [ "${RC_ALIAS:-1}" -ne 0 ] && fail "alias 追加失败"
}

# ---------------------------------------------------------------- 5b) GetSequence 文档示例
step_getsequence_doc() {
  log "--- 5b) GetSequence 文档示例（getsequence_search.txt）---"
  local DOC="${WHEATOMICS_GETSEQUENCE_DOC:-/var/www/html/doc/getsequence_search.txt}"
  local UPD="${REPO}/scripts/update_getsequence_search.py"
  if [ ! -f "$DOC" ]; then warn "缺少 ${DOC}，跳过 GetSequence 文档更新"; return 0; fi
  if [ ! -f "$UPD" ]; then warn "缺少 ${UPD}，跳过 GetSequence 文档更新"; return 0; fi
  local EXTRA=""
  [ "$DRY" = 1 ] && EXTRA="--dry-run"
  local OUT RC
  OUT="$(python3 "$UPD" --doc "$DOC" --name "$DS" --region "$EXAMPLE_SPECIES_CHR" \
          --gene "$FIRST_CDS" --composition "$PLOIDY" --library all_genomes $EXTRA 2>&1)"
  RC=$?
  if [ "$RC" -ne 0 ]; then
    fail "GetSequence 文档更新失败：$(printf '%s' "$OUT" | tail -2)"
  else
    log "  [OK] getsequence_search.txt 已更新（${DS}）"
    CHANGED=$((CHANGED+1))
  fi
}

# ---------------------------------------------------------------- 6-8) 元数据
run_registry_tools() {
  log "--- 6-8) jbrowse_meta 导入 / genome_registry 重建 / 元数据写回 ---"
  if [ "$SKIP_REGISTRY" = 1 ]; then log "跳过（--skip-registry）"; return 0; fi
  unset DB_PASS DB_HOST
  export DB_USER="wheatomics_user"
  set -a; . "$APP_ENV"; set +a
  export DB_PASSWORD
  if [ "$DRY" = 1 ]; then
    log "  [DRY] import_jbrowse_meta.py --dataset ${DS}"
    log "  [DRY] rebuild_genome_registry.py"
    log "  [DRY] UPDATE genome_registry 元数据（DOI/期刊/年份/物种 + 派生事实字段）"
    return 0
  fi
  ( cd "$REPO" && "$ZJW_PY" scripts/import_jbrowse_meta.py --dataset "$DS" >/tmp/imp_${DS}.log 2>&1 ) \
    && log "  [OK] jbrowse_meta 已导入" \
    || { warn "import_jbrowse_meta 失败：$(tail -2 /tmp/imp_${DS}.log 2>/dev/null)"; fail "jbrowse_meta 导入失败"; }
  ( cd "$REPO" && "$ZJW_PY" scripts/rebuild_genome_registry.py >/tmp/rgb_${DS}.log 2>&1 ) \
    && log "  [OK] genome_registry 已重建" \
    || { warn "rebuild_genome_registry 失败：$(tail -3 /tmp/rgb_${DS}.log 2>/dev/null)"; fail "genome_registry 重建失败"; }

  # ---- 派生事实：新基因组不在策展表里时，rebuild 会把这些留空，这里按产物补齐 ----
  local GENE_N="" ANN_OK=0
  [ -r "${DATA_ROOT}/${DS}/${MYTAG}.gff3" ] && \
    GENE_N="$(awk -F'\t' '$3=="gene"' "${DATA_ROOT}/${DS}/${MYTAG}.gff3" | wc -l)"
  [ -s "${DATA_ROOT}/${DS}/${DS}.add_eggnog_ChineseSpring02G.gff3" ] && ANN_OK=1

  local SETS
  SETS="$(DOI="$DOI" TITLE="$TITLE" JOURNAL="$JOURNAL" YEAR="$YEAR" SPECIES="$SPECIES" \
          CULTIVAR="$CULTIVAR" ACCESSION="$ACCESSION" SOURCE_URL="$SOURCE_URL" SOURCE_MD5="$SOURCE_MD5" \
          PAPER_CODE="$PAPER_CODE" DS_ENV="$DS" GENE_N="$GENE_N" ANN_OK="$ANN_OK" \
          SUBGENOMES="${SUBGENOMES:-}" \
          python3 - <<'PY'
import os
def q(s):
    return "'" + s.replace("\\", "\\\\").replace("'", "''") + "'"
m = [("doi","DOI"), ("paper_title","TITLE"), ("journal","JOURNAL"), ("publication_year","YEAR"),
     ("species","SPECIES"), ("cultivar_or_line","CULTIVAR"), ("assembly_accession","ACCESSION"),
     ("source_url","SOURCE_URL"), ("source_md5","SOURCE_MD5")]
parts = [f"{c}={q(os.environ[k])}" for c, k in m if os.environ.get(k)]
paper = (os.environ.get("PAPER_CODE") or "").strip().replace("'", "")
if paper:
    parts.append("notes=LEFT(CONCAT(COALESCE(notes,''), IF(COALESCE(notes,'')='', '', '; '), 'paper_code=" + paper + "'), 1000)")
ds = os.environ.get("DS_ENV", "")
gn = (os.environ.get("GENE_N") or "").strip()
if gn.isdigit() and int(gn) > 0:
    parts.append(f"gene_count={int(gn)}")
sub = (os.environ.get("SUBGENOMES") or "").strip()
if sub:
    parts.append(f"subgenomes={q(sub)}")
if os.environ.get("ANN_OK") == "1":
    parts.append("annotation_status='available'")
    parts.append("assembly_level='Chromosome'")
if ds:
    parts.append(f"gene_table={q('Genefunc_' + ds + '_table')}")
    for col in ("blast_genome_db", "blast_cds_db", "blast_pep_db", "jbrowse_dataset"):
        parts.append(f"{col}={q(ds)}")
    for col in ("getfasta_member", "primerserver_fai", "web_blast_group", "gene_function_ui"):
        parts.append(f"{col}=1")
print(", ".join(parts))
PY
)"
  if [ -n "$SETS" ]; then
    local MYSQL="mysql -h${DB_HOST:-localhost} -u${DB_USER:-wheatomics_user} -p${DB_PASSWORD} --default-character-set=utf8mb4"
    if echo "UPDATE wheatomics_db.genome_registry SET ${SETS} WHERE dataset_id='${DS}';" | $MYSQL 2>/dev/null; then
      log "  [OK] genome_registry 元数据 + 派生事实已写回"
    else
      fail "genome_registry 元数据写回失败"
    fi
  else
    log "  [SKIP] 未提供元数据参数"
  fi
}

# ------------------------------------------------------ 9) BLAST↔JBrowse 映射
# /api/blast/database/{db}/jbrowse 依赖这份离线映射；新基因组 / 重命名 BLAST 库 /
# 重建 JBrowse 数据（seq/refSeqs.json 变化）后都必须重建，否则 BLAST 结果页
# 不会出现 JBrowse 按钮。映射按染色体长度校验，长度不一致的组装会被拒绝。
step_jbrowse_map() {
  log "--- 9) BLAST↔JBrowse 映射（BLAST 命中跳转）---"
  if [ "$SKIP_REGISTRY" = 1 ]; then log "跳过（--skip-registry）"; return 0; fi
  if [ "$DRY" = 1 ]; then log "  [DRY] build_blast_jbrowse_map.py"; return 0; fi
  if [ ! -x "$ZJW_PY" ] || [ ! -f "$REPO/scripts/build_blast_jbrowse_map.py" ]; then
    warn "缺少 ${ZJW_PY} 或 build_blast_jbrowse_map.py，跳过（BLAST 命中将无法跳 JBrowse）"
    return 0
  fi
  if ( cd "$REPO" && "$ZJW_PY" scripts/build_blast_jbrowse_map.py >/tmp/jbmap_${DS}.log 2>&1 ); then
    log "  [OK] 映射已重建 $(tail -1 /tmp/jbmap_${DS}.log 2>/dev/null)"
  else
    warn "映射重建失败：$(tail -2 /tmp/jbmap_${DS}.log 2>/dev/null)"
  fi
  if "$ZJW_PY" -c 'import json,sys
m = json.load(open(sys.argv[1]))
e = m.get(sys.argv[2]) or {}
sys.exit(0 if (e.get("assembly_match") and (e.get("chroms") or e.get("norm"))) else 1)' \
      "$REPO/app/services/data/blast_jbrowse_map.json" "$DS" 2>/dev/null; then
    log "  [OK] 新基因组已进入映射表（BLAST 命中可跳 JBrowse）"
  else
    warn "新基因组未进入映射表：检查 JBrowse seq/refSeqs.json 与 BLAST ${DS}.genome 的染色体长度是否一致；复检：$ZJW_PY scripts/build_blast_jbrowse_map.py --check"
  fi
}

# ---------------------------------------------------------------- 10) 验收
verify() {
  log "--- 10) 验收 ---"
  # HTML / BLAST 库清单：新版 wheatBLAST SPA 由 /api/blast/databases 动态生成 → API 断言；
  # 旧页面保留原 blast.html grep。JBrowse 卡片的 ?data= 新旧页面都适用。
  grep -q "?data=${DS}" "$JBROWSE_HTML" \
    && log "  [OK] jbrowse.html 含卡片（?data=${DS}）" || fail "jbrowse.html 缺卡片"
  if [ -f "$BLAST_HTML" ] \
     && grep -qE 'wheatBLAST SPA|blast-db-cats|api/blast/databases' "$BLAST_HTML" 2>/dev/null \
     && ! grep -q '<optgroup' "$BLAST_HTML" 2>/dev/null; then
    local DBS_JSON
    DBS_JSON="$(curl -s --max-time 15 "${API}/api/blast/databases?program=blastn" 2>/dev/null)"
    if [ -z "$DBS_JSON" ]; then
      warn "${API}/api/blast/databases 不可达，跳过 BLAST 库清单断言（重启 API 后再验）"
    else
      local BLAST_VERDICT
      BLAST_VERDICT="$(printf '%s' "$DBS_JSON" | DS="$DS" EXPECT_CAT="$EXPECT_CAT" python3 -c '
import json, os, sys
ds = os.environ["DS"]
want = (os.environ.get("EXPECT_CAT") or "").strip() or "other_triticeae"
try:
    d = json.load(sys.stdin)
except Exception:
    print("BADJSON"); raise SystemExit
found = []
for c in d.get("categories") or []:
    cid, clabel = c.get("id") or "", c.get("label") or ""
    for db in c.get("databases") or []:
        if db == ds + ".genome" or db.startswith(ds + ".genome_") or db in (ds + ".add_Description.cds", ds + ".add_Description.pep"):
            found.append((cid, clabel, db))
if not found:
    print("MISS"); raise SystemExit
ids = set(x[0] for x in found)
labels = [x[1] for x in found]
hit = (want in ids) or any(want.lower() in (l or "").lower() for l in labels)
if hit:
    print("OK:" + (found[0][1] or found[0][0]))
else:
    print("CAT:%s:%s" % (found[0][0], found[0][1]))
')"
      case "$BLAST_VERDICT" in
        OK:*)   log "  [OK] /api/blast/databases 含 ${DS}.genome（分类 ${BLAST_VERDICT#OK:}）" ;;
        CAT:*)  fail "BLAST 分类不符：${BLAST_VERDICT#CAT:}（期望含 '${EXPECT_CAT:-other_triticeae}'）" ;;
        MISS)   fail "/api/blast/databases 未含 ${DS}.genome（BLAST 索引未建好 / API 缓存 1h）" ;;
        *)      warn "BLAST 库清单断言未执行（响应=${BLAST_VERDICT:-空}）" ;;
      esac
    fi
  else
    grep -q "${DS}_chromosomes" "$BLAST_HTML" \
      && log "  [OK] blast.html 含 group" || fail "blast.html 缺 group"
    grep -q "${DS}.add_Description.cds=>" "$BLAST_HTML" \
      && log "  [OK] blast.html All genes 含成员" || fail "blast.html All genes 缺成员"
  fi
  [ -s "${BLASTDB}/${DS}.genome.fai" ] && log "  [OK] genome .fai" || fail "缺 genome .fai"
  [ -s "${BLASTDB}/${DS}.add_Description.cds.fai" ] && log "  [OK] cds .fai" || fail "缺 cds .fai"

  # GetSequence 聚合库成员（页面 by-gene 默认查 all_genes/all_proteins）
  for pair in \
      "all_genomes.nal:${DS}.genome" \
      "all_gene.nal:${DS}.add_Description.cds" \
      "all_genes.nal:${DS}.add_Description.cds" \
      "all_protein.pal:${DS}.add_Description.pep" \
      "all_proteins.pal:${DS}.add_Description.pep"; do
    local AGG="${pair%%:*}" MEMBER="${pair#*:}"
    if [ -f "${BLASTDB}/${AGG}" ] && grep -qF -- "$MEMBER" "${BLASTDB}/${AGG}"; then
      log "  [OK] ${AGG} 含 ${MEMBER}"
    else
      warn "${AGG} 未含 ${MEMBER}（GetSequence 可能查不到该基因组/CDS/PEP）"
    fi
  done
  if curl -s --max-time 20 \
      "${API}/api/sequence/by-gene?gene_id=${FIRST_CDS}&gene_db=all_genes&protein_db=all_proteins" \
      | grep -q 'gene_sequence": ">'; then
    log "  [OK] /api/sequence/by-gene（all_genes/all_proteins）可取 ${FIRST_CDS}"
  else
    warn "/api/sequence/by-gene 未返回 ${FIRST_CDS}（检查聚合库 / 重启 API 后再验）"
  fi

  if [ -x "${BLASTX}/blastdbcmd" ]; then
    local n_std n_cds n_pep n_alias
    n_std=$("${BLASTX}/blastdbcmd" -db "${BLASTDB}/${DS}.genome" -info 2>/dev/null | awk -F';' '/sequences/{gsub(/[^0-9]/,"",$1); print $1}')
    n_cds=$("${BLASTX}/blastdbcmd" -db "${BLASTDB}/${DS}.add_Description.cds" -info 2>/dev/null | awk -F';' '/sequences/{gsub(/[^0-9]/,"",$1); print $1}')
    n_pep=$("${BLASTX}/blastdbcmd" -db "${BLASTDB}/${DS}.add_Description.pep" -info 2>/dev/null | awk -F';' '/sequences/{gsub(/[^0-9]/,"",$1); print $1}')
    log "  BLAST 库序列数: genome=${n_std:-?} cds=${n_cds:-?} pep=${n_pep:-?}"
    [ -n "${n_std:-}" ] && [ "${n_std:-0}" -gt 0 ] || fail "genome BLAST 库异常"
    n_alias=$("${BLASTX}/blastdbcmd" -db "${BLASTDB}/all_genomes" -entry "$STD_FIRST" -range 1-40 2>/dev/null | tr -d '\n' | wc -c)
    [ "${n_alias:-0}" -gt 0 ] && log "  [OK] all_genomes alias 可查 ${STD_FIRST}" || fail "all_genomes alias 查不到 ${STD_FIRST}"
  fi

  local MYSQL
  if [ -z "${DB_PASSWORD:-}" ] && [ -r "$APP_ENV" ]; then
    unset DB_PASS DB_HOST
    export DB_USER="wheatomics_user"
    set -a; . "$APP_ENV"; set +a
  fi
  MYSQL="mysql --connect-timeout=5 -B -N -u ${DB_USER:-wheatomics_user} -p${DB_PASSWORD:-}"
  local cnt
  cnt=$($MYSQL -e "SELECT COUNT(*) FROM Genefuncdb.Genefunc_${DS}_table" 2>/dev/null | head -1)
  [ -n "${cnt:-}" ] && log "  [OK] Genefunc 表行数: ${cnt}" || warn "查不到 Genefunc_${DS}_table（可能需要 DDL 账号）"

  for ep in "/api/jbrowse/datasets" "/api/PrimerServer2/databases"; do
    if curl -s --max-time 10 "${API}${ep}" | grep -q "${DS}"; then
      log "  [OK] ${ep} 含 ${DS}"
    else
      warn "${ep} 暂未含 ${DS}（新库缓存 / 需重启 API）"
    fi
  done
  if curl -s --max-time 10 "${API}/api/sequence/by-interval?region=${EXAMPLE_SPECIES_CHR}&database=all_genomes" | grep -q ">${STD_FIRST}"; then
    log "  [OK] /api/sequence/by-interval 取序列成功"
  else
    warn "/api/sequence/by-interval 未返回序列（检查 alias / 缓存）"
  fi
  if curl -s --max-time 10 "${API}/api/genes/functions/registry" | grep -q "Genefunc_${DS}_table"; then
    log "  [OK] /api/genes/functions/registry 含新表"
  else
    warn "/api/genes/functions/registry 暂未含新表"
  fi
  grep -q "${DS}.genome" "${BLASTDB}/all_genomes.nal" 2>/dev/null \
    && log "  [OK] all_genomes.nal 含成员" || warn "all_genomes.nal 未见成员"

  # BLAST 命中 -> JBrowse 跳转的映射（/api/blast/database/{db}/jbrowse）
  if [ -f "$REPO/app/services/data/blast_jbrowse_map.json" ] && \
     "$ZJW_PY" -c 'import json,sys
m = json.load(open(sys.argv[1]))
e = m.get(sys.argv[2]) or {}
sys.exit(0 if (e.get("assembly_match") and (e.get("chroms") or e.get("norm"))) else 1)' \
       "$REPO/app/services/data/blast_jbrowse_map.json" "$DS" 2>/dev/null; then
    log "  [OK] BLAST↔JBrowse 映射含 ${DS}"
  else
    warn "BLAST↔JBrowse 映射未含 ${DS}（新基因组将没有 JBrowse 跳转按钮；重建：build_blast_jbrowse_map.py）"
  fi
  if curl -s --max-time 10 "${API}/api/jbrowse/coverage" | python3 -c 'import json,sys
try: d=json.load(sys.stdin)["data"]
except Exception: sys.exit(1)
sys.exit(0 if d.get("ok") else 1)' 2>/dev/null; then
    log "  [OK] /api/jbrowse/coverage ok=true"
  else
    warn "/api/jbrowse/coverage 未通过（registry/jbrowse_meta/映射表有缺口，详见该接口）"
  fi

  # 分类归属（需要 API 缓存刷新；不符时给修法提示）
  if [ -n "$EXPECT_CAT" ]; then
    local CAT_HIT
    CAT_HIT="$(curl -s --max-time 20 "${API}/api/blast/databases" | DS="$DS" python3 -c '
import json,os,sys
ds=os.environ["DS"]
try: d=json.load(sys.stdin)
except Exception: print(""); raise SystemExit
for c in d.get("categories") or []:
    dbs=c.get("databases") or []
    if any(ds in x for x in dbs):
        print(c.get("label") or ""); break
' 2>/dev/null)"
    if [ -z "$CAT_HIT" ]; then
      warn "API 分类里还没出现 ${DS}（/api/blast/databases 有 1h 缓存，重启 API 后再验）"
    elif printf '%s' "$CAT_HIT" | grep -qi "$EXPECT_CAT"; then
      log "  [OK] 分类归属：${CAT_HIT}"
    else
      fail "分类归属不符：实际 '${CAT_HIT}'，期望含 '${EXPECT_CAT}' → 给 blast.py 加关键词或改用带关键词的 MYTAG"
    fi
  fi
}

# ---------------------------------------------------------------- 收尾提示
print_next_steps() {
  local PLOIDY_LC
  PLOIDY_LC="$(printf '%s' "$PLOIDY" | tr '[:upper:]' '[:lower:]')"   # 兼容 bash 3.2（不用 ${VAR,,}）
  echo
  log "=== 剩余手工步骤 ==="
  cat <<EOF
  1) getfasta / Web BLAST 分类（需改代码，不在本脚本范围）：
     在 ${REPO}/app/api/routers/blast.py 的 DB_CLASSIFICATION 里加一条，例如
       {"id": "${PLOIDY_LC}", "label": "${LABEL}", "description": "...", "keywords": ["${MYTAG}"]}
     然后：本地 commit → push origin/github → 服务器 git fetch && git merge --ff-only → 重启 API
  2) 重启 API（DB 列表缓存 1h / sequence 缓存 1h）：
       sudo systemctl restart wheatomics-api     # 或用本脚本 --restart-api
  3) 可选：cite.html 引文、JBrowse 额外注释轨道（TE/CENH5 等）
     · 加轨道只改 trackList，不影响 BLAST 跳转；但若改了 seq/refSeqs.json
       （增删/重命名 refseq 或换组装版本），必须重跑：
         ${ZJW_PY} ${REPO}/scripts/build_blast_jbrowse_map.py
         ${ZJW_PY} ${REPO}/scripts/build_blast_jbrowse_map.py --check   # 期望 CHECK OK
  4) 记录 provenance（材料身份/登录号/文章代号）：<data_dir>/provenance.txt
  5) 更新技能 manifest：
       ~/.agents/skills/lab-server/servers/wheatomics.yaml 追加条目并跑 scripts/validate.sh
EOF
  [ -d "$BACKUP" ] && log "本次改动备份：${BACKUP}"
  log "执行步骤计数：${CHANGED}；失败计数：${FAILED}"
}

# ---------------------------------------------------------------- 主流程
backup_files
step_jbrowse_card
step_blast_html
step_fai
step_genefunc_registry
step_aliases
step_getsequence_doc
run_registry_tools
step_jbrowse_map
verify

if [ "$RESTART" = 1 ] && [ "$DRY" = 0 ]; then
  log "--- 重启 wheatomics-api ---"
  if sudo -n true 2>/dev/null; then
    sudo systemctl restart wheatomics-api && log "  [OK] 已重启" || fail "重启失败"
  elif [ -n "${WHEATOMICS_SUDO_PASS:-}" ]; then
    echo "$WHEATOMICS_SUDO_PASS" | sudo -S systemctl restart wheatomics-api 2>/dev/null \
      && log "  [OK] 已重启" || fail "重启失败（sudo 密码不对？）"
  else
    warn "需要 sudo 密码：直接执行 sudo systemctl restart wheatomics-api，或设置 WHEATOMICS_SUDO_PASS 后重跑 --restart-api"
  fi
fi

print_next_steps
[ "$DRY" = 1 ] && log "（dry-run 结束，未改动任何文件）"
[ "$FAILED" -eq 0 ] && exit 0 || exit 1
