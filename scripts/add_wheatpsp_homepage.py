"""Server-side script: add wheatPSP to WheatOmics homepage menu + tool card.

Run on the server (Apache docroot /var/www/html):
    sudo python3 scripts/add_wheatpsp_homepage.py

Idempotent: safe to run twice.
"""
import os

NL = chr(10)


def add_to_header_nav(path: str) -> bool:
    """Add wheatPSP into the Tools/Browse dropdown right after scRNA."""
    if not os.path.exists(path):
        print(f"[skip] {path} not found")
        return False
    t = open(path, encoding="utf-8").read()
    if "wheatPSP" in t:
        print(f"[ok] {path} already has wheatPSP")
        return False
    anchor = '<li><a href="/scRNA">scRNA</a></li>'
    if anchor not in t:
        print(f"[ERR] anchor not found in {path}")
        return False
    t = t.replace(anchor, anchor + NL + '\t <li><a href="/wheatPSP">wheatPSP</a></li>', 1)
    open(path, "w", encoding="utf-8").write(t)
    print(f"[done] header nav updated: {path}")
    return True


def add_card(path: str) -> bool:
    """Add a wheatPSP card after the WheatPPI card (inside the same card-group)."""
    if not os.path.exists(path):
        print(f"[skip] {path} not found")
        return False
    t = open(path, encoding="utf-8").read()
    if "wheatPSP" in t:
        print(f"[ok] {path} already has wheatPSP")
        return False
    card = (
        '      <div class="card">' + NL
        + '        <div class="card-body">' + NL
        + '          <h5 class="card-title"><a class="card-title" href="/wheatPSP/">wheatPSP</a></h5>' + NL
        + '          <p class="card-text">Phase Separation-associated Proteins</p>' + NL
        + '        </div>' + NL
        + '      </div>' + NL
    )
    # anchor = WheatPPI card body + card close + card-group close
    anchor = ('Protein Interactions Search</p>' + NL + '        </div>' + NL
              + '      </div>' + NL + '    </div>')
    if anchor not in t:
        print(f"[ERR] card anchor not found in {path}")
        return False
    cut = anchor.rindex('    </div>')          # keep card-body close + card close
    head = anchor[:cut]
    t = t.replace(anchor, head + NL + card + '    </div>', 1)
    open(path, "w", encoding="utf-8").write(t)
    print(f"[done] tool card added: {path}")
    return True


if __name__ == "__main__":
    docroot = os.environ.get("WHEATOMICS_DOCROOT", "/var/www/html")
    add_to_header_nav(os.path.join(docroot, "header.html"))
    add_card(os.path.join(docroot, "index.html"))
    print("done")
