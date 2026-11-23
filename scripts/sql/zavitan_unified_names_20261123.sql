-- 2026-11-23  Zavitan 四套组装：统一显示名 + DOI 错位修复
--
-- 目标：同一套基因组在 BLAST 选择器、JBrowse 网关卡片、genome_registry、
-- Genefunc_registry 里叫同一个名字。
--
--   display_name                    dataset_id               BLAST 库（不改）              DOI
--   Zavitan v1.0 (2017)             Wild_emmer               AABB_Wild_emmer.genome        10.1126/science.aan0032
--   Zavitan v2.0 (2019)             Wild_emmerV2             AABB_Wild_emmerV2.genome      10.1534/g3.118.200902
--   Zavitan near-complete (2026)    AABB_Wild_emmer_Zavitan  AABB_Wild_emmer_Zavitan.genome 10.1038/s41588-026-02808-3
--   Zavitan pangenome (2026)        Zavitan                  AABB_Zavitan.genome           10.1038/s41588-026-02678-9
--
-- 只改显示名 / 文献字段；BLAST 库名、JBrowse 目录名、基因表名一律不动。
-- 表名已全限定，可在任一库下执行，例如：
--   mysql -u wheatomics_user -p wheatomics_db < scripts/sql/zavitan_unified_names_20261123.sql
--
-- 修复的三处 DOI 错位（JBrowse 卡片上的 DOI 本来就是对的）：
--   Wild_emmer            原本写的是 v2 的 DOI (10.1534/g3.118.200902)
--   Wild_emmerV2          原本写的是 v1 的 DOI (10.1126/science.aan0032)，journal/year 为空
--   AABB_Wild_emmer_Zavitan 原本写的是 v1 的 DOI (10.1126/science.aan0032)
-- 另：三行的 paper_title 都被填成 v1 的论文，一并按 DOI 改正。

UPDATE wheatomics_db.genome_registry SET
  display_name   = 'Zavitan v1.0 (2017)',
  doi            = '10.1126/science.aan0032',
  journal        = 'Science',
  publication_year = 2017,
  paper_title    = 'Wild emmer genome architecture and diversity elucidate wheat evolution and domestication'
WHERE dataset_id = 'Wild_emmer';

UPDATE wheatomics_db.genome_registry SET
  display_name   = 'Zavitan v2.0 (2019)',
  doi            = '10.1534/g3.118.200902',
  journal        = 'G3 (Bethesda, Md.)',
  publication_year = 2019,
  paper_title    = 'Improved Genome Sequence of Wild Emmer Wheat Zavitan with the Aid of Optical Maps'
WHERE dataset_id = 'Wild_emmerV2';

UPDATE wheatomics_db.genome_registry SET
  display_name   = 'Zavitan near-complete (2026)',
  doi            = '10.1038/s41588-026-02808-3',
  journal        = 'Nature Genetics',
  publication_year = 2026,
  paper_title    = 'Near-complete assembly of wild emmer wheat unveils centromere reorganization during polyploid evolution'
WHERE dataset_id = 'AABB_Wild_emmer_Zavitan';

UPDATE wheatomics_db.genome_registry SET
  display_name = 'Zavitan pangenome (2026)'
WHERE dataset_id = 'Zavitan';

-- Genefunc registry：同样的显示名；“Wild Ember” 拼写改为 Emmer；
-- 两张本来就该有 DOI 的注释表补上 DOI（此前为空）。
UPDATE Genefuncdb.Genefunc_registry SET
  display_name = 'Zavitan v2.0 (2019)',
  Doi          = '10.1534/g3.118.200902'
WHERE table_name = 'Genefunc_AABB_Wild_emmerV2_table';

UPDATE Genefuncdb.Genefunc_registry SET
  display_name = 'Zavitan near-complete (2026)'
WHERE table_name = 'Genefunc_AABB_Wild_emmer_Zavitan_table';

UPDATE Genefuncdb.Genefunc_registry SET
  display_name = 'Zavitan pangenome (2026)',
  Doi          = '10.1038/s41588-026-02678-9'
WHERE table_name = 'Genefunc_AABB_Zavitan_table';

-- 重复注释表：Genefunc_Zavitan_table 与 Genefunc_AABB_Zavitan_table 是同一套
-- 97,882 个基因模型（只有染色体大小写不同），旧表却叫 “Zavitan v1.0”，改名后
-- 会与真正的 v1 组装混淆。按 scripts/dedupe_genefunc_registry.py 的既有规则
-- （同基因组同注释：保留带倍性前缀的现代表，隐藏 legacy 表，不删数据）处理。
UPDATE Genefuncdb.Genefunc_registry SET visible = 0
WHERE table_name = 'Genefunc_Zavitan_table';
