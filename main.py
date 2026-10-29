"""Main application entry point for the refactored WheatOmics FastAPI service."""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pathlib import Path
from fastapi.staticfiles import StaticFiles

from app.api.routers import comparative, expression, gene, genehub, pfam, interval, coexpression, ppi, sequence, blast_extra, triticeae, blast, orthofinder, track, go_kegg, varianthub, syntenyview, jbrowse, caps, eqtl, scrna, wheatpsp, genome, ptm
from app.api.routers.gene_write import router as gene_write
from app.api.routers.regulatory import router as regulatory_router
from app.api.routers.regulatory_integration import router as regulatory_integration_router
from app.api.routers.regulatory_tf_atlas import router as regulatory_tf_atlas_router
from app.core.config import settings
from app.mcp.sequence_tools import sequence_mcp_server
from app.primerserver2.dependencies import verify_api_key
from app.primerserver2.routers import config as ps2_config
from app.primerserver2.routers import jobs as ps2_jobs
from app.primerserver2.routers import results as ps2_results
from app.primerserver2.routers import server as ps2_server

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
    openapi_tags=[
        {
            "name": "PrimerServer2",
            "description": "Primer design, version 2",
        },
        {
            "name": "OrthoFinder",
            "description": "OrthoFinder orthogroup browser and search",
        },
    ],
    description=(
        "<h2>Overview</h2>"
        "WheatOmics is a global wheat multi-omics data integration and analysis platform "
        "covering genome, transcriptome, protein-protein interaction and literature data. "
        "This API is the platform's backend service; it follows RESTful design principles and "
        "provides structured data access for front-end applications and third-party tools."
        "<br><br>"
        "All endpoints are prefixed with <code>/api</code> and return JSON in a unified envelope: "
        "<pre>{\"success\": true, \"data\": { ... }}</pre>"

        "<h2>Modules</h2>"
        "<table>"
        "<tr><td><b>Known Genes</b></td><td><code>/api/genes/known</code></td>"
        "<td>Known-gene search and details</td></tr>"
        "<tr><td><b>PfamSearch</b></td><td><code>/api/genes/functions/pfam</code></td><td>Gene structural-domain search (gene family)</td></tr><tr><td><b>IntervalTool</b></td><td><code>/api/genes/functions/interval</code></td><td>Genes within a chromosome interval</td></tr><tr><td><b>Coexpression</b></td><td><code>/api/coexpression</code></td>"
        "<td>Co-expression network edge query and network-graph data</td></tr>"
        "<tr><td><b>Search Wheat Protein-Protein Interactions</b></td><td><code>/api/ppi</code></td>"
        "<td>Wheat protein-protein interactions (wheatPPI, CF-MS data)</td></tr>"
        "<tr><td><b>Comparative</b></td><td><code>/api/comparative</code></td>"
        "<td>Wheat-rice-Arabidopsis homolog mapping, synteny interval queries and cross-database gene ID conversion</td></tr>"
        "<tr><td><b>Expression</b></td><td><code>/api/expression</code></td>"
        "<td>Multi-species, multi-project gene expression profiles</td></tr>"
        "<tr><td><b>GeneHub</b></td><td><code>/api/genes/detail/{gene_id}</code></td>"
        "<td>GeneHub: normalized gene details (v1/v2/v3 ID mapping, protein properties, functional annotation)</td></tr>"
        "<tr><td><b>Sequences</b></td><td><code>/api/sequence</code></td>"
        "<td>Gene and interval sequence extraction, pre-computed BLAST hits</td></tr>"
        "<tr><td><b>Triticeae Papers</b></td><td><code>/api/papers</code></td><td>Triticeae literature filtering by gene, trait, confidence and AI tags</td></tr><tr><td><b>BLAST</b></td><td><code>/api/blast</code></td>"
        "<td>Sequence similarity search (blastn/blastp/blastx/tblastn/tblastx)</td></tr>"
        "<tr><td><b>OrthoFinder</b></td><td><code>/api/orthofinder</code></td><td>OrthoFinder orthogroup browser: cluster-filtered gene tree, synteny, MSA download</td></tr>"
"<tr><td><b>PrimerServer (SNP)</b></td><td><code>/api/tasks</code></td>"
        "<td>SNP primer design and specificity checks (PrimerServer replica)</td></tr>"
        "<tr><td><b>PrimerServer2</b></td><td><code>/api/PrimerServer2</code></td>"
        "<td>Batch PCR primer design and specificity checks (Primer design, version 2)</td></tr>"
        "<tr><td><b>GO/KEGG Enrichment</b></td><td><code>/api/go</code> / <code>/api/kegg</code></td>"
        "<td>GO/KEGG enrichment analysis: hypergeometric test with Benjamini-Hochberg FDR correction and bubble-plot visualization</td></tr>"
        "<tr><td><b>VariantHub</b></td><td><code>/api/VariantHub/query</code></td>"
        "<td>VCF variant queries across 26 population variation datasets grouped by genome (IWGSCv1.0 / IWGSCv2.1), with interval/variant-ID search and sample-subset filtering (bcftools)</td></tr>"
        "<tr><td><b>JBrowse</b></td><td><code>/api/jbrowse</code></td>"
        "<td>Genome browser dataset and track metadata (jbrowse_meta database; trackList.json is rebuilt by the API)</td></tr>"
        "<tr><td><b>CAPS/dCAPS</b></td><td><code>/api/caps</code></td>"
        "<td>CAPS/dCAPS primer design by SNP: enumeration of restriction enzymes and mismatch primers, with sequence/coordinate/VCF input modes</td></tr>"
        "<tr><td><b>eQTL Atlas</b></td><td><code>/api/eqtl/search</code></td>"
        "<td>Wheat eQTL atlas: eQTL records by gene and per-project FarmCPU Manhattan plots</td></tr>"
        "</table>"

        "<h2>AI Agent access (MCP)</h2>"
        "This service embeds an MCP (Model Context Protocol) server, so AI agents can call the data endpoints through a standardized protocol. "
        "SSE endpoint: <code>GET /api/mcp/sse</code>; message endpoint: <code>POST /api/mcp/messages</code>. "
        "See <a href='https://wheatomics.sdau.edu.cn/agent.html'>Agent &amp; API documentation</a> for details."
        "<br>For issues and feedback, please email: "
        "<a href='mailto:shengweima@icloud.com'>shengweima@icloud.com</a>."
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
# Compress large JSON responses (VariantHub /samples ~865 KB -> ~100 KB,
# VCF query payloads) — avoids Apache proxy buffering timeouts.
app.add_middleware(GZipMiddleware, minimum_size=1000)

@app.middleware("http")
async def no_cache_known_gene_assets(request: Request, call_next):
    """Force revalidation of the KnownGene SPA + v2 shell HTML/JS/CSS.

    StaticFiles only sends ETag/Last-Modified, so browsers may reuse a stale
    HTML/JS bundle by heuristic caching after a deploy (e.g. an old
    known_gene_common.js still truncating the protein-family chip).  Sending
    Cache-Control: no-cache makes normal reloads revalidate instead; the files
    are tiny, and hashed/static API payloads are not affected.
    """
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/api/v2shell/img/"):
        # versioned image URLs (shell.js appends ?v=...) can be cached for good
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.startswith(("/genes/", "/api/v2shell/")):
        ctype = response.headers.get("content-type", "")
        if ctype.startswith(("text/html", "text/css", "text/javascript", "application/javascript")):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


app.mount("/expression", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "expression", html=True), name="expression")
app.mount("/getfasta", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "getfasta", html=True), name="getfasta")
app.mount("/interval", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "interval", html=True), name="interval")
app.mount("/preblast", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "preblast", html=True), name="preblast")
app.mount("/wheatPPI", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "wheatPPI", html=True), name="wheatPPI")
app.mount("/orthofinder", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "orthofinder", html=True), name="orthofinder")
app.mount("/neighborhood", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "neighborhood", html=True), name="neighborhood")
app.mount("/HomologFinder", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "HomologFinder", html=True), name="HomologFinder")
app.mount("/PfamSearch", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "PfamSearch", html=True), name="PfamSearch")
app.mount("/idConvert", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "idConvert", html=True), name="idConvert")
app.mount("/sms2", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "sms2", html=True), name="sms2")
app.mount("/coexpression", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "coexpression", html=True), name="coexpression")
app.mount("/papers", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "papers", html=True), name="papers")
app.mount("/genes", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "genes", html=True), name="genes")
app.mount("/GO_KEGG", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "GO_KEGG", html=True), name="GO_KEGG")
app.mount("/VariantHub", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "VariantHub", html=True), name="VariantHub")
app.mount("/syntenyview", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "syntenyview", html=True), name="syntenyview")
app.mount("/caps", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "caps", html=True), name="caps")
app.mount("/eqtl", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "eqtl", html=True), name="eqtl")
app.mount("/scRNA", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "scRNA", html=True), name="scRNA")
app.mount("/wheatPSP", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "wheatPSP", html=True), name="wheatPSP")
app.mount("/wheatPTM", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "wheatPTM", html=True), name="wheatPTM")
# Shared WheatOmics 2.0 chrome (theme CSS + injected header/footer) used by
# the converted SPAs. Deliberately mounted under /api/ because Apache already
# proxies /api to the backend — a new top-level mount would need an extra
# ProxyPass rule. See scripts/extract_v2_shell.py and app/static/_v2/template.html.
app.mount("/api/v2shell", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "_v2"), name="v2shell")
# Built Vue SPA. The path must match base: '/PrimerServer2/' in the frontend's
# vite.config.js, which also bakes it into the asset URLs.
app.mount("/PrimerServer2", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "primerserver2", html=True), name="primerserver2")
app.mount("/regulatoryhub", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "regulatoryhub", html=True), name="regulatoryhub")


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
        content={"success": False, "error": "Validation error", "detail": jsonable_encoder(exc.errors())},
    )


