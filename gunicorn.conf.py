"""WheatOmics gunicorn configuration — 8 workers, async UvicornWorker class.

Why this file exists
--------------------
The single-worker `uvicorn main:app` setup was fine while the only "long"
endpoints were getfasta / sequence (~5s). It is unsafe for /api/blast/search,
which can run a `blastn` against a multi-genome aggregate library for
hundreds of seconds and hold 1-2 GB of RSS while it does. Under that load:

  - The single worker's event loop is occupied for the whole BLAST run, so
    every other request (health, databases, even other BLAST calls) hangs
    behind it.
  - Two long BLASTs back-to-back push the worker past 2 GB and the Linux
    OOM killer terminates the whole process. The whole API goes down until
    something restarts it.

Replacing the single uvicorn with gunicorn + 8 UvicornWorker processes:

  - 1/8 = 12.5% of connections can be stuck at once. The other 7 workers
    keep serving health, databases, short BLAST calls, and unrelated routes.
  - A worker that crashes (OOM, segfault, ctrl-c) is replaced by gunicorn
    in seconds. The API stays available.
  - `max_requests` + `max_requests_jitter` causes each worker to recycle
    after ~100 requests, preventing the slow-leak accumulation of BLAST
    subprocess memory.

Bind
----
127.0.0.1:8000 — Apache terminates TLS on 443 and reverse-proxies
`/api` to this address. Do NOT bind 0.0.0.0; do NOT expose this port
beyond localhost.

Worker count
------------
8 is a reasonable default for a 16-core machine when each BLAST peak
is ~2 GB. On smaller boxes with < 16 GB RAM, lower this to
`(available_gb - 4)` to avoid OOM during a full-house long-query storm.
"""


# --- Network ---
bind = "127.0.0.1:8000"

# --- Worker model ---
worker_class = "uvicorn.workers.UvicornWorker"
workers = 8

# Recycle each worker after ~100 requests (with ±20 jitter) so BLAST
# subprocess memory doesn't accumulate indefinitely within a single worker.
# Keep this high: an aggressive value (e.g. 5) makes all 8 workers exit and
# cold-start within the same window, dropping in-flight requests. SyntenyView
# memory is handled separately by its MySQL-backed dataset, not by recycling.
max_requests = 100
max_requests_jitter = 20

# --- Timeouts ---
# Worker silent timeout: must exceed the longest subprocess.run call inside
# any handler. Currently /api/blast/search uses timeout=600s for blastn +
# 120s for blast_formatter + buffer. 1200s gives margin.
timeout = 1200
graceful_timeout = 60
keepalive = 5

# --- Logging ---
accesslog = "-"      # stdout, captured by the systemd journal / api.log
errorlog  = "-"
loglevel  = "info"
access_log_format = (
    '%(t)s - %(h)s "%(r)s" %(s)s %(L)s %(b)s "%(a)s" '
    'worker=%(p)s req_id=%({x-request-id}o)s'
)

# --- Process naming ---
proc_name = "wheatomics-api"

# --- Memory ---
# Preload app code so workers share the read-only mmap of .pyc files.
# FastAPI app objects are picklable across the fork when fully read-only.
preload_app = True
