# SynTeny Viewer — 部署配置说明

> 版本：`12221c2`（基于 `4277c5c` 修复后）  
> 部署日期：2026-07-30  
> 服务器：`fei@WheatOmics`  
> 项目路径：`/var/www/FastAPI_backend_Port8000`

---

## 一、概述

SynTeny Viewer 是 WheatOmics 平台的新模块，用于展示基因在染色体上的邻域（上下游 N 个基因）与同源群（homoeologous group）共线性关系。画图风格参考 JCVI 的 `mcscan` 格式：左侧为基因组/亚基因组名称和染色体区间，右侧为染色体轨道上的基因点图，不同染色体之间属于同一同源群的基因用虚线连接。

### 数据依赖

| 数据 | 路径 | 说明 |
|---|---|---|
| BED 文件 | `/var/www/html/col_bed/*.bed` | 4 列制表符分隔：`chromosome start end gene_id` |
| Cluster 文件 | `/var/www/html/orthefind/Results_Jul24/WorkingDirectory/SpeciesIDs_cluster.txt` | 物种到同源群 (1-7) 的映射 |

---

## 二、服务器操作步骤

```bash
# 1. 进入项目目录
cd /var/www/FastAPI_backend_Port8000

# 2. 备份当前版本（可选）
cp -r app/api/routers /tmp/routers_backup_$(date +%Y%m%d)
cp main.py /tmp/main_backup_$(date +%Y%m%d)

# 3. 拉取最新代码
git reset --hard 4277c5c
git pull gitee main --force

# 4. 确认新增文件存在
ls -la app/api/routers/syntenyview.py
ls -la app/static/syntenyview/index.html

# 5. 确认 BED 文件目录正确且有权访问
ls /var/www/html/col_bed/ | head -10
# 应输出类似：
#   AK58_A.filter.bed
#   AK58_B.filter.bed
#   ...

# 6. 确认 SpeciesIDs_cluster.txt 存在
head -2 /var/www/html/orthefind/Results_Jul24/WorkingDirectory/SpeciesIDs_cluster.txt
# 应输出类似：
#   SpeciesIDs	cluster1	cluster2	...
#   0: AK58_A.pep	TraesAK58CH1A	TraesAK58CH2A	...
```

---

## 三、服务重启

```bash
# 1. 终止当前运行的 uvicorn 进程
pkill -f 'uvicorn main:app'

# 2. 确认进程已终止
ps aux | grep uvicorn

# 3. 重新启动（nohup 后台运行）
nohup /home/fei/mambaforge/envs/zjw/bin/uvicorn main:app --host 0.0.0.0 --port 8000 > api.log 2>&1 &

# 4. 等待 2-3 秒确认启动成功
sleep 3
tail -20 api.log
```

---

## 四、验证

### 4.1 API 端点验证

```bash
# 测试 neighborhood API
curl 'http://localhost:8000/api/syntenyview/neighborhood?q=TraesCS1A02G219700.1&upstream=5&downstream=5' | python3 -m json.tool | head -40
```

期望返回 JSON 包含：`query`, `query_cluster`, `rows` (数组), `cluster_connections` (数组)。

### 4.2 前端页面验证

打开浏览器访问：
```
https://wheatomics.sdau.edu.cn/syntenyview/?q=TraesCS1A02G219700.1
```

应显示：
- 顶部搜索框
- 图例（Query 基因 + 7 个同源群颜色）
- SVG 画布：各行对应不同基因组/亚基因组/染色体，基因点按位置排列，同源群基因之间虚线连接

### 4.3 故障排查

| 症状 | 检查项 |
|---|---|
| API 返回 `Gene not found` | BED 文件路径是否正确？`app/api/routers/syntenyview.py` 第 22 行 `BED_DIR = Path("/var/www/html/col_bed")` |
| API 返回空 rows | SpeciesIDs_cluster.txt 路径是否正确？确认 `CLUSTER_FILE` 指向 `Results_Jul24` |
| 前端页面 404 | `main.py` 第 134 行的 `app.mount("/syntenyview", ...)` 是否存在 |
| 前端页面 500 | 查看 `api.log` 尾部错误信息 |

---

## 五、新增文件清单

| 文件 | 说明 |
|---|---|
| `app/api/routers/syntenyview.py` | 独立 API 端点，负责 BED 加载、cluster 解析、邻域检索 |
| `app/api/routers/__init__.py` | 新增 `syntenyview` router 导入 |
| `app/static/syntenyview/index.html` | 前端页面（SVG 交互式可视化） |
| `main.py` | 新增 mount 和 router 注册 |

---

## 六、API 接口说明

### `GET /api/syntenyview/neighborhood`

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `q` | string | (必填) | 查询基因 ID，如 `TraesCS1A02G219700.1` |
| `upstream` | int | 5 | 上游基因数量 (0-20) |
| `downstream` | int | 5 | 下游基因数量 (0-20) |

**返回结构：**

```json
{
  "query": "TraesCS1A02G219700.1",
  "query_cluster": 1,
  "query_genome": "CS-IAAS",
  "query_subgenome": "A",
  "query_chrom": "chr1A",
  "rows": [
    {
      "genome": "CS-IAAS",
      "subgenome": "A",
      "chrom": "chr1A",
      "genes": [
        { "gene_id": "...", "cluster": 1, "start": 12345 }
      ]
    }
  ],
  "cluster_connections": [
    {
      "from_gene": "...",
      "to_gene": "...",
      "cluster": 1
    }
  ]
}
```

---

## 七、注意事项

1. BED 文件命名规则：`{GenomeName}_{A/B/D}.filter.bed` 或 `{GenomeName}_{A/B/D}.bed`，其中 `{A/B/D}` 为亚基因组代码。
2. 同源群解析依赖 `SpeciesIDs_cluster.txt`，确保该文件指向正确的 OrthoFinder 结果目录（当前为 `Results_Jul24`）。
3. 首次请求会加载并缓存所有 BED 文件，后续请求直接使用缓存，无需重启服务。
