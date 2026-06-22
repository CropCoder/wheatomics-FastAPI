"""Nearest-neighbor thermodynamics for primer Tm calculation.

This module is a Python port of the thermodynamic logic embedded in the
original PrimerServer Perl scripts (``_run_specificity_check.pl`` and
``function_Tm.pl``).  It uses the SantaLucia & Hicks (2004) nearest-neighbor
model with terminal and internal mismatch tables from Allawi & SantaLucia.
"""

import math
from typing import Dict, Tuple

# dH (kcal/mol) and dS (eu) coefficients.
# SantaLucia & Hicks (2004), Annu. Rev. Biophys. Biomol. Struct 33: 415-440
DNA_NN_TABLE: Dict[str, Tuple[float, float]] = {
    "init": (0.2, -5.7),
    "init_A/T": (2.2, 6.9),
    "init_G/C": (0.0, 0.0),
    "init_oneG/C": (0.0, 0.0),
    "init_allA/T": (0.0, 0.0),
    "init_5T/A": (0.0, 0.0),
    "sym": (0.0, -1.4),
    "AA/TT": (-7.6, -21.3),
    "AT/TA": (-7.2, -20.4),
    "TA/AT": (-7.2, -20.4),
    "CA/GT": (-8.5, -22.7),
    "GT/CA": (-8.4, -22.4),
    "CT/GA": (-7.8, -21.0),
    "GA/CT": (-8.2, -22.2),
    "CG/GC": (-10.6, -27.2),
    "GC/CG": (-9.8, -24.4),
    "GG/CC": (-8.0, -19.0),
}

# Internal mismatch and inosine table (DNA).
# Allawi & SantaLucia (1997-1998), Peyret et al. (1999)
DNA_IMM_TABLE: Dict[str, Tuple[float, float]] = {
    "AG/TT": (1.0, 0.9),
    "AT/TG": (-2.5, -8.3),
    "CG/GT": (-4.1, -11.7),
    "CT/GG": (-2.8, -8.0),
    "GG/CT": (3.3, 10.4),
    "GG/TT": (5.8, 16.3),
    "GT/CG": (-4.4, -12.3),
    "GT/TG": (4.1, 9.5),
    "TG/AT": (-0.1, -1.7),
    "TG/GT": (-1.4, -6.2),
    "TT/AG": (-1.3, -5.3),
    "AA/TG": (-0.6, -2.3),
    "AG/TA": (-0.7, -2.3),
    "CA/GG": (-0.7, -2.3),
    "CG/GA": (-4.0, -13.2),
    "GA/CG": (-0.6, -1.0),
    "GG/CA": (0.5, 3.2),
    "TA/AG": (0.7, 0.7),
    "TG/AA": (3.0, 7.4),
    "AC/TT": (0.7, 0.2),
    "AT/TC": (-1.2, -6.2),
    "CC/GT": (-0.8, -4.5),
    "CT/GC": (-1.5, -6.1),
    "GC/CT": (2.3, 5.4),
    "GT/CC": (5.2, 13.5),
    "TC/AT": (1.2, 0.7),
    "TT/AC": (1.0, 0.7),
    "AA/TC": (2.3, 4.6),
    "AC/TA": (5.3, 14.6),
    "CA/GC": (1.9, 3.7),
    "CC/GA": (0.6, -0.6),
    "GA/CC": (5.2, 14.2),
    "GC/CA": (-0.7, -3.8),
    "TA/AC": (3.4, 8.0),
    "TC/AA": (7.6, 20.2),
    "AA/TA": (1.2, 1.7),
    "CA/GA": (-0.9, -4.2),
    "GA/CA": (-2.9, -9.8),
    "TA/AA": (4.7, 12.9),
    "AC/TC": (0.0, -4.4),
    "CC/GC": (-1.5, -7.2),
    "GC/CC": (3.6, 8.9),
    "TC/AC": (6.1, 16.4),
    "AG/TG": (-3.1, -9.5),
    "CG/GG": (-4.9, -15.3),
    "GG/CG": (-6.0, -15.8),
    "TG/AG": (1.6, 3.6),
    "AT/TT": (-2.7, -10.8),
    "CT/GT": (-5.0, -15.8),
    "GT/CT": (-2.2, -8.4),
    "TT/AT": (0.2, -1.5),
}

