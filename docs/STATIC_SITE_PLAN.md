# Static site plan

The first static dashboard should answer four questions:

1. What is active now?
2. What matures next?
3. What might be exposed right now?
4. Which sponsors are concentrated in which perils?

## Homepage sections

### Hero KPIs
- active tranches
- sponsors
- next 12m maturities
- watchlist matches
- data refresh timestamp

### Maturity wall
Thin bars for active tranches sorted by maturity date.

### Watchlist cards
Recent events and matched tranche snippets with reason text.

### Sponsor × peril matrix
Compact heatmap or table.

### Evidence notes
Explain that matches are possible overlaps, not confirmed triggers.

## Static data contract

The dashboard should read one JSON file:
`apps/site/data/dashboard.json`

Keep the schema human-readable and stable enough for external contributors.
