"""Main application entry point for the refactored WheatOmics FastAPI service."""

from __future__ import annotations

import logging
import subprocess
import time
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import comparative, expression, gene, genehub, literature, coexpression, ppi, sequence, tasks, blast
from app.core.config import settings
from app.mcp.sequence_tools import sequence_mcp_server

# 导入 MCP 核心组件
from mcp.server import Server
from mcp.server.sse import SseServerTransport

from starlette.routing import Route




logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,   
    description=(
        "<h2>概述</h2>"
        "WheatOmics 是全球小麦多组学数据整合分析平台，涵盖基因组、转录组、"
        "蛋白互作组及文献等多维度数据。本 API 为平台后端服务，采用 RESTful 设计，"
        "为前端应用与第三方工具提供结构化的数据访问能力。"
        "<br><br>"
        "所有接口前缀为 <code>/api</code>，统一返回 JSON 格式："
        "<pre>{\"success\": true, \"data\": { ... }}</pre>"

        "<h2>模块说明</h2>"
        "<table>"
        "<tr><td><b>Known Genes</b></td><td><code>/api/genes</code></td>"
        "<td>已知基因搜索与详情、PFAM 搜索、染色体区间工具</td></tr>"
        "<tr><td><b>Coexpression</b></td><td><code>/api/coexpression</code></td>"
        "<td>共表达网络关系对查询与网络图数据检索</td></tr>"
        "<tr><td><b>Search Wheat Protein-Protein Interactions</b></td><td><code>/api/ppi</code></td>"
        "<td>小麦蛋白质互作关系查询（wheatPPI，CF-MS 数据）</td></tr>"
        "<tr><td><b>Comparative 比较</b></td><td><code>/api/comparative</code></td>"
        "<td>小麦-水稻-拟南芥同源基因映射、共线性区间查询、基因 ID 跨库转换</td></tr>"
        "<tr><td><b>Expression 表达</b></td><td><code>/api/expression</code></td>"
        "<td>多物种、多项目的基因表达谱数据查询</td></tr>"
        "<tr><td><b>GeneHub</b></td><td><code>/api/genes</code></td>"
        "<td>基因标准细节与基因组浏览器链接</td></tr>"
        "<tr><td><b>Sequences 序列</b></td><td><code>/api/sequence</code></td>"
        "<td>基因及区间序列提取、预计算 BLAST 结果检索</td></tr>"
        "<tr><td><b>Blast</b></td><td><code>/api/blast</code></td>"
        "<td>序列比对搜索（blastn/blastp/blastx/tblastn/tblastx）</td></tr>"
        "<tr><td><b>Literature 文献</b></td><td><code>/api/literature</code></td>"
        "<td>文献标签统计与全文检索</td></tr>"
        "<tr><td><b>Tasks 任务</b></td><td><code>/api/tasks</code></td>"
        "<td>共线性图生成、SNP 引物设计等异步任务提交与结果获取</td></tr>"
        "</table>"

        "<h2>AI Agent 接入 (MCP)</h2>"
        "本服务内置 MCP (Model Context Protocol) 服务器，"
        "AI Agent 可通过标准化协议直接调用数据接口。"
        "SSE 端点: <code>GET /api/mcp/sse</code>，消息端点: <code>POST /api/mcp/messages</code>。"
        "详细说明见 <a href='https://wheatomics.sdau.edu.cn/V2/MCP-ServerUsage.html'>MCP 服务器文档</a>。"
    ),
    docs_url="/api/docs",           # 将 Swagger UI 移到 /api/docs
    redoc_url="/api/redoc",         # 将 ReDoc 移到 /api/redoc (可选)
    openapi_url="/api/openapi.json" # 将核心的 schema 文件移到 /api/openapi.json
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log request duration for diagnostics."""

    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    logger.info("%s %s %s %.3fs", request.method, request.url.path, response.status_code, elapsed)
    return response


@app.exception_handler(RequestValidationError)
async def request_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Return normalized request validation errors."""

    return JSONResponse(
        status_code=422,
        content={"success": False, "error": "Validation error", "detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception(_: Request, exc: Exception) -> JSONResponse:
    """Return normalized unhandled errors."""

    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "detail": str(exc) if settings.DEBUG else "An unexpected error occurred",
        },
    )


