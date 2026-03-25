# AGENTS.md

This repository is designed so a coding agent can begin work immediately with minimal ambiguity.

## Mission

Build **OpenCatWatch**, an evidence-first open source registry and watchlist for catastrophe bonds and closely related public insurance-linked securities using free public data.

The first shipping goal is **not** a pricing terminal. The first shipping goal is a trustworthy public-data pipeline that can:

1. discover and normalize public cat-bond-like listings,
2. link them to issuers / SPIs / sponsors using official sources,
3. attach source evidence to every important field,
4. monitor live hazard feeds and create a **possible overlap** watchlist,
5. publish a static GitHub Pages dashboard.

## Product principles

- **Evidence first**: every material fact should trace back to a source URL, filing, or public page.
- **No false precision**: do not claim trigger events or losses unless trigger mechanics and event parameters make that supportable from public evidence.
- **Registry first**: reliable deal inventory before sophisticated analytics.
- **Static-site friendly**: precompute data artifacts; keep the front end thin.
- **Open-source safe**: prefer government/public-domain data; for non-government sources, publish normalized facts and source links rather than mirrored text.

## Hard scope boundaries

In scope for v0:
- catastrophe bonds and public ILS listings visible on BSX,
- Bermuda regulated-entity enrichment,
- SEC sponsor-disclosure scanning,
- NOAA Storm Events,
- NWS alerts,
- IBTrACS tropical cyclone tracks,
- USGS earthquakes,
- FEMA disaster declarations,
- a rule-based watchlist.

Out of scope for v0:
- secondary-market pricing,
- investor holdings,
- comprehensive private ILW / collateralized reinsurance tracking,
- opaque OTC weather derivatives.

## Recommended implementation order

1. Make `fetch-bsx` robust and extract a clean tranche registry.
2. Add `fetch-bma` and join BSX issuers to Bermuda entities.
3. Add `fetch-sec` for sponsor evidence.
4. Produce `tranches.jsonl` / `tranches.parquet`.
5. Add `fetch-nws`, `fetch-usgs`, `fetch-ibtracs`, `fetch-stormevents`, `fetch-fema`.
6. Build `watchlist/matches.jsonl`.
7. Build `apps/site/data/dashboard.json`.
8. Expand tests and add more fixtures.

## Data-quality guardrails

- Preserve raw downloads in `data/raw/`.
- Write normalized records to `data/processed/`.
- Prefer append-only manifests and deterministic rebuilds.
- Record `source_url`, `source_name`, `retrieved_at`, and `extraction_method`.
- Add `confidence` and `review_status` when inference is involved.
- Any geographic inference should be represented as coarse, text-backed coverage unless actual coverage geometry is public and trustworthy.

## Coding conventions

- Python 3.11+
- use `requests`, `beautifulsoup4`, `polars`, `duckdb`, `typer`
- avoid framework-heavy abstractions early
- keep functions pure where practical
- keep parsers deterministic and testable
- avoid LLM extraction for first pass; use rules and manual review queues

## How an agent should work in this repo

- Read `README.md` first, then the public reference docs in `docs/`.
- Use `catalog/sources.yml` for source URLs and rules.
- Run commands via `python -m opencatwatch --help` after installing editable with `pip install -e .`.
- Update tests whenever parser logic changes.
- Never add claims to the site that are not supported by source evidence or rule-based explanations.
