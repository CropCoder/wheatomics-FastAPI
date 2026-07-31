#!/usr/bin/env python3
"""End-to-end smoke test for POST /api/blast/search.

Derived from the FastAPI handler in app/api/routers/blast.py (search endpoint
at /blast/search, mounted under /api, so the public path is /api/blast/search).

Why this script exists
----------------------
I cannot reach wheatomics.sdau.edu.cn from this environment (TCP to
202.194.139.32 times out, DNS resolves fine). Run this on the server or
anywhere that can reach the public API.

Schema (extracted from blast.py:228-244, all fields are application/x-www-form-urlencoded):
  program      str   one of: blastp, blastn, blastx, tblastn, tblastx (default blastp)
  database     str   database name, comma-separated for multi-db. Must exist in
                     /var/www/html/getfasta/blastdb/ (with .phr/.psq/.pdb or .nhr/.nin/.nsq).
                     Get the list from GET /api/blast/databases
  query        str   FASTA. Leading ">" optional (handler adds ">query\\n" if missing).
                     Max 100,000 chars.
  evalue       float default 10.0
  max_target_seqs int  default 1000  (form field name; response key is max_targets)
  word_size    int   optional
  matrix       str   optional
  outfmt       str   "tabular" (outfmt 6, .tsv) | "traditional" (outfmt 0, .txt) | "both"
                     default "tabular"

The handler ALWAYS writes both tabular AND traditional result files
(see lines 282-285 and 327-335 / 340-370 — fmt_defs is iterated for both
formats regardless of the outfmt parameter; outfmt only affects which one
is returned when blast_formatter is unavailable). The response is
{"success": True, "program": ..., "database": [...], "parameters": {...},
 "query_header": ..., "outfmt": ["tabular","traditional"],
 "download_url": {"tabular": "...", "traditional": "..."}}

Usage:
  python3 scripts/blast_api_smoke.py                       # default: blastp vs Fielder_protein, short query
  python3 scripts/blast_api_smoke.py --program blastn      # change program
  python3 scripts/blast_api_smoke.py --database AK58_protein.fasta
  python3 scripts/blast_api_smoke.py --api http://127.0.0.1:8000   # test local backend
  python3 scripts/blast_api_smoke.py --query-file query.fa
  python3 scripts/blast_api_smoke.py --no-download                 # only check job_id, don't fetch result
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


# A tiny, known-good protein FASTA. "MSSSTG..." matches the example in the
# handler's docstring (line 251 of blast.py) and is short enough that blastp
# against any protein DB finishes in well under a second. The handler prepends
# ">query\n" if the query doesn't start with ">", but we include it explicitly
# so the result is unambiguous in logs.
DEFAULT_QUERY = """>smoke_test
MSSSTGSNNSLDFGDSETSLASGKKKKRGISKLFKGVDWDQETLGDVISNGHEPKLRGVKRL
KYRDTLEVVVTSEQYNKFCKEFVKEYEPLLKDQKELKDFLKDRQELNDLYQKQYEHLKKL
"""


def post_search(api: str, fields: dict[str, str], timeout: int) -> tuple[int, dict, float]:
    """POST application/x-www-form-urlencoded. Returns (http_status, body_dict, elapsed_s)."""
    body = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url=f"{api.rstrip('/')}/api/blast/search",
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw), time.time() - t0
    except urllib.error.HTTPError as e:
        # 4xx/5xx body is JSON per app/core/response.py envelope
        raw = e.read()
        try:
            return e.code, json.loads(raw), time.time() - t0
        except json.JSONDecodeError:
            return e.code, {"raw": raw.decode("utf-8", errors="replace")}, time.time() - t0


def download(url: str, out_dir: Path, timeout: int) -> tuple[int, Path, float]:
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = out_dir / Path(urllib.parse.urlparse(url).path).name
    t0 = time.time()
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        data = resp.read()
    fname.write_bytes(data)
    return len(data), fname, time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="https://wheatomics.sdau.edu.cn",
                    help="Base API URL (default: https://wheatomics.sdau.edu.cn)")
    ap.add_argument("--program", default="blastp", choices=["blastp", "blastn", "blastx", "tblastn", "tblastx"])
    ap.add_argument("--database", default="Fielder_protein",
                    help="Database name as it appears in GET /api/blast/databases (default: Fielder_protein)")
    ap.add_argument("--query", default=DEFAULT_QUERY, help="Inline FASTA query")
    ap.add_argument("--query-file", type=Path, help="Read query from file instead of --query")
    ap.add_argument("--evalue", type=float, default=10.0)
    ap.add_argument("--max-target-seqs", type=int, default=1000)
    ap.add_argument("--word-size", type=int, default=None)
    ap.add_argument("--matrix", default=None)
    ap.add_argument("--outfmt", default="tabular", choices=["tabular", "traditional", "both"])
    ap.add_argument("--timeout", type=int, default=700,
                    help="HTTP timeout in seconds (must be > blast.py 600s subprocess timeout)")
    ap.add_argument("--no-download", action="store_true",
                    help="Skip downloading result files; only verify the search response")
    ap.add_argument("--download-dir", type=Path, default=Path("/tmp/blast_api_smoke_results"),
                    help="Where to save downloaded result files")
    args = ap.parse_args()

    if args.query_file:
        query = args.query_file.read_text()
    else:
        query = args.query

    # Build form fields. Key names must match blast.py:228-244.
    # The handler's max_targets parameter uses `alias="max_target_seqs"`, so
    # the form key is "max_target_seqs".
    fields = {
        "program": args.program,
        "database": args.database,
        "query": query,
        "evalue": str(args.evalue),
        "max_target_seqs": str(args.max_target_seqs),
        "outfmt": args.outfmt,
    }
    if args.word_size is not None:
        fields["word_size"] = str(args.word_size)
    if args.matrix is not None:
        fields["matrix"] = args.matrix

    print(f"→ POST {args.api}/api/blast/search", flush=True)
    print(f"  program={args.program}  database={args.database}  evalue={args.evalue}  "
          f"max_target_seqs={args.max_target_seqs}  outfmt={args.outfmt}  query_len={len(query)}", flush=True)

    try:
        status, body, elapsed = post_search(args.api, fields, args.timeout)
    except urllib.error.URLError as e:
        print(f"✗ NETWORK ERROR: {e.reason} (could not reach {args.api})", file=sys.stderr)
        return 2
    except TimeoutError:
        print(f"✗ TIMEOUT after {args.timeout}s (handler subprocess timeout is 600s, "
              "Apache ProxyTimeout must be ≥1200, gunicorn timeout ≥700)", file=sys.stderr)
        return 3

    print(f"← HTTP {status} in {elapsed:.2f}s", flush=True)
    print(json.dumps(body, indent=2, ensure_ascii=False)[:2000], flush=True)

    if status != 200:
        print(f"✗ Non-200 status: {status}", file=sys.stderr)
        return 1

    if not body.get("success"):
        print("✗ Response success != True", file=sys.stderr)
        return 1

    d_urls = body.get("download_url") or {}
    if not d_urls:
        print("✗ No download_url in response (BLAST likely produced no hits or backend misconfigured)",
              file=sys.stderr)
        return 1

    print(f"✓ job_id: {body.get('query_header', '?')!r}  hits: {len(d_urls)} format(s) ready", flush=True)

    if args.no_download:
        return 0

    # Download every format the handler produced and sanity-check content.
    for fmt, url in d_urls.items():
        try:
            nbytes, fpath, dl_elapsed = download(url, args.download_dir, args.timeout)
        except urllib.error.URLError as e:
            print(f"✗ Download failed for {fmt}: {e.reason}", file=sys.stderr)
            return 4
        # Basic format check
        head = fpath.read_text(errors="replace").splitlines()[:3]
        if fmt == "tabular" and head:
            cols = head[0].split("\t")
            if len(cols) != 12:
                print(f"✗ tabular header has {len(cols)} columns, expected 12 (outfmt 6):\n  {head[0]}",
                      file=sys.stderr)
                return 5
        elif fmt == "traditional" and head and "BLAST" not in head[0]:
            print(f"✗ traditional result doesn't look like BLAST output (no 'BLAST' in first line):\n  {head[0]}",
                  file=sys.stderr)
            return 5
        print(f"✓ {fmt:11s}  {nbytes:>10d} bytes  ({dl_elapsed:.2f}s)  → {fpath}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
