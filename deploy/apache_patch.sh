#!/usr/bin/env bash
# WheatOmics FastAPI — Apache ProxyPass force-replace patch
# Run on production server (fei@wheatomics) AFTER each SPA add or update.
#
# For every SPA path, REMOVES any existing ProxyPass / ProxyPassReverse
# (regardless of whether it pointed to old CGI or anything else),
# then APPENDS the FastAPI rule. Idempotent in outcome, not in execution.
set -euo pipefail

APACHE_PATHS=(
    /etc/apache2/sites-enabled/000-default-ssl.conf
    /etc/apache2/sites-enabled/000-default.conf
)

SPA_PATHS=( /getfasta /HomologFinder /PfamSearch /orthofinder /preblast /wheatPPI /interval /expression )

for f in "${APACHE_PATHS[@]}"; do
    [ -f "$f" ] || { echo "SKIP $f (not found)"; continue; }
    for p in "${SPA_PATHS[@]}"; do
        # Delete any existing ProxyPass or ProxyPassReverse line for this path.
        # Pattern: optional leading whitespace, "ProxyPass" or "ProxyPassReverse",
        # then whitespace + the path, then a trailing space-or-end-of-line anchor.
        sudo sed -i -E "\\#^[[:space:]]*ProxyPass(Reverse)?[[:space:]]+${p}([[:space:]]|$)#d" "$f"
        # Now append the FastAPI rule
        printf '    ProxyPass %s http://127.0.0.1:8000%s\n    ProxyPassReverse %s http://127.0.0.1:8000%s\n' \
            "$p" "$p" "$p" "$p" | sudo tee -a "$f" >/dev/null
        echo "OK   $f → $p"
    done
done

echo
echo "=== Validating Apache config ==="
sudo apachectl configtest

echo
echo "=== Restarting Apache ==="
sudo apachectl restart

echo
echo "=== Done. Verify with: ==="
for p in "${SPA_PATHS[@]}"; do
    echo "curl -I https://wheatomics.sdau.edu.cn${p}/"
done
