# Plan: X growth data in Supabase

Plan only. No application code in this document. The static builder
(`python3 build.py` → one `index.html`) stays the public and private
site until an explicit cutover.

Bar: first principles. One source of truth at a time. The public page
must never be able to read another person's handle, even if someone
points a browser at the database URL.

## 1. What problem this solves

Today every account's history lives as files on one machine:

- `data/followers/snapshot-*.json` — full handle lists, counts, following
- `data/analytics-csv/*.csv` — unmodified X Analytics exports
- `data/posts/*.json` — optional extra post metrics
- `data/config.json`, `target_accounts.json`, `public_allowlist.json`

`build.py` parses those files, embeds JSON, writes HTML. That path is
zero-cost, works offline, and is already leak-checked.

It does not scale to several customer accounts or to a second machine
rebuilding the same dashboard. The files are the product's memory.
Postgres should become that memory without making the website a
database client.

## 2. Non-negotiable constraints

1. **Frankfurt, Free tier.** Create the project in `eu-central-1` on
   day one. Region is not a cheap later change. Free is about 500 MB
   database, ~1 GB file storage, low egress, and **projects pause after
   roughly a week of inactivity**.
2. **Static path until cutover.** Default `python3 build.py` still reads
   files. Hosted HTML is still Netlify static. Visitors never talk to
   Supabase.
3. **One source of truth at a time.** Dual-write is a validation
   window, not the architecture.
4. **Reuse today's parsers and event rules.** Ingest calls the existing
   Python in `build.py` (`load_followers`, `compute_follower_events`,
   CSV/JSON post merge). Do not reimplement status words
   (`nieuw` / `terug` / `ontvolger` / `mogelijk` / `capture_gat` /
   `verwijderd`) in SQL. v1 ingest is a **full recompute from files**
   then upsert, the same work `build.py` already does every day.
5. **Handles never go to `anon`.** The public site is a stripped HTML
   file plus `check_public_leaks.py`. The database is a private store.
6. **No `service_role` in a browser, a public Netlify function, or a
   committed file.** Ingest runs on the owner machine (same place as
   `scripts/publish.sh`).
7. **No Realtime** on any table that can hold a handle.
8. **No authorization from `user_metadata`.** If Auth arrives later,
   roles live in `account_members` or `app_metadata`, not profile JSON
   the user can edit.

## 3. The storage mistake to refuse

A daily snapshot is a full follower list. One mid-size account at
50k handles × 365 days is hundreds of megabytes before posts,
following lists, or a second customer. Free 500 MB cannot hold
"every list, every day" for several accounts.

The private UI does not need those historical lists after events
exist. It needs:

- counts and completeness **per snapshot** (the growth chart)
- **new / lost / gap** events with the current status rules
- the **latest** follower and following sets (follow-back, not
  following back)
- the union of `unavailable` and `verified_unfollowers` (read model
  for `--source supabase`; ingest still starts from files)

A later snapshot can reclassify an earlier loss as `capture_gat`
(`reappeared_on`). Events are therefore **upserted from a full
recompute**, not append-only stone tablets.

Do **not** store every historical handle list. Do **not** invent a
second event algorithm in SQL, and do **not** invent a
from-database incremental event engine while files still exist.

## 4. Target shape

### 4.1 Accounts

One row per X account the operator tracks.

| column | why |
|---|---|
| `id` uuid pk | children reference this `ON DELETE CASCADE` |
| `handle` text not null | stored as collected; unique index on `lower(handle)` |
| `display_name` text | header / OG title |
| `csv_timezone` text not null default `UTC` | CSV timestamps without offset |
| `site_url` text | canonical / OG origin |
| `source_repo_url` text | public GitHub CTA |
| `repo_url` text | private footer |
| `og_image_url` text | optional override; empty means `{site_url}/assets/og-image.png` |
| `mode` text check in (`public`,`private`) | default public. Do not add a second `is_public` flag. |
| `goal_followers` int | nullable; CHECK: both goals null or both set |
| `goal_date` date | nullable; same CHECK |
| `goal_posts_per_day` int | optional |
| `goal_replies_per_day` int | optional |
| `created_at` timestamptz | |