@app.exception_handler(Exception)
async def unhandled_exception(_: Request, exc: Exception) -> JSONResponse:
    """Return normalized unhandled errors.

    ValidationFailure / ResourceNotFound / ExternalToolFailure are HTTPException
    subclasses and are handled by FastAPI's own HTTPException handler (higher
    MRO priority), so they keep their 400/404/502 status. This catch-all only
    sees genuinely unexpected errors. With DEBUG=False (default) the message
    is generic to avoid leaking DB/table/SQL fragments from pymysql errors.
    """

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
    pfam,
    interval,
    comparative,
    triticeae,
    sequence,
    blast_extra,
    blast,
    orthofinder,
    track,
    go_kegg,
    varianthub,
    syntenyview,
    jbrowse,
    caps,
    eqtl,
    scrna,
    wheatpsp,
    genome,
    ptm,
    gene_write,
]:
    app.include_router(router, prefix=settings.API_PREFIX)

# Wheat Regulatory Hub: motif atlas, candidate TFs, and VariantHub overlap
app.include_router(regulatory_router, prefix=settings.API_PREFIX)
app.include_router(regulatory_integration_router, prefix=settings.API_PREFIX)
# The TF Atlas router already includes /api in its prefix.
app.include_router(regulatory_tf_atlas_router)


