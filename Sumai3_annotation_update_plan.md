# Sumai3 注释上线规划（GFF3 / CDS / PEP → WheatOmics）

> 日期：2026-10-29
> 状态：**待确认**（本文只做规划，未改动生产环境）
> 上游依据：`~/.agents/skills/lab-server/references/wheatomics-new-genome-sop.md`、`genome-only-then-annotation-update.md`；生产脚本 `/var/www/data/masw_data/_prep/annotation_update.sh`
> 关联文档：`Sumai3_genome_update_plan.md`（序列层上线计划，Phase 1/2 尚未执行的部分并入本文）

---

## 0. 结论先行

Sumai3 的 **EGAPx 注释已经完成并通过 BUSCO 99.0%**，但网站目前仍是“只有序列、无注释”的状态。接下来按站点标准流程做两件事：

1. **补齐 Phase 1 缺口**：建立标准数据目录、FASTA 指纹、JBrowse refseq 大小写归一化（`chr1A_Sumai3` → `Chr1A_Sumai3`）、补 `all_genomes_type.txt`；
2. **注释增量上线**：把 EGAPx GFF3/CDS/PEP 归一化为站点格式，跑 `annotation_update.sh`（gffread → QC → EggNOG → MySQL 基因功能表 → 中国春 02G → CDS/PEP BLAST → JBrowse all_gene → registry/聚合库/前端），最后更新 `genome_registry` 元数据与验收。

预计**有效操作 5–8 小时**（其中 `annotation_update.sh` 全量约 2.5–4 小时，生产服务器 128 核/503 GB，磁盘剩 30 T）。

需要你确认的 5 个决策见 §2，确认后即可开工。

---

## 1. 现状核对（2026-10-29）

### 1.1 Ma 上的注释产物（已就绪）

| 文件 | 大小 | md5 | 说明 |
|---|---|---|---|
| `/data/masw_data/Sumai3/annotation/Sumai3_EGAPx.gff3` | 630 MB | `9a7735a6…` | NCBI annotwriter GFF3，21 条 seqid（CM123981.1 …） |
| `Sumai3_EGAPx.cds.fna` | 231 MB | `c126d919…` | 151,286 条 CDS |
| `Sumai3_EGAPx.proteins.faa` | 74 MB | `5f22b12c…` | 151,286 条蛋白 |
| `feature_counts.txt` / BUSCO summary | 小 | — | BUSCO: C:99.0% [S:5.1%, D:93.9%], F:0.0%, M:1.0% |

GFF 特征统计：

- `gene` 128,475；`pseudogene` 36,923（合计 165,398 个“基因位点”）
- `mRNA` 188,859 = **蛋白编码 mRNA 151,286**（ID 带 `-R` 后缀、有 CDS）+ **假基因 mRNA 37,573**（`pseudo=true`、无 CDS）
- `lncRNA` 28,730；`transcript` 10,074；`CDS` 765,019；`exon` 1,182,142
- 蛋白编码基因 116,420（与 `mRNA` 151,286 的差异是可变剪接）

### 1.2 生产站现状（2026-10-29 核对）

| 模块 | 现状 | 缺口 |
|---|---|---|
| 数据目录/指纹 | `/var/www/data/masw_data/AABBDD_Sumai3/` **不存在** | 需建目录、`Sumai3.fa`、`.fai`、`genome_fingerprint.txt`、provenance、seqid mapping |
| 核酸 BLAST | `AABBDD_Sumai3.genome`：21 seqs / 14,408,607,908 bp；21 个染色体拆分库 | ✅ 不动 |
| getfasta 源 FASTA | `/var/www/html/getfasta/blastdb/AABBDD_Sumai3.genome`（14.59 GB，头 `>Chr1A_Sumai3 …`） | ✅ 可直接作为标准 FASTA |
| JBrowse | 数据集 `Sumai3`，21 refseq，但名字是 **小写 `chr1A_Sumai3`**；只有 DNA track | 需重建 refseq 为 `Chr1A_Sumai3`，才能挂 all_gene 轨道 |
| CDS/PEP BLAST | 无 `AABBDD_Sumai3.add_Description.cds/.pep` | 注释流程产出 |
| JBrowse 基因轨道 | 无 `all_gene` | 注释流程产出 |
| MySQL 基因功能表 | 无 `Genefunc_AABBDD_Sumai3_table`；`Genefunc_registry` 无行 | 注释流程产出 |
| `all_genomes_type.txt` | **无 Sumai3 行**（`all_genomes.nal` 里已有 `AABBDD_Sumai3.genome`） | 补一行 `AABBDD_Sumai3.genome<TAB>AABBDD` |
| PrimerServer2 | `AABBDD_Sumai3.genome` 已收录，`.fai` 存在 | 注释流程会再加 `add_Description.cds` 及 `.fai` |
| genome_registry | `id=219`，`annotation_status=none`，`gene_count=null`，`gene_table=null` | 上线后更新 |
| 磁盘 | `/var/www` 81T/116T 已用，**剩 30T** | 足够（注释层约 +5–10 GB） |

### 1.3 seqid 映射（已验证 21/21）

`CM123981.1 … CM124001.1` 与站点 `Chr1A_Sumai3 … Chr7D_Sumai3` **按顺序逐条长度完全一致**：

```
CM123981.1 -> Chr1A_Sumai3 (603,896,264 bp)
...
CM124001.1 -> Chr7D_Sumai3 (653,597,169 bp)
```

Ma 上已生成 `annotation/seqid_mapping_CM_to_Chr_Sumai3.tsv`（21 行，全部长度校验通过）。

---

## 2. 需要你确认的决策（开工前）

