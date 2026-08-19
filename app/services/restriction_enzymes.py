"""Curated restriction enzyme library for CAPS/dCAPS primer design.

Each entry: (name, recognition_sequence, (cut_left, cut_right), common).

- recognition: IUPAC ambiguity codes allowed (R/Y/S/W/K/M/B/D/H/V/N).
- cut offsets are 0-based positions within the recognition sequence:
  the top strand is cut between bases (cut_left-1, cut_left), the bottom
  strand between (cut_right-1, cut_right). Examples:
      EcoRI  G|AATTC            -> (1, 5)   5' overhang
      KpnI   GGTAC|C            -> (5, 1)   3' overhang
      SmaI   CCC|GGG            -> (3, 3)   blunt
      BsaI   GGTCTC(N)1/5       -> (7, 11)  Type IIS, cut outside recognition
- common=True marks cheap/ubiquitous enzymes shown first in the frontend.

Curated from the NEB catalog's most-used set plus plant-genotyping
staples; the list is intentionally high-confidence (accuracy over
completeness) and easy to extend.
"""

RESTRICTION_ENZYMES: list[dict] = [
    # --- 4-cutters (frequent cutters, cheap) ---
    {"name": "AluI",     "recognition": "AGCT",   "cut": (1, 3), "common": True},
    {"name": "HaeIII",   "recognition": "GGCC",   "cut": (2, 2), "common": True},
    {"name": "MspI",     "recognition": "CCGG",   "cut": (1, 1), "common": True},
    {"name": "HpaII",    "recognition": "CCGG",   "cut": (1, 1), "common": True},
    {"name": "TaqI",     "recognition": "TCGA",   "cut": (1, 1), "common": True},
    {"name": "MboI",     "recognition": "GATC",   "cut": (0, 0), "common": True},
    {"name": "Sau3AI",   "recognition": "GATC",   "cut": (0, 0), "common": False},
    {"name": "NlaIII",   "recognition": "CATG",   "cut": (2, 2), "common": True},
    {"name": "MseI",     "recognition": "TTAA",   "cut": (1, 1), "common": True},
    {"name": "BfaI",     "recognition": "CTAG",   "cut": (1, 1), "common": True},
    {"name": "CviQI",    "recognition": "GTAC",   "cut": (1, 1), "common": False},
    {"name": "MluCI",    "recognition": "AATT",   "cut": (0, 0), "common": False},
    {"name": "Tsp509I",  "recognition": "AATT",   "cut": (0, 0), "common": False},
    {"name": "BstUI",    "recognition": "CGCG",   "cut": (2, 2), "common": False},
    {"name": "RsaI",     "recognition": "GTAC",   "cut": (2, 2), "common": True},
    {"name": "DdeI",     "recognition": "CTNAG",  "cut": (1, 1), "common": False},
    {"name": "HinfI",    "recognition": "GANTC",  "cut": (1, 1), "common": False},
    {"name": "ScrFI",    "recognition": "CCNGG",  "cut": (2, 2), "common": False},
    {"name": "BsaJI",    "recognition": "CCNNGG", "cut": (2, 2), "common": False},
    {"name": "BstNI",    "recognition": "CCWGG",  "cut": (2, 3), "common": True},
    {"name": "Fnu4HI",   "recognition": "GCNGC",  "cut": (2, 2), "common": False},
    {"name": "HpyCH4III","recognition": "ACNGT",  "cut": (3, 1), "common": False},
    {"name": "Hpy188I",  "recognition": "TCNGA",  "cut": (3, 1), "common": False},
    {"name": "HpyCH4IV", "recognition": "ACGT",   "cut": (1, 1), "common": False},
    {"name": "HpyCH4V",  "recognition": "TGCA",   "cut": (1, 1), "common": False},
    {"name": "AciI",     "recognition": "CCGC",   "cut": (1, 3), "common": False},
    {"name": "BsaWI",    "recognition": "WCCGGW", "cut": (5, 1), "common": False},
    {"name": "PspGI",    "recognition": "CCWGG",  "cut": (1, 5), "common": False},
    # --- classic 6-cutters, 5' overhang ---
    {"name": "EcoRI",    "recognition": "GAATTC", "cut": (1, 5), "common": True},
    {"name": "HindIII",  "recognition": "AAGCTT", "cut": (1, 5), "common": True},
    {"name": "BamHI",    "recognition": "GGATCC", "cut": (1, 5), "common": True},
    {"name": "BglII",    "recognition": "AGATCT", "cut": (1, 5), "common": True},
    {"name": "XbaI",     "recognition": "TCTAGA", "cut": (1, 5), "common": True},
    {"name": "XhoI",     "recognition": "CTCGAG", "cut": (1, 5), "common": True},
    {"name": "SalI",     "recognition": "GTCGAC", "cut": (1, 5), "common": True},
    {"name": "NcoI",     "recognition": "CCATGG", "cut": (1, 5), "common": True},
    {"name": "MfeI",     "recognition": "CAATTG", "cut": (1, 5), "common": False},
    {"name": "MluI",     "recognition": "ACGCGT", "cut": (1, 5), "common": False},
    {"name": "BssHII",   "recognition": "GCGCGC", "cut": (1, 5), "common": False},
    {"name": "AgeI",     "recognition": "ACCGGT", "cut": (1, 5), "common": False},
    {"name": "SpeI",     "recognition": "ACTAGT", "cut": (1, 5), "common": True},
    {"name": "NheI",     "recognition": "GCTAGC", "cut": (1, 5), "common": True},
    {"name": "AvrII",    "recognition": "CCTAGG", "cut": (1, 5), "common": False},
    {"name": "EagI",     "recognition": "CGGCCG", "cut": (1, 5), "common": False},
    {"name": "XmaI",     "recognition": "CCCGGG", "cut": (1, 5), "common": True},
    {"name": "BsrGI",    "recognition": "TGTACA", "cut": (1, 5), "common": False},
    {"name": "BspEI",    "recognition": "TCCGGA", "cut": (1, 5), "common": False},
    {"name": "BspHI",    "recognition": "TCATGA", "cut": (1, 5), "common": False},
    {"name": "PciI",     "recognition": "ACATGT", "cut": (1, 5), "common": False},
    {"name": "AflII",    "recognition": "CTTAAG", "cut": (1, 5), "common": False},
    {"name": "PspOMI",   "recognition": "GGGCCC", "cut": (1, 5), "common": False},
    {"name": "PvuI",     "recognition": "CGATCG", "cut": (4, 2), "common": False},
    {"name": "SacII",    "recognition": "CCGCGG", "cut": (4, 2), "common": True},
    {"name": "ApaLI",    "recognition": "GTGCAC", "cut": (1, 5), "common": False},
    {"name": "BmtI",     "recognition": "GCTAGC", "cut": (1, 5), "common": False},
    {"name": "PaeR7I",   "recognition": "CTCGAG", "cut": (1, 5), "common": False},
    # --- classic 6-cutters, 3' overhang ---
    {"name": "PstI",     "recognition": "CTGCAG", "cut": (5, 1), "common": True},
    {"name": "SphI",     "recognition": "GCATGC", "cut": (5, 1), "common": False},
    {"name": "KpnI",     "recognition": "GGTACC", "cut": (5, 1), "common": True},
    {"name": "Acc65I",   "recognition": "GGTACC", "cut": (1, 5), "common": False},
    {"name": "SacI",     "recognition": "GAGCTC", "cut": (5, 1), "common": True},
    {"name": "Eco53kI",  "recognition": "GAGCTC", "cut": (3, 3), "common": False},
    {"name": "ApaI",     "recognition": "GGGCCC", "cut": (5, 1), "common": True},
    {"name": "AatII",    "recognition": "GACGTC", "cut": (5, 1), "common": False},
    {"name": "NsiI",     "recognition": "ATGCAT", "cut": (5, 1), "common": False},
    {"name": "BanII",    "recognition": "GRGCYC", "cut": (5, 1), "common": False},
    {"name": "HaeII",    "recognition": "RGCGCY", "cut": (5, 1), "common": False},
    {"name": "Bsu36I",   "recognition": "CCTNAGG", "cut": (2, 4), "common": False},
    {"name": "EaeI",     "recognition": "YGGCCR", "cut": (1, 5), "common": False},
    # --- classic 6-cutters, blunt ---
    {"name": "EcoRV",    "recognition": "GATATC", "cut": (3, 3), "common": True},
    {"name": "PvuII",    "recognition": "CAGCTG", "cut": (3, 3), "common": False},
    {"name": "SmaI",     "recognition": "CCCGGG", "cut": (3, 3), "common": True},
    {"name": "StuI",     "recognition": "AGGCCT", "cut": (3, 3), "common": False},
    {"name": "DraI",     "recognition": "TTTAAA", "cut": (3, 3), "common": True},
    {"name": "HpaI",     "recognition": "GTTAAC", "cut": (3, 3), "common": False},
    {"name": "SspI",     "recognition": "AATATT", "cut": (3, 3), "common": False},
    {"name": "ScaI",     "recognition": "AGTACT", "cut": (3, 3), "common": True},
    {"name": "SnaBI",    "recognition": "TACGTA", "cut": (3, 3), "common": False},
    {"name": "PsiI",     "recognition": "TTATAA", "cut": (3, 3), "common": False},
    {"name": "NruI",     "recognition": "TCGCGA", "cut": (3, 3), "common": False},
    {"name": "MscI",     "recognition": "TGGCCA", "cut": (3, 3), "common": False},
    {"name": "PmlI",     "recognition": "CACGTG", "cut": (3, 3), "common": False},
    {"name": "FspI",     "recognition": "TGCGCA", "cut": (3, 3), "common": False},
    {"name": "BsaAI",    "recognition": "YACGTR", "cut": (3, 3), "common": False},
    {"name": "BsaBI",    "recognition": "GATNNNNATC", "cut": (5, 5), "common": False},
    {"name": "XmnI",     "recognition": "GAANNNNTTC", "cut": (5, 5), "common": False},
    # --- 2/4 overhang 6-cutters ---
    {"name": "NdeI",     "recognition": "CATATG", "cut": (2, 4), "common": True},
    {"name": "ClaI",     "recognition": "ATCGAT", "cut": (2, 4), "common": False},
    {"name": "BstBI",    "recognition": "TTCGAA", "cut": (2, 4), "common": False},
    {"name": "BspDI",    "recognition": "ATCGAT", "cut": (2, 4), "common": False},
    {"name": "AccI",     "recognition": "GTMKAC", "cut": (2, 4), "common": False},
    {"name": "HincII",   "recognition": "GTYRAC", "cut": (3, 3), "common": False},
    # --- degenerate / flexible ---
    {"name": "ApoI",     "recognition": "RAATTY", "cut": (1, 5), "common": True},
    {"name": "StyI",     "recognition": "CCWWGG", "cut": (1, 5), "common": False},
    {"name": "EcoO109I", "recognition": "RGGNCCY", "cut": (2, 4), "common": False},
    {"name": "SgrAI",    "recognition": "CRCCGGYG", "cut": (5, 3), "common": False},
    {"name": "RsrII",    "recognition": "CGGWCCG", "cut": (2, 6), "common": False},
    {"name": "BstXI",    "recognition": "CCANNNNNNTGG", "cut": (8, 4), "common": False},
    {"name": "XcmI",     "recognition": "CCANNNNNNNNNTGG", "cut": (11, 4), "common": False},
    {"name": "SfiI",     "recognition": "GGCCNNNNNGGCC", "cut": (8, 4), "common": False},
    {"name": "AhdI",     "recognition": "GACNNNNGTC", "cut": (6, 3), "common": False},
    {"name": "PshAI",    "recognition": "GACNNNNGTC", "cut": (6, 3), "common": False},
    # --- 8-cutters (rare cutters) ---
    {"name": "NotI",     "recognition": "GCGGCCGC", "cut": (2, 6), "common": True},
    {"name": "AscI",     "recognition": "GGCGCGCC", "cut": (2, 6), "common": True},
    {"name": "PacI",     "recognition": "TTAATTAA", "cut": (5, 3), "common": True},
    {"name": "PmeI",     "recognition": "GTTTAAAC", "cut": (4, 4), "common": True},
    {"name": "SwaI",     "recognition": "ATTTAAAT", "cut": (4, 4), "common": True},
    {"name": "FseI",     "recognition": "GGCCGGCC", "cut": (6, 6), "common": False},
    {"name": "AsiSI",    "recognition": "GCGATCGC", "cut": (5, 3), "common": False},
    {"name": "SbfI",     "recognition": "CCTGCAGG", "cut": (6, 2), "common": True},
    {"name": "SdaI",     "recognition": "CCTGCAGG", "cut": (6, 2), "common": False},
    {"name": "SrfI",     "recognition": "GCCCGGGC", "cut": (4, 4), "common": False},
    {"name": "SgsI",     "recognition": "GGCGCGCC", "cut": (2, 6), "common": False},
    # --- Type IIS (cut outside recognition; Golden Gate staples) ---
    {"name": "BsaI",     "recognition": "GGTCTC", "cut": (7, 11), "common": True},
    {"name": "BsmBI",    "recognition": "CGTCTC", "cut": (7, 11), "common": True},
    {"name": "Esp3I",    "recognition": "CGTCTC", "cut": (7, 11), "common": False},
    {"name": "BbsI",     "recognition": "GAAGAC", "cut": (8, 12), "common": True},
    {"name": "BsaXI",    "recognition": "ACNNNNNCTCC", "cut": (10, 15), "common": False},
    {"name": "SapI",     "recognition": "GCTCTTC", "cut": (7, 12), "common": False},
    {"name": "BspQI",    "recognition": "GCTCTTC", "cut": (7, 12), "common": False},
    {"name": "FokI",     "recognition": "GGATG", "cut": (9, 13), "common": False},
    {"name": "BspMI",    "recognition": "ACCTGC", "cut": (4, 8), "common": False},
    {"name": "BtgZI",    "recognition": "GCGATG", "cut": (10, 14), "common": False},
    {"name": "BccI",     "recognition": "CCATC", "cut": (4, 5), "common": False},
]

ENZYME_BY_NAME: dict[str, dict] = {e["name"]: e for e in RESTRICTION_ENZYMES}