# PrimerServer2 (original PCR primer design) - mounted under /api/PrimerServer2
PS2_PREFIX = f"{settings.API_PREFIX}/PrimerServer2"
app.include_router(ps2_config.router, prefix=PS2_PREFIX)
app.include_router(ps2_server.router, prefix=PS2_PREFIX)
app.include_router(ps2_jobs.router, prefix=PS2_PREFIX)
app.include_router(ps2_results.router, prefix=PS2_PREFIX, dependencies=[Depends(verify_api_key)])


# # ==========================================
# # 初始化并配置 MCP 服务器
# # ==========================================
# mcp_server = Server("WheatOmics-MCP")

# MCP SSE Transport 初始化
sse_transport = SseServerTransport("/api/mcp/messages")

async def mcp_sse_endpoint(request: Request):
    """Handle the SSE connection from an LLM client."""
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
    """Handle POST messages (tool calls, etc.) sent by an LLM client."""
    await sse_transport.handle_post_message(
        request.scope, 
        request.receive, 
        request._send
    )

app.routes.append(Route("/api/mcp/sse", endpoint=mcp_sse_endpoint, methods=["GET"]))
app.routes.append(Route("/api/mcp/messages", endpoint=mcp_messages_endpoint, methods=["POST"]))

@app.get("/api/about")
async def root(request: Request) -> dict:
    """Return basic application information.

    Purpose:
        Return the WheatOmics API name, version, interactive documentation URL and API prefix.

    Usage:
        GET /api/about
        No parameters; returns the application metadata JSON directly.

    Example:
        Request:
          curl -X GET "http://localhost:8000/api/about"

        Response:
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
    """Service health check.

    Purpose:
        Return the service status for liveness probes and monitoring.

    Usage:
        GET /api/health
        No parameters; returns the status information directly.

    Example:
        Request:
          curl -X GET "http://localhost:8000/api/health"

        Response:
          { "status": "Wheatomics API running, ..." }
    """

    return {"status": "Wheatomics API running, powered by Server."}


_git_pull_lock = threading.Lock()


def run_git_pull():
    """Run auto_pull.sh in the background to fetch the latest code.

    Serialized with a lock (two webhooks arriving back-to-back would otherwise
    run concurrent git fetch + reset --hard and corrupt .git) and capped at
    120s so a hung git fetch cannot hold a worker thread forever.
    Note: the script only performs git pull — Python changes still require a
    manual service restart.
    """

    if not _git_pull_lock.acquire(blocking=False):
        logger.info("Git Pull 跳过：上一次拉取仍在进行中")
        return
    try:
        result = subprocess.run(
            ["/bin/bash", str(settings.AUTO_PULL_SCRIPT)],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
        logger.info("Git Pull 成功: %s", result.stdout)
    except subprocess.TimeoutExpired:
        logger.error("Git Pull 超时（120s），已终止")
    except subprocess.CalledProcessError as e:
        logger.error("Git Pull 失败: %s", e.stderr)
    finally:
        _git_pull_lock.release()


@app.post("/api/webhook/gitee")
async def gitee_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle a Gitee webhook push.

    After validating the X-Gitee-Token header, run git pull as a background
    task and return immediately so the Gitee request does not time out.
    """

    token = request.headers.get("X-Gitee-Token")
    if not settings.WEBHOOK_SECRET:
        # Secret deliberately not hardcoded; set WEBHOOK_SECRET in .env.
        raise HTTPException(status_code=503, detail="Webhook 未配置：请在服务器 .env 设置 WEBHOOK_SECRET")
    if token != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="身份验证失败：无效的 Webhook Token")

    payload = await request.json()
    logger.info("收到 Webhook 推送: ref=%s", payload.get("ref", "unknown"))

    background_tasks.add_task(run_git_pull)

    return {"status": "success", "message": "Webhook 已接收，代码拉取任务已在后台启动"}




