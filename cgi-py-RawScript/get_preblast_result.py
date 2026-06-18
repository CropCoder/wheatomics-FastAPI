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
print('<title>PreBLAST</title>')
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
print('<div style="padding-left:20%">')
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
print('<br>')
print('</div>')
print('</div>')
print('<div id="footer"></div>')

print('</body>')
print('</html>')

