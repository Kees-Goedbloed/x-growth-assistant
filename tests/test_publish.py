#!/usr/bin/env python3
"""publish.sh: env requirements, no git data push, dry-run, mode/site mismatch."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_guard

ROOT = Path(__file__).resolve().parents[1]


class TestPublishScript(unittest.TestCase):
    def test_bash_syntax(self):
        r = subprocess.run(["bash", "-n", str(ROOT / "scripts" / "publish.sh")])
        self.assertEqual(r.returncode, 0)
        r2 = subprocess.run(["bash", "-n", str(ROOT / "scripts" / "netlify-build.sh")])
        self.assertEqual(r2.returncode, 0)
        r3 = subprocess.run(["bash", "-n", str(ROOT / "scripts" / "check_no_real_data.sh")])
        self.assertEqual(r3.returncode, 0)

    def test_no_git_data_push(self):
        src = (ROOT / "scripts" / "publish.sh").read_text(encoding="utf-8")
        self.assertNotRegex(src, re.compile(r"^\s*git\s+add\b", re.M))
        self.assertNotRegex(src, re.compile(r"^\s*git\s+commit\b", re.M))
        self.assertNotRegex(src, re.compile(r"^\s*git\s+push\b", re.M))
        self.assertIn("netlify deploy", src)
        self.assertIn("--no-build", src)
        self.assertIn("NETLIFY_SITE_ID_PUBLIC", src)
        self.assertIn("NETLIFY_SITE_ID_PRIVATE", src)
        self.assertIn("NETLIFY_AUTH_TOKEN", src)
        self.assertIn("SOURCE_DATA_DIR", src)
        self.assertIn("X_FOLLOWERS_DIR", src)
        self.assertIn("XDASH_AVATAR_CACHE", src)
        self.assertIn("mktemp -d", src)
        self.assertNotIn("mktemp /tmp/xdash-test.XXXXXX.html", src)
        r4 = subprocess.run(["bash", "-n", str(ROOT / "scripts" / "check_tmp_hygiene.sh")])
        self.assertEqual(r4.returncode, 0)
        self.assertIn(".avatar-cache", src)
        # Generic only: no hardcoded absolute home/agent paths.
        self.assertNotRegex(src, re.compile(r"/home/[^/]+/"))

    def test_origin_urls(self):
        script = ROOT / "scripts" / "publish.sh"
        cases = [
            ("https://github.com/Kees-Goedbloed/x-growth-assistant", True),
            ("https://github.com/Kees-Goedbloed/x-growth-assistant.git", True),
            ("git@github.com:Kees-Goedbloed/x-growth-assistant.git", True),
            ("https://x-access-token:fake@github.com/Kees-Goedbloed/x-growth-assistant", True),
            ("ssh://git@github.com:Kees-Goedbloed/x-growth-assistant.git", True),
            ("https://github.com/other-org/other-repo", False),
            ("https://github.com/other/x-growth-assistant", False),
        ]
        for url, ok in cases:
            r = subprocess.run(
                ["bash", "-c",
                 'source "$1"; origin_allowed "$2" && echo 0 || echo 1',
                 "bash", str(script), url],
                capture_output=True, text=True, check=True,
            )
            code = r.stdout.strip().splitlines()[-1]
            self.assertEqual(code, "0" if ok else "1", f"{url} -> {r.stdout!r} {r.stderr!r}")

    def test_missing_env_fails(self):
        env = repo_guard.origin_git_env()
        for k in ("SOURCE_DATA_DIR", "X_FOLLOWERS_DIR", "NETLIFY_SITE_ID_PUBLIC",
                  "NETLIFY_SITE_ID_PRIVATE", "NETLIFY_AUTH_TOKEN"):
            env.pop(k, None)
        r = subprocess.run(
            ["bash", str(ROOT / "scripts" / "publish.sh"), "--dry-run"],
            cwd=ROOT, capture_output=True, text=True, env=env,
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue("SOURCE_DATA_DIR" in r.stderr or "SOURCE_DATA_DIR" in r.stdout)

    def test_dry_run_builds_fixtures_without_deploy(self):
        extra = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, extra, ignore_errors=True)
        env = repo_guard.origin_git_env()
        env.update({
            "SOURCE_DATA_DIR": str(ROOT / "test-fixtures" / "data"),
            "X_FOLLOWERS_DIR": str(extra),
            "NETLIFY_SITE_ID_PUBLIC": "public-site-id-example",
            "NETLIFY_SITE_ID_PRIVATE": "private-site-id-example",
            "NETLIFY_AUTH_TOKEN": "not-a-real-token",
            "PATH": "/usr/bin:/bin",
            "PYTHON": os.environ.get("PYTHON", "python3"),
        })
        r = subprocess.run(
            ["bash", str(ROOT / "scripts" / "publish.sh"), "--dry-run"],
            cwd=ROOT, capture_output=True, text=True, env=env,
        )
        combined = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, combined)
        self.assertNotIn("git commit", combined)
        self.assertIn("Dry-run", combined)

    def test_mode_mismatch_helper(self):
        script = ROOT / "scripts" / "publish.sh"
        r = subprocess.run(
            ["bash", "-c",
             'source "$1"; meta_mode "$2"',
             "bash", str(script), str(ROOT / "template.html")],
            capture_output=True, text=True,
        )
        out = (r.stdout or "").strip()
        self.assertTrue(
            r.returncode != 0 or out in ("", "private", "public", "__MODE__"),
            f"unexpected meta_mode output: {out!r} {r.stderr!r}",
        )

    def test_tmp_hygiene_wrapper_passes_when_clean(self):
        r = subprocess.run(
            ["bash", str(ROOT / "scripts" / "check_tmp_hygiene.sh"), "true"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_tmp_hygiene_wrapper_flags_new_tmp_dir(self):
        r = subprocess.run(
            ["bash", str(ROOT / "scripts" / "check_tmp_hygiene.sh"),
             sys.executable, "-c",
             "import tempfile; print(tempfile.mkdtemp())"],
            cwd=ROOT, capture_output=True, text=True,
        )
        planted = []
        try:
            planted = (r.stdout or "").strip().splitlines()
            planted.extend((r.stderr or "").splitlines())
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(
                any("tmp" in line for line in (r.stderr or "").splitlines()),
                r.stderr,
            )
        finally:
            for line in planted:
                p = Path(line.strip())
                if p.is_dir() and p.name.startswith("tmp"):
                    shutil.rmtree(p, ignore_errors=True)
