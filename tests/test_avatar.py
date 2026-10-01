#!/usr/bin/env python3
"""Owner avatar: build-time fetch, keep-on-failure, initials fallback."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import repo_guard  # noqa: E402,F401
import build as B  # noqa: E402
from tiny_avatar import fixture_avatar_bytes, fixture_jpeg_bytes  # noqa: E402

TEMPLATE = (ROOT / "template.html").read_text(encoding="utf-8")
TINY = fixture_avatar_bytes()
TINY_JPG = fixture_jpeg_bytes()
TMP_ASSETS = Path("/tmp/assets")


def _cleanup_tmp_assets():
    if not TMP_ASSETS.is_dir():
        return
    for name in ("avatar.jpg", "avatar.jpeg", "avatar.webp", "avatar.png",
                 "avatar.jpg.tmp", "avatar.png.tmp"):
        p = TMP_ASSETS / name
        if p.is_file():
            p.unlink()
    try:
        TMP_ASSETS.rmdir()
    except OSError:
        pass


def _env_without_avatar_cache():
    env = os.environ.copy()
    env.pop("XDASH_AVATAR_CACHE", None)
    return env


def _extract_fn(src: str, name: str) -> str:
    needle = f"function {name}"
    i = src.find(needle)
    if i < 0:
        raise AssertionError(f"missing function {name}")
    brace = src.find("{", i)
    depth = 0
    for j, ch in enumerate(src[brace:], brace):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[i : j + 1]
    raise AssertionError(f"unclosed function {name}")


class TestAvatarSourceGuards(unittest.TestCase):
    def test_template_never_hotlinks_x_or_other_avatars(self):
        self.assertNotIn("pbs.twimg.com", TEMPLATE)
        self.assertNotIn("unavatar.io", TEMPLATE)
        self.assertNotIn("twimg.com", TEMPLATE)
        self.assertIn("function ownerAvatarHtml", TEMPLATE)
        self.assertIn("function ownerInitial", TEMPLATE)
        self.assertIn("function avatarImgFallback", TEMPLATE)
        self.assertIn("window.avatarImgFallback", TEMPLATE)
        self.assertIn("onerror=\"avatarImgFallback(this)\"", TEMPLATE)
        self.assertIn('id="dash-av"', TEMPLATE)
        self.assertIn("ownerAvatarHtml('pcard-av')", TEMPLATE)
        card = _extract_fn(TEMPLATE, "postCard")
        self.assertIn("ownerAvatarHtml", card)
        self.assertNotIn("in_reply_to", _extract_fn(TEMPLATE, "ownerAvatarHtml"))
        self.assertNotIn("api.fxtwitter.com", TEMPLATE)

    def test_builder_uses_owner_handle_only(self):
        src = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertIn("unavatar.io/x/{handle}", src)
        self.assertIn("api.fxtwitter.com/{handle}", src)
        self.assertIn("profile_images", src)
        self.assertIn("_400x400", src)
        self.assertIn("place_owner_avatar", src)
        self.assertIn("AVATAR_FILENAME", src)
        self.assertIn("sniff_image_ext", src)
        self.assertIn("avatar_cache_dir", src)
        self.assertIn("XDASH_AVATAR_CACHE", src)


class TestAvatarResolveAndFetch(unittest.TestCase):
    def setUp(self):
        self._cache_env = os.environ.pop("XDASH_AVATAR_CACHE", None)
        _cleanup_tmp_assets()

    def tearDown(self):
        _cleanup_tmp_assets()
        if self._cache_env is not None:
            os.environ["XDASH_AVATAR_CACHE"] = self._cache_env
        else:
            os.environ.pop("XDASH_AVATAR_CACHE", None)

    def test_upgrade_pbs_to_400(self):
        raw = "https://pbs.twimg.com/profile_images/1/foo_normal.jpg"
        self.assertEqual(
            B.upgrade_pbs_avatar(raw),
            "https://pbs.twimg.com/profile_images/1/foo_400x400.jpg",
        )
        self.assertEqual(
            B.upgrade_pbs_avatar("https://pbs.twimg.com/profile_images/1/foo_200x200.png"),
            "https://pbs.twimg.com/profile_images/1/foo_400x400.png",
        )
        self.assertEqual(
            B.upgrade_pbs_avatar("https://pbs.twimg.com/profile_images/1/foo_bigger.jpg"),
            "https://pbs.twimg.com/profile_images/1/foo_400x400.jpg",
        )

    def test_sniff_image_ext_from_magic_and_content_type(self):
        self.assertEqual(B.sniff_image_ext(TINY), ".png")
        self.assertEqual(B.sniff_image_ext(TINY_JPG), ".jpg")
        self.assertEqual(B.sniff_image_ext(b"xxxx", "image/png"), ".png")
        self.assertEqual(B.sniff_image_ext(b"xxxx", "image/jpeg"), ".jpg")

    def test_config_override_wins_then_export_then_fxtwitter(self):
        url, src = B.resolve_avatar_url({"profile_image_url": "/tmp/a.jpg"}, "demo_owner", [])
        self.assertEqual(url, "/tmp/a.jpg")
        self.assertEqual(src, "config")
        http = "https://pbs.twimg.com/profile_images/1/foo_normal.jpg"
        url, src = B.resolve_avatar_url({"profile_image_url": http}, "demo_owner", [])
        self.assertEqual(url, "https://pbs.twimg.com/profile_images/1/foo_400x400.jpg")
        self.assertEqual(src, "config")
        posts = [{"profile_image_url": "https://pbs.twimg.com/profile_images/9/x_normal.jpg"}]
        url, src = B.resolve_avatar_url({}, "demo_owner", posts)
        self.assertEqual(url, "https://pbs.twimg.com/profile_images/9/x_400x400.jpg")
        self.assertEqual(src, "export")
        url, src = B.resolve_avatar_url({}, "demo_owner", [])
        self.assertEqual(url, "https://api.fxtwitter.com/demo_owner")
        self.assertEqual(src, "fxtwitter")
        cands = B.avatar_candidates({}, "demo_owner", [])
        self.assertEqual([s for _, s in cands], ["fxtwitter", "unavatar"])
        url, src = B.resolve_avatar_url({"avatar_lookup": False}, "demo_owner", [])
        self.assertEqual(url, "")
        url, src = B.resolve_avatar_url({}, "", [])
        self.assertEqual(url, "")

    def test_export_scan_ignores_non_pbs_fields(self):
        posts = [{"media_url": "https://pbs.twimg.com/media/abc.jpg", "url": "https://x.com/other/status/1"}]
        self.assertEqual(B.export_owner_avatar_url(posts, []), "")

    def test_export_scan_reads_snapshot_owner_url(self):
        snaps = [{"profile_image_url_https": "https://pbs.twimg.com/profile_images/2/me_normal.jpg"}]
        self.assertEqual(
            B.export_owner_avatar_url([], snaps),
            "https://pbs.twimg.com/profile_images/2/me_400x400.jpg",
        )

    def test_non_image_response_is_missing(self):
        with tempfile.TemporaryDirectory() as td:
            path, how = B.place_owner_avatar(
                {"profile_image_url": "https://example.test/me.jpg"},
                "demo_owner",
                [],
                str(Path(td) / "index.html"),
                fetch_fn=lambda u: b"<html>nope</html>",
            )
            self.assertIsNone(path)
            self.assertEqual(how, "missing")

    def test_fetch_success_writes_file(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "index.html"
            seen = []

            def fetch(url):
                seen.append(url)
                return TINY

            path, how = B.place_owner_avatar(
                {"profile_image_url": "https://example.test/me.jpg"},
                "demo_owner",
                [],
                str(out),
                fetch_fn=fetch,
            )
            self.assertEqual(seen, ["https://example.test/me.jpg"])
            self.assertEqual(how, "config")
            self.assertTrue(path and Path(path).is_file())
            self.assertEqual(Path(path).read_bytes(), TINY)
            self.assertTrue(B.looks_like_image(TINY))

    def test_fetch_failure_keeps_previous(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "assets" / "avatar.jpg"
            dest.parent.mkdir()
            dest.write_bytes(TINY)

            def fetch(_url):
                raise OSError("offline")

            path, how = B.place_owner_avatar(
                {"profile_image_url": "https://example.test/me.jpg"},
                "demo_owner",
                [],
                str(Path(td) / "index.html"),
                fetch_fn=fetch,
            )
            self.assertEqual(how, "kept")
            self.assertEqual(Path(path).read_bytes(), TINY)
            self.assertTrue(str(path).startswith(td))

    def test_fetch_failure_without_previous_is_missing(self):
        with tempfile.TemporaryDirectory() as td:
            path, how = B.place_owner_avatar(
                {"profile_image_url": "https://example.test/me.jpg"},
                "demo_owner",
                [],
                str(Path(td) / "index.html"),
                fetch_fn=lambda u: (_ for _ in ()).throw(OSError("offline")),
            )
            self.assertIsNone(path)
            self.assertEqual(how, "missing")
            self.assertFalse((Path(td) / "assets" / "avatar.jpg").exists())
            self.assertFalse((Path(td) / "assets" / "avatar.png").exists())

    def test_local_override_and_build_never_fails(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "data"
            (data / "followers").mkdir(parents=True)
            (data / "posts").mkdir()
            (data / "analytics-csv").mkdir()
            (data / "avatar.jpg").write_bytes(TINY)
            (data / "config.json").write_text(json.dumps({
                "account": "demo_owner",
                "display_name": "Demo Owner",
                "profile_image_url": "avatar.jpg",
            }), encoding="utf-8")
            out = Path(td) / "index.html"
            r = subprocess.run(
                [sys.executable, str(ROOT / "build.py"), "--data", str(data),
                 "--no-followers", "--out", str(out), "--today", "2026-09-25"],
                cwd=ROOT, capture_output=True, text=True, env=_env_without_avatar_cache(),
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            dest = Path(td) / "assets" / "avatar.png"
            self.assertTrue(dest.is_file(), "PNG fixture must be saved as .png")
            self.assertFalse((Path(td) / "assets" / "avatar.jpg").exists())
            html = out.read_text(encoding="utf-8")
            self.assertIn('"avatar": "assets/avatar.png"', html)
            self.assertNotIn("unavatar.io", html)
            self.assertNotIn("pbs.twimg.com", html)
            self.assertNotIn("api.fxtwitter.com", html)

    def test_build_survives_http_error_and_uses_initials(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "data"
            (data / "followers").mkdir(parents=True)
            (data / "posts").mkdir()
            (data / "analytics-csv").mkdir()
            (data / "config.json").write_text(json.dumps({
                "account": "demo_owner",
                "display_name": "Demo Owner",
                "profile_image_url": "https://127.0.0.1:1/nope.jpg",
            }), encoding="utf-8")
            out = Path(td) / "index.html"
            r = subprocess.run(
                [sys.executable, str(ROOT / "build.py"), "--data", str(data),
                 "--no-followers", "--out", str(out), "--today", "2026-09-25"],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            html = out.read_text(encoding="utf-8")
            payload = json.loads(html.split('id="dash-data">', 1)[1].split("</script>", 1)[0])
            self.assertEqual(payload["meta"]["avatar"], "")
            self.assertNotIn("unavatar.io", html)
            self.assertNotIn("pbs.twimg.com", html)

    def test_urlopen_success_via_patch(self):
        with tempfile.TemporaryDirectory() as td:
            class Resp:
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

                def read(self, _n=None):
                    return TINY

            with patch("build.urllib.request.urlopen", return_value=Resp()):
                path, how = B.place_owner_avatar(
                    {},
                    "demo_owner",
                    [],
                    str(Path(td) / "index.html"),
                )
            self.assertEqual(how, "fxtwitter")
            self.assertEqual(Path(path).read_bytes(), TINY)
            self.assertTrue(str(path).endswith(".png"))

    def test_fxtwitter_json_upgrades_and_fetches_image(self):
        with tempfile.TemporaryDirectory() as td:
            seen = []

            def fetch(url):
                seen.append(url)
                if "api.fxtwitter.com" in url:
                    return json.dumps({
                        "user": {
                            "avatar_url": "https://pbs.twimg.com/profile_images/1/foo_normal.jpg",
                        }
                    }).encode()
                return TINY

            path, how = B.place_owner_avatar(
                {},
                "demo_owner",
                [],
                str(Path(td) / "index.html"),
                fetch_fn=fetch,
                today="2026-09-25",
            )
            self.assertEqual(how, "fxtwitter")
            self.assertEqual(seen[0], "https://api.fxtwitter.com/demo_owner")
            self.assertEqual(seen[1], "https://pbs.twimg.com/profile_images/1/foo_400x400.jpg")
            self.assertTrue(str(path).endswith(".png"))
            self.assertEqual(Path(path).read_bytes(), TINY)

    def test_fxtwitter_failure_falls_back_to_unavatar(self):
        with tempfile.TemporaryDirectory() as td:
            seen = []

            def fetch(url):
                seen.append(url)
                if "fxtwitter" in url:
                    raise OSError("429")
                return TINY_JPG

            path, how = B.place_owner_avatar(
                {},
                "demo_owner",
                [],
                str(Path(td) / "index.html"),
                fetch_fn=fetch,
                today="2026-09-25",
            )
            self.assertEqual(how, "unavatar")
            self.assertEqual(seen[0], "https://api.fxtwitter.com/demo_owner")
            self.assertEqual(seen[1], "https://unavatar.io/x/demo_owner")
            self.assertTrue(str(path).endswith(".jpg"))
            self.assertEqual(Path(path).read_bytes(), TINY_JPG)

    def test_persistent_cache_skips_http_refetch_same_day(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            cache = td / "cache"
            out = td / "build" / "index.html"
            out.parent.mkdir()
            seen = []

            def fetch(url):
                seen.append(url)
                return TINY

            cfg = {"avatar_cache": str(cache)}
            path1, how1 = B.place_owner_avatar(
                cfg, "demo_owner", [], str(out), fetch_fn=fetch, today="2026-09-25",
            )
            self.assertEqual(how1, "fxtwitter")
            self.assertTrue((cache / "avatar.png").is_file())
            meta = json.loads((cache / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["fetched_on"], "2026-09-25")
            self.assertEqual(meta["source"], "fxtwitter")
            seen.clear()

            def boom(url):
                seen.append(url)
                raise OSError("should not refetch")

            path2, how2 = B.place_owner_avatar(
                cfg, "demo_owner", [], str(out), fetch_fn=boom, today="2026-09-25",
            )
            self.assertEqual(how2, "cache")
            self.assertEqual(seen, [])
            self.assertEqual(Path(path2).read_bytes(), TINY)
            self.assertTrue(str(path2).endswith(".png"))

    def test_stale_cache_refetches_next_day_and_kept_on_fail(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            cache = td / "cache"
            out = td / "index.html"
            cfg = {"avatar_cache": str(cache)}
            B.place_owner_avatar(
                cfg, "demo_owner", [], str(out),
                fetch_fn=lambda u: TINY, today="2026-09-25",
            )
            seen = []

            def fetch_jpg(url):
                seen.append(url)
                return TINY_JPG

            path, how = B.place_owner_avatar(
                cfg, "demo_owner", [], str(out),
                fetch_fn=fetch_jpg, today="2026-09-26",
            )
            self.assertEqual(how, "fxtwitter")
            self.assertTrue(seen)
            self.assertTrue(str(path).endswith(".jpg"))
            self.assertEqual(Path(path).read_bytes(), TINY_JPG)
            meta = json.loads((cache / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["fetched_on"], "2026-09-26")

            path2, how2 = B.place_owner_avatar(
                cfg, "demo_owner", [], str(out),
                fetch_fn=lambda u: (_ for _ in ()).throw(OSError("offline")),
                today="2026-09-27",
            )
            self.assertEqual(how2, "kept")
            self.assertEqual(Path(path2).read_bytes(), TINY_JPG)

    def test_cache_survives_fresh_temp_publish_dir(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            data = td / "data"
            cache = data / ".avatar-cache"
            first = td / "pub1"
            second = td / "pub2"
            first.mkdir()
            second.mkdir()
            cfg = {"avatar_cache": str(cache)}
            B.place_owner_avatar(
                cfg, "demo_owner", [], str(first / "index.html"),
                fetch_fn=lambda u: TINY, today="2026-09-25", data_dir=str(data),
            )
            path, how = B.place_owner_avatar(
                cfg, "demo_owner", [], str(second / "index.html"),
                fetch_fn=lambda u: (_ for _ in ()).throw(OSError("429")),
                today="2026-09-25", data_dir=str(data),
            )
            self.assertEqual(how, "cache")
            self.assertTrue((second / "assets" / "avatar.png").is_file())
            self.assertEqual((second / "assets" / "avatar.png").read_bytes(), TINY)

    def test_does_not_write_tmp_assets_leftover(self):
        _cleanup_tmp_assets()
        self.assertFalse((TMP_ASSETS / "avatar.jpg").exists())
        self.assertFalse((TMP_ASSETS / "avatar.png").exists())
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "index.html"
            path, how = B.place_owner_avatar(
                {"profile_image_url": "https://example.test/me.jpg"},
                "demo_owner",
                [],
                str(out),
                fetch_fn=lambda u: TINY,
                today="2026-09-25",
            )
            self.assertEqual(how, "config")
            self.assertTrue(str(path).startswith(td))
            self.assertTrue((Path(td) / "assets" / "avatar.png").is_file())
        self.assertFalse((TMP_ASSETS / "avatar.jpg").exists())
        self.assertFalse((TMP_ASSETS / "avatar.png").exists())
        if TMP_ASSETS.exists():
            self.assertFalse(any(TMP_ASSETS.glob("avatar.*")))
