#!/usr/bin/env python3
"""Public-repo defaults: fixtures, public mode, leak check, hygiene, hosted creds."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_guard  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build  # noqa: E402

from test_public import extract_payload, write_mini_dataset  # noqa: E402


def _copy_fresh_tree(dest: Path) -> None:
    skip_dirs = {".git", "__pycache__", "dist", ".pytest_cache", "node_modules"}

    def ignore(directory, names):
        dropped = [n for n in names if n in skip_dirs or n.endswith(".pyc")]
        if Path(directory).name == "test-fixtures" and "data" in names:
            dropped.append("data")
        return dropped

    shutil.copytree(ROOT, dest, ignore=ignore)
    for html in dest.glob("index*.html"):
        html.unlink()
    cfg = dest / "data" / "config.json"
    if cfg.exists():
        cfg.unlink()
    for sub in ("followers", "posts", "analytics-csv"):
        folder = dest / "data" / sub
        if not folder.is_dir():
            folder.mkdir(parents=True, exist_ok=True)
            continue
        for p in folder.iterdir():
            if p.name == ".gitkeep":
                continue
            if p.is_file():
                p.unlink()
            else:
                shutil.rmtree(p)
    shutil.rmtree(dest / "test-fixtures" / "data", ignore_errors=True)


class TestResolveBuildMode(unittest.TestCase):
    def test_cli_wins_then_config_then_public(self):
        self.assertEqual(build.resolve_build_mode("public", {"mode": "private"}), "public")
        self.assertEqual(build.resolve_build_mode("private", {"mode": "public"}), "private")
        self.assertEqual(build.resolve_build_mode(None, {"mode": "private"}), "private")
        self.assertEqual(build.resolve_build_mode(None, {"mode": "public"}), "public")
        self.assertEqual(build.resolve_build_mode(None, {}), "public")
        self.assertEqual(build.resolve_build_mode(None, {"mode": "garbage"}), "public")
        self.assertEqual(build.resolve_build_mode("", None), "public")


class TestConfigModePrivate(unittest.TestCase):
    def test_config_mode_private_without_cli(self):
        with tempfile.TemporaryDirectory(prefix="xdash-cfg-priv-") as td:
            tmp = Path(td)
            data = tmp / "data"
            write_mini_dataset(data)
            cfg_path = data / "config.json"
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            cfg["mode"] = "private"
            cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
            out = tmp / "index.html"
            r = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "build.py"),
                    "--data",
                    str(data),
                    "--no-followers",
                    "--out",
                    str(out),
                    "--today",
                    "2026-09-25",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            html = out.read_text(encoding="utf-8")
            self.assertIn('name="x-dashboard-mode" content="private"', html)
            self.assertIn("other_user_00", html)

    def test_cli_public_overrides_config_private(self):
        with tempfile.TemporaryDirectory(prefix="xdash-cfg-cli-") as td:
            tmp = Path(td)
            data = tmp / "data"
            write_mini_dataset(data)
            cfg_path = data / "config.json"
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            cfg["mode"] = "private"
            cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
            out = tmp / "index.html"
            r = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "build.py"),
                    "--data",
                    str(data),
                    "--mode",
                    "public",
                    "--no-followers",
                    "--out",
                    str(out),
                    "--today",
                    "2026-09-25",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            html = out.read_text(encoding="utf-8")
            self.assertIn('name="x-dashboard-mode" content="public"', html)
            self.assertNotIn("other_user_00", html)


class TestFreshCloneDefaultBuild(unittest.TestCase):
    def test_empty_clone_builds_public_fixtures(self):
        with tempfile.TemporaryDirectory(prefix="xdash-clone-") as td:
            dest = Path(td) / "repo"
            _copy_fresh_tree(dest)
            self.assertFalse((dest / "test-fixtures" / "data").exists())
            out = dest / "index.html"
            self.assertFalse(out.exists())
            r = subprocess.run(
                [sys.executable, str(dest / "build.py")],
                cwd=dest,
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(out.is_file())
            html = out.read_text(encoding="utf-8")
            self.assertIn("TESTFIXTURE", html)
            self.assertIn('name="x-dashboard-mode" content="public"', html)
            self.assertIn("Demo data", html)
            payload = extract_payload(html)
            self.assertEqual(payload["meta"]["mode"], "public")
            self.assertTrue(payload["meta"].get("demo"))
            self.assertNotIn("peer_alpha", html)
            self.assertNotIn("lowreach_acct", html)
            leak = subprocess.run(
                [
                    sys.executable,
                    str(dest / "scripts" / "check_public_leaks.py"),
                    str(out),
                    str(dest / "test-fixtures" / "data"),
                ],
                cwd=dest,
                capture_output=True,
                text=True,
            )
            self.assertEqual(leak.returncode, 0, leak.stdout + leak.stderr)


class TestPublicBuildAutoLeakCheck(unittest.TestCase):
    def test_public_build_runs_leak_checker(self):
        src = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertIn("enforce_public_leak_check", src)
        self.assertIn("check_public_leaks.py", src)
        netlify = (ROOT / "scripts" / "netlify-build.sh").read_text(encoding="utf-8")
        self.assertIn("check_public_leaks.py", netlify)
        self.assertIn('MODE="${DASHBOARD_MODE:-public}"', netlify)
        self.assertIn("DASHBOARD_USER", netlify)
        self.assertIn("DASHBOARD_PASSWORD", netlify)


class TestNetlifyPrivateRequiresCreds(unittest.TestCase):
    def _prep(self, tmp: Path) -> Path:
        (tmp / "scripts").mkdir()
        shutil.copy(ROOT / "scripts" / "netlify-build.sh", tmp / "scripts" / "netlify-build.sh")
        for sub in ("followers", "posts", "analytics-csv"):
            (tmp / "data" / sub).mkdir(parents=True)
        (tmp / "data" / "analytics-csv" / "x.csv").write_text("id\n1\n", encoding="utf-8")
        return tmp / "scripts" / "netlify-build.sh"

    def test_private_without_creds_refuses(self):
        with tempfile.TemporaryDirectory(prefix="xdash-npriv-") as td:
            tmp = Path(td)
            script = self._prep(tmp)
            env = {**os.environ, "DASHBOARD_MODE": "private"}
            env.pop("DASHBOARD_USER", None)
            env.pop("DASHBOARD_PASSWORD", None)
            r = subprocess.run(["bash", str(script)], cwd=tmp, capture_output=True, text=True, env=env)
            self.assertNotEqual(r.returncode, 0)
            combined = (r.stdout + r.stderr).lower()
            self.assertTrue("dashboard_user" in combined or "password" in combined, combined)
            self.assertFalse((tmp / "dist" / "index.html").exists())

    def test_private_with_only_user_refuses(self):
        with tempfile.TemporaryDirectory(prefix="xdash-nuser-") as td:
            tmp = Path(td)
            script = self._prep(tmp)
            env = {**os.environ, "DASHBOARD_MODE": "private", "DASHBOARD_USER": "owner"}
            env.pop("DASHBOARD_PASSWORD", None)
            r = subprocess.run(["bash", str(script)], cwd=tmp, capture_output=True, text=True, env=env)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("DASHBOARD_PASSWORD", r.stdout + r.stderr)

    def test_garbage_mode_refuses(self):
        with tempfile.TemporaryDirectory(prefix="xdash-ngarb-") as td:
            tmp = Path(td)
            script = self._prep(tmp)
            env = {**os.environ, "DASHBOARD_MODE": "share"}
            r = subprocess.run(["bash", str(script)], cwd=tmp, capture_output=True, text=True, env=env)
            self.assertNotEqual(r.returncode, 0)
            self.assertRegex(r.stdout + r.stderr, r"public or private")


class TestPublicRepoHygiene(unittest.TestCase):
    def test_mit_license(self):
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("MIT License"))

    def test_docs_present(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("What stays private, what is public", readme)
        self.assertIn("assets/og-image.png", readme)
        self.assertIn("python3 build.py", readme)
        self.assertTrue((ROOT / "SECURITY.md").is_file())
        self.assertTrue((ROOT / "CONTRIBUTING.md").is_file())
        self.assertTrue((ROOT / "CODE_OF_CONDUCT.md").is_file())
        self.assertIn("Contributor Covenant", (ROOT / "CODE_OF_CONDUCT.md").read_text(encoding="utf-8"))
        contrib = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertIn("gitleaks", contrib)
        self.assertIn("hooksPath", contrib)
        sec = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        self.assertIn("check_public_leaks.py", sec)

    def test_og_image_present(self):
        og = ROOT / "assets" / "og-image.png"
        self.assertTrue(og.is_file())
        self.assertGreater(og.stat().st_size, 100)

    def test_examples_document_public_default(self):
        cfg = json.loads((ROOT / "data" / "config.example.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg.get("mode"), "public")
        env = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("DASHBOARD_MODE=public", env)
        self.assertIn("DASHBOARD_USER", env)
        self.assertIn("DASHBOARD_PASSWORD", env)

    def test_gitleaks_ci_and_hook(self):
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("gitleaks", ci)
        self.assertIn(".gitleaks.toml", ci)
        self.assertIn("fetch-depth: 0", ci)
        self.assertTrue((ROOT / ".gitleaks.toml").is_file())
        hook = ROOT / ".githooks" / "pre-commit"
        self.assertTrue(hook.is_file())
        self.assertIn("gitleaks protect", hook.read_text(encoding="utf-8"))

    def test_no_internal_briefs(self):
        for rel in (
            "CURSOR-BRIEF.md",
            "TASK.md",
            "AGENT.md",
            "docs/CURSOR-BRIEF.md",
            "docs/TASK.md",
            ".cursor/CURSOR-BRIEF.md",
        ):
            self.assertFalse((ROOT / rel).exists(), rel)

    def test_agent_onboarding_files(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("AGENTS.md", claude)
        self.assertIn("scripts/setup.sh", agents)
        self.assertIn("What stays private", agents)
        self.assertIn("check_public_leaks.py", agents)
        self.assertIn("https://x.ai/bot/GV9QXOW5kYS9o8Rq6MFFi", agents)
        self.assertIn("snapshot-YYYYMMDD-HHMMSS.json", agents)
        self.assertIn("latest.json", agents)
        self.assertIn("data/analytics-csv/", agents)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Get the data collector (Darrel)", readme)
        self.assertIn("Install the X Growth Assistant", readme)
        self.assertIn("https://x.ai/bot/GV9QXOW5kYS9o8Rq6MFFi", readme)
        self.assertIn("snapshot-YYYYMMDD-HHMMSS.json", readme)

    def test_no_hardcoded_local_paths_in_docs(self):
        for rel in (
            "README.md",
            "DEPLOY.md",
            "SECURITY.md",
            "CONTRIBUTING.md",
            "AGENTS.md",
            "CLAUDE.md",
            "CODE_OF_CONDUCT.md",
            "docs/daily-routine.md",
            "docs/PLAN-supabase.md",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("/workspace", text, rel)
            self.assertNotRegex(text, r"/home/[^/\s]+/", rel)
            self.assertNotIn("leinaisystems.com", text, rel)
            self.assertNotIn("leingoedbloed", text, rel)
        leaks = (ROOT / ".gitleaks.toml").read_text(encoding="utf-8")
        self.assertIn("USER:PASS", leaks)


class TestSetupFromFreshClone(unittest.TestCase):
    def test_setup_script_is_wired(self):
        script = (ROOT / "scripts" / "setup.sh").read_text(encoding="utf-8")
        self.assertIn("XDASH_SETUP_SKIP_TESTS", script)
        self.assertIn("unittest discover", script)
        self.assertIn("config.example.json", script)
        self.assertIn(".env.example", script)
        self.assertIn("build.py", script)
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("scripts/setup.sh", makefile)
        r = subprocess.run(["bash", "-n", str(ROOT / "scripts" / "setup.sh")])
        self.assertEqual(r.returncode, 0)

    def test_setup_from_empty_clone(self):
        with tempfile.TemporaryDirectory(prefix="xdash-setup-") as td:
            dest = Path(td) / "repo"
            _copy_fresh_tree(dest)
            env = {**os.environ, "XDASH_SETUP_SKIP_TESTS": "1"}
            r = subprocess.run(
                ["bash", str(dest / "scripts" / "setup.sh")],
                cwd=dest,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue((dest / "data" / "config.json").is_file())
            self.assertTrue((dest / ".env").is_file())
            self.assertTrue((dest / "data" / "followers").is_dir())
            self.assertTrue((dest / "data" / "analytics-csv").is_dir())
            html = (dest / "index.html").read_text(encoding="utf-8")
            self.assertIn("TESTFIXTURE", html)
            self.assertIn('name="x-dashboard-mode" content="public"', html)
            self.assertIn("X Growth Assistant", r.stdout)
            self.assertIn("GV9QXOW5kYS9o8Rq6MFFi", r.stdout)
            cfg = json.loads((dest / "data" / "config.json").read_text(encoding="utf-8"))
            cfg["display_name"] = "Kept By Setup"
            (dest / "data" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
            r2 = subprocess.run(
                ["bash", str(dest / "scripts" / "setup.sh")],
                cwd=dest,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
            self.assertIn("keeping existing data/config.json", r2.stdout)
            kept = json.loads((dest / "data" / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(kept.get("display_name"), "Kept By Setup")
