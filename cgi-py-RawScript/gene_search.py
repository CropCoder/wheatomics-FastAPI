#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
__author__ = 'shengwei ma'
__author_email__ = 'shengweima@icloud.com'

# this file like apache cgi file

from datetime import datetime, date
import MySQLdb
import cgi

print("Content-Type: text/html")
print("")
print('<html>')
  
print('<head>')
print('<title>Wheat Gene</title>')
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
print('<div id="header"></div>')
print('<div id=home_content>')
print('<br>')

try:
    import cgitb
    cgitb.enable(display=0, logdir='/var/www/html/genes/log/')
except:
    pass

form = cgi.FieldStorage()

searchid = form["searchid"].value.strip().replace('"', '')

web = "http://wheatomics.sdau.edu.cn/cgi-bin/gene_search_by_id.py?searchid="
try:
    sql = "SELECT gene_id,gene_name,chrom_pos,gene_phenotype, gene_species,paper_doi FROM cloned_gene_tbl WHERE gene_id like '%" + searchid + "%' or gene_name like '%" + searchid + \
        "%' or chrom_pos like '%" + searchid + "%' or gene_phenotype like '%" + searchid + "%' or gene_species like '%" + searchid + "%' or paper_doi like '%" + searchid + "%';"
    mydb = MySQLdb.connect(host='localhost',
                           user='wheatomics_user',
                           passwd='wheatomics115599',
                           db='cloned_gene_db',
                           charset='utf8')
    cursor = mydb.cursor()
    cursor.execute(sql)
    row = cursor.fetchall()
    print('''<table  class="table table-striped">
             <thead>
             <tr>
             <th class="card-title">GeneID</th>
             <th class="card-title">GeneName</th>
             <th class="card-title">Position</th>
             <th class="card-title">Trait</th>
             <th class="card-title">Species</th>
             <th class="card-title">DOI</th>
             </tr>
             </thead>
             <tbody>
             ''')
    for ele in row:
        print('<td><a href="' + web + str(ele[0]) + '"> ' + str(ele[0]) + '</a></td>')
        print('<td>' + str(ele[1]).replace('###',';') + '</td>')
        print('<td>' + str(ele[2]).replace('###',';') + '</td>')
        print('<td>' + str(ele[3]).replace('###',';') + '</td>')
        print('<td>' + str(ele[4]).replace('###',';') + '</td>')
        print('<td>')
        if str(ele[5]).count('###') >=1:
            for num in range(str(ele[5]).count('###')+1):
                print('<a href="https://www.doi.org/' + str(ele[5]).split('###')[num] + '"> ' + str(ele[5]).split('###')[num] + '</a>')
            print('</td><tr>')
        else:
            print('<a href="https://www.doi.org/' + str(ele[5]) + '"> ' + str(ele[5]) + '</a></td><tr>')
    print('</tbody>\n</table>')
except Exception as e:
    print(str(e))
else:
    print('')
    print('')
    print('Found')

cursor.close()
mydb.close()

print('</div>')
print('<div id="footer"></div>')

print('</body>')
print('</html>')