| # | 决策 | 建议 | 备选 |
|---|---|---|---|
| D1 | **基因/转录本 ID 方案（已确认，中国春 02G 风格）** | **最终采用**：基因 `TraesSM3_<chr>01G<6 位数字>`（例 `TraesSM3_1A01G000100`；按染色体坐标排序、从 `000100` 起步长 100；假基因加 `LC`），转录本 `<geneID>.<n>`；旧 `SUM3_…` **不保留**（仅内部 QA mapping）。详见 **`Sumai3_gene_id_scheme.md`** | 如 `01G` 是 `02G` 笔误，需立即改为 `02G`；改后全量 ID 重生成 |
| D2 | **假基因 mRNA 是否进功能表/BLAST** | 把 37,573 条 `pseudo=true` 的 mRNA 类型改为 `pseudogenic_transcript`：GFF/JBrowse 保留结构，但 **Genefunc/BLAST/All genes 只含 151,286 条蛋白编码转录本**，与 CDS/PEP 数量一致、干净 | 全部保留为 `mRNA`：Genefunc 表 188,859 行，含无 CDS/无功能的假基因转录本 |
| D3 | **网站显示的 `gene_count`** | `116,420`（蛋白编码基因） | `165,398`（含假基因/非编码的总位点数）或 `128,475`（GFF `gene` 行数） |
| D4 | **JBrowse refseq 大小写统一** | 重建为 `Chr1A_Sumai3`（与 BLAST/getfasta/注释一致；备份旧数据集；`?data=Sumai3` 入口不变） | 保留小写 `chr1A_Sumai3`，另生成一份小写 seqid 的 JBrowse 专用 GFF |
| D5 | **`annotation_source` 文案/分组** | `EGAPx 1.0 (NCBI) de novo annotation; 18 RNA-seq + IsoSeq (SRR38604212)`；`Group=Allohexaploid`；`display_order=500`（对齐 PT） | 由你指定文案/排序 |

另：EGAPx work 目录 563 GB，验收后可清理（保留 `out_run2` 与 annotation 目录即可）。

---

## 3. 总体流程与门禁

```
G0 备份/权限/磁盘
 → Phase 1 数据目录 + FASTA 指纹 + JBrowse refseq 归一化 + all_genomes_type
   → G1 数据目录/指纹/JBrowse 21 条大写 refseq 通过
 → Phase 2 GFF/CDS/PEP 归一化 + 上传 + 兼容性校验/QC
   → G2 check_annotation_compat + check_genome_files rc=0，计数符合
 → Phase 3 annotation_update 全量（含 JBROWSE_DS 补丁）
   → G3 MySQL/BLAST/JBrowse/registry 产物齐全
 → Phase 4 元数据收尾 + 站点验收 + 回归
   → G4 公网 5 个入口 + API + 回归全部通过
```

---

## 4. Phase 0：备份与前置检查（约 0.5 h）

### 4.1 生产备份目录

```bash
TS=$(date +%Y%m%d_%H%M%S)
BK=/var/www/data/masw_data/backup_sumai3_annotation_${TS}
mkdir -p "$BK"
# JBrowse 数据集：只备份控制文件（trackList.json / seq / tracks.conf）
# 目录里的两个 ~14.6 GB FASTA 是历史冗余文件，不压缩、不复制，只登记路径/大小
tar czf "$BK/jbrowse_Sumai3_meta.tgz" -C /var/www/html/jbrowse-1.12.3-release \
  Sumai3/trackList.json Sumai3/seq Sumai3/tracks.conf
stat -c '%s %n' /var/www/html/jbrowse-1.12.3-release/Sumai3/*.fna \
  /var/www/html/jbrowse-1.12.3-release/Sumai3/Sumai3.genome > "$BK/jbrowse_Sumai3_bigfiles.txt" 2>/dev/null || true
cp -a /var/www/html/jbrowse.html "$BK/"
cp -a /var/www/html/blast/blast.html "$BK/"
cp -a /var/www/html/getfasta/blastdb/all_genomes.nal "$BK/"
cp -a /var/www/html/getfasta/blastdb/all_genomes_type.txt "$BK/"
cp -a /var/www/html/getfasta/blastdb/all_gene.nal "$BK/"
cp -a /var/www/html/getfasta/blastdb/all_protein.pal "$BK/" 2>/dev/null || true
cp -a /var/www/data/masw_data/_prep/annotation_update.sh "$BK/"
# DB 备份（Genefuncdb 用 db_ddl 账号；genome_registry 用 FastAPI .env 账号）
PW=$(awk -F= '/^DB_PASS=/{print $2}' /etc/wheatomics/db_ddl.env)
mysqldump -u wheatomics_ddl -p"$PW" Genefuncdb Genefunc_registry > "$BK/Genefunc_registry.sql"
cd /var/www/FastAPI_backend_Port8000
set -a; . ./.env; set +a
mysqldump -u "$DB_USER" -p"$DB_PASSWORD" wheatomics_db genome_registry \
  --where="dataset_id IN ('Sumai3')" > "$BK/genome_registry_sumai3.sql"
```

### 4.2 前置检查

- `df -h /var/www` ≥ 20 T 可用；
- `id fei` 含 `www-data`；`/etc/wheatomics/db_ddl.env` 可读；
- MySQL 写权限：`mysql -u wheatomics_ddl -p... -e "SELECT 1"`；
- `/var/www/FastAPI_backend_Port8000/.env` 的 DB 账号可写 `wheatomics_db`；
- EggNOG DB `/var/www/data/tiantian_data/soft/emapperdb/eggnog_proteins.dmnd`、02G 资源 `Chinese_Spring1.0.mpi` / `IWGSC_v1.1.gff3` 存在；
- 站点当前无正在跑的 pipeline（`pgrep -af annotation_update`）。

---

## 5. Phase 1：数据目录 + 指纹 + JBrowse 归一化（约 1–1.5 h）

### 5.1 建标准数据目录

```bash
D=/var/www/data/masw_data/AABBDD_Sumai3
mkdir -p "$D"
# 用硬链接避免再复制 14.6 GB（同一 /var/www 文件系统）
ln /var/www/html/getfasta/blastdb/AABBDD_Sumai3.genome "$D/Sumai3.fa"
samtools faidx "$D/Sumai3.fa"
grep -c '^>' "$D/Sumai3.fa"     # 期望 21
head -1 "$D/Sumai3.fa"          # 期望 >Chr1A_Sumai3 Sumai3 AABBDD Chr1A
```

