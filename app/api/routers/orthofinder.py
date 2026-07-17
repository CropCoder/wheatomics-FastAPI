"""OrthoFinder orthogroup browser routes — cluster filtering + synteny + downloads."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.core.response import ok
from app.db.mysql import mysql_cursor

ORTHOFINDER_BASE_DIR = settings.ORTHOFINDER_BASE_DIR
ORTHOFINDER_DB = settings.DB_ORTHOFINDER
CLUSTER_FILE = settings.ORTHOFINDER_CLUSTER_FILE

router = APIRouter(prefix="/orthofinder", tags=["OrthoFinder"])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _clean(s: str) -> str:
    return s.strip(" \t\n\r\0\x0B'\"")

def _first_token(s: str) -> str:
    parts = _clean(s).split()
    return _clean(parts[0]) if parts else ""

def _norm_sub(s: str) -> str:
    s = s.upper()
    return s if s in ("A", "B", "D") else "Other"

def _split_prefixed_gene(gid: str) -> dict:
    gid = _clean(gid)
    out = {"gene": gid, "genome_type": "", "sub": "Other"}
    m = re.match(r"^(.+)_([ABD])_(.+)$", gid, re.I)
    if m:
        out["gene"] = m.group(3)
        out["sub"] = m.group(2).upper()
        out["genome_type"] = f"{m.group(1)}_{out['sub']}_subgenome"
        return out
    m = re.match(r"^(.+?)\d([ABD])\d.*$", gid, re.I)
    if m:
        out["sub"] = m.group(2).upper()
        out["genome_type"] = f"{m.group(1)}_{out['sub']}_subgenome"
    return out

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


# ---------------------------------------------------------------------------
# cluster map
# ---------------------------------------------------------------------------

_cluster_cache: tuple | None = None
_sorted_prefixes: list | None = None

def _load_cluster_map() -> tuple[dict, dict]:
    global _cluster_cache
    if _cluster_cache is not None:
        return _cluster_cache

    prefix_map: dict[str, int] = {}
    chrom_map: dict[str, int] = {}

    if CLUSTER_FILE.exists():
        lines = CLUSTER_FILE.read_text(encoding="utf-8").splitlines()
        for line in lines[1:]:  # skip header
            cols = line.split("\t")
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

def resolve_cluster(gene_id: str, cursor=None) -> int | None:
    gene_id = _clean(gene_id)
    prefix_map, chrom_map = _load_cluster_map()
    if not prefix_map and not chrom_map:
        return None

    for pfx in _get_sorted_prefixes():
        if gene_id.lower().startswith(pfx.lower()):
            return prefix_map[pfx]

    if chrom_map and cursor is not None:
        gh = hashlib.md5(gene_id.encode()).hexdigest()
        cursor.execute("SELECT chromosome FROM gene_positions WHERE gene_hash = %s LIMIT 1", (gh,))
        row = cursor.fetchone()
        if row:
            chrom = row["chromosome"].lower()
            if chrom in chrom_map:
                return chrom_map[chrom]

    return None

def get_cluster_members(genes: list, target: int, cursor) -> list:
    members = []
    for g in genes:
        g = _clean(g)
        if not g:
            continue
        if resolve_cluster(g, cursor) == target:
            members.append(g)
    return members


# ---------------------------------------------------------------------------
# sequence-id map helpers
# ---------------------------------------------------------------------------

def _fetch_meta(cursor, names: list[str]) -> dict:
    """Load sequence_id mapping for a list of names (short_id/gene_id)."""
    meta: dict = {}
    clean = list({_first_token(n) for n in names if _first_token(n)})
    for chunk in _chunk_list(clean, 400):
        if not chunk:
            continue
        for field in ("short_id", "gene_id"):
            ph = ",".join(["%s"] * len(chunk))
            try:
                cursor.execute(
                    f"SELECT short_id, gene_id, genome_type, subgenome FROM sequence_ids WHERE {field} IN ({ph})",
                    chunk,
                )
                for r in cursor.fetchall():
                    info = _make_info(r["short_id"], r["gene_id"],
                                      r["genome_type"], r["subgenome"])
                    for k in ("short_id", "gene_id", "raw_id"):
                        if info.get(k):
                            meta[info[k]] = info
            except Exception:
                pass
        hashes = [hashlib.md5(x.encode()).hexdigest() for x in chunk]
        ph2 = ",".join(["%s"] * len(hashes))
        try:
            cursor.execute(
                f"SELECT short_id, gene_id, genome_type, subgenome FROM sequence_ids WHERE gene_hash IN ({ph2})",
                hashes,
            )
            for r in cursor.fetchall():
                info = _make_info(r["short_id"], r["gene_id"],
                                  r["genome_type"], r["subgenome"])
                for k in ("short_id", "gene_id", "raw_id"):
                    if info.get(k):
                        meta[info[k]] = info
        except Exception:
            pass
    return meta


# ---------------------------------------------------------------------------
# Newick tree helpers
# ---------------------------------------------------------------------------

def _parse_newick_leaves(newick: str) -> list[str]:
    i, n = 0, len(newick)
    leaves = []

    def _skip():
        nonlocal i
        while i < n and newick[i] in " \t\r\n":
            i += 1

    def _read_name() -> str:
        nonlocal i
        _skip()
        if i >= n:
            return ""
        if newick[i] in ("'", '"'):
            q = newick[i]; i += 1
            s = i
            while i < n and newick[i] != q:
                i += 1
            name = newick[s:i]
            if i < n:
                i += 1
            return _clean(name)
        s = i
        while i < n and newick[i] not in "(),:;":
            i += 1
        return _clean(newick[s:i])

    def _read_length():
        nonlocal i
        _skip()
        if i < n and newick[i] == ":":
            i += 1
            while i < n and newick[i] not in "(),:;":
                i += 1

    def _node():
        nonlocal i
        _skip()
        if i < n and newick[i] == "(":
            i += 1
            while i < n:
                _node()
                _skip()
                if i < n and newick[i] == ",":
                    i += 1
                    continue
                if i < n and newick[i] == ")":
                    i += 1
                    break
                break
            _read_name(); _read_length()
        else:
            name = _read_name(); _read_length()
            if name:
                leaves.append(name)

    if newick:
        _node()
    return leaves


def _prune_newick(newick: str, keep_set: set) -> str:
    """Prune a Newick tree, keeping only leaves in keep_set. Collapses single-child nodes."""
    i, n = 0, len(newick)

    def _skip():
        nonlocal i
        while i < n and newick[i] in " \t\r\n":
            i += 1

    def _read_name() -> str:
        nonlocal i
        _skip()
        if i >= n:
            return ""
        if newick[i] in ("'", '"'):
            q = newick[i]; i += 1
            s = i
            while i < n and newick[i] != q:
                i += 1
            name = newick[s:i]
            if i < n:
                i += 1
            return _clean(name)
        s = i
        while i < n and newick[i] not in "(),:;":
            i += 1
        return _clean(newick[s:i])

    def _read_length() -> float:
        nonlocal i
        _skip()
        if i < n and newick[i] == ":":
            i += 1
            s = i
            while i < n and newick[i] not in "(),:;":
                i += 1
            try:
                v = float(newick[s:i])
                return v if v == v else 0.0  # NaN check
            except ValueError:
                return 0.0
        return 0.0

    def _parse() -> dict:
        nonlocal i
        _skip()
        node = {"name": "", "length": 0.0, "children": []}
        if i < n and newick[i] == "(":
            i += 1
            while i < n:
                node["children"].append(_parse())
                _skip()
                if i < n and newick[i] == ",":
                    i += 1
                    continue
                if i < n and newick[i] == ")":
                    i += 1
                    break
                break
            node["name"] = _read_name()
            node["length"] = _read_length()
        else:
            node["name"] = _read_name()
            node["length"] = _read_length()
        return node

    def _annotate(node: dict):
        if not node["children"]:
            n = _clean(node["name"])
            n0 = re.sub(r"\.\d+$", "", n)
            node["_keep"] = n in keep_set or n0 in keep_set or _first_token(n) in keep_set
            node["_leaf_count"] = 1 if node["_keep"] else 0
            return
        node["_keep"] = False
        node["_leaf_count"] = 0
        for child in node["children"]:
            _annotate(child)
            if child["_keep"]:
                node["_keep"] = True
            node["_leaf_count"] += child["_leaf_count"]

    def _serialize(node: dict) -> str:
        if not node["children"]:
            if not node["_keep"]:
                return ""
            lpart = f":{node['length']:.6g}" if node["length"] > 0 else ""
            return node["name"] + lpart
        if node["_leaf_count"] == 0:
            return ""
        kept = [s for s in (_serialize(c) for c in node["children"]) if s]
        if not kept:
            return ""
        if len(kept) == 1:
            return kept[0]
        inner = ",".join(kept)
        npart = node["name"] if node["name"] else ""
        lpart = f":{node['length']:.6g}" if node["length"] > 0 else ""
        return f"({inner}){npart}{lpart}"

    if not newick:
        return ""
    root = _parse()
    if not root.get("children"):
        return ""
    _annotate(root)
    result = _serialize(root)
    return result + ";" if result else ""


def _build_prune_keep_set(cluster_genes: list[str], meta: dict, tree_leaves: list[str]) -> set:
    """Map tree leaves → meta → gene_id → check against cluster_genes."""
    if not cluster_genes or not tree_leaves:
        return set()

    cluster_set = {_clean(cg) for cg in cluster_genes if _clean(cg)}
    keep: set[str] = set()

    for lf in tree_leaves:
        lf = _clean(lf)
        if not lf:
            continue

        matched = False

        # Method 1: leaf directly in meta
        if lf in meta:
            gid = _clean(meta[lf].get("gene_id", ""))
            rid = _clean(meta[lf].get("raw_id", ""))
            if (gid and gid in cluster_set) or (rid and rid in cluster_set):
                matched = True

        # Method 2: strip version suffix
        if not matched:
            lf_nv = re.sub(r"\.\d+$", "", lf)
            if lf_nv != lf and lf_nv in meta:
                gid = _clean(meta[lf_nv].get("gene_id", ""))
                if gid and gid in cluster_set:
                    matched = True

        # Method 3: strip genome_number prefix
        if not matched:
            parts = lf.split("_", 1)
            if len(parts) == 2 and parts[1] and parts[1] in meta:
                gid = _clean(meta[parts[1]].get("gene_id", ""))
                if gid and gid in cluster_set:
                    matched = True

        if matched:
            keep.add(lf)

    return keep


# ---------------------------------------------------------------------------
# alignment helpers
# ---------------------------------------------------------------------------

def _find_alignment_file(og_id: str) -> Path | None:
    candidates = [
        ORTHOFINDER_BASE_DIR / "WorkingDirectory" / "MultipleSequenceAlignments" / f"{og_id}.fa",
        ORTHOFINDER_BASE_DIR / "WorkingDirectory" / "MultipleSequenceAlignments" / f"{og_id}.fasta",
        ORTHOFINDER_BASE_DIR / "MultipleSequenceAlignments" / f"{og_id}.fa",
        ORTHOFINDER_BASE_DIR / "MultipleSequenceAlignments" / f"{og_id}.fasta",
        ORTHOFINDER_BASE_DIR / "WorkingDirectory" / "Alignments_ids" / f"{og_id}.fa",
        ORTHOFINDER_BASE_DIR / "WorkingDirectory" / "Alignments_ids" / f"{og_id}.fasta",
        ORTHOFINDER_BASE_DIR / "WorkingDirectory" / "Alignments" / f"{og_id}.fa",
        ORTHOFINDER_BASE_DIR / "WorkingDirectory" / "Alignments" / f"{og_id}.fasta",
        ORTHOFINDER_BASE_DIR / "Alignments_ids" / f"{og_id}.fa",
        ORTHOFINDER_BASE_DIR / "Alignments" / f"{og_id}.fa",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _parse_alignment(aln: str) -> tuple[dict, list]:
    records: dict = {}
    order: list[str] = []
    cur_id = None
    for line in aln.splitlines():
        if line.startswith(">"):
            cur_id = _first_token(line[1:])
            if cur_id and cur_id not in records:
                records[cur_id] = []
                order.append(cur_id)
        elif cur_id:
            records[cur_id].append(line.rstrip())
    return records, order


def _ordered_record_ids(leaf_order, record_order, records, meta):
    g2s = {}; s2g = {}
    for info in meta.values():
        if info.get("gene_id") and info.get("short_id"):
            g2s[info["gene_id"]] = info["short_id"]
        if info.get("short_id") and info.get("gene_id"):
            s2g[info["short_id"]] = info["gene_id"]

    ordered, used = [], set()
    for leaf in leaf_order:
        leaf = _first_token(leaf)
        sp = _split_prefixed_gene(leaf)
        cand = [leaf, sp["gene"]]
        if leaf in meta:
            for f in ("short_id", "gene_id", "raw_id"):
                if meta[leaf].get(f):
                    cand.append(_clean(meta[leaf][f]))
        for c in list(cand):
            if c in g2s:
                cand.append(g2s[c])
        more = [re.sub(r"\.\d+$", "", c) for c in cand if c]
        cand = list({c for c in cand + more if c})
        for c in cand:
            if c in records and c not in used:
                ordered.append(c); used.add(c); break
    for rid in record_order:
        if rid not in used:
            ordered.append(rid)
    return ordered


def _chunk_list(lst, size):
    return [lst[i:i+size] for i in range(0, len(lst), size)]


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@router.get("/species_catalog", summary="List species from cluster file")
def species_catalog() -> dict:
    species = []
    if CLUSTER_FILE.exists():
        for line in CLUSTER_FILE.read_text(encoding="utf-8").splitlines()[1:]:
            cols = line.split("\t")
            if len(cols) >= 8:
                raw = re.sub(r"^\d+:\s*", "", cols[0].strip())
                raw = re.sub(r"_[ABD]\.pep$", "", raw, flags=re.I)
                if raw and raw not in species:
                    species.append(raw)
    return ok({"species": species})


@router.get("/positions", summary="Chromosome positions for orthogroup genes")
def positions(
    og: str = Query(..., description="Orthogroup ID"),
    cluster: int = Query(0, description="Cluster filter (1-7, 0=all)"),
) -> dict:
    if not re.match(r"^OG\d+$", og):
        raise HTTPException(400, "Invalid orthogroup ID")

    with mysql_cursor(ORTHOFINDER_DB) as cur:
        cur.execute("SELECT genes FROM orthogroups WHERE og_id = %s LIMIT 1", (og,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Orthogroup not found")

        genes = [g for g in row["genes"].split() if g]
        gene_hashes = []
        for g in genes:
            g = _clean(g)
            if not g:
                continue
            if cluster > 0 and resolve_cluster(g, cur) != cluster:
                continue
            gene_hashes.append(hashlib.md5(g.encode()).hexdigest())

        if not gene_hashes:
            return ok({"positions": [], "chromosomes": [], "genomes": []})

        result = []
        for chunk in _chunk_list(gene_hashes, 500):
            ph = ",".join(["%s"] * len(chunk))
            try:
                cur.execute(
                    f"SELECT gene_id, chromosome, start_pos, end_pos, genome, subgenome "
                    f"FROM gene_positions WHERE gene_hash IN ({ph})", chunk)
                for r in cur.fetchall():
                    info = _make_info("", r["gene_id"], "", r.get("subgenome", ""))
                    result.append({
                        "gene_id": r["gene_id"],
                        "chromosome": r["chromosome"],
                        "start": int(r["start_pos"]),
                        "end": int(r["end_pos"]),
                        "genome": r["genome"],
                        "subgenome": r.get("subgenome", "Other"),
                        "label": info["full_label"],
                    })
            except Exception:
                pass

        chromosomes = sorted(set(r["chromosome"] for r in result))
        genomes = sorted(set(r["genome"] for r in result))
        return ok({"positions": result, "chromosomes": chromosomes, "genomes": genomes})


@router.get("/search", summary="Search by protein ID or orthogroup ID")
def search(
    q: str = Query(..., description="Protein/gene ID or orthogroup ID"),
) -> dict:
    q = q.strip()
    if not q:
        raise HTTPException(400, "Query is required")

    with mysql_cursor(ORTHOFINDER_DB) as cur:
        # Determine OG
        if re.match(r"^OG\d+$", q):
            og_id = q
        else:
            gene_hash = hashlib.md5(q.encode()).hexdigest()
            cur.execute(
                "SELECT og_id FROM gene_to_og WHERE gene_hash = %s AND gene_id = %s LIMIT 1",
                (gene_hash, q),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, f"Protein ID not found: {q}")
            og_id = row["og_id"]

        cur.execute(
            "SELECT genes, gene_count FROM orthogroups WHERE og_id = %s LIMIT 1", (og_id,),
        )
        og_row = cur.fetchone()
        if not og_row:
            raise HTTPException(404, f"Orthogroup not found: {og_id}")

        genes = [g for g in og_row["genes"].split() if g]
        gene_count = og_row["gene_count"]

        # Read tree & alignment
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
                tree_label_map[rid] = meta[rid]
            else:
                tree_label_map[rid] = _make_info("", rid, "", "")

        sub_counts = {"A": 0, "B": 0, "D": 0, "Other": 0}
        for g in genes:
            info = meta.get(g, _make_info("", g, "", ""))
            sub_counts[_norm_sub(info["subgenome"])] += 1

        # Cluster resolution
        query_cluster = resolve_cluster(q, cur)
        cluster_genes = get_cluster_members(genes, query_cluster, cur) if query_cluster else []
        cluster_sub_counts = {"A": 0, "B": 0, "D": 0, "Other": 0}
        for g in cluster_genes:
            info = meta.get(g, _make_info("", g, "", ""))
            cluster_sub_counts[_norm_sub(info["subgenome"])] += 1

        # Build cluster tree
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

            ok_samples = [lf for lf in tree_leaves[:50] if _clean(lf) in keep][:5]
            nok_samples = [lf for lf in tree_leaves[:50] if _clean(lf) not in keep][:5]
            debug_prune["sample_ok"] = ok_samples
            debug_prune["sample_nok"] = nok_samples

            if keep:
                pruned = _prune_newick(tree, keep)
                if pruned:
                    cluster_tree = pruned
                pl = _parse_newick_leaves(cluster_tree) if cluster_tree else []
                debug_prune["pruned_leaf_count"] = len(pl)
            else:
                debug_prune["pruned_leaf_count"] = 0

        # Order alignment records
        ordered_ids = _ordered_record_ids(leaf_order, record_order, records, meta)
        alignment_preview = [
            {"id": sid, "label": tree_label_map.get(sid, {}).get("full_label", sid),
             "seq": "".join(records[sid])}
            for sid in ordered_ids[:5] if sid in records
        ]

        return ok({
            "query": q,
            "orthogroup": og_id,
            "gene_count": gene_count,
            "genes": genes,
            "sub_counts": sub_counts,
            "tree": tree,
            "cluster_tree": cluster_tree,
            "debug_prune": debug_prune,
            "tree_label_map": {k: {"full_label": v.get("full_label", v.get("label", k)),
                                   "gene_id": v.get("gene_id", k),
                                   "subgenome": v.get("subgenome", "Other"),
                                   "genome_type": v.get("genome_type", "")}
                              for k, v in tree_label_map.items()},
            "leaf_order": leaf_order,
            "alignment_preview": alignment_preview,
            "query_cluster": query_cluster,
            "cluster_gene_count": len(cluster_genes),
            "cluster_genes": cluster_genes,
            "cluster_sub_counts": cluster_sub_counts,
        })


@router.get("/download", summary="Download tree or alignment file")
def download_file(
    og: str = Query(..., description="Orthogroup ID"),
    type: str = Query(..., description="'tree' or 'alignment'"),
    cluster: int = Query(0, description="Cluster filter for tree (1-7)"),
) -> PlainTextResponse:
    if not re.match(r"^OG\d+$", og):
        raise HTTPException(400, "Invalid orthogroup ID")

    if type == "tree":
        tree_file = ORTHOFINDER_BASE_DIR / "WorkingDirectory" / "Resolved_Gene_Trees" / f"{og}.txt"
        if not tree_file.exists():
            raise HTTPException(404, "Tree file not found")
        tree = tree_file.read_text(encoding="utf-8")

        if 1 <= cluster <= 7 and tree:
            with mysql_cursor(ORTHOFINDER_DB) as cur:
                cur.execute("SELECT genes FROM orthogroups WHERE og_id = %s LIMIT 1", (og,))
                row = cur.fetchone()
                if row:
                    genes = [g for g in row["genes"].split() if g]
                    cluster_genes = get_cluster_members(genes, cluster, cur)
                    tree_leaves = _parse_newick_leaves(tree)
                    meta = _fetch_meta(cur, tree_leaves + cluster_genes)
                    keep = _build_prune_keep_set(cluster_genes, meta, tree_leaves)
                    if keep:
                        pruned = _prune_newick(tree, keep)
                        if pruned:
                            tree = pruned

        suffix = f".cluster{cluster}.tree.txt" if cluster else ".tree.txt"
        return PlainTextResponse(tree, media_type="text/plain",
                                 headers={"Content-Disposition": f'attachment; filename="{og}{suffix}"'})

    elif type == "alignment":
        aln_file = _find_alignment_file(og)
        if not aln_file:
            raise HTTPException(404, "Alignment file not found")
        tree_file = ORTHOFINDER_BASE_DIR / "WorkingDirectory" / "Resolved_Gene_Trees" / f"{og}.txt"
        tree = tree_file.read_text(encoding="utf-8") if tree_file.exists() else ""
        alignment = aln_file.read_text(encoding="utf-8")

        with mysql_cursor(ORTHOFINDER_DB) as cur:
            leaf_order = _parse_newick_leaves(tree) if tree else []
            records, record_order = _parse_alignment(alignment)
            meta = _fetch_meta(cur, leaf_order + record_order)
            ordered = _ordered_record_ids(leaf_order, record_order, records, meta)

        lines = []
        for sid in ordered:
            if sid in records:
                label = meta.get(sid, {}).get("full_label", sid)
                lines.append(f">{label}")
                lines.append("\n".join(records[sid]))

        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain",
                                 headers={"Content-Disposition": f'attachment; filename="{og}.alignment.fa"'})

    raise HTTPException(400, "Invalid type; must be 'tree' or 'alignment'")