# Terminal mismatch table (DNA).
# SantaLucia & Peyret (2001) Patent Application WO 01/94611
DNA_TMM_TABLE: Dict[str, Tuple[float, float]] = {
    "AA/TA": (-3.1, -7.8),
    "TA/AA": (-2.5, -6.3),
    "CA/GA": (-4.3, -10.7),
    "GA/CA": (-8.0, -22.5),
    "AC/TC": (-0.1, 0.5),
    "TC/AC": (-0.7, -1.3),
    "CC/GC": (-2.1, -5.1),
    "GC/CC": (-3.9, -10.6),
    "AG/TG": (-1.1, -2.1),
    "TG/AG": (-1.1, -2.7),
    "CG/GG": (-3.8, -9.5),
    "GG/CG": (-0.7, -19.2),
    "AT/TT": (-2.4, -6.5),
    "TT/AT": (-3.2, -8.9),
    "CT/GT": (-6.1, -16.9),
    "GT/CT": (-7.4, -21.2),
    "AA/TC": (-1.6, -4.0),
    "AC/TA": (-1.8, -3.8),
    "CA/GC": (-2.6, -5.9),
    "CC/GA": (-2.7, -6.0),
    "GA/CC": (-5.0, -13.8),
    "GC/CA": (-3.2, -7.1),
    "TA/AC": (-2.3, -5.9),
    "TC/AA": (-2.7, -7.0),
    "AC/TT": (-0.9, -1.7),
    "AT/TC": (-2.3, -6.3),
    "CC/GT": (-3.2, -8.0),
    "CT/GC": (-3.9, -10.6),
    "GC/CT": (-4.9, -13.5),
    "GT/CC": (-3.0, -7.8),
    "TC/AT": (-2.5, -6.3),
    "TT/AC": (-0.7, -1.2),
    "AA/TG": (-1.9, -4.4),
    "AG/TA": (-2.5, -5.9),
    "CA/GG": (-3.9, -9.6),
    "CG/GA": (-6.0, -15.5),
    "GA/CG": (-4.3, -11.1),
    "GG/CA": (-4.6, -11.4),
    "TA/AG": (-2.0, -4.7),
    "TG/AA": (-2.4, -5.8),
    "AG/TT": (-3.2, -8.7),
    "AT/TG": (-3.5, -9.4),
    "CG/GT": (-3.8, -9.0),
    "CT/GG": (-6.6, -18.7),
    "GG/CT": (-5.7, -15.9),
    "GT/CG": (-5.9, -16.1),
    "TG/AT": (-3.9, -10.5),
    "TT/AG": (-3.6, -9.8),
}


def complement(seq: str) -> str:
    """Return the complement (not reverse) of a DNA sequence."""
    table = str.maketrans("ACGT", "TGCA")
    return seq.upper().translate(table)


def reverse_complement(seq: str) -> str:
    """Return the reverse-complement of a DNA sequence."""
    return complement(seq)[::-1]


def ion_correction(
    Na: float,
    K: float,
    Tris: float,
    Mg: float,
    dNTPs: float,
    seq_len: int,
) -> float:
    """Calculate the entropy correction factor due to salt concentration.

    Reference: von Ahsen et al. (2001, Clin Chem 47: 1956-1961)
    [Na_eq] = [Na+] + [K+] + [Tris]/2 + 120*sqrt([Mg2+] - [dNTPs])
    If [dNTPs] >= [Mg2+]: [Na_eq] = [Na+] + [K+] + [Tris]/2
    """
    if dNTPs >= Mg:
        na_eq_mmol = Na + K + (Tris / 2)
    else:
        na_eq_mmol = Na + K + (Tris / 2) + 120 * math.sqrt(Mg - dNTPs)
    na_eq_mol = na_eq_mmol / 1000.0
    return 0.368 * (seq_len - 1) * math.log(na_eq_mol)


def _reverse_nn(nn: str) -> str:
    """Reverse a nearest-neighbor key like 'AA/TT' -> 'TT/AA'.

    This matches Perl's scalar reverse on the full string.
    """
    return nn[::-1]