> 若不想硬链接，可 `cp`；硬链接只是省 14.6 GB，内容与 md5 完全一致。

### 5.2 指纹 / provenance / seqid mapping

```bash
bash /var/www/data/masw_data/_prep/annotation_update.sh \
  Sumai3 /var/www/data/masw_data/AABBDD_Sumai3 AABBDD --init-fingerprint

cat > "$D/provenance.txt" <<'EOF'
assembly=GCA_051988995.1 (ASM5198899v1)
source=https://www.ncbi.nlm.nih.gov/datasets/genome/GCA_051988995.1/
source_md5=97cc06136176b8a880c21c0b1e7d6f86
paper=10.1002/tpg2.70285 (The Plant Genome 2026)
annotation=EGAPx 1.0.1 de novo; 18 RNA-seq + IsoSeq SRR38604212; taxid 4565
annotation_run=/data/masw_data/Sumai3/egapx/out_run2
EOF
cp /path/from/Ma/seqid_mapping_CM_to_Chr_Sumai3.tsv "$D/"
```

### 5.3 JBrowse refseq 归一化（D4 建议方案）

```bash
JB=/var/www/html/jbrowse-1.12.3-release
# 1) 控制文件已在 Phase 0 备份；把旧数据集移走（不要 cp/tar 里面 14.6GB 的 FASTA）
mv "$JB/Sumai3" "$JB/Sumai3.old_$(date +%Y%m%d_%H%M%S)"
# 2) 用标准 FASTA 重建 refseq（FASTA 头已是 Chr1A_Sumai3…）
cd "$JB"
./bin/prepare-refseqs.pl --fasta "$D/Sumai3.fa" --out Sumai3
# 3) 导入 jbrowse_meta
cd /var/www/FastAPI_backend_Port8000
set -a; . ./.env; set +a
/home/fei/mambaforge/envs/zjw/bin/python3 scripts/import_jbrowse_meta.py --dataset Sumai3
# 4) 验收通过后再删除旧数据集目录（约 29 GB 冗余 FASTA）；保留 1–2 天也可
# rm -rf "$JB/Sumai3.old_*"
```

验收：

```bash
python3 -c "import json;d=json.load(open('$JB/Sumai3/seq/refSeqs.json'));print(len(d),[x['name'] for x in d[:3]])"
# 期望 21 ['Chr1A_Sumai3','Chr1B_Sumai3','Chr1D_Sumai3']
curl -s "http://127.0.0.1:8000/api/jbrowse/datasets/Sumai3/trackList" | head -c 200
```

> 旧数据集目录（含两个 ~14.6 GB 冗余 FASTA）已整体移到 `Sumai3.old_*`；控制文件已备份，确认新页面正常后可直接删除旧目录释放约 29 GB。

### 5.4 补 `all_genomes_type.txt`

```bash
B=/var/www/html/getfasta/blastdb
grep -q '^AABBDD_Sumai3\.genome' "$B/all_genomes_type.txt" || \
  echo -e "AABBDD_Sumai3.genome\tAABBDD" >> "$B/all_genomes_type.txt"
grep 'AABBDD_Sumai3' "$B/all_genomes_type.txt"
```

### 5.5 门禁 G1

- `Sumai3.fa` 21 条、`.fai` 21 条；
- `genome_fingerprint.txt` 存在且 md5 = 现网 BLAST 源；
- JBrowse refseq 21 条、全部 `Chr…_Sumai3`；`?data=Sumai3` 200；
- `all_genomes_type.txt` 有 Sumai3；
- `getfasta`/BLAST/PrimerServer2 原功能正常。

---

## 6. Phase 2：GFF/CDS/PEP 归一化与上传（约 1.5–2 h）

### 6.1 归一化规则（建议 D1/D2）

新建 `normalize_egapx_gff.py`（Ma 上生成，也可在生产 `/var/www/data/masw_data/_prep/` 放一份）：

1. **seqid**：按 `seqid_mapping_CM_to_Chr_Sumai3.tsv` 把 `CM123981.1…` 换成 `Chr1A_Sumai3…`；`##sequence-region` 同步改写。
2. **基因 ID（中国春 02G 风格，最终决定）**：按 `Sumai3_gene_id_scheme.md` 的最终方案生成：
   - 每条染色体的 `gene`+`pseudogene` 位点按 `start,end,旧 ID` 排序；
   - 序号从 100 起、步长 100，六位补零；
   - 基因 ID = `TraesSM3_<chr>01G<6位数字>`；`pseudogene` 追加 `LC`；
   - 例：`SUM3_000009`（Chr1A 第 9 个位点）→ `TraesSM3_1A01G000900`；
   - 旧 `SUM3_…` **不写入 GFF/站点文件**；仅在 Ma 上保留内部 `gene_id_mapping.tsv` 供 QA，不发布。
3. **转录本 ID**：按基因内坐标顺序编号 `.1/.2/...`：
   - 蛋白编码 mRNA：`ID=rna-SUM3_000009-R1` → `TraesSM3_1A01G000900.1`；
   - 假基因 mRNA（D2）：type 改为 `pseudogenic_transcript`，ID → `<geneID>.1`（同样 `.数字`，但不再是 `mRNA`）；
   - `lncRNA`/`transcript`：类型保留，ID → `<geneID>.n`；
   - 具体编号以归一化脚本实际排序为准；内部 mapping 记录每条旧 ID 的最终新 ID，仅用于 QA。
4. **层级属性**：`Parent=` / `Derives_from=` 全部映射到新 ID；`CDS` 的 ID 改为 `cds-<新转录本ID>`（同一条转录本的多个 CDS 片段沿用同一个 ID，与 EGAPx 原格式一致），`exon` 的 ID 改为 `exon-<新转录本ID>-<n>`（保证唯一）。
5. 其他属性（`product=`、`gbkey`、`gene_biotype`、`pseudo=true`、`model_evidence`）原样保留。
6. 输出前统计并断言：
   - `gene=128,475`、`pseudogene=36,923`、`pseudogenic_transcript=37,573`、`mRNA=151,286`、`lncRNA=28,730`、`transcript=10,074`、`CDS=765,019`、`exon=1,182,142`；
   - `mRNA` ID 全部 `.数字` 结尾且唯一；所有 `Parent` 能解析；所有坐标 ≤ 染色体长度。

