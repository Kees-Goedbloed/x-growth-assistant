# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Public pages open with a short visitor explainer (this account’s real growth dashboard; other handles stripped) and a “Free source on GitHub” link to the X Growth Assistant repo. Open Graph / X cards use `summary_large_image`, an absolute image URL when `site_url` or `SITE_URL` is set, and a 1200×630 share card with no fictional stamp.
- `docs/PLAN-supabase.md` — plan only — for moving snapshots, CSVs, and posts into Supabase (Frankfurt Free) without dropping the static builder until cutover.

### Changed

- Heatmaps and “What works best” bars use the same green / yellow / orange / red scale as KPIs, judged versus **your usual post**. Small-n cells shrink toward that average (k=3) and fade instead of going grey. “Strongest so far” uses a conservative lower bound and needs enough weight that an n=2 fluke cannot lead. Equal or single-item comparisons stay mid/yellow. A named “best time” still needs n ≥ 5.

### Added

- Public-by-default builds, automatic leak check, gitleaks CI, and agent onboarding (`AGENTS.md`, `scripts/setup.sh`, `skills/`).

## [0.1.0] - 2026-09-30

- Initial public-prep snapshot of the offline X growth dashboard (stdlib `build.py`, public/private modes, fixture suite). Version is declared in `pyproject.toml` only; no git tags or GitHub Releases are created by this work.
