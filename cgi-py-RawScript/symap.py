#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
__author__ = 'shengwei ma'
__author_email__ = 'shengweima@icloud.com'

import sys
reload(sys)
import re
sys.setdefaultencoding('utf-8')

print("Content-Type: text/html")
print("")
print('<html>')
  
print('<head>')
print('<title>Genome Synteny</title>')
print('<link rel="shortcut icon" href="/favicon.ico" type="image/x-icon" />')
print('<link rel="stylesheet" href="/css/style.css" type="text/css" />')
print('<link rel="stylesheet" href="/css/bootstrap-4.5.3-dist/css/bootstrap.css" type="text/css" />')
print('<script src="/css/bootstrap-4.5.3-dist/js/bootstrap.js" type=text/javascript></script>')
print('<script src="/js/jquery/1.9.1/jquery.min.js" type=text/javascript></script>')
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
#print('<div id="header"></div>')
#print('<div id=home_content>')
print('<br>')

try:
    import cgitb
    cgitb.enable()
except:
    pass
import cgi
import subprocess

import MySQLdb


form = cgi.FieldStorage()

symaptbl = form["query"].value  # 获取wheatPPI mysql

name = form["ID"].value.strip().split()  # 获取输入的基因

mydb = MySQLdb.connect(host='localhost',
                       user='wheatomics_user',
                       passwd='wheatomics115599',
                       db='symapdb',
                       charset='utf8')
cursor = mydb.cursor()



if symaptbl == 'CSsymaptbl':
    for gene in name:
        if ':' in gene:
            chrom = gene.split(':')[0]
            start = gene.split(':')[1].split('-')[0]
            end = gene.split(':')[1].split('-')[1]
            if 0 < int(end) - int(start) <= 30000000:
                select_sql = "select * from " + symaptbl + " where Chrom='" + chrom + "' AND Start1 >= " + start + " AND End1 <=" + end + ";"
                try:
                    cursor.execute(select_sql)
                    row = cursor.fetchall()
                    print('''<table class="table table-striped" width=1000>
                        <thead>
                        <tr>
                        <th class="card-title">Chrom</th>
                        <th class="card-title">Start</th>
                        <th class="card-title">END</th>
                        <th class="card-title">Strand</th>
                        <th class="card-title">Gene</th>
                        <th class="card-title">Chinese spring</th>
                        <th class="card-title">Durum wheat</th>
                        <th class="card-title">Wild emmer</th>
                        <th class="card-title">Triticum urartu</th>
                        <th class="card-title">Aegilops tauschii</th>
                        </tr>
                        </thead>
                        <tbody>
                        ''' )
                    for ele in row:
                        print('<td>' + str(ele[1]) + '</td>')
                        print('<td>' + str(float(ele[2])/1000000.0) + 'Mb</td>')
                        print('<td>' + str(float(ele[3])/1000000.0) + 'Mb</td>')
                        print('<td>' + str(ele[4]) + '</td>')
                        print('<td>' + str(ele[5]) + '</td>')
                        print('<td>' + str(ele[6]) + '</td>')
                        print('<td>' + str(ele[7]) + '</td>')
                        print('<td>' + str(ele[8]) + '</td>')
                        print('<td>' + re.sub(r'\.\d+','',str(ele[9])) + '</td>')
                        print('<td>' + str(ele[10]) + '</td><tr>')
                    print('''</tbody>\n</table>''')
                except Exception as e:
                    print("Not found, please check your input")
                    print('Reason:', e)
            else:
                print("End number should be more than start number and region should not be more than 30Mb !!!")
        if 'Traes' in gene and '01G' in gene:
            select_sql = "select * from " + symaptbl + " where Gene='" + gene + "';"
            try:
                cursor.execute(select_sql)
                row = cursor.fetchall()
                print('''<table class="table table-striped" width=1000>
                        <thead>
                        <tr>
                        <th class="card-title">Chrom</th>
                        <th class="card-title">Start</th>
                        <th class="card-title">END</th>
                        <th class="card-title">Strand</th>
                        <th class="card-title">Gene</th>
                        <th class="card-title">Chinese spring</th>
                        <th class="card-title">Durum wheat </th>
                        <th class="card-title">Wild emmer </th>
                        <th class="card-title">Triticum urartu </th>
                        <th class="card-title">Aegilops tauschii</th>
                        </tr>
                        </thead>
                        <tbody>
                        ''' )
                for ele in row:
                    print('<td>' + str(ele[1]) + '</td>')
                    print('<td>' + str(float(ele[2])/1000000.0) + 'Mb</td>')
                    print('<td>' + str(float(ele[3])/1000000.0) + 'Mb</td>')
                    print('<td>' + str(ele[4]) + '</td>')
                    print('<td>' + str(ele[5]) + '</td>')
                    print('<td>' + str(ele[6]) + '</td>')
                    print('<td>' + str(ele[7]) + '</td>')
                    print('<td>' + str(ele[8]) + '</td>')
                    print('<td>' + re.sub(r'\.\d+','',str(ele[9])) + '</td>')
                    print('<td>' + str(ele[10]) + '</td><tr>')
                    print('''</tbody>\n</table>''')
            except Exception as e:
                print("Not found, please check your input")
                print('Reason:', e)
        



cursor.close()
mydb.close()

#print('</div>')
#print('<div id="footer"></div>')

print('</body>')
print('</html>')
