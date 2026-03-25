# OpenCatWatch

OpenCatWatch is an evidence-first public registry and watchlist for catastrophe bonds and closely related publicly visible insurance-linked securities.

This repository is an initial public release and still a work in progress. The current snapshot is meant to be credible, inspectable, and reproducible, not complete.

The current release goal is a trustworthy public snapshot:

- a normalized tranche registry built from public listings
- sponsor enrichment tied to source evidence
- a rule-based hazard overlap watchlist
- a committed static dashboard for GitHub Pages
- a committed audit report with a hard public-release gate

## What It Is

- Registry-first public infrastructure for cat-bond-like issuance
- A static, precomputed dashboard and audit that can be committed to GitHub
- A conservative watchlist of possible overlaps between public hazards and public tranche records
- A codebase that prefers source URLs, filing links, and explicit notes over opaque enrichment

## What It Is Not

- Not a pricing terminal
- Not a loss-trigger monitor
- Not a comprehensive private ILS database
- Not a substitute for offering documents or sponsor disclosures

## Evidence Model

Every material public-facing artifact should stay traceable:

- tranche rows carry listing evidence and sponsor evidence URLs when available
- manual sponsor aliases and tranche overrides require both `source_url` and `notes`
- watchlist cards are labeled `possible overlap` and include rule-based reason text
- unresolved families are called out in the audit’s public limitations section

## What Gets Committed

Committed:

- code, tests, docs, fixture data
- manual evidence tables in `data/manual/`
- the current static snapshot in `apps/site/data/dashboard.json`
- the current audit outputs in `reports/data_audit.json` and `reports/data_audit.md`

Not committed:

- raw downloads in `data/raw/`
- processed rebuild artifacts in `data/processed/`

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e '.[dev]'
cp .env.example .env
```

Before any live fetch, set a real contact string:

```bash
export OPENCATWATCH_USER_AGENT="OpenCatWatch/0.1 (contact contact@example.com)"
```

The fetchers will reject the placeholder default.

## Common Commands

```bash
make lint
make test
make registry
make watchlist
make site
make audit
make review-queue
make release-check
```

`make release-check` runs the local operator-facing release flow:

1. lint
2. tests
3. registry rebuild
4. watchlist rebuild
5. site rebuild
6. audit generation
7. release-gate assertions

## Rebuilding The Public Snapshot

If local raw/processed source data already exists:

```bash
make registry
make watchlist
make site
make audit
make review-queue
```

If you need to refresh live data first, set a real user agent and run the relevant fetch commands. `fetch-bsx` currently falls back to reparsing saved raw BSX detail pages if the live listing routes are unavailable.

## Publishing GitHub Pages

The repo is designed to publish the committed snapshot in `apps/site/` directly. The Pages workflow does not fetch live data; it deploys the checked-in dashboard and accompanying assets from the current initial-release snapshot.

## Repository Map

- `src/opencatwatch/` - fetchers, pipelines, CLI
- `apps/site/` - static dashboard
- `docs/` - public reference docs only
- `catalog/sources.yml` - source catalog
- `data/manual/` - tracked manual evidence tables
- `reports/` - committed public audit outputs
- `tests/` - parser, pipeline, and quality regressions

## Public Docs Boundary

`docs/` is part of the public repo surface. Keep only stable public reference material there. Internal planning notes, operator checklists, release playbooks, and agent/session bootstrap docs belong under `do/` and must stay untracked.

## Current Public Gate

The first public push targets a usable snapshot, not a perfect market map. The release gate currently enforces:

- sponsor coverage on material tranches >= 70%
- region coverage on material tranches >= 95%
- outstanding rows missing maturity <= 40
- `other_property_cat` rows in the registry <= 25
- non-demo dashboard snapshot present
- current audit outputs present
- manual evidence metadata complete

## License

MIT. See `LICENSE`.
