"""PrimerServer2 configuration adapter for WheatOmics.

Reads centralized settings from app.core.config.settings and provides the
same typed accessors the original PrimerServer backend used.
"""

import configparser
import re
from pathlib import Path
from typing import Dict, List, Optional

from app.core.config import settings

#: BLAST index extensions — same set used by the main API's DB existence
#: oracle (app/api/routers/sequence.py). .nal/.pal are alias files.
_BLAST_INDEX_EXTS = (".nsq", ".nin", ".nhr", ".nal", ".psq", ".pin", ".phr", ".pal")


def blast_db_exists(name: str) -> bool:
    """True if `name` resolves to a BLAST database under BLAST_DB_PATH.

    Accepts multi-volume index sets (name.nsq/name.nin/name.nhr), alias
    files (name.nal/.pal) and BLAST v5 database directories.
    """
    if not name:
        return False
    base = Path(settings.BLAST_DB_PATH) / name
    for ext in _BLAST_INDEX_EXTS:
        if (base.parent / (base.name + ext)).exists():
            return True
    if base.is_dir():
        return any(base.glob("*.nsq")) or any(base.glob("*.psq")) or any(base.glob("*.ndb"))
    return False


class PrimerServerConfig:
    """Wrapper around config.ini with typed accessors."""

    _QUOTE_RE = re.compile(r'^["\']|["\']$')

    def __init__(self, config_path: Path):
        self._path = config_path
        self._parser = configparser.ConfigParser()
        # Preserve the original case of option keys (e.g. database names).
        self._parser.optionxform = str
        if config_path.exists():
            self._parser.read(config_path, encoding="utf-8")

    @property
    def path(self) -> Path:
        return self._path

    @classmethod
    def _strip_quotes(cls, value: str) -> str:
        return cls._QUOTE_RE.sub("", value).strip()

    def _path_value(self, key: str) -> str:
        return self._strip_quotes(self._parser.get("Path", key, fallback=""))

    def _system_value(self, key: str, fallback=None):
        return self._parser.get("System Configuration", key, fallback=fallback)

    def _limit_value(self, key: str, fallback: int = 0) -> int:
        try:
            return self._parser.getint("Input Limit Number", key, fallback=fallback)
        except ValueError:
            return fallback

    @property
    def samtools(self) -> str:
        return self._path_value("samtools")

    @property
    def primer3(self) -> str:
        return self._path_value("primer3")

    @property
    def blastn(self) -> str:
        return self._path_value("blastn")

    @property
    def blastdbcmd(self) -> str:
        """blastdbcmd binary path: [Path] blastdbcmd, else sibling of blastn,
        else rely on PATH."""
        configured = self._path_value("blastdbcmd")
        if configured:
            return configured
        blastn = self.blastn
        if blastn:
            sibling = Path(blastn).parent / "blastdbcmd"
            if sibling.exists():
                return str(sibling)
        return "blastdbcmd"

    @property
    def makeblastdb(self) -> str:
        return self._path_value("makeblastdb")

    @property
    def database_dir(self) -> str:
        return self._path_value("database")

    @property
    def use_cpu(self) -> int:
        try:
            return int(self._system_value("useCPU", fallback="1"))
        except ValueError:
            return 1

    @property
    def show_info(self) -> bool:
        val = self._system_value("showInfo", fallback="false")
        return val.lower() in ("true", "1", "yes")

    @property
    def remove_tmp(self) -> bool:
        val = self._system_value("removeTmp", fallback="true")
        return val.lower() in ("true", "1", "yes")

    @property
    def limit_site(self) -> int:
        return self._limit_value("limitSite", fallback=100)

    @property
    def limit_primer(self) -> int:
        return self._limit_value("limitPrimer", fallback=1000)

    @property
    def limit_database(self) -> int:
        return self._limit_value("limitDatabase", fallback=4)

    def databases(self) -> Dict[str, Dict[str, str]]:
        """Return database groups mapping group name to {filename: alias}."""
        groups: Dict[str, Dict[str, str]] = {}
        for section in self._parser.sections():
            if section.startswith("Database."):
                group_name = section[len("Database."):]
                groups[group_name] = {
                    self._strip_quotes(k): self._strip_quotes(v)
                    for k, v in self._parser.items(section)
                }
        return groups

    def all_database_files(self) -> List[str]:
        """Return all database file names declared in [Database.*] sections."""
        files = []
        for group in self.databases().values():
            files.extend(group.keys())
        return files

    def database_exists(self, name: str) -> bool:
        """Check whether a database file name is declared in config.ini or
        present as a BLAST database under settings.BLAST_DB_PATH."""
        if name == "custom":
            return True
        if name in self.all_database_files():
            return True
        return blast_db_exists(name)

    def database_path(self, name: str) -> Path:
        """Return absolute path to a database file."""
        return Path(self.database_dir) / name

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
        """Check whether an executable configured in [Path] is available."""
        import shutil

        exe = getattr(self, name, "")
        if not exe:
            return False
        return shutil.which(exe) is not None


def get_primer_config() -> PrimerServerConfig:
    """Load PrimerServer config.ini from the path configured in WheatOmics settings."""
    return PrimerServerConfig(settings.PRIMERSERVER2_CONFIG_PATH)
