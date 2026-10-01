#!/usr/bin/env python3
"""Genereert FICTIEVE testdata in test-fixtures/data/ (NOOIT in ../data/ zetten).
Dekt alle secties: canonieke + extra-formaat snapshots, capture-gat, verwijderd/geschorst,
echte ontvolgers, following-lijst, posts JSON + JSONL + overschrijvende snapshot,
CSV met Nederlandse headers (;-gescheiden) en CSV met Engelse (oude) X-headers."""
import csv, json, os, random, shutil
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

AMS = ZoneInfo("Europe/Amsterdam"); UTC = ZoneInfo("UTC")
R = random.Random(42)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
shutil.rmtree(OUT, ignore_errors=True)
for d in ("followers", "posts", "analytics-csv"):
    os.makedirs(os.path.join(OUT, d))

START, END = date(2026, 8, 20), date(2026, 9, 25)
days = [START + timedelta(i) for i in range((END - START).days + 1)]

# ---------------- followers
followers = [f"test_volger{i:03d}" for i in range(80)] + ["gap_user", "deleted_acct", "unfollower_a", "unfollower_b",
                                                           "unfollower_c", "unfollower_d"]
following = [f"test_volger{i:03d}" for i in range(0, 80, 2)] + ["unfollower_a", "celebrity_x", "celebrity_y", "gap_user",
                                                               "unfollower_c", "unfollower_d"]
counter = 200
for d in days:
    if d == date(2026, 9, 5):
        continue  # ontbrekende dag
    # nieuwe volgers
    for _ in range(R.randint(0, 3)):
        h = f"nieuw_{counter}"; counter += 1
        followers.append(h)
        if R.random() < 0.4:
            following.append(h)
    if d == date(2026, 9, 18):
        followers.remove("unfollower_a")   # echte ontvolger, eigenaar volgt nog -> kandidaat
    if d == date(2026, 9, 20):
        followers.remove("unfollower_b")   # echte ontvolger, eigenaar volgt niet
    if d == date(2026, 9, 15):
        followers.remove("deleted_acct")   # verwijderd/geschorst
    if d == date(2026, 9, 22):
        followers.remove("unfollower_c")   # onvolledige snapshot, maar handmatig geverifieerd -> ontvolgd
        followers.remove("unfollower_d")   # onvolledige snapshot, niet geverifieerd -> mogelijk
    snap_followers = list(followers)
    if d == date(2026, 9, 10):
        # extra-formaat, onvolledige capture: gap_user niet geladen
        snap_followers = [h for h in snap_followers if h != "gap_user"]
        doc = {"account": "demo_owner", "captured_at": f"{d}T09:30:00.123+02:00",
               "profile_followers": len(followers), "profile_following": None,
               "collected_count": len(snap_followers), "complete": False,
               "handles": snap_followers, "notes": "TESTFIXTURE extra-formaat, onvolledig"}
        with open(os.path.join(OUT, "followers", f"snapshot-{d:%Y%m%d}-093000.json"), "w") as f:
            json.dump(doc, f, indent=2)
        continue
    fol_out, fol_complete = list(following), True
    if d == END:
        # following-lijst onvolledig: unfollower_d, celebrity_y en een paar test_volgers niet geladen
        drop = {"unfollower_d", "celebrity_y", "test_volger000", "test_volger002", "test_volger004"}
        fol_out, fol_complete = [h for h in following if h not in drop], False
    doc = {"account": "demo_owner", "date": d.isoformat(), "captured_at": f"{d}T09:45:00+02:00",
           "profile_followers": len(followers), "profile_following": len(following),
           "collected_count": len(snap_followers), "complete": d != date(2026, 9, 22),
           "handles": snap_followers, "following_handles": fol_out, "following_complete": fol_complete,
           "unavailable": [{"handle": "deleted_acct", "reason": "geschorst"}] if d >= date(2026, 9, 15) else [],
           "notes": "TESTFIXTURE"}
    if d >= date(2026, 9, 22):
        doc["verified_unfollowers"] = [{"handle": "unfollower_c", "checked_at": "2026-09-22T11:00:00+02:00",
                                        "note": "TESTFIXTURE profiel gecontroleerd"}]
    with open(os.path.join(OUT, "followers", f"snapshot-{d}.json"), "w") as f:
        json.dump(doc, f, indent=2)

