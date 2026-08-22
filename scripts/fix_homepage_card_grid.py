"""Server-side script: normalize the WheatOmics homepage tool card grid.

Canonical order - one row of exactly 3 cards per card-group:
  GetSequence | BLAST | PfamSearch
  PrimerServer | IDConverter | HomologFinder
  GeneExpression | Co-expression | scRNA        <- scRNA moved right after Co-expression
  WheatPPI | wheatPSP | KnownGene
  SyntenySearch | IntervalTool | CAPS/KASP(Beta)
  preBLAST | SequenceToolkit | Orthofinder
  VariantHub | eQTL Atlas | GO/KEGG Enrichment
  Collinearity | Triticeae papers

The whole tool section (<!-- tool --> ... up to the "Data in JBrowse" ribbon)
is regenerated, so it works whether or not the earlier add_* scripts were run.

Run on the server (Apache docroot /var/www/html):
    sudo python3 scripts/fix_homepage_card_grid.py

Idempotent: safe to run twice.
"""
import os

NL = chr(10)

# (title, href, description) - canonical order
CARDS = [
    ("GetSequence", "/getfasta/index.html", "Querying by Gene ID or Genomic Interval"),
    ("BLAST", "/blast/blast.html", "Sequence Similarity Search"),
    ("PfamSearch", "/tools/proteinfamily.html", "Querying by Pfam ID"),
    ("PrimerServer", "/PrimerServer", "Primer Design"),
    ("IDConverter", "/idConvert/", "Gene ID Converter"),
    ("HomologFinder", "/homologtools/index.html", "Querying by Gene ID"),
    ("GeneExpression", "/expression/index.html", "Querying by Gene ID"),
    ("Co-expression", "/coexpression/index.html", "Co-expression Analysis"),
    ("scRNA", "/scRNA", "Single-cell RNA Expression"),
    ("WheatPPI", "/wheatPPI/index.html", "Protein Interactions Search"),
    ("wheatPSP", "/wheatPSP/", "Phase Separation-associated Proteins"),
    ("KnownGene", "/genes", "Wheat Known Genes Search"),
    ("SyntenySearch", "/symap/index.html", "Querying Gene Synteny"),
    ("IntervalTool", "/tools/intervalTools.html", "Gene information for a genome interval"),
    ("CAPS/dCAPS", "/caps", "CAPS/dCAPS Primer Design"),
    ("preBLAST", "/preblast", "Pre-computed BLAST Alignment"),
    ("SequenceToolkit", "/sms2", "Multi-purpose Sequence Processing"),
    ("Orthofinder", "/orthofinder", "Orthogroup Browser & Search"),
    ("VariantHub", "/VariantHub", "Wheat Variants & Population Genotypes"),
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


def build_grid() -> str:
    """Emit rows of three; the last row may hold the remaining cards (2)."""
    rows = []
    for i in range(0, len(CARDS), 3):
        rows.append(group(CARDS[i:i + 3]))
    return ('    <!-- tool -->' + NL + NL.join(rows) + '    <br>' + NL)


def main() -> None:
    docroot = os.environ.get("WHEATOMICS_DOCROOT", "/var/www/html")
    path = os.path.join(docroot, "index.html")
    if not os.path.exists(path):
        print(f"[skip] {path} not found")
        return
    t = open(path, encoding="utf-8").read()

    start_marker = '    <!-- tool -->'
    end_marker = 'Data in JBrowse:'
    if start_marker not in t:
        print(f"[ERR] '<!-- tool -->' marker not found in {path} - file not modified")
        return
    if end_marker not in t:
        print(f"[ERR] 'Data in JBrowse:' marker not found in {path} - file not modified")
        return

    i1 = t.index(start_marker)
    i2 = t.index(end_marker)
    old_section = t[i1:i2]
    new_section = build_grid()

    if old_section == new_section:
        print(f"[ok] {path} already normalized")
        return

    t2 = t[:i1] + new_section + t[i2:]
    delta = t2.count("<div") - t2.count("</div>") - (t.count("<div") - t.count("</div>"))
    if delta != 0:
        print(f"[ERR] div balance mismatch ({delta}) - file not modified")
        return
    open(path, "w", encoding="utf-8").write(t2)

    # report
    groups = [g for g in new_section.split(f'<div class="card-group">{NL}') if g.strip()]
    print(f"[done] tool grid normalized: {path}")
    n = new_section.count('class="card"')
    print(f"       {n} cards in {len(groups)} rows (each row <= 3)")


if __name__ == "__main__":
    main()
