#!/usr/bin/python2.7
# -*- coding: utf-8 -*-

import cgi
import MySQLdb
import sys
from highcharts import Highchart

# 开启调试模式：如果脚本出错，会在网页直接显示详细错误
import cgitb
cgitb.enable()

# 设置编码
reload(sys)
sys.setdefaultencoding('utf-8')

# 打印 HTML 头部
print("Content-Type: text/html\n")
print("<!DOCTYPE html><html><head>")
print('<title>wheat expression</title>')
# 引入必需的 JS 资源
print('<script src="https://code.highcharts.com/highcharts.js"></script>')
print('<script src="https://code.highcharts.com/highcharts-more.js"></script>')
print('<script src="https://code.highcharts.com/modules/exporting.js"></script>')
print('<link rel="stylesheet" href="/css/bootstrap-4.5.3-dist/css/bootstrap.css" type="text/css" />')
print('<script src="/js/jquery/1.9.1/jquery.min.js"></script>')
print('</head><body>')
print('<div class="container mt-5">')

form = cgi.FieldStorage()

# 获取数据
selected_tables = form.getlist("expressiontable")
gene_input = form.getvalue("ID", "")
name = gene_input.strip().split()

if not selected_tables or not name:
    print('<div class="alert alert-danger">Please select database and input Gene ID.</div>')
    print('</div></body></html>')
    sys.exit()

# 连接数据库
try:
    mydb = MySQLdb.connect(host='localhost', user='wheatomics_user', passwd='wheatomics115599', db='gene_expression', charset='utf8')
    cursor = mydb.cursor()
except Exception as e:
    print('<div class="alert alert-danger">Database Connection Error: ' + str(e) + '</div>')
    sys.exit()

print('<h2 class="mb-4">Wheat Gene Expression Results</h2>')

