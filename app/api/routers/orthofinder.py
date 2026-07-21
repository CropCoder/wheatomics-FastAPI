"""OrthoFinder orthogroup browser routes.

Returns raw JSON matching the PHP api.php format, so the front-end
app.js (shared with the PHP branch) works without modification.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.db.mysql import mysql_cursor

ORTHOFINDER_BASE_DIR = settings.ORTHOFINDER_BASE_DIR
ORTHOFINDER_DB = settings.DB_ORTHOFINDER
CLUSTER_FILE = settings.ORTHOFINDER_CLUSTER_FILE

router = APIRouter(prefix="/orthofinder", tags=["OrthoFinder"])

# Escape sequences keep the file portable.
_WS = " \t\n\r\x00\x0b'\""
_TAB = "\t"
_NL = "\n"
_TREE_WS = " \t\n\r"
_TREE_STOP = "(),:;"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _clean(s: str) -> str:
    return str(s).strip(_WS)

def _first_token(s: str) -> str:
    parts = re.split(r"\s+", _clean(s))
    return _clean(parts[0]) if parts and parts[0] else ""

def _norm_sub(s: str) -> str:
    s = _clean(s).upper()
    return s if s in ("A", "B", "D") else "Other"


# ---------------------------------------------------------------------------
# cluster map
# ---------------------------------------------------------------------------

_cluster_cache: tuple | None = None
_sorted_prefixes: list | None = None
_resolve_cache: dict = {}

def _load_cluster_map() -> tuple[dict, dict]:
    global _cluster_cache
    if _cluster_cache is not None:
        return _cluster_cache
    prefix_map: dict[str, int] = {}
    chrom_map: dict[str, int] = {}
    if CLUSTER_FILE.exists():
        for line in CLUSTER_FILE.read_text(encoding="utf-8").splitlines()[1:]:
            cols = line.split(_TAB)
            if len(cols) < 8:
                continue
            for c in range(1, 8):
                val = cols[c].strip()
                if not val:
                    continue
                if re.match(r"^chr\d+[ABD]$", val, re.I):
                    chrom_map[val.lower()] = c
                else:
                    prefix_map[val] = c
    _cluster_cache = (prefix_map, chrom_map)
    return _cluster_cache

def _get_sorted_prefixes() -> list:
    global _sorted_prefixes
    if _sorted_prefixes is not None:
        return _sorted_prefixes
    prefix_map, _ = _load_cluster_map()
    _sorted_prefixes = sorted(prefix_map.keys(), key=lambda x: -len(x))
    return _sorted_prefixes

def _resolve_cluster(gene_id: str, cursor=None) -> int | None:
    gene_id = _clean(gene_id)
    if gene_id in _resolve_cache:
        return _resolve_cache[gene_id]
    prefix_map, chrom_map = _load_cluster_map()
    result = None
    if prefix_map or chrom_map:
        for pfx in _get_sorted_prefixes():
            if gene_id.lower().startswith(pfx.lower()):
                result = prefix_map[pfx]
                break
        if result is None and chrom_map and cursor is not None:
            gh = hashlib.md5(gene_id.encode()).hexdigest()
            cursor.execute("SELECT chromosome FROM gene_positions WHERE gene_hash = %s LIMIT 1", (gh,))
            row = cursor.fetchone()
            if row and row["chromosome"].lower() in chrom_map:
                result = chrom_map[row["chromosome"].lower()]
    _resolve_cache[gene_id] = result
    return result

def _get_cluster_members(genes: list, target: int, cursor) -> list:
    members = []
    for g in genes:
        g = _clean(g)
        if not g:
            continue
        if _resolve_cluster(g, cursor) == target:
            members.append(g)
    return members


# ---------------------------------------------------------------------------
# sequence-id helpers — ported from PHP download.php
# ---------------------------------------------------------------------------

_seq_id_full_cache: dict | None = None

def _sequence_id_files() -> list:
    base = ORTHOFINDER_BASE_DIR
    return [
        base / "WorkingDirectory" / "SequenceIDs.txt",
        base / "SequenceIDs.txt",
        base.parent / "WorkingDirectory" / "SequenceIDs.txt",
    ]

def _load_all_sequence_ids() -> dict:
    """Parse SequenceIDs.txt ONCE and cache. Keyed by short_id/gene_id/raw_id."""
    global _seq_id_full_cache
    if _seq_id_full_cache is not None:
        return _seq_id_full_cache
    mp: dict = {}
    for f in _sequence_id_files():
        if not f.exists():
            continue
        try:
            with f.open("r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    m = re.match(r"^([^:\s]+)\s*:\s*(\S+)", line)
                    if not m:
                        m = re.match(r"^(\S+)\s+(\S+)", line)
                    if not m:
                        continue
                    short = _clean(m.group(1)); full = _clean(m.group(2))
                    if not short or not full:
                        continue
                    sp = _split_prefixed_gene(full)
                    _add_info(mp, _make_info(short, full, sp["genome_type"], sp["sub"]))
        except Exception:
            continue
        if mp:
            break
    _seq_id_full_cache = mp
    return mp

def _load_sequence_id_map(wanted) -> dict:
    """Return only the wanted subset from the cached full map (no re-read)."""
    full = _load_all_sequence_ids()
    if not full:
        return {}
    want: set[str] = set()
    for w in wanted:
        w = _first_token(w)
        if w:
            want.add(w)
            want.add(re.sub(r"\.\d+$", "", w))
    if not want:
        return {}
    out: dict = {}
    for key in want:
        info = full.get(key)
        if info:
            _add_info(out, info)
    return out

def _fetch_meta(cursor, names) -> dict:
    # Start from the (cached) SequenceIDs.txt map, then overlay DB rows.
    meta: dict = _load_sequence_id_map(names)
    clean = list({_first_token(n) for n in names if n and _first_token(n)})
    for chunk in _chunk_list(clean, 400):
        if not chunk:
            continue
        for field in ("short_id", "gene_id"):
            ph = ",".join(["%s"] * len(chunk))
            try:
                cursor.execute(
                    f"SELECT short_id,gene_id,genome_type,subgenome FROM sequence_ids WHERE {field} IN ({ph})",
                    chunk,
                )
                for r in cursor.fetchall():
                    info = _make_info(r["short_id"], r["gene_id"], r["genome_type"], r["subgenome"])
                    _add_info(meta, info)
            except Exception:
                pass
        hashes = [hashlib.md5(x.encode()).hexdigest() for x in chunk]
        ph2 = ",".join(["%s"] * len(hashes))
        try:
            cursor.execute(
                f"SELECT short_id,gene_id,genome_type,subgenome FROM sequence_ids WHERE gene_hash IN ({ph2})",
                hashes,
            )
            for r in cursor.fetchall():
                info = _make_info(r["short_id"], r["gene_id"], r["genome_type"], r["subgenome"])
                _add_info(meta, info)
        except Exception:
            pass
    return meta

def _make_info(short: str, gene: str, genome_type: str, sub: str) -> dict:
    short = _clean(short); gene = _clean(gene); genome_type = _clean(genome_type)
    sub = _norm_sub(sub)
    src = gene if gene else short
    sp = _split_prefixed_gene(src)
    if sp["gene"] != src and gene:
        gene = sp["gene"]
    if not genome_type and sp["genome_type"]:
        genome_type = sp["genome_type"]
    if sub == "Other" and sp["sub"] != "Other":
        sub = sp["sub"]
    if not genome_type:
        genome_type = "Unknown" if sub == "Other" else f"{sub}_subgenome"
    label_gene = gene if gene else (sp["gene"] if sp["gene"] else short)
    label = f"{label_gene} {genome_type}".strip()
    return {"short_id": short, "gene_id": gene, "raw_id": src,
            "genome_type": genome_type, "subgenome": sub,
            "label": label, "full_label": label}

def _add_info(mp: dict, info: dict):
    for k in ("short_id", "gene_id", "raw_id"):
        if info.get(k):
            mp[info[k]] = info

def _split_prefixed_gene(gid: str) -> dict:
    gid = _clean(gid)
    out = {"gene": gid, "genome_type": "", "sub": "Other"}
    m = re.match(r"^(.+)_([ABD])_(.+)$", gid, re.I)
    if m:
        out["gene"] = m.group(3); out["sub"] = m.group(2).upper()
        out["genome_type"] = f"{m.group(1)}_{out['sub']}_subgenome"
        return out
    m = re.match(r"^(.+?)\d([ABD])\d.*$", gid, re.I)
    if m:
        out["sub"] = m.group(2).upper()
        out["genome_type"] = f"{m.group(1)}_{out['sub']}_subgenome"
    return out


# ---------------------------------------------------------------------------
# Newick helpers
# ---------------------------------------------------------------------------

def _parse_newick_leaves(newick: str) -> list[str]:
    i, n = 0, len(newick)
    leaves = []

    def _skip():
        nonlocal i
        while i < n and newick[i] in _TREE_WS:
            i += 1

    def _read_name() -> str:
        nonlocal i
        _skip()
        if i >= n:
            return ""
        if newick[i] in ("'", '"'):
            q = newick[i]; i += 1; s = i
            while i < n and newick[i] != q: i += 1
            name = newick[s:i]
            if i < n: i += 1
            return _clean(name)
        s = i
        while i < n and newick[i] not in _TREE_STOP: i += 1
        return _clean(newick[s:i])

    def _read_length():
        nonlocal i
        _skip()
        if i < n and newick[i] == ":":
            i += 1
            while i < n and newick[i] not in _TREE_STOP: i += 1

    def _node():
        nonlocal i
        _skip()
        if i < n and newick[i] == "(":
            i += 1
            while i < n:
                _node(); _skip()
                if i < n and newick[i] == ",": i += 1; continue
                if i < n and newick[i] == ")": i += 1; break
                break
            _read_name(); _read_length()
        else:
            name = _read_name(); _read_length()
            if name: leaves.append(name)

    if newick: _node()
    return leaves


def _prune_newick(newick: str, keep_set: set) -> str:
    i, n = 0, len(newick)

    def _skip():
        nonlocal i
        while i < n and newick[i] in _TREE_WS: i += 1

    def _read_name() -> str:
        nonlocal i
        _skip()
        if i >= n: return ""
        if newick[i] in ("'", '"'):
            q = newick[i]; i += 1; s = i
            while i < n and newick[i] != q: i += 1
            name = newick[s:i]
            if i < n: i += 1
            return _clean(name)
        s = i
        while i < n and newick[i] not in _TREE_STOP: i += 1
        return _clean(newick[s:i])

    def _read_length() -> float:
        nonlocal i
        _skip()
        if i < n and newick[i] == ":":
            i += 1; s = i
            while i < n and newick[i] not in _TREE_STOP: i += 1
            try:
                v = float(newick[s:i])
                return v if v == v else 0.0
            except ValueError: return 0.0
        return 0.0

    def _parse() -> dict:
        nonlocal i
        _skip()
        node = {"name": "", "length": 0.0, "children": []}
        if i < n and newick[i] == "(":
            i += 1
            while i < n:
                node["children"].append(_parse()); _skip()
                if i < n and newick[i] == ",": i += 1; continue
                if i < n and newick[i] == ")": i += 1; break
                break
            node["name"] = _read_name(); node["length"] = _read_length()
        else:
            node["name"] = _read_name(); node["length"] = _read_length()
        return node

    def _annotate(node: dict):
        if not node["children"]:
            nm = _clean(node["name"]); n0 = re.sub(r"\.\d+$", "", nm)
            node["_keep"] = nm in keep_set or n0 in keep_set or _first_token(nm) in keep_set
            node["_leaf_count"] = 1 if node["_keep"] else 0
            return
        node["_keep"] = False; node["_leaf_count"] = 0
        for c in node["children"]:
            _annotate(c)
            if c["_keep"]: node["_keep"] = True
            node["_leaf_count"] += c["_leaf_count"]

    def _serialize(node: dict) -> str:
        if not node["children"]:
            if not node["_keep"]: return ""
            lpart = f":{node['length']:.6g}" if node["length"] > 0 else ""
            return node["name"] + lpart
        if node["_leaf_count"] == 0: return ""
        kept = [s for s in (_serialize(c) for c in node["children"]) if s]
        if not kept: return ""
        if len(kept) == 1: return kept[0]
        inner = ",".join(kept)
        npart = node["name"] if node["name"] else ""
        lpart = f":{node['length']:.6g}" if node["length"] > 0 else ""
        return f"({inner}){npart}{lpart}"

    if not newick: return ""
    root = _parse()
    if not root.get("children"): return ""
    _annotate(root)
    result = _serialize(root)
    return result + ";" if result else ""


def _build_prune_keep_set(cluster_genes: list, meta: dict, tree_leaves: list) -> set:
    """Map tree leaves → meta → gene_id → check against cluster_genes.

    Enriched crosswalk: tries leaf→meta directly, leaf token in meta,
    without-version, genome-number prefix strip, then unique suffix guard.
    """
    if not cluster_genes or not tree_leaves:
        return set()
    cluster_set = {_clean(cg) for cg in cluster_genes if _clean(cg)}
    cluster_list = sorted(cluster_set, key=lambda x: -len(x))
    keep: set[str] = set()
    for lf in tree_leaves:
        lf = _clean(lf)
        if not lf: continue
        matched = False

        # 1) leaf directly keyed in meta → check gene_id / raw_id / short_id
        if lf in meta:
            for f in ("gene_id", "raw_id", "short_id"):
                v = _clean(meta[lf].get(f, ""))
                if v and v in cluster_set:
                    matched = True; break

        # 2) first-token of leaf (genome-prefixed name) in meta
        lf_tok = _first_token(lf)
        if not matched and lf_tok and lf_tok != lf and lf_tok in meta:
            for f in ("gene_id", "raw_id", "short_id"):
                v = _clean(meta[lf_tok].get(f, ""))
                if v and v in cluster_set:
                    matched = True; break

        # 3) without-version variants
        if not matched:
            lf_nv = re.sub(r"\.\d+$", "", lf)
            if lf_nv != lf and lf_nv in meta:
                for f in ("gene_id", "raw_id", "short_id"):
                    v = _clean(meta[lf_nv].get(f, ""))
                    if v and v in cluster_set:
                        matched = True; break
        if not matched:
            lf_tok_nv = re.sub(r"\.\d+$", "", lf_tok) if lf_tok else ""
            if lf_tok_nv and lf_tok_nv != lf_tok and lf_tok_nv in meta:
                for f in ("gene_id", "raw_id", "short_id"):
                    v = _clean(meta[lf_tok_nv].get(f, ""))
                    if v and v in cluster_set:
                        matched = True; break

        # 4) strip genome-number prefix (e.g. "3_127" → "127")
        if not matched:
            parts = lf.split("_", 1)
            if len(parts) == 2 and parts[1] and parts[1] in meta:
                for f in ("gene_id", "raw_id", "short_id"):
                    v = _clean(meta[parts[1]].get(f, ""))
                    if v and v in cluster_set:
                        matched = True; break

        # 5) unique suffix guard: leaf token ends with cluster gene, but
        #    ONLY when exactly one cluster gene matches (avoids false match)
        if not matched:
            lf_tok_val = _first_token(lf)
            lf_tok_nv_val = re.sub(r"\.\d+$", "", lf_tok_val)
            cands = [cg for cg in cluster_list
                     if lf_tok_val == cg
                     or lf_tok_val.endswith("_" + cg)
                     or lf_tok_val.endswith(cg)
                     or lf_tok_nv_val == cg
                     or (lf_tok_nv_val and lf_tok_nv_val.endswith("_" + cg))
                     or (lf_tok_nv_val and lf_tok_nv_val.endswith(cg))]
            if len(set(cands)) == 1:
                matched = True

        if matched: keep.add(lf)
    return keep


# ---------------------------------------------------------------------------
# alignment helpers
# ---------------------------------------------------------------------------

def _parse_alignment(aln: str) -> tuple[dict, list]:
    records, order = {}, []
    cur = None
    for line in aln.splitlines():
        if line.startswith(">"):
            cur = _first_token(line[1:])
            if cur and cur not in records:
                records[cur] = []; order.append(cur)
        elif cur:
            records[cur].append(line.rstrip())
    return records, order

_aln_path_cache: dict = {}

def _find_alignment_file(og_id: str) -> Path | None:
    if og_id in _aln_path_cache:
        return _aln_path_cache[og_id]
    base = ORTHOFINDER_BASE_DIR
    candidates = [
        base / "WorkingDirectory" / "MultipleSequenceAlignments" / f"{og_id}.fa",
        base / "WorkingDirectory" / "MultipleSequenceAlignments" / f"{og_id}.fasta",
        base / "MultipleSequenceAlignments" / f"{og_id}.fa",
        base / "MultipleSequenceAlignments" / f"{og_id}.fasta",
        base / "WorkingDirectory" / "Alignments_ids" / f"{og_id}.fa",
        base / "WorkingDirectory" / "Alignments_ids" / f"{og_id}.fasta",
        base / "WorkingDirectory" / "Alignments" / f"{og_id}.fa",
        base / "WorkingDirectory" / "Alignments" / f"{og_id}.fasta",
        base / "Alignments_ids" / f"{og_id}.fa",
        base / "Alignments" / f"{og_id}.fa",
    ]
    found = next((p for p in candidates if p.exists()), None)
    _aln_path_cache[og_id] = found
    return found

def _chunk_list(lst, size):
    return [lst[i:i+size] for i in range(0, len(lst), size)]


# ---- genome-aware leaf↔record matching (from 3d31957) -----------------------

def _genome_type_of(name: str, meta: dict) -> str:
    """Best-effort genome_type for a leaf or record id.

    Looks up by short_id → gene_id → genome_type (short_ids are unique per
    genome, so this never collides).  Falls back to splitting the prefixed
    name (e.g. Chinese_Spring1.1_A_TraesCS... → Chinese_Spring1.1_A_subgenome).
    """
    tok = _first_token(name)
    info = meta.get(tok)
    if info and info.get("genome_type"):
        return info["genome_type"]
    sp = _split_prefixed_gene(tok)
    gene = sp["gene"]
    if gene and gene != tok:
        info2 = meta.get(gene)
        if info2 and info2.get("genome_type"):
            return info2["genome_type"]
    return sp["genome_type"]


def _match_keys(name: str, meta: dict) -> set:
    """All normalized gene-level keys a leaf/record can be matched by."""
    tok = _first_token(name)
    sp = _split_prefixed_gene(tok)
    ks: set = set()
    for v in (tok, sp["gene"]):
        if v:
            ks.add(v)
            ks.add(re.sub(r"\.\d+$", "", v))
    info = meta.get(tok)
    if info:
        for f in ("short_id", "gene_id", "raw_id"):
            v = info.get(f)
            if v:
                ks.add(v)
                ks.add(re.sub(r"\.\d+$", "", v))
    return ks


def _ordered_record_ids(leaf_order, record_order, records, meta, include_unmatched=True):
    """Port of PHP d_ordered(): tree-leaf order, genome-aware one-to-one.

    Two records can share the same gene_id but come from different genomes
    (e.g. TraesCS1A02G219700.1 in Chinese_Spring1.1_A and in
    Triticum_aestivum_alchemy_A).  Each leaf carries a genome prefix, and
    each record's short_id is unique — we disambiguate by genome_type so
    each leaf gets its own record and nothing is dropped.

    include_unmatched=True  → append leftover records at end (whole OG).
    include_unmatched=False → only records assigned to a leaf (cluster mode).
    """
    rec_genome: dict = {}
    key_to_recs: dict = {}
    for rid in records:
        rec_genome[rid] = _genome_type_of(rid, meta)
        for k in _match_keys(rid, meta):
            key_to_recs.setdefault(k, [])
            if rid not in key_to_recs[k]:
                key_to_recs[k].append(rid)

    rec_ids_by_len = sorted(records.keys(), key=lambda x: -len(x))

    ordered, used = [], set()
    for leaf in leaf_order:
        leaf_tok = _first_token(leaf)
        leaf_gt = _genome_type_of(leaf, meta)

        cand: list = []
        for k in _match_keys(leaf, meta):
            for rid in key_to_recs.get(k, []):
                if rid not in used and rid not in cand:
                    cand.append(rid)

        if not cand:
            for rid in rec_ids_by_len:
                if rid in used:
                    continue
                if leaf_tok == rid or leaf_tok.endswith("_" + rid) or leaf_tok.endswith(rid):
                    cand.append(rid)

        chosen = None
        if len(cand) == 1:
            chosen = cand[0]
        elif cand:
            gt_hits = [r for r in cand if leaf_gt and rec_genome.get(r) == leaf_gt]
            if len(gt_hits) == 1:
                chosen = gt_hits[0]
            elif len(gt_hits) > 1:
                pool = sorted(gt_hits, key=lambda r: len(r), reverse=True)
                chosen = pool[0]
            else:
                pool = sorted(cand, key=lambda r: len(r), reverse=True)
                chosen = pool[0]

        if chosen and chosen in records and chosen not in used:
            ordered.append(chosen); used.add(chosen)

    if include_unmatched:
        for rid in record_order:
            if rid not in used:
                ordered.append(rid)
    return ordered

def _label_for(id, meta):
    """Build display label — mirrors PHP d_label()."""
    return meta.get(id, {}).get("full_label", id)


# ===================================================================
# API endpoints  (raw JSON matching PHP api.php format)
# ===================================================================

@router.get(
    "/api.php",
    summary="Search by protein ID / orthogroup ID / species catalog / members / positions",
    description="PHP api.php compatible endpoint (action=search|species_catalog|members|positions).",
)
def search_php(
    q: str = Query("", description="Protein/gene ID or orthogroup ID."),
    action: str = Query("search", description="Action: 'search' | 'species_catalog' | 'members' | 'positions'"),
    og: str = Query("", description="Orthogroup ID, required for action=members and action=positions"),
    sub: str = Query("", description="Subgenome filter (A/B/D), used with action=members"),
    cluster: int = Query(0, description="Cluster filter (1-7), used with action=positions"),
    species: str = Query("", description="Species filter for gene search (optional)"),
    _: int = Query(0, description="Cache-buster (optional)"),
):
    if action == "species_catalog":
        species = []
        if CLUSTER_FILE.exists():
            for line in CLUSTER_FILE.read_text(encoding="utf-8").splitlines()[1:]:
                cols = line.split(_TAB)
                if len(cols) >= 8:
                    raw = re.sub(r"^\d+:\s*", "", cols[0].strip())
                    raw = re.sub(r"_[ABD]\.pep$", "", raw, flags=re.I)
                    if raw and raw not in species:
                        species.append(raw)
        return {"species": species}

    if action == "members":
        if not re.match(r"^OG\d+$", og):
            return {"error": "Invalid orthogroup"}
        sub = _norm_sub(sub)
        with mysql_cursor(ORTHOFINDER_DB) as cur:
            cur.execute("SELECT genes FROM orthogroups WHERE og_id = %s LIMIT 1", (og,))
            row = cur.fetchone()
            if not row:
                return {"error": "Orthogroup not found"}
            genes = [g for g in row["genes"].split() if g]
            meta = _fetch_meta(cur, genes)
            items = {}
            for g in genes:
                info = meta.get(g, _make_info("", g, "", ""))
                if _norm_sub(info["subgenome"]) != sub: continue
                gt = info["genome_type"] or "Unknown"
                items.setdefault(gt, []).append(info.get("gene_id") or g)
            for arr in items.values():
                arr.sort()
            return {"items": dict(sorted(items.items()))}

    if action == "positions":
        if not re.match(r"^OG\d+$", og):
            return {"error": "Invalid orthogroup"}
        with mysql_cursor(ORTHOFINDER_DB) as cur:
            cur.execute("SELECT genes FROM orthogroups WHERE og_id = %s LIMIT 1", (og,))
            row = cur.fetchone()
            if not row:
                return {"error": "Orthogroup not found"}
            genes = [g for g in row["genes"].split() if g]
            gene_hashes = []
            for g in genes:
                g = _clean(g)
                if not g: continue
                if cluster > 0 and _resolve_cluster(g, cur) != cluster:
                    continue
                gene_hashes.append(hashlib.md5(g.encode()).hexdigest())
            if not gene_hashes:
                return {"positions": [], "chromosomes": [], "genomes": []}
            result = []
            for chunk in _chunk_list(gene_hashes, 500):
                ph = ",".join(["%s"] * len(chunk))
                try:
                    cur.execute(
                        f"SELECT gene_id,chromosome,start_pos,end_pos,genome,subgenome "
                        f"FROM gene_positions WHERE gene_hash IN ({ph})", chunk)
                    for r in cur.fetchall():
                        info = _make_info("", r["gene_id"], "", r.get("subgenome", ""))
                        result.append({
                            "gene_id": r["gene_id"], "chromosome": r["chromosome"],
                            "start": int(r["start_pos"]), "end": int(r["end_pos"]),
                            "genome": r["genome"], "subgenome": r.get("subgenome", "Other"),
                            "label": info["full_label"],
                        })
                except Exception: pass
            chromosomes = sorted(set(r["chromosome"] for r in result))
            genomes = sorted(set(r["genome"] for r in result))
            return {"positions": result, "chromosomes": chromosomes, "genomes": genomes}

    # -- main search --
    q = q.strip()
    if not q:
        return {"error": "Please input a protein ID or orthogroup ID."}

    with mysql_cursor(ORTHOFINDER_DB) as cur:
        if re.match(r"^OG\d+$", q):
            og_id = q
        else:
            cand_ids = [q]
            if species:
                cand_ids.append(f"{species}_{q}")
            row = None
            for cid in {c for c in cand_ids if c}:
                cur.execute(
                    "SELECT og_id FROM gene_to_og WHERE gene_hash = MD5(%s) AND gene_id = %s LIMIT 1",
                    (cid, cid),
                )
                row = cur.fetchone()
                if row:
                    break
            if not row:
                return {"error": "Protein ID was not found."}
            og_id = row["og_id"]

        cur.execute("SELECT genes,gene_count FROM orthogroups WHERE og_id = %s LIMIT 1", (og_id,))
        og_row = cur.fetchone()
        if not og_row:
            return {"error": "Orthogroup was not found."}

        genes = [g for g in og_row["genes"].split() if g]
        gene_count = og_row["gene_count"]

        tree_file = ORTHOFINDER_BASE_DIR / "WorkingDirectory" / "Resolved_Gene_Trees" / f"{og_id}.txt"
        aln_file = _find_alignment_file(og_id)
        tree = tree_file.read_text(encoding="utf-8") if tree_file.exists() else ""
        alignment = aln_file.read_text(encoding="utf-8") if aln_file else ""

        leaf_order = _parse_newick_leaves(tree) if tree else []
        records, record_order = _parse_alignment(alignment) if alignment else ({}, [])

        meta = _fetch_meta(cur, leaf_order + record_order + genes)

        tree_label_map = {}
        for rid in set(leaf_order + record_order + genes):
            if rid in meta:
                _add_info(tree_label_map, meta[rid])
            else:
                _add_info(tree_label_map, _make_info("", rid, "", ""))

        sub_counts = {"A": 0, "B": 0, "D": 0, "Other": 0}
        for g in genes:
            info = meta.get(g, _make_info("", g, "", ""))
            sub_counts[_norm_sub(info["subgenome"])] += 1

        query_cluster = _resolve_cluster(q, cur)
        cluster_genes = _get_cluster_members(genes, query_cluster, cur) if query_cluster is not None else []
        cluster_sub_counts = {"A": 0, "B": 0, "D": 0, "Other": 0}
        for g in cluster_genes:
            info = meta.get(g, _make_info("", g, "", ""))
            cluster_sub_counts[_norm_sub(info["subgenome"])] += 1

        cluster_tree = ""
        debug_prune = {}
        if query_cluster is not None and tree:
            tree_leaves = _parse_newick_leaves(tree)
            debug_prune = {
                "query_cluster": query_cluster,
                "cluster_genes_n": len(cluster_genes),
                "tree_leaves_n": len(tree_leaves),
            }
            keep = _build_prune_keep_set(cluster_genes, meta, tree_leaves)
            debug_prune["keep_count"] = len(keep)
            ok_samp = [lf for lf in tree_leaves[:60] if _clean(lf) in keep][:5]
            nok_samp = [lf for lf in tree_leaves[:60] if _clean(lf) not in keep][:5]
            debug_prune["sample_ok"] = ok_samp
            debug_prune["sample_nok"] = nok_samp
            if keep:
                pruned = _prune_newick(tree, keep)
                if pruned: cluster_tree = pruned
                pl = _parse_newick_leaves(cluster_tree) if cluster_tree else []
                debug_prune["pruned_leaf_count"] = len(pl)
            else:
                debug_prune["pruned_leaf_count"] = 0

        return {
            "query": q, "orthogroup": og_id, "gene_count": gene_count,
            "sub_counts": sub_counts, "tree": tree,
            "cluster_tree": cluster_tree, "debug_prune": debug_prune,
            "tree_label_map": {k: {
                "full_label": v.get("full_label", v.get("label", k)),
                "gene_id": v.get("gene_id", k),
                "short_id": v.get("short_id", ""),
                "raw_id": v.get("raw_id", v.get("gene_id", k)),
                "subgenome": v.get("subgenome", "Other"),
                "genome_type": v.get("genome_type", ""),
            } for k, v in tree_label_map.items()},
            "rectangular_leaf_order": leaf_order,
            "tree_leaf_count": len(leaf_order),
            "query_cluster": query_cluster,
            "cluster_gene_count": len(cluster_genes),
            "cluster_genes": cluster_genes,
            "cluster_sub_counts": cluster_sub_counts,
        }


# ---------------------------------------------------------------------------
# download helpers
# ---------------------------------------------------------------------------

def _load_tree_text(og: str) -> str:
    tree_file = ORTHOFINDER_BASE_DIR / "WorkingDirectory" / "Resolved_Gene_Trees" / f"{og}.txt"
    return tree_file.read_text(encoding="utf-8") if tree_file.exists() else ""


def _prune_tree_to_cluster(cur, og: str, tree: str, cluster: int) -> str:
    """Prune a tree to one homoeologous cluster. Shared by tree & alignment
    downloads so they derive from the exact same pruned newick."""
    if not (1 <= cluster <= 7) or not tree:
        return tree
    cur.execute("SELECT genes FROM orthogroups WHERE og_id = %s LIMIT 1", (og,))
    row = cur.fetchone()
    if not row:
        return tree
    genes = [g for g in row["genes"].split() if g]
    c_genes = _get_cluster_members(genes, cluster, cur)
    leaves = _parse_newick_leaves(tree)
    meta = _fetch_meta(cur, leaves + c_genes)
    keep = _build_prune_keep_set(c_genes, meta, leaves)
    if keep:
        pruned = _prune_newick(tree, keep)
        if pruned:
            return pruned
    return tree


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------

@router.get(
    "/download",
    summary="Download gene tree (Newick) or multiple sequence alignment (FASTA)",
    description="""Download orthogroup data files:

