import json
from mcp.server import Server
import mcp.types as types

# 导入你现有的路由函数
from app.api.routers.sequence import (
    sequence_by_gene,
    sequence_by_interval,
    batch_sequence,
    novabrowse_run
)

# 1. 初始化 MCP Server
sequence_mcp_server = Server("wheatomics")

# 2. 注册大模型可以使用的工具列表
@sequence_mcp_server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_sequence_by_gene",
            description="Retrieve wheat gene and protein FASTA records by gene ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "gene_id": {"type": "string", "description": "Target gene ID (e.g., TraesCS1A02G001000)"},
                    "gene_db": {"type": "string", "description": "Gene database name", "default": "all_gene"},
                    "protein_db": {"type": "string", "description": "Protein database name", "default": "all_protein"}
                },
                "required": ["gene_id"]
            }
        ),
        types.Tool(
            name="get_sequence_by_interval",
            description="Retrieve FASTA sequence by genomic interval using blastdbcmd.",
            inputSchema={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Genomic region in legacy format (e.g., chr1A:10-100)"},
                    "database": {"type": "string", "description": "Genome database name (must contain 'genome')"}
                },
                "required": ["region", "database"]
            }
        ),
        types.Tool(
            name="batch_sequence",
            description="Retrieve direct-entry FASTA for multiple gene IDs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "database": {"type": "string", "description": "Database name"},
                    "ids": {"type": "string", "description": "Space-separated string of gene identifiers"}
                },
                "required": ["database", "ids"]
            }
        ),
        types.Tool(
                "properties": {
                    "gene_id": {"type": "string", "description": "Target gene ID"},
                    "species_table": {"type": "string", "description": "Target species preblast table name"}
                },
                "required": ["gene_id", "species_table"]
            }
        ),
        types.Tool(
            name="run_novabrowse",
            description="Start the NovaBrowse workflow for a genomic region and return the generated result URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "chrom": {"type": "string", "description": "Chromosome name"},
                    "start": {"type": "integer", "description": "Start position (>=1)"},
                    "end": {"type": "integer", "description": "End position (must be > start)"}
                },
                "required": ["chrom", "start", "end"]
            }
        )
    ]

# 3. 处理大模型的工具调用请求
@sequence_mcp_server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        # 工具 1: 按基因 ID 查询
        if name == "get_sequence_by_gene":
            gene_id = arguments["gene_id"]
            gene_db = arguments.get("gene_db", "all_gene")
            protein_db = arguments.get("protein_db", "all_protein")
            
            # 直接调用现有的 FastAPI 函数，Python 会忽略 Query() 默认对象并使用我们传入的值
            result = sequence_by_gene(gene_id=gene_id, gene_db=gene_db, protein_db=protein_db)
            
            # 由于返回的是 Pydantic 模型 SequenceBundle，我们使用 model_dump_json() 序列化
            return [types.TextContent(type="text", text=result.model_dump_json())]

        # 工具 2: 按区间查询
        elif name == "get_sequence_by_interval":
            result = sequence_by_interval(
                region=arguments["region"],
                database=arguments["database"]
            )
            return [types.TextContent(type="text", text=json.dumps(result))]

        # 工具 3: 批量查询
        elif name == "batch_sequence":
            result = batch_sequence(
                database=arguments["database"],
                ids=arguments["ids"]
            )
            return [types.TextContent(type="text", text=json.dumps(result))]

        elif name == "run_novabrowse":
            result = novabrowse_run(
                chrom=arguments["chrom"],
                start=arguments["start"],
                end=arguments["end"]
            )
            return [types.TextContent(type="text", text=json.dumps(result))]

        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        # 捕获你代码中的 ResourceNotFound, ValidationFailure 或其他异常
        # 将异常信息作为正常文本返回给大模型，以便大模型根据错误信息自行调整重试
        return [
            types.TextContent(
                type="text", 
                text=json.dumps({"error": str(e), "status": "failed"})
            )
        ]