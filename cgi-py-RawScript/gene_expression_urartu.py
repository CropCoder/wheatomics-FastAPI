#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
__author__ = 'shengwei ma'
__author_email__ = 'shengweima@icloud.com'

# this file like apache cgi file

from highcharts import Highchart # highcharts came from python-highcharts
import MySQLdb
import subprocess
import cgi
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

# the 1th project SRP072147
if expressiontable == 'SRP072147_tbl':
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
    options = {'xAxis': {'categories': ['0h_PI428193', '4h_PI428193', '24h_PI428193', '0h_PI428196', '4h_PI428196', '24h_PI428196', '0h_PI428198', '4h_PI428198', '24h_PI428198', '0h_PI428208', '4h_PI428208', '24h_PI428208', '0h_PI428211', '4h_PI428211', '24h_PI428211', '0h_PI428242', '4h_PI428242', '24h_PI428242', '0h_PI428266', '4h_PI428266', '24h_PI428266', '0h_PI428278', '4h_PI428278', '24h_PI428278', '0h_PI428282', '4h_PI428282', '24h_PI428282', '0h_PI428288', '4h_PI428288', '24h_PI428288', '0h_PI428294', '4h_PI428294', '24h_PI428294', '0h_PI428295', '4h_PI428295', '24h_PI428295', '0h_PI428298', '4h_PI428298', '24h_PI428298', '0h_PI428303', '4h_PI428303', '24h_PI428303', '0h_PI428307', '4h_PI428307', '24h_PI428307', '0h_PI428322', '4h_PI428322', '24h_PI428322', '0h_PI428328', '4h_PI428328', '24h_PI428328', '0h_PI428335', '4h_PI428335', '24h_PI428335', '0h_PI487265', '4h_PI487265', '24h_PI487265', '0h_PI487269', '4h_PI487269', '24h_PI487269']
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
        chart.add_data_set(value[0], series_type='line', dashStyle='ShortDash', name=key, tooltip={
            'pointFormat': '<span style="font-weight: bold; color: {series.color}">{series.name}</span>: <b>{point.y:.1f} TPM</b> <br>'
        })
    chart.save_file('/tmp/test')
    new_htmlcontent = chart.htmlcontent.replace('''"exporting": {}''','''"exporting":{"buttons": {"ContextButton": {"text": "Export data"}}}''')
    print(new_htmlcontent)

    print('''<br>  
    <br> 
    &nbsp &nbsp &nbsp &nbsp To understand the disease responses to powdery milldew, the diploid Triticum urartu were used as models for hexaploid wheat to perform RNA-seq induced by Bgt innoculation.
     <p>
    &nbsp &nbsp &nbsp &nbsp 1 Coexpression network analysis of the genes regulated by two types of resistance responses to powdery mildew in wheat. Juncheng Zhang, Hongyuan Zheng, Yiwen Li, Hongjie Li, Xin Liu, Huanju Qin, Lingli Dong, Daowen Wang <a href="https://www.ncbi.nlm.nih.gov/pubmed/27033636/"> Sci Rep. 2016; 6: 23805. Published online 2016 Apr 1. doi: 10.1038/srep23805 </a>''')

# the 2th project SRP104243
if expressiontable == 'SRP104243_tbl':
    for gene in name:
        errorbar = []
        select_sql = "select * from " + expressiontable + \
            " where" + " GeneID='" + gene + "';"
        select_sql_std = "select * from " + expressiontable + \
            "_std where" + " GeneID='" + gene + "';"
        try:
            cursor.execute(select_sql)
            row = cursor.fetchall()
            cursor.execute(select_sql_std)
            row_std = cursor.fetchall()
            row2 = row[0][1:]
            row2_std = row_std[0][1:]
            for r1, r2 in zip(list(row2[1:]), list(row2_std[1:])):
                errorbar.append([r1-r2, r1+r2])
            new = [list(row2[1:]), errorbar]
            data[row2[0]] = new

        except:
            print("not found")
    cursor.close()
    mydb.close()
    chart = Highchart(width=850, height=600)
    options = {'xAxis': {'categories': ['TMU38_seedling_root', 'TMU38_endosperm_6dpa', 'TMU06_endosperm_6dpa']
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
        chart.add_data_set(value[1], series_type='errorbar', name=key, tooltip={
            'pointFormat': '(error range: {point.low}-{point.high}TPM)<br/>'})
    chart.save_file('/tmp/test')
    new_htmlcontent = chart.htmlcontent.replace('''"exporting": {}''','''"exporting":{"buttons": {"ContextButton": {"text": "Export data"}}}''')
    print(new_htmlcontent)

    print('''<br>  
   <br>
   <br>
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Asymmetrical changes of gene expression, small RNAs and chromatin in two resynthesized wheat allotetraploids. Wu Jiao, Jingya Yuan, Shan Jiang, Yanfeng Liu, Lili Wang, Mingming Liu, Dewei Zheng, Wenxue Ye, Xiue Wang, Z. Jeffrey Chen <a href="https://www.ncbi.nlm.nih.gov/pubmed/29265531"> Plant J. 2017 Dec 18 Published online 2017 Dec 18. doi: 10.1111/tpj.13805 </a>''')

print('</div>')
print('<div id="footer"></div>')

print('</body>')
print('</html>')

