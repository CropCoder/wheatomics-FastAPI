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

# the 1th project ERP022006
if expressiontable == 'ERP022006_tbl':
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
    options = {'xAxis': {'categories': ['Root 20days', 'Leaf 54days', 'Leaf 77days', 'Developing spike 1cm', 'Developing spike 1.5cm', 'Developing spike 2cm', 'Developing spike 2.5cm', 'Developing spike 3cm', 'Developing spike 3.5cm', 'Developing spike 4.5cm', 'Developing spike 5cm', 'Developing spike 5.5cm', 'Lemma 112days', 'Glume 112days', 'Flower 105days', 'Flower 110days', 'Flower 112days', 'Grain 123days', 'Grain 134days', 'Flag leaf 134days']
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
    chart.save_file('/tmp/test')
    new_htmlcontent = chart.htmlcontent.replace('''"exporting": {}''','''"exporting":{"buttons": {"ContextButton": {"text": "Export data"}}}''')
    print(new_htmlcontent)

    print('''<br>  
    <br> 
     <p>
    &nbsp &nbsp &nbsp &nbsp 1 Wild emmer genome architecture and diversity elucidate wheat evolution and domestication. Raz Avni, Moran Nave, Omer Barad, Kobi Baruch, Sven O. Twardziok, Heidrun Gundlach, Iago Hale, Martin Mascher, Manuel Spannagl, Krystalee Wiebe, et al.  <a href="https://www.ncbi.nlm.nih.gov/pubmed/28684525/"> Science. 2017 Jul 7; 357(6346): 93–97. doi: 10.1126/science.aan0032 </a>''')

#the 2th project kat2 muant
if expressiontable == 'kat2_tpm_mean_tbl':
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
    options = {'xAxis': {'categories': ['kat2', 'Kronos']
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
    chart.save_file('/tmp/test')
    new_htmlcontent = chart.htmlcontent.replace('''"exporting": {}''','''"exporting":{"buttons": {"ContextButton": {"text": "Export data"}}}''')
    print(new_htmlcontent)
    print('''<br>  
    <br> 
    &nbsp &nbsp &nbsp &nbsp This dataset was provided by Jin-Ying Gou from Fudan University.
    <p>
    &nbsp &nbsp &nbsp &nbsp For more information and any question, please contact :&nbsp;<a href="mailto:13148474750@163.com" class="">Jin-Ying Gou</a>
    ''')


print('</div>')
print('<div id="footer"></div>')

print('</body>')
print('</html>')

