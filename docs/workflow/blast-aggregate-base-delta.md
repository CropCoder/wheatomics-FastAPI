# BLAST 聚合库 base + delta 维护

目标:保留 `all_genes` / `all_gene` / `all_proteins` / `all_protein` 这些对外名称,
把原来 196–200 个成员 alias 改成一个合并 base + 少量新增 delta,以后新基因组
可以继续增量加入,不需要每次全量重建。

## 为什么不是单一物理库直接 append

- BLAST+ 2.12 `makeblastdb` 没有 append/update;新增序列必须重建物理库。
- nucleotide 与 protein 不能合并为一个 BLAST DB。
- BLAST alias 最多稳定读取 200 个成员(见
  `scripts/rebuild_getfasta_aggregates.py` 的 `ALIAS_MEMBER_LIMIT`)。

## 目录与脚本

- `scripts/plan_blast_aggregate_merge.py`
  - 只读预检:成员数、坏库、序列/碱基统计、重复序列 ID。
  - 输出 `--report` JSON 和 `--dup-map` TSV。
- `scripts/build_blast_aggregate_base.py`
  - 从 alias 成员或指定成员流式抽取 FASTA,合并、去重 ID、`makeblastdb`。
  - 重复 ID:第一个成员保留原 ID,其他成员加 `__dup__` 前缀。
  - 默认 dry-run;`--apply` 只在 staging 写文件,不碰生产 alias。
- `scripts/update_blast_alias.py`
  - 原子改写 alias,自动备份并用 `blastdbcmd -info` 验证。
  - 模式:`switch`(切换到 base)、`append`(加新 delta)、`set`(显式成员表)。

## 标准流程

### 1. 预检

```bash
python3 scripts/plan_blast_aggregate_merge.py \
  --alias all_genes.nal \
  --report /var/www/html/getfasta/blastdb_migration_20261113/all_genes_audit.json \
  --dup-map /var/www/html/getfasta/blastdb_migration_20261113/all_genes_dups.tsv

python3 scripts/plan_blast_aggregate_merge.py \
  --alias all_proteins.pal \
  --report /var/www/html/getfasta/blastdb_migration_20261113/all_proteins_audit.json \
  --dup-map /var/www/html/getfasta/blastdb_migration_20261113/all_proteins_dups.tsv
```

### 2. 构建 base(staging)

```bash
STAGE=/var/www/html/getfasta/blastdb_migration_20261113

python3 scripts/build_blast_aggregate_base.py \
  --alias all_genes.nal --dup-map "$STAGE/all_genes_dups.tsv" \
  --out-base all_genes_base --staging-dir "$STAGE" --apply \
  --known-id TraesAK58CH1A01G000100.1

python3 scripts/build_blast_aggregate_base.py \
  --alias all_proteins.pal --dup-map "$STAGE/all_proteins_dups.tsv" \
  --out-base all_proteins_base --staging-dir "$STAGE" --apply \
  --known-id TraesAK58CH1A01G000100.1
```

验证:

- `blastdbcmd -db <base> -info` 的序列数;
- 已知 ID `blastdbcmd -db <base> -entry <id>`;
- `/api/sequence/by-gene?gene_db=all_genes&protein_db=all_proteins`;
- GetSequence 页面、BLAST 页面、PrimerServer2。

### 3. 切换 alias(生产)

```bash
# 先备份并验证;--apply 才会写
python3 scripts/update_blast_alias.py \
  --alias all_genes.nal --mode switch --base all_genes_base --apply

python3 scripts/update_blast_alias.py \
  --alias all_gene.nal --mode switch --base all_genes_base --apply

python3 scripts/update_blast_alias.py \
  --alias all_proteins.pal --mode switch --base all_proteins_base --apply

python3 scripts/update_blast_alias.py \
  --alias all_protein.pal --mode switch --base all_proteins_base --apply
```

alias 文件位于 BLASTDB 根目录;切换是原子 rename,不需要重启 API 或 BLAST daemon。

### 4. 新基因组增量追加

现有 `finish_genome_integration.sh` 仍会为新基因组生成独立的 per-genome DB。
在 base 切换后,把它作为 delta 追加:

```bash
python3 scripts/update_blast_alias.py \
  --alias all_genes.nal --mode append \
  --members AABBDD_NewGenome.add_Description.cds --apply

python3 scripts/update_blast_alias.py \
  --alias all_proteins.pal --mode append \
  --members AABBDD_NewGenome.add_Description.pep --apply
```

同时保持 `all_gene.nal` 与 `all_genes.nal`、`all_protein.pal` 与
`all_proteins.pal` 成员一致。

### 5. Compaction

当 delta 数量达到阈值(建议 50–100)时,把 base + delta 合并成新 base:

1. 把 base + delta 作为成员列表交给 `build_blast_aggregate_base.py`;
2. 重新跑 `plan_blast_aggregate_merge.py` 生成新的 dup map;
3. staging 构建新 base;
4. `update_blast_alias.py --mode switch` 原子切换;
5. 保留旧 base 和旧 alias 备份用于回滚。

## 重复 ID 策略

预检会输出:

```
id  first_member  duplicate_member
```

构建时:

- `first_member` 保留原始 ID,保证 GetSequence by-gene 的 canonical 查询;
- 其他成员的同 ID 记录改为 `<member>__dup__<original_id>`;
- `__dup__` 记录仍可被 BLAST 搜索命中,但不会与原 ID 冲突。

如果未来需要把所有重复副本都按原 ID 查询,需要另做 ID→sequence 的映射层,
不要在未确认前修改前缀规则。

## 回滚

`update_blast_alias.py` 每次写入都生成
`<alias>.bak-YYYYMMDD_HHMMSS`。直接复制备份覆盖 alias 即可回滚;物理 base
不会被删除。

## 注意

- `all_genomes` 当前 203 个成员,已超过 200;它包含 1.65 Tb 染色体序列,
  不适合直接合并成一个物理库。建议单独采用分组 compacted volumes 或先清理
  无效成员,不要与 all_genes/all_proteins 共用本次合并流程。
- 合并构建会占用 staging 空间,启动前确认 `df -h /var/www`。
- 不要在 API 请求高峰时切换 alias;切换本身很快,但 BLAST 任务可能正在使用旧成员。
