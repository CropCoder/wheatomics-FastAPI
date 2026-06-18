#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
__author__ = 'shengwei ma'
__author_email__ = 'shengweima@icloud.com'

# this file like apache cgi file

from highcharts import Highchart # highcharts came from python-highcharts
import MySQLdb
import subprocess
import cgi
from tabulate import tabulate

print("Content-Type: text/html")
print("")
print('<html>')
  
print('<head>')
print('<title>wheat expression</title>')
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
print('<br><h5 class="card-title">Gene Expression</h5><br>')

try:
    import cgitb
    cgitb.enable()
except:
    pass


form = cgi.FieldStorage()

expressiontable = form["expressiontable"].value  # 获取表达数据库
name = form["ID"].value.strip().split()  # 获取输入的基因

mydb = MySQLdb.connect(host='localhost',
                       user='wheatomics_user',
                       passwd='wheatomics115599',
                       db='gene_expression',
                       charset='utf8')
cursor = mydb.cursor()
data = dict()

# the 1th project from PmiREN
if expressiontable == 'miRNA_mature_tissue_tbl':
    for gene in name:
        select_sql = "select * from " + expressiontable + \
            " where" + " GeneID='" + gene + "';"
        try:
            cursor.execute(select_sql)
            row = cursor.fetchall()
            row2 = row[0][1:]
            new = [list(row2[1:])]
            data[row2[0]] = new

        except:
            print("not found")
    cursor.close()
    mydb.close()
    chart = Highchart(width=850, height=600)
    options = {'xAxis': {'categories': ['Flower','Grain','Leaf','Seed','Seedling','Spike','Whole plant']
                         # 'title': {'enabled': True, 'text': 'Tissue'}
                         },
               'chart': {
        'zoomType': 'xy'
    },
        'title': {
        'text': ''
    },
        'yAxis': {
        'title': {
            'text': 'Expression(TPM)'
        },
        'lineWidth': 2
    },
        'tooltip': {'shared': True},
    }

    chart.set_dict_options(options)
    for key, value in data.items():
        chart.add_data_set(value[0], series_type='column', name=key, tooltip={
            'pointFormat': '<span style="font-weight: bold; color: {series.color}">{series.name}</span>: <b>{point.y:.1f} TPM</b> '
        })
    print(chart.htmlcontent)

    print('''<br>  
    <br> 
    
     <p>
    &nbsp &nbsp &nbsp &nbsp PmiREN: a comprehensive encyclopedia of plant miRNAs. Z Guo, Z Kuang, Y Wang, Y Zhao, Y Tao, C Cheng,  J Yang, X Lu, C Hao,  T Wang, X Cao,  J Wei, L Li, and X Yang. Nucleic Acids Res. 2019. <a href="https://doi.org/10.1093/nar/gkz894"> doi: 10.1093/nar/gkz894 </a>''')


print('</div>')
print('<div id="footer"></div>')

print('</body>')
print('</html>')



