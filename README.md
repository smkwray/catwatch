# OpenCatWatch

**[View the live dashboard](https://smkwray.github.io/catwatch/)**

OpenCatWatch (`catwatch`) is a public registry of catastrophe bonds and other publicly listed insurance-linked securities (ILS), with a rule-based watchlist of natural-hazard events that may overlap a bond's covered peril, region and risk period. Tranche records come from Bermuda Stock Exchange (BSX) listings, with issuers and sponsors matched through the Bermuda Monetary Authority (BMA) register and SEC filings. Each record links to the sources behind it.

The repository holds the code, a committed snapshot of the static dashboard (`apps/site/`) and a data-quality audit (`reports/data_audit.md`). It is a work in progress and covers only what public listings show. It is not a pricing tool, a loss-trigger monitor or a complete ILS database, and a watchlist match means a possible overlap, not a triggered bond.

## How the data are built

- Tranche rows carry listing and sponsor source URLs where available.
- Manual sponsor aliases and tranche overrides in `data/manual/` must include a `source_url` and `notes`.
- A tranche enters the public watchlist only when its risk window is active or plausibly active, the event peril matches its peril, the event geography overlaps its coverage region, and its source evidence is strong enough. Matches with broad peril labels or weak region evidence are kept as review candidates and shown separately.
- Families with unresolved sponsor, region or maturity evidence are listed in the audit.

[`docs/METHODS.md`](docs/METHODS.md) describes the matching and linkage rules, and [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) the tables.

## Data sources

| Source | Used for |
|---|---|
| BSX listing and company pages | Tranche discovery: series, status, listing date, currency, sponsor where shown |
| BMA regulated-entities search | Issuer and special-purpose insurer names |
| SEC EDGAR filings | Sponsor evidence for public sponsors |
| National Weather Service alerts, NOAA Storm Events, IBTrACS tropical cyclone tracks, USGS earthquakes, OpenFEMA disaster declarations | Hazard events for the watchlist |
| `data/manual/` | Sourced aliases and overrides |

NOAA is the National Oceanic and Atmospheric Administration, IBTrACS the International Best Track Archive for Climate Stewardship, USGS the U.S. Geological Survey and FEMA the Federal Emergency Management Agency. Raw downloads (`data/raw/`) and rebuild artifacts (`data/processed/`) are not committed. See [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) and [`docs/LEGAL_NOTES.md`](docs/LEGAL_NOTES.md).

## Setup

Requires Python 3.11 or later.

```bash
python3 -m venv .venv
source .venv/bin/activate
make install
cp .env.example .env
```

Before any live fetch, set `OPENCATWATCH_USER_AGENT` in `.env` or your shell to a string with your real contact URL or email; the fetchers refuse the built-in default. Data go to `data/` unless `OPENCATWATCH_DATA_DIR` names another directory. `OPENCATWATCH_AS_OF_DATE=YYYY-MM-DD` pins the registry, dashboard and audit to one date and is required for `make release-check`.

## Usage

Check the committed snapshot without fetching anything:

```bash
make lint
make test
make snapshot-check
```

Fetch live data and rebuild everything with `make fetch` (or `make refresh`). With raw data already in place, rebuild step by step:

```bash
export OPENCATWATCH_AS_OF_DATE=YYYY-MM-DD
make registry watchlist site audit review-queue
```

`make site` writes `apps/site/data/dashboard.json` and `make audit` writes `reports/data_audit.json` and `reports/data_audit.md`. To show the audit on the dashboard, copy it into the site:

```bash
cp reports/data_audit.json apps/site/data/audit.json
```

If the live BSX listing pages are unavailable, `fetch-bsx` reparses previously saved BSX detail pages. `make release-check` runs lint, tests, the full rebuild and the audit, and fails if coverage falls below the release thresholds.

To preview the dashboard, run `python3 -m http.server -d apps/site 8000` and open `http://localhost:8000`. It is plain HTML, CSS and JavaScript with no build step; charts load Apache ECharts from a CDN.

## Repository map

```
src/opencatwatch/   Fetchers, pipelines and the opencatwatch command
apps/site/          Static dashboard and its committed data
reports/            Committed audit outputs
data/manual/        Manual evidence tables
catalog/sources.yml Source catalog
docs/               Methods, data model, sources and legal notes
tests/              Parser, pipeline and quality tests
```

## Limitations

- Coverage is limited to tranches visible in public listings; private placements and unlisted deals are missing.
- Sponsor, region and maturity evidence is incomplete for some issuer families; the audit lists them.
- Watchlist matching uses coarse peril, date and geography rules, so it cannot confirm a trigger, a loss or a payout.
- Programme shells without a maturity date are excluded from watchlist matching and maturity counts.
- The sponsor-peril matrix counts only identified sponsors.

## License

MIT. See [`LICENSE`](LICENSE).