# --- 主循环：遍历选中的每一个数据库 ---
for idx, expressiontable in enumerate(selected_tables):
    data = dict()
    categories = []
    ref_html = ""
    series_type = 'column'
    
    # 1. 对应原始脚本中的 50 多个分支配置
    # 注意：这里需要涵盖所有数据库的 Categories
    if expressiontable == 'PRJEB25639_tbl':
        series_type = 'line'
        categories = ['radicle at Seedling stage', 'coleoptile at Seedling stage', 'roots at Seedling stage', 'stem axis at Seedling stage', 'shoot apical meristem at Seedling stage', 'first leaf sheath at Seedling stage', 'first leaf blade at Seedling stage', 'roots at three leaf stage', 'axillary roots at three leaf stage', 'root apical meristem at three leaf stage', 'third leaf sheath at three leaf stage', 'third leaf blade at three leaf stage', 'fifth leaf sheath at fifth leaf stage', 'fifth leaf blade at fifth leaf stage', 'roots at Tillering stage', 'root apical meristem at Tillering stage', 'shoot apical meristem at Tillering stage', 'shoot axis at Tillering stage', 'first leaf sheath at Tillering stage', 'first leaf blade at Tillering stage', 'roots at Flag leaf stage', 'shoot axis at Flag leaf stage', 'fifth leaf sheath at Flag leaf stage', 'fifth leaf blade at Flag leaf stage', 'flag leaf blade night (-0.25h) 06:45 at Flag leaf stage', 'flag leaf blade night (+0.25h) 07:15 at Flag leaf stage', 'fifth leaf blade night (-0.25h) 21:45 at Flag leaf stage', 'fifth leaf blade night (+0.25h) 22:15 at Flag leaf stage', 'flag leaf blade at Flag leaf stage', 'flag leaf sheath at Full boot', 'flag leaf blade at Full boot', 'leaf ligule at Full boot', 'shoot axis at Full boot', 'spike at Full boot', 'fifth leaf blade at Ear emergence', 'flag leaf sheath at Ear emergence', 'flag leaf blade at Ear emergence', 'Internode sec at Ear emergence', 'glumes at Ear emergence', 'lemma at Ear emergence', 'peduncle at Ear emergence', 'awns at Ear emergence', 'roots at 30% spike', 'Internode sec at 30% spike', 'flag leaf sheath at 30% spike', 'flag leaf blade at 30% spike', 'peduncle at 30% spike', 'spike at 30% spike', 'spikelets at 30% spike', 'flag leaf blade night (-0.25h) 06:45 at anthesis', 'fifth leaf blade night (-0.25h) 21:45 at anthesis', 'stigma & ovary at anthesis', 'anther at anthesis', 'fifth leaf blade (senescence) at milk grain stage', 'flag leaf sheath at milk grain stage', 'flag leaf blade at milk grain stage', 'Internode sec at milk grain stage', 'shoot axis at milk grain stage', 'glumes at milk grain stage', 'peduncle at milk grain stage', 'lemma at milk grain stage', 'awns at milk grain stage', 'grain at milk grain stage', 'flag leaf blade (senescence) at Dough', 'embryo proper at Dough', 'endosperm at Dough', 'grain at Soft dough', 'grain at Hard dough', 'flag leaf blade (senescence) at Ripening', 'grain at Ripening']
        ref_html = 'Science. 2018 Aug 17;361(6403).'
    elif expressiontable == 'PRJEB13569_tbl':
        categories = ['LIB21745', 'LIB21746', 'LIB21747', 'LIB21748', 'LIB21749', 'LIB21750', 'LIB21751', 'LIB21752']
        ref_html = 'Field Pathogenomics of Wheat Blast PRJEB13569'
    elif expressiontable == 'PRJEB5135_tbl':
        categories = ['Room1_10DPA', 'Room1_AL_20DPA', 'Room1_AL_20DPA_Extra', 'Room1_TC_20DPA', 'Room1_SE_20DPA', 'Room1_REF_20DPA', 'Room1_AL.SE_30DPA', 'Room1_SE_30DPA', 'Room2_10DPA', 'Room2_AL_20DPA', 'Room2_TC_20DPA', 'Room2_SE_20DPA', 'Room2_REF_20DPA', 'Room2_AL.SE_30DPA', 'Room2_SE_30DPA']
        ref_html = 'Science. 2014 Jul 18; 345(6194).'
    elif expressiontable == 'PRJEB5314_paired_tbl':
        categories = ['root_Z10', 'root_Z13', 'root_Z39', 'stem_Z30', 'stem_Z32', 'stem_Z65', 'leaf_Z10', 'leaf_Z23', 'leaf_Z71', 'spike_Z32', 'spike_Z39', 'spike_Z65', 'grain_Z71', 'grain_Z75', 'grain_Z85']
        ref_html = 'Science 2014, doi: 10.1126/science.1251788'
    elif expressiontable == 'PRJEB5314_single_tbl':
        categories = ['root', 'stem', 'leaf', 'spike', 'grain']
        ref_html = 'Science 2014'
    elif expressiontable == 'PRJDB2496_tbl':
        categories = ['root_0day', 'root_10day_-P', 'shoot_0day', 'shoot_10day_-P']
        ref_html = 'BMC Genomics. 2013; 14: 77.'
    elif expressiontable == 'PRJEB5029_tbl':
        categories = ['latent_lepto', 'diplo_dia', 'zygo_pachy', 'metaphaseI']
        ref_html = 'PRJEB5029, INRA Clermont-Ferrand'
    elif expressiontable == 'PRJEB24686_tbl':
        categories = ['2618H2ORACH', '2618_FG_RACH', '2618_H2O_SP', '2618_FG_SP', '2890_H2O_SP', '2890_FG_SP', '2890_H2O_RACH', '2890_FG_RACH']
        ref_html = 'Front Plant Sci. 2018; 9: 37.'
    elif expressiontable == 'PRJNA327013_tbl':
        categories = ['Mock1-3dpi', 'Mock2-3dpi', 'Mock3-3dpi', 'Mock2-24dpi', 'Mock3-24dpi', 'Mock5-24dpi', '1A5-10-7d_R1', '1A5-1-7d_R1', '1A5-7-7d_R1', '1A5-3-12d_R1', '1A5-5-12d_R1', '1A5-7-12d_R1', '1A5-10-14d_R1', '1A5-8-14d_R1', '1A5-9-14d_R1', '1E4-4-7d_R1', '1E4-5-7d_R1', '1E4-6-7d_R1', '1E4-3-12d_R1', '1E4-6-12d_R1', '1E4-7-12d_R1', '1E4-10-14d_R1', '1E4-5-14d_R1', '1E4-8-14d_R1', '3D1-1-7d_R1', '3D1-2-7d_R1', '3D1-3-7d_R1', '3D1-2-12d_R1', '3D1-5-12d_R1', '3D1-8-12d_R1', '3D1-10-14d_R1', '3D1-7-14d_R1', '3D1-9-14d_R1', '3D7-10-7d_R1', '3D7-2-7d_R1', '3D7-8-7d_R1', '3D7-2-12d_R1', '3D7-3-12d_R1', '3D7-3-12d-rep', '3D7-6-12d_R1', '3D7-4-14d_R1', '3D7-5-14d_R1']
        ref_html = 'Comparative transcriptomics of Zymoseptoria tritici isolates'
    elif expressiontable == 'PRJNA263755_tbl':
        categories = ['1A_mock_3dpi', '1A_mock_5dpi', '1A_fusarium_3dpi', '1A_fusarium_5dpi', '1B_mock_3dpi', '1B_mock_5dpi', '1B_fusarium_3dpi', '1B_fusarium_5dpi', '2A_fusarium_5dpi', '2B_fusarium_5dpi', '3A_fusarium_5dpi', '3B_fusarium_5dpi', '4A_fusarium_5dpi', '4B_fusarium_5dpi', '9A_fusarium_5dpi', '9B_fusarium_5dpi']
        ref_html = 'PLoS One. 2014; 9(11): e113309.'
    elif expressiontable == 'PRJNA325489_tbl':
        categories = ['KNI', 'KNII', 'KNIII', 'KNIV', 'KNV', 'KNVI']
        ref_html = 'Scientific Reports DOI:10.1038/s41598-018-33718-y'
    elif expressiontable == 'PRJEB12358_tbl':
        categories = ['NIL38_M3', 'NIL38_F3', 'NIL38_M6', 'NIL38_F6', 'NIL38_M12', 'NIL38_F12', 'NIL38_M24', 'NIL38_F24', 'NIL38_M36', 'NIL38_F36', 'NIL38_M48', 'NIL38_F48', 'NIL51_M3', 'NIL51_F3', 'NIL51_M6', 'NIL51_F6', 'NIL51_M12', 'NIL51_F12', 'NIL51_M24', 'NIL51_F24', 'NIL51_M36', 'NIL51_F36', 'NIL51_M48', 'NIL51_F48']
        ref_html = 'Theor Appl Genet. 2016; 129: 1607–1623.'
    elif expressiontable == 'PRJEB21835_tbl':
        categories = ['Control_Root', 'Xt_Root', 'Control_Leaf', 'Xt_Leaf']
        ref_html = 'Xanthomonas translucens infection PRJEB21835'
    elif expressiontable == 'PRJEB21874_tbl':
        categories = ['MycorhizalFungiLeaf', 'MycorhizalFungiXanthomonasLeaf', 'MycorhizalFungiRoot', 'MycorhizalFungiXanthomonasRoot']
        ref_html = 'interactions with mycorhizal fungi PRJEB21874'
    elif expressiontable == 'PRJEB22854_tbl':
        categories = ['Grain_15dpa', 'Grain_15dpa_dark', 'Grain_20dpa', 'Grain_20dpa_dark']
        ref_html = 'pericarp of purple-grain wheat PRJEB22854'
    elif expressiontable == 'PRJEB23056_tbl':
        categories = ['H2O', 'H2O_30min', 'H2O_180min', 'Flag22_30min', 'Flag22_180min', 'Chitin_30min', 'Chitin_180min']
        ref_html = 'Physical and transcriptional organisation bioRxiv'
    elif expressiontable == 'PRJEB25586_tbl':
        categories = ['CS_Ph1_minus', 'CS_Ph1_plus']
        ref_html = 'early meiosis in wheat PRJEB25586'
    elif expressiontable == 'PRJEB7795_tbl':
        categories = ['endosperm_12DPA', 'inner_pericarp_12DPA','outer_pericarp_12DPA']
        ref_html = 'developing wheat grain PRJEB7795'
    elif expressiontable == 'PRJEB8762_tbl':
        categories = ['12℃', '24℃']
        ref_html = 'DNA methylation in hexaploid wheat PRJEB8762'
    elif expressiontable == 'PRJEB8798_tbl':
        categories = ['Mock_1dpi', 'Mock_4dpi', 'Mock_9dpi', 'Mock_14dpi', 'Mock_21dpi', 'Inoculation_1dpi', 'Inoculation_4dpi', 'Inoculation_9dpi', 'Inoculation_14dpi', 'Inoculation_21dpi']
        ref_html = 'Zymoseptoria tritici on wheat PRJEB8798'
    elif expressiontable == 'PRJNA243835_powdery_tbl':
        categories = ['non-innoculation', 'Powdery24h', 'Powdery48h', 'Powdery72h']
        ref_html = 'Powdery mildew Pathogen Stress PRJNA243835'
    elif expressiontable == 'PRJNA243835_stripe_tbl':
        categories = ['non-innoculation', 'Stripe24h', 'Stripe48h', 'Stripe72h']
        ref_html = 'Stripe rust Pathogen Stress PRJNA243835'
    elif expressiontable == 'PRJNA253535_tbl':
        categories = ['wheat23℃', 'wheat4℃']
        ref_html = 'temperature-induced lipid pathway PRJNA253535'
    elif expressiontable == 'PRJNA257938_tbl':
        categories = ['control', 'drought_1h', 'drought_6h', 'heat_1h', 'heat_6h', 'drough&theat_1h', 'drought&heat_6h']
        ref_html = 'heat and drought acclimation in wheat PRJNA257938'
    elif expressiontable == 'PRJNA273659_tbl':
        categories = ['Fhb1-Water_12hai', 'Fhb1+Water12hai', 'Fhb1-DON12hai', 'Fhb1+DON12hai', 'Fhb1-F.graminearum96haiRep1','Fhb1-F.graminearumrep2','Fhb1+F.graminearum96haiRep1', 'Fhb1+F.graminearum96haiRep2']
        ref_html = 'Triticum aestivum Transcriptome PRJNA273659'
    elif expressiontable == 'PRJNA297822_tbl':
        categories = ['Chara_Mock', 'Chara_Fp']
        ref_html = 'Fusarium pseudograminearum infected wheat PRJNA297822'
    elif expressiontable == 'PRJNA297977_tbl':
        categories = ['microspore embryogenesis S1', 'microspore embryogenesis S2', 'microspore embryogenesis S3']
        ref_html = 'wheat microspore embryogenesis induction PRJNA297977'
    elif expressiontable == 'PRJNA306536_tbl':
        categories = ['PEG6000_0h_Giza168', 'PEG600_02h_Giza168', 'PEG6000_12h_Giza168', 'PEG6000_0h_Gemmiza10', 'PEG6000_2h_Gemmiza10', 'PEG6000_12h_Gemmiza10']
        ref_html = 'PEG(6000) PRJNA306536'
    elif expressiontable == 'PRJNA307237_tbl':
        categories = ['DBF-L1', 'DAF-L2', 'DAF-L3', 'DAF-L4', 'DAF-L5']
        ref_html = 'flag leaf during its senescence PRJNA307237'
    elif expressiontable == 'PRJNA307989_tbl':
        categories = ['FHB', 'GA','ABA']
        ref_html = 'F. graminearum infection on FHB susceptible PRJNA307989'
    elif expressiontable == 'PRJNA325136_tbl':
        categories = ['Columbus_0dpi', 'ColumbusNS765_0dpi', 'ColumbusNS766_0dpi', 'Columbus_2dpi', 'ColumbusNS765_2dpi', 'ColumbusNS766_2dpi', 'Columbus_5dpi', 'ColumbusNS765_5dpi', 'ColumbusNS766_5dpi']
        ref_html = 'stem rust resistance locus on wheat PRJNA325136'
    elif expressiontable == 'PRJNA327829_tbl':
        categories = ['Glenlea_Control_Zero', 'Glenlea_Control_48pi', 'Glenlea_Toxin_48pi', 'Glenlea_Fungus_48pi', 'Salamouni_Control_Zero', 'Salamouni_Control_48pi', 'Salamouni_Toxin_48pi', 'Salamouni_Fungus_48pi']
        ref_html = 'Pyrenophora tritici-repentis inoculation PRJNA327829'
    elif expressiontable == 'PRJNA328385_tbl':
        categories = ['TaWL711_0hpi', 'TaWL711_12hpi', 'TaWL711_24hpi', 'TaWL711_48hpi', 'TaWL711_72hpi', 'TaWL711Lr57_0hpi', 'TaWL711Lr57_12hpi', 'TaWL711Lr57_24hpi', 'TaWL711Lr57_48hpi', 'TaWL711Lr57_72hpi']
        ref_html = 'NIL Carrying Lr57 PRJNA328385'
    elif expressiontable == 'PRJNA341486_tbl':
        categories = ['7279_non-glaucous', '7282_non-glaucous', '7284_non-glaucous', '7285_non-glaucous', '7287_non-glaucous', '7289_glaucous', '7290_glaucous', '7293_glaucous', '7294_glaucous']
        ref_html = 'Identification of key genes for wax production PRJNA341486'
    elif expressiontable == 'PRJNA322418_tbl':
        categories = ['doumai_15_20_25', 'doumai X keyi 15DPA', 'doumai X keyi 20DPA', 'doumai X keyi 25DPA', 'keyi_15_20_25', 'keyi X doumai 15DPA', 'keyi X doumai 20DPA', 'keyi X doumai 25DPA']
        ref_html = 'gene imprinting analysis PRJNA322418'
    elif expressiontable == 'PRJNA348655_tbl':
        series_type = 'line'
        categories = ['Aimengniu', 'Aodesa3', 'Baibiansui', 'Baidatou', 'Baihuamai', 'Baimaizi', 'Baimangmai', 'BaipuLuoqing', 'Baiqimai', 'Baiqiumai', 'Baituzitou', 'Banjiemang', 'Bendihuanghuamai', 'Chanbuzhi', 'Changmangshibiantou', 'Dabaimai', 'Dachunbaisilengmai', 'Dahuangpi', 'Daimanghongmai', 'Dakoumai', 'Dalibanmang', 'Dayuhua', 'EarlyPremium', 'Fumai', 'Funo', 'Fuyanghong', 'Hanzhongbai', 'Honggoudou', 'Hongheshangtou', 'Honghuamai', 'Hongjinmai', 'Honglaomai', 'Hongmai', 'Hongmangmai', 'Hongmangzi', 'Hongpidongmai', 'Hongxumai', 'Huangguaxian', 'Huangshuibai', 'Huanxiangguo', 'Huomai', 'Jiahongmai', 'Jiangdongmen', 'Jiangmai', 'Jinan17', 'Laizhou953', 'Lanhuamai', 'Laolaixia', 'Laomai', 'Laoqimai', 'Laotutou', 'Liuzhutou', 'Louguding', 'Lovrin10', 'Mazhamai', 'Motuoxiaomai', 'Niuzhijia', 'Nonglin10', 'Panshiwumang', 'Paozimai', 'Qianjiaomai', 'Sankecun', 'Sanyuehuang', 'Shanxibaimai', 'Shijiazhuang407', 'Shuilizhan', 'Suotiaohongmai', 'Tongjiabaxiaomai', 'Triumph', 'VillaGlori', 'Xianyangdasui', 'Xiaobaimang', 'Xiaofoshou', 'Xiaokouhong', 'Xiaoyan6', 'Xindong2', 'Xishanbiansui', 'Youbaomai', 'Youmangbaifu', 'Youmangsaogudan', 'Youzimai', 'Yuqiumai', 'Zaowutian', 'Zaoxiaomai', 'Zhengyin4', 'Zhugoumai', 'Zhuoludongmai', 'Zhushimai', 'Zijiehong', 'Zipi']
        ref_html = 'regulators of wheat grain production PRJNA348655'
    elif expressiontable == 'PRJNA358808_tbl':
        categories = ['Atay85_Control_Root', 'Atay85_Drought_Root', 'Atay85_Heat_Root', 'Atay85_DroughtHeat_Root', 'Atay85_Control_Leaf', 'Atay85_Drought_Leaf', 'Atay85_Heat_Leaf', 'Atay85_DroughtHeat_Leaf', 'Atay85_Control_Grain', 'Atay85_Drought_Grain', 'Atay85_Heat_Grain', 'Atay85_DroughtHeat_Grain', 'Zubkov_Control_Root', 'Zubkov_Drought_Root', 'Zubkov_Heat_Root', 'Zubkov_DroughtHeat_Root', 'Zubkov_Control_Leaf', 'Zubkov_Drought_Leaf', 'Zubkov_Heat_Leaf', 'Zubkov_DroughtHeat_Leaf', 'Zubkov_Control_Grain', 'Zubkov_Drought_Grain', 'Zubkov_Heat_Grain', 'Zubkov_DroughtHeat_Grain']
        ref_html = 'stress treatment leaf, root and grain PRJNA358808'
    elif expressiontable == 'PRJNA353130_tbl':
        categories = ['WT_1HAI', 'WT_6HAI', 'WT_12HAI', 'OE_1HAI', 'OE_6HAI', 'OE12_HAI']
        ref_html = 'miR9678 function in wheat PRJNA353130'
    elif expressiontable == 'PRJNA396738_tbl':
        categories = ['5A-_NIL_4dpa', '5A+_NIL_4dpa', '5A-_NIL_8dpa', '5A+NIL_8dpa']
        ref_html = 'grain weight QTL on 5AL PRJNA396738'
    elif expressiontable == 'PRJNA427246_tbl':
        categories = ['grain_heat_at_0m', 'grain_heat_at_5m', 'grain_heat_at_10m', 'grain_heat_at_30m', 'grain_heat_at_1h', 'grain_heat_at_4h', 'Leaf_heat_at_0m', 'Leaf_heat_at_5m', 'Leaf_heat_at_10m', 'Leaf_heat_at_30m', 'Leaf_heat_at_1h', 'Leaf_heat_at_4h']
        ref_html = 'heat stress-responsive transcriptomes PRJNA427246'
    elif expressiontable == 'PRJNA471426_tbl':
        categories = ['WT9DPA', 'M9DPA', 'WT15DPA', 'M15DPA', 'WT20DPA', 'M20DPA', 'WT25DPA', 'M25DPA']
        ref_html = 'increased grain size mutant PRJNA471426'
    elif expressiontable == 'PRJNA477934_tbl':
        categories = ['CB037_endosperm_15dpa', 'TAA10_endosperm_15dpa', 'XX329_endosperm_15dpa', 'CB037_TAA10_endosperm_15dpa', 'TAA10_CB037_endosperm_15dpa', 'CB037_XX329_endosperm_15dpa', 'XX329_CB037_endosperm_15dpa']
        ref_html = 'tetraploid and hexaploid cross endosperm PRJNA477934'
    elif expressiontable == 'PRJNA485741_tbl':
        categories = ['embryo14dpa', 'endosperm14dpa', 'embryo25dpa', 'endosperm25dpa']
        ref_html = 'embryo and endosperm in developing grain PRJNA485741'
    elif expressiontable == 'PRJNA362497_tbl':
        categories = ['wild type', 'mutant']
        ref_html = 'chlorophyll-deficient mutant PRJNA362497'
    elif expressiontable == 'DMSO_GA_JA_tpm_mean_tbl':
        categories = ['DMSO1h', 'GA1h', 'JA1h']
        ref_html = 'treated 1h with DMSO,GA and JA'
    elif expressiontable == 'ABA_JA_6BA_DMSO3h_mean_tbl':
        categories = ['DMSO3h', '6BA3h', 'ABA3h', 'SA3h']
        ref_html = 'treated 3h with DMSO,ABA, 6-BA and SA'
    elif expressiontable == 'PRJNA293629_tbl':
        categories = ['CS_CK_6h', 'CS_Na_6h', 'QM_CK_6h', 'QM_Na_6h', 'CS_CK_12h', 'CS_Na_12h', 'QM_CK_12h', 'QM_Na_12h', 'CS_CK_24h', 'CS_Na_24h', 'QM_CK_24h', 'QM_Na_24h', 'CS_CK_6h', 'CS_Na_48h', 'QM_CK_48h', 'QM_Na_48h']
        ref_html = 'two wheat cultivers to salt stress PRJNA293629'
    elif expressiontable == 'PRJNA487923_tbl':
        categories = ['Root CK', 'Root Salt']
        ref_html = 'The root transcriptome salt stress PRJNA487923'
    elif expressiontable == 'PRJNA171754_tbl':
        categories = ['HD2985_control', 'HD2985_stress', 'HD2329_control', 'HD2329_stress']
        ref_html = 'tolerant and susceptible heat stress PRJNA171754'
    elif expressiontable == 'PRJNA307228_tbl':
        categories = ['SKM0', 'AKM0', 'AKM24', 'AKM48', 'AKM120', 'AKI24', 'AKI48', 'AkI120']
        ref_html = 'stripe rust Pathogen Stress PRJNA307228'
    elif expressiontable == 'Wangmeng_NR_tbl':
        categories = ['CS_CT', 'CS_NS1h', 'NR1h', 'NR24h']
        ref_html = 'Nitrogen treatment Wangmeng'
    elif expressiontable == 'PRJNA1037698_tbl':
        categories = ['DR3_24', 'DR3_72h', 'DR3_CK', 'DR7_24h', 'DR3_72h', 'DR7_CK']
        ref_html = 'wild emmer response to stripe rust PRJNA1037698'
    elif expressiontable == 'PRJNA613349_tbl':
        categories = ['PBW343C12', 'PBW343C48', 'FLW29C12', 'FLW29C48', 'FLW29C72', 'FLW29T12', 'FLW29T48', 'FLW29T72', 'PBW343C72', 'PBW343T12', 'PBW343T48', 'PBW343T72']
        ref_html = 'response to stripe rust on wheat PRJNA613349'
    elif expressiontable == 'PRJEB51827_tbl':
        try:
            cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'PRJEB51827_tbl' AND COLUMN_NAME NOT IN ('GeneID', 'IWGSCV1_1_id')")
            categories = [c[0] for c in cursor.fetchall()]
            ref_html = '10+ cultivars population transcriptome PRJEB51827'
        except: categories = ["Error getting columns"]

    # 2. 数据检索
    for gene in name:
        try:
            cursor.execute("select * from " + expressiontable + " where GeneID='" + gene + "';")
            row = cursor.fetchall()
            if not row: continue
            
            row2 = row[0][1:]
            eb = []
            try:
                cursor.execute("select * from " + expressiontable + "_std where GeneID='" + gene + "';")
                row_std = cursor.fetchall()
                if row_std:
                    row2_std = row_std[0][1:]
                    for r1, r2 in zip(list(row2[1:]), list(row2_std[1:])):
                        eb.append([round(r1-r2,2), round(r1+r2,2)])
            except: pass
            
            data[row2[0]] = [list(row2[1:]), eb]
        except: continue

    # 3. 渲染图表
    print('<div class="card mb-5 shadow-sm">')
    print('<div class="card-header bg-dark text-white">Database: ' + expressiontable + '</div>')
    print('<div class="card-body">')
    
    if not data:
        print('<p class="text-danger">No genes found in this table.</p>')
    else:
        chart = Highchart(width=900, height=500)
        chart_id = "chart_" + str(idx)
        chart.set_options('chart', {'zoomType': 'xy', 'renderTo': chart_id})
        chart.set_options('xAxis', {'categories': categories})
        chart.set_options('yAxis', {'title': {'text': 'Expression(TPM)'}})
        
        for g_id, g_info in data.items():
            chart.add_data_set(g_info[0], series_type=series_type, name=g_id)
            if g_info[1]:
                chart.add_data_set(g_info[1], series_type='errorbar', name=g_id+' err')
        
        print('<div id="' + chart_id + '"></div>')
        print('<script>' + chart.script + '</script>')
        print('<p class="mt-2 small text-muted">' + ref_html + '</p>')
    
    print('</div></div>')

cursor.close()
mydb.close()
print('</div></body></html>')
