#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import sys
reload(sys)
sys.setdefaultencoding('utf-8')

import cgitb
cgitb.enable()

print("Content-Type: text/html\n")

print('''<!DOCTYPE html>
<html>
<head>
<title>Wheat Co-expression</title>

<link rel="stylesheet" href="/css/style.css" />
<link rel="stylesheet" href="/css/bootstrap-4.5.3-dist/css/bootstrap.css" />

<script src="/js/jquery/1.9.1/jquery.min.js"></script>
<script src="/css/bootstrap-4.5.3-dist/js/bootstrap.js"></script>
<script src="/js/FileSaver.js/FileSaver.min.js"></script>

<!-- 本地 echarts -->
<script src="/js/echarts.min.js"></script>

<script>
$(function(){
  $("#header").load("/header.html");
  $("#footer").load("/footer.html");
});
</script>

</head>
<body>
<div id="header"></div>
<div id="home_content">
''')

print('<button style="color:white;background-color:#007DBC;" onclick="download();">Download table</button><br><br>')

# 网络图容器
print('<div id="network" style="width:100%;height:520px;border:1px solid #ccc;"></div><br>')
print('<div id="seq">')

# ================= 参数 =================
import cgi
form = cgi.FieldStorage()

coexpressiontable = form.getvalue("query")
filter1 = form.getvalue("filter")
ids = form.getvalue("ID")

if not coexpressiontable or not filter1 or not ids:
    print("<h3>Parameter missing</h3></div></body></html>")
    sys.exit()

name = ids.strip().split()

# ================= 数据库 =================
import MySQLdb
import json

mydb = MySQLdb.connect(
    host='localhost',
    user='wheatomics_user',
    passwd='wheatomics115599',
    db='coexpressiondb',
    charset='utf8'
)
cursor = mydb.cursor()

all_rows = []

# ================= 查询 =================
for gene in name:
    if '.' in filter1:
        filter2 = str((0 - float(filter1)))
        sql = """
        SELECT * FROM %s
        WHERE (Gene1='%s' OR Gene2='%s')
        AND (CAST(PCC AS DECIMAL(10,4)) >= %s OR CAST(PCC AS DECIMAL(10,4)) <= %s)
        ORDER BY CAST(PCC AS DECIMAL(10,4)) DESC
        """ % (coexpressiontable, gene, gene, filter1, filter2)
    else:
        sql = """
        SELECT * FROM %s
        WHERE (Gene1='%s' OR Gene2='%s')
        AND CAST(MR AS UNSIGNED) <= %s
        ORDER BY CAST(MR AS UNSIGNED) ASC
        """ % (coexpressiontable, gene, gene, filter1)

    cursor.execute(sql)
    rows = cursor.fetchall()
    rows = rows[:200]
    all_rows.extend(rows)

# ================= 构建网络 =================
nodes_set = set()
edges_list = []
edge_seen = set()

for ele in all_rows:
    try:
        g1 = str(ele[1]).strip()
        g2 = str(ele[2]).strip()
        pcc = float(ele[3])

        nodes_set.add(g1)
        nodes_set.add(g2)

        key = tuple(sorted([g1, g2]))
        if key not in edge_seen:
            edges_list.append({
                "source": g1,
                "target": g2,
                "value": pcc
            })
            edge_seen.add(key)

    except:
        pass

query_genes = set([g.strip() for g in name])

node_list = []
for n in nodes_set:
    node_list.append({
        "id": n,
        "name": n,
        "symbolSize": 60 if n in query_genes else 22,
        "itemStyle": {
            "color": "#ff0000" if n in query_genes else "#3399ff"
        }
    })

# 输出 JS 数据
print("<script>")
print("var nodes = %s;" % json.dumps(node_list, ensure_ascii=False))
print("var edges = %s;" % json.dumps(edges_list, ensure_ascii=False))
print("</script>")

# ================= 表格 =================
print('''<table class="table table-striped">
<thead>
<tr>
<th>Gene1</th>
<th>Gene2</th>
<th>PCC</th>
<th>MR</th>
</tr>
</thead>
<tbody>
''')

web = "http://wheatomics.sdau.edu.cn/cgi-bin/geneDetail.py?search="

for ele in all_rows:
    try:
        print('<tr>')
        print('<td><a href="'+ web + str(ele[1]).strip() + '" target="_blank">' + str(ele[1]).strip() + '</a></td>')
        print('<td><a href="'+ web + str(ele[2]).strip() + '" target="_blank">' + str(ele[2]).strip() + '</a></td>')
        print('<td>' + str('%.2f' % float(ele[3])) + '</td>')
        print('<td>' + str(ele[4].split('.')[0]) + '</td>')
        print('</tr>')
    except:
        pass

print('</tbody></table>')

cursor.close()
mydb.close()

print('</div>')

# ================= 网络图 =================
print('''
<script>

console.log("nodes:", nodes);
console.log("edges:", edges);

if (nodes.length > 0 && edges.length > 0) {

    var chart = echarts.init(document.getElementById('network'));

    chart.setOption({
        tooltip: {},

        series: [{
            type: 'graph',
            layout: 'force',

            data: nodes,
            links: edges,

            roam: true,

            label: {
                show: true,
                fontSize: 10
            },

            force: {
                repulsion: 300,
                edgeLength: 120
            },

            // 🔥 强制显示线
            lineStyle: {
                color: "#000000",
                width: 2,
                opacity: 1
            }
        }]
    });

} else {
    console.log("⚠️ edges为空或nodes为空");
}

</script>
''')

# 下载
print('''
<script>
function download(){
    var save = document.getElementById("seq").innerText;
    var blob = new Blob([save], {type: "text/plain;charset=utf-8"});
    saveAs(blob, "co-expression.txt");
}
</script>
''')

print('<div id="footer"></div>')
print('</div></body></html>')
