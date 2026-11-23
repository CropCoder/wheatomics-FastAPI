#!/bin/bash
# -*- coding: utf-8 -*-

############################################################
# wheat_data.sh (fixed + cds/pep keep .add_Description
#                + Step 0 内容质检
#                + Step 6 挪到 Step 7.3 之后，读最终 GFF 判断)
#
# 2026-10-21 修改：
#   - Step 1 直接产出 ${PLOIDY}_${MYTAG}.genome（修复 Step 2/3 找不到文件）
#   - Step 1 增加输入格式校验：FASTA 头必须 Chr+数字、GFF3 染色体必须在 FASTA 中存在、
#     标准化后序列名不能重复；不合规直接报错并提示怎么改
#   - 去掉 FASTA 头里的字面量 "ploidy"
#   - FASTA 头模板做成可选第 4 个参数（占位符 {sid} {chrom} {MYTAG} {PLOIDY}）
#   - 新增 Step 10：收尾自动跑 import_jbrowse_meta.py，把 ${PLOIDY}_${MYTAG} 同步进 jbrowse_meta 库
#
# 执行顺序：
#   Step 0  内容质检
#   Step 1  输入格式校验 + FASTA 标准化 → ${PLOIDY}_${MYTAG}.genome
#   Step 2  拆分 genome
#   Step 3  拷贝 genome 到 blastdb
#   Step 4  建 BLAST 核酸库
#   Step 5  BLAST 核酸软链
#   Step 6a 创建 JBrowse 目录
#   Step 7  EggNOG / BED / GFF / CDS / PEP / ChineseSpring02G
#     Step 7.1  EggNOG
#     Step 7.2  BED + 注释
#     Step 7.2.1 注册 MySQL
#     Step 7.3  GFF/CDS/PEP + 02G
#     Step 7.3.1 拷 CDS/PEP 到 blastdb
#     Step 7.4  建 CDS/PEP BLAST 库
#     Step 7.5  CDS/PEP 软链
#     Step 7.6  GFF 导入 JBrowse
#   Step 6b JBrowse 参考序列（读最终 GFF）
#   Step 8  JBrowse gene name 搜索索引
#   Step 9  BED 加 ChineseSpring02G
#   Step 10 JBrowse 元数据导入 jbrowse_meta（/api/jbrowse/datasets 依赖）
############################################################

set -euo pipefail

#############################
# 全局变量
#############################

CURRENT_STEP="初始化"
CURRENT_CMD=""

#############################
# 日志函数
#############################

log_line() {
    echo "============================================================"
}

step_start() {
    CURRENT_STEP="$1"
    log_line
    echo "[START] $CURRENT_STEP"
    echo "[INFO]  $2"
    echo "[INFO]  工作目录: $(pwd)"
    log_line
}

step_ok() {
    echo "[OK]    $CURRENT_STEP 完成"
    echo
}

error_exit() {
    local exit_code="$1"

    echo
    log_line
    echo "[ERROR] $CURRENT_STEP FAILED"
    echo "[ERROR] 返回值: $exit_code"
    echo "[ERROR] 工作目录: $(pwd)"

    if [ -n "$CURRENT_CMD" ]; then
        echo "[ERROR] 失败命令:"
        echo "[ERROR] $CURRENT_CMD"
    fi

    echo "[ERROR] Pipeline stopped."
    log_line
    exit "$exit_code"
}

run_cmd() {
    CURRENT_CMD="$*"

    echo "[CMD] $CURRENT_CMD"
    "$@"
    local rc=$?

    if [ $rc -ne 0 ]; then
        error_exit $rc
    fi
}

run_shell() {
    CURRENT_CMD="$1"

    echo "[CMD] $CURRENT_CMD"
    bash -c "$CURRENT_CMD"
    local rc=$?

    if [ $rc -ne 0 ]; then
        error_exit $rc
    fi
}

check_file() {
    local file="$1"
    local description="$2"

    if [ ! -s "$file" ]; then
        echo "[ERROR] 输出文件不存在或为空: $file"
        echo "[ERROR] $description"
        error_exit 1
    fi

    echo "[CHECK] $description : OK"
}

check_dir() {
    local dir="$1"
    local description="$2"

    if [ ! -d "$dir" ]; then
        echo "[ERROR] 输出目录不存在: $dir"
        echo "[ERROR] $description"
        error_exit 1
    fi

    echo "[CHECK] $description : OK"
}

check_command() {
    local cmd="$1"

    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "[ERROR] 找不到命令: $cmd"
        echo "[ERROR] 请检查环境或 PATH。"
        error_exit 127
    fi
}

# [FIX-2] 统一的 conda 激活函数
# 为了兼容 set -u，source/activate 期间临时关闭 -u
activate_env() {
    local env_name="$1"

    if ! command -v conda >/dev/null 2>&1; then
        echo "[ERROR] 找不到 conda 命令"
        error_exit 127
    fi

    # shellcheck disable=SC1091
    set +u
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate "$env_name"
    local rc=$?
    set -u

    if [ $rc -ne 0 ]; then
        echo "[ERROR] conda activate $env_name 失败"
        error_exit 1
    fi

    echo "[INFO] 已激活 conda 环境: $env_name"
}

