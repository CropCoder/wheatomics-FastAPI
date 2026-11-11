#!/usr/bin/env bash
# ============================================================================
# fetch_aegilops4_data.sh — 下载 4 个二倍体 Aegilops（M/C/U/N）的组装与注释数据
#
# 数据源：
#   · 组装 FASTA / assembly_report / md5checksums：NCBI GenBank（4DWheat）
#   · 基因注释（HC+LC GFF3 + 蛋白 FASTA）与 EDTA TE：Zenodo 22681907
#
# 目标目录（每个基因组一个，与平台数据集名一致）：
#   ${DATA_ROOT}/MM_Aegilops_comosa_IPK_AE783/
#   ${DATA_ROOT}/CC_Aegilops_markgrafii_EKC105_RL5723/
#   ${DATA_ROOT}/UU_Aegilops_umbellulata_IPK_AE740/
#   ${DATA_ROOT}/NN_Aegilops_uniaristata_IPK_AE680/
#
# 预计磁盘：~5.3 GB（FASTA gz ~4.7 GB + 注释 ~0.6 GB；含 TE）
# 特性：断点续传（curl -C -）、md5 校验、幂等（已下载且 md5 通过则跳过）、
#       每个物种写 provenance.txt、最后 gzip -t 完整性检查。
#
# 用法：
#   bash fetch_aegilops4_data.sh [--data-root DIR] [--with-te] [--only MM|CC|UU|NN]
#   bash fetch_aegilops4_data.sh --check-only        # 只校验已有文件
# ============================================================================
set -uo pipefail

DATA_ROOT="${WHEATOMICS_DATA_ROOT:-/var/www/data/masw_data}"
WITH_TE=0
ONLY=""
CHECK_ONLY=0
ZENODO_API="https://zenodo.org/api/records/22681907"
ZENODO_DOI="10.5281/zenodo.22681907"
PAPER_DOI="10.1186/s12870-026-10046-2"
STAMP="$(date +%Y%m%d_%H%M%S)"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --data-root) DATA_ROOT="${2:?}"; shift 2 ;;
    --with-te)   WITH_TE=1; shift ;;
    --only)      ONLY="${2:?}"; shift 2 ;;
    --check-only) CHECK_ONLY=1; shift ;;
    -h|--help) sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done
mkdir -p "${DATA_ROOT}/_prep" 2>/dev/null || true
LOG="${WHEATOMICS_FETCH_LOG:-${DATA_ROOT}/_prep/fetch_aegilops4_${STAMP}_$$.log}"
if [ -n "${WHEATOMICS_FETCH_VERBOSE:-}" ]; then
  exec > >(tee -a "$LOG") 2>&1
else
  exec >> "$LOG" 2>&1
fi

log()  { echo "[$(date '+%F %T')] $*"; }
die()  { echo "[$(date '+%F %T')] [FATAL] $*" >&2; exit 2; }
warn() { echo "[$(date '+%F %T')] [WARN] $*" >&2; }

# ---------------- 物种配置 ----------------
# 字段：PLOIDY|MYTAG|GCA|NCBI_FTP_DIR(genomes/all 之后的相对路径)|FASTA_MD5|ZENODO_PREFIX|NSEQ
SPECIES=(
  "MM|Aegilops_comosa_IPK_AE783|GCA_052815735.2|GCA/052/815/735/GCA_052815735.2_ASM5281573v2|38b8436f9c4eb360a066a1c79f1a122a|Ae.comosa|17"
  "CC|Aegilops_markgrafii_EKC105_RL5723|GCA_052815875.1|GCA/052/815/875/GCA_052815875.1_ASM5281587v1|2a55e0ca2d74109c63c84dcb6d6a077a|Ae.markgrafii|24"
  "UU|Aegilops_umbellulata_IPK_AE740|GCA_060308565.1|GCA/060/308/565/GCA_060308565.1_AAFC_Aeum_AE740_v02|1766c56e9ed9f2d6bcf292925a6628bb|Ae.umbellulata|250"
  "NN|Aegilops_uniaristata_IPK_AE680|GCA_052815765.1|GCA/052/815/765/GCA_052815765.1_ASM5281576v1|b9b855678d7beba1cdd58f7ed89123eb|Ae.uniaristata|21"
)

NCBI_BASE="https://ftp.ncbi.nlm.nih.gov/genomes/all"
mkdir -p "$DATA_ROOT/_prep"
ZENODO_JSON="${DATA_ROOT}/_prep/zenodo_22681907.json"
ZENODO_JSON_TMP="${ZENODO_JSON}.tmp.$$"
if [ "$CHECK_ONLY" -eq 1 ] && [ ! -s "$ZENODO_JSON" ]; then
  log "== check-only：补取 Zenodo 元数据（校验 md5 需要）=="
