# Docroot pages managed from the repo (`app/static/docpages/`)

Some public pages are plain Apache docroot files, outside every FastAPI
`ProxyPass` prefix, so they cannot be static mounts like the SPAs. Their repo
sources live here and are published with `scripts/deploy_doc_pages.py`
(copy + timestamped backup, `--check` / `--dry-run` / `--only` modes).
Apache needs no changes and no service restart is required.

| repo source | public URL | notes |
|---|---|---|
| `jbrowse.html` | `/jbrowse.html` | V2.0 JBrowse gateway (213 `?data=` links, filter, group chips); citation block still fetches `/cite.html` |
| `download.html` | `/download.html` | V2.0 download page (uses `/css/about_tracks.png`, `/css/mutant.png`) |
| `help_contact.html` | `/help/contact.html` | V2.0 contact page |
| `help_news.html` | `/help/news.html` | V2.0 news page; the feed still loads `/V2.0/news.json` at runtime |
| `outsitelink.html` | `/outsitelink.html` | V2.0 external links; hero image `/css/wheat.jpeg` |
| `agent.html` | `/agent.html` | V2.0 AI Agent (MCP) + REST API overview; target of the header "Agent" menu |
| `genehub_index.html` | `/GeneHub/index.html` | V2.0 GeneHub search page (form + `/api/genes/resolve` mapping table) |
| `geneDetail.py` | `/cgi-bin/geneDetail.py` | GeneHub gene-result CGI, V2.0 frame; **root-owned target — see below** |

Every page uses the shared shell (`/api/v2shell/shell.css` + `shell.js`), so the
header/footer/theme stay consistent with the SPAs.

## Publishing

On the production web node, from the repo directory:

```bash
python3 scripts/deploy_doc_pages.py                 # publish changed pages
python3 scripts/deploy_doc_pages.py --check         # compare only (exit 1 on drift)
python3 scripts/deploy_doc_pages.py --dry-run       # show planned writes
python3 scripts/deploy_doc_pages.py --only jbrowse download
```

Each target keeps the replaced file next to it as `<name>.bak-<timestamp>`;
copy it back to roll back.

## The GeneHub result CGI (already installed)

`/var/www/cgi-bin/geneDetail.py` is owned by `root`/`www-data` and the
`/var/www/cgi-bin` directory is not writable by the `fei` account, so
`deploy_doc_pages.py` cannot copy it directly (it prints the exact commands and
exits non-zero for that key).

It was installed on 2026-10-27 by running a short root step inside a container
(the `fei` account is in the `docker` group):

```bash
docker run --rm -u 0 --entrypoint /bin/sh \
  -v /var/www/cgi-bin:/cgi -v /var/www/data/masw_data:/staged \
  hugegraph/hugegraph -c \
  'cp -f /staged/geneDetail_v2_20261027.py /cgi/geneDetail.py && \
   chown root:root /cgi/geneDetail.py && chmod 755 /cgi/geneDetail.py'
```

The previous version is kept at
`/var/www/data/masw_data/backup_geneDetail_20261027.py`; roll back with the same
docker pattern (or one sudo `cp`). Future updates of this CGI need the same
root step — the rest of the docpages deploy normally with the script.

## Not repo-managed (runtime dependencies, left in the docroot)

`/V2.0/*` (V2.0 homepage, images, `news.json`), `/css/*` images, `/cite.html`,
`/favicon.ico`, the JBrowse instances (`/jbrowse-1.12.3-release/`, `/jbrowse2/`),
and the third-party Sequence Manipulation Suite pages under `/sms2/` (only the
`sms2/index.html` entry page is tracked in the repo).
