#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
__author__ = 'shengwei ma'
__author_email__ = 'shengweima@icloud.com'

import sys
reload(sys)

sys.setdefaultencoding('utf-8')

print("Content-Type: text/html")
print ("")
print ("<html>")

try:
    import cgitb
    cgitb.enable()
except:
    pass
import cgi
import subprocess

import random

resultdir = '/var/www/html/symap/result/'

random_num = ''.join([str(random.randint(0,9)),str(random.randint(0,9)),str(random.randint(0,9))])


form = cgi.FieldStorage()


style = form["style"].value
dpi = form["dpi"].value
format1 = form["format"].value
font = form["font"].value
diverge = form["diverge"].value
scalebar = form["scalebar"].value
shadestyle = form["shadestyle"].value
figsize = form["figsize"].value.strip()
block = form["block"].value.strip().split('\r')
bed = form["bed"].value.strip().split('\r')
layout = form["layout"].value.strip().split('\r')

if 'True' in scalebar:
    para = ' --scalebar ' + ' --dpi=' + dpi + ' --format=' + format1 + ' --font=' + font + ' --diverge=' + diverge + ' --shadestyle=' + shadestyle + ' --style=' + style + ' --figsize=' + str(figsize)
else:
    para = ' --dpi=' + dpi + ' --format=' + format1 + ' --font=' + font + ' --diverge=' + diverge + ' --style=' + style + ' --shadestyle=' + shadestyle + ' --figsize=' + str(figsize)

output = 'block_' + random_num + '.' + format1
blockfile = resultdir + 'block_' + random_num + '.txt'
bedfile = resultdir + 'block_' + random_num + '.bed'
layoutfile = resultdir + 'block_' + random_num + '.layout'

with open(blockfile, 'w') as f:
    for line in block:
        f.write(line)

with open(bedfile, 'w') as f:
    for line in bed:
        f.write(line)

with open(layoutfile, 'w') as f:
    for line in layout:
        f.write(line)

cmd = 'python -m jcvi.graphics.synteny ' + ' '.join([blockfile,bedfile,layoutfile]) + para


proc = subprocess.Popen(cmd,shell=True, close_fds=True, stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=resultdir)
# proc = subprocess.Popen(['ls', '-lh'], cwd=tmpdir, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
for line in iter(proc.stdout.readline, ''):
    print(line + '<br>')
for line in iter(proc.stderr.readline, ''):
    if '.txt' in line:
        inputfile = str(line.split('`')[1].split('/')[-1])
        print('<a href="/symap/result/' + inputfile + '"> Input block file: ' + inputfile + '</a><br><br>')
    if '.bed' in line:
        bedfile = str(line.split('`')[1].split('/')[-1])
        print('<a href="/symap/result/' + bedfile + '"> Input block file: ' + bedfile + '</a><br><br>')
    if '.layout' in line:
        layoutfile = str(line.split('`')[1].split('/')[-1])
        print('<a href="/symap/result/' + layoutfile + '"> Input layout file: ' + layoutfile + '</a><br><br>')
    if 'Figure saved to' in line:
        print('<a href="/symap/result/' + str(output) + '">Download Result:' + str(output) + '</a><br><br>')
        print('<br><br>Success !!!!!<br><br>')
proc.wait()