#############################
# 参数检查
#############################

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
    echo "用法:"
    echo "  bash add_wheat_genome.sh <基因组名称> <数据路径(绝对路径)> <倍性> [FASTA头模板]"
    echo
    echo "输入文件（放在数据路径下，文件名固定，且必须符合 WheatOmics 格式）:"
    echo "  \${MYTAG}.fa    FASTA，序列头必须以 Chr 开头（如 >Chr1A / >Chr1At）"
    echo "  \${MYTAG}.gff3  GFF3，第 1 列染色体名必须与 FASTA 一致"
    echo "  \${MYTAG}.cds / \${MYTAG}.pep"
    echo
    echo "例如:"
    echo "  bash add_wheat_genome.sh XM000834 /var/www/data/masw_data/XM000834 AABB"
    echo
    echo "可选第 4 个参数：FASTA 头模板，占位符 {sid} {chrom} {MYTAG} {PLOIDY}"
    echo "  默认: >{sid} {MYTAG} {PLOIDY} {chrom}   → 如 >Chr1A_Abo Abo AABBDD Chr1A"
    exit 1
fi

MYTAG="$1"
data_path="$2"
PLOIDY="$3"
HEADER_TEMPLATE="${4:-}"
[ -n "$HEADER_TEMPLATE" ] || HEADER_TEMPLATE='>{sid} {MYTAG} {PLOIDY} {chrom}'

############################################################
# [NEW 2026-10-23] 命名/分类门禁
#   数据集名 PLOIDY_MYTAG 会绑定 BLAST 库名 / JBrowse 数据集 / MySQL 表名 /
#   聚合库 alias / all_genomes_type.txt；跑完再改名代价极高。
#   跑本脚本之前必须先用技能脚本确认并落盘 name_plan.json：
#     finish_genome_integration.sh <PLOIDY> <MYTAG> <DOI> --check-name --write-plan --confirm
#   确需跳过：WHEATOMICS_SKIP_NAMING_GATE=1 bash add_wheat_genome.sh ...
############################################################

if [ "${WHEATOMICS_SKIP_NAMING_GATE:-0}" != "1" ]; then
    PLAN_FILE="${data_path}/name_plan.json"
    if [ ! -s "$PLAN_FILE" ]; then
        echo "[ERROR] 缺少命名/分类预检方案: $PLAN_FILE"
        echo "        数据集名会绑定 BLAST 库名/JBrowse 数据集/MySQL 表名/聚合库 alias，跑完再改代价极高。"
        echo "        先执行（在 ~/.agents/skills/lab-server/scripts 下或服务器 _prep 副本）："
        echo "          finish_genome_integration.sh ${PLOIDY} ${MYTAG} <DOI> --check-name"
        echo "          finish_genome_integration.sh ${PLOIDY} ${MYTAG} <DOI> --check-name --write-plan --confirm"
        echo "        确需跳过：WHEATOMICS_SKIP_NAMING_GATE=1 bash add_wheat_genome.sh ..."
        exit 1
    fi
    PLAN_DS=$(grep -o '"ds"[[:space:]]*:[[:space:]]*"[^"]*"' "$PLAN_FILE" | head -1 | sed -E 's/.*"([^"]*)"$/\1/')
    if [ -n "$PLAN_DS" ] && [ "$PLAN_DS" != "${PLOIDY}_${MYTAG}" ]; then
        echo "[ERROR] name_plan.json 的 ds=${PLAN_DS} 与本次 ${PLOIDY}_${MYTAG} 不一致（改名了？重新 --check-name --write-plan）"
        exit 1
    fi
    echo "[INFO] 命名/分类方案: $PLAN_FILE (ds=${PLAN_DS:-?})"
fi


