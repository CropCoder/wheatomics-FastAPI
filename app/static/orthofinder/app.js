let currentGenes = [];
let currentQuery = "";
let treeZoom = 1;

document.addEventListener("DOMContentLoaded", function () {
  loadSiteFrame();
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

function loadSiteFrame() {
  fetch("/header.html").then(function (r) { return r.text(); }).then(function (h) {
    document.getElementById("siteHeader").innerHTML = h;
  }).catch(function () {});
  fetch("/footer.html").then(function (r) { return r.text(); }).then(function (f) {
    document.getElementById("siteFooter").innerHTML = f;
  }).catch(function () {});
}

async function searchProtein(q) {
  currentQuery = q;
  var msg = document.getElementById("message");
  var result = document.getElementById("result");
  msg.textContent = "Loading...";
  result.style.display = "none";

  try {
    var res = await fetch("/api/orthofinder/search?q=" + encodeURIComponent(q));
    var data = await res.json();
    if (!res.ok || !data.success) {
      msg.textContent = data.detail || data.error || "Server error: " + res.status;
      return;
    }
    msg.textContent = "";
    result.style.display = "block";
    currentGenes = data.data.genes || [];
    document.getElementById("ogTitle").textContent =
      data.data.orthogroup + " | Query: " + data.data.query + " | Members: " + data.data.gene_count;
    document.getElementById("downloadTree").href =
      "/api/orthofinder/download?og=" + encodeURIComponent(data.data.orthogroup) + "&type=tree";
    document.getElementById("downloadAlignment").href =
      "/api/orthofinder/download?og=" + encodeURIComponent(data.data.orthogroup) + "&type=alignment";
    document.getElementById("geneFilter").value = "";
    renderGeneList();
    renderAlignment(data.data.alignment, data.data.sequence_map || {});
    renderTree(data.data.tree, data.data.query);
  } catch (e) {
    msg.textContent = "Request failed: " + e.message;
  }
}

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

function renderAlignment(fasta, seqMap) {
  var box = document.getElementById("alignmentBox");
  if (!fasta) {
    box.textContent = "Alignment file was not found for this orthogroup.";
    return;
  }
  var lines = fasta.split(/\r?\n/);
  var html = "";
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    if (line.startsWith(">")) {
      var shortId = line.substring(1).trim();
      var realId = seqMap[shortId] || shortId;
      html += '<span class="aa-header">&gt;' + escapeHtml(shortId) + " | " + escapeHtml(realId) + "</span>\n";
    } else {
      html += escapeHtml(line)
        .replaceAll("-", '<span class="aa-gap">-</span>')
        .replaceAll("*", '<span class="aa-stop">*</span>') + "\n";
    }
  }
  box.innerHTML = html;
}

function parseNewick(newick) {
  var index = 0;
  function skipSpace() { while (/\s/.test(newick[index])) index++; }
  function readName() {
    skipSpace();
    var start = index;
    while (index < newick.length && !["(", ")", ",", ":", ";"].includes(newick[index])) index++;
    return newick.slice(start, index).trim();
  }
  function readLength() {
    skipSpace();
    if (newick[index] !== ":") return 0;
    index++;
    skipSpace();
    var start = index;
    while (index < newick.length && !["(", ")", ",", ":", ";"].includes(newick[index])) index++;
    var v = parseFloat(newick.slice(start, index));
    return Number.isFinite(v) ? v : 0;
  }
  function parseNode() {
    skipSpace();
    var node = { name: "", length: 0, children: [] };
    if (newick[index] === "(") {
      index++;
      while (true) {
        node.children.push(parseNode());
        skipSpace();
        if (newick[index] === ",") { index++; continue; }
        if (newick[index] === ")") { index++; break; }
        break;
      }
      node.name = readName();
      node.length = readLength();
    } else {
      node.name = readName();
      node.length = readLength();
    }
    return node;
  }
  return parseNode();
}

function layoutTree(root) {
  var leaves = [];
  var maxDistance = 0;
  function setDistance(node, dist) {
    node.dist = dist;
    maxDistance = Math.max(maxDistance, dist);
    if (!node.children || node.children.length === 0) {
      leaves.push(node);
      return;
    }
    for (var i = 0; i < node.children.length; i++)
      setDistance(node.children[i], dist + Math.max(node.children[i].length || 0, 0.000001));
  }
  setDistance(root, 0);
  leaves.forEach(function (leaf, i) { leaf.y = 30 + i * 22; });
  function setInternalY(node) {
    if (!node.children || node.children.length === 0) return node.y;
    node.children.forEach(setInternalY);
    node.y = node.children.reduce(function (s, c) { return s + c.y; }, 0) / node.children.length;
    return node.y;
  }
  setInternalY(root);
  return { leaves: leaves, maxDistance: maxDistance };
}

function renderTree(newick, query) {
  var svg = document.getElementById("treeSvg");
  svg.innerHTML = "";
  treeZoom = 1;
  svg.style.transform = "scale(1)";
  if (!newick) {
    svg.innerHTML = "<text x='20' y='30'>Tree file was not found for this orthogroup.</text>";
    return;
  }
  var root;
  try { root = parseNewick(newick.trim()); }
  catch (e) {
    svg.innerHTML = "<text x='20' y='30'>Failed to parse Newick tree.</text>";
    return;
  }
  var layout = layoutTree(root);
  var leaves = layout.leaves;
  var maxDistance = layout.maxDistance;
  var labelMax = Math.max.apply(null, leaves.map(function (x) { return (x.name || "").length; }));
  var height = Math.max(650, leaves.length * 22 + 60);
  var treeWidth = 900;
  var width = Math.max(1300, treeWidth + labelMax * 8 + 100);
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
  var xScale = function (d) { return 40 + (maxDistance > 0 ? d / maxDistance : 0) * treeWidth; };
  function addLine(x1, y1, x2, y2) {
    var l = document.createElementNS("http://www.w3.org/2000/svg", "line");
    l.setAttribute("x1", x1);
    l.setAttribute("y1", y1);
    l.setAttribute("x2", x2);
    l.setAttribute("y2", y2);
    l.setAttribute("stroke", "#333");
    l.setAttribute("stroke-width", "1.1");
    svg.appendChild(l);
  }
  function addText(x, y, content, isHit) {
    var t = document.createElementNS("http://www.w3.org/2000/svg", "text");
    t.setAttribute("x", x);
    t.setAttribute("y", y);
    t.setAttribute("class", isHit ? "tree-label highlight" : "tree-label");
    t.textContent = content || "";
    svg.appendChild(t);
  }
  function draw(node) {
    var x = xScale(node.dist);
    if (!node.children || node.children.length === 0) {
      var isHit = node.name && node.name.includes(query);
      addText(x + 6, node.y + 4, node.name, isHit);
      return;
    }
    var ys = node.children.map(function (c) { return c.y; });
    addLine(x, Math.min.apply(null, ys), x, Math.max.apply(null, ys));
    for (var i = 0; i < node.children.length; i++) {
      var child = node.children[i];
      var cx = xScale(child.dist);
      addLine(x, child.y, cx, child.y);
      draw(child);
    }
  }
  draw(root);
}

function zoomTree(factor) {
  treeZoom *= factor;
  treeZoom = Math.max(0.3, Math.min(treeZoom, 4));
  document.getElementById("treeSvg").style.transform = "scale(" + treeZoom + ")";
}

function resetTreeZoom() {
  treeZoom = 1;
  document.getElementById("treeSvg").style.transform = "scale(1)";
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
