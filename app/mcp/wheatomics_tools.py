"""WheatOmics MCP server: tools, resources and prompts for AI agents.

The server exposes the platform's main read-only query capabilities as MCP
tools, plus two documentation resources and one copy-ready prompt, so an agent
can discover the data model without scraping the website:

* 28 tools covering genes/annotation, sequences, expression, networks,
  comparative genomics, eQTL, enrichment, literature, genomes, JBrowse and
  BLAST (see :mod:`app.mcp.tool_specs` for the full catalog);
* ``wheatomics://docs/modules`` — JSON module/tool catalog;
* ``wheatomics://docs/agent-guide`` — Markdown usage guide;
* prompt ``generate_wheatomics_skill`` — the "generate a data-query skill"
  prompt that is also shown on ``/agent.html#howto``.

Every tool wraps an existing FastAPI route handler, so the MCP surface and the
REST API can never drift in behaviour. Synchronous handlers run in a thread via
``asyncio.to_thread`` (DB / subprocess work must not block the event loop) with
a concurrency cap; the BLAST submit tool forces the asynchronous job mode and
returns a ``job_id`` for :func:`get_blast_status`.
"""
from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any, Callable

import mcp.types as types
from mcp.server import Server
from pydantic_core import PydanticUndefined

from app.api.routers.blast import blast_job_status, blast_search, list_databases
from app.api.routers.coexpression import query_coexpression
from app.api.routers.comparative import (
    convert_gene_ids,
    search_synteny,
    wheat_rice_arabidopsis_homologs,
)
from app.api.routers.eqtl import search_eqtl
from app.api.routers.expression import get_expression_projects, query_expression
from app.api.routers.gene import (
    get_gene_detail,
    get_known_gene,
    resolve_gene_id,
    search_gene_interval,
    search_known_genes,
    search_pfam,
)
from app.api.routers.genome import get_genome, list_genomes
from app.api.routers.go_kegg import EnrichmentRequest, go_enrichment, kegg_enrichment
from app.api.routers.jbrowse import list_jbrowse_datasets
from app.api.routers.ppi import query_ppi
from app.api.routers.sequence import batch_sequence, sequence_by_gene, sequence_by_interval
from app.api.routers.triticeae import get_paper, search_papers
from app.mcp.tool_specs import (
    AGENT_PROMPT,
    MODULE_CATALOG,
    RESOURCE_SPECS,
    TOOL_GROUPS,
    TOOL_SPECS,
)
from app.services.caps_designer import design_caps_dcaps

try:  # mcp >= 1.x ships the helper; keep a graceful fallback for older SDKs.
    from mcp.server.lowlevel.helper_types import ReadResourceContents
except Exception:  # pragma: no cover - only for very old mcp versions
    ReadResourceContents = None  # type: ignore[assignment]

#: Server name advertised to MCP clients.
SERVER_NAME = "wheatomics"

wheatomics_mcp_server = Server(SERVER_NAME)

# Subprocess-heavy tools (blastdbcmd / primer design / BLAST submit) share a
# small semaphore: a burst of agent calls must not fork unbounded processes
# across the 8 gunicorn workers.
_HEAVY_SEMAPHORE = asyncio.Semaphore(4)
# DB / HTTP-bound tools can run a bit more in parallel; each worker caps at 8.
_GENERAL_SEMAPHORE = asyncio.Semaphore(8)

_HEAVY_TOOLS = {
    "get_sequence_by_gene",
    "get_sequence_by_interval",
    "batch_sequence",
    "design_caps_primers",
    "submit_blast",
}


