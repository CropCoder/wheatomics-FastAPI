-- 2026-11-23  scaffold 级组装的 BLAST 链接 + chromosome_count 语义修正
--
-- 1) 五个 scaffold 级组装在 genome_registry 里没有 blast_* 链接，BLAST 选择器
--    只能退回显示磁盘库名。补上链接后，选择器显示 registry 的 display_name：
--       Paragon  -> AABBDD_Paragon.scaffold   (+ scaffolds CDS/PEP)
--       Robigus  -> AABBDD_Robigus.scaffold   (+ scaffolds CDS/PEP)
--       Weebill  -> AABBDD_Weebill.scaffold   (+ scaffolds CDS/PEP)
--       Chili    -> AABB_Chili.scaffold
--       Mahmoudi -> AABB_Mahmoudi.scaffold
--    Chili / Mahmoudi 同时补 ploidy/species/assembly_level（此前全为 NULL）。
--
-- 2) chromosome_count 的语义是“染色体数”，不是 .fai 行数：
--       AABB_Wild_emmer_Zavitan  114 -> 14  (14 条染色体 + 100 unplaced)
--       Zavitan                  818 -> 14  (14 条染色体 + 804 unplaced)
--    两者都是染色体级参考组装，assembly_level 统一为 Chromosome。
--
-- 表名已全限定，可在任一库下执行：
--   mysql -u wheatomics_user -p wheatomics_db < scripts/sql/scaffold_blast_links_20261123.sql

UPDATE wheatomics_db.genome_registry SET
  blast_genome_db = 'AABBDD_Paragon.scaffold',
  blast_cds_db    = 'AABBDD_Paragon_scaffolds.add_Description.cds',
  blast_pep_db    = 'AABBDD_Paragon_scaffolds.add_Description.pep'
WHERE dataset_id = 'Paragon';

UPDATE wheatomics_db.genome_registry SET
  blast_genome_db = 'AABBDD_Robigus.scaffold',
  blast_cds_db    = 'AABBDD_Robigus_scaffolds.add_Description.cds',
  blast_pep_db    = 'AABBDD_Robigus_scaffolds.add_Description.pep'
WHERE dataset_id = 'Robigus';

UPDATE wheatomics_db.genome_registry SET
  blast_genome_db = 'AABBDD_Weebill.scaffold',
  blast_cds_db    = 'AABBDD_Weebill_scaffolds.add_Description.cds',
  blast_pep_db    = 'AABBDD_Weebill_scaffolds.add_Description.pep'
WHERE dataset_id = 'Weebill';

UPDATE wheatomics_db.genome_registry SET
  blast_genome_db = 'AABB_Chili.scaffold',
  ploidy          = 'AABB',
  species         = 'Triticum turgidum L.',
  assembly_level  = 'Scaffold'
WHERE dataset_id = 'Chili';

UPDATE wheatomics_db.genome_registry SET
  blast_genome_db = 'AABB_Mahmoudi.scaffold',
  ploidy          = 'AABB',
  species         = 'Triticum turgidum L.',
  assembly_level  = 'Scaffold'
WHERE dataset_id = 'Mahmoudi';

-- chromosome_count: 114/818 是 .fai 行数（含 unplaced），改成真实染色体数 14。
UPDATE wheatomics_db.genome_registry SET
  chromosome_count = 14,
  assembly_level   = 'Chromosome'
WHERE dataset_id = 'AABB_Wild_emmer_Zavitan';

UPDATE wheatomics_db.genome_registry SET
  chromosome_count = 14,
  assembly_level   = 'Chromosome'
WHERE dataset_id = 'Zavitan';

-- 同一口径：v2 的 15 行 .fai = 14 条染色体 + ChrUn。
UPDATE wheatomics_db.genome_registry SET
  chromosome_count = 14,
  assembly_level   = 'Chromosome'
WHERE dataset_id = 'Wild_emmerV2';
