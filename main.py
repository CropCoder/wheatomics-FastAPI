"""Main application entry point for the refactored WheatOmics FastAPI service."""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import comparative, expression, gene, literature, network, sequence, tasks
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
        "WheatOmics 小麦多组学数据平台后端 API，提供基因搜索、表达谱查询、"
        "共表达网络、PPI 互作、序列检索、比较基因组学及文献查询等数据服务。"
        "<br><br>"
        "<b>使用方法</b>：通过下方各接口分组浏览可用端点，点击 «Try it out» 在线调试；"
        "也可在 <a href='/api/redoc'>ReDoc</a> 查看完整文档。"
        "<br>"
        "生产环境请将请求发送至 <code>https://wheatomics.sdau.edu.cn/api</code>。"
        "<br>"
        "MCP 使用说明详见 "
        "<a href='https://wheatomics.sdau.edu.cn/V2/MCP-ServerUsage.html'>MCP 服务器文档</a>。"
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
    network,
    gene,
    comparative,
    sequence,
    literature,
    tasks,
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
async def root() -> dict:
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
            "api_prefix": "/api"
          }
    """

    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/api/docs",
        "api_prefix": settings.API_PREFIX
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