fi
if [ ! -s "$ZENODO_JSON" ] || [ "$CHECK_ONLY" -eq 0 ]; then
  log "== Zenodo 记录元数据 =="
  for i in 1 2 3 4 5; do
    if curl -sSL --max-time 60 "$ZENODO_API" -o "$ZENODO_JSON_TMP" && python3 -c "import json;json.load(open('$ZENODO_JSON_TMP'))" 2>/dev/null; then mv -f "$ZENODO_JSON_TMP" "$ZENODO_JSON"; break; fi
    warn "Zenodo API 获取失败（第 $i 次），5s 后重试"; sleep 5
  done
  [ -s "$ZENODO_JSON" ] || die "无法获取 Zenodo 元数据：$ZENODO_API"
  python3 -c "import json;d=json.load(open('$ZENODO_JSON'));print('zenodo files:',len(d['files']))" || die "Zenodo JSON 解析失败"
fi

fetch_ncbi() { # $1=url $2=dest
  local url="$1" dest="$2"
  local try
  for try in 1 2 3 4; do
    log "  curl -C - (try $try): $(basename "$dest")"
    if curl -sSL --fail --connect-timeout 30 --max-time 7200 \
         --retry 3 --retry-delay 5 -C - "$url" -o "$dest"; then
      return 0
    fi
    sleep $((try * 5))
  done
  return 1
}

verify_md5() { # $1=file $2=expected
  local f="$1" exp="$2" got
  [ -s "$f" ] || return 1
  got="$(md5sum "$f" | cut -d' ' -f1)"
  if [ "$got" = "$exp" ]; then
    log "  [MD5 OK] $(basename "$f")  ($exp)"
    return 0
  fi
  warn "  [MD5 MISMATCH] $(basename "$f"): got=$got expected=$exp"
  return 1
}

zenodo_expected_md5() { # $1=file key (basename) -> echo md5 or empty
  python3 - "$ZENODO_JSON" "$1" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for f in d.get("files", []):
    if f["key"] == sys.argv[2]:
        ck = f.get("checksum", "")
        print(ck.split(":", 1)[1] if ":" in ck else "")
        break
PY
}

fetch_zenodo() { # $1=key $2=dest
  local key="$1" dest="$2" url try
  url="${ZENODO_API}/files/${key}/content"
  for try in 1 2 3 4; do
    if curl -sSL --fail --connect-timeout 30 --max-time 3600 \
         --retry 3 --retry-delay 5 -C - "$url" -o "$dest"; then
      return 0
    fi
    warn "  Zenodo 下载失败 $(basename "$dest")（第 $try 次），10s 后重试"; sleep 10
  done
  return 1
}

SUMMARY=()
FAILED=0
trap 'rm -rf "${LOCKDIR:-}"' EXIT

