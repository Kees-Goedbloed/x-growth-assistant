#!/usr/bin/env python3
"""check_public_leaks.py: handle-context matching, not bare words."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import repo_guard  # noqa: E402,F401
import check_public_leaks as cpl  # noqa: E402

PLAIN = (
    "I asked Grok bot how Karpathy would design this with OpenAI and Google"
)


def write_data(data: Path, extra_handles=None, owner="demo_owner", allow=None):
    (data / "followers").mkdir(parents=True, exist_ok=True)
    (data / "posts").mkdir(exist_ok=True)
    (data / "analytics-csv").mkdir(exist_ok=True)
    handles = ["someone", "bot", "Google", "graphify", "grok", "karpathy", "OpenAI"]
    if extra_handles:
        handles.extend(extra_handles)
    (data / "target_accounts.json").write_text(
        json.dumps({h: 1000 for h in handles}), encoding="utf-8")
    (data / "config.json").write_text(json.dumps({
        "account": owner,
        "display_name": "Demo Owner",
    }), encoding="utf-8")
    (data / "posts" / "posts.json").write_text(json.dumps({
        "posts": [{
            "id": "1",
            "text": PLAIN,
            "in_reply_to_handle": "someone",
        }]
    }), encoding="utf-8")
    if allow is not None:
        (data / "public_allowlist.json").write_text(
            json.dumps(allow), encoding="utf-8")


def run_cli(html: Path, data: Path):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_public_leaks.py"),
         str(html), str(data)],
        cwd=ROOT, capture_output=True, text=True,
    )


class TestLeakContextMatching(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.data = self.tmp / "data"
        write_data(self.data)
        self.html = self.tmp / "page.html"

    def test_fails_on_at_mention(self):
        self.html.write_text("<p>see @someone later</p>", encoding="utf-8")
        r = run_cli(self.html, self.data)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("someone", (r.stderr + r.stdout).lower())

    def test_fails_on_x_com_url(self):
        self.html.write_text(
            '<a href="https://x.com/someone/status/1">post</a>', encoding="utf-8")
        r = run_cli(self.html, self.data)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("someone", (r.stderr + r.stdout).lower())

    def test_fails_on_twitter_com_url(self):
        self.html.write_text(
            '<a href="https://twitter.com/someone">p</a>', encoding="utf-8")
        r = run_cli(self.html, self.data)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_fails_on_handle_in_reply_target_json(self):
        blob = json.dumps({"posts": [{"in_reply_to_handle": "someone", "text": PLAIN}]})
        self.html.write_text(
            f'<script id="dash-data" type="application/json">{blob}</script>',
            encoding="utf-8")
        r = run_cli(self.html, self.data)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("someone", (r.stderr + r.stdout).lower())

    def test_passes_on_plain_words_that_equal_handles(self):
        self.html.write_text(f"<article><p>{PLAIN}</p></article>", encoding="utf-8")
        r = run_cli(self.html, self.data)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_plain_words_inside_embedded_post_text_pass(self):
        blob = json.dumps({
            "meta": {"account": "demo_owner"},
            "posts": [{"text": PLAIN, "id": "1"}],
        })
        self.html.write_text(
            f'<script id="dash-data" type="application/json">{blob}</script>',
            encoding="utf-8")
        r = run_cli(self.html, self.data)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_never_flags_owner_handle(self):
        self.html.write_text(
            "<p>@demo_owner https://x.com/demo_owner</p>"
            + json.dumps({"account": "demo_owner"}),
            encoding="utf-8")
        r = run_cli(self.html, self.data)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_allowlist_skips_explicit_handles(self):
        write_data(self.data, allow={"handles": ["someone"]})
        self.html.write_text("<p>@someone is allowed</p>", encoding="utf-8")
        r = run_cli(self.html, self.data)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_data_attribute_is_handle_context(self):
        self.html.write_text(
            '<div data-handle="someone"></div>', encoding="utf-8")
        r = run_cli(self.html, self.data)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_css_at_media_is_not_a_handle_mention(self):
        write_data(self.data, extra_handles=["media"])
        css = (
            "<style>@media (max-width:640px){body{margin:0}}"
            "@supports (display:grid){.g{display:grid}}</style>"
            f"<p>{PLAIN}</p>"
        )
        self.html.write_text(css, encoding="utf-8")
        r = run_cli(self.html, self.data)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_find_leaks_helper_plain_vs_mention(self):
        handles, owner = cpl.collect_handles(str(self.data))
        self.assertIn("someone", {h.lower() for h in handles})
        plain = cpl.find_leaks(f"<p>{PLAIN}</p>", handles, owner=owner)
        self.assertEqual(plain, [])
        mention = cpl.find_leaks("<p>@someone</p>", handles, owner=owner)
        self.assertTrue(any(h.lower() == "someone" for h in mention))
