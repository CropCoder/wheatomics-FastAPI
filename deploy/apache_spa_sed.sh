#!/usr/bin/env bash
# 一次性 sed 插入：在两个 Apache conf 的 `ProxyPassReverse /preblast` 之后插入 8 个 SPA 的转发。
# 服务器上执行：sudo bash apache_spa_sed.sh
set -euo pipefail

APACHE_PATHS=(
    /etc/apache2/sites-enabled/000-default-ssl.conf
    /etc/apache2/sites-enabled/000-default.conf
)

SPA_PATHS=( /getfasta /HomologFinder /PfamSearch /orthofinder /preblast /wheatPPI /interval /expression )

for f in "${APACHE_PATHS[@]}"; do
    [ -f "$f" ] || { echo "SKIP $f (not found)"; continue; }
    sudo cp "$f" "${f}.bak.$(date +%Y%m%d%H%M%S)"
    for p in "${SPA_PATHS[@]}"; do
        # 跳过 preblast 自己（锚点行）
        [ "$p" = "/preblast" ] && continue
        # 检查是否已有该路径的 ProxyPass，跳过避免重复
        if sudo grep -qE "^[[:space:]]*ProxyPass[[:space:]]+${p}[[:space:]]" "$f"; then
            echo "HAVE $f → $p"
            continue
        fi
        # 在 ProxyPassReverse /preblast 行后面插入
        sudo sed -i "/ProxyPassReverse \\/preblast/a\\    ProxyPass ${p} http://127.0.0.1:8000${p}\\n    ProxyPassReverse ${p} http://127.0.0.1:8000${p}" "$f"
        echo "ADD  $f → $p"
    done
done

echo
echo "=== Config test ==="
sudo apachectl configtest
echo
echo "=== Restart ==="
sudo apachectl restart

echo
echo "=== Verify ==="
for p in "${SPA_PATHS[@]}"; do
    echo "curl -I https://wheatomics.sdau.edu.cn${p}/"
done