def nn_tm(
    seq: str,
    compl_seq: str,
    primer_conc: float,
    Na: float,
    K: float,
    Tris: float,
    Mg: float,
    dNTPs: float,
    ion_corr: bool = True,
) -> float:
    """Calculate melting temperature using nearest-neighbor thermodynamics.

    Args:
        seq: Primer sequence (5'->3').
        compl_seq: Complementary sequence (3'->5').
        primer_conc: Primer concentration in nM.
        Na, K, Tris, Mg, dNTPs: Ion concentrations in mM.
        ion_corr: Whether to apply salt correction.

    Returns:
        Tm in degrees Celsius, rounded to one decimal place.
    """
    dH = 0.0
    dS = 0.0

    seq = seq.upper()
    compl_seq = compl_seq.upper()

    # General initiation value
    dH += DNA_NN_TABLE["init"][0]
    dS += DNA_NN_TABLE["init"][1]

    # Terminal A/T correction (considers terminal mismatches)
    count_at = 0
    terminal = f"{seq[0]}/{compl_seq[0]}"
    if terminal in ("A/T", "T/A"):
        count_at += 1
    terminal = f"{seq[-1]}/{compl_seq[-1]}"
    if terminal in ("A/T", "T/A"):
        count_at += 1
    dH += DNA_NN_TABLE["init_A/T"][0] * count_at
    dS += DNA_NN_TABLE["init_A/T"][1] * count_at

    for i in range(len(seq) - 1):
        nn = f"{seq[i]}{seq[i + 1]}/{compl_seq[i]}{compl_seq[i + 1]}"
        reverse_nn_key = _reverse_nn(nn)

        if i == 0:  # left terminal NN
            if reverse_nn_key in DNA_TMM_TABLE:
                dH += DNA_TMM_TABLE[reverse_nn_key][0]
                dS += DNA_TMM_TABLE[reverse_nn_key][1]
            elif nn in DNA_NN_TABLE:
                dH += DNA_NN_TABLE[nn][0]
                dS += DNA_NN_TABLE[nn][1]
            elif reverse_nn_key in DNA_NN_TABLE:
                dH += DNA_NN_TABLE[reverse_nn_key][0]
                dS += DNA_NN_TABLE[reverse_nn_key][1]
        elif i == len(seq) - 2:  # right terminal NN
            if nn in DNA_TMM_TABLE:
                dH += DNA_TMM_TABLE[nn][0]
                dS += DNA_TMM_TABLE[nn][1]
            elif nn in DNA_NN_TABLE:
                dH += DNA_NN_TABLE[nn][0]
                dS += DNA_NN_TABLE[nn][1]
            elif reverse_nn_key in DNA_NN_TABLE:
                dH += DNA_NN_TABLE[reverse_nn_key][0]
                dS += DNA_NN_TABLE[reverse_nn_key][1]
        else:  # internal NN
            if nn in DNA_IMM_TABLE:
                dH += DNA_IMM_TABLE[nn][0]
                dS += DNA_IMM_TABLE[nn][1]
            elif reverse_nn_key in DNA_IMM_TABLE:
                dH += DNA_IMM_TABLE[reverse_nn_key][0]
                dS += DNA_IMM_TABLE[reverse_nn_key][1]
            elif nn in DNA_NN_TABLE:
                dH += DNA_NN_TABLE[nn][0]
                dS += DNA_NN_TABLE[nn][1]
            elif reverse_nn_key in DNA_NN_TABLE:
                dH += DNA_NN_TABLE[reverse_nn_key][0]
                dS += DNA_NN_TABLE[reverse_nn_key][1]

    if ion_corr:
        correction = ion_correction(Na, K, Tris, Mg, dNTPs, len(seq))
        dS += correction

    # x = 4 for non-self-complementary; x = 1 for self-complementary.
    # The original Perl code hard-codes x = 4.
    x = 4
    R = 1.9872  # cal/(mol*K)
    primer_conc_molar = primer_conc / 1e9
    tm = (1000 * dH) / (dS + (R * math.log(primer_conc_molar / x))) - 273.15
    return round(tm, 1)


def primer_tm(
    seq: str,
    primer_conc: float = 100.0,
    Na: float = 0.0,
    K: float = 50.0,
    Tris: float = 10.0,
    Mg: float = 1.5,
    dNTPs: float = 0.2,
) -> float:
    """Convenience wrapper: Tm of a primer against its perfect complement."""
    return nn_tm(seq, complement(seq), primer_conc, Na, K, Tris, Mg, dNTPs, ion_corr=True)
