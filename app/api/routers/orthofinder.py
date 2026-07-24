"""OrthoFinder orthogroup browser routes.

Response bodies keep the legacy PHP api.php JSON structure so the front-end
app.js works unchanged. The route path is /api/orthofinder/search (formerly
/api/orthofinder/api.php).

All data is read directly from the OrthoFinder results directory on the
filesystem — no MySQL dependency.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.core.config import settings

ORTHOFINDER_BASE_DIR = settings.ORTHOFINDER_BASE_DIR
CLUSTER_FILE = settings.ORTHOFINDER_CLUSTER_FILE
BED_DIR = Path("/var/www/html/jcvi_col/db")  # where *.filter.bed files live

router = APIRouter(prefix="/orthofinder", tags=["OrthoFinder"])

# Escape sequences for whitespace — prevents raw NL/TAB in source from
# breaking the parser.
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

def _load_cluster_map() -> tuple[dict, dict]:
    global _cluster_cache
    if _cluster_cache is not None:
        return _cluster_cache
    prefix_map: dict[str, int] = {}
    chrom_map: dict[str, int] = {}
    _type_map: dict = {}
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
                    # collect type1/type2 classification for this prefix row
                    t1 = (cols[8].strip().lower() if len(cols) > 8 else "no")
                    t2 = (cols[9].strip().lower() if len(cols) > 9 else "no")
                    _type_map[val] = (t1, t2)
    _cluster_cache = (prefix_map, chrom_map)
    global _type_map_cache
    if _type_map_cache is None:
        _type_map_cache = _type_map
    return _cluster_cache

def _load_type_map() -> dict:
    """Return type classification cache: {gene_prefix: [type1_yesno, type2_yesno]}.
    Lazy-loaded on first _load_cluster_map call."""
    _load_cluster_map()
    return _type_map_cache if _type_map_cache is not None else {}

def _get_type_for_gene(gene_id: str) -> tuple[str, str]:
    """Return (type1, type2) for a gene_id — 'yes' or 'no' per column."""
    gene_id = _clean(gene_id)
    type_map = _load_type_map()
    for pfx in _get_sorted_prefixes():
        if pfx in type_map and gene_id.lower().startswith(pfx.lower()):
            return type_map[pfx][0], type_map[pfx][1]
    return "no", "no"

def _get_sorted_prefixes() -> list:
    global _sorted_prefixes
    if _sorted_prefixes is not None:
        return _sorted_prefixes
    prefix_map, _ = _load_cluster_map()
    _sorted_prefixes = sorted(prefix_map.keys(), key=lambda x: -len(x))
    return _sorted_prefixes

#: gene_id → chromosome, lazily populated from BED files
_bed_chromosome_cache: dict | None = None

#: type classification cache — per row(gene_prefix → type1/type2)
_type_map_cache: dict | None = None

def _load_bed_chromosome_map() -> dict:
    """Build gene_id → chromosome dict from *.filter.bed files (lazy + cached).

    Only scans BED files that correspond to genomes listed in
    SpeciesIDs_cluster.txt.  Each BED line is tab-separated:
        chromosome  start  end  gene_id
    """
    global _bed_chromosome_cache
    if _bed_chromosome_cache is not None:
        return _bed_chromosome_cache

    mp: dict = {}
    if not BED_DIR.exists():
        _bed_chromosome_cache = mp
        return mp

    # --- determine which genomes are in the analysis ---
    genomes: set[str] = set()
    if CLUSTER_FILE.exists():
        for line in CLUSTER_FILE.read_text(encoding="utf-8").splitlines()[1:]:
            cols = line.split(_TAB)
            if len(cols) < 8:
                continue
            raw = re.sub(r"^\d+:\s*", "", cols[0].strip())
            raw = re.sub(r"_[ABD]\.pep$", "", raw, flags=re.I)
            if raw:
                genomes.add(raw)

    # --- helper: fuzzy-match BED file name to genome ---
    def _bed_matches(fname: str) -> str | None:
        """Return genome name if *fname* matches a known genome."""
        for g in genomes:
            if fname == g:
                return g
            if fname.lower() == g.lower():
                return g
            # prefix match (e.g. Chinese_Spring2.1_A.filter.bed  vs  Chinese_Spring2.1)
            if fname.startswith(g + "_") or fname.startswith(g + "."):
                return g
        return None

    # --- scan BED files ---
    for entry in sorted(BED_DIR.iterdir()):
        fname = entry.name
        if not fname.endswith(".filter.bed"):
            continue
        # strip subgenome suffix and .filter.bed
        base = os.path.splitext(fname)[0]           # Chinese_Spring2.1_A.filter
        base = re.sub(r"\.filter$", "", base)        # Chinese_Spring2.1_A
        parts = base.rsplit("_", 1)
        genome_name = parts[0] if len(parts) == 2 else base
        sub = parts[1] if len(parts) == 2 and parts[1] in ("A", "B", "D") else ""
        if not sub:
            continue
        if not _bed_matches(genome_name):
            continue
        try:
            for line in entry.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("track"):
                    continue
                cols = line.split("\t")
                if len(cols) < 4:
                    continue
                gid = _clean(cols[3])
                chrom = _clean(cols[0])
                if gid and chrom:
                    mp[gid] = chrom
        except Exception:
            continue

    _bed_chromosome_cache = mp
    return mp

def _resolve_cluster(gene_id: str) -> int | None:
    """Map a gene_id to its homoeologous cluster (1-7)."""
    gene_id = _clean(gene_id)
    prefix_map, chrom_map = _load_cluster_map()
    if not prefix_map and not chrom_map:
        return None

    # 1) prefix match
    for pfx in _get_sorted_prefixes():
        if gene_id.lower().startswith(pfx.lower()):
            return prefix_map[pfx]

    # 2) chromosome fallback via BED files
    if chrom_map:
        chrom = _load_bed_chromosome_map().get(gene_id)
        if chrom and chrom.lower() in chrom_map:
            return chrom_map[chrom.lower()]

    return None

def _get_cluster_members(genes: list, target: int) -> list:
    members = []
    for g in genes:
        g = _clean(g)
        if not g:
            continue
        if _resolve_cluster(g) == target:
            members.append(g)
    return members


# ---------------------------------------------------------------------------
# Orthogroups.txt cache  (replaces orthogroups + gene_to_og MySQL tables)
# ---------------------------------------------------------------------------

_orthogroups_cache: dict | None = None
_gene_to_og_cache: dict | None = None

def _orthogroups_file() -> Path:
    base = ORTHOFINDER_BASE_DIR
    for p in [base / "Orthogroups" / "Orthogroups.txt",
              base / "WorkingDirectory" / "Orthogroups.txt",
              base.parent / "Orthogroups" / "Orthogroups.txt"]:
        if p.exists():
            return p
    return base / "Orthogroups" / "Orthogroups.txt"

def _load_orthogroups() -> dict:
    """Parse Orthogroups.txt ONCE.

    Returns: {og_id: {"genes": [gene_id, ...], "gene_count": int}}
    Also populates _gene_to_og_cache: {gene_id: og_id}.
    """
    global _orthogroups_cache, _gene_to_og_cache
    if _orthogroups_cache is not None:
        return _orthogroups_cache

    mp: dict = {}
    g2og: dict = {}
    f = _orthogroups_file()
    if f.exists():
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            og_id, genes_str = line.split(":", 1)
            og_id = _clean(og_id)
            genes = [_clean(g) for g in genes_str.strip().split() if _clean(g)]
            mp[og_id] = {"genes": genes, "gene_count": len(genes)}
            for g in genes:
                if g not in g2og:            # first OG wins (same as INSERT IGNORE)
                    g2og[g] = og_id
    _orthogroups_cache = mp
    _gene_to_og_cache = g2og
    return mp

def _find_og_for_gene(gene_id: str) -> str | None:
    _load_orthogroups()
    return _gene_to_og_cache.get(gene_id)


# ---------------------------------------------------------------------------
# sequence-id helpers
# ---------------------------------------------------------------------------

def _sequence_id_files() -> list:
    base = ORTHOFINDER_BASE_DIR
    return [
        base / "WorkingDirectory" / "SequenceIDs.txt",
        base / "SequenceIDs.txt",
        base.parent / "WorkingDirectory" / "SequenceIDs.txt",
    ]

def _species_id_files() -> list:
    """Paths to SpeciesIDs.txt — maps genome_number → species_subgenome."""
    base = ORTHOFINDER_BASE_DIR
    return [
        base / "WorkingDirectory" / "SpeciesIDs.txt",
        base / "SpeciesIDs.txt",
        base.parent / "WorkingDirectory" / "SpeciesIDs.txt",
    ]

_species_id_cache: dict | None = None

def _load_species_id_map() -> dict:
    """Parse SpeciesIDs.txt ONCE and cache.

    Format: "0: AK58_A.pep"
    Returns: {"0": {"species": "AK58", "subgenome": "A"}}
    """
    global _species_id_cache
    if _species_id_cache is not None:
        return _species_id_cache
    mp: dict = {}
    for f in _species_id_files():
        if not f.exists():
            continue
        try:
            for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                m = re.match(r"^(\d+)\s*:\s*(\S+)", line)
                if not m:
                    continue
                genome_number = m.group(1)
                species_raw = _clean(m.group(2))
                species_raw = re.sub(r"\.pep$", "", species_raw, flags=re.I)
                parts = species_raw.rsplit("_", 1)
                species_name = parts[0] if len(parts) == 2 else species_raw
                sub = _norm_sub(parts[1]) if len(parts) == 2 else "Other"
                mp[genome_number] = {"species": species_name, "subgenome": sub}
        except Exception:
            continue
        if mp:
            break
    _species_id_cache = mp
    return mp

# ---------------------------------------------------------------------------
# genome_type.txt cache — authoritative mapping: genome_number → genome_type
# Format: Number  species  type
#         0       AK58_A   AK58_A_subgenome
#         ...
#         114     RM271_N  RM271_N_subgenome   → subgenome "Other" (N not in A/B/D)
# ---------------------------------------------------------------------------

_genome_type_cache: dict | None = None

def _genome_type_file() -> Path:
    """Locate genome_type.txt."""
    base = ORTHOFINDER_BASE_DIR.parent  # /var/www/html/orthefind/
    for p in [base / "genome_type.txt",
              Path("/var/www/html/orthefind/genome_type.txt")]:
        if p.exists():
            return p
    return Path("/var/www/html/orthefind/genome_type.txt")

def _load_genome_type_map() -> dict:
    """Parse genome_type.txt ONCE.

    Returns: {genome_number_str: {"species": "...", "genome_type": "...", "subgenome": "A/B/D/Other"}}
    """
    global _genome_type_cache
    if _genome_type_cache is not None:
        return _genome_type_cache
    mp: dict = {}
    f = _genome_type_file()
    if f.exists():
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.lower().startswith("number"):
                continue
            cols = re.split(r"\s+", line)
            if len(cols) < 3:
                continue
            gn = cols[0].strip()
            species = cols[1].strip()
            gtype = cols[2].strip()
            # Determine subgenome from the final character of the type
            sub = _norm_sub(gtype[0] if gtype else "")
            if gtype:
                m_sub = re.search(r"_([ABD])_subgenome$", gtype, re.I)
                if m_sub:
                    sub = m_sub.group(1).upper()
                else:
                    # Try to extract from species name (e.g. RM271_N → N)
                    m_sub2 = re.search(r"_([ABD])$", species, re.I)
                    if m_sub2:
                        sub = m_sub2.group(1).upper()
            mp[gn] = {"species": species, "genome_type": gtype, "subgenome": sub}
    _genome_type_cache = mp
    return mp

_seq_id_full_cache: dict | None = None

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
    """Return only the wanted subset from the cached full map."""
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

def _fetch_meta(names) -> dict:
    """Build metadata dictionary from SequenceIDs.txt (file-only, no DB)."""
    return _load_sequence_id_map(names)

def _make_info(short: str, gene: str, genome_type: str, sub: str) -> dict:
    short = _clean(short); gene = _clean(gene); genome_type = _clean(genome_type)
    sub = _norm_sub(sub)
    src = gene if gene else short
    sp = _split_prefixed_gene(src)

    # ---- Resolve genome_type + subgenome from genome_type.txt ----
    # This is the authoritative source that maps every genome_number to its
    # exact species+subgenome label (e.g. 114→RM271_N_subgenome, which becomes
    # subgenome Other because N is not A/B/D).
    gn = short.split("_", 1)[0] if short else ""
    gt_info = _load_genome_type_map().get(gn)
    if gt_info:
        if not genome_type or genome_type == "Unknown":
            genome_type = gt_info["genome_type"]
        sub = gt_info["subgenome"]
        # Keep the exact species name from genome_type.txt (not the
        # assembled x_A_subgenome form) so labels read correctly:
        #   RM271_N_subgenome  not  RM271_N_N_subgenome
        sp["genome_type"] = genome_type

    # Fallback: SpeciesIDs.txt if genome_type.txt didn't have an entry
    if not genome_type or genome_type == "Unknown":
        sm = _load_species_id_map().get(gn, {})
        sp_name = sm.get("species", "")
        sp_sub  = sm.get("subgenome", "Other")
        if sp_name:
            sp["genome_type"] = f"{sp_name}_{sp_sub}_subgenome"
            sp["sub"] = sp_sub
        if not genome_type:
            genome_type = sp["genome_type"]

    if sp["gene"] != src and gene:
        gene = sp["gene"]
    if not genome_type:
        genome_type = sp.get("genome_type") or ("Unknown" if sub == "Other" else f"{sub}_subgenome")
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
    """Map tree leaves → meta → gene_id → check against cluster_genes."""
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

        # 5) unique suffix guard
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
    """Fast existence check; cache per OG."""
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


def _ordered_record_ids(leaf_order, record_order, records, meta, include_unmatched=True):
    """Order alignment records by tree-leaf order.

    Graded matching per leaf (stop at first hit):
      1) exact crosswalk candidates (gene_id/short_id/raw_id + version-stripped);
      2) unique suffix match (leaf endswith record_id) for prefixed leaf names.
    """
    g2s, s2g, raw2s = {}, {}, {}
    for info in meta.values():
        gid = info.get("gene_id"); sid = info.get("short_id"); rid = info.get("raw_id")
        if gid and sid: g2s[gid] = sid
        if sid and gid: s2g[sid] = gid
        if rid and sid: raw2s[rid] = sid

    rec_ids_by_len = sorted(records.keys(), key=lambda x: -len(x))

    def _exact_match(leaf):
        leaf_tok = _first_token(leaf)
        sp = _split_prefixed_gene(leaf_tok)
        cand = [leaf_tok, sp["gene"]]
        if leaf_tok in meta:
            for f in ("short_id", "gene_id", "raw_id"):
                v = meta[leaf_tok].get(f)
                if v: cand.append(v)
        if leaf_tok in g2s: cand.append(g2s[leaf_tok])
        if leaf_tok in raw2s: cand.append(raw2s[leaf_tok])
        if sp["gene"] in g2s: cand.append(g2s[sp["gene"]])
        more = [re.sub(r"\.\d+$", "", c) for c in cand if c]
        seen, all_cand = set(), []
        for c in cand + more:
            if c and c not in seen:
                seen.add(c); all_cand.append(c)
        for c in all_cand:
            if c in records:
                return c
        return None

    def _suffix_match(leaf, used):
        leaf_tok = _first_token(leaf)
        cands = []
        for fid in rec_ids_by_len:
            if fid in used:
                continue
            if leaf_tok == fid or leaf_tok.endswith("_" + fid) or leaf_tok.endswith(fid):
                cands.append(fid)
        if not cands:
            return None
        if len(cands) == 1:
            return cands[0]
        if len(cands[0]) > len(cands[1]):
            return cands[0]
        return None

    ordered, used = [], set()
    for leaf in leaf_order:
        rid = _exact_match(leaf)
        if not rid or rid in used:
            rid2 = _suffix_match(leaf, used)
            rid = rid2 if rid2 else (rid if (rid and rid not in used) else None)
        if rid and rid in records and rid not in used:
            ordered.append(rid); used.add(rid)

    if include_unmatched:
        for rid in record_order:
            if rid not in used:
                ordered.append(rid)
    return ordered

def _label_for(id, meta):
    """Build display label — mirrors PHP d_label()."""
    return meta.get(id, {}).get("full_label", id)


# ===================================================================
# API endpoints  (raw JSON matching the legacy PHP api.php response format)
# ===================================================================

@router.get(
    "/search",
    summary="Search by protein ID / orthogroup ID / species catalog / members / positions",
)
def search_orthogroup(
    q: str = Query("", description="Protein/gene ID or orthogroup ID. Used when action=search."),
    action: str = Query("search", description="Action: 'search' (default) | 'species_catalog' | 'members' | 'positions'"),
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
        og_data = _load_orthogroups().get(og)
        if not og_data:
            return {"error": "Orthogroup not found"}
        genes = og_data["genes"]
        meta = _fetch_meta(genes)
        items = {}
        for g in genes:
            info = meta.get(g, _make_info("", g, "", ""))
            if _norm_sub(info["subgenome"]) != sub:
                continue
            gt = info["genome_type"] or "Unknown"
            items.setdefault(gt, []).append(info.get("gene_id") or g)
        for arr in items.values():
            arr.sort()
        return {"items": dict(sorted(items.items()))}

    if action == "positions":
        if not re.match(r"^OG\d+$", og):
            return {"error": "Invalid orthogroup"}
        og_data = _load_orthogroups().get(og)
        if not og_data:
            return {"error": "Orthogroup not found"}
        genes = og_data["genes"]
        bc_map = _load_bed_chromosome_map()
        result = []
        for g in genes:
            g = _clean(g)
            if not g:
                continue
            if cluster > 0 and _resolve_cluster(g) != cluster:
                continue
            chrom = bc_map.get(g, "")
            info = _make_info("", g, "", "")
            result.append({
                "gene_id": g, "chromosome": chrom,
                "start": 0, "end": 0,
                "genome": "", "subgenome": info.get("subgenome", "Other"),
                "label": info["full_label"],
            })
        chromosomes = sorted(set(r["chromosome"] for r in result if r["chromosome"]))
        genomes = sorted(set(r["genome"] for r in result if r["genome"]))
        return {"positions": result, "chromosomes": chromosomes, "genomes": genomes}

    # -- main search --
    q = q.strip()
    if not q:
        return {"error": "Please input a protein ID or orthogroup ID."}

    # Resolve og_id from query
    if re.match(r"^OG\d+$", q):
        og_id = q
    else:
        # Try direct gene → OG lookup. Orthogroups.txt stores protein IDs
        # with a version suffix (.1), so a bare gene ID also tries the .1 form.
        cand_ids = [q]
        if not re.search(r"\.\d+$", q):
            cand_ids.append(q + ".1")
        og_id = None
        for cid in cand_ids:
            og_id = _find_og_for_gene(cid)
            if og_id:
                q = cid  # report the ID that actually matched
                break
        if not og_id and species:
            og_id = _find_og_for_gene(f"{species}_{q}")
        if not og_id:
            # Try hash-based fallback via Orthogroups.txt
            for cid in cand_ids:
                qh = hashlib.md5(cid.encode()).hexdigest()
                for oid, odata in _load_orthogroups().items():
                    for g in odata["genes"]:
                        if g == cid or hashlib.md5(g.encode()).hexdigest() == qh:
                            og_id = oid
                            break
                    if og_id:
                        break
                if og_id:
                    q = cid
                    break

    og_data = _load_orthogroups().get(og_id)
    if not og_data:
        return {"error": "Orthogroup was not found."}

    genes = og_data["genes"]
    gene_count = og_data["gene_count"]

    tree_file = ORTHOFINDER_BASE_DIR / "WorkingDirectory" / "Trees_ids" / f"{og_id}.txt"
    aln_file = _find_alignment_file(og_id)
    tree = tree_file.read_text(encoding="utf-8") if tree_file.exists() else ""
    alignment = aln_file.read_text(encoding="utf-8") if aln_file else ""

    leaf_order = _parse_newick_leaves(tree) if tree else []
    records, record_order = _parse_alignment(alignment) if alignment else ({}, [])

    meta = _fetch_meta(leaf_order + record_order + genes)

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

    # Cluster resolution
    query_cluster = _resolve_cluster(q)
    cluster_genes = _get_cluster_members(genes, query_cluster) if query_cluster is not None else []
    cluster_sub_counts = {"A": 0, "B": 0, "D": 0, "Other": 0}
    for g in cluster_genes:
        info = meta.get(g, _make_info("", g, "", ""))
        cluster_sub_counts[_norm_sub(info["subgenome"])] += 1

    # ---- type1 / type2 split ----
    cluster_genes_type1 = [g for g in cluster_genes if _get_type_for_gene(g)[0] == "yes"]
    cluster_genes_type2 = [g for g in cluster_genes if _get_type_for_gene(g)[1] == "yes"]

    def _prune_typed_tree(type_genes):
        """Prune the full OG tree to a subset of cluster genes (type1 or type2)."""
        if not type_genes or not tree:
            return ""
        keep = _build_prune_keep_set(type_genes, meta, _parse_newick_leaves(tree))
        if keep:
            pruned = _prune_newick(tree, keep)
            return pruned if pruned else ""
        return ""

    cluster_tree_type1 = _prune_typed_tree(cluster_genes_type1)
    cluster_tree_type2 = _prune_typed_tree(cluster_genes_type2)

    # Build cluster tree (original — all cluster genes)
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
        "cluster_tree_type1": cluster_tree_type1,
        "cluster_tree_type2": cluster_tree_type2,
        "cluster_genes_type1": cluster_genes_type1,
        "cluster_genes_type2": cluster_genes_type2,
        "cluster_gene_count_type1": len(cluster_genes_type1),
        "cluster_gene_count_type2": len(cluster_genes_type2),
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
    tree_file = ORTHOFINDER_BASE_DIR / "WorkingDirectory" / "Trees_ids" / f"{og}.txt"
    return tree_file.read_text(encoding="utf-8") if tree_file.exists() else ""


def _prune_tree_to_cluster(og: str, tree: str, cluster: int) -> str:
    """Prune a tree to one homoeologous cluster."""
    if not (1 <= cluster <= 7) or not tree:
        return tree
    og_data = _load_orthogroups().get(og)
    if not og_data:
        return tree
    genes = og_data["genes"]
    c_genes = _get_cluster_members(genes, cluster)
    leaves = _parse_newick_leaves(tree)
    meta = _fetch_meta(leaves + c_genes)
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
)
def download_file(
    og: str = Query(..., description="Orthogroup ID, e.g. OG0001897"),
    type: str = Query("tree", description="File type: 'tree' or 'alignment'"),
    cluster: int = Query(0, description="Cluster number (1-7). 0 = full OG."),
    type_tree: str = Query("", description="Type tree filter: 'type1' or 'type2'. Only for cluster downloads."),
):
    if not re.match(r"^OG\d+$", og):
        raise HTTPException(400, "Invalid OG ID")

    # ---- Download OG tree / Download some homoeologous tree ----
    if type == "tree":
        tree = _load_tree_text(og)
        if not tree:
            raise HTTPException(404, "Tree file not found")
        if 1 <= cluster <= 7 and tree:
            if type_tree in ("type1", "type2"):
                # Prune to cluster + type subset
                og_data = _load_orthogroups().get(og)
                if og_data:
                    c_genes = _get_cluster_members(og_data["genes"], cluster)
                    if type_tree == "type1":
                        c_genes = [g for g in c_genes if _get_type_for_gene(g)[0] == "yes"]
                    else:
                        c_genes = [g for g in c_genes if _get_type_for_gene(g)[1] == "yes"]
                    leaves = _parse_newick_leaves(tree)
                    meta = _fetch_meta(leaves + c_genes)
                    keep = _build_prune_keep_set(c_genes, meta, leaves)
                    if keep:
                        pruned = _prune_newick(tree, keep)
                        if pruned:
                            tree = pruned
            else:
                tree = _prune_tree_to_cluster(og, tree, cluster)
        type_label = {"type1": "Triticum_aestivum", "type2": "Triticeae"}.get(type_tree, type_tree.upper() if type_tree else "")
        label = type_label or ("cluster" + str(cluster) if cluster else "")
        suffix = f".HomoeologousGroup{label}.tree.txt" if label else ".tree.txt"
        return PlainTextResponse(
            tree, media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{og}{suffix}"'})

    # ---- Download OG alignment / Download some homoeologous alignment ----
    if type == "alignment":
        aln_file = _find_alignment_file(og)
        if not aln_file:
            raise HTTPException(404, "Alignment file not found")
        alignment = aln_file.read_text(encoding="utf-8")
        records, record_order = _parse_alignment(alignment)
        tree = _load_tree_text(og)

        tree_leaves_full = _parse_newick_leaves(tree) if tree else []

        if 1 <= cluster <= 7 and tree:
            og_data = _load_orthogroups().get(og)
            c_genes_for_meta = []
            if og_data:
                c_genes_all = _get_cluster_members(og_data["genes"], cluster)
                if type_tree in ("type1", "type2"):
                    c_genes_for_meta = [g for g in c_genes_all if (type_tree == "type1" and _get_type_for_gene(g)[0] == "yes") or (type_tree == "type2" and _get_type_for_gene(g)[1] == "yes")]
                else:
                    c_genes_for_meta = c_genes_all

            if c_genes_for_meta:
                keep = _build_prune_keep_set(c_genes_for_meta, _fetch_meta(tree_leaves_full + list(records.keys()) + c_genes_for_meta), tree_leaves_full)
                pruned = _prune_newick(tree, keep) if keep else ""
            else:
                pruned = _prune_tree_to_cluster(og, tree, cluster)
            leaf_order = _parse_newick_leaves(pruned) if pruned else []
            include_unmatched = False
            meta = _fetch_meta(tree_leaves_full + list(records.keys()) + c_genes_for_meta)
        else:
            leaf_order = tree_leaves_full
            include_unmatched = True
            meta = _fetch_meta(tree_leaves_full + list(records.keys()))

        ordered = _ordered_record_ids(
            leaf_order, record_order, records, meta,
            include_unmatched=include_unmatched,
        )

        out_lines = []
        for sid in ordered:
            if sid in records:
                out_lines.append(">" + _label_for(sid, meta))
                out_lines.append(_NL.join(records[sid]))

        type_label = {"type1": "Triticum_aestivum", "type2": "Triticeae"}.get(type_tree, type_tree.upper() if type_tree else "")
        label = type_label or ("cluster" + str(cluster) if cluster else "")
        suffix = f".HomoeologousGroup{label}" if label else ""
        body = _NL.join(out_lines) + _NL
        return PlainTextResponse(
            body, media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{og}{suffix}.alignment.fa"'})

    raise HTTPException(400, "Invalid type")
