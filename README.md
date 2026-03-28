# OpenCatWatch

> **[View the live dashboard →](https://smkwray.github.io/catwatch/)**

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
- watchlist cards are labeled `possible overlap`, carry explicit `public` vs `candidate` scope, and include rule-based reason text plus candidate diagnostics
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

Optional shared-data mode:

- `PROJ_SHARED_DATA_ROOT=/path/to/shared/pool` stores this repo's data under `$PROJ_SHARED_DATA_ROOT/catwatch/data/`
- `OPENCATWATCH_DATA_DIR` still overrides that path if you need a custom location
- `OPENCATWATCH_AS_OF_DATE=YYYY-MM-DD` pins registry/site/audit build math to a reproducible as-of date and is required for `make release-check`

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
make snapshot-check
```

`make release-check` runs the local operator-facing release flow:

1. lint
2. tests
3. registry rebuild
4. watchlist rebuild
5. site rebuild
6. audit generation
7. release-gate assertions

`make snapshot-check` validates the committed `apps/site/data/dashboard.json` and `reports/data_audit.json` snapshot without fetching live data.

## Rebuilding The Public Snapshot

If local raw/processed source data already exists:

```bash
export OPENCATWATCH_AS_OF_DATE=YYYY-MM-DD
make registry
make watchlist
make site
make audit
make review-queue
```

If you need to refresh live data first, set a real user agent and an explicit `OPENCATWATCH_AS_OF_DATE`, then run the relevant fetch commands. `fetch-bsx` currently falls back to reparsing saved raw BSX detail pages if the live listing routes are unavailable.

## Frontend

The static site in `apps/site/` is a data-rich dashboard built with plain HTML, CSS, and vanilla JavaScript. It reads precomputed JSON artifacts at runtime — no build step, no framework, no backend service.

### What the frontend shows

The dashboard is built as an editorial, data-journalism-style narrative rather than a generic admin panel:

- **Hero** — headline stats: total capital tracked, active tranches, identified sponsors, 12-month maturing capital
- **Sponsor concentration** — top 10 sponsors by placed USD capital (horizontal bar chart)
- **Geographic concentration** — bubble scatter on a world map, sized by capital, colored by dominant peril
- **Peril mix** — treemap showing how capital splits across peril families (US wind, CA earthquake, mortgage insurance, etc.)
- **Market timeline** — annual issuance bar chart showing growth from 2018 to present
- **Maturity runway** — three stat cards (12/24/36 month windows) plus a stacked maturity wall by quarter and peril
- **Watchlist pressure** — public vs. candidate split, promotion blockers, and most blocked issuer families
- **Evidence quality** — coverage scorecard with progress bars, gap counts, trigger coverage, and unresolved families
- **Data tables** — sortable, searchable, paginated views of the public watchlist, review candidates, and maturity wall

### Data sources

The site loads two JSON files:

| File | Path (relative to site root) | Required | Contents |
|------|------------------------------|----------|----------|
| Dashboard | `./data/dashboard.json` | Yes | KPIs, maturity wall, watchlist, diagnostics, matrix, notes, limitations |
| Audit | `./data/audit.json` | No (graceful degradation) | Coverage metrics, release-gate checks, review candidates |

`dashboard.json` is produced by `make site`. To make audit data available on the deployed site, copy the audit output into the site data directory:

```bash
cp reports/data_audit.json apps/site/data/audit.json
```

### Dark / light mode

The theme system uses CSS custom properties on `[data-theme]` with a toggle button in the hero:

1. On first load, checks `localStorage` for a saved preference.
2. Falls back to the OS preference via `prefers-color-scheme`.
3. Clicking the toggle switches the theme, persists to `localStorage`, and dispatches a `themechange` custom event on `<html>`.
4. All ECharts instances listen for `themechange` and recompute their full option objects — tooltip backgrounds, axis labels, gridlines, legend text, and series colors are all re-applied, not just the page chrome.

### Charting

Charts use [Apache ECharts 5](https://echarts.apache.org/) loaded from the jsDelivr CDN. ECharts was chosen because:

- Rich interactive tooltips, zoom, and legend filtering out of the box
- Full programmatic theme control — chart options are regenerated from a `getChartTheme()` helper on every theme toggle
- No build step; works from a CDN `<script>` tag
- Responsive resize via `chart.resize()` on window resize events

All chart text, axes, gridlines, tooltips, and legends use theme-aware color tokens so they remain readable in both light and dark mode.

### Local preview

```bash
# From the repo root — any static file server works
cd apps/site && python3 -m http.server 8000
# Open http://localhost:8000
```

Or use VS Code's Live Server, `npx serve apps/site`, etc. No npm install or build step is needed.

## Publishing GitHub Pages

The repo is designed to publish the committed snapshot in `apps/site/` directly. The Pages workflow does not fetch live data; it deploys the checked-in dashboard and accompanying assets from the current initial-release snapshot.

To include audit metrics on the deployed site, copy the audit JSON before committing:

```bash
cp reports/data_audit.json apps/site/data/audit.json
```

## Repository Map

- `src/opencatwatch/` - fetchers, pipelines, CLI
- `apps/site/` - static dashboard (HTML/CSS/JS + committed JSON data)
- `apps/site/assets/` - styles, theme toggle, main app logic
- `apps/site/data/` - committed dashboard snapshot
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
- public watchlist rows have zero unresolved tranche blockers

## License

MIT. See `LICENSE`.
