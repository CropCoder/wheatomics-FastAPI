"""Mount with: from app.api.routers.regulatory_tf_atlas import router as tf_atlas_router
app.include_router(tf_atlas_router)
"""
import csv, sqlite3
from functools import lru_cache
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query

router=APIRouter(prefix="/api/regulatory/atlas",tags=["Regulatory TF Atlas"])
ROOT=Path("/var/www/html/wheat-regulatory-hub/data/processed")
DB=ROOT/"regulatory.sqlite"
ATLAS=ROOT/"wheat_tf_atlas.tsv"
EXPR=ROOT/"wheat_tf_expression.tsv"
CLASS=ROOT/"wheat_tf_classification.tsv"
CITATION="Ren et al. (2026), Journal of Integrative Agriculture 25(10):4378–4382; DOI:10.1016/j.jia.2026.07.037"

# Upstream hits live in the main database. Downstream hits are sharded one file
# per chromosome under regulatory_shards/, where hits.region_id is the text
# "<gene_id>|downstream" rather than the main database's integer region id.
SHARDS=ROOT/"regulatory_shards"
REGION_KINDS={
    "upstream":("upstream",),
    "downstream":("downstream",),
    "upstream+downstream":("upstream","downstream"),
}

@lru_cache(maxsize=8)
def read_table(path,mtime):
    with open(path,encoding="utf-8",newline="") as f:
        return {row["gene_id"]:row for row in csv.DictReader(f,delimiter="\t")}
def table(path):
    if not path.is_file():
        raise HTTPException(503,f"TF Atlas input not found: {path.name}")
    return read_table(str(path),path.stat().st_mtime_ns)

@lru_cache(maxsize=4)
def read_classification(path,mtime):
    """TF classification table keyed by IWGSC RefSeq v1.1 gene id."""
    with open(path,encoding="utf-8",newline="") as f:
        return {row["gene_id_v11"]:row for row in csv.DictReader(f,delimiter="\t")
                if row.get("gene_id_v11")}
def classification(g):
    """Gene name + TF family calls. Tolerates a missing/partial table."""
    if not CLASS.is_file():
        return {"status":"classification_not_configured"}
    rows=read_classification(str(CLASS),CLASS.stat().st_mtime_ns)
    row=rows.get(g)
    if not row:
        return {"status":"not_in_tf_classification"}
    return {"status":"ok",**{k:v for k,v in row.items() if v not in (None,"","NA")}}
def conn():
    if not DB.is_file():raise HTTPException(503,"Regulatory SQLite unavailable")
    c=sqlite3.connect(DB.resolve().as_uri()+"?mode=ro",uri=True)
    c.row_factory=sqlite3.Row
    return c
def valid_gene(g):
    if len(g)>120 or not all(c.isalnum() or c in "._-" for c in g):
        raise HTTPException(400,"Invalid gene ID")
    return g.split(".")[0]
def gene_lookup(c,g):
    row=c.execute("SELECT * FROM genes WHERE gene_id=? LIMIT 1",(g,)).fetchone()
    return dict(row) if row else None
def tf_info(g):
    item=table(ATLAS).get(g)
    if not item:return {"status":"not_annotated_in_ren2026","is_candidate_tf":False,"source":CITATION}
    return {"status":"annotated_candidate_tf","is_candidate_tf":True,**item}
