"""Backwards-compatibility shim for the original 4-tool MCP module.

The WheatOmics MCP server now lives in :mod:`app.mcp.wheatomics_tools` and
exposes the full platform tool catalog (see :mod:`app.mcp.tool_specs`).
This module only re-exports the server object so older imports keep working.
"""
from app.mcp.wheatomics_tools import SERVER_NAME, wheatomics_mcp_server

#: Legacy name kept for code that still imports ``sequence_mcp_server``.
sequence_mcp_server = wheatomics_mcp_server

__all__ = ["SERVER_NAME", "sequence_mcp_server", "wheatomics_mcp_server"]
