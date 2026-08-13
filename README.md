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
| **BLAST** | `/api/blast` | BLAST 同源搜索（蛋白/核酸），全长序列提取，异步 job 执行（daemon） |

## BLAST 搜索

对小麦基因组数据库中已索引的蛋白或核酸序列进行 BLAST 同源搜索。路径配置与原有 CGI 脚本一致，支持多数据库并发搜索。

所有 job 由独立的 **blast job daemon**（systemd 服务 `wheatomics-blastd`）执行，与 API 进程完全解耦：API 只负责入队和查询状态，job 不因 API worker 回收或重启而中断；daemon 崩溃由 systemd 自动拉起，排队中的 job 重新认领、在跑的 job 标记 `stale`。全局并发上限为 `BLAST_MAX_CONCURRENT`（默认 20）。每个 job 一个目录：`BLAST_RESULT_DIR/<job_id>/` 内含 `params.json`、`status.json` 与结果文件，结果由 Apache 在 `/blast_results/` 下直接伺服，7 天后（或目录条目超过 3000 时按最老裁剪）自动清理。

### 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/blast/search` | 执行 BLAST 搜索（`wait` 参数控制同步/异步） |
| `GET` | `/api/blast/status/{job_id}` | 轮询异步 job 的状态与下载链接 |
| `GET` | `/api/blast/databases` | 列出可用数据库 |
| `GET` | `/api/blast/status` | 检查 BLAST 环境 |

### 执行 BLAST 搜索

```bash
curl -X POST "https://wheatomics.sdau.edu.cn/api/blast/search" \
  -d "program=blastp" \
  -d "database=Fielder_protein" \
  -d "evalue=10" \
  -d "max_target_seqs=20" \
  --data-urlencode "query=>seq\nMSSSTGAVTSGIKK..."
```

**参数说明**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `program` | string | `blastp` | `blastp`（蛋白→蛋白库） / `blastn`（核酸→核酸库） / `blastx`（核酸翻译→蛋白库） / `tblastn`（蛋白→核酸库翻译） / `tblastx`（核酸翻译→蛋白库翻译） |
| `database` | string | **必填** | 数据库名，多个用逗号分隔（最多 20 个；仅允许字母/数字/下划线/点/连字符） |
| `query` | string | **必填** | FASTA 格式查询序列（最长 100K 字符；不以 `>` 开头时自动补 `>query` 头） |
| `evalue` | float | `10.0` | E-value 阈值（0–1000） |
| `max_target_seqs` | int | `1000` | 最多返回的匹配数（1–50000） |
| `word_size` | int | — | 可选，word 大小 |
| `matrix` | string | — | 可选，打分矩阵 |
| `outfmt` | string | `tabular` | 结果格式：`tabular`（默认，outfmt 6 表格，含 `ppos`/`btop` 变异信息列） / `traditional`（outfmt 0 逐位比对，标记行直接显示氨基酸差异） / `both`（两种都生成） |
| `wait` | bool | `true` | `true`＝同步等待 job 完成（默认，与历史调用契约一致）；`false`＝立即返回 `job_id`，轮询状态接口 |

**同步模式**（`wait=true`，默认）：请求等待 job 完成（轮询上限 1100 秒），返回结果文件下载链接：

```json
{
  "success": true,
  "program": "blastp",
  "database": ["Fielder_protein"],
  "parameters": {"evalue": 10.0, "max_target_seqs": 20},
  "query_header": ">seq",
  "outfmt": ["tabular"],
  "download_url": {
    "tabular": "https://wheatomics.sdau.edu.cn/blast_results/<job_id>/result.tsv"
  }
}
```

`download_url` 与 `outfmt` 只包含提交时选择的格式：`traditional` 时是 `.txt` 逐位比对文件，`both` 时两个键都有。tabular 的 `.tsv` 除标准列外还带 `ppos`（正匹配百分比）与 `btop`（逐位变异编码）两列，不用 traditional 也能看出具体氨基酸差异。

失败时返回对应状态码：400（参数错误）、404（数据库不存在）、429（任务队列已满，稍后重试）、500（BLAST 执行失败）、504（执行或轮询超时），错误消息在响应的 `message`/`detail` 字段。

**异步模式**（`wait=false`）：立即返回，适合浏览器前端与长查询：

```bash
curl -X POST "https://wheatomics.sdau.edu.cn/api/blast/search" \
  -d "program=blastn" -d "database=CS_v2.1_cds" -d "wait=false" \
  --data-urlencode "query=>seq\nACGTACGTACGT"
```

```json
{
  "success": true,
  "job_id": "a3f1c9d2-e9b5-4d4c-b3a1-6e8f0d9c2a1b",
  "status": "pending",
  "status_url": "/api/blast/status/a3f1c9d2-e9b5-4d4c-b3a1-6e8f0d9c2a1b",
  "message": "BLAST job submitted; poll the status_url for completion."
}
```

### 轮询 job 状态

```bash
curl "https://wheatomics.sdau.edu.cn/api/blast/status/<job_id>"
```

```json
{
  "success": true,
  "job_id": "a3f1c9d2-e9b5-4d4c-b3a1-6e8f0d9c2a1b",
  "status": "done",
  "message": "",
  "download_urls": {
    "tabular": "https://wheatomics.sdau.edu.cn/blast_results/<job_id>/result.tsv"
  }
}
```

`status` 取值：`pending`（排队）→ `running`（执行中）→ `done` / `error` / `stale`（终态）。`done` 时 `download_urls` 填充（只含提交时 `outfmt` 指定的格式）；`error`/`stale` 时看 `message`——`stale` 表示 job 在 daemon 重启时被中断，需重新提交。`job_id` 必须为 uuid4 格式，非法或不存在返回 404。

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
| `BLAST_RESULT_DIR` | BLAST job 目录（结果 + 状态文件） | /var/www/html/blast_results |
| `BLAST_RESULT_BASE_URL` | BLAST 结果 URL 前缀 | /blast_results |
| `BLAST_RESULT_EXPIRE_DAYS` | job 结果保留天数 | 7 |
| `BLAST_RESULT_MAX_FILES` | 结果目录条目上限（超限按最老裁剪） | 3000 |
| `BLAST_MAX_CONCURRENT` | blast daemon 全局并发上限（需重启 daemon 生效） | 20 |
| `BLAST_MAX_QUEUED` | 排队+运行中 blast 任务上限（超限提交返回 429） | 200 |
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
