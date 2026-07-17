var goData = null, keggData = null;

document.getElementById('geneInput').addEventListener('input', function() {
    var n = parseGenes(this.value).length;
    document.getElementById('geneCount').textContent = n + ' genes detected';
    document.getElementById('geneCount').style.color = n>0 ? '#2e7d32' : '#999';
});

function parseGenes(raw) {
    var arr = raw.split(/[\s,;\t\n\r]+/).map(function(s){return s.trim()}).filter(Boolean);
    var seen = {};
    return arr.filter(function(g){if(seen[g])return false;seen[g]=true;return true});
}

async function runEnrichment() {
    var genes = parseGenes(document.getElementById('geneInput').value);
    if (!genes.length) { alert('Paste at least one gene ID.'); return; }
    var padj = document.getElementById('padjThreshold').value;
    var btn = document.getElementById('runBtn');
    btn.disabled = true; btn.textContent = 'Running...';
    setStatus('Running enrichment analysis...', 'info');
    try {
        var body = JSON.stringify({genes: genes, padj_threshold: parseFloat(padj)});
        var headers = {'Content-Type': 'application/json'};
        var rs = await Promise.all([
            fetch('/api/go-kegg/go', {method:'POST', headers:headers, body:body}),
            fetch('/api/go-kegg/kegg', {method:'POST', headers:headers, body:body})
        ]);
        goData = await rs[0].json(); keggData = await rs[1].json();
        if (goData.error) { setStatus('GO: '+goData.error, 'error'); return; }
        if (keggData.error) { setStatus('KEGG: '+keggData.error, 'error'); return; }
        setStatus('', 'hidden');
        document.getElementById('results').style.display = 'block';
        renderGO(); renderKEGG(); switchTab('go');
    } catch(e) { setStatus('Network error: '+e.message, 'error'); }
    finally { btn.disabled = false; btn.textContent = 'Run Enrichment'; }
}

function makeLegendTraces(color) {
    return [
        {x:[null],y:[null],mode:'markers',type:'scatter',
         marker:{size:14,color:color,opacity:0.72,line:{width:1,color:'rgba(0,0,0,0.25)'}},
         name:'5',showlegend:true,legendgroup:'size'},
        {x:[null],y:[null],mode:'markers',type:'scatter',
         marker:{size:28,color:color,opacity:0.72,line:{width:1,color:'rgba(0,0,0,0.25)'}},
         name:'10',showlegend:true,legendgroup:'size'},
        {x:[null],y:[null],mode:'markers',type:'scatter',
         marker:{size:42,color:color,opacity:0.72,line:{width:1,color:'rgba(0,0,0,0.25)'}},
         name:'20',showlegend:true,legendgroup:'size'},
    ];
}

function makeBubble(divId, items, color, title, maxN) {
    maxN = maxN || 20;
    var el = document.getElementById(divId);
    if (!items || !items.length) { el.innerHTML = '<p class="no-data">No significant terms</p>'; return; }
    var top = items.slice().sort(function(a,b){return (a.padj||1)-(b.padj||1)}).slice(0, maxN).reverse();

    var mainTrace = {
        y: top.map(function(r){ var t=r.term||r.name||r.id||''; return t.length>55 ? t.slice(0,52)+'...' : t; }),
        x: top.map(function(r){ return -Math.log10(Math.max(r.padj||1e-300,1e-300)); }),
        text: top.map(function(r){
            return '<b>'+escHtml(r.id||r.term)+'</b><br>'+escHtml(r.term||r.name||'')+
                '<br>Genes: '+(r.k||0)+' / '+(r.K||0)+
                '<br>Ratio: '+(r.ratio||0).toFixed(2)+
                '<br>p.adjust: '+(r.padj||1).toExponential(2);
        }),
        mode: 'markers', type: 'scatter',
        marker: {
            size: top.map(function(r){ return Math.max((r.k||1)*7, 14); }),
            color: color, opacity: 0.72,
            line: { width: 1, color: 'rgba(0,0,0,0.25)' },
            sizemode: 'area', sizeref: 1.2,
            showscale: false,
        },
        hovertemplate: '%{text}<extra></extra>',
        showlegend: false,
    };

    var allTraces = [mainTrace].concat(makeLegendTraces(color));

    var layout = {
        title: { text: title+' ('+top.length+' terms)', font:{size:13} },
        xaxis: { title:'-log10(p.adjust)', zeroline:false, gridcolor:'#e8e8e8', titlefont:{size:11} },
        margin: { l:20, r:20, t:40, b:50 },
        height: Math.max(420, top.length*24),
        showlegend: true,
        legend: {
            title:{text:'<b>Gene Number</b>'},
            x:1.02, y:0.98,
            xanchor:'left', yanchor:'top',
            font:{size:10},
            bgcolor:'rgba(255,255,255,0.85)',
            bordercolor:'#ddd', borderwidth:1
        },
        paper_bgcolor: '#fafbfc', plot_bgcolor: '#fafbfc',
        yaxis: { automargin:true, tickfont:{size:10} }
    };
    Plotly.newPlot(divId, allTraces, layout, { responsive:true, displayModeBar:false });
}

