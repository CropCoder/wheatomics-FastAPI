#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

print "Content-Type: text/html"
print ""
print "<html>"

try:
    import cgitb; cgitb.enable()
except:
    pass
import cgi
import gzip
from Bio import SeqIO

form = cgi.FieldStorage()

DbPath = '/data/fasta/'
DATALIB = form["database"].value
name = form["ID"].value.strip().split() 


if "genome" in DATALIB:
    fasta = DbPath + DATALIB
    for seq in name:
        if ':' in seq and '-' in seq:
            start = seq.split(":")[1].split("-")[0]
            end = seq.split(":")[1].split("-")[1]
            if 0<int(end)- int(start) <= 5000000:     
                record_dict = SeqIO.index(fasta, "fasta")
                print '<pre>'
                print record_dict[seq.split(":")[0]].seq[int(start):int(end)]
                print '</pre>'
            else:
                print '<pre>'
                print "If you want get a sequence from chromosome region(<=5000000bp), your input format must be like chr1A:10-100."
                print "<br>"
                print "But if you just want to get a gene or marker sequence, your input only needs a name or ID."
                print '</pre>'
        else:
            print '<pre>'
            print "If you want get a sequence from chromosome region(<=5000000bp), your input format must be like chr1A:10-100."
            print "<br>"
            print "But if you just want to get a gene or marker sequence, your input only needs a name or ID."
            print '</pre>'
    record_dict.close()
else:
    fasta = DbPath + DATALIB 
    for seq in name:
        record_dict = SeqIO.index(fasta, "fasta")
        print '<pre>'
        print record_dict[seq.strip()].format("fasta")
        print '</pre>'


