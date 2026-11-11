# 4 个二倍体 Aegilops 基因组数据下载报告（生产机）

> 日期：2026-11-11 20:21–21:40 CST ｜ 执行：Lead（经 lab-server 隧道在 `wheatomics` 节点操作）
> 触发：用户确认「先在 wheatomics 上下载基因组和注释数据」
> 脚本：`scripts/fetch_aegilops4_data.sh`（服务器副本 `/var/www/data/masw_data/_prep/fetch_aegilops4_data.sh`，最终 md5 `7c0985d1…`，已加数据集互斥锁防并发写坏）
> 目标目录：`/var/www/data/masw_data/${PLOIDY}_${MYTAG}/`（与计划中的数据集名一致）

## 0. 结论

**4 个基因组 ×（组装 FASTA + 注释 3 件套）全部下载完成并通过 md5 校验**，共约 **5.32 GB**（4.97 GB 组装 + 0.35 GB 注释），
生产 `/var/www` 磁盘占用后仍有 **30 TB** 余量。每目录 7 个文件 + `provenance.txt`，无残留分片/临时文件。

| 数据集目录 | NCBI 组装 | 组装 FASTA (md5 与 NCBI 一致) | Zenodo 注释（3 个文件 md5 与 Zenodo 一致） | 目录大小 |
|---|---|---|---|---|
| `MM_Aegilops_comosa_IPK_AE783` | GCA_052815735.2 | `…_genomic.fna.gz` 1,300,115,087 B ✅ | GFF3 4,708,571 B / 蛋白 10,668,666 B / EDTA TE 75,641,029 B ✅ | 1.3 G |
| `CC_Aegilops_markgrafii_EKC105_RL5723` | GCA_052815875.1 | `…_genomic.fna.gz` 1,057,009,085 B ✅ | GFF3 4,456,369 B / 蛋白 9,859,590 B / EDTA TE 62,222,449 B ✅ | 1.1 G |
| `UU_Aegilops_umbellulata_IPK_AE740` | GCA_060308565.1 | `…_genomic.fna.gz` 1,268,571,806 B ✅ | GFF3 4,637,390 B / 蛋白 11,846,334 B / EDTA TE 73,292,397 B ✅ | 1.3 G |
| `NN_Aegilops_uniaristata_IPK_AE680` | GCA_052815765.1 | `…_genomic.fna.gz` 1,341,628,727 B ✅ | GFF3 4,613,254 B / 蛋白 10,279,500 B / EDTA TE 77,947,960 B ✅ | 1.4 G |

## 1. 每个目录的文件清单（统一 7 个 + provenance）

| 文件 | 内容 | 来源 |
|---|---|---|
| `GCA_*_genomic.fna.gz` | 基因组组装 FASTA（NCBI 头为 GenBank 登录号，如 `CM127985.1` / `JBHEGE…`） | NCBI FTP `genomes/all/…` |
| `GCA_*_assembly_report.txt` | Sequence-Name ↔ GenBank-Accn ↔ 长度映射（归一化必需） | NCBI FTP |
| `md5checksums.txt` | NCBI 目录 md5 清单（校验基准） | NCBI FTP |
| `Ae.<sp>_genes_HC_LC.gff3.gz` | 基因结构注释（gene/mRNA/exon/CDS，HC+LC 合并） | Zenodo 22681907 |
| `Ae.<sp>_genes_HC_LC.fasta.gz` | 注释蛋白序列（交叉验证用；CDS 由平台 gffread 生成） | Zenodo 22681907 |
| `Ae.<sp>.EDTA.TEanno.gff3.gz` | EDTA TE/重复注释（可选 JBrowse 轨道） | Zenodo 22681907 |
| `provenance.txt` | 本目录数据来源/URL/md5/日期留痕 | 脚本生成 |

## 2. 校验方法与结果

```text
# 在服务器每个数据集目录执行
md5sum GCA_*_genomic.fna.gz   → 与 md5checksums.txt 逐字节一致（4/4 OK）
md5sum *.gff3.gz *.fasta.gz   → 与 Zenodo API checksum 一致（12/12 OK）
gzip -t 全部 .gz              → 16/16 OK
ls 残留 part_*/corrupt_*      → 无
```

