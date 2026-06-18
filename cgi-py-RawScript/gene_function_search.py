#!/usr/bin/python2.7
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
print('<script src="/js/jquery/1.9.1/jquery.min.js" type=text/javascript></script>')
print('<link rel="stylesheet" href="/css/bootstrap-4.5.3-dist/css/bootstrap.css" type="text/css" />')
print('<script src="/css/bootstrap-4.5.3-dist/js/bootstrap.js" type=text/javascript></script>')
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
print('<button style="color:white;background-color:#007DBC;border-color:#007BFF" id="button" onclick="download();">Download table</button>')
print('<br><br>')
try:
    import cgitb
    cgitb.enable()
except:
    pass
import cgi
import subprocess

import MySQLdb


form = cgi.FieldStorage()

genefunctable = form["query"].value  # 获取wheatPPI mysql

name = form["ID"].value.strip().split()  # 获取输入的基因
web = "http://wheatomics.sdau.edu.cn/cgi-bin/geneDetail.py?search="

if genefunctable == 'Genefunc_table':
    mydb = MySQLdb.connect(host='localhost',
                       user='wheatomics_user',
                       passwd='wheatomics115599',
                       db='Genefuncdb',
                       charset='utf8')
    cursor = mydb.cursor()
    print('''<table id="myTable" class="table-striped">
                        <thead>
                        <tr>
                        <th style="text-align:center">Chrom</th>
                        <th style="text-align:center">Start</th>
                        <th style="text-align:center">END</th>
                        <th style="text-align:center">Gene</th>
                        <th style="text-align:center">Strand</th>
                        <th style="text-align:center">Function description</th>
                        <th style="text-align:center">Domain</th>
                        </tr>
                        </thead>
                        <tbody>
                        ''' )
    for gene in name:
        if ':' in gene:
            chrom = gene.split(':')[0]
            start = gene.split(':')[1].split('-')[0]
            end = gene.split(':')[1].split('-')[1]
            if 0 < int(end) - int(start) <= 30000000:
                select_sql = "select * from " + genefunctable + \
            " where Chrom='" + chrom + "' AND Start1 >= " + start + " AND End1 <=" + end + ";"
                try:
                    cursor.execute(select_sql)
                    row = cursor.fetchall()
                    for ele in row:
                        print('<td style="text-align:center">' + str(ele[2]) + '</td>')
                        print('<td style="text-align:center">' + str(float(ele[3])/1000000.0) + 'Mb</td>')
                        print('<td style="text-align:center">' + str(float(ele[4])/1000000.0) + 'Mb</td>')
                        print('<td style="text-align:center"><a href="'+ web + str(ele[1]) + '" target="_blank">' + str(ele[1]) + '</a></td>')
                        print('<td style="text-align:center">' + str(ele[5]) + '</td>')
                        print('<td style="text-align:center">' + str(ele[6].replace("#", "'")) + '</td>')
                        print('<td style="text-align:center">' + str(ele[7].replace("#","'")) + '</td><tr>')
                except Exception as e:
                    print("Not found, please check your input")
                    print('Reason:', e)
            else:
                print("End number should be more than start number and region should not be more than 30Mb !!!")
        if 'Traes' in gene:
            select_sql = "select * from " + genefunctable + \
            " where Gene='" + gene + "';"
            try:
                cursor.execute(select_sql)
                row = cursor.fetchall()
                for ele in row:
                    print('<td style="text-align:center">' + str(ele[2]) + '</td>')
                    print('<td style="text-align:center">' + str(float(ele[3])/1000000.0) + 'Mb</td>')
                    print('<td style="text-align:center">' + str(float(ele[4])/1000000.0) + 'Mb</td>')
                    print('<td style="text-align:center"><a href="'+ web + str(ele[1]) + '" target="_blank">' + str(ele[1]) + '</a></td>')
                    print('<td style="text-align:center">' + str(ele[5]) + '</td>')
                    print('<td style="text-align:center">' + str(ele[6].replace("#", "'")) + '</td>')
                    print('<td style="text-align:center">' + str(ele[7].replace("#","'")) + '</td><tr>')
            except Exception as e:
                print("Not found, please check your input")
                print('Reason:', e)
        if 'PF' in gene:
            select_sql = "select * from " + genefunctable + \
            " where Domain REGEXP '" + gene + "';"
            try:
                cursor.execute(select_sql)
                row = cursor.fetchall()
                for ele in row:
                    print('<td style="text-align:center">' + str(ele[2]) + '</td>')
                    print('<td style="text-align:center">' + str(float(ele[3])/1000000.0) + 'Mb</td>')
                    print('<td style="text-align:center">' + str(float(ele[4])/1000000.0) + 'Mb</td>')
                    print('<td style="text-align:center"><a href="'+ web + str(ele[1]) + '" target="_blank">' + str(ele[1]) + '</a></td>')
                    print('<td style="text-align:center">' + str(ele[5]) + '</td>')
                    print('<td style="text-align:center">' + str(ele[6].replace("#", "'")) + '</td>')
                    print('<td style="text-align:center">' + str(ele[7].replace("#","'")) + '</td><tr>')
            except Exception as e:
                print("Not found, please check your input")
                print('Reason:', e)
    print('''<tbody>\n</table>''')
    cursor.close()
    mydb.close()
