let currentOG = "";
let syntenyZoom = 1;
let treeZoom = 1;
let treeDisplayError = "";
let currentTreeLeafCount = 0;
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

const SUB_COLORS = {
  A: "#d73027",
  B: "#4575b4",
  D: "#1a9850",
  Other: "#777777"
};

document.addEventListener("DOMContentLoaded", () => {
  loadSpeciesCatalog();

  document.getElementById("searchForm").addEventListener("submit", e => {
    e.preventDefault();

    const q = document.getElementById("proteinInput").value.trim();
    if (!q) return;

    const url = new URL(window.location.href);
    url.searchParams.set("q", q);
    window.history.pushState({}, "", url);

    searchProtein(q);
  });

  const q = new URLSearchParams(window.location.search).get("q");

  if (q) {
    document.getElementById("proteinInput").value = q;
    searchProtein(q);
  }
});

async function loadSiteFrame() {
  await loadFragment(
    "/header.html",
    "siteHeader",
    ["home_header", "header-tabs"]
  );

  await loadFragment(
    "/footer.html",
    "siteFooter",
    ["home_footer"]
  );
}

async function loadFragment(url, targetId, wantedIds) {
  const target = document.getElementById(targetId);

  if (!target) return;

  try {
    const res = await fetch(url, {
      cache: "no-store"
    });

    const html = await res.text();
    const doc = new DOMParser().parseFromString(html, "text/html");
    const nodes = [];

    wantedIds.forEach(id => {
      const el = doc.getElementById(id);

      if (el) {
        nodes.push(el.outerHTML);
      }
    });

    target.innerHTML = nodes.length
      ? nodes.join("\n")
      : html;

    target.querySelectorAll("script").forEach(el => el.remove());

    target
      .querySelectorAll("img[src*='clustrmaps']")
      .forEach(img => {
        img.onerror = function () {
          this.style.display = "none";
        };
      });
  } catch (e) {
    target.innerHTML = "";
  }
}

/* =================================================================
   Species catalog
   ================================================================= */

async function loadSpeciesCatalog() {
  try {
    const res = await fetch(
      "/api/orthofinder/api.php?action=species_catalog&_=" + Date.now(),
      {
        cache: "no-store"
      }
    );

    const data = await res.json();

    if (!data.error && data.species) {
      speciesList = data.species;

      const select = document.getElementById("speciesSelect");

      speciesList.forEach(function (species) {
        const option = document.createElement("option");

        option.value = species;
        option.textContent = species;

        select.appendChild(option);
      });
    }
  } catch (e) {
    console.warn("Failed to load species catalog:", e);
  }
  const speciesSel = document.getElementById("speciesSelect");
  speciesSel.addEventListener("change", function () {
    const species = this.value;
    const input = document.getElementById("proteinInput");
    if (species) {
      input.placeholder = "Type gene ID for " + species + "...";
    } else {
      input.placeholder = "Example: TraesAK58CH1A01G123400.1";
    }
  });
}

/* =================================================================
   Main search
   ================================================================= */

async function searchProtein(q) {
  const message = document.getElementById("message");
  const result = document.getElementById("result");

  message.textContent = "Loading...";
  result.style.display = "none";

  try {
    const response = await fetch(
      `/api/orthofinder/api.php?q=${encodeURIComponent(q)}&_=${Date.now()}`,
      {
        cache: "no-store"
      }
    );

    const text = await response.text();
    let data;

    try {
      data = JSON.parse(text);
    } catch (e) {
      message.textContent =
        "Invalid server response: " +
        text.slice(0, 300);

      return;
    }

    if (!response.ok || data.error) {
      message.textContent =
        data.detail ||
        data.error ||
        "Server error.";

      return;
    }

    currentOG = data.orthogroup || "";
    currentTree = data.tree || "";
    currentLabelMap = data.tree_label_map || {};

    currentCluster =
      data.query_cluster === null ||
      data.query_cluster === undefined
        ? null
        : Number(data.query_cluster);

    currentTreeLeafCount =
      Number(data.tree_leaf_count || 0);

    currentClusterTree = "";
    currentParsedTree = null;
    currentPreparedTree = null;
    treeDisplayError = "";

    clusterGeneSet = {};

    (data.cluster_genes || []).forEach(function (gene) {
      addClusterGeneKey(gene);
    });

    message.textContent = "";
    result.style.display = "block";

    document.getElementById("ogTitle").textContent =
      `${data.orthogroup} | Query: ${data.query} | OG members: ${data.gene_count}`;

    document.getElementById("downloadTree").href =
      `/api/orthofinder/download?og=${encodeURIComponent(data.orthogroup)}` +
      `&type=tree`;

    document.getElementById("downloadAlignment").href =
      `/api/orthofinder/download?og=${encodeURIComponent(data.orthogroup)}` +
      `&type=alignment`;

    const badge = document.getElementById("clusterBadge");

    if (currentCluster !== null && currentCluster > 0) {
      badge.textContent =
        "Cluster " + currentCluster;

      badge.className =
        "cluster-badge cluster-badge-" +
        currentCluster;

      badge.style.display = "";
    } else {
      badge.style.display = "none";
    }

    const downloadClusterTree =
      document.getElementById("downloadClusterTree");

    if (
      currentCluster !== null &&
      currentCluster > 0 &&
      data.query
    ) {
      downloadClusterTree.href =
        `/api/orthofinder/download?og=${encodeURIComponent(data.orthogroup)}` +
        `&type=tree` +
        `&cluster=${currentCluster}`;

      downloadClusterTree.style.display = "";
    } else {
      downloadClusterTree.style.display = "none";
    }

    const treeClusterLabel =
      document.getElementById("treeClusterLabel");

    if (
      currentCluster !== null &&
      currentCluster > 0
    ) {
      const expectedClusterLeaves =
        Number(data.cluster_gene_count || 0);

      const selectedTree =
        selectClusterTree(
          data,
          expectedClusterLeaves
        );

      currentClusterTree =
        selectedTree.tree;

      treeDisplayError =
        selectedTree.error;

      document.getElementById("treeHeading").textContent =
        "Cluster " +
        currentCluster +
        " Gene Tree";

      treeClusterLabel.style.display = "";

      if (selectedTree.tree) {
        treeClusterLabel.textContent =
          "Showing " +
          selectedTree.leafCount +
          " genes from cluster " +
          currentCluster +
          " (full OG has " +
          data.gene_count +
          " genes)";

        treeClusterLabel.title =
          "Tree source: " +
          selectedTree.source;

        currentParsedTree =
          parseNewick(
            selectedTree.tree.trim()
          );
      } else {
        treeClusterLabel.textContent =
          "Cluster " +
          currentCluster +
          " contains " +
          expectedClusterLeaves +
          " genes, but a matching pruned tree could not be constructed.";

        treeClusterLabel.title = "";
        currentParsedTree = null;
      }

      if (data.debug_prune) {
        console.log(
          "DEBUG prune:",
          data.debug_prune
        );
      }
    } else {
      document.getElementById("treeHeading").textContent =
        "Gene Tree";

      treeClusterLabel.style.display =
        "none";

      currentParsedTree =
        currentTree
          ? parseNewick(currentTree.trim())
          : null;
    }

    currentPreparedTree = null;

    renderMembers(
      data.sub_counts || {}
    );

    renderTree();
    loadAndRenderSynteny();
  } catch (e) {
    message.textContent =
      "Invalid server response: " +
      e.message;
  }
}

