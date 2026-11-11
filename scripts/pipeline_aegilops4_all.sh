#!/bin/bash
# G3：顺序跑 4 个二倍体 Aegilops 的 add_wheat_genome.sh（服务端运行）
# 用法：pipeline_aegilops4_all.sh [数据根目录，默认 /var/www/data/masw_data]
set -uo pipefail
ROOT="${1:-${WHEATOMICS_DATA_ROOT:-/var/www/data/masw_data}}"
export PATH=/var/www/html/blast/blast+/bin:/home/fei/mambaforge/bin:/usr/bin:/bin
export HOME=/home/fei
SUMMARY="$ROOT/_prep/pipeline_aegilops4_summary.log"
: > "$SUMMARY"
SPECS=("MM:Aegilops_comosa_IPK_AE783" "NN:Aegilops_uniaristata_IPK_AE680" "CC:Aegilops_markgrafii_EKC105_RL5723" "UU:Aegilops_umbellulata_IPK_AE740")
for spec in "${SPECS[@]}"; do
  PLOIDY=${spec%%:*}; MYTAG=${spec##*:}; DIR=$ROOT/${PLOIDY}_${MYTAG}
  echo "=== $(date "+%F %T") START ${PLOIDY}/${MYTAG} ===" | tee -a "$SUMMARY"
  ( cd "$DIR" || exit 2; bash "$ROOT/add_wheat_genome.sh" "$MYTAG" "$DIR" "$PLOIDY" > "pipeline_${MYTAG}.log" 2>&1 )
  RC=$?
  OK=$(grep -c "\[SUCCESS\]" "$DIR/pipeline_${MYTAG}.log" 2>/dev/null || echo 0)
  echo "=== $(date "+%F %T") END ${MYTAG} rc=$RC marker=$OK ===" | tee -a "$SUMMARY"
  if [ "$RC" -ne 0 ] || [ "$OK" -eq 0 ]; then
    echo "STOP: ${MYTAG} failed (rc=$RC marker=$OK)" | tee -a "$SUMMARY"; exit 1
  fi
done
echo "ALL SUCCESS $(date "+%F %T")" >> "$SUMMARY"
