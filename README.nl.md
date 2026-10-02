# X-groeidashboard

Nederlands. English: [README.md](README.md).

Lokaal, offline dashboard voor groei op X. Geen internet, geen CDN:
`build.py` (alleen Python 3 standaardbibliotheek) leest de data en schrijft één zelfstandig `index.html`
waarin alle data als JSON is ingebed. Werkt direct via `file://`.

**Privacy:** `data/` wordt nooit gecommit. Publieke builds (`--mode public`) strippen handles en namen van anderen.

```
x-growth-assistant/
├── build.py            # bouwt index.html
├── template.html       # HTML/CSS/JS-sjabloon (grafieken = eigen inline SVG, geen externe libs)
├── index.html          # GEGENEREERD — echte data
├── serve.sh            # optioneel: lokale http-server op een vrije poort
├── README.md           # Engels (hoofd-README)
├── README.nl.md        # dit bestand
├── data/               # lokale inputs (gitignored via data/**, nooit committen)
│   ├── followers/      # snapshot-YYYY-MM-DD.json
│   ├── posts/          # *.json / *.jsonl  (per-post metrics)
│   ├── analytics-csv/  # X Analytics CSV-exports
│   ├── config.json     # optioneel (gitignored; zie data/config.example.json)
│   └── target_accounts.json  # optioneel, alleen public-mode groottes
└── test-fixtures/      # FICTIEVE testdata + generator (nooit in data/ zetten)
```

## Dagelijkse workflow

1. Follower-snapshot maken. Zet het bestand in `data/followers/`, of geef een extra map
   met `--followers-dir` (read-only). (Hetzelfde `captured_at` in beide = één snapshot;
   de versie in `data/followers/` wint.)
2. Optioneel: post-metrics in `data/posts/` en/of X Analytics CSV-exports in `data/analytics-csv/`.
3. Bouwen:
   ```
   python3 build.py
   ```
   De build-output toont per snapshot de aantallen, gemapte/niet-gemapte CSV-kolommen en waarschuwingen
   (ook onderaan het dashboard onder "Bronnen & build-log").
4. Openen: `file:///pad/naar/x-growth-assistant/index.html`
   (of `./serve.sh` → `http://127.0.0.1:<poort>/index.html`).

Opties: `--data MAP`, `--out BESTAND`, `--followers-dir MAP` (geen default),
`--no-followers` (geen extra snapshots), `--mode public|private` (default public),
`--today YYYY-MM-DD` (referentiedatum; standaard vandaag in Europe/Amsterdam).

## 1. Follower-snapshot — `data/followers/snapshot-YYYY-MM-DD.json`

Canoniek formaat = JSON-snapshot + drie optionele velden. Er hoeft dus niets te veranderen;
alleen `following_handles` en `unavailable` toevoegen levert extra inzichten op.

```json
{
  "account": "demo_owner",
  "date": "2026-09-26",
  "captured_at": "2026-09-26T09:45:00+02:00",
  "profile_followers": 107,
  "profile_following": 120,
  "collected_count": 105,
  "complete": false,
  "handles": ["demo_follower_a", "demo_follower_b", "demo_follower_c"],
  "following_handles": ["demo_follower_a", "peer_alpha", "demo_follower_c"],
  "following_complete": true,
  "unavailable": ["some_deleted_acct", {"handle": "suspended_acct", "reason": "geschorst"}],
  "verified_unfollowers": ["example_user1", {"handle": "example_user2", "checked_at": "2026-09-25T12:30:00+02:00", "note": "profiel gecontroleerd"}],
  "notes": "vrije tekst"
}
```