for row in "${SPECIES[@]}"; do
  IFS='|' read -r PLOIDY MYTAG GCA FTPDIR FMD5 ZPREFIX NSEQ <<< "$row"
  [ -n "$ONLY" ] && [ "$ONLY" != "$PLOIDY" ] && continue
  DS="${PLOIDY}_${MYTAG}"
  DIR="${DATA_ROOT}/${DS}"
  mkdir -p "$DIR" || die "无法创建目录 $DIR"
  # 数据集级互斥锁：同一 DS 只允许一个下载进程（防止并发写坏文件）
  LOCKDIR="${DATA_ROOT}/_prep/.lock_${DS}"
  if ! mkdir "$LOCKDIR" 2>/dev/null; then
    if [ -f "$LOCKDIR/pid" ] && kill -0 "$(cat "$LOCKDIR/pid")" 2>/dev/null; then
      die "另一个 ${DS} 下载进程正在运行（pid $(cat "$LOCKDIR/pid")），拒绝并发下载"
    fi
    warn "清理陈旧锁 ${LOCKDIR}（进程已不存在）"
    rm -rf "$LOCKDIR"; mkdir "$LOCKDIR" || die "无法创建锁 $LOCKDIR"
  fi
  echo $$ > "$LOCKDIR/pid"
  log ""
  log "================ $DS ($GCA) ================"
  log "目录: $DIR"

  NCBI_BASENAME="$(basename "$FTPDIR")"
  FASTA_GZ="${NCBI_BASENAME}_genomic.fna.gz"
  REPORT_TXT="${NCBI_BASENAME}_assembly_report.txt"
  MD5_TXT="md5checksums.txt"

  if [ "$CHECK_ONLY" -eq 0 ]; then
    # ---- NCBI ----
    if [ ! -s "${DIR}/md5checksums.txt" ]; then
      fetch_ncbi "${NCBI_BASE}/${FTPDIR}/md5checksums.txt" "${DIR}/md5checksums.txt" || { warn "md5checksums.txt 下载失败"; FAILED=$((FAILED+1)); }
    fi
    if [ ! -s "${DIR}/${REPORT_TXT}" ]; then
      fetch_ncbi "${NCBI_BASE}/${FTPDIR}/${REPORT_TXT}" "${DIR}/${REPORT_TXT}" || { warn "${REPORT_TXT} 下载失败"; FAILED=$((FAILED+1)); }
    fi
    if [ -s "${DIR}/${FASTA_GZ}" ] && verify_md5 "${DIR}/${FASTA_GZ}" "$FMD5" >/dev/null 2>&1; then
      log "  [SKIP] ${FASTA_GZ} 已存在且 md5 通过"
    else
      fetch_ncbi "${NCBI_BASE}/${FTPDIR}/${FASTA_GZ}" "${DIR}/${FASTA_GZ}" || { warn "${FASTA_GZ} 下载失败"; FAILED=$((FAILED+1)); }
    fi
    # ---- Zenodo 注释 ----
    for key in "${ZPREFIX}_genes_HC_LC.gff3.gz" "${ZPREFIX}_genes_HC_LC.fasta.gz"; do
      exp="$(zenodo_expected_md5 "$key")"
      if [ -s "${DIR}/${key}" ] && [ -n "$exp" ] && verify_md5 "${DIR}/${key}" "$exp" >/dev/null 2>&1; then
        log "  [SKIP] ${key} 已存在且 md5 通过"
      else
        fetch_zenodo "$key" "${DIR}/${key}" || { warn "${key} 下载失败"; FAILED=$((FAILED+1)); }
      fi
    done
    if [ "$WITH_TE" -eq 1 ]; then
      key="${ZPREFIX}.EDTA.TEanno.gff3.gz"
      exp="$(zenodo_expected_md5 "$key")"
      if [ -s "${DIR}/${key}" ] && [ -n "$exp" ] && verify_md5 "${DIR}/${key}" "$exp" >/dev/null 2>&1; then
        log "  [SKIP] ${key} 已存在且 md5 通过"
      else
        fetch_zenodo "$key" "${DIR}/${key}" || { warn "${key} 下载失败"; FAILED=$((FAILED+1)); }
      fi
    fi
  fi

  # ---- 校验 ----
  log "  -- 校验 --"
  OK=1
  verify_md5 "${DIR}/${FASTA_GZ}" "$FMD5" || OK=0
  for key in "${ZPREFIX}_genes_HC_LC.gff3.gz" "${ZPREFIX}_genes_HC_LC.fasta.gz"; do
    exp="$(zenodo_expected_md5 "$key")"
    if [ -n "$exp" ]; then verify_md5 "${DIR}/${key}" "$exp" || OK=0; else warn "  ${key} 无 Zenodo md5 记录"; OK=0; fi
  done
  if [ "$WITH_TE" -eq 1 ]; then
    key="${ZPREFIX}.EDTA.TEanno.gff3.gz"; exp="$(zenodo_expected_md5 "$key")"
    [ -n "$exp" ] && { verify_md5 "${DIR}/${key}" "$exp" || OK=0; }
  fi
  for gz in "${DIR}/"*.gff3.gz "${DIR}/${FASTA_GZ}"; do
    [ -s "$gz" ] || { warn "  缺失: $gz"; OK=0; continue; }
    gzip -t "$gz" 2>/dev/null || { warn "  gzip 损坏: $gz"; OK=0; }
  done
  [ -s "${DIR}/${REPORT_TXT}" ] || { warn "  缺失 ${REPORT_TXT}"; OK=0; }

  # ---- provenance ----
  {
    echo "# ${DS} 数据来源与校验（由 scripts/fetch_aegilops4_data.sh 生成）"
    echo "fetch_date: $(date '+%F %T %Z')"
    echo "dataset: ${DS}"
    echo "ploidy: ${PLOIDY}"
    echo "ncbi_assembly: ${GCA}"
    echo "ncbi_ftp_dir: ${NCBI_BASE}/${FTPDIR}/"
    echo "ncbi_fasta_gz_md5: ${FMD5}"
    echo "zenodo_record: https://zenodo.org/records/22681907"
    echo "zenodo_doi: ${ZENODO_DOI}"
    echo "paper_doi: ${PAPER_DOI}"
    echo "files:"
    ls -l "${DIR}" 2>/dev/null | awk 'NR>1 && $NF !~ /^\.$/ {print "  " $NF "  " $5 " bytes"}'
  } > "${DIR}/provenance.txt"

  if [ "$OK" -eq 1 ]; then
    SUMMARY+=("OK   ${DS}")
  else
    SUMMARY+=("FAIL ${DS}")
    FAILED=$((FAILED+1))
  fi
  log "  [$([ "$OK" -eq 1 ] && echo OK || echo FAIL)] ${DS}"
  du -sh "$DIR" 2>/dev/null | sed 's/^/  目录大小: /'
  rm -rf "$LOCKDIR"; LOCKDIR=""
done

log ""
log "================ 汇总 ================"
for s in "${SUMMARY[@]}"; do log "  $s"; done
log "日志: $LOG"
if [ "$FAILED" -gt 0 ]; then
  log "[WARNING] 有 ${FAILED} 项失败/待重试；重跑本脚本会断点续传"
  exit 1
fi
log "[SUCCESS] 4 个基因组数据下载 + md5 校验完成"
