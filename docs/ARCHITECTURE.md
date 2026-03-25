# Architecture

## Overview

The architecture is intentionally simple:

1. fetch raw source artifacts to `data/raw/`
2. parse and normalize into `data/processed/`
3. assemble registry and watchlist artifacts
4. emit static JSON for the front end

## Logical layers

### Source adapters
Small modules in `src/opencatwatch/sources/` that know how to:
- request documents politely,
- save raw payloads,
- parse source-specific fields,
- emit normalized row-oriented records.

### Registry pipeline
`pipelines/registry.py` merges:
- BSX listing records
- BMA entity matches
- SEC sponsor hints
- manual overrides

### Watchlist pipeline
`pipelines/watchlist.py` reads:
- normalized tranches
- normalized events from NWS / USGS / IBTrACS / optional others
- rule-based peril and geography matchers

### Site pipeline
`pipelines/site_data.py` computes:
- KPIs
- maturity wall data
- watchlist cards
- sponsor-peril matrix
- notes / caveats

## Storage format

- raw downloads: HTML, JSON, CSV.GZ, Parquet
- normalized tables: JSONL, optionally Parquet
- later: DuckDB or Postgres/PostGIS

## Why static-first

Static deployment is cheap, auditable, and easy to share. Most of the heavy work belongs in scheduled builds, not in request-time APIs.
