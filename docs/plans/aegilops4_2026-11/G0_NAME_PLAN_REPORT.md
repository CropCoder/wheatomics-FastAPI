# G0 命名门禁执行报告（4 个二倍体 Aegilops）

> 日期：2026-11-12 00:08–00:12 CST ｜ 执行：Lead（生产机只读 + 数据目录写入）
> 触发：用户确认「接着做 G0（生成 4 份 name_plan.json 并跑 --check-name）」
> 结果：**4/4 `[OK] 命名可直接开跑`，4 份 `name_plan.json` 已落盘**

## 0. 结论

| 数据集 | ploidy | Group | BLAST 分类 | JBrowse 分区 | 门禁 |
|---|---|---|---|---|---|
| `MM_Aegilops_comosa_IPK_AE783` | MM | Other Triticeae | other_triticeae | `group-mm`（已存在） | `[OK]` |
| `CC_Aegilops_markgrafii_EKC105_RL5723` | CC | Other Triticeae | other_triticeae | `group-cc`（收尾时新建，WARN） | `[OK]` |
| `UU_Aegilops_umbellulata_IPK_AE740` | UU | Other Triticeae | other_triticeae | `group-uu`（已存在） | `[OK]` |
| `NN_Aegilops_uniaristata_IPK_AE680` | NN | Other Triticeae | other_triticeae | `group-nn`（收尾时新建，WARN） | `[OK]` |

- 4 份 plan 文件：`<data_dir>/name_plan.json`（本地副本：`docs/plans/aegilops4_2026-11/name_plans/`）；
- 关键字段：`ds/ploidy/myTag/subgenomes/group/label/doi/title/accession/species/cultivar/sourceUrl/sourceMd5/journal/year/classification/jbrowseSection/confirmed=true`；
- `displayOrder=1`（同 Polyploidy 现有行多为 NULL/0，收尾时可按需调整）。

## 1. 执行方式（不碰线上业务）

- 服务器安装了**新版收尾脚本**：`/var/www/data/masw_data/_prep/finish_genome_integration.sh`
  （v2，md5 `d8162ac0…`，旧版备份 `finish_genome_integration.sh.bak-20261112_000850`）；
- 门禁读取的代码用**预发布仓库副本**（因为阶段 0 代码尚未部署到生产 repo）：
  `/var/www/data/masw_data/_prep/staging_repo/{app/api/routers/blast.py, scripts/rebuild_genome_registry.py}`
  （= 本仓库已改好的版本：分类关键词 + `SUB` CC/NN）；
- JBrowse/BLAST 页面用生产真实页面（只读）做 V2/SPA 识别；
- **生产代码/服务未改动**；G0 只新增了 4 个数据目录里的 `name_plan.json`。

## 2. 每份 plan 的关键内容

以 comosa 为例（其余 3 份同结构，仅材料/登录号/分区不同）：

```json
{
  "ds": "MM_Aegilops_comosa_IPK_AE783",
  "ploidy": "MM",
  "myTag": "Aegilops_comosa_IPK_AE783",
  "subgenomes": "M",
  "group": "Other Triticeae",
  "label": "Ae.comosa IPK-AE783 (M)",
  "doi": "10.1186/s12870-026-10046-2",
  "title": "Chromosome-level reference genome assemblies and annotation of four diploid Aegilops",
  "accession": "GCA_052815735.2",
  "species": "Aegilops comosa",
  "cultivar": "IPK-AE783",
  "sourceUrl": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/052/815/735/GCA_052815735.2_ASM5281573v2/",
  "sourceMd5": "38b8436f9c4eb360a066a1c79f1a122a",
  "journal": "BMC Plant Biology",
  "year": "2026",
  "classification": "other_triticeae",
  "jbrowseSection": "group-mm",
  "sectionTitle": "MM Aegilops comosa",
  "sectionDesc": "Aegilops comosa (M genome)",
  "searchExtra": "aegilops comosa m genome ipk-ae783",
  "confirmed": true
}
```

## 3. 下一步 G3 前的前置条件（需要确认）

G3 流水线（`add_wheat_genome.sh`）本身只强校验 `name_plan.json`，但：

1. 流水线 Step 10 会跑 `rebuild_genome_registry.py`（生产 repo 版本）——**阶段 0 的 `SUB` CC/NN、4 条 overrides、web_blast SPA 判定尚未部署**，不部署则 registry 元数据/染色体数会不对；
2. G4 收尾需要**新版 `finish_genome_integration.sh`**（已装服务器 `_prep/`）与生产 repo 的分类关键词（`DB_CLASSIFICATION`）生效；
3. 因此建议 **G3 前先把阶段 0 代码部署到生产**：
   ```bash
   # 本地：git fetch origin 对齐 → commit → github+gitee 双推
   # 生产：git fetch origin && git merge --ff-only origin/main
   sudo systemctl restart wheatomics-api          # blast.py/分类缓存生效（60–90 s）
   ```
4. G3 流水线（每基因组 25–45 min，4 个顺序 2–4 h）会创建 BLAST 库 / Genefunc 表 / JBrowse 数据，属于生产写操作，建议夜间低峰一次跑完。

## 4. 证据

- 4 份 `name_plan.json`（本地备份 `docs/plans/aegilops4_2026-11/name_plans/`）；
- 服务器门禁输出：4 次 `[OK] 命名可直接开跑`（`/tmp/g0_plans.sh` 运行日志；CC/NN 仅 WARN"收尾时新建分区"）；
- 脚本/副本 md5：`finish_genome_integration.sh` = `d8162ac0…`；staging `blast.py` = `1bb62043…`；staging `rebuild_genome_registry.py` = `5a799ffd…`。
