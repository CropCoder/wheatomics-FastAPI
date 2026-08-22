"""Server-side script: add homepage tool cards for modules missing from the
WheatOmics homepage tool grid (those present in the header menu but not as cards).

Run on the server (Apache docroot /var/www/html):
    sudo python3 scripts/add_homepage_cards.py

Idempotent: safe to run twice. Verifies card-structure balance afterwards.
"""
import os

NL = chr(10)

# (title, href, description) — order follows the Tools/Browse menu
CARDS = [
    ("CAPS/KASP(Beta)", "/snprimer", "Marker Design for CAPS, dCAPS & KASP"),
    ("preBLAST", "/preblast", "Pre-computed BLAST Alignment"),
    ("SequenceToolkit", "/sms2", "Multi-purpose Sequence Processing"),
    ("Orthofinder", "/orthofinder", "Orthogroup Browser & Search"),
    ("VariantHub", "/VariantHub", "Wheat Variants & Population Genotypes"),
    ("scRNA", "/scRNA", "Single-cell RNA Expression"),
    ("eQTL Atlas", "/eqtl", "Expression Quantitative Trait Loci"),
    ("GO/KEGG Enrichment", "/GO_KEGG", "Gene Ontology & KEGG Pathways"),
    ("Collinearity", "/syntenyview", "Genome Synteny & Collinearity"),
    ("Triticeae papers", "/papers", "Triticeae Literature Collection"),
]


def card(title: str, href: str, desc: str) -> str:
    return (
        '      <div class="card">' + NL
        + '        <div class="card-body">' + NL
        + '          <h5 class="card-title"><a class="card-title" href="' + href + '">' + title + '</a></h5>' + NL
        + '          <p class="card-text">' + desc + '</p>' + NL
        + '        </div>' + NL
        + '      </div>' + NL
    )


def group(items) -> str:
    body = "".join(card(*c) for c in items)
    return '    <div class="card-group">' + NL + body + '    </div>' + NL


def build_groups(modules) -> str:
    """3 groups: 3 / 3 / rest (last group may hold 4)."""
    parts = []
    for i in range(0, len(modules), 3):
        parts.append(group(modules[i:i + 3]))
    return NL.join(parts) + NL + '    <br>' + NL


def main() -> None:
    docroot = os.environ.get("WHEATOMICS_DOCROOT", "/var/www/html")
    path = os.path.join(docroot, "index.html")
    if not os.path.exists(path):
        print(f"[skip] {path} not found")
        return
    t = open(path, encoding="utf-8").read()
    if "/GO_KEGG" in t and 'href="/GO_KEGG"' in t:
        print(f"[ok] {path} already has the new cards")
        return
    anchor = ('<p class="card-text"> Gene information for a genome interval</p>' + NL
              + '        </div>' + NL
              + '      </div>' + NL
              + '    </div>' + NL
              + '    ' + NL
              + '    <br>' + NL)
    if anchor not in t:
        print(f"[ERR] IntervalTool card anchor not found in {path} — file not modified")
        return
    groups = build_groups(CARDS)
    t2 = t.replace(anchor, anchor + groups, 1)
    # sanity: div balance must be unchanged
    delta = t2.count("<div") - t2.count("</div>") - (t.count("<div") - t.count("</div>"))
    if delta != 0:
        print(f"[ERR] div balance mismatch ({delta}) — file not modified")
        return
    open(path, "w", encoding="utf-8").write(t2)
    print(f"[done] {len(CARDS)} tool cards added: {path}")


if __name__ == "__main__":
    main()
