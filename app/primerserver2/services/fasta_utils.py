"""FASTA sequence utilities for PrimerServer2.

The original Perl scripts rely heavily on ``samtools faidx``.  This module
wraps those calls and provides small helper functions for parsing FASTA
indices and regions.
"""

import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple


_REGION_RE = re.compile(r"^([^:]+):(\d+)-(\d+)$")


def parse_fai(path: Path) -> Dict[str, Tuple[int, int, int, int, str]]:
    """Parse a FASTA index (.fai) file.

    Returns a dict mapping sequence name to (length, offset, line_bases,
    line_bytes, qualifier).
    """
    entries: Dict[str, Tuple[int, int, int, int, str]] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 5:
                continue
            name, length, offset, line_bases, line_bytes, *rest = parts
            qualifier = rest[0] if rest else ""
            entries[name] = (int(length), int(offset), int(line_bases), int(line_bytes), qualifier)
    return entries


def parse_region(region: str) -> Tuple[str, int, int]:
    """Parse a samtools-style region string ``chr:start-end``.

    Returns (chrom, start, end) with 1-based inclusive coordinates.
    """
    match = _REGION_RE.match(region)
    if not match:
        raise ValueError(f"Invalid region format: {region}")
    chrom = match.group(1)
    start = int(match.group(2))
    end = int(match.group(3))
    return chrom, start, end


def normalize_region(region: str) -> str:
    """Return a canonical region string with start <= end.

    samtools faidx rejects regions where start > end. The original Perl code
    sometimes emits reversed coordinates for reverse-strand hits; flipping the
    coordinates preserves the fetched sequence while keeping samtools happy.
    """
    chrom, start, end = parse_region(region)
    if start > end:
        start, end = end, start
    return f"{chrom}:{start}-{end}"


def faidx_fetch(
    db: Path,
    regions: List[str],
    samtools: str = "samtools",
    batch_size: int = 500,
) -> Dict[str, str]:
    """Fetch multiple regions from an indexed FASTA using samtools faidx.

    Regions are processed in batches to avoid exceeding the operating system's
    command-line length limit (``ARG_MAX``). Returns a dict mapping region
    string to uppercase sequence string.
    """
    if not regions:
        return {}

    normalized_regions = [normalize_region(r) for r in regions]
    sequences: Dict[str, str] = {}

    for i in range(0, len(normalized_regions), batch_size):
        batch = normalized_regions[i : i + batch_size]
        cmd = [samtools, "faidx", str(db), *batch]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )

        current_name: Optional[str] = None
        lines: List[str] = []

        for line in result.stdout.splitlines():
            if line.startswith(">"):
                if current_name is not None:
                    sequences[current_name] = "".join(lines).upper()
                current_name = line[1:].split()[0]
                lines = []
            else:
                lines.append(line.strip())
        if current_name is not None:
            sequences[current_name] = "".join(lines).upper()

    return sequences


def sequence_length(db: Path, samtools: str = "samtools") -> Dict[str, int]:
    """Return a mapping of sequence name to length from the .fai file."""
    fai_path = Path(f"{db}.fai")
    if fai_path.exists():
        return {name: data[0] for name, data in parse_fai(fai_path).items()}

    # Fallback: use samtools idxstats if no .fai is directly readable.
    cmd = [samtools, "idxstats", str(db)]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    lengths: Dict[str, int] = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0] != "*":
            lengths[parts[0]] = int(parts[1])
    return lengths
