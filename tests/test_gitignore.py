#!/usr/bin/env python3
"""Nested files under data/ must stay gitignored (data/**, not data/*).

Runs git check-ignore in a temp git repo that copies only .gitignore, so the
suite never creates, modifies, or deletes files in the real data/ tree, and
works in a folder that has no .git.
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_guard  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]

MUST_IGNORE = [
    "data/followers/snapshot-2026-01-01.json",
    "data/followers/latest.json",
    "data/posts/posts-1.json",
    "data/analytics-csv/x.csv",
    "data/research/reply_targets.json",
    "data/research/README-onderzoek.md",
    "data/config.json",
    "data/target_accounts.json",
    "data/public_allowlist.json",
    "assets/avatar.jpg",
    "assets/avatar.png",
    ".avatar-cache/meta.json",
    "data/.avatar-cache/avatar.png",
    "secrets.pem",
    "deploy.key",
]

MUST_KEEP = [
    "data/followers/.gitkeep",
    "data/config.example.json",
    "data/.gitkeep",
    "data/posts/.gitkeep",
    "data/analytics-csv/.gitkeep",
    "data/target_accounts.example.json",
    "data/public_allowlist.example.json",
    "assets/og-image.png",
    ".env.example",
]


class TestGitignoreData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory(prefix="xdash-ignore-")
        cls.addClassCleanup(cls._td.cleanup)
        cls.tmp = Path(cls._td.name)
        subprocess.run(["git", "init", "-q"], cwd=cls.tmp, check=True, capture_output=True)
        shutil.copy(ROOT / ".gitignore", cls.tmp / ".gitignore")
        for rel in (
            "data/followers", "data/posts", "data/analytics-csv", "data/research",
        ):
            (cls.tmp / rel).mkdir(parents=True, exist_ok=True)

    def check_ignore(self, path: str) -> int:
        return subprocess.run(
            ["git", "check-ignore", "-q", "--", path],
            cwd=self.tmp,
        ).returncode

    def test_data_block_uses_double_star(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^data/\*\*$")
        self.assertRegex(text, r"(?m)^!data/\*\*/$")
        self.assertRegex(text, r"(?m)^!data/\*\*/\.gitkeep$")
        self.assertRegex(text, r"(?m)^!data/\*\*/\*\.example\.\*$")
        self.assertNotRegex(text, r"(?m)^data/\*$")

    def test_nested_data_paths_are_ignored(self):
        for p in MUST_IGNORE:
            with self.subTest(p=p):
                self.assertEqual(self.check_ignore(p), 0, f"expected ignored: {p}")

    def test_gitkeep_and_examples_are_not_ignored(self):
        for p in MUST_KEEP:
            with self.subTest(p=p):
                self.assertEqual(self.check_ignore(p), 1, f"expected not ignored: {p}")

    def test_git_add_does_not_stage_nested_data(self):
        dummies = [
            self.tmp / "data" / "followers" / "snapshot-2026-01-01.json",
            self.tmp / "data" / "followers" / "latest.json",
            self.tmp / "data" / "posts" / "posts-1.json",
            self.tmp / "data" / "analytics-csv" / "x.csv",
            self.tmp / "data" / "research" / "reply_targets.json",
            self.tmp / "data" / "research" / "README-onderzoek.md",
        ]
        for p in dummies:
            p.write_text("{}\n", encoding="utf-8")
        r = subprocess.run(
            ["git", "add", "-A", "-n", "--", "data"],
            cwd=self.tmp, capture_output=True, text=True,
        )
        out = r.stdout + r.stderr
        self.assertNotIn("snapshot-2026-01-01.json", out)
        self.assertNotIn("latest.json", out)
        self.assertNotIn("posts-1.json", out)
        self.assertNotIn("analytics-csv/x.csv", out)
        self.assertNotIn("reply_targets.json", out)
        self.assertNotIn("README-onderzoek.md", out)
        add_one = subprocess.run(
            ["git", "add", "-n", "--", "data/followers/latest.json"],
            cwd=self.tmp, capture_output=True, text=True,
        )
        self.assertNotEqual(add_one.returncode, 0)
        self.assertIn("ignored", (add_one.stderr + add_one.stdout).lower())