No home-directory paths. No tokens. Handle uniqueness is
`unique (lower(handle))`. Membership tables use
`(account_id, handle_key)` with `handle_key = lower(handle)` plus a
display `handle` (casing as collected).

### 4.2 Snapshot metadata — one row per dashboard day

`build.py` already collapses files to **one snapshot per
Europe/Amsterdam date** (`load_followers` + `merge_same_capture`).
The database stores that same grain. Unique
`(account_id, local_date)`. `captured_at` is the winning file's
timestamp, not a second identity.

A second file the same day is a merge + recompute of **that day**,
not a new history row.

`follower_snapshots`

- `account_id`, `local_date` (unique together) — `local_date` comes
  from the existing loader (Amsterdam), never from the Postgres
  TimeZone setting
- `captured_at` timestamptz not null
- `profile_followers`, `profile_following` (nullable ints)
- `collected_followers`, `collected_following`
- `complete`, `following_complete`
- `unavailable_count`, `verified_count`
- `n_new`, `n_returned`, `n_unfollowed`, `n_possible`, `n_gap`, `n_removed`
  (same counters `compute_follower_events` already puts on each day)
- `notes` text (private; stripped in public HTML)
- `source` text — same string the builder already stores after
  basename (no home paths)

### 4.3 Latest lists only

`current_followers (account_id, handle_key)` pk + display `handle`  
`current_following (account_id, handle_key)` pk + display `handle`

Replaced on each accepted day. This is what follow-back reads.
`not_following_back` is **not stored**. `--source supabase` builds one
synthetic latest-day struct from `current_*` plus that day's
snapshot row and runs the same follow-back block as
`compute_follower_events`.

Do **not** add an `ever_followers` table in v1. `terug` vs `nieuw`
already lives on `follower_events`. A third copy would only matter
for incremental-from-DB, which is out of scope.

`unavailable_handles` / `verified_unfollowers` — union tables
(`handle_key`, first flagged, reason / note). Read model for the
private payload. Not an ingest input while files exist.

### 4.4 Events (the private people tables)

`follower_events`

- `account_id`, `local_date` (not a column named `date`)
- `handle_key` + display `handle`
- `direction` `new` | `lost`
- `status` — exact current vocabulary, CHECK in
  (`nieuw`,`terug`,`ontvolger`,`mogelijk`,`capture_gat`,`verwijderd`)
- `follows_back` / `still_following` and their reason/basis fields
- `verified`, `verified_info jsonb`, `reappeared_on`
- unique `(account_id, local_date, handle_key, direction)` so
  re-ingest is an upsert
- FK `(account_id, local_date)` → `follower_snapshots` ON DELETE
  CASCADE, so removing a day removes that day's events

v1 ingest (including daily, including first import) is one function:

1. Call `load_followers` (same merge, same `latest.json` ranking,
   same one-row-per-day).
2. Call `compute_follower_events` on the **full series**.
3. Merge posts the existing way.
4. In **one transaction per account**, reconcile the working set to
   that result: upsert snapshot rows, events, unions, replace
   `current_*`.
5. **Delete** snapshot/event/post/map rows for that account that
   are no longer in the file result (a removed file or CSV must
   disappear).
6. Commit. A failed write leaves files untouched.

Do not apply events incrementally from `current_*` while files
exist. `current_*` is today's list; it cannot reconstruct yesterday.
An incremental-from-DB path is only allowed after the collector
stops writing files, and it is a later design — not cutover.

If a hand-rolled incremental and a full file replay ever disagree,
the file replay wins. Do not "fix" a mismatch by changing SQL
status rules.

### 4.5 Posts

`posts` pk `(account_id, post_id)`

Columns match the builder's post dict: `created_at`, `type`, `media`,
`text`, `url`, `in_reply_to_handle`, impressions / likes / replies /
profile_visits / new_follows (use `bigint` for counters),
`time_source`, etc.