> 归一化后，GFF 保留假基因结构，但 `--type=mRNA` 只取 151,286 条蛋白编码转录本 → Genefunc 表/BLAST/JBrowse all_gene 都是 151,286，与 CDS/PEP 对齐。

### 6.2 在 Ma 上生成并自检

```bash
cd /data/masw_data/Sumai3/annotation
python3 normalize_egapx_gff.py \
  --gff Sumai3_EGAPx.gff3 \
  --map seqid_mapping_CM_to_Chr_Sumai3.tsv \
  --out Sumai3.normalized.gff3
# 统计/ID 唯一性自检（脚本内完成，另存 normalize_summary.txt）
gzip -9 -c Sumai3.normalized.gff3 > Sumai3.normalized.gff3.gz
md5sum Sumai3.normalized.gff3.gz
```

### 6.3 上传到生产（注意：Mac 直连 Ma 当前不通）

- Ma→Mac：通过 GPU 跳板
  ```bash
  ssh -J sa@10.33.34.55 masw@10.33.34.122 \
    'gzip -c /data/masw_data/Sumai3/annotation/Sumai3.normalized.gff3' \
    > /tmp/Sumai3.normalized.gff3.gz
  ```
- Mac→生产：用 `wheatomics.sh tunnel` + 带密码的 `scp -P 2222`（`~/.config/lab-server/wheatomics.env` 里的 node 密码；可写一个小 expect wrapper）
  ```bash
  scp -P 2222 /tmp/Sumai3.normalized.gff3.gz fei@127.0.0.1:/var/www/data/masw_data/AABBDD_Sumai3/Sumai3.gff3.gz
  ```
- 生产解压并校验 md5；同时把 `seqid_mapping` / normalization 脚本 / summary 一并上传归档。

### 6.4 生成 CDS/PEP，跑兼容性校验

```bash
cd /var/www/data/masw_data/AABBDD_Sumai3
gzip -dc Sumai3.gff3.gz > Sumai3.gff3
/home/fei/mambaforge/envs/new_env/bin/gffread \
  -g Sumai3.fa -x Sumai3.cds -y Sumai3.pep Sumai3.gff3
grep -c '^>' Sumai3.cds Sumai3.pep      # 期望 151,286 / 151,286
python3 /var/www/data/masw_data/_prep/check_annotation_compat.py \
  --dir /var/www/data/masw_data/AABBDD_Sumai3 --mytag Sumai3
python3 /var/www/html/Script/check_genome_files.py Sumai3   # rc=0
```

这里生成的 `Sumai3.cds` / `Sumai3.pep` 就是接下来 `annotation_update.sh` 使用的站点格式文件；脚本第 1 步会再执行一次同样的 gffread（幂等）。建议同时对比 EGAPx 原版 `complete.cds.fna` / `complete.proteins.faa` 的 `>` 数并记录差异（EGAPx 原版 ID 是 `gnl|WGS:…` 风格，不能直接用于站点）。

若 gffread 数量或 QC 不符：回到 Ma 修 normalization（常见：假基因 mRNA 未转换为 `pseudogenic_transcript`、ID 重复、lncRNA 类型干扰），重新上传，不继续生产。

### 6.5 门禁 G2

- `Sumai3.gff3/.cds/.pep` 三件套 + `.fa/.fai` 齐备；
- `check_annotation_compat.py` rc=0；`check_genome_files.py` rc=0；
- CDS/PEP 的 `>` 数 = 151,286（以实际为准，与 EGAPx 原版对比）；
- 头 ID 结尾 `.数字`，pep 序列行无 `.`。

---

## 7. Phase 3：`annotation_update.sh` 全量执行（约 2.5–4 h）

### 7.1 先打 `JBROWSE_DS` 补丁

`annotation_update.sh` 默认 JBrowse 目录 `$JB/$DS`（`AABBDD_Sumai3`），而 Sumai3 的公开数据集是 `Sumai3`。改法（幂等、默认行为不变）：

```bash
cp -a /var/www/data/masw_data/_prep/annotation_update.sh \
      /var/www/data/masw_data/_prep/annotation_update.sh.bak-$(date +%Y%m%d)
# 在 DS=... 下方加：
JBROWSE_DS="${JBROWSE_DS:-$DS}"
# 把 JBrowse 相关 4 处 $DS 改成 $JBROWSE_DS：
#   [ -d "$JB/$DS/seq" ]              -> "$JB/$JBROWSE_DS/seq"
#   cd "$JB/$DS"                     -> "$JB/$JBROWSE_DS"
#   cp ... "$JB/$DS/"                -> "$JB/$JBROWSE_DS/"
#   import_jbrowse_meta.py --dataset "$DS" -> "$JBROWSE_DS"
```

同步更新技能内副本/说明（`~/.agents/skills/lab-server/...` 或 wheatomics.yaml 的 note），避免下次新基因组踩坑。

### 7.2 先 check / dry-run

```bash
cd /var/www/data/masw_data/AABBDD_Sumai3
export JBROWSE_DS=Sumai3
bash /var/www/data/masw_data/_prep/annotation_update.sh \
  Sumai3 /var/www/data/masw_data/AABBDD_Sumai3 AABBDD --check
bash /var/www/data/masw_data/_prep/annotation_update.sh \
  Sumai3 /var/www/data/masw_data/AABBDD_Sumai3 AABBDD --dry-run
```

### 7.3 正式执行（后台 + 日志）

```bash
cd /var/www/data/masw_data/AABBDD_Sumai3
export JBROWSE_DS=Sumai3
setsid --fork bash -c '
  export PATH=/home/fei/mambaforge/bin:/var/www/html/blast/blast+/bin:$PATH
  export JBROWSE_DS=Sumai3
  bash /var/www/data/masw_data/_prep/annotation_update.sh \
    Sumai3 /var/www/data/masw_data/AABBDD_Sumai3 AABBDD
' > pipeline_Sumai3_annotation.log 2>&1 < /dev/null
```

