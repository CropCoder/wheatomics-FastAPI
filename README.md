![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688)

# WheatOmics Backend

> **版本**: v2.0 | **更新日期**: 2025-06-18
>
> **重要提示**: 本项目为 WheatOmics 后端重构版本，API 接口与原 CGI 版本不完全兼容。如果你正在使用旧版 API，请参考 [遗留系统说明](#遗留系统说明) 并逐步迁移。生产环境部署前请务必检查 `app/core/config.py` 中的数据库连接与路径配置。

WheatOmics 是全球小麦多组学数据整合分析平台（[wheatomics.sdau.edu.cn](https://wheatomics.sdau.edu.cn)）的后端服务，基于 FastAPI 构建，为前端提供 RESTful API，同时内置 MCP（Model Context Protocol）服务器以支持 AI Agent 的智能数据访问。

## 项目背景

本项目是对 WheatOmics 原始 CGI 后端脚本的全面重构。`cgi-py-RawScript/` 目录保留了网站初期的所有后端脚本，`app/` 目录则是基于 FastAPI 的现代化重构版本，在保持原有业务逻辑的基础上，提供了：

- 标准化的 RESTful API 设计
- 统一的请求校验与错误处理
- 自动生成的交互式 API 文档（Swagger / ReDoc）
- MCP 协议支持，可直接对接大语言模型

## 快速开始

### 环境要求

- Python 3.10+
- MySQL 5.7+ / 8.0
- Linux 环境（生产部署需要 BLAST+ 等外部工具）

### 安装

```bash
# 克隆仓库
git clone https://github.com/CropCoder/wheatomics-FastAPI.git
cd wheatomics-FastAPI

# 创建虚拟环境
python -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量（可选，config.py 中有默认值）
cp .env.example .env
# 编辑 .env 填写数据库连接信息
```

### 开发模式启动

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

启动后访问：
- Swagger UI: [http://localhost:8000/api/docs](http://localhost:8000/api/docs)
- ReDoc: [http://localhost:8000/api/redoc](http://localhost:8000/api/redoc)
- 健康检查: [http://localhost:8000/api/health](http://localhost:8000/api/health)

### 生产部署

```bash
nohup gunicorn main:app \
  -b 127.0.0.1:8000 \
  -w 8 \
  -k uvicorn.workers.UvicornWorker \
  --reload \
  > api.log 2>&1 &
```

## API 概览

所有接口前缀为 `/api`，统一返回格式：

```json
{
  "success": true,
  "data": { ... }
}
```

| 模块 | 前缀 | 主要功能 |
|------|------|----------|
| Genes | `/api/genes` | 已知基因搜索、详情、功能注释、基因提交与更新 |
| Expression | `/api/expression` | 多项目基因表达谱查询 |
| Networks | `/api` | 共表达网络边查询、PPI 互作网络 |
| Comparative | `/api` | 同源基因映射（小麦-水稻-拟南芥）、共线性区间 |
| Sequences | `/api` | 基因序列获取、预计算 BLAST 结果 |
| Literature | `/api/literature` | 文献标签统计与检索 |
| Tasks | `/api/tasks` | 共线性图生成、SNP 引物设计（异步任务模式） |
| **BLAST** | `/api/blast` | BLAST 同源搜索（蛋白/核酸），全长序列提取，静态结果页面 |

## BLAST 搜索

对小麦基因组数据库中已索引的蛋白或核酸序列进行 BLAST 同源搜索。路径配置与原有 CGI 脚本一致，支持多数据库并发搜索。

### 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/blast/search` | 执行 BLAST 搜索 |
| `GET` | `/api/blast/databases` | 列出可用数据库 |
| `GET` | `/api/blast/status` | 检查 BLAST 环境 |

### 执行 BLAST 搜索

```bash
curl -X POST "https://wheatomics.sdau.edu.cn/api/blast/search" \
  -d "program=blastp" \
  -d "database=Fielder_protein" \
  -d "evalue=10" \
  -d "max_target_seqs=20" \
  -d "outfmt=json" \
  --data-urlencode "query=>seq\nMSSSTGAVTSGIKK..."
```

**参数说明**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `program` | string | `blastp` | `blastp`（蛋白→蛋白库） / `blastn`（核酸→核酸库） / `blastx`（核酸翻译→蛋白库） / `tblastn`（蛋白→核酸库翻译） / `tblastx`（核酸翻译→蛋白库翻译） |
| `database` | string | **必填** | 数据库名，多个用逗号分隔 |
| `query` | string | **必填** | FASTA 格式查询序列（最长 100K 字符） |
| `evalue` | float | `10.0` | E-value 阈值 |
| `max_target_seqs` | int | `20` | 最多返回的匹配数 |
| `word_size` | int | — | 可选，word 大小 |
| `matrix` | string | — | 可选，打分矩阵 |
| `outfmt` | string | `json` | 返回格式：`json`（结构化）或 `tabular`（表格文本） |
| `save_html` | bool | `false` | 是否生成可访问的静态结果页面 |

**返回结构**（`outfmt=json`）：

```json
{
  "success": true,
  "program": "blastp",
  "database": ["Fielder_protein"],
  "parameters": {"evalue": 10.0, "max_target_seqs": 20},
  "query_header": ">seq",
  "total_hits": 15,
  "hits": [
    {
      "query_id": "seq",
      "subject_id": "TraesCS1A02G123400",
      "pident": 98.45,
      "alignment_length": 345,
      "mismatches": 4,
      "gap_opens": 1,
      "q_start": 1,
      "q_end": 345,
      "s_start": 23,
      "s_end": 367,
      "evalue": 1.23e-45,
      "bitscore": 678.9,
      "subject_full_sequence": ">seq\nMSSSTGAVTSGIKK..."
    }
  ]
}
```

每个 hit 的 `subject_full_sequence` 字段通过 `blastdbcmd` 从 BLAST 数据库中提取全长序列，按唯一 subject ID 去重查询。

### 生成静态结果页面

设置 `save_html=true` 会在服务器生成一份 HTML 结果页面，自动清理 7 天前的过期结果：

```bash
curl -X POST "https://wheatomics.sdau.edu.cn/api/blast/search" \
  -d "program=blastp" \
  -d "database=Fielder_protein" \
  -d "save_html=true" \
  --data-urlencode "query=>seq\nMSSSTGAVTSGIKK..."
```

响应会额外返回 `html_url` 字段：

```json
{
  "success": true,
  "html_url": "https://wheatomics.sdau.edu.cn/blast_results/blast_20250618_112233_123456.html",
  "hits": [...]
}
```

结果页面带有完整站点风格（header/footer、Bootstrap 表格），每个 hit 支持展开查看全长序列。

### 列出可用数据库

```bash
curl "https://wheatomics.sdau.edu.cn/api/blast/databases?program=blastp"
```

返回按蛋白/核酸分组的数据库列表，同时提供按**基因组分类**的结构化数据，供 AI agent 参考：

```json
{
  "success": true,
  "program": "blastp",
  "protein": {
    "count": 30,
    "databases": ["Fielder_protein", "AK58_protein.fasta", ...]
  },
  "nucleotide": {
    "count": 12,
    "databases": ["CS_v2.1_cds", ...]
  },
  "total": 42,
  "categories": [
    {
      "id": "hexaploid_wheat",
      "label": "Hexaploid wheat genome",
      "description": "Common wheat (Triticum aestivum)",
      "count": 18,
      "databases": ["Fielder_protein", "AK58_protein.fasta", "Jagger_protein", ...]
    },
    {
      "id": "tetraploid_wheat",
      "label": "Tetraploid wheat genome",
      "description": "Durum wheat, wild emmer, domesticated emmer",
      "count": 3,
      "databases": ["durum_protein", "wild_emmer_protein", ...]
    },
    {
      "id": "diploid_wheat",
      "label": "Diploid wheat genome and wild relatives",
      "description": "Aegilops tauschii, Triticum urartu, Triticum monococcum, and other Aegilops species",
      "count": 15,
      "databases": ["tauschii_protein", "urartu_protein", ...]
    },
    {
      "id": "barley",
      "label": "Barley genome",
      "description": "Barley (Hordeum vulgare) - Morex, Golden Promise, Qingke",
      "count": 3,
      "databases": ["barley_morex_protein", ...]
    },
    {
      "id": "other_triticeae",
      "label": "Other Triticeae genome",
      "description": "Rye (Secale cereale), Thinopyrum elongatum",
      "count": 3,
      "databases": ["rye_protein", ...]
    }
  ]
}
```

分类基于数据库名关键词自动匹配，未匹配的数据库归入 `Other / Unclassified`。

### 检查 BLAST 环境

```bash
curl "https://wheatomics.sdau.edu.cn/api/blast/status"
```

返回 `blastp`、`blastn`、`blastdbcmd` 的可执行状态及版本号，以及数据目录中已索引的数据库列表。

## MCP 服务器

本项目内置了 MCP（Model Context Protocol）服务器，允许 AI Agent（如 Claude、ChatGPT）直接通过标准化协议访问 WheatOmics 数据。

- **SSE 端点**: `GET /api/mcp/sse`
- **消息端点**: `POST /api/mcp/messages`

MCP 工具目前提供序列查询等功能，可通过配置 MCP 客户端连接使用。

## 配置说明

所有配置通过环境变量注入，详见 `app/core/config.py`：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `APP_NAME` | 应用名称 | WheatOmics API for Ai Agent - FastAPI |
| `APP_VERSION` | 版本号 | 2.0 |
| `API_PREFIX` | API 路由前缀 | /api |
| `DEBUG` | 调试模式 | true |
| `DB_HOST` | 数据库地址 | localhost |
| `DB_PORT` | 数据库端口 | 3306 |
| `DB_USER` | 数据库用户 | wheatomics_user |
| `DB_PASSWORD` | 数据库密码 | - |
| `DB_*` | 各业务数据库名 | 见 config.py |
| `BLAST_DB_PATH` | BLAST 数据库路径 | /var/www/html/getfasta/blastdb |
| `FASTA_DB_PATH` | FASTA 序列文件路径 | /data/fasta |
| `BLAST_RESULT_DIR` | BLAST 结果 HTML 存储路径 | /var/www/html/blast_results |
| `BLAST_RESULT_BASE_URL` | BLAST 结果 URL 前缀 | /blast_results |
| `BLAST_RESULT_EXPIRE_DAYS` | 结果文件保留天数 | 7 |
| `BLAST_SITE_BASE_URL` | 站点域名 | https://wheatomics.sdau.edu.cn |

## 遗留系统说明

`cgi-py-RawScript/` 目录是 WheatOmics 网站 V1 版本的原始 CGI 后端脚本集合，包括：

- 基因搜索与详情（`gene_search.py`、`geneDetail.py`）
- 基因表达查询（`gene_expression*.py`）
- 共表达网络（`co-expression.py`）
- PPI 互作网络（`get_wheatPPI.py`）
- BLAST 序列检索（`get_fasta_bedtools.py`、`preblast`）
- 文献管理（`literature.py`）
- SNP 引物设计（`run_getkasp.py`、`snprimer_index.py`）
- 共线性可视化（`symap.py`、`viewsymap.py`）

这些脚本作为业务逻辑参考保留，`app/` 中的路由模块均基于此重构。

## 许可证

MIT License

## 联系方式

- 网站: [https://wheatomics.sdau.edu.cn](https://wheatomics.sdau.edu.cn)
- 邮箱: zhaojiwen@yzwlab.cn
