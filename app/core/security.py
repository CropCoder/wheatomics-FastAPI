"""Input validation helpers and table allowlists derived from legacy CGI scripts."""

from __future__ import annotations

import re
from typing import Iterable

from .exceptions import ValidationFailure


COEXPRESSION_TABLES = {
    "CO_PRJEB25639": "Wheat multiple tissues",
    "CO_BioticStress_2026": "Wheat biotic stress (filter-extracted)",
    "CO_result2": "Wheat grain",
}

GENE_FUNCTION_TABLES = {
    "Genefunc_table": "Functional annotation against IWGSC v1/v2",
    "Genefunc_IWGSC03G_table": "Functional annotation with IWGSC v3 mapping",
    "GenePageIWGSCv1_table": "Gene detail page table",
    "WheatRiceArabidopsis_tbl": "Wheat, rice and Arabidopsis homologs",
    "Triticeae_table": "Triticeae homologs",
}

ID_CONVERSION_TABLES = {
    "MIPS_result",
    "TGACv1_result",
    "IWGSCv1_result",
}

PPI_TABLES: dict[str, str] = {
    "PPI_result": "Wheat PPI CF-MS data",
}
SYNTENY_TABLES = {"CSsymaptbl"}
BLASTP_TABLES: dict[str, str] = {
    "all_protein_blastp": "All protein BLASTP results",
}


PREBLAST_TABLES = {
    "rice_blastp",
    "arabidopsis_blastp",
    "barley_blastp",
    "rye_blastp",
    "tauschii_blastp",
}

FIGURE_FORMATS = {"pdf", "png", "svg"}
SYNTENY_STYLE_VALUES = {"line", "curve"}
SYNTENY_SHADE_STYLES = {"curve", "line"}

GENE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")
REGION_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+:\d+(?:-|\.\.)\d+$")


def ensure_allowed_table(table_name: str, allowlist: Iterable[str], label: str = "table") -> str:
    """Validate that a user-selected table is explicitly allowed."""

    if table_name not in set(allowlist):
        raise ValidationFailure(f"Unsupported {label}: {table_name}")
    return table_name


def ensure_gene_like(value: str, label: str = "gene_id") -> str:
    """Validate gene-like identifiers and interval-like tokens."""

    if not value or not GENE_ID_PATTERN.match(value):
        raise ValidationFailure(
            f"Invalid {label}: {value!r}.\n"
            "Wheat gene IDs follow patterns like:\n"
            "  - TraesCS5A02G391700          (IWGSC v1.1 / 02G, no version suffix)\n"
            "  - TraesCS5A02G391700.1        (with transcript version)\n"
            "  - TraesCS5A03G1158600         (IWGSC v3 / 03G)\n"
            "  - Abo1A000100.1               (Abbondanza)\n"
            "If you typed a region (chr:start-end) instead, use the "
            "/api/sequence/by-interval endpoint."
        )
    return value


def ensure_interval_like(value: str) -> str:
    """Validate interval string used by legacy CGI input."""

    if not REGION_PATTERN.match(value):
        raise ValidationFailure(
            f"Invalid region format: {value!r}.\n"
            "Expected: <chromosome>:<start>-<end>, e.g.\n"
            "  - Chr1A_Abo:200-500                 (Abbondanza)\n"
            "  - chr1A:200-500                     (Chinese Spring, no suffix)\n"
            "  - Chr1A_Chinese_Spring1.0:200-500   (Chinese Spring v1.0)\n"
            "  - chr1H_Barley3:200-500             (Barley v3)\n"
            "Note: there is NO 'Chinese_Spring_v1.0' (with a 'v') database — "
            "use 'Chinese_Spring1.0' (no 'v').\n"
            "Full chromosome-name reference: https://wheatomics.sdau.edu.cn/doc/getsequence_search.txt"
        )
    return value
