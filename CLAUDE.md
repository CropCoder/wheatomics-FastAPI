# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

WheatOmics API — the FastAPI backend for [wheatomics.sdau.edu.cn](https://wheatomics.sdau.edu.cn), a wheat multi-omics data integration platform. This is a refactored version of the original CGI backend (preserved in `cgi-py-RawScript/`). Python 3.10+, MySQL with raw SQL (no ORM), built-in MCP server for AI agent access, and a PrimerServer2 sub-app for PCR primer design.

## Commands

```bash
# Dev server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production (8 workers)
nohup gunicorn main:app -b 127.0.0.1:8000 -w 8 -k uvicorn.workers.UvicornWorker --reload > api.log 2>&1 &

# Restart on server (webhook only does git pull, does NOT restart)
pkill -f 'uvicorn main:app'
sleep 1
nohup /home/fei/mambaforge/envs/zjw/bin/uvicorn main:app --host 0.0.0.0 --port 8000 > api.log 2>&1 &

# Configure
cp .env.example .env   # edit DB credentials; see app/core/config.py for all vars
```

There is no `requirements.txt` or `pyproject.toml` in the repo.

**OpenAPI docs**: `/api/docs` (Swagger), `/api/redoc` (ReDoc), `/api/openapi.json` (schema).

## Architecture

```
main.py                          # App factory, middleware, router registration, 11 static mounts, MCP SSE wiring, webhook
app/
├── api/routers/                 # 12 route modules → 15 routers (gene.py exports 4)
├── core/
│   ├── config.py                # Pydantic Settings — single source of truth for all config
│   ├── exceptions.py            # ValidationFailure(400), ResourceNotFound(404), ExternalToolFailure(502)
│   ├── response.py              # ok(data, message) → {success, message, timestamp, data}
│   └── security.py              # Table allowlists + regex validators (ensure_gene_like, ensure_interval_like)
├── db/mysql.py                  # pymysql + DictCursor; context-managed mysql_cursor(database) committing on success
├── mcp/sequence_tools.py        # MCP Server("wheatomics") — 4 sequence tools via SSE (/api/mcp/sse, /api/mcp/messages)
├── primerserver2/               # Standalone FastAPI sub-app for PCR primer design (mounted at /api/PrimerServer2)
├── schemas/                     # Pydantic response models (gene, expression, sequence, comparative, etc.)
├── services/                    # command_runner (safe subprocess), legacy_parsers, expression_catalog, genome_examples
└── static/                      # 11 SPA frontends mounted at root paths (genes, expression, orthofinder, etc.)
```

## Key patterns

**Response format**: Every endpoint returns `ok(data)` from `app.core.response`, producing `{"success": true, "message": "ok", "timestamp": "...", "data": ...}`. Global exception handlers in `main.py` catch `RequestValidationError` (422) and unhandled `Exception` (500) with the same envelope.

**Database access**: All queries use raw SQL via `with mysql_cursor(settings.DB_XXX) as cursor:` — the context manager commits on success, rolls back on error. No connection pooling; connections are created/destroyed per call. 14 separate MySQL databases configured in `app/core/config.py`.

**Router registration**: Two-step — import router in `app/api/routers/__init__.py`, then add to the `for router in [...]` loop in `main.py` with `prefix=settings.API_PREFIX` (`/api`). The `include_router` call already prepends `/api`, so **do not** prefix endpoints in router files with `/api`.

**Avoid double prefixes**: When a router's own `prefix="..."` overlaps with endpoint paths, you get `/api/papers/papers` instead of `/api/papers`. Preferred pattern: set `router = APIRouter(prefix="", tags=["..."])` and write the full path in each `@router.get("/papers")`.

**Static frontend convention**: Each SPA in `app/static/<name>/` is mounted in `main.py` via `app.mount("/<name>", StaticFiles(...), html=True)`. Frontends must use hardcoded nav menus (not `fetch('/header.html')` — that file doesn't exist on the server). See MAINTENANCE.md §I for the full 4-step process of adding a new SPA.

**Styling conventions** (from MAINTENANCE.md §VII): Bootstrap 4.5.3 + jQuery 1.9.1, local assets only (no CDN). Each SPA has: `charset`, `viewport`, `<title>ModuleName - WheatOmics</title>`, `favicon.ico`, `bootstrap.css`, `jquery`. Do not override Bootstrap built-in classes (`.card-title`, `.btn-primary`, `.form-control`). Reference/citation blocks use plain `<h6>` without `card-title` class and must be in their own card (not nested inside result cards that get hidden).

**External tools**: Bioinfo tools (BLAST, primer3, samtools) are called via `app.services.command_runner.run_command()` — no shell, captured output, structured `ExternalToolFailure` on non-zero exit.

**MCP server**: Wraps 4 sequence-tool route functions as MCP tools. Errors are serialized as JSON text (not raised) so the LLM can adapt. Wired via SSE transport with raw `Route` objects in `main.py`.

**Webhook**: `POST /api/webhook/gitee` validates `X-Gitee-Token` header, then runs `auto_pull.sh` as a background task. It does **not** restart uvicorn — after a `git pull`, manual restart is required for Python changes to take effect.

**No tests or dependency file**: The repo has no `tests/` directory, no `requirements.txt`, and no `pyproject.toml`. Dependencies must be inferred from imports.

## Git workflow (for this contributor)

This repo is owned by `CropCoder`; the current contributor `tiantian-chen` has collaborator access. Push via `gh` OAuth token configured in the git remote:

```bash
git push origin main
```
