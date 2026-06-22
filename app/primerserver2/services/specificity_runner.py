"""Specificity-check runner for PrimerServer2 (Python replacement for
_run_specificity_check.pl).

This module runs BLAST for each primer group against each database, pairs
plus/minus hits into candidate amplicons, retrieves template sequences,
computes Tm values, applies 3′-end filters, and writes the specificity result
files consumed by the downstream selection step.
"""

import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, TextIO, Tuple

from .blast_parser import AmpliconPair, pair_amplicons, parse_blast_outfmt6, write_filterlength
from .fasta_utils import faidx_fetch, normalize_region
from .progress import log_progress, set_progress_file
from .thermo import complement, nn_tm, reverse_complement


@dataclass
class PrimerGroup:
    site_id: str
    rank: int
    sequences: List[str] = field(default_factory=list)

    @property
    def group_key(self) -> str:
        return f"{self.site_id}.{self.rank}"


@dataclass
class Query:
    name: str
    sequence: str
    group: PrimerGroup

    @property
    def group_key(self) -> str:
        return self.group.group_key


def parse_primer_input(input_path: Path) -> Tuple[List[PrimerGroup], List[Query], Dict[str, str]]:
    """Parse the simple primer table: #Site_ID Primer_Rank Primer_Seq_Left ..."""
    groups: List[PrimerGroup] = []
    queries: List[Query] = []
    group_for_query: Dict[str, str] = {}
    seen_keys: Dict[str, PrimerGroup] = {}

    with open(input_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 4:
                # Fallback: space-separated check input
                parts = line.split()
            if len(parts) < 4:
                continue

            site_id = parts[0]
            rank = int(parts[1]) if parts[1].isdigit() else 0
            seqs = parts[2:]

            key = f"{site_id}.{rank}"
            group = seen_keys.get(key)
            if group is None:
                group = PrimerGroup(site_id=site_id, rank=rank, sequences=seqs)
                seen_keys[key] = group
                groups.append(group)
            else:
                group.sequences = seqs

            for idx, seq in enumerate(seqs):
                qname = f"{key}.Primer{idx}"
                queries.append(Query(name=qname, sequence=seq.upper(), group=group))
                group_for_query[qname] = key

    return groups, queries, group_for_query


def split_queries(
    queries: List[Query],
    num_dbs: int,
    num_cpu: int,
    outputdir: Path,
) -> List[Path]:
    """Split queries into FASTA files for parallel BLAST runs.

    Number of splits = min(int(cpu / num_dbs) + 1, num_primer_groups).
    Importantly, all queries belonging to the same primer group (left/right
    primers) are written to the same file so BLAST hits can be paired later.
    """
    # Group queries by primer group so left/right primers stay together.
    group_queries: Dict[str, List[Query]] = {}
    for q in queries:
        group_queries.setdefault(q.group_key, []).append(q)

    num_groups = len(group_queries)
    split_num = min(int(num_cpu / num_dbs) + 1, num_groups)
    if split_num < 1:
        split_num = 1

    tmp_dir = outputdir / "tmp.specificity.check"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    group_keys = list(group_queries.keys())
    files: List[Path] = []
    for split in range(split_num):
        path = tmp_dir / f"primer.query.{split}.fa"
        with open(path, "w", encoding="utf-8") as fh:
            for i, key in enumerate(group_keys):
                if i % split_num == split:
                    for q in group_queries[key]:
                        fh.write(f">{q.name}\n{q.sequence}\n")
        files.append(path)

    return files


def run_blast(
    query_file: Path,
    db_file: Path,
    db_name: str,
    blastn: str,
    blast_e_value: float,
    blast_word_size: int,
    blast_identity: float,
    blast_max_hsps: int,
    num_threads: int,
) -> Path:
    """Run blastn-short for one query file against one database."""
    out_file = Path(f"{query_file}.{db_name}.out")
    cmd = [
        blastn,
        "-task", "blastn-short",
        "-query", str(query_file),
        "-db", str(db_file),
        "-evalue", str(blast_e_value),
        "-word_size", str(blast_word_size),
        "-perc_identity", str(blast_identity),
        "-dust", "no",
        "-ungapped",
        "-reward", "1",
        "-penalty", "-1",
        "-max_hsps", str(blast_max_hsps),
        "-outfmt", "6 qseqid qstart qend sseqid sstart send sstrand",
        "-out", str(out_file),
        "-num_threads", str(num_threads),
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    return out_file


def retrieve_regions_for_amplicons(
    pairs: List[AmpliconPair],
    query_seqs: Dict[str, str],
    db: Path,
    samtools: str = "samtools",
) -> Tuple[Dict[str, Dict[str, str]], Dict[str, List[Tuple[str, str, str]]]]:
    """Retrieve target sequences for amplicon ends and build lookup maps."""
    retrieve_region_data: Dict[str, List[Tuple[str, str, str]]] = {}
    unique_regions: set = set()

    for p in pairs:
        left_len = len(query_seqs[p.plus_query])
        right_len = len(query_seqs[p.minus_query])

        # End-filling coordinates from Perl code
        select_ts = p.plus_ts - p.plus_qs + 1
        select_te = p.plus_te + left_len - p.plus_qe
        select_next_ts = p.minus_ts - right_len + p.minus_qe
        select_next_te = p.minus_te + p.minus_qs - 1

        if select_ts < 0 or select_next_ts < 0:
            continue

        left_region = normalize_region(f"{p.target}:{select_ts}-{select_te}")
        right_region = normalize_region(f"{p.target}:{select_next_ts}-{select_next_te}")

        key = (p.db_name, p.plus_query)
        retrieve_region_data.setdefault(key, []).append((left_region, right_region, p.minus_query))
        unique_regions.add((str(db), left_region))
        unique_regions.add((str(db), right_region))

    # Batch fetch all unique regions per database
    db_regions: Dict[str, List[str]] = {}
    for db_path, region in unique_regions:
        db_regions.setdefault(db_path, []).append(region)

    target_seqs: Dict[str, Dict[str, str]] = {}
    for db_path, regions in db_regions.items():
        fetched = faidx_fetch(Path(db_path), regions, samtools=samtools)
        target_seqs.setdefault(Path(db_path).name, {}).update(fetched)

    # Reorganize by (db_name, query)
    per_query: Dict[str, List[Tuple[str, str, str]]] = {}
    for (db_name, query), regions in retrieve_region_data.items():
        per_query[f"{db_name}|{query}"] = regions

    return target_seqs, per_query


def _draw_alignment(
    fh: TextIO,
    query_seq: str,
    target_seq: str,
    target_pos: int,
    strand: int,
    query_label: str,
) -> None:
    """Draw primer vs template alignment in legacy PrimerServer format.

    Matching bases in the target are replaced with '.', mismatches keep the
    base letter.  For the left primer (strand=1) the target coordinates
    increase; for the right primer (strand=-1) they decrease because the
    right primer binds the minus strand.
    """
    if len(query_seq) != len(target_seq):
        return
    aligned = "".join("." if a == b else b for a, b in zip(query_seq, target_seq))
    qs = 1
    qe = len(query_seq)
    ts = target_pos
    te = ts + (qe - 1) * strand
    name_len = max(len(query_label), len("Template"))
    num_len = len(str(target_pos))
    fh.write(
        f"{query_label:<{name_len}s} {qs:>{num_len}d} {query_seq} {qe:<{num_len}d}\n"
    )
    fh.write(
        f"{'Template':<{name_len}s} {ts:>{num_len}d} {aligned} {te:<{num_len}d}\n"
    )


def specificity_check(
    groups: List[PrimerGroup],
    queries: List[Query],
    query_seqs: Dict[str, str],
    amplicons_by_db: Dict[str, List[AmpliconPair]],
    target_seqs: Dict[str, Dict[str, str]],
    retrieve_map: Dict[str, List[Tuple[str, str, str]]],
    params: "SpecificityParams",
    outputdir: Path,
    detail: bool = False,
) -> Tuple[Dict, Dict, Dict]:
    """Apply Tm / 3′-end filters and write specificity outputs."""
    hit_num_for_primer: Dict[str, Dict[int, Dict[str, int]]] = {}
    hit_regions_for_primer: Dict[str, Dict[int, Dict[str, List[Tuple]]]] = {}
    success_site: Dict[str, bool] = {}
    db_names = sorted(amplicons_by_db.keys())
    primary_db = db_names[0] if db_names else ""

    result_txt = outputdir / "specificity.check.result.txt"
    result_amp = outputdir / "specificity.check.result.amplicon"
    result_dir = outputdir / "result.specificity.check"
    result_dir.mkdir(parents=True, exist_ok=True)

    with open(result_txt, "w", encoding="utf-8") as out, open(result_amp, "w", encoding="utf-8") as amp_out:
        out.write("#Site_ID\tPrimer_Rank\tDatabase\tPossible_Amplicon_Number\tPrimer_Seqs\n")
        amp_out.write(
            "#ID\tRank\tDatabase\tTarget_ID\tTarget_start\tNext_target_end\t"
            "Left_end3\tRight_end3\tDiff_left_end3\tDiff_right_end3\n"
        )

        for group in groups:
            for db_name in db_names:
                seqs = group.sequences
                min_tm_own = min(
                    nn_tm(s, complement(s), params.primer_conc, params.Na, params.K, params.Tris, params.Mg, params.dNTPs, ion_corr=True)
                    for s in seqs
                )

                hit_num = 0
                alignment_file = result_dir / f"PrimerGroup.{db_name}.{group.site_id}.{group.rank}.txt"
                with open(alignment_file, "w", encoding="utf-8") as aln:
                    aln.write("Primer Group:\n")
                    for j, s in enumerate(seqs, 1):
                        aln.write(f"{j}:\t{s}\n")
                    aln.write(f"Minimum Melting Temperature (°C) for this group: {min_tm_own}\n")
                    aln.write(f"Database: {db_name}\n\n")

                    key_prefix = f"{db_name}|{group.group_key}"
                    for j, seq in enumerate(seqs):
                        qname = f"{group.group_key}.Primer{j}"
                        regions = retrieve_map.get(f"{db_name}|{qname}", [])
                        for left_region, right_region, next_qname in regions:
                            if hit_num >= params.max_report_amplicon:
                                break

                            target_seq = target_seqs.get(db_name, {}).get(left_region)
                            next_target_seq_raw = target_seqs.get(db_name, {}).get(right_region)
                            if target_seq is None or next_target_seq_raw is None:
                                continue
                            next_target_seq = reverse_complement(next_target_seq_raw)

                            next_seq = query_seqs[next_qname]
                            if len(seq) != len(target_seq) or len(next_seq) != len(next_target_seq):
                                continue

                            tm_1 = nn_tm(seq, complement(target_seq), params.primer_conc, params.Na, params.K, params.Tris, params.Mg, params.dNTPs, ion_corr=True)
                            tm_2 = nn_tm(next_seq, complement(next_target_seq), params.primer_conc, params.Na, params.K, params.Tris, params.Mg, params.dNTPs, ion_corr=True)
                            if tm_1 < min_tm_own - params.min_tm_diff or tm_2 < min_tm_own - params.min_tm_diff:
                                continue

                            end1 = "No" if seq[-1] == target_seq[-1] else "Yes"
                            end2 = "No" if next_seq[-1] == next_target_seq[-1] else "Yes"

                            end3_window = min(5, len(seq), len(next_seq))
                            diff1 = sum(
                                a != b for a, b in zip(seq[-end3_window:], target_seq[-end3_window:])
                            )
                            diff2 = sum(
                                a != b for a, b in zip(next_seq[-end3_window:], next_target_seq[-end3_window:])
                            )
                            if diff1 > params.end3_mismatch_threshold or diff2 > params.end3_mismatch_threshold:
                                continue

                            hit_num += 1
                            target_id, left_coords = left_region.split(":")
                            tstart = int(left_coords.split("-")[0])
                            _, right_coords = right_region.split(":")
                            # For the minus-strand region, the samtools-style
                            # string stores the 5' end (larger coordinate) first
                            # and the 3' end (smaller coordinate) second. The
                            # amplicon ends at the 5' end of the right primer.
                            right_start, right_end = right_coords.split("-")
                            next_end = int(right_start) if int(right_start) > int(right_end) else int(right_end)

                            aln.write(f"############ Amplicon {hit_num} ###########\n")
                            aln.write(f"Template: {target_id}\n")
                            aln.write(f"Template Region: {tstart}-{next_end}\n")
                            aln.write(f"Primer Left: {qname} ({seq})\n")
                            aln.write(f"Primer Right: {next_qname} ({next_seq})\n")
                            aln.write(f"Product Size: {next_end - tstart + 1} bp\n")
                            aln.write(f"Melting Temperature for Left Primer (°C): {tm_1}\n")
                            aln.write(f"Melting Temperature for Right Primer (°C): {tm_2}\n")
                            aln.write(f"Differ in the 3' End for Left Primer?: {end1}\n")
                            aln.write(f"Differ in the 3' End for Right Primer?: {end2}\n\n")

                            _draw_alignment(aln, seq, target_seq, tstart, 1, "Primer Left")
                            _draw_alignment(aln, next_seq, next_target_seq, next_end, -1, "Primer Right")
                            aln.write("\n")

                            hit_regions_for_primer.setdefault(group.site_id, {}).setdefault(group.rank, {}).setdefault(db_name, []).append(
                                (target_id, tstart, next_end)
                            )
                            amp_out.write(
                                f"{group.site_id}\t{group.rank}\t{db_name}\t{target_id}\t{tstart}\t{next_end}\t{end1}\t{end2}\t{diff1}\t{diff2}\n"
                            )

                hit_num_for_primer.setdefault(group.site_id, {}).setdefault(group.rank, {})[db_name] = hit_num
                out.write(f"{group.site_id}\t{group.rank}\t{db_name}\t{hit_num}\t{' '.join(seqs)}\n")
                if hit_num == 1 and db_name == primary_db:
                    success_site[group.site_id] = True

    return hit_num_for_primer, hit_regions_for_primer, success_site


@dataclass
class SpecificityParams:
    """Parameters controlling specificity checking."""

    size_start: int = 50
    size_stop: int = 5000
    min_tm_diff: float = 20.0
    max_report_amplicon: int = 50
    primer_conc: float = 100.0
    Na: float = 0.0
    K: float = 50.0
    Tris: float = 10.0
    Mg: float = 1.5
    dNTPs: float = 0.2
    blast_e_value: float = 30000
    blast_word_size: int = 7
    blast_identity: float = 60.0
    blast_max_hsps: int = 500
    num_cpu: int = 1
    end3_mismatch_threshold: int = 5
    report_last_5bp_in_3end: bool = True
    debug: bool = False


def run(
    input_path: Path,
    databases: List[str],
    outputdir: Path,
    params: SpecificityParams,
    samtools: str = "samtools",
    blastn: str = "blastn",
    detail: bool = False,
    progress_fh: Optional[TextIO] = None,
) -> None:
    """Run the full specificity check."""
    outputdir = Path(outputdir)
    outputdir.mkdir(parents=True, exist_ok=True)
    tmp_dir = outputdir / "tmp.specificity.check"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    if progress_fh:
        set_progress_file(progress_fh)

    log_progress(35, "specificity_blast")

    groups, queries, group_for_query = parse_primer_input(input_path)
    if not groups:
        (outputdir / "specificity.check.result.txt").write_text(
            "#Site_ID\tPrimer_Rank\tDatabase\tPossible_Amplicon_Number\tPrimer_Seqs\n"
        )
        (outputdir / "specificity.check.result.amplicon").write_text(
            "#ID\tRank\tDatabase\tTarget_ID\tTarget_start\tNext_target_end\t"
            "Left_end3\tRight_end3\tDiff_left_end3\tDiff_right_end3\n"
        )
        return

    query_seqs = {q.name: q.sequence for q in queries}
    query_files = split_queries(queries, len(databases), params.num_cpu, outputdir)

    # Run BLAST in parallel across (query_file, db) combinations.
    num_dbs = len(databases)
    split_num = len(query_files)
    run_cpu = max(1, int(params.num_cpu / split_num))

    all_pairs: List[AmpliconPair] = []
    with ThreadPoolExecutor(max_workers=params.num_cpu) as executor:
        futures = {}
        for qfile in query_files:
            for db_path in databases:
                db_name = Path(db_path).name
                future = executor.submit(
                    run_blast,
                    qfile,
                    Path(db_path),
                    db_name,
                    blastn,
                    params.blast_e_value,
                    params.blast_word_size,
                    params.blast_identity,
                    params.blast_max_hsps,
                    run_cpu,
                )
                futures[future] = (qfile, db_name)

        for future in as_completed(futures):
            qfile, db_name = futures[future]
            out_file = future.result()
            filter_file = Path(f"{out_file}.filterlength")
            hits = parse_blast_outfmt6(out_file.read_text(encoding="utf-8").splitlines())
            pairs = pair_amplicons(
                hits,
                group_for_query,
                db_name,
                params.size_start,
                params.size_stop,
            )
            write_filterlength(filter_file, pairs)
            all_pairs.extend(pairs)

    log_progress(55, "specificity_retrieve")

    # Retrieve target sequences per database.
    target_seqs: Dict[str, Dict[str, str]] = {}
    retrieve_map: Dict[str, List[Tuple[str, str, str]]] = {}
    for db_path in databases:
        db_name = Path(db_path).name
        db_pairs = [p for p in all_pairs if p.db_name == db_name]
        seqs, mapping = retrieve_regions_for_amplicons(db_pairs, query_seqs, Path(db_path), samtools=samtools)
        target_seqs.update(seqs)
        for key, regions in mapping.items():
            retrieve_map[key] = regions

    log_progress(75, "specificity_filter")

    specificity_check(
        groups,
        queries,
        query_seqs,
        {db_name: [p for p in all_pairs if p.db_name == db_name] for db_name in {p.db_name for p in all_pairs}},
        target_seqs,
        retrieve_map,
        params,
        outputdir,
        detail=detail,
    )

    if not params.debug:
        shutil.rmtree(tmp_dir, ignore_errors=True)
