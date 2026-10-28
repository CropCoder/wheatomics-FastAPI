# SPA multi-width render check — kg-index-stats

- URL: http://127.0.0.1:8100/genes/
- Checked: 2026-10-28T10:08:39.795Z
- Widths: 360, 390, 768, 1024, 1440
- Result: **PASS**

| width | overflow | broken img | JS errors | viewport | contrast <3 | contrast 3-4.5 | small targets | screenshot |
|---|---|---|---|---|---|---|---|---|
| 360 | 0px | 0 | 0 | ok | 0 | 0 | 1 | w360.png |
| 390 | 0px | 0 | 0 | ok | 0 | 0 | 1 | w390.png |
| 768 | 0px | 0 | 0 | ok | 0 | 0 | 0 | w768.png |
| 1024 | 0px | 0 | 0 | ok | 0 | 0 | 0 | w1024.png |
| 1440 | 0px | 0 | 0 | ok | 0 | 0 | 0 | w1440.png |

## Warnings (review, may be acceptable)
- w360: small touch target 72x15 — "Back to top ↑" (footer.site-footer > div.container.footer-bottom > button.back-top)
- w390: small touch target 72x15 — "Back to top ↑" (footer.site-footer > div.container.footer-bottom > button.back-top)

Screenshots: /Users/mashengwei/Desktop/markdown/wheatomics/FastAPI_backend_Port8000/docs/known_genes/_evidence/ui/stats
