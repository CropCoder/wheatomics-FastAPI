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

## The CGI needs one sudo step

`/var/www/cgi-bin/` and `/var/www/cgi-bin/geneDetail.py` are owned by
`root`/`www-data` and are **not writable by the `fei` account** (passwordless
sudo only covers the `wheatomics-api` systemctl commands). The deploy script
prints the exact commands when it hits this case; run them once:

```bash
sudo cp -a /var/www/cgi-bin/geneDetail.py /var/www/data/masw_data/backup_geneDetail_<date>.py
sudo cp /var/www/FastAPI_backend_Port8000/app/static/docpages/geneDetail.py /var/www/cgi-bin/geneDetail.py
sudo chmod 755 /var/www/cgi-bin/geneDetail.py
```

Until that is done the live GeneHub result page stays on the old CGI template
(the repo copy and local render test are still valid).

## Not repo-managed (runtime dependencies, left in the docroot)

`/V2.0/*` (V2.0 homepage, images, `news.json`), `/css/*` images, `/cite.html`,
`/favicon.ico`, the JBrowse instances (`/jbrowse-1.12.3-release/`, `/jbrowse2/`),
and the third-party Sequence Manipulation Suite pages under `/sms2/` (only the
`sms2/index.html` entry page is tracked in the repo).