function renderGO() {
    var d = goData, R = d.results || [];
    document.getElementById('goSummary').innerHTML =
        '<b>GO:</b> BG='+(d.N||0).toLocaleString()+' | Query='+(d.n||0).toLocaleString()+' | Sig='+R.length;
    if (!R.length) {
        ['goChartBP','goChartMF','goChartCC'].forEach(function(id){ document.getElementById(id).innerHTML='<p class="no-data">None</p>'; });
        document.querySelector('#goTable tbody').innerHTML='<tr><td colspan="8" class="no-data">None</td></tr>';
        return;
    }
    var bp=[],mf=[],cc=[];
    R.forEach(function(r){
        var o = (r.ontology||'').replace(/\r/g,'').trim();
        if (/biological/i.test(o)) bp.push(r);
        else if (/molecular/i.test(o)) mf.push(r);
        else if (/cellular/i.test(o)) cc.push(r);
        else bp.push(r);
    });
    makeBubble('goChartBP', bp, '#2196F3', 'Biological Process', 20);
    makeBubble('goChartMF', mf, '#4CAF50', 'Molecular Function', 20);
    makeBubble('goChartCC', cc, '#FF9800', 'Cellular Component', 20);

    window._goResults = R;

    var rows = [];
    for (var i=0; i<Math.min(R.length,300); i++) {
        (function(r){
            rows.push(
                '<tr class="go-row" data-go="'+escHtml(r.id)+'">'+
                '<td><a target="_blank" href="https://amigo.geneontology.org/amigo/term/'+escHtml(r.id)+'">'+escHtml(r.id)+'</a></td>'+
                '<td>'+escHtml(r.term||'')+'</td>'+
                '<td><span class="badge badge-'+(r.ontology||'').replace(/_/g,'-')+'">'+escHtml(r.ontology||'')+'</span></td>'+
                '<td><a href="#" class="gene-link" data-go="'+escHtml(r.id)+'">'+(r.k||0)+'</a></td>'+
                '<td>'+(r.K||0)+'</td><td>'+(r.ratio||0).toFixed(2)+'</td>'+
                '<td>'+(r.pvalue||1).toExponential(2)+'</td><td>'+(r.padj||1).toExponential(2)+'</td>'+
                '</tr>');
        })(R[i]);
    }
    var tbody = document.querySelector('#goTable tbody');
    tbody.innerHTML = rows.join('');
    tbody.querySelectorAll('.gene-link').forEach(function(a){
        a.addEventListener('click', function(e){ e.preventDefault(); toggleGoGenes(this); });
    });
}

function renderKEGG() {
    var d = keggData, R = d.results || [];
    document.getElementById('keggSummary').innerHTML =
        '<b>KEGG:</b> BG='+(d.N||0).toLocaleString()+' | Query='+(d.n||0).toLocaleString()+' | Sig='+R.length;
    if (!R.length) {
        document.getElementById('keggChart').innerHTML='<p class="no-data">None</p>';
        document.querySelector('#keggTable tbody').innerHTML='<tr><td colspan="7" class="no-data">None</td></tr>';
        return;
    }
    makeBubble('keggChart', R, '#E91E63', 'KEGG Pathways', 30);

    window._keggResults = R;

    var rows = [];
    for (var i=0; i<Math.min(R.length,300); i++) {
        (function(r){
            rows.push(
                '<tr class="kegg-row" data-pw="'+escHtml(r.id)+'">'+
                '<td><a target="_blank" href="https://www.genome.jp/pathway/'+escHtml((r.id||'').replace('path:',''))+'">'+escHtml(r.id||'')+'</a></td>'+
                '<td>'+escHtml(r.name||'')+'</td>'+
                '<td><a href="#" class="gene-link" data-pw="'+escHtml(r.id)+'">'+(r.k||0)+'</a></td>'+
                '<td>'+(r.K||0)+'</td><td>'+(r.ratio||0).toFixed(2)+'</td>'+
                '<td>'+(r.pvalue||1).toExponential(2)+'</td><td>'+(r.padj||1).toExponential(2)+'</td>'+
                '</tr>');
        })(R[i]);
    }
    var tbody = document.querySelector('#keggTable tbody');
    tbody.innerHTML = rows.join('');
    tbody.querySelectorAll('.gene-link').forEach(function(a){
        a.addEventListener('click', function(e){ e.preventDefault(); toggleKEGGGenes(this); });
    });
}