Ingest uses the existing CSV + JSON merge (JSON wins on equal
timestamp). Re-ingest is upsert. Do not keep a parallel "raw rows"
table. v1 does **not** copy CSVs into Supabase Storage — the files
already are the provenance. Storage copies wait until files might
go away.

### 4.6 Small maps

`target_accounts (account_id, handle_key, follower_count)` + display `handle`  
`public_allowlist (account_id, handle_key)` + display `handle`

Same meaning as the gitignored JSON files.

### 4.7 What does not belong in Postgres

- Owner avatars — files (`assets/avatar.*`) or Storage; the HTML
  already inlines or copies bytes
- ECharts / Inter — already vendored
- Built `index.html` — stays on Netlify
- Home paths, Netlify tokens, Basic Auth passwords

## 5. Privileges and RLS

v1 has **no end-user login**. The operator ingests with the service
role on a trusted machine. The website does not query Postgres.

For every table in `public`:

1. `ENABLE ROW LEVEL SECURITY` (no policy ⇒ no access for
   `anon` / `authenticated`).
2. `REVOKE ALL` on the table from `PUBLIC`, `anon`, `authenticated`.
   Also `ALTER DEFAULT PRIVILEGES` so a later table does not silently
   grant to `anon`.
3. Do not add a policy "authenticated can read their rows" until a
   real customer login exists.
4. v1 connects as a superuser-class DB login (`DATABASE_URL`).
   That bypasses RLS. The URI lives in the owner `.env` only. There
   is no service-role JWT in v1.

If any view is added later:

- Postgres 15+: `WITH (security_invoker = true)`
- Revoke it from `anon` unless it is a handle-free public projection
  written on purpose

Do not put `SECURITY DEFINER` functions in an exposed schema.

**Data API.** Leave it on if you want the dashboard UI; it must still
see zero rows as `anon`. Prefer also removing `public` from the
exposed schemas until a live API is a real product decision. Either
control is sufficient; both is better.

**v2 (only when a second customer logs in):**

- `account_members (account_id, user_id, role)` with
  `role in ('owner','reader')`
- Policies use `(select auth.uid())` (initplan; do not call
  `auth.uid()` per row)
- `UPDATE` policies require a matching `SELECT` policy
- Roles in `app_metadata` or this table, never `user_metadata`
- Still no `anon` select on handle columns
- Public live read, if ever: a separate `public_payloads` row
  (`account_id`, `payload jsonb`, `built_at`) written by the same
  Python that already runs `to_public_payload`. `anon` may select
  that one table for accounts with `mode = 'public'`. Leak check
  the payload before write.

v2 is listed so the schema does not paint us into a corner. It is
not part of cutover.

## 6. Ingest (daily collection)

The collector already writes files, then builds HTML. Keep that.
Add one step on the **same machine**:

```text
snapshot JSON + CSV on disk
        ↓
python3 scripts/ingest_supabase.py   # DATABASE_URL, owner .env
        ↓
python3 build.py                     # still files, until cutover
```

`ingest_supabase.py` (not written in this PR):

- Reads the same directories and flags `build.py` / `publish.sh`
  already use (`--data`, `--followers-dir`)
- Uses the same loaders
- Upserts the tables above
- Stores **basename** sources only
- Exits non-zero on API/auth errors; files remain
- Speaks **SQL in one transaction** through an optional Postgres
  driver (`psycopg`), not a chain of PostgREST upserts. Multi-table
  reconcile is not atomic over REST.
- That driver is an **optional extra**. Default `python3 build.py`
  (files) stays stdlib-only and must not import it. `--source
  supabase` fails with a clear message if the extra is missing.

Do not send ingest through a public HTTPS function that holds the
service role. A Netlify scheduled function with that key is a later
option only if it is a **private** function, the key is a secret,
and it is not shipped to the browser.

Idempotent: a second run is a full reconcile to the same result,
not a skip.

## 7. Builder compatibility

Add a read path later, not now:

```text
python3 build.py --source files      # default, today's behavior
python3 build.py --source supabase   # after golden tests pass
```

`--source supabase` reconstructs the in-memory payload the template
already consumes (`meta`, `followers.snapshots`, `followers.new` /
`lost` / `unavailable` / `not_following_back`, `posts`). It must not
change `template.html`. The owner-avatar step stays file/HTTP
(`place_owner_avatar`); v1 does not store avatars in Postgres.

