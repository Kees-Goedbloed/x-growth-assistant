#!/usr/bin/env python3
"""Public vs private build mode: payload strip, aggregates, leak checker."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Generic only: do not encode specific host, company, or product names.
ABS_HOME_RE = re.compile(r"/home/[^/]+/")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import repo_guard  # noqa: E402,F401
from tiny_avatar import fixture_avatar_bytes  # noqa: E402


def run_build(data: Path, out: Path, today="2026-09-25", mode="private", extra=None):
    cmd = [sys.executable, str(ROOT / "build.py"), "--data", str(data),
           "--mode", mode, "--out", str(out), "--today", today]
    if extra:
        cmd.extend(["--followers-dir", str(extra)])
    else:
        cmd.append("--no-followers")
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"build failed mode={mode}\n{r.stdout}\n{r.stderr}")
    return r


def extract_payload(html: str) -> dict:
    blob = html.split('id="dash-data">', 1)[1].split("</script>", 1)[0]
    return json.loads(blob)


def write_mini_dataset(data: Path, with_targets=True):
    (data / "followers").mkdir(parents=True)
    (data / "posts").mkdir()
    (data / "analytics-csv").mkdir()
    handles = [f"other_user_{i:02d}" for i in range(12)] + ["gone_acct"]
    following = handles[:8] + ["celeb_one"]
    snap = {
        "account": "demo_owner",
        "date": "2026-09-20",
        "captured_at": "2026-09-20T09:00:00+02:00",
        "profile_followers": len(handles),
        "profile_following": len(following),
        "handles": handles,
        "following_handles": following,
        "following_complete": True,
        "complete": True,
        "unavailable": [{"handle": "gone_acct", "reason": "geschorst"}],
        "notes": "TESTFIXTURE-PUBLIC-MINI",
    }
    (data / "followers" / "snapshot-2026-09-20.json").write_text(
        json.dumps(snap), encoding="utf-8")
    snap2 = dict(snap)
    snap2.update({
        "date": "2026-09-25",
        "captured_at": "2026-09-25T09:00:00+02:00",
        "handles": handles[1:] + ["fresh_acct"],
        "profile_followers": len(handles),
    })
    (data / "followers" / "snapshot-2026-09-25.json").write_text(
        json.dumps(snap2), encoding="utf-8")
    posts = []
    pid = 1920000000000000000
    # 6 accounts in the 1k–10k bucket, 2 replies each.
    mid = [f"bucket_mid_{i}" for i in range(6)]
    tiny = ["bucket_tiny_a", "bucket_tiny_b"]
    for h in mid:
        for j in range(2):
            pid += 1
            posts.append({
                "id": str(pid),
                "url": f"https://x.com/demo_owner/status/{pid}",
                "created_at": f"2026-09-22T10:{j:02d}:00+02:00",
                "type": "reply",
                "media": "text",
                "in_reply_to_handle": h,
                "text": f"@{h} hello from @demo_owner vs @stranger_zz",
                "impressions": 100 + j,
                "likes": 2,
                "profile_visits": 4,
                "new_follows": 1,
            })
    for h in tiny:
        pid += 1
        posts.append({
            "id": str(pid),
            "created_at": "2026-09-22T11:00:00+02:00",
            "type": "reply",
            "in_reply_to_handle": h,
            "text": f"@{h} tiny bucket",
            "impressions": 10,
            "profile_visits": 1,
            "new_follows": 0,
        })
    pid += 1
    posts.append({
        "id": str(pid),
        "created_at": "2026-09-22T12:00:00+02:00",
        "type": "post",
        "text": "Own post mentioning @stranger_zz and @demo_owner",
        "impressions": 500,
        "profile_visits": 20,
        "new_follows": 2,
        "url": f"https://x.com/demo_owner/status/{pid}",
    })
    (data / "posts" / "posts.json").write_text(
        json.dumps({"posts": posts}), encoding="utf-8")
    (data / "avatar.jpg").write_bytes(fixture_avatar_bytes())
    (data / "config.json").write_text(json.dumps({
        "account": "demo_owner",
        "display_name": "Demo Owner",
        "site_url": "https://example.com",
        "repo_url": "https://github.com/example/x-growth-assistant",
        "lang": "en",
        "csv_timezone": "UTC",
        "og_image_url": "",
        "profile_image_url": "avatar.jpg",
    }), encoding="utf-8")
    if with_targets:
        targets = {h: 4000 for h in mid}
        targets.update({h: 50 for h in tiny})
        (data / "target_accounts.json").write_text(
            json.dumps(targets), encoding="utf-8")


class TestPublicVsPrivateMini(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory(prefix="xdash-pub-")
        cls.tmp = Path(cls._td.name)
        cls.data = cls.tmp / "data"
        write_mini_dataset(cls.data, with_targets=True)
        cls.priv = cls.tmp / "private.html"
        cls.pub = cls.tmp / "public.html"
        run_build(cls.data, cls.priv, mode="private")
        run_build(cls.data, cls.pub, mode="public")
        cls.priv_html = cls.priv.read_text(encoding="utf-8")
        cls.pub_html = cls.pub.read_text(encoding="utf-8")
        cls.priv_p = extract_payload(cls.priv_html)
        cls.pub_p = extract_payload(cls.pub_html)

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def test_meta_mode(self):
        self.assertEqual(self.priv_p["meta"]["mode"], "private")
        self.assertEqual(self.pub_p["meta"]["mode"], "public")
        self.assertIn('name="x-dashboard-mode" content="private"', self.priv_html)
        self.assertIn('name="x-dashboard-mode" content="public"', self.pub_html)

    def test_default_mode_is_public(self):
        out = self.tmp / "default.html"
        r = subprocess.run(
            [sys.executable, str(ROOT / "build.py"), "--data", str(self.data),
             "--no-followers", "--out", str(out), "--today", "2026-09-25"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        html = out.read_text(encoding="utf-8")
        self.assertIn('content="public"', html)
        self.assertNotIn("other_user_00", html)

    def test_private_keeps_handles(self):
        for h in ("other_user_00", "bucket_mid_0", "stranger_zz", "gone_acct", "fresh_acct"):
            self.assertIn(h, self.priv_html.lower() if False else self.priv_html)
        self.assertTrue(any(p.get("in_reply_to_handle") for p in self.priv_p["posts"]))
        self.assertTrue(self.priv_p["followers"]["new"] or self.priv_p["followers"]["lost"])

    def test_public_strips_lists_and_reply_handles(self):
        fol = self.pub_p["followers"]
        self.assertEqual(fol.get("new") or [], [])
        self.assertEqual(fol.get("lost") or [], [])
        self.assertEqual(fol.get("unavailable") or [], [])
        self.assertEqual(fol.get("verified_unfollowers") or [], [])
        self.assertIsNone(fol.get("not_following_back"))
        for p in self.pub_p["posts"]:
            self.assertNotIn("in_reply_to_handle", p)
            self.assertNotIn("in_reply_to_created_at", p)
            self.assertNotIn("profile_image_url", p)
            self.assertNotIn("profile_image_url_https", p)

    def test_owner_avatar_is_local_asset(self):
        self.assertEqual(self.priv_p["meta"].get("avatar"), "assets/avatar.png")
        self.assertEqual(self.pub_p["meta"].get("avatar"), "assets/avatar.png")
        self.assertTrue((self.tmp / "assets" / "avatar.png").is_file())
        self.assertFalse((self.tmp / "assets" / "avatar.jpg").exists())
        self.assertNotIn("unavatar.io", self.pub_html)
        self.assertNotIn("pbs.twimg.com", self.pub_html)
        self.assertNotIn("api.fxtwitter.com", self.pub_html)

    def test_public_redacts_mentions_keeps_owner(self):
        texts = " ".join(p.get("text") or "" for p in self.pub_p["posts"])
        self.assertNotIn("@stranger_zz", texts)
        self.assertNotIn("@bucket_mid_0", texts)
        self.assertIn("@demo_owner", texts)
        self.assertIn("@…", texts)
        self.assertTrue(any("demo_owner/status/" in (p.get("url") or "") for p in self.pub_p["posts"]))

    def test_public_omits_paths(self):
        self.assertIsNone(self.pub_p["meta"].get("data_dir"))
        self.assertIsNone(self.pub_p["meta"].get("followers_dir"))
        self.assertNotIn(str(self.data), self.pub_html)

    def test_public_keeps_growth_and_goal_keys(self):
        self.assertTrue(self.pub_p["followers"]["snapshots"])
        self.assertIn("goal", self.pub_p["meta"])
        self.assertIn("Follower goal", self.pub_html)
        self.assertIn("What works best", self.pub_html)
        self.assertIn("From profile visit to follower", self.pub_html)

    def test_size_buckets_hide_small_groups(self):
        buckets = self.pub_p.get("reply_buckets") or []
        labels = {b["label"] for b in buckets}
        self.assertIn("1k–10k", labels)
        for b in buckets:
            self.assertGreaterEqual(b["n_accounts"], 5)
            self.assertNotIn("handle", b)
        # tiny <1k group has only 2 accounts → hidden
        self.assertNotIn("<1k", labels)
        self.assertEqual(self.pub_p["meta"].get("reply_bucket_kind"), "size")

    def test_og_and_robots_sidecars(self):
        self.assertIn("og:title", self.pub_html)
        self.assertIn("twitter:card", self.pub_html)
        self.assertIn("summary_large_image", self.pub_html)
        self.assertIn('rel="canonical"', self.pub_html)
        self.assertNotIn("og:title", self.priv_html)
        pdir = self.tmp / "pdist"
        pdir.mkdir(exist_ok=True)
        run_build(self.data, pdir / "index.html", mode="private")
        pr = (pdir / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("Disallow: /", pr)
        ph = (pdir / "_headers").read_text(encoding="utf-8")
        self.assertIn("noindex", ph)
        self.assertIn("private, no-store", ph)
        udir = self.tmp / "udist"
        udir.mkdir(exist_ok=True)
        run_build(self.data, udir / "index.html", mode="public")
        uh = (udir / "_headers").read_text(encoding="utf-8")
        self.assertNotIn("noindex", uh)
        ur = (udir / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("Allow: /", ur)
        self.assertNotIn("Disallow: /", ur)

    def test_leak_script_blocks_private_html(self):
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_public_leaks.py"),
             str(self.priv), str(self.data)],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_leak_script_allows_public_html(self):
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_public_leaks.py"),
             str(self.pub), str(self.data)],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_header_footer_from_config(self):
        self.assertIn("Demo Owner", self.pub_html)
        self.assertIn("https://github.com/example/x-growth-assistant", self.pub_html)
        self.assertIn("Built with x-growth-assistant", self.pub_html)

    def test_public_ui_hides_private_tables(self):
        self.assertIn("Replies by audience", self.pub_html)
        self.assertFalse(any(p.get("in_reply_to_handle") for p in self.pub_p["posts"]))


class TestFrequencyFallback(unittest.TestCase):
    def test_groups_by_reply_frequency_without_targets(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "data"
            write_mini_dataset(data, with_targets=False)
            # extra 5 accounts with a single reply each → 1x bucket (>=5 accounts)
            posts = json.loads((data / "posts" / "posts.json").read_text())
            pid = 1930000000000000000
            extra = []
            for i in range(6):
                pid += 1
                extra.append({
                    "id": str(pid),
                    "created_at": f"2026-09-23T10:{i:02d}:00+02:00",
                    "type": "reply",
                    "in_reply_to_handle": f"once_acct_{i}",
                    "text": f"@once_acct_{i} once",
                    "impressions": 80,
                    "profile_visits": 2,
                    "new_follows": 0,
                })
            posts["posts"].extend(extra)
            (data / "posts" / "posts.json").write_text(json.dumps(posts), encoding="utf-8")
            out = Path(td) / "public.html"
            run_build(data, out, mode="public")
            payload = extract_payload(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["meta"].get("reply_bucket_kind"), "frequency")
            labels = {b["label"] for b in payload.get("reply_buckets") or []}
            self.assertIn("1×", labels)
            html = out.read_text(encoding="utf-8")
            self.assertNotIn("once_acct_0", html)
            self.assertNotIn("bucket_mid_0", html)


class TestFollowersDirFlags(unittest.TestCase):
    def test_followers_dir_flags(self):
        src = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertIn("--followers-dir", src)
        self.assertIn("--no-followers", src)
        self.assertNotRegex(src, ABS_HOME_RE)

    def test_empty_account_default(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "data"
            (data / "followers").mkdir(parents=True)
            (data / "posts").mkdir()
            (data / "analytics-csv").mkdir()
            out = Path(td) / "index.html"
            run_build(data, out, mode="private")
            html = out.read_text(encoding="utf-8")
            payload = extract_payload(html)
            self.assertEqual(payload["meta"].get("account") or "", "")
            self.assertNotRegex(html, ABS_HOME_RE)
            self.assertIn('id="dash-footer" hidden', html)
            src = (ROOT / "build.py").read_text(encoding="utf-8")
            self.assertRegex(src, r'norm_handle\(cfg\.get\("account"\)\) or ""')


class TestNetlifyBuildFailClosed(unittest.TestCase):
    def test_empty_data_refuses(self):
        import shutil
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / "scripts").mkdir()
            shutil.copy(
                ROOT / "scripts" / "netlify-build.sh",
                tmp / "scripts" / "netlify-build.sh",
            )
            for sub in ("followers", "posts", "analytics-csv"):
                (tmp / "data" / sub).mkdir(parents=True)
            r = subprocess.run(
                ["bash", str(tmp / "scripts" / "netlify-build.sh")],
                cwd=tmp, capture_output=True, text=True,
            )
            self.assertNotEqual(r.returncode, 0)
            combined = r.stdout + r.stderr
            self.assertTrue("geen" in combined.lower() or "no real" in combined.lower()
                            or "weiger" in combined.lower() or "refuse" in combined.lower(),
                            combined)
            self.assertFalse((tmp / "dist").exists())


class TestFullFixturePublicLeak(unittest.TestCase):
    def test_fixture_public_build_has_no_other_handles(self):
        subprocess.run(
            [sys.executable, str(ROOT / "test-fixtures" / "make_fixtures.py")],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        data = ROOT / "test-fixtures" / "data"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "index.html"
            run_build(data, out, mode="public")
            html = out.read_text(encoding="utf-8")
            payload = extract_payload(html)
            self.assertEqual(payload["meta"]["mode"], "public")
            self.assertIn("1k–10k", html)
            self.assertIn("10k–100k", html)
            self.assertNotIn("<1k", {b["label"] for b in payload.get("reply_buckets") or []})
            r = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "check_public_leaks.py"),
                 str(out), str(data)],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            priv = Path(td) / "private.html"
            run_build(data, priv, mode="private")
            priv_html = priv.read_text(encoding="utf-8")
            self.assertIn("peer_alpha", priv_html)
            self.assertIn("lowreach_acct", priv_html)
            self.assertNotIn("peer_alpha", html)
            self.assertNotIn("lowreach_acct", html)