# The motif metadata layout never changes between releases, so resolve it once
# per database file instead of running two PRAGMA/schema queries per request.
_META_CACHE={}
def motif_metadata_columns(c):
    """Discover motif metadata without changing the production SQLite database."""
    key=(str(DB),DB.stat().st_mtime_ns)
    hit=_META_CACHE.get(key)
    if hit:
        return hit
    tables={r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "motifs" not in tables:
        raise HTTPException(503, "motifs metadata table not found in regulatory.sqlite")
    cols={r[1] for r in c.execute("PRAGMA table_info(motifs)")}
    if "motif_id" not in cols:
        raise HTTPException(503, "motifs.motif_id not found")
    name=next((v for v in ("motif_name","name","model_name","tf_name")
               if v in cols),None)
    source=next((v for v in ("motif_source","source","database")
                 if v in cols),None)
    if name is None:
        raise HTTPException(503, "No motif model name column in motifs metadata")
    _META_CACHE.clear()
    _META_CACHE[key]=(name,source)
    return name,source

# motif_id -> (model name, source), loaded once per database release. The
# downstream shards carry no motifs table, so their hits are annotated here.
_MOTIF_META_CACHE={}
def motif_meta(c):
    key=(str(DB),DB.stat().st_mtime_ns)
    hit=_MOTIF_META_CACHE.get(key)
    if hit is not None:
        return hit
    name,source=motif_metadata_columns(c)
    source_sql=f", {source} AS s" if source else ", NULL AS s"
    rows=c.execute(f"SELECT motif_id, {name} AS n"+source_sql+" FROM motifs").fetchall()
    out={r["motif_id"]:(r["n"],r["s"]) for r in rows}
    _MOTIF_META_CACHE.clear()
    _MOTIF_META_CACHE[key]=out
    return out

def _upstream_rows(c,g,limit):
    name,source=motif_metadata_columns(c)
    source_sql=f"m.{source}" if source else "NULL"
    sql=f"""SELECT h.hit_id,h.region_id,h.motif_id,h.chrom,h.start0,h.end0,
                  h.strand,h.score,h.pvalue,h.qvalue,h.matched_sequence,r.kind,
                  m.{name} AS motif_name,
                  m.{name} AS motif_model,
                  {source_sql} AS motif_source
           FROM regions r JOIN hits h ON h.region_id=r.region_id
           LEFT JOIN motifs m ON m.motif_id=h.motif_id
           WHERE r.gene_id=? AND r.kind='upstream'
           ORDER BY h.start0,h.hit_id LIMIT ?"""
    return [dict(x) for x in c.execute(sql,(g,limit))]

def shard_path(chrom):
    return SHARDS/f"{chrom}.sqlite"

def _downstream_rows(c,gene,limit):
    """Downstream hits live in the per-chromosome shard for this gene."""
    path=shard_path(gene.get("chrom") or "")
    if not path.is_file():
        return []
    con=sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True)
    con.row_factory=sqlite3.Row
    try:
        rows=[dict(x) for x in con.execute(
            "SELECT hit_id,region_id,motif_id,chrom,start0,end0,strand,"
            "score,pvalue,qvalue,matched_sequence FROM hits "
            "WHERE region_id=? ORDER BY start0,hit_id LIMIT ?",
            (f"{gene['gene_id']}|downstream",limit))]
    finally:
        con.close()
    meta=motif_meta(c)
    for r in rows:
        name,source=meta.get(r["motif_id"],(None,None))
        r["motif_name"]=name
        r["motif_model"]=name
        r["motif_source"]=source
        r["kind"]="downstream"
    return rows

def get_motifs(c,gene,region,limit):
    kinds=REGION_KINDS[region]
    rows=[]
    if "upstream" in kinds:
        rows+=_upstream_rows(c,gene["gene_id"],limit+1)
    if "downstream" in kinds:
        rows+=_downstream_rows(c,gene,limit+1)
    rows.sort(key=lambda r:(r["start0"],r["hit_id"]))
    return rows[:limit],len(rows)>limit

@router.get("/search")
def search(q:str=Query(...,min_length=2,max_length=100),limit:int=Query(20,ge=1,le=100)):
    q=q.lower()
    items=[{"gene_id":g,"tf_family":x["tf_family"],"cloned":x["cloned"]}
           for g,x in table(ATLAS).items()
           if q in g.lower() or q in x["tf_family"].lower()]
    return {"items":items[:limit],"total_matches":len(items),"source":CITATION}

@router.get("/gene/{gene_id}")
def profile(gene_id:str,region:str="upstream",motif_limit:int=Query(100,ge=1,le=500)):
    g=valid_gene(gene_id)
    if region not in REGION_KINDS:
        raise HTTPException(400,"Invalid region")
    with conn() as c:
        gene=gene_lookup(c,g)
        if not gene:raise HTTPException(404,"Gene not present in regulatory.sqlite genes")
        motifs,truncated=get_motifs(c,gene,region,motif_limit)
        regions=[dict(r) for r in c.execute(
            "SELECT * FROM regions WHERE gene_id=? ORDER BY start0",(g,))]
    tf=tf_info(g)
    expression=table(EXPR).get(g) if tf["is_candidate_tf"] else None
    return {"gene":gene,"tf":tf,"classification":classification(g),
            "expression":expression,"regions":regions,"region":region,
            "motifs":motifs,"motifs_truncated":truncated,"citation":CITATION}

