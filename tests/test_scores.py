#!/usr/bin/env python3
"""Hand-computed fixtures for value score, consistency, streak, and traffic lights."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import repo_guard  # noqa: E402,F401

TEMPLATE = (ROOT / "template.html").read_text(encoding="utf-8")


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


def _node_bin():
    return shutil.which("node") or shutil.which("nodejs")


class TestScoreSourceGuards(unittest.TestCase):
    def test_score_config_block_and_formula_copy(self):
        self.assertIn("const SCORE=", TEMPLATE)
        self.assertIn("viewsW:0.4", TEMPLATE.replace(" ", ""))
        self.assertIn("engW:0.6", TEMPLATE.replace(" ", ""))
        self.assertIn("likes:1", TEMPLATE.replace(" ", ""))
        self.assertIn("bookmarks:2", TEMPLATE.replace(" ", ""))
        self.assertIn("reposts:3", TEMPLATE.replace(" ", ""))
        self.assertIn("quotes:3", TEMPLATE.replace(" ", ""))
        self.assertIn("replies:4", TEMPLATE.replace(" ", ""))
        self.assertIn("lights:{green:75,yellow:50,orange:25}", TEMPLATE.replace(" ", ""))
        self.assertIn("function valueScore", TEMPLATE)
        self.assertIn("function consistencyScore", TEMPLATE)
        self.assertIn("function currentStreak", TEMPLATE)
        self.assertIn("function trafficLightScore", TEMPLATE)
        self.assertIn("function trafficLightDelta", TEMPLATE)
        self.assertIn("function postCard", TEMPLATE)
        self.assertIn("function replyLine", TEMPLATE)
        self.assertIn("Replying to a post", _extract_fn(TEMPLATE, "replyLine"))
        self.assertIn("function postsExplorer", TEMPLATE)
        self.assertIn("function miniTop", TEMPLATE)
        self.assertIn("Show more", TEMPLATE)
        self.assertIn("Load more", TEMPLATE)
        self.assertIn("target=\"_blank\"", _extract_fn(TEMPLATE, "postCard"))
        tip = _extract_fn(TEMPLATE, "valueFormulaTip")
        self.assertIn("percentile rank", tip)
        self.assertIn("likes", tip)

    def test_canvas_uses_cards_not_table(self):
        tops = _extract_fn(TEMPLATE, "canvasTops")
        self.assertIn("postCard", tops)
        self.assertIn("post-grid", tops)
        self.assertNotIn("postsExplorer", tops)
        self.assertNotIn("miniTop", tops)

    def test_round6_helpers_and_call_sites(self):
        for name in (
            "lastDataDate",
            "lastCompleteDay",
            "isIncompleteDay",
            "completeDays",
            "pluralize",
            "dayScoreStrip",
        ):
            self.assertIn(f"function {name}", TEMPLATE)
        last = _extract_fn(TEMPLATE, "lastDataDate")
        self.assertNotIn("generated_at", last)
        self.assertIn("local_date", last)
        cap = _extract_fn(TEMPLATE, "lastCompleteDay")
        self.assertIn("TODAY", cap)
        kpis = _extract_fn(TEMPLATE, "canvasKpis")
        self.assertIn("completeDays", kpis)
        self.assertIn("isIncompleteDay", kpis)
        self.assertIn("cons-panel", kpis)
        posts = _extract_fn(TEMPLATE, "canvasPosts")
        self.assertIn("dayScoreStrip", posts)
        self.assertNotIn("dayColor", posts)
        replies = _extract_fn(TEMPLATE, "canvasRepliesSent")
        self.assertIn("dayScoreStrip", replies)
        self.assertNotIn("dayColor", replies)
        tops = _extract_fn(TEMPLATE, "canvasTops")
        self.assertIn("post-split", tops)
        self.assertIn("Top posts", tops)
        self.assertIn("Top replies", tops)
        cal = _extract_fn(TEMPLATE, "consistencyCalendar")
        self.assertIn("is-incomplete", cal)
        self.assertIn("cal-months", cal)
        self.assertIn("data-date", cal)
        card = _extract_fn(TEMPLATE, "postCard")
        self.assertIn("pluralize", card)
        self.assertIn("data-kind", card)

    def test_round8_helpers_and_call_sites(self):
        for name in ("kpiCompleteRange", "streakDays", "calendarDays", "avatarImgFallback"):
            self.assertIn(f"function {name}", TEMPLATE)
        self.assertIn("constCAL_WEEKS_MAX=10", TEMPLATE.replace(" ", ""))
        self.assertIn("function latestFollowers", TEMPLATE)
        self.assertIn("function weekdaySummary", TEMPLATE)
        self.assertIn("window.avatarImgFallback", TEMPLATE)
        self.assertIn("--split-n", TEMPLATE)
        self.assertIn(".split-h{font-size:13px;margin:0 0 10px", TEMPLATE)
        self.assertIn(".post-split .split-h{margin:0}", TEMPLATE)
        self.assertIn("IS_DEMO", TEMPLATE)
        self.assertIn("Demo data", TEMPLATE)
        self.assertIn("IS_DEMO?'#'", _extract_fn(TEMPLATE, "postCard").replace(" ", ""))
        kpis = _extract_fn(TEMPLATE, "canvasKpis")
        self.assertIn("latestFollowers", kpis)
        self.assertIn("weekdaySummary", kpis)
        self.assertIn("kpiCompleteRange", kpis)
        self.assertIn("streakDays", kpis)
        self.assertIn("isIncompleteDay", kpis)
        self.assertIn("'—'", kpis)
        self.assertIn("currentStreak(streakDays())", kpis.replace(" ", ""))
        tip = _extract_fn(TEMPLATE, "consistencyFormulaTip")
        self.assertIn("not clipped by the selected period", tip)
        cal = _extract_fn(TEMPLATE, "consistencyCalendar")
        self.assertIn("calendarDays", cal)
        self.assertIn("is-in-range", cal)
        self.assertIn("is-out", cal)
        self.assertIn("minDataDate", cal)
        self.assertIn("display:contents", TEMPLATE)
        self.assertIn("subgrid", TEMPLATE)
        empty = _extract_fn(TEMPLATE, "consistencyScore")
        self.assertIn("return null", empty)


@unittest.skipUnless(_node_bin(), "node is required to execute extracted score helpers")
class TestScoreNodeFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = _node_bin()
        score_line = TEMPLATE[TEMPLATE.find("const SCORE=") : TEMPLATE.find("function scoreGoals")]
        bits = [
            "const TODAY='2026-09-25';",
            "const META={goal:{posts_per_day:2,replies_per_day:10}};",
            "const POSTS=[];",
            _extract_fn(TEMPLATE, "addDays"),
            score_line,
            _extract_fn(TEMPLATE, "scoreGoals"),
            _extract_fn(TEMPLATE, "messageKind"),
            _extract_fn(TEMPLATE, "weightedEng"),
            _extract_fn(TEMPLATE, "percentileRank"),
            _extract_fn(TEMPLATE, "valueScore"),
            _extract_fn(TEMPLATE, "dayActivity"),
            _extract_fn(TEMPLATE, "dayScore"),
            _extract_fn(TEMPLATE, "consistencyScore"),
            _extract_fn(TEMPLATE, "currentStreak"),
            _extract_fn(TEMPLATE, "trafficLightScore"),
            _extract_fn(TEMPLATE, "trafficLightDelta"),
            r"""
