-- ============================================================
-- 1. 在 gene_expression 库中创建 project_meta 表
-- ============================================================

CREATE DATABASE IF NOT EXISTS gene_expression
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_general_ci;

USE gene_expression;

DROP TABLE IF EXISTS project_meta;

CREATE TABLE project_meta (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    table_name      VARCHAR(100) NOT NULL COMMENT '数据库中的表名，如 PRJEB25639_tbl',
    display_name    VARCHAR(300) NOT NULL COMMENT '展示名，如 BCS cv-1 Development',
    group_name      VARCHAR(50)  NOT NULL COMMENT '分组名：wheat population / wheat developmental tissues / wheat biotic stresses / wheat abiotic stresses / Others',
    labels          JSON         DEFAULT NULL COMMENT '实验条件列标签（JSON 数组），如 ["root_Z10","leaf_Z10","stem_Z30"]',
    citation        TEXT         DEFAULT NULL COMMENT '参考文献引用（HTML格式）',
    has_std_table   TINYINT(1)   DEFAULT 1 COMMENT '是否存在对应的 _std 标准差表，0=否 1=是',

    UNIQUE KEY uk_table_name (table_name),
    INDEX idx_group_name (group_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
  COMMENT='表达谱项目元数据表，替代代码中的硬编码 EXPRESSION_PROJECTS / PROJECT_CATEGORIES / EXPRESSION_GROUPS';

-- 总共 69 条记录

INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('ABA_JA_6BA_DMSO3h_mean_tbl', 'Fielder leaf treated 3h with DMSO, ABA, 6-BA and SA', 'Others', '["DMSO3h", "6BA3h", "ABA3h", "SA3h"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('CRA020462_tbl', 'RNA-seq of wheat accessions in water use efficiency omics analysis', 'wheat population', '[]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('DMSO_GA_JA_tpm_mean_tbl', 'Fielder leaf treated 1h with DMSO, GA and JA', 'Others', '["DMSO1h", "GA1h", "JA1h"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('ERP022006_tbl', 'Wild emmer expression', 'Others', '[]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('LAMC_tbl', 'The population transcriptome reveals the evolution of the seedling roots', 'wheat population', '[]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJCA004969_tbl', 'Population transcriptomic analysis of spike in 178 wheat', 'wheat population', '[]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJDB2496_tbl', 'Phosphate starvation', 'wheat abiotic stresses', '["root_0day", "root_10day_-P", "shoot_0day", "shoot_10day_-P"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJEB12358_tbl', 'FHB-resistance QTL Fhb1 and Qfhs.ifa-5A', 'wheat biotic stresses', '["NIL38_M3", "NIL38_F3", "NIL38_M6", "NIL38_F6", "NIL38_M12", "NIL38_F12", "NIL38_M24", "NIL38_F24", "NIL38_M36", "NIL38_F36", "NIL38_M48", "NIL38_F48", "NIL51_M3", "NIL51_F3", "NIL51_M6", "NIL51_F6", "NIL51_M12", "NIL51_F12", "NIL51_M24", "NIL51_F24", "NIL51_M36", "NIL51_F36", "NIL51_M48", "NIL51_F48"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJEB13569_tbl', 'Field Pathogenomics of Wheat Blast', 'wheat biotic stresses', '["LIB21745", "LIB21746", "LIB21747", "LIB21748", "LIB21749", "LIB21750", "LIB21751", "LIB21752"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJEB21835_tbl', 'Xanthomonas translucens infection', 'wheat biotic stresses', '["Control_Root", "Xt_Root", "Control_Leaf", "Xt_Leaf"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJEB21874_tbl', 'Mycorrhizal fungi interaction', 'wheat biotic stresses', '["MycorhizalFungiLeaf", "MycorhizalFungiXanthomonasLeaf", "MycorhizalFungiRoot", "MycorhizalFungiXanthomonasRoot"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJEB22854_tbl', 'Purple-grain wheat pericarp RNA-seq', 'Others', '["Grain_15dpa", "Grain_15dpa_dark", "Grain_20dpa", "Grain_20dpa_dark"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJEB23056_tbl', 'Elicitation with PAMPs', 'wheat biotic stresses', '["H2O", "H2O_30min", "H2O_180min", "Flag22_30min", "Flag22_180min", "Chitin_30min", "Chitin_180min"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJEB24686_tbl', 'Fusarium head blight 2DL', 'wheat biotic stresses', '["2618H2ORACH", "2618_FG_RACH", "2618_H2O_SP", "2618_FG_SP", "2890_H2O_SP", "2890_FG_SP", "2890_H2O_RACH", "2890_FG_RACH"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJEB25586_tbl', 'Early meiosis with or without Ph1', 'Others', '["CS_Ph1_minus", "CS_Ph1_plus"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJEB25639_tbl', 'BCS cv-1 Development', 'wheat developmental tissues', '["radicle at Seedling stage", "coleoptile at Seedling stage", "roots at Seedling stage", "stem axis at Seedling stage", "shoot apical meristem at Seedling stage", "first leaf sheath at Seedling stage", "first leaf blade at Seedling stage", "roots at three leaf stage", "axillary roots at three leaf stage", "root apical meristem at three leaf stage", "third leaf sheath at three leaf stage", "third leaf blade at three leaf stage", "fifth leaf sheath at fifth leaf stage", "fifth leaf blade at fifth leaf stage", "roots at Tillering stage", "root apical meristem at Tillering stage", "shoot apical meristem at Tillering stage", "shoot axis at Tillering stage", "first leaf sheath at Tillering stage", "first leaf blade at Tillering stage", "roots at Flag leaf stage", "shoot axis at Flag leaf stage", "fifth leaf sheath at Flag leaf stage", "fifth leaf blade at Flag leaf stage", "flag leaf blade night (-0.25h) 06:45 at Flag leaf stage", "flag leaf blade night (+0.25h) 07:15 at Flag leaf stage", "fifth leaf blade night (-0.25h) 21:45 at Flag leaf stage", "fifth leaf blade night (+0.25h) 22:15 at Flag leaf stage", "flag leaf blade at Flag leaf stage", "flag leaf sheath at Full boot", "flag leaf blade at Full boot", "leaf ligule at Full boot", "shoot axis at Full boot", "spike at Full boot", "fifth leaf blade at Ear emergence", "flag leaf sheath at Ear emergence", "flag leaf blade at Ear emergence", "Internode sec at Ear emergence", "glumes at Ear emergence", "lemma at Ear emergence", "peduncle at Ear emergence", "awns at Ear emergence", "roots at 30% spike", "Internode sec at 30% spike", "flag leaf sheath at 30% spike", "flag leaf blade at 30% spike", "peduncle at 30% spike", "spike at 30% spike", "spikelets at 30% spike", "flag leaf blade night (-0.25h) 06:45 at anthesis", "fifth leaf blade night (-0.25h) 21:45 at anthesis", "stigma & ovary at anthesis", "anther at anthesis", "fifth leaf blade (senescence) at milk grain stage", "flag leaf sheath at milk grain stage", "flag leaf blade at milk grain stage", "Internode sec at milk grain stage", "shoot axis at milk grain stage", "glumes at milk grain stage", "peduncle at milk grain stage", "lemma at milk grain stage", "awns at milk grain stage", "grain at milk grain stage", "flag leaf blade (senescence) at Dough", "embryo proper at Dough", "endosperm at Dough", "grain at Soft dough", "grain at Hard dough", "flag leaf blade (senescence) at Ripening", "grain at Ripening"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJEB5029_tbl', 'Meiosis data', 'wheat developmental tissues', '["latent_lepto", "diplo_dia", "zygo_pachy", "metaphaseI"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJEB5135_tbl', 'Developing wheat grain', 'wheat developmental tissues', '["Room1_10DPA", "Room1_AL_20DPA", "Room1_AL_20DPA_Extra", "Room1_TC_20DPA", "Room1_SE_20DPA", "Room1_REF_20DPA", "Room1_AL.SE_30DPA", "Room1_SE_30DPA", "Room2_10DPA", "Room2_AL_20DPA", "Room2_TC_20DPA", "Room2_SE_20DPA", "Room2_REF_20DPA", "Room2_AL.SE_30DPA", "Room2_SE_30DPA"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJEB51827_tbl', 'Population transcriptome', 'wheat population', '[]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJEB5314_paired_tbl', 'Chinese Spring cv-1 Development (pair)', 'wheat developmental tissues', '["root_Z10", "root_Z13", "root_Z39", "stem_Z30", "stem_Z32", "stem_Z65", "leaf_Z10", "leaf_Z23", "leaf_Z71", "spike_Z32", "spike_Z39", "spike_Z65", "grain_Z71", "grain_Z75", "grain_Z85"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJEB5314_single_tbl', 'Chinese Spring cv-1 Development (single)', 'wheat developmental tissues', '["root", "stem", "leaf", "spike", "grain"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJEB7795_tbl', 'Tissue layers from developing wheat grain at 12 DPA', 'wheat developmental tissues', '["endosperm_12DPA", "inner_pericarp_12DPA", "outer_pericarp_12DPA"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJEB8762_tbl', 'Temperature treatment', 'wheat abiotic stresses', '["12℃", "24℃"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJEB8798_tbl', 'Zymoseptoria tritici time course', 'wheat biotic stresses', '["Mock_1dpi", "Mock_4dpi", "Mock_9dpi", "Mock_14dpi", "Mock_21dpi", "Inoculation_1dpi", "Inoculation_4dpi", "Inoculation_9dpi", "Inoculation_14dpi", "Inoculation_21dpi"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA1037698_tbl', 'Wild emmer stripe rust response', 'wheat biotic stresses', '["DR3_24", "DR3_72h", "DR3_CK", "DR7_24h", "DR3_72h", "DR7_CK"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA171754_tbl', 'Heat stress tolerant vs susceptible cultivar', 'wheat abiotic stresses', '["HD2985_control", "HD2985_stress", "HD2329_control", "HD2329_stress"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA243835_powdery_tbl', 'Powdery mildew pathogen stress', 'wheat biotic stresses', '["non-innoculation", "Powdery24h", "Powdery48h", "Powdery72h"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA243835_stripe_tbl', 'Stripe rust pathogen stress', 'wheat biotic stresses', '["non-innoculation", "Stripe24h", "Stripe48h", "Stripe72h"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA253535_tbl', 'Low temperature response', 'wheat abiotic stresses', '["wheat23℃", "wheat4℃"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA257938_tbl', 'Drought and heat stress', 'wheat abiotic stresses', '["control", "drought_1h", "drought_6h", "heat_1h", "heat_6h", "drough&theat_1h", "drought&heat_6h"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA263755_tbl', 'Fusarium crown rot', 'wheat biotic stresses', '[]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA273659_tbl', 'Fhb1 plus/minus DON and infection', 'wheat biotic stresses', '["Fhb1-Water_12hai", "Fhb1+Water12hai", "Fhb1-DON12hai", "Fhb1+DON12hai", "Fhb1-F.graminearum96haiRep1", "Fhb1-F.graminearumrep2", "Fhb1+F.graminearum96haiRep1", "Fhb1+F.graminearum96haiRep2"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA293629_tbl', 'Salt stress transcriptome', 'wheat abiotic stresses', '["CS_CK_6h", "CS_Na_6h", "QM_CK_6h", "QM_Na_6h", "CS_CK_12h", "CS_Na_12h", "QM_CK_12h", "QM_Na_12h", "CS_CK_24h", "CS_Na_24h", "QM_CK_24h", "QM_Na_24h", "CS_CK_6h", "CS_Na_48h", "QM_CK_48h", "QM_Na_48h"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA297822_tbl', 'Fusarium pseudograminearum infected wheat', 'wheat biotic stresses', '["Chara_Mock", "Chara_Fp"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA297977_tbl', 'Microspore embryogenesis induction', 'wheat developmental tissues', '["microspore embryogenesis S1", "microspore embryogenesis S2", "microspore embryogenesis S3"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA306536_tbl', 'PEG6000 treatment', 'wheat abiotic stresses', '["PEG6000_0h_Giza168", "PEG600_02h_Giza168", "PEG6000_12h_Giza168", "PEG6000_0h_Gemmiza10", "PEG6000_2h_Gemmiza10", "PEG6000_12h_Gemmiza10"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA307228_tbl', 'Stripe rust stress in Xingzi 9104', 'wheat biotic stresses', '["SKM0", "AKM0", "AKM24", "AKM48", "AKM120", "AKI24", "AKI48", "AkI120"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA307237_tbl', 'Flag leaf senescence', 'Others', '["DBF-L1", "DAF-L2", "DAF-L3", "DAF-L4", "DAF-L5"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA307989_tbl', 'F. graminearum infection on Fielder', 'wheat biotic stresses', '["FHB", "GA", "ABA"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA322418_tbl', 'Gene imprinting analysis', 'Others', '["doumai_15_20_25", "doumai X keyi 15DPA", "doumai X keyi 20DPA", "doumai X keyi 25DPA", "keyi_15_20_25", "keyi X doumai 15DPA", "keyi X doumai 20DPA", "keyi X doumai 25DPA"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA325136_tbl', 'Stem rust resistance locus on 7AL', 'wheat biotic stresses', '["Columbus_0dpi", "ColumbusNS765_0dpi", "ColumbusNS766_0dpi", "Columbus_2dpi", "ColumbusNS765_2dpi", "ColumbusNS766_2dpi", "Columbus_5dpi", "ColumbusNS765_5dpi", "ColumbusNS766_5dpi"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA325489_tbl', 'Early wheat spike development', 'wheat developmental tissues', '["KNI", "KNII", "KNIII", "KNIV", "KNV", "KNVI"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA327013_tbl', 'Zymoseptoria tritici isolates', 'wheat biotic stresses', '[]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA327829_tbl', 'Pyrenophora tritici-repentis inoculation', 'wheat biotic stresses', '["Glenlea_Control_Zero", "Glenlea_Control_48pi", "Glenlea_Toxin_48pi", "Glenlea_Fungus_48pi", "Salamouni_Control_Zero", "Salamouni_Control_48pi", "Salamouni_Toxin_48pi", "Salamouni_Fungus_48pi"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA328385_tbl', 'Lr57 NIL interactions', 'wheat biotic stresses', '["TaWL711_0hpi", "TaWL711_12hpi", "TaWL711_24hpi", "TaWL711_48hpi", "TaWL711_72hpi", "TaWL711Lr57_0hpi", "TaWL711Lr57_12hpi", "TaWL711Lr57_24hpi", "TaWL711Lr57_48hpi", "TaWL711Lr57_72hpi"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA341486_tbl', 'Wax production regulators', 'Others', '["7279_non-glaucous", "7282_non-glaucous", "7284_non-glaucous", "7285_non-glaucous", "7287_non-glaucous", "7289_glaucous", "7290_glaucous", "7293_glaucous", "7294_glaucous"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA348655_tbl', 'Regulators of wheat grain production', 'wheat population', '[]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA353130_tbl', 'miR9678 function in wheat', 'Others', '["WT_1HAI", "WT_6HAI", "WT_12HAI", "OE_1HAI", "OE_6HAI", "OE12_HAI"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA358808_tbl', 'Combined drought and heat stress', 'wheat abiotic stresses', '["Atay85_Control_Root", "Atay85_Drought_Root", "Atay85_Heat_Root", "Atay85_DroughtHeat_Root", "Atay85_Control_Leaf", "Atay85_Drought_Leaf", "Atay85_Heat_Leaf", "Atay85_DroughtHeat_Leaf", "Atay85_Control_Grain", "Atay85_Drought_Grain", "Atay85_Heat_Grain", "Atay85_DroughtHeat_Grain", "Zubkov_Control_Root", "Zubkov_Drought_Root", "Zubkov_Heat_Root", "Zubkov_DroughtHeat_Root", "Zubkov_Control_Leaf", "Zubkov_Drought_Leaf", "Zubkov_Heat_Leaf", "Zubkov_DroughtHeat_Leaf", "Zubkov_Control_Grain", "Zubkov_Drought_Grain", "Zubkov_Heat_Grain", "Zubkov_DroughtHeat_Grain"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA362497_tbl', 'Chlorophyll-deficient mutant', 'Others', '["wild type", "mutant"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA396738_tbl', 'Major grain weight QTL on 5AL', 'Others', '["5A-_NIL_4dpa", "5A+_NIL_4dpa", "5A-_NIL_8dpa", "5A+NIL_8dpa"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA427246_tbl', 'Heat stress responsive transcriptomes', 'wheat abiotic stresses', '["grain_heat_at_0m", "grain_heat_at_5m", "grain_heat_at_10m", "grain_heat_at_30m", "grain_heat_at_1h", "grain_heat_at_4h", "Leaf_heat_at_0m", "Leaf_heat_at_5m", "Leaf_heat_at_10m", "Leaf_heat_at_30m", "Leaf_heat_at_1h", "Leaf_heat_at_4h"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA471426_tbl', 'Increased grain size mutant', 'Others', '["WT9DPA", "M9DPA", "WT15DPA", "M15DPA", "WT20DPA", "M20DPA", "WT25DPA", "M25DPA"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA477934_tbl', 'Tetraploid, hexaploid and reciprocal endosperm', 'Others', '["CB037_endosperm_15dpa", "TAA10_endosperm_15dpa", "XX329_endosperm_15dpa", "CB037_TAA10_endosperm_15dpa", "TAA10_CB037_endosperm_15dpa", "CB037_XX329_endosperm_15dpa", "XX329_CB037_endosperm_15dpa"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA485741_tbl', 'Expression of embryo and endosperm in developing grain', 'wheat developmental tissues', '["embryo14dpa", "endosperm14dpa", "embryo25dpa", "endosperm25dpa"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA487923_tbl', 'Salt stress root transcriptome', 'wheat abiotic stresses', '["Root CK", "Root Salt"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA509214_tbl', 'Population transcriptomic analysis in 100 FHB resistant wheat', 'wheat population', '[]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA613349_tbl', 'Stripe rust response on wheat', 'wheat biotic stresses', '["PBW343C12", "PBW343C48", "FLW29C12", "FLW29C48", "FLW29C72", "FLW29T12", "FLW29T48", "FLW29T72", "PBW343C72", "PBW343T12", "PBW343T48", "PBW343T72"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('PRJNA863398_tbl', 'Population transcriptomic analysis of roots and leaves in 58 spring wheat cultivars', 'wheat population', '[]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('SRP072147_tbl', 'Triticum urartu expression', 'Others', '[]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('SRP104243_tbl', 'Triticum urartu stress expression', 'Others', '[]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('Wangmeng_NR_tbl', 'Nitrogen treatment', 'wheat abiotic stresses', '["CS_CT", "CS_NS1h", "NR1h", "NR24h"]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('barley_development_PRJEB14349_tbl', 'Barley development', 'Others', '[]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('kat2_tpm_mean_tbl', 'Wild emmer KAT2', 'Others', '[]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('miRNA_mature_tissue_tbl', 'miRNA mature tissue expression', 'Others', '[]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('rye_cold_tbl', 'Rye cold stress', 'Others', '[]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('rye_development_tbl', 'Rye development', 'Others', '[]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('rye_drought_tbl', 'Rye drought stress', 'Others', '[]', 1);
INSERT INTO project_meta (table_name, display_name, group_name, labels, has_std_table) VALUES
('tpm327_tbl', 'Diversity to the modern wheat improvement in 328 wheat', 'wheat population', '[]', 1);


-- ============================================================
-- 3. 填入参考文献引用信息
-- ============================================================

UPDATE project_meta SET citation = 'Chen Y, Yan Y, Wu TT, et al. Cloning of wheat keto-acyl thiolase 2B reveals a role of jasmonic acid in grain weight determination. <a href=\'https://doi.org/10.1038/s41467-020-20133-z\'>Nat Commun 2020, doi: 10.1038/s41467-020-20133-z</a>' WHERE table_name = 'ABA_JA_6BA_DMSO3h_mean_tbl';
UPDATE project_meta SET citation = 'Chen Y, Yan Y, Wu TT, et al. Cloning of wheat keto-acyl thiolase 2B reveals a role of jasmonic acid in grain weight determination. <a href=\'https://doi.org/10.1038/s41467-020-20133-z\'>Nat Commun 2020, doi: 10.1038/s41467-020-20133-z</a>' WHERE table_name = 'DMSO_GA_JA_tpm_mean_tbl';
UPDATE project_meta SET citation = 'Wild emmer expression. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/ERP022006\'>ERP022006</a>' WHERE table_name = 'ERP022006_tbl';
UPDATE project_meta SET citation = 'Phosphate (Pi) starvation condition (CS). <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJDB2496\'>PRJDB2496</a>' WHERE table_name = 'PRJDB2496_tbl';
UPDATE project_meta SET citation = 'FHB-resistance QTL Fhb1 and Qfhs.ifa-5A. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJEB12358\'>PRJEB12358</a>' WHERE table_name = 'PRJEB12358_tbl';
UPDATE project_meta SET citation = 'Field Pathogenomics of Wheat Blast. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJEB13569\'>PRJEB13569</a>' WHERE table_name = 'PRJEB13569_tbl';
UPDATE project_meta SET citation = 'Xanthomonas translucens infection. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJEB21835\'>PRJEB21835</a>' WHERE table_name = 'PRJEB21835_tbl';
UPDATE project_meta SET citation = 'Mycorhizal fungi with and without Xanthomonas translucens infection. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJEB21874\'>PRJEB21874</a>' WHERE table_name = 'PRJEB21874_tbl';
UPDATE project_meta SET citation = 'RNA-seq of pericarp of purple-grain wheat. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJEB22854\'>PRJEB22854</a>' WHERE table_name = 'PRJEB22854_tbl';
UPDATE project_meta SET citation = 'Elicitation with PAMPs. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJEB23056\'>PRJEB23056</a>' WHERE table_name = 'PRJEB23056_tbl';
UPDATE project_meta SET citation = 'Fusarium head blight (FHB) 2DL. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJEB24686\'>PRJEB24686</a>' WHERE table_name = 'PRJEB24686_tbl';
UPDATE project_meta SET citation = 'Early meiosis in wheat in the presence and absence of the Ph1 locus. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJEB25586\'>PRJEB25586</a>' WHERE table_name = 'PRJEB25586_tbl';
UPDATE project_meta SET citation = 'Shifting the limits in wheat research and breeding using a fully annotated reference genome. International Wheat Genome Sequencing Consortium. <a href=\'https://www.ncbi.nlm.nih.gov/pubmed/30115783\'>Science 2018, doi: 10.1126/science.aar7191</a>' WHERE table_name = 'PRJEB25639_tbl';
UPDATE project_meta SET citation = 'Meiosis data (CS). <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJEB5029\'>PRJEB5029</a>' WHERE table_name = 'PRJEB5029_tbl';
UPDATE project_meta SET citation = 'Transcriptome analysis of developing wheat grain. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJEB5135\'>PRJEB5135</a>' WHERE table_name = 'PRJEB5135_tbl';
UPDATE project_meta SET citation = '10+ cultivars population transcriptome. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJEB51827\'>PRJEB51827</a>' WHERE table_name = 'PRJEB51827_tbl';
UPDATE project_meta SET citation = 'A chromosome-based draft sequence of the hexaploid bread wheat (Triticum aestivum) genome. International Wheat Genome Sequencing Consortium (IWGSC). <a href=\'https://www.ncbi.nlm.nih.gov/pubmed/25035500\'>Science 2014, doi: 10.1126/science.1251788</a>' WHERE table_name = 'PRJEB5314_paired_tbl';
UPDATE project_meta SET citation = 'A chromosome-based draft sequence of the hexaploid bread wheat (Triticum aestivum) genome. International Wheat Genome Sequencing Consortium (IWGSC). <a href=\'https://www.ncbi.nlm.nih.gov/pubmed/25035500\'>Science 2014, doi: 10.1126/science.1251788</a>' WHERE table_name = 'PRJEB5314_single_tbl';
UPDATE project_meta SET citation = 'Tissue layers from developing wheat grain at 12 days post-anthesis. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJEB7795\'>PRJEB7795</a>' WHERE table_name = 'PRJEB7795_tbl';
UPDATE project_meta SET citation = 'Gene expression data for the 12°C and 27°C sample. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJEB8762\'>PRJEB8762</a>' WHERE table_name = 'PRJEB8762_tbl';
UPDATE project_meta SET citation = 'Time course of Z.tritici post inoculation on wheat leafs. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJEB8798\'>PRJEB8798</a>' WHERE table_name = 'PRJEB8798_tbl';
UPDATE project_meta SET citation = 'Wild emmer wheat response to stripe rust fungus. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1037698\'>PRJNA1037698</a>' WHERE table_name = 'PRJNA1037698_tbl';
UPDATE project_meta SET citation = 'Tolerant and susceptible wheat cultivar under heat stress. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA171754\'>PRJNA171754</a>' WHERE table_name = 'PRJNA171754_tbl';
UPDATE project_meta SET citation = 'Powdery Mildew Pathogen Stress. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA243835\'>PRJNA243835</a>' WHERE table_name = 'PRJNA243835_powdery_tbl';
UPDATE project_meta SET citation = 'Stripe rust Pathogen Stress. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA243835\'>PRJNA243835</a>' WHERE table_name = 'PRJNA243835_stripe_tbl';
UPDATE project_meta SET citation = 'Wheat tissues grown at 23°C and 4°C. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA253535\'>PRJNA253535</a>' WHERE table_name = 'PRJNA253535_tbl';
UPDATE project_meta SET citation = 'Drought and heat stress. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA257938\'>PRJNA257938</a>' WHERE table_name = 'PRJNA257938_tbl';
UPDATE project_meta SET citation = 'Fusarium crown rot (Qcrs-3B). <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA263755\'>PRJNA263755</a>' WHERE table_name = 'PRJNA263755_tbl';
UPDATE project_meta SET citation = 'Fhb1+ Fhb1- transcriptome. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA273659\'>PRJNA273659</a>' WHERE table_name = 'PRJNA273659_tbl';
UPDATE project_meta SET citation = 'Zhang Y, Liu Z, Khan AA, et al. Expression partitioning of homeologs and tandem duplications contribute to salt tolerance in wheat. <a href=\'https://www.ncbi.nlm.nih.gov/pubmed/26892368\'>PMID: 26892368</a>' WHERE table_name = 'PRJNA293629_tbl';
UPDATE project_meta SET citation = 'RNA-seq on Fusarium pseudograminearum infected wheat. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA297822\'>PRJNA297822</a>' WHERE table_name = 'PRJNA297822_tbl';
UPDATE project_meta SET citation = 'Three stages from wheat microspore embryogenesis induction. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA297977\'>PRJNA297977</a>' WHERE table_name = 'PRJNA297977_tbl';
UPDATE project_meta SET citation = 'PEG(6000) treatment. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA306536\'>PRJNA306536</a>' WHERE table_name = 'PRJNA306536_tbl';
UPDATE project_meta SET citation = 'Stripe rust stress in Xingzi 9104. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA307228\'>PRJNA307228</a>' WHERE table_name = 'PRJNA307228_tbl';
UPDATE project_meta SET citation = 'Transcriptome analysis of flag leaf senescence in wheat. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA307237\'>PRJNA307237</a>' WHERE table_name = 'PRJNA307237_tbl';
UPDATE project_meta SET citation = 'Effects of F. graminearum infection on FHB susceptible wheat cultivar Fielder. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA307989\'>PRJNA307989</a>' WHERE table_name = 'PRJNA307989_tbl';
UPDATE project_meta SET citation = 'Gene imprinting analysis. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA322418\'>PRJNA322418</a>' WHERE table_name = 'PRJNA322418_tbl';
UPDATE project_meta SET citation = 'Transcriptome analysis of a stem rust resistance locus on wheat chromosome 7AL. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA325136\'>PRJNA325136</a>' WHERE table_name = 'PRJNA325136_tbl';
UPDATE project_meta SET citation = 'Early Wheat Spike Development. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA325489\'>PRJNA325489</a>' WHERE table_name = 'PRJNA325489_tbl';
UPDATE project_meta SET citation = 'Comparative transcriptomics of Zymoseptoria tritici isolates. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA327013\'>PRJNA327013</a>' WHERE table_name = 'PRJNA327013_tbl';
UPDATE project_meta SET citation = 'Pyrenophora tritici-repentis inoculation. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA327829\'>PRJNA327829</a>' WHERE table_name = 'PRJNA327829_tbl';
UPDATE project_meta SET citation = 'NIL Carrying Lr57 Under Compatible and Incompatible interactions. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA328385\'>PRJNA328385</a>' WHERE table_name = 'PRJNA328385_tbl';
UPDATE project_meta SET citation = 'Identification of key genes for wax production. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA341486\'>PRJNA341486</a>' WHERE table_name = 'PRJNA341486_tbl';
UPDATE project_meta SET citation = 'Transcriptome association identifies regulators of wheat grain production. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA348655\'>PRJNA348655</a>' WHERE table_name = 'PRJNA348655_tbl';
UPDATE project_meta SET citation = 'Global studies of miR9678 function in wheat. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA353130\'>PRJNA353130</a>' WHERE table_name = 'PRJNA353130_tbl';
UPDATE project_meta SET citation = 'Stress treatment (drought, heat, and drought+heat) leaf, root and grain tissues. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA358808\'>PRJNA358808</a>' WHERE table_name = 'PRJNA358808_tbl';
UPDATE project_meta SET citation = 'Leaf transcriptome between wild type and a chlorophyll-deficient mutant. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA362497\'>PRJNA362497</a>' WHERE table_name = 'PRJNA362497_tbl';
UPDATE project_meta SET citation = 'Two NILs segregating for a major grain weight QTL on 5AL. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA396738\'>PRJNA396738</a>' WHERE table_name = 'PRJNA396738_tbl';
UPDATE project_meta SET citation = 'Unveiling multidimensional regulations of heat stress-responsive transcriptomes in wheat. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA427246\'>PRJNA427246</a>' WHERE table_name = 'PRJNA427246_tbl';
UPDATE project_meta SET citation = 'A mutant wheat line with increased grain size. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA471426\'>PRJNA471426</a>' WHERE table_name = 'PRJNA471426_tbl';
UPDATE project_meta SET citation = 'RNA seq data from tetraploid and hexaploid wheat endosperm. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA477934\'>PRJNA477934</a>' WHERE table_name = 'PRJNA477934_tbl';
UPDATE project_meta SET citation = 'Expression of embryo and endosperm in developing grain. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA485741\'>PRJNA485741</a>' WHERE table_name = 'PRJNA485741_tbl';
UPDATE project_meta SET citation = 'The root transcriptome profiling of the salt stress response. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA487923\'>PRJNA487923</a>' WHERE table_name = 'PRJNA487923_tbl';
UPDATE project_meta SET citation = 'Transcriptome analysis reveals key expressed genes in response to stripe rust on wheat. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJNA613349\'>PRJNA613349</a>' WHERE table_name = 'PRJNA613349_tbl';
UPDATE project_meta SET citation = 'Triticum urartu expression. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/SRP072147\'>SRP072147</a>' WHERE table_name = 'SRP072147_tbl';
UPDATE project_meta SET citation = 'Triticum urartu stress expression. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/SRP104243\'>SRP104243</a>' WHERE table_name = 'SRP104243_tbl';
UPDATE project_meta SET citation = 'Nitrogen treatment.' WHERE table_name = 'Wangmeng_NR_tbl';
UPDATE project_meta SET citation = 'Barley development transcriptome. <a href=\'https://www.ncbi.nlm.nih.gov/bioproject/PRJEB14349\'>PRJEB14349</a>' WHERE table_name = 'barley_development_PRJEB14349_tbl';
UPDATE project_meta SET citation = 'Wild emmer KAT2 expression.' WHERE table_name = 'kat2_tpm_mean_tbl';
UPDATE project_meta SET citation = 'miRNA mature tissue expression in wheat.' WHERE table_name = 'miRNA_mature_tissue_tbl';
UPDATE project_meta SET citation = 'Rye cold stress transcriptome.' WHERE table_name = 'rye_cold_tbl';
UPDATE project_meta SET citation = 'Rye development transcriptome.' WHERE table_name = 'rye_development_tbl';
UPDATE project_meta SET citation = 'Rye drought stress transcriptome.' WHERE table_name = 'rye_drought_tbl';
