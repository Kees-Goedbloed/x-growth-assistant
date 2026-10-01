#!/usr/bin/env python3
"""Snowflake timestamps, goal parsing, and ROI constants (build.py)."""
import os
import sys
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))
import repo_guard  # noqa: E402,F401

import build

AMS = ZoneInfo("Europe/Amsterdam")


class TestSnowflakeRoundtrip(unittest.TestCase):
    def test_epoch_constant(self):
        self.assertEqual(build.TWITTER_EPOCH_MS, 1288834974657)

    def test_ams_roundtrip(self):
        dt = datetime(2026, 9, 12, 7, 20, tzinfo=AMS)
        sid = build.make_snowflake(dt)
        got = build.snowflake_to_ams(sid)
        self.assertLess(abs((got - dt).total_seconds()), 1)

    def test_id_from_url(self):
        sid = build.make_snowflake(datetime(2026, 9, 12, 8, 0, tzinfo=AMS))
        self.assertEqual(
            build.snowflake_id_from(None, f"https://x.com/demo_owner/status/{sid}"),
            sid,
        )
        self.assertEqual(build.snowflake_id_from(str(sid), None), sid)

    def test_gen_id_skipped(self):
        self.assertIsNone(build.snowflake_id_from("gen-abc123", None))


class TestSnowflakeApply(unittest.TestCase):
    def setUp(self):
        build.LOG.clear()

    def _norm(self, raw):
        return build.normalize_post(raw, AMS, "demo_owner", "test")

    def test_date_only_matching_id_gets_time(self):
        dt = datetime(2026, 9, 12, 7, 20, tzinfo=AMS)
        sid = str(build.make_snowflake(dt))
        r = self._norm({
            "id": sid,
            "created_at": "Sat, Sep 12, 2026",
            "text": "hello",
        })
        self.assertIsNotNone(r)
        p, _ = r
        self.assertTrue(p["time_known"])
        self.assertEqual(p["time_source"], "snowflake")
        self.assertEqual(p["_dt"].astimezone(AMS).hour, 7)
        self.assertEqual(p["_dt"].astimezone(AMS).minute, 20)

    def test_mismatch_ignored_and_warned(self):
        old = datetime(2024, 1, 15, 12, 0, tzinfo=AMS)
        sid = str(build.make_snowflake(old))
        r = self._norm({
            "id": sid,
            "created_at": "Sat, Sep 12, 2026",
            "text": "mismatch",
        })
        p, _ = r
        self.assertFalse(p["time_known"])
        self.assertNotEqual(p.get("time_source"), "snowflake")
        self.assertTrue(any("snowflake" in x["msg"].lower() for x in build.LOG if x["level"] == "warn"))

    def test_plus_minus_one_day_allowed(self):
        # UTC evening 11 Sep → AMS early 12 Sep; CSV date is 12 Sep (slack 1 day).
        dt = datetime(2026, 9, 11, 23, 30, tzinfo=timezone.utc).astimezone(AMS)
        sid = str(build.make_snowflake(dt))
        r = self._norm({
            "id": sid,
            "created_at": "Sat, Sep 12, 2026",
            "text": "slack",
        })
        p, _ = r
        self.assertTrue(p["time_known"])
        self.assertEqual(p["time_source"], "snowflake")

    def test_explicit_time_not_overwritten(self):
        dt = datetime(2026, 9, 12, 7, 20, tzinfo=AMS)
        sid = str(build.make_snowflake(dt))
        r = self._norm({
            "id": sid,
            "created_at": "2026-09-12T15:00:00+02:00",
            "text": "kept",
        })
        p, _ = r
        self.assertTrue(p["time_known"])
        self.assertEqual(p.get("time_source"), "explicit")
        loc = p["_dt"].astimezone(AMS)
        self.assertEqual(loc.hour, 15)
        self.assertEqual(loc.minute, 0)

    def test_merge_feeds_hour(self):
        dt = datetime(2026, 9, 12, 7, 20, tzinfo=AMS)
        sid = str(build.make_snowflake(dt))
        p, inf = self._norm({
            "id": sid,
            "url": f"https://x.com/demo_owner/status/{sid}",
            "created_at": "Sat, Sep 12, 2026",
            "text": "hour",
            "impressions": 100,
        })
        out = build.merge_posts([((0, 0, "t", 0), p, inf, "t")], "demo_owner")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["hour"], 7)
        self.assertEqual(out[0]["local_time"], "07:20")
        self.assertEqual(out[0]["time_source"], "snowflake")


class TestGoalParse(unittest.TestCase):
    def setUp(self):
        build.LOG.clear()

    def test_missing_is_unset(self):
        self.assertEqual(build.parse_goal({}), (None, None))
        self.assertEqual(build.parse_goal({"goal_followers": "", "goal_date": ""}), (None, None))
        self.assertEqual(build.parse_goal({"goal_followers": None, "goal_date": None}), (None, None))

    def test_both_set(self):
        self.assertEqual(
            build.parse_goal({"goal_followers": 500, "goal_date": "2026-12-31"}),
            (500, "2026-12-31"),
        )

    def test_only_one_set_is_unset(self):
        self.assertEqual(build.parse_goal({"goal_followers": 500}), (None, None))
        self.assertEqual(build.parse_goal({"goal_date": "2026-12-31"}), (None, None))

    def test_invalid_does_not_crash(self):
        self.assertEqual(build.parse_goal({"goal_followers": "abc", "goal_date": "not-a-date"}), (None, None))
        self.assertEqual(build.parse_goal({"goal_followers": -3, "goal_date": "2026-12-31"}), (None, None))

    def test_daily_goals_defaults_and_overrides(self):
        self.assertEqual(build.parse_daily_goals({}), (2, 10))
        self.assertEqual(build.parse_daily_goals({"goal_posts_per_day": 3, "goal_replies_per_day": 8}), (3, 8))
        self.assertEqual(build.parse_daily_goals({"goal_posts_per_day": 0, "goal_replies_per_day": "nope"}), (2, 10))


class TestRoiConstants(unittest.TestCase):
    def test_thresholds_at_top_of_build(self):
        self.assertEqual(build.LOW_ROI_MIN_REPLIES, 5)
        self.assertEqual(build.LOW_ROI_MAX_MEAN_IMPRESSIONS, 30)
        self.assertEqual(build.ROI_TOP_MIN_REPLIES, 3)
        self.assertEqual(build.SNOWFLAKE_DATE_SLACK_DAYS, 1)


if __name__ == "__main__":
    unittest.main()
