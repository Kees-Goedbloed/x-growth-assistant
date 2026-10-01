#!/usr/bin/env python3
"""Unit tests for insights helpers (Wat werkt het best)."""
import os
import sys
import unittest
from datetime import datetime, timedelta

from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))
import repo_guard  # noqa: E402,F401

AMS = ZoneInfo("Europe/Amsterdam")


class TestConstants(unittest.TestCase):
    def test_bounds_and_min_n(self):
        import insights
        self.assertEqual(insights.MIN_N, 5)
        self.assertEqual(insights.LEN_SHORT, 80)
        self.assertEqual(insights.LEN_MEDIUM, 200)
        self.assertEqual(insights.LEN_LONG, 280)
        self.assertEqual(insights.X_URL_LENGTH, 23)


class TestWeightedLength(unittest.TestCase):
    def test_plain_text(self):
        import insights
        self.assertEqual(insights.weighted_length("hello"), 5)

    def test_url_counts_as_23(self):
        import insights
        text = "zie https://example.com/very/long/path?x=1 einde"
        # "zie " (4) + 23 + " einde" (6) = 33
        self.assertEqual(insights.weighted_length(text), 33)

    def test_two_urls(self):
        import insights
        text = "https://a.com https://b.com"
        self.assertEqual(insights.weighted_length(text), 23 + 1 + 23)

    def test_empty(self):
        import insights
        self.assertEqual(insights.weighted_length(""), 0)
        self.assertEqual(insights.weighted_length(None), 0)


class TestLengthBucket(unittest.TestCase):
    def test_buckets(self):
        import insights
        self.assertEqual(insights.length_bucket(0), "short")
        self.assertEqual(insights.length_bucket(79), "short")
        self.assertEqual(insights.length_bucket(80), "medium")
        self.assertEqual(insights.length_bucket(200), "medium")
        self.assertEqual(insights.length_bucket(201), "long")
        self.assertEqual(insights.length_bucket(280), "long")
        self.assertEqual(insights.length_bucket(281), "long_form")


class TestClassifyMedia(unittest.TestCase):
    def test_explicit_wins(self):
        import insights
        kind, src = insights.classify_media("video", "https://example.com")
        self.assertEqual(kind, "video")
        self.assertEqual(src, "explicit")

    def test_url_derives_link_only(self):
        import insights
        kind, src = insights.classify_media(None, "lees https://example.com/x")
        self.assertEqual(kind, "link")
        self.assertEqual(src, "derived")

    def test_unknown_when_uncertain(self):
        import insights
        kind, src = insights.classify_media(None, "gewoon een zin zonder url")
        self.assertEqual(kind, "unknown")
        self.assertEqual(src, "missing")

    def test_does_not_guess_image_from_text(self):
        import insights
        kind, src = insights.classify_media(None, "foto van de hond")
        self.assertEqual(kind, "unknown")
        self.assertEqual(src, "missing")

    def test_all_optional_values_pass_through(self):
        import insights
        for m in ("text", "image", "multi_image", "video", "gif", "poll", "link", "article"):
            kind, src = insights.classify_media(m, "")
            self.assertEqual(kind, m)
            self.assertEqual(src, "explicit")


class TestTextFeatures(unittest.TestCase):
    def test_question_link_hashtags_mention_emoji_list_multiline(self):
        import insights
        text = (
            "3 tips voor makers?\n"
            "Lees https://example.com @peer_alpha #ai #build #x 🚀"
        )
        f = insights.text_features(text)
        self.assertTrue(f["question"])
        self.assertTrue(f["link"])
        self.assertEqual(f["hashtags"], "3+")
        self.assertTrue(f["mention"])
        self.assertTrue(f["emoji"])
        self.assertTrue(f["list_start"])
        self.assertEqual(f["lines"], "multi")

    def test_zero_hashtags_single_block(self):
        import insights
        f = insights.text_features("Gewoon een zin.")
        self.assertFalse(f["question"])
        self.assertFalse(f["link"])
        self.assertEqual(f["hashtags"], "0")
        self.assertFalse(f["mention"])
        self.assertFalse(f["emoji"])
        self.assertFalse(f["list_start"])
        self.assertEqual(f["lines"], "single")

    def test_one_or_two_hashtags(self):
        import insights
        self.assertEqual(insights.text_features("#een woord").get("hashtags"), "1-2")
        self.assertEqual(insights.text_features("#een #twee").get("hashtags"), "1-2")

    def test_language_nl_vs_en_or_skip(self):
        import insights
        nl = insights.text_features(
            "Dit is een Nederlandse zin met de het een van en op dat voor met niet."
        )
        en = insights.text_features(
            "This is an English sentence with the a of and is to in that for on with."
        )
        skip = insights.text_features("TESTFIXTURE xyz 123")
        self.assertEqual(nl["lang"], "nl")
        self.assertEqual(en["lang"], "en")
        self.assertIsNone(skip["lang"])


