#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'shengwei ma'
__author_email__ = 'shengweima@icloud.com'

import sys
reload(sys)

sys.setdefaultencoding('utf-8')

print("Content-Type: text/html")
print ("")
print ("<html>")

try:
    import cgitb
    cgitb.enable()
except:
    pass
import cgi
import subprocess

import MySQLdb


form = cgi.FieldStorage()

ppitable = form["query"].value  # 获取wheatPPI mysql
filter1 = form["filter"].value  # 获取wheatPPI mysql
name = form["ID"].value.strip().split()  # 获取输入的基因

mydb = MySQLdb.connect(host='localhost',
                       user='wheatomics_user',
                       passwd='wheatomics115599',
                       db='wheatPPIdb',
                       charset='utf8')
cursor = mydb.cursor()



if ppitable == 'PPI_result':
    for gene in name:
        select_sql = "select * from " + ppitable + \
            " where WheatID1 or WheatID2 REGEXP '" + gene + "' AND Score >= " + filter1 + ";"
        
        try:
            cursor.execute(select_sql)
            row = cursor.fetchall()
            print('''<table border="1">
             <tr>
             <th>WheatID1</th>
             <th>WheatID2</th>
             <th>eggNOGID1</th>
             <th>eggNOGID2</th>
             <th>Scores</th>
             <th>Annotation1</th>
             <th>Annotation2</th>
             </tr>
             ''' )
            for ele in row:
                a = []
                b = []
                for i in ele[1].split('#'):
                    if i in a:
                        pass
                    else:
                        a.append(i)
                for i in ele[2].split('#'):
                    if i in b:
                        pass
                    else:
                        b.append(i)
                
                print('<td>' + '<br>'.join(a) + '</td>')
                print('<td>' + '<br>'.join(b) + '</td>')
                print('<td><a href="http://plants.proteincomplexes.org/getInteractionsForOrthogroupID?OrthogroupID=' + ele[3] + '&Species=wheat" target="_blank">'+ ele[3]+ '</a></td>')
                print('<td><a href="http://plants.proteincomplexes.org/getInteractionsForOrthogroupID?OrthogroupID=' + ele[4] + '&Species=wheat" target="_blank">'+ ele[4]+ '</a></td>')
                print('<td>' + ele[5] + '</td>')
                print('<td>' + ele[6].replace("####","'") + '</td>')
                print('<td>' + ele[7].replace("####","'") + '</td><tr>')
            print('''</table>''')
            
        except Exception as e:
            print("not found")
            print('Reason:', e)


    cursor.close()
    mydb.close()