@router.get("/gene/{gene_id}/motif-variants")
def motif_variants(gene_id:str,dataset_id:str,region:str="upstream",
                   motif_limit:int=Query(20000,ge=1,le=100000),
                   variant_limit:int=Query(10000,ge=1,le=50000),
                   result_limit:int=Query(500,ge=1,le=2000)):
    """Precise motif-variant genomic interval intersection; NO PWM scoring.
    One VCF fetch per regulatory region (upstream in the main database,
    downstream in the per-chromosome shard), then in-memory interval checks.
    """
    import pysam
    from app.api.routers.regulatory_integration import load_catalog
    g=valid_gene(gene_id)
    if region not in REGION_KINDS:
        raise HTTPException(400,"Invalid region")
    kinds=REGION_KINDS[region]
    matches=[x for x in load_catalog() if x["dataset_id"]==dataset_id]
    if not matches:raise HTTPException(404,"Unknown dataset")
    ds=matches[0]
    if ds["status"]!="ready":raise HTTPException(409,f"Dataset not ready: {ds['status']}")
    if ds["assembly"]!="IWGSC RefSeq v1.0":raise HTTPException(409,"Assembly mismatch")
    ph=",".join("?"*len(kinds))
    with conn() as c:
        gene=gene_lookup(c,g)
        if not gene:raise HTTPException(404,"Gene not present")
        regions=[dict(r) for r in c.execute(
            f"SELECT * FROM regions WHERE gene_id=? AND kind IN ({ph}) "
            "ORDER BY start0",(g,*kinds))]
        if not regions:raise HTTPException(404,"Region not found")
        motifs,truncated=get_motifs(c,gene,region,motif_limit)
    if truncated:raise HTTPException(413,"Too many motifs; raise motif_limit or narrow region")
    for r in regions:
        if r["end0"]-r["start0"]>100000:
            raise HTTPException(413,"Region too large for interactive VCF scan")
    items=[];vcf_count=0;variant_truncated=False
    seen=set()
    try:
        with pysam.VariantFile(ds["vcf_path"]) as vcf:
            for r in regions:
                if r["chrom"] not in vcf.header.contigs:
                    raise HTTPException(422,"Chromosome not in VCF header")
                chrom_motifs=[h for h in motifs
                              if h["chrom"]==r["chrom"] and h["kind"]==r["kind"]]
                if not chrom_motifs:continue
                for v in vcf.fetch(r["chrom"],r["start0"],r["end0"]):
                    vcf_count+=1
                    if vcf_count>variant_limit:
                        variant_truncated=True;break
                    for alt in v.alts or ():
                        vs,ve=v.start,v.stop
                        if vs>=r["end0"] or ve<=r["start0"]:continue
                        for h in chrom_motifs:
                            left=max(vs,h["start0"]);right=min(ve,h["end0"])
                            if left>=right:continue
                            key=(r["kind"],h["hit_id"],vs,ve,alt)
                            if key in seen:continue
                            seen.add(key)
                            items.append({"hit_id":h["hit_id"],"motif_id":h["motif_id"],
                              "motif_model":h["motif_model"],"motif_name":h["motif_name"],
                              "motif_start0":h["start0"],"motif_end0":h["end0"],
                              "region_kind":r["kind"],
                              "chrom":r["chrom"],"pos1":v.pos,"variant_start0":vs,
                              "variant_end0":ve,"ref":v.ref,"alt":alt,
                              "overlap_bp":right-left,"dataset_id":dataset_id})
                            if len(items)>=result_limit:
                                return {"gene_id":g,"dataset_id":dataset_id,
                                    "region":region,"regions":regions,"items":items,
                                    "truncated":True,"note":"Genomic overlap only; no REF/ALT PWM effect"}
                if variant_truncated:break
    except (OSError,ValueError) as exc:
        raise HTTPException(422,f"VCF query failed: {str(exc)[:250]}")
    return {"gene_id":g,"dataset_id":dataset_id,"region":region,"regions":regions,
            "items":items,"truncated":variant_truncated,
            "vcf_records_examined":min(vcf_count,variant_limit),
            "note":"Genomic overlap only; no REF/ALT PWM effect"}