脚本依次产出（与 SOP 一致）：

| # | 步骤 | 产物 / 预期 |
|---|---|---|
| 1 | gffread | `Sumai3.cds` / `Sumai3.pep`（151,286 条） |
| 2 | check_genome_files | rc=0 |
| 3 | EggNOG emapper | `AABBDD_Sumai3_annotation.emapper.annotations`（约 20–40 min） |
| 4 | jcvi BED + 注释 | `AABBDD_Sumai3.bed`、`*_with_annotation.bed`（151,286 行） |
| 5 | MySQL 注册 | `Genefuncdb.Genefunc_AABBDD_Sumai3_table`（151,286 行，TRUNCATE+LOAD） |
| 6 | 中国春 02G | `*_with_annotation_ChineseSpring02G.bed`、add_eggnog gff3（约 20–40 min） |
| 7 | CDS/PEP BLAST | `AABBDD_Sumai3.add_Description.cds/.pep` + `.fai` + 软链 |
| 8 | JBrowse | `Sumai3/all_gene` 轨道（含 FeatureSequence 菜单）+ names |
| 9 | jbrowse_meta | `import_jbrowse_meta.py --dataset Sumai3` |
| 10 | registry/聚合库/前端 | `Genefunc_registry` 行、all_gene/all_protein 别名、`blast.html` All genes/All proteins |

全程日志：`/var/www/data/masw_data/AABBDD_Sumai3/annotation_update_*.log`；退出码 0 且日志末尾无 `[FAIL]` 即通过。

### 7.4 元数据收尾（脚本之后）

**A. `Genefunc_registry` 行补全**（脚本只插占位行，需补 DOI/标题/分组/显示名；`example_*` 必须选**真实存在**的 ID，建议直接用脚本日志里的 `first mRNA=...`，下面示例用编码转录本占位）：

```sql
UPDATE Genefuncdb.Genefunc_registry
SET Doi='10.1002/tpg2.70285',
    title='Chromosome-scale assembly of wheat cultivar Sumai 3 …',
    `Group`='Allohexaploid',
    Polyploidy='AABBDD',
    display_name='Sumai3',
    display_order=500,
    example_chr_id='Chr1A_Sumai3',
    example_gene_id='<first coding mRNA，如 TraesSM3_1A01G000900.1>',
    example_cds_id='<同一 mRNA ID>',
    example_protein_id='<同一 mRNA ID>'
WHERE table_name='Genefunc_AABBDD_Sumai3_table';
```

**B. `genome_registry` 元数据**：在 `scripts/rebuild_genome_registry.py` 的 `overrides` 中新增：

```python
# 注意：overrides 的 key 是站点 dataset_id（API 里 Sumai3 的 dataset_id = "Sumai3"），
# 不是内部 BLAST/MySQL 前缀 AABBDD_Sumai3；内部库名用 blast_* 字段显式指定。
"Sumai3": {
    "ploidy": "AABBDD", "species": "Triticum aestivum", "cultivar_or_line": "Sumai 3",
    "assembly_accession": "GCA_051988995.1", "assembly_level": "Chromosome",
    "genome_size": 14408607908, "chromosome_count": 21,
    "doi": "10.1002/tpg2.70285",
    "paper_title": "Chromosome-scale assembly of wheat cultivar Sumai 3 …",
    "jbrowse_dataset": "Sumai3",
    "blast_genome_db": "AABBDD_Sumai3",
    "blast_cds_db": "AABBDD_Sumai3",
    "blast_pep_db": "AABBDD_Sumai3",
    "annotation_status": "available",
    "annotation_source": "EGAPx 1.0 (NCBI) de novo annotation; 18 RNA-seq + IsoSeq (SRR38604212)",
    "annotation_doi": "10.1002/tpg2.70285",
    "gene_table": "Genefunc_AABBDD_Sumai3_table",
    "gene_count": 116420,
    "notes": "EGAPx annotation 2026-10; BUSCO poales_odb10 C:99.0% [S:5.1%,D:93.9%]; 165,398 gene loci incl. 36,923 pseudogenes; 38,804 ncRNAs",
},
```

> 必须走本地 repo commit → push（github + gitee）→ 服务器 `git pull`，再跑 `rebuild_genome_registry.py`（生产脚本改动会被 webhook 覆盖，见 SOP §7-2）。

```bash
cd /var/www/FastAPI_backend_Port8000
set -a; . ./.env; set +a
/home/fei/mambaforge/envs/zjw/bin/python3 scripts/rebuild_genome_registry.py
```

**C. 可选**：`cite.html` 已含 Sumai3 引文，无需改；JBrowse 卡片维持 DOI；如需下载页/新闻另加。

### 7.5 门禁 G3

- `Genefunc_AABBDD_Sumai3_table` 行数 = 151,286；
- `AABBDD_Sumai3.add_Description.cds/.pep` 的 `blastdbcmd -info` 条数 = 151,286；
- JBrowse `Sumai3` trackList 含 `all_gene` + FeatureSequence；
- `/api/genomes/Sumai3` 的 `annotation_status=available`、`gene_count=116420`、`gene_table=...`；
- `/api/genes/functions/tables` 含 `Genefunc_AABBDD_Sumai3_table`；
- `all_gene.nal` / `all_protein.pal` 已追加成员；
- `blast.html` 的 All genes/All proteins value 已含 Sumai3。

---

## 8. Phase 4：验收与回归（约 1 h）

