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
print('<title>Get Sequence</title>')
print('<link rel="shortcut icon" href="/favicon.ico" type="image/x-icon" />')
print('<link rel="stylesheet" href="/css/style.css" type="text/css" />')
print('<script src="/js/jquery/1.9.1/jquery.min.js" type=text/javascript></script>')
print('<link rel="stylesheet" href="/css/bootstrap-4.5.3-dist/css/bootstrap.css" type="text/css" />')
print('<script src="/css/bootstrap-4.5.3-dist/js/bootstrap.js" type=text/javascript></script>')
print('<script src="/js/FileSaver.js/FileSaver.min.js" type=text/javascript></script>')
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

try:
    import cgitb
    cgitb.enable()
except:
    pass
import cgi
import subprocess

import random

tmpdir = '/var/www/html/snprimer/tmp/'
resultdir = '/var/www/html/snprimer/result/'

random_num = ''.join([str(random.randint(0,9)),str(random.randint(0,9)),str(random.randint(0,9))])

genomedir = '/var/www/html/getfasta/blastdb/'

form = cgi.FieldStorage()

genome = genomedir + form["querydb"].value  # 获取wheatPPI mysql
genomenumber = form["ploidy"].value
price = form["price"].value
caps = form["caps"].value
kasp = form["kasp"].value
blast = '1'
max_Tm = form["tm"].value
max_size = form["size"].value.strip().split()[0]
pick = form["pick"].value
name = form["ID"].value.strip().split()  # 获取输入的基因

with open(tmpdir + 'for_polymarker.csv', 'w') as f:
    for lin in name:
        if len(lin.split(',')) == 3 and lin.count('[') == 1  and lin.count(']')  == 1 and lin.count('/') == 1 and lin.split(',')[2].upper().count('A') + lin.split(',')[2].upper().count('T') + lin.split(',')[2].upper().count('C') + lin.split(',')[2].upper().count('G') + lin.split(',')[2].upper().count('N') == len(lin.split(',')[2].upper()) - 3:
            f.write(lin + '\n')
            print(lin.split(',')[0] + ' has been submitted.<br>')
        else:
            print(lin.split(',')[0] + ' format may be wrong!!!' + ' Please check and correct it, and then submit it in alone in next time.<br>')
cmd = '/var/www/html/snprimer/SNP_Primer_Pipeline/run_getkasp.py ' + 'for_polymarker.csv ' + ' '.join([genomenumber, price, caps, kasp, blast, max_Tm, max_size, pick, genome])

proc = subprocess.Popen(cmd,shell=True, close_fds=True, stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=tmpdir)
# proc = subprocess.Popen(['ls', '-lh'], cwd=tmpdir, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#for line in iter(proc.stdout.readline, ''):
#    if 'successfully' in line or 'select_primer' in line:
#        print(line)
        
proc.wait()

if caps == '1':
    capsdir = 'My_CAPS_' + random_num
    proc = subprocess.Popen('mkdir ' + capsdir, shell=True,cwd=resultdir,close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.wait()
    for file1 in name:
        fname = file1.split(',')[0]
        proc = subprocess.Popen('mv ' + tmpdir +'/CAPS_output/selected_CAPS_primers_' + fname + '.txt ' + capsdir + '/',shell=True,cwd=resultdir,close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.wait()
        proc = subprocess.Popen('cp ' + tmpdir +'/blast_out.txt ' + capsdir + '/' + fname +'_blast_out.txt',shell=True,cwd=resultdir,close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.wait()
        proc = subprocess.Popen('cp ' + tmpdir +'/alignment_raw_' + fname + '.fa ' + capsdir + '/',shell=True,cwd=resultdir,close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.wait()
    proc = subprocess.Popen('tar czvf ' + capsdir + '.tar.gz ' + capsdir,shell=True,cwd=resultdir,close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.wait()
    print('<a href="/snprimer/result/' + capsdir + '.tar.gz' + '">CAPS result</a><br><br>')
    
if kasp == '1':
    kaspdir = 'My_KASP_' + random_num
    proc = subprocess.Popen('mkdir ' + kaspdir, shell=True,cwd=resultdir,close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.wait()
    for file1 in name:
        fname = file1.split(',')[0]
        proc = subprocess.Popen('mv ' + tmpdir +'/KASP_output/selected_KASP_primers_' + fname + '.txt ' + kaspdir + '/',shell=True,cwd=resultdir,close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.wait()
        proc = subprocess.Popen('cp ' + tmpdir +'/blast_out.txt ' + kaspdir + '/' + fname +'_blast_out.txt',shell=True,cwd=resultdir,close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.wait()
        proc = subprocess.Popen('cp ' + tmpdir +'/alignment_raw_' + fname + '.fa ' + kaspdir + '/',shell=True,cwd=resultdir,close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.wait()
    proc = subprocess.Popen('tar czvf ' + kaspdir + '.tar.gz ' + kaspdir,shell=True,cwd=resultdir,close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.wait()
    proc = subprocess.Popen('rm -fr /var/www/html/snprimer/tmp/flanking_temp_marker_* /var/www/html/snprimer/tmp/temp_marker_* /var/www/html/snprimer/tmp/renamed_flanking_temp_marker* /var/www/html/snprimer/tmp/alignment_raw_*',shell=True,cwd=resultdir,close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.wait()
    print('<a href="/snprimer/result/' + kaspdir + '.tar.gz' +  '"> KASP result</a>')
print('<br><br>Check files beginning with \'selected_\' in the CAPS_output or KASP_output file<br><br>')
print('Finish !!!!!<br>')

print('</div>')
print('</pre>')
print('</div>')

print('''<script  type="text/javascript">
            function download(){
            var save = document.getElementById("seq").innerText;
            var save2 = save.trim().split("\\n").map(line => line.trim()).join("\\n");
            var blob = new Blob([save2], {type: "text/plain;charset=utf-8"});
            saveAs(blob, "Sequence_download.txt");}
        </script>''')
print('''<script  type="text/javascript">
            function gotoblastn() {
            var save = document.getElementById("seq").innerText;
            var save2 = save.trim().split("\\n").map(line => line.trim()).join("\\n");
            window.open("/blast/blast.html");}
    </script>''')
print('<div id="footer"></div>')

print('</body>')
print('</html>')