**type=tree** — Gene tree in Newick format. Add `cluster=N` (1-7) to prune to cluster members only.

**type=alignment** — Multiple sequence alignment in FASTA format, ordered by tree leaf order.

Each alignment follows the leaf order of its paired tree.
""",)
def download_file(
    og: str = Query(..., description="Orthogroup ID, e.g. OG0001897"),
    type: str = Query("tree", description="File type: 'tree' or 'alignment'"),
    cluster: int = Query(0, description="Cluster number (1-7) for tree pruning or alignment filtering. 0 = full OG."),
):
    if not re.match(r"^OG\d+$", og):
        raise HTTPException(400, "Invalid OG ID")

    # ---- Download OG tree / Download homoeologous tree ----
    if type == "tree":
        tree = _load_tree_text(og)
        if not tree:
            raise HTTPException(404, "Tree file not found")
        if 1 <= cluster <= 7:
            with mysql_cursor(ORTHOFINDER_DB) as cur:
                tree = _prune_tree_to_cluster(cur, og, tree, cluster)
        suffix = f".HomoeologousGroup{cluster}.tree.txt" if cluster else ".tree.txt"
        return PlainTextResponse(
            tree, media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{og}{suffix}"'})

    # ---- Download OG alignment / Download homoeologous alignment ----
    if type == "alignment":
        aln_file = _find_alignment_file(og)
        if not aln_file:
            raise HTTPException(404, "Alignment file not found")
        alignment = aln_file.read_text(encoding="utf-8")
        records, record_order = _parse_alignment(alignment)
        tree = _load_tree_text(og)

        with mysql_cursor(ORTHOFINDER_DB) as cur:
            tree_leaves_full = _parse_newick_leaves(tree) if tree else []

            if 1 <= cluster <= 7 and tree:
                pruned = _prune_tree_to_cluster(cur, og, tree, cluster)
                leaf_order = _parse_newick_leaves(pruned)
                include_unmatched = False

                # Include cluster gene IDs in meta so the crosswalk has every
                # gene-level key needed for leaf→record matching.
                cur.execute("SELECT genes FROM orthogroups WHERE og_id = %s LIMIT 1", (og,))
                row = cur.fetchone()
                c_genes_for_meta = []
                if row:
                    genes_all = [g for g in row["genes"].split() if g]
                    c_genes_for_meta = _get_cluster_members(genes_all, cluster, cur)
                meta = _fetch_meta(cur, tree_leaves_full + list(records.keys()) + c_genes_for_meta)
            else:
                leaf_order = tree_leaves_full
                include_unmatched = True
                meta = _fetch_meta(cur, tree_leaves_full + list(records.keys()))

            ordered = _ordered_record_ids(
                leaf_order, record_order, records, meta,
                include_unmatched=include_unmatched,
            )

        out_lines = []
        for sid in ordered:
            if sid in records:
                out_lines.append(">" + _label_for(sid, meta))
                out_lines.append(_NL.join(records[sid]))

        cluster_suffix = f".HomoeologousGroup{cluster}" if cluster else ""
        body = _NL.join(out_lines) + _NL
        return PlainTextResponse(
            body, media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{og}{cluster_suffix}.alignment.fa"'})

    raise HTTPException(400, "Invalid type")