| # | 检查 | 命令 | 预期 |
|---|---|---|---|
| 1 | 数据目录 | `ls -lh /var/www/data/masw_data/AABBDD_Sumai3/{Sumai3.fa,Sumai3.fa.fai,Sumai3.gff3,Sumai3.cds,Sumai3.pep,genome_fingerprint.txt}` | 全存在 |
| 2 | QC | `check_genome_files.py Sumai3` | rc=0 |
| 3 | MySQL 表 | `SELECT COUNT(*) FROM Genefuncdb.Genefunc_AABBDD_Sumai3_table` | 151,286 |
| 4 | BLAST | `blastdbcmd -db .../AABBDD_Sumai3.add_Description.cds -info`；`.pep` | 151,286 seqs |
| 5 | JBrowse | `curl -s http://127.0.0.1:8000/api/jbrowse/datasets/Sumai3/trackList` | 含 `all_gene`；21 refseq `Chr…_Sumai3` |
| 6 | JBrowse 页面 | `https://wheatomics.sdau.edu.cn/jbrowse-1.12.3-release/?data=Sumai3` | 200，基因结构可显示（可用 Chr3B Fhb1 区域做视觉核验） |
| 7 | API | `/api/genomes/Sumai3`、`/api/genes/functions/tables`、`/api/genes/functions/examples` | 字段齐全 |
| 8 | 序列 API | `/api/sequence/by-gene?gene_id=<first coding mRNA，如 TraesSM3_1A01G000900.1>` | CDS/蛋白 |
| 9 | getfasta | `/api/sequence/chromosomes?database=AABBDD_Sumai3.genome`（21） + `all_genomes` 区域查询 | 正常，含 Sumai3 |
| 10 | PrimerServer2 | `/api/PrimerServer2/databases` | 含 `AABBDD_Sumai3.genome` 与 `.add_Description.cds`，examples 非空 |
| 11 | Web BLAST | `blast.html` 页面 Sumai3 group / All genes / All proteins | 前端可见 |
| 12 | 回归 | 抽查 PT / JM229 / CS 的 JBrowse、BLAST、getfasta | 不受影响 |

浏览器侧可再用 `bash scripts/spa_visual_check.sh`（如改动 SPA）或 ego-browser 截图留档。

---

## 9. 回滚方案

| 场景 | 回滚 |
|---|---|
| GFF/QC 不通过（未跑 pipeline） | 删除数据目录/上传文件即可，站点无变化 |
| pipeline 中途失败 | 脚本幂等；修 GFF 后重跑（表 TRUNCATE、轨道重建、registry UPSERT） |
| 上线后发现问题 | 恢复 `$BK/jbrowse_Sumai3_meta.tgz` 到 JBrowse 目录（或把 `Sumai3.old_*` 移回）；恢复 `jbrowse.html`/`blast.html`/`all_genomes*`；`DROP TABLE Genefuncdb.Genefunc_AABBDD_Sumai3_table`；删除 `Genefunc_registry` 行；删除 `AABBDD_Sumai3.add_Description.*` 库及软链；恢复 `genome_registry` SQL；`systemctl restart wheatomics-api` |
| JBrowse 大写改名导致旧链接失效 | 备份可回滚；如需兼容可在 Apache 加 rewrite/软链 `chr1A_Sumai3` → `Chr1A_Sumai3`（可选） |

Ma 上的 EGAPx 原始产物、归一化脚本与 md5 全部保留，可随时重放。

---

## 10. 风险与应对

| 风险 | 概率/影响 | 应对 |
|---|---|---|
| 归一化后 mRNA ID 重复/缺 `.数字` | 中/高 | check_annotation_compat + 自检脚本拦截；先在 Ma 打印统计 |
| 假基因 mRNA 类型转换与 gffread/JBrowse 兼容性 | 中/中 | 先做小样本测试（1 条染色体）再全量；备选保留 `mRNA` |
| JBrowse 重建 refseq 后旧 locus 链接失效（小写→大写） | 中/低 | 已备份；`?data=Sumai3` 不变；必要时 Apache 重写 |
| `annotation_update.sh` 未适配 `JBROWSE_DS` | 高/中 | 先打补丁 + `--dry-run`；补丁前备份、默认行为不变 |
| 生产磁盘/MySQL 压力 | 低/中 | 30 T 空闲；EggNOG/02G 低峰跑；MySQL 表 151k 行，压力小 |
| Ma→Mac 直连异常（当前已断） | 高/低 | 走 GPU 跳板 + Mac 中转；生产传输用 wheatomics 隧道 |
| `all_genomes_type` 漏行导致 getfasta chips 不显示 | 中/低 | Phase 1 补行并核对 |
| `rebuild_genome_registry.py` 覆盖手工元数据 | 中/中 | 把 Sumai3 写进 overrides 并 push/pull，而不是只改 DB |
| 生产公告/引用口径（EGAPx 不是作者官方注释） | 低/中 | `annotation_source` 明确写 EGAPx；notes 注明方法；如作者后续提供正式 GFF 可替换 |

---

## 11. 时间估算

| 阶段 | 内容 | 预计 |
|---|---|---|
| Phase 0 | 备份/检查 | 0.5 h |
| Phase 1 | 数据目录/指纹/JBrowse 归一化/all_genomes_type | 1–1.5 h |
| Phase 2 | 归一化 + 上传 + QC | 1.5–2 h |
| Phase 3 | annotation_update 全量 | 2.5–4 h（机器时间） |
| Phase 4 | 元数据/验收/回归 | 1 h |
| **合计** | | **约 5–8 h 有效操作**（不含失败重试） |

建议在生产低峰（晚间/周末）跑 Phase 3；EggNOG 与 02G miniprot 可并行资源，但脚本串行执行。

---

## 12. 已确认的决定

- **D1 已定**：`TraesSM3_<chr>01G<6 位数字>`（例 `TraesSM3_1A01G000100`），转录本 `.n`；假基因加 `LC`；旧 `SUM3_…` 不保留。详见 **`Sumai3_gene_id_scheme.md`**。
- **D2 已定**：37,573 条 `pseudo=true` mRNA → `pseudogenic_transcript`；Genefunc/BLAST 只上 151,286 条蛋白编码转录本。
- **D3/D4/D5** 按本计划推荐执行（`gene_count=116,420`；JBrowse refseq 重建为 `Chr1A_Sumai3`；annotation_source 用 EGAPx 文案）；如需调整请在开工前说。

接下来按：

> Phase 0 → G1 → Phase 1 → G2 → Phase 2 → G3 → Phase 3 → G4

逐阶段执行，并在每个门禁后向你汇报实际数字和截图。

---

## 13. 执行记录（2026-10-29 23:25）

