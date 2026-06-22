"""Input validation helpers and table allowlists derived from legacy CGI scripts."""

from __future__ import annotations

import re
from typing import Iterable

from .exceptions import ValidationFailure

EXPRESSION_PROJECTS: dict[str, dict[str, object]] = {
    "PRJEB25639_tbl": {"description": "BCS cv-1 Development"},
    "PRJEB5314_paired_tbl": {"description": "Chinese Spring cv-1 Development (pair)"},
    "PRJEB5314_single_tbl": {"description": "Chinese Spring cv-1 Development (single)"},
    "PRJEB5135_tbl": {"description": "Developing wheat grain"},
    "PRJNA485741_tbl": {"description": "Expression of embryo and endosperm in developing grain"},
    "PRJEB7795_tbl": {"description": "Tissue layers from developing wheat grain at 12 DPA"},
    "PRJEB5029_tbl": {"description": "Meiosis data"},
    "PRJNA297977_tbl": {"description": "Microspore embryogenesis induction"},
    "PRJNA325489_tbl": {"description": "Early wheat spike development"},
    "PRJEB24686_tbl": {"description": "Fusarium head blight 2DL"},
    "PRJNA327013_tbl": {"description": "Zymoseptoria tritici isolates"},
    "PRJNA263755_tbl": {"description": "Fusarium crown rot"},
    "PRJEB12358_tbl": {"description": "FHB-resistance QTL Fhb1 and Qfhs.ifa-5A"},
    "PRJNA273659_tbl": {"description": "Fhb1 plus/minus DON and infection"},
    "PRJNA297822_tbl": {"description": "Fusarium pseudograminearum infected wheat"},
    "PRJNA307989_tbl": {"description": "F. graminearum infection on Fielder"},
    "PRJEB21835_tbl": {"description": "Xanthomonas translucens infection"},
    "PRJEB21874_tbl": {"description": "Mycorrhizal fungi interaction"},
    "PRJNA327829_tbl": {"description": "Pyrenophora tritici-repentis inoculation"},
    "PRJEB23056_tbl": {"description": "Elicitation with PAMPs"},
    "PRJNA243835_powdery_tbl": {"description": "Powdery mildew pathogen stress"},
    "PRJEB8798_tbl": {"description": "Zymoseptoria tritici time course"},
    "PRJNA243835_stripe_tbl": {"description": "Stripe rust pathogen stress"},
    "PRJEB13569_tbl": {"description": "Field Pathogenomics of Wheat Blast"},
    "PRJNA307228_tbl": {"description": "Stripe rust stress in Xingzi 9104"},
    "PRJNA325136_tbl": {"description": "Stem rust resistance locus on 7AL"},
    "PRJNA328385_tbl": {"description": "Lr57 NIL interactions"},
    "PRJDB2496_tbl": {"description": "Phosphate starvation"},
    "PRJEB8762_tbl": {"description": "Temperature treatment"},
    "PRJNA253535_tbl": {"description": "Low temperature response"},
    "PRJNA257938_tbl": {"description": "Drought and heat stress"},
    "PRJNA358808_tbl": {"description": "Combined drought and heat stress"},
    "PRJNA171754_tbl": {"description": "Heat stress tolerant vs susceptible cultivar"},
    "PRJNA427246_tbl": {"description": "Heat stress responsive transcriptomes"},
    "PRJNA293629_tbl": {"description": "Salt stress transcriptome"},
    "PRJNA487923_tbl": {"description": "Salt stress root transcriptome"},
    "PRJNA306536_tbl": {"description": "PEG6000 treatment"},
    "Wangmeng_NR_tbl": {"description": "Nitrogen treatment"},
    "PRJNA362497_tbl": {"description": "Chlorophyll-deficient mutant"},
    "PRJNA322418_tbl": {"description": "Gene imprinting analysis"},
    "PRJEB25586_tbl": {"description": "Early meiosis with or without Ph1"},
    "PRJNA353130_tbl": {"description": "miR9678 function in wheat"},
    "DMSO_GA_JA_tpm_mean_tbl": {"description": "Fielder leaf treated 1h with DMSO, GA and JA"},
    "ABA_JA_6BA_DMSO3h_mean_tbl": {"description": "Fielder leaf treated 3h with DMSO, ABA, 6-BA and SA"},
    "PRJNA396738_tbl": {"description": "Major grain weight QTL on 5AL"},
    "PRJNA341486_tbl": {"description": "Wax production regulators"},
    "PRJNA348655_tbl": {"description": "Regulators of wheat grain production"},
    "PRJNA471426_tbl": {"description": "Increased grain size mutant"},
    "PRJEB22854_tbl": {"description": "Purple-grain wheat pericarp RNA-seq"},
    "PRJNA307237_tbl": {"description": "Flag leaf senescence"},
    "PRJNA477934_tbl": {"description": "Tetraploid, hexaploid and reciprocal endosperm"},
    "PRJEB51827_tbl": {"description": "Population transcriptome"},
    "PRJNA1037698_tbl": {"description": "Wild emmer stripe rust response"},
    "PRJNA613349_tbl": {"description": "Stripe rust response on wheat"},
    "barley_development_PRJEB14349_tbl": {"description": "Barley development"},
    "miRNA_mature_tissue_tbl": {"description": "miRNA mature tissue expression"},
    "rye_cold_tbl": {"description": "Rye cold stress"},
    "rye_development_tbl": {"description": "Rye development"},
    "rye_drought_tbl": {"description": "Rye drought stress"},
    "ERP022006_tbl": {"description": "Wild emmer expression"},
    "kat2_tpm_mean_tbl": {"description": "Wild emmer KAT2"},
    "SRP072147_tbl": {"description": "Triticum urartu expression"},
    "SRP104243_tbl": {"description": "Triticum urartu stress expression"},
}

COEXPRESSION_TABLES = {
    "CO_result2": "Wheat grain",
    "CO_PRJEB25639": "Wheat multiple tissues",
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

PPI_TABLES = {"PPI_result"}
SYNTENY_TABLES = {"CSsymaptbl"}
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
REGION_PATTERN = re.compile(r"^[A-Za-z0-9_.]+:\d+(?:-|\.\.)\d+$")


def ensure_allowed_table(table_name: str, allowlist: Iterable[str], label: str = "table") -> str:
    """Validate that a user-selected table is explicitly allowed."""

    if table_name not in set(allowlist):
        raise ValidationFailure(f"Unsupported {label}: {table_name}")
    return table_name


def ensure_gene_like(value: str, label: str = "gene_id") -> str:
    """Validate gene-like identifiers and interval-like tokens."""

    if not value or not GENE_ID_PATTERN.match(value):
        raise ValidationFailure(f"Invalid {label}: {value}")
    return value


def ensure_interval_like(value: str) -> str:
    """Validate interval string used by legacy CGI input."""

    if not REGION_PATTERN.match(value):
        raise ValidationFailure(
            "Invalid region format. Expected e.g. Chr1A_Abo:200-500 or chr1A:10-100. See https://wheatomics.sdau.edu.cn/doc/getsequence_search.txt"
        )
    return value
