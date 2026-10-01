#!/usr/bin/env python3
"""conftest.py must import when pytest is invoked from the repo root."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestConftestPytestImport(unittest.TestCase):
    def test_conftest_imports_without_tests_dir_on_sys_path(self):
        # pytest from repo root puts "" / ROOT on sys.path, not tests/.
        code = r"""
import sys, importlib.util
from pathlib import Path
root = Path(%r)
sys.path = [str(root)] + [p for p in sys.path[1:] if Path(p).resolve() != root / "tests"]
spec = importlib.util.spec_from_file_location("conftest", root / "tests" / "conftest.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert hasattr(mod, "pytest_sessionfinish"), dir(mod)
assert callable(mod.pytest_sessionfinish)
print("import-ok")
""" % str(ROOT)
        r = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            r.returncode, 0,
            f"conftest import failed (pytest-from-root simulation)\n{r.stdout}\n{r.stderr}",
        )
        self.assertIn("import-ok", r.stdout)

    def test_conftest_still_calls_data_tree_guard(self):
        src = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
        self.assertIn("pytest_sessionfinish", src)
        self.assertIn("data_tree_drift", src)
        self.assertIn("repo_guard", src)
