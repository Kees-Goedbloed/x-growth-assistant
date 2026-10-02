#!/usr/bin/env python3
"""Open Agent Skills frontmatter and discovery paths."""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_guard  # noqa: F401,E402

ROOT = Path(__file__).resolve().parents[1]
FRONT = re.compile(
    r"^---\r?\n"
    r"(?P<body>.*?)"
    r"^---\r?\n",
    re.S | re.M,
)
NAME = re.compile(r"(?m)^name:\s*(\S+)\s*$")
DESC = re.compile(r"(?m)^description:\s*(.+)$")


class TestAgentSkills(unittest.TestCase):
    def test_skill_frontmatter(self):
        skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
        self.assertGreaterEqual(len(skills), 2, skills)
        names = set()
        for path in skills:
            text = path.read_text(encoding="utf-8")
            m = FRONT.match(text)
            self.assertIsNotNone(m, f"YAML frontmatter missing: {path}")
            block = m.group("body")
            nm = NAME.search(block)
            ds = DESC.search(block)
            self.assertIsNotNone(nm, path)
            self.assertIsNotNone(ds, path)
            self.assertGreater(len(ds.group(1).strip()), 20, path)
            names.add(nm.group(1))
            self.assertNotIn("leingoedbloed", text.lower())
            self.assertNotIn("/workspace", text)
            self.assertNotIn("leinaisystems", text.lower())
        self.assertIn("x-growth-getting-started", names)
        self.assertIn("x-growth-data-collection", names)

    def test_host_skill_aliases(self):
        for host in (".claude/skills", ".cursor/skills"):
            for name in ("x-growth-getting-started", "x-growth-data-collection"):
                link = ROOT / host / name
                self.assertTrue(link.exists(), link)
                skill = (link / "SKILL.md").resolve()
                self.assertTrue(skill.is_file(), skill)
                self.assertEqual(skill.parent.name, name)

    def test_daily_routine_and_coc(self):
        routine = (ROOT / "docs" / "daily-routine.md").read_text(encoding="utf-8")
        self.assertIn("snapshot-YYYYMMDD-HHMMSS.json", routine)
        self.assertIn("data/analytics-csv/", routine)
        self.assertIn("GV9QXOW5kYS9o8Rq6MFFi", routine)
        coc = (ROOT / "CODE_OF_CONDUCT.md").read_text(encoding="utf-8")
        self.assertIn("Contributor Covenant", coc)
        self.assertIn("version 2.1", coc)
        self.assertIn("GitHub", coc)
        proj = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('version = "0.1.0"', proj)
        self.assertTrue((ROOT / "CHANGELOG.md").is_file())
        self.assertTrue((ROOT / ".cursorrules").is_file())
        rules = (ROOT / ".cursorrules").read_text(encoding="utf-8")
        self.assertIn("AGENTS.md", rules)
