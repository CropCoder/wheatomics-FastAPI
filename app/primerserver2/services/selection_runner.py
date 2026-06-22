"""Final selection / report generator for PrimerServer2.

Python replacement for ``_run_final_selection.pl``.  Reads Primer3 output and
specificity-check results, selects the top primer pairs, and writes the final
``primer.final.result.txt`` (and optionally a simplified HTML report).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class PrimerPair:
    rank: int
    seq_left: str
    seq_right: str
    pos_left: int
    len_left: int
    pos_right: int
    len_right: int
    tm_left: float
    tm_right: float
    gc_left: float
    gc_right: float
    self_any_left: float
    self_any_right: float
    self_end_left: float
    self_end_right: float
    hairpin_left: float
    hairpin_right: float
    end_stability_left: float
    end_stability_right: float
    pair_compl_any: float
    pair_compl_end: float
    product_size: int
    penalty: float


@dataclass
class Primer3Record:
    site_id: str
    chrom: str
    target_start: int
    target_length: int
    tag: Optional[str]
    retrieve_start: int
    pairs: List[PrimerPair] = field(default_factory=list)
    error: Optional[str] = None
    left_explain: Optional[str] = None
    right_explain: Optional[str] = None
    pair_explain: Optional[str] = None


def parse_specificity_result(path: Path) -> Dict[str, Dict[int, Dict[str, int]]]:
    """Parse specificity.check.result.txt into hit counts."""
    hit_num: Dict[str, Dict[int, Dict[str, int]]] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 5:
                continue
            site_id, rank_str, db_name, num_str, *_ = parts
            rank = int(rank_str)
            hit_num.setdefault(site_id, {}).setdefault(rank, {})[db_name] = int(num_str)
    return hit_num


def parse_amplicon_regions(path: Path) -> Dict[str, Dict[int, Dict[str, List[Tuple[str, int, int]]]]]:
    """Parse specificity.check.result.amplicon into hit region lists."""
    regions: Dict[str, Dict[int, Dict[str, List[Tuple[str, int, int]]]]] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            site_id, rank_str, db_name, target_id, tstart, tend, *_ = parts
            rank = int(rank_str)
            regions.setdefault(site_id, {}).setdefault(rank, {}).setdefault(db_name, []).append(
                (target_id, int(tstart), int(tend))
            )
    return regions


def _float_field(record: str, pattern: str) -> float:
    match = re.search(pattern, record)
    return float(match.group(1)) if match else 0.0


def _int_field(record: str, pattern: str) -> int:
    match = re.search(pattern, record)
    return int(match.group(1)) if match else 0


def parse_primer3_result(
    path: Path,
    region_type: str,
    retain: int,
) -> List[Primer3Record]:
    """Parse primer3output.txt into structured records."""
    content = path.read_text(encoding="utf-8")
    raw_records = [r.strip() for r in content.split("\n=\n") if r.strip()]

    records: List[Primer3Record] = []
    for raw in raw_records:
        id_match = re.search(r"SEQUENCE_ID=(\S+)", raw)
        if not id_match:
            continue
        site_id = id_match.group(1)

        # Parse ID like chr-target_start-target_length[-TAG]
        m = re.match(r"^(.*)-(\d+)-(\d+)(?:-(\w+))?", site_id)
        if not m:
            continue
        chrom = m.group(1)
        target_start = int(m.group(2))
        target_length = int(m.group(3))
        tag = m.group(4)

        if region_type == "FORCE_END":
            if "SEQUENCE_FORCE_LEFT_END" in raw:
                rel_match = re.search(r"SEQUENCE_FORCE_LEFT_END=(\d+)", raw)
            else:
                rel_match = re.search(r"SEQUENCE_FORCE_RIGHT_END=(\d+)", raw)
        else:
            rel_match = re.search(rf"{region_type}=(\d+),", raw)

        relative_target_start = int(rel_match.group(1)) if rel_match else 0
        retrieve_start = target_start - relative_target_start

        error_match = re.search(r"PRIMER_ERROR=(.*)", raw)
        num_match = re.search(r"PRIMER_PAIR_NUM_RETURNED=(\d+)", raw)

        record = Primer3Record(
            site_id=site_id,
            chrom=chrom,
            target_start=target_start,
            target_length=target_length,
            tag=tag,
            retrieve_start=retrieve_start,
            error=error_match.group(1).strip() if error_match else None,
            left_explain=_extract_explain(raw, "PRIMER_LEFT_EXPLAIN"),
            right_explain=_extract_explain(raw, "PRIMER_RIGHT_EXPLAIN"),
            pair_explain=_extract_explain(raw, "PRIMER_PAIR_EXPLAIN"),
        )

        if num_match and not record.error:
            num_pairs = min(int(num_match.group(1)), retain)
            for i in range(num_pairs):
                pair = _parse_pair(raw, i, retrieve_start)
                if pair:
                    record.pairs.append(pair)

        records.append(record)
    return records


def _extract_explain(record: str, key: str) -> Optional[str]:
    match = re.search(rf"{key}=(.*)", record)
    return match.group(1).strip() if match else None


def _parse_pair(raw: str, i: int, retrieve_start: int) -> Optional[PrimerPair]:
    seq_left = re.search(rf"PRIMER_LEFT_{i}_SEQUENCE=(\S+)", raw)
    seq_right = re.search(rf"PRIMER_RIGHT_{i}_SEQUENCE=(\S+)", raw)
    if not seq_left or not seq_right:
        return None

    pos_left_match = re.search(rf"PRIMER_LEFT_{i}=(\d+),(\d+)", raw)
    pos_right_match = re.search(rf"PRIMER_RIGHT_{i}=(\d+),(\d+)", raw)
    if not pos_left_match or not pos_right_match:
        return None

    pos_left = int(pos_left_match.group(1))
    len_left = int(pos_left_match.group(2))
    pos_right = int(pos_right_match.group(1))
    len_right = int(pos_right_match.group(2))

    start_left = pos_left + retrieve_start
    end_left = start_left + len_left - 1
    end_right = pos_right + retrieve_start
    start_right = end_right - len_right + 1

    return PrimerPair(
        rank=i,
        seq_left=seq_left.group(1),
        seq_right=seq_right.group(1),
        pos_left=start_left,
        len_left=len_left,
        pos_right=start_right,
        len_right=len_right,
        tm_left=_float_field(raw, rf"PRIMER_LEFT_{i}_TM=(\S+)"),
        tm_right=_float_field(raw, rf"PRIMER_RIGHT_{i}_TM=(\S+)"),
        gc_left=_float_field(raw, rf"PRIMER_LEFT_{i}_GC_PERCENT=(\S+)"),
        gc_right=_float_field(raw, rf"PRIMER_RIGHT_{i}_GC_PERCENT=(\S+)"),
        self_any_left=_float_field(raw, rf"PRIMER_LEFT_{i}_SELF_ANY_TH=(\S+)"),
        self_any_right=_float_field(raw, rf"PRIMER_RIGHT_{i}_SELF_ANY_TH=(\S+)"),
        self_end_left=_float_field(raw, rf"PRIMER_LEFT_{i}_SELF_END_TH=(\S+)"),
        self_end_right=_float_field(raw, rf"PRIMER_RIGHT_{i}_SELF_END_TH=(\S+)"),
        hairpin_left=_float_field(raw, rf"PRIMER_LEFT_{i}_HAIRPIN_TH=(\S+)"),
        hairpin_right=_float_field(raw, rf"PRIMER_RIGHT_{i}_HAIRPIN_TH=(\S+)"),
        end_stability_left=_float_field(raw, rf"PRIMER_LEFT_{i}_END_STABILITY=(\S+)"),
        end_stability_right=_float_field(raw, rf"PRIMER_RIGHT_{i}_END_STABILITY=(\S+)"),
        pair_compl_any=_float_field(raw, rf"PRIMER_PAIR_{i}_COMPL_ANY_TH=(\S+)"),
        pair_compl_end=_float_field(raw, rf"PRIMER_PAIR_{i}_COMPL_END_TH=(\S+)"),
        product_size=_int_field(raw, rf"PRIMER_PAIR_{i}_PRODUCT_SIZE=(\d+)"),
        penalty=_float_field(raw, rf"PRIMER_PAIR_{i}_PENALTY=(\S+)"),
    )


def select_primers(
    records: List[Primer3Record],
    hit_num: Dict[str, Dict[int, Dict[str, int]]],
    databases: List[str],
    primary_db: str,
    retain: int,
) -> List[Tuple[Primer3Record, List[PrimerPair]]]:
    """Sort and limit primer pairs per site."""
    selected: List[Tuple[Primer3Record, List[PrimerPair]]] = []
    for record in records:
        site_hits = hit_num.get(record.site_id, {})

        def sort_key(pair: PrimerPair) -> Tuple[int, int]:
            count = site_hits.get(pair.rank, {}).get(primary_db, 999)
            return (count, pair.rank)

        sorted_pairs = sorted(record.pairs, key=sort_key)
        limited = sorted_pairs[:retain]
        selected.append((record, limited))
    return selected


def write_text_result(
    selected: List[Tuple[Primer3Record, List[PrimerPair]]],
    hit_num: Dict[str, Dict[int, Dict[str, int]]],
    databases: List[str],
    output_path: Path,
) -> None:
    """Write primer.final.result.txt."""
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(
            "### Site_ID\tPrimer_Rank\tPrimer_Seq_Left\tPrimer_Seq_Right\t"
            "Target_Amplicon_Size\tPrimer_Pair_Penalty_Score\tDatabase\t"
            "Possible_Amplicon_Number\tPrimer_Rank_in_Primer3_output\n"
        )
        for record, pairs in selected:
            if record.error or not pairs:
                fh.write(
                    f"{record.site_id}\tNo_Primer\t{record.left_explain or ''}\t"
                    f"{record.right_explain or ''}\t{record.pair_explain or ''}\n"
                )
                continue

            site_hits = hit_num.get(record.site_id, {})
            for output_rank, pair in enumerate(pairs, 1):
                for db_name in databases:
                    count = site_hits.get(pair.rank, {}).get(db_name, 0)
                    fh.write(
                        f"{record.site_id}\t{output_rank}\t{pair.seq_left}\t{pair.seq_right}\t"
                        f"{pair.product_size}\t{pair.penalty:.1f}\t{db_name}\t{count}\t{pair.rank}\n"
                    )
            fh.write("###\n")


def run(
    primer3result: Path,
    specificity: Path,
    amplicon: Path,
    databases: List[str],
    outputdir: Path,
    retain: int = 10,
    region_type: str = "SEQUENCE_TARGET",
    detail: bool = False,
) -> None:
    """Run the final selection step."""
    outputdir = Path(outputdir)
    outputdir.mkdir(parents=True, exist_ok=True)

    hit_num = parse_specificity_result(specificity)
    hit_regions = parse_amplicon_regions(amplicon)
    records = parse_primer3_result(primer3result, region_type, retain)

    primary_db = databases[0] if databases else ""
    selected = select_primers(records, hit_num, databases, primary_db, retain)

    text_path = outputdir / "primer.final.result.txt"
    write_text_result(selected, hit_num, databases, text_path)

    if detail:
        html_path = outputdir / "primer.final.result.html"
        write_html_result(selected, hit_num, hit_regions, databases, primary_db, html_path)


def write_html_result(
    selected: List[Tuple[Primer3Record, List[PrimerPair]]],
    hit_num: Dict[str, Dict[int, Dict[str, int]]],
    hit_regions: Dict[str, Dict[int, Dict[str, List[Tuple[str, int, int]]]]],
    databases: List[str],
    primary_db: str,
    output_path: Path,
) -> None:
    """Write a simplified HTML report."""
    lines = [
        '<div class="panel-group" id="primers-result" role="tablist">',
    ]
    for site_num, (record, pairs) in enumerate(selected, 1):
        site_hits = hit_num.get(record.site_id, {})
        success = any(
            site_hits.get(pair.rank, {}).get(primary_db, 0) == 1 for pair in pairs
        )
        lines.append('<div class="panel panel-default">')
        lines.append('  <div class="panel-heading" role="tab">')
        lines.append(f"    <h4>Site {site_num}: {record.site_id}</h4>")
        if success:
            lines.append('    <span class="glyphicon glyphicon-ok"></span>')
        lines.append("  </div>")
        lines.append('  <div class="panel-body">')
        lines.append('    <ul class="list-group">')
        for pair in pairs:
            count_primary = site_hits.get(pair.rank, {}).get(primary_db, 0)
            cls = "list-group-item-success" if count_primary == 1 else ""
            lines.append(f'      <li class="list-group-item {cls}">')
            lines.append(f"        <strong>Left:</strong> {pair.seq_left}<br>")
            lines.append(f"        <strong>Right:</strong> {pair.seq_right}<br>")
            lines.append(f"        <strong>Size:</strong> {pair.product_size} bp")
            lines.append("      </li>")
        lines.append("    </ul>")
        lines.append("  </div>")
        lines.append("</div>")
    lines.append("</div>")
    output_path.write_text("\n".join(lines), encoding="utf-8")