elif genefunctable == 'Genefunc_IWGSC03G_table':
    mydb = MySQLdb.connect(host='localhost',
                       user='wheatomics_user',
                       passwd='wheatomics115599',
                       db='Genefuncdb',
                       charset='utf8')
    cursor = mydb.cursor()
    print('''<table id="myTable" class="table-striped">
                        <thead>
                        <tr>
                        <th style="text-align:center">Chrom</th>
                        <th style="text-align:center">Start</th>
                        <th style="text-align:center">END</th>
                        <th style="text-align:center">Gene03G</th>
                        <th style="text-align:center">Gene02G</th>
                        <th style="text-align:center">Strand</th>
                        <th style="text-align:center">Function description</th>
                        <th style="text-align:center">Domain</th>
                        </tr>
                        </thead>
                        <tbody>
                        ''' )
    for gene in name:
        if ':' in gene:
            chrom = gene.split(':')[0]
            start = gene.split(':')[1].split('-')[0]
            end = gene.split(':')[1].split('-')[1]
            if 0 < int(end) - int(start) <= 30000000:
                select_sql = "select * from " + genefunctable + \
            " where Chrom='" + chrom + "' AND Start1 >= " + start + " AND End1 <=" + end + ";"
                try:
                    cursor.execute(select_sql)
                    row = cursor.fetchall()
                    for ele in row:
                        print('<td style="text-align:center">' + str(ele[3]) + '</td>')
                        print('<td style="text-align:center">' + str(float(ele[4])/1000000.0) + 'Mb</td>')
                        print('<td style="text-align:center">' + str(float(ele[5])/1000000.0) + 'Mb</td>')
                        print('<td style="text-align:center"><a href="'+ web + str(ele[1]) + '" target="_blank">' + str(ele[1]) + '</a></td>')
                        print('<td style="text-align:center"><a href="'+ web + str(ele[2]) + '" target="_blank">' + str(ele[2]) + '</a></td>')
                        print('<td style="text-align:center">' + str(ele[6]) + '</td>')
                        print('<td style="text-align:center">' + str(ele[7].replace("#", "'")) + '</td>')
                        print('<td style="text-align:center">' + str(ele[8].replace("#","'")) + '</td><tr>')
                    print('''</tbody>\n</table>''')
                except Exception as e:
                    print("Not found, please check your input")
                    print('Reason:', e)
            else:
                print("End number should be more than start number and region should not be more than 30Mb !!!")
        if 'Traes' in gene:
            select_sql = "select * from " + genefunctable + \
            " where Gene03G='" + gene + "' OR Gene02G='" + gene + "';"
            try:
                cursor.execute(select_sql)
                row = cursor.fetchall()
                for ele in row:
                    print('<td style="text-align:center">' + str(ele[3]) + '</td>')
                    print('<td style="text-align:center">' + str(float(ele[4])/1000000.0) + 'Mb</td>')
                    print('<td style="text-align:center">' + str(float(ele[5])/1000000.0) + 'Mb</td>')
                    print('<td style="text-align:center"><a href="'+ web + str(ele[1]) + '" target="_blank">' + str(ele[1]) + '</a></td>')
                    print('<td style="text-align:center"><a href="'+ web + str(ele[2]) + '" target="_blank">' + str(ele[2]) + '</a></td>')
                    print('<td style="text-align:center">' + str(ele[6]) + '</td>')
                    print('<td style="text-align:center">' + str(ele[8].replace("#", "'")) + '</td>')
                    print('<td style="text-align:center">' + str(ele[8].replace("#","'")) + '</td><tr>')
                print('''<tbody>\n</table>''')
            except Exception as e:
                print("Not found, please check your input")
                print('Reason:', e)
        if 'PF' in gene:
            select_sql = "select * from " + genefunctable + \
            " where Domain REGEXP '" + gene + "';"
            try:
                cursor.execute(select_sql)
                row = cursor.fetchall()
                for ele in row:
                    print('<td style="text-align:center">' + str(ele[3]) + '</td>')
                    print('<td style="text-align:center">' + str(float(ele[4])/1000000.0) + 'Mb</td>')
                    print('<td style="text-align:center">' + str(float(ele[5])/1000000.0) + 'Mb</td>')
                    print('<td style="text-align:center"><a href="'+ web + str(ele[1]) + '" target="_blank">' + str(ele[1]) + '</a></td>')
                    print('<td style="text-align:center"><a href="'+ web + str(ele[2]) + '" target="_blank">' + str(ele[2]) + '</a></td>')
                    print('<td style="text-align:center">' + str(ele[6]) + '</td>')
                    print('<td style="text-align:center">' + str(ele[7].replace("#", "'")) + '</td>')
                    print('<td style="text-align:center">' + str(ele[8].replace("#","'")) + '</td><tr>')
                print('''<tbody>\n</table>''')
            except Exception as e:
                print("Not found, please check your input")
                print('Reason:', e)
    print('''<tbody>\n</table>''')
    cursor.close()
    mydb.close()

print('</div>')
print('''<script  type="text/javascript">
            function download(){
            var save = document.getElementById("myTable").innerText;
            var blob = new Blob([save], {type: "text/plain;charset=utf-8"});
            saveAs(blob, "table_download.txt");}
        </script>''')
print('<div id="footer"></div>')

print('</body>')
print('</html>')
