#!/usr/bin/env python3
"""Last test module: fail if any test mutated the real data/ tree or leaked /tmp/tmp*."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_guard


class TestDataTreeUnchanged(unittest.TestCase):
    def test_data_tree_matches_session_start(self):
        drift = repo_guard.data_tree_drift()
        self.assertEqual(
            drift, {},
            f"tests mutated repo data/ (paths + hashes must stay unchanged): {drift}",
        )

    def test_no_new_tmp_star_dirs(self):
        repo_guard.cleanup_origin_git_envs()
        leftover = repo_guard.leftover_tmp_star_dirs()
        self.assertEqual(
            leftover, set(),
            f"full test run left new /tmp/tmp* dirs: {sorted(leftover)}",
        )

    def test_mkdtemp_sites_register_cleanup(self):
        root = Path(__file__).resolve().parent
        offenders = []
        tokens = ("addCleanup", "addClassCleanup", "TemporaryDirectory", "cleanup_origin_git")
        for path in sorted(root.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if "tempfile.mkdtemp" not in text:
                continue
            if not any(tok in text for tok in tokens):
                offenders.append(str(path.relative_to(root)))
        self.assertEqual(offenders, [], f"mkdtemp without cleanup: {offenders}")