const peers = [
  {id:'a', type:'post', impressions:10, likes:1, bookmarks:0, reposts:0, quotes:0, replies:0},
  {id:'b', type:'post', impressions:20, likes:2, bookmarks:0, reposts:0, quotes:0, replies:0},
  {id:'c', type:'post', impressions:30, likes:3, bookmarks:0, reposts:0, quotes:0, replies:0}
];
const scores = peers.map(p => valueScore(p, peers));
const reply = {id:'r', type:'reply', impressions:30, likes:3, bookmarks:0, reposts:0, quotes:0, replies:0};
const replyVsPosts = valueScore(reply, peers);
const w = weightedEng({likes:1, bookmarks:1, reposts:1, quotes:1, replies:1});
const days = ['2026-09-23','2026-09-24','2026-09-25'];
const posts = [
  {local_date:'2026-09-23', type:'post'}, {local_date:'2026-09-23', type:'post'},
  {local_date:'2026-09-23', type:'reply'}, {local_date:'2026-09-23', type:'reply'},
  {local_date:'2026-09-23', type:'reply'}, {local_date:'2026-09-23', type:'reply'},
  {local_date:'2026-09-23', type:'reply'}, {local_date:'2026-09-23', type:'reply'},
  {local_date:'2026-09-23', type:'reply'}, {local_date:'2026-09-23', type:'reply'},
  {local_date:'2026-09-23', type:'reply'}, {local_date:'2026-09-23', type:'reply'},
  {local_date:'2026-09-24', type:'post'},
  {local_date:'2026-09-24', type:'reply'}, {local_date:'2026-09-24', type:'reply'},
  {local_date:'2026-09-24', type:'reply'}, {local_date:'2026-09-24', type:'reply'},
  {local_date:'2026-09-24', type:'reply'},
  {local_date:'2026-09-25', type:'post'}, {local_date:'2026-09-25', type:'post'},
  {local_date:'2026-09-25', type:'quote'},
  {local_date:'2026-09-25', type:'reply'}, {local_date:'2026-09-25', type:'reply'},
  {local_date:'2026-09-25', type:'reply'}, {local_date:'2026-09-25', type:'reply'},
  {local_date:'2026-09-25', type:'reply'}, {local_date:'2026-09-25', type:'reply'},
  {local_date:'2026-09-25', type:'reply'}, {local_date:'2026-09-25', type:'reply'},
  {local_date:'2026-09-25', type:'reply'}, {local_date:'2026-09-25', type:'reply'}
];
const ds = days.map(d => dayScore(d, posts));
const cons = consistencyScore(days, posts);
const streakFull = currentStreak(days, posts);
const streakBroken = currentStreak(days, posts.filter(p => p.local_date !== '2026-09-25' || p.type !== 'reply').concat(
  {local_date:'2026-09-25', type:'post'}
));
const out = {
  scores,
  rankA: percentileRank(10, [10,20,30]),
  rankB: percentileRank(20, [10,20,30]),
  rankC: percentileRank(30, [10,20,30]),
  replyVsPosts,
  weighted: w,
  ds,
  cons,
  streakFull,
  streakBroken,
  tl75: trafficLightScore(75),
  tl74: trafficLightScore(74),
  tl50: trafficLightScore(50),
  tl49: trafficLightScore(49),
  tl25: trafficLightScore(25),
  tl24: trafficLightScore(24),
  d10: trafficLightDelta(0.10),
  d099: trafficLightDelta(0.099),
  dNeg10: trafficLightDelta(-0.10),
  dNeg101: trafficLightDelta(-0.101),
  dNeg25: trafficLightDelta(-0.25),
  dNeg251: trafficLightDelta(-0.251)
};
console.log(JSON.stringify(out));
""",
        ]
        r = subprocess.run(
            [cls.node, "-e", "\n".join(bits)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise AssertionError(f"node score helpers failed\n{r.stdout}\n{r.stderr}")
        cls.out = json.loads(r.stdout.strip().splitlines()[-1])

    def test_percentile_and_value_score_hand_computed(self):
        self.assertAlmostEqual(self.out["rankA"], 1 / 6, places=8)
        self.assertAlmostEqual(self.out["rankB"], 0.5, places=8)
        self.assertAlmostEqual(self.out["rankC"], 5 / 6, places=8)
        self.assertAlmostEqual(self.out["scores"][0], 100 / 6, places=6)
        self.assertAlmostEqual(self.out["scores"][1], 50, places=6)
        self.assertAlmostEqual(self.out["scores"][2], 100 * 5 / 6, places=6)
        self.assertEqual(self.out["weighted"], 1 + 2 + 3 + 3 + 4)
        self.assertAlmostEqual(self.out["replyVsPosts"], 50, places=6)

    def test_consistency_and_streak_hand_computed(self):
        # Sep 23: 2 posts / 2 + 10 replies / 10 → 1.0
        # Sep 24: 1/2 + 5/10 → 0.4*0.5 + 0.6*0.5 = 0.5
        # Sep 25: 3 posts capped at 1 + 10 replies → 1.0
        self.assertAlmostEqual(self.out["ds"][0], 1.0, places=8)
        self.assertAlmostEqual(self.out["ds"][1], 0.5, places=8)
        self.assertAlmostEqual(self.out["ds"][2], 1.0, places=8)
        self.assertAlmostEqual(self.out["cons"], 250 / 3, places=6)
        self.assertEqual(self.out["streakFull"], 1)
        self.assertEqual(self.out["streakBroken"], 0)

    def test_traffic_light_thresholds(self):
        self.assertEqual(self.out["tl75"], "green")
        self.assertEqual(self.out["tl74"], "yellow")
        self.assertEqual(self.out["tl50"], "yellow")
        self.assertEqual(self.out["tl49"], "orange")
        self.assertEqual(self.out["tl25"], "orange")
        self.assertEqual(self.out["tl24"], "red")
        self.assertEqual(self.out["d10"], "green")
        self.assertEqual(self.out["d099"], "yellow")
        self.assertEqual(self.out["dNeg10"], "yellow")
        self.assertEqual(self.out["dNeg101"], "orange")
        self.assertEqual(self.out["dNeg25"], "orange")
        self.assertEqual(self.out["dNeg251"], "red")


@unittest.skipUnless(_node_bin(), "node is required to execute extracted score helpers")
class TestRound6IncompleteAndPlural(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = _node_bin()
        score_line = TEMPLATE[TEMPLATE.find("const SCORE=") : TEMPLATE.find("function scoreGoals")]
        bits = [
            "const TODAY='2026-09-25';",
            "const META={goal:{posts_per_day:2,replies_per_day:10}};",
            "const F={snapshots:[{date:'2026-09-24'}]};",
            "const POSTS=[];",
            _extract_fn(TEMPLATE, "addDays"),
            score_line,
            _extract_fn(TEMPLATE, "scoreGoals"),
            _extract_fn(TEMPLATE, "dayActivity"),
            _extract_fn(TEMPLATE, "dayScore"),
            _extract_fn(TEMPLATE, "consistencyScore"),
            _extract_fn(TEMPLATE, "currentStreak"),
            _extract_fn(TEMPLATE, "lastDataDate"),
            _extract_fn(TEMPLATE, "lastCompleteDay"),
            _extract_fn(TEMPLATE, "isIncompleteDay"),
            _extract_fn(TEMPLATE, "completeDays"),
            _extract_fn(TEMPLATE, "pluralize"),
            r"""
