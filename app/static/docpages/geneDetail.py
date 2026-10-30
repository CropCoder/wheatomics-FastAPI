#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

try:
    import cgitb; cgitb.enable()
except:
    pass
import cgi
cgitb.enable(display=0, logdir='/var/www/html/genepage/')
import subprocess
import MySQLdb

form = cgi.FieldStorage()

geneid = form["search"].value.strip()

# The legacy page embeds an http:// JBrowse iframe, which browsers block on the
# https site (mixed content); send users to the new SPA gene page instead.
if not form.getvalue("legacy"):
    try:
        import urllib
        quoted = urllib.quote(geneid, safe="")
    except Exception:
        from urllib.parse import quote
        quoted = quote(geneid, safe="")
    print("Status: 302 Found")
    print("Location: /GeneHub/gene.html?gene=" + quoted)
    print("")
    raise SystemExit


def escape_html(value):
    """Minimal HTML escaping for values this script echoes itself.

    The gene ID comes straight from the query string, so it must not be
    reflected into the new V2.0 hero block as raw markup.
    """
    return (str(value).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


geneid_html = escape_html(geneid)

print("Content-Type: text/html")
print("")
print('''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="WheatOmics 2.0 GeneHub gene page: IWGSCv1 annotation, genomic context, JBrowse tracks, expression and co-expression, protein interactions and curated external resources for a wheat gene.">
  <title>GeneHub | WheatOmics 2.0</title>
  <link rel="shortcut icon" href="/favicon.ico" type="image/x-icon">
  <link rel="stylesheet" href="/api/v2shell/shell.css">
  <style>
    /* GeneHub result page - skin for the legacy #genetable markup */
    .gd-toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 16px; }
    .gd-toolbar-note { margin: 0; color: var(--muted); font-size: 12px; }
    .gd-gene-head { margin: 2px 0 14px; }
    .gd-gene-head h2 { margin: 0 0 4px; color: var(--forest-deep); font-family: var(--display); font-size: 21px; font-weight: 750; letter-spacing: -.02em; }
    .gd-gene-head h2 em { color: var(--leaf); font-style: normal; }
    .gd-gene-sub { margin: 0; color: var(--muted); font-size: 12px; }
    .gd-table-wrap { width: 100%; overflow-x: auto; }
    #genetable { width: 100%; border-collapse: collapse; }
    #genetable th, #genetable td { border: 1px solid var(--line); padding: 9px 12px; font-size: 13px; line-height: 1.7; vertical-align: top; }
    #genetable th { width: 200px; color: #4d6559; background: var(--mist); text-align: left; font-weight: 700; white-space: nowrap; }
    #genetable td { color: var(--ink); background: #fff; }
    #genetable a { color: var(--leaf); }
    #genetable a:hover { color: var(--forest); text-decoration: underline; }
    #genetable iframe { display: block; width: 100%; max-width: 900px; border: 1px solid var(--line) !important; border-radius: 10px; background: #fff; }
    #genetable select { max-width: 100%; padding: 5px 8px; color: var(--ink); background: #fbfdfb; border: 1px solid var(--line); border-radius: 8px; font-size: 12px; }
    #genetable input[type="submit"] { padding: 7px 14px; color: #fff; background: var(--forest); border: 1px solid var(--forest); border-radius: 8px; font-size: 12px; font-weight: 700; cursor: pointer; }
    #genetable input[type="submit"]:hover { background: var(--forest-deep); border-color: var(--forest-deep); }
    #genetable button { padding: 5px 10px; background: var(--mist) !important; border: 1px solid var(--line) !important; border-radius: 8px; }
    #genetable button a { color: var(--forest) !important; font-weight: 700; }
    #genetable button:hover { border-color: rgba(17,134,83,.35) !important; }
    @media (max-width: 720px) {
      #genetable, #genetable tbody, #genetable tr, #genetable th, #genetable td { display: block; width: 100%; }
      #genetable tr { margin-bottom: 12px; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
      #genetable th { border: 0; border-bottom: 1px solid var(--line); white-space: normal; }
      #genetable td { border: 0; }
      #genetable select { width: 100%; }
      #genetable iframe { max-width: 100%; }
    }
  </style>
</head>
<body>
  <div id="v2-shell-header"></div>

  <main id="main-content">
    <section class="news-hero">
      <div class="container news-hero-inner">
        <div>
          <p class="news-kicker">WheatOmics 2.0 · Gene page</p>
          <h1 class="news-title">Gene <em>''' + geneid_html + '''</em></h1>
          <p class="news-lead">Annotation, genomic context, JBrowse tracks, expression and co-expression, protein interactions and curated external resources for this wheat gene.</p>
          <div class="news-stats">
            <span class="news-stat"><strong>GeneHub</strong> IWGSCv1 record</span>
            <span class="news-stat">4 JBrowse track views</span>
            <span class="news-stat">Expression · Co-expression · PPI</span>
          </div>
        </div>
        <div class="news-hero-mark" aria-hidden="true"><svg class="icon"><use href="#i-gene"/></svg></div>
      </div>
    </section>

    <section class="news-body">
      <div class="container">
        <div class="card">
          <div class="card-body">
            <div class="gd-toolbar">
              <p class="gd-toolbar-note">Gene record from the GeneHub database (IWGSC RefSeqv1.1 annotation).</p>
              <a class="v2-chip" href="/GeneHub/">&larr; GeneHub search</a>
            </div>
''')
try:
    sql = "SELECT * FROM GenePageIWGSCv1_table WHERE GeneIDv2='" + geneid + "' or GeneIDv1='" + geneid + "' or GeneIDv3='" + geneid + "';"
    mydb = MySQLdb.connect(host='localhost',
                           user='wheatomics_user',
                           passwd=__import__('wheat_dbpass').DB_PASSWORD,
                           db='Genehub_DB',
                           charset='utf8')
    cursor = mydb.cursor()
    cursor.execute(sql)
    row = cursor.fetchall()
except Exception as e:
    row = []
    print('<div class="alert alert-danger" role="alert">GeneHub could not load the record for <strong>' + geneid_html + '</strong>: ' + escape_html(e) + '</div>')
else:
    if not row:
        print('<div class="news-state">No GeneHub annotation record was found for <strong>' + geneid_html + '</strong>. Check the gene ID or <a href="/GeneHub/">search GeneHub</a> again.</div>')

    for ele in row:
      print('<div class="gd-gene-head"><h2>Gene information for <em>' + ele[2] + '</em></h2><p class="gd-gene-sub">GeneHub record, IWGSC RefSeqv1.1 annotation</p></div>')
      print('<div class="gd-table-wrap"><table id="genetable"><tbody><tr><th>GeneID:</th><td style="text-align:left">' + ele[2] + '<br>' + ele[3] + '<br>' + ele[4] + '</td></tr>')
      print('<tr><th>Description:</th><td>' + ele[12] + '</td></tr>')
      print('<tr><th>Location:</th><td>' + ele[1] + '_' + ele[5] + ':' + str(ele[6]) + ' - ' + str(ele[7]) + '</td></tr>')
      print('<tr><th>Strand:</th><td>' + ele[8] + '</td></tr>')
      print('<tr><th>Protein length:</th><td>' + ele[9] + '</td></tr>')
      print('<tr><th>Molecular Weight:</th><td>' + ele[10] + '</td></tr>')
      print('<tr><th>Isoelectric points:</th><td>' + ele[11] + '</td></tr>')
      print('<tr><th>Function:</th><td>' + ele[13] +'<br>' + ele[14] + '<br>' +ele[15] + '</td></tr>')
      # Phase separation (wheatPSP) — same <th>:</th> row style as Function.
      # Best-effort: any DB error just prints a dash, never breaks the page.
      try:
          psp_db = MySQLdb.connect(host='localhost', user='wheatomics_user', passwd=__import__('wheat_dbpass').DB_PASSWORD, db='wheat_psp_db', charset='utf8')
          psp_cur = psp_db.cursor()
          cand_norm = []
          for cand in [str(ele[2]).strip(), str(ele[3]).strip(), str(ele[4]).strip()]:
              if cand.endswith('.1'):
                  cand = cand[:-2]
              if cand and cand not in cand_norm:
                  cand_norm.append(cand)
          ge = " OR ".join(["cs_gene_id='" + c + "'" for c in cand_norm]) if cand_norm else "1=0"
          psp_cur.execute("SELECT seq_id, ps_score, is_psp, molphase_score, has_prd, plaac_llr, plaac_papa_prop FROM wheat_psp WHERE " + ge + " ORDER BY id")
          psp_rows = psp_cur.fetchall()
          psp_db.close()
      except Exception:
          psp_rows = []
      if psp_rows:
          any_psp = any(r[2] == 1 for r in psp_rows)
          any_prd = any(r[4] == 1 for r in psp_rows)
          lines = ['Predicted PSP: ' + ('YES' if any_psp else 'NO') + (' | PrD: YES' if any_prd else '')]
          for r in psp_rows[:6]:
              lines.append('seq ' + str(r[0]) + ': ps_score ' + str(r[1]) +
                           ' | MolPhase ' + str(r[3]) +
                           ' | PrD ' + ('YES' if r[4] == 1 else 'NO') +
                           ' | PLAAC LLR ' + str(r[5]) + ' | PAPA prop ' + str(r[6]))
          if len(psp_rows) > 6:
              lines.append('... ' + str(len(psp_rows) - 6) + ' more transcript(s)')
          psp_link = '<a href="/wheatPSP/#/gene/' + cand_norm[0] + '" target="_blank">View in wheatPSP &raquo;</a>'
          print('<tr><th>Phase separation:</th><td>' + '<br>'.join(lines) + '<br>' + psp_link + '</td></tr>')
      else:
          print('<tr><th>Phase separation:</th><td>&mdash;</td></tr>')
      print('<tr><th>GetSequence:</th><td><button style="color:white;background-color:#007DBC;border-color:#007BFF" id="button"> <a style="color:white;" href="https://wheatomics.sdau.edu.cn/getfasta/?query=' + ele[2] +'.1&database=all_genes" target="_blank">Get sequence (new GetSequence)</a></button></td></tr>')
      print('''<tr><th>Gene structure:</th><td><p style="font-size:12px;" align="right"> <a href="http://wheatomics.sdau.edu.cn/jbrowse-1.12.3-release/?data=Chinese_Spring1.0&loc='''+ ele[5]+ '%3A' + str(ele[6]-200)+'..'+ str(ele[7]+200) + '&tracks=IWGSCv1.1_HC_LC&amp;tracklist=0&amp;nav=0&amp;overview=0&amp;fullviewlink=0"' + ''' target="jbrowse1">Center on '''+ ele[2] +''' </a> | <a href="http://wheatomics.sdau.edu.cn/jbrowse-1.12.3-release/?data=Chinese_Spring1.0&loc='''+ ele[5]+ '%3A' + str(ele[6]-200)+'..'+ str(ele[7]+200) + '&tracks=IWGSCv1.1_HC_LC"' +''' target="_blank">Full-screen view</a></p>
    <iframe name="jbrowse1" src="http://wheatomics.sdau.edu.cn/jbrowse-1.12.3-release/?data=Chinese_Spring1.0&loc='''+ ele[5]+ '%3A' + str(ele[6]-200)+'..'+ str(ele[7] + 200) + '&tracks=IWGSCv1.1_HC_LC&amp;tracklist=0&amp;nav=0&amp;overview=0&amp;fullviewlink=0"' +''' style="border: 1px solid black" width="900" height="200"></iframe></td></tr>''')
      print('''<tr><th>GeneExpression:</th><td><FORM target="_blank" ACTION="/cgi-bin/gene_expression.py" METHOD="GET"><INPUT TYPE="submit" VALUE="Get Expression">
     <select name="expressiontable">
        <optgroup label=" wheat developmental tissues" style="font-weight:bold;">
            <option VALUE="PRJEB25639_tbl"> BCS cv-1 Development
            <option VALUE="PRJEB5314_paired_tbl" selected="selected"> Chinese Spring cv-1 Development (pair)
            <option VALUE="PRJEB5314_single_tbl"> Chinese Spring cv-1 Development (single)
            <option VALUE="PRJEB5135_tbl"> developing wheat grain
            <option VALUE="PRJNA485741_tbl"> Expression of embryo and endosperm in developing grain
            <option VALUE="PRJEB7795_tbl"> Tissue layers from developing wheat grain at 12 days post-anthesis
            <option VALUE="PRJEB5029_tbl"> meiosis data (CS)
            <option VALUE="PRJNA297977_tbl">three stages from wheat microspore embryogenesis induction
            <option VALUE="PRJNA325489_tbl"> Early Wheat Spike Development    
    
        <optgroup label="wheat biotic stresses" style="font-weight:bold;">
            <option VALUE="PRJEB24686_tbl">  Fusarium head blight (FHB) 2DL
            <option VALUE="PRJNA327013_tbl"> Comparative transcriptomics of Zymoseptoria tritici isolates
            <option VALUE="PRJNA263755_tbl"> Fusarium crown rot (Qcrs-3B)
            <option VALUE="PRJEB12358_tbl">  FHB-resistance QTL Fhb1 and Qfhs.ifa-5A
            <option VALUE="PRJNA273659_tbl"> Fhb1+ Fhb1-
            <option VALUE="PRJNA297822_tbl">RNA-seq on Fusarium pseudograminearum infected wheat
            <option VALUE="PRJNA307989_tbl"> Examining the effects of F. graminearum infection on FHB susceptible wheat cultivar 'fielder'.
            <option VALUE="PRJEB21835_tbl"> Xanthomonas translucens infection
            <option VALUE="PRJEB21874_tbl"> mycorhizal fungi with and without Xanthomonas translucens infection
            <option VALUE="PRJNA327829_tbl"> Pyrenophora tritici-repentis inoculation 
            <option VALUE="PRJEB23056_tbl"> Elicitation with PAMPs
            <option VALUE="PRJNA243835_powdery_tbl"> Powdery Mildew Pathogen Stress
            <option VALUE="PRJEB8798_tbl"> Time course of Z.tritici X days post inoculation on wheat leafs
            <option VALUE="PRJNA243835_stripe_tbl"> Stripe rust Pathogen Stress
            <option VALUE="PRJEB13569_tbl"> Field Pathogenomics of Wheat Blast
            <option VALUE="PRJNA307228_tbl"> stripe rust Pathogen Stress(Xingzi 9104 )
            <option VALUE="PRJNA325136_tbl"> Transcriptome analysis of a stem rust resistance locus on wheat chromosome 7AL
            <option VALUE="PRJNA328385_tbl"> NIL Carrying Lr57 Under Compatible and Incompatible interactions

        <optgroup label="wheat abiotic stresses" style="font-weight:bold;">
            <option VALUE="PRJDB2496_tbl"> phosphate (Pi) starvation condition(CS)
            <option VALUE="PRJEB8762_tbl"> gene expression data for the 12 and sample
            <option VALUE="PRJNA253535_tbl"> wheat tissues grown at 23 and 4
            <option VALUE="PRJNA257938_tbl"> drought and heat stress
            <option VALUE="PRJNA358808_tbl"> stress treatment (drought, heat, and drought + heat) leaf, root and grain tissues
            <option VALUE="PRJNA171754_tbl"> tolerant and susceptible wheat cultivar under heat stress
            <option VALUE="PRJNA427246_tbl"> Unveiling multidimensional regulations of heat stress-responsive transcriptomes in wheat
            <option VALUE="PRJNA293629_tbl"> transcriptome response of two wheat cultivers to salt stress
            <option VALUE="PRJNA487923_tbl"> The root transcriptome profiling of the salt stress response    
            <option VALUE="PRJNA306536_tbl"> PEG(6000)
            <option VALUE="Wangmeng_NR_tbl"> Nitrogen treatment
            <optgroup label="Others" style="font-weight:bold;">
            <option VALUE="PRJNA362497_tbl"> Leaf transcriptome between wild type and a chlorophyll-deficient mutant
            <option VALUE="PRJNA322418_tbl"> gene imprinting analysis
                <option VALUE="PRJEB25586_tbl"> early meiosis in wheat in the presence and absence of the Ph1 locus
            <option VALUE="PRJNA353130_tbl"> Global studies of miR9678 function in wheat
            <option VALUE="DMSO_GA_JA_tpm_mean_tbl"> Fielder leaf was treated 1h with DMSO,GA and JA.
            <option VALUE="ABA_JA_6BA_DMSO3h_mean_tbl"> Fielder leaf was treated 3h with DMSO,ABA, 6-BA and JA.
            <option VALUE="PRJNA396738_tbl"> two NILs segregating for a major grain weight QTL located on wheat chromosome arm 5AL
            <option VALUE="PRJNA341486_tbl"> Identification of key genes for wax production
            <option VALUE="PRJNA348655_tbl"> Transcriptome association identifies regulators of wheat grain production
            <option VALUE="PRJNA471426_tbl"> a mutant wheat line exhibited increased grain size and 1000-grain weight
            <option VALUE="PRJEB22854_tbl"> RNA-seq of pericarp of purple-grain wheat
            <option VALUE="PRJNA307237_tbl"> Transcriptome analysis of flag leaf during its senescence in wheat
            <option VALUE="PRJNA477934_tbl"> RNA seq data from tetraploid wheat, hexaploid wheat and reciprocally crossed endosperm
        </select><input Name="ID" type = "hidden" type="text" value="'''+ ele[2] + '''"></form></td></tr>''')
      print('''<tr><th>Co-expression:</th><td><FORM target="_blank" ACTION="/cgi-bin/co-expression.py" METHOD="GET"><INPUT TYPE="submit" VALUE="Get Co-expression">
      <select name="query"><option VALUE="CO_result2">  Wheat Grain&nbsp;&nbsp;</option><option VALUE="CO_PRJEB25639" selected=selected>  Wheat multiple tissues&nbsp;&nbsp;</option></select>
     <select name="filter">
        <optgroup label="Pearson Correlation coefficient" style="font-weight:bold;">
        <option VALUE="0.9"> PCC >= 0.9</option>
        <option VALUE="0.8" selected="selected"> PCC >= 0.8 </option>
        <option VALUE="0.7"> PCC >= 0.7 </option>
        <option VALUE="0.6"> PCC >= 0.6 </option>
        <optgroup label="Mutual Rank" style="font-weight:bold;">
        <option VALUE="30"> MR <= 30 </option>
        <option VALUE="90"> MR <= 90 </option>
        <option VALUE="300"> MR <= 300 </option>
        <option VALUE="600"> MR <= 600 </option>
        <option VALUE="900"> MR <= 900 </option>
        <option VALUE="1200"> MR <= 1200 </option>
        <option VALUE="1500"> MR <= 1500 </option>
        <option VALUE="1800"> MR <= 1800 </option>
</select><input Name="ID" type = "hidden" type="text" value="'''+ ele[2] + '''"></form></td></tr>''')
      print('''<tr><th>WheatPPI:</th><td><FORM target="_blank" ACTION="/cgi-bin/get_wheatPPI.py" METHOD="GET"><INPUT TYPE="submit" VALUE="Get protein interactions">
      <select name="query">
        <option VALUE="PPI_result"> WheatPPI database</option>
      </select>
      <select name="filter">
        <option VALUE="0.5">  > 0.5 </option>
        <option VALUE="0.2">  > 0.2 </option>
        <option VALUE="0">  all </option>
      </select>
      <input Name="ID" type = "hidden" type="text" value="'''+ ele[2] + '''.1"></form></td></tr>''')

      print('<tr><th>HomologFinder:</th><td><button style="color:white;background-color:#007DBC;border-color:#007BFF" id="button"> <a style="color:white;" href="http://wheatomics.sdau.edu.cn/cgi-bin/wheat_rice_arabidopsis.py?query2=WheatRiceArabidopsis_tbl&filter2=3&ID2=' + ele[2] + '" target="_blank">Find homologs in rice and Arabidopsis</a></button>  |   <button style="color:white;background-color:#007DBC;border-color:#007BFF" id="button"> <a style="color:white;" href="http://wheatomics.sdau.edu.cn/cgi-bin/triticeae_gene_search.py?query3=Triticeae_table&filter3=1&ID3=' + ele[2] + '" target="_blank">Find homologs in Triticeae </a></button></td></tr>')
      print('<tr><th>EMS Mutants :</th><td><p style="font-size:12px;" align="right"> <a href="http://wheatomics.sdau.edu.cn/jbrowse-1.12.3-release/?data=Chinese_Spring1.0&loc='''+ ele[5]+ '%3A' + str(ele[6]-200)+'..'+ str(ele[7]+200) + '&tracks=IWGSCv1.1_HC_LC%2CCadenza_Kronos_EMS%2CJimai%20EMS%20MutantsS&amp;tracklist=0&amp;nav=0&amp;overview=0&amp;fullviewlink=0"' + ''' target="jbrowse2">Center on '''+ ele[2] +''' </a> | <a href="http://wheatomics.sdau.edu.cn/jbrowse-1.12.3-release/?data=Chinese_Spring1.0&loc='''+ ele[5]+ '%3A' + str(ele[6]-200)+'..'+ str(ele[7]+200) + '&tracks=IWGSCv1.1_HC_LC%2CCadenza_Kronos_EMS%2CJimai%20EMS%20MutantsS"' +''' target="_blank">Full-screen view</a></p>
    <iframe name="jbrowse2" src="http://wheatomics.sdau.edu.cn/jbrowse-1.12.3-release/?data=Chinese_Spring1.0&loc='''+ ele[5]+ '%3A' + str(ele[6]-200)+'..'+ str(ele[7] + 200) + '&tracks=IWGSCv1.1_HC_LC%2CCadenza_Kronos_EMS%2CJimai%20EMS%20MutantsS&amp;tracklist=0&amp;nav=0&amp;overview=0&amp;fullviewlink=0"' +''' style="border: 1px solid black" width="900" height="300"></iframe></td></tr>''')
      print('<tr><th>Variants in the natural population :</th><td><p style="font-size:12px;" align="right"> <a href="http://wheatomics.sdau.edu.cn/jbrowse-1.12.3-release/?data=Chinese_Spring1.0&loc='''+ ele[5]+ '%3A' + str(ele[6]-200)+'..'+ str(ele[7]+200) + '&tracks=IWGSCv1.1_HC_LC%2C1000%20wheat%20exomes%2CVmap%201.0%2Ccommonwheat63WGS&amp;tracklist=0&amp;nav=0&amp;overview=0&amp;fullviewlink=0"' + ''' target="jbrowse3">Center on '''+ ele[2] +''' </a> | <a href="http://wheatomics.sdau.edu.cn/jbrowse-1.12.3-release/?data=Chinese_Spring1.0&loc='''+ ele[5]+ '%3A' + str(ele[6]-200)+'..'+ str(ele[7]+200) + '&tracks=IWGSCv1.1_HC_LC%2C1000%20wheat%20exomes%2CVmap%201.0%2Ccommonwheat63WGS"' +''' target="_blank">Full-screen view</a></p>
    <iframe name="jbrowse3" src="http://wheatomics.sdau.edu.cn/jbrowse-1.12.3-release/?data=Chinese_Spring1.0&loc='''+ ele[5]+ '%3A' + str(ele[6]-200)+'..'+ str(ele[7] + 200) + '&tracks=IWGSCv1.1_HC_LC%2C1000%20wheat%20exomes%2CVmap%201.0%2Ccommonwheat63WGS&amp;tracklist=0&amp;nav=0&amp;overview=0&amp;fullviewlink=0"' +''' style="border: 1px solid black" width="900" height="300"></iframe></td></tr>''')
      print('<tr><th>CRISPR/Cas9 sgRNA :</th><td><p style="font-size:12px;" align="right"> <a href="http://wheatomics.sdau.edu.cn/jbrowse-1.12.3-release/?data=Chinese_Spring1.0&loc='''+ ele[5]+ '%3A' + str(ele[6]-200)+'..'+ str(ele[7]+200) + '&tracks=IWGSCv1.1_HC_LC%2CsgRNA_Cas9&amp;tracklist=0&amp;nav=0&amp;overview=0&amp;fullviewlink=0"' + ''' target="jbrowse4">Center on '''+ ele[2] +''' </a> | <a href="http://wheatomics.sdau.edu.cn/jbrowse-1.12.3-release/?data=Chinese_Spring1.0&loc='''+ ele[5]+ '%3A' + str(ele[6]-200)+'..'+ str(ele[7]+200) + '&tracks=IWGSCv1.1_HC_LC%2CsgRNA_Cas9"' +''' target="_blank">Full-screen view</a></p>
    <iframe name="jbrowse4" src="http://wheatomics.sdau.edu.cn/jbrowse-1.12.3-release/?data=Chinese_Spring1.0&loc='''+ ele[5]+ '%3A' + str(ele[6]-200)+'..'+ str(ele[7] + 200) + '&tracks=IWGSCv1.1_HC_LC%2CsgRNA_Cas9&amp;tracklist=0&amp;nav=0&amp;overview=0&amp;fullviewlink=0"' +''' style="border: 1px solid black" width="900" height="300"></iframe></td></tr>''')
      print('<tr><th>External links:</th><td> Subcellular localization: <a href="https://croppal.org/factsheet/' + ele[3] + '.1.html" target="_blank"> crop-pal </a><br><br>Gene network: <a href="https://knetminer.rothamsted.ac.uk/wheatknet/genepage?list=' + ele[2] + '" target="_blank">knetminer</a>')
      if 'A' in ele[2]:
            print('<br><br>MicroCollinearity:<a href="http://wheat.cau.edu.cn/TGT/m5/?navbar=MicroCollinearity&mul_geneID=' + ele[2] + '&mul_gnum=5&mul_region=&mul_species1=IWGSCv1p1_chrNA&mul_spec_table_select=zavitan_chrNA,tu_TuN" target="_blank">TGT</a></button>')
      elif 'B' in ele[2]:
            print('<br><br> MicroCollinearity: <a href="http://wheat.cau.edu.cn/TGT/m5/?navbar=MicroCollinearity&mul_geneID=' + ele[2] + '&mul_gnum=5&mul_region=&mul_species1=IWGSCv1p1_chrNB&mul_spec_table_select=svevo_chrNB,zavitan_chrNB" target="_blank">TGT</a></button>')
      elif 'D' in ele[2]:
            print('<br><br> MicroCollinearity:<a href="http://wheat.cau.edu.cn/TGT/m5/?navbar=MicroCollinearity&mul_geneID=' + ele[2] + '&mul_gnum=5&mul_region=&mul_species1=IWGSCv1p1_chrND&mul_spec_table_select=aet_ChrN" target="_blank">TGT</a>')
      else:
            print('')
      if 'Unknown' in ele[17]:
            print('')
      else:
          print('<br><br> Proteome: <a href="https://wheatproteome.org/protein-details/'+ ele[17] + '" target="_blank">Wheat Proteome</a></button>')

      print('<br><br>More information: <a  href="https://ensembl.gramene.org/Triticum_aestivum/Gene/Summary?g=' + ele[2] + '" target="_blank">Ensembl Plants</a>')
      if 'Unknown' in ele[16]:
            pass
      else:
            print('&nbsp;&nbsp;|&nbsp;&nbsp;<a href="https://www.uniprot.org/uniprot/' + ele[16] + '" target="_blank">UniPort</a>') 
      print('</td></tr>')
      print('</tbody></table></div>')

try:
    cursor.close()
    mydb.close()
except Exception:
    pass

print('''          </div>
        </div>
      </div>
    </section>
  </main>

  <div id="v2-shell-footer"></div>

  <script src="/api/v2shell/shell.js"></script>
</body>
</html>''')
