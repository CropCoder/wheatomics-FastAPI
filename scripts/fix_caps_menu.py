"""Server-side script: rename the CAPS menu item on the WheatOmics homepage.

header.html (the menu bar loaded by the homepage index.html) still labels the
entry "CAPS/KASP(Beta)" linking to /snprimer; the new module is /caps with the
title "CAPS/dCAPS".

Run on the server (Apache docroot /var/www/html):
    sudo python3 scripts/fix_caps_menu.py

Idempotent: safe to run twice.
"""
import os

NL = chr(10)

OLD_LI = '<li><a href="/snprimer">CAPS/KASP(Beta)</a></li>'
NEW_LI = '<li><a href="/caps">CAPS/dCAPS</a></li>'
OLD_LABEL = 'CAPS/KASP(Beta)'
NEW_LABEL = 'CAPS/dCAPS'


def rename(path: str) -> bool:
    if not os.path.exists(path):
        print(f"[skip] {path} not found")
        return False
    t = open(path, encoding="utf-8").read()
    if NEW_LABEL not in t and OLD_LI not in t:
        print(f"[ok] {path} already uses CAPS/dCAPS")
        return False
    t2 = t.replace(OLD_LI, NEW_LI, 1)
    t2 = t2.replace(OLD_LABEL, NEW_LABEL)          # label-only fallback
    changed = t2 != t
    open(path, "w", encoding="utf-8").write(t2)
    print(f"[done] menu item renamed in {path}" if changed else f"[ok] {path} unchanged")
    return changed


def main() -> None:
    docroot = os.environ.get("WHEATOMICS_DOCROOT", "/var/www/html")
    for name in ("header.html", "index.html"):
        rename(os.path.join(docroot, name))
    print("done")


if __name__ == "__main__":
    main()
