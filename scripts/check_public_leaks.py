#!/usr/bin/env python3
"""Fail if a public dashboard HTML still contains other people's handles.

Usage:
  python3 scripts/check_public_leaks.py <html> <data-dir> [--followers-dir DIR]

publish.sh runs this on the public build before every public deploy.
The owner handle from data/config.json (or data/config.example.json) is allowed.
Only @mentions, x.com/twitter.com profile URLs, and structured handle fields
are treated as leaks — not bare words in post text that happen to equal a handle.
Optional allowlist: data/public_allowlist.json (see public_allowlist.example.json).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys

HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
MENTION_RE = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z0-9_]{1,15})")
URL_HANDLE_RE = re.compile(
    r"(?:https?://)?(?:www\.|mobile\.)?(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})",
    re.I,
)


def norm_handle(h):
    if h is None:
        return None
    if isinstance(h, dict):
        h = h.get("handle") or h.get("username") or h.get("screen_name")
        if h is None:
            return None
    h = str(h).strip().lstrip("@")
    m = URL_HANDLE_RE.search(h)
    if m:
        h = m.group(1)
    h = h.strip()
    return h if h and HANDLE_RE.fullmatch(h) else (h if h else None)


def add_handle(store, h):
    n = norm_handle(h)
    if n:
        store.add(n)


def add_from_text(store, text):
    if not text:
        return
    s = str(text)
    for m in MENTION_RE.finditer(s):
        add_handle(store, m.group(1))
    for m in URL_HANDLE_RE.finditer(s):
        add_handle(store, m.group(1))


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def collect_from_snapshot(store, doc):
    if not isinstance(doc, dict):
        return
    for key in ("handles", "followers", "follower_handles", "following_handles", "following"):
        val = doc.get(key)
        if isinstance(val, list):
            for h in val:
                add_handle(store, h)
    for key in ("unavailable", "verified_unfollowers"):
        val = doc.get(key)
        if isinstance(val, list):
            for item in val:
                add_handle(store, item)


def collect_from_post(store, raw):
    if not isinstance(raw, dict):
        return
    add_handle(store, raw.get("in_reply_to_handle"))
    add_from_text(store, raw.get("text"))
    add_from_text(store, raw.get("url"))


def iter_json_posts(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            if path.endswith(".jsonl"):
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
            else:
                d = json.load(f)
    except Exception:
        return
    if path.endswith(".jsonl"):
        return
    if isinstance(d, list):
        for item in d:
            yield item
    elif isinstance(d, dict):
        posts = d.get("posts") or []
        if isinstance(posts, list):
            for item in posts:
                yield item


def collect_from_csv(store, path):
    try:
        with open(path, "rb") as f:
            b = f.read()
    except OSError:
        return
    text = None
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            text = b.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return
    first = text.lstrip("\ufeff").splitlines()[0] if text.strip() else ""
    delim = max([",", ";", "\t"], key=lambda c: first.count(c))
    rows = list(csv.reader(io.StringIO(text), delimiter=delim, quotechar='"', doublequote=True))
    for row in rows:
        for cell in row:
            add_from_text(store, cell)


def collect_dir_json(store, directory, snapshot=False):
    if not directory or not os.path.isdir(directory):
        return
    for name in os.listdir(directory):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        if snapshot and name.endswith(".json"):
            doc = load_json(path)
            collect_from_snapshot(store, doc)
        elif name.endswith(".json") or name.endswith(".jsonl"):
            if snapshot:
                continue
            for item in iter_json_posts(path):
                collect_from_post(store, item)


def owner_from_config(data_dir):
    for name in ("config.json", "config.example.json"):
        path = os.path.join(data_dir, name)
        doc = load_json(path)
        if isinstance(doc, dict) and doc.get("account"):
            n = norm_handle(doc.get("account"))
            if n:
                return n
    root_example = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "data", "config.example.json")
    doc = load_json(root_example)
    if isinstance(doc, dict) and doc.get("account"):
        return norm_handle(doc.get("account"))
    return None


def collect_handles(data_dir, followers_dir=None):
    store = set()
    collect_dir_json(store, os.path.join(data_dir, "followers"), snapshot=True)
    collect_dir_json(store, followers_dir, snapshot=True)
    collect_dir_json(store, os.path.join(data_dir, "posts"), snapshot=False)
    csv_dir = os.path.join(data_dir, "analytics-csv")
    if os.path.isdir(csv_dir):
        for name in os.listdir(csv_dir):
            if name.lower().endswith(".csv"):
                collect_from_csv(store, os.path.join(csv_dir, name))
    targets = load_json(os.path.join(data_dir, "target_accounts.json"))
    if isinstance(targets, dict):
        for k in targets:
            add_handle(store, k)
    elif isinstance(targets, list):
        for item in targets:
            if isinstance(item, dict):
                add_handle(store, item.get("handle") or item.get("account"))
            else:
                add_handle(store, item)
    owner = owner_from_config(data_dir)
    if owner:
        store = {h for h in store if h.lower() != owner.lower()}
    return store, owner


HANDLE_FIELD_KEYS = {
    "handle", "handles", "username", "user_name", "screen_name", "author",
    "account", "in_reply_to_handle", "in_reply_to_user", "follower_handles",
    "following_handles", "following", "verified_unfollowers", "unavailable",
}

STRUCTURED_FIELD_RE = re.compile(
    r'(?i)(?:"(?:in_reply_to_handle|in_reply_to_user|handle|username|'
    r'screen_name|author|account|user_name)"\s*:\s*")(@?[A-Za-z0-9_]{1,15})"'
)
DATA_ATTR_RE = re.compile(
    r'''(?i)\b(?:data-handle|data-username|data-author|data-account)\s*=\s*["']@?([A-Za-z0-9_]{1,15})["']'''
)
SCRIPT_JSON_RE = re.compile(
    r"<script\b[^>]*>(.*?)</script>",
    re.I | re.S,
)


def load_allowlist(data_dir, path=None):
    """Return extra handles the owner explicitly accepts (never flagged)."""
    candidates = []
    if path:
        candidates.append(path)
    if data_dir:
        candidates.append(os.path.join(data_dir, "public_allowlist.json"))
    store = set()
    for p in candidates:
        if not p or not os.path.isfile(p):
            continue
        doc = load_json(p)
        values = []
        if isinstance(doc, dict):
            values.extend(doc.get("handles") or [])
            values.extend(doc.get("words") or [])
        elif isinstance(doc, list):
            values.extend(doc)
        for item in values:
            if isinstance(item, str) and item.strip():
                n = norm_handle(item) or item.strip().lstrip("@")
                if n:
                    store.add(n)
        break
    return store


def _add_structured_value(store, val):
    if isinstance(val, str):
        add_handle(store, val)
    elif isinstance(val, dict):
        add_handle(store, val)
        for v in val.values():
            _add_structured_value(store, v)
    elif isinstance(val, list):
        for item in val:
            _add_structured_value(store, item)


def collect_structured_handles(obj, store):
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k).lower()
            if (
                key in HANDLE_FIELD_KEYS
                or key.endswith("_handle")
                or key.endswith("_handles")
            ):
                _add_structured_value(store, v)
            collect_structured_handles(v, store)
    elif isinstance(obj, list):
        for item in obj:
            collect_structured_handles(item, store)


def _decode_entities(text):
    return (
        text.replace("&quot;", '"')
        .replace("&#34;", '"')
        .replace("&amp;", "&")
        .replace("&#39;", "'")
        .replace("&apos;", "'")
    )


def handles_in_handle_contexts(html):
    """Handles that appear as @mentions, profile URLs, or structured fields.

    Bare words in visible post text are ignored even if they equal a handle.
    """
    found = set()
    if not html:
        return found
    raw = _decode_entities(html)
    for m in MENTION_RE.finditer(raw):
        rest = raw[m.end():]
        if re.match(r"\s*[\({]", rest):
            continue  # CSS/JS at-rule (@media (, @supports (, @font-face {)
        add_handle(found, m.group(1))
    for m in URL_HANDLE_RE.finditer(raw):
        add_handle(found, m.group(1))
    for m in DATA_ATTR_RE.finditer(raw):
        add_handle(found, m.group(1))
    for m in STRUCTURED_FIELD_RE.finditer(raw):
        add_handle(found, m.group(1))
    for m in SCRIPT_JSON_RE.finditer(html):
        body = m.group(1).strip()
        if not body or (body[0] not in "{["):
            continue
        try:
            doc = json.loads(body)
        except json.JSONDecodeError:
            continue
        collect_structured_handles(doc, found)
    return found


def find_leaks(html, handles, owner=None, allowlist=None):
    skip = set()
    if owner:
        n = norm_handle(owner)
        if n:
            skip.add(n.lower())
    for a in allowlist or []:
        n = norm_handle(a) or str(a).strip().lstrip("@")
        if n:
            skip.add(n.lower())
    wanted = {h.lower(): h for h in handles if h and h.lower() not in skip}
    found = handles_in_handle_contexts(html)
    leaks = []
    for f in found:
        fl = f.lower()
        if fl in skip:
            continue
        if fl in wanted:
            leaks.append(wanted[fl])
    leaks.sort(key=str.lower)
    return leaks


def main(argv=None):
    ap = argparse.ArgumentParser(description="Block a public build that still contains other handles.")
    ap.add_argument("html")
    ap.add_argument("data_dir")
    ap.add_argument("--followers-dir", default=None)
    ap.add_argument("--allowlist", default=None,
                    help="JSON allowlist (default: <data-dir>/public_allowlist.json)")
    args = ap.parse_args(argv)
    if not os.path.isfile(args.html):
        print(f"check_public_leaks: HTML missing: {args.html}", file=sys.stderr)
        return 2
    if not os.path.isdir(args.data_dir):
        print(f"check_public_leaks: data directory missing: {args.data_dir}", file=sys.stderr)
        return 2
    html = open(args.html, encoding="utf-8").read()
    handles, owner = collect_handles(args.data_dir, args.followers_dir)
    allow = load_allowlist(args.data_dir, args.allowlist)
    leaks = find_leaks(html, handles, owner=owner, allowlist=allow)
    if leaks:
        print("check_public_leaks: public build contains other people's handles:", file=sys.stderr)
        for h in leaks[:40]:
            print(f"  - {h}", file=sys.stderr)
        if len(leaks) > 40:
            print(f"  … +{len(leaks) - 40} more", file=sys.stderr)
        return 1
    print(f"check_public_leaks: OK ({len(handles)} other handles checked"
          + (f", owner @{owner} allowed" if owner else "") + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
