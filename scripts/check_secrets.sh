#!/usr/bin/env bash
# Fail when known leaked secrets reappear in tracked files.
# Introduced after the 2026-08 password purge (see MAINTENANCE.md).
# Wire into pre-commit / CI:  bash scripts/check_secrets.sh
set -euo pipefail

P1="wheatomics"; P2="115599"          # legacy MySQL password (rotated)
P3="Zjw_Super_Secret"; P4="_Token_2026" # legacy webhook secret (rotate too)

fail=0
for pat in "${P1}${P2}" "${P3}${P4}"; do
    if git grep -qIn "$pat" -- . 2>/dev/null; then
        echo "[secrets] LEAK FOUND for pattern: <redacted>" >&2
        git grep -nI "$pat" -- . || true
        fail=1
    fi
done

if [ "$fail" -eq 0 ]; then
    echo "[secrets] clean: no hardcoded secrets in tracked files"
fi
exit "$fail"
