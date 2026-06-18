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
print("<html>")

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
    print('''<table border="1">
                        <tr>
                        <th>GeneID</th>
                        <th>GeneName</th>
                        <th>Position</th>
                        <th>Trait</th>
                        <th>Species</th>
                        <th>DOI</th>
                        </tr>
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
    print('</table>')
except Exception as e:
    print(str(e))
else:
    print('')
    print('')
    print('Found')

cursor.close()
mydb.close()

