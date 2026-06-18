#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
__author__ = 'shengwei ma'
__author_email__ = 'shengweima@icloud.com'

import sys
reload(sys)

sys.setdefaultencoding('utf-8')

print("Content-Type: text/html")
print("")
print('<html>')
print('<head>')
print('<title>HomologFinder</title>')
print('<link rel="shortcut icon" href="/favicon.ico" type="image/x-icon" />')
print('<link rel="stylesheet" href="/css/style.css" type="text/css" />')
print('<link rel="stylesheet" href="/css/bootstrap-4.5.3-dist/css/bootstrap.css" type="text/css" />')
print('<script src="/css/bootstrap-4.5.3-dist/js/bootstrap.js" type=text/javascript></script>')
print('<script src="/js/jquery/1.9.1/jquery.min.js" type=text/javascript></script>')
print('<script src="/js/FileSaver.js/FileSaver.min.js" type=text/javascript></script>')
print('<script> ')
print('$(function(){')
print('$("#header").load("/header.html");')
print('});')
print('</script>')
print('<script> ')
print('$(function(){')
print('$("#footer").load("/footer.html");')
print('});')
print('</script>')

print('</head>')
print('<body>')
print('<div id="header"></div>')
print('<div id=home_content>')
print('''<button style="color:white;background-color:#007DBC;border-color:#007BFF" id="button" onclick="download();">Download Table</button>''')
print('<br>')
print('<br>')
print('<div id=seq>')
try:
    import cgitb
    cgitb.enable()
except:
    pass
import cgi
import subprocess

import MySQLdb


form = cgi.FieldStorage()

genefunctable = form["query3"].value  # 获取wheatPPI mysql
MAXtargets = int(form["filter3"].value)
name = form["ID3"].value.strip().split()  # 获取输入的基因
web = "http://wheatomics.sdau.edu.cn/cgi-bin/geneDetail.py?search="

wheat_max = MAXtargets * 3
durum_max = MAXtargets * 2
mydb = MySQLdb.connect(host='localhost',
                       user='wheatomics_user',
                       passwd='wheatomics115599',
                       db='Genefuncdb',
                       charset='utf8')
cursor = mydb.cursor()


if genefunctable == 'Triticeae_table':
    for gene in name:
        select_sql = "select * from " + genefunctable + \
            " where Query='" + gene + "';"
    try:
        cursor.execute(select_sql)
        row = cursor.fetchall()
        
        row_Triticum_aestivum = filter(lambda x: x[3] == 'Triticum aestivum', row)
        row_Durum_wheat = filter(lambda x: x[3] == 'Durum wheat', row)
        row_Wild_emmer = filter(lambda x: x[3] == 'Wild emmer', row)
        row_Triticum_urartu = filter(lambda x: x[3] == 'Triticum urartu', row)
        row_Aegilops_tauschii = filter(lambda x: x[3] == 'Aegilops tauschii', row)
        row_Hordeum_vulgare = filter(lambda x: x[3] == 'Hordeum vulgare', row)
        

        res_Triticum_aestivum = sorted(row_Triticum_aestivum, key=lambda x: float(x[8]))[:wheat_max]
        res_Durum_wheat = sorted(row_Durum_wheat, key=lambda x: float(x[8]))[:durum_max]
        res_Wild_emmer = sorted(row_Wild_emmer, key=lambda x: float(x[8]))[:durum_max]
        res_Triticum_urartu = sorted(row_Triticum_urartu, key=lambda x: float(x[8]))[:MAXtargets]
        res_Aegilops_tauschii = sorted(row_Aegilops_tauschii, key=lambda x: float(x[8]))[:MAXtargets]
        res_Hordeum_vulgare = sorted(row_Hordeum_vulgare, key=lambda x: float(x[8]))[:MAXtargets]
            
        res_all = res_Triticum_aestivum + res_Wild_emmer + res_Durum_wheat + res_Triticum_urartu + res_Aegilops_tauschii + res_Hordeum_vulgare

        print('''<table class="table table-striped">
            <thead>
            <tr>
            <th class="card-title">Query</th>
            <th class="card-title">Target</th>
            <th class="card-title">Species</th>
            <th class="card-title">Qcovs (%)</th>
            <th class="card-title">Length</th>
            <th class="card-title">Identity (%)</th>
            <th class="card-title">Positive (%)</th>
            <th class="card-title">Evalue</th>
            <th class="card-title">Score</th>
            </tr>
            </thead>
            <tbody>
                ''' )
                
        for ele in res_all:
            print('<td>' + str(ele[1]) + '</td>')
            if 'TraesCS' in ele[2]:
                print('<td><a href="' + web + str(ele[2]) + '" target ="_blank">'+str(ele[2])+'</a></td>')
            else:
                print('<td>' + str(ele[2]) + '</td>')
            print('<td>' + str(ele[3]) + '</td>')
            print('<td>' + str(ele[4]) + '</td>')
            print('<td>' + str(ele[5]) + '</td>')
            print('<td>' + str(ele[6]) + '</td>')
            print('<td>' + str(ele[7]) + '</td>')
            print('<td>' + str(ele[8]) + '</td>')
            print('<td>' + str(ele[9]) + '</td><tr>')
        print('</tbody>\n</table>')        
    except Exception as e:
        print("Not found, please check your input")
        print('Reason:', e)

    finally:
        print('''<br><br>qcovs: Query Coverage Per Subject<br>length: Alignment length<br>identity: Percentage of identical matches<br>positive: Percentage of positive-scoring matches<br>evalue: Expect value<br>score: Raw score<br><br>''') 

cursor.close()
mydb.close()
print('</div>')
print('</div>')
print('''<script  type="text/javascript">
            function download(){
            var save = document.getElementById("seq").innerText;
            var save2 = save.trim().split("\\n").map(line => line.trim()).join("\\n");
            var blob = new Blob([save2], {type: "text/plain;charset=utf-8"});
            saveAs(blob, "Triticeae_homologs.txt");}
        </script>''')
print('<div id="footer"></div>')

print('</body>')
print('</html>')
