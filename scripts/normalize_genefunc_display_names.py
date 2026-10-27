#!/usr/bin/env python3
"""Normalize Genefuncdb.Genefunc_registry.display_name for the getfasta chips.

The getfasta "Supported genomes" chips render ``display_name``; for most rows it
was copied from the internal dataset id (``AABBDD_Chinese_Spring1_0``), which is
not how a human writes a cultivar name. This script rewrites those ids into
readable labels while leaving hand-curated names untouched.

Rules (applied in order)
------------------------
1. Skip rows whose display_name is already curated (anything that is not the
   dataset-id form).
2. Strip the ``Genefunc_`` prefix / ``_table`` suffix, then the leading ploidy
   token (``AABBDD_``, ``AABB_``, ``HH_`` …) or a species-name polyploidy.
3. Underscores become spaces; version suffixes collapse into dotted versions
   (``PGSBv2_1`` -> ``PGSBv2.1``, ``Chinese_Spring1_0`` -> ``Chinese Spring 1.0``).
4. Tokens that are established codes stay uppercase (``AK58``, ``AMN``,
   ``CS-IAAS``, ``PGSBv2.1``); other tokens get Title Case.
5. ``EXPLICIT`` overrides win last (see below).

Usage
-----
    python3 scripts/normalize_genefunc_display_names.py --dry-run
    python3 scripts/normalize_genefunc_display_names.py --apply
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

EXPLICIT = {
    # cultivar / assembly names whose id form would be mangled by the generic rules
    "AABBDD_Chinese_Spring1_0": "Chinese Spring 1.0",
    "AABBDD_Chinese_Spring2_1": "Chinese Spring 2.1",
    "AABBDD_Chinese_Spring_Triticum_4_0": "Chinese Spring (Triticum 4.0)",
    "AABBDD_CS_IAAS": "CS-IAAS",
    "AABBDD_CS_CAU": "CS-CAU",
    "AABBDD_Cadenza_scaffold": "Cadenza (scaffold assembly)",
    "AABBDD_Claire_scaffold": "Claire (scaffold assembly)",
    "AABBDD_Paragon_scaffolds": "Paragon (scaffold assembly)",
    "AABBDD_Robigus_scaffolds": "Robigus (scaffold assembly)",
    "AABBDD_Weebill_scaffolds": "Weebill (scaffold assembly)",
    "AABBDD_arinalrfor_PGSBv2_1": "Arinalrfor (PGSBv2.1)",
    "AABBDD_jagger_PGSBv2_1": "Jagger (PGSBv2.1)",
    "AABBDD_lancer_PGSBv2_1": "Lancer (PGSBv2.1)",
    "AABBDD_landmark_PGSBv2_1": "Landmark (PGSBv2.1)",
    "AABBDD_mattis_PGSBv2_1": "Mattis (PGSBv2.1)",
    "AABBDD_spelta_PGSBv2_0": "Spelta (PGSBv2.0)",
    "AABBDD_spelta_PGSBv2_1": "Spelta (PGSBv2.1)",
    "AABBDD_TGACv1": "TGACv1",
    "AABB_Durum_Wheat": "Durum wheat",
    "AABB_Durum_Wheat_Langdon": "Durum wheat Langdon",
    "AABB_Durum_Wheat_Svevo": "Durum wheat Svevo",
    "AABB_durum_PI192051": "Durum PI192051",
    "AABB_Wild_emmer": "Wild emmer v1.0",
    "AABB_Wild_emmerV2": "Wild emmer v2.0",
    "AABB_Zavitan": "Zavitan (pangenome)",
    "Wild_emmer": "Wild emmer v1.0",
    "Wild_emmerV2": "Wild emmer v2.0",
    "Wild_emmer_Zavitan": "Zavitan (near-complete, 2026)",
    "Durum_Wheat": "Durum wheat",
    "Durum_Wheat_Langdon": "Durum wheat Langdon",
    "Durum_Wheat_Langdon_clean": "Durum wheat Langdon",
    "Durum_Wheat_Svevo": "Durum wheat Svevo",
    "durum_PI192051": "Durum PI192051",
    "Durum_PI192051": "Durum PI192051",
    "CS_CNAU": "CS-CNAU",
    "ArinaLrFor_PGSBv2": "Arinalrfor (PGSBv2)",
    "sharonensis_AS_1644": "Ae. sharonensis AS1644",
    "ae_longissima_TAEG67822": "Ae. longissima TAEG67822",
    "ae_longissima_AEG_6782_2": "Ae. longissima AEG-6782-2",
    "ae_speltoides_AEG_9674_1": "Ae. speltoides AEG-9674-1",
    "AeComosa_PI551049": "Ae. comosa PI551049",
    "Ae_Comosa_PI551049": "Ae. comosa PI551049",
    "Ae_tauschii_Aet6_clean_dedup": "Ae. tauschii Aet6",
    "Aegilops_tauschii_Aet6": "Ae. tauschii Aet6",
    "tauschii_Aet5": "Ae. tauschii Aet5",
    "tauschii_Luo": "Ae. tauschii Luo",
}

# Species epithets stay lowercase (botanical convention).
SPECIES_EPITHETS = {
    "aestivum", "turgidum", "durum", "dicoccoides", "dicoccum", "monococcum",
    "urartu", "timopheevii", "spelta", "tauschii", "ponticum", "longissima",
    "sharonensis", "speltoides", "bicornis", "searsii", "umbellulata", "comosa",
    "mutica", "geniculata", "ventricosa", "nutans", "sibiricus", "villosum",
    "kamojii", "kamoji", "weining", "bulbosum", "erectifolium", "chinensis",
    "intermedium", "elongatum", "cereale", "vulgare", "spontaneum",
}
# Common nouns that should stay lowercase in a display label.
COMMON_NOUNS = {"cv.", "cv", "wheat", "emmer", "rye", "barley", "triticale",
                "scaffold", "scaffolds", "assembly", "genome", "pangenome"}
# Leading ploidy/karyotype tokens used when Polyploidy is NULL.
PLOIDY_PREFIXES = (
    "AABBDD", "AABBRR", "AABB", "AAGG", "DDNN", "ATATGG", "NSNSXMXM", "STSTYYHH",
    "STSTVVJJ", "HHHH", "AA", "DD", "HH", "SS", "MM", "RR", "UU", "VV", "EE", "TT",
    "PP", "GG",
)

# Tokens (case-insensitive match) that should stay uppercase / as written.
# Rows that are junk / placeholders and must not be renamed.
SKIP_TABLES = {"Genefunc_table"}

KEEP_TOKENS = {
    "AK58", "AMN", "BJ8", "CM42", "JM22", "JM44", "JM47", "JIN50", "KF11",
    "MACE", "MZM", "NC4", "NC99BGTAG11", "RGT", "SUMAI3", "SY", "TA", "TG",
    "CWI86942", "HD6172", "KN9204", "S4185", "XN6028", "XY6", "YM33", "YM158",
    "ZM16", "ZM22", "ZM366", "CS-IAAS", "CS-CAU", "T2T", "NCBI",
    "PGSBv2.1", "PGSBv2.0", "TGACv1", "IWGSC", "CS", "PI", "CItr", "NU", "IG",
    "WBDC", "HOR", "FT", "ZDM", "AEG", "TB01", "TH02", "TE01", "TL05", "TS01",
    "AS_1644", "AEG-9674-1",
}


def _db_connect():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.core.config import settings  # noqa: E402
    from app.db.mysql import mysql_cursor  # noqa: E402

    return settings, mysql_cursor


def strip_dataset_id(display_name: str, table_name: str, polyploidy: str | None) -> str:
    """Turn an internal dataset id into the material part (no ploidy prefix)."""
    name = display_name or table_name
    name = re.sub(r"^Genefunc_", "", name)
    name = re.sub(r"_table$", "", name)
    name = re.sub(r"_clean$", "", name)
    if polyploidy and not re.search(r"\s", polyploidy):
        ploid = re.escape(polyploidy)
        name = re.sub(rf"^{ploid}_", "", name, flags=re.I)
    else:
        for ploid in PLOIDY_PREFIXES:
            if name.upper().startswith(ploid + "_"):
                name = name[len(ploid) + 1:]
                break
    return name


def humanize(raw: str) -> str:
    s = re.sub(r"(?<=[0-9])_([0-9]+)(?=$|_)", r".\1", raw)   # PGSBv2_1 -> PGSBv2.1
    s = re.sub(r"_(clean_dedup|clean|dedup)$", "", s)
    s = s.replace("_", " ")
    s = re.sub(r"\s+", " ", s).strip()

    tokens = []
    for tok in s.split():
        low, up = tok.lower(), tok.upper()
        if low in SPECIES_EPITHETS or low in COMMON_NOUNS:
            tokens.append(low)
        elif re.fullmatch(r"v\d+(\.\d+)?", tok, re.I):
            tokens.append("v" + tok[1:])
        elif re.fullmatch(r"PGSBv\d+(\.\d+)?", tok, re.I):
            m = re.match(r"PGSBv(\d+)(?:\.(\d+))?", tok, re.I)
            tokens.append(f"PGSBv{m.group(1)}" + (f".{m.group(2)}" if m.group(2) else ""))
        elif up in {"AE", "AE."}:
            tokens.append("Ae.")
        elif re.fullmatch(r"Ae([A-Z][a-z]+)", tok):            # AeComosa -> Ae. comosa
            tokens.append("Ae. " + tok[2:].lower())
        elif up in KEEP_TOKENS or re.fullmatch(r"[A-Z0-9]{2,}", tok):
            tokens.append(up)
        else:
            tokens.append(tok[:1].upper() + tok[1:])

    label = " ".join(tokens)
    label = re.sub(r" (PGSBv\d+(?:\.\d+)?)$", r" (\1)", label)   # trailing version in parens
    label = re.sub(r"\b(PI|HOR|WBDC|FT|ZDM|HID|TA|AS|NU|IG|XM|CItr) (\d.*)$", r"\1\2", label)
    label = re.sub(r"^(\w)", lambda m: m.group(1).upper(), label)
    return label


def build_label(display_name: str, table_name: str, polyploidy: str | None) -> tuple[str, str]:
    """Return (new_label, reason). reason='curated' means leave untouched."""
    raw_id = re.sub(r"^Genefunc_", "", display_name or table_name)
    raw_id = re.sub(r"_table$", "", raw_id)

    # Already human-written (contains a space and no underscores, e.g.
    # "Wild Ember Zavitan v1.0" / "Durum Wheat cv. Svevo (AABB)") -> keep.
    looks_like_id = ("_" in display_name) or display_name.endswith("table")
    if display_name and not looks_like_id and " " in display_name:
        return display_name, "curated"

    if display_name in EXPLICIT:
        return EXPLICIT[display_name], "explicit"

    material = strip_dataset_id(display_name, table_name, polyploidy)
    if material in EXPLICIT:
        return EXPLICIT[material], "explicit"
    return humanize(material), "rule"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the new labels to MySQL")
    ap.add_argument("--dry-run", action="store_true", help="only print the mapping (default)")
    args = ap.parse_args()
    dry = not args.apply

    settings, mysql_cursor = _db_connect()
    with mysql_cursor(settings.DB_GENEFUNC) as cur:
        cur.execute(
            "SELECT table_name, display_name, Polyploidy FROM Genefunc_registry "
            "ORDER BY Polyploidy, table_name"
        )
        rows = cur.fetchall()

    changes, kept = [], 0
    skipped = 0
    for r in rows:
        if r["table_name"] in SKIP_TABLES:
            skipped += 1
            continue
        old = r["display_name"] or r["table_name"]
        new, reason = build_label(old, r["table_name"], r.get("Polyploidy"))
        if reason == "curated" or new == old:
            kept += 1
            continue
        changes.append((r["table_name"], old, new, r.get("Polyploidy")))

    print(f"total rows      : {len(rows)}")
    print(f"unchanged       : {kept}")
    print(f"skipped (junk)  : {skipped}")
    print(f"to normalize    : {len(changes)}\n")
    for table, old, new, ploidy in changes:
        print(f"  {ploidy or '?':<12} {old:<42} -> {new}")

    if dry:
        print("\n(dry-run: nothing written; re-run with --apply)")
        return 0

    with mysql_cursor(settings.DB_GENEFUNC) as cur:
        for table, _old, new, _p in changes:
            cur.execute(
                "UPDATE Genefunc_registry SET display_name = %s WHERE table_name = %s",
                (new, table),
            )
    print(f"\nupdated {len(changes)} rows in Genefuncdb.Genefunc_registry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