function fillDay(d){
  const a=[];
  for(let i=0;i<2;i++) a.push({local_date:d,type:'post'});
  for(let i=0;i<10;i++) a.push({local_date:d,type:'reply'});
  return a;
}
POSTS.push(...fillDay('2026-09-23'), ...fillDay('2026-09-24'));
const days=['2026-09-23','2026-09-24','2026-09-25'];
const done=completeDays(days);
const cap=lastCompleteDay();
const last=lastDataDate();
const F2={snapshots:[{date:'2026-09-23'}]};
const POSTS23=fillDay('2026-09-23');
function lastDataDateAlt(){let m='';for(const s of F2.snapshots){if(s&&s.date&&(!m||s.date>m))m=s.date;}for(const p of POSTS23){if(p&&p.local_date&&(!m||p.local_date>m))m=p.local_date;}return m||'';}
function lastCompleteDayAlt(){const last=lastDataDateAlt();const yest=addDays(TODAY,-1);if(!last)return yest;return last<yest?last:yest;}
const todayFilled=fillDay('2026-09-25');
const Ftoday={snapshots:[{date:'2026-09-25'}]};
function lastDataDateToday(){let m='';for(const s of Ftoday.snapshots){if(s&&s.date&&(!m||s.date>m))m=s.date;}for(const p of todayFilled){if(p&&p.local_date&&(!m||p.local_date>m))m=p.local_date;}return m||'';}
function lastCompleteDayToday(){const last=lastDataDateToday();const yest=addDays(TODAY,-1);if(!last)return yest;return last<yest?last:yest;}
const out={
  last, cap,
  todayIncomplete: isIncompleteDay('2026-09-25'),
  yestIncomplete: isIncompleteDay('2026-09-24'),
  done,
  cons: consistencyScore(done, POSTS),
  streak: currentStreak(done, POSTS),
  streakIfIncludeToday: currentStreak(days, POSTS),
  gapLast: lastDataDateAlt(),
  gapCap: lastCompleteDayAlt(),
  gap24: lastCompleteDayAlt() < '2026-09-24',
  todayHasDataCap: lastCompleteDayToday(),
  p0: pluralize(0,'reply'),
  p1r: pluralize(1,'reply'),
  p2r: pluralize(2,'reply'),
  p1v: pluralize(1,'view'),
  p2v: pluralize(2,'view'),
  p1l: pluralize(1,'like'),
  p1rp: pluralize(1,'repost'),
  p1p: pluralize(1,'post'),
  p1d: pluralize(1,'day'),
  p2d: pluralize(2,'day'),
  p1custom: pluralize(1,'box','boxes'),
  p2custom: pluralize(2,'box','boxes')
};
console.log(JSON.stringify(out));
""",
        ]
        r = subprocess.run(
            [cls.node, "-e", "\n".join(bits)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise AssertionError(f"node round6 helpers failed\n{r.stdout}\n{r.stderr}")
        cls.out = json.loads(r.stdout.strip().splitlines()[-1])

    def test_incomplete_days_excluded_when_last_data_is_yesterday(self):
        self.assertEqual(self.out["last"], "2026-09-24")
        self.assertEqual(self.out["cap"], "2026-09-24")
        self.assertTrue(self.out["todayIncomplete"])
        self.assertFalse(self.out["yestIncomplete"])
        self.assertEqual(self.out["done"], ["2026-09-23", "2026-09-24"])
        self.assertAlmostEqual(self.out["cons"], 100.0, places=6)
        self.assertEqual(self.out["streak"], 2)
        self.assertEqual(self.out["streakIfIncludeToday"], 0)
        self.assertEqual(self.out["gapLast"], "2026-09-23")
        self.assertEqual(self.out["gapCap"], "2026-09-23")
        self.assertTrue(self.out["gap24"])
        self.assertEqual(self.out["todayHasDataCap"], "2026-09-24")

    def test_pluralize_singular_and_plural(self):
        self.assertEqual(self.out["p0"], "replies")
        self.assertEqual(self.out["p1r"], "reply")
        self.assertEqual(self.out["p2r"], "replies")
        self.assertEqual(self.out["p1v"], "view")
        self.assertEqual(self.out["p2v"], "views")
        self.assertEqual(self.out["p1l"], "like")
        self.assertEqual(self.out["p1rp"], "repost")
        self.assertEqual(self.out["p1p"], "post")
        self.assertEqual(self.out["p1d"], "day")
        self.assertEqual(self.out["p2d"], "days")
        self.assertEqual(self.out["p1custom"], "box")
        self.assertEqual(self.out["p2custom"], "boxes")


@unittest.skipUnless(_node_bin(), "node is required to execute extracted score helpers")
class TestRound8StreakRangeAndCalendar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = _node_bin()
        score_line = TEMPLATE[TEMPLATE.find("const SCORE=") : TEMPLATE.find("function scoreGoals")]
        bits = [
            "const TODAY='2026-09-25';",
            "const META={goal:{posts_per_day:2,replies_per_day:10}};",
            "let state={start:'2026-08-27',end:'2026-09-25',preset:'30'};",
            "const F={snapshots:[{date:'2026-08-20'},{date:'2026-09-24'}]};",
            "const POSTS=[];",
            _extract_fn(TEMPLATE, "addDays"),
            _extract_fn(TEMPLATE, "dayList"),
            _extract_fn(TEMPLATE, "wdOf"),
            score_line,
            _extract_fn(TEMPLATE, "scoreGoals"),
            _extract_fn(TEMPLATE, "dayActivity"),
            _extract_fn(TEMPLATE, "dayScore"),
            _extract_fn(TEMPLATE, "consistencyScore"),
            _extract_fn(TEMPLATE, "currentStreak"),
            _extract_fn(TEMPLATE, "lastDataDate"),
            _extract_fn(TEMPLATE, "lastCompleteDay"),
            _extract_fn(TEMPLATE, "isIncompleteDay"),
            _extract_fn(TEMPLATE, "completeDays"),
            _extract_fn(TEMPLATE, "minDataDate"),
            _extract_fn(TEMPLATE, "kpiCompleteRange"),
            _extract_fn(TEMPLATE, "streakDays"),
            "const CAL_WEEKS_MAX=10;",
            _extract_fn(TEMPLATE, "calendarDays"),
            r"""
