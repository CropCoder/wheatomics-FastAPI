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
if expressiontable == 'PRJEB5314_paired_tbl':
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
    options = {'xAxis': {'categories': ['root_Z10', 'root_Z13', 'root_Z39', 'stem_Z30', 'stem_Z32', 'stem_Z65', 'leaf_Z10', 'leaf_Z23', 'leaf_Z71', 'spike_Z32', 'spike_Z39', 'spike_Z65', 'grain_Z71', 'grain_Z75', 'grain_Z85']                    
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

