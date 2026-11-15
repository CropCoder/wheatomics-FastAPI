#!/usr/bin/env python3
"""Unit tests for scripts/update_blast_alias.py (base + delta alias maintenance).

Run with::

    python3 -m unittest scripts.tests.test_update_blast_alias -v
    # or
    python3 scripts/tests/test_update_blast_alias.py
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "update_blast_alias.py"


def load_module():
    spec = importlib.util.spec_from_file_location("update_blast_alias", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["update_blast_alias"] = module
    spec.loader.exec_module(module)
    return module


STUB = textwrap.dedent(
    """\
    #!/bin/sh
    # stub blastdbcmd: supports "-db NAME -info" and "-db NAME -entry ID"
    db=""; action=""; entry=""
    while [ $# -gt 0 ]; do
      case "$1" in
        -db) db="$2"; shift 2 ;;
        -info) action="info"; shift ;;
        -entry) entry="$2"; shift 2 ;;
        *) shift ;;
      esac
    done
    if [ "$action" = "info" ]; then
      echo "Database: $db"
      echo "\\t10 sequences; 100 total bases"
      exit 0
    fi
    if [ -n "$entry" ]; then
      echo ">$entry"
      echo "ACGTACGTACGT"
      exit 0
    fi
    exit 1
    """
)


class AliasTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.blastdb = Path(self.tmp.name)
        self.stub = self.blastdb / "blastdbcmd"
        self.stub.write_text(STUB, encoding="utf-8")
        self.stub.chmod(0o755)
        self.mod = load_module()

    def tearDown(self):
        self.tmp.cleanup()

    # -- helpers ---------------------------------------------------------
    def db(self, *members: str) -> None:
        """Create fake physical files for each member DB."""
        for member in members:
            (self.blastdb / f"{member}.nhr").write_text("x", encoding="utf-8")

    def alias(self, name: str, members: list[str], title: str = "TEST") -> Path:
        path = self.blastdb / name
        path.write_text("TITLE " + title + "\nDBLIST " + " ".join(members) + "\n",
                        encoding="utf-8")
        return path

    def read(self, name: str) -> list[str]:
        _title, members = self.mod.read_alias(self.blastdb / name)
        return members

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        cmd = [sys.executable, str(SCRIPT), "--blastdb", str(self.blastdb),
               "--blastdbcmd", str(self.stub), *args]
        return subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))


class TestAppend(AliasTestBase):
    def test_append_legacy_alias_keeps_order_and_dedupes(self):
        self.db("A.genome", "B.genome", "C.genome")
        self.alias("all_genomes.nal", ["A.genome", "B.genome"])
        proc = self.run_cli("--alias", "all_genomes.nal", "--mode", "append",
                            "--members", "B.genome", "C.genome", "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read("all_genomes.nal"), ["A.genome", "B.genome", "C.genome"])
        self.assertIn("ALIAS_OK", proc.stdout)

    def test_append_base_plus_delta_keeps_base_first(self):
        self.db("all_genes_base", "d1.cds", "d2.cds")
        self.alias("all_genes.nal", ["all_genes_base", "d1.cds"])
        proc = self.run_cli("--alias", "all_genes.nal", "--mode", "append",
                            "--members", "d2.cds", "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read("all_genes.nal"), ["all_genes_base", "d1.cds", "d2.cds"])
        self.assertIn("layout: base+delta", proc.stdout)

    def test_append_over_limit_requires_flag(self):
        members = [f"g{i}.genome" for i in range(200)]
        self.db(*members, "new.genome")
        self.alias("all_genomes.nal", members)
        before = (self.blastdb / "all_genomes.nal").read_text()
        proc = self.run_cli("--alias", "all_genomes.nal", "--mode", "append",
                            "--members", "new.genome", "--apply")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual((self.blastdb / "all_genomes.nal").read_text(), before)

    def test_append_over_limit_prepends_with_flag(self):
        members = [f"g{i}.genome" for i in range(200)]
        self.db(*members, "new.genome")
        self.alias("all_genomes.nal", members)
        proc = self.run_cli("--alias", "all_genomes.nal", "--mode", "append",
                            "--members", "new.genome", "--allow-overlimit", "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        after = self.read("all_genomes.nal")
        self.assertEqual(len(after), 201)
        self.assertEqual(after[0], "new.genome")  # readable inside first-200 window
        self.assertEqual(after[1:], members)

    def test_append_invalid_member_aborts(self):
        self.db("A.genome")
        self.alias("all_genomes.nal", ["A.genome"])
        before = (self.blastdb / "all_genomes.nal").read_text()
        proc = self.run_cli("--alias", "all_genomes.nal", "--mode", "append",
                            "--members", "missing.genome", "--apply")
        self.assertEqual(proc.returncode, 4)
        self.assertEqual((self.blastdb / "all_genomes.nal").read_text(), before)

    def test_append_invalid_member_skipped_with_flag(self):
        self.db("A.genome")
        self.alias("all_genomes.nal", ["A.genome"])
        proc = self.run_cli("--alias", "all_genomes.nal", "--mode", "append",
                            "--members", "missing.genome", "--skip-invalid", "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read("all_genomes.nal"), ["A.genome"])

    def test_dry_run_does_not_write(self):
        self.db("A.genome", "B.genome")
        path = self.alias("all_genomes.nal", ["A.genome"])
        before = path.read_text()
        proc = self.run_cli("--alias", "all_genomes.nal", "--mode", "append",
                            "--members", "B.genome")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(path.read_text(), before)
        self.assertIn("[DRY-RUN]", proc.stdout)


class TestSwitchAndSet(AliasTestBase):
    def test_switch_replaces_with_base(self):
        self.db("all_genes_base", "old1.cds")
        self.alias("all_genes.nal", ["old1.cds"])
        proc = self.run_cli("--alias", "all_genes.nal", "--mode", "switch",
                            "--base", "all_genes_base", "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read("all_genes.nal"), ["all_genes_base"])

    def test_switch_keep_deltas(self):
        self.db("all_genes_base", "old1.cds", "old2.cds")
        self.alias("all_genes.nal", ["old1.cds", "old2.cds"])
        proc = self.run_cli("--alias", "all_genes.nal", "--mode", "switch",
                            "--base", "all_genes_base", "--keep-deltas", "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read("all_genes.nal"),
                         ["all_genes_base", "old1.cds", "old2.cds"])

    def test_set_from_member_file(self):
        self.db("all_genes_base", "d1.cds")
        self.alias("all_genes.nal", ["legacy.cds"])
        mf = self.blastdb / "members.txt"
        mf.write_text("all_genes_base\nd1.cds\n# comment\n", encoding="utf-8")
        proc = self.run_cli("--alias", "all_genes.nal", "--mode", "set",
                            "--member-file", str(mf), "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read("all_genes.nal"), ["all_genes_base", "d1.cds"])

    def test_backup_created(self):
        self.db("A.genome", "B.genome")
        self.alias("all_genomes.nal", ["A.genome"])
        proc = self.run_cli("--alias", "all_genomes.nal", "--mode", "append",
                            "--members", "B.genome", "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        backups = list(self.blastdb.glob("all_genomes.nal.bak-*"))
        self.assertEqual(len(backups), 1)
        self.assertIn("A.genome", backups[0].read_text())

    def test_check_entry_runs(self):
        self.db("A.genome")
        self.alias("all_genomes.nal", ["A.genome"])
        proc = self.run_cli("--alias", "all_genomes.nal", "--mode", "append",
                            "--members", "A.genome", "--check-entry", "Chr1A_x",
                            "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("entry Chr1A_x: found", proc.stdout)

    def test_missing_alias_errors(self):
        proc = self.run_cli("--alias", "nope.nal", "--mode", "append",
                            "--members", "A.genome")
        self.assertNotEqual(proc.returncode, 0)


class TestHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def test_is_base_member(self):
        self.assertTrue(self.mod.is_base_member("all_genes_base"))
        self.assertTrue(self.mod.is_base_member("all_genomes_base"))
        self.assertTrue(self.mod.is_base_member("foo_base.cds"))
        self.assertFalse(self.mod.is_base_member("AABB_genome.genome"))
        self.assertFalse(self.mod.is_base_member("all_genes"))
        self.assertFalse(self.mod.is_base_member("database_baseball"))

    def test_layout_of(self):
        self.assertIn("legacy", self.mod.layout_of(["a", "b"]))
        self.assertIn("base+delta", self.mod.layout_of(["all_genes_base", "d1"]))
        self.assertIn("deltas=0", self.mod.layout_of(["all_genes_base"]))

    def test_dedupe_keep_order(self):
        unique, dups = self.mod.dedupe_keep_order(["a", "b", "a", "c", "b"])
        self.assertEqual(unique, ["a", "b", "c"])
        self.assertEqual(dups, ["a", "b"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
