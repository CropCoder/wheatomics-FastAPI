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
print('<title>Gene ID Conversion</title>')
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
print('''<button style="color:white;background-color:#007DBC;border-color:#007BFF" id="button" onclick="download();">Download table</button>''')
print('<br>')
print('<br>')
print('<div id=seq>')
try:
    import cgitb
    cgitb.enable()
except:
    pass
import cgi

import MySQLdb



form = cgi.FieldStorage()

gene_version = form["gene_version"].value # 获取物种
name = form["ID"].value.strip().split()  # 获取输入的基因

mydb = MySQLdb.connect(host='localhost',
                       user='wheatomics_user',
                       passwd='wheatomics115599',
                       db='Convert_gene_id',
                       charset='utf8')
cursor = mydb.cursor()

null = ''

try:
    print('''<table class="table table-striped">
             <thead>
             <tr>
             <th class="card-title">Query Gene</th>
             <th class="card-title">Reference Gene</th>
             <th class="card-title">Code</th>
             <th class="card-title">Length</th>
             </tr>
             </thead>
             <tbody>
             ''')
    for geneid in name:
        try:
            select_sql = "select * from " + gene_version + " where" + " MIPS='" + geneid + "';"
            cursor.execute(select_sql)
            row = cursor.fetchone()
            print('<tr><td>' + row[1].encode('ascii') + '\t</td><td><a href="http://wheatomics.sdau.edu.cn/cgi-bin/geneDetail.py?search=' + row[2].encode('ascii').split('.')[0] + '" target="_blank">'+ row[2].encode('ascii')+'\t</a></td><td>' + row[3].encode('ascii') + '\t</td><td>' + row[4].encode('ascii') + '</tr>')
            
        except:
            null= null + str(geneid) + " was not found.<br>"
    print('''</tbody>\n</table>''')
    print('<br')
    print('<br>')
    print('<br>')
    print(null)
except:
    print ('error')       

cursor.close()
mydb.close()

print('</div>')
print('</div>')

print('''<script  type="text/javascript">
            function download(){
            var save = document.getElementById("seq").innerText;
            var save2 = save.trim().split("\\n").map(line => line.trim()).join("\\n");
            var blob = new Blob([save2], {type: "text/plain;charset=utf-8"});
            saveAs(blob, "IDConvert.txt");}
        </script>''')
print('<div id="footer"></div>')

print('</body>')
print('</html>')
