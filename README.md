![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688)

# WheatOmics Backend

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

## MCP 服务器

本项目内置了 MCP（Model Context Protocol）服务器，允许 AI Agent（如 Claude、ChatGPT）直接通过标准化协议访问 WheatOmics 数据。

- **SSE 端点**: `GET /api/mcp/sse`
- **消息端点**: `POST /api/mcp/messages`

MCP 工具目前提供序列查询等功能，可通过配置 MCP 客户端连接使用。

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