# ---------------------------------------------------------------------------
# Tool dispatch table: every tool calls an existing FastAPI route handler.
# ---------------------------------------------------------------------------
_SYNC_TOOLS: dict[str, tuple[Callable[..., Any], dict[str, Any]]] = {
    # sequences & primers
    "get_sequence_by_gene": (sequence_by_gene, {}),
    "get_sequence_by_interval": (sequence_by_interval, {}),
    "batch_sequence": (batch_sequence, {}),
    "design_caps_primers": (design_caps_dcaps, {"mismatch_max": 1, "top_n": 10}),
    # genes & annotation
    "search_known_genes": (search_known_genes, {"field": "all", "limit": 20, "offset": 0}),
    "get_known_gene": (get_known_gene, {}),
    "get_gene_detail": (get_gene_detail, {}),
    "resolve_gene_id": (resolve_gene_id, {}),
    "search_pfam": (search_pfam, {"table": "Genefunc_CS_IWGSC03G_table"}),
    "genes_in_interval": (search_gene_interval, {"table": "Genefunc_CS_IWGSC03G_table"}),
    # expression & networks
    "list_expression_projects": (get_expression_projects, {}),
    "query_expression": (query_expression, {"project": "PRJEB5314_paired_tbl"}),
    "query_coexpression": (query_coexpression, {"database": "CO_PRJEB25639", "filter_value": 300}),
    "query_ppi": (query_ppi, {"table": "PPI_result", "min_score": 0.5}),
    # comparative & variation
    "find_homologs": (wheat_rice_arabidopsis_homologs, {"max_targets": 3}),
    "search_synteny": (search_synteny, {"table": "CSsymaptbl"}),
    "convert_gene_ids": (convert_gene_ids, {}),
    "search_eqtl": (search_eqtl, {}),
    # literature
    "search_papers": (search_papers, {"limit": 20, "offset": 0}),
    "get_paper": (get_paper, {}),
    # genomes / JBrowse
    "list_genomes": (list_genomes, {"include_hidden": False, "limit": 100, "offset": 0}),
    "get_genome": (get_genome, {}),
    "list_jbrowse_datasets": (list_jbrowse_datasets, {}),
    # BLAST read side (the submit side is async, handled separately)
    "get_blast_status": (blast_job_status, {}),
    "list_blast_databases": (list_databases, {}),
}

_ASYNC_TOOLS: dict[str, tuple[Callable[..., Any], dict[str, Any]]] = {
    # BLAST is always submitted as an asynchronous job; poll get_blast_status.
    "submit_blast": (blast_search, {"wait": False, "program": "blastp", "evalue": 10.0,
                                          "max_targets": 1000, "outfmt": "tabular"}),
}

#: ``submit_blast`` tool argument -> ``blast_search`` route parameter.
_BLAST_ARG_MAP = {"max_target_seqs": "max_targets"}


def _plain_default(value: Any) -> Any:
    """Return the plain Python default behind a FastAPI ``Query``/``Form``."""
    default = getattr(value, "default", value)
    return default


def _build_kwargs(fn: Callable[..., Any], arguments: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """Build the full keyword dict for a FastAPI handler called outside HTTP.

    FastAPI route functions declare ``Query(...)`` / ``Form(...)`` sentinels as
    parameter defaults; calling them directly would pass those objects into the
    function body, so every parameter must be supplied with a plain value.
    """
    kwargs: dict[str, Any] = {}
    for param in inspect.signature(fn).parameters.values():
        value = arguments.get(param.name)
        if value is None:
            value = extra.get(param.name)
        if value is not None:
            kwargs[param.name] = value
            continue
        if param.default is inspect.Parameter.empty:
            raise ValueError(f"missing required argument: {param.name}")
        default = _plain_default(param.default)
        if default is PydanticUndefined:
            raise ValueError(f"missing required argument: {param.name}")
        kwargs[param.name] = default
    return kwargs


def _as_text(result: Any) -> str:
    """Serialize a route-handler result into MCP text content."""
    if hasattr(result, "model_dump_json"):
        return result.model_dump_json()
    if isinstance(result, (dict, list)):
        return json.dumps(result, ensure_ascii=False, default=str)
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)


async def _run_tool(name: str, arguments: dict[str, Any]) -> Any:
    if name == "go_enrichment":
        request = EnrichmentRequest(
            genes=[str(g) for g in (arguments.get("genes") or [])],
            padj_threshold=float(arguments.get("padj_threshold", 0.05)),
        )
        return await asyncio.to_thread(go_enrichment, request)

    if name == "kegg_enrichment":
        request = EnrichmentRequest(
            genes=[str(g) for g in (arguments.get("genes") or [])],
            padj_threshold=float(arguments.get("padj_threshold", 0.05)),
        )
        return await asyncio.to_thread(kegg_enrichment, request)

    if name in _ASYNC_TOOLS:
        fn, extra = _ASYNC_TOOLS[name]
        mapped = {_BLAST_ARG_MAP.get(key, key): value for key, value in arguments.items()}
        kwargs = _build_kwargs(fn, mapped, extra)
        kwargs["wait"] = False
        return await fn(**kwargs)

    if name in _SYNC_TOOLS:
        fn, extra = _SYNC_TOOLS[name]
        kwargs = _build_kwargs(fn, arguments, extra)
        # Some route handlers are async even though they do trivial work
        # (e.g. blast_job_status / list_databases); awaiting is both correct
        # and cheaper than a thread hop. Everything else is blocking DB or
        # subprocess work and belongs in a thread.
        if inspect.iscoroutinefunction(fn):
            return await fn(**kwargs)
        return await asyncio.to_thread(lambda: fn(**kwargs))

    raise ValueError(f"Unknown tool: {name}")


