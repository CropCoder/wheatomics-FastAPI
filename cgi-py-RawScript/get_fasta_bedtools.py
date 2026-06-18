#!/usr/bin/python2.7
# -*- coding: utf-8 -*-

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
    import cgitb; cgitb.enable()
except:
    pass
import cgi
import subprocess
import re

form = cgi.FieldStorage()

DbPath = '/var/www/html/getfasta/blastdb/'
DATALIB = form["database"].value
name = form["ID"].value.strip().split() 
print('<pre>')
print('''<button style="color:white;background-color:#007DBC;border-color:#007BFF" id="button" onclick="download();">Download Sequence</button>&nbsp;&nbsp;<button style="color:white;background-color:#007DBC;border-color:#007BFF" id="button" onclick="gotoblastn();">BLAST</button>''')
print('<div id=seq>')
if "genome" in DATALIB:
    strand = 'plus'
    for seq in name:
        if ':' in seq and '_' in seq:
            if 'hr' in seq and '_' in seq :
                nam = seq.split(":")[0]
                start = re.split('-|\.\.', seq.split(":")[1])[0]
                end = re.split('-|\.\.', seq.split(":")[1])[1]
                if 0<int(end)- int(start) <= 5000000:
                    database = DbPath + DATALIB 
                    order ='/usr/bin/blastdbcmd -db ' + database + ' -line_length 110 -entry ' + nam + ' -range ' + start + '-' + end + ' -strand ' + strand
                    proc = subprocess.Popen(['/bin/bash', '-c', order], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                    out = proc.stdout.read()
                    print(out.strip())
            elif 'hr' in seq and '_' not in seq:
                new = DATALIB[:-7]
                nam = seq.split(":")[0] + '_' + new
                start = re.split('-|\.\.', seq.split(":")[1])[0]
                end = re.split('-|\.\.', seq.split(":")[1])[1]
                if 0<int(end)- int(start) <= 5000000:
                    database = DbPath + DATALIB 
                    order ='/usr/bin/blastdbcmd -db ' + database + ' -line_length 110 -entry ' + nam + ' -range ' + start + '-' + end + ' -strand ' + strand
                    proc = subprocess.Popen(['/bin/bash', '-c', order], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                    out = proc.stdout.read()
                    print(out.strip())
            else:
                print("If you want get a sequence from chromosome region(<=5000000bp), your input format must be like chr1A:10-100.")
                print("<br>")
                print("But if you just want to get a gene or marker sequence, your input only needs a name or ID.")
                
        else:
            print("If you want get a sequence from chromosome region(<=5000000bp), your input format must be like chr1A:10-100.")
            print("<br>")
            print("But if you just want to get a gene or marker sequence, your input only needs a name or ID.")
            
 
else:
    for seq in name:
        database = DbPath + DATALIB 
        order ='/usr/bin/blastdbcmd -db ' + database + ' -entry ' + seq
        proc = subprocess.Popen(['/bin/bash', '-c', order], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = proc.stdout.read()
        print(out.strip())
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