- **ID 方案**：已按用户决定改为 `TraesSM3_<chr>01G<6 位数字>`（例 `TraesSM3_1A01G000100`）；转录本 `.n`；假基因加 `LC`；37,573 条 `pseudo=true` mRNA 已转为 `pseudogenic_transcript`；旧 `SUM3_…` ID 未写入 GFF/站点文件（内部 mapping 留在 Ma）。
- **归一化结果**（Ma）：`gene=128475`、`pseudogene=36923`、`mRNA=151286`、`pseudogenic_transcript=37573`、`lncRNA=28730`、`transcript=10074`、`CDS=765019`、`exon=1182142`；151,286 条 mRNA ID 全部 `.数字` 结尾；0 个残留旧 ID。
- **Phase 0/1 已完成**：
  - 生产备份：`/var/www/data/masw_data/backup_sumai3_annotation_20261029_224929/`
  - 数据目录：`/var/www/data/masw_data/AABBDD_Sumai3/`（`Sumai3.fa` 硬链 + `.fai` + 指纹 `3e998418…` + provenance + seqid mapping）
  - JBrowse：旧数据集移到 `Sumai3.old_*`，refseq 已重建为 `Chr1A_Sumai3…Chr7D_Sumai3`（21 条，公开 `?data=Sumai3` 200），`jbrowse_meta` 已导入
  - `all_genomes_type.txt` 已补 `AABBDD_Sumai3.genome<TAB>AABBDD`
  - `annotation_update.sh` 已打 `JBROWSE_DS` 补丁（备份 `.bak-jbrowseds-20261029`）
- **Phase 2 校验**：`check_annotation_compat.py` 兼容 ✅；`check_genome_files.py` rc=0；gffread CDS/PEP 均 151,286 条。
- **Phase 3 进行中**：2026-10-29 23:14 启动全量 `annotation_update.sh`，当前 EggNOG/diamond 步骤；日志 `/var/www/data/masw_data/AABBDD_Sumai3/pipeline_Sumai3_annotation_20261029_231445.log`。

### 13.1 完成记录（2026-10-30 00:25 完成，10:16 复核）

- `annotation_update.sh` 全量运行成功：2026-10-29 23:14 → 2026-10-30 00:25（约 1h11m），日志 `annotation_update_20261029_231445.log`，末尾 `=== annotation_update 完成 ===`，无 `[FAIL]`。
- 产物：
  - `Genefuncdb.Genefunc_AABBDD_Sumai3_table` = **151,286 行**
  - `AABBDD_Sumai3.add_Description.cds` / `.pep` = 各 **151,286** 条（BLAST `blastdbcmd -info`）
  - JBrowse `Sumai3` trackList = **DNA + all_gene**（含 FeatureSequence 菜单）；`tracks/all_gene/Chr1A_Sumai3/trackData.json` 200
  - `all_gene.nal` / `all_protein.pal` 已追加 Sumai3 成员
- 元数据：
  - `Genefunc_registry`：`Group=Allohexaploid`、Doi/标题、display_name=Sumai3、display_order=500、example IDs=`TraesSM3_1A01G000900.1`
  - `genome_registry`：`annotation_status=available`、`gene_count=116,420`、`gene_table=Genefunc_AABBDD_Sumai3_table`、`annotation_source=EGAPx…`、`annotation_doi=10.1002/tpg2.70285`、blast/getfasta/PrimerServer2/JBrowse usage 字段齐全
- 复核 API：`/api/genomes/Sumai3`、`/api/genes/functions/interval`、`/api/sequence/by-gene`、`/api/sequence/by-interval`、`/api/PrimerServer2/databases`、`/api/blast/databases`（`hexaploid_wheat` 分类 24 个 Sumai3 库）全部正常。
- 说明：`annotation_update.sh` 第 13 步“Web BLAST 前端 All genes/All proteins”因站点已切换为 **wheatBLAST SPA**（动态读 `/api/blast/databases`）而跳过；Sumai3 的 CDS/PEP 库已由 API 自动出现在前端，不需要手工改 `blast.html`。
- 可选项：`download.html` 目前没有注释 GFF3/CDS/PEP 的公网下载卡片（标准 SOP 不自动加）；如需公开下载链接可再加。旧 JBrowse 数据集保留在 `Sumai3.old_20261029_225958/` 供回滚，确认后可删。

### 13.2 News 更新（2026-10-30 10:22）

- 站点新闻源：`/var/www/html/V2.0/news.json`（`/help/news.html` 与首页 news bar 动态加载）。
- 原文件最后更新 2026-10-28，**无 Sumai3 条目**；已新增 2026-10-30 头条：
  - 标题：*Sumai 3 genome and EGAPx annotation added to BLAST, GetSequence, JBrowse and gene function search.*
  - 摘要含：GCA_051988995.1、21 条染色体、14,408,607,908 bp、165,398 gene loci / 116,420 protein-coding / 151,286 transcripts / 38,804 ncRNAs、BUSCO 99.0%、ID 方案 `TraesSM3_…`
  - 链接：`https://doi.org/10.1002/tpg2.70285`
- 备份：`/var/www/html/V2.0/news.json.bak-20261030_102243`
- 验证：公网 `https://wheatomics.sdau.edu.cn/V2.0/news.json` 34 条，第一条为 Sumai3（2026-10-30）。

### 13.3 清理（2026-10-30 10:24）

- 已删除旧 JBrowse 数据集 `/var/www/html/jbrowse-1.12.3-release/Sumai3.old_20261029_225958`（约 41 GB，含旧的小写 refseq 与冗余 FASTA）。
- 已删除本次注释更新备份 `/var/www/data/masw_data/backup_sumai3_annotation_20261029_224929`（464 KB）。
- 删除后复核：`?data=Sumai3` 200、trackList 200、`all_gene/Chr1A_Sumai3/trackData.json` 200、news 200、genome API 200；当前 JBrowse 仍为 DNA + all_gene 两条轨道。
- 仍保留的早期备份（如需可再删）：`backup_sumai3_card_20261026_135903`、`backup_sumai3_doi_20261026_113347`、`backup_sumai3_meta_20261026_135618`。