/* =================================================================
   Orthogroup members
   ================================================================= */

function renderMembers(counts) {
  document.getElementById("geneList").innerHTML =
    `<div class="sub-summary">` +
    `${subButton("A", counts.A || 0)}` +
    `${subButton("B", counts.B || 0)}` +
    `${subButton("D", counts.D || 0)}` +
    `${subButton("Other", counts.Other || 0)}` +
    `</div>` +
    `<div id="memberSelectBox"></div>` +
    `<div id="memberDetail"></div>`;
}

function subButton(subgenome, count) {
  const label =
    subgenome === "Other"
      ? "Other"
      : subgenome + "_subgenome";

  return (
    `<button class="sub-btn sub-${subgenome}" ` +
    `onclick="showGenomeSelector('${subgenome}')">` +
    `${label}: ${count}` +
    `</button>`
  );
}

async function showGenomeSelector(subgenome) {
  const selectBox =
    document.getElementById("memberSelectBox");

  const detail =
    document.getElementById("memberDetail");

  selectBox.innerHTML = "Loading...";
  detail.innerHTML = "";

  try {
    const response = await fetch(
      `/api/orthofinder/api.php?action=members` +
      `&og=${encodeURIComponent(currentOG)}` +
      `&sub=${encodeURIComponent(subgenome)}` +
      `&_=${Date.now()}`,
      {
        cache: "no-store"
      }
    );

    const data = await response.json();
    const items = data.items || {};
    const types = Object.keys(items).sort();

    const options = types.map(function (type) {
      return (
        `<option value="${escapeHtml(type)}">` +
        `${escapeHtml(type)} (${items[type].length})` +
        `</option>`
      );
    }).join("");

    selectBox.innerHTML =
      `<select id="genomeSelect" ` +
      `onchange='showSelectedGenome(${JSON.stringify(items)})'>` +
      `<option value="">Select a genome...</option>` +
      options +
      `</select>`;
  } catch (e) {
    selectBox.innerHTML =
      "Failed to load orthogroup members.";
  }
}

function showSelectedGenome(items) {
  const select =
    document.getElementById("genomeSelect");

  const detail =
    document.getElementById("memberDetail");

  const value = select.value;

  if (!value || !items[value]) {
    detail.innerHTML = "";
    return;
  }

  detail.innerHTML =
    `<div class="gene-detail-list">` +
    items[value].map(function (gene) {
      return (
        `<div>` +
        `${escapeHtml(gene)} ` +
        `${escapeHtml(value)}` +
        `</div>`
      );
    }).join("") +
    `</div>`;
}

/* =================================================================
   Newick parser
   ================================================================= */

