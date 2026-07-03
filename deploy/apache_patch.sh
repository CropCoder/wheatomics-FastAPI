# WheatOmics FastAPI - Apache ProxyPass patch
# Run on production server (fei@wheatomics) AFTER each SPA add.
#
# Replaces CGI-era proxy rules for /getfasta/ with FastAPI SPA mount.
# Idempotent: skips any path that already has a ProxyPass line.

set -euo pipefail

APACHE_PATHS=(
    /etc/apache2/sites-enabled/000-default-ssl.conf
    /etc/apache2/sites-enabled/000-default.conf
)

SPA_PATHS=( /getfasta /HomologFinder /PfamSearch /orthofinder /preblast /wheatPPI /interval /expression )

for f in "${APACHE_PATHS[@]}"; do
    [ -f "$f" ] || { echo "SKIP $f (not found)"; continue; }
    for p in "${SPA_PATHS[@]}"; do
        # Only add if no existing ProxyPass for this path
        if grep -qE "^[[:space:]]*ProxyPass[[:space:]]+${p}[[:space:]]" "$f"; then
            echo "HAVE $f → $p"
        else
            # Insert after the LAST existing ProxyPass line in the file
            printf '    ProxyPass %s http://127.0.0.1:8000%s\n    ProxyPassReverse %s http://127.0.0.1:8000%s\n' \
                "$p" "$p" "$p" "$p" \
                | sudo tee -a "$f" >/dev/null
            echo "ADD  $f → $p"
        fi
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
echo "curl -I https://wheatomics.sdau.edu.cn/getfasta/"
echo "curl -I https://wheatomics.sdau.edu.cn/HomologFinder/"
