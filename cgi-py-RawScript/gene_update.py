#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
__author__ = 'shengwei ma'
__author_email__ = 'shengweima@icloud.com'

# this file like apache cgi file

from datetime import datetime, date
import MySQLdb
import cgi

print("Content-Type: text/html")
print("")
print("<html>")

try:
    import cgitb
    cgitb.enable(display=0, logdir='/var/www/html/genes/log/')
except:
    pass

form = cgi.FieldStorage()
clone_id = form["cloneid"].value.strip().replace('"', '').encode("ascii", "ignore").decode()
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
    select_sql = "select * from cloned_gene_tbl where" + " clone_id='" + clone_id + "';"
    try:
        mydb = MySQLdb.connect(host='localhost',
                               user='wheatomics_user',
                               passwd='wheatomics115599',
                               db='cloned_gene_db',
                               charset='utf8')
        cursor = mydb.cursor()
        cursor.execute(select_sql)
        row = cursor.fetchall()
        if clone_id in str(row):
            sql = "UPDATE cloned_gene_tbl SET gene_id=%s, gene_name=%s, chrom_pos=%s, gene_phenotype=%s, gene_species=%s, paper_title=%s, paper_doi=%s,key_result=%s,author=%s,author_mail=%s,submission_date=%s WHERE clone_id=%s"
            val = (str(gene_id), str(gene_name), str(chrom_pos), str(gene_phenotype), str(gene_species), str(paper_title), str(paper_doi), str(key_result), str(author), str(author_mail), str(submission_date),str(clone_id))  
            cursor.execute(sql,val)
            mydb.commit()
            print('The gene ' + gene_id + ' has been updated.')
        else:
            print("The gene" +  gene_id + " is not in the database ,welcome to submit it to database <a href='/genes/index.html'> Go submit page</a>")
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

