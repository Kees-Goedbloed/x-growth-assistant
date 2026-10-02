#!/usr/bin/env python3
"""Smoke tests for the dashboard build (empty data + fixtures + new section)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import repo_guard  # noqa: E402,F401
BASELINE_IDS = (ROOT / "tests" / "baseline_post_ids.txt").read_text().splitlines()


def run_build(data: Path, out: Path, today="2026-09-25"):
    r = subprocess.run(
        [sys.executable, str(ROOT / "build.py"), "--data", str(data),
         "--mode", "private", "--no-followers", "--out", str(out), "--today", today],
        cwd=ROOT, capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise AssertionError(f"build failed\n{r.stdout}\n{r.stderr}")
    return r


def extract_payload(html: str) -> dict:
    blob = html.split('id="dash-data">', 1)[1].split("</script>", 1)[0]
    return json.loads(blob)


class TestEmptyBuild(unittest.TestCase):
    def test_empty_data_succeeds_and_includes_new_section(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "data"
            (data / "followers").mkdir(parents=True)
            (data / "posts").mkdir()
            (data / "analytics-csv").mkdir()
            out = Path(td) / "index.html"
            run_build(data, out)
            html = out.read_text(encoding="utf-8")
            self.assertIn("X growth dashboard", html)
            self.assertIn("What works best", html)
            self.assertIn("Follower goal", html)
            self.assertIn("No goal set (goal_followers / goal_date in data/config.json)", html)
            self.assertIn("Reply ROI by account", html)
            self.assertIn("From profile visit to follower", html)
            self.assertIn('html lang="en"', html)
            self.assertNotIn("TESTFIXTURE", html)
            payload = extract_payload(html)
            self.assertEqual(payload["posts"], [])
            self.assertFalse(payload.get("meta", {}).get("demo"), payload.get("meta"))
            self.assertEqual(payload["meta"]["insights"]["min_n"], 5)
            self.assertEqual(payload["meta"]["insights"]["judge_k"], 3)
            self.assertIsNone(payload["meta"]["goal"]["followers"])
            self.assertIsNone(payload["meta"]["goal"]["date"])
            self.assertEqual(payload["meta"]["roi"]["low_min_replies"], 5)
            self.assertEqual(payload["meta"]["roi"]["low_max_mean_impressions"], 30)


class TestFixtureBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(
            [sys.executable, str(ROOT / "test-fixtures" / "make_fixtures.py")],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        cls._td = tempfile.TemporaryDirectory(prefix="xdash-fixbuild-")
        cls.out = Path(cls._td.name) / "index.test.html"
        run_build(ROOT / "test-fixtures" / "data", cls.out)
        cls.html = cls.out.read_text(encoding="utf-8")
        cls.payload = extract_payload(cls.html)

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def test_marker_and_new_section(self):
        self.assertTrue(self.out.exists())
        self.assertIn("TESTFIXTURE", self.html)
        self.assertTrue(self.payload.get("meta", {}).get("demo"), self.payload.get("meta"))
        self.assertIn("Demo data", self.html)
        self.assertIn('id="demo-badge"', self.html)
        self.assertIn("What works best", self.html)
        self.assertIn("function secBest", self.html)
        self.assertIn("correlation", self.html.lower())
        self.assertIn("too little data", self.html)

    def test_followup_sections_and_medians(self):
        for s in (
            "Reply ROI by account",
            "high effort, low reach",
            "best follower source",
            "From profile visit to follower",
            "Follower goal",
            "No goal set",
            "Median impressions",
            "based on new followers from X analytics",
        ):
            self.assertIn(s, self.html)

    def test_snowflake_time_from_date_only_csv(self):
        import build
        from datetime import datetime
        from zoneinfo import ZoneInfo
        ams = ZoneInfo("Europe/Amsterdam")
        sid = str(build.make_snowflake(datetime(2026, 9, 12, 7, 20, tzinfo=ams)))
        posts = {p["id"]: p for p in self.payload["posts"]}
        self.assertIn(sid, posts)
        viral = posts[sid]
        self.assertEqual(viral["hour"], 7)
        self.assertEqual(viral["local_time"], "07:20")
        self.assertEqual(viral["time_source"], "snowflake")
        mismatch = next(p for p in self.payload["posts"] if "snowflake-mismatch" in (p.get("text") or ""))
        self.assertIsNone(mismatch["hour"])
        self.assertTrue(any("snowflake" in (x.get("msg") or "").lower()
                            for x in self.payload["log"] if x.get("level") == "warn"))

    def test_roi_fixture_accounts(self):
        replies = [p for p in self.payload["posts"]
                   if p.get("type") == "reply" and not p.get("self_reply")]
        by = {}
        for p in replies:
            h = (p.get("in_reply_to_handle") or "").lower()
            by.setdefault(h, []).append(p)
        low = by.get("lowreach_acct") or []
        self.assertGreaterEqual(len(low), 5)
        mean = sum(p["impressions"] for p in low) / len(low)
        self.assertLess(mean, 30)
        self.assertGreaterEqual(len(by.get("gold_source") or []), 3)
        self.assertGreaterEqual(len(by.get("reach_king") or []), 3)
        self.assertIn("lowreach_acct", self.html)
        self.assertIn("gold_source", self.html)

    def test_original_fixture_ids_preserved(self):
        ids = {p["id"] for p in self.payload["posts"]}
        missing = [i for i in BASELINE_IDS if i not in ids]
        self.assertEqual(missing, [], f"original fixture posts lost: {missing[:10]}")
        self.assertGreater(len(ids), len(BASELINE_IDS))

    def test_insights_fields_and_coverage(self):
        posts = self.payload["posts"]
        kinds = {p.get("kind") for p in posts}
        media = {p.get("media_kind") for p in posts}
        lengths = {p.get("length_bucket") for p in posts}
        for k in ("post", "reply", "quote", "repost", "thread"):
            self.assertIn(k, kinds, f"missing kind {k}")
        for m in ("text", "image", "multi_image", "video", "gif", "poll", "link", "article"):
            self.assertIn(m, media, f"missing media {m}")
        for b in ("short", "medium", "long", "long_form"):
            self.assertIn(b, lengths, f"missing length {b}")
        timed = [p for p in posts if p.get("hour") is not None]
        self.assertGreaterEqual(len(timed), 40)
        speeds = {p.get("reply_speed") for p in posts if p.get("reply_speed")}
        self.assertTrue({"15m", "1h", "4h", "later"} <= speeds)
        self.assertTrue(any(p.get("text", "").startswith("TESTFIXTURE-INSIGHTS") or
                            "TESTFIXTURE-INSIGHTS" in (p.get("text") or "") for p in posts))

    def test_cli_has_followers_dir_flags(self):
        src = Path(ROOT / "build.py").read_text(encoding="utf-8")
        self.assertIn("--followers-dir", src)
        self.assertIn("--no-followers", src)


class TestGoalConfig(unittest.TestCase):
    def test_goal_set_renders_status_not_unset_note(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "data"
            (data / "followers").mkdir(parents=True)
            (data / "posts").mkdir()
            (data / "analytics-csv").mkdir()
            for i, (day, n) in enumerate((("2026-09-01", 100), ("2026-09-10", 130), ("2026-09-25", 160))):
                doc = {
                    "account": "demo_owner",
                    "date": day,
                    "captured_at": f"{day}T09:00:00+02:00",
                    "profile_followers": n,
                    "handles": [f"g{i}_{j}" for j in range(n)],
                    "complete": True,
                    "notes": "TESTFIXTURE-GOAL",
                }
                (data / "followers" / f"snapshot-{day}.json").write_text(
                    json.dumps(doc), encoding="utf-8")
            (data / "config.json").write_text(json.dumps({
                "account": "demo_owner",
                "goal_followers": 200,
                "goal_date": "2026-10-25",
                "avatar_lookup": False,
            }), encoding="utf-8")
            out = Path(td) / "index.html"
            run_build(data, out)
            html = out.read_text(encoding="utf-8")
            payload = extract_payload(html)
            self.assertEqual(payload["meta"]["goal"]["followers"], 200)
            self.assertEqual(payload["meta"]["goal"]["date"], "2026-10-25")
            self.assertIn("Follower goal", html)
            self.assertTrue(any(s in html for s in ("on track", "behind", "ahead", "goal reached")))

    def test_sparse_snapshots_fallback_to_analytics_follows(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "data"
            (data / "followers").mkdir(parents=True)
            (data / "posts").mkdir()
            (data / "analytics-csv").mkdir()
            doc = {
                "account": "demo_owner",
                "date": "2026-09-25",
                "captured_at": "2026-09-25T09:00:00+02:00",
                "profile_followers": 80,
                "handles": [f"only_{j}" for j in range(80)],
                "complete": True,
            }
            (data / "followers" / "snapshot-2026-09-25.json").write_text(
                json.dumps(doc), encoding="utf-8")
            posts = [{
                "id": str(1910000000000000000 + i),
                "created_at": f"2026-09-{20+i:02d}T10:00:00+02:00",
                "type": "post",
                "text": f"TESTFIXTURE-GOAL-FALLBACK {i}",
                "impressions": 100,
                "new_follows": 4,
                "profile_visits": 20,
            } for i in range(5)]
            (data / "posts" / "posts.json").write_text(
                json.dumps({"posts": posts}), encoding="utf-8")
            out = Path(td) / "index.html"
            run_build(data, out)
            html = out.read_text(encoding="utf-8")
            self.assertIn("based on new followers from X analytics", html)
            self.assertIn("No goal set", html)


def _media_640(css: str) -> str:
    needle = "@media (max-width:640px)"
    i = css.find(needle)
    if i < 0:
        return ""
    brace = css.find("{", i)
    if brace < 0:
        return ""
    depth = 0
    for j, ch in enumerate(css[brace:], brace):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return css[brace : j + 1]
    return css[brace:]


class TestTemplateMobileCss(unittest.TestCase):
    def test_overflow_guards_present(self):
        t = (ROOT / "template.html").read_text(encoding="utf-8")
        self.assertIn("minmax(min(420px,100%),1fr)", t)
        self.assertIn("minmax(min(180px,100%),1fr)", t)
        self.assertIn("min-width:0", t)
        self.assertIn("svg.ch{width:100%;max-width:100%", t)
        self.assertIn("viewport", t)
        self.assertIn("@media (max-width:640px)", t)
        self.assertIn("custom-range", t)

    def test_mobile_period_bar_is_compact_and_accessible(self):
        t = (ROOT / "template.html").read_text(encoding="utf-8")
        self.assertIn('class="bar-presets"', t)
        self.assertIn('role="group"', t)
        self.assertIn('aria-label="Period"', t)
        self.assertRegex(t, r'<button type="button" data-p="7"')
        self.assertRegex(t, r'<button type="button" data-p="30"')
        self.assertRegex(t, r'<button type="button" data-p="90"')
        self.assertRegex(t, r'<button type="button" data-p="all"')
        self.assertIn("aria-pressed", t)
        self.assertIn("setAttribute('aria-pressed'", t)
        mq = _media_640(t)
        self.assertIn(".bar{position:sticky", mq)
        self.assertNotIn(".bar{position:static", mq)
        self.assertNotRegex(mq, r"\.bar-presets\{[^}]*position:sticky")
        self.assertIn("max-height:56px", mq)
        self.assertIn("overflow-x:hidden", mq)
        self.assertIn("flex-wrap:nowrap", mq)
        tablet = t.split("@media (max-width:1100px) and (min-width:641px)", 1)[-1]
        self.assertIn(".p-short{display:inline}", tablet.replace(" ", "").split("@media", 1)[0])
        self.assertIn("text-overflow:ellipsis", t)
        self.assertIn("confine:true", t)
        self.assertIn("Compare previous", t)
        self.assertIn("theme-toggle", t)
        self.assertIn('class="bar-custom"', t)
        self.assertIn("<summary", t)
        # Custom dates stay in the document but must not sit in the preset row.
        presets_start = t.find('class="bar-presets"')
        presets_end = t.find("</div>", presets_start)
        presets = t[presets_start:presets_end]
        self.assertNotIn("custom-range", presets)
        self.assertNotIn('id="perlabel"', presets)
        self.assertIn("data-p", presets)
        self.assertIn("bar-custom", t)
        custom = t[t.find('class="bar-custom"'): t.find('id="perlabel"')]
        self.assertIn("custom-range", custom)
        self.assertIn("<summary", custom)

    def test_chart_first_kpis_and_short_titles(self):
        t = (ROOT / "template.html").read_text(encoding="utf-8")
        self.assertIn('class="kpis"', t)
        self.assertIn("function kpi(", t)
        self.assertIn("class=\"fold\"", t)
        self.assertIn("<h3>Followers per day</h3>", t)
        self.assertIn("<h3>Posts per day</h3>", t)
        self.assertIn("<h3>Impressions per day</h3>", t)
        self.assertIn("<h3>Replies per day</h3>", t)
        self.assertIn("heatPanel('Best time to post'", t)
        self.assertIn("Not enough data yet", t)
        self.assertNotIn("<h3>Aantal per dag</h3>", t)
        self.assertNotIn("<h3>Weergaven per dag</h3>", t)
        self.assertNotIn("<h3>Volgers per dag</h3>", t)
        self.assertIn("id=\"kpis\"", t)
        mq = _media_640(t)
        self.assertIn("repeat(2,minmax(0,1fr))", mq)

    def test_top_posts_meta_wraps_instead_of_ellipsis(self):
        t = (ROOT / "template.html").read_text(encoding="utf-8")
        self.assertIn("mini-top", t)
        self.assertIn("top-meta", t)
        self.assertIn(".mini-top table{width:100%", t)
        self.assertIn("top-metrics", t)
        self.assertIn("mini-top-metric", t)
        self.assertIn("table-layout:fixed", t)
        self.assertIn(".mini-top .txt .note", t)
        self.assertIn("white-space:normal", t)
        mq = _media_640(t)
        self.assertNotRegex(mq, r"\.mini-top \.txt\{[^}]*max-width:11rem")
        # Title may ellipsis; the grey meta line must not.
        self.assertIn(".mini-top .txt .note,.mini-top .top-meta{white-space:normal", t)
        self.assertIn("overflow:visible", t)
        self.assertIn(".top-metrics{", t)
        self.assertRegex(t, r"\.top-metrics\{[^}]*white-space:nowrap")


class TestPublishScript(unittest.TestCase):
    def test_bash_syntax(self):
        r = subprocess.run(["bash", "-n", str(ROOT / "scripts" / "publish.sh")])
        self.assertEqual(r.returncode, 0)

    def test_origin_urls(self):
        script = ROOT / "scripts" / "publish.sh"
        cases = [
            ("https://github.com/Kees-Goedbloed/x-growth-assistant", True),
            ("https://github.com/Kees-Goedbloed/x-growth-assistant.git", True),
            ("git@github.com:Kees-Goedbloed/x-growth-assistant.git", True),
            ("https://x-access-token:fake@github.com/Kees-Goedbloed/x-growth-assistant", True),
            ("ssh://git@github.com/Kees-Goedbloed/x-growth-assistant.git", True),
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


# User-facing Dutch that must not remain after the English UI switch.
# Data keys (nieuw/terug/ontvolger/mogelijk/berekend/lijst_onvolledig) stay in JS/JSON.
DUTCH_UI_PHRASES = (
    "Volgersdoel",
    "Weergaven per dag",
    "Reacties per dag",
    "Reacties per doelgroep",
    "Reactie-rendement",
    'aria-label="Periode"',
    "correlatie",
    "te weinig data",
    "op schema",
    "doel bereikt",
    "Kies een geldige",
    " t/m ",
    "Toepassen",
    "Volgers per dag",
    "Nog geen doel ingesteld",
    "Mediaan impressies",
    "Van profielbezoek",
    "Wat werkt het best",
    "X-groeidashboard",
    "Geen data",
    "geverifieerd",
    "Bladwijzers",
    "Profielbez.",
    "Linkklikken",
    "Hashtagklikken",
    "Permalinkklikken",
    "veel moeite, weinig bereik",
    "beste volgersbron",
    "Nederlands",
    "Tonen:",
    "Tabellen",
    "Recepten",
    "Vraagteken",
    "Regelafbreking",
    "Tekstkenmerken",
    "Ontvolgers",
    "volgerslijst",
    "waarschijnlijk",
    "onbekend",
    "deze periode",
    "Meldingen",
    "Fout bij renderen",
    "gewogen",
    "hogere mediaan",
    "niet beschikbaar",
    "tijdstip",
    "posttype",
    "Conversie",
    "Bezoeken",
    "Impressies",
    "Gem. ",
    "nl-NL",
    "html lang=\"nl\"",
    "Beste posttijd",
    "Beste reactietijd",
    "Periode:",
    "7 dagen",
    "90 dagen",
    "weggelaten",
    "namen en paden",
)


def _strip_dash_data(html: str) -> str:
    start = html.find('id="dash-data">')
    if start < 0:
        return html
    end = html.find("</script>", start)
    if end < 0:
        return html
    return html[:start] + 'id="dash-data">' + html[end:]


class TestEnglishUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(
            [sys.executable, str(ROOT / "test-fixtures" / "make_fixtures.py")],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        cls.td = tempfile.TemporaryDirectory(prefix="xdash-en-")
        out = Path(cls.td.name)
        cls.private = out / "index.private.html"
        cls.public = out / "index.public.html"
        for path, mode in ((cls.private, "private"), (cls.public, "public")):
            r = subprocess.run(
                [sys.executable, str(ROOT / "build.py"),
                 "--data", str(ROOT / "test-fixtures" / "data"),
                 "--mode", mode, "--out", str(path), "--today", "2026-09-25"],
                cwd=ROOT, capture_output=True, text=True,
            )
            if r.returncode != 0:
                raise AssertionError(f"build {mode} failed\n{r.stdout}\n{r.stderr}")
        cls.priv_html = cls.private.read_text(encoding="utf-8")
        cls.pub_html = cls.public.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    def test_html_lang_en_and_en_us_formatters(self):
        for html, mode in ((self.priv_html, "private"), (self.pub_html, "public")):
            self.assertIn('<html lang="en"', html, mode)
            self.assertIn("Intl.NumberFormat('en-US')", html, mode)
            self.assertIn("toLocaleString('en-US'", html, mode)
            self.assertNotIn("nl-NL", html, mode)

    def test_no_leftover_dutch_ui_in_private_or_public(self):
        for html, mode in ((self.priv_html, "private"), (self.pub_html, "public")):
            body = _strip_dash_data(html)
            hits = [p for p in DUTCH_UI_PHRASES if p.lower() in body.lower()]
            self.assertEqual(hits, [], f"{mode} leftover Dutch UI: {hits}")

    def test_public_build_log_is_english(self):
        payload = extract_payload(self.pub_html)
        msgs = " ".join(x.get("msg") or "" for x in payload.get("log") or [])
        self.assertIn("omitted", msgs.lower())
        self.assertNotIn("weggelaten", msgs)
        self.assertNotIn("namen en paden", msgs)

    def test_unavailable_reason_stored_keys_unchanged(self):
        payload = extract_payload(self.priv_html)
        reasons = [u.get("reason") for u in (payload.get("followers") or {}).get("unavailable") or []]
        self.assertIn("geschorst", reasons)

    def test_private_left_list_log_maps_keys(self):
        payload = extract_payload(self.priv_html)
        msgs = " ".join(x.get("msg") or "" for x in payload.get("log") or [])
        self.assertIn("left list:", msgs)
        self.assertNotIn("ontvolger", msgs)
        self.assertNotIn("'verwijderd'", msgs)
        self.assertRegex(msgs, r"unfollowed")


class TestStatusDisplayLabels(unittest.TestCase):
    def test_left_list_log_uses_english_keys(self):
        import build
        shown = build.format_left_list({"ontvolger": 3, "verwijderd": 1, "mogelijk": 1, "capture_gat": 1})
        self.assertIn("unfollowed", shown)
        self.assertIn("deleted", shown)
        self.assertNotIn("ontvolger", shown)
        self.assertNotIn("verwijderd", shown)

    def test_public_log_line_in_builder_is_english(self):
        src = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertIn("Public build: handles, names, and paths omitted.", src)
        self.assertNotIn("weggelaten", src)


class TestDemoBuildFlag(unittest.TestCase):
    def test_is_demo_build_helpers(self):
        import build
        self.assertTrue(build.is_demo_build({"demo": True}, "/tmp/real-looking"))
        self.assertTrue(build.is_demo_build({}, str(ROOT / "test-fixtures" / "data")))
        self.assertTrue(build.is_demo_build({}, "/tmp/x", [{"text": "hello TESTFIXTURE"}]))
        self.assertFalse(build.is_demo_build({"display_name": "Demo Owner"}, "/tmp/owner-data"))
        self.assertFalse(build.is_demo_build({}, "/tmp/owner-data", [{"text": "hello"}]))

    def test_real_data_build_keeps_status_urls_and_hides_badge(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "data"
            (data / "followers").mkdir(parents=True)
            (data / "posts").mkdir()
            (data / "analytics-csv").mkdir()
            (data / "config.json").write_text(json.dumps({
                "account": "real_owner",
                "display_name": "Real Owner",
            }), encoding="utf-8")
            (data / "posts" / "posts.json").write_text(json.dumps({
                "posts": [{
                    "id": "1746849708241846272",
                    "text": "a real post",
                    "impressions": 10,
                    "created_at": "2026-09-24T12:00:00+02:00",
                    "type": "post",
                    "url": "https://x.com/real_owner/status/1746849708241846272",
                }]
            }), encoding="utf-8")
            out = Path(td) / "index.html"
            run_build(data, out)
            html = out.read_text(encoding="utf-8")
            payload = extract_payload(html)
            self.assertFalse(payload["meta"].get("demo"), payload["meta"])
            self.assertIn("IS_DEMO?'#'", html.replace(" ", ""))
            self.assertIn("https://x.com/real_owner/status/1746849708241846272", json.dumps(payload["posts"]))