function parseNewick(newick) {
  let index = 0;

  function skipWhitespace() {
    while (
      index < newick.length &&
      /\s/.test(newick[index])
    ) {
      index++;
    }
  }

  function readName() {
    skipWhitespace();

    if (index >= newick.length) {
      return "";
    }

    if (
      newick[index] === "'" ||
      newick[index] === '"'
    ) {
      const quote = newick[index++];
      const start = index;

      while (
        index < newick.length &&
        newick[index] !== quote
      ) {
        index++;
      }

      const name =
        newick.slice(start, index).trim();

      if (index < newick.length) {
        index++;
      }

      return cleanId(name);
    }

    const start = index;

    while (
      index < newick.length &&
      !["(", ")", ",", ":", ";"].includes(
        newick[index]
      )
    ) {
      index++;
    }

    return cleanId(
      newick.slice(start, index)
    );
  }

  function readLength() {
    skipWhitespace();

    if (newick[index] !== ":") {
      return 0;
    }

    index++;

    const start = index;

    while (
      index < newick.length &&
      !["(", ")", ",", ":", ";"].includes(
        newick[index]
      )
    ) {
      index++;
    }

    const value =
      parseFloat(
        newick.slice(start, index)
      );

    return Number.isFinite(value)
      ? value
      : 0;
  }

  function readNode() {
    skipWhitespace();

    const node = {
      name: "",
      length: 0,
      children: []
    };

    if (newick[index] === "(") {
      index++;

      while (index < newick.length) {
        node.children.push(
          readNode()
        );

        skipWhitespace();

        if (newick[index] === ",") {
          index++;
          continue;
        }

        if (newick[index] === ")") {
          index++;
          break;
        }

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

  return readNode();
}

function cleanId(value) {
  return String(value || "")
    .trim()
    .replace(/^['"]|['"]$/g, "");
}

function firstToken(value) {
  return cleanId(
    String(value || "").split(/\s+/)[0]
  );
}

function withoutVersion(id) {
  return cleanId(id).replace(/\.\d+$/, "");
}

function getTreeInfo(name) {
  const key = firstToken(name);

  if (currentLabelMap[key]) {
    return currentLabelMap[key];
  }

  if (currentLabelMap[name]) {
    return currentLabelMap[name];
  }

  return {
    full_label: key || name,
    gene_id: key || name,
    subgenome:
      inferSubFromId(key || name)
  };
}

function inferSubFromId(id) {
  const value = String(id || "");

  if (
    /(^|_)A(_|$)/i.test(value) ||
    /\dA\d/i.test(value)
  ) {
    return "A";
  }

  if (
    /(^|_)B(_|$)/i.test(value) ||
    /\dB\d/i.test(value)
  ) {
    return "B";
  }

  if (
    /(^|_)D(_|$)/i.test(value) ||
    /\dD\d/i.test(value)
  ) {
    return "D";
  }

  return "Other";
}

function normalizeSub(subgenome) {
  return (
    subgenome === "A" ||
    subgenome === "B" ||
    subgenome === "D"
  )
    ? subgenome
    : "Other";
}

function dominantSub(counts) {
  let best = "Other";
  let bestCount = -1;

  ["A", "B", "D", "Other"].forEach(function (key) {
    const value = counts[key] || 0;

    if (value > bestCount) {
      bestCount = value;
      best = key;
    }
  });

  return best;
}

/* =================================================================
   Cluster tree validation and fallback pruning
   ================================================================= */

function addClusterGeneKey(id) {
  const key = firstToken(id);

  if (!key) return;

  clusterGeneSet[key] = true;

  const noVersion =
    withoutVersion(key);

  if (noVersion) {
    clusterGeneSet[noVersion] = true;
  }
}

function treeLeafCandidates(name) {
  const leaf = firstToken(name);
  const info = getTreeInfo(leaf) || {};

  const candidates = [
    leaf,
    info.short_id,
    info.gene_id,
    info.raw_id
  ];

  const unique = [];
  const seen = {};

  candidates.forEach(function (value) {
    const key = firstToken(value || "");

    if (!key) return;

    [
      key,
      withoutVersion(key)
    ].forEach(function (candidate) {
      if (
        candidate &&
        !seen[candidate]
      ) {
        seen[candidate] = true;
        unique.push(candidate);
      }
    });
  });

  return unique;
}

function isClusterTreeLeaf(name) {
  const candidates =
    treeLeafCandidates(name);

  for (
    let index = 0;
    index < candidates.length;
    index++
  ) {
    if (
      clusterGeneSet[candidates[index]]
    ) {
      return true;
    }
  }

  return false;
}

function countTreeLeaves(node) {
  if (!node) return 0;

  if (
    !node.children ||
    node.children.length === 0
  ) {
    return node.name ? 1 : 0;
  }

  return node.children.reduce(
    function (sum, child) {
      return (
        sum +
        countTreeLeaves(child)
      );
    },
    0
  );
}

function cloneTreeNode(node) {
  return {
    name:
      node && node.name
        ? node.name
        : "",

    length:
      node &&
      Number.isFinite(Number(node.length))
        ? Number(node.length)
        : 0,

    children:
      node && node.children
        ? node.children.map(cloneTreeNode)
        : []
  };
}

function pruneParsedTreeForCluster(
  node,
  isRoot
) {
  if (!node) return null;

  if (
    !node.children ||
    node.children.length === 0
  ) {
    return isClusterTreeLeaf(node.name)
      ? cloneTreeNode(node)
      : null;
  }

  const children = [];

  node.children.forEach(function (child) {
    const kept =
      pruneParsedTreeForCluster(
        child,
        false
      );

    if (kept) {
      children.push(kept);
    }
  });

  if (children.length === 0) {
    return null;
  }

  if (
    children.length === 1 &&
    !isRoot
  ) {
    const onlyChild = children[0];

    onlyChild.length =
      Number(onlyChild.length || 0) +
      Number(node.length || 0);

    return onlyChild;
  }

  return {
    name: node.name || "",
    length: Number(node.length || 0),
    children: children
  };
}

function newickName(name) {
  const value = String(name || "");

  if (value === "") {
    return "";
  }

  if (
    /^[^\s(),:;\[\]'\"]+$/.test(value)
  ) {
    return value;
  }

  return (
    "'" +
    value.replace(/'/g, "''") +
    "'"
  );
}

function serializeNewickNode(
  node,
  isRoot
) {
  if (!node) return "";

  let output = "";

  if (
    node.children &&
    node.children.length
  ) {
    output +=
      "(" +
      node.children.map(function (child) {
        return serializeNewickNode(
          child,
          false
        );
      }).join(",") +
      ")";

    output +=
      newickName(node.name || "");
  } else {
    output +=
      newickName(node.name || "");
  }

  const length =
    Number(node.length || 0);

  if (
    !isRoot &&
    Number.isFinite(length) &&
    length > 0
  ) {
    output +=
      ":" +
      String(
        Number(length.toPrecision(10))
      );
  }

  return output;
}

function selectClusterTree(
  data,
  expectedLeaves
) {
  const apiTree =
    String(data.cluster_tree || "").trim();

  if (apiTree) {
    try {
      const apiParsed =
        parseNewick(apiTree);

      const apiCount =
        countTreeLeaves(apiParsed);

      if (apiCount === expectedLeaves) {
        return {
          tree:
            apiTree.endsWith(";")
              ? apiTree
              : apiTree + ";",

          leafCount: apiCount,
          source: "server-pruned tree",
          error: ""
        };
      }

      console.warn(
        "Server cluster tree leaf mismatch:",
        {
          expected: expectedLeaves,
          actual: apiCount,
          debug: data.debug_prune || null
        }
      );
    } catch (e) {
      console.warn(
        "Server cluster tree could not be parsed:",
        e
      );
    }
  }

  if (
    currentTree &&
    expectedLeaves > 0
  ) {
    try {
      const fullParsed =
        parseNewick(
          currentTree.trim()
        );

      const pruned =
        pruneParsedTreeForCluster(
          fullParsed,
          true
        );

      const prunedCount =
        countTreeLeaves(pruned);

      if (
        pruned &&
        prunedCount === expectedLeaves
      ) {
        return {
          tree:
            serializeNewickNode(
              pruned,
              true
            ) + ";",

          leafCount: prunedCount,
          source: "browser fallback pruning",
          error: ""
        };
      }

      return {
        tree: "",
        leafCount: prunedCount,
        source: "none",

        error:
          "Cluster tree leaf mismatch: expected " +
          expectedLeaves +
          ", matched " +
          prunedCount +
          ". The full OG tree is intentionally not displayed."
      };
    } catch (e) {
      return {
        tree: "",
        leafCount: 0,
        source: "none",

        error:
          "Cluster tree pruning failed: " +
          e.message
      };
    }
  }

  return {
    tree: "",
    leafCount: 0,
    source: "none",

    error:
      "Cluster tree was not returned by the server."
  };
}

/* =================================================================
   Prepared tree
   ================================================================= */

function getPreparedTree() {
  if (currentPreparedTree) {
    return currentPreparedTree;
  }

  const root =
    currentParsedTree ||
    (
      !currentCluster &&
      currentTree
        ? parseNewick(currentTree.trim())
        : null
    );

  if (!root) return null;

  const leaves = [];
  let maxDepth = 0;

  function walk(node, depth) {
    node.depth = depth;

    maxDepth =
      Math.max(maxDepth, depth);

    if (
      !node.children ||
      node.children.length === 0
    ) {
      const key =
        firstToken(node.name);

      const info =
        getTreeInfo(key);

      node.rawName = key;

      node.displayLabel =
        info.full_label ||
        info.label ||
        info.gene_id ||
        key;

      node.sub =
        normalizeSub(
          info.subgenome ||
          inferSubFromId(
            node.displayLabel ||
            key
          )
        );

      node.order =
        leaves.length;

      node.counts = {
        A: 0,
        B: 0,
        D: 0,
        Other: 0
      };

      node.counts[node.sub]++;
      node.numLeaves = 1;

      leaves.push(node);

      return node.counts;
    }

    node.counts = {
      A: 0,
      B: 0,
      D: 0,
      Other: 0
    };

    node.numLeaves = 0;

    node.children.forEach(function (child) {
      const childCounts =
        walk(child, depth + 1);

      ["A", "B", "D", "Other"].forEach(
        function (key) {
          node.counts[key] +=
            childCounts[key];
        }
      );

      node.numLeaves +=
        child.numLeaves;
    });

    node.sub =
      dominantSub(node.counts);

    return node.counts;
  }

  walk(root, 0);

  function calculateBounds(node) {
    if (
      !node.children ||
      node.children.length === 0
    ) {
      node.minOrder = node.order;
      node.maxOrder = node.order;
      node.meanOrder = node.order;

      return [
        node.minOrder,
        node.maxOrder,
        node.meanOrder,
        1
      ];
    }

    let minimum = Infinity;
    let maximum = -Infinity;
    let sum = 0;
    let count = 0;

    node.children.forEach(function (child) {
      const bounds =
        calculateBounds(child);

      minimum =
        Math.min(minimum, bounds[0]);

      maximum =
        Math.max(maximum, bounds[1]);

      sum += bounds[2] * bounds[3];
      count += bounds[3];
    });

    node.minOrder = minimum;
    node.maxOrder = maximum;
    node.meanOrder = sum / count;

    return [
      minimum,
      maximum,
      node.meanOrder,
      count
    ];
  }

  calculateBounds(root);

  currentPreparedTree = {
    root: root,
    leaves: leaves,
    maxDepth: maxDepth
  };

  return currentPreparedTree;
}

function clearSvg(svg) {
  svg.innerHTML = "";

  if (svg.id === "treeSvg") {
    treeZoom = 1;
    svg.style.transform = "scale(1)";
  } else {
    syntenyZoom = 1;
    svg.style.transform = "scale(1)";
  }
}

/* =================================================================
   Tree rendering
   ================================================================= */

function setTreeMode(mode) {
  treeMode = mode;
  renderTree();
}

function renderTree() {
  if (treeMode === "circular") {
    renderTreeCircular();
  } else {
    renderTreeRectangular();
  }
}

/* -----------------------------------------------------------------
   Rectangular tree
   ----------------------------------------------------------------- */

function renderTreeRectangular() {
  const svg =
    document.getElementById("treeSvg");

  clearSvg(svg);

  if (treeDisplayError) {
    svg.setAttribute("width", "1100");
    svg.setAttribute("height", "100");
    svg.setAttribute(
      "viewBox",
      "0 0 1100 100"
    );

    svg.innerHTML =
      '<text x="20" y="38" ' +
      'font-size="14" fill="#b00020">' +
      escapeHtml(treeDisplayError) +
      "</text>";

    return;
  }

  if (!currentParsedTree) {
    svg.innerHTML =
      "<text x='20' y='30'>" +
      "Tree file was not found." +
      "</text>";

    return;
  }

  const prepared =
    getPreparedTree();

  if (!prepared) return;

  const root = prepared.root;
  const leaves = prepared.leaves;
  const maxDepth = prepared.maxDepth;

  const showLabels =
    leaves.length < 220;

  const rowHeight =
    showLabels ? 24 : 12;

  const top = 42;
  const left = 45;

  const treeRight =
    showLabels ? 690 : 1040;

  const labelX =
    showLabels ? 820 : 1080;

  const width =
    showLabels ? 1900 : 1180;

  const height =
    Math.max(
      720,
      top * 2 +
      leaves.length * rowHeight
    );

  leaves.forEach(function (leaf, index) {
    leaf.y =
      top +
      index * rowHeight;
  });

  function setNodeY(node) {
    if (
      !node.children ||
      node.children.length === 0
    ) {
      return node.y;
    }

    node.children.forEach(setNodeY);

    node.y =
      node.children.reduce(
        function (sum, child) {
          return sum + child.y;
        },
        0
      ) /
      node.children.length;

    return node.y;
  }

  setNodeY(root);

  function xCoordinate(depth) {
    return (
      left +
      (
        maxDepth > 0
          ? depth / maxDepth
          : 0
      ) *
      (treeRight - left)
    );
  }

  svg.setAttribute(
    "width",
    width
  );

  svg.setAttribute(
    "height",
    height
  );

  svg.setAttribute(
    "viewBox",
    `0 0 ${width} ${height}`
  );

  const parts = [];

  function drawNode(node) {
    if (
      !node.children ||
      node.children.length === 0
    ) {
      if (showLabels) {
        const branchEndX =
          xCoordinate(node.depth);

        const label =
          node.displayLabel ||
          node.name;

        parts.push(
          '<g class="tree-leaf">' +
          "<title>" +
          escapeHtml(label) +
          " [" +
          node.sub +
          "_subgenome]" +
          "</title>"
        );

        parts.push(
          lineSvg(
            branchEndX,
            node.y,
            labelX - 12,
            node.y,
            node.sub,
            0.9
          )
        );

        parts.push(
          textSvg(
            labelX,
            node.y + 4,
            label,
            node.sub,
            11,
            true
          )
        );

        parts.push("</g>");
      }

      return;
    }

    const parentX =
      xCoordinate(node.depth);

    const childYValues =
      node.children.map(function (child) {
        return child.y;
      });

    parts.push(
      "<g>" +
      "<title>" +
      node.numLeaves +
      " genes in this clade" +
      "</title>" +
      lineSvg(
        parentX,
        Math.min(...childYValues),
        parentX,
        Math.max(...childYValues),
        node.sub,
        1.6
      ) +
      "</g>"
    );

    node.children.forEach(function (child) {
      parts.push(
        "<g>" +
        "<title>" +
        child.numLeaves +
        " genes in this clade (" +
        child.sub +
        "_subgenome)" +
        "</title>" +
        lineSvg(
          parentX,
          child.y,
          xCoordinate(child.depth),
          child.y,
          child.sub,
          1.6
        ) +
        "</g>"
      );

      drawNode(child);
    });
  }

  drawNode(root);

  svg.innerHTML =
    parts.join("");
}

/* -----------------------------------------------------------------
   Circular tree
   ----------------------------------------------------------------- */

function renderTreeCircular() {
  const svg =
    document.getElementById("treeSvg");

  clearSvg(svg);

  if (treeDisplayError) {
    svg.setAttribute("width", "1100");
    svg.setAttribute("height", "100");
    svg.setAttribute(
      "viewBox",
      "0 0 1100 100"
    );

    svg.innerHTML =
      '<text x="20" y="38" ' +
      'font-size="14" fill="#b00020">' +
      escapeHtml(treeDisplayError) +
      "</text>";

    return;
  }

  if (!currentParsedTree) {
    svg.innerHTML =
      "<text x='20' y='30'>" +
      "Tree file was not found." +
      "</text>";

    return;
  }

  const prepared =
    getPreparedTree();

  if (!prepared) return;

  const root = prepared.root;
  const leaves = prepared.leaves;
  const maxDepth = prepared.maxDepth;

  const showLabels =
    leaves.length < 220;

  const size =
    showLabels
      ? 2200
      : Math.max(
          1000,
          Math.min(
            2800,
            leaves.length * 10
          )
        );

  const centerX = size / 2;
  const centerY = size / 2;

  const radius =
    showLabels
      ? size / 2 - 430
      : size / 2 - 120;

  const labelRadius =
    showLabels
      ? radius + 135
      : radius + 20;

  const innerRadius =
    showLabels ? 18 : 8;

  const leafCount =
    Math.max(1, leaves.length);

  function angleForOrder(order) {
    return (
      2 *
      Math.PI *
      (order + 0.5) /
      leafCount -
      Math.PI / 2
    );
  }

  leaves.forEach(function (leaf) {
    leaf.angle =
      angleForOrder(leaf.order);
  });

  function setNodeAngle(node) {
    if (
      !node.children ||
      node.children.length === 0
    ) {
      return node.angle;
    }

    node.children.forEach(setNodeAngle);

    let sumX = 0;
    let sumY = 0;
    let count = 0;

    node.children.forEach(function (child) {
      const weight =
        child.maxOrder -
        child.minOrder +
        1 || 1;

      sumX +=
        Math.cos(child.angle) *
        weight;

      sumY +=
        Math.sin(child.angle) *
        weight;

      count += weight;
    });

    node.angle =
      count
        ? Math.atan2(
            sumY / count,
            sumX / count
          )
        : 0;

    return node.angle;
  }

  setNodeAngle(root);

  function nodeRadius(node) {
    return (
      innerRadius +
      (
        maxDepth > 0
          ? node.depth / maxDepth
          : 0
      ) *
      (radius - innerRadius)
    );
  }

  function polarToCartesian(r, angle) {
    return {
      x:
        centerX +
        r * Math.cos(angle),

      y:
        centerY +
        r * Math.sin(angle)
    };
  }

  svg.setAttribute(
    "width",
    size
  );

  svg.setAttribute(
    "height",
    size
  );

  svg.setAttribute(
    "viewBox",
    `0 0 ${size} ${size}`
  );

  const parts = [];

  function drawNode(node) {
    const point =
      polarToCartesian(
        nodeRadius(node),
        node.angle
      );

    if (
      !node.children ||
      node.children.length === 0
    ) {
      if (showLabels) {
        const lineEnd =
          polarToCartesian(
            labelRadius - 22,
            node.angle
          );

        const labelPoint =
          polarToCartesian(
            labelRadius,
            node.angle
          );

        const label =
          node.displayLabel ||
          node.name;

        parts.push(
          '<g class="tree-leaf">' +
          "<title>" +
          escapeHtml(label) +
          " [" +
          node.sub +
          "_subgenome]" +
          "</title>" +
          lineSvg(
            point.x,
            point.y,
            lineEnd.x,
            lineEnd.y,
            node.sub,
            0.9
          ) +
          radialTextSvg(
            labelPoint.x,
            labelPoint.y,
            node.angle,
            label,
            node.sub
          ) +
          "</g>"
        );
      }

      return;
    }

    node.children.forEach(function (child) {
      const childPoint =
        polarToCartesian(
          nodeRadius(child),
          child.angle
        );

      parts.push(
        "<g>" +
        "<title>" +
        child.numLeaves +
        " genes in this clade (" +
        child.sub +
        "_subgenome)" +
        "</title>" +
        lineSvg(
          point.x,
          point.y,
          childPoint.x,
          childPoint.y,
          child.sub,
          1.6
        ) +
        "</g>"
      );

      drawNode(child);
    });
  }

  drawNode(root);

  svg.innerHTML =
    parts.join("");
}

/* =================================================================
   SVG tree helpers
   ================================================================= */

function lineSvg(
  x1,
  y1,
  x2,
  y2,
  subgenome,
  width
) {
  const strokeWidth =
    width || 1.6;

  return (
    `<line ` +
    `x1="${x1}" ` +
    `y1="${y1}" ` +
    `x2="${x2}" ` +
    `y2="${y2}" ` +
    `stroke="${SUB_COLORS[subgenome] || SUB_COLORS.Other}" ` +
    `stroke-width="${strokeWidth}" ` +
    `fill="none"/>`
  );
}

function textSvg(
  x,
  y,
  text,
  subgenome,
  size,
  halo
) {
  const extra =
    halo
      ? (
          ` paint-order="stroke"` +
          ` stroke="#fff"` +
          ` stroke-width="5"` +
          ` stroke-linejoin="round"`
        )
      : "";

  return (
    `<text ` +
    `x="${x}" ` +
    `y="${y}" ` +
    `fill="${SUB_COLORS[subgenome] || "#333"}" ` +
    `font-size="${size}"${extra}>` +
    `${escapeHtml(text)}` +
    `</text>`
  );
}

function radialTextSvg(
  x,
  y,
  angle,
  text,
  subgenome
) {
  const degrees =
    angle * 180 / Math.PI;

  const flip =
    degrees > 90 &&
    degrees < 270;

  return (
    `<text ` +
    `x="${x}" ` +
    `y="${y}" ` +
    `fill="${SUB_COLORS[subgenome] || "#333"}" ` +
    `font-size="10" ` +
    `dominant-baseline="middle" ` +
    `paint-order="stroke" ` +
    `stroke="#fff" ` +
    `stroke-width="4" ` +
    `stroke-linejoin="round" ` +
    `text-anchor="${flip ? "end" : "start"}" ` +
    `transform="rotate(${flip ? degrees + 180 : degrees},${x},${y})">` +
    `${escapeHtml(text)}` +
    `</text>`
  );
}

function zoomTree(factor) {
  treeZoom =
    Math.max(
      0.3,
      Math.min(
        treeZoom * factor,
        4
      )
    );

  document.getElementById(
    "treeSvg"
  ).style.transform =
    `scale(${treeZoom})`;
}

function resetTreeZoom() {
  treeZoom = 1;

  document.getElementById(
    "treeSvg"
  ).style.transform =
    "scale(1)";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

/* =================================================================
   Synteny data loading
   ================================================================= */

async function loadAndRenderSynteny() {
  if (!currentOG) return;

  const clusterParameter =
    currentCluster
      ? "&cluster=" + currentCluster
      : "";

  const url =
    "/api/orthofinder/api.php?action=positions" +
    "&og=" +
    encodeURIComponent(currentOG) +
    clusterParameter +
    "&_=" +
    Date.now();

  try {
    const response =
      await fetch(url, {
        cache: "no-store"
      });

    const data =
      await response.json();

    if (data.error) {
      document.getElementById(
        "syntenyBox"
      ).textContent =
        data.error;

      return;
    }

    currentSyntenyData = data;
    renderSynteny(data);
  } catch (e) {
    document.getElementById(
      "syntenyBox"
    ).textContent =
      "Failed to load chromosome positions.";
  }
}

/* =================================================================
   Synteny rendering

   Important rules:
   1. Tracks are sorted from top to bottom.
   2. Only adjacent tracks are connected.
   3. Track 1 connects only to track 2.
   4. Track 2 connects only to track 3.
   5. No track is skipped.
   6. Gene pairs are monotonic by genomic position.
   7. Every gene in both adjacent tracks participates in at least one line.
   ================================================================= */

function renderSynteny(data) {
  const svg =
    document.getElementById("syntenySvg");

  svg.innerHTML = "";

  if (
    !data.positions ||
    data.positions.length === 0
  ) {
    svg.innerHTML =
      "<text x='20' y='30' " +
      "font-size='13' fill='#999'>" +
      "No chromosome position data." +
      "</text>";

    svg.setAttribute(
      "width",
      "900"
    );

    svg.setAttribute(
      "height",
      "60"
    );

    svg.setAttribute(
      "viewBox",
      "0 0 900 60"
    );

    svg.dataset.baseWidth = "900";
    svg.dataset.baseHeight = "60";

    applySyntenyZoom();
    return;
  }

  const positions =
    data.positions.map(
      function (position, index) {
        return Object.assign(
          {},
          position,
          {
            _index: index,

            start:
              Number(
                position.start || 0
              ),

            end:
              Number(
                position.end ||
                position.start ||
                0
              ),

            subgenome:
              normalizeSub(
                position.subgenome ||
                "Other"
              )
          }
        );
      }
    );

  /*
   * Each genome + chromosome pair is one independent track.
   */
  const trackMap = {};

  positions.forEach(function (position) {
    const genome =
      String(
        position.genome ||
        "Unknown"
      );

    const chromosome =
      String(
        position.chromosome ||
        "Unknown"
      );

    const key =
      genome +
      "\u0001" +
      chromosome;

    if (!trackMap[key]) {
      trackMap[key] = {
        key: key,
        genome: genome,
        chromosome: chromosome,
        label:
          genome +
          "_" +
          chromosome,
        genes: []
      };
    }

    trackMap[key].genes.push(
      position
    );
  });

  const tracks =
    Object.keys(trackMap)
      .map(function (key) {
        const track =
          trackMap[key];

        track.genes.sort(
          function (a, b) {
            return (
              a.start - b.start ||
              a.end - b.end ||
              String(a.gene_id).localeCompare(
                String(b.gene_id)
              )
            );
          }
        );

        track.subgenome =
          getChrSub(track.genes);

        return track;
      })
      .sort(trackSorter);

  const LEFT_WIDTH = 230;
  const RIGHT_PADDING = 45;
  const TRACK_HEIGHT = 62;
  const TRACK_GAP = 12;
  const GENE_BAR_HEIGHT = 10;
  const CHART_WIDTH = 900;
  const TOP_PADDING = 34;
  const BOTTOM_PADDING = 46;

  const svgWidth =
    LEFT_WIDTH +
    CHART_WIDTH +
    RIGHT_PADDING;

  const svgHeight =
    TOP_PADDING +
    tracks.length *
      (
        TRACK_HEIGHT +
        TRACK_GAP
      ) +
    BOTTOM_PADDING;

  svg.setAttribute(
    "width",
    String(svgWidth)
  );

  svg.setAttribute(
    "height",
    String(svgHeight)
  );

  svg.setAttribute(
    "viewBox",
    "0 0 " +
    svgWidth +
    " " +
    svgHeight
  );

  svg.dataset.baseWidth =
    String(svgWidth);

  svg.dataset.baseHeight =
    String(svgHeight);

  function trackTop(index) {
    return (
      TOP_PADDING +
      index *
      (
        TRACK_HEIGHT +
        TRACK_GAP
      )
    );
  }

  const coordinateMap =
    new Map();

  const spans =
    new Map();

  tracks.forEach(
    function (track, trackIndex) {
      let minimumStart = Infinity;
      let maximumEnd = -Infinity;

      track.genes.forEach(
        function (gene) {
          minimumStart =
            Math.min(
              minimumStart,
              gene.start
            );

          maximumEnd =
            Math.max(
              maximumEnd,
              gene.end
            );
        }
      );

      if (
        !Number.isFinite(minimumStart)
      ) {
        minimumStart = 0;
      }

      if (
        !Number.isFinite(maximumEnd)
      ) {
        maximumEnd =
          minimumStart + 1;
      }

      const rawLength =
        Math.max(
          1,
          maximumEnd -
          minimumStart
        );

      const padding =
        Math.max(
          rawLength * 0.05,
          5000
        );

      const span = {
        min:
          Math.max(
            0,
            minimumStart -
            padding
          ),

        max:
          maximumEnd +
          padding
      };

      span.length =
        Math.max(
          1,
          span.max -
          span.min
        );

      spans.set(
        track,
        span
      );

      const top =
        trackTop(trackIndex);

      const chromosomeBarY =
        top +
        TRACK_HEIGHT -
        7;

      track.genes.forEach(
        function (gene) {
          const center =
            (
              gene.start +
              gene.end
            ) / 2;

          const fraction =
            Math.max(
              0,
              Math.min(
                1,
                (
                  center -
                  span.min
                ) /
                span.length
              )
            );

          coordinateMap.set(
            gene,
            {
              x:
                LEFT_WIDTH +
                fraction *
                CHART_WIDTH,

              y:
                chromosomeBarY -
                GENE_BAR_HEIGHT / 2,

              barY:
                chromosomeBarY,

              trackIndex:
                trackIndex
            }
          );
        }
      );
    }
  );

  const lineParts = [];
  const featureParts = [];

  /*
   * Strict top-to-bottom adjacency:
   *
   * tracks[0] -> tracks[1]
   * tracks[1] -> tracks[2]
   * tracks[2] -> tracks[3]
   *
   * There are no links from tracks[0] directly to tracks[2].
   */
  for (
    let trackIndex = 0;
    trackIndex < tracks.length - 1;
    trackIndex++
  ) {
    const upperTrack =
      tracks[trackIndex];

    const lowerTrack =
      tracks[trackIndex + 1];

    const pairs =
      buildSequentialGenePairs(
        upperTrack.genes,
        lowerTrack.genes
      );

    pairs.forEach(function (pair) {
      const upperGene =
        upperTrack.genes[
          pair.upperIndex
        ];

      const lowerGene =
        lowerTrack.genes[
          pair.lowerIndex
        ];

      const upperCoordinate =
        coordinateMap.get(
          upperGene
        );

      const lowerCoordinate =
        coordinateMap.get(
          lowerGene
        );

      if (
        !upperCoordinate ||
        !lowerCoordinate
      ) {
        return;
      }

      const startY =
        upperCoordinate.barY + 1;

      const endY =
        lowerCoordinate.barY -
        GENE_BAR_HEIGHT -
        1;

      const middleY =
        (startY + endY) / 2;

      const sourceSubgenome =
        normalizeSub(
          upperGene.subgenome ||
          upperTrack.subgenome
        );

      const targetSubgenome =
        normalizeSub(
          lowerGene.subgenome ||
          lowerTrack.subgenome
        );

      const color =
        sourceSubgenome ===
        targetSubgenome
          ? (
              SUB_COLORS[
                sourceSubgenome
              ] ||
              SUB_COLORS.Other
            )
          : SUB_COLORS.Other;

      lineParts.push(
        '<path d="' +
        "M" +
        upperCoordinate.x +
        "," +
        startY +
        " C" +
        upperCoordinate.x +
        "," +
        middleY +
        " " +
        lowerCoordinate.x +
        "," +
        middleY +
        " " +
        lowerCoordinate.x +
        "," +
        endY +
        '" ' +
        'stroke="' +
        color +
        '" ' +
        'stroke-width="0.75" ' +
        'fill="none" ' +
        'opacity="0.32">' +
        "<title>" +
        escapeHtml(
          String(
            upperGene.gene_id ||
            ""
          )
        ) +
        " → " +
        escapeHtml(
          String(
            lowerGene.gene_id ||
            ""
          )
        ) +
        "</title>" +
        "</path>"
      );
    });
  }

  /*
   * Draw chromosome bars and genes after lines,
   * so gene blocks appear above the connectors.
   */
  tracks.forEach(
    function (track, trackIndex) {
      const span =
        spans.get(track);

      const top =
        trackTop(trackIndex);

      const chromosomeBarY =
        top +
        TRACK_HEIGHT -
        7;

      const labelColor =
        SUB_COLORS[
          track.subgenome
        ] ||
        "#333";

      let intervalText;

      if (
        span.length >= 500000
      ) {
        intervalText =
          (
            span.min /
            1000000
          ).toFixed(1) +
          " - " +
          (
            span.max /
            1000000
          ).toFixed(1) +
          " Mb";
      } else if (
        span.length >= 500
      ) {
        intervalText =
          (
            span.min /
            1000
          ).toFixed(1) +
          " - " +
          (
            span.max /
            1000
          ).toFixed(1) +
          " Kb";
      } else {
        intervalText =
          Math.round(span.min) +
          " - " +
          Math.round(span.max) +
          " bp";
      }

      featureParts.push(
        '<text ' +
        'x="' +
        (LEFT_WIDTH - 16) +
        '" ' +
        'y="' +
        (top + 18) +
        '" ' +
        'text-anchor="end" ' +
        'font-size="12" ' +
        'font-family="Consolas,monospace" ' +
        'fill="' +
        labelColor +
        '" ' +
        'font-weight="bold">' +
        escapeHtml(track.label) +
        "</text>"
      );

      featureParts.push(
        '<text ' +
        'x="' +
        (LEFT_WIDTH - 16) +
        '" ' +
        'y="' +
        (top + 35) +
        '" ' +
        'text-anchor="end" ' +
        'font-size="9.5" ' +
        'font-family="Consolas,monospace" ' +
        'fill="#888">' +
        escapeHtml(intervalText) +
        " · " +
        track.genes.length +
        " genes" +
        "</text>"
      );

      featureParts.push(
        '<rect ' +
        'x="' +
        LEFT_WIDTH +
        '" ' +
        'y="' +
        (chromosomeBarY - 1) +
        '" ' +
        'width="' +
        CHART_WIDTH +
        '" ' +
        'height="3" ' +
        'fill="#d0d0d0" ' +
        'rx="1"/>'
      );

      track.genes.forEach(
        function (gene) {
          const coordinate =
            coordinateMap.get(gene);

          if (!coordinate) return;

          const subgenome =
            normalizeSub(
              gene.subgenome
            );

          const color =
            SUB_COLORS[subgenome] ||
            SUB_COLORS.Other;

          const width =
            Math.max(
              5,
              CHART_WIDTH *
              0.0045
            );

          const blockY =
            chromosomeBarY -
            GENE_BAR_HEIGHT;

          const label =
            gene.label ||
            gene.gene_id ||
            "";

          const geneName =
            firstToken(label);

          const shortName =
            geneName.length > 24
              ? geneName.slice(0, 23) +
                "…"
              : geneName;

          featureParts.push(
            '<rect ' +
            'x="' +
            (
              coordinate.x -
              width / 2
            ) +
            '" ' +
            'y="' +
            blockY +
            '" ' +
            'width="' +
            width +
            '" ' +
            'height="' +
            GENE_BAR_HEIGHT +
            '" ' +
            'fill="' +
            color +
            '" ' +
            'rx="1.5" ' +
            'opacity="0.94">' +
            "<title>" +
            escapeHtml(label) +
            "</title>" +
            "</rect>"
          );

          featureParts.push(
            '<text ' +
            'x="' +
            coordinate.x +
            '" ' +
            'y="' +
            (blockY - 4) +
            '" ' +
            'fill="' +
            color +
            '" ' +
            'font-size="8.5" ' +
            'font-family="Consolas,monospace" ' +
            'text-anchor="start" ' +
            'transform="rotate(-45,' +
            coordinate.x +
            "," +
            (blockY - 4) +
            ')">' +
            escapeHtml(shortName) +
            "</text>"
          );
        }
      );
    }
  );

  svg.innerHTML =
    lineParts.join("") +
    featureParts.join("");

  syntenyZoom = 1;
  applySyntenyZoom();
}

/* =================================================================
   Sequential gene pairing

   The first pass ensures every upper gene is connected.
   The second pass ensures every lower gene is connected.

   Mapping uses positional rank, not every-to-every combinations.
   This prevents random criss-cross connections.
   ================================================================= */

function buildSequentialGenePairs(
  upperGenes,
  lowerGenes
) {
  const upperCount =
    upperGenes.length;

  const lowerCount =
    lowerGenes.length;

  const pairs = [];
  const seen = {};

  if (
    upperCount === 0 ||
    lowerCount === 0
  ) {
    return pairs;
  }

  function addPair(
    upperIndex,
    lowerIndex
  ) {
    upperIndex =
      Math.max(
        0,
        Math.min(
          upperCount - 1,
          upperIndex
        )
      );

    lowerIndex =
      Math.max(
        0,
        Math.min(
          lowerCount - 1,
          lowerIndex
        )
      );

    const key =
      upperIndex +
      ":" +
      lowerIndex;

    if (!seen[key]) {
      seen[key] = true;

      pairs.push({
        upperIndex: upperIndex,
        lowerIndex: lowerIndex
      });
    }
  }

  /*
   * Upper-to-lower pass.
   * Every upper gene obtains one lower match.
   */
  for (
    let upperIndex = 0;
    upperIndex < upperCount;
    upperIndex++
  ) {
    const lowerIndex =
      upperCount === 1
        ? Math.round(
            (lowerCount - 1) / 2
          )
        : Math.round(
            upperIndex *
            (lowerCount - 1) /
            (upperCount - 1)
          );

    addPair(
      upperIndex,
      lowerIndex
    );
  }

  /*
   * Lower-to-upper pass.
   * Every lower gene obtains one upper match.
   */
  for (
    let lowerIndex = 0;
    lowerIndex < lowerCount;
    lowerIndex++
  ) {
    const upperIndex =
      lowerCount === 1
        ? Math.round(
            (upperCount - 1) / 2
          )
        : Math.round(
            lowerIndex *
            (upperCount - 1) /
            (lowerCount - 1)
          );

    addPair(
      upperIndex,
      lowerIndex
    );
  }

  pairs.sort(
    function (a, b) {
      return (
        a.upperIndex -
        b.upperIndex ||
        a.lowerIndex -
        b.lowerIndex
      );
    }
  );

  return pairs;
}

/* =================================================================
   Natural track sorting
   ================================================================= */

function naturalParts(value) {
  return String(value || "")
    .split(/(\d+)/)
    .map(function (part) {
      return /^\d+$/.test(part)
        ? Number(part)
        : part.toLowerCase();
    });
}

function naturalCompare(a, b) {
  const left =
    naturalParts(a);

  const right =
    naturalParts(b);

  const length =
    Math.max(
      left.length,
      right.length
    );

  for (
    let index = 0;
    index < length;
    index++
  ) {
    if (
      left[index] === undefined
    ) {
      return -1;
    }

    if (
      right[index] === undefined
    ) {
      return 1;
    }

    if (
      left[index] === right[index]
    ) {
      continue;
    }

    if (
      typeof left[index] === "number" &&
      typeof right[index] === "number"
    ) {
      return (
        left[index] -
        right[index]
      );
    }

    return String(
      left[index]
    ).localeCompare(
      String(right[index])
    );
  }

  return 0;
}

function trackSorter(a, b) {
  const genomeOrder =
    naturalCompare(
      a.genome,
      b.genome
    );

  if (genomeOrder !== 0) {
    return genomeOrder;
  }

  return naturalCompare(
    a.chromosome,
    b.chromosome
  );
}

/* =================================================================
   Synteny zoom and download
   ================================================================= */

function applySyntenyZoom() {
  const svg =
    document.getElementById(
      "syntenySvg"
    );

  const baseWidth =
    Number(
      svg.dataset.baseWidth ||
      svg.getAttribute("width") ||
      900
    );

  const baseHeight =
    Number(
      svg.dataset.baseHeight ||
      svg.getAttribute("height") ||
      60
    );

  /*
   * Use actual width and height instead of CSS transform.
   * This keeps the scrollable area consistent with the displayed size.
   */
  svg.style.transform = "none";

  svg.style.width =
    (
      baseWidth *
      syntenyZoom
    ) +
    "px";

  svg.style.height =
    (
      baseHeight *
      syntenyZoom
    ) +
    "px";
}

function zoomSynteny(factor) {
  syntenyZoom =
    Math.max(
      0.2,
      Math.min(
        syntenyZoom * factor,
        6
      )
    );

  applySyntenyZoom();
}

function resetSyntenyZoom() {
  syntenyZoom = 1;
  applySyntenyZoom();
}

function downloadSynteny() {
  const svgElement =
    document.getElementById(
      "syntenySvg"
    );

  const clone =
    svgElement.cloneNode(true);

  clone.setAttribute(
    "xmlns",
    "http://www.w3.org/2000/svg"
  );

  clone.style.width = "";
  clone.style.height = "";
  clone.style.transform = "";

  const serialized =
    new XMLSerializer()
      .serializeToString(clone);

  const blob =
    new Blob(
      [
        '<?xml version="1.0" encoding="UTF-8"?>' +
        serialized
      ],
      {
        type: "image/svg+xml"
      }
    );

  const url =
    URL.createObjectURL(blob);

  const link =
    document.createElement("a");

  link.href = url;

  link.download =
    (currentOG || "synteny") +
    ".synteny.svg";

  document.body.appendChild(link);
  link.click();
  link.remove();

  setTimeout(function () {
    URL.revokeObjectURL(url);
  }, 1000);
}

/* =================================================================
   Track subgenome
   ================================================================= */

function getChrSub(genes) {
  const counts = {
    A: 0,
    B: 0,
    D: 0,
    Other: 0
  };

  genes.forEach(function (gene) {
    const subgenome =
      normalizeSub(
        gene.subgenome ||
        "Other"
      );

    counts[subgenome] =
      (counts[subgenome] || 0) +
      1;
  });

  let best = "Other";
  let bestCount = -1;

  ["A", "B", "D", "Other"].forEach(
    function (key) {
      if (
        counts[key] >
        bestCount
      ) {
        bestCount =
          counts[key];

        best = key;
      }
    }
  );

  return best;
}
