#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补全 KnownGene 参考文献元数据（作者 / 杂志 / 年份），DOI 优先、PubMed 兜底。

输出：app/services/data/known_gene_reference_meta.json
结构：
{
  "generated_at": "...",
  "doi":  { "<lower-doi>": {"authors": ["Given Family", ...], "journal": "...", "year": 2021,
                            "title": "...", "source": "crossref|pubmed", "verified": true,
                            "title_similarity": 0.98} },
  "title": { "<normalized-title>": { ...同上..., "doi": "..." } }
}
用法：python3 scripts/enrich_known_gene_references.py [--input /tmp/refs.json] [--out ...]
"""
from __future__ import annotations
import argparse, difflib, html, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_IN = "/tmp/refs_v2066.json"
DEFAULT_OUT = os.path.join(ROOT, "app/services/data/known_gene_reference_meta.json")
UA = {"User-Agent": "WheatOmics-KnownGene-ref-enrich/1.0 (mailto:shengweima@icloud.com)"}


def split_multi(value: object) -> list[str]:
    """Excel multi-value convention: ``; `` (semicolon + space)."""
    return [part.strip() for part in str(value or "").split("; ")]


def refs_from_xlsx(path: str) -> list[dict]:
    """Build the aligned reference list from a KnownGene 17-column Excel."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = [str(x) for x in next(rows)]

    def col(prefix: str) -> int:
        for i, h in enumerate(header):
            if h.startswith(prefix):
                return i
        raise SystemExit(f"column not found: {prefix}")

    ti, di, yi = col("title（"), col("doi（"), col("publication_year（")
    name_i = col("gene_name（")
    refs: list[dict] = []
    for k, row in enumerate(rows, 2):
        titles, dois, years = split_multi(row[ti]), split_multi(row[di]), split_multi(row[yi])
        for i in range(max(len(titles), len(dois), len(years))):
            title = titles[i] if i < len(titles) else ""
            doi = dois[i] if i < len(dois) else ""
            year = years[i] if i < len(years) else ""
            if not (title or doi or year):
                continue
            refs.append({"row": k, "gene": str(row[name_i] or ""), "doi": doi, "title": title,
                         "year": year})
    return refs


def norm_title(s: str) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", " ", str(s or "")))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def sim(a: str, b: str) -> float:
    na, nb = norm_title(a), norm_title(b)
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def year_of(item: dict) -> int | None:
    for key in ("issued", "published-print", "published-online", "created"):
        parts = ((item.get(key) or {}).get("date-parts") or [[None]])[0]
        if parts and parts[0]:
            try:
                return int(parts[0])
            except (TypeError, ValueError):
                pass
    return None


def authors_of(item: dict) -> list[str]:
    out = []
    for a in item.get("author") or []:
        given = (a.get("given") or "").strip()
        family = (a.get("family") or "").strip()
        if family and given:
            out.append(html.unescape(f"{given} {family}"))
        elif family or given or a.get("name"):
            out.append(html.unescape((family or given or a.get("name")).strip()))
    return out


def crossref(doi: str) -> dict | None:
    try:
        r = requests.get(f"https://api.crossref.org/works/{requests.utils.quote(doi, safe='')}",
                         headers=UA, timeout=25)
        if r.status_code != 200:
            return None
        item = r.json()["message"]
        return {
            "title": html.unescape(re.sub(r"<[^>]+>", "", (item.get("title") or [""])[0] or "")).strip(),
            "authors": authors_of(item),
            "journal": html.unescape(((item.get("container-title") or [""])[0] or "").strip())
            or ("bioRxiv (preprint)" if str(doi).lower().startswith("10.1101/") else
                ("Research Square (preprint)" if str(doi).lower().startswith("10.21203/") else "")),
            "year": year_of(item),
            "source": "crossref",
        }
    except Exception:
        return None


def pubmed_by_doi(doi: str) -> dict | None:
    try:
        r = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                         params={"db": "pubmed", "term": f'"{doi}"[DOI]', "retmode": "json"}, timeout=25)
        ids = r.json().get("esearchresult", {}).get("idlist") or []
        if not ids:
            return None
        return pubmed_summary(ids[0])
    except Exception:
        return None


