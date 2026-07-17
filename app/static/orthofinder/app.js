let currentGenes = [];
let currentQuery = "";
let currentOG = "";
let treeZoom = 1;
let syntenyZoom = 1;
let currentTree = "";
let currentClusterTree = "";
let currentLabelMap = {};
let currentParsedTree = null;
let currentPreparedTree = null;
let treeMode = "rectangular";
let currentCluster = null;
let clusterGeneSet = {};
let currentSyntenyData = null;
let speciesList = [];

const SUB_COLORS = { A: "#d73027", B: "#4575b4", D: "#1a9850", Other: "#777777" };

document.addEventListener("DOMContentLoaded", function () {
  loadSpeciesCatalog();
  document.getElementById("searchForm").addEventListener("submit", function (e) {
    e.preventDefault();
    var q = document.getElementById("proteinInput").value.trim();
    if (q) {
      var url = new URL(window.location.href);
      url.searchParams.set("q", q);
      window.history.pushState({}, "", url);
      searchProtein(q);
    }
  });
  document.getElementById("geneFilter").addEventListener("input", renderGeneList);
  var params = new URLSearchParams(window.location.search);
  var q = params.get("q");
  if (q) {
    document.getElementById("proteinInput").value = q;
    searchProtein(q);
  }
});

/* ---- Species catalog ---- */
async function loadSpeciesCatalog() {
  try {
    var res = await fetch("/api/orthofinder/species_catalog");
    var json = await res.json();
    if (!json.error && json.data && json.data.species) {
      speciesList = json.data.species;
      var sel = document.getElementById("speciesSelect");
      speciesList.forEach(function (s) {
        var opt = document.createElement("option"); opt.value = s; opt.textContent = s; sel.appendChild(opt);
      });
    }
  } catch (e) {}
}
function onSpeciesChange() {
  document.getElementById("subgenomeSelect").style.display = document.getElementById("speciesSelect").value ? "" : "none";
  updateProteinPlaceholder();
}
function onSubgenomeChange() { updateProteinPlaceholder(); }
function updateProteinPlaceholder() {
  var species = document.getElementById("speciesSelect").value;
  var sub = document.getElementById("subgenomeSelect").value;
  var input = document.getElementById("proteinInput");
  if (species && sub) input.placeholder = "Type gene ID for " + species + " " + sub + " subgenome...";
  else if (species) input.placeholder = "Type gene ID for " + species + "...";
  else input.placeholder = "e.g. TraesCS1A03G0053300.1";
}

/* ---- Main search ---- */
async function searchProtein(q) {
  currentQuery = q;
  var msg = document.getElementById("message");
  var result = document.getElementById("result");
  msg.textContent = "Loading...";
  result.style.display = "none";

  try {
    var res = await fetch("/api/orthofinder/search?q=" + encodeURIComponent(q));
    var json = await res.json();
    if (!res.ok || !json.success) {
      msg.textContent = json.detail || json.error || "Server error: " + res.status;
      return;
    }
    var data = json.data;
    msg.textContent = "";
    result.style.display = "block";

    currentOG = data.orthogroup;
    currentGenes = data.genes || [];
    currentTree = data.tree || "";
    currentLabelMap = data.tree_label_map || {};
    currentCluster = data.query_cluster || null;
    clusterGeneSet = {};
    if (data.cluster_genes) {
      data.cluster_genes.forEach(function (g) { clusterGeneSet[g] = true; clusterGeneSet[firstToken(g)] = true; });
    }

    document.getElementById("ogTitle").textContent =
      data.orthogroup + " | Query: " + data.query + " | Members: " + data.gene_count;

    // Badge
    var badge = document.getElementById("clusterBadge");
    if (currentCluster) {
      badge.textContent = "Cluster " + currentCluster;
      badge.className = "cluster-badge cluster-badge-" + currentCluster;
      badge.style.display = "";
    } else {
      badge.style.display = "none";
    }

    // Download links
    document.getElementById("downloadTree").href =
      "/api/orthofinder/download?og=" + encodeURIComponent(data.orthogroup) + "&type=tree";
    document.getElementById("downloadAlignment").href =
      "/api/orthofinder/download?og=" + encodeURIComponent(data.orthogroup) + "&type=alignment";

    var dlc = document.getElementById("downloadClusterTree");
    if (currentCluster && data.query) {
      dlc.href = "/api/orthofinder/download?og=" + encodeURIComponent(data.orthogroup) +
        "&type=tree&cluster=" + currentCluster;
      dlc.style.display = "";
    } else {
      dlc.style.display = "none";
    }

    // Tree heading
    var treeClusterLabel = document.getElementById("treeClusterLabel");
    if (currentCluster) {
      document.getElementById("treeHeading").textContent = "Cluster " + currentCluster + " Gene Tree";
      treeClusterLabel.style.display = "";
      treeClusterLabel.textContent = "Showing " + data.cluster_gene_count +
        " genes from cluster " + currentCluster + " (full OG has " + data.gene_count + " genes)";
    } else {
      document.getElementById("treeHeading").textContent = "Gene Tree";
      treeClusterLabel.style.display = "none";
    }

    currentClusterTree = data.cluster_tree || "";
    if (currentCluster && !currentClusterTree && data.debug_prune) {
      console.log("DEBUG prune:", JSON.stringify(data.debug_prune));
      msg.textContent += " [Prune: matched " + (data.debug_prune.pruned_leaf_count || 0) + " leaves]";
    }

    var treeForDisplay = (currentCluster && currentClusterTree) ? currentClusterTree : currentTree;
    currentParsedTree = treeForDisplay ? parseNewick(treeForDisplay.trim()) : null;
    currentPreparedTree = null;

    document.getElementById("geneFilter").value = "";
    renderGeneList();
    renderTree();
    loadAndRenderSynteny();
    renderAlignment(data.alignment_preview || []);
  } catch (e) {
    msg.textContent = "Request failed: " + e.message;
  }
}

