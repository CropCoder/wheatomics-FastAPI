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

coexpressiontable = form["query"].value  # 获取wheatPPI mysql
filter1 = form["filter"].value  # 获取wheatPPI mysql
name = form["ID"].value.strip().split()  # 获取输入的基因

mydb = MySQLdb.connect(host='localhost',
                       user='wheatomics_user',
                       passwd='wheatomics115599',
                       db='coexpressiondb',
                       charset='utf8')
cursor = mydb.cursor()



if coexpressiontable == 'CO_result2':
    for gene in name:
        if '.' in filter1:
            filter2 = str((0 - float(filter1)))
            select_sql = "select * from " + coexpressiontable + \
            " where (Gene1= '" + gene + "' OR Gene2='" + gene + "') AND (PCC >=" + filter1 + " OR PCC <=" + filter2 + ") ORDER BY PCC DESC;"
            try:
                cursor.execute(select_sql)
                row = cursor.fetchall()
                print('''<table border="1">
                    <tr>
                    <th>Gene1</th>
                    <th>Gene2</th>
                    <th>PCC</th>
                    <th>MR</th>
                    </tr>
                    ''' )
                for ele in row:
                    print('<td>' + str(ele[1]) + '</td>')
                    print('<td>' + str(ele[2]) + '</td>')
                    print('<td>' + str('%.2f'%(float(ele[3]))) + '</td>')
                    print('<td>' + str(ele[4].split('.')[0]) + '</td><tr>')
                print('''</table>''')
            except Exception as e:
                print("not found")
                print('Reason:', e)
        if '.' not in filter1:
            select_sql = "select * from " + coexpressiontable + \
            " WHERE (Gene1='" + gene + "' OR Gene2='" + gene + "') AND MR <= " + filter1 + " ORDER BY MR+0 ASC;"
            try:
                cursor.execute(select_sql)
                row = cursor.fetchall()
                print('''<table border="1">
                    <tr>
                    <th>Gene1</th>
                    <th>Gene2</th>
                    <th>PCC</th>
                    <th>MR</th>
                    </tr>
                    ''' )
                for ele in row:
                    print('<td>' + str(ele[1]) + '</td>')
                    print('<td>' + str(ele[2]) + '</td>')
                    print('<td>' + str('%.2f'%(float(ele[3]))) + '</td>')
                    print('<td>' + str(ele[4].split('.')[0]) + '</td><tr>')
                print('''</table>''')
            except Exception as e:
                print("not found")
                print('Reason:', e)

if coexpressiontable == 'CO_PRJEB25639':
    for gene in name:
        if '.' in filter1:
            filter2 = str((0 - float(filter1)))
            select_sql = "select * from " + coexpressiontable + \
            " where (Gene1= '" + gene + "' OR Gene2='" + gene + "') AND (PCC >=" + filter1 + " OR PCC <=" + filter2 + ") ORDER BY PCC DESC;"
            try:
                cursor.execute(select_sql)
                row = cursor.fetchall()
                print('''<table border="1">
                    <tr>
                    <th>Gene1</th>
                    <th>Gene2</th>
                    <th>PCC</th>
                    <th>MR</th>
                    </tr>
                    ''' )
                for ele in row:
                    print('<td>' + str(ele[1]) + '</td>')
                    print('<td>' + str(ele[2]) + '</td>')
                    print('<td>' + str('%.2f'%(float(ele[3]))) + '</td>')
                    print('<td>' + str(ele[4].split('.')[0]) + '</td><tr>')
                print('''</table>''')
            except Exception as e:
                print("not found")
                print('Reason:', e)
        if '.' not in filter1:
            select_sql = "select * from " + coexpressiontable + \
            " WHERE (Gene1='" + gene + "' OR Gene2='" + gene + "') AND MR <= " + filter1 + " ORDER BY MR+0 ASC;"
            try:
                cursor.execute(select_sql)
                row = cursor.fetchall()
                print('''<table border="1">
                    <tr>
                    <th>Gene1</th>
                    <th>Gene2</th>
                    <th>PCC</th>
                    <th>MR</th>
                    </tr>
                    ''' )
                for ele in row:
                    print('<td>' + str(ele[1]) + '</td>')
                    print('<td>' + str(ele[2]) + '</td>')
                    print('<td>' + str('%.2f'%(float(ele[3]))) + '</td>')
                    print('<td>' + str(ele[4].split('.')[0]) + '</td><tr>')
                print('''</table>''')
            except Exception as e:
                print("not found")
                print('Reason:', e)


cursor.close()
mydb.close()

