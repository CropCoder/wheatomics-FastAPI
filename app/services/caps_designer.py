"""CAPS/dCAPS primer design — Neff et al. (2002) style enumeration.

Pure Python, no external dependencies. Given two allele sequences that
differ at exactly one position (a SNP), enumerate restriction enzymes and
primer placements such that:

  * CAPS  — the SNP itself creates/destroys a natural restriction site
            (0 primer mismatches);
  * dCAPS — 1..mismatch_max bases in the primer are altered so that the
            primer + template forms a restriction site in one allele only.

The recognition site must lie entirely inside the designed primer, the
opposite primer is picked from the product-size window by GC/Tm rules,
and any additional copy of the enzyme's site in the amplicon (a "problem
site" that would cut both alleles) rejects the design.

Tm is computed with the PrimerServer2 nearest-neighbour model
(app/primerserver2/services/thermo.py); mismatches get a heuristic
penalty (3 C each, 4 C in the last 5 bases of the 3' end).

Both orientations are tried: the caller's sequences are also run
reverse-complemented, and those designs are converted back so the
reported primer_f/primer_r always match the caller's sequences.
"""

from __future__ import annotations

from bisect import bisect_left

from app.primerserver2.services.thermo import primer_tm, reverse_complement

from .restriction_enzymes import RESTRICTION_ENZYMES

_IUPAC = {
    "A": "A", "C": "C", "G": "G", "T": "T",
    "R": "AG", "Y": "CT", "S": "CG", "W": "AT",
    "K": "GT", "M": "AC", "B": "CGT", "D": "AGT",
    "H": "ACT", "V": "ACG", "N": "ACGT",
}

_SIMPLE_RE = frozenset("ACGT")


def _rc(seq: str) -> str:
    return reverse_complement(seq)


def _iupac_contains(code: str, base: str) -> bool:
    return base in _IUPAC[code]


def _alt_base(template: str, code: str) -> str:
    """A primer base allowed by `code` that differs from `template`."""
    for b in _IUPAC[code]:
        if b != template:
            return b
    return _IUPAC[code][0]


def _site_matches(seq: str, pos: int, rec: str) -> bool:
    """True if `rec` (IUPAC) matches seq[pos:pos+len(rec)] on the top strand."""
    if pos < 0 or pos + len(rec) > len(seq):
        return False
    return all(_iupac_contains(rec[i], seq[pos + i]) for i in range(len(rec)))


def _find_natural_sites(seq: str, rec: str) -> list[int]:
    """All 0-based positions where `rec` matches `seq` on either strand."""
    sites: list[int] = []
    rc_rec = _rc(rec)
    for pos in range(len(seq) - len(rec) + 1):
        if _site_matches(seq, pos, rec) or _site_matches(seq, pos, rc_rec):
            sites.append(pos)
    return sites


class _OppositeCandidate:
    __slots__ = ("seq", "tm", "pos")

    def __init__(self, seq: str, tm: float, pos: int):
        self.seq, self.tm, self.pos = seq, tm, pos


