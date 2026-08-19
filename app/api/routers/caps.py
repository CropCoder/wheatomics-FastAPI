"""CAPS/dCAPS primer design routes.

Design primers that discriminate two alleles of a SNP via restriction
digestion:

  * CAPS  — the SNP creates/destroys a natural restriction site;
  * dCAPS — the primer introduces 1-3 mismatches to create the site.

Three input modes are supported (see ``CapsDesignRequest``):

  1. pasted sequences        — ``seq1`` + ``seq2`` (equal length, one SNP)
  2. genomic coordinates     — ``db`` + ``region`` + ``pos`` + ``allele1/allele2``
  3. VCF variant             — ``vcf_dataset`` + ``chrom`` + ``pos``

Modes 2/3 fetch the flanking sequence from the BLAST databases
(blastdbcmd, same mechanism as /api/sequence/by-interval) and splice the
alleles in. The core algorithm is app/services/caps_designer.py.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.exceptions import ResourceNotFound, ValidationFailure
from app.core.response import ok
from app.services import caps_designer
from app.services.caps_designer import design_caps_dcaps
from app.services.command_runner import run_command
from app.services.restriction_enzymes import ENZYME_BY_NAME, RESTRICTION_ENZYMES

router = APIRouter(prefix="/caps", tags=["CAPS/dCAPS"])

_SEQ_RE = re.compile(r"^[ACGT]+$")
_ENZYME_NAME_RE = re.compile(r"^[A-Za-z0-9.\-]{1,32}$")
_RECOG_RE = re.compile(r"^[ACGTRYSWKMBDHVN]{3,16}$")
_REGION_RE = re.compile(r"^(.+?):(\d+)-(\d+)$")


# ---------------------------------------------------------------------------
# Enzyme library
# ---------------------------------------------------------------------------
@router.get("/enzymes")
def list_enzymes(q: str | None = Query(None, description="按酶名过滤")) -> dict:
    """列出内置限制酶库（名称、识别序列、切点、是否常用）。"""
    enzymes = RESTRICTION_ENZYMES
    if q:
        ql = q.lower()
        enzymes = [e for e in enzymes if ql in e["name"].lower()]
    return ok({"total": len(enzymes), "enzymes": enzymes})


# ---------------------------------------------------------------------------
# Design
# ---------------------------------------------------------------------------
class CapsDesignRequest(BaseModel):
    # Mode 1 — pasted sequences
    seq1: str | None = None
    seq2: str | None = None
    # Mode 2 — genomic coordinates (BLAST DB name, e.g. Chinese_Spring2.1)
    db: str | None = None
    region: str | None = None
    pos: int | None = None
    allele1: str | None = None
    allele2: str | None = None
    # Mode 3 — VCF variant (VariantHub dataset key)
    vcf_dataset: str | None = None
    chrom: str | None = None
    # Shared
    enzymes: list[str] | None = Field(
        None, description="酶名子集；null = 全部内置酶")
    custom_enzymes: list[dict] | None = Field(
        None, description="自定义酶 [{'name','recognition','cut':[l,r]}]")
    mismatch_max: int = Field(1, ge=0, le=3)
    primer_len: tuple[int, int] = (20, 27)
    tm_range: tuple[float, float] = (55.0, 65.0)
    product_size: tuple[int, int] = (100, 1000)
    flank: int = Field(250, ge=60, le=2000, description="坐标/VCF 模式下 SNP 两侧各取多少 bp")
    top_n: int = Field(20, ge=1, le=100)


def _resolve_enzymes(req: CapsDesignRequest) -> list[dict]:
    """Built-in subset + custom enzymes, validated."""
    if req.enzymes:
        subset = []
        for name in req.enzymes:
            if not _ENZYME_NAME_RE.fullmatch(name):
                raise ValidationFailure(f"Invalid enzyme name: {name!r}")
            enz = ENZYME_BY_NAME.get(name)
            if enz is None:
                raise ValidationFailure(
                    f"Unknown enzyme: {name} (see GET /api/caps/enzymes)")
            subset.append(enz)
    else:
        subset = list(RESTRICTION_ENZYMES)

    for ce in req.custom_enzymes or []:
        name = ce.get("name", "")
        rec = str(ce.get("recognition", "")).upper()
        cut = ce.get("cut")
        if not _ENZYME_NAME_RE.fullmatch(name) or not _RECOG_RE.fullmatch(rec):
            raise ValidationFailure(
                f"Invalid custom enzyme: {ce!r} (name 1-32 chars, "
                "recognition 3-16 IUPAC letters)")
        if (not isinstance(cut, (list, tuple)) or len(cut) != 2
                or not all(isinstance(c, int) and 0 <= c <= 16 for c in cut)):
            raise ValidationFailure(
                f"Invalid cut offsets for custom enzyme {name}: {cut!r}")
        subset.append({"name": name, "recognition": rec,
                       "cut": (cut[0], cut[1]), "common": False})
    return subset


def _fetch_flank(db: str, chrom: str, start: int, end: int) -> str:
    """Fetch genomic sequence via blastdbcmd (same as /sequence/by-interval)."""
    from app.api.routers.sequence import _check_db_exists, _try_interval

    db_path = settings.BLAST_DB_PATH / db
    if not _check_db_exists(db_path):
        raise ValidationFailure(
            f"BLAST database '{db}' not found under {settings.BLAST_DB_PATH}. "
            "List available DBs via /api/blast/databases.")
    seq = _try_interval(db_path, chrom, start, end)
    return "".join(line.strip() for line in seq.splitlines()
                   if not line.startswith(">"))


def _resolve_vcf_variant(req: CapsDesignRequest) -> tuple[str, str, str, str]:
    """Return (db, chrom, ref, alt) for the VCF mode variant."""
    from app.api.routers.varianthub import (
        VARIANTHUB_DATASETS, _bcftools_path, _vcf_path)

    vcf = _vcf_path(req.vcf_dataset)
    meta = VARIANTHUB_DATASETS[req.vcf_dataset]
    db = meta["reference"]
    chrom = req.chrom
    out = run_command(
        [_bcftools_path(), "view", "-H", "--no-version", str(vcf),
         "-r", f"{chrom}:{req.pos}-{req.pos}"])
    lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
    if not lines:
        raise ResourceNotFound(
            f"No variant at {chrom}:{req.pos} in {req.vcf_dataset}")
    fields = lines[0].split("\t")
    if len(fields) < 5:
        raise ValidationFailure(
            f"Unexpected VCF row: {lines[0][:80]!r}")
    return db, chrom, fields[3].upper(), fields[4].split(",")[0].upper()


def _resolve_sequences(req: CapsDesignRequest) -> tuple[str, str, dict]:
    """Resolve (seq1, seq2, snp_meta) from whichever input mode is used."""
    # Mode 1: pasted sequences
    if req.seq1 is not None or req.seq2 is not None:
        if req.seq1 is None or req.seq2 is None:
            raise ValidationFailure("Provide both seq1 and seq2")
        if not _SEQ_RE.fullmatch(req.seq1.upper()) or not _SEQ_RE.fullmatch(req.seq2.upper()):
            raise ValidationFailure("seq1/seq2 may only contain A/C/G/T")
        return req.seq1.upper(), req.seq2.upper(), {}

    # Mode 3: VCF variant
    if req.vcf_dataset is not None:
        if req.chrom is None or req.pos is None:
            raise ValidationFailure(
                "VCF mode requires vcf_dataset + chrom + pos")
        db, chrom, ref, alt = _resolve_vcf_variant(req)
        start, end = req.pos - req.flank, req.pos + req.flank
        seq = _fetch_flank(db, chrom, start, end)
        offset = req.pos - start
        if seq[offset:offset + len(ref)].upper() != ref:
            raise ValidationFailure(
                f"Reference mismatch at {chrom}:{req.pos}: genome has "
                f"{seq[offset:offset + len(ref)]!r}, VCF REF={ref!r} "
                "(chrom naming or reference build mismatch?)")
        seq1 = seq[:offset] + ref + seq[offset + len(ref):]
        seq2 = seq[:offset] + alt + seq[offset + len(alt):]
        return seq1, seq2, {"db": db, "chrom": chrom, "pos": req.pos,
                            "allele1": ref, "allele2": alt,
                            "vcf_dataset": req.vcf_dataset}

    # Mode 2: genomic coordinates
    if req.db is not None and req.region is not None:
        if req.pos is None or req.allele1 is None or req.allele2 is None:
            raise ValidationFailure(
                "Coordinate mode requires db + region + pos + allele1 + allele2")
        m = _REGION_RE.fullmatch(req.region.strip())
        if not m:
            raise ValidationFailure(
                "region must look like 'chr1A:100-500'")
        chrom, start, end = m.group(1), int(m.group(2)), int(m.group(3))
        a1, a2 = req.allele1.upper(), req.allele2.upper()
        if not _SEQ_RE.fullmatch(a1) or not _SEQ_RE.fullmatch(a2):
            raise ValidationFailure("allele1/allele2 must be A/C/G/T")
        if not (start <= req.pos <= end):
            raise ValidationFailure(
                f"pos={req.pos} must lie inside region {start}-{end}")
        seq = _fetch_flank(req.db, chrom, start, end)
        offset = req.pos - start
        ref_base = seq[offset]
        if ref_base not in (a1, a2):
            raise ValidationFailure(
                f"Genome has {ref_base!r} at {chrom}:{req.pos}, which matches "
                "neither allele1 nor allele2 (chrom naming mismatch?)")
        seq1 = seq[:offset] + a1 + seq[offset + 1:]
        seq2 = seq[:offset] + a2 + seq[offset + 1:]
        return seq1, seq2, {"db": req.db, "chrom": chrom, "pos": req.pos,
                            "allele1": a1, "allele2": a2}

    raise ValidationFailure(
        "No input mode detected. Provide either (seq1+seq2), "
        "(db+region+pos+allele1+allele2), or (vcf_dataset+chrom+pos).")


@router.post("/design")
def design_caps_primers(req: CapsDesignRequest) -> dict:
    """设计 CAPS/dCAPS 引物对（三种输入模式，见 CapsDesignRequest）。

    用法:
        POST /api/caps/design
        {
          "seq1": "...", "seq2": "...",          // 模式 1：粘贴序列
          "mismatch_max": 1
        }
    """
    enzymes = _resolve_enzymes(req)
    seq1, seq2, snp_meta = _resolve_sequences(req)

    try:
        designs = design_caps_dcaps(
            seq1, seq2,
            enzymes=enzymes,
            mismatch_max=req.mismatch_max,
            primer_len=tuple(req.primer_len),
            tm_range=tuple(req.tm_range),
            product_size=tuple(req.product_size),
            top_n=req.top_n,
        )
    except ValueError as e:
        raise ValidationFailure(str(e)) from e

    # Locate the SNP for the response metadata.
    snp_pos = next(
        (i for i, (a, b) in enumerate(zip(seq1, seq2)) if a != b), None)
    return ok({
        "snp": {"pos_in_seq": snp_pos, **snp_meta},
        "enzyme_count": len(enzymes),
        "total_designs": len(designs),
        "designs": designs,
    })
