#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = 'shengwei ma'
__author_email__ = 'shengweima@icloud.com'
import sys
reload(sys)

sys.setdefaultencoding('utf-8')

print ("Content-Type: text/html")
print ("")
print ("<html>")

try:
    import cgitb
    cgitb.enable()
except:
    pass
import cgi

import MySQLdb
import urllib2 


form = cgi.FieldStorage()

blastp_species = form["blastp_species"].value # 获取物种
name = form["ID"].value.strip()  # 获取输入的基因

mydb = MySQLdb.connect(host='localhost',
                       user='wheatomics_user',
                       passwd='wheatomics115599',
                       db='pre_blast',
                       charset='utf8')
cursor = mydb.cursor()


select_sql = "select * from " + blastp_species + " where" + " Geneid='" + name + "';"

try:
            cursor.execute(select_sql)
            row = cursor.fetchone()
            try:
                s = urllib2.urlopen(row[2]).read()
                print (s)
            except urllib2.HTTPError, e:
                print (e.code)
            except urllib2.URLErrror, e:
                print (str(e))
except:
    print (name + " not found")
cursor.close()
mydb.close()

