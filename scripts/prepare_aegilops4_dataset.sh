#!/usr/bin/env bash
# ============================================================================
# prepare_aegilops4_dataset.sh — A2 归一化（服务器侧，单基因组，幂等）
#
# 把下载好的「NCBI 组装 + Zenodo 注释」整理成平台四件套：
#   ${MYTAG}.fa / ${MYTAG}.gff3 / ${MYTAG}.cds / ${MYTAG}.pep
#
# 步骤：
#   1) FASTA：GenBank 登录号 → Chr1M../ChrUn_*（normalize_diploid.py fasta）
#   2) GFF3 seqid 归一化，保留作者 ID（normalize_diploid.py gff3 --keep-author-ids）
#   3) gene/mRNA ID 按平台规则重编号（renumber_gff_ids.py；每染色体 100 步）
#   4) gffread 生成 CDS/PEP
#   5) PEP 终止符清理（. / * → 尾部删除、内部替换 X；normalize_diploid.py pep --stop-mode trim）
#   6) 平台质检 check_genome_files.py（rc=0 才算过）
#
# 用法：prepare_aegilops4_dataset.sh <PLOIDY> <MYTAG> <ZENODO_PREFIX> [--force]
#   例：prepare_aegilops4_dataset.sh MM Aegilops_comosa_IPK_AE783 Ae.comosa
#   （脚本会按 PLOIDY 自动取 ID 前缀与预期计数；--force 强制重跑已完成步骤）
# ============================================================================
set -uo pipefail

DATA_ROOT="${WHEATOMICS_DATA_ROOT:-/var/www/data/masw_data}"
PREP="${DATA_ROOT}/_prep"
PY="${WHEATOMICS_PY:-/usr/bin/python3}"
GFFREAD="${WHEATOMICS_GFFREAD:-/home/fei/mambaforge/envs/new_env/bin/gffread}"
CHECK="${WHEATOMICS_CHECK:-/var/www/html/Script/check_genome_files.py}"

PLOIDY="${1:?用法: prepare_aegilops4_dataset.sh <PLOIDY> <MYTAG> <ZENODO_PREFIX> [--force]}"
MYTAG="${2:?缺少 MYTAG}"
ZPREFIX="${3:?缺少 ZENODO_PREFIX（如 Ae.comosa）}"
FORCE=0
[ "${4:-}" = "--force" ] && FORCE=1
DS="${PLOIDY}_${MYTAG}"
DIR="${DATA_ROOT}/${DS}"

case "$PLOIDY" in
  MM) IDPFX="AeCom.AE783.r1."; NSEQ=17;  NGENE=51203; NUNPLACED=38 ;;
  CC) IDPFX="AeMar.EKC105.r1."; NSEQ=24; NGENE=47246; NUNPLACED=53 ;;
  UU) IDPFX="AeUmb.AE740.r1.";  NSEQ=250; NGENE=49677; NUNPLACED=1103 ;;
  NN) IDPFX="AeUna.AE680.r1.";  NSEQ=21;  NGENE=50416; NUNPLACED=66 ;;
  *) echo "[ERROR] 未配置的 PLOIDY: $PLOIDY（本脚本只服务 4 个二倍体 Aegilops）" >&2; exit 2 ;;
esac

LOG="${WHEATOMICS_PREP_LOG:-${DIR}/prepare_${MYTAG}.log}"
mkdir -p "$DIR" || exit 2
exec >> "$LOG" 2>&1
log()  { echo "[$(date '+%F %T')] $*"; }
die()  { echo "[$(date '+%T')] [FATAL] $*" >&2; exit 2; }
ok()   { echo "[$(date '+%T')] [OK] $*"; }
need() { [ -s "$1" ] || die "缺少文件/为空: $1"; }

log "======== prepare ${DS}（PLOIDY=${PLOIDY}, ZPREFIX=${ZPREFIX}, IDPFX=${IDPFX}）========"
cd "$DIR" || die "无法进入 $DIR"

# ---------------- 0) 定位原始文件 ----------------
FASTA_GZ=$(ls GCA_*_genomic.fna.gz 2>/dev/null | head -1)
REPORT=$(ls GCA_*_assembly_report.txt 2>/dev/null | head -1)
GFF_GZ=$(ls "${ZPREFIX}"_genes_HC_LC.gff3.gz 2>/dev/null | head -1)
need "$FASTA_GZ"; need "$REPORT"; need "$GFF_GZ"
ok "输入: $FASTA_GZ / $REPORT / $GFF_GZ"

FA="${MYTAG}.fa"; GFF_RAW="${MYTAG}.rawseqids.gff3"; GFF="${MYTAG}.gff3"
CDS="${MYTAG}.cds"; PEP="${MYTAG}.pep"
IDMAP="${MYTAG}.idmap.tsv"

# ---------------- 1) FASTA 归一化 ----------------
if [ -s "$FA" ] && [ "$FORCE" -eq 0 ] && [ "$(grep -c '^>' "$FA")" = "$NSEQ" ]; then
  ok "[1/6] FASTA 已存在且序列数=$NSEQ，跳过"
