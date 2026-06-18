#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
__author__ = 'shengwei ma'
__author_email__ = 'shengweima@icloud.com'

# this file like apache cgi file

from datetime import datetime, date
import MySQLdb
import cgi

from datetime import datetime, date
import MySQLdb
import cgi

print("Content-Type: text/html")
print("")
print('<html>')
  
print('<head>')
print('<title>Gene Submit</title>')
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

try:
    import cgitb
    cgitb.enable(display=0, logdir='/var/www/html/genes/log/')
except:
    pass

form = cgi.FieldStorage()

gene_id = form["geneid"].value.strip().replace('"', '').encode("ascii", "ignore").decode()
gene_name = form["genename"].value.strip().replace('"', '').encode("ascii", "ignore").decode()
chrom_pos = form["chrompos"].value.strip().replace('"', '').encode("ascii", "ignore").decode()
gene_phenotype = form["phenotype"].value.strip().replace('"', '').encode("ascii", "ignore").decode()
gene_species = form["genespecies"].value.strip().replace('"', '').encode("ascii", "ignore").decode()
paper_title = form["papertilte"].value.strip().replace('"', '').encode("ascii", "ignore").decode()
paper_doi = form["paperdoi"].value.strip().replace('"', '').encode("ascii", "ignore").decode()
key_result = form["keyresult"].value.strip().replace('"', '').encode("ascii", "ignore").decode()
author = form["author"].value.strip().replace('"', '').encode("ascii", "ignore").decode()
author_mail = form["authormail"].value.strip().replace('"', '').encode("ascii", "ignore").decode()
sub_paswd = form["paswd"].value.strip().replace('"', '').encode("ascii", "ignore").decode()
submission_date = date.today()

if sub_paswd == 'wheatomics':
    select_sql = "select * from cloned_gene_tbl where" + " gene_id='" + gene_id + "';"
    sql = "INSERT INTO cloned_gene_tbl(gene_id, gene_name, chrom_pos, gene_phenotype, gene_species, paper_title, paper_doi,key_result,author,author_mail,submission_date) VALUES ('%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s')" % (gene_id, gene_name, chrom_pos, gene_phenotype, gene_species, paper_title, paper_doi, key_result, author, author_mail, submission_date)
    try:
        mydb = MySQLdb.connect(host='localhost',
                               user='wheatomics_user',
                               passwd='wheatomics115599',
                               db='cloned_gene_db',
                               charset='utf8')
        cursor = mydb.cursor()
        cursor.execute(select_sql)
        row = cursor.fetchall()
        if gene_id in str(row):
            print("The gene was already in the database.")
        else:
            cursor.execute(sql)
            mydb.commit()
            print("submit successfully <a href='/genes/index.html'>return Search page</a>")
    except Exception as e:
        mydb.rollback()
        print(str(e))
    else:
        with open('/var/www/html/genes/gene_table.txt','a') as f:
            f.write('\t'.join([gene_id, gene_name, chrom_pos, gene_phenotype, gene_species, paper_title, paper_doi, key_result, author, author_mail, str(submission_date) + '\n']))


    cursor.close()
    mydb.close()
else:
    print('the submission password is wrong, please contact us :&nbsp;<a href="mailto:shengweima@icloud.com" class="">WheatOmics</a>')

print('</div>')
print('<div id="footer"></div>')

print('</body>')
print('</html>')
