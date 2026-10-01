#!/usr/bin/env python3
"""
X growth dashboard — offline builder.

Reads:
  * data/followers/snapshot-*.json      (canonical follower snapshots)
  * data/posts/*.json | *.jsonl         (canonical post metrics)
  * data/analytics-csv/*.csv            (X Analytics CSV exports)
  * data/config.json                    (optional)
  * data/target_accounts.json           (optional; public-mode size buckets)
  * --followers-dir DIR                 (optional extra snapshot directory)

Writes one self-contained index.html (JSON embedded, works via file://).

Python 3 standard library only.

Usage:
  python3 build.py
  python3 build.py --data test-fixtures/data --mode public --out index.test.html --today 2026-09-25

Default mode is public (safe to share). Private mode is opt-in
(`--mode private` or config.json "mode": "private") and keeps other
people's handles. A public build always runs the leak checker.
"""
import argparse
import base64
import csv
import glob
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, time as dtime, timezone
from zoneinfo import ZoneInfo

from insights import INSIGHTS_META, LEN_LONG, LEN_MEDIUM, LEN_SHORT, MIN_N, X_URL_LENGTH, enrich_posts

AMS = ZoneInfo("Europe/Amsterdam")
BASE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(BASE, "template.html")
ASSETS_OG = os.path.join(BASE, "assets", "og-image.png")
AVATAR_STEM = "avatar"
AVATAR_FILENAME = "avatar.jpg"
UNAVATAR_TMPL = "https://unavatar.io/x/{handle}"
FXTWITTER_TMPL = "https://api.fxtwitter.com/{handle}"
_PBS_SIZE_RE = re.compile(r"_(normal|bigger|mini|\d+x\d+)(\.[A-Za-z0-9]+)$")
VENDOR_ECHARTS = os.path.join(BASE, "vendor", "echarts", "echarts.min.js")
VENDOR_FONTS = (
    (400, os.path.join(BASE, "vendor", "fonts", "inter-latin-400.woff2")),
    (600, os.path.join(BASE, "vendor", "fonts", "inter-latin-600.woff2")),
    (700, os.path.join(BASE, "vendor", "fonts", "inter-latin-700.woff2")),
)
MIN_BUCKET_ACCOUNTS = 5
SIZE_BUCKET_ORDER = ["<1k", "1k–10k", "10k–100k", ">100k"]
FREQ_BUCKET_ORDER = ["1×", "2–4×", "5×+"]
MENTION_RE = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z0-9_]{1,15})")
# Bucketgrenzen voor "Wat werkt het best" (ook in insights.py; hier zodat ze
# bovenaan build.py staan zoals de spec vraagt).
assert MIN_N == 5 and LEN_SHORT == 80 and LEN_MEDIUM == 200 and LEN_LONG == 280 and X_URL_LENGTH == 23

# X snowflake: ms = (id >> 22) + TWITTER_EPOCH_MS (Unix epoch ms, UTC).
TWITTER_EPOCH_MS = 1288834974657
SNOWFLAKE_DATE_SLACK_DAYS = 1
# Reactie-rendement: "veel moeite, weinig bereik" en top-10 drempels.
LOW_ROI_MIN_REPLIES = 5
LOW_ROI_MAX_MEAN_IMPRESSIONS = 30
ROI_TOP_MIN_REPLIES = 3

METRICS = ["impressions", "likes", "replies", "reposts", "quotes", "bookmarks",
           "profile_visits", "link_clicks", "new_follows",
           # extra X-metrics (optioneel): X's eigen engagements-totaal en overige kliks
           "engagements", "shares", "detail_expands", "hashtag_clicks", "permalink_clicks"]
# Engagement rate per post:
#   als X's eigen 'engagements' aanwezig is: engagements / impressions            (bron "X")
#   anders: (likes + replies + reposts + quotes + bookmarks + profile_visits + link_clicks) / impressions  (bron "berekend")
ER_COMPONENTS = ["likes", "replies", "reposts", "quotes", "bookmarks", "profile_visits", "link_clicks"]

# ---------------------------------------------------------------- logging
LOG = []


def log(level, msg):
    LOG.append({"level": level, "msg": msg})
    prefix = {"info": "  ", "warn": "! ", "error": "X "}.get(level, "  ")
    print(prefix + msg, file=sys.stderr if level != "info" else sys.stdout)


def info(msg):
    log("info", msg)


def warn(msg):
    log("warn", msg)


# Stored follower-event keys stay Dutch; English is display/log only.
STATUS_EN = {
    "ontvolger": "unfollowed",
    "verwijderd": "deleted",
    "geschorst": "suspended",
    "mogelijk": "possible",
    "capture_gat": "capture_gap",
    "nieuw": "new",
    "terug": "returned",
}


def format_left_list(cnt):
    """English display of left-list status counts; stored keys stay Dutch."""
    if not cnt:
        return "0"
    mapped = {STATUS_EN.get(k, k): v for k, v in cnt.items()}
    return str(mapped)


# ---------------------------------------------------------------- helpers
def norm_handle(h):
    """'@Foo', 'https://x.com/Foo', {'handle': 'Foo'} -> 'Foo' (casing behouden)."""
    if h is None:
        return None
    if isinstance(h, dict):
        h = h.get("handle") or h.get("username") or h.get("screen_name")
        if h is None:
            return None
    h = str(h).strip()
    m = re.match(r"^(?:https?://)?(?:www\.|mobile\.)?(?:x|twitter)\.com/([A-Za-z0-9_]+)", h)
    if m:
        h = m.group(1)
    h = h.lstrip("@").strip()
    return h or None


def hkey(h):
    return h.lower() if h else None


EN_FORMATS = [
    ("%Y-%m-%d %H:%M %z", True), ("%Y-%m-%d %H:%M:%S %z", True),
    ("%Y-%m-%d %H:%M", True), ("%Y-%m-%d %H:%M:%S", True),
    ("%a, %b %d, %Y %H:%M", True), ("%a, %b %d, %Y %I:%M %p", True), ("%a, %b %d, %Y", False),
    ("%b %d, %Y %H:%M", True), ("%b %d, %Y %I:%M %p", True), ("%b %d, %Y", False),
    ("%B %d, %Y %H:%M", True), ("%B %d, %Y", False),
    ("%a %b %d %H:%M:%S %z %Y", True),
    ("%d-%m-%Y %H:%M", True), ("%d-%m-%Y %H:%M:%S", True), ("%d-%m-%Y", False),
    ("%d/%m/%Y %H:%M", True), ("%d/%m/%Y", False),  # alleen gebruikt na NL-vertaling
    ("%m/%d/%Y %H:%M", True), ("%m/%d/%Y %I:%M %p", True), ("%m/%d/%Y", False),
    ("%d.%m.%Y %H:%M", True), ("%d.%m.%Y", False),
    ("%d %b %Y %H:%M", True), ("%d %b %Y", False),
    ("%d %B %Y %H:%M", True), ("%d %B %Y", False),
    ("%Y-%m-%d", False),
]
NL_MONTHS = {
    "januari": "Jan", "februari": "Feb", "maart": "Mar", "april": "Apr", "mei": "May", "juni": "Jun",
    "juli": "Jul", "augustus": "Aug", "september": "Sep", "oktober": "Oct", "november": "Nov",
    "december": "Dec", "jan": "Jan", "feb": "Feb", "mrt": "Mar", "mar": "Mar", "apr": "Apr",
    "jun": "Jun", "jul": "Jul", "aug": "Aug", "sep": "Sep", "sept": "Sep", "okt": "Oct",
    "nov": "Nov", "dec": "Dec",
}
NL_DROP = {"maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag",
           "ma", "di", "wo", "do", "vr", "za", "zo", "om", "u", "uur"}


def _try_formats(s, formats):
    for fmt, has_time in formats:
        try:
            return datetime.strptime(s, fmt), has_time
        except ValueError:
            continue
    return None, False


NAIVE_HITS = []  # tijdstempels zonder tijdzone (voor waarschuwingen)


def parse_dt(value, naive_tz):
    """-> (aware datetime | None, time_known). Datum-zonder-tijd -> 12:00 lokaal, time_known=False."""
    if value is None:
        return None, False
    if isinstance(value, (int, float)):
        # epoch seconden of milliseconden
        v = float(value)
        if v > 1e12:
            v /= 1000.0
        return datetime.fromtimestamp(v, tz=timezone.utc), True
    s = str(value).strip()
    if not s:
        return None, False
    dt, has_time = None, True
    iso = s.replace("Z", "+00:00") if re.search(r"\dZ$", s) else s
    try:
        dt = datetime.fromisoformat(iso)
        has_time = bool(re.search(r"\d[T ]\d{1,2}:\d{2}", iso))
    except ValueError:
        dt = None
    if dt is None:
        # Engelse formaten (m/d/Y voor '/' zoals X-exports)
        en = [f for f in EN_FORMATS if not f[0].startswith("%d/%m")]
        dt, has_time = _try_formats(re.sub(r"\s+", " ", s), en)
    if dt is None and re.search(r"[A-Za-z]", s):
        # Nederlandse maand-/dagnamen vertalen
        t = s.lower().replace(".", " ").replace(",", " ")
        toks = []
        for tok in re.split(r"\s+", t):
            if not tok or tok in NL_DROP:
                continue
            toks.append(NL_MONTHS.get(tok, tok))
        t2 = " ".join(toks)
        # "22 Sep 2026 14 03" (punt als tijdscheiding) -> herstel ':'
        t2 = re.sub(r"(\d{4}) (\d{1,2}) (\d{2})$", r"\1 \2:\3", t2)
        dt, has_time = _try_formats(t2, EN_FORMATS)
    if dt is None:
        return None, False
    if not has_time:
        return datetime.combine(dt.date(), dtime(12, 0), tzinfo=AMS), False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=naive_tz)
        NAIVE_HITS.append(s)
    return dt, True


