#!/usr/bin/env python3
"""
Kenmerken en groepen voor de sectie "Wat werkt het best".

Alleen Python 3-standaardbibliotheek. Geen gokken: ontbrekende velden blijven
ontbrekend; media wordt alleen uit een expliciet veld of een zekere externe URL
afgeleid.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Iterable, Optional

# Honesty / bucket constants (also embedded in dashboard meta)
MIN_N = 5
LEN_SHORT = 80       # gewogen lengte < 80
LEN_MEDIUM = 200     # 80–200
LEN_LONG = 280       # 201–280; daarboven = long-form (premium)
X_URL_LENGTH = 23    # X telt elke URL als 23 tekens

MEDIA_KIND_VALUES = (
    "text", "image", "multi_image", "video", "gif", "poll", "link", "article",
    "thread", "unknown",
)

DAYPART_NL = {
    "night": "nacht",
    "morning": "ochtend",
    "afternoon": "middag",
    "evening": "avond",
}
LENGTH_NL = {
    "short": "kort",
    "medium": "middel",
    "long": "lang",
    "long_form": "long-form",
}
KIND_NL = {
    "post": "post",
    "reply": "reactie",
    "quote": "quote",
    "repost": "repost",
    "thread": "thread",
}
MEDIA_NL = {
    "text": "alleen tekst",
    "image": "afbeelding",
    "multi_image": "meerdere afbeeldingen",
    "video": "video",
    "gif": "GIF",
    "poll": "peiling",
    "link": "link",
    "article": "artikel",
    "thread": "thread",
    "unknown": "onbekend",
}
SPEED_NL = {
    "15m": "binnen 15 min",
    "1h": "binnen 1 uur",
    "4h": "binnen 4 uur",
    "later": "later",
}

INSIGHTS_META = {
    "min_n": MIN_N,
    "len_short": LEN_SHORT,
    "len_medium": LEN_MEDIUM,
    "len_long": LEN_LONG,
    "url_weight": X_URL_LENGTH,
    "labels": {
        "daypart": DAYPART_NL,
        "length": LENGTH_NL,
        "kind": KIND_NL,
        "media": MEDIA_NL,
        "speed": SPEED_NL,
    },
}

# http(s) URLs; trailing sentence punctuation is not part of the URL
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
HASHTAG_RE = re.compile(r"(?<![A-Za-z0-9_])#([A-Za-z0-9_]+)")
MENTION_RE = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z0-9_]+)")
LIST_START_RE = re.compile(r"^\s*(?:\d+[\.\:\)]\s|\d+\s+\S|[-*•]\s+\S)")
WORD_RE = re.compile(r"[A-Za-zÀ-ÿ']+")
EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002600-\U000026FF"
    "\U00002700-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "]+"
)

NL_FUNC = {
    "de", "het", "een", "van", "en", "is", "op", "dat", "die", "voor", "met",
    "niet", "zijn", "er", "je", "ik", "we", "dit", "maar", "ook", "als", "bij",
    "om", "nog", "wel", "geen", "naar", "uit", "dan", "wat", "geen", "haar",
    "zijn", "was", "heb", "hebt", "heeft", "had", "kan", "kunnen", "moet",
    "worden", "werd", "hier", "daar", "zo", "al", "of",
}
EN_FUNC = {
    "the", "a", "an", "of", "and", "is", "to", "in", "that", "it", "for", "on",
    "with", "as", "was", "be", "this", "are", "by", "at", "from", "or", "not",
    "your", "you", "we", "have", "has", "had", "but", "they", "their", "can",
    "will", "just", "about", "what", "when", "how", "if",
}


def _strip_url(m: re.Match) -> str:
    u = m.group(0)
    return u.rstrip(".,;:!?)]}\"'>")


def iter_urls(text: str) -> list[str]:
    if not text:
        return []
    return [_strip_url(m) for m in URL_RE.finditer(text)]


def weighted_length(text: Optional[str]) -> int:
    if not text:
        return 0
    out, last = [], 0
    for m in URL_RE.finditer(text):
        url = _strip_url(m)
        out.append(text[last:m.start()])
        out.append("x" * X_URL_LENGTH)
        last = m.start() + len(url)
    out.append(text[last:])
    return len("".join(out))


def length_bucket(n: int) -> str:
    if n < LEN_SHORT:
        return "short"
    if n <= LEN_MEDIUM:
        return "medium"
    if n <= LEN_LONG:
        return "long"
    return "long_form"


def has_external_url(text: Optional[str]) -> bool:
    return bool(iter_urls(text or ""))


def classify_media(explicit: Optional[str], text: Optional[str]) -> tuple[str, str]:
    """Return (media_kind, source) where source is explicit|derived|missing."""
    if explicit:
        return explicit, "explicit"
    if has_external_url(text):
        return "link", "derived"
    return "unknown", "missing"


def detect_language(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    words = [w.lower() for w in WORD_RE.findall(text)]
    if not words:
        return None
    nl = sum(1 for w in words if w in NL_FUNC)
    en = sum(1 for w in words if w in EN_FUNC)
    if nl < 4 and en < 4:
        return None
    if nl >= 4 and nl >= en * 1.5:
        return "nl"
    if en >= 4 and en >= nl * 1.5:
        return "en"
    return None


def text_features(text: Optional[str]) -> dict:
    t = text or ""
    tags = HASHTAG_RE.findall(t)
    if len(tags) >= 3:
        hb = "3+"
    elif len(tags) >= 1:
        hb = "1-2"
    else:
        hb = "0"
    lines = "multi" if re.search(r"\n", t) else "single"
    return {
        "question": "?" in t,
        "link": has_external_url(t),
        "hashtags": hb,
        "mention": bool(MENTION_RE.search(t)),
        "emoji": bool(EMOJI_RE.search(t)),
        "list_start": bool(LIST_START_RE.search(t)),
        "lines": lines,
        "lang": detect_language(t),
    }


def post_kind(typ: Optional[str], self_reply: bool) -> str:
    if typ == "reply" and self_reply:
        return "thread"
    return typ or "post"


def daypart(hour: Optional[int]) -> Optional[str]:
    if hour is None:
        return None
    if 0 <= hour <= 5:
        return "night"
    if 6 <= hour <= 11:
        return "morning"
    if 12 <= hour <= 17:
        return "afternoon"
    return "evening"


def median(values: Iterable) -> Optional[float]:
    nums = [v for v in values if v is not None and v == v]
    if not nums:
        return None
    nums = sorted(float(v) for v in nums)
    n = len(nums)
    mid = n // 2
    if n % 2:
        return nums[mid]
    return (nums[mid - 1] + nums[mid]) / 2.0


def per_thousand(count, impressions) -> Optional[float]:
    if count is None or impressions is None or impressions <= 0:
        return None
    return (float(count) / float(impressions)) * 1000.0


def _as_dt(value) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            return None
        return dt
    s = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt


def reply_speed_bucket(created, parent) -> Optional[str]:
    a, b = _as_dt(created), _as_dt(parent)
    if a is None or b is None:
        return None
    delay = a - b
    if delay < timedelta(0):
        return None
    if delay <= timedelta(minutes=15):
        return "15m"
    if delay <= timedelta(hours=1):
        return "1h"
    if delay <= timedelta(hours=4):
        return "4h"
    return "later"


def recipe_label(media_kind: str, length: str, part: Optional[str]) -> str:
    bits = [MEDIA_NL.get(media_kind, media_kind), LENGTH_NL.get(length, length)]
    if part:
        bits.append(DAYPART_NL.get(part, part))
    return " + ".join(bits)


def top_recipes(posts: list, min_n: int = MIN_N, limit: int = 5) -> list[dict]:
    groups: dict[tuple, list] = {}
    for p in posts:
        mk = p.get("media_kind") or "unknown"
        lb = p.get("length_bucket")
        dp = p.get("daypart")
        if not lb or not dp or mk == "unknown":
            continue
        key = (mk, lb, dp)
        groups.setdefault(key, []).append(p)
    rows = []
    for key, items in groups.items():
        n = len(items)
        if n < min_n:
            continue
        rows.append({
            "key": key,
            "label": recipe_label(*key),
            "n": n,
            "median_impressions": median(p.get("impressions") for p in items),
            "median_er": median(p.get("er") for p in items),
        })
    rows.sort(
        key=lambda r: (
            r["median_impressions"] is None,
            -(r["median_impressions"] or 0),
            r["median_er"] is None,
            -(r["median_er"] or 0),
        )
    )
    return rows[:limit]


def enrich_post(p: dict, account: str) -> dict:
    """Add insight fields in-place; never overwrite existing metrics."""
    text = p.get("text") or ""
    explicit = p.get("media")
    kind, src = classify_media(explicit, text)
    p["media_kind"] = kind
    p["media_source"] = src
    p["text_len"] = weighted_length(text)
    p["length_bucket"] = length_bucket(p["text_len"])
    feat = text_features(text)
    p["feat_question"] = feat["question"]
    p["feat_link"] = feat["link"]
    p["feat_hashtags"] = feat["hashtags"]
    p["feat_mention"] = feat["mention"]
    p["feat_emoji"] = feat["emoji"]
    p["feat_list_start"] = feat["list_start"]
    p["feat_lines"] = feat["lines"]
    p["lang"] = feat["lang"]
    p["kind"] = post_kind(p.get("type"), bool(p.get("self_reply")))
    p["daypart"] = daypart(p.get("hour"))
    parent = p.get("in_reply_to_created_at")
    p["reply_speed"] = reply_speed_bucket(p.get("created_at"), parent)
    if p.get("impressions"):
        p["visits_per_1k"] = per_thousand(p.get("profile_visits"), p["impressions"])
        p["follows_per_1k"] = per_thousand(p.get("new_follows"), p["impressions"])
    else:
        p["visits_per_1k"] = None
        p["follows_per_1k"] = None
    return p


def enrich_posts(posts: list, account: str) -> list:
    for p in posts:
        enrich_post(p, account)
    return posts