#: Compact views for the two tools whose raw REST payload is too large to put
#: into an agent context (expression projects ~600 KB, BLAST databases ~600 KB).
def _compact_expression_projects(result: dict, include_details: bool) -> dict:
    if include_details:
        return result
    data = result.get("data", {})
    projects = data.get("projects", []) if isinstance(data, dict) else []
    compact = [
        {
            "id": project.get("id"),
            "description": project.get("description"),
            "categories": project.get("categories"),
            "group": project.get("group"),
            "subgroup": project.get("subgroup"),
        }
        for project in projects
    ]
    return {
        "success": result.get("success", True),
        "count": len(compact),
        "projects": compact,
        "hint": "Compact catalog. Use include_details=true or GET /api/expression/projects for citations and the nested group tree.",
    }


def _compact_blast_databases(
    result: dict, include_databases: bool, include_metadata: bool
) -> dict:
    if include_metadata:
        return result
    protein = result.get("protein", {}) or {}
    nucleotide = result.get("nucleotide", {}) or {}
    protein_dbs = protein.get("databases", []) or []
    nucleotide_dbs = nucleotide.get("databases", []) or []
    categories = [
        {
            "id": category.get("id"),
            "label": category.get("label"),
            "description": category.get("description"),
            "count": category.get("count"),
        }
        for category in (result.get("categories", []) or [])
    ]
    compact = {
        "success": result.get("success", True),
        "program": result.get("program"),
        "total": result.get("total"),
        "kind_counts": result.get("kind_counts"),
        "protein": {"count": protein.get("count"), "databases": protein_dbs},
        "nucleotide": {
            "count": nucleotide.get("count"),
            "databases": nucleotide_dbs if include_databases else nucleotide_dbs[:80],
        },
        "categories": categories,
        "hint": (
            "Compact summary: all protein database names plus a sample of nucleotide names. "
            "Use include_databases=true for every name, include_metadata=true for per-database metadata, "
            "or call with program=blastn/blastp to narrow the list."
        ),
    }
    return compact


