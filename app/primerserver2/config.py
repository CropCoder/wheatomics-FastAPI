"""PrimerServer2 configuration.

The original PrimerServer read its own config.ini. This module keeps the same
typed accessors but sources them from app.core.config.settings, so the whole
project has one configuration mechanism and one place to look — see the
PRIMERSERVER2_* entries in .env.example.

The ini format is gone on purpose: half of that file was a legacy FASTA database
list the code no longer resolves, and a duplicate key in it made configparser
raise, which turned every /api/PrimerServer2/* request into a 500.
"""

import shutil
from pathlib import Path

from app.core.config import settings

#: BLAST index extensions — single-volume flat files and alias files.
#: Multi-volume splits (name.00.nsq, name.01.nsq) and BLAST v5 files are
#: handled separately in blast_db_exists.
_BLAST_INDEX_EXTS = (".nsq", ".nin", ".nhr", ".nal", ".psq", ".pin", ".phr", ".pal")


def blast_db_exists(name: str) -> bool:
    """True if `name` resolves to a BLAST database under BLAST_DB_PATH.

    Covers the layouts actually present on the server:
    - single-volume index sets (name.nsq / name.nin / name.nhr)
    - multi-volume splits (name.00.nsq, name.01.nsq, ...)
    - BLAST v5 single-file databases (name.ndb / .njs / ...)
    - alias files (name.nal / .pal)
    - v5 database directories
    """
    if not name:
        return False
    base = Path(settings.BLAST_DB_PATH) / name
    parent, stem = base.parent, base.name

    for ext in _BLAST_INDEX_EXTS:
        if (parent / f"{stem}{ext}").exists():
            return True
        # multi-volume: stem.00.ext, stem.01.ext, ...
        try:
            if next(parent.glob(f"{stem}.[0-9][0-9]{ext}"), None):
                return True
        except OSError:
            pass

    # BLAST v5 single-file databases (nucleotide .ndb family, protein .pdb family)
    for ext in (".ndb", ".njs", ".not", ".ntf", ".nto", ".pdb", ".pjs", ".pot", ".ptf", ".pto"):
        if (parent / f"{stem}{ext}").exists():
            return True

    if base.is_dir():
        return any(base.glob("*.nsq")) or any(base.glob("*.psq")) or any(base.glob("*.ndb"))
    return False


class PrimerServerConfig:
    """Typed accessors over the PRIMERSERVER2_* settings."""

    @property
    def samtools(self) -> str:
        return settings.PRIMERSERVER2_SAMTOOLS

    @property
    def primer3(self) -> str:
        return settings.PRIMERSERVER2_PRIMER3

    @property
    def blastn(self) -> str:
        return settings.PRIMERSERVER2_BLASTN

    @property
    def makeblastdb(self) -> str:
        return settings.PRIMERSERVER2_MAKEBLASTDB

    @property
    def blastdbcmd(self) -> str:
        """Configured path, else the blastdbcmd beside blastn, else PATH."""
        if settings.PRIMERSERVER2_BLASTDBCMD:
            return settings.PRIMERSERVER2_BLASTDBCMD
        blastn = self.blastn
        if blastn:
            sibling = Path(blastn).parent / "blastdbcmd"
            if sibling.exists():
                return str(sibling)
        return "blastdbcmd"

    @property
    def use_cpu(self) -> int:
        return settings.PRIMERSERVER2_USE_CPU

    @property
    def show_info(self) -> bool:
        return settings.PRIMERSERVER2_SHOW_INFO

    @property
    def remove_tmp(self) -> bool:
        return settings.PRIMERSERVER2_REMOVE_TMP

    @property
    def limit_site(self) -> int:
        return settings.PRIMERSERVER2_LIMIT_SITE

    @property
    def limit_primer(self) -> int:
        return settings.PRIMERSERVER2_LIMIT_PRIMER

    @property
    def limit_database(self) -> int:
        return settings.PRIMERSERVER2_LIMIT_DATABASE

    def to_public_dict(self) -> dict:
        return {
            "limitSite": self.limit_site,
            "limitPrimer": self.limit_primer,
            "limitDatabase": self.limit_database,
            "useCPU": self.use_cpu,
            "showInfo": self.show_info,
            "removeTmp": self.remove_tmp,
        }

    def executable_available(self, name: str) -> bool:
        """True when the `name` tool is configured and actually runnable.

        False covers both "not configured" and "configured but missing" — either
        way the job would fail, and /health reports which tools are affected.
        """
        exe = getattr(self, name, "")
        if not exe:
            return False
        return shutil.which(exe) is not None

    def database_exists(self, name: str) -> bool:
        """True if `name` is 'custom' or a BLAST database under BLAST_DB_PATH."""
        if name == "custom":
            return True
        return blast_db_exists(name)


def get_primer_config() -> PrimerServerConfig:
    return PrimerServerConfig()