Public mode still runs `to_public_payload` + `check_public_leaks.py`.
The database is not a substitute for that strip.

Golden compare drops `generated_at`, `data_dir`, `followers_dir`,
`out`, and `log` (file builds warn about paths the database path
will not repeat). Everything the UI reads must match.

## 8. Migration of existing data

One-shot, on the owner machine, against real `data/` (never in CI,
never against a tree that tests touch):

1. Create the Frankfurt project. Apply SQL migrations from a
   `supabase/migrations/` folder that does not appear until the
   implementation PR.
2. Insert the `accounts` row from `data/config.json`.
3. Call `load_followers` + `compute_follower_events` **once on the
   full series**, write snapshot metadata, events, unions, and the
   latest `current_*` lists.
4. Load posts with the existing merge. Do not upload CSV bytes.
5. Load `target_accounts` / `public_allowlist` if present.
6. **Golden compare:** build HTML from files and from Supabase with
   `--today` fixed. Compare the embedded payload after dropping
   `generated_at`, `data_dir`, `followers_dir`, `out`, and `log`.
   They must match. If they do not, do not cut over.

Keep the files. They are the rollback. Supabase **cannot** recreate
historical handle lists after cutover. If the owner machine dies and
the files are gone, you still have latest lists, events, and counts —
not `snapshot-*.json` for day N-30. Do not add an export that
pretends otherwise. Optional later: copy those JSON blobs into
Supabase Storage as files (not rows). That is extra insurance, not
the working set.

## 9. Cutover

| step | source of truth | public site |
|---|---|---|
| now | files | static HTML from files |
| validation | files; SB is a mirror | still files |
| cutover | Supabase; files are backup | static HTML from `build.py --source supabase` |
| later (optional) | Supabase | same static host, or `public_payloads` if we truly need live |

Validation is a short measured window (several successful daily
ingests + golden match), not a product mode. After cutover, the
collector may stop being load-bearing, but writing files a while
longer is cheap insurance.

Free-tier pause: a paused project makes ingest fail. Files still
build. Daily ingest is also the keep-alive. If ingest is skipped
for a week, unpause before relying on Supabase.

## 10. Multi-account / customers

`account_id` on every row from the first migration. v1 is still one
operator and a service role. A second X account is another
`accounts` row, same key. A second human is v2 (`account_members`).

Do not build Auth, dashboards-per-JWT, or a JS client to ship the
first extra handle.

## 11. Live updates

"Live" for this product means: new snapshot in, HTML rebuilt, CDN
updated. That is minutes, same as today. It is not Realtime and not
the browser polling PostgREST.

If someone later wants the page to refresh without a deploy, the
only safe feed is `public_payloads` (already stripped). That is a
separate product decision after cutover.

## 12. Free-tier budget (order of magnitude)

| thing | size idea |
|---|---|
| latest lists + events | low single-digit MB per busy account per year |
| snapshot metadata + posts | similar |
| daily full lists | **rejected** — would exhaust 500 MB |
| raw CSVs in Storage | **not in v1** — files already hold them |
| public visitors | **0 bytes** Supabase egress (they hit Netlify) |

Indexes: `(account_id, local_date)` on snapshots and events,
`(account_id, created_at)` on posts. No partitioning.

Connections: ingest and `build.py --source supabase` use **one**
session (session pooler URI, SSL required). Migrations use the
direct connection. Do not open a pool per Netlify request; there
are no Netlify requests to Postgres in v1.

## 13. Secrets and repo hygiene

Document names only in `.env.example`:

- `DATABASE_URL` — session-pooler URI, SSL, owner machine only.
  This is the only v1 secret. Do not add `SUPABASE_URL` /
  `SUPABASE_SERVICE_ROLE_KEY` until something actually uses REST
  or Storage.

The publishable/anon key is unused in v1. Do not put it in the
static HTML "just in case."

`data/` stays gitignored. CI never sees a live project. The golden
compare runs on the owner box (or a throwaway project). It is not a
GitHub Actions gate.