/* ---- Gene list ---- */
function renderGeneList() {
  var box = document.getElementById("geneList");
  var keyword = document.getElementById("geneFilter").value.trim().toLowerCase();
  var genes = currentGenes.filter(function (g) {
    return !keyword || g.toLowerCase().includes(keyword);
  });
  box.innerHTML = genes.map(function (g) {
    var hit = g === currentQuery ? " hit" : "";
    return '<div class="gene-item' + hit + '">' + escapeHtml(g) + "</div>";
  }).join("");
}

/* ---- Alignment ---- */
function renderAlignment(preview) {
  var box = document.getElementById("alignmentBox");
  if (!preview || preview.length === 0) {
    box.textContent = "Alignment file was not found for this orthogroup.";
    return;
  }
  var html = "";
  preview.forEach(function (p) {
    html += '<span class="aa-header">&gt;' + escapeHtml(p.label || p.id) + "</span>\n";
    var seq = p.seq || "";
    html += seq.replace(/-/g, '<span class="aa-gap">-</span>')
              .replace(/\*/g, '<span class="aa-stop">*</span>') + "\n";
  });
  box.innerHTML = html;
}

/* ---- Newick parser ---- */
function parseNewick(newick) {
  var i = 0;
  function skip() { while (i < newick.length && /\s/.test(newick[i])) i++; }
  function readName() {
    skip();
    if (i >= newick.length) return "";
    if (newick[i] === "'" || newick[i] === '"') {
      var q = newick[i++]; var s = i;
      while (i < newick.length && newick[i] !== q) i++;
      var name = newick.slice(s, i).trim();
      if (i < newick.length) i++;
      return cleanId(name);
    }
    var s = i;
    while (i < newick.length && !["(", ")", ",", ":", ";"].includes(newick[i])) i++;
    return cleanId(newick.slice(s, i));
  }
  function readLength() {
    skip();
    if (newick[i] !== ":") return 0;
    i++;
    var s = i;
    while (i < newick.length && !["(", ")", ",", ":", ";"].includes(newick[i])) i++;
    var v = parseFloat(newick.slice(s, i));
    return Number.isFinite(v) ? v : 0;
  }
  function node() {
    skip();
    var n = { name: "", length: 0, children: [] };
    if (newick[i] === "(") {
      i++;
      while (i < newick.length) {
        n.children.push(node());
        skip();
        if (newick[i] === ",") { i++; continue; }
        if (newick[i] === ")") { i++; break; }
        break;
      }
      n.name = readName();
      n.length = readLength();
    } else {
      n.name = readName();
      n.length = readLength();
    }
    return n;
  }
  return node();
}
function cleanId(s) { return String(s || "").trim().replace(/^['"]|['"]$/g, ""); }
function firstToken(s) { return cleanId(String(s || "").split(/\s+/)[0]); }

function getTreeInfo(name) {
  var key = firstToken(name);
  if (currentLabelMap[key]) return currentLabelMap[key];
  if (currentLabelMap[name]) return currentLabelMap[name];
  return { full_label: key || name, gene_id: key || name, subgenome: inferSubFromId(key || name) };
}
function inferSubFromId(id) {
  var s = String(id || "");
  if (/(^|_)A(_|$)/i.test(s) || /\dA\d/i.test(s)) return "A";
  if (/(^|_)B(_|$)/i.test(s) || /\dB\d/i.test(s)) return "B";
  if (/(^|_)D(_|$)/i.test(s) || /\dD\d/i.test(s)) return "D";
  return "Other";
}
function normalizeSub(s) { return s === "A" || s === "B" || s === "D" ? s : "Other"; }
function dominantSub(counts) {
  var best = "Other", bestN = -1;
  ["A", "B", "D", "Other"].forEach(function (k) { if ((counts[k] || 0) > bestN) { bestN = counts[k] || 0; best = k; } });
  return best;
}

function getPreparedTree() {
  if (currentPreparedTree) return currentPreparedTree;
  var root = currentParsedTree || (currentTree ? parseNewick(currentTree.trim()) : null);
  if (!root) return null;
  var leaves = []; var maxDepth = 0;
  function walk(n, depth) {
    n.depth = depth;
    maxDepth = Math.max(maxDepth, depth);
    if (!n.children || n.children.length === 0) {
      var key = firstToken(n.name);
      var info = getTreeInfo(key);
      n.rawName = key;
      n.displayLabel = info.full_label || info.label || info.gene_id || key;
      n.sub = normalizeSub(info.subgenome || inferSubFromId(n.displayLabel || key));
      n.order = leaves.length;
      n.counts = { A: 0, B: 0, D: 0, Other: 0 };
      n.counts[n.sub]++;
      n.numLeaves = 1;
      leaves.push(n);
      return n.counts;
    }
    n.counts = { A: 0, B: 0, D: 0, Other: 0 };
    n.numLeaves = 0;
    n.children.forEach(function (c) {
      var cc = walk(c, depth + 1);
      ["A", "B", "D", "Other"].forEach(function (k) { n.counts[k] += cc[k]; });
      n.numLeaves += c.numLeaves;
    });
    n.sub = dominantSub(n.counts);
    return n.counts;
  }
  walk(root, 0);
  function bounds(n) {
    if (!n.children || n.children.length === 0) {
      n.minOrder = n.order; n.maxOrder = n.order; n.meanOrder = n.order;
      return [n.minOrder, n.maxOrder, n.meanOrder, 1];
    }
    var mn = Infinity, mx = -Infinity, sum = 0, cnt = 0;
    n.children.forEach(function (c) {
      var b = bounds(c);
      mn = Math.min(mn, b[0]);
      mx = Math.max(mx, b[1]);
      sum += b[2] * b[3];
      cnt += b[3];
    });
    n.minOrder = mn; n.maxOrder = mx; n.meanOrder = sum / cnt;
    return [mn, mx, n.meanOrder, cnt];
  }
  bounds(root);
  currentPreparedTree = { root: root, leaves: leaves, maxDepth: maxDepth };
  return currentPreparedTree;
}

/* ---- Tree rendering ---- */
function setTreeMode(mode) { treeMode = mode; renderTree(); }
function renderTree() { if (treeMode === "circular") renderTreeCircular(); else renderTreeRectangular(); }

function clearSvg(svg) {
  svg.innerHTML = "";
  if (svg.id === "treeSvg") { treeZoom = 1; svg.style.transform = "scale(1)"; }
  else { syntenyZoom = 1; svg.style.transform = "scale(1)"; }
}

function renderTreeRectangular() {
  var svg = document.getElementById("treeSvg"); clearSvg(svg);
  var treeForDisplay = (currentCluster && currentClusterTree) ? currentClusterTree : currentTree;
  if (!treeForDisplay) { svg.innerHTML = "<text x='20' y='30'>Tree file was not found.</text>"; return; }
  var prep = getPreparedTree(); if (!prep) return;
  var root = prep.root, leaves = prep.leaves, maxDepth = prep.maxDepth;
  var showLabels = leaves.length < 220;
  var rowH = showLabels ? 24 : 12;
  var top = 42, left = 45;
  var treeRight = showLabels ? 690 : 1040;
  var labelX = showLabels ? 820 : 1080;
  var width = showLabels ? 1900 : 1180;
  var height = Math.max(720, top * 2 + leaves.length * rowH);
  leaves.forEach(function (leaf, idx) { leaf.y = top + idx * rowH; });
  function setY(n) {
    if (!n.children || n.children.length === 0) return n.y;
    n.children.forEach(setY);
    n.y = n.children.reduce(function (s, c) { return s + c.y; }, 0) / n.children.length;
    return n.y;
  }
  setY(root);
  var x = function (d) { return left + (maxDepth > 0 ? d / maxDepth : 0) * (treeRight - left); };
  svg.setAttribute("width", width); svg.setAttribute("height", height);
  svg.setAttribute("viewBox", "0 0 " + width + " " + height);
  var parts = [];
  function draw(n) {
    if (!n.children || n.children.length === 0) {
      if (showLabels) {
        var endX = x(n.depth);
        var tip = n.displayLabel || n.name;
        parts.push('<g class="tree-leaf"><title>' + escapeHtml(tip) + ' [' + n.sub + '_subgenome]</title>');
        parts.push(lineSvg(endX, n.y, labelX - 12, n.y, n.sub, 0.9));
        parts.push(textSvg(labelX, n.y + 4, tip, n.sub, 11, true));
        parts.push('</g>');
      }
      return;
    }
    var px = x(n.depth);
    var ys = n.children.map(function (c) { return c.y; });
    parts.push('<g><title>' + n.numLeaves + ' genes in this clade</title>' +
      lineSvg(px, Math.min.apply(null, ys), px, Math.max.apply(null, ys), n.sub, 1.6) + '</g>');
    n.children.forEach(function (c) {
      parts.push('<g><title>' + c.numLeaves + ' genes in this clade (' + c.sub + '_subgenome)</title>' +
        lineSvg(px, c.y, x(c.depth), c.y, c.sub, 1.6) + '</g>');
      draw(c);
    });
  }
  draw(root);
  svg.innerHTML = parts.join("");
}

function renderTreeCircular() {
  var svg = document.getElementById("treeSvg"); clearSvg(svg);
  var treeForDisplay = (currentCluster && currentClusterTree) ? currentClusterTree : currentTree;
  if (!treeForDisplay) { svg.innerHTML = "<text x='20' y='30'>Tree file was not found.</text>"; return; }
  var prep = getPreparedTree(); if (!prep) return;
  var root = prep.root, leaves = prep.leaves, maxDepth = prep.maxDepth;
  var showLabels = leaves.length < 220;
  var size = showLabels ? 2200 : Math.max(1000, Math.min(2800, leaves.length * 10));
  var cx = size / 2, cy = size / 2;
  var radius = showLabels ? size / 2 - 430 : size / 2 - 120;
  var labelRadius = showLabels ? radius + 135 : radius + 20;
  var innerRadius = showLabels ? 18 : 8;
  var nLeaves = Math.max(1, leaves.length);
  var angleForOrder = function (order) { return (2 * Math.PI * (order + 0.5)) / nLeaves - Math.PI / 2; };
  leaves.forEach(function (leaf) { leaf.angle = angleForOrder(leaf.order); });
  function setAngle(n) {
    if (!n.children || n.children.length === 0) return n.angle;
    n.children.forEach(setAngle);
    var sx = 0, sy = 0, cnt = 0;
    n.children.forEach(function (c) {
      var w = (c.maxOrder - c.minOrder + 1) || 1;
      sx += Math.cos(c.angle) * w;
      sy += Math.sin(c.angle) * w;
      cnt += w;
    });
    n.angle = cnt ? Math.atan2(sy / cnt, sx / cnt) : 0;
    return n.angle;
  }
  setAngle(root);
  function rOf(n) { return innerRadius + (maxDepth > 0 ? (n.depth / maxDepth) * (radius - innerRadius) : 0); }
  function xy(r, a) { return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) }; }
  svg.setAttribute("width", size); svg.setAttribute("height", size);
  svg.setAttribute("viewBox", "0 0 " + size + " " + size);
  var parts = [];
  function draw(n) {
    var p = xy(rOf(n), n.angle);
    if (!n.children || n.children.length === 0) {
      if (showLabels) {
        var ep = xy(labelRadius - 22, n.angle);
        var lp = xy(labelRadius, n.angle);
        var tip = n.displayLabel || n.name;
        parts.push('<g class="tree-leaf"><title>' + escapeHtml(tip) + ' [' + n.sub + '_subgenome]</title>' +
          lineSvg(p.x, p.y, ep.x, ep.y, n.sub, 0.9) + radialTextSvg(lp.x, lp.y, n.angle, tip, n.sub) + '</g>');
      }
      return;
    }
    n.children.forEach(function (c) {
      var cp = xy(rOf(c), c.angle);
      parts.push('<g><title>' + c.numLeaves + ' genes in this clade (' + c.sub + '_subgenome)</title>' +
        lineSvg(p.x, p.y, cp.x, cp.y, c.sub, 1.6) + '</g>');
      draw(c);
    });
  }
  draw(root);
  svg.innerHTML = parts.join("");
}

/* ---- SVG helpers ---- */
function lineSvg(x1, y1, x2, y2, sub, w) {
  return '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 +
    '" stroke="' + (SUB_COLORS[sub] || SUB_COLORS.Other) + '" stroke-width="' + (w || 1.6) + '" fill="none"/>';
}
function textSvg(x, y, text, sub, size, halo) {
  var extra = halo ? ' paint-order="stroke" stroke="#fff" stroke-width="5" stroke-linejoin="round"' : "";
  return '<text x="' + x + '" y="' + y + '" fill="' + (SUB_COLORS[sub] || "#333") +
    '" font-size="' + size + '"' + extra + '>' + escapeHtml(text) + '</text>';
}
function radialTextSvg(x, y, angle, text, sub) {
  var deg = angle * 180 / Math.PI;
  var flip = deg > 90 && deg < 270;
  return '<text x="' + x + '" y="' + y + '" fill="' + (SUB_COLORS[sub] || "#333") +
    '" font-size="10" dominant-baseline="middle" paint-order="stroke" stroke="#fff" stroke-width="4" stroke-linejoin="round"' +
    ' text-anchor="' + (flip ? 'end' : 'start') +
    '" transform="rotate(' + (flip ? deg + 180 : deg) + ',' + x + ',' + y + ')">' + escapeHtml(text) + '</text>';
}
function zoomTree(factor) {
  treeZoom = Math.max(0.3, Math.min(treeZoom * factor, 4));
  document.getElementById("treeSvg").style.transform = "scale(" + treeZoom + ")";
}
function resetTreeZoom() { treeZoom = 1; document.getElementById("treeSvg").style.transform = "scale(1)"; }

/* =================================================================
   Synteny Visualization — JCVI-style
   ================================================================= */

async function loadAndRenderSynteny() {
  if (!currentOG) return;
  var clusterParam = currentCluster ? "&cluster=" + currentCluster : "";
  var url = "/api/orthofinder/positions?og=" + encodeURIComponent(currentOG) + clusterParam;
  try {
    var res = await fetch(url);
    var json = await res.json();
    if (!json.success || json.data.error) {
      document.getElementById("syntenyBox").textContent = json.data ? json.data.error : "No data";
      return;
    }
    currentSyntenyData = json.data;
    renderSynteny(json.data);
  } catch (e) {
    document.getElementById("syntenyBox").textContent = "Failed to load chromosome positions.";
  }
}

function renderSynteny(data) {
  var svg = document.getElementById("syntenySvg");
  svg.innerHTML = "";
  if (!data.positions || data.positions.length === 0) {
    svg.innerHTML = "<text x='20' y='30' font-size='13' fill='#999'>No chromosome position data.</text>";
    svg.setAttribute("width", "900"); svg.setAttribute("height", "60"); return;
  }

  var positions = data.positions;

  function fullChr(p) { return (p.genome || "") + "_" + (p.chromosome || ""); }
  var byChr = {};
  positions.forEach(function (p) {
    var key = fullChr(p);
    if (!byChr[key]) byChr[key] = [];
    byChr[key].push(p);
  });

  var chrNames = Object.keys(byChr).sort(chrSorter);
  chrNames.forEach(function (chr) { byChr[chr].sort(function (a, b) { return a.start - b.start; }); });

  var chrSpans = {};
  chrNames.forEach(function (chr) {
    var genes = byChr[chr];
    var minS = Infinity, maxE = -Infinity;
    genes.forEach(function (p) { if (p.start < minS) minS = p.start; if (p.end > maxE) maxE = p.end; });
    var pad = Math.max((maxE - minS) * 0.05, 5000);
    chrSpans[chr] = { min: Math.max(0, minS - pad), max: maxE + pad };
    chrSpans[chr].len = chrSpans[chr].max - chrSpans[chr].min + 1;
  });

  var LEFT_W = 200, RIGHT_PAD = 40, TRACK_H = 56, TRACK_GAP = 8, BAR_H = 9, CHART_W = 720;
  var nChrs = chrNames.length;
  var svgWidth = LEFT_W + CHART_W + RIGHT_PAD;
  var svgHeight = nChrs * (TRACK_H + TRACK_GAP) + 60;

  svg.setAttribute("width", svgWidth);
  svg.setAttribute("height", svgHeight);
  svg.setAttribute("viewBox", "0 0 " + svgWidth + " " + svgHeight);

  function trackTop(ci) { return 30 + ci * (TRACK_H + TRACK_GAP); }
  function trackCY(ci) { return trackTop(ci) + TRACK_H / 2; }

  var parts = [];
  var geneCoords = {};

  chrNames.forEach(function (chr, ci) {
    var genes = byChr[chr], span = chrSpans[chr], ty = trackTop(ci);
    genes.forEach(function (p) {
      var frac = span.len > 0 ? ((p.start - span.min) / span.len) : 0;
      var gx = LEFT_W + frac * CHART_W;
      geneCoords[p.gene_id] = {
        x: gx, y: ty + TRACK_H - BAR_H - 6 + BAR_H / 2,
        subgenome: p.subgenome || "Other", chr: chr, label: p.label || p.gene_id
      };
    });
  });

  // ---- Synteny lines: evenly distributed across adjacent tracks ----
  var nPairs = Math.max(1, chrNames.length - 1);
  var maxPerPair = Math.max(15, Math.floor(2500 / nPairs));

  for (var i = 0; i < chrNames.length - 1; i++) {
    var j = i + 1;
    var genesI = byChr[chrNames[i]], genesJ = byChr[chrNames[j]];
    var linksThisPair = 0;
    var pairs = [];
    genesI.forEach(function (gi) {
      var c1 = geneCoords[gi.gene_id]; if (!c1) return;
      genesJ.forEach(function (gj) {
        var c2 = geneCoords[gj.gene_id]; if (!c2) return;
        var score = 0;
        if (gi.subgenome === gj.subgenome) score += 1000;
        score += 500 - Math.min(Math.abs(c1.x - c2.x), 500);
        pairs.push({ gi: gi, gj: gj, c1: c1, c2: c2, score: score });
      });
    });
    pairs.sort(function (a, b) { return b.score - a.score; });
    for (var k = 0; k < pairs.length && linksThisPair < maxPerPair; k++) {
      var p = pairs[k];
      var color = SUB_COLORS[p.gi.subgenome] || SUB_COLORS.Other;
      var midY = (p.c1.y + p.c2.y) / 2;
      parts.push('<path d="M' + p.c1.x + ',' + p.c1.y + ' C' + p.c1.x + ',' + midY + ' ' +
        p.c2.x + ',' + midY + ' ' + p.c2.x + ',' + p.c2.y +
        '" stroke="' + color + '" stroke-width="0.4" fill="none" opacity="0.15"/>');
      linksThisPair++;
    }
  }

  // ---- Bars, blocks, labels ----
  chrNames.forEach(function (chr, ci) {
    var genes = byChr[chr], span = chrSpans[chr], ty = trackTop(ci), cy = trackCY(ci);
    var sub = getChrSub(genes);
    var labelColor = SUB_COLORS[sub] || "#333";

    var minMb = span.min / 1e6, maxMb = span.max / 1e6;
    var intervalText;
    if (span.len >= 5e5) intervalText = minMb.toFixed(1) + " - " + maxMb.toFixed(1) + " Mb";
    else if (span.len >= 500) intervalText = (span.min / 1e3).toFixed(1) + " - " + (span.max / 1e3).toFixed(1) + " Kb";
    else intervalText = Math.round(span.min) + " - " + Math.round(span.max) + " bp";

    parts.push('<text x="' + (LEFT_W - 16) + '" y="' + (ty + 18) +
      '" text-anchor="end" font-size="12" font-family="Consolas,monospace" fill="' + labelColor + '" font-weight="bold">' +
      escapeHtml(chr) + '</text>');
    parts.push('<text x="' + (LEFT_W - 16) + '" y="' + (ty + 34) +
      '" text-anchor="end" font-size="9.5" font-family="Consolas,monospace" fill="#999">' +
      escapeHtml(intervalText) + '</text>');

    var barY = ty + TRACK_H - 6;
    parts.push('<rect x="' + LEFT_W + '" y="' + (barY - 1) + '" width="' + CHART_W + '" height="3" fill="#d0d0d0" rx="1"/>');

    genes.forEach(function (p) {
      var coord = geneCoords[p.gene_id]; if (!coord) return;
      var gx = coord.x, psub = p.subgenome || "Other", color = SUB_COLORS[psub] || SUB_COLORS.Other;
      var gw = Math.max(5, CHART_W * 0.0045), blockY = barY - BAR_H;
      parts.push('<rect x="' + (gx - gw / 2) + '" y="' + blockY + '" width="' + gw +
        '" height="' + BAR_H + '" fill="' + color + '" rx="1.5" opacity="0.92"><title>' +
        escapeHtml(coord.label) + '</title></rect>');
      var geneName = firstToken(coord.label || "");
      var shortName = geneName.length > 20 ? geneName.substring(0, 19) + "…" : geneName;
      parts.push('<text x="' + gx + '" y="' + (blockY - 4) +
        '" fill="' + color + '" font-size="8.5" font-family="Consolas,monospace" text-anchor="start"' +
        ' transform="rotate(-45,' + gx + ',' + (blockY - 4) + ')">' + escapeHtml(shortName) + '</text>');
    });
  });

  svg.innerHTML = parts.join("");
  syntenyZoom = 1; svg.style.transform = "scale(1)";
}

function zoomSynteny(factor) {
  syntenyZoom = Math.max(0.2, Math.min(syntenyZoom * factor, 5));
  document.getElementById("syntenySvg").style.transform = "scale(" + syntenyZoom + ")";
}
function resetSyntenyZoom() { syntenyZoom = 1; document.getElementById("syntenySvg").style.transform = "scale(1)"; }
function downloadSynteny() {
  var svgEl = document.getElementById("syntenySvg");
  var clone = svgEl.cloneNode(true);
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  var data = new XMLSerializer().serializeToString(clone);
  var blob = new Blob(['<?xml version="1.0" encoding="UTF-8"?>' + data], { type: "image/svg+xml" });
  var url = URL.createObjectURL(blob);
  var a = document.createElement("a"); a.href = url; a.download = (currentOG || "synteny") + ".synteny.svg"; a.click();
  URL.revokeObjectURL(url);
}

function chrSorter(a, b) {
  function parts(s) {
    var m = s.match(/^([^0-9]*?)(\d+)(.*)$/);
    if (m) return [m[1], parseInt(m[2], 10), m[3]];
    return [s, 0, ""];
  }
  var pa = parts(a), pb = parts(b);
  if (pa[0] !== pb[0]) return pa[0].localeCompare(pb[0]);
  if (pa[1] !== pb[1]) return pa[1] - pb[1];
  return pa[2].localeCompare(pb[2]);
}
function getChrSub(genes) {
  var counts = { A: 0, B: 0, D: 0, Other: 0 };
  genes.forEach(function (g) { var s = g.subgenome || "Other"; counts[s] = (counts[s] || 0) + 1; });
  var best = "Other", bestN = -1;
  ["A", "B", "D", "Other"].forEach(function (k) { if (counts[k] > bestN) { bestN = counts[k]; best = k; } });
  return best;
}

/* ---- Utils ---- */
function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
