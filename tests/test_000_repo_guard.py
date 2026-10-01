#!/usr/bin/env python3
"""Import first (filename sorts first) so data/ is snapshotted before other tests."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_guard  # noqa: F401  # snapshots SESSION_DATA_SNAPSHOT at import


class TestRepoGuardStarted(unittest.TestCase):
    def test_session_snapshot_captured(self):
        self.assertIsInstance(repo_guard.SESSION_DATA_SNAPSHOT, dict)
        self.assertTrue(
            any(k.endswith(".example.json") or k.endswith(".gitkeep") or k.endswith("/")
                for k in repo_guard.SESSION_DATA_SNAPSHOT),
            repo_guard.SESSION_DATA_SNAPSHOT,
        )

    def test_tmp_dir_snapshot_captured(self):
        self.assertIsInstance(repo_guard.SESSION_TMP_DIRS, set)