def parse_int(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(round(v))
    s = str(v).strip().replace("\u00a0", "").replace(" ", "")
    if s in ("", "-", "—", "n/a", "N/A", "null", "None"):
        return None
    m = re.match(r"^([\d.,]+)\s*([kKmM])$", s)
    if m:
        num = float(m.group(1).replace(",", "."))
        return int(round(num * (1000 if m.group(2).lower() == "k" else 1_000_000)))
    s2 = re.sub(r"[.,](?=\d{3}(\D|$))", "", s)  # duizendtallen-scheiding weg
    try:
        return int(round(float(s2.replace(",", "."))))
    except ValueError:
        return None


def first_present(d, keys):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def date_from_filename(path):
    m = re.search(r"(\d{4})-?(\d{2})-?(\d{2})", os.path.basename(path))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


# ---------------------------------------------------------------- followers
def parse_handle_list(val):
    if not isinstance(val, list):
        return None
    out = []
    for h in val:
        n = norm_handle(h)
        if n:
            out.append(n)
    return out


def parse_unavailable(val):
    out = []
    if not isinstance(val, list):
        return out
    for item in val:
        reason = None
        if isinstance(item, dict):
            reason = item.get("reason") or item.get("status")
        n = norm_handle(item)
        if n:
            out.append({"handle": n, "reason": reason})
    return out


def parse_verified(val):
    out = []
    if not isinstance(val, list):
        return out
    for item in val:
        checked, note = None, None
        if isinstance(item, dict):
            checked, note = item.get("checked_at"), item.get("note")
        n = norm_handle(item)
        if n:
            out.append({"handle": n, "checked_at": checked, "note": note})
    return out


def load_follower_file(path, source):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:  # noqa
        warn(f"Follower file unreadable: {path} ({e})")
        return None
    if not isinstance(d, dict):
        warn(f"Follower file is not a JSON object, skipped: {path}")
        return None
    followers = parse_handle_list(first_present(d, ["handles", "followers", "follower_handles"]))
    if followers is None:
        warn(f"No 'handles' list in {path}, skipped")
        return None
    captured = None
    if d.get("captured_at"):
        captured, _ = parse_dt(d.get("captured_at"), AMS)
    day = None
    if d.get("date"):
        try:
            day = date.fromisoformat(str(d["date"])[:10])
        except ValueError:
            warn(f"Invalid 'date' in {path}: {d.get('date')!r}")
    if day is None and captured:
        day = captured.astimezone(AMS).date()
    if day is None:
        day = date_from_filename(path)
    if day is None:
        warn(f"Could not determine a date for {path} (provide 'date' or 'captured_at'), skipped")
        return None
    if captured is None:
        captured = datetime.combine(day, dtime(12, 0), tzinfo=AMS)
    fc = parse_int(first_present(d, ["profile_followers", "followers_count"]))
    gc = parse_int(first_present(d, ["profile_following", "following_count"]))
    following = parse_handle_list(first_present(d, ["following_handles", "following"]))
    # dedupe (case-insensitive), casing behouden
    def dedupe(lst):
        seen, out = set(), []
        for h in lst:
            if hkey(h) not in seen:
                seen.add(hkey(h))
                out.append(h)
        return out
    followers = dedupe(followers)
    following = dedupe(following) if following is not None else None
    complete = d.get("complete")
    if complete is None:
        complete = (fc is not None and len(followers) >= fc)
    following_complete = d.get("following_complete")
    if following is not None and following_complete is None:
        following_complete = (gc is not None and len(following) >= gc)
    out = {
        "date": day.isoformat(),
        "captured_at": captured.astimezone(AMS).isoformat(),
        "followers_count": fc,
        "following_count": gc,
        "followers": followers,
        "following": following,
        "complete": bool(complete),
        "following_complete": bool(following_complete) if following is not None else None,
        "unavailable": parse_unavailable(d.get("unavailable")),
        "verified_unfollowers": parse_verified(d.get("verified_unfollowers")),
        "notes": d.get("notes"),
        "source": source + ":" + os.path.basename(path),
        "path": path,
    }
    for key in ("profile_image_url", "profile_image_url_https"):
        raw = d.get(key)
        if raw and "pbs.twimg.com/profile_images" in str(raw):
            out[key] = str(raw).strip()
    return out


def load_followers(extra_dir, data_dir):
    by_capture = {}
    files = []
    if extra_dir:
        if os.path.isdir(extra_dir):
            files += [(p, "extra") for p in sorted(glob.glob(os.path.join(extra_dir, "*.json")))]
        else:
            warn(f"Extra follower directory not found: {extra_dir}")
    fdir = os.path.join(data_dir, "followers")
    if os.path.isdir(fdir):
        files += [(p, "data") for p in sorted(glob.glob(os.path.join(fdir, "*.json")))]
    for path, src in files:
        s = load_follower_file(path, src)
        if not s:
            continue
        # prioriteit bij dezelfde captured_at: data/followers > extra snapshot-* > extra latest.json
        s["_rank"] = 2 if src == "data" else (0 if os.path.basename(path) == "latest.json" else 1)
        key = s["captured_at"]
        prev = by_capture.get(key)
        if prev is None:
            by_capture[key] = s
        elif s["_rank"] >= prev["_rank"]:
            by_capture[key] = merge_same_capture(prev, s)
        else:
            by_capture[key] = merge_same_capture(s, prev)
    snaps = sorted(by_capture.values(), key=lambda s: s["captured_at"])
    info(f"Follower snapshots loaded: {len(snaps)} unique (from {len(files)} files)")
    # één snapshot per dag: laatste van die dag, ontbrekende velden aanvullen met eerdere van die dag
    per_day = {}
    for s in snaps:
        if s["date"] in per_day:
            per_day[s["date"]] = merge_same_capture(per_day[s["date"]], s, union_unavail=True)
        else:
            per_day[s["date"]] = s
    return [per_day[k] for k in sorted(per_day)]


def merge_same_capture(old, new, union_unavail=True):
    """new wint; ontbrekende velden uit old."""
    m = dict(new)
    for k in ("followers_count", "following_count", "following", "following_complete", "notes",
              "profile_image_url", "profile_image_url_https"):
        if m.get(k) is None and old.get(k) is not None:
            m[k] = old[k]
    if union_unavail:
        for key in ("unavailable", "verified_unfollowers"):
            seen = {hkey(u["handle"]) for u in m[key]}
            m[key] = list(m[key]) + [u for u in old[key] if hkey(u["handle"]) not in seen]
    if old["source"] not in m["source"]:
        m["source"] = m["source"] + " + " + old["source"]
    return m


def compute_follower_events(days):
    # unavailable (verwijderd/geschorst): unie over alle snapshots
    unavailable = {}
    for s in days:
        for u in s["unavailable"]:
            k = hkey(u["handle"])
            if k not in unavailable:
                unavailable[k] = {"handle": u["handle"], "first_flagged": s["date"], "reason": u["reason"]}
    verified = {}
    for s in days:
        for u in s["verified_unfollowers"]:
            k = hkey(u["handle"])
            if k not in verified:
                verified[k] = dict(u, first_listed=s["date"])
    latest_following = None
    for s in reversed(days):
        if s["following"] is not None:
            latest_following = s
            break
    lf_keys = {hkey(h) for h in latest_following["following"]} if latest_following else None

    def follow_status(k, snap):
        """-> (True/False/None, reden, basisdatum). None = onbekend."""
        base = snap if (snap is not None and snap["following"] is not None) else latest_following
        if base is None:
            return None, "geen_lijst", None
        keys = {hkey(h) for h in base["following"]}
        if k in keys:
            return True, None, base["date"]
        if base["following_complete"]:
            return False, None, base["date"]
        return None, "lijst_onvolledig", base["date"]

    seen_before = {}
    new_events, lost_events = [], []
    day_keys = [{hkey(h): h for h in s["followers"]} for s in days]
    for i, s in enumerate(days):
        cur = day_keys[i]
        if i > 0:
            prev = day_keys[i - 1]
            fol_keys = {hkey(h) for h in s["following"]} if s["following"] is not None else None
            for k in sorted(set(cur) - set(prev)):
                status = "terug" if k in seen_before else "nieuw"
                fb, why, basis = follow_status(k, s)
                new_events.append({
                    "date": s["date"], "handle": cur[k], "status": status,
                    "follows_back": fb, "follows_back_reason": why, "follows_back_basis": basis,
                })
            for k in sorted(set(prev) - set(cur)):
                reappeared = None
                for j in range(i + 1, len(days)):
                    if k in day_keys[j]:
                        reappeared = days[j]["date"]
                        break
                is_verified = False
                if k in unavailable:
                    status = "verwijderd"
                elif k in verified:
                    status = "ontvolger"
                    is_verified = True
                elif reappeared:
                    status = "capture_gat"
                elif s["complete"]:
                    status = "ontvolger"
                else:
                    status = "mogelijk"
                sf, why, basis = follow_status(k, None)
                lost_events.append({
                    "date": s["date"], "handle": prev[k], "status": status,
                    "verified": is_verified,
                    "verified_info": verified.get(k) if is_verified else None,
                    "reappeared_on": reappeared,
                    "still_following": sf, "still_following_reason": why, "still_following_basis": basis,
                })
        for k in cur:
            seen_before.setdefault(k, s["date"])

    ever_follower = set(seen_before)
    unavail_list = [dict(v, was_follower=(k in ever_follower)) for k, v in unavailable.items()]

    not_following_back = None
    if latest_following:
        fk = {hkey(h) for h in latest_following["followers"]}
        lst = [h for h in latest_following["following"] if hkey(h) not in fk and hkey(h) not in unavailable]
        not_following_back = {
            "date": latest_following["date"],
            "followers_complete": latest_following["complete"],
            "following_complete": latest_following["following_complete"],
            "followers_loaded": len(latest_following["followers"]),
            "followers_profile": latest_following["followers_count"],
            "following_loaded": len(latest_following["following"]),
            "following_profile": latest_following["following_count"],
            "handles": sorted(lst, key=str.lower),
        }
    snaps_out = []
    for s in days:
        d = s["date"]
        row = {
            "date": d, "captured_at": s["captured_at"],
            "followers_count": s["followers_count"], "following_count": s["following_count"],
            "collected_count": len(s["followers"]),
            "following_collected": len(s["following"]) if s["following"] is not None else None,
            "complete": s["complete"], "following_complete": s["following_complete"],
            "unavailable_count": len(s["unavailable"]),
            "verified_count": len(s["verified_unfollowers"]),
            "n_new": sum(1 for e in new_events if e["date"] == d and e["status"] == "nieuw"),
            "n_returned": sum(1 for e in new_events if e["date"] == d and e["status"] == "terug"),
            "n_unfollowed": sum(1 for e in lost_events if e["date"] == d and e["status"] == "ontvolger"),
            "n_possible": sum(1 for e in lost_events if e["date"] == d and e["status"] == "mogelijk"),
            "n_gap": sum(1 for e in lost_events if e["date"] == d and e["status"] == "capture_gat"),
            "n_removed": sum(1 for e in lost_events if e["date"] == d and e["status"] == "verwijderd"),
            "notes": s["notes"],
            "source": os.path.basename(s.get("source") or "") or s.get("source"),
        }
        for key in ("profile_image_url", "profile_image_url_https"):
            if s.get(key):
                row[key] = s[key]
        snaps_out.append(row)
    return {
        "snapshots": snaps_out,
        "new": new_events,
        "lost": lost_events,
        "unavailable": sorted(unavail_list, key=lambda u: u["handle"].lower()),
        "verified_unfollowers": sorted(verified.values(), key=lambda u: u["handle"].lower()),
        "not_following_back": not_following_back,
        "latest_following_date": latest_following["date"] if latest_following else None,
        "latest_following_complete": latest_following["following_complete"] if latest_following else None,
        "latest_following_loaded": len(latest_following["following"]) if latest_following else None,
        "latest_following_profile": latest_following["following_count"] if latest_following else None,
    }


# ---------------------------------------------------------------- posts
TYPE_MAP = {
    "post": "post", "tweet": "post", "original": "post", "bericht": "post",
    "reply": "reply", "replies": "reply", "reactie": "reply", "antwoord": "reply",
    "repost": "repost", "retweet": "repost", "rt": "repost", "herpost": "repost",
    "quote": "quote", "quote tweet": "quote", "quote post": "quote", "citaat": "quote", "geciteerd": "quote",
}
MEDIA_MAP = {
    "text": "text", "tekst": "text", "none": "text", "geen": "text",
    "image": "image", "photo": "image", "foto": "image", "afbeelding": "image", "img": "image",
    "multi image": "multi_image", "multi_image": "multi_image", "images": "multi_image",
    "meerdere afbeeldingen": "multi_image", "album": "multi_image",
    "gif": "gif", "animated gif": "gif", "animated_gif": "gif",
    "video": "video", "clip": "video",
    "poll": "poll", "peiling": "poll",
    "link": "link", "url": "link",
    "article": "article", "artikel": "article",
    "thread": "thread", "draad": "thread", "draadje": "thread",
}


def norm_enum(v, mapping):
    if v is None:
        return None
    s = str(v).strip().lower().replace("_", " ").replace("-", " ")
    return mapping.get(s)


def id_from_url(url):
    if not url:
        return None
    m = re.search(r"/status(?:es)?/(\d+)", str(url))
    return m.group(1) if m else None


def snowflake_id_from(pid, url=None):
    """Numerieke X-snowflake uit post-id of /status/<id> in de URL. gen- ids overslaan."""
    if pid is not None:
        s = str(pid).strip()
        if s.startswith("gen-"):
            return None
        if re.fullmatch(r"\d{10,20}", s):
            return int(s)
    extracted = id_from_url(url)
    if extracted and re.fullmatch(r"\d{10,20}", extracted):
        return int(extracted)
    return None


def make_snowflake(dt, extra_bits=0):
    """Encodeer een datetime als X-snowflake (milliseconde-precisie)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=AMS)
    ms = int(dt.astimezone(timezone.utc).timestamp() * 1000)
    return ((ms - TWITTER_EPOCH_MS) << 22) | (int(extra_bits) & ((1 << 22) - 1))


def snowflake_to_ams(sid):
    """Snowflake-id → aware datetime in Europe/Amsterdam."""
    ms = (int(sid) >> 22) + TWITTER_EPOCH_MS
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).astimezone(AMS)


def apply_snowflake_time(p, src):
    """Vul created_at uit de snowflake-id als er geen expliciete tijd is.

    Alleen als time_known ontbreekt/False. Als er wel een CSV-datum is, moet de
    afgeleide Amsterdam-datum binnen ± SNOWFLAKE_DATE_SLACK_DAYS liggen.
    """
    if p.get("time_known"):
        p.setdefault("time_source", "explicit")
        return
    sid = snowflake_id_from(p.get("id"), p.get("url"))
    if sid is None:
        if "_dt" in p:
            p.setdefault("time_source", "date")
        return
    try:
        derived = snowflake_to_ams(sid)
    except (OverflowError, OSError, ValueError):
        warn(f"{src}: snowflake id {p.get('id')} could not be read as a time — ignored")
        if "_dt" in p:
            p.setdefault("time_source", "date")
        return
    csv_dt = p.get("_dt")
    if csv_dt is not None:
        csv_date = csv_dt.astimezone(AMS).date()
        derived_date = derived.date()
        if abs((derived_date - csv_date).days) > SNOWFLAKE_DATE_SLACK_DAYS:
            warn(f"{src}: snowflake time of id {p['id']} ({derived.isoformat()}) differs from "
                 f"CSV date {csv_date.isoformat()} (±{SNOWFLAKE_DATE_SLACK_DAYS} day) — ignored")
            p.setdefault("time_source", "date")
            return
    p["_dt"] = derived
    p["time_known"] = True
    p["time_source"] = "snowflake"


def parse_goal(cfg):
    """Optionele goal_followers + goal_date. Beide of geen; anders unset + waarschuwing."""
    if not isinstance(cfg, dict):
        return None, None
    raw_f, raw_d = cfg.get("goal_followers"), cfg.get("goal_date")
    empty_f = raw_f in (None, "", False)
    empty_d = raw_d in (None, "")
    if empty_f and empty_d:
        return None, None
    followers, gdate = None, None
    if not empty_f:
        try:
            followers = int(raw_f)
            if followers <= 0:
                warn(f"goal_followers must be a positive integer, got {raw_f!r} — ignored")
                followers = None
        except (TypeError, ValueError):
            warn(f"goal_followers unreadable: {raw_f!r} — ignored")
            followers = None
    if not empty_d:
        s = str(raw_d).strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            try:
                date.fromisoformat(s)
                gdate = s
            except ValueError:
                warn(f"goal_date invalid: {raw_d!r} — ignored")
        else:
            warn(f"goal_date must be YYYY-MM-DD, got {raw_d!r} — ignored")
    if followers is None or gdate is None:
        if (followers is None) != (gdate is None) or (not empty_f or not empty_d):
            if followers is None or gdate is None:
                warn("goal_followers and goal_date must both be set — goal not active")
        return None, None
    return followers, gdate


def parse_daily_goals(cfg):
    """Optional posts/replies-per-day targets. Invalid values fall back to defaults."""
    posts, replies = 2, 10
    if not isinstance(cfg, dict):
        return posts, replies

    def _pos_int(raw, default, name):
        if raw in (None, "", False):
            return default
        try:
            v = int(raw)
            if v <= 0:
                warn(f"{name} must be a positive integer, got {raw!r} — using {default}")
                return default
            return v
        except (TypeError, ValueError):
            warn(f"{name} unreadable: {raw!r} — using {default}")
            return default

    return (
        _pos_int(cfg.get("goal_posts_per_day"), posts, "goal_posts_per_day"),
        _pos_int(cfg.get("goal_replies_per_day"), replies, "goal_replies_per_day"),
    )


def normalize_post(raw, naive_tz, account, src):
    """raw dict -> (post dict met alleen aanwezige velden, inferred_fields set) of None."""
    p, inferred = {}, set()
    url = raw.get("url")
    pid = raw.get("id")
    if pid is not None and str(pid).strip():
        pid = str(pid).strip()
        if re.fullmatch(r"\d+(\.0+)?", pid):
            pid = pid.split(".")[0]
    else:
        pid = id_from_url(url)
    if not pid:
        if raw.get("created_at") and raw.get("text"):
            pid = "gen-" + hashlib.sha1((str(raw.get("created_at")) + str(raw.get("text"))).encode()).hexdigest()[:12]
            warn(f"{src}: post without id/url — temporary id {pid} (dedupe on time+text)")
        else:
            warn(f"{src}: post without id, url, and time/text skipped")
            return None
    p["id"] = pid
    if url:
        p["url"] = str(url).strip()
    if raw.get("created_at") not in (None, ""):
        dt, tk = parse_dt(raw["created_at"], naive_tz)
        if dt is None:
            warn(f"{src}: unreadable date/time {raw['created_at']!r} for post {pid}")
        else:
            p["_dt"] = dt
            p["time_known"] = tk
    t = raw.get("type")
    if t not in (None, ""):
        nt = norm_enum(t, TYPE_MAP)
        if nt:
            p["type"] = nt
        else:
            warn(f"{src}: unknown type {t!r} for post {pid}")
    m = raw.get("media")
    if m not in (None, ""):
        nm = norm_enum(m, MEDIA_MAP)
        if nm:
            p["media"] = nm
        else:
            warn(f"{src}: unknown media type {m!r} for post {pid}")
    irh = norm_handle(raw.get("in_reply_to_handle"))
    if irh:
        p["in_reply_to_handle"] = irh
    irct = raw.get("in_reply_to_created_at")
    if irct not in (None, ""):
        pdt, _ptk = parse_dt(irct, naive_tz)
        if pdt is None:
            warn(f"{src}: unreadable in_reply_to_created_at {irct!r} for post {pid}")
        else:
            p["in_reply_to_created_at"] = pdt.astimezone(AMS).isoformat()
    if raw.get("text") not in (None, ""):
        p["text"] = str(raw["text"])
    for k in METRICS:
        if k in raw:
            v = parse_int(raw[k])
            if v is not None:
                p[k] = v
    for key in ("profile_image_url", "profile_image_url_https"):
        raw_url = raw.get(key)
        if raw_url and "pbs.twimg.com/profile_images" in str(raw_url):
            p[key] = str(raw_url).strip()
    # heuristieken als type ontbreekt (vooral CSV)
    if "type" not in p and raw.get("_infer_type"):
        txt = p.get("text", "")
        if re.match(r"^RT @\w+", txt):
            p["type"] = "repost"
        elif re.match(r"^@\w+", txt):
            p["type"] = "reply"
            if "in_reply_to_handle" not in p:
                p["in_reply_to_handle"] = re.match(r"^@(\w+)", txt).group(1)
                inferred.add("in_reply_to_handle")
        else:
            p["type"] = "post"
        inferred.add("type")
    apply_snowflake_time(p, src)
    return p, inferred


def post_capture_ts(rec_cap, file_cap, path):
    for c in (rec_cap, file_cap):
        if c:
            dt, _ = parse_dt(c, AMS)
            if dt:
                return dt.timestamp()
    d = date_from_filename(path)
    if d:
        return datetime.combine(d, dtime(23, 59), tzinfo=AMS).timestamp()
    return os.path.getmtime(path)


def load_posts_json(data_dir, account):
    recs = []
    pdir = os.path.join(data_dir, "posts")
    if not os.path.isdir(pdir):
        return recs
    paths = sorted(glob.glob(os.path.join(pdir, "*.json")) + glob.glob(os.path.join(pdir, "*.jsonl")))
    for path in paths:
        name = os.path.basename(path)
        items, file_cap = [], None
        try:
            with open(path, encoding="utf-8-sig") as f:
                if path.endswith(".jsonl"):
                    for ln, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            items.append(json.loads(line))
                        except json.JSONDecodeError as e:
                            warn(f"{name} line {ln}: invalid JSON ({e})")
                else:
                    d = json.load(f)
                    if isinstance(d, list):
                        items = d
                    elif isinstance(d, dict):
                        file_cap = d.get("captured_at")
                        items = d.get("posts") or []
                        if not isinstance(items, list):
                            warn(f"{name}: 'posts' is not a list")
                            items = []
        except Exception as e:  # noqa
            warn(f"Post file unreadable: {name} ({e})")
            continue
        n = 0
        NAIVE_HITS.clear()
        for idx, raw in enumerate(items):
            if not isinstance(raw, dict):
                warn(f"{name}: item {idx} is not an object")
                continue
            r = normalize_post(raw, AMS, account, name)
            if not r:
                continue
            ts = post_capture_ts(raw.get("captured_at"), file_cap, path)
            recs.append(((ts, 1, name, idx), r[0], r[1], name))
            n += 1
        if NAIVE_HITS:
            warn(f"{name}: {len(NAIVE_HITS)} created_at without a timezone (e.g. {NAIVE_HITS[0]!r}) — interpreted as Europe/Amsterdam")
        info(f"Posts JSON: {name}: {n} records")
    return recs


# CSV kolom-aliassen (genormaliseerd: lowercase, niet-alfanumeriek -> spatie)
CSV_ALIASES = {
    "id": ["post id", "tweet id", "id", "post-id", "postid", "tweet-id", "bericht id", "berichtid", "post nummer"],
    "url": ["url", "post link", "post url", "tweet permalink", "permalink", "link", "post permalink",
            "tweet link", "tweet url", "link naar post", "postlink", "post-link"],
    "text": ["text", "post text", "tweet text", "tekst", "posttekst", "post tekst", "inhoud", "content",
             "bericht", "tweet"],
    "_datetime": ["created at", "created_at", "datetime", "date time", "timestamp", "posted at",
                  "datum tijd", "datum en tijd", "geplaatst", "geplaatst op", "publicatiedatum", "gepubliceerd",
                  "tijdstempel", "post date", "tweet date"],
    "_date": ["date", "datum", "dag", "day"],
    "_time": ["time", "tijd", "tijdstip", "uur"],
    "impressions": ["impressions", "impressies", "weergaven", "vertoningen", "views", "impressie"],
    "likes": ["likes", "like", "vind ik leuks", "vind ik leuk", "favorites", "favorieten", "hartjes"],
    "replies": ["replies", "antwoorden", "reacties", "reply", "reply count"],
    "reposts": ["reposts", "retweets", "reposts retweets", "herposts", "repost", "retweet"],
    "quotes": ["quotes", "quote", "citaten", "quote posts", "quote tweets", "geciteerd", "citaat"],
    "bookmarks": ["bookmarks", "bladwijzers", "bookmark", "bladwijzer"],
    "profile_visits": ["profile visits", "profielbezoeken", "user profile clicks", "profile clicks",
                       "profielklikken", "profiel bezoeken", "profielbezoek"],
    "link_clicks": ["link clicks", "linkklikken", "url clicks", "link klikken", "klikken op link",
                    "linkkliks", "url klikken"],
    "new_follows": ["new follows", "nieuwe volgers", "follows", "new followers", "volgers erbij",
                    "nieuwe volgers via post"],
    "engagements": ["engagements", "engagement", "total engagements", "betrokkenheid", "interacties",
                    "engagements totaal", "totaal engagements"],
    "shares": ["shares", "share", "gedeeld", "delen", "keer gedeeld"],
    "detail_expands": ["detail expands", "details expanded", "detailuitbreidingen", "details uitgevouwen",
                       "detail uitklappen", "uitgeklapt"],
    "hashtag_clicks": ["hashtag clicks", "hashtagklikken", "hashtag klikken", "klikken op hashtag"],
    "permalink_clicks": ["permalink clicks", "permalinkklikken", "permalink klikken", "klikken op permalink"],
    "type": ["type", "post type", "posttype", "soort", "tweet type"],
    "media": ["media", "media type", "mediatype", "format", "formaat"],
    "in_reply_to_handle": ["in reply to", "in reply to handle", "reply to", "antwoord op", "reactie op",
                           "in antwoord op"],
    "in_reply_to_created_at": ["in reply to created at", "in_reply_to_created_at", "parent created at",
                               "parent time", "tijd originele post", "parent timestamp"],
}


def norm_header(h):
    h = (h or "").replace("\ufeff", "").strip().lower()
    return re.sub(r"[^0-9a-zà-ÿ]+", " ", h).strip()


ALIAS_LOOKUP = {}
for _field, _al in CSV_ALIASES.items():
    for _a in _al:
        ALIAS_LOOKUP.setdefault(norm_header(_a), _field)


def read_text_any(path):
    with open(path, "rb") as f:
        b = f.read()
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            t = b.decode(enc)
            if enc == "utf-16" and not (b.startswith(b"\xff\xfe") or b.startswith(b"\xfe\xff")):
                continue
            return t
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", errors="replace")


def load_posts_csv(data_dir, account, csv_tz):
    recs = []
    cdir = os.path.join(data_dir, "analytics-csv")
    if not os.path.isdir(cdir):
        return recs
    for path in sorted(glob.glob(os.path.join(cdir, "*.csv"))):
        name = os.path.basename(path)
        text = read_text_any(path)
        # Alleen het scheidingsteken bepalen (uit de kopregel); quoting altijd standaard '"'.
        # (csv.Sniffer kan een apostrof als quotechar kiezen en zo rijen samenvoegen.)
        first_line = text.lstrip("\ufeff").splitlines()[0] if text.strip() else ""
        delim = max([",", ";", "\t"], key=lambda c: first_line.count(c))
        rows = list(csv.reader(io.StringIO(text), delimiter=delim, quotechar='"', doublequote=True))
        rows = [r for r in rows if any(c.strip() for c in r)]
        if not rows:
            warn(f"CSV {name}: empty")
            continue
        header = rows[0]
        colmap, unmapped, dup = {}, [], []
        for i, h in enumerate(header):
            f = ALIAS_LOOKUP.get(norm_header(h))
            if f is None:
                unmapped.append(h)
            elif f in colmap:
                dup.append(h)
            else:
                colmap[f] = i
        mapped_desc = ", ".join(sorted(f.lstrip("_") for f in colmap))
        info(f"CSV {name}: delimiter {delim!r}, columns mapped: {mapped_desc}")
        if unmapped:
            warn(f"CSV {name}: UNMAPPED columns (ignored): {', '.join(repr(u) for u in unmapped)}")
        if dup:
            warn(f"CSV {name}: duplicate columns for the same field (ignored): {', '.join(repr(u) for u in dup)}")
        if not any(k in colmap for k in ("id", "url", "text")):
            warn(f"CSV {name}: no post id/url/text column — looks like an account daily summary, not a per-post export. Skipped.")
            continue
        has_dt = any(k in colmap for k in ("_datetime", "_date", "_time"))
        if not has_dt:
            warn(f"CSV {name}: no date/time column found — posts without a date are skipped")
        file_ts = post_capture_ts(None, None, path)
        n = 0
        NAIVE_HITS.clear()
        badlen = [i for i, r in enumerate(rows[1:], 2) if len(r) != len(header)]
        if badlen:
            warn(f"CSV {name}: {len(badlen)} row(s) with a mismatched column count (e.g. row {badlen[0]}) — check quoting")
        for ridx, row in enumerate(rows[1:], 2):
            def cell(f):
                i = colmap.get(f)
                if i is None or i >= len(row):
                    return None
                v = row[i].strip()
                return v if v != "" else None
            raw = {"_infer_type": True}
            for f in ("id", "url", "text", "type", "media", "in_reply_to_handle",
                      "in_reply_to_created_at") + tuple(METRICS):
                v = cell(f)
                if v is not None:
                    raw[f] = v
            dtv = cell("_datetime")
            dv, tv = cell("_date"), cell("_time")
            if dtv:
                raw["created_at"] = dtv
            elif dv and tv:
                full, tk = parse_dt(tv, csv_tz)
                raw["created_at"] = tv if (full and tk and re.search(r"\d{4}", tv)) else f"{dv} {tv}"
            elif dv or tv:
                raw["created_at"] = dv or tv
            r = normalize_post(raw, csv_tz, account, f"{name} r{ridx}")
            if not r:
                continue
            recs.append(((file_ts, 0, name, ridx), r[0], r[1], name))
            n += 1
        if NAIVE_HITS:
            warn(f"CSV {name}: {len(NAIVE_HITS)} timestamp(s) without a timezone (e.g. {NAIVE_HITS[0]!r}) — "
                 f"interpreted as {csv_tz.key}. Set 'csv_timezone' in data/config.json if this is wrong.")
        info(f"CSV {name}: {n} post rows read (of {len(rows) - 1} data rows)")
    return recs


def merge_posts(recs, account):
    recs.sort(key=lambda r: r[0])
    posts = {}
    for _, p, inferred, src in recs:
        cur = posts.get(p["id"])
        if cur is None:
            cur = {"id": p["id"], "_inferred": set(), "sources": []}
            posts[p["id"]] = cur
        for k, v in p.items():
            if k == "id":
                continue
            if k in inferred and k in cur and k not in cur["_inferred"]:
                continue  # expliciete waarde niet overschrijven met een gok
            if k in ("_dt", "time_known", "time_source"):
                # Expliciete tijd wint altijd van snowflake/datum-only.
                if cur.get("time_source") == "explicit" and p.get("time_source") != "explicit":
                    continue
                if k in ("_dt", "time_known") and not p.get("time_known", True) and cur.get("time_known") \
                        and "_dt" in cur and cur["_dt"].astimezone(AMS).date() == p["_dt"].astimezone(AMS).date():
                    continue  # datum-zonder-tijd overschrijft geen bekende tijd op dezelfde dag
            cur[k] = v
            if k in inferred:
                cur["_inferred"].add(k)
            else:
                cur["_inferred"].discard(k)
        if src not in cur["sources"]:
            cur["sources"].append(src)
    out = []
    acc = (account or "").lower()
    for p in posts.values():
        if "_dt" not in p:
            warn(f"Post {p['id']}: no created_at — not included in the dashboard")
            continue
        loc = p["_dt"].astimezone(AMS)
        typ = p.get("type") or "post"
        irh = p.get("in_reply_to_handle")
        imp = p.get("impressions")
        eng_c = sum(p.get(k) or 0 for k in ER_COMPONENTS)
        has_any_eng = any(p.get(k) is not None for k in ER_COMPONENTS)
        eng_c = eng_c if has_any_eng else None
        if p.get("engagements") is not None:
            eng_used, er_src = p["engagements"], "x"
        elif eng_c is not None:
            eng_used, er_src = eng_c, "berekend"
        else:
            eng_used, er_src = None, None
        o = {
            "id": p["id"],
            "url": p.get("url") or (
                f"https://x.com/{account}/status/{p['id']}" if account
                else f"https://x.com/i/web/status/{p['id']}"
            ),
            "created_at": loc.isoformat(),
            "local_date": loc.date().isoformat(),
            "local_time": loc.strftime("%H:%M") if p.get("time_known", True) else None,
            "weekday": loc.weekday(),
            "hour": loc.hour if p.get("time_known", True) else None,
            "time_source": p.get("time_source") or ("explicit" if p.get("time_known", True) else "date"),
            "type": typ,
            "type_inferred": "type" in p["_inferred"] or "type" not in p,
            "media": p.get("media"),
            "in_reply_to_handle": irh,
            "in_reply_to_created_at": p.get("in_reply_to_created_at"),
            "self_reply": bool(irh and acc and irh.lower() == acc),
            "text": p.get("text", ""),
            "eng_computed": eng_c,
            "eng_used": eng_used,
            "er_source": er_src,
            "er": (eng_used / imp) if (imp and imp > 0 and eng_used is not None) else None,
            "sources": p["sources"],
        }
        for k in METRICS:
            o[k] = p.get(k)
        for key in ("profile_image_url", "profile_image_url_https"):
            if p.get(key):
                o[key] = p[key]
        out.append(o)
    out.sort(key=lambda o: o["created_at"])
    return out


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return (sum(xs) / len(xs)) if xs else None


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    mid = n // 2
    return xs[mid] if n % 2 else (xs[mid - 1] + xs[mid]) / 2


def html_esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def redact_mentions(text, owner):
    if not text:
        return text
    owner_l = (owner or "").lower()

    def repl(m):
        if owner_l and m.group(1).lower() == owner_l:
            return m.group(0)
        return "@…"

    return MENTION_RE.sub(repl, str(text))


def size_bucket_label(n):
    if n < 1000:
        return "<1k"
    if n < 10000:
        return "1k–10k"
    if n < 100000:
        return "10k–100k"
    return ">100k"


def freq_bucket_label(n):
    if n <= 1:
        return "1×"
    if n <= 4:
        return "2–4×"
    return "5×+"


def load_target_accounts(data_dir):
    path = os.path.join(data_dir, "target_accounts.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:  # noqa
        warn(f"target_accounts.json unreadable ({e}) — grouping by reply frequency")
        return None
    out = {}
    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, list):
        items = ((item.get("handle") or item.get("account"), item.get("followers"))
                 for item in raw if isinstance(item, dict))
    else:
        items = []
    for handle, followers in items:
        h = norm_handle(handle)
        n = parse_int(followers)
        if h and n is not None and n >= 0:
            out[h.lower()] = n
    if not out:
        warn("target_accounts.json contains no handle→followers pairs — grouping by reply frequency")
        return None
    info(f"target_accounts.json: {len(out)} account(s)")
    return out


def _bucket_row(label, posts, accounts):
    n = len(posts)
    imps = [p.get("impressions") for p in posts if p.get("impressions") is not None]
    vis_sum = sum(p.get("profile_visits") or 0 for p in posts)
    fol_sum = sum(p.get("new_follows") or 0 for p in posts)
    return {
        "label": label,
        "n_replies": n,
        "n_accounts": len(accounts),
        "mean_impressions": _mean(imps),
        "median_impressions": _median(imps),
        "visits_per_reply": (vis_sum / n) if n else None,
        "follows_per_reply": (fol_sum / n) if n else None,
    }


def reply_aggregates(posts, targets):
    replies = [p for p in posts
               if p.get("type") == "reply" and not p.get("self_reply") and p.get("in_reply_to_handle")]
    by = {}
    for p in replies:
        k = p["in_reply_to_handle"].lower()
        by.setdefault(k, []).append(p)
    groups = {}
    if targets:
        kind = "size"
        order = SIZE_BUCKET_ORDER
        for k, ps in by.items():
            if k not in targets:
                continue
            lab = size_bucket_label(targets[k])
            g = groups.setdefault(lab, {"posts": [], "accounts": set()})
            g["posts"].extend(ps)
            g["accounts"].add(k)
    else:
        kind = "frequency"
        order = FREQ_BUCKET_ORDER
        for k, ps in by.items():
            lab = freq_bucket_label(len(ps))
            g = groups.setdefault(lab, {"posts": [], "accounts": set()})
            g["posts"].extend(ps)
            g["accounts"].add(k)
    buckets = []
    hidden = 0
    for lab in order:
        g = groups.get(lab)
        if not g:
            continue
        if len(g["accounts"]) < MIN_BUCKET_ACCOUNTS:
            hidden += 1
            continue
        buckets.append(_bucket_row(lab, g["posts"], g["accounts"]))
    return buckets, kind, hidden


def handles_in_payload(payload, owner):
    found = set()
    fol = payload.get("followers") or {}
    for key in ("new", "lost", "unavailable", "verified_unfollowers"):
        for e in fol.get(key) or []:
            if isinstance(e, dict) and e.get("handle"):
                found.add(e["handle"])
            elif isinstance(e, str):
                found.add(e)
    nfb = fol.get("not_following_back") or {}
    for h in nfb.get("handles") or []:
        found.add(h)
    for p in payload.get("posts") or []:
        if p.get("in_reply_to_handle"):
            found.add(p["in_reply_to_handle"])
        for m in MENTION_RE.finditer(p.get("text") or ""):
            found.add(m.group(1))
    owner_l = (owner or "").lower()
    return {h for h in found if h and h.lower() != owner_l}


def scrub_text(msg, handles, paths):
    msg = str(msg or "")
    for p in paths:
        if p:
            msg = msg.replace(p, "[omitted]")
    for h in sorted(handles, key=len, reverse=True):
        msg = re.sub(r"(?i)(?<![A-Za-z0-9_])" + re.escape(h) + r"(?![A-Za-z0-9_])", "…", msg)
    return redact_mentions(msg, None)


def is_demo_build(cfg, data_dir, posts=None) -> bool:
    """True for fixture/demo inputs — never inferred from a real display name alone."""
    if isinstance(cfg, dict) and cfg.get("demo") is True:
        return True
    norm = os.path.normpath(os.path.abspath(data_dir or "")).replace("\\", "/")
    if norm.rstrip("/").endswith("/test-fixtures/data"):
        return True
    for p in posts or []:
        if "TESTFIXTURE" in str((p or {}).get("text") or ""):
            return True
    return False


def owner_url(url, owner, pid):
    if not url:
        return url
    m = re.search(r"(?i)(?:x|twitter)\.com/([A-Za-z0-9_]+)(?:/|$)", url)
    if not m:
        return url
    if owner and m.group(1).lower() == owner.lower():
        return url
    if owner:
        return f"https://x.com/{owner}/status/{pid}"
    return "https://x.com/i/web/status/" + str(pid)


def to_public_payload(payload, owner, data_dir, followers_dir, buckets, bucket_kind):
    sensitive = handles_in_payload(payload, owner)
    paths = [data_dir, followers_dir, payload.get("meta", {}).get("out")]
    posts = []
    for p in payload.get("posts") or []:
        q = dict(p)
        q.pop("in_reply_to_handle", None)
        q.pop("in_reply_to_created_at", None)
        q.pop("profile_image_url", None)
        q.pop("profile_image_url_https", None)
        q["sources"] = []
        if "text" in q:
            q["text"] = redact_mentions(q["text"], owner)
        q["url"] = owner_url(q.get("url"), owner, q.get("id"))
        posts.append(q)
    fol = payload.get("followers") or {}
    snaps = []
    for s in fol.get("snapshots") or []:
        t = dict(s)
        t["notes"] = None
        t["source"] = "snapshot"
        t.pop("profile_image_url", None)
        t.pop("profile_image_url_https", None)
        snaps.append(t)
    fol_pub = {
        "snapshots": snaps,
        "new": [],
        "lost": [],
        "unavailable": [],
        "verified_unfollowers": [],
        "not_following_back": None,
        "latest_following_date": None,
        "latest_following_complete": None,
        "latest_following_loaded": None,
        "latest_following_profile": None,
    }
    meta = dict(payload.get("meta") or {})
    meta["data_dir"] = None
    meta["followers_dir"] = None
    meta["out"] = None
    meta["reply_bucket_kind"] = bucket_kind
    log = []
    for item in payload.get("log") or []:
        msg = scrub_text(item.get("msg"), sensitive, paths)
        log.append({"level": item.get("level"), "msg": msg})
    log.append({"level": "info", "msg": "Public build: handles, names, and paths omitted."})
    return {
        "meta": meta,
        "followers": fol_pub,
        "posts": posts,
        "reply_buckets": buckets,
        "log": log,
    }


def head_extra(mode, cfg, account, display_name):
    if mode != "public":
        return ""
    site = str(cfg.get("site_url") or "").rstrip("/")
    if display_name and account:
        title = f"{display_name} (@{account})"
    elif display_name:
        title = display_name
    elif account:
        title = f"@{account}"
    else:
        title = "X growth dashboard"
    desc = cfg.get("og_description") or (
        "Public growth dashboard: your own growth and aggregated replies, without other people's names."
    )
    og_img = cfg.get("og_image_url") or (
        f"{site}/assets/og-image.png" if site else "/assets/og-image.png"
    )
    parts = []
    if site:
        parts.append(f'<link rel="canonical" href="{html_esc(site)}">')
    parts.extend([
        f'<meta property="og:title" content="{html_esc(title)}">',
        f'<meta property="og:description" content="{html_esc(desc)}">',
        f'<meta property="og:image" content="{html_esc(og_img)}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{html_esc(title)}">',
        f'<meta name="twitter:description" content="{html_esc(desc)}">',
        f'<meta name="twitter:image" content="{html_esc(og_img)}">',
    ])
    if site:
        parts.append(f'<meta property="og:url" content="{html_esc(site)}">')
        parts.append('<meta property="og:type" content="website">')
    return "\n".join(parts)


def vendor_font_css():
    parts = []
    for weight, path in VENDOR_FONTS:
        if not os.path.isfile(path):
            warn(f"Vendored font missing: {path}")
            continue
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        parts.append(
            f"@font-face{{font-family:'Inter';font-style:normal;font-weight:{weight};"
            f"font-display:swap;src:url(data:font/woff2;base64,{b64}) format('woff2');}}"
        )
    return "\n".join(parts)


def vendor_echarts_script():
    if not os.path.isfile(VENDOR_ECHARTS):
        warn(f"Vendored ECharts missing: {VENDOR_ECHARTS}")
        return "<!--__ECHARTS__-->"
    with open(VENDOR_ECHARTS, encoding="utf-8") as f:
        js = f.read().replace("</", "<\\/")
    return f"<script>\n{js}\n</script>"


def inject_vendors(html):
    html = html.replace("/*__INTER__*/", vendor_font_css(), 1)
    html = html.replace("<!--__ECHARTS__-->", vendor_echarts_script(), 1)
    return html


def write_sidecars(out_html, mode):
    dest = os.path.dirname(os.path.abspath(out_html))
    os.makedirs(dest, exist_ok=True)
    # Do not overwrite repo-root robots.txt when writing local index.html.
    if os.path.abspath(dest) == os.path.abspath(BASE):
        return
    if mode == "public":
        robots = "User-agent: *\nAllow: /\n"
        headers = (
            "/*\n"
            "  X-Content-Type-Options: nosniff\n"
            "  Referrer-Policy: no-referrer\n"
        )
    else:
        robots = "User-agent: *\nDisallow: /\n"
        headers = (
            "/*\n"
            "  X-Robots-Tag: noindex, nofollow\n"
            "  Cache-Control: private, no-store\n"
            "  X-Content-Type-Options: nosniff\n"
            "  Referrer-Policy: no-referrer\n"
        )
    with open(os.path.join(dest, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(robots)
    with open(os.path.join(dest, "_headers"), "w", encoding="utf-8") as f:
        f.write(headers)
    if os.path.isfile(ASSETS_OG):
        adest = os.path.join(dest, "assets")
        os.makedirs(adest, exist_ok=True)
        dest_png = os.path.join(adest, "og-image.png")
        if os.path.abspath(ASSETS_OG) != os.path.abspath(dest_png):
            shutil.copy2(ASSETS_OG, dest_png)


def avatar_assets_dir(out_html):
    dest_dir = os.path.dirname(os.path.abspath(out_html)) or "."
    return os.path.join(dest_dir, "assets")


def avatar_dest(out_html, ext=".jpg"):
    if ext and not str(ext).startswith("."):
        ext = "." + ext
    return os.path.join(avatar_assets_dir(out_html), AVATAR_STEM + (ext or ".jpg"))


def looks_like_image(data):
    if not data or len(data) < 8:
        return False
    if data[:3] == b"\xff\xd8\xff":
        return True
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return True
    return False


def sniff_image_ext(data, content_type=None):
    if data and data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data and data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data and data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    ct = str(content_type or "").lower()
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"
    if "gif" in ct:
        return ".gif"
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    return ".jpg"


def upgrade_pbs_avatar(url):
    u = str(url or "").strip()
    if "pbs.twimg.com/profile_images" not in u:
        return u
    if _PBS_SIZE_RE.search(u):
        return _PBS_SIZE_RE.sub(r"_400x400\2", u)
    return u


def export_owner_avatar_url(posts, snapshots):
    """Owner profile image only — never follower/reply-target avatars."""
    for row in list(posts or []) + list(snapshots or []):
        if not isinstance(row, dict):
            continue
        for key in ("profile_image_url", "profile_image_url_https"):
            raw = row.get(key)
            if raw and "pbs.twimg.com/profile_images" in str(raw):
                return upgrade_pbs_avatar(str(raw).strip())
    return ""


def _lookup_disabled(cfg):
    lookup = (cfg or {}).get("avatar_lookup")
    return lookup is False or (isinstance(lookup, str) and str(lookup).strip().lower() in ("0", "false", "no"))


def avatar_candidates(cfg, account, posts, snapshots=None):
    """Ordered (url, source) pairs. Config override is exclusive."""
    cfg = cfg or {}
    override = str(cfg.get("profile_image_url") or "").strip()
    if override:
        if re.match(r"^https?://", override, re.I):
            override = upgrade_pbs_avatar(override)
        return [(override, "config")]
    out = []
    exported = export_owner_avatar_url(posts, snapshots)
    if exported:
        out.append((exported, "export"))
    if _lookup_disabled(cfg):
        return out
    handle = norm_handle(account) or ""
    if handle:
        out.append((FXTWITTER_TMPL.format(handle=handle), "fxtwitter"))
        out.append((UNAVATAR_TMPL.format(handle=handle), "unavatar"))
    return out


def resolve_avatar_url(cfg, account, posts, snapshots=None):
    cands = avatar_candidates(cfg, account, posts, snapshots)
    if not cands:
        return "", ""
    return cands[0]


def avatar_cache_dir(cfg, data_dir=None):
    cfg = cfg or {}
    raw = str(cfg.get("avatar_cache") or os.environ.get("XDASH_AVATAR_CACHE") or "").strip()
    if raw:
        if not os.path.isabs(raw):
            raw = os.path.join(data_dir or "", raw)
        return os.path.abspath(raw)
    if data_dir:
        return os.path.join(os.path.abspath(data_dir), ".avatar-cache")
    return None


def _read_cache_meta(cache_dir):
    path = os.path.join(cache_dir or "", "meta.json")
    if not cache_dir or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            meta = json.load(f)
        return meta if isinstance(meta, dict) else None
    except Exception:
        return None


def _cache_image_path(cache_dir, meta=None):
    meta = meta if meta is not None else _read_cache_meta(cache_dir)
    if cache_dir and meta and meta.get("filename"):
        p = os.path.join(cache_dir, os.path.basename(str(meta["filename"])))
        if os.path.isfile(p):
            return p
    if not cache_dir or not os.path.isdir(cache_dir):
        return None
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        p = os.path.join(cache_dir, AVATAR_STEM + ext)
        if os.path.isfile(p):
            return p
    return None


def cache_is_fresh(meta, today):
    if not meta or not today:
        return False
    return str(meta.get("fetched_on") or "") == str(today)


def read_avatar_source(url, data_dir=None, timeout=6):
    if not url:
        raise ValueError("empty avatar url")
    local = url
    if url.startswith("file://"):
        local = url[7:]
    if not re.match(r"^https?://", url, re.I):
        if not os.path.isabs(local):
            local = os.path.join(data_dir or "", local)
        if os.path.isfile(local):
            with open(local, "rb") as f:
                return f.read(2_000_000)
        raise FileNotFoundError(local)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "x-growth-assistant-avatar"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(2_000_000)


def write_avatar_file(dest, data):
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    tmp = dest + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dest)


def _write_cache(cache_dir, data, ext, source, today):
    if not cache_dir:
        return None
    name = AVATAR_STEM + ext
    dest = os.path.join(cache_dir, name)
    write_avatar_file(dest, data)
    meta = {"fetched_on": today or "", "source": source, "filename": name}
    mp = os.path.join(cache_dir, "meta.json")
    tmp = mp + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f)
    os.replace(tmp, mp)
    return dest


def _copy_to_build(src, out_html):
    ext = os.path.splitext(src)[1] or ".jpg"
    dest = avatar_dest(out_html, ext)
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    if os.path.abspath(src) != os.path.abspath(dest):
        shutil.copy2(src, dest)
    return dest


def _parse_fxtwitter_avatar(raw):
    if looks_like_image(raw):
        return None
    payload = json.loads(raw.decode("utf-8", errors="replace"))
    if not isinstance(payload, dict):
        raise ValueError("fxtwitter: not an object")
    user = payload.get("user") if isinstance(payload.get("user"), dict) else payload
    url = user.get("avatar_url") or user.get("avatar") or ""
    if not url:
        raise ValueError("fxtwitter: no avatar_url")
    return upgrade_pbs_avatar(str(url).strip())


def load_avatar_bytes(url, loader, source=""):
    data = loader(url)
    if source == "fxtwitter" or "api.fxtwitter.com" in str(url):
        img_url = _parse_fxtwitter_avatar(data)
        if img_url:
            data = loader(img_url)
    if not looks_like_image(data):
        raise ValueError("response is not an image")
    return data


def _existing_build_avatar(out_html):
    assets = avatar_assets_dir(out_html)
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        p = os.path.join(assets, AVATAR_STEM + ext)
        if os.path.isfile(p):
            return p
    return None


def place_owner_avatar(cfg, account, posts, out_html, snapshots=None, data_dir=None,
                       fetch_fn=None, today=None):
    """Write assets/avatar.{png,jpg} next to the HTML. Never raises to the caller."""
    try:
        if today is None:
            today = datetime.now(AMS).date().isoformat()
        cache_dir = avatar_cache_dir(cfg, data_dir)
        cached = _cache_image_path(cache_dir)
        meta = _read_cache_meta(cache_dir)
        cands = avatar_candidates(cfg, account, posts, snapshots)
        http_only = bool(cands) and all(re.match(r"^https?://", u, re.I) for u, _ in cands)
        if cached and http_only and cache_is_fresh(meta, today):
            return _copy_to_build(cached, out_html), "cache"
        loader = fetch_fn or (lambda u: read_avatar_source(u, data_dir))
        last_err = None
        for url, src in cands:
            try:
                data = load_avatar_bytes(url, loader, src)
                ext = sniff_image_ext(data)
                _write_cache(cache_dir, data, ext, src, today)
                dest = avatar_dest(out_html, ext)
                write_avatar_file(dest, data)
                return dest, src
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
        if cached:
            if last_err:
                warn(f"Owner avatar fetch failed ({last_err}) — using cached file")
            return _copy_to_build(cached, out_html), "kept"
        prev = _existing_build_avatar(out_html)
        if prev:
            if last_err:
                warn(f"Owner avatar fetch failed ({last_err}) — keeping previous file")
            return prev, "kept"
        if last_err:
            warn(f"Owner avatar fetch failed ({last_err}) — initials fallback")
        elif not cands:
            pass
        return None, "missing"
    except Exception as e:  # noqa: BLE001 — avatar must never fail the build
        prev = _existing_build_avatar(out_html)
        if prev:
            warn(f"Owner avatar fetch failed ({e}) — keeping previous file")
            return prev, "kept"
        warn(f"Owner avatar fetch failed ({e}) — initials fallback")
        return None, "missing"


DEFAULT_DATA = os.path.join(BASE, "data")
FIXTURE_DATA = os.path.join(BASE, "test-fixtures", "data")
FIXTURE_TODAY = "2026-09-25"


def data_has_real_inputs(data_dir):
    for pat in (
        os.path.join(data_dir, "analytics-csv", "*.csv"),
        os.path.join(data_dir, "posts", "*.json"),
        os.path.join(data_dir, "posts", "*.jsonl"),
        os.path.join(data_dir, "followers", "*.json"),
    ):
        if glob.glob(pat):
            return True
    return False


def resolve_build_mode(cli_mode, cfg):
    if cli_mode in ("public", "private"):
        return cli_mode
    cfg_mode = str((cfg or {}).get("mode") or "").strip().lower()
    if cfg_mode in ("public", "private"):
        return cfg_mode
    return "public"


def maybe_use_demo_fixtures(data_dir, using_default):
    if not using_default or data_has_real_inputs(data_dir):
        return data_dir, False
    script = os.path.join(BASE, "test-fixtures", "make_fixtures.py")
    print("No real inputs in ./data — generating bundled demo fixtures (public by default).")
    r = subprocess.run([sys.executable, script], cwd=BASE)
    if r.returncode != 0:
        sys.exit(r.returncode or 1)
    return os.path.abspath(FIXTURE_DATA), True


def enforce_public_leak_check(html_path, data_dir):
    script = os.path.join(BASE, "scripts", "check_public_leaks.py")
    r = subprocess.run([sys.executable, script, html_path, data_dir], cwd=BASE)
    if r.returncode != 0:
        print("Refuse: public leak check failed.", file=sys.stderr)
        sys.exit(r.returncode or 1)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Build the X growth dashboard (index.html)")
    ap.add_argument("--data", default=DEFAULT_DATA, help="data directory (default: ./data; empty default dir uses demo fixtures)")
    ap.add_argument("--followers-dir", default=None,
                    help="extra follower snapshots (read-only; no default)")
    ap.add_argument("--no-followers", action="store_true",
                    help="no extra follower snapshots (ignores --followers-dir)")
    ap.add_argument("--mode", choices=("public", "private"), default=None,
                    help="public = shareable, no other people's handles (default). private = explicit opt-in")
    ap.add_argument("--out", default=os.path.join(BASE, "index.html"), help="output file")
    ap.add_argument("--today", default=None, help="reference date YYYY-MM-DD (default: today, Europe/Amsterdam)")
    args = ap.parse_args()

    using_default_data = os.path.abspath(args.data) == os.path.abspath(DEFAULT_DATA)
    data_dir, used_fixtures = maybe_use_demo_fixtures(os.path.abspath(args.data), using_default_data)
    cfg = {}
    cfg_path = os.path.join(data_dir, "config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as f:
                cfg = json.load(f)
            info(f"Config loaded: {cfg_path}")
        except Exception as e:  # noqa
            warn(f"config.json unreadable: {e}")
    account = norm_handle(cfg.get("account")) or ""
    display_name = str(cfg.get("display_name") or "").strip()
    site_url = str(cfg.get("site_url") or "").strip()
    repo_url = str(cfg.get("repo_url") or "").strip()
    og_image_url = str(cfg.get("og_image_url") or "").strip()
    lang = "en"
    try:
        csv_tz = ZoneInfo(cfg.get("csv_timezone", "UTC"))
    except Exception:  # noqa
        warn(f"Unknown csv_timezone {cfg.get('csv_timezone')!r}, using UTC")
        csv_tz = ZoneInfo("UTC")
    goal_followers, goal_date = parse_goal(cfg)
    goal_posts_per_day, goal_replies_per_day = parse_daily_goals(cfg)
    mode = resolve_build_mode(args.mode, cfg)

    now = datetime.now(AMS)
    today = args.today or (FIXTURE_TODAY if used_fixtures else now.date().isoformat())
    acc_lbl = f"@{account}" if account else "(no account in config)"
    print(f"X growth dashboard build — {acc_lbl}, mode={mode}, reference date {today} (Europe/Amsterdam)")
    if mode != "public":
        print(f"Data directory: {data_dir}")

    extra_dir = None
    if not args.no_followers:
        extra_dir = args.followers_dir
    if extra_dir:
        extra_dir = os.path.abspath(extra_dir)
        if mode != "public":
            print(f"Extra follower directory (read-only): {extra_dir}")
    days = load_followers(extra_dir, data_dir)
    fol = compute_follower_events(days)
    for s in fol["snapshots"]:
        info(f"  {s['date']}: followers(profile)={s['followers_count']} following(profile)={s['following_count']} "
             f"handles collected={s['collected_count']} complete={s['complete']} "
             f"following list={s['following_collected']} [{s['source']}]")
    cnt = {}
    for e in fol["lost"]:
        cnt[e["status"]] = cnt.get(e["status"], 0) + 1
    if fol["verified_unfollowers"] and mode != "public":
        info(f"verified_unfollowers: {len(fol['verified_unfollowers'])} account(s)")
    info(f"Follower events: new={sum(1 for e in fol['new'] if e['status']=='nieuw')}, "
         f"returned={sum(1 for e in fol['new'] if e['status']=='terug')}, left list: {format_left_list(cnt)}")
    if not fol["latest_following_date"]:
        warn("No following list (following_handles) in snapshots: follow-back status and 'does not follow back' unavailable")

    recs = load_posts_json(data_dir, account) + load_posts_csv(data_dir, account, csv_tz)
    posts = enrich_posts(merge_posts(recs, account), account)
    info(f"Posts after merge (unique ids): {len(posts)}")
    if posts:
        nx = sum(1 for p in posts if p["er_source"] == "x")
        nb = sum(1 for p in posts if p["er_source"] == "berekend")
        info(f"ER source: {nx} post(s) with X engagements, {nb} calculated; "
             f"{sum(1 for p in posts if p['hour'] is None)} without time (date only); "
             f"{sum(1 for p in posts if not p['media'])} without media info; "
             f"{sum(1 for p in posts if p['type_inferred'])} with inferred type")
    if not posts:
        info("No post data found — post sections show an empty state")

    targets = load_target_accounts(data_dir)
    buckets, bucket_kind, hidden_b = reply_aggregates(posts, targets)
    if hidden_b:
        info(f"Public aggregates: {hidden_b} group(s) with < {MIN_BUCKET_ACCOUNTS} accounts omitted")

    payload = {
        "meta": {
            "account": account,
            "display_name": display_name,
            "site_url": site_url,
            "repo_url": repo_url,
            "og_image_url": og_image_url,
            "lang": lang,
            "mode": mode,
            "today": today,
            "generated_at": now.isoformat(timespec="seconds"),
            "data_dir": data_dir,
            "followers_dir": extra_dir,
            "out": os.path.abspath(args.out),
            "insights": INSIGHTS_META,
            "goal": {
                "followers": goal_followers,
                "date": goal_date,
                "posts_per_day": goal_posts_per_day,
                "replies_per_day": goal_replies_per_day,
            },
            "reply_bucket_kind": bucket_kind,
            "roi": {
                "low_min_replies": LOW_ROI_MIN_REPLIES,
                "low_max_mean_impressions": LOW_ROI_MAX_MEAN_IMPRESSIONS,
                "top_min_replies": ROI_TOP_MIN_REPLIES,
            },
            "avatar": "",
            "demo": is_demo_build(cfg, data_dir, posts),
        },
        "followers": fol,
        "posts": posts,
        "reply_buckets": buckets,
        "log": LOG,
    }
    if mode == "public":
        payload = to_public_payload(payload, account, data_dir, extra_dir, buckets, bucket_kind)
        payload["meta"]["mode"] = "public"
        payload["meta"]["account"] = account
        payload["meta"]["display_name"] = display_name
        payload["meta"]["site_url"] = site_url
        payload["meta"]["repo_url"] = repo_url
        payload["meta"]["lang"] = lang
        payload["meta"]["today"] = today
        payload["meta"]["generated_at"] = now.isoformat(timespec="seconds")
        payload["meta"]["insights"] = INSIGHTS_META
        payload["meta"]["goal"] = {
            "followers": goal_followers,
            "date": goal_date,
            "posts_per_day": goal_posts_per_day,
            "replies_per_day": goal_replies_per_day,
        }
        payload["meta"]["roi"] = {
            "low_min_replies": LOW_ROI_MIN_REPLIES,
            "low_max_mean_impressions": LOW_ROI_MAX_MEAN_IMPRESSIONS,
            "top_min_replies": ROI_TOP_MIN_REPLIES,
        }
        payload["meta"]["demo"] = is_demo_build(cfg, data_dir, posts)
    out = os.path.abspath(args.out)
    try:
        avatar_path, avatar_how = place_owner_avatar(
            cfg, account, posts, out,
            snapshots=fol.get("snapshots") if isinstance(fol, dict) else None,
            data_dir=data_dir,
            today=today,
        )
        if avatar_path:
            payload["meta"]["avatar"] = "assets/" + os.path.basename(avatar_path)
            info(f"Owner avatar: assets/{os.path.basename(avatar_path)} ({avatar_how})")
        else:
            payload["meta"]["avatar"] = ""
            info("Owner avatar: initials fallback")
    except Exception as e:  # noqa: BLE001
        warn(f"Owner avatar step failed ({e}) — initials fallback")
        payload["meta"]["avatar"] = ""
    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = tpl.replace("/*__DATA__*/{}", blob)
    html = html.replace("__HTML_LANG__", "en")
    html = html.replace("__MODE__", mode)
    html = html.replace("<!--__HEAD_EXTRA__-->", head_extra(mode, cfg, account, display_name))
    html = inject_vendors(html)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, out)
    write_sidecars(out, mode)
    print(f"OK — wrote: {out}  ({len(html)//1024} KB) mode={mode}")
    print(f"Open: file://{out}")
    if mode == "public":
        enforce_public_leak_check(out, data_dir)


if __name__ == "__main__":
    main()
