// =============================================================================
// SPA multi-width render check (runs inside ego-browser's Node runtime).
//
// Inspired by Hallmark's sloplint: load a page in a real browser at eight
// widths and fail on the things that actually break a published page. No npm
// dependency: ego-browser already ships a Chromium and the page API we need.
//
// Do not run with plain `node`; launch it through scripts/spa_visual_check.sh,
// which fills globalThis.__SPA_CHECK_CONFIG__ and calls ego-browser.
//
// Config (JSON, injected by the shell wrapper):
//   { url, label, widths[], waitFor?, actions[], scrollTo?, settleMs, outDir }
// Exit code: 0 = PASS, 1 = floor violations, 2 = could not run.
// =============================================================================

const cfg = globalThis.__SPA_CHECK_CONFIG__;
if (!cfg || !cfg.url) {
  console.error("[spa-check] missing globalThis.__SPA_CHECK_CONFIG__ (run scripts/spa_visual_check.sh)");
  throw new Error("spa-check: no config");
}

const fs = await import("node:fs/promises");
const nodePath = await import("node:path");

const DEFAULT_WIDTHS = [360, 390, 414, 768, 1024, 1280, 1440, 1920];
const widths = (cfg.widths && cfg.widths.length ? cfg.widths : DEFAULT_WIDTHS)
  .map(Number).filter((w) => Number.isFinite(w) && w >= 240 && w <= 3840);
if (!widths.length) { console.error("[spa-check] no valid widths"); throw new Error("spa-check: widths"); }

const settleMs = Number(cfg.settleMs) || 600;
const label = cfg.label || "page";
const outDir = cfg.outDir || `/tmp/spa-check/${label}`;
await fs.mkdir(outDir, { recursive: true });

const heightFor = (w) => (w <= 480 ? 844 : w <= 1024 ? 1024 : 900);

// Collect load-time JS errors before any navigation on this page.
const ERROR_COLLECTOR = [
  "window.__spaCheckErrors = [];",
  "window.addEventListener('error', function (e) { window.__spaCheckErrors.push(String((e && e.message) || (e && e.type) || 'error')); });",
  "window.addEventListener('unhandledrejection', function (e) { window.__spaCheckErrors.push('unhandledrejection: ' + String(e && e.reason)); });"
].join("\n");

const task = await taskSpace(`spa visual check ${label} ${Date.now()}`);
const page = await task.newPage();
await page.cdp("Page.addScriptToEvaluateOnNewDocument", { source: ERROR_COLLECTOR });