for router in [
    expression,
    coexpression,
    ppi,
    gene,
    genehub,
    comparative,
    sequence,
    literature,
    tasks,
    blast,
]:
    app.include_router(router, prefix=settings.API_PREFIX)




# # ==========================================
# # 初始化并配置 MCP 服务器
# # ==========================================
# mcp_server = Server("WheatOmics-MCP")

# MCP SSE Transport 初始化
sse_transport = SseServerTransport("/api/mcp/messages")

async def mcp_sse_endpoint(request: Request):
    """处理大模型客户端的 SSE 连接"""
    async with sse_transport.connect_sse(
        request.scope, 
        request.receive, 
        request._send
    ) as (read_stream, write_stream):
        await sequence_mcp_server.run(
            read_stream, 
            write_stream, 
            sequence_mcp_server.create_initialization_options()
        )

async def mcp_messages_endpoint(request: Request):
    """处理大模型客户端发来的 POST 消息 (Tool calls 等)"""
    await sse_transport.handle_post_message(
        request.scope, 
        request.receive, 
        request._send
    )

app.routes.append(Route("/api/mcp/sse", endpoint=mcp_sse_endpoint, methods=["GET"]))
app.routes.append(Route("/api/mcp/messages", endpoint=mcp_messages_endpoint, methods=["POST"]))

@app.get("/api/about")
async def root(request: Request) -> dict:
    """获取应用基本信息。

    功能:
        返回 WheatOmics API 的名称、版本号、交互式文档地址和 API 前缀。

    用法:
        GET /api/about
        无需任何参数，直接返回应用元信息 JSON。

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/about"

        响应:
          {
            "name": "WheatOmics",
            "version": "1.0.0",
            "docs": "/api/docs",
            "api_prefix": "/api",
            "server_time": "2025-06-18T10:30:00+00:00",
            "client_ip": "192.168.1.1"
          }
    """

    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/api/docs",
        "api_prefix": settings.API_PREFIX,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "client_ip": request.client.host if request.client else None,
    }


@app.get("/api/health")
async def health() -> dict:
    """服务健康检查。

    功能:
        返回服务运行状态，用于探活和监控。

    用法:
        GET /api/health
        无需任何参数，直接返回状态信息。

    案例:
        请求:
          curl -X GET "http://localhost:8000/api/health"

        响应:
          { "status": "Wheatomics API running, ..." }
    """

    return {"status": "Wheatomics API running, powered by Server.(Connect Email:zhaojiwen@yzwlab.cn)"}


def run_git_pull():
    """在后台执行 auto_pull.sh 脚本，拉取最新代码。"""

    try:
        result = subprocess.run(
            ["/bin/bash", str(settings.AUTO_PULL_SCRIPT)],
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info("Git Pull 成功: %s", result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error("Git Pull 失败: %s", e.stderr)


@app.post("/api/webhook/gitee")
async def gitee_webhook(request: Request, background_tasks: BackgroundTasks):
    """处理 Gitee Webhook 推送。

    验证 X-Gitee-Token 后，将 git pull 放入后台任务异步执行，
    立即返回响应以避免 Gitee 端请求超时。
    """

    token = request.headers.get("X-Gitee-Token")
    if token != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="身份验证失败：无效的 Webhook Token")

    payload = await request.json()
    logger.info("收到 Webhook 推送: ref=%s", payload.get("ref", "unknown"))

    background_tasks.add_task(run_git_pull)

    return {"status": "success", "message": "Webhook 已接收，代码拉取任务已在后台启动"}




