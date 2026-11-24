#!/usr/bin/env python3
"""Audit every DOI in the WheatOmics genome registry against Crossref.

Why this exists
---------------
``wheatomics_db.genome_registry`` gets its ``doi`` from three sources, none of
which is validated:

1. the ``--doi`` argument of ``finish_genome_integration.sh`` (written verbatim
   at G4, historically the main source of copy-paste errors);
2. the ``Doi`` column of ``Genefuncdb.Genefunc_registry``;
3. the ``doi:`` string scraped from the ``jbrowse.html`` / ``cite.html`` cards.

A wrong DOI is invisible on the site (the card simply links to another paper)
and only shows up when a user cites the platform. This script resolves every
DOI through the Crossref REST API and reports, per record:

* ``format``  – the string is not a syntactically valid DOI (e.g. a missing
  ``/`` such as ``10.1038s41586-018-0108-0``);
* ``unresolved`` – Crossref returns 404 (DOI does not exist / is not registered);
* ``suspect`` – the DOI resolves but its title / journal / year look unrelated
  to the dataset (species and cultivar keywords missing, journal family wrong);
* ``duplicate-other-species`` – the same DOI is attached to datasets of
  different species (usually one of them is a copy-paste error).

Usage
-----
    # audit the live registry (read-only, no DB credentials needed)
    python3 scripts/verify_genome_doi.py --api https://wheatomics.sdau.edu.cn

    # write a Markdown + JSON report
    python3 scripts/verify_genome_doi.py --report wheatomics_results/reports/doi_audit.md \
        --json wheatomics_results/json/doi_audit.json

    # audit a single dataset / ignore a known-good duplicate group
    python3 scripts/verify_genome_doi.py --dataset rye_weining2

    # machine gate: exit 1 when any error-level finding exists (for G5 / CI)
    python3 scripts/verify_genome_doi.py --strict

Exit codes: 0 = no error-level findings, 1 = error-level findings, 2 = usage/IO
failure. ``--strict`` only promotes ``suspect``/``duplicate`` to errors; format
and unresolved findings are always errors.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

DEFAULT_API = "https://wheatomics.sdau.edu.cn"
CROSSREF = "https://api.crossref.org/works/"
MAILTO = "wheatomics@sdau.edu.cn"  # Crossref polite pool

DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s\"'<>]+$")
# 常见手误：`10.1038s41586-…`（漏了 `/`）、`https://doi.org/…` 前缀、尾随标点
BROKEN_PREFIX_RE = re.compile(r"^(10\.\d{4,9})(s\d|\D)")
DOI_URL_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)

# 期刊家族：用于判断 DOI 的期刊是否与“基因组论文”相符
GENOME_JOURNALS = {
    "nature", "nature genetics", "nature communications", "nature plants",
    "science", "cell", "molecular plant", "plant journal", "the plant journal",
    "plant biotechnology journal", "genome biology", "genome research",
    "nucleic acids research", "gigascience", "scientific data", "dna research",
    "the plant genome", "plant communications", "molecular plant pathology",
    "journal of integrative plant biology", "new phytologist", "bmc biology",
    "bmc genomics", "bmc plant biology", "plos genetics", "elife", "cell reports",
    "proceedings of the national academy of sciences",
    "nature food", "nature biotechnology", "science advances", "imat",
    "plant cell & environment", "plant cell and environment", "the plant cell",
    "theoretical and applied genetics", "tag", "crop journal", "the crop journal",
    "molecular breeding", "bmc genomic data", "genome", "chromosome research",
    "current biology", "trends in plant science", "aob plants", "annals of botany",
    "frontiers in plant science", "international journal of molecular sciences",
    "agriculture", "agronomy", "cells", "genes", "biomolecules", "peerj",
    "scientific reports", "communications biology", "cell discovery",
    "g3 genes|genomes|genetics", "g3: genes, genomes, genetics", "g3",
    "genetics", "genomics", "imeta", "science china life sciences",
    "plant molecular biology", "bmc plant biology", "molecular plant pathology",
    "journal of experimental botany", "plant physiology", "the plant journal",
    "nature food", "one earth", "cell genomics", "genome biology and evolution",
    "plant biotechnology reports", "crop science", "agronomy journal", "nature",
    "molecular ecology resources", "molecular ecology", "heredity",
    "theoretical and applied genetics (tag)", "plant direct", "plant genome",
}

# 属名 → 记录里应出现的关键词（标题/摘要/期刊以外用物种名兜底）
GENUS_ALIASES = {
    "triticum": ("wheat", "triticum", "aestivum", "turgidum", "durum", "dicoccoides",
                 "urartu", "monococcum", "spelta", "carthlicum", "polonicum",
                 "turanicum", "aethiopicum", "ispahanicum", "karamyschevii",
                 "timopheevii", "zhukovskyi", "macha", "vavilovii"),
    "hordeum": ("barley", "hordeum", "vulgare", "spontaneum", "bulbosum"),
    "secale": ("rye", "secale", "cereale"),
    "aegilops": ("aegilops", "goatgrass"),
    "leyus": ("leymus",),
    "leymus": ("leymus",),
    "thinopyrum": ("thinopyrum", "intermedium", "elongatum", "ponticum"),
    "elymus": ("elymus",),
    "roegneria": ("roegneria",),
    "dasypyrum": ("dasypyrum", "villosum"),
    "agropyron": ("agropyron", "cristatum"),
    "triticale": ("triticale", "triticosecale"),
    "oryza": ("rice", "oryza"),
    "zea": ("maize", "zea"),
}

STOP = {"genome", "genomes", "assembly", "assemblies", "chromosome", "chromosome-scale",
        "high-quality", "high", "quality", "de", "novo", "the", "a", "an", "and",
        "of", "for", "with", "reveals", "insights", "into", "based"}


def normalize_doi(raw: str | None) -> tuple[str | None, str | None]:
    """Return (clean_doi, problem). problem in {None,"format","empty"}."""
    if raw is None:
        return None, "empty"
    s = str(raw).strip()
    if not s or s.lower() in {"none", "null", "n/a"}:
        return None, "empty"
    s = DOI_URL_RE.sub("", s).strip().rstrip(".,;)]}>")
    if DOI_RE.match(s):
        return s, None
    m = BROKEN_PREFIX_RE.match(s)
    if m:
        fixed = m.group(1) + "/" + s[len(m.group(1)):].lstrip("/")
        if DOI_RE.match(fixed):
            return fixed, "format"  # 可自动修复，但仍记为 format 问题
    # 有的记录把 `10.1038s41586` 之外的形式（如 `10.1038/ s41586`）写进来
    compact = re.sub(r"\s+", "", s)
    if compact != s and DOI_RE.match(compact):
        return compact, "format"
    return s, "format"


def fetch_json(url: str, timeout: int = 25) -> tuple[int, dict | None]:
    req = urllib.request.Request(url, headers={
        "User-Agent": f"wheatomics-doi-audit/1.0 (mailto:{MAILTO})",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            return fh.status, json.loads(fh.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (urllib.error.URLError, TimeoutError, ValueError):
        return 0, None


def load_registry(api: str, dataset: str | None) -> list[dict]:
    url = f"{api.rstrip('/')}/api/genomes?limit=500&include_hidden=true"
    status, payload = fetch_json(url)
    if status != 200 or not payload:
        raise SystemExit(f"[error] cannot read {url} (status={status})")
    items = payload.get("data", {}).get("items", [])
    if dataset:
        items = [i for i in items if i.get("dataset_id") == dataset]
        if not items:
            raise SystemExit(f"[error] dataset {dataset!r} not in registry")
    return items


def crossref(doi: str) -> tuple[int, str | None, str | None, int | None]:
    """Return (status, title, journal, year)."""
    status, payload = fetch_json(CROSSREF + urllib.parse.quote(doi, safe="/"))
    if status != 200 or not payload:
        return status, None, None, None
    m = payload.get("message") or {}
    title = (m.get("title") or [None])[0]
    journal = (m.get("container-title") or [None])[0]
    year = None
    for key in ("published-print", "published-online", "published", "issued"):
        parts = (m.get(key) or {}).get("date-parts") or [[None]]
        if parts and parts[0] and parts[0][0]:
            year = int(parts[0][0])
            break
    return status, title, journal, year


def keywords(texts: list[str]) -> set[str]:
    out = set()
    for t in texts:
        for w in re.split(r"[^A-Za-z0-9]+", (t or "").lower()):
            if len(w) >= 4 and w not in STOP:
                out.add(w)
    return out


def species_expected(species: str | None, cultivar: str | None) -> tuple[set[str], str | None]:
    """Return (expected keyword set, genus)."""
    genus = (species or "").split()[0].lower() if species else None
    exp = set(GENUS_ALIASES.get(genus or "", ()))
    for w in re.split(r"[^A-Za-z0-9]+", (cultivar or "").lower()):
        if len(w) >= 4 and w not in STOP:
            exp.add(w)
    return exp, genus


def judge(rec: dict, status: int, title: str | None, journal: str | None, year: int | None,
          doi_clean: str | None) -> tuple[str, list[str]]:
    """Return (level, reasons). level in {ok, info, suspect, error}.

    判定只用「物种/属」关键词做硬性比对：泛基因组论文的标题通常只写属名或俗名，
    不会出现每个材料的登录号，所以品种名（BCC2058/NGB90062…）只作加分项，
    不能因为标题里没有登录号就报可疑。
    """
    if status == 404:
        return "error", ["Crossref 404：DOI 未注册"]
    if status == 0:
        return "info", ["网络失败，未判定"]
    if status != 200:
        return "info", [f"Crossref 返回 {status}"]

    species = rec.get("species") or ""
    cultivar = rec.get("cultivar_or_line") or ""
    blob = " ".join([title or "", journal or ""]).lower()

    species_kw, _genus = species_expected(species, None)
    cultivar_kw = {w for w in re.split(r"[^A-Za-z0-9]+", cultivar.lower())
                   if len(w) >= 4 and w not in STOP}
    species_hit = any(k in blob for k in species_kw) if species_kw else None
    cultivar_hit = any(k in blob for k in cultivar_kw) if cultivar_kw else None

    reasons: list[str] = []
    hard_species_miss = species_hit is False and cultivar_hit is not True
    if hard_species_miss:
        reasons.append(f"标题/期刊未出现物种关键词 {sorted(species_kw)[:4]}")

    jl = (journal or "").lower().strip()
    journal_unknown = bool(jl) and jl not in GENOME_JOURNALS
    if journal_unknown:
        reasons.append(f"期刊不在常见基因组论文列表：{journal}")

    rec_year = rec.get("publication_year")
    if rec_year and year and abs(int(year) - int(rec_year)) > 1:
        reasons.append(f"年份不符：记录 {rec_year} vs Crossref {year}")

    if not reasons:
        return "ok", []
    # 物种完全对不上 + 期刊也不认识 → 视为错误；其余（年份/期刊单项）只是可疑
    if hard_species_miss and journal_unknown:
        return "error", reasons
    return "suspect", reasons


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default=DEFAULT_API, help="WheatOmics base URL")
    ap.add_argument("--dataset", help="audit a single dataset_id")
    ap.add_argument("--report", help="Markdown report path")
    ap.add_argument("--json", help="JSON report path")
    ap.add_argument("--strict", action="store_true",
                    help="treat suspect/duplicate findings as errors (exit 1)")
    ap.add_argument("--sleep", type=float, default=0.35,
                    help="delay between Crossref calls (default 0.35 s)")
    args = ap.parse_args()

    records = load_registry(args.api, args.dataset)
    print(f"[info] {len(records)} registry records to audit", file=sys.stderr)

    results: list[dict] = []
    cache: dict[str, tuple[int, str | None, str | None, int | None]] = {}
    for idx, rec in enumerate(records, 1):
        raw = rec.get("doi")
        clean, problem = normalize_doi(raw)
        item = {
            "dataset_id": rec.get("dataset_id"),
            "species": rec.get("species"),
            "cultivar_or_line": rec.get("cultivar_or_line"),
            "doi_raw": raw,
            "doi_clean": clean,
            "format_problem": problem,
            "crossref_status": None,
            "crossref_title": None,
            "crossref_journal": None,
            "crossref_year": None,
            "level": "ok",
            "reasons": [],
        }
        if problem == "empty":
            item["level"] = "info"
            item["reasons"] = ["无 DOI"]
        elif problem == "format":
            item["level"] = "error"
            item["reasons"] = [f"DOI 格式错误：{raw!r} → 建议 {clean!r}"]
            if clean and clean not in cache:
                cache[clean] = crossref(clean)
                time.sleep(args.sleep)
        if clean and problem is None:
            if clean not in cache:
                cache[clean] = crossref(clean)
                time.sleep(args.sleep)
            status, title, journal, year = cache[clean]
            item.update({"crossref_status": status, "crossref_title": title,
                         "crossref_journal": journal, "crossref_year": year})
            level, reasons = judge(rec, status, title, journal, year, clean)
            item["level"], item["reasons"] = level, reasons
        elif clean and problem == "format":
            status, title, journal, year = cache.get(clean, (None, None, None, None))
            item.update({"crossref_status": status, "crossref_title": title,
                         "crossref_journal": journal, "crossref_year": year})
        results.append(item)
        if idx % 25 == 0:
            print(f"[info] {idx}/{len(records)}", file=sys.stderr)

    # 同一 DOI 挂在多个物种下 → 复制粘贴嫌疑。
    # 但一篇泛基因组/多品种论文本来就覆盖多个材料，所以只在"标题只提到其中一部分
    # 属"时才报（例如 Sumai 3 的论文同时挂在 rye/Elymus 记录上）。
    by_doi: dict[str, list[dict]] = {}
    for item in results:
        if item["doi_clean"]:
            by_doi.setdefault(item["doi_clean"], []).append(item)
    for doi, group in by_doi.items():
        if len(group) < 2:
            continue
        title_blob = " ".join([(group[0].get("crossref_title") or ""),
                               (group[0].get("crossref_journal") or "")]).lower()
        hits: dict[str, bool | None] = {}
        for g in group:
            exp, _genus = species_expected(g.get("species"), None)  # 只看属/俗名，不看品种
            hits[g["dataset_id"]] = None if not exp else any(k in title_blob for k in exp)
        vals = [h for h in hits.values() if h is not None]
        if vals and any(vals) and not all(vals):
            matched = sorted(d for d, h in hits.items() if h)
            for g in group:
                if hits[g["dataset_id"]] is False:
                    g["reasons"].append(
                        f"同一 DOI 也挂在 {matched[:3]} 上，但其标题只对应那些物种，本条需人工确认")
                    if g["level"] == "ok":
                        g["level"] = "suspect"

    counts = {"error": 0, "suspect": 0, "info": 0, "ok": 0}
    for item in results:
        counts[item["level"]] = counts.get(item["level"], 0) + 1

    bad = [r for r in results if r["level"] in {"error", "suspect"}]
    print(f"[result] error={counts['error']} suspect={counts['suspect']} "
          f"info={counts['info']} ok={counts['ok']}", file=sys.stderr)
    for r in bad:
        print(f"  [{r['level']}] {r['dataset_id']}: {r['doi_raw']} → "
              f"{(r['crossref_title'] or '')[:70]} | {r['crossref_journal']} | "
              f"{r['crossref_year']} :: {'; '.join(r['reasons'])}", file=sys.stderr)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"generated_at": stamp, "api": args.api,
                       "counts": counts, "results": results}, fh,
                      ensure_ascii=False, indent=2)
        print(f"[write] {args.json}", file=sys.stderr)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(_markdown(stamp, args.api, counts, results))
        print(f"[write] {args.report}", file=sys.stderr)

    errors = counts["error"] + (counts["suspect"] if args.strict else 0)
    return 1 if errors else 0


def _markdown(stamp: str, api: str, counts: dict, results: list[dict]) -> str:
    lines = [
        "# WheatOmics 基因组 DOI 核查报告",
        "",
        f"- 生成时间：{stamp}",
        f"- 数据源：`{api}/api/genomes`",
        f"- 统计：error **{counts['error']}** / suspect **{counts['suspect']}** / "
        f"info {counts['info']} / ok {counts['ok']}（共 {len(results)} 条）",
        "- 判定：`error` = DOI 格式错/Crossref 404/标题期刊明显不符；"
        "`suspect` = 单一可疑信号（关键词或期刊或年份）；`ok` = 通过。",
        "",
        "## 需要修复 / 复核的记录",
        "",
        "| dataset_id | species | 当前 DOI | Crossref 标题 | 期刊 | 年份 | 级别 | 说明 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    bad = sorted([r for r in results if r["level"] in {"error", "suspect"}],
                 key=lambda r: (r["level"] != "error", r["dataset_id"] or ""))
    for r in bad:
        title = (r.get("crossref_title") or "").replace("|", "\\|")[:80]
        lines.append(
            f"| `{r['dataset_id']}` | {r.get('species') or ''} | `{r.get('doi_raw')}` | "
            f"{title} | {r.get('crossref_journal') or ''} | {r.get('crossref_year') or ''} | "
            f"**{r['level']}** | {'; '.join(r['reasons'])} |"
        )
    lines += ["", "## 全量明细（ok / info 略）", "",
              "完整逐条结果见 JSON 报告（`--json`）。", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
