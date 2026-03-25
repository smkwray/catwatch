# Codex bootstrap guide

This file is the fastest path to useful output.

## Objective

Build a trustworthy v0 in three layers:

1. **Registry**: public tranche/programme inventory
2. **Watchlist**: rule-based possible-overlap signals from public hazards
3. **Static site**: precomputed dashboard JSON and a GitHub Pages front end

## Read order

1. `AGENTS.md`
2. `docs/PROJECT_PLAN.md`
3. `docs/DATA_SOURCES.md`
4. `docs/DATA_MODEL.md`
5. `docs/METHODS.md`

## First tasks

### Task 1: prove the registry flow
- run `python -m opencatwatch fetch-bsx --max-pages 2`
- inspect `data/processed/bsx/company_records.jsonl`
- improve parsing until sponsor / issuer / dates / listing status look clean

### Task 2: issuer enrichment
- run `python -m opencatwatch fetch-bma`
- inspect `data/processed/bma/entity_matches.jsonl`
- create better alias handling for SPV names

### Task 3: sponsor evidence
- run `python -m opencatwatch fetch-sec --sponsors-csv seeds/sponsor_universe_template.csv`
- inspect `recent_filings.jsonl` and `term_hits.jsonl`
- expand term list cautiously

### Task 4: normalized registry
- run `python -m opencatwatch build-registry`
- inspect `data/processed/registry/tranches.jsonl`
- add manual overrides only when deterministic parsing is insufficient

### Task 5: live event watch
- run `python -m opencatwatch fetch-nws`
- run `python -m opencatwatch fetch-usgs --days 14 --min-magnitude 5.5`
- run `python -m opencatwatch build-watchlist`

### Task 6: static dashboard
- run `python -m opencatwatch build-site`
- open `apps/site/index.html`

## Definition of done for v0

- 100+ public tranche-like records parse cleanly
- every tranche row has provenance
- sponsor pages have at least one evidence snippet where available
- watchlist signals include reasons and confidence
- site renders without a backend

## Non-goals for first milestone

- bond pricing
- investor holdings
- exact trigger outcomes
- comprehensive private-market coverage