md5 基准值：
- 组装（NCBI）：comosa `38b8436f9c4eb360a066a1c79f1a122a` / markgrafii `2a55e0ca2d74109c63c84dcb6d6a077a` / umbellulata `1766c56e9ed9f2d6bcf292925a6628bb` / uniaristata `b9b855678d7beba1cdd58f7ed89123eb`
- 注释（Zenodo）：见 `docs/plans/aegilops4_2026-11/PAPER_DATA.md` §3.2 或各目录 `provenance.txt`

## 3. 过程记录（含一次事故与修复）

1. 20:21 启动单进程顺序下载（`fetch_aegilops4_data.sh --with-te`）→ 实测 NCBI 单连接被限速 ~150 KB/s。
2. 20:30 改为 **4 个基因组并行**（`--only MM/CC/UU/NN`）；并行后聚合速率 ~0.7–3.7 MB/s（波动大）。
3. ⚠ 20:29 停旧进程时 `pkill -f fetch_aegilops4_data.sh` **只杀了 bash，没杀 curl 子进程** → 20:30 新进程用 `curl -C -` 续传时与残留 curl 并发写同一文件 → **comosa FASTA 损坏**（md5 不符、gzip 报 trailing garbage）。
4. 21:29 修复：杀残留 curl → 删除损坏文件 → **6 路分段（Range）并行**重下 → 21:37 完成，size 1,300,115,087 B + md5 `38b8436f…` + gzip OK 全部通过。
5. 其余 3 个基因组一次通过（下载中断/重试均由脚本 `curl -C -` + md5 校验兜住）。

> 教训已写入 SOP §11 第 19 条：停下载任务必须连同 curl 子进程一起杀（或 `pkill -9 -f <URL/文件名>`），
> 续传前确认无残留进程；校验必须 `md5 + gzip -t` 双查。`fetch_aegilops4_data.sh` 已加 **数据集级互斥锁**（`.lock_<DS>` + pid 校验 + 陈旧锁自动清理），同一数据集并发启动会被拒绝。

## 4. 下一步（阶段 A2 归一化，尚未执行）

```bash
# 服务器侧，每基因组：
cd /var/www/data/masw_data/MM_Aegilops_comosa_IPK_AE783
python3 /var/www/data/masw_data/_prep/normalize_diploid.py fasta \
  --fasta GCA_052815735.2_ASM5281573v2_genomic.fna.gz \
  --assembly-report GCA_052815735.2_ASM5281573v2_assembly_report.txt \
  --out Aegilops_comosa_IPK_AE783.fa --mapping Aegilops_comosa_IPK_AE783.fa.mapping.tsv
python3 /var/www/data/masw_data/_prep/normalize_diploid.py gff3 \
  --gff3 Ae.comosa_genes_HC_LC.gff3.gz \
  --assembly-report GCA_052815735.2_ASM5281573v2_assembly_report.txt \
  --out Aegilops_comosa_IPK_AE783.gff3 --id-prefix "AeCom.AE783." \
  --mapping Aegilops_comosa_IPK_AE783.gff3.mapping.tsv --id-map Aegilops_comosa_IPK_AE783.idmap.tsv
/home/fei/mambaforge/envs/new_env/bin/gffread -E -g Aegilops_comosa_IPK_AE783.fa \
  -x Aegilops_comosa_IPK_AE783.cds -y Aegilops_comosa_IPK_AE783.pep Aegilops_comosa_IPK_AE783.gff3
python3 /var/www/data/masw_data/_prep/normalize_diploid.py pep \
  --pep Aegilops_comosa_IPK_AE783.pep --out Aegilops_comosa_IPK_AE783.pep
python3 /var/www/html/Script/check_genome_files.py Aegilops_comosa_IPK_AE783   # 期望 rc=0
```

> 注：`normalize_diploid.py` 尚未安装到服务器 `_prep/`（脚本已在仓库，安装步骤见 `docs/workflow/README.md`）；
> 上表目录中的 `<MYTAG>` 与文件名可按 `name_plan.json` 最终确认后统一。