| veld | verplicht | betekenis |
|---|---|---|
| `handles` | **ja** | handles van volgers (zonder of met `@`, of x.com-URL). Vergelijking is hoofdletter-ongevoelig. Alias: `followers`. |
| `captured_at` of `date` | ja (één van beide) | ISO-tijd met tijdzone. `date` (YYYY-MM-DD) wint; anders dag van `captured_at` in Europe/Amsterdam; anders datum uit bestandsnaam. |
| `profile_followers` | aanbevolen | volgersteller op het profiel (bron voor grafiek en netto groei). Alias: `followers_count`. |
| `profile_following` | optioneel | following-teller. Alias: `following_count`. `null` = niet vastgelegd. |
| `complete` | aanbevolen | `true` als de handles-lijst alle volgers bevat. Ontbreekt het, dan: `len(handles) >= profile_followers`. |
| `following_handles` | optioneel | wie het dashboard-account volgt. Nodig voor "volgt het account terug?", "volgt het account nog?", kandidaten om te ontvolgen en "volgt niet terug". Alias: `following`. |
| `following_complete` | optioneel | of `following_handles` compleet is. |
| `unavailable` | optioneel | handles die verwijderd/geschorst zijn (strings of `{"handle","reason"}`). Geldt vanaf die snapshot voor alle diffs. |
| `verified_unfollowers` | optioneel | handles die handmatig als ontvolger zijn gecontroleerd (strings of `{"handle","checked_at","note"}`). Verdwijnt zo'n handle uit de lijst, dan telt hij als **ontvolgd (zeker, "geverifieerd")**, ook als `complete: false`. Geldt vanaf elke snapshot waarin het staat, voor alle diffs. `unavailable` gaat vóór. |
| `collected_count`, `notes`, `diff_vs_previous` | optioneel | worden getoond/genegeerd; `build.py` berekent diffs zelf. |

Bestandsnaam: `snapshot-YYYY-MM-DD.json` (`snapshot-YYYYMMDD-HHMMSS.json` en `latest.json` werken ook).
Meerdere snapshots op één dag → de laatste (`captured_at`) telt; ontbrekende velden worden aangevuld uit eerdere
van die dag.

### Hoe volgers-diffs werken
Tussen twee opeenvolgende snapshot-dagen:
- **Nieuw**: handle staat er nu wel, vorige keer niet, en is nooit eerder gezien.
  **Terug**: stond er eerder al eens in (meestal capture-gat) — telt niet als nieuwe volger.
- Handle verdwenen uit de lijst:
  - in `unavailable` → **verwijderd/geschorst** (niet als ontvolger geteld);
  - in `verified_unfollowers` → **ontvolgd** (zeker, label "geverifieerd");
  - verschijnt in een latere snapshot weer → **capture-gat** (niet geteld);
  - huidige snapshot `complete: true` → **ontvolgd** (zeker);
  - huidige snapshot onvolledig → **mogelijk ontvolgd**.
- **Volgt het account terug? / volgt het account nog?**: staat de handle in `following_handles` → *ja*. Staat hij er niet in:
  bij `following_complete: true` → *nee*; bij een onvolledige following-lijst → **"onbekend (lijst onvolledig)"**
  (het dashboard claimt dan niet dat het account iemand níet volgt). Bovenaan staat "Following-lijst onvolledig: X van Y
  geladen" (geladen `following_handles` vs. `profile_following`).
- **Kandidaten om te ontvolgen** = ontvolgers (zeker of mogelijk) waarvan "volgt het account nog?" *ja* of
  *onbekend (lijst onvolledig)* is (die laatste handmatig controleren).
- **Volgt niet terug** = `following_handles` minus `handles` van de laatste snapshot mét following-lijst
  (minus `unavailable`). Bij een onvolledige following-lijst is dit een **ondergrens**; bij een onvolledige
  volgerslijst staat per account "waarschijnlijk (volgerslijst X/Y)" — hooguit Y−X ervan volgt toch terug.

## 2. Post-metrics — `data/posts/*.json` of `*.jsonl`

Eén bestand per dag aanbevolen, bv. `data/posts/posts-2026-09-26.json`:

```json
{
  "captured_at": "2026-09-26T22:00:00+02:00",
  "posts": [
    {
      "id": "1839000000000000001",
      "url": "https://x.com/demo_owner/status/1839000000000000001",
      "created_at": "2026-09-26T09:12:00+02:00",
      "type": "post",
      "media": "image",
      "text": "Mijn post…",
      "impressions": 1520, "likes": 31, "replies": 4, "reposts": 2, "quotes": 1,
      "bookmarks": 3, "profile_visits": 9, "link_clicks": 2, "new_follows": 1
    },
    {
      "id": "1839000000000000002",
      "created_at": "2026-09-26T10:40:00+02:00",
      "type": "reply", "media": "text", "in_reply_to_handle": "peer_alpha",
      "in_reply_to_created_at": "2026-09-26T10:31:00+02:00",
      "text": "Mooie take!", "impressions": 310, "likes": 5, "replies": 1, "reposts": 0,
      "quotes": 0, "bookmarks": 0, "profile_visits": 3, "link_clicks": 0, "new_follows": 0
    }
  ]
}
```

