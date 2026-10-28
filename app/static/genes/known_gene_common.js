/* =============================================================================
 * known_gene_common.js — shared helpers for the KnownGene pages
 *   /genes/            (index.html,  search + stats)
 *   /genes/detail.html (detail.html,  one curated gene record)
 *
 * Loaded with a plain <script> tag (no modules/build step), served by the
 * existing `/genes` static mount.  Everything hangs off the global `KG`
 * object so the inline page scripts can use it freely under jQuery 1.9.1.
 *
 * Conventions
 *   - ES5 syntax only (the site ships jQuery 1.9.1-era pages).
 *   - Every helper returns a plain string / object; nothing touches the DOM
 *     until the page decides to render it, and every value that reaches the
 *     DOM goes through esc()/escAttr().
 *   - Multi-value fields are separated by the half-width "; " convention used
 *     by the v2055 spreadsheet (see docs/known_genes/CONTEXT.md §1).
 * ========================================================================== */
(function (global) {
  'use strict';

  var WHEAT_CHROMS = (function () {
    var out = [];
    for (var n = 1; n <= 7; n++) {
      out.push(n + 'A', n + 'B', n + 'D');
    }
    return out;
  })();

  var WHEAT_CHROM_INDEX = (function () {
    var map = {};
    for (var i = 0; i < WHEAT_CHROMS.length; i++) { map[WHEAT_CHROMS[i]] = i; }
    return map;
  })();

  /* ------------------------------------------------------------------ *
   * Text / escaping
   * ------------------------------------------------------------------ */

  // HTML-escape a value that is about to be concatenated into markup.
  // NEVER strip tags: the v2055 data has no real HTML, but it *does* contain
  // legitimate "<" characters ("p < 0.05"), so stripping would corrupt text.
  function esc(value) {
    if (value == null) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function escAttr(value) { return esc(value); }

  function str(value) { return value == null ? '' : String(value); }

  // Trim trailing punctuation from labels derived from free text.
  function cleanLabel(value) {
    return str(value).replace(/[\s.,;:]+$/, '');
  }

  // Shorten to `n` characters, appending an ellipsis when truncated.
  function truncate(value, n) {
    var text = str(value);
    if (text.length <= n) return text;
    return text.slice(0, n).replace(/\s+\S*$/, '') + '\u2026';
  }

  function fmtNum(value) {
    var n = Number(value);
    if (!isFinite(n)) return str(value);
    return n.toLocaleString('en-US');
  }

  /* ------------------------------------------------------------------ *
   * Multi-value fields
   * ------------------------------------------------------------------ */

  // Split the spreadsheet's "; " convention.  Arrays are kept as arrays
  // (each element trimmed, empties dropped) because DOI titles can legitimately
  // contain "; " and must not be re-split.
  function splitMulti(value) {
    var out = [];
    if (value == null) return out;
    if (Object.prototype.toString.call(value) === '[object Array]') {
      for (var i = 0; i < value.length; i++) {
        var item = str(value[i]).trim();
        if (item) out.push(item);
      }
      return out;
    }
    var parts = str(value).split(/\s*;\s+/);
    for (var j = 0; j < parts.length; j++) {
      var part = parts[j].trim();
      if (part) out.push(part);
    }
    return out;
  }

  // Publication years: accept ["2008","2024"], "2008; 2024", "2008" or 2008.
  // Returns de-duplicated numeric years in ascending order as strings.
  function fmtYears(value) {
    var raw = splitMulti(value);
    var seen = {};
    var years = [];
    for (var i = 0; i < raw.length; i++) {
      var m = String(raw[i]).match(/(19|20)\d{2}/);
      if (!m) continue;
      var year = m[0];
      if (!seen[year]) { seen[year] = true; years.push(year); }
    }
    years.sort(function (a, b) { return Number(a) - Number(b); });
    return years;
  }

  /* ------------------------------------------------------------------ *
   * chromosome / reference-assembly parsing (mirrors the backend helpers)
   * ------------------------------------------------------------------ */

  // Parse "Refv1.0 chr3A:646.127-646.132Mb" / "MorexV3 chr3H:..." /
  // "AetTA1675 2D:2.33-2.45Mb" / "T.ponticum.v1 chr51:..." / "5A".
  // Returns { label, genome, raw } where label is display-ready
  // ("3A", "3H", "2D", "chr51") and genome is the assembly prefix.
  function parseChrom(pos) {
    var raw = str(pos).trim();
    var label = '';
    var match;
    if (raw) {
      match = raw.match(/chr\s*([0-9]+[A-Za-z]{0,2})\b/i);
      if (match) {
        label = match[1];
      } else {
        match = raw.match(/\b([0-9]+[A-Za-z])\s*:/) ||
                raw.match(/(?:^|\s)([0-9]+[A-Za-z]{0,2})(?=:|\s|$)/);
        if (match) label = match[1];
      }
    }
    label = label.toUpperCase();
    // T. ponticum chr51/chr54 keep a visible "chr" prefix so they cannot be
    // mistaken for a numbered wheat chromosome.
    if (/^[0-9]+$/.test(label)) label = 'chr' + label;
    return { label: label, genome: parseRefGenome(raw), raw: raw };
  }

  // First token of chrom_pos when it looks like a reference assembly name
  // ("Refv1.0", "MorexV3", "AetTA1675", "Ae.sharonensis.v1").  Bare
  // chromosome strings ("5A") and digit-only tokens return "".
  function parseRefGenome(pos) {
    var text = str(pos).trim();
    if (!text) return '';
    var token = text.split(/\s+/)[0] || '';
    if (!token || /^[0-9]+$/.test(token)) return '';
    if (/^(?:chr)?[0-9]{1,2}[A-Za-z]{0,2}$/i.test(token)) return '';
    return cleanLabel(token);
  }

  function isWheatChrom(label) {
    return WHEAT_CHROM_INDEX.hasOwnProperty(str(label).toUpperCase());
  }

  // Chromosome badge classes: wheat keeps the theme's badge-secondary, other
  // Triticeae labels use badge-light to stay visually distinct.
  function chromBadgeClass(label) {
    return 'badge kg-chrom ' + (isWheatChrom(label) ? 'badge-secondary' : 'badge-light');
  }

  // Sort the 21 wheat chromosomes into karyotype order (1A,1B,1D,…,7D).
  function sortWheatChroms(labels) {
    return labels.slice().sort(function (a, b) {
      var ia = WHEAT_CHROM_INDEX.hasOwnProperty(a) ? WHEAT_CHROM_INDEX[a] : 999;
      var ib = WHEAT_CHROM_INDEX.hasOwnProperty(b) ? WHEAT_CHROM_INDEX[b] : 999;
      return ia - ib;
    });
  }

  /* ------------------------------------------------------------------ *
   * Links (whitelisted only — never build a href from raw user-ish text)
   * ------------------------------------------------------------------ */

  var DOI_PATTERN = /^10\.\d{4,9}\/\S+$/;

  function isSafeDoi(doi) {
    return DOI_PATTERN.test(str(doi).trim());
  }

  // Return a https://doi.org/... URL for valid DOIs, "" for anything else.
  function doiUrl(doi) {
    var text = str(doi).trim();
    if (!text) return '';
    if (/^https?:\/\/doi\.org\/10\.\d{4,9}\/\S+$/i.test(text)) {
      return text.replace(/^http:/i, 'https:');
    }
    var match = text.match(/^doi:\s*(10\.\d{4,9}\/\S+)$/i);
    if (match) return 'https://doi.org/' + match[1];
    if (isSafeDoi(text)) return 'https://doi.org/' + text;
    return '';
  }

  // GeneHub only resolves TraesCS / Traes_ identifiers (see spec §3.2); every
  // other reference-genome ID is rendered as plain text to avoid dead links.
  function isGeneHubLinkable(ref) {
    var text = str(ref).trim();
    return /^TraesCS\d/.test(text) || /^Traes_/.test(text);
  }

  function geneHubUrl(ref) {
    if (!isGeneHubLinkable(ref)) return '';
    return '/GeneHub/?search=' + encodeURIComponent(str(ref).trim());
  }

  // Detail-page URL.  clone_id is the only stable key: gene_id may contain "/"
  // (e.g. "Yr87/Lr85") which would break the URL and the detail lookup.
  function detailUrl(record) {
    var r = record || {};
    var cloneId = r.clone_id;
    if (cloneId != null && String(cloneId) !== '') {
      return '/genes/detail.html?id=' + encodeURIComponent(String(cloneId));
    }
    var geneId = str(r.gene_id).trim();
    if (geneId && /^[A-Za-z0-9_.:-]+$/.test(geneId)) {
      return '/genes/detail.html?id=' + encodeURIComponent(geneId);
    }
    return '/genes/';
  }

  /* ------------------------------------------------------------------ *
   * Protein family head label
   * ------------------------------------------------------------------ */

  // "NRT1/PTR (POT) family; peptide transporter" -> "NRT1/PTR"
  // "CC-NLR (coiled-coil ...) - Sr62NLR is ..."   -> "CC-NLR"
  function familyHead(value, maxLen) {
    var text = str(value).trim();
    if (!text) return '';
    var head = text.split(/\s+-\s+|;|\(/)[0].trim();
    if (!head) head = text.split(/\s+/)[0];
    // Detail page passes 0 to show the full family head (no "..." cut);
    // list cards keep the compact 48-char label by default.
    var limit = (maxLen == null ? 48 : maxLen);
    return limit ? truncate(head, limit) : head;
  }

  /* ------------------------------------------------------------------ *
   * CSV export helpers (RFC 4180 + UTF-8 BOM + Excel formula injection)
   * ------------------------------------------------------------------ */

  // Prefix cells that Excel would treat as a formula.  The v2055 data has no
  // such values, but the escape keeps exported files safe for any future row.
  function csvGuard(text) {
    var s = str(text);
    if (/^[=+\-@\t\r]/.test(s)) return "'" + s;
    return s;
  }

  function csvCell(value) {
    if (value == null) return '""';
    var text = Object.prototype.toString.call(value) === '[object Array]'
      ? value.join('; ')
      : str(value);
    return '"' + csvGuard(text).replace(/"/g, '""') + '"';
  }

  // rows: array of arrays (already ordered).  Header must be passed separately
  // so it is never treated as user data.
  function toCsv(header, rows) {
    var lines = [];
    var h = [];
    for (var i = 0; i < header.length; i++) h.push(csvCell(header[i]));
    lines.push(h.join(','));
    for (var r = 0; r < rows.length; r++) {
      var cells = [];
      for (var c = 0; c < rows[r].length; c++) cells.push(csvCell(rows[r][c]));
      lines.push(cells.join(','));
    }
    return '\ufeff' + lines.join('\r\n');
  }

  function excelFilename(term) {
    var slug = str(term || 'all').replace(/[^A-Za-z0-9_.-]+/g, '_').slice(0, 40) || 'all';
    var ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
    return 'known_genes_' + slug + '_' + ts + '.csv';
  }

  function downloadCsv(csv, filename) {
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  /* ------------------------------------------------------------------ *
   * Long-text clamp expanders (event delegation, no per-card handlers)
   * ------------------------------------------------------------------ */

  function expandTarget(button) {
    var id = button.getAttribute('aria-controls');
    if (id) return document.getElementById(id);
    var sibling = button.previousElementSibling;
    while (sibling && sibling.nodeType === 1) {
      if (sibling.classList && sibling.classList.contains('kg-longtext')) return sibling;
      sibling = sibling.previousElementSibling;
    }
    return null;
  }

  // Toggle one `.kg-expand` button.  The full text is always in the DOM; we
  // only switch the line-clamp class state (see .kg-longtext.is-open).
  function toggleExpand(button) {
    var target = expandTarget(button);
    if (!target) return;
    var open = !target.classList.contains('is-open');
    if (open) {
      target.classList.add('is-open');
    } else {
      target.classList.remove('is-open');
    }
    button.setAttribute('aria-expanded', open ? 'true' : 'false');
    button.textContent = open ? 'Show less' : 'Show more';
  }

  // Wire clicks once per page; safe to call before content exists because the
  // listener lives on `root` (document or a container) and uses delegation.
  function bindExpanders(root) {
    var host = root || document;
    if (host.__kgExpandBound) return;
    host.__kgExpandBound = true;
    host.addEventListener('click', function (event) {
      var target = event.target;
      while (target && target !== host && !(target.classList && target.classList.contains('kg-expand'))) {
        target = target.parentNode;
      }
      if (!target || target === host) return;
      event.preventDefault();
      toggleExpand(target);
    }, false);
  }

  // Hide "Show more" buttons whose clamped text is not actually overflowing,
  // and show the button when it is (also after a viewport resize).
  function syncExpanders(root) {
    var host = root || document;
    var buttons = host.querySelectorAll('.kg-expand');
    for (var i = 0; i < buttons.length; i++) {
      var button = buttons[i];
      var target = expandTarget(button);
      if (!target) { button.hidden = true; continue; }
      if (target.classList.contains('is-open')) {
        button.hidden = false;
        continue;
      }
      // scrollHeight > clientHeight means the line clamp is cutting text off.
      var overflow = target.scrollHeight - target.clientHeight > 2;
      button.hidden = !overflow;
    }
  }

  function initExpanders(root) {
    // Bind the delegated click handler exactly once per page (on document);
    // binding again on a container would double-toggle and cancel the click.
    bindExpanders(document);
    var host = root || document;
    var run = function () { syncExpanders(host); };
    if (window.requestAnimationFrame) {
      window.requestAnimationFrame(function () { window.setTimeout(run, 0); });
    } else {
      window.setTimeout(run, 30);
    }
    if (!global.__kgResizeBound) {
      global.__kgResizeBound = true;
      var timer = null;
      window.addEventListener('resize', function () {
        if (timer) window.clearTimeout(timer);
        timer = window.setTimeout(run, 180);
      });
    }
  }

  /* ------------------------------------------------------------------ *
   * Small DOM helpers
   * ------------------------------------------------------------------ */

  // Toggle a `hidden` property/attribute in a jQuery-1.9 friendly way.
  function setHidden(selectorOrEl, hidden) {
    var el = typeof selectorOrEl === 'string'
      ? document.querySelector(selectorOrEl)
      : selectorOrEl;
    if (!el) return;
    if (hidden) {
      el.setAttribute('hidden', 'hidden');
    } else {
      el.removeAttribute('hidden');
    }
  }

  function setText(selectorOrEl, text) {
    var el = typeof selectorOrEl === 'string'
      ? document.querySelector(selectorOrEl)
      : selectorOrEl;
    if (el) el.textContent = str(text);
  }

  // Global object
  var KG = {
    // constants
    WHEAT_CHROMS: WHEAT_CHROMS,
    // escaping / text
    esc: esc,
    escAttr: escAttr,
    str: str,
    truncate: truncate,
    fmtNum: fmtNum,
    cleanLabel: cleanLabel,
    // multi-value
    splitMulti: splitMulti,
    fmtYears: fmtYears,
    // chromosome / assembly
    parseChrom: parseChrom,
    parseRefGenome: parseRefGenome,
    isWheatChrom: isWheatChrom,
    chromBadgeClass: chromBadgeClass,
    sortWheatChroms: sortWheatChroms,
    // links
    isSafeDoi: isSafeDoi,
    doiUrl: doiUrl,
    isGeneHubLinkable: isGeneHubLinkable,
    geneHubUrl: geneHubUrl,
    detailUrl: detailUrl,
    // family label
    familyHead: familyHead,
    // csv
    csvGuard: csvGuard,
    csvCell: csvCell,
    toCsv: toCsv,
    excelFilename: excelFilename,
    downloadCsv: downloadCsv,
    // clamp expanders
    bindExpanders: bindExpanders,
    syncExpanders: syncExpanders,
    initExpanders: initExpanders,
    toggleExpand: toggleExpand,
    // dom
    setHidden: setHidden,
    setText: setText
  };

  global.KG = KG;
})(window);