if [[ "$data_path" != /* ]]; then
    echo "[ERROR] data_path 必须是绝对路径（脚本中途会 cd 到 /var/www/html 下的目录再回来）"
    echo "[ERROR] 你给的是: $data_path"
    exit 1
fi

if [ ! -d "$data_path" ]; then
    echo "[ERROR] 数据目录不存在: $data_path"
    exit 1
fi

if [ ! -f "$data_path/${MYTAG}.fa" ]; then
    echo "[ERROR] 输入 FASTA 不存在: $data_path/${MYTAG}.fa"
    exit 1
fi

if [ ! -f "$data_path/${MYTAG}.gff3" ]; then
    echo "[ERROR] 输入 GFF3 不存在: $data_path/${MYTAG}.gff3"
    exit 1
fi

if [ ! -f "$data_path/${MYTAG}.pep" ]; then
    echo "[ERROR] 输入 PEP 不存在: $data_path/${MYTAG}.pep"
    exit 1
fi

if [ ! -f "$data_path/${MYTAG}.cds" ]; then
    echo "[ERROR] 输入 CDS 不存在: $data_path/${MYTAG}.cds"
    exit 1
fi

cd "$data_path" || exit 1

log_line
echo "[START] wheat_data.sh"
echo "[INFO] 基因组名称 : ${MYTAG}"
echo "[INFO] 数据路径   : ${data_path}"
echo "[INFO] 倍性       : ${PLOIDY}"
echo "[INFO] 开始时间   : $(date '+%Y-%m-%d %H:%M:%S')"
log_line

#############################
# 基础命令检查
#############################

CURRENT_STEP="初始化：检查基础命令"

for cmd in sed cp makeblastdb python3 awk grep; do
    check_command "$cmd"
done

step_ok

############################################################
# Step 0
# 输入文件内容质检
############################################################

step_start \
"Step 0" \
"输入文件内容质检（check_genome_files.py）"

cd "$data_path" || error_exit 1

run_cmd \
python3 \
/var/www/html/Script/check_genome_files.py \
"${MYTAG}"

check_file "${MYTAG}.fa"   "质检后 FASTA"
check_file "${MYTAG}.gff3" "质检后 GFF3"
check_file "${MYTAG}.cds"  "质检后 CDS"
check_file "${MYTAG}.pep"  "质检后 PEP"

step_ok

############################################################
# Step 1
# FASTA 头信息标准化
############################################################

step_start \
"Step 1" \
"校验输入格式 + 标准化 FASTA 序列头 → ${PLOIDY}_${MYTAG}.genome"

# ---- 校验 1：FASTA 序列头必须以 Chr 开头（染色体 Chr+数字；未定位 ChrUn_* 也允许）----
BAD_HEADERS=$( grep -E '^>' "${MYTAG}.fa" | grep -vE '^>Chr' | head -5 || true )
if [ -n "$BAD_HEADERS" ]; then
    echo "[ERROR] FASTA 序列头不符合要求，必须以 Chr 开头（如 >Chr1A / >Chr1At，或未定位序列 >ChrUn_xxx）"
    echo "[ERROR] 不符合的序列头（最多显示 5 条）:"
    echo "$BAD_HEADERS"
    echo "[ERROR] 请先修正 ${data_path}/${MYTAG}.fa 的序列头后重跑。"
    error_exit 1
fi

# ---- 校验 2：GFF3 的染色体名必须都能在 FASTA 中找到 ----
awk -F'\t' '!/^#/ && NF>=9 {print $1}' "${MYTAG}.gff3" | sort -u > ._gff_chroms.txt
grep -E '^>' "${MYTAG}.fa" | awk '{ sub(/^>/,""); split($0, a, /[ \t]+/); print a[1] }' | sort -u > ._fa_chroms.txt
MISSING_CHROMS=$( grep -Fxv -f ._fa_chroms.txt ._gff_chroms.txt | head -5 || true )
rm -f ._gff_chroms.txt ._fa_chroms.txt
if [ -n "$MISSING_CHROMS" ]; then
    echo "[ERROR] GFF3 中的染色体在 FASTA 中不存在（命名不一致）:"
    echo "$MISSING_CHROMS"
    echo "[ERROR] 请统一 ${MYTAG}.fa 与 ${MYTAG}.gff3 的染色体命名后重跑。"
    error_exit 1
fi

# ---- 校验 3：染色体名若带下划线（如 Chr1_part1），拆分脚本会按 Chr1 归一，提醒风险 ----
BAD_CHROM_NAME=$( grep -E '^>' "${MYTAG}.fa" | awk '{ sub(/^>/,""); split($0, a, /[ \t]+/); if (a[1] ~ /_/ && a[1] !~ /^ChrUn_/) { print a[1]; exit } }' || true )
if [ -n "$BAD_CHROM_NAME" ]; then
    echo "[WARNING] 染色体名含下划线: $BAD_CHROM_NAME"
    echo "[WARNING] split_fasta_by_chrom.py 只识别 Chr+数字+字母，形如 Chr1_part1 会被归并成 Chr1；"
    echo "[WARNING] 若同一染色体有多个 part，请先把它们合并成一条后再跑。"
fi

# ---- 标准化序列头：>Chr1A → >Chr1A_<MYTAG> <MYTAG> <PLOIDY> Chr1A（模板可覆盖）----
# 注意：这里不能写 `run_cmd awk ... > file`，否则 run_cmd 的 "[CMD] ..." 日志会被重定向进 genome 文件
echo "[CMD] awk standardize-headers > ${PLOIDY}_${MYTAG}.genome"
CURRENT_CMD="awk standardize-headers ${MYTAG}.fa > ${PLOIDY}_${MYTAG}.genome"
awk \
-v tag="$MYTAG" \
-v ploidy="$PLOIDY" \
-v tpl="$HEADER_TEMPLATE" '
/^>/ {
    line = $0
    sub(/^>/, "", line)
    split(line, f, /[ \t]+/)
    chrom = f[1]

    # 未定位序列（ChrUn_*）保持原样：不加 _<MYTAG> 后缀，保证与 GFF/BED 的 seqid 一致
    if (chrom ~ /^ChrUn_/) {
        print
        next
    }

    suffix = "_" tag
    base = chrom
    if (length(chrom) >= length(suffix) && substr(chrom, length(chrom) - length(suffix) + 1) == suffix) {
        base = substr(chrom, 1, length(chrom) - length(suffix))
    }
    sid = base suffix

    out = tpl
    gsub(/\{sid\}/, sid, out)
    gsub(/\{chrom\}/, base, out)
    gsub(/\{MYTAG\}/, tag, out)
    gsub(/\{PLOIDY\}/, ploidy, out)
    print out
    next
}
{ print }' \
"${MYTAG}.fa" > "${PLOIDY}_${MYTAG}.genome"
AWK_RC=$?
if [ "$AWK_RC" -ne 0 ]; then
    echo "[ERROR] 标准化 FASTA 头失败（awk rc=$AWK_RC）"
    error_exit 1
fi

# ---- 校验 4：标准化后序列名不能重复 ----
DUP_IDS=$( grep -E '^>' "${PLOIDY}_${MYTAG}.genome" | awk '{print $1}' | sort | uniq -d | head -5 || true )
if [ -n "$DUP_IDS" ]; then
    echo "[ERROR] 标准化后序列名重复（输入 FASTA 里染色体名不唯一）:"
    echo "$DUP_IDS"
    error_exit 1
fi

check_file "${PLOIDY}_${MYTAG}.genome" "标准化 FASTA"

step_ok

############################################################
# Step 2
# 按染色体拆分 genome
############################################################

step_start \
"Step 2" \
"按染色体拆分 genome FASTA"

run_cmd \
python3 \
/var/www/html/Script/split_fasta_by_chrom.py \
"${PLOIDY}_${MYTAG}.genome"

shopt -s nullglob
chrom_files=( "${PLOIDY}_${MYTAG}.genome_"* )
shopt -u nullglob

if [ "${#chrom_files[@]}" -eq 0 ]; then
    echo "[ERROR] 没有发现拆分后的染色体 FASTA 文件"
    error_exit 1
fi

echo "[CHECK] 染色体 FASTA 数量: ${#chrom_files[@]}"

step_ok

############################################################
# Step 3
# 拷贝 genome 到 BLAST 数据库目录
############################################################

step_start \
"Step 3" \
"拷贝 genome 文件到 BLAST 数据库目录"

check_dir \
"/var/www/html/getfasta/blastdb" \
"BLAST 数据库目录"

run_shell \
"cp \"${PLOIDY}_${MYTAG}.genome\"* /var/www/html/getfasta/blastdb/"

check_file \
"/var/www/html/getfasta/blastdb/${PLOIDY}_${MYTAG}.genome" \
"主 genome 文件"

step_ok

############################################################
# Step 4
# 建立 BLAST 数据库
############################################################

step_start \
"Step 4" \
"为每条染色体建立 BLAST 核酸数据库"

cd /var/www/html/getfasta/blastdb || error_exit 1

shopt -s nullglob
blast_genomes=( "${PLOIDY}_${MYTAG}.genome_"* )
shopt -u nullglob

if [ "${#blast_genomes[@]}" -eq 0 ]; then
    echo "[ERROR] BLAST 数据库目录中没有 ${PLOIDY}_${MYTAG}.genome_*"
    error_exit 1
fi

for i in "${blast_genomes[@]}"; do

    # 只处理 split_fasta_by_chrom.py 产出的纯 FASTA（<DS>.genome_Chr1H 等）；
    # 旧一轮的 BLAST 索引文件（.ndb/.nhr/.nin/.nsq/...）必须跳过，
    # 否则 makeblastdb 会把 .ndb 当成 FASTA 输入而报 "does not match input format"。
    _chrom="${i#*.genome_}"
    if [[ "$_chrom" == *"."* ]]; then
        continue
    fi

    echo "[INFO] 建立数据库: $i"

    run_cmd \
    makeblastdb \
    -in "$i" \
    -dbtype nucl \
    -parse_seqids \
    -out "$i"

    check_file "${i}.nhr" "BLAST nhr 索引"
    check_file "${i}.nin" "BLAST nin 索引"
    check_file "${i}.nsq" "BLAST nsq 索引"

done

# ---- 整基因组 BLAST 库（多卷 + .nal alias；BLAST 前端 “all chromosomes” 与 getfasta 整基因组查询依赖它）----
echo "[INFO] 建立整基因组数据库: ${PLOIDY}_${MYTAG}.genome"

run_cmd \
makeblastdb \
-in "${PLOIDY}_${MYTAG}.genome" \
-dbtype nucl \
-parse_seqids \
-out "${PLOIDY}_${MYTAG}.genome"

if [ -f "${PLOIDY}_${MYTAG}.genome.nal" ] || [ -f "${PLOIDY}_${MYTAG}.genome.nhr" ]; then
    echo "[OK] 整基因组 BLAST 库建立完成"
else
    echo "[ERROR] 整基因组 BLAST 库建立失败（既无 .nal 也无 .nhr）"
    error_exit 1
fi

step_ok

############################################################
# Step 5
# 建立 BLAST 软链接
############################################################

step_start \
"Step 5" \
"创建 Web BLAST nucleotide 软链接"

cd /var/www/html/blast/db/nucleotide || error_exit 1

run_shell \
"ln -sf /var/www/html/getfasta/blastdb/${PLOIDY}_${MYTAG}.gen* ./"

echo "[CHECK] BLAST nucleotide 软链接创建命令执行成功"

step_ok

############################################################
# Step 6a
# 创建 JBrowse 目录（仅建目录，参考序列在 Step 6b 建）
############################################################

step_start \
"Step 6a" \
"创建 JBrowse 物种目录"

cd /var/www/html/jbrowse-1.12.3-release || error_exit 1

if [ -d "${PLOIDY}_${MYTAG}" ]; then
    echo "[WARNING] JBrowse 目录已经存在: ${PLOIDY}_${MYTAG}"
    echo "[WARNING] 不删除已有目录。"
else
    run_cmd mkdir "${PLOIDY}_${MYTAG}"
fi

check_dir \
"/var/www/html/jbrowse-1.12.3-release/${PLOIDY}_${MYTAG}" \
"JBrowse 物种目录"

step_ok

############################################################
# Step 7
# EggNOG / BED / GFF / CDS / PEP / ChineseSpring02G
############################################################

step_start \
"Step 7" \
"EggNOG 注释、ChineseSpring02G 映射、BLAST 与 JBrowse 导入"

############################################################
# Step 7.1
# EggNOG 功能注释
############################################################

step_start \
"Step 7.1" \
"运行 EggNOG emapper"

activate_env eggnog

cd "$data_path" || error_exit 1

# 清理上一轮残留的 emapper 输出（否则 emapper 报 Output files detected in disk 而中止）
rm -f "${PLOIDY}_${MYTAG}_annotation".emapper.* "${PLOIDY}_${MYTAG}_annotation".emapper 2>/dev/null

run_cmd mkdir -p \
/var/www/data/tiantian_data/soft/emapperdb/tmp/${MYTAG}

run_cmd \
emapper.py \
-i "${MYTAG}.pep" \
--data_dir /var/www/data/tiantian_data/soft/emapperdb \
-m diamond \
--dmnd_db /var/www/data/tiantian_data/soft/emapperdb/eggnog_proteins.dmnd \
--pfam_realign realign \
--num_servers 3 \
--num_workers 4 \
--dbmem \
--scratch_dir /var/www/data/tiantian_data/soft/emapperdb/tmp/${MYTAG} \
--temp_dir /var/www/data/tiantian_data/soft/emapperdb/tmp/${MYTAG} \
--output_dir ./ \
--output "${PLOIDY}_${MYTAG}_annotation" \
--cpu 12

check_file \
"${PLOIDY}_${MYTAG}_annotation.emapper.annotations" \
"EggNOG annotation"

step_ok

############################################################
# Step 7.2
# GFF -> BED + EggNOG/Pfam 注释
############################################################

step_start \
"Step 7.2" \
"生成带 EggNOG/Pfam 注释的 BED"

activate_env new_env

cd "$data_path" || error_exit 1

run_shell \
"python3 -m jcvi.formats.gff bed --type=mRNA --key=ID \"${MYTAG}.gff3\" > \"${PLOIDY}_${MYTAG}.bed\""

check_file "${PLOIDY}_${MYTAG}.bed" "JCVI BED"

run_cmd \
python3 \
/var/www/html/jcvi_col/old/bed/add_eggnog_to_bed.py \
-b "${PLOIDY}_${MYTAG}.bed" \
-a "${PLOIDY}_${MYTAG}_annotation.emapper.annotations" \
-p /var/www/html/jcvi_col/old/bed/annotation/pfam/Pfam-A.hmm \
-o "${PLOIDY}_${MYTAG}_with_annotation.bed" \
--null "null"

check_file \
"${PLOIDY}_${MYTAG}_with_annotation.bed" \
"带 EggNOG/Pfam 注释 BED"

step_ok

############################################################
# Step 7.2.1
# BED 注册 MySQL
############################################################

step_start \
"Step 7.2.1" \
"将带注释 BED 注册到 MySQL"

run_cmd \
python \
/var/www/cgi-bin/register_genome.n.py \
"./${PLOIDY}_${MYTAG}_with_annotation.bed" \
"Genefunc_${PLOIDY}_${MYTAG}_table"

step_ok

############################################################
# Step 7.3
# GFF + CDS + PEP + ChineseSpring02G
############################################################

step_start \
"Step 7.3" \
"生成带 Description / PFAMs / ChineseSpring02G 的 GFF/CDS/PEP"

cd "$data_path" || error_exit 1

run_cmd \
python3 \
/var/www/html/Script/add_eggnogand02G_to_gff_cds.py \
-a "${PLOIDY}_${MYTAG}_annotation.emapper.annotations" \
-g "${MYTAG}.gff3" \
-c "${MYTAG}.cds" \
--pep "${MYTAG}.pep" \
--cs-index /var/www/html/Script/Chinese_Spring1.0.mpi \
--cs-gff3 /var/www/html/Script/IWGSC_v1.1.gff3 \
--miniprot /home/fei/mambaforge/envs/new_env/bin/miniprot \
--threads 50 \
--min-coverage 0.80 \
--min-identity 0.50 \
-o "${PLOIDY}_${MYTAG}.add_eggnog_ChineseSpring02G.gff3" \
-p "${PLOIDY}_${MYTAG}.add_Description.cds" \
--out-pep "${PLOIDY}_${MYTAG}.add_Description.pep"

check_file \
"${PLOIDY}_${MYTAG}.add_eggnog_ChineseSpring02G.gff3" \
"ChineseSpring02G GFF3"

check_file \
"${PLOIDY}_${MYTAG}.add_Description.cds" \
"带 Description/ChineseSpring02G CDS"

check_file \
"${PLOIDY}_${MYTAG}.add_Description.pep" \
"带 Description/ChineseSpring02G PEP"

step_ok

############################################################
# Step 7.3.1
# 拷贝 CDS / PEP 到 BLAST 目录（保留 .add_Description）
############################################################

step_start \
"Step 7.3.1" \
"拷贝更新后的 CDS/PEP 到 BLAST 数据库目录（保留 .add_Description）"

run_cmd \
cp \
"${data_path}/${PLOIDY}_${MYTAG}.add_Description.cds" \
"/var/www/html/getfasta/blastdb/${PLOIDY}_${MYTAG}.add_Description.cds"

run_cmd \
cp \
"${data_path}/${PLOIDY}_${MYTAG}.add_Description.pep" \
"/var/www/html/getfasta/blastdb/${PLOIDY}_${MYTAG}.add_Description.pep"

check_file \
"/var/www/html/getfasta/blastdb/${PLOIDY}_${MYTAG}.add_Description.cds" \
"BLAST CDS 输入"

check_file \
"/var/www/html/getfasta/blastdb/${PLOIDY}_${MYTAG}.add_Description.pep" \
"BLAST PEP 输入"

step_ok

############################################################
# Step 7.4
# 建立 CDS / PEP BLAST 数据库（.add_Description）
############################################################

step_start \
"Step 7.4" \
"建立 CDS 和 PEP BLAST 数据库（.add_Description）"

cd /var/www/html/getfasta/blastdb || error_exit 1

run_cmd \
makeblastdb \
-in "${PLOIDY}_${MYTAG}.add_Description.cds" \
-dbtype nucl \
-parse_seqids \
-out "${PLOIDY}_${MYTAG}.add_Description.cds"

check_file "${PLOIDY}_${MYTAG}.add_Description.cds.nhr" "CDS BLAST nhr"
check_file "${PLOIDY}_${MYTAG}.add_Description.cds.nin" "CDS BLAST nin"
check_file "${PLOIDY}_${MYTAG}.add_Description.cds.nsq" "CDS BLAST nsq"

run_cmd \
makeblastdb \
-in "${PLOIDY}_${MYTAG}.add_Description.pep" \
-dbtype prot \
-parse_seqids \
-out "${PLOIDY}_${MYTAG}.add_Description.pep"

check_file "${PLOIDY}_${MYTAG}.add_Description.pep.phr" "PEP BLAST phr"
check_file "${PLOIDY}_${MYTAG}.add_Description.pep.pin" "PEP BLAST pin"
check_file "${PLOIDY}_${MYTAG}.add_Description.pep.psq" "PEP BLAST psq"

step_ok

############################################################
# Step 7.5
# BLAST 软链接（.add_Description）
############################################################

step_start \
"Step 7.5" \
"创建 CDS/PEP BLAST 软链接（.add_Description）"

cd /var/www/html/blast/db/nucleotide || error_exit 1

run_shell \
"ln -sf /var/www/html/getfasta/blastdb/${PLOIDY}_${MYTAG}.add_Description.cd* ./"

cd /var/www/html/blast/db/protein || error_exit 1

run_shell \
"ln -sf /var/www/html/getfasta/blastdb/${PLOIDY}_${MYTAG}.add_Description.pe* ./"

step_ok

############################################################
# Step 7.6
# GFF 导入 JBrowse
############################################################

step_start \
"Step 7.6" \
"将带 ChineseSpring02G 的 GFF 导入 JBrowse"

activate_env new_env

cd "/var/www/html/jbrowse-1.12.3-release/${PLOIDY}_${MYTAG}" || error_exit 1

run_cmd \
cp \
"${data_path}/${PLOIDY}_${MYTAG}.add_eggnog_ChineseSpring02G.gff3" \
"/var/www/html/jbrowse-1.12.3-release/${PLOIDY}_${MYTAG}/"

run_cmd \
../bin/flatfile-to-json.pl \
--gff "${data_path}/${PLOIDY}_${MYTAG}.add_eggnog_ChineseSpring02G.gff3" \
--trackLabel all_gene \
--type mRNA \
--nameAttributes "ID" \
--out ./

if [ ! -f "trackList.json" ]; then
    echo "[WARNING] 没有检测到 trackList.json。"
    echo "[INFO] flatfile-to-json.pl 可能已经修改了已有 trackList.json。"
fi

step_ok

############################################################
# Step 6b  [MOVED]
# JBrowse 准备参考序列（现在在 Step 7.3 之后，读最终 GFF）
############################################################

step_start \
"Step 6b" \
"建立 JBrowse 参考序列（读最终 GFF 自动对齐染色体名）"

cd /var/www/html/jbrowse-1.12.3-release || error_exit 1

GFF_FILE="${data_path}/${PLOIDY}_${MYTAG}.add_eggnog_ChineseSpring02G.gff3"

if [ ! -s "$GFF_FILE" ]; then
    echo "[ERROR] 最终 GFF 不存在或为空: $GFF_FILE"
    echo "[ERROR] Step 7.3 可能没有成功生成它。"
    error_exit 1
fi

# 用 awk 稳健取第一条数据行的第 1 列
FIRST_SEQID=$(awk -F'\t' '!/^#/ && NF>=9 {print $1; exit}' "$GFF_FILE")

if [ -z "$FIRST_SEQID" ]; then
    echo "[ERROR] 无法从 GFF 中提取第一列染色体名: $GFF_FILE"
    error_exit 1
fi

echo "[INFO] GFF 文件        : $GFF_FILE"
echo "[INFO] GFF 第一列示例  : $FIRST_SEQID"

if [[ "$FIRST_SEQID" == *"_${MYTAG}"* ]]; then
    REF_FASTA="${data_path}/${PLOIDY}_${MYTAG}.genome"
    echo "[INFO] GFF 使用长名（带 _${MYTAG}），JBrowse 用 ${PLOIDY}_${MYTAG}.genome"
else
    REF_FASTA="${data_path}/${MYTAG}.fa"
    echo "[INFO] GFF 使用短名，JBrowse 用 ${MYTAG}.fa"
fi

if [ ! -s "$REF_FASTA" ]; then
    echo "[ERROR] 选定的参考 FASTA 不存在或为空: $REF_FASTA"
    error_exit 1
fi

run_cmd \
./bin/prepare-refseqs.pl \
--fasta "$REF_FASTA" \
--out "${PLOIDY}_${MYTAG}"

check_dir \
"/var/www/html/jbrowse-1.12.3-release/${PLOIDY}_${MYTAG}" \
"JBrowse genome 目录"

step_ok

############################################################
# Step 8
# JBrowse gene name 搜索索引
############################################################

step_start \
"Step 8" \
"建立 JBrowse gene name 搜索索引"

cd "/var/www/html/jbrowse-1.12.3-release/${PLOIDY}_${MYTAG}" || error_exit 1

run_cmd \
../bin/generate-names.pl \
-i \
--tracks all_gene \
--hashBits 16 \
--out ./

step_ok

############################################################
# Step 9
# BED 增加 ChineseSpring02G
############################################################

step_start \
"Step 9" \
"给带 EggNOG 注释的 BED 增加 ChineseSpring02G"

cd "$data_path" || error_exit 1

run_cmd \
python3 \
/var/www/html/Script/add_chinese_spring_to_bed.py \
--bed "${PLOIDY}_${MYTAG}_with_annotation.bed" \
--gff3 "${PLOIDY}_${MYTAG}.add_eggnog_ChineseSpring02G.gff3" \
--output "${PLOIDY}_${MYTAG}_with_annotation_ChineseSpring02G.bed"

check_file \
"${PLOIDY}_${MYTAG}_with_annotation_ChineseSpring02G.bed" \
"最终 ChineseSpring02G BED"

# [NEW] 行数检查，避免空匹配也算通过
FINAL_BED="${PLOIDY}_${MYTAG}_with_annotation_ChineseSpring02G.bed"
FINAL_LINES=$(wc -l < "$FINAL_BED")
if [ "$FINAL_LINES" -lt 2 ]; then
    echo "[ERROR] 输出 BED 行数过少 ($FINAL_LINES)，可能匹配失败"
    error_exit 1
fi
echo "[CHECK] 最终 BED 行数: $FINAL_LINES"

step_ok

############################################################
# Step 10
# 同步 JBrowse 元数据到 MySQL（jbrowse_meta）
############################################################

step_start \
"Step 10" \
"导入 JBrowse 元数据到 jbrowse_meta（/api/jbrowse/datasets 与 trackList 代理依赖）"

JBROWSE_REPO="/var/www/FastAPI_backend_Port8000"
JBROWSE_PY="/home/fei/mambaforge/envs/zjw/bin/python3"
JBROWSE_DATASET="${PLOIDY}_${MYTAG}"
IMPORT_SCRIPT="${JBROWSE_REPO}/scripts/import_jbrowse_meta.py"

if [ -f "$IMPORT_SCRIPT" ] && [ -x "$JBROWSE_PY" ]; then
    # import_jbrowse_meta.py 依赖 DB_PASSWORD（在仓库 .env 里），其余默认值见脚本
    set +u
    set -a
    # shellcheck disable=SC1091
    . "${JBROWSE_REPO}/.env"
    set +a
    set -u

    run_cmd \
    "$JBROWSE_PY" \
    "$IMPORT_SCRIPT" \
    --dataset "${JBROWSE_DATASET}"

    set +e
    DATASET_ROWS=$( mysql -h "${DB_HOST:-localhost}" -P "${DB_PORT:-3306}" \
        -u "${DB_USER:-wheatomics_user}" -p"${DB_PASSWORD}" -N \
        -e "SELECT COUNT(*) FROM jbrowse_meta.jbrowse_datasets WHERE id='${JBROWSE_DATASET}';" 2>/dev/null )
    set -e
    if [ "${DATASET_ROWS:-0}" -ge 1 ]; then
        echo "[CHECK] jbrowse_meta 已登记数据集: ${JBROWSE_DATASET}"
    else
        echo "[WARNING] jbrowse_meta 里查不到 ${JBROWSE_DATASET}，请检查上一步输出"
    fi
else
    echo "[WARNING] 跳过 Step 10：找不到 ${IMPORT_SCRIPT} 或 ${JBROWSE_PY}"
    echo "[WARNING] 手动执行: cd ${JBROWSE_REPO} && python3 scripts/import_jbrowse_meta.py --dataset ${JBROWSE_DATASET}"
fi

step_ok

############################################################
# [NEW 2026-10-22] 重建基因组信息库 genome_registry
#   表: wheatomics_db.genome_registry；脚本: scripts/rebuild_genome_registry.py
#   从 JBrowse / Genefunc_registry / blastdb / blast.html / all_genomes.nal
#   / synteny / orthofinder 等平台事实重建（幂等 upsert）
############################################################

if [ -f "${JBROWSE_REPO}/scripts/rebuild_genome_registry.py" ] && [ -x "${JBROWSE_PY}" ]; then
    set +u
    set -a
    . "${JBROWSE_REPO}/.env"
    set +a
    set -u
    if "${JBROWSE_PY}" "${JBROWSE_REPO}/scripts/rebuild_genome_registry.py" >> "${data_path}/genome_registry_rebuild.log" 2>&1; then
        echo "[CHECK] genome_registry 已重建（${JBROWSE_DATASET} 等已记录）"
    else
        echo "[WARNING] genome_registry 重建失败（不影响主流程，可手动执行）"
    fi
else
    echo "[WARNING] 跳过 genome_registry 重建：找不到脚本或 python"
fi

############################################################
# 最终检查
############################################################

CURRENT_STEP="最终输出检查"

echo "============================================================"
echo "[FINAL CHECK] 检查主要输出文件"
echo "============================================================"

check_file \
"${data_path}/${PLOIDY}_${MYTAG}.genome" \
"标准化 genome"

check_file \
"${data_path}/${MYTAG}.gff3" \
"原始 GFF3"

check_file \
"${data_path}/${PLOIDY}_${MYTAG}_annotation.emapper.annotations" \
"EggNOG annotation"

check_file \
"${data_path}/${PLOIDY}_${MYTAG}_with_annotation.bed" \
"EggNOG/Pfam BED"

check_file \
"${data_path}/${PLOIDY}_${MYTAG}.add_eggnog_ChineseSpring02G.gff3" \
"ChineseSpring02G GFF3"

check_file \
"${data_path}/${PLOIDY}_${MYTAG}.add_Description.cds" \
"ChineseSpring02G CDS"

check_file \
"${data_path}/${PLOIDY}_${MYTAG}.add_Description.pep" \
"ChineseSpring02G PEP"

check_file \
"${data_path}/${PLOIDY}_${MYTAG}_with_annotation_ChineseSpring02G.bed" \
"ChineseSpring02G BED"

check_file \
"/var/www/html/jbrowse-1.12.3-release/${PLOIDY}_${MYTAG}/trackList.json" \
"JBrowse trackList"

echo
echo "============================================================"
echo "[SUCCESS] ${MYTAG} 全部完成"
echo "[INFO] 完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

