"""BLAST output parsing and amplicon pairing for specificity checking."""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class BlastHit:
    """A single BLAST hit for a short primer query."""

    query: str
    qstart: int
    qend: int
    target: str
    tstart: int
    tend: int
    strand: str  # 'plus' or 'minus'


@dataclass(frozen=True)
class AmpliconPair:
    """A paired plus/minus hit forming a candidate amplicon."""

    db_name: str
    target: str
    plus_ts: int
    plus_te: int
    minus_ts: int
    minus_te: int
    size: int
    plus_query: str
    plus_qs: int
    plus_qe: int
    minus_query: str
    minus_qs: int
    minus_qe: int


def parse_blast_outfmt6(lines: Iterable[str]) -> List[BlastHit]:
    """Parse BLAST -outfmt '6 qseqid qstart qend sseqid sstart send sstrand'."""
    hits: List[BlastHit] = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        query, qs, qe, target, ts, te, strand = parts[:7]
        hits.append(
            BlastHit(
                query=query,
                qstart=int(qs),
                qend=int(qe),
                target=target,
                tstart=int(ts),
                tend=int(te),
                strand=strand,
            )
        )
    return hits


def pair_amplicons(
    hits: List[BlastHit],
    group_for_query: Dict[str, str],
    db_name: str,
    size_start: int,
    size_stop: int,
) -> List[AmpliconPair]:
    """Pair plus-strand and minus-strand hits into candidate amplicons.

    This mirrors the logic in _run_specificity_check.pl:
      - plus hits are keyed by their target start
      - minus hits are keyed by their target end
      - sorted target positions are scanned; for each plus hit, subsequent
        minus hits are considered if the implied amplicon size is within range.
    """
    # Group hits by (group, target, position)
    # position = tstart for plus, tend for minus
    grouped: Dict[str, Dict[str, Dict[int, List[BlastHit]]]] = {}
    for hit in hits:
        group = group_for_query.get(hit.query)
        if group is None:
            continue
        target_map = grouped.setdefault(group, {})
        pos_map = target_map.setdefault(hit.target, {})
        pos = hit.tstart if hit.strand == "plus" else hit.tend
        pos_map.setdefault(pos, []).append(hit)

    pairs: List[AmpliconPair] = []
    for group, target_map in grouped.items():
        for target, pos_map in target_map.items():
            positions = sorted(pos_map.keys())
            for i, pos in enumerate(positions):
                for plus_hit in pos_map[pos]:
                    if plus_hit.strand != "plus":
                        continue
                    for next_pos in positions[i + 1 :]:
                        for minus_hit in pos_map[next_pos]:
                            if minus_hit.strand != "minus":
                                continue
                            # Amplicon size is measured from the 5' end of the
                            # plus-strand primer to the 5' end of the minus-strand
                            # primer. For a minus-strand BLAST hit, tstart is the
                            # 5' end (larger coordinate), tend is the 3' end.
                            size = minus_hit.tstart - plus_hit.tstart + 1
                            if size < size_start:
                                continue
                            if size > size_stop:
                                break
                            pairs.append(
                                AmpliconPair(
                                    db_name=db_name,
                                    target=target,
                                    plus_ts=plus_hit.tstart,
                                    plus_te=plus_hit.tend,
                                    minus_ts=minus_hit.tstart,
                                    minus_te=minus_hit.tend,
                                    size=size,
                                    plus_query=plus_hit.query,
                                    plus_qs=plus_hit.qstart,
                                    plus_qe=plus_hit.qend,
                                    minus_query=minus_hit.query,
                                    minus_qs=minus_hit.qstart,
                                    minus_qe=minus_hit.qend,
                                )
                            )
    return pairs


def write_filterlength(path: Path, pairs: List[AmpliconPair]) -> None:
    """Write the intermediate ``.out.filterlength`` file."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            "#db_name\ttarget\tts\tte\tnext_ts\tnext_te\tsize\t"
            "query\tqs\tqe\tnext_query\tnext_qs\tnext_qe\n"
        )
        for p in pairs:
            fh.write(
                f"{p.db_name}\t{p.target}\t{p.plus_ts}\t{p.plus_te}\t"
                f"{p.minus_ts}\t{p.minus_te}\t{p.size}\t"
                f"{p.plus_query}\t{p.plus_qs}\t{p.plus_qe}\t"
                f"{p.minus_query}\t{p.minus_qs}\t{p.minus_qe}\n"
            )