class TestKindAndDaypart(unittest.TestCase):
    def test_thread_is_self_reply(self):
        import insights
        self.assertEqual(insights.post_kind("reply", True), "thread")
        self.assertEqual(insights.post_kind("reply", False), "reply")
        self.assertEqual(insights.post_kind("post", False), "post")
        self.assertEqual(insights.post_kind("quote", False), "quote")
        self.assertEqual(insights.post_kind("repost", False), "repost")

    def test_daypart_amsterdam_hours(self):
        import insights
        self.assertEqual(insights.daypart(0), "night")
        self.assertEqual(insights.daypart(5), "night")
        self.assertEqual(insights.daypart(6), "morning")
        self.assertEqual(insights.daypart(11), "morning")
        self.assertEqual(insights.daypart(12), "afternoon")
        self.assertEqual(insights.daypart(17), "afternoon")
        self.assertEqual(insights.daypart(18), "evening")
        self.assertEqual(insights.daypart(23), "evening")
        self.assertIsNone(insights.daypart(None))


class TestMedianAndRates(unittest.TestCase):
    def test_median_odd_even_empty(self):
        import insights
        self.assertEqual(insights.median([1, 3, 2]), 2)
        self.assertEqual(insights.median([1, 2, 3, 4]), 2.5)
        self.assertIsNone(insights.median([]))
        self.assertIsNone(insights.median([None, None]))
        self.assertEqual(insights.median([10, None, 20]), 15)

    def test_per_thousand(self):
        import insights
        self.assertEqual(insights.per_thousand(3, 1000), 3)
        self.assertEqual(insights.per_thousand(1, 500), 2)
        self.assertIsNone(insights.per_thousand(1, 0))
        self.assertIsNone(insights.per_thousand(None, 100))


class TestReplySpeed(unittest.TestCase):
    def test_buckets(self):
        import insights
        t0 = datetime(2026, 9, 20, 12, 0, tzinfo=AMS)
        self.assertEqual(insights.reply_speed_bucket(t0, t0 - timedelta(minutes=10)), "15m")
        self.assertEqual(insights.reply_speed_bucket(t0, t0 - timedelta(minutes=15)), "15m")
        self.assertEqual(insights.reply_speed_bucket(t0, t0 - timedelta(minutes=16)), "1h")
        self.assertEqual(insights.reply_speed_bucket(t0, t0 - timedelta(hours=1)), "1h")
        self.assertEqual(insights.reply_speed_bucket(t0, t0 - timedelta(hours=1, seconds=1)), "4h")
        self.assertEqual(insights.reply_speed_bucket(t0, t0 - timedelta(hours=4)), "4h")
        self.assertEqual(insights.reply_speed_bucket(t0, t0 - timedelta(hours=4, seconds=1)), "later")
        self.assertIsNone(insights.reply_speed_bucket(t0, None))
        self.assertIsNone(insights.reply_speed_bucket(None, t0))

    def test_never_guess_negative_delay(self):
        import insights
        t0 = datetime(2026, 9, 20, 12, 0, tzinfo=AMS)
        # parent after reply: do not invent a bucket
        self.assertIsNone(insights.reply_speed_bucket(t0, t0 + timedelta(minutes=5)))


class TestEnrichAndRecipes(unittest.TestCase):
    def test_enrich_adds_fields_without_guessing_parent(self):
        import insights
        p = {
            "id": "1",
            "text": "3 tips https://example.com #a #b?",
            "type": "reply",
            "self_reply": False,
            "media": None,
            "hour": 20,
            "created_at": "2026-09-20T20:00:00+02:00",
            "in_reply_to_created_at": None,
        }
        out = insights.enrich_post(p, "demo_owner")
        self.assertEqual(out["kind"], "reply")
        self.assertEqual(out["media_kind"], "link")
        self.assertEqual(out["media_source"], "derived")
        self.assertEqual(out["length_bucket"], "short")
        self.assertTrue(out["feat_question"])
        self.assertIsNone(out["reply_speed"])
        self.assertEqual(out["daypart"], "evening")

    def test_recipe_needs_min_n(self):
        import insights
        posts = []
        for i in range(5):
            posts.append({
                "media_kind": "video",
                "length_bucket": "short",
                "daypart": "evening",
                "impressions": 100 + i,
                "er": 0.1,
            })
        posts.append({
            "media_kind": "text",
            "length_bucket": "long",
            "daypart": "morning",
            "impressions": 9999,
            "er": 0.9,
        })
        recipes = insights.top_recipes(posts, min_n=5, limit=5)
        self.assertEqual(len(recipes), 1)
        self.assertGreaterEqual(recipes[0]["n"], 5)
        self.assertIn("video", recipes[0]["label"])


if __name__ == "__main__":
    unittest.main()
