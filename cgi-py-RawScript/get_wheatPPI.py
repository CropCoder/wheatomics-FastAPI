#!/usr/bin/env python2.7
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
print('<title>Wheat PPI</title>')
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
import subprocess

import MySQLdb


form = cgi.FieldStorage()

ppitable = form["query"].value  # 获取wheatPPI mysql
filter1 = form["filter"].value  # 获取wheatPPI mysql
name = form["ID"].value.strip().split()  # 获取输入的基因
web = "http://wheatomics.sdau.edu.cn/cgi-bin/geneDetail.py?search="

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
            if len(row) > 0:
                print('''<table class="table table-striped">
                <thead>
                <tr>
                <th class="card-title">WheatID1</th>
                <th class="card-title">WheatID2</th>
                <th class="card-title">eggNOGID1</th>
                <th class="card-title">eggNOGID2</th>
                <th class="card-title">Scores</th>
                <th class="card-title">Annotation1</th>
                <th class="card-title">Annotation2</th>
                </tr>
                </thead>
                <tbody>
                ''' )
                for ele in row:
                    a = []
                    b = []
                    for i in ele[1].split('#'):
                        if i in a:
                            pass
                        else:
                            a.append('<a href="'+ web + str(i.strip('.1')) + '" target="_blank">' + str(i) + '</a>')
                    for i in ele[2].split('#'):
                        if i in b:
                            pass
                        else:
                            b.append('<a href="'+ web + str(i.strip('.1')) + '" target="_blank">' + str(i) + '</a>')
                
                    print('<td>' + '<br>'.join(a) + '</td>')
                    print('<td>' + '<br>'.join(b) + '</td>')
                    print('<td><a href="http://plants.proteincomplexes.org/getInteractionsForOrthogroupID?OrthogroupID=' + ele[3] + '&Species=wheat" target="_blank">'+ ele[3]+ '</a></td>')
                    print('<td><a href="http://plants.proteincomplexes.org/getInteractionsForOrthogroupID?OrthogroupID=' + ele[4] + '&Species=wheat" target="_blank">'+ ele[4]+ '</a></td>')
                    print('<td>' + ele[5] + '</td>')
                    print('<td><font size=3>' + ele[6].replace("####","'") + '</font></td>')
                    print('<td><font size=3>' + ele[7].replace("####","'") + '</font></td><tr>')
                print('''<tbody>\n</table>''')
            else:
                print( gene + " was not found protein interactions in the database.")
        except Exception as e:
            print( gene + " was not found protein interactions in the database.")
            print('Reason:', e)


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