function fillDay(d){
  const a=[];
  for(let i=0;i<2;i++) a.push({local_date:d,type:'post'});
  for(let i=0;i<10;i++) a.push({local_date:d,type:'reply'});
  return a;
}
for(let d='2026-09-10'; d<='2026-09-24'; d=addDays(d,1)) POSTS.push(...fillDay(d));
function streakViaPeriod(){return currentStreak(completeDays(dayList(state.start,state.end)));}
state.start='2026-09-19'; state.end='2026-09-25'; state.preset='7';
const streak7=currentStreak(streakDays());
const clipped7=streakViaPeriod();
const days7=streakDays();
state.start='2026-08-27'; state.end='2026-09-25'; state.preset='30';
const streak30=currentStreak(streakDays());
const clipped30=streakViaPeriod();
const days30=streakDays();
const todayOnly=kpiCompleteRange('2026-09-25','2026-09-25');
const emptyCons=consistencyScore([]);
const cal=calendarDays();
const out={
  cap: lastCompleteDay(),
  min: minDataDate(),
  streak7, streak30, clipped7, clipped30,
  days7Last: days7[days7.length-1]||null,
  days30Last: days30[days30.length-1]||null,
  days7HasToday: days7.includes('2026-09-25'),
  daysEqual: JSON.stringify(days7)===JSON.stringify(days30),
  todayDays: todayOnly.days,
  emptyCons,
  calLen: cal.length,
  calFirst: cal[0],
  calLast: cal[cal.length-1],
  weeks: Math.round(cal.length/7),
  maxW: typeof CAL_WEEKS_MAX==='undefined'?10:CAL_WEEKS_MAX
};
console.log(JSON.stringify(out));
""",
        ]
        r = subprocess.run(
            [cls.node, "-e", "\n".join(bits)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise AssertionError(f"node round8 helpers failed\n{r.stdout}\n{r.stderr}")
        cls.out = json.loads(r.stdout.strip().splitlines()[-1])

    def test_streak_is_not_clipped_by_selected_period(self):
        self.assertEqual(self.out["cap"], "2026-09-24")
        self.assertEqual(self.out["streak7"], self.out["streak30"])
        self.assertGreaterEqual(self.out["streak7"], 15)
        self.assertEqual(self.out["clipped7"], 6)
        self.assertGreater(self.out["clipped30"], self.out["clipped7"])
        self.assertTrue(self.out["daysEqual"])
        self.assertEqual(self.out["days7Last"], "2026-09-24")
        self.assertEqual(self.out["days30Last"], "2026-09-24")
        self.assertFalse(self.out["days7HasToday"])

    def test_empty_complete_range_and_calendar_span(self):
        self.assertEqual(self.out["todayDays"], [])
        self.assertIsNone(self.out["emptyCons"])
        self.assertLessEqual(self.out["weeks"], 10)
        self.assertGreaterEqual(self.out["weeks"], 4)
        self.assertEqual(self.out["calFirst"], "2026-08-17")
        self.assertEqual(self.out["calLast"], "2026-09-27")
        self.assertEqual(self.out["maxW"], 10)


@unittest.skipUnless(_node_bin(), "node is required to execute extracted score helpers")
class TestRound9FollowersAndCalendar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = _node_bin()
        bits = [
            "const TODAY='2026-09-25';",
            "let state={start:'2026-08-27',end:'2026-09-25',preset:'30'};",
            "const S=[{date:'2026-09-23',followers_count:120},{date:'2026-09-24',followers_count:128},{date:'2026-09-25',followers_count:133}];",
            "const F={snapshots:S};",
            "const POSTS=[];",
            _extract_fn(TEMPLATE, "addDays"),
            _extract_fn(TEMPLATE, "dayList"),
            _extract_fn(TEMPLATE, "wdOf"),
            _extract_fn(TEMPLATE, "minDataDate"),
            _extract_fn(TEMPLATE, "snapOnOrBefore"),
            _extract_fn(TEMPLATE, "latestFollowers"),
            "const CAL_WEEKS_MAX=10;",
            _extract_fn(TEMPLATE, "calendarDays"),
            r"""
