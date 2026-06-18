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
print("<!DOCTYPE html>")  
print('<head>')
print('<title>wheat expression</title>')
print('<link rel="shortcut icon" href="/favicon.ico" type="image/x-icon" />')
print('<link rel="stylesheet" href="/css/style.css" type="text/css" />')
print('<script src="/js/jquery/1.9.1/jquery.min.js" type=text/javascript></script>')
print('<link rel="stylesheet" href="/css/bootstrap-4.5.3-dist/css/bootstrap.css" type="text/css" />')
print('<script src="/css/bootstrap-4.5.3-dist/js/bootstrap.js" type=text/javascript></script>')
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

# the first bioproject PRJEB25639
if expressiontable == 'PRJEB25639_tbl':
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
    chart = Highchart(width=1000, height=700)
    options = {'xAxis': {'categories': ['radicle at Seedling stage', 'coleoptile at Seedling stage', 'roots at Seedling stage', 'stem axis at Seedling stage', 'shoot apical meristem at Seedling stage', 'first leaf sheath at Seedling stage', 'first leaf blade at Seedling stage', 'roots at three leaf stage', 'axillary roots at three leaf stage', 'root apical meristem at three leaf stage', 'third leaf sheath at three leaf stage', 'third leaf blade at three leaf stage', 'fifth leaf sheath at fifth leaf stage', 'fifth leaf blade at fifth leaf stage', 'roots at Tillering stage', 'root apical meristem at Tillering stage', 'shoot apical meristem at Tillering stage', 'shoot axis at Tillering stage', 'first leaf sheath at Tillering stage', 'first leaf blade at Tillering stage', 'roots at Flag leaf stage', 'shoot axis at Flag leaf stage', 'fifth leaf sheath at Flag leaf stage', 'fifth leaf blade at Flag leaf stage', 'flag leaf blade night (-0.25h) 06:45 at Flag leaf stage', 'flag leaf blade night (+0.25h) 07:15 at Flag leaf stage', 'fifth leaf blade night (-0.25h) 21:45 at Flag leaf stage', 'fifth leaf blade night (+0.25h) 22:15 at Flag leaf stage', 'flag leaf blade at Flag leaf stage', 'flag leaf sheath at Full boot', 'flag leaf blade at Full boot', 'leaf ligule at Full boot', 'shoot axis at Full boot', 'spike at Full boot', 'fifth leaf blade at Ear emergence', 'flag leaf sheath at Ear emergence', 'flag leaf blade at Ear emergence', 'Internode sec at Ear emergence', 'glumes at Ear emergence', 'lemma at Ear emergence', 'peduncle at Ear emergence', 'awns at Ear emergence', 'roots at 30% spike', 'Internode sec at 30% spike', 'flag leaf sheath at 30% spike', 'flag leaf blade at 30% spike', 'peduncle at 30% spike', 'spike at 30% spike', 'spikelets at 30% spike', 'flag leaf blade night (-0.25h) 06:45 at anthesis', 'fifth leaf blade night (-0.25h) 21:45 at anthesis', 'stigma & ovary at anthesis', 'anther at anthesis', 'fifth leaf blade (senescence) at milk grain stage', 'flag leaf sheath at milk grain stage', 'flag leaf blade at milk grain stage', 'Internode sec at milk grain stage', 'shoot axis at milk grain stage', 'glumes at milk grain stage', 'peduncle at milk grain stage', 'lemma at milk grain stage', 'awns at milk grain stage', 'grain at milk grain stage', 'flag leaf blade (senescence) at Dough', 'embryo proper at Dough', 'endosperm at Dough', 'grain at Soft dough', 'grain at Hard dough', 'flag leaf blade (senescence) at Ripening', 'grain at Ripening']
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
        chart.add_data_set(value[0], series_type='line', lineWidth=1, dashStyle='ShortDash', name=key, tooltip={
            'pointFormat': '<span style="font-weight: bold; color: {series.color}">{series.name}</span>: <b>{point.y:.1f} TPM</b> '
        })
        chart.add_data_set(value[1], series_type='errorbar', name=key, tooltip={
            'pointFormat': '(error range: {point.low}-{point.high}TPM)<br/>'})
    chart.save_file('/tmp/test')
    new_htmlcontent = chart.htmlcontent.replace('''"exporting": {}''','''"exporting":{"buttons": {"ContextButton": {"text": "Export data"}}}''')
    print(new_htmlcontent)

    print('''<p>
    &nbsp &nbsp &nbsp &nbsp 1 Shifting the limits in wheat research and breeding using a fully annotated reference genome. International Wheat Genome Sequencing C, investigators IRp, Appels R, Eversole K, Feuillet C, Keller B, et al. <a href="https://www.ncbi.nlm.nih.gov/pubmed/30115783">Science. 2018 Aug 17;361(6403). pii: eaar7191. doi: 10.1126/science.aar7191.</a>''')

# the second project PRJEB13569
if expressiontable == 'PRJEB13569_tbl':
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
    options = {'xAxis': {'categories': ['LIB21745', 'LIB21746', 'LIB21747', 'LIB21748', 'LIB21749', 'LIB21750', 'LIB21751', 'LIB21752']
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

    print('''<p>
    &nbsp &nbsp &nbsp &nbsp 1 Field Pathogenomics of Wheat Blast <a href="https://www.ncbi.nlm.nih.gov/bioproject/PRJEB13569">NCBI PRJEB13569</a>''')
 
 # the third project PRJEB5135
if expressiontable == 'PRJEB5135_tbl':
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
    options = {'xAxis': {'categories': ['Room1_10DPA', 'Room1_AL_20DPA', 'Room1_AL_20DPA_Extra', 'Room1_TC_20DPA', 'Room1_SE_20DPA', 'Room1_REF_20DPA', 'Room1_AL.SE_30DPA', 'Room1_SE_30DPA', 'Room2_10DPA', 'Room2_AL_20DPA', 'Room2_TC_20DPA', 'Room2_SE_20DPA', 'Room2_REF_20DPA', 'Room2_AL.SE_30DPA', 'Room2_SE_30DPA']
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

    print('''<p>
    &nbsp &nbsp &nbsp &nbsp 1 Genome interplay in the grain transcriptome of hexaploid bread wheat. Matthias Pfeifer, Karl G. Kugler, Simen R. Sandve, Bujie Zhan, Heidi Rudi, Torgeir R. Hvidsten, International Wheat Genome Sequencing Consortium, Klaus F. X. Mayer, Odd-Arne Olsen <a href="https://www.ncbi.nlm.nih.gov/pubmed/25035498">Science. 2014 Jul 18; 345(6194): 1250091. doi: 10.1126/science.1250091</a>''')

# the fourth project PRJEB5134
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

    print('''<p>
    &nbsp &nbsp &nbsp &nbsp 1 A chromosome-based draft sequence of the hexaploid bread wheat (Triticum aestivum) genome. International Wheat Genome Sequencing Consortium (IWGSC) <a href="https://www.ncbi.nlm.nih.gov/pubmed/25035500">Science 2014, doi: 10.1126/science.1251788</a>''')

# the fifth project PRJEB5134_single
if expressiontable == 'PRJEB5314_single_tbl':
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
    options = {'xAxis': {'categories': ['root', 'stem', 'leaf', 'spike', 'grain']                       
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

    print('''<p>
    &nbsp &nbsp &nbsp &nbsp 1 A chromosome-based draft sequence of the hexaploid bread wheat (Triticum aestivum) genome. International Wheat Genome Sequencing Consortium (IWGSC) <a href="https://www.ncbi.nlm.nih.gov/pubmed/25035500">Science 2014, doi: 10.1126/science.1251788</a>''')

# the six project PRJDB2496
if expressiontable == 'PRJDB2496_tbl':
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
    options = {'xAxis': {'categories': ['root_0day', 'root_10day_-P', 'shoot_0day', 'shoot_10day_-P']                        
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

    print('''<p>
    &nbsp &nbsp &nbsp &nbsp 1 Characterisation of the wheat (triticum aestivum L.) transcriptome by de novo assembly for the discovery of phosphate starvation-responsive genes: gene expression in Pi-stressed wheat
Youko Oono, Fuminori Kobayashi, Yoshihiro Kawahara, Takayuki Yazawa, Hirokazu Handa, Takeshi Itoh, Takashi Matsumoto. <a href="https://www.ncbi.nlm.nih.gov/pubmed/23379779">BMC Genomics. 2013; 14: 77. Published online 2013 Feb 4. doi: 10.1186/1471-2164-14-77</a>''')

# the seven project PRJEB5029
if expressiontable == 'PRJEB5029_tbl':
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
    options = {'xAxis': {'categories': ['latent_lepto', 'diplo_dia', 'zygo_pachy', 'metaphaseI']
                         
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

    print('''<p>
    &nbsp &nbsp &nbsp &nbsp 1 meiose non oriented RNA-Seq data <a href="https://www.ncbi.nlm.nih.gov/bioproject/237154"> PRJEB5029, INRA Clermont-Ferrand - Theix</a>''')

# the eighth project PRJEB24686
if expressiontable == 'PRJEB24686_tbl':
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
    options = {'xAxis': {'categories': ['2618H2ORACH', '2618_FG_RACH', '2618_H2O_SP', '2618_FG_SP', '2890_H2O_SP', '2890_FG_SP', '2890_H2O_RACH', '2890_FG_RACH']
                         
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

    print('''<p>
    &nbsp &nbsp &nbsp &nbsp 1 Comparative Transcriptome Profiles of Near-Isogenic Hexaploid Wheat Lines Differing for Effective Alleles at the 2DL FHB Resistance QTL
Chiara Biselli, Paolo Bagnaresi, Primetta Faccioli, Xinkun Hu, Margaret Balcerzak, Maria G. Mattera, Zehong Yan, Therese Ouellet, Luigi Cattivelli, Giampiero Valè. <a href="https://www.ncbi.nlm.nih.gov/pubmed/29434615"> Front Plant Sci. 2018; 9: 37. Published online 2018 Jan 30. doi: 10.3389/fpls.2018.00037</a>''')

# the ninth project PRJNA327013
if expressiontable == 'PRJNA327013_tbl':
    for gene in name:
        errorbar = []
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
    options = {'xAxis': {'categories': ['Mock1-3dpi', 'Mock2-3dpi', 'Mock3-3dpi', 'Mock2-24dpi', 'Mock3-24dpi', 'Mock5-24dpi', '1A5-10-7d_R1', '1A5-1-7d_R1', '1A5-7-7d_R1', '1A5-3-12d_R1', '1A5-5-12d_R1', '1A5-7-12d_R1', '1A5-10-14d_R1', '1A5-8-14d_R1', '1A5-9-14d_R1', '1E4-4-7d_R1', '1E4-5-7d_R1', '1E4-6-7d_R1', '1E4-3-12d_R1', '1E4-6-12d_R1', '1E4-7-12d_R1', '1E4-10-14d_R1', '1E4-5-14d_R1', '1E4-8-14d_R1', '3D1-1-7d_R1', '3D1-2-7d_R1', '3D1-3-7d_R1', '3D1-2-12d_R1', '3D1-5-12d_R1', '3D1-8-12d_R1', '3D1-10-14d_R1', '3D1-7-14d_R1', '3D1-9-14d_R1', '3D7-10-7d_R1', '3D7-2-7d_R1', '3D7-8-7d_R1', '3D7-2-12d_R1', '3D7-3-12d_R1', '3D7-3-12d-rep', '3D7-6-12d_R1', '3D7-4-14d_R1', '3D7-5-14d_R1']
                         
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
    print('''Some samples (SRR3724140,SRR3724142,SRR3724145,SRR3724167,SRR3724169,SRR3724171,SRR3724076,SRR3724079,SRR3724081,SRR3724102,SRR3724108,SRR3724104 and SRR3724106) were removed because of low mapping rate.''')
    print('''<p>
    &nbsp &nbsp &nbsp &nbsp 1 RNAseq of wheat leaves (cultivar drifter) infected with different strains of Zymoseptoria tritici <a href="https://www.ncbi.nlm.nih.gov/bioproject/PRJNA327013"> Comparative transcriptomics of Zymoseptoria tritici isolates</a>''')


# the 10th project PRJNA263755
if expressiontable == 'PRJNA263755_tbl':
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
    options = {'xAxis': {'categories': ['1A_mock_3dpi', '1A_mock_5dpi', '1A_fusarium_3dpi', '1A_fusarium_5dpi', '1B_mock_3dpi', '1B_mock_5dpi', '1B_fusarium_3dpi', '1B_fusarium_5dpi', '2A_fusarium_5dpi', '2B_fusarium_5dpi', '3A_fusarium_5dpi', '3B_fusarium_5dpi', '4A_fusarium_5dpi', '4B_fusarium_5dpi', '9A_fusarium_5dpi', '9B_fusarium_5dpi']
                         
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

    print('''<p>
    &nbsp &nbsp &nbsp &nbsp 1 Transcriptome and Allele Specificity Associated with a 3BL Locus for Fusarium Crown Rot Resistance in Bread Wheat.
Jian Ma, Jiri Stiller, Qiang Zhao, Qi Feng, Colin Cavanagh, Penghao Wang, Donald Gardiner, Frédéric Choulet, Catherine Feuillet, You-Liang Zheng, Yuming Wei, Guijun Yan, Bin Han, John M. Manners, Chunji Liu. <a href="https://www.ncbi.nlm.nih.gov/pubmed/25405461"> PLoS One. 2014; 9(11): e113309. Published online 2014 Nov 18. doi: 10.1371/journal.pone.0113309</a>''')

# the 11th project PRJNA325489
if expressiontable == 'PRJNA325489_tbl':
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
    options = {'xAxis': {'categories': ['KNI', 'KNII', 'KNIII', 'KNIV', 'KNV', 'KNVI']
                         
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

    print('''<p>
    &nbsp &nbsp &nbsp &nbsp 1 A Genome-wide View of Transcriptome Dynamics During Early Spike Development in Bread Wheat.
Li, Yongpeng and Fu, Xing and Zhao, Meicheng and Zhang, Wei and Li, Bo and An, Diaoguo and Li, Junming and Zhang, Aimin and Liu, Renyi and Liu, Xigang. <a href="https://www.ncbi.nlm.nih.gov/pubmed/30337587"> Scientific Reports DOI:10.1038/s41598-018-33718-y</a>''')

# the 12th project PRJEB12358
if expressiontable == 'PRJEB12358_tbl':
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
    options = {'xAxis': {'categories': ['NIL38_M3', 'NIL38_F3', 'NIL38_M6', 'NIL38_F6', 'NIL38_M12', 'NIL38_F12', 'NIL38_M24', 'NIL38_F24', 'NIL38_M36', 'NIL38_F36', 'NIL38_M48', 'NIL38_F48', 'NIL51_M3', 'NIL51_F3', 'NIL51_M6', 'NIL51_F6', 'NIL51_M12', 'NIL51_F12', 'NIL51_M24', 'NIL51_F24', 'NIL51_M36', 'NIL51_F36', 'NIL51_M48', 'NIL51_F48']
                         
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

    print('''<p>
    &nbsp &nbsp &nbsp &nbsp 1 Suppressed recombination and unique candidate genes in the divergent haplotype encoding Fhb1, a major Fusarium head blight resistance locus in wheat.
W. Schweiger, B. Steiner, S. Vautrin, T. Nussbaumer, G. Siegwart, M. Zamini, F. Jungreithmeier, V. Gratl, M. Lemmens, K. F. X. Mayer, H. Bérgès, G. Adam, H. Buerstmayr <a href="https://www.ncbi.nlm.nih.gov/pubmed/27174222"> Theor Appl Genet. 2016; 129: 1607–1623. Published online 2016 May 12. doi: 10.1007/s00122-016-2727-x</a>''')

# the 13th project PRJEB21835
if expressiontable == 'PRJEB21835_tbl':
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
    options = {'xAxis': {'categories': ['Control_Root', 'Xt_Root', 'Control_Leaf', 'Xt_Leaf']
                         
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
    <p> &nbsp &nbsp &nbsp &nbsp This study aimed at decrypting the transcriptomic response of 2 months-old grown tender wheat (cv Chinese Spring) to a the Xanthomonas translucens pathogen infection by infiltration. The response was monitored by RNAseq 24h post leaf clipping. Triticum aestivum cv. Chinese Spring plants were maintained in a growth chamber with cycles of 12 h of light at 21°C and 50% relative humidity (RH) and 12 h of dark at 21°C and 50% RH. Leaves of 49 days-old plants were infiltrated with a bacterial suspension in water with an optical density at 600 nm (OD600) of 0.5 using a needleless syringe. Plants inoculated with water were used as controls. For transcriptomic and proteomic analyses, leaves and root tissues were harvested 1 day post-inoculation (dpi), when symptoms were not visible yet. Three biological replicates per treatment were performed, and each with pooled leaves from two independent plants per replicate. The files per conditions and replicates are:Sample 1 Root tissue with 3 replicates: CONTROL * control condition for roots (wheat without pathogen infection): 3 replicates: 1.1R,1.2R, 1.3R * control condition for leaves (wheat without pathogen infection): 3 replicates1.1L,1.2L, 1.3L * Wheat Roots infected by Xanthomonas translucens: 3 replicates: 5.1R, 5.2R, 5.3R * Wheat Leaves infected by Xanthomonas translucens: 3 replicates: 5.1L, 5.2L, 5.3L<p>
    <br>
    <br>
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 RNA-seq of wheat leaves and roots in response to Xanthomonas translucens infection <a href="https://www.ncbi.nlm.nih.gov/bioproject/PRJEB21835/"> PRJEB21835</a>''')

# the 14th project PRJEB21874
if expressiontable == 'PRJEB21874_tbl':
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
    options = {'xAxis': {'categories': ['MycorhizalFungiLeaf', 'MycorhizalFungiXanthomonasLeaf', 'MycorhizalFungiRoot', 'MycorhizalFungiXanthomonasRoot']
                         
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
    <p> &nbsp &nbsp &nbsp &nbsp We monitored by RNAseq the transcriptomic response of roots and leaves of Triticum aestivum cv chinese Spring during a long term interaction with Funneliformis mossae (2 months) with or without a pathogen infection by infiltration of Xanthomonas translucens CFBP 2054. The control condition of roots and leaves wheat without mycorhizal fungi is in E-MTAB-5891 (material produced simultaneously and treated at the same time).<p>
    <br>
    <br>
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Accession: PRJEB21874 ID: 474303
RNAseq of roots and leaves of tender wheat (Triticum aestivum cv chinese Spring) during interactions with mycorhizal fungi (Funneliformis mossae) with and without a pathogen attack by Xanthomonas translucens <a href="https://www.ncbi.nlm.nih.gov/bioproject/PRJEB21874/"> PRJEB21874</a>''')

# the 15th project PRJEB22854
if expressiontable == 'PRJEB22854_tbl':
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
    options = {'xAxis': {'categories': ['Grain_15dpa', 'Grain_15dpa_dark', 'Grain_20dpa', 'Grain_20dpa_dark']
                         
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
    <p> &nbsp &nbsp &nbsp &nbsp Purple-grain wheat are caused by anthocyanin accumulation in the seed coat. But little is known about molecular mechanism of anthocyanin biosynthesis. The anthocyanin biosynthesis and accumulation were affected by light in purple-grain wheat. The spikes of purple-grain wheat Luozhen No.1 were bagged with four-layer Kraft paper bags after pollination. To identify genes involved in the anthocyanin biosynthesis, we sequenced four pericarp cDNA libraries, D15 (15 DAP), D20 (20 DAP) of shading treatment, and L15 (15 DAP), L20 (20 DAP) of untreated control using an Illumina HiSeqTM 2000. After quality control, raw reads are filtered into clean reads which will be aligned to the reference sequences. The alignment data is utilized to calculate distribution of reads on reference genes and mapping ratio, and proceed with downstream analysis including gene and isoform expression, deep analysis based on gene expression (PCA/correlation/screening differentially expressed genes and so on),exon expression, gene structure refinement, alternative splicing, novel transcript prediction and annotation, SNP detection, Indel detection. Further, we also perform deep analysis based on different expression genes, including Gene Ontology (GO) enrichment analysis, Pathway enrichment analysis, cluster analysis, and finding transcriptor factor.<p>
    <br>
    <br>
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 RNA-seq of pericarp of purple-grain wheat Luozhen No.1 of 15 days (D15) and 20 days (D20) shading treatment after pollination, against 15 DAP, 20 DAP untreated controls. <a href="https://www.ncbi.nlm.nih.gov/bioproject/?term=PRJEB22854"> PRJEB22854</a>''')

# the 16th project PRJEB23056
if expressiontable == 'PRJEB23056_tbl':
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
    options = {'xAxis': {'categories': ['H2O', 'H2O_30min', 'H2O_180min', 'Flag22_30min', 'Flag22_180min', 'Chitin_30min', 'Chitin_180min']
                         
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
    <p>&nbsp &nbsp &nbsp &nbsp Chinese Spring wheat plants were grown for 3 weeks in a growth cabinet under a 16:8 hours day:night regime at 23:18 °C. For each biological repetition three strips (2 cm) where cut from leaf 2 and 3, placed in a 2 ml tube with sterile water and vacuum-infiltrated for 3 times for 1 minute. The following day water was removed and replaced by fresh water or PAMPs dissolved in water at 1 g/l for chitin (Nacosy, YSK, Japan) or 500 nM flg22 (www.peptron.com). Samples were drained and flash frozen in liquid Nitrogen after 30 or 180 min prior to pulverisation with 2 stainless steel balls in a Geno/Grinder (SPEX). <p>
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Physical and transcriptional organisation of the bread wheat intracellular immune receptor repertoire. <a href="http://dx.doi.org/10.1101/339424"> bioRxiv preprint first posted online Jun. 5, 2018.</a>''')

# the 17th project PRJEB25586
if expressiontable == 'PRJEB25586_tbl':
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
    options = {'xAxis': {'categories': ['CS_Ph1_minus', 'CS_Ph1_plus']
                         
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
    <p>&nbsp &nbsp &nbsp &nbsp <option VALUE="PRJEB25586_tbl"> early meiosis in wheat in the presence and absence of the Ph1 locus <p>
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Genome-Wide Transcription During Early Wheat Meiosis Is Independent of Synapsis, Ploidy Level, and the Ph1 Locus <a href="https://doi.org/10.3389/fpls.2018.01791"> Front. Plant Sci., 04 December 2018 | https://doi.org/10.3389/fpls.2018.01791</a>''')

# the 18th project PRJEB7795
if expressiontable == 'PRJEB7795_tbl':
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
    options = {'xAxis': {'categories': ['endosperm_12DPA', 'inner_pericarp_12DPA','outer_pericarp_12DPA']                     
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
    <p>&nbsp &nbsp &nbsp &nbsp  Construction protocol: Immature grain at 12 days post-anthesis were collected from floret positions 1 & 2 of spikelets in the central 3/4 of the ears. Three tissue layers were isolated by manual dissection: the 'outer pericarp', which included the cuticle, outer epidermis, hypodermis and parenchyma cells; the 'inner pericarp' which comprised the cross cells, inner epidermis, integuments and aleurone; and the endosperm. Tissues were frozen in liquid nitrogen and stored at -80oC Plants growth in 15cm pots of a peat and loam-based compost in a glasshouse: 16 hr day (), 8 hr night (). Plant were tagged at anthesis. RNA was extracted according to Wan et al. (2009) Plant Biotechnol J 7, 401-410. Libraries were prepared using the Illumina TruSeq mRNA sample kit using 4ug of total RNA as described in the Illumina TruSeq RNA sample preparation guide, Part 15008136 Rev A, Nov 2010.
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Tissue layers from developing wheat grain at 12 days post-anthesis <a href="https://www.ncbi.nlm.nih.gov/bioproject/PRJEB7795"> PRJEB7795</a>''')

# the 19th project PRJEB8762
if expressiontable == 'PRJEB8762_tbl':
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
    options = {'xAxis': {'categories': ['12℃', '24℃']
                         
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
    
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 A genome-wide survey of DNA methylation in hexaploid wheat. Laura-Jayne Gardiner, Mark Quinton-Tulloch, Lisa Olohan, Jonathan Price, Neil Hall, Anthony Hall <a href="https://www.ncbi.nlm.nih.gov/pubmed/26653535/"> Genome Biol. 2015; 16: 273. Published online 2015 Dec 10. doi: 10.1186/s13059-015-0838-3 </a>''')

# the 20th project PRJEB8798
if expressiontable == 'PRJEB8798_tbl':
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
    options = {'xAxis': {'categories': ['Mock_1dpi', 'Mock_4dpi', 'Mock_9dpi', 'Mock_14dpi', 'Mock_21dpi', 'Inoculation_1dpi', 'Inoculation_4dpi', 'Inoculation_9dpi', 'Inoculation_14dpi', 'Inoculation_21dpi']                        
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
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Transcriptome and metabolite profiling of the infection cycle of Zymoseptoria tritici on wheat reveals a biphasic interaction with plant immunity involving differential pathogen chromosomal contributions and a variation on the hemibiotrophic lifestyle definition. Jason J. Rudd, Kostya Kanyuka, Keywan Hassani-Pak, Mark Derbyshire, Ambrose Andongabo, Jean Devonshire, Artem Lysenko, Mansoor Saqi, Nalini M. Desai, Stephen J. Powers, Juliet Hooper, Linda Ambroso, Arvind Bharti, Andrew Farmer, Kim E. Hammond-Kosack, Robert A. Dietrich, Mikael Courbot. <a href="https://www.ncbi.nlm.nih.gov/pubmed/25596183"> Plant Physiol. 2015 Mar; 167(3): 1158–1185. Published online 2015 Jan 16. doi: 10.1104/pp.114.255927 </a>''')

# the 21th project PRJNA243835
if expressiontable == 'PRJNA243835_powdery_tbl':
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
    options = {'xAxis': {'categories': ['non-innoculation', 'Powdery24h', 'Powdery48h', 'Powdery72h']                     
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
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Large-scale transcriptome comparison reveals distinct gene activations in wheat responding to stripe rust and powdery mildew. <a href="https://www.ncbi.nlm.nih.gov/pubmed/25318379"> BMC Genomics. 2014; 15(1): 898. Published online 2014 Oct 15. doi: 10.1186/1471-2164-15-898 </a>''')

# the 22th project PRJNA243835
if expressiontable == 'PRJNA243835_stripe_tbl':
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
    options = {'xAxis': {'categories': ['non-innoculation', 'Stripe24h', 'Stripe48h', 'Stripe72h']
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
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Large-scale transcriptome comparison reveals distinct gene activations in wheat responding to stripe rust and powdery mildew. <a href="https://www.ncbi.nlm.nih.gov/pubmed/25318379"> BMC Genomics. 2014; 15(1): 898. Published online 2014 Oct 15. doi: 10.1186/1471-2164-15-898 </a>''')

# the 23th project PRJNA253535
if expressiontable == 'PRJNA253535_tbl':
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
    options = {'xAxis': {'categories': ['wheat23℃', 'wheat4℃']
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
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Understanding the biochemical basis of temperature-induced lipid pathway adjustments in plants. Qiang Li, Qian Zheng, Wenyun Shen, Dustin Cram, D. Brian Fowler, Yangdou Wei, Jitao Zou <a href="https://www.ncbi.nlm.nih.gov/pubmed/25564555"> Plant Cell. 2015 Jan; 27(1): 86–103. Published online 2015 Jan 6. doi: 10.1105/tpc.114.134338 </a>''')

# the 24th project PRJNA257938
if expressiontable == 'PRJNA257938_tbl':
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
    options = {'xAxis': {'categories': ['control', 'drought_1h', 'drought_6h', 'heat_1h', 'heat_6h', 'drough&theat_1h', 'drought&heat_6h']
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
    <br> &nbsp &nbsp &nbsp &nbsp Design: we performed deep sequencing of 1-week old wheat seedling leaves subjected to drought stress, heat stress and their combination before (0h) and after stress (1h or 6h) using the Illumina sequencing platform, and two biological replicates were conducted for each sample.
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Temporal transcriptome profiling reveals expression partitioning of homeologous genes contributing to heat and drought acclimation in wheat (Triticum aestivum L.). Zhenshan Liu, Mingming Xin, Jinxia Qin, Huiru Peng, Zhongfu Ni, Yingyin Yao, Qixin Sun. <a href="https://www.ncbi.nlm.nih.gov/pubmed/26092253"> BMC Plant Biol. 2015; 15: 152. Published online 2015 Jun 20. doi: 10.1186/s12870-015-0511-8</a>''')


# the 25th project PRJNA273659
if expressiontable == 'PRJNA273659_tbl':
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
    options = {'xAxis': {'categories': ['Fhb1-Water_12hai', 'Fhb1+Water12hai', 'Fhb1-DON12hai', 'Fhb1+DON12hai', 'Fhb1-F.graminearum96haiRep1','Fhb1-F.graminearumrep2','Fhb1+F.graminearum96haiRep1', 'Fhb1+F.graminearum96haiRep2']
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
            'pointFormat': '<span style="font-weight: bold; color: {series.color}">{series.name}</span>: <b>{point.y:.1f} TPM</b><br/>'
        })
    new_htmlcontent = chart.htmlcontent.replace('''"exporting": {}''','''"exporting":{"buttons": {"ContextButton": {"text": "Export data"}}}''')
    print(new_htmlcontent)

    print('''<br>  
    <br> &nbsp &nbsp &nbsp &nbsp Design: The fungal pathogen Fusarium graminearum infects wheat spikes and causes Fusarium head blight (FHB). During infection the fungus produces a set of trichothecene mycotoxins (e.g. deoxynivalenol or DON) that increase the virulence of the fungus and result in reduced grain quality. The Fhb1 resistant allele confers type II resistance (reduced spread of symptoms on the spike) to F. graminearum infection. This study examined differentially expressed genes from a wheat near-isogenic line pair carrying resistant and susceptible alleles for the Fhb1 locus. The NIL pair for Fhb1 was derived from self pollinating a F7-derived line that was heterozygous for the Fhb1 region and identifying Fhb1+ (resistant) and Fhb1- (susceptible) lines. The wheat NIL pair 260-1-1-2 (Fhb1+) and 260-1-1-4 (Fhb1-) was used for this study. Spikelet and rachis tissue was sampled after inoculation with F. graminearum, DON, or water. For the F. graminearum-inoculated samples, wheat spikes were point inoculated with F. graminearum (10µl of 100,000 macroconidia per ml) in the four central spikelets and the inoculated spikelet and corresponding rachis were sampled at 96 hours after inoculation (hai). For the DON- and water-inoculated samples, wheat spikes were point inoculated with DON (2ug) and water on the four central spikelets, and the inoculated spikelets were sampled at 12 hai. The goal of this study was to identify plant and fungal genes that are differentially expressed between plants carrying the resistant and susceptible alleles for the Fhb1 locus.
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Triticum aestivum Transcriptome or Gene expression. <a href="https://www.ncbi.nlm.nih.gov/bioproject/PRJNA273659"> PRJNA273659</a>''')

# the 26th project PRJNA297822
if expressiontable == 'PRJNA297822_tbl':
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
    options = {'xAxis': {'categories': ['Chara_Mock', 'Chara_Fp']
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
    <br> &nbsp &nbsp &nbsp &nbsp Design: Bread wheat (Triticum aestivum L.) is an allopolyploid species that contains three ancestral genomes. Therefore, potentially three homoeologous copies exist for any given gene in the wheat genome. Whether different homoeologs are differentially expressed (homoeolog expression bias) in response to biotic and abiotic stresses in wheat is poorly understood. In this study, we used an RNA-seq approach to analyze homoeolog-specific global gene expression patterns during infection by the fungal pathogen Fusarium pseudograminearum, which causes crown rot disease. We substantially increased the number of known homoeologous gene sets in wheat. Our analyses revealed patterns of differential expression among homoeologs under both control and infection conditions, indicating homoeolog expression bias underpins a large proportion of the wheat transcriptome. We found that B and D subgenomes disproportionately contributed to differentially expressed genes during plant defense. Furthermore, we observed that the degree of responsiveness to pathogen infection varied among homoeologous genes and we use the term “homoeolog induction bias” to refer to this phenomenon. Further understanding how homoeolog expression and induction bias impacts biotic stress responses will assist the improvement of biotic stress tolerance in elite wheat cultivars. 
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 The defence-associated transcriptome of hexaploid wheat displays homoeolog expression and induction bias. Jonathan J. Powell, Timothy L. Fitzgerald, Jiri Stiller, Paul J. Berkman, Donald M. Gardiner, John M. Manners, Robert J. Henry, Kemal Kazan <a href="https://www.ncbi.nlm.nih.gov/pubmed/27735125/"> Plant Biotechnol J. 2017 Apr; 15(4): 533–543. Published online 2016 Nov 11. doi: 10.1111/pbi.12651</a>''')


# the 27th project PRJNA297977
if expressiontable == 'PRJNA297977_tbl':
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
    options = {'xAxis': {'categories': ['microspore embryogenesis S1', 'microspore embryogenesis S2', 'microspore embryogenesis S3']
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
    <br> &nbsp &nbsp &nbsp &nbsp Design: We performed mRNA and sRNA transcriptome sequencing of three stages from wheat microspore embryogenesis induction to generate the first sequencing based resource of mRNA and sRNA expression of microspore embryogensis induction. 
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Analysis of wheat microspore embryogenesis induction by transcriptome and small RNA sequencing using the highly responsive cultivar "Svilena". Felix Seifert, Sandra Bössow, Jochen Kumlehn, Heike Gnad, Stefan Scholten <a href="https://www.ncbi.nlm.nih.gov/pubmed/27098368"> BMC Plant Biol. 2016; 16: 97. Published online 2016 Apr 21. doi: 10.1186/s12870-016-0782-8 </a>''')

# the 28th project PRJNA306536
if expressiontable == 'PRJNA306536_tbl':
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
    options = {'xAxis': {'categories': ['PEG6000_0h_Giza168', 'PEG600_02h_Giza168', 'PEG6000_12h_Giza168', 'PEG6000_0h_Gemmiza10', 'PEG6000_2h_Gemmiza10', 'PEG6000_12h_Gemmiza10']
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
    <br> &nbsp &nbsp &nbsp &nbsp Design: genotypes, Giza 168 (or GZ168) as the tolerant cultivar and Gemmiza 10 (or GM10) as the sensitive cultivar
    <p>
    &nbsp &nbsp &nbsp &nbsp 1  <a href="https://www.ncbi.nlm.nih.gov/bioproject/?term=PRJNA306536"> PRJNA306536 </a>''')

# the 29th project PRJNA307237
if expressiontable == 'PRJNA307237_tbl':
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
    options = {'xAxis': {'categories': ['DBF-L1', 'DAF-L2', 'DAF-L3', 'DAF-L4', 'DAF-L5']
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
    new_htmlcontent = chart.htmlcontent.replace('''"exporting": {}''','''"exporting":{"buttons": {"ContextButton": {"text": "Export data"}}}''')
    print(new_htmlcontent)

    print('''<br>  
    <br> &nbsp &nbsp &nbsp &nbsp Design: The flag leaf was collected at the heading stage, first flowering date (0DAA), 15 days after anthesis (DAA), 25DAA, and 30DAA. At each time point, tissues were harvested from fifteen randomly selected tillers. Total RNA was extracted using the RNA extraction kit, following the manufacturer’s protocol (Bioteke, Beijing, China). Ten equimolar high-quality RNA samples for each time point were mixed. The library was constructed using NEBNext® Ultra™ RNA Library Prep Kit for Illumina® (NEB, USA) following manufacturer’s protocol. Briefly, mRNA was purified from total RNA using poly-T oligo-attached magnetic beads, and then fragmented using divalent cations under elevated temperature . First strand cDNA was synthesized using random hexamer primer and M-MuLV Reverse Transcriptase(RNase H-). Second strand cDNA synthesis was subsequently performed using DNA Polymerase I and RNase H. Remaining overhangs were converted into blunt ends via exonuclease/polymerase activities. After adenylation of 3’ ends of DNA fragments, NEBNext Adaptor with hairpin loop structure were ligated to prepare for hybridization. In order to select cDNA fragments of preferentially 150~200 bp in length, the library fragments were purified with AMPure XP system (Beckman Coulter, Beverly, USA). Then 3 µl USER Enzyme (NEB, USA) was used with size-selected, adaptor-ligated cDNA at 37 ? for 15 min followed by 5 min at 95 ? before PCR. Then PCR was performed with Phusion High-Fidelity DNA polymerase, Universal PCR primers and Index (X) Primer. At last, PCR products were purified (AMPure XP system) and library quality was assessed on the Agilent Bioanalyzer 2100 system.
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Transcriptome analysis of flag leaf during its senescence in wheat. <a href="https://www.ncbi.nlm.nih.gov/bioproject/PRJNA307237"> PRJNA307237</a>''')

# the 30th project PRJNA307989
if expressiontable == 'PRJNA307989_tbl':
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
    options = {'xAxis': {'categories': ['FHB', 'GA','ABA']
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
   
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Examining the effects of F. graminearum infection on FHB susceptible wheat cultivar 'fielder'. <a href="https://www.ncbi.nlm.nih.gov/bioproject/PRJNA307989"> PRJNA307989 </a>''')

# the 31th project PRJNA325136
if expressiontable == 'PRJNA325136_tbl':
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
    options = {'xAxis': {'categories': ['Columbus_0dpi', 'ColumbusNS765_0dpi', 'ColumbusNS766_0dpi', 'Columbus_2dpi', 'ColumbusNS765_2dpi', 'ColumbusNS766_2dpi', 'Columbus_5dpi', 'ColumbusNS765_5dpi', 'ColumbusNS766_5dpi']
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
   &nbsp &nbsp &nbsp &nbsp To characterise a recently discovered stem rust resistance locus on wheat chromosome 7AL. Transcriptome analysis by RNA-sequencing, in association with microscopic observations, was used to compare responses to the Puccinia graminis f. sp. tritici pathogen of the susceptible line Columbus, and two independent backcrossed resistant lines containing the locus, Columbus-NS765 and Columbus-NS766.
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Cellular and molecular characterization of a stem rust resistance locus on wheat chromosome 7AL.Pujol, V., Robles, J., Wang, P., Taylor, J., Zhang, P., Huang, L., Tabe, L., … Lagudah, E. <a href="https://www.ncbi.nlm.nih.gov/pubmed/27927228"> BMC research notes, 9(1), 502. doi:10.1186/s13104-016-2320-z </a>''')

# the 32th project PRJNA327829
if expressiontable == 'PRJNA327829_tbl':
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
    options = {'xAxis': {'categories': ['Glenlea_Control_Zero', 'Glenlea_Control_48pi', 'Glenlea_Toxin_48pi', 'Glenlea_Fungus_48pi', 'Salamouni_Control_Zero', 'Salamouni_Control_48pi', 'Salamouni_Toxin_48pi', 'Salamouni_Fungus_48pi']
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
    new_htmlcontent = chart.htmlcontent.replace('''"exporting": {}''','''"exporting":{"buttons": {"ContextButton": {"text": "Export data"}}}''')
    print(new_htmlcontent)

    print('''<br>  
    <br> &nbsp &nbsp &nbsp &nbsp Design: We used Illumina RNAseq to compared the leaf transcriptomes before and after Pyrenophora tritici-repentis inoculation and before and after infiltration of its host selective toxin PtrTox A in two wheat genotypes ‘Glenlea’ susceptible and ‘Salamouni’ resistant.
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Triticum aestivum cultivar:Glenlea and Salamouni Transcriptome or Gene expression. <a href="https://www.ncbi.nlm.nih.gov/bioproject/PRJNA327829"> PRJNA327829</a>''')

# the 33th project PRJNA328385
if expressiontable == 'PRJNA328385_tbl':
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
    options = {'xAxis': {'categories': ['TaWL711_0hpi', 'TaWL711_12hpi', 'TaWL711_24hpi', 'TaWL711_48hpi', 'TaWL711_72hpi', 'TaWL711Lr57_0hpi', 'TaWL711Lr57_12hpi', 'TaWL711Lr57_24hpi', 'TaWL711Lr57_48hpi', 'TaWL711Lr57_72hpi']
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
   &nbsp &nbsp &nbsp &nbsp Design: Leaf rust caused by Puccinia triticina (Pt) is one of the most important diseases of bread wheat globally. Next generation sequencing technologies has made feasible the study of the complete transcriptome of the host as well as pathogen through RNA sequencing (RNAseq) allowing expression analysis of the host genes in response to pathogen attack. Differential expression in a near isogenic line carrying leaf rust resistance gene Lr57 and recipient genotype upon challenge with the Pt isolate 77-5 is being reported in the present study. RNA samples were collected at five different time points 0, 12, 24, 48 and 72 hours post inoculation (HPI) following inoculation with Pt 77-5.
    <br>
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Comparative Temporal Transcriptome Profiling of Wheat near Isogenic Line Carrying Lr57 under Compatible and Incompatible Interactions. <a href="https://www.ncbi.nlm.nih.gov/pubmed/28066494"> Front Plant Sci. 2016; 7: 1943. Published online 2016 Dec 23. doi: 10.3389/fpls.2016.01943 </a>''')

# the 34th project PRJNA341486
if expressiontable == 'PRJNA341486_tbl':
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
    options = {'xAxis': {'categories': ['7279_non-glaucous', '7282_non-glaucous', '7284_non-glaucous', '7285_non-glaucous', '7287_non-glaucous', '7289_glaucous', '7290_glaucous', '7293_glaucous', '7294_glaucous']
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
    new_htmlcontent = chart.htmlcontent.replace('''"exporting": {}''','''"exporting":{"buttons": {"ContextButton": {"text": "Export data"}}}''')
    print(new_htmlcontent)

    print('''<br>  
    <br>
     <p>
    &nbsp &nbsp &nbsp &nbsp 1 Identification of key genes for wax production. <a href="https://www.ncbi.nlm.nih.gov/bioproject/?term=PRJNA341486"> PRJNA341486</a>''')

# the 35th project PRJNA322418
if expressiontable == 'PRJNA322418_tbl':
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
    options = {'xAxis': {'categories': ['doumai_15_20_25', 'doumai X keyi 15DPA', 'doumai X keyi 20DPA', 'doumai X keyi 25DPA', 'keyi_15_20_25', 'keyi X doumai 15DPA', 'keyi X doumai 20DPA', 'keyi X doumai 25DPA']
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
   &nbsp &nbsp &nbsp &nbsp  Transcriptome of hexaploid wheat endosperm, used for gene imprinting analysis.
    <br>
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Genomic Imprinting Was Evolutionarily Conserved during Wheat Polyploidization. <a href="https://doi.org/10.1105/tpc.17.00837"> Published January 2018. DOI: https://doi.org/10.1105/tpc.17.00837 </a>''')

# the 36th project PRJNA348655
if expressiontable == 'PRJNA348655_tbl':
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
    options = {'xAxis': {'categories': ['Aimengniu', 'Aodesa3', 'Baibiansui', 'Baidatou', 'Baihuamai', 'Baimaizi', 'Baimangmai', 'BaipuLuoqing', 'Baiqimai', 'Baiqiumai', 'Baituzitou', 'Banjiemang', 'Bendihuanghuamai', 'Chanbuzhi', 'Changmangshibiantou', 'Dabaimai', 'Dachunbaisilengmai', 'Dahuangpi', 'Daimanghongmai', 'Dakoumai', 'Dalibanmang', 'Dayuhua', 'EarlyPremium', 'Fumai', 'Funo', 'Fuyanghong', 'Hanzhongbai', 'Honggoudou', 'Hongheshangtou', 'Honghuamai', 'Hongjinmai', 'Honglaomai', 'Hongmai', 'Hongmangmai', 'Hongmangzi', 'Hongpidongmai', 'Hongxumai', 'Huangguaxian', 'Huangshuibai', 'Huanxiangguo', 'Huomai', 'Jiahongmai', 'Jiangdongmen', 'Jiangmai', 'Jinan17', 'Laizhou953', 'Lanhuamai', 'Laolaixia', 'Laomai', 'Laoqimai', 'Laotutou', 'Liuzhutou', 'Louguding', 'Lovrin10', 'Mazhamai', 'Motuoxiaomai', 'Niuzhijia', 'Nonglin10', 'Panshiwumang', 'Paozimai', 'Qianjiaomai', 'Sankecun', 'Sanyuehuang', 'Shanxibaimai', 'Shijiazhuang407', 'Shuilizhan', 'Suotiaohongmai', 'Tongjiabaxiaomai', 'Triumph', 'VillaGlori', 'Xianyangdasui', 'Xiaobaimang', 'Xiaofoshou', 'Xiaokouhong', 'Xiaoyan6', 'Xindong2', 'Xishanbiansui', 'Youbaomai', 'Youmangbaifu', 'Youmangsaogudan', 'Youzimai', 'Yuqiumai', 'Zaowutian', 'Zaoxiaomai', 'Zhengyin4', 'Zhugoumai', 'Zhuoludongmai', 'Zhushimai', 'Zijiehong', 'Zipi']
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
            'pointFormat': '<span style="font-weight: bold; color: {series.color}">{series.name}</span>: <b>{point.y:.1f} TPM</b><br> '
        })
    new_htmlcontent = chart.htmlcontent.replace('''"exporting": {}''','''"exporting":{"buttons": {"ContextButton": {"text": "Export data"}}}''')
    print(new_htmlcontent)

    print('''<br>  
    <br> 
    &nbsp &nbsp &nbsp &nbsp Improving grain yield is an aim during crop domestication, and also a major goal of crop breeding. Spike complexity determines the number of seeds per spike, and is a major strategy to improve yield potential. Whereas a large number of inflorescence regulators have been identified in other plant species, we have limited understanding of wheat spike development. In this work, we tried to identified genes or gene regulatory networks, underlying spike architecture, by correlating trait variation with quantitative gene expression variation
     <p>
    &nbsp &nbsp &nbsp &nbsp 1 Transcriptome Association Identifies Regulators of Wheat Spike Architecture. <a href="https://www.ncbi.nlm.nih.gov/pubmed/28807930"> Plant Physiol. 2017 Oct; 175(2): 746–757. Published online 2017 Aug 14. doi: 10.1104/pp.17.00694 </a>''')


# the 37th project PRJNA358808
if expressiontable == 'PRJNA358808_tbl':
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
    options = {'xAxis': {'categories': ['Atay85_Control_Root', 'Atay85_Drought_Root', 'Atay85_Heat_Root', 'Atay85_DroughtHeat_Root', 'Atay85_Control_Leaf', 'Atay85_Drought_Leaf', 'Atay85_Heat_Leaf', 'Atay85_DroughtHeat_Leaf', 'Atay85_Control_Grain', 'Atay85_Drought_Grain', 'Atay85_Heat_Grain', 'Atay85_DroughtHeat_Grain', 'Zubkov_Control_Root', 'Zubkov_Drought_Root', 'Zubkov_Heat_Root', 'Zubkov_DroughtHeat_Root', 'Zubkov_Control_Leaf', 'Zubkov_Drought_Leaf', 'Zubkov_Heat_Leaf', 'Zubkov_DroughtHeat_Leaf', 'Zubkov_Control_Grain', 'Zubkov_Drought_Grain', 'Zubkov_Heat_Grain', 'Zubkov_DroughtHeat_Grain']
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
    new_htmlcontent = chart.htmlcontent.replace('''"exporting": {}''','''"exporting":{"buttons": {"ContextButton": {"text": "Export data"}}}''')
    print(new_htmlcontent)

    print('''<br>  
    <br> 
    &nbsp &nbsp &nbsp &nbsp Two cultivars (resistant and susceptible) stress treatment (drought, heat, and drought + heat) leaf, root and grain tissues.
     <p>
    &nbsp &nbsp &nbsp &nbsp 1 Bread wheat transcriptome analysis for drought and heat stress treatments. <a href="https://www.ncbi.nlm.nih.gov/bioproject/?term=PRJNA358808"> PRJNA358808 </a>''')


# the 38th project PRJNA353130
if expressiontable == 'PRJNA353130_tbl':
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
    options = {'xAxis': {'categories': ['WT_1HAI', 'WT_6HAI', 'WT_12HAI', 'OE_1HAI', 'OE_6HAI', 'OE12_HAI']
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
   &nbsp &nbsp &nbsp &nbsp Seed germination is not only a critical developmental step in the wheat life cycle, but is also important for agricultural production including yield and quality. However, in wheat, the knowledge of the mechanism of regulating seed germination is still limited. In this study, we found 22nt microRNA (miR) miR021b, specifically expressed in scutellum of developing and germinating wheat seed, generated phased ta-siRNAs by cleaving a long non coding RNA LNCR. Overexpression of miR021b in wheat showed a retarded germination and improved resistance to pre-harvest sprouting (PHS), while its silencing enhanced germination rate through transiently expressing in immature embryos. To figure out the mechanism of miR021b regulating seed germination, we found miR021b affected the expression of genes involved in bioactive gibberellin (GA) synthesis and its overexpression reduced the bioactive GA content and inhibited amylase genes expression. In addition, it was observed that TaVp1, TaABF and TaABI3, responded the abscisic acid (ABA) signaling, can bind the promoter of miR021b precursor and regulated its expression, suggesting that miR021b might function in GA-ABA balance during germination. This study identified a signaling pathway that miR021b controlled GA-dependent seed germination in wheat through generating phased ta-siRNAs by cleaved a long non coding RNA LNCR.
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Wheat miR9678 Affects Seed Germination by Generating Phased siRNAs and Modulating Abscisic Acid/Gibberellin Signaling.Guanghui Guo, Xinye Liu, Fenglong Sun, Jie Cao, Na Huo, Bala Wuda, Mingming Xin, Zhaorong Hu, Jinkun Du, Rui Xia, Vincenzo Rossi, Huiru Peng, Zhongfu Ni, Qixin Sun, Yingyin Yao. <a href="https://www.ncbi.nlm.nih.gov/pmc/articles/pmid/29567662/"> Plant Cell. 2018 Apr; 30(4): 796–814. Published online 2018 Mar 22. doi: 10.1105/tpc.17.00842 </a>''')
# the 39th project PRJNA396738
if expressiontable == 'PRJNA396738_tbl':
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
    options = {'xAxis': {'categories': ['5A-_NIL_4dpa', '5A+_NIL_4dpa', '5A-_NIL_8dpa', '5A+NIL_8dpa']
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
   &nbsp &nbsp &nbsp &nbsp In this study we performed RNA-sequencing on two NILs segregating for a major grain weight quantitative trait loci located on wheat chromosome arm 5AL. The QTL was identified in a doubled haploid population between the UK cultivars Charger and Badger. Badger offers the positive allele and Charger was used as the recurrent parent in NIL generation. 5A+ NILs have increased grain weight, grain length and pericarp cell size.
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Ubiquitin-related genes are differentially expressed in isogenic lines contrasting for pericarp cell size and grain weight in hexaploid wheat. Jemima Brinton, James Simmonds, Cristobal Uauy. <a href="https://www.ncbi.nlm.nih.gov/pubmed/29370763"> BMC Plant Biol. 2018; 18: 22. Published online 2018 Jan 25. doi: 10.1186/s12870-018-1241-5 </a>''')

# the 40th project PRJNA427246
if expressiontable == 'PRJNA427246_tbl':
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
    options = {'xAxis': {'categories': ['grain_heat_at_0m', 'grain_heat_at_5m', 'grain_heat_at_10m', 'grain_heat_at_30m', 'grain_heat_at_1h', 'grain_heat_at_4h', 'Leaf_heat_at_0m', 'Leaf_heat_at_5m', 'Leaf_heat_at_10m', 'Leaf_heat_at_30m', 'Leaf_heat_at_1h', 'Leaf_heat_at_4h']
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
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Unveiling multidimensional regulations of heat stress-responsive transcriptomes in wheat (Triticum aestivum L.). <a href="https://www.ncbi.nlm.nih.gov/bioproject/PRJNA427246"> PRJNA427246 </a>''')

# the 40th project PRJNA471426
if expressiontable == 'PRJNA471426_tbl':
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
    options = {'xAxis': {'categories': ['WT9DPA', 'M9DPA', 'WT15DPA', 'M15DPA', 'WT20DPA', 'M20DPA', 'WT25DPA', 'M25DPA']
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
    &nbsp &nbsp &nbsp &nbsp SM482gs was a mutant wheat line by using EMS, which identified from the common wheat cultivar Shumai 482 and exhibited increased grain size and 1000-grain weight as compared to wild-type (shumai 482) plants. The RNA-seq data of the developmental grain of SM482gs and shumai482 provides insights into the metabolic mechanism of SM482gs.
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 A mutant wheat line exhibited increased grain size and 1000-grain weight. <a href="https://www.ncbi.nlm.nih.gov/bioproject/PRJNA471426"> PRJNA471426 </a>''')

# the 41th project PRJNA477934
if expressiontable == 'PRJNA477934_tbl':
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
    options = {'xAxis': {'categories': ['CB037_endosperm_15dpa', 'TAA10_endosperm_15dpa', 'XX329_endosperm_15dpa', 'CB037_TAA10_endosperm_15dpa', 'TAA10_CB037_endosperm_15dpa', 'CB037_XX329_endosperm_15dpa', 'XX329_CB037_endosperm_15dpa']
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
    &nbsp &nbsp &nbsp &nbsp Genomic imbalance affects seed development and mass accumulation in wheat interspecific crosses with different ploidies.
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 RNA seq data from tetraploid wheat, hexaploid wheat and reciprocally crossed endosperm. <a href="https://www.ncbi.nlm.nih.gov/bioproject/PRJNA477934"> PRJNA477934 </a>''')


# the 42th project PRJNA485741
if expressiontable == 'PRJNA485741_tbl':
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
    options = {'xAxis': {'categories': ['embryo14dpa', 'endosperm14dpa', 'embryo25dpa', 'endosperm25dpa']
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
    &nbsp &nbsp &nbsp &nbsp To analyse the regulation of transcripts in grain embryo and endosperm during development, we performed RNA-Seq for wheat from 14 and 25 day post anthesis (DPA). And long-read sequencing for mixed whole grains from 14 and 25 DPA was employed to obtain full-length transcripts. A series of differentially expressed genes and tissues-specific genes of embryo and endosperm were identified. Moreover, 4351, 4641, 4516 and 4453 genes with A, B and D homoeoloci were detected in the four tissues. These provide specific gene pools of embryo and endosperm and homoeolog expression bias model in a large scale, which provides new insights into the molecular physiology of wheat. Overall design: Wheat (Triticum aestivum L.) cultivar Zhou 8425B were field cultivated. Embryo and endosperm (including episperm and pericarp) at 14 and 25 day post anthesis (DPA) were collected respectively for three biological replicates and immediately frozen in liquid nitrogen. They were then stored at -80°C following RNA extraction. Totals RNAs were extracted from each tissue sample using Plant Total RNA Purification Kit (GMbiolab co., Ltd. Taichung, Taiwan) according to the manufacturer’s protocol. Finally, the twelve RNA librarie sequencing based on Illumina HiSeq 4000 platform by paired-end experiments.
    <p>
    &nbsp &nbsp &nbsp &nbsp 1Insights into transcriptional characteristics and homoeolog expression bias of embryo and endosperm in developing grain through mRNA-Seq and Iso-Seq (bread wheat). <a href="https://www.ncbi.nlm.nih.gov/bioproject/?term=PRJNA485741"> PRJNA485741 </a>''')

# the 43th project PRJNA362497
if expressiontable == 'PRJNA362497_tbl':
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
    options = {'xAxis': {'categories': ['wild type', 'mutant']
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
    &nbsp &nbsp &nbsp &nbsp Leaf at tillering stage.
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 The purpose of this project is to find out the expression difference on transcription level between wild type (Jimai5265) and Jimai5265yg which is a chlorophyll-deficient mutant. <a href="https://www.ncbi.nlm.nih.gov/bioproject/PRJNA362497"> PRJNA362497 </a>''')

# the 44th project DMSO_GA_JA_tbl
if expressiontable == 'DMSO_GA_JA_tpm_mean_tbl':
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
    options = {'xAxis': {'categories': ['DMSO1h', 'GA1h', 'JA1h']
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
    &nbsp &nbsp &nbsp &nbsp This dataset was provided by Jin-Ying Gou from Fudan University.
    <p>
    &nbsp &nbsp &nbsp &nbsp , please cite:<br> 
    Chen, Y., Yan, Y., Wu, TT. et al. Cloning of wheat keto-acyl thiolase 2B reveals a role of jasmonic acid in grain weight determination. Nat Commun 11, 6266 (2020).<a href="https://doi.org/10.1038/s41467-020-20133-z"> https://doi.org/10.1038/s41467-020-20133-z.</a>
    ''')
#the 45th project DMSO_ABA_JA_6BA 3h
if expressiontable == 'ABA_JA_6BA_DMSO3h_mean_tbl':
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
    options = {'xAxis': {'categories': ['DMSO3h', '6BA3h', 'ABA3h', 'SA3h']
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
    &nbsp &nbsp &nbsp &nbsp This dataset was provided by Jin-Ying Gou from Fudan University.
    <p>
    &nbsp &nbsp &nbsp &nbsp , please cite:<br> 
    Chen, Y., Yan, Y., Wu, TT. et al. Cloning of wheat keto-acyl thiolase 2B reveals a role of jasmonic acid in grain weight determination. Nat Commun 11, 6266 (2020).<a href="https://doi.org/10.1038/s41467-020-20133-z"> https://doi.org/10.1038/s41467-020-20133-z.</a>''')

# the 46th project PRJNA293629
if expressiontable == 'PRJNA293629_tbl':
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
    options = {'xAxis': {'categories': ['CS_CK_6h', 'CS_Na_6h', 'QM_CK_6h', 'QM_Na_6h', 'CS_CK_12h', 'CS_Na_12h', 'QM_CK_12h', 'QM_Na_12h', 'CS_CK_24h', 'CS_Na_24h', 'QM_CK_24h', 'QM_Na_24h', 'CS_CK_6h', 'CS_Na_48h', 'QM_CK_48h', 'QM_Na_48h']
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
            'pointFormat': '<span style="font-weight: bold; color: {series.color}">{series.name}</span>: <b>{point.y:.1f} TPM</b> <br/> '
        })
    new_htmlcontent = chart.htmlcontent.replace('''"exporting": {}''','''"exporting":{"buttons": {"ContextButton": {"text": "Export data"}}}''')
    print(new_htmlcontent)

    print('''<br>  
    <br> 
    &nbsp &nbsp &nbsp &nbsp 
transcriptome response of two wheat cultivers to salt stress
     <p>
    &nbsp &nbsp &nbsp &nbsp 1 Yumei Zhang, Zhenshan Liu, Abul Awlad Khan, Qi Lin, Yao Han, Ping Mu, Yiguo Liu, Hongsheng Zhang, Lingyan Li, Xianghao Meng, Zhongfu Ni, Mingming Xin. Expression partitioning of homeologs and tandem duplications contribute to salt tolerance in wheat (Triticum aestivum L.). <a href="https://www.ncbi.nlm.nih.gov/pubmed/26892368"> PMID: 26892368 </a>''')


#the 47th project PRJNA487923
if expressiontable == 'PRJNA487923_tbl':
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
    options = {'xAxis': {'categories': ['Root CK', 'Root Salt']
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
    &nbsp &nbsp &nbsp &nbsp The root transcriptome profiling of the salt-stress response in bread wheat.
    <p>
    &nbsp &nbsp &nbsp &nbsp Amirbakhtiar N, Ismaili A, Ghaffari MR, Nazarian Firouzabadi F, Shobbar ZS. Transcriptome response of roots to salt stress in a salinity-tolerant bread wheat cultivar. PLoS One. 2019 Mar 15;14(3):e0213305.<a href="https://www.ncbi.nlm.nih.gov/pubmed/30875373">PMID: 30875373</a>
    ''')

#the 48th project PRJNA171754
if expressiontable == 'PRJNA171754_tbl':
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
    options = {'xAxis': {'categories': ['HD2985_control', 'HD2985_stress', 'HD2329_control', 'HD2329_stress']
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
    new_htmlcontent = chart.htmlcontent.replace('''"exporting": {}''','''"exporting":{"buttons": {"ContextButton": {"text": "Export data"}}}''')
    print(new_htmlcontent)

    print('''<br>  
    <br> 
    &nbsp &nbsp &nbsp &nbsp The study was conducted in order to find out the differential change in the transcript of tolerant and susceptible wheat cultivar under heat stress and to decipher the mechanism of thermotolerance in wheat by identifying novel genes and transcription factors involved in the pathways. Wheat cultivar HD2985 (thermotolerant) and HD2329 (thermosusceptible) were exposed to heat stress of 42 degree for 4h at pollination stage and samples were collected from both control and heat shock treated plants for further characterization.
    <p>
    &nbsp &nbsp &nbsp &nbsp Ranjeet R. Kumar, Suneha Goswami, Sushil K. Sharma, Yugal K. Kala, Gyanendra K. Rai, Dwijesh C. Mishra, Monendra Grover, Gyanendra P. Singh, Himanshu Pathak, Anil Rai, Viswanathan Chinnusamy, Raj D. Rai
OMICS. 2015 Oct 1; 19(10): 632-647. doi: 10.1089/omi.2015.0097. Harnessing Next Generation Sequencing in Climate Change: RNA-Seq Analysis of Heat Stress-Responsive Genes in Wheat (Triticum aestivum L.) <a href="https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4615779/">PRJNA171754</a>
    ''')

#the 49th project PRJNA307228
if expressiontable == 'PRJNA307228_tbl':
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
    options = {'xAxis': {'categories': ['SKM0', 'AKM0', 'AKM24', 'AKM48', 'AKM120', 'AKI24', 'AKI48', 'AkI120']
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
    new_htmlcontent = chart.htmlcontent.replace('''"exporting": {}''','''"exporting":{"buttons": {"ContextButton": {"text": "Export data"}}}''')
    print(new_htmlcontent)

    print('''<br>  
    <br> 
    &nbsp &nbsp &nbsp &nbsp Wheat cultivar Xingzi 9104 is an elite wheat germplasm that possesses adult plant resistance to stripe rust. This work will help further our understanding of the detailed mechanisms underlying APR to stripe rust.
    <p>
    &nbsp &nbsp &nbsp &nbsp <a href="   http://www.ncbi.nlm.nih.gov/bioproject/PRJNA307228">PRJNA307228</a>
    ''')
#the 50th project Wangmeng_NR
if expressiontable == 'Wangmeng_NR_tbl':
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
    options = {'xAxis': {'categories': ['CS_CT', 'CS_NS1h', 'NR1h', 'NR24h']
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
    &nbsp &nbsp &nbsp &nbsp NS nitrate starvation；NR nitrate recovery.
    <p>
    &nbsp &nbsp &nbsp &nbsp Wang, M., Zhang, P., Liu, Q., Li, G., Di, D., Xia, G., ... & Shi, W. (2020). TaANR1-TaBG1 and TaWabi5-TaNRT2s/NARs link ABA metabolism and nitrate acquisition in wheat roots. Plant Physiology, 182(3), 1440-1453.
    ''')
# the 51th project PRJNA1037698
if expressiontable == 'PRJNA1037698_tbl':
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
    options = {'xAxis': {'categories': ['DR3_24', 'DR3_72h', 'DR3_CK', 'DR7_24h', 'DR3_72h', 'DR7_CK']
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
            'pointFormat': '<span style="font-weight: bold; color: {series.color}">{series.name}</span>: <b>{point.y:.1f} TPM</b><br/>'
        })
    new_htmlcontent = chart.htmlcontent.replace('''"exporting": {}''','''"exporting":{"buttons": {"ContextButton": {"text": "Export data"}}}''')
    print(new_htmlcontent)

    print('''<br>  
    <br> &nbsp &nbsp &nbsp &nbsp The objectives of this study were to identify crucial genes and pathways associated with the response and regulation of wild emmer wheat to Pst infection, as well as to elucidate the underlying molecular mechanisms involved in the response to strip rust.
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Triticum aestivum Transcriptome or Gene expression. <a href="https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1037698"> PRJNA1037698</a>''')

# the 52th project PRJNA613349
if expressiontable == 'PRJNA613349_tbl':
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
    options = {'xAxis': {'categories': ['PBW343C12', 'PBW343C48', 'FLW29C12', 'FLW29C48', 'FLW29C72', 'FLW29T12', 'FLW29T48', 'FLW29T72', 'PBW343C72', 'PBW343T12', 'PBW343T48', 'PBW343T72']
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
            'pointFormat': '<span style="font-weight: bold; color: {series.color}">{series.name}</span>: <b>{point.y:.1f} TPM</b><br/>'
        })
    new_htmlcontent = chart.htmlcontent.replace('''"exporting": {}''','''"exporting":{"buttons": {"ContextButton": {"text": "Export data"}}}''')
    print(new_htmlcontent)

    print('''<br>  
    <br> &nbsp &nbsp &nbsp &nbsp A near isogenic line FLW29 containing yellow rust resistance gene Yr16 introgressed from wild wheat species (Cappelle-Desprez) was crossed with wheat cultivar PBW343. The recipient parent FLW29 (resistant), and cv. PBW343 (susceptible) were used for studying the differential gene expression in response to Puccinia striiformis f. sp. tritici (Pst). Two wheat genotypes were inoculated with Pst pathotype 46S119 such that for each cultivar a total of 10 pots (5 mock-inoculated and 5 inoculated) with three biological replicates were used for the experiment. Fresh uredinospores of 46S119 were harvested from infected wheat plant and resuspended in sterile distilled water evenly mixed with soltrol (20mg/100ml) that was used to inoculate seedlings growth. Seedlings at two-leaf stage/flag leaves (approx 20 days after sowing), were inoculated with the spore suspension using an automizer and then kept in dark at 10 degree C for 16-h light/8-hdark to maintain the relative high humidity. Later, leaf samples were collected at 3 different time periods i,e. at 12, 48 and 72 hr post-inoculation (HPI). The collected samples were immediately placed in RNA later and stored at -20 degree C until use. The RNA from leaf samples were extracted using Qiagen RNeasy Mini kit (QiagenInc, USA). Samples were IIumina sequenced on a single HiSeq 4000 machines yielding at least 895M 150bp paired-end reads per sample. Each sample represents one experimental condition (pathogen/mock; time points; genotype).
    <p>
    &nbsp &nbsp &nbsp &nbsp 1 Triticum aestivum Transcriptome or Gene expression. <a href="https://www.ncbi.nlm.nih.gov/bioproject/PRJNA613349"> PRJNA613349</a>''')
# the 53th project PRJEB51827
if expressiontable == 'PRJEB51827_tbl':
    data = {}
    
    # 1. 先获取样本列名（在关闭连接前）
    try:
        cursor.execute("""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = 'gene_expression' 
            AND TABLE_NAME = 'PRJEB51827_tbl' 
            AND COLUMN_NAME NOT IN ('IWGSCV1_1_id', 'GeneID') 
            ORDER BY ORDINAL_POSITION
        """)
        sample_columns = [col[0] for col in cursor.fetchall()]
        
        print("<p>找到 " + str(len(sample_columns)) + " 个样本列</p>")
        
        # 2. 查询基因数据
        for gene in name:
            select_sql = "SELECT * FROM PRJEB51827_tbl WHERE GeneID = %s"
            
            try:
                cursor.execute(select_sql, (gene,))
                row = cursor.fetchall()
                
                if row:
                    row2 = row[0][1:]  # 跳过自增ID
                    # 获取所有样本值（跳过GeneID）
                    sample_values = list(row2[1:])
                    
                    # 确保数据长度与列数匹配
                    if len(sample_values) != len(sample_columns):
                        print("<p>警告: 基因 " + gene + " 的数据长度不匹配</p>")
                        print("<p>数据长度: " + str(len(sample_values)) + ", 列数: " + str(len(sample_columns)) + "</p>")
                        # 调整数据长度
                        if len(sample_values) > len(sample_columns):
                            sample_values = sample_values[:len(sample_columns)]
                        else:
                            sample_values = sample_values + [0] * (len(sample_columns) - len(sample_values))
                    
                    new = [sample_values]
                    data[row2[0]] = new
                    print("<p>成功获取基因 " + gene + " 的数据</p>")
                else:
                    print("<p>未找到基因: " + gene + "</p>")
                    # 显示一些存在的基因
                    cursor.execute("SELECT GeneID FROM PRJEB51827_tbl LIMIT 5")
                    samples = cursor.fetchall()
                    if samples:
                        print("<p>示例基因: " + ", ".join([str(s[0]) for s in samples]) + "</p>")
                        
            except Exception as e:
                print("<p>查询基因错误: " + str(e) + "</p>")
        
    except Exception as e:
        print("<p>获取列名错误: " + str(e) + "</p>")
        sample_columns = []
    
    # 3. 现在才关闭数据库连接
    cursor.close()
    mydb.close()
    
    # 4. 如果有数据，绘制图表
    if data and sample_columns:
        chart = Highchart(width=850, height=600)
        options = {
            'xAxis': {
                'categories': sample_columns,
                'labels': {
                    'rotation': -45,
                    'style': {
                        'fontSize': '8px'
                    }
                }
            },
            'chart': {
                'zoomType': 'xy',
                'height': 800
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
                'pointFormat': '<span style="font-weight: bold; color: {series.color}">{series.name}</span>: <b>{point.y:.1f} TPM</b><br/>'
            })
        
        chart.save_file('/tmp/test')
        new_htmlcontent = chart.htmlcontent.replace('''"exporting": {}''','''"exporting":{"buttons": {"ContextButton": {"text": "Export data"}}}''')
        print(new_htmlcontent)
    elif not data:
        print("<h3>错误：没有找到任何基因数据</h3>")
        print("<p>请检查基因ID是否正确，或者数据库中是否有数据</p>")
    elif not sample_columns:
        print("<h3>错误：无法获取样本列信息</h3>")
    
    print('''<p>
    &nbsp &nbsp &nbsp &nbsp 1 De novo annotation reveals transcriptomic complexity across the hexaploid wheat pan-genome <a href="https://doi.org/10.1038/s41467-025-64046-1">Nat Commun 2025, doi: 10.1038/s41467-025-64046-1</a>''')
print('</div>')
print('<div id="footer"></div>')

print('</body>')
print('</html>')


