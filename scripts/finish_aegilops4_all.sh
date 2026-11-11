#!/bin/bash
# G4：顺序跑 4 个二倍体 Aegilops 的 finish_genome_integration.sh（v2）
set -uo pipefail
export PATH=/var/www/html/blast/blast+/bin:/home/fei/mambaforge/bin:/usr/bin:/bin
export HOME=/home/fei
ROOT=/var/www/data/masw_data
PREP=$ROOT/_prep
DOI=10.1186/s12870-026-10046-2
SUMMARY=$PREP/finish_aegilops4_summary.log
: > "$SUMMARY"
SPECS=("MM:Aegilops_comosa_IPK_AE783" "NN:Aegilops_uniaristata_IPK_AE680" "CC:Aegilops_markgrafii_EKC105_RL5723" "UU:Aegilops_umbellulata_IPK_AE740")
for spec in "${SPECS[@]}"; do
  PLOIDY=${spec%%:*}; MYTAG=${spec##*:}; DIR=$ROOT/${PLOIDY}_${MYTAG}
  echo "=== $(date "+%F %T") FINISH ${PLOIDY}/${MYTAG} ===" | tee -a "$SUMMARY"
  bash "$PREP/finish_genome_integration.sh" "$PLOIDY" "$MYTAG" "$DOI" > "$DIR/finish_${MYTAG}.log" 2>&1
  RC=$?
  NF=$(grep -c "\[FAIL\]" "$DIR/finish_${MYTAG}.log" 2>/dev/null || echo 0)
  NO=$(grep -c "\[OK\]" "$DIR/finish_${MYTAG}.log" 2>/dev/null || echo 0)
  echo "=== $(date "+%F %T") END ${MYTAG} rc=$RC OK=$NO FAIL=$NF ===" | tee -a "$SUMMARY"
  if [ "$RC" -ne 0 ]; then
    echo "STOP: finish ${MYTAG} rc=$RC（详见 $DIR/finish_${MYTAG}.log）" | tee -a "$SUMMARY"; exit 1
  fi
done
echo "ALL FINISH SUCCESS $(date "+%F %T")" >> "$SUMMARY"
