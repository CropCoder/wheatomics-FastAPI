"""KASP primer design for a single SNP.

Pure-Python enumeration (no external process).  Given two equal-length allele
sequences that differ at exactly one SNP, design:

  * two allele-specific primers ending on the SNP base (one per allele);
  * one common primer on the opposite side.

The SNP can be discriminated by a forward primer (common = reverse primer) or
by a reverse primer (common = forward primer); both orientations are returned
and ranked.  The KASP fluorescent tails (FAM/HEX etc.) are intentionally not
added here — these are the core primers that go into a KASP assay.

Tm uses the PrimerServer2 nearest-neighbour model; GC, homopolymer runs and
simple 3'-complement/dimer checks reject poor candidates.
"""

from __future__ import annotations

from app.primerserver2.services.thermo import primer_tm, reverse_complement

_ALLOWED = frozenset("ACGT")
_MIN_PRODUCT = 50
_MAX_PRODUCT = 250


def _rc(seq: str) -> str:
    return reverse_complement(seq)


def _gc(seq: str) -> float:
    return (seq.count("G") + seq.count("C")) / len(seq)


def _valid_primer(seq: str, tm_range: tuple[float, float]) -> float | None:
    """Return Tm if `seq` passes the basic KASP primer checks, else None."""
    if len(seq) < 16 or len(seq) > 32 or any(b not in _ALLOWED for b in seq):
        return None
    gc = _gc(seq)
    if not (0.35 <= gc <= 0.65):
        return None
    if any(seq[i] == seq[i + 1] == seq[i + 2] == seq[i + 3]
           for i in range(len(seq) - 3)):
        return None
    # avoid a self-complementary 3' end and very stable 3' GC runs
    tail = seq[-5:]
    if tail == _rc(tail):
        return None
    if seq[-1] in "GC" and seq[-2] in "GC" and seq[-3] in "GC":
        return None
    tm = primer_tm(seq)
    if tm is None or not (tm_range[0] <= tm <= tm_range[1]):
        return None
    return round(float(tm), 2)


def _bad_dimer(a: str, b: str) -> bool:
    """True if the 3' ends of a and b can anneal (last 4-8 bases)."""
    max_k = min(8, len(a), len(b))
    for k in range(4, max_k + 1):
        if a[-k:] == _rc(b[-k:]):
            return True
    return False


def _amplicon(seq: str, start: int, end: int) -> str:
    return seq[max(0, start):min(len(seq), end + 1)]