const lastSnap=S[S.length-1].followers_count;
const yest=S.find(s=>s.date==='2026-09-24').followers_count;
const cal=calendarDays();
const out={
  latest: latestFollowers(state.end),
  latestToday: latestFollowers('2026-09-25'),
  latestYest: latestFollowers('2026-09-24'),
  lastSnap, yest,
  calFirst: cal[0],
  calWeeks: Math.round(cal.length/7),
  startsOnMonday: cal[0] && ((new Date(cal[0]+'T00:00:00Z').getUTCDay()+6)%7)===0
};
console.log(JSON.stringify(out));
""",
        ]
        r = subprocess.run(
            [cls.node, "-e", "\n".join(bits)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise AssertionError(f"node round9 helpers failed\n{r.stdout}\n{r.stderr}")
        cls.out = json.loads(r.stdout.strip().splitlines()[-1])

    def test_followers_kpi_uses_latest_snapshot_including_today(self):
        self.assertEqual(self.out["latest"], 133)
        self.assertEqual(self.out["latestToday"], 133)
        self.assertEqual(self.out["lastSnap"], 133)
        self.assertEqual(self.out["latestYest"], 128)
        self.assertNotEqual(self.out["latest"], self.out["yest"])

    def test_calendar_starts_at_first_data_week_and_caps(self):
        self.assertLessEqual(self.out["calWeeks"], 10)
        self.assertTrue(self.out["startsOnMonday"])
        self.assertGreaterEqual(self.out["calFirst"], "2026-09-21")