### 13.4 清理（2026-10-30 10:33）

- 已删除剩余 3 个 Sumai3 备份：
  - `backup_sumai3_card_20261026_135903`
  - `backup_sumai3_doi_20261026_113347`
  - `backup_sumai3_meta_20261026_135618`
- 生产数据目录下已无 `backup_sumai3_*`。
- 复核：站点根 200、`?data=Sumai3` 200、trackList 200、all_gene trackData 200、news 200、`/api/genomes/Sumai3` 200。

### 13.5 JBrowse 追加轨道（2026-10-30）

- 18 个 RNA-seq BAM → 1 kb CPM BigWig（Ma：`/data/masw_data/Sumai3/rnaseq_bigwig/bw/`），已上传生产并加入 Sumai3 JBrowse 1.12：`tracks/rnaseq/*.bw`，分类 `RNA-seq (Sumai3)`；trackList 共 20 条（DNA + all_gene + 18 RNA-seq）。
- IsoSeq BAM（`SRR38604212.splice.sorted.bam`，60 MB，CSI 索引）生成，但 **JBrowse 1.12 BAM store 只支持 BAI**；测试轨道前端报 `Not a BAI file`，已从 1.12 trackList 移除。
- 服务器另有 JBrowse 2 v4.1.15：`/var/www/html/genome_browser/`。已添加 Sumai3 assembly 和 IsoSeq BAM 轨道（`BamAdapter` + `CSI`），并测试前端：BAM 206、CSI 200，轨道可见。配置文件：`genome_browser/Sumai3_config.json`（直接 URL：`/genome_browser/?config=Sumai3_config.json`），同时追加到默认 `config.json`（已备份）。

### 13.6 回退 JBrowse 2 的 Sumai3 改动（2026-10-30 14:23）

- 删除 `genome_browser/Sumai3_config.json`；
- 删除 `genome_browser/Sumai3.fa`、`Sumai3.fa.fai`、`SRR38604212.splice.sorted.bam`、`.bam.csi` 软链；
- 用备份恢复 `genome_browser/config.json`：assemblies 仅 `wheat`，tracks 5，无 `Sumai3` 引用；
- 验证：`/genome_browser/` 200，`Sumai3_config.json`/`Sumai3.fa`/BAM 均 404；Sumai3 JBrowse 1.12 仍 200，20 条轨道（DNA + all_gene + 18 RNA-seq BigWig）。

### 13.7 JBrowse 1.12 CSI BAM 支持（方案 A，2026-10-30）

- 问题：1.12 的 `BAM/File.js` 硬编码 BAI（magic/reg2bins/16 kb 线性索引），小麦染色体 >512 Mb 只能生成 `.csi`，前端报 `Not a BAI file`。
- 补丁（仅 1.12，不影响 JBrowse2）：
  - `src/JBrowse/Store/SeqFeature/BAM/File.js`：新增 `_readCSI`（BGZF 解压、CSI header、每 ref bins/chunks；CSI 无线性索引）；`blocksForRange` 增加 CSI 分支；`_reg2bin/_reg2bins` 按 `min_shift/depth` 泛化，保留 BAI 默认参数。
  - `src/JBrowse/Store/SeqFeature/BAM.js`：新增 `csiUrlTemplate` 配置；`saveStore` 兼容 csi。
  - 回滚备份：`/var/www/data/masw_data/_prep/jbrowse_csi_backup_20261030_1435/`（原 `BAM.js`、`BAM/File.js`）。
- Sumai3 轨道：`isoseq_bam`，`urlTemplate=tracks/isoseq/SRR38604212.splice.sorted.bam`，`csiUrlTemplate=...bam.csi`，category `IsoSeq (Sumai3)`。
- 前端测试：`?data=Sumai3&loc=Chr1A_Sumai3:1130000..1150000&tracks=DNA,isoseq_bam` 可显示 BAM alignments；无 `Not a BAI file` 报错。

### 13.8 PacBio 三代转录本 BLAST 库追加 Sumai3 IsoSeq（2026-10-30）

- 选定的“三代转录本”库：`PacBioFullLengthcDNA`（BLAST 聚合库 `aggregated`；原 578,119 seq / 1,210,882,964 bp）。
- 序列 ID 改造：`SRR38604212.N` → `Sumai3_SRR38604212.N`，描述保留 `transcript_M/1`；182,402 条。
- 上传文件：
  - `/var/www/html/getfasta/blastdb/PacBioFullLengthcDNA.Sumai3.fa`（318 MB）
  - `/var/www/html/getfasta/blastdb/PacBioFullLengthcDNA.Sumai3.fa.gz`（92 MB）
  - 原始/改名版也在 Ma：`/data/masw_data/Sumai3/isoseq/Sumai3_SRR38604212.flnc.fasta(.gz)`
- 重建 BLAST DB：合并原有 578,119 条 + 新 182,402 条 = **760,521 条 / 1,535,235,290 bp**；
  - 备份旧库：`/var/www/data/masw_data/_prep/PacBioFullLengthcDNA_update_20261030_1525/`
  - 新库替换 `PacBioFullLengthcDNA.n*`，标题保持 `PacBioFullLengthcDNA`。
- 验证：`blastdbcmd` 计数 760,521；新序列 self hit 100%；旧 `PRJEB15048_hq_1` self hit 100%；`/api/blast/databases` 仍列出该库，category `aggregated`。

#### 13.8.1 验证与 .fai

- 新库 `.fai` 由合并 FASTA（`combined.fa`，760,521 条）重建：`/var/www/html/getfasta/blastdb/PacBioFullLengthcDNA.fai`（32 MB，760,521 行）。
- 站点 `/api/blast/database-example?db=PacBioFullLengthcDNA` → 200，example `PRJEB15048_hq_1`。
- 站点 BLAST 实测（`POST /api/blast/search`，blastn，database=PacBioFullLengthcDNA）：任务成功，结果首条为 `Sumai3_test → Sumai3_SRR38604212.1` 100%，同时仍能命中 `PRJEB15048_*` 旧条目。
