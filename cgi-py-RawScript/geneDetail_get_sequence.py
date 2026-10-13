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


def run_blastdbcmd(args):
    """Run blastdbcmd with stderr merged into stdout, as this page always did."""
    proc = subprocess.Popen(['/usr/bin/blastdbcmd'] + args,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.stdout.read().strip()


def fetch_genome(db, chrom, start, end):
    """Fetch a chromosome interval, tolerating a chr/Chr casing mismatch.

    The gene table and the chromosome database disagree on the first letter:
    GenePageIWGSCv1_table stores the arm as "chr6A" while all_genomes holds the
    entry as "Chr6A_Chinese_Spring1.0", and blastdbcmd matches entry names
    case-sensitively — the requested arm is only found in its own spelling.
    """
    candidates = [chrom]
    if len(chrom) > 3 and chrom[:3].lower() == 'chr':
        other = ('Chr' if chrom[0] == 'c' else 'chr') + chrom[3:]
        if other != chrom:
            candidates.append(other)
    first_output = None
    for candidate in candidates:
        out = run_blastdbcmd(['-db', db, '-line_length', '110', '-entry',
                              candidate, '-range', start + '-' + end,
                              '-strand', strand])
        if first_output is None:
            first_output = out
        if 'Entry not found' not in out:
            return out
    return first_output


print(fetch_genome(genome_db, chrom, start, end))
print(run_blastdbcmd(['-db', gene_db, '-entry', gene_id]))
print(run_blastdbcmd(['-db', protein_db, '-entry', protein_id]))
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