def _build_opposite_candidates(
    seq: str, primer_len: tuple[int, int], tm_range: tuple[float, float],
) -> list[_OppositeCandidate]:
    """All valid opposite-primer candidates, precomputed once per sequence.

    Candidate = reverse-complement of a window of seq; GC 40-60%, no
    4-base homopolymer run, Tm inside tm_range.
    """
    cands: list[_OppositeCandidate] = []
    lengths = {primer_len[0], primer_len[1], (primer_len[0] + primer_len[1]) // 2}
    for plen in sorted(lengths):
        for start in range(len(seq) - plen + 1):
            window = seq[start:start + plen]
            if "N" in window:
                continue
            gc = (window.count("G") + window.count("C")) / plen
            if not (0.40 <= gc <= 0.60):
                continue
            if any(window[i] == window[i + 1] == window[i + 2] == window[i + 3]
                   for i in range(plen - 3)):
                continue
            primer = _rc(window)
            tm = primer_tm(primer)
            if tm_range[0] <= tm <= tm_range[1]:
                cands.append(_OppositeCandidate(seq=primer, tm=tm, pos=start))
    return cands


def _alignment_block(
    seq1: str, seq2: str, primer: str, primer_start: int,
    rec: str, rec_start: int, enzyme: str,
    cut_top: int, cut_bottom: int,
) -> str:
    """indCAPS-style ASCII alignment of seq1/seq2/primer/recognition.

    The window covers the primer plus the recognition site (which may
    extend past the primer's 3' end into the extension region).
    """
    L = len(rec)
    primer_end = primer_start + len(primer) - 1
    view_start = max(0, min(primer_start, rec_start, cut_top) - 2)
    view_end = min(len(seq1),
                   max(primer_end + 1, rec_start + L, cut_bottom + 1) + 2)

    def pad(text: str, start: int) -> str:
        return (" " * (start - view_start) + text
                + " " * (view_end - start - len(text)))

    marked = pad("".join(
        b.lower() if b != seq1[i] else b
        for i, b in zip(range(primer_start, primer_end + 1), primer)),
        primer_start)
    rec_row = pad(rec, rec_start)
    snp_row = [" "] * (view_end - view_start)
    for i in range(view_start, view_end):
        if seq1[i] != seq2[i]:
            snp_row[i - view_start] = "*"
    snp_row = "".join(snp_row)
    cut_row = [" "] * (view_end - view_start)
    for c in (cut_top, cut_bottom):
        if view_start <= c < view_end:
            cut_row[c - view_start] = "^"
    cut_row = "".join(cut_row)
    return (
        f"Enzyme: {enzyme}  recognition: {rec}\n"
        f"Seq1  : {seq1[view_start:view_end]}\n"
        f"Seq2  : {seq2[view_start:view_end]}\n"
        f"SNP   : {snp_row}\n"
        f"Primer: {marked}\n"
        f"        {rec_row}\n"
        f"cut   : {cut_row}\n"
    )


def _tm_with_mismatch_penalty(
    primer: str, mism_at: list[int], primer_start: int,
    rec_start: int, tm_range: tuple[float, float],
) -> float | None:
    """nn_tm on the full primer, minus heuristic mismatch penalties."""
    tm = primer_tm(primer)
    for rec_i in mism_at:
        pos = rec_start + rec_i - primer_start
        tm -= 4.0 if pos >= len(primer) - 5 else 3.0
    if not (tm_range[0] <= tm <= tm_range[1]):
        return None
    return round(tm, 1)


def _extra_site_in_primer(
    primer: str, rec: str, design_lo: int | None,
) -> bool:
    """True if `primer` carries the recognition on either strand anywhere
    other than the designed anchor position (design_lo, or None to treat
    every match as extra — used for the plain opposite primer).
    """
    rc_rec = _rc(rec)
    for pos in range(len(primer) - len(rec) + 1):
        if (_site_matches(primer, pos, rec)
                or _site_matches(primer, pos, rc_rec)):
            if pos == design_lo:
                continue  # the designed site itself
            return True
    return False


def _score(mismatches: int, tm_diff: float, common: bool, cut_from_3end: int) -> tuple:
    """Lower is better."""
    return (mismatches, round(tm_diff, 1), 0 if common else 1, cut_from_3end)


def design_caps_dcaps(
    seq1: str,
    seq2: str,
    *,
    enzymes: list[dict] | None = None,
    mismatch_max: int = 1,
    primer_len: tuple[int, int] = (20, 27),
    tm_range: tuple[float, float] = (55.0, 65.0),
    product_size: tuple[int, int] = (100, 1000),
    top_n: int = 20,
) -> list[dict]:
    """Design CAPS/dCAPS primer pairs discriminating seq1 vs seq2.

    seq1/seq2 must be equal-length A/C/G/T strings differing at exactly
    one position. `enzymes` defaults to the built-in library; pass a list
    of dicts {name, recognition, cut:(l,r)} to use a subset or custom
    enzymes. Designs are returned for both primer orientations; the
    reported primer_f/primer_r always match the caller's sequences.
    """
    seq1 = seq1.upper()
    seq2 = seq2.upper()
    if len(seq1) != len(seq2):
        raise ValueError("sequences must have the same length")
    if len(seq1) < 40:
        raise ValueError(
            "sequences must be at least 40 bp (need primer + SNP flanking)")
    if any(b not in _SIMPLE_RE for b in seq1 + seq2):
        raise ValueError("sequences may only contain A/C/G/T")
    diffs = [(i, a, b) for i, (a, b) in enumerate(zip(seq1, seq2)) if a != b]
    if not diffs:
        raise ValueError("sequences are identical — no SNP to discriminate")
    if len(diffs) > 1:
        raise ValueError(
            f"{len(diffs)} differences found; exactly one SNP is required "
            "(split multi-SNP loci into single-SNP queries)")
    if not (0 <= mismatch_max <= 3):
        raise ValueError("mismatch_max must be 0-3")

    if enzymes is None:
        enzymes = RESTRICTION_ENZYMES

    raw = _design_orientation(seq1, seq2, enzymes, mismatch_max,
                              primer_len, tm_range, product_size, "F")
    raw += _design_orientation(_rc(seq1), _rc(seq2), enzymes, mismatch_max,
                               primer_len, tm_range, product_size, "R")
    designs = [_finalize(d, len(seq1)) for d in raw]

    designs.sort(key=lambda d: _score(
        d["mismatch_count"],
        999.0 if (d["tm_f"] is None or d["tm_r"] is None)
        else abs(d["tm_f"] - d["tm_r"]),
        d["common"], d["cut_from_3end"]))
    for rank, d in enumerate(designs[:top_n], 1):
        d["rank"] = rank
        d["mode"] = "caps" if d["mismatch_count"] == 0 else "dcaps"
    return designs[:top_n]


def _design_orientation(
    seq1: str,
    seq2: str,
    enzymes: list[dict],
    mismatch_max: int,
    primer_len: tuple[int, int],
    tm_range: tuple[float, float],
    product_size: tuple[int, int],
    side: str,
) -> list[dict]:
    """Enumerate designs whose designed primer sits at the LEFT end of seq1.

    Returns raw internal dicts (with `_`-prefixed fields) in this
    orientation's coordinates; `_finalize` converts side "R" designs back
    to the caller's coordinate system.
    """
    snp_pos, base1, base2 = next(
        (i, a, b) for i, (a, b) in enumerate(zip(seq1, seq2)) if a != b)

    opp_cands = _build_opposite_candidates(seq1, primer_len, tm_range)
    if not opp_cands:
        return []
    opp_by_start: dict[int, list[_OppositeCandidate]] = {}
    for c in opp_cands:
        opp_by_start.setdefault(c.pos, []).append(c)
    opp_starts = sorted(opp_by_start)

    min_len, max_len = primer_len
    lengths = sorted({min_len, max_len, (min_len + max_len) // 2})
    pmin, pmax = product_size

    results: list[dict] = []
    for enz in enzymes:
        rec = enz["recognition"].upper()
        L = len(rec)
        cut_l, cut_r = enz["cut"]
        sites1 = set(_find_natural_sites(seq1, rec))
        sites2 = set(_find_natural_sites(seq2, rec))

        for anchor in range(L):
            # The recognition site sits at [rec_start, rec_start+L) with
            # the SNP at its index `anchor`. The designed primer covers
            # indices [0, anchor) of the site and ENDS at the base just
            # 5' of the SNP (primer_end = rec_start + anchor - 1); the
            # SNP and the rest of the site come from the template via
            # polymerase extension. Allele1's extension completes the
            # site, allele2's SNP base breaks it — this is what makes
            # the amplicons differentially digestible.
            rec_start = snp_pos - anchor
            if rec_start < 0 or rec_start + L > len(seq1):
                continue
            if not _iupac_contains(rec[anchor], base1):
                continue
            if _iupac_contains(rec[anchor], base2):
                continue
            # Site letters 3' of the SNP come from the template in both
            # alleles and cannot be fixed by primer mismatches.
            if any(not _iupac_contains(rec[i], seq1[rec_start + i])
                   for i in range(anchor + 1, L)):
                continue
            # Site letters 5' of the SNP are primer-contributed; template
            # disagreements there are the dCAPS mismatches.
            mism_at = [i for i in range(anchor)
                       if not _iupac_contains(rec[i], seq1[rec_start + i])]
            if len(mism_at) > mismatch_max:
                continue

            primer_end = rec_start + anchor - 1
            for plen in lengths:
                primer_start = primer_end - plen + 1
                if primer_start < 0:
                    continue
                primer = _build_primer(seq1, primer_start, primer_end,
                                       rec_start, rec, mism_at)
                if primer is None:
                    continue
                if _extra_site_in_primer(primer, rec, None):
                    continue
                tm = _tm_with_mismatch_penalty(
                    primer, mism_at, primer_start, rec_start, tm_range)
                if tm is None:
                    continue
                yield_design(primer, primer_start, primer_end, mism_at,
                             tm, rec_start, rec, enz, cut_l, cut_r, L,
                             sites1, sites2, opp_by_start, opp_starts,
                             pmin, pmax, side, seq1, seq2, results)
    return results


def yield_design(
    primer: str, primer_start: int, primer_end: int, mism_at: list[int],
    tm: float, rec_start: int, rec: str, enz: dict,
    cut_l: int, cut_r: int, L: int,
    sites1: set[int], sites2: set[int],
    opp_by_start: dict[int, list[_OppositeCandidate]],
    opp_starts: list[int], pmin: int, pmax: int, side: str,
    seq1: str, seq2: str, results: list[dict],
) -> None:
    """Pair one designed primer with an opposite primer and record it."""
    cut_top = rec_start + cut_l
    cut_bottom = rec_start + cut_r
    if cut_top < primer_start:
        return

    # Opposite primer within the product window. When no candidate exists
    # (short input), the design is still reported without primer_r — like
    # indCAPS, the caller supplies the other side themselves.
    win_lo = primer_end + 1 + pmin
    win_hi = primer_end + 1 + pmax
    best_opp: _OppositeCandidate | None = None
    best_tm_diff = float("inf")
    for s in opp_starts[bisect_left(opp_starts, win_lo):]:
        if s > win_hi:
            break
        for c in opp_by_start[s]:
            diff = abs(c.tm - tm)
            if diff < best_tm_diff:
                best_tm_diff = diff
                best_opp = c

    if best_opp is None:
        # Assume the amplicon may extend to the sequence end.
        r_end = len(seq1) - 1
    else:
        r_end = best_opp.pos + len(best_opp.seq) - 1

    # Type IIS guard: the bottom-strand cut must also fall inside the
    # amplicon.
    if cut_bottom > r_end:
        return
    # Opposite primer must not carry a complete copy of the site (it is
    # identical in both alleles → would cut both).
    if best_opp is not None and _extra_site_in_primer(best_opp.seq, rec, None):
        return
    # Natural sites present in BOTH alleles strictly between the two
    # primers → the enzyme would cut both alleles. (The designed site at
    # rec_start is natural in seq1 only, so it never enters this
    # intersection.)
    bad = any(
        primer_end + 1 <= s <= r_end - L + 1
        and (best_opp is None or s + L - 1 <= best_opp.pos - 1)
        for s in sites1 & sites2)
    if bad:
        return

    results.append({
        "side": side,
        "enzyme": enz["name"],
        "recognition": rec,
        "common": enz["common"],
        "mismatch_count": len(mism_at),
        "_primer": primer,
        "_opp": best_opp,
        "_primer_start": primer_start,
        "_primer_end": primer_end,
        "_rec_start": rec_start,
        "_mism_at": mism_at,
        "_cut_top": cut_top,
        "_cut_bottom": cut_bottom,
        "_tm": tm,
        "_seq1": seq1,
        "_seq2": seq2,
    })


def _build_primer(
    seq1: str, primer_start: int, primer_end: int,
    rec_start: int, rec: str, mism_at: list[int],
) -> str | None:
    """Primer = template copy with mismatches only inside the recognition."""
    mism_set = set(mism_at)
    bases = []
    for i in range(primer_start, primer_end + 1):
        rec_i = i - rec_start
        if 0 <= rec_i < len(rec):
            t = seq1[i]
            if rec_i in mism_set:
                bases.append(_alt_base(t, rec[rec_i]))
            elif _iupac_contains(rec[rec_i], t):
                bases.append(t)
            else:  # recognition requires a mismatch we didn't budget
                return None
        else:
            bases.append(seq1[i])
    return "".join(bases)


def _finalize(d: dict, seq_len: int) -> dict:
    """Convert a raw design dict into the caller-facing shape.

    Side "F" designs pass through; side "R" designs (enumerated on the
    reverse-complemented pair) are mapped back so primer_f/primer_r and
    all positions refer to the caller's sequences.
    """
    L = len(d["_primer"])
    opp = d["_opp"]
    if d["side"] == "F":
        primer_f = d["_primer"]
        primer_r = opp.seq if opp is not None else None
        designed_tm, opp_tm = d["_tm"], (opp.tm if opp is not None else None)
        mismatch_positions = sorted(
            d["_rec_start"] + i - d["_primer_start"]
            for i in d["_mism_at"])
        cut_pos = d["_cut_top"] - d["_primer_start"]
        alignment = _alignment_block(
            d["_seq1"], d["_seq2"], d["_primer"], d["_primer_start"],
            d["recognition"], d["_rec_start"], d["enzyme"],
            d["_cut_top"], d["_cut_bottom"])
    else:
        # Designed primer (left end of the RC pair) becomes the reverse
        # primer; its RC opposite becomes the forward primer.
        primer_f = _rc(d["_opp"].seq) if d["_opp"] is not None else None
        primer_r = _rc(d["_primer"])
        designed_tm, opp_tm = d["_tm"], (d["_opp"].tm if d["_opp"] is not None else None)
        E = d["_primer_end"]
        mismatch_positions = sorted(
            E - d["_rec_start"] - i for i in d["_mism_at"])
        cut_pos = E - d["_cut_top"]
        # Bottom-strand view: the shown sequences are the RC pair the
        # enumeration ran on (the caller's bottom strand).
        alignment = _alignment_block(
            d["_seq1"], d["_seq2"], d["_primer"], d["_primer_start"],
            d["recognition"], d["_rec_start"], d["enzyme"],
            d["_cut_top"], d["_cut_bottom"]) + "      (bottom-strand view)\n"

    product_size = (
        d["_opp"].pos + len(d["_opp"].seq) - d["_primer_start"]
        if d["_opp"] is not None else None)
    return {
        "enzyme": d["enzyme"],
        "recognition": d["recognition"],
        "common": d["common"],
        "designed_primer": "F" if d["side"] == "F" else "R",
        "mismatch_count": d["mismatch_count"],
        "mismatch_positions": mismatch_positions,
        "cut_pos": cut_pos,
        "cut_from_3end": L - 1 - cut_pos,
        "primer_f": primer_f,
        "primer_r": primer_r,
        "tm_f": opp_tm if d["side"] == "R" else designed_tm,
        "tm_r": designed_tm if d["side"] == "R" else opp_tm,
        "product_size": product_size,
        "alignment": alignment,
    }
