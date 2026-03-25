# Data sources

This repository is intentionally grounded in official or highly authoritative public sources.

## Core registry sources

### BSX
Use BSX listing and company detail pages as the initial discovery layer for cat-bond-like programmes and tranches.

Extract at least:
- title / series name
- company or issuer id
- listing type
- listing status
- listed date
- qualified investor flag
- currency
- sponsor or related-party field where visible
- source URL

### BMA
Use the Bermuda Monetary Authority regulated-entities search to enrich issuer / SPV names and identify restricted special purpose insurers where possible.

## Sponsor evidence

### SEC EDGAR
Use submissions JSON to pull recent filing metadata for public sponsors.
Optionally fetch filing pages or primary documents and scan for terms such as:
- catastrophe bond
- cat bond
- special purpose insurer
- indemnity bond
- parametric
- wildfire
- earthquake
- hurricane

Keep all extracted evidence snippets linked to the original filing URL.

## Hazard sources

### NOAA Storm Events
Historical weather-disaster event history for backfills and rough backtests.

### NWS alerts
Live U.S. hazard signals for active watchlists.

### IBTrACS
Global tropical cyclone tracks for current or recent storm overlays.

### USGS earthquakes
Current and historical earthquake events for quake-relevant bonds.

### OpenFEMA DisasterDeclarationsSummaries
Broad disaster context for sponsor and geography-level history.

## Optional later sources

- FEMA NFHL map services for flood context
- NOAA CDO station observations
- CME weather futures data for market context
