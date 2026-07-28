const CLUSTER_COLORS = {
  1: "#1565c0", 2: "#c62828", 3: "#2e7d32", 4: "#e65100",
  5: "#7b1fa2", 6: "#00695c", 7: "#4e342e", "none": "#94a3b8"
};

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("searchForm").addEventListener("submit", e => {
    e.preventDefault();
    const q = document.getElementById("geneInput").value.trim();
    if (!q) return;
    window.history.pushState({}, "", "?q=" + encodeURIComponent(q));
    searchGene(q);
  });
  const q = new URLSearchParams(window.location.search).get("q");
  if (q) { document.getElementById("geneInput").value = q; searchGene(q); }
});

async function searchGene(q) {
  const msg = document.getElementById("message");
  const result = document.getElementById("result");
  msg.textContent = "Loading...";
  result.style.display = "none";

  try {
    const resp = await fetch("/api/orthofinder/neighborhood?q=" + encodeURIComponent(q));
    const data = await resp.json();
    if (!resp.ok || data.error) { msg.textContent = data.detail || data.error || "Server error"; return; }

    msg.textContent = "";
    result.style.display = "block";

    // Summary
    document.getElementById("queryTitle").textContent =
      data.query + " — " + data.query_genome + "_" + data.query_subgenome + " subgenome";
    document.getElementById("chromLabel").textContent =
      data.query_chrom + " (" + data.query_genome + "_" + data.query_subgenome + ")";

    const qc = data.query_cluster;
    const clusterBadge = qc
      ? '<span class="cluster-badge cluster-badge-' + qc + '">Homoeologous group ' + qc + '</span>'
      : '<span class="cluster-badge cluster-badge-none">No cluster</span>';
    document.getElementById("clusterInfo").innerHTML =
      "<strong>Homoeologous group:</strong> " + clusterBadge +
      " &nbsp;|&nbsp; <strong>Total genes on chromosome:</strong> " + data.total_on_chromosome;

    // Legend
    var legendHtml = '<div class="legend-item"><div class="legend-dot" style="background:#f59e0b;"></div>Query gene</div>';
    for (var c = 1; c <= 7; c++) {
      legendHtml += '<div class="legend-item"><div class="legend-dot" style="background:' + CLUSTER_COLORS[c] + ';"></div>Group ' + c + '</div>';
    }
    legendHtml += '<div class="legend-item"><div class="legend-dot" style="background:' + CLUSTER_COLORS["none"] + ';"></div>No group</div>';
    document.getElementById("legend").innerHTML = legendHtml;

    // Table
    var genes = data.neighborhood || [];
    var html = '<table><thead><tr><th>Gene ID</th><th>Label</th><th>Position</th><th>Homoeologous group</th><th>Connected?</th></tr></thead><tbody>';
    genes.forEach(function(g) {
      var isQuery = g.gene_id === data.query;
      var rowClass = isQuery ? " query-row" : "";
      var clusterColor = CLUSTER_COLORS[g.cluster || "none"];
      var clusterText = g.cluster ? "Group " + g.cluster : "—";
      var connected = (g.cluster && g.cluster === qc) ? "✓" : "";
      if (isQuery) connected = "★";
      html += '<tr class="' + rowClass + '">' +
        '<td>' + escapeHtml(g.gene_id) + '</td>' +
        '<td style="font-size:12px;color:#64748b;">' + escapeHtml(g.label) + '</td>' +
        '<td>' + g.start.toLocaleString() + '</td>' +
        '<td><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + clusterColor + ';margin-right:6px;"></span>' + clusterText + '</td>' +
        '<td>' + connected + '</td>' +
        '</tr>';
    });
    html += '</tbody></table>';
    document.getElementById("geneTable").innerHTML = html;

  } catch (e) {
    msg.textContent = "Error: " + e.message;
  }
}

function escapeHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
