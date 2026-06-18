#!/usr/bin/env python2.7
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


form = cgi.FieldStorage()

DbPath = '/var/www/html/getfasta/blastdb/'
genome_db = DbPath + form["genome_db"].value
gene_id = form["gene_id"].value
gene_db = DbPath + form["gene_db"].value
protein_id = form["protein_id"].value
protein_db = DbPath + form["protein_db"].value
chrom = form["chrom"].value
start= form["start"].value
end= form["end"].value
print('<pre>')
print('''<button style="color:white;background-color:#007DBC;border-color:#007BFF" id="button" onclick="download();">Download Sequence</button>&nbsp;&nbsp;<button style="color:white;background-color:#007DBC;border-color:#007BFF" id="button" onclick="gotoblastn();">BLAST</button>''')
print('<div id=seq>')

strand = 'plus'

order1 ='/usr/bin/blastdbcmd -db ' + genome_db + ' -line_length 110 -entry ' + chrom + ' -range ' + start + '-' + end + ' -strand ' + strand
proc1 = subprocess.Popen(['/bin/bash', '-c', order1], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
out1 = proc1.stdout.read()
print(out1.strip())

order2 ='/usr/bin/blastdbcmd -db ' + gene_db + ' -entry ' + gene_id
proc2 = subprocess.Popen(['/bin/bash', '-c', order2], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
out2 = proc2.stdout.read()
print(out2.strip())

order3 ='/usr/bin/blastdbcmd -db ' + protein_db + ' -entry ' + protein_id
proc3 = subprocess.Popen(['/bin/bash', '-c', order3], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
out3 = proc3.stdout.read()
print(out3.strip())
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