else
  log "[1/6] FASTA 头映射（GenBank 登录号 → Chr*/ChrUn_*）"
  "$PY" "$PREP/normalize_diploid.py" fasta \
    --fasta "$FASTA_GZ" --assembly-report "$REPORT" \
    --out "$FA" --mapping "${MYTAG}.fa.mapping.tsv" || die "FASTA 归一化失败"
  [ "$(grep -c '^>' "$FA")" = "$NSEQ" ] || die "FASTA 序列数 $(grep -c '^>' "$FA") != $NSEQ"
  ! grep -qE '^>(CM|JB)' "$FA" || die "FASTA 仍有 NCBI 登录号头未映射"
  ok "[1/6] FASTA 完成：$NSEQ 条"
fi

# ---------------- 2) GFF3 seqid 归一化（保留作者 ID） ----------------
if [ -s "$GFF_RAW" ] && [ "$FORCE" -eq 0 ]; then
  ok "[2/6] rawseqids GFF 已存在，跳过"
else
  log "[2/6] GFF3 seqid 归一化（保留作者 ID）"
  "$PY" "$PREP/normalize_diploid.py" gff3 \
    --gff3 "$GFF_GZ" --assembly-report "$REPORT" --keep-author-ids \
    --out "$GFF_RAW" --mapping "${MYTAG}.seqid_mapping.tsv" || die "GFF3 seqid 归一化失败"
  ok "[2/6] seqid 归一化完成：$(grep -c $'\tmRNA\t' "$GFF_RAW") mRNA"
fi

# ---------------- 3) 平台风格重编号 ----------------
if [ -s "$GFF" ] && [ "$FORCE" -eq 0 ] && [ "$(grep -c $'\tmRNA\t' "$GFF")" = "$NGENE" ]; then
  ok "[3/6] 重编号 GFF 已存在且 mRNA=$NGENE，跳过"
else
  log "[3/6] gene/mRNA 重编号（每染色体 100 步；前缀 ${IDPFX}）"
  "$PY" "$PREP/renumber_gff_ids.py" \
    --gff3 "$GFF_RAW" --out "$GFF" --id-prefix "$IDPFX" --id-map "$IDMAP" || die "重编号失败"
  [ "$(grep -c $'\tmRNA\t' "$GFF")" = "$NGENE" ] || die "重编号后 mRNA 数不符"
  ok "[3/6] 重编号完成：mRNA=$NGENE，idmap=$(wc -l < "$IDMAP") 行"
fi

# ---------------- 4) gffread 生成 CDS/PEP ----------------
if [ -s "$CDS" ] && [ -s "$PEP" ] && [ "$FORCE" -eq 0 ] \
   && [ "$(grep -c '^>' "$PEP")" = "$NGENE" ]; then
  ok "[4/6] CDS/PEP 已存在且 PEP=$NGENE，跳过"
else
  log "[4/6] gffread 生成 CDS/PEP"
  "$GFFREAD" -E -g "$FA" -x "$CDS" -y "$PEP" "$GFF" 2> "${MYTAG}.gffread.log" \
    || die "gffread 失败（见 ${MYTAG}.gffread.log）"
  [ "$(grep -c '^>' "$PEP")" = "$NGENE" ] || die "gffread PEP 数 $(grep -c '^>' "$PEP") != $NGENE"
  ok "[4/6] CDS/PEP 完成：PEP=$NGENE"
fi

# ---------------- 5) PEP 终止符清理 ----------------
if grep -q '[.*]' "$PEP" 2>/dev/null; then
  log "[5/6] PEP 清洗（. / * → 尾部删除、内部 X）"
  "$PY" "$PREP/normalize_diploid.py" pep --pep "$PEP" --out "${PEP}.clean" --stop-mode trim \
    || die "PEP 清洗失败"
  mv -f "${PEP}.clean" "$PEP"
  ok "[5/6] PEP 清洗完成"
else
  ok "[5/6] PEP 无 . / *，跳过清洗"
fi

# ---------------- 6) 平台质检 ----------------
log "[6/6] 平台质检 check_genome_files.py"
"$PY" "$CHECK" "$MYTAG" > "${MYTAG}.check_genome_files.log" 2>&1
RC=$?
tail -3 "${MYTAG}.check_genome_files.log" | sed 's/^/    /'
[ "$RC" -eq 0 ] || die "check_genome_files.py rc=$RC（见 ${MYTAG}.check_genome_files.log）"
ok "[6/6] 质检通过（rc=0）"

# ---------------- 汇总 ----------------
log "-------- 产物 --------"
ls -la "$FA" "$GFF" "$CDS" "$PEP" "$IDMAP" 2>/dev/null | awk '{printf "  %-52s %14d\n", $9, $5}'
log "  seqids: $(grep -c '^>' "$FA") ; mRNA: $(grep -c $'\tmRNA\t' "$GFF") ; ChrUn 基因: $(awk -F'\t' '$1 ~ /^ChrUn_/ && $3=="gene"' "$GFF" | wc -l)"
log "[SUCCESS] ${DS} A2 归一化完成"