## 14. Implementation order (later PR, not this one)

1. Frankfurt project + migrations (tables, RLS, revokes, indexes).
2. `ingest_supabase.py` wrapping current loaders.
3. One-shot import + golden payload test on the owner box.
4. `--source supabase` behind a flag, default off.
5. Daily ingest beside the existing file write (full recompute +
   upsert, not incremental-from-DB).
6. Cut over the builder when goldens stay green.
7. Only then consider Auth / `public_payloads`.
8. Only after files are no longer written: design incremental
   ingest that keeps two days of member lists. Not before.

If a step does not earn the next one, stop.

## 15. Explicit refusals

- Storing every daily handle list "for flexibility"
- Rewriting event logic in SQL
- Dual-write as the steady state
- `anon` select on handle columns
- `user_metadata` in policies
- Views that bypass RLS
- Service role in frontend env or a public function
- Realtime on people tables
- supabase-js in `template.html`
- Using Netlify Blobs as the metrics store
- Guessing a region after the first row exists

---

## Review log

Self-review against code design, data model, RLS, ingest, migration,
operability, simplicity. UI is out of scope. Approval is two
consecutive zero-change rounds that both say `FINAL`, or stop at
round 7.

### Round 1

Changes:

- Snapshot grain is one row per Amsterdam date, matching
  `load_followers` / `merge_same_capture`, not one row per
  `captured_at`.
- Ingest must call those loaders; `latest.json` ranking stays theirs.
- Incremental events need the accumulated unavailable / verified /
  ever-seen sets, not two raw files alone.
- Persist only the new day's events plus capture-gap patches; one
  transaction with `current_*`.
- Drop redundant `is_public`; goal pair CHECK; `handle_key`;
  `bigint` counters; `not_following_back` computed at read time.
- Honest limit: losing the files loses historical lists.

Not FINAL.

### Round 2

Changes:

- v1 ingest is a full `load_followers` + `compute_follower_events`
  + reconcile upsert. Incremental-from-DB was wrong: after a write,
  `current_*` is today and cannot rebuild yesterday.
- Reconcile deletes dates that vanished from the file series.
- `og_image_url` on `accounts`. Storage upsert needs INSERT +
  SELECT + UPDATE. Golden compare is owner-box, not CI.
- Incremental-from-DB deferred until files stop being written.

Not FINAL.

### Round 3

Changes:

- v1 talks SQL in one transaction via optional `psycopg`. Default
  file builds stay stdlib. No PostgREST upsert chain.
- `DATABASE_URL` (session pooler, SSL). Indexes on `local_date`.
- `handle_key` on maps; status CHECK; default privileges revoke;
  ingest takes the same flags as `build.py`.
- Avatar stays file/HTTP. Golden compare also drops `log`.
- v2 public read keys off `mode = 'public'`.
- Reconcile deletes posts/maps that left the files.

Not FINAL.

### Round 4

Changes:

- Drop `ever_followers` from v1 (events already have `terug` /
  `nieuw`). Unions are a read model, not ingest inputs.
- No Supabase Storage CSVs in v1. Only `DATABASE_URL` as a secret.
- Events use `local_date` + `verified_info jsonb`. Migration text
  uses `load_followers`.

Not FINAL.

### Round 5

Changes:

- v1 auth is `DATABASE_URL` (superuser-class login), not a
  service-role JWT. Diagram comment updated.
- `--source supabase` reconstructs one latest-day struct for
  follow-back, instead of implying `current_*` alone is enough.

Not FINAL.

### Round 6

Changes:

- Every child row references `accounts(id) ON DELETE CASCADE`.
- Events also reference `follower_snapshots(account_id, local_date)`
  ON DELETE CASCADE so a removed day cannot leave orphan people
  rows.

Not FINAL.

### Round 7

Zero changes. The schema grain, ingest (full file recompute + one
transaction), privileges, cutover, and refusals hold. Stop at the
hard cap. Two consecutive FINAL rounds were not reached (Round 6
still added ON DELETE CASCADE).

FINAL.