Ook toegestaan: een kale JSON-lijst `[ {...}, {...} ]`, of JSONL (`.jsonl`, één post-object per regel, optioneel
met eigen `captured_at`).

| veld | waarden |
|---|---|
| `id` | post-id (string). Mag ontbreken als `url` een `/status/<id>` bevat. |
| `url` | optioneel; standaard `https://x.com/<account>/status/<id>` |
| `created_at` | ISO 8601 **met tijdzone** (zonder tijdzone → Europe/Amsterdam + waarschuwing) |
| `type` | `post` \| `reply` \| `repost` \| `quote` (NL-varianten `reactie`, `citaat` worden ook herkend) |
| `media` | `text` \| `image` \| `video` \| `thread` (ontbreekt → "onbekend"). Optioneel, backwards compatible: `multi_image`, `gif`, `poll`, `link`, `article`. Ontbreekt het veld, dan wordt alleen een **externe URL in de tekst** als `link` afgeleid; verder blijft het onbekend (nooit gokken op foto/video). |
| `in_reply_to_handle` | voor replies: op wie gereageerd werd (eigen handle = reactie op zichzelf, apart geteld) |
| `in_reply_to_created_at` | optioneel, ISO 8601: tijdstip van de **parent-post** waarop deze reply reageert. Nodig voor “reactiesnelheid” (binnen 15 min / 1 u / 4 u / later). Ontbreekt het → “niet beschikbaar in de huidige data”; er wordt nooit een parent-tijd geraden. |
| metrics | `impressions, likes, replies, reposts, quotes, bookmarks, profile_visits, link_clicks, new_follows` (gehele getallen; ontbrekend = onbekend) |
| extra metrics (optioneel) | `engagements` (X's eigen totaal), `shares`, `detail_expands`, `hashtag_clicks`, `permalink_clicks` — worden getoond in de engagement-tabellen als ze aanwezig zijn |

**Latere snapshots overschrijven eerdere** per `id`, veld voor veld (alleen velden die in de nieuwere snapshot staan).
Volgorde: `captured_at` van het record → `captured_at` van het bestand → datum in bestandsnaam (23:59) → mtime.
Een update-bestand met alleen `{"id": "...", "impressions": 4000}` is dus prima.

## 3. X Analytics CSV — `data/analytics-csv/*.csv`

Zet de export van X ongewijzigd in deze map. Tolerante import:
- scheidingsteken `,` `;` of tab (automatisch), UTF-8 (met/zonder BOM), UTF-16 of cp1252;
- kolomnamen hoofdletter-ongevoelig, leestekens genegeerd, Engelse en Nederlandse varianten:

| veld | herkende kolomnamen (selectie) |
|---|---|
| id | Post id, Tweet id, ID, Post-ID |
| url | Post Link, Tweet permalink, Permalink, URL, Link naar post |
| text | Post text, Tweet text, Text, Tekst |
| datum/tijd | Date, Time, Created at, Datum, Tijd, Tijdstip, Geplaatst op (losse Datum + Tijd worden samengevoegd) |
| impressions | Impressions, Impressies, Weergaven, Vertoningen, Views |
| likes | Likes, Vind-ik-leuks, Favorites |
| replies | Replies, Antwoorden, Reacties |
| reposts | Reposts, Retweets |
| quotes | Quotes, Citaten |
| bookmarks | Bookmarks, Bladwijzers |
| profile_visits | Profile visits, User profile clicks, Profielbezoeken |
| link_clicks | Link clicks, URL clicks, Linkklikken |
| new_follows | New follows, Follows, Nieuwe volgers |
| engagements | Engagements, Betrokkenheid, Interacties |
| shares | Shares, Gedeeld, Delen |
| detail_expands | Detail Expands, Detailuitbreidingen |
| hashtag_clicks | Hashtag Clicks, Hashtagklikken |
| permalink_clicks | Permalink Clicks, Permalinkklikken |
| type / media / in_reply_to_handle | Type, Media, In reply to / Antwoord op |

- Niet-gemapte kolommen (bv. `Engagement rate`) worden in de build-output en het build-log gemeld en genegeerd.
- Scheidingsteken wordt uit de kopregel bepaald; quoting is altijd standaard (`"`). Rijen met een afwijkend
  aantal kolommen worden gemeld. De build meldt "N post-rijen ingelezen (van M datarijen)".
- Getallen als `1.234`, `1,234` en `1.2K` worden begrepen. Datums: ISO, `2026-09-22 14:03 +0000`,
  `Mon, Sep 22, 2026`, `09/22/2026`, `22-09-2026 14:03`, `ma 22 sep. 2026 14:03`, enz.
- Tijden **zonder** tijdzone in CSV worden als **UTC** gelezen (X-exports zijn doorgaans UTC); de build waarschuwt.
  Aanpassen in `data/config.json`: `{"csv_timezone": "Europe/Amsterdam"}`.
- **Datum zonder tijd** (zoals de huidige X-content-export: `Fri, Sep 25, 2026`) → die kalenderdag in
  Europe/Amsterdam, zonder tijdzone-verschuiving (kan nooit naar een andere dag schuiven). **Tijd uit de
  post-id:** als er geen expliciete tijd is, leidt `build.py` de creatietijd af uit de X-snowflake
  (`ms = (id >> 22) + 1288834974657` Unix-epoch-ms UTC, daarna Europe/Amsterdam). De id komt uit
  `Post id` / `Tweet id` of uit het numerieke deel van de post-URL (`/status/<id>`). De afgeleide
  Amsterdam-datum moet overeenkomen met de CSV-datum (± 1 dag, voor tijdzone); anders wordt de
  snowflake-tijd genegeerd (waarschuwing in het build-log) en blijft het tijdstip onbekend.
  Een datum-zonder-tijd overschrijft nooit een al bekende exacte tijd van dezelfde post op dezelfde dag.
- Geen media-kolom → "beste posttype (tekst/afbeelding/video/thread)" blijft leeg met uitleg.
- Geen type-kolom → type wordt afgeleid: tekst begint met `RT @` → repost, met `@naam` → reply (op `naam`),
  anders post (gemarkeerd met `*`). Een expliciet `type` uit JSON wordt nooit door zo'n gok overschreven.
- CSV zonder post-id/url/tekst (account-dagoverzicht) wordt overgeslagen met een melding.
- CSV-rijen en JSON-records met dezelfde `id` worden samengevoegd (JSON-bestanden winnen bij gelijke tijd).

## `data/config.json` (optioneel)

Kopieer `data/config.example.json` (fictieve waarden; `goal_followers` / `goal_date` zijn `null`). **Niet committen** met echte metrics of tokens.

```json
{
  "account": "demo_owner",
  "display_name": "Demo Owner",
  "site_url": "https://example.com",
  "repo_url": "https://github.com/example/x-growth-assistant",
  "og_image_url": "",
  "lang": "nl",
  "csv_timezone": "UTC",
  "goal_followers": null,
  "goal_date": null
}
```

| veld | betekenis |
|---|---|
| `account` | X-handle (geen hardcoded default; zet dit in config) |
| `display_name` | in de header; zonder waarde: generieke titel |
| `site_url` | canonical / Open Graph URL (public mode). Nodig voor een absolute `og:image` op X. `SITE_URL` / `PUBLIC_SITE_URL` / `URL` zijn fallbacks. |
| `repo_url` | privé-footer “Built with x-growth-assistant”; leeg = verborgen |
| `source_repo_url` | publieke “Free source on GitHub”-link (default `https://github.com/Kees-Goedbloed/x-growth-assistant`) |
| `og_image_url` | override OG-afbeelding (default `{site_url}/assets/og-image.png`) |
| `lang` | `nl` (default) of `en` voor header/footer/sectietitels |
| `csv_timezone` | tijdzone voor CSV-tijden zonder offset (default `UTC`) |
| `goal_followers` | optioneel, positief geheel getal: volgersdoel. **Niet committen met een echte waarde.** Ontbreekt het (of `null`/leeg) samen met `goal_date`, dan crasht de build niet: het dashboard toont de Nederlandse noot *Nog geen doel ingesteld (goal_followers / goal_date in data/config.json)* plus het huidige tempo en een prognose. |
| `goal_date` | optioneel, `YYYY-MM-DD`. Moet **samen** met `goal_followers` gezet zijn, anders blijft het doel uit. |

`data/target_accounts.json` (gitignored; voorbeeld: `data/target_accounts.example.json`) is `handle → volgersaantal`. Alleen gebruikt in `--mode public` om reacties te groeperen op doelgrootte (`<1k`, `1k–10k`, `10k–100k`, `>100k`). Ontbreekt het bestand, dan groepeert de public build op hoe vaak er op hetzelfde account is gereageerd (`1×`, `2–4×`, `5×+`). Groepen met minder dan 5 verschillende accounts worden weggelaten.

Is het doel gezet, dan tekent sectie 2 de werkelijke volgers, de rechte “op schema”-lijn van de eerste snapshot naar het doel, en prognoses op het tempo van de laatste 7 en 30 dagen (status op schema / achter / voor, nodig tempo per week, verwachte datum per tempo). Bij minder dan 2 snapshots over minstens 3 dagen valt het tempo terug op de som van `new_follows` uit de X-analytics, duidelijk gelabeld *op basis van nieuwe volgers uit X-analytics*.

## Metrics — wat betekent wat

Alle tijden en dagen in **Europe/Amsterdam**. De periodefilter (7 / 30 / 90 dagen / Alles / eigen periode) werkt op
alle secties; "vandaag" = de referentiedatum van de build.

**1. Overzicht** — referentiedag = einde van de gekozen periode.
- *Volgers / Following*: profieltellers uit de snapshot van precies die dag ("geen snapshot" als die ontbreekt).
- *Netto groei dag/week/maand*: volgers(laatste snapshot ≤ referentiedag) − volgers(laatste snapshot ≤ referentiedag − 1/7/30).
  Is er nog geen 7/30 dagen historie, dan staat erbij "sinds <eerste snapshot>".
- *Posts vandaag*, *impressies* en *gemiddelde engagement rate over 7 dagen* (referentiedag en 6 dagen ervoor, met vergelijking met de 7 dagen daarvoor).

**2. Volgers** — zie "Hoe volgers-diffs werken" hierboven. De grafiek toont profielteller volgers, following en
(gestippeld) het aantal daadwerkelijk verzamelde handles. **Volgersdoel** (optioneel `goal_followers` /
`goal_date`) toont tempo, prognose en — als het doel gezet is — of je op schema ligt.

**3. Posts** — aantal per dag per type. *Streak* = aantal dagen op rij t/m de referentiedag met minstens één post,
repost of quote (reacties tellen mee als je het vinkje aanzet). Als vandaag nog niet gepost is, loopt de streak t/m
gisteren. *Dagen zonder post* telt alleen vanaf de eerste bekende post.

**4. Engagement**
```
Per post:
  als X's eigen "engagements" aanwezig is:  ER = engagements / impressions                       (marker X)
  anders:  ER = (likes + replies + reposts + quotes + bookmarks + profile_visits + link_clicks) / impressions  (marker b)
Per dag / periode / groep (gewogen):
  ER = Σ (engagements-of-berekend per post) / Σ impressions
```
- Alleen posts met impressies > 0 tellen mee. Het dashboard toont per post de marker **X** of **b**, per dag
  "X" / "b" / "gemengd", en bovenaan hoeveel posts elke bron gebruiken.
- Let op: X's `engagements` omvat ook o.a. detail expands en klikken, dus is meestal hoger dan de berekende som.
- Reposts worden uitgesloten (hun metrics horen bij de originele post). Filter: alle behalve reposts / alleen eigen
  posts + quotes / alleen reacties.
- *Gemiddeld aantal nieuwe volgers per post* = Σ new_follows / aantal posts waarvoor new_follows bekend is.
- **Van profielbezoek naar volger**: conversie = `new_follows / profile_visits` over de gekozen periode en per
  ISO-week (label W36). Daarnaast profielbezoeken en nieuwe volgers per 1.000 impressies, met ruwe aantallen in
  tooltip en tabel.

**5. Reactie-activiteit** — replies (`type: reply`) die het dashboard-account zelf plaatst: per dag, op welke accounts
(`in_reply_to_handle`, of het eerste `@handle` als het type uit de tekst kwam). Self-replies tellen niet mee in
**Reactie-rendement per account**: sorteerbare tabel (klik kolomkoppen) met zoekfilter, aantal reacties, impressies,
gemiddelde én mediaan impressies per reactie, ER, profielbezoeken, nieuwe volgers en volgers per reactie.
Flag *veel moeite, weinig bereik* bij ≥ 5 reacties en gem. impressies per reactie &lt; 30 (constanten bovenaan
`build.py`). Top 10 beste volgersbronnen (meeste nieuwe volgers, daarna volgers/reactie) en top 10 op gem.
impressies (min. 3 reacties). *Reacties ontvangen op eigen posts* = Σ `replies` van eigen posts van het account en
quotes in de periode (op postdatum).

**6. Top posts & patronen** — eigen posts + quotes. Top 5 per ISO-week en per maand op impressies en op ER.
Beste dag van de week / beste uur (Amsterdam) / beste posttype = hoogste **mediaan** impressies per post;
gemiddelde staat ernaast (n altijd zichtbaar), omdat één uitbijter het gemiddelde kan scheeftrekken.
Tijden komen uit `created_at` of uit de snowflake-id.

**7. Wat werkt het best** — wanneer posten/reageren, en welk soort bericht (mediaan, altijd met n).
Heatmaps dag × uur (Europe/Amsterdam; tooltip toont ook het gemiddelde), type/media/lengte/tekstkenmerken, top-recepten. Groepen met
n &lt; 5 zijn “te weinig data”. Dit is correlatie, geen oorzakelijkheid. Zie invoervelden hierboven
(`media`, `in_reply_to_created_at`, `created_at` mét tijd of snowflake-id).

## Beperkingen
- X geeft niet aan *waarom* iemand uit de volgerslijst verdwijnt: ontvolgen, verwijderd, geschorst of een
  laad-/scrollprobleem. Alleen met `unavailable` wordt iets als verwijderd/geschorst getoond.
- Snapshots zijn vaak `complete: false` (X laadt de lijst virtueel), dus verdwenen handles zijn
  "mogelijk ontvolgd" totdat ze in een latere snapshot terugkomen (dan: capture-gat).
- Zonder `following_handles` zijn terugvolg-status, kandidaten om te ontvolgen en "volgt niet terug" onbekend.
- Metrics groeien na plaatsing; de laatste aangeleverde snapshot per post telt.
- `new_follows` per post en `profile_visits` zijn alleen beschikbaar als X ze in de export/metrics toont.
- Tijden zonder tijdzone zijn een aanname (zie CSV).
- De huidige X-content-export heeft geen tijd, geen type, geen media en geen quotes-kolom: type wordt afgeleid
  (`@…` → reactie, `*`); de **tijd** komt uit de snowflake in de Post id als die bij de CSV-datum past;
  "beste posttype" blijft leeg zonder media-kolom; quotes = onbekend.

## Testen
```
python3 -m unittest discover -s tests -v
```
De suite schrijft **niet** in de echte `data/`-map (ook niet als daar echte snapshots staan). Tests die git nodig hebben, maken een tijdelijke repo met een nep-`origin`, dus de suite werkt ook in een map zonder `.git`. `python3 test-fixtures/make_fixtures.py` vult alleen `test-fixtures/data/` (fictief, gitignored).

```
python3 test-fixtures/make_fixtures.py
python3 build.py --data test-fixtures/data --out /tmp/index.test.html --today 2026-09-25
```
`/tmp/index.test.html` bevat uitsluitend fictieve data (tekst "TESTFIXTURE"). Het echte `index.html` wordt alleen uit
`data/` (plus optioneel `--followers-dir`) gebouwd.

Optioneel: `data/public_allowlist.json` (gitignored; voorbeeld `data/public_allowlist.example.json`) voor extra handles die de public leak-check mag laten staan. De checker flagt geen kale woorden in posttekst die toevallig gelijk zijn aan een handle.

## Publiceren / hosting

Twee Netlify-sites, zelfde code: publiek (geen auth) en privé (HTTP Basic Auth). Ruwe `data/` gaat
**niet** in git en **niet** online. `scripts/publish.sh` bouwt lokaal beide modes en deployt `dist/`
met de Netlify CLI. Zie **[DEPLOY.md](DEPLOY.md)**.