// ====== Download ======
function downloadCSV(filename, headers, data) {
    var BOM = '﻿', csv = BOM + headers.join(',') + '\n';
    for (var i=0; i<data.length; i++) {
        var row = [];
        for (var j=0; j<headers.length; j++) {
            var v = data[i][j] != null ? String(data[i][j]) : '';
            v = v.replace(/"/g, '""');
            row.push('"'+v+'"');
        }
        csv += row.join(',') + '\n';
    }
    var blob = new Blob([csv], {type:'text/csv;charset=utf-8'});
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a'); a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
}

function downloadGOTable() {
    var R = window._goResults || [];
    var rows = R.map(function(r){ return [r.id, r.term, r.ontology, r.k, r.K, r.ratio, r.pvalue, r.padj]; });
    downloadCSV('GO_enrichment.csv', ['GO_ID','Term','Ontology','Genes_in_list','Genes_in_BG','Enrichment_Ratio','pvalue','padj'], rows);
}

function downloadKEGGTable() {
    var R = window._keggResults || [];
    var rows = R.map(function(r){ return [r.id, r.name, r.k, r.K, r.ratio, r.pvalue, r.padj]; });
    downloadCSV('KEGG_enrichment.csv', ['Pathway_ID','Pathway_Name','Genes_in_list','Genes_in_BG','Enrichment_Ratio','pvalue','padj'], rows);
}

function downloadChart(divId, filename) {
    Plotly.downloadImage(document.getElementById(divId), {format:'png', width:1200, height:600, filename:filename});
}

// ====== Inline gene expansion ======
async function toggleGoGenes(el) {
    var row = el.closest('tr');
    var next = row.nextElementSibling;
    if (next && next.classList.contains('sub-row')) { next.remove(); return; }
    document.querySelectorAll('.sub-row').forEach(function(sr){ sr.remove(); });
    var goId = el.getAttribute('data-go');
    var sub = document.createElement('tr'); sub.className = 'sub-row';
    sub.innerHTML = '<td colspan="8"><em>Loading...</em></td>';
    row.parentNode.insertBefore(sub, row.nextSibling);
    var genes = parseGenes(document.getElementById('geneInput').value);
    try {
        var resp = await fetch('/api/go-kegg/go-genes?go_id='+encodeURIComponent(goId)+'&genes='+encodeURIComponent(genes.join(',')));
        var data = await resp.json();
        var hits = (data.genes||[]).filter(Boolean);
        sub.querySelector('td').innerHTML = hits.length
            ? '<strong style="color:#3f51b5;">'+hits.length+' genes:</strong><br>'+
              hits.map(function(g){return '<code>'+escHtml(g)+'</code>'}).join(' ')
            : '<em style="color:#999;">None</em>';
    } catch(e) { sub.querySelector('td').innerHTML = '<em style="color:red;">Error</em>'; }
}

async function toggleKEGGGenes(el) {
    var row = el.closest('tr');
    var next = row.nextElementSibling;
    if (next && next.classList.contains('sub-row')) { next.remove(); return; }
    document.querySelectorAll('.sub-row').forEach(function(sr){ sr.remove(); });
    var pwId = el.getAttribute('data-pw');
    var sub = document.createElement('tr'); sub.className = 'sub-row';
    sub.innerHTML = '<td colspan="7"><em>Loading...</em></td>';
    row.parentNode.insertBefore(sub, row.nextSibling);
    var genes = parseGenes(document.getElementById('geneInput').value);
    try {
        var resp = await fetch('/api/go-kegg/kegg-genes?pathway='+encodeURIComponent(pwId)+'&genes='+encodeURIComponent(genes.join(',')));
        var data = await resp.json();
        var hits = (data.genes||[]).filter(Boolean);
        sub.querySelector('td').innerHTML = hits.length
            ? '<strong style="color:#E91E63;">'+hits.length+' genes:</strong><br>'+
              hits.map(function(g){return '<code>'+escHtml(g)+'</code>'}).join(' ')
            : '<em style="color:#999;">None</em>';
    } catch(e) { sub.querySelector('td').innerHTML = '<em style="color:red;">Error</em>'; }
}

// Tabs
document.addEventListener('DOMContentLoaded', function(){
    document.querySelectorAll('.enrich-tab').forEach(function(t){
        t.addEventListener('click', function(){ switchTab(this.getAttribute('data-tab')); });
    });
});
function switchTab(tab) {
    document.querySelectorAll('.enrich-tab').forEach(function(t){ t.classList.toggle('active', t.getAttribute('data-tab')===tab); });
    document.getElementById('goPanel').classList.toggle('active', tab==='go');
    document.getElementById('keggPanel').classList.toggle('active', tab==='kegg');
    setTimeout(function(){
        if (tab==='go') { Plotly.Plots.resize('goChartBP'); Plotly.Plots.resize('goChartMF'); Plotly.Plots.resize('goChartCC'); }
        else Plotly.Plots.resize('keggChart');
    }, 200);
}
function loadExample() {
    var ex = 'TraesCS1A02G045300.1\nTraesCS1A02G104700.1\nTraesCS1A02G118400.1\nTraesCS1A02G193200.1\nTraesCS1A02G207700.1\nTraesCS1B02G024500.1\nTraesCS1B02G076300.1\nTraesCS1B02G108700.1\nTraesCS1B02G317100.1\nTraesCS2A02G338200.1';
    document.getElementById('geneInput').value = ex;
    document.getElementById('geneCount').textContent = '10 genes detected';
    document.getElementById('geneCount').style.color = '#2e7d32';
}
function setStatus(msg, cls) { var s=document.getElementById('status'); s.textContent=msg; s.className='status '+cls; }
function escHtml(s){ if(!s)return''; var d=document.createElement('div');d.textContent=String(s).replace(/\r/g,'');return d.innerHTML; }
