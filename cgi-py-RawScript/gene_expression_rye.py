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

# the 1th project from Guangwei Li
if expressiontable == 'rye_development_tbl':
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
    options = {'xAxis': {'categories': ['Root', 'Leaf', 'Stem', 'Spikelet', 'Flowering.5day', 'Flowering.10day', 'Flowering.15day', 'Seed.10DAF', 'Seed.20DAF', 'Seed.30DAF', 'Seed.40DAF']
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
    Li, G., Wang, L., Yang, J. et al. A high-quality genome assembly highlights rye genomic characteristics and agronomically important genes. Nat Genet (2021). <br><a href="https://doi.org/10.1038/s41588-021-00808-z" target="_blank">doi:10.1038/s41588-021-00808-z</a><br>''')

#the 2th project from Guangwei Li
if expressiontable == 'rye_cold_tbl':
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
    options = {'xAxis': {'categories': ['Root.Cold.0h', 'Root.Cold.1h', 'Root.Cold.4h', 'Root.Cold.8h', 'Leaf.Cold.0h','Leaf.Cold.1h', 'Leaf.Cold.4h', 'Leaf.Cold.8h']
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
    Li, G., Wang, L., Yang, J. et al. A high-quality genome assembly highlights rye genomic characteristics and agronomically important genes. Nat Genet (2021). <br><a href="https://doi.org/10.1038/s41588-021-00808-z" target="_blank">doi:10.1038/s41588-021-00808-z</a><br>''')

#the 3th project from Guangwei Li
if expressiontable == 'rye_drought_tbl':
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
    options = {'xAxis': {'categories': ['RootDrought0h','Root.Drought.3h', 'Root.Drought.6h', 'Root.Drought.12h', 'LeafDrought0h','Leaf.Drought.3h', 'Leaf.Drought.6h', 'Leaf.Drought.12h']
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
    Li, G., Wang, L., Yang, J. et al. A high-quality genome assembly highlights rye genomic characteristics and agronomically important genes. Nat Genet (2021). <br><a href="https://doi.org/10.1038/s41588-021-00808-z" target="_blank">doi:10.1038/s41588-021-00808-z</a><br>''')
print('</div>')
print('<div id="footer"></div>')

print('</body>')
print('</html>')

