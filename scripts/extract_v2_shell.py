#!/usr/bin/env python3
"""Extract the WheatOmics 2.0 site shell from the canonical BLAST page.

The BLAST SPA (app/static/blast2/index.html) was built from the live
V2.0 pages and carries the full site chrome in one file. Other SPAs should
share that chrome instead of copying it again, so this script pulls the
reusable parts — theme CSS, header, footer, SVG sprite and the header/footer
JavaScript — into app/static/_v2/ and leaves the BLAST-specific CSS behind.

Run after changing the canonical chrome (blast2 page or a V2.0 page):

    python3 scripts/extract_v2_shell.py

Outputs (all committed):
    app/static/_v2/shell.css      theme + header/footer styles + Bootstrap bridge
    app/static/_v2/shell.js       injects header/footer, wires nav/visit stats
    app/static/_v2/template.html  reference skeleton for a converted SPA

The files are served by FastAPI at /api/v2shell/ (mounted in main.py), so
Apache needs no extra ProxyPass rule: /api/* already goes to the backend.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "app" / "static" / "blast2" / "index.html"
OUT = REPO / "app" / "static" / "_v2"

BOOTSTRAP_BRIDGE = """
/* ==================== Bootstrap bridge ====================
   The older SPAs still use Bootstrap 4 markup (card / btn / form-control /
   table / nav-tabs …). These rules re-skin those components with the V2.0
   tokens so a converted page keeps its HTML and JS but looks like V2.0. */

