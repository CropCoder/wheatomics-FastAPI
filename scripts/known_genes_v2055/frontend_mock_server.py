#!/usr/bin/env python3
"""Local mock server for the KnownGene frontend (task-5 verification only).

Why this exists
---------------
The v2056 KnownGene API (``app/api/routers/gene.py``) needs the production
MySQL database, which is not available in this workspace.  To validate
``app/static/genes/index.html`` / ``detail.html`` end-to-end we serve:

  * the real page files from ``app/static/genes/``;
  * the real ``_v2`` shell from ``app/static/_v2/``;
  * ``/api/genes/known/{all,search,stats,<id>}`` assembled from the frozen
    fixtures in ``scripts/known_genes_v2055/out/api_fixtures/`` — these are the
    final response shapes the backend implements;
  * the Bootstrap 4.5.3 / jQuery 1.9.1 / favicon / V2.0 image assets, which
    live in the production docroot (not in this repository).  They are cached
    under ``/tmp/kg_assets`` (or ``--asset-cache``); on a cache miss the server
    tries a short read-only download from https://wheatomics.sdau.edu.cn and
    falls back to harmless stubs so the layout check can still run.

The mock implements the same contract the backend does (``limit``/``offset``,
``field`` whitelist, ``total`` semantics) so pagination/search/export can be
exercised locally.

Usage
-----
    python3 scripts/known_genes_v2055/frontend_mock_server.py --port 8100
    # then open http://127.0.0.1:8100/genes/

This file is a local verification helper; it is never imported by the app.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import mimetypes
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TASK_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURE_DIR = os.path.join(TASK_ROOT, "scripts", "known_genes_v2055", "out", "api_fixtures")
STATIC_GENES = os.path.join(TASK_ROOT, "app", "static", "genes")
STATIC_V2 = os.path.join(TASK_ROOT, "app", "static", "_v2")
DEFAULT_ASSET_CACHE = os.path.join("/tmp", "kg_assets")
PRODUCTION_ORIGIN = "https://wheatomics.sdau.edu.cn"

# Fields a summary search term is matched against (mirrors backend whitelist).
SEARCH_FIELDS: dict[str, tuple[str, ...]] = {
    "all": (
        "gene_id",
        "gene_name",
        "reference_genome_id",
        "chrom_pos",
        "phenotype",
        "phenotype_brief",
        "species",
        "species_primary",
        "doi",
        "protein_family",
        "functional_category",
        "research_strategy",
        "publication_years",
    ),
    "gene_id": ("gene_id",),
    "gene_name": ("gene_name",),
    "reference_genome_id": ("reference_genome_id",),
    "phenotype": ("phenotype", "phenotype_brief"),
    "species": ("species", "species_primary"),
    "doi": ("doi",),
    "protein_family": ("protein_family",),
    "functional_category": ("functional_category",),
    "research_strategy": ("research_strategy",),
    "chrom_pos": ("chrom_pos", "chromosome"),
}

# A 1x1 transparent PNG used when a production image cannot be fetched.
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000d49444154789c626001000000ffff03000006000557"
    "bfabd40000000049454e44ae426082"
)


# ---------------------------------------------------------------------------
# Fixture data (loaded once)
# ---------------------------------------------------------------------------
class Fixtures:
    def __init__(self) -> None:
        self.all_payload = self._read_json("known_all.json")
        self.stats_payload = self._read_json("known_stats.json")
        self.summaries: list[dict] = list(self.all_payload["data"]["records"])
        self.summary_by_clone = {int(r["clone_id"]): r for r in self.summaries}
        self.details: dict[int, dict] = {}
        for name in sorted(os.listdir(FIXTURE_DIR)):
            if not (name.startswith("known_detail_") and name.endswith(".json")):
                continue
            payload = self._read_json(name)
            record = payload["data"]
            self.details[int(record["clone_id"])] = record

    @staticmethod
    def _read_json(name: str) -> dict:
        path = os.path.join(FIXTURE_DIR, name)
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def detail_for(self, key: str) -> dict | None:
        """Resolve ``id`` the way the backend does: clone_id, gene_id, gene_name."""
        if key.isdigit():
            clone_id = int(key)
            if clone_id in self.details:
                return self.details[clone_id]
            summary = self.summary_by_clone.get(clone_id)
            return self._synthesize_detail(summary) if summary else None
        for record in self.details.values():
            if key in (record.get("gene_id"), record.get("gene_name")):
                return record
        for summary in self.summaries:
            if key in (summary.get("gene_id"), summary.get("gene_name")):
                return self._synthesize_detail(summary)
        return None

    @staticmethod
    def _synthesize_detail(summary: dict | None) -> dict | None:
        """Detail row for a summary that has no hand-checked fixture.

        The real API returns the curated row with long-text columns; the mock
        only has summaries for most rows, so long fields stay empty and the
        detail page exercises its empty-value hiding paths.
        """
        if not summary:
            return None
        references = []
        dois = summary.get("dois") or []
        years = summary.get("publication_years") or []
        for index, doi in enumerate(dois):
            references.append(
                {
                    "doi": doi,
                    "title": None,
                    "year": years[index] if index < len(years) else None,
                }
            )
        detail = dict(summary)
        detail.update(
            {
                "paper_title": [],
                "references": references,
                "key_result": [],
                "function_description": None,
                "cloning_method": None,
                "cloning_method_description": None,
                "author": None,
                "author_mail": None,
                "submission_date": None,
                "protein_family": None,
                "validation_method": None,
                "validation_methods": [],
            }
        )
        return detail


FIXTURES = Fixtures()


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------
class AssetStore:
    """Serve production-docroot assets from a local cache, download on miss."""

    def __init__(self, cache_dir: str, allow_network: bool, download_timeout: float) -> None:
        self.cache_dir = cache_dir
        self.allow_network = allow_network
        self.download_timeout = download_timeout
        self._lock = threading.Lock()
        self._failed: set[str] = set()

    def path_for(self, url_path: str) -> str:
        return os.path.join(self.cache_dir, url_path.lstrip("/"))

    def load(self, url_path: str) -> bytes | None:
        """Return asset bytes, or None when it should be stubbed."""
        target = self.path_for(url_path)
        if os.path.isfile(target):
            try:
                with open(target, "rb") as handle:
                    return handle.read()
            except OSError:
                return None
        if not self.allow_network or url_path in self._failed:
            return None
        with self._lock:
            if os.path.isfile(target):
                with open(target, "rb") as handle:
                    return handle.read()
            try:
                request = urllib.request.Request(
                    PRODUCTION_ORIGIN + url_path,
                    headers={"User-Agent": "wheatomics-known-gene-mock/1.0"},
                )
                with urllib.request.urlopen(request, timeout=self.download_timeout) as response:
                    body = response.read()
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as handle:
                    handle.write(body)
                log(f"downloaded {url_path} ({len(body)} bytes) -> {target}")
                return body
            except (urllib.error.URLError, OSError, ValueError) as exc:
                log(f"asset download failed for {url_path}: {exc}")
                self._failed.add(url_path)
                return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def log(message: str) -> None:
    sys.stderr.write(f"[mock] {message}\n")
    sys.stderr.flush()


def envelope(data: object) -> dict:
    return {
        "success": True,
        "message": "ok",
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "data": data,
    }


def error_envelope(status: int, detail: str) -> dict:
    return {
        "success": False,
        "message": detail,
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "detail": detail,
        "status": status,
    }


def searchable_text(record: dict, fields: tuple[str, ...]) -> str:
    chunks: list[str] = []
    for field in fields:
        value = record.get(field)
        if value is None:
            continue
        if isinstance(value, list):
            chunks.extend(str(item) for item in value)
        else:
            chunks.append(str(value))
    # The DOI column is rendered as details[].doi but summaries expose dois[].
    if "doi" in fields:
        chunks.extend(str(item) for item in record.get("dois") or [])
    return "\n".join(chunks).lower()


def page_records(records: list[dict], limit: int | None, offset: int) -> tuple[list[dict], int]:
    total = len(records)
    if limit is None:
        return records, total
    return records[offset : offset + limit], total


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------
class MockHandler(BaseHTTPRequestHandler):
    server_version = "KnownGeneMock/1.0"
    protocol_version = "HTTP/1.1"

    # -------------------------------------------------- response plumbing
    def _send(self, status: int, body: bytes, content_type: str, extra_headers: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _file(self, path: str, content_type: str | None = None) -> bool:
        try:
            with open(path, "rb") as handle:
                body = handle.read()
        except OSError:
            return False
        if content_type:
            guessed = content_type
        else:
            guessed = mimetypes.guess_type(path)[0] or "application/octet-stream"
            if guessed.startswith("text/") or guessed == "application/javascript":
                guessed += "; charset=utf-8"
        self._send(200, body, guessed)
        return True

    def _asset(self, url_path: str) -> None:
        body = self.server.assets.load(url_path)  # type: ignore[attr-defined]
        guessed = mimetypes.guess_type(url_path)[0] or "application/octet-stream"
        if body is None:
            if url_path.endswith(".css"):
                body = b"/* asset unavailable in local mock (production docroot) */\n"
            elif url_path.endswith((".js", ".mjs")):
                body = b"/* asset unavailable in local mock (production docroot) */\n"
            elif url_path.endswith((".png", ".jpg", ".jpeg", ".gif", ".ico")):
                body = TINY_PNG
                guessed = "image/png"
            else:
                body = b""
            self._send(200, body, guessed if guessed.startswith("image/") else guessed)
            return
        if guessed.startswith("text/") or guessed in ("application/javascript",):
            guessed += "; charset=utf-8"
        self._send(200, body, guessed)

    # -------------------------------------------------- routing
    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        try:
            if path in ("/", "/index.html"):
                self.send_response(302)
                self.send_header("Location", "/genes/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if path in ("/genes", "/genes/", "/genes/index.html"):
                if self._file(os.path.join(STATIC_GENES, "index.html"), "text/html; charset=utf-8"):
                    return
                self._json(error_envelope(404, "index.html not found"), 404)
                return
            if path == "/genes/detail.html":
                if self._file(os.path.join(STATIC_GENES, "detail.html"), "text/html; charset=utf-8"):
                    return
                self._json(error_envelope(404, "detail.html not found"), 404)
                return
            if path == "/genes/known_gene_common.js":
                if self._file(os.path.join(STATIC_GENES, "known_gene_common.js"), "application/javascript; charset=utf-8"):
                    return
                self._json(error_envelope(404, "known_gene_common.js not found"), 404)
                return
            if path == "/api/v2shell/shell.js":
                if self._file(os.path.join(STATIC_V2, "shell.js"), "application/javascript; charset=utf-8"):
                    return
                self._json(error_envelope(404, "shell.js not found"), 404)
                return
            if path == "/api/v2shell/shell.css":
                if self._file(os.path.join(STATIC_V2, "shell.css"), "text/css; charset=utf-8"):
                    return
                self._json(error_envelope(404, "shell.css not found"), 404)
                return
            if path.startswith("/api/genes/known/"):
                self._known_api(path, query)
                return
            if path == "/api/track/stats":
                self._json(
                    envelope(
                        {
                            "today": {"pv": 1234, "uv": 321},
                            "total": {"pv": 456789, "uv": 12345},
                            "online": 12,
                        }
                    )
                )
                return
            if path.startswith(("/css/", "/js/", "/V2.0/", "/favicon.ico")):
                self._asset(path)
                return
            # Anything else (GeneHub pages etc.) is outside the mock's scope.
            self._json(error_envelope(404, f"Not found in local mock: {path}"), 404)
        except BrokenPipeError:
            return

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        if parsed.path in ("/api/track/visit", "/api/track/stats"):
            self._json({"success": True, "message": "ok"})
            return
        self._json(error_envelope(404, f"Not found in local mock: {parsed.path}"), 404)

    # -------------------------------------------------- KnownGene API
    def _known_api(self, path: str, query: dict) -> None:
        endpoint = path[len("/api/genes/known/") :]
        params = {key: values[-1] for key, values in query.items()}

        if endpoint == "all":
            limit = parse_positive_int(params.get("limit"), 1, 5000)
            if params.get("limit") and limit is None:
                self._json(error_envelope(400, "limit must be between 1 and 5000"), 400)
                return
            offset = parse_offset(params.get("offset"))
            records, total = page_records(FIXTURES.summaries, limit, offset)
            self._json(envelope({"total": total, "records": records}))
            return

        if endpoint == "stats":
            self._json(self.server.stats_payload)  # type: ignore[attr-defined]
            return

        if endpoint == "search":
            searchid = (params.get("searchid") or "").strip()
            if not searchid:
                self._json(error_envelope(400, "searchid is required"), 400)
                return
            field = params.get("field") or "all"
            if field not in SEARCH_FIELDS:
                valid = ", ".join(SEARCH_FIELDS)
                self._json(
                    error_envelope(400, f"Unsupported search field: {field!r}. Valid fields: {valid}."),
                    400,
                )
                return
            limit = parse_positive_int(params.get("limit"), 1, 5000)
            if params.get("limit") and limit is None:
                self._json(error_envelope(400, "limit must be between 1 and 5000"), 400)
                return
            offset = parse_offset(params.get("offset"))
            term = searchid.lower()
            fields = SEARCH_FIELDS[field]
            matched = [r for r in FIXTURES.summaries if term in searchable_text(r, fields)]
            records, total = page_records(matched, limit, offset)
            self._json(
                envelope({"query": searchid, "field": field, "total": total, "records": records})
            )
            return

        if endpoint == "by-chromosome":
            self._json(error_envelope(404, "by-chromosome needs a chromosome segment"), 404)
            return

        # /api/genes/known/<id>
        key = urllib.parse.unquote(endpoint).strip()
        detail = FIXTURES.detail_for(key)
        if detail is None:
            self._json(error_envelope(404, f"Known gene not found: {key}"), 404)
            return
        self._json(envelope(detail))

    # -------------------------------------------------- logging
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        if self.server.verbose:  # type: ignore[attr-defined]
            log(f"{self.address_string()} {fmt % args}")

    def log_error(self, fmt: str, *args) -> None:
        log(f"error {fmt % args}")


def parse_positive_int(value: str | None, minimum: int, maximum: int) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    if parsed < minimum or parsed > maximum:
        return None
    return parsed


def parse_offset(value: str | None) -> int:
    if not value:
        return 0
    try:
        parsed = int(value)
    except ValueError:
        return 0
    return max(0, parsed)


class MockServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], fixtures: Fixtures, stats_payload: dict,
                 assets: AssetStore, verbose: bool) -> None:
        super().__init__(address, MockHandler)
        self.fixtures = fixtures
        self.stats_payload = stats_payload
        self.assets = assets
        self.verbose = verbose


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--asset-cache", default=DEFAULT_ASSET_CACHE,
                        help="cache dir for production docroot assets (default: /tmp/kg_assets)")
    parser.add_argument("--offline", action="store_true",
                        help="never download assets at request time (only use the cache)")
    parser.add_argument("--download-timeout", type=float, default=8.0)
    parser.add_argument("--verbose", action="store_true", help="log every request")
    args = parser.parse_args()

    if not os.path.isdir(FIXTURE_DIR):
        log(f"fixture dir missing: {FIXTURE_DIR}")
        return 2
    assets = AssetStore(args.asset_cache, not args.offline, args.download_timeout)
    server = MockServer(
        (args.host, args.port),
        fixtures=FIXTURES,
        stats_payload=FIXTURES.stats_payload,
        assets=assets,
        verbose=args.verbose,
    )
    log(f"fixtures: {FIXTURE_DIR}")
    log(f"genes:    {STATIC_GENES}")
    log(f"assets:   {args.asset_cache}")
    log(f"listening on http://{args.host}:{args.port}/genes/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
