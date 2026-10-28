# SPA multi-width render check — kg-prod-stats

- URL: https://wheatomics.sdau.edu.cn/genes/
- Checked: 2026-10-28T10:15:30.933Z
- Widths: 360, 390, 414, 768, 1024, 1280, 1440, 1920
- Result: **PASS**

| width | overflow | broken img | JS errors | viewport | contrast <3 | contrast 3-4.5 | small targets | screenshot |
|---|---|---|---|---|---|---|---|---|
| 360 | 0px | 0 | 0 | ok | 0 | 0 | 1 | w360.png |
| 390 | 0px | 0 | 0 | ok | 0 | 0 | 1 | w390.png |
| 414 | 0px | 0 | 0 | ok | 0 | 0 | 1 | w414.png |
| 768 | 0px | 0 | 0 | ok | 0 | 0 | 0 | w768.png |
| 1024 | 0px | 0 | 0 | ok | 0 | 0 | 0 | w1024.png |
| 1280 | 0px | 0 | 0 | ok | 0 | 0 | 0 | w1280.png |
| 1440 | 0px | 0 | 0 | ok | 0 | 0 | 0 | w1440.png |
| 1920 | 0px | 0 | 0 | ok | 0 | 0 | 0 | w1920.png |

## Warnings (review, may be acceptable)
- w360: small touch target 72x15 — "Back to top ↑" (footer.site-footer > div.container.footer-bottom > button.back-top)
- w390: small touch target 72x15 — "Back to top ↑" (footer.site-footer > div.container.footer-bottom > button.back-top)
- w414: small touch target 72x15 — "Back to top ↑" (footer.site-footer > div.container.footer-bottom > button.back-top)

Screenshots: /tmp/kg_prod_visual/stats