// ---------------------------------------------------------------------------
// In-page audit. Self-contained: every helper lives inside the page.
// ---------------------------------------------------------------------------
function inPageAudit() {
  const vw = window.innerWidth;
  const isVisible = (el) => {
    const s = getComputedStyle(el);
    if (s.display === "none" || s.visibility === "hidden" || Number(s.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const pathOf = (el) => {
    const parts = [];
    let n = el;
    for (let i = 0; n && n.nodeType === 1 && i < 3; i++, n = n.parentElement) {
      let p = n.tagName.toLowerCase();
      if (n.id) p += "#" + n.id;
      else if (n.classList && n.classList.length) p += "." + Array.prototype.slice.call(n.classList, 0, 2).join(".");
      parts.unshift(p);
    }
    return parts.join(" > ");
  };
  const shortText = (el) => (el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 42);

  // 1) horizontal overflow + offending elements
  const docW = Math.max(document.documentElement.scrollWidth, document.body ? document.body.scrollWidth : 0);
  const overflowPx = Math.max(0, docW - vw);
  const offenders = [];
  if (overflowPx > 1 && document.body) {
    const all = document.body.querySelectorAll("*");
    for (let i = 0; i < all.length && offenders.length < 6; i++) {
      const el = all[i];
      if (!isVisible(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.right > vw + 1 || r.left < -1) {
        offenders.push({
          path: pathOf(el),
          left: Math.round(r.left), right: Math.round(r.right), width: Math.round(r.width),
          text: shortText(el)
        });
      }
    }
  }

  // 2) broken images / missing alt
  const brokenImages = [];
  const imagesMissingAlt = [];
  Array.prototype.forEach.call(document.images, (img) => {
    if (img.complete && img.naturalWidth === 0) brokenImages.push(img.getAttribute("src") || img.currentSrc || "(inline)");
    if (!img.hasAttribute("alt")) imagesMissingAlt.push(img.getAttribute("src") || "(inline)");
  });

  // 3) load-time JS errors captured by the injected collector
  const jsErrors = (window.__spaCheckErrors || []).slice(0, 8);

  // 4) document basics
  const viewportMeta = document.querySelector('meta[name="viewport"]');
  const lang = document.documentElement.getAttribute("lang") || "";

  // 5) text contrast (WCAG 2.1): skip text on background images/gradients.
  const parseColor = (value) => {
    const m = String(value || "").match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(",").map((x) => parseFloat(x));
    if (p.length < 3) return null;
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const channel = (v) => {
    v /= 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  };
  const luminance = (c) => 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b);
  const ratio = (a, b) => {
    const la = luminance(a), lb = luminance(b);
    const hi = Math.max(la, lb), lo = Math.min(la, lb);
    return (hi + 0.05) / (lo + 0.05);
  };
  const effectiveBackground = (el) => {
    const layers = [];
    let n = el;
    while (n && n.nodeType === 1) {
      const s = getComputedStyle(n);
      if (s.backgroundImage && s.backgroundImage !== "none") return null; // image/gradient: can't decide
      const c = parseColor(s.backgroundColor);
      if (c && c.a > 0) {
        layers.push(c);
        if (c.a >= 0.999) break;
      }
      n = n.parentElement;
    }
    let base = { r: 255, g: 255, b: 255 };
    for (let i = layers.length - 1; i >= 0; i--) {
      const c = layers[i];
      base = {
        r: c.r * c.a + base.r * (1 - c.a),
        g: c.g * c.a + base.g * (1 - c.a),
        b: c.b * c.a + base.b * (1 - c.a)
      };
    }
    return base;
  };
  const severe = [];
  const minor = [];
  const candidates = document.body ? document.body.querySelectorAll("p, li, td, th, h1, h2, h3, h4, h5, h6, span, a, button, label, small, strong, em, code, div") : [];
  for (let i = 0; i < candidates.length && i < 600; i++) {
    const el = candidates[i];
    if (el.getAttribute("aria-hidden") === "true" || el.hasAttribute("hidden")) continue;
    const directText = Array.prototype.some.call(el.childNodes, (n) => n.nodeType === 3 && n.textContent.trim().length > 1);
    if (!directText || !isVisible(el)) continue;
    const s = getComputedStyle(el);
    const fg = parseColor(s.color);
    if (!fg || fg.a < 0.5) continue;
    const bg = effectiveBackground(el);
    if (!bg) continue;
    const r = ratio(fg, bg);
    const size = parseFloat(s.fontSize) || 16;
    const bold = (parseInt(s.fontWeight, 10) || 400) >= 700;
    const large = size >= 24 || (size >= 18.66 && bold);
    const threshold = large ? 3 : 4.5;
    if (r < threshold) {
      const item = {
        ratio: Math.round(r * 100) / 100,
        required: threshold,
        path: pathOf(el),
        text: shortText(el),
        color: s.color,
        background: `rgb(${Math.round(bg.r)}, ${Math.round(bg.g)}, ${Math.round(bg.b)})`,
        fontSize: Math.round(size)
      };
      if (r < 3) { if (severe.length < 8) severe.push(item); }
      else if (minor.length < 8) minor.push(item);
    }
  }

  // 6) small touch targets (phones only; WCAG 2.5.8 = 24px minimum)
  const smallTargets = [];
  if (vw <= 480) {
    const interactive = document.body ? document.body.querySelectorAll("button, select, textarea, input:not([type=hidden]), [role=button], .primary-button, .secondary-button, .ptm-example, .ptm-select") : [];
    for (let i = 0; i < interactive.length && smallTargets.length < 8; i++) {
      const el = interactive[i];
      if (!isVisible(el)) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width < 24 || rect.height < 24) {
        smallTargets.push({
          path: pathOf(el),
          size: `${Math.round(rect.width)}x${Math.round(rect.height)}`,
          text: shortText(el)
        });
      }
    }
  }

  return {
    title: document.title,
    url: location.href,
    viewport: { width: vw, height: window.innerHeight, scrollWidth: docW },
    overflowPx,
    offenders,
    brokenImages,
    imagesMissingAlt,
    jsErrors,
    hasViewportMeta: !!viewportMeta,
    viewportContent: viewportMeta ? viewportMeta.getAttribute("content") : null,
    lang,
    contrast: { severe, minor },
    smallTargets
  };
}

// ---------------------------------------------------------------------------
// Run every width.
// ---------------------------------------------------------------------------
const results = [];
const shotFiles = [];


async function waitForLoadingToFinish() {
  // Many WheatOmics pages render "Loading..." / a spinner until their fetch
  // resolves; auditing then would flag a transient placeholder, not the page.
  const deadline = Date.now() + 4000;
  while (Date.now() < deadline) {
    const busy = await page.evaluate(() => {
      const nodes = document.querySelectorAll(".loading, .ptm-loading, #loading-indicator, .empty-note, .spinner-border");
      for (const el of nodes) {
        const s = getComputedStyle(el);
        if (s.display === "none" || s.visibility === "hidden") continue;
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) continue;
        if (el.classList.contains("spinner-border")) return true;
        if (/loading|searching/i.test(el.textContent || "")) return true;
      }
      return false;
    });
    if (!busy) return;
    await page.waitForTimeout(400);
  }
}

async function runActions() {
  for (const action of cfg.actions || []) {
    if (action.type === "fill") {
      await page.fill(action.selector, action.value);
    } else if (action.type === "click") {
      await page.click(action.selector);
    } else if (action.type === "waitFor") {
      await page.waitForSelector(action.selector, { state: "visible", timeout: action.timeout || 20000 });
    } else if (action.type === "wait") {
      await page.waitForTimeout(action.ms || 500);
    }
  }
}

for (const width of widths) {
  const height = heightFor(width);
  const row = { width, height };
  try {
    await page.cdp("Emulation.setDeviceMetricsOverride", {
      width, height, deviceScaleFactor: 1, mobile: width <= 480
    });
    await page.goto(cfg.url);
    await page.waitForLoadState("load", { timeout: 45000 }).catch(() => {});
    if (cfg.waitFor) {
      await page.waitForSelector(cfg.waitFor, { state: "visible", timeout: 20000 }).catch(() => {
        row.waitForMissing = cfg.waitFor;
      });
    }
    await runActions();
    await page.waitForTimeout(settleMs);
    await waitForLoadingToFinish();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(150);

    const audit = await page.evaluate(inPageAudit);
    Object.assign(row, audit);

    const shot = nodePath.join(outDir, `w${width}.png`);
    await page.screenshot({ path: shot });
    shotFiles.push(shot);
    row.screenshot = shot;

    if (cfg.scrollTo) {
      await page.evaluate((sel) => {
        const el = document.querySelector(sel);
        if (el) el.scrollIntoView({ behavior: "auto", block: "start" });
      }, cfg.scrollTo);
      await page.waitForTimeout(400);
      const sectionShot = nodePath.join(outDir, `w${width}-section.png`);
      await page.screenshot({ path: sectionShot });
      row.sectionScreenshot = sectionShot;
    }
  } catch (err) {
    row.fatal = String(err && err.message ? err.message : err);
  }
  results.push(row);
  const flags = [];
  if (row.fatal) flags.push("FATAL");
  if (row.overflowPx > 1) flags.push(`overflow ${row.overflowPx}px`);
  if (row.brokenImages && row.brokenImages.length) flags.push(`${row.brokenImages.length} broken img`);
  if (row.jsErrors && row.jsErrors.length) flags.push(`${row.jsErrors.length} JS error`);
  if (row.hasViewportMeta === false) flags.push("no viewport meta");
  if (row.waitForMissing) flags.push(`missing ${row.waitForMissing}`);
  if (row.contrast && row.contrast.severe.length) flags.push(`${row.contrast.severe.length} low contrast (<3)`);
  if (row.contrast && row.contrast.minor.length) flags.push(`${row.contrast.minor.length} contrast 3-4.5`);
  if (row.smallTargets && row.smallTargets.length) flags.push(`${row.smallTargets.length} small target`);
  console.log(`[spa-check] ${String(width).padStart(4)}px  ${flags.length ? flags.join(", ") : "ok"}`);
}

await page.cdp("Emulation.clearDeviceMetricsOverride", {}).catch(() => {});
await page.close().catch(() => {});

// ---------------------------------------------------------------------------
// Classify: floor problems fail the check, the rest are warnings.
// ---------------------------------------------------------------------------
const floor = [];
const warnings = [];
for (const row of results) {
  if (row.fatal) floor.push(`w${row.width}: ${row.fatal}`);
  if (row.overflowPx > 1) floor.push(`w${row.width}: horizontal overflow ${row.overflowPx}px`);
  if (row.brokenImages && row.brokenImages.length) floor.push(`w${row.width}: ${row.brokenImages.length} broken image(s)`);
  if (row.jsErrors && row.jsErrors.length) floor.push(`w${row.width}: ${row.jsErrors.length} JS error(s)`);
  if (row.hasViewportMeta === false) floor.push(`w${row.width}: missing <meta name="viewport">`);
  if (row.waitForMissing) floor.push(`w${row.width}: waitFor selector not found (${row.waitForMissing})`);
  (row.contrast && row.contrast.severe ? row.contrast.severe : []).forEach((c) =>
    floor.push(`w${row.width}: contrast ${c.ratio}:1 < 3:1 — "${c.text}" (${c.path})`));
  (row.contrast && row.contrast.minor ? row.contrast.minor : []).forEach((c) =>
    warnings.push(`w${row.width}: contrast ${c.ratio}:1 — "${c.text}" (${c.path})`));
  (row.imagesMissingAlt || []).forEach((src) => warnings.push(`w${row.width}: image without alt — ${src}`));
  (row.smallTargets || []).forEach((t) => warnings.push(`w${row.width}: small touch target ${t.size} — "${t.text}" (${t.path})`));
  if (row.lang === "") warnings.push(`w${row.width}: <html lang> missing`);
}

const passed = floor.length === 0;
const summary = {
  label: cfg.label,
  url: cfg.url,
  checkedAt: new Date().toISOString(),
  widths,
  passed,
  floor,
  warnings: warnings.slice(0, 40),
  results
};
await fs.writeFile(nodePath.join(outDir, "report.json"), JSON.stringify(summary, null, 2), "utf8");

// Markdown report, also printed to the terminal.
const md = [];
md.push(`# SPA multi-width render check — ${label}`);
md.push("");
md.push(`- URL: ${cfg.url}`);
md.push(`- Checked: ${summary.checkedAt}`);
md.push(`- Widths: ${widths.join(", ")}`);
md.push(`- Result: **${passed ? "PASS" : "FAIL"}**`);
md.push("");
md.push("| width | overflow | broken img | JS errors | viewport | contrast <3 | contrast 3-4.5 | small targets | screenshot |");
md.push("|---|---|---|---|---|---|---|---|---|");
for (const row of results) {
  md.push(`| ${row.width} | ${row.overflowPx || 0}px | ${(row.brokenImages || []).length} | ${(row.jsErrors || []).length} | ${row.hasViewportMeta === false ? "MISSING" : "ok"} | ${(row.contrast && row.contrast.severe || []).length} | ${(row.contrast && row.contrast.minor || []).length} | ${(row.smallTargets || []).length} | ${row.screenshot ? nodePath.basename(row.screenshot) : "-"} |`);
}
if (floor.length) {
  md.push("", "## Floor problems (must fix)");
  floor.forEach((item) => md.push(`- ${item}`));
}
if (warnings.length) {
  md.push("", "## Warnings (review, may be acceptable)");
  warnings.slice(0, 40).forEach((item) => md.push(`- ${item}`));
}
md.push("", `Screenshots: ${outDir}`);
await fs.writeFile(nodePath.join(outDir, "report.md"), md.join("\n") + "\n", "utf8");

console.log("");
console.log(md.join("\n"));
console.log("");
if (!passed) {
  throw new Error(`SPA visual check FAILED: ${floor.length} floor problem(s) — see ${outDir}/report.md`);
}