# ---------------- posts
others = ["peer_alpha", "peer_bravo", "peer_charlie", "peer_delta", "peer_echo"]
media_opts = ["text", "image", "video", "thread"]
pid = 1830000000000000000
json_posts_by_day = {}
for d in days:
    if d >= date(2026, 9, 5) or d in (date(2026, 8, 27), date(2026, 8, 28)):
        pass
    if d.day in (1, 2, 12, 22) or d in (date(2026, 8, 27), date(2026, 8, 28)):
        continue  # dagen zonder post
    if d < date(2026, 9, 1):
        continue  # augustus komt uit de Engelse CSV
    n = R.randint(1, 4)
    for _ in range(n):
        pid += R.randint(1000, 99999)
        typ = R.choices(["post", "reply", "repost", "quote"], [4, 5, 1, 1])[0]
        hr = R.choice([8, 9, 12, 13, 17, 19, 20, 21, 22])
        created = datetime(d.year, d.month, d.day, hr, R.randint(0, 59), tzinfo=AMS)
        imp = R.randint(40, 3000) if typ != "repost" else None
        p = {"id": str(pid), "url": f"https://x.com/demo_owner/status/{pid}",
             "created_at": created.isoformat(), "type": typ,
             "media": R.choice(media_opts) if typ in ("post", "quote") else "text",
             "text": f"TESTFIXTURE {typ} op {d} #{pid % 1000}"}
        if typ == "reply":
            p["in_reply_to_handle"] = "demo_owner" if R.random() < 0.2 else R.choice(others)
        if imp is not None:
            p.update(impressions=imp, likes=imp // R.randint(15, 60), replies=R.randint(0, 8),
                     reposts=R.randint(0, 4), quotes=R.randint(0, 2), bookmarks=R.randint(0, 6),
                     profile_visits=R.randint(0, 15), link_clicks=R.randint(0, 5), new_follows=R.randint(0, 3))
        json_posts_by_day.setdefault(d, []).append(p)

jsonl_days = {date(2026, 9, 3), date(2026, 9, 4)}
csv_days = {date(2026, 9, 14), date(2026, 9, 15), date(2026, 9, 16)}
for d, ps in json_posts_by_day.items():
    if d in csv_days:
        continue
    if d in jsonl_days:
        with open(os.path.join(OUT, "posts", f"posts-{d}.jsonl"), "w") as f:
            for p in ps:
                f.write(json.dumps(dict(p, captured_at=f"{d}T23:00:00+02:00")) + "\n")
    else:
        with open(os.path.join(OUT, "posts", f"posts-{d}.json"), "w") as f:
            json.dump({"captured_at": f"{d}T23:00:00+02:00", "posts": ps}, f, indent=2)

# latere snapshot met gegroeide metrics voor posts van 2026-09-20 (moet overschrijven)
upd = []
for p in json_posts_by_day.get(date(2026, 9, 20), []):
    if p.get("impressions"):
        upd.append({"id": p["id"], "impressions": p["impressions"] * 3, "likes": p["likes"] * 2 + 5,
                    "new_follows": (p["new_follows"] or 0) + 2})
with open(os.path.join(OUT, "posts", "posts-2026-09-24-update.json"), "w") as f:
    json.dump({"captured_at": "2026-09-24T22:00:00+02:00", "posts": upd}, f, indent=2)

