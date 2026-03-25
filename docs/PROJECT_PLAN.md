# Project plan

## Vision

OpenCatWatch should become the most transparent open-source starting point for tracking catastrophe bonds and adjacent public ILS structures with free public data.

## Product shape

### Deliverable A: public tranche registry
Normalized programme / series / tranche records, with source URLs and extracted fields.

### Deliverable B: sponsor intelligence
Sponsor pages summarizing recent public disclosure references to cat bonds or related capital-markets reinsurance.

### Deliverable C: event watchlist
Rule-based event-to-bond matching that surfaces **possible overlaps** between current hazards and active risk windows.

### Deliverable D: static dashboard
A GitHub Pages-compatible site with a maturity wall, watchlist, sponsor-peril heatmap, and evidence links.

## Timeline

### Phase 1: 0-30 days
- robust BSX discovery and parsing
- initial BMA enrichment
- tranche data model stabilized
- test fixtures for listing pages

### Phase 2: 31-60 days
- SEC sponsor evidence scanning
- NWS + USGS + IBTrACS ingestion
- watchlist rules v1
- dashboard JSON generation

### Phase 3: 61-90 days
- public snapshots
- improved search/filter UX
- expanded historical hazard backfills
- contributor docs and issue templates

## Success criteria

- users can browse active tranches and maturities
- users can inspect source evidence behind every key field
- users can see recent events that may overlap active coverages
- contributors can rebuild the dataset locally and in CI