# ---------------------------------------------------------------------------
# MCP protocol handlers
# ---------------------------------------------------------------------------
@wheatomics_mcp_server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Advertise every registered tool (catalog lives in app.mcp.tool_specs)."""
    return [
        types.Tool(
            name=spec["name"],
            description=spec["description"],
            inputSchema=spec["inputSchema"],
        )
        for spec in TOOL_SPECS
    ]


@wheatomics_mcp_server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    """Execute one tool call and return its JSON result as text.

    Errors are returned as JSON text (not raised) so the model can read the
    message and retry with better arguments.
    """
    arguments = arguments or {}
    semaphore = _HEAVY_SEMAPHORE if name in _HEAVY_TOOLS else _GENERAL_SEMAPHORE
    try:
        async with semaphore:
            result = await _run_tool(name, arguments)
        if name == "list_expression_projects":
            result = _compact_expression_projects(result, bool(arguments.get("include_details", False)))
        elif name == "list_blast_databases":
            result = _compact_blast_databases(
                result,
                bool(arguments.get("include_databases", False)),
                bool(arguments.get("include_metadata", False)),
            )
        return [types.TextContent(type="text", text=_as_text(result))]
    except Exception as exc:  # noqa: BLE001 - MCP protocol wants text errors
        return [
            types.TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": str(exc),
                        "status": "failed",
                        "tool": name,
                        "support": "If the problem persists, please report it by email to shengweima@icloud.com",
                    },
                    ensure_ascii=False,
                ),
            )
        ]


def _modules_resource() -> str:
    payload = {
        "platform": "WheatOmics 2.0",
        "docs": {
            "agent_page": "https://wheatomics.sdau.edu.cn/agent.html",
            "agent_howto": "https://wheatomics.sdau.edu.cn/agent.html#howto",
            "swagger": "https://wheatomics.sdau.edu.cn/api/docs",
            "openapi": "https://wheatomics.sdau.edu.cn/api/openapi.json",
            "mcp_sse": "https://wheatomics.sdau.edu.cn/api/mcp/sse",
        },
        "modules": MODULE_CATALOG,
        "tool_groups": [
            {
                "group": group["name"],
                "tools": [{"name": tool["name"], "description": tool["description"]} for tool in group["tools"]],
            }
            for group in TOOL_GROUPS
        ],
        "tool_count": len(TOOL_SPECS),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _agent_guide_resource() -> str:
    lines = [
        "# WheatOmics agent guide",
        "",
        "WheatOmics is an agent-ready wheat multi-omics platform.",
        "",
        "## Endpoints",
        "",
        "- MCP server (SSE): `https://wheatomics.sdau.edu.cn/api/mcp/sse` (messages: `/api/mcp/messages`)",
        "- REST API base: `https://wheatomics.sdau.edu.cn/api`",
        "- Swagger UI: `https://wheatomics.sdau.edu.cn/api/docs`",
        "- ReDoc: `https://wheatomics.sdau.edu.cn/api/redoc`",
        "- OpenAPI schema: `https://wheatomics.sdau.edu.cn/api/openapi.json`",
        "",
        "## Available MCP tools",
        "",
    ]
    for group in TOOL_GROUPS:
        lines.append(f"### {group['name']}")
        lines.append("")
        for tool in group["tools"]:
            lines.append(f"- `{tool['name']}` — {tool['description']}")
        lines.append("")
    lines += [
        "## Mandatory verification rule",
        "",
        "Whenever an answer involves a specific gene ID, pathway ID (GO/KEGG) or cited reference "
        "(PMID/DOI), call the corresponding tool or REST endpoint to verify it in real time. "
        "Never rely on memory or guesswork; anything not returned by an actual API response must "
        "not be stated as fact.",
        "",
        "## Result persistence convention",
        "",
        "When a query produces results the user may cite or reproduce later (gene details, expression "
        "profiles, BLAST hits, enrichment results, literature, ...), write them to local files "
        "(JSON / Markdown report) by default. With the optional `wheatomics.py` helper use "
        "`wheatomics.py ... -o <file>` and keep outputs in a dedicated directory such as "
        "`./wheatomics_results/`.",
        "",
        "## Copy-ready prompt (generate a reusable data-query skill)",
        "",
        "```text",
        AGENT_PROMPT,
        "```",
        "",
    ]
    return "\n".join(lines)


@wheatomics_mcp_server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    return [
        types.Resource(
            uri=spec["uri"],
            name=spec["name"],
            description=spec["description"],
            mimeType=spec["mimeType"],
        )
        for spec in RESOURCE_SPECS
    ]


@wheatomics_mcp_server.read_resource()
async def handle_read_resource(uri):
    uri_text = str(uri)
    if uri_text == "wheatomics://docs/modules":
        text, mime = _modules_resource(), "application/json"
    elif uri_text == "wheatomics://docs/agent-guide":
        text, mime = _agent_guide_resource(), "text/markdown"
    else:
        raise ValueError(f"Unknown resource: {uri_text}")
    if ReadResourceContents is not None:
        return [ReadResourceContents(content=text, mime_type=mime)]
    return text


@wheatomics_mcp_server.list_prompts()
async def handle_list_prompts() -> list[types.Prompt]:
    return [
        types.Prompt(
            name="generate_wheatomics_skill",
            title="Generate a WheatOmics data-query skill",
            description=(
                "Copy-ready prompt: ask an AI agent to read the WheatOmics OpenAPI docs and generate a "
                "reusable data-query skill with live-verification and result-persistence rules."
            ),
            arguments=[],
        )
    ]


@wheatomics_mcp_server.get_prompt()
async def handle_get_prompt(name: str, arguments: dict[str, str] | None) -> types.GetPromptResult:
    if name != "generate_wheatomics_skill":
        raise ValueError(f"Unknown prompt: {name}")
    return types.GetPromptResult(
        description="Generate a reusable WheatOmics data-query skill from the live OpenAPI schema.",
        messages=[
            types.PromptMessage(
                role="user",
                content=types.TextContent(type="text", text=AGENT_PROMPT),
            )
        ],
    )
