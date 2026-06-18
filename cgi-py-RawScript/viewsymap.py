#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
__author__ = 'shengwei ma'
__author_email__ = 'shengweima@icloud.com'

import sys
reload(sys)

sys.setdefaultencoding('utf-8')

print("Content-Type: text/html")
print("")
print('<html>')
print('<head>')
print('<title>Synteny Viewer</title>')
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
    cgitb.enable()
except:
    pass
import cgi
import subprocess

import random

resultdir = '/var/www/html/symap/result/'

random_num = ''.join([str(random.randint(0,9)),str(random.randint(0,9)),str(random.randint(0,9))])


form = cgi.FieldStorage()

bed = '/var/www/html/symap/CS_CS_durum_emmer_urartu_tauschii.bed'
style = form["style"].value
dpi = form["dpi"].value
format1 = form["format"].value
font = form["font"].value
diverge = form["diverge"].value
scalebar = form["scalebar"].value
shadestyle = form["shadestyle"].value
figsize = form["figsize"].value.strip()
block = form["block"].value.strip().split('\r') 
layout = form["layout"].value.strip().split('\r')

if 'True' in scalebar:
    para = ' --scalebar ' + ' --dpi=' + dpi + ' --format=' + format1 + ' --font=' + font + ' --diverge=' + diverge + ' --shadestyle=' + shadestyle + ' --style=' + style + ' --figsize=' + str(figsize)
else:
    para = ' --dpi=' + dpi + ' --format=' + format1 + ' --font=' + font + ' --diverge=' + diverge + ' --style=' + style + ' --shadestyle=' + shadestyle + ' --figsize=' + str(figsize)

output = 'block_' + random_num + '.' + format1
blockfile = resultdir + 'block_' + random_num + '.txt'
layoutfile = resultdir + 'block_' + random_num + '.layout'

with open(blockfile, 'w') as f:
    for line in block:
        f.write(line)

with open(layoutfile, 'w') as f:
    for line in layout:
        f.write(line)

cmd = 'python -m jcvi.graphics.synteny ' + ' '.join([blockfile,bed,layoutfile]) + para


proc = subprocess.Popen(cmd,shell=True, close_fds=True, stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=resultdir)
# proc = subprocess.Popen(['ls', '-lh'], cwd=tmpdir, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
for line in iter(proc.stdout.readline, ''):
    print(line + '<br>')
for line in iter(proc.stderr.readline, ''):
    if '.txt' in line:
        inputfile = str(line.split('`')[1].split('/')[-1])
        print('<a href="/symap/result/' + inputfile + '"> Input block file: ' + inputfile + '</a><br><br>')
    if '.layout' in line:
        layoutfile = str(line.split('`')[1].split('/')[-1])
        print('<a href="/symap/result/' + layoutfile + '"> Input layout file: ' + layoutfile + '</a><br><br>')
    if 'Figure saved to' in line:
        print('<a href="/symap/result/' + str(output) + '">Download Result:' + str(output) + '</a><br><br>')
        print('<br><br>Success !!!!!<br><br>')
proc.wait()


print('</div>')
print('<div id="footer"></div>')

print('</body>')
print('</html>')
