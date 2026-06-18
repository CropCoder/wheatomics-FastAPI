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
print('<title>KnownGenes</title>')
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
try:
    sql = "SELECT * FROM cloned_gene_tbl WHERE gene_id =\'" + searchid + "\';"
    mydb = MySQLdb.connect(host='localhost',
                           user='wheatomics_user',
                           passwd='wheatomics115599',
                           db='cloned_gene_db',
                           charset='utf8')
    cursor = mydb.cursor()
    cursor.execute(sql)
    row = cursor.fetchall()

    for ele in row:
        print('<span class="card-title"> ID in the database</span>:<br>' + str(ele[0]).replace('###','<br>') + '<br>')
        print('<span class="card-title">Gene id </span>:<br><a href="http://wheatomics.sdau.edu.cn/cgi-bin/geneDetail.py?search=' + str(ele[1]).replace('###','<br>') + '" target="_blank">' + str(ele[1]).replace('###','<br>') +'</a><br>')
        print('<span class="card-title">Gene name </span>: <br>' + str(ele[2]).replace('###','<br>') + '<br>')
        print('<span class="card-title">Gene position </span>: <br>' + str(ele[3]).replace('###','<br>') + '<br>')
        print('<span class="card-title">The phenotype regulated by this gene </span>: <br>' + str(ele[4]).replace('###','<br>') + '<br>')
        print('<span class="card-title">Gene from species </span>: <br>' + str(ele[5]).replace('###','<br>') + '<br>')
        print('<span class="card-title">Reference</span>: <br>')
        if str(ele[7]).count('###') >=1:
            for num in range(str(ele[7]).count('###') +1):
                print('<a href="https://www.doi.org/' + str(ele[7]).split('###')[num] + '"> ' + str(ele[6]).split('###')[num] + '</a><br>')
        else:
            print('<a href="https://www.doi.org/' + str(ele[7]) + '"> ' + str(ele[6]) + '</a><br>')
        print('<span class="card-title">Key result </span>: <br>' + str(ele[8]).replace('###','<br>') + '<br>')
        print('<span class="card-title">submission date</span>: <br>' + str(ele[11]) + '<br>')
        print('<hr />')
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
