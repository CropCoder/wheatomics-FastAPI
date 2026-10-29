#!/usr/bin/env python3
"""Self-test for the WheatOmics MCP server.

Two modes:

1. In-process (default) — imports the server module, lists tools/resources/
   prompts and calls a few read-only tools with known-good arguments. Needs the
   full runtime environment (on the server: conda env ``zjw``)::

       /home/fei/mambaforge/envs/zjw/bin/python3 scripts/mcp_selftest.py

2. Live MCP client — connects to a running server, performs the MCP handshake
   and calls ``tools/list`` / ``tools/call`` / the two resources::

       # recommended: stateless Streamable HTTP (multi-worker safe)
       python3 scripts/mcp_selftest.py --live-http http://127.0.0.1:8000/api/mcp
       # legacy SSE transport (single-worker/dev only)
       python3 scripts/mcp_selftest.py --live http://127.0.0.1:8000/api/mcp/sse

Exit code 0 = PASS, 1 = failures, 2 = could not run (missing deps / server).
The BLAST submission tool is opt-in (``--include-blast``) because it queues a
real job; when enabled the test submits a tiny query, polls the job and deletes
it again.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Allow `python3 scripts/mcp_selftest.py` to import the repo's `app` package.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _ok(label: str, extra: str = "") -> None:
    print(f"  [PASS] {label}{(' — ' + extra) if extra else ''}")


def _fail(label: str, extra: str = "") -> None:
    print(f"  [FAIL] {label}{(' — ' + extra) if extra else ''}")


async def in_process(include_blast: bool) -> int:
    from app.mcp import wheatomics_tools as wt

    failures = 0
    tools = await wt.handle_list_tools()
    names = [tool.name for tool in tools]
    expected = [spec["name"] for spec in wt.TOOL_SPECS]
    print(f"[in-process] tools advertised: {len(tools)}")
    if len(tools) != 28:
        _fail("tool count", f"expected 28, got {len(tools)}")
        failures += 1
    else:
        _ok("tool count", "28")
    if names != expected:
        _fail("tool catalog order/names", "mismatch with tool_specs.py")
        failures += 1
    else:
        _ok("tool names match tool_specs.py")

    schema_errors = [t.name for t in tools if not t.inputSchema.get("properties") and t.inputSchema.get("required")]
    if schema_errors:
        _fail("input schemas", str(schema_errors))
        failures += 1
    else:
        _ok("input schemas present")

    resources = await wt.handle_list_resources()
    uris = sorted(str(r.uri) for r in resources)
    if uris == ["wheatomics://docs/agent-guide", "wheatomics://docs/modules"]:
        _ok("resources", ", ".join(uris))
    else:
        _fail("resources", str(uris))
        failures += 1
    for uri in uris:
        text = await wt.handle_read_resource(uri)
        payload = text[0].content if isinstance(text, list) else text
        if payload and len(payload) > 100:
            _ok(f"resource {uri}", f"{len(payload)} chars")
        else:
            _fail(f"resource {uri}", "empty content")
            failures += 1

    prompts = await wt.handle_list_prompts()
    if any(p.name == "generate_wheatomics_skill" for p in prompts):
        result = await wt.handle_get_prompt("generate_wheatomics_skill", {})
        text = result.messages[0].content.text
        if "WheatOmics Data Query" in text:
            _ok("prompt generate_wheatomics_skill", f"{len(text)} chars")
        else:
            _fail("prompt content", "unexpected text")
            failures += 1
    else:
        _fail("prompt missing")
        failures += 1

    async def call(name: str, arguments: dict, expect_error: bool = False) -> str:
        result = await wt.handle_call_tool(name, arguments)
        text = result[0].text
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if expect_error:
            ok = isinstance(parsed, dict) and parsed.get("status") == "failed"
        else:
            ok = isinstance(parsed, (dict, list)) and not (
                isinstance(parsed, dict) and parsed.get("success") is False
            )
        if ok:
            _ok(f"call {name}", f"{len(text)} chars")
        else:
            _fail(f"call {name}", text[:160])
            return text
        return text

    samples = [
        ("get_gene_detail", {"gene_id": "TraesCS1A02G001000"}),
        ("search_known_genes", {"search": "TaCRT", "limit": 2}),
        ("list_expression_projects", {}),
        ("query_expression", {"gene_ids": "TraesCS1A02G001000"}),
        ("query_coexpression", {"gene_ids": "TraesCS1A02G001000"}),
        ("find_homologs", {"gene_id": "TraesCS1A02G001000"}),
        ("search_eqtl", {"gene": "TraesCS1A02G001000"}),
        ("list_genomes", {"limit": 2}),
        ("list_jbrowse_datasets", {}),
        ("list_blast_databases", {"program": "blastp"}),
        ("get_blast_status", {"job_id": "00000000-0000-4000-8000-000000000000"}, True),
    ]
    for name, args, *rest in samples:
        await call(name, args, bool(rest and rest[0]))

    # Large list tools must return a compact view by default (agent context safety).
    expr_text = (await wt.handle_call_tool("list_expression_projects", {}))[0].text
    if len(expr_text) < 80_000 and '"projects"' in expr_text:
        _ok("compact list_expression_projects", f"{len(expr_text)} chars")
    else:
        _fail("compact list_expression_projects", f"{len(expr_text)} chars")
        failures += 1
    blast_text = (await wt.handle_call_tool("list_blast_databases", {}))[0].text
    if len(blast_text) < 50_000 and '"protein"' in blast_text:
        _ok("compact list_blast_databases", f"{len(blast_text)} chars")
    else:
        _fail("compact list_blast_databases", f"{len(blast_text)} chars")
        failures += 1
    blast_all = (await wt.handle_call_tool("list_blast_databases", {"include_databases": True}))[0].text
    if len(blast_all) > len(blast_text):
        _ok("list_blast_databases include_databases", f"{len(blast_all)} chars")
    else:
        _fail("list_blast_databases include_databases", f"{len(blast_all)} chars")
        failures += 1

    if include_blast:
        from app.api.routers.blast import delete_blast_job

        catalog = json.loads(
            (await wt.handle_call_tool("list_blast_databases", {"program": "blastp"}))[0].text
        )
        protein_dbs = (catalog.get("protein") or {}).get("databases") or []
        # Pick a real database from the live catalog; prefer plain protein entries.
        database = next(
            (name for name in protein_dbs if "protein" in name.lower() or "pep" in name.lower()),
            protein_dbs[0] if protein_dbs else None,
        )
        if not database:
            _fail("call submit_blast", "no protein BLAST database available")
            failures += 1
            return 1 if failures else 0
        _ok("blast database for self-test", database)
        submitted = await wt.handle_call_tool(
            "submit_blast",
            {
                "program": "blastp",
                "database": database,
                "query": ">selftest\nMSSSTGAVTSGIKK",
                "evalue": 10,
                "max_target_seqs": 5,
            },
        )
        payload = json.loads(submitted[0].text)
        job_id = payload.get("job_id")
        if job_id:
            _ok("call submit_blast", f"job_id={job_id}")
            final = None
            for _ in range(30):
                await asyncio.sleep(3)
                status = json.loads((await wt.handle_call_tool("get_blast_status", {"job_id": job_id}))[0].text)
                final = status.get("status")
                if final in {"done", "error", "stale"}:
                    _ok("get_blast_status", str(final))
                    break
            try:
                await delete_blast_job(job_id)
                _ok("cleanup BLAST job", job_id)
            except Exception as exc:  # noqa: BLE001 - cleanup is best-effort
                _ok("cleanup BLAST job skipped", str(exc))
        else:
            _fail("call submit_blast", submitted[0].text[:160])
            failures += 1

    return 1 if failures else 0


async def _verify_session(session, label: str) -> int:
    """Run the shared MCP client assertions against an initialized session."""
    failures = 0
    tools = await session.list_tools()
    names = [tool.name for tool in tools.tools]
    print(f"[{label}] tools advertised: {len(names)}")
    if len(names) >= 20:
        _ok("tools/list", f"{len(names)} tools")
    else:
        _fail("tools/list", f"only {len(names)} tools")
        failures += 1
    expected = {
        "get_sequence_by_gene", "get_gene_detail", "search_known_genes", "query_expression",
        "query_coexpression", "query_ppi", "find_homologs", "search_synteny", "convert_gene_ids",
        "search_eqtl", "go_enrichment", "kegg_enrichment", "search_papers", "get_paper",
        "list_genomes", "get_genome", "list_jbrowse_datasets", "submit_blast", "get_blast_status",
        "list_blast_databases", "design_caps_primers",
    }
    missing = sorted(expected - set(names))
    if missing:
        _fail("expected tools present", ", ".join(missing))
        failures += 1
    else:
        _ok("expected tools present", f"{len(expected)} core tools")

    result = await session.call_tool("get_gene_detail", {"gene_id": "TraesCS1A02G001000"})
    text = result.content[0].text if result.content else ""
    if "TraesCS1A02G001000" in text:
        _ok("tools/call get_gene_detail", f"{len(text)} chars")
    else:
        _fail("tools/call get_gene_detail", text[:160])
        failures += 1

    resources = await session.list_resources()
    if len(resources.resources) == 2:
        _ok("resources/list", "2 resources")
        read = await session.read_resource("wheatomics://docs/modules")
        if read.contents and len(read.contents[0].text) > 100:
            _ok("resources/read wheatomics://docs/modules")
        else:
            _fail("resources/read", "empty")
            failures += 1
    else:
        _fail("resources/list", str(len(resources.resources)))
        failures += 1

    prompts = await session.list_prompts()
    if any(p.name == "generate_wheatomics_skill" for p in prompts.prompts):
        _ok("prompts/list", "generate_wheatomics_skill")
    else:
        _fail("prompts/list", "prompt missing")
        failures += 1
    return 1 if failures else 0


async def live_http(url: str) -> int:
    """Verify the recommended stateless Streamable HTTP transport."""
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except Exception as exc:  # pragma: no cover - depends on environment
        print(f"[live-http] mcp client unavailable: {exc}")
        return 2
    async with streamablehttp_client(url) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await _verify_session(session, "live-http")


async def live(url: str) -> int:
    """Verify the legacy SSE transport (single-worker/dev only)."""
    try:
        from mcp import ClientSession
        from mcp.client.sse import sse_client
    except Exception as exc:  # pragma: no cover - depends on environment
        print(f"[live] mcp client unavailable: {exc}")
        return 2
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await _verify_session(session, "live-sse")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live-http",
        metavar="URL",
        help="connect to a running MCP Streamable HTTP endpoint (e.g. http://127.0.0.1:8000/api/mcp)",
    )
    parser.add_argument("--live", metavar="SSE_URL", help="connect to a legacy MCP SSE endpoint")
    parser.add_argument("--include-blast", action="store_true", help="also submit a tiny BLAST job")
    args = parser.parse_args()
    if args.live_http:
        return asyncio.run(live_http(args.live_http))
    if args.live:
        return asyncio.run(live(args.live))
    return asyncio.run(in_process(args.include_blast))


if __name__ == "__main__":
    raise SystemExit(main())
