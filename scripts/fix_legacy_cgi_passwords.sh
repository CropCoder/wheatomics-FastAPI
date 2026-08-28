#!/usr/bin/env bash
# Rewrite live legacy CGI scripts so they read the DB password from
# wheat_dbpass.py instead of a hardcoded leaked literal.
#
# Usage:
#   bash scripts/fix_legacy_cgi_passwords.sh [CGI_DIR] [--yes]
#   default CGI_DIR=/var/www/html/cgi-bin, default mode=dry run
#
set -euo pipefail

DIR="${1:-/var/www/html/cgi-bin}"
YES=0
for a in "$@"; do [[ "$a" == "--yes" ]] && YES=1; done

[[ -d "$DIR" ]] || { echo "[ERR] not a directory: $DIR" >&2; exit 2; }
HELPER="cgi-py-RawScript/wheat_dbpass.py"

# 1) helper module
if [[ $YES -eq 1 ]]; then
    mkdir -p "$DIR"
    cp -p "$HELPER" "$DIR/wheat_dbpass.py"
    echo "helper installed: $DIR/wheat_dbpass.py"
else
    echo "plan: install $DIR/wheat_dbpass.py (from $HELPER)"
fi

# 2) replace literals
LIT_OLD1="wheatomics115599"
LIT_OLD2="<REDACTED>"
REPL="passwd=__import__('wheat_dbpass').DB_PASSWORD"
pattern=$(printf '%s' "s/passwd='wheatomics115599'/passwd=__import__('wheat_dbpass').DB_PASSWORD/g; s/password='wheatomics115599'/passwd=__import__('wheat_dbpass').DB_PASSWORD/g; s/passwd='<REDACTED>'/passwd=__import__('wheat_dbpass').DB_PASSWORD/g")

changed=0
for f in "$DIR"/*.py; do
    [[ -f "$f" ]] || continue
    if grep -qE "passwd='wheatomics115599'|password='wheatomics115599'|passwd='<REDACTED>'" "$f"; then
        echo "  fix: $(basename "$f")"
        changed=$((changed + 1))
        if [[ $YES -eq 1 ]]; then
            sed -i "$pattern" "$f"
            # ensure passwd-ish reads module even in password= form
            sed -i "s/password=__import__/passwd=__import__/g" "$f"
        fi
    fi
done

if [[ $YES -eq 0 ]]; then
    echo "dry run: $changed file(s) affected; re-run with --yes to apply"
else
    echo "done: $changed file(s) rewritten"
    rem=$(grep -rlE "passwd=.wheatomics115599...|password=.wheatomics115599...|passwd=.REDACTED." "$DIR"/*.py 2>/dev/null | wc -l || true)
    echo "remaining leaks: $rem"
fi
