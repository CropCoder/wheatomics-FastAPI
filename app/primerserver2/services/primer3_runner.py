"""Primer3 runner for PrimerServer2 (Python replacement for _run_primer3.pl)."""

import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from .fasta_utils import faidx_fetch, sequence_length


_REGION_LINE_RE = re.compile(r"^\s*(\S+)\s+(\S+)\s*(\S*)?\s*(\S*)?\s*(\S*)?\s*")


class Primer3Region:
    """A single target region for primer design."""

    def __init__(
        self,
        chrom: str,
        target_start: int,
        target_length: int,
        size_min: int,
        size_max: int,
    ):
        self.chrom = chrom
        self.target_start = target_start
        self.target_length = target_length
        self.size_min = size_min
        self.size_max = size_max

    @property
    def region_id(self) -> str:
        return f"{self.chrom}-{self.target_start}-{self.target_length}"

    def retrieve_window(self) -> Tuple[int, int]:
        """Return the flanking window around the target suitable for samtools."""
        start = max(1, self.target_start - self.size_max)
        end = self.target_start + self.target_length + self.size_max
        return start, end

    @property
    def retrieve_region(self) -> str:
        start, end = self.retrieve_window()
        return f"{self.chrom}:{start}-{end}"


def parse_input_regions(
    input_path: Path,
    db: Path,
    product_size_min: int,
    product_size_max: int,
) -> List[Primer3Region]:
    """Parse the tab-delimited input region list."""
    regions: List[Primer3Region] = []
    lengths = sequence_length(db)

    with open(input_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            chrom = parts[0]
            target_start_str = parts[1] if len(parts) > 1 else ""
            target_length_str = parts[2] if len(parts) > 2 else ""
            size_min_str = parts[3] if len(parts) > 3 else ""
            size_max_str = parts[4] if len(parts) > 4 else ""

            if target_start_str:
                target_start = int(target_start_str.replace(",", ""))
            else:
                target_start = 1

            if target_length_str:
                target_length = int(target_length_str.replace(",", ""))
            elif target_start == 1:
                # ID only: whole template (qRT-PCR)
                target_length = lengths.get(chrom, 0)
            else:
                # ID + position only: SNP, length = 1
                target_length = 1

            if target_length > 1_000_000:
                raise ValueError(
                    f"Target region length too long: {chrom}: {target_length} bp"
                )

            size_min = int(size_min_str) if size_min_str else product_size_min
            size_max = int(size_max_str) if size_max_str else product_size_max

            regions.append(
                Primer3Region(chrom, target_start, target_length, size_min, size_max)
            )
    return regions


def generate_primer3_input(
    regions: List[Primer3Region],
    sequences: dict,
    region_type: str,
    output_path: Path,
) -> None:
    """Generate a primer3 input file from retrieved sequences."""
    with open(output_path, "w", encoding="utf-8") as fh:
        for region in regions:
            seq = sequences.get(region.retrieve_region, "")
            if not seq:
                continue
            start, _ = region.retrieve_window()
            relative_target_start = region.target_start - start

            if region_type == "SEQUENCE_TARGET":
                fh.write(
                    f"SEQUENCE_ID={region.region_id}\n"
                    f"SEQUENCE_TEMPLATE={seq}\n"
                    f"PRIMER_PRODUCT_SIZE_RANGE={region.size_min}-{region.size_max}\n"
                    f"SEQUENCE_TARGET={relative_target_start},{region.target_length}\n"
                    f"=\n"
                )
            elif region_type == "SEQUENCE_INCLUDED_REGION":
                fh.write(
                    f"SEQUENCE_ID={region.region_id}\n"
                    f"SEQUENCE_TEMPLATE={seq}\n"
                    f"PRIMER_PRODUCT_SIZE_RANGE={region.size_min}-{region.size_max}\n"
                    f"SEQUENCE_INCLUDED_REGION={relative_target_start},{region.target_length}\n"
                    f"=\n"
                )
            elif region_type == "FORCE_END":
                fh.write(
                    f"SEQUENCE_ID={region.region_id}-LEFT\n"
                    f"SEQUENCE_TEMPLATE={seq}\n"
                    f"PRIMER_PRODUCT_SIZE_RANGE={region.size_min}-{region.size_max}\n"
                    f"SEQUENCE_FORCE_LEFT_END={relative_target_start}\n"
                    f"PRIMER_MIN_LEFT_THREE_PRIME_DISTANCE=-1\n"
                    f"PRIMER_MIN_RIGHT_THREE_PRIME_DISTANCE=3\n"
                    f"=\n"
                    f"SEQUENCE_ID={region.region_id}-RIGHT\n"
                    f"SEQUENCE_TEMPLATE={seq}\n"
                    f"PRIMER_PRODUCT_SIZE_RANGE={region.size_min}-{region.size_max}\n"
                    f"SEQUENCE_FORCE_RIGHT_END={relative_target_start}\n"
                    f"PRIMER_MIN_RIGHT_THREE_PRIME_DISTANCE=-1\n"
                    f"PRIMER_MIN_LEFT_THREE_PRIME_DISTANCE=3\n"
                    f"=\n"
                )


def run_primer3(
    input_path: Path,
    output_path: Path,
    primer3bin: str = "primer3_core",
    primer3setting: Optional[Path] = None,
) -> None:
    """Run primer3_core and write raw output."""
    cmd = [primer3bin]
    if primer3setting:
        cmd.append(f"-p3_settings_file={primer3setting}")
    cmd.append(str(input_path))

    with open(output_path, "w", encoding="utf-8") as out_fh:
        subprocess.run(cmd, stdout=out_fh, stderr=subprocess.PIPE, text=True, check=True)


def parse_primer3_output(
    primer3_output: Path,
    simple_table: Path,
) -> None:
    """Parse primer3 output and write the simple primer table."""
    with open(primer3_output, "r", encoding="utf-8") as fh:
        content = fh.read()

    records = [r.strip() for r in content.split("\n=\n") if r.strip()]

    with open(simple_table, "w", encoding="utf-8") as out:
        out.write("#Site_ID\tPrimer_Rank\tPrimer_Seq_Left\tPrimer_Seq_Right\n")
        for record in records:
            seq_id_match = re.search(r"SEQUENCE_ID=(\S+)", record)
            error_match = re.search(r"PRIMER_ERROR=(.*)", record)
            num_match = re.search(r"PRIMER_PAIR_NUM_RETURNED=(\d+)", record)

            if not seq_id_match:
                continue
            seq_id = seq_id_match.group(1)

            if error_match:
                raise RuntimeError(f"Primer3 error: {error_match.group(1).strip()}")

            if num_match:
                num_pairs = int(num_match.group(1))
                for i in range(num_pairs):
                    left = re.search(rf"PRIMER_LEFT_{i}_SEQUENCE=(\S+)", record)
                    right = re.search(rf"PRIMER_RIGHT_{i}_SEQUENCE=(\S+)", record)
                    if left and right:
                        out.write(f"{seq_id}\t{i}\t{left.group(1)}\t{right.group(1)}\n")


def run(
    input_path: Path,
    db: Path,
    outputdir: Path,
    region_type: str = "SEQUENCE_TARGET",
    product_size_min: int = 100,
    product_size_max: int = 1000,
    samtools: str = "samtools",
    primer3bin: str = "primer3_core",
    primer3setting: Optional[Path] = None,
    debug: bool = False,
) -> None:
    """Run the full primer3 design step."""
    outputdir = Path(outputdir)
    outputdir.mkdir(parents=True, exist_ok=True)

    regions = parse_input_regions(input_path, db, product_size_min, product_size_max)
    if not regions:
        raise ValueError("No valid input regions")

    retrieve_regions = [r.retrieve_region for r in regions]
    sequences = faidx_fetch(db, retrieve_regions, samtools=samtools)

    primer3_input = outputdir / "primer3input.tmp"
    primer3_output = outputdir / "primer3output.txt"
    simple_table = outputdir / "primer3output.simple.table.txt"

    generate_primer3_input(regions, sequences, region_type, primer3_input)
    run_primer3(primer3_input, primer3_output, primer3bin, primer3setting)
    parse_primer3_output(primer3_output, simple_table)

    if not debug:
        for tmp in outputdir.glob("*.tmp"):
            tmp.unlink()