def pubmed_summary(pmid: str) -> dict | None:
    try:
        r = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                         params={"db": "pubmed", "id": pmid, "retmode": "json"}, timeout=25)
        item = (r.json().get("result") or {}).get(pmid) or {}
        if not item:
            return None
        authors = []
        for a in item.get("authors") or []:
            name = (a.get("name") or "").strip()
            if name:
                authors.append(name)
        journal = item.get("fulljournalname") or item.get("source") or ""
        year = None
        for key in ("pubdate", "epubdate"):
            m = re.search(r"(\d{4})", item.get(key) or "")
            if m:
                year = int(m.group(1)); break
        return {"title": (item.get("title") or "").rstrip("."), "authors": authors,
                "journal": journal, "year": year, "source": "pubmed", "pmid": pmid}
    except Exception:
        return None


def pubmed_by_title(title: str) -> dict | None:
    try:
        r = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                         params={"db": "pubmed", "term": f'"{title}"[Title]', "retmode": "json"}, timeout=25)
        ids = r.json().get("esearchresult", {}).get("idlist") or []
        if not ids:
            return None
        res = pubmed_summary(ids[0])
        if res and sim(title, res.get("title", "")) >= 0.6:
            return res
        return None
    except Exception:
        return None


def enrich_ref(ref: dict) -> dict:
    doi = (ref.get("doi") or "").strip()
    title = (ref.get("title") or "").strip()
    table_year = ref.get("year")
    rec = None
    if doi:
        rec = crossref(doi)
        if not rec or not rec.get("authors") or sim(title, rec.get("title", "")) < 0.6:
            pm = pubmed_by_doi(doi)
            if pm and sim(title, pm.get("title", "")) >= 0.6:
                rec = {**pm, "doi": doi}
    if not rec and title:
        rec = pubmed_by_title(title)
    if not rec:
        return {"ref": ref, "meta": None}
    rec = dict(rec)
    rec["title_similarity"] = round(sim(title, rec.get("title", "")), 3) if title else None
    rec["verified"] = bool(title and rec["title_similarity"] is not None and rec["title_similarity"] >= 0.6)
    if table_year and rec.get("year"):
        try:
            rec["year_delta"] = abs(int(rec["year"]) - int(table_year))
        except ValueError:
            rec["year_delta"] = None
    rec["doi"] = doi or rec.get("doi")
    return {"ref": ref, "meta": rec}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default=None, help="直接从 KnownGene 17 列 Excel 构建参考文献列表")
    ap.add_argument("--input", default=DEFAULT_IN, help="refs JSON（无 --xlsx 时使用）")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    refs = refs_from_xlsx(args.xlsx) if args.xlsx else json.load(open(args.input, encoding="utf-8"))
    # unique DOI first; refs without DOI by title
    uniq: dict[str, dict] = {}
    for r in refs:
        doi = (r.get("doi") or "").strip().lower()
        if doi and doi not in uniq:
            uniq[doi] = r
    title_only = [r for r in refs if not (r.get("doi") or "").strip()]
    print(f"refs={len(refs)} unique_doi={len(uniq)} no_doi={len(title_only)}")
    doi_meta: dict[str, dict] = {}
    mismatched = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(enrich_ref, r): doi for doi, r in uniq.items()}
        for i, fut in enumerate(as_completed(futs), 1):
            doi = futs[fut]
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                print("ERR", doi, exc); continue
            meta = res.get("meta")
            if meta:
                doi_meta[doi] = meta
                if not meta.get("verified"):
                    mismatched.append((doi, uniq[doi].get("title", ""), meta.get("title", ""), meta.get("title_similarity")))
            if i % 50 == 0:
                print(f"crossref {i}/{len(uniq)} ok={len(doi_meta)}")
    title_meta: dict[str, dict] = {}
    for r in title_only:
        res = enrich_ref(r)
        if res.get("meta"):
            title_meta[norm_title(r.get("title", ""))] = res["meta"]
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "Crossref (DOI) + NCBI PubMed fallback; title-similarity verified >=0.6",
        "doi": doi_meta,
        "title": title_meta,
        "stats": {
            "refs": len(refs), "unique_doi": len(uniq), "no_doi": len(title_only),
            "doi_with_meta": len(doi_meta), "doi_verified": sum(1 for m in doi_meta.values() if m.get("verified")),
            "title_with_meta": len(title_meta), "mismatched": len(mismatched),
        },
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(out["stats"], ensure_ascii=False))
    if mismatched:
        print("unverified samples:", mismatched[:10])
    return 0


if __name__ == "__main__":
    sys.exit(main())
