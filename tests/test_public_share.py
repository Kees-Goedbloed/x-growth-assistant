#!/usr/bin/env python3
"""Public visitor explainer, Open Graph / X cards, and source-repo link."""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import build  # noqa: E402
from test_public import extract_payload, run_build, write_mini_dataset  # noqa: E402

SOURCE = "https://github.com/Kees-Goedbloed/x-growth-assistant"
BANNED_NOTICE = re.compile(r"\b(demo|sample|fake|fictional|preview data)\b", re.I)


class TestVisitorCopy(unittest.TestCase):
    def test_real_dashboard_wording(self):
        html = build.visitor_intro_html("owner", "Ada Lovelace", SOURCE)
        self.assertIn("Ada Lovelace's public X growth dashboard (@owner).", html)
        self.assertIn("Followers, posts, and what works on this account.", html)
        self.assertIn("Other people's handles are stripped.", html)
        self.assertIn(f'href="{SOURCE}"', html)
        self.assertIn("Free source on GitHub", html)
        self.assertIsNone(BANNED_NOTICE.search(html))

    def test_handle_only_and_empty(self):
        self.assertIn("@solo's public X growth dashboard.", build.visitor_intro_html("solo", "", SOURCE))
        empty = build.visitor_intro_html("", "", SOURCE)
        self.assertIn("This public X growth dashboard.", empty)
        self.assertIsNone(BANNED_NOTICE.search(empty))

    def test_og_description_uses_name(self):
        desc = build.public_og_description("owner", "Ada Lovelace")
        self.assertTrue(desc.startswith("Ada Lovelace's public X growth dashboard."))
        self.assertIsNone(BANNED_NOTICE.search(desc))
        self.assertTrue(build.public_og_description("", "").startswith("A public X growth dashboard."))


class TestPublicShareBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory(prefix="xdash-share-")
        cls.tmp = Path(cls._td.name)
        cls.data = cls.tmp / "data"
        write_mini_dataset(cls.data)
        cls.pub = cls.tmp / "public.html"
        cls.priv = cls.tmp / "private.html"
        run_build(cls.data, cls.pub, mode="public")
        run_build(cls.data, cls.priv, mode="private")
        cls.pub_html = cls.pub.read_text(encoding="utf-8")
        cls.priv_html = cls.priv.read_text(encoding="utf-8")
        cls.pub_p = extract_payload(cls.pub_html)

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def test_visitor_intro_public_only(self):
        self.assertIn('id="visitor-intro"', self.pub_html)
        self.assertIn("Demo Owner's public X growth dashboard (@demo_owner).", self.pub_html)
        self.assertIn("Free source on GitHub", self.pub_html)
        self.assertIn(SOURCE, self.pub_html)
        self.assertNotIn("<!--__VISITOR_INTRO__-->", self.pub_html)
        self.assertIn('id="visitor-intro" class="visitor-intro" hidden', self.priv_html)
        self.assertNotIn("public X growth dashboard", self.priv_html)
        self.assertIn('<footer id="dash-footer" hidden>', self.priv_html)
        self.assertNotIn(f'<a href="{SOURCE}" rel="noopener">Free source on GitHub</a>', self.priv_html)

    def test_title_and_og_tags(self):
        self.assertIn("<title>Demo Owner (@demo_owner)</title>", self.pub_html)
        self.assertIn('property="og:title" content="Demo Owner (@demo_owner)"', self.pub_html)
        self.assertIn("Demo Owner's public X growth dashboard.", self.pub_html)
        self.assertIn('name="twitter:card" content="summary_large_image"', self.pub_html)
        self.assertIn('property="og:image" content="https://example.com/assets/og-image.png"', self.pub_html)
        self.assertIn('property="og:image:width" content="1200"', self.pub_html)
        self.assertIn('property="og:image:height" content="630"', self.pub_html)
        self.assertIn('rel="canonical" href="https://example.com"', self.pub_html)
        self.assertNotIn("og:title", self.priv_html)
        self.assertEqual(self.pub_p["meta"].get("source_repo_url"), SOURCE)
        self.assertEqual(self.pub_p["meta"].get("site_url"), "https://example.com")

    def test_footer_visible_on_public(self):
        self.assertIn('<footer id="dash-footer">', self.pub_html)
        self.assertNotIn('<footer id="dash-footer" hidden>', self.pub_html)
        self.assertIn("footer:not([hidden]){display:block}", self.pub_html)

    def test_site_url_env_fallback(self):
        data = self.tmp / "env-data"
        write_mini_dataset(data)
        cfg = (data / "config.json")
        raw = cfg.read_text(encoding="utf-8")
        cfg.write_text(raw.replace("https://example.com", ""), encoding="utf-8")
        out = self.tmp / "env.html"
        env = {**os.environ, "SITE_URL": "https://share.example", "PUBLIC_SITE_URL": "https://ignored.example"}
        env.pop("URL", None)
        run_build(data, out, mode="public", env=env)
        html = out.read_text(encoding="utf-8")
        self.assertIn('property="og:image" content="https://share.example/assets/og-image.png"', html)
        self.assertIn('rel="canonical" href="https://share.example"', html)
        payload = extract_payload(html)
        self.assertEqual(payload["meta"].get("site_url"), "https://share.example")

    def test_config_site_url_wins_over_env(self):
        out = self.tmp / "cfg-wins.html"
        env = {**os.environ, "SITE_URL": "https://env.example"}
        run_build(self.data, out, mode="public", env=env)
        html = out.read_text(encoding="utf-8")
        self.assertIn('content="https://example.com/assets/og-image.png"', html)
        self.assertNotIn("env.example", html)

    def test_relative_og_image_without_site(self):
        data = self.tmp / "nosite"
        write_mini_dataset(data)
        cfg = (data / "config.json")
        cfg.write_text(cfg.read_text(encoding="utf-8").replace("https://example.com", ""), encoding="utf-8")
        out = self.tmp / "nosite.html"
        env = {k: v for k, v in os.environ.items() if k not in ("SITE_URL", "PUBLIC_SITE_URL", "URL")}
        run_build(data, out, mode="public", env=env)
        html = out.read_text(encoding="utf-8")
        self.assertIn('property="og:image" content="/assets/og-image.png"', html)
        self.assertNotIn('rel="canonical"', html)

    def test_source_repo_override(self):
        data = self.tmp / "src-data"
        write_mini_dataset(data)
        cfg_path = data / "config.json"
        import json
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["source_repo_url"] = "https://github.com/example/x-growth-assistant"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        out = self.tmp / "src.html"
        run_build(data, out, mode="public")
        html = out.read_text(encoding="utf-8")
        self.assertIn("https://github.com/example/x-growth-assistant", html)
        self.assertNotIn(SOURCE, html)

    def test_og_image_asset(self):
        og = ROOT / "assets" / "og-image.png"
        self.assertTrue(og.is_file())
        with Image.open(og) as im:
            self.assertEqual(im.size, (1200, 630))
        self.assertGreater(og.stat().st_size, 1000)


class TestPublishSiteUrl(unittest.TestCase):
    def test_publish_exports_public_site_url(self):
        src = (ROOT / "scripts" / "publish.sh").read_text(encoding="utf-8")
        self.assertIn("PUBLIC_SITE_URL", src)
        self.assertIn('export SITE_URL=', src)


if __name__ == "__main__":
    unittest.main()