def design_kasp(
    seq1: str,
    seq2: str,
    *,
    primer_len: tuple[int, int] = (20, 27),
    tm_range: tuple[float, float] = (55.0, 65.0),
    product_size: tuple[int, int] = (_MIN_PRODUCT, _MAX_PRODUCT),
    top_n: int = 20,
) -> list[dict]:
    """Design KASP primers discriminating seq1 vs seq2 (one SNP)."""
    seq1 = seq1.upper()
    seq2 = seq2.upper()
    if len(seq1) != len(seq2):
        raise ValueError("KASP requires equal-length allele sequences")
    if len(seq1) < 40:
        raise ValueError("sequences must be at least 40 bp")
    if any(b not in _ALLOWED for b in seq1 + seq2):
        raise ValueError("sequences may only contain A/C/G/T")
    diffs = [i for i, (a, b) in enumerate(zip(seq1, seq2)) if a != b]
    if len(diffs) != 1:
        raise ValueError(
            f"KASP requires exactly one SNP; found {len(diffs)} difference(s)")
    snp = diffs[0]
    plo, phi = max(16, int(primer_len[0])), min(32, int(primer_len[1]))
    if phi < plo:
        raise ValueError("invalid primer length range")
    pmin = max(_MIN_PRODUCT, int(product_size[0]))
    pmax = min(_MAX_PRODUCT, int(product_size[1]))
    if pmax <= pmin:
        pmin, pmax = _MIN_PRODUCT, _MAX_PRODUCT
    lengths = list(range(plo, phi + 1))
    designs: list[dict] = []

    def add_design(orientation, p1, p2, common, start, end, prod):
        tm1 = _valid_primer(p1, tm_range)
        tm2 = _valid_primer(p2, tm_range)
        tmc = _valid_primer(common, tm_range)
        if tm1 is None or tm2 is None or tmc is None:
            return
        if abs(tm1 - tm2) > 5.0 or abs(tmc - (tm1 + tm2) / 2.0) > 5.0:
            return
        if _bad_dimer(p1, p2) or _bad_dimer(p1, common) or _bad_dimer(p2, common):
            return
        if p1[-1] == p2[-1]:
            return
        if orientation == "forward":
            amp_start, amp_end = start, end
        else:
            amp_start, amp_end = start, end
        gc1, gc2, gcc = _gc(p1), _gc(p2), _gc(common)
        tm_pen = abs(tm1 - tm2) + abs(tmc - (tm1 + tm2) / 2.0)
        gc_pen = abs(gc1 - 0.5) + abs(gc2 - 0.5) + abs(gcc - 0.5)
        prod_pen = abs(prod - 100) / 25.0
        score = round(tm_pen + 10.0 * gc_pen + prod_pen, 3)
        row = {
            "rank": 0,
            "orientation": orientation,
            "allele1_primer": p1,
            "allele2_primer": p2,
            "common_primer": common,
            "product_size": prod,
            "tm_allele1": tm1,
            "tm_allele2": tm2,
            "tm_common": tmc,
            "gc_allele1": round(gc1 * 100, 1),
            "gc_allele2": round(gc2 * 100, 1),
            "gc_common": round(gcc * 100, 1),
            "snp_pos_in_seq": snp,
            "snp_allele1": seq1[snp],
            "snp_allele2": seq2[snp],
            "amplicon_start": amp_start,
            "amplicon_end": amp_end,
            "amplicon": _amplicon(seq1, amp_start, amp_end),
            "score": score,
        }
        designs.append(row)

    # Orientation 1: allele-specific forward primers, common reverse primer.
    for plen in lengths:
        start = snp - plen + 1
        if start < 0:
            continue
        p1 = seq1[start:snp + 1]
        p2 = seq2[start:snp + 1]
        if p1[:-1] != p2[:-1]:
            continue
        for rlen in lengths:
            for cstart in range(snp + 1, len(seq1) - rlen + 1):
                prod = cstart + rlen - start
                if not (pmin <= prod <= pmax):
                    continue
                common = _rc(seq1[cstart:cstart + rlen])
                if p1[-1] == common[-1]:
                    continue
                add_design("forward", p1, p2, common, start, cstart + rlen - 1, prod)

    # Orientation 2: allele-specific reverse primers, common forward primer.
    for plen in lengths:
        if snp + plen > len(seq1):
            continue
        p1 = _rc(seq1[snp:snp + plen])
        p2 = _rc(seq2[snp:snp + plen])
        if p1[:-1] != p2[:-1]:
            continue
        for flen in lengths:
            for cstart in range(0, snp - flen + 1):
                prod = snp + plen - cstart
                if not (pmin <= prod <= pmax):
                    continue
                common = seq1[cstart:cstart + flen]
                if p1[-1] == common[-1]:
                    continue
                add_design("reverse", p1, p2, common, cstart, snp + plen - 1, prod)

    # de-duplicate identical primer trios, then rank.
    uniq: dict[tuple, dict] = {}
    for row in designs:
        key = (row["orientation"], row["allele1_primer"],
               row["allele2_primer"], row["common_primer"])
        if key not in uniq or row["score"] < uniq[key]["score"]:
            uniq[key] = row
    ordered = sorted(uniq.values(), key=lambda r: (
        r["score"], 0 if r["orientation"] == "forward" else 1,
        r["product_size"]))
    for i, row in enumerate(ordered[:top_n], 1):
        row["rank"] = i
    return ordered[:top_n]