body { background: #fff; font-size: 15px; }

.container {
  width: var(--page);
  max-width: none;
  padding: 0;
}
.container-fluid { padding: 0 24px; }

h1, h2, h3, h4, h5, h6 { color: var(--forest-deep); font-family: var(--display); letter-spacing: -.02em; }
h1 { font-size: 30px; } h2 { font-size: 24px; } h3 { font-size: 19px; } h4 { font-size: 17px; }
hr { border-top: 1px solid var(--line); }
.text-muted { color: var(--muted) !important; }
a { color: var(--leaf); }
a:hover { color: var(--forest); }

/* Cards ----------------------------------------------------------------
   The docroot copy of Bootstrap 4.5.3 is site-customised: .card-body has a
   6px #1a659e top bar and .card-title is #00aadc + centered. Neutralise both. */
.card-body { border-top: 0; }
.card-title { color: var(--forest-deep); text-align: left; }
.card {
  border: 1px solid var(--line);
  border-radius: 14px;
  background: #fff;
  box-shadow: none;
  margin-bottom: 18px;
}
.card-header {
  padding: 14px 20px;
  color: var(--forest-deep);
  background: var(--mist);
  border-bottom: 1px solid var(--line);
  font-family: var(--display);
  font-weight: 750;
  letter-spacing: -.01em;
}
.card-body { padding: 18px 20px; }
.card-footer { padding: 12px 20px; background: #fbfdfb; border-top: 1px solid var(--line); }

/* Buttons -------------------------------------------------------------- */
.btn {
  padding: 7px 16px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.4;
  transition: 160ms ease;
}
.btn-primary { color: #fff; background: var(--forest); border-color: var(--forest); }
.btn-primary:hover, .btn-primary:focus { color: #fff; background: var(--forest-deep); border-color: var(--forest-deep); }
.btn-secondary { color: var(--forest); background: var(--mist); border-color: var(--line); }
.btn-secondary:hover, .btn-secondary:focus { color: var(--forest-deep); background: #e8f3ea; border-color: rgba(17,134,83,.35); }
.btn-success { color: #fff; background: var(--leaf); border-color: var(--leaf); }
.btn-success:hover, .btn-success:focus { color: #fff; background: var(--forest); border-color: var(--forest); }
.btn-outline-primary { color: var(--forest); border-color: rgba(17,134,83,.45); }
.btn-outline-primary:hover { color: #fff; background: var(--forest); border-color: var(--forest); }
.btn-outline-secondary { color: var(--forest); border-color: var(--line); background: #fff; }
.btn-outline-secondary:hover { color: var(--forest-deep); background: var(--mist); border-color: rgba(17,134,83,.35); }
.btn-danger { color: #fff; background: #b4432f; border-color: #b4432f; }
.btn-sm { padding: 5px 12px; font-size: 12px; }
.btn-lg { padding: 11px 24px; font-size: 15px; }
.btn-link { color: var(--leaf); font-weight: 700; }

/* Forms ---------------------------------------------------------------- */
.form-control, .custom-select {
  height: 40px;
  color: var(--ink);
  background: #fbfdfb;
  border: 1px solid var(--line);
  border-radius: 8px;
  font-size: 13px;
}
textarea.form-control { height: auto; min-height: 96px; padding: 10px 12px; }
.form-control:focus, .custom-select:focus {
  border-color: rgba(17,134,83,.55);
  box-shadow: 0 0 0 3px rgba(119,185,65,.20);
  background: #fff;
}
.form-control::placeholder { color: #96a79d; }
.form-group label, .control-label, label { color: var(--forest-deep); font-weight: 700; font-size: 12px; }
.custom-control-label { font-weight: 500; font-size: 13px; color: var(--ink); }
.custom-control-input:checked ~ .custom-control-label::before { background-color: var(--forest); border-color: var(--forest); }
.form-text { color: var(--muted); font-size: 11px; }
.input-group-text { background: var(--mist); border: 1px solid var(--line); border-radius: 8px; font-size: 12px; }

/* Tables --------------------------------------------------------------- */
.table { color: var(--ink); font-size: 13px; }
.table thead th {
  padding: 9px 12px;
  color: #4d6559;
  background: var(--mist);
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  font-family: var(--utility);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .07em;
  text-transform: uppercase;
  white-space: nowrap;
}
.table td, .table th { padding: 8px 12px; border-top: 1px solid var(--line); vertical-align: middle; }
.table-striped tbody tr:nth-of-type(odd) { background: #fbfdfb; }
.table-hover tbody tr:hover { background: #f1f8f2; }
.table-bordered, .table-bordered td, .table-bordered th { border: 1px solid var(--line); }

/* Tabs ----------------------------------------------------------------- */
.nav-tabs { border-bottom: 1px solid var(--line); }
.nav-tabs .nav-link {
  padding: 8px 16px;
  color: #5e7268;
  background: transparent;
  border: 0;
  border-bottom: 2px solid transparent;
  border-radius: 0;
  font-size: 13px;
  font-weight: 700;
}
.nav-tabs .nav-link:hover { color: var(--forest); border-bottom-color: rgba(17,134,83,.35); }
.nav-tabs .nav-link.active { color: var(--forest); background: transparent; border-bottom-color: var(--forest); }
.nav-pills .nav-link { color: #5e7268; border-radius: 999px; font-size: 13px; font-weight: 700; padding: 6px 14px; }
.nav-pills .nav-link.active { color: #fff; background: var(--forest); }

/* Badges / alerts / list group ---------------------------------------- */
.badge {
  padding: 4px 9px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .02em;
}
.badge-primary, .badge-info { color: #fff; background: var(--forest); }
.badge-secondary { color: var(--forest); background: var(--mist); }
.badge-success { color: #fff; background: var(--leaf); }
.badge-warning { color: #5a4308; background: #f6e2ac; }
.badge-danger { color: #fff; background: #b4432f; }
.badge-light { color: var(--forest-deep); background: #eef6f0; }

.alert { border-radius: 12px; border: 1px solid var(--line); font-size: 13px; }
.alert-info { color: #1e4d3b; background: #eef7f1; border-color: #cfe6d6; }
.alert-warning { color: #6b4f07; background: #fdf6e3; border-color: #f0dfb0; }
.alert-danger { color: #7d2a1b; background: #fdf1ee; border-color: #f0c9bf; }
.alert-success { color: #14543a; background: #edf8f1; border-color: #c9e7d4; }

.list-group-item { border-color: var(--line); font-size: 13px; }
.list-group-item.active { color: #fff; background: var(--forest); border-color: var(--forest); }

/* Modal / dropdown / pagination / progress ---------------------------- */
.modal-content { border: 1px solid var(--line); border-radius: 16px; box-shadow: 0 30px 80px rgba(8,69,47,.22); }
.modal-header { padding: 16px 22px; border-bottom: 1px solid var(--line); }
.modal-title { font-family: var(--display); font-weight: 750; color: var(--forest-deep); }
.modal-body { padding: 20px 22px; font-size: 13px; }
.modal-footer { padding: 14px 22px; border-top: 1px solid var(--line); }

.dropdown-menu {
  padding: 6px;
  border: 1px solid var(--line);
  border-radius: 12px;
  box-shadow: 0 18px 44px rgba(8,69,47,.14);
  font-size: 13px;
}
.dropdown-item { padding: 7px 12px; border-radius: 8px; }
.dropdown-item:hover, .dropdown-item:focus { color: var(--forest-deep); background: var(--mist); }

.pagination { font-size: 12px; }
.page-link { color: var(--forest); border-color: var(--line); border-radius: 8px !important; margin: 0 2px; }
.page-item.active .page-link { color: #fff; background: var(--forest); border-color: var(--forest); }
.progress { height: 8px; border-radius: 999px; background: #e9f1eb; }
.progress-bar { background: var(--leaf); }

/* Small layout helpers used by the converted pages ------------------- */
.v2-tool-head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 14px; margin: 4px 0 20px; }
.v2-tool-head h2 { margin: 0; font-size: 23px; }
.v2-tool-head .v2-note { margin: 0; color: var(--muted); font-size: 12px; }
.v2-section-title { margin: 26px 0 12px; font-family: var(--display); font-size: 17px; font-weight: 750; letter-spacing: -.02em; color: var(--forest-deep); }
.v2-chip-row { display: flex; flex-wrap: wrap; gap: 8px; }
.v2-chip { display: inline-flex; align-items: center; gap: 6px; padding: 5px 11px; color: var(--forest); background: var(--mist); border: 1px solid var(--line); border-radius: 999px; font-size: 11px; font-weight: 700; }
.v2-mono { font-family: var(--utility); font-size: 12px; }
"""


def main() -> None:
    src = SRC.read_text(encoding="utf-8")
    lines = src.splitlines()

    def find(pattern: str, start: int = 0) -> int:
        rx = re.compile(pattern)
        for i in range(start, len(lines)):
            if rx.search(lines[i]):
                return i
        raise SystemExit(f"anchor not found: {pattern}")

    # ---- CSS -----------------------------------------------------------
    style_start = find(r"^\s*<style>\s*$")
    style_end = find(r"^\s*</style>\s*$")
    css_lines = lines[style_start + 1:style_end]

    # Drop the BLAST-only / external-link / news? sections that only make
    # sense on the canonical page.
    drop_from = []
    for marker in (
        "External Links hero wheat photo",
        "BLAST tool page",
    ):
        drop_from.append(next(i for i, ln in enumerate(css_lines) if marker in ln))

    # External-links block sits before the BLAST block: cut between them.
    ext_start, blast_start = drop_from[0], drop_from[1]
    kept = css_lines[:ext_start] + css_lines[blast_start:]
    # The BLAST block runs to the end of the stylesheet.
    blast_in_kept = next(i for i, ln in enumerate(kept) if "BLAST tool page" in ln)
    kept = kept[:blast_in_kept]

    theme_css = "\n".join(kept)
    theme_css = theme_css.replace('url("home.png")', 'url("/V2.0/home.png")')

    shell_css = (
        "/* WheatOmics 2.0 shared shell — generated by scripts/extract_v2_shell.py\n"
        "   from app/static/blast2/index.html (canonical V2.0 chrome).\n"
        "   Do not edit by hand; edit the canonical page and re-run the script. */\n"
        + theme_css.strip()
        + "\n"
        + BOOTSTRAP_BRIDGE
    )
    (OUT / "shell.css").write_text(shell_css, encoding="utf-8")

    # ---- sprite --------------------------------------------------------
    sprite_start = find(r'<svg aria-hidden="true" width="0" height="0"')
    sprite_end = find(r"^\s*</svg>\s*$", sprite_start)
    sprite = "\n".join(lines[sprite_start:sprite_end + 1])

    # ---- header --------------------------------------------------------
    header_start = find(r"^\s*<header class=\"site-header\">")
    header_end = find(r"^\s*</header>\s*$", header_start)
    header = "\n".join(lines[header_start:header_end + 1])

    # ---- footer --------------------------------------------------------
    footer_start = find(r"^\s*<footer class=\"site-footer\">")
    footer_end = find(r"^\s*</footer>\s*$", footer_start)
    footer = "\n".join(lines[footer_start:footer_end + 1])

    # ---- chrome JS (nav toggle, back-to-top, visit stats) --------------
    script_start = find(r"^\s*<script>\s*$", footer_end)
    script_end = find(r"^\s*</script>\s*$", script_start)
    chrome_js = "\n".join(lines[script_start + 1:script_end])
    # The back-to-top button is wired by the shell template below, so drop the
    # canonical page's copy (three lines: trigger + scrollTo + closing `});`).
    raw = [ln.rstrip() for ln in chrome_js.strip().splitlines()]
    for i, ln in enumerate(raw):
        if ".back-top" in ln:
            j = i
            while j < len(raw) and raw[j].strip() != "});":
                j += 1
            del raw[i:j + 1]
            break
    import textwrap
    chrome_js = textwrap.dedent("\n".join(raw))

    def js_template(text: str) -> str:
        return "`" + text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${") + "`"

    shell_js = f"""/* WheatOmics 2.0 shared shell — generated by scripts/extract_v2_shell.py
   from app/static/blast2/index.html (canonical V2.0 chrome).
   Injects the site header/footer into a page that provides
   <div id="v2-shell-header"></div> and <div id="v2-shell-footer"></div>
   (or no placeholders at all), then wires the mobile menu, dropdowns,
   back-to-top button and the footer visit statistics. */
(function () {{
  'use strict';
  var SPRITE = {js_template(sprite)};
  var HEADER = {js_template(header)};
  var FOOTER = {js_template(footer)};

  function initChrome() {{
    var backTop = document.querySelector('.back-top');
    if (backTop) {{
      backTop.addEventListener('click', function () {{ window.scrollTo({{ top: 0, behavior: 'smooth' }}); }});
    }}
{chr(10).join('    ' + ln for ln in chrome_js.splitlines())}

    /* Mark the nav entry of the current module as active. */
    try {{
      var path = location.pathname;
      var aliases = [
        ['/blast/', '/blast/'], ['/getfasta/', '/getfasta/'], ['/genes/', '/genes/'],
        ['/expression/', '/expression/'], ['/coexpression/', '/coexpression/'],
        ['/interval/', '/interval/'], ['/PfamSearch/', '/PfamSearch/'],
        ['/idConvert/', '/idConvert/'], ['/HomologFinder/', '/HomologFinder/'],
        ['/caps/', '/caps/'], ['/preblast/', '/preblast/'], ['/sms2/', '/sms2/'],
        ['/VariantHub/', '/VariantHub/'], ['/eqtl/', '/eqtl/'],
        ['/GO_KEGG/', '/GO_KEGG/'], ['/syntenyview/', '/syntenyview/'],
        ['/orthofinder/', '/orthofinder/'], ['/scRNA/', '/scRNA/'],
        ['/wheatPPI/', '/wheatPPI/'], ['/wheatPSP/', '/wheatPSP/'],
        ['/papers/', '/papers/'], ['/wheatPTM/', '/wheatPTM/']
      ];
      var current = aliases.find(function (pair) {{ return path.indexOf(pair[0]) === 0; }});
      if (current) {{
        var link = document.querySelector('.main-nav a[href*="' + current[1] + '"]');
        if (link) {{
          link.setAttribute('aria-current', 'page');
          link.classList.add('is-current');
        }}
      }}
    }} catch (err) {{ /* non-fatal */ }}
  }}

  function injectChrome() {{
    var headerHost = document.getElementById('v2-shell-header');
    if (!headerHost) {{
      headerHost = document.createElement('div');
      headerHost.id = 'v2-shell-header';
      document.body.insertBefore(headerHost, document.body.firstChild);
    }}
    headerHost.innerHTML = SPRITE + HEADER;

    var footerHost = document.getElementById('v2-shell-footer');
    if (!footerHost) {{
      footerHost = document.createElement('div');
      footerHost.id = 'v2-shell-footer';
      document.body.appendChild(footerHost);
    }}
    footerHost.innerHTML = FOOTER;
  }}

  function boot() {{
    injectChrome();
    initChrome();
  }}

  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', boot);
  }} else {{
    boot();
  }}
}})();
"""
    (OUT / "shell.js").write_text(shell_js, encoding="utf-8")

    template = """<!doctype html>
<!--
  Reference skeleton for a converted WheatOmics SPA.
  Copy the head/hero/main structure below and keep the page's own JS at the
  bottom. The header, footer, sprite, mobile menu and visit statistics come
  from /api/v2shell/shell.js — do not paste header/footer markup again.
-->
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MODULE | WheatOmics 2.0</title>
  <link rel="shortcut icon" href="/favicon.ico" type="image/x-icon">
  <link rel="stylesheet" href="/api/v2shell/shell.css">
  <style>
    /* page-specific styles on top of the shared shell */
  </style>
</head>
<body>
  <div id="v2-shell-header"></div>

  <main id="main-content">
    <section class="news-hero">
      <div class="container news-hero-inner">
        <div>
          <p class="news-kicker">WheatOmics 2.0 · Analysis tool</p>
          <h1 class="news-title">MODULE</h1>
          <p class="news-lead">One-sentence description of what this tool does and what the user gets back.</p>
          <div class="news-stats">
            <span class="news-stat"><strong>N</strong> databases</span>
            <span class="news-stat">Async job queue</span>
          </div>
        </div>
        <div class="news-hero-mark" aria-hidden="true"><svg class="icon"><use href="#i-search"/></svg></div>
      </div>
    </section>

    <section class="news-body">
      <div class="container">
        <!-- page content goes here -->
      </div>
    </section>
  </main>

  <div id="v2-shell-footer"></div>

  <script src="/js/jquery/1.9.1/jquery.min.js"></script>
  <script src="/api/v2shell/shell.js"></script>
  <script>
    /* page JS */
  </script>
</body>
</html>
"""
    (OUT / "template.html").write_text(template, encoding="utf-8")

    for name in ("shell.css", "shell.js", "template.html"):
        path = OUT / name
        print(f"wrote {path.relative_to(REPO)} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