# CSV met Nederlandse headers, ';' als scheidingsteken, NL-datums, 1.234-notatie
NL_DAYS = ["ma", "di", "wo", "do", "vr", "za", "zo"]
NL_MON = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]
with open(os.path.join(OUT, "analytics-csv", "x-analytics-nl-2026-09-17.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f, delimiter=";")
    w.writerow(["Post-ID", "Datum", "Tekst", "Weergaven", "Vind-ik-leuks", "Antwoorden", "Reposts", "Citaten",
                "Bladwijzers", "Profielbezoeken", "Linkklikken", "Nieuwe volgers", "Betrokkenheid", "Link naar post"])
    for d in sorted(csv_days):
        for p in json_posts_by_day.get(d, []):
            if p["type"] == "repost":
                continue
            c = datetime.fromisoformat(p["created_at"])
            ds = f"{NL_DAYS[c.weekday()]} {c.day} {NL_MON[c.month-1]}. {c.year} {c:%H:%M}"
            text = p["text"] if p["type"] != "reply" else f"@{p['in_reply_to_handle']} {p['text']}"
            imp = p["impressions"] * 7
            w.writerow([p["id"], ds, text, f"{imp:,}".replace(",", "."), p["likes"], p["replies"], p["reposts"],
                        p["quotes"], p["bookmarks"], p["profile_visits"], p["link_clicks"], p["new_follows"],
                        p["likes"] + p["replies"], p["url"]])

# CSV met Engelse (oude X "tweet activity") headers, UTC-tijden
with open(os.path.join(OUT, "analytics-csv", "tweet_activity_metrics_demo_owner_20260820_20260831_en.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Tweet id", "Tweet permalink", "Tweet text", "time", "impressions", "engagements", "engagement rate",
                "retweets", "replies", "likes", "user profile clicks", "url clicks", "follows", "detail expands", "Bookmarks"])
    for d in days:
        if d >= date(2026, 9, 1) or d in (date(2026, 8, 27), date(2026, 8, 28)):
            continue
        for _ in range(R.randint(1, 3)):
            pid += R.randint(1000, 99999)
            t = datetime(d.year, d.month, d.day, R.choice([6, 7, 11, 16, 18, 19]), R.randint(0, 59), tzinfo=UTC)
            reply = R.random() < 0.4
            text = (f"@{R.choice(others)} " if reply else "") + f"TESTFIXTURE csv-en {d}"
            imp = R.randint(50, 2500)
            likes, rep, rt = imp // 40, R.randint(0, 5), R.randint(0, 3)
            w.writerow([pid, f"https://twitter.com/demo_owner/status/{pid}", text, t.strftime("%Y-%m-%d %H:%M +0000"),
                        imp, likes + rep + rt, f"{(likes+rep+rt)/imp:.4f}", rt, rep, likes, R.randint(0, 9),
                        R.randint(0, 3), R.randint(0, 2), R.randint(0, 20), R.randint(0, 4)])

# CSV in het echte X-content-exportformaat: alleen datum (geen tijd), X-engagements, extra kolommen.
# Bevat ook een post die al met exacte tijd in JSON staat (2026-09-13): tijd mag niet verloren gaan.
real_hdr = ["Post id", "Date", "Post text", "Post Link", "Impressions", "Likes", "Engagements", "Bookmarks", "Shares",
            "New follows", "Replies", "Reposts", "Profile visits", "Detail Expands", "URL Clicks", "Hashtag Clicks",
            "Permalink Clicks"]
with open(os.path.join(OUT, "analytics-csv", "account_analytics_content_2026-09-12_2026-09-13.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(real_hdr)
    d = date(2026, 9, 12)
    for i, (txt, imp) in enumerate([("TESTFIXTURE datum-only post, it's fine", 900),
                                    ("@peer_alpha TESTFIXTURE datum-only reactie", 400),
                                    ("TESTFIXTURE datum-only tweede post", 300)]):
        pid += R.randint(1000, 99999)
        w.writerow([pid, d.strftime("%a, %b %-d, %Y"), txt, f"https://x.com/demo_owner/status/{pid}", imp, imp // 30,
                    imp // 12, 2, 1, 1, 3, 1, 4, 20, 1, 0, 2])
    for p in json_posts_by_day.get(date(2026, 9, 13), [])[:1]:
        w.writerow([p["id"], "Sun, Sep 13, 2026", p["text"], p["url"], p.get("impressions") or 0, p.get("likes") or 0,
                    99, 0, 0, 0, 0, 0, 0, 5, 0, 0, 0])

# account-dagoverzicht CSV (geen per-post data) -> moet netjes worden overgeslagen
with open(os.path.join(OUT, "analytics-csv", "account_overview_2026-09.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["Date", "Impressions", "Likes", "Unfollows"]); w.writerow(["2026-09-01", 1000, 20, 1])

# Extra FICTIEVE posts voor "Wat werkt het best". Eigen teller, geen Random(42),
# zodat de bestaande fixture-IDs ongewijzigd blijven.
def _pad(prefix, n):
    extra = max(0, n - len(prefix))
    return prefix + ("x" * extra)


def _iso(d, hour, minute=0):
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=AMS).isoformat()


cov, cid = [], 1900000000000000000


def add_cov(**kw):
    global cid
    cid += 1
    p = {
        "id": str(cid),
        "url": f"https://x.com/demo_owner/status/{cid}",
        "text": kw.pop("text", "TESTFIXTURE-INSIGHTS"),
        "type": kw.pop("type", "post"),
        "impressions": kw.pop("impressions", 400),
        "likes": kw.pop("likes", 8),
        "replies": kw.pop("replies", 1),
        "reposts": kw.pop("reposts", 0),
        "quotes": kw.pop("quotes", 0),
        "bookmarks": kw.pop("bookmarks", 1),
        "profile_visits": kw.pop("profile_visits", 2),
        "link_clicks": kw.pop("link_clicks", 0),
        "new_follows": kw.pop("new_follows", 0),
    }
    p.update(kw)
    cov.append(p)
    return p


# 6 posts per media-waarde (n >= MIN_N=5). Video bewust sterker dan tekst.
MEDIA_IMP = {
    "text": 800, "image": 1400, "multi_image": 1600, "video": 3200,
    "gif": 1100, "poll": 700, "link": 900, "article": 1500,
}
media_days = [date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10),
              date(2026, 9, 11), date(2026, 9, 15), date(2026, 9, 16)]
for media, imp in MEDIA_IMP.items():
    for i, d in enumerate(media_days):
        txt = f"TESTFIXTURE-INSIGHTS media={media} #{i+1}"
        if media == "link":
            txt += " https://example.com/testfixture"
        add_cov(created_at=_iso(d, 14, i * 3), type="post", media=media, text=txt,
                impressions=imp + i * 10, likes=imp // 40, new_follows=1 if media == "video" else 0,
                profile_visits=imp // 200)

# Lengte-buckets: 6 per bucket, eigen posts.
for i in range(6):
    d = date(2026, 9, 17)
    add_cov(created_at=_iso(d, 9, i), media="text",
            text=_pad(f"TESTFIXTURE-INSIGHTS kort {i} ", 40), impressions=500 + i)
    add_cov(created_at=_iso(d, 10, i), media="text",
            text=_pad(f"TESTFIXTURE-INSIGHTS middel {i} ", 120), impressions=600 + i)
    add_cov(created_at=_iso(d, 11, i), media="text",
            text=_pad(f"TESTFIXTURE-INSIGHTS lang {i} ", 240), impressions=550 + i)
    add_cov(created_at=_iso(d, 12, i), media="text",
            text=_pad(f"TESTFIXTURE-INSIGHTS longform {i} ", 320), impressions=700 + i)

# Types: quote, repost, thread (self-reply), reply op anderen.
for i in range(6):
    d = date(2026, 9, 18)
    add_cov(created_at=_iso(d, 13, i), type="quote", media="text",
            text=f"TESTFIXTURE-INSIGHTS quote {i}", impressions=900)
    add_cov(created_at=_iso(d, 14, i), type="repost", media="text",
            text=f"RT @peer_alpha TESTFIXTURE-INSIGHTS repost {i}", impressions=None,
            likes=None, replies=None, reposts=None, quotes=None, bookmarks=None,
            profile_visits=None, link_clicks=None, new_follows=None)
    add_cov(created_at=_iso(d, 15, i), type="reply", media="text",
            in_reply_to_handle="demo_owner",
            text=f"TESTFIXTURE-INSIGHTS thread {i}", impressions=300)
    add_cov(created_at=_iso(d, 16, i), type="reply", media="text",
            in_reply_to_handle="peer_alpha",
            text=f"@peer_alpha TESTFIXTURE-INSIGHTS reactie {i}", impressions=450)

# Heatmap posts+quotes: top slots di 20:00, wo 21:00, do 20:00 (elk 6 posts).
heat = [
    (date(2026, 9, 8), 20, 2800), (date(2026, 9, 15), 20, 2900), (date(2026, 9, 22), 20, 3000),
    (date(2026, 9, 8), 20, 2700), (date(2026, 9, 15), 20, 2750), (date(2026, 9, 22), 20, 2850),
    (date(2026, 9, 9), 21, 2600), (date(2026, 9, 16), 21, 2650), (date(2026, 9, 23), 21, 2700),
    (date(2026, 9, 9), 21, 2500), (date(2026, 9, 16), 21, 2550), (date(2026, 9, 23), 21, 2580),
    (date(2026, 9, 10), 20, 2400), (date(2026, 9, 17), 20, 2450), (date(2026, 9, 24), 20, 2480),
    (date(2026, 9, 10), 20, 2300), (date(2026, 9, 17), 20, 2350), (date(2026, 9, 24), 20, 2380),
]
for i, (d, hr, imp) in enumerate(heat):
    add_cov(created_at=_iso(d, hr, (i % 6) * 4), type="post", media="video",
            text=f"TESTFIXTURE-INSIGHTS heatmap post {i} 🚀", impressions=imp,
            likes=imp // 20, profile_visits=imp // 100, new_follows=2)

# Weinig-data cel (n=2) — moet grijs/"te weinig data" tonen.
add_cov(created_at=_iso(date(2026, 9, 11), 3, 0), type="post", media="text",
        text="TESTFIXTURE-INSIGHTS low-n heatmap a", impressions=50)
add_cov(created_at=_iso(date(2026, 9, 18), 3, 10), type="post", media="text",
        text="TESTFIXTURE-INSIGHTS low-n heatmap b", impressions=60)

# Replies heatmap: vr 10/11/12 uur, elk 6, hoge impressies/profiel/volgers.
reply_heat = [
    (date(2026, 9, 11), 10, 1800, 12, 3), (date(2026, 9, 18), 10, 1900, 13, 3),
    (date(2026, 9, 25), 10, 2000, 14, 4), (date(2026, 9, 11), 10, 1700, 11, 2),
    (date(2026, 9, 18), 10, 1750, 11, 2), (date(2026, 9, 25), 10, 1850, 12, 3),
    (date(2026, 9, 11), 11, 1500, 9, 2), (date(2026, 9, 18), 11, 1550, 9, 2),
    (date(2026, 9, 25), 11, 1600, 10, 2), (date(2026, 9, 11), 11, 1400, 8, 1),
    (date(2026, 9, 18), 11, 1450, 8, 1), (date(2026, 9, 25), 11, 1480, 8, 1),
    (date(2026, 9, 11), 12, 1200, 7, 1), (date(2026, 9, 18), 12, 1250, 7, 1),
    (date(2026, 9, 25), 12, 1300, 7, 1), (date(2026, 9, 11), 12, 1100, 6, 1),
    (date(2026, 9, 18), 12, 1150, 6, 1), (date(2026, 9, 25), 12, 1180, 6, 1),
]
for i, (d, hr, imp, vis, fol) in enumerate(reply_heat):
    add_cov(created_at=_iso(d, hr, (i % 6) * 5), type="reply", media="text",
            in_reply_to_handle="peer_bravo",
            text=f"@peer_bravo TESTFIXTURE-INSIGHTS reply-heat {i}",
            impressions=imp, profile_visits=vis, new_follows=fol, likes=imp // 30)

# Response speed: 6 replies per bucket, parent timestamp expliciet.
speed_spec = [
    ("15m", timedelta(minutes=8), 900),
    ("1h", timedelta(minutes=40), 600),
    ("4h", timedelta(hours=2, minutes=30), 400),
    ("later", timedelta(hours=10), 200),
]
for label, delta, imp in speed_spec:
    for i in range(6):
        created = datetime(2026, 9, 19, 18, i * 2, tzinfo=AMS)
        parent = created - delta
        add_cov(created_at=created.isoformat(), type="reply", media="text",
                in_reply_to_handle="peer_charlie",
                in_reply_to_created_at=parent.isoformat(),
                text=f"@peer_charlie TESTFIXTURE-INSIGHTS speed {label} {i}",
                impressions=imp + i, likes=imp // 25)

# Tekstkenmerken (elk n>=5), NL vs EN.
for i in range(6):
    d = date(2026, 9, 21)
    add_cov(created_at=_iso(d, 8, i), media="text",
            text=f"TESTFIXTURE-INSIGHTS vraag {i}: wat werkt voor jullie?",
            impressions=640)
    add_cov(created_at=_iso(d, 9, i), media="text",
            text=f"TESTFIXTURE-INSIGHTS tags {i} #ai #build #x #makers",
            impressions=610)
    add_cov(created_at=_iso(d, 10, i), media="text",
            text=f"TESTFIXTURE-INSIGHTS hallo @peer_alpha @peer_bravo nummer {i}",
            impressions=580)
    add_cov(created_at=_iso(d, 11, i), media="text",
            text=f"TESTFIXTURE-INSIGHTS emoji {i} 🚀✨",
            impressions=700)
    add_cov(created_at=_iso(d, 12, i), media="text",
            text=f"3 tips voor lokale AI {i} — TESTFIXTURE-INSIGHTS",
            impressions=720)
    add_cov(created_at=_iso(d, 13, i), media="text",
            text=f"TESTFIXTURE-INSIGHTS blok {i}\n\ntweede alinea hier.",
            impressions=530)
    add_cov(created_at=_iso(d, 19, i), media="video",
            text=("TESTFIXTURE-INSIGHTS Dit is een Nederlandse zin met de het een van "
                  f"en op dat voor met niet zijn er je ik we dit maar ook als {i}."),
            impressions=2100)
    add_cov(created_at=_iso(d, 20, i), media="text",
            text=("TESTFIXTURE-INSIGHTS This is an English sentence with the a of and "
                  f"is to in that for on with as was be this are {i}."),
            impressions=950)

# --- Follow-up A–D coverage (snowflake, ROI, conversion). Own cid, no Random(42). ---
TWITTER_EPOCH_MS = 1288834974657


def make_snowflake(dt):
    ms = int(dt.astimezone(timezone.utc).timestamp() * 1000)
    return str((ms - TWITTER_EPOCH_MS) << 22)


# A: date-only X-content CSV whose Post id encodes 2026-09-12 times (AMS).
# Keep the older date-only CSV IDs unchanged (they fail the ±1-day check).
snow_hdr = ["Post id", "Date", "Post text", "Post Link", "Impressions", "Likes", "Engagements",
            "Bookmarks", "Shares", "New follows", "Replies", "Reposts", "Profile visits",
            "Detail Expands", "URL Clicks", "Hashtag Clicks", "Permalink Clicks"]
with open(os.path.join(OUT, "analytics-csv", "account_analytics_content_snowflake_2026-09-12.csv"),
          "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(snow_hdr)
    d12 = date(2026, 9, 12)
    ds = d12.strftime("%a, %b %-d, %Y")
    # Viral 07:20 outlier (own post) + five quiet 07:xx posts → mean ≫ median.
    hour7 = [
        (7, 20, 50000, "TESTFIXTURE-FOLLOWUP snowflake viral 07:20"),
        (7, 5, 40, "TESTFIXTURE-FOLLOWUP snowflake quiet 07:05"),
        (7, 8, 45, "TESTFIXTURE-FOLLOWUP snowflake quiet 07:08"),
        (7, 12, 50, "TESTFIXTURE-FOLLOWUP snowflake quiet 07:12"),
        (7, 16, 55, "TESTFIXTURE-FOLLOWUP snowflake quiet 07:16"),
        (7, 25, 60, "TESTFIXTURE-FOLLOWUP snowflake quiet 07:25"),
        (21, 0, 800, "TESTFIXTURE-FOLLOWUP snowflake evening 21:00"),
        (21, 15, 820, "TESTFIXTURE-FOLLOWUP snowflake evening 21:15"),
    ]
    for hr, mn, imp, txt in hour7:
        created = datetime(2026, 9, 12, hr, mn, tzinfo=AMS)
        sid = make_snowflake(created)
        w.writerow([sid, ds, txt, f"https://x.com/demo_owner/status/{sid}", imp, imp // 40,
                    imp // 15, 1, 0, 0, 1, 0, 2, 8, 0, 0, 1])
    # Mismatch: CSV date Sep 12 2026, snowflake from 2024 → ignore derived time.
    bad = make_snowflake(datetime(2024, 3, 1, 12, 0, tzinfo=AMS))
    w.writerow([bad, ds, "TESTFIXTURE-FOLLOWUP snowflake-mismatch",
                f"https://x.com/demo_owner/status/{bad}", 120, 2, 5, 0, 0, 0, 0, 0, 1, 2, 0, 0, 0])

# B: reply ROI — lowreach (flag), gold_source (follows), reach_king (mean impressions).
for i in range(6):
    add_cov(created_at=_iso(date(2026, 9, 20), 11, i * 3), type="reply", media="text",
            in_reply_to_handle="lowreach_acct",
            text=f"@lowreach_acct TESTFIXTURE-FOLLOWUP low-roi {i}",
            impressions=8 + i * 2, likes=0, profile_visits=0, new_follows=0)
for i in range(5):
    add_cov(created_at=_iso(date(2026, 9, 21), 14, i * 2), type="reply", media="text",
            in_reply_to_handle="gold_source",
            text=f"@gold_source TESTFIXTURE-FOLLOWUP gold {i}",
            impressions=400 + i * 10, likes=12, profile_visits=20 + i, new_follows=8 + i)
for i in range(4):
    add_cov(created_at=_iso(date(2026, 9, 23), 16, i * 2), type="reply", media="text",
            in_reply_to_handle="reach_king",
            text=f"@reach_king TESTFIXTURE-FOLLOWUP reach {i}",
            impressions=3000 + i * 50, likes=40, profile_visits=15, new_follows=1)
# Extra ROI accounts so "beste bereik" (top 10, min. 3 replies) does not include lowreach.
for name, imp in (("midreach_a", 220), ("midreach_b", 260), ("midreach_c", 310)):
    for i in range(3):
        add_cov(created_at=_iso(date(2026, 9, 22), 12, i), type="reply", media="text",
                in_reply_to_handle=name,
                text=f"@{name} TESTFIXTURE-FOLLOWUP mid {i}",
                impressions=imp + i, likes=4, profile_visits=2, new_follows=0)

# C: conversion spike in ISO-week 38 (2026-09-14 … 2026-09-20).
for i in range(6):
    add_cov(created_at=_iso(date(2026, 9, 14), 18, i * 4), type="post", media="text",
            text=f"TESTFIXTURE-FOLLOWUP conversion-spike W38 {i}",
            impressions=2000, profile_visits=200, new_follows=20, likes=30)

# Public-mode size buckets: 6 fictional accounts in 1k–10k and 6 in 10k–100k.
TARGET = {}
for i in range(6):
    h = f"size_mid_{i:02d}"
    TARGET[h] = 4000
    for j in range(2):
        add_cov(created_at=_iso(date(2026, 9, 24), 9, i * 2 + j), type="reply", media="text",
                in_reply_to_handle=h,
                text=f"@{h} TESTFIXTURE-PUBLIC size-mid {j}",
                impressions=220 + i, likes=3, profile_visits=5, new_follows=1)
for i in range(6):
    h = f"size_big_{i:02d}"
    TARGET[h] = 40000
    add_cov(created_at=_iso(date(2026, 9, 24), 11, i), type="reply", media="text",
            in_reply_to_handle=h, text=f"@{h} TESTFIXTURE-PUBLIC size-big",
            impressions=800 + i * 10, likes=8, profile_visits=12, new_follows=2)
for i in range(2):
    h = f"size_tiny_{i:02d}"
    TARGET[h] = 80
    add_cov(created_at=_iso(date(2026, 9, 24), 10, i), type="reply", media="text",
            in_reply_to_handle=h, text=f"@{h} TESTFIXTURE-PUBLIC size-tiny",
            impressions=12, likes=0, profile_visits=0, new_follows=0)

# Round-3: clip-able daily outlier on an otherwise empty day.
# 289,780 sits well above the fixture's robust y-cap (~84k) so the
# impressions series must draw a markPoint labeled 289,780.
add_cov(
    created_at=_iso(date(2026, 9, 2), 15, 0),
    type="post",
    media="text",
    text="TESTFIXTURE-OUTLIER daily 289780",
    impressions=289780,
    likes=200,
    replies=20,
    profile_visits=80,
    new_follows=5,
)

# Round-4: previous-week 7d outlier (Sep 16 is in 7d previous: Sep 12–18).
# 400,000 must not inflate the current-week impressions y-axis.
add_cov(
    created_at=_iso(date(2026, 9, 16), 11, 0),
    type="post",
    media="text",
    text="TESTFIXTURE-OUTLIER prev-week 400000",
    impressions=400000,
    likes=250,
    replies=25,
    profile_visits=90,
    new_follows=6,
)

# Uneven heatmap range: a saturated low cell (n=5, median 14) and a mid cell (144).
for i in range(5):
    add_cov(
        created_at=_iso(date(2026, 9, 7), 4, i * 2),
        type="post",
        media="text",
        text=f"TESTFIXTURE-HEAT-LOW {i}",
        impressions=14,
    )
add_cov(
    created_at=_iso(date(2026, 9, 8), 5, 0),
    type="post",
    media="text",
    text="TESTFIXTURE-HEAT-MID 144",
    impressions=144,
)

with open(os.path.join(OUT, "posts", "posts-insights-coverage.json"), "w") as f:
    json.dump({"captured_at": "2026-09-25T23:00:00+02:00", "posts": cov}, f, indent=2)

def _fixture_avatar_png(w=40, h=40, rgb=(29, 155, 240)):
    """Solid PNG written as avatar.jpg so fixture builds never hit the network."""
    import struct
    import zlib

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


with open(os.path.join(OUT, "avatar.jpg"), "wb") as f:
    f.write(_fixture_avatar_png())

data_cfg = {
    "account": "demo_owner",
    "display_name": "Demo Owner",
    "demo": True,
    "site_url": "https://example.com",
    "repo_url": "https://github.com/example/x-growth-assistant",
    "og_image_url": "",
    "profile_image_url": "avatar.jpg",
    "lang": "en",
    "csv_timezone": "UTC",
}
with open(os.path.join(OUT, "config.json"), "w") as f:
    json.dump(data_cfg, f, indent=2)
with open(os.path.join(OUT, "target_accounts.json"), "w") as f:
    json.dump(TARGET, f, indent=2)

print("Wrote fixtures to", OUT)
