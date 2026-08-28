#!/usr/bin/env bash
# Fail when known leaked secrets appear in tracked files.
# Introduced after the 2026-08 password purge (see MAINTENANCE.md).
# Wire into pre-commit / CI:  bash scripts/check_secrets.sh
set -euo pipefail

P1="wheatomics"; P2="115599"          # legacy MySQL password (rotated)
P3="Zjw_Super_Secret"; P4="_Token_2026" # legacy webhook secret (rotate too)

# The legacy-CGI converters below legitimately contain the old literal as a
# DETECTION PATTERN (they rewrite live CGI files on the server). Exclude them.
EXCLUDES=( ":!scripts/fix_legacy_cgi_passwords.py" ":!scripts/fix_legacy_cgi_passwords.sh" )

fail=0
for pat in "${P1}${P2}" "${P3}${P4}"; do
    if git grep -qIn "$pat" -- . "${EXCLUDES[@]}" 2>/dev/null; then
        echo "[secrets] LEAK FOUND for pattern: <redacted>" >&2
        git grep -nI "$pat" -- . "${EXCLUDES[@]}" || true
        fail=1
    fi
done

if [ "$fail" -eq 0 ]; then
    echo "[secrets] clean: no hardcoded secrets in tracked files"
fi
exit "$fail"
