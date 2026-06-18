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
print('<title>Gene Tools</title>')
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

genefunctable = form["query2"].value  # 获取wheatPPI mysql
MAXtargets = int(form["filter2"].value)
name = form["ID2"].value.strip().split()  # 获取输入的基因
web = "http://wheatomics.sdau.edu.cn/cgi-bin/geneDetail.py?search="

mydb = MySQLdb.connect(host='localhost',
                       user='wheatomics_user',
                       passwd='wheatomics115599',
                       db='Genefuncdb',
                       charset='utf8')
cursor = mydb.cursor()


if genefunctable == 'WheatRiceArabidopsis_tbl':
    for gene in name:
        if 'Traes' in gene:
            select_sql = "select * from " + genefunctable + \
            " where Query='" + gene + "';"
            try:
                cursor.execute(select_sql)
                row = cursor.fetchall()
                row_rice = filter(lambda x: x[4] == 'Rice', row)
                row_arabidopsis = filter(lambda x: x[4] == 'Arabidopsis', row)
                res_rice = sorted(row_rice, key=lambda x: float(x[11]),reverse=True)[:MAXtargets]
                res_arabidopsis = sorted(row_arabidopsis, key = lambda x: float(x[11]),reverse=True)[:MAXtargets]
                print('''<table class="table table-striped">
                    <thead>
                    <tr>
                    <th class="card-title">Query</th>
                    <th class="card-title">Target</th>
                    <th class="card-title">Description</th>
                    <th class="card-title">Species</th>
                    <th class="card-title">Name</th>
                    <th class="card-title">Qcovs</th>
                    <th class="card-title">Length</th>
                    <th class="card-title">Identity</th>
                    <th class="card-title">Evalue</th>
                    </tr>
                    </thead>
                    <tbody>
                    ''' )
                
                for ele in res_rice:
                    print('<td><a href="'+ web + str(ele[1]) + '" target="_blank">' + str(ele[1]) + '</a></td>')
                    print('<td>' + str(ele[2]) + '</td>')
                    print('<td>' + str(ele[3].replace("#", "'")) + '</td>')
                    print('<td>' + str(ele[4]) + '</td>')
                    print('<td>' + str(ele[5]) + '</td>')
                    print('<td>' + str(ele[6]) + '</td>')
                    print('<td>' + str(ele[7]) + '</td>')
                    print('<td>' + str(ele[8]) + '</td>')
                    print('<td>' + str(float(ele[10])) + '</td></tr>')

                for ele in res_arabidopsis:
                    print('<td><a href="'+ web + str(ele[1]) + '" target="_blank">' + str(ele[1]) + '</a></td>')
                    print('<td>' + str(ele[2]) + '</td>')
                    print('<td>' + str(ele[3].replace("#", "'")) + '</td>')
                    print('<td>' + str(ele[4]) + '</td>')
                    print('<td>' + str(ele[5]) + '</td>')
                    print('<td>' + str(ele[6]) + '</td>')
                    print('<td>' + str(ele[7]) + '</td>')
                    print('<td>' + str(ele[8]) + '</td>')
                    print('<td>' + str(float(ele[10])) + '</td></tr>')
                print('''</tbody>\n</table>''')
                
            except Exception as e:
                print("Not found, please check your input")
                print('Reason:', e)
    

        elif gene.startswith('LOC_Os') or gene.startswith('Os'):
            select_sql = "select * from " + genefunctable + \
            " where Target1='" + gene + "';"
            try:
                MAXtargets = MAXtargets *3
                cursor.execute(select_sql)
                row = cursor.fetchall()
                row_rice = filter(lambda x: x[4] == 'Rice', row)
                res = sorted(row_rice, key = lambda x: float(x[11]),reverse=True)[:MAXtargets]
                print('''<table class="table table-striped">
                    <thead>
                    <tr>
                    <th class="card-title">Query</th>
                    <th class="card-title">Target</th>
                    <th class="card-title">Description</th>
                    <th class="card-title">Species</th>
                    <th class="card-title">Name</th>
                    <th class="card-title">Qcovs</th>
                    <th class="card-title">Length</th>
                    <th class="card-title">Identity</th>
                    <th class="card-title">Evalue</th>

                    </tr>
                    </thead>
                    <tbody>
                    ''' )
                #http://rice.plantbiology.msu.edu/cgi-bin/ORF_infopage.cgi?orf=LOC_Os11g35500    
                for ele in res:
                    print('<td><a href="'+ web + str(ele[1]) + '" target="_blank">' + str(ele[1]) + '</a></td>')
                    print('<td><a href="http://rice.plantbiology.msu.edu/cgi-bin/ORF_infopage.cgi?orf=' + str(ele[2]) + '" target="_blank">' + str(ele[2]) + '</a></td>')
                    print('<td>' + str(ele[3].replace("#", "'")) + '</td>')
                    print('<td>' + str(ele[4]) + '</td>')
                    print('<td>' + str(ele[5]) + '</td>')
                    print('<td>' + str(ele[6]) + '</td>')
                    print('<td>' + str(ele[7]) + '</td>')
                    print('<td>' + str(ele[8]) + '</td>')
                    print('<td>' + str(float(ele[10])) + '</td></tr>')
                print('''</tbody>\n</table>''')
                
            except Exception as e:
                print("Not found, please check your input")
                print('Reason:', e)

        elif gene.startswith('AT'):
            select_sql = "select * from " + genefunctable + \
            " where Target1='" + gene + "';"
            try:
                cursor.execute(select_sql)
                row = cursor.fetchall()
                res = sorted(row, key = lambda x: float(x[11]),reverse=True)[:MAXtargets*3]
                print('''<table class="table table-striped">
                    <thead>
                    <tr>
                    <th class="card-title">Query</th>
                    <th class="card-title">Target</th>
                    <th class="card-title">Description</th>
                    <th class="card-title">Species</th>
                    <th class="card-title">Name</th>
                    <th class="card-title">Qcovs</th>
                    <th class="card-title">Length</th>
                    <th class="card-title">Identity</th>
                    <th class="card-title">Evalue</th>
                    </tr>
                    </thead>
                    <tbody>
                    ''' )
                # https://www.arabidopsis.org/servlets/Search?type=general&search_action=detail&method=1&show_obsolete=F&name=AT5G66140&sub_type=gene&SEARCH_EXACT=4&SEARCH_CONTAINS=1
                for ele in res:
                    print('<td><a href="'+ web + str(ele[1]) + '" target="_blank">' + str(ele[1]) + '</a></td>')
                    print('<td><a href="https://www.arabidopsis.org/servlets/Search?type=general&search_action=detail&method=1&show_obsolete=F&name=' + str(ele[2]) + '&sub_type=gene&SEARCH_EXACT=4&SEARCH_CONTAINS=1" target="_blank">' + str(ele[2]) + '</td>')
                    print('<td>' + str(ele[3].replace("#", "'")) + '</td>')
                    print('<td>' + str(ele[4]) + '</td>')
                    print('<td>' + str(ele[5]) + '</td>')
                    print('<td>' + str(ele[6]) + '</td>')
                    print('<td>' + str(ele[7]) + '</td>')
                    print('<td>' + str(ele[8]) + '</td>')
                    print('<td>' + str(float(ele[10])) + '</td></tr>')
                print('''<tbody>\n</table>''')

            except Exception as e:
                print("Not found, please check your input")
                print('Reason:', e)

        else:
            print("Not found, please check your input")
   

print('''<br><br>qcovs : Query Coverage Per Subject<br>length : Alignment length<br>identity : Percentage of identical matches<br>positive : Percentage of positive-scoring matches<br>evalue : Expect value<br>score : Raw score<br><br>''')


cursor.close()
mydb.close()

print('</div>')
print('</div>')
print('''<script  type="text/javascript">
            function download(){
            var save = document.getElementById("seq").innerText;
            var save2 = save.trim().split("\\n").map(line => line.trim()).join("\\n");
            var blob = new Blob([save2], {type: "text/plain;charset=utf-8"});
            saveAs(blob, "wheat_rice_Arabidopsis_homologs.txt");}
        </script>''')
print('<div id="footer"></div>')

print('</body>')
print('</html>